"""Read-only pipeline dashboard: which checkouts run a pipeline, whether it is alive, and safe
terminal text. Nothing here writes a file: checkouts are read only through workflow.py's pinned,
bounded readers, processes only through a ProcSource (`/proc` or a test fixture tree)."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

# No __pycache__: .ai/bin is part of the approved gate digest.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow import (BOX_KEYS, DIR_FLAGS, NOTIFICATIONS_LIMIT, OBSERVATION_LIMIT,  # noqa: E402
                      OBSERVATION_STATES, SMALL_LIMIT, TASKS_LIMIT, checkout_fds, close_fds,
                      git_branch, read_record, state_root, task_blocks)
from watchdog import is_runner  # noqa: E402

PIPELINE_NAMES = ('ai-pipeline', 'ai-recover')
FROM_ENVIRONMENT = object()


class ProcSource:
    """Process facts in watchdog.py's semantics, read from ROOT (`AI_DASHBOARD_PROC`, test
    only, else `/proc`)."""

    def __init__(self, root=None):
        self.root = Path(root if root is not None else os.environ.get('AI_DASHBOARD_PROC', '/proc'))
        self.boot_ns = None

    def pids(self):
        try:
            return sorted((name for name in os.listdir(self.root) if name.isdigit()), key=int)
        except OSError:
            return []

    def process(self, pid):
        """(args, start ticks) of a live, non-zombie process, or None."""
        entry = self.root / str(pid)
        try:
            status = (entry / 'stat').read_bytes().rsplit(b')', 1)[1].split()
            args = (entry / 'cmdline').read_bytes().split(b'\0')
        except (OSError, IndexError):
            return None
        if len(status) < 20 or status[0] == b'Z' or not status[19].isdigit():
            return None
        return args, status[19].decode()

    def cwd(self, pid):
        try:
            return os.readlink(self.root / str(pid) / 'cwd')
        except OSError:
            return None

    def start_ns(self, ticks):
        """Process start (stat field 22, clock ticks since boot) as epoch ns."""
        if self.boot_ns is None:
            btime = re.search(rb'^btime (\d+)$', (self.root / 'stat').read_bytes(), re.M)
            self.boot_ns = int(btime[1]) * 1_000_000_000
        return self.boot_ns + int(ticks) * 1_000_000_000 // os.sysconf('SC_CLK_TCK')


def has_ai(checkout):
    """True for an absolute existing directory whose `.ai` is a real directory."""
    if not isinstance(checkout, str) or not os.path.isabs(checkout) or not os.path.isdir(checkout):
        return False
    fds = checkout_fds(checkout)
    if fds is None:
        return False
    close_fds(*fds)
    return True


def registered_checkouts():
    """Checkout paths named by `<state root>/pipelines/*.json`; unreadable entries skipped."""
    try:
        directory = os.open(state_root() / 'pipelines', DIR_FLAGS)
    except OSError:
        return []
    found = []
    try:
        for name in sorted(os.listdir(directory)):
            if name.startswith('.') or not name.endswith('.json'):
                continue
            record = read_record(directory, name, OBSERVATION_LIMIT)
            try:
                data = json.loads(record[0]) if record else None
            except ValueError:
                continue
            if isinstance(data, dict) and has_ai(data.get('checkout')):
                found.append(data['checkout'])
    except OSError:
        pass
    finally:
        close_fds(directory)
    return found


def inside(path, base):
    return os.path.commonpath([path, base]) == base


def discover(source=None, only_under=FROM_ENVIRONMENT):
    """[(checkout, [(pid, start ticks), ...])] for every registered checkout and every checkout
    a live runner works in, deduplicated by realpath; ONLY_UNDER (`AI_DASHBOARD_ROOT`, test
    only) keeps just the checkouts inside it."""
    source = source or ProcSource()
    if only_under is FROM_ENVIRONMENT:
        only_under = os.environ.get('AI_DASHBOARD_ROOT') or None
    base = os.path.realpath(only_under) if only_under else None
    checkouts = {}

    def add(checkout):
        real = os.path.realpath(checkout)
        if base and not inside(real, base):
            return None
        return checkouts.setdefault(real, (checkout, []))[1]

    for checkout in registered_checkouts():
        add(checkout)
    for pid in source.pids():
        found = source.process(pid)
        if not found or not is_runner(found[0]):
            continue
        cwd = source.cwd(pid)
        if not has_ai(cwd):
            continue
        runners = add(cwd)
        if runners is not None:
            runners.append((int(pid), found[1]))
    return sorted(checkouts.values())


def marker(local_fd):
    """(pid, mtime ns) of `.ai/local/pipeline.active` from one open, or None when it is absent
    or unreadable (a FIFO, a symlink, garbage)."""
    if local_fd is None:
        return None
    record = read_record(local_fd, 'pipeline.active', SMALL_LIMIT)
    if record is None:
        return None
    try:
        return int(record[0].split()[0]), record[1].st_mtime_ns
    except (ValueError, IndexError):
        return None


def liveness(local_fd, runners, source=None):
    """`alive`, `crashed` or `gone`, with watchdog.py's pipeline_died semantics."""
    source = source or ProcSource()
    snapshot = marker(local_fd)
    for _ in range(3):
        if snapshot is None:
            break
        pid, written = snapshot
        found = source.process(pid)
        # A reused PID started after the marker; ai-recover replaces the pipeline (same PID).
        if found and is_runner(found[0], PIPELINE_NAMES) \
                and source.start_ns(found[1]) <= written + 1_000_000_000:
            return 'alive'
        # A run that just finished removes its marker; only an unchanged marker is a crash.
        again = marker(local_fd)
        if again == snapshot:
            return 'crashed'
        snapshot = again
    # No marker: versions without pipeline.active are alive while a runner works there.
    return 'alive' if runners else 'gone'


