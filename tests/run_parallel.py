#!/usr/bin/env python3
"""Run the unittest suite in parallel batches (stdlib only).

Discovers the same tests as `python3 -m unittest discover -s tests`, deals the sorted test
IDs into interleaved batches pulled by AI_TEST_WORKERS workers (default min(8, CPU count))
and runs each batch as `python3 -m unittest <ids...>` in its own process. Exits 1 when a
batch fails or crashes, when nothing was collected, or when the batches ran a different
number of tests than were collected. On Python 3.12+ it also reports the slowest tests and
how busy each worker was.
"""
import argparse
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
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


class Dispatcher:
    """Worker threads pull batches from a shared queue; each batch is one child process.
    Stopping (interrupt or a worker error) terminates every running child."""

    def __init__(self, batches, workers, start_dir):
        self.batches = batches
        self.workers = min(workers, len(batches))
        self.start_dir = start_dir
        self.pending = queue.Queue()
        for number, batch in enumerate(batches, 1):
            self.pending.put((number, batch))
        self.lock = threading.Lock()
        self.stopping = threading.Event()
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
        return env

    def run_batch(self, ids):
        command = [sys.executable, '-m', 'unittest', *(['--durations', '0'] if TIMINGS else []), *ids]
        with self.lock:
            # Checked under the lock: stop() cannot miss a child started after it ran.
            if self.stopping.is_set():
                return None
            process = subprocess.Popen(command, cwd=ROOT, env=self.env(), stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, errors='replace')
            self.running.add(process)
        try:
            output, _ = process.communicate()
        finally:
            with self.lock:
                self.running.discard(process)
        ran, status = summary(output)
        return process.returncode, ran, status, output, durations(output)

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
        with self.lock:
            self.stopping.set()
            children = list(self.running)
        for process in children:
            process.terminate()
        for process in children:
            try:
                process.wait(timeout=TERMINATE_GRACE)
            except subprocess.TimeoutExpired:
                process.kill()

    def run(self):
        threads = [threading.Thread(target=self.work, args=(index,), daemon=True)
                   for index in range(self.workers)]
        for thread in threads:
            thread.start()
        try:
            for thread in threads:
                thread.join()
        except BaseException:
            self.stop()
            for thread in threads:
                thread.join()
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
    dispatcher = Dispatcher(batches, workers, start_dir)
    started = time.monotonic()
    results = dispatcher.run()
    elapsed = time.monotonic() - started

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
    print(f'Ran {total} tests in {elapsed:.1f}s '
          f'({len(batches)} batches on {dispatcher.workers} workers, {len(ids)} collected)')
    if problems:
        print('FAILED (' + '; '.join(problems) + ')')
        return 1
    print('OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
