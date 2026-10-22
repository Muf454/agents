#!/usr/bin/env python3
"""Standard-library helpers for safe copying, Markdown parsing, and evidence.

The shell scripts own the workflow. This module never invokes an AI agent.
"""
import argparse
import contextlib
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta, timezone


def fail(message):
    raise ValueError(message)


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.DEVNULL)


def atomic(path, contents):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as file:
        temp = Path(file.name)
        file.write(contents)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def safe_paths(root, destinations=None):
    """Never copy/write through a symlink; fail before setup changes anything."""
    root = Path(root).resolve()
    if destinations is None:
        destinations = ['.ai', '.ai/local', '.ai/state.md', '.ai/tasks.md',
                        '.ai/run-log.md', '.ai/reviews/current.md', '.ai/validate',
                        '.ai/permissions.allow', '.ai/prompts/resume.md',
                        '.ai/prompts/implement.md', '.ai/prompts/review.md']
        ai = root / '.ai'
        if ai.is_dir() and not ai.is_symlink():
            destinations += [str(p.relative_to(root)) for p in ai.rglob('*')]
    for relative in destinations:
        path = root / relative
        for part in [path, *path.parents]:
            if part == root:
                break
            if part.is_symlink():
                fail(f'Unsafe symlink in workflow path: {part}')
            if part != path and part.exists() and not part.is_dir():
                fail(f'Parent is not a directory: {part}')


def candidates(root):
    lines = ['# Detected validation candidates', '',
             'Suggestions only: inspect command definitions and environment before running.',
             'Nothing below has been executed or established as a passing check.',
             'Configure `.ai/validate` explicitly; include all applicable check categories.', '']
    package = root / 'package.json'
    if package.is_file():
        manager = ('pnpm' if (root / 'pnpm-lock.yaml').exists() else
                   'bun' if any((root / x).exists() for x in ('bun.lock', 'bun.lockb')) else
                   'yarn' if (root / 'yarn.lock').exists() else 'npm')
        try:
            scripts = json.loads(package.read_text()).get('scripts', {})
            lines += [f'## Node ({manager})', '']
            for name, command in sorted(scripts.items()):
                if re.search(r'format|lint|type|check|test|build', name, re.I):
                    lines += [f'- `{manager} run {name}` — defined as `{command}`']
            lines += ['', 'Prefer non-writing format checks and non-watch test commands.', '']
        except (ValueError, AttributeError, TypeError):
            lines += ['package.json could not be parsed; inspect it manually.', '']
    if any((root / p).exists() for p in ('pyproject.toml', 'pytest.ini', 'setup.cfg', 'requirements.txt')):
        lines += ['## Python', '', 'Inspect configured environments/tools in pyproject.toml, setup.cfg, and CI.',
                  'Possible checks ONLY IF configured: `python -m pytest`, `ruff check .`,',
                  '`ruff format --check .`, `mypy .`. Do not assume these tools/tests exist.', '']
    if (root / 'Cargo.toml').exists():
        lines += ['## Rust', '', '- `cargo fmt --check`', '- `cargo clippy --all-targets -- -D warnings`',
                  '- `cargo test`', '- `cargo build`', 'Inspect features/workspaces/integration dependencies first.', '']
    if (root / 'go.mod').exists():
        lines += ['## Go', '', '- `go vet ./...`', '- `go test ./...`', '- `go build ./...`',
                  'For formatting, check gofmt output without modifying files.', '']
    for path in ('Makefile', 'justfile', 'scripts/ai-check', '.github/workflows'):
        if (root / path).exists():
            lines += [f'- Inspect existing `{path}` for the authoritative validation commands.']
    return '\n'.join(lines) + '\n'


STAMP_FILE = '.ai/toolkit-version'
TOOLKIT_GROUPS = (('runtime', '.ai/bin/'), ('prompts', '.ai/prompts/'))


def file_sha(data):
    return hashlib.sha256(data).hexdigest()


def toolkit_owned(relative):
    return any(relative.startswith(prefix) for _, prefix in TOOLKIT_GROUPS)


def read_stamp(root):
    """Return (stamp, problem). A missing or malformed stamp is a legacy install."""
    path = root / STAMP_FILE
    if not path.exists():
        return {'files': {}, 'templates': {}}, 'missing'
    try:
        data = json.loads(path.read_text())
        files, templates = data.get('files', {}), data.get('templates', {})
        if not isinstance(files, dict) or not isinstance(templates, dict) or not all(
                isinstance(v, str) for v in [*files.values(), *templates.values()]):
            raise ValueError('bad shape')
        return {'commit': data.get('toolkit_commit', 'unknown'), 'files': files, 'templates': templates}, None
    except (ValueError, AttributeError, OSError):
        return {'files': {}, 'templates': {}}, 'malformed'


def stamp_text(toolkit, stamp):
    try:
        commit = git('rev-parse', 'HEAD', cwd=toolkit).decode().strip() or 'unknown'
    except (subprocess.CalledProcessError, OSError):
        commit = 'unknown'
    return json.dumps({'toolkit_commit': commit, 'files': dict(sorted(stamp['files'].items())),
                       'templates': dict(sorted(stamp['templates'].items()))}, indent=2) + '\n'


def write_stamp(root, toolkit, stamp):
    text = stamp_text(toolkit, stamp)
    path = root / STAMP_FILE
    if not path.exists() or path.read_text() != text:
        atomic(path, text)


