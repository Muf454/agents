#!/usr/bin/env python3
"""Run the unittest suite in parallel batches (stdlib only).

Discovers the same tests as `python3 -m unittest discover -s tests`, deals the sorted test
IDs into interleaved batches pulled by AI_TEST_WORKERS workers (default min(8, CPU count))
and runs each batch as `python3 -m unittest <ids...>` in its own process. Exits 1 when a
batch fails or crashes, when nothing was collected, or when the batches ran a different
number of tests than were collected. On Python 3.12+ it also reports the slowest tests and
how busy each worker was. Each batch runs in its own process group; an interrupt, SIGTERM or
a crashed worker terminates every running group, so subprocesses the tests started go too. On
Linux the runner is a child subreaper: it adopts the batches' orphaned descendants and reaps
them, so they stay its descendants, and a stop terminates that whole descendant tree (GNU
`timeout` groups, detached sessions) and waits until /proc shows none alive; when some
survive it says so on stderr and exits non-zero. When the caller sets no TMPDIR and /dev/shm is a writable,
executable tmpfs with 1 GiB free, the batches get a temporary directory there (removed after
the run); AI_TEST_TMPFS=0 turns that off.
"""
import argparse
import ctypes
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Several batches per worker, so a worker that drew slow tests does not hold up the end of
# the run while the others sit idle.
BATCHES_PER_WORKER = 6
# `python3 -m unittest --durations` exists from Python 3.12.
TIMINGS = sys.version_info >= (3, 12)
SLOWEST_SHOWN = 15
TERMINATE_GRACE = 5
# After a stop, how often a batch's reader checks, and how long it waits for EOF on a pipe
# that a process outside the batch's process group (one that started its own session) holds.
DRAIN_POLL = 0.5
DRAIN_GRACE = 2 * TERMINATE_GRACE
# Stopping the descendant tree (Linux, subreaper): /proc poll interval, SIGKILL rounds, and
# how long the completion barrier waits for the last descendants to die.
KILL_POLL = 0.1
KILL_ROUNDS = 3
FINAL_WAIT = TERMINATE_GRACE


def worker_count():
    raw = os.environ.get('AI_TEST_WORKERS', '').strip()
    if not raw:
        return min(8, os.cpu_count() or 1)
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        sys.exit(f'run_parallel: AI_TEST_WORKERS must be a positive integer, got {raw!r}')
    return value


TMPFS_MIN_FREE = 1 << 30
PROBE_TIMEOUT = 30