ESCAPE = re.compile(r'''
      (?:\x1b\]|\x9d) .*? (?:\x07|\x1b\\|\x9c|\Z)               # OSC (BEL or ST)
    | (?:\x1b[P^_X]|[\x90\x98\x9e\x9f]) .*? (?:\x1b\\|\x9c|\Z)  # DCS, PM, APC, SOS
    | (?:\x1b\[|\x9b) [0-?]* [ -/]* [@-~]?                      # CSI, 7- and 8-bit
    | \x1b [ -/]* [0-~]?                                         # other escapes, bare ESC
''', re.S | re.X)
CONTROL = re.compile('[\x00-\x08\x0e-\x1f\x7f-\x9f‪-‮⁦-⁩]')


def sanitize(text, limit=200):
    """TEXT safe to print: no escape sequences, controls or bidi overrides, whitespace
    collapsed, at most LIMIT characters."""
    text = CONTROL.sub('', ESCAPE.sub('', str(text or '')))
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


STAGES = (*BOX_KEYS, 'none')
EVENT_COUNT = 20
HIDE_AFTER = 24 * 3600
RANK = {'needs_you': 0, 'crashed': 1, 'running': 2, 'paused': 2, 'recovering': 2, 'finished': 3,
        'idle': 4, 'unknown': 5}


def text_field(value, limit=200):
    return sanitize(value, limit) if isinstance(value, str) else ''


def observation_of(local_fd, seen):
    """The validated observation record, or None (absent, malformed, unknown stage or state)."""
    record = read_record(local_fd, 'observation.json', OBSERVATION_LIMIT) if local_fd is not None else None
    if record is None:
        return None
    seen.append(record[1].st_mtime)
    try:
        data = json.loads(record[0])
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get('stage') not in STAGES \
            or data.get('state') not in OBSERVATION_STATES:
        return None
    return {'stage': data['stage'], 'state': data['state'], 'detail': text_field(data.get('detail')),
            'note': text_field(data.get('note'), 400), 'since': text_field(data.get('since'), 40)}


def events_of(local_fd, seen):
    """The last EVENT_COUNT notification lines as {'ts', 'message'}; malformed lines skipped."""
    record = read_record(local_fd, 'notifications.log', NOTIFICATIONS_LIMIT, tail=True) \
        if local_fd is not None else None
    if record is None:
        return []
    seen.append(record[1].st_mtime)
    events = []
    for line in record[0].splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get('message'), str):
            events.append({'ts': text_field(data.get('ts'), 40), 'message': text_field(data['message'], 300)})
    return events[-EVENT_COUNT:]


def tasks_of(ai_fd, seen):
    """{'done', 'total', 'current'} counted like `tasks counts` (DONE over all blocks), or None."""
    record = read_record(ai_fd, 'tasks.md', TASKS_LIMIT)
    if record is None:
        return None
    seen.append(record[1].st_mtime)
    try:
        blocks = task_blocks(record[0])
    except (SystemExit, Exception):
        return None
    current = next((block['title'] for block in blocks if 'Status: IN_PROGRESS' in block['lines']), '')
    return {'done': sum('Status: DONE' in block['lines'] for block in blocks), 'total': len(blocks),
            'current': text_field(current, 120)}


