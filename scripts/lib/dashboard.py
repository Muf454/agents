"""Read-only pipeline dashboard: which checkouts run a pipeline, whether it is alive, and safe
terminal text. Nothing here writes a file: checkouts are read only through workflow.py's pinned,
bounded readers, processes only through a ProcSource (`/proc` or a test fixture tree)."""
import json
import os
from pathlib import Path
import re
import sys

# No __pycache__: .ai/bin is part of the approved gate digest.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow import (DIR_FLAGS, OBSERVATION_LIMIT, SMALL_LIMIT, checkout_fds, close_fds,  # noqa: E402
                      read_record, state_root)
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