def exec_probe(directory):
    """True when a script written into `directory` can be executed directly (a writable
    mount may be noexec, and fixtures run mock agents and toolkit scripts from their temp dirs)."""
    script = Path(directory) / 'probe.sh'
    try:
        script.write_text('#!/bin/sh\necho probe-ok\n')
        os.chmod(script, 0o700)
        result = subprocess.run([str(script)], capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == 'probe-ok'


def choose_temp_dir(candidate, probe=exec_probe, statvfs=os.statvfs):
    """Return a fresh `ai-tests-*` directory under `candidate` (a tmpfs such as /dev/shm) for
    the batches' TMPDIR, or None to keep the default temp dir. Needs a writable candidate with
    1 GiB free; a candidate that cannot run scripts is removed again and reported."""
    candidate = str(candidate)
    if not os.path.isdir(candidate) or not os.access(candidate, os.W_OK | os.X_OK):
        return None
    try:
        stats = statvfs(candidate)
    except OSError:
        return None
    if stats.f_bavail * stats.f_frsize < TMPFS_MIN_FREE:
        return None
    created = None
    usable = False
    if not stats.f_flag & os.ST_NOEXEC:
        try:
            created = tempfile.mkdtemp(prefix='ai-tests-', dir=candidate)
            usable = bool(probe(created))
        except (OSError, subprocess.SubprocessError):
            usable = False
    if usable:
        return created
    if created:
        shutil.rmtree(created, ignore_errors=True)
    print(f'Temp dir: default ({candidate} not executable)')
    return None


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def collect(start_dir):
    tests = list(flatten(unittest.defaultTestLoader.discover(str(start_dir))))
    # Modules that fail to import are reported as synthetic tests; their IDs cannot be
    # loaded by name in a batch, so run them here to print the import error.
    broken = [test for test in tests if test.id().startswith('unittest.loader.')]
    if broken:
        unittest.TextTestRunner(stream=sys.stdout).run(unittest.TestSuite(broken))
        print('run_parallel: test discovery failed (see the errors above)')
        sys.exit(1)
    return sorted(test.id() for test in tests)


def make_batches(ids, workers):
    """Deal sorted IDs into interleaved batches: neighbours (often similar, similarly slow
    tests of one class) land in different batches."""
    count = min(len(ids), workers * BATCHES_PER_WORKER)
    return [ids[index::count] for index in range(count)]


ANSI = re.compile(r'\x1b\[[0-9;]*m')


def summary(output):
    """Return (tests run, OK/FAILED) from a batch's output, colored or plain."""
    plain = ANSI.sub('', output)
    ran = re.findall(r'^Ran (\d+) tests? in ', plain, re.M)
    status = re.findall(r'^(OK|FAILED)\b.*$', plain, re.M)
    return int(ran[-1]) if ran else None, status[-1] if status else None


DURATION = re.compile(r'^\s*(\d+(?:\.\d+)?)s\s+(\S.*?)\s*$')


def durations(output):
    """Return [(seconds, test name)] from the last "Slowest test durations" block of a
    batch's output. Lines that do not parse are ignored, so format drift loses timings
    rather than failing the run."""
    lines = ANSI.sub('', output).splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == 'Slowest test durations']
    if not starts:
        return []
    found = []
    for line in lines[starts[-1] + 1:]:
        if line.startswith('Ran '):
            break
        match = DURATION.match(line)
        if match:
            found.append((float(match.group(1)), match.group(2)))
    return found


def signal_group(process, signum):
    """Signal the process group a batch leads (pgid == its pid: start_new_session); a group
    that is already gone is fine."""
    try:
        os.killpg(process.pid, signum)
    except (ProcessLookupError, PermissionError):
        pass


PR_SET_CHILD_SUBREAPER = 36


def enable_subreaper():
    """Make this process the child subreaper of its descendants (Linux): an orphan is
    reparented here instead of to init. True when that worked."""
    if not sys.platform.startswith('linux'):
        return False
    try:
        return ctypes.CDLL(None, use_errno=True).prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0
    except (OSError, AttributeError):
        return False


def parse_stat(text):
    """Return (state, ppid, starttime) from the text (or bytes) of /proc/<pid>/stat, or None.
    The fields are read after the LAST ')': the command name may contain spaces and
    parentheses. It is arbitrary bytes too (any process can set it with PR_SET_NAME), so
    bytes are decoded losslessly; only the numeric fields after it are used."""
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'surrogateescape')
    try:
        fields = text.rsplit(')', 1)[1].split()
        return fields[0], int(fields[1]), int(fields[19])
    except (IndexError, ValueError):
        return None


def proc_stat(pid):
    # Bytes, not text: a strict decode of a non-UTF-8 name of ANY process on the host would
    # raise out of process_table(). One odd entry is skipped, never fatal.
    try:
        return parse_stat(Path(f'/proc/{pid}/stat').read_bytes())
    except (OSError, ValueError):
        return None


def process_table():
    """Return {pid: (state, ppid, starttime)} from one scan of /proc ({} where there is none)."""
    try:
        entries = os.listdir('/proc')
    except OSError:
        return {}
    found = {}
    for entry in entries:
        if entry.isdigit():
            stat = proc_stat(entry)
            if stat:
                found[int(entry)] = stat
    return found


def children_of(pid):
    """Return {child pid: (state, ppid, starttime)} for the children of `pid`, from one scan
    of /proc ({} where there is no /proc)."""
    return {child: stat for child, stat in process_table().items() if stat[1] == pid}


