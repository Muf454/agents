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
import subprocess
import sys
import time


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(data)
    temporary.replace(path)


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
    if not install:
        if timer_unit.exists():
            subprocess.run(['systemctl', '--user', 'disable', '--now', timer_unit.name])
        for unit in (service, timer_unit):
            unit.unlink(missing_ok=True)
        systemctl('daemon-reload')
        print('Removed ' + name)
        return 0
    command = [str(Path(__file__).resolve().parent.parent / 'ai-watchdog'), str(root),
               '--stale-minutes', str(args.stale_minutes)]
    if args.diagnose:
        command += ['--diagnose', '--diagnosis-timeout', str(args.diagnosis_timeout)]
    units.mkdir(parents=True, exist_ok=True)
    # The timer has no login shell: keep the installing shell's PATH (claude, curl, timeout).
    service.write_text(
        '[Unit]\nDescription=AI workflow health check for ' + str(root).replace('%', '%%') + '\n\n'
        '[Service]\nType=oneshot\n'
        'Environment=' + unit_quote('PATH=' + os.environ.get('PATH', '/usr/bin:/bin'), command=False) + '\n'
        'ExecStart=' + ' '.join(unit_quote(part) for part in command) + '\n'
        '# Exit 1 means "incident reported", not a failed probe.\nSuccessExitStatus=1\n')
    timer_unit.write_text(
        '[Unit]\nDescription=Check AI workflow health every 10 minutes\n\n'
        '[Timer]\nOnBootSec=2min\nOnUnitActiveSec=10min\nUnit=' + service.name + '\n\n'
        '[Install]\nWantedBy=timers.target\n')
    systemctl('daemon-reload')
    systemctl('enable', '--now', timer_unit.name)
    print(f'Installed {timer_unit}\nRemove with: {shlex.quote(command[0])} {shlex.quote(str(root))} --uninstall-timer')
    return 0


def runners(root):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / 'cwd').resolve() != root:
                continue
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            # Match executable/script arguments, never a prompt or shell command string.
            if any(Path(os.fsdecode(arg)).name in ('ai-run', 'ai-pipeline')
                   for arg in args[:3] if arg):
                status = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                if status[0] != 'Z':
                    found.append(entry.name + ':' + status[19])
        except (OSError, RuntimeError):
            continue  # Processes may disappear during the snapshot.
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description='Silent health check for one toolkit checkout.')
    parser.add_argument('project', nargs='?', default='.')
    parser.add_argument('--stale-minutes', type=positive, default=45)
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--diagnosis-timeout', type=positive, default=120, help='seconds (default 120)')
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
        now = time.time_ns()
        alive = runners(root)
        state = (ai / 'state.md').read_text() if (ai / 'state.md').exists() else ''
        phase = re.search(r'^Phase:\s*(\S+)\s*$', state, re.M)
        activity = [ai / 'run-log.md', local / 'pauses.log',
                    *local.glob('claude-*.json'), *local.glob('*events.log')]
        newest = max((p.stat().st_mtime_ns for p in activity if p.is_file()), default=ai.stat().st_mtime_ns)
        incidents = {}
        error = local / 'last-error'
        error_time = error.stat().st_mtime_ns if error.is_file() else 0
        # ai-pipeline writes this marker at start and removes it on every exit it controls
        # (finish or ai_die), so a leftover marker means it was killed, crashed or rebooted.
        marker = local / 'pipeline.active'
        if not alive and marker.is_file():
            incidents['died:' + str(marker.stat().st_mtime_ns)] = (
                'Watchdog: ai-pipeline is gone without finishing or reporting a stop '
                '(killed, crashed or machine restarted). Rerun ai-pipeline to resume.')
        elif not alive and not error_time and phase and phase[1] in ('implementing', 'fixing_review'):
            # With a last-error the stop below explains it; this catches a killed ai-run.
            incidents['stalled'] = f'Watchdog: stalled/crashed ({phase[1]}); no checkout runner is alive.'
        # A usage-limit pause is quiet by design until its announced resume time.
        quiet_since = max(newest, paused_until(local))
        if alive and now - quiet_since > args.stale_minutes * 60 * 1_000_000_000:
            incidents['hung:' + ','.join(alive) + ':' + str(quiet_since)] = (
                f'Watchdog: hung; runner alive with no activity for over {args.stale_minutes} minutes.')
        if error_time > previous.get('notified_at_ns', 0):
            incidents['stop:' + str(error_time)] = 'Watchdog: stopped: ' + ' '.join(error.read_text().split())[:500]
        # Keep an already acknowledged stop active until the file changes/disappears.
        stop_key = 'stop:' + str(error_time)
        if error_time and stop_key in previous.get('active', []):
            incidents.setdefault(stop_key, 'Watchdog: stopped.')
        fresh = sorted(set(incidents) - set(previous.get('active', [])))
        record = {'active': sorted(incidents), 'notified_at_ns': previous.get('notified_at_ns', 0)}
        if fresh:
            record['notified_at_ns'] = now
            # Reserve before inference/notification: interrupted probes never start it twice.
            save(state_file, json.dumps(record) + '\n')
            message = ' '.join(incidents[key] for key in fresh)
            if args.diagnose:
                prompt = ('Diagnose this workflow incident read-only. Do not change files or run commands. '
                          'Inspect .ai/state.md, .ai/run-log.md and .ai/local logs as needed. '
                          'Start with a one-line summary, then evidence and suggested human recovery.\n' + message)
                command = ['timeout', '--signal=TERM', '--kill-after=10s', str(args.diagnosis_timeout),
                           'claude', '-p', '--permission-mode', 'dontAsk', '--tools', 'Read,Glob,Grep',
                           '--allowedTools', 'Read,Glob,Grep', '--setting-sources', 'project',
                           '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
                if os.environ.get('AI_MODEL'):
                    command += ['--model', os.environ['AI_MODEL']]
                command += ['--', prompt]
                try:
                    with open('/dev/null') as stdin:
                        result = subprocess.run(command, stdin=stdin, capture_output=True, text=True)
                    diagnosis = result.stdout.strip()
                    if result.returncode or not diagnosis:
                        diagnosis = f'Diagnosis unavailable (exit {result.returncode}).\n' + diagnosis
                except OSError as error:
                    diagnosis = f'Diagnosis unavailable: {error}'
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
