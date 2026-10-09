"""Dashboard discovery, liveness and text sanitising (scripts/lib/dashboard.py, T006). Every test
sets AI_DASHBOARD_ROOT to its temp base, and AI_DASHBOARD_PROC to a fixture process tree unless
it needs a real process: the parallel gate and the host run real pipelines elsewhere."""
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
LIB = ROOT / 'scripts/lib'
TIMEOUT_SCALE = float(os.environ.get('AI_TEST_TIMEOUT_SCALE', '1'))
BOUND = 5 * TIMEOUT_SCALE
CLOCK_TICKS = os.sysconf('SC_CLK_TCK')
BTIME = 1_700_000_000


def load_dashboard():
    spec = importlib.util.spec_from_file_location('dashboard_view', LIB / 'dashboard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dash = load_dashboard()


class FakeProc:
    """A fixture process tree: `stat` with btime plus `<pid>/{stat,cmdline,cwd}` entries."""

    def __init__(self, root):
        self.root = root
        root.mkdir()
        (root / 'stat').write_text(f'cpu 1 2 3 4\nbtime {BTIME}\nprocesses 9\n')

    def add(self, pid, args, cwd, started=None, state='S', stat=True):
        entry = self.root / str(pid)
        entry.mkdir()
        started = time.time() - 60 if started is None else started
        ticks = int((started - BTIME) * CLOCK_TICKS)
        if stat:
            fields = ['0'] * 18 + [str(ticks), '0', '0']
            (entry / 'stat').write_text(f'{pid} (odd) name) {state} ' + ' '.join(fields) + '\n')
        (entry / 'cmdline').write_bytes(b'\0'.join(os.fsencode(arg) for arg in args) + b'\0')
        os.symlink(str(cwd), entry / 'cwd')
        return entry


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='ai-dashboard-'))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.state = self.base / 'state'
        self.proc = FakeProc(self.base / 'proc')
        environment = mock.patch.dict(os.environ, {'AI_STATE_DIR': str(self.state),
                                                   'AI_DASHBOARD_ROOT': str(self.base),
                                                   'AI_DASHBOARD_PROC': str(self.proc.root)})
        environment.start()
        self.addCleanup(environment.stop)

    def checkout(self, name, base=None):
        path = (base or self.base) / name
        (path / '.ai/local').mkdir(parents=True)
        return path

    def register(self, name, checkout=None, raw=None):
        (self.state / 'pipelines').mkdir(parents=True, exist_ok=True)
        record = raw if raw is not None else json.dumps(
            {'checkout': str(checkout), 'project': 'p', 'branch': 'b', 'started': '2026-10-09T00:00:00Z'})
        (self.state / 'pipelines' / name).write_text(record)

    def mark(self, checkout, pid, written=None):
        marker = checkout / '.ai/local/pipeline.active'
        marker.write_text(f'{pid}\n')
        if written is not None:
            os.utime(marker, (written, written))
        return marker

    def local_fd(self, checkout):
        fds = dash.checkout_fds(str(checkout))
        self.assertIsNotNone(fds)
        self.addCleanup(dash.close_fds, *fds)
        return fds[2]

    def live(self, checkout, source=None):
        source = source or dash.ProcSource()
        runners = dict(dash.discover(source)).get(str(checkout), [])
        return dash.liveness(self.local_fd(checkout), runners, source)

    def spawn(self, name, checkout):
        """A real process named NAME (a symlink to a sleeping script) working in CHECKOUT."""
        bin_dir = self.base / 'bin'
        bin_dir.mkdir(exist_ok=True)
        script = bin_dir / 'runner.py'
        script.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(120)\n')
        script.chmod(0o755)
        link = bin_dir / name
        link.symlink_to(script)
        process = subprocess.Popen([str(link)], cwd=checkout, stdin=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process

    def test_dashboard_liveness_real_pipeline_and_recover(self):
        real = dash.ProcSource('/proc')
        for name in ('ai-pipeline', 'ai-recover'):
            with self.subTest(name=name):
                checkout = self.checkout(name + '-checkout')
                process = self.spawn(name, checkout)
                self.mark(checkout, process.pid)
                found = dict(dash.discover(real))
                self.assertIn(process.pid, [pid for pid, _ in found[str(checkout)]])
                self.assertTrue(all(dash.inside(os.path.realpath(path), str(self.base))
                                    for path in found))
                self.assertEqual(self.live(checkout, real), 'alive')

    def test_dashboard_liveness_fixture_pipeline_alive(self):
        checkout = self.checkout('c')
        self.proc.add(4242, ['bash', '/opt/x/.ai/bin/ai-pipeline'], checkout)
        self.mark(checkout, 4242)
        self.assertEqual(self.live(checkout), 'alive')

    def test_dashboard_liveness_reused_pid_is_crashed(self):
        checkout = self.checkout('c')
        written = time.time() - 30
        self.proc.add(4242, ['bash', '/opt/x/.ai/bin/ai-pipeline'], checkout, started=written + 10)
        self.mark(checkout, 4242, written)
        self.assertEqual(self.live(checkout), 'crashed')

    def test_dashboard_liveness_marker_removed_between_reads_is_gone(self):
        checkout = self.checkout('c')
        marker = self.mark(checkout, 4242)

        class Finishing(dash.ProcSource):
            def process(self, pid):
                marker.unlink(missing_ok=True)  # The run finishes during the snapshot.
                return super().process(pid)

        self.assertEqual(dash.liveness(self.local_fd(checkout), [], Finishing()), 'gone')

    def test_dashboard_liveness_orphaned_runner_is_crashed(self):
        checkout = self.checkout('c')
        self.mark(checkout, 4242)
        self.proc.add(5000, ['bash', '/opt/x/.ai/bin/ai-run', '--max-tasks', '1'], checkout)
        self.assertEqual([pid for pid, _ in dict(dash.discover())[str(checkout)]], [5000])
        self.assertEqual(self.live(checkout), 'crashed')

    def test_dashboard_liveness_legacy_runner_alive_else_gone(self):
        checkout = self.checkout('c')
        self.proc.add(5000, ['bash', '/opt/x/.ai/bin/ai-run'], checkout)
        self.assertEqual([path for path, _ in dash.discover()], [str(checkout)])
        self.assertEqual(self.live(checkout), 'alive')
        quiet = self.checkout('quiet')
        empty = dash.ProcSource(self.base / 'empty-proc')
        self.assertEqual(dash.discover(empty), [])
        self.assertEqual(dash.liveness(self.local_fd(quiet), [], empty), 'gone')

    def test_dashboard_liveness_root_filter(self):
        elsewhere = Path(tempfile.mkdtemp(prefix='ai-dashboard-elsewhere-'))
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)
        running = self.checkout('running', elsewhere)
        registered = self.checkout('registered', elsewhere)
        self.proc.add(5000, ['bash', '/opt/x/.ai/bin/ai-run'], running)
        self.register('r.json', registered)
        self.assertEqual(dash.discover(), [])
        unfiltered = [path for path, _ in dash.discover(only_under=None)]
        self.assertIn(str(running), unfiltered)
        self.assertIn(str(registered), unfiltered)
        with mock.patch.dict(os.environ, {'AI_DASHBOARD_ROOT': ''}):
            self.assertIn(str(running), [path for path, _ in dash.discover()])

    def test_dashboard_liveness_fifo_marker_and_symlinked_local(self):
        checkout = self.checkout('fifo')
        os.mkfifo(checkout / '.ai/local/pipeline.active')
        self.proc.add(4242, ['bash', '/opt/x/.ai/bin/ai-pipeline'], self.base)
        started = time.monotonic()
        self.assertEqual(self.live(checkout), 'gone')
        linked = self.base / 'linked'
        (linked / '.ai').mkdir(parents=True)
        real_local = self.checkout('real')
        self.mark(real_local, 4242)
        os.symlink(real_local / '.ai/local', linked / '.ai/local')
        fds = dash.checkout_fds(str(linked))
        self.addCleanup(dash.close_fds, *fds)
        self.assertIsNone(fds[2])
        self.assertEqual(dash.liveness(fds[2], [], dash.ProcSource()), 'gone')
        self.assertLess(time.monotonic() - started, BOUND)

    def test_dashboard_liveness_discovery_skips_and_merges(self):
        good = self.checkout('good')
        symlinked = self.base / 'symlinked'
        symlinked.mkdir()
        os.symlink(good / '.ai', symlinked / '.ai')
        self.register('relative.json', 'good')
        self.register('missing.json', self.base / 'missing')
        self.register('symlinked.json', symlinked)
        self.register('invalid.json', raw='{not json')
        self.register('list.json', raw='[1, 2]')
        self.register('good.json', good)
        self.register('alias.json', self.base / '.' / 'good')
        self.proc.add(5000, ['bash', '/opt/x/.ai/bin/ai-run'], good)
        for name, state, stat in (('6000', 'S', False), ('6001', 'Z', True), ('abc', 'S', True)):
            other = self.checkout(f'skipped-{name}')
            entry = self.proc.add(name, ['bash', '/opt/x/.ai/bin/ai-pipeline'], other,
                                  state=state, stat=stat)
            self.assertTrue(entry.is_dir())
        found = dash.discover()
        self.assertEqual([path for path, _ in found], [str(good)])
        self.assertEqual([pid for pid, _ in found[0][1]], [5000])

    def test_dashboard_liveness_writes_nothing(self):
        lib = self.base / 'lib'
        lib.mkdir()
        for name in ('dashboard.py', 'workflow.py', 'watchdog.py'):
            shutil.copy2(LIB / name, lib / name)
        checkout = self.checkout('c')
        self.mark(checkout, 4242)
        self.register('c.json', checkout)
        self.proc.add(4242, ['bash', '/opt/x/.ai/bin/ai-pipeline'], checkout)

        def listing():
            return sorted((str(path), path.lstat().st_mtime_ns) for path in self.base.rglob('*'))

        before = listing()
        code = ('import os, runpy, sys\n'
                'view = runpy.run_path(sys.argv[1])\n'
                'for checkout, runners in view["discover"]():\n'
                '    fds = view["checkout_fds"](checkout)\n'
                '    print(checkout, view["liveness"](fds[2], runners))\n')
        result = subprocess.run([sys.executable, '-c', code, str(lib / 'dashboard.py')],
                                capture_output=True, text=True, timeout=30 * TIMEOUT_SCALE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'{checkout} alive\n')
        self.assertEqual(listing(), before)
        self.assertFalse((lib / '__pycache__').exists())