def install_bytes(target, data, mode):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
        temp = Path(file.name)
        file.write(data)
    try:
        temp.chmod(mode)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def activate(root, files):
    """Install every (relative, data, mode) or none of them.

    Each new file is staged next to its target before anything is replaced, then renamed into
    place. On any failure the replaced files get their previous bytes and mode back, created
    files and directories are removed, and the error is raised with any rollback problems."""
    previous, staged, done, made = {}, {}, [], []
    try:
        for relative, data, mode in files:
            target = root / relative
            previous[relative] = ((target.read_bytes(), target.stat().st_mode & 0o7777)
                                  if target.exists() else None)
            missing = [p for p in [target.parent, *target.parent.parents] if not p.exists()]
            target.parent.mkdir(parents=True, exist_ok=True)
            made += missing  # deepest first
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.upgrade-', delete=False) as file:
                staged[relative] = Path(file.name)
                file.write(data)
            staged[relative].chmod(mode)
        for relative, _, _ in files:
            os.replace(staged[relative], root / relative)
            del staged[relative]
            done.append(relative)
    except Exception as error:
        problems = []
        for relative in reversed(done):
            try:
                if previous[relative] is None:
                    (root / relative).unlink()
                else:
                    install_bytes(root / relative, *previous[relative])
            except OSError as undo:
                problems.append(f'{relative}: {undo}')
        for temp in staged.values():
            temp.unlink(missing_ok=True)
        for directory in sorted(made, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError as undo:
                problems.append(f'{directory.relative_to(root)}: {undo}')
        if problems:
            fail(f'Upgrade failed ({error}) and ROLLBACK FAILED, the install may be mixed: '
                 + '; '.join(problems))
        fail(f'Upgrade failed ({error}); every file was restored and {STAMP_FILE} is unchanged.')


def file_mode(relative):
    return 0o755 if relative.startswith('.ai/bin/') or relative in ('.ai/validate', '.ai/ci-setup') else 0o644


def upgrade(root, toolkit, copies, apply, force):
    if not (root / '.ai').is_dir():
        fail('No .ai directory: run setup-project (without --upgrade) first.')
    destinations = [*copies, STAMP_FILE]
    safe_paths(root, destinations)
    for relative in copies:
        if (root / relative).exists() and not (root / relative).is_file():
            fail(f'Expected a regular file: {relative}')
    stamp, problem = read_stamp(root)
    if problem:
        print(f'WARNING: {STAMP_FILE} is {problem} (legacy install): every differing toolkit-owned '
              'file counts as locally edited, so --force is needed to replace it.')
    plan = []  # (action, relative, group)
    baselines = {}
    for group, prefix in TOOLKIT_GROUPS:
        for relative in (r for r in copies if r.startswith(prefix)):
            new = file_sha(copies[relative].read_bytes())
            target = root / relative
            if not target.exists():
                plan.append(('CREATE', relative, group))
            elif file_sha(target.read_bytes()) == new:
                baselines[relative] = new
                plan.append(('OK', relative, group))
            elif stamp['files'].get(relative) == file_sha(target.read_bytes()):
                plan.append(('REPLACE', relative, group))
            else:
                plan.append(('EDITED', relative, group))
    for action, relative, _ in plan:
        if action != 'OK':
            print({'EDITED': 'EDITED (locally changed; needs --force) '}.get(action, action + ' ') + relative)
    for relative, source in copies.items():
        if toolkit_owned(relative):
            continue
        target = root / relative
        new = file_sha(source.read_bytes())
        if not target.exists():
            print(f'ADVICE {relative} is missing: run setup-project (without --upgrade) to create it')
        elif file_sha(target.read_bytes()) != new and stamp['templates'].get(relative) != new:
            print(f'ADVICE {relative} is project-owned and differs from the current template: '
                  f'compare with {source} and merge by hand')
    edited = [relative for action, relative, _ in plan if action == 'EDITED']
    changes = [(a, r) for a, r, _ in plan if a in ('CREATE', 'REPLACE') or (a == 'EDITED' and force)]
    if edited and not force:
        print('Refusing to upgrade: these toolkit files were edited locally (or have no baseline):')
        for relative in edited:
            print(f'  - {relative}')
        print('Reconcile them (or rerun with --force to overwrite them). Nothing was changed.')
        if apply:
            raise SystemExit(1)
        return
    if not apply:
        print(f'Plan only: {len(changes)} file(s) would change. Rerun with --upgrade --apply to apply.')
        return
    files = []
    for relative, source in copies.items():
        if toolkit_owned(relative) and any(r == relative for _, r in changes):
            files.append((relative, source.read_bytes(), file_mode(relative)))
            baselines[relative] = file_sha(files[-1][1])
    stamp['files'].update(baselines)
    text = stamp_text(toolkit, stamp)
    if not (root / STAMP_FILE).exists() or (root / STAMP_FILE).read_text() != text:
        files.append((STAMP_FILE, text.encode(), 0o644))
    activate(root, files)  # all or nothing, the stamp last
    print(f'Upgraded {len(changes)} file(s); {STAMP_FILE} updated.')
    if any(r.startswith('.ai/bin/') for _, r in changes):
        print('Reinstall the watchdog timer so it uses the new scripts: '
              '.ai/bin/ai-watchdog --install-timer --diagnose --recover')


def setup(arguments):
    parser = argparse.ArgumentParser(description='Copy templates without overwriting existing files.')
    parser.add_argument('project', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--upgrade', action='store_true',
                        help='plan an upgrade of toolkit-owned files (.ai/bin, .ai/prompts); changes nothing')
    parser.add_argument('--apply', action='store_true', help='with --upgrade: apply the plan')
    parser.add_argument('--force', action='store_true', help='with --upgrade --apply: overwrite locally edited files')
    parser.add_argument('--watchdog', action='store_true',
                        help='after installing, install the watchdog timer for this checkout')
    args = parser.parse_args(arguments)
    if (args.apply or args.force) and not args.upgrade:
        fail('--apply and --force only make sense with --upgrade.')
    if args.watchdog and (args.dry_run or args.upgrade):
        fail('--watchdog cannot be combined with --dry-run or --upgrade.')
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        fail('Target directory must exist. Create it and run git init first.')
    try:
        repo = Path(git('rev-parse', '--show-toplevel', cwd=root).decode().strip()).resolve()
    except subprocess.CalledProcessError:
        fail('Target must be a Git repository. Run git init there first.')
    if repo != root:
        fail('Target must be the repository root, not a subdirectory.')
    toolkit = Path(__file__).resolve().parents[2]
    template_root = toolkit / 'templates'
    if not template_root.is_dir():
        fail('Use setup-project from the toolkit checkout, not a target project.')
    copies = {str(p.relative_to(template_root)): p for p in sorted(template_root.rglob('*')) if p.is_file()}
    for name in ('ai-run', 'ai-pipeline', 'ai-check', 'ai-status', 'ai-review', 'ai-watchdog', 'ai-recover', 'ai-task',
                 'ai-dashboard', 'ai-plan', 'lib/common.sh', 'lib/workflow.py', 'lib/watchdog.py', 'lib/dashboard.py'):
        copies[f'.ai/bin/{name}'] = toolkit / 'scripts' / name
    if args.upgrade:
        return upgrade(root, toolkit, copies, args.apply and not args.dry_run, args.force)
    generated = '.ai/validation-candidates.md'
    destinations = list(copies) + [generated, '.gitignore', '.ai/local', STAMP_FILE]
    safe_paths(root, destinations)
    for relative in copies:
        if (root / relative).exists() and not (root / relative).is_file():
            fail(f'Expected a regular file: {relative}')
    for relative in (generated, '.gitignore'):
        if (root / relative).exists() and not (root / relative).is_file():
            fail(f'Expected a regular file: {relative}')
    ignores = ['/.ai/local/', '/.claude/settings.local.json']
    ignore_file = root / '.gitignore'
    existing = ignore_file.read_text() if ignore_file.exists() else ''
    missing = [line for line in ignores if line not in existing.splitlines()]
    for relative in [*copies, generated]:
        print(('KEEP   ' if (root / relative).exists() else 'CREATE ') + relative)
    instruction_sections = {
        'CLAUDE.md': ('## Autonomous implementation loop', '## Deterministic validation',
                      '## Persistence and recovery', '## Authority and boundaries'),
        'AGENTS.md': ('# Codex — independent reviewer by default', '.ai/reviews/current.md',
                      'BLOCKER', 'MAJOR', 'MINOR'),
    }
    for relative, sections in instruction_sections.items():
        target = root / relative
        if target.exists():
            text = target.read_text()
            absent = [section for section in sections if section not in text]
            if absent:
                print(f'WARNING: KEEP {relative} lacks toolkit instruction sections/markers:')
                for section in absent:
                    print(f'  - {section}')
                print(f'  Workflow rules are NOT installed in {relative}. Merge guidance from')
                print(f'  {template_root / relative} before planning or unattended implementation.')
                print('  Section detection is a heuristic; review merged instructions for conflicts.')
    if missing:
        print(('APPEND ' if ignore_file.exists() else 'CREATE ') + '.gitignore (local logs/settings ignored)')
    if args.dry_run:
        return
    created = False
    stamp, _ = read_stamp(root)  # baselines are only ever written for files this run creates
    for relative, source in copies.items():
        target = root / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects existing files even if setup is repeated.
        with target.open('xb') as file:
            file.write(source.read_bytes())
        stamp['files' if toolkit_owned(relative) else 'templates'][relative] = file_sha(source.read_bytes())
        created = True
        target.chmod(0o755 if relative.startswith('.ai/bin/') or relative in ('.ai/validate', '.ai/ci-setup') else 0o644)
        if relative == '.ai/state.md':
            text = target.read_text().replace('Project: unset', f'Project: {root.name}')
            try:
                branch = git('symbolic-ref', '--short', 'HEAD', cwd=root).decode().strip()
            except subprocess.CalledProcessError:
                branch = 'detached HEAD (create a feature branch before implementation)'
            text = text.replace('Branch: unset', f'Branch: {branch}').replace('Last updated: unset', f'Last updated: {now()}')
            atomic(target, text)
    target = root / generated
    if not target.exists():
        with target.open('x') as file:
            file.write(candidates(root))
    if missing:
        with ignore_file.open('a') as file:
            file.write(('\n' if existing and not existing.endswith('\n') else '') + '\n'.join(missing) + '\n')
    if created or not (root / STAMP_FILE).exists():  # a no-op repeat must not move the recorded commit
        write_stamp(root, toolkit, stamp)
    print('Installed. Existing files were preserved: reconcile KEEP entries manually before running.')
    if not args.watchdog:
        print('Next: install the watchdog timer: .ai/bin/ai-watchdog --install-timer --diagnose --recover')
        return
    result = subprocess.run([str(root / '.ai/bin/ai-watchdog'), str(root), '--install-timer',
                             '--diagnose', '--recover'],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True)
    print(result.stdout, end='')
    if result.returncode:
        fail('The watchdog timer was not installed (files were installed; the timer was not): '
             + (result.stderr.strip() or result.stdout.strip() or f'exit {result.returncode}'))


def task_blocks(text):
    blocks = []
    fence = None
    current = None
    for line in text.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            if current is not None:
                current['raw'].append(line)
            continue
        if fence:
            if current is not None:
                current['raw'].append(line)
            continue
        heading = re.match(r'^##\s+(T\d{3,})\s+[—-]\s+(.+?)\s*$', line)
        if heading:
            # raw: every source line of the block, fenced lines included (plan-keeps-done).
            current = {'id': heading.group(1), 'title': heading.group(2), 'lines': [],
                       'heading': line, 'raw': []}
            blocks.append(current)
        elif re.match(r'^##\s+T\d', line):
            fail(f'Malformed task heading: {line}')
        elif line.startswith('## '):
            current = None
        elif current is not None:
            current['lines'].append(line)
            current['raw'].append(line)
    return blocks


REQUIRED_SECTIONS = ('Goal', 'Implementation notes', 'Likely affected modules',
                     'Acceptance criteria', 'Validation', 'Result / notes')
# The content-free sections `tasks fill-sections` may add, with the body inserted under the heading.
FILLABLE_SECTIONS = {'Likely affected modules': ['(not listed)\n'], 'Result / notes': []}


STATUSES = ('TODO', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'SKIPPED')
# Finished for the queue: satisfies dependencies and counts toward `complete` (SKIPPED only with
# its host authorization, which tasks() checks).
FINISHED = ('DONE', 'SKIPPED')
SKIPPED_LINE = re.compile(r'Skipped \(\d{4}-\d{2}-\d{2}, ai-task skip\): \S.*')


def skipped_lines(task):
    """The task's `Skipped (…)` lines (fenced lines don't count; task_blocks skips them)."""
    return [line for line in task['lines'] if line.startswith('Skipped (')]


def skip_key(task, line):
    """sha256 of the repository's sorted root commits, the task's heading line and its Skipped line:
    host-wide per repository (every checkout and branch), bound to the heading and exact reason."""
    try:
        roots = sorted(git('rev-list', '--max-parents=0', 'HEAD').decode().split())
    except subprocess.CalledProcessError:
        fail('Skip authorizations need a Git repository with a commit.')
    return hashlib.sha256('\0'.join([' '.join(roots), task['heading'], line]).encode()).hexdigest()


def skips_dir():
    """Host-only store of skip authorizations (agent sessions get no write access there)."""
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    return check_state_root(root) / 'skips'


def skip_authorized(task):
    """True when the SKIPPED task has exactly one valid Skipped line and the host authorized it."""
    lines = skipped_lines(task)
    if len(lines) != 1 or not SKIPPED_LINE.fullmatch(lines[0]):
        return False
    return (skips_dir() / skip_key(task, lines[0])).is_file()


def tasks(text=None, check_skips=True):
    """Parse and validate the queue; check_skips=False turns off only the SKIPPED authorization check."""
    blocks = task_blocks(Path('.ai/tasks.md').read_text() if text is None else text)
    ids = [task['id'] for task in blocks]
    if len(ids) != len(set(ids)):
        fail('Duplicate task IDs.')
    required = REQUIRED_SECTIONS
    for task in blocks:
        for field in ('Status', 'Dependencies'):
            values = [line.split(':', 1)[1].strip() for line in task['lines'] if line.startswith(field + ':')]
            if len(values) != 1:
                fail(f"{task['id']}: expected exactly one {field}: line")
            task[field.lower()] = values[0]
        models = [line.split(':', 1)[1].strip() for line in task['lines'] if line.startswith('Model:')]
        if len(models) > 1:
            fail(f"{task['id']}: at most one Model: line")
        task['model'] = models[0] if models else ''
        if task['model'] and not re.fullmatch(r'[A-Za-z0-9._:\[\]-]{1,64}', task['model']):
            fail(f"{task['id']}: invalid Model: value")
        if task['status'] not in STATUSES:
            fail(f"{task['id']}: invalid status")
        value = task['dependencies']
        task['deps'] = [] if value == 'none' else [x.strip() for x in value.split(',')]
        for dep in task['deps']:
            if dep not in ids or ids.index(dep) >= ids.index(task['id']):
                fail(f"{task['id']}: dependencies must exist earlier in the queue: {dep}")
        if len(task['deps']) != len(set(task['deps'])):
            fail(f"{task['id']}: duplicate dependencies")
        for section in required:
            if f'### {section}' not in task['lines']:
                fail(f"{task['id']}: missing ### {section}")
    by_id = {task['id']: task for task in blocks}
    for task in blocks:
        if task['status'] in ('DONE', 'IN_PROGRESS') and any(by_id[d]['status'] not in FINISHED for d in task['deps']):
            fail(f"{task['id']}: {task['status']} requires DONE dependencies")
    if sum(task['status'] == 'IN_PROGRESS' for task in blocks) > 1:
        fail('At most one task can be IN_PROGRESS.')
    if check_skips:
        for task in blocks:
            if task['status'] == 'SKIPPED' and not skip_authorized(task):
                fail(f"{task['id']}: SKIPPED without a host skip record (use ai-task skip, or "
                     f"ai-task skip {task['id']} --reauthorize on another host)")
    return blocks


def queue_segments(text):
    """Split the queue into ('pre'|'task'|'section', key, lines) segments, same heading and fence rules as task_blocks."""
    segments = [('pre', '', [])]
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
        elif not fence:
            heading = re.match(r'^##\s+(T\d{3,})\s+[—-]\s+(.+?)\s*$', line)
            if heading:
                segments.append(('task', heading.group(1), []))
            elif re.match(r'^##\s', line):
                segments.append(('section', line.strip(), []))
        segments[-1][2].append(line)
    return segments


def queue_order(text):
    """(blocks, ids, order, deps) of TEXT: the stable dependency-first order `tasks reorder` writes,
    deps per ID in file order. Fails on duplicates, prose or unknown IDs and cycles."""
    blocks = task_blocks(text)
    ids = [task['id'] for task in blocks]
    if len(ids) != len(set(ids)):
        fail('Duplicate task IDs.')
    deps = {}
    for task in blocks:
        values = [line.split(':', 1)[1].strip() for line in task['lines'] if line.startswith('Dependencies:')]
        if len(values) != 1:
            fail(f"{task['id']}: expected exactly one Dependencies: line")
        value = values[0]
        if value != 'none' and not re.fullmatch(r'T\d{3,}(\s*,\s*T\d{3,})*', value):
            fail(f'{task["id"]}: Dependencies: must be "none" or task IDs separated by commas, found "{value}"')
        listed = [] if value == 'none' else [x.strip() for x in value.split(',')]
        for dep in listed:
            if dep not in ids:
                fail(f"{task['id']}: dependency {dep} is not a task in the queue")
        if len(listed) != len(set(listed)):
            fail(f"{task['id']}: duplicate dependencies")
        deps[task['id']] = sorted(listed, key=ids.index)
    order, state, stack = [], {}, []

    def visit(task_id):
        if state.get(task_id) == 'done':
            return
        if state.get(task_id) == 'active':
            cycle = stack[stack.index(task_id):] + [task_id]
            fail('dependency cycle: ' + ' -> '.join(cycle))
        state[task_id] = 'active'
        stack.append(task_id)
        for dep in deps[task_id]:
            visit(dep)
        stack.pop()
        state[task_id] = 'done'
        order.append(task_id)

    for task_id in ids:
        visit(task_id)
    return blocks, ids, order, deps


def reordered_text(text, order):
    """TEXT with its task blocks in ORDER; the preamble and the trailer are kept as they are."""
    segments = queue_segments(text)
    positions = [index for index, segment in enumerate(segments) if segment[0] == 'task']
    first, last = positions[0], positions[-1]
    for segment in segments[first:last]:
        if segment[0] == 'section':
            fail(f'cannot reorder: section "{segment[1]}" sits between tasks')
    by_id = {key: lines for kind, key, lines in segments if kind == 'task'}
    # Everything before the first task (including ordinary ## sections) is the preamble, kept as is.
    out = [line for segment in segments[:first] for line in segment[2]]
    for position, task_id in enumerate(order):
        lines = list(by_id[task_id])
        if position < len(order) - 1 or last < len(segments) - 1:
            if not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            if lines[-1].strip():
                lines.append('\n')
        out.extend(lines)
    for segment in segments[last + 1:]:
        out.extend(segment[2])
    return ''.join(out)


def tasks_reorder():
    path = Path('.ai/tasks.md')
    text = path.read_text()
    _, ids, order, _ = queue_order(text)
    if order == ids:
        return
    new = reordered_text(text, order)
    mode = stat.S_IMODE(path.stat().st_mode)
    atomic(path, new)
    path.chmod(mode)
    print('Task queue reordered (dependencies first): ' + ' '.join(order))


def section_positions(lines):
    """Line index of each exact `### <required section>` heading outside code fences."""
    found, fence = {}, None
    for index, line in enumerate(lines):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
        elif not fence and line.rstrip('\n') in {f'### {name}' for name in REQUIRED_SECTIONS}:
            found.setdefault(line.rstrip('\n')[4:], index)
    return found, fence


def fill_task_sections(lines):
    """Return (new lines, names added) for one TODO task block; other blocks are the caller's to skip."""
    lines, added = list(lines), []
    for name, body in FILLABLE_SECTIONS.items():
        found, fence = section_positions(lines)
        if name in found or fence:
            continue
        later = [found[n] for n in REQUIRED_SECTIONS[REQUIRED_SECTIONS.index(name) + 1:] if n in found]
        if later:
            at = min(later)
            new = [f'### {name}\n', *body, '\n']
            if lines[at - 1].strip():
                new.insert(0, '\n')
        else:
            at = len(lines)
            while at > 0 and not lines[at - 1].strip():
                at -= 1
            if lines[at - 1] and not lines[at - 1].endswith('\n'):
                lines[at - 1] += '\n'
            new = ['\n', f'### {name}\n', *body]
        lines[at:at] = new
        added.append(name)
    return lines, added


def task_status(block):
    """The block's only `Status:` value, or None (fenced lines don't count; task_blocks skips them)."""
    statuses = [line for line in block['lines'] if line.startswith('Status:')]
    return statuses[0].split(':', 1)[1].strip() if len(statuses) == 1 else None


def filled_text(text):
    """(TEXT with the missing fillable sections of TODO tasks added, [(ID, names added)])."""
    out, report = [], []
    for kind, key, lines in queue_segments(text):
        if kind == 'task':
            block = next((b for b in task_blocks(''.join(lines)) if b['id'] == key), None)
            if block and task_status(block) == 'TODO':
                lines, added = fill_task_sections(lines)
                if added:
                    report.append((key, added))
        out.extend(lines)
    return ''.join(out), report


def tasks_fill_sections():
    path = Path('.ai/tasks.md')
    new, report = filled_text(path.read_text())
    if not report:
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    atomic(path, new)
    path.chmod(mode)
    print('Task queue: added missing sections: '
          + ', '.join(f"{key} ({', '.join(added)})" for key, added in report))


PREFLIGHT_OVERLAP_LINES = 20


def likely_paths(block):
    """Path-like tokens of `### Likely affected modules` (outside fences), in first-seen order."""
    lines, inside, fence = [], False, None
    for line in block['raw']:
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        if line.startswith('### '):
            inside = line.rstrip() == '### Likely affected modules'
        elif inside:
            lines.append(line)
    paths = []
    for token in re.split(r'[\s,]+', ' '.join(lines)):
        token = token.replace('`', '').rstrip(',.;:')
        if ('/' in token or '.' in token) and token not in paths:
            paths.append(token)
    return paths


def tasks_preflight(arguments):
    """tasks preflight [--dry-run]: repair a queue whose only faults are the order (only TODO
    tasks move) and empty fillable sections of TODO tasks, print one line per change and the
    TODO task pairs sharing a likely-affected path. A queue the repair can't make valid fails with
    the `tasks reorder`/`tasks()` message and nothing is written."""
    if arguments not in ([], ['--dry-run']):
        fail('Usage: tasks preflight [--dry-run]')
    dry_run = bool(arguments)
    path = Path('.ai/tasks.md')
    text = path.read_text()
    blocks, ids, order, deps = queue_order(text)
    late = {task_id: [dep for dep in deps[task_id] if ids.index(dep) >= ids.index(task_id)]
            for task_id in ids}
    changes, new = [], text
    if order != ids:
        status = {block['id']: task_status(block) for block in blocks}
        moved = [task_id for index, task_id in enumerate(ids) if order[index] != task_id]
        stuck = [task_id for task_id in moved if status[task_id] != 'TODO']
        if stuck:
            # The tasks() wording: a stuck task's own late dependency, else the queue's first one.
            first = next((t for t in stuck if late[t]), None) or next(t for t in ids if late[t])
            fail(f'{first}: dependencies must exist earlier in the queue: {late[first][0]}')
        new = reordered_text(text, order)
        changes += [f"queue-order {task_id} placed after {', '.join(late[task_id])}"
                    for task_id in order if late[task_id]]
        # Prerequisites and intervening tasks move too; the host claims them like the rest.
        changes += [f'queue-moved {task_id}' for task_id in order
                    if task_id in moved and not late[task_id]]
    new, filled = filled_text(new)
    changes += [f"task-sections {key} added {', '.join(added)}" for key, added in filled]
    final = tasks(new)
    todo = [block for block in final if block['status'] == 'TODO']
    overlaps = []
    for index, first in enumerate(todo):
        first_paths = likely_paths(first)
        for second in todo[index + 1:]:
            shared = [p for p in first_paths if p in likely_paths(second)]
            if shared:
                overlaps.append(f"overlap {first['id']} {second['id']} {', '.join(shared)}")
    if len(overlaps) > PREFLIGHT_OVERLAP_LINES:
        overlaps = (overlaps[:PREFLIGHT_OVERLAP_LINES]
                    + [f'overlap … {len(overlaps) - PREFLIGHT_OVERLAP_LINES} more'])
    if not dry_run and new != text:
        mode = stat.S_IMODE(path.stat().st_mode)
        atomic(path, new)
        path.chmod(mode)
    # The overlap report is advisory and not a queue change, so a dry run refreshes it too.
    local_fd = local_dir_fd(os.getcwd())
    if local_fd is not None:
        try:
            write_record(local_fd, 'preflight.md', ''.join(line + '\n' for line in overlaps))
        except (RecordError, OSError):
            pass  # An unsafe .ai/local skips the report quietly.
        finally:
            close_fds(local_fd)
    for line in changes + overlaps:
        print(line)


def task_command(arguments):
    if arguments[0] == 'reorder':
        tasks_reorder()
        return
    if arguments[0] == 'fill-sections':
        tasks_fill_sections()
        return
    if arguments[0] == 'preflight':
        tasks_preflight(arguments[1:])
        return
    blocks = tasks()
    action = arguments[0]
    if action == 'check':
        if not blocks:
            fail('No real tasks. Plan before starting implementation.')
    elif action == 'complete':
        if not blocks or any(task['status'] not in FINISHED for task in blocks):
            fail('Task queue is not complete.')
    elif action == 'untouched':
        # No task finished yet: the plan gate still applies (BLOCKED/IN_PROGRESS don't lift it).
        if not blocks or any(task['status'] == 'DONE' for task in blocks):
            fail('A task is already DONE (or there are no tasks).')
    elif action == 'newly-done':
        # Tasks DONE in the working queue but not (or absent) at REV, in file order.
        rev = arguments[1] if len(arguments) == 2 else ''
        if not rev or rev.startswith('-'):
            fail('Usage: tasks newly-done REV')
        try:
            commit = git('rev-parse', '--verify', '-q', f'{rev}^{{commit}}').decode().strip()
        except subprocess.CalledProcessError:
            fail(f'Unknown revision: {rev}')
        try:
            before = git('show', f'{commit}:.ai/tasks.md').decode()
        except subprocess.CalledProcessError:
            before = ''  # no queue at REV: every DONE task is new
        done = {task['id'] for task in tasks(before, check_skips=False) if task['status'] == 'DONE'}
        for task in blocks:
            if task['status'] == 'DONE' and task['id'] not in done:
                print(task['id'])
    elif action == 'blocked':
        for task in blocks:
            if task['status'] == 'BLOCKED':
                print(task['id'])
    elif action == 'next':
        by_id = {task['id']: task for task in blocks}
        eligible = [task for task in blocks if task['status'] in ('TODO', 'IN_PROGRESS')
                    and all(by_id[d]['status'] in FINISHED for d in task['deps'])]
        active = next((task for task in eligible if task['status'] == 'IN_PROGRESS'), None)
        print((active or (eligible[0] if eligible else {'id': 'none'}))['id'])
    elif action == 'model':
        task = next((task for task in blocks if task['id'] == arguments[1]), None)
        if task is None:
            fail(f'Unknown task: {arguments[1]}')
        print(task['model'])
    elif action == 'count':
        print(len(blocks))
    elif action == 'counts':
        # "<done> <total>": the same counting as `progress`, for the dashboard's Build detail.
        print(sum(t['status'] == 'DONE' for t in blocks), len(blocks))
    elif action == 'progress':
        # One line for notifications: "<id> <title> (<done>/<total> done)".
        task = next((task for task in blocks if task['id'] == arguments[1]), None)
        if task is None:
            fail(f'Unknown task: {arguments[1]}')
        done = sum(t['status'] == 'DONE' for t in blocks)
        print(f"{task['id']} {task['title'][:80]} ({done}/{len(blocks)} done)")
    elif action in ('status', 'show', 'set', 'skip'):
        task = next((task for task in blocks if task['id'] == arguments[1]), None)
        if task is None:
            fail(f'Unknown task: {arguments[1]}')
        if action == 'status':
            print(task['status'])
        elif action == 'show':
            print(f"{task['id']} {task['title']}\nStatus: {task['status']}\n"
                  f"Model: {task['model'] or 'default'}\nDependencies: {task['dependencies']}")
        elif action == 'skip':
            if len(arguments) != 3:
                fail('Usage: tasks skip ID REASON')
            tasks_skip(blocks, task, arguments[2])
        else:
            if arguments[2] == 'SKIPPED':
                fail('Invalid task status: use ai-task skip to skip a task.')
            if arguments[2] not in STATUSES:
                fail('Invalid task status.')
            path = Path('.ai/tasks.md')
            lines = path.read_text().splitlines(keepends=True)
            index, _ = task_line_positions(lines, task['id'])
            if index is not None:
                lines[index] = f'Status: {arguments[2]}\n'
            atomic(path, ''.join(lines))


def task_line_positions(lines, task_id):
    """(index of the task's Status: line, index of its `### Result / notes` heading), each None
    when absent; the real heading is found by exact ID outside code fences (not a fenced example)."""
    fence = None
    active = False
    status = notes = None
    for index, line in enumerate(lines):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        if line.startswith('## '):
            if active:
                break
            active = bool(re.match(r'^##\s+' + re.escape(task_id) + r'\s+[—-]\s+', line))
        elif active and line.startswith('Status:') and status is None:
            status = index
        elif active and line.rstrip('\r\n') == '### Result / notes' and notes is None:
            notes = index
    return status, notes


def skip_reason_error(reason):
    """Why REASON can't be a Skipped line's reason, or '' (one line, 1-500 characters, no control,
    format or line separator characters, no backticks)."""
    if not 1 <= len(reason) <= 500:
        return 'the reason must be 1-500 characters'
    if reason != reason.strip():
        return 'the reason must not start or end with whitespace'
    if '`' in reason or any(unicodedata.category(c) in ('Cc', 'Cf', 'Zl', 'Zp') for c in reason):
        return 'the reason must be one line without control characters or backticks'
    return ''


def tasks_skip(blocks, task, reason):
    """tasks skip ID REASON: TODO/BLOCKED → SKIPPED with a `Skipped (DATE, ai-task skip): REASON`
    line under `### Result / notes`. The host authorization is created first, so a failed write
    leaves only an unused authorization, never an unauthorized SKIPPED."""
    if task['status'] not in ('TODO', 'BLOCKED'):
        fail(f"{task['id']} is {task['status']}; only a TODO or BLOCKED task can be skipped.")
    dependents = [other['id'] for other in blocks
                  if task['id'] in other['deps'] and other['status'] not in FINISHED]
    if dependents:
        fail(f"{task['id']} cannot be skipped: unfinished tasks depend on it: {', '.join(dependents)}")
    error = skip_reason_error(reason)
    if error:
        fail(f'Cannot skip {task["id"]}: {error}.')
    if skipped_lines(task):
        fail(f"{task['id']} already has a Skipped line; remove it first.")
    path = Path('.ai/tasks.md')
    lines = path.read_text().splitlines(keepends=True)
    status, notes = task_line_positions(lines, task['id'])
    if status is None or notes is None:
        fail(f"{task['id']}: Status: line or ### Result / notes not found.")
    skipped = f"Skipped ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}, ai-task skip): {reason}"
    lines[status] = 'Status: SKIPPED\n'
    # Append to the end of the Result / notes section: after its last non-blank line.
    end = notes + 1
    while end < len(lines) and not re.match(r'^#{2,3}\s', lines[end]):
        end += 1
    while end > notes + 1 and not lines[end - 1].strip():
        end -= 1
    if not lines[end - 1].endswith('\n'):
        lines[end - 1] += '\n'
    lines.insert(end, skipped + '\n')
    new = ''.join(lines)
    after = next(t for t in tasks(new, check_skips=False) if t['id'] == task['id'])
    if skipped_lines(after) != [skipped]:
        fail(f"{task['id']}: the Skipped line could not be placed in the task.")
    directory = skips_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.close(os.open(directory / skip_key(after, skipped), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        pass
    tasks(new)  # the whole queue, with the new authorization in place
    mode = stat.S_IMODE(path.stat().st_mode)
    atomic(path, new)
    path.chmod(mode)
    print(f"{task['id']} SKIPPED: {reason}")


def fingerprint():
    """Hash project content, including untracked source; omit workflow metadata.

    Validation evidence stays usable after state/log/review updates and commits.
    Spec/plan/tasks, source, tests, instructions, tools, and validation ARE hashed.
    """
    ignored = {'.ai/state.md', '.ai/handoff.md', '.ai/run-log.md'}
    names = set(git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0'))
    digest = hashlib.sha256()
    for raw in sorted(names):
        if not raw:
            continue
        name = os.fsdecode(raw)
        if name in ignored or name.startswith(('.ai/local/', '.ai/reviews/')):
            continue
        path = Path(name)
        digest.update(raw + b'\0')
        if path.is_symlink():
            digest.update(b'link\0' + os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(b'file\0' + str(path.stat().st_mode & 0o777).encode() + b'\0')
            with path.open('rb') as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b''):
                    digest.update(chunk)
        elif path.is_dir():
            # Git submodules: use HEAD plus dirty/untracked state, never ignore them.
            digest.update(git('-C', name, 'rev-parse', 'HEAD'))
            status = git('-C', name, 'status', '--porcelain', '--untracked-files=all')
            if status:
                fail(f'Dirty submodule: {name}; checkpoint it before validation.')
        else:
            digest.update(b'missing\0')
        digest.update(b'\0')
    return digest.hexdigest()


def stamp(arguments):
    path = Path('.ai/local/validation.json')
    action = arguments[0]
    if action == 'invalidate':
        # Record the content that is about to be validated. Removes stale success.
        atomic(path, json.dumps({'result': 'RUNNING', 'started': now(), 'before': fingerprint()}) + '\n')
    elif action == 'record':
        before = json.loads(path.read_text())['before']
        after = fingerprint()
        result = int(arguments[1])
        data = {'result': 'PASS' if result == 0 and before == after else 'FAIL',
                'exit_code': result, 'timestamp': now(), 'fingerprint': after,
                'unchanged': before == after, 'head': git('rev-parse', 'HEAD').decode().strip(),
                'log': arguments[2]}
        atomic(path, json.dumps(data, indent=2) + '\n')
        if result == 0 and before != after:
            fail('Validation modified project content. Use non-writing checks and rerun.')
    elif action == 'verify':
        if not path.exists():
            fail('No validation evidence. Run .ai/bin/ai-check first.')
        data = json.loads(path.read_text())
        if data.get('result') != 'PASS' or data.get('fingerprint') != fingerprint():
            fail('Validation failed, interrupted, or stale. Run .ai/bin/ai-check.')
        print(f"Validation PASS: {data['timestamp']} (content unchanged since checks)")
    elif action == 'outcome':
        print(stamp_outcome())


STAMP_LIMIT = 64 * 1024


def stamp_outcome():
    """'WORD DIGEST' for what the last ai-check left in `.ai/local/validation.json`, read through
    the pinned `.ai/local` (never a symlink, never blocking on a FIFO). WORD: none (missing,
    unsafe, unreadable, too large or not a JSON object), running, pass, changed (FAIL with exit 0
    because the content changed) or fail. DIGEST: sha256 of the bytes read, or '-'. The runner
    compares it across a session to tell whether the session ran the gate (FL-32)."""
    try:
        dir_fd = local_dir_fd(checkout_root())
    except (OSError, subprocess.CalledProcessError):
        dir_fd = None
    if dir_fd is None:
        return 'none -'
    try:
        record = read_record(dir_fd, 'validation.json', STAMP_LIMIT + 1, raw=True)
    finally:
        os.close(dir_fd)
    if record is None or len(record[0]) > STAMP_LIMIT:
        return 'none -'
    content = record[0]
    digest = hashlib.sha256(content).hexdigest()
    try:
        data = json.loads(content)
    except (ValueError, RecursionError):
        return f'none {digest}'
    if not isinstance(data, dict):
        return f'none {digest}'
    result = data.get('result')
    if result == 'RUNNING':
        word = 'running'
    elif result == 'PASS':
        word = 'pass'
    elif result == 'FAIL' and type(data.get('exit_code')) is int and data['exit_code'] == 0 \
            and data.get('unchanged') is False:
        word = 'changed'
    else:
        word = 'fail'
    return f'{word} {digest}'


def update_state(phase, next_action):
    path = Path('.ai/state.md')
    blocks = tasks()
    done = [task['id'] for task in blocks if task['status'] == 'DONE']
    active = next((task['id'] for task in blocks if task['status'] == 'IN_PROGRESS'), 'none')
    validation = 'not run'
    evidence = Path('.ai/local/validation.json')
    if evidence.exists():
        data = json.loads(evidence.read_text())
        validation = f"{data['result']} at {data.get('timestamp', data.get('started', 'unknown'))}"
    values = {'Branch': git('symbolic-ref', '--short', 'HEAD').decode().strip(), 'Phase': phase,
              'Current task': active, 'Last completed task': done[-1] if done else 'none',
              'Tasks complete': str(len(done)), 'Tasks remaining': str(len(blocks) - len(done)),
              'Last validation': validation,
              'Blocked': 'yes' if phase == 'blocked' or any(t['status'] == 'BLOCKED' for t in blocks) else 'no',
              'Next action': next_action, 'Last updated': now()}
    text = path.read_text()
    for key, value in values.items():
        pattern = r'^' + re.escape(key) + r':.*$'
        if not re.search(pattern, text, flags=re.M):
            fail(f'State is missing {key}:')
        text = re.sub(pattern, lambda match: f'{key}: {value}', text, flags=re.M)
    atomic(path, text)


def status():
    text = Path('.ai/state.md').read_text()
    for field in ('Project', 'Phase', 'Current task', 'Blocked', 'Next action'):
        match = re.search(r'^' + field + r':\s*(.*)$', text, flags=re.M)
        print(f'{field}: {match.group(1) if match else "missing"}')
    try:
        branch = git('symbolic-ref', '--short', 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        branch = 'detached HEAD'
    print('Branch: ' + branch)
    blocks = tasks()
    print(f"Completed / total tasks: {sum(t['status'] == 'DONE' for t in blocks)} / {len(blocks)}")
    try:
        print('Last checkpoint: ' + git('log', '-1', '--format=%h %s').decode().strip())
    except subprocess.CalledProcessError:
        print('Last checkpoint: none (initial commit needed)')
    dirty = git('status', '--porcelain', '--untracked-files=all').decode().splitlines()
    print(f'Working tree: {len(dirty)} changed/untracked entries' if dirty else 'Working tree: clean')
    evidence = Path('.ai/local/validation.json')
    if evidence.exists():
        data = json.loads(evidence.read_text())
        stale = data.get('fingerprint') != fingerprint()
        print(f"Last validation: {data['result']} ({'stale/incomplete' if stale else 'current content'})")
    else:
        print('Last validation: not run')


def claude_result(path, check_only=False):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or data.get('type') != 'result' or data.get('is_error') is not False:
        fail('Missing/failed Claude result.')
    if data.get('subtype') != 'success':
        fail(f"Claude did not finish successfully: {data.get('subtype')}")
    denials = data.get('permission_denials') or []
    if denials and not check_only:
        # Denied attempts are reported, not fatal: the runner still requires a real
        # DONE/BLOCKED checkpoint, so a session that couldn't work around them stops anyway.
        with open('.ai/local/denials.log', 'a') as log:
            for denial in denials:
                command = json.dumps(denial.get('tool_input', {}))[:300]
                log.write(f"{now()} {denial.get('tool_name')} {command}\n")
        print(f'Note: {len(denials)} denied tool call(s) logged in .ai/local/denials.log', file=sys.stderr)


def claude_text(arguments):
    """Write the final text of a successful `claude -p --output-format json` run to OUT
    (--allow-empty: blank text writes an empty OUT, for the review format check to judge)."""
    allow_empty = '--allow-empty' in arguments
    source, target = [argument for argument in arguments if argument != '--allow-empty']
    claude_result(source, check_only=True)
    data = json.loads(Path(source).read_text())
    denials = data.get('permission_denials') or []
    if denials:
        # The reviewer's attempts at its boundary are the audit signal: keep them.
        with open('.ai/local/review-denials.log', 'a') as log:
            for denial in denials:
                log.write(f"{now()} {denial.get('tool_name')} {json.dumps(denial.get('tool_input', {}))[:300]}\n")
        print(f'Note: {len(denials)} denied reviewer tool call(s) logged in .ai/local/review-denials.log',
              file=sys.stderr)
    text = data.get('result')
    if not isinstance(text, str) or not (text.strip() or allow_empty):
        fail('Claude returned no text.')
    Path(target).write_text(text.strip() + '\n' if text.strip() else '')


def review_allowlist(arguments):
    """--allowedTools entries for the Claude reviewer, one per line: Read, Glob and Grep only.
    No shell and no write tool: every Bash allow/deny list tried before left a command-argument
    route to running code or writing files (runner options, git option abbreviations), so the
    host prepares the git context in .ai/local/review-context/ instead. The project's
    .ai/permissions.allow is deliberately not read."""
    print('\n'.join(('Read', 'Glob', 'Grep')))


SECRET_PATTERNS = ('.env*', '*.pem', '*.key', '*.p12', '*.pfx', '*.keystore', 'id_rsa*',
                   'id_ed25519*', 'id_ecdsa*', '*.kdbx', '*credentials*', '*secret*', '.npmrc', '.netrc')


def checkpoint_guard(arguments):
    """Run after an automatic checkpoint staged everything git doesn't ignore. Fails if a
    newly added file (added, copied or renamed into place) looks like a secret; otherwise
    prints the new files for the notification. Sessions start from a clean tree, so new
    files are that session's own output (Codex and the human review them before merge)."""
    import fnmatch
    staged = git('diff', '--cached', '--name-only', '-z', '--no-renames', '--diff-filter=A').split(b'\0')
    names = [os.fsdecode(raw) for raw in staged if raw]
    secrets = [name for name in names
               if any(fnmatch.fnmatch(Path(name).name.lower(), pattern) for pattern in SECRET_PATTERNS)]
    if secrets:
        fail('Secret-looking new files, not committed: ' + ', '.join(secrets[:10]))
    print(', '.join(names[:8]) + (f' (+{len(names) - 8} more)' if len(names) > 8 else ''))


def publish_review(arguments):
    source, head, base = arguments
    content = Path(source).read_text()
    error = review_format_error('code', content)
    if error:
        fail(f'{error.rstrip(".")}; prior review preserved. Inspect local report.')
    header = f'<!-- Host evidence: HEAD {head}; merge-base {base}; saved {now()}. -->\n\n' + \
        reviewed_by_line() + reviewer_label()
    atomic('.ai/reviews/current.md', header + content)
    bind_review(head, header + content)


COUNTS = re.compile(r'^Finding counts:\s*BLOCKER=(\d+)\s+MAJOR=(\d+)\s+MINOR=(\d+)\s*$', re.M)


FINDING_ID = re.compile(r'^(?:#{2,6}\s+|[-*]\s+(?:\*\*)?)\s*([A-Z][A-Z0-9]{0,4}-?\d+)\b', re.M)
NONE_TEXT = re.compile(r'^(?:none|no findings|n/?a)\b', re.I)


def reviewer_label():
    """Visible label for a review written by the Claude fallback (ai-review sets AI_REVIEW_BY
    and AI_REVIEW_LABEL); empty for Codex reviews, so their files are unchanged."""
    label = ' '.join(os.environ.get('AI_REVIEW_LABEL', '').split())
    return f'> **Reviewer: {label}**\n\n' if label else ''


def reviewed_by_line():
    """`Reviewed by: WHO` line for every published review (ai-review sets AI_REVIEW_WHO:
    family, model and, for Claude, the reason); empty when unset."""
    who = ' '.join(os.environ.get('AI_REVIEW_WHO', '').split())
    return f'Reviewed by: {who}\n\n' if who else ''


VERDICT_LINE = re.compile(r'^(?:\*\*)?Overall verdict:(?:\*\*)?[ \t]*(.*)$', re.M)
VERDICT_HEADING = re.compile(r'^#{1,6}[ \t]+Overall verdict:?[ \t]*$(.*?)(?=^#{1,6}\s|\Z)', re.M | re.S)


def review_verdict(content):
    """Verdict text from the first 'Overall verdict: <text>' line, else the first non-empty line
    under an '## Overall verdict' heading; None when the report has neither."""
    line = VERDICT_LINE.search(content)
    if line:
        return line.group(1).strip()
    heading = VERDICT_HEADING.search(content)
    if not heading:
        return None
    body = re.sub(r'<!--.*?-->', '', heading.group(1), flags=re.S)
    return next((text.strip() for text in body.splitlines() if text.strip()), None)


def finding_ids(content, level):
    """IDs of findings listed under '## <level> findings' (headings or bullets starting with an ID)."""
    return list(dict.fromkeys(FINDING_ID.findall(section(content, f'{level} findings'))))


def review_counts(content):
    """Counts line, which must be unique and agree with the listed findings."""
    matches = COUNTS.findall(content)
    if len(matches) != 1:
        fail('Review needs exactly one "Finding counts: BLOCKER=n MAJOR=n MINOR=n" line.')
    counts = tuple(int(x) for x in matches[0])
    for level, count in zip(('BLOCKER', 'MAJOR', 'MINOR'), counts):
        body = section(content, f'{level} findings')
        listed = bool(body) and not NONE_TEXT.match(body)
        if count == 0 and listed:
            fail(f'Review lists {level} findings but counts {level}=0.')
        if count > 0 and not listed:
            fail(f'Review counts {level}={count} but lists none.')
        if count and len(finding_ids(content, level)) != count:
            fail(f'Review counts {level}={count} but lists {len(finding_ids(content, level))} '
                 f'{level} finding IDs; each finding needs a stable ID such as M1.')
    return counts


# Only what the pipeline relies on is mandatory; the other sections are requested by the
# prompt but a renamed one ("Missing coverage and limitations") must not discard a review.
# A section whose count is 0 may be left out: review_counts rejects a missing one above 0.
REVIEW_FIELDS = {'code': ('Finding counts:',), 'plan': ('Finding counts:',)}


def review_format_error(mode, content):
    """The content checks of publish-review (code) and publish-plan-review (plan): the format
    error, or None. An empty report is a format error too (ai-review retries it once)."""
    if not content.strip():
        return 'The reviewer returned an empty report.'
    # A code review's verdict: an 'Overall verdict:' line or an '## Overall verdict' heading.
    if mode == 'code' and not review_verdict(content):
        return 'Review is missing Overall verdict:'
    for field in REVIEW_FIELDS[mode]:
        if field not in content:
            return f"{'Plan review' if mode == 'plan' else 'Review'} is missing {field}"
    try:
        review_counts(content)
    except ValueError as error:
        return str(error)
    return None


def review_format_check(arguments):
    """`review-format-check plan|code REPORT`, no writes: exit 0 when publishable, exit 2 with
    the format error on stdout; any other failure (unreadable report) exits 1."""
    if len(arguments) != 2 or arguments[0] not in REVIEW_FIELDS:
        fail('Usage: review-format-check plan|code REPORT')
    error = review_format_error(arguments[0], Path(arguments[1]).read_text())
    if error:
        print(' '.join(error.split()))
        sys.exit(2)


# A table cell: a backslash is only ever consumed together with the character after it, so `\|`
# can never be split into a cell ending in `\` plus a separator (letting `[^|\n]` eat the
# backslash on backtracking would do that). An unescaped `|` still ends the cell.
TABLE_CELL = r'((?:\\.|[^\\|\n])*?)'


def table_cell(text):
    """A captured table cell as a value: `\\\\` is a backslash, `\\|` a pipe (one left-to-right
    pass, other backslashes kept), surrounding space is dropped."""
    return re.sub(r'\\([\\|])', r'\1', text).strip()


# The finding cell of a disposition row (FL-16: sessions write `ID (SEVERITY) title`). One
# capturing group, the ID; a row only ever counts for its first ID. Optional severity suffix,
# then optional title text after a separator: whitespace, or `:` right after the ID/suffix; a
# dash (`—`, `–`, `-`) counts only after whitespace or the suffix. The title may not start with
# `(` (so `M1 (CRITICAL)` stays unmatched) and has no unescaped `|` or newline.
FINDING_CELL = (r'([A-Z][A-Z0-9]{0,4}-?\d+)(?:[ \t]*\((?:BLOCKER|MAJOR|MINOR)\))?'
                r'(?:(?:[ \t]+|:[ \t]*|(?<=\))(?=[—–-]))(?![ \t]*\()(?:\\.|[^\\|\n])+)?')

# `[ \t]*`, not `\s*`: a row's match must never cross a newline into the next row.
DISPOSITION_ROW = re.compile(r'^\|[ \t]*' + FINDING_CELL + r'[ \t]*\|[ \t]*(accepted|rejected|deferred)[ \t]*\|'
                             r'[ \t]*' + TABLE_CELL + r'[ \t]*\|[ \t]*' + TABLE_CELL + r'[ \t]*\|', re.M | re.I)


def unmatched_cell_hint(text, finding, row=None):
    """For a finding without a row: name the first table line whose first cell mentions it but
    that does not match the row pattern, and the row to write. Diagnostic only."""
    row = row or DISPOSITION_ROW
    mention = re.compile(r'(?<![A-Za-z0-9-])' + re.escape(finding) + r'(?!\d)')
    for line in text.splitlines():
        cell = re.match(r'\|((?:\\.|[^\\|])*)', line)
        if cell and mention.search(cell.group(1)) and not row.match(line):
            return (f' (the row starting "| {cell.group(1).strip()[:60]} |" does not match; '
                    f'write "| {finding} | <disposition> | <evidence> | <task> |")')
    return ''
# Text on the same line: `\s` would cross the newline into the table.
CONVERGENCE_LINE = re.compile(r'^Convergence:[ \t]*[^ \t\r\n]', re.M)


def start_dispositions(arguments):
    """Host-written dispositions file bound to the current review's HEAD (Claude fills the rows)."""
    head = arguments[0]
    existing = Path('.ai/reviews/dispositions.md')
    if existing.exists() and re.search(r'^Review HEAD:\s*' + re.escape(head) + r'\s*$', existing.read_text(), re.M):
        return  # Already bound to this review (e.g. resuming an interrupted triage).
    atomic('.ai/reviews/dispositions.md', f"""# Review dispositions (Claude)

Review HEAD: {head}

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
""")


def triage_check(arguments):
    """Validate dispositions against the current review. Prints 'accepted=N deferred=M'.
    With --fresh (right after triage), accepted findings must point to open TODO tasks, and
    from review round 3 on the dispositions need a `Convergence: <text>` line."""
    fresh = '--fresh' in arguments
    review = Path('.ai/reviews/current.md').read_text()
    head = re.search(r'Host evidence: HEAD ([0-9a-f]{7,40});', review)
    path = Path('.ai/reviews/dispositions.md')
    if not head or not path.exists():
        fail('No dispositions for the current review.')
    text = path.read_text()
    bound = re.search(r'^Review HEAD:\s*([0-9a-f]{7,40})\s*$', text, re.M)
    if not bound or bound.group(1) != head.group(1):
        fail('Dispositions belong to a different review.')
    rows = {m.group(1): (m.group(2).lower(), table_cell(m.group(3)), table_cell(m.group(4)))
            for m in DISPOSITION_ROW.finditer(text)}
    queue = {t['id']: t['status'] for t in tasks()}
    accepted = deferred = 0
    for level in ('BLOCKER', 'MAJOR'):
        for finding in finding_ids(review, level):
            if finding not in rows:
                fail(f'{level} finding {finding} has no disposition.' + unmatched_cell_hint(text, finding))
            disposition, evidence, task_ref = rows[finding]
            if disposition == 'accepted':
                refs = set(re.findall(r'T\d{3,}', task_ref))
                if not refs or not refs <= set(queue):
                    fail(f'Accepted finding {finding} needs an existing fix task ID.')
                if fresh and any(queue[ref] != 'TODO' for ref in refs):
                    fail(f'Accepted finding {finding} must reference new TODO fix tasks, not finished ones.')
                accepted += 1
            elif disposition == 'rejected':
                if len(evidence.strip()) < 15:
                    fail(f'Rejected finding {finding} needs concrete evidence.')
            else:
                deferred += 1
    if fresh:
        # From round 3 on, triage must say whether an area keeps failing (FL-03).
        number = len(current_review_rounds()) + 1
        if number >= 3 and not CONVERGENCE_LINE.search(re.sub(r'<!--.*?-->', '', text, flags=re.S)):
            fail(f'Round {number} triage needs a Convergence: line (see the triage prompt).')
    print(f'accepted={accepted} deferred={deferred}')


REVIEW_SUBJECT = 'chore(ai): record independent review'
TRIAGE_SUBJECT = 'chore(ai): record review triage'
HISTORY_CAP = 6000


def committed_file(commit, path):
    try:
        return git('show', f'{commit}:{path}').decode(errors='replace')
    except subprocess.CalledProcessError:
        return ''


def finding_title(body, match):
    """The one-line title of the finding whose ID `match` starts (ID and markup stripped)."""
    line = body[match.start():].split('\n', 1)[0]
    line = re.sub(r'^[#*\-\s]+', '', line)
    line = line[len(match.group(1)):] if line.startswith(match.group(1)) else line
    return re.sub(r'^[\s*:.—–-]+|[\s*]+$', '', line).replace('**', '') or '(untitled)'


def review_rounds(base, head):
    """Earlier review rounds in base..head, oldest first and uncapped. Context only, never
    authority: commit subjects can be imitated, so nothing here may approve, count or skip
    anything; the one use beyond context only adds a requirement (triage's Convergence line).
    A round is a commit titled REVIEW_SUBJECT that changed .ai/reviews/current.md; its
    disposition per finding comes from dispositions.md at the first later triage commit
    before the next round."""
    log = git('log', '--reverse', '--format=%H%x00%s', f'{base}..{head}').decode().splitlines()
    commits = [line.split('\0', 1) for line in log if '\0' in line]
    rounds = []
    for sha, subject in commits:
        if subject == REVIEW_SUBJECT and '.ai/reviews/current.md' in git(
                'diff-tree', '--no-commit-id', '--name-only', '-r', '--root', sha).decode().split('\n'):
            review = committed_file(sha, '.ai/reviews/current.md')
            reviewed = re.search(r'Host evidence: HEAD ([0-9a-f]{7,40});', review)
            findings = []
            for level in ('BLOCKER', 'MAJOR'):
                body = section(review, f'{level} findings')
                seen = set()
                for match in FINDING_ID.finditer(body):
                    if match.group(1) not in seen:
                        seen.add(match.group(1))
                        findings.append((match.group(1), level, finding_title(body, match)))
            rounds.append({'head': reviewed.group(1) if reviewed else sha, 'findings': findings,
                           'rows': None})
        elif subject == TRIAGE_SUBJECT and rounds and rounds[-1]['rows'] is None:
            text = committed_file(sha, '.ai/reviews/dispositions.md')
            rounds[-1]['rows'] = {m.group(1): (m.group(2).lower(), table_cell(m.group(4)))
                                  for m in DISPOSITION_ROW.finditer(text)}
    return rounds


def current_review_rounds():
    """Rounds before the current review: M..H from its host header (`HEAD H; merge-base M`),
    which excludes the current review's own commit, so every caller gets the same answer."""
    path = Path('.ai/reviews/current.md')
    header = review_header(path.read_text() if path.exists() else '')
    if not header:
        fail('review-history --current needs .ai/reviews/current.md with a host evidence header.')
    return review_rounds(header[1], header[0])


def review_header(content):
    """(HEAD, merge-base) from a review's host evidence header, or None."""
    header = re.search(r'Host evidence: HEAD ([0-9a-f]{7,40}); merge-base ([0-9a-f]{7,40});', content)
    return header.groups() if header else None


def review_range(arguments):
    """Print 'HEAD MERGE_BASE' of the current, verified review (the re-check's diff range)."""
    head = review_info_values()[0]
    header = review_header(Path('.ai/reviews/current.md').read_text())
    if not header or header[0] != head:
        fail('Current review has no merge-base in its host evidence header.')
    print(*header)


def render_round(number, entry, missing='no triage recorded'):
    lines = [f'### Round {number} (HEAD {entry["head"][:7]})']
    for finding, level, title in entry['findings']:
        if entry['rows'] is None:
            outcome = missing
        elif finding not in entry['rows']:
            outcome = 'no disposition'
        else:
            disposition, task_ref = entry['rows'][finding]
            tasks_found = ', '.join(dict.fromkeys(re.findall(r'T\d{3,}', task_ref)))
            outcome = f'{disposition} ({tasks_found})' if tasks_found else disposition
        lines.append(f'- {finding} [{level}] {title} — {outcome}')
    if not entry['findings']:
        lines.append('- no BLOCKER or MAJOR findings')
    return '\n'.join(lines)


def render_rounds(rounds, cap=HISTORY_CAP, title='## Previous review rounds', missing='no triage recorded'):
    """`title` section with the oldest rounds dropped until it fits the cap."""
    if not rounds:
        return ''
    blocks = [render_round(number, entry, missing) for number, entry in enumerate(rounds, 1)]
    for omitted in range(len(blocks)):
        parts = [title]
        if omitted:
            parts.append(f'({omitted} earlier rounds omitted)')
        text = '\n\n'.join(parts + blocks[omitted:])
        if len(text) <= cap:
            return text
    return '\n\n'.join([title, f'({len(blocks) - 1} earlier rounds omitted)', blocks[-1]])[:cap]


def review_history(arguments):
    """Summarise earlier review rounds (context only, never authority).
    --base B --head H: rounds in B..H. --current: rounds in M..H from the current review's
    host header. --count: only the uncapped number; --last-head: only the newest reviewed HEAD."""
    options = {}
    flags = set()
    queue = list(arguments)
    while queue:
        item = queue.pop(0)
        if item in ('--base', '--head'):
            if not queue:
                fail(f'review-history: {item} needs a value.')
            options[item] = queue.pop(0)
        elif item in ('--current', '--count', '--last-head'):
            flags.add(item)
        else:
            fail(f'review-history: unknown argument {item}.')
    if '--current' in flags:
        rounds = current_review_rounds()
    elif '--base' in options and '--head' in options:
        rounds = review_rounds(options['--base'], options['--head'])
    else:
        fail('review-history needs --current or both --base and --head.')
    if '--count' in flags:
        print(len(rounds))
    elif '--last-head' in flags:
        if rounds:
            print(rounds[-1]['head'])
    elif rounds:
        print(render_rounds(rounds))


def state_root():
    """Host state directory: AI_STATE_DIR, else $XDG_STATE_HOME/ai-toolkit, else
    ~/.local/state/ai-toolkit. A relative setting would depend on the current directory."""
    for name, suffix in (('AI_STATE_DIR', ''), ('XDG_STATE_HOME', 'ai-toolkit')):
        value = os.environ.get(name, '')
        if value:
            if not os.path.isabs(value):
                fail(f'{name} must be an absolute path: {value}')
            return Path(value, suffix) if suffix else Path(value)
    return Path(os.path.expanduser('~/.local/state/ai-toolkit'))


def overlap(a, b):
    """True when either path equals or lies inside the other, lexically or after resolving
    symlinks (realpath resolves the existing prefix of a path not created yet)."""
    for resolve in (os.path.abspath, os.path.realpath):
        first, second = Path(resolve(a)), Path(resolve(b))
        if first.is_relative_to(second) or second.is_relative_to(first):
            return True
    return False


def check_state_root(checkout, knowledge=None):
    """Refuse a host state directory agent sessions can write: one overlapping the checkout
    or the knowledge directory. This is a path check, not OS isolation."""
    root = state_root()
    for path, label in ((checkout, 'the checkout'), (knowledge, 'the knowledge directory')):
        if path and overlap(root, path):
            fail(f'Host state directory {root} overlaps {label} {path} (agent sessions can '
                 'write there); set AI_STATE_DIR to a directory outside it.')
    return root


def state_root_check(arguments):
    parser = argparse.ArgumentParser(prog='state-root-check')
    parser.add_argument('--checkout')
    parser.add_argument('knowledge', nargs='?')
    options = parser.parse_args(arguments)
    checkout = options.checkout or git('rev-parse', '--show-toplevel').decode().strip()
    check_state_root(os.path.abspath(checkout), options.knowledge)


def binding_dir():
    """Host-only store of published review digests, outside the checkout (agent sessions
    get no write access there). Keyed by the repository's root commit and path."""
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    base = check_state_root(root)
    key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return base / 'reviews' / key


# Usage-limit relaunch schedule of the run (optional, so older manifests stay valid): relaunches
# used, the pending relaunch time, the HEAD, tree digest, task and pipeline stage it was
# scheduled at and the armed resume binding ({"head", "tree", "task"}). The other optional
# fields, `timeout_reruns`, `gate_unblocks` and `rulings`, are checked beside them
# (timeout_reruns_valid).
LIMIT_FIELDS = ('limit_relaunches', 'limit_relaunch_at', 'limit_head', 'limit_tree', 'limit_task',
                'limit_stage', 'limit_resume')


def limit_stage_valid(value):
    return isinstance(value, str) and re.fullmatch(r'[ -~]{1,40}', value) is not None


def task_id_valid(value):
    return isinstance(value, str) and re.fullmatch(r'T\d{3,}', value) is not None


def limit_fields_valid(data):
    def hexes(value, size):
        return isinstance(value, str) and re.fullmatch(f'[0-9a-f]{{{size}}}', value) is not None

    count, at = data.get('limit_relaunches', 0), data.get('limit_relaunch_at', 0)
    resume = data.get('limit_resume')
    return (type(count) is int and 0 <= count <= 100 and type(at) is int and at >= 0
            and ('limit_head' not in data or hexes(data['limit_head'], 40))
            and ('limit_tree' not in data or hexes(data['limit_tree'], 64))
            and ('limit_task' not in data or task_id_valid(data['limit_task']))
            and ('limit_stage' not in data or limit_stage_valid(data['limit_stage']))
            and ('limit_resume' not in data
                 or (isinstance(resume, dict) and set(resume) == {'head', 'tree', 'task'}
                     and hexes(resume['head'], 40) and hexes(resume['tree'], 64)
                     and task_id_valid(resume['task']))))


def task_list_valid(data, field):
    """The optional list FIELD: unique valid task IDs, at most 200. Any other shape invalidates
    the manifest, as a wrong limit field does."""
    tasks = data.get(field, [])
    return (isinstance(tasks, list) and len(tasks) <= 200
            and all(task_id_valid(task) for task in tasks) and len(set(tasks)) == len(tasks))


RULING_KINDS = ('queue-order', 'task-sections', 'disposition-cell', 'flow-line')


def ruling_valid(value):
    if not isinstance(value, str) or ':' not in value:
        return False
    kind, key = value.split(':', 1)
    return kind in RULING_KINDS and re.fullmatch(r'[A-Za-z0-9._-]{1,48}', key) is not None


def timeout_reruns_valid(data):
    """The optional `timeout_reruns` field: the tasks whose timed-out session was committed and
    rerun in this run. `gate_unblocks`: the tasks set back from a gate-only block in this run.
    `rulings`: the `KIND:KEY` host rulings made in this run (same list rules, other items)."""
    rulings = data.get('rulings', [])
    return (task_list_valid(data, 'timeout_reruns') and task_list_valid(data, 'gate_unblocks')
            and isinstance(rulings, list) and len(rulings) <= 200
            and all(ruling_valid(item) for item in rulings) and len(set(rulings)) == len(rulings))


def ruling_row(arguments):
    """`ruling-row KIND WHAT WHY COST`: the run-log action cell of one host ruling, on one line
    that cannot break the run-log table (no `|`, backslash or line break; at most 400 chars)."""
    if len(arguments) != 4 or arguments[0] not in RULING_KINDS:
        fail('Usage: ruling-row KIND WHAT WHY COST')

    def clean(text):
        return re.sub(r' {2,}', ' ', re.sub(r'[|\\\r\n]', ' ', text)).strip()

    kind, what, why, cost = (clean(part) for part in arguments)
    row = f'Ruling ({kind}): {what}. Why: {why}. Cost if wrong: {cost}.'
    if len(row) > 400:
        # At the last word boundary, unless one huge word would leave little more than the prefix.
        cut = row[:401].rsplit(' ', 1)[0]
        row = cut if 300 <= len(cut) <= 400 else row[:400]
    print(row)


def limit_binding():
    """(HEAD, worktree digest) of the checkout: what a usage-limit relaunch is bound to."""
    root = checkout_root()
    try:
        head = git('rev-parse', '--verify', '-q', 'HEAD^{commit}', cwd=root).decode().strip()
    except subprocess.CalledProcessError:
        fail('usage limit: the checkout has no commit to bind the relaunch to')
    return head, worktree_digest(root)


def limit_mismatch(head, tree):
    """The reason the checkout differs from the recorded binding, or None when it is exact."""
    now_head, now_tree = limit_binding()
    if now_head != head:
        return 'the branch moved to another commit'
    if now_tree != tree:
        return 'the checkout changed'
    return None


def limit_relaunch(path, data, action, arguments):
    """run-manifest limit-* actions. A schedule is pending (AT > NOW) until one recovery claims
    it once it is due, so it is never left due after a recovery saw it. Schedule, hold and claim
    each give back the attempt `ai-recover` reserved before it could know the stop was a usage
    limit: waiting for a reset is not a failed recovery."""
    def number(value, usage):
        if not re.fullmatch(r'\d{1,12}', value):
            fail(f'Usage: run-manifest {usage}')
        return int(value)

    def clock(usage):
        if len(arguments) > 1:
            fail(f'Usage: run-manifest {usage}')
        return number(arguments[0], usage) if arguments else int(time.time())

    def give_back():
        data['attempts'] = max(0, data['attempts'] - 1)

    at = data.get('limit_relaunch_at')
    count = data.get('limit_relaunches', 0)
    if action == 'limit-schedule':
        usage = 'limit-schedule AT CAP STAGE'
        if len(arguments) != 3 or not limit_stage_valid(arguments[2]):
            fail(f'Usage: run-manifest {usage}')
        when, cap = number(arguments[0], usage), number(arguments[1], usage)
        if at is not None:
            fail('usage limit: a relaunch is already scheduled')
        if count >= min(cap, 100):
            fail(f'usage limit: already relaunched {count} time(s) in this run')
        # Verification point: ai-recover schedules after the stop's bookkeeping was written and
        # before any commit, so this is exactly the checkout the relaunch must find; the
        # relaunch verifies it before it touches the checkout (ai-recover relaunch_verify).
        start, tree = limit_binding()
        # The stage is ai-recover's --stage (host-owned, passed by ai-pipeline's stop()): the arm
        # reads it from here, never from the relaunch's own arguments.
        data.update(limit_relaunches=count + 1, limit_relaunch_at=when, limit_head=start, limit_tree=tree,
                    limit_stage=arguments[2])
        # The task whose output the stopped tree is (ai-run's record); absent stays absent.
        data.pop('limit_task', None)
        if 'task' in data:
            data['limit_task'] = data['task']
        give_back()
        atomic(path, json.dumps(data) + '\n')
        print(count + 1)
    elif action == 'limit-due':
        if at is None or at > clock('limit-due [NOW]'):
            sys.exit(1)
        print(at)
    elif action == 'limit-at':
        if arguments:
            fail('Usage: run-manifest limit-at')
        if at is None:
            sys.exit(1)
        print(at)
    elif action == 'limit-hold':
        # Still waiting: the recovery gives its reservation back and restores the wait.
        if at is None or at <= clock('limit-hold [NOW]'):
            sys.exit(1)
        give_back()
        atomic(path, json.dumps(data) + '\n')
        print(at)
    elif action == 'limit-claim':
        # Due: consumed in the same write, so any later stop of this relaunch is terminal.
        if at is None or at > clock('limit-claim [NOW]'):
            sys.exit(1)
        data.pop('limit_relaunch_at')
        give_back()
        atomic(path, json.dumps(data) + '\n')
        print(count)
    elif action in ('limit-verify', 'limit-arm'):
        # Both recompute HEAD and the tree; verify is read only, arm records the exact match.
        if arguments:
            fail(f'Usage: run-manifest {action}')
        if 'limit_head' not in data or 'limit_tree' not in data:
            fail('no scheduled relaunch')
        # Only an implementation session legitimately leaves uncommitted task work: the arm is
        # bound to that stage first, then to the task it belongs to; no record fails closed.
        if action == 'limit-arm' and data.get('limit_stage') != 'implementation':
            fail('the usage-limit stop left uncommitted changes outside an implementation session')
        if action == 'limit-arm' and 'limit_task' not in data:
            fail('the usage-limit stop left uncommitted changes with no task recorded')
        why = limit_mismatch(data['limit_head'], data['limit_tree'])
        if why:
            fail(why)
        if action == 'limit-arm':
            data['limit_resume'] = {'head': data['limit_head'], 'tree': data['limit_tree'],
                                    'task': data['limit_task']}
            atomic(path, json.dumps(data) + '\n')
    elif action == 'limit-armed':
        if arguments:
            fail('Usage: run-manifest limit-armed')
        resume = data.get('limit_resume')
        if resume is None or limit_mismatch(resume['head'], resume['tree']):
            sys.exit(1)
    elif action == 'limit-task':
        # Read only: the task the armed tree belongs to.
        if arguments:
            fail('Usage: run-manifest limit-task')
        if 'limit_resume' not in data:
            sys.exit(1)
        print(data['limit_resume']['task'])
    elif action == 'limit-disarm':
        if 'limit_resume' in data:
            data.pop('limit_resume')
            atomic(path, json.dumps(data) + '\n')
    elif action == 'limit-count':
        print(count)
    else:
        fail('Unknown run-manifest action.')


def run_manifest(arguments):
    """Host-side record of the human-approved run (outside the checkout, like review
    bindings): approved gate digest, branch, arguments and the recovery attempt budget.
    Agent sessions cannot write here, so recovery never trusts checkout files for authority."""
    path = binding_dir() / 'run.json'
    action = arguments[0]
    if action == 'start':
        gate, branch, args = arguments[1], arguments[2], arguments[3:]
        if not re.fullmatch(r'[0-9a-f]{64}', gate):
            fail('Invalid gate digest.')
        path.parent.mkdir(parents=True, exist_ok=True)
        settings = {key: os.environ[key] for key in RUN_SETTINGS if key in os.environ}
        data = {'gate': gate, 'branch': branch, 'args': args, 'attempts': 0, 'env': settings}
        # Stages live per branch (stage_path), so a run on another branch neither drops nor
        # inherits them, and one on the same branch completes it first. A legacy stage
        # inside run.json moves to its branch's file.
        try:
            old = json.loads(path.read_text())
        except (OSError, ValueError):
            old = None
        if isinstance(old, dict) and 'stage' in old and isinstance(old.get('branch'), str) \
                and not stage_path(old['branch']).exists():
            atomic(stage_path(old['branch']), json.dumps({'branch': old['branch'], 'stage': old['stage']}) + '\n')
        atomic(path, json.dumps(data) + '\n')
        return
    if action == 'stage':
        # The open stage of the current branch ('name start_head review_digest'), if any.
        # Read before any run is recorded, too: the pipeline checks it before `start`.
        stage = load_stage(current_branch())
        if stage is not None:
            print(' '.join(stage_fields(stage)))
        return
    try:
        data = json.loads(path.read_text())
        valid = (isinstance(data, dict) and isinstance(data.get('gate'), str)
                 and isinstance(data.get('branch'), str) and isinstance(data.get('args'), list)
                 and all(isinstance(a, str) for a in data['args'])
                 and type(data.get('attempts')) is int and 0 <= data['attempts'] <= 100
                 and ('task' not in data or task_id_valid(data['task']))
                 and limit_fields_valid(data) and timeout_reruns_valid(data))
    except (OSError, ValueError):
        valid = False
    if not valid:
        fail('No valid run manifest; rerun ai-pipeline --approved by hand.')
    if action.startswith('limit-'):
        return limit_relaunch(path, data, action, arguments[1:])
    if action == 'gate':
        print(data['gate'])
    elif action == 'branch':
        print(data['branch'])
    elif action == 'args':
        sys.stdout.write(''.join(arg + '\0' for arg in data['args']))
    elif action == 'env':
        # The approved run's settings, so a resume behaves like the run the human started.
        settings = data.get('env') if isinstance(data.get('env'), dict) else {}
        sys.stdout.write(''.join(f'{key}={value}\0' for key, value in settings.items()
                                 if key in RUN_SETTINGS and isinstance(value, str) and '\0' not in value))
    elif action == 'reserve-attempt':
        # Reserved before any fallible recovery work, so failures can't retry for free.
        data['attempts'] += 1
        atomic(path, json.dumps(data) + '\n')
        print(data['attempts'])
    elif action == 'clear-attempts':
        # Keeps `timeout_reruns`, `gate_unblocks` and `rulings`: a resumed pipeline must not
        # reset "once per task" (only `start`, a human-approved run, does).
        data['attempts'] = 0
        for key in ('task',) + LIMIT_FIELDS:
            data.pop(key, None)
        atomic(path, json.dumps(data) + '\n')
    elif action == 'task-set':
        # The task of the implementation session about to start. Host state written by ai-run
        # (host code, like `outcome attempt-open`), never read from the checkout; only
        # limit-schedule reads it.
        if len(arguments) != 2 or not task_id_valid(arguments[1]):
            fail('Usage: run-manifest task-set ID')
        data['task'] = arguments[1]
        atomic(path, json.dumps(data) + '\n')
    elif action == 'task-clear':
        if len(arguments) != 1:
            fail('Usage: run-manifest task-clear')
        if 'task' in data:
            data.pop('task')
            atomic(path, json.dumps(data) + '\n')
    elif action == 'task':
        # Read only: the task of the implementation session ai-run recorded, if any.
        if len(arguments) != 1:
            fail('Usage: run-manifest task')
        if 'task' not in data:
            sys.exit(1)
        print(data['task'])
    elif action == 'timeout-rerun':
        # Claims the one commit-and-rerun of a timed-out session allowed per task in this run.
        if len(arguments) != 2 or not task_id_valid(arguments[1]):
            fail('Usage: run-manifest timeout-rerun ID')
        task = arguments[1]
        reruns = data.get('timeout_reruns', [])
        if task in reruns:
            fail(f'session timeout: {task} was already committed and rerun once in this run')
        if len(reruns) >= 200:
            fail('session timeout: too many timeout reruns in this run')
        data['timeout_reruns'] = reruns + [task]
        atomic(path, json.dumps(data) + '\n')
    elif action == 'gate-unblock':
        # Claims the one gate-only block retry allowed per task in this run (FL-32): spent
        # before the host gate runs, so a failing gate spends it too.
        if len(arguments) != 2 or not task_id_valid(arguments[1]):
            fail('Usage: run-manifest gate-unblock ID')
        task = arguments[1]
        unblocks = data.get('gate_unblocks', [])
        if task in unblocks:
            fail(f'gate-only block: {task} was already retried once in this run')
        if len(unblocks) >= 200:
            fail('gate-only block: too many gate-only block retries in this run')
        data['gate_unblocks'] = unblocks + [task]
        atomic(path, json.dumps(data) + '\n')
    elif action == 'ruling':
        # Claims the one host ruling of KIND allowed per KEY in this run (BR-01): a record-format
        # repair the host makes instead of stopping, never twice for the same thing.
        if (len(arguments) != 3 or arguments[1] not in RULING_KINDS
                or not re.fullmatch(r'[A-Za-z0-9._-]{1,48}', arguments[2])):
            fail(f'Usage: run-manifest ruling KIND KEY (KIND: {", ".join(RULING_KINDS)})')
        kind, key = arguments[1], arguments[2]
        rulings = data.get('rulings', [])
        if f'{kind}:{key}' in rulings:
            fail(f'ruling {kind} for {key} was already made once in this run')
        if len(rulings) >= 200:
            fail('ruling: too many rulings in this run')
        data['rulings'] = rulings + [f'{kind}:{key}']
        atomic(path, json.dumps(data) + '\n')
    elif action == 'stage-set':
        # Recorded before the stage starts, bound to the verified review it works on: the
        # current implementation review (triage) or the current plan review (plan-revision).
        name, start = arguments[1], arguments[2]
        if name not in STAGE_DIGESTS or not re.fullmatch(r'[0-9a-f]{40}', start):
            fail('Invalid stage.')
        if name == 'triage':
            review_info_values()
            digest = review_digest()
        else:
            content = PLAN_REVIEW.read_text() if PLAN_REVIEW.exists() else ''
            if not verified_plan_review(content):
                fail('Plan revision stage: the plan review does not match the report ai-review published.')
            digest = report_digest(content)
        branch = current_branch()
        if not branch:
            fail('Invalid stage: detached HEAD.')
        stage = {'name': name, 'start_head': start, STAGE_DIGESTS[name]: digest}
        atomic(stage_path(branch), json.dumps({'branch': branch, 'stage': stage}) + '\n')
    elif action == 'revision-reserve':
        # Plan revisions this run, reserved per plan-review report BEFORE the stage opens (and
        # again, idempotently, when it is completed): a report counts once, a resume keeps the
        # list, a human (re)start resets it.
        if len(arguments) != 3 or not re.fullmatch(r'[0-9a-f]{64}', arguments[1]) \
                or not re.fullmatch(r'\d', arguments[2]):
            fail('Usage: run-manifest revision-reserve DIGEST LIMIT')
        reserved = manifest_revisions(data)
        if arguments[1] not in reserved:
            if len(reserved) >= int(arguments[2]):
                fail(f'plan review: supervision limit reached ({len(reserved)} revisions this run)')
            reserved.append(arguments[1])
            data['plan_revisions'] = reserved
            atomic(path, json.dumps(data) + '\n')
        print(len(reserved))
    elif action == 'revision-count':
        print(len(manifest_revisions(data)))
    elif action == 'extra-round-reserve':
        # The one extra fix round of this run, reserved for one implementation review BEFORE its
        # triage starts: a resume keeps it (for that review only), a human (re)start resets it.
        if len(arguments) != 2 or not re.fullmatch(r'[0-9a-f]{64}', arguments[1]):
            fail('Usage: run-manifest extra-round-reserve DIGEST')
        reserved = manifest_extra_round(data)
        if reserved and reserved != arguments[1]:
            fail('fix rounds: the extra fix round of this run is already used')
        if not reserved:
            data['extra_fix_round'] = arguments[1]
            atomic(path, json.dumps(data) + '\n')
    elif action == 'extra-round':
        print(manifest_extra_round(data))
    elif action == 'stage-clear':
        branch = current_branch()
        if branch:
            stage_path(branch).unlink(missing_ok=True)
        if 'stage' in data and data['branch'] == branch:
            data.pop('stage')
            atomic(path, json.dumps(data) + '\n')
    else:
        fail('Unknown run-manifest action.')


# Run records (RC-01 G3): one schema-versioned host record per run under `<binding dir>/runs/`
# (`<id>.json`), `runs/current` (the id of the latest run) and `runs/.lock` (flock for every
# write). The id is `<UTC stamp>-<pid>-<seq>`; `seq` is one more than the highest kept record's,
# chosen under the lock, so two starts by one pid in one second never collide. The id is not
# authority: lifecycle writes (T315) also check the recorded process identity.
RUN_SCHEMA = 1
RUN_ID = re.compile(r'\d{8}T\d{6}Z-(\d{1,10})-(\d{1,9})')
RUN_KINDS = ('pipeline', 'ai-run')
RUN_OUTCOMES = ('running', 'finished', 'stopped', 'human_stop', 'paused', 'crashed')
RUN_KEEP = 20
RUN_MAX_BYTES = 64 * 1024
RUN_LOCK_SECONDS = 5
RUN_LAUNCHER = re.compile(r'[a-z0-9._-]{1,32}')


def run_stamp():
    """UTC stamp of a new run id (one function, so tests can fix the clock)."""
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def runs_dir():
    return binding_dir() / 'runs'


def process_identity(pid):
    """{pid, pgid, sid, start_ticks} of a live process from /proc/<pid>/stat, or None when it
    does not exist or is a zombie. pid plus start ticks identifies it, so a reused pid differs."""
    try:
        data = Path(f'/proc/{int(pid)}/stat').read_bytes()
        # Fields after the command name (which may hold spaces and parentheses): state is field
        # 3, pgid 5, sid 6, start ticks 22.
        fields = data[data.rindex(b')') + 1:].split()
        if fields[0] in (b'Z', b'X', b'x'):
            return None
        return {'pid': int(pid), 'pgid': int(fields[2]), 'sid': int(fields[3]),
                'start_ticks': int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


@contextlib.contextmanager
def run_lock(runs):
    """Hold `runs/.lock` for a read-modify-write of run records; give up after
    RUN_LOCK_SECONDS rather than block a stop or a pipeline behind a stuck holder."""
    runs.mkdir(parents=True, exist_ok=True)
    fd = os.open(runs / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + RUN_LOCK_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fail('run record is locked')
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def read_small(path, limit):
    """Bytes of a regular, non-symlinked file of at most `limit` bytes, else None."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    with os.fdopen(fd, 'rb') as file:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = file.read(limit + 1)
    return data if len(data) <= limit else None


def run_valid(data, run_id):
    """Schema 1 with the plan's field types; unknown extra fields are accepted."""
    def is_int(value):
        return type(value) is int

    def is_str(value):
        return isinstance(value, str)

    if not isinstance(data, dict) or not is_int(data.get('schema')) or data['schema'] != RUN_SCHEMA:
        return False
    base, process, stop = data.get('base'), data.get('process'), data.get('stop_requested')
    return (data.get('id') == run_id and data.get('kind') in RUN_KINDS
            and all(is_str(data.get(key)) for key in ('checkout', 'branch', 'launcher', 'started', 'detail'))
            and (base is None or (isinstance(base, dict) and is_str(base.get('ref')) and is_str(base.get('sha'))))
            and isinstance(data.get('argv'), list) and all(is_str(arg) for arg in data['argv'])
            and (data.get('log') is None or is_str(data['log']))
            and isinstance(process, dict)
            and all(is_int(process.get(key)) for key in ('pid', 'pgid', 'sid', 'start_ticks'))
            and is_int(data.get('resumes')) and data['resumes'] >= 0
            and (stop is None or isinstance(stop, dict))
            and (data.get('ended') is None or is_str(data['ended']))
            and data.get('outcome') in RUN_OUTCOMES)


def current_run_id(runs):
    data = read_small(runs / 'current', 64)
    try:
        run_id = data.decode().strip('\n') if data is not None else ''
    except UnicodeDecodeError:
        return None
    return run_id if RUN_ID.fullmatch(run_id) else None


def read_run(runs, run_id=None):
    """The valid record of `run_id` (default: the current one), else None: an invalid id, an
    unknown schema, wrong field types, a symlink or a file over 64 KB is "no record"."""
    if run_id is None:
        run_id = current_run_id(runs)
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return None
    data = read_small(runs / f'{run_id}.json', RUN_MAX_BYTES)
    try:
        record = json.loads(data) if data is not None else None
    except ValueError:
        return None
    return record if run_valid(record, run_id) else None


def run_seqs(runs):
    """{seq: name} of the record names in `runs/` (names only; contents are not checked)."""
    seqs = {}
    for entry in runs.iterdir():
        match = RUN_ID.fullmatch(entry.name.removesuffix('.json')) if entry.name.endswith('.json') else None
        if match:
            seqs[int(match.group(2))] = entry.name
    return seqs


def run_launcher():
    launcher = os.environ.get('AI_LAUNCHER', '')
    if RUN_LAUNCHER.fullmatch(launcher):
        return launcher
    if os.environ.get('INVOCATION_ID'):
        return 'systemd'
    return 'terminal' if os.isatty(0) else 'other'


def run_log(pid):
    log = os.environ.get('AI_RUN_LOG', '')
    if os.path.isabs(log) and '\n' not in log and '\0' not in log:
        return log
    try:
        target = os.readlink(f'/proc/{pid}/fd/1')
        return target if os.path.isabs(target) and stat.S_ISREG(os.stat(target).st_mode) else None
    except OSError:
        return None


def start_run(runs, checkout, kind, branch, base, argv, pid):
    """Create the record of a new run for process `pid`, point `current` at it, keep the
    RUN_KEEP records with the highest seq; return the id."""
    identity = process_identity(pid)
    if identity is None:
        fail(f'run-record start: process {pid} is not running')
    record = {'schema': RUN_SCHEMA, 'id': '', 'kind': kind, 'checkout': str(checkout),
              'branch': branch, 'base': base, 'argv': list(argv), 'launcher': run_launcher(),
              'log': run_log(pid), 'started': now(), 'process': identity, 'resumes': 0,
              'stop_requested': None, 'ended': None, 'outcome': 'running', 'detail': ''}
    with run_lock(runs):
        seqs = run_seqs(runs)
        seq = max(seqs, default=0) + 1
        if seq >= 10 ** 9:
            fail('run-record start: run sequence exhausted')
        run_id = f'{run_stamp()}-{pid}-{seq}'
        record['id'] = run_id
        path = runs / f'{run_id}.json'
        # Exclusive creation: an existing name fails, never replaced.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w') as file:
                file.write(json.dumps(record) + '\n')
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        atomic(runs / 'current', run_id + '\n')
        clear_escalation(runs)
        seqs[seq] = path.name
        for old in sorted(seqs)[:-RUN_KEEP]:
            if seqs[old] != path.name:
                (runs / seqs[old]).unlink(missing_ok=True)
    return run_id


# Lifecycle (T315): every change names its run and is checked under `runs/.lock`; a run that
# is not `current`, an invalid record or a failed identity check is "not the owner" (exit 3).
RUN_END_OUTCOMES = ('finished', 'stopped', 'human_stop', 'crashed')
RUN_STOP_VIA = ('ai-pipeline --stop', 'signal')


def run_ended(record):
    return record['outcome'] not in ('running', 'paused')


def run_process_alive(process):
    identity = process_identity(process['pid'])
    return identity is not None and identity['start_ticks'] == process['start_ticks']


def run_is_process(record, pid):
    """The recorded process is `pid` with `pid`'s current start ticks (a reused pid is not)."""
    return record['process']['pid'] == pid and run_process_alive(record['process'])


def run_detail(text):
    return ' '.join(text.replace('|', '').split())[:200]


def run_change(runs, run_id, change, after=None):
    """Under the lock: `change(record)` returns the new record, True (allowed, nothing to
    write) or None (refused). Return False when refused, so no record is touched; `after()`
    runs under the same lock once a change is published."""
    with run_lock(runs):
        record = read_run(runs, run_id) if current_run_id(runs) == run_id else None
        result = change(record) if record is not None else None
        if result is None:
            return False
        if isinstance(result, dict):
            atomic(runs / f'{run_id}.json', json.dumps(result) + '\n')
            if after is not None:
                after()
        return True


def own_run(runs, run_id, pid, launcher=None):
    """Recovery (`launcher` given) or a resumed pipeline takes over the run for `pid`."""
    def change(record):
        identity = process_identity(pid)
        process = record['process']
        if (record['stop_requested'] is not None or run_ended(record) or identity is None
                or (process['pid'] != pid and run_process_alive(process))):
            return None
        record.update(process=identity, outcome='running')
        if launcher is None:
            record['resumes'] += 1
        else:
            record['launcher'] = launcher
        return record
    # An automatic resume removes the escalation record (P7); a recovery taking over does not.
    return run_change(runs, run_id, change, after=None if launcher else lambda: clear_escalation(runs))


def pause_run(runs, run_id, pid):
    def change(record):
        if run_ended(record) or not run_is_process(record, pid):
            return None
        record['outcome'] = 'paused'
        return record
    return run_change(runs, run_id, change)


def end_run(runs, run_id, pid, outcome, detail=''):
    """End the run; a pending stop request makes `stopped` a `human_stop` (P16)."""
    def change(record):
        if run_ended(record) or not run_is_process(record, pid):
            return None
        stored = 'human_stop' if outcome == 'stopped' and record['stop_requested'] is not None else outcome
        record.update(outcome=stored, ended=now(), detail=run_detail(detail))
        return record
    return run_change(runs, run_id, change)


def request_stop(runs, run_id, via, expect=None):
    """Record a stop request; `expect` = (pid, start ticks) the caller verified. A second
    request keeps the first."""
    def change(record):
        process = record['process']
        if run_ended(record) or (expect is not None and (process['pid'], process['start_ticks']) != expect):
            return None
        if record['stop_requested'] is not None:
            return True
        record['stop_requested'] = {'at': now(), 'via': via}
        return record
    return run_change(runs, run_id, change)


def settle_stop(runs, run_id):
    """A stop-requested run whose process is gone and that has not ended is a `human_stop`."""
    def change(record):
        if record['stop_requested'] is None or run_ended(record) or run_process_alive(record['process']):
            return None
        record.update(outcome='human_stop', ended=now())
        return record
    return run_change(runs, run_id, change)


def stop_requested(runs, run_id):
    """True or False for the current run `run_id`; None when it is not current or invalid."""
    with run_lock(runs):
        record = read_run(runs, run_id) if current_run_id(runs) == run_id else None
    if record is None:
        return None
    return record['stop_requested'] is not None or record['outcome'] == 'human_stop'


STOP_VIA = 'ai-pipeline --stop'
STOP_POLL_SECONDS = 0.2


def stop_ended_message(record):
    """Exit-0 message for a run that ended on its own after the stop began (P16: never settled)."""
    if record['outcome'] == 'human_stop':
        return f'Run {record["id"]} stopped (stopped by you).'
    return f'Run {record["id"]} ended ({record["outcome"]}) before the stop took effect; nothing will resume it.'


def stop_replaced(run_id, checkout):
    return f'Run {run_id} ended; another run replaced it in {checkout}; nothing else recorded.'


def stop_gone(runs, checkout, run_id, message):
    """The run's process is gone but its record has not ended: record the request and settle it
    as `human_stop`, so nothing resumes it, then complete the records it left (T319). Return
    MESSAGE, or what happened instead: it ended by itself in between, or another run replaced
    it (then nothing more is written)."""
    request_stop(runs, run_id, STOP_VIA)
    if not settle_stop(runs, run_id):
        record = read_run(runs, run_id)
        if current_run_id(runs) != run_id:
            return stop_replaced(run_id, checkout)
        if record is None or not run_ended(record):
            fail(f'Run {run_id} could not be recorded as stopped.')
        return stop_ended_message(record)
    return stop_complete(runs, checkout, run_id, message)


def stop_stage(local_fd):
    """The run's last pipeline step (a box key of the observation record), else `unknown`."""
    found = read_record(local_fd, 'observation.json', OBSERVATION_LIMIT)
    try:
        stage = json.loads(found[0]).get('stage') if found is not None else None
    except (ValueError, AttributeError):
        stage = None
    return stage if stage in BOX_KEYS else 'unknown'


def stop_complete(runs, checkout, run_id, message):
    """Completion (T319): the settled run's process ended without its own stop records. Only
    while this process holds `.ai/local/workflow.lock` (`flock -n`; held: another runner owns
    the checkout) and `run_id` is still current: the escalation record, the liveness marker
    when it names the recorded pid, `last-error` and `last-error.notified` (the human was told
    here), all through the pinned `.ai/local`."""
    record = read_run(runs, run_id)
    fds = checkout_fds(checkout)
    local_fd = None
    if fds is not None:
        local_fd = fds[2]
        if local_fd is None:  # as ai_root's `mkdir -p .ai/local`, on the pinned `.ai`
            with contextlib.suppress(OSError):
                os.mkdir('local', 0o755, dir_fd=fds[1])
            local_fd = open_dir(fds[1], 'local')
        close_fds(fds[0], fds[1])
    if record is None or local_fd is None:
        fail(f'Run {run_id} was recorded as stopped by you, but .ai/local is missing or unsafe; nothing else recorded.')
    try:
        try:
            lock_fd = os.open('workflow.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
                              | os.O_CLOEXEC, 0o600, dir_fd=local_fd)
        except OSError as error:
            fail(f'Run {run_id} was recorded as stopped by you; cannot open the checkout lock: {error.strerror}')
        try:
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                fail(f'Run {run_id} was recorded as stopped by you; the checkout lock is not a regular file.')
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return f'Run {run_id} ended; another runner owns {checkout} now; nothing else recorded.'
            if current_run_id(runs) != run_id:
                return stop_replaced(run_id, checkout)
            stage = stop_stage(local_fd)
            write_escalation(runs, 'human_stop', stage, run_id, [], [], None)
            marker = read_record(local_fd, 'pipeline.active', SMALL_LIMIT)
            if marker is not None and marker[0].strip() == str(record['process']['pid']):
                with contextlib.suppress(FileNotFoundError):
                    os.unlink('pipeline.active', dir_fd=local_fd)
            try:
                write_record(local_fd, 'last-error', f'stopped by the human during {stage}\n')
                write_record(local_fd, 'last-error.notified', '')
                # Strictly newer, also within one coarse timestamp tick: nothing announces it again.
                error_ns = os.stat('last-error', dir_fd=local_fd, follow_symlinks=False).st_mtime_ns
                os.utime('last-error.notified', ns=(error_ns + 1000, error_ns + 1000), dir_fd=local_fd,
                         follow_symlinks=False)
            except (RecordError, OSError) as error:
                fail(f'Run {run_id} was recorded as stopped by you; cannot write last-error: {error}')
        finally:
            os.close(lock_fd)  # releases the lock
    finally:
        os.close(local_fd)
    return message


def stop_relaunch_scheduled(record):
    """The paused run has a scheduled usage-limit relaunch in its manifest."""
    if record['outcome'] != 'paused':
        return False
    data = read_small(binding_dir() / 'run.json', RUN_MAX_BYTES)
    try:
        manifest = json.loads(data) if data is not None else None
    except ValueError:
        return False
    at = manifest.get('limit_relaunch_at') if isinstance(manifest, dict) else None
    return type(at) is int and at > 0


def stop_not_running(run_id):
    return f'Run {run_id} was not running (its process is gone); recorded as stopped by you, it will not be resumed.'


def stop_signal(process):
    """SIGTERM to the run's group when its pid leads it (and it is not our own group), else to
    the pid alone; never PID 1."""
    pid, pgid = process['pid'], process['pgid']
    if pid <= 1:
        fail(f'refusing to signal process {pid}')
    with contextlib.suppress(ProcessLookupError):  # ended in between: the wait sees it gone
        if pgid == pid and pgid != os.getpgrp():
            os.killpg(pgid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)


def run_stop(arguments):
    """`run-stop [--wait SECONDS]` (RC-01 G1, `ai-pipeline --stop`): stop the checkout's current
    run, found through its record only and kept by id. Exit 0 stopped or recorded as stopped,
    3 nothing to stop, 4 still ending after the wait, 1 refused or error."""
    wait = 60
    if arguments:
        if len(arguments) != 2 or arguments[0] != '--wait' or not re.fullmatch(r'[1-9]\d{0,3}', arguments[1]):
            fail('Usage: run-stop [--wait SECONDS]')
        wait = int(arguments[1])
    runs, checkout = runs_dir(), checkout_root()
    run_id = current_run_id(runs)
    record = read_run(runs, run_id) if run_id else None
    if record is None:
        print(f'No run active in {checkout}.', file=sys.stderr)
        sys.exit(3)
    if run_ended(record):
        if record['outcome'] == 'human_stop':
            print(f'Run {run_id} was already stopped by you.', file=sys.stderr)
        else:
            print(f'No run active in {checkout} (run {run_id} ended {record["outcome"]}).', file=sys.stderr)
        sys.exit(3)
    process = record['process']
    if not run_process_alive(process):
        message = (f'Cancelled the scheduled usage-limit relaunch of {run_id}.'
                   if stop_relaunch_scheduled(record) else stop_not_running(run_id))
        print(stop_gone(runs, checkout, run_id, message))
        return
    if not request_stop(runs, run_id, STOP_VIA, expect=(process['pid'], process['start_ticks'])):
        latest = read_run(runs, run_id)
        if latest is not None and run_ended(latest):
            print(stop_ended_message(latest))
            return
        fail(f'Run {run_id} is no longer the current run of {checkout}; nothing signalled.')
    # Checked again just before the signal: a pid reused since the request is never signalled.
    identity = process_identity(process['pid'])
    if identity is None or identity['start_ticks'] != process['start_ticks']:
        print(stop_gone(runs, checkout, run_id, stop_not_running(run_id)))
        return
    stop_signal(identity)
    deadline = time.monotonic() + wait
    while True:
        # Liveness first: once the process is gone, every record write it made is visible.
        alive = run_process_alive(process)
        latest = read_run(runs, run_id)
        if latest is not None and run_ended(latest):
            print(stop_ended_message(latest))
            return
        if not alive:
            print(stop_gone(runs, checkout, run_id, f'Run {run_id} stopped (stopped by you).'))
            return
        if time.monotonic() >= deadline:
            break
        time.sleep(STOP_POLL_SECONDS)
    print(f'Signalled run {run_id}; still ending after {wait} s. Rerun to wait again.', file=sys.stderr)
    sys.exit(4)


def run_lifecycle(action, rest, runs):
    usage = {'own': '--run ID --pid PID --launcher NAME', 'resume': '--run ID --pid PID',
             'pause': '--run ID --pid PID', 'end': '--run ID --pid PID OUTCOME [DETAIL]',
             'request-stop': '--run ID --via VIA [--expect-pid P --expect-ticks T]',
             'settle-stop': '--run ID', 'stop-requested': '--run ID'}[action]
    names = {'own': ('--pid', '--launcher'), 'resume': ('--pid',), 'pause': ('--pid',), 'end': ('--pid',),
             'request-stop': ('--via', '--expect-pid', '--expect-ticks')}.get(action, ())
    options, positional, index = {}, [], 0
    while index < len(rest):
        if rest[index] in ('--run', *names) and index + 1 < len(rest) and rest[index] not in options:
            options[rest[index]] = rest[index + 1]
            index += 2
        else:
            positional.append(rest[index])
            index += 1

    def number(name):
        value = options.get(name, '')
        return int(value) if re.fullmatch(r'[1-9]\d{0,18}', value) else None

    run_id, pid = options.get('--run', ''), number('--pid')
    valid = (RUN_ID.fullmatch(run_id) is not None and len(positional) in ((1, 2) if action == 'end' else (0,))
             and ('--pid' not in names or pid is not None))
    if action == 'own':
        valid = valid and RUN_LAUNCHER.fullmatch(options.get('--launcher', '')) is not None
    if action == 'end':
        valid = valid and positional[0] in RUN_END_OUTCOMES
    if action == 'request-stop':
        expect = (number('--expect-pid'), number('--expect-ticks'))
        valid = (valid and options.get('--via') in RUN_STOP_VIA
                 and ('--expect-pid' in options) == ('--expect-ticks' in options) and
                 ('--expect-pid' not in options or None not in expect))
    if not valid:
        fail(f'Usage: run-record {action} {usage}')
    if action == 'stop-requested':
        requested = stop_requested(runs, run_id)
        if requested is not None:
            sys.exit(0 if requested else 1)
    elif {'own': lambda: own_run(runs, run_id, pid, options['--launcher']),
          'resume': lambda: own_run(runs, run_id, pid),
          'pause': lambda: pause_run(runs, run_id, pid),
          'end': lambda: end_run(runs, run_id, pid, *positional),
          'request-stop': lambda: request_stop(runs, run_id, options['--via'],
                                               expect if '--expect-pid' in options else None),
          'settle-stop': lambda: settle_stop(runs, run_id)}[action]():
        return
    print(f'run-record {action}: not the owner of run {run_id}', file=sys.stderr)
    sys.exit(3)


def run_record(arguments):
    """`start KIND BRANCH BASE_REF BASE_SHA --pid PID -- ARGS…` (prints the new id),
    `current`, `show [ID]` and `alive [ID]`; exit 1 when there is no valid record. Lifecycle
    actions (`own`, `resume`, `pause`, `end`, `request-stop`, `settle-stop`, `stop-requested`)
    exit 3 when the caller is not the owner of the named run."""
    if not arguments:
        fail('Usage: run-record start|current|show|alive|own|resume|pause|end|request-stop|'
             'settle-stop|stop-requested …')
    action, rest = arguments[0], arguments[1:]
    runs = runs_dir()
    if action in ('own', 'resume', 'pause', 'end', 'request-stop', 'settle-stop', 'stop-requested'):
        run_lifecycle(action, rest, runs)
        return
    if action == 'start':
        if len(rest) < 7 or rest[4] != '--pid' or rest[6] != '--':
            fail('Usage: run-record start KIND BRANCH BASE_REF BASE_SHA --pid PID -- ARGS…')
        kind, branch, ref, sha, pid, argv = rest[0], rest[1], rest[2], rest[3], rest[5], rest[7:]
        if kind not in RUN_KINDS:
            fail(f'run-record start: KIND must be one of {", ".join(RUN_KINDS)}')
        if not re.fullmatch(r'[1-9]\d{0,9}', pid):
            fail('run-record start: invalid --pid')
        if (ref == '-') != (sha == '-') or (sha != '-' and not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha)):
            fail('run-record start: BASE_REF and BASE_SHA are both "-" or a ref and a commit id')
        base = None if ref == '-' else {'ref': ref, 'sha': sha}
        print(start_run(runs, checkout_root(), kind, branch, base, argv, int(pid)))
        return
    if action not in ('current', 'show', 'alive') or len(rest) > (action != 'current'):
        fail('Usage: run-record current | show [ID] | alive [ID]')
    record = read_run(runs, rest[0] if rest else None)
    if record is None:
        sys.exit(1)
    if action == 'current':
        print(record['id'])
    elif action == 'show':
        print(json.dumps(record, indent=2))
    else:
        process = record['process']
        identity = process_identity(process['pid'])
        sys.exit(0 if identity and identity['start_ticks'] == process['start_ticks'] else 1)


# Escalation record (RC-01 G9, T305): why the current run waits for a human, with redacted
# evidence and the allowed answers as argument arrays. One record and one pending hint beside
# `runs/`, both changed under `runs/.lock`.
ESCALATION_SCHEMA = 1
ESCALATION_KINDS = ('plan_review_limit', 'fix_round_limit', 'task_blocked', 'needs_human_question',
                    'validation', 'usage_limit', 'crash', 'human_stop', 'other')
ESCALATION_TASK = re.compile(r'T\d{3,}')
ESCALATION_FINDING = re.compile(r'[A-Z]{1,3}\d{1,4}')
ESCALATION_REVIEWS = ('.ai/reviews/plan.md', '.ai/reviews/current.md', '.ai/reviews/recheck.md')
ESCALATION_MAX_ROUNDS = 5
ESCALATION_ERROR_CHARS = 400
# Spec B10: provider keys anywhere, and the value after a secret-looking word.
REDACT_KEYS = re.compile(r'(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{6,}|gh[pousr]_[A-Za-z0-9]{6,}'
                         r'|github_pat_[A-Za-z0-9_]{6,}|xox[a-z]-[A-Za-z0-9-]+)')
REDACT_VALUES = re.compile(r'(?i)(?<![a-z])((?:token|password|secret|key|authorization|bearer)[a-z_-]*)'
                           r'(\s*[=:]\s*|\s+)(?:bearer\s+)?(?!\[redacted\])\S+')


def escalation_paths(runs):
    return runs.parent / 'escalation.json', runs.parent / 'escalation-hint.json'


def clear_escalation(runs):
    """Remove the record and the hint (the caller holds `runs/.lock`)."""
    for path in escalation_paths(runs):
        path.unlink(missing_ok=True)


def escalation_kind(kind):
    return kind if kind in ESCALATION_KINDS else 'other'


def redact_error(text):
    """One line of at most 400 characters with secrets replaced by `[redacted]` (spec B10)."""
    line = REDACT_KEYS.sub('[redacted]', ' '.join(text.split()))
    line = REDACT_VALUES.sub(lambda match: f'{match.group(1)}{match.group(2)}[redacted]', line)
    return line[:ESCALATION_ERROR_CHARS]


def escalation_local(name):
    """Text of `.ai/local/NAME` of this checkout through the pinned `.ai/local` (regular file,
    at most 64 KB), else None."""
    local_fd = local_dir_fd(checkout_root())
    if local_fd is None:
        return None
    try:
        found = read_record(local_fd, name, RUN_MAX_BYTES)
    finally:
        os.close(local_fd)
    return found[0] if found is not None else None


def read_escalation_file(path):
    data = read_small(path, RUN_MAX_BYTES)
    try:
        value = json.loads(data) if data is not None else None
    except ValueError:
        return None
    return value if isinstance(value, dict) and value.get('schema') == ESCALATION_SCHEMA \
        and type(value['schema']) is int else None


def escalation_valid(data):
    evidence = data.get('evidence')
    return (all(isinstance(data.get(key), str) for key in ('kind', 'stage', 'run', 'branch', 'created'))
            and isinstance(data.get('tasks'), list) and isinstance(evidence, dict)
            and isinstance(evidence.get('findings'), list) and isinstance(data.get('answers'), list)
            and all(isinstance(answer, dict) and isinstance(answer.get('argv'), list)
                    and all(isinstance(arg, str) for arg in answer['argv']) for answer in data['answers']))


def option_value(argv, name):
    """The last value of `name VALUE` in argv (as bash option parsing keeps it), else None."""
    value = None
    for index, arg in enumerate(argv[:-1]):
        if arg == name:
            value = argv[index + 1]
    return value


def escalation_answers(kind, tasks, record):
    """Answers built only from the run record (its kind and argv), never from `run.json`
    (round 3, P18)."""
    argv, pipeline = record['argv'], record['kind'] == 'pipeline'
    if pipeline:
        resume = ['.ai/bin/ai-pipeline', *argv]
    elif '--approved' in argv and not {'--plan', '--triage', '--revise-plan'} & set(argv):
        resume = ['.ai/bin/ai-run', *argv]
    else:
        resume = None
    answers = []
    if kind == 'task_blocked':
        for task in tasks:
            answers += [
                {'id': 'retry_task', 'task': task, 'label': f'Return {task} to TODO with a note',
                 'argv': ['.ai/bin/ai-task', 'retry', task, '--note', '{note}', '--commit']},
                {'id': 'skip_task', 'task': task, 'label': f'Skip {task} with a reason',
                 'argv': ['.ai/bin/ai-task', 'skip', task, '--reason', '{reason}', '--commit']},
                {'id': 'set_model', 'task': task, 'label': f'Set the model of {task}',
                 'argv': ['.ai/bin/ai-task', 'model', task, '{model}', '--commit']}]
    elif kind == 'needs_human_question':
        answers.append({'id': 'review_plan',
                        'label': 'Review the plan again after answering in .ai/reviews/plan-dispositions.md',
                        'argv': ['.ai/bin/ai-review', '--plan']})
    elif kind == 'plan_review_limit' and pipeline:
        if '--skip-plan-review' not in argv:
            answers.append({'id': 'resume_skip_plan_review', 'label': 'Start the run again without the plan review',
                            'argv': [*resume, '--skip-plan-review']})
    elif kind == 'fix_round_limit' and pipeline:
        rounds = option_value(argv, '--max-fix-rounds')
        rounds = 2 if rounds is None else int(rounds) if re.fullmatch(r'\d', rounds) else None
        if rounds is not None and rounds + 1 <= ESCALATION_MAX_ROUNDS:
            more = list(argv)
            if '--max-fix-rounds' in more:
                index = len(more) - 2 - more[-2::-1].index('--max-fix-rounds')
                more[index + 1] = str(rounds + 1)
            else:
                more += ['--max-fix-rounds', str(rounds + 1)]
            answers.append({'id': 'resume_more_rounds', 'label': f'Start the run again with {rounds + 1} fix rounds',
                            'argv': ['.ai/bin/ai-pipeline', *more]})
    if resume is not None:
        answers.append({'id': 'resume', 'label': 'Start the run again with its approved arguments',
                        'argv': resume})
    return answers


def escalation_not_before():
    """Reset epoch from `.ai/local/limit-stop` (`<Agent> <epoch>`), or None when unknown."""
    stop = re.fullmatch(r'(?:Claude|Codex) (\d{1,12})\n?', escalation_local('limit-stop') or '')
    return int(stop.group(1)) if stop and int(stop.group(1)) > 0 else None


def write_escalation(runs, kind, stage, run_id, tasks, findings, review):
    """Write the record for the current run `run_id`; False (nothing written) when it is not
    current. A same-run write whose kind stays `other` keeps a specific kind (P13)."""
    record_path, hint_path = escalation_paths(runs)
    with run_lock(runs):
        record = read_run(runs, run_id) if current_run_id(runs) == run_id else None
        if record is None:
            return False
        hint = read_escalation_file(hint_path)
        hint = hint if hint is not None and hint.get('run') == run_id else None
        kind = escalation_kind(kind)
        if kind == 'other':
            if record['stop_requested'] is not None or record['outcome'] == 'human_stop':
                kind = 'human_stop'
            elif hint is not None:
                kind = escalation_kind(hint.get('kind'))

                def hinted(key, pattern):
                    values = hint.get(key) if isinstance(hint.get(key), list) else []
                    return [value for value in values if isinstance(value, str) and pattern.fullmatch(value)]
                tasks = list(dict.fromkeys(tasks + hinted('tasks', ESCALATION_TASK)))
                findings = list(dict.fromkeys(findings + hinted('findings', ESCALATION_FINDING)))
            elif stage == 'validation':
                kind = 'validation'
            elif stage.startswith('crash'):
                kind = 'crash'
        if hint is not None:
            hint_path.unlink(missing_ok=True)
        existing = read_escalation_file(record_path)
        if kind == 'other' and existing is not None and existing.get('run') == run_id \
                and existing.get('kind') != 'other':
            return True
        last_error = escalation_local('last-error')
        data = {'schema': ESCALATION_SCHEMA, 'kind': kind, 'stage': stage, 'run': run_id,
                'branch': record['branch'], 'created': now(), 'tasks': tasks,
                'evidence': {'last_error': redact_error(last_error) if last_error is not None else None,
                             'review': review, 'findings': findings, 'log': record['log']},
                'answers': escalation_answers(kind, tasks, record)}
        if kind == 'usage_limit':
            data['not_before'] = escalation_not_before()
        atomic(record_path, json.dumps(data, indent=2) + '\n')
    return True


def write_escalation_hint(runs, kind, run_id, tasks, findings):
    with run_lock(runs):
        if current_run_id(runs) != run_id or read_run(runs, run_id) is None:
            return False
        atomic(escalation_paths(runs)[1], json.dumps(
            {'schema': ESCALATION_SCHEMA, 'run': run_id, 'kind': escalation_kind(kind), 'tasks': tasks,
             'findings': findings, 'created': now()}) + '\n')
    return True


def escalation(arguments):
    """`write KIND STAGE --run ID [--task ID]… [--finding ID]… [--review PATH]`, `hint KIND
    --run ID [--task ID]… [--finding ID]…`, `show` (exit 1 when none or invalid) and `clear`.
    `write` and `hint` exit 3, writing nothing, when ID is not the current run."""
    usage = ('Usage: escalation write KIND STAGE --run ID [--task ID]… [--finding ID]… [--review PATH] | '
             'hint KIND --run ID [--task ID]… [--finding ID]… | show | clear')
    if not arguments:
        fail(usage)
    action, rest = arguments[0], arguments[1:]
    runs = runs_dir()
    if action in ('show', 'clear'):
        if rest:
            fail(usage)
        if action == 'clear':
            with run_lock(runs):
                clear_escalation(runs)
            return
        data = read_escalation_file(escalation_paths(runs)[0])
        if data is None or not escalation_valid(data):
            sys.exit(1)
        data['kind'] = escalation_kind(data['kind'])
        print(json.dumps(data, indent=2))
        return
    if action not in ('write', 'hint'):
        fail(usage)
    positional, options, tasks, findings, index = [], {}, [], [], 0
    while index < len(rest):
        name = rest[index]
        if name in ('--run', '--task', '--finding', '--review') and index + 1 < len(rest):
            value = rest[index + 1]
            if name == '--task' and ESCALATION_TASK.fullmatch(value):
                tasks.append(value)
            elif name == '--finding' and ESCALATION_FINDING.fullmatch(value):
                findings.append(value)
            elif name in ('--run', '--review') and name not in options and (action == 'write' or name == '--run'):
                options[name] = value
            else:
                fail(usage)
            index += 2
        else:
            positional.append(name)
            index += 1
    run_id, review = options.get('--run', ''), options.get('--review')
    stage_ok = action == 'hint' or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}',
                                                positional[1] if len(positional) > 1 else '')
    if (not RUN_ID.fullmatch(run_id) or len(positional) != (2 if action == 'write' else 1) or not stage_ok
            or (review is not None and review not in ESCALATION_REVIEWS)):
        fail(usage)
    if action == 'write' and positional[0] == 'fix_round_limit' and review is not None and not findings:
        # The findings the loop gave up on: the review's BLOCKER and MAJOR ids; unreadable is [].
        raw = read_small(os.path.join(checkout_root(), review), 1 << 20)
        if raw is not None:
            text = raw.decode('utf-8', 'replace')
            findings = [i for level in ('BLOCKER', 'MAJOR') for i in finding_ids(text, level)
                        if ESCALATION_FINDING.fullmatch(i)]
    tasks, findings = list(dict.fromkeys(tasks)), list(dict.fromkeys(findings))
    if action == 'write':
        done = write_escalation(runs, positional[0], positional[1], run_id, tasks, findings, review)
    else:
        done = write_escalation_hint(runs, positional[0], run_id, tasks, findings)
    if not done:
        print(f'escalation {action}: run {run_id} is not the current run', file=sys.stderr)
        sys.exit(3)


# Files a review triage may change: dispositions, the task queue and runner bookkeeping.
TRIAGE_RECORDS = ('.ai/tasks.md', '.ai/reviews/dispositions.md', '.ai/current-plan.md',
                  '.ai/state.md', '.ai/handoff.md', '.ai/run-log.md')
TRIAGE_COMMIT = 'chore(ai): record review triage'


def current_branch():
    try:
        return git('symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        return ''


def stage_path(branch):
    """Host-side file holding BRANCH's open stage, beside the run manifest."""
    return binding_dir() / f'stage-{hashlib.sha256(branch.encode()).hexdigest()[:16]}.json'


PR_DRAFT_URL = re.compile(r'https://\S+/pull/\d+')
PR_DRAFT_HOW = ('created', 'converted')


def pr_draft_path(branch):
    """Host-side record that the pipeline made BRANCH's pull request a draft. It lives outside
    every checkout so an agent session cannot forge "the pipeline drafted this", in its own
    subdirectory so a fault there is confined to it."""
    return binding_dir() / 'pr-draft' / f'{hashlib.sha256(branch.encode()).hexdigest()[:16]}.json'


def pr_draft_read(branch):
    """The record for BRANCH as a dict, or None. Anything unreadable or foreign is "not ours":
    the pipeline never un-drafts a pull request on doubt."""
    if not branch:
        return None
    try:
        data = json.loads(pr_draft_path(branch).read_text())
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or data.get('branch') != branch
            or not isinstance(data.get('url'), str) or not PR_DRAFT_URL.fullmatch(data['url'])
            or data.get('how') not in PR_DRAFT_HOW):
        return None
    return data


def pr_draft_remove(path):
    """Durably remove the record: unlink, fsync the directory, confirm the path is gone."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as error:
        fail(f'cannot remove the draft record {path}: {error.strerror}')
    try:
        fd = os.open(path.parent, os.O_RDONLY)
    except FileNotFoundError:
        fd = None
    except OSError as error:
        fail(f'cannot remove the draft record {path}: {error.strerror}')
    if fd is not None:
        try:
            os.fsync(fd)
        except OSError as error:
            fail(f'cannot remove the draft record {path}: {error.strerror}')
        finally:
            os.close(fd)
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        fail(f'cannot remove the draft record {path}: {error.strerror}')
    fail(f'cannot remove the draft record {path}: still present')


def pr_draft(arguments):
    action, *rest = arguments or ['']
    branch = current_branch()
    if action == 'record' and len(rest) == 2:
        url, how = rest
        if not PR_DRAFT_URL.fullmatch(url) or how not in PR_DRAFT_HOW:
            fail('pr-draft record needs a pull request URL and created or converted.')
        if not branch:
            fail('pr-draft record needs a branch (HEAD is detached).')
        path = pr_draft_path(branch)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic(path, json.dumps({'branch': branch, 'url': url, 'how': how, 'at': now()}) + '\n')
    elif action == 'get' and not rest:
        record = pr_draft_read(branch)
        if record is None:
            sys.exit(1)
        print(record['url'])
    elif action == 'clear' and not rest:
        if branch:
            pr_draft_remove(pr_draft_path(branch))
    elif action == 'take' and len(rest) == 1:
        record = pr_draft_read(branch)
        if record is None or record['url'] != rest[0]:
            sys.exit(1)
        pr_draft_remove(pr_draft_path(branch))
        print(record['how'])
    else:
        fail('Usage: pr-draft record URL created|converted | get | clear | take URL')


def load_stage(branch):
    """BRANCH's open stage record, or None. Unreadable or foreign data fails closed."""
    if not branch:
        return None
    path = stage_path(branch)
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        # A legacy stage inside run.json (until `start` moves it to its branch's file).
        try:
            data = json.loads((binding_dir() / 'run.json').read_text())
        except (OSError, ValueError):
            return None
        if isinstance(data, dict) and data.get('branch') == branch and 'stage' in data:
            return data['stage']
        return None
    except (OSError, ValueError):
        fail(f'Triage stage: the stage record {path} is unreadable.')
    if not isinstance(data, dict) or data.get('branch') != branch or 'stage' not in data:
        fail(f'Triage stage: the stage record {path} does not belong to this branch.')
    return data['stage']


def review_digest():
    return hashlib.sha256(Path('.ai/reviews/current.md').read_bytes()).hexdigest()


def manifest_revisions(data):
    """The plan-review report digests reserved for revision in this run (run manifest)."""
    reserved = data.get('plan_revisions', [])
    if not isinstance(reserved, list) or not all(
            isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) for digest in reserved):
        fail('The run manifest plan revision reservations are unreadable; rerun ai-pipeline --approved by hand.')
    return list(reserved)


def manifest_extra_round(data):
    """The review digest the extra fix round of this run is reserved for, or ''."""
    reserved = data.get('extra_fix_round', '')
    if not isinstance(reserved, str) or not re.fullmatch(r'(?:[0-9a-f]{64})?', reserved):
        fail('The run manifest extra fix round reservation is unreadable; rerun ai-pipeline --approved by hand.')
    return reserved


# Stage name ->the digest it is bound to: the implementation review a triage answers, the
# plan review a plan revision answers.
STAGE_DIGESTS = {'triage': 'review_digest', 'plan-revision': 'report_digest'}
STAGE_LABELS = {'triage': 'Triage stage', 'plan-revision': 'Plan revision stage'}


def stage_fields(stage):
    """'name start_head digest' of a stage record; anything else fails closed."""
    name = stage.get('name') if isinstance(stage, dict) else None
    if name not in STAGE_DIGESTS:
        fail('Triage stage: the stage record is invalid.')
    fields = [name, stage.get('start_head'), stage.get(STAGE_DIGESTS[name])]
    if not isinstance(fields[1], str) or not re.fullmatch(r'[0-9a-f]{40}', fields[1]) \
            or not isinstance(fields[2], str) or not re.fullmatch(r'[0-9a-f]{64}', fields[2]):
        fail(f'{STAGE_LABELS[name]}: the stage record is invalid.')
    return fields


def changed_since(start):
    """Paths changed since START: committed, staged, unstaged and untracked (not ignored)."""
    names = git('diff', '--name-only', '--no-renames', '-z', start).split(b'\0')
    names += git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
    return sorted({os.fsdecode(name) for name in names if name})


def records_scope(start, records, label):
    """Since START, only RECORDS changed (committed or not)."""
    if subprocess.run(['git', 'merge-base', '--is-ancestor', start, 'HEAD'],
                      stderr=subprocess.DEVNULL).returncode != 0:
        fail(f'{start[:12]} is not an ancestor of HEAD (history rewritten?).')
    outside = [name for name in changed_since(start) if name not in records]
    if outside:
        fail(f'{label} changed files outside workflow records: ' + ' '.join(outside[:8])
             + (f' (+{len(outside) - 8} more)' if len(outside) > 8 else ''))


def triage_scope(arguments):
    """Since START, only triage records changed (committed or not)."""
    records_scope(arguments[0], TRIAGE_RECORDS, 'Triage')


def stage_verify(arguments):
    """Verify an open stage before it is completed. Prints 'committed' when its counted
    commit already exists after start_head (close it without a second count), else 'pending'.
    Any mismatch fails: the caller escalates without implementation or counting."""
    stage = load_stage(current_branch())
    if stage is None:
        fail('Triage stage: no open stage for this branch.')
    name, start, digest = stage_fields(stage)
    if name == 'plan-revision':
        plan_stage_verify(start, digest)
        return
    try:
        review_info_values()
    except ValueError as error:
        fail(f'Triage stage: {error}')
    if review_digest() != digest:
        fail('Triage stage: the current review is not the one this triage started on.')
    try:
        triage_scope([start])
    except ValueError as error:
        fail(f'Triage stage: {error}')
    # Only a host-recorded triage commit closes the stage; a commit subject alone never does.
    commits = git('log', '--format=%H', f'{start}..HEAD').decode().split()
    if not set(commits) & set(fix_round_commits()):
        print('pending')
        return
    if git('status', '--porcelain', '--untracked-files=all').strip():
        fail('Triage stage: uncommitted changes after the counted triage commit.')
    print('committed')


def bind_review(head, content):
    directory = binding_dir()
    directory.mkdir(parents=True, exist_ok=True)
    atomic(directory / f'{head}.sha256', hashlib.sha256(content.encode()).hexdigest() + '\n')


def review_info(arguments):
    """Print reviewed HEAD and finding counts: HEAD BLOCKER MAJOR MINOR. The report must match
    the digest the host recorded when ai-review published it."""
    print(*review_info_values())


def review_info_values():
    content = Path('.ai/reviews/current.md').read_text()
    head = re.search(r'Host evidence: HEAD ([0-9a-f]{7,40});', content)
    if not head:
        fail('Current review has no host evidence; it was not produced by ai-review.')
    binding = binding_dir() / f'{head.group(1)}.sha256'
    if not binding.exists() or binding.read_text().strip() != hashlib.sha256(content.encode()).hexdigest():
        fail('Current review does not match the report ai-review published; it is invalid until Codex reviews again.')
    return (head.group(1), *review_counts(content))


RECHECK = Path('.ai/reviews/recheck.md')
# Since the reviewed commit a re-check allows only workflow records (pending accepted fix
# tasks included): the code Codex re-checks must still be the code it reviewed.
RECHECK_RECORDS = TRIAGE_RECORDS + ('.ai/reviews/current.md', '.ai/reviews/recheck.md', '.ai/reviews/disputes.md',
                                    '.ai/reviews/fallback-log.md')
RECHECK_HEADER = re.compile(r'\A<!-- Host evidence: re-check of review ([0-9a-f]{64}); rejected rows '
                            r'([0-9a-f]{64}); reviewed HEAD ([0-9a-f]{7,40}); saved [^;>]*\. -->\n')
RECHECK_VERDICTS = ('withdrawn', 'upheld')


def rejected_rows():
    """Rejected BLOCKER/MAJOR findings of the current, verified review as (id, level, evidence),
    from dispositions bound to that review. Returns (review head, rows)."""
    head = review_info_values()[0]
    path = Path('.ai/reviews/dispositions.md')
    text = path.read_text() if path.exists() else ''
    bound = re.search(r'^Review HEAD:\s*([0-9a-f]{7,40})\s*$', text, re.M)
    if not bound or bound.group(1) != head:
        fail('No dispositions for the current review.')
    review = Path('.ai/reviews/current.md').read_text()
    rows = {}
    for match in DISPOSITION_ROW.finditer(text):
        if match.group(1) in rows:
            fail(f'Finding {match.group(1)} has more than one disposition.')
        rows[match.group(1)] = (match.group(2).lower(), table_cell(match.group(3)))
    rejected = [(finding, level, rows[finding][1])
                for level in ('BLOCKER', 'MAJOR') for finding in finding_ids(review, level)
                if finding in rows and rows[finding][0] == 'rejected']
    return head, rejected


def rows_digest(rows):
    """sha256 of the rejected rows the re-check answers: ids and Claude's evidence."""
    canonical = json.dumps([[finding, evidence] for finding, _, evidence in rows],
                           ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def recheck_preflight():
    """The re-check's own preconditions. Returns (head, review digest, rows digest, rows)."""
    head, rows = rejected_rows()
    if not rows:
        fail('Re-check: the current review has no rejected BLOCKER/MAJOR finding.')
    full = git('rev-parse', '--verify', f'{head}^{{commit}}').decode().strip()
    if subprocess.run(['git', 'merge-base', '--is-ancestor', full, 'HEAD'],
                      stderr=subprocess.DEVNULL).returncode != 0:
        fail(f'Re-check: the reviewed commit {head[:12]} is not an ancestor of HEAD.')
    outside = [name for name in changed_since(full) if name not in RECHECK_RECORDS]
    if outside:
        fail('Re-check: the code changed since the reviewed commit: ' + ' '.join(outside[:8])
             + (f' (+{len(outside) - 8} more)' if len(outside) > 8 else ''))
    return head, review_digest(), rows_digest(rows), rows


def recheck_prepare(arguments):
    """Print 'head review_digest rows_digest', then one 'ID<TAB>LEVEL<TAB>evidence' line per
    rejected finding (for the Codex prompt)."""
    head, digest, rows_hash, rows = recheck_preflight()
    print(head, digest, rows_hash)
    for finding, level, evidence in rows:
        print(f"{finding}\t{level}\t{' '.join(evidence.split())}")


def parse_recheck(text, ids):
    """Codex's answer -> {id: (verdict, reason)} for exactly IDS. The answer must be one JSON
    object {"answers": [{"id", "verdict", "reason"}, ...]}; anything missing, duplicated,
    malformed counts as upheld (a re-check can only withdraw explicitly). An answer for an
    unknown finding, or an entry that is not an object with a string id, makes the whole answer
    set untrustworthy: every finding then counts as upheld."""
    answers = {finding: ('upheld', 'no valid answer (counted as upheld)') for finding in ids}
    notes = []
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError:
        data = None
    if not isinstance(data, dict) or set(data) != {'answers'} or not isinstance(data['answers'], list):
        return answers, ['the answer was not one JSON object {"answers": [...]}; every finding counts as upheld']
    stray = [entry.get('id') if isinstance(entry, dict) else entry for entry in data['answers']
             if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or entry['id'] not in answers]
    if stray:
        reason = 'the answer set had an unknown or malformed entry (counted as upheld)'
        return ({finding: ('upheld', reason) for finding in ids},
                [f'answer for an unknown finding or malformed entry: {str(item)[:40]!r}' for item in stray]
                + ['the answer set had unknown or malformed entries; every finding counts as upheld'])
    seen = {}
    for entry in data['answers']:
        finding = entry['id']
        seen[finding] = seen.get(finding, 0) + 1
        valid = (set(entry) == {'id', 'verdict', 'reason'} and entry['verdict'] in RECHECK_VERDICTS
                 and isinstance(entry['reason'], str) and entry['reason'].strip())
        if not valid:
            notes.append(f'{finding}: malformed answer (counted as upheld)')
            answers[finding] = ('upheld', 'malformed answer (counted as upheld)')
        elif seen[finding] == 1:
            answers[finding] = (entry['verdict'], ' '.join(entry['reason'].split())[:1000])
    for finding, count in seen.items():
        if count > 1:
            notes.append(f'{finding}: {count} answers (counted as upheld)')
            answers[finding] = ('upheld', 'duplicate answers (counted as upheld)')
    for finding in ids:
        if finding not in seen:
            notes.append(f'{finding}: no answer (counted as upheld)')
    return answers, notes


def publish_recheck(arguments):
    """Save Codex's re-check as .ai/reviews/recheck.md, bound to the review, the rejected rows
    and the reviewed HEAD it answered; the report digest goes to host state."""
    source, head, digest, rows_hash = arguments
    *current, rows = recheck_preflight()
    if tuple(current) != (head, digest, rows_hash):
        fail('Re-check: the review or the rejected rows changed during the re-check; run it again.')
    answers, notes = parse_recheck(Path(source).read_text(), [finding for finding, _, _ in rows])
    cell = lambda value: ' '.join(value.split()).replace('\\', '\\\\').replace('|', '\\|')
    lines = [f'<!-- Host evidence: re-check of review {digest}; rejected rows {rows_hash}; '
             f'reviewed HEAD {head}; saved {now()}. -->', '',
             f"# Re-check of rejected findings ({os.environ.get('AI_REVIEW_BY') or 'Codex'})", '',
             f'Review digest: {digest}', f'Rejected rows digest: {rows_hash}', f'Reviewed HEAD: {head}', '',
             '| Finding | Level | Answer | Claude\'s evidence | Codex\'s reason |', '| --- | --- | --- | --- | --- |']
    for finding, level, evidence in rows:
        verdict, reason = answers[finding]
        lines.append(f'| {finding} | {level} | {verdict} | {cell(evidence)} | {cell(reason)} |')
    lines += ['', '## Parsing notes', '']
    lines += [f'- {note}' for note in notes] or ['None.']
    machine = json.dumps({finding: {'verdict': answers[finding][0], 'reason': answers[finding][1]}
                          for finding, _, _ in rows}, ensure_ascii=False, sort_keys=True)
    lines += ['', '## Answers (machine-readable)', '', '```json', machine, '```', '']
    content = '\n'.join(lines)
    atomic(RECHECK, content)
    directory = binding_dir()
    directory.mkdir(parents=True, exist_ok=True)
    atomic(directory / f'recheck-{digest}.sha256', hashlib.sha256(content.encode()).hexdigest() + '\n')


def recheck_values():
    """Verify .ai/reviews/recheck.md against host state and the current review/dispositions.
    Returns (head, review digest, rows digest, {id: (verdict, reason)})."""
    if not RECHECK.exists():
        fail('No re-check report.')
    content = RECHECK.read_text()
    header = RECHECK_HEADER.match(content)
    if not header:
        fail('Re-check report has no host evidence; it was not produced by ai-review --recheck.')
    digest, rows_hash, head = header.groups()
    binding = binding_dir() / f'recheck-{digest}.sha256'
    if not binding.exists() or binding.read_text().strip() != hashlib.sha256(content.encode()).hexdigest():
        fail('Re-check report does not match the one ai-review --recheck published.')
    if review_digest() != digest or review_info_values()[0] != head:
        fail('Re-check report belongs to another review.')
    _, rows = rejected_rows()
    if rows_digest(rows) != rows_hash:
        fail('Re-check report answers different rejection evidence; run the re-check again.')
    block = re.search(r'^## Answers \(machine-readable\)\s*```json\n(.*?)\n```', content, re.M | re.S)
    answers = json.loads(block.group(1)) if block else None
    if not isinstance(answers, dict) or set(answers) != {finding for finding, _, _ in rows}:
        fail('Re-check report answers do not cover the rejected findings.')
    return head, digest, rows_hash, {finding: (value['verdict'], value['reason']) for finding, value in answers.items()}


def recheck_verify(arguments):
    """Print one 'ID<TAB>withdrawn|upheld<TAB>reason' line per rejected finding of a verified,
    current re-check; fail when the report is missing, stale or tampered."""
    *_, answers = recheck_values()
    for finding, (verdict, reason) in answers.items():
        print(f'{finding}\t{verdict}\t{reason}')


def recheck_status(arguments):
    """'none' (no verified review with rejected BLOCKER/MAJOR in dispositions bound to it),
    'pending' (rejected findings without a verified, current re-check) or 'verified'."""
    try:
        head = review_info_values()[0]
    except (ValueError, OSError):
        print('none')  # no verified review: it is replaced before anything relies on it
        return
    path = Path('.ai/reviews/dispositions.md')
    bound = re.search(r'^Review HEAD:\s*([0-9a-f]{7,40})\s*$', path.read_text(), re.M) if path.exists() else None
    if not bound or bound.group(1) != head:
        print('none')  # not triaged yet
        return
    _, rows = rejected_rows()
    if not rows:
        print('none')
        return
    try:
        recheck_values()
    except ValueError:
        print('pending')
        return
    print('verified')


DISPUTES = Path('.ai/reviews/disputes.md')
DISPUTE_FIELDS = ('review_digest', 'finding', 'level', 'finding_text', 'evidence', 'answer', 'date')


def disputes_store():
    """Host-side dispute records of the current branch (append-only; agents can't write here)."""
    branch = current_branch()
    if not branch:
        fail('Disputed findings need a branch (detached HEAD).')
    return binding_dir() / f'disputes-{hashlib.sha256(branch.encode()).hexdigest()[:16]}.json'


def fix_rounds_store():
    """Host-side record of this branch's counted triage rounds (commit hashes written by the
    host triage commit), so agent-chosen commit subjects never change the fix round budget."""
    branch = current_branch()
    if not branch:
        fail('Fix rounds need a branch (detached HEAD).')
    return binding_dir() / f'fix-rounds-{hashlib.sha256(branch.encode()).hexdigest()[:16]}.json'


def fix_round_record_valid(record):
    """A legacy bare commit hash, or {commit, review_head, review_digest, blockers, majors}."""
    if isinstance(record, str):
        return re.fullmatch(r'[0-9a-f]{40,64}', record) is not None
    return (isinstance(record, dict)
            and isinstance(record.get('commit'), str) and re.fullmatch(r'[0-9a-f]{40,64}', record['commit']) is not None
            and isinstance(record.get('review_head'), str)
            and re.fullmatch(r'[0-9a-f]{7,40}', record['review_head']) is not None
            and isinstance(record.get('review_digest'), str)
            and re.fullmatch(r'[0-9a-f]{64}', record['review_digest']) is not None
            and all(type(record.get(key)) is int and record[key] >= 0 for key in ('blockers', 'majors')))


def fix_round_commit(record):
    return record if isinstance(record, str) else record['commit']


def fix_round_records():
    path = fix_rounds_store()
    if not path.exists():
        return None
    try:
        records = json.loads(path.read_text())
    except ValueError:
        records = None
    if not isinstance(records, list) or not all(fix_round_record_valid(r) for r in records):
        fail('The host fix round records are unreadable; inspect them before continuing.')
    return records


def fix_round_commits():
    return [fix_round_commit(record) for record in fix_round_records() or []]


def write_fix_rounds(records):
    path = fix_rounds_store()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, json.dumps(records, indent=2) + '\n')


def fix_rounds(arguments):
    """record COMMIT: the host triage commit of one round, with the verified review it triaged
    (head, digest, BLOCKER/MAJOR counts). init BASE: a branch without a host record (legacy)
    starts from its commits whose subject is exactly the host subject (bare hashes, no counts);
    later commits, whatever their subject, never count. count BASE: recorded rounds in
    BASE..HEAD. trend BASE: BLOCKER+MAJOR of the last two reachable rounds and of the current
    review ('x y z'), or fails 'insufficient history'."""
    action = arguments[0]
    if action == 'record':
        commit = git('rev-parse', '--verify', f'{arguments[1]}^{{commit}}').decode().strip()
        if git('log', '-1', '--format=%s', commit).decode().strip() != TRIAGE_COMMIT:
            fail(f'{commit} is not a host triage commit.')
        records = fix_round_records() or []
        if commit not in [fix_round_commit(record) for record in records]:
            head, blockers, majors, _ = review_info_values()
            write_fix_rounds(records + [{'commit': commit, 'review_head': head, 'review_digest': review_digest(),
                                         'blockers': blockers, 'majors': majors}])
        return
    if action not in ('init', 'count', 'trend'):
        fail('Usage: fix-rounds record COMMIT | init BASE | count BASE | trend BASE')
    base = git('rev-parse', '--verify', f'{arguments[1]}^{{commit}}').decode().strip()
    history = git('log', '--format=%H %s', f'{base}..HEAD').decode().splitlines()
    records = fix_round_records()
    if records is None:
        records = [line.split(' ', 1)[0] for line in reversed(history)
                   if line.split(' ', 1)[1:] == [TRIAGE_COMMIT]]
        write_fix_rounds(records)
    reachable = {line.split(' ', 1)[0] for line in history}
    rounds = [record for record in records if fix_round_commit(record) in reachable]
    if action == 'count':
        print(len(rounds))
    elif action == 'trend':
        # Only the last two rounds of this branch, both host-recorded with verified counts (a
        # legacy round or one from an older toolkit never stands in), then the current review.
        last = rounds[-2:]
        head, blockers, majors, _ = review_info_values()
        if len(last) < 2 or not all(isinstance(record, dict) for record in last) \
                or last[-1]['review_head'] == head or last[-1]['review_digest'] == review_digest():
            fail('insufficient history')
        print(*(record['blockers'] + record['majors'] for record in last), blockers + majors)


def dispute_records():
    path = disputes_store()
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text())
    except ValueError:
        records = None
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and set(r) == set(DISPUTE_FIELDS) and all(isinstance(r[k], str) for k in DISPUTE_FIELDS)
            for r in records):
        fail('The host dispute records are unreadable; inspect them before publishing.')
    return records


def inherited_disputes():
    """The dispute file as it is at the merge-base with the run's base (AI_DISPUTES_BASE, set by
    ai-pipeline), or None. Those records came from an earlier PR the human resolved and merged:
    historical, never active on this branch. Without a base nothing is inherited (fails closed)."""
    base = os.environ.get('AI_DISPUTES_BASE')
    if not base:
        return None
    try:
        merge_base = git('merge-base', base, 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        fail(f'No merge-base of {base} and HEAD for the inherited dispute records.')
    try:
        return git('cat-file', 'blob', f'{merge_base}:{DISPUTES}').decode()
    except subprocess.CalledProcessError:
        return None


def render_disputes(records, inherited=None):
    """The file for RECORDS (this branch's host records). Inherited content stays verbatim on
    top and this branch's records follow it, numbered on from the inherited ones."""
    if inherited is None:
        lines = ['# Disputed findings', '',
                 '<!-- Host-written by ai-pipeline from host state; append-only. Never edit: a changed file',
                 'fails verification. A dispute is never resolved automatically; the human resolves it',
                 'at the pull request. -->', '']
        offset = 0
    else:
        lines = [inherited.rstrip('\n'), '',
                 '<!-- Recorded on a later branch; the records above were merged before it. -->', '']
        offset = len(re.findall(r'^## D\d+ — ', inherited, re.M))
    for number, record in enumerate(records, offset + 1):
        lines += [f"## D{number} — {record['finding']} ({record['level']})", '',
                  f"- Review digest: {record['review_digest']}",
                  f"- Recorded: {record['date']}",
                  f"- Original finding: {record['finding_text']}",
                  f"- Claude's evidence: {record['evidence']}",
                  f"- Codex's answer: {record['answer']}", '']
    return '\n'.join(lines)


def expected_disputes(records, inherited):
    """Exact expected file: the inherited copy (or none) until this branch records a dispute."""
    return render_disputes(records, inherited) if records else inherited


def disputes_values():
    """Verified dispute records active on this branch: the file must be exactly the inherited
    copy plus what the host recorded here. Inherited records are not returned."""
    records = dispute_records()
    actual = DISPUTES.read_text() if DISPUTES.exists() else None
    if actual != expected_disputes(records, inherited_disputes()):
        fail('.ai/reviews/disputes.md does not match the dispute records the host wrote; '
             'restore it from Git (records are append-only and never edited).')
    return records


def disputes_verify(arguments):
    """Print the number of verified dispute records; fail when the file was edited or removed."""
    print(len(disputes_values()))


def finding_text(review, level, finding):
    """The finding's own text from the review (its heading or bullet up to the next finding)."""
    body = section(review, f'{level} findings')
    starts = [(match.start(), match.group(1)) for match in FINDING_ID.finditer(body)]
    for number, (start, name) in enumerate(starts):
        if name == finding:
            end = starts[number + 1][0] if number + 1 < len(starts) else len(body)
            return ' '.join(body[start:end].split())[:1500]
    return '(not found in the review)'


def disputes_record(arguments):
    """Append a dispute record for every upheld answer of the verified, current re-check that
    has none yet (keyed by review digest + finding id), then rewrite the file from host state.
    The file may lag behind host state (an interrupted earlier write) but never differ from it.
    Prints the number of records added. `--check` writes nothing and fails unless a real call
    would write nothing either (the armed resume admits only that: no host write while armed)."""
    if arguments not in ([], ['--check']):
        fail('Usage: disputes-record [--check]')
    check = arguments == ['--check']
    records = dispute_records()
    inherited = inherited_disputes()
    actual = DISPUTES.read_text() if DISPUTES.exists() else None
    prefixes = [expected_disputes(records[:count], inherited) for count in range(len(records) + 1)]
    if actual not in prefixes:
        fail('.ai/reviews/disputes.md does not match the dispute records the host wrote; '
             'restore it from Git (records are append-only and never edited).')
    _, digest, _, answers = recheck_values()
    _, rows = rejected_rows()
    review = Path('.ai/reviews/current.md').read_text()
    known = {(record['review_digest'], record['finding']) for record in records}
    # An inherited re-check of a merged PR's review was recorded (and resolved) there.
    known |= {(digest, finding) for finding, digest in re.findall(
        r'^## D\d+ — (\S+) \(\w+\)\n\n- Review digest: ([0-9a-f]+)$', inherited or '', re.M)}
    added = []
    for finding, level, evidence in rows:
        verdict, reason = answers[finding]
        if verdict != 'upheld' or (digest, finding) in known:
            continue
        added.append({'review_digest': digest, 'finding': finding, 'level': level,
                      'finding_text': finding_text(review, level, finding),
                      'evidence': ' '.join(evidence.split()), 'answer': ' '.join(reason.split()),
                      'date': now()})
    records += added
    rendered = render_disputes(records, inherited) if records else actual
    if check:
        if added or rendered != actual:
            fail(f'{len(added)} dispute record(s) to add; .ai/reviews/disputes.md would change.')
        print(0)
        return
    if added:
        path = disputes_store()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, json.dumps(records, ensure_ascii=False, indent=1) + '\n')
    if rendered != actual:
        atomic(DISPUTES, rendered)
    print(len(added))


RECOVER_ACTIONS = ('rerun', 'commit_and_rerun', 'escalate')
# Settings captured with the approved run and restored for its resumes.
RUN_SETTINGS = ('AI_NOTIFY_CMD', 'AI_MODEL', 'AI_REVIEW_MODEL', 'AI_REVIEW_EFFORT', 'AI_RECHECK_EFFORT',
                'AI_AUTO_RECOVER', 'AI_RECOVER_MAX', 'AI_LIMIT_RELAUNCH_MAX', 'AI_LIMIT_RETRY', 'AI_LIMIT_MAX_WAIT',
                'AI_REVIEWER', 'AI_CLAUDE_REVIEW_MODEL', 'AI_CLAUDE_REVIEW_EFFORT', 'AI_DIAGNOSIS_MODEL',
                'AI_SUPERVISE', 'AI_SUPERVISE_PLAN_ROUNDS', 'AI_SUPERVISE_ESCALATE_ROUND',
                'AI_SUPERVISE_ESCALATE_MODEL', 'AI_REVIEW_ROUTE', 'AI_REVIEW_SMALL_LINES', 'AI_REVIEW_RISK_PATHS',
                'AI_REVIEW_RISK_WORDS')


def _no_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate key')
    return dict(pairs)


# Recovery answer scanner. Prose around a decision may hide it inside an enclosing container
# (`Diagnostic: [` ... `]`, or a bracket inside a JSON string fooling a count), and prose has
# unbalanced quotes, so no string-aware count over it is well defined. A container needs an
# opening bracket before the object and a closing one after it, so the prose around the one
# candidate may contain no '{', '}', '[' or ']' at all; inside the object the JSON parser decides.
# The object must start a line and end its last line (inline, quoted or backticked objects are
# prose). No character counting and no string parsing happen outside the object.
_PROSE_BRACKETS = re.compile(r'[{}\[\]]')


def _scan_decision(text):
    """The one line-start object inside bracket-free prose, or None."""
    start = text.find('{')
    if start < 0 or _PROSE_BRACKETS.search(text, 0, start) \
            or text[text.rfind('\n', 0, start) + 1:start].strip():
        return None
    try:
        decision, end = json.JSONDecoder(object_pairs_hook=_no_duplicate_keys).raw_decode(text, start)
    except ValueError:
        return None
    line_end = text.find('\n', end)
    if not isinstance(decision, dict) or _PROSE_BRACKETS.search(text, end) \
            or text[end:len(text) if line_end < 0 else line_end].strip():
        return None
    return decision


def shorten(text, cap):
    """Whitespace collapsed; longer than cap is cut at a sentence end (if that keeps at least
    half of cap), else at a word boundary, else hard, plus '…' (total at most cap)."""
    text = ' '.join(text.split())
    if len(text) <= cap:
        return text
    room = text[:cap - 1]
    ends = [i + 1 for i in range(len(room)) if room[i] in '.!?' and text[i + 1] == ' ']
    if ends and ends[-1] >= cap // 2:
        cut = room[:ends[-1]]
    elif ' ' in room or text[cap - 1] == ' ':
        cut = room[:room.rfind(' ')] if text[cap - 1] != ' ' else room
    else:
        cut = room
    return cut.rstrip() + '…'


RECOVERY_DECISION_FILE = '.ai/local/recovery-decision.txt'


def recover_decision(arguments):
    """Parse the recovery session's verdict: 'action<TAB>reason<TAB>human_action'.
    Only a successful claude exit, a success envelope and exactly ONE complete decision
    object (no duplicate keys; the whole answer, or one line-start object inside prose
    that has no '{', '}', '[' or ']') count. Everything else escalates; when the session
    wrote something, the reason quotes the start of it."""
    log, exit_code = arguments[0], arguments[1]
    escalate = 'escalate\tthe recovery session gave no valid decision\tinspect the stop yourself'
    Path(RECOVERY_DECISION_FILE).unlink(missing_ok=True)
    cut = []

    def clean(value):
        short = shorten(value, 300)
        if short != ' '.join(value.split()):
            cut.append(True)
        return short
    try:
        envelope = json.loads(Path(log).read_text(), object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError):
        envelope = None
    if not isinstance(envelope, dict) or exit_code != '0' or envelope.get('is_error') is not False \
            or envelope.get('subtype') != 'success' or not isinstance(envelope.get('result'), str):
        print(escalate)
        return
    if envelope['result'].strip():
        escalate = ('escalate\t' + shorten('the recovery session gave no valid decision; it wrote: '
                                           + envelope['result'], 300) + '\tinspect the stop yourself')
    # The answer is one JSON object (optionally in a ```json fence), or prose plus one object.
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', envelope['result'].strip())
    try:
        decision = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError:
        decision = _scan_decision(text)
    if not isinstance(decision, dict):
        print(escalate)
        return
    fields = (decision.get('action'), decision.get('reason'), decision.get('human_action', ''))
    if fields[0] not in RECOVER_ACTIONS or not all(isinstance(f, str) for f in fields) \
            or not fields[1].strip():
        print(escalate)
        return
    reason, human_action = clean(fields[1]), clean(fields[2])
    if cut:
        full = lambda value: ' '.join(value.split())[:4000]
        atomic(RECOVERY_DECISION_FILE, f'reason: {full(fields[1])}\nhuman_action: {full(fields[2])}\n')
    print(f'{fields[0]}\t{reason}\t{human_action}')


def committed_matches_worktree(arguments):
    """The HEAD tree holds exactly the bytes on disk (what validation hashed). Catches
    clean/smudge filters and hooks that commit something other than what was validated."""
    entries = [entry for entry in git('ls-tree', '-r', '-z', 'HEAD').split(b'\0') if entry]
    files, expected = [], {}
    for entry in entries:
        meta, raw = entry.split(b'\t', 1)
        mode, _, sha = meta.decode().split()
        name = os.fsdecode(raw)
        if mode == '160000':
            continue  # submodule: its own HEAD is checked by validation
        if mode == '120000':
            if not Path(name).is_symlink():
                fail(f'Committed symlink differs on disk: {name}')
            actual = subprocess.run(['git', 'hash-object', '--no-filters', '--stdin'], check=True,
                                    input=os.fsencode(os.readlink(name)), capture_output=True).stdout.decode().strip()
            if actual != sha:
                fail(f'Committed symlink differs on disk: {name}')
            continue
        if '\n' in name or not Path(name).is_file() or Path(name).is_symlink():
            fail(f'Committed file differs on disk: {name}')
        executable = bool(Path(name).stat().st_mode & 0o111)
        if mode != ('100755' if executable else '100644'):
            fail(f'Committed mode of {name} ({mode}) differs from the validated file on disk.')
        files.append(name)
        expected[name] = sha
    if files:
        hashes = subprocess.run(['git', 'hash-object', '--no-filters', '--stdin-paths'], check=True,
                                input='\n'.join(files).encode(), capture_output=True).stdout.decode().split()
        for name, actual in zip(files, hashes):
            if actual != expected[name]:
                fail(f'Committed content of {name} differs from the validated file on disk.')


DEPS_STAMP = '.ai/local/deps.json'
DEPS_LOCKFILES = ('package-lock.json', 'npm-shrinkwrap.json', 'pnpm-lock.yaml', 'yarn.lock',
                  'bun.lock', 'bun.lockb', 'requirements*.txt', 'poetry.lock', 'uv.lock',
                  'Pipfile.lock', 'Gemfile.lock', 'go.sum', 'Cargo.lock', 'composer.lock')
DEPS_DECLARATION = re.compile(r'^# ?ai-deps-(inputs|outputs):(.*)$', re.M)


def checkout_root():
    return Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve()


def deps_inside(root, token, path):
    """Declared paths stay inside the checkout, also after resolving symlinks."""
    try:
        path.resolve().relative_to(root)
    except ValueError:
        fail(f'Dependency path {token!r} in .ai/ci-setup leaves the checkout.')


def deps_files(root, tokens):
    """Existing files matched by relative paths/globs (directories: every file below)."""
    found = set()
    for token in tokens:
        if os.path.isabs(token) or '..' in Path(token).parts:
            fail(f'Dependency path {token!r} in .ai/ci-setup must be relative and inside the checkout.')
        matches = sorted(root.glob(token)) if re.search(r'[*?[]', token) else [root / token]
        for match in matches:
            if not match.exists():
                continue
            deps_inside(root, token, match)
            below = [match] if not match.is_dir() else \
                [Path(top) / name for top, _, names in os.walk(match) for name in names]
            for path in below:
                deps_inside(root, token, path)
                if path.is_file():
                    found.add(path.relative_to(root).as_posix())
    return sorted(found)


def deps_spec(root):
    """(setup sha, {input path: sha}, [output dirs]) from .ai/ci-setup's declarations."""
    setup = root / '.ai/ci-setup'
    if not setup.is_file():
        fail('Missing .ai/ci-setup.')
    data = setup.read_bytes()
    declared = {'inputs': [], 'outputs': []}
    for kind, value in DEPS_DECLARATION.findall(data.decode(errors='replace')):
        declared[kind] += value.split()
    inputs = deps_files(root, declared['inputs'] or DEPS_LOCKFILES)
    outputs = declared['outputs'] or (['node_modules'] if (root / 'package.json').is_file() else [])
    for token in outputs:
        if os.path.isabs(token) or '..' in Path(token).parts:
            fail(f'Dependency path {token!r} in .ai/ci-setup must be relative and inside the checkout.')
        deps_inside(root, token, root / token)
    return file_sha(data), {path: file_sha((root / path).read_bytes()) for path in inputs}, outputs


def deps_status(arguments):
    """'current' or 'stale <reason>': must the host run .ai/ci-setup? No stamp is always
    stale, even without inputs, so a configured installer runs at least once."""
    root = checkout_root()
    setup, inputs, outputs = deps_spec(root)
    try:
        stamp = json.loads((root / DEPS_STAMP).read_text())
    except FileNotFoundError:
        stamp = None
        reason = 'no dependency stamp (.ai/local/deps.json)'
    except (OSError, ValueError):
        stamp = None
        reason = 'unreadable dependency stamp (.ai/local/deps.json)'
    if stamp is not None:
        recorded = stamp.get('inputs') if isinstance(stamp, dict) else None
        if not isinstance(recorded, dict):
            reason = 'unreadable dependency stamp (.ai/local/deps.json)'
        elif stamp.get('setup') != setup:
            reason = '.ai/ci-setup changed'
        elif recorded != inputs:
            changes = [f'added {p}' for p in sorted(inputs.keys() - recorded.keys())]
            changes += [f'removed {p}' for p in sorted(recorded.keys() - inputs.keys())]
            changes += [f'changed {p}' for p in sorted(inputs.keys() & recorded.keys())
                        if inputs[p] != recorded[p]]
            reason = 'inputs changed: ' + ', '.join(changes)
        else:
            missing = [t for t in outputs if not os.path.lexists(root / t)]
            wrong = [t for t in outputs if t not in missing and not (root / t).is_dir()]
            if missing:
                reason = 'missing output ' + ', '.join(missing)
            elif wrong:
                reason = 'output ' + ', '.join(wrong) + ' is not a directory'
            else:
                reason = None
    print(f'stale {reason}' if reason else 'current')


def deps_record(arguments):
    root = checkout_root()
    setup, inputs, _ = deps_spec(root)
    (root / '.ai/local').mkdir(parents=True, exist_ok=True)
    atomic(root / DEPS_STAMP, json.dumps({'setup': setup, 'inputs': inputs}, indent=2, sort_keys=True) + '\n')


def snapshot_put(digest, *parts):
    for part in parts:
        part = part if isinstance(part, bytes) else str(part).encode()
        digest.update(len(part).to_bytes(8, 'big') + part)


def snapshot_path(digest, name, path, walk=False):
    """Kind, mode and bytes or link target of one path, symlinks never followed; with walk,
    a directory's contents too, read from the filesystem without ignore rules."""
    if path.is_symlink():
        snapshot_put(digest, name, b'link', os.fsencode(os.readlink(path)))
    elif path.is_file():
        snapshot_put(digest, name, b'file', path.stat().st_mode, file_sha(path.read_bytes()))
    elif path.is_dir():
        snapshot_put(digest, name, b'dir', path.stat().st_mode)
        for child in sorted(os.listdir(path)) if walk else ():
            snapshot_path(digest, name + b'/' + os.fsencode(child), path / child, walk)
    else:
        snapshot_put(digest, name, b'missing')


def tree_snapshot(root):
    """One hash over HEAD, the index and every non-ignored path (kind, mode, bytes) outside
    .ai/local/; submodules recursively. Equal before/after a command proves it changed no
    tracked or untracked project file, mode, index entry or commit, also on a dirty tree.
    Ignored paths (installed dependencies) are deliberately not covered. Git lists nothing
    under an uninitialised submodule, so its directory is walked on the filesystem instead;
    a symlink at a submodule path is recorded as a link, never followed.
    The usage-limit relaunch binding (worktree_digest, run-manifest limit-*) relies on this
    covering everything, tracked bookkeeping (.ai/state.md, run-log, handoff, reviews/)
    included: a human edit there during the wait must count, so any new skip here needs that
    binding rethought."""
    digest = hashlib.sha256()
    try:
        head = git('rev-parse', '--verify', '-q', 'HEAD', cwd=root)
    except subprocess.CalledProcessError:
        head = b'no HEAD'
    snapshot_put(digest, b'head', head, b'index', git('diff', '--cached', '--binary', cwd=root))
    gitlinks = set()
    for entry in git('ls-files', '--stage', '-z', cwd=root).split(b'\0'):
        if entry.startswith(b'160000 '):
            gitlinks.add(entry.split(b'\t', 1)[1])
    listed = git('ls-files', '--cached', '--others', '--exclude-standard', '-z', cwd=root)
    for raw in sorted({entry for entry in listed.split(b'\0') if entry}):
        name = raw.rstrip(b'/')
        if name == b'.ai/local' or name.startswith(b'.ai/local/'):
            continue
        path = Path(root) / os.fsdecode(name)
        if name in gitlinks or raw.endswith(b'/'):  # submodule or untracked nested repository
            if path.is_dir() and not path.is_symlink() and (path / '.git').exists():
                snapshot_put(digest, name, b'repo', tree_snapshot(path))
                continue
            snapshot_put(digest, name, b'uninitialised')
            snapshot_path(digest, name, path, walk=True)
        else:
            snapshot_path(digest, name, path)
    return digest.hexdigest()


# The tree a usage-limit relaunch resumes: deliberately the same digest, never a second one.
worktree_digest = tree_snapshot


def finish_summary(arguments):
    """The final notification: what was delivered and the human's todo list."""
    url, reviews, unresolved = arguments[0], arguments[1], arguments[2] == '1'
    blocks = tasks()
    done = sum(task['status'] == 'DONE' for task in blocks)
    handoff = Path('.ai/handoff.md').read_text() if Path('.ai/handoff.md').exists() else ''
    needs_you, automated, legacy = manual_testing(handoff)
    steps = [line for line in needs_you.splitlines() if BULLET.match(line)]
    steps = [line for line in steps if legacy or not NONE_TEXT.match(BULLET_PREFIX.sub('', line).strip())]
    checks = sum(bool(BULLET.match(line)) for line in automated.splitlines())
    extra = [re.sub(r'^\s*(\d+[.)]|[-*])\s+(\[ \]\s*)?', '', line).strip()
             for line in section(handoff, 'Human todos').splitlines()
             if re.match(r'^\s*(\d+[.)]|[-*])\s+\S', line)]
    extra = [item for item in extra if not NONE_TEXT.match(item)]
    try:
        _, blockers, majors, minors = review_info_values()
        review = f'Codex review: BLOCKER {blockers}, MAJOR {majors}, MINOR {minors} ({reviews} round(s))'
    except (ValueError, OSError):
        review = f'Codex review rounds: {reviews}'
    todos = []
    try:
        disputes = len(disputes_values())
    except (ValueError, OSError):
        disputes = 0
    if disputes:
        todos.append(f'Resolve {disputes} disputed finding(s) at the PR (Codex upheld what Claude rejected)')
    if unresolved:
        todos.append('Decide the unresolved review findings (draft PR, see dispositions)')
    if steps:
        todos.append(f'Test: {len(steps)} manual step(s) in the PR')
    elif legacy:
        todos.append('Test the change (no manual steps were written)')
    else:
        todos.append(f'Nothing to test by hand ({checks} automated checks in the PR)')
    todos.append('Merge the PR')
    todos += extra[:10]
    if len(extra) > 10:
        todos.append(f'...and {len(extra) - 10} more under "Human todos" in .ai/handoff.md')
    lines = [f'🏁 FINISHED: all {done}/{len(blocks)} tasks done and validated. {review}.', f'PR: {url}', 'Your todos:']
    lines += [f'{n}. {todo[:200]}' for n, todo in enumerate(todos, 1)]
    print('\n'.join(lines))


PLAN_REVIEW = Path('.ai/reviews/plan.md')
# Workflow records that change without changing what the plan review judged.
PLAN_REVIEW_SUBJECT = 'chore(ai): record plan review'
PLAN_BOOKKEEPING = ('.ai/reviews/', '.ai/state.md', '.ai/run-log.md', '.ai/handoff.md')


def plan_digest():
    """Digest of the committed tree the plan review judged: spec, plan, tasks, source,
    validation and prompts (the review reads all of them), minus workflow bookkeeping."""
    entries = git('ls-tree', '-r', '-z', 'HEAD').split(b'\0')
    kept = [entry for entry in entries if entry and not
            entry.split(b'\t', 1)[1].decode(errors='replace').startswith(PLAN_BOOKKEEPING)]
    return hashlib.sha256(b'\0'.join(kept)).hexdigest()


def publish_plan_review(arguments):
    """Save Codex's plan review, bound to the exact spec/plan/tasks it reviewed."""
    content = Path(arguments[0]).read_text()
    error = review_format_error('plan', content)
    if error:
        fail(f'{error.rstrip(".")}; inspect the local report.')
    # HEAD in the header: a review after a revision commit is always a new report (own round),
    # even when the plan digest and the reviewer's text repeat within the same second.
    head = git('rev-parse', 'HEAD').decode().strip()
    content = f'<!-- Plan review of plan digest {arguments[1]}; HEAD {head}; saved {now()}. -->\n\n' + \
        reviewed_by_line() + reviewer_label() + content
    atomic(PLAN_REVIEW, content)
    # Host-side binding, like implementation reviews: an edited report is not a review.
    directory = binding_dir()
    directory.mkdir(parents=True, exist_ok=True)
    atomic(directory / f'plan-{arguments[1]}.sha256', hashlib.sha256(content.encode()).hexdigest() + '\n')


def plan_review_info(arguments):
    """Print 'current|stale BLOCKER MAJOR MINOR' for the saved plan review."""
    if not PLAN_REVIEW.exists():
        fail('No plan review yet.')
    content = PLAN_REVIEW.read_text()
    reviewed = re.search(r'Plan review of plan digest ([0-9a-f]{64});', content)
    binding = binding_dir() / f'plan-{reviewed.group(1)}.sha256' if reviewed else None
    if not binding or not binding.exists() or \
            binding.read_text().strip() != hashlib.sha256(content.encode()).hexdigest():
        fail('Plan review does not match the report ai-review published; Codex must review again.')
    print('current' if reviewed.group(1) == plan_digest() else 'stale', *review_counts(content))


def verified_plan_review(content):
    """(plan digest, counts) when `content` is a plan review exactly as ai-review published it
    (host binding of its plan digest), else None."""
    reviewed = re.search(r'Plan review of plan digest ([0-9a-f]{64});', content)
    binding = binding_dir() / f'plan-{reviewed.group(1)}.sha256' if reviewed else None
    if not binding or not binding.exists() or \
            binding.read_text().strip() != hashlib.sha256(content.encode()).hexdigest():
        return None
    return reviewed.group(1), review_counts(content)


def report_digest(content):
    return hashlib.sha256(content.encode()).hexdigest()


def plan_rounds_store():
    """Host-side plan-review round records of the current branch (agents can't write here)."""
    branch = current_branch()
    if not branch:
        fail('Plan review rounds need a branch (detached HEAD).')
    return binding_dir() / f'plan-rounds-{hashlib.sha256(branch.encode()).hexdigest()[:16]}.json'


def plan_round_records():
    path = plan_rounds_store()
    if not path.exists():
        return None
    try:
        records = json.loads(path.read_text())
    except ValueError:
        records = None
    keys = {'commit', 'report_digest', 'plan_digest', 'blockers', 'majors', 'minors'}
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and set(r) == keys and isinstance(r['commit'], str)
            and re.fullmatch(r'[0-9a-f]{40,64}', r['commit'])
            and re.fullmatch(r'[0-9a-f]{64}', str(r['report_digest'])) for r in records):
        fail('The host plan round records are unreadable; inspect them before continuing.')
    return records