def descendants(root, table=None):
    """Return {pid: (state, starttime)} for every descendant of `root` (root excluded), by
    walking the ppid map of one /proc scan. A process that forks or is reparented during the
    scan may be missed; callers walk again."""
    table = process_table() if table is None else table
    children = {}
    for pid, (state, ppid, starttime) in table.items():
        children.setdefault(ppid, []).append(pid)
    found, todo = {}, [root]
    while todo:
        for child in children.get(todo.pop(), ()):
            if child not in found and child != root:
                found[child] = (table[child][0], table[child][2])
                todo.append(child)
    return found


def signal_pid(pid, starttime, signum):
    """Signal `pid` only while /proc still shows the process recorded with `starttime`: a pid
    that ended and was reused belongs to someone else."""
    stat = proc_stat(pid)
    if stat is None or stat[2] != starttime:
        return
    try:
        os.kill(pid, signum)
    except (ProcessLookupError, PermissionError):
        pass


class Dispatcher:
    """Worker threads pull batches from a shared queue; each batch is one child process in its
    own process group. Stopping (interrupt or a worker error) terminates every running group.
    With `reap` (the runner is a subreaper) run() also reaps the orphans it adopts, and stop()
    terminates every descendant of this process."""

    def __init__(self, batches, workers, start_dir, tmpdir=None, reap=False):
        self.batches = batches
        self.reap = reap
        self.tmpdir = tmpdir
        self.workers = min(workers, len(batches))
        self.start_dir = start_dir
        self.pending = queue.Queue()
        for number, batch in enumerate(batches, 1):
            self.pending.put((number, batch))
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.stopped_at = None
        # Set (under the lock) by the first stop() caller, which owns the shutdown; stop_done
        # is set when that shutdown has finished, also when it failed.
        self.terminating = False
        self.stop_done = threading.Event()
        self.kill_rounds = 0
        self.cleanup_failed = []
        self.scan_error = None
        self.running = set()
        self.results = {}
        self.busy = [0.0] * self.workers
        self.errors = []

    def env(self):
        env = dict(os.environ)
        # Colored output would hide the summary lines parsed below. PYTHON_COLORS=1 beats
        # NO_COLOR on Python 3.14+, so switch colors off explicitly.
        env.pop('FORCE_COLOR', None)
        env['NO_COLOR'] = '1'
        env['PYTHON_COLORS'] = '0'
        # Discovery IDs (test_workflow.X.test_y) only import with the start directory on the path.
        env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(self.start_dir), env.get('PYTHONPATH'))))
        if self.tmpdir:
            env['TMPDIR'] = self.tmpdir
        return env

    def run_batch(self, ids):
        command = [sys.executable, '-m', 'unittest', *(['--durations', '0'] if TIMINGS else []), *ids]
        with self.lock:
            # Checked under the lock: stop() cannot miss a child started after it ran.
            if self.stopping.is_set():
                return None
            # Its own session/process group, so stop() reaches the subprocesses its tests start.
            process = subprocess.Popen(command, cwd=ROOT, env=self.env(), stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, errors='replace', start_new_session=True)
            self.running.add(process)
        try:
            output = self.drain(process)
        finally:
            with self.lock:
                self.running.discard(process)
        ran, status = summary(output)
        return process.returncode, ran, status, output, durations(output)

    def drain(self, process):
        """Read the batch's output until EOF. Unbounded while the run goes on (the per-test
        timeouts own that); after stop() it gives up DRAIN_GRACE later, when a process that
        left the batch's group still holds the pipe."""
        while True:
            try:
                return process.communicate(timeout=DRAIN_POLL)[0]
            except subprocess.TimeoutExpired:
                if self.stopped_at is None or time.monotonic() - self.stopped_at < DRAIN_GRACE:
                    continue
            process.kill()
            process.stdout.close()
            process.wait()
            return ''

    def work(self, index):
        while not self.stopping.is_set():
            try:
                number, ids = self.pending.get_nowait()
            except queue.Empty:
                return
            started = time.monotonic()
            try:
                result = self.run_batch(ids)
            except BaseException as error:
                with self.lock:
                    self.errors.append(error)
                self.stop()
                return
            if result is None:
                return
            with self.lock:
                self.busy[index] += time.monotonic() - started
                self.results[number] = result

    def stop(self):
        """Terminate the running batches (and, as subreaper, every descendant). Idempotent:
        the first caller does the work, later callers wait until it has finished."""
        with self.lock:
            self.stopping.set()
            if self.stopped_at is None:
                self.stopped_at = time.monotonic()
            owner = not self.terminating
            self.terminating = True
            children = list(self.running)
        if not owner:
            self.stop_done.wait()
            return
        # Outside the lock: no batch can start once `stopping` is set.
        try:
            self.kill_rounds += 1
            self.terminate(children)
        finally:
            self.stop_done.set()
        if self.reap:
            self.reap_adopted(after_stop=True)

    def live_descendants(self):
        """{pid: starttime} of the descendants of this process that are not zombies."""
        return {pid: starttime for pid, (state, starttime) in descendants(os.getpid()).items()
                if state != 'Z'}

    def scan(self):
        """live_descendants(), or None when the scan raised: a scan failure must never abort a
        stop (stop_done is set regardless, so nobody would retry the cleanup)."""
        try:
            return self.live_descendants()
        except Exception as error:
            self.scan_error = error
            return None

    def terminate(self, children):
        # The batch groups first: they need no scan, so a failing scan cannot spare them.
        for process in children:
            signal_group(process, signal.SIGTERM)
        tree = (self.scan() or {}) if self.reap else {}
        # GNU `timeout` and detached sessions are outside the batches' groups.
        for pid, starttime in tree.items():
            signal_pid(pid, starttime, signal.SIGTERM)
        deadline = time.monotonic() + TERMINATE_GRACE
        for process in children:
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        while tree and time.monotonic() < deadline:
            live = self.scan() or {}
            if not any(live.get(pid) == starttime for pid, starttime in tree.items()):
                break
            time.sleep(KILL_POLL)
        # Also descendants that ignored SIGTERM or outlived their batch process.
        for process in children:
            signal_group(process, signal.SIGKILL)
        if not self.reap:
            return
        # Every walk kills what it finds, so a process forked during the stop goes too.
        # Zombies are left alone: reap_adopted() waits until stop_done, so their pids stay
        # reserved and a SIGKILL never reaches a reused pid.
        for _ in range(KILL_ROUNDS):
            live = self.scan()
            if live == {}:
                break
            for pid, starttime in (live or {}).items():
                signal_pid(pid, starttime, signal.SIGKILL)
            time.sleep(KILL_POLL)
        # Completion barrier: SIGKILL is asynchronous, only /proc says a process is gone. A
        # failed scan proves nothing, so the barrier keeps scanning until its deadline.
        deadline = time.monotonic() + FINAL_WAIT
        while True:
            live = self.scan()
            if live == {}:
                return
            if time.monotonic() >= deadline:
                break
            for pid, starttime in (live or {}).items():
                signal_pid(pid, starttime, signal.SIGKILL)
            time.sleep(KILL_POLL)
        if live is None:
            self.cleanup_failed = [f'unknown (descendant scan failed: {self.scan_error!r})']
        else:
            self.cleanup_failed = sorted(live)
        print('run_parallel: could not terminate descendants: ' + ' '.join(map(str, self.cleanup_failed)),
              file=sys.stderr, flush=True)

    def reap_adopted(self, after_stop=False):
        """Reap the zombie children of this process that are not batches (orphans adopted as
        subreaper). Under the lock: batches start under it, so a just-started batch is always
        in self.running and its status stays with its Popen. Never os.waitpid(-1, ...): it can
        take a batch's status, and Popen then reports exit 0. Does nothing while a stop is in
        progress (its owner passes after_stop once it is done)."""
        with self.lock:
            if self.terminating and not self.stop_done.is_set() and not after_stop:
                return
            batches = {process.pid for process in self.running}
            for pid, (state, _, _) in children_of(os.getpid()).items():
                if state == 'Z' and pid not in batches:
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        pass

    def run(self):
        threads = [threading.Thread(target=self.work, args=(index,), daemon=True)
                   for index in range(self.workers)]
        # The start loop is inside the try: an interrupt during a later start() must still stop
        # the batch an earlier worker launched. Only started threads can be joined.
        started = []
        try:
            for thread in threads:
                thread.start()
                started.append(thread)
            for thread in threads:
                if not self.reap:
                    thread.join()
                    continue
                thread.join(timeout=DRAIN_POLL)
                while thread.is_alive():
                    self.reap_adopted()
                    thread.join(timeout=DRAIN_POLL)
            if self.reap:
                self.reap_adopted()
        except BaseException:
            self.stop()
            for thread in started:
                thread.join()
            if self.reap:
                self.reap_adopted()
            raise
        if self.errors:
            raise self.errors[0]
        return [self.results[number] for number in range(1, len(self.batches) + 1)]


