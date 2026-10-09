#!/usr/bin/env python3
"""Run the unittest suite in parallel shards (stdlib only).

Discovers the same tests as `python3 -m unittest discover -s tests`, deals the sorted test
IDs round-robin into AI_TEST_WORKERS shards (default min(8, CPU count)) and runs each shard
as `python3 -m unittest <ids...>` in its own process. Exits 1 when a shard fails or
crashes, when nothing was collected, or when the shards ran a different number of tests
than were collected.
"""
import argparse
import concurrent.futures
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


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
    # loaded by name in a shard, so run them here to print the import error.
    broken = [test for test in tests if test.id().startswith('unittest.loader.')]
    if broken:
        unittest.TextTestRunner(stream=sys.stdout).run(unittest.TestSuite(broken))
        print('run_parallel: test discovery failed (see the errors above)')
        sys.exit(1)
    return sorted(test.id() for test in tests)


ANSI = re.compile(r'\x1b\[[0-9;]*m')


def summary(output):
    """Return (tests run, OK/FAILED) from a shard's output, colored or plain."""
    plain = ANSI.sub('', output)
    ran = re.findall(r'^Ran (\d+) tests? in ', plain, re.M)
    status = re.findall(r'^(OK|FAILED)\b.*$', plain, re.M)
    return int(ran[-1]) if ran else None, status[-1] if status else None


def run_shard(ids, start_dir):
    env = dict(os.environ)
    # Colored output would hide the summary lines parsed below. PYTHON_COLORS=1 beats
    # NO_COLOR on Python 3.14+, so switch colors off explicitly.
    env.pop('FORCE_COLOR', None)
    env['NO_COLOR'] = '1'
    env['PYTHON_COLORS'] = '0'
    # Discovery IDs (test_workflow.X.test_y) only import with the start directory on the path.
    env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(start_dir), env.get('PYTHONPATH'))))
    result = subprocess.run([sys.executable, '-m', 'unittest', *ids], cwd=ROOT, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors='replace')
    ran, status = summary(result.stdout)
    return result.returncode, ran, status, result.stdout


def main():
    parser = argparse.ArgumentParser(description='Run the unittest suite in parallel shards.')
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
    shards = [ids[index::workers] for index in range(min(workers, len(ids)))]
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(shards)) as pool:
        results = list(pool.map(lambda shard: run_shard(shard, start_dir), shards))
    elapsed = time.monotonic() - started

    failed, total = [], 0
    for number, (returncode, ran, status, output) in enumerate(results, 1):
        total += ran or 0
        if returncode == 0 and ran is not None and status == 'OK':
            continue
        if ran is None or status is None:
            reason = f'crashed (exit code {returncode}) without a unittest summary'
        else:
            reason = f'{status} (exit code {returncode})'
        failed.append(number)
        print(f'===== shard {number}/{len(shards)}: {reason} =====')
        print(output.rstrip())
        print()
    problems = []
    if failed:
        problems.append('failing shards: ' + ', '.join(map(str, failed)))
    if total != len(ids):
        problems.append(f'count mismatch: ran {total} of {len(ids)} collected tests')
    print(f'Ran {total} tests in {elapsed:.1f}s ({len(shards)} shards, {len(ids)} collected)')
    if problems:
        print('FAILED (' + '; '.join(problems) + ')')
        return 1
    print('OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