def write_plan_rounds(records):
    path = plan_rounds_store()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, json.dumps(records, indent=2) + '\n')


def plan_round_entry(commit):
    """The record for a host plan-review commit, or None when its plan.md does not verify."""
    content = committed_file(commit, str(PLAN_REVIEW))
    verified = verified_plan_review(content)
    if not verified:
        return None
    blockers, majors, minors = verified[1]
    return {'commit': commit, 'report_digest': report_digest(content), 'plan_digest': verified[0],
            'blockers': blockers, 'majors': majors, 'minors': minors}


def reachable_plan_rounds(base):
    """(base, commits in BASE..HEAD oldest first, all records, records in BASE..HEAD). A store
    that does not exist yet is initialised once from the exact-subject commits in BASE..HEAD
    that changed plan.md; that can only raise the round number (a stricter requirement)."""
    base = git('rev-parse', '--verify', f'{base}^{{commit}}').decode().strip()
    history = git('log', '--reverse', '--format=%H%x00%s', f'{base}..HEAD').decode().splitlines()
    commits = [line.split('\0', 1) for line in history if '\0' in line]
    records = plan_round_records()
    if records is None:
        records = []
        for sha, subject in commits:
            if subject == PLAN_REVIEW_SUBJECT and str(PLAN_REVIEW) in git(
                    'diff-tree', '--no-commit-id', '--name-only', '-r', '--root', sha).decode().split('\n'):
                entry = plan_round_entry(sha)
                if entry and all(r['report_digest'] != entry['report_digest'] for r in records):
                    records.append(entry)
        write_plan_rounds(records)
    reachable = {sha for sha, _ in commits}
    return base, commits, records, [r for r in records if r['commit'] in reachable]