class DashboardSanitizeTest(unittest.TestCase):
    def test_dashboard_sanitize_escape_sequences(self):
        cases = {
            'csi colour': ('\x1b[31;1mred\x1b[0m', 'red'),
            'csi cursor': ('a\x1b[2J\x1b[10;5Hb\x1b[?25l', 'ab'),
            'osc 8 bel': ('\x1b]8;;https://evil.example\x07link\x1b]8;;\x07', 'link'),
            'osc 8 st': ('\x1b]8;;https://evil.example\x1b\\link\x1b]8;;\x1b\\', 'link'),
            'osc 52': ('x\x1b]52;c;cm0gLXJmIH4=\x07y', 'xy'),
            'osc 52 st': ('x\x1b]52;c;cm0gLXJmIH4=\x1b\\y', 'xy'),
            'dcs': ('a\x1bP1$tx\x1b\\b', 'ab'),
            'apc pm sos': ('a\x1b_apc\x1b\\b\x1b^pm\x1b\\c\x1bXsos\x1b\\d', 'abcd'),
            '8-bit csi': ('a\u009b31mb', 'ab'),
            '8-bit osc': ('a\u009d0;title\u009cb', 'ab'),
            'single escapes': ('a\x1bcb\x1b7c\x1b(Bd', 'abcd'),
            'bare esc at end': ('done\x1b', 'done'),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(dash.sanitize(text), expected)

    def test_dashboard_sanitize_controls_and_bidi(self):
        self.assertEqual(dash.sanitize('safe\rEVIL'), 'safe EVIL')
        self.assertEqual(dash.sanitize('abc\b\b\bxyz'), 'abcxyz')
        self.assertEqual(dash.sanitize('a\x7fb\x00c\x07d\u0085e'), 'abcde')
        self.assertEqual(dash.sanitize('file‮gnp.exe ⁦x⁩ ‪‫‬‭'),
                         'filegnp.exe x')
        self.assertEqual(dash.sanitize('  many \t\n spaces\v\f '), 'many spaces')

    def test_dashboard_sanitize_keeps_utf8_and_caps(self):
        self.assertEqual(dash.sanitize('✅ Café — naïve 🚀 日本'), '✅ Café — naïve 🚀 日本')
        capped = dash.sanitize('x' * 500)
        self.assertEqual(len(capped), 200)
        self.assertTrue(capped.endswith('…'))
        self.assertEqual(dash.sanitize('abcdef', limit=4), 'abc…')
        self.assertEqual(dash.sanitize('abcd', limit=4), 'abcd')
        self.assertEqual(dash.sanitize(None), '')


ESC = '\x1b'
EVIL = f'{ESC}]52;c;ZXZpbA==\x07{ESC}[31mred{ESC}[0m'


class SnapshotTest(DashboardTest):
    """Snapshot model and the `--once`/`--json` CLI (T007)."""

    def plant(self, name, stage=None, state='active', detail='', note='', age=0, branch='main',
              tasks=('DONE', 'IN_PROGRESS', 'TODO'), title='Task'):
        checkout = self.checkout(name)
        (checkout / '.git').mkdir()
        (checkout / '.git/HEAD').write_text(f'ref: refs/heads/{branch}\n')
        blocks = ''.join(f'## T00{n} — {title} {n}\nStatus: {status}\n\n'
                         for n, status in enumerate(tasks, 1))
        (checkout / '.ai/tasks.md').write_text('# Tasks\n\n' + blocks)
        if stage:
            record = {'stage': stage, 'state': state, 'detail': detail, 'note': note,
                      'since': '2026-10-09T10:00:00Z', 'pid': 1, 'branch': branch,
                      'updated': '2026-10-09T10:00:00Z'}
            (checkout / '.ai/local/observation.json').write_text(json.dumps(record))
        self.register(name + '.json', checkout)
        if age:
            self.age(checkout, age)
        return checkout

    def age(self, checkout, seconds):
        then = time.time() - seconds
        for path in checkout.rglob('*'):
            if path.is_file():
                os.utime(path, (then, then))

    def run_cli(self, *options, tool=None, cwd=None, expected=0):
        command = [sys.executable, '-B', str(LIB / 'dashboard.py')] if tool is None else [str(tool)]
        result = subprocess.run([*command, *options], cwd=cwd or self.base, capture_output=True,
                                text=True, timeout=BOUND * 3)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def runs(self, *options):
        data = json.loads(self.run_cli('--json', *options).stdout)
        return {run['project']: run for run in data['runs']}

    def test_dashboard_snapshot_empty_state_names_state_root(self):
        data = json.loads(self.run_cli('--json').stdout)
        self.assertEqual(data, {'state_root': str(self.state), 'runs': []})
        self.assertIn(str(self.state), self.run_cli('--once').stdout)

    def test_dashboard_snapshot_statuses(self):
        live = self.plant('live', 'build', detail='T003')
        self.proc.add(4001, ['bash', '/x/.ai/bin/ai-pipeline'], live)
        self.mark(live, 4001)
        paused = self.plant('paused', 'review', 'paused', note='limit')
        self.proc.add(4002, ['bash', '/x/.ai/bin/ai-pipeline'], paused)
        self.mark(paused, 4002)
        recovering = self.plant('recovering', 'checks', 'recovering')
        self.proc.add(4003, ['bash', '/x/.ai/bin/ai-pipeline'], recovering)
        self.mark(recovering, 4003)
        self.plant('question', 'plan_revision', 'stopped', note='Which database?')
        self.plant('atstart', 'none', 'stopped', note='base moved')
        crashed = self.plant('crashed', 'build')
        self.mark(crashed, 4999)
        self.plant('finished', 'pr', 'done', note='PR open')
        self.plant('idle', None)
        broken = self.plant('broken', 'build')
        error = broken / '.ai/local/last-error'
        error.write_text('gate is broken\nsecond line\n')
        future = time.time() + 5
        os.utime(error, (future, future))
        runs = self.runs()
        expected = {'live': ('running', 'build'), 'paused': ('paused', 'review'),
                    'recovering': ('recovering', 'checks'), 'question': ('needs_you', 'plan_revision'),
                    'atstart': ('needs_you', 'none'), 'crashed': ('crashed', 'build'),
                    'finished': ('finished', 'pr'), 'idle': ('idle', 'unknown'),
                    'broken': ('needs_you', 'build')}
        self.assertEqual({name: (run['status'], run['stage']) for name, run in runs.items()}, expected)
        self.assertEqual(runs['question']['observation']['note'], 'Which database?')
        self.assertEqual(runs['broken']['last_error'], 'gate is broken')
        self.assertEqual(runs['live']['branch'], 'main')
        self.assertEqual(runs['live']['tasks'], {'done': 1, 'total': 3, 'current': 'Task 2'})
        order = [run['status'] for run in json.loads(self.run_cli('--json').stdout)['runs']]
        ranks = [dash.RANK[status] for status in order]
        self.assertEqual(ranks, sorted(ranks))

    def test_dashboard_snapshot_real_process_through_symlink(self):
        checkout = self.plant('real', 'build')
        process = self.spawn('ai-pipeline', checkout)
        self.mark(checkout, process.pid)
        with mock.patch.dict(os.environ, {'AI_DASHBOARD_PROC': '/proc'}):
            self.assertEqual(self.runs()['real']['status'], 'running')

    def test_dashboard_snapshot_legacy_checkout_found_by_process(self):
        checkout = self.checkout('legacy')
        self.proc.add(5000, ['bash', '/opt/x/.ai/bin/ai-run'], checkout)
        run = self.runs()['legacy']
        self.assertEqual((run['status'], run['stage'], run['observation']), ('running', 'unknown', None))

    def test_dashboard_snapshot_malformed_records(self):
        checkout = self.plant('bad', 'bogus_stage')
        (checkout / '.ai/local/notifications.log').write_text(
            'not json\n{"ts": "t1", "message": "ok"}\n[1]\n{"message": 5}\n')
        (checkout / '.ai/tasks.md').write_text('## T001 oops no dash\n')
        run = self.runs()['bad']
        self.assertEqual((run['status'], run['stage'], run['observation'], run['tasks']),
                         ('idle', 'unknown', None, None))
        self.assertEqual(run['events'], [{'ts': 't1', 'message': 'ok'}])
        (checkout / '.ai/local/observation.json').write_text('{')
        self.assertIsNone(self.runs()['bad']['observation'])
        (checkout / '.ai/tasks.md').unlink()
        self.assertIsNone(self.runs()['bad']['tasks'])

    def test_dashboard_snapshot_sanitises_every_field(self):
        checkout = self.plant('evil' + EVIL, 'build', 'stopped', detail=EVIL, note=EVIL,
                              branch='br' + EVIL, title=EVIL)
        (checkout / '.ai/local/notifications.log').write_text(
            json.dumps({'ts': EVIL, 'message': EVIL}) + '\n')
        (checkout / '.ai/local/last-error').write_text(EVIL + '\n')
        future = time.time() + 5
        os.utime(checkout / '.ai/local/last-error', (future, future))
        for options in (('--once',), ('--json',), ('--once', '--all')):
            output = self.run_cli(*options).stdout
            with self.subTest(options=options):
                self.assertIn('red', output)
                self.assertNotIn(ESC, output)
                self.assertNotIn('\x07', output)
                self.assertNotIn('ZXZpbA', output)

    def test_dashboard_snapshot_unreadable_checkout_next_to_healthy_one(self):
        healthy = self.plant('healthy', 'checks')
        hostile = self.plant('hostile', 'build')
        (hostile / '.ai/local/pipeline.active').unlink(missing_ok=True)
        os.mkfifo(hostile / '.ai/local/pipeline.active')
        (hostile / '.ai/local/observation.json').unlink()
        os.mkfifo(hostile / '.ai/local/observation.json')
        with (hostile / '.ai/local/notifications.log').open('w') as file:
            for number in range(300_000):
                file.write(json.dumps({'ts': 't', 'message': f'event {number}'}) + '\n')
        self.assertGreater((hostile / '.ai/local/notifications.log').stat().st_size, 10 * 1024 * 1024)
        start = time.monotonic()
        result = self.run_cli('--once')
        self.assertLess(time.monotonic() - start, BOUND)
        self.assertIn('healthy · main', result.stdout)
        self.assertIn('stage checks (active)', result.stdout)
        runs = self.runs()
        self.assertEqual(runs['healthy']['stage'], 'checks')
        self.assertEqual(runs['hostile']['stage'], 'unknown')
        self.assertEqual(runs['hostile']['events'][-1]['message'], 'event 299999')
        self.assertEqual(len(runs['hostile']['events']), 20)
        self.assertIsNotNone(healthy)

    def test_dashboard_snapshot_hides_old_finished_and_idle(self):
        day = 25 * 3600
        self.plant('old-finished', 'pr', 'done', age=day)
        self.plant('old-idle', None, age=day)
        self.plant('old-needs', 'build', 'stopped', age=day)
        old_crash = self.plant('old-crash', 'build', age=day)
        self.mark(old_crash, 4999, time.time() - day)
        self.plant('new-finished', 'pr', 'done')
        self.assertEqual(sorted(self.runs()), ['new-finished', 'old-crash', 'old-needs'])
        self.assertEqual(sorted(self.runs('--all')),
                         ['new-finished', 'old-crash', 'old-finished', 'old-idle', 'old-needs'])

    def tree(self, *paths):
        listing = {}
        for path in paths:
            for entry in [Path(path), *Path(path).rglob('*')]:
                info = entry.lstat()
                listing[str(entry)] = (info.st_mtime_ns, info.st_size)
        return listing

    def install(self, name='installed'):
        project = self.base / name
        project.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=project, check=True)
        result = subprocess.run([str(ROOT / 'scripts/setup-project'), str(project)], capture_output=True,
                                text=True, timeout=BOUND * 6)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return project

    def test_dashboard_snapshot_read_only_from_toolkit_and_install(self):
        self.plant('a', 'build')
        self.plant('b', 'pr', 'done')
        project = self.install()
        watched = (self.base / 'a', self.base / 'b', self.state, ROOT / 'scripts', project / '.ai/bin')
        before = self.tree(*watched)
        for command in ([sys.executable, '-B', str(LIB / 'dashboard.py')],
                        [str(project / '.ai/bin/ai-dashboard')]):
            for options in (['--once'], ['--json'], ['--once', '--all']):
                subprocess.run([*command, *options], cwd=self.base, check=True, capture_output=True,
                               timeout=BOUND * 3)
        self.assertEqual(self.tree(*watched), before)
        self.assertEqual(list((project / '.ai/bin').rglob('__pycache__')), [])

    def test_dashboard_snapshot_wrapper_through_symlink_outside_a_checkout(self):
        project = self.install()
        bin_dir = self.base / 'elsewhere-bin'
        bin_dir.mkdir()
        (bin_dir / 'ai-dashboard').symlink_to(project / '.ai/bin/ai-dashboard')
        outside = self.base / 'not-a-checkout'
        outside.mkdir()
        self.plant('seen', 'build')
        result = self.run_cli('--once', tool=bin_dir / 'ai-dashboard', cwd=outside)
        self.assertIn('seen · main', result.stdout)

    def test_dashboard_snapshot_setup_and_upgrade_install_the_dashboard(self):
        project = self.install()
        installed = [project / '.ai/bin/ai-dashboard', project / '.ai/bin/lib/dashboard.py']
        for path in installed:
            self.assertTrue(path.is_file(), path)
        self.assertTrue(os.access(installed[0], os.X_OK))
        for path in installed:
            path.unlink()
        result = subprocess.run([str(ROOT / 'scripts/setup-project'), '--upgrade', '--apply', str(project)],
                                capture_output=True, text=True, timeout=BOUND * 6)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in installed:
            self.assertTrue(path.is_file(), result.stdout)


if __name__ == '__main__':
    unittest.main()
