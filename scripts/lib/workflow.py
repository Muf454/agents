#!/usr/bin/env python3
"""Standard-library helpers for safe copying, Markdown parsing, and evidence.

The shell scripts own the workflow. This module never invokes an AI agent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
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


def setup(arguments):
    parser = argparse.ArgumentParser(description='Copy templates without overwriting existing files.')
    parser.add_argument('project', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(arguments)
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
                 'lib/common.sh', 'lib/workflow.py', 'lib/watchdog.py'):
        copies[f'.ai/bin/{name}'] = toolkit / 'scripts' / name
    generated = '.ai/validation-candidates.md'
    destinations = list(copies) + [generated, '.gitignore', '.ai/local']
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
    for relative, source in copies.items():
        target = root / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects existing files even if setup is repeated.
        with target.open('xb') as file:
            file.write(source.read_bytes())
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
    print('Installed. Existing files were preserved: reconcile KEEP entries manually before running.')


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
            continue
        if fence:
            continue
        heading = re.match(r'^##\s+(T\d{3,})\s+[—-]\s+(.+?)\s*$', line)
        if heading:
            current = {'id': heading.group(1), 'title': heading.group(2), 'lines': []}
            blocks.append(current)
        elif re.match(r'^##\s+T\d', line):
            fail(f'Malformed task heading: {line}')
        elif line.startswith('## '):
            current = None
        elif current is not None:
            current['lines'].append(line)
    return blocks


def tasks():
    blocks = task_blocks(Path('.ai/tasks.md').read_text())
    ids = [task['id'] for task in blocks]
    if len(ids) != len(set(ids)):
        fail('Duplicate task IDs.')
    required = ('Goal', 'Implementation notes', 'Likely affected modules',
                'Acceptance criteria', 'Validation', 'Result / notes')
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
        if task['status'] not in ('TODO', 'IN_PROGRESS', 'BLOCKED', 'DONE'):
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
        if task['status'] in ('DONE', 'IN_PROGRESS') and any(by_id[d]['status'] != 'DONE' for d in task['deps']):
            fail(f"{task['id']}: {task['status']} requires DONE dependencies")
    if sum(task['status'] == 'IN_PROGRESS' for task in blocks) > 1:
        fail('At most one task can be IN_PROGRESS.')
    return blocks


def task_command(arguments):
    blocks = tasks()
    action = arguments[0]
    if action == 'check':
        if not blocks:
            fail('No real tasks. Plan before starting implementation.')
    elif action == 'complete':
        if not blocks or any(task['status'] != 'DONE' for task in blocks):
            fail('Task queue is not complete.')
    elif action == 'untouched':
        # No task finished yet: the plan gate still applies (BLOCKED/IN_PROGRESS don't lift it).
        if not blocks or any(task['status'] == 'DONE' for task in blocks):
            fail('A task is already DONE (or there are no tasks).')
    elif action == 'next':
        by_id = {task['id']: task for task in blocks}
        eligible = [task for task in blocks if task['status'] in ('TODO', 'IN_PROGRESS')
                    and all(by_id[d]['status'] == 'DONE' for d in task['deps'])]
        active = next((task for task in eligible if task['status'] == 'IN_PROGRESS'), None)
        print((active or (eligible[0] if eligible else {'id': 'none'}))['id'])
    elif action == 'model':
        task = next((task for task in blocks if task['id'] == arguments[1]), None)
        if task is None:
            fail(f'Unknown task: {arguments[1]}')
        print(task['model'])
    elif action == 'count':
        print(len(blocks))
    elif action == 'progress':
        # One line for notifications: "<id> <title> (<done>/<total> done)".
        task = next((task for task in blocks if task['id'] == arguments[1]), None)
        if task is None:
            fail(f'Unknown task: {arguments[1]}')
        done = sum(t['status'] == 'DONE' for t in blocks)
        print(f"{task['id']} {task['title'][:80]} ({done}/{len(blocks)} done)")
    elif action in ('status', 'show', 'set'):
        task = next((task for task in blocks if task['id'] == arguments[1]), None)
        if task is None:
            fail(f'Unknown task: {arguments[1]}')
        if action == 'status':
            print(task['status'])
        elif action == 'show':
            print(f"{task['id']} {task['title']}\nStatus: {task['status']}\n"
                  f"Model: {task['model'] or 'default'}\nDependencies: {task['dependencies']}")
        else:
            if arguments[2] not in ('TODO', 'IN_PROGRESS', 'BLOCKED', 'DONE'):
                fail('Invalid task status.')
            path = Path('.ai/tasks.md')
            text = path.read_text()
            # Find real heading, not the code-fenced example, by exact task title.
            lines = text.splitlines(keepends=True)
            fence = None
            active = False
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
                    active = bool(re.match(r'^##\s+' + re.escape(task['id']) + r'\s+[—-]\s+', line))
                if active and line.startswith('Status:'):
                    lines[index] = f'Status: {arguments[2]}\n'
                    break
            atomic(path, ''.join(lines))


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
    # Only what the pipeline relies on is mandatory; the other sections are requested by the
    # prompt but a renamed one ("Missing coverage and limitations") must not discard a review.
    required = ('Overall verdict:', 'Finding counts:', '## BLOCKER findings', '## MAJOR findings',
                '## MINOR findings')
    for field in required:
        if field not in content:
            fail(f'Review is missing {field}; prior review preserved. Inspect local report.')
    review_counts(content)
    header = f'<!-- Host evidence: HEAD {head}; merge-base {base}; saved {now()}. -->\n\n'
    atomic('.ai/reviews/current.md', header + content)
    bind_review(head, header + content)


COUNTS = re.compile(r'^Finding counts:\s*BLOCKER=(\d+)\s+MAJOR=(\d+)\s+MINOR=(\d+)\s*$', re.M)


FINDING_ID = re.compile(r'^(?:#{2,6}\s+|[-*]\s+(?:\*\*)?)\s*([A-Z][A-Z0-9]{0,4}-?\d+)\b', re.M)
NONE_TEXT = re.compile(r'^(?:none|no findings|n/?a)\b', re.I)


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


DISPOSITION_ROW = re.compile(r'^\|\s*([A-Z][A-Z0-9]{0,4}-?\d+)\s*\|\s*(accepted|rejected|deferred)\s*\|'
                             r'\s*(.*?)\s*\|\s*(.*?)\s*\|', re.M | re.I)


def start_dispositions(arguments):
    """Host-written dispositions file bound to the current review's HEAD (Claude fills the rows)."""
    head = arguments[0]
    existing = Path('.ai/reviews/dispositions.md')
    if existing.exists() and re.search(r'^Review HEAD:\s*' + re.escape(head) + r'\s*$', existing.read_text(), re.M):
        return  # Already bound to this review (e.g. resuming an interrupted triage).
    atomic('.ai/reviews/dispositions.md', f"""# Review dispositions (Claude)

Review HEAD: {head}

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
""")


