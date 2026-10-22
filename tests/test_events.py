"""Flow event log (ME-01): envelope, schema, bounded lock, guarded writer, tolerant reader."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
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


if __name__ == '__main__':
    unittest.main()