def plan_rounds_record(base, commit):
    base, commits, records, reachable = reachable_plan_rounds(base)
    commit = git('rev-parse', '--verify', f'{commit}^{{commit}}').decode().strip()
    if dict(commits).get(commit) != PLAN_REVIEW_SUBJECT:
        fail(f'{commit} is not a host plan review commit in the review range.')
    entry = plan_round_entry(commit)
    if not entry:
        fail(f'The plan review in {commit} does not match the report ai-review published.')
    if all(r['report_digest'] != entry['report_digest'] for r in reachable):
        write_plan_rounds(records + [entry])


def plan_rounds_sync(base):
    """Crash window between the review's host commit and its record: record the newest host
    commit holding the current verified plan.md, when that report has no record yet."""
    base, commits, records, reachable = reachable_plan_rounds(base)
    content = PLAN_REVIEW.read_text() if PLAN_REVIEW.exists() else ''
    if not verified_plan_review(content) or any(
            r['report_digest'] == report_digest(content) for r in reachable):
        return
    for sha, subject in reversed(commits):
        if subject == PLAN_REVIEW_SUBJECT and committed_file(sha, str(PLAN_REVIEW)) == content:
            plan_rounds_record(base, sha)
            return


def plan_round_current(base):
    """(n, report digest) of the current plan review; it must be the last recorded round."""
    reachable = reachable_plan_rounds(base)[3]
    content = PLAN_REVIEW.read_text() if PLAN_REVIEW.exists() else ''
    if not reachable or reachable[-1]['report_digest'] != report_digest(content):
        fail('The current plan review is not the last recorded round; run ai-review --plan.')
    return len(reachable), reachable[-1]['report_digest']


