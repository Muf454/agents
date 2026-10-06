"""One-checkout Linux health probe; inference is strictly opt-in."""
import argparse
import calendar
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import subprocess
import sys
import time

# The sibling helper (the same copy: checkout .ai/bin/lib or the timer's host copy).
# No __pycache__: .ai/bin is part of the approved gate digest.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow import check_state_root, overlap  # noqa: E402


class Refused(Exception):
    """An unsafe host layout: reported as is, before anything is written."""


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def save(path, data):
    # Unpredictable, exclusively created temp name: nothing can pre-plant it as a symlink.
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(descriptor, 'w') as file:
            file.write(data)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def mtime(path):
    """mtime in ns, or 0: runners create and delete these files while we look."""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def read(path):
    try:
        return path.read_text()
    except OSError:
        return ''


BOOT_NS = None


def start_ns(ticks):
    """Process start (/proc/PID/stat field 22, clock ticks since boot) as epoch ns."""
    global BOOT_NS
    if BOOT_NS is None:
        btime = re.search(r'^btime (\d+)$', Path('/proc/stat').read_text(), re.M)
        BOOT_NS = int(btime[1]) * 1_000_000_000
    return BOOT_NS + int(ticks) * 1_000_000_000 // os.sysconf('SC_CLK_TCK')


def process(pid):
    """(args, start ticks) of a live, non-zombie process, or None."""
    entry = Path('/proc') / str(pid)
    try:
        status = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
        args = (entry / 'cmdline').read_bytes().split(b'\0')
    except (OSError, IndexError):
        return None
    return None if status[0] == 'Z' else (args, status[19])


def is_runner(args, names=('ai-run', 'ai-pipeline', 'ai-recover')):
    # Match executable/script arguments, never a prompt or shell command string.
    return any(Path(os.fsdecode(arg)).name in names for arg in args[:3] if arg)


def marker_snapshot(marker):
    """(pid, mtime ns) read from one open file, or None if absent/unreadable."""
    try:
        with marker.open() as file:
            return int(file.read().split()[0]), os.fstat(file.fileno()).st_mtime_ns
    except (OSError, ValueError, IndexError):
        return None


def pipeline_died(marker):
    """mtime of a marker whose own ai-pipeline is gone, else 0 (children don't count)."""
    snapshot = marker_snapshot(marker)
    if not snapshot:
        return 0
    pid, written = snapshot
    found = process(pid)
    # A reused PID would have started after the marker was written.
    # ai-recover replaces the pipeline process (exec, same PID) while it decides.
    if found and is_runner(found[0], ('ai-pipeline', 'ai-recover')) and start_ns(found[1]) <= written + 1_000_000_000:
        return 0
    # A pipeline that just finished removes its marker: only an unchanged marker is a crash.
    return written if marker_snapshot(marker) == snapshot else 0


def paused_until(local):
    """End of the latest usage-limit pause (ns), from ai_limit_pause's pauses.log line."""
    try:
        lines = (local / 'pauses.log').read_text().splitlines()
    except OSError:
        return 0
    match = re.match(r'^(\S+) paused (\d+)s:', lines[-1]) if lines else None
    if not match:
        return 0
    try:
        start = calendar.timegm(time.strptime(match[1], '%Y-%m-%dT%H:%M:%SZ'))
    except ValueError:
        return 0
    return int((start + int(match[2])) * 1_000_000_000)


def unit_quote(value, command=True):
    # systemd unquotes C-style, expands %specifiers everywhere and $VARS only in Exec lines.
    if '\n' in value:
        raise ValueError('newline in systemd value')
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return '"' + (escaped.replace('$', '$$') if command else escaped) + '"'


