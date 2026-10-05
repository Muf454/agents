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
Status: DONE
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
Implemented by two pipeline sessions (sonnet) on 2026-10-05; both ended without a checkpoint
because the gate (now ~5 min, 146 tests) exceeds the Bash tool's default 2-minute timeout: the
session ran `.ai/bin/ai-check` in the background and could not wait for it (polling via
`timeout … bash -c` is correctly not allowed). Recovery escalated after the second stop.
The coordinator (Claude, interactive) checked the uncommitted work against every acceptance
criterion (9 `toolkit_upgrade` tests incl. the refused-group, `--force` + mock pipeline smoke run
and the CREATE path for ai-task/recheck.md), ran the full gate (PASS 2026-10-05T10:40Z, 146
tests) and committed it. Root cause addressed in T010.

## T009 — Docs match the code
Status: DONE
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
permissions; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (the
suite takes ~5 minutes; never background it).

### Result / notes
Fixed wrong sentences in README.md (denials stop the runner; denied permissions as a stop
reason) and docs/workflow.md (runner never stages application files; toolkit does not invoke
`git push`; permission denial as stop; no automatic retry of provider failures). Added a
Modes table to both. Vault flow chart audited (R1, R2, R3 present, `updated:` 2026-10-05) and
given a note on logged denials. Evidence: `docs_consistency` 3 OK; gate result in run log.

## T010 — Tool contract: run the long gate in the foreground
Status: DONE
Dependencies: T009
Model: haiku

### Goal
Prevent the 2026-10-05 T008 stop: sessions must never background `.ai/bin/ai-check`.

### Implementation notes
In the shared "How to work here" section (templates/.ai/prompts/runner.md, triage.md):
run `.ai/bin/ai-check` in the foreground with the Bash tool's `timeout` set to 600000 ms;
never run it in the background or poll it; if it still times out, mark the task BLOCKED with
the evidence instead of ending without a checkpoint. Mirror the sentence in the README's
permissions/tool section.

### Likely affected modules
templates/.ai/prompts/runner.md, templates/.ai/prompts/triage.md, README.md, tests

### Acceptance criteria
- Tests named `tool_contract` assert the foreground/600000 ms rule is present in runner and
  triage and identical in both.