def plan_rounds(arguments):
    """record BASE COMMIT | sync BASE | count BASE | current BASE: this branch's plan-review
    rounds, counted only when their host commit is in BASE..HEAD."""
    action = arguments[0] if arguments else ''
    if action == 'record' and len(arguments) == 3:
        plan_rounds_record(arguments[1], arguments[2])
    elif action == 'sync' and len(arguments) == 2:
        plan_rounds_sync(arguments[1])
    elif action == 'count' and len(arguments) == 2:
        print(len(reachable_plan_rounds(arguments[1])[3]))
    elif action == 'current' and len(arguments) == 2:
        print(*plan_round_current(arguments[1]))
    else:
        fail('Usage: plan-rounds record BASE COMMIT | sync BASE | count BASE | current BASE')


PLAN_DISPOSITIONS = '.ai/reviews/plan-dispositions.md'
PLAN_SECTION = re.compile(r'^## Plan review round (\d+) \(report ([0-9a-f]{64})\)[ \t]*$', re.M)
PLAN_DISPOSITION_ROW = re.compile(
    r'^\|[ \t]*' + FINDING_CELL + r'[ \t]*\|[ \t]*(accepted|rejected|needs-human)[ \t]*\|'
    r'[ \t]*' + TABLE_CELL + r'[ \t]*\|[ \t]*' + TABLE_CELL + r'[ \t]*\|', re.M | re.I)


def plan_history(arguments):
    """plan-history BASE [--count | --include-current]: the plan-review rounds before the current
    one (--include-current: and the current one, for the review that follows its revision), each
    with its BLOCKER/MAJOR findings (from the committed plan.md at the record) and the disposition
    per finding from that round's plan-dispositions section at HEAD. Context only, never
    authority: nothing here may approve, count or skip anything. Reads no implementation review."""
    if not arguments or len(arguments) > 2 or \
            (len(arguments) == 2 and arguments[1] not in ('--count', '--include-current')):
        fail('Usage: plan-history BASE [--count | --include-current]')
    reachable = reachable_plan_rounds(arguments[0])[3]
    content = PLAN_REVIEW.read_text() if PLAN_REVIEW.exists() else ''
    earlier = reachable[:-1] if reachable and reachable[-1]['report_digest'] == report_digest(content) \
        and arguments[1:] != ['--include-current'] else reachable
    if arguments[1:] == ['--count']:
        print(len(earlier))
        return
    text = committed_file('HEAD', PLAN_DISPOSITIONS)
    marks = list(PLAN_SECTION.finditer(text))
    sections = {m.group(2): text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)]
                for i, m in reversed(list(enumerate(marks)))}
    rounds = []
    for record in earlier:
        review = committed_file(record['commit'], str(PLAN_REVIEW))
        findings = []
        for level in ('BLOCKER', 'MAJOR'):
            body = section(review, f'{level} findings')
            seen = set()
            for match in FINDING_ID.finditer(body):
                if match.group(1) not in seen:
                    seen.add(match.group(1))
                    findings.append((match.group(1), level, finding_title(body, match)))
        body = sections.get(record['report_digest'])
        rows = None if body is None else {m.group(1): (m.group(2).lower(), table_cell(m.group(4)))
                                          for m in PLAN_DISPOSITION_ROW.finditer(body)}
        rounds.append({'head': record['commit'], 'findings': findings, 'rows': rows})
    if rounds:
        print(render_rounds(rounds, title='## Previous plan review rounds', missing='no revision recorded'))


# Files a plan revision may change (R1): the plan records and runner bookkeeping.
PLAN_REVISION_RECORDS = ('.ai/project-spec.md', '.ai/current-plan.md', '.ai/tasks.md', PLAN_DISPOSITIONS,
                         '.ai/handoff.md', '.ai/state.md', '.ai/run-log.md')
PLAN_DISPOSITIONS_PREAMBLE = """# Plan review dispositions (Claude)

<!-- The host appends one section per plan-review round; fill only the last one and never edit
earlier sections or .ai/reviews/plan.md. One row per BLOCKER/MAJOR finding of that round's plan
review (MINOR optional), the finding ID alone in the first cell, e.g. "| P1 | accepted | evidence | T012 |".
Disposition: accepted (Task: the new TODO task IDs that answer it),
rejected (concrete evidence) or needs-human (the question for the human in the Evidence column).
From plan-review round 3 on, the section also needs a line starting with "Convergence:". -->
"""
PLAN_REVIEW_HEAD = re.compile(r'^Plan review HEAD: ([0-9a-f]{40})[ \t]*$', re.M)
QUESTION_CAP = 300
QUESTION_LIMIT = 3


def plan_section_heading(number, digest):
    return f'## Plan review round {number} (report {digest})'


def plan_section_opened(text, number, digest):
    """TEXT with the host-written section for this round appended, or None when its last
    section already is that header."""
    heading = plan_section_heading(number, digest)
    marks = list(PLAN_SECTION.finditer(text))
    if marks and marks[-1].group(0).rstrip() == heading:
        return None
    if any(mark.group(2) == digest for mark in marks):
        fail(f'{PLAN_DISPOSITIONS} has a section for plan review round {number} that is not the last; '
             'inspect it before revising.')
    head = git('rev-parse', 'HEAD').decode().strip()
    return text.rstrip('\n') + f'\n\n{heading}\n\nPlan review HEAD: {head}\n\n' \
        '| Finding | Disposition | Evidence / reason | Task |\n| --- | --- | --- | --- |\n'


def start_plan_dispositions(arguments):
    """Append the host-written section for the current plan-review round (idempotent: a resume
    whose last section already is that header adds nothing). --pending: exit 0 only when the
    file differs from HEAD by exactly that host section (a crash between writing it and its
    commit, before any session ran), so the resume may commit it."""
    pending = arguments[1:] == ['--pending']
    if len(arguments) != (2 if pending else 1):
        fail('Usage: start-plan-dispositions BASE [--pending]')
    number, digest = plan_round_current(arguments[0])
    path = Path(PLAN_DISPOSITIONS)
    if pending:
        in_head = subprocess.run(['git', 'cat-file', '-e', f'HEAD:{PLAN_DISPOSITIONS}'],
                                 stderr=subprocess.DEVNULL).returncode == 0
        expected = plan_section_opened(committed_file('HEAD', PLAN_DISPOSITIONS) if in_head
                                       else PLAN_DISPOSITIONS_PREAMBLE, number, digest)
        if expected is None or not path.is_file() or path.read_text() != expected:
            fail(f'{PLAN_DISPOSITIONS} is not just the uncommitted host section header.')
        return
    text = plan_section_opened(path.read_text() if path.exists() else PLAN_DISPOSITIONS_PREAMBLE, number, digest)
    if text is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, text)


def plan_text_above(start, heading):
    """What must stand above the round's section: START's text above the same header, else
    START's whole file, else (no file at START) the host preamble."""
    if subprocess.run(['git', 'cat-file', '-e', f'{start}:{PLAN_DISPOSITIONS}'],
                      stderr=subprocess.DEVNULL).returncode != 0:
        return PLAN_DISPOSITIONS_PREAMBLE
    old = committed_file(start, PLAN_DISPOSITIONS)
    same = [mark for mark in PLAN_SECTION.finditer(old) if mark.group(0).rstrip() == heading]
    return old[:same[0].start()] if same else old


def task_statuses(text):
    return {block['id']: next((line.split(':', 1)[1].strip() for line in block['lines']
                               if line.startswith('Status:')), '') for block in task_blocks(text)}


