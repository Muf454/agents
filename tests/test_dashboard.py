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


if __name__ == '__main__':
    unittest.main()