def inspect(checkout, runners, now, source=None):
    """One checkout as a plain dict; every checkout-derived string is sanitised. A checkout whose
    records cannot be read safely comes back with status `unknown`."""
    run = {'project': text_field(os.path.basename(checkout.rstrip('/')) or checkout, 80),
           'checkout': text_field(checkout, 300), 'branch': 'unknown', 'liveness': 'gone',
           'observation': None, 'events': [], 'last_error': '', 'tasks': None, 'status': 'unknown',
           'stage': 'unknown', 'since': '', 'updated': 0.0}
    fds = checkout_fds(checkout)
    if fds is None:
        return run
    root_fd, ai_fd, local_fd = fds
    try:
        seen = []
        run['branch'] = text_field(git_branch(root_fd) or 'unknown', 120)
        run['liveness'] = liveness(local_fd, runners, source)
        observation = observation_of(local_fd, seen)
        observed = seen[0] if observation else 0.0
        run['observation'] = observation
        run['events'] = events_of(local_fd, seen)
        run['tasks'] = tasks_of(ai_fd, seen)
        error = read_record(local_fd, 'last-error', SMALL_LIMIT) if local_fd is not None else None
        errored = bool(error and error[1].st_mtime > observed)
        if error:
            seen.append(error[1].st_mtime)
        if errored:
            run['last_error'] = text_field((error[0].strip().splitlines() or [''])[0], 300)
        state = observation['state'] if observation else None
        if run['liveness'] == 'crashed':
            status = 'crashed'
        elif run['liveness'] == 'alive':
            status = state if state in ('paused', 'recovering') else 'running'
        elif state == 'stopped' or errored:
            status = 'needs_you'
        elif state == 'done':
            status = 'finished'
        else:
            status = 'idle'
        run.update(status=status, stage=observation['stage'] if observation else 'unknown',
                   since=observation['since'] if observation else '', updated=max(seen, default=0.0))
        return run
    finally:
        close_fds(root_fd, ai_fd, local_fd)


def snapshot(all_runs=False, now=None, source=None):
    """{'state_root', 'runs'}: needs_you, crashed, live, finished, idle, then newest first. Old
    (> 24 h) finished and idle runs are hidden unless ALL_RUNS."""
    now = time.time() if now is None else now
    source = source or ProcSource()
    runs = [inspect(checkout, runners, now, source) for checkout, runners in discover(source)]
    if not all_runs:
        runs = [run for run in runs
                if run['status'] not in ('finished', 'idle') or now - run['updated'] <= HIDE_AFTER]
    runs.sort(key=lambda run: (RANK[run['status']], -run['updated']))
    return {'state_root': str(state_root()), 'runs': runs}


def title_line(run):
    progress = f" · {run['tasks']['done']}/{run['tasks']['total']} tasks" if run['tasks'] else ''
    return f"{run['project']} · {run['branch']} · {run['status']}{progress}"


def stage_line(run):
    observation = run['observation']
    text = f"stage {run['stage']}"
    if observation:
        text += f" ({observation['state']})"
        extra = ' — '.join(part for part in (observation['detail'], observation['note']) if part)
        text += f' · {extra}' if extra else ''
    if run['last_error']:
        text += f" · error: {run['last_error']}"
    return text


def render_text(data):
    """Plain text: per run a title line, a compact stage line and the last event."""
    if not data['runs']:
        return f"No pipelines found (watching {data['state_root']}).\n"
    lines = []
    for run in data['runs']:
        event = run['events'][-1] if run['events'] else None
        lines += [title_line(run), '  ' + stage_line(run),
                  '  ' + (f"{event['ts']} {event['message']}" if event else 'no events')]
    return '\n'.join(lines) + '\n'


def main(arguments=None):
    parser = argparse.ArgumentParser(prog='ai-dashboard', description='Watch all pipelines on this machine.')
    parser.add_argument('--once', action='store_true', help='print the text view once and exit')
    parser.add_argument('--json', action='store_true', help='print the snapshot as JSON and exit')
    parser.add_argument('--all', action='store_true', help='also show old finished and idle runs')
    args = parser.parse_args(arguments)
    data = snapshot(args.all)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_text(data))
    return 0


if __name__ == '__main__':
    sys.exit(main())