def timing_report(timings, busy, workers):
    if TIMINGS:
        print(f'Slowest {min(SLOWEST_SHOWN, len(timings))} tests:')
        for seconds, name in sorted(timings, key=lambda item: item[0], reverse=True)[:SLOWEST_SHOWN]:
            print(f'  {seconds:8.3f}s  {name}')
        total = f'{sum(seconds for seconds, _ in timings):.1f} s'
    else:
        total = 'not measured (Python < 3.12)'
    print(f'Test time: {total} across {workers} workers; '
          f'worker busy: {min(busy):.1f}–{max(busy):.1f} s')


def terminated(signum, frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description='Run the unittest suite in parallel batches.')
    parser.add_argument('--start-dir', default=str(ROOT / 'tests'),
                        help='discovery directory (default: the tests directory of this repository)')
    parser.add_argument('--collect-only', action='store_true',
                        help='print the number of collected tests and exit')
    args = parser.parse_args()
    start_dir = Path(args.start_dir).resolve()
    if not start_dir.is_dir():
        parser.error(f'--start-dir is not a directory: {start_dir}')
    workers = worker_count()
    ids = collect(start_dir)
    if args.collect_only:
        print(f'Collected {len(ids)} tests')
        return 0
    if not ids:
        print(f'run_parallel: no tests collected in {start_dir}')
        return 1
    batches = make_batches(ids, workers)
    tmpdir = None
    if not os.environ.get('TMPDIR') and os.environ.get('AI_TEST_TMPFS', '1') != '0':
        # AI_TEST_TMPFS_DIR is test-only: it points the candidate somewhere other than /dev/shm.
        tmpdir = choose_temp_dir(os.environ.get('AI_TEST_TMPFS_DIR') or '/dev/shm')
        if tmpdir:
            print(f'Temp dir: {tmpdir} (tmpfs)')
    # The batches are outside this process group, so a group-wide SIGTERM (ai-check's
    # `timeout`) misses them: turn it into an exception that makes run() stop them.
    signal.signal(signal.SIGTERM, terminated)
    try:
        # Here only, never at import: tests import this module and must not become subreapers.
        dispatcher = Dispatcher(batches, workers, start_dir, tmpdir, reap=enable_subreaper())
        started = time.monotonic()
        results = dispatcher.run()
        elapsed = time.monotonic() - started
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    failed, total, timings = [], 0, []
    for number, (returncode, ran, status, output, found) in enumerate(results, 1):
        total += ran or 0
        timings.extend(found)
        if returncode == 0 and ran is not None and status == 'OK':
            continue
        if ran is None or status is None:
            reason = f'crashed (exit code {returncode}) without a unittest summary'
        else:
            reason = f'{status} (exit code {returncode})'
        failed.append(number)
        print(f'===== batch {number}/{len(batches)}: {reason} =====')
        print('Tests in this batch:')
        for test_id in batches[number - 1]:
            print(f'  {test_id}')
        print(output.rstrip())
        print()
    timing_report(timings, dispatcher.busy, dispatcher.workers)
    problems = []
    if failed:
        problems.append('failing batches: ' + ', '.join(map(str, failed)))
    if total != len(ids):
        problems.append(f'count mismatch: ran {total} of {len(ids)} collected tests')
    if dispatcher.cleanup_failed:
        problems.append('descendants survived the stop: ' + ' '.join(map(str, dispatcher.cleanup_failed)))
    print(f'Ran {total} tests in {elapsed:.1f}s '
          f'({len(batches)} batches on {dispatcher.workers} workers, {len(ids)} collected)')
    if problems:
        print('FAILED (' + '; '.join(problems) + ')')
        return 1
    print('OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
