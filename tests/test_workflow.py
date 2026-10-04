"""Offline integration tests: real shell tools/Git, mock Claude and Codex."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/lib/workflow.py'


def task(task_id, status='TODO', dependencies='none'):
    return f'''## {task_id} — Verify {task_id}
Status: {status}
Dependencies: {dependencies}

### Goal
Write a local test artifact.
### Implementation notes
Use the offline mock agent.
### Likely affected modules
{task_id}.txt
### Acceptance criteria
The artifact exists and the real validation succeeds.
### Validation
bash .ai/validate
### Result / notes
Pending.

'''


MOCK_CLAUDE = r'''#!/usr/bin/env python3
import json, os, pathlib, re, subprocess, sys, time
# Real CLIs read extra prompt input from an open stdin and can hang; it must be /dev/null.
assert os.path.samestat(os.fstat(0), os.stat('/dev/null')), 'claude stdin not /dev/null'
args = sys.argv[1:]
assert '--permission-mode' in args and args[args.index('--permission-mode')+1] == 'dontAsk'
assert '--' in args
prompt = args[args.index('--')+1]
assert 'RUNNER CONTRACT' in prompt or 'TRIAGE CONTRACT' in prompt
assert '--strict-mcp-config' in args
assert args[args.index('--setting-sources')+1] == 'project'
knowledge = os.environ.get('MOCK_KNOWLEDGE_DIR')
if knowledge:
    assert args[args.index('--add-dir')+1] == knowledge
    assert 'Project knowledge base explicitly configured' in prompt
    assert knowledge in prompt
else:
    assert '--add-dir' not in args
mode = os.environ.get('MOCK_CLAUDE', 'success')
with open('.ai/local/mock-invocations', 'a') as f: f.write('call\n')
with open('.ai/local/mock-args', 'a') as f: f.write(' '.join(a for a in args if a != prompt) + '\n')
if mode == 'limit-once' and not pathlib.Path('.ai/local/mock-limit-hit').exists():
    pathlib.Path('.ai/local/mock-limit-hit').touch()
    print(json.dumps({'type':'result','subtype':'error','is_error':True,
                      'result':"You've hit your usage limit. Try again in 2 minutes."}))
    sys.exit(1)
if mode == 'limit-far':
    print(json.dumps({'type':'result','subtype':'error','is_error':True,
                      'result':'Claude AI usage limit reached|' + str(int(time.time()) + 7 * 86400)}))
    sys.exit(1)
if 'TRIAGE CONTRACT' in prompt:
    tasks_file = pathlib.Path('.ai/tasks.md')
    text = tasks_file.read_text()
    review = pathlib.Path('.ai/reviews/dispositions.md')
    if mode == 'triage-rewrites-review':
        current = pathlib.Path('.ai/reviews/current.md')
        current.write_text(current.read_text().replace('MAJOR=1', 'MAJOR=0'))
        subprocess.run(['git','add','--','.ai/reviews/current.md'],check=True)
    elif mode == 'triage-accept-done':
        review.write_text(review.read_text() + '| M1 | accepted | already handled by T001 | T001 |\n')
        subprocess.run(['git','add','--','.ai/reviews/dispositions.md'],check=True)
    elif mode in ('triage-reject', 'triage-defer', 'triage-missing'):
        row = {'triage-reject': '| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
               'triage-defer': '| M1 | deferred | real but out of scope for this change | none |\n',
               'triage-missing': 'Looked at the review; no decision recorded.\n'}[mode]
        review.write_text(review.read_text() + row)
        subprocess.run(['git','add','--','.ai/reviews/dispositions.md'],check=True)
    else:
        ids = [int(x) for x in re.findall(r'^## T(\d+)', text, re.M)]
        new_id = 'T%03d' % (max(ids) + 1)
        block = open(os.environ['MOCK_TASK_TEMPLATE']).read().replace('TXXX', new_id)
        tasks_file.write_text(text.rstrip('\n') + '\n\n' + block)
        review.write_text(review.read_text() + f'| M1 | accepted | fixture defect confirmed | {new_id} |\n'
                          + ('| M2 | deferred | real but out of scope for this change | none |\n'
                             if mode == 'triage-mixed' else ''))
        paths = ['.ai/tasks.md', '.ai/reviews/dispositions.md']
        if mode == 'triage-touches-source':
            pathlib.Path('src.txt').write_text('not allowed in triage')
            paths.append('src.txt')
        subprocess.run(['git','add','--',*paths],check=True)
    subprocess.run(['git','commit','-qm','triage review'],check=True)
    print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[]}))
    sys.exit(0)
if mode == 'timeout':
    pathlib.Path('partial.txt').write_text('interrupted work')
    time.sleep(30)
if mode == 'error':
    print(json.dumps({'type':'result','subtype':'error','is_error':True}))
    sys.exit(0)
if mode == 'denied':
    print(json.dumps({'type':'result','subtype':'success','is_error':False,
                      'permission_denials':[{'tool_name':'Bash'}]}))
    sys.exit(0)
denied_but_done = mode == 'denied-but-done'
if denied_but_done:
    mode = 'success'
if mode == 'invalid':
    print('not JSON')
    sys.exit(0)
if mode not in ('no-progress', 'bad-format'):
    task_id = re.search(r'exactly one task in this invocation: (T\d+)', prompt).group(1)
    file = pathlib.Path('.ai/tasks.md')
    text = file.read_text()
    start = text.index('## ' + task_id + ' —')
    end = text.find('\n## ', start + 1)
    if end == -1: end = len(text)
    part = text[start:end]
    status = 'BLOCKED' if mode == 'blocked-first' and task_id == 'T001' else 'DONE'
    part = re.sub(r'^Status:.*$', 'Status: ' + status, part, flags=re.M)
    file.write_text(text[:start] + part + text[end:])
    pathlib.Path(task_id + '.txt').write_text('checkpointed implementation')
    if mode == 'tamper':
        target = pathlib.Path(os.environ['MOCK_TAMPER_PATH'])
        if target.suffix == '.py':
            target.write_text("from pathlib import Path\nPath('UNTRUSTED_HELPER_RAN').touch()\n")
        elif target.name == 'ai-check':
            target.write_text('#!/usr/bin/env bash\ntouch UNTRUSTED_CHECK_RAN\nexit 0\n')
        elif target.name == 'validate':
            target.write_text('#!/usr/bin/env bash\nexit 0\n')
        else:
            target.write_text('modified by agent\n')
    if mode != 'dirty':
        subprocess.run(['git','add','--','.ai/tasks.md','.ai/state.md',task_id+'.txt','.ai/validate'],check=True)
        if mode == 'tamper':
            subprocess.run(['git','add','--',os.environ['MOCK_TAMPER_PATH']],check=True)
        subprocess.run(['git','commit','-qm','implement '+task_id],check=True)
if mode == 'bad-format':
    pathlib.Path('.ai/tasks.md').write_text('## T001 — broken\nStatus: MAGIC\n')
if denied_but_done:
    # Real-run behaviour: a denied shell write, worked around, plus an uncommitted run-log line.
    with open('.ai/run-log.md', 'a') as f: f.write('| now | claude | T001 | done | pass | x | note |\n')
    print(json.dumps({'type':'result','subtype':'success','is_error':False,
                      'permission_denials':[{'tool_name':'Bash','tool_input':{'command':'cat > greet.py'}}]}))
    sys.exit(0)
print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[]}))
'''

MOCK_CODEX = r'''#!/usr/bin/env python3
import os, pathlib, sys
assert os.path.samestat(os.fstat(0), os.stat('/dev/null')), 'codex stdin not /dev/null'
args = sys.argv[1:]
assert args[0] == 'exec'
assert args[args.index('--sandbox')+1] == 'read-only'
assert 'approval_policy="never"' in args
assert '--ignore-user-config' in args
mode = os.environ.get('MOCK_CODEX', 'success')
state = pathlib.Path(os.environ.get('MOCK_STATE_DIR', '.'))
calls = state / 'codex-calls'
calls.write_text(calls.read_text() + 'call\n' if calls.exists() else 'call\n')
count = calls.read_text().count('call')
if mode == 'error': sys.exit(17)
if mode == 'limit-once' and count == 1:
    print('ERROR: usage_limit_reached. You have hit your usage limit. Try again in 3 minutes.')
    sys.exit(1)
path = pathlib.Path(args[args.index('--output-last-message')+1])
if mode == 'empty': sys.exit(0)
if mode == 'malformed':
    path.write_text('looks fine')
    sys.exit(0)
if mode == 'mutates':
    pathlib.Path('unexpected.txt').write_text('unexpected concurrent edit')
if mode == 'counts-lie':
    path.write_text('# Independent review\nOverall verdict: says clean but lists a finding\n'
                    'Finding counts: BLOCKER=0 MAJOR=0 MINOR=0\n## BLOCKER findings\nNone found.\n'
                    '## MAJOR findings\n- M1: a real defect.\n## MINOR findings\nNone found.\n'
                    '## Missing test coverage\nx\n## Security concerns\nx\n## Architecture concerns\nx\n'
                    '## Manual testing recommendations\nx\n')
    sys.exit(0)
major = mode == 'major-always' or (mode in ('major-once', 'two-major-once') and count == 1)
two = mode == 'two-major-once' and count == 1
path.write_text("""# Independent review
Overall verdict: """ + ('one major finding' if major else 'no demonstrated findings in inspected fixture') + """
Finding counts: BLOCKER=0 MAJOR=""" + ('2' if two else '1' if major else '0') + """ MINOR=0
## BLOCKER findings
None found.
## MAJOR findings
""" + ('- M1: fixture defect at T001.txt:1.' + ('\n- M2: second defect, out of scope.' if two else '') if major else 'None found.') + """
## MINOR findings
None found.
## Missing test coverage
Only an offline fixture was inspected.
## Security concerns
No real model or application reviewed.
## Architecture concerns
No application built.
## Manual testing recommendations
Run a supervised CLI smoke test in a real project.
""")
'''


MOCK_GH = r'''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
args = sys.argv[1:]
log = pathlib.Path(os.environ['MOCK_GH_LOG'])
with log.open('a') as f: f.write(json.dumps(args) + '\n')
draft = pathlib.Path(os.environ['MOCK_STATE_DIR']) / 'gh-draft'
if args[:2] == ['pr', 'view']:
    if not os.environ.get('MOCK_GH_EXISTING'):
        sys.exit(1)
    if 'isDraft' in args:
        print('true' if draft.exists() else 'false'); sys.exit(0)
    print('https://github.com/example/project/pull/7'); sys.exit(0)
if args[:2] == ['pr', 'ready']:
    if os.environ.get('MOCK_GH_READY_FAIL'):
        sys.exit(1)
    draft.touch(); sys.exit(0)
if args[:2] in (['pr', 'create'], ['pr', 'edit']):
    body = args[args.index('--body-file') + 1]
    shutil.copy(body, str(log) + '.body.md')
    if args[1] == 'create': print('https://github.com/example/project/pull/7')
    sys.exit(0)
sys.exit(2)
'''

MOCK_SLEEP = r'''#!/usr/bin/env bash
echo "$1" >> "$MOCK_SLEEP_LOG"
'''


class ToolkitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai-toolkit-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project with spaces'
        self.project.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
        self.run_cmd(['git', 'init', '-b', 'main'])
        self.run_cmd(['git', 'config', 'user.name', 'Toolkit Test'])
        self.run_cmd(['git', 'config', 'user.email', 'toolkit-test@example.invalid'])
        self.run_cmd(['git', 'config', 'commit.gpgsign', 'false'])
        self.mock_bin = self.base / 'mock-bin'
        self.mock_bin.mkdir()
        for name, contents in (('claude', MOCK_CLAUDE), ('codex', MOCK_CODEX), ('gh', MOCK_GH),
                               ('mock-sleep', MOCK_SLEEP)):
            file = self.mock_bin / name
            file.write_text(contents)
            file.chmod(0o755)
        self.env['PATH'] = str(self.mock_bin) + os.pathsep + self.env['PATH']
        self.config = self.base / 'xdg-config'
        self.config.mkdir()
        template = self.base / 'task-template.md'
        template.write_text(task('TXXX'))
        self.notify_log = self.base / 'notifications.log'
        self.env.update(XDG_CONFIG_HOME=str(self.config), MOCK_STATE_DIR=str(self.base),
                        MOCK_GH_LOG=str(self.base / 'gh.log'), MOCK_TASK_TEMPLATE=str(template),
                        AI_STATE_DIR=str(self.base / 'host-state'),
                        MOCK_SLEEP_LOG=str(self.base / 'sleep.log'), AI_SLEEP=str(self.mock_bin / 'mock-sleep'),
                        AI_NOTIFY_CMD=f'printf "%s\\n" "$1" >> "{self.notify_log}"')

    def run_cmd(self, command, expected=0, env=None):
        result = subprocess.run(command, cwd=self.project, env=env or self.env,
                                capture_output=True, text=True, timeout=25)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def setup_project(self, *options):
        return self.run_cmd([str(ROOT / 'scripts/setup-project'), *options, str(self.project)])

    def helper(self, *args, expected=0):
        return self.run_cmd(['python3', str(HELPER), *args], expected=expected)

    def commit(self, message='fixture'):
        self.run_cmd(['git', 'add', '--all'])
        self.run_cmd(['git', 'commit', '-qm', message])

    def watchdog(self, *args, expected=0):
        return self.tool('ai-watchdog', *args, expected=expected)

    def watchdog_phase(self, phase):
        (self.project / '.ai/state.md').write_text('Phase: ' + phase + '\n')

    def watchdog_runner(self, project=None, name='ai-run'):
        script = self.base / name
        script.write_text(f'#!/usr/bin/env bash\nexec -a {name} sleep 30\n')
        script.chmod(0o755)
        process = subprocess.Popen([str(script)], cwd=project or self.project, env=self.env)
        self.addCleanup(lambda: (process.terminate(), process.wait()) if process.poll() is None else None)
        # Wait for exec using the process command line rather than a timing guess.
        import time
        for _ in range(100):
            if Path(f'/proc/{process.pid}/cmdline').read_bytes().startswith(name.encode() + b'\0'):
                break
            time.sleep(0.01)
        return process

    def test_watchdog_health_stall_recovery_and_checkout_scope(self):
        self.setup_project()
        self.watchdog()
        self.assertEqual(self.notifications(), '')
        self.watchdog_phase('implementing')
        other = self.base / 'other'
        other.mkdir()
        self.watchdog_runner(other)
        self.watchdog(expected=1)
        self.watchdog(expected=1)
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.watchdog_phase('ready_for_review')
        self.watchdog()
        self.watchdog_phase('fixing_review')
        self.watchdog(expected=1)
        self.assertEqual(len(self.notifications().splitlines()), 2)

    def test_watchdog_hung_activity_sources_and_new_incident(self):
        import time
        self.setup_project()
        self.watchdog_runner()
        fake = time.time() + 3600  # the runner has been alive for an hour
        self.env['AI_WATCHDOG_NOW'] = str(fake)
        log = self.project / '.ai/run-log.md'
        old = time.time() - 3600
        os.utime(log, (old, old))
        self.watchdog('--stale-minutes', '120')
        self.watchdog(expected=1)
        self.watchdog(expected=1)
        self.assertEqual(len(self.notifications().splitlines()), 1)
        for name in ('pauses.log', 'claude-test.json', 'test-events.log'):
            activity = self.project / '.ai/local' / name
            activity.touch()
            os.utime(activity, (fake, fake))
            self.watchdog()
            os.utime(activity, (old, old))
        self.watchdog(expected=1)
        self.assertEqual(len(self.notifications().splitlines()), 2)

    def test_watchdog_stop_diagnosis_once_and_new_stop(self):
        self.setup_project()
        mock = self.mock_bin / 'claude'
        mock.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
assert os.path.samestat(os.fstat(0), os.stat('/dev/null'))
a = sys.argv[1:]
assert a[0] == '-p'
assert a[a.index('--tools')+1] == 'Read,Glob,Grep'
assert a[a.index('--allowedTools')+1] == 'Read,Glob,Grep'
assert a[a.index('--permission-mode')+1] == 'dontAsk'
assert a[a.index('--setting-sources')+1] == 'project'
assert '--strict-mcp-config' in a
with open(os.environ['MOCK_STATE_DIR'] + '/diagnosis-calls', 'a') as f: f.write('call\\n')
print('Runner stopped after a failed check.\\nInspect validation evidence.')
''')
        error = self.project / '.ai/local/last-error'
        error.parent.mkdir(exist_ok=True)
        error.write_text('validation failed')
        self.watchdog('--diagnose', expected=1)
        self.watchdog('--diagnose', expected=1)
        self.assertEqual((self.base / 'diagnosis-calls').read_text().count('call'), 1)
        self.assertIn('Runner stopped after a failed check.', self.notifications())
        self.assertIn('Inspect validation evidence.', (self.project / '.ai/local/diagnosis.md').read_text())
        error.write_text('another stop')
        self.watchdog('--diagnose', expected=1)
        self.assertEqual((self.base / 'diagnosis-calls').read_text().count('call'), 2)

    def test_watchdog_diagnosis_failure_is_not_retried_and_usage(self):
        self.setup_project()
        self.watchdog('--stale-minutes', '0', expected=2)
        self.watchdog('--unknown', expected=2)
        self.watchdog_phase('implementing')
        (self.mock_bin / 'claude').write_text('#!/usr/bin/env bash\nexit 17\n')
        self.watchdog('--diagnose', expected=1)
        self.watchdog('--diagnose', expected=1)
        self.assertIn('exit 17', (self.project / '.ai/local/diagnosis.md').read_text())
        self.assertEqual(len(self.notifications().splitlines()), 1)

    def test_watchdog_usage_pause_is_not_hung(self):
        import time
        self.setup_project()
        self.watchdog_runner()
        self.env['AI_WATCHDOG_NOW'] = str(time.time() + 3600)
        old = time.time() - 3600
        os.utime(self.project / '.ai/run-log.md', (old, old))
        pauses = self.project / '.ai/local/pauses.log'
        pauses.parent.mkdir(exist_ok=True)
        start = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(old))
        pauses.write_text(start + ' paused 9000s: Claude usage limit (resume ~Mon 12:00)\n')
        os.utime(pauses, (old, old))
        self.watchdog()
        pauses.write_text(start + ' paused 60s: Claude usage limit (resume ~Mon 12:00)\n')
        os.utime(pauses, (old, old))
        self.watchdog(expected=1)
        self.assertIn('hung', self.notifications())

    def test_watchdog_pipeline_marker_detects_killed_pipeline(self):
        self.setup_project()
        self.watchdog_phase('ready_for_review')
        marker = self.project / '.ai/local/pipeline.active'
        marker.parent.mkdir(exist_ok=True)
        dead = subprocess.Popen(['true'])
        dead.wait()
        marker.write_text(f'{dead.pid}\n')
        self.watchdog(expected=1)
        self.watchdog(expected=1)
        self.assertEqual(self.notifications().count('gone without finishing'), 1)
        self.assertNotIn('stalled', self.notifications())

    def test_watchdog_orphaned_child_does_not_hide_dead_pipeline(self):
        self.setup_project()
        pipeline = self.watchdog_runner(name='ai-pipeline')
        self.watchdog_runner()  # its ai-run child
        marker = self.project / '.ai/local/pipeline.active'
        marker.parent.mkdir(exist_ok=True)
        marker.write_text(f'{pipeline.pid}\n')
        self.watchdog()
        pipeline.kill()
        pipeline.wait()
        self.watchdog(expected=1)
        self.assertIn('gone without finishing', self.notifications())
        # A reused PID that started after the marker was written is not the pipeline.
        os.utime(marker, (1, 1))
        later = self.watchdog_runner(name='ai-pipeline')
        marker.write_text(f'{later.pid}\n')
        os.utime(marker, (1, 1))
        self.watchdog(expected=1)

    def test_watchdog_resumed_run_ignores_old_logs(self):
        import time
        self.setup_project()
        old = time.time() - 7200
        for path in (self.project / '.ai/run-log.md', self.project / '.ai'):
            os.utime(path, (old, old))
        self.watchdog_runner()
        self.watchdog()  # just started: not hung despite 2-hour-old logs
        self.assertEqual(self.notifications(), '')

    def test_watchdog_install_and_uninstall_timer(self):
        project = self.base / 'my 100% project'
        project.mkdir()
        self.project = project
        self.run_cmd(['git', 'init', '-q', '-b', 'main'])
        self.setup_project()
        (self.mock_bin / 'systemctl').write_text(
            '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_STATE_DIR/systemctl.log"\n')
        (self.mock_bin / 'systemctl').chmod(0o755)
        self.watchdog('--install-timer', '--diagnose', '--stale-minutes', '90')
        units = sorted((self.config / 'systemd/user').iterdir())
        self.assertEqual([u.suffix for u in units], ['.service', '.timer'])
        self.assertTrue(units[0].name.startswith('ai-watchdog-my-100-project-'))
        service = units[0].read_text()
        exec_start = next(line for line in service.splitlines() if line.startswith('ExecStart='))
        self.assertIn('"' + str(project).replace('%', '%%') + '"', exec_start)
        self.assertIn('"--stale-minutes" "90" "--diagnose"', exec_start)
        self.assertIn('SuccessExitStatus=1', service)
        self.assertIn('Unit=' + units[0].name, units[1].read_text())
        calls = (self.base / 'systemctl.log').read_text().splitlines()
        self.assertEqual(calls, ['--user daemon-reload', '--user enable --now ' + units[1].name])
        self.watchdog('--uninstall-timer')
        self.assertEqual(list((self.config / 'systemd/user').iterdir()), [])
        self.assertIn('--user disable --now ' + units[1].name, (self.base / 'systemctl.log').read_text())
        self.watchdog('--install-timer', '--uninstall-timer', expected=2)

    def test_watchdog_diagnosis_timeout_and_concurrent_dedupe(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        (self.mock_bin / 'claude').write_text(
            '#!/usr/bin/env bash\nprintf "call\\n" >> "$MOCK_STATE_DIR/timeout-calls"\nsleep 30\n')
        command = [str(self.project / '.ai/bin/ai-watchdog'), '--diagnose', '--diagnosis-timeout', '1']
        first = subprocess.Popen(command, cwd=self.project, env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.watchdog('--diagnose', '--diagnosis-timeout', '1', expected=1)
            first.communicate(timeout=15)
            self.assertEqual(first.returncode, 1)
        finally:
            if first.poll() is None:
                first.kill()
                first.wait()
        self.assertEqual((self.base / 'timeout-calls').read_text().count('call'), 1)
        self.assertIn('exit 124', (self.project / '.ai/local/diagnosis.md').read_text())
        self.assertEqual(len(self.notifications().splitlines()), 1)

    def ready(self, queue=None):
        self.setup_project()
        self.commit('bootstrap')
        self.run_cmd(['git', 'switch', '-c', 'feature/test'])
        (self.project / '.ai/tasks.md').write_text(queue or task('T001'))
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nset -euo pipefail\npython3 -c "assert 2 + 2 == 4"\n')
        self.commit('approved plan and real fixture gate')

    def tool(self, name, *args, expected=0, **env):
        return self.run_cmd([str(self.project / '.ai/bin' / name), *args], expected=expected,
                            env=dict(self.env, **env))

    def test_setup_dry_run_preservation_and_repeatability(self):
        (self.project / 'CLAUDE.md').write_text('human instructions\n')
        (self.project / 'AGENTS.md').write_text('human review contract\n')
        (self.project / '.gitignore').write_text('existing-rule\n')
        result = self.setup_project('--dry-run')
        self.assertIn('KEEP   CLAUDE.md', result.stdout)
        self.assertIn('WARNING: KEEP CLAUDE.md', result.stdout)
        self.assertIn('WARNING: KEEP AGENTS.md', result.stdout)
        self.assertIn('Workflow rules are NOT installed', result.stdout)
        self.assertFalse((self.project / '.ai').exists())
        self.setup_project()
        self.assertEqual((self.project / 'CLAUDE.md').read_text(), 'human instructions\n')
        self.assertEqual((self.project / 'AGENTS.md').read_text(), 'human review contract\n')
        before = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*')
                  if p.is_file() and '.git' not in p.parts}
        self.setup_project()
        after = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*')
                 if p.is_file() and '.git' not in p.parts}
        self.assertEqual(before, after)
        self.assertTrue((self.project / '.ai/bin/ai-run').stat().st_mode & 0o100)
        self.assertEqual((self.project / '.gitignore').read_text().count('/.ai/local/'), 1)

    def test_setup_rejects_symlink_before_any_copy(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.project / 'docs').symlink_to(outside, target_is_directory=True)
        result = self.run_cmd([str(ROOT / 'scripts/setup-project'), str(self.project)], expected=1)
        self.assertIn('symlink', result.stderr)
        self.assertFalse((self.project / 'CLAUDE.md').exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_setup_rejects_subdirectory_and_file_collision(self):
        nested = self.project / 'nested'
        nested.mkdir()
        self.run_cmd([str(ROOT / 'scripts/setup-project'), str(nested)], expected=1)
        (self.project / '.ai').mkdir()
        (self.project / '.ai/tasks.md').mkdir()
        self.run_cmd([str(ROOT / 'scripts/setup-project'), str(self.project)], expected=1)
        self.assertFalse((self.project / 'CLAUDE.md').exists())

    def test_candidates_do_not_execute_commands(self):
        (self.project / 'package.json').write_text(json.dumps({'scripts': {
            'lint': 'touch NEVER_EXECUTED', 'test': 'test command', 'start': 'server'}}))
        (self.project / 'pnpm-lock.yaml').write_text('')
        self.setup_project()
        text = (self.project / '.ai/validation-candidates.md').read_text()
        self.assertIn('pnpm run lint', text)
        self.assertNotIn('pnpm run start', text)
        self.assertFalse((self.project / 'NEVER_EXECUTED').exists())

    def test_empty_template_is_not_a_real_task(self):
        self.setup_project()
        self.helper('tasks', 'check', expected=1)
        self.helper('tasks', 'complete', expected=1)
        self.assertEqual(self.helper('tasks', 'next').stdout.strip(), 'none')
        result = self.tool('ai-status')
        self.assertIn('0 / 0', result.stdout)
        self.assertIn('Last checkpoint: none', result.stdout)

    def test_invalid_task_queues_fail(self):
        self.setup_project()
        cases = [task('T001', 'MAGIC'), task('T001') + task('T001'),
                 task('T001', dependencies='T999'),
                 task('T001', dependencies='T002') + task('T002', dependencies='T001'),
                 task('T001') + task('T002', 'DONE', 'T001'),
                 task('T001', 'IN_PROGRESS') + task('T002', 'IN_PROGRESS'),
                 task('T001').replace('### Validation', '### Missing'),
                 task('T001').replace('Status: TODO', 'Status: TODO\nStatus: DONE')]
        for queue in cases:
            with self.subTest(queue=queue[:100]):
                (self.project / '.ai/tasks.md').write_text(queue)
                self.helper('tasks', 'check', expected=1)

    def test_resume_priority_and_blocked_dependencies(self):
        self.ready(task('T001', 'BLOCKED') + task('T002', dependencies='T001') + task('T003', 'IN_PROGRESS'))
        self.assertEqual(self.helper('tasks', 'next').stdout.strip(), 'T003')
        self.helper('tasks', 'set', 'T003', 'DONE')
        self.assertEqual(self.helper('tasks', 'next').stdout.strip(), 'none')

    def test_validation_placeholder_failure_and_stale_success(self):
        self.setup_project()
        self.commit()
        self.tool('ai-check', expected=78)
        self.helper('stamp', 'verify', expected=1)
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nexit 0\n')
        self.tool('ai-check')
        self.helper('stamp', 'verify')
        (self.project / 'source.txt').write_text('new untracked content')
        self.helper('stamp', 'verify', expected=1)
        self.tool('ai-check')
        self.commit('same validated content')
        self.helper('stamp', 'verify')
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nexit 31\n')
        self.tool('ai-check', expected=31)
        self.helper('stamp', 'verify', expected=1)

    def test_validation_content_mutation_and_timeout_fail(self):
        self.ready()
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\necho changed > source.txt\n')
        self.tool('ai-check', expected=1)
        self.helper('stamp', 'verify', expected=1)
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nsleep 30\n')
        self.tool('ai-check', expected=124, AI_CHECK_TIMEOUT='1')
        self.helper('stamp', 'verify', expected=1)

    def test_runner_requires_approval_feature_branch_and_clean_checkpoint(self):
        self.ready()
        self.tool('ai-run', expected=1)
        self.run_cmd(['git', 'switch', 'main'])
        self.tool('ai-run', '--approved', expected=1)
        self.run_cmd(['git', 'switch', 'feature/test'])
        (self.project / 'unrelated.txt').write_text('human work')
        self.tool('ai-run', '--approved', expected=1)
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())

    def test_runner_completes_dependency_queue_at_exact_session_limit(self):
        self.ready(task('T001') + task('T002', dependencies='T001'))
        self.tool('ai-run', '--approved', '--sessions', '2')
        self.helper('tasks', 'complete')
        self.assertIn('Phase: ready_for_review', (self.project / '.ai/state.md').read_text())
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.helper('stamp', 'verify')
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text().count('call'), 2)
        self.assertIn('runner checkpoint', self.run_cmd(['git', 'log', '--oneline']).stdout)

    def test_runner_no_progress_denial_and_error_stop_without_retry(self):
        for mode in ('no-progress', 'denied', 'error', 'invalid', 'bad-format'):
            with self.subTest(mode=mode):
                if not (self.project / '.ai').exists():
                    self.ready()
                self.tool('ai-run', '--approved', '--sessions', '5', expected=1, MOCK_CLAUDE=mode)
                self.assertFalse((self.project / 'T001.txt').exists())
                (self.project / '.ai/tasks.md').write_text(task('T001'))
                self.commit('reconcile failed run')
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text().count('call'), 5)

    def test_runner_validation_failure_reopens_task(self):
        self.ready()
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nif [[ -e T001.txt ]]; then exit 42; fi\n')
        self.commit('gate fails for invalid fixture implementation')
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='validation-failure')
        self.assertEqual(self.helper('tasks', 'status', 'T001').stdout.strip(), 'IN_PROGRESS')
        self.assertIn('Phase: blocked', (self.project / '.ai/state.md').read_text())
        self.helper('stamp', 'verify', expected=1)

    def test_permission_policy_protects_gate_tools_and_prompts(self):
        deny = json.loads((ROOT / 'templates/.claude/settings.json').read_text())['permissions']['deny']
        for tool in ('Edit', 'Write'):
            for path in ('.ai/bin/**', '.ai/validate', '.ai/prompts/**', '.ai/ci-setup',
                         '.ai/permissions.allow', '.claude/settings.json',
                         '.github/workflows/ai-validate.yml'):
                self.assertIn(f'{tool}({path})', deny)
        for command in ('git commit --no-verify *', 'git commit -n *',
                        'git commit * --no-verify', 'git commit * -n'):
            self.assertIn(f'Bash({command})', deny)

    def test_runner_detects_even_committed_gate_changes_before_untrusted_helpers(self):
        self.ready()
        targets = ('.ai/validate', '.ai/ci-setup', '.github/workflows/ai-validate.yml',
                   '.ai/bin/ai-pipeline', '.ai/prompts/runner.md', '.ai/bin/ai-check', '.ai/bin/lib/workflow.py',
                   '.ai/bin/lib/common.sh', '.ai/bin/ai-run', '.ai/prompts/implement.md',
                   '.ai/permissions.allow', '.claude/settings.json', '.ai/bin/added-tool')
        for target in targets:
            with self.subTest(target=target):
                path = self.project / target
                original = path.read_bytes() if path.exists() else None
                result = self.tool('ai-run', '--approved', expected=1,
                                   MOCK_CLAUDE='tamper', MOCK_TAMPER_PATH=target)
                self.assertIn('Approved workflow gate changed', result.stderr)
                self.assertFalse((self.project / 'UNTRUSTED_HELPER_RAN').exists())
                self.assertFalse((self.project / 'UNTRUSTED_CHECK_RAN').exists())
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
                (self.project / '.ai/tasks.md').write_text(task('T001'))
                self.commit('human restores inspected gate for next probe')
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text().count('call'), len(targets))

    def test_runner_detects_gate_changes_made_by_git_hooks(self):
        self.ready()
        hook = self.project / '.git/hooks/post-commit'
        hook.write_text('#!/usr/bin/env bash\nprintf "changed by hook\\n" >> .ai/prompts/implement.md\n')
        hook.chmod(0o755)
        result = self.tool('ai-run', '--approved', expected=1)
        self.assertIn('Approved workflow gate changed', result.stderr)

    def test_integrity_verifier_cannot_import_project_modules(self):
        self.ready()
        # An unrelated project module must not replace the verifier's hashlib.
        self.tool('ai-run', '--approved', MOCK_CLAUDE='tamper', MOCK_TAMPER_PATH='hashlib.py')
        self.helper('tasks', 'complete')
        digest = (self.project / '.ai/local/approved-gate.sha256').read_text().strip()
        self.assertEqual(len(digest), 64)

    def test_optional_external_knowledge_directory_is_explicit_and_scoped(self):
        self.ready()
        notes = self.base / 'external notes with spaces'
        notes.mkdir()
        self.tool('ai-run', '--approved', '--knowledge-dir', str(notes),
                  MOCK_KNOWLEDGE_DIR=str(notes))
        self.assertEqual(list(notes.iterdir()), [])  # Toolkit never edits notes itself.
        self.helper('tasks', 'complete')
        self.tool('ai-run', '--approved', '--knowledge-dir', str(notes / 'missing'), expected=1)

    def test_repeated_setup_with_toolkit_instructions_needs_no_merge_warning(self):
        self.setup_project()
        result = self.setup_project('--dry-run')
        self.assertNotIn('WARNING: KEEP CLAUDE.md', result.stdout)
        self.assertNotIn('WARNING: KEEP AGENTS.md', result.stdout)

    def test_runner_timeout_keeps_partial_work(self):
        self.ready()
        self.tool('ai-run', '--approved', '--session-timeout', '1', expected=1, MOCK_CLAUDE='timeout')
        self.assertEqual((self.project / 'partial.txt').read_text(), 'interrupted work')
        self.assertIn('stopped', (self.project / '.ai/run-log.md').read_text())

    def test_runner_dirty_output_is_not_auto_staged(self):
        self.ready()
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='dirty')
        self.assertIn('T001.txt', self.run_cmd(['git', 'status', '--porcelain']).stdout)
        self.assertNotIn('T001.txt', self.run_cmd(['git', 'ls-files']).stdout)

    def test_runner_continues_independent_tasks_after_blocker(self):
        self.ready(task('T001') + task('T002', dependencies='T001') + task('T003'))
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='blocked-first')
        self.assertEqual(self.helper('tasks', 'status', 'T001').stdout.strip(), 'BLOCKED')
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.assertEqual(self.helper('tasks', 'status', 'T003').stdout.strip(), 'DONE')

    def test_runner_session_limit_and_resume(self):
        self.ready(task('T001') + task('T002', dependencies='T001'))
        self.tool('ai-run', '--approved', '--sessions', '1', expected=1)
        self.assertEqual(self.helper('tasks', 'status', 'T001').stdout.strip(), 'DONE')
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.commit('checkpoint stopped run')
        self.tool('ai-run', '--approved', '--sessions', '1')
        self.helper('tasks', 'complete')

    def test_git_hooks_are_not_disabled(self):
        self.ready()
        hook = self.project / '.git/hooks/pre-commit'
        hook.write_text('#!/usr/bin/env bash\necho hook-ran >> .ai/local/hook-ran\nexit 0\n')
        hook.chmod(0o755)
        self.tool('ai-run', '--approved')
        self.assertGreaterEqual((self.project / '.ai/local/hook-ran').read_text().count('hook-ran'), 3)

    def test_review_requires_complete_clean_validated_nonempty_range(self):
        self.ready()
        self.tool('ai-review', '--base', 'main', expected=1)
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'HEAD', expected=1)
        self.tool('ai-review', '--base', 'not-a-ref', expected=1)
        (self.project / 'new-source.txt').write_text('changed')
        self.tool('ai-review', '--base', 'main', expected=1)
        self.commit('new source')
        self.tool('ai-review', '--base', 'main', expected=1)
        self.tool('ai-check')
        self.tool('ai-review', '--base', 'main')
        report = (self.project / '.ai/reviews/current.md').read_text()
        self.assertIn(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip(), report)
        self.assertIn('Host evidence', report)

    def test_failed_or_malformed_reviews_preserve_report(self):
        self.ready()
        self.tool('ai-run', '--approved')
        original = (self.project / '.ai/reviews/current.md').read_bytes()
        for mode in ('error', 'empty', 'malformed'):
            with self.subTest(mode=mode):
                self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX=mode)
                self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)

    def test_review_detects_concurrent_checkout_changes(self):
        self.ready()
        self.tool('ai-run', '--approved')
        original = (self.project / '.ai/reviews/current.md').read_bytes()
        self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX='mutates')
        self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)

    def test_checkout_lock_excludes_runner_and_reviewer(self):
        import fcntl
        self.ready()
        self.tool('ai-status')
        with (self.project / '.ai/local/workflow.lock').open('w') as file:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.tool('ai-run', '--approved', expected=1)
            self.tool('ai-review', '--base', 'main', expected=1)
        self.tool('ai-run', '--approved')

    # ---------------------------------------------------------------- pipeline
    def add_origin(self):
        origin = self.base / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(origin)], check=True, env=self.env)
        self.run_cmd(['git', 'remote', 'add', 'origin', str(origin)])
        return origin

    def gh_calls(self):
        log = self.base / 'gh.log'
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def notifications(self):
        return self.notify_log.read_text() if self.notify_log.exists() else ''

    def test_pipeline_clean_review_pushes_and_opens_pr(self):
        self.ready()
        origin = self.add_origin()
        (self.project / '.ai/handoff.md').write_text(
            '# Handoff\n\n## Manual testing for the human\n1. Open the app and check T001.\n')
        self.commit('handoff with test steps')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assertIn('Pull request: https://github.com/example/project/pull/7', result.stdout)
        self.helper('tasks', 'complete')
        branches = subprocess.run(['git', '--git-dir', str(origin), 'branch'], capture_output=True, text=True).stdout
        self.assertIn('feature/test', branches)
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertEqual(len(create), 1)
        self.assertNotIn('--draft', create[0])
        self.assertEqual(create[0][create[0].index('--base') + 1], 'main')
        body = (self.base / 'gh.log.body.md').read_text()
        self.assertIn('[x] T001', body)
        self.assertIn('Open the app and check T001.', body)
        self.assertIn('BLOCKER 0, MAJOR 0', body)
        self.assertIn('Phase: ready_for_acceptance', (self.project / '.ai/state.md').read_text())
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        log = self.run_cmd(['git', 'log', '--oneline']).stdout
        self.assertEqual(log.count('record independent review'), 1)
        self.assertIn('Pipeline started', self.notifications())
        self.assertIn('PR ready for testing: https://github.com/example/project/pull/7', self.notifications())
        self.assertFalse((self.project / '.ai/local/pipeline.active').exists())

    def test_pipeline_fixes_major_findings_then_reviews_again(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='major-once')
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        log = self.run_cmd(['git', 'log', '--oneline']).stdout
        self.assertEqual(log.count('record independent review'), 2)
        self.assertEqual(log.count('record review triage'), 1)
        self.assertIn('| M1 | accepted |', (self.project / '.ai/reviews/dispositions.md').read_text())
        self.assertIn('1 accepted', (self.base / 'gh.log.body.md').read_text())
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertNotIn('--draft', create[0])

    def test_pipeline_opens_draft_when_findings_persist(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--max-fix-rounds', '1',
                  MOCK_CODEX='major-always')
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertIn('--draft', create[0])
        self.assertIn('significant review findings remain', (self.base / 'gh.log.body.md').read_text())
        self.assertIn('Draft PR needs your attention', self.notifications())

    def test_pipeline_rejected_findings_still_open_normal_pr(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main',
                  MOCK_CODEX='major-always', MOCK_CLAUDE='triage-reject')
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertNotIn('--draft', create[0])
        self.assertIn('| M1 | rejected |', (self.project / '.ai/reviews/dispositions.md').read_text())

    def test_pipeline_rerun_updates_existing_pr_without_new_review(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_GH_EXISTING='1')
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), 1)
        self.assertTrue(any(c[:2] == ['pr', 'edit'] for c in self.gh_calls()))

    def test_pipeline_without_remote_or_pr_reports_ready(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assertIn("no 'origin' remote", self.notifications())
        self.assertEqual(self.gh_calls(), [])

    def test_pipeline_stop_is_notified(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, MOCK_CLAUDE='error')
        self.assertIn('Pipeline stopped during implementation', self.notifications())
        # A reported stop removes the liveness marker: the watchdog reports the stop, not a crash.
        self.assertFalse((self.project / '.ai/local/pipeline.active').exists())
        self.tool('ai-watchdog', expected=1)
        self.assertNotIn('gone without finishing', self.notifications())
        self.assertNotIn('stalled', self.notifications())
        self.assertIn('Watchdog: stopped:', self.notifications())
        self.tool('ai-pipeline', '--approved', '--base', 'not-a-ref', expected=1)
        self.run_cmd(['git', 'switch', 'main'])
        self.tool('ai-pipeline', '--approved', expected=1)

    # ---------------------------------------------------------------- limits, models, triage, config
    def test_worked_around_denials_and_bookkeeping_leftovers_do_not_stop_the_run(self):
        self.ready()
        self.tool('ai-run', '--approved', MOCK_CLAUDE='denied-but-done')
        self.helper('tasks', 'complete')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.assertIn('| claude | T001 |', self.run_cmd(['git', 'show', 'HEAD~1:.ai/run-log.md'], expected=None).stdout +
                      (self.project / '.ai/run-log.md').read_text())
        self.assertEqual((self.project / '.ai/local/denials.log').read_text().count('cat > greet.py'), 1)

    def test_claude_usage_limit_pauses_then_resumes(self):
        self.ready()
        self.tool('ai-run', '--approved', MOCK_CLAUDE='limit-once')
        self.helper('tasks', 'complete')
        waited = int((self.base / 'sleep.log').read_text().split()[0])
        self.assertTrue(150 <= waited <= 200, waited)  # "try again in 2 minutes" + 60s buffer
        self.assertIn('Paused: Claude usage limit', self.notifications())
        self.assertIn('Claude usage limit', (self.project / '.ai/local/pauses.log').read_text())

    def test_usage_limit_beyond_wait_budget_stops(self):
        self.ready()
        result = self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='limit-far', AI_LIMIT_MAX_WAIT='3600')
        self.assertIn('wait budget', result.stderr)
        self.assertFalse((self.base / 'sleep.log').exists())
        self.assertIn('Runner stopped', self.notifications())

    def test_codex_usage_limit_pauses_then_retries(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='limit-once')
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), 2)
        self.assertIn('Paused: Codex usage limit', self.notifications())
        self.assertIn('Host evidence', (self.project / '.ai/reviews/current.md').read_text())

    def test_task_model_line_overrides_run_model(self):
        self.ready(task('T001').replace('Dependencies: none', 'Dependencies: none\nModel: sonnet') +
                   task('T002', dependencies='T001'))
        self.tool('ai-run', '--approved', '--model', 'opus')
        calls = (self.project / '.ai/local/mock-args').read_text().splitlines()
        self.assertIn('--model sonnet', calls[0])
        self.assertIn('--model opus', calls[1])
        self.tool('ai-run', '--approved', '--model', 'bad model', expected=1)
        (self.project / '.ai/tasks.md').write_text(task('T001').replace('Dependencies: none', 'Dependencies: none\nModel: a b'))
        self.helper('tasks', 'check', expected=1)

    def test_triage_may_only_change_workflow_records(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-always')
        self.commit('record review')
        result = self.tool('ai-run', '--approved', '--triage', expected=1, MOCK_CLAUDE='triage-touches-source')
        self.assertIn('outside workflow records', result.stderr)

    def test_user_config_file_supplies_notify_command_only_for_known_keys(self):
        self.ready()
        out = self.base / 'from-config.log'
        cfg = self.config / 'ai-toolkit'
        cfg.mkdir()
        (cfg / 'config').write_text(f'AI_NOTIFY_CMD="echo \\"$1\\" >> {out}"\nPATH=/nowhere\nAI_UNKNOWN=1\n')
        env = {k: v for k, v in self.env.items() if k != 'AI_NOTIFY_CMD'}
        result = self.run_cmd([str(self.project / '.ai/bin/ai-run'), '--approved'], env=env)
        self.assertIn('ready for independent review', out.read_text())
        self.assertEqual(result.returncode, 0)

    def test_reset_time_parsing(self):
        import importlib.util
        from datetime import datetime
        spec = importlib.util.spec_from_file_location('workflow', HELPER)
        wf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wf)
        ref = datetime(2026, 10, 4, 15, 30).astimezone()
        base = int(ref.timestamp())
        self.assertEqual(wf.parse_reset('limit reached|1791134319', ref), 1791134319)
        self.assertEqual(wf.parse_reset('Rate limit. Try again in 2h 13m.', ref), base + 7980)
        self.assertEqual(datetime.fromtimestamp(wf.parse_reset("hit your limit · resets 7pm", ref)).hour, 19)
        self.assertEqual(datetime.fromtimestamp(wf.parse_reset('resets at 3:05 PM', ref)).day, 5)
        self.assertEqual(wf.parse_reset('usage limit, no time given', ref), 0)
        self.assertIsNone(wf.LIMIT_TEXT.search('Error: unrelated failure'))

    # ---------------------------------------------------------------- review-integrity fixes (Codex review of the pipeline)
    def test_review_counts_must_match_listed_findings(self):
        self.ready()
        self.tool('ai-run', '--approved')
        original = (self.project / '.ai/reviews/current.md').read_bytes()
        result = self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX='counts-lie')
        self.assertIn('counts MAJOR=0', result.stderr)
        self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)

    def test_no_claude_session_may_rewrite_the_codex_review(self):
        self.ready()
        self.add_origin()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1,
                           MOCK_CODEX='major-always', MOCK_CLAUDE='triage-rewrites-review')
        self.assertIn('modified .ai/reviews/current.md', result.stderr)
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ['pr', 'create']], [])

    def test_deferred_finding_makes_the_pr_a_draft(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='major-always', MOCK_CLAUDE='triage-defer')
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertIn('--draft', create[0])
        self.assertIn('1 deferred', (self.base / 'gh.log.body.md').read_text())

    def test_missing_disposition_stops_the_pipeline(self):
        self.ready()
        self.add_origin()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1,
                           MOCK_CODEX='major-always', MOCK_CLAUDE='triage-missing')
        self.assertIn('Triage incomplete', result.stderr)
        self.assertIn('Pipeline stopped during triage', self.notifications())

    def test_rerun_reuses_completed_rejection_triage(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='major-always', MOCK_CLAUDE='triage-reject')
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='major-always',
                  MOCK_CLAUDE='triage-reject', MOCK_GH_EXISTING='1')
        log = self.run_cmd(['git', 'log', '--oneline']).stdout
        self.assertEqual(log.count('triage review'), 1)
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), 1)

    def test_existing_ready_pr_is_converted_to_draft(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--draft', MOCK_GH_EXISTING='1')
        self.assertIn(['pr', 'ready', '--undo', 'feature/test'], self.gh_calls())

    def test_current_review_still_requires_fresh_validation(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        (self.project / '.ai/local/validation.json').unlink()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('== Validation ==', result.stdout)
        self.helper('stamp', 'verify')
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), 1)

    def test_pipeline_holds_the_shared_checkout_lock(self):
        import fcntl
        self.ready()
        self.tool('ai-status')
        with (self.project / '.ai/local/workflow.lock').open('w') as file:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
            self.assertIn('Another runner/reviewer owns this checkout', result.stderr)
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())

    def test_hook_on_host_review_commit_cannot_run_modified_helper(self):
        self.ready()
        hook = self.project / '.git/hooks/post-commit'
        hook.write_text('#!/usr/bin/env bash\n'
                        'if [[ "$(git log -1 --format=%s)" == "chore(ai): record independent review" ]]; then\n'
                        '  printf "from pathlib import Path\\nPath(\'UNTRUSTED_HELPER_RAN\').touch()\\n" > .ai/bin/lib/workflow.py\n'
                        'fi\n')
        hook.chmod(0o755)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertIn('Approved workflow gate changed', result.stderr)
        self.assertFalse((self.project / 'UNTRUSTED_HELPER_RAN').exists())

    def test_pr_base_follows_the_review_base_or_must_be_explicit(self):
        self.ready()
        origin = self.add_origin()
        self.run_cmd(['git', 'push', '-q', 'origin', 'main:develop'])
        self.run_cmd(['git', 'fetch', '-q', 'origin'])
        sha = self.run_cmd(['git', 'rev-parse', 'main']).stdout.strip()
        result = self.tool('ai-pipeline', '--approved', '--base', sha, expected=1)
        self.assertIn('--pr-base', result.stderr)
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        self.tool('ai-pipeline', '--approved', '--base', 'origin/develop')
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']][0]
        self.assertEqual(create[create.index('--base') + 1], 'develop')
        self.assertTrue(origin.exists())

    def test_failed_final_push_is_reported_not_hidden(self):
        self.ready()
        self.add_origin()
        hook = self.project / '.git/hooks/pre-push'
        hook.write_text('#!/usr/bin/env bash\n[[ "$(git log -1 --format=%s)" != "chore(ai): record pull request" ]]\n')
        hook.chmod(0o755)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('final push failed', result.stderr)
        self.assertIn('final handoff commit failed', self.notifications())

    # ---------------------------------------------------------------- follow-up review fixes
    def test_forged_committed_review_is_rejected_on_resume_and_reviewed_again(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-always',
                  MOCK_CLAUDE='triage-reject')
        review = self.project / '.ai/reviews/current.md'
        review.write_text(review.read_text().replace('one major finding', 'all good'))
        self.commit('a session "fixes" the review text')
        self.helper('review-info', expected=1)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CLAUDE='triage-reject')
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), 2)
        self.helper('review-info')

    def test_push_hook_cannot_run_a_modified_helper(self):
        self.ready()
        self.add_origin()
        hook = self.project / '.git/hooks/pre-push'
        hook.write_text('#!/usr/bin/env bash\n'
                        'printf "from pathlib import Path\\nPath(\'UNTRUSTED_HELPER_RAN\').touch()\\n" > .ai/bin/lib/workflow.py\n')
        hook.chmod(0o755)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('Approved workflow gate changed', result.stderr)
        self.assertFalse((self.project / 'UNTRUSTED_HELPER_RAN').exists())
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ['pr', 'create']], [])

    def test_push_hook_cannot_alter_the_review_that_gets_published(self):
        self.ready()
        self.add_origin()
        hook = self.project / '.git/hooks/pre-push'
        hook.write_text('#!/usr/bin/env bash\nsed -i "s/no demonstrated findings/flawless/" .ai/reviews/current.md\n')
        hook.chmod(0o755)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('does not match the report ai-review published', result.stderr)
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ['pr', 'create']], [])

    def test_accepted_finding_must_point_to_a_new_fix_task(self):
        self.ready()
        self.add_origin()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1,
                           MOCK_CODEX='major-always', MOCK_CLAUDE='triage-accept-done')
        self.assertIn('Triage incomplete', result.stderr)

    def test_failed_draft_conversion_stops(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--draft', expected=1,
                           MOCK_GH_EXISTING='1', MOCK_GH_READY_FAIL='1')
        self.assertIn('could not convert the existing PR to draft', result.stderr)
        self.assertNotIn('Draft PR needs your attention', self.notifications())

    def test_interrupted_triage_resumes_after_dispositions_were_opened(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-always')
        self.commit('record review')
        self.tool('ai-run', '--approved', '--triage', expected=1, MOCK_CLAUDE='limit-far', AI_LIMIT_MAX_WAIT='60')
        self.assertIn('open review dispositions', self.run_cmd(['git', 'log', '--oneline']).stdout)
        self.commit('checkpoint the interrupted triage') if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip() else None
        self.tool('ai-run', '--approved', '--triage')
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')

    def test_minor_count_must_match_listed_ids(self):
        self.setup_project()
        report = self.base / 'report.md'
        report.write_text('# Independent review\nOverall verdict: minor issues\n'
                          'Finding counts: BLOCKER=0 MAJOR=0 MINOR=2\n## BLOCKER findings\nNone found.\n'
                          '## MAJOR findings\nNone found.\n## MINOR findings\n- N1: one issue only.\n'
                          '## Missing test coverage\nx\n## Security concerns\nx\n## Architecture concerns\nx\n'
                          '## Manual testing recommendations\nx\n')
        self.commit('fixture')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        result = self.helper('publish-review', str(report), head, head, expected=1)
        self.assertIn('MINOR=2', result.stderr)

    def test_deferral_in_an_earlier_round_does_not_draft_a_clean_final_review(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='two-major-once', MOCK_CLAUDE='triage-mixed')
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertNotIn('--draft', create[0])
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')


if __name__ == '__main__':
    unittest.main()