def bounded_questions(questions):
    """At most three questions, each on one line of at most 300 characters, plus a pointer to the rest."""
    lines = [shorten(re.sub(r'<br\s*/?>', ' ', question, flags=re.I), QUESTION_CAP)
             for question in questions[:QUESTION_LIMIT]]
    if len(questions) > QUESTION_LIMIT:
        lines.append(f'(+{len(questions) - QUESTION_LIMIT} more in {PLAN_DISPOSITIONS})')
    return '\n'.join(lines)


def plan_dispositions_check(arguments):
    """plan-dispositions-check --since START --base BASE [--fresh] [--questions]: validate ONLY
    the current plan-review round's section (contract in .ai/current-plan.md). Prints
    'accepted=a rejected=r needs_human=h', or with --questions the bounded needs-human questions.
    With --fresh (right after the revision), accepted findings must point to TODO tasks, every
    task that existed at START keeps its status and every new task is TODO."""
    options, flags, rest = {}, set(), list(arguments)
    while rest:
        name = rest.pop(0)
        if name in ('--since', '--base') and rest:
            options[name] = rest.pop(0)
        elif name in ('--fresh', '--questions'):
            flags.add(name)
        else:
            fail('Usage: plan-dispositions-check --since START --base BASE [--fresh] [--questions]')
    if set(options) != {'--since', '--base'}:
        fail('Usage: plan-dispositions-check --since START --base BASE [--fresh] [--questions]')
    start = git('rev-parse', '--verify', f"{options['--since']}^{{commit}}").decode().strip()
    if subprocess.run(['git', 'merge-base', '--is-ancestor', start, 'HEAD'],
                      stderr=subprocess.DEVNULL).returncode != 0:
        fail(f'{start[:12]} is not an ancestor of HEAD (history rewritten?).')
    number, digest = plan_round_current(options['--base'])
    review = PLAN_REVIEW.read_text()
    if not verified_plan_review(review):
        fail('Plan review does not match the report ai-review published; Codex must review again.')
    path = Path(PLAN_DISPOSITIONS)
    if not path.exists():
        fail(f'No {PLAN_DISPOSITIONS} for plan review round {number}.')
    text = path.read_text()
    heading = plan_section_heading(number, digest)
    marks = list(PLAN_SECTION.finditer(text))
    own = [mark for mark in marks if mark.group(2) == digest]
    if not own:
        fail(f'{PLAN_DISPOSITIONS} has no section for plan review round {number}.')
    if len(own) > 1:
        fail(f'{PLAN_DISPOSITIONS} has {len(own)} headers for plan review round {number}; keep only the host one.')
    mark = own[0]
    if mark.group(0).rstrip() != heading:
        fail(f'The section header for plan review round {number} was changed; it must read: {heading}')
    if mark is not marks[-1]:
        fail(f'The section for plan review round {number} must be the last section.')
    if text[:mark.start()].rstrip('\n') != plan_text_above(start, heading).rstrip('\n'):
        fail(f'Text above the round {number} section changed: earlier sections and the preamble are read-only.')
    body = re.sub(r'<!--.*?-->', '', text[mark.end():], flags=re.S)
    heads = PLAN_REVIEW_HEAD.findall(body)
    if len(heads) != 1 or subprocess.run(['git', 'merge-base', '--is-ancestor', heads[0], 'HEAD'],
                                         stderr=subprocess.DEVNULL).returncode != 0:
        fail(f'The round {number} section needs its host "Plan review HEAD:" line.')
    required = finding_ids(review, 'BLOCKER') + finding_ids(review, 'MAJOR')
    known = set(required + finding_ids(review, 'MINOR'))
    rows = {}
    for row in PLAN_DISPOSITION_ROW.finditer(body):
        finding = row.group(1)
        if finding not in known:
            fail(f'Row for {finding}, which is not a finding of plan review round {number}.')
        if finding in rows:
            fail(f'Finding {finding} has more than one row in the round {number} section.')
        rows[finding] = (row.group(2).lower(), table_cell(row.group(3)), table_cell(row.group(4)))
    for finding in required:
        if finding not in rows:
            fail(f'Finding {finding} has no row in the round {number} section.'
                 + unmatched_cell_hint(body, finding, PLAN_DISPOSITION_ROW))
    queue = {task['id']: task['status'] for task in tasks()}
    counts = {'accepted': 0, 'rejected': 0, 'needs-human': 0}
    questions = []
    for finding, (disposition, evidence, task_ref) in rows.items():
        counts[disposition] += 1
        if disposition == 'accepted':
            refs = list(dict.fromkeys(re.findall(r'T\d{3,}', task_ref)))
            if not refs:
                fail(f'Accepted finding {finding} needs the task ID that answers it.')
            unknown = [ref for ref in refs if ref not in queue]
            if unknown:
                fail(f'Accepted finding {finding} references unknown task {unknown[0]}.')
            done = [ref for ref in refs if queue[ref] != 'TODO']
            if '--fresh' in flags and done:
                fail(f'Accepted finding {finding} must reference TODO tasks; {done[0]} is {queue[done[0]]}.')
        elif disposition == 'rejected':
            if len(evidence.strip()) < 15:
                fail(f'Rejected finding {finding} needs concrete evidence.')
        elif len(evidence.strip()) < 15:
            fail(f'needs-human finding {finding} needs the question for the human.')
        else:
            questions.append(f'{finding}: {evidence.strip()}')
    if number >= 3 and not CONVERGENCE_LINE.search(body):
        fail(f'Plan review round {number} needs a Convergence: line in its section.')
    if '--fresh' in flags:
        before = task_statuses(committed_file(start, '.ai/tasks.md'))
        for task_id, status in before.items():
            if task_id not in queue:
                fail(f'Task {task_id} was removed; a plan revision keeps existing tasks.')
            if queue[task_id] != status:
                fail(f'Task {task_id} changed status from {status} to {queue[task_id]}; '
                     'a plan revision never changes task status.')
        for task_id, status in queue.items():
            if task_id not in before and status != 'TODO':
                fail(f'New task {task_id} must be TODO, not {status}.')
    if '--questions' in flags:
        if questions:
            print(bounded_questions(questions))
        return
    print(f"accepted={counts['accepted']} rejected={counts['rejected']} needs_human={counts['needs-human']}")


def disposition_ruling(arguments):
    """`disposition-ruling triage|plan [--dry-run]` (BR-01): for each BLOCKER/MAJOR finding of the
    current review without a row (the check's own pattern), the one table line whose first cell,
    with `*`, backticks and brackets removed, names that finding and no other finding of the review
    gets the bare ID as its first cell, the rest of the line byte-identical (and only when the line
    then is a row for it). Triage: all of dispositions.md; plan: the last plan-dispositions section.
    Comments, the header and other lines are never touched. Prints `digest <sha256-12 of the
    review>`, then `ID <old cell>` per rewrite; --dry-run writes nothing."""
    dry = arguments[1:] == ['--dry-run']
    mode = arguments[0] if arguments else None
    if mode not in ('triage', 'plan') or len(arguments) != (2 if dry else 1):
        fail('Usage: disposition-ruling triage|plan [--dry-run]')
    review_path, path, row = ((Path('.ai/reviews/current.md'), Path('.ai/reviews/dispositions.md'), DISPOSITION_ROW)
                              if mode == 'triage' else (PLAN_REVIEW, Path(PLAN_DISPOSITIONS), PLAN_DISPOSITION_ROW))
    data = review_path.read_bytes()
    print('digest ' + hashlib.sha256(data).hexdigest()[:12])
    if not path.is_file():
        return
    review, text, start = data.decode(errors='replace'), path.read_text(), 0
    if mode == 'plan':
        marks = list(PLAN_SECTION.finditer(text))
        if not marks:
            return
        start = marks[-1].end()
    region = text[start:]
    # The rows each check already counts: triage reads the whole file, plan its uncommented section.
    counted = region if mode == 'triage' else re.sub(r'<!--.*?-->', '', region, flags=re.S)
    matched = {m.group(1) for m in row.finditer(counted)}
    required = finding_ids(review, 'BLOCKER') + finding_ids(review, 'MAJOR')
    known = set(required + finding_ids(review, 'MINOR'))
    mentions = {f: re.compile(r'(?<![A-Za-z0-9-])' + re.escape(f) + r'(?![A-Za-z0-9])') for f in known}
    comments = [m.span() for m in re.finditer(r'<!--.*?-->', region, re.S)]
    lines, offset, cells = region.splitlines(keepends=True), 0, []
    for index, line in enumerate(lines):
        cell = re.match(r'\|((?:\\.|[^\\|\n])*)\|', line)
        if cell and not any(begin <= offset < end for begin, end in comments):
            plain = re.sub(r'[*`\[\]]', '', cell.group(1))
            cells.append((index, cell, {f for f, mention in mentions.items() if mention.search(plain)}))
        offset += len(line)
    changes = []
    for finding in required:
        found = [(index, cell) for index, cell, named in cells if named == {finding}]
        if finding in matched or len(found) != 1:
            continue
        index, cell = found[0]
        new = f'| {finding} ' + lines[index][cell.end(1):]
        result = row.match(new)
        if result and result.group(1) == finding:
            lines[index] = new
            changes.append(f'{finding} {shorten(cell.group(1), 60)}')
    for change in changes:
        print(change)
    if changes and not dry:
        atomic(path, text[:start] + ''.join(lines))


FLOW_LINE_PHRASES = ('Flow chart updated', 'Flow unchanged')


def flow_line_ruling(arguments):
    """`flow-line-ruling [--dry-run]` (BR-01, A6): the handoff's `## Flow chart` section (the first
    such heading outside code fences) must start with `Flow chart updated` or `Flow unchanged` on the
    line right after the heading. HTML comments count as empty, as in the PR body. When its first
    non-empty line starts with one of them, it moves right under the heading; otherwise `Flow
    unchanged (host ruling)` (the section says "unchanged" or "no flow change") or `Flow chart
    updated (host ruling; see below)` is inserted there. Either way the blank lines before that
    line go (comment lines stay, below it). Prints the moved or inserted line; nothing (and no
    change) for a correct, empty or missing section. --dry-run writes nothing."""
    dry = arguments == ['--dry-run']
    if arguments and not dry:
        fail('Usage: flow-line-ruling [--dry-run]')
    path = Path('.ai/handoff.md')
    if not path.is_file():
        return
    lines, fence, heading = path.read_text().splitlines(keepends=True), False, None
    for index, line in enumerate(lines):
        if re.match(r'\s*(```|~~~)', line):
            fence = not fence
        elif not fence and re.match(r'##\s+Flow chart\s*$', line):
            heading = index
            break
    if heading is None:
        return
    end = next((i for i in range(heading + 1, len(lines)) if re.match(r'##\s', lines[i])), len(lines))
    # The section with each comment blanked character for character, so its lines align.
    body = re.sub(r'<!--.*?-->', lambda m: re.sub(r'[^\n]', ' ', m.group()),
                  ''.join(lines[heading + 1:end]), flags=re.S)
    visible = body.splitlines(keepends=True)
    first = next((i for i, line in enumerate(visible) if line.strip()), None)
    if first is None:
        return
    first += heading + 1
    kept = [line for line in lines[heading + 1:first] if line.strip()]  # comment lines
    if lines[first].startswith(FLOW_LINE_PHRASES):
        if first == heading + 1:
            return
        new, rest = lines[first].rstrip('\n'), lines[first + 1:]
    else:
        new = ('Flow unchanged (host ruling)' if re.search(r'\bunchanged\b|no flow change', body, re.I)
               else 'Flow chart updated (host ruling; see below)')
        rest = lines[first:]
    print(new)
    if not dry:
        head = lines[heading] if lines[heading].endswith('\n') else lines[heading] + '\n'
        atomic(path, ''.join(lines[:heading] + [head, new + '\n'] + kept + rest))


def plan_revision_scope(arguments):
    """Since START, only plan revision records changed (committed or not)."""
    if len(arguments) != 1:
        fail('Usage: plan-revision-scope START')
    records_scope(arguments[0], PLAN_REVISION_RECORDS, 'Plan revision')


# The records a revision session may edit (Edit only, no Write or Bash): the host owns state.md
# and run-log.md and writes the section header itself.
PLAN_REVISION_EDITABLE = ('.ai/project-spec.md', '.ai/current-plan.md', '.ai/tasks.md', PLAN_DISPOSITIONS,
                          '.ai/handoff.md')
PLAN_REVISION_SUBJECT = 'chore(ai): record plan revision'


def plan_revision_allowlist(arguments):
    """--allowedTools entries for the plan revision session, one per line: read tools and Edit
    of the editable plan records. Nothing from .ai/permissions.allow, no Bash, no Write."""
    print('\n'.join(['Read', 'Glob', 'Grep'] + [f'Edit(./{path})' for path in PLAN_REVISION_EDITABLE]))


# The records a planning session may edit (Edit and Write, no Bash). run-log.md is written by
# ai-run's exit handler, never by the session, so only the scope check allows it.
PLAN_EDITABLE = ('.ai/project-spec.md', '.ai/current-plan.md', '.ai/tasks.md', '.ai/state.md',
                 '.ai/handoff.md', '.ai/reviews/dispositions.md')


def plan_allowlist(arguments):
    """--allowedTools entries for the planning session, one per line: read tools and Edit/Write
    of the plan records. Nothing from .ai/permissions.allow, no Bash."""
    entries = ['Read', 'Glob', 'Grep']
    for path in PLAN_EDITABLE:
        entries += [f'Edit(./{path})', f'Write(./{path})']
    print('\n'.join(entries))


def plan_scope(arguments):
    """Since START, only the plan records (and the run log) changed (committed or not)."""
    if len(arguments) != 1:
        fail('Usage: plan-scope START')
    records_scope(arguments[0], PLAN_EDITABLE + ('.ai/run-log.md',), 'Planning')


def plan_keeps_done(arguments):
    """Every task DONE in START's .ai/tasks.md, or in BASELINE (the host's copy of the working-tree
    queue when planning started, committed or not), is still in the working tree, block unchanged.
    A task DONE in both must match the BASELINE block, the queue the session actually started from."""
    if len(arguments) not in (1, 3) or (len(arguments) == 3 and arguments[1] != '--baseline'):
        fail('Usage: plan-keeps-done START [--baseline FILE]')
    start = arguments[0]
    try:
        git('rev-parse', '--verify', '--quiet', f'{start}^{{commit}}')
    except subprocess.CalledProcessError:
        fail(f'Unknown commit: {start}')
    queues = []
    if subprocess.run(['git', 'cat-file', '-e', f'{start}:.ai/tasks.md'],
                      stderr=subprocess.DEVNULL).returncode == 0:
        queues.append(git('show', f'{start}:.ai/tasks.md').decode(errors='replace'))
    if len(arguments) == 3 and Path(arguments[2]).is_file():
        queues.append(Path(arguments[2]).read_text(errors='replace'))
    done = {}
    for before in [task_blocks(text) for text in queues]:
        for task in before:
            # SKIPPED blocks are protected the same way (their Skipped line is authorized as is).
            status = next((line.split(':', 1)[1].strip() for line in task['lines']
                           if line.startswith('Status:') and line.split(':', 1)[1].strip() in FINISHED), None)
            if status:
                done[task['id']] = dict(task, finished=status)
    if not done:
        return
    path = Path('.ai/tasks.md')
    after = {}
    for task in task_blocks(path.read_text()) if path.is_file() else []:
        after.setdefault(task['id'], task)

    def block(task):
        raw = list(task['raw'])
        while raw and not raw[-1].strip():
            raw.pop()
        return [task['heading'], *raw]

    for task in done.values():
        if task['id'] not in after or block(after[task['id']]) != block(task):
            fail(f"{task['finished']} task {task['id']} was changed or removed")


def plan_revisions_store():
    """Host-side plan revision records of the current branch (agents can't write here)."""
    branch = current_branch()
    if not branch:
        fail('Plan revisions need a branch (detached HEAD).')
    return binding_dir() / f'plan-revisions-{hashlib.sha256(branch.encode()).hexdigest()[:16]}.json'


def plan_revision_records():
    """The stored revision records ([] when there is no store yet); unreadable data fails."""
    path = plan_revisions_store()
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text())
    except ValueError:
        records = None
    keys = {'commit', 'report_digest', 'round', 'accepted', 'rejected', 'needs_human', 'questions'}
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and set(r) == keys and isinstance(r['commit'], str)
            and re.fullmatch(r'[0-9a-f]{40,64}', r['commit'])
            and isinstance(r['report_digest'], str) and re.fullmatch(r'[0-9a-f]{64}', r['report_digest'])
            and all(isinstance(r[k], int) and not isinstance(r[k], bool) and r[k] >= 0
                    for k in ('round', 'accepted', 'rejected', 'needs_human'))
            and isinstance(r['questions'], str) for r in records):
        fail('The host plan revision records are unreadable; inspect them before continuing.')
    return records


def is_ancestor(commit, head='HEAD'):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', commit, head],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def plan_revisions_record(arguments):
    """record BASE COMMIT --accepted A --rejected R --needs-human H (questions on stdin): the
    outcome of the host revision commit for the current plan review, in one write."""
    usage = 'Usage: plan-revisions record BASE COMMIT --accepted A --rejected R --needs-human H'
    if len(arguments) != 8 or arguments[2::2] != ['--accepted', '--rejected', '--needs-human'] or \
            not all(re.fullmatch(r'\d{1,4}', value) for value in arguments[3::2]):
        fail(usage)
    base, commit = arguments[:2]
    accepted, rejected, needs_human = (int(value) for value in arguments[3::2])
    commit = git('rev-parse', '--verify', f'{commit}^{{commit}}').decode().strip()
    if git('log', '-1', '--format=%s', commit).decode().strip() != PLAN_REVISION_SUBJECT or not is_ancestor(commit):
        fail(f'{commit} is not a host plan revision commit.')
    number, digest = plan_round_current(base)
    if report_digest(committed_file(commit, str(PLAN_REVIEW))) != digest:
        fail(f'{commit} does not hold the current plan review.')
    # Re-bounded here too: only this short text ever reaches stop messages and notifications.
    lines = [line for line in sys.stdin.read().splitlines() if line.strip()]
    questions = '\n'.join(' '.join(line.split())[:QUESTION_CAP] for line in lines[:QUESTION_LIMIT + 1])
    records = plan_revision_records()
    if any(r['report_digest'] == digest and is_ancestor(r['commit']) for r in records):
        return
    plan_revisions_store().parent.mkdir(parents=True, exist_ok=True)
    atomic(plan_revisions_store(), json.dumps(records + [{
        'commit': commit, 'report_digest': digest, 'round': number, 'accepted': accepted,
        'rejected': rejected, 'needs_human': needs_human, 'questions': questions}], indent=2) + '\n')


def plan_revision_lookup():
    """(record for the verified current plan.md or None, report verified?, last reachable
    record or None). Raises on an unreadable store."""
    reachable = [r for r in plan_revision_records() if is_ancestor(r['commit'])]
    content = PLAN_REVIEW.read_text() if PLAN_REVIEW.exists() else None
    if content is None or not verified_plan_review(content):
        return None, False, reachable[-1] if reachable else None
    digest = report_digest(content)
    return next((r for r in reversed(reachable) if r['report_digest'] == digest), None), True, \
        reachable[-1] if reachable else None


def plan_revisions(arguments):
    """record ... | revised | outcome | decision. revised: exit 0 when the verified current plan
    review already has a revision record, 1 when not. outcome: as revised, and print the record's
    'round accepted rejected needs_human'. decision: exit 0 and print the stored questions
    when that record holds needs-human rows (the human answers, commits and runs ai-review
    --plan, which makes a new report and clears it), 1 when not. Both exit 2 on an unreadable
    store, and when the report does not verify while the last revision asked the human."""
    action = arguments[0] if arguments else ''
    if action == 'record':
        plan_revisions_record(arguments[1:])
        return
    if action not in ('revised', 'outcome', 'decision') or len(arguments) != 1:
        fail('Usage: plan-revisions record BASE COMMIT ... | revised | outcome | decision')
    try:
        record, verified, last = plan_revision_lookup()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(2)
    if not verified:
        if last and last['needs_human'] > 0:
            print('Error: the plan review does not match the report ai-review published, and the last '
                  'plan revision is waiting for your decision; inspect .ai/reviews/plan.md.', file=sys.stderr)
            sys.exit(2)
        sys.exit(1)
    if record is None or (action == 'decision' and record['needs_human'] == 0):
        sys.exit(1)
    if action == 'decision':
        print(record['questions'])
    elif action == 'outcome':
        print(record['round'], record['accepted'], record['rejected'], record['needs_human'])


def revision_queue_repair(arguments):
    """Reorder the uncommitted queue of an interrupted plan revision (as `tasks reorder`) before
    any queue check, only when: .ai/tasks.md differs from HEAD's, only plan revision records are
    dirty, HEAD's queue is valid with no DONE task, and the verified current plan review is not
    revised yet. Otherwise do nothing: the usual checks reject the queue as before."""
    if arguments:
        fail('Usage: revision-queue-repair')
    path = Path('.ai/tasks.md')
    committed = committed_file('HEAD', str(path))
    if not path.is_file() or path.read_text() == committed:
        return
    try:
        records_scope('HEAD', PLAN_REVISION_RECORDS, 'Plan revision')
        before = tasks(committed)
        record, verified, _ = plan_revision_lookup()
    except (ValueError, OSError, subprocess.CalledProcessError):
        return
    if not before or any(task['status'] == 'DONE' for task in before) or not verified or record:
        return
    tasks_reorder()


def plan_stage_verify(start, digest):
    """stage-verify for an open plan-revision stage: 'committed' once a host revision record
    for this plan review names a commit in START..HEAD (the record carries the outcome, so
    the outcome is stored), else 'pending'. Never 'committed' from a commit subject alone."""
    content = PLAN_REVIEW.read_text() if PLAN_REVIEW.exists() else ''
    if not verified_plan_review(content):
        fail('Plan revision stage: the plan review does not match the report ai-review published.')
    if report_digest(content) != digest:
        fail('Plan revision stage: the current plan review is not the one this revision started on.')
    try:
        records_scope(start, PLAN_REVISION_RECORDS, 'Plan revision')
        records = plan_revision_records()
    except ValueError as error:
        fail(f'Plan revision stage: {error}')
    commits = set(git('log', '--format=%H', f'{start}..HEAD').decode().split())
    if not any(r['commit'] in commits and r['report_digest'] == digest for r in records):
        print('pending')
        return
    if git('status', '--porcelain', '--untracked-files=all').strip():
        fail('Plan revision stage: uncommitted changes after the counted revision commit.')
    print('committed')


RISK_TITLE = re.compile(
    r'\bRLS\b|row[- ]level|\bauth(?:n|z|entication|enticate|orization|orisation|orize|orise)?\b|'
    r'permission|\bpolic(?:y|ies)\b|\block(?:s|ing|ed)?\b|lock order|concurren|deadlock|race condition|'
    r'\bdata race\b|migrat|\bdelet(?:e|es|ed|ing|ion)\b|\bdrop\b|irreversib|payment', re.I)


def review_risk(arguments):
    """'high <reason>' when the reviewed work is risky, else 'normal'. Risky: a task on opus
    (the planning rules put security/auth/RLS, locking, data-moving migrations and
    irreversible operations there) or a task title naming such work."""
    try:
        blocks = tasks()
    except (OSError, ValueError):
        print('normal')
        return
    for task in blocks:
        if task['model'].lower().startswith(('opus', 'claude-opus')):
            print(f"high {task['id']} runs on opus")
            return
    for task in blocks:
        match = RISK_TITLE.search(task['title'])
        if match:
            print(f"high {task['id']} title names {match.group(0).lower()}")
            return
    print('normal')


REVIEW_SMALL_LINES = 200
REVIEW_RISK_PATHS = ('*migration*', '*.sql', 'supabase/*', '*auth*', '*polic*', '*rls*', '*security*',
                     '*payment*', '*billing*', '.github/*', '.claude/*', '.ai/permissions.allow',
                     'scripts/lib/common.sh', 'scripts/ai-check')
REVIEW_RISK_WORDS = ('auth', 'RLS', r'row\s+level', 'polic(?:y|ies)', 'grant', 'revoke', r'security\s+definer',
                     'migrat', 'payment', 'billing', 'invoice', 'money', 'price', 'lock', 'mutex', 'concurren',
                     'race', 'transaction', 'deadlock', 'secret', 'token', 'password', 'crypt', 'permission')


def risk_path(path, globs):
    """The first risk glob PATH matches (case-insensitive), or None. Under `.ai/` only globs
    naming `.ai/` count: workflow records are not reviewed code."""
    lowered = path.lower()
    for glob in globs:
        if lowered.startswith('.ai/') and not glob.lower().startswith('.ai/'):
            continue
        if fnmatch.fnmatchcase(lowered, glob.lower()):
            return glob
    return None


def risk_word(base, head, words):
    """(word, path) of the first changed `+`/`-` line outside `.ai/` that names a risk word at a
    word start (case-insensitive; `_` separates words, so `is_auth` names auth), or None."""
    pattern = re.compile(r'(?<![^\W_])(' + '|'.join(f'(?:{word})' for word in words) + ')', re.I)
    diff = git('-c', 'core.quotepath=off', 'diff', '--no-color', '--no-ext-diff', '-U0', base, head,
               '--', '.', ':!.ai').decode(errors='replace')
    path, header = None, False
    for line in diff.split('\n'):
        if line.startswith('diff --git '):
            path, header = None, True
        elif header and line.startswith('--- '):
            path = line[6:] if line.startswith('--- a/') else path
        elif header and line.startswith('+++ '):
            path = line[6:] if line.startswith('+++ b/') else path
        elif line.startswith('@@'):
            header = False
        elif not header and line[:1] in ('+', '-'):
            match = pattern.search(line[1:])
            if match:
                return match.group(1).lower(), path
    return None


def route_fix_rounds(base):
    """Host-recorded fix rounds reachable in BASE..HEAD, without writing. A branch without a host
    record counts none: triage commit subjects are agent-controlled history and never make a
    review eligible for routing (A10); only `fix-rounds init` migrates them."""
    base = git('rev-parse', '--verify', f'{base}^{{commit}}').decode().strip()
    records = fix_round_records()
    if records is None:
        return 0
    reachable = set(git('log', '--format=%H', f'{base}..HEAD').decode().split())
    return sum(1 for record in records if fix_round_commit(record) in reachable)


def queue_at(commit):
    try:
        text = git('show', f'{commit}:.ai/tasks.md').decode()
    except subprocess.CalledProcessError:
        return []
    return tasks(text)


def review_route_reason(mode, base, head):
    route = os.environ.get('AI_REVIEW_ROUTE', '')
    if route == 'codex':
        return 'codex routing off'
    if route not in ('', 'risk'):
        return 'codex invalid AI_REVIEW_ROUTE'
    if mode == 'plan':
        return 'codex plan review'
    if mode == 'recheck':
        return 'codex re-check'
    if mode != 'code':
        raise ValueError(f'unknown mode {mode}')
    head = git('rev-parse', '--verify', f'{head}^{{commit}}').decode().strip()
    if route_fix_rounds(base) == 0:
        return 'codex first full code review'
    check_state_root(git('rev-parse', '--show-toplevel').decode().strip())
    project, branch = project_name(), current_branch() or 'detached'
    rows = [r for r in read_outcomes([outcomes_path()], strict=True)
            if r.get('kind') == 'review' and r.get('mode') == 'code' and r.get('project') == project
            and r.get('branch') == branch and isinstance(r.get('head'), str)
            and re.fullmatch(r'[0-9a-f]{40,64}', r['head'])]
    reachable = [r for r in rows if is_ancestor(r['head'], head)]
    if not any(r.get('reviewer') == 'codex' for r in reachable):
        return 'codex no Codex review of this branch yet'
    last = next((r['head'] for r in reversed(reachable) if r['head'] != head), None)
    if last is None:
        return 'codex no earlier review'
    limit = os.environ.get('AI_REVIEW_SMALL_LINES', '')
    limit = int(limit) if re.fullmatch(r'\d{1,9}', limit) else REVIEW_SMALL_LINES
    lines, binary = 0, False
    for line in git('diff', '--numstat', '--no-ext-diff', last, head, '--', '.', ':!.ai').decode().splitlines():
        added, deleted = line.split('\t')[:2]
        if added == '-' or deleted == '-':
            binary = True
        else:
            lines += int(added) + int(deleted)
    if binary:
        return f'codex fix round diff {lines} lines and a binary file'
    if lines > limit:
        return f'codex fix round diff {lines} lines'
    globs = REVIEW_RISK_PATHS + tuple(os.environ.get('AI_REVIEW_RISK_PATHS', '').split())
    fields = git('diff', '--name-status', '-z', '-M', '--no-ext-diff', last, head).decode(errors='replace').split('\0')
    paths = []
    while len(fields) > 1:
        status, fields = fields[0], fields[1:]
        count = 2 if status[:1] in ('R', 'C') else 1  # a rename or copy names both paths
        paths += fields[:count]
        fields = fields[count:]
    for path in paths:
        if risk_path(path, globs):
            return f'codex risk path {path}'
    words = REVIEW_RISK_WORDS + tuple(re.escape(word) for word in os.environ.get('AI_REVIEW_RISK_WORDS', '').split())
    found = risk_word(last, head, words)
    if found:
        return f'codex risk word {found[0]} in {found[1]}'
    before = {t['id'] for t in queue_at(last) if t['status'] == 'DONE'}
    for task in queue_at(head):
        if task['status'] == 'DONE' and task['id'] not in before \
                and task['model'].lower().startswith(('opus', 'claude-opus')):
            return f"codex {task['id']} runs on opus"
    return f'claude small low-risk fix round ({lines} lines)'


def review_route(arguments):
    """review-route MODE BASE HEAD (BR-14, A9/A10): `codex REASON` or `claude REASON`, from host
    records only (fix-round records, outcome review rows) and the diff since the last
    host-recorded code review; never review commit subjects (`review_rounds`). Exit 0 always;
    any error routes to Codex."""
    if len(arguments) != 3 or arguments[0] not in ('plan', 'code', 'recheck'):
        fail('Usage: review-route plan|code|recheck BASE HEAD')
    try:
        reason = review_route_reason(*arguments)
    except Exception:  # Routing never fails a review: Codex is the safe choice.
        reason = 'codex routing unavailable'
    print(reason)


def codex_limit_reset():
    """The recorded Codex reset (epoch seconds) while it lies in the future, else None. A missing,
    symlinked, unreadable or malformed record counts as no record."""
    path = state_root() / 'codex-limit.json'
    try:
        if path.is_symlink() or not path.is_file():
            return None
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    reset = record.get('reset') if isinstance(record, dict) else None
    if type(reset) is not int or reset <= time.time():
        return None
    return reset


def codex_limit(arguments):
    """codex-limit set RESET | active (BR-14, A11): the host's memory of a Codex usage limit.
    `set` records a future reset (epoch seconds) in the state root; `active` prints it and exits
    0 while it lies ahead, else exits 1 without writing."""
    if arguments[:1] == ['active'] and len(arguments) == 1:
        reset = codex_limit_reset()
        if reset is None:
            sys.exit(1)
        print(reset)
        return
    if arguments[:1] != ['set'] or len(arguments) != 2 or not re.fullmatch(r'[1-9][0-9]{0,11}', arguments[1]) \
            or int(arguments[1]) <= time.time():
        fail('Usage: codex-limit set RESET (epoch seconds in the future) | codex-limit active')
    root = check_state_root(git('rev-parse', '--show-toplevel').decode().strip())
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'codex-limit.json'
    if path.is_symlink():
        path.unlink()
    atomic(path, json.dumps({'reset': int(arguments[1]), 'recorded': now()}) + '\n')


FALLBACK_LOG = Path('.ai/reviews/fallback-log.md')


def fallback_record(arguments):
    """Append one Claude-fallback review to .ai/reviews/fallback-log.md: the list of work
    Codex reviews in one catch-up once it has usage again."""
    mode, model, effort, head, base, reason = arguments
    try:
        branch = git('symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        branch = 'detached'
    cell = lambda value: ' '.join(str(value).split()).replace('\\', '\\\\').replace('|', '\\|') or '-'
    text = FALLBACK_LOG.read_text() if FALLBACK_LOG.exists() else (
        '# Claude fallback reviews (Codex catch-up pending)\n\n'
        'Reviews written by the Claude fallback while Codex could not review. Codex reviews all of\n'
        'this work once in a catch-up review when it has usage again; record the outcome below.\n\n'
        '| Date (UTC) | Mode | Branch | HEAD | Base | Model | Effort | Reason |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- |\n')
    row = '| ' + ' | '.join(cell(x) for x in (now(), mode, branch, head[:12], base[:12], model, effort, reason)) + ' |\n'
    atomic(FALLBACK_LOG, text.rstrip('\n') + '\n' + row)


def outcomes_path():
    return state_root() / 'outcomes.jsonl'


def project_name():
    """Main repository name, the same for all its worktrees (wt/raid-x -> raid-planner)."""
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip())
    return (common.parent if common.name == '.git' else common).name


CATEGORIES = (('security', r'\bRLS\b|row[- ]level|\bauth(?:n|z|entication|orization|orisation)?\b|permission|'
                           r'\bpolic(?:y|ies)\b|secur|secret'),
              ('concurrency', r'\block(?:s|ing|ed)?\b|concurren|deadlock|race condition|\bdata race\b'),
              ('migration', r'migrat|schema|\bdrop\b'),
              ('tests', r'\btests?\b|e2e|playwright'),
              ('docs', r'\bdocs?\b|readme|documentation|rename|copy\b|wording'),
              ('ui', r'\bui\b|page|view|button|layout|style|css|component|screen|tab\b|board'))


def task_category(title):
    for name, pattern in CATEGORIES:
        if re.search(pattern, title, re.I):
            return name
    return 'feature'


def decode_outcome_lines(data):
    """(line index, record) for every valid JSON object line of an outcome log's bytes.
    Each line is decoded on its own: a torn tail can end inside a multibyte character, and a
    whole-file decode raised before any line was parsed. Splitting on b'\\n' only, because
    str.splitlines also splits on U+2028 inside ensure_ascii=False records."""
    records = []
    for line_index, line in enumerate(data.split(b'\n')):
        try:
            record = json.loads(line.decode('utf-8'))
        except ValueError:  # UnicodeDecodeError is a ValueError
            continue
        if isinstance(record, dict):
            records.append((line_index, record))
    return records


def read_outcomes(paths, strict=False):
    """Records in file order; each carries `_at` = (file index, line index), its write position.
    Lenient by default (an unreadable file is skipped: reports and attempt numbering). With
    `strict`, only a missing file counts as empty and any other OSError propagates: a transient
    read failure must not look like "no record yet", or reconcile appends a duplicate."""
    records = []
    for file_index, path in enumerate(paths):
        try:
            data = Path(path).read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            if strict:
                raise
            continue
        for line_index, record in decode_outcome_lines(data):
            record['_at'] = (file_index, line_index)
            records.append(record)
    return records


