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
if 'RECOVERY CONTRACT' in prompt:
    assert args[args.index('--tools')+1] == 'Read,Glob,Grep'
    state = pathlib.Path(os.environ['MOCK_STATE_DIR'])
    with open(state / 'recover-calls', 'a') as f: f.write(prompt.split('RECOVERY CONTRACT')[1][:400].replace('\n', ' ') + '\n')
    decision = {'action': os.environ.get('MOCK_RECOVER', 'rerun'), 'reason': 'the session crashed once.',
                'human_action': 'look at T001 yourself'}
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                      'result': json.dumps(decision)}))
    sys.exit(0)
assert 'RUNNER CONTRACT' in prompt or 'TRIAGE CONTRACT' in prompt
assert 'TRIAGE CONTRACT' in prompt or 'never prefix commands with `cd`' in prompt
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
if os.environ.get('MOCK_REQUIRE'):  # e.g. dependencies the host installs before a session
    assert pathlib.Path(os.environ['MOCK_REQUIRE']).exists(), 'missing ' + os.environ['MOCK_REQUIRE']
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
    with open(pathlib.Path(os.environ['MOCK_STATE_DIR']) / 'triage-calls', 'a') as f: f.write('call\n')
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
                             if mode == 'triage-mixed' else '')
                          + ('| M2 | rejected | the second defect is handled by the gate | none |\n'
                             if mode == 'triage-mixed-reject' else ''))
        paths = ['.ai/tasks.md', '.ai/reviews/dispositions.md']
        if mode == 'triage-touches-source':
            pathlib.Path('src.txt').write_text('not allowed in triage')
            paths.append('src.txt')
        if mode == 'triage-no-commit-source':
            pathlib.Path('src.txt').write_text('not allowed in triage')
        subprocess.run(['git','add','--',*paths],check=True)
    # The 2026-10-05 case: the session's own commit was denied; its records stay uncommitted.
    if mode not in ('triage-no-commit', 'triage-no-commit-source'):
        subprocess.run(['git','commit','-qm',os.environ.get('MOCK_TRIAGE_SUBJECT', 'triage review')],check=True)
    if mode == 'triage-crash':
        # The machine "restarts": ai-run (claude <- timeout <- ai-run) and the pipeline die at once.
        runner = int(pathlib.Path(f'/proc/{os.getppid()}/stat').read_text().rsplit(')', 1)[1].split()[1])
        os.kill(runner, 9)
        os.kill(int(pathlib.Path('.ai/local/pipeline.active').read_text()), 9)
    print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[]}))
    sys.exit(0)
if mode in ('error-once', 'error-once-partial') and not pathlib.Path('.ai/local/mock-error-hit').exists():
    pathlib.Path('.ai/local/mock-error-hit').touch()
    if mode == 'error-once-partial':
        pathlib.Path('partial.txt').write_text('finished work the session never committed')
        if os.environ.get('MOCK_EXTRA_FILE'):
            pathlib.Path(os.environ['MOCK_EXTRA_FILE']).write_text('not in the plan')
    print(json.dumps({'type':'result','subtype':'error','is_error':True}))
    sys.exit(0)
if mode in ('error-once', 'error-once-partial'):
    mode = 'success'
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
    if mode == 'dirty-secret':
        pathlib.Path('deploy.pem').write_text('-----BEGIN PRIVATE KEY-----')
    if mode not in ('dirty', 'dirty-secret'):
        subprocess.run(['git','add','--','.ai/tasks.md','.ai/state.md',task_id+'.txt','.ai/validate'],check=True)
        if mode == 'tamper':
            subprocess.run(['git','add','--',os.environ['MOCK_TAMPER_PATH']],check=True)
        if mode == 'exec-committed-644':
            # Executable on disk, committed as 100644 (unseen with core.filemode=false).
            pathlib.Path(task_id + '.txt').chmod(0o755)
            subprocess.run(['git','update-index','--chmod=-x','--',task_id+'.txt'],check=True)
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
state = pathlib.Path(os.environ.get('MOCK_STATE_DIR', '.'))
with open(state / 'codex-args.log', 'a') as log: log.write(' '.join(args[:-1]) + '\n')
if 'Diagnose this workflow incident' in args[-1]:
    path = pathlib.Path(args[args.index('--output-last-message')+1])
    path.write_text('Codex: the runner was killed.\nEvidence follows.')
    sys.exit(0)
if 'RECHECK SCOPE' in args[-1]:
    with open(state / 'codex-recheck-calls', 'a') as f: f.write(args[-1].split('RECHECK SCOPE')[1] + '\n')
    if os.environ.get('MOCK_RECHECK_FAIL'): sys.exit(17)
    pathlib.Path(args[args.index('--output-last-message')+1]).write_text(
        os.environ.get('MOCK_RECHECK', '{"answers": [{"id": "M1", "verdict": "upheld", "reason": "still broken"}]}'))
    sys.exit(0)
if 'PLAN SCOPE' in args[-1]:
    with open(state / 'codex-plan-calls', 'a') as f: f.write('call\n')
    major = os.environ.get('MOCK_CODEX_PLAN') == 'major'
    pathlib.Path(args[args.index('--output-last-message')+1]).write_text(
        '# Plan review\nOverall verdict: ' + ('gap' if major else 'ok') + '\n'
        'Finding counts: BLOCKER=0 MAJOR=' + ('1' if major else '0') + ' MINOR=0\n'
        '## BLOCKER findings\nNone.\n## MAJOR findings\n' + ('- P1: T001 has no test.\n' if major else 'None.\n') +
        '## MINOR findings\nNone.\n')
    sys.exit(0)
mode = os.environ.get('MOCK_CODEX', 'success')
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

