# Handoff

## What has been implemented?
Toolkit self-installed. Plan for batch 1 (T001–T009) from the vault backlog.
- T001: permissions template allows read-only shell (ls/grep/cat/head/tail/wc/echo),
  git rm/mv and `.ai/bin/ai-task`; sed/rg/find deliberately excluded; README documents
  that these can read files outside the project. Test fixture no longer inherits
  `AI_PIPELINE`/`AI_LOCK_HELD` (they broke 4 tests when the gate ran inside a pipeline).
- T002: runner/triage/recover prompts share a "How to work here" section (tools, no `cd`,
  gate as `.ai/bin/ai-check`, `git rm`/`git mv`, `ai-task`); new `ai-task set|show` command
  installed by setup; ai-run's contract refers to the section. `scripts/ai-task` could not be
  chmod'ed in this session (denied): setup installs it as 0755, but the source file is 0644
  in Git until the human runs `chmod +x scripts/ai-task`.

## Validation
`.ai/validate`: shell syntax + full test suite.

## Manual testing for the human
1. Read the PR's summary of each item; the tests cover behaviour (mocked agents).
2. After merging: `setup-project --upgrade ~/Projects/raid-planner` shows a sensible preview.
3. Permissions: in a project set up from this toolkit, `.ai/permissions.allow` lists
   `Bash(cat *)`, `Bash(git rm *)`, `Bash(.ai/bin/ai-task *)` etc., and contains no
   sed/rg/find/curl entry. In an unattended run, `cat README.md` works but
   `cat README.md > x` and `ls; curl …` are denied.

4. Tool contract: `setup-project` into a scratch repo installs `.ai/bin/ai-task`;
   `.ai/bin/ai-task show T001` prints status, model and dependencies and
   `.ai/bin/ai-task set T001 DONE` changes the status (bad status or unknown id fails).

## Human todos
- Run `chmod +x scripts/ai-task` (and commit the mode) so the toolkit source file is executable like the other scripts.

## Next action
Runner continues with T003 (model rule and human-todo rule in templates).