def fsync_dir(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def make_dirs(directory):
    """Create `directory` with its missing ancestors; returns the ones created, deepest first.
    The caller syncs each one's parent (`sync_created`) once the new entries matter."""
    directory = Path(directory)
    created = []
    for candidate in (directory, *directory.parents):
        if candidate.exists():
            break
        created.append(candidate)
    directory.mkdir(parents=True, exist_ok=True)
    return created


def sync_created(created):
    for directory in created:  # deepest first
        fsync_dir(directory.parent)


def append_outcome(path, record):
    """Append one record as one line; False when the write was short. OSError propagates,
    including one from a file or directory sync: True means the line is durable."""
    path = Path(path)
    created = make_dirs(path.parent)
    # Read-write: the newline guard reads the last byte, and os.pread on O_WRONLY raises EBADF.
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        # The lock makes "tail check, then write" one step for every writer using this helper,
        # in any checkout on the host; os.close in the finally releases it. Known limit: an
        # older installed copy (path.open('a'), no lock) can still interleave until upgraded;
        # its buffered write only leaves a partial line on a crash or a full disk.
        fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.fstat(fd).st_size
        # A torn earlier line (no final newline) must not swallow this record.
        prefix = b'\n' if size > 0 and os.pread(fd, 1, size - 1) != b'\n' else b''
        data = prefix + (json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n').encode()
        # One write call; a short write is a failure, never success. No retry of the remainder:
        # another checkout may have appended in between, and the next append's newline guard
        # isolates the fragment instead.
        if os.write(fd, data) != len(data):
            return False
        os.fsync(fd)
    finally:
        os.close(fd)
    # A file fsync does not persist a new directory entry: sync the log's directory on every
    # append (no race over who created the file) and the parent of every directory created.
    fsync_dir(path.parent)
    sync_created(created)
    return True


def attempt_seq_path():
    """The host-wide attempt counter, beside the log in the same state root."""
    return state_root() / 'attempt-seq'


def next_attempt_seq():
    """Allocate the next attempt sequence number: max(counter, highest recorded seq) + 1,
    persisted before it is returned. Every OSError propagates.
    The lock is the log's (the one every writer takes, append_outcome), not the counter's: the
    counter is replaced atomically, and a lock on a replaced inode no longer excludes later
    lockers. Self-heal: a lost counter continues after the highest seq recorded in the log;
    markers allocated but not yet recorded may then duplicate one, and `_at` breaks that tie.
    Cost: one log read, what `outcome task` already pays for its `attempt` count."""
    path = outcomes_path()
    counter = attempt_seq_path()
    created = make_dirs(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            current = int(counter.read_text().strip())
        except (FileNotFoundError, ValueError):
            current = 0
        recorded = max((r['seq'] for r in read_outcomes([path], strict=True)
                        if r.get('kind') == 'task' and attempt_seq(r) is not None), default=0)
        n = max(current, recorded) + 1
        temp = counter.with_name(counter.name + '.tmp')
        try:
            temp_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                data = str(n).encode()
                if os.write(temp_fd, data) != len(data):
                    raise OSError(f'Short write of attempt counter {temp}')
                os.fsync(temp_fd)
            finally:
                os.close(temp_fd)
            os.replace(temp, counter)
        except BaseException:
            with contextlib.suppress(OSError):
                temp.unlink()
            raise
        fsync_dir(counter.parent)
        sync_created(created)
    finally:
        os.close(fd)  # releases the lock
    return n


def attempt_seq(record):
    """The record's attempt sequence number, or None (missing, a bool, or not an int)."""
    seq = record.get('seq')
    return seq if isinstance(seq, int) and not isinstance(seq, bool) else None


def ordered_attempts(task_rows):
    """{(project, branch, task): [record, ...]} in attempt order: rows without a seq first in
    `_at` order, then the rest by (seq, `_at`). Round 6: every row the current helper writes has
    a seq, so rows without one are pre-upgrade rows, all older than any new row and appended in
    attempt order by one writer per checkout, so file order is exact for them; `_at` orders two
    new rows only when the counter was lost. The sequence is host-wide (one counter per state
    root), so a task's numbers have gaps: an order key, not a count."""
    groups = {}
    for r in task_rows:
        groups.setdefault((r.get('project'), r.get('branch'), r.get('task')), []).append(r)
    for rows in groups.values():
        rows.sort(key=lambda r: (0, 0, r['_at']) if attempt_seq(r) is None else (1, r['seq'], r['_at']))
    return groups


def confirm_recorded(path, attempt_id):
    """True when the log holds a task record with `attempt_id` and the file and its directory
    were synced just now; False when it holds none (a missing log is not created). Other
    OSErrors propagate. A complete write whose file or directory sync failed leaves a readable
    line and a kept marker: this retry must finish the sync before the marker may go. Residual:
    after a failed fsync the kernel may already have marked the dirty pages clean, so this
    persists what is still dirty; it guarantees a successful sync attempt before removal, not
    recovery of dropped data (advisory telemetry).
    Removal rule: a marker is removed only after append_outcome returned True for a record
    carrying its id, or after this returned True. This and a following append_outcome lock
    separately; that is safe because a checkout's attempts are sequential under its lock, so
    no other writer appends that id in between."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)  # a writer mid-append finishes its line first
        chunks = []
        while chunk := os.read(fd, 1 << 16):
            chunks.append(chunk)
        if not any(record.get('kind') == 'task' and record.get('attempt_id') == attempt_id
                   for _, record in decode_outcome_lines(b''.join(chunks))):
            return False
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(path.parent)
    return True


def attempts_dir():
    """Host-side attempt markers, one file per attempt, never overwritten."""
    return binding_dir() / 'attempts'


MARKER_ID = re.compile(r'^[0-9a-f]{16}$')


def marker_path(attempt_id):
    if not isinstance(attempt_id, str) or not MARKER_ID.match(attempt_id):
        raise ValueError(f'Invalid attempt id: {attempt_id!r}')
    return attempts_dir() / f'{attempt_id}.json'


def write_marker(record):
    """Publish one attempt marker: complete, fsynced tmp file, then a hard link to the final
    name (fails if it exists, so a marker is never overwritten), then a directory sync."""
    final = marker_path(record.get('id'))
    created = make_dirs(final.parent)
    sync_created(created)
    temp = final.with_name(final.name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        try:
            data = (json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n').encode()
            if os.write(fd, data) != len(data):
                raise OSError(f'Short write of attempt marker {temp}')
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(temp, final)  # FileExistsError propagates
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()
    fsync_dir(final.parent)
    return final


MARKER_FIELDS = ('id', 'task', 'model', 'project', 'branch', 'started', 'seq', 'pid', 'pid_start')


def read_marker(path):
    """(record, error): the record of a valid marker; the OSError when opening or reading it
    failed (the marker is the only evidence of an unrecorded attempt, so a transient EIO or
    EACCES must never look like garbage); (None, None) for content read completely but not a
    marker. Invalid content may be discarded: our writer links only complete, fsynced files,
    so invalid content under the final name is foreign or corrupt, never a torn marker of ours."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        return None, error
    try:
        record = json.loads(data.decode('utf-8'))
    except ValueError:
        return None, None
    if not isinstance(record, dict) or any(field not in record for field in MARKER_FIELDS) \
            or record['id'] != Path(path).stem or not MARKER_ID.match(str(record['id'])) \
            or not isinstance(record['started'], (int, float)) or isinstance(record['started'], bool) \
            or attempt_seq(record) is None:
        return None, None
    return record, None


def marker_sort_key(entry):
    path, record, _ = entry
    return (1, record['seq'], path.name) if record else (0, 0, path.name)


def list_markers():
    """[(path, record, error)] for every `*.json` marker, oldest attempt first; see read_marker.
    One file's failure never raises; a failing directory listing does (the caller notes it
    and touches nothing)."""
    directory = attempts_dir()
    try:
        with os.scandir(directory) as listing:
            paths = [directory / entry.name for entry in listing if entry.name.endswith('.json')]
    except FileNotFoundError:
        return []
    return sorted(((path, *read_marker(path)) for path in paths), key=marker_sort_key)


def process_start(pid):
    """Field 22 of /proc/PID/stat (start in clock ticks since boot), or None. Read as bytes and
    split after the last ')': the command name can hold spaces, parentheses or non-UTF-8."""
    try:
        return int(Path(f'/proc/{int(pid)}/stat').read_bytes().rsplit(b')', 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return None


class AttemptSeqError(OSError):
    """next_attempt_seq failed inside open_attempt: nothing was printed or published."""


def open_attempt(task, model, pid, out=None):
    """Print a new attempt id, then publish its marker; returns the id.
    Contract (P13): the id reaches the caller BEFORE the marker can exist, so a marker whose id
    the runner lacks is impossible (a failed write to the pipe raises before the link, and
    such a marker would later be logged as a false `crashed`). An id without a marker is
    harmless: the outcome line carries it, remove_marker of a missing file is a no-op, and
    nothing reconciles it. An OSError from write_marker propagates after the print, the
    marker possibly present; `outcome attempt-open` (T003) turns it into a stderr note and
    exit 1, and reconciles leftovers before calling this (this does not reconcile).
    Runner side (T004) keeps every valid printed id whatever the exit status:
      attempt_id=$(ai_helper outcome attempt-open … 2>/dev/null) || true
      [[ "$attempt_id" =~ ^[0-9a-f]{16}$ ]] || attempt_id=
    Residual: a marker whose directory sync failed after the link may not survive a power
    loss; that loses at most a `crashed` record, never produces a false one.
    The attempt's seq is allocated before the print: an OSError from next_attempt_seq
    propagates with nothing printed and nothing published (the attempt runs untracked)."""
    try:
        branch = git('symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        branch = 'detached'
    attempt_id = os.urandom(8).hex()
    record = {'id': attempt_id, 'task': task, 'model': model or 'default', 'project': project_name(),
              'branch': branch, 'started': int(time.time()), 'pid': int(pid),
              'pid_start': process_start(pid)}
    try:
        record['seq'] = next_attempt_seq()
    except OSError as error:
        raise AttemptSeqError(*error.args) from error
    print(attempt_id, file=out or sys.stdout, flush=True)
    write_marker(record)
    return attempt_id


def remove_marker(path):
    path = Path(path)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    with contextlib.suppress(FileNotFoundError):  # no directory: no entry to persist
        fsync_dir(path.parent)


def note(message):
    print(f'Note: {message}', file=sys.stderr)


def runner_alive(record):
    """The marker's runner still runs: its pid exists with the recorded start time (a reused
    pid has another), or with any start time when none was recorded."""
    try:
        pid = int(record['pid'])
    except (TypeError, ValueError):
        return False
    if record['pid_start'] is None:
        return pid > 0 and Path(f'/proc/{pid}').exists()
    start = process_start(pid)
    return start is not None and start == record['pid_start']


def reconcile_marker(log, marker, record, own_pid):
    """Turn one valid marker of a runner that is gone (or of the caller itself) into exactly
    one task record, then remove it. OSError propagates with the marker kept."""
    if runner_alive(record) and record['pid'] != own_pid:
        return  # another runner's attempt in progress
    # A marker of own_pid with a matching start is an earlier, finished attempt of the calling
    # runner whose outcome append failed: attempts are sequential under the checkout lock (P6).
    if confirm_recorded(log, record['id']):
        remove_marker(marker)  # recorded, and its interrupted sync is finished now (P9)
        return
    # Strict: a transient read failure must not number (or duplicate) anything (P10).
    earlier = [r for r in read_outcomes([log], strict=True) if r.get('kind') == 'task'
               and (r.get('project'), r.get('branch'), r.get('task'))
               == (record['project'], record['branch'], record['task'])]
    title = outcome_title(record['task'])
    row = {'time': now(), 'kind': 'task', 'project': record['project'], 'branch': record['branch'],
           'task': record['task'], 'title': title, 'category': task_category(title),
           'model': record['model'] or 'default', 'result': 'crashed', 'attempt': len(earlier) + 1,
           'first_pass': False, 'seconds': None, 'started': record['started'], 'seq': record['seq'],
           'attempt_id': record['id']}
    if not append_outcome(log, row):
        note('could not log the crashed attempt completely; will retry at the next start.')
        return
    remove_marker(marker)
    note(f"logged a crashed attempt of {record['task']} (the runner was killed without its exit handler).")


def reconcile_attempts(own_pid=None):
    """Log every attempt whose runner died without its exit handler as `crashed`, once. Each
    marker is handled on its own and kept on any failure; never raises (best effort at start).
    Removal rule (T009): a readable marker goes only after its record is durably in the log.
    Known limit: a short write of a normal `outcome task --attempt` line keeps its marker, so
    that attempt is logged as `crashed` here (storage was full; the conservative record)."""
    try:
        entries = list_markers()
    except (OSError, ValueError, subprocess.CalledProcessError):
        note('could not list the attempt markers.')
        return
    log = outcomes_path()
    for marker, record, error in entries:
        if error is not None:
            note('could not read an attempt marker; keeping it.')  # transient: retried next start
            continue
        try:
            if record is None:
                remove_marker(marker)  # complete content, but not ours (see read_marker)
                note('discarded an invalid attempt marker.')
                continue
            reconcile_marker(log, marker, record, own_pid)
        except (OSError, ValueError):
            note('could not read or sync the outcome log; keeping the attempt marker.')


def outcome_title(task_id):
    """The task's title; a queue that no longer parses (the outcome of that very stop) falls
    back to a heading scan, then to an empty title, so the attempt is still logged."""
    try:
        return next((t['title'] for t in tasks() if t['id'] == task_id), '')
    except (ValueError, OSError):
        pass
    try:
        for line in Path('.ai/tasks.md').read_text().splitlines():
            heading = re.match(r'^##\s+(T\d{3,})\s+[—-]\s+(.+?)\s*$', line)
            if heading and heading.group(1) == task_id:
                return heading.group(2)
    except OSError:
        pass
    return ''


def recheck_counts(answers, levels):
    """(upheld BLOCKER, upheld MAJOR, withdrawn BLOCKER, withdrawn MAJOR) of a re-check's answers."""
    def count(verdict, level):
        return sum(1 for finding, (answer, _) in answers.items()
                   if answer == verdict and levels.get(finding) == level)
    return (count('upheld', 'BLOCKER'), count('upheld', 'MAJOR'),
            count('withdrawn', 'BLOCKER'), count('withdrawn', 'MAJOR'))


def outcome(arguments):
    """Append one outcome line to the host-side log (outside every checkout).
    task TASK RESULT MODEL SECONDS | review MODE REVIEWER MODEL EFFORT SECONDS [REPORT] [--route REASON]
    | plan_revision ROUND RESULT MODEL SECONDS (not part of outcomes_report)
    | plan RESULT MODEL SECONDS [TASKS] [--revision] (a planning session; done, stopped,
      interrupted or timeout; not part of outcomes_report)
    | catchup BRANCH (the human recorded a Codex catch-up of that branch)
    | gate pass|fail|timeout SECONDS (one host gate run of ai-run; read by gate-seconds,
      not part of outcomes_report)
    | attempt-dir (prints the attempt marker directory)
    | attempt-open TASK MODEL PID (reconciles, then prints a new attempt id and publishes its marker)
    | attempt-reconcile [OWN_PID] (logs dead runners' attempts as crashed; always exit 0)
    `task … --attempt ID` takes seq and started from that attempt's marker and removes the
    marker once the line is durably appended."""
    kind, *rest = arguments
    if kind == 'attempt-dir':
        if rest:
            fail('Usage: outcome attempt-dir')
        print(attempts_dir())
        return
    if kind == 'attempt-reconcile':
        if len(rest) > 1 or (rest and not rest[0].isdigit()):
            fail('Usage: outcome attempt-reconcile [OWN_PID]')
        reconcile_attempts(int(rest[0]) if rest else None)
        return
    if kind == 'attempt-open':
        if len(rest) != 3 or not rest[2].isdigit():
            fail('Usage: outcome attempt-open TASK MODEL PID')
        task_id, model, pid = rest[0], rest[1], int(rest[2])
        reconcile_attempts(pid)
        try:
            open_attempt(task_id, model, pid)
        except AttemptSeqError:
            print('Note: could not allocate the attempt sequence.', file=sys.stderr)
            sys.exit(1)
        except OSError:
            # The id is printed already: the runner keeps it, and its outcome line removes the
            # marker if the link happened (open_attempt, P13).
            print('Note: could not publish the attempt marker.', file=sys.stderr)
            sys.exit(1)
        return
    try:
        branch = git('symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        branch = 'detached'
    path = outcomes_path()
    check_state_root(git('rev-parse', '--show-toplevel').decode().strip())
    record = {'time': now(), 'kind': kind, 'project': project_name(), 'branch': branch}
    marker = None
    if kind == 'task':
        if len(rest) not in (4, 6) or (len(rest) == 6 and rest[4] != '--attempt'):
            fail('Usage: outcome task TASK RESULT MODEL SECONDS [--attempt ID]')
        task_id, result, model, seconds = rest[:4]
        attempt_id = rest[5] if len(rest) == 6 else None
        title = outcome_title(task_id)
        earlier = [r for r in read_outcomes([path]) if r.get('kind') == 'task' and r.get('task') == task_id
                   and r.get('project') == record['project'] and r.get('branch') == branch]
        # `attempt` and `first_pass` are counted at append time and kept for readers of the log;
        # the report no longer reads them (it derives both from the seq order).
        attempt = len(earlier) + 1
        # The attempt's start as the runner measured it (epoch seconds; informational, never an order key).
        started = int(time.time()) - int(seconds)
        seq = None
        if attempt_id is not None:
            marker = marker_path(attempt_id)
            opened, _ = read_marker(marker)
            if opened:
                # The marker's order key and open time: this row, its marker and a `crashed` row
                # reconciled from the same marker agree. Absent or unreadable (P13): fresh seq.
                seq, started = opened['seq'], opened['started']
        if seq is None:
            # A row is never written without seq: one without would sort as a pre-upgrade row,
            # before every real attempt of the task.
            try:
                seq = next_attempt_seq()
            except OSError:
                fail(f'Could not allocate the attempt sequence: {attempt_seq_path()}.')
        record.update(task=task_id, title=title, category=task_category(title), model=model or 'default',
                      result=result, attempt=attempt, first_pass=result == 'done' and attempt == 1,
                      seconds=int(seconds), started=started, seq=seq)
        if attempt_id is not None:
            record['attempt_id'] = attempt_id
    elif kind == 'review':
        route = None
        if '--route' in rest:
            at = rest.index('--route')
            if at != len(rest) - 2:
                fail('Usage: outcome review MODE REVIEWER MODEL EFFORT SECONDS [REPORT] [--route REASON]')
            route = ' '.join(rest[at + 1].split())[:200]
            rest = rest[:at]
        mode, reviewer, model, effort, seconds, *report = rest
        record.update(mode=mode, reviewer=reviewer, model=model or 'default', effort=effort,
                      seconds=int(seconds), head=git('rev-parse', 'HEAD').decode().strip())
        if route:
            record['route'] = route
        if report and mode != 'recheck':
            try:
                counts = review_counts(Path(report[0]).read_text())
                record.update(blocker=counts[0], major=counts[1], minor=counts[2])
            except (OSError, ValueError):
                pass
        elif mode == 'recheck':
            try:
                head, _, _, answers = recheck_values()
                levels = {finding: level for finding, level, _ in rejected_rows()[1]}
                counts = recheck_counts(answers, levels)
                reviewed = git('rev-parse', '--verify', f'{head}^{{commit}}').decode().strip()
                record.update(upheld_blocker=counts[0], upheld_major=counts[1], withdrawn_blocker=counts[2],
                              withdrawn_major=counts[3], reviewed_head=reviewed)
            except (OSError, ValueError, subprocess.CalledProcessError):
                pass
    elif kind == 'plan_revision':
        round_number, result, model, seconds = rest
        record.update(round=int(round_number), result=result, model=model or 'default', seconds=int(seconds))
    elif kind == 'plan':
        revision = '--revision' in rest
        rest = [a for a in rest if a != '--revision']
        if len(rest) not in (3, 4) or rest[0] not in ('done', 'stopped', 'interrupted', 'timeout') \
                or not rest[2].isdigit() or (len(rest) == 4 and not rest[3].isdigit()):
            fail('Usage: outcome plan done|stopped|interrupted|timeout MODEL SECONDS [TASKS] [--revision]')
        record.update(result=rest[0], model=rest[1] or 'default', seconds=int(rest[2]),
                      tasks=int(rest[3]) if len(rest) == 4 else None, revision=revision)
    elif kind == 'catchup':
        if len(rest) != 1 or not rest[0]:
            fail('Usage: outcome catchup BRANCH')
        record['branch'] = rest[0]
    elif kind == 'gate':
        if len(rest) != 2 or rest[0] not in ('pass', 'fail', 'timeout') or not rest[1].isdigit():
            fail('Usage: outcome gate pass|fail|timeout SECONDS')
        record.update(result=rest[0], seconds=int(rest[1]))
    else:
        fail(f'Unknown outcome kind: {kind}')
    try:
        complete = append_outcome(path, record)
    except OSError:
        complete = False
    if not complete:
        fail(f'Could not append the outcome line completely: {path}.')  # the marker stays
    if marker is not None:
        # Only this attempt's marker, only after a durable append. A failed directory sync of
        # the removal is harmless: a resurrected marker's record is found by confirm_recorded.
        with contextlib.suppress(OSError):
            remove_marker(marker)


def gate_seconds(arguments):
    """Prints this project's gate time: the largest seconds among its last 3 passing host gate
    runs (`outcome gate pass`), or 0 without any. Torn or foreign lines are ignored; a missing or
    unreadable log is 0. The log sits in the host state root, which agents cannot write."""
    if arguments:
        fail('Usage: gate-seconds')
    check_state_root(git('rev-parse', '--show-toplevel').decode().strip())
    project = project_name()
    passes = [r['seconds'] for r in read_outcomes([outcomes_path()])
              if r.get('kind') == 'gate' and r.get('result') == 'pass' and r.get('project') == project
              and type(r.get('seconds')) is int and r['seconds'] >= 0]
    print(max(passes[-3:], default=0))


ATTEMPT_NOTE_LIMIT = 600
ATTEMPT_LOG_LIMIT = 256 * 1024
FAILING_CHECK = re.compile(r'^(?:(?:FAIL|ERROR): (.+?)|FAILED ([^\s(]\S*)(?: - .*)?)\s*$')  # not unittest's `FAILED (failures=1)`


def raised_model(model):
    """One tier up from MODEL (BR-03, A7): haiku → sonnet, sonnet → opus; opus, fable and
    unknown names stay; no model → opus."""
    if not model:
        return 'opus'
    lowered = model.lower()
    if 'haiku' in lowered:
        return 'sonnet'
    if 'sonnet' in lowered:
        return 'opus'
    return model


def attempt_note_item(text, limit=ATTEMPT_NOTE_LIMIT):
    """One note item on one line: `|`, backslashes and line breaks become spaces, at most LIMIT."""
    text = ' '.join(re.sub(r'[|\\\r\n\x0b\x0c\x1c-\x1e\x85  ]', ' ', str(text)).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def gate_log_lines():
    """The last ai-check's log lines, read like `stamp outcome` (pinned `.ai/local`, never a
    symlink): only a log that is a regular file directly inside `.ai/local`, at most
    ATTEMPT_LOG_LIMIT bytes from its end. None when there is no such log."""
    root = checkout_root()
    dir_fd = local_dir_fd(root)
    if dir_fd is None:
        return None
    try:
        record = read_record(dir_fd, 'validation.json', STAMP_LIMIT + 1)
        if record is None or len(record[0]) > STAMP_LIMIT:
            return None
        try:
            data = json.loads(record[0])
        except (ValueError, RecursionError):
            return None
        log = data.get('log') if isinstance(data, dict) else None
        if not isinstance(log, str) or not log or '\0' in log:
            return None
        path = Path(log)
        parent = path.parent if path.is_absolute() else Path(root) / path.parent
        if path.name in ('', '.', '..') or os.path.normpath(parent) != os.path.normpath(Path(root) / '.ai/local'):
            return None
        content = read_record(dir_fd, path.name, ATTEMPT_LOG_LIMIT, tail=True)
    finally:
        os.close(dir_fd)
    return None if content is None else content[0].splitlines()


def failing_checks_item():
    lines = gate_log_lines()
    if not lines:
        return None
    names = []
    for line in lines:
        match = FAILING_CHECK.match(line)
        name = match and (match.group(1) or match.group(2))
        if name and name not in names:
            names.append(name)
    if names:
        return 'Failing checks: ' + ', '.join(names[:5]) + '.'
    last = next((line for line in reversed(lines) if line.strip()), None)
    return f'Last gate line: {last.strip()}' if last else None


def result_notes_line(task):
    section = None
    last = None
    for line in task['lines']:
        if line.startswith('### '):
            section = line[4:].strip()
        elif section == 'Result / notes' and line.strip():
            last = line.strip()
    return last


def attempt_info(arguments):
    """attempt-info TASK [BASE_MODEL] (BR-03): line 1 `N MODEL RAISED` for the next attempt of
    TASK on this project and branch, then (from attempt 2) a short failure note, from the host
    outcome log, the last gate log and the queue. Never fails the runner: any read error prints
    `1 <task or base model or -> no` and exits 0."""
    if len(arguments) not in (1, 2) or not re.fullmatch(r'T\d{3,}', arguments[0]):
        fail('Usage: attempt-info TASK [BASE_MODEL]')
    task_id, base = arguments[0], (arguments[1] if len(arguments) == 2 else '')
    known = base
    try:
        task = next((t for t in tasks() if t['id'] == task_id), None)
        known = (task and task['model']) or base
        check_state_root(git('rev-parse', '--show-toplevel').decode().strip())
        try:
            branch = git('symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()
        except subprocess.CalledProcessError:
            branch = 'detached'
        rows = [r for r in read_outcomes([outcomes_path()], strict=True) if r.get('kind') == 'task']
        rows = ordered_attempts(rows).get((project_name(), branch, task_id), [])
    except (ValueError, OSError, subprocess.CalledProcessError, RecursionError):
        print(f"1 {known or '-'} no")
        return
    failures = [r for r in rows if r.get('result') != 'done']
    attempt = len(failures) + 1
    model = raised_model(known) if attempt >= 3 else known
    print(f"{attempt} {model or '-'} {'yes' if model != known else 'no'}")
    if attempt < 2:
        return
    last = failures[-1]
    seconds = last.get('seconds')
    took = f' after {seconds} s' if type(seconds) is int else ''
    items = [f"Attempt {attempt - 1} ended {last.get('result')}{took} on {last.get('model') or 'default'}."]
    try:
        checks = failing_checks_item()
    except (ValueError, OSError, subprocess.CalledProcessError):
        checks = None
    if checks:
        items.append(checks)
    notes = task and result_notes_line(task)
    if notes:
        items.append('Last result line: ' + attempt_note_item(notes, 200))
    room = ATTEMPT_NOTE_LIMIT
    for item in items:
        if room <= 1:
            break
        item = attempt_note_item(item, room)
        print(item)
        room -= len(item) + 1  # the newline between items counts

def outcomes_report(arguments):
    """Summary of the outcome log(s) for tuning the model rules."""
    # Gate runs are runner timing (gate_seconds), not outcomes: a log of only gate lines still
    # reports "No outcomes recorded yet".
    records = [r for r in read_outcomes(arguments or [outcomes_path()]) if r.get('kind') != 'gate']
    if not records:
        print('No outcomes recorded yet (' + ', '.join(str(x) for x in (arguments or [outcomes_path()])) + ').')
        return
    task_rows = [r for r in records if r.get('kind') == 'task']
    ordered = ordered_attempts(task_rows)
    # A task's last attempt in sequence order is its result; a crashed attempt may be appended
    # late; rows without `seq` are pre-upgrade rows in file order. Its time is the sum of its attempts.
    final = {key: rows[-1] for key, rows in ordered.items()}
    first_row = {key: rows[0] for key, rows in ordered.items()}
    spent = {key: sum(r.get('seconds') or 0 for r in rows) for key, rows in ordered.items()}

    def table(title, key):
        groups = {}
        for task_key, r in final.items():
            groups.setdefault(key(r), []).append(task_key)
        lines = [f'## Tasks by {title}', '',
                 f'| {title} | tasks | first-time pass | done | not done | avg attempts | avg minutes |',
                 '| --- | --- | --- | --- | --- | --- | --- |']
        for name in sorted(groups, key=str):
            keys = groups[name]
            count = len(keys)
            first = sum(first_row[k].get('result') == 'done' for k in keys)
            done = sum(final[k].get('result') == 'done' for k in keys)
            attempts = sum(len(ordered[k]) for k in keys) / count
            minutes = sum(spent[k] for k in keys) / count / 60
            lines.append(f'| {name} | {count} | {first}/{count} ({100 * first // count}%) | {done} | '
                         f'{count - done} | {attempts:.1f} | {minutes:.1f} |')
        return lines + ['']

    def attempts_table(title, key):
        groups = {}
        for r in task_rows:
            task_key = (r.get('project'), r.get('branch'), r.get('task'))
            groups.setdefault(key(r, final[task_key]), []).append((r, first_row[task_key] is r))
        lines = [f'## Attempts by {title}', '',
                 f'| {title} | attempts | done | not done | first-time pass | avg minutes |',
                 '| --- | --- | --- | --- | --- | --- |']
        for name in sorted(groups, key=str):
            rows = groups[name]
            done = sum(r.get('result') == 'done' for r, _ in rows)
            starts = [r for r, is_first in rows if is_first]
            first = sum(r.get('result') == 'done' for r in starts)
            rate = f'{first}/{len(starts)} ({100 * first // len(starts)}%)' if starts else '-'
            minutes = sum(r.get('seconds') or 0 for r, _ in rows) / len(rows) / 60
            lines.append(f'| {name} | {len(rows)} | {done} | {len(rows) - done} | {rate} | {minutes:.1f} |')
        return lines + ['']

    lines = ['# Outcomes report', '', f'{len(final)} task(s), {len(task_rows)} attempt(s), '
             f"{sum(r.get('kind') == 'review' for r in records)} review(s).", '']
    if final:
        lines += attempts_table('model', lambda r, last: r.get('model', 'default'))
        lines += table('category', lambda r: r.get('category', 'feature'))
        lines += attempts_table('model and category',
                                lambda r, last: f"{r.get('model', 'default')} / {last.get('category', 'feature')}")
    reviews = [r for r in records if r.get('kind') == 'review']
    rechecks = [r for r in reviews if r.get('mode') == 'recheck']
    plain = [r for r in reviews if r.get('mode') != 'recheck']
    if plain:
        groups = {}
        for r in plain:
            groups.setdefault((r.get('reviewer'), r.get('model'), r.get('mode')), []).append(r)
        lines += ['## Reviews by reviewer', '', '| reviewer | model | mode | reviews | BLOCKER | MAJOR | MINOR | avg minutes |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- |']
        for (reviewer, model, mode), rows in sorted(groups.items(), key=str):
            total = lambda field: sum(r.get(field, 0) or 0 for r in rows)
            lines.append(f'| {reviewer} | {model} | {mode} | {len(rows)} | {total("blocker")} | {total("major")} | '
                         f'{total("minor")} | {total("seconds") / len(rows) / 60:.1f} |')
        lines.append('')
    if rechecks:
        groups = {}
        for r in rechecks:
            groups.setdefault((r.get('reviewer'), r.get('model') or 'default'), []).append(r)
        lines += ['## Re-checks by reviewer', '',
                  '| reviewer | model | re-checks | upheld BLOCKER | upheld MAJOR | withdrawn BLOCKER | '
                  'withdrawn MAJOR | avg minutes |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- |']
        for (reviewer, model), rows in sorted(groups.items(), key=str):
            total = lambda field: sum(r.get(field, 0) or 0 for r in rows)
            lines.append(f'| {reviewer} | {model} | {len(rows)} | {total("upheld_blocker")} | '
                         f'{total("upheld_major")} | {total("withdrawn_blocker")} | {total("withdrawn_major")} | '
                         f'{total("seconds") / len(rows) / 60:.1f} |')
        lines.append('')
    fallback = [r for r in reviews if str(r.get('reviewer', '')).startswith('claude')]
    # Codex mode -> Claude modes it covers; a targeted re-check never covers a full code review
    covers = {'plan': ('plan',), 'code': ('code', 'recheck'), 'recheck': ('recheck',)}

    def covered(claude):
        for later in records:
            if (later.get('project'), later.get('branch')) != (claude.get('project'), claude.get('branch')):
                continue
            is_codex = later.get('kind') == 'review' and later.get('reviewer') == 'codex' \
                and claude.get('mode') in covers.get(later.get('mode'), ())
            if not (is_codex or later.get('kind') == 'catchup'):
                continue
            if str(later.get('time')) > str(claude.get('time')) or (
                    later.get('time') == claude.get('time') and later['_at'][0] == claude['_at'][0]
                    and later['_at'][1] > claude['_at'][1]):
                return True
        return False

    pending = [r for r in fallback if not covered(r)]
    if pending:
        lines += ['## Claude-only reviews (Codex catch-up pending)', '']
        lines += [f"- {r.get('time')} {r.get('project')} {r.get('branch')} {r.get('mode')} "
                  f"HEAD {str(r.get('head', ''))[:12]} ({r.get('model')})" for r in pending]
        lines.append('')
    if len(fallback) > len(pending):
        lines += [f'{len(fallback) - len(pending)} Claude review(s) covered by a later Codex review or '
                  'catch-up record.', '']
    print('\n'.join(lines).rstrip('\n'))


LIMIT_TEXT = re.compile(
    r"usage limit|rate[ _-]?limit|limit reached|hit your (?:usage )?limit|out of (?:usage|credits)|"
    r"too many requests|quota exceeded|\b429\b|resets? at|try again (?:in|at|later)", re.I)


def _next_clock(hour, minute, meridiem, reference):
    if meridiem:
        hour = hour % 12 + (12 if meridiem.lower() == 'pm' else 0)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return 0
    moment = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if moment <= reference:
        moment += timedelta(days=1)
    return int(moment.timestamp())


def parse_reset(text, reference=None):
    """Best-effort reset time (epoch seconds) from a provider limit message; 0 if unknown."""
    reference = reference or datetime.now().astimezone()
    match = re.search(r'\|(\d{10})\b', text)
    if match:
        return int(match.group(1))
    match = re.search(r'(?:reset|again)\D{0,20}(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)', text, re.I)
    if match:
        try:
            value = datetime.fromisoformat(match.group(1).replace('Z', '+00:00').replace(' ', 'T'))
            if value.tzinfo is None:
                value = value.replace(tzinfo=reference.tzinfo)
            return int(value.timestamp())
        except ValueError:
            pass
    match = re.search(r'(?:try again in|resets? in|retry in|available in)\s*(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?|rs?)?)?\s*(?:(\d+)\s*m(?:in(?:ute)?s?)?)?\s*(?:(\d+)\s*s(?:ec(?:ond)?s?)?)?', text, re.I)
    if match and any(match.groups()):
        days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
        return int(reference.timestamp()) + ((days * 24 + hours) * 60 + minutes) * 60 + seconds
    match = re.search(r'(?:resets?|again)(?: at)?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text, re.I) or \
        re.search(r'(?:resets?|again) at\s+(\d{1,2}):(\d{2})\b()', text, re.I)
    if match:
        return _next_clock(int(match.group(1)), int(match.group(2) or 0), match.group(3), reference)
    return 0


def limit_check(paths):
    """Exit 0 and print the reset epoch (0 = unknown) if the files show a usage/rate limit."""
    text = ''
    for name in paths:
        try:
            text += Path(name).read_text(errors='replace')[-20000:] + '\n'
        except OSError:
            continue
    try:
        data = json.loads(Path(paths[0]).read_text())
        if isinstance(data, dict):
            text += ' ' + str(data.get('result', '')) + ' ' + str(data.get('error', ''))
    except (OSError, ValueError, IndexError):
        pass
    if not LIMIT_TEXT.search(text):
        sys.exit(1)
    print(parse_reset(text))


def section(text, heading):
    match = re.search(r'^##\s+' + re.escape(heading) + r'\s*$(.*?)(?=^##\s|\Z)', text, re.M | re.S)
    if not match:
        return ''
    body = re.sub(r'<!--.*?-->', '', match.group(1), flags=re.S).strip()
    return body


BULLET = re.compile(r'^\s*(\d+[.)]|[-*])\s+\S')
BULLET_PREFIX = re.compile(r'^\s*(\d+[.)]|[-*])\s+(\[ \]\s*)?')


def manual_testing(handoff):
    """Split "Manual testing for the human" into (needs_you, automated, legacy).
    Without the `### Needs you` / `### Covered by automated tests` subsections the whole
    section is "needs you" and legacy is True."""
    body = section(handoff, 'Manual testing for the human')
    parts = re.split(r'^###\s+(Needs you|Covered by automated tests)\s*$', body, flags=re.M)
    if len(parts) == 1:
        return body, '', True
    found = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}
    return found.get('Needs you', ''), found.get('Covered by automated tests', ''), False


NAMED_TEST = re.compile(r'`[^`\n]+`')


def flag_unnamed(automated):
    """Return (lines, count) for the automated section. A list item is a bullet line plus its
    continuation lines; one without a paired backtick span gets a warning on its last line."""
    items, current = [], None
    for line in automated.splitlines():
        if BULLET.match(line):
            current = [line]
            items.append(current)
        elif current is not None and line.strip():
            current.append(line)
        else:
            current = None
            items.append([line])
    lines, count = [], 0
    for item in items:
        if BULLET.match(item[0]):
            count += 1
            if not NAMED_TEST.search('\n'.join(item)):
                item = item[:-1] + [item[-1] + ' ⚠ no test named']
        lines += item
    return lines, count


def pr_title(arguments):
    """PR title: first line of the spec objective, else the branch name."""
    objective = section(Path('.ai/project-spec.md').read_text(), 'Objective') if Path('.ai/project-spec.md').exists() else ''
    line = next((l.strip(' #-*') for l in objective.splitlines() if l.strip()), '')
    if not line:
        line = git('symbolic-ref', '--short', 'HEAD').decode().strip()
    print(line[:72])


REVIEWER_NAMES = {'codex': 'Codex', 'claude': 'Claude', 'claude-fallback': 'Claude fallback',
                  'claude-routed': 'Claude, routed'}


def reviewed_by_entries(review):
    """Who reviewed each round of this project and branch, from the outcome log (plan and code
    reviews, oldest first, at most 10, newest kept); the current report's `Reviewed by:` line
    when the log is unreadable or has none."""
    entries = []
    try:
        check_state_root(git('rev-parse', '--show-toplevel').decode().strip())
        project, branch = project_name(), current_branch() or 'detached'
        rows = [r for r in read_outcomes([outcomes_path()])
                if r.get('kind') == 'review' and r.get('mode') in ('plan', 'code')
                and r.get('project') == project and r.get('branch') == branch]
        code_rounds = 0
        for row in rows:
            name = REVIEWER_NAMES.get(row.get('reviewer'), str(row.get('reviewer')))
            text = f"{name} ({row.get('model') or 'default'})"
            if row.get('route'):
                text += f": {row['route']}"
            if row['mode'] == 'plan':
                entries.append(f'plan: {text}')
            else:
                code_rounds += 1
                entries.append(f'code round {code_rounds}: {text}')
    except (OSError, ValueError, SystemExit, subprocess.CalledProcessError):
        entries = []
    if not entries:
        line = re.search(r'^Reviewed by: (.+)$', review, re.M)
        return [line.group(1).strip()] if line else ['not recorded']
    return entries[-10:]


def pr_body(arguments):
    """Markdown PR description from workflow records. Args: rounds unresolved(0/1)."""
    rounds, unresolved = int(arguments[0]), arguments[1] == '1'
    spec = Path('.ai/project-spec.md').read_text() if Path('.ai/project-spec.md').exists() else ''
    handoff = Path('.ai/handoff.md').read_text() if Path('.ai/handoff.md').exists() else ''
    review = Path('.ai/reviews/current.md').read_text() if Path('.ai/reviews/current.md').exists() else ''
    if review and 'Host evidence' in review:
        # Never publish review claims that don't match what ai-review recorded.
        head = re.search(r'Host evidence: HEAD ([0-9a-f]{7,40});', review)
        binding = binding_dir() / f'{head.group(1)}.sha256' if head else None
        if not binding or not binding.exists() or \
                binding.read_text().strip() != hashlib.sha256(review.encode()).hexdigest():
            fail('Current review does not match the report ai-review published; refusing to publish it.')
    lines = []
    disputes = disputes_values()  # never publish dispute records the host didn't write
    if disputes:
        lines += ['## Disputed findings', '',
                  f'> [!CAUTION]\n> Draft: Codex upheld {len(disputes)} finding(s) Claude rejected. '
                  'Resolve each one here before testing and merging; the pipeline never resolves them.', '']
        for record in disputes:
            lines += [f"- **{record['finding']}** ({record['level']}, review {record['review_digest'][:12]}): "
                      f"{record['finding_text']}",
                      f"  - Claude's reason: {record['evidence']}",
                      f"  - Codex's answer: {record['answer']}"]
        lines += ['', 'Records: `.ai/reviews/disputes.md`.', '']
    if unresolved:
        lines += ['> [!WARNING]', '> Draft: significant review findings remain after the automatic fix rounds.',
                  '> See "Independent review" below before testing.', '']
    objective = section(spec, 'Objective')
    lines += ['## Summary', '', objective or 'See `.ai/project-spec.md`.', '']
    flow = section(handoff, 'Flow chart')
    if flow:
        lines += [flow, '']
    lines += ['## Tasks', '']
    queue = tasks()
    for task in queue:
        mark = {'DONE': 'x'}.get(task['status'], ' ')
        suffix = '' if task['status'] == 'DONE' else f" ({task['status']})"
        lines.append(f"- [{mark}] {task['id']} {task['title']}{suffix}")
    skipped = [f"{task['id']}: {skipped_lines(task)[0].split('): ', 1)[1]}"
               for task in queue if task['status'] == 'SKIPPED']
    if skipped:
        lines += ['', 'Skipped tasks: ' + '; '.join(skipped)]
    lines.append('')
    evidence = Path('.ai/local/validation.json')
    lines += ['## Validation', '']
    if evidence.exists():
        data = json.loads(evidence.read_text())
        lines.append(f"`.ai/validate`: **{data.get('result')}** at {data.get('timestamp', '?')} "
                     f"(commit {str(data.get('head', '?'))[:9]}).")
    else:
        lines.append('No local validation evidence recorded.')
    lines.append('')
    fallback = re.search(r'^> \*\*Reviewer: (Claude(?: fallback)?) \(([^,;)]+), effort [^;]*; ([^)]*)\)', review, re.M)
    routed = re.search(r'^> \*\*Reviewer: Claude, routed \(([^,;)]+), effort [^;]*; (.*)\)\. Codex reviewed', review, re.M)
    heading = f'Claude, routed, {routed.group(1)}' if routed else \
        fallback.group(1) + ', ' + fallback.group(2) if fallback else 'Codex'
    lines += [f'## Independent review ({heading})', '']
    if routed:
        lines += ['> [!NOTE]', f'> Codex reviewed this branch earlier; this fix round was routed to a fresh Claude '
                  f'session: {routed.group(2)}.', '']
    elif fallback:
        lines += ['> [!NOTE]', f'> A read-only Claude session reviewed this instead of Codex ({fallback.group(3)}). '
                  'Codex reviews it later in one catch-up review (`.ai/reviews/fallback-log.md`).', '']
    lines += ['Reviewed by:'] + [f'- {entry}' for entry in reviewed_by_entries(review)] + ['']
    if review:
        verdict = review_verdict(review)
        counts = COUNTS.search(review)
        verdict_text = verdict.rstrip('.') if verdict else 'unknown'
        lines.append(f"Rounds: {rounds}. Verdict: {verdict_text}.")
        if counts:
            lines.append(f"Findings in the last review: BLOCKER {counts.group(1)}, MAJOR {counts.group(2)}, "
                         f"MINOR {counts.group(3)}. Full report and Claude's dispositions: `.ai/reviews/current.md`.")
        dispositions = Path('.ai/reviews/dispositions.md')
        if dispositions.exists():
            rows = [m.group(2).lower() for m in DISPOSITION_ROW.finditer(dispositions.read_text())]
            if rows:
                summary = ', '.join(f'{rows.count(kind)} {kind}' for kind in ('accepted', 'rejected', 'deferred') if rows.count(kind))
                lines.append(f'Claude\'s dispositions of earlier findings: {summary} (`.ai/reviews/dispositions.md`).')
    else:
        lines.append('No review recorded.')
    lines.append('')
    needs_you, automated, legacy = manual_testing(handoff)
    if legacy:
        lines += ['## How to test', '', needs_you or 'See `.ai/handoff.md`.', '']
    else:
        lines += ['## How to test', '', '### Needs you', '']
        if not needs_you or NONE_TEXT.match(BULLET_PREFIX.sub('', needs_you)):
            lines += ['None — everything below is automated.', '']
        else:
            lines += [needs_you, '']
        if automated:
            flagged, count = flag_unnamed(automated)
            lines += ['### Covered by automated tests', '',
                      f'<details><summary>{count} automated checks</summary>', '', *flagged, '', '</details>', '']
    lines += ['---', 'Opened by `ai-pipeline`. Merging and deployment remain with the human.', '',
              '🤖 Generated with [Claude Code](https://claude.com/claude-code)']
    print('\n'.join(lines))


# Safe record I/O for the dashboard's host-written records (.ai/local/observation.json,
# .ai/local/notifications.log, <state root>/pipelines/). Agent sessions can write the checkout,
# so every directory is opened without following symlinks and then used as a pinned
# descriptor; files are opened O_NOFOLLOW|O_NONBLOCK, regular files only, reads are capped and
# locks are nonblocking with a deadline. The writers never fail their caller: any failure
# prints a warning and skips the write.

DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
LOCK_DEADLINE = 2.0
LOCK_RETRY = 0.05
OBSERVATION_LIMIT = 64 * 1024
NOTIFICATIONS_LIMIT = 256 * 1024
NOTIFICATIONS_KEEP = 200
SMALL_LIMIT = 4 * 1024
TASKS_LIMIT = 1024 * 1024
BOX_KEYS = ('planning', 'plan_review', 'plan_revision', 'setup', 'build', 'checks', 'review', 'triage',
            'recheck', 'pr')
OBSERVATION_STATES = ('active', 'paused', 'recovering', 'stopped', 'done')
# ai-pipeline's stop labels: (box keys the label covers, stage when the recorded one is outside).
STOP_LABELS = {
    'start': ((), 'none'),
    'plan': (('planning',), 'planning'),
    'plan review': (('plan_review', 'plan_revision'), 'plan_review'),
    'plan revision': (('plan_revision',), 'plan_revision'),
    'implementation': (('setup', 'build', 'checks'), 'build'),
    'validation': (('checks',), 'checks'),
    'review': (('review',), 'review'),
    'triage': (('triage',), 'triage'),
    're-check': (('recheck',), 'recheck'),
    'pull request preparation': (('pr',), 'pr'),
    'push': (('pr',), 'pr'),
    'pull request': (('pr',), 'pr'),
    'final push': (('pr',), 'pr'),
}


class RecordError(Exception):
    """An unsafe or unavailable record; the writer warns and skips."""


def warn(message):
    print(f'Warning: {message}', file=sys.stderr)


def close_fds(*fds):
    for fd in fds:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def open_dir(base_fd, relative):
    """Descriptor for RELATIVE below BASE_FD, every component opened without following a
    symlink; None for a symlink, a non-directory, `..` or any error."""
    current = os.dup(base_fd)
    try:
        for part in relative.split('/'):
            if part in ('', '.'):
                continue
            if part == '..':
                return close_fds(current)
            following = os.open(part, DIR_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        return current
    except OSError:
        return close_fds(current)


def checkout_fds(root):
    """(root, .ai, .ai/local) descriptors pinned without following symlinks below the root
    (the human's checkout path); None when the root or `.ai` is unsafe or missing, local None
    when only `.ai/local` is. The caller closes them."""
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except (OSError, ValueError):
        return None
    ai_fd = open_dir(root_fd, '.ai')
    if ai_fd is None:
        return close_fds(root_fd)
    return root_fd, ai_fd, open_dir(ai_fd, 'local')


def local_dir_fd(root):
    """Pinned `.ai/local` descriptor of ROOT, or None when any component is unsafe."""
    fds = checkout_fds(root)
    if fds is None:
        return None
    close_fds(fds[0], fds[1])
    return fds[2]


EXEC_LOG_NAME = re.compile(r'plan-\d{8}T\d{6}Z-[0-9a-f]{8}\.log')


def exec_logged(arguments):
    """exec-logged NAME -- CMD [ARGS...]: exec CMD with stdout/stderr on the new log NAME in
    the pinned `.ai/local` of the current checkout, keeping this process's PID. Not a shell
    `>"$log"`: that follows a planted symlink or blocks on a FIFO, and a second-resolution name
    is shared by two launches. The log is created exclusively without following symlinks, so any
    existing entry (file, symlink, FIFO) fails untouched. Errors before the dup2 reach the
    caller's stderr; usage errors exit 2 before anything is created."""
    if len(arguments) < 3 or arguments[1] != '--':
        print('Usage: workflow.py exec-logged NAME -- CMD [ARGS...]', file=sys.stderr)
        sys.exit(2)
    name, command, args = arguments[0], arguments[2], arguments[3:]
    if not EXEC_LOG_NAME.fullmatch(name):
        print(f'Error: invalid log name: {name}', file=sys.stderr)
        sys.exit(2)
    if not os.path.isabs(command) or not os.path.isfile(command) or not os.access(command, os.X_OK):
        print(f'Error: not an absolute path to an executable: {command}', file=sys.stderr)
        sys.exit(2)
    dir_fd = local_dir_fd(checkout_root())
    if dir_fd is None:
        fail('.ai/local is missing or unsafe')
    try:
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK
                         | os.O_CLOEXEC, 0o600, dir_fd=dir_fd)
        except FileExistsError:
            fail(f'log {name} already exists')
        except OSError as error:
            fail(error.strerror or str(error))
    finally:
        os.close(dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            fail(f'log {name} is not a regular file')
        fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK)
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(fd, 1)
        os.dup2(fd, 2)
    finally:
        os.close(fd)
    os.execv(command, [command, *args])


def remove_tree(parent_fd, name):
    """Delete the directory NAME of PARENT_FD and everything below it, walking descriptors
    opened without following symlinks: an inner symlink is unlinked, never entered."""
    fd = os.open(name, DIR_FLAGS, dir_fd=parent_fd)
    try:
        with os.scandir(fd) as entries:
            children = [(entry.name, entry.is_dir(follow_symlinks=False)) for entry in entries]
        for child, is_dir in children:
            if is_dir:
                remove_tree(fd, child)
            else:
                os.unlink(child, dir_fd=fd)
    finally:
        os.close(fd)
    os.rmdir(name, dir_fd=parent_fd)


def clear_scratch():
    """clear-scratch: empty .ai/local/scratch of AI_ROOT (else the current directory) between
    agent sessions. Never a path-based delete: a session may have replaced `.ai`, `.ai/local`
    or `scratch` by a symlink, so everything goes through the pinned `.ai/local` descriptor.
    Warns and never fails the caller."""
    root = os.environ.get('AI_ROOT') or os.getcwd()
    local_fd = local_dir_fd(root)
    if local_fd is None:
        return warn('could not clear .ai/local/scratch: unsafe or missing .ai/local')
    try:
        try:
            info = os.stat('scratch', dir_fd=local_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISDIR(info.st_mode):
            remove_tree(local_fd, 'scratch')
        else:
            # A symlink is removed itself, never followed.
            os.unlink('scratch', dir_fd=local_fd)
    except (OSError, RecursionError) as error:
        warn(f'could not clear .ai/local/scratch: {error}')
    finally:
        os.close(local_fd)


def exec_bits(protected):
    """exec-bits ROOT...: give back the execute bit git records (index mode 100755) to a regular
    file that lost it in the working tree. A path equal to a ROOT or below it is never touched
    (the runner passes the guard's protected-path list), nor is a symlink: every path component
    is opened below the pinned root without following a symlink, so a directory replaced by a
    symlink never leads outside the checkout. Prints the restored relative paths, one per line."""
    if not protected:
        fail('usage: exec-bits ROOT...')
    root = checkout_root()
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError:
        return
    try:
        for entry in git('ls-files', '-s', '-z', cwd=root).split(b'\0'):
            meta, _, raw = entry.partition(b'\t')
            if not meta.startswith(b'100755 '):
                continue
            name = raw.decode()
            if any(name == gate.rstrip('/') or name.startswith(gate.rstrip('/') + '/') for gate in protected):
                continue
            if exec_bit_restored(root_fd, name):
                print(name)
    finally:
        os.close(root_fd)


def exec_bit_restored(root_fd, name):
    """True when the regular file NAME below ROOT_FD, reached without following any symlink,
    lacked every execute bit and got them back for each read bit."""
    parent, _, leaf = name.rpartition('/')
    if leaf in ('', '.', '..'):
        return False
    dir_fd = open_dir(root_fd, parent)
    if dir_fd is None:
        return False
    fd = None
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode) or mode & 0o111:
            return False
        os.fchmod(fd, stat.S_IMODE(mode) | ((mode & 0o444) >> 2))
        return True
    except OSError:
        return False
    finally:
        close_fds(fd, dir_fd)


def read_record(dir_fd, name, limit, tail=False, raw=False):
    """(text, stat) of the regular file NAME in DIR_FD, at most LIMIT bytes, or None. Never
    follows a symlink or blocks on a FIFO or device. TAIL reads the newest complete lines; RAW
    returns the bytes undecoded."""
    if '/' in name or name in ('', '.', '..'):
        return None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None
        cut = tail and info.st_size > limit
        if cut:
            # One byte more: when it is a newline the window starts on a complete line.
            os.lseek(fd, info.st_size - limit - 1, os.SEEK_SET)
        wanted = limit + 1 if cut else limit
        chunks = []
        while wanted > 0:
            chunk = os.read(fd, min(wanted, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            wanted -= len(chunk)
        data = b''.join(chunks)
        if cut:
            data = data.split(b'\n', 1)[1] if b'\n' in data else b''
        return (data if raw else data.decode('utf-8', errors='replace')), info
    except OSError:
        return None
    finally:
        os.close(fd)


def lock_record(dir_fd, name):
    """Exclusive flock on the regular file NAME (created, never truncated or written), retried
    every 50 ms up to the 2 s deadline. Returns the descriptor that holds the lock."""
    try:
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     0o600, dir_fd=dir_fd)
    except OSError as error:
        raise RecordError(f'cannot open lock {name}: {error.strerror}')
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RecordError(f'lock {name} is not a regular file')
        deadline = time.monotonic() + LOCK_DEADLINE
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RecordError(f'lock {name} still held after {LOCK_DEADLINE:g} s')
                time.sleep(LOCK_RETRY)
    except BaseException:
        os.close(fd)
        raise


def write_record(dir_fd, name, contents):
    """Replace NAME in DIR_FD with CONTENTS through an exclusively created temp file and a
    rename on the pinned descriptor (a symlink or hard link at NAME is replaced, never
    written through)."""
    data = contents.encode()
    for attempt in range(3):
        temp = f'.{name}.{os.getpid()}.tmp' if attempt == 0 else f'.{name}.{os.urandom(6).hex()}.tmp'
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK
                         | os.O_CLOEXEC, 0o644, dir_fd=dir_fd)
            break
        except FileExistsError:
            continue
        except OSError as error:
            raise RecordError(f'cannot create a temp file for {name}: {error.strerror}')
    else:
        raise RecordError(f'cannot create a temp file for {name}')
    try:
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RecordError(f'temp file for {name} is not a regular file')
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        os.replace(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        try:
            os.unlink(temp, dir_fd=dir_fd)
        except OSError:
            pass
        raise


def git_branch(root_fd):
    """Branch of the checkout at ROOT_FD from its Git metadata (no git subprocess): the name,
    `detached`, or None for anything unexpected or unsafe."""
    git_fd = open_dir(root_fd, '.git')
    if git_fd is None:
        pointer = read_record(root_fd, '.git', SMALL_LIMIT)
        if pointer is None:
            return None
        match = re.fullmatch(r'gitdir: (.+?)\s*', pointer[0])
        path = match.group(1) if match else ''
        # A worktree points at an absolute gitdir; refuse relative paths and `..`.
        if not os.path.isabs(path) or '..' in path.split('/'):
            return None
        try:
            slash = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        except OSError:
            return None
        git_fd = open_dir(slash, path)
        os.close(slash)
        if git_fd is None:
            return None
    try:
        head = read_record(git_fd, 'HEAD', SMALL_LIMIT)
    finally:
        os.close(git_fd)
    if head is None:
        return None
    text = head[0].strip()
    match = re.fullmatch(r'ref: refs/heads/(\S+)', text)
    if match:
        return match.group(1)
    if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', text):
        return 'detached'
    return None


def observation_update(record, action, values):
    """The new observation record for ACTION, or None when nothing changes."""
    def box(key):
        if key not in BOX_KEYS:
            raise RecordError(f'unknown stage key: {key}')
        return key

    def needs(count, usage):
        if not count[0] <= len(values) <= count[1]:
            raise RecordError(f'usage: observe {usage}')

    stamp = now()
    if action == 'start':
        needs((0, 0), 'start')
        return {**record, 'stage': 'none', 'state': 'active', 'detail': '', 'note': '', 'since': stamp}
    if action == 'step':
        needs((1, 2), 'step STAGE [DETAIL]')
        return {**record, 'stage': box(values[0]), 'state': 'active',
                'detail': values[1] if len(values) > 1 else '', 'note': '', 'since': stamp}
    if action == 'detail':
        needs((2, 2), 'detail STAGE TEXT')
        if record.get('stage') != box(values[0]) or record.get('state') not in ('active', 'paused'):
            return None
        return {**record, 'detail': values[1]}
    if action == 'pause':
        needs((1, 1), 'pause NOTE')
        return {**record, 'state': 'paused', 'note': values[0]}
    if action == 'relaunch':
        # Waiting for a scheduled usage-limit relaunch. previous_observation keeps only the
        # base fields, so every other action drops `relaunch_at`.
        needs((2, 2), 'relaunch AT NOTE')
        if not re.fullmatch(r'\d{1,12}', values[0]):
            raise RecordError('usage: observe relaunch AT NOTE')
        return {**record, 'state': 'paused', 'note': values[1], 'relaunch_at': int(values[0])}
    if action == 'resume':
        needs((0, 0), 'resume')
        # Only a pause is lifted: a stop or recovery recorded meanwhile stays visible.
        if record.get('state') != 'paused':
            return None
        return {**record, 'state': 'active', 'note': ''}
    if action == 'stop':
        needs((2, 2), 'stop LABEL REASON')
        stage = record.get('stage', 'none')
        group, target = STOP_LABELS.get(values[0], (None, None))
        if group is not None and stage not in group:
            stage = target
        return {**record, 'stage': stage, 'state': 'stopped', 'note': values[1], 'since': stamp}
    if action == 'recovering':
        needs((1, 2), 'recovering NOTE [STAGE]')
        stage = box(values[1]) if len(values) > 1 else record.get('stage', 'none')
        return {**record, 'stage': stage, 'state': 'recovering', 'note': values[0], 'since': stamp}
    if action == 'done':
        needs((1, 1), 'done NOTE')
        return {**record, 'stage': 'pr', 'state': 'done', 'detail': '', 'note': values[0], 'since': stamp}
    if action == 'planned':
        needs((1, 1), 'planned NOTE')
        return {**record, 'stage': 'planning', 'state': 'done', 'detail': '', 'note': values[0], 'since': stamp}
    raise RecordError(f'unknown observe action: {action}')


def replaced_record(dir_fd, name, limit, tail=False):
    """read_record for a record the writer replaces next: warns when NAME exists but cannot
    be read safely (a symlink, FIFO or device is replaced, never followed)."""
    current = read_record(dir_fd, name, limit, tail)
    if current is None:
        try:
            os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            warn(f'{name} is not a regular file; replacing it')
        except OSError:
            pass
    return current


def previous_observation(local_fd):
    previous = replaced_record(local_fd, 'observation.json', OBSERVATION_LIMIT)
    try:
        record = json.loads(previous[0]) if previous else {}
    except ValueError:
        record = {}
    if not isinstance(record, dict):
        record = {}
    fields = {'stage': 'none', 'state': 'active', 'detail': '', 'since': '', 'note': ''}
    for key, default in fields.items():
        if not isinstance(record.get(key), str):
            record[key] = default
    if record['stage'] not in BOX_KEYS + ('none',):
        record['stage'] = 'none'
    if record['state'] not in OBSERVATION_STATES:
        record['state'] = 'active'
    return {key: record[key] for key in fields}


def observe(arguments):
    """observe ACTION [ARGS]: update .ai/local/observation.json of AI_ROOT (else the current
    directory). Never fails the caller."""
    if not arguments:
        raise RecordError('usage: observe ACTION [ARGS]')
    root = os.environ.get('AI_ROOT') or os.getcwd()
    fds = checkout_fds(root)
    if fds is None or fds[2] is None:
        if fds:
            close_fds(*fds)
        raise RecordError(f'{root}/.ai/local is missing, a symlink or not a directory')
    root_fd, ai_fd, local_fd = fds
    lock = None
    try:
        lock = lock_record(local_fd, 'observation.lock')
        record = observation_update(previous_observation(local_fd), arguments[0], arguments[1:])
        if record is None:
            return
        record.update(pid=os.getppid(), branch=git_branch(root_fd), updated=now())
        write_record(local_fd, 'observation.json', json.dumps(record, ensure_ascii=False) + '\n')
    finally:
        close_fds(lock, root_fd, ai_fd, local_fd)


LIMIT_STOP_ERROR = (r'(Claude|Codex) usage limit: the reset is beyond the \d+s wait budget\. '
                    r'Rerun after it resets\.')


def limit_stop_write(arguments):
    """limit-stop-write AGENT RESET: record `AGENT RESET` in .ai/local/limit-stop of AI_ROOT
    (else the current directory) through the pinned `.ai/local` and write_record, so a symlink
    or FIFO planted at the temp or final name is replaced, never written through."""
    if len(arguments) != 2 or not re.fullmatch(r'Claude|Codex', arguments[0]) \
            or not re.fullmatch(r'\d{1,12}', arguments[1]):
        fail('Usage: limit-stop-write Claude|Codex RESET')
    local_fd = local_dir_fd(os.environ.get('AI_ROOT') or os.getcwd())
    if local_fd is None:
        fail('.ai/local is missing, a symlink or not a directory')
    try:
        write_record(local_fd, 'limit-stop', f'{arguments[0]} {arguments[1]}\n')
    except RecordError as error:
        fail(str(error))
    finally:
        os.close(local_fd)


def limit_stop(arguments):
    """limit-stop [--now EPOCH]: print `<Agent> <relaunch epoch>` when the last stop of this
    checkout was only a usage limit beyond the wait budget (last-error is exactly that message
    and limit-stop, written just before it, names the same agent); else exit 1 silently."""
    if arguments and not (len(arguments) == 2 and arguments[0] == '--now'
                          and re.fullmatch(r'\d{1,12}', arguments[1])):
        sys.exit(1)
    current = int(arguments[1]) if arguments else int(time.time())
    retry = os.environ.get('AI_LIMIT_RETRY') or '1800'
    local_fd = local_dir_fd(os.environ.get('AI_ROOT') or os.getcwd())
    if local_fd is None or not re.fullmatch(r'\d{1,9}', retry):
        close_fds(local_fd)
        sys.exit(1)
    try:
        error = read_record(local_fd, 'last-error', SMALL_LIMIT)
        record = read_record(local_fd, 'limit-stop', SMALL_LIMIT)
    finally:
        os.close(local_fd)
    if error is None or record is None:
        sys.exit(1)
    text = error[0][:-1] if error[0].endswith('\n') else error[0]
    message = re.fullmatch(LIMIT_STOP_ERROR, text)
    stop = re.fullmatch(r'(Claude|Codex) (\d{1,12})\n?', record[0])
    # A record from an earlier stop never qualifies: written just before this last-error.
    age = error[1].st_mtime - record[1].st_mtime
    if not message or not stop or message.group(1) != stop.group(1) or not 0 <= age <= 120:
        sys.exit(1)
    reset = int(stop.group(2))
    if reset > current:
        relaunch = reset + 60
    elif reset == 0:
        relaunch = current + int(retry)
    else:
        relaunch = current
    print(f'{stop.group(1)} {relaunch}')


def log_entry(line):
    """True for a notification log line worth keeping: a JSON object (a partial or planted
    line is dropped on the next rewrite)."""
    try:
        return isinstance(json.loads(line), dict)
    except ValueError:
        return False


def notify_log(arguments):
    """notify-log ROOT MESSAGE: append {"ts","message"} to ROOT/.ai/local/notifications.log,
    keeping the last 200 lines; the log is replaced, never written in place."""
    if len(arguments) != 2:
        raise RecordError('usage: notify-log ROOT MESSAGE')
    root, message = arguments
    local_fd = local_dir_fd(root)
    if local_fd is None:
        raise RecordError(f'{root}/.ai/local is missing, a symlink or not a directory')
    lock = None
    try:
        lock = lock_record(local_fd, 'notifications.lock')
        current = replaced_record(local_fd, 'notifications.log', NOTIFICATIONS_LIMIT, tail=True)
        lines = [line for line in (current[0] if current else '').splitlines() if log_entry(line)]
        lines.append(json.dumps({'ts': now(), 'message': message}, ensure_ascii=False))
        write_record(local_fd, 'notifications.log', '\n'.join(lines[-NOTIFICATIONS_KEEP:]) + '\n')
    finally:
        close_fds(lock, local_fd)


PRUNE_HOOK = None  # Tests only: runs between the prune's listing and its re-reads.


def pipeline_register(arguments):
    """pipeline-register CHECKOUT BRANCH: record the run in <state root>/pipelines and drop
    entries whose checkout is gone or whose JSON is invalid."""
    if len(arguments) != 2:
        raise RecordError('usage: pipeline-register CHECKOUT BRANCH')
    checkout, branch = os.path.abspath(arguments[0]), arguments[1]
    root = check_state_root(checkout)
    try:
        os.makedirs(root / 'pipelines', mode=0o700, exist_ok=True)
        directory = os.open(root / 'pipelines', DIR_FLAGS)
    except OSError as error:
        raise RecordError(f'{root}/pipelines is not a usable directory: {error.strerror}')
    lock = None
    try:
        lock = lock_record(directory, '.lock')
        own = hashlib.sha256(checkout.encode()).hexdigest()[:16] + '.json'
        entry = {'checkout': checkout, 'project': os.path.basename(checkout), 'branch': branch,
                 'started': now()}
        write_record(directory, own, json.dumps(entry, ensure_ascii=False) + '\n')
        names = sorted(name for name in os.listdir(directory)
                       if name.endswith('.json') and not name.startswith('.') and name != own)
        if PRUNE_HOOK:
            PRUNE_HOOK(directory, names)
        for name in names:
            current = read_record(directory, name, OBSERVATION_LIMIT)
            if current is None:
                continue
            try:
                data = json.loads(current[0])
                keep = isinstance(data, dict) and isinstance(data.get('checkout'), str) \
                    and os.path.isdir(data['checkout'])
            except ValueError:
                keep = False
            if not keep:
                try:
                    os.unlink(name, dir_fd=directory)
                except OSError:
                    pass
    finally:
        close_fds(lock, directory)


RECORD_COMMANDS = {'observe': observe, 'notify-log': notify_log,
                   'pipeline-register': pipeline_register}


def record_command(command, arguments):
    """Run a record writer; exit 0 whatever happens (a warning on stderr instead)."""
    try:
        RECORD_COMMANDS[command](arguments)
    except (RecordError, ValueError, OSError) as error:
        warn(f'{command}: {error}')
    except Exception as error:  # Never fail the caller over an observation.
        warn(f'{command}: unexpected {type(error).__name__}: {error}')


def main():
    if len(sys.argv) < 2:
        fail('Missing helper command.')
    command, *arguments = sys.argv[1:]
    if command == 'setup':
        setup(arguments)
    elif command == 'paths':
        safe_paths(arguments[0])
    elif command == 'tasks':
        task_command(arguments)
    elif command == 'state':
        update_state(*arguments)
    elif command == 'stamp':
        stamp(arguments)
    elif command == 'status':
        status()
    elif command == 'claude-result':
        claude_result(arguments[0], '--check-only' in arguments[1:])
    elif command == 'publish-review':
        publish_review(arguments)
    elif command == 'start-dispositions':
        start_dispositions(arguments)
    elif command == 'triage-check':
        triage_check(arguments)
    elif command == 'review-history':
        review_history(arguments)
    elif command == 'review-info':
        review_info(arguments)
    elif command == 'review-range':
        review_range(arguments)
    elif command == 'recheck-prepare':
        recheck_prepare(arguments)
    elif command == 'publish-recheck':
        publish_recheck(arguments)
    elif command == 'recheck-verify':
        recheck_verify(arguments)
    elif command == 'recheck-status':
        recheck_status(arguments)
    elif command == 'disputes-record':
        disputes_record(arguments)
    elif command == 'disputes-verify':
        disputes_verify(arguments)
    elif command == 'fix-rounds':
        fix_rounds(arguments)
    elif command == 'triage-scope':
        triage_scope(arguments)
    elif command == 'stage-verify':
        stage_verify(arguments)
    elif command == 'run-manifest':
        run_manifest(arguments)
    elif command == 'run-record':
        run_record(arguments)
    elif command == 'run-stop':
        run_stop(arguments)
    elif command == 'escalation':
        escalation(arguments)
    elif command == 'ruling-row':
        ruling_row(arguments)
    elif command == 'state-root-check':
        state_root_check(arguments)
    elif command == 'checkpoint-guard':
        checkpoint_guard(arguments)
    elif command == 'committed-matches-worktree':
        committed_matches_worktree(arguments)
    elif command == 'recover-decision':
        recover_decision(arguments)
    elif command == 'deps-status':
        deps_status(arguments)
    elif command == 'deps-record':
        deps_record(arguments)
    elif command == 'clear-scratch':
        clear_scratch()
    elif command == 'exec-bits':
        exec_bits(arguments)
    elif command == 'exec-logged':
        exec_logged(arguments)
    elif command == 'tree-snapshot':
        print(tree_snapshot(checkout_root()))
    elif command == 'worktree-digest':
        print(worktree_digest(checkout_root()))
    elif command == 'finish-summary':
        finish_summary(arguments)
    elif command == 'plan-digest':
        print(plan_digest())
    elif command == 'publish-plan-review':
        publish_plan_review(arguments)
    elif command == 'review-format-check':
        review_format_check(arguments)
    elif command == 'plan-review-info':
        plan_review_info(arguments)
    elif command == 'plan-rounds':
        plan_rounds(arguments)
    elif command == 'plan-history':
        plan_history(arguments)
    elif command == 'start-plan-dispositions':
        start_plan_dispositions(arguments)
    elif command == 'plan-dispositions-check':
        plan_dispositions_check(arguments)
    elif command == 'disposition-ruling':
        disposition_ruling(arguments)
    elif command == 'flow-line-ruling':
        flow_line_ruling(arguments)
    elif command == 'plan-revision-scope':
        plan_revision_scope(arguments)
    elif command == 'plan-revision-allowlist':
        plan_revision_allowlist(arguments)
    elif command == 'plan-allowlist':
        plan_allowlist(arguments)
    elif command == 'plan-scope':
        plan_scope(arguments)
    elif command == 'plan-keeps-done':
        plan_keeps_done(arguments)
    elif command == 'plan-revisions':
        plan_revisions(arguments)
    elif command == 'revision-queue-repair':
        revision_queue_repair(arguments)
    elif command == 'limit-check':
        limit_check(arguments)
    elif command == 'limit-stop':
        limit_stop(arguments)
    elif command == 'limit-stop-write':
        limit_stop_write(arguments)
    elif command == 'claude-text':
        claude_text(arguments)
    elif command == 'review-allowlist':
        review_allowlist(arguments)
    elif command == 'review-risk':
        review_risk(arguments)
    elif command == 'review-route':
        review_route(arguments)
    elif command == 'codex-limit':
        codex_limit(arguments)
    elif command == 'fallback-record':
        fallback_record(arguments)
    elif command == 'outcome':
        outcome(arguments)
    elif command == 'gate-seconds':
        gate_seconds(arguments)
    elif command == 'attempt-info':
        attempt_info(arguments)
    elif command == 'outcomes-report':
        outcomes_report(arguments)
    elif command == 'pr-draft':
        pr_draft(arguments)
    elif command == 'pr-title':
        pr_title(arguments)
    elif command == 'pr-body':
        pr_body(arguments)
    elif command in RECORD_COMMANDS:
        record_command(command, arguments)
    else:
        fail(f'Unknown helper command: {command}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