def timer(root, args, install):
    units = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'systemd' / 'user'
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '-', root.name).strip('-') or 'project'
    name = f'ai-watchdog-{slug}-{hashlib.sha256(str(root).encode()).hexdigest()[:8]}'
    service, timer_unit = units / (name + '.service'), units / (name + '.timer')
    def systemctl(*command):
        result = subprocess.run(['systemctl', '--user', *command])
        if result.returncode:
            sys.exit(f'systemctl --user {" ".join(command)} failed (exit {result.returncode})')
    # The timer runs a host copy of the toolkit scripts (outside the checkout), so the code
    # that verifies the gate before crash recovery is never code an agent session could edit.
    host = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'ai-toolkit' / 'watchdog' / name
    if not install:
        if timer_unit.exists():
            systemctl('disable', '--now', timer_unit.name)  # exits before removing anything
        for unit in (service, timer_unit):
            unit.unlink(missing_ok=True)
        shutil.rmtree(host, ignore_errors=True)
        systemctl('daemon-reload')
        print('Removed ' + name)
        return 0
    # Check the TARGET checkout (root), never the caller's directory, before writing anything:
    # a host copy or state dir an agent session can edit would defeat the gate check.
    data = os.environ.get('XDG_DATA_HOME')
    if data and not os.path.isabs(data):
        raise Refused('XDG_DATA_HOME must be an absolute path: ' + data)
    if overlap(host, root):
        raise Refused(f'Host copy {host} overlaps the checkout {root} (agent sessions can write '
                      'there); set XDG_DATA_HOME to a directory outside it.')
    try:
        check_state_root(root)  # reads the AI_STATE_DIR/XDG_STATE_HOME the timer forwards
    except ValueError as error:
        raise Refused(str(error)) from None
    if host.exists():
        shutil.rmtree(host)
    shutil.copytree(Path(__file__).resolve().parent.parent, host / 'bin',
                    ignore=shutil.ignore_patterns('__pycache__'))
    command = [str(host / 'bin' / 'ai-watchdog'), str(root), '--stale-minutes', str(args.stale_minutes)]
    if args.recover:
        command += ['--recover']
    if args.diagnose:
        command += ['--diagnose', '--diagnosis-timeout', str(args.diagnosis_timeout),
                    '--diagnosis-agent', args.diagnosis_agent]
    units.mkdir(parents=True, exist_ok=True)
    # The timer has no login shell: keep the installing shell's PATH (claude, curl, timeout).
    service.write_text(
        '[Unit]\nDescription=AI workflow health check for ' + str(root).replace('%', '%%') + '\n\n'
        '[Service]\nType=oneshot\n'
        + ''.join('Environment=' + unit_quote(key + '=' + value, command=False) + '\n'
                  for key, value in sorted(forwarded_env().items())) +
        'ExecStart=' + ' '.join(unit_quote(part) for part in command) + '\n'
        '# Exit 1 means "incident reported", not a failed probe.\nSuccessExitStatus=1\n')
    timer_unit.write_text(
        '[Unit]\nDescription=Check AI workflow health every 10 minutes\n\n'
        '[Timer]\nOnBootSec=2min\nOnUnitActiveSec=10min\nUnit=' + service.name + '\n\n'
        '[Install]\nWantedBy=timers.target\n')
    systemctl('daemon-reload')
    systemctl('enable', '--now', timer_unit.name)
    print(f'Installed {timer_unit} (scripts copied to {host}; reinstall after updating the toolkit)\n'
          f'Remove with: {shlex.quote(str(root / ".ai/bin/ai-watchdog"))} {shlex.quote(str(root))} --uninstall-timer')
    return 0


# Settings a detached service needs to behave like the human's shell (notifications,
# budgets, host state location). The test clock is deliberately not forwarded.
FORWARDED_ENV = ('PATH', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'AI_STATE_DIR')


def forwarded_env():
    return {key: value for key, value in os.environ.items()
            if (key in FORWARDED_ENV or key.startswith('AI_')) and key != 'AI_WATCHDOG_NOW'
            and '\n' not in value}


