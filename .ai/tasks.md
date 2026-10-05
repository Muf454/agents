# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files. This run is started with
`--knowledge-dir "~/zWiki/zWiki/20 Projects/agents"` so the vault flow chart can be updated.

## T001 — Permissions template: approved read-only shell, git rm/mv, ai-task
Status: TODO
Dependencies: none
Model: opus

### Goal
Permission part of B1/E1 (security policy, hence opus).

### Implementation notes
templates/.ai/permissions.allow: add `Bash(ls)`, `Bash(ls *)`, `Bash(grep *)`, `Bash(rg *)`,
`Bash(cat *)`, `Bash(head *)`, `Bash(tail *)`, `Bash(wc *)`, `Bash(sed -n *)`, `Bash(echo *)`,
`Bash(git rm *)`, `Bash(git mv *)`, `Bash(.ai/bin/ai-task *)`, with a comment: Claude Code
denies redirects, pipes and chains into commands that are not allowed (verified live on
2026-10-05). Document in README (permissions section) the residual risk: read-only commands
can read files outside the project.

### Likely affected modules
templates/.ai/permissions.allow, README.md (permissions), tests

### Acceptance criteria
- Tests named `permissions_template`: the new entries exist; NONE of these appear:
  network (curl, wget, ssh, scp), installs (npm install, npm i, pip install), `git push`,
  `git reset --hard`, `rm `, `sed -i`, `find`, `chmod`, `sudo`.

