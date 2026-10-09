"""Safe record I/O for the dashboard: observation writer, notification log, host registry and
the bounded readers in workflow.py (T001)."""
import fcntl
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/lib/workflow.py'
TIMEOUT_SCALE = float(os.environ.get('AI_TEST_TIMEOUT_SCALE', '1'))
BOUND = 5 * TIMEOUT_SCALE
GIT = ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
       '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main']


def load_workflow():
    spec = importlib.util.spec_from_file_location('workflow_records', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wf = load_workflow()


def task(task_id, status='TODO'):
    return (f'## {task_id} — Verify {task_id}\nStatus: {status}\nDependencies: none\n\n'
            '### Goal\nx\n### Implementation notes\nx\n### Likely affected modules\nx\n'
            '### Acceptance criteria\nx\n### Validation\nx\n### Result / notes\nx\n\n')


class ObservationWriterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ai-observe-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.checkout = self.tmp / 'checkout'
        self.checkout.mkdir()
        subprocess.run([*GIT, 'init', '-q', '-b', 'feature/x', str(self.checkout)], check=True)
        (self.checkout / '.ai/local').mkdir(parents=True)
        self.local = self.checkout / '.ai/local'
        self.state = self.tmp / 'state'
        self.sentinel = self.tmp / 'sentinel'
        self.sentinel.write_text('SENTINEL\n')
        self.env = {**os.environ, 'AI_ROOT': str(self.checkout), 'AI_STATE_DIR': str(self.state)}

    def helper(self, *args, cwd=None, env=None, timeout=None):
        started = time.monotonic()
        result = subprocess.run([sys.executable, str(HELPER), *args], cwd=cwd or self.checkout,
                                env=env or self.env, capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=timeout or 30 * TIMEOUT_SCALE)
        result.elapsed = time.monotonic() - started
        return result

    def observe(self, *args):
        result = self.helper('observe', *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def record(self):
        return json.loads((self.local / 'observation.json').read_text())

    def seed(self, **fields):
        record = {'stage': 'none', 'state': 'active', 'detail': '', 'since': '2000-01-01T00:00:00Z',
                  'note': '', 'pid': 1, 'branch': None, 'updated': '2000-01-01T00:00:00Z'}
        record.update(fields)
        (self.local / 'observation.json').write_text(json.dumps(record))

    def assert_sentinel(self):
        self.assertEqual(self.sentinel.read_text(), 'SENTINEL\n')

    def in_process(self, function, *args):
        with mock.patch.dict(os.environ, {'AI_ROOT': str(self.checkout)}):
            function(list(args))

    # observe: actions and schema

    def test_observation_writer_actions_and_schema(self):
        self.observe('step', 'build', 'T001 · opus · 1/3')
        record = self.record()
        self.assertEqual(set(record), {'stage', 'state', 'detail', 'since', 'note', 'pid', 'branch',
                                       'updated'})
        self.assertEqual((record['stage'], record['state'], record['detail'], record['note']),
                         ('build', 'active', 'T001 · opus · 1/3', ''))
        self.observe('pause', 'claude until 10:00')
        paused = self.record()
        self.assertEqual((paused['stage'], paused['state'], paused['detail'], paused['since'],
                          paused['note']),
                         ('build', 'paused', record['detail'], record['since'], 'claude until 10:00'))
        self.observe('resume')
        resumed = self.record()
        self.assertEqual((resumed['stage'], resumed['state'], resumed['detail'], resumed['since'],
                          resumed['note']), ('build', 'active', record['detail'], record['since'], ''))
        for final in (('stop', 'review', 'failed'), ('done', 'https://example.invalid/pr/1')):
            self.seed(stage='review', detail='old', note='old')
            self.observe(*final)
            self.observe('start')
            started = self.record()
            self.assertEqual((started['stage'], started['state'], started['detail'], started['note']),
                             ('none', 'active', '', ''))
            self.assertNotEqual(started['since'], '2000-01-01T00:00:00Z')

    def test_observation_writer_detail_only_on_recorded_stage(self):
        self.seed(stage='review', detail='round 1')
        self.observe('detail', 'review', 'format retry')
        record = self.record()
        self.assertEqual((record['stage'], record['detail'], record['since']),
                         ('review', 'format retry', '2000-01-01T00:00:00Z'))
        self.observe('step', 'build')
        before = (self.local / 'observation.json').read_bytes()
        self.observe('detail', 'review', 'format retry')
        self.assertEqual((self.local / 'observation.json').read_bytes(), before)

    def test_observation_writer_done_records_pr(self):
        self.seed(stage='checks', detail='final')
        self.observe('done', 'no PR')
        record = self.record()
        self.assertEqual((record['stage'], record['state'], record['note'], record['detail']),
                         ('pr', 'done', 'no PR', ''))
        self.assertNotEqual(record['since'], '2000-01-01T00:00:00Z')

    def test_observation_writer_pid_and_branch(self):
        command = f'{sys.executable} {HELPER} observe step build; echo $$'
        result = subprocess.run(['bash', '-c', command], cwd=self.checkout, env=self.env,
                                capture_output=True, text=True, timeout=30 * TIMEOUT_SCALE)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.record()
        self.assertEqual(record['pid'], int(result.stdout.strip()))
        self.assertEqual(record['branch'], 'feature/x')

    def test_observation_writer_stop_labels(self):
        targets = {'start': 'none', 'plan review': 'plan_review', 'plan revision': 'plan_revision',
                   'implementation': 'build', 'validation': 'checks', 'review': 'review',
                   'triage': 'triage', 're-check': 'recheck', 'pull request preparation': 'pr',
                   'push': 'pr', 'pull request': 'pr', 'final push': 'pr'}
        for label, target in targets.items():
            outside = 'build' if label == 'triage' else 'triage'
            self.observe('step', outside)
            self.observe('stop', label, 'failed')
            record = self.record()
            self.assertEqual((record['stage'], record['state'], record['note']),
                             (target, 'stopped', 'failed'), label)
        cases = (('plan_revision', 'plan review', 'plan_revision'), ('build', 'plan review', 'plan_review'),
                 ('checks', 'implementation', 'checks'), ('setup', 'implementation', 'setup'),
                 ('triage', 'start', 'none'), ('review', 'crash (pipeline killed)', 'review'),
                 ('review', '', 'review'))
        for stage, label, expected in cases:
            self.observe('step', stage)
            self.observe('stop', label, 'reason')
            self.assertEqual(self.record()['stage'], expected, (stage, label))

    def test_observation_writer_recovering(self):
        self.observe('step', 'build')
        self.observe('recovering', '1/2', 'checks')
        record = self.record()
        self.assertEqual((record['stage'], record['state'], record['note']), ('checks', 'recovering', '1/2'))
        self.observe('step', 'review')
        self.observe('recovering', '2/2')
        self.assertEqual((self.record()['stage'], self.record()['state']), ('review', 'recovering'))
        before = (self.local / 'observation.json').read_bytes()
        result = self.observe('recovering', '2/2', 'bogus')
        self.assertIn('Warning:', result.stderr)
        self.assertEqual((self.local / 'observation.json').read_bytes(), before)
        result = self.observe('step', 'nonsense')
        self.assertIn('Warning:', result.stderr)
        self.assertEqual((self.local / 'observation.json').read_bytes(), before)

    # observe: symlinks and swapped directories

    def test_observation_writer_refuses_symlinked_directories(self):
        outside = self.tmp / 'outside'
        (outside / 'local').mkdir(parents=True)
        shutil.rmtree(self.local)
        self.local.symlink_to(outside / 'local')
        result = self.observe('step', 'build')
        self.assertIn('Warning:', result.stderr)
        self.assertEqual(list((outside / 'local').iterdir()), [])
        self.local.unlink()
        ai = self.checkout / '.ai'
        ai.rmdir()
        ai.symlink_to(outside)
        result = self.observe('step', 'build')
        self.assertIn('Warning:', result.stderr)
        self.assertEqual(list((outside / 'local').iterdir()), [])
        result = self.helper('notify-log', str(self.checkout), 'hello')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Warning:', result.stderr)
        self.assertEqual(list((outside / 'local').iterdir()), [])

    def test_observation_writer_replaces_symlinked_record(self):
        (self.local / 'observation.json').symlink_to(self.sentinel)
        result = self.observe('step', 'build')
        self.assert_sentinel()
        self.assertFalse((self.local / 'observation.json').is_symlink())
        self.assertEqual(self.record()['stage'], 'build')
        self.assertIn('Warning:', result.stderr)

    def test_observation_writer_preplanted_temp_symlink(self):
        (self.local / f'.observation.json.{os.getpid()}.tmp').symlink_to(self.sentinel)
        self.in_process(wf.observe, 'step', 'checks')
        self.assert_sentinel()
        self.assertEqual(self.record()['stage'], 'checks')

    def test_observation_writer_local_swapped_after_validation(self):
        outside = self.tmp / 'outside'
        outside.mkdir()
        (outside / 'observation.json').symlink_to(self.sentinel)
        moved = self.checkout / '.ai/moved'
        original = wf.checkout_fds

        def swapping(root):
            fds = original(root)
            self.local.rename(moved)
            self.local.symlink_to(outside)
            return fds

        with mock.patch.object(wf, 'checkout_fds', swapping):
            self.in_process(wf.observe, 'step', 'review')
        self.assert_sentinel()
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ['observation.json'])
        self.assertEqual(json.loads((moved / 'observation.json').read_text())['stage'], 'review')

    # FIFOs and held locks

    def assert_bounded_warning(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Warning:', result.stderr)

    def test_observation_writer_fifos_and_held_locks_return(self):
        os.mkfifo(self.local / 'observation.json')
        self.assert_bounded_warning(self.helper('observe', 'step', 'build', timeout=BOUND))
        os.mkfifo(self.local / 'notifications.log')
        self.assert_bounded_warning(self.helper('notify-log', str(self.checkout), 'hi', timeout=BOUND))
        (self.local / 'notifications.log').unlink()
        (self.local / 'notifications.lock').unlink()
        os.mkfifo(self.local / 'notifications.lock')
        self.assert_bounded_warning(self.helper('notify-log', str(self.checkout), 'hi', timeout=BOUND))
        (self.local / 'notifications.lock').unlink()
        for name, args in (('observation.lock', ('observe', 'step', 'checks')),
                           ('notifications.lock', ('notify-log', str(self.checkout), 'held'))):
            holder = subprocess.Popen(
                [sys.executable, '-c', 'import fcntl, sys, time\n'
                 'f = open(sys.argv[1], "a"); fcntl.flock(f, fcntl.LOCK_EX)\n'
                 'print("locked", flush=True); time.sleep(60)', str(self.local / name)],
                stdout=subprocess.PIPE, text=True)
            self.addCleanup(holder.wait)
            self.addCleanup(holder.kill)
            self.assertEqual(holder.stdout.readline().strip(), 'locked')
            result = self.helper(*args, timeout=BOUND)
            self.assert_bounded_warning(result)
            self.assertIn('still held', result.stderr)
            holder.kill()
        self.assertNotEqual(self.record()['stage'], 'checks')
        self.assertFalse((self.local / 'notifications.log').exists())

    # read_record

    def test_observation_writer_read_record_bounds(self):
        directory = self.tmp / 'reads'
        directory.mkdir()
        os.mkfifo(directory / 'fifo')
        (directory / 'zero').symlink_to('/dev/zero')
        big = directory / 'big'
        big.write_bytes(b'x' * (10 * 1024 * 1024))
        (directory / 'bad').write_bytes(b'ok \xff\xfe end')
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        started = time.monotonic()
        self.assertIsNone(wf.read_record(fd, 'fifo', 4096))
        self.assertIsNone(wf.read_record(fd, 'zero', 4096))
        self.assertIsNone(wf.read_record(fd, 'missing', 4096))
        self.assertIsNone(wf.read_record(fd, '../reads/big', 4096))
        text, info = wf.read_record(fd, 'big', 65536)
        self.assertEqual(len(text), 65536)
        self.assertEqual((info.st_ino, info.st_size), (big.stat().st_ino, big.stat().st_size))
        text, _ = wf.read_record(fd, 'bad', 4096)
        self.assertEqual(text, 'ok �� end')
        self.assertLess(time.monotonic() - started, BOUND)

    def test_observation_writer_read_record_tail(self):
        directory = self.tmp / 'reads'
        directory.mkdir()
        lines = [f'line {number:08d}' for number in range(10 * 1024 * 1024 // 14 + 1)]
        (directory / 'log').write_text('\n'.join(lines) + '\n')
        self.assertGreater((directory / 'log').stat().st_size, 10 * 1024 * 1024)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        limit = 256 * 1024
        text, _ = wf.read_record(fd, 'log', limit, tail=True)
        self.assertLessEqual(len(text.encode()), limit)
        got = text.splitlines()
        self.assertEqual(got, lines[-len(got):])
        self.assertGreater(len(got), limit // 14 - 2)
        self.assertNotIn(lines[0], got)
        text, _ = wf.read_record(fd, 'log', limit, tail=False)
        self.assertEqual(text.splitlines()[:3], lines[:3])
        small, _ = wf.read_record(fd, 'log', 30, tail=True)
        self.assertEqual(small, lines[-2] + '\n' + lines[-1] + '\n')

    # git_branch

    def branch_of(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            return wf.git_branch(fd)
        finally:
            os.close(fd)

    def test_observation_writer_git_branch(self):
        self.assertEqual(self.branch_of(self.checkout), 'feature/x')
        subprocess.run([*GIT, '-C', str(self.checkout), 'commit', '-q', '--allow-empty', '-m', 'init'],
                       check=True)
        worktree = self.tmp / 'worktree'
        subprocess.run([*GIT, '-C', str(self.checkout), 'worktree', 'add', '-q', '-b', 'wt/branch',
                        str(worktree)], check=True)
        self.assertEqual(self.branch_of(worktree), 'wt/branch')
        subprocess.run([*GIT, '-C', str(worktree), 'checkout', '-q', '--detach'], check=True)
        self.assertEqual(self.branch_of(worktree), 'detached')
        started = time.monotonic()
        cases = self.tmp / 'cases'
        fifo = cases / 'fifo'
        fifo.mkdir(parents=True)
        os.mkfifo(fifo / '.git')
        self.assertIsNone(self.branch_of(fifo))
        linked = cases / 'linked'
        linked.mkdir()
        (linked / '.git').symlink_to(self.checkout / '.git')
        self.assertIsNone(self.branch_of(linked))
        gitdir = (worktree / '.git').read_text().split(': ', 1)[1].strip()
        alias = self.tmp / 'alias'
        alias.symlink_to(self.checkout)
        for name, pointer in (('dotdot', f'gitdir: {self.checkout}/.git/../.git/worktrees/worktree'),
                              ('relative', 'gitdir: ../checkout/.git/worktrees/worktree'),
                              ('symlinked', f'gitdir: {alias}/.git/worktrees/worktree'),
                              ('control', f'gitdir: {gitdir}')):
            directory = cases / name
            directory.mkdir()
            (directory / '.git').write_text(pointer + '\n')
        self.assertEqual(self.branch_of(cases / 'control'), 'detached')
        for name in ('dotdot', 'relative', 'symlinked'):
            self.assertIsNone(self.branch_of(cases / name), name)
        self.assertLess(time.monotonic() - started, BOUND)

    # checkout_fds / open_dir

    def test_observation_writer_checkout_fds(self):
        (self.checkout / '.ai/tasks.md').write_text('original\n')
        fds = wf.checkout_fds(str(self.checkout))
        self.addCleanup(wf.close_fds, *fds)
        outside = self.tmp / 'outside'
        outside.mkdir()
        (outside / 'tasks.md').write_text('planted\n')
        (self.checkout / '.ai').rename(self.checkout / '.ai-moved')
        (self.checkout / '.ai').symlink_to(outside)
        self.assertEqual(wf.read_record(fds[1], 'tasks.md', 1024)[0], 'original\n')
        self.assertIsNone(wf.checkout_fds(str(self.checkout)))
        self.assertIsNone(wf.open_dir(fds[0], '.ai'))
        self.assertIsNone(wf.open_dir(fds[0], '.ai-moved/../.ai-moved'))
        local = wf.open_dir(fds[0], '.ai-moved/local')
        self.assertIsNotNone(local)
        os.close(local)

    # notify-log

    def log_lines(self):
        return [json.loads(line) for line in (self.local / 'notifications.log').read_text().splitlines()]

    def test_observation_writer_hard_links_untouched(self):
        os.link(self.sentinel, self.local / 'notifications.log')
        os.link(self.sentinel, self.local / 'observation.json')
        self.assertEqual(self.helper('notify-log', str(self.checkout), 'first').returncode, 0)
        self.observe('step', 'build')
        self.assert_sentinel()
        self.assertEqual(self.log_lines()[-1]['message'], 'first')
        self.assertEqual(self.record()['stage'], 'build')

    def test_observation_writer_notify_log_symlinks(self):
        (self.local / 'notifications.log').symlink_to(self.sentinel)
        self.assertEqual(self.helper('notify-log', str(self.checkout), 'one').returncode, 0)
        self.assert_sentinel()
        self.assertEqual([entry['message'] for entry in self.log_lines()], ['one'])
        lock_target = self.tmp / 'lock-target'
        lock_target.write_text('SENTINEL\n')
        (self.local / 'notifications.lock').unlink()
        (self.local / 'notifications.lock').symlink_to(lock_target)
        result = self.helper('notify-log', str(self.checkout), 'two')
        self.assert_bounded_warning(result)
        self.assertEqual(lock_target.read_text(), 'SENTINEL\n')
        self.assertEqual([entry['message'] for entry in self.log_lines()], ['one'])

    def test_observation_writer_notify_log_keeps_last_200(self):
        for number in range(250):
            wf.notify_log([str(self.checkout), f'message {number}'])
        entries = self.log_lines()
        self.assertEqual([entry['message'] for entry in entries],
                         [f'message {number}' for number in range(50, 250)])
        self.assertTrue(all(set(entry) == {'ts', 'message'} for entry in entries))

    def test_observation_writer_notify_log_concurrent(self):
        (self.local / 'notifications.log').write_text(''.join(
            json.dumps({'ts': 'old', 'message': f'old {n}'}) + '\n' for n in range(200)))
        script = ('import importlib.util, sys\n'
                  'spec = importlib.util.spec_from_file_location("wf", sys.argv[1])\n'
                  'wf = importlib.util.module_from_spec(spec); spec.loader.exec_module(wf)\n'
                  'for n in range(100):\n'
                  '    wf.record_command("notify-log", [sys.argv[2], f"{sys.argv[3]} {n}"])\n')
        workers = [subprocess.Popen([sys.executable, '-c', script, str(HELPER), str(self.checkout), name],
                                    stderr=subprocess.PIPE, text=True) for name in ('a', 'b')]
        for worker in workers:
            _, stderr = worker.communicate(timeout=120 * TIMEOUT_SCALE)
            self.assertEqual((worker.returncode, stderr), (0, ''))
        messages = [entry['message'] for entry in self.log_lines()]
        self.assertEqual(sorted(messages), sorted(f'{name} {n}' for name in 'ab' for n in range(100)))
        for name in 'ab':
            own = [message for message in messages if message.startswith(name + ' ')]
            self.assertEqual(own, [f'{name} {n}' for n in range(100)])

    # pipeline-register

    def entry_name(self, checkout):
        return hashlib.sha256(str(checkout).encode()).hexdigest()[:16] + '.json'

    def test_observation_writer_pipeline_register(self):
        pipelines = self.state / 'pipelines'
        pipelines.mkdir(parents=True)
        gone = pipelines / 'aaaaaaaaaaaaaaaa.json'
        gone.write_text(json.dumps({'checkout': str(self.tmp / 'removed'), 'project': 'x'}))
        (pipelines / 'bbbbbbbbbbbbbbbb.json').write_text('{not json')
        other = self.tmp / 'other'
        other.mkdir()
        alive = pipelines / 'cccccccccccccccc.json'
        alive.write_text(json.dumps({'checkout': str(other), 'project': 'other'}))
        result = self.helper('pipeline-register', str(self.checkout), 'feature/x')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        entry = json.loads((pipelines / self.entry_name(self.checkout)).read_text())
        self.assertEqual((entry['checkout'], entry['project'], entry['branch']),
                         (str(self.checkout), 'checkout', 'feature/x'))
        self.assertTrue(entry['started'])
        self.assertEqual(sorted(p.name for p in pipelines.iterdir()),
                         sorted(['.lock', alive.name, self.entry_name(self.checkout)]))

    def test_observation_writer_pipeline_register_keeps_replaced_entry(self):
        pipelines = self.state / 'pipelines'
        pipelines.mkdir(parents=True)
        stale = pipelines / 'dddddddddddddddd.json'
        stale.write_text(json.dumps({'checkout': str(self.tmp / 'removed')}))
        other = self.tmp / 'other'
        other.mkdir()

        def rewrite(directory, names):
            self.assertIn(stale.name, names)
            stale.write_text(json.dumps({'checkout': str(other)}))

        with mock.patch.object(wf, 'PRUNE_HOOK', rewrite), \
                mock.patch.dict(os.environ, {'AI_STATE_DIR': str(self.state)}):
            wf.pipeline_register([str(self.checkout), 'feature/x'])
        self.assertEqual(json.loads(stale.read_text())['checkout'], str(other))

    def test_observation_writer_pipeline_register_unusable_directory(self):
        self.state.mkdir()
        (self.state / 'pipelines').write_text('a file\n')
        (self.state / 'outcomes.jsonl').write_text('{"keep": true}\n')
        result = self.helper('pipeline-register', str(self.checkout), 'feature/x')
        self.assert_bounded_warning(result)
        self.assertEqual((self.state / 'pipelines').read_text(), 'a file\n')
        self.assertEqual((self.state / 'outcomes.jsonl').read_text(), '{"keep": true}\n')
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), ['outcomes.jsonl', 'pipelines'])
        inside = {**self.env, 'AI_STATE_DIR': str(self.checkout / 'state')}
        self.assert_bounded_warning(self.helper('pipeline-register', str(self.checkout), 'x', env=inside))
        self.assertFalse((self.checkout / 'state').exists())

    # tasks counts

    def test_observation_writer_tasks_counts(self):
        queue = ''.join(task(f'T00{n}', 'DONE' if n <= 2 else 'TODO') for n in range(1, 6))
        (self.checkout / '.ai/tasks.md').write_text('# Task queue\n\n' + queue)
        result = self.helper('tasks', 'counts')
        self.assertEqual((result.returncode, result.stdout), (0, '2 5\n'))
        (self.checkout / '.ai/tasks.md').write_text('# Task queue\n\n' + task('T001'))
        self.assertEqual(self.helper('tasks', 'counts').stdout, '0 1\n')
        (self.checkout / '.ai/tasks.md').write_text('# Task queue\n\n## T01x broken\n')
        counts, count = self.helper('tasks', 'counts'), self.helper('tasks', 'count')
        self.assertEqual(counts.returncode, 1)
        self.assertEqual((counts.returncode, counts.stderr), (count.returncode, count.stderr))
        self.assertIn('Malformed task heading', counts.stderr)


if __name__ == '__main__':
    unittest.main()