def start_recovery(root, local, marker):
    """Start ai-recover outside this (oneshot, soon reaped) service. Returns None when
    recovery confirmed it took over, else the reason it didn't (the human must be told)."""
    # Verify with THIS copy's code (the host copy --install-timer made), never checkout code.
    # Whether recovery is allowed is the approved run's setting; ai-recover enforces it.
    bin_dir = Path(__file__).resolve().parent.parent
    if overlap(bin_dir, root):
        return 'auto-recovery only runs from the installed timer (ai-watchdog --install-timer --recover)'
    try:
        check_state_root(root)  # before trusting the approved run recorded there
    except ValueError as error:
        return 'auto-recovery refused: ' + str(error).rstrip('.')
    common = bin_dir / 'lib' / 'common.sh'
    # Same check ai-pipeline does before handing over: only approved gate code may run.
    digest = subprocess.run(['bash', '-c', 'source "$1"; ai_guard_digest', 'ai-watchdog', str(common)],
                            capture_output=True, text=True)
    approved = subprocess.run(['python3', str(bin_dir / 'lib' / 'workflow.py'), 'run-manifest', 'gate'],
                              capture_output=True, text=True)
    if digest.returncode or approved.returncode or digest.stdout.strip() != approved.stdout.strip():
        return 'auto-recovery refused: gate files changed since the run was approved (or no approved run)'
    error = local / 'last-error'
    if not error.exists():
        save(error, 'ai-pipeline was killed, crashed or the machine restarted\n')
    before = marker_snapshot(marker)
    launched_ns = time.time_ns()
    unit = f'ai-recover-{re.sub(r"[^A-Za-z0-9_.-]+", "-", root.name)}-{int(time.time())}'
    command = ['systemd-run', '--user', '--collect', '--quiet', '--service-type=exec', '--unit=' + unit,
               '--working-directory=' + str(root)]
    command += ['--setenv=' + key + '=' + value for key, value in sorted(forwarded_env().items())]
    command += ['--', str(root / '.ai' / 'bin' / 'ai-recover'), '--stage', 'crash (pipeline killed or restarted)']
    try:
        if subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True).returncode:
            return 'auto-recovery could not be started (systemd-run failed)'
    except OSError:
        return 'auto-recovery could not be started (no systemd-run)'
    # Hand over notification duty only once ai-recover owns the marker (or escalated).
    deadline = time.monotonic() + float(os.environ.get('AI_RECOVER_ACK_SECONDS', '20'))
    while time.monotonic() < deadline:
        # Took over the marker, or already escalated with its own ⛔.
        if marker_snapshot(marker) != before or mtime(local / 'last-error.notified') >= launched_ns:
            return None
        time.sleep(0.2)
    return 'auto-recovery did not confirm it started within 20 seconds'


