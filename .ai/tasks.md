# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files. This run is started with
`--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` (absolute path) so the vault flow chart can be updated.

## T001 — Permissions template: approved read-only shell, git rm/mv, ai-task
Status: DONE
Dependencies: none
Model: opus

### Goal
Permission part of B1/E1 (security policy, hence opus).

### Implementation notes
templates/.ai/permissions.allow: add `Bash(ls)`, `Bash(ls *)`, `Bash(grep *)`, `Bash(cat *)`,
`Bash(head *)`, `Bash(tail *)`, `Bash(wc *)`, `Bash(echo *)`, `Bash(git rm *)`, `Bash(git mv *)`,
`Bash(.ai/bin/ai-task *)`. Deliberately NOT sed, rg or find: they write or execute through
their own flags (sed -i / w / e, rg --pre, find -exec/-delete), which no redirect check stops
(plan review P10). Comment in the file: Claude Code denies redirects, pipes and chains into
commands that aren't allowed (verified live 2026-10-05). README (permissions section):
document the actual residual capability: these commands can READ files outside the project.

### Likely affected modules
templates/.ai/permissions.allow, README.md (permissions), tests

### Acceptance criteria
- Tests named `permissions_template`: the new entries exist; NONE of these appear:
  network (curl, wget, ssh, scp), installs (npm install, npm i, pip install), `git push`,
  `git reset --hard`, `rm `, `sed`, `rg`, `find`, `xargs`, `chmod`, `sudo`, `bash -c`, `python`.

