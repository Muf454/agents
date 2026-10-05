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
- T003: B6 model rule (retry failed attempts on opus; review-fix tasks use their own risk
  criterion, no blanket promotion) in templates/CLAUDE.md, templates/.ai/prompts/plan.md, and
  plan-review.md. R6 human-todo rule (never tick/untick knowledge-base checkboxes; append
  dated progress to project log) in runner.md and triage.md. Tests verify new wording and
  absence of old wording.
- T004: triage completion protocol (R1). Before each triage the pipeline stores a `stage`
  (start HEAD, review digest) in the host run manifest; every pipeline start/resume first
  completes it (review binding, only triage records changed since start, fresh dispositions),
  closing it if the counted `chore(ai): record review triage` commit exists, else recording
  it once via `ai-run --triage --since`. ai-recover never commits triage leftovers: it reruns
  without a Claude decision or escalates. Failed checks are `Triage stage …` stops that
  always escalate. Vault flow chart updated.

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
5. Triage completion: in a scratch project with a review that has a MAJOR finding, start
   `ai-pipeline --approved`, and when "Review triage" starts, kill the pipeline (or deny the
   triage session's commit). Rerun `ai-pipeline --approved`: it prints "Completing the
   interrupted review triage", `git log --oneline | grep -c 'record review triage'` is 1,
   and there is no "recovery checkpoint" commit. If you add an uncommitted `src.txt` before
   the rerun, it stops with "Triage stage cannot be completed safely" and commits nothing.

## Human todos
- Run `chmod +x scripts/ai-task` (and commit the mode) so the toolkit source file is executable like the other scripts.

## Next action
Runner continues with T005 (publish invariants around every push).