def runners(root):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / 'cwd').resolve() != root:
                continue
        except (OSError, RuntimeError):
            continue  # Processes may disappear during the snapshot.
        live = process(entry.name)
        if live and is_runner(live[0]):
            found.append((entry.name, live[1]))
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description='Silent health check for one toolkit checkout.')
    parser.add_argument('project', nargs='?', default='.')
    parser.add_argument('--stale-minutes', type=positive, default=45)
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--recover', action='store_true',
                        help='after a crashed ai-pipeline, start ai-recover (bounded auto-recovery)')
    parser.add_argument('--diagnosis-timeout', type=positive, default=120, help='seconds (default 120)')
    parser.add_argument('--diagnosis-agent', choices=('codex', 'claude'), default='codex',
                        help='read-only diagnosis by Codex (default; separate limit) or Claude')
    timer_group = parser.add_mutually_exclusive_group()
    timer_group.add_argument('--install-timer', action='store_true',
                             help='install and start a systemd user timer (every 10 min) with these options')
    timer_group.add_argument('--uninstall-timer', action='store_true')
    args = parser.parse_args()
    root = Path(args.project).resolve()
    ai = root / '.ai'
    local = ai / 'local'
    if not ai.is_dir() or ai.is_symlink() or local.is_symlink():
        parser.error('project must have a real .ai directory and safe .ai/local')
    if args.install_timer or args.uninstall_timer:
        try:
            return timer(root, args, args.install_timer)
        except Refused as error:
            parser.error('refusing to install the timer: ' + str(error))
        except (OSError, ValueError) as error:
            parser.error('cannot write the timer units: ' + str(error))
    local.mkdir(exist_ok=True)
    for name in ('watchdog.lock', 'watchdog.json', 'watchdog.json.tmp', 'diagnosis.md', 'diagnosis.md.tmp'):
        if (local / name).is_symlink():
            parser.error('unsafe watchdog output path: ' + name)
    os.chdir(root)
    with (local / 'watchdog.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_file = local / 'watchdog.json'
        try:
            previous = json.loads(state_file.read_text())
            if (not isinstance(previous, dict)
                    or not isinstance(previous.get('notified_at_ns', 0), int)
                    or not isinstance(previous.get('active', []), list)
                    or not all(isinstance(key, str) for key in previous.get('active', []))):
                raise ValueError('invalid dedupe record')
        except FileNotFoundError:
            previous = {}
        except (ValueError, OSError) as error:
            parser.error('cannot read watchdog.json: ' + str(error))
        # AI_WATCHDOG_NOW (epoch seconds) is for tests, like AI_SLEEP.
        now = int(float(os.environ['AI_WATCHDOG_NOW']) * 1e9) if os.environ.get('AI_WATCHDOG_NOW') else time.time_ns()
        alive = runners(root)
        phase = re.search(r'^Phase:\s*(\S+)\s*$', read(ai / 'state.md'), re.M)
        activity = [ai / 'run-log.md', local / 'pauses.log', *local.glob('claude-*.json'),
                    *local.glob('*events.log'), *local.glob('check-*.log')]
        newest = max([mtime(path) for path in activity] + [mtime(ai)])
        incidents = {}
        error = local / 'last-error'
        error_time = mtime(error)
        # ai-pipeline writes this marker (its PID) at start and removes it on every exit it
        # controls (finish or ai_die), so a marker whose own process is gone means it was
        # killed, crashed or rebooted, even if an orphaned ai-run child still runs.
        marker = local / 'pipeline.active'
        died = pipeline_died(marker)
        if died:
            incidents['died:' + str(died)] = (
                '⛔ STOPPED, needs you: ai-pipeline is gone without finishing or reporting a stop '
                '(killed, crashed or machine restarted). Rerun ai-pipeline to resume.')
        elif not alive and not error_time and phase and phase[1] in ('implementing', 'fixing_review'):
            # With a last-error the stop below explains it; this catches a killed ai-run.
            incidents['stalled'] = (f'⛔ STOPPED, needs you: nothing is running but the checkout is mid-'
                                    f'{phase[1]} (killed runner?). Rerun ai-pipeline or ai-run to resume.')
        # Quiet time counts from this run's start (old logs of a resumed run don't count),
        # and a usage-limit pause is quiet by design until its announced resume time.
        quiet_since = max(newest, paused_until(local))
        if alive:
            quiet_since = max(quiet_since, min(start_ns(ticks) for _, ticks in alive))
        if alive and now - quiet_since > args.stale_minutes * 60 * 1_000_000_000:
            identity = ','.join(pid + ':' + ticks for pid, ticks in alive)
            incidents['hung:' + identity + ':' + str(quiet_since)] = (
                f'⚠ HUNG? A runner is alive but has logged nothing for over {args.stale_minutes} minutes. '
                'It keeps running; check it.')
        # A stop while a runner/recovery is still alive isn't final yet: judge it once it ends.
        if error_time > previous.get('notified_at_ns', 0) and not alive:
            incidents['stop:' + str(error_time)] = 'Stopped: ' + (' '.join(read(error).split())[:500] or 'see .ai/local')
        # Keep an already acknowledged stop active until the file changes/disappears.
        stop_key = 'stop:' + str(error_time)
        if error_time and stop_key in previous.get('active', []):
            incidents.setdefault(stop_key, 'Stopped.')
        fresh = sorted(set(incidents) - set(previous.get('active', [])))
        record = {'active': sorted(incidents), 'notified_at_ns': previous.get('notified_at_ns', 0)}
        if fresh:
            record['notified_at_ns'] = now
            # Reserve before inference/notification: interrupted probes never start it twice.
            save(state_file, json.dumps(record) + '\n')
            # Stops the runner already announced aren't repeated (they only matter for a diagnosis).
            announced = mtime(local / 'last-error.notified') >= error_time > 0
            loud = [key for key in fresh if not (key.startswith('stop:') and announced)]
            for key in loud:
                if key.startswith('stop:'):
                    incidents[key] = '⛔ STOPPED, needs you: ' + incidents[key]
            message = ' '.join(incidents[key] for key in loud)
            if not loud and args.diagnose:
                message = '🩺 Diagnosis of the stop (' + incidents[fresh[0]][:200] + ').'
            if args.recover and any(key.startswith('died:') for key in fresh):
                refused = start_recovery(root, local, marker)
                if refused is None:
                    # ai-recover announces itself (🔧 Recovering / ⛔ STOPPED); stay quiet.
                    loud = [key for key in loud if not key.startswith('died:')]
                    message = ' '.join(incidents[key] for key in loud)
                else:
                    message += ' (' + refused + '.)'
            if not message:
                save(state_file, json.dumps(record) + '\n')
                return 1
            if args.diagnose:
                prompt = ('Diagnose this workflow incident read-only: inspect files, but never modify, '
                          'create or delete anything or run project code (tests, builds, git writes). '
                          'Inspect .ai/state.md, .ai/run-log.md and .ai/local logs as needed. '
                          'Start with a one-line summary, then evidence and suggested human recovery.\n' + message)
                command = ['timeout', '--signal=TERM', '--kill-after=10s', str(args.diagnosis_timeout)]
                output = None
                if args.diagnosis_agent == 'codex':
                    # Default: Codex has its own limit; Claude's is shared with interactive sessions.
                    descriptor, output = tempfile.mkstemp(dir=local, prefix='.diagnosis-', suffix='.md')
                    os.close(descriptor)
                    command += ['codex', 'exec', '--ignore-user-config', '-c', 'approval_policy="never"',
                                '--sandbox', 'read-only', '-c', 'model_reasoning_effort="medium"',
                                '--output-last-message', output, prompt]
                else:
                    command += ['claude', '-p', '--permission-mode', 'dontAsk', '--tools', 'Read,Glob,Grep',
                                '--allowedTools', 'Read,Glob,Grep', '--setting-sources', 'project',
                                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
                    if os.environ.get('AI_MODEL'):
                        command += ['--model', os.environ['AI_MODEL']]
                    command += ['--', prompt]
                try:
                    with open('/dev/null') as stdin:
                        result = subprocess.run(command, stdin=stdin, capture_output=True, text=True)
                    diagnosis = (read(Path(output)) if output else result.stdout).strip()
                    if result.returncode or not diagnosis:
                        diagnosis = f'Diagnosis unavailable (exit {result.returncode}).\n' + diagnosis
                except OSError as error:
                    diagnosis = f'Diagnosis unavailable: {error}'
                finally:
                    if output:
                        Path(output).unlink(missing_ok=True)
                save(local / 'diagnosis.md', diagnosis + '\n')
                message += ' Diagnosis: ' + ' '.join(diagnosis.splitlines()[0].split())[:300]
            common = Path(__file__).resolve().with_name('common.sh')
            subprocess.run(['bash', '-c', 'source "$1"; AI_ROOT=$2; ai_notify "$3"',
                            'ai-watchdog', str(common), str(root), message], check=False)
        else:
            save(state_file, json.dumps(record) + '\n')
        return 1 if incidents else 0


if __name__ == '__main__':
    sys.exit(main())