# .ai/ci-setup fixture for the host dependency step; MOCK_DEPS picks a misbehaviour.
DEPS_SETUP = r'''#!/usr/bin/env bash
# ai-deps-inputs: deps.lock
# ai-deps-outputs: vendor-deps
set -euo pipefail
printf 'call\n' >> "$MOCK_STATE_DIR/deps-calls"
first=no
[[ -e "$MOCK_STATE_DIR/deps-once" ]] || { first=yes; touch "$MOCK_STATE_DIR/deps-once"; }
case "${MOCK_DEPS:-ok}" in
  fail) exit 1 ;;
  fail-once) [[ $first == no ]] || exit 1 ;;
  sleep) sleep 60 ;;
  overwrite) echo changed >> tracked.txt ;;
  overwrite-fail) echo changed >> tracked.txt; exit 1 ;;
  change-once) [[ $first == no ]] || echo changed >> tracked.txt ;;
  fail-later) [[ $first == yes ]] || exit 1 ;;
  change-later) [[ $first == yes ]] || echo changed >> tracked.txt ;;
  untracked) echo new > new.txt ;;
  commit) echo changed >> tracked.txt; git commit -qam 'installer commit' ;;
esac
mkdir -p vendor-deps
cp deps.lock vendor-deps/
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
        for name in ('AI_PIPELINE', 'AI_LOCK_HELD', 'AI_RECOVERY_ATTEMPT', 'AI_SETTINGS_FROM_MANIFEST',
                     'AI_DISPUTES_BASE'):
            # set when the gate runs inside a pipeline (or one resumed by ai-recover)
            self.env.pop(name, None)
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
        self.env['AI_AUTO_RECOVER'] = '0'  # recovery has its own tests
        self.env['XDG_DATA_HOME'] = str(self.base / 'xdg-data')
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

    def watchdog(self, *args, expected=0, **env):
        return self.tool('ai-watchdog', *args, expected=expected, **env)

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
        self.watchdog('--diagnose', '--diagnosis-agent', 'claude', expected=1)
        self.watchdog('--diagnose', '--diagnosis-agent', 'claude', expected=1)
        self.assertEqual((self.base / 'diagnosis-calls').read_text().count('call'), 1)
        self.assertIn('Runner stopped after a failed check.', self.notifications())
        self.assertIn('Inspect validation evidence.', (self.project / '.ai/local/diagnosis.md').read_text())
        error.write_text('another stop')
        self.watchdog('--diagnose', '--diagnosis-agent', 'claude', expected=1)
        self.assertEqual((self.base / 'diagnosis-calls').read_text().count('call'), 2)

    def test_watchdog_diagnosis_failure_is_not_retried_and_usage(self):
        self.setup_project()
        self.watchdog('--stale-minutes', '0', expected=2)
        self.watchdog('--unknown', expected=2)
        self.watchdog_phase('implementing')
        (self.mock_bin / 'claude').write_text('#!/usr/bin/env bash\nexit 17\n')
        self.watchdog('--diagnose', '--diagnosis-agent', 'claude', expected=1)
        self.watchdog('--diagnose', '--diagnosis-agent', 'claude', expected=1)
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
        self.assertIn('⚠ HUNG?', self.notifications())

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

    def test_watchdog_finished_pipeline_is_not_a_crash(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('watchdog', ROOT / 'scripts/lib/watchdog.py')
        watchdog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watchdog)
        marker = self.base / 'pipeline.active'
        dead = subprocess.Popen(['true'])
        dead.wait()
        marker.write_text(f'{dead.pid}\n')
        self.assertTrue(watchdog.pipeline_died(marker))
        snapshot = watchdog.marker_snapshot
        def finishing(path):
            result = snapshot(path)
            path.unlink(missing_ok=True)  # the pipeline finishes mid-probe
            return result
        watchdog.marker_snapshot = finishing
        self.assertEqual(watchdog.pipeline_died(marker), 0)

    def test_watchdog_resumed_run_ignores_old_logs(self):
        import time
        self.setup_project()
        old = time.time() - 7200
        for path in (self.project / '.ai/run-log.md', self.project / '.ai'):
            os.utime(path, (old, old))
        self.watchdog_runner()
        self.watchdog()  # just started: not hung despite 2-hour-old logs
        self.assertEqual(self.notifications(), '')

    def test_watchdog_diagnosis_defaults_to_codex(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        self.watchdog('--diagnose', expected=1)
        self.assertIn('Codex: the runner was killed.', self.notifications())
        self.assertIn('Evidence follows.', (self.project / '.ai/local/diagnosis.md').read_text())
        self.assertIn('--sandbox read-only', (self.base / 'codex-args.log').read_text())
        self.assertEqual(list((self.project / '.ai/local').glob('.diagnosis-*')), [])

    def host_watchdog(self, *args, expected=0, **env):
        # What --install-timer runs: a copy of .ai/bin outside the checkout.
        import shutil
        host = self.base / 'host-bin'
        if not host.exists():
            shutil.copytree(self.project / '.ai/bin', host)
        return self.run_cmd([str(host / 'ai-watchdog'), str(self.project), *args], expected=expected,
                            env=dict(self.env, **env))

    def approve_run(self):
        digest = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.helper('run-manifest', 'start', digest, 'main', '--approved')

    def crashed_marker(self):
        marker = self.project / '.ai/local/pipeline.active'
        marker.parent.mkdir(exist_ok=True)
        dead = subprocess.Popen(['true'])
        dead.wait()
        marker.write_text(f'{dead.pid}\n')
        return marker

    def mock_systemd_run(self, takes_over=True):
        (self.mock_bin / 'systemd-run').write_text(
            '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_STATE_DIR/systemd-run.log"\n'
            + ('printf "4242\\n" > .ai/local/pipeline.active\n' if takes_over else ''))
        (self.mock_bin / 'systemd-run').chmod(0o755)

    def test_watchdog_recover_starts_ai_recover_after_a_crash(self):
        self.setup_project()
        self.commit('bootstrap')
        self.approve_run()
        self.mock_systemd_run()
        self.crashed_marker()
        self.host_watchdog('--recover', expected=1, AI_AUTO_RECOVER='1', AI_NOTIFY_CMD='true')
        self.watchdog('--recover', expected=1)  # from the checkout: refused, the human is told
        launched = (self.base / 'systemd-run.log').read_text()
        self.assertIn('--user --collect --quiet --service-type=exec', launched)
        self.assertIn('--setenv=AI_STATE_DIR=', launched)
        self.assertNotIn('AI_WATCHDOG_NOW', launched)
        self.assertIn(str(self.project / '.ai/bin/ai-recover') + ' --stage crash', launched)
        self.assertIn('killed', (self.project / '.ai/local/last-error').read_text())
        # Only the checkout run (refused) spoke; the host run handed over silently.
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.assertIn('only runs from the installed timer', self.notifications())

    def test_watchdog_recover_refuses_changed_gate_and_reports_unconfirmed_launch(self):
        self.setup_project()
        self.commit('bootstrap')
        self.approve_run()
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nexit 0\n')
        self.mock_systemd_run()
        self.crashed_marker()
        self.host_watchdog('--recover', expected=1, AI_AUTO_RECOVER='1')
        self.assertFalse((self.base / 'systemd-run.log').exists())
        self.assertIn('⛔ STOPPED, needs you', self.notifications())
        self.assertIn('auto-recovery refused: gate files changed', self.notifications())
        self.approve_run()
        self.mock_systemd_run(takes_over=False)
        self.crashed_marker()
        self.host_watchdog('--recover', expected=1, AI_AUTO_RECOVER='1', AI_RECOVER_ACK_SECONDS='1')
        self.assertIn('did not confirm it started', self.notifications())

    def test_watchdog_reports_unannounced_stops(self):
        self.setup_project()
        error = self.project / '.ai/local/last-error'
        error.parent.mkdir(exist_ok=True)
        error.write_text('Codex failed; prior review preserved.')
        self.watchdog(expected=1)
        self.assertIn('⛔ STOPPED, needs you: Stopped: Codex failed', self.notifications())

    def test_committed_mode_must_match_validated_file(self):
        self.ready()
        self.run_cmd(['git', 'config', 'core.filemode', 'false'])
        hook = self.project / '.git/hooks/pre-commit'
        hook.write_text('#!/usr/bin/env bash\n'
                        'git diff --cached --name-only | grep -q T001.txt || exit 0\n'
                        'git update-index --chmod=+x T001.txt\n')
        hook.chmod(0o755)
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='dirty')
        self.assertIn('differs from the validated content', (self.project / '.ai/local/last-error').read_text())

    def test_watchdog_waits_for_a_live_runner_before_reporting_a_stop(self):
        self.setup_project()
        error = self.project / '.ai/local/last-error'
        error.parent.mkdir(exist_ok=True)
        error.write_text('stopped during review')
        runner = self.watchdog_runner()
        self.watchdog()  # still running (e.g. recovery deciding): nothing to report yet
        self.assertEqual(self.notifications(), '')
        runner.kill()
        runner.wait()
        self.watchdog(expected=1)
        self.assertIn('⛔ STOPPED, needs you: Stopped: stopped during review', self.notifications())

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
        host = self.base / 'xdg-data/ai-toolkit/watchdog' / units[0].stem
        self.assertIn('"' + str(host / 'bin/ai-watchdog') + '"', exec_start)
        self.assertTrue((host / 'bin/lib/common.sh').is_file())
        self.assertIn('"--stale-minutes" "90" "--diagnose"', exec_start)
        self.assertIn('SuccessExitStatus=1', service)
        self.assertIn('Unit=' + units[0].name, units[1].read_text())
        calls = (self.base / 'systemctl.log').read_text().splitlines()
        self.assertEqual(calls, ['--user daemon-reload', '--user enable --now ' + units[1].name])
        self.watchdog('--uninstall-timer')
        self.assertEqual(list((self.config / 'systemd/user').iterdir()), [])
        self.assertFalse(host.exists())
        self.assertIn('--user disable --now ' + units[1].name, (self.base / 'systemctl.log').read_text())
        self.watchdog('--install-timer', '--uninstall-timer', expected=2)
        self.watchdog('--install-timer')
        (self.mock_bin / 'systemctl').write_text('#!/usr/bin/env bash\n[[ "$2" != disable ]]\n')
        self.watchdog('--uninstall-timer', expected=1)
        self.assertEqual(len(list((self.config / 'systemd/user').iterdir())), 2)

    def assert_install(self, cwd, expected, **env):
        # Installs the timer for self.project while the caller's directory is cwd.
        (self.mock_bin / 'systemctl').write_text(
            '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_STATE_DIR/systemctl.log"\n')
        (self.mock_bin / 'systemctl').chmod(0o755)
        result = subprocess.run([str(self.project / '.ai/bin/ai-watchdog'), str(self.project), '--install-timer'],
                                cwd=cwd, env=dict(self.env, **env), capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        units = self.config / 'systemd/user'
        hosts = self.base / 'xdg-data/ai-toolkit/watchdog'
        if expected:
            self.assertFalse(units.exists() and any(units.iterdir()), result.stderr)
            self.assertFalse(hosts.exists() and any(hosts.iterdir()), result.stderr)
            self.assertFalse((self.base / 'systemctl.log').exists())
        else:
            self.assertEqual(len(list(units.iterdir())), 2)
            self.watchdog('--uninstall-timer')
            (self.base / 'systemctl.log').unlink()
        return result.stderr

    def test_watchdog_host_root_install_checks_the_target_checkout(self):
        self.setup_project()
        inside = str(self.project / '.ai/local/state')
        plain = self.base / 'plain'
        plain.mkdir()
        other = self.base / 'other checkout'
        other.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(other)], check=True, env=self.env)
        for cwd in (plain, other):
            with self.subTest(cwd=cwd.name):
                error = self.assert_install(cwd, 2, AI_STATE_DIR=inside)
                self.assertIn('Host state directory ' + inside, error)
                self.assertIn('overlaps the checkout ' + str(self.project), error)
                self.assert_install(cwd, 0)  # control: safe state dir
        link = self.base / 'data-link'
        link.symlink_to(self.project / '.ai/local')
        for data in (str(self.project / '.ai/local/data'), str(link)):
            with self.subTest(data=data):
                error = self.assert_install(plain, 2, XDG_DATA_HOME=data)
                self.assertIn('overlaps the checkout', error)
                self.assertFalse((self.project / '.ai/local/ai-toolkit').exists())
        self.assertIn('XDG_DATA_HOME must be an absolute path',
                      self.assert_install(plain, 2, XDG_DATA_HOME='relative/data'))
        self.assertFalse((plain / 'relative').exists())

    def test_watchdog_host_root_recovery_refuses_a_state_dir_in_the_checkout(self):
        self.setup_project()
        self.commit('bootstrap')
        self.approve_run()
        self.mock_systemd_run()
        self.crashed_marker()
        self.host_watchdog('--recover', expected=1, AI_AUTO_RECOVER='1',
                           AI_STATE_DIR=str(self.project / '.ai/local/state'))
        notified = self.notifications().splitlines()
        self.assertEqual(len(notified), 1)
        self.assertIn('auto-recovery refused: Host state directory', notified[0])
        self.assertIn('overlaps the checkout', notified[0])
        self.assertFalse((self.base / 'systemd-run.log').exists())
        self.assertFalse((self.base / 'recover-calls').exists())

    def test_watchdog_diagnosis_timeout_and_concurrent_dedupe(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        (self.mock_bin / 'claude').write_text(
            '#!/usr/bin/env bash\nprintf "call\\n" >> "$MOCK_STATE_DIR/timeout-calls"\nsleep 30\n')
        command = [str(self.project / '.ai/bin/ai-watchdog'), '--diagnose', '--diagnosis-timeout', '1', '--diagnosis-agent', 'claude']
        first = subprocess.Popen(command, cwd=self.project, env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.watchdog('--diagnose', '--diagnosis-timeout', '1', '--diagnosis-agent', 'claude', expected=1)
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

    def permissions_template_entries(self):
        text = (ROOT / 'templates/.ai/permissions.allow').read_text()
        return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]

    def prompt_section(self, name):
        text = (ROOT / f'templates/.ai/prompts/{name}.md').read_text()
        self.assertIn('\n## How to work here\n', text)
        return text.split('\n## How to work here\n', 1)[1]

    def test_tool_contract_section_is_shared_by_prompts(self):
        runner = self.prompt_section('runner')
        self.assertEqual(runner, self.prompt_section('triage'))
        self.assertIn('.ai/bin/ai-task', runner)
        self.assertIn('never prefix commands with `cd`', runner)
        self.assertIn('never prefix commands with `cd`', self.prompt_section('recover'))
        self.assertNotIn('never prefix commands with cd (', (ROOT / 'scripts/ai-run').read_text())

    def test_tool_contract_setup_installs_ai_task(self):
        self.setup_project()
        self.assertTrue((self.project / '.ai/bin/ai-task').is_file())
        self.assertTrue(os.access(self.project / '.ai/bin/ai-task', os.X_OK))

    def test_tool_contract_ai_task_set_and_show(self):
        self.setup_project()
        (self.project / '.ai/tasks.md').write_text(
            task('T001', 'DONE').replace('Dependencies: none', 'Dependencies: none\nModel: sonnet')
            + task('T002', 'TODO', 'T001'))
        ai_task = str(self.project / '.ai/bin/ai-task')
        shown = self.run_cmd([ai_task, 'show', 'T001']).stdout
        for text in ('Status: DONE', 'Model: sonnet', 'Dependencies: none'):
            self.assertIn(text, shown)
        shown = self.run_cmd([ai_task, 'show', 'T002']).stdout
        for text in ('Status: TODO', 'Dependencies: T001'):
            self.assertIn(text, shown)
        self.run_cmd([ai_task, 'set', 'T002', 'IN_PROGRESS'])
        self.assertIn('Status: IN_PROGRESS', self.run_cmd([ai_task, 'show', 'T002']).stdout)
        self.assertIn('Status: DONE', self.run_cmd([ai_task, 'show', 'T001']).stdout)
        self.run_cmd([ai_task, 'set', 'T002', 'FINISHED'], expected=1)
        self.run_cmd([ai_task, 'set', 'T009', 'DONE'], expected=1)
        self.run_cmd([ai_task, 'show', 'T009'], expected=1)
        self.run_cmd([ai_task, 'bogus'], expected=2)

    def test_template_rules_b6_model_selection_in_claude_and_plan(self):
        for name in ('CLAUDE.md', '.ai/prompts/plan.md'):
            with self.subTest(file=name):
                text = (ROOT / 'templates' / name).read_text()
                self.assertIn('A task whose own earlier attempt failed validation or review', text)
                self.assertIn('review-fix tasks get a model by their own risk', text)
                self.assertNotIn('any task that already failed review or validation once', text)

    def test_template_rules_b6_model_in_plan_review(self):
        text = (ROOT / 'templates/.ai/prompts/plan-review.md').read_text()
        self.assertIn('a task whose own failed attempt is marked for retry', text)
        self.assertIn('is a MAJOR finding', text)

    def test_template_rules_r6_human_todo_in_runner_and_triage(self):
        for name in ('runner', 'triage'):
            with self.subTest(prompt=name):
                section = self.prompt_section(name)
                self.assertIn('Never tick or untick checkboxes', section)
                self.assertIn('knowledge base', section)
                self.assertIn('Append dated progress', section)

    def test_permissions_template_allows_read_only_shell_and_task_helper(self):
        entries = self.permissions_template_entries()
        for entry in ('Bash(ls)', 'Bash(ls *)', 'Bash(grep *)', 'Bash(cat *)', 'Bash(head *)',
                      'Bash(tail *)', 'Bash(wc *)', 'Bash(echo *)', 'Bash(git rm *)',
                      'Bash(git mv *)', 'Bash(.ai/bin/ai-task *)'):
            self.assertIn(entry, entries)
        self.assertNotIn('Bash', entries)
        self.assertNotIn('Bash(*)', entries)

    def test_permissions_template_excludes_network_installs_and_writers(self):
        commands = [entry[5:-1] for entry in self.permissions_template_entries() if entry.startswith('Bash(')]
        self.assertTrue(commands)
        programs = ('curl', 'wget', 'ssh', 'scp', 'rm', 'sed', 'rg', 'find', 'xargs', 'chmod',
                    'sudo', 'sh', 'python', 'python3')
        phrases = ('npm install', 'npm i ', 'pip install', 'git push', 'git reset --hard', 'bash -c')
        for command in commands:
            with self.subTest(command=command):
                self.assertNotIn(command.split()[0], programs)
                for phrase in phrases:
                    self.assertNotIn(phrase, command + ' ')

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

    def assert_state_root_refused(self, state, message, *args):
        for tool in ('ai-run', 'ai-pipeline'):
            extra = ('--base', 'main', '--no-pr') if tool == 'ai-pipeline' else ()
            result = self.tool(tool, '--approved', *extra, *args, expected=1, AI_STATE_DIR=str(state))
            self.assertIn(message, result.stderr)
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        for name in ('codex-calls', 'codex-plan-calls'):
            self.assertFalse((self.base / name).exists())

    def test_state_root_inside_checkout_is_refused_before_any_agent(self):
        self.ready()
        state = self.project / 'host state'
        self.assert_state_root_refused(state, 'overlaps the checkout')
        self.assertFalse(state.exists())
        self.assert_state_root_refused(self.project, 'overlaps the checkout')
        self.assert_state_root_refused(self.base, 'overlaps the checkout')

    def test_state_root_symlinks_into_or_out_of_the_checkout_are_refused(self):
        self.ready()
        into = self.base / 'link into checkout'
        into.symlink_to(self.project / '.ai')
        self.assert_state_root_refused(into / 'state', 'overlaps the checkout')
        outside = self.base / 'outside'
        outside.mkdir()
        out = self.project / 'link out'
        out.symlink_to(outside)
        self.assert_state_root_refused(out, 'overlaps the checkout')
        self.assertEqual(list(outside.iterdir()), [])

    def test_state_root_overlapping_the_knowledge_dir_is_refused(self):
        self.ready()
        notes = self.base / 'notes'
        knowledge = notes / 'kb'
        knowledge.mkdir(parents=True)
        for state in (knowledge / 'state', knowledge, notes):
            self.assert_state_root_refused(state, 'overlaps the knowledge directory',
                                           '--knowledge-dir', str(knowledge))
        self.assertEqual(list(knowledge.iterdir()), [])

    def test_state_root_relative_settings_are_refused(self):
        self.ready()
        self.assert_state_root_refused('relative/state', 'AI_STATE_DIR must be an absolute path')
        for tool in ('ai-run', 'ai-pipeline'):
            result = self.tool(tool, '--approved', expected=1, AI_STATE_DIR='', XDG_STATE_HOME='relative')
            self.assertIn('XDG_STATE_HOME must be an absolute path', result.stderr)

    def test_state_root_helpers_fail_closed_and_check_the_named_checkout(self):
        self.ready()
        self.env['AI_STATE_DIR'] = str(self.project / 'state')
        (self.project / '.ai/reviews/current.md').write_text('<!-- Host evidence: HEAD abcdef0; saved now. -->\n')
        for args in (('review-info',), ('run-manifest', 'gate')):
            self.assertIn('overlaps the checkout', self.helper(*args, expected=1).stderr)
        self.assertFalse((self.project / 'state').exists())
        other = self.base / 'elsewhere'
        other.mkdir()
        check = ['python3', str(HELPER), 'state-root-check', '--checkout', str(self.project)]
        result = subprocess.run(check, cwd=other, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f'overlaps the checkout {self.project}', result.stderr)
        self.env['AI_STATE_DIR'] = str(other / 'state')
        result = subprocess.run(check, cwd=other, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_state_root_default_xdg_and_relative_knowledge_dir_recorded_absolute(self):
        self.ready()
        notes = self.base / 'notes'
        notes.mkdir()
        real = os.path.realpath(notes)
        self.env.update(AI_STATE_DIR='', XDG_STATE_HOME=str(self.base / 'xdg-state'))
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--knowledge-dir', '../notes',
                  MOCK_KNOWLEDGE_DIR=real)
        self.helper('tasks', 'complete')
        manifest = json.loads(next((self.base / 'xdg-state/ai-toolkit').rglob('run.json')).read_text())
        self.assertEqual(manifest['args'][manifest['args'].index('--knowledge-dir') + 1], real)
        self.assertFalse((self.base / 'host-state').exists())

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

    def test_runner_commits_validated_leftovers_but_never_failing_work(self):
        self.ready()
        # Tier-1 recovery: DONE + full gate passed on this content, but the session didn't commit.
        self.tool('ai-run', '--approved', MOCK_CLAUDE='dirty')
        self.assertIn('T001.txt', self.run_cmd(['git', 'ls-files']).stdout)
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.assertIn('checkpoint T001 (validated; the session did not commit)',
                      self.run_cmd(['git', 'log', '--format=%s']).stdout)
        self.assertIn("Claude didn't commit its validated work", self.notifications())
        self.assertIn('New files: T001.txt', self.notifications())

    def test_runner_checkpoint_never_commits_secret_looking_files(self):
        self.ready()
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='dirty-secret')
        self.assertIn('secret-looking files', (self.project / '.ai/local/last-error').read_text())
        tracked = self.run_cmd(['git', 'ls-files']).stdout
        self.assertNotIn('deploy.pem', tracked)
        self.assertNotIn('T001.txt', tracked)
        self.assertEqual(self.run_cmd(['git', 'diff', '--cached', '--name-only']).stdout.strip(), '')

    def test_recovery_never_commits_secret_looking_files(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error-once-partial', MOCK_RECOVER='commit_and_rerun',
                  MOCK_EXTRA_FILE='.env.production')
        self.assertIn('leftovers include secret-looking files', self.notifications())
        self.assertNotIn('.env.production', self.run_cmd(['git', 'ls-files']).stdout)
        self.assertNotIn('recovery checkpoint', self.run_cmd(['git', 'log', '--format=%s']).stdout)

    def test_checkpoint_guard_catches_secret_names_however_they_were_added(self):
        self.setup_project()
        self.commit('bootstrap')
        (self.project / 'plain.txt').write_text('x')
        self.commit('plain')
        (self.project / 'nested').mkdir()
        for name in ('nested/.envrc', '.environment', 'notes.txt'):
            (self.project / name).write_text('x')
        self.run_cmd(['git', 'mv', 'plain.txt', 'api.key'])  # rename destination
        self.run_cmd(['git', 'add', '--all', '--', '.'])
        result = self.helper('checkpoint-guard', expected=1)
        for name in ('nested/.envrc', '.environment', 'api.key'):
            self.assertIn(name, result.stderr)
        self.assertNotIn('notes.txt', result.stderr)
        self.run_cmd(['git', 'reset', '-q', '--hard'])
        self.run_cmd(['git', 'clean', '-qfd'])
        (self.project / 'ok.txt').write_text('x')
        self.run_cmd(['git', 'add', '--all', '--', '.'])
        self.assertIn('ok.txt', self.helper('checkpoint-guard').stdout)

    def test_review_with_a_renamed_optional_section_is_accepted(self):
        report = self.base / 'renamed.md'
        report.write_text('# Review\nOverall verdict: fine\nFinding counts: BLOCKER=0 MAJOR=0 MINOR=0\n'
                          '## BLOCKER findings\nNone.\n## MAJOR findings\nNone.\n## MINOR findings\nNone.\n'
                          '## Missing coverage and limitations\nx\n')
        self.setup_project()
        self.run_cmd(['python3', str(HELPER), 'publish-review', str(report), 'a' * 40, 'b' * 40])
        self.assertIn('Missing coverage and limitations', (self.project / '.ai/reviews/current.md').read_text())

    def test_runner_dirty_output_failing_validation_is_not_committed(self):
        self.ready()
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\ntest ! -e T001.txt\n')
        self.commit('gate that rejects the fixture output')
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
        self.assertIn('▶ STARTED on feature/test', self.notifications())
        self.assertIn('🏁 FINISHED: all 1/1 tasks done', self.notifications())
        self.assertIn('PR: https://github.com/example/project/pull/7', self.notifications())
        self.assertIn('1. Test: 1 manual step(s) in the PR', self.notifications())
        self.assertIn('Done: T001 Verify T001 (1/1 done)', self.notifications())
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
        self.assertIn('1. Decide the unresolved review findings', self.notifications())

    def test_pipeline_rejected_findings_still_open_normal_pr(self):
        # Rejected findings the re-check withdraws (R3; an upheld one would make it a draft).
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main',
                  MOCK_CODEX='major-always', MOCK_CLAUDE='triage-reject',
                  MOCK_RECHECK=json.dumps({'answers': [{'id': 'M1', 'verdict': 'withdrawn', 'reason': 'evidence holds'}]}))
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

    def test_pipeline_plan_review_gates_implementation(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, MOCK_CODEX_PLAN='major')
        self.assertIn('⛔ STOPPED, needs you: feature/test stopped during plan review', self.notifications())
        self.assertIn('P1: T001 has no test.', (self.project / '.ai/reviews/plan.md').read_text())
        self.assertEqual(self.helper('tasks', 'status', 'T001').stdout.strip(), 'TODO')  # no Claude spent
        self.assertFalse((self.base / 'codex-calls').exists())
        # The same plan is not reviewed again; skipping is explicit.
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertEqual((self.base / 'codex-plan-calls').read_text().count('call'), 1)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--skip-plan-review')
        self.helper('tasks', 'complete')

    def test_plan_review_is_bound_and_tracks_the_whole_tree(self):
        self.ready(task('T001', 'BLOCKED') + '\n' + task('T002'))
        # A BLOCKED task doesn't lift the gate for the untouched rest of the queue.
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, MOCK_CODEX_PLAN='major')
        plans = lambda: (self.base / 'codex-plan-calls').read_text().count('call')
        self.assertEqual(plans(), 1)
        # A forged clean report (edited counts and findings) is not a review.
        review = self.project / '.ai/reviews/plan.md'
        forged = review.read_text().replace('MAJOR=1', 'MAJOR=0').replace('- P1: T001 has no test.', 'None.')
        review.write_text(forged)
        self.commit('forge plan review')
        self.helper('plan-review-info', expected=1)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, MOCK_CODEX_PLAN='major')
        self.assertEqual(plans(), 2)
        # Unchanged tree: the verdict is reused. A source-only change is reviewed again.
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertEqual(plans(), 2)
        (self.project / 'src.txt').write_text('changed source\n')
        self.commit('source change')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertEqual(plans(), 3)

    def test_pipeline_plan_review_passes_and_reviews_use_effort(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', AI_REVIEW_MODEL='gpt-test')
        self.assertEqual((self.base / 'codex-plan-calls').read_text().count('call'), 1)
        log = self.run_cmd(['git', 'log', '--oneline']).stdout
        self.assertIn('record plan review', log)
        calls = (self.base / 'codex-args.log').read_text().splitlines()
        self.assertEqual(len(calls), 2)  # plan review + implementation review
        for call in calls:
            self.assertIn('-c model_reasoning_effort="high" --model gpt-test', call)
        self.tool('ai-review', '--plan', expected=1, AI_REVIEW_EFFORT='turbo')
        self.tool('ai-review', '--plan')  # by hand: committed, checkout stays clean
        self.tool('ai-review', '--plan')  # unchanged report: still succeeds
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.assertIn('record plan review', self.run_cmd(['git', 'log', '-1', '--format=%s']).stdout)

    def test_plan_review_stops_if_commit_hook_changes_reviewed_content(self):
        self.ready()
        hook = self.project / '.git/hooks/post-commit'
        hook.write_text('#!/usr/bin/env bash\n'
                        'git log -1 --format=%s | grep -q "record plan review" || exit 0\n'
                        'echo hooked >> hook.txt && git add hook.txt && git commit -qm hook\n')
        hook.chmod(0o755)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertIn('reviewed content changed while recording the plan review', self.notifications())
        self.assertEqual(self.helper('tasks', 'status', 'T001').stdout.strip(), 'TODO')
        # Run by hand, the same hook makes ai-review --plan fail instead of reporting success.
        self.tool('ai-review', '--plan', expected=1)
        self.assertIn('Reviewed content changed', (self.project / '.ai/local/last-error').read_text())

    def test_progress_notifications_for_done_and_blocked_tasks(self):
        title_task = task('T001').replace('Verify T001', 'Fix "$(touch pwned)" & `id`; rm -rf x')
        self.ready(title_task + '\n' + task('T002'))
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='blocked-first')
        notes = self.notifications()
        self.assertIn('Blocked: T001 Fix "$(touch pwned)" & `id`; rm -rf x (0/2 done)', notes)
        self.assertIn('Done: T002 Verify T002 (1/2 done)', notes)
        self.assertFalse((self.project / 'pwned').exists())

    def test_pipeline_stop_is_notified(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, MOCK_CLAUDE='error')
        self.assertIn('⛔ STOPPED, needs you: feature/test stopped during implementation', self.notifications())
        # A reported stop removes the liveness marker: the watchdog reports the stop, not a crash.
        self.assertFalse((self.project / '.ai/local/pipeline.active').exists())
        self.tool('ai-watchdog', expected=1)
        self.assertNotIn('gone without finishing', self.notifications())
        self.assertNotIn('stalled', self.notifications())
        # The runner announced the stop; the watchdog doesn't repeat it.
        self.assertEqual(self.notifications().count('⛔ STOPPED'), 1)
        self.tool('ai-pipeline', '--approved', '--base', 'not-a-ref', expected=1)
        self.run_cmd(['git', 'switch', 'main'])
        self.tool('ai-pipeline', '--approved', expected=1)

    # ---------------------------------------------------------------- auto-recovery
    def recovery_calls(self):
        calls = self.base / 'recover-calls'
        return calls.read_text().splitlines() if calls.exists() else []

    def test_recovery_reruns_after_a_transient_stop_and_finishes(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr',
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error-once')
        self.helper('tasks', 'complete')
        notes = self.notifications()
        self.assertEqual(len(self.recovery_calls()), 1)
        self.assertIn('stopped during: implementation', self.recovery_calls()[0].lower())
        self.assertIn('🔧 Recovering (1/2)', notes)
        self.assertIn('🔧 Recovered (1/2)', notes)
        self.assertIn('▶ RESUMED on feature/test after auto-recovery (1)', notes)
        self.assertIn('🏁 FINISHED', notes)
        self.assertNotIn('⛔', notes)
        self.assertIn('record stop during implementation', self.run_cmd(['git', 'log', '--format=%s']).stdout)
        self.assertFalse((self.project / '.ai/local/recovery-attempts').exists())
        self.assertFalse((self.project / '.ai/local/pipeline.active').exists())

    def test_recovery_commits_validated_leftovers_then_resumes(self):
        self.ready(task('T001').replace('T001.txt\n', 'T001.txt, partial.txt\n'))
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', AI_AUTO_RECOVER='1',
                  MOCK_CLAUDE='error-once-partial', MOCK_RECOVER='commit_and_rerun')
        self.assertIn('partial.txt', self.run_cmd(['git', 'ls-files']).stdout)
        self.assertIn('recovery checkpoint (validated leftover work)', self.run_cmd(['git', 'log', '--format=%s']).stdout)
        self.assertIn('🏁 FINISHED', self.notifications())

    def test_recovery_escalates_with_the_next_step(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        notes = self.notifications()
        self.assertIn('⛔ STOPPED, needs you: feature/test stopped during implementation', notes)
        self.assertIn('Next: look at T001 yourself', notes)
        self.assertEqual(notes.count('⛔'), 1)
        self.assertFalse((self.project / '.ai/local/pipeline.active').exists())

    def test_recovery_is_bounded_per_run(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error')
        notes = self.notifications()
        self.assertEqual(len(self.recovery_calls()), 2)
        self.assertIn('already tried 2 time(s)', notes)
        self.assertEqual(notes.count('⛔'), 1)
        # A human restart (after recording the stop) gets a fresh budget.
        self.commit('record the stop')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', AI_RECOVER_MAX='1', MOCK_CLAUDE='error')
        self.assertEqual(len(self.recovery_calls()), 3)

    def test_recovery_never_passes_a_changed_gate_or_hard_stop(self):
        self.ready()
        (self.project / '.ai/local').mkdir(exist_ok=True)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nexit 0\n')
        self.commit('weaken the gate')
        self.tool('ai-recover', '--stage', 'implementation', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn('gate files changed since you approved the run', self.notifications())
        self.assertEqual(len(self.recovery_calls()), 1)  # no AI consulted for the gate
        self.run_cmd(['git', 'revert', '--no-edit', 'HEAD'])  # gate back to the approved one
        (self.project / '.ai/local/last-error').write_text('Approved workflow gate changed during this run.')
        self.tool('ai-recover', '--stage', 'implementation', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn('this kind of stop always needs a human', self.notifications())
        self.assertEqual(len(self.recovery_calls()), 1)

    def test_recovery_decision_parsing_is_strict(self):
        log = self.base / 'decision.json'
        ok = {'type': 'result', 'subtype': 'success', 'is_error': False}
        cases = [
            (dict(ok, result='{"action": "rerun", "reason": "crash"}'), '0', 'rerun'),
            (dict(ok, result='{"action": "rerun", "reason": "crash"}'), '1', 'escalate'),  # nonzero exit
            (dict(ok, is_error=True, result='{"action": "rerun", "reason": "x"}'), '0', 'escalate'),
            (dict(ok, result='{"action": "rerun", "reason": "a"} {"action": "commit_and_rerun", "reason": "b"}'), '0', 'escalate'),
            (dict(ok, result='{"action": "delete_branch", "reason": "x"}'), '0', 'escalate'),
            (dict(ok, result='{"action": "rerun"}'), '0', 'escalate'),  # no reason
            (dict(ok, result=['not', 'a', 'string']), '0', 'escalate'),
            (dict(ok, result='{"action": "escalate", "reason": "x", "n": {"action": "commit_and_rerun"}}'), '0', 'escalate'),
            (dict(ok, result='{"action": "escalate", "action": "rerun", "reason": "x"}'), '0', 'escalate'),
            (dict(ok, result='```json\n{"action": "rerun", "reason": "crash"}\n```'), '0', 'rerun'),
            (dict(ok, result='Decision: {"action": "rerun", "reason": "crash"}'), '0', 'escalate'),
            (dict(ok, result='[{"action": "rerun", "reason": "crash"}]'), '0', 'escalate'),
        ]
        log.write_text('{"type": "result", "subtype": "success", "is_error": true, "is_error": false, '
                       '"result": "{\\"action\\": \\"rerun\\", \\"reason\\": \\"x\\"}"}')
        self.assertTrue(self.helper('recover-decision', str(log), '0').stdout.startswith('escalate'))
        log.write_text(json.dumps(['not', 'an', 'envelope']))
        self.assertTrue(self.helper('recover-decision', str(log), '0').stdout.startswith('escalate'))
        for envelope, code, expected in cases:
            log.write_text(json.dumps(envelope))
            self.assertEqual(self.helper('recover-decision', str(log), code).stdout.split('\t')[0], expected, envelope)
        log.write_text('not json')
        self.assertTrue(self.helper('recover-decision', str(log), '0').stdout.startswith('escalate'))

    def test_recovery_refuses_other_branch_and_tampered_manifest(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        calls = len(self.recovery_calls())
        self.run_cmd(['git', 'switch', '-q', '-c', 'other-branch'])
        self.tool('ai-recover', '--stage', 'implementation', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn("not the approved run's branch", self.notifications())
        self.run_cmd(['git', 'switch', '-q', 'feature/test'])
        manifest = next((self.base / 'host-state').rglob('run.json'))
        data = json.loads(manifest.read_text())
        data['attempts'] = 'BASH_VERSINFO[$(touch pwned)0]'
        manifest.write_text(json.dumps(data))
        self.tool('ai-recover', '--stage', 'implementation', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn('no approved run to resume', self.notifications())
        self.assertFalse((self.project / 'pwned').exists())
        self.assertEqual(len(self.recovery_calls()), calls)  # no AI consulted
        self.assertFalse((self.project / '.ai/local/pipeline.active').exists())

    def test_recover_state_root_unsafe_escalates_before_reading_the_manifest(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', AI_RECOVER_MAX='9', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        manifest = next((self.base / 'host-state').rglob('run.json'))
        budget = manifest.read_text()
        calls = len(self.recovery_calls())
        last_error = self.project / '.ai/local/last-error'
        marker = self.project / '.ai/local/pipeline.active'
        for state, message in ((self.project / 'state', 'overlaps the checkout'),
                               ('relative/state', 'AI_STATE_DIR must be an absolute path')):
            with self.subTest(state=state):
                last_error.write_text('Claude session failed for T001\n')
                marker.write_text('999999\n')
                head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout
                before = self.notifications().count('⛔ STOPPED, needs you')
                result = self.tool('ai-recover', '--stage', 'implementation', expected=1,
                                   AI_AUTO_RECOVER='1', AI_STATE_DIR=str(state))
                self.assertIn('escalated to the human', result.stderr)
                error = last_error.read_text()
                self.assertIn(message, error)
                self.assertIn('Claude session failed for T001', error)
                stops = [line for line in self.notifications().splitlines() if '⛔ STOPPED, needs you' in line]
                self.assertEqual(len(stops) - before, 1)
                self.assertIn(message, stops[-1])
                self.assertEqual(len(self.recovery_calls()), calls)  # no recovery Claude session
                self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout, head)
                self.assertFalse(marker.exists())
                self.assertEqual(manifest.read_text(), budget)  # attempt budget untouched
                self.assertFalse((self.project / 'state').exists())

    def test_tier1_checkpoint_rejects_hook_changed_content(self):
        self.ready()
        hook = self.project / '.git/hooks/pre-commit'
        hook.write_text('#!/usr/bin/env bash\n'
                        'git diff --cached --name-only | grep -q T001.txt || exit 0\n'
                        'echo sneaky > sneaky.txt && git add sneaky.txt\n')
        hook.chmod(0o755)
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='dirty')
        self.assertIn('differs from the validated content', (self.project / '.ai/local/last-error').read_text())

    def test_recovery_signal_and_rejected_process_handling(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        marker = self.project / '.ai/local/pipeline.active'
        # A second recovery that can't get the lock leaves the live run's marker alone.
        marker.write_text('999999\n')
        lock = subprocess.Popen(['flock', '-o', str(self.project / '.ai/local/workflow.lock'), 'sleep', '30'])
        self.addCleanup(lambda: (lock.kill(), lock.wait()))
        import time
        time.sleep(0.3)
        self.tool('ai-recover', '--stage', 'implementation', expected=1, AI_AUTO_RECOVER='1')
        self.assertEqual(marker.read_text(), '999999\n')
        self.assertIn('Claude session failed', (self.project / '.ai/local/last-error').read_text())
        lock.kill()
        lock.wait()
        # A killed recovery still sends exactly one final ⛔ and drops its own marker.
        slow = self.mock_bin / 'slow-claude'
        (self.mock_bin / 'claude').rename(slow)
        (self.mock_bin / 'claude').write_text('#!/usr/bin/env bash\nsleep 3\n')
        (self.mock_bin / 'claude').chmod(0o755)
        before = self.notifications().count('⛔')
        recover = subprocess.Popen([str(self.project / '.ai/bin/ai-recover'), '--stage', 'implementation'],
                                   cwd=self.project, env=dict(self.env, AI_AUTO_RECOVER='1'),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(100):
            if marker.exists() and marker.read_text().strip() == str(recover.pid):
                break
            time.sleep(0.05)
        recover.terminate()
        out = recover.communicate(timeout=60)[0].decode()
        self.assertEqual(self.notifications().count('⛔') - before, 1, out + self.notifications())
        self.assertIn('auto-recovery failed unexpectedly (exit 143)', self.notifications())
        self.assertFalse(marker.exists())

    def test_recovery_restores_the_approved_runs_settings(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', AI_RECOVER_MAX='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        manifest = json.loads(next((self.base / 'host-state').rglob('run.json')).read_text())
        self.assertEqual(manifest['env']['AI_RECOVER_MAX'], '1')
        self.assertEqual(manifest['env']['AI_AUTO_RECOVER'], '1')
        # Started without those settings (as a detached service would be), it uses the approved ones.
        self.tool('ai-recover', '--stage', 'implementation', expected=1)
        self.assertIn('already tried 1 time(s)', self.notifications())

    def test_resume_ignores_user_config_the_approved_run_did_not_have(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        # Added to the user config after approval: a resume must not pick it up.
        (self.config / 'ai-toolkit').mkdir(parents=True, exist_ok=True)
        (self.config / 'ai-toolkit/config').write_text('AI_MODEL=opus-later\n')
        (self.project / '.ai/local/mock-args').unlink()
        self.tool('ai-recover', '--stage', 'implementation', MOCK_RECOVER='rerun')
        self.helper('tasks', 'complete')
        args = (self.project / '.ai/local/mock-args').read_text()
        self.assertNotIn('opus-later', args)
        # Control: a human start does read it.
        manifest = json.loads(next((self.base / 'host-state').rglob('run.json')).read_text())
        self.assertNotIn('AI_MODEL', manifest['env'])

    def test_committed_content_must_match_validated_files(self):
        self.ready()
        (self.project / '.gitattributes').write_text('*.txt filter=sneaky\n')
        self.run_cmd(['git', 'config', 'filter.sneaky.clean', 'sed s/checkpointed/tampered/'])
        self.commit('filter')
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='dirty')
        self.assertIn('differs from the validated content', (self.project / '.ai/local/last-error').read_text())

    def subjects(self):
        return self.run_cmd(['git', 'log', '--format=%s']).stdout.splitlines()

    def only_run_log_dirty(self):
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain', '--untracked-files=all']).stdout,
                         ' M .ai/run-log.md\n')

    def test_committed_bytes_run_stops_on_a_filtered_agent_commit(self):
        self.ready(task('T001') + task('T002'))
        (self.project / '.gitattributes').write_text('*.txt filter=sneaky\n')
        self.run_cmd(['git', 'config', 'filter.sneaky.clean', 'sed s/checkpointed/tampered/'])
        self.commit('filter')
        self.tool('ai-run', '--approved', expected=1)
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('The checkpoint of T001 differs from the validated content', error)
        self.assertIn('T001.txt', error)
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text(), 'call\n')
        subjects = self.subjects()
        self.assertEqual(subjects[0], 'chore(ai): record T001 runner checkpoint')
        self.assertIn('implement T001', subjects)
        self.assertEqual(self.helper('tasks', 'status', 'T001').stdout.strip(), 'DONE')
        self.assertNotIn('✅ Done', self.notifications())
        self.only_run_log_dirty()

    def test_committed_bytes_run_stops_on_a_committed_mode_mismatch(self):
        self.ready()
        self.run_cmd(['git', 'config', 'core.filemode', 'false'])
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='exec-committed-644')
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('differs from the validated content', error)
        self.assertIn('Committed mode of T001.txt (100644)', error)
        self.only_run_log_dirty()
        self.assertTrue(self.run_cmd(['git', 'ls-tree', 'HEAD', 'T001.txt']).stdout.startswith('100644 '))
        self.assertTrue(os.access(self.project / 'T001.txt', os.X_OK))
        self.assertFalse([s for s in self.subjects() if 'the session did not commit' in s])

    def test_committed_bytes_run_stops_on_a_filtered_final_handoff(self):
        self.ready(task('T001') + task('T002'))
        (self.project / '.gitattributes').write_text('.ai/state.md filter=phase\n')
        # Only the final handoff's phase line is rewritten; task checkpoints say "implementing".
        self.run_cmd(['git', 'config', 'filter.phase.clean',
                      "sed -E 's/^Phase: ready_for_review$/Phase: tampered/'"])
        self.commit('phase filter')
        self.tool('ai-run', '--approved', expected=1)
        subjects = self.subjects()
        for task_id in ('T001', 'T002'):
            self.assertIn(f'chore(ai): record {task_id} runner checkpoint', subjects)
            self.assertEqual(self.helper('tasks', 'status', task_id).stdout.strip(), 'DONE')
        self.assertEqual(self.notifications().count('✅ Done'), 2)
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('The checkpoint of final handoff differs from the validated content', error)
        self.assertIn('.ai/state.md', error)
        self.assertEqual(subjects[0], 'chore(ai): record review handoff')
        self.only_run_log_dirty()
        self.assertNotIn('All tasks done', self.notifications())

    def test_committed_bytes_run_accepts_symlinks_and_submodules(self):
        self.ready()
        source = self.base / 'submodule-source'
        source.mkdir()
        for command in (['init', '-q', '-b', 'main'], ['commit', '-q', '--allow-empty', '-m', 'init']):
            subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *command],
                           cwd=source, env=self.env, check=True, capture_output=True)
        self.run_cmd(['git', '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(source), 'vendored'])
        (self.project / 'target.txt').write_text('symlink target\n')
        os.symlink('target.txt', self.project / 'link')
        self.commit('symlink and submodule')
        self.tool('ai-run', '--approved')
        self.helper('tasks', 'complete')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain', '--untracked-files=all']).stdout, '')
        self.assertIn('All tasks done', self.notifications())

    def no_pr_published(self):
        self.assertEqual([c for c in self.gh_calls() if c[:2] in (['pr', 'create'], ['pr', 'edit'])], [])
        self.assertNotIn('FINISHED', self.notifications())

    def test_committed_bytes_pipeline_stops_before_review(self):
        self.ready(task('T001', 'DONE'))
        (self.project / '.gitattributes').write_text('*.txt filter=sneaky\n')
        self.run_cmd(['git', 'config', 'filter.sneaky.clean', 'sed s/checkpointed/tampered/'])
        (self.project / 'T001.txt').write_text('checkpointed implementation\n')
        self.commit('done task, committed through a filter')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('Pipeline stopped during review: Committed content differs from the validated content', result.stderr)
        self.assertIn('T001.txt', (self.project / '.ai/local/last-error').read_text())
        self.assertFalse((self.base / 'codex-calls').exists())
        self.no_pr_published()

    def test_committed_bytes_pipeline_publish_check_catches_a_filtered_review(self):
        self.ready()
        origin = self.add_origin()
        (self.project / '.gitattributes').write_text('.ai/reviews/current.md filter=review\n')
        self.run_cmd(['git', 'config', 'filter.review.clean', 'sed s/no.demonstrated.findings/flawless/'])
        self.commit('review filter')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('Publish check failed at pull request preparation: committed content differs from the '
                      'validated content', result.stderr)
        self.assertIn('.ai/reviews/current.md', result.stderr)
        self.assertEqual(self.remote_head(origin), '')
        self.assertEqual(self.gh_calls(), [])
        self.no_pr_published()

    def push_hook_commits_filtered_file(self, commit_on, exit_code):
        """pre-push hook: on invocation number `commit_on` it commits hooked.txt through a clean
        filter (committed bytes differ, tree stays clean); it always exits `exit_code`."""
        (self.project / '.gitattributes').write_text('hooked.txt filter=hooked\n')
        self.run_cmd(['git', 'config', 'filter.hooked.clean', 'sed s/original/tampered/'])
        self.commit('hooked filter')
        calls = self.base / 'hook-calls'
        self.hook('pre-push', f'echo call >> "{calls}"\n'
                              f'if [[ "$(grep -c call "{calls}")" == {commit_on} ]]; then\n'
                              '  echo original > hooked.txt; git add hooked.txt; git commit -qm "hook: hooked.txt"\n'
                              f'fi\nexit {exit_code}\n')
        return calls

    def assert_hooked_stop(self, calls, hook_runs):
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('Publish check failed at push: committed content differs from the validated content', error)
        self.assertIn('hooked.txt', error)
        self.assertNotIn('3 tries', error)
        self.assertEqual(calls.read_text().count('call'), hook_runs)
        subjects = self.subjects()
        self.assertEqual(subjects[0], 'hook: hooked.txt')
        self.assertIn('implement T001', subjects)
        self.helper('tasks', 'complete')
        self.no_pr_published()

    def test_committed_bytes_pipeline_failed_push_hook_commit_stops(self):
        self.ready()
        origin = self.add_origin()
        calls = self.push_hook_commits_filtered_file(1, 1)
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assert_hooked_stop(calls, 1)
        self.assertEqual(self.remote_head(origin), '')
        self.assertFalse((self.base / 'sleep.log').exists())  # no retry wait after the failed check

    def test_committed_bytes_pipeline_successful_push_hook_commit_stops(self):
        self.ready()
        self.add_origin()
        calls = self.push_hook_commits_filtered_file(1, 0)
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assert_hooked_stop(calls, 1)

    def test_committed_bytes_pipeline_third_push_attempt_escalates_without_recovery(self):
        self.ready()
        origin = self.add_origin()
        calls = self.push_hook_commits_filtered_file(3, 1)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn('escalated to the human', result.stderr)
        self.assert_hooked_stop(calls, 3)
        self.assertFalse((self.base / 'recover-calls').exists())
        self.assertEqual(self.remote_head(origin), '')
        self.assertEqual((self.base / 'sleep.log').read_text().split(), ['20', '40'])

    def test_committed_bytes_pipeline_harmless_failed_push_still_retries(self):
        self.ready()
        origin = self.add_origin()
        marker = self.base / 'failed-once'
        self.hook('pre-push', f'[[ -e "{marker}" ]] && exit 0\ntouch "{marker}"\nexit 1\n')
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assertEqual((self.base / 'sleep.log').read_text().split(), ['20'])
        self.assertEqual(self.remote_head(origin), self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip())
        self.assertEqual(len([c for c in self.gh_calls() if c[:2] == ['pr', 'create']]), 1)

    def test_committed_bytes_pipeline_accepts_symlinks_and_submodules(self):
        self.ready()
        origin = self.add_origin()
        source = self.base / 'submodule-source'
        source.mkdir()
        for command in (['init', '-q', '-b', 'main'], ['commit', '-q', '--allow-empty', '-m', 'init']):
            subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *command],
                           cwd=source, env=self.env, check=True, capture_output=True)
        self.run_cmd(['git', '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(source), 'vendored'])
        (self.project / 'target.txt').write_text('symlink target\n')
        os.symlink('target.txt', self.project / 'link')
        self.commit('symlink and submodule')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assertIn('Pull request: https://github.com/example/project/pull/7', result.stdout)
        self.assertEqual(self.remote_head(origin), self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip())
        self.assertIn('🏁 FINISHED', self.notifications())

    def test_finish_summary_lists_human_todos(self):
        self.ready()
        self.add_origin()
        (self.project / '.ai/handoff.md').write_text(
            '# Handoff\n\n## Manual testing for the human\n1. Open the app.\n2. Drag a card.\n\n'
            '## Human todos\n- Create the Discord app credentials\n- [ ] Decide the guild limit\n')
        self.commit('handoff with human todos')
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        notes = self.notifications()
        self.assertIn('1. Test: 2 manual step(s) in the PR', notes)
        self.assertIn('2. Merge the PR', notes)
        self.assertIn('3. Create the Discord app credentials', notes)
        self.assertIn('4. Decide the guild limit', notes)

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
        self.assertIn('⏸ PAUSED: Claude usage limit', self.notifications())
        self.assertIn('Claude usage limit', (self.project / '.ai/local/pauses.log').read_text())

    def test_usage_limit_beyond_wait_budget_stops(self):
        self.ready()
        result = self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='limit-far', AI_LIMIT_MAX_WAIT='3600')
        self.assertIn('wait budget', result.stderr)
        self.assertFalse((self.base / 'sleep.log').exists())
        self.assertIn('⛔ STOPPED, needs you: runner stopped at T001', self.notifications())

    def test_codex_usage_limit_pauses_then_retries(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='limit-once')
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), 2)
        self.assertIn('⏸ PAUSED: Codex usage limit', self.notifications())
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
        self.assertIn('stopped during triage', self.notifications())

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
        self.assertIn('pushing the final handoff commit failed', result.stderr)
        self.assertIn('⛔ STOPPED, needs you', self.notifications())
        self.assertIn('final handoff commit failed', self.notifications())

    # ---------------------------------------------------------------- publish invariants (R2)
    def hook(self, name, body):
        hook = self.project / '.git/hooks' / name
        hook.write_text('#!/usr/bin/env bash\n' + body)
        hook.chmod(0o755)

    def remote_head(self, origin):
        return subprocess.run(['git', '--git-dir', str(origin), 'rev-parse', '--verify', '--quiet',
                               'refs/heads/feature/test'], capture_output=True, text=True).stdout.strip()

    def test_publish_ready_commit_hook_changing_source_while_recording_review_stops_before_push(self):
        self.ready()
        origin = self.add_origin()
        self.hook('post-commit', '[[ "$(git log -1 --format=%s)" == "chore(ai): record independent review" ]] || exit 0\n'
                                 'echo sneaky > app.py; git add app.py; git commit -qm "hook: unreviewed source"\n')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('Publish check failed at pull request preparation: the review is not current', result.stderr)
        self.assertEqual(self.remote_head(origin), '')
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ['pr', 'create']], [])
        self.assertNotIn('FINISHED', self.notifications())

    def test_publish_ready_final_push_hook_leaving_uncommitted_source_stops(self):
        self.ready()
        self.add_origin()
        self.hook('pre-push', '[[ "$(git log -1 --format=%s)" == "chore(ai): record pull request" ]] || exit 0\n'
                              'echo sneaky > app.py\n')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('Publish check failed at final push: the checkout is not clean', result.stderr)
        self.assertIn('⛔ STOPPED, needs you', self.notifications())
        self.assertNotIn('FINISHED', self.notifications())

    def test_publish_ready_failed_push_that_changes_checkout_stops_before_retry(self):
        self.ready()
        origin = self.add_origin()
        self.hook('pre-push', 'echo sneaky > untracked.txt\nexit 1\n')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('Publish check failed at push: the checkout is not clean', result.stderr)
        self.assertFalse((self.base / 'sleep.log').exists())  # checked after the failed attempt, no retry
        self.assertEqual(self.remote_head(origin), '')
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ['pr', 'create']], [])

    def test_publish_ready_push_hook_adding_workflow_commit_stops_before_pr(self):
        self.ready()
        origin = self.add_origin()
        marker = self.base / 'hooked'
        self.hook('pre-push', f'[[ -e "{marker}" ]] && exit 0\ntouch "{marker}"\n'
                              'echo "| hook |" >> .ai/run-log.md; git commit -qm "hook: log only" -- .ai/run-log.md\n')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.assertNotEqual(self.remote_head(origin), head)
        self.assertIn('Publish check failed after push: origin feature/test is', result.stderr)
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ['pr', 'create']], [])
        self.assertNotIn('FINISHED', self.notifications())

    def test_publish_ready_normal_path_remote_equals_final_head(self):
        self.ready()
        origin = self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.assertEqual(self.run_cmd(['git', 'log', '-1', '--format=%s']).stdout.strip(), 'chore(ai): record pull request')
        self.assertEqual(self.remote_head(origin), head)
        self.assertEqual(len([c for c in self.gh_calls() if c[:2] == ['pr', 'create']]), 1)
        self.assertIn('🏁 FINISHED', self.notifications())

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
        self.assertNotIn('1. Decide the unresolved review findings', self.notifications())

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

    # ---------------------------------------------------------------- triage completion (R1)
    def subjects(self):
        return self.run_cmd(['git', 'log', '--format=%s']).stdout.splitlines()

    def triage_rounds(self):
        return self.subjects().count('chore(ai): record review triage')

    def triage_calls(self):
        calls = self.base / 'triage-calls'
        return calls.read_text().count('call') if calls.exists() else 0

    def open_stage(self):
        return self.helper('run-manifest', 'stage').stdout.strip()

    def test_triage_completion_normal_round_counts_once(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once')
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.triage_calls(), 1)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertEqual(self.open_stage(), '')

    def test_triage_completion_uncommitted_records_recover_into_one_round(self):
        # 2026-10-05: the triage session's commit was denied, the run stopped, recovery resumed.
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', AI_AUTO_RECOVER='1',
                  MOCK_CODEX='major-once', MOCK_CLAUDE='triage-no-commit')
        subjects = self.subjects()
        self.assertEqual(self.triage_rounds(), 1)
        self.assertFalse([s for s in subjects if 'recovery checkpoint' in s or 'record stop during' in s])
        counted = self.run_cmd(['git', 'log', '--format=%H', '--grep', '^chore(ai): record review triage']).stdout.split()
        files = self.run_cmd(['git', 'show', '--name-only', '--format=', counted[0]]).stdout.split()
        self.assertIn('.ai/tasks.md', files)
        self.assertIn('.ai/reviews/dispositions.md', files)
        self.assertEqual(self.triage_calls(), 1)  # recorded, not triaged again
        self.assertEqual(self.recovery_calls(), [])  # no Claude decision: the stage rules decide
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        notes = self.notifications()
        self.assertIn('🔧 Recovered (1/2)', notes)
        self.assertIn('🏁 FINISHED', notes)
        self.assertNotIn('⛔', notes)
        self.assertEqual(self.open_stage(), '')

    def test_triage_completion_respects_the_fix_round_limit(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--max-fix-rounds', '1', AI_AUTO_RECOVER='1',
                  MOCK_CODEX='major-always', MOCK_CLAUDE='triage-no-commit')
        self.assertEqual(self.triage_rounds(), 1)
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertIn('--draft', create[0])

    def test_triage_completion_crash_after_counted_commit_does_not_count_twice(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-once')
        if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip():
            self.commit('record review')
        gate = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.helper('run-manifest', 'start', gate, 'feature/test', '--approved', '--base', 'main', '--no-pr')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('run-manifest', 'stage-set', 'triage', head)
        # The pipeline's triage child finished its counted commit; then the pipeline died.
        self.tool('ai-run', '--approved', '--triage', '--since', head)
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.open_stage().split()[:2], ['triage', head])
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once')
        self.assertIn('Completing the interrupted review triage', result.stdout)
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.triage_calls(), 1)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertEqual(self.open_stage(), '')

    def test_triage_completion_watchdog_crash_recovery_completes_once(self):
        self.ready()
        crashed = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=None,
                            AI_AUTO_RECOVER='1', MOCK_CODEX='major-once', MOCK_CLAUDE='triage-crash')
        self.assertEqual(crashed.returncode, -9)
        self.assertEqual(self.triage_rounds(), 0)
        self.assertTrue(self.open_stage().startswith('triage '))
        # What ai-watchdog --recover starts after a crash; the stage comes from the manifest.
        self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', MOCK_CLAUDE='',
                  MOCK_CODEX='major-once')
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.triage_calls(), 1)
        self.assertEqual(self.recovery_calls(), [])
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertIn('🏁 FINISHED', self.notifications())
        self.assertEqual(self.open_stage(), '')

    # ---------------------------------------------------------------- stage per branch (T017)
    def start_run(self, branch):
        gate = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.helper('run-manifest', 'start', gate, branch, '--approved', '--base', 'main', '--no-pr')

    def test_stage_per_branch_survives_a_run_on_another_branch(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-once')
        if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip():
            self.commit('record review')
        self.start_run('feature/test')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('run-manifest', 'stage-set', 'triage', head)
        stage = self.open_stage()
        self.assertEqual(stage.split()[:2], ['triage', head])
        # Another branch's run neither drops nor inherits it, and clearing there leaves it alone.
        self.run_cmd(['git', 'switch', '-q', '-c', 'other'])
        self.start_run('other')
        self.assertEqual(self.open_stage(), '')
        self.helper('run-manifest', 'stage-clear')
        self.run_cmd(['git', 'switch', '-q', 'feature/test'])
        self.assertEqual(self.open_stage(), stage)
        # A human restart on the same branch carries it over.
        self.start_run('feature/test')
        self.assertEqual(self.open_stage(), stage)
        self.helper('run-manifest', 'stage-clear')
        self.assertEqual(self.open_stage(), '')

    def test_stage_per_branch_legacy_manifest_stage_moves_to_its_branch(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-once')
        if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip():
            self.commit('record review')
        self.start_run('feature/test')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('run-manifest', 'stage-set', 'triage', head)
        stage = self.open_stage()
        # Rewrite it in the old format: the stage inside run.json, no per-branch file.
        state = self.base / 'host-state'
        stage_file = next(state.rglob('stage-*.json'))
        manifest = next(state.rglob('run.json'))
        data = json.loads(manifest.read_text())
        data['stage'] = json.loads(stage_file.read_text())['stage']
        manifest.write_text(json.dumps(data))
        stage_file.unlink()
        self.assertEqual(self.open_stage(), stage)
        self.run_cmd(['git', 'switch', '-q', '-c', 'other'])
        self.start_run('other')
        self.assertEqual(self.open_stage(), '')
        self.run_cmd(['git', 'switch', '-q', 'feature/test'])
        self.assertEqual(self.open_stage(), stage)

    def test_stage_per_branch_unreadable_record_fails_closed(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-once')
        if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip():
            self.commit('record review')
        self.start_run('feature/test')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('run-manifest', 'stage-set', 'triage', head)
        next((self.base / 'host-state').rglob('stage-*.json')).write_text('{not json')
        self.assertIn('is unreadable', self.helper('run-manifest', 'stage', expected=1).stderr)
        self.helper('stage-verify', expected=1)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertIn("Cannot read this branch's triage stage", result.stderr)
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip(), head)

    def test_stage_per_branch_interrupted_triage_completes_after_another_branch_run(self):
        # Review M4: a run on branch B in between erased branch A's interrupted triage, so
        # restarting A skipped scope/freshness checks and never counted the round.
        self.ready()
        crashed = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=None,
                            MOCK_CODEX='major-once', MOCK_CLAUDE='triage-crash')
        self.assertEqual(crashed.returncode, -9)
        stage = self.open_stage()
        self.assertTrue(stage.startswith('triage '))
        start = stage.split()[1]
        self.assertEqual(self.fix_rounds(), 0)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        (self.project / '.ai/local/pipeline.active').unlink(missing_ok=True)
        # The human runs the pipeline on another branch in between.
        self.run_cmd(['git', 'switch', '-q', '-c', 'other', 'main'])
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=None)
        self.assertEqual(self.helper('run-manifest', 'branch').stdout.strip(), 'other')
        self.assertEqual(self.open_stage(), '')
        self.run_cmd(['git', 'switch', '-q', '-f', 'feature/test'])
        self.assertEqual(self.open_stage(), stage)
        # Restart A: the stage is verified and counted once, before any implementation.
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once')
        self.assertIn('Completing the interrupted review triage', result.stdout)
        self.assertEqual(self.triage_calls(), 1)
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.fix_rounds(), 1)
        counted = self.run_cmd(['git', 'log', '--format=%H', '--grep', '^chore(ai): record review triage$']).stdout.split()
        self.assertEqual(len(counted), 1)
        changed = self.run_cmd(['git', 'diff', '--name-only', start, counted[0]]).stdout.split()
        self.assertTrue(set(changed) <= {'.ai/tasks.md', '.ai/reviews/dispositions.md', '.ai/current-plan.md',
                                          '.ai/state.md', '.ai/handoff.md', '.ai/run-log.md'}, changed)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertEqual(self.open_stage(), '')

    # ---------------------------------------------------------------- fix round count (T015)
    def fix_rounds(self):
        return int(self.helper('fix-rounds', 'count', 'main').stdout.strip())

    def assert_two_rounds_with_agent_subject(self, subject):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--max-fix-rounds', '2',
                  MOCK_CODEX='major-always', MOCK_TRIAGE_SUBJECT=subject)
        self.assertEqual(self.triage_calls(), 2)
        self.assertEqual(self.fix_rounds(), 2)
        # The round limit still makes the PR a draft once it is really reached.
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertIn('--draft', create[0])

    def test_fix_round_count_ignores_agent_subject_starting_with_host_subject(self):
        # 2026-10-05: the triage session's own "chore(ai): record review triage dispositions"
        # commit counted as a second round and stopped the run after one round.
        self.assert_two_rounds_with_agent_subject('chore(ai): record review triage dispositions')

    def test_fix_round_count_ignores_agent_subject_equal_to_host_subject(self):
        self.assert_two_rounds_with_agent_subject('chore(ai): record review triage')

    def test_fix_round_count_one_real_round_counts_once(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once')
        self.assertEqual(self.fix_rounds(), 1)
        self.helper('fix-rounds', 'record', 'HEAD~0', expected=1)  # not a host triage commit
        counted = self.run_cmd(['git', 'log', '--format=%H', '--grep', '^chore(ai): record review triage$']).stdout.split()
        self.helper('fix-rounds', 'record', counted[0])  # recording the same round again is a no-op
        self.assertEqual(self.fix_rounds(), 1)

    def test_fix_round_count_survives_recovery_resume(self):
        self.ready()
        crashed = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--max-fix-rounds', '1',
                            expected=None, AI_AUTO_RECOVER='1', MOCK_CODEX='major-always', MOCK_CLAUDE='triage-crash')
        self.assertEqual(crashed.returncode, -9)
        self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', MOCK_CLAUDE='',
                  MOCK_CODEX='major-always')
        self.assertEqual(self.triage_calls(), 1)
        self.assertEqual(self.fix_rounds(), 1)
        self.assertIn('🏁 FINISHED', self.notifications())

    def test_fix_round_count_agent_subject_does_not_close_an_interrupted_triage(self):
        # The session committed with the host subject, then the machine restarted before the
        # host's counted commit: the round is still recorded, exactly once.
        self.ready()
        crashed = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=None,
                            AI_AUTO_RECOVER='1', MOCK_CODEX='major-once', MOCK_CLAUDE='triage-crash',
                            MOCK_TRIAGE_SUBJECT='chore(ai): record review triage')
        self.assertEqual(crashed.returncode, -9)
        self.assertEqual(self.fix_rounds(), 0)
        self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', MOCK_CLAUDE='',
                  MOCK_CODEX='major-once')
        self.assertEqual(self.triage_calls(), 1)
        self.assertEqual(self.fix_rounds(), 1)
        self.assertEqual(self.open_stage(), '')

    def test_fix_round_count_survives_human_restart(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--max-fix-rounds', '1',
                  MOCK_CODEX='major-always')
        self.assertEqual(self.triage_calls(), 1)
        # The human restarts the same branch with a larger budget: one more round, not two.
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--max-fix-rounds', '2',
                  MOCK_CODEX='major-always')
        self.assertEqual(self.triage_calls(), 2)
        self.assertEqual(self.fix_rounds(), 2)

    def test_fix_round_count_is_per_branch_and_legacy_needs_the_exact_subject(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once')
        self.assertEqual(self.fix_rounds(), 1)
        self.run_cmd(['git', 'checkout', '-q', '-b', 'other', 'main'])
        self.assertEqual(self.fix_rounds(), 0)
        # Once a branch has a host record, a commit subject alone never counts.
        self.run_cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'chore(ai): record review triage'])
        self.assertEqual(self.fix_rounds(), 0)
        # A legacy branch (no host record): only exact host subjects count, and are recorded.
        self.run_cmd(['git', 'checkout', '-q', '-b', 'legacy', 'main'])
        self.run_cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'chore(ai): record review triage'])
        self.run_cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'chore(ai): record review triage dispositions'])
        self.assertEqual(self.fix_rounds(), 1)
        self.run_cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'chore(ai): record review triage'])
        self.assertEqual(self.fix_rounds(), 1)
        self.run_cmd(['git', 'checkout', '-q', 'feature/test'])
        self.assertEqual(self.fix_rounds(), 1)

    def test_triage_completion_source_leftovers_escalate_and_commit_nothing(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1',
                  MOCK_CODEX='major-once', MOCK_CLAUDE='triage-no-commit-source')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        notes = self.notifications()
        self.assertEqual(notes.count('⛔'), 1)
        self.assertIn('outside its scope', notes)
        self.assertEqual(self.recovery_calls(), [])
        self.assertEqual(self.triage_rounds(), 0)
        self.assertIn('?? src.txt', self.run_cmd(['git', 'status', '--porcelain']).stdout)
        # A human restart verifies the same stage: still escalates, nothing committed or implemented.
        sessions = (self.project / '.ai/local/mock-invocations').read_text().count('call')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertIn('Triage stage cannot be completed safely', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip(), head)
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text().count('call'), sessions)
        self.assertEqual(self.triage_rounds(), 0)

    def test_triage_completion_hook_changing_source_in_counted_commit_escalates(self):
        self.ready()
        hook = self.project / '.git/hooks/pre-commit'
        hook.write_text('#!/usr/bin/env bash\n'
                        'git diff --cached --name-only | grep -qx .ai/state.md || exit 0\n'
                        'grep -q "^Phase: fixing_review" .ai/state.md || exit 0\n'
                        'echo hooked > src.txt && git add src.txt\n')
        hook.chmod(0o755)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1',
                  MOCK_CODEX='major-once')
        self.assertEqual(self.triage_rounds(), 1)
        self.assertIn('src.txt', self.run_cmd(['git', 'show', '--name-only', '--format=', 'HEAD']).stdout)
        self.assertIn('Triage stage: the triage commit is out of scope', self.notifications())
        self.assertEqual(self.notifications().count('⛔'), 1)
        self.assertEqual(self.recovery_calls(), [])
        # Resume (human restart): escalates again, no implementation, no second count.
        sessions = (self.project / '.ai/local/mock-invocations').read_text().count('call')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, MOCK_CODEX='major-once')
        self.assertIn('Triage stage cannot be completed safely', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text().count('call'), sessions)

    # ---------------------------------------------------------------- R3: disputed findings re-check
    def rejected_review(self, rows, fix_task=False):
        """A verified review with M1/M2 (MAJOR) and committed dispositions ROWS."""
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='two-major-once')
        self.commit('record review')
        head = self.helper('review-info').stdout.split()[0]
        self.helper('start-dispositions', head)
        dispositions = self.project / '.ai/reviews/dispositions.md'
        dispositions.write_text(dispositions.read_text() + ''.join(rows))
        if fix_task:
            tasks = self.project / '.ai/tasks.md'
            tasks.write_text(tasks.read_text().rstrip('\n') + '\n\n' + task('T002'))
        self.commit('record triage')

    def recheck_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('workflow', HELPER)
        wf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wf)
        return wf

    def test_recheck_command_parses_withdrawn_and_upheld(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
                              '| M2 | rejected | the second defect is handled by the gate | none |\n'])
        answer = json.dumps({'answers': [{'id': 'M1', 'verdict': 'withdrawn', 'reason': 'evidence holds'},
                                         {'id': 'M2', 'verdict': 'upheld', 'reason': 'the gate does not | cover it'}]})
        result = self.tool('ai-review', '--recheck', MOCK_RECHECK=answer)
        self.assertIn('1 withdrawn, 1 upheld', result.stdout)
        prompt = (self.base / 'codex-recheck-calls').read_text()
        self.assertIn('M1\tMAJOR\tT001.txt is a fixture; the finding misreads it', prompt)
        self.assertIn('model_reasoning_effort="medium"', (self.base / 'codex-args.log').read_text().splitlines()[-1])
        answers = self.helper('recheck-verify').stdout.splitlines()
        self.assertEqual(answers, ['M1\twithdrawn\tevidence holds', 'M2\tupheld\tthe gate does not | cover it'])
        # Hand-run: recorded in its own commit, checkout clean; the report carries its binding.
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        report = (self.project / '.ai/reviews/recheck.md').read_text()
        self.assertIn('Rejected rows digest:', report)
        self.assertIn('the gate does not \\| cover it', report)
        # AI_RECHECK_EFFORT (not AI_REVIEW_EFFORT) sets the re-check effort.
        self.tool('ai-review', '--recheck', AI_RECHECK_EFFORT='low', AI_REVIEW_EFFORT='xhigh')
        self.assertIn('model_reasoning_effort="low"', (self.base / 'codex-args.log').read_text().splitlines()[-1])
        self.tool('ai-review', '--recheck', expected=1, AI_RECHECK_EFFORT='huge')

    def test_recheck_command_missing_duplicate_extra_malformed_count_as_upheld(self):
        wf = self.recheck_module()
        ids = ['M1', 'M2']
        entry = lambda finding, verdict='withdrawn', **extra: dict(id=finding, verdict=verdict, reason='ok', **extra)
        cases = {
            'missing': {'answers': [entry('M1')]},
            'duplicate': {'answers': [entry('M1'), entry('M2'), entry('M2')]},
            'malformed': {'answers': [entry('M1'), entry('M2', verdict='maybe')]},
            'extra-key': {'answers': [entry('M1'), entry('M2', note='x')]},
        }
        for name, data in cases.items():
            with self.subTest(name):
                answers, notes = wf.parse_recheck(json.dumps(data), ids)
                self.assertEqual(answers['M1'][0], 'withdrawn')
                self.assertEqual(answers['M2'][0], 'upheld')
                self.assertTrue(notes)
        self.assertEqual(wf.parse_recheck('```json\n' + json.dumps({'answers': [entry('M1'), entry('M2')]}) + '\n```',
                                          ids)[0]['M2'][0], 'withdrawn')
        for text in ('M1 withdrawn', '{"answers": [], "extra": 1}', '{"answers": {}}',
                     '{"answers": [], "answers": []}', json.dumps({'answers': [entry('M1'), entry('M2')]}) + ' trailing',
                     json.dumps({'answers': [dict(entry('M1'), reason=' ')]})):
            with self.subTest(text=text):
                answers, notes = wf.parse_recheck(text, ids)
                self.assertEqual({verdict for verdict, _ in answers.values()}, {'upheld'})
                self.assertTrue(notes)

    def test_recheck_command_extra_or_stray_entry_upholds_every_finding(self):
        # Review M1: a fully withdrawn answer set plus anything unknown must withdraw nothing.
        wf = self.recheck_module()
        ids = ['M1', 'M2']
        entry = lambda finding: dict(id=finding, verdict='withdrawn', reason='ok')
        self.assertEqual({v for v, _ in wf.parse_recheck(json.dumps({'answers': [entry('M1'), entry('M2')]}),
                                                         ids)[0].values()}, {'withdrawn'})
        for name, extra in {'unknown id': entry('M9'), 'bare string': 'M9', 'number': 7, 'list': ['M1'],
                            'id not a string': dict(entry('M1'), id=1), 'no id': {'verdict': 'withdrawn'}}.items():
            with self.subTest(name):
                answers, notes = wf.parse_recheck(json.dumps({'answers': [entry('M1'), entry('M2'), extra]}), ids)
                self.assertEqual(answers, {f: ('upheld', answers[f][1]) for f in ids})
                self.assertIn('unknown or malformed', answers['M1'][1])
                self.assertTrue(any('every finding counts as upheld' in note for note in notes))

    def test_recheck_command_binding_rejects_other_review_changed_evidence_and_tampering(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
                              '| M2 | accepted | real defect | T001 |\n'])
        self.tool('ai-review', '--recheck')
        self.helper('recheck-verify')
        report = self.project / '.ai/reviews/recheck.md'
        dispositions = self.project / '.ai/reviews/dispositions.md'
        original_report, original_rows = report.read_text(), dispositions.read_text()
        # Tampered report: a flipped answer no longer matches the host binding.
        report.write_text(original_report.replace('"upheld"', '"withdrawn"').replace('| upheld |', '| withdrawn |'))
        self.assertIn('does not match', self.helper('recheck-verify', expected=1).stderr)
        report.write_text(original_report)
        # Changed rejection evidence after the re-check.
        dispositions.write_text(original_rows.replace('the finding misreads it', 'never mind'))
        self.assertIn('different rejection evidence', self.helper('recheck-verify', expected=1).stderr)
        dispositions.write_text(original_rows)
        self.helper('recheck-verify')
        # A report from another review: a new review of the same code replaces current.md.
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='two-major-once')
        self.assertIn('another review', self.helper('recheck-verify', expected=1).stderr)
        # A missing report fails too.
        report.unlink()
        self.helper('recheck-verify', expected=1)

    def test_recheck_command_preflight_allows_pending_fix_tasks_but_not_code_changes(self):
        self.rejected_review(['| M1 | accepted | real defect | T002 |\n',
                              '| M2 | rejected | the second defect is handled by the gate | none |\n'], fix_task=True)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.tool('ai-review', '--recheck', MOCK_RECHECK=json.dumps(
            {'answers': [{'id': 'M2', 'verdict': 'withdrawn', 'reason': 'the gate covers it'}]}))
        self.assertEqual(self.helper('recheck-verify').stdout, 'M2\twithdrawn\tthe gate covers it\n')
        before = (self.base / 'codex-recheck-calls').read_text().count('reviewed HEAD=')
        # Source changed since the reviewed commit: refused before Codex runs.
        (self.project / 'src.txt').write_text('a fix')
        self.commit('fix')
        result = self.tool('ai-review', '--recheck', expected=1)
        self.assertIn('code changed since the reviewed commit: src.txt', result.stderr)
        self.assertEqual((self.base / 'codex-recheck-calls').read_text().count('reviewed HEAD='), before)

    def test_recheck_command_needs_a_rejected_finding_and_a_verified_review(self):
        self.rejected_review(['| M1 | accepted | real defect | T001 |\n', '| M2 | deferred | out of scope here | none |\n'])
        self.assertIn('no rejected BLOCKER/MAJOR', self.tool('ai-review', '--recheck', expected=1).stderr)
        current = self.project / '.ai/reviews/current.md'
        current.write_text(current.read_text().replace('second defect', 'other defect'))
        self.commit('edit review')
        self.assertIn('does not match the report', self.tool('ai-review', '--recheck', expected=1).stderr)
        self.assertFalse((self.base / 'codex-recheck-calls').exists())

    def test_recheck_command_effort_survives_recovery_like_other_settings(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', AI_RECOVER_MAX='1', AI_RECHECK_EFFORT='low',
                  MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        manifest = json.loads(next((self.base / 'host-state').rglob('run.json')).read_text())
        self.assertEqual(manifest['env']['AI_RECHECK_EFFORT'], 'low')
        wf = self.recheck_module()
        self.assertIn('AI_RECHECK_EFFORT', wf.RUN_SETTINGS)
        # ai-recover unsets and restores exactly the run settings; the user config reads it too.
        recover = (ROOT / 'scripts/ai-recover').read_text()
        unset = next(line for line in recover.splitlines() if line.startswith('unset AI_'))
        self.assertEqual(set(unset.split()[1:]), set(wf.RUN_SETTINGS))
        restore = next(line for line in recover.splitlines() if line.strip().startswith('AI_NOTIFY_CMD|'))
        self.assertEqual(set(restore.strip().rstrip(')').split('|')), set(wf.RUN_SETTINGS))
        (self.config / 'ai-toolkit').mkdir(parents=True, exist_ok=True)
        (self.config / 'ai-toolkit/config').write_text('AI_RECHECK_EFFORT=xhigh\n')
        self.run_cmd(['git', 'switch', '-q', '-c', 'feature/second'])
        env = {k: v for k, v in self.env.items() if k != 'AI_RECHECK_EFFORT'}
        self.run_cmd([str(self.project / '.ai/bin/ai-pipeline'), '--approved', '--base', 'main', '--no-pr'],
                     env=dict(env, MOCK_CLAUDE='error', AI_AUTO_RECOVER='0'), expected=1)
        manifest = json.loads(next((self.base / 'host-state').rglob('run.json')).read_text())
        self.assertEqual(manifest['env']['AI_RECHECK_EFFORT'], 'xhigh')

    # ---------------------------------------------------------------- R3: disputed findings in the pipeline
    UPHELD_M2 = json.dumps({'answers': [{'id': 'M2', 'verdict': 'upheld', 'reason': 'the gate never runs that path'}]})

    def recheck_calls(self):
        calls = self.base / 'codex-recheck-calls'
        return calls.read_text().split(': reviewed HEAD=')[1:] if calls.exists() else []

    def created_prs(self):
        return [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]

    def pr_body_text(self):
        return (self.base / 'gh.log.body.md').read_text()

    def disputes(self):
        return int(self.helper('disputes-verify').stdout)

    def commit_files(self, subject):
        sha = self.run_cmd(['git', 'log', '--format=%H', '--fixed-strings', '--grep', subject]).stdout.split()
        self.assertEqual(len(sha), 1, subject)
        return self.run_cmd(['git', 'show', '--name-only', '--format=', sha[0]]).stdout.split()

    def assert_order(self, *subjects):
        log = list(reversed(self.subjects()))
        positions = [next(i for i, s in enumerate(log) if s.startswith(subject)) for subject in subjects]
        self.assertEqual(positions, sorted(positions), log)

    def test_disputed_findings_all_withdrawn_open_a_normal_pr(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='major-once', MOCK_CLAUDE='triage-reject',
                  MOCK_RECHECK=json.dumps({'answers': [{'id': 'M1', 'verdict': 'withdrawn', 'reason': 'evidence holds'}]}))
        self.assertEqual(len(self.recheck_calls()), 1)
        self.assertEqual(self.helper('recheck-verify').stdout, 'M1\twithdrawn\tevidence holds\n')
        self.assertEqual(self.commit_files('chore(ai): record review re-check'), ['.ai/reviews/recheck.md'])
        self.assertFalse((self.project / '.ai/reviews/disputes.md').exists())
        self.assertEqual(self.disputes(), 0)
        self.assertNotIn('--draft', self.created_prs()[0])
        self.assertNotIn('Disputed findings', self.pr_body_text())

    def test_disputed_findings_one_upheld_makes_a_draft_with_the_section_on_top(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='major-once', MOCK_CLAUDE='triage-reject')
        self.assertEqual(self.disputes(), 1)
        # Report and record in ONE host commit.
        self.assertEqual(sorted(self.commit_files('chore(ai): record review re-check')),
                         ['.ai/reviews/disputes.md', '.ai/reviews/recheck.md'])
        self.assertIn('--draft', self.created_prs()[0])
        body = self.pr_body_text()
        self.assertTrue(body.startswith('## Disputed findings\n'), body[:200])
        top = body.split('## Summary')[0]
        for text in ('**M1** (MAJOR', 'M1: fixture defect at T001.txt:1.',
                     "Claude's reason: T001.txt is a fixture; the finding misreads it", "Codex's answer: still broken"):
            self.assertIn(text, top)
        self.assertIn('Resolve 1 disputed finding(s) at the PR', self.notifications())
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout, '')

    def test_disputed_findings_mixed_triage_rechecks_then_fixes_and_survives_clean_review_and_restart(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='two-major-once',
                  MOCK_CLAUDE='triage-mixed-reject', MOCK_RECHECK=self.UPHELD_M2)
        # The re-check runs right after the triage, before the accepted fix is implemented.
        self.assert_order('chore(ai): record review triage', 'chore(ai): record review re-check', 'implement T002')
        self.assertEqual(len(self.recheck_calls()), 1)
        self.assertIn('M2\tMAJOR\t', self.recheck_calls()[0])
        self.assertNotIn('M1\tMAJOR\t', self.recheck_calls()[0])
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertEqual(self.helper('review-info').stdout.split()[1:], ['0', '0', '0'])  # later clean review
        self.assertIn('--draft', self.created_prs()[0])
        self.assertTrue(self.pr_body_text().startswith('## Disputed findings\n'))
        self.assertIn('**M2** (MAJOR', self.pr_body_text())
        # A restart: the dispute is never resolved automatically; the existing PR stays a draft.
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_GH_EXISTING='1')
        self.assertIn(['pr', 'ready', '--undo', 'feature/test'], self.gh_calls())
        self.assertTrue(self.pr_body_text().startswith('## Disputed findings\n'))
        self.assertEqual(self.disputes(), 1)
        self.assertEqual(len(self.recheck_calls()), 1)

    def test_disputed_findings_resume_with_dispositions_but_no_recheck_runs_it(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
                              '| M2 | rejected | the second defect is handled by the gate | none |\n'])
        self.add_origin()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_RECHECK=json.dumps({'answers': [
            {'id': 'M1', 'verdict': 'upheld', 'reason': 'still broken'},
            {'id': 'M2', 'verdict': 'withdrawn', 'reason': 'the gate covers it'}]}))
        self.assertIn('Re-check of rejected findings (Codex)', result.stdout)
        self.assertEqual(len(self.recheck_calls()), 1)
        self.assertEqual(self.triage_calls(), 0)
        self.assertEqual(self.disputes(), 1)
        self.assertIn('--draft', self.created_prs()[0])
        body = self.pr_body_text()
        self.assertIn('**M1** (MAJOR', body)
        self.assertNotIn('**M2**', body)

    def test_disputed_findings_tampered_file_fails_verification(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once',
                  MOCK_CLAUDE='triage-reject')
        self.assertIn('resolve 1 disputed finding(s)', self.notifications())
        disputes = self.project / '.ai/reviews/disputes.md'
        original = disputes.read_text()
        disputes.write_text(original.replace('still broken', 'withdrawn after all'))
        self.commit('edit the dispute')
        self.assertIn('does not match the dispute records', self.helper('disputes-verify', expected=1).stderr)
        self.assertIn('does not match the dispute records', self.helper('disputes-record', expected=1).stderr)
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('disputes.md does not match', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.created_prs(), [])
        # Removed after a later review replaced the one it disputes: publishing stops too.
        disputes.write_text(original)
        self.commit('restore the dispute')
        self.helper('disputes-verify')
        self.run_cmd(['git', 'rm', '-q', '--', '.ai/reviews/disputes.md'])
        self.run_cmd(['git', 'commit', '-qm', 'drop the dispute'])
        self.tool('ai-review', '--base', 'main')
        self.commit('record a clean review')
        self.assertEqual(self.helper('recheck-status').stdout.strip(), 'none')
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('Publish check failed', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.created_prs(), [])

    def test_disputed_findings_no_rejected_finding_makes_no_recheck_call(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once')
        self.assertEqual(self.recheck_calls(), [])
        self.assertFalse((self.base / 'codex-recheck-calls').exists())
        self.assertFalse((self.project / '.ai/reviews/recheck.md').exists())
        self.assertEqual(self.disputes(), 0)
        self.assertFalse([s for s in self.subjects() if 're-check' in s or 'disputed' in s])

    def test_disputed_findings_interrupted_before_recheck_rechecks_original_findings_first(self):
        self.ready()
        self.add_origin()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, MOCK_CODEX='two-major-once',
                           MOCK_CLAUDE='triage-mixed-reject', MOCK_RECHECK_FAIL='1')
        self.assertIn('Pipeline stopped during re-check', result.stderr)
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.assertEqual(self.helper('recheck-status').stdout.strip(), 'pending')
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_RECHECK=self.UPHELD_M2)
        calls = self.recheck_calls()
        self.assertEqual(len(calls), 2)
        self.assertIn('M2\tMAJOR\tthe second defect is handled by the gate', calls[1])
        self.assert_order('chore(ai): record review re-check', 'implement T002')
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.helper('review-info').stdout.split()[1:], ['0', '0', '0'])
        self.assertIn('--draft', self.created_prs()[0])
        self.assertTrue(self.pr_body_text().startswith('## Disputed findings\n'))
        self.assertIn('**M2** (MAJOR', self.pr_body_text())

    def test_disputed_findings_missing_record_after_recheck_is_added_once_before_any_task(self):
        self.rejected_review(['| M1 | accepted | real defect | T002 |\n',
                              '| M2 | rejected | the second defect is handled by the gate | none |\n'], fix_task=True)
        # Interrupted after the re-check report exists, before its dispute record was written.
        self.tool('ai-review', '--recheck', MOCK_RECHECK=self.UPHELD_M2)
        self.assertFalse((self.project / '.ai/reviews/disputes.md').exists())
        self.assertEqual(self.helper('recheck-status').stdout.strip(), 'verified')
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assertEqual(len(self.recheck_calls()), 1)  # not re-checked again
        self.assertEqual(self.commit_files('chore(ai): record disputed findings'), ['.ai/reviews/disputes.md'])
        self.assert_order('chore(ai): record disputed findings', 'implement T002')
        self.assertEqual(self.disputes(), 1)
        self.assertIn('**M2** (MAJOR', self.pr_body_text())
        self.assertIn('--draft', self.created_prs()[0])
        # A restart never duplicates the record.
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_GH_EXISTING='1')
        self.assertEqual(self.disputes(), 1)
        self.assertEqual(self.subjects().count('chore(ai): record disputed findings'), 1)

    def test_disputed_findings_uncommitted_recheck_report_is_committed_with_its_record(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
                              '| M2 | accepted | real defect | T001 |\n'])
        # A stop between the pipeline's re-check and its host commit leaves the report uncommitted.
        self.tool('ai-review', '--recheck', AI_PIPELINE='1')
        self.assertIn('.ai/reviews/recheck.md', self.run_cmd(['git', 'status', '--porcelain']).stdout)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertEqual(len(self.recheck_calls()), 1)
        self.assertEqual(sorted(self.commit_files('chore(ai): record review re-check')),
                         ['.ai/reviews/disputes.md', '.ai/reviews/recheck.md'])
        self.assertEqual(self.disputes(), 1)
        # Re-running reconciliation on the same verified re-check adds nothing.
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout
        self.assertEqual(self.helper('disputes-record').stdout.strip(), '0')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertEqual(self.disputes(), 1)
        self.assertEqual(self.run_cmd(['git', 'log', '--format=%s', head.strip() + '..HEAD']).stdout.count('re-check'), 0)
        self.assertEqual(self.subjects().count('chore(ai): record disputed findings'), 0)
        # Any other leftover still blocks the start.
        (self.project / 'src.txt').write_text('stray')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertIn('Start from a clean checkpoint', result.stderr)

    # --- disputes_lifecycle: a merged PR's dispute file is inherited by later branches ---

    def merged_dispute_then_next_branch(self):
        """feature/test records one upheld dispute and the human merges it into main; then a
        new branch with its own task starts from main, inheriting the dispute file."""
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once',
                  MOCK_CLAUDE='triage-reject')
        self.assertEqual(self.disputes(), 1)
        self.run_cmd(['git', 'switch', '-q', 'main'])
        self.run_cmd(['git', 'merge', '-q', '--no-ff', '-m', 'merge feature/test', 'feature/test'])
        self.run_cmd(['git', 'switch', '-q', '-c', 'feature/next'])
        tasks = self.project / '.ai/tasks.md'
        tasks.write_text(tasks.read_text().rstrip('\n') + '\n\n' + task('T002'))
        self.commit('plan T002')
        (self.base / 'codex-calls').unlink()
        self.add_origin()
        return (self.project / '.ai/reviews/disputes.md').read_text()

    def disputes_from(self, base, expected=0):
        return self.run_cmd(['python3', str(HELPER), 'disputes-verify'], expected=expected,
                            env=dict(self.env, AI_DISPUTES_BASE=base))

    def test_disputes_lifecycle_inherited_unchanged_file_publishes_a_normal_pr(self):
        inherited = self.merged_dispute_then_next_branch()
        self.assertEqual(self.disputes_from('main').stdout.strip(), '0')
        # Without a base nothing is inherited: the branch's (empty) host records don't match.
        self.helper('disputes-verify', expected=1)
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertNotIn('--draft', self.created_prs()[0])
        self.assertNotIn('Disputed findings', self.pr_body_text())
        self.assertNotIn('disputed finding', self.notifications().splitlines()[-1])
        self.assertEqual((self.project / '.ai/reviews/disputes.md').read_text(), inherited)
        self.assertEqual(self.subjects().count('chore(ai): record disputed findings'), 0)

    def test_disputes_lifecycle_edited_inherited_file_fails(self):
        inherited = self.merged_dispute_then_next_branch()
        disputes = self.project / '.ai/reviews/disputes.md'
        disputes.write_text(inherited.replace('still broken', 'withdrawn after all'))
        self.commit('edit the inherited dispute')
        self.assertIn('does not match the dispute records', self.disputes_from('main', expected=1).stderr)
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assertIn('disputes.md does not match', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.created_prs(), [])
        # Removing it is an edit too.
        self.run_cmd(['git', 'rm', '-q', '--', '.ai/reviews/disputes.md'])
        self.run_cmd(['git', 'commit', '-qm', 'drop the inherited dispute'])
        self.disputes_from('main', expected=1)

    def test_disputes_lifecycle_new_dispute_on_later_branch_drafts_and_lists_only_it(self):
        inherited = self.merged_dispute_then_next_branch()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX='major-once',
                  MOCK_CLAUDE='triage-reject', MOCK_RECHECK=json.dumps(
                      {'answers': [{'id': 'M1', 'verdict': 'upheld', 'reason': 'still broken on next'}]}))
        self.assertEqual(self.disputes_from('main').stdout.strip(), '1')
        text = (self.project / '.ai/reviews/disputes.md').read_text()
        self.assertTrue(text.startswith(inherited.rstrip('\n')), text)
        self.assertIn('## D2 — M1 (MAJOR)', text[len(inherited):])
        self.assertIn('still broken on next', text[len(inherited):])
        self.assertIn('--draft', self.created_prs()[0])
        body = self.pr_body_text()
        self.assertIn('Codex upheld 1 finding(s)', body)
        self.assertEqual(body.count('**M1** (MAJOR'), 1)
        self.assertIn("Codex's answer: still broken on next", body)
        self.assertNotIn("Codex's answer: still broken\n", body)
        # Editing either part still fails.
        for edit in (text.replace('still broken\n', 'gone\n', 1), text.replace('still broken on next', 'gone')):
            (self.project / '.ai/reviews/disputes.md').write_text(edit)
            self.disputes_from('main', expected=1)
        (self.project / '.ai/reviews/disputes.md').write_text(text)
        self.assertEqual(self.disputes_from('main').stdout.strip(), '1')

    # --- toolkit_upgrade: version stamp and setup-project --upgrade ---

    def old_toolkit(self, drop=()):
        """A copy of the toolkit that differs from this one: an 'older' release."""
        import shutil
        old = self.base / 'toolkit-a'
        shutil.copytree(ROOT / 'scripts', old / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'templates', old / 'templates')
        for relative in drop:
            (old / relative).unlink()
            if relative == 'scripts/ai-task':  # the older setup did not know the command either
                workflow = old / 'scripts/lib/workflow.py'
                import re
                workflow.write_text(re.sub(r"'ai-task',\s*", '', workflow.read_text()))
        for relative in ('scripts/ai-status', 'scripts/lib/workflow.py', 'templates/.ai/prompts/runner.md'):
            with (old / relative).open('a') as file:
                file.write('\n# older release\n' if not relative.endswith('.md') else '\nolder release\n')
        return old

    def setup_old(self, old):
        return self.run_cmd([str(old / 'scripts/setup-project'), str(self.project)])

    def upgrade(self, *options, expected=0):
        return self.setup_project('--upgrade', *options) if expected == 0 else self.run_cmd(
            [str(ROOT / 'scripts/setup-project'), '--upgrade', *options, str(self.project)], expected=expected)

    def snapshot(self):
        return {str(p.relative_to(self.project)): (p.read_bytes(), p.stat().st_mode) for p in self.project.rglob('*')
                if p.is_file() and '.git' not in p.parts}

    def stamp_files(self):
        return json.loads((self.project / '.ai/toolkit-version').read_text())['files']

    def sha(self, path):
        import hashlib
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def test_toolkit_upgrade_fresh_setup_writes_stamp(self):
        self.setup_project()
        data = json.loads((self.project / '.ai/toolkit-version').read_text())
        self.assertIn('toolkit_commit', data)
        self.assertEqual(data['files']['.ai/bin/ai-task'], self.sha(ROOT / 'scripts/ai-task'))
        self.assertEqual(data['files']['.ai/prompts/recheck.md'], self.sha(ROOT / 'templates/.ai/prompts/recheck.md'))
        self.assertNotIn('.ai/validate', data['files'])

    def test_toolkit_upgrade_preview_changes_nothing(self):
        self.setup_old(self.old_toolkit())
        before = self.snapshot()
        result = self.upgrade()
        self.assertIn('REPLACE .ai/bin/ai-status', result.stdout)
        self.assertIn('Plan only', result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_toolkit_upgrade_replaces_outdated_and_keeps_project_files(self):
        self.setup_old(self.old_toolkit())
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\ntrue\n')
        (self.project / '.ai/permissions.allow').write_text('Bash(ls)\n')
        self.upgrade('--apply')
        for relative, source in (('.ai/bin/ai-status', 'scripts/ai-status'),
                                 ('.ai/bin/lib/workflow.py', 'scripts/lib/workflow.py'),
                                 ('.ai/prompts/runner.md', 'templates/.ai/prompts/runner.md')):
            self.assertEqual((self.project / relative).read_bytes(), (ROOT / source).read_bytes())
        self.assertEqual((self.project / '.ai/validate').read_text(), '#!/usr/bin/env bash\ntrue\n')
        self.assertEqual((self.project / '.ai/permissions.allow').read_text(), 'Bash(ls)\n')
        self.assertEqual(self.stamp_files()['.ai/bin/ai-status'], self.sha(ROOT / 'scripts/ai-status'))
        self.assertTrue(os.access(self.project / '.ai/bin/ai-status', os.X_OK))

    def test_toolkit_upgrade_two_applies_are_stable(self):
        self.setup_old(self.old_toolkit())
        self.upgrade('--apply')
        after_first = self.snapshot()
        result = self.upgrade('--apply')
        self.assertEqual(self.snapshot(), after_first)
        self.assertIn('Upgraded 0 file(s)', result.stdout)

    def test_toolkit_upgrade_local_edit_refuses_group_and_force_installs_all(self):
        self.setup_old(self.old_toolkit())
        with (self.project / '.ai/bin/lib/workflow.py').open('a') as file:
            file.write('\n# local edit\n')
        before = self.snapshot()
        result = self.upgrade('--apply', expected=1)
        self.assertIn('.ai/bin/lib/workflow.py', result.stdout)
        self.assertIn('Nothing was changed', result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.tool('ai-status')  # the old install is still usable
        self.upgrade('--apply', '--force')
        for relative in ('ai-status', 'lib/workflow.py', 'ai-pipeline', 'lib/common.sh'):
            source = ROOT / 'scripts' / relative
            self.assertEqual((self.project / '.ai/bin' / relative).read_bytes(), source.read_bytes())
        # The installed pipeline still runs end to end with the mock agents.
        self.run_cmd(['git', 'add', '--all'])
        self.commit('upgrade')
        self.run_cmd(['git', 'switch', '-c', 'feature/test'])
        (self.project / '.ai/tasks.md').write_text(task('T001'))
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nset -euo pipefail\npython3 -c "assert 2 + 2 == 4"\n')
        self.commit('approved plan and real fixture gate')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('Status: DONE', (self.project / '.ai/tasks.md').read_text())

    def test_toolkit_upgrade_repeated_setup_does_not_bless_local_edit(self):
        self.setup_old(self.old_toolkit())
        baseline = self.stamp_files()['.ai/bin/ai-status']
        with (self.project / '.ai/bin/ai-status').open('a') as file:
            file.write('\n# local edit\n')
        self.setup_project()
        self.assertEqual(self.stamp_files()['.ai/bin/ai-status'], baseline)
        self.upgrade('--apply', expected=1)

    def test_toolkit_upgrade_legacy_install_needs_force_for_differing_files(self):
        self.setup_old(self.old_toolkit())
        (self.project / '.ai/toolkit-version').unlink()
        result = self.upgrade()
        self.assertIn('legacy install', result.stdout)
        self.assertIn('EDITED', result.stdout)
        self.upgrade('--apply', expected=1)
        self.upgrade('--apply', '--force')
        self.assertEqual((self.project / '.ai/bin/ai-status').read_bytes(), (ROOT / 'scripts/ai-status').read_bytes())
        self.assertEqual(self.stamp_files()['.ai/bin/ai-task'], self.sha(ROOT / 'scripts/ai-task'))
        (self.project / '.ai/toolkit-version').write_text('{not json')  # malformed behaves like missing
        self.assertIn('malformed', self.upgrade().stdout)

    def test_toolkit_upgrade_creates_missing_files_in_older_inventory(self):
        old = self.old_toolkit(drop=('scripts/ai-task', 'templates/.ai/prompts/recheck.md'))
        self.setup_old(old)
        self.assertFalse((self.project / '.ai/bin/ai-task').exists())
        self.assertFalse((self.project / '.ai/prompts/recheck.md').exists())
        self.assertIn('CREATE .ai/bin/ai-task', self.upgrade().stdout)
        self.assertFalse((self.project / '.ai/bin/ai-task').exists())
        self.upgrade('--apply')
        self.assertTrue(os.access(self.project / '.ai/bin/ai-task', os.X_OK))
        self.assertTrue((self.project / '.ai/prompts/recheck.md').is_file())
        self.assertIn('recheck.md', json.dumps(self.stamp_files()))
        (self.project / '.ai/tasks.md').write_text(task('T001', status='DONE'))
        self.assertIn('DONE', self.tool('ai-task', 'show', 'T001').stdout)

    def test_toolkit_upgrade_write_failure_rolls_back_everything(self):
        old = self.old_toolkit(drop=('scripts/ai-task', 'templates/.ai/prompts/recheck.md'))
        self.setup_old(old)
        self.assertIn('CREATE .ai/bin/ai-task', self.upgrade().stdout)
        before = self.snapshot()
        # Fail the rename of the LATER file only, after earlier files were already replaced/created.
        inject = ('import os, sys\n'
                  f'sys.path.insert(0, {str(ROOT / "scripts/lib")!r})\n'
                  'import workflow\n'
                  'real = os.replace\n'
                  'def replace(src, dst, *a, **k):\n'
                  '    if str(dst).endswith(".ai/bin/lib/workflow.py"):\n'
                  '        raise OSError(28, "No space left on device (injected)")\n'
                  '    return real(src, dst, *a, **k)\n'
                  'os.replace = replace\n'
                  'try:\n'
                  '    workflow.main()\n'
                  'except (ValueError, OSError) as error:\n'
                  '    print(f"Error: {error}", file=sys.stderr)\n'
                  '    sys.exit(1)\n')
        result = self.run_cmd(['python3', '-c', inject, 'setup', '--upgrade', '--apply', str(self.project)],
                              expected=1)
        self.assertIn('injected', result.stderr)
        self.assertIn('every file was restored', result.stderr)
        self.assertNotIn('Upgraded', result.stdout)
        after = self.snapshot()  # bytes and modes; created files and temps are gone
        self.assertEqual(sorted(after), sorted(before))
        self.assertEqual([k for k in after if after[k] != before[k]], [])
        self.assertFalse((self.project / '.ai/bin/ai-task').exists())
        self.assertFalse((self.project / '.ai/prompts/recheck.md').exists())
        self.tool('ai-status')  # the old install is still usable
        self.upgrade('--apply')  # and a later apply succeeds
        self.assertEqual((self.project / '.ai/bin/lib/workflow.py').read_bytes(),
                         (ROOT / 'scripts/lib/workflow.py').read_bytes())
        self.assertEqual(self.stamp_files()['.ai/bin/ai-task'], self.sha(ROOT / 'scripts/ai-task'))

    def test_toolkit_upgrade_refuses_symlinked_target(self):
        self.setup_old(self.old_toolkit())
        target = self.project / '.ai/bin/ai-status'
        target.unlink()
        target.symlink_to(self.base / 'elsewhere')
        result = self.upgrade('--apply', expected=1)
        self.assertIn('symlink', result.stderr + result.stdout)

    def pr_body_for(self, handoff):
        (self.project / '.ai/handoff.md').write_text(handoff)
        return self.helper('pr-body', '0', '0').stdout

    def test_pr_body_flow_section_is_copied_when_present(self):
        self.setup_project()
        base = '# Handoff\n\n## Manual testing for the human\n1. Try it.\n\n## Next action\nNone.\n'
        plain = self.pr_body_for(base)
        self.assertNotIn('Flow chart', plain)
        body = self.pr_body_for(base.replace('## Manual', '## Flow chart\nFlow chart updated: audited.\n\n## Manual'))
        self.assertIn('Flow chart updated: audited.', body)
        self.assertLess(body.index('## Summary'), body.index('Flow chart updated'))
        self.assertLess(body.index('Flow chart updated'), body.index('## Tasks'))
        self.assertEqual(body.replace('Flow chart updated: audited.\n\n', ''), plain)

    SPLIT_HANDOFF = ('# Handoff\n\n## Manual testing for the human\n### Needs you\n{needs}\n\n'
                     '### Covered by automated tests\n1. Drag fails: `test_drag_fails`\n'
                     '2. Resize works without a name\n\n## Next action\nNone.\n')

    def test_manual_testing_render_pr_body_splits_needs_you_from_automated(self):
        self.setup_project()
        body = self.pr_body_for(self.SPLIT_HANDOFF.format(needs='1. Check it on your phone.'))
        self.assertLess(body.index('### Needs you'), body.index('Check it on your phone.'))
        self.assertLess(body.index('Check it on your phone.'), body.index('### Covered by automated tests'))
        self.assertIn('<details><summary>2 automated checks</summary>', body)
        self.assertIn('</details>', body)
        self.assertIn('`test_drag_fails`\n', body)
        self.assertIn('Resize works without a name ⚠ no test named', body)
        self.assertNotIn('test_drag_fails` ⚠', body)

    def test_manual_testing_render_none_says_everything_is_automated(self):
        self.setup_project()
        body = self.pr_body_for(self.SPLIT_HANDOFF.format(needs='None.'))
        self.assertIn('None — everything below is automated.', body)

    def test_manual_testing_render_finish_summary_counts_only_needs_you(self):
        self.ready()
        self.add_origin()
        (self.project / '.ai/handoff.md').write_text(self.SPLIT_HANDOFF.format(needs='None'))
        self.commit('handoff with only automated steps')
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        notes = self.notifications()
        self.assertIn('1. Nothing to test by hand (2 automated checks in the PR)', notes)
        self.assertNotIn('manual step', notes)

    def test_manual_testing_render_legacy_handoff_is_unchanged(self):
        self.setup_project()
        body = self.pr_body_for('# Handoff\n\n## Manual testing for the human\n1. Try it.\n2. Again.\n\n## Next action\nNone.\n')
        self.assertIn('## How to test\n\n1. Try it.\n2. Again.\n\n---', body)
        self.assertNotIn('Needs you', body)
        self.assertNotIn('<details>', body)

    def test_manual_testing_prompts_describe_the_split(self):
        handoff = (ROOT / 'templates/.ai/handoff.md').read_text()
        self.assertIn('### Needs you', handoff)
        self.assertIn('### Covered by automated tests', handoff)
        for name in ('.ai/prompts/runner.md', '.ai/prompts/triage.md', '.ai/prompts/fix-review.md',
                     '.ai/prompts/review.md', 'CLAUDE.md', 'AGENTS.md'):
            with self.subTest(file=name):
                text = ' '.join((ROOT / 'templates' / name).read_text().split())
                self.assertIn('Needs you', text)
                self.assertIn('Covered by automated tests', text)

    def test_manual_testing_prompts_fresh_handoff_renders_in_pr_body(self):
        self.setup_project()
        body = self.helper('pr-body', '0', '0').stdout
        self.assertIn('## Summary', body)
        self.assertIn('## Tasks', body)

    def test_pr_body_flow_this_repo_declares_the_flow_chart(self):
        handoff = (ROOT / '.ai/handoff.md').read_text()
        self.assertIn('## Flow chart\nFlow chart updated', handoff)
        self.setup_project()
        self.assertIn('Flow chart updated', self.pr_body_for(handoff))

    def test_script_modes_all_shebang_scripts_are_executable(self):
        scripts_dir = ROOT / 'scripts'
        for script in scripts_dir.glob('*'):
            if not script.is_file():
                continue
            with self.subTest(script=script.name):
                first_line = script.read_text(errors='ignore').split('\n')[0]
                if first_line.startswith('#!'):
                    # Has shebang: must be executable
                    self.assertTrue(os.access(script, os.X_OK),
                                    f'{script.name} has shebang but is not executable')

    def deps_fixture(self, setup_text):
        (self.project / '.ai').mkdir(exist_ok=True)
        (self.project / '.ai/ci-setup').write_text(setup_text)

    def deps(self):
        return self.helper('deps-status').stdout.strip()

    def test_deps_status_declared_inputs_and_outputs(self):
        self.deps_fixture('#!/usr/bin/env bash\n# ai-deps-inputs: deps.lock extra/*.lock\n'
                          '# ai-deps-outputs: vendor-deps\nmkdir -p vendor-deps\n')
        (self.project / 'deps.lock').write_text('one\n')
        (self.project / 'vendor-deps').mkdir()
        self.assertEqual(self.deps(), 'stale no dependency stamp (.ai/local/deps.json)')
        self.helper('deps-record')
        self.assertEqual(self.deps(), 'current')
        recorded = json.loads((self.project / '.ai/local/deps.json').read_text())
        self.assertEqual(list(recorded['inputs']), ['deps.lock'])
        (self.project / 'deps.lock').write_text('two\n')
        self.assertEqual(self.deps(), 'stale inputs changed: changed deps.lock')
        self.helper('deps-record')
        (self.project / 'extra').mkdir()
        (self.project / 'extra/a.lock').write_text('a\n')
        self.assertEqual(self.deps(), 'stale inputs changed: added extra/a.lock')
        self.helper('deps-record')
        self.assertEqual(self.deps(), 'current')
        (self.project / 'extra/a.lock').unlink()
        self.assertEqual(self.deps(), 'stale inputs changed: removed extra/a.lock')
        self.helper('deps-record')
        with (self.project / '.ai/ci-setup').open('a') as file:
            file.write('true\n')
        self.assertEqual(self.deps(), 'stale .ai/ci-setup changed')
        self.helper('deps-record')
        self.assertEqual(self.deps(), 'current')
        (self.project / 'vendor-deps').rmdir()
        self.assertEqual(self.deps(), 'stale missing output vendor-deps')

    def test_deps_status_default_lockfiles_and_node_modules(self):
        self.deps_fixture((ROOT / 'templates/.ai/ci-setup').read_text())
        (self.project / 'package.json').write_text('{}\n')
        (self.project / 'package-lock.json').write_text('{"lockfileVersion": 3}\n')
        (self.project / 'requirements-dev.txt').write_text('pytest\n')
        self.assertTrue(self.deps().startswith('stale no dependency stamp'))
        self.helper('deps-record')
        self.assertEqual(self.deps(), 'stale missing output node_modules')
        recorded = json.loads((self.project / '.ai/local/deps.json').read_text())
        self.assertEqual(sorted(recorded['inputs']), ['package-lock.json', 'requirements-dev.txt'])
        (self.project / 'node_modules').mkdir()
        (self.project / '.ai/local/deps.json').unlink()
        self.assertTrue(self.deps().startswith('stale no dependency stamp'))
        self.helper('deps-record')
        self.assertEqual(self.deps(), 'current')
        (self.project / 'package-lock.json').write_text('{"lockfileVersion": 3, "x": 1}\n')
        self.assertEqual(self.deps(), 'stale inputs changed: changed package-lock.json')

    def test_deps_status_installer_without_lockfiles_runs_once(self):
        self.deps_fixture('#!/usr/bin/env bash\necho installing\n')
        self.assertTrue(self.deps().startswith('stale no dependency stamp'))
        self.helper('deps-record')
        self.assertEqual(self.deps(), 'current')
        self.assertEqual(self.deps(), 'current')
        self.assertEqual(json.loads((self.project / '.ai/local/deps.json').read_text())['inputs'], {})

    def test_deps_status_rejects_paths_outside_the_checkout(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret.lock').write_text('x\n')
        (self.project / 'escape.lock').symlink_to(outside / 'secret.lock')
        (self.project / 'escape-dir').symlink_to(outside)
        cases = (('# ai-deps-inputs: ../outside/secret.lock', 'must be relative'),
                 (f'# ai-deps-inputs: {outside}/secret.lock', 'must be relative'),
                 ('# ai-deps-outputs: ../vendor', 'must be relative'),
                 ('# ai-deps-inputs: escape.lock', 'leaves the checkout'),
                 ('# ai-deps-inputs: *.lock', 'leaves the checkout'),
                 ('# ai-deps-outputs: escape-dir', 'leaves the checkout'))
        for declaration, message in cases:
            with self.subTest(declaration=declaration):
                self.deps_fixture(f'#!/usr/bin/env bash\n{declaration}\n')
                for command in ('deps-status', 'deps-record'):
                    result = self.helper(command, expected=1)
                    self.assertIn(message, result.stderr)
                self.assertFalse((self.project / '.ai/local/deps.json').exists())

    def tree_snapshot(self):
        return self.helper('tree-snapshot').stdout.strip()

    def test_deps_status_tree_snapshot_covers_project_files(self):
        (self.project / '.gitignore').write_text('ignored/\n')
        (self.project / 'a.txt').write_text('one\n')
        self.commit()
        self.run_cmd(['git', 'config', 'core.filemode', 'false'])
        (self.project / 'a.txt').write_text('dirty\n')
        seen = [self.tree_snapshot()]
        self.assertEqual(self.tree_snapshot(), seen[0])
        (self.project / 'ignored').mkdir()
        (self.project / 'ignored/dep.js').write_text('installed\n')
        (self.project / '.ai/local').mkdir(parents=True)
        (self.project / '.ai/local/deps.log').write_text('log\n')
        self.assertEqual(self.tree_snapshot(), seen[0])

        def changed(action):
            action()
            seen.append(self.tree_snapshot())
            self.assertNotIn(seen[-1], seen[:-1])

        changed(lambda: (self.project / 'a.txt').write_text('dirty again\n'))
        changed(lambda: (self.project / 'a.txt').chmod(0o755))
        changed(lambda: self.run_cmd(['git', 'add', '--', 'a.txt']))
        changed(lambda: self.run_cmd(['git', 'commit', '-qm', 'change']))
        changed(lambda: (self.project / 'new.txt').write_text('untracked\n'))
        changed(lambda: (self.project / 'a.txt').unlink())

    def test_deps_status_tree_snapshot_covers_submodules(self):
        origin = self.base / 'sub-origin'
        origin.mkdir()

        def sub_git(cwd, *args):
            subprocess.run(['git', '-c', 'user.name=T', '-c', 'user.email=t@example.invalid',
                            '-c', 'commit.gpgsign=false', *args], cwd=cwd, env=self.env,
                           check=True, capture_output=True)
        sub_git(origin, 'init', '-q', '-b', 'main')
        (origin / 'file.txt').write_text('committed\n')
        sub_git(origin, 'add', 'file.txt')
        sub_git(origin, 'commit', '-qm', 'sub')
        self.run_cmd(['git', '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q',
                      str(origin), 'sub'])
        self.commit('add submodule')
        first = self.tree_snapshot()
        self.assertEqual(self.tree_snapshot(), first)
        seen = [first]

        def changed(action):
            action()
            seen.append(self.tree_snapshot())
            self.assertNotIn(seen[-1], seen[:-1])

        sub = self.project / 'sub'
        changed(lambda: (sub / 'file.txt').write_text('modified\n'))
        changed(lambda: (sub / 'file.txt').write_text('modified again\n'))
        changed(lambda: (sub_git(sub, 'add', 'file.txt'), sub_git(sub, 'commit', '-qm', 'move')))

    def test_deps_status_template_ci_setup(self):
        template = ROOT / 'templates/.ai/ci-setup'
        self.run_cmd(['bash', '-n', str(template)])
        result = self.run_cmd(['bash', str(template)])
        self.assertIn('installing nothing', result.stdout)
        text = template.read_text()
        self.assertIn('# ai-deps-inputs:', text)
        self.assertIn('# ai-deps-outputs:', text)
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ['.git'])

    # ---------------------------------------------------------------- host dependency setup
    def deps_ready(self, queue=None):
        self.ready(queue)
        (self.project / '.ai/ci-setup').write_text(DEPS_SETUP)
        (self.project / 'deps.lock').write_text('dep 1\n')
        (self.project / 'tracked.txt').write_text('tracked\n')
        with (self.project / '.gitignore').open('a') as file:
            file.write('/vendor-deps/\n')
        self.commit('dependency fixture')
        return self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()

    def deps_calls(self):
        calls = self.base / 'deps-calls'
        return calls.read_text().count('call') if calls.exists() else 0

    def assert_deps_stopped(self, message):
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn(message, error)
        self.assertIn('.ai/ci-setup', error)
        self.assertRegex(error, r'see \.ai/local/deps-\w{8}\.log')
        self.assertFalse((self.project / '.ai/local/deps.json').exists())
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())

    def test_deps_runner_installs_once_before_the_first_task(self):
        base = self.deps_ready()
        result = self.tool('ai-run', '--approved', MOCK_REQUIRE='vendor-deps/deps.lock')
        self.assertIn('Dependency setup (.ai/ci-setup): no dependency stamp', result.stdout)
        self.assertIn('Dependencies installed', result.stdout)
        self.assertEqual(self.deps_calls(), 1)
        self.assertEqual(self.helper('deps-status').stdout.strip(), 'current')
        self.helper('tasks', 'complete')
        # The install changed no project file: only the task and runner commits follow.
        subjects = self.run_cmd(['git', 'log', '--format=%s', f'{base}..HEAD']).stdout.splitlines()
        self.assertEqual(subjects, ['chore(ai): record review handoff',
                                    'chore(ai): record T001 runner checkpoint', 'implement T001'])
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')

        def add_task(task_id, lock=None):
            if lock:
                (self.project / 'deps.lock').write_text(lock)
            with (self.project / '.ai/tasks.md').open('a') as file:
                file.write('\n' + task(task_id))
            self.commit('add ' + task_id)
        # Unchanged inputs: the next ai-run does not install again.
        add_task('T002')
        self.tool('ai-run', '--approved', MOCK_REQUIRE='vendor-deps/deps.lock')
        self.assertEqual(self.deps_calls(), 1)
        # A changed lockfile installs again at the next start that runs a task.
        add_task('T003', 'dep 2\n')
        self.tool('ai-run', '--approved', MOCK_REQUIRE='vendor-deps/deps.lock')
        self.assertEqual(self.deps_calls(), 2)
        self.assertEqual((self.project / 'vendor-deps/deps.lock').read_text(), 'dep 2\n')

    def test_deps_runner_failed_or_changing_installer_stops_before_claude(self):
        base = self.deps_ready()
        cases = (('fail', {}, 'Dependency setup (.ai/ci-setup) failed (exit 1)'),
                 ('sleep', {'AI_DEPS_TIMEOUT': '1'}, 'failed (exit 124, timeout after 1s)'),
                 ('overwrite', {}, 'Dependency setup changed project files'),
                 ('untracked', {}, 'Dependency setup changed project files'),
                 ('commit', {}, 'Dependency setup changed project files'),
                 ('overwrite-fail', {}, 'Dependency setup changed project files'))
        for mode, env, message in cases:
            with self.subTest(mode=mode):
                self.tool('ai-run', '--approved', expected=1, MOCK_DEPS=mode, **env)
                self.assert_deps_stopped(message)
                self.assertEqual(self.deps_calls(), 1)
                self.run_cmd(['git', 'reset', '-q', '--hard', base])
                self.run_cmd(['git', 'clean', '-fdq'])
                (self.base / 'deps-calls').unlink()

    def test_deps_runner_install_is_capped_by_the_run_time(self):
        import time
        self.deps_ready()
        started = time.monotonic()
        self.tool('ai-run', '--approved', '--run-timeout', '5', expected=1,
                  MOCK_DEPS='sleep', AI_DEPS_TIMEOUT='600')
        self.assertLess(time.monotonic() - started, 15)
        self.assert_deps_stopped('timeout after')
        self.run_cmd(['git', 'checkout', '--', '.ai/run-log.md'])  # the stop's run-log line
        self.tool('ai-run', '--approved', expected=1, AI_DEPS_TIMEOUT='soon')
        self.assertIn('invalid AI_DEPS_TIMEOUT', (self.project / '.ai/local/last-error').read_text())

    def test_deps_runner_complete_queue_installs_nothing(self):
        self.deps_ready(task('T001', 'DONE'))
        self.tool('ai-run', '--approved')
        self.assertEqual(self.deps_calls(), 0)

    def deps_recovery(self, mode):
        self.deps_ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_DEPS=mode)
        notes = self.notifications()
        self.assertIn('⛔ STOPPED, needs you: feature/test stopped during implementation', notes)
        self.assertIn('Dependency setup', notes)
        self.assertIn('this kind of stop always needs a human', notes)
        self.assertEqual(self.recovery_calls(), [])
        self.assertNotIn('recovery checkpoint', self.run_cmd(['git', 'log', '--format=%s']).stdout)
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        self.assertFalse(any(c[:2] == ['pr', 'create'] for c in self.gh_calls()))
        self.assertEqual(self.deps_calls(), 1)

    def test_deps_runner_failed_install_escalates_without_recovery(self):
        self.deps_recovery('fail-once')

    def test_deps_runner_changing_install_escalates_without_recovery(self):
        self.deps_recovery('change-once')

    def deps_recovery_run(self, mode, expected):
        """The session dies leaving a changed deps.lock; recovery decides commit_and_rerun.
        The gate passes only when vendor-deps/ matches deps.lock."""
        self.deps_ready(task('T001').replace('T001.txt\n', 'T001.txt, partial.txt, deps.lock\n'))
        (self.project / '.ai/validate').write_text(
            '#!/usr/bin/env bash\nset -euo pipefail\ncmp -s deps.lock vendor-deps/deps.lock\n')
        self.commit('gate that needs installed dependencies')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=expected,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error-once-partial', MOCK_RECOVER='commit_and_rerun',
                  MOCK_EXTRA_FILE='deps.lock', MOCK_DEPS=mode, MOCK_REQUIRE='vendor-deps/deps.lock')
        self.assertEqual(len(self.recovery_calls()), 1)
        self.assertEqual(self.deps_calls(), 2)  # ai-run's first install, then recovery's
        return self.notifications()

    def assert_deps_recovery_escalated(self, notes, message):
        self.assertIn('⛔ STOPPED, needs you: feature/test stopped during implementation', notes)
        self.assertIn('but dependency setup failed: Dependency setup', notes)
        self.assertIn(message, notes)
        self.assertIn('Next: inspect .ai/ci-setup and the log', notes)
        self.assertNotIn('🔧 Recovered', notes)
        self.assertNotIn('▶ RESUMED', notes)
        self.assertNotIn('recovery checkpoint', self.run_cmd(['git', 'log', '--format=%s']).stdout)
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text().count('call'), 1)
        self.assertIn('deps.lock', self.run_cmd(['git', 'status', '--porcelain']).stdout)

    def test_deps_recovery_installs_before_the_gate_and_resumes(self):
        notes = self.deps_recovery_run('ok', 0)
        self.assertEqual(notes.count('🔧 Recovered'), 1)
        self.assertIn('🔧 Recovered (1/2)', notes)
        self.assertIn('🏁 FINISHED', notes)
        self.assertNotIn('⛔', notes)
        log = self.run_cmd(['git', 'log', '--format=%H %s']).stdout.splitlines()
        checkpoint = next(line.split()[0] for line in log if 'recovery checkpoint (validated leftover work)' in line)
        files = self.run_cmd(['git', 'show', '--name-only', '--format=', checkpoint]).stdout.split()
        self.assertIn('deps.lock', files)
        self.assertIn('partial.txt', files)
        self.assertNotIn('vendor-deps/deps.lock', self.run_cmd(['git', 'ls-files']).stdout)
        self.assertEqual((self.project / 'vendor-deps/deps.lock').read_text(), 'not in the plan')
        self.assertEqual(self.helper('deps-status').stdout.strip(), 'current')
        self.helper('tasks', 'complete')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')

    def test_deps_recovery_failed_install_escalates_without_a_commit(self):
        notes = self.deps_recovery_run('fail-later', 1)
        self.assert_deps_recovery_escalated(notes, 'failed (exit 1)')

    def test_deps_recovery_changing_install_escalates_without_a_commit(self):
        notes = self.deps_recovery_run('change-later', 1)
        self.assert_deps_recovery_escalated(notes, 'changed project files')

    def test_deps_runner_pipeline_end_to_end(self):
        self.deps_ready()
        self.add_origin()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main',
                           MOCK_REQUIRE='vendor-deps/deps.lock')
        self.assertIn('Pull request: https://github.com/example/project/pull/7', result.stdout)
        self.assertEqual(self.deps_calls(), 1)
        self.assertEqual(len([c for c in self.gh_calls() if c[:2] == ['pr', 'create']]), 1)
        self.assertEqual(self.helper('deps-status').stdout.strip(), 'current')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')


class DocsConsistencyTest(unittest.TestCase):
    """R10: README.md and docs/workflow.md must describe what the code does."""

    FILES = ('README.md', 'docs/workflow.md')

    FORBIDDEN = (
        'never stages application files',
        'does not invoke `git push`',
        'never invokes push',
        'no automatic provider retries',
        'no automatic retry of provider failures',
        'stops on reported permission denials',
        'denied permissions, timeouts',
        'permission denial, or crash',
    )

    REQUIRED = (
        'denials are logged and the run continues',
        "automatic checkpoints stage the session's output except secret-looking files",
        'the pipeline pushes the feature branch and opens the pull request',
        'usage limits pause and resume',
        'committed bytes equal to the validated files',
        'outside the checkout',
    )

    def text(self, name):
        return ' '.join((ROOT / name).read_text().lower().split())

    def test_docs_consistency_no_wrong_sentences(self):
        for name in self.FILES:
            text = self.text(name)
            for phrase in self.FORBIDDEN:
                self.assertNotIn(' '.join(phrase.lower().split()), text, f'{name}: {phrase}')
            self.assertNotRegex(text, r'(?:stop|stops|stopped)[^.]*\bdenied permissions?\b', name)

    def test_docs_consistency_required_sentences(self):
        for name in self.FILES:
            text = self.text(name)
            for phrase in self.REQUIRED:
                self.assertIn(phrase, text, f'{name}: {phrase}')

    def test_docs_consistency_modes_table(self):
        for name in self.FILES:
            raw = (ROOT / name).read_text()
            self.assertRegex(raw, r'(?mi)^#+ Modes\b|^\| Mode \|', name)
            rows = [line.lower() for line in raw.splitlines() if line.startswith('|')]
            for mode in ('interactive claude', 'ai-run', 'ai-pipeline', 'ai-watchdog'):
                self.assertTrue(any(row.startswith(f'| {mode} |') for row in rows), f'{name}: {mode}')


if __name__ == '__main__':
    unittest.main()