### Validation
Targeted: `python3 -m unittest discover -s tests -k tool_contract` (allowed by this run's
permissions; the output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
DONE 2026-10-05. Updated "How to work here" section in templates/.ai/prompts/runner.md and
triage.md to explicitly require running `.ai/bin/ai-check` in the foreground with 600000 ms
timeout, never in the background or with polling. Added instruction to mark task BLOCKED if
it times out rather than ending without a checkpoint. Mirrored in README.md step 4. Sections
remain identical in runner and triage (verified by test). Evidence: `python3 -m unittest
discover -s tests -k tool_contract` → Ran 3 tests, OK. `.ai/bin/ai-check` → Ran 149 tests, OK.
All acceptance criteria met.

## T011 — Re-check: extra answers fail closed (review M1)
Status: DONE
Dependencies: T010
Model: opus

### Goal
Review finding M1: an answer set containing any unknown/extra entry must not withdraw anything.

### Implementation notes
`parse_recheck` in scripts/lib/workflow.py currently logs and ignores answers for unknown ids,
so an all-withdrawn response plus an extra `M9` still withdraws everything. Validate the whole
answer set first: any unknown id, non-object entry or non-string id makes EVERY requested
finding upheld (note says why). Keep the existing per-finding duplicate/malformed handling.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py (recheck_command tests), docs if they describe parsing

### Acceptance criteria
- Regression test (named `recheck_command`): requested M1, M2, both withdrawn plus an extra
  `M9` answer → both upheld; same with a malformed extra entry (e.g. a bare string).
- The existing "extra" test is changed so it no longer masks the bug (extra added to an
  otherwise valid, fully withdrawn response).

### Validation
Targeted: `python3 -m unittest discover -s tests -k recheck_command` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
`parse_recheck` now validates the whole answer set before using any entry: an answer for an
unknown id, a non-object entry, or a missing/non-string id returns every requested finding
as upheld (reason "the answer set had an unknown or malformed entry", one note per stray entry
plus a summary note). Per-finding duplicate/malformed handling unchanged. The masking `extra`
subcase was removed from the generic test; new `test_recheck_command_extra_or_stray_entry_upholds_every_finding`
adds an unknown `M9`, bare string, number, list, non-string id and id-less object to an
otherwise valid fully withdrawn M1+M2 answer → both upheld (control without extra → both
withdrawn). The old code ignored such entries, so it withdrew both. docs/workflow.md and
README updated. The template prompt `recheck.md` still says "extra … counts as upheld", which
stays accurate, so it is unchanged.
Evidence: `-k recheck_command` Ran 7 tests OK; `.ai/bin/ai-check` Ran 150 tests OK.
Limitation: I couldn't run the new test against the pre-fix code because `git stash` was denied.

## T012 — Upgrade apply: all-or-nothing activation with rollback (review M2)
Status: DONE
Dependencies: T011
Model: opus

### Goal
Review finding M2: a write failure part-way through `setup-project --upgrade --apply` must not
leave a mixed-version runtime.

### Implementation notes
In the apply loop of scripts/lib/workflow.py (~line 208), snapshot the current bytes/mode (or
absence) of every file in the change set before replacing anything; on any exception restore
all already-replaced files (remove newly created ones), leave the stamp unwritten, report the
failure and exit non-zero. Prefer staging each new file next to its target and renaming, so a
single failure never leaves a half-written file. Rollback errors must be reported, not hidden.

### Likely affected modules
scripts/lib/workflow.py (install_bytes / upgrade apply), tests/test_workflow.py

### Acceptance criteria
- Regression test (named `toolkit_upgrade`): inject an `OSError` into the install of a LATER
  file; afterwards every installed file equals its pre-upgrade content (created files are
  gone), the stamp is unchanged, and the exit status is non-zero. Successful apply and
  existing `toolkit_upgrade` tests still pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k toolkit_upgrade` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
New `activate()` in scripts/lib/workflow.py: snapshots bytes/mode (or absence) of every target,
stages all new files (including the new `.ai/toolkit-version`, renamed last) next to their
targets, then renames; on any exception it restores replaced files, removes created files,
temps and created directories, and fails non-zero ("every file was restored"; rollback errors
are reported as "ROLLBACK FAILED"). `write_stamp` split into `stamp_text` + write.
Test `test_toolkit_upgrade_write_failure_rolls_back_everything` injects `OSError` into the rename
of `.ai/bin/lib/workflow.py` (after recheck.md/ai-task were created and runner.md/ai-status
replaced): snapshot (bytes + modes) equals pre-upgrade, created files gone, exit 1; a later
apply succeeds. Evidence: toolkit_upgrade `Ran 10 tests` OK; ai-check `Ran 151 tests` OK.
README upgrade section documents it. Limitation: rollback-failure path not covered by a test.

## T013 — Source `scripts/ai-task` executable (review N1)
Status: DONE
Dependencies: T010
Model: haiku

### Goal
Review finding N1: Git mode of scripts/ai-task is 100644.

### Implementation notes
`git update-index --chmod=+x scripts/ai-task` plus `chmod +x` (if the run's permissions deny
both, record the exact denied command and leave it as the human todo already in the handoff).
Add a test asserting every file in scripts/ that has a shebang is executable.

### Likely affected modules
scripts/ai-task, tests

### Acceptance criteria
- Test named `script_modes`: all shebang scripts directly under scripts/ are executable;
  `git ls-tree HEAD scripts/ai-task` shows 100755 after the checkpoint.

### Validation
Targeted: `python3 -m unittest discover -s tests -k script_modes` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
The session added the `script_modes` test but could not set the executable bit: `chmod` is
deliberately not allowed for unattended sessions, so it marked the task BLOCKED (correct).
The coordinator ran `chmod +x scripts/ai-task` + `git update-index --chmod=+x` on
2026-10-05 and committed the mode change; T014's validation had failed only on this test.

## T014 — PR body carries the flow-chart declaration (review N2)
Status: DONE
Dependencies: T010
Model: sonnet

### Goal
Review finding N2: AGENTS.md/T009 require "Flow chart updated" in this change's PR description,
but `pr_body` only copies the handoff's "Manual testing for the human" section.

### Implementation notes
Add an optional handoff section `## Flow chart` (one line: "Flow chart updated" or "Flow
unchanged") which `pr_body` copies into the description (e.g. under Summary) when present.
Add that section to this repo's `.ai/handoff.md` with "Flow chart updated: R1/R2/R3 audited,
vault agents-flow.md updated 2026-10-05." Update the templates' handoff if it has a section
list, and docs/workflow.md briefly.

### Likely affected modules
scripts/lib/workflow.py (pr_body), templates/.ai/handoff.md, .ai/handoff.md, docs/workflow.md, tests

### Acceptance criteria
- Test named `pr_body_flow`: a handoff with the section → generated body contains it; without
  → body unchanged. Generated body for this repo contains "Flow chart updated".

### Validation
Targeted: `python3 -m unittest discover -s tests -k pr_body_flow` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
DONE 2026-10-05. `pr_body` (scripts/lib/workflow.py) copies an optional handoff `## Flow chart`
section under Summary; absent section → body unchanged. This repo's `.ai/handoff.md` declares
"Flow chart updated: R1/R2/R3 audited, vault agents-flow.md updated 2026-10-05."; the template
handoff has an optional section; docs/workflow.md mentions it. Tests `pr_body_flow` (2): with/without
section (body otherwise identical), and this repo's handoff yields "Flow chart updated" in the body.
Evidence: `-k pr_body_flow` → Ran 2 tests, OK. `.ai/bin/ai-check` → Ran 154 tests, 1 failure:
`script_modes` for `scripts/ai-task` (0644), the pre-existing T013 blocker (needs human
`chmod +x`); no other failures.

## T015 — Count fix rounds from host state, not commit messages
Status: TODO
Dependencies: T014
Model: opus

### Goal
Observed 2026-10-05 in this run: the triage SESSION committed "chore(ai): record review triage
dispositions", which matches `count_commits '^chore(ai): record review triage'` in ai-pipeline,
so one real round counted as two and the run stopped at the fix-round limit after one round
(draft PR #11). Agent-chosen commit messages must never influence a gate budget.

### Implementation notes
Record each counted triage round in host state (outside the checkout, like the review
bindings), keyed by checkout + branch, written by the same code path that creates the counted
`chore(ai): record review triage` commit (T004), including the commit hash. `ai-pipeline`
reads the count from there. It persists across recovery AND human restarts of the same branch
(like today's git-history count) and never trusts commit subjects alone. Legacy branches with
no host record: fall back to counting only commits whose subject is EXACTLY the host subject,
and record them. Keep T004's triage completion protocol intact.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, scripts/lib/workflow.py, tests

### Acceptance criteria
- Tests named `fix_round_count`: an agent commit whose subject starts with (or equals) the host
  triage subject does not change the count; one real round counts once; the count survives a
  recovery resume and a human restart on the same branch; another branch starts at zero;
  the round limit still produces a draft PR when reached.

### Validation
Targeted: `python3 -m unittest discover -s tests -k fix_round_count` (the output must say
`Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
(pending)