def triage_check(arguments):
    """Validate dispositions against the current review. Prints 'accepted=N deferred=M'.
    With --fresh (right after triage), accepted findings must point to open TODO tasks."""
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
    rows = {m.group(1): (m.group(2).lower(), m.group(3), m.group(4)) for m in DISPOSITION_ROW.finditer(text)}
    queue = {t['id']: t['status'] for t in tasks()}
    accepted = deferred = 0
    for level in ('BLOCKER', 'MAJOR'):
        for finding in finding_ids(review, level):
            if finding not in rows:
                fail(f'{level} finding {finding} has no disposition.')
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
    print(f'accepted={accepted} deferred={deferred}')


def binding_dir():
    """Host-only store of published review digests, outside the checkout (agent sessions
    get no write access there). Keyed by the repository's root commit and path."""
    base = os.environ.get('AI_STATE_DIR') or os.path.join(
        os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state'), 'ai-toolkit')
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return Path(base) / 'reviews' / key


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
        # An interrupted stage on this branch outlives a human restart: the pipeline
        # completes (or escalates) it before anything else.
        try:
            old = json.loads(path.read_text())
            if isinstance(old, dict) and old.get('branch') == branch and 'stage' in old:
                data['stage'] = old['stage']
        except (OSError, ValueError):
            pass
        atomic(path, json.dumps(data) + '\n')
        return
    try:
        data = json.loads(path.read_text())
        valid = (isinstance(data, dict) and isinstance(data.get('gate'), str)
                 and isinstance(data.get('branch'), str) and isinstance(data.get('args'), list)
                 and all(isinstance(a, str) for a in data['args'])
                 and type(data.get('attempts')) is int and 0 <= data['attempts'] <= 100)
    except (OSError, ValueError):
        valid = False
    if not valid:
        fail('No valid run manifest; rerun ai-pipeline --approved by hand.')
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
        data['attempts'] = 0
        atomic(path, json.dumps(data) + '\n')
    elif action == 'stage-set':
        # Recorded before the stage starts, bound to the verified review it works on.
        name, start = arguments[1], arguments[2]
        if name != 'triage' or not re.fullmatch(r'[0-9a-f]{40}', start):
            fail('Invalid stage.')
        review_info_values()
        data['stage'] = {'name': name, 'start_head': start, 'review_digest': review_digest()}
        atomic(path, json.dumps(data) + '\n')
    elif action == 'stage':
        # The open stage of this branch's run ('name start_head review_digest'), if any.
        stage = data.get('stage')
        if stage is None or data['branch'] != current_branch():
            return
        print(' '.join(stage_fields(stage)))
    elif action == 'stage-clear':
        data.pop('stage', None)
        atomic(path, json.dumps(data) + '\n')
    else:
        fail('Unknown run-manifest action.')


# Files a review triage may change: dispositions, the task queue and runner bookkeeping.
TRIAGE_RECORDS = ('.ai/tasks.md', '.ai/reviews/dispositions.md', '.ai/current-plan.md',
                  '.ai/state.md', '.ai/handoff.md', '.ai/run-log.md')
TRIAGE_COMMIT = 'chore(ai): record review triage'


def current_branch():
    try:
        return git('symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        return ''


def review_digest():
    return hashlib.sha256(Path('.ai/reviews/current.md').read_bytes()).hexdigest()


def stage_fields(stage):
    fields = [stage.get(key) if isinstance(stage, dict) else None
              for key in ('name', 'start_head', 'review_digest')]
    if fields[0] != 'triage' or not isinstance(fields[1], str) or not re.fullmatch(r'[0-9a-f]{40}', fields[1]) \
            or not isinstance(fields[2], str) or not re.fullmatch(r'[0-9a-f]{64}', fields[2]):
        fail('Triage stage: the run manifest holds an invalid stage record.')
    return fields


def changed_since(start):
    """Paths changed since START: committed, staged, unstaged and untracked (not ignored)."""
    names = git('diff', '--name-only', '--no-renames', '-z', start).split(b'\0')
    names += git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
    return sorted({os.fsdecode(name) for name in names if name})


def triage_scope(arguments):
    """Since START, only triage records changed (committed or not)."""
    start = arguments[0]
    if subprocess.run(['git', 'merge-base', '--is-ancestor', start, 'HEAD'],
                      stderr=subprocess.DEVNULL).returncode != 0:
        fail(f'{start[:12]} is not an ancestor of HEAD (history rewritten?).')
    outside = [name for name in changed_since(start) if name not in TRIAGE_RECORDS]
    if outside:
        fail('Triage changed files outside workflow records: ' + ' '.join(outside[:8])
             + (f' (+{len(outside) - 8} more)' if len(outside) > 8 else ''))


def stage_verify(arguments):
    """Verify an open triage stage before it is completed. Prints 'committed' when its counted
    commit already exists after start_head (close it without a second count), else 'pending'.
    Any mismatch fails: the caller escalates without implementation or counting."""
    path = binding_dir() / 'run.json'
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        fail('Triage stage: the run manifest is unreadable.')
    if not isinstance(data, dict) or 'stage' not in data:
        fail('Triage stage: no open stage in the run manifest.')
    _, start, digest = stage_fields(data['stage'])
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
    subjects = git('log', '--format=%s', f'{start}..HEAD').decode().splitlines()
    if TRIAGE_COMMIT not in subjects:
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
RECHECK_RECORDS = TRIAGE_RECORDS + ('.ai/reviews/current.md', '.ai/reviews/recheck.md', '.ai/reviews/disputes.md')
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
        rows[match.group(1)] = (match.group(2).lower(), match.group(3))
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
    extra or malformed counts as upheld (a re-check can only withdraw explicitly)."""
    answers = {finding: ('upheld', 'no valid answer (counted as upheld)') for finding in ids}
    notes = []
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError:
        data = None
    if not isinstance(data, dict) or set(data) != {'answers'} or not isinstance(data['answers'], list):
        return answers, ['the answer was not one JSON object {"answers": [...]}; every finding counts as upheld']
    seen = {}
    for entry in data['answers']:
        finding = entry.get('id') if isinstance(entry, dict) else None
        if not isinstance(finding, str) or finding not in answers:
            notes.append(f'ignored an answer for an unknown finding: {str(finding)[:40]!r}')
            continue
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
    cell = lambda value: ' '.join(value.split()).replace('|', '\\|')
    lines = [f'<!-- Host evidence: re-check of review {digest}; rejected rows {rows_hash}; '
             f'reviewed HEAD {head}; saved {now()}. -->', '',
             '# Re-check of rejected findings (Codex)', '',
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


def render_disputes(records):
    lines = ['# Disputed findings', '',
             '<!-- Host-written by ai-pipeline from host state; append-only. Never edit: a changed file',
             'fails verification. A dispute is never resolved automatically; the human resolves it',
             'at the pull request. -->', '']
    for number, record in enumerate(records, 1):
        lines += [f"## D{number} — {record['finding']} ({record['level']})", '',
                  f"- Review digest: {record['review_digest']}",
                  f"- Recorded: {record['date']}",
                  f"- Original finding: {record['finding_text']}",
                  f"- Claude's evidence: {record['evidence']}",
                  f"- Codex's answer: {record['answer']}", '']
    return '\n'.join(lines)


def disputes_values():
    """Verified dispute records: the file must be exactly what the host recorded."""
    records = dispute_records()
    actual = DISPUTES.read_text() if DISPUTES.exists() else None
    if actual != (render_disputes(records) if records else None):
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
    Prints the number of records added."""
    records = dispute_records()
    actual = DISPUTES.read_text() if DISPUTES.exists() else None
    prefixes = [None] + [render_disputes(records[:count]) for count in range(1, len(records) + 1)]
    if actual not in prefixes:
        fail('.ai/reviews/disputes.md does not match the dispute records the host wrote; '
             'restore it from Git (records are append-only and never edited).')
    _, digest, _, answers = recheck_values()
    _, rows = rejected_rows()
    review = Path('.ai/reviews/current.md').read_text()
    known = {(record['review_digest'], record['finding']) for record in records}
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
    if added:
        path = disputes_store()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, json.dumps(records, ensure_ascii=False, indent=1) + '\n')
    if records:
        atomic(DISPUTES, render_disputes(records))
    print(len(added))


RECOVER_ACTIONS = ('rerun', 'commit_and_rerun', 'escalate')
# Settings captured with the approved run and restored for its resumes.
RUN_SETTINGS = ('AI_NOTIFY_CMD', 'AI_MODEL', 'AI_REVIEW_MODEL', 'AI_REVIEW_EFFORT', 'AI_RECHECK_EFFORT',
                'AI_AUTO_RECOVER', 'AI_RECOVER_MAX', 'AI_LIMIT_RETRY', 'AI_LIMIT_MAX_WAIT')


def _no_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate key')
    return dict(pairs)


def recover_decision(arguments):
    """Parse the recovery session's verdict: 'action<TAB>reason<TAB>human_action'.
    Only a successful claude exit, a success envelope and exactly ONE complete decision
    object (no duplicate keys; the span from the first '{' to the last '}') count.
    Everything else escalates."""
    log, exit_code = arguments[0], arguments[1]
    escalate = 'escalate\tthe recovery session gave no valid decision\tinspect the stop yourself'
    try:
        envelope = json.loads(Path(log).read_text(), object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError):
        envelope = None
    if not isinstance(envelope, dict) or exit_code != '0' or envelope.get('is_error') is not False \
            or envelope.get('subtype') != 'success' or not isinstance(envelope.get('result'), str):
        print(escalate)
        return
    # The answer must be exactly one JSON object (optionally in a ```json fence), nothing else.
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', envelope['result'].strip())
    try:
        decision = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError:
        decision = None
    if not isinstance(decision, dict):
        print(escalate)
        return
    fields = (decision.get('action'), decision.get('reason'), decision.get('human_action', ''))
    if fields[0] not in RECOVER_ACTIONS or not all(isinstance(f, str) for f in fields) \
            or not fields[1].strip():
        print(escalate)
        return
    clean = lambda value: ' '.join(value.split())[:300]
    print(f'{fields[0]}\t{clean(fields[1])}\t{clean(fields[2])}')


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


def finish_summary(arguments):
    """The final notification: what was delivered and the human's todo list."""
    url, reviews, unresolved = arguments[0], arguments[1], arguments[2] == '1'
    blocks = tasks()
    done = sum(task['status'] == 'DONE' for task in blocks)
    handoff = Path('.ai/handoff.md').read_text() if Path('.ai/handoff.md').exists() else ''
    steps = [line for line in section(handoff, 'Manual testing for the human').splitlines()
             if re.match(r'^\s*(\d+[.)]|[-*])\s+\S', line)]
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
    todos.append(f'Test: {len(steps)} manual step(s) in the PR' if steps else 'Test the change (no manual steps were written)')
    todos.append('Merge the PR')
    todos += extra[:10]
    if len(extra) > 10:
        todos.append(f'...and {len(extra) - 10} more under "Human todos" in .ai/handoff.md')
    lines = [f'🏁 FINISHED: all {done}/{len(blocks)} tasks done and validated. {review}.', f'PR: {url}', 'Your todos:']
    lines += [f'{n}. {todo[:200]}' for n, todo in enumerate(todos, 1)]
    print('\n'.join(lines))


PLAN_REVIEW = Path('.ai/reviews/plan.md')
# Workflow records that change without changing what the plan review judged.
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
    for field in ('Finding counts:', '## BLOCKER findings', '## MAJOR findings', '## MINOR findings'):
        if field not in content:
            fail(f'Plan review is missing {field}; inspect the local report.')
    review_counts(content)
    content = f'<!-- Plan review of plan digest {arguments[1]}; saved {now()}. -->\n\n' + content
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


def pr_title(arguments):
    """PR title: first line of the spec objective, else the branch name."""
    objective = section(Path('.ai/project-spec.md').read_text(), 'Objective') if Path('.ai/project-spec.md').exists() else ''
    line = next((l.strip(' #-*') for l in objective.splitlines() if l.strip()), '')
    if not line:
        line = git('symbolic-ref', '--short', 'HEAD').decode().strip()
    print(line[:72])


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
    lines += ['## Tasks', '']
    for task in tasks():
        mark = {'DONE': 'x'}.get(task['status'], ' ')
        suffix = '' if task['status'] == 'DONE' else f" ({task['status']})"
        lines.append(f"- [{mark}] {task['id']} {task['title']}{suffix}")
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
    lines += ['## Independent review (Codex)', '']
    if review:
        verdict = re.search(r'^Overall verdict:\s*(.*)$', review, re.M)
        counts = COUNTS.search(review)
        verdict_text = verdict.group(1).strip().rstrip('.') if verdict else 'unknown'
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
    manual = section(handoff, 'Manual testing for the human')
    lines += ['## How to test', '', manual or 'See `.ai/handoff.md`.', '']
    lines += ['---', 'Opened by `ai-pipeline`. Merging and deployment remain with the human.', '',
              '🤖 Generated with [Claude Code](https://claude.com/claude-code)']
    print('\n'.join(lines))


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
    elif command == 'review-info':
        review_info(arguments)
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
    elif command == 'triage-scope':
        triage_scope(arguments)
    elif command == 'stage-verify':
        stage_verify(arguments)
    elif command == 'run-manifest':
        run_manifest(arguments)
    elif command == 'checkpoint-guard':
        checkpoint_guard(arguments)
    elif command == 'committed-matches-worktree':
        committed_matches_worktree(arguments)
    elif command == 'recover-decision':
        recover_decision(arguments)
    elif command == 'finish-summary':
        finish_summary(arguments)
    elif command == 'plan-digest':
        print(plan_digest())
    elif command == 'publish-plan-review':
        publish_plan_review(arguments)
    elif command == 'plan-review-info':
        plan_review_info(arguments)
    elif command == 'limit-check':
        limit_check(arguments)
    elif command == 'pr-title':
        pr_title(arguments)
    elif command == 'pr-body':
        pr_body(arguments)
    else:
        fail(f'Unknown helper command: {command}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