### Validation
Targeted: `python3 -m unittest discover -s tests -k permissions_template` (allowed by this run's
permissions; new tests are named with `permissions_template`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
Done 2026-10-05. templates/.ai/permissions.allow gains the 11 entries plus a comment on
redirect/pipe denial, outside-project reads and why sed/rg/find are absent; README planning
step 3 documents the residual read capability. Tests `test_permissions_template_*` (2):
required entries present, no unrestricted Bash, no forbidden program/phrase (bare `rm` is
checked as a program, so `git rm` is allowed; `bash .ai/validate` stays, `bash -c` is banned).
Targeted: `Ran 2 tests ... OK`. Gate: 104 tests OK. Also fixed a test-hermeticity bug found
by the gate: the fixture inherited `AI_PIPELINE`/`AI_LOCK_HELD` from the pipeline running this
session, which made 4 notification/plan-review tests fail; setUp now drops both.

## T002 — Shared tool contract and the ai-task command
Status: DONE
Dependencies: T001
Model: sonnet

### Goal
Contract part of B1/E1.

### Implementation notes
Identical "How to work here" section in templates/.ai/prompts/runner.md, triage.md and
recover.md (recover is read-only: only the reading rules): Read/Grep/Glob for reading,
Edit/Write for changes (no heredoc/sed edits), plain commands without `cd`, run the full gate as
`.ai/bin/ai-check` (no redirects or `; echo`), and the task's own targeted test command when
it names one, `git rm`/`git mv` for tracked files, `.ai/bin/ai-task` for task status.
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
Targeted: `python3 -m unittest discover -s tests -k tool_contract` (allowed by this run's
permissions; new tests are named with `tool_contract`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
Done 2026-10-05. "How to work here" section appended to runner.md and triage.md (identical)
and recover.md (read-only rules only). `scripts/ai-task` (`set`, `show`; usage errors exit 2)
over the existing `tasks` helper, which gained `show` (id/title, status, model, dependencies);
setup's copy list includes ai-task (installed 0755). ai-run's RUNNER CONTRACT now points to the
section. The mock Claude's prompt assertion follows the new wording (`cd` in backticks).
Tests `test_tool_contract_*` (3). Targeted: `Ran 3 tests ... OK`. Gate: 107 tests OK.
Limitation: `chmod +x scripts/ai-task` was denied in this run, so the source file is 0644
(human todo); installed copies are 0755 via setup.

## T003 — Model rule and human-todo rule in templates
Status: DONE
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
Targeted: `python3 -m unittest discover -s tests -k template_rules` (allowed by this run's
permissions; new tests are named with `template_rules`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
(pending)

## T004 — Triage completion protocol (recovery and crashes)
Status: DONE
Dependencies: T003
Model: opus

### Goal
R1 of `.ai/project-spec.md`; plan review P1.

### Implementation notes
One owner for the counted commit: ai-run --triage (as today) creates `chore(ai): record review
triage`. Before triage, ai-pipeline stores `stage = {name: triage, start_head, review_digest}`
in the run manifest. A shared reconciliation step runs on EVERY pipeline start and resume
(human or recovery) BEFORE the manifest is reset or implementation starts. In BOTH paths it first
verifies: the review binding (stage review_digest = current verified review), committed AND
uncommitted changes since start_head ⊆ triage-allowed records, and `triage-check --fresh`.
Then: if a counted triage commit for that review already exists after start_head, close the
stage without a second count (crash after commit, before clearing); otherwise create the
counted commit once through the same ai-run code path. Any failed verification escalates
without implementation and without counting. ai-recover never commits triage-stage leftovers
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
  committed; the counted commit exists but a hook changed source in it → resume escalates,
  no implementation, no second count; the fix-round limit still holds.

### Validation
Targeted: `python3 -m unittest discover -s tests -k triage_completion` (allowed by this run's
permissions; new tests are named with `triage_completion`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
DONE 2026-10-05. `run-manifest stage-set|stage|stage-clear` (stage carried over by a human
restart on the same branch), `triage-scope`, `stage-verify` in scripts/lib/workflow.py.
ai-pipeline: `complete_stage` runs before the clean-tree check on every start/resume and as
the triage step itself; failed checks are `Triage stage …` stops (hard escalation in
ai-recover). ai-run --triage: `--since`, leftovers limited to triage records, skips the
session when dispositions are already complete, commits leftover records in the one counted
commit, re-checks scope after it. ai-recover: open stage → scope check → rerun without a
Claude decision or escalate; never commits. Evidence: `python3 -m unittest discover -s tests
-k triage_completion` → Ran 7 tests, OK (normal round, 2026-10-05 uncommitted records,
fix-round limit, crash after counted commit, watchdog-style crash recovery, source leftovers,
hook in counted commit). `.ai/bin/ai-check` → Ran 117 tests, OK. Limitation: the crash test
calls `ai-recover --stage 'crash …'` directly (what the watchdog launches via systemd-run).
Decision: incomplete dispositions with only bookkeeping leftovers rerun the triage session
(escalating would trap every human restart after e.g. a usage-limit stop); uncommitted
incomplete triage records escalate.

## T005 — Publish invariants around every push
Status: DONE
Dependencies: T004
Model: opus

### Goal
R2 of `.ai/project-spec.md`; plan review P2.

### Implementation notes
A `publish_ready` check in ai-pipeline: review current for HEAD, validation stamp current,
clean tree (incl. untracked), all tasks DONE. Run it after every host commit on the publish
path, before EACH push attempt (inside the retry loop) and after each push (hooks ran),
plus compare `git ls-remote origin <branch>` with HEAD after the push. Failures go
through `stop`. Update the vault flow chart (publish checks, remote-HEAD verification) and
its `updated:` date in this task.

### Likely affected modules
scripts/ai-pipeline, tests

### Acceptance criteria
- Tests named `publish_ready`: a commit hook changing source while recording the review
  stops before push; a pre-push hook leaving an UNcommitted source change on the final push
  stops; a failed push that changes the checkout before the retry stops; a pre-push hook
  that adds a workflow-only commit (checkout clean, everything else fine) makes the remote
  `refs/heads/<branch>` differ from HEAD → stop before PR creation and before any FINISHED
  notification; the normal path opens the PR and the remote ref equals final HEAD exactly.

### Validation
Targeted: `python3 -m unittest discover -s tests -k publish_ready` (allowed by this run's
permissions; new tests are named with `publish_ready`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
`publish_ready STAGE` in scripts/ai-pipeline: gate verify, review-info binding, clean tree
(untracked too), `tasks complete`, `review_current`, `stamp verify`; failure writes
"Publish check failed at STAGE: …" and calls `stop`. Runs before the PR stage (replaces the
plain clean-tree check), before each push attempt inside `push`'s retry loop, and after each
push, followed by `git ls-remote origin refs/heads/<branch>` == HEAD (exact ref match via
awk). The final push goes through the same `push` (its output is no longer silenced so stop
messages reach stderr). Evidence: `python3 -m unittest discover -s tests -k publish_ready`
→ Ran 5 tests, OK (commit hook review→stop before push; final-push hook dirty→stop; failed
push changing checkout→stop before retry, one sleep; pre-push workflow-only commit→remote
≠ HEAD, no PR, no FINISHED; normal path remote == final HEAD). `.ai/bin/ai-check` → Ran 122
tests, OK. docs/workflow.md, README, vault flow chart + hub log updated. ai-recover
unchanged: publish stops follow the normal recovery rules (review-integrity messages still
escalate).

## T006 — Disputed findings: the re-check command and its binding
Status: DONE
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
Targeted: `python3 -m unittest discover -s tests -k recheck_command` (allowed by this run's
permissions; new tests are named with `recheck_command`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
DONE 2026-10-05. `ai-review --recheck` (scripts/ai-review) with its own preflight
(`workflow.py recheck-prepare`: clean tree, verified review, bound dispositions, ≥1 rejected
BLOCKER/MAJOR, reviewed commit ancestor of HEAD, only RECHECK_RECORDS changed since it).
`parse_recheck` is strict (missing/duplicate/extra/malformed → upheld); `publish-recheck`
re-runs the preflight, writes `.ai/reviews/recheck.md` (review digest, rows digest, reviewed
HEAD, table + machine-readable answers) and stores `recheck-<review digest>.sha256` in host
state; `recheck-verify` checks binding, review, rows and prints `ID\tverdict\treason`.
Prompt `templates/.ai/prompts/recheck.md`. `AI_RECHECK_EFFORT` (default medium) in the
user-config allowlist, RUN_SETTINGS and ai-recover's unset/restore list; `ai_review_args`
takes the setting name/default. Run by hand it commits `chore(ai): record review re-check`
(pipeline integration and the single report+disputes commit are T007). Evidence:
`python3 -m unittest discover -s tests -k recheck_command` → Ran 6 tests, OK;
`.ai/bin/ai-check` → Ran 128 tests, OK. README and docs/workflow.md updated; flow chart
unchanged (the pipeline does not call the re-check until T007).

## T007 — Disputed findings in the pipeline and the PR
Status: DONE
Dependencies: T006
Model: opus

### Goal
R3 (integration) of `.ai/project-spec.md`; plan review P3.

### Implementation notes
Right after every triage, AND on every pipeline start/resume BEFORE any task runs or the
implementation review is replaced (regardless of task completion), ai-pipeline reconciles
pending re-checks: rejected BLOCKER/MAJOR in the current dispositions without a verified,
current re-check → run `ai-review --recheck`. The re-check report and the dispute records for
its upheld answers are written and committed together in ONE host commit (no window between
them). Reconciliation also verifies, for an already verified re-check, that every upheld
answer has its record (keyed by review digest + finding id) and appends any missing one
exactly once, before implementation or review replacement. Every UPHELD answer becomes a
durable dispute record in
`.ai/reviews/disputes.md` (review digest, finding id, original finding text, Claude's
evidence, Codex's answer, date), digest-bound in host state like the reviews; records are
only ever appended. Lifetime rule (simple on purpose): a recorded dispute is never resolved
automatically, not by later fixes or a clean later review. While any record exists, the PR
is a draft and the body starts with "Disputed findings" listing every record (id, original
finding, Claude's reason, Codex's answer); Zack resolves them at the PR. Update the vault
flow chart (the re-check step) and its `updated:` date.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/workflow.py (pr-body), tests, vault agents-flow.md

### Acceptance criteria
- Tests named `disputed_findings`: all withdrawn → normal PR; one upheld → draft with the
  section on top; mixed accepted + rejected (one upheld) → re-check runs right after triage,
  the accepted fixes proceed, a later clean review and a restart still end in a draft PR
  listing the dispute; resume with completed dispositions but no re-check → re-check runs;
  a tampered disputes file fails verification; no rejected BLOCKER/MAJOR → no re-check call;
  interrupted after a mixed triage but before the re-check → the resume re-checks the
  ORIGINAL rejected findings first, then implements the accepted fixes, and an upheld
  dispute survives a later clean review into a draft PR.
- Interrupted after a re-check report exists but its dispute record is missing (simulated by
  removing the record) → the resume adds the record exactly once before any task runs, and
  the dispute reaches the draft PR; re-running reconciliation doesn't duplicate records.

### Validation
Targeted: `python3 -m unittest discover -s tests -k disputed_findings` (allowed by this run's
permissions; new tests are named with `disputed_findings`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
DONE 2026-10-05. `ai-pipeline` `reconcile_disputes` runs after every triage (after
`triage-check --fresh`) and on every start/resume (after completing an open triage stage,
before plan review/implementation). New helpers in `workflow.py`: `recheck-status`
(none/pending/verified), `disputes-record` (append-only, keyed by review digest + finding id,
per-branch host store `disputes-<branch hash>.json`, file rewritten from it; a lagging file
prefix is accepted, any other difference fails), `disputes-verify` (exact match; part of
`publish_ready`). Report + records are one host commit (`chore(ai): record review re-check`,
or `chore(ai): record disputed findings` when only a missing record is added). A start may
find only an uncommitted `recheck.md`/`disputes.md`, which reconciliation verifies and
commits. `pr-body` starts with "Disputed findings" (id, level, original finding, Claude's
reason, Codex's answer); a recorded dispute forces a draft (also converts an existing PR);
`finish-summary` and the no-PR notification list the disputes as a human todo.
Evidence: `python3 -m unittest discover -s tests -k disputed_findings` → Ran 9 tests, OK
(all withdrawn → normal PR; one upheld → draft with section on top and one commit holding
report + record; mixed triage → re-check before `implement T002`, later clean review and a
restart still draft; completed dispositions without re-check → re-check runs; tampered or
removed file fails; no rejected finding → no re-check call; failed re-check then resume
re-checks the original M2 before the fix; report without record → record added once before
any task, no duplicates on restart; uncommitted report committed with its record).
`.ai/bin/ai-check` → Ran 137 tests, OK. Changed existing test
`test_pipeline_rejected_findings_still_open_normal_pr` to supply a withdrawn re-check
answer: under R3 an upheld rejection drafts the PR, so the old premise no longer holds.
Docs: README, docs/workflow.md. Vault: flow chart (re-check step) + hub log.
Limitation: a dispute is only lost if someone edits the host store outside the checkout,
which agent sessions cannot write.

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
nothing; `--upgrade --apply PATH` upgrades the toolkit runtime (`.ai/bin/**`) as ONE compatible
group, all or nothing (plan review P11: the scripts call each other and the shared helper):
if any runtime file is locally edited (hash ≠ baseline), it refuses before changing anything
and lists the files to reconcile, unless `--force`; otherwise it replaces/creates the whole
group. Prompts (`.ai/prompts/**`) follow the same rule as their own group. It writes new
baselines only for files it actually installed, and reminds to reinstall the watchdog
timer. A toolkit-owned
file missing in the project is CREATED (preview shows CREATE; executable mode kept; path and
symlink checks as in setup; baseline recorded); this is how `.ai/bin/ai-task` and
`.ai/prompts/recheck.md` reach older installs. Missing or malformed stamp (legacy install):
every differing existing toolkit-owned file counts as locally edited (needs `--force`),
identical ones get baselines, missing ones are created. README: upgrades are their own PR.

### Likely affected modules
scripts/setup-project, scripts/lib/workflow.py, README.md, tests

### Acceptance criteria
- Tests named `toolkit_upgrade`: fresh setup writes the stamp; preview changes nothing;
  A→B upgrade replaces an outdated file and keeps .ai/validate and permissions; a locally
  edited older `lib/workflow.py` makes a plain apply refuse with NO file changed (the old
  install still passes `ai-status`), while `--force` installs the complete new group and an
  installed pipeline smoke run (mock agents) passes; repeated setup after a local edit
  doesn't bless it; two consecutive applies are stable; a legacy install needs --force for
  differing files; upgrading an older inventory without ai-task and recheck.md creates both,
  and the installed `ai-task show` then works.

### Validation
Targeted: `python3 -m unittest discover -s tests -k toolkit_upgrade` (allowed by this run's
permissions; new tests are named with `toolkit_upgrade`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

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
today's `updated:` and shows R1, R2 and R3, and audit it against every changed step and
default of this batch. The pipeline's PR description for this change must contain "Flow
chart updated" (record it in the handoff so the PR body carries it).

### Likely affected modules
README.md, docs/workflow.md, tests

### Acceptance criteria
- Tests named `docs_consistency` (case-insensitive) fail if README.md or docs/workflow.md
  contain: "never stages application files", "does not invoke `git push`", "never invokes
  push", a sentence listing denied permissions among reasons a run stops, or "no automatic
  provider retries"; and require: a "Modes" table with rows for interactive Claude, ai-run,
  ai-pipeline and ai-watchdog; sentences stating that denials are logged and the run
  continues, that automatic checkpoints stage the session's output except secret-looking
  files, that the pipeline pushes the branch and opens the PR, and that usage limits pause
  and resume. Read the actual docs first and extend the forbidden list to every wrong
  sentence you find.

### Validation
Targeted: `python3 -m unittest discover -s tests -k docs_consistency` (allowed by this run's
permissions; new tests are named with `docs_consistency`; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check`.

### Result / notes
(pending)

