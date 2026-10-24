"""Flow event log (ME-01): envelope, schema, bounded lock, guarded writer, tolerant reader."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation  # noqa: E402,F401  (first: host state goes to a temp dir)
from timeouts import TIMEOUT_SCALE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/lib/workflow.py'
COMMON = ROOT / 'scripts/lib/common.sh'
GATE_ID = '0123456789abcdef'
# A bounded wait plus process start-up and git calls, never a tight duration.
BOUND = 8 * TIMEOUT_SCALE
COMMAND_TIMEOUT = 60 * TIMEOUT_SCALE

_spec = importlib.util.spec_from_file_location('workflow_events', HELPER)
workflow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workflow)

HOLDER = r'''
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_SH if sys.argv[2] == 'shared' else fcntl.LOCK_EX)
print('ready', flush=True)
sys.stdin.read()
'''

APPENDER = r'''
import importlib.util, os, sys, time
spec = importlib.util.spec_from_file_location('workflow', sys.argv[1])
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
while not os.path.exists(sys.argv[2]):
    time.sleep(0.005)
for n in range(50):
    try:
        if not workflow.append_event('gate', {'gate_id': '0123456789abcdef', 'seconds': n}, 'p', 'b'):
            print('short write', file=sys.stderr)
    except workflow.EventsBusy:
        print('Note: busy', file=sys.stderr)
'''

# One active run per process: 200 events of its run, each followed by a droppable filler event.
ROTATOR = r'''
import importlib.util, os, sys, time
spec = importlib.util.spec_from_file_location('workflow', sys.argv[1])
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
run = sys.argv[3]
while not os.path.exists(sys.argv[2]):
    time.sleep(0.005)
for n in range(200):
    for run_id, stage in ((run, f'{run}-{n}'), (None, 'filler')):
        if run_id:
            os.environ['AI_RUN_ID'] = run_id
        else:
            os.environ.pop('AI_RUN_ID', None)
        try:
            if not workflow.append_event('stop', {'stage': stage, 'message': 'm' * 100}, 'p', 'b'):
                print('short write', file=sys.stderr)
        except workflow.EventsBusy:
            print('Note: busy', file=sys.stderr)
'''
MIN_CAP = '65536'


def event_line(run, when, kind='stop', **fields):
    record = {'v': 1, 'id': os.urandom(8).hex(), 'time': when, 'kind': kind, 'project': 'p',
              'branch': 'b', 'run': run, **dict.fromkeys(workflow.EVENT_KINDS.get(kind, {})), **fields}
    return json.dumps(record, sort_keys=True) + '\n'


def stamp(**ago):
    return (datetime.now(timezone.utc) - timedelta(**ago)).strftime('%Y-%m-%dT%H:%M:%SZ')


class EventsFixture(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='ai-events-'))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.state = self.base / 'state'
        self.repo = self.base / 'events-project'
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ('AI_RUN_ID', 'AI_EVENTS_LOCK_SECONDS', 'AI_EVENTS_MAX_BYTES', 'AI_GATE_BROKEN')}
        self.env.update(AI_STATE_DIR=str(self.state), XDG_CONFIG_HOME=str(self.base / 'config'),
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=self.repo, env=self.env, check=True)
        patch = mock.patch.dict(os.environ, {'AI_STATE_DIR': str(self.state)})
        patch.start()
        self.addCleanup(patch.stop)
        for name in ('AI_EVENTS_LOCK_SECONDS', 'AI_EVENTS_MAX_BYTES', 'AI_RUN_ID'):
            os.environ.pop(name, None)

    def event(self, *args, cwd=None, **env):
        return subprocess.run([sys.executable, str(HELPER), 'event', *args], cwd=cwd or self.repo,
                              env={**self.env, **env}, capture_output=True, text=True,
                              timeout=COMMAND_TIMEOUT)

    def shell(self, script, *args, common=COMMON, **env):
        return subprocess.run(['bash', '-c', f'source "$1"; shift\n{script}', 'events-test', str(common), *args],
                              cwd=self.repo, env={**self.env, **env}, capture_output=True, text=True,
                              timeout=COMMAND_TIMEOUT)

    def lines(self):
        path = self.state / 'events.jsonl'
        return path.read_text().splitlines() if path.exists() else []

    def records(self):
        return [json.loads(line) for line in self.lines()]

    def holder(self, mode):
        self.state.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen([sys.executable, '-c', HOLDER, str(self.state / 'events.lock'), mode],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.release, process)
        self.assertEqual(process.stdout.readline().strip(), 'ready')
        return process

    def release(self, process):
        process.kill()
        process.wait(timeout=COMMAND_TIMEOUT)
        process.stdin.close()
        process.stdout.close()


class EventsCoreTests(EventsFixture):
    def test_events_core_envelope_and_run_tag(self):
        self.assertFalse(set(workflow.EVENT_ENVELOPE) & {f for fields in workflow.EVENT_KINDS.values() for f in fields})
        result = self.event('gate', f'gate_id={GATE_ID}', 'task=T201', 'start=1700000000', 'seconds=12',
                            'tests=40', 'failures=-', 'result=pass', AI_RUN_ID='a1' * 8)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        for run_id in ('', 'A1' * 8, 'abc', 'a1' * 8 + '0'):
            self.assertEqual(self.event('stop', 'stage=final', AI_RUN_ID=run_id).returncode, 0)
        self.assertEqual(self.event('stop', 'stage=final').returncode, 0)  # AI_RUN_ID unset
        gate, *stops = self.records()
        self.assertEqual(gate['run'], 'a1' * 8)
        self.assertEqual([stop['run'] for stop in stops], [None] * 5)
        self.assertEqual((gate['v'], gate['kind'], gate['project'], gate['branch']),
                         (1, 'gate', 'events-project', 'main'))
        self.assertRegex(gate['id'], r'^[0-9a-f]{16}$')
        self.assertRegex(gate['time'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertEqual({k: gate[k] for k in workflow.EVENT_KINDS['gate']},
                         {'gate_id': GATE_ID, 'task': 'T201', 'stage': None, 'start': 1700000000, 'seconds': 12,
                          'tests': 40, 'failures': None, 'workers': None, 'result': 'pass'})
        self.assertEqual(len({record['id'] for record in self.records()}), 6)
        self.assertEqual(self.event('ruling', 'ruling_kind=queue-order', 'key=T004', 'task=T004').returncode, 0)
        ruling = [e for e in workflow.read_events() if e['kind'] == 'ruling']
        self.assertEqual(len(ruling), 1)
        self.assertEqual((ruling[0]['kind'], ruling[0]['ruling_kind'], ruling[0]['key']),
                         ('ruling', 'queue-order', 'T004'))

    def test_events_core_cli_rejects_unknown_kind_field_type_and_envelope_names(self):
        gate = f'gate_id={GATE_ID}'
        for args in (['nope'], [], ['gate', gate, 'bogus=1'], ['gate', gate, 'kind=stop'],
                     ['gate', gate, 'run=' + 'a' * 16], ['gate', gate, 'v=2'], ['stop', 'id=x'],
                     ['gate', gate, 'start=abc'], ['gate', gate, 'start=-'], ['gate', gate, 'seconds=-3'],
                     ['gate', gate, 'tests=1.5'], ['gate', gate, gate], ['stop', 'message'],
                     ['gate', 'task=T1'], ['gate', 'gate_id=0123'], ['gate', 'gate_id=' + 'A' * 16],
                     ['gate', 'gate_id=' + 'g' * 16], ['gate', 'gate_id=-']):
            with self.subTest(args=args):
                result = self.event(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('Error:', result.stderr)
                self.assertEqual(self.lines(), [])
        with self.assertRaises(workflow.EventUsage):
            workflow.append_event('gate', {'gate_id': GATE_ID, 'seconds': True}, 'p', 'b')
        self.assertFalse((self.state / 'events.jsonl').exists())

    def test_events_core_strings_are_one_bounded_line(self):
        message = 'first line\nsecond\r\tthird\x1b[31m\u2028' + 'x' * 500
        self.assertEqual(self.event('stop', 'stage=final', f'message={message}', 'recovery=none').returncode, 0)
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        text = json.loads(lines[0])['message']
        self.assertEqual(len(text), 200)
        self.assertTrue(text.startswith('first line second  third [31m '))
        self.assertFalse(any(ord(c) < 32 for c in text))
        self.assertEqual(workflow.event_text('a\nb', limit=2), 'a ')
        self.assertEqual(workflow.event_text('short'), 'short')

    def test_events_redact_tokens(self):
        redacted = workflow.REDACTED
        for token in ('sk-' + 'aB3_-' * 4, 'ghp_' + 'Ab1' * 7, 'github_pat_' + 'A_b1' * 6,
                      'xoxb-' + '12ab-' * 3, 'xoxp-1234567890', 'AKIA' + 'ABCD2345' * 2,
                      'Bearer abc.def-ghi', 'bearer xyz'):
            with self.subTest(token=token):
                self.assertEqual(workflow.event_text(f'got {token} here'), f'got {redacted} here')
        for text, expected in (('password=hunter2', 'password=[redacted]'),
                               ('retry with API_KEY=abc123 now', 'retry with API_KEY=[redacted] now'),
                               ('Token=t0k secret=s3 x', 'Token=[redacted] secret=[redacted] x')):
            self.assertEqual(workflow.event_text(text), expected)
        for text in ('T201 failed at stage final', 'gate 3f9a0c12b4de passed', 'sk-short',
                     'see https://github.com/o/r/pull/12', 'AKIA lowercase akiaabcdefghijklmnop'):
            self.assertEqual(workflow.event_text(text), text)
        # A token across the 200th character is redacted whole, never cut to a leaked prefix.
        straddle = 'x' * 190 + 'ghp_' + 'Q' * 36
        self.assertEqual(workflow.event_text(straddle), 'x' * 190 + redacted)
        self.assertNotIn('ghp_', workflow.event_text(straddle))
        secret = 'ghp_' + 'Z9' * 15
        result = self.event('stop', 'stage=final', f'message=push failed: {secret} password=hunter2')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertNotIn(secret, '\n'.join(self.lines()))
        self.assertEqual([e['message'] for e in workflow.read_events()],
                         [f'push failed: {redacted} password={redacted}'])

    def test_events_core_held_lock_is_bounded(self):
        holder = self.holder('exclusive')
        fast = {'AI_EVENTS_LOCK_SECONDS': '0.5'}
        started = time.monotonic()
        result = self.event('gate', f'gate_id={GATE_ID}', 'result=pass', **fast)
        self.assertLess(time.monotonic() - started, BOUND)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Note: could not record the gate event (event log busy).', result.stderr)
        self.assertEqual(self.lines(), [])
        started = time.monotonic()
        result = self.shell('ai_event gate gate_id=$1 result=pass; echo "status $?"', GATE_ID, **fast)
        self.assertLess(time.monotonic() - started, BOUND)
        self.assertEqual((result.returncode, result.stdout), (0, 'status 0\n'))
        self.assertEqual(result.stderr, 'Note: could not record the gate event.\n')
        with mock.patch.dict(os.environ, fast):
            started = time.monotonic()
            with self.assertRaises(workflow.EventsBusy):
                workflow.read_events()
            self.assertLess(time.monotonic() - started, BOUND)
        self.release(holder)
        self.assertEqual(self.event('stop', 'stage=one').returncode, 0)
        holder = self.holder('shared')
        with mock.patch.dict(os.environ, fast):
            self.assertEqual([e['stage'] for e in workflow.read_events()], ['one'])
        started = time.monotonic()
        result = self.event('stop', 'stage=two', **fast)
        self.assertLess(time.monotonic() - started, BOUND)
        self.assertEqual(result.returncode, 1)
        self.assertIn('(event log busy)', result.stderr)
        self.release(holder)
        self.assertEqual(self.event('stop', 'stage=three', **fast).returncode, 0)
        self.assertEqual([r['stage'] for r in self.records()], ['one', 'three'])

    def test_events_lock_held_reader_reports_unavailable(self):
        run = {'AI_RUN_ID': 'fedcba9876543210'}
        self.assertEqual(self.event('gate', f'gate_id={GATE_ID}', 'result=fail', **run).returncode, 0)

        def totals(**env):
            started = time.monotonic()
            result = subprocess.run([sys.executable, str(HELPER), 'run-totals'], cwd=self.repo,
                                    env={**self.env, **run, **env}, capture_output=True, text=True,
                                    timeout=COMMAND_TIMEOUT)
            self.assertLess(time.monotonic() - started, BOUND)
            return result.returncode, result.stdout, result.stderr
        free = totals()
        self.assertEqual(free, (0, 'tasks=0 gates=1 gate_failures=1 seconds=-\n', ''))
        holder = self.holder('exclusive')
        self.assertEqual(totals(AI_EVENTS_LOCK_SECONDS='0.5'), (0, 'tasks=0 gates=- gate_failures=- seconds=-\n', ''))
        self.release(holder)
        self.assertEqual(totals(), free)

    def test_events_core_lock_seconds_setting(self):
        for value, expected in (('0.5', 0.5), ('60', 60.0), ('0.05', 5.0), ('61', 5.0), ('nan', 5.0),
                                ('x', 5.0), ('', 5.0)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {'AI_EVENTS_LOCK_SECONDS': value}):
                self.assertEqual(workflow.events_lock_seconds(), expected)

    def test_events_core_reader_tolerates_unknown_kinds_and_versions(self):
        def event(event_id, **extra):
            return json.dumps({'v': 1, 'id': event_id, 'kind': 'stop', 'stage': event_id, **extra})
        self.state.mkdir(parents=True)
        (self.state / 'events.1.jsonl').write_text(event('a' * 16) + '\n' + event('b' * 16) + '\n')
        (self.state / 'events.jsonl').write_text('\n'.join([
            event('b' * 16), event('c' * 16, kind='future'), event('d' * 16, v=2), event('e' * 16, v=True),
            '[1, 2]', '"text"', json.dumps({'v': 1, 'kind': 'stop'}), event('f' * 16),
            '{"v": 1, "id": "torn'])
            + '\n')
        self.assertEqual([e['id'][0] for e in workflow.read_events()], ['a', 'b', 'f'])
        self.assertEqual(self.event('stop', 'stage=after').returncode, 0)  # the newline guard
        self.assertEqual([e['stage'] for e in workflow.read_events()][-1], 'after')

    def test_events_core_concurrent_appends_are_whole_lines(self):
        go = self.base / 'go'
        workers = [subprocess.Popen([sys.executable, '-c', APPENDER, str(HELPER), str(go)],
                                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                   for _ in range(8)]
        for worker in workers:
            self.addCleanup(worker.kill)
        go.touch()
        for worker in workers:
            out, err = worker.communicate(timeout=COMMAND_TIMEOUT * 2)
            self.assertEqual((worker.returncode, err), (0, ''))
        lines = self.lines()
        self.assertEqual(len(lines), 400)
        records = [json.loads(line) for line in lines]
        self.assertEqual(len({r['id'] for r in records}), 400)
        self.assertEqual(len(workflow.read_events()), 400)

    def test_events_core_unwritable_state_dir_is_a_note(self):
        blocker = self.base / 'not-a-dir'
        blocker.write_text('file\n')
        state = str(blocker / 'state')
        result = self.event('gate', f'gate_id={GATE_ID}', AI_STATE_DIR=state)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Note: could not record the gate event (', result.stderr)
        result = self.shell('ai_event gate gate_id=$1; echo "continued $?"', GATE_ID, AI_STATE_DIR=state)
        self.assertEqual((result.returncode, result.stdout), (0, 'continued 0\n'))
        self.assertEqual(result.stderr, 'Note: could not record the gate event.\n')
        with mock.patch.dict(os.environ, {'AI_STATE_DIR': state}):
            self.assertEqual(workflow.read_events(), [])  # a reader never fails on it

    def test_events_core_gate_broken_runs_no_helper(self):
        lib = self.base / 'bin/lib'
        lib.mkdir(parents=True)
        shutil.copy(COMMON, lib / 'common.sh')
        marker = self.base / 'HELPER_RAN'
        (lib / 'workflow.py').write_text(f'import pathlib\npathlib.Path({str(marker)!r}).touch()\n')
        script = 'ai_event gate gate_id=$1 result=pass; echo "status $?"'
        result = self.shell(f'AI_GATE_BROKEN=1\n{script}', GATE_ID, common=lib / 'common.sh')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'status 0\n', ''))
        self.assertFalse(marker.exists())
        self.assertEqual(self.lines(), [])
        result = self.shell(script, GATE_ID, common=lib / 'common.sh')
        self.assertEqual((result.returncode, result.stdout), (0, 'status 0\n'))
        self.assertTrue(marker.exists())


class EventsGateTests(EventsFixture):
    def gate(self, *args, **env):
        return subprocess.run([sys.executable, str(HELPER), 'event-gate', *args], cwd=self.repo,
                              env={**self.env, **env}, capture_output=True, text=True,
                              timeout=COMMAND_TIMEOUT)

    def gate_log(self, content, log='.ai/local/check-test.log'):
        local = self.repo / '.ai/local'
        local.mkdir(parents=True, exist_ok=True)
        (self.repo / log).write_text(content)
        (local / 'validation.json').write_text(json.dumps({'result': 'FAIL', 'log': log}))

    def counts(self, *args):
        result = self.gate(*args)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        record = self.records()[-1]
        return record['tests'], record['failures'], record['workers']

    def test_events_gate_parses_the_gate_log(self):
        args = ('T207', '1700000000', '42', 'pass', GATE_ID)
        self.gate_log('test_a ... ok\n\n------\nRan 12 tests in 0.5s\n\nOK (skipped=1)\n')
        self.assertEqual(self.counts(*args), (12, 0, None))
        self.gate_log('FAIL: test_a (t.T)\n------\nRan 7 tests in 0.1s\n\nFAILED (failures=2, errors=1, skipped=4)\n')
        self.assertEqual(self.counts(*args), (7, 3, None))
        self.gate_log('Workers: 14 (auto)\n===== batch 3/9: FAILED =====\nRan 5 tests in 1s\n'
                      'FAILED (failures=1)\n===== batch 7/9: FAILED =====\nRan 4 tests in 1s\nFAILED (errors=4)\n'
                      'Ran 120 tests in 9.0s (9 batches on 14 workers, 120 collected)\n'
                      'FAILED (failing batches: 3, 7)\n')
        self.assertEqual(self.counts(*args), (120, 2, 14))
        self.gate_log('test_a ... ok\n' * 3 + 'Ran 30 tests in 9.0s (4 batches on 6 workers, 30 collected)\nOK\n')
        self.assertEqual(self.counts(*args), (30, 0, 6))  # `Workers:` outside the tail: the summary
        self.gate_log('Workers: 14 (auto)\ntest_a ... ok\ntest_b ... ')
        self.assertEqual(self.counts(*args), (None, None, 14))
        self.gate_log('test_a ... ok\ntest_b ... ')
        self.assertEqual(self.counts(*args), (None, None, None))
        (self.repo / '.ai/local/validation.json').unlink()
        self.assertEqual(self.counts('final-validation', '1700000100', '9', 'timeout', GATE_ID), (None, None, None))
        record = self.records()[-1]
        self.assertEqual({k: record[k] for k in ('gate_id', 'task', 'stage', 'start', 'seconds', 'result')},
                         {'gate_id': GATE_ID, 'task': None, 'stage': 'final-validation', 'start': 1700000100,
                          'seconds': 9, 'result': 'timeout'})
        self.assertEqual(self.records()[0]['task'], 'T207')
        written = len(self.lines())
        good = ['T207', '1700000000', '42', 'fail', GATE_ID]
        for index, bad in ((1, 'abc'), (1, '-5'), (1, ''), (2, '1.5'), (3, 'passed'), (3, 'PASS'),
                           (4, ''), (4, GATE_ID[:15]), (4, GATE_ID.upper()), (4, GATE_ID + '0'), (0, '')):
            with self.subTest(index=index, bad=bad):
                args = good[:index] + [bad] + good[index + 1:]
                result = self.gate(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertTrue(result.stderr.startswith('Error: '))
        for args in (good[:4], good + ['extra'], []):
            self.assertEqual(self.gate(*args).returncode, 2)
        self.assertEqual(len(self.lines()), written)

    def snapshot(self, *paths):
        state = {}
        for path in paths:
            info = os.lstat(path)
            state[str(path)] = (info.st_mode, info.st_ino, os.readlink(path) if os.path.islink(path)
                                else Path(path).read_bytes() if os.path.isfile(path) else None)
        return state

    def test_events_gate_unsafe_records_return_promptly(self):
        ran = 'Ran 99 tests in 1.0s\nFAILED (failures=5)\n'

        def stamp_fifo(local):
            os.mkfifo(local / 'validation.json')
            return [local / 'validation.json']

        def log_fifo(local):
            os.mkfifo(local / 'check.log')
            (local / 'validation.json').write_text(json.dumps({'log': '.ai/local/check.log'}))
            return [local / 'check.log', local / 'validation.json']

        def log_symlink(local):
            target = self.base / 'outside.log'
            target.write_text(ran)
            (local / 'check.log').symlink_to(target)
            (local / 'validation.json').write_text(json.dumps({'log': '.ai/local/check.log'}))
            return [local / 'check.log', target, local / 'validation.json']

        def local_symlink(local):
            local.rmdir()
            target = self.base / 'elsewhere'
            target.mkdir()
            (target / 'check.log').write_text(ran)
            (target / 'validation.json').write_text(json.dumps({'log': '.ai/local/check.log'}))
            local.symlink_to(target)
            return [local, target, target / 'check.log', target / 'validation.json']

        def outside(name):
            def plant(local):
                target = self.repo.parent / 'x.log' if name == '../x.log' else Path(name)
                target.write_text(ran)
                (local / 'validation.json').write_text(json.dumps({'log': name}))
                return [target, local / 'validation.json']
            return plant

        def big_stamp(local):
            (local / 'check.log').write_text(ran)
            text = json.dumps({'log': '.ai/local/check.log'})
            (local / 'validation.json').write_text(text + ' ' * (workflow.STAMP_LIMIT + 1 - len(text)))
            return [local / 'check.log', local / 'validation.json']

        cases = {'stamp FIFO': stamp_fifo, 'log FIFO': log_fifo, 'log symlink': log_symlink,
                 '.ai/local symlink': local_symlink, 'relative outside': outside('../x.log'),
                 'absolute outside': outside(str(self.base / 'abs.log')), 'oversized stamp': big_stamp}
        for number, (name, plant) in enumerate(cases.items()):
            with self.subTest(name):
                shutil.rmtree(self.repo / '.ai', ignore_errors=True)
                local = self.repo / '.ai/local'
                local.mkdir(parents=True)
                planted = plant(local)
                before = self.snapshot(*planted)
                started = time.monotonic()
                result = self.gate(f'T{number}', '1700000000', '3', 'fail', GATE_ID)
                self.assertLess(time.monotonic() - started, BOUND)
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                record = self.records()[-1]
                self.assertEqual((record['task'], record['tests'], record['failures'], record['workers']),
                                 (f'T{number}', None, None, None))
                self.assertEqual(self.snapshot(*planted), before)
        self.assertEqual(len(self.lines()), len(cases))


class EventsStopTests(EventsFixture):
    def category(self, stage='implementation'):
        result = subprocess.run([sys.executable, str(HELPER), 'stop-category', stage], cwd=self.repo,
                                env=self.env, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        return result.stdout.strip()

    def test_events_stop_category_table(self):
        local = self.repo / '.ai/local'
        local.mkdir(parents=True)
        error = local / 'last-error'
        self.assertEqual(self.category(), 'other')  # no last-error
        for text, category in (
                ('Claude usage limit: the reset is beyond the 28800s wait budget. Rerun after it resets.', 'usage_limit'),
                ('Claude exited 124 (timeout/interruption/error). Preserve partial work.', 'timeout'),
                ('Run time limit reached before final validation.', 'timeout'),
                ('Validation failed; T001 returned to IN_PROGRESS.', 'validation_failed'),
                ('T002 fails validation after the session', 'validation_failed'),
                ('Task queue is invalid: T003 dependencies must exist earlier', 'queue_order'),
                ('T004 is missing ### Result / notes', 'record_format'),
                ('review round 3 has no row in dispositions.md', 'record_format'),
                ('Fix round limit reached (4).', 'review_round_limit'),
                ('plan review needs your decision: keep A?', 'needs_human'),
                ('Claude session was killed', 'crash'),
                ('the pipeline ended without a checkpoint', 'crash'),
                ('The reviewer said something nobody planned for', 'other')):
            with self.subTest(category=category, text=text):
                error.write_text(text + '\n')
                self.assertEqual(self.category(), category)
        error.write_text('stopped during validation (see terminal)\n')
        self.assertEqual(self.category('validation'), 'validation_failed')
        # A reworded message no pattern knows is `other`, never a guess.
        error.write_text('Checks went red; the task is back in progress.\n')
        self.assertEqual(self.category(), 'other')
        # Only the first 4 KiB is read.
        error.write_text('x' * 5000 + ' usage limit\n')
        self.assertEqual(self.category(), 'other')
        # A symlink is never followed, even to a file that names a category.
        error.unlink()
        target = self.base / 'outside-error'
        target.write_text('Validation failed; T001 returned to IN_PROGRESS.\n')
        error.symlink_to(target)
        self.assertEqual(self.category(), 'other')
        usage = subprocess.run([sys.executable, str(HELPER), 'stop-category'], cwd=self.repo, env=self.env,
                               capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
        self.assertNotEqual(usage.returncode, 0)


class EventsGateIdTests(EventsFixture):
    def helper(self, *args, **env):
        return subprocess.run([sys.executable, str(HELPER), *args], cwd=self.repo, env={**self.env, **env},
                              capture_output=True, text=True, timeout=COMMAND_TIMEOUT)

    def rows(self, state=None):
        path = (state or self.state) / 'outcomes.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_events_gate_id_on_outcome_rows(self):
        result = self.helper('outcome', 'gate', 'pass', '12', '--id', GATE_ID)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual({k: self.rows()[0][k] for k in ('kind', 'result', 'seconds', 'gate_id')},
                         {'kind': 'gate', 'result': 'pass', 'seconds': 12, 'gate_id': GATE_ID})
        for args in (['--id', GATE_ID[:15]], ['--id', GATE_ID.upper()], ['--id'], ['--id', GATE_ID + '0'],
                     ['--id', GATE_ID, 'extra'], ['--id', ''], ['--id', GATE_ID[:15] + '\n']):
            with self.subTest(args=args):
                result = self.helper('outcome', 'gate', 'pass', '12', *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('Usage: outcome gate pass|fail|timeout SECONDS [--id GATE_ID]', result.stderr)
                self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.helper('outcome', 'gate', 'fail', '7').returncode, 0)
        self.assertNotIn('gate_id', self.rows()[1])
        # gate-seconds reads the same seconds whether the rows carry ids or not.
        other = self.base / 'other-state'
        for seconds in ('30', '50'):
            self.assertEqual(self.helper('outcome', 'gate', 'pass', seconds).returncode, 0)
            self.assertEqual(self.helper('outcome', 'gate', 'pass', seconds, '--id', os.urandom(8).hex(),
                                         AI_STATE_DIR=str(other)).returncode, 0)
        self.assertTrue(all('gate_id' in row for row in self.rows(other)))
        with_ids = self.helper('gate-seconds', AI_STATE_DIR=str(other))
        without = self.helper('gate-seconds')
        self.assertEqual((with_ids.returncode, without.returncode), (0, 0))
        self.assertEqual(with_ids.stdout, '50\n')
        self.assertEqual(without.stdout, '50\n')
        first, second = (self.shell('ai_new_id').stdout for _ in range(2))
        self.assertRegex(first, r'\A[0-9a-f]{16}\Z')
        self.assertRegex(second, r'\A[0-9a-f]{16}\Z')
        self.assertNotEqual(first, second)

    def test_events_gate_merge_counts_each_gate_once(self):
        ids = {name: name * 16 for name in 'abc'}

        def row(seconds, name=None):
            return {'kind': 'gate', 'result': 'pass', 'seconds': seconds, 'run': 'r' * 16,
                    **({'gate_id': ids[name]} if name else {})}

        def event(name, seconds, tests=None, **extra):
            return {'kind': 'gate', 'gate_id': ids[name], 'seconds': seconds, 'result': 'pass', 'tests': tests,
                    'failures': 0, 'workers': 4, 'task': 'T1', 'stage': None, 'start': 1700000000,
                    'run': None, **extra}

        def seconds(gates):
            return sorted(gate['seconds'] for gate in gates)

        with self.subTest('complete overlap'):
            gates = workflow.merge_gates([row(10, 'a'), row(100, 'b')], [event('a', 10, 40), event('b', 100, 41)])
            self.assertEqual(len(gates), 2)
            self.assertEqual(statistics.median(seconds(gates)), 55)
            self.assertEqual([(g['gate_id'], g['tests'], g['run']) for g in gates],
                             [(ids['a'], 40, 'r' * 16), (ids['b'], 41, 'r' * 16)])
        with self.subTest('partial event loss'):
            gates = workflow.merge_gates([row(10, 'a'), row(100, 'b')], [event('b', 100, 41)])
            self.assertEqual(len(gates), 2)
            self.assertEqual(statistics.median(seconds(gates)), 55)
            self.assertEqual([g['tests'] for g in gates], [None, 41])
        with self.subTest('events rotated away'):
            gates = workflow.merge_gates([row(10, 'a'), row(100, 'b')], [])
            self.assertEqual((len(gates), seconds(gates)), (2, [10, 100]))
        with self.subTest('legacy rows without gate_id'):
            gates = workflow.merge_gates([row(30), row(50), row(70, 'c')], [event('c', 70, 9)])
            self.assertEqual((len(gates), seconds(gates)), (3, [30, 50, 70]))
            self.assertEqual([g['gate_id'] for g in gates], [None, None, ids['c']])
            self.assertEqual(gates[2]['tests'], 9)
        with self.subTest('event-only validation gate'):
            only = event('b', 200, 5, task=None, stage='final-validation')
            gates = workflow.merge_gates([row(10, 'a')], [only])
            self.assertEqual((len(gates), seconds(gates)), (2, [10, 200]))
            self.assertEqual((gates[1]['stage'], gates[1]['tests']), ('final-validation', 5))
        with self.subTest('row seconds win'):
            gates = workflow.merge_gates([row(10, 'a')], [event('a', 13, 7, result='fail')])
            self.assertEqual([(g['seconds'], g['result'], g['tests']) for g in gates], [(10, 'pass', 7)])
        with self.subTest('duplicate event after a rotation crash'):
            gates = workflow.merge_gates([], [event('a', 10, 40), event('a', 10, 40)])
            self.assertEqual(len(gates), 1)


class EventsRotationTests(EventsFixture):
    def setUp(self):
        super().setUp()
        self.live = self.state / 'events.jsonl'
        self.archive = self.state / 'events.1.jsonl'
        self.cap = {'AI_EVENTS_MAX_BYTES': MIN_CAP}

    def append(self, stage, run=None):
        env = {**self.cap, **({'AI_RUN_ID': run} if run else {})}
        with mock.patch.dict(os.environ, env):
            if not run:
                os.environ.pop('AI_RUN_ID', None)
            self.assertTrue(workflow.append_event('stop', {'stage': stage}, 'p', 'b'))

    def runs(self, path):
        return [json.loads(line)['run'] for line in path.read_text().splitlines()]

    def test_events_rotation_keeps_every_active_run(self):
        repo_b = self.base / 'project-b'
        repo_b.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=repo_b, env=self.env, check=True)
        run_a = 'a' * 16
        for args in (['run', 'action=start'], ['stop', 'stage=a0'], ['stop', 'stage=a1'], ['recovery', 'decision=pause']):
            result = self.event(*args, AI_RUN_ID=run_a, **self.cap)
            self.assertEqual((result.returncode, result.stderr), (0, ''))
        b_runs = ['b1' * 8, 'b2' * 8, 'b3' * 8]
        for index, run in enumerate(b_runs):
            result = self.event('run', 'action=start', cwd=repo_b, AI_RUN_ID=run, **self.cap)
            self.assertEqual((result.returncode, result.stderr), (0, ''))
            with mock.patch.dict(os.environ, {'AI_RUN_ID': run, **self.cap}):
                for n in range(250 if index < 2 else 3):  # an ended run is about 80 KB, over the cap
                    self.assertTrue(workflow.append_event('stop', {'stage': f'{run}-{n}', 'message': 'b' * 150},
                                                          'project-b', 'main'))
            if index < 2:
                result = self.event('run', 'action=end', 'result=pass', cwd=repo_b, AI_RUN_ID=run, **self.cap)
                self.assertEqual((result.returncode, result.stderr), (0, ''))
        # Rotation 1 at b2's start dropped b1; rotation 2 at b3's start archived b2 and dropped b1 for good.
        events = workflow.read_events()
        by_run = {}
        for event in events:
            by_run.setdefault(event['run'], []).append(event)
        self.assertEqual(sorted(by_run), sorted([run_a, b_runs[1], b_runs[2]]))
        self.assertEqual([e['kind'] for e in by_run[run_a]], ['run', 'stop', 'stop', 'recovery'])
        self.assertEqual({e['project'] for e in by_run[run_a]}, {'events-project'})
        self.assertEqual(len(by_run[b_runs[2]]), 4)
        self.assertEqual(len(by_run[b_runs[1]]), 252)
        self.assertNotIn(b_runs[0], self.archive.read_text())
        live_runs = self.runs(self.live)
        self.assertEqual(live_runs.count(run_a), 4)
        self.assertEqual(set(live_runs), {run_a, b_runs[2]})
        self.assertEqual(len(events), len({e['id'] for e in events}))

    def test_events_rotation_waiting_writers_lose_nothing(self):
        go = self.base / 'go'
        runs = [f'{n:016x}' for n in range(1, 7)]
        workers = [subprocess.Popen([sys.executable, '-c', ROTATOR, str(HELPER), str(go), run],
                                    env={**self.env, **self.cap}, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
                   for run in runs]
        for worker in workers:
            self.addCleanup(worker.kill)
        go.touch()
        for worker in workers:
            out, err = worker.communicate(timeout=COMMAND_TIMEOUT * 4)
            self.assertEqual((worker.returncode, err), (0, ''))  # no busy Note, no short write
        self.assertTrue(self.archive.exists())
        for path in (self.archive, self.live):
            for line in path.read_text().splitlines():
                json.loads(line)
        live_runs = self.runs(self.live)
        self.assertLess(len(live_runs), 2400)  # without rotation it would hold every line
        self.assertLess(live_runs.count(None), 1200)
        run_events = [e for e in workflow.read_events() if e['run']]
        self.assertEqual(len(run_events), 1200)
        self.assertEqual(sorted(e['stage'] for e in run_events),
                         sorted(f'{run}-{n}' for run in runs for n in range(200)))

    def test_events_rotation_small_gain_and_stale_runs(self):
        for value, expected in (('65536', 65536), ('1000000', 1000000), ('65535', 8 * 1024 * 1024),
                                ('-1', 8 * 1024 * 1024), ('x', 8 * 1024 * 1024), ('', 8 * 1024 * 1024)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {'AI_EVENTS_MAX_BYTES': value}):
                self.assertEqual(workflow.events_max_bytes(), expected)
        self.state.mkdir(parents=True)
        active = ['1' * 16, '2' * 16]
        self.live.write_text(''.join(event_line(active[n % 2], stamp(minutes=5), message='x' * 150)
                                     for n in range(260)))
        self.assertGreater(self.live.stat().st_size, 65536)
        self.append('one', run=active[0])
        self.assertFalse(self.archive.exists())  # only active runs: nothing to gain, no rotation
        self.assertEqual(len(self.runs(self.live)), 261)
        stale = '3' * 16
        with self.live.open('a') as handle:
            for _ in range(40):
                handle.write(event_line(stale, stamp(days=8), message='s' * 150))
                handle.write(event_line(None, stamp(minutes=1), message='n' * 150))
            handle.write(event_line(active[0], stamp(minutes=1), kind='future'))
            handle.write('{"v": 1, "torn')
        before = self.live.read_bytes()
        self.append('two', run=active[1])
        self.assertEqual(self.archive.read_bytes(), before)
        records = [json.loads(line) for line in self.live.read_text().splitlines()]
        self.assertEqual(len(records), 262)
        self.assertEqual({r['run'] for r in records}, set(active))
        self.assertNotIn('future', {r['kind'] for r in records})
        self.assertEqual([r['stage'] for r in records[-2:]], ['one', 'two'])
        self.assertEqual(oct(self.live.stat().st_mode & 0o777), '0o644')

    def test_events_rotation_crash_between_replaces_duplicates_only(self):
        self.state.mkdir(parents=True)
        run = '4' * 16
        self.live.write_text(''.join(event_line(run if n % 3 else None, stamp(minutes=2), message='y' * 150)
                                     for n in range(300)))
        self.archive.write_bytes(self.live.read_bytes())  # the first replace done, the second not
        events = workflow.read_events()
        self.assertEqual(len(events), 300)
        self.assertEqual(len({e['id'] for e in events}), 300)
        # A failing rotation leaves both files as they were, removes its temp, and the append happens.
        before = self.live.read_bytes()
        with mock.patch.object(workflow.os, 'replace', side_effect=OSError('disk full')):
            self.append('during-failure', run=run)
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertEqual(self.live.read_bytes()[:len(before)], before)
        self.assertEqual(len(self.runs(self.live)), 301)
        self.assertEqual(list(self.state.glob('.events-*')), [])
        before = self.live.read_bytes()
        self.append('after', run=run)
        self.assertEqual(self.archive.read_bytes(), before)
        live = [json.loads(line) for line in self.live.read_text().splitlines()]
        self.assertEqual({r['run'] for r in live}, {run})
        self.assertEqual(len(live), 202)
        events = workflow.read_events()
        self.assertEqual(len(events), len({e['id'] for e in events}))
        self.assertEqual(len(events), 301 + 1)


RUN_A, RUN_B, RUN_C, RUN_D, RUN_E = (str(n) * 16 for n in range(1, 6))
NUMBERS = ('attempts', 'tasks', 'first_pass', 'first_pass_rate', 'timeouts', 'median_task_seconds', 'gates',
           'median_gate_seconds', 'stops', 'review_rounds', 'findings')


def outcome_row(when, kind, run=None, project='alpha', branch='feat', **fields):
    return {'time': when, 'kind': kind, 'project': project, 'branch': branch,
            **({'run': run} if run else {}), **fields}


def metrics_event(when, kind, run=None, project='alpha', branch='feat', **fields):
    return {**json.loads(event_line(run, when, kind=kind, **fields)), 'project': project, 'branch': branch}


class MetricsTests(EventsFixture):
    def write(self, name, records):
        path = self.base / name
        path.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))
        return path

    def metrics(self, *args, **env):
        started = time.monotonic()
        result = subprocess.run([sys.executable, str(HELPER), 'metrics', *args], cwd=self.repo,
                                env={**self.env, **env}, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
        self.assertLess(time.monotonic() - started, BOUND)
        return result

    def data(self, rows, events, *args):
        result = self.metrics('--json', '--outcomes', str(self.write('outcomes.jsonl', rows)),
                              '--events', str(self.write('events.jsonl', events)), *args)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        return json.loads(result.stdout)

    def by_run(self, data):
        return {(r['project'], r['run']): r for r in data['runs']}

    def numbers(self, entry):
        return {name: entry[name] for name in NUMBERS}

    def assert_sums(self, data):
        for project in data['projects']:
            runs = [r for r in data['runs'] if r['project'] == project['project']]
            for name in ('attempts', 'timeouts', 'review_rounds'):
                self.assertEqual(project[name], sum(r[name] for r in runs), name)

    def test_metrics_json_on_fixture_logs(self):
        day = '2026-01-05T'
        rows = [outcome_row(day + '10:05:00Z', 'task', RUN_A, task='T1', result='done', seconds=300, seq=1),
                outcome_row(day + '10:20:00Z', 'task', RUN_A, task='T2', result='timeout', seconds=1800, seq=2),
                outcome_row(day + '10:30:00Z', 'gate', RUN_A, result='pass', seconds=600, gate_id='a' * 16),
                outcome_row(day + '10:40:00Z', 'review', RUN_A, mode='code', reviewer='codex', blocker=0,
                            major=2, minor=3),
                outcome_row(day + '12:10:00Z', 'task', RUN_B, task='T2', result='done', seconds=600, seq=3),
                outcome_row(day + '12:20:00Z', 'gate', RUN_B, result='pass', seconds=800, gate_id='b' * 16),
                outcome_row(day + '12:30:00Z', 'review', RUN_B, mode='code', reviewer='claude-routed', blocker=0,
                            major=0, minor=1),
                outcome_row(day + '12:35:00Z', 'review', RUN_B, mode='recheck', reviewer='codex'),
                outcome_row(day + '12:36:00Z', 'plan', RUN_B, result='done'),
                outcome_row(day + '13:00:00Z', 'future', RUN_B),
                outcome_row(day + '14:00:00Z', 'task', project='beta', branch='main', task='T9', result='done',
                            seconds=100, seq=4)]
        events = [metrics_event(day + '10:00:00Z', 'run', RUN_A, action='start'),
                  metrics_event(day + '10:30:00Z', 'gate', RUN_A, gate_id='a' * 16, seconds=600, result='pass'),
                  metrics_event(day + '10:45:00Z', 'stop', RUN_A, category='timeout'),
                  metrics_event(day + '10:46:00Z', 'run', RUN_A, action='end', result='stopped'),
                  metrics_event(day + '12:00:00Z', 'run', RUN_B, action='start'),
                  metrics_event(day + '12:20:00Z', 'gate', RUN_B, gate_id='b' * 16, seconds=800, result='pass'),
                  metrics_event(day + '12:40:00Z', 'stop', RUN_B, category='queue_order'),
                  metrics_event(day + '12:50:00Z', 'run', RUN_B, action='end', result='pass')]
        data = self.data(rows, events)
        self.assertEqual(data['v'], 1)
        alpha, beta = data['projects']
        self.assertEqual({k: alpha[k] for k in ('project', 'runs', 'runs_without_events')}, {
            'project': 'alpha', 'runs': 2, 'runs_without_events': 0})
        self.assertEqual(self.numbers(alpha), {
            'attempts': 3, 'tasks': 2, 'first_pass': 1, 'first_pass_rate': 0.5, 'timeouts': 1,
            'median_task_seconds': 1350, 'gates': 2, 'median_gate_seconds': 700,
            'stops': {'timeout': 1, 'queue_order': 1}, 'review_rounds': 2,
            'findings': {'codex': {'blocker': 0, 'major': 2, 'minor': 3},
                         'claude-routed': {'blocker': 0, 'major': 0, 'minor': 1}}})
        self.assertEqual(self.numbers(beta), {
            'attempts': 1, 'tasks': 1, 'first_pass': 1, 'first_pass_rate': 1.0, 'timeouts': 0,
            'median_task_seconds': 100, 'gates': 0, 'median_gate_seconds': None, 'stops': {},
            'review_rounds': 0, 'findings': {}})
        runs = self.by_run(data)
        self.assertEqual(list(runs), [('alpha', RUN_A), ('alpha', RUN_B), ('beta', None)])
        run_a, run_b, no_run = runs.values()
        self.assertEqual({k: run_a[k] for k in ('branch', 'events', 'start', 'end', 'result')},
                         {'branch': 'feat', 'events': 4, 'start': day + '10:00:00Z', 'end': day + '10:46:00Z',
                          'result': 'stopped'})
        self.assertEqual(self.numbers(run_a), {
            'attempts': 2, 'tasks': 2, 'first_pass': 1, 'first_pass_rate': 0.5, 'timeouts': 1,
            'median_task_seconds': 1050, 'gates': 1, 'median_gate_seconds': 600, 'stops': {'timeout': 1},
            'review_rounds': 1, 'findings': {'codex': {'blocker': 0, 'major': 2, 'minor': 3}}})
        # T2 was first tried in run A: its pass in run B is not a first pass.
        self.assertEqual(self.numbers(run_b), {
            'attempts': 1, 'tasks': 1, 'first_pass': 0, 'first_pass_rate': 0.0, 'timeouts': 0,
            'median_task_seconds': 600, 'gates': 1, 'median_gate_seconds': 800, 'stops': {'queue_order': 1},
            'review_rounds': 1, 'findings': {'claude-routed': {'blocker': 0, 'major': 0, 'minor': 1}}})
        self.assertEqual(run_b['result'], 'pass')
        self.assertEqual({k: no_run[k] for k in ('label', 'branch', 'events', 'result', 'stops', 'attempts')},
                         {'label': '(no run record)', 'branch': 'main', 'events': 0, 'result': None,
                          'stops': None, 'attempts': 1})
        self.assert_sums(data)
        plain = self.metrics('--outcomes', str(self.base / 'outcomes.jsonl'),
                             '--events', str(self.base / 'events.jsonl'))
        self.assertEqual(plain.stdout, workflow.metrics_text(data) + '\n')  # without --json: the text tables
        text = plain.stdout
        self.assertNotIn('|', text)
        projects, runs, footer = text.rstrip('\n').split('\n\n')
        lines = projects.splitlines()
        self.assertEqual(lines[0], 'Projects')
        self.assertEqual(' '.join(lines[2].split()), 'alpha 2 2 50 1 22.5 2 11.7 queue_order 1, timeout 1 2 '
                                                     'claude-routed 0/0/1, codex 0/2/3')
        self.assertEqual(lines[3].split(), ['beta', '0', '1', '100', '0', '1.7', '0', '-', '-', '0', '-'])
        self.assertIn('(no run record)', runs)
        self.assertIn('events 0: event numbers unavailable', footer)

    def text(self, rows, events, *args):
        result = self.metrics('--outcomes', str(self.write('outcomes.jsonl', rows)),
                              '--events', str(self.write('events.jsonl', events)), *args)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertNotIn('|', result.stdout)
        return result.stdout

    def test_metrics_text_tables(self):
        rows = [outcome_row('2026-01-05T10:05:00Z', 'task', RUN_A, task='T1', result='done', seconds=300, seq=1),
                outcome_row('2026-01-05T10:20:00Z', 'task', RUN_A, task='T2', result='timeout', seconds=1800, seq=2)]
        events = [metrics_event('2026-01-05T10:00:00Z', 'run', RUN_A, action='start'),
                  metrics_event('2026-01-05T10:45:00Z', 'stop', RUN_A, category='timeout'),
                  metrics_event('2026-01-05T10:46:00Z', 'run', RUN_A, action='end', result='stopped')]
        text = self.text(rows, events)
        projects, runs, footer = text.rstrip('\n').split('\n\n')
        self.assertEqual(projects.splitlines()[0], 'Projects')
        self.assertEqual(projects.splitlines()[2].split(),
                         ['alpha', '1', '2', '50', '1', '17.5', '0', '-', 'timeout', '1', '0', '-'])
        self.assertEqual(runs.splitlines()[0], 'Runs')
        self.assertEqual(runs.splitlines()[2].split(),
                         ['alpha', RUN_A[:8], 'feat', 'stopped', '3', '2', '50', '1', '17.5', '0', '-',
                          'timeout', '1', '0', '-'])
        self.assertIn('Sources:', footer)

    def test_metrics_text_rotated_run(self):
        rows = [outcome_row('2026-02-01T10:10:00Z', 'task', RUN_A, task='T1', result='done', seconds=60, seq=1),
                outcome_row('2026-02-01T11:10:00Z', 'task', RUN_D, task='T2', result='done', seconds=60, seq=2)]
        events = [metrics_event(stamp(minutes=5), 'run', RUN_D, action='start'),
                  metrics_event(stamp(minutes=6), 'stop', RUN_D, category='other')]
        text = self.text(rows, events)
        runs = {line.split()[1]: line.split() for line in text.split('Runs\n')[1].split('\n\n')[0].splitlines()[1:]}
        self.assertEqual(runs[RUN_A[:8]][3:5], ['unknown', '0'])
        self.assertEqual(runs[RUN_A[:8]][11], '-')  # stops
        self.assertEqual(runs[RUN_D[:8]][3], 'open')
        self.assertIn('result unknown: the run\'s lifecycle events rotated away or were never written.', text)
        self.assertIn('events 0: event numbers unavailable; gates come from the outcome log only.', text)

    def test_metrics_ai_status_flag(self):
        rows = [outcome_row('2026-01-05T10:05:00Z', 'task', RUN_A, task='T1', result='done', seconds=300, seq=1),
                outcome_row('2026-01-05T10:06:00Z', 'task', RUN_B, project='beta', task='T1', result='done',
                            seconds=300, seq=2)]
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / 'outcomes.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))

        def status(*args):
            return subprocess.run([str(ROOT / 'scripts/ai-status'), *args], cwd=self.repo, env=self.env,
                                  capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
        result = status('--metrics', '--json', '--project', 'alpha')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual([p['project'] for p in json.loads(result.stdout)['projects']], ['alpha'])
        bad = status('--metrics', '--since', 'x')
        self.assertEqual(bad.returncode, 2)
        self.assertIn('Usage: metrics', bad.stderr)
        self.assertIn('--metrics', status('--help').stdout)

    def test_metrics_attribution_by_run_field(self):
        rows = [outcome_row('2026-02-01T10:10:00Z', 'task', RUN_A, task='T1', result='timeout', seconds=60, seq=1),
                outcome_row('2026-02-01T11:10:00Z', 'task', RUN_B, task='T3', result='done', seconds=60, seq=3),
                outcome_row('2026-02-01T11:15:00Z', 'task', task='T4', result='done', seconds=60, seq=4),
                # Reconciled during run B, for an attempt of run A: it counts for A.
                outcome_row('2026-02-01T11:30:00Z', 'task', RUN_A, task='T2', result='crashed', seconds=0, seq=2),
                outcome_row('2026-02-01T09:00:00Z', 'gate', RUN_E, result='pass', seconds=40)]
        events = [metrics_event('2026-02-01T10:00:00Z', 'run', RUN_A, action='start'),
                  metrics_event('2026-02-01T10:50:00Z', 'run', RUN_A, action='end', result='stopped'),
                  metrics_event('2026-02-01T11:00:00Z', 'run', RUN_B, action='start'),
                  metrics_event('2026-02-01T11:20:00Z', 'stop', None, category='other'),
                  metrics_event('2026-02-01T11:40:00Z', 'run', RUN_B, action='end', result='pass'),
                  metrics_event(stamp(minutes=5), 'run', RUN_C, action='start'),
                  metrics_event(stamp(days=8), 'run', RUN_D, action='resume')]
        runs = self.by_run(self.data(rows, events))
        self.assertEqual([runs[('alpha', run)]['attempts'] for run in (RUN_A, RUN_B, None)], [2, 1, 1])
        self.assertEqual(runs[('alpha', RUN_A)]['timeouts'], 1)
        no_run = runs[('alpha', None)]
        self.assertEqual((no_run['label'], no_run['events'], no_run['stops']), ('(no run record)', 1, {'other': 1}))
        self.assertEqual([runs[('alpha', run)]['result'] for run in (RUN_A, RUN_B, RUN_C, RUN_D)],
                         ['stopped', 'pass', 'open', 'unknown'])
        self.assertIsNone(runs[('alpha', RUN_C)]['end'])
        self.assertEqual({k: runs[('alpha', RUN_E)][k] for k in ('result', 'events', 'start', 'end', 'stops', 'gates')},
                         {'result': 'unknown', 'events': 0, 'start': None, 'end': None, 'stops': None, 'gates': 1})
        project = self.data(rows, events)['projects'][0]
        self.assertEqual((project['runs'], project['runs_without_events'], project['attempts']), (5, 1, 4))

    def test_metrics_gates_counted_once(self):
        rows = [outcome_row('2026-03-01T10:00:00Z', 'gate', RUN_A, result='pass', seconds=10, gate_id='a' * 16),
                outcome_row('2026-03-01T10:10:00Z', 'gate', RUN_A, result='pass', seconds=100, gate_id='b' * 16)]
        events = [metrics_event('2026-03-01T10:10:00Z', 'gate', RUN_A, gate_id='b' * 16, seconds=100, result='pass')]
        data = self.data(rows, events)
        for entry in (data['projects'][0], self.by_run(data)[('alpha', RUN_A)]):
            self.assertEqual((entry['gates'], entry['median_gate_seconds']), (2, 55))

    def test_metrics_filters_and_empty_logs(self):
        rows = [outcome_row('2026-01-01T23:59:59Z', 'task', RUN_A, task='T1', result='done', seconds=5, seq=1),
                outcome_row('2026-01-02T00:00:00Z', 'task', RUN_B, task='T2', result='done', seconds=7, seq=2),
                outcome_row('2026-01-03T00:00:00Z', 'task', RUN_B, project='beta', task='T3', result='done',
                            seconds=9, seq=3)]
        events = [metrics_event('2026-01-01T10:00:00Z', 'run', RUN_A, action='start')]
        data = self.data(rows, events, '--since', '2026-01-02')
        self.assertEqual(sorted(self.by_run(data)), [('alpha', RUN_B), ('beta', RUN_B)])
        self.assertEqual([p['attempts'] for p in data['projects']], [1, 1])
        data = self.data(rows, events, '--project', 'beta')
        self.assertEqual(([p['project'] for p in data['projects']], list(self.by_run(data))),
                         (['beta'], [('beta', RUN_B)]))
        self.assertEqual(self.data(rows, events, '--project', 'alph')['projects'], [])
        self.assertEqual(self.data([], []), {'v': 1, 'projects': [], 'runs': []})
        empty = workflow.metrics_numbers([], [], {})
        self.assertEqual({k: v for k, v in empty.items() if k != 'findings'}, {
            'attempts': 0, 'tasks': 0, 'first_pass': 0, 'first_pass_rate': None, 'timeouts': 0,
            'median_task_seconds': None, 'gates': 0, 'median_gate_seconds': None, 'review_rounds': 0})
        default = self.metrics('--json')  # the state root's logs, none written yet
        self.assertEqual((default.returncode, json.loads(default.stdout)), (0, {'v': 1, 'projects': [], 'runs': []}))
        for args in (['--since', '2026-13-01'], ['--since', '2026-1-1'], ['--since', 'yesterday'], ['--since'],
                     ['--bogus'], ['--events'], ['--project']):
            with self.subTest(args=args):
                result = self.metrics(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('Usage: metrics', result.stderr)
        self.holder('exclusive')
        result = self.metrics('--json', AI_EVENTS_LOCK_SECONDS='0.5')
        self.assertEqual((result.returncode, result.stdout), (1, ''))
        self.assertEqual(result.stderr, 'Error: the event log is busy (lock held for more than 0.5 s); try again.\n')

    def test_metrics_runs_survive_event_rotation(self):
        git = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com']
        subprocess.run([*git, 'commit', '-q', '--allow-empty', '-m', 'base'], cwd=self.repo, env=self.env, check=True)
        cap = {'AI_EVENTS_MAX_BYTES': MIN_CAP}

        def helper(run, *args):
            result = subprocess.run([sys.executable, str(HELPER), *args], cwd=self.repo,
                                    env={**self.env, **cap, **({'AI_RUN_ID': run} if run else {})},
                                    capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
            self.assertEqual((result.returncode, result.stderr), (0, ''), args)

        helper(RUN_A, 'event', 'run', 'action=start')
        helper(RUN_A, 'outcome', 'task', 'T1', 'timeout', 'sonnet', '1800')
        helper(RUN_A, 'outcome', 'task', 'T1', 'done', 'sonnet', '600')
        helper(RUN_A, 'outcome', 'gate', 'pass', '700', '--id', GATE_ID)
        helper(RUN_A, 'event', 'gate', f'gate_id={GATE_ID}', 'seconds=700', 'result=pass')
        helper(RUN_A, 'outcome', 'review', 'code', 'codex', 'gpt', 'high', '90')
        helper(RUN_A, 'event', 'stop', 'stage=implementation', 'category=timeout')
        helper(RUN_A, 'event', 'run', 'action=end', 'result=stopped')
        archive = self.state / 'events.1.jsonl'
        rotations, last = 0, None
        for run in (RUN_B, RUN_C, RUN_D):
            helper(run, 'event', 'run', 'action=start')
            helper(run, 'outcome', 'task', 'T2', 'done', 'sonnet', '30')
            for n in range(250):  # null-run filler: always dropped by a rotation
                with mock.patch.dict(os.environ, cap):
                    self.assertTrue(workflow.append_event('stop', {'stage': f'filler-{n}', 'message': 'f' * 150},
                                                          'events-project', 'main'))
                inode = archive.stat().st_ino if archive.exists() else None
                if inode != last:
                    rotations, last = rotations + 1, inode
            helper(run, 'event', 'stop', 'stage=final', 'category=other')
            if run != RUN_D:
                helper(run, 'event', 'run', 'action=end', 'result=pass')
        self.assertGreaterEqual(rotations, 3)
        self.assertNotIn(RUN_A, archive.read_text())
        self.assertNotIn(RUN_A, (self.state / 'events.jsonl').read_text())
        result = self.metrics('--json', **cap)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        data = json.loads(result.stdout)
        runs = self.by_run(data)
        run_a = runs[('events-project', RUN_A)]
        self.assertEqual({k: run_a[k] for k in ('result', 'events', 'stops', 'attempts', 'timeouts', 'gates',
                                                'review_rounds', 'start', 'branch')},
                         {'result': 'unknown', 'events': 0, 'stops': None, 'attempts': 2, 'timeouts': 1,
                          'gates': 1, 'review_rounds': 1, 'start': None, 'branch': 'main'})
        self.assertEqual(runs[('events-project', RUN_D)]['result'], 'open')
        self.assertEqual([runs[('events-project', run)]['attempts'] for run in (RUN_B, RUN_C, RUN_D)], [1, 1, 1])
        project, = data['projects']
        self.assert_sums(data)
        self.assertGreaterEqual(project['runs_without_events'], 1)
        rows = [json.loads(line) for line in (self.state / 'outcomes.jsonl').read_text().splitlines()]
        gate_ids = {r['gate_id'] for r in rows if r['kind'] == 'gate' and 'gate_id' in r}
        gate_ids |= {e['gate_id'] for e in workflow.read_events() if e['kind'] == 'gate'}
        idless = sum(1 for r in rows if r['kind'] == 'gate' and 'gate_id' not in r)
        self.assertEqual(project['gates'], len(gate_ids) + idless)


if __name__ == '__main__':
    unittest.main()
