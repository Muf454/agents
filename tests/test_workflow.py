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
args = sys.argv[1:]
assert '--permission-mode' in args and args[args.index('--permission-mode')+1] == 'dontAsk'
assert '--' in args
prompt = args[args.index('--')+1]
assert 'RUNNER CONTRACT' in prompt
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
print(json.dumps({'type':'result','subtype':'success','is_error':False,'permission_denials':[]}))
'''

MOCK_CODEX = r'''#!/usr/bin/env python3
import os, pathlib, sys
args = sys.argv[1:]
assert args[0] == 'exec'
assert args[args.index('--sandbox')+1] == 'read-only'
assert 'approval_policy="never"' in args
assert '--ignore-user-config' in args
mode = os.environ.get('MOCK_CODEX', 'success')
if mode == 'error': sys.exit(17)
path = pathlib.Path(args[args.index('--output-last-message')+1])
if mode == 'empty': sys.exit(0)
if mode == 'malformed':
    path.write_text('looks fine')
    sys.exit(0)
if mode == 'mutates':
    pathlib.Path('unexpected.txt').write_text('unexpected concurrent edit')
path.write_text("""# Independent review
Overall verdict: no demonstrated findings in inspected fixture
## BLOCKER findings
None found.
## MAJOR findings
None found.
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
        for name, contents in (('claude', MOCK_CLAUDE), ('codex', MOCK_CODEX)):
            file = self.mock_bin / name
            file.write_text(contents)
            file.chmod(0o755)
        self.env['PATH'] = str(self.mock_bin) + os.pathsep + self.env['PATH']

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
            for path in ('.ai/bin/**', '.ai/validate', '.ai/prompts/**',
                         '.ai/permissions.allow', '.claude/settings.json'):
                self.assertIn(f'{tool}({path})', deny)
        for command in ('git commit --no-verify *', 'git commit -n *',
                        'git commit * --no-verify', 'git commit * -n'):
            self.assertIn(f'Bash({command})', deny)

    def test_runner_detects_even_committed_gate_changes_before_untrusted_helpers(self):
        self.ready()
        targets = ('.ai/validate', '.ai/bin/ai-check', '.ai/bin/lib/workflow.py',
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


if __name__ == '__main__':
    unittest.main()
