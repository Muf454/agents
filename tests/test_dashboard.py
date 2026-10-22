"""Dashboard discovery, liveness and text sanitising (scripts/lib/dashboard.py, T006). Every test
sets AI_DASHBOARD_ROOT to its temp base, and AI_DASHBOARD_PROC to a fixture process tree unless
it needs a real process: the parallel gate and the host run real pipelines elsewhere."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'scripts/lib'
sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation  # noqa: E402,F401  (first: host state goes to a temp dir)
from timeouts import TIMEOUT_SCALE  # noqa: E402
BOUND = 5 * TIMEOUT_SCALE
COMMAND_TIMEOUT = 30 * TIMEOUT_SCALE
CLOCK_TICKS = os.sysconf('SC_CLK_TCK')
BTIME = 1_700_000_000


def load_dashboard():
    spec = importlib.util.spec_from_file_location('dashboard_view', LIB / 'dashboard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dash = load_dashboard()


class FakeProc:
    """A fixture process tree: `stat` with btime plus `<pid>/{stat,cmdline,cwd,environ}` entries."""

    def __init__(self, root):
        self.root = root
        root.mkdir()
        (root / 'stat').write_text(f'cpu 1 2 3 4\nbtime {BTIME}\nprocesses 9\n')

    def add(self, pid, args, cwd, started=None, state='S', stat=True, environ=None):
        entry = self.root / str(pid)
        entry.mkdir()
        started = time.time() - 60 if started is None else started
        ticks = int((started - BTIME) * CLOCK_TICKS)
        if stat:
            fields = ['0'] * 18 + [str(ticks), '0', '0']
            (entry / 'stat').write_text(f'{pid} (odd) name) {state} ' + ' '.join(fields) + '\n')
        (entry / 'cmdline').write_bytes(b'\0'.join(os.fsencode(arg) for arg in args) + b'\0')
        os.symlink(str(cwd), entry / 'cwd')
        if environ is not None:
            (entry / 'environ').write_bytes(b'\0'.join(os.fsencode(item) for item in environ) + b'\0')
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

    def spawn(self, name, checkout, env=None):
        """A real process named NAME (a symlink to a sleeping script) working in CHECKOUT, with
        ENV, else this environment without the dashboard ignore marker (discovery must see it)."""
        if env is None:
            env = {key: value for key, value in os.environ.items() if key != 'AI_DASHBOARD_IGNORE'}
        bin_dir = self.base / 'bin'
        bin_dir.mkdir(exist_ok=True)
        script = bin_dir / 'runner.sh'
        script.write_text('#!/usr/bin/env bash\nsleep 120\n:\n')  # argv is `bash <link>`, as for the real runners
        script.chmod(0o755)
        link = bin_dir / name
        link.unlink(missing_ok=True)
        link.symlink_to(script)
        process = subprocess.Popen([str(link)], cwd=checkout, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def test_dashboard_liveness_ignores_non_runner_processes(self):
        for args in (['vim', '/x/scripts/ai-run'], ['less', '.ai/bin/ai-pipeline'],
                     ['git', 'diff', 'scripts/ai-recover']):
            with self.subTest(args=args):
                checkout = self.checkout('c')
                self.proc.add(6000, args, checkout)
                self.assertEqual(dash.discover(), [])
                self.assertEqual(self.live(checkout), 'gone')
                shutil.rmtree(checkout)
                shutil.rmtree(self.proc.root / '6000')
        for args in (['bash', '/x/.ai/bin/ai-run', '--approved'], ['/x/.ai/bin/ai-pipeline']):
            with self.subTest(args=args):
                checkout = self.checkout('c')
                self.proc.add(6000, args, checkout)
                self.assertEqual([pid for pid, _ in dict(dash.discover())[str(checkout)]], [6000])
                self.assertEqual(self.live(checkout), 'alive')
                shutil.rmtree(checkout)
                shutil.rmtree(self.proc.root / '6000')

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
                                capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'{checkout} alive\n')
        self.assertEqual(listing(), before)
        self.assertFalse((lib / '__pycache__').exists())

    def test_dashboard_ignore_marked_runner_unless_registered(self):
        checkout = self.checkout('fixture')
        self.proc.add(4242, ['bash', '/opt/x/.ai/bin/ai-pipeline'], checkout,
                      environ=['HOME=/x', 'AI_DASHBOARD_IGNORE=1'])
        self.mark(checkout, 4242)
        self.assertEqual(dash.discover(), [])
        self.assertEqual(dash.snapshot()['runs'], [])
        self.register('fixture.json', checkout)
        self.assertEqual(dash.discover(), [(str(checkout), [])])
        run, = dash.snapshot()['runs']
        self.assertEqual((run['checkout'], run['liveness'], run['status']), (str(checkout), 'alive', 'running'))

    def test_dashboard_ignore_other_environments_are_discovered(self):
        oversized = ['AI_DASHBOARD_IGNORE=1', 'X=' + 'x' * dash.ENVIRON_LIMIT]
        cases = (('zero', ['AI_DASHBOARD_IGNORE=0']), ('prefixed', ['XAI_DASHBOARD_IGNORE=1']),
                 ('suffixed', ['AI_DASHBOARD_IGNORE=1 ']), ('missing', None),
                 ('unreadable', ['AI_DASHBOARD_IGNORE=1']), ('fifo', None),
                 ('directory', None), ('oversized', oversized))
        for pid, (case, environ) in enumerate(cases, 5000):
            with self.subTest(case=case):
                checkout = self.checkout(case)
                entry = self.proc.add(pid, ['bash', '/opt/x/.ai/bin/ai-run'], checkout, environ=environ)
                if case == 'unreadable':
                    (entry / 'environ').chmod(0)
                    if os.access(entry / 'environ', os.R_OK):
                        self.skipTest('running as root: mode 000 is still readable')
                elif case == 'fifo':
                    os.mkfifo(entry / 'environ')
                elif case == 'directory':
                    (entry / 'environ').mkdir()
                started = time.monotonic()
                self.assertEqual([found for found, _ in dict(dash.discover())[str(checkout)]], [pid])
                self.assertLess(time.monotonic() - started, BOUND)

    def test_dashboard_ignore_environ_reader(self):
        source = dash.ProcSource()
        self.proc.add(1, ['ai-run'], self.base, environ=['A=1', 'B=x=y'])
        self.assertEqual(source.environ(1), {b'A=1', b'B=x=y'})
        self.assertIsNone(source.environ(2))
        entry = self.proc.add(3, ['ai-run'], self.base)
        os.symlink(self.proc.root / '1/environ', entry / 'environ')
        self.assertIsNone(source.environ(3))
        exact = self.proc.add(4, ['ai-run'], self.base)
        (exact / 'environ').write_bytes(b'A=1\0' + b'x' * (dash.ENVIRON_LIMIT - 4))
        self.assertEqual(source.environ(4), {b'A=1', b'x' * (dash.ENVIRON_LIMIT - 4)})
        (exact / 'environ').write_bytes(b'A=1\0' + b'x' * (dash.ENVIRON_LIMIT - 3))
        self.assertIsNone(source.environ(4))

    def test_dashboard_ignore_real_processes(self):
        real = dash.ProcSource('/proc')
        if real.environ(os.getpid()) is None:
            self.skipTest('/proc/<pid>/environ is not readable here')
        hidden = self.checkout('hidden')
        shown = self.checkout('shown')
        environment = {key: value for key, value in os.environ.items() if key != 'AI_DASHBOARD_IGNORE'}
        ignored = self.spawn('ai-pipeline', hidden, dict(environment, AI_DASHBOARD_IGNORE='1'))
        listed = self.spawn('ai-pipeline', shown)
        for process in (ignored, listed):
            for _ in range(200):  # until the exec: environ is the parent's copy before it
                if (real.process(process.pid) or ((),))[0][1:2] == [os.fsencode(self.base / 'bin/ai-pipeline')]:
                    break
                time.sleep(0.01)
        self.assertIn(b'AI_DASHBOARD_IGNORE=1', real.environ(ignored.pid))
        found = dict(dash.discover(real))
        self.assertNotIn(str(hidden), found)
        self.assertEqual([pid for pid, _ in found[str(shown)]], [listed.pid])


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

    def inspect_run(self, checkout):
        return dash.inspect(str(checkout), [], time.time())

    def report(self, counts=((0, 1, 2),), head='abc1234def'):
        text = f'<!-- Host evidence: HEAD {head}; merge-base {head}; saved now. -->\n\n' if head else ''
        return text + ''.join(f'Finding counts: BLOCKER={b} MAJOR={m} MINOR={n}\n' for b, m, n in counts)

    def test_dashboard_pr_review_url_sources(self):
        url = 'https://github.com/o/r/pull/27'
        checkout = self.plant('pr')
        self.assertEqual(self.inspect_run(checkout)['pr'], '')
        (checkout / '.ai/run-log.md').write_text(
            f'- pull request ready: https://github.com/o/r/pull/3\n- pull request ready: {url}\n- other\n')
        self.assertEqual(self.inspect_run(checkout)['pr'], url)
        (checkout / '.ai/state.md').write_text(
            'Next action: Human: test and merge the pull request https://github.com/o/r/pull/99\n')
        self.assertEqual(self.inspect_run(checkout)['pr'], 'https://github.com/o/r/pull/99')
        (checkout / '.ai/state.md').write_text(
            f'Next action: merge \x1b[31m{url}\n')
        self.assertEqual(self.inspect_run(checkout)['pr'], url)
        self.assertNotIn('\x1b', json.dumps(self.inspect_run(checkout)))

    def test_dashboard_pr_review_counts_and_heads(self):
        checkout = self.plant('rev')
        reviews = checkout / '.ai/reviews'
        reviews.mkdir()
        (reviews / 'plan.md').write_text(
            f'<!-- Plan review of plan digest {"e" * 64}; HEAD 1234567890; saved now. -->\n\n'
            'Finding counts: BLOCKER=0 MAJOR=1 MINOR=2\n')
        (reviews / 'current.md').write_text(self.report(((3, 0, 4),)))
        run = self.inspect_run(checkout)
        self.assertEqual(run['reviews']['plan'], {'blocker': 0, 'major': 1, 'minor': 2, 'head': '1234567'})
        self.assertEqual(run['reviews']['code'], {'blocker': 3, 'major': 0, 'minor': 4, 'head': 'abc1234'})
        (reviews / 'plan.md').write_text(self.report(((0, 1, 2), (1, 1, 1))))
        (reviews / 'current.md').write_text('no counts here\n')
        run = self.inspect_run(checkout)
        self.assertEqual(run['reviews'], {'plan': None, 'code': None})
        self.assertEqual(run['branch'], 'main')
        self.assertEqual(run['tasks']['total'], 3)
        (reviews / 'plan.md').write_text(self.report(head=''))
        self.assertEqual(self.inspect_run(checkout)['reviews']['plan'],
                         {'blocker': 0, 'major': 1, 'minor': 2, 'head': ''})

    def test_dashboard_pr_review_oversized_count(self):
        checkout = self.plant('huge')
        (checkout / '.ai/reviews').mkdir()
        (checkout / '.ai/reviews/plan.md').write_text(self.report(((0, 1, 2),)))
        (checkout / '.ai/reviews/current.md').write_text(
            f'Finding counts: BLOCKER={"9" * 5000} MAJOR=0 MINOR=0\n')
        self.plant('other', 'build')
        for run in (dash.inspect(str(checkout), [], time.time()),
                    next(run for run in dash.snapshot(all_runs=True)['runs'] if run['project'] == 'huge')):
            self.assertIsNone(run['reviews']['code'])
            self.assertEqual(run['reviews']['plan'], {'blocker': 0, 'major': 1, 'minor': 2, 'head': 'abc1234'})
        runs = self.runs('--all')
        self.assertIsNone(runs['huge']['reviews']['code'])
        self.assertEqual(runs['huge']['reviews']['plan']['minor'], 2)
        self.assertEqual(runs['other']['branch'], 'main')

    def test_dashboard_pr_review_unsafe_entries(self):
        fifo = self.plant('fifo')
        os.mkfifo(fifo / '.ai/reviews')
        start = time.time()
        run = self.inspect_run(fifo)
        self.assertLess(time.time() - start, BOUND)
        self.assertEqual(run['reviews'], {'plan': None, 'code': None})
        self.assertEqual(run['branch'], 'main')
        link = self.plant('link')
        real = self.base / 'elsewhere'
        real.mkdir()
        (real / 'plan.md').write_text(self.report())
        os.symlink(real, link / '.ai/reviews')
        self.assertEqual(self.inspect_run(link)['reviews'], {'plan': None, 'code': None})
        files = self.plant('files')
        (files / '.ai/reviews').mkdir()
        os.mkfifo(files / '.ai/reviews/plan.md')
        os.symlink(real / 'plan.md', files / '.ai/reviews/current.md')
        self.assertEqual(self.inspect_run(files)['reviews'], {'plan': None, 'code': None})

    def test_dashboard_pr_review_json_every_run(self):
        self.plant('good', 'build')
        (self.base / 'bad').mkdir()
        self.register('bad.json', self.base / 'bad')
        runs = self.runs()
        self.assertTrue(runs)
        for run in runs.values():
            self.assertEqual(run['pr'], '')
            self.assertEqual(run['reviews'], {'plan': None, 'code': None})

    # --wait (T009)

    def wait_cli(self, *options, expected=0):
        result = self.run_cli('--wait', '--interval', '0.1', *options, expected=expected)
        return json.loads(result.stdout)

    def start_wait(self, *options):
        process = subprocess.Popen([sys.executable, '-B', str(LIB / 'dashboard.py'), '--wait', '--interval', '0.1',
                                    '--timeout', str(20 * TIMEOUT_SCALE), *options], cwd=self.base,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(process.kill)
        self.addCleanup(process.communicate)
        time.sleep(1 * TIMEOUT_SCALE)
        self.assertIsNone(process.poll())
        return process

    def finish_wait(self, process, expected=0):
        out, err = process.communicate(timeout=BOUND * 3)
        self.assertEqual(process.returncode, expected, out + err)
        return json.loads(out)

    def observe(self, checkout, stage):
        path = checkout / '.ai/local/observation.json'
        record = json.loads(path.read_text())
        record['stage'] = stage
        path.write_text(json.dumps(record))

    def notify(self, checkout, message, ts='2026-10-09T10:00:00Z'):
        with open(checkout / '.ai/local/notifications.log', 'a') as log:
            log.write(json.dumps({'ts': ts, 'message': message}) + '\n')

    def test_dashboard_wait_stage_change_reports_only_that_run(self):
        first = self.plant('one', 'build')
        self.plant('two', 'build')
        process = self.start_wait()
        self.observe(first, 'checks')
        data = self.finish_wait(process)
        self.assertEqual([run['project'] for run in data['runs']], ['one'])
        self.assertEqual(data['runs'][0]['stage'], 'checks')
        self.assertFalse(data['timed_out'])
        self.assertTrue(data['cursor'])
        self.assertNotIn('notifications_mark', data['runs'][0])

    def test_dashboard_wait_notification_changes_but_tasks_edit_does_not(self):
        checkout = self.plant('one', 'build')
        process = self.start_wait()
        self.notify(checkout, 'hello')
        self.assertEqual([run['project'] for run in self.finish_wait(process)['runs']], ['one'])
        process = subprocess.Popen([sys.executable, '-B', str(LIB / 'dashboard.py'), '--wait', '--interval', '0.1',
                                    '--timeout', '2'], cwd=self.base, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.addCleanup(process.kill)
        self.addCleanup(process.communicate)
        time.sleep(0.5 * TIMEOUT_SCALE)
        (checkout / '.ai/tasks.md').write_text('# Tasks\n\n## T001 — x\nStatus: DONE\n')
        data = self.finish_wait(process, expected=1)
        self.assertTrue(data['timed_out'])
        self.assertEqual(data['runs'], [])

    def test_dashboard_wait_lookalike_notifications_change(self):
        checkout = self.plant('one', 'build')
        long = 'x' * 400
        self.notify(checkout, long + 'a')
        before = self.inspect_run(checkout)
        first = self.wait_cli('--timeout', '0.3', expected=1)['cursor']
        self.notify(checkout, long + 'b')
        after = self.inspect_run(checkout)
        self.assertEqual(before['events'][-1], after['events'][-1])
        self.assertNotEqual(before['notifications_mark'], after['notifications_mark'])
        data = self.wait_cli('--since', first, '--timeout', '5')
        self.assertEqual([run['project'] for run in data['runs']], ['one'])
        # the same line again, same second: identical bytes still change the mark
        mid = self.wait_cli('--timeout', '0.3', expected=1)['cursor']
        self.notify(checkout, long + 'b')
        again = self.inspect_run(checkout)
        self.assertEqual(after['events'][-1], again['events'][-1])
        self.assertNotEqual(after['notifications_mark'], again['notifications_mark'])
        self.assertEqual(len(self.wait_cli('--since', mid, '--timeout', '5')['runs']), 1)
        self.assertNotIn('notifications_mark', next(iter(self.runs().values())))

    def test_dashboard_wait_since_cursor(self):
        checkout = self.plant('one', 'build')
        cursor = self.wait_cli('--timeout', '0.3', expected=1)['cursor']
        data = self.wait_cli('--since', cursor, '--timeout', '0.3', expected=1)
        self.assertTrue(data['timed_out'])
        self.observe(checkout, 'review')
        data = self.wait_cli('--since', cursor, '--timeout', '5')
        self.assertEqual(data['runs'][0]['stage'], 'review')

    def test_dashboard_wait_new_checkout_reported_removed_not(self):
        self.plant('one', 'build')
        self.plant('two', 'build')
        cursor = self.wait_cli('--timeout', '0.3', expected=1)['cursor']
        self.plant('three', 'build')
        data = self.wait_cli('--since', cursor, '--timeout', '5')
        self.assertEqual([run['project'] for run in data['runs']], ['three'])
        cursor = data['cursor']
        (self.state / 'pipelines' / 'two.json').unlink()
        data = self.wait_cli('--since', cursor, '--timeout', '0.5', expected=1)
        self.assertTrue(data['timed_out'])

    def test_dashboard_wait_usage_errors(self):
        for options in (('--wait', '--since', 'garbage'), ('--since', 'abc'), ('--wait', '--once'),
                        ('--wait', '--timeout', '0'), ('--timeout', '5'), ('--interval', '1'),
                        ('--wait', '--interval', '0.01')):
            self.run_cli(*options, expected=2)

    def test_dashboard_wait_reports_a_hidden_old_run(self):
        checkout = self.plant('old', 'pr', 'done', age=3 * 86400)
        self.assertEqual(self.runs(), {})
        process = self.start_wait()
        self.observe(checkout, 'review')
        self.assertEqual([run['project'] for run in self.finish_wait(process)['runs']], ['old'])

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

    def test_observation_writer_plan_dashboard_snapshot(self):
        self.plant('planning', 'planning', detail='opus · first plan')
        runs = self.runs()
        self.assertIn('planning', runs)
        self.assertEqual(runs['planning']['stage'], 'planning')

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
        self.assertEqual(result.stdout.count('✓'), 5)  # the five boxes before Checks, healthy run only
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


def fake_run(stage='build', state='active', status='running', detail='T003 · sonnet · 12m', note='',
             tasks=(2, 7), last_error='', observed=True, events=None, pr='', reviews=None):
    """A snapshot run dict, as `inspect` would return it."""
    if events is None:
        events = [{'ts': '2026-10-09T10:00:00Z', 'message': '🔁 Round 2'}]
    observation = {'stage': stage, 'state': state, 'detail': detail, 'note': note, 'since': ''}
    return {'project': 'demo', 'checkout': '/x/demo', 'branch': 'feature/x', 'liveness': 'alive',
            'observation': observation if observed else None, 'events': events, 'last_error': last_error,
            'tasks': {'done': tasks[0], 'total': tasks[1], 'current': ''} if tasks else None,
            'pr': pr, 'reviews': reviews or {'plan': None, 'code': None},
            'status': status, 'stage': stage if observed else 'unknown', 'since': '', 'updated': 0.0}


def plain(lines):
    return [''.join(text for text, _style in line).rstrip() for line in lines]


def styles(lines):
    """[(text, style)] of every segment of every line."""
    return [segment for line in lines for segment in line]


HEADER = 'AI pipelines  1 running · 0 needs you · 0 finished  00:00  ↑↓ ⏎ a r q'
WIDE_BOXES = [
    '  ┌──────┐ ┌────────────┐ ┌───────────────┐ ┌───────┐ ╔═══════════╗ ┌────────┐ ┌────────┐ ┌────────┐ ┌────┐',
    '  │ Plan │─│ Plan check │─│ Plan revision │─│ Setup │─║ Build 3/7 ║─│ Checks │─│ Review │─│ Triage │─│ PR │',
    '  └──────┘ └────────────┘ └───────────────┘ └───────┘ ╚═══════════╝ └────────┘ └────────┘ └────────┘ └────┘',
]
WIDE_MARKS = '    ✓' + ' ' * 8 + '✓' + ' ' * 14 + '✓' + ' ' * 17 + '✓' + ' ' * 7 + 'T003 · sonnet · 12m'
WRITER_STAGES = {'start': None, 'plan review': 'plan_review', 'plan revision': 'plan_revision',
                 'implementation': 'build', 'validation': 'checks', 'review': 'review',
                 'triage': 'triage', 're-check': 'recheck', 'pull request preparation': 'pr',
                 'push': 'pr', 'pull request': 'pr', 'final push': 'pr'}


class RenderTest(DashboardTest):
    """The shared renderer and the curses view (T008)."""

    def setUp(self):
        super().setUp()
        zone = mock.patch.dict(os.environ, {'TZ': 'UTC'})
        zone.start()
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(zone.stop)

    def view(self, run, width=140, **options):
        return render_lines(run, width, **options)

    def run_cli(self, *options):
        result = subprocess.run([sys.executable, '-B', str(LIB / 'dashboard.py'), *options], cwd=self.base,
                                capture_output=True, text=True, timeout=BOUND * 3)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def observe(self, checkout, *arguments):
        result = subprocess.run([sys.executable, '-B', str(LIB / 'workflow.py'), 'observe', *arguments],
                                env={**os.environ, 'AI_ROOT': str(checkout)}, capture_output=True,
                                text=True, timeout=BOUND * 3, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')

    def test_dashboard_render_golden_widths(self):
        wide = plain(self.view(fake_run()))
        self.assertEqual(wide, [HEADER, '', '  demo · feature/x · running · 2/7 tasks', *WIDE_BOXES,
                                WIDE_MARKS, '  10:00 🔁 Round 2'])
        self.assertEqual(plain(self.view(fake_run(), 120)), wide)
        compact = ['  ✓Plan ✓PlanCheck ✓Revise ✓Setup ▶Build 3/7 ·Checks ·Review ·Triage ·PR', '  10:00 🔁 Round 2']
        self.assertEqual(plain(self.view(fake_run(), 119))[2:], ['  demo · feature/x · running · 2/7 tasks',
                                                                *compact])
        narrow = plain(self.view(fake_run(), 60))
        self.assertEqual(narrow[3], '  ✓Plan ✓PlanCheck ✓Revise ✓Setup ▶Build 3/7 ·Checks ·Revie…')
        self.assertTrue(all(dash.cols(line) <= 60 for line in narrow))

    def test_dashboard_render_styles_of_the_active_box(self):
        segments = styles(self.view(fake_run()))
        self.assertIn(('║ Build 3/7 ║', 'active_claude'), segments)
        self.assertIn(('│ Plan check │', 'done'), segments)
        self.assertIn(('│ Checks │', 'pending'), segments)

    def test_dashboard_render_worst_case_row_is_not_truncated(self):
        lines = plain(self.view(fake_run('plan_revision', 'paused', 'paused', note='limit'), 120))
        for line in lines[3:6]:
            self.assertNotIn('…', line)
        self.assertIn('║ Plan revision ⏸ ║', lines[4])
        self.assertLessEqual(max(dash.cols(line) for line in lines), 120)
        longest = ['Plan', 'Plan check', 'Plan revision ⏸', 'Setup', 'Build 99/99', 'Checks', 'Review', 'Re-check',
                   'PR']
        self.assertLessEqual(sum(dash.cols(label) + 4 for label in longest) + 8 + 2, 120)
        lines = plain(self.view(fake_run('build', tasks=(99, 120)), 120))
        self.assertIn('Build 100/…', lines[4])

    def test_dashboard_render_stopped_review_and_finished(self):
        stopped = self.view(fake_run('review', 'stopped', 'needs_you', note='2 blockers'))
        self.assertIn(('║ Review ║', 'stopped'), styles(stopped))
        self.assertIn('⛔ 2 blockers', plain(stopped)[6])
        self.assertFalse([s for s in styles(stopped) if s[1].startswith('active_')])
        done = plain(self.view(fake_run('pr', 'done', 'finished', note='PR open')))
        self.assertEqual(done[6].count('✓'), 9)
        self.assertEqual(done[7], '  🏁 PR open')

    def test_dashboard_render_plan_revision_stored_decision_extra_round_format_retry(self):
        running = self.view(fake_run('plan_revision', detail='1/3 · round 2'))
        self.assertIn(('║ Plan revision ║', 'active_claude'), styles(running))
        self.assertTrue(plain(running)[6].rstrip().endswith('1/3 · round 2'))
        decision = self.view(fake_run('plan_revision', 'stopped', 'needs_you', note='Which database?'))
        self.assertIn(('║ Plan revision ║', 'stopped'), styles(decision))
        self.assertIn('⛔ Which database?', plain(decision)[6])
        extra = plain(self.view(fake_run('triage', detail='round 3 · extra (5 → 3 → 1)')))[6]
        self.assertEqual(extra.index('round 3'), 86)  # the Triage box column; Build is short here
        retry = plain(self.view(fake_run('review', detail='format retry')))[6]
        self.assertEqual(retry.index('format retry'), 75)

    def test_dashboard_render_recheck_is_the_triage_box(self):
        lines = self.view(fake_run('recheck'))
        self.assertIn(('║ Re-check ║', 'active_codex'), styles(lines))
        self.assertNotIn('Triage', plain(lines)[4])

    def test_dashboard_render_stop_at_start_highlights_no_box(self):
        lines = self.view(fake_run('none', 'stopped', 'needs_you', note='base moved', detail=''))
        self.assertEqual([s for s in styles(lines) if s[1] in ('stopped', 'done') and '│' in s[0]],
                         [('│ Plan │', 'done')])  # the pipeline got past planning
        self.assertNotIn('╔', ''.join(plain(lines)))
        self.assertEqual(plain(lines)[6], '    ✓ ⛔ stopped before Plan check · base moved')

    def test_dashboard_render_needs_you_with_active_record_and_last_error(self):
        run = fake_run('build', 'active', 'needs_you', last_error='gate broken', detail='T003')
        lines = self.view(run)
        self.assertIn(('║ Build 3/7 ║', 'stopped'), styles(lines))
        self.assertFalse([s for s in styles(lines) if s[1].startswith('active_')])
        self.assertTrue(plain(lines)[6].endswith('⛔ gate broken'))
        checkout = self.checkout('broken')
        (checkout / '.ai/local/observation.json').write_text(json.dumps(
            {'stage': 'build', 'state': 'active', 'detail': 'T003', 'note': '', 'since': ''}))
        self.register('broken.json', checkout)
        error = checkout / '.ai/local/last-error'
        error.write_text('gate broken\nmore\n')
        future = time.time() + 5
        os.utime(error, (future, future))
        output = self.run_cli('--once').stdout
        self.assertIn('⛔ gate broken', output)
        self.assertIn('║ Build ║', output)

    def test_dashboard_render_writer_to_renderer_stops_and_overlays(self):
        for label, stage in WRITER_STAGES.items():
            with self.subTest(label=label):
                checkout = self.checkout('stop-' + label.replace(' ', '-'))
                if stage:
                    self.observe(checkout, 'step', stage)
                self.observe(checkout, 'stop', label, 'because')
                run = dash.inspect(str(checkout), [], time.time())
                texts = [text for text, style in styles(self.view(run)) if style == 'stopped']
                if stage is None:
                    self.assertIn('⛔ stopped before Plan check · because', texts)
                else:
                    box = 'Re-check' if stage == 'recheck' else dict((k, v) for k, v, *_ in dash.FLOW)[stage]
                    self.assertTrue(any(f' {box} ' in text for text in texts), texts)
                    self.assertIn('⛔ because', texts)
        cases = {'build': ('active_claude', '⏸', 'pause'), 'review': ('active_codex', '⏸', 'pause'),
                 'plan_revision': ('active_claude', '⏸', 'pause'),
                 'checks': ('active_script', '🔧', 'recovering')}
        for stage, (style, overlay, action) in cases.items():
            with self.subTest(stage=stage, action=action):
                checkout = self.checkout('overlay-' + stage + action)
                self.observe(checkout, 'step', stage)
                self.observe(checkout, action, 'note')
                run = dash.inspect(str(checkout), [(1, '1')], time.time())
                segments = styles(self.view(run))
                self.assertTrue(any(s == style and overlay in t for t, s in segments), segments)

    def test_dashboard_render_legacy_and_malformed_show_no_active_box(self):
        lines = self.view(fake_run(observed=False, tasks=None))
        self.assertEqual(plain(lines)[6], '  stage unknown (older toolkit)')
        self.assertFalse([s for s in styles(lines) if s[1].startswith('active_') or s[1] == 'done'])
        self.assertNotIn('╔', ''.join(plain(lines)))
        checkout = self.checkout('bad')
        (checkout / '.ai/local/observation.json').write_text('{"stage": "bogus", "state": "active"}')
        self.register('bad.json', checkout)
        self.proc.add(7000, ['bash', '/x/.ai/bin/ai-run'], checkout)
        output = self.run_cli('--once').stdout
        self.assertIn('stage unknown', output)
        self.assertNotIn('╔', output)
        self.assertIn('bad · unknown · running', output)

    def test_dashboard_render_legacy_checkout_with_last_error(self):
        for name, content in (('legacy', None), ('malformed', '{"stage": "bogus", "state": "active"}')):
            checkout = self.checkout(name)
            if content is not None:
                (checkout / '.ai/local/observation.json').write_text(content)
            self.register(name + '.json', checkout)
            error = checkout / '.ai/local/last-error'
            error.write_text('gate broken\n')
            future = time.time() + 5
            os.utime(error, (future, future))
        data = json.loads(self.run_cli('--json').stdout)
        self.assertEqual({run['project']: run['status'] for run in data['runs']},
                         {'legacy': 'needs_you', 'malformed': 'needs_you'})
        saved = os.environ.get('COLUMNS')
        try:
            for width in ('140', '80'):
                os.environ['COLUMNS'] = width
                output = self.run_cli('--once').stdout
                with self.subTest(width=width):
                    self.assertIn('older toolkit', output)
                    self.assertIn('gate broken', output)
                    self.assertNotIn('before Plan check', output)
        finally:
            if saved is None:
                os.environ.pop('COLUMNS', None)
            else:
                os.environ['COLUMNS'] = saved

    def test_dashboard_render_overlays_and_line_widths(self):
        runs = [fake_run(), fake_run('plan_revision', 'paused', 'paused', note='x' * 300),
                fake_run('review', 'recovering', 'recovering'), fake_run('pr', 'active', 'crashed'),
                fake_run('recheck', 'stopped', 'needs_you', note='y' * 300),
                fake_run('none', 'stopped', 'needs_you', note='z' * 300), fake_run('pr', 'done', 'finished'),
                fake_run(observed=False), fake_run(detail='d' * 400, tasks=(99, 120))]
        for width in range(40, 201):
            for run in runs:
                for line in plain(render_lines(run, width, expanded=frozenset({'/x/demo'}))):
                    self.assertLessEqual(dash.cols(line), width, (width, line))
        crashed = plain(self.view(runs[3], 119))
        self.assertIn('▶PR ⚠', crashed[3])
        paused = plain(self.view(runs[1], 119))
        self.assertIn('▶Revise ⏸', paused[3])
        stopped = plain(self.view(runs[4], 80))
        self.assertIn('✗Re-check', stopped[3])

    def planned_checkout(self, name, *steps, age=0):
        """A registered checkout whose observation is written by `workflow.py observe`."""
        checkout = self.checkout(name)
        self.register(name + '.json', checkout)
        for step in steps:
            self.observe(checkout, *step)
        if age:
            then = time.time() - age
            for path in checkout.rglob('*'):
                if path.is_file():
                    os.utime(path, (then, then))
        return checkout

    def json_runs(self, *options):
        data = json.loads(self.run_cli('--json', *options).stdout)
        return {run['project']: run for run in data['runs']}

    def test_dashboard_plan_running_session_golden_widths(self):
        planning = fake_run('planning', detail='opus · first plan', tasks=None)
        wide = plain(self.view(planning))
        self.assertEqual(wide[3:], [
            '  ╔══════╗ ┌────────────┐ ┌───────────────┐ ┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────┐',
            '  ║ Plan ║─│ Plan check │─│ Plan revision │─│ Setup │─│ Build │─│ Checks │─│ Review │─│ Triage │─│ PR │',
            '  ╚══════╝ └────────────┘ └───────────────┘ └───────┘ └───────┘ └────────┘ └────────┘ └────────┘ └────┘',
            '  opus · first plan', '  10:00 🔁 Round 2'])
        self.assertNotIn('✓', ''.join(wide))
        self.assertIn(('║ Plan ║', 'active_claude'), styles(self.view(planning)))
        self.assertEqual(plain(self.view(planning, 120)), wide)
        self.assertEqual(plain(self.view(planning, 119))[3:], [
            '  ▶Plan ·PlanCheck ·Revise ·Setup ·Build ·Checks ·Review ·Triage ·PR', '  10:00 🔁 Round 2'])
        narrow = plain(self.view(planning, 60))
        self.assertEqual(narrow[3], '  ▶Plan ·PlanCheck ·Revise ·Setup ·Build ·Checks ·Review ·T…')
        self.assertTrue(all(dash.cols(line) <= 60 for line in narrow))

    def test_dashboard_plan_running_build_ticks_plan(self):
        wide = plain(self.view(fake_run()))
        self.assertEqual(wide[3:6], WIDE_BOXES)
        self.assertEqual(wide[6], WIDE_MARKS)
        self.assertEqual(wide[6].index('✓'), 4)  # under the Plan box

    def test_dashboard_plan_nine_boxes_fit_120_without_truncation(self):
        runs = [fake_run('plan_revision', 'paused', 'paused', note='limit', tasks=(98, 99)),
                fake_run('recheck', tasks=(98, 99)), fake_run('planning', detail='opus · first plan'),
                fake_run('planning', 'done', 'planned', note='7 tasks'),
                fake_run('planning', 'stopped', 'needs_you', note='Task queue is invalid: x' * 20),
                fake_run('none', 'active'), fake_run('none', 'stopped', 'needs_you', note='z' * 300)]
        for number, run in enumerate(runs):
            lines = plain(self.view(run, 120))
            with self.subTest(run=number):
                for line in lines[3:6]:
                    self.assertNotIn('…', line)
                self.assertEqual(lines[4].count('│') + lines[4].count('║'), 18)
            for width in range(40, 201):
                for line in plain(render_lines(run, width, expanded=frozenset({'/x/demo'}))):
                    self.assertLessEqual(dash.cols(line), width, (width, line))
        build = plain(self.view(fake_run('build', tasks=(98, 99)), 120))
        self.assertIn('Build 99/99', build[4])
        recheck = plain(self.view(runs[1], 120))
        self.assertIn('Re-check', recheck[4])
        self.assertEqual(dash.BOX_OF['recheck'], dash.BOX_OF['triage'])

    def test_dashboard_plan_planned_status(self):
        planned = self.planned_checkout('planned', ('planned', '7 tasks'))
        running = self.planned_checkout('running', ('step', 'build'))
        self.proc.add(6001, ['bash', '/x/.ai/bin/ai-pipeline'], running)
        self.mark(running, 6001)
        self.planned_checkout('finished', ('done', 'PR open'))
        runs = self.json_runs()
        self.assertEqual((runs['planned']['status'], runs['planned']['stage']), ('planned', 'planning'))
        self.assertEqual(runs['planned']['observation']['note'], '7 tasks')
        self.assertEqual(list(runs), ['running', 'planned', 'finished'])
        lines = plain(self.view(dash.inspect(str(planned), [], time.time())))
        self.assertEqual(lines[6][:5], '    ✓')
        self.assertNotIn('╔', ''.join(lines))
        self.assertTrue(lines[6].endswith('📝 7 tasks'))
        self.assertEqual(lines[6].index('📝'), 11)  # under the Plan check box
        self.assertIn('planned', lines[2])
        compact = plain(self.view(dash.inspect(str(planned), [], time.time()), 100))
        self.assertTrue(compact[3].startswith('  ✓Plan ·PlanCheck ·Revise'))
        self.assertNotIn('▶', compact[3])
        self.assertEqual(len(compact), 5)

    def test_dashboard_plan_planned_hidden_after_a_day(self):
        self.planned_checkout('old', ('planned', '3 tasks'), age=25 * 3600)
        self.planned_checkout('new', ('planned', '3 tasks'))
        self.assertEqual(sorted(self.json_runs()), ['new'])
        self.assertEqual(sorted(self.json_runs('--all')), ['new', 'old'])

    def test_dashboard_plan_stopped_planning_needs_you(self):
        stopped = self.planned_checkout('stopped', ('step', 'planning', 'opus · first plan'),
                                        ('stop', 'plan', 'Task queue is invalid: T002 has no Goal'))
        runs = self.json_runs()
        self.assertEqual((runs['stopped']['status'], runs['stopped']['stage']), ('needs_you', 'planning'))
        run = dash.inspect(str(stopped), [], time.time())
        self.assertIn(('║ Plan ║', 'stopped'), styles(self.view(run)))
        self.assertIn('⛔ Task queue is invalid: T002 has no Goal', plain(self.view(run))[6])
        compact = plain(self.view(run, 100))
        self.assertTrue(compact[3].startswith('  ✗Plan ·PlanCheck'))

    def test_dashboard_plan_pipeline_start_record_ticks_plan(self):
        checkout = self.planned_checkout('started', ('start',))
        self.proc.add(6002, ['bash', '/x/.ai/bin/ai-pipeline'], checkout)
        self.mark(checkout, 6002)
        run = dash.inspect(str(checkout), dash.discover(dash.ProcSource())[0][1], time.time())
        self.assertEqual((run['status'], run['stage']), ('running', 'none'))
        segments = styles(self.view(run))
        self.assertIn(('│ Plan │', 'done'), segments)
        self.assertFalse([s for s in segments if s[1].startswith('active_') or s[1] == 'stopped'])
        self.assertNotIn('╔', ''.join(plain(self.view(run))))
        stopped = self.planned_checkout('start-stop', ('start',), ('stop', 'start', 'base moved'))
        run = dash.inspect(str(stopped), [], time.time())
        self.assertIn(('│ Plan │', 'done'), styles(self.view(run)))
        self.assertEqual(plain(self.view(run))[6], '    ✓ ⛔ stopped before Plan check · base moved')

    def test_dashboard_plan_old_records_and_legacy(self):
        checkout = self.checkout('old')
        (checkout / '.ai/local/observation.json').write_text(json.dumps(
            {'stage': 'build', 'state': 'active', 'detail': 'T003', 'note': '', 'since': ''}))
        run = dash.inspect(str(checkout), [(1, '1')], time.time())
        self.assertIn(('│ Plan │', 'done'), styles(self.view(run)))
        legacy = plain(self.view(fake_run(observed=False, tasks=None)))
        segments = styles(self.view(fake_run(observed=False, tasks=None)))
        self.assertEqual(legacy[6], '  stage unknown (older toolkit)')
        self.assertIn(('│ Plan │', 'pending'), segments)
        self.assertFalse([s for s in segments if s[1] in ('stopped', 'done')])

    def test_dashboard_plan_live_ai_run_plan_is_running_on_plan(self):
        checkout = self.planned_checkout('live', ('step', 'planning', 'opus · first plan'))
        self.proc.add(6003, ['bash', '/x/.ai/bin/ai-run', '--plan', 'p.md'], checkout)
        runs = self.json_runs()
        self.assertEqual((runs['live']['status'], runs['live']['stage']), ('running', 'planning'))
        self.assertIn('║ Plan ║', self.run_cli('--once').stdout)

    RELAUNCH = ('relaunch', '1700000000', 'Claude limit · relaunch after Sat 09:05')

    def test_dashboard_limit_relaunch_gone_run_is_paused_with_note(self):
        checkout = self.planned_checkout('waiting', ('step', 'build', 'T003'), self.RELAUNCH)
        run = self.json_runs()['waiting']
        self.assertEqual((run['status'], run['stage']), ('paused', 'build'))
        view = self.run_cli('--once').stdout
        self.assertIn('⏸', view)
        self.assertIn('Claude limit · relaunch after Sat 09:05', view)
        self.assertEqual(run['observation']['relaunch_at'], 1700000000)
        self.assertTrue(checkout.exists())

    def test_dashboard_limit_relaunch_newer_error_wins(self):
        checkout = self.planned_checkout('errored', ('step', 'build', 'T003'), self.RELAUNCH)
        error = checkout / '.ai/local/last-error'
        error.write_text('relaunch refused: tree changed\n')
        future = time.time() + 60
        os.utime(error, (future, future))
        run = self.json_runs()['errored']
        self.assertEqual(run['status'], 'needs_you')
        self.assertEqual(run['last_error'], 'relaunch refused: tree changed')

    def test_dashboard_limit_relaunch_in_process_pause_without_schedule_stays_idle(self):
        self.planned_checkout('inproc', ('step', 'build', 'T003'), ('pause', 'Claude until Sat 09:05'))
        self.assertEqual(self.json_runs()['inproc']['status'], 'idle')

    def test_dashboard_plan_killed_in_pause_needs_you(self):
        self.planned_checkout('pplan', ('step', 'planning', 'opus · first plan'),
                              ('pause', 'Claude until Sat 09:05'))
        run = self.json_runs()['pplan']
        self.assertEqual(run['status'], 'needs_you')
        self.assertIn('planning session ended without a plan', run['last_error'])

    def test_dashboard_plan_killed_session_shows_stop_on_plan_box(self):
        self.planned_checkout('killed', ('step', 'planning', 'opus · first plan'))
        run = self.json_runs()['killed']
        self.assertEqual((run['status'], run['stage']), ('needs_you', 'planning'))
        self.assertIn('planning session ended without a plan', run['last_error'])
        lines = self.view(run)
        self.assertIn(('║ Plan ║', 'stopped'), styles(lines))
        self.assertTrue(any('⛔' in line and 'planning session ended without a plan' in line
                            for line in plain(lines)))
        self.assertTrue(plain(self.view(run, 119))[3].startswith('  ✗Plan ·PlanCheck'))

    def test_dashboard_plan_killed_and_relaunch_runs_fit_every_width(self):
        self.planned_checkout('waiting', ('step', 'build', 'T003'), self.RELAUNCH)
        self.planned_checkout('killed', ('step', 'planning', 'opus · first plan'))
        for name, run in self.json_runs().items():
            for width in range(40, 201):
                for line in plain(render_lines(run, width, expanded=frozenset({run['checkout']}))):
                    self.assertLessEqual(dash.cols(line), width, (name, width, line))
            self.assertNotIn('…', ''.join(plain(self.view(run, 120))[3:6]))

    def test_dashboard_plan_recheck_stays_in_the_triage_box(self):
        lines = self.view(fake_run('recheck'))
        self.assertIn(('║ Re-check ║', 'active_codex'), styles(lines))
        self.assertNotIn('Triage', plain(lines)[4])
        self.assertEqual(plain(lines)[4].index('Re-check'), 88)

    def test_dashboard_render_empty_state_and_expanded_events(self):
        empty = plain(dash.render([], 140, now=0, state_root='/some/root'))
        self.assertIn('No pipelines found (state root /some/root)', empty[2])
        self.assertIn('.ai/bin/ai-pipeline --approved', empty[2])
        events = [{'ts': '2026-10-09T10:00:00Z', 'message': f'm{n}'} for n in range(12)]
        lines = plain(self.view(fake_run(events=events), expanded=frozenset({'/x/demo'})))
        shown = [line for line in lines if line.startswith('  10:00 m')]
        self.assertEqual([line[8:] for line in shown], ['m11'] + [f'm{n}' for n in range(4, 12)])
        self.assertIn('  path: /x/demo', lines)

    def test_dashboard_pr_review_expanded_lines(self):
        expanded = frozenset({'/x/demo'})
        lines = plain(self.view(fake_run(), expanded=expanded))
        self.assertNotIn('  pr:', ' '.join(line[:5] for line in lines))
        self.assertIn('  reviews: none yet', lines)
        reviews = {'plan': {'blocker': 0, 'major': 1, 'minor': 2, 'head': 'abc1234'},
                   'code': {'blocker': 3, 'major': 0, 'minor': 0, 'head': ''}}
        lines = plain(self.view(fake_run(pr='https://github.com/o/r/pull/27', reviews=reviews),
                                expanded=expanded))
        self.assertIn('  pr: https://github.com/o/r/pull/27', lines)
        self.assertIn('  reviews: plan B0 M1 m2 @abc1234 · code B3 M0 m0', lines)
        reviews['plan'] = None
        lines = plain(self.view(fake_run(reviews=reviews), expanded=expanded))
        self.assertIn('  reviews: code B3 M0 m0', lines)

    def pty_run(self, argv, rows=30, columns=140):
        """Start ARGV on a pty of the given size; returns (pid, master fd)."""
        pid, fd = pty.fork()
        if pid == 0:
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
                os.execvpe(argv[0], argv, {**os.environ, 'TERM': 'xterm-256color', 'LC_ALL': 'C.UTF-8'})
            finally:
                os._exit(127)
        self.addCleanup(self.reap, pid, fd)
        return pid, fd

    def reap(self, pid, fd):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass

    def read_until(self, fd, seen, text=None, limit=15):
        """Append pty output to SEEN until TEXT shows in it (or EOF); fails after LIMIT seconds."""
        deadline = time.monotonic() + limit * TIMEOUT_SCALE
        while text is None or text not in seen[0].decode('utf-8', 'replace'):
            if time.monotonic() > deadline:
                self.fail(f'timed out waiting for {text!r}; saw {seen[0][-600:]!r}')
            if not select.select([fd], [], [], 0.2)[0]:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            seen[0] += chunk

    def finish(self, pid, fd, seen):
        self.read_until(fd, seen)
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status)

    def fixture_runs(self, count=10):
        for n in range(count):
            # The last run has a name no other shares a character with: curses redraws only
            # the characters that changed, so a similar name would never show whole.
            name = 'qxzjwvkp' if n == count - 1 and count > 5 else f'run{n:02d}'
            checkout = self.checkout(name)
            state = 'stopped' if n == 0 else 'done' if n == 1 else 'active'
            (checkout / '.ai/local/observation.json').write_text(json.dumps(
                {'stage': 'pr' if n == 1 else 'build', 'state': state, 'detail': '', 'note': 'why',
                 'since': ''}))
            then = time.time() - n
            os.utime(checkout / '.ai/local/observation.json', (then, then))
            self.register(f'{name}.json', checkout)

    def test_dashboard_render_curses_smoke(self):
        self.fixture_runs(3)
        pid, fd = self.pty_run([str(ROOT / 'scripts/ai-dashboard')])
        seen = [b'']
        self.read_until(fd, seen, 'AI pipelines  0 running · 1 needs you · 1 finished')
        os.write(fd, b'q')
        self.assertEqual(self.finish(pid, fd, seen), 0, seen[0][-400:])
        self.assertIn(b'\x1b[?1049l', seen[0])

    def test_dashboard_render_curses_interaction(self):
        self.fixture_runs(10)
        pid, fd = self.pty_run([str(ROOT / 'scripts/ai-dashboard')], 30, 140)
        seen = [b'']
        self.read_until(fd, seen, 'AI pipelines  0 running · 1 needs you · 1 finished')
        self.assertNotIn('qxzjwvkp', seen[0].decode('utf-8', 'replace'))
        os.write(fd, b'\x1bOB' * 9)
        self.read_until(fd, seen, 'qxzjwvkp')
        os.write(fd, b'\n')
        self.read_until(fd, seen, 'path: ')
        self.assertNotIn('✓Setup', seen[0].decode('utf-8', 'replace'))
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 20, 100, 0, 0))
        os.kill(pid, signal.SIGWINCH)
        self.read_until(fd, seen, '·Build')
        os.write(fd, b'q')
        self.assertEqual(self.finish(pid, fd, seen), 0, seen[0][-400:])
        self.assertIn(b'\x1b[?1049l', seen[0])

    def test_dashboard_render_curses_runs_appear_and_disappear(self):
        empty, name = 'No pipelines found', 'qxzjwvkp'
        pid, fd = self.pty_run([str(ROOT / 'scripts/ai-dashboard')])
        seen = [b'']
        self.read_until(fd, seen, empty)
        checkout = self.checkout(name)
        (checkout / '.ai/local/observation.json').write_text(json.dumps(
            {'stage': 'build', 'state': 'active', 'detail': '', 'note': '', 'since': ''}))
        self.register(f'{name}.json', checkout)
        self.read_until(fd, seen, name)  # picked up by the 2 s auto-refresh
        seen[0] = b''
        (self.state / 'pipelines' / f'{name}.json').unlink()
        os.write(fd, b'r')
        self.read_until(fd, seen, empty)
        os.write(fd, b'q')
        self.assertEqual(self.finish(pid, fd, seen), 0, seen[0][-400:])
        self.assertNotIn(b'Traceback', seen[0])

    def test_dashboard_render_curses_all_toggle_with_only_old_runs(self):
        empty, name = 'No pipelines found', 'qxzjwvkp'
        checkout = self.checkout(name)
        observation = checkout / '.ai/local/observation.json'
        observation.write_text(json.dumps(
            {'stage': 'pr', 'state': 'done', 'detail': '', 'note': '', 'since': ''}))
        old = time.time() - 25 * 3600
        os.utime(observation, (old, old))
        self.register(f'{name}.json', checkout)
        pid, fd = self.pty_run([str(ROOT / 'scripts/ai-dashboard')])
        seen = [b'']
        self.read_until(fd, seen, empty)
        os.write(fd, b'a')
        self.read_until(fd, seen, name)
        seen[0] = b''
        os.write(fd, b'a')
        self.read_until(fd, seen, empty)
        os.write(fd, b'q')
        self.assertEqual(self.finish(pid, fd, seen), 0, seen[0][-400:])
        self.assertNotIn(b'Traceback', seen[0])

    def test_dashboard_render_curses_failure_restores_the_terminal(self):
        self.fixture_runs(2)
        code = ('import sys\nsys.path.insert(0, %r)\nimport dashboard\n'
                'def boom(*a, **k):\n    raise RuntimeError("injected")\n'
                'dashboard.layout = boom\nsys.exit(dashboard.main([]))\n' % str(LIB))
        pid, fd = self.pty_run([sys.executable, '-B', '-c', code])
        seen = [b'']
        status = self.finish(pid, fd, seen)
        self.assertNotEqual(status, 0)
        self.assertIn(b'\x1b[?1049l', seen[0])
        self.assertIn(b'injected', seen[0])


def render_lines(run, width, **options):
    return dash.render([run], width, now=0, state_root='/s', **options)


if __name__ == '__main__':
    unittest.main()
