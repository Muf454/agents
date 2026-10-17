"""Offline integration tests: real shell tools/Git, mock Claude and Codex."""
import ast
import calendar
import contextlib
import errno
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/lib/workflow.py'
# Short commands fail fast on a hang; whole-pipeline runs get more room (CI runners are several times
# slower than a workstation). AI_TEST_TIMEOUT_SCALE (or CI=true) stretches every bound; see timeouts.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeouts import TIMEOUT_SCALE  # noqa: E402
SHORT_TIMEOUT = 10 * TIMEOUT_SCALE
COMMAND_TIMEOUT = 25 * TIMEOUT_SCALE
MEDIUM_TIMEOUT = 60 * TIMEOUT_SCALE
PIPELINE_TIMEOUT = 120 * TIMEOUT_SCALE
# 17 mock sessions in one ai-run (about 5 s each in parallel batches); CI runs on a 2-core runner
# without AI_TEST_TIMEOUT_SCALE, so PIPELINE_TIMEOUT has no margin for them.
LONG_RUN_TIMEOUT = 600 * TIMEOUT_SCALE


def git_fixture_env(base=None):
    """Environment for fixture repositories: no user/system git config, and no fsync or
    background gc (short-lived repos gain nothing from them; disk syncs are slow on CI).
    An outer GIT_CONFIG_COUNT entry list is kept and extended."""
    env = dict(os.environ if base is None else base, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
    try:
        count = max(int(env.get('GIT_CONFIG_COUNT', '0')), 0)
    except ValueError:
        count = 0
    for key, value in (('core.fsync', 'none'), ('gc.auto', '0')):
        env[f'GIT_CONFIG_KEY_{count}'] = key
        env[f'GIT_CONFIG_VALUE_{count}'] = value
        count += 1
    env['GIT_CONFIG_COUNT'] = str(count)
    return env


def command_timeout(name):
    # ai-recover execs the resumed pipeline in the same process, so it needs the pipeline bound too
    # (PR #27 run 38356827946 timed out at 25 s in test_supervised_plan_resume_*_watchdog).
    return PIPELINE_TIMEOUT if name in ('ai-pipeline', 'ai-recover') else COMMAND_TIMEOUT


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
import json, os, pathlib, re, signal, subprocess, sys, time
def crash_kill(pid, pipeline):
    # A simulated restart: kill the nearest ai-run ancestor and the pipeline. Only processes
    # running in this fixture project count: the walk stops at the first ancestor outside it,
    # so a test run inside a real pipeline session never reaches the host's ai-run.
    root = os.path.realpath(os.getcwd())
    def fixture(pid, *names):
        try:
            return os.path.realpath(f'/proc/{pid}/cwd') == root and any(
                part.endswith(names) for part in pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0'))
        except OSError:
            return False
    while pid > 1 and fixture(pid, b''):
        if fixture(pid, b'/ai-run'):
            os.kill(pid, 9)
            break
        pid = int(pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[1])
    if fixture(pipeline, b'/ai-pipeline', b'/ai-recover'):
        os.kill(pipeline, 9)
# Real CLIs read extra prompt input from an open stdin and can hang; it must be /dev/null.
assert os.path.samestat(os.fstat(0), os.stat('/dev/null')), 'claude stdin not /dev/null'
args = sys.argv[1:]
assert '--permission-mode' in args and args[args.index('--permission-mode')+1] == 'dontAsk'
assert '--' in args
prompt = args[args.index('--')+1]
def drop_sections(block, names=('Likely affected modules', 'Result / notes')):
    # A task block as a forgetful session would write it: the named ### sections left out.
    for name in names:
        block = re.sub(r'^### ' + re.escape(name) + r'\n.*?(?=^### |\Z)', '', block, flags=re.S | re.M)
    return block
if 'RECOVERY CONTRACT' in prompt:
    assert args[args.index('--tools')+1] == 'Read,Glob,Grep'
    state = pathlib.Path(os.environ['MOCK_STATE_DIR'])
    with open(state / 'recover-calls', 'a') as f: f.write(prompt.split('RECOVERY CONTRACT')[1][:400].replace('\n', ' ') + '\n')
    if os.path.exists('.ai/local/observation.json'):
        with open(state / 'obs-recover', 'a') as f: f.write(open('.ai/local/observation.json').read())
    if os.environ.get('MOCK_RECOVER_KILL'):
        # ai-recover (claude <- timeout <- ai-recover) is terminated from outside once the session ends
        os.kill(int(pathlib.Path('.ai/local/pipeline.active').read_text()), 15)
    mode = os.environ.get('MOCK_RECOVER', 'rerun')
    decision = {'action': mode.removeprefix('prose-'), 'reason': 'the session crashed once.',
                'human_action': 'look at T001 yourself'}
    answer = json.dumps(decision)
    if mode == 'escalate-long':
        decision.update(action='escalate', reason=' '.join(f'Sentence number {n} explains the stop.' for n in range(1, 40)))
        answer = json.dumps(decision)
    elif mode == 'prose-only':
        answer = 'The session\tcrashed once;\n\nI could not decide what to do.'
    elif mode.startswith('prose-'):
        answer = 'The session crashed once and left nothing behind.\n' + answer + '\nThat is my verdict.'
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': answer}))
    sys.exit(0)
if 'CLAUDE REVIEWER' in prompt:
    state = pathlib.Path(os.environ['MOCK_STATE_DIR'])
    with open(state / 'claude-review-args.log', 'a') as f: f.write(json.dumps([a for a in args if a != prompt]) + '\n')
    with open(state / 'claude-review-prompts.log', 'a') as f: f.write(prompt + '\n=====\n')
    assert not pathlib.Path('.ai/local/review-probes').exists(), 'probe directory exists'
    assert 'inspect git diff' not in prompt, 'the Claude prompt names a git command'
    context = pathlib.Path('.ai/local/review-context')
    read = lambda name: (context / name).read_text() if (context / name).is_file() else None
    review_kind = 'recheck' if 'RECHECK SCOPE' in prompt else 'plan' if 'PLAN SCOPE' in prompt else 'code'
    with open(state / 'claude-review-context.log', 'a') as f:
        f.write(json.dumps({'mode': review_kind,
                            'names': sorted(p.name for p in context.iterdir()) if context.is_dir() else None,
                            'files': (read('files.txt') or '').splitlines(),
                            'diff': [l for l in (read('diff.patch') or '').splitlines() if l.startswith('diff --git')],
                            'findings': read('findings.txt')}) + '\n')
    pass  # the reviewer writes nothing (a test rewrites this line)
    review_mode = os.environ.get('MOCK_CLAUDE_REVIEW', 'success').split(',')
    # 'malformed,success': mode of review call 1, 2, ...; the last one repeats.
    review_mode = review_mode[min(len((state / 'claude-review-args.log').read_text().splitlines()), len(review_mode)) - 1]
    if review_mode in ('malformed', 'empty'):
        print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[],
                          'result': 'looks fine' if review_mode == 'malformed' else '  \n'}))
        sys.exit(0)
    if review_mode == 'limit-once' and not (state / 'claude-review-limit').exists():
        (state / 'claude-review-limit').touch()
        print(json.dumps({'type':'result','subtype':'error','is_error':True,
                          'result':"You've hit your usage limit. Try again in 2 minutes."}))
        sys.exit(1)
    if review_mode == 'error':
        sys.exit(3)
    if 'RECHECK SCOPE' in prompt:
        text = os.environ.get('MOCK_RECHECK', '{"answers": [{"id": "M1", "verdict": "withdrawn", "reason": "Claude agrees"}]}')
    else:
        major = review_mode == 'major' and 'REVIEW SCOPE' in prompt
        text = ('# Review by Claude\nOverall verdict: ' + ('one major finding' if major else 'no demonstrated findings') + '\n'
                'Finding counts: BLOCKER=0 MAJOR=' + ('1' if major else '0') + ' MINOR=0\n'
                '## BLOCKER findings\nNone.\n## MAJOR findings\n' + ('- M1: demonstrated by a probe.\n' if major else 'None.\n') +
                '## MINOR findings\nNone.\n')
    print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[],'result':text}))
    sys.exit(0)
if 'REVISION CONTRACT' in prompt:
    # A plan revision session: Read/Glob/Grep/Edit only, never commits (it has no shell).
    state = pathlib.Path(os.environ['MOCK_STATE_DIR'])
    with open(state / 'revision-args.log', 'a') as f: f.write(json.dumps([a for a in args if a != prompt]) + '\n')
    with open(state / 'revision-prompts.log', 'a') as f: f.write('=== PROMPT ===\n' + prompt + '\n')
    assert pathlib.Path('.ai/local/revision-context/plan-history.md').exists(), 'no revision context'
    def crash(when):
        # The machine "restarts" during revision call MOCK_REVISION_CRASH_CALL (default 1), before
        # or after the session's edits: ai-run (claude <- timeout <- ai-run) and the pipeline die.
        calls = len((state / 'revision-args.log').read_text().splitlines())
        if os.environ.get('MOCK_REVISION_CRASH') == when and calls == int(os.environ.get('MOCK_REVISION_CRASH_CALL', '1')):
            crash_kill(os.getppid(), int(pathlib.Path('.ai/local/pipeline.active').read_text()))
            sys.exit(0)
    crash('before')
    if os.path.exists('.ai/local/observation.json'):
        with open('.ai/local/obs-history', 'a') as f: f.write(open('.ai/local/observation.json').read())
    mode = os.environ.get('MOCK_CLAUDE', 'revise-accept')
    review = pathlib.Path('.ai/reviews/plan.md').read_text()
    majors = review.split('## MAJOR findings')[1].split('## MINOR findings')[0]
    ids = re.findall(r'^- (P\d+):', majors, re.M)
    section = pathlib.Path('.ai/reviews/plan-dispositions.md')
    tasks_file = pathlib.Path('.ai/tasks.md')
    rows = ''
    for number, finding in enumerate(ids):
        if mode == 'revise-needs-human' and number == 0:
            rows += f'| {finding} | needs-human | ' + os.environ.get('MOCK_QUESTION', 'Should the rollback keep option A or switch to B?') + ' | |\n'
        elif mode in ('revise-reject', 'revise-needs-human', 'revise-touch-source', 'revise-edit-plan-review'):
            rows += f'| {finding} | rejected | the plan covers it in current-plan.md:12 | |\n'
        else:
            text = tasks_file.read_text()
            new_id = 'T%03d' % (max(int(x) for x in re.findall(r'^## T(\d+)', text, re.M)) + 1)
            new_task = open(os.environ['MOCK_TASK_TEMPLATE']).read().replace('TXXX', new_id)
            if mode == 'revise-accept-missing-sections':
                new_task = drop_sections(new_task)
            if mode in ('revise-accept-prereq', 'revise-accept-cycle'):
                # The new task is a prerequisite of the first task, appended after it (the cycle
                # variant also makes the new task depend on that first task).
                first = re.search(r'^## (T\d+)', text, re.M).group(1)
                text = re.sub(r'^Dependencies: .*$', f'Dependencies: {new_id}', text, count=1, flags=re.M)
                if mode == 'revise-accept-cycle':
                    new_task = new_task.replace('Dependencies: none', f'Dependencies: {first}')
            tasks_file.write_text(text.rstrip('\n') + '\n\n' + new_task)
            rows += f'| {finding} | accepted | the plan lacks this test | {new_id} |\n'
    if os.environ.get('MOCK_CONVERGENCE'):
        rows += os.environ['MOCK_CONVERGENCE'] + '\n'
    section.write_text(section.read_text() + rows)
    if mode == 'revise-touch-source':
        with open(os.environ.get('MOCK_SOURCE_PATH', 'src.txt'), 'a') as f: f.write('# not allowed in a plan revision\n')
    if mode == 'revise-edit-plan-review':
        pathlib.Path('.ai/reviews/plan.md').write_text(review.replace('MAJOR=', 'MAJOR=0 was '))
    crash('after')
    if mode == 'revise-error':
        print(json.dumps({'type':'result','subtype':'error','is_error':True}))
        sys.exit(0)
    print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[]}))
    sys.exit(0)
if 'PLANNING CONTRACT' in prompt:
    # A headless planning session (ai-run --plan): Edit/Write of the plan records, no shell, no commit.
    state = pathlib.Path(os.environ['MOCK_STATE_DIR'])
    with open(state / 'plan-args.log', 'a') as f: f.write(json.dumps([a for a in args if a != prompt]) + '\n')
    with open(state / 'plan-prompts.log', 'a') as f: f.write('=== PROMPT ===\n' + prompt + '\n')
    if os.path.exists('.ai/local/observation.json'):
        with open('.ai/local/obs-history', 'a') as f: f.write(open('.ai/local/observation.json').read())
    mode = os.environ.get('MOCK_CLAUDE', 'plan-ok')
    if mode == 'limit-once' and not (state / 'plan-limit-hit').exists():
        (state / 'plan-limit-hit').touch()
        print(json.dumps({'type':'result','subtype':'error','is_error':True,
                          'result':"You've hit your usage limit. Try again in 2 minutes."}))
        sys.exit(1)
    if mode == 'plan-error':
        print(json.dumps({'type':'result','subtype':'error','is_error':True}))
        sys.exit(0)
    template = open(os.environ['MOCK_TASK_TEMPLATE']).read()
    if mode in ('plan-revision-ok', 'plan-revision-drops-done', 'plan-revision-removes-done',
                'plan-revision-edits-done', 'plan-revision-prereq'):
        # A revision of the queue: append a TODO task; the drop variant flips DONE to TODO, the
        # remove variant deletes the first DONE block, the edit variant changes its result text,
        # the prereq variant makes the first TODO task depend on the appended task.
        queue = pathlib.Path('.ai/tasks.md').read_text()
        if mode == 'plan-revision-drops-done':
            queue = queue.replace('Status: DONE', 'Status: TODO', 1)
        done_block = re.compile(r'^## T\d+[^\n]*\nStatus: DONE\n.*?(?=^## |\Z)', re.S | re.M)
        if mode == 'plan-revision-removes-done':
            queue = done_block.sub('', queue, count=1)
        if mode == 'plan-revision-edits-done':
            queue = done_block.sub(lambda m: m.group(0).replace('Pending.', 'Passed.'), queue, count=1)
        new_id = 'T%03d' % (max(map(int, re.findall(r'^## T(\d+)', queue, re.M)), default=0) + 1)
        if mode == 'plan-revision-prereq':
            queue = re.sub(r'(^Status: TODO\nDependencies: ).*$', r'\g<1>' + new_id, queue, count=1, flags=re.M)
        pathlib.Path('.ai/tasks.md').write_text(queue.rstrip('\n') + '\n\n' + template.replace('TXXX', new_id))
        print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[]}))
        sys.exit(0)
    first, second = template.replace('TXXX', 'T001'), template.replace('TXXX', 'T002')
    if mode == 'plan-missing-sections':
        second = drop_sections(second)
    if mode in ('plan-out-of-order', 'plan-bad-queue', 'plan-preamble-section'):
        first = first.replace('Dependencies: none', 'Dependencies: T002')
    if mode == 'plan-bad-queue':
        second = second.replace('Dependencies: none', 'Dependencies: T001')
    preamble = '## Context\nKeep this intro.\n\n' if mode == 'plan-preamble-section' else ''
    pathlib.Path('.ai/tasks.md').write_text('# Task queue\n\n' + preamble + first + second)
    with open('.ai/project-spec.md', 'a') as f: f.write('\nObjective from the planning session.\n')
    if mode == 'plan-outside':
        pathlib.Path('src.txt').write_text('not allowed in planning\n')
    if mode == 'plan-gate':
        helper = pathlib.Path('.ai/bin/lib/workflow.py')
        helper.write_text(f'import pathlib; pathlib.Path({str(state / "UNTRUSTED_HELPER_RAN")!r}).touch()\n'
                          + helper.read_text())
    print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[]}))
    sys.exit(0)
assert 'RUNNER CONTRACT' in prompt or 'TRIAGE CONTRACT' in prompt
assert 'TRIAGE CONTRACT' in prompt or 'never prefix commands with `cd`' in prompt
assert '.ai/local/scratch/' in prompt, 'the prompt does not name the scratch directory'
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
if os.path.lexists('.ai/local/scratch'):  # the host empties scratch before every session
    with open(pathlib.Path(os.environ['MOCK_STATE_DIR']) / 'scratch-seen', 'a') as f:
        f.write(' '.join(sorted(os.listdir('.ai/local/scratch'))) + '\n')
if os.path.exists('.ai/local/observation.json'):  # the stage seen by each agent session
    with open('.ai/local/obs-history', 'a') as f: f.write(open('.ai/local/observation.json').read())
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
    with open(pathlib.Path(os.environ['MOCK_STATE_DIR']) / 'triage-prompts.log', 'a') as f:
        f.write('=== PROMPT ===\n' + prompt + '\n')
    tasks_file = pathlib.Path('.ai/tasks.md')
    text = tasks_file.read_text()
    review = pathlib.Path('.ai/reviews/dispositions.md')
    convergence = os.environ.get('MOCK_CONVERGENCE')
    if convergence is not None and re.search(r'^\| M1 \|', review.read_text(), re.M):
        # Resuming a triage whose rows are recorded: only the convergence line is missing.
        review.write_text(review.read_text() + convergence + '\n')
        subprocess.run(['git','add','--','.ai/reviews/dispositions.md'],check=True)
    elif mode == 'triage-rewrites-review':
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
        if mode == 'triage-missing-sections':
            block = drop_sections(block)
        if mode == 'triage-missing-goal':
            block = drop_sections(block, ('Goal', 'Likely affected modules', 'Result / notes'))
        tasks_file.write_text(text.rstrip('\n') + '\n\n' + block)
        review.write_text(review.read_text() + f'| M1 | accepted | fixture defect confirmed | {new_id} |\n'
                          + ('| M2 | deferred | real but out of scope for this change | none |\n'
                             if mode == 'triage-mixed' else '')
                          + ('| M2 | rejected | the second defect is handled by the gate | none |\n'
                             if mode == 'triage-mixed-reject' else '')
                          # MOCK_CODEX=counts: the further MAJOR findings share the fix task.
                          + ''.join(f'| {finding} | accepted | fixture defect confirmed | {new_id} |\n'
                                    for finding in re.findall(r'^- (M\d+):',
                                                              pathlib.Path('.ai/reviews/current.md').read_text(), re.M)
                                    if finding != 'M1' and os.environ.get('MOCK_CODEX') == 'counts')
                          + (convergence + '\n' if convergence else ''))
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
if mode == 'self-kill':
    os.kill(os.getpid(), signal.SIGKILL)
if mode == 'sigkill-runner':
    # The runner dies without its exit handler (claude <- timeout <- ai-run): walk the ppids up to
    # the first bash running ai-run, record it and every pid on the way for the test's cleanup.
    pid, seen = os.getppid(), []
    while pid > 1:
        seen.append(pid)
        argv = pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if pathlib.Path(argv[0].decode()).name == 'bash' and any(b'ai-run' in part for part in argv):
            break
        pid = int(pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[1])
    else:
        sys.exit('mock: no ai-run ancestor')
    with open(pathlib.Path(os.environ['MOCK_STATE_DIR']) / 'sigkill-runner.pids', 'a') as f:
        f.write(''.join(f'{p}\n' for p in seen))
    os.kill(pid, signal.SIGKILL)
    sys.exit(0)
if mode == 'hold':
    # Bounded wait for the test to signal the runner, then release and fail.
    pathlib.Path('.ai/local/mock-session.pid').write_text(str(os.getpid()))
    for _ in range(200):
        if pathlib.Path('.ai/local/mock-release').exists():
            break
        time.sleep(0.05)
    print(json.dumps({'type':'result','subtype':'error','is_error':True}))
    sys.exit(1)
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
if mode == 'scratch-leftover':
    # Throwaway files a session leaves behind; the host must remove them after the session.
    scratch = pathlib.Path('.ai/local/scratch')
    (scratch / 'nested/deeper').mkdir(parents=True, exist_ok=True)
    (scratch / 'tmp.test.sh').write_text('echo scratch\n')
    (scratch / 'nested/deeper/notes.txt').write_text('scratch\n')
if mode == 'scratch-parent-symlink':
    pathlib.Path('.ai/local').rename('.ai/local-aside')
    pathlib.Path('.ai/local').symlink_to(os.environ['MOCK_VICTIM'])
if mode == 'scratch-symlink':
    pathlib.Path('.ai/local/scratch').symlink_to(os.environ['MOCK_VICTIM'])
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
import os, pathlib, subprocess, sys
assert os.path.samestat(os.fstat(0), os.stat('/dev/null')), 'codex stdin not /dev/null'
args = sys.argv[1:]
assert args[0] == 'exec'
assert args[args.index('--sandbox')+1] == 'read-only'
assert 'approval_policy="never"' in args
assert '--ignore-user-config' in args
state = pathlib.Path(os.environ.get('MOCK_STATE_DIR', '.'))
with open(state / 'codex-args.log', 'a') as log: log.write(' '.join(args[:-1]) + '\n')
with open(state / 'codex-prompts.log', 'a') as log: log.write('=== PROMPT ===\n' + args[-1] + '\n')
if os.path.exists('.ai/local/observation.json'):
    with open('.ai/local/obs-history', 'a') as f: f.write(open('.ai/local/observation.json').read())
if os.environ.get('MOCK_CODEX_LIMIT') and 'Diagnose this workflow incident' not in args[-1]:
    with open(state / 'codex-limit-calls', 'a') as f: f.write('call\n')
    print('ERROR: You have hit your usage limit. Try again in 7 days.')
    sys.exit(1)
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
    plan_calls = (state / 'codex-plan-calls').read_text().count('call')
    # The checkout as each plan review saw it ('clean' when nothing is uncommitted).
    status = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all'],
                            capture_output=True, text=True, check=True).stdout.strip()
    with open(state / 'codex-plan-status', 'a') as f: f.write((status or 'clean').replace('\n', ' ') + '\n')
    # MOCK_CODEX_PLAN_FORMAT='malformed,ok': report format of plan call 1, 2, ...; the last one repeats.
    formats = os.environ.get('MOCK_CODEX_PLAN_FORMAT', 'ok').split(',')
    plan_format = formats[min(plan_calls, len(formats)) - 1]
    out = pathlib.Path(args[args.index('--output-last-message')+1])
    if plan_format == 'error': sys.exit(17)
    if plan_format == 'empty': sys.exit(0)
    if plan_format == 'malformed':
        out.write_text('looks fine')
        sys.exit(0)
    if plan_format == 'counts-lie':
        out.write_text('# Plan review\nOverall verdict: gap\nFinding counts: BLOCKER=0 MAJOR=0 MINOR=0\n'
                       '## BLOCKER findings\nNone.\n## MAJOR findings\n- P1: T001 has no test.\n## MINOR findings\nNone.\n')
        sys.exit(0)
    if plan_format == 'mutates':
        pathlib.Path('unexpected.txt').write_text('unexpected concurrent edit')
    major = os.environ.get('MOCK_CODEX_PLAN') == 'major' or \
        (os.environ.get('MOCK_CODEX_PLAN') == 'major-once' and plan_calls == 1)
    items = [item.split('|', 1) for item in os.environ.get('MOCK_CODEX_PLAN_FINDINGS', '').split(';') if item]
    if not items and major: items = [['P1', 'T001 has no test.']]
    minor = [item.split('|', 1) for item in os.environ.get('MOCK_CODEX_PLAN_MINOR', '').split(';') if item]
    pathlib.Path(args[args.index('--output-last-message')+1]).write_text(
        '# Plan review\nOverall verdict: ' + ('gap' if items else 'ok') + '\n'
        'Finding counts: BLOCKER=0 MAJOR=' + str(len(items)) + ' MINOR=' + str(len(minor)) + '\n'
        '## BLOCKER findings\nNone.\n## MAJOR findings\n' +
        (''.join('- %s: %s\n' % (i, t) for i, t in items) if items else 'None.\n') +
        '## MINOR findings\n' + (''.join('- %s: %s\n' % (i, t) for i, t in minor) if minor else 'None.\n'))
    sys.exit(0)
mode = os.environ.get('MOCK_CODEX', 'success')
calls = state / 'codex-calls'
calls.write_text(calls.read_text() + 'call\n' if calls.exists() else 'call\n')
count = calls.read_text().count('call')
if ',' in mode:
    # 'malformed,success': mode of review call 1, 2, ...; the last one repeats.
    mode = mode.split(',')[min(count, len(mode.split(','))) - 1]
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
if mode == 'verdict-heading':
    path.write_text('# Independent review\n## Overall verdict\n\nApprove with two minor notes\n\n'
                    'Finding counts: BLOCKER=0 MAJOR=0 MINOR=0\n## BLOCKER findings\nNone found.\n'
                    '## MAJOR findings\nNone found.\n## Missing test coverage\nx\n')
    sys.exit(0)
major = mode == 'major-always' or (mode in ('major-once', 'two-major-once') and count == 1)
two = mode == 'two-major-once' and count == 1
majors = 2 if two else 1 if major else 0
if mode == 'counts':
    # MOCK_CODEX_MAJORS='3,2,1': MAJOR findings of review call 1, 2, 3; the last one repeats.
    series = [int(n) for n in os.environ['MOCK_CODEX_MAJORS'].split(',')]
    majors = series[min(count, len(series)) - 1]
    major = majors > 0
path.write_text("""# Independent review
Overall verdict: """ + ('one major finding' if major else 'no demonstrated findings in inspected fixture') + """
Finding counts: BLOCKER=0 MAJOR=""" + str(majors) + """ MINOR=0
## BLOCKER findings
None found.
## MAJOR findings
""" + ('- M1: fixture defect at T001.txt:1.' + ('\n- M2: second defect, out of scope.' if two else '')
       + ''.join(f'\n- M{n}: fixture defect {n}.' for n in range(2, majors + 1) if mode == 'counts')
       if major else 'None found.') + """
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
cat .ai/local/observation.json >> "$MOCK_STATE_DIR/deps-obs" 2>/dev/null || true
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
  submodule) echo new > sub/new.txt ;;
  submodule-fail) echo new > sub/new.txt; exit 1 ;;
  commit) echo changed >> tracked.txt; git commit -qam 'installer commit' ;;
esac
mkdir -p vendor-deps
cp deps.lock vendor-deps/
'''

MOCK_SLEEP = r'''#!/usr/bin/env bash
echo "$1" >> "$MOCK_SLEEP_LOG"
'''

# Git hook body (HOOK and SUBJECT set above it): at the first host commit with SUBJECT the
# machine "restarts": the ai-run that commits (if any) and the pipeline die at once.
# commit-msg aborts the commit (crash before it); post-commit runs after it (crash after it).
CRASH_HOOK = r'''
if HOOK == 'commit-msg':
    message = pathlib.Path(sys.argv[1]).read_text().strip()
else:
    message = subprocess.run(['git', 'log', '-1', '--format=%s'], capture_output=True, text=True).stdout.strip()
fired = pathlib.Path(os.environ['MOCK_STATE_DIR']) / 'crash-hook-fired'
if message != SUBJECT or fired.exists():
    sys.exit(0)
fired.touch()
crash_kill(os.getppid(), int(pathlib.Path('.ai/local/pipeline.active').read_text()))
sys.exit(1 if HOOK == 'commit-msg' else 0)
'''
CRASH_KILL = MOCK_CLAUDE[MOCK_CLAUDE.index('def crash_kill'):MOCK_CLAUDE.index('# Real CLIs')]
CRASH_HOOK = CRASH_KILL + CRASH_HOOK


class ToolkitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai-toolkit-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project with spaces'
        self.project.mkdir()
        self.env = git_fixture_env()
        for name in ('AI_PIPELINE', 'AI_LOCK_HELD', 'AI_RECOVERY_ATTEMPT', 'AI_SETTINGS_FROM_MANIFEST',
                     'AI_DISPUTES_BASE', 'AI_SUPERVISE_PLAN_ROUNDS', 'AI_SUPERVISE_ESCALATE_ROUND',
                     'AI_SUPERVISE_ESCALATE_MODEL'):
            # set when the gate runs inside a pipeline (or one resumed by ai-recover); the
            # supervision settings would override the fixture's config file
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
        self.env['AI_SUPERVISE'] = '0'  # supervision has its own tests
        # ai-dashboard on the host lists only real pipelines, not these fixture runners.
        self.env['AI_DASHBOARD_IGNORE'] = '1'
        self.env['XDG_DATA_HOME'] = str(self.base / 'xdg-data')
        self.env.update(XDG_CONFIG_HOME=str(self.config), MOCK_STATE_DIR=str(self.base),
                        MOCK_GH_LOG=str(self.base / 'gh.log'), MOCK_TASK_TEMPLATE=str(template),
                        AI_STATE_DIR=str(self.base / 'host-state'),
                        MOCK_SLEEP_LOG=str(self.base / 'sleep.log'), AI_SLEEP=str(self.mock_bin / 'mock-sleep'),
                        AI_NOTIFY_CMD=f'printf "%s\\n" "$1" >> "{self.notify_log}"')

    def run_cmd(self, command, expected=0, env=None, timeout=COMMAND_TIMEOUT):
        try:
            result = subprocess.run(command, cwd=self.project, env=env or self.env,
                                    capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            def tail(data):
                data = data.decode(errors='replace') if isinstance(data, bytes) else data or ''
                return data[-3000:]
            self.fail(f'command timed out after {timeout} s: {command}\n'
                      f'--- stdout (tail) ---\n{tail(error.stdout)}\n--- stderr (tail) ---\n{tail(error.stderr)}')
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

    def watchdog_stalled(self, phase):
        # A stall a probe already sighted long ago: the next probe confirms it.
        self.watchdog_phase(phase)
        state = self.project / '.ai/local/watchdog.json'
        state.parent.mkdir(exist_ok=True)
        record = json.loads(state.read_text()) if state.exists() else {}
        state.write_text(json.dumps(dict(record, stall_seen_ns=0)) + '\n')

    def watchdog_state(self):
        return json.loads((self.project / '.ai/local/watchdog.json').read_text())

    def test_watchdog_health_stall_recovery_and_checkout_scope(self):
        self.setup_project()
        self.watchdog()
        self.assertEqual(self.notifications(), '')
        self.watchdog_phase('implementing')
        other = self.base / 'other'
        other.mkdir()
        self.watchdog_runner(other)
        start = time.time()
        self.watchdog(AI_WATCHDOG_NOW=str(start))  # first sighting: not confirmed yet
        self.assertEqual(self.notifications(), '')
        self.watchdog(expected=1, AI_WATCHDOG_NOW=str(start + 600))
        self.watchdog(expected=1, AI_WATCHDOG_NOW=str(start + 1200))
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.watchdog_phase('ready_for_review')
        self.watchdog(AI_WATCHDOG_NOW=str(start + 1800))
        self.watchdog_phase('fixing_review')
        self.watchdog(AI_WATCHDOG_NOW=str(start + 2400))
        self.watchdog(expected=1, AI_WATCHDOG_NOW=str(start + 3000))
        self.assertEqual(len(self.notifications().splitlines()), 2)

    def test_watchdog_confirm_timer_first_probe_two_minutes_after_activation(self):
        self.setup_project()
        self.mock_systemctl()
        self.watchdog('--install-timer')
        timer = next((self.config / 'systemd/user').glob('*.timer')).read_text()
        self.assertIn('OnActiveSec=2min\n', timer)
        self.assertIn('OnUnitActiveSec=10min\n', timer)
        self.assertNotIn('OnBootSec', timer)

    def test_watchdog_confirm_install_before_pipeline_start_is_silent(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        start = time.time()
        self.watchdog(AI_WATCHDOG_NOW=str(start))
        self.assertIsInstance(self.watchdog_state()['stall_seen_ns'], int)
        pipeline = self.watchdog_runner(name='ai-pipeline')
        (self.project / '.ai/local/pipeline.active').write_text(f'{pipeline.pid}\n')
        self.watchdog(AI_WATCHDOG_NOW=str(start + 600))
        self.assertEqual(self.notifications(), '')
        self.assertNotIn('stall_seen_ns', self.watchdog_state())

    def test_watchdog_confirm_killed_runner_reported_once_after_five_minutes(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        start = time.time()
        self.watchdog(AI_WATCHDOG_NOW=str(start))
        self.watchdog(AI_WATCHDOG_NOW=str(start + 120))
        self.assertEqual(self.notifications(), '')
        self.watchdog(expected=1, AI_WATCHDOG_NOW=str(start + 360))
        self.watchdog(expected=1, AI_WATCHDOG_NOW=str(start + 960))
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.assertIn('⛔', self.notifications())
        self.assertIn('killed runner?', self.notifications())

    def test_watchdog_confirm_dead_pipeline_marker_reported_at_first_probe(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        self.crashed_marker()
        self.watchdog(expected=1)
        self.assertIn('ai-pipeline is gone', self.notifications())
        self.assertNotIn('killed runner?', self.notifications())

    def test_watchdog_confirm_planning_stage_is_not_stalled(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        observation = self.project / '.ai/local/observation.json'
        observation.parent.mkdir(exist_ok=True)
        start = time.time()
        for offset, state in ((0, 'active'), (600, 'done')):
            observation.write_text(json.dumps({'stage': 'planning', 'state': state}) + '\n')
            self.watchdog(AI_WATCHDOG_NOW=str(start + offset))
            self.assertNotIn('stall_seen_ns', self.watchdog_state())
        self.assertEqual(self.notifications(), '')
        # An unreadable record (a FIFO) is ignored without blocking: the stall rule applies.
        observation.unlink()
        os.mkfifo(observation)
        command = [str(self.project / '.ai/bin/ai-watchdog')]
        self.run_cmd(command, env=dict(self.env, AI_WATCHDOG_NOW=str(start + 1200)), timeout=SHORT_TIMEOUT)
        self.assertIn('stall_seen_ns', self.watchdog_state())
        self.run_cmd(command, expected=1, env=dict(self.env, AI_WATCHDOG_NOW=str(start + 1800)), timeout=SHORT_TIMEOUT)
        self.assertIn('killed runner?', self.notifications())

    def test_watchdog_confirm_legacy_active_stall(self):
        self.setup_project()
        self.watchdog_phase('implementing')
        state = self.project / '.ai/local/watchdog.json'
        state.parent.mkdir(exist_ok=True)
        start = time.time()
        # An older watchdog already announced this stall and recorded no stall_seen_ns.
        state.write_text(json.dumps({'active': ['stalled'], 'notified_at_ns': int(start * 1e9) - 1}) + '\n')
        for offset in (0, 360):
            self.watchdog('--diagnose', expected=1, AI_WATCHDOG_NOW=str(start + offset))
            self.assertEqual(self.watchdog_state()['active'], ['stalled'])
        self.assertEqual(self.notifications(), '')
        self.assertFalse((self.project / '.ai/local/diagnosis.md').exists())
        # Once it clears and returns, it is a new stall that needs confirmation again.
        self.watchdog_phase('ready_for_review')
        self.watchdog(AI_WATCHDOG_NOW=str(start + 720))
        self.assertNotIn('stall_seen_ns', self.watchdog_state())
        self.watchdog_phase('implementing')
        self.watchdog(AI_WATCHDOG_NOW=str(start + 1080))
        self.assertEqual(self.notifications(), '')
        self.watchdog(expected=1, AI_WATCHDOG_NOW=str(start + 1440))
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.assertIn('killed runner?', self.notifications())

    def test_watchdog_confirm_dedupe_record_versions(self):
        self.setup_project()
        state = self.project / '.ai/local/watchdog.json'
        state.parent.mkdir(exist_ok=True)
        state.write_text('{"active": [], "notified_at_ns": 0}\n')  # previous version
        self.watchdog()
        state.write_text('{"active": [], "notified_at_ns": 0, "stall_seen_ns": "x"}\n')
        result = self.watchdog(expected=2)
        self.assertIn('invalid dedupe record', result.stderr)

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
        self.watchdog_stalled('implementing')
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
        self.watchdog_stalled('implementing')
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
        # --recover runs the resumed pipeline through the mock systemd-run
        return self.run_cmd([str(host / 'ai-watchdog'), str(self.project), *args], expected=expected,
                            env=dict(self.env, **env),
                            timeout=PIPELINE_TIMEOUT if '--recover' in args else COMMAND_TIMEOUT)

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
        self.assertIn('--setenv=AI_DASHBOARD_IGNORE=1 ', launched)  # a resumed fixture stays hidden
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

    def limit_relaunch_fixture(self, at):
        # An approved run stopped at a usage limit: relaunch scheduled at AT, nothing running.
        self.setup_project()
        self.commit('bootstrap')
        self.approve_run()
        self.mock_systemd_run()
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('run-manifest', 'limit-schedule', str(at), '2', head)
        self.watchdog_phase('implementing')
        (self.project / '.ai/local').mkdir(exist_ok=True)

    def launches(self):
        log = self.base / 'systemd-run.log'
        return log.read_text() if log.exists() else ''

    def test_limit_relaunch_watchdog_due_schedule_starts_ai_recover(self):
        start = int(time.time())
        self.limit_relaunch_fixture(start - 10)
        self.host_watchdog(AI_WATCHDOG_NOW=str(start))  # without --recover: nothing relaunches
        self.assertEqual(self.launches(), '')
        self.host_watchdog('--recover', AI_WATCHDOG_NOW=str(start))
        self.assertIn(str(self.project / '.ai/bin/ai-recover') + ' --stage usage limit relaunch', self.launches())
        self.assertFalse((self.project / '.ai/local/last-error').exists())
        self.assertEqual(self.notifications(), '')
        state = self.watchdog_state()
        self.assertNotIn('stall_seen_ns', state)
        self.assertNotIn('stalled', state['active'])

    def test_limit_relaunch_watchdog_pending_schedule_is_not_stalled(self):
        start = int(time.time())
        self.limit_relaunch_fixture(start + 3600)
        stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start))
        (self.project / '.ai/local/pauses.log').write_text(f'{stamp} paused 3660s: Claude usage limit\n')
        for args in ((), ('--recover',)):
            with self.subTest(args=args):
                self.host_watchdog(*args, AI_WATCHDOG_NOW=str(start))
                self.host_watchdog(*args, AI_WATCHDOG_NOW=str(start + 360))
                self.assertEqual(self.launches(), '')
                self.assertEqual(self.notifications(), '')
                self.assertEqual(self.watchdog_state()['active'], [])

    def test_limit_relaunch_watchdog_schedule_alone_suppresses_the_stall(self):
        # P2: a kill before the pauses.log append leaves only the host schedule.
        start = int(time.time())
        at = start + 3600
        self.limit_relaunch_fixture(at)
        local = self.project / '.ai/local'
        for pauses in (None, f'{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start - 7200))} paused 60s: x\n'):
            for args in (('--recover',), ()):
                with self.subTest(pauses=pauses, args=args):
                    if pauses:
                        (local / 'pauses.log').write_text(pauses)
                    self.host_watchdog(*args, AI_WATCHDOG_NOW=str(start))
                    self.host_watchdog(*args, AI_WATCHDOG_NOW=str(start + 360))
                    self.assertEqual(self.launches(), '')
                    self.assertEqual(self.notifications(), '')
                    self.assertEqual(self.watchdog_state()['active'], [])
                    self.assertNotIn('stall_seen_ns', self.watchdog_state())
        (local / 'pauses.log').unlink()
        self.host_watchdog('--recover', AI_WATCHDOG_NOW=str(at + 1))
        self.assertIn('ai-recover --stage usage limit relaunch', self.launches())
        (local / 'pipeline.active').unlink()  # the mock's takeover; the relaunch claims:
        self.helper('run-manifest', 'limit-claim', str(at))
        self.host_watchdog('--recover', AI_WATCHDOG_NOW=str(at + 600))
        self.host_watchdog('--recover', expected=1, AI_WATCHDOG_NOW=str(at + 960))
        self.assertIn('killed runner?', self.notifications())
        self.assertEqual(len(self.notifications().splitlines()), 1)

    def test_limit_relaunch_watchdog_refusal_reported_once_without_a_stall(self):
        start = int(time.time())
        self.limit_relaunch_fixture(start - 10)
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nexit 0\n')  # changed gate
        for offset in (0, 360, 720):
            self.host_watchdog('--recover', expected=1, AI_WATCHDOG_NOW=str(start + offset))
            state = self.watchdog_state()
            self.assertNotIn('stall_seen_ns', state)
            self.assertNotIn('stalled', state['active'])
            self.assertEqual(state['active'], [f'relaunch:{start - 10}'])
        self.assertEqual(self.launches(), '')
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.assertIn('⛔ STOPPED, needs you: the usage-limit relaunch could not start: '
                      'auto-recovery refused: gate files changed', self.notifications())
        # A human start drops the schedule: the stall rule applies again.
        self.approve_run()
        self.host_watchdog('--recover', AI_WATCHDOG_NOW=str(start + 1080))
        self.host_watchdog('--recover', expected=1, AI_WATCHDOG_NOW=str(start + 1440))
        self.assertEqual(self.launches(), '')
        self.assertEqual(len(self.notifications().splitlines()), 2)
        self.assertIn('killed runner?', self.notifications().splitlines()[1])

    def test_limit_relaunch_watchdog_checkout_copy_refused_and_due_without_recover_stalls(self):
        start = int(time.time())
        self.limit_relaunch_fixture(start - 10)
        self.watchdog('--recover', expected=1, AI_WATCHDOG_NOW=str(start))  # not the host copy
        self.watchdog('--recover', expected=1, AI_WATCHDOG_NOW=str(start + 360))
        self.assertEqual(self.launches(), '')
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.assertIn('the usage-limit relaunch could not start: auto-recovery only runs from the installed timer',
                      self.notifications())
        # Due, but this probe cannot relaunch: the killed-runner alarm is right.
        (self.project / '.ai/local/watchdog.json').unlink()
        self.notify_log.unlink()
        self.host_watchdog(AI_WATCHDOG_NOW=str(start + 720))
        self.host_watchdog(expected=1, AI_WATCHDOG_NOW=str(start + 1080))
        self.assertEqual(self.launches(), '')
        self.assertNotIn('usage-limit relaunch', self.notifications())
        self.assertEqual(len(self.notifications().splitlines()), 1)
        self.assertIn('killed runner?', self.notifications())

    def test_limit_relaunch_watchdog_absent_schedule_changes_nothing(self):
        # P11: no schedule is "absent", never "due at 0".
        self.setup_project()
        self.commit('bootstrap')
        self.mock_systemd_run()
        local = self.project / '.ai/local'
        start = int(time.time())
        cases = (('no manifest', None, 'planning'), ('approved, unscheduled', 'approve', 'implementing'),
                 ('finished', 'finish', 'ready_for_review'))
        for args in (('--recover',), ()):
            for name, run, phase in cases:
                with self.subTest(case=name, args=args):
                    for path in (local / 'watchdog.json', self.notify_log):
                        path.unlink(missing_ok=True)
                    if run:
                        self.approve_run()
                    if run == 'finish':
                        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
                        self.helper('run-manifest', 'limit-schedule', str(start - 10), '2', head)
                        self.helper('run-manifest', 'clear-attempts')
                    self.watchdog_phase(phase)
                    self.host_watchdog(*args, AI_WATCHDOG_NOW=str(start))
                    stalls = phase == 'implementing'
                    self.host_watchdog(*args, expected=1 if stalls else 0, AI_WATCHDOG_NOW=str(start + 360))
                    self.assertEqual(self.launches(), '')
                    self.assertNotIn('usage-limit relaunch', self.notifications())
                    self.assertFalse(any(key.startswith('relaunch:') for key in self.watchdog_state()['active']))
                    if stalls:
                        self.assertEqual(len(self.notifications().splitlines()), 1)
                        self.assertIn('killed runner?', self.notifications())
                    else:
                        self.assertEqual(self.notifications(), '')
            for path in self.base.joinpath('host-state').rglob('run.json'):
                path.unlink()

    def test_limit_relaunch_watchdog_live_marker_or_runner_blocks_the_launch(self):
        start = int(time.time())
        self.limit_relaunch_fixture(start - 10)
        pipeline = self.watchdog_runner(name='ai-pipeline')
        (self.project / '.ai/local/pipeline.active').write_text(f'{pipeline.pid}\n')
        self.host_watchdog('--recover', AI_WATCHDOG_NOW=str(start))
        self.assertEqual(self.launches(), '')
        (self.project / '.ai/local/pipeline.active').unlink()
        self.host_watchdog('--recover', AI_WATCHDOG_NOW=str(start))  # the ai-pipeline still runs
        self.assertEqual(self.launches(), '')
        self.assertEqual(self.notifications(), '')

    def test_limit_relaunch_watchdog_timer_recovers(self):
        self.setup_project()
        self.mock_systemctl()
        result = self.watchdog('--timer-recovers', expected=1)
        self.assertTrue(result.stdout.startswith('no-recover ai-watchdog-'), result.stdout)
        self.assertIn('(timer missing: no unit files)', result.stdout)
        self.watchdog('--install-timer', '--recover')
        self.assertTrue(self.watchdog('--timer-recovers').stdout.startswith('recovers ai-watchdog-'))
        self.watchdog('--install-timer', '--diagnose')
        self.assertIn('installed without --recover', self.watchdog('--timer-recovers', expected=1).stdout)
        self.watchdog('--timer-recovers', '--timer-status', expected=2)

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

    def mock_systemctl(self):
        # Records calls; enable --now makes the timer enabled+active unless MOCK_SYSTEMCTL=fail.
        # MOCK_SYSTEMCTL=broken answers queries with an error and no output (no user bus).
        (self.mock_bin / 'systemctl').write_text(
            '#!/usr/bin/env bash\n'
            'printf "%s\\n" "$*" >> "$MOCK_STATE_DIR/systemctl.log"\n'
            'case "$MOCK_SYSTEMCTL:$2" in\n'
            '  fail:enable) echo "Failed to enable" >&2; exit 1 ;;\n'
            '  broken:is-*) echo "Failed to connect to bus" >&2; exit 1 ;;\n'
            'esac\n'
            'case "$2" in\n'
            '  enable) echo enabled > "$MOCK_STATE_DIR/sc-enabled"; echo active > "$MOCK_STATE_DIR/sc-active" ;;\n'
            '  disable) rm -f "$MOCK_STATE_DIR"/sc-enabled "$MOCK_STATE_DIR"/sc-active ;;\n'
            '  is-enabled) cat "$MOCK_STATE_DIR/sc-enabled" 2>/dev/null || { echo disabled; exit 1; } ;;\n'
            '  is-active) cat "$MOCK_STATE_DIR/sc-active" 2>/dev/null || { echo inactive; exit 3; } ;;\n'
            'esac\n'
            'exit 0\n')
        (self.mock_bin / 'systemctl').chmod(0o755)

    def timer_status(self, expected, **env):
        result = self.watchdog('--timer-status', expected=expected, **env)
        return result.stdout.strip()

    def test_watchdog_setup_flag_installs_files_and_timer(self):
        self.mock_systemctl()
        result = self.setup_project('--watchdog')
        units = sorted((self.config / 'systemd/user').iterdir())
        self.assertEqual([u.suffix for u in units], ['.service', '.timer'])
        self.assertTrue((self.base / 'xdg-data/ai-toolkit/watchdog' / units[0].stem / 'bin/ai-watchdog').is_file())
        self.assertIn('--user enable --now ' + units[1].name, (self.base / 'systemctl.log').read_text())
        self.assertNotIn('Next: install the watchdog timer', result.stdout)
        self.assertTrue(self.timer_status(0).startswith('installed '))

    def test_watchdog_setup_flag_is_rejected_with_dry_run_and_upgrade(self):
        self.mock_systemctl()
        for option in ('--dry-run', '--upgrade'):
            with self.subTest(option=option):
                result = self.run_cmd([str(ROOT / 'scripts/setup-project'), '--watchdog', option,
                                       str(self.project)], expected=1)
                self.assertIn('--watchdog', result.stderr + result.stdout)
        self.assertFalse((self.project / '.ai').exists())
        self.assertFalse((self.base / 'systemctl.log').exists())

    def test_watchdog_setup_flag_reports_a_failing_systemctl(self):
        self.mock_systemctl()
        result = self.run_cmd([str(ROOT / 'scripts/setup-project'), '--watchdog', str(self.project)],
                              expected=1, env=dict(self.env, MOCK_SYSTEMCTL='fail'))
        self.assertIn('the timer was not', result.stderr + result.stdout)
        self.assertIn('enable', result.stderr + result.stdout)
        self.assertTrue((self.project / '.ai/bin/ai-watchdog').is_file())

    def test_watchdog_setup_plain_prints_next_step_and_writes_no_units(self):
        self.mock_systemctl()
        result = self.setup_project()
        self.assertIn('Next: install the watchdog timer: .ai/bin/ai-watchdog --install-timer --diagnose --recover',
                      result.stdout)
        self.assertFalse((self.config / 'systemd').exists())
        self.assertFalse((self.base / 'systemctl.log').exists())

    def test_watchdog_setup_timer_status_missing_installed_partial_stopped_unknown(self):
        self.setup_project()
        self.mock_systemctl()
        self.assertIn('no unit files', self.timer_status(1))
        self.watchdog('--install-timer')
        self.assertTrue(self.timer_status(0).startswith('installed ai-watchdog-'))
        (self.base / 'sc-enabled').unlink()  # unit files present, enable --now never took effect
        self.assertTrue(self.timer_status(1).startswith('missing '))
        self.assertIn('not enabled', self.timer_status(1))
        (self.base / 'sc-enabled').write_text('enabled\n')
        (self.base / 'sc-active').write_text('inactive\n')
        self.assertIn('not active', self.timer_status(1))
        (self.base / 'sc-active').write_text('active\n')
        self.assertTrue(self.timer_status(0).startswith('installed '))
        self.assertTrue(self.timer_status(2, MOCK_SYSTEMCTL='broken').startswith('unknown '))
        (self.mock_bin / 'systemctl').unlink()
        empty = self.base / 'empty-bin'
        empty.mkdir()
        result = self.run_cmd([sys.executable, '-I', str(self.project / '.ai/bin/lib/watchdog.py'),
                               str(self.project), '--timer-status'], expected=2,
                              env=dict(self.env, PATH=str(empty)))
        self.assertTrue(result.stdout.startswith('unknown '), result.stdout)
        self.watchdog('--timer-status', '--install-timer', expected=2)

    def pipeline_ready(self):
        self.ready()
        self.mock_systemctl()

    def test_watchdog_setup_pipeline_warns_when_timer_is_missing(self):
        self.pipeline_ready()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('No watchdog timer for this checkout', result.stdout)
        self.assertIn('▶ STARTED on feature/test. (no watchdog timer for this checkout)', self.notifications())
        self.helper('tasks', 'complete')

    def test_watchdog_setup_pipeline_warns_when_timer_is_stopped(self):
        self.pipeline_ready()
        self.watchdog('--install-timer')
        (self.base / 'sc-active').write_text('inactive\n')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('No watchdog timer for this checkout', result.stdout)
        self.assertIn('(no watchdog timer for this checkout)', self.notifications())
        self.helper('tasks', 'complete')

    def test_watchdog_setup_pipeline_is_quiet_with_an_installed_timer(self):
        self.pipeline_ready()
        self.watchdog('--install-timer')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertNotIn('watchdog timer', result.stdout)
        self.assertIn('▶ STARTED on feature/test.\n', self.notifications())
        self.helper('tasks', 'complete')

    def test_watchdog_setup_pipeline_notes_unknown_status_and_continues(self):
        self.pipeline_ready()
        self.watchdog('--install-timer')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_SYSTEMCTL='broken')
        self.assertIn('Watchdog timer status unknown', result.stdout)
        self.assertIn('(watchdog timer status unknown)', self.notifications())
        self.helper('tasks', 'complete')

    def test_watchdog_setup_recovery_resume_notification_carries_the_note(self):
        self.pipeline_ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr',
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error-once')
        self.assertIn('▶ RESUMED on feature/test after auto-recovery (1). (no watchdog timer for this checkout)',
                      self.notifications())

    def test_watchdog_setup_no_pgrep_f_waits_in_executable_code_and_readme_documents_pids(self):
        for directory in ('scripts', 'templates'):
            for path in sorted((ROOT / directory).rglob('*')):
                # Bytecode is not source, and parallel shards write it concurrently.
                if '__pycache__' in path.parts:
                    continue
                if path.is_file() and path.suffix != '.md':
                    self.assertNotRegex(path.read_text(errors='replace'), r'pgrep\s+(-\w*f|--full)',
                                        str(path))
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('while kill -0 "$pid" 2>/dev/null; do sleep 60; done', readme)
        self.assertIn('pgrep -f', readme)
        self.assertIn('matches itself', readme)

    def assert_install(self, cwd, expected, **env):
        # Installs the timer for self.project while the caller's directory is cwd.
        (self.mock_bin / 'systemctl').write_text(
            '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_STATE_DIR/systemctl.log"\n')
        (self.mock_bin / 'systemctl').chmod(0o755)
        result = subprocess.run([str(self.project / '.ai/bin/ai-watchdog'), str(self.project), '--install-timer'],
                                cwd=cwd, env=dict(self.env, **env), capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
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
        self.watchdog_stalled('implementing')
        (self.mock_bin / 'claude').write_text(
            '#!/usr/bin/env bash\nprintf "call\\n" >> "$MOCK_STATE_DIR/timeout-calls"\nsleep 30\n')
        command = [str(self.project / '.ai/bin/ai-watchdog'), '--diagnose', '--diagnosis-timeout', '1', '--diagnosis-agent', 'claude']
        first = subprocess.Popen(command, cwd=self.project, env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.watchdog('--diagnose', '--diagnosis-timeout', '1', '--diagnosis-agent', 'claude', expected=1)
            first.communicate(timeout=SHORT_TIMEOUT * 1.5)
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

    def tool(self, name, *args, expected=0, timeout=None, **env):
        if timeout is None:
            timeout = command_timeout(name)
        return self.run_cmd([str(self.project / '.ai/bin' / name), *args], expected=expected,
                            env=dict(self.env, **env), timeout=timeout)

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
                before = self.outcome_rows()
                self.tool('ai-run', '--approved', '--sessions', '5', expected=1, MOCK_CLAUDE=mode)
                added = self.outcome_rows()[len(before):]
                self.assertEqual([r['task'] for r in added], ['T001'])
                self.assertEqual(added[0]['attempt'], len(before) + 1)
                if mode == 'bad-format':
                    self.assertEqual(added[0]['result'], 'error')
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

    def test_task_sections_prompts_show_the_format(self):
        for name in ('triage', 'plan-revision', 'plan'):
            text = (ROOT / f'templates/.ai/prompts/{name}.md').read_text()
            for phrase in ('### Likely affected modules', '### Result / notes', 'write a pipe as'):
                self.assertIn(phrase, text, f'{name}.md lacks {phrase!r}')
        tasks = (ROOT / 'templates/.ai/tasks.md').read_text()
        self.assertIn('`### Result / notes` starts empty', tasks)

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
        programs = ('curl', 'wget', 'ssh', 'scp', 'rm', 'sed', 'rg', 'find', 'xargs',
                    'sudo', 'sh', 'python', 'python3')
        phrases = ('npm install', 'npm i ', 'pip install', 'git push', 'git reset --hard', 'bash -c')
        for command in commands:
            with self.subTest(command=command):
                self.assertNotIn(command.split()[0], programs)
                if command.startswith('chmod'):
                    self.assertEqual(command, 'chmod +x *')
                for phrase in phrases:
                    self.assertNotIn(phrase, command + ' ')

    def test_permissions_chmod_template_has_only_plus_x(self):
        entries = self.permissions_template_entries()
        self.assertEqual(entries.count('Bash(chmod +x *)'), 1)
        self.assertEqual([e for e in entries if e.startswith('Bash(chmod')], ['Bash(chmod +x *)'])

    def test_permissions_chmod_installed_and_passed_to_runner(self):
        self.ready()
        self.assertIn('Bash(chmod +x *)', (self.project / '.ai/permissions.allow').read_text().splitlines())
        self.tool('ai-run', '--approved')
        calls = (self.project / '.ai/local/mock-args').read_text().splitlines()
        self.assertTrue(any('Bash(chmod +x *)' in call for call in calls))

    def test_permissions_chmod_runner_prompt_rule(self):
        section = ' '.join(self.prompt_section('runner').split())
        self.assertIn('chmod +x', section)
        self.assertIn('inside this checkout', section)
        self.setup_old(self.old_toolkit())
        self.upgrade('--apply')
        installed = ' '.join((self.project / '.ai/prompts/runner.md').read_text().split())
        self.assertIn('chmod +x', installed)
        self.assertIn('inside this checkout', installed)

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

    # ---------------------------------------------------------------- gate-broken guard (T010)
    def gate_shell(self, script, *args, expected=0):
        return self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh\n' + script, 'gate-test', *args],
                            expected=expected)

    def gate_digest(self):
        return self.gate_shell('ai_guard_digest').stdout.strip()

    def test_observation_gate_flag_skips_record_helpers(self):
        self.setup_project()
        ran = self.base / 'helper-ran'
        (self.project / '.ai/bin/lib/workflow.py').write_text(
            'import os, sys\n'
            f'with open({str(ran)!r}, "a") as f: f.write(" ".join(sys.argv[1:]) + "\\n")\n')
        result = self.gate_shell('AI_GATE_BROKEN=1 ai_observe step build; echo "observe=$?"\n'
                                 'AI_GATE_BROKEN=1 ai_notify_log m; echo "log=$?"')
        self.assertEqual(result.stdout, 'observe=0\nlog=0\n')
        self.assertFalse(ran.exists())
        result = self.gate_shell('ai_observe step build; echo "observe=$?"\n'
                                 'ai_notify_log m; echo "log=$?"')
        self.assertEqual(result.stdout, 'observe=0\nlog=0\n')
        self.assertEqual(ran.read_text().splitlines(),
                         ['observe step build', f'notify-log {self.project} m'])

    def test_observation_gate_check_sets_flag_on_changed_or_unreadable_gate(self):
        self.setup_project()
        digest = self.gate_digest()
        probe = ('if ai_gate_check "$1"; then rc=0; else rc=1; fi\n'
                 'printf "rc=%s flag=%s\\n" "$rc" "${AI_GATE_BROKEN:-unset}"')
        self.assertEqual(self.gate_shell(probe, digest).stdout, 'rc=0 flag=unset\n')
        check = self.project / '.ai/bin/ai-check'
        original = check.read_bytes()
        check.write_bytes(original + b'#')
        self.assertEqual(self.gate_shell(probe, digest).stdout, 'rc=1 flag=1\n')
        check.write_bytes(original)
        self.assertEqual(self.gate_shell(probe, digest).stdout, 'rc=0 flag=unset\n')
        # .ai/bin replaced by a symlink: the digest is unreadable, which counts as broken.
        (self.project / '.ai/bin').rename(self.project / '.ai/bin-real')
        (self.project / '.ai/bin').symlink_to('bin-real')
        self.assertEqual(self.gate_shell(probe, digest).stdout, 'rc=1 flag=1\n')

    def test_observation_gate_ok_form_sets_flag_in_calling_shell(self):
        self.setup_project()
        script = ('AI_APPROVED_GATE=0000; readonly AI_APPROVED_GATE\n'
                  'written() { local gate_ok=no; if ai_gate_check "$AI_APPROVED_GATE"; then gate_ok=yes; fi\n'
                  '  printf "gate_ok=%s\\n" "$gate_ok"; }\n'
                  # Counter-example (never use it): the flag is set in the subshell only.
                  'substituted() { local gate_ok; gate_ok=$(ai_gate_check "$AI_APPROVED_GATE" && echo yes || echo no)\n'
                  '  printf "gate_ok=%s\\n" "$gate_ok"; }\n'
                  '"$1"\nprintf "flag=%s\\n" "${AI_GATE_BROKEN:-unset}"')
        self.assertEqual(self.gate_shell(script, 'written').stdout, 'gate_ok=no\nflag=1\n')
        self.assertEqual(self.gate_shell(script, 'substituted').stdout, 'gate_ok=no\nflag=unset\n')

    def test_observation_gate_pipeline_resume_gate_stop_unchanged(self):
        self.ready()
        validate = self.project / '.ai/validate'
        original = validate.read_bytes()
        validate.write_bytes(original + b'# approved before a change\n')
        self.approve_run()
        validate.write_bytes(original)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, AI_RECOVERY_ATTEMPT='1')
        self.assertIn('Error: Gate files changed since the run was approved; rerun ai-pipeline --approved yourself.',
                      result.stderr)
        self.assertEqual(self.notifications().count('⛔'), 1)
        self.assertIn('Gate files changed since the run was approved', self.notifications())
        self.assertFalse((self.project / '.ai/local/pipeline.active').exists())

    def test_observation_gate_deps_installer_changing_gate_sets_flag(self):
        self.deps_ready()
        with (self.project / '.ai/ci-setup').open('a') as file:
            file.write("printf '# installer\\n' >> .ai/bin/lib/workflow.py\n")
        (self.project / '.ai/local').mkdir(exist_ok=True)  # ai_root makes it in the scripts
        result = self.gate_shell('gate=$(ai_guard_digest)\n'
                                 'if ai_deps "$gate" 60; then echo installed; fi\n'
                                 'printf "error=%s\\nflag=%s\\n" "$AI_DEPS_ERROR" "${AI_GATE_BROKEN:-unset}"')
        self.assertRegex(result.stdout, r'error=Dependency setup \(\.ai/ci-setup\) changed the approved workflow '
                                        r'gate; see \.ai/local/deps-\w{8}\.log\nflag=1\n$')
        self.assertNotIn('installed', result.stdout)

    def test_observation_gate_runner_tamper_stop_runs_no_helper(self):
        self.ready()
        result = self.tool('ai-run', '--approved', expected=1,
                           MOCK_CLAUDE='tamper', MOCK_TAMPER_PATH='.ai/bin/lib/workflow.py')
        self.assertIn('Error: Approved workflow gate changed during this run. Stop, inspect the diff, '
                      'and explicitly reapprove before resuming.', result.stderr)
        self.assertFalse((self.project / 'UNTRUSTED_HELPER_RAN').exists())
        self.assertEqual(self.notifications().count('⛔ STOPPED, needs you: runner stopped at T001'), 1)

    def logged_notifications(self):
        path = self.project / '.ai/local/notifications.log'
        return [json.loads(line)['message'] for line in path.read_text().splitlines()] if path.exists() else []

    def test_observation_notify_log_mirrors_what_was_sent(self):
        self.ready()
        self.tool('ai-run', '--approved', MOCK_CLAUDE='limit-once')
        sent = self.notifications().splitlines()
        self.assertTrue(any('⏸ PAUSED: Claude usage limit' in line for line in sent), sent)
        self.assertEqual(self.logged_notifications(), sent)
        # without a notification command the lines are still kept
        (self.project / '.ai/local/notifications.log').unlink()
        self.notify_log.unlink()
        env = dict(self.env)
        env.pop('AI_NOTIFY_CMD')
        self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; AI_ROOT=$PWD; ai_notify "hello there"'], env=env)
        self.assertEqual(self.logged_notifications(), ['[project with spaces] hello there'])
        self.assertFalse(self.notify_log.exists())

    def test_observation_notify_watchdog_notification_is_logged_and_symlink_safe(self):
        self.setup_project()
        self.watchdog_stalled('implementing')
        other = self.base / 'other'
        other.mkdir()
        self.watchdog_runner(other)
        sentinel = self.base / 'sentinel'
        sentinel.write_text('keep\n')
        (self.project / '.ai/local').mkdir(exist_ok=True)
        (self.project / '.ai/local/notifications.log').symlink_to(sentinel)
        self.watchdog(expected=1)
        self.assertEqual(sentinel.read_text(), 'keep\n')
        self.assertEqual(len(self.notifications().splitlines()), 1)
        (self.project / '.ai/local/notifications.log').unlink()
        self.watchdog_phase('ready_for_review')
        self.watchdog()
        self.watchdog_stalled('fixing_review')
        self.watchdog(expected=1)
        self.assertEqual(self.logged_notifications(), self.notifications().splitlines()[1:])

    def test_observation_notify_fifo_log_and_held_lock_do_not_block_the_run(self):
        import fcntl
        self.ready()
        local = self.project / '.ai/local'
        local.mkdir(exist_ok=True)
        os.mkfifo(local / 'notifications.log')
        with open(local / 'notifications.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.tool('ai-run', '--approved', MOCK_CLAUDE='limit-once')
        self.helper('tasks', 'complete')
        self.assertIn('⏸ PAUSED: Claude usage limit', self.notifications())

    def pause_probe(self):
        probe = self.mock_bin / 'probe-sleep'
        probe.write_text('#!/usr/bin/env bash\n'
                         f'cp .ai/local/observation.json "{self.base}/during.json"\n')
        probe.chmod(0o755)
        return probe

    def test_observation_notify_usage_limit_pause_marks_the_stage_paused(self):
        self.ready()
        (self.project / '.ai/local').mkdir(exist_ok=True)
        self.helper('observe', 'step', 'build', 'T001')
        self.tool('ai-run', '--approved', MOCK_CLAUDE='limit-once', AI_SLEEP=str(self.pause_probe()))
        during = json.loads((self.base / 'during.json').read_text())
        self.assertEqual((during['state'], during['stage']), ('paused', 'build'))
        self.assertIn('Claude until', during['note'])
        after = json.loads((self.project / '.ai/local/observation.json').read_text())
        # ai-run goes on to its own validation (T004), so the resumed run ends on the checks box
        self.assertEqual((after['state'], after['stage'], after['note']), ('active', 'checks', ''))

    def test_observation_notify_codex_pause_marks_the_stage_paused(self):
        self.ready()
        self.tool('ai-run', '--approved')
        (self.project / '.ai/local').mkdir(exist_ok=True)
        self.helper('observe', 'step', 'review')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='limit-once', AI_REVIEWER='codex',
                  AI_SLEEP=str(self.pause_probe()))
        during = json.loads((self.base / 'during.json').read_text())
        self.assertEqual((during['state'], during['stage']), ('paused', 'review'))
        self.assertIn('Codex until', during['note'])
        after = json.loads((self.project / '.ai/local/observation.json').read_text())
        self.assertEqual((after['state'], after['stage']), ('active', 'review'))

    def test_observation_notify_gate_changed_stop_notifies_but_logs_nothing(self):
        self.ready()
        result = self.tool('ai-run', '--approved', expected=1,
                           MOCK_CLAUDE='tamper', MOCK_TAMPER_PATH='.ai/bin/lib/workflow.py')
        self.assertIn('Approved workflow gate changed during this run', result.stderr)
        self.assertEqual(self.notifications().count('⛔ STOPPED, needs you: runner stopped at T001'), 1)
        self.assertFalse((self.project / 'UNTRUSTED_HELPER_RAN').exists())
        self.assertFalse((self.project / '.ai/local/notifications.log').exists())

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

    def scratch_victim(self):
        """An external directory a session might point the host's delete at."""
        victim = self.base / 'victim'
        (victim / 'scratch').mkdir(parents=True)
        (victim / 'scratch/keep').write_text('keep\n')
        (victim / 'keep').write_text('keep\n')
        return victim

    def clear_scratch(self):
        return self.helper('clear-scratch')

    def test_scratch_clear_refuses_a_symlinked_local_or_ai(self):
        self.setup_project()
        victim = self.scratch_victim()
        local = self.project / '.ai/local'
        local.mkdir(exist_ok=True)
        local.rename(self.base / 'local-aside')
        local.symlink_to(victim)
        result = self.clear_scratch()
        self.assertIn('Warning: could not clear .ai/local/scratch', result.stderr)
        self.assertTrue((victim / 'scratch/keep').exists())
        local.unlink()
        ai = self.project / '.ai'
        other = self.base / 'other-ai'
        (other / 'local/scratch').mkdir(parents=True)
        (other / 'local/scratch/keep').write_text('keep\n')
        ai.rename(self.base / 'ai-aside')
        ai.symlink_to(other)
        result = self.clear_scratch()
        self.assertIn('Warning: could not clear .ai/local/scratch', result.stderr)
        self.assertTrue((other / 'local/scratch/keep').exists())

    def test_scratch_clear_removes_a_symlink_without_following_it(self):
        self.setup_project()
        victim = self.scratch_victim()
        scratch = self.project / '.ai/local/scratch'
        scratch.parent.mkdir(exist_ok=True)
        scratch.symlink_to(victim)
        result = self.clear_scratch()
        self.assertEqual(result.stdout + result.stderr, '')
        self.assertFalse(scratch.is_symlink() or scratch.exists())
        self.assertTrue((victim / 'keep').exists())
        self.assertTrue((victim / 'scratch/keep').exists())

    def test_scratch_clear_removes_a_tree_but_never_enters_inner_symlinks(self):
        self.setup_project()
        victim = self.scratch_victim()
        scratch = self.project / '.ai/local/scratch'
        (scratch / 'nested/deeper').mkdir(parents=True)
        (scratch / 'tmp.test.sh').write_text('echo\n')
        (scratch / 'nested/deeper/file').write_text('x\n')
        (scratch / 'link').symlink_to(victim)
        (scratch / 'nested/link').symlink_to(victim / 'keep')
        result = self.clear_scratch()
        self.assertEqual(result.stdout + result.stderr, '')
        self.assertFalse(scratch.exists())
        self.assertTrue((self.project / '.ai/local').is_dir())
        self.assertTrue((victim / 'keep').exists())
        self.assertTrue((victim / 'scratch/keep').exists())

    def test_scratch_clear_handles_missing_scratch_and_a_regular_file(self):
        self.setup_project()
        scratch = self.project / '.ai/local/scratch'
        scratch.parent.mkdir(exist_ok=True)
        result = self.clear_scratch()
        self.assertEqual(result.stdout + result.stderr, '')
        scratch.write_text('a file, not a directory\n')
        result = self.clear_scratch()
        self.assertEqual(result.stdout + result.stderr, '')
        self.assertFalse(scratch.exists())

    def test_scratch_clear_runs_before_and_after_each_session(self):
        self.ready()
        scratch = self.project / '.ai/local/scratch'
        scratch.mkdir(parents=True)
        (scratch / 'old').write_text('left by an earlier session\n')
        self.tool('ai-run', '--approved', MOCK_CLAUDE='scratch-leftover')
        self.assertIn('Status: DONE', (self.project / '.ai/tasks.md').read_text())
        # The mock records any scratch it finds at session start: there must be none.
        seen = self.base / 'scratch-seen'
        self.assertFalse(seen.exists(), seen.read_text() if seen.exists() else '')
        self.assertFalse(scratch.exists())
        self.assertNotIn('scratch', self.run_cmd(['git', 'ls-files']).stdout)
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')

    def test_scratch_clear_never_follows_a_symlink_a_session_planted(self):
        self.ready()
        victim = self.scratch_victim()
        self.tool('ai-run', '--approved', expected=None, MOCK_CLAUDE='scratch-parent-symlink',
                  MOCK_VICTIM=str(victim))
        self.assertTrue((victim / 'scratch/keep').exists())
        self.assertTrue((victim / 'keep').exists())

    def test_scratch_clear_removes_a_scratch_symlink_after_the_session(self):
        self.ready()
        victim = self.scratch_victim()
        self.tool('ai-run', '--approved', MOCK_CLAUDE='scratch-symlink', MOCK_VICTIM=str(victim))
        scratch = self.project / '.ai/local/scratch'
        self.assertFalse(scratch.is_symlink() or scratch.exists())
        self.assertTrue((victim / 'keep').exists())
        self.assertTrue((victim / 'scratch/keep').exists())

    def test_scratch_dir_prompts_name_it_and_share_one_block(self):
        self.ready()
        # The mock asserts the runner prompt names .ai/local/scratch/ on every session.
        self.tool('ai-run', '--approved')
        self.assertIn('Status: DONE', (self.project / '.ai/tasks.md').read_text())
        for name in ('runner', 'triage'):
            self.assertIn('`.ai/local/scratch/`', self.prompt_section(name))
            self.assertIn('`rm` is not allowed', self.prompt_section(name))
        self.assertEqual(self.prompt_section('runner'), self.prompt_section('triage'))
        self.assertIn('.ai/local/scratch/', (ROOT / 'templates/CLAUDE.md').read_text())

    def test_scratch_dir_docs_describe_the_host_clear(self):
        for path in ('README.md', 'docs/workflow.md'):
            text = ' '.join((ROOT / path).read_text().split())
            self.assertIn('empties `.ai/local/scratch`', text, path)
            self.assertIn('never follows a symlink', text, path)

    def test_scratch_clear_startup_refuses_a_preexisting_scratch_symlink(self):
        self.ready()
        victim = self.scratch_victim()
        scratch = self.project / '.ai/local/scratch'
        scratch.parent.mkdir(exist_ok=True)
        scratch.symlink_to(victim)
        result = self.tool('ai-run', '--approved', expected=1)
        self.assertIn('Unsafe symlink in workflow path', result.stderr)
        self.assertTrue((victim / 'keep').exists())
        self.assertTrue((victim / 'scratch/keep').exists())
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())

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

    def invalid_queue(self):
        return task('T001', dependencies='T002') + '\n' + task('T002')

    def test_queue_check_command(self):
        self.ready()
        result = self.tool('ai-task', 'check')
        self.assertEqual(result.stdout.strip(), 'Task queue OK: 1 tasks, 0 DONE')
        queue = self.project / '.ai/tasks.md'
        queue.write_text(self.invalid_queue())
        before = queue.read_text()
        result = self.tool('ai-task', 'check', expected=1)
        self.assertIn('dependencies must exist earlier in the queue: T002', result.stderr)
        self.assertEqual(queue.read_text(), before)

    def night_queue(self):
        fence = '```\n## T009 — not a heading\n```\n\n'
        return ('# Task queue\n\nPreamble text.\n\n' + task('T001', dependencies='T011') + task('T002')
                + task('T003', status='DONE') + task('T004') + task('T005', dependencies='T014')
                + task('T011').replace('Pending.\n', 'Pending.\n' + fence)
                + task('T014') + '## Notes\nTrailer text.\n')

    def queue_blocks(self, text):
        blocks = {}
        for part in re.split(r'(?m)^(?=## T(?!009)\d{3} — )', text)[1:]:
            blocks[part[3:7]] = part.split('## Notes')[0].rstrip('\n')
        return blocks

    def test_queue_reorder_night_case(self):
        self.ready()
        queue = self.project / '.ai/tasks.md'
        original = self.night_queue()
        queue.write_text(original)
        self.helper('tasks', 'check', expected=1)
        result = self.helper('tasks', 'reorder')
        self.assertEqual(result.stdout.strip(), 'Task queue reordered (dependencies first): '
                         'T011 T001 T002 T003 T004 T014 T005')
        self.helper('tasks', 'check')
        text = queue.read_text()
        self.assertEqual(re.findall(r'(?m)^## (T(?!009)\d{3}) — ', text),
                         ['T011', 'T001', 'T002', 'T003', 'T004', 'T014', 'T005'])
        self.assertEqual(self.queue_blocks(text), self.queue_blocks(original))
        self.assertTrue(text.startswith('# Task queue\n\nPreamble text.\n\n'))
        self.assertTrue(text.endswith('## Notes\nTrailer text.\n'))
        self.assertIn('## T009 — not a heading', self.queue_blocks(text)['T011'])

    def test_queue_reorder_valid_queue_is_untouched(self):
        self.ready(task('T001') + task('T002', dependencies='T001'))
        queue = self.project / '.ai/tasks.md'
        before, mtime = queue.read_bytes(), queue.stat().st_mtime_ns
        result = self.helper('tasks', 'reorder')
        self.assertEqual(result.stdout + result.stderr, '')
        self.assertEqual(queue.read_bytes(), before)
        self.assertEqual(queue.stat().st_mtime_ns, mtime)

    def test_queue_reorder_keeps_done_tasks(self):
        self.ready(task('T001', dependencies='T003') + task('T002', status='DONE') + task('T003'))
        self.helper('tasks', 'reorder')
        self.helper('plan-keeps-done', 'HEAD')
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')

    def test_queue_reorder_rejects_what_it_cannot_repair(self):
        two = task('T001').replace('Dependencies: none\n', 'Dependencies: none\nDependencies: none\n')
        cases = [
            (task('T001', dependencies='T002') + task('T002', dependencies='T001'),
             'dependency cycle: T001 -> T002 -> T001'),
            (task('T001', dependencies='T001'), 'dependency cycle: T001 -> T001'),
            (task('T001', dependencies='T009'), 'T001: dependency T009 is not a task in the queue'),
            (task('T001') + task('T002', dependencies='T001 (after the API lands)'),
             'T002: Dependencies: must be "none" or task IDs'),
            (task('T001') + task('T002') + task('T003', dependencies='T001 and T002'),
             'T003: Dependencies: must be "none" or task IDs'),
            (two, 'T001: expected exactly one Dependencies: line'),
            (task('T001') + task('T001'), 'Duplicate task IDs.'),
            (task('T001', dependencies='T002') + '## Notes\nx\n\n' + task('T002'),
             'cannot reorder: section "## Notes" sits between tasks'),
        ]
        self.ready()
        queue = self.project / '.ai/tasks.md'
        for text, message in cases:
            queue.write_text(text)
            result = self.helper('tasks', 'reorder', expected=1)
            self.assertIn(message, result.stderr)
            self.assertEqual(queue.read_text(), text)

    def test_queue_reorder_preamble_sections_are_kept(self):
        self.ready()
        queue = self.project / '.ai/tasks.md'
        preamble = '# Queue\n\n## Context\nKeep this intro.\n\n'
        queue.write_text(preamble + task('T001', dependencies='T002') + task('T002'))
        result = self.helper('tasks', 'reorder')
        self.assertEqual(result.stdout.strip(), 'Task queue reordered (dependencies first): T002 T001')
        text = queue.read_text()
        self.assertTrue(text.startswith(preamble + '## T002 — '))
        self.assertEqual(re.findall(r'(?m)^## (T\d{3}) — ', text), ['T002', 'T001'])
        self.helper('tasks', 'check')

    def test_queue_reorder_tab_after_hashes(self):
        self.ready()
        queue = self.project / '.ai/tasks.md'
        first = task('T001', dependencies='T002').replace('## T001', '##\tT001', 1)
        queue.write_text(first + task('T002'))
        self.helper('tasks', 'check', expected=1)
        result = self.helper('tasks', 'reorder')
        self.assertEqual(result.stdout.strip(), 'Task queue reordered (dependencies first): T002 T001')
        text = queue.read_text()
        self.assertIn('\n##\tT001 — ', text)
        self.assertEqual([line for line in text.splitlines() if line.startswith('##\t')],
                         [line for line in first.splitlines() if line.startswith('##\t')])
        self.assertLess(text.index('## T002 — '), text.index('##\tT001 — '))
        self.helper('tasks', 'check')

    def test_queue_reorder_command(self):
        self.ready()
        (self.project / '.ai/tasks.md').write_text(self.night_queue())
        result = self.tool('ai-task', 'reorder')
        self.assertIn('Task queue reordered (dependencies first): T011 T001', result.stdout)
        self.tool('ai-task', 'check')

    def test_task_sections_fill_raid_case(self):
        self.ready()
        queue = self.project / '.ai/tasks.md'
        no_result = '### Result / notes\nPending.\n'

        def without_likely(text, task_id):
            return text.replace(f'### Likely affected modules\n{task_id}.txt\n', '')
        t19 = without_likely(task('T019'), 'T019').replace(no_result, '')
        t20 = task('T020').replace(no_result, '')
        t01 = without_likely(task('T001', status='DONE'), 'T001')
        original = '# Queue\n\nPreamble.\n\n' + t01 + t19 + t20 + '## Notes\nTrailer.\n'
        queue.write_text(original)
        self.commit()
        result = self.helper('tasks', 'fill-sections')
        self.assertEqual(result.stdout.strip(), 'Task queue: added missing sections: '
                         'T019 (Likely affected modules, Result / notes), T020 (Result / notes)')
        text = queue.read_text()
        self.assertTrue(text.startswith('# Queue\n\nPreamble.\n\n' + t01 + '## T019'))
        self.assertTrue(text.endswith('## Notes\nTrailer.\n'))
        parts = self.queue_blocks(text)
        self.assertEqual(parts['T001'], t01.rstrip('\n'))
        self.assertEqual(parts['T019'].count('### Likely affected modules\n(not listed)\n\n### Acceptance'), 1)
        self.assertTrue(parts['T019'].endswith('### Validation\nbash .ai/validate\n\n### Result / notes'))
        self.assertTrue(parts['T020'].endswith('### Validation\nbash .ai/validate\n\n### Result / notes'))
        self.assertEqual(parts['T020'].count('### Likely affected modules'), 1)
        self.helper('plan-keeps-done', 'HEAD')
        result = self.helper('tasks', 'check', expected=1)
        self.assertIn('T001: missing ### Likely affected modules', result.stderr)
        queue.write_text(text.replace(t01, task('T001', status='DONE'), 1))
        self.helper('tasks', 'check')

    def test_task_sections_fill_complete_queue_is_untouched(self):
        self.ready(task('T001') + task('T002', dependencies='T001'))
        queue = self.project / '.ai/tasks.md'
        before, mtime = queue.read_bytes(), queue.stat().st_mtime_ns
        result = self.helper('tasks', 'fill-sections')
        self.assertEqual(result.stdout + result.stderr, '')
        self.assertEqual(queue.read_bytes(), before)
        self.assertEqual(queue.stat().st_mtime_ns, mtime)

    def test_task_sections_fill_ignores_fences_and_adds_only_two(self):
        self.ready()
        queue = self.project / '.ai/tasks.md'
        fenced = task('T001').replace('### Result / notes\nPending.\n',
                                      '```\n### Result / notes\n```\n')
        queue.write_text(fenced)
        self.helper('tasks', 'check', expected=1)
        self.helper('tasks', 'fill-sections')
        text = queue.read_text()
        self.assertTrue(text.rstrip('\n').endswith('```\n\n### Result / notes'))
        self.helper('tasks', 'check')
        no_goal = task('T001').replace('### Goal\nWrite a local test artifact.\n', '') \
            .replace('### Result / notes\nPending.\n', '')
        queue.write_text(no_goal)
        self.helper('tasks', 'fill-sections')
        self.assertNotIn('### Goal', queue.read_text())
        self.assertIn('### Result / notes', queue.read_text())
        result = self.helper('tasks', 'check', expected=1)
        self.assertIn('T001: missing ### Goal', result.stderr)

    def test_queue_check_empty_template_queue_fails(self):
        self.setup_project()
        result = self.tool('ai-task', 'check', expected=1)
        self.assertIn('No real tasks', result.stderr)

    def test_queue_check_invalid_queue_stops_plan_review(self):
        self.ready(self.invalid_queue())
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertFalse((self.base / 'codex-plan-calls').exists())
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        error = (self.project / '.ai/local/last-error').read_text()
        # ai_die prefixes the stage ("Pipeline stopped during plan review: ").
        self.assertIn('Task queue is invalid:', error)
        self.assertIn('T002', error)
        notes = self.notifications()
        self.assertEqual(notes.count('⛔'), 1)
        self.assertIn('Task queue is invalid', notes)
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('plan_review', 'stopped'))

    def test_queue_check_invalid_queue_escalates_without_recovery_session(self):
        self.ready(self.invalid_queue())
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1')
        self.assertFalse((self.base / 'recover-calls').exists())
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        self.assertIn('Task queue is invalid', self.notifications())

    def test_queue_check_done_task_still_skips_plan_review(self):
        self.ready(task('T001', 'DONE') + '\n' + task('T002'))
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertFalse((self.base / 'codex-plan-calls').exists())

    def test_queue_check_invalid_queue_stops_with_skip_plan_review(self):
        self.ready(self.invalid_queue())
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--skip-plan-review',
                  expected=1)
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        self.assertIn('during implementation: Task queue is invalid:',
                      (self.project / '.ai/local/last-error').read_text())
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('build', 'stopped'))
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--skip-plan-review',
                  expected=1, AI_AUTO_RECOVER='1')
        self.assertFalse((self.base / 'recover-calls').exists())

    def test_queue_check_plan_prompt_mentions_the_command(self):
        text = (ROOT / 'templates/.ai/prompts/plan.md').read_text()
        self.assertIn('.ai/bin/ai-task check', text)

    def budget_queue(self, todo, done=0):
        return '\n'.join([task(f'T{n:03}', 'DONE') for n in range(1, done + 1)] +
                         [task(f'T{n:03}', 'TODO', f'T{n - 1:03}' if n > done + 1 else 'none')
                          for n in range(done + 1, done + todo + 1)])

    def test_session_budget_covers_the_unfinished_queue(self):
        self.ready(self.budget_queue(20))
        result = self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='error')
        self.assertIn('Session budget: 22 (default: 20 unfinished tasks + 2, at least 16)', result.stdout)

    def test_session_budget_has_a_floor_of_16(self):
        self.ready(self.budget_queue(3))
        result = self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='error')
        self.assertIn('Session budget: 16 (default: 3 unfinished tasks + 2, at least 16)', result.stdout)

    def test_session_budget_ignores_done_tasks(self):
        self.ready(self.budget_queue(19, done=1))
        result = self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='error')
        self.assertIn('Session budget: 21 (default: 19 unfinished tasks + 2', result.stdout)

    def test_session_budget_explicit_sessions_wins(self):
        self.ready(task('T001') + '\n' + task('T002'))
        result = self.tool('ai-run', '--approved', '--sessions', '1', expected=1)
        self.assertIn('Session budget: 1 (--sessions)', result.stdout)
        self.assertIn('Session limit reached', result.stderr)

    def test_session_budget_end_to_end_runs_past_session_16(self):
        self.ready(self.budget_queue(17))
        result = self.tool('ai-run', '--approved', timeout=LONG_RUN_TIMEOUT)
        self.assertIn('Session budget: 19', result.stdout)
        self.assertIn('Iteration 17/19', result.stdout)
        self.assertIn('Tasks complete and validation passed', result.stdout + result.stderr)
        self.assertNotIn('Session limit reached', result.stdout + result.stderr)

    def test_session_budget_end_to_end_explicit_16_stops(self):
        self.ready(self.budget_queue(17))
        result = self.tool('ai-run', '--approved', '--sessions', '16', expected=1, timeout=LONG_RUN_TIMEOUT)
        self.assertIn('Session limit reached', result.stdout + result.stderr)
        self.assertNotIn('Iteration 17/', result.stdout + result.stderr)

    def test_session_budget_not_printed_for_triage_and_revise_plan(self):
        self.ready()
        for flag in ('--triage', '--revise-plan'):
            result = self.tool('ai-run', '--approved', flag, expected=None)
            self.assertNotIn('Session budget', result.stdout)

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

    def plan_round(self, findings, number, **env):
        """One hand-run plan review (host commit + record); a source change keeps plan digests distinct."""
        (self.project / 'src.txt').write_text(f'source {number}\n')
        self.commit(f'source {number}')
        self.tool('ai-review', '--plan', MOCK_CODEX_PLAN_FINDINGS=findings, **env)

    def plan_current(self, expected=0):
        return self.helper('plan-rounds', 'current', 'main', expected=expected).stdout.split()

    def plan_dispositions(self, number, rows):
        digest = self.plan_current()[1]
        path = self.project / '.ai/reviews/plan-dispositions.md'
        text = path.read_text() if path.exists() else '# Plan review dispositions\n'
        path.write_text(text + f'\n## Plan review round {number} (report {digest})\n\n'
                        '| Finding | Disposition | Evidence / reason | Task |\n| --- | --- | --- | --- |\n' + rows)
        self.commit(f'dispositions {number}')

    def plan_store(self):
        return next((self.base / 'host-state').rglob('plan-rounds-*.json'))

    def test_plan_rounds_history_pairs_findings_with_dispositions(self):
        self.ready()
        self.plan_round('P1|Gap in tests;P2|Unrelated area', 1)
        self.plan_dispositions(1, '| P1 | accepted | add the test | T002 |\n| P2 | rejected | out of scope here | |\n')
        self.plan_round('P1|Gap in tests again', 2)
        self.plan_dispositions(2, '| P1 | accepted | tests added now | T002 |\n')
        # An implementation review in the same range is not plan history.
        (self.project / '.ai/reviews').mkdir(exist_ok=True)
        (self.project / '.ai/reviews/current.md').write_text('## MAJOR findings\n- ZZ9: implementation thing\n')
        self.run_cmd(['git', 'add', '--all'])
        self.run_cmd(['git', 'commit', '-qm', 'chore(ai): record independent review'])
        self.plan_round('P1|Gap still open', 3)
        self.assertEqual(self.plan_current()[0], '3')
        self.assertEqual(self.helper('plan-history', 'main', '--count').stdout.strip(), '2')
        history = self.helper('plan-history', 'main').stdout
        self.assertIn('## Previous plan review rounds', history)
        self.assertIn('### Round 1', history)
        self.assertIn('- P1 [MAJOR] Gap in tests — accepted (T002)', history)
        self.assertIn('- P2 [MAJOR] Unrelated area — rejected', history)
        self.assertIn('### Round 2', history)
        self.assertIn('- P1 [MAJOR] Gap in tests again — accepted (T002)', history)
        self.assertNotIn('Round 3', history)
        self.assertNotIn('Gap still open', history)
        self.assertNotIn('ZZ9', history)

    def test_plan_history_marks_rounds_without_a_revision(self):
        self.ready()
        self.plan_round('P1|Gap in tests', 1)
        self.plan_round('P1|Gap in tests', 2)
        self.assertIn('- P1 [MAJOR] Gap in tests — no revision recorded', self.helper('plan-history', 'main').stdout)

    def test_plan_rounds_ignore_agent_commits_and_tampered_reports(self):
        self.ready()
        self.plan_round('P1|Gap in tests', 1)
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '1')
        (self.project / 'src.txt').write_text('agent change\n')
        self.commit('chore(ai): record plan review')  # agent-chosen subject, no host record
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '1')
        review = self.project / '.ai/reviews/plan.md'
        review.write_text(review.read_text().replace('Gap in tests', 'Nothing to see'))
        self.commit('chore(ai): record plan review')
        self.helper('plan-rounds', 'record', 'main', 'HEAD', expected=1)
        self.plan_current(expected=1)
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '1')

    def test_plan_rounds_pipeline_and_hand_run_record_once_per_review(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '1')
        self.assertEqual(self.plan_current()[0], '1')
        self.tool('ai-review', '--plan')  # tree changed since: a second review, a second round
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '2')
        self.run_cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'chore(ai): record plan review'])
        self.helper('plan-rounds', 'record', 'main', 'HEAD')  # same report from another commit
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '2')

    def test_plan_rounds_restart_when_a_branch_name_is_recreated(self):
        self.ready()
        self.plan_round('P1|Gap in tests', 1)
        self.plan_round('P1|Gap in tests', 2)
        self.assertEqual(self.plan_current()[0], '2')
        self.run_cmd(['git', 'switch', 'main'])
        self.run_cmd(['git', 'merge', '-q', '--ff-only', 'feature/test'])
        self.run_cmd(['git', 'branch', '-q', '-d', 'feature/test'])
        self.run_cmd(['git', 'switch', '-q', '-c', 'feature/test'])
        self.plan_round('P1|Gap in tests', 3)
        self.assertEqual(self.plan_current()[0], '1')

    def test_plan_rounds_sync_records_a_crashed_review_once(self):
        self.ready()
        self.plan_round('P1|Gap in tests', 1)
        self.plan_store().write_text('[]\n')  # the record was lost between the host commit and its write
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '0')
        self.plan_current(expected=1)
        self.helper('plan-rounds', 'sync', 'main')
        self.helper('plan-rounds', 'sync', 'main')
        self.assertEqual(self.plan_current()[0], '1')

    def test_plan_rounds_sync_ignores_a_forged_report(self):
        self.ready()
        self.plan_round('P1|Gap in tests', 1)
        self.plan_store().write_text('[]\n')
        review = self.project / '.ai/reviews/plan.md'
        review.write_text(review.read_text().replace('Gap in tests', 'Nothing to see'))
        self.commit('chore(ai): record plan review')
        self.helper('plan-rounds', 'sync', 'main')
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '0')

    PLAN_ROWS = ('| P1 | accepted | add the missing test | T002 |\n'
                 '| P2 | rejected | rollback is covered in docs/rollback.md:12 | |\n')
    PLAN_REJECTED = ('| P1 | rejected | the test exists in tests/test_x.py:40 | |\n'
                     '| P2 | rejected | rollback is covered in docs/rollback.md:12 | |\n')

    def open_plan_section(self, findings='P1|Gap in tests;P2|Unclear rollback', rounds=1, **env):
        """Plan review `rounds` (earlier rounds get a committed section with a Convergence line),
        then the host opens the current round's section. Returns START (HEAD before opening)."""
        self.ready(task('T001', 'DONE') + task('T002', dependencies='T001'))
        for number in range(1, rounds + 1):
            if number > 1:
                self.plan_dispositions(number - 1, self.PLAN_ROWS + 'Convergence: rollback keeps coming back\n')
            self.plan_round(findings, number, **env)
        start = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('start-plan-dispositions', 'main')
        return start

    def plan_check(self, start, *flags, expected=0):
        return self.helper('plan-dispositions-check', '--since', start, '--base', 'main', '--fresh', *flags,
                           expected=expected)

    def test_plan_dispositions_complete_section_passes_and_counts(self):
        start = self.open_plan_section()
        path = self.project / '.ai/reviews/plan-dispositions.md'
        self.run_cmd(['git', 'cat-file', '-e', f'{start}:.ai/reviews/plan-dispositions.md'], expected=128)
        opened = path.read_text()
        digest = self.plan_current()[1]
        self.assertIn(f'## Plan review round 1 (report {digest})\n\nPlan review HEAD: {start}\n\n'
                      '| Finding | Disposition | Evidence / reason | Task |\n| --- | --- | --- | --- |\n', opened)
        self.helper('start-plan-dispositions', 'main')  # resume: no second header
        self.assertEqual(path.read_text(), opened)
        path.write_text(opened + self.PLAN_ROWS)
        self.assertEqual(self.plan_check(start).stdout.strip(), 'accepted=1 rejected=1 needs_human=0')
        self.assertEqual(self.plan_check(start, '--questions').stdout, '')
        # START already holding the same header (rows committed, e.g. a resume) passes too.
        self.helper('start-plan-dispositions', 'main')
        self.assertEqual(path.read_text(), opened + self.PLAN_ROWS)
        self.commit('rows')
        resumed = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.assertEqual(self.plan_check(resumed).stdout.strip(), 'accepted=1 rejected=1 needs_human=0')
        self.helper('plan-dispositions-check', '--since', start, expected=1)  # --base is required

    def test_plan_dispositions_minor_rows_optional_and_round_two_needs_no_convergence(self):
        start = self.open_plan_section(rounds=2, MOCK_CODEX_PLAN_MINOR='P3|Typo in the plan')
        path = self.project / '.ai/reviews/plan-dispositions.md'
        opened = path.read_text()
        self.assertEqual(opened.count('## Plan review round'), 2)
        path.write_text(opened + self.PLAN_ROWS)
        self.assertEqual(self.plan_check(start).stdout.strip(), 'accepted=1 rejected=1 needs_human=0')
        path.write_text(opened + self.PLAN_ROWS + '| P3 | rejected | wording is already fixed in plan.md | |\n')
        self.assertEqual(self.plan_check(start).stdout.strip(), 'accepted=1 rejected=2 needs_human=0')

    def test_plan_dispositions_reject_adversarial_sections(self):
        start = self.open_plan_section()
        path = self.project / '.ai/reviews/plan-dispositions.md'
        queue = self.project / '.ai/tasks.md'
        opened, tasks_text = path.read_text(), queue.read_text()
        digest = self.plan_current()[1]
        cases = (
            ('missing row', opened + self.PLAN_ROWS.splitlines(True)[0], None, 'Finding P2 has no row'),
            ('duplicate', opened + self.PLAN_ROWS + '| P1 | rejected | the test exists already, see x | |\n',
             None, 'Finding P1 has more than one row'),
            ('unknown ID', opened + self.PLAN_ROWS + '| P7 | rejected | not a real finding at all | |\n',
             None, 'P7, which is not a finding of plan review round 1'),
            ('rejected without evidence', opened + self.PLAN_ROWS.replace('rollback is covered in docs/rollback.md:12',
                                                                       'no'),
             None, 'Rejected finding P2 needs concrete evidence'),
            ('accepted without task', opened + self.PLAN_ROWS.replace('| T002 |', '| |'), None,
             'Accepted finding P1 needs the task ID'),
            ('unknown task', opened + self.PLAN_ROWS.replace('T002', 'T009'), None,
             'Accepted finding P1 references unknown task T009'),
            ('DONE task', opened + self.PLAN_ROWS.replace('T002', 'T001'), None,
             'Accepted finding P1 must reference TODO tasks; T001 is DONE'),
            ('needs-human without question', opened + self.PLAN_ROWS.replace(
                '| rejected | rollback is covered in docs/rollback.md:12 |', '| needs-human | why? |'), None,
             'needs-human finding P2 needs the question for the human'),
            ('status changed', opened + self.PLAN_REJECTED,
             tasks_text.replace('Status: TODO', 'Status: IN_PROGRESS'), 'Task T002 changed status from TODO'),
            ('new task DONE', opened + self.PLAN_REJECTED, tasks_text + task('T003', 'DONE', 'T001'),
             'New task T003 must be TODO'),
            ('edited preamble', opened.replace('never edit', 'freely edit') + self.PLAN_ROWS, None,
             'Text above the round 1 section changed'),
            ('second header', opened + self.PLAN_ROWS + f'\n## Plan review round 1 (report {digest})\n',
             None, 'has 2 headers for plan review round 1'),
            ('renumbered header', opened.replace('## Plan review round 1 ', '## Plan review round 2 ')
             + self.PLAN_ROWS, None, 'header for plan review round 1 was changed'),
            ('no host HEAD line', opened.replace('Plan review HEAD:', 'Plan HEAD:') + self.PLAN_ROWS, None,
             'needs its host "Plan review HEAD:" line'),
        )
        for name, text, tasks_change, message in cases:
            with self.subTest(name):
                path.write_text(text)
                queue.write_text(tasks_change or tasks_text)
                self.assertIn(message, self.plan_check(start, expected=1).stderr)
        path.write_text(opened + self.PLAN_ROWS)
        queue.write_text(tasks_text + task('T003', dependencies='T001'))
        self.plan_check(start)  # a new TODO task is fine

    def test_plan_dispositions_check_only_the_current_round(self):
        start = self.open_plan_section(rounds=2)
        path = self.project / '.ai/reviews/plan-dispositions.md'
        opened = path.read_text()
        # The older section holds rows with the same IDs; they don't answer round 2.
        self.assertIn('Finding P1 has no row in the round 2 section', self.plan_check(start, expected=1).stderr)
        path.write_text(opened.replace('add the missing test', 'add the test later') + self.PLAN_ROWS)
        self.assertIn('Text above the round 2 section changed', self.plan_check(start, expected=1).stderr)
        path.write_text(opened + self.PLAN_ROWS)
        self.plan_check(start)

    def test_plan_dispositions_round_three_needs_its_own_convergence_line(self):
        start = self.open_plan_section(rounds=3)
        path = self.project / '.ai/reviews/plan-dispositions.md'
        opened = path.read_text()
        self.assertIn('Convergence: rollback', opened)  # only in the older sections
        path.write_text(opened + self.PLAN_ROWS)
        self.assertIn('Plan review round 3 needs a Convergence: line', self.plan_check(start, expected=1).stderr)
        path.write_text(opened + self.PLAN_ROWS + '<!-- Convergence: hidden -->\n')
        self.plan_check(start, expected=1)
        path.write_text(opened + self.PLAN_ROWS + '\nConvergence: redesign rollback as a whole in T002\n')
        self.assertEqual(self.plan_check(start).stdout.strip(), 'accepted=1 rejected=1 needs_human=0')

    def test_plan_dispositions_questions_are_bounded(self):
        findings = ';'.join(f'P{n}|Open question {n}' for n in range(1, 6))
        start = self.open_plan_section(findings=findings)
        path = self.project / '.ai/reviews/plan-dispositions.md'
        question = ('Should the rollback keep  option A <br> or\tswitch to B? ' * 30)[:1000]
        path.write_text(path.read_text() + ''.join(f'| P{n} | needs-human | {question} | |\n' for n in range(1, 6)))
        self.assertEqual(self.plan_check(start).stdout.strip(), 'accepted=0 rejected=0 needs_human=5')
        lines = self.plan_check(start, '--questions').stdout.splitlines()
        self.assertEqual(len(lines), 4)
        for number, line in enumerate(lines[:3], 1):
            self.assertTrue(line.startswith(f'P{number}: Should the rollback keep option A or switch to B?'), line)
            self.assertLessEqual(len(line), 300)
            self.assertNotIn('<br>', line)
        self.assertEqual(lines[3], '(+2 more in .ai/reviews/plan-dispositions.md)')

    def test_plan_dispositions_revision_scope(self):
        start = self.open_plan_section()
        records = ('.ai/project-spec.md', '.ai/current-plan.md', '.ai/tasks.md', '.ai/reviews/plan-dispositions.md',
                   '.ai/handoff.md', '.ai/state.md', '.ai/run-log.md')
        for name in records:
            file = self.project / name
            file.write_text((file.read_text() if file.exists() else '') + 'revised\n')
        self.helper('plan-revision-scope', start)
        for outside in ('src.txt', '.ai/reviews/plan.md'):
            with self.subTest(outside):
                file = self.project / outside
                original = file.read_text()
                file.write_text(original + 'agent edit\n')
                self.assertIn(f'Plan revision changed files outside workflow records: {outside}',
                              self.helper('plan-revision-scope', start, expected=1).stderr)
                file.write_text(original)
        self.helper('plan-revision-scope', start)

    def revise_ready(self, findings='P1|Gap in tests', queue=None):
        """A MAJOR plan review recorded by hand; returns HEAD (the revision's START)."""
        self.ready(queue)
        self.plan_round(findings, 1)
        return self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()

    def revise(self, *args, expected=0, **env):
        return self.tool('ai-run', '--approved', '--revise-plan', *args, expected=expected, **env)

    def revision_commits(self):
        return self.run_cmd(['git', 'log', '--format=%s']).stdout.splitlines().count('chore(ai): record plan revision')

    def revisions(self, action, expected):
        return self.helper('plan-revisions', action, expected=expected)

    def revision_args(self):
        return [json.loads(line) for line in (self.base / 'revision-args.log').read_text().splitlines()]

    def test_revise_plan_accept_commits_once_and_leaves_a_clean_checkout(self):
        start = self.revise_ready()
        self.revisions('revised', 1)
        self.revisions('decision', 1)  # fresh install: no store, nothing outstanding
        self.revise()
        section = (self.project / '.ai/reviews/plan-dispositions.md').read_text()
        self.assertTrue(section.startswith('# Plan review dispositions (Claude)'))  # host preamble, file absent at START
        self.assertIn('| P1 | accepted | the plan lacks this test | T002 |', section)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain', '--untracked-files=all']).stdout, '')
        self.assertEqual(self.revision_commits(), 1)
        self.assertEqual(self.run_cmd(['git', 'log', '--format=%s', f'{start}..HEAD']).stdout.splitlines(),
                         ['chore(ai): record plan revision', 'chore(ai): open plan dispositions'])
        committed = self.run_cmd(['git', 'show', 'HEAD', '--', '.ai/run-log.md']).stdout
        self.assertIn('plan revised (round 1): accepted 1, rejected 0, needs-human 0', committed)
        records = json.loads(next((self.base / 'host-state').rglob('plan-revisions-*.json')).read_text())
        self.assertEqual(len(records), 1)
        self.assertEqual({k: records[0][k] for k in ('round', 'accepted', 'rejected', 'needs_human', 'questions')},
                         {'round': 1, 'accepted': 1, 'rejected': 0, 'needs_human': 0, 'questions': ''})
        self.assertEqual(records[0]['commit'], self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip())
        self.revisions('revised', 0)
        self.revisions('decision', 1)
        self.assertFalse((self.project / '.ai/local/revision-context').exists())
        outcomes = [json.loads(line) for line in (self.base / 'host-state/outcomes.jsonl').read_text().splitlines()]
        self.assertEqual([(o['kind'], o['round'], o['result'], o['model']) for o in outcomes
                          if o['kind'] == 'plan_revision'], [('plan_revision', 1, 'revised', 'opus')])
        # Session boundary: read tools and Edit of the plan records only, no shell, no project allowlist.
        (call,) = self.revision_args()
        self.assertEqual(call[call.index('--tools') + 1], 'Read,Glob,Grep,Edit')
        self.assertEqual(call[call.index('--model') + 1], 'opus')
        allowed = call[call.index('--allowedTools') + 1:call.index('--setting-sources')]
        editable = {'.ai/project-spec.md', '.ai/current-plan.md', '.ai/tasks.md',
                    '.ai/reviews/plan-dispositions.md', '.ai/handoff.md'}
        for entry in allowed:
            self.assertNotIn('Bash', entry)
            self.assertNotIn('Write', entry)
            self.assertNotIn('ai-check', entry)
            self.assertNotIn('validate', entry)
            if entry.startswith('Edit'):
                self.assertRegex(entry, r'^Edit\(\./[^*]+\)$')
                self.assertIn(entry[7:-1], editable)
            else:
                self.assertIn(entry, ('Read', 'Glob', 'Grep'))
        prompt = (self.base / 'revision-prompts.log').read_text()
        self.assertIn('REVISION CONTRACT: This is plan review round 1', prompt)
        self.assertIn('ID alone in the first cell', prompt)
        self.assertIn('Do not commit; the host validates the section and commits it.', prompt)
        self.assertNotIn('Convergence:', prompt.split('REVISION CONTRACT')[1])
        # The same report again: refused, no second commit or record.
        result = self.revise(expected=1)
        self.assertIn('this plan review was already revised; review again (ai-review --plan)', result.stderr)
        self.assertEqual(self.revision_commits(), 1)
        self.assertEqual(len(self.revision_args()), 1)
        self.run_cmd(['git', 'checkout', '--', '.ai/run-log.md'])  # the refused run's stop line
        self.tool('ai-review', '--plan')  # starts: no "Commit the plan before reviewing it"
        self.revisions('revised', 1)

    def test_revise_plan_reject_only_changes_only_the_dispositions(self):
        start = self.revise_ready('P1|Gap in tests;P2|Unclear rollback')
        self.revise(MOCK_CLAUDE='revise-reject')
        changed = self.run_cmd(['git', 'diff', '--name-only', start, 'HEAD']).stdout.split()
        self.assertEqual(sorted(changed), ['.ai/reviews/plan-dispositions.md', '.ai/run-log.md', '.ai/state.md'])
        self.assertIn('plan revised (round 1): accepted 0, rejected 2, needs-human 0',
                      (self.project / '.ai/run-log.md').read_text())
        self.assertEqual(self.helper('tasks', 'count').stdout.strip(), '1')

    def test_revise_plan_needs_human_record_and_decision(self):
        self.revise_ready('P1|Rollback choice;P2|Gap in tests')
        question = ('Should the rollback keep  option A <br> or switch to B? ' * 20)[:1000]
        result = self.revise(MOCK_CLAUDE='revise-needs-human', MOCK_QUESTION=question)
        self.assertIn('Your decision is needed:', result.stdout)
        self.assertIn('accepted 0, rejected 1, needs-human 1', (self.project / '.ai/run-log.md').read_text())
        self.assertIn('Phase: blocked', (self.project / '.ai/state.md').read_text())
        lines = self.revisions('decision', 0).stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('P1: Should the rollback keep option A or switch to B?'), lines[0])
        self.assertLessEqual(len(lines[0]), 300)
        store = next((self.base / 'host-state').rglob('plan-revisions-*.json'))
        self.assertEqual(json.loads(store.read_text())[0]['questions'], lines[0])
        # Outstanding decision with forged or missing evidence fails closed.
        review = self.project / '.ai/reviews/plan.md'
        original = review.read_text()
        review.write_text(original.replace('Rollback choice', 'Nothing to decide'))
        self.assertIn('waiting for your decision', self.revisions('decision', 2).stderr)
        review.unlink()
        self.revisions('decision', 2)
        review.write_text(original)
        good = store.read_text()
        store.write_text('{not json')
        self.revisions('decision', 2)
        self.revisions('revised', 2)
        store.write_text(json.dumps([dict(json.loads(good)[0], needs_human='1')]))
        self.revisions('decision', 2)
        store.write_text(good)
        self.revisions('decision', 0)
        # The human answers, commits, and reviews again by hand: the new report clears it.
        (self.project / '.ai/current-plan.md').write_text('Rollback: option B (human decision).\n')
        self.commit('answer the plan question')
        self.tool('ai-review', '--plan', MOCK_CODEX_PLAN_FINDINGS='P1|Another gap')
        self.revisions('decision', 1)

    def test_revise_plan_forged_report_without_a_decision_takes_the_normal_path(self):
        self.revise_ready()
        review = self.project / '.ai/reviews/plan.md'
        review.write_text(review.read_text().replace('Gap in tests', 'Nothing to see'))
        self.commit('forged report')
        self.revisions('decision', 1)  # no store: the normal invalid-report path handles it
        self.revisions('revised', 1)
        self.assertIn('does not match the report ai-review published', self.revise(expected=1).stderr)
        self.run_cmd(['git', 'checkout', '--', '.ai/run-log.md'])  # the stopped run's log line
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')  # AI_SUPERVISE=0: reviews again
        self.revisions('decision', 1)

    def revise_out_of_bounds(self, message, **env):
        self.revise_ready()
        self.assertIn(message, self.revise(expected=1, **env).stderr)
        self.assertEqual(self.revision_commits(), 0)
        self.revisions('revised', 1)

    def test_revise_plan_touching_source_stops_with_nothing_counted(self):
        self.revise_out_of_bounds('Plan revision changed files outside workflow records: src.txt',
                                  MOCK_CLAUDE='revise-touch-source')

    def test_revise_plan_editing_the_plan_review_stops_with_nothing_counted(self):
        self.revise_out_of_bounds('A Claude session modified .ai/reviews/plan.md', MOCK_CLAUDE='revise-edit-plan-review')

    def test_revise_plan_touching_a_gate_file_stops_with_nothing_counted(self):
        self.revise_out_of_bounds('Approved workflow gate changed during this run',
                                  MOCK_CLAUDE='revise-touch-source', MOCK_SOURCE_PATH='.ai/validate')

    def test_revise_plan_resumes_an_uncommitted_complete_section_without_a_session(self):
        start = self.revise_ready()
        # The session wrote its rows (it never commits), then the run died before the host commit.
        self.assertIn('Claude session failed', self.revise(expected=1, MOCK_CLAUDE='revise-error').stderr)
        self.assertEqual(self.revision_commits(), 0)
        self.assertIn('.ai/reviews/plan-dispositions.md', self.run_cmd(['git', 'status', '--porcelain']).stdout)
        result = self.revise()  # no --since: START = HEAD, which already holds the section header
        self.assertIn('already complete; recording the revision', result.stdout)
        self.assertEqual(len(self.revision_args()), 1)
        self.assertEqual(self.revision_commits(), 1)
        self.revisions('revised', 0)
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain', '--untracked-files=all']).stdout, '')
        self.helper('plan-revision-scope', start)

    def test_revise_plan_preconditions_and_round_three_contract(self):
        self.revise_ready()
        self.assertIn('exclusive', self.tool('ai-run', '--approved', '--triage', '--revise-plan', expected=1).stderr)
        self.assertIn('--base only applies', self.tool('ai-run', '--approved', '--base', 'main', expected=1).stderr)
        prompt = self.project / '.ai/prompts/plan-revision.md'
        saved = prompt.read_text()
        prompt.unlink()
        self.commit('drop the prompt')
        self.assertIn('setup-project --upgrade', self.revise(expected=1).stderr)
        prompt.write_text(saved)
        self.commit('restore the prompt')
        # Rounds 1 and 2 answered, round 3 needs a Convergence line in its own section.
        self.revise(MOCK_CLAUDE='revise-reject')
        self.plan_round('P1|Gap in tests', 2)
        self.revise(MOCK_CLAUDE='revise-reject')
        self.plan_round('P1|Gap in tests', 3)
        self.assertIn('Plan review round 3 needs a Convergence: line',
                      self.revise(expected=1, MOCK_CLAUDE='revise-reject').stderr)
        self.assertIn('redesign the area as a whole', (self.base / 'revision-prompts.log').read_text().split('=== PROMPT ===')[-1])
        self.assertEqual(self.revision_commits(), 2)
        # Resume with the missing line: an uncommitted complete section is recorded without a session.
        section = self.project / '.ai/reviews/plan-dispositions.md'
        section.write_text(section.read_text() + 'Convergence: none — one gap, redesigned in T001\n')
        self.revise()
        self.assertEqual(self.revision_commits(), 3)
        self.assertEqual(len(self.revision_args()), 3)
        self.assertIn('Previous plan review rounds', (self.base / 'revision-prompts.log').read_text())

    # ---------------------------------------------------------------- planning session (DB-04)
    def plan_ready(self):
        """An installed project on a feature branch with the template queue; returns the prompt file."""
        self.setup_project()
        self.commit('bootstrap')
        self.run_cmd(['git', 'switch', '-c', 'feature/test'])
        objective = self.base / 'objective.md'
        objective.write_text('Build a tiny CLI that greets the user.\n')
        return objective

    def plan(self, *args, expected=0, **env):
        return self.tool('ai-run', '--plan', str(self.base / 'objective.md'), *args, expected=expected, **env)

    def plan_args(self):
        log = self.base / 'plan-args.log'
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def plan_prompt(self):
        return (self.base / 'plan-prompts.log').read_text().split('=== PROMPT ===')[-1]

    def assert_plan_stopped(self, result, text):
        self.assertIn(text, result.stderr)
        self.assertIn(text, (self.project / '.ai/local/last-error').read_text())
        record = self.observation()
        self.assertEqual((record['stage'], record['state']), ('planning', 'stopped'))
        self.assertIn(text, record['note'])
        self.assertEqual(self.notifications().count('⛔'), 1)

    def test_plan_session_writes_the_plan_without_committing(self):
        self.plan_ready()
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout
        result = self.plan()
        self.assertIn('Plan ready on feature/test: 2 tasks', result.stdout)
        self.assertIn('limit 3600s', result.stdout)
        args = self.plan_args()[0]
        self.assertEqual(args[args.index('--tools') + 1], 'Read,Glob,Grep,Edit,Write')
        self.assertEqual(args[args.index('--permission-mode') + 1], 'dontAsk')
        self.assertEqual(args[args.index('--model') + 1], 'opus')
        start = args.index('--allowedTools') + 1
        end = next(i for i in range(start, len(args)) if args[i].startswith('--'))
        self.assertEqual(args[start:end], self.helper('plan-allowlist').stdout.splitlines())
        self.assertFalse(any('Bash' in arg for arg in args[start:end]))
        prompt = self.plan_prompt()
        self.assertIn('OBJECTIVE (from objective.md):\nBuild a tiny CLI that greets the user.', prompt)
        self.assertIn('PLANNING CONTRACT', prompt)
        self.assertNotIn('keep DONE tasks', prompt)
        during = self.seen()[-1]
        self.assertEqual((during['stage'], during['state'], during['detail']),
                         ('planning', 'active', 'opus · first plan'))
        after = self.observation()
        self.assertEqual((after['stage'], after['state'], after['note']), ('planning', 'done', '2 tasks'))
        registry = [json.loads(p.read_text()) for p in (self.base / 'host-state/pipelines').glob('*.json')]
        self.assertIn(os.path.realpath(self.project), [os.path.realpath(e['checkout']) for e in registry])
        self.assertIn('📝 PLANNING on feature/test (opus, first plan).', self.notifications())
        self.assertIn('📝 Plan ready on feature/test: 2 tasks.', self.notifications())
        self.assertNotIn('⛔', self.notifications())
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout, head)
        changed = self.run_cmd(['git', 'status', '--porcelain', '--untracked-files=all']).stdout
        self.assertIn('.ai/tasks.md', changed)
        self.assertIn('.ai/project-spec.md', changed)
        # A revision on top of the uncommitted plan: another model and session limit.
        result = self.plan('--revision', '--model', 'sonnet', '--session-timeout', '900')
        self.assertIn('limit 900s', result.stdout)
        args = self.plan_args()[1]
        self.assertEqual(args[args.index('--model') + 1], 'sonnet')
        self.assertIn('keep DONE tasks', self.plan_prompt())
        self.assertEqual(self.seen()[-1]['detail'], 'sonnet · revision')
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout, head)

    def test_plan_session_prompt_file_paths(self):
        self.plan_ready()
        self.assertIn('Prompt file not found', self.tool('ai-run', '--plan', 'missing.md', expected=1).stderr)
        self.assertEqual(self.plan_args(), [])
        notes = self.project / 'notes'
        notes.mkdir()
        (notes / 'objective.md').write_text('Objective from a subdirectory.\n')
        self.commit('objective')
        result = subprocess.run([str(self.project / '.ai/bin/ai-run'), '--plan', 'objective.md'], cwd=notes,
                                env=self.env, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Objective from a subdirectory.', self.plan_prompt())

    def test_plan_session_invalid_queue_stops_and_keeps_the_file(self):
        self.plan_ready()
        result = self.plan(expected=1, MOCK_CLAUDE='plan-bad-queue')
        self.assert_plan_stopped(result, 'task queue is invalid')
        self.assertIn('dependency cycle', result.stderr)
        self.assertIn('Dependencies: T002', (self.project / '.ai/tasks.md').read_text())

    def test_plan_session_outside_the_plan_records_stops(self):
        self.plan_ready()
        result = self.plan(expected=1, MOCK_CLAUDE='plan-outside')
        self.assert_plan_stopped(result, 'src.txt')
        self.assertTrue((self.project / 'src.txt').exists())

    def test_plan_session_gate_change_runs_no_helper(self):
        self.plan_ready()
        result = self.plan(expected=1, MOCK_CLAUDE='plan-gate')
        self.assertIn('Approved workflow gate changed', result.stderr)
        self.assertFalse((self.base / 'UNTRUSTED_HELPER_RAN').exists())
        record = self.observation()
        self.assertEqual((record['stage'], record['state']), ('planning', 'active'))

    def test_plan_session_error_result_stops(self):
        self.plan_ready()
        self.assert_plan_stopped(self.plan(expected=1, MOCK_CLAUDE='plan-error'), 'Claude session failed')

    def test_plan_session_refusals_run_no_session(self):
        import fcntl
        self.plan_ready()
        self.assertIn('runs outside a pipeline', self.plan(expected=1, AI_PIPELINE='1').stderr)
        self.assertIn('--triage does not apply', self.plan('--triage', expected=1).stderr)
        self.assertIn('--sessions does not apply', self.plan('--sessions', '2', expected=1).stderr)
        self.assertIn('--sessions does not apply', self.plan('--sessions', '16', expected=1).stderr)
        self.assertIn('--revision only applies', self.tool('ai-run', '--revision', expected=1).stderr)
        (self.project / 'src.txt').write_text('uncommitted work\n')
        result = self.plan(expected=1)
        self.assertIn('Planning', result.stderr)
        self.assertIn('src.txt', result.stderr)
        (self.project / 'src.txt').unlink()
        (self.project / '.ai/local').mkdir(exist_ok=True)
        with (self.project / '.ai/local/workflow.lock').open('w') as file:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIn('Another runner/reviewer owns this checkout', self.plan(expected=1).stderr)
        self.assertEqual(self.plan_args(), [])

    def test_plan_session_usage_limit_pauses_then_completes(self):
        self.plan_ready()
        self.plan(MOCK_CLAUDE='limit-once', AI_SLEEP=str(self.pause_probe()))
        during = json.loads((self.base / 'during.json').read_text())
        self.assertEqual((during['state'], during['stage']), ('paused', 'planning'))
        after = self.observation()
        self.assertEqual((after['stage'], after['state'], after['note']), ('planning', 'done', '2 tasks'))

    # ---------------------------------------------------------------- plan keeps DONE tasks (T011)
    def keeps_done(self, start_queue, queue, expected=0, baseline=None):
        """Commit START_QUEUE (None: no queue at START), write QUEUE (None: removed), run the check
        (with --baseline BASELINE when given)."""
        path = self.project / '.ai/tasks.md'
        path.parent.mkdir(exist_ok=True)
        (self.project / 'README.md').write_text('fixture\n')
        if start_queue is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(start_queue)
        self.run_cmd(['git', 'add', '--all'])
        self.run_cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'start'])
        if queue is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(queue)
        extra = ('--baseline', str(baseline)) if baseline else ()
        return self.helper('plan-keeps-done', 'HEAD', *extra, expected=expected)

    def test_plan_keeps_done_passes_when_done_blocks_are_unchanged(self):
        start = '# Task queue\n\n' + task('T001', 'DONE') + task('T002') + task('T003')
        edited = task('T002').replace('Write a local', 'Write another local')
        self.keeps_done(start, '# Task queue\n\n' + task('T001', 'DONE') + edited + task('T004'))

    def test_plan_keeps_done_ignores_trailing_blank_lines_of_the_last_done_task(self):
        start = '# Task queue\n\n' + task('T001', 'DONE').rstrip('\n') + '\n'
        self.keeps_done(start, '# Task queue\n\n' + task('T001', 'DONE') + '\n\n' + task('T002'))
        self.keeps_done(start + '\n\n\n', start)

    def test_plan_keeps_done_fails_naming_the_task(self):
        start = '# Task queue\n\n' + task('T001') + task('T002', 'DONE') + task('T003', 'DONE')
        changes = {
            'removed': task('T001') + task('T003', 'DONE'),
            'set to TODO': task('T001') + task('T002') + task('T003', 'DONE'),
            'result changed': (task('T001') + task('T002', 'DONE').replace('Pending.', 'Passed.')
                               + task('T003', 'DONE').replace('Pending.', 'Passed.')),
        }
        for name, queue in changes.items():
            with self.subTest(name):
                result = self.keeps_done(start, '# Task queue\n\n' + queue, expected=1)
                self.assertIn('DONE task T002 was changed or removed', result.stderr)
        result = self.keeps_done(start, None, expected=1)
        self.assertIn('DONE task T002 was changed or removed', result.stderr)

    def test_plan_keeps_done_compares_fenced_lines(self):
        fenced = task('T001', 'DONE').replace('Pending.', 'Pending.\n```\nRan 3 tests\nOK\n```')
        start = '# Task queue\n\n' + fenced
        result = self.keeps_done(start, start.replace('Ran 3 tests', 'Ran 4 tests'), expected=1)
        self.assertIn('DONE task T001 was changed or removed', result.stderr)
        # A "## " line inside a fence belongs to the block too.
        start = '# Task queue\n\n' + fenced.replace('OK\n', 'OK\n## not a heading\n')
        self.keeps_done(start, start)
        self.keeps_done(start, start.replace('## not a heading', '## changed'), expected=1)

    def test_plan_keeps_done_passes_without_done_tasks_at_start(self):
        self.keeps_done(None, '# Task queue\n\n' + task('T001'))
        self.keeps_done('# Task queue\n\n' + task('T001') + task('T002', 'IN_PROGRESS'), None)
        self.assertIn('Malformed task heading', self.keeps_done('## T01 broken\n', None, expected=1).stderr)
        self.assertIn('Unknown commit', self.helper('plan-keeps-done', 'no-such-ref', expected=1).stderr)

    def test_plan_keeps_done_uncommitted_baseline_is_checked_too(self):
        baseline = self.base / 'baseline.md'
        start = '# Task queue\n\n' + task('T001') + task('T002', 'DONE')
        baseline.write_text('# Task queue\n\n' + task('T001', 'DONE') + task('T002', 'DONE'))
        check = lambda queue, expected=0: self.keeps_done(start, queue, expected, baseline=baseline)
        result = check('# Task queue\n\n' + task('T001') + task('T002', 'DONE'), expected=1)
        self.assertIn('DONE task T001 was changed or removed', result.stderr)
        result = check('# Task queue\n\n' + task('T001', 'DONE') + task('T002'), expected=1)
        self.assertIn('DONE task T002 was changed or removed', result.stderr)
        check('# Task queue\n\n' + task('T001', 'DONE') + task('T002', 'DONE') + task('T003'))
        # A task DONE in both must match the baseline block (the queue the session started from).
        baseline.write_text(baseline.read_text().replace('Pending.', 'Passed.'))
        check(baseline.read_text())
        # A missing baseline (no working-tree queue) keeps the START-only check.
        baseline.unlink()
        check('# Task queue\n\n' + task('T001') + task('T002', 'DONE'))
        baseline.write_text('## T01 broken\n')
        self.assertIn('Malformed task heading', check(start, expected=1).stderr)
        self.assertIn('Usage: plan-keeps-done START [--baseline FILE]',
                      self.helper('plan-keeps-done', 'HEAD', '--base', str(baseline), expected=1).stderr)

    def test_plan_keeps_done_raw_leaves_parsed_lines_unchanged(self):
        text = ('# Task queue\n\n' + task('T001', 'DONE').replace('Pending.', 'Pending.\n```\nStatus: TODO\n```')
                + '## Notes\nnot a task\n')
        code = (f'import json, sys; sys.path.insert(0, {str(ROOT / "scripts/lib")!r}); import workflow; '
                'print(json.dumps(workflow.task_blocks(sys.stdin.read())))')
        result = subprocess.run(['python3', '-c', code], input=text, capture_output=True, text=True, check=True)
        [block] = json.loads(result.stdout)
        self.assertEqual(block['lines'], task('T001', 'DONE').splitlines()[1:])
        self.assertEqual(block['raw'], text.split('\n## Notes')[0].splitlines()[3:] + [''])
        self.assertIn('Status: TODO', block['raw'])
        self.assertNotIn('Status: TODO', block['lines'])

    def done_queue_ready(self):
        self.plan_ready()
        (self.project / '.ai/tasks.md').write_text('# Task queue\n\n' + task('T001', 'DONE') + task('T002'))
        self.commit('plan with a DONE task')

    def test_plan_session_revision_malformed_start_queue_runs_no_session(self):
        self.plan_ready()
        (self.project / '.ai/tasks.md').write_text('# Task queue\n\n## T01 broken heading\n')
        self.commit('broken queue')
        result = self.plan('--revision', expected=1)
        self.assertIn('Malformed task heading', result.stderr)
        self.assertEqual(self.plan_args(), [])

    def test_plan_session_revision_dropping_a_done_task_stops(self):
        self.done_queue_ready()
        result = self.plan('--revision', expected=1, MOCK_CLAUDE='plan-revision-drops-done')
        self.assert_plan_stopped(result, 'DONE task T001 was changed or removed')
        queue = (self.project / '.ai/tasks.md').read_text()
        self.assertNotIn('Status: DONE', queue)
        self.assertIn('## T003', queue)

    def test_plan_session_revision_flag_missing_still_refuses_the_drop(self):
        self.done_queue_ready()
        result = self.plan(expected=1, MOCK_CLAUDE='plan-revision-drops-done')
        self.assert_plan_stopped(result, 'DONE task T001 was changed or removed')

    def test_plan_session_revision_keeping_done_tasks_completes(self):
        self.done_queue_ready()
        result = self.plan('--revision', MOCK_CLAUDE='plan-revision-ok')
        self.assertIn('Plan ready on feature/test: 3 tasks', result.stdout)
        self.assertIn('the host stops the run when a DONE task was changed or removed', self.plan_prompt())
        after = self.observation()
        self.assertEqual((after['stage'], after['state'], after['note']), ('planning', 'done', '3 tasks'))
        self.assertNotIn('⛔', self.notifications())

    def uncommitted_done_ready(self):
        """Committed HEAD has TODO T001; the working tree has it DONE (uncommitted) at entry."""
        self.plan_ready()
        (self.project / '.ai/tasks.md').write_text('# Task queue\n\n' + task('T001') + task('T002'))
        self.commit('plan without DONE tasks')
        (self.project / '.ai/tasks.md').write_text('# Task queue\n\n' + task('T001', 'DONE') + task('T002'))
        tmp = self.base / 'tmp'
        tmp.mkdir()
        return tmp

    def uncommitted_done_stops(self, mode, written, *flags):
        """WRITTEN: text the session left in T001's block (None: T001 removed)."""
        tmp = self.uncommitted_done_ready()
        result = self.plan(*flags, expected=1, MOCK_CLAUDE=mode, TMPDIR=str(tmp))
        self.assert_plan_stopped(result, 'Planning: DONE task T001 was changed or removed')
        queue = (self.project / '.ai/tasks.md').read_text()
        self.assertIn('## T003', queue)  # left as the session wrote it
        if written is None:
            self.assertNotIn('## T001', queue)
        else:
            self.assertIn(written, queue.split('## T002')[0])
        self.assertEqual(list(tmp.iterdir()), [])  # the host baseline is removed

    def test_plan_keeps_done_uncommitted_status_flip_stops(self):
        self.uncommitted_done_stops('plan-revision-drops-done', 'Status: TODO')

    def test_plan_keeps_done_uncommitted_status_flip_stops_with_revision(self):
        self.uncommitted_done_stops('plan-revision-drops-done', 'Status: TODO', '--revision')

    def test_plan_keeps_done_uncommitted_removal_stops(self):
        self.uncommitted_done_stops('plan-revision-removes-done', None)

    def test_plan_keeps_done_uncommitted_removal_stops_with_revision(self):
        self.uncommitted_done_stops('plan-revision-removes-done', None, '--revision')

    def test_plan_keeps_done_uncommitted_result_edit_stops(self):
        self.uncommitted_done_stops('plan-revision-edits-done', 'Passed.')

    def test_plan_keeps_done_uncommitted_result_edit_stops_with_revision(self):
        self.uncommitted_done_stops('plan-revision-edits-done', 'Passed.', '--revision')

    def uncommitted_done_kept(self, *flags):
        tmp = self.uncommitted_done_ready()
        result = self.plan(*flags, MOCK_CLAUDE='plan-revision-ok', TMPDIR=str(tmp))
        self.assertIn('Plan ready on feature/test: 3 tasks', result.stdout)
        after = self.observation()
        self.assertEqual((after['stage'], after['state'], after['note']), ('planning', 'done', '3 tasks'))
        self.assertIn(task('T001', 'DONE').rstrip('\n'), (self.project / '.ai/tasks.md').read_text())
        self.assertEqual(list(tmp.iterdir()), [])

    def test_plan_keeps_done_uncommitted_kept_identical_completes(self):
        self.uncommitted_done_kept()

    def test_plan_keeps_done_uncommitted_kept_identical_completes_with_revision(self):
        self.uncommitted_done_kept('--revision')

    def test_plan_dispositions_pending_accepts_only_the_host_header(self):
        self.revise_ready()
        pending = lambda expected: self.helper('start-plan-dispositions', 'main', '--pending', expected=expected)
        pending(1)  # no file yet
        self.helper('start-plan-dispositions', 'main')
        pending(0)  # exactly the host's uncommitted header (a crash before its commit)
        path = self.project / '.ai/reviews/plan-dispositions.md'
        path.write_text(path.read_text() + '| P1 | rejected | the plan covers it in current-plan.md:12 | |\n')
        self.assertIn('is not just the uncommitted host section header', pending(1).stderr)
        self.commit('rows')
        pending(1)  # committed: nothing pending

    # ---------------------------------------------------------------- plan revision stage (T005)
    def plan_stage_ready(self, findings='P1|Gap in tests', recoverable=False):
        """A MAJOR plan review, an approved run and an open plan-revision stage; returns START."""
        start = self.revise_ready(findings)
        self.start_recoverable_run() if recoverable else self.start_run('feature/test')
        self.helper('run-manifest', 'stage-set', 'plan-revision', start)
        return start

    def stage_verify(self, expected=0):
        return self.helper('stage-verify', expected=expected)

    def commit_leftovers(self, message):
        if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip():
            self.commit(message)

    def start_recoverable_run(self):
        """An approved run whose captured settings allow auto-recovery (the fixture default is off)."""
        gate = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.run_cmd(['python3', str(HELPER), 'run-manifest', 'start', gate, 'feature/test', '--approved',
                      '--base', 'main', '--no-pr'], env=dict(self.env, AI_AUTO_RECOVER='1'))

    def test_plan_revision_stage_set_and_verify(self):
        start = self.plan_stage_ready()
        digest = self.plan_current()[1]
        self.assertEqual(self.open_stage(), f'plan-revision {start} {digest}')
        self.assertEqual(self.stage_verify().stdout.strip(), 'pending')
        # An agent commit with the revision subject is not a host record.
        self.run_cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'chore(ai): record plan revision'])
        self.assertEqual(self.stage_verify().stdout.strip(), 'pending')
        self.run_cmd(['git', 'reset', '-q', '--hard', start])
        # Out-of-scope leftovers and a forged report fail closed.
        (self.project / 'src.txt').write_text('agent edit\n')
        self.assertIn('Plan revision stage: Plan revision changed files outside workflow records: src.txt',
                      self.stage_verify(expected=1).stderr)
        self.run_cmd(['git', 'checkout', '--', 'src.txt'])
        review = self.project / '.ai/reviews/plan.md'
        original = review.read_text()
        review.write_text(original.replace('Gap in tests', 'Nothing to see'))
        self.assertIn('Plan revision stage: the plan review does not match', self.stage_verify(expected=1).stderr)
        self.assertIn('Plan revision stage: the plan review does not match',
                      self.helper('run-manifest', 'stage-set', 'plan-revision', start, expected=1).stderr)
        review.write_text(original)
        # The host revision record closes it; a dirty tree after the record commit fails.
        self.revise('--since', start)
        self.assertEqual(self.stage_verify().stdout.strip(), 'committed')
        handoff = self.project / '.ai/handoff.md'
        handoff.write_text(handoff.read_text() + 'late edit\n')
        self.assertIn('Plan revision stage: uncommitted changes after the counted revision commit.',
                      self.stage_verify(expected=1).stderr)
        self.run_cmd(['git', 'checkout', '--', '.ai/handoff.md'])
        # A foreign report: the stage stays bound to the one it started on.
        self.plan_round('P1|Another gap', 2)
        self.assertIn('Plan revision stage: the current plan review is not the one this revision started on.',
                      self.stage_verify(expected=1).stderr)
        # A stage record without its report digest is invalid.
        stage_file = next((self.base / 'host-state').rglob('stage-*.json'))
        stage_file.write_text(json.dumps({'branch': 'feature/test',
                                          'stage': {'name': 'plan-revision', 'start_head': start}}))
        self.assertIn('Plan revision stage: the stage record is invalid.',
                      self.helper('run-manifest', 'stage', expected=1).stderr)

    def test_plan_revision_stage_reservation_per_run(self):
        self.ready()
        self.start_run('feature/test')
        first, second = 'a' * 64, 'b' * 64
        reserve = lambda digest, limit, expected=0: self.helper('run-manifest', 'revision-reserve', digest, limit,
                                                                expected=expected)
        self.assertEqual(self.helper('run-manifest', 'revision-count').stdout.strip(), '0')
        self.assertEqual(reserve(first, '1').stdout.strip(), '1')
        self.assertEqual(reserve(first, '1').stdout.strip(), '1')  # idempotent, also at the limit
        self.assertIn('plan review: supervision limit reached (1 revisions this run)',
                      reserve(second, '1', expected=1).stderr)
        self.assertEqual(reserve(second, '2').stdout.strip(), '2')
        self.assertIn('Usage: run-manifest revision-reserve', reserve('xyz', '2', expected=1).stderr)
        self.assertIn('Usage: run-manifest revision-reserve', reserve(first, '10', expected=1).stderr)
        # A recovery (attempt reserved, no start) keeps the list; a human (re)start resets it.
        self.helper('run-manifest', 'reserve-attempt')
        self.assertEqual(self.helper('run-manifest', 'revision-count').stdout.strip(), '2')
        self.start_run('feature/test')
        self.assertEqual(self.helper('run-manifest', 'revision-count').stdout.strip(), '0')
        manifest = next((self.base / 'host-state').rglob('run.json'))
        manifest.write_text(json.dumps(dict(json.loads(manifest.read_text()), plan_revisions=['short'])))
        self.assertIn('reservations are unreadable', self.helper('run-manifest', 'revision-count', expected=1).stderr)

    def test_plan_revision_stage_committed_record_only_clears_the_stage(self):
        start = self.plan_stage_ready()
        self.revise('--since', start)  # the pipeline's revision child recorded it, then the pipeline died
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                           MOCK_CODEX_PLAN='major')
        self.assertIn('Completing the interrupted plan revision', result.stdout)
        self.assertNotIn('already revised', result.stderr)
        self.assertEqual(len(self.revision_args()), 1)
        self.assertEqual(self.revision_commits(), 1)
        self.assertEqual(self.open_stage(), '')
        self.assertEqual(self.helper('run-manifest', 'revision-count').stdout.strip(), '0')  # nothing reserved

    def test_plan_revision_stage_pending_runs_the_round_model(self):
        self.plan_stage_ready()
        # --model is the implementation model; the revision gets opus below the escalation round.
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--model', 'sonnet', expected=1,
                  MOCK_CODEX_PLAN='major', AI_SUPERVISE_ESCALATE_ROUND='2', AI_SUPERVISE_ESCALATE_MODEL='claude-test-x')
        (call,) = self.revision_args()
        self.assertEqual(call[call.index('--model') + 1], 'opus')
        self.assertEqual(self.revision_commits(), 1)
        self.assertEqual(self.open_stage(), '')
        self.assertIn('plan review found', (self.project / '.ai/local/last-error').read_text())  # re-reviewed
        # Round 2 (the re-review) reaches the escalation round.
        self.commit_leftovers('record the stop')
        self.assertEqual(self.plan_current()[0], '2')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('run-manifest', 'stage-set', 'plan-revision', head)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, MOCK_CLAUDE='revise-reject',
                  MOCK_CODEX_PLAN='major', AI_SUPERVISE_ESCALATE_ROUND='2', AI_SUPERVISE_ESCALATE_MODEL='claude-test-x')
        call = self.revision_args()[-1]
        self.assertEqual(call[call.index('--model') + 1], 'claude-test-x')
        self.assertEqual(self.revision_commits(), 2)

    def test_plan_revision_stage_limit_stops_before_the_session(self):
        self.plan_stage_ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1',
                  AI_SUPERVISE_PLAN_ROUNDS='0')
        self.assertIn('plan review: supervision limit reached (0 revisions this run)',
                      (self.project / '.ai/local/last-error').read_text())
        self.assertFalse((self.base / 'revision-args.log').exists())
        self.assertEqual(self.recovery_calls(), [])
        self.assertIn('this kind of stop always needs a human', self.notifications())
        self.assertTrue(self.open_stage().startswith('plan-revision '))

    def test_plan_revision_stage_recovery_reasons_always_escalate(self):
        self.ready()
        self.start_recoverable_run()
        (self.project / '.ai/local').mkdir(exist_ok=True)
        for reason in ('Plan revision stage cannot be completed safely: the plan revision was not recorded.',
                       'plan review: supervision limit reached (3 revisions this run); BLOCKER 0, MAJOR 1 remain',
                       'plan review needs your decision (round 2): P1: keep A or B?'):
            with self.subTest(reason):
                (self.project / '.ai/local/last-error').write_text(reason + '\n')
                self.tool('ai-recover', '--stage', 'plan review', expected=1, AI_AUTO_RECOVER='1')
                self.assertIn(f'stopped during plan review: {reason}', self.notifications())
                self.assertEqual(self.recovery_calls(), [])
        self.assertIn('this kind of stop always needs a human', self.notifications())

    def test_plan_revision_stage_source_leftovers_escalate_without_a_commit(self):
        self.plan_stage_ready(recoverable=True)
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        (self.project / 'src.txt').write_text('agent edit\n')
        self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', expected=1, AI_AUTO_RECOVER='1')
        notes = self.notifications()
        self.assertIn('the interrupted plan revision left changes outside its scope', notes)
        self.assertEqual(self.recovery_calls(), [])
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip(), head)
        self.assertIn(' M src.txt', self.run_cmd(['git', 'status', '--porcelain']).stdout)

    def test_plan_revision_stage_stored_decision_escalates_before_any_resume(self):
        start = self.plan_stage_ready('P1|Rollback choice;P2|Gap in tests', recoverable=True)
        self.revise('--since', start, MOCK_CLAUDE='revise-needs-human', MOCK_QUESTION='Keep option A or B?')
        # A crash after the record, before stage-clear; the recovery allowance is already used up.
        for _ in range(3):
            self.helper('run-manifest', 'reserve-attempt')
        (self.project / '.ai/local/last-error').unlink(missing_ok=True)
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', expected=1, AI_AUTO_RECOVER='1')
        notes = self.notifications()
        self.assertIn('plan review needs your decision: P1: Keep option A or B?', notes)
        self.assertIn('a plan revision recorded questions only you can answer', notes)
        self.assertNotIn('already tried', notes)
        self.assertNotIn('Resuming the pipeline', notes)
        self.assertEqual(self.recovery_calls(), [])
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip(), head)
        self.assertIn('needs your decision', (self.project / '.ai/local/last-error').read_text())
        # The recorded stage is closed (no resume): the human's answer gets a new plan review.
        self.assertEqual(self.open_stage(), '')
        # An unreadable store escalates too, still without a session.
        next((self.base / 'host-state').rglob('plan-revisions-*.json')).write_text('{not json')
        self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn('the plan revision records are unreadable', self.notifications())
        self.assertEqual(self.recovery_calls(), [])

    # ---------------------------------------------------------------- supervised plan review loop (T006)
    def supervised(self, *args, expected=0, **env):
        return self.tool('ai-pipeline', '--approved', '--base', 'main', *args, expected=expected,
                         **dict({'AI_SUPERVISE': '1'}, **env))

    def plan_calls(self):
        calls = self.base / 'codex-plan-calls'
        return calls.read_text().count('call') if calls.exists() else 0

    def plan_statuses(self):
        return (self.base / 'codex-plan-status').read_text().splitlines()

    def implementation_calls(self):
        calls = self.project / '.ai/local/mock-invocations'
        return calls.read_text().count('call') if calls.exists() else 0

    def subjects_oldest_first(self):
        return self.run_cmd(['git', 'log', '--reverse', '--format=%s']).stdout.splitlines()

    def test_supervised_plan_major_once_revises_reviews_again_and_opens_the_pr(self):
        self.ready()
        self.add_origin()
        result = self.supervised(MOCK_CODEX_PLAN='major-once')
        self.assertIn('Pull request: https://github.com/example/project/pull/7', result.stdout)
        self.assertEqual(self.plan_calls(), 2)
        self.assertEqual(self.plan_statuses(), ['clean', 'clean'])  # the re-review starts on a clean checkout
        self.assertEqual(self.revision_commits(), 1)
        self.assertIn('🔁 Plan revised (round 1/3): accepted 1, rejected 0', self.notifications())
        revision = self.run_cmd(['git', 'log', '-1', '--format=%H', '--grep', '^chore(ai): record plan revision']).stdout.strip()
        self.assertIn('plan revised (round 1): accepted 1, rejected 0, needs-human 0',
                      self.run_cmd(['git', 'show', revision, '--', '.ai/run-log.md']).stdout)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')  # the accepted task ran
        self.helper('tasks', 'complete')
        self.assertTrue(any(c[:2] == ['pr', 'create'] for c in self.gh_calls()))
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '2')
        self.assertEqual(self.open_stage(), '')

    def test_supervised_plan_reject_only_reviews_again_on_a_clean_checkout(self):
        self.ready()
        self.supervised('--no-pr', MOCK_CODEX_PLAN='major-once', MOCK_CLAUDE='revise-reject')
        self.assertEqual(self.plan_calls(), 2)
        self.assertEqual(self.plan_statuses(), ['clean', 'clean'])
        subjects = self.subjects_oldest_first()
        # Both plan reviews (and the revision between them) before any implementation commit.
        self.assertEqual([s for s in subjects if s.startswith(('chore(ai): record plan', 'implement'))][:4],
                         ['chore(ai): record plan review', 'chore(ai): record plan revision',
                          'chore(ai): record plan review', 'implement T001'], subjects)
        self.assertIn('🔁 Plan revised (round 1/3): accepted 0, rejected 1', self.notifications())
        first, second = [p for p in self.prompts() if 'PLAN SCOPE' in p]
        self.assertNotIn('PLAN REVISION CONTEXT:', first)
        context = second.split('PLAN REVISION CONTEXT:')[1]
        self.assertIn('This is plan review round 2', context)
        self.assertIn('dispositions of round 1: .ai/reviews/plan-dispositions.md', context)
        self.assertIn('## Previous plan review rounds', context)
        self.assertIn('rejected', context)
        self.assertNotIn('PREVIOUS ROUNDS:', second)  # never implementation-review rounds

    def test_supervised_plan_needs_human_stops_with_the_bounded_question(self):
        self.ready()
        question = ('Should the rollback keep  option A <br> or switch to B? ' * 20)[:1000]
        self.supervised('--no-pr', expected=1, MOCK_CODEX_PLAN='major',
                        MOCK_CODEX_PLAN_FINDINGS='P1|Rollback choice;P2|Gap in tests',
                        MOCK_CLAUDE='revise-needs-human', MOCK_QUESTION=question)
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertEqual(len(error.splitlines()), 1)
        self.assertTrue(error.startswith('Pipeline stopped during plan review: plan review needs your decision '
                                         '(round 1): P1: Should the rollback keep option A or switch to B?'), error)
        self.assertLessEqual(len(error), 400)  # the stored question is capped at 300 characters
        self.assertIn('stopped during plan review: plan review needs your decision (round 1)', self.notifications())
        self.assertEqual(self.plan_calls(), 1)  # no re-review of a report waiting for the human
        self.assertEqual(self.implementation_calls(), 0)
        self.assertNotIn('🔁 Plan revised', self.notifications())
        # A human rerun with auto-recovery on stops again at the stored decision, no session at all.
        self.commit_leftovers('record the stop')
        self.supervised('--no-pr', expected=1, AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major')
        self.assertIn('needs your decision', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.plan_calls(), 1)
        self.assertEqual(len(self.revision_args()), 1)
        self.assertEqual(self.implementation_calls(), 0)
        self.assertEqual(self.recovery_calls(), [])

    # ---------------------------------------------------------------- needs-human decision gate (T011)
    def decision_recorded(self, queue=None):
        """A supervised run whose plan revision asked the human, stopped and committed."""
        self.ready(queue)
        self.supervised('--no-pr', expected=1, MOCK_CODEX_PLAN='major',
                        MOCK_CODEX_PLAN_FINDINGS='P1|Rollback choice;P2|Gap in tests',
                        MOCK_CLAUDE='revise-needs-human', MOCK_QUESTION='Keep option A or switch to B?')
        self.commit_leftovers('record the stop')
        (self.project / '.ai/local/last-error').unlink()
        return self.plan_calls(), len(self.revision_args())

    def assert_decision_stop(self, plan_calls, sessions, recovery):
        error = (self.project / '.ai/local/last-error').read_text()
        if recovery:  # ai-recover escalates the pipeline's stop with its own wording
            self.assertIn('plan review needs your decision: P1: Keep option A or switch to B?', error)
        else:
            self.assertEqual(error, 'Pipeline stopped during plan review: plan review needs your decision '
                                    '(round 1): P1: Keep option A or switch to B?\n')
        self.assertEqual(self.plan_calls(), plan_calls)
        self.assertEqual(len(self.revision_args()), sessions)
        self.assertEqual(self.implementation_calls(), 0)
        self.assertEqual(self.recovery_calls(), [])

    def test_needs_human_decision_gate_holds_with_skip_plan_review(self):
        calls = self.decision_recorded()
        self.supervised('--no-pr', '--skip-plan-review', expected=1, AI_AUTO_RECOVER='0', MOCK_CODEX_PLAN='major')
        self.assert_decision_stop(*calls, recovery=False)
        (self.project / '.ai/local/last-error').unlink()
        self.supervised('--no-pr', '--skip-plan-review', expected=1, AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major')
        self.assert_decision_stop(*calls, recovery=True)

    def test_needs_human_decision_gate_holds_with_tasks_partly_done(self):
        calls = self.decision_recorded(task('T001') + task('T002'))
        tasks = self.project / '.ai/tasks.md'
        tasks.write_text(tasks.read_text().replace('Status: TODO', 'Status: DONE', 1))
        self.commit('T001 done by hand')
        self.helper('tasks', 'untouched', expected=1)
        self.supervised('--no-pr', expected=1, AI_AUTO_RECOVER='0', MOCK_CODEX_PLAN='major')
        self.assert_decision_stop(*calls, recovery=False)
        (self.project / '.ai/local/last-error').unlink()
        self.supervised('--no-pr', expected=1, AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major')
        self.assert_decision_stop(*calls, recovery=True)

    def test_needs_human_decision_gate_unreadable_store_fails_closed_with_skip(self):
        calls = self.decision_recorded()
        next((self.base / 'host-state').rglob('plan-revisions-*.json')).write_text('{not json')
        self.supervised('--no-pr', '--skip-plan-review', expected=1, AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major')
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('Plan revision stage cannot be completed safely: the plan revision records are unreadable', error)
        self.assertEqual(self.plan_calls(), calls[0])
        self.assertEqual(len(self.revision_args()), calls[1])
        self.assertEqual(self.implementation_calls(), 0)
        self.assertEqual(self.recovery_calls(), [])

    def test_needs_human_decision_gate_absent_skip_plan_review_implements(self):
        self.ready()
        self.supervised('--no-pr', '--skip-plan-review', MOCK_CODEX_PLAN='major')
        self.assertEqual(self.plan_calls(), 0)
        self.assertGreater(self.implementation_calls(), 0)
        self.helper('tasks', 'complete')

    def test_supervised_plan_limit_stops_without_recovery(self):
        self.ready()
        self.supervised('--no-pr', expected=1, AI_AUTO_RECOVER='1', AI_SUPERVISE_PLAN_ROUNDS='1',
                        MOCK_CODEX_PLAN='major', MOCK_CLAUDE='revise-reject')
        self.assertEqual((self.project / '.ai/local/last-error').read_text().strip(),
                         'plan review: supervision limit reached (1 revisions this run); BLOCKER 0, MAJOR 1 remain')
        self.assertEqual(self.revision_commits(), 1)
        self.assertEqual(self.plan_calls(), 2)
        self.assertEqual(self.implementation_calls(), 0)
        self.assertEqual(self.recovery_calls(), [])
        self.assertIn('this kind of stop always needs a human', self.notifications())

    def test_supervised_plan_off_keeps_todays_stop(self):
        self.ready()
        self.supervised('--no-pr', expected=1, AI_SUPERVISE='0', AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major')
        self.assertIn('plan review found BLOCKER 0, MAJOR 1', (self.project / '.ai/local/last-error').read_text())
        self.assertFalse((self.base / 'revision-args.log').exists())
        self.assertEqual(self.recovery_calls(), [])

    def test_supervised_plan_revision_touching_source_stops_without_recovery(self):
        self.ready()
        self.supervised('--no-pr', expected=1, AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major',
                        MOCK_CLAUDE='revise-touch-source')
        self.assertIn('Plan revision changed files outside workflow records: src.txt',
                      (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.revision_commits(), 0)
        self.assertEqual(self.plan_calls(), 1)
        self.assertEqual(self.implementation_calls(), 0)
        self.assertEqual(self.recovery_calls(), [])

    def test_supervised_plan_escalation_model_and_round_three_convergence(self):
        self.ready()
        self.supervised('--no-pr', '--model', 'sonnet', expected=1, MOCK_CODEX_PLAN='major',
                        MOCK_CLAUDE='revise-reject', AI_SUPERVISE_ESCALATE_MODEL='claude-test-x')
        models = [call[call.index('--model') + 1] for call in self.revision_args()]
        self.assertEqual(models, ['opus', 'opus', 'claude-test-x'])
        self.assertIn('Plan review round 3 needs a Convergence: line', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.revision_commits(), 2)
        self.assertEqual(self.plan_calls(), 3)
        self.assertEqual(self.implementation_calls(), 0)
        self.assertTrue(self.open_stage().startswith('plan-revision '))

    # ---------------------------------------------------------------- host queue repair (FL-24)
    def queue_ids(self, text):
        return re.findall(r'^## (T\d+)', text, re.M)

    def test_queue_repair_revision_prerequisite_is_reordered_and_runs(self):
        self.ready()
        result = self.supervised('--no-pr', MOCK_CODEX_PLAN='major-once', MOCK_CLAUDE='revise-accept-prereq')
        self.assertIn('Task queue reordered (dependencies first): T002 T001', result.stdout)
        self.assertEqual(len(self.revision_args()), 1)
        self.assertEqual(self.recovery_calls(), [])
        self.assertNotIn('⛔', self.notifications())
        revision = self.run_cmd(['git', 'log', '-1', '--format=%H', '--grep', '^chore(ai): record plan revision']).stdout.strip()
        committed = self.run_cmd(['git', 'show', f'{revision}:.ai/tasks.md']).stdout
        self.assertEqual(self.queue_ids(committed), ['T002', 'T001'])
        self.assertIn('Dependencies: T002', committed)
        self.helper('tasks', 'complete')

    def test_queue_repair_revision_cycle_escalates_without_rerun(self):
        self.ready()
        self.supervised('--no-pr', expected=1, AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major-once',
                        MOCK_CLAUDE='revise-accept-cycle')
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('Plan revision stage: task queue is invalid', error)
        self.assertIn('dependency cycle', error)
        self.assertEqual(self.notifications().count('⛔'), 1)
        self.assertEqual(self.recovery_calls(), [])
        self.assertEqual(len(self.revision_args()), 1)
        self.assertEqual(self.implementation_calls(), 0)
        self.assertEqual(self.revision_commits(), 0)

    def test_queue_repair_planning_session_reorders_without_committing(self):
        self.plan_ready()
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout
        result = self.plan(MOCK_CLAUDE='plan-out-of-order')
        self.assertIn('Task queue reordered (dependencies first): T002 T001', result.stdout)
        self.assertEqual(self.queue_ids((self.project / '.ai/tasks.md').read_text()), ['T002', 'T001'])
        after = self.observation()
        self.assertEqual((after['stage'], after['state']), ('planning', 'done'))
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout, head)
        self.assertIn('rejects cycles, unknown IDs and prose', self.plan_prompt())

    def test_queue_repair_planning_preamble_section_reorders(self):
        self.plan_ready()
        result = self.plan(MOCK_CLAUDE='plan-preamble-section')
        self.assertIn('Task queue reordered (dependencies first): T002 T001', result.stdout)
        queue = (self.project / '.ai/tasks.md').read_text()
        self.assertTrue(queue.startswith('# Task queue\n\n## Context\nKeep this intro.\n\n## T002 — '))
        self.assertEqual(self.queue_ids(queue), ['T002', 'T001'])
        after = self.observation()
        self.assertEqual((after['stage'], after['state']), ('planning', 'done'))

    def test_queue_repair_planning_cycle_stops_and_keeps_the_file(self):
        self.plan_ready()
        result = self.plan(expected=1, MOCK_CLAUDE='plan-bad-queue')
        self.assert_plan_stopped(result, 'Planning: task queue is invalid')
        self.assertIn('dependency cycle', result.stderr)
        queue = (self.project / '.ai/tasks.md').read_text()
        self.assertEqual(self.queue_ids(queue), ['T001', 'T002'])
        self.assertIn('Dependencies: T002', queue)

    def test_queue_repair_planning_revision_keeps_done_tasks(self):
        self.done_queue_ready()
        done = task('T001', 'DONE').rstrip('\n')
        result = self.plan('--revision', MOCK_CLAUDE='plan-revision-prereq')
        self.assertIn('Task queue reordered (dependencies first): T001 T003 T002', result.stdout)
        queue = (self.project / '.ai/tasks.md').read_text()
        self.assertEqual(self.queue_ids(queue), ['T001', 'T003', 'T002'])
        self.assertIn(done, queue)
        self.helper('tasks', 'check')

    def test_queue_repair_committed_out_of_order_queue_still_stops_the_pipeline(self):
        self.ready(self.invalid_queue())
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertIn('Task queue is invalid:', (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.queue_ids((self.project / '.ai/tasks.md').read_text()), ['T001', 'T002'])

    def test_queue_repair_revision_prompt_places_new_tasks_first(self):
        start = self.revise_ready()
        self.revise('--since', start)
        prompt = (self.base / 'revision-prompts.log').read_text()
        self.assertIn('placed before the first task that depends on them', prompt)
        self.assertIn('placed before the first task that depends on them',
                      (ROOT / 'templates/.ai/prompts/plan-revision.md').read_text().replace('\n  ', ' '))

    # ---------------------------------------------------------------- interrupted revision queue (FL-24)
    def queue_recovery_crash(self, mode):
        """A revision session wrote an out-of-order queue, then the machine died before the host's checks."""
        self.ready()
        self.crash_supervised(MOCK_REVISION_CRASH='after', MOCK_CLAUDE=mode)
        self.assertEqual(self.revision_commits(), 0)
        self.assertEqual(self.queue_ids((self.project / '.ai/tasks.md').read_text()), ['T001', 'T002'])

    def assert_queue_recovered(self, result):
        self.assertIn('Task queue reordered (dependencies first): T002 T001', result.stdout)
        self.assert_resumed_once()
        revision = self.run_cmd(['git', 'log', '-1', '--format=%H', '--grep', '^chore(ai): record plan revision']).stdout.strip()
        self.assertEqual(self.queue_ids(self.run_cmd(['git', 'show', f'{revision}:.ai/tasks.md']).stdout), ['T002', 'T001'])
        self.assertEqual(self.recovery_calls(), [])

    def test_queue_recovery_session_crash_human_rerun(self):
        self.queue_recovery_crash('revise-accept-prereq')
        self.assert_queue_recovered(self.resume('human', MOCK_CLAUDE='revise-accept-prereq'))

    def test_queue_recovery_session_crash_watchdog(self):
        self.queue_recovery_crash('revise-accept-prereq')
        self.assert_queue_recovered(self.resume('watchdog', MOCK_CLAUDE='revise-accept-prereq'))

    def test_queue_recovery_cycle_escalates_without_a_second_session(self):
        self.queue_recovery_crash('revise-accept-cycle')
        self.resume('watchdog', expected=1, MOCK_CLAUDE='revise-accept-cycle')
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('Plan revision stage: task queue is invalid', error)
        self.assertIn('dependency cycle', error)
        self.assertEqual(self.notifications().count('⛔'), 1)
        self.assertEqual(len(self.revision_args()), 1)
        self.assertEqual(self.revision_commits(), 0)
        self.assertFalse((self.base / 'recover-calls').exists())

    def out_of_order(self, *extra):
        """The working-tree queue an interrupted revision left: T001 now depends on the appended T002."""
        queue = self.project / '.ai/tasks.md'
        text = queue.read_text().replace('Dependencies: none', 'Dependencies: T002', 1)
        queue.write_text(text.rstrip('\n') + '\n\n' + ''.join(extra or (task('T002'),)))
        return queue.read_text()

    def assert_repair_noop(self, queue):
        result = self.helper('revision-queue-repair')
        self.assertEqual(result.stdout, '')
        self.assertEqual((self.project / '.ai/tasks.md').read_text(), queue)

    def test_queue_recovery_helper_repairs_an_interrupted_revision(self):
        self.revise_ready()
        self.out_of_order()
        result = self.helper('revision-queue-repair')
        self.assertIn('Task queue reordered (dependencies first): T002 T001', result.stdout)
        self.assertEqual(self.queue_ids((self.project / '.ai/tasks.md').read_text()), ['T002', 'T001'])
        self.helper('tasks', 'check')
        self.assert_repair_noop((self.project / '.ai/tasks.md').read_text())  # nothing left to move

    def test_queue_recovery_helper_cycle_fails_with_the_reorder_message(self):
        self.revise_ready()
        queue = self.out_of_order(task('T002', dependencies='T001'))
        self.assertIn('dependency cycle', self.helper('revision-queue-repair', expected=1).stderr)
        self.assertEqual((self.project / '.ai/tasks.md').read_text(), queue)

    def test_queue_recovery_helper_leaves_a_committed_queue(self):
        self.revise_ready()
        queue = self.out_of_order()
        self.commit('out-of-order queue')
        self.assert_repair_noop(queue)

    def test_queue_recovery_helper_ignores_a_dirty_file_outside_the_records(self):
        self.revise_ready()
        queue = self.out_of_order()
        (self.project / 'src.txt').write_text('not a plan record\n')
        self.assert_repair_noop(queue)

    def test_queue_recovery_helper_ignores_a_done_task_at_head(self):
        self.revise_ready(queue=task('T001', 'DONE') + task('T002'))
        queue = task('T001', 'DONE') + task('T002', dependencies='T003') + task('T003')
        (self.project / '.ai/tasks.md').write_text(queue)
        self.assert_repair_noop(queue)

    def test_queue_recovery_helper_ignores_an_already_revised_review(self):
        start = self.revise_ready()
        self.revise('--since', start)
        self.assertEqual(self.revision_commits(), 1)
        self.assert_repair_noop(self.out_of_order(task('T003')))

    def test_queue_recovery_revise_plan_with_a_done_task_still_stops(self):
        start = self.revise_ready(queue=task('T001', 'DONE') + task('T002'))
        self.assertIn('a task is already DONE', self.revise('--since', start, expected=1).stderr)

    # ---------------------------------------------------------------- supervised plan resume (T007)
    def test_supervised_plan_resume_crash_kill_stays_inside_the_fixture(self):
        # A fake host ai-run/ai-pipeline whose child calls crash_kill in the fixture: outside the
        # fixture (the real runner of a session running these tests) it survives; inside it dies.
        code = 'import os, pathlib\n' + CRASH_KILL + 'crash_kill(os.getppid(), os.getppid())\n'
        for name in ('ai-run', 'ai-pipeline'):
            fake = self.base / 'host-bin' / name
            fake.parent.mkdir(exist_ok=True)
            fake.write_text('#!/usr/bin/env bash\nenv -C "$1" python3 -c "$2"\necho survived\n')
            fake.chmod(0o755)
            for cwd, killed in ((self.base, False), (self.project, True)):
                result = subprocess.run([str(fake), str(self.project), code], cwd=cwd,
                                        capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
                self.assertEqual(result.returncode == -9, killed, (name, cwd, result.stdout + result.stderr))
                self.assertEqual('survived' in result.stdout, not killed)

    def crash_hook(self, hook, subject):
        path = self.project / '.git/hooks' / hook
        path.write_text('#!/usr/bin/env python3\nimport os, pathlib, subprocess, sys\n'
                        f'HOOK, SUBJECT = {hook!r}, {subject!r}\n' + CRASH_HOOK)
        path.chmod(0o755)

    def crash_supervised(self, **env):
        """A supervised run (auto-recovery approved) that a crash kills: no stop, no recovery."""
        crashed = self.supervised('--no-pr', expected=None, AI_AUTO_RECOVER='1',
                                  **dict({'MOCK_CODEX_PLAN': 'major-once'}, **env))
        self.assertEqual(crashed.returncode, -9, crashed.stdout + crashed.stderr)
        self.assertTrue((self.project / '.ai/local/pipeline.active').exists())  # what ai-watchdog finds

    def hook_crash(self, hook, subject):
        self.ready()
        self.crash_hook(hook, subject)
        self.crash_supervised()

    def start_supervised_run(self, **env):
        gate = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.run_cmd(['python3', str(HELPER), 'run-manifest', 'start', gate, 'feature/test', '--approved',
                      '--base', 'main', '--no-pr'], env=dict(self.env, AI_AUTO_RECOVER='1', AI_SUPERVISE='1', **env))

    def revision_written(self, clear=False, findings='P1|Gap in tests', **env):
        """Host-write window: the pipeline reserved, opened the stage and its ai-run child recorded
        the revision; the crash came before stage-clear (or, with clear, right after it)."""
        start = self.revise_ready(findings)
        self.start_supervised_run()
        self.helper('run-manifest', 'revision-reserve', self.plan_current()[1], '3')
        self.helper('run-manifest', 'stage-set', 'plan-revision', start)
        self.revise('--since', start, '--base', 'main', **env)
        if clear:
            self.helper('run-manifest', 'stage-clear')

    def resume(self, path, expected=0, **env):
        env = dict({'MOCK_CODEX_PLAN': 'major-once'}, **env)
        if path == 'human':
            return self.supervised('--no-pr', expected=expected, **env)
        # What ai-watchdog --recover starts after a crash: the approved run's settings, kept manifest.
        return self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', expected=expected, **env)

    def revision_records(self):
        return json.loads(next((self.base / 'host-state').rglob('plan-revisions-*.json')).read_text())

    def assert_resumed_once(self, counted='1'):
        """One record and one session for the report, one re-review on a clean checkout, then the tasks."""
        self.assertEqual(len(self.revision_records()), 1)
        self.assertEqual(self.helper('run-manifest', 'revision-count').stdout.strip(), counted)
        self.assertEqual(len(self.revision_args()), 1)  # no second revision session
        self.assertEqual(self.plan_calls(), 2)
        self.assertEqual(self.plan_statuses()[-1], 'clean')
        self.assertEqual(self.helper('plan-rounds', 'count', 'main').stdout.strip(), '2')
        self.helper('tasks', 'complete')
        self.assertEqual(self.open_stage(), '')

    # Crash point 1: the session's edits, the host's preamble commit and its revision commit.
    def session_crash(self):
        self.ready()
        self.crash_supervised(MOCK_REVISION_CRASH='after')
        self.assertEqual(self.revision_commits(), 0)
        self.assertIn('.ai/reviews/plan-dispositions.md', self.run_cmd(['git', 'status', '--porcelain']).stdout)

    def test_supervised_plan_resume_session_crash_human_rerun(self):
        self.session_crash()
        self.resume('human')
        self.assert_resumed_once()
        self.assertIn('🔁 Plan revised (round 1/3): accepted 1, rejected 0', self.notifications())

    def test_supervised_plan_resume_session_crash_watchdog(self):
        self.session_crash()
        self.resume('watchdog')
        self.assert_resumed_once()
        self.assertEqual(self.recovery_calls(), [])  # the stage rules decide, no Claude decision

    def open_crash(self, hook):
        self.hook_crash(hook, 'chore(ai): open plan dispositions')
        self.assertFalse((self.base / 'revision-args.log').exists())  # died before the session

    def test_supervised_plan_resume_before_the_preamble_commit_human_rerun(self):
        self.open_crash('commit-msg')
        self.assertIn('.ai/reviews/plan-dispositions.md', self.run_cmd(['git', 'status', '--porcelain']).stdout)
        self.resume('human')
        self.assert_resumed_once()

    def test_supervised_plan_resume_before_the_preamble_commit_watchdog(self):
        self.open_crash('commit-msg')
        self.resume('watchdog')
        self.assert_resumed_once()

    def test_supervised_plan_resume_after_the_preamble_commit_human_rerun(self):
        self.open_crash('post-commit')
        self.resume('human')
        self.assert_resumed_once()

    def test_supervised_plan_resume_after_the_preamble_commit_watchdog(self):
        self.open_crash('post-commit')
        self.resume('watchdog')
        self.assert_resumed_once()

    def test_supervised_plan_resume_before_the_revision_commit_human_rerun(self):
        self.hook_crash('commit-msg', 'chore(ai): record plan revision')
        self.assertEqual(self.revision_commits(), 0)
        self.resume('human')
        self.assert_resumed_once()

    def test_supervised_plan_resume_before_the_revision_commit_watchdog(self):
        self.hook_crash('commit-msg', 'chore(ai): record plan revision')
        self.resume('watchdog')
        self.assert_resumed_once()

    # Crash point 2: after the host revision commit, before its record (the resume records the
    # revision with a second host commit; only the record counts).
    def test_supervised_plan_resume_after_the_revision_commit_human_rerun(self):
        self.hook_crash('post-commit', 'chore(ai): record plan revision')
        self.assertEqual(self.revision_commits(), 1)
        self.revisions('revised', 1)
        self.resume('human')
        self.assert_resumed_once()

    def test_supervised_plan_resume_after_the_revision_commit_watchdog(self):
        self.hook_crash('post-commit', 'chore(ai): record plan revision')
        self.resume('watchdog')
        self.assert_resumed_once()

    # After the record, before stage-clear: a human restart closes it without counting it in
    # its fresh allowance; a recovery resume keeps the reservation.
    def test_supervised_plan_resume_after_the_record_human_rerun(self):
        self.revision_written()
        self.resume('human')
        self.assert_resumed_once(counted='0')
        self.assertIn('🔁 Plan revised (in the previous run): accepted 1, rejected 0', self.notifications())

    def test_supervised_plan_resume_after_the_record_watchdog(self):
        self.revision_written()
        self.resume('watchdog')
        self.assert_resumed_once()
        self.assertIn('🔁 Plan revised (round 1/3): accepted 1, rejected 0', self.notifications())

    def test_supervised_plan_resume_after_stage_clear_human_rerun(self):
        self.revision_written(clear=True)
        self.resume('human')
        self.assert_resumed_once(counted='0')

    def test_supervised_plan_resume_after_stage_clear_watchdog(self):
        self.revision_written(clear=True)
        self.resume('watchdog')
        self.assert_resumed_once()

    # Crash point 3: host-write windows.
    def reserved_without_stage(self):
        self.revise_ready()
        self.start_supervised_run(AI_SUPERVISE_PLAN_ROUNDS='1')
        self.helper('run-manifest', 'revision-reserve', self.plan_current()[1], '1')

    def test_supervised_plan_resume_reserved_without_a_stage_human_rerun(self):
        self.reserved_without_stage()
        self.resume('human', AI_SUPERVISE_PLAN_ROUNDS='1')
        self.assert_resumed_once()

    def test_supervised_plan_resume_reserved_without_a_stage_watchdog(self):
        self.reserved_without_stage()
        self.resume('watchdog')  # a non-idempotent limit check would stop here (limit 1, 1 reserved)
        self.assert_resumed_once()

    def stage_without_reservation(self):
        start = self.revise_ready()
        self.start_supervised_run()
        self.helper('run-manifest', 'stage-set', 'plan-revision', start)

    def test_supervised_plan_resume_stage_without_a_reservation_human_rerun(self):
        self.stage_without_reservation()
        self.resume('human')
        self.assert_resumed_once()

    def test_supervised_plan_resume_stage_without_a_reservation_watchdog(self):
        self.stage_without_reservation()
        self.resume('watchdog')
        self.assert_resumed_once()

    def rounds_crash(self):
        # The pipeline's host commit of the first plan review, then the crash before its record.
        self.hook_crash('post-commit', 'chore(ai): record plan review')
        self.assertEqual(self.plan_calls(), 1)
        self.assertEqual(json.loads(self.plan_store().read_text()), [])  # store initialised, no record

    def test_supervised_plan_resume_plan_review_without_its_round_record_human_rerun(self):
        self.rounds_crash()
        self.resume('human')
        self.assert_resumed_once()

    def test_supervised_plan_resume_plan_review_without_its_round_record_watchdog(self):
        self.rounds_crash()
        self.resume('watchdog')
        self.assert_resumed_once()

    # Crash point 4: the third revision session dies; its resume runs on the escalation model.
    def test_supervised_plan_resume_round_three_crash_runs_on_the_escalation_model(self):
        self.ready()
        always = dict(MOCK_CODEX_PLAN='major', MOCK_CLAUDE='revise-reject')
        self.crash_supervised(MOCK_REVISION_CRASH='before', MOCK_REVISION_CRASH_CALL='3',
                              AI_SUPERVISE_ESCALATE_MODEL='claude-test-x', **always)
        self.assertEqual(self.revision_commits(), 2)
        self.resume('watchdog', expected=1, MOCK_CONVERGENCE='Convergence: none — one gap, rejected each round', **always)
        self.assertEqual([call[call.index('--model') + 1] for call in self.revision_args()],
                         ['opus', 'opus', 'claude-test-x', 'claude-test-x'])
        self.assertEqual(self.helper('run-manifest', 'revision-count').stdout.strip(), '3')
        self.assertEqual([r['round'] for r in self.revision_records()], [1, 2, 3])
        section = (self.project / '.ai/reviews/plan-dispositions.md').read_text().split('## Plan review round 3 ')[1]
        self.assertIn('\nConvergence: none — one gap, rejected each round\n', section)
        self.assertIn('supervision limit reached (3 revisions this run)', (self.project / '.ai/local/last-error').read_text())

    def test_supervised_plan_resume_keeps_the_approved_settings_after_a_config_change(self):
        self.ready()
        (self.config / 'ai-toolkit').mkdir(parents=True, exist_ok=True)
        config = self.config / 'ai-toolkit/config'
        config.write_text('AI_SUPERVISE_PLAN_ROUNDS=2\nAI_SUPERVISE_ESCALATE_ROUND=1\n'
                          'AI_SUPERVISE_ESCALATE_MODEL=claude-approved\n')
        always = dict(MOCK_CODEX_PLAN='major', MOCK_CLAUDE='revise-reject')
        self.crash_supervised(MOCK_REVISION_CRASH='before', **always)
        config.write_text('AI_SUPERVISE_PLAN_ROUNDS=1\nAI_SUPERVISE_ESCALATE_ROUND=9\n'
                          'AI_SUPERVISE_ESCALATE_MODEL=claude-changed\n')
        self.resume('watchdog', expected=1, **always)
        # The approved limit 2 (not 1) and the approved escalation from round 1 (not 9).
        self.assertEqual([call[call.index('--model') + 1] for call in self.revision_args()], ['claude-approved'] * 3)
        self.assertEqual(self.revision_commits(), 2)
        self.assertEqual(self.plan_calls(), 3)
        self.assertIn('supervision limit reached (2 revisions this run)', (self.project / '.ai/local/last-error').read_text())

    # Crash point 5: a recorded needs-human decision survives the crash.
    def assert_decision_survives(self, path, clear):
        self.revision_written(clear=clear, findings='P1|Rollback choice;P2|Gap in tests',
                              MOCK_CLAUDE='revise-needs-human', MOCK_QUESTION='Keep option A or switch to B?')
        plan_calls, sessions = self.plan_calls(), len(self.revision_args())
        if path == 'human':
            self.supervised('--no-pr', expected=1, AI_AUTO_RECOVER='1', MOCK_CODEX_PLAN='major')
        else:
            self.resume(path, expected=1, MOCK_CODEX_PLAN='major')
        error = (self.project / '.ai/local/last-error').read_text()
        self.assertIn('needs your decision', error)
        self.assertIn('P1: Keep option A or switch to B?', error)
        self.assertIn('P1: Keep option A or switch to B?', self.notifications())
        self.assertEqual(self.plan_calls(), plan_calls)
        self.assertEqual(len(self.revision_args()), sessions)
        self.assertEqual(self.implementation_calls(), 0)
        self.assertEqual(self.recovery_calls(), [])
        # The human answers, commits and reviews again by hand (approved); the rerun implements.
        self.commit_leftovers('record the stop')
        (self.project / '.ai/current-plan.md').write_text('Rollback: option B (human decision).\n')
        self.commit('answer the plan question')
        self.tool('ai-review', '--plan')
        self.supervised('--no-pr')
        self.helper('tasks', 'complete')
        self.assertGreater(self.implementation_calls(), 0)

    def test_supervised_plan_resume_decision_after_stage_clear_human_rerun(self):
        self.assert_decision_survives('human', clear=True)

    def test_supervised_plan_resume_decision_after_stage_clear_watchdog(self):
        self.assert_decision_survives('watchdog', clear=True)

    def test_supervised_plan_resume_decision_after_the_record_human_rerun(self):
        self.assert_decision_survives('human', clear=False)

    def test_supervised_plan_resume_decision_after_the_record_watchdog(self):
        self.assert_decision_survives('watchdog', clear=False)

    def test_supervised_plan_resume_human_restart_after_the_limit_reviews_first(self):
        self.ready()
        limit = dict(AI_SUPERVISE_PLAN_ROUNDS='1', MOCK_CODEX_PLAN='major', MOCK_CLAUDE='revise-reject',
                     MOCK_CONVERGENCE='Convergence: none — one gap, rejected each round')
        self.supervised('--no-pr', expected=1, **limit)
        self.assertIn('supervision limit reached (1 revisions this run)', (self.project / '.ai/local/last-error').read_text())
        self.commit_leftovers('record the stop')
        # A restart revised the second report, then died right after closing its stage.
        self.revise(MOCK_CLAUDE='revise-reject')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.supervised('--no-pr', expected=1, **limit)
        # A fresh allowance, but the recorded revision is not redone: it reviews first.
        subjects = self.run_cmd(['git', 'log', '--reverse', '--format=%s', f'{head}..HEAD']).stdout.splitlines()
        self.assertEqual([s for s in subjects if s.startswith('chore(ai): ')],
                         ['chore(ai): record plan review', 'chore(ai): open plan dispositions',
                          'chore(ai): record plan revision', 'chore(ai): record plan review'])
        self.assertEqual(self.plan_calls(), 4)
        self.assertEqual(len(self.revision_args()), 3)
        self.assertEqual(self.helper('run-manifest', 'revision-count').stdout.strip(), '1')
        self.assertIn('supervision limit reached (1 revisions this run)', (self.project / '.ai/local/last-error').read_text())

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

    def scan_decision(self, result):
        log = self.base / 'decision.json'
        log.write_text(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': result}))
        return self.helper('recover-decision', str(log), '0').stdout.rstrip('\n')

    def assert_scan_escalates(self, cases):
        for result in cases:
            with self.subTest(result=result):
                reason = ' '.join(f'the recovery session gave no valid decision; it wrote: {result}'.split())[:300]
                self.assertEqual(self.scan_decision(result), f'escalate\t{reason}\tinspect the stop yourself')

    def assert_prose_excerpt(self, result):
        action, reason, human = self.scan_decision(result).split('\t')
        self.assertEqual((action, human), ('escalate', 'inspect the stop yourself'))
        self.assertTrue(reason.startswith('the recovery session gave no valid decision; it wrote: '), reason)
        self.assertLessEqual(len(reason), 300)
        return reason

    def test_recovery_decision_prose_only_escalates_with_an_excerpt(self):
        reason = self.assert_prose_excerpt('The gate\ttimed out   twice.\n\nI cannot tell why. ' + 'x' * 400)
        # Cut at the word boundary before the unbroken 400-character word, never mid-word.
        self.assertTrue(reason.endswith('it wrote: The gate timed out twice. I cannot tell why.…'), reason)
        self.assertLessEqual(len(reason), 300)
        # Nothing written: the reason stays as before.
        self.assertEqual(self.scan_decision('  \n '),
                         'escalate\tthe recovery session gave no valid decision\tinspect the stop yourself')

    def test_recovery_reason_shorten_unit_cases(self):
        wf = self.outcome_module()
        sentences = ' '.join(f'Sentence {n} ends here.' for n in range(1, 40))
        cut = wf.shorten(sentences, 300)
        self.assertTrue(cut.endswith('.…'), cut)
        self.assertLessEqual(len(cut), 300)
        words = ' '.join(['word'] * 100)
        cut = wf.shorten(words, 300)
        self.assertTrue(cut.endswith('word…'), cut)
        self.assertLessEqual(len(cut), 300)
        self.assertEqual(wf.shorten('x' * 400, 300), 'x' * 299 + '…')
        self.assertEqual(wf.shorten('a  short\ttext', 300), 'a short text')

    def recovery_reason_decision(self, reason, human_action='look yourself'):
        log = self.base / 'decision.json'
        result = json.dumps({'action': 'escalate', 'reason': reason, 'human_action': human_action})
        log.write_text(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': result}))
        return self.helper('recover-decision', str(log), '0').stdout.rstrip('\n').split('\t')

    def test_recovery_reason_shorten_keeps_the_full_text_in_a_sidecar(self):
        sidecar = self.project / '.ai/local/recovery-decision.txt'
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        full = ' '.join(f'Reason sentence {n} is here.' for n in range(1, 30))
        self.assertGreater(len(full), 500)
        action, reason, human = self.recovery_reason_decision(full)
        self.assertEqual((action, human), ('escalate', 'look yourself'))
        self.assertTrue(reason.endswith('.…'), reason)
        self.assertLessEqual(len(reason), 300)
        self.assertEqual(sidecar.read_text(), f'reason: {full}\nhuman_action: look yourself\n')
        self.assertEqual(self.recovery_reason_decision('short reason'), ['escalate', 'short reason', 'look yourself'])
        self.assertFalse(sidecar.exists())  # a short decision removes the stale file

    def test_recovery_reason_shorten_prose_only_excerpt_stays_bounded(self):
        reason = self.assert_prose_excerpt('word ' * 200)
        self.assertTrue(reason.endswith('word…'), reason)
        self.assertFalse((self.project / '.ai/local/recovery-decision.txt').exists())

    def test_recovery_reason_shorten_notification_points_at_the_full_text(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate-long')
        note = [line for line in self.notifications().splitlines() if '⛔' in line][-1]
        self.assertTrue(note.endswith('Full text: .ai/local/recovery-decision.txt'), note)
        self.assertIn('explains the stop.…', note)
        self.assertTrue((self.project / '.ai/local/recovery-decision.txt').is_file())
        # P4: an early escalation of a later invocation never points at the previous text.
        before = len(self.notifications().splitlines())
        (self.project / '.ai/local/last-error').write_text('Approved workflow gate changed during this run.')
        self.tool('ai-recover', '--stage', 'implementation', expected=1, AI_AUTO_RECOVER='1')
        later = [line for line in self.notifications().splitlines()[before:] if '⛔' in line]
        self.assertEqual(len(later), 1)
        self.assertNotIn('Full text:', later[0])
        self.assertFalse((self.project / '.ai/local/recovery-decision.txt').exists())

    def test_recovery_reason_shorten_plan_questions_end_at_a_word(self):
        wf = self.outcome_module()
        question = ' '.join(['rollback'] * 60)
        line = wf.bounded_questions([question]).splitlines()[0]
        self.assertTrue(line.endswith('rollback…'), line)
        self.assertLessEqual(len(line), 300)

    def test_recovery_decision_prose_with_brackets_escalates_with_an_excerpt(self):
        candidate = '{"action":"commit_and_rerun","reason":"example"}'
        reason = self.assert_prose_excerpt(f'Diagnostic: ["]",\n{candidate}\n]')
        self.assertIn('it wrote: Diagnostic: ["]", {"action":"commit_and_rerun"', reason)
        reason = self.assert_prose_excerpt('Diagnosis.\n{"action": "delete_branch", "reason": "a"}')
        self.assertIn('it wrote: Diagnosis. {"action": "delete_branch"', reason)

    def test_recovery_decision_prose_rerun_resumes_the_pipeline(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', AI_AUTO_RECOVER='1',
                  MOCK_CLAUDE='error-once', MOCK_RECOVER='prose-rerun')
        notes = self.notifications()
        self.assertEqual(len(self.recovery_calls()), 1)
        self.assertIn('🔧 Recovered (1/2)', notes)
        self.assertIn('🏁 FINISHED', notes)
        self.assertNotIn('⛔', notes)

    def test_recovery_decision_prose_only_notification_quotes_the_session(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='prose-only')
        notes = self.notifications()
        self.assertIn('the recovery session gave no valid decision; it wrote: The session crashed once; '
                      'I could not decide what to do.', notes)
        self.assertEqual(notes.count('⛔'), 1)

    def test_recovery_decision_scan_accepts_one_line_start_object_in_bracket_free_prose(self):
        decision = '{"action": "escalate", "reason": "x", "human_action": "y"}'
        self.assertEqual(self.scan_decision(f'The run stopped because the gate timed out.\nIt looks real.\n{decision}'),
                         'escalate\tx\ty')
        self.assertEqual(self.scan_decision(f'Diagnosis first.\n{decision}\nThat is my verdict.\nThanks.'),
                         'escalate\tx\ty')
        self.assertEqual(self.scan_decision(f'Diagnosis first.\n```json\n{decision}\n```'), 'escalate\tx\ty')
        self.assertEqual(self.scan_decision(f'Diagnosis first.\n```json\n{decision}\n```\nMore prose.'),
                         'escalate\tx\ty')
        self.assertEqual(self.scan_decision('Diagnosis.\n  {\n    "action": "rerun",\n    "reason": "crash"\n}\n'),
                         'rerun\tcrash\t')
        self.assertEqual(self.scan_decision('Diagnosis.\n{"action": "rerun", "reason": "saw [1] and {x} ]["}'),
                         'rerun\tsaw [1] and {x} ][\t')

    def test_recovery_decision_scan_nested_action_only_outer_counts(self):
        self.assertEqual(self.scan_decision('Diagnosis.\n{"action": "rerun", "reason": "x", '
                                            '"n": {"action": "commit_and_rerun", "reason": "y"}}'),
                         'rerun\tx\t')

    def test_recovery_decision_scan_escalates_enclosing_containers(self):
        candidate = '{"action":"commit_and_rerun","reason":"example"}'
        self.assert_scan_escalates([
            # plan review round 2 (P3): a bracket inside a JSON string in the prose
            f'Diagnostic: ["]",\n{candidate}\n]',
            f'Diagnostic: ["{{",\n{candidate}\n]',
            f'Diagnostic: ["}}",\n{candidate}\n]',
            f'Diagnosis.\n{candidate}\n]',
            f'Diagnosis.\n{candidate}\n}}',
            f'See [the log].\n{candidate}',
            # round 1
            'Broken diagnostic: {"details":{"action":"commit_and_rerun", "reason":"example"}, BROKEN}',
            'Broken diagnostic:\n{"details":{"action":"commit_and_rerun", "reason":"example"}, BROKEN}',
            'Diagnostic: [{"action":"rerun","reason":"example"}]',
            f'Diagnostic: [\n{candidate}\n]',
            'An example: "{\\"action\\": \\"rerun\\", \\"reason\\": \\"x\\"}"',
            'I would answer `{"action": "rerun", "reason": "x"}` here.',
            f'The template is {{"action": "...", "reason": "..."}}.\n{candidate}',
        ])

    def test_recovery_decision_scan_escalates_invalid_or_ambiguous_candidates(self):
        self.assert_scan_escalates([
            'Diagnosis.\n{"action": "rerun", "reason": "a"}\n{"action": "rerun", "reason": "b"}',
            'Diagnosis.\n{"action": "rerun", "reason": "a"}\n{"action": "escalate", "reason": "b"}',
            'Diagnosis.\n{"action": "rerun", "action": "escalate", "reason": "a"}',
            'Diagnosis.\n{"action": "rerun"}',
            'Diagnosis.\n{"action": "rerun", "reason": "a"} that is it',
            'Diagnosis.\n{"verdict": "rerun", "reason": "a"}',
            'Diagnosis.\n{"action": "delete_branch", "reason": "a"}',
            'Prose only, no decision at all.',
        ])

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
        out = recover.communicate(timeout=MEDIUM_TIMEOUT)[0].decode()
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

    def held_and_hidden(self, command, **env):
        """Start COMMAND with a session held in MOCK_CLAUDE=hold; once it holds, the host dashboard
        (real /proc, this fixture's base) lists nothing, though a reader blind to the marker would.
        Returns (runner, session pid); the caller releases or kills them."""
        local = self.project / '.ai/local'
        for name in ('mock-session.pid', 'mock-release'):
            (local / name).unlink(missing_ok=True)
        runner = subprocess.Popen(command, cwd=self.project, env=dict(self.env, MOCK_CLAUDE='hold', **env),
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + PIPELINE_TIMEOUT
            while not ((local / 'mock-session.pid').exists() and (local / 'mock-session.pid').read_text()):
                if runner.poll() is not None or time.monotonic() > deadline:
                    self.fail('the session never started')
                time.sleep(0.05)
            session = int((local / 'mock-session.pid').read_text())
            self.assertIn(b'AI_DASHBOARD_IGNORE=1', Path(f'/proc/{session}/environ').read_bytes().split(b'\0'))
            spec = importlib.util.spec_from_file_location('dashboard_view', ROOT / 'scripts/lib/dashboard.py')
            dashboard = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(dashboard)

            class Blind(dashboard.ProcSource):
                def environ(self, pid):
                    return None

            with mock.patch.dict(os.environ, {'AI_DASHBOARD_ROOT': str(self.base), 'AI_DASHBOARD_PROC': '/proc',
                                              'AI_STATE_DIR': str(self.base / 'dashboard-state')}):
                self.assertEqual(dashboard.snapshot()['runs'], [])
                self.assertIn(os.path.realpath(self.project),
                              [run['checkout'] for run in dashboard.snapshot(source=Blind())['runs']])
            return runner, session
        except BaseException:
            os.killpg(runner.pid, signal.SIGKILL)
            runner.communicate()
            raise

    def test_dashboard_ignore_fixture_pipeline_is_hidden(self):
        self.ready()
        runner, _ = self.held_and_hidden([str(self.project / '.ai/bin/ai-pipeline'), '--approved', '--base', 'main',
                                          '--no-pr'], AI_AUTO_RECOVER='1', MOCK_RECOVER='escalate')
        (self.project / '.ai/local/mock-release').touch()
        output = runner.communicate(timeout=PIPELINE_TIMEOUT)[0].decode(errors='replace')
        self.assertEqual(runner.returncode, 1, output)
        # The same for the pipeline ai-recover resumes in its own process (what the watchdog starts).
        runner, session = self.held_and_hidden([str(self.project / '.ai/bin/ai-recover'), '--stage', 'implementation'],
                                               MOCK_RECOVER='rerun')
        os.killpg(runner.pid, signal.SIGKILL)
        os.kill(session, signal.SIGKILL)  # GNU timeout runs the session in its own process group
        runner.communicate()

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

    def test_supervise_settings_invalid_values_stop_before_any_agent(self):
        self.ready()
        for key, value in (('AI_SUPERVISE', '2'), ('AI_SUPERVISE_PLAN_ROUNDS', '10'),
                           ('AI_SUPERVISE_ESCALATE_ROUND', '0'), ('AI_SUPERVISE_ESCALATE_MODEL', 'bad model!')):
            with self.subTest(key=key):
                result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr',
                                   expected=1, **{key: value})
                self.assertIn(f'Invalid {key}: {value}', result.stderr)
                self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
                for name in ('codex-calls', 'codex-plan-calls'):
                    self.assertFalse((self.base / name).exists())

    def test_supervise_settings_invalid_supervise_stops_hand_run_tools(self):
        self.ready()
        result = self.tool('ai-review', '--plan', expected=1, AI_SUPERVISE='yes')
        self.assertIn('Invalid AI_SUPERVISE: yes', result.stderr)
        result = self.tool('ai-run', '--approved', expected=1, AI_SUPERVISE='yes')
        self.assertIn('Invalid AI_SUPERVISE: yes', result.stderr)
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        for name in ('codex-calls', 'codex-plan-calls'):
            self.assertFalse((self.base / name).exists())

    def test_supervise_settings_are_captured_and_survive_a_config_change(self):
        self.ready()
        (self.config / 'ai-toolkit').mkdir(parents=True, exist_ok=True)
        (self.config / 'ai-toolkit/config').write_text(
            'AI_SUPERVISE_PLAN_ROUNDS=5\nAI_SUPERVISE_ESCALATE_MODEL=model-one\n')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        manifest_file = next((self.base / 'host-state').rglob('run.json'))
        env = json.loads(manifest_file.read_text())['env']
        self.assertEqual(env['AI_SUPERVISE_PLAN_ROUNDS'], '5')
        self.assertEqual(env['AI_SUPERVISE_ESCALATE_MODEL'], 'model-one')
        self.assertEqual(env['AI_SUPERVISE'], '0')
        self.assertEqual(env['AI_SUPERVISE_ESCALATE_ROUND'], '3')
        (self.config / 'ai-toolkit/config').write_text(
            'AI_SUPERVISE_PLAN_ROUNDS=7\nAI_SUPERVISE_ESCALATE_MODEL=model-two\n')
        self.tool('ai-recover', '--stage', 'implementation', MOCK_RECOVER='rerun',
                  AI_SUPERVISE_PLAN_ROUNDS='9')
        env = json.loads(manifest_file.read_text())['env']
        self.assertEqual(env['AI_SUPERVISE_PLAN_ROUNDS'], '5')
        self.assertEqual(env['AI_SUPERVISE_ESCALATE_MODEL'], 'model-one')

    def test_supervise_settings_key_lists_are_identical(self):
        root = Path(__file__).resolve().parent.parent / 'scripts'
        key = r'AI_[A-Z_]+'
        common = (root / 'lib/common.sh').read_text()
        config = re.search(r'case "\$key" in ((?:%s\|)*%s)\) ;;' % (key, key), common)
        recover = (root / 'ai-recover').read_text()
        unset = re.search(r'^unset ((?:%s ?)+)$' % key, recover, re.M)
        case = re.search(r'^\s+((?:%s\|)*%s)\)$' % (key, key), recover, re.M)
        py = re.search(r'RUN_SETTINGS = \(([^)]*)\)', (root / 'lib/workflow.py').read_text())
        self.assertTrue(config and unset and case and py)
        lists = {
            'ai_config': set(config.group(1).split('|')),
            'unset': set(unset.group(1).split()),
            'case': set(case.group(1).split('|')),
            'RUN_SETTINGS': set(re.findall(r"'(AI_[A-Z_]+)'", py.group(1))),
        }
        for name, keys in lists.items():
            self.assertEqual(keys, lists['RUN_SETTINGS'], name)
        self.assertIn('AI_SUPERVISE_ESCALATE_MODEL', lists['RUN_SETTINGS'])

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

    # ---------------------------------------------------------------- limit relaunch (MC-01)
    LIMIT_MESSAGE = 'Claude usage limit: the reset is beyond the 60s wait budget. Rerun after it resets.'

    def limit_far_stop(self, prepare=None):
        self.ready()
        if prepare:
            prepare()
        result = self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='limit-far', AI_LIMIT_MAX_WAIT='60')
        self.assertIn(self.LIMIT_MESSAGE, result.stderr)
        self.assertEqual((self.project / '.ai/local/last-error').read_text(), self.LIMIT_MESSAGE + '\n')
        self.assertFalse((self.base / 'sleep.log').exists())
        return result

    def limit_stop(self, *args, expected=0, **env):
        result = self.run_cmd(['python3', str(HELPER), 'limit-stop', *args], expected=expected,
                              env=dict(self.env, **env))
        if expected:
            self.assertEqual(result.stdout, '')
        return result.stdout.strip()

    def test_limit_relaunch_record_beyond_budget_stop(self):
        self.limit_far_stop()
        record = (self.project / '.ai/local/limit-stop')
        self.assertFalse(record.is_symlink())
        agent, reset = record.read_text().split()
        self.assertEqual(agent, 'Claude')
        self.assertLess(abs(int(reset) - (time.time() + 7 * 86400)), 300)
        self.assertEqual(self.limit_stop(), f'Claude {int(reset) + 60}')

    def test_limit_relaunch_record_planted_temp_symlink_is_not_followed(self):
        sentinel = self.base / 'sentinel'
        sentinel.write_text('keep me\n')

        def plant():
            # Planted by the session (ai-run's startup path check refuses it earlier).
            claude = self.mock_bin / 'claude'
            claude.rename(self.mock_bin / 'claude-real')
            claude.write_text(f'#!/usr/bin/env bash\nln -s {shlex.quote(str(sentinel))} .ai/local/limit-stop.tmp\n'
                              f'exec {shlex.quote(str(self.mock_bin / "claude-real"))} "$@"\n')
            os.chmod(claude, 0o755)
        self.limit_far_stop(plant)
        self.assertTrue((self.project / '.ai/local/limit-stop.tmp').is_symlink())
        self.assertEqual(sentinel.read_text(), 'keep me\n')
        self.assertRegex((self.project / '.ai/local/limit-stop').read_text(), r'^Claude \d+\n$')

    def test_limit_relaunch_record_limit_stop_rejects_anything_else(self):
        self.setup_project()
        local = self.project / '.ai/local'
        local.mkdir(exist_ok=True)

        def records(error=self.LIMIT_MESSAGE + '\n', stop='Claude 0\n'):
            for name in ('last-error', 'limit-stop'):
                (local / name).unlink(missing_ok=True)
            if stop is not None:
                (local / 'limit-stop').write_text(stop)
            (local / 'last-error').write_text(error)

        records()
        self.assertEqual(self.limit_stop('--now', '1000', AI_LIMIT_RETRY='600'), 'Claude 1600')
        records(stop='Claude 900\n')
        self.assertEqual(self.limit_stop('--now', '1000'), 'Claude 1000')  # the reset has passed
        records(stop='Claude 5000\n')
        self.assertEqual(self.limit_stop('--now', '1000'), 'Claude 5060')
        for error, stop in ((self.LIMIT_MESSAGE + '\nsomething else\n', 'Claude 0\n'),
                            ('other text: ' + self.LIMIT_MESSAGE + '\n', 'Claude 0\n'),
                            ('runner stopped\n', 'Claude 0\n'),
                            (self.LIMIT_MESSAGE + '\n', None),
                            (self.LIMIT_MESSAGE + '\n', 'garbage\n'),
                            (self.LIMIT_MESSAGE + '\n', 'Codex 0\n')):
            with self.subTest(error=error, stop=stop):
                records(error, stop)
                self.limit_stop('--now', '1000', expected=1)
        records()
        when = (local / 'last-error').stat().st_mtime
        os.utime(local / 'limit-stop', (when - 300, when - 300))
        self.limit_stop('--now', '1000', expected=1)  # a stale record from an earlier stop

    def test_limit_relaunch_record_manifest_schedule_lifecycle(self):
        self.setup_project()
        self.approve_run()
        manifest_path = next((self.base / 'host-state').rglob('run.json'))

        def manifest():
            return json.loads(manifest_path.read_text())

        head, other = 'a' * 40, 'b' * 40
        self.assertEqual(self.helper('run-manifest', 'limit-count').stdout, '0\n')
        self.helper('run-manifest', 'limit-at', expected=1)
        self.helper('run-manifest', 'reserve-attempt')
        self.assertEqual(self.helper('run-manifest', 'limit-schedule', '100', '2', head).stdout, '1\n')
        self.assertEqual(manifest()['attempts'], 0)
        self.assertEqual(self.helper('run-manifest', 'limit-due', '99', expected=1).stdout, '')
        self.assertEqual(self.helper('run-manifest', 'limit-due', '100').stdout, '100\n')
        failed = self.helper('run-manifest', 'limit-schedule', '200', '2', head, expected=1)
        self.assertIn('a relaunch is already scheduled', failed.stderr)
        self.assertEqual(manifest()['limit_relaunches'], 1)
        # Still waiting: the recovery's reservation is given back, the schedule kept.
        self.helper('run-manifest', 'reserve-attempt')
        self.assertEqual(self.helper('run-manifest', 'limit-hold', '99').stdout, '100\n')
        self.assertEqual((manifest()['attempts'], manifest()['limit_relaunch_at']), (0, 100))
        self.helper('run-manifest', 'limit-claim', '99', expected=1)
        self.helper('run-manifest', 'limit-hold', '100', expected=1)
        self.assertEqual(self.helper('run-manifest', 'limit-at').stdout, '100\n')
        # Due: claimed once, the attempt given back (never below 0).
        self.helper('run-manifest', 'reserve-attempt')
        self.assertEqual(self.helper('run-manifest', 'limit-claim', '100').stdout, '1\n')
        self.assertNotIn('limit_relaunch_at', manifest())
        self.assertEqual(manifest()['attempts'], 0)
        self.helper('run-manifest', 'limit-claim', '100', expected=1)
        self.helper('run-manifest', 'limit-claim', '100', expected=1)
        self.helper('run-manifest', 'limit-at', expected=1)
        self.helper('run-manifest', 'limit-due', '100', expected=1)
        self.assertEqual(manifest()['attempts'], 0)
        # The relaunch checks the checkout it resumes; verify writes nothing.
        moved = self.helper('run-manifest', 'limit-verify', other, expected=1)
        self.assertIn('moved to another commit', moved.stderr)
        before = manifest_path.read_bytes()
        self.helper('run-manifest', 'limit-verify', head)
        self.assertEqual(manifest_path.read_bytes(), before)
        self.helper('run-manifest', 'limit-arm', other, expected=1)
        self.assertEqual(manifest_path.read_bytes(), before)
        self.helper('run-manifest', 'limit-armed', head, expected=1)
        self.helper('run-manifest', 'limit-arm', head)
        self.helper('run-manifest', 'limit-armed', head)
        self.helper('run-manifest', 'limit-armed', other, expected=1)
        self.helper('run-manifest', 'limit-disarm')
        self.helper('run-manifest', 'limit-armed', head, expected=1)
        self.helper('run-manifest', 'limit-disarm')  # missing is fine
        # The cap counts relaunches per human-started run.
        self.assertEqual(self.helper('run-manifest', 'limit-schedule', '300', '2', other).stdout, '2\n')
        self.helper('run-manifest', 'limit-claim', '300')
        capped = self.helper('run-manifest', 'limit-schedule', '400', '2', head, expected=1)
        self.assertIn('usage limit: already relaunched 2 time(s) in this run', capped.stderr)
        self.assertEqual(self.helper('run-manifest', 'limit-count').stdout, '2\n')
        self.helper('run-manifest', 'limit-arm', other)
        self.helper('run-manifest', 'clear-attempts')
        self.assertFalse(set(manifest()) & {'limit_relaunches', 'limit_relaunch_at', 'limit_head', 'limit_resume'})
        unscheduled = self.helper('run-manifest', 'limit-verify', head, expected=1)
        self.assertIn('no scheduled relaunch', unscheduled.stderr)
        self.helper('run-manifest', 'limit-schedule', '500', '2', head)
        self.helper('run-manifest', 'limit-arm', head)
        self.approve_run()
        self.assertFalse(set(manifest()) & {'limit_relaunches', 'limit_relaunch_at', 'limit_head', 'limit_resume'})
        for key, value in (('limit_relaunches', '1'), ('limit_relaunch_at', '100'),
                           ('limit_head', 'x' * 40), ('limit_resume', 7), ('limit_relaunches', True)):
            with self.subTest(key=key, value=value):
                manifest_path.write_text(json.dumps(dict(manifest(), **{key: value})) + '\n')
                invalid = self.helper('run-manifest', 'limit-count', expected=1)
                self.assertIn('No valid run manifest', invalid.stderr)
                self.approve_run()

    def test_limit_relaunch_record_setting_recorded_with_the_run(self):
        self.setup_project()
        self.run_cmd(['python3', str(HELPER), 'run-manifest', 'start', 'c' * 64, 'main', '--approved'],
                     env=dict(self.env, AI_LIMIT_RELAUNCH_MAX='3'))
        manifest = json.loads(next((self.base / 'host-state').rglob('run.json')).read_text())
        self.assertEqual(manifest['env']['AI_LIMIT_RELAUNCH_MAX'], '3')
        restored = self.helper('run-manifest', 'env').stdout
        self.assertIn('AI_LIMIT_RELAUNCH_MAX=3\0', restored)

    def test_limit_relaunch_record_write_never_follows_planted_files(self):
        self.setup_project()
        local = self.project / '.ai/local'
        local.mkdir(exist_ok=True)
        sentinel = self.base / 'sentinel'
        sentinel.write_text('keep me\n')

        def write(*args, expected=0):
            started = time.monotonic()
            result = self.run_cmd(['python3', str(HELPER), 'limit-stop-write', *args], expected=expected,
                                  timeout=SHORT_TIMEOUT)
            self.assertLess(time.monotonic() - started, SHORT_TIMEOUT)
            return result

        def regular_record(expected):
            path = local / 'limit-stop'
            self.assertTrue(path.is_file() and not path.is_symlink())
            self.assertEqual(path.read_text(), expected)

        for name in ('limit-stop', 'limit-stop.tmp'):
            with self.subTest(symlink=name):
                (local / name).unlink(missing_ok=True)
                (local / name).symlink_to(sentinel)
                write('Claude', '123')
                self.assertEqual(sentinel.read_text(), 'keep me\n')
                regular_record('Claude 123\n')
        (local / 'limit-stop').unlink()
        os.mkfifo(local / 'limit-stop')
        write('Codex', '0')  # never blocks on the FIFO: it is replaced
        regular_record('Codex 0\n')
        for args in (('Gemini', '1'), ('Claude', 'soon'), ('Claude', '1' * 13), ('Claude',)):
            with self.subTest(args=args):
                write(*args, expected=1)
                regular_record('Codex 0\n')
        # The first temp name of an in-process writer, planted as a symlink and as a FIFO.
        wf = self.outcome_module()
        first = local / f'.limit-stop.{os.getpid()}.tmp'
        for plant in (lambda: first.symlink_to(sentinel), lambda: os.mkfifo(first)):
            plant()
            started = time.monotonic()
            with mock.patch.dict(os.environ, AI_ROOT=str(self.project)):
                wf.limit_stop_write(['Claude', '77'])
            self.assertLess(time.monotonic() - started, SHORT_TIMEOUT)
            self.assertEqual(sentinel.read_text(), 'keep me\n')
            regular_record('Claude 77\n')
            first.unlink()
        # .ai/local replaced by a symlink: nothing is written anywhere.
        outside = self.base / 'outside'
        outside.mkdir()
        shutil.rmtree(local)
        local.symlink_to(outside)
        write('Claude', '5', expected=1)
        self.assertEqual(list(outside.iterdir()), [])

    def test_limit_relaunch_record_observe_relaunch(self):
        self.setup_project()
        observation = self.project / '.ai/local/observation.json'
        observation.parent.mkdir(exist_ok=True)
        self.helper('observe', 'step', 'build', 'T001')
        self.helper('observe', 'relaunch', '1700000000', 'note')
        record = json.loads(observation.read_text())
        self.assertEqual((record['state'], record['note'], record['relaunch_at']), ('paused', 'note', 1700000000))
        self.assertEqual((record['stage'], record['detail']), ('build', 'T001'))
        self.helper('observe', 'step', 'build', 'x')
        self.assertNotIn('relaunch_at', json.loads(observation.read_text()))
        self.helper('observe', 'relaunch', 'later', 'note')  # warns, never fails the caller
        self.assertNotIn('relaunch_at', json.loads(observation.read_text()))

    def test_codex_usage_limit_pauses_then_retries(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='limit-once', AI_REVIEWER='codex')
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), 2)
        self.assertIn('⏸ PAUSED: Codex usage limit', self.notifications())
        self.assertIn('Host evidence', (self.project / '.ai/reviews/current.md').read_text())

    # ---------------------------------------------------------------- review context (B3)
    def prompts(self):
        path = self.base / 'codex-prompts.log'
        return path.read_text().split('=== PROMPT ===\n')[1:] if path.exists() else []

    def first_review_round(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-always')
        self.commit('chore(ai): record independent review')
        first_head = self.run_cmd(['git', 'rev-parse', 'HEAD~1']).stdout.strip()
        (self.project / '.ai/reviews/dispositions.md').write_text(
            f'Review HEAD: {first_head}\n\n'
            '| Finding | Disposition | Evidence / reason | Fix task |\n| --- | --- | --- | --- |\n'
            '| M1 | rejected | fixture defect is intended by the test | none |\n')
        self.commit('chore(ai): record review triage')
        return first_head

    def test_review_context_first_review_has_no_previous_rounds(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main')
        prompt = self.prompts()[-1]
        self.assertIn('REVIEW SCOPE', prompt)
        self.assertNotIn('PREVIOUS ROUNDS:', prompt)
        self.assertNotIn('CHANGED SINCE THE LAST REVIEW: inspect', prompt)

    def test_review_context_second_review_gets_rounds_and_delta(self):
        first_head = self.first_review_round()
        self.tool('ai-review', '--base', 'main')
        prompt = self.prompts()[-1]
        self.assertIn('PREVIOUS ROUNDS:', prompt)
        self.assertIn('### Round 1', prompt)
        self.assertIn('M1', prompt)
        self.assertIn('rejected', prompt)
        self.assertIn(f'CHANGED SINCE THE LAST REVIEW: inspect git diff {first_head}..', prompt)

    def test_review_context_plan_review_and_recheck_prompts_have_neither(self):
        self.first_review_round()
        self.tool('ai-review', '--recheck')
        self.tool('ai-review', '--plan')
        recheck, plan = self.prompts()[-2:]
        self.assertIn('PLAN SCOPE', plan)
        self.assertIn('RECHECK SCOPE', recheck)
        for prompt in (plan, recheck):
            self.assertNotIn('PREVIOUS ROUNDS:', prompt)
            self.assertNotIn('CHANGED SINCE THE LAST REVIEW: inspect', prompt)
        # Plan reviews only ever get plan history, and only after a plan revision
        # (test_supervised_plan_reject_only_reviews_again_on_a_clean_checkout).
        self.assertNotIn('PLAN REVISION CONTEXT:', plan)

    def test_review_context_failing_helper_still_produces_a_review(self):
        self.first_review_round()
        helper = self.project / '.ai/bin/lib/workflow.py'
        text = helper.read_text()
        marker = 'def review_history(arguments):\n'
        self.assertIn(marker, text)
        helper.write_text(text.replace(marker, marker + "    fail('review-history: forced failure')\n", 1))
        self.commit('fixture: helper that fails')
        self.tool('ai-check')
        result = self.tool('ai-review', '--base', 'main')
        self.assertIn('review-history failed', result.stderr)
        self.assertNotIn('PREVIOUS ROUNDS:', self.prompts()[-1])
        self.assertIn('Host evidence', (self.project / '.ai/reviews/current.md').read_text())

    def test_review_prompt_template_explains_previous_rounds(self):
        text = (ROOT / 'templates/.ai/prompts/review.md').read_text()
        self.assertIn('PREVIOUS ROUNDS', text)
        self.assertIn('CHANGED SINCE THE LAST REVIEW', text)
        self.assertIn('full range', text)

    # ---------------------------------------------------------------- review convergence (FL-03)
    def triage_prompts(self):
        path = self.base / 'triage-prompts.log'
        return path.read_text().split('=== PROMPT ===\n')[1:] if path.exists() else []

    def three_round_pipeline(self):
        """Rounds 1 and 2 triage without a Convergence: line; round 3 stops for lack of it."""
        self.ready()
        return self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--max-fix-rounds', '3',
                         expected=1, MOCK_CODEX='major-always')

    def test_convergence_pipeline_requires_the_line_from_round_three(self):
        result = self.three_round_pipeline()
        self.assertIn('Round 3 triage needs a Convergence: line', result.stderr)
        self.assertIn('Round 3 triage needs a Convergence: line', self.notifications())
        self.assertEqual(self.triage_rounds(), 2)
        prompts = self.triage_prompts()
        self.assertEqual(len(prompts), 3)
        self.assertIn('This review is round 1.', prompts[0])
        self.assertNotIn('PREVIOUS ROUNDS:', prompts[0])
        self.assertIn('This review is round 2.', prompts[1])
        self.assertIn('- M1 [MAJOR] fixture defect at T001.txt:1. — accepted (T002)', prompts[1])
        self.assertIn('This review is round 3.', prompts[2])
        self.assertIn('### Round 1', prompts[2])
        self.assertIn('### Round 2', prompts[2])
        self.assertIn('accepted (T003)', prompts[2])
        # The rerun completes the interrupted round 3 once the line is there.
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--max-fix-rounds', '3',
                  MOCK_CODEX='major-always',
                  MOCK_CONVERGENCE='Convergence: T004 design note "the fixture lacks a marker"')
        self.assertEqual(self.triage_rounds(), 3)
        self.assertIn('This review is round 3.', self.triage_prompts()[-1])
        self.assertEqual(self.helper('tasks', 'status', 'T004').stdout.strip(), 'DONE')

    def test_convergence_interrupted_round_three_resumes_through_ai_run_with_the_same_round(self):
        self.three_round_pipeline()
        self.tool('ai-run', '--approved', '--triage',
                  MOCK_CONVERGENCE='Convergence: none — findings are in unrelated areas (fixture only)')
        self.assertIn('This review is round 3.', self.triage_prompts()[-1])
        self.assertEqual(self.triage_rounds(), 3)
        self.assertEqual(self.helper('review-history', '--current', '--count').stdout.strip(), '2')
        self.helper('triage-check', '--fresh')

    def convergence_fixture(self, title='a short defect', rounds=3):
        """Recorded earlier rounds, then the current review (round `rounds`) with M1 accepted (T001)."""
        self.ready()
        merge_base = self.run_cmd(['git', 'rev-parse', 'main']).stdout.strip()
        current = self.project / '.ai/reviews/current.md'
        for number in range(1, rounds + 1):
            (self.project / f'round{number}.txt').write_text('work\n')
            self.commit(f'work for round {number}')
            head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
            current.write_text(
                f'<!-- Host evidence: HEAD {head}; merge-base {merge_base}; saved now. -->\n\n'
                '# Independent review\nOverall verdict: one major finding\n'
                'Finding counts: BLOCKER=0 MAJOR=1 MINOR=0\n## BLOCKER findings\nNone found.\n'
                f'## MAJOR findings\n- M1: {title}\n## MINOR findings\nNone found.\n')
            self.commit('chore(ai): record independent review')
        self.helper('start-dispositions', head)
        dispositions = self.project / '.ai/reviews/dispositions.md'
        rows = dispositions.read_text() + '| M1 | accepted | defect confirmed in the fixture | T001 |\n'
        dispositions.write_text(rows)
        return dispositions, rows

    def test_convergence_line_checked_only_with_fresh_from_round_three(self):
        dispositions, rows = self.convergence_fixture()
        self.assertEqual(self.helper('review-history', '--current', '--count').stdout.strip(), '2')
        for bad in ('Convergence:', 'Convergence:   \t', 'Convergence:\n| M9 | rejected | x | none |',
                    '<!-- Convergence: hidden in a comment -->', 'convergence: lower case'):
            dispositions.write_text(rows + bad + '\n')
            result = self.helper('triage-check', '--fresh', expected=1)
            self.assertIn('Round 3 triage needs a Convergence: line (see the triage prompt)', result.stderr)
            self.helper('triage-check')  # without --fresh: unchanged
        dispositions.write_text(rows + 'Convergence: T014 design note "the sync model lacks an edited marker"\n')
        self.assertEqual(self.helper('triage-check', '--fresh').stdout.strip(), 'accepted=1 deferred=0')

    def test_convergence_round_two_needs_no_line(self):
        self.convergence_fixture(rounds=2)
        self.assertEqual(self.helper('review-history', '--current', '--count').stdout.strip(), '1')
        self.assertEqual(self.helper('triage-check', '--fresh').stdout.strip(), 'accepted=1 deferred=0')

    def test_convergence_history_over_the_cap_still_counts_round_three(self):
        dispositions, rows = self.convergence_fixture(title='a very long defect ' * 250)
        history = self.helper('review-history', '--current').stdout
        self.assertIn('(1 earlier rounds omitted)', history)
        self.assertLessEqual(len(history.rstrip('\n')), 6000)
        self.assertEqual(self.helper('review-history', '--current', '--count').stdout.strip(), '2')
        result = self.helper('triage-check', '--fresh', expected=1)
        self.assertIn('Round 3 triage needs a Convergence: line', result.stderr)
        dispositions.write_text(rows + 'Convergence: none — findings are in unrelated areas (fixture)\n')
        self.helper('triage-check', '--fresh')

    # ------------------------------------------------------- reviewer fallback
    def claude_review_args(self):
        return [json.loads(line) for line in (self.base / 'claude-review-args.log').read_text().splitlines()]

    def test_review_falls_back_to_claude_at_the_codex_limit(self):
        self.ready()
        self.tool('ai-run', '--approved')
        result = self.tool('ai-review', '--base', 'main', MOCK_CODEX_LIMIT='1')
        self.assertIn('Codex usage limit', result.stdout)
        self.assertIn('Review by Claude (claude-opus-5-5) saved', result.stdout)
        self.assertFalse((self.base / 'sleep.log').exists())  # no pause for a 7-day limit
        review = (self.project / '.ai/reviews/current.md').read_text()
        self.assertIn('> **Reviewer: Claude fallback (claude-opus-5-5, effort high; Codex usage limit', review)
        self.assertIn('BLOCKER 0', self.notifications() or 'BLOCKER 0')
        self.helper('review-info')  # bound like a Codex review
        args = self.claude_review_args()[0]
        self.assertEqual(args[args.index('--model') + 1], 'claude-opus-5-5')
        self.assertEqual(args[args.index('--effort') + 1], 'high')
        self.assertEqual(args[args.index('--tools') + 1], 'Read,Glob,Grep')
        allowed = args[args.index('--allowedTools') + 1:args.index('--setting-sources')]
        self.assertEqual(allowed, ['Read', 'Glob', 'Grep'])
        self.assertIn('--strict-mcp-config', args)
        self.assertFalse((self.project / '.ai/local/review-probes').exists())
        self.assertFalse((self.project / '.ai/local/review-context').exists())
        prompt = (self.base / 'claude-review-prompts.log').read_text()
        self.assertIn('REVIEW SCOPE', prompt)
        self.assertIn('Lock order and deadlocks', prompt)
        self.assertIn('Main/alt identity changes', prompt)
        log = (self.project / '.ai/reviews/fallback-log.md').read_text()
        self.assertIn('| code | feature/test |', log)
        self.assertIn('| claude-opus-5-5 | high | Codex usage limit', log)
        outcome = json.loads((self.base / 'host-state/outcomes.jsonl').read_text().splitlines()[-1])
        self.assertEqual((outcome['kind'], outcome['reviewer'], outcome['model'], outcome['mode']),
                         ('review', 'claude-fallback', 'claude-opus-5-5', 'code'))
        self.assertEqual(outcome['major'], 0)

    def test_claude_reviewer_model_follows_risk_and_overrides(self):
        self.ready(task('T001').replace('Dependencies: none', 'Dependencies: none\nModel: opus'))
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX_LIMIT='1')
        args = self.claude_review_args()[-1]
        self.assertEqual(args[args.index('--model') + 1], 'claude-fable-5-1')
        self.assertIn('claude-fable-5-1', (self.project / '.ai/reviews/current.md').read_text())
        self.commit('record review')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX_LIMIT='1',
                  AI_CLAUDE_REVIEW_MODEL='claude-opus-5-5', AI_CLAUDE_REVIEW_EFFORT='max')
        args = self.claude_review_args()[-1]
        self.assertEqual((args[args.index('--model') + 1], args[args.index('--effort') + 1]), ('claude-opus-5-5', 'max'))
        self.tool('ai-review', '--base', 'main', expected=1, AI_CLAUDE_REVIEW_EFFORT='huge', AI_REVIEWER='claude')

    def test_review_risk_helper(self):
        self.ready(task('T001') + task('T002', dependencies='T001').replace('Verify T002', 'Add the RLS policy'))
        self.assertEqual(self.helper('review-risk').stdout.strip(), 'high T002 title names rls')
        (self.project / '.ai/tasks.md').write_text(task('T001'))
        self.assertEqual(self.helper('review-risk').stdout.strip(), 'normal')
        wf = self.recheck_module()
        for title in ('Add author column to notes', 'Lockfile update', 'Authoring guide for docs', 'Race results page',
                      'Locksmith icon'):
            self.assertIsNone(wf.RISK_TITLE.search(title), title)
        for title in ('Auth callback', 'Fix lock order', 'Account deletion cleanup', 'Data migration', 'Authorization per role',
                      'Race condition in refresh'):
            self.assertIsNotNone(wf.RISK_TITLE.search(title), title)

    def test_reviewer_setting_codex_and_claude_only(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', AI_REVIEWER='claude')
        self.assertFalse((self.base / 'codex-calls').exists())
        self.assertIn('> **Reviewer: Claude (claude-opus-5-5, effort high; AI_REVIEWER=claude)',
                      (self.project / '.ai/reviews/current.md').read_text())
        self.assertIn('| AI_REVIEWER=claude |', (self.project / '.ai/reviews/fallback-log.md').read_text())
        self.tool('ai-review', '--base', 'main', expected=1, AI_REVIEWER='gemini')
        self.commit('record review')
        # Codex reviews carry no label; other Codex errors never fall back.
        self.tool('ai-review', '--base', 'main')
        self.commit('record review')
        self.assertNotIn('Reviewer:', (self.project / '.ai/reviews/current.md').read_text())
        before = len(self.claude_review_args())
        self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX='error')
        self.assertEqual(len(self.claude_review_args()), before)
        # The setting also comes from the user config.
        (self.config / 'ai-toolkit').mkdir()
        (self.config / 'ai-toolkit/config').write_text('AI_REVIEWER=claude\n')
        calls = (self.base / 'codex-calls').read_text().count('call')
        self.tool('ai-review', '--base', 'main')
        self.commit('record review')
        self.assertEqual((self.base / 'codex-calls').read_text().count('call'), calls)

    def test_claude_review_usage_limit_pauses_then_retries_codex_first(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX_LIMIT='1', MOCK_CLAUDE_REVIEW='limit-once')
        self.assertEqual((self.base / 'codex-limit-calls').read_text().count('call'), 2)
        self.assertEqual(len(self.claude_review_args()), 2)
        self.assertIn('⏸ PAUSED: Claude usage limit', self.notifications())
        self.helper('review-info')

    def test_plan_review_and_recheck_fall_back_to_claude(self):
        self.ready()
        result = self.tool('ai-review', '--plan', MOCK_CODEX_LIMIT='1')
        self.assertIn('Plan review by Claude (claude-opus-5-5)', result.stdout)
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        shown = self.run_cmd(['git', 'show', '--stat', 'HEAD']).stdout
        self.assertIn('.ai/reviews/fallback-log.md', shown)
        self.assertIn('Reviewer: Claude fallback', (self.project / '.ai/reviews/plan.md').read_text())
        self.assertTrue(self.helper('plan-review-info').stdout.startswith('current'))

    def test_recheck_falls_back_to_claude(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n'])
        result = self.tool('ai-review', '--recheck', MOCK_CODEX_LIMIT='1')
        self.assertIn('Re-check by Claude (claude-opus-5-5) saved', result.stdout)
        self.assertIn('1 withdrawn', result.stdout)
        report = (self.project / '.ai/reviews/recheck.md').read_text()
        self.assertIn('# Re-check of rejected findings (Claude fallback, claude-opus-5-5)', report)
        self.assertEqual(self.helper('recheck-verify').stdout.splitlines(), ['M1\twithdrawn\tClaude agrees'])
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.assertIn('| recheck |', (self.project / '.ai/reviews/fallback-log.md').read_text())

    def test_pipeline_runs_on_the_claude_fallback_reviewer(self):
        self.ready()
        self.add_origin()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX_LIMIT='1')
        self.assertIn('Pull request: https://github.com/example/project/pull/7', result.stdout)
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        log = (self.project / '.ai/reviews/fallback-log.md').read_text()
        self.assertIn('| plan |', log)
        self.assertIn('| code |', log)
        tracked = self.run_cmd(['git', 'ls-files', '.ai/reviews']).stdout
        self.assertIn('fallback-log.md', tracked)
        body = (self.base / 'gh.log.body.md').read_text()
        self.assertIn('## Independent review (Claude fallback, claude-opus-5-5)', body)
        self.assertIn('Codex reviews it later in one catch-up review', body)
        self.assertIn('instead of Codex (Codex usage limit', body)
        self.assertIn('↪ Codex usage limit', self.notifications())

    def test_pipeline_fallback_recheck_is_committed_with_the_log(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_CODEX_LIMIT='1',
                  MOCK_CLAUDE_REVIEW='major', MOCK_CLAUDE='triage-reject')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.assertIn('Claude fallback, claude-opus-5-5', (self.project / '.ai/reviews/recheck.md').read_text())
        log = (self.project / '.ai/reviews/fallback-log.md').read_text()
        self.assertIn('| recheck |', log)
        shown = self.run_cmd(['git', 'log', '-1', '--stat', '--format=%s', '--grep', 'record review re-check']).stdout
        self.assertIn('fallback-log.md', shown)

    def test_pipeline_without_codex_cli_uses_claude(self):
        self.ready()
        self.add_origin()
        (self.mock_bin / 'codex').unlink()
        # Only the mocks and system tools: a real Codex CLI on this machine must not be found.
        self.env['PATH'] = os.pathsep.join((str(self.mock_bin), '/usr/bin', '/bin'))
        result = self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assertIn('Codex CLI not found', result.stdout)
        self.assertIn('Codex CLI not installed', (self.project / '.ai/reviews/fallback-log.md').read_text())
        self.assertIn('instead of Codex (Codex CLI not installed)', (self.base / 'gh.log.body.md').read_text())
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, AI_REVIEWER='codex')

    def test_claude_review_failure_or_write_keeps_the_prior_review(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main')
        self.commit('record review')
        before = (self.project / '.ai/reviews/current.md').read_text()
        result = self.tool('ai-review', '--base', 'main', expected=1, AI_REVIEWER='claude', MOCK_CLAUDE_REVIEW='error')
        self.assertIn('Claude review failed (exit 3); prior review preserved', result.stderr)
        self.assertEqual((self.project / '.ai/reviews/current.md').read_text(), before)
        self.assertFalse((self.project / '.ai/local/review-context').exists())
        # A reviewer that changes the checkout is never published.
        mock = self.mock_bin / 'claude'
        marker = 'pass  # the reviewer writes nothing (a test rewrites this line)'
        self.assertIn(marker, mock.read_text())
        mock.write_text(mock.read_text().replace(marker, "pathlib.Path('stray.txt').write_text('written by the reviewer')"))
        result = self.tool('ai-review', '--base', 'main', expected=1, AI_REVIEWER='claude')
        self.assertIn('Checkout changed during review', result.stderr)
        self.assertEqual((self.project / '.ai/reviews/current.md').read_text(), before)

    def test_claude_review_denials_and_allowlist_are_recorded(self):
        self.ready()
        self.tool('ai-run', '--approved')
        mock = self.mock_bin / 'claude'
        mock.write_text(mock.read_text().replace(
            "print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[],'result':text}))",
            "print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':text,"
            "'permission_denials':[{'tool_name':'Bash','tool_input':{'command':'git push origin x'}}]}))"))
        result = self.tool('ai-review', '--base', 'main', AI_REVIEWER='claude')
        self.assertIn('1 denied reviewer tool call(s)', result.stderr)
        self.assertIn('git push origin x', (self.project / '.ai/local/review-denials.log').read_text())
        allowlists = list((self.project / '.ai/local').glob('review-*.allowlist'))
        self.assertEqual(len(allowlists), 1)
        self.assertEqual(allowlists[0].read_text().splitlines(), ['Read', 'Glob', 'Grep'])

    def test_pipeline_rejects_an_invalid_reviewer_setting_first(self):
        self.ready()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, AI_REVIEWER='gemini')
        self.assertIn('Invalid AI_REVIEWER: gemini', result.stderr)
        self.assertNotIn('Plan review', result.stdout)

    def test_watchdog_codex_diagnosis_does_not_fall_back(self):
        self.setup_project()
        self.watchdog_stalled('implementing')
        (self.mock_bin / 'codex').write_text('#!/usr/bin/env bash\necho "usage limit"; exit 1\n')
        (self.mock_bin / 'claude').write_text('#!/usr/bin/env bash\ntouch "$MOCK_STATE_DIR/claude-called"\n')
        self.watchdog('--diagnose', '--diagnosis-agent', 'codex', expected=1)
        self.assertFalse((self.base / 'claude-called').exists())
        self.assertIn('Diagnosis unavailable (exit 1)', (self.project / '.ai/local/diagnosis.md').read_text())

    def test_review_allowlist_is_read_glob_grep_whatever_the_project_allows(self):
        self.ready()
        self.tool('ai-run', '--approved')
        allow = self.project / '.ai/permissions.allow'
        allow.write_text(allow.read_text() + 'Bash(npm test)\nBash(npx vitest run *)\nBash(git grep *)\n'
                         'Bash(pytest --basetemp=/x)\nBash(git log *)\nBash(bash *)\nBash(python3 *)\nBash(cat *)\n'
                         'Edit\nWrite\n')
        self.commit('fixture: an allowlist full of runners')
        self.tool('ai-check')
        self.assertEqual(self.helper('review-allowlist').stdout.splitlines(), ['Read', 'Glob', 'Grep'])
        self.tool('ai-review', '--base', 'main', AI_REVIEWER='claude')
        args = self.claude_review_args()[-1]
        self.assertEqual(args[args.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertEqual(args[args.index('--allowedTools') + 1:args.index('--setting-sources')], ['Read', 'Glob', 'Grep'])
        allowlists = list((self.project / '.ai/local').glob('review-*.allowlist'))
        self.assertEqual([path.read_text().splitlines() for path in allowlists], [['Read', 'Glob', 'Grep']])

    # ------------------------------------------- Claude reviewer context (no shell)
    def review_contexts(self):
        path = self.base / 'claude-review-context.log'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def claude_prompts(self):
        return (self.base / 'claude-review-prompts.log').read_text().split('\n=====\n')[:-1]

    def test_claude_review_context_code_mode(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', AI_REVIEWER='claude')
        [context] = self.review_contexts()
        self.assertEqual(context['mode'], 'code')
        self.assertIn('T001.txt', context['files'])
        self.assertIn('diff --git a/T001.txt b/T001.txt', context['diff'])
        self.assertEqual(context['names'], ['diff.patch', 'files.txt', 'log.txt'])
        prompt = self.claude_prompts()[-1]
        self.assertIn('.ai/local/review-context/diff.patch', prompt)
        self.assertNotIn('inspect git diff', prompt.lower())
        self.assertNotIn('since-last-review.patch', prompt)
        self.assertFalse((self.project / '.ai/local/review-context').exists())
        self.helper('review-info')

    def test_claude_review_context_second_review_has_the_delta(self):
        self.first_review_round()
        self.tool('ai-review', '--base', 'main', AI_REVIEWER='claude')
        [context] = self.review_contexts()
        self.assertIn('since-last-review.patch', context['names'])
        prompt = self.claude_prompts()[-1]
        self.assertIn('PREVIOUS ROUNDS:', prompt)
        self.assertIn('CHANGED SINCE THE LAST REVIEW: .ai/local/review-context/since-last-review.patch', prompt)

    def test_claude_review_context_recheck_mode(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n'])
        self.tool('ai-review', '--recheck', MOCK_CODEX_LIMIT='1')
        [context] = self.review_contexts()
        self.assertEqual(context['mode'], 'recheck')
        self.assertIn('T001.txt', context['files'])
        self.assertIn('diff --git a/T001.txt b/T001.txt', context['diff'])
        self.assertIn('M1', context['findings'])
        self.assertIn('findings.txt', self.claude_prompts()[-1])
        self.assertFalse((self.project / '.ai/local/review-context').exists())

    def test_claude_review_context_plan_mode(self):
        self.ready()
        self.tool('ai-review', '--plan', AI_REVIEWER='claude')
        [context] = self.review_contexts()
        self.assertEqual(context['mode'], 'plan')
        self.assertEqual(context['files'], ['.ai/project-spec.md', '.ai/current-plan.md', '.ai/tasks.md'])
        self.assertEqual(context['names'], ['files.txt', 'log.txt'])
        self.assertIn('.ai/local/review-context/files.txt', self.claude_prompts()[-1])
        self.assertFalse((self.project / '.ai/local/review-context').exists())

    def test_claude_review_context_is_rebuilt_after_a_limit_and_removed(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', AI_REVIEWER='claude', MOCK_CLAUDE_REVIEW='limit-once')
        contexts = self.review_contexts()
        self.assertEqual(len(contexts), 2)
        for context in contexts:
            self.assertEqual(context['names'], ['diff.patch', 'files.txt', 'log.txt'])
        self.assertFalse((self.project / '.ai/local/review-context').exists())
        self.helper('review-info')

    def test_claude_review_context_failure_stops_before_claude(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main')
        self.commit('record review')
        before = (self.project / '.ai/reviews/current.md').read_bytes()
        real_git = shutil.which('git', path=self.env['PATH'].split(os.pathsep, 1)[1])
        wrapper = self.mock_bin / 'git'
        # Only the host's context diffs carry --no-ext-diff; preflight git calls pass through.
        wrapper.write_text(f'#!/usr/bin/env bash\n[[ "$1" == diff && " $* " == *" --no-ext-diff "* ]] && exit 1\n'
                           f'exec "{real_git}" "$@"\n')
        wrapper.chmod(0o755)
        result = self.tool('ai-review', '--base', 'main', expected=1, AI_REVIEWER='claude')
        self.assertIn('Could not prepare the review context; prior review preserved.', result.stderr)
        self.assertEqual(self.review_contexts(), [])
        self.assertFalse((self.base / 'claude-review-args.log').exists())
        self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), before)
        self.helper('review-info')
        self.assertFalse((self.project / '.ai/local/review-context').exists())

    def test_review_range_prints_head_and_merge_base(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main')
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        merge_base = self.run_cmd(['git', 'merge-base', 'main', 'HEAD']).stdout.strip()
        self.assertEqual(self.helper('review-range').stdout.split(), [head, merge_base])
        current = self.project / '.ai/reviews/current.md'
        current.write_text(current.read_text() + '\ntampered\n')
        self.helper('review-range', expected=1)

    def test_setup_installs_the_claude_review_prompt(self):
        self.setup_project()
        self.assertIn('Checklist of failure types', (self.project / '.ai/prompts/claude-review.md').read_text())

    # ------------------------------------------------------------ outcome log
    def test_runner_logs_task_outcomes_and_report(self):
        self.ready(task('T001').replace('Dependencies: none', 'Dependencies: none\nModel: sonnet') +
                   task('T002', dependencies='T001').replace('Verify T002', 'Docs for T002'))
        self.tool('ai-run', '--approved')
        lines = [json.loads(x) for x in (self.base / 'host-state/outcomes.jsonl').read_text().splitlines()]
        self.assertEqual([(r['task'], r['model'], r['result'], r['attempt'], r['first_pass']) for r in lines],
                         [('T001', 'sonnet', 'done', 1, True), ('T002', 'default', 'done', 1, True)])
        self.assertEqual(lines[1]['category'], 'docs')
        self.assertEqual(lines[0]['project'], 'project with spaces')
        self.assertEqual(lines[0]['branch'], 'feature/test')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX_LIMIT='1')
        report = self.tool('ai-status', '--outcomes').stdout
        self.assertIn('## Attempts by model', report)
        self.assertIn('| sonnet | 1 | 1 | 0 | 1/1 (100%) |', report)
        self.assertIn('## Tasks by category', report)
        self.assertIn('| claude-fallback | claude-opus-5-5 | code | 1 | 0 | 0 | 0 |', report)
        self.assertIn('Codex catch-up pending', report)
        self.commit('record review')
        self.tool('ai-review', '--base', 'main', AI_REVIEWER='claude')
        report = self.tool('ai-status', '--outcomes').stdout
        catch_up = report.split('Codex catch-up pending')[1]
        self.assertEqual(catch_up.count('code HEAD'), 2)  # forced Claude reviews are listed too

    def outcome_report_for(self, rows):
        self.setup_project()
        path = self.base / 'report.jsonl'
        base = {'kind': 'task', 'project': 'p', 'branch': 'b', 'category': 'feature'}
        path.write_text(''.join(json.dumps({**base, **row}) + '\n' for row in rows))
        return self.tool('ai-status', '--outcomes', str(path)).stdout

    def test_outcome_report_credits_each_attempt_to_its_model(self):
        report = self.outcome_report_for([
            {'task': 'T001', 'model': 'sonnet', 'attempt': 1, 'result': 'error', 'first_pass': False, 'seconds': 600},
            {'task': 'T001', 'model': 'opus', 'attempt': 2, 'result': 'done', 'first_pass': False, 'seconds': 300},
            {'task': 'T002', 'model': 'sonnet', 'attempt': 1, 'result': 'done', 'first_pass': True, 'seconds': 60}])
        self.assertIn('2 task(s), 3 attempt(s)', report)
        self.assertIn('| sonnet | 2 | 1 | 1 | 1/2 (50%) | 5.5 |', report)
        self.assertIn('| opus | 1 | 1 | 0 | - | 5.0 |', report)
        self.assertIn('| sonnet / feature | 2 | 1 | 1 | 1/2 (50%) | 5.5 |', report)
        self.assertIn('| feature | 2 | 1/2 (50%) | 2 | 0 | 1.5 | 8.0 |', report)  # per task, summed time

    def test_outcome_report_old_lines_without_model_or_attempt(self):
        report = self.outcome_report_for([
            {'task': 'T009', 'result': 'error', 'seconds': 60},
            {'task': 'T009', 'result': 'done', 'seconds': 60}])
        self.assertIn('| default | 2 | 1 | 1 | 0/1 (0%) | 1.0 |', report)

    def test_outcome_report_old_line_followed_by_new_attempt(self):
        report = self.outcome_report_for([
            {'task': 'T010', 'result': 'error', 'seconds': 60},
            {'task': 'T010', 'model': 'opus', 'attempt': 2, 'result': 'done', 'first_pass': False, 'seconds': 120}])
        self.assertIn('| default | 1 | 0 | 1 | 0/1 (0%) | 1.0 |', report)
        self.assertIn('| opus | 1 | 1 | 0 | - | 2.0 |', report)

    def test_outcome_attempt_order_round6_equal_seconds(self):
        done = {'task': 'T001', 'model': 'm', 'attempt': 1, 'first_pass': True, 'result': 'done', 'seconds': 5,
                'started': 1000, 'seq': 2}
        crashed = {'task': 'T001', 'model': 'm', 'attempt': 2, 'first_pass': False, 'result': 'crashed',
                   'seconds': None, 'started': 1000, 'seq': 1}
        reports = [self.outcome_report_for([done, crashed]), self.outcome_report_for([crashed, done]),
                   self.outcome_report_for([done, {**crashed, 'started': 900}])]
        for report in reports:
            self.assertIn('1 task(s), 2 attempt(s)', report)
            self.assertIn('| feature | 1 | 0/1 (0%) | 1 | 0 | 2.0 | 0.1 |', report)
            self.assertIn('| m | 2 | 1 | 1 | 0/1 (0%) |', report)
        self.assertEqual(len(set(reports)), 1)

    def test_outcome_attempt_order_pre_upgrade_rows_follow_file_order(self):
        error = {'task': 'T001', 'result': 'error', 'time': '2026-10-17T10:05:00Z', 'seconds': 60}
        done = {'task': 'T001', 'result': 'done', 'time': '2026-10-17T10:00:00Z', 'seconds': 600}
        report = self.outcome_report_for([error, done])
        self.assertIn('| feature | 1 | 0/1 (0%) | 1 | 0 | 2.0 | 11.0 |', report)
        report = self.outcome_report_for([done, error])
        self.assertIn('| feature | 1 | 1/1 (100%) | 0 | 1 | 2.0 | 11.0 |', report)

    def test_outcome_attempt_order_mixed_rows(self):
        old = [{'task': 'T001', 'result': 'error', 'seconds': 60}, {'task': 'T001', 'result': 'done', 'seconds': 60}]
        crashed = {'task': 'T001', 'model': 'm', 'result': 'crashed', 'seconds': None, 'seq': 1}
        done = {'task': 'T001', 'model': 'm', 'result': 'done', 'seconds': 60, 'seq': 2}
        reports = [self.outcome_report_for([*old, crashed, done]), self.outcome_report_for([*old, done, crashed])]
        for report in reports:
            self.assertIn('1 task(s), 4 attempt(s)', report)
            self.assertIn('| feature | 1 | 0/1 (0%) | 1 | 0 | 4.0 | 3.0 |', report)
        self.assertEqual(reports[0], reports[1])

    def test_outcome_attempt_order_real_log_started(self):
        self.outcome_log_project()
        before = int(time.time())
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5')
        after = int(time.time())
        row = self.outcome_rows()[-1]
        self.assertIs(type(row['started']), int)
        self.assertIs(type(row['seq']), int)
        self.assertTrue(before - 5 <= row['started'] <= after - 5, (before, row['started'], after))
        logged = calendar.timegm(time.strptime(row['time'], '%Y-%m-%dT%H:%M:%SZ'))
        self.assertLessEqual(abs(row['started'] - (logged - 5)), 2)  # `time` minus `seconds`

    def catchup_report(self, rows, extra_files=()):
        self.setup_project()
        paths = []
        for index, group in enumerate([rows, *extra_files]):
            path = self.base / f'catchup{index}.jsonl'
            path.write_text(''.join(json.dumps({'project': 'p', 'branch': 'b', **row}) + '\n' for row in group))
            paths.append(str(path))
        return self.tool('ai-status', '--outcomes', *paths).stdout

    def claude_review(self, time, mode='code', **extra):
        return {'kind': 'review', 'reviewer': 'claude-fallback', 'mode': mode, 'model': 'm', 'time': time,
                'head': 'a' * 40, **extra}

    def test_outcome_catchup_later_codex_review_covers(self):
        report = self.catchup_report([self.claude_review('2026-01-01T00:00:01Z'),
                                      {'kind': 'review', 'reviewer': 'codex', 'mode': 'code', 'time': '2026-01-01T00:00:02Z'}])
        self.assertNotIn('Codex catch-up pending', report)
        self.assertIn('1 Claude review(s) covered', report)

    def test_outcome_catchup_earlier_other_branch_or_family_does_not_cover(self):
        claude = self.claude_review('2026-01-01T00:00:05Z')
        for later in ({'kind': 'review', 'reviewer': 'codex', 'mode': 'code', 'time': '2026-01-01T00:00:01Z'},
                      {'kind': 'review', 'reviewer': 'codex', 'mode': 'code', 'time': '2026-01-01T00:00:09Z', 'branch': 'o'},
                      {'kind': 'review', 'reviewer': 'codex', 'mode': 'plan', 'time': '2026-01-01T00:00:09Z'}):
            self.assertIn('Codex catch-up pending', self.catchup_report([claude, later]))

    def test_outcome_catchup_recheck_and_plan_families(self):
        report = self.catchup_report([
            self.claude_review('2026-01-01T00:00:01Z', 'recheck'), self.claude_review('2026-01-01T00:00:01Z', 'plan'),
            {'kind': 'review', 'reviewer': 'codex', 'mode': 'code', 'time': '2026-01-01T00:00:02Z'}])
        self.assertIn('plan HEAD', report.split('Codex catch-up pending')[1])
        self.assertNotIn('recheck HEAD', report)
        self.assertIn('1 Claude review(s) covered', report)
        report = self.catchup_report([
            self.claude_review('2026-01-01T00:00:01Z', 'plan'),
            {'kind': 'review', 'reviewer': 'codex', 'mode': 'plan', 'time': '2026-01-01T00:00:02Z'}])
        self.assertNotIn('Codex catch-up pending', report)

    def test_outcome_catchup_recheck_does_not_cover_code(self):
        report = self.catchup_report([
            self.claude_review('2026-01-01T00:00:01Z'),
            {'kind': 'review', 'reviewer': 'codex', 'mode': 'recheck', 'time': '2026-01-01T00:00:02Z'}])
        self.assertIn('code HEAD', report.split('Codex catch-up pending')[1])
        self.assertNotIn('covered by a later', report)

    def test_outcome_catchup_code_covers_recheck(self):
        report = self.catchup_report([
            self.claude_review('2026-01-01T00:00:01Z', 'recheck'),
            {'kind': 'review', 'reviewer': 'codex', 'mode': 'code', 'time': '2026-01-01T00:00:02Z'}])
        self.assertNotIn('Codex catch-up pending', report)
        self.assertIn('1 Claude review(s) covered', report)

    def test_outcome_catchup_done_command_records_and_covers(self):
        self.setup_project()
        state = self.base / 'host-state/outcomes.jsonl'
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({**self.claude_review('2026-01-01T00:00:01Z'), 'project': 'project with spaces',
                                     'branch': 'feature/x'}) + '\n')
        out = self.tool('ai-status', '--catch-up-done', 'feature/x').stdout
        self.assertIn('Recorded Codex catch-up for feature/x', out)
        record = self.outcome_rows()[-1]
        self.assertEqual((record['kind'], record['branch'], record['project']),
                         ('catchup', 'feature/x', 'project with spaces'))
        self.assertTrue(record['time'])
        self.assertNotIn('Codex catch-up pending', self.tool('ai-status', '--outcomes').stdout)
        with state.open('a') as log:
            log.write(json.dumps({**self.claude_review('2999-01-01T00:00:00Z'), 'project': 'project with spaces',
                                  'branch': 'feature/x'}) + '\n')
        self.assertIn('Codex catch-up pending', self.tool('ai-status', '--outcomes').stdout)

    def test_outcome_catchup_equal_times(self):
        t = '2026-01-01T00:00:01Z'
        self.assertNotIn('Codex catch-up pending', self.catchup_report([self.claude_review(t), {'kind': 'catchup', 'time': t}]))
        self.assertIn('Codex catch-up pending', self.catchup_report([{'kind': 'catchup', 'time': t}, self.claude_review(t)]))
        self.assertIn('Codex catch-up pending', self.catchup_report([self.claude_review(t)], [[{'kind': 'catchup', 'time': t}]]))

    def outcome_module(self):
        spec = importlib.util.spec_from_file_location('workflow', HELPER)
        wf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wf)
        return wf

    def outcome_log_project(self):
        self.setup_project()
        self.commit()  # review records carry HEAD

    def outcome_log_review(self, expected=0):
        return self.helper('outcome', 'review', 'code', 'codex', 'm', 'high', '5', expected=expected)

    def outcome_log_records(self):
        return self.outcome_module().read_outcomes([self.base / 'host-state/outcomes.jsonl'])

    def test_outcome_log_io_appends_to_a_non_empty_log(self):
        self.outcome_log_project()
        for _ in range(3):
            self.outcome_log_review()
        self.assertEqual([r['kind'] for r in self.outcome_log_records()], ['review'] * 3)

    def test_outcome_log_io_torn_line_without_final_newline(self):
        self.outcome_log_project()
        log = self.base / 'host-state/outcomes.jsonl'
        self.outcome_log_review()
        log.write_bytes(log.read_bytes() + b'{"time": "x", "kin')
        self.outcome_log_review()
        records = self.outcome_log_records()
        self.assertEqual([(r['kind'], r['_at'][1]) for r in records], [('review', 0), ('review', 2)])
        self.outcome_log_review()  # the log ends in a newline now: no empty line is inserted
        self.assertEqual(log.read_bytes().count(b'\n'), 4)
        self.assertEqual([r['_at'][1] for r in self.outcome_log_records()], [0, 2, 3])

    def test_outcome_log_io_torn_multibyte_tail(self):
        self.outcome_log_project()
        log = self.base / 'host-state/outcomes.jsonl'
        self.outcome_log_review()
        log.write_bytes(log.read_bytes() + b'{"title": "caf\xc3')
        self.assertEqual(len(self.outcome_log_records()), 1)
        self.outcome_log_review()
        self.assertEqual(len(self.outcome_log_records()), 2)
        self.assertIn('codex', self.tool('ai-status', '--outcomes').stdout)

    def test_outcome_log_io_line_separator_in_a_title(self):
        wf = self.outcome_module()
        log = self.base / 'state/outcomes.jsonl'
        title = 'one\N{LINE SEPARATOR}two'
        self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'title': title}))
        self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'title': 'three'}))
        self.assertIn('\N{LINE SEPARATOR}'.encode(), log.read_bytes())  # written unescaped
        self.assertEqual([r['title'] for r in wf.read_outcomes([log])], [title, 'three'])

    def test_outcome_log_io_short_write_is_a_failure(self):
        import runpy
        self.outcome_log_project()
        log = self.base / 'host-state/outcomes.jsonl'
        self.outcome_log_review()
        real_write = os.write

        def half_write(fd, data):
            if b'"kind"' not in data:
                return real_write(fd, data)
            return real_write(fd, data[:len(data) // 2])

        wf = self.outcome_module()
        with mock.patch('os.write', half_write), mock.patch('os.fsync') as fsync:
            self.assertFalse(wf.append_outcome(log, {'kind': 'review', 'reviewer': 'unit'}))
        fsync.assert_not_called()
        stderr = io.StringIO()
        with mock.patch('os.write', half_write), mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(sys, 'argv', [str(HELPER), 'outcome', 'review', 'code', 'codex', 'm', 'high', '5']), \
                contextlib.chdir(self.project), contextlib.redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as stop:
            runpy.run_path(str(HELPER), run_name='__main__')
        self.assertEqual(stop.exception.code, 1)
        self.assertIn('Could not append the outcome line completely', stderr.getvalue())
        self.outcome_log_review()
        records = self.outcome_log_records()
        self.assertEqual([r['reviewer'] for r in records], ['codex', 'codex'])
        self.assertEqual(log.read_bytes().count(b'\n'), 4)  # two records, two newline-isolated fragments

    def test_outcome_write_protocol_lock_serializes_tail_check_and_write(self):
        import fcntl
        wf = self.outcome_module()
        log = self.base / 'state/outcomes.jsonl'
        log.parent.mkdir()
        log.write_bytes(b'{"kind": "task", "title": "one"}\n')
        fd = os.open(log, os.O_RDWR | os.O_APPEND)
        self.addCleanup(lambda: os.close(fd) if fd is not None else None)
        fcntl.flock(fd, fcntl.LOCK_EX)
        results = []
        thread = threading.Thread(target=lambda: results.append(
            wf.append_outcome(log, {'kind': 'task', 'title': 'two'})), daemon=True)
        thread.start()
        time.sleep(0.3 * TIMEOUT_SCALE)
        self.assertTrue(thread.is_alive())
        self.assertEqual(log.stat().st_size, len(b'{"kind": "task", "title": "one"}\n'))
        os.write(fd, b'{"time": "x", "kin')
        os.close(fd)  # releases the lock
        fd = None
        thread.join(SHORT_TIMEOUT)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results, [True])
        self.assertTrue(log.read_bytes().endswith(b'{"time": "x", "kin\n{"kind": "task", "title": "two"}\n'))
        self.assertEqual([r['title'] for r in wf.read_outcomes([log])], ['one', 'two'])

    def outcome_write_protocol_syncs(self, wf, log):
        """Inodes passed to os.fsync by one append, and whether it returned True."""
        real_fsync = os.fsync
        synced = []

        def recording_fsync(fd):
            synced.append(os.fstat(fd).st_ino)
            return real_fsync(fd)

        with mock.patch('os.fsync', recording_fsync):
            result = wf.append_outcome(log, {'kind': 'task', 'title': 'x'})
        return synced, result

    def test_outcome_write_protocol_syncs_file_then_new_directories(self):
        wf = self.outcome_module()
        log = self.base / 'host-state/nested/outcomes.jsonl'
        synced, result = self.outcome_write_protocol_syncs(wf, log)
        self.assertTrue(result)
        inode = lambda path: os.stat(path).st_ino  # noqa: E731
        self.assertEqual(synced, [inode(log), inode(log.parent), inode(self.base / 'host-state'), inode(self.base)])
        synced, result = self.outcome_write_protocol_syncs(wf, log)
        self.assertTrue(result)
        self.assertEqual(synced, [inode(log), inode(log.parent)])

    def test_outcome_write_protocol_directory_sync_failure(self):
        import runpy
        self.outcome_log_project()
        log = self.base / 'host-state/outcomes.jsonl'
        self.outcome_log_review()
        directory = os.stat(log.parent).st_ino
        real_fsync = os.fsync

        def failing_fsync(fd):
            if os.fstat(fd).st_ino == directory:
                raise OSError(5, 'Input/output error')
            return real_fsync(fd)

        wf = self.outcome_module()
        with mock.patch('os.fsync', failing_fsync), self.assertRaises(OSError):
            wf.append_outcome(log, {'kind': 'review', 'reviewer': 'unit'})
        stderr = io.StringIO()
        with mock.patch('os.fsync', failing_fsync), mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(sys, 'argv', [str(HELPER), 'outcome', 'review', 'code', 'codex', 'm', 'high', '5']), \
                contextlib.chdir(self.project), contextlib.redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as stop:
            runpy.run_path(str(HELPER), run_name='__main__')
        self.assertNotEqual(stop.exception.code, 0)
        self.assertIn('Could not append the outcome line completely', stderr.getvalue())

    def test_outcome_write_protocol_marker_store(self):
        wf = self.outcome_module()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project):
            directory = wf.attempts_dir()
            self.assertEqual(self.helper('outcome', 'attempt-dir').stdout.strip(), str(directory))
            later = self.marker_record('b' * 16, 2)
            earlier = self.marker_record('c' * 16, 1)
            first = wf.write_marker(later)
            second = wf.write_marker(earlier)
            self.assertEqual(sorted(p.name for p in directory.iterdir()), [first.name, second.name])
            content = first.read_bytes()
            with self.assertRaises(FileExistsError):
                wf.write_marker(dict(later, task='T002'))
            self.assertEqual(first.read_bytes(), content)
            self.assertFalse(any(p.name.endswith('.tmp') for p in directory.iterdir()))
            garbage = directory / ('a' * 16 + '.json')
            garbage.write_text('not json')
            self.assertEqual(wf.list_markers(), [(garbage, None, None), (second, earlier, None), (first, later, None)])
            for bad in ('../escape0000000', 'B' * 16, 'b' * 15, None):
                with self.assertRaises(ValueError):
                    wf.write_marker({'id': bad})
            wf.remove_marker(second)
            wf.remove_marker(second)  # already gone: fine
            self.assertEqual([p for p, _, _ in wf.list_markers()], [garbage, first])

    @staticmethod
    def marker_record(attempt_id, seq, **fields):
        return dict({'id': attempt_id, 'task': 'T001', 'model': 'm', 'project': 'p', 'branch': 'b',
                     'started': 1000, 'seq': seq, 'pid': 1, 'pid_start': None}, **fields)

    def test_outcome_marker_contract_three_way_read(self):
        wf = self.outcome_module()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project):
            directory = wf.attempts_dir()
            valid = wf.write_marker(self.marker_record('a' * 16, 1))
            failing = wf.write_marker(self.marker_record('c' * 16, 2))
            garbage = directory / ('b' * 16 + '.json')
            garbage.write_text('{"id": "bbbb')
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            real_read_bytes = Path.read_bytes

            def read_bytes(path):
                if path == failing:
                    raise OSError(errno.EIO, 'Input/output error')
                return real_read_bytes(path)

            with mock.patch.object(Path, 'read_bytes', read_bytes):
                entries = wf.list_markers()
            self.assertEqual(len(entries), 3)
            # Entries without a record sort first, by name.
            self.assertEqual(entries[0], (garbage, None, None))
            self.assertEqual(entries[1][:2], (failing, None))
            self.assertIsInstance(entries[1][2], OSError)
            self.assertEqual(entries[1][2].errno, errno.EIO)
            self.assertEqual(entries[2], (valid, self.marker_record('a' * 16, 1), None))
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)
            if os.geteuid() != 0:
                failing.chmod(0o000)
                try:
                    entry = next(e for e in wf.list_markers() if e[0] == failing)
                finally:
                    failing.chmod(0o600)
                self.assertEqual(entry[1], None)
                self.assertIsInstance(entry[2], PermissionError)
            with mock.patch('os.scandir', side_effect=OSError(errno.EIO, 'Input/output error')), \
                    self.assertRaises(OSError):
                wf.list_markers()

    def test_outcome_marker_contract_invalid_content(self):
        wf = self.outcome_module()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project):
            directory = wf.attempts_dir()
            directory.mkdir(parents=True)
            mismatch = directory / ('d' * 16 + '.json')
            mismatch.write_text(json.dumps(self.marker_record('e' * 16, 1)))
            missing = directory / ('f' * 16 + '.json')
            record = self.marker_record('f' * 16, 1)
            del record['pid_start']
            missing.write_text(json.dumps(record))
            no_seq = directory / ('1' * 16 + '.json')
            record = self.marker_record('1' * 16, 1)
            del record['seq']
            no_seq.write_text(json.dumps(record))
            bool_seq = directory / ('2' * 16 + '.json')
            bool_seq.write_text(json.dumps(self.marker_record('2' * 16, True)))
            text_seq = directory / ('3' * 16 + '.json')
            text_seq.write_text(json.dumps(self.marker_record('3' * 16, '3')))
            self.assertEqual(wf.list_markers(), [(no_seq, None, None), (bool_seq, None, None), (text_seq, None, None),
                                                 (mismatch, None, None), (missing, None, None)])

    def test_outcome_marker_contract_id_printed_before_publish(self):
        wf = self.outcome_module()
        out = io.StringIO()
        real_write_marker = wf.write_marker
        seen = []

        def write_marker(record):
            seen.append(out.getvalue())
            return real_write_marker(record)

        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project), \
                mock.patch.object(wf, 'write_marker', write_marker):
            attempt_id = wf.open_attempt('T001', 'sonnet', os.getpid(), out=out)
            self.assertRegex(attempt_id, r'^[0-9a-f]{16}$')
            self.assertEqual(out.getvalue(), attempt_id + '\n')
            self.assertEqual(seen, [attempt_id + '\n'])
            [(path, record, error)] = wf.list_markers()
            self.assertEqual((path.name, error), (attempt_id + '.json', None))
            self.assertEqual((record['id'], record['task'], record['model'], record['pid']),
                             (attempt_id, 'T001', 'sonnet', os.getpid()))
            self.assertIsInstance(record['pid_start'], int)

    def test_outcome_marker_contract_failure_after_print(self):
        wf = self.outcome_module()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project):
            directory = wf.attempts_dir()
            directory.mkdir(parents=True)
            inode = directory.stat().st_ino
            real_fsync = os.fsync

            def failing_fsync(fd):
                if os.fstat(fd).st_ino == inode:
                    raise OSError(errno.EIO, 'Input/output error')
                return real_fsync(fd)

            out = io.StringIO()
            with mock.patch('os.fsync', failing_fsync), self.assertRaises(OSError):
                wf.open_attempt('T001', 'm', os.getpid(), out=out)
            attempt_id = out.getvalue().strip()
            self.assertRegex(attempt_id, r'^[0-9a-f]{16}$')
            self.assertEqual(json.loads((directory / f'{attempt_id}.json').read_text())['id'], attempt_id)
            wf.remove_marker(directory / f'{attempt_id}.json')
            if os.geteuid() != 0:
                out = io.StringIO()
                directory.chmod(0o500)
                try:
                    with self.assertRaises(OSError):
                        wf.open_attempt('T001', 'm', os.getpid(), out=out)
                finally:
                    directory.chmod(0o700)
                self.assertRegex(out.getvalue(), r'^[0-9a-f]{16}\n$')
                self.assertEqual(list(directory.iterdir()), [])

    def test_outcome_marker_contract_no_publish_when_print_fails(self):
        wf = self.outcome_module()

        class BrokenPipe(io.StringIO):
            def write(self, text):
                raise OSError(errno.EPIPE, 'Broken pipe')

        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project), \
                mock.patch.object(wf, 'write_marker', wraps=wf.write_marker) as write_marker:
            with self.assertRaises(OSError):
                wf.open_attempt('T001', 'm', os.getpid(), out=BrokenPipe())
            write_marker.assert_not_called()
            directory = wf.attempts_dir()
            self.assertEqual(list(directory.iterdir()) if directory.exists() else [], [])

    def test_outcome_removal_gate_strict_read(self):
        wf = self.outcome_module()
        log = self.base / 'state/outcomes.jsonl'
        self.assertEqual(wf.read_outcomes([log], strict=True), [])  # missing log: empty
        self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'attempt_id': 'a' * 16}))
        real_read_bytes = Path.read_bytes
        for error in (OSError(5, 'Input/output error'), PermissionError(13, 'Permission denied')):
            for strict in (True, False):
                raised = []

                def failing_once(path):
                    if not raised:
                        raised.append(path)
                        raise error
                    return real_read_bytes(path)

                with mock.patch.object(Path, 'read_bytes', failing_once):
                    if strict:
                        with self.assertRaises(type(error)):
                            wf.read_outcomes([log], strict=True)
                    else:
                        self.assertEqual(wf.read_outcomes([log]), [])  # lenient mode unchanged
                self.assertEqual(raised, [log])
        self.assertEqual(len(wf.read_outcomes([log], strict=True)), 1)

    def outcome_removal_gate_confirm(self, wf, log, attempt_id, fail_inode=None):
        """Inodes passed to os.fsync by one confirm_recorded, and its result."""
        real_fsync = os.fsync
        synced = []

        def recording_fsync(fd):
            synced.append(os.fstat(fd).st_ino)
            if synced[-1] == fail_inode:
                raise OSError(5, 'Input/output error')
            return real_fsync(fd)

        with mock.patch('os.fsync', recording_fsync):
            return synced, wf.confirm_recorded(log, attempt_id)

    def test_outcome_removal_gate_confirm_recorded(self):
        wf = self.outcome_module()
        log = self.base / 'state/outcomes.jsonl'
        self.assertEqual(self.outcome_removal_gate_confirm(wf, log, 'a' * 16), ([], False))
        self.assertFalse(log.exists())  # a missing log is not created
        self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'attempt_id': 'a' * 16}))
        self.assertTrue(wf.append_outcome(log, {'kind': 'review', 'attempt_id': 'b' * 16}))
        file_inode, directory_inode = os.stat(log).st_ino, os.stat(log.parent).st_ino
        self.assertEqual(self.outcome_removal_gate_confirm(wf, log, 'b' * 16), ([], False))  # not a task
        self.assertEqual(self.outcome_removal_gate_confirm(wf, log, 'c' * 16), ([], False))
        self.assertEqual(self.outcome_removal_gate_confirm(wf, log, 'a' * 16),
                         ([file_inode, directory_inode], True))
        with self.assertRaises(OSError):
            self.outcome_removal_gate_confirm(wf, log, 'a' * 16, fail_inode=file_inode)
        synced = []
        real_fsync = os.fsync

        def failing_directory(fd):
            synced.append(os.fstat(fd).st_ino)
            if synced[-1] == directory_inode:
                raise OSError(5, 'Input/output error')
            return real_fsync(fd)

        with mock.patch('os.fsync', failing_directory), self.assertRaises(OSError):
            wf.confirm_recorded(log, 'a' * 16)
        self.assertEqual(synced, [file_inode, directory_inode])  # file sync observed first

    def test_outcome_removal_gate_waits_for_the_log_lock(self):
        import fcntl
        wf = self.outcome_module()
        log = self.base / 'state/outcomes.jsonl'
        self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'attempt_id': 'a' * 16}))
        fd = os.open(log, os.O_RDWR)
        self.addCleanup(lambda: os.close(fd) if fd is not None else None)
        fcntl.flock(fd, fcntl.LOCK_EX)
        results = []
        thread = threading.Thread(target=lambda: results.append(wf.confirm_recorded(log, 'a' * 16)), daemon=True)
        thread.start()
        time.sleep(0.3 * TIMEOUT_SCALE)
        self.assertTrue(thread.is_alive())
        os.close(fd)  # releases the lock
        fd = None
        thread.join(SHORT_TIMEOUT)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results, [True])

    def test_outcome_removal_gate_torn_multibyte_tail(self):
        wf = self.outcome_module()
        log = self.base / 'state/outcomes.jsonl'
        self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'attempt_id': 'a' * 16}))
        log.write_bytes(log.read_bytes() + b'{"title": "caf\xc3')
        self.assertTrue(wf.confirm_recorded(log, 'a' * 16))
        self.assertEqual(len(wf.read_outcomes([log], strict=True)), 1)

    def outcome_attempt_seq_env(self):
        return mock.patch.dict(os.environ, {'AI_STATE_DIR': str(self.base / 'host-state')})

    def outcome_attempt_seq_helper(self, *args):
        """Run the helper in-process (so mock patches apply); (exit code, stderr)."""
        import runpy
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(sys, 'argv', [str(HELPER), 'outcome', *args]), \
                contextlib.chdir(self.project), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(HELPER), run_name='__main__')
            except SystemExit as stop:
                return stop.code, stderr.getvalue()
        return 0, stderr.getvalue()

    def test_outcome_attempt_seq_fresh_store_and_new_process(self):
        self.outcome_log_project()
        wf = self.outcome_module()
        counter = self.base / 'host-state/attempt-seq'
        with self.outcome_attempt_seq_env():
            self.assertEqual([wf.next_attempt_seq() for _ in range(3)], [1, 2, 3])
        self.assertEqual(counter.read_text(), '3')
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5')
        self.assertEqual(self.outcome_rows()[-1]['seq'], 4)
        self.assertEqual(counter.read_text(), '4')

    def test_outcome_attempt_seq_self_heal(self):
        wf = self.outcome_module()
        state = self.base / 'host-state'
        log, counter = state / 'outcomes.jsonl', state / 'attempt-seq'
        with self.outcome_attempt_seq_env():
            for seq in (7, 2):
                self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'task': 'T001', 'seq': seq}))
            self.assertTrue(wf.append_outcome(log, {'kind': 'review', 'seq': 50}))  # not a task row
            self.assertEqual(wf.next_attempt_seq(), 8)
            self.assertEqual(counter.read_text(), '8')
            self.assertTrue(wf.append_outcome(log, {'kind': 'task', 'task': 'T001', 'seq': 9}))
            counter.write_text('5')
            self.assertEqual(wf.next_attempt_seq(), 10)
            counter.write_text('garbage')
            self.assertEqual(wf.next_attempt_seq(), 10)  # garbage is 0: the log maximum (9) rules
            self.assertEqual(counter.read_text(), '10')
            self.assertEqual(wf.next_attempt_seq(), 11)  # a counter ahead of the log rules too

    def test_outcome_attempt_seq_waits_for_the_log_lock(self):
        import fcntl
        wf = self.outcome_module()
        log = self.base / 'host-state/outcomes.jsonl'
        counter = self.base / 'host-state/attempt-seq'
        with self.outcome_attempt_seq_env():
            self.assertEqual(wf.next_attempt_seq(), 1)
            fd = os.open(log, os.O_RDWR)
            self.addCleanup(lambda: os.close(fd) if fd is not None else None)
            fcntl.flock(fd, fcntl.LOCK_EX)
            results = []
            thread = threading.Thread(target=lambda: results.append(wf.next_attempt_seq()), daemon=True)
            thread.start()
            time.sleep(0.3 * TIMEOUT_SCALE)
            self.assertTrue(thread.is_alive())
            self.assertEqual(counter.read_text(), '1')
            os.close(fd)  # releases the lock
            fd = None
            thread.join(SHORT_TIMEOUT)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results, [2])
        self.assertEqual(counter.read_text(), '2')

    def test_outcome_attempt_seq_allocation_failure(self):
        self.outcome_log_project()
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5')
        state = self.base / 'host-state'
        log = state / 'outcomes.jsonl'
        before = log.read_bytes()
        with mock.patch('os.replace', side_effect=OSError(errno.EIO, 'Input/output error')):
            code, stderr = self.outcome_attempt_seq_helper('task', 'T001', 'done', 'm', '5')
        self.assertEqual(code, 1)
        self.assertIn('Could not allocate the attempt sequence', stderr)
        self.assertEqual(log.read_bytes(), before)
        self.assertFalse((state / 'attempt-seq.tmp').exists())
        wf = self.outcome_module()
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project):
            directory = wf.attempts_dir()
            with mock.patch('os.replace', side_effect=OSError(errno.EIO, 'Input/output error')), \
                    self.assertRaises(OSError):
                wf.open_attempt('T001', 'm', os.getpid(), out=out)
            self.assertEqual(out.getvalue(), '')
            self.assertEqual(list(directory.iterdir()) if directory.exists() else [], [])
            self.assertFalse((state / 'attempt-seq.tmp').exists())
        if os.geteuid() != 0:
            state.chmod(0o500)
            try:
                code, stderr = self.outcome_attempt_seq_helper('task', 'T001', 'done', 'm', '5')
            finally:
                state.chmod(0o700)
            self.assertEqual(code, 1)
            self.assertIn('Could not allocate the attempt sequence', stderr)
            self.assertEqual(log.read_bytes(), before)

    def test_outcome_attempt_seq_open_attempt_then_outcome(self):
        self.outcome_log_project()
        wf = self.outcome_module()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.chdir(self.project):
            wf.open_attempt('T001', 'm', os.getpid(), out=io.StringIO())
            [(_, record, _)] = wf.list_markers()
        counter = self.base / 'host-state/attempt-seq'
        self.assertEqual(record['seq'], int(counter.read_text()))
        self.helper('outcome', 'task', 'T002', 'done', 'm', '5')
        self.assertGreater(self.outcome_rows()[-1]['seq'], record['seq'])

    def test_outcome_attempt_seq_real_log_row(self):
        self.outcome_log_project()
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5')
        row = self.outcome_rows()[-1]
        self.assertIs(type(row['seq']), int)
        self.assertGreaterEqual(row['seq'], 1)
        self.assertEqual((self.base / 'host-state/attempt-seq').read_text(), str(row['seq']))

    def test_outcome_attempt_seq_ordered_attempts(self):
        wf = self.outcome_module()

        def rows(*specs):
            return [dict({'kind': 'task', 'project': 'p', 'branch': 'b', 'task': 'T001', '_at': (0, at)}, **fields)
                    for at, fields in specs]

        def order(task_rows):
            return {key: [r['name'] for r in value] for key, value in wf.ordered_attempts(task_rows).items()}

        key = ('p', 'b', 'T001')
        # Round 6 reproduction: B done (seq 2) logged before A crashed (seq 1), same start second.
        for b_at, a_at in ((0, 1), (1, 0)):
            self.assertEqual(order(rows((b_at, {'name': 'B', 'result': 'done', 'seq': 2, 'started': 1000}),
                                        (a_at, {'name': 'A', 'result': 'crashed', 'seq': 1, 'started': 1000}))),
                             {key: ['A', 'B']})
        self.assertEqual(order(rows((2, {'name': 'y'}), (1, {'name': 'x'}))), {key: ['x', 'y']})
        self.assertEqual(order(rows((0, {'name': 'new', 'seq': 3}), (1, {'name': 'old1'}), (2, {'name': 'old2'}))),
                         {key: ['old1', 'old2', 'new']})
        self.assertEqual(order(rows((5, {'name': 'late', 'seq': 4}), (3, {'name': 'early', 'seq': 4}))),
                         {key: ['early', 'late']})
        self.assertEqual(order(rows((0, {'name': 'int', 'seq': 1}), (1, {'name': 'bool', 'seq': True}),
                                    (2, {'name': 'text', 'seq': '2'}))),
                         {key: ['bool', 'text', 'int']})
        self.assertEqual(order(rows((0, {'name': 'a', 'seq': 1}), (1, {'name': 'o', 'seq': 2, 'branch': 'o'}))),
                         {key: ['a'], ('p', 'o', 'T001'): ['o']})
        self.assertIsNone(wf.attempt_seq({'seq': False}))
        self.assertEqual(wf.attempt_seq({'seq': 0}), 0)

    def outcome_attempt_setup(self):
        """A project with the helper module imported and the test inside its environment."""
        self.outcome_log_project()
        wf = self.outcome_module()
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.dict(os.environ, self.env, clear=True))
        stack.enter_context(contextlib.chdir(self.project))
        self.addCleanup(stack.close)
        self.attempt_log = self.base / 'host-state/outcomes.jsonl'
        return wf

    def outcome_attempt_cmd(self, *args):
        """`outcome ARGS` in-process (so mock patches apply); (exit code, stdout, stderr)."""
        import runpy
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(sys, 'argv', [str(HELPER), 'outcome', *args]), contextlib.chdir(self.project), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                runpy.run_path(str(HELPER), run_name='__main__')
                code = 0
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()

    def outcome_attempt_rows(self, wf, attempt_id=None):
        return [r for r in wf.read_outcomes([self.attempt_log]) if r.get('kind') == 'task'
                and (attempt_id is None or r.get('attempt_id') == attempt_id)]

    @staticmethod
    def outcome_attempt_dead_pid():
        child = subprocess.Popen(['true'])
        child.wait()  # reaped: no /proc entry left
        return child.pid

    def outcome_attempt_marker(self, wf, task='T001', **fields):
        """Publish a marker as a runner that has since died would have; (path, record)."""
        branch = wf.git('symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()
        record = dict({'id': os.urandom(8).hex(), 'task': task, 'model': 'm', 'project': wf.project_name(),
                       'branch': branch, 'started': int(time.time()), 'seq': wf.next_attempt_seq(),
                       'pid': self.outcome_attempt_dead_pid(), 'pid_start': None}, **fields)
        return wf.write_marker(record), record

    def outcome_attempt_reconcile(self, *args):
        return self.helper('outcome', 'attempt-reconcile', *args)

    @staticmethod
    def outcome_attempt_category_row(report):
        """Cells of the single row of the "Tasks by category" table."""
        section = report.split('## Tasks by category')[1].split('\n\n')[1]
        [row] = section.splitlines()[2:]
        return [cell.strip() for cell in row.strip('|').split('|')]

    def test_outcome_attempt_open_close_reconcile(self):
        wf = self.outcome_attempt_setup()
        attempt_id = self.helper('outcome', 'attempt-open', 'T001', 'm', str(os.getpid())).stdout.strip()
        self.assertRegex(attempt_id, r'^[0-9a-f]{16}$')
        marker = wf.attempts_dir() / f'{attempt_id}.json'
        opened = json.loads(marker.read_text())
        self.assertEqual((opened['task'], opened['pid'], opened['pid_start']),
                         ('T001', os.getpid(), wf.process_start(os.getpid())))
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5', '--attempt', attempt_id)
        [row] = self.outcome_attempt_rows(wf)
        self.assertEqual((row['attempt_id'], row['seq'], row['started']), (attempt_id, opened['seq'], opened['started']))
        self.assertFalse(marker.exists())
        self.assertEqual(self.outcome_attempt_reconcile().stderr, '')
        self.assertEqual(len(self.outcome_attempt_rows(wf)), 1)

    def test_outcome_attempt_dead_runner_logged_once(self):
        wf = self.outcome_attempt_setup()
        marker, record = self.outcome_attempt_marker(wf, model='opus')
        result = self.outcome_attempt_reconcile()
        self.assertIn('Note: logged a crashed attempt of T001 (the runner was killed without its exit handler).',
                      result.stderr)
        [row] = self.outcome_attempt_rows(wf)
        self.assertEqual({k: row[k] for k in ('task', 'model', 'branch', 'project', 'result', 'seconds', 'attempt',
                                               'first_pass', 'seq', 'started', 'attempt_id')},
                         {'task': 'T001', 'model': 'opus', 'branch': record['branch'], 'project': record['project'],
                          'result': 'crashed', 'seconds': None, 'attempt': 1, 'first_pass': False,
                          'seq': record['seq'], 'started': record['started'], 'attempt_id': record['id']})
        self.assertFalse(marker.exists())
        self.assertEqual(self.outcome_attempt_reconcile().stderr, '')
        self.assertEqual(len(self.outcome_attempt_rows(wf)), 1)
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5')
        self.assertEqual([r['attempt'] for r in self.outcome_attempt_rows(wf)], [1, 2])

    def test_outcome_attempt_branch_comes_from_the_marker(self):
        wf = self.outcome_attempt_setup()
        self.outcome_attempt_marker(wf, branch='feature/old')
        self.outcome_attempt_reconcile()
        [row] = self.outcome_attempt_rows(wf)
        self.assertEqual(row['branch'], 'feature/old')

    def test_outcome_attempt_crash_between_append_and_unlink(self):
        wf = self.outcome_attempt_setup()
        marker, record = self.outcome_attempt_marker(wf)
        self.assertTrue(wf.append_outcome(self.attempt_log, {'kind': 'task', 'task': 'T001', 'result': 'done',
                                                             'attempt_id': record['id'], 'seq': record['seq']}))
        self.assertEqual(self.outcome_attempt_reconcile().stderr, '')
        self.assertEqual(len(self.outcome_attempt_rows(wf)), 1)
        self.assertFalse(marker.exists())

    def test_outcome_attempt_live_runner_left_alone(self):
        wf = self.outcome_attempt_setup()
        start = wf.process_start(os.getpid())
        live, _ = self.outcome_attempt_marker(wf, pid=os.getpid(), pid_start=start)
        unknown_start, _ = self.outcome_attempt_marker(wf, pid=os.getpid(), pid_start=None)
        content = live.read_bytes()
        self.assertEqual(self.outcome_attempt_reconcile().stderr, '')
        self.assertEqual(live.read_bytes(), content)
        self.assertTrue(unknown_start.exists())
        self.assertEqual(self.outcome_attempt_rows(wf), [])
        reused, record = self.outcome_attempt_marker(wf, pid=os.getpid(), pid_start=start + 1)
        self.assertIn('logged a crashed attempt', self.outcome_attempt_reconcile().stderr)
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [record['id']])
        self.assertFalse(reused.exists())
        self.assertTrue(live.exists())

    def test_outcome_attempt_garbage_marker_discarded(self):
        wf = self.outcome_attempt_setup()
        garbage = wf.attempts_dir() / ('a' * 16 + '.json')
        garbage.parent.mkdir(parents=True)
        garbage.write_text('not json')
        result = self.outcome_attempt_reconcile()
        self.assertIn('Note: discarded an invalid attempt marker.', result.stderr)
        self.assertFalse(garbage.exists())
        self.assertEqual(self.outcome_attempt_rows(wf), [])

    def test_outcome_attempt_transient_marker_read_failure(self):
        wf = self.outcome_attempt_setup()
        first, a = self.outcome_attempt_marker(wf)
        second, b = self.outcome_attempt_marker(wf)
        content = first.read_bytes()
        real_read_bytes = Path.read_bytes
        raised = []

        def failing_once(path):
            if path == first and not raised:
                raised.append(path)
                raise OSError(errno.EIO, 'Input/output error')
            return real_read_bytes(path)

        with mock.patch.object(Path, 'read_bytes', failing_once):
            code, _, err = self.outcome_attempt_cmd('attempt-reconcile')
        self.assertEqual((code, raised), (0, [first]))
        self.assertIn('Note: could not read an attempt marker; keeping it.', err)
        self.assertEqual(first.read_bytes(), content)
        self.assertFalse(second.exists())
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [b['id']])
        self.outcome_attempt_reconcile()
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [b['id'], a['id']])
        self.assertFalse(first.exists())

    @unittest.skipIf(os.geteuid() == 0, 'root reads a 0o000 file')
    def test_outcome_attempt_unreadable_marker_file(self):
        wf = self.outcome_attempt_setup()
        first, a = self.outcome_attempt_marker(wf)
        second, b = self.outcome_attempt_marker(wf)
        content = first.read_bytes()
        first.chmod(0o000)
        try:
            result = self.outcome_attempt_reconcile()
        finally:
            first.chmod(0o600)
        self.assertIn('could not read an attempt marker', result.stderr)
        self.assertEqual(first.read_bytes(), content)
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [b['id']])
        self.outcome_attempt_reconcile()
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [b['id'], a['id']])

    def test_outcome_attempt_unlistable_directory(self):
        wf = self.outcome_attempt_setup()
        marker, _ = self.outcome_attempt_marker(wf)
        content = marker.read_bytes()
        with mock.patch('os.scandir', side_effect=OSError(errno.EIO, 'Input/output error')):
            code, _, err = self.outcome_attempt_cmd('attempt-reconcile')
        self.assertEqual(code, 0)
        self.assertIn('Note: could not list the attempt markers.', err)
        self.assertEqual(marker.read_bytes(), content)
        self.assertEqual(self.outcome_attempt_rows(wf), [])

    def outcome_attempt_delayed(self, offset=0, chmod=False):
        """Round 5/6 P15: A dies, its marker is unreadable while B opens and finishes in the same
        second; A is logged later, after B's line, and the task stays done."""
        wf = self.outcome_attempt_setup()
        marker_a, a = self.outcome_attempt_marker(wf, started=int(time.time()) + offset)
        blocked = [True]
        real_read_bytes = Path.read_bytes

        def read_bytes(path):
            if path == marker_a and blocked[0]:
                raise OSError(errno.EIO, 'Input/output error')
            return real_read_bytes(path)

        if chmod:
            marker_a.chmod(0o000)
        with contextlib.nullcontext() if chmod else mock.patch.object(Path, 'read_bytes', read_bytes):
            code, out, err = self.outcome_attempt_cmd('attempt-open', 'T001', 'm', str(os.getpid()))
        self.assertEqual(code, 0)
        self.assertIn('could not read an attempt marker', err)
        b_id = out.strip()
        marker_b = wf.attempts_dir() / f'{b_id}.json'
        b = json.loads(marker_b.read_text())
        self.assertEqual(b['seq'], a['seq'] + 1)
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5', '--attempt', b_id)
        [row_b] = self.outcome_attempt_rows(wf)
        self.assertEqual((row_b['seq'], row_b['started']), (b['seq'], b['started']))
        self.assertFalse(marker_b.exists())
        row = self.outcome_attempt_category_row(self.tool('ai-status', '--outcomes').stdout)
        self.assertEqual(row[1:6], ['1', '1/1 (100%)', '1', '0', '1.0'])
        if chmod:
            marker_a.chmod(0o600)
        blocked[0] = False
        self.outcome_attempt_reconcile()
        rows = self.outcome_attempt_rows(wf)
        self.assertEqual([r['attempt_id'] for r in rows], [b_id, a['id']])  # logged after B's line
        self.assertEqual((rows[1]['result'], rows[1]['seq'], rows[1]['started']), ('crashed', a['seq'], a['started']))
        self.assertFalse(marker_a.exists())
        report = self.tool('ai-status', '--outcomes').stdout
        self.assertEqual(self.outcome_attempt_category_row(report)[1:6], ['1', '0/1 (0%)', '1', '0', '2.0'])
        for _ in range(2):
            self.outcome_attempt_reconcile()
            self.assertEqual(len(self.outcome_attempt_rows(wf)), 2)
            self.assertEqual(self.tool('ai-status', '--outcomes').stdout, report)

    def test_outcome_attempt_delayed_reconcile_same_second(self):
        self.outcome_attempt_delayed()

    def test_outcome_attempt_delayed_reconcile_older_start(self):
        self.outcome_attempt_delayed(offset=-100)

    @unittest.skipIf(os.geteuid() == 0, 'root reads a 0o000 file')
    def test_outcome_attempt_delayed_reconcile_unreadable_file(self):
        self.outcome_attempt_delayed(chmod=True)

    def test_outcome_attempt_task_row_seq_without_marker(self):
        wf = self.outcome_attempt_setup()
        attempt_id = self.helper('outcome', 'attempt-open', 'T001', 'm', str(os.getpid())).stdout.strip()
        marker = wf.attempts_dir() / f'{attempt_id}.json'
        opened = json.loads(marker.read_text())
        wf.remove_marker(marker)  # P13: the id was printed, the marker never published
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5', '--attempt', attempt_id)
        [row] = self.outcome_attempt_rows(wf)
        self.assertGreater(row['seq'], opened['seq'])
        self.assertEqual((self.base / 'host-state/attempt-seq').read_text(), str(row['seq']))
        self.assertLessEqual(abs(row['started'] - (time.time() - 5)), 5)
        self.assertEqual(row['attempt_id'], attempt_id)

    def test_outcome_attempt_task_row_allocation_failure(self):
        wf = self.outcome_attempt_setup()
        failing_replace = mock.patch('os.replace', side_effect=OSError(errno.EIO, 'Input/output error'))
        with failing_replace:
            code, out, err = self.outcome_attempt_cmd('attempt-open', 'T001', 'm', str(os.getpid()))
        self.assertEqual((code, out), (1, ''))
        self.assertIn('Note: could not allocate the attempt sequence.', err)
        self.assertFalse(wf.attempts_dir().exists() and any(wf.attempts_dir().iterdir()))
        with failing_replace:
            code, _, err = self.outcome_attempt_cmd('task', 'T001', 'done', 'm', '5', '--attempt', 'ab' * 8)
        self.assertEqual(code, 1)
        self.assertIn('Could not allocate the attempt sequence', err)
        self.assertEqual(self.outcome_attempt_rows(wf), [])
        marker, record = self.outcome_attempt_marker(wf)
        content = marker.read_bytes()
        real_read_bytes = Path.read_bytes

        def unreadable(path):
            if path == marker:
                raise OSError(errno.EIO, 'Input/output error')
            return real_read_bytes(path)

        with failing_replace, mock.patch.object(Path, 'read_bytes', unreadable):
            code, _, err = self.outcome_attempt_cmd('task', 'T001', 'done', 'm', '5', '--attempt', record['id'])
        self.assertEqual(code, 1)
        self.assertIn('Could not allocate the attempt sequence', err)
        self.assertEqual(self.outcome_attempt_rows(wf), [])
        self.assertEqual(marker.read_bytes(), content)
        self.outcome_attempt_reconcile()
        [row] = self.outcome_attempt_rows(wf)
        self.assertEqual((row['result'], row['seq'], row['attempt_id']), ('crashed', record['seq'], record['id']))
        self.assertFalse(marker.exists())

    def test_outcome_attempt_open_publish_failure(self):
        wf = self.outcome_attempt_setup()
        directory = wf.attempts_dir()
        directory.mkdir(parents=True)
        inode = directory.stat().st_ino
        real_fsync = os.fsync

        def failing_fsync(fd):
            if os.fstat(fd).st_ino == inode:
                raise OSError(errno.EIO, 'Input/output error')
            return real_fsync(fd)

        with mock.patch('os.fsync', failing_fsync):
            code, out, err = self.outcome_attempt_cmd('attempt-open', 'T001', 'm', str(os.getpid()))
        attempt_id = out.strip()
        self.assertEqual(code, 1)
        self.assertRegex(out, r'^[0-9a-f]{16}\n$')
        self.assertIn('Note: could not publish the attempt marker.', err)
        self.assertTrue((directory / f'{attempt_id}.json').exists())
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5', '--attempt', attempt_id)
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [attempt_id])
        self.assertFalse((directory / f'{attempt_id}.json').exists())
        self.outcome_attempt_reconcile()
        self.assertEqual(len(self.outcome_attempt_rows(wf)), 1)
        if os.geteuid() != 0:
            directory.chmod(0o500)
            try:
                result = self.helper('outcome', 'attempt-open', 'T002', 'm', str(os.getpid()), expected=1)
            finally:
                directory.chmod(0o700)
            self.assertRegex(result.stdout, r'^[0-9a-f]{16}\n$')
            self.assertIn('could not publish the attempt marker', result.stderr)
            self.assertEqual(list(directory.iterdir()), [])
            second = result.stdout.strip()
            self.helper('outcome', 'task', 'T002', 'done', 'm', '5', '--attempt', second)
            self.outcome_attempt_reconcile()
            self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [attempt_id, second])

    def test_outcome_attempt_torn_tail(self):
        wf = self.outcome_attempt_setup()
        self.outcome_attempt_marker(wf)  # creates the log
        self.attempt_log.write_bytes(self.attempt_log.read_bytes() + b'{"time": "x", "kin')
        self.outcome_attempt_reconcile()
        self.assertIn(b'"kin\n{', self.attempt_log.read_bytes())
        self.assertEqual([r['result'] for r in wf.read_outcomes([self.attempt_log])], ['crashed'])

    def test_outcome_attempt_torn_multibyte_tail(self):
        wf = self.outcome_attempt_setup()
        self.helper('outcome', 'task', 'T001', 'error', 'm', '5')
        self.attempt_log.write_bytes(self.attempt_log.read_bytes() + b'{"title": "caf\xc3')
        self.outcome_attempt_marker(wf)
        self.outcome_attempt_reconcile()
        self.assertEqual([r['result'] for r in self.outcome_attempt_rows(wf)], ['error', 'crashed'])
        self.outcome_attempt_reconcile()
        self.assertEqual(len(self.outcome_attempt_rows(wf)), 2)

    @staticmethod
    def outcome_attempt_half_write(needle):
        real_write = os.write

        def half_write(fd, data):
            if needle not in data:
                return real_write(fd, data)
            return real_write(fd, data[:len(data) // 2])
        return mock.patch('os.write', half_write)

    def test_outcome_attempt_short_write_during_reconcile(self):
        wf = self.outcome_attempt_setup()
        marker, record = self.outcome_attempt_marker(wf)
        content = marker.read_bytes()
        with self.outcome_attempt_half_write(b'"crashed"'):
            code, _, err = self.outcome_attempt_cmd('attempt-reconcile')
        self.assertEqual(code, 0)
        self.assertIn('Note: could not log the crashed attempt completely; will retry at the next start.', err)
        self.assertEqual(marker.read_bytes(), content)
        self.assertEqual(self.outcome_attempt_rows(wf), [])
        self.outcome_attempt_reconcile()
        [row] = self.outcome_attempt_rows(wf)
        self.assertEqual((row['result'], row['attempt_id']), ('crashed', record['id']))
        self.assertEqual(row['_at'][1], 1)  # after the fragment's line
        self.assertFalse(marker.exists())
        marker, record = self.outcome_attempt_marker(wf, task='T002')
        with self.outcome_attempt_half_write(b'"kind"'):
            code, _, _ = self.outcome_attempt_cmd('task', 'T002', 'done', 'm', '5', '--attempt', record['id'])
        self.assertEqual(code, 1)
        self.assertTrue(marker.exists())

    def test_outcome_attempt_other_marker_left_alone(self):
        wf = self.outcome_attempt_setup()
        marker, _ = self.outcome_attempt_marker(wf)
        content = marker.read_bytes()
        self.helper('outcome', 'task', 'T001', 'done', 'm', '5', '--attempt', 'ab' * 8)
        self.assertEqual(marker.read_bytes(), content)

    def test_outcome_attempt_own_earlier_attempt_reconciled_at_open(self):
        wf = self.outcome_attempt_setup()
        pid = str(os.getpid())
        a = self.helper('outcome', 'attempt-open', 'T002', 'm', pid).stdout.strip()
        marker_a = wf.attempts_dir() / f'{a}.json'
        with self.outcome_attempt_half_write(b'"kind"'):
            code, _, _ = self.outcome_attempt_cmd('task', 'T002', 'failed', 'm', '5', '--attempt', a)
        self.assertEqual(code, 1)
        self.assertTrue(marker_a.exists())
        result = self.helper('outcome', 'attempt-open', 'T002', 'm', pid)
        b = result.stdout.strip()
        self.assertIn('logged a crashed attempt of T002', result.stderr)
        self.assertEqual([(r['attempt_id'], r['result']) for r in self.outcome_attempt_rows(wf)], [(a, 'crashed')])
        self.assertFalse(marker_a.exists())
        self.assertTrue((wf.attempts_dir() / f'{b}.json').exists())
        self.helper('outcome', 'task', 'T002', 'done', 'm', '5', '--attempt', b)
        self.assertFalse((wf.attempts_dir() / f'{b}.json').exists())
        self.outcome_attempt_reconcile(pid)
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [a, b])

    def test_outcome_attempt_own_earlier_attempt_reconcile_fails_too(self):
        wf = self.outcome_attempt_setup()
        pid = str(os.getpid())
        a = self.helper('outcome', 'attempt-open', 'T002', 'm', pid).stdout.strip()
        marker_a = wf.attempts_dir() / f'{a}.json'
        with self.outcome_attempt_half_write(b'"kind"'):
            self.outcome_attempt_cmd('task', 'T002', 'failed', 'm', '5', '--attempt', a)
        content = marker_a.read_bytes()
        with self.outcome_attempt_half_write(b'"kind"'):
            code, out, err = self.outcome_attempt_cmd('attempt-open', 'T002', 'm', pid)
        self.assertEqual(code, 0)
        self.assertIn('could not log the crashed attempt completely', err)
        b = out.strip()
        self.assertEqual(marker_a.read_bytes(), content)
        self.assertTrue((wf.attempts_dir() / f'{b}.json').exists())
        self.assertEqual(self.outcome_attempt_rows(wf), [])
        self.helper('outcome', 'task', 'T002', 'done', 'm', '5', '--attempt', b)
        self.outcome_attempt_reconcile(pid)
        self.outcome_attempt_reconcile(pid)
        self.assertEqual(sorted((r['attempt_id'], r['result']) for r in self.outcome_attempt_rows(wf)),
                         sorted([(a, 'crashed'), (b, 'done')]))

    def test_outcome_attempt_two_dead_runners(self):
        wf = self.outcome_attempt_setup()
        first, a = self.outcome_attempt_marker(wf)
        second, b = self.outcome_attempt_marker(wf, task='T002')
        self.outcome_attempt_reconcile()
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [a['id'], b['id']])
        self.assertFalse(first.exists() or second.exists())
        self.outcome_attempt_reconcile()
        self.assertEqual(len(self.outcome_attempt_rows(wf)), 2)

    def test_outcome_attempt_failed_sync_after_complete_write(self):
        wf = self.outcome_attempt_setup()
        self.assertTrue(wf.append_outcome(self.attempt_log, {'kind': 'review'}))
        file_inode, directory_inode = self.attempt_log.stat().st_ino, self.attempt_log.parent.stat().st_ino
        real_fsync = os.fsync
        for fail_inode in (file_inode, directory_inode):
            with self.subTest(fail_inode=fail_inode):
                marker, record = self.outcome_attempt_marker(wf)
                synced = []

                def fsync(fd, fail=fail_inode):
                    synced.append(os.fstat(fd).st_ino)
                    if fail is not None and synced[-1] == fail:
                        raise OSError(errno.EIO, 'Input/output error')
                    return real_fsync(fd)

                with mock.patch('os.fsync', fsync):
                    code, _, _ = self.outcome_attempt_cmd('task', 'T001', 'done', 'm', '5', '--attempt', record['id'])
                    self.assertNotEqual(code, 0)
                    self.assertEqual(len(self.outcome_attempt_rows(wf, record['id'])), 1)
                    self.assertTrue(marker.exists())
                    code, _, err = self.outcome_attempt_cmd('attempt-reconcile')
                self.assertEqual(code, 0)
                self.assertIn('Note: could not read or sync the outcome log; keeping the attempt marker.', err)
                self.assertTrue(marker.exists())
                self.assertEqual(len(self.outcome_attempt_rows(wf, record['id'])), 1)
                synced.clear()
                with mock.patch('os.fsync', lambda fd: fsync(fd, None)):
                    self.outcome_attempt_cmd('attempt-reconcile')
                self.assertEqual(synced[:2], [file_inode, directory_inode])
                self.assertFalse(marker.exists())
                self.assertEqual(len(self.outcome_attempt_rows(wf, record['id'])), 1)

    def test_outcome_attempt_unreadable_log(self):
        wf = self.outcome_attempt_setup()
        self.assertTrue(wf.append_outcome(self.attempt_log, {'kind': 'review'}))
        log_inode = self.attempt_log.stat().st_ino
        real_read, real_read_bytes = os.read, Path.read_bytes
        for recorded in (True, False):
            with self.subTest(recorded=recorded):
                marker, record = self.outcome_attempt_marker(wf)
                if recorded:
                    self.assertTrue(wf.append_outcome(self.attempt_log, {'kind': 'task', 'task': 'T001',
                                                                         'attempt_id': record['id']}))
                raised = []

                def read(fd, n):
                    if not raised and os.fstat(fd).st_ino == log_inode:
                        raised.append(fd)
                        raise OSError(errno.EIO, 'Input/output error')
                    return real_read(fd, n)

                with mock.patch('os.read', read):
                    code, _, err = self.outcome_attempt_cmd('attempt-reconcile')
                self.assertEqual((code, len(raised)), (0, 1))
                self.assertIn('could not read or sync the outcome log', err)
                self.assertTrue(marker.exists())
                self.assertEqual(len(self.outcome_attempt_rows(wf, record['id'])), int(recorded))
                self.outcome_attempt_reconcile()
                self.assertFalse(marker.exists())
                self.assertEqual(len(self.outcome_attempt_rows(wf, record['id'])), 1)
        # The strict numbering read failing after the confirm check: nothing appended either.
        marker, record = self.outcome_attempt_marker(wf)

        def read_bytes(path):
            if path == self.attempt_log:
                raise OSError(errno.EIO, 'Input/output error')
            return real_read_bytes(path)

        with mock.patch.object(Path, 'read_bytes', read_bytes):
            code, _, err = self.outcome_attempt_cmd('attempt-reconcile')
        self.assertEqual(code, 0)
        self.assertIn('could not read or sync the outcome log', err)
        self.assertTrue(marker.exists())
        self.assertEqual(self.outcome_attempt_rows(wf, record['id']), [])

    def test_outcome_attempt_missing_log(self):
        wf = self.outcome_attempt_setup()
        marker, record = self.outcome_attempt_marker(wf)
        self.attempt_log.unlink()  # the seq allocation created it
        self.outcome_attempt_reconcile()
        self.assertEqual([r['attempt_id'] for r in self.outcome_attempt_rows(wf)], [record['id']])
        self.assertFalse(marker.exists())

    def test_outcome_attempt_crashed_row_in_report(self):
        wf = self.outcome_attempt_setup()
        self.outcome_attempt_marker(wf)
        self.outcome_attempt_reconcile()
        report = self.tool('ai-status', '--outcomes').stdout
        self.assertEqual(self.outcome_attempt_category_row(report)[1:7], ['1', '0/1 (0%)', '0', '1', '1.0', '0.0'])

    def outcome_rows(self):
        path =self.base / 'host-state/outcomes.jsonl'
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def task_rows(self):
        return [(r['attempt'], r['result'], r['first_pass']) for r in self.outcome_rows() if r['kind'] == 'task']

    def test_outcome_stopped_attempts_are_logged_and_numbered(self):
        self.ready()
        self.tool('ai-run', '--approved', '--session-timeout', '1', expected=1, MOCK_CLAUDE='timeout')
        self.run_cmd(['git', 'clean', '-fdq'])
        self.commit('reconcile timeout')
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='error')
        self.commit('reconcile error')
        self.tool('ai-run', '--approved')
        self.assertEqual(self.task_rows(), [(1, 'timeout', False), (2, 'error', False), (3, 'done', False)])

    def test_outcome_validation_failure_logs_once(self):
        self.ready()
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nif [[ -e T001.txt ]]; then exit 42; fi\n')
        self.commit('gate fails for invalid fixture implementation')
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='validation-failure')
        self.assertEqual(self.task_rows(), [(1, 'validation_failed', False)])

    def test_outcome_killed_session_is_a_timeout(self):
        self.ready()
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='self-kill')
        self.assertEqual(self.task_rows(), [(1, 'timeout', False)])

    def test_outcome_signal_to_runner_logs_interrupted_once(self):
        self.ready()
        local = self.project / '.ai/local'
        for attempt, sig in ((1, signal.SIGTERM), (2, signal.SIGINT)):
            with self.subTest(signal=sig.name):
                for name in ('mock-session.pid', 'mock-release'):
                    (local / name).unlink(missing_ok=True)
                runner = subprocess.Popen([str(self.project / '.ai/bin/ai-run'), '--approved'], cwd=self.project,
                                          env=dict(self.env, MOCK_CLAUDE='hold'), stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, start_new_session=True,
                                          # a background-launched pipeline inherits SIGINT ignored, which bash cannot trap
                                          preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
                try:
                    for _ in range(200):
                        if (local / 'mock-session.pid').exists() and (local / 'mock-session.pid').read_text():
                            break
                        time.sleep(0.05)
                    else:
                        self.fail('the session never started')
                    runner.send_signal(sig)  # the runner only: GNU timeout leaves the session's group
                    (local / 'mock-release').touch()
                    runner.communicate(timeout=SHORT_TIMEOUT * 2)
                finally:
                    if runner.poll() is None:
                        os.killpg(runner.pid, signal.SIGKILL)
                        runner.communicate()
                    try:
                        os.kill(int((local / 'mock-session.pid').read_text()), signal.SIGKILL)
                    except (OSError, ValueError):
                        pass
                self.assertEqual(runner.returncode, 128 + sig)
                self.assertEqual([r[:2] for r in self.task_rows()][-1], (attempt, 'interrupted'))
                self.assertEqual(len(self.task_rows()), attempt)
                self.commit('reconcile interrupted run')
        self.tool('ai-run', '--approved')
        self.assertEqual([r[:2] for r in self.task_rows()], [(1, 'interrupted'), (2, 'interrupted'), (3, 'done')])

    def test_outcome_malformed_queue_then_retry(self):
        self.ready()
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='bad-format')
        (self.project / '.ai/tasks.md').write_text(task('T001'))
        self.commit('repair the queue')
        self.tool('ai-run', '--approved')
        self.assertEqual(self.task_rows(), [(1, 'error', False), (2, 'done', False)])
        self.assertEqual(self.outcome_rows()[0]['title'], 'broken')

    def test_outcome_no_time_left_logs_nothing(self):
        self.ready()
        slow = self.mock_bin / 'git'
        real = shutil.which('git', path=self.env['PATH'].split(os.pathsep, 1)[1])
        slow.write_text('#!/usr/bin/env bash\n'
                        'marker="$MOCK_STATE_DIR/slow-once"\n'
                        'if [[ -e .ai/local/approved-gate.sha256 && ! -e "$marker" ]]; then touch "$marker"; sleep 2; fi\n'
                        f'exec {real} "$@"\n')
        slow.chmod(0o755)
        result = self.tool('ai-run', '--approved', '--run-timeout', '1', expected=1)
        # The limit can be reached in dependency setup ("... not run: run time limit reached.") or later.
        self.assertIn('run time limit', result.stderr.lower())
        self.assertEqual(self.outcome_rows(), [])
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())

    def test_outcome_triage_runs_log_no_task_outcome(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-always')
        self.commit('record review')
        self.tool('ai-run', '--approved', '--triage', expected=1, MOCK_CLAUDE='limit-far', AI_LIMIT_MAX_WAIT='60')
        self.assertEqual(self.task_rows(), [(1, 'done', True)])
        if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip():
            self.commit('checkpoint the interrupted triage')
        self.tool('ai-run', '--approved', '--triage')
        self.assertEqual(self.task_rows(), [(1, 'done', True)])

    def test_outcome_limit_pause_stays_in_one_attempt(self):
        self.ready()
        nap = self.mock_bin / 'nap'
        nap.write_text('#!/usr/bin/env bash\nsleep 2\n')
        nap.chmod(0o755)
        self.tool('ai-run', '--approved', MOCK_CLAUDE='limit-once', AI_SLEEP=str(nap))
        rows = [r for r in self.outcome_rows() if r['kind'] == 'task']
        self.assertEqual([(r['attempt'], r['result'], r['first_pass']) for r in rows], [(1, 'done', True)])
        self.assertGreaterEqual(rows[0]['seconds'], 2)  # the wait belongs to the original attempt

    def test_runner_logs_blocked_and_failed_validation_attempts(self):
        self.ready(task('T001') + task('T002'))
        self.tool('ai-run', '--approved', expected=None, MOCK_CLAUDE='blocked-first')
        lines = [json.loads(x) for x in (self.base / 'host-state/outcomes.jsonl').read_text().splitlines()]
        self.assertEqual([(r['task'], r['result']) for r in lines], [('T001', 'blocked'), ('T002', 'done')])
        self.assertFalse(lines[0]['first_pass'])
        empty = self.tool('ai-status', '--outcomes', str(self.base / 'missing.jsonl')).stdout
        self.assertIn('No outcomes recorded yet', empty)

    # ---------------------------------------------------------------- killed runner (CU-5, T004)
    def crash_attempts_dir(self):
        return Path(self.helper('outcome', 'attempt-dir').stdout.strip())

    def crash_markers(self):
        directory = self.crash_attempts_dir()
        return sorted(directory.glob('*.json')) if directory.exists() else []

    def crash_reap_killed(self):
        """SIGKILL every process the sigkill-runner mock recorded (still the same program), and
        wait until they are gone: the session's `timeout` inherits the checkout lock."""
        pids = self.base / 'sigkill-runner.pids'
        if not pids.exists():
            return
        for pid in {int(x) for x in pids.read_text().split()}:
            with contextlib.suppress(OSError):
                if any(name in Path(f'/proc/{pid}/cmdline').read_bytes() for name in (b'ai-run', b'timeout')):
                    os.kill(pid, signal.SIGKILL)
            for _ in range(200):
                if not Path(f'/proc/{pid}').exists() or \
                        Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                    break
                time.sleep(0.05)

    def test_outcome_crash_killed_runner_logged_once_at_next_start(self):
        self.ready()
        self.addCleanup(self.crash_reap_killed)
        killed = self.tool('ai-run', '--approved', expected=None, MOCK_CLAUDE='sigkill-runner')
        self.assertIn(killed.returncode, (-9, 137), killed.stdout + killed.stderr)
        self.crash_reap_killed()
        self.assertEqual(self.task_rows(), [])
        [marker] = self.crash_markers()
        attempt_id = json.loads(marker.read_text())['id']
        self.assertIn('.ai/state.md', self.run_cmd(['git', 'status', '--porcelain']).stdout)
        refused = self.tool('ai-run', '--approved', expected=1)
        self.assertIn('Start from a clean checkpoint', refused.stderr)
        self.assertIn('logged a crashed attempt of T001', refused.stderr)
        self.assertEqual((self.project / '.ai/local/mock-invocations').read_text().count('call'), 1)
        [crashed] = [r for r in self.outcome_rows() if r['kind'] == 'task']
        self.assertEqual((crashed['result'], crashed['attempt'], crashed['attempt_id'], crashed['seconds']),
                         ('crashed', 1, attempt_id, None))
        self.assertEqual(self.crash_markers(), [])
        self.commit('checkpoint the killed run')
        self.tool('ai-run', '--approved')
        rows = [r for r in self.outcome_rows() if r['kind'] == 'task']
        self.assertEqual([(r['result'], r['attempt']) for r in rows], [('crashed', 1), ('done', 2)])
        self.assertRegex(rows[1]['attempt_id'], r'^[0-9a-f]{16}$')
        self.assertNotEqual(rows[1]['attempt_id'], attempt_id)
        self.assertEqual(self.crash_markers(), [])
        self.tool('ai-run', '--approved', expected=None)
        self.assertEqual(self.outcome_rows(), rows)

    def test_outcome_crash_normal_stops_carry_attempt_id_and_leave_no_marker(self):
        self.ready()
        self.tool('ai-run', '--approved', '--session-timeout', '1', expected=1, MOCK_CLAUDE='timeout')
        self.assertEqual(self.crash_markers(), [])
        self.run_cmd(['git', 'clean', '-fdq'])
        self.commit('reconcile timeout')
        self.tool('ai-run', '--approved', expected=1, MOCK_CLAUDE='error')
        self.assertEqual(self.crash_markers(), [])
        self.commit('reconcile error')
        self.tool('ai-run', '--approved')
        rows = [r for r in self.outcome_rows() if r['kind'] == 'task']
        self.assertEqual([r['result'] for r in rows], ['timeout', 'error', 'done'])
        ids = [r['attempt_id'] for r in rows]
        self.assertTrue(all(re.match(r'^[0-9a-f]{16}$', i) for i in ids), ids)
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(self.crash_markers(), [])

    def test_outcome_crash_failed_attempt_open_keeps_the_printed_id(self):
        if os.geteuid() == 0:
            self.skipTest('root ignores directory permissions')
        self.ready()
        directory = self.crash_attempts_dir()
        directory.mkdir(parents=True)
        directory.chmod(0o500)
        self.addCleanup(directory.chmod, 0o700)
        result = self.tool('ai-run', '--approved')
        [row] = [r for r in self.outcome_rows() if r['kind'] == 'task']
        self.assertEqual(row['result'], 'done')
        self.assertRegex(row['attempt_id'], r'^[0-9a-f]{16}$')
        self.assertNotIn('crashed', result.stdout + result.stderr)
        self.tool('ai-run', '--approved', expected=None)
        self.assertEqual([r for r in self.outcome_rows() if r['kind'] == 'task'], [row])

    def test_outcome_crash_gate_change_leaves_no_marker(self):
        self.ready()
        result = self.tool('ai-run', '--approved', expected=1,
                           MOCK_CLAUDE='tamper', MOCK_TAMPER_PATH='.ai/prompts/implement.md')
        self.assertIn('Approved workflow gate changed', result.stderr)
        self.assertEqual(self.outcome_rows(), [])
        self.assertEqual(self.crash_markers(), [])
        self.run_cmd(['git', 'checkout', 'HEAD~1', '--', '.ai/prompts/implement.md'])
        (self.project / '.ai/tasks.md').write_text(task('T001'))
        self.commit('human restores the inspected gate')
        restart = self.tool('ai-run', '--approved')
        self.assertNotIn('crashed', restart.stderr)
        self.assertEqual(self.task_rows(), [(1, 'done', True)])

    def test_watchdog_auto_diagnosis_falls_back_to_claude_sonnet(self):
        self.setup_project()
        self.watchdog_stalled('implementing')
        (self.mock_bin / 'codex').write_text('#!/usr/bin/env bash\necho "usage limit"; exit 1\n')
        (self.mock_bin / 'claude').write_text('#!/usr/bin/env python3\nimport os, sys\n'
                                              'a = sys.argv[1:]\n'
                                              "open(os.environ['MOCK_STATE_DIR'] + '/diag-model', 'w').write(a[a.index('--model')+1])\n"
                                              "print('Claude: the runner was killed.')\n")
        self.watchdog('--diagnose', expected=1)
        self.assertEqual((self.base / 'diag-model').read_text(), 'claude-sonnet-5-5')
        self.assertIn('Claude: the runner was killed.', self.notifications())

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

    # ------------------------------------------------------------- review format retry (T009)
    def reset_review_fixture(self):
        """Undo one review attempt: reviewer call counters, uncommitted records, stray files."""
        for name in ('codex-calls', 'codex-plan-calls', 'codex-prompts.log', 'claude-review-args.log',
                     'claude-review-prompts.log', 'notifications.log'):
            (self.base / name).unlink(missing_ok=True)
        (self.project / 'unexpected.txt').unlink(missing_ok=True)
        self.run_cmd(['git', 'checkout', '--', '.ai'])
        self.run_cmd(['git', 'clean', '-fdq', '--', '.ai/reviews'])

    def format_retry_lines(self):
        return [line for line in (self.project / '.ai/run-log.md').read_text().splitlines()
                if 'review format retry' in line]

    def codex_calls(self, name='codex-calls'):
        path = self.base / name
        return path.read_text().count('call') if path.exists() else 0

    def test_format_retry_code_review_once_then_publish_or_stop(self):
        self.ready()
        self.tool('ai-run', '--approved')
        original = (self.project / '.ai/reviews/current.md').read_bytes()
        cases = [  # MOCK_CODEX, exit code, Codex calls, run-log outcome (None: no retry)
            ('malformed,success', 0, 2, 'published'),
            ('empty,success', 0, 2, 'published'),
            ('counts-lie,success', 0, 2, 'published'),
            ('success', 0, 1, None),
            ('malformed', 1, 2, 'stopped again, prior review preserved'),
            ('empty', 1, 2, 'stopped again, prior review preserved'),
            ('mutates', 1, 1, None),
            ('error', 1, 1, None),
            ('malformed,mutates', 1, 2, 'stopped again, prior review preserved'),
            ('malformed,error', 1, 2, 'stopped again, prior review preserved'),
        ]
        for mode, code, calls, outcome in cases:
            with self.subTest(mode=mode):
                self.reset_review_fixture()
                result = self.tool('ai-review', '--base', 'main', expected=code, MOCK_CODEX=mode, AI_SUPERVISE='1')
                self.assertEqual(self.codex_calls(), calls)
                lines = self.format_retry_lines()
                if outcome is None:
                    self.assertEqual(lines, [])
                    self.assertNotIn('Review format retry', self.notifications())
                else:
                    self.assertEqual(len(lines), 1, lines)
                    self.assertIn(f'review format retry (code): {outcome}', lines[0])
                    first = re.search(r'first report (\.ai/local/review-\w+\.md)', lines[0]).group(1)
                    self.assertTrue((self.project / first).exists())  # the first report is kept
                    self.assertIn('🔁 Review format retry (code): ', self.notifications())
                    prompts = (self.base / 'codex-prompts.log').read_text().split('=== PROMPT ===')
                    self.assertNotIn('FORMAT ERROR', prompts[1])
                    self.assertIn('FORMAT ERROR: ', prompts[2])
                    self.assertIn('Return the full report again in the required structure.', prompts[2])
                if code:
                    self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)
                else:
                    self.helper('review-info')
        # The second call mutating the checkout is still an integrity stop.
        self.reset_review_fixture()
        result = self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX='malformed,mutates', AI_SUPERVISE='1')
        self.assertIn('Checkout changed during review', result.stderr)
        self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)
        self.assertIn('Review is missing Overall verdict:', self.format_retry_lines()[0])
        # The counts-lie is a format error: its message reaches the reviewer.
        self.reset_review_fixture()
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='counts-lie,success', AI_SUPERVISE='1')
        self.assertIn('FORMAT ERROR: Review lists MAJOR findings but counts MAJOR=0',
                      (self.base / 'codex-prompts.log').read_text())

    def test_format_retry_off_without_supervision(self):
        self.ready()
        self.tool('ai-run', '--approved')
        original = (self.project / '.ai/reviews/current.md').read_bytes()
        for mode, message in (('malformed,success', 'Review is missing Overall verdict:'),
                              ('empty,success', 'The reviewer produced no review')):
            with self.subTest(mode=mode):
                self.reset_review_fixture()
                result = self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX=mode, AI_SUPERVISE='0')
                self.assertIn(message, result.stderr)
                self.assertEqual(self.codex_calls(), 1)
                self.assertEqual(self.format_retry_lines(), [])
                self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)
        self.reset_review_fixture()
        self.tool('ai-review', '--plan', expected=1, MOCK_CODEX_PLAN_FORMAT='malformed,ok', AI_SUPERVISE='0')
        self.assertEqual(self.codex_calls('codex-plan-calls'), 1)
        self.reset_review_fixture()
        self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX_LIMIT='1', MOCK_CLAUDE_REVIEW='empty,success',
                  AI_SUPERVISE='0')
        self.assertEqual(len(self.claude_review_args()), 1)

    def test_format_retry_claude_fallback_reviewer(self):
        self.ready()
        self.tool('ai-run', '--approved')
        original = (self.project / '.ai/reviews/current.md').read_bytes()
        for mode, code in (('malformed,success', 0), ('empty,success', 0), ('empty', 1), ('malformed', 1)):
            with self.subTest(mode=mode):
                self.reset_review_fixture()
                self.tool('ai-review', '--base', 'main', expected=code, MOCK_CODEX_LIMIT='1',
                          MOCK_CLAUDE_REVIEW=mode, AI_SUPERVISE='1')
                self.assertEqual(len(self.claude_review_args()), 2)
                prompts = (self.base / 'claude-review-prompts.log').read_text().split('\n=====\n')
                self.assertIn('FORMAT ERROR: ', prompts[1])
                self.assertEqual(len(self.format_retry_lines()), 1)
                if code:
                    self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)
                else:
                    review = (self.project / '.ai/reviews/current.md').read_text()
                    self.assertIn('> **Reviewer: Claude fallback (claude-opus-5-5', review)
                    self.helper('review-info')
        # A plan review on the Claude fallback, too.
        self.reset_review_fixture()
        self.tool('ai-review', '--plan', MOCK_CODEX_LIMIT='1', MOCK_CLAUDE_REVIEW='empty,success', AI_SUPERVISE='1')
        self.assertEqual(len(self.claude_review_args()), 2)
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')

    def test_format_retry_after_claude_fallback_attributes_the_codex_review(self):
        self.ready()
        self.tool('ai-run', '--approved')
        # Call 1: Codex at its limit -> Claude fallback, malformed; the retry: Codex is back.
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='limit-once', MOCK_CLAUDE_REVIEW='malformed', AI_SUPERVISE='1')
        self.assertEqual(len(self.claude_review_args()), 1)
        self.assertEqual(self.codex_calls(), 2)
        review = (self.project / '.ai/reviews/current.md').read_text()
        self.assertNotIn('Reviewer:', review)
        self.assertFalse((self.project / '.ai/reviews/fallback-log.md').exists())
        outcome = json.loads((self.base / 'host-state/outcomes.jsonl').read_text().splitlines()[-1])
        self.assertEqual((outcome['reviewer'], outcome['mode']), ('codex', 'code'))
        self.helper('review-info')

    def test_format_retry_plan_review_by_hand(self):
        self.ready()
        plan = self.project / '.ai/reviews/plan.md'
        cases = [  # MOCK_CODEX_PLAN_FORMAT, exit code, Codex plan calls, run-log outcome
            ('malformed,ok', 0, 2, 'published'),
            ('empty,ok', 0, 2, 'published'),
            ('counts-lie,ok', 0, 2, 'published'),
            ('ok', 0, 1, None),
            ('malformed', 1, 2, 'stopped again, prior review preserved'),
            ('mutates', 1, 1, None),
            ('error', 1, 1, None),
            ('malformed,mutates', 1, 2, 'stopped again, prior review preserved'),
        ]
        for number, (mode, code, calls, outcome) in enumerate(cases):
            with self.subTest(mode=mode):
                self.reset_review_fixture()
                (self.project / 'src.txt').write_text(f'source {number}\n')  # a new plan digest each time
                self.commit(f'source {number}')
                before = plan.read_bytes() if plan.exists() else None
                logged = len(self.format_retry_lines())  # earlier lines are committed
                self.tool('ai-review', '--plan', expected=code, MOCK_CODEX_PLAN_FORMAT=mode, AI_SUPERVISE='1')
                self.assertEqual(self.codex_calls('codex-plan-calls'), calls)
                # The checkout was clean for both reviewer calls (no run-log line in between).
                self.assertEqual(set((self.base / 'codex-plan-status').read_text().split('\n')[-calls - 1:-1]),
                                 {'clean'})
                lines = self.format_retry_lines()[logged:]
                if outcome:
                    self.assertEqual(len(lines), 1, lines)
                    self.assertIn(f'review format retry (plan): {outcome}', lines[0])
                    self.assertIn('🔁 Review format retry (plan): ', self.notifications())
                else:
                    self.assertEqual(lines, [])
                if code:
                    self.assertEqual(plan.read_bytes() if plan.exists() else None, before)
                    (self.base / 'codex-plan-status').unlink()
                    continue
                # Published and recorded by hand: the run-log line is in the record commit.
                self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
                self.assertEqual(self.run_cmd(['git', 'log', '-1', '--format=%s']).stdout.strip(),
                                 'chore(ai): record plan review')
                if outcome:
                    self.assertIn('.ai/run-log.md', self.run_cmd(['git', 'show', '--name-only', '--format=']).stdout)
                self.assertTrue(self.helper('plan-review-info').stdout.startswith('current'))
                (self.base / 'codex-plan-status').unlink()

    def test_format_retry_pipeline_commits_the_run_log_line_with_each_review(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', AI_SUPERVISE='1',
                  MOCK_CODEX_PLAN_FORMAT='malformed,ok', MOCK_CODEX='empty,success')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.assertEqual((self.codex_calls('codex-plan-calls'), self.codex_calls()), (2, 2))
        for subject, mode in (('chore(ai): record plan review', 'plan'),
                              ('chore(ai): record independent review', 'code')):
            sha = self.run_cmd(['git', 'log', '-1', '--format=%H', '--fixed-strings', f'--grep={subject}']).stdout.strip()
            shown = self.run_cmd(['git', 'show', sha, '--', '.ai/run-log.md']).stdout
            self.assertIn(f'review format retry ({mode}): published', shown)
            self.assertIn(f'🔁 Review format retry ({mode}): ', self.notifications())

    def test_format_retry_stops_when_the_checkout_changes_between_the_calls(self):
        # Review M2: the notification between the calls commits (or leaves) a change; the
        # retry must not adopt it as a new baseline.
        self.ready()
        self.tool('ai-run', '--approved')
        notify = self.base / 'notify-mutate'
        notify.write_text(f'printf "%s\\n" "$1" >> "{self.notify_log}"\n'
                          'case "$1" in *"Review format retry"*)\n'
                          '  printf "x\\n" >> unexpected.txt\n'
                          '  [ "$MUTATE" = commit ] && { git add -- unexpected.txt; git commit -qm moved; }\n'
                          'esac\n'
                          'exit 0\n')
        hook = dict(AI_NOTIFY_CMD=f'bash "{notify}" "$1"', AI_SUPERVISE='1')
        plan = self.project / '.ai/reviews/plan.md'
        # Code reviews first (dirty before commit): a committed source change voids the validation stamp.
        for mutate in ('dirty', 'commit'):
            with self.subTest(review='code', mutate=mutate):
                self.reset_review_fixture()
                original = (self.project / '.ai/reviews/current.md').read_bytes()
                logged = len(self.format_retry_lines())
                result = self.tool('ai-review', '--base', 'main', expected=1, MOCK_CODEX='malformed,success',
                                   MUTATE=mutate, **hook)
                self.assertIn('Checkout changed between the review and its format retry', result.stderr)
                self.assertEqual(self.codex_calls(), 1)  # no second reviewer call
                self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), original)
                lines = self.format_retry_lines()[logged:]
                self.assertEqual(len(lines), 1, lines)
                self.assertIn('review format retry (code): stopped, checkout changed between the calls', lines[0])
        for number, mutate in enumerate(('dirty', 'commit')):
            with self.subTest(review='plan', mutate=mutate):
                self.reset_review_fixture()
                (self.project / 'src.txt').write_text(f'moved source {number}\n')  # a new plan digest
                self.commit(f'moved source {number}')
                before = plan.read_bytes() if plan.exists() else None
                logged = len(self.format_retry_lines())
                result = self.tool('ai-review', '--plan', expected=1, MOCK_CODEX_PLAN_FORMAT='malformed,ok',
                                   MUTATE=mutate, **hook)
                self.assertIn('Checkout changed between the review and its format retry', result.stderr)
                self.assertEqual(self.codex_calls('codex-plan-calls'), 1)
                self.assertEqual(plan.read_bytes() if plan.exists() else None, before)
                lines = self.format_retry_lines()[logged:]
                self.assertEqual(len(lines), 1, lines)
                self.assertIn('review format retry (plan): stopped, checkout changed between the calls', lines[0])

    def test_format_retry_never_for_a_malformed_recheck(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
                              '| M2 | rejected | out of scope | none |\n'])
        self.tool('ai-review', '--recheck', MOCK_RECHECK='M1 withdrawn', AI_SUPERVISE='1')
        self.assertEqual((self.base / 'codex-recheck-calls').read_text().count('reviewed HEAD='), 1)
        answers = self.helper('recheck-verify').stdout
        self.assertEqual(answers.count('\tupheld\t'), 2)
        self.assertEqual(self.format_retry_lines(), [])

    def test_review_format_check_helper_matches_publish(self):
        report = self.base / 'report.md'
        good = ('Overall verdict: ok\nFinding counts: BLOCKER=0 MAJOR=0 MINOR=0\n'
                '## BLOCKER findings\nNone.\n## MAJOR findings\nNone.\n## MINOR findings\nNone.\n')
        report.write_text(good)
        self.helper('review-format-check', 'code', str(report))
        self.helper('review-format-check', 'plan', str(report))
        report.write_text(good.replace('Overall verdict: ok\n', ''))
        self.helper('review-format-check', 'plan', str(report))
        result = self.helper('review-format-check', 'code', str(report), expected=2)
        self.assertEqual(result.stdout.strip(), 'Review is missing Overall verdict:')
        report.write_text('\n')
        self.assertIn('empty report', self.helper('review-format-check', 'plan', str(report), expected=2).stdout)
        self.helper('review-format-check', 'code', str(self.base / 'missing.md'), expected=1)
        self.helper('review-format-check', 'recheck', str(report), expected=1)

    def publish_report(self, text, plan=False, expected=0):
        report = self.base / 'format-report.md'
        report.write_text(text)
        if plan:
            digest = self.helper('plan-digest').stdout.strip()
            return self.helper('publish-plan-review', str(report), digest, expected=expected)
        return self.helper('publish-review', str(report), 'a' * 40, 'b' * 40, expected=expected)

    def test_review_format_missing_zero_count_sections_are_accepted(self):
        self.ready()
        self.publish_report('# Review\nOverall verdict: one major\nFinding counts: BLOCKER=0 MAJOR=1 MINOR=0\n'
                            '## MAJOR findings\n- M1: a real defect.\n')
        self.assertEqual(self.helper('review-info').stdout.split(), ['a' * 40, '0', '1', '0'])
        self.publish_report('# Plan review\nFinding counts: BLOCKER=0 MAJOR=1 MINOR=0\n'
                            '## BLOCKER findings\nNone.\n## MAJOR findings\n- P1: T001 has no test.\n', plan=True)
        self.assertEqual(self.helper('plan-review-info').stdout.split(), ['current', '0', '1', '0'])

    def test_review_format_count_mismatches_are_still_rejected(self):
        self.ready()
        self.publish_report('# Review\nOverall verdict: ok\nFinding counts: BLOCKER=0 MAJOR=0 MINOR=0\n')
        self.publish_report('# Plan review\nFinding counts: BLOCKER=0 MAJOR=0 MINOR=0\n', plan=True)
        current = (self.project / '.ai/reviews/current.md').read_bytes()
        plan = (self.project / '.ai/reviews/plan.md').read_bytes()
        counts = 'Finding counts: BLOCKER=0 MAJOR={} MINOR={}\n'
        cases = {
            'minor section missing': counts.format(0, 1),
            'minor section only none': counts.format(0, 1) + '## MINOR findings\nNone.\n',
            'major listed but counted 0': counts.format(0, 0) + '## MAJOR findings\n- M1: a defect.\n',
            'major count above ids': counts.format(2, 0) + '## MAJOR findings\n- M1: a defect.\n',
            'no counts line': '## MAJOR findings\nNone.\n',
            'two counts lines': counts.format(0, 0) + counts.format(0, 0),
        }
        for name, body in cases.items():
            for is_plan in (False, True):
                with self.subTest(case=name, plan=is_plan):
                    self.publish_report('# Review\nOverall verdict: ok\n' + body, plan=is_plan, expected=1)
                    self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), current)
                    self.assertEqual((self.project / '.ai/reviews/plan.md').read_bytes(), plan)

    def test_review_format_verdict_heading_is_accepted(self):
        self.setup_project()
        tail = 'Finding counts: BLOCKER=0 MAJOR=0 MINOR=0\n'
        for heading in ('## Overall verdict', '## Overall verdict:', '### Overall verdict'):
            with self.subTest(heading=heading):
                self.publish_report(f'# Review\n{heading}\n\n<!-- note -->\nApprove with two minor notes\n\n'
                                    '## Findings\n' + tail)
                self.assertEqual(self.helper('review-info').stdout.split()[1:], ['0', '0', '0'])
                body = self.helper('pr-body', '1', '0').stdout
                self.assertIn('Verdict: Approve with two minor notes.', body)

    def test_review_format_missing_or_empty_verdict_is_rejected(self):
        self.setup_project()
        self.publish_report('# Review\nOverall verdict: ok\nFinding counts: BLOCKER=0 MAJOR=0 MINOR=0\n')
        current = (self.project / '.ai/reviews/current.md').read_bytes()
        tail = 'Finding counts: BLOCKER=0 MAJOR=0 MINOR=0\n'
        for name, text in (('no verdict', '# Review\n' + tail),
                           ('empty heading', '# Review\n## Overall verdict\n\n<!-- x -->\n## Counts\n' + tail),
                           ('empty heading at end', '# Review\n' + tail + '## Overall verdict\n\n'),
                           ('empty line', '# Review\nOverall verdict:\n' + tail)):
            with self.subTest(case=name):
                result = self.publish_report(text, expected=1)
                self.assertIn('missing Overall verdict', result.stderr)
                self.assertEqual((self.project / '.ai/reviews/current.md').read_bytes(), current)

    def test_review_format_verdict_heading_through_ai_review(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='verdict-heading')
        report = (self.project / '.ai/reviews/current.md').read_text()
        self.assertIn('Approve with two minor notes', report)
        self.assertNotIn('## MINOR findings', report)
        self.assertEqual(self.helper('review-info').stdout.split()[1:], ['0', '0', '0'])

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

    # ---------------------------------------------------------------- lock owner hint (FL-19)
    def lock_owner(self, name, through_bash=False):
        """A process holding the checkout lock with pipeline.active naming it: argv
        `<name> 30` (exec -a), or `bash …/<name>` when through_bash."""
        import time
        script = self.base / 'owner-bin' / name
        script.parent.mkdir(exist_ok=True)
        (self.project / '.ai/local').mkdir(exist_ok=True)
        tail = 'sleep 30 9>&-\n' if through_bash else f'exec -a {name} sleep 30\n'
        script.write_text('#!/usr/bin/env bash\nexec 9>.ai/local/workflow.lock\nflock 9\n'
                          'printf "%s\\n" $$ > .ai/local/pipeline.active\n' + tail)
        script.chmod(0o755)
        command = ['bash', str(script)] if through_bash else [str(script)]
        process = subprocess.Popen(command, cwd=self.project, env=self.env)
        self.addCleanup(lambda: (process.kill(), process.wait()) if process.poll() is None else None)
        marker = self.project / '.ai/local/pipeline.active'
        for _ in range(500):
            cmdline = Path(f'/proc/{process.pid}/cmdline').read_bytes()
            ready = marker.exists() and marker.read_text() == f'{process.pid}\n'
            if ready and (through_bash or cmdline.startswith(name.encode() + b'\0')):
                return process
            time.sleep(0.01)
        self.fail(f'lock owner {name} did not start')

    def rejected(self, name, *args):
        """Run a tool that must be refused by the lock: exit 1 within SHORT_TIMEOUT (10 s unscaled)."""
        return self.run_cmd([str(self.project / '.ai/bin' / name), *args], expected=1, timeout=SHORT_TIMEOUT)

    def test_lock_owner_recovery_hint_changes_nothing(self):
        self.ready()
        local = self.project / '.ai/local'
        local.mkdir(exist_ok=True)
        owner = self.lock_owner('ai-recover')
        (local / 'last-error').write_text('Session limit reached; 16 sessions used.\n')
        (local / 'observation.json').write_text('{"state": "recovering", "attempt": "1/2"}\n')
        (local / 'notifications.log').write_text('')
        names = ('last-error', 'pipeline.active', 'observation.json', 'notifications.log')
        before = {name: (local / name).read_bytes() for name in names}
        result = self.rejected('ai-pipeline', '--approved', '--sessions', '20')
        self.assertIn('Another runner/reviewer owns this checkout', result.stderr)
        self.assertIn(f'auto-recovery (PID {owner.pid})', result.stderr)
        self.assertIn(f'kill {owner.pid}', result.stderr)
        self.assertEqual({name: (local / name).read_bytes() for name in names}, before)
        self.assertFalse((local / 'last-error.notified').exists())
        self.assertEqual(self.notifications(), '')
        self.assertFalse((local / 'mock-invocations').exists())
        self.assertFalse((self.base / 'codex-calls').exists())

    def test_lock_owner_recovery_through_bash_and_other_tools(self):
        self.ready()
        owner = self.lock_owner('ai-recover', through_bash=True)
        for name, args in (('ai-pipeline', ('--approved',)), ('ai-run', ('--approved',)),
                           ('ai-review', ('--base', 'main'))):
            result = self.rejected(name, *args)
            self.assertIn('Another runner/reviewer owns this checkout: auto-recovery '
                          f'(PID {owner.pid})', result.stderr, name)
            self.assertIn(f'kill {owner.pid}', result.stderr, name)
        self.assertFalse((self.project / '.ai/local/last-error').exists())
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())

    def test_lock_owner_pipeline_hint(self):
        self.ready()
        owner = self.lock_owner('ai-pipeline')
        result = self.rejected('ai-pipeline', '--approved')
        self.assertIn(f'Another runner/reviewer owns this checkout: a pipeline (PID {owner.pid}) '
                      'is running here', result.stderr)
        self.assertNotIn('auto-recovery', result.stderr)
        self.assertFalse((self.project / '.ai/local/last-error').exists())

    def test_lock_owner_unknown_owner_gets_the_plain_message(self):
        import fcntl
        self.ready()
        local = self.project / '.ai/local'
        local.mkdir(exist_ok=True)
        marker = local / 'pipeline.active'
        dead = subprocess.Popen(['true'])
        dead.wait()
        runner = self.watchdog_runner(name='ai-pipeline')  # a runner the marker must not reach
        target = self.base / 'elsewhere-marker'
        target.write_text(f'{runner.pid}\n')
        cases = {'no marker': None, 'dead PID': f'{dead.pid}\n', 'non-runner': f'{os.getpid()}\n',
                 'garbage': 'ai-recover\n', 'fifo': os.mkfifo, 'symlink': target}
        with (local / 'workflow.lock').open('w') as file:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for label, plant in cases.items():
                if marker.exists() or marker.is_symlink():
                    marker.unlink()
                if isinstance(plant, str):
                    marker.write_text(plant)
                elif isinstance(plant, Path):
                    marker.symlink_to(plant)
                elif plant is not None:
                    plant(marker)
                result = self.rejected('ai-pipeline', '--approved')
                # ai_root refuses any symlink under .ai before the lock; the hint's own guard
                # is covered by test_lock_owner_hint_never_follows_a_symlink_or_fifo.
                expected = ('Error: Unsafe symlink in workflow path' if label == 'symlink' else
                            'Error: Another runner/reviewer owns this checkout.\n')
                self.assertIn(expected, result.stderr, label)
                self.assertNotIn('PID', result.stderr, label)
                self.assertFalse((local / 'last-error').exists(), label)
        self.assertEqual(self.notifications(), '')
        self.assertFalse((local / 'mock-invocations').exists())

    def test_lock_owner_hint_never_follows_a_symlink_or_fifo(self):
        self.ready()
        owner = self.lock_owner('ai-recover')
        local = self.project / '.ai/local'
        marker = local / 'pipeline.active'
        target = self.base / 'elsewhere-marker'
        target.write_text(f'{owner.pid}\n')
        hint = ['bash', '-c', 'source "$1"; ai_lock_owner_hint', '_',
                str(self.project / '.ai/bin/lib/common.sh')]
        self.assertIn(f'(PID {owner.pid})', self.run_cmd(hint, timeout=SHORT_TIMEOUT).stdout)
        for label, plant in (('symlink', lambda: marker.symlink_to(target)),
                             ('fifo', lambda: os.mkfifo(marker))):
            marker.unlink()
            plant()
            self.assertEqual(self.run_cmd(hint, timeout=SHORT_TIMEOUT).stdout, '.', label)

    def test_lock_owner_quiet_recovery_rejection_unchanged(self):
        self.ready()
        self.lock_owner('ai-recover')
        result = self.rejected('ai-recover', '--stage', 'implementation')
        self.assertEqual(result.stderr, 'Another runner owns this checkout; nothing to recover.\n')

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

    # ---------------------------------------------------------------- review base (FL-15)
    def git_out(self, *args):
        return self.run_cmd(['git', *args]).stdout.strip()

    def origin_with_main(self):
        self.ready()
        origin = self.add_origin()
        self.run_cmd(['git', 'push', '-q', 'origin', 'main'])
        self.run_cmd(['git', 'fetch', '-q', 'origin'])
        return origin

    def commit_on(self, parent, message):
        return self.git_out('commit-tree', f'{parent}^{{tree}}', '-p', parent, '-m', message)

    def advance_origin_main(self):
        """Moves origin's main one commit ahead without touching the local main branch."""
        sha = self.commit_on('origin/main', 'merged elsewhere')
        self.run_cmd(['git', 'push', '-q', 'origin', f'{sha}:refs/heads/main'])
        self.run_cmd(['git', 'fetch', '-q', 'origin'])
        return sha

    def advance_local_main(self):
        sha = self.commit_on('main', 'local only')
        self.run_cmd(['git', 'branch', '-f', 'main', sha])
        return sha

    def assert_reviewed_against(self, result, ref, sha, behind=False):
        short = self.git_out('rev-parse', '--short', sha)
        line = f'Review base: {ref} at {short}' + (' (local main is behind)' if behind else '')
        self.assertIn(line + '\n', result.stdout)
        header = re.search(r'merge-base ([0-9a-f]{40})', (self.project / '.ai/reviews/current.md').read_text())
        self.assertEqual(header.group(1), sha)
        prompts = (self.base / 'codex-prompts.log').read_text()
        self.assertIn(f'supplied base={sha}; merge-base={sha}.', prompts)

    def test_review_base_origin_ahead_of_local(self):
        self.origin_with_main()
        sha = self.advance_origin_main()
        self.run_cmd(['git', 'merge', '-q', '--no-edit', sha])
        local = self.git_out('rev-parse', 'main')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assert_reviewed_against(result, 'origin/main', sha, behind=True)
        self.assertNotIn(f'merge-base={local}', (self.base / 'codex-prompts.log').read_text())

    def test_review_base_origin_ahead_pr_still_targets_main(self):
        self.origin_with_main()
        sha = self.advance_origin_main()
        self.run_cmd(['git', 'merge', '-q', '--no-edit', sha])
        result = self.tool('ai-pipeline', '--approved', '--base', 'main')
        self.assert_reviewed_against(result, 'origin/main', sha, behind=True)
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']][0]
        self.assertEqual(create[create.index('--base') + 1], 'main')

    def test_review_base_equal_to_origin(self):
        self.origin_with_main()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assert_reviewed_against(result, 'main', self.git_out('rev-parse', 'main'))
        self.assertNotIn('diverged', result.stdout)

    def test_review_base_without_origin_ref(self):
        self.ready()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assert_reviewed_against(result, 'main', self.git_out('rev-parse', 'main'))

    def test_review_base_local_ahead_of_origin(self):
        self.origin_with_main()
        remote = self.git_out('rev-parse', 'origin/main')
        sha = self.advance_local_main()
        self.run_cmd(['git', 'merge', '-q', '--no-edit', sha])
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assert_reviewed_against(result, 'main', sha)
        self.assertNotIn('is behind', result.stdout)
        self.assertNotIn(f'merge-base={remote}', (self.base / 'codex-prompts.log').read_text())

    def test_review_base_diverged_uses_local(self):
        self.origin_with_main()
        self.advance_origin_main()
        sha = self.advance_local_main()
        self.run_cmd(['git', 'merge', '-q', '--no-edit', sha])
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('Local main and origin/main have diverged; reviewing against local main.', result.stdout)
        self.assert_reviewed_against(result, 'main', sha)

    def test_review_base_explicit_sha(self):
        self.origin_with_main()
        self.advance_origin_main()
        sha = self.git_out('rev-parse', 'main')
        result = self.tool('ai-pipeline', '--approved', '--base', sha, '--no-pr')
        self.assert_reviewed_against(result, sha, sha)

    # ---------------------------------------------------------------- base moved past the branch (FL-17)
    def base_moved_message(self, ref, sha):
        short = self.git_out('rev-parse', '--short', sha)
        return f'Review base {ref} ({short}) moved past the branch; merge it into feature/test and rerun ai-pipeline'

    def test_base_moved_stops_before_any_agent(self):
        self.origin_with_main()
        sha = self.advance_origin_main()
        message = self.base_moved_message('origin/main', sha)
        for base in ('main', 'origin/main'):
            with self.subTest(base=base):
                result = self.tool('ai-pipeline', '--approved', '--base', base, '--no-pr', expected=1)
                self.assertIn(message, result.stderr)
                self.assertIn('Pipeline stopped during start', result.stderr)
                self.assertIn(message, (self.project / '.ai/local/last-error').read_text())
                self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
                self.assertFalse((self.base / 'codex-prompts.log').exists())
        notes = self.notifications()
        self.assertIn('⛔ STOPPED, needs you', notes)
        self.assertIn('moved past the branch; merge it', notes)
        # Merging the base is the fix: the rerun proceeds normally.
        self.run_cmd(['git', 'merge', '-q', '--no-edit', 'origin/main'])
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('Pipeline complete (no PR requested).', result.stdout)
        self.assertEqual(self.helper('tasks', 'status', 'T001').stdout.strip(), 'DONE')

    def test_base_moved_recovery_escalates_without_claude(self):
        self.origin_with_main()
        sha = self.advance_origin_main()
        message = self.base_moved_message('origin/main', sha)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn(message, result.stderr)
        self.assertIn('escalated to the human: the review base moved past the branch.', result.stderr)
        self.assertEqual(self.recovery_calls(), [])
        self.assertFalse((self.project / '.ai/local/mock-invocations').exists())
        self.assertEqual((self.project / '.ai/local/last-error').read_text().strip(), message)
        notes = self.notifications()
        self.assertIn('⛔ STOPPED, needs you', notes)
        self.assertIn(f'Review base origin/main ({self.git_out("rev-parse", "--short", sha)})', notes)

    def open_triage_stage_with_origin(self, counted):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-once')
        if self.run_cmd(['git', 'status', '--porcelain']).stdout.strip():
            self.commit('record review')
        self.add_origin()
        self.run_cmd(['git', 'push', '-q', 'origin', 'main'])
        self.run_cmd(['git', 'fetch', '-q', 'origin'])
        gate = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.helper('run-manifest', 'start', gate, 'feature/test', '--approved', '--base', 'main', '--no-pr')
        head = self.git_out('rev-parse', 'HEAD')
        self.helper('run-manifest', 'stage-set', 'triage', head)
        if counted:
            self.tool('ai-run', '--approved', '--triage', '--since', head)
            self.assertEqual(self.triage_rounds(), 1)
        return self.advance_origin_main()

    def assert_triage_settled_then_merge(self, sha):
        reviews = self.codex_calls()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, MOCK_CODEX='major-once')
        self.assertIn('Completing the interrupted review triage', result.stdout)
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.triage_calls(), 1)
        self.assertEqual(self.open_stage(), '')
        self.assertIn(self.base_moved_message('origin/main', sha), result.stderr)
        self.assertEqual(self.codex_calls(), reviews)
        self.run_cmd(['git', 'merge', '-q', '--no-edit', 'origin/main'])
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', MOCK_CODEX='major-once')
        self.assertNotIn('Triage stage', result.stderr)
        self.assertEqual(self.triage_rounds(), 1)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')

    def test_base_moved_with_pending_triage_stage(self):
        self.assert_triage_settled_then_merge(self.open_triage_stage_with_origin(counted=False))

    def test_base_moved_with_counted_open_triage_stage(self):
        self.assert_triage_settled_then_merge(self.open_triage_stage_with_origin(counted=True))

    def test_base_moved_with_pending_recheck(self):
        self.origin_with_main()
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, MOCK_CODEX='two-major-once',
                  MOCK_CLAUDE='triage-mixed-reject', MOCK_RECHECK_FAIL='1')
        self.assertEqual(self.helper('recheck-status').stdout.strip(), 'pending')
        reviews = self.subjects().count('chore(ai): record independent review')
        sha = self.advance_origin_main()
        message = self.base_moved_message('origin/main', sha)
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, MOCK_RECHECK=self.UPHELD_M2)
        calls = self.recheck_calls()
        self.assertEqual(len(calls), 2)
        self.assertIn('M2\tMAJOR\tthe second defect is handled by the gate', calls[1])
        self.assertEqual(self.helper('recheck-status').stdout.strip(), 'verified')
        self.assertEqual(self.subjects().count('chore(ai): record review re-check'), 1)
        self.assertEqual(self.disputes(), 1)
        self.assertIn(message, result.stderr)
        self.assertIn(message, (self.project / '.ai/local/last-error').read_text())
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'TODO')
        self.assertEqual(self.subjects().count('chore(ai): record independent review'), reviews)
        self.assertEqual(self.triage_rounds(), 1)
        self.run_cmd(['git', 'merge', '-q', '--no-edit', 'origin/main'])
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', MOCK_RECHECK=self.UPHELD_M2)
        self.assertNotIn('Re-check:', result.stderr)
        self.assertEqual(len(self.recheck_calls()), 2)
        self.assertEqual(self.subjects().count('chore(ai): record review re-check'), 1)
        self.assertEqual(self.disputes(), 1)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertIn('--draft', self.created_prs()[0])

    def rewrite_history_while_recording_review(self):
        """main gains the plan commit; a hook then reparents HEAD onto main^ (same tree, clean
        checkout, merge-base kept), so main is no longer an ancestor at the publish check."""
        self.ready()
        origin = self.add_origin()
        self.run_cmd(['git', 'branch', '-f', 'main', 'HEAD'])
        self.hook('post-commit', '[[ "$(git log -1 --format=%s)" == "chore(ai): record independent review" ]] || exit 0\n'
                                 'git reset -q --soft "$(git commit-tree "HEAD^{tree}" -p main^ -m \'hook: rewritten history\')"\n')
        return origin

    def assert_publish_names_the_base(self, origin, result):
        prefix = 'Publish check failed at pull request preparation: Review base main ('
        for text in (result.stderr, (self.project / '.ai/local/last-error').read_text()):
            self.assertIn(prefix, text)
            self.assertIn('moved past the branch; merge it into feature/test', text)
            self.assertNotIn('reviewed content changed', text)
        self.assertEqual(self.remote_head(origin), '')
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ['pr', 'create']], [])
        self.assertIn('⛔', self.notifications())
        self.assertNotIn('FINISHED', self.notifications())

    def test_base_moved_publish_check_names_the_base(self):
        origin = self.rewrite_history_while_recording_review()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, AI_AUTO_RECOVER='1')
        self.assert_publish_names_the_base(origin, result)
        self.assertIn('escalated to the human', result.stderr)
        self.assertEqual(self.recovery_calls(), [])

    def test_base_moved_publish_check_without_recovery(self):
        origin = self.rewrite_history_while_recording_review()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1)
        self.assert_publish_names_the_base(origin, result)
        self.assertNotIn('escalated to the human', result.stderr)

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

    def test_task_sections_host_triage_adds_the_missing_sections(self):
        self.ready()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr',
                           MOCK_CODEX='major-once', MOCK_CLAUDE='triage-missing-sections')
        self.assertIn('Task queue: added missing sections: T002 (Likely affected modules, Result / notes)',
                      result.stdout)
        self.assertEqual(self.triage_rounds(), 1)
        counted = self.run_cmd(['git', 'log', '--format=%H', '--grep', '^chore(ai): record review triage$']).stdout.split()
        tasks_text = self.run_cmd(['git', 'show', f'{counted[0]}:.ai/tasks.md']).stdout
        new_task = tasks_text.split('## T002')[1]
        self.assertIn('### Likely affected modules', new_task)
        self.assertIn('### Result / notes', new_task)
        self.assertEqual(self.helper('tasks', 'status', 'T002').stdout.strip(), 'DONE')
        self.assertEqual(self.open_stage(), '')
        prompt = (self.base / 'triage-prompts.log').read_text()
        self.assertIn('Copy the task format of .ai/tasks.md exactly', prompt)
        self.assertIn('ID alone in the first cell', prompt)

    def test_task_sections_host_triage_missing_goal_still_stops(self):
        self.ready()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                           MOCK_CODEX='major-once', MOCK_CLAUDE='triage-missing-goal')
        self.assertIn('missing ### Goal', result.stderr)
        self.assertNotIn('(Goal', result.stdout)

    def test_task_sections_host_planning_adds_the_missing_sections(self):
        self.plan_ready()
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout
        result = self.plan(MOCK_CLAUDE='plan-missing-sections')
        self.assertIn('Task queue: added missing sections: T002 (Likely affected modules, Result / notes)',
                      result.stdout)
        self.assertIn('Plan ready on feature/test: 2 tasks', result.stdout)
        queue = (self.project / '.ai/tasks.md').read_text()
        second = queue.split('## T002')[1]
        self.assertIn('### Likely affected modules', second)
        self.assertIn('### Result / notes', second)
        self.assertEqual(self.observation()['note'], '2 tasks')
        self.assertEqual(self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout, head)

    def test_task_sections_host_revision_adds_the_missing_sections(self):
        self.revise_ready()
        result = self.revise(MOCK_CLAUDE='revise-accept-missing-sections')
        self.assertIn('Task queue: added missing sections: T002', result.stdout)
        self.assertEqual(len(self.revision_args()), 1)
        self.assertEqual(self.revision_commits(), 1)
        committed = self.run_cmd(['git', 'show', 'HEAD:.ai/tasks.md']).stdout.split('## T002')[1]
        self.assertIn('### Likely affected modules', committed)
        self.assertIn('### Result / notes', committed)
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain', '--untracked-files=all']).stdout, '')

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
        self.assertIn("Cannot read this branch's open stage", result.stderr)
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

    # ---------------------------------------------------------------- extra fix round (T008)
    # Round 3+ triage needs a Convergence line; the extra round is round 3 here.
    CONVERGENCE = 'Convergence: findings fall each round; the fix tasks address them'

    def falling_run(self, majors, *args, expected=0, **env):
        return self.tool('ai-pipeline', '--approved', '--base', 'main', '--max-fix-rounds', '2', *args,
                         expected=expected, **dict({'AI_SUPERVISE': '1', 'MOCK_CODEX': 'counts',
                                                    'MOCK_CODEX_MAJORS': majors, 'MOCK_CONVERGENCE': self.CONVERGENCE},
                                                   **env))

    def pr_draft(self):
        create = [c for c in self.gh_calls() if c[:2] == ['pr', 'create']]
        self.assertEqual(len(create), 1)
        return '--draft' in create[0]

    def fix_round_store(self):
        return next((self.base / 'host-state').rglob('fix-rounds-*.json'))

    def triage_commits(self):
        return self.run_cmd(['git', 'log', '--reverse', '--format=%H', '--grep',
                             '^chore(ai): record review triage$']).stdout.split()

    def test_extra_fix_round_falling_counts_get_one_round_then_draft(self):
        self.ready()
        self.add_origin()
        result = self.falling_run('4,3,2,1')
        self.assertIn('Review triage, round 3 (Claude)', result.stdout)
        self.assertEqual(self.triage_calls(), 3)
        self.assertEqual(self.fix_rounds(), 3)
        notes = self.notifications()
        self.assertEqual(notes.count('🔁 Extra fix round'), 1)
        self.assertIn('🔁 Extra fix round: findings falling (4 → 3 → 2)', notes)
        # Still falling (3 → 2 → 1) at the next limit, but the run's extra round is used: draft.
        self.assertIn('Fix round limit (2) reached', result.stdout)
        self.assertTrue(self.pr_draft())
        # The third triage commit carries the run-log line; the records hold verified counts.
        third = self.triage_commits()[2]
        self.assertIn('extra fix round 3: findings falling (4 → 3 → 2)',
                      self.run_cmd(['git', 'show', third, '--', '.ai/run-log.md']).stdout)
        records = json.loads(self.fix_round_store().read_text())
        self.assertEqual([r['majors'] for r in records], [4, 3, 2])
        self.assertEqual([r['commit'] for r in records], self.triage_commits())

    def test_extra_fix_round_clean_review_after_it_opens_a_ready_pr(self):
        self.ready()
        self.add_origin()
        self.falling_run('3,2,1,0')
        self.assertEqual(self.triage_calls(), 3)
        self.assertIn('🔁 Extra fix round: findings falling (3 → 2 → 1)', self.notifications())
        self.assertFalse(self.pr_draft())

    def assert_no_extra_round(self, majors, **env):
        self.ready()
        self.add_origin()
        result = self.falling_run(majors, **env)
        self.assertEqual(self.triage_calls(), 2)
        self.assertEqual(self.fix_rounds(), 2)
        self.assertIn('Fix round limit (2) reached', result.stdout)
        self.assertNotIn('Extra fix round', self.notifications())
        self.assertTrue(self.pr_draft())
        self.assertEqual(self.helper('run-manifest', 'extra-round').stdout.strip(), '')

    def test_extra_fix_round_flat_counts_and_imitated_subjects_draft(self):
        self.assert_no_extra_round('2,2,2', MOCK_TRIAGE_SUBJECT='chore(ai): record review triage')

    def test_extra_fix_round_rising_counts_draft(self):
        self.assert_no_extra_round('1,2,3')

    def test_extra_fix_round_unsupervised_draft(self):
        self.assert_no_extra_round('3,2,1', AI_SUPERVISE='0')

    def test_extra_fix_round_trend_history_boundaries(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--max-fix-rounds', '3',
                  MOCK_CODEX='counts', MOCK_CODEX_MAJORS='4,3,2,1', MOCK_CONVERGENCE=self.CONVERGENCE)
        self.assertEqual(self.helper('fix-rounds', 'trend', 'main').stdout.split(), ['3', '2', '1'])
        store = self.fix_round_store()
        counted = json.loads(store.read_text())
        legacy = [r['commit'] for r in counted]

        def trend(records, rounds=3):
            store.write_text(json.dumps(records))
            self.assertEqual(self.fix_rounds(), rounds)  # both shapes still count
            result = self.helper('fix-rounds', 'trend', 'main', expected=None)
            return result.stdout.split() if result.returncode == 0 else result.stderr.strip()
        insufficient = 'Error: insufficient history'
        # Round 1 triaged by the old toolkit, rounds 2-3 with counts: only 2-3 and the current review.
        self.assertEqual(trend([legacy[0], counted[1], counted[2]]), ['3', '2', '1'])
        # Only round 3 counted.
        self.assertEqual(trend([legacy[0], legacy[1], counted[2]]), insufficient)
        # A legacy record between counted ones, or as the most recent one.
        self.assertEqual(trend([counted[0], legacy[1], counted[2]]), insufficient)
        self.assertEqual(trend([counted[0], counted[1], legacy[2]]), insufficient)
        # The current review must not be the one the last round already triaged.
        head = self.helper('review-info').stdout.split()[0]
        self.assertEqual(trend([counted[0], counted[1], dict(counted[2], review_head=head)]), insufficient)
        # A record no longer reachable from HEAD is skipped: the last two reachable rounds count.
        self.assertEqual(trend([counted[0], counted[1], dict(counted[2], commit='f' * 40)], rounds=2),
                         ['4', '3', '1'])
        self.assertEqual(trend([legacy[0], counted[1], dict(counted[2], commit='f' * 40)], rounds=2), insufficient)
        store.write_text(json.dumps(counted))
        # Another branch at the same commits has no host records: commit subjects alone (also
        # agent-chosen ones) give legacy rounds without counts, never an extra round.
        self.run_cmd(['git', 'switch', '-q', '-c', 'other'])
        self.assertEqual(self.fix_rounds(), 3)
        self.assertEqual(self.helper('fix-rounds', 'trend', 'main', expected=1).stderr.strip(), insufficient)

    def test_extra_fix_round_reservation_once_per_run(self):
        self.ready()
        self.start_run('feature/test')
        first, second = 'a' * 64, 'b' * 64
        self.assertEqual(self.helper('run-manifest', 'extra-round').stdout.strip(), '')
        self.helper('run-manifest', 'extra-round-reserve', first)
        self.helper('run-manifest', 'extra-round-reserve', first)  # a resume: same review, no error
        self.assertIn('already used', self.helper('run-manifest', 'extra-round-reserve', second, expected=1).stderr)
        self.assertEqual(self.helper('run-manifest', 'extra-round').stdout.strip(), first)
        self.helper('run-manifest', 'extra-round-reserve', 'not-a-digest', expected=1)
        self.start_run('feature/test')  # a human (re)start resets it
        self.assertEqual(self.helper('run-manifest', 'extra-round').stdout.strip(), '')

    def test_extra_fix_round_crash_after_reservation_resumes_it_once(self):
        self.ready()
        notify = self.base / 'notify-crash'
        notify.write_text(f'printf "%s\\n" "$1" >> "{self.notify_log}"\n'
                          f'case "$1" in *"Extra fix round"*)\n'
                          f'  [ -e "{self.base}/notify-crashed" ] || {{ touch "{self.base}/notify-crashed"; '
                          'kill -9 "$(cat .ai/local/pipeline.active)"; }\n'
                          'esac\n')
        crash = dict(AI_AUTO_RECOVER='1', AI_NOTIFY_CMD=f'bash "{notify}" "$1"')
        crashed = self.falling_run('3,2,1', '--no-pr', expected=None, **crash)
        self.assertEqual(crashed.returncode, -9)
        self.assertEqual(self.triage_calls(), 2)
        self.assertEqual(self.open_stage(), '')  # reserved, the stage not opened yet
        self.assertNotEqual(self.helper('run-manifest', 'extra-round').stdout.strip(), '')
        self.assertEqual(self.run_cmd(['git', 'status', '--porcelain']).stdout.strip(), '')
        self.tool('ai-recover', '--stage', 'crash (pipeline killed or restarted)', MOCK_CLAUDE='',
                  MOCK_CODEX='counts', MOCK_CODEX_MAJORS='3,2,1', MOCK_CONVERGENCE=self.CONVERGENCE, **crash)
        self.assertEqual(self.triage_calls(), 3)
        self.assertEqual(self.fix_rounds(), 3)
        self.assertEqual(self.notifications().count('🔁 Extra fix round'), 1)
        self.assertIn('reserved before a restart',
                      self.run_cmd(['git', 'show', self.triage_commits()[2], '--', '.ai/run-log.md']).stdout)
        self.assertIn('🏁 FINISHED', self.notifications())

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

    def recheck_outcomes(self):
        return [r for r in self.outcome_rows() if r['kind'] == 'review' and r['mode'] == 'recheck']

    def test_outcome_recheck_records_upheld_and_withdrawn_totals(self):
        self.rejected_review(['| M1 | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
                              '| M2 | rejected | the second defect is handled by the gate | none |\n'])
        reviewed = self.helper('review-info').stdout.split()[0]
        answer = json.dumps({'answers': [{'id': 'M1', 'verdict': 'withdrawn', 'reason': 'evidence holds'},
                                         {'id': 'M2', 'verdict': 'upheld', 'reason': 'not covered'}]})
        self.tool('ai-review', '--recheck', MOCK_RECHECK=answer)
        line = self.recheck_outcomes()[-1]
        self.assertEqual((line['upheld_major'], line['withdrawn_major']), (1, 1))
        self.assertEqual((line['upheld_blocker'], line['withdrawn_blocker']), (0, 0))
        full = self.run_cmd(['git', 'rev-parse', reviewed]).stdout.strip()
        self.assertEqual(line['reviewed_head'], full)
        self.assertEqual(len(full), 40)
        self.assertNotEqual(line['reviewed_head'], line['head'])  # the triage commit moved HEAD on
        self.tool('ai-review', '--recheck', MOCK_RECHECK='not json')  # malformed: every finding upheld
        line = self.recheck_outcomes()[-1]
        self.assertEqual((line['upheld_major'], line['withdrawn_major']), (2, 0))

    def test_outcome_recheck_counts_blockers(self):
        wf = self.recheck_module()
        answers = {'B1': ('upheld', 'x'), 'B2': ('withdrawn', 'x'), 'M1': ('upheld', 'x'), 'M2': ('withdrawn', 'x')}
        levels = {'B1': 'BLOCKER', 'B2': 'BLOCKER', 'M1': 'MAJOR', 'M2': 'MAJOR'}
        self.assertEqual(wf.recheck_counts(answers, levels), (1, 1, 1, 1))

    def test_outcome_recheck_without_report_still_logs_a_line(self):
        self.ready()
        before = len(self.outcome_rows())
        self.helper('outcome', 'review', 'recheck', 'codex', 'gpt', 'medium', '1')
        rows = self.outcome_rows()
        self.assertEqual(len(rows), before + 1)
        self.assertEqual(rows[-1]['mode'], 'recheck')
        for field in ('upheld_blocker', 'upheld_major', 'withdrawn_blocker', 'withdrawn_major', 'reviewed_head'):
            self.assertNotIn(field, rows[-1])

    def test_outcome_recheck_report_has_its_own_table(self):
        self.setup_project()
        path = self.base / 'recheck.jsonl'
        review = {'kind': 'review', 'project': 'p', 'branch': 'b', 'mode': 'recheck'}
        rows = [{**review, 'reviewer': 'codex', 'model': 'gpt', 'seconds': 60, 'upheld_blocker': 1,
                 'upheld_major': 2, 'withdrawn_blocker': 0, 'withdrawn_major': 3},
                {**review, 'reviewer': 'codex', 'model': 'gpt', 'seconds': 180, 'upheld_major': 1},
                {**review, 'reviewer': 'claude-fallback', 'model': 'claude-opus-5-5', 'seconds': 60,
                 'head': 'abcdef0123456789abcdef'}]
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        report = self.tool('ai-status', '--outcomes', str(path)).stdout
        self.assertIn('## Re-checks by reviewer', report)
        self.assertIn('| codex | gpt | 2 | 1 | 3 | 0 | 3 | 2.0 |', report)
        self.assertNotIn('| recheck |', report)
        self.assertNotIn('## Reviews by reviewer', report)
        self.assertIn('recheck HEAD abcdef012345', report.split('Codex catch-up pending')[1])
        path.write_text(json.dumps(rows[2]) + '\n')
        report = self.tool('ai-status', '--outcomes', str(path)).stdout
        self.assertIn('recheck HEAD abcdef012345', report.split('Codex catch-up pending')[1])

    def test_triage_severity_suffix_satisfies_triage_check(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        for cell in ('M1 (MAJOR)', 'M1 (major)', 'M1(MAJOR)'):
            dispositions.write_text(rows.replace('| M1 |', f'| {cell} |'))
            self.assertEqual(self.helper('triage-check', '--fresh').stdout.strip(), 'accepted=1 deferred=0')
        # Accepted rows still need an existing fix task.
        dispositions.write_text(rows.replace('| M1 |', '| M1 (MAJOR) |').replace('T001', 'T099'))
        self.helper('triage-check', '--fresh', expected=1)

    def test_triage_severity_suffix_other_decorations_stay_unmatched(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        for cell in ('M1 (CRITICAL)', '**M1**'):
            dispositions.write_text(rows.replace('| M1 |', f'| {cell} |'))
            result = self.helper('triage-check', '--fresh', expected=1)
            self.assertIn('MAJOR finding M1 has no disposition', result.stderr)

    def test_finding_cell_triage_accepts_suffix_and_title(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        for cell in ('M1 (MAJOR) title text', 'M1 — title', 'M1: title', 'M1 (MAJOR) about M1'):
            dispositions.write_text(rows.replace('| M1 |', f'| {cell} |'))
            self.assertEqual(self.helper('triage-check', '--fresh').stdout.strip(), 'accepted=1 deferred=0')

    def test_finding_cell_triage_stays_unmatched_with_a_hint(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        for cell in ('**M1**', 'M1 (CRITICAL)', 'M1 (CRITICAL) x', 'M1,M2', 'M1/M2', 'M1x'):
            with self.subTest(cell):
                dispositions.write_text(rows.replace('| M1 |', f'| {cell} |'))
                result = self.helper('triage-check', '--fresh', expected=1)
                self.assertIn('MAJOR finding M1 has no disposition', result.stderr)
                self.assertIn(f'the row starting "| {cell} |" does not match', result.stderr)
                self.assertIn('write "| M1 |', result.stderr)

    def test_finding_cell_plan_dispositions_accept_suffix_and_title(self):
        start = self.open_plan_section()
        path = self.project / '.ai/reviews/plan-dispositions.md'
        base = path.read_text()
        for cell in ('P1 (MAJOR)', 'P1(major)', 'P1 (MAJOR) selection highlight is lost',
                     'P1 — title', 'P1: title', 'P1 title'):
            with self.subTest(cell):
                path.write_text(base + f'| {cell} | accepted | real | T002 |\n'
                                '| P2 | rejected | rollback is covered in docs/rollback.md:12 | |\n')
                self.assertEqual(self.plan_check(start).stdout.strip(), 'accepted=1 rejected=1 needs_human=0')

    def test_finding_cell_plan_dispositions_stay_unmatched_with_a_hint(self):
        start = self.open_plan_section()
        path = self.project / '.ai/reviews/plan-dispositions.md'
        base = path.read_text()
        for cell in ('**P1**', 'P1 (CRITICAL)', 'P1,P2', 'P1/P2', 'P1x'):
            with self.subTest(cell):
                path.write_text(base + f'| {cell} | accepted | real | T002 |\n'
                                '| P2 | rejected | rollback is covered in docs/rollback.md:12 | |\n')
                result = self.plan_check(start, expected=1)
                self.assertIn('Finding P1 has no row', result.stderr)
                self.assertIn(f'the row starting "| {cell} |" does not match', result.stderr)
                self.assertIn('write "| P1 |', result.stderr)

    def test_finding_cell_pattern_units(self):
        wf = self.recheck_module()
        row = wf.DISPOSITION_ROW.search('| M1 (MAJOR) a \\| b | accepted | ev \\| x | T001 |\n')
        self.assertEqual((row.group(1), row.group(2), wf.table_cell(row.group(3)), row.group(4)),
                         ('M1', 'accepted', 'ev | x', ' T001'.strip()))
        self.assertEqual(wf.DISPOSITION_ROW.search('| SEC-12 - fix | accepted | e | T001 |').group(1), 'SEC-12')
        self.assertEqual(wf.PLAN_DISPOSITION_ROW.search('| SEC-12 - fix | needs-human | e | |').group(1), 'SEC-12')

    def test_finding_cell_row_counts_for_its_first_id_only(self):
        start = self.open_plan_section()
        path = self.project / '.ai/reviews/plan-dispositions.md'
        path.write_text(path.read_text() + '| P1 (MAJOR) about P2 | accepted | real | T002 |\n')
        self.assertIn('Finding P2 has no row', self.plan_check(start, expected=1).stderr)

    def test_finding_cell_prompts_show_the_row(self):
        for name, row in (('triage', '| M1 | accepted |'), ('plan-revision', '| P1 | accepted |')):
            with self.subTest(name):
                text = (ROOT / f'templates/.ai/prompts/{name}.md').read_text()
                self.assertIn(row, text)
                self.assertIn('ID alone in the first cell', text)
        contract = (ROOT / 'scripts/ai-run').read_text()
        self.assertIn('| M1 | accepted | evidence | T012 |', contract)
        self.assertIn('| P1 | accepted | evidence | T012 |', contract)
        self.ready()
        head = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        self.helper('start-dispositions', head)
        self.assertIn('| M1 | accepted |', (self.project / '.ai/reviews/dispositions.md').read_text())

    def test_triage_severity_suffix_rejected_row_is_rechecked_and_counted(self):
        self.rejected_review(['| M1 (MAJOR) | rejected | T001.txt is a fixture; the finding misreads it | none |\n',
                              '| M2 (MAJOR) | accepted | real defect | T002 |\n'], fix_task=True)
        self.helper('triage-check', '--fresh')
        self.tool('ai-review', '--recheck')
        self.assertIn('M1\tMAJOR\tT001.txt is a fixture; the finding misreads it',
                      (self.base / 'codex-recheck-calls').read_text())
        self.helper('recheck-verify')
        wf = self.recheck_module()
        rows = [m.group(2).lower() for m in wf.DISPOSITION_ROW.finditer(
            (self.project / '.ai/reviews/dispositions.md').read_text())]
        self.assertEqual(rows, ['rejected', 'accepted'])

    def test_disposition_pipes_escaped_pipe_in_evidence_keeps_the_task_cell(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        piped = rows.replace('defect confirmed in the fixture', 'use `--yes \\| --no`')
        dispositions.write_text(piped)
        self.assertEqual(self.helper('triage-check', '--fresh').stdout.strip(), 'accepted=1 deferred=0')
        wf = self.recheck_module()
        row = wf.DISPOSITION_ROW.search(piped)
        self.assertEqual((wf.table_cell(row.group(3)), wf.table_cell(row.group(4))), ('use `--yes | --no`', 'T001'))
        # An unescaped pipe still splits the row: the Task cell is then misread.
        dispositions.write_text(rows.replace('defect confirmed in the fixture', 'use --yes | --no'))
        self.helper('triage-check', '--fresh', expected=1)

    def test_disposition_pipes_rejected_row_with_escaped_pipe_passes(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        dispositions.write_text(rows.replace(
            '| accepted | defect confirmed in the fixture | T001 |',
            '| rejected | the flag reads `--yes \\| --no` in the fixture | none |'))
        self.assertEqual(self.helper('triage-check', '--fresh').stdout.strip(), 'accepted=0 deferred=0')

    def test_disposition_pipes_missing_task_cell_is_malformed(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        dispositions.write_text(rows.replace('| accepted | defect confirmed in the fixture | T001 |',
                                             '| accepted | discussion of fix \\| T001 |'))
        result = self.helper('triage-check', '--fresh', expected=1)
        self.assertIn('MAJOR finding M1 has no disposition', result.stderr)

    def test_disposition_pipes_table_cell_pattern(self):
        wf = self.recheck_module()
        cell = re.compile('^' + wf.TABLE_CELL + r'\|')
        self.assertEqual(cell.match('a \\| b|').group(1), 'a \\| b')
        self.assertEqual(cell.match('C:\\path|').group(1), 'C:\\path')
        self.assertEqual(wf.table_cell(' a \\| b '), 'a | b')
        self.assertEqual(wf.table_cell('C:\\path'), 'C:\\path')

    def test_disposition_pipes_missing_task_before_next_row(self):
        dispositions, rows = self.convergence_fixture(rounds=2)
        dispositions.write_text(rows.replace(
            '| accepted | defect confirmed in the fixture | T001 |',
            '| accepted | defect confirmed in the fixture |\n| M9 | rejected | other | none |'))
        self.helper('triage-check', '--fresh', expected=1)
        wf = self.recheck_module()
        found = [m.group(1) for m in wf.DISPOSITION_ROW.finditer(dispositions.read_text())]
        self.assertNotIn('M1', found)
        self.assertIn('M9', found)

    def test_disposition_pipes_missing_task_before_next_plan_row(self):
        wf = self.recheck_module()
        plan = '| P1 | accepted | note |\n| P2 | rejected | covered in docs/x.md:1 | |\n'
        self.assertEqual([m.group(1) for m in wf.PLAN_DISPOSITION_ROW.finditer(plan)], ['P2'])
        start = self.open_plan_section()
        path = self.project / '.ai/reviews/plan-dispositions.md'
        path.write_text(path.read_text() + plan)
        self.plan_check(start, expected=1)

    def test_disposition_pipes_literal_backslash_round_trip(self):
        wf = self.recheck_module()
        for decoded in ('literal regex | is required', 'a \\\\ b', 'ends with \\', 'C:\\path | x', 'a \\| b'):
            with self.subTest(decoded):
                encoded = ' '.join(decoded.split()).replace('\\', '\\\\').replace('|', '\\|')
                row = f'| M1 | accepted | {encoded} | T001 |\n'
                match = wf.DISPOSITION_ROW.search(row)
                self.assertEqual((wf.table_cell(match.group(3)), wf.table_cell(match.group(4))), (decoded, 'T001'))
        self.assertEqual(wf.table_cell('literal regex \\| is required'), 'literal regex | is required')
        self.assertEqual(wf.table_cell('a \\\\\\\\ b'), 'a \\\\ b')
        dispositions, rows = self.convergence_fixture(rounds=2)
        dispositions.write_text(rows.replace('defect confirmed in the fixture', 'literal regex \\| is required'))
        self.assertEqual(self.helper('triage-check', '--fresh').stdout.strip(), 'accepted=1 deferred=0')

    def test_disposition_pipes_plan_dispositions_read_the_task_cell(self):
        start = self.open_plan_section()
        path = self.project / '.ai/reviews/plan-dispositions.md'
        rows = ('| P1 | accepted | flag `--no\\|--yes` needs a test | T002 |\n'
                '| P2 | rejected | rollback is covered in docs/rollback.md:12 | |\n')
        path.write_text(path.read_text() + rows)
        self.assertEqual(self.plan_check(start).stdout.strip(), 'accepted=1 rejected=1 needs_human=0')
        malformed = '| P1 | accepted | discussion of fix \\| T002 |\n'
        path.write_text(path.read_text().replace(rows.splitlines(True)[0], malformed))
        self.plan_check(start, expected=1)

    def test_disposition_pipes_round_trip_through_the_recheck_record(self):
        self.rejected_review(['| M1 | rejected | the flag reads `--yes \\| --no` in the fixture | none |\n',
                              '| M2 | accepted | real defect | T002 |\n'], fix_task=True)
        self.helper('triage-check', '--fresh')
        self.tool('ai-review', '--recheck')
        self.assertIn('the flag reads `--yes | --no` in the fixture',
                      (self.base / 'codex-recheck-calls').read_text())
        recheck = (self.project / '.ai/reviews/recheck.md').read_text()
        self.assertIn('the flag reads `--yes \\| --no` in the fixture', recheck)
        self.assertNotIn('\\\\|', recheck)

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
        self.assertIn('Re-check of rejected findings (Codex; Claude fallback)', result.stdout)
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

    WRAPPED_HANDOFF = ('# Handoff\n\n## Manual testing for the human\n### Needs you\n'
                       '1. Check it.\n2. Check it again.\n\n'
                       '### Covered by automated tests\n'
                       '- Drag fails and the card snaps back:\n  `test_drag_fails`.\n'
                       '- Resize works,\n  continues here, and names\n  `test_resize`.\n'
                       '- Nothing names a test here\n  even on this line.\n'
                       '- Lone backtick ` only\n  on the next line.\n\n## Next action\nNone.\n')

    def test_manual_testing_wrapped_name_on_continuation_line_is_not_flagged(self):
        self.setup_project()
        body = self.pr_body_for(self.WRAPPED_HANDOFF)
        self.assertIn('<details><summary>4 automated checks</summary>', body)
        self.assertIn('  `test_drag_fails`.\n', body)
        self.assertIn('  `test_resize`.\n', body)
        self.assertEqual(body.count('⚠ no test named'), 2)

    def test_manual_testing_wrapped_unnamed_and_lone_backtick_are_flagged_on_the_last_line(self):
        self.setup_project()
        body = self.pr_body_for(self.WRAPPED_HANDOFF)
        self.assertIn('- Nothing names a test here\n  even on this line. ⚠ no test named\n', body)
        self.assertIn('- Lone backtick ` only\n  on the next line. ⚠ no test named\n', body)

    def test_manual_testing_wrapped_this_repo_flags_only_unnamed_bullets(self):
        self.setup_project()
        handoff = (ROOT / '.ai/handoff.md').read_text()
        body = self.pr_body_for(handoff)
        flagged = [line for line in body.splitlines() if line.endswith('⚠ no test named')]
        # The live handoff changes per branch: exactly its automated bullets without a test name.
        automated = handoff.split('### Covered by automated tests', 1)[1].split('\n## ', 1)[0]
        # A bullet wraps onto indented continuation lines; the warning goes on its last line.
        items = []
        for line in automated.splitlines():
            if line.startswith('- '):
                items.append([line])
            elif items and line.startswith(' ') and line.strip():
                items[-1].append(line)
        unnamed = [item[-1] + ' ⚠ no test named' for item in items if '`' not in '\n'.join(item)]
        self.assertEqual(flagged, unnamed)

    def test_manual_testing_wrapped_finish_summary_counts_needs_you_steps(self):
        self.setup_project()
        (self.project / '.ai/handoff.md').write_text(
            self.WRAPPED_HANDOFF.replace('## Next action', '## Human todos\nNone.\n\n## Next action'))
        out = self.helper('finish-summary', 'https://example.test/pr/1', '0', '0').stdout
        self.assertIn('Test: 2 manual step(s) in the PR', out)
        self.assertNotIn('automated checks', out)

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
        # AGENTS.md allows either line; a batch that leaves the flow alone says "Flow unchanged".
        handoff = (ROOT / '.ai/handoff.md').read_text()
        match = re.search(r'^## Flow chart\n(Flow chart updated|Flow unchanged)', handoff, re.M)
        self.assertIsNotNone(match, 'the handoff needs a "## Flow chart" line')
        self.setup_project()
        self.assertIn(match.group(1), self.pr_body_for(handoff))

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

    def test_deps_status_output_kind(self):
        self.deps_fixture('#!/usr/bin/env bash\n# ai-deps-outputs: vendor-deps\ntrue\n')
        self.helper('deps-record')
        out = self.project / 'vendor-deps'
        out.write_text('not a dir\n')
        self.assertEqual(self.deps(), 'stale output vendor-deps is not a directory')
        out.unlink()
        out.symlink_to(self.project / 'nowhere')
        self.assertEqual(self.deps(), 'stale output vendor-deps is not a directory')
        out.unlink()
        target = self.project / 'real-deps'
        target.mkdir()
        out.symlink_to(target)
        self.assertEqual(self.deps(), 'current')
        out.unlink()
        out.mkdir()
        self.assertEqual(self.deps(), 'current')

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

    def test_tree_snapshot_uninitialised_submodule(self):
        origin = self.base / 'sub-origin'
        origin.mkdir()
        for args in (['init', '-q', '-b', 'main'], ['commit', '-q', '--allow-empty', '-m', 'sub']):
            subprocess.run(['git', '-c', 'user.name=T', '-c', 'user.email=t@example.invalid',
                            '-c', 'commit.gpgsign=false', *args], cwd=origin, env=self.env,
                           check=True, capture_output=True)
        self.run_cmd(['git', '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q',
                      str(origin), 'sub'])
        self.commit('add submodule')
        self.run_cmd(['git', 'submodule', '--quiet', 'deinit', '-f', 'sub'])
        sub = self.project / 'sub'
        self.assertEqual(list(sub.iterdir()), [])
        seen = [self.tree_snapshot()]
        self.assertEqual(self.tree_snapshot(), seen[0])

        def changed(action):
            action()
            seen.append(self.tree_snapshot())
            self.assertNotIn(seen[-1], seen[:-1])
            self.assertEqual(self.tree_snapshot(), seen[-1])

        changed(lambda: (sub / 'new.txt').write_text('created\n'))
        changed(lambda: (sub / 'new.txt').write_text('overwritten\n'))
        changed(lambda: (sub / 'new.txt').chmod(0o755))
        changed(lambda: (sub / 'nested').mkdir())
        changed(lambda: (sub / 'nested/link').symlink_to('../new.txt'))
        changed(lambda: sub.chmod(0o700))

        def replace_with_link():
            shutil.rmtree(sub)
            sub.symlink_to(self.base)
        changed(replace_with_link)
        changed(lambda: (sub.unlink(), sub.write_text('file\n')))
        changed(lambda: sub.unlink())

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

    def test_deps_runner_installer_writing_into_uninitialised_submodule_stops(self):
        base = self.deps_ready()
        self.run_cmd(['git', 'update-index', '--add', '--cacheinfo', f'160000,{base},sub'])
        (self.project / 'sub').mkdir()
        self.commit('uninitialised submodule')
        base = self.run_cmd(['git', 'rev-parse', 'HEAD']).stdout.strip()
        for mode in ('submodule', 'submodule-fail'):
            with self.subTest(mode=mode):
                self.tool('ai-run', '--approved', expected=1, MOCK_DEPS=mode)
                self.assert_deps_stopped('Dependency setup changed project files')
                self.assertEqual(self.deps_calls(), 1)
                (self.project / 'sub/new.txt').unlink()
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

    # ---------------------------------------------------------------- stage records (T003)
    def observation(self):
        return json.loads((self.project / '.ai/local/observation.json').read_text())

    def seen(self):
        """The records the mock agents saw, in order (observation.json at each session start)."""
        path = self.project / '.ai/local/obs-history'
        decoder, text, records = json.JSONDecoder(), path.read_text() if path.exists() else '', []
        while text.strip():
            record, end = decoder.raw_decode(text.lstrip())
            records.append(record)
            text = text.lstrip()[end:]
        return records

    def plant_observation(self, **fields):
        (self.project / '.ai/local').mkdir(exist_ok=True)
        record = dict(stage='pr', state='done', detail='', since='2026-01-01T00:00:00Z', note='old',
                      pid=1, branch='feature/test', updated='2026-01-01T00:00:00Z')
        (self.project / '.ai/local/observation.json').write_text(json.dumps(dict(record, **fields)) + '\n')

    def test_observation_pipeline_normal_run_records_stages_and_the_pr(self):
        self.ready()
        self.add_origin()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        stages = [r['stage'] for r in self.seen()]
        self.assertEqual([s for i, s in enumerate(stages) if i == 0 or s != stages[i - 1]],
                         ['plan_review', 'build', 'review'])
        done = self.observation()
        self.assertEqual((done['stage'], done['state'], done['note']),
                         ('pr', 'done', 'https://github.com/example/project/pull/7'))

    def test_observation_pipeline_no_pr_run_ends_at_pr_with_a_note(self):
        self.ready()
        self.plant_observation(stage='review', state='stopped')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('Pipeline complete (no PR requested).', result.stdout)
        done = self.observation()
        self.assertEqual((done['stage'], done['state'], done['note']), ('pr', 'done', 'no PR'))

    def test_observation_pipeline_local_only_finish_notes_it(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main')
        done = self.observation()
        self.assertEqual((done['stage'], done['state'], done['note']), ('pr', 'done', 'no PR (local only)'))

    def test_observation_pipeline_review_stop_records_one_stop_with_the_reason(self):
        self.ready(task('T001', 'DONE'))
        (self.project / '.gitattributes').write_text('*.txt filter=sneaky\n')
        self.run_cmd(['git', 'config', 'filter.sneaky.clean', 'sed s/checkpointed/tampered/'])
        (self.project / 'T001.txt').write_text('checkpointed implementation\n')
        self.commit('done task, committed through a filter')
        self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, AI_AUTO_RECOVER='0')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('review', 'stopped'))
        # stop() recorded the last-error reason; ai_die did not add the longer "Pipeline stopped" note
        self.assertTrue(stopped['note'].startswith('Committed content differs'), stopped['note'])

    def test_observation_pipeline_plan_review_stop_records_plan_review(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, MOCK_CODEX_PLAN='major',
                  AI_SUPERVISE='0')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('plan_review', 'stopped'))

    def test_observation_pipeline_supervised_plan_revision_shows_round_then_review(self):
        self.ready()
        self.supervised('--no-pr', MOCK_CODEX_PLAN='major-once')
        seen = [(r['stage'], r['detail']) for r in self.seen()]
        revision = seen.index(('plan_revision', '1/3 · round 1'))
        self.assertIn('plan_review', [stage for stage, _ in seen[revision + 1:]])

    def test_observation_pipeline_stored_needs_human_decision_stops_on_plan_revision(self):
        self.ready()
        self.supervised('--no-pr', expected=1, MOCK_CODEX_PLAN='major',
                        MOCK_CODEX_PLAN_FINDINGS='P1|Rollback choice;P2|Gap in tests',
                        MOCK_CLAUDE='revise-needs-human', MOCK_QUESTION='Keep option A or switch to B?')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('plan_revision', 'stopped'))
        self.assertIn('Keep option A or switch to B?', stopped['note'])

    def test_observation_pipeline_extra_fix_round_detail(self):
        self.ready()
        self.add_origin()
        self.falling_run('4,3,2,1')
        details = [r['detail'] for r in self.seen() if r['stage'] == 'triage']
        self.assertIn('round 3 · extra (4 → 3 → 2)', details)
        self.assertIn('round 1', details)

    def test_observation_pipeline_base_moved_stops_with_stage_none(self):
        self.origin_with_main()
        sha = self.advance_origin_main()
        self.plant_observation()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('none', 'stopped'))
        self.assertIn(self.git_out('rev-parse', '--short', sha), stopped['note'])

    def test_observation_pipeline_start_dying_at_the_clean_check_records_stop_none(self):
        self.ready()
        self.plant_observation()
        (self.project / 'stray.txt').write_text('uncommitted\n')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('none', 'stopped'))
        self.assertIn('clean checkpoint', stopped['note'])

    def test_observation_pipeline_resume_gate_stop_leaves_the_record_untouched(self):
        self.ready()
        validate = self.project / '.ai/validate'
        original = validate.read_bytes()
        validate.write_bytes(original + b'# approved before a change\n')
        self.approve_run()
        validate.write_bytes(original)
        self.plant_observation()
        before = (self.project / '.ai/local/observation.json').read_bytes()
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', expected=1, AI_RECOVERY_ATTEMPT='1')
        self.assertIn('Gate files changed since the run was approved', result.stderr)
        self.assertEqual((self.project / '.ai/local/observation.json').read_bytes(), before)
        self.assertFalse((self.project / '.ai/local/notifications.log').exists())
        self.assertIn('⛔', self.notifications())

    def test_observation_pipeline_gate_changed_by_a_hook_runs_no_helper(self):
        self.ready()
        self.hook('post-commit', 'if [[ "$(git log -1 --format=%s)" == "chore(ai): record independent review" ]]; then\n'
                                 '  printf "from pathlib import Path\\nPath(\'UNTRUSTED_HELPER_RAN\').touch()\\n" > .ai/bin/lib/workflow.py\n'
                                 'fi\n')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1)
        self.assertIn('Approved workflow gate changed', result.stderr)
        self.assertFalse((self.project / 'UNTRUSTED_HELPER_RAN').exists())
        # the last record is the review step: no stop was written after the gate changed
        last = self.observation()
        self.assertEqual((last['stage'], last['state']), ('review', 'active'))

    def registry(self):
        return sorted((self.base / 'host-state').rglob('pipelines/*.json'))

    def test_observation_pipeline_registers_the_checkout_on_start_and_resume(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        entries = [json.loads(path.read_text()) for path in self.registry()]
        self.assertEqual([(e['checkout'], e['branch']) for e in entries],
                         [(str(self.project), 'feature/test')])
        for path in self.registry():
            path.unlink()
        gate = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.helper('run-manifest', 'start', gate, 'feature/test', '--approved', '--base', 'main', '--no-pr')
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', AI_RECOVERY_ATTEMPT='1')
        self.assertEqual(len(self.registry()), 1)

    def test_observation_pipeline_unusable_registry_only_warns(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        directory = self.registry()[0].parent
        shutil.rmtree(directory)
        directory.write_text('not a directory\n')
        result = self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr')
        self.assertIn('Pipeline complete (no PR requested).', result.stdout)
        self.assertIn('pipeline-register', result.stderr)
        self.assertTrue(list((self.base / 'host-state').rglob('run.json')))
        self.assertTrue(directory.is_file())

    # ---------------------------------------------------------------- runner records (T004)
    RECORDING_VALIDATE = """#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json, os, pathlib, sys
path = pathlib.Path('.ai/local/observation.json')
record = json.loads(path.read_text()) if path.exists() else {}
with open('.ai/local/val-history', 'a') as f: f.write(json.dumps(record) + '\\n')
fail = os.environ.get('MOCK_VALIDATE_FAIL')
if fail and fail in (record.get('detail'), 'all'): sys.exit(1)
PY
"""

    def runner_ready(self, queue=None):
        """The fixture gate records the observation it runs under (val-history) and fails on demand."""
        self.ready(queue)
        (self.project / '.ai/validate').write_text(self.RECORDING_VALIDATE)
        self.commit('recording fixture gate')

    def validated(self):
        path = self.project / '.ai/local/val-history'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def runner_pipeline(self, expected=1, **env):
        return self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=expected,
                         **dict({'AI_AUTO_RECOVER': '0'}, **env))

    def test_observation_runner_normal_run_shows_build_then_checks(self):
        self.runner_ready()
        self.tool('ai-run', '--approved')
        built = [r for r in self.seen() if r['stage'] == 'build']
        self.assertEqual(len(built), 1)
        self.assertRegex(built[0]['detail'], r'^T001 · .+ · 1/1$')
        details = [r['detail'] for r in self.validated() if r['stage'] == 'checks']
        self.assertEqual(details, ['T001', 'final'])
        final = self.observation()
        self.assertEqual((final['stage'], final['state'], final['detail']), ('checks', 'active', 'final · passed'))

    def test_observation_runner_failing_post_task_gate_ends_on_checks(self):
        self.runner_ready()
        self.runner_pipeline(MOCK_VALIDATE_FAIL='T001')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('checks', 'stopped'))

    def test_observation_runner_failing_final_gate_ends_on_checks(self):
        self.runner_ready()
        self.runner_pipeline(MOCK_VALIDATE_FAIL='final')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('checks', 'stopped'))
        self.assertIn('Final validation failed', stopped['note'])

    def test_observation_runner_failing_install_ends_on_setup(self):
        self.deps_ready()
        self.runner_pipeline(MOCK_DEPS='fail')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('setup', 'stopped'))
        self.assertIn('Dependency setup', stopped['note'])

    def test_observation_runner_current_dependencies_record_no_setup(self):
        self.runner_ready()
        self.tool('ai-run', '--approved')
        self.assertNotIn('setup', [r['stage'] for r in self.seen() + self.validated()])

    def test_observation_runner_recovery_install_records_setup_recovering(self):
        self.deps_ready()
        self.plant_observation(stage='build', state='recovering', note='1/2')
        gate = self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_guard_digest']).stdout.strip()
        self.run_cmd(['bash', '-c', 'source .ai/bin/lib/common.sh; ai_deps "$1" 100', 'deps', gate],
                     env=dict(self.env, AI_OBSERVE_RECOVERY='2'))
        record = self.observation()
        self.assertEqual((record['stage'], record['state'], record['note']), ('setup', 'recovering', '2'))

    def test_observation_runner_session_limit_between_tasks_stops_on_build(self):
        self.runner_ready(task('T001') + task('T002'))
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', '--sessions', '1', expected=1,
                  AI_AUTO_RECOVER='0')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state'], stopped['detail']),
                         ('build', 'stopped', 'T001 · checkpointed · 1/2'))
        self.assertIn('Session limit reached', stopped['note'])

    def test_observation_runner_triage_in_a_pipeline_keeps_the_pipeline_detail(self):
        self.ready()
        self.add_origin()
        self.falling_run('4,3,2,1')
        details = [r['detail'] for r in self.seen() if r['stage'] == 'triage']
        self.assertIn('round 1', details)
        self.assertNotIn('', details)

    def test_observation_runner_standalone_triage_records_triage(self):
        self.ready()
        self.tool('ai-run', '--approved')
        self.tool('ai-review', '--base', 'main', MOCK_CODEX='major-always')
        self.commit('record review')
        self.plant_observation()
        self.tool('ai-run', '--approved', '--triage')
        self.assertEqual([(r['stage'], r['state']) for r in self.seen()][-1:], [('triage', 'active')])

    def test_observation_runner_standalone_revise_plan_records_the_round_and_model(self):
        self.revise_ready()
        self.revise()
        revision = [r for r in self.seen() if r['stage'] == 'plan_revision']
        self.assertEqual([r['detail'] for r in revision], ['round 1 · opus'])

    def test_observation_runner_format_retry_shows_on_the_review_boxes(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', AI_SUPERVISE='1',
                  MOCK_CODEX_PLAN_FORMAT='malformed,ok', MOCK_CODEX='empty,success')
        seen = [(r['stage'], r['detail']) for r in self.seen()]
        self.assertIn(('plan_review', 'format retry'), seen)
        self.assertIn(('review', 'format retry'), seen)

    def test_observation_runner_by_hand_plan_review_retry_leaves_another_stage_alone(self):
        self.ready()
        self.plant_observation(stage='build', state='active', detail='T001 · busy')
        before = (self.project / '.ai/local/observation.json').read_bytes()
        self.tool('ai-review', '--plan', AI_SUPERVISE='1', MOCK_CODEX_PLAN_FORMAT='malformed,ok')
        self.assertEqual(self.plan_calls(), 2)
        self.assertEqual((self.project / '.ai/local/observation.json').read_bytes(), before)

    # ---------------------------------------------------------------- recovery records (T005)
    def recorded(self, path):
        """Every JSON record appended to PATH (a mock agent's snapshots of observation.json)."""
        decoder, text, records = json.JSONDecoder(), path.read_text() if path.exists() else '', []
        while text.strip():
            record, end = decoder.raw_decode(text.lstrip())
            records.append(record)
            text = text.lstrip()[end:]
        return records

    def stopped_notifications(self):
        return self.notifications().count('⛔ STOPPED')

    def test_observation_recovery_keeps_the_stage_then_the_resumed_pipeline_replaces_it(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr',
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error-once')
        during = self.recorded(self.base / 'obs-recover')
        self.assertEqual([(r['stage'], r['state'], r['note']) for r in during], [('build', 'recovering', '1/2')])
        # the resumed pipeline's first step replaced the recovering record
        self.assertEqual(self.seen()[-1]['state'], 'active')
        self.assertEqual(self.observation()['state'], 'done')

    def test_observation_recovery_validation_shows_checks_and_its_failure_stops_there(self):
        queue = task('T001').replace('T001.txt\n', 'T001.txt, partial.txt\n')
        self.runner_ready(queue)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1',
                  MOCK_CLAUDE='error-once-partial', MOCK_RECOVER='commit_and_rerun', MOCK_VALIDATE_FAIL='all')
        self.assertEqual(self.stopped_notifications(), 1)
        recovering = [r for r in self.validated() if r['state'] == 'recovering']
        self.assertEqual([(r['stage'], r['note']) for r in recovering], [('checks', '1/2')])
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('checks', 'stopped'))
        self.assertIn('leftover work fails validation', self.notifications())
        self.assertIn('(stopped during implementation)', stopped['note'])

    def test_observation_recovery_validation_failure_after_later_stops_ends_on_checks(self):
        queue = task('T001').replace('T001.txt\n', 'T001.txt, partial.txt\n')
        self.runner_ready(queue)
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1',
                  AI_RECOVER_MAX='9', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        for label in ('review', 're-check', 'pull request'):
            with self.subTest(label):
                self.plant_observation(stage={'review': 'review', 're-check': 'recheck', 'pull request': 'pr'}[label],
                                       state='stopped', note=label)
                (self.project / 'partial.txt').write_text('leftover\n')
                self.tool('ai-recover', '--stage', label, expected=1, MOCK_RECOVER='commit_and_rerun',
                          MOCK_VALIDATE_FAIL='all')
                stopped = self.observation()
                self.assertEqual((stopped['stage'], stopped['state']), ('checks', 'stopped'))
                self.assertIn(f'(stopped during {label})', stopped['note'])

    def test_observation_recovery_unexpected_term_stops_once_and_keeps_the_substage(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1',
                  MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        notified = self.stopped_notifications()
        self.tool('ai-recover', '--stage', 'implementation', expected=143, AI_AUTO_RECOVER='1',
                  MOCK_RECOVER_KILL='1')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('build', 'stopped'))
        self.assertIn('auto-recovery failed unexpectedly (exit 143)', stopped['note'])
        self.assertEqual(self.stopped_notifications(), notified + 1)

    def test_observation_recovery_unexpected_failing_command_stops_once(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1',
                  MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        notified = self.stopped_notifications()
        with open(self.project / '.ai/run-log.md', 'a') as log:  # new bookkeeping only: recovery records it
            log.write('- a later bookkeeping line\n')
        (self.project / '.git/index.lock').write_text('')  # the bookkeeping `git add` fails under set -e
        result = self.tool('ai-recover', '--stage', 'implementation', expected=128, AI_AUTO_RECOVER='1')
        self.assertIn('index.lock', result.stderr)
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('build', 'stopped'))
        self.assertIn('auto-recovery failed unexpectedly (exit 128)', stopped['note'])
        self.assertEqual(self.stopped_notifications(), notified + 1)

    def assert_recovery_install_records(self, mode):
        self.deps_recovery_run(mode, 1)
        during = self.recorded(self.base / 'deps-obs')[-1]
        self.assertEqual((during['stage'], during['state'], during['note']), ('setup', 'recovering', '1/2'))
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('setup', 'stopped'))
        self.assertIn('(stopped during implementation)', stopped['note'])

    def test_observation_recovery_failed_install_shows_setup_then_stops_there(self):
        self.assert_recovery_install_records('fail-later')

    def test_observation_recovery_changing_install_shows_setup_then_stops_there(self):
        self.assert_recovery_install_records('change-later')

    def test_observation_recovery_stored_decision_stops_on_plan_revision(self):
        self.revision_written(findings='P1|Rollback choice;P2|Gap in tests',
                              MOCK_CLAUDE='revise-needs-human', MOCK_QUESTION='Keep option A or switch to B?')
        self.plant_observation(stage='plan_review', state='active')
        notified = self.stopped_notifications()
        self.resume('watchdog', expected=1, MOCK_CODEX_PLAN='major')
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('plan_revision', 'stopped'))
        self.assertIn('Keep option A or switch to B?', stopped['note'])
        self.assertEqual(self.stopped_notifications(), notified + 1)

    def test_observation_recovery_base_moved_ends_on_none(self):
        self.origin_with_main()
        self.advance_origin_main()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1, AI_AUTO_RECOVER='1')
        self.assertEqual(self.recovery_calls(), [])
        stopped = self.observation()
        self.assertEqual((stopped['stage'], stopped['state']), ('none', 'stopped'))
        self.assertIn('moved past the branch', stopped['note'])

    def test_observation_recovery_changed_gate_leaves_the_recovering_record_and_no_log_line(self):
        self.ready()
        self.tool('ai-pipeline', '--approved', '--base', 'main', '--no-pr', expected=1,
                  AI_AUTO_RECOVER='1', MOCK_CLAUDE='error', MOCK_RECOVER='escalate')
        calls = len(self.recovery_calls())
        (self.project / '.ai/validate').write_text('#!/usr/bin/env bash\nexit 0\n')
        self.commit('weaken the gate')
        log = self.project / '.ai/local/notifications.log'
        before = log.read_text() if log.exists() else ''
        self.tool('ai-recover', '--stage', 'implementation', expected=1, AI_AUTO_RECOVER='1')
        self.assertIn('gate files changed since you approved the run', self.notifications())
        record = self.observation()
        self.assertEqual((record['stage'], record['state']), ('build', 'recovering'))
        self.assertEqual(log.read_text() if log.exists() else '', before)
        self.assertEqual(len(self.recovery_calls()), calls)


class ReviewHistoryTest(unittest.TestCase):
    """T002: review-history summarises earlier review rounds from Git (context only)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai-review-history-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.env = git_fixture_env()
        for command in (['init', '-q', '-b', 'main'], ['config', 'user.name', 'T'],
                        ['config', 'user.email', 't@example.invalid'], ['config', 'commit.gpgsign', 'false']):
            self.git(*command)
        (self.repo / '.ai/reviews').mkdir(parents=True)
        (self.repo / 'code.txt').write_text('0\n')
        self.commit('base')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.counter = 0

    def git(self, *args, expected=0):
        result = subprocess.run(['git', *args], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout

    def commit(self, message, *paths):
        self.git('add', '--all')
        self.git('commit', '-q', '--allow-empty', '-m', message)

    def code(self):
        self.counter += 1
        (self.repo / 'code.txt').write_text(f'{self.counter}\n')
        self.commit(f'fix {self.counter}')
        return self.git('rev-parse', 'HEAD').strip()

    def review(self, head, findings, subject='chore(ai): record independent review'):
        majors = ''.join(f'### {i} {t}\nbody\n' for i, t in findings)
        text = (f'<!-- Host evidence: HEAD {head}; merge-base {self.base}; saved now. -->\n\n'
                f'Overall verdict: x\nFinding counts: BLOCKER=0 MAJOR={len(findings)} MINOR=0\n\n'
                f'## BLOCKER findings\nNone\n\n## MAJOR findings\n{majors}\n## MINOR findings\nNone\n')
        (self.repo / '.ai/reviews/current.md').write_text(text)
        self.commit(subject)

    def triage(self, rows):
        body = ''.join(f'| {f} | {d} | because of reasons here | {t} |\n' for f, d, t in rows)
        (self.repo / '.ai/reviews/dispositions.md').write_text(
            '| Finding | Disposition | Evidence / reason | Fix task |\n| --- | --- | --- | --- |\n' + body)
        self.commit('chore(ai): record review triage')

    def history(self, *args, expected=0):
        result = subprocess.run(['python3', str(HELPER), 'review-history', *args], cwd=self.repo,
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout if expected == 0 else result.stderr

    def head(self):
        return self.git('rev-parse', 'HEAD').strip()

    def test_review_history_no_round_is_empty(self):
        self.code()
        self.assertEqual(self.history('--base', self.base, '--head', 'HEAD'), '')
        self.assertEqual(self.history('--base', self.base, '--head', 'HEAD', '--count').strip(), '0')

    def test_review_history_two_rounds_with_triage_and_last_head(self):
        first = self.code()
        self.review(first, [('M1', 'Race in sync'), ('M2', 'Missing check')])
        self.triage([('M1', 'accepted', 'T012'), ('M2', 'rejected', '')])
        second = self.code()
        self.review(second, [('M3', 'Still broken')])
        self.triage([('M3', 'deferred', '')])
        end = self.code()
        out = self.history('--base', self.base, '--head', end)
        self.assertIn('## Previous review rounds', out)
        self.assertIn(f'### Round 1 (HEAD {first[:7]})', out)
        self.assertIn('- M1 [MAJOR] Race in sync — accepted (T012)', out)
        self.assertIn('- M2 [MAJOR] Missing check — rejected', out)
        self.assertIn(f'### Round 2 (HEAD {second[:7]})', out)
        self.assertIn('- M3 [MAJOR] Still broken — deferred', out)
        self.assertEqual(self.history('--base', self.base, '--head', end, '--last-head').strip(), second)

    def test_review_history_round_without_triage(self):
        first = self.code()
        self.review(first, [('M1', 'Race in sync')])
        out = self.history('--base', self.base, '--head', 'HEAD')
        self.assertIn('- M1 [MAJOR] Race in sync — no triage recorded', out)

    def test_review_history_ignores_review_subject_without_current_change(self):
        self.code()
        self.commit('chore(ai): record independent review')
        self.assertEqual(self.history('--base', self.base, '--head', 'HEAD'), '')

    def test_review_history_cap_drops_oldest_and_count_is_uncapped(self):
        for number in range(8):
            reviewed = self.code()
            self.review(reviewed, [(f'M{number}', 'x' * 400), (f'N{number}', 'y' * 400)])
            self.triage([(f'M{number}', 'accepted', 'T001'), (f'N{number}', 'accepted', 'T002')])
        out = self.history('--base', self.base, '--head', 'HEAD')
        self.assertLessEqual(len(out), 6000)
        self.assertRegex(out, r'\(\d+ earlier rounds omitted\)')
        self.assertIn('### Round 8', out)
        self.assertNotIn('### Round 1 ', out)
        self.assertEqual(self.history('--base', self.base, '--head', 'HEAD', '--count').strip(), '8')

    def test_review_history_current_excludes_the_current_review(self):
        first = self.code()
        self.review(first, [('M1', 'Race in sync')])
        self.triage([('M1', 'accepted', 'T012')])
        second = self.code()
        self.review(second, [('M2', 'Another')])  # committed as the current review, after its HEAD
        out = self.history('--current')
        self.assertIn('M1', out)
        self.assertNotIn('M2', out)
        self.assertEqual(self.history('--current', '--count').strip(), '1')

    def test_review_history_current_without_header_fails(self):
        self.code()
        self.assertIn('host evidence header', self.history('--current', expected=1))
        (self.repo / '.ai/reviews/current.md').write_text('no header\n')
        self.assertIn('host evidence header', self.history('--current', expected=1))


class ParallelRunnerTest(unittest.TestCase):
    """FL-11: tests/run_parallel.py shards the suite without changing what is tested."""

    RUNNER = ROOT / 'tests/run_parallel.py'
    # How long a stop may take: well under the sleepers' LONG_RUN_TIMEOUT, with room for
    # stop()'s TERMINATE_GRACE (5 s) on top.
    STOP_BOUND = SHORT_TIMEOUT + 10

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ai-parallel-test-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.suite = self.base / 'suite'
        self.suite.mkdir()
        self.elsewhere = self.base / 'elsewhere'
        self.elsewhere.mkdir()
        # No PYTHONPATH: the runner must give each shard the discovery directory itself.
        self.env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'AI_TEST_WORKERS')}
        self.env['AI_TEST_WORKERS'] = '2'

    def write(self, name, body):
        (self.suite / name).write_text('import os, unittest\n\n\nclass Sample(unittest.TestCase):\n' + body)

    def runner(self, *args, cwd=None, workers=None, expected=0):
        env = dict(self.env)
        if workers is not None:
            env['AI_TEST_WORKERS'] = workers
        result = subprocess.run([sys.executable, str(self.RUNNER), *args], cwd=cwd or ROOT, env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=PIPELINE_TIMEOUT)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_parallel_runner_all_pass_from_repo_root_and_unrelated_cwd(self):
        self.write('test_one.py', '    def test_a(self): pass\n    def test_b(self): pass\n')
        self.write('test_two.py', '    def test_c(self): pass\n')
        for cwd in (ROOT, self.elsewhere):
            result = self.runner('--start-dir', str(self.suite), cwd=cwd)
            self.assertIn('Ran 3 tests', result.stdout)
            self.assertIn('3 batches on 2 workers, 3 collected', result.stdout)
            self.assertNotIn('ModuleNotFoundError', result.stdout)
        relative = self.runner('--start-dir', 'suite', cwd=self.base)
        self.assertIn('Ran 3 tests', relative.stdout)

    def test_parallel_runner_failing_test_prints_traceback(self):
        self.write('test_one.py', '    def test_a(self): pass\n'
                   '    def test_b(self): self.assertEqual(1, 2, "distinctive failure")\n')
        result = self.runner('--start-dir', str(self.suite), expected=1)
        self.assertIn('Traceback', result.stdout)
        self.assertIn('distinctive failure', result.stdout)
        self.assertIn('FAILED (failing batches:', result.stdout)
        self.assertNotIn('count mismatch', result.stdout)
        # The failing batch is named by its test IDs, not by a number only.
        self.assertRegex(result.stdout, r'Tests in this batch:\n(?:  \S+\n)*  test_one\.Sample\.test_b\n')

    def test_parallel_runner_reports_slowest_tests_and_worker_time(self):
        body = ''.join(f'    def test_slow{n}(self): __import__("time").sleep(0.3)\n' for n in range(3))
        body += ''.join(f'    def test_fast{n}(self): pass\n' for n in range(9))
        self.write('test_one.py', body)
        result = self.runner('--start-dir', str(self.suite))
        self.assertIn('Ran 12 tests', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('OK'), result.stdout)
        self.assertRegex(result.stdout, r'Test time: .* across 2 workers; worker busy: [\d.]+–[\d.]+ s')
        if sys.version_info < (3, 12):
            self.skipTest('unittest --durations needs Python 3.12+')
        listed = re.findall(r'^ +[\d.]+s  (\S+)', result.stdout, re.M)
        self.assertEqual(sorted(listed[:3]), ['test_slow0', 'test_slow1', 'test_slow2'], result.stdout)
        self.assertGreaterEqual(float(re.search(r'Test time: ([\d.]+) s', result.stdout).group(1)), 0.85)

    def test_parallel_runner_interleaves_batches_of_adjacent_slow_tests(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))
        import run_parallel
        for count, workers in ((4, 2), (12, 2), (50, 3), (700, 8), (5, 1)):
            ids = [f'mod.Class.test_{n:04d}' for n in range(count)]
            batches = run_parallel.make_batches(ids, workers)
            with self.subTest(count=count, workers=workers):
                self.assertEqual(sorted(sum(batches, [])), ids)
                self.assertEqual(len(batches), min(count, workers * run_parallel.BATCHES_PER_WORKER))
                where = {test_id: number for number, batch in enumerate(batches) for test_id in batch}
                for first, second in zip(ids, ids[1:]):
                    self.assertNotEqual(where[first], where[second], (first, second))
        self.write('test_one.py', ''.join(f'    def test_sleep{n}(self): __import__("time").sleep(1)\n'
                                          for n in range(4)))
        started = time.monotonic()
        result = self.runner('--start-dir', str(self.suite))
        self.assertLess(time.monotonic() - started, 3.5 * TIMEOUT_SCALE, result.stdout)
        self.assertIn('Ran 4 tests', result.stdout)
        self.assertIn('4 batches on 2 workers', result.stdout)

    def test_parallel_runner_durations_parse_tolerates_format_drift(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))
        import run_parallel
        output = ('0.900s     test_noise (outside.the.block)\n'
                  'Slowest test durations\n' + '-' * 70 + '\n'
                  '0.302s     test_a (m.C.test_a)\n'
                  'garbled line\n'
                  '\x1b[1m1.5s test_b (m.C.test_b)\x1b[0m\n'
                  '\n(durations < 0.001s were hidden; use -v to show these durations)\n'
                  'Ran 3 tests in 1.9s\n\nOK\n')
        self.assertEqual(run_parallel.durations(output),
                         [(0.302, 'test_a (m.C.test_a)'), (1.5, 'test_b (m.C.test_b)')])
        self.assertEqual(run_parallel.durations('Ran 1 test in 0.1s\n\nOK\n'), [])

    def colour_env(self, **colours):
        for name in ('NO_COLOR', 'FORCE_COLOR', 'PYTHON_COLORS'):
            self.env.pop(name, None)
        self.env.update(colours)

    def test_parallel_runner_passes_with_caller_colour_settings(self):
        self.write('test_one.py', '    def test_a(self): pass\n    def test_b(self): pass\n')
        for colours in ({'FORCE_COLOR': '3'}, {'PYTHON_COLORS': '1'},
                        {'FORCE_COLOR': '3', 'PYTHON_COLORS': '1'}):
            self.colour_env(**colours)
            result = self.runner('--start-dir', str(self.suite))
            self.assertIn('Ran 2 tests', result.stdout, colours)
            self.assertTrue(result.stdout.rstrip().endswith('OK'), result.stdout)

    def test_parallel_runner_failing_shard_output_has_no_escapes(self):
        self.write('test_one.py', '    def test_a(self): pass\n'
                   '    def test_b(self): self.assertEqual(1, 2, "distinctive failure")\n')
        self.colour_env(PYTHON_COLORS='1')
        result = self.runner('--start-dir', str(self.suite), expected=1)
        self.assertIn('distinctive failure', result.stdout)
        self.assertNotIn('\x1b', result.stdout)

    def test_parallel_runner_summary_parses_coloured_and_plain(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))
        import run_parallel
        plain = 'Ran 3 tests in 0.001s\n\nOK\n'
        coloured = '\x1b[1mRan 3 tests in 0.001s\x1b[0m\n\n\x1b[32mOK\x1b[0m\n'
        self.assertEqual(run_parallel.summary(plain), (3, 'OK'))
        self.assertEqual(run_parallel.summary(coloured), (3, 'OK'))
        self.assertEqual(run_parallel.summary('\x1b[31mFAILED (failures=1)\x1b[0m\n'), (None, 'FAILED'))
        self.assertEqual(run_parallel.summary('boom\n'), (None, None))

    def test_parallel_runner_zero_tests_fail(self):
        result = self.runner('--start-dir', str(self.suite), expected=1)
        self.assertIn('no tests collected', result.stdout)

    def test_parallel_runner_crashed_shard_fails_with_count_mismatch(self):
        self.write('test_one.py', '    def test_a(self): pass\n    def test_b(self): os._exit(3)\n'
                   '    def test_c(self): pass\n    def test_d(self): pass\n')
        result = self.runner('--start-dir', str(self.suite), expected=1)
        self.assertIn('crashed (exit code 3)', result.stdout)
        self.assertRegex(result.stdout, r'count mismatch: ran \d of 4 collected tests')

    def test_parallel_runner_import_error_fails(self):
        (self.suite / 'test_broken.py').write_text('import no_such_module_for_this_test\n')
        result = self.runner('--start-dir', str(self.suite), expected=1)
        self.assertIn('no_such_module_for_this_test', result.stdout)
        self.assertIn('test discovery failed', result.stdout)

    def test_parallel_runner_rejects_invalid_workers(self):
        self.write('test_one.py', '    def test_a(self): pass\n')
        for value in ('0', 'x', '-2'):
            result = self.runner('--start-dir', str(self.suite), workers=value, expected=1)
            self.assertIn('AI_TEST_WORKERS must be a positive integer', result.stderr)
        self.runner('--start-dir', str(self.suite), workers='')  # empty means the default

    def test_parallel_runner_collect_only_matches_serial_discovery(self):
        # A fresh loader: `unittest -k` sets name patterns on the default loader of this process.
        expected = unittest.TestLoader().discover(str(ROOT / 'tests')).countTestCases()
        result = self.runner('--collect-only', cwd=self.elsewhere)
        self.assertEqual(result.stdout.strip(), f'Collected {expected} tests')

    # Review M3: a stopped batch must take the subprocesses its tests started with it, or one
    # holding the batch's output pipe keeps the dispatcher waiting.
    def write_sleeper(self):
        """A batch whose test starts a long sleep that inherits the batch's stdout, publishes
        its PID and waits for it."""
        self.pidfile = self.base / 'sleeper.pid'
        self.addCleanup(self.kill_sleeper)
        self.write('test_sleeper.py',
                   '    def test_sleep(self):\n'
                   '        import subprocess\n'
                   f'        child = subprocess.Popen(["sleep", "{int(LONG_RUN_TIMEOUT)}"])\n'
                   f'        path = {str(self.pidfile)!r}\n'
                   '        open(path + ".tmp", "w").write(str(child.pid))\n'
                   '        os.replace(path + ".tmp", path)\n'
                   '        child.wait()\n')
        self.write('test_other.py', '    def test_a(self): pass\n')

    def sleeper_pid(self):
        deadline = time.monotonic() + MEDIUM_TIMEOUT
        while not self.pidfile.exists():
            if time.monotonic() > deadline:
                raise AssertionError('the sleeper test never started')
            time.sleep(0.05)
        return int(self.pidfile.read_text())

    def sleeper_gone(self, pid):
        """True once the PID is gone or a zombie waiting for its new parent to reap it."""
        deadline = time.monotonic() + SHORT_TIMEOUT
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            try:
                if Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                    return True
            except (OSError, IndexError):
                pass
            time.sleep(0.05)
        return False

    def kill_sleeper(self):
        try:
            os.kill(int(self.pidfile.read_text()), signal.SIGKILL)
        except (OSError, ValueError):
            pass

    def run_dispatcher(self, dispatcher):
        """Run the dispatcher on a named thread (so a regression fails instead of hanging the
        suite); return (finished, the exception it raised)."""
        outcome = {}

        def target():
            try:
                dispatcher.run()
            except BaseException as error:
                outcome['error'] = error
        thread = threading.Thread(target=target, name='dispatcher-run', daemon=True)
        thread.start()
        pid = self.sleeper_pid()
        thread.join(self.STOP_BOUND)
        return not thread.is_alive(), outcome.get('error'), pid

    def dispatcher(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))
        import run_parallel
        self.write_sleeper()
        batches = [['test_sleeper.Sample.test_sleep'], ['test_other.Sample.test_a']]
        return run_parallel, run_parallel.Dispatcher(batches, 2, self.suite)

    def test_parallel_runner_worker_error_kills_batch_descendants(self):
        run_parallel, dispatcher = self.dispatcher()
        real_popen = subprocess.Popen

        def popen(command, *args, **kwargs):
            if 'test_other.Sample.test_a' in command:
                self.sleeper_pid()  # fail only once the other batch has its subprocess
                raise OSError('injected launch failure')
            return real_popen(command, *args, **kwargs)
        with mock.patch.object(run_parallel.subprocess, 'Popen', popen):
            finished, error, pid = self.run_dispatcher(dispatcher)
        self.assertTrue(finished, 'Dispatcher.run() still blocked after the worker error')
        self.assertIsInstance(error, OSError)
        self.assertIn('injected launch failure', str(error))
        self.assertTrue(self.sleeper_gone(pid), f'sleeper {pid} survived the stop')

    def test_parallel_runner_interrupt_kills_batch_descendants(self):
        run_parallel, dispatcher = self.dispatcher()
        real_join = threading.Thread.join
        interrupted = []

        def join(thread, timeout=None):
            if threading.current_thread().name == 'dispatcher-run' and not interrupted:
                interrupted.append(True)
                self.sleeper_pid()
                raise KeyboardInterrupt
            return real_join(thread, timeout)
        with mock.patch.object(threading.Thread, 'join', join):
            finished, error, pid = self.run_dispatcher(dispatcher)
        self.assertTrue(finished, 'Dispatcher.run() still blocked after the interrupt')
        self.assertIsInstance(error, KeyboardInterrupt)
        self.assertTrue(self.sleeper_gone(pid), f'sleeper {pid} survived the stop')

    def test_parallel_runner_sigterm_kills_batch_descendants(self):
        # ai-check's `timeout` signals its own process group, which no longer holds the batches.
        self.write_sleeper()
        process = subprocess.Popen([sys.executable, str(self.RUNNER), '--start-dir', str(self.suite)],
                                   cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(process.kill)
        pid = self.sleeper_pid()
        process.terminate()
        output, _ = process.communicate(timeout=self.STOP_BOUND)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, output)
        self.assertTrue(self.sleeper_gone(pid), f'sleeper {pid} survived the SIGTERM')

    # FL-27: as a child subreaper the runner adopts what the batches orphan and reaps it.
    def write_orphan(self):
        """A test whose `sh` backgrounds a 1 s sleep and exits at once, orphaning it; it records
        the sleeper's ppid as /proc shows it and the runner's pid (the batch's parent)."""
        self.pidfile = self.base / 'sleeper.pid'
        # No kill on cleanup: the sleep ends by itself, and once reaped its pid may be reused.
        self.seen = self.base / 'seen'
        self.write('test_orphan.py',
                   '    def test_spawn(self):\n'
                   '        import subprocess\n'
                   f'        path = {str(self.pidfile)!r}\n'
                   '        subprocess.run(["sh", "-c", "sleep 1 & echo $! > " + path + ".tmp"], check=True)\n'
                   '        os.replace(path + ".tmp", path)\n'
                   '        pid = int(open(path).read())\n'
                   '        stat = open(f"/proc/{pid}/stat").read()\n'
                   f'        open({str(self.seen)!r}, "w").write(stat.rsplit(")", 1)[1].split()[1]'
                   ' + " " + str(os.getppid()))\n')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'child subreapers are Linux-only')
    def test_parallel_runner_subreaper_adopts_and_reaps_orphans(self):
        self.write_orphan()
        # Keeps the run going until the sleeper has exited, then wants it reaped (gone from
        # /proc, not a zombie) and no zombie child of the runner left.
        self.write('test_wait.py',
                   '    def test_wait(self):\n'
                   '        import time\n'
                   f'        path, deadline = {str(self.pidfile)!r}, time.monotonic() + {MEDIUM_TIMEOUT}\n'
                   '        while not os.path.exists(path):\n'
                   '            self.assertLess(time.monotonic(), deadline, "the orphan never started")\n'
                   '            time.sleep(0.05)\n'
                   '        pid = int(open(path).read())\n'
                   '        while os.path.exists(f"/proc/{pid}"):\n'
                   '            self.assertLess(time.monotonic(), deadline, f"orphan {pid} was not reaped")\n'
                   '            time.sleep(0.05)\n'
                   '        runner = os.getppid()\n'
                   '        while True:\n'
                   '            zombies = []\n'
                   '            for entry in filter(str.isdigit, os.listdir("/proc")):\n'
                   '                try:\n'
                   '                    fields = open(f"/proc/{entry}/stat").read().rsplit(")", 1)[1].split()\n'
                   '                except OSError:\n'
                   '                    continue\n'
                   '                if fields[0] == "Z" and int(fields[1]) == runner:\n'
                   '                    zombies.append(entry)\n'
                   '            if not zombies:\n'
                   '                break\n'
                   '            self.assertLess(time.monotonic(), deadline, f"zombie children of the runner: {zombies}")\n'
                   '            time.sleep(0.05)\n')
        result = self.runner('--start-dir', str(self.suite))
        self.assertTrue(result.stdout.rstrip().endswith('OK'), result.stdout)
        self.assertIn('Ran 2 tests', result.stdout)
        ppid, runner = self.seen.read_text().split()
        self.assertEqual(ppid, runner, 'the orphan was not reparented to the runner')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'child subreapers are Linux-only')
    def test_parallel_runner_subreaper_keeps_failure_and_crash_reports(self):
        self.write_orphan()
        self.write('test_fail.py', '    def test_fail(self): self.assertEqual(1, 2, "distinctive failure")\n')
        self.write('test_crash.py', '    def test_crash(self): os._exit(3)\n')
        result = self.runner('--start-dir', str(self.suite), expected=1)
        self.assertIn('distinctive failure', result.stdout)
        self.assertIn('FAILED (exit code 1)', result.stdout)
        self.assertIn('crashed (exit code 3) without a unittest summary', result.stdout)
        self.assertIn('FAILED (failing batches:', result.stdout)
        ppid, runner = self.seen.read_text().split()
        self.assertEqual(ppid, runner)

    def test_parallel_runner_subreaper_stat_parse_and_main_only(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))
        import run_parallel
        # Fields 5..52 hold their own numbers, so starttime (field 22) reads 22.
        text = '4321 (we) (ird name) R 99 ' + ' '.join(str(field) for field in range(5, 53)) + '\n'
        self.assertEqual(run_parallel.parse_stat(text), ('R', 99, 22))
        self.assertIsNone(run_parallel.parse_stat('4321 (truncated'))
        self.assertIsNone(run_parallel.parse_stat('4321 (x) S notanumber'))
        if sys.platform.startswith('linux'):
            self.assertEqual(run_parallel.proc_stat(os.getpid())[1], os.getppid())
            self.assertIn(os.getpid(), run_parallel.children_of(os.getppid()))
        tree = ast.parse(self.RUNNER.read_text())
        callers = []
        for function in ast.walk(tree):
            if isinstance(function, (ast.FunctionDef, ast.ClassDef)):
                for node in ast.walk(function):
                    if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'enable_subreaper':
                        callers.append(function.name)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'enable_subreaper']
        # One call, inside main() only (not at module level, not in Dispatcher).
        self.assertEqual(len(calls), 1)
        self.assertEqual(callers, ['main'])

    # FL-27 part 2: a stop terminates the runner's whole descendant tree, including GNU
    # `timeout` (its own process group) and detached sessions. The Dispatcher runs in a child
    # driver: the test process itself must never become a subreaper.
    def tree_guard(self):
        if not sys.platform.startswith('linux'):
            self.skipTest('the descendant walk needs Linux /proc and a child subreaper')
        if not shutil.which('timeout') or not shutil.which('setsid'):
            self.skipTest('GNU timeout and setsid are needed')
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))
        import run_parallel
        self.rp = run_parallel
        self.pidfiles = []
        self.addCleanup(self.kill_recorded)

    def kill_recorded(self):
        for path in self.pidfiles:
            try:
                os.kill(int(path.read_text()), signal.SIGKILL)
            except (OSError, ValueError):
                pass

    def pidfile(self, name):
        path = self.base / name
        self.pidfiles.append(path)
        return path

    def write_tree_test(self, name, shell, popen_pidfile=None):
        """A test whose `sh -c <shell>` (or `timeout 120 sh -c`) runs in the batch and is
        waited for; with `popen_pidfile` the command is `timeout 120 sh -c <shell>` and the
        `timeout` pid is written there."""
        command = (['timeout', '120', 'sh', '-c', shell] if popen_pidfile else ['sh', '-c', shell])
        body = ('    def test_tree(self):\n'
                '        import subprocess\n'
                f'        child = subprocess.Popen({command!r})\n')
        if popen_pidfile:
            body += (f'        path = {str(popen_pidfile)!r}\n'
                     '        open(path + ".tmp", "w").write(str(child.pid))\n'
                     '        os.replace(path + ".tmp", path)\n')
        body += '        child.wait()\n'
        self.write(name, body)

    def write_timeout_tree(self):
        self.timeout_pid, self.child_pid = self.pidfile('timeout.pid'), self.pidfile('child.pid')
        self.write_tree_test('test_tree.py', f'echo $$ > {self.child_pid}.tmp; mv {self.child_pid}.tmp '
                             f'{self.child_pid}; exec sleep 120', popen_pidfile=self.timeout_pid)
        return [self.timeout_pid, self.child_pid]

    def write_stub_tree(self):
        self.stub_pid = self.pidfile('stub.pid')
        inner = f'trap "" TERM; echo $$ > {self.stub_pid}.tmp; mv {self.stub_pid}.tmp {self.stub_pid}; exec sleep 120'
        self.write_tree_test('test_stub.py', f"setsid sh -c '{inner}' </dev/null >/dev/null 2>&1 & "
                             'while :; do sleep 1; done')
        return [self.stub_pid]

    def wait_pidfiles(self, paths):
        deadline = time.monotonic() + MEDIUM_TIMEOUT
        while not all(path.exists() for path in paths):
            self.assertLess(time.monotonic(), deadline, f'pid files never appeared: {paths}')
            time.sleep(0.05)
        return [int(path.read_text()) for path in paths]

    def driver(self, scenario, batches, workers=2):
        """Write a driver that runs a subreaper Dispatcher on `batches` after `scenario`
        (patches) and prints the exception run() raised; returns its path."""
        script = self.base / 'driver.py'
        script.write_text(
            'import os, subprocess, sys, threading, time\n'
            f'sys.path.insert(0, {str(ROOT / "tests")!r})\n'
            'import run_parallel\n'
            f'PIDFILES = {[str(path) for path in self.pidfiles]!r}\n'
            f'BOUND = {MEDIUM_TIMEOUT!r}\n'
            'def wait_pidfiles():\n'
            '    deadline = time.monotonic() + BOUND\n'
            '    while not all(os.path.exists(path) for path in PIDFILES):\n'
            '        if time.monotonic() > deadline:\n'
            '            raise SystemExit("driver: pid files never appeared")\n'
            '        time.sleep(0.05)\n'
            'reap = run_parallel.enable_subreaper()\n'
            'assert reap, "driver: no subreaper"\n'
            f'dispatcher = run_parallel.Dispatcher({batches!r}, {workers}, {str(self.suite)!r}, reap=reap)\n'
            + scenario +
            'try:\n'
            '    dispatcher.run()\n'
            'except BaseException as error:\n'
            '    print("raised", type(error).__name__, error, flush=True)\n'
            '    sys.exit(3)\n'
            'print("no error", flush=True)\n')
        return script

    def run_driver(self, script, paths, bound):
        """Run the driver; return its result and how long it took after `paths` existed (the
        stop starts then), failing when that exceeds `bound`."""
        process = subprocess.Popen([sys.executable, str(script)], cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(process.kill)
        self.wait_pidfiles(paths)
        started = time.monotonic()
        stdout, stderr = process.communicate(timeout=bound + MEDIUM_TIMEOUT)
        elapsed = time.monotonic() - started
        result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        self.assertLess(elapsed, bound, stdout + stderr)
        return result

    FAIL_SECOND_LAUNCH = (
        'real_popen = subprocess.Popen\n'
        'def popen(command, *args, **kwargs):\n'
        '    if "test_other.Sample.test_a" in command:\n'
        '        wait_pidfiles()\n'
        '        raise OSError("injected launch failure")\n'
        '    return real_popen(command, *args, **kwargs)\n'
        'run_parallel.subprocess.Popen = popen\n')

    def state_of(self, pid):
        """The /proc state letter of `pid`, or None when it is gone."""
        stat = self.rp.proc_stat(pid)
        return stat and stat[0]

    def assert_gone(self, pids):
        for pid in pids:
            self.assertTrue(self.sleeper_gone(pid), f'{pid} survived the stop ({self.state_of(pid)})')

    def test_parallel_runner_tree_worker_failure_kills_timeout_group(self):
        self.tree_guard()
        paths = self.write_timeout_tree()
        self.write('test_other.py', '    def test_a(self): pass\n')
        script = self.driver(self.FAIL_SECOND_LAUNCH, [['test_tree.Sample.test_tree'], ['test_other.Sample.test_a']])
        result = self.run_driver(script, paths, (self.rp.TERMINATE_GRACE + 10) * TIMEOUT_SCALE)
        self.assertIn('raised OSError injected launch failure', result.stdout, result.stdout + result.stderr)
        self.assert_gone(self.wait_pidfiles(paths))

    def start_runner(self, wrapper=None):
        command = [sys.executable, str(self.RUNNER), '--start-dir', str(self.suite)]
        if wrapper:
            command = [sys.executable, '-c', wrapper, *command[1:]]
        process = subprocess.Popen(command, cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(process.kill)
        return process

    def stop_runner(self, process, paths, signum, bound):
        pids = self.wait_pidfiles(paths)
        process.send_signal(signum)
        started = time.monotonic()
        output, _ = process.communicate(timeout=bound + MEDIUM_TIMEOUT)
        self.assertLess(time.monotonic() - started, bound, output)
        return pids, output

    def test_parallel_runner_tree_sigterm_kills_timeout_group(self):
        self.tree_guard()
        paths = self.write_timeout_tree()
        process = self.start_runner()
        pids, output = self.stop_runner(process, paths, signal.SIGTERM,
                                        (self.rp.TERMINATE_GRACE + 10) * TIMEOUT_SCALE)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, output)
        self.assert_gone(pids)

    def test_parallel_runner_tree_sigint_to_runner_alone_kills_timeout_group(self):
        self.tree_guard()
        paths = self.write_timeout_tree()
        # The runner gets Python's SIGINT handler even when this test inherited SIGINT ignored.
        wrapper = ('import runpy, signal, sys; signal.signal(signal.SIGINT, signal.default_int_handler); '
                   'sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name="__main__")')
        process = self.start_runner(wrapper)
        pids, output = self.stop_runner(process, paths, signal.SIGINT,
                                        (self.rp.TERMINATE_GRACE + 10) * TIMEOUT_SCALE)
        self.assertNotEqual(process.returncode, 0, output)
        self.assertIn('KeyboardInterrupt', output)
        self.assert_gone(pids)

    def test_parallel_runner_tree_sigterm_kills_stubborn_detached_descendant(self):
        self.tree_guard()
        paths = self.write_stub_tree()
        process = self.start_runner()
        pids, output = self.stop_runner(process, paths, signal.SIGTERM,
                                        (self.rp.TERMINATE_GRACE * 2 + 10) * TIMEOUT_SCALE)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, output)
        # Right after the runner returned, no extra polling: the completion barrier saw to it.
        for pid in pids:
            self.assertIn(self.state_of(pid), (None, 'Z'), f'stub {pid} survived the stop')

    def test_parallel_runner_tree_kills_process_forked_during_stop(self):
        self.tree_guard()
        parent, forked = self.pidfile('parent.pid'), self.pidfile('forked.pid')
        self.write_tree_test('test_tree.py', f'trap "sleep 120 & echo \\$! > {forked}; wait" TERM; '
                             f'echo $$ > {parent}.tmp; mv {parent}.tmp {parent}; while :; do sleep 1; done')
        self.write('test_other.py', '    def test_a(self): pass\n')
        self.pidfiles.remove(forked)  # written only during the stop
        script = self.driver(self.FAIL_SECOND_LAUNCH, [['test_tree.Sample.test_tree'], ['test_other.Sample.test_a']])
        self.pidfiles.append(forked)
        result = self.run_driver(script, [parent], (self.rp.TERMINATE_GRACE * 2 + 10) * TIMEOUT_SCALE)
        self.assertIn('raised OSError', result.stdout, result.stdout + result.stderr)
        pids = [int(parent.read_text())]
        if forked.exists() and forked.read_text().strip():
            pids.append(int(forked.read_text()))
        self.assert_gone(pids)

    def test_parallel_runner_tree_completion_barrier_failure_exits_non_zero(self):
        self.tree_guard()
        paths = self.write_timeout_tree()
        self.write('test_other.py', '    def test_a(self): pass\n')
        # Above the kernel's largest pid_max (2**22): never a real process.
        phantom = 2 ** 22 + 1
        scenario = self.FAIL_SECOND_LAUNCH + (
            'real_live = run_parallel.Dispatcher.live_descendants\n'
            f'run_parallel.Dispatcher.live_descendants = lambda self: {{**real_live(self), {phantom}: 0}}\n')
        script = self.driver(scenario, [['test_tree.Sample.test_tree'], ['test_other.Sample.test_a']])
        result = self.run_driver(script, paths, (self.rp.FINAL_WAIT + self.rp.TERMINATE_GRACE + 10) * TIMEOUT_SCALE)
        self.assertIn(f'run_parallel: could not terminate descendants: {phantom}', result.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assert_gone(self.wait_pidfiles(paths))

    def test_parallel_runner_tree_main_exits_non_zero_when_cleanup_failed(self):
        self.tree_guard()
        self.write('test_one.py', '    def test_a(self): pass\n')
        wrapper = ('import runpy, sys; sys.argv = sys.argv[1:]; sys.path.insert(0, sys.argv[0].rsplit("/", 1)[0]); '
                   'import run_parallel; real = run_parallel.Dispatcher.run\n'
                   'def run(self):\n'
                   '    results = real(self); self.cleanup_failed = [4242]; return results\n'
                   'run_parallel.Dispatcher.run = run; sys.exit(run_parallel.main())')
        process = self.start_runner(wrapper)
        output, _ = process.communicate(timeout=PIPELINE_TIMEOUT)
        self.assertEqual(process.returncode, 1, output)
        self.assertIn('descendants survived the stop: 4242', output)

    def test_parallel_runner_tree_concurrent_stops_never_reap_during_shutdown(self):
        self.tree_guard()
        stubs = []
        for number in (1, 2):
            stub = self.pidfile(f'stub{number}.pid')
            stubs.append(stub)
            inner = f'trap "" TERM; echo $$ > {stub}.tmp; mv {stub}.tmp {stub}; exec sleep 120'
            self.write_tree_test(f'test_stub{number}.py', f"setsid sh -c '{inner}' </dev/null >/dev/null 2>&1 & "
                                 'while :; do sleep 1; done')
        # Both workers fail at once (after both stubs exist) and both call stop(), while run()'s
        # reap loop keeps polling (the stubs ignore SIGTERM, so the stop lasts TERMINATE_GRACE);
        # a reap during the kill rounds would free a pid for reuse.
        scenario = (
            'barrier = threading.Barrier(2, timeout=BOUND)\n'
            'def drain(self, process):\n'
            '    wait_pidfiles()\n'
            '    barrier.wait()\n'
            '    raise RuntimeError(f"injected failure {process.pid}")\n'
            'run_parallel.Dispatcher.drain = drain\n'
            'real_waitpid = os.waitpid\n'
            'during_stop = []\n'
            'def waitpid(pid, options):\n'
            '    if sys._getframe(1).f_code.co_name == "reap_adopted" and dispatcher.terminating \\\n'
            '            and not dispatcher.stop_done.is_set():\n'
            '        during_stop.append(pid)\n'
            '    return real_waitpid(pid, options)\n'
            'os.waitpid = waitpid\n'
            'import atexit\n'
            'atexit.register(lambda: print("during_stop", during_stop, "rounds", dispatcher.kill_rounds,\n'
            '                              "errors", len(dispatcher.errors), "alive",\n'
            '                              [t.name for t in threading.enumerate() if t.daemon], flush=True))\n')
        script = self.driver(scenario, [['test_stub1.Sample.test_tree'], ['test_stub2.Sample.test_tree']])
        result = self.run_driver(script, stubs, (self.rp.TERMINATE_GRACE * 2 + 10) * TIMEOUT_SCALE)
        output = result.stdout + result.stderr
        self.assertIn('raised RuntimeError injected failure', result.stdout, output)
        self.assertIn('during_stop [] rounds 1 errors 2 alive []', result.stdout, output)
        self.assert_gone(self.wait_pidfiles(stubs))

    # Review M1: a process name is arbitrary bytes, and the scan reads every process on the host.
    def test_parallel_runner_tree_non_utf8_stat_parse(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))
        import run_parallel
        # Fields 5..52 hold their own numbers, so starttime (field 22) reads 22.
        text = b'4321 (\xff) \xfe) Z 99 ' + ' '.join(str(field) for field in range(5, 53)).encode() + b'\n'
        self.assertEqual(run_parallel.parse_stat(text), ('Z', 99, 22))
        self.assertIsNone(run_parallel.parse_stat(b'4321 (\xff'))

    def test_parallel_runner_tree_non_utf8_name(self):
        self.tree_guard()
        named = self.pidfile('named.pid')
        # PR_SET_NAME is 15; the pid file only appears once /proc shows the non-UTF-8 name.
        code = ('import ctypes, os, time; ctypes.CDLL(None).prctl(15, b"\\xff", 0, 0, 0); '
                'assert open("/proc/self/comm", "rb").read() == b"\\xff\\n"; '
                f'path = {str(named)!r}; open(path + ".tmp", "w").write(str(os.getpid())); '
                'os.replace(path + ".tmp", path); time.sleep(120)')
        self.write_tree_test('test_tree.py', f'exec {shlex.quote(sys.executable)} -c {shlex.quote(code)}')
        self.write('test_other.py', '    def test_a(self): pass\n')
        script = self.driver(self.FAIL_SECOND_LAUNCH, [['test_tree.Sample.test_tree'], ['test_other.Sample.test_a']])
        result = self.run_driver(script, [named], (self.rp.TERMINATE_GRACE + 10) * TIMEOUT_SCALE)
        output = result.stdout + result.stderr
        self.assertIn('raised OSError injected launch failure', result.stdout, output)
        self.assertNotIn('UnicodeDecodeError', output)
        self.assert_gone(self.wait_pidfiles([named]))

    def test_parallel_runner_tree_scan_failure_still_signals_batch_groups(self):
        self.tree_guard()
        batch, child = self.pidfile('batch.pid'), self.pidfile('child.pid')
        self.write_tree_test('test_tree.py', f'echo $PPID > {batch}.tmp; mv {batch}.tmp {batch}; '
                             f'echo $$ > {child}.tmp; mv {child}.tmp {child}; exec sleep 120')
        self.write('test_other.py', '    def test_a(self): pass\n')
        scenario = self.FAIL_SECOND_LAUNCH + (
            'def descendants(root, table=None):\n'
            '    raise RuntimeError("injected scan failure")\n'
            'run_parallel.descendants = descendants\n')
        script = self.driver(scenario, [['test_tree.Sample.test_tree'], ['test_other.Sample.test_a']])
        result = self.run_driver(script, [batch, child],
                                 (self.rp.FINAL_WAIT + self.rp.TERMINATE_GRACE + 10) * TIMEOUT_SCALE)
        output = result.stdout + result.stderr
        self.assertIn('raised OSError injected launch failure', result.stdout, output)
        # The failed scans never confirmed the tree gone, so the stop reports it.
        self.assertIn('could not terminate descendants: unknown (descendant scan failed: '
                      "RuntimeError('injected scan failure')", result.stderr)
        self.assert_gone(self.wait_pidfiles([batch, child]))

    # Review M3: when /proc cannot be listed, an empty table proves nothing.
    def proc_listdir_driver(self, body):
        """Run a subreaping driver whose `os.listdir('/proc')` raises PermissionError while
        `failing` is set, then `body`; return its result."""
        script = self.base / 'listdir_driver.py'
        script.write_text(
            'import os, subprocess, sys, time\n'
            f'sys.path.insert(0, {str(ROOT / "tests")!r})\n'
            'import run_parallel\n'
            'assert run_parallel.enable_subreaper(), "driver: no subreaper"\n'
            'real_listdir = os.listdir\n'
            'failing = False\n'
            'def listdir(path="."):\n'
            '    if failing and path == "/proc":\n'
            '        raise PermissionError(13, "injected listdir failure", path)\n'
            '    return real_listdir(path)\n'
            'os.listdir = listdir\n'
            f'dispatcher = run_parallel.Dispatcher([["unused"]], 1, {str(self.suite)!r}, reap=True)\n'
            + body)
        return subprocess.run([sys.executable, str(script)], cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True,
                              timeout=(self.rp.FINAL_WAIT + 10) * TIMEOUT_SCALE + MEDIUM_TIMEOUT)

    def test_parallel_runner_tree_proc_listdir_failure(self):
        self.tree_guard()
        result = self.proc_listdir_driver(
            'child = subprocess.Popen(["sleep", "120"], start_new_session=True)\n'
            'assert child.pid in dispatcher.live_descendants(), "driver: child not seen"\n'
            'failing = True\n'
            'dispatcher.stop()\n'
            'failing = False\n'
            'print("cleanup_failed", *dispatcher.cleanup_failed, sep="|", flush=True)\n'
            'print("child alive", child.poll() is None, flush=True)\n'
            'child.kill()\n'
            'child.wait()\n')
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("cleanup_failed|unknown (descendant scan failed: PermissionError(13, "
                      "'injected listdir failure'))\n", result.stdout, output)
        self.assertIn('run_parallel: could not terminate descendants: unknown (descendant scan failed: '
                      'PermissionError(', result.stderr)
        # No scan succeeded, so nothing signalled the child: the stop saw no tree at all.
        self.assertIn('child alive True', result.stdout, output)

    def test_parallel_runner_tree_proc_listdir_failure_skips_reap_round(self):
        self.tree_guard()
        result = self.proc_listdir_driver(
            'child = subprocess.Popen(["true"])\n'
            'deadline = time.monotonic() + 30\n'
            'while run_parallel.proc_stat(child.pid)[0] != "Z":\n'
            '    assert time.monotonic() < deadline, "driver: no zombie"\n'
            '    time.sleep(0.05)\n'
            'failing = True\n'
            'dispatcher.reap_adopted()\n'
            'print("after failing round", run_parallel.proc_stat(child.pid)[0], flush=True)\n'
            'failing = False\n'
            'dispatcher.reap_adopted()\n'
            'print("after next round", run_parallel.proc_stat(child.pid), flush=True)\n')
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn('after failing round Z', result.stdout, output)
        self.assertIn('after next round None', result.stdout, output)

    # FL-27 part 3: an interrupt while run() is still starting workers (after the first one
    # launched its batch) goes through stop() like any later interrupt.
    def startup_interrupt(self, raised):
        self.tree_guard()
        self.timeout_pid, self.child_pid = self.pidfile('timeout.pid'), self.pidfile('child.pid')
        self.stub_pid = self.pidfile('stub.pid')
        stub = (f'trap "" TERM; echo $$ > {self.stub_pid}.tmp; mv {self.stub_pid}.tmp {self.stub_pid}; '
                'exec sleep 120')
        self.write_tree_test('test_tree.py', f"setsid sh -c '{stub}' </dev/null >/dev/null 2>&1 & "
                             f'echo $$ > {self.child_pid}.tmp; mv {self.child_pid}.tmp {self.child_pid}; '
                             'exec sleep 120', popen_pidfile=self.timeout_pid)
        self.write('test_other.py', '    def test_a(self): pass\n')
        paths = [self.timeout_pid, self.child_pid, self.stub_pid]
        # The main thread's second Thread.start() raises once the first batch's tree exists.
        scenario = (
            'real_start = threading.Thread.start\n'
            'starts = []\n'
            'def start(self):\n'
            '    if threading.current_thread() is threading.main_thread():\n'
            '        starts.append(self)\n'
            '        if len(starts) == 2:\n'
            '            wait_pidfiles()\n'
            f'            raise {raised}\n'
            '    return real_start(self)\n'
            'threading.Thread.start = start\n'
            'import atexit\n'
            'atexit.register(lambda: print("rounds", dispatcher.kill_rounds, flush=True))\n')
        script = self.driver(scenario, [['test_tree.Sample.test_tree'], ['test_other.Sample.test_a']])
        result = self.run_driver(script, paths,
                                 (self.rp.TERMINATE_GRACE * 2 + self.rp.FINAL_WAIT + 10) * TIMEOUT_SCALE)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn('rounds 1\n', result.stdout, output)
        self.assertNotIn('RuntimeError', output)
        # Right after the driver exited, no extra polling: the completion barrier saw to it.
        for pid in self.wait_pidfiles(paths):
            self.assertIn(self.state_of(pid), (None, 'Z'), f'{pid} survived the stop')
        return result

    def test_parallel_runner_startup_sigint_during_worker_start_stops_batch(self):
        result = self.startup_interrupt('KeyboardInterrupt')
        self.assertIn('raised KeyboardInterrupt', result.stdout, result.stdout + result.stderr)

    def test_parallel_runner_startup_sigterm_during_worker_start_stops_batch(self):
        result = self.startup_interrupt('SystemExit(143)')
        self.assertIn('raised SystemExit 143', result.stdout, result.stdout + result.stderr)


class TestHarnessTimeoutsTest(unittest.TestCase):
    def scale(self, **env):
        base = {k: v for k, v in os.environ.items() if k not in ('CI', 'AI_TEST_TIMEOUT_SCALE')}
        return subprocess.run([sys.executable, '-I', '-c',
                               'import sys; sys.path.insert(0, sys.argv[1]); import timeouts; print(timeouts.TIMEOUT_SCALE)',
                               str(ROOT / 'tests')],
                              env=dict(base, **env), capture_output=True, text=True, timeout=SHORT_TIMEOUT)

    def test_test_harness_timeouts_pipeline_commands_get_the_pipeline_bound(self):
        for name in ('ai-pipeline', 'ai-recover'):
            self.assertEqual(command_timeout(name), PIPELINE_TIMEOUT, name)
        self.assertEqual(command_timeout('ai-check'), COMMAND_TIMEOUT)
        self.assertGreater(PIPELINE_TIMEOUT, COMMAND_TIMEOUT)

    def test_test_harness_timeouts_scale_rule(self):
        for env, expected in (({}, 1.0), ({'CI': 'true'}, 2.0), ({'CI': 'false'}, 1.0),
                              ({'AI_TEST_TIMEOUT_SCALE': '3'}, 3.0),
                              ({'CI': 'true', 'AI_TEST_TIMEOUT_SCALE': '3'}, 3.0)):
            with self.subTest(env=env):
                result = self.scale(**env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(float(result.stdout), expected)
        for bad in ('0', 'x', '-1'):
            with self.subTest(bad=bad):
                result = self.scale(AI_TEST_TIMEOUT_SCALE=bad)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('AI_TEST_TIMEOUT_SCALE', result.stderr)

    def test_test_harness_timeouts_no_literal_timeout_numbers(self):
        for name in ('test_workflow.py', 'test_dashboard.py', 'test_observation.py'):
            source = (ROOT / 'tests' / name).read_text()
            self.assertNotRegex(source, r'timeout\s*=\s*\d', name)

    def test_test_harness_timeouts_timed_out_command_shows_its_output(self):
        case = ToolkitTest('run_cmd')
        case.project = ROOT
        case.env = dict(os.environ)
        bound = 1  # deliberately tiny and unscaled: the command must time out
        with self.assertRaises(AssertionError) as caught:
            case.run_cmd(['bash', '-c', 'echo started; sleep 30'], timeout=bound)
        message = str(caught.exception)
        self.assertIn('started', message)
        self.assertIn(f'timed out after {bound} s', message)


class FixtureIoTest(unittest.TestCase):
    """FL-23: fixtures skip git syncs and run_parallel puts batch temp files on tmpfs."""

    RUNNER = ROOT / 'tests/run_parallel.py'

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ai-fixture-io-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        sys.path.insert(0, str(ROOT / 'tests'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tests'))

    def git_config(self, env, name):
        result = subprocess.run(['git', 'config', '--get', name], cwd=self.base, env=env,
                                capture_output=True, text=True, timeout=SHORT_TIMEOUT)
        return result.stdout.strip()

    def test_fixture_io_git_config_disables_fsync_and_gc(self):
        case = ToolkitTest('run_cmd')
        case.setUp()
        self.addCleanup(case.doCleanups)
        for name, expected in (('core.fsync', 'none'), ('gc.auto', '0')):
            result = subprocess.run(['git', 'config', '--get', name], cwd=case.project, env=case.env,
                                    capture_output=True, text=True, timeout=SHORT_TIMEOUT)
            self.assertEqual(result.stdout.strip(), expected, name)

    def test_fixture_io_git_config_keeps_an_outer_config_count(self):
        outer = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'user.signingkey', 'GIT_CONFIG_VALUE_0': 'x'}
        env = git_fixture_env(dict(os.environ, **outer))
        self.assertEqual(env['GIT_CONFIG_COUNT'], '3')
        for name, expected in (('user.signingkey', 'x'), ('core.fsync', 'none'), ('gc.auto', '0')):
            self.assertEqual(self.git_config(env, name), expected, name)

    def suite(self):
        suite = self.base / 'suite'
        suite.mkdir(exist_ok=True)
        (suite / 'test_tmp.py').write_text(
            'import os, stat, subprocess, tempfile, unittest\n\n\n'
            'class Sample(unittest.TestCase):\n'
            '    def test_tmp(self):\n'
            '        directory = tempfile.gettempdir()\n'
            '        script = os.path.join(directory, "run-me.sh")\n'
            '        with open(script, "w") as handle:\n'
            '            handle.write("#!/bin/sh\\necho ran-here\\n")\n'
            '        os.chmod(script, 0o700)\n'
            '        out = subprocess.run([script], capture_output=True, text=True)\n'
            '        with open(os.environ["TMP_REPORT"], "w") as handle:\n'
            '            handle.write(directory + "\\n" + out.stdout.strip() + "\\n" + str(out.returncode))\n')
        return suite

    def run_suite(self, **env):
        report = self.base / 'report.txt'
        base = {k: v for k, v in os.environ.items()
                if k not in ('TMPDIR', 'AI_TEST_TMPFS', 'AI_TEST_TMPFS_DIR', 'PYTHONPATH')}
        base.update(AI_TEST_WORKERS='1', TMP_REPORT=str(report))
        base.update(env)
        result = subprocess.run([sys.executable, str(self.RUNNER), '--start-dir', str(self.suite())],
                                cwd=ROOT, env=base, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=PIPELINE_TIMEOUT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        directory, ran, code = report.read_text().split('\n')
        self.assertEqual((ran, code), ('ran-here', '0'), result.stdout)
        return result, directory

    def shm_usable(self):
        shm = '/dev/shm'
        if not (os.path.isdir(shm) and os.access(shm, os.W_OK | os.X_OK)):
            return False
        stats = os.statvfs(shm)
        return stats.f_bavail * stats.f_frsize >= (1 << 30) and not stats.f_flag & os.ST_NOEXEC

    def test_fixture_io_batches_use_tmpfs_and_remove_it(self):
        if not self.shm_usable():
            self.skipTest('/dev/shm is not a writable, executable directory with 1 GiB free')
        result, directory = self.run_suite()
        self.assertTrue(directory.startswith('/dev/shm/ai-tests-'), directory)
        self.assertIn(f'Temp dir: {directory} (tmpfs)', result.stdout)
        self.assertFalse(os.path.exists(directory))

    def test_fixture_io_tmpfs_can_be_disabled_or_overridden_by_tmpdir(self):
        result, directory = self.run_suite(AI_TEST_TMPFS='0')
        self.assertFalse(directory.startswith('/dev/shm/ai-tests-'), directory)
        self.assertNotIn('Temp dir:', result.stdout)
        given = self.base / 'given'
        given.mkdir()
        result, directory = self.run_suite(TMPDIR=str(given))
        self.assertEqual(Path(directory).resolve(), given.resolve())
        self.assertNotIn('Temp dir:', result.stdout)

    def test_fixture_io_unusable_candidate_falls_back_and_is_removed(self):
        import run_parallel
        candidate = self.base / 'candidate'
        candidate.mkdir()

        class Stats:
            f_bavail, f_frsize, f_flag = 1 << 30, 4096, 0

        class NoExec(Stats):
            f_flag = os.ST_NOEXEC

        def raising(directory):
            raise PermissionError(directory)

        for label, probe, statvfs in (('probe false', lambda directory: False, lambda path: Stats()),
                                      ('probe raises', raising, lambda path: Stats()),
                                      ('noexec mount', lambda directory: True, lambda path: NoExec())):
            with self.subTest(label), contextlib.redirect_stdout(io.StringIO()) as shown:
                self.assertIsNone(run_parallel.choose_temp_dir(candidate, probe=probe, statvfs=statvfs))
                self.assertEqual(list(candidate.iterdir()), [])
                self.assertIn('Temp dir: default', shown.getvalue())
        with self.subTest('usable'):
            chosen = run_parallel.choose_temp_dir(candidate, probe=lambda directory: True, statvfs=lambda path: Stats())
            self.assertEqual(Path(chosen).parent, candidate)
            self.assertTrue(Path(chosen).name.startswith('ai-tests-'))
        with self.subTest('too little space'):
            Stats.f_bavail = 1
            self.assertIsNone(run_parallel.choose_temp_dir(candidate, probe=lambda directory: True,
                                                           statvfs=lambda path: Stats()))
        self.assertTrue(run_parallel.exec_probe(self.base))

    def test_fixture_io_toolkit_does_not_set_core_fsync(self):
        for folder in ('scripts', 'templates'):
            for path in (ROOT / folder).rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts:
                    self.assertNotIn('core.fsync', path.read_text(errors='ignore'), str(path))


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
        'only reachable with `--max-fix-rounds`',
    )

    REQUIRED = (
        'denials are logged and the run continues',
        "automatic checkpoints stage the session's output except secret-looking files",
        'the pipeline pushes the feature branch and opens the pull request',
        'usage limits pause and resume',
        'committed bytes equal to the validated files',
        'outside the checkout',
        'tree-snapshot',
        'dependencies a task changes mid-run are installed at the next start',
        'needs you',
        'covered by automated tests',
        'context only',
        'interleaved batches pulled by `ai_test_workers` workers',
        'convergence',
        'convergence: <text>',
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
