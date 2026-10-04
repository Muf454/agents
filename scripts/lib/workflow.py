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
    for name in ('ai-run', 'ai-pipeline', 'ai-check', 'ai-status', 'ai-review', 'ai-watchdog', 'ai-recover',
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
    elif action in ('status', 'set'):
        task = next((task for task in blocks if task['id'] == arguments[1]), None)
        if task is None:
            fail(f'Unknown task: {arguments[1]}')
        if action == 'status':
            print(task['status'])
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


def publish_review(arguments):
    source, head, base = arguments
    content = Path(source).read_text()
    required = ('Overall verdict:', 'Finding counts:', '## BLOCKER findings', '## MAJOR findings',
                '## MINOR findings', '## Missing test coverage', '## Security concerns',
                '## Architecture concerns', '## Manual testing recommendations')
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
        atomic(path, json.dumps({'gate': gate, 'branch': branch, 'args': args, 'attempts': 0}) + '\n')
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
    elif action == 'reserve-attempt':
        # Reserved before any fallible recovery work, so failures can't retry for free.
        data['attempts'] += 1
        atomic(path, json.dumps(data) + '\n')
        print(data['attempts'])
    elif action == 'clear-attempts':
        data['attempts'] = 0
        atomic(path, json.dumps(data) + '\n')
    else:
        fail('Unknown run-manifest action.')


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


RECOVER_ACTIONS = ('rerun', 'commit_and_rerun', 'escalate')


def recover_decision(arguments):
    """Parse the recovery session's verdict: 'action<TAB>reason<TAB>human_action'.
    Only a successful claude exit, a success envelope and exactly one valid decision
    object count; everything else escalates."""
    log, exit_code = arguments[0], arguments[1]
    escalate = 'escalate\tthe recovery session gave no valid decision\tinspect the stop yourself'
    try:
        envelope = json.loads(Path(log).read_text())
    except (OSError, ValueError):
        print(escalate)
        return
    result = envelope.get('result') if isinstance(envelope, dict) else None
    if exit_code != '0' or envelope.get('is_error') is not False or envelope.get('subtype') != 'success' \
            or not isinstance(result, str):
        print(escalate)
        return
    decisions = []
    for match in re.finditer(r'\{[^{}]*\}', result):
        try:
            candidate = json.loads(match.group(0))
        except ValueError:
            continue
        if isinstance(candidate, dict) and 'action' in candidate:
            decisions.append(candidate)
    if len(decisions) != 1:
        print(escalate)
        return
    decision = decisions[0]
    fields = (decision.get('action'), decision.get('reason'), decision.get('human_action', ''))
    if decision['action'] not in RECOVER_ACTIONS or not all(isinstance(f, str) for f in fields) \
            or not fields[1].strip():
        print(escalate)
        return
    clean = lambda value: ' '.join(value.split())[:300]
    print(f'{fields[0]}\t{clean(fields[1])}\t{clean(fields[2])}')


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
    elif command == 'run-manifest':
        run_manifest(arguments)
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