### Validation
`python3 -m unittest discover -s tests -k permissions_template` (new tests are named with `permissions_template` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T002 — Shared tool contract and the ai-task command
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
Contract part of B1/E1.

### Implementation notes
Identical "How to work here" section in templates/.ai/prompts/runner.md, triage.md and
recover.md (recover is read-only: only the reading rules): Read/Grep/Glob for reading,
Edit/Write for changes (no heredoc/sed edits), plain commands without `cd`, run checks only
as `.ai/bin/ai-check`, `git rm`/`git mv` for tracked files, `.ai/bin/ai-task` for task status.
New `scripts/ai-task`: `set T003 IN_PROGRESS|DONE|BLOCKED|TODO` (existing helper) and
`show T003` (prints status, model, dependencies); add it to setup's copy list. ai-run's
contract strings refer to the section instead of repeating rules.

### Likely affected modules
templates/.ai/prompts/{runner,triage,recover}.md, scripts/ai-task, scripts/lib/workflow.py
(setup list), scripts/ai-run, tests

### Acceptance criteria
- Tests named `tool_contract`: the section is identical in runner and triage and present in
  recover; setup installs ai-task; `set` changes status and rejects bad values/unknown ids;
  `show` prints status, model and dependencies.

### Validation
`python3 -m unittest discover -s tests -k tool_contract` (new tests are named with `tool_contract` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T003 — Model rule and human-todo rule in templates
Status: TODO
Dependencies: T002
Model: haiku

### Goal
B6 and R6 of `.ai/project-spec.md`.

### Implementation notes
Model-selection text in templates/CLAUDE.md, templates/.ai/prompts/plan.md, plan-review.md
and triage.md (for review-fix tasks) gets the B6 wording. Runner.md and triage.md get the R6
rule (never tick/untick knowledge-base checkboxes; append dated log lines).

### Likely affected modules
templates/CLAUDE.md, templates/.ai/prompts/{plan,plan-review,runner,triage}.md, tests

### Acceptance criteria
- Tests named `template_rules`: the new wording exists; the old blanket "already failed
  review or validation once" wording is gone; the R6 rule is in runner and triage.

### Validation
`python3 -m unittest discover -s tests -k template_rules` (new tests are named with `template_rules` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T004 — Triage completion protocol (recovery and crashes)
Status: TODO
Dependencies: T003
Model: opus

### Goal
R1 of `.ai/project-spec.md`; plan review P1.

### Implementation notes
One owner for the counted commit: ai-run --triage (as today) creates `chore(ai): record review
triage`. Before triage, ai-pipeline stores `stage = {name: triage, start_head, review_digest}`
in the run manifest. A shared reconciliation step runs on EVERY pipeline start and resume
(human or recovery) BEFORE the manifest is reset or implementation starts: if a triage stage
is open and a counted triage commit for that review exists after start_head, mark it
complete (crash after commit, before clearing); otherwise complete it once (paths changed
since start_head ⊆ triage-allowed records, `triage-check --fresh`, then the counted commit
through the same ai-run code path). ai-recover never commits triage-stage leftovers
generically: it reruns (reconciliation completes the stage) or escalates; watchdog crash
recovery reads the stage from the manifest. Update the vault flow chart
(agents-flow.md, "When something goes wrong") and its `updated:` date in this task.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, scripts/ai-recover, scripts/lib/workflow.py (manifest
stage), tests, vault agents-flow.md

### Acceptance criteria
- Tests named `triage_completion`: normal triage counts one round; the 2026-10-05 case
  (triage records left uncommitted) → stop → recovery → exactly one counted round; crash
  after the counted commit but before clearing → no second count; watchdog crash recovery
  during triage completes it once; leftovers touching source → escalation, nothing
  committed; the fix-round limit still holds.

### Validation
`python3 -m unittest discover -s tests -k triage_completion` (new tests are named with `triage_completion` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T005 — Publish invariants around every push
Status: TODO
Dependencies: T004
Model: opus

### Goal
R2 of `.ai/project-spec.md`; plan review P2.

### Implementation notes
A `publish_ready` check in ai-pipeline: review current for HEAD, validation stamp current,
clean tree (incl. untracked), all tasks DONE. Run it after every host commit on the publish
path, before EACH push attempt (inside the retry loop) and after each push (hooks ran),
plus compare `git ls-remote origin <branch>` with HEAD after the push. Failures go
through `stop`.

### Likely affected modules
scripts/ai-pipeline, tests

### Acceptance criteria
- Tests named `publish_ready`: a commit hook changing source while recording the review
  stops before push; a pre-push hook leaving an UNcommitted source change on the final push
  stops; a failed push that changes the checkout before the retry stops; the normal path
  still opens the PR.

### Validation
`python3 -m unittest discover -s tests -k publish_ready` (new tests are named with `publish_ready` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T006 — Disputed findings: the re-check command and its binding
Status: TODO
Dependencies: T005
Model: opus

### Goal
R3 (command) of `.ai/project-spec.md`; plan review P3/P4.

### Implementation notes
`ai-review --recheck` with its OWN preflight: a published implementation review whose
provenance verifies, source unchanged since the reviewed commit except workflow records
(pending accepted fix tasks allowed), and at least one rejected BLOCKER/MAJOR. Codex gets
`templates/.ai/prompts/recheck.md`, the review, the rejected rows (id + Claude's evidence)
and the code; it must answer one JSON object with exactly one `withdrawn|upheld` + reason
per rejected id. Parse strictly: missing, duplicate, extra or malformed answers count as
upheld. Host writes `.ai/reviews/recheck.md` with a binding: review digest, sha256 of the
rejected rows (ids + evidence), reviewed HEAD; the report digest is stored in the host
state like other reviews. A helper verifies the binding.
Effort: `AI_RECHECK_EFFORT` (default medium), model `AI_REVIEW_MODEL`; add the setting to
the user config allowlist, the run manifest settings and ai-recover's unset/restore list.

### Likely affected modules
scripts/ai-review, scripts/lib/workflow.py, scripts/lib/common.sh, scripts/ai-recover,
templates/.ai/prompts/recheck.md, tests (mock codex modes)

### Acceptance criteria
- Tests named `recheck_command`: withdrawn/upheld parsed; missing, duplicate, extra and
  malformed answers → upheld; a report from another review, changed rejection evidence and
  a tampered report all fail verification; the preflight allows pending accepted fix tasks;
  `AI_RECHECK_EFFORT` survives recovery like the other settings.

### Validation
`python3 -m unittest discover -s tests -k recheck_command` (new tests are named with `recheck_command` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T007 — Disputed findings in the pipeline and the PR
Status: TODO
Dependencies: T006
Model: opus

### Goal
R3 (integration) of `.ai/project-spec.md`; plan review P3.

### Implementation notes
After every triage, AND when resuming with completed dispositions (the early-exit path),
ai-pipeline derives the dispute state from verified evidence: rejected BLOCKER/MAJOR without
a verified, current re-check → run `ai-review --recheck`; any upheld → unresolved. Don't reset
the dispute state between rounds except from re-verified evidence. pr-body starts with a
"Disputed findings" section (id, Claude's reason, Codex's answer) whenever any is upheld;
the PR is a draft. Update the vault flow chart (the re-check step) and `updated:`.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/workflow.py (pr-body), tests, vault agents-flow.md

### Acceptance criteria
- Tests named `disputed_findings`: all withdrawn → normal PR; one upheld → draft with the
  section on top; mixed accepted + rejected findings → re-check runs right after triage and
  the accepted fixes proceed; resume with completed dispositions but no re-check → re-check
  runs; no rejected BLOCKER/MAJOR → no re-check call.

### Validation
`python3 -m unittest discover -s tests -k disputed_findings` (new tests are named with `disputed_findings` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T008 — Toolkit version stamp and setup --upgrade
Status: TODO
Dependencies: T007
Model: sonnet

### Goal
R4/R5 of `.ai/project-spec.md`; plan review P5.

### Implementation notes
setup writes `.ai/toolkit-version` (JSON: toolkit commit or "unknown"; per toolkit-owned
file the sha256 of the version the TOOLKIT installed). Ordinary setup never updates the
baseline of a preserved (kept) file. `setup-project --upgrade PATH` prints the plan
(replace / keep / advice for project-owned template changes / warning) and changes
nothing; `--upgrade --apply PATH` replaces toolkit-owned files (`.ai/bin/**`,
`.ai/prompts/**`) whose current hash equals their baseline, keeps locally edited ones
(warning; replaced only with `--force`), keeps the old baseline for kept files, writes new
baselines for replaced ones, and reminds to reinstall the watchdog timer. Missing or
malformed stamp (legacy install): every differing toolkit-owned file counts as locally
edited (needs `--force`), identical ones get baselines. README: upgrades are their own PR.

### Likely affected modules
scripts/setup-project, scripts/lib/workflow.py, README.md, tests

### Acceptance criteria
- Tests named `toolkit_upgrade`: fresh setup writes the stamp; preview changes nothing;
  A→B upgrade replaces an outdated file and keeps .ai/validate and permissions; a local
  edit is kept and reported, replaced with --force; repeated setup after a local edit
  doesn't bless it; two consecutive applies are stable; a legacy install needs --force for
  differing files.

### Validation
`python3 -m unittest discover -s tests -k toolkit_upgrade` (new tests are named with `toolkit_upgrade` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T009 — Docs match the code
Status: TODO
Dependencies: T008
Model: sonnet

### Goal
R10 of `.ai/project-spec.md`.

### Implementation notes
Fix in README.md and docs/workflow.md: denials are logged, not fatal; the runner and
recovery stage application files (with the secret guard); the pipeline pushes and opens
PRs; provider-limit retries, recovery and the watchdog exist. Add a modes table (interactive
Claude, ai-run, ai-pipeline, watchdog: what each may do). Check the vault flow chart has
today's `updated:` and shows R1 and R3.

### Likely affected modules
README.md, docs/workflow.md, tests

### Acceptance criteria
- Tests named `docs_consistency` fail if README.md or docs/workflow.md contain any of:
  "never stages application files", "never invokes push", "stops on denied", "no automatic
  provider retries" (case-insensitive), or lack a "Modes" table heading.

### Validation
`python3 -m unittest discover -s tests -k docs_consistency` (new tests are named with `docs_consistency` and the
output must say `Ran N tests` with N ≥ 1), then `.ai/bin/ai-check`.

### Result / notes
(pending)

