"""Flow event log (ME-01): envelope, schema, bounded lock, guarded writer, tolerant reader."""
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


class EventsCoreTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='ai-events-'))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.state = self.base / 'state'
        self.repo = self.base / 'events-project'
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ('AI_RUN_ID', 'AI_EVENTS_LOCK_SECONDS', 'AI_GATE_BROKEN')}
        self.env.update(AI_STATE_DIR=str(self.state), XDG_CONFIG_HOME=str(self.base / 'config'),
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=self.repo, env=self.env, check=True)
        patch = mock.patch.dict(os.environ, {'AI_STATE_DIR': str(self.state)})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop('AI_EVENTS_LOCK_SECONDS', None)
        os.environ.pop('AI_RUN_ID', None)

    def event(self, *args, **env):
        return subprocess.run([sys.executable, str(HELPER), 'event', *args], cwd=self.repo,
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


if __name__ == '__main__':
    unittest.main()
