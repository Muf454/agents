# Task queue

Branch `feature/supervisor` (FL-04, bounded supervisor for "needs a human" stops). Prioritised by
Zack 2026-10-07 before the dashboard (DB-01). Revision 4 after plan review round 3 (see
`.ai/current-plan.md` for the host-state table, section contract, revision commit and loop). The
shared run budget is not part of this batch (OR-09); tasks were renumbered T001–T010. Edit
`scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit `.ai/bin`,
`.ai/prompts` or other gate files of this repo. Every task leaves `.ai/bin/ai-check` passing and
names its tests with the prefix given in Validation. Flow-chart rule: a task that changes the flow
updates vault `agents-flow.md` and its `updated:` date and sets `.ai/handoff.md` `## Flow chart`
to "Flow chart updated" in the same task (see the plan for the no-vault-access case).

## T001 — Supervision settings: config, validation, manifest, recovery restore
Status: TODO
Dependencies: none
Model: sonnet

### Goal
R5/Settings: the four `AI_SUPERVISE*` settings are read from the user config, validated before any agent, captured with the approved run and restored on resume. No behaviour uses them yet.

### Implementation notes
- `scripts/lib/common.sh` `ai_config`: add `AI_SUPERVISE`, `AI_SUPERVISE_PLAN_ROUNDS`, `AI_SUPERVISE_ESCALATE_ROUND` and `AI_SUPERVISE_ESCALATE_MODEL` to the known keys. Add `ai_supervise_settings` that sets defaults (1, 3, 3, `claude-fable-5-1`), `ai_die`s on invalid values (`AI_SUPERVISE` 0|1; rounds 0–9; escalate round 1–9; model `^[A-Za-z0-9._:-]{1,64}$`) and EXPORTS the four validated values (children never see a raw/unset value).
- `scripts/lib/workflow.py` `RUN_SETTINGS`: add the four keys. `scripts/ai-recover`: add them to the `unset` list and the restore `case` list.
- `scripts/ai-pipeline`: call `ai_supervise_settings` next to the `AI_REVIEWER` check (before `ai_lock`/any agent). `scripts/ai-review` and `scripts/ai-run` call it after argument parsing too (hand-run use is validated the same way).
- Add a test that the key lists in `ai_config`, `RUN_SETTINGS` and both `ai-recover` lists are identical (parsed from the files, no exceptions), so a later setting cannot be half-wired.
- `tests/test_workflow.py` `ToolkitTest.setUp`: `self.env['AI_SUPERVISE'] = '0'  # supervision has its own tests` beside `AI_AUTO_RECOVER`, so existing plan-stop, malformed-review and counts-lie tests keep today's behaviour unchanged; supervised tests set `AI_SUPERVISE='1'` per call.
- README/`docs/workflow.md` configuration section: list the settings with defaults ("used by the supervisor"). Flow unchanged in this task.

### Likely affected modules
scripts/lib/common.sh, scripts/lib/workflow.py, scripts/ai-recover, scripts/ai-pipeline, scripts/ai-review, scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Each invalid value stops `ai-pipeline` with a message naming the setting before any Claude/Codex call (mock call files absent); an invalid `AI_SUPERVISE` also stops a hand-run `ai-review --plan` and `ai-run` before any agent.
- Values from the config file are captured in the manifest; after the config file changes, a recovery resume (`AI_RECOVERY_ATTEMPT` path) still sees the approved values (pattern: `test_resume_ignores_user_config_the_approved_run_did_not_have`).
- The key-list consistency test passes.

### Validation
`python3 -m unittest tests.test_workflow -k supervise_settings`; `.ai/bin/ai-check`

### Result / notes

## T002 — Host plan-review round records and plan history (context only)
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
R2: a plan-review round number from host records and a plan-only history that pairs each round's findings with its plan-dispositions section.

### Implementation notes
- Depends on T001: this task changes `scripts/ai-review` (plan mode `--base`, round recording), which T001 also changes (settings check), and its pipeline/hand-run tests rely on T001's fixture default `AI_SUPERVISE='0'`.
- Every `plan-rounds` action takes `BASE`: the pipeline passes `base_sha`; `ai-review --plan` by hand uses `merge-base` of `--base REF` (now accepted in plan mode, default `main` like `ai-pipeline`). Only records whose commit is in `BASE..HEAD` count, so a merged-then-recreated branch name starts at round 1.
- `workflow.py plan-rounds record BASE COMMIT`: COMMIT must be in `BASE..HEAD`, have the subject `chore(ai): record plan review` and a tree whose `.ai/reviews/plan.md` verifies (`plan-review-info` binding); appends `{commit, report_digest, plan_digest, blockers, majors, minors}` to `plan-rounds-<branch hash>.json` beside `fix-rounds`, idempotent per report digest (a second commit holding the same report never adds a round). Call it in `ai-pipeline` after `host_commit 'chore(ai): record plan review'` and in `ai-review --plan` by hand after its own commit (also when the commit was a no-op: record the existing HEAD only if it holds that report).
- `plan-rounds sync BASE`: when the current verified `plan.md` has no record, records the newest host-subject commit in `BASE..HEAD` whose committed `plan.md` equals it (crash between the review's host commit and its record); no-op otherwise. `ai-pipeline` calls it at the top of the plan-review loop, `ai-review --plan` and `ai-run --revise-plan` before reading `current`.
- `plan-rounds count BASE` / `plan-rounds current BASE`: records in `BASE..HEAD`; `current` prints `n report_digest` and fails when `.ai/reviews/plan.md`'s digest is not the last such record. Legacy init (no store yet): once, from exact-subject commits in `BASE..HEAD` that changed `plan.md` (document: can only raise n).
- `workflow.py plan-history BASE [--count]`: for each recorded round (in `BASE..HEAD`) before the current one, findings (ID, level, title via `finding_title`) from the committed `plan.md` at that record, and the disposition per ID from the section `## Plan review round <k> (report <digest>)` of `.ai/reviews/plan-dispositions.md` at HEAD (format in the plan; "no revision recorded" when absent). Rendered like `render_rounds` under `## Previous plan review rounds`, capped. Docstring: context only, never authority. Never reads `current.md` or implementation-review commits.
- Flow unchanged (records only); `docs/workflow.md` one paragraph on plan rounds.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-pipeline, scripts/ai-review, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Three plan rounds (mock Codex plan reviews with different IDs/titles, sections for rounds 1–2 written by the test): history lists rounds 1–2 with dispositions; an area repeated in rounds 1–3 and an unrelated one both appear; earlier implementation reviews in the same history are absent.
- An agent commit with the plan-review subject (no host record) does not change `plan-rounds count` once the store exists; a tampered `plan.md` fails `record`.
- The pipeline and a hand-run `ai-review --plan` both leave one record per review; recording the same report from a second commit adds nothing.
- Merged-then-recreated branch name: `feature/x` with two recorded rounds is merged into `main` and deleted, a new `feature/x` from `main` gets its first review → `plan-rounds current BASE` prints round 1.
- Host commit of a plan review present but no record (simulated crash): `plan-rounds sync BASE` records it once and `current` succeeds; a forged `plan.md` in such a commit is not recorded.

### Validation
`python3 -m unittest tests.test_workflow -k plan_rounds`; `.ai/bin/ai-check`

### Result / notes

## T003 — Plan-dispositions section writer and round-specific validator
Status: TODO
Dependencies: T002
Model: opus

### Goal
R1/R2: a host-bound section per plan-review round and a validator that checks only that section and keeps the plan gate.

### Implementation notes
- `workflow.py PLAN_DISPOSITIONS = .ai/reviews/plan-dispositions.md`; `PLAN_REVISION_RECORDS` = the R1 file list.
- `start-plan-dispositions BASE`: from `plan-rounds current BASE` (round n, report digest) and HEAD, create the file (title + comment explaining the contract) if missing and append the section header exactly as in the plan's contract, unless the last section already is that header (resume: no duplicate).
- `plan-dispositions-check --since START [--fresh]`: implement the full contract from `.ai/current-plan.md` ("Plan-dispositions section contract"); the text above the section is compared with START's committed file by the three-case rule there (START has the header → START's text above it; else START's whole file; no file at START → the exact host preamble); "pre-existing task statuses unchanged" compares with the committed `tasks.md` at START. `PLAN_DISPOSITION_ROW` accepts `accepted|rejected|needs-human`. Prints `accepted=a rejected=r needs_human=h`; `--questions` prints at most 3 needs-human questions, each whitespace-collapsed to one line and capped at 300 chars, plus `(+k more in .ai/reviews/plan-dispositions.md)` when there are more (for the revision record and the bounded stop message).
- `plan-revision-scope START`: like `triage-scope`, with `PLAN_REVISION_RECORDS`.
- No caller yet; flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Adversarial validator tests, each failing with a specific message: missing row; duplicate/conflicting rows; row for an unknown ID; rows only in an older section with the same IDs; Convergence line only in an older section (round 3); rejected without evidence; accepted without a task / with an unknown or DONE task; needs-human without a question; a pre-existing task status changed or a new task DONE; an edited earlier section; a second header for the same round.
- Complete section passes and prints the counts; MINOR rows are optional; round 2 needs no Convergence line.
- Above-the-section rule: START already holding the same header (rows committed) passes; file absent at START with the exact preamble passes, an edited preamble fails; START without the header requires its whole file unchanged above.
- `--questions` with 5 multi-line questions of 1000 chars prints 3 single-line questions of ≤ 300 chars and `(+2 more ...)`.
- `plan-revision-scope` rejects a source file and accepts every listed record.

### Validation
`python3 -m unittest tests.test_workflow -k plan_dispositions`; `.ai/bin/ai-check`

### Result / notes

## T004 — ai-run --revise-plan: prompt, read/plan-only allowlist, host commit with log entry, outcome record
Status: TODO
Dependencies: T001, T003
Model: opus

### Goal
R1/R5: a standalone, hand-testable revision mode with an enforced edit boundary, a counted host commit that leaves the checkout clean (its run-log entry included) and a durable outcome record (needs-human questions), before the pipeline uses it.

### Implementation notes
- `scripts/ai-run --revise-plan [--since COMMIT] [--base REF]` (exclusive with `--triage`; `--since` now valid for both; `--base` default `main`, BASE = its merge-base with HEAD, the pipeline passes `base_sha`): requires a verified plan review with BLOCKER+MAJOR > 0 (`plan-review-info`), `plan-rounds sync BASE` then `plan-rounds current BASE`, `tasks untouched`, and refuses with `Plan revision: this plan review was already revised; review again (ai-review --plan).` when a `plan-revisions` record exists for the current report digest (no second host commit/record for one report). Mirrors the triage block: scope check (`plan-revision-scope`) before and after; if `plan-dispositions-check --since S --fresh` already passes, record without a session; else require no dirty files beyond records, `start-plan-dispositions`, commit it (`chore(ai): open plan dispositions`), run one session, then validate.
- Session: prompt `templates/.ai/prompts/plan-revision.md` (new; installed by `setup-project` like the other prompts; missing in `.ai/prompts` → die naming `setup-project --upgrade`) + host `REVISION CONTRACT` (round n, report path, section header, editable files, needs-human rule, Convergence rule from round 3 with "redesign the area as a whole", "do not commit; the host commits") + `plan-history BASE` output as PREVIOUS PLAN ROUNDS. Model: `--model` from the caller (default `opus` when none; the pipeline always passes it, T005/T006). Per-call limits as any `ai-run` (`--run-timeout`, `--session-timeout`).
- Allowlist (plan review round 4 P1; same policy as the catch-up fix's no-Bash reviewer): new `workflow.py plan-revision-allowlist` = `Read`, `Glob`, `Grep`, `Edit(./<path>)` for each editable R1 record, nothing else: no Bash at all (no git, no inherited project entries). `claude_session` takes the allowlist and the `--tools` list as parameters: `--revise-plan` passes `--tools Read,Glob,Grep,Edit`. The host prepares the git context the session needs (plan history and the plan files' recent diff in `.ai/local/revision-context/`, removed afterwards) and does all staging and committing itself (the host commit below); the session never commits. Tests: invocation assertions that Bash/Write are absent and the project allowlist is ignored; mission control runs a live check in a disposable fixture after the task.
- Host commit, exactly in the order of the plan's "Revision host commit and record" (P1/P2 of round 3): counts from `plan-dispositions-check --fresh` and the bounded `--questions` text; `ai_log plan-revision 'plan revised (round n): accepted a, rejected r, needs-human h' ...` and the state line BEFORE the commit; `git add` the existing R1 records incl. `.ai/run-log.md`; `git commit --allow-empty -m 'chore(ai): record plan revision'`; `ai_guard_verify`; then ONE `plan-revisions record HEAD --accepted a --rejected r --needs-human h` write with the questions on stdin (new per-branch store `{commit, report_digest, round, accepted, rejected, needs_human, questions}`; subject must match; questions re-bounded by the helper); post-commit scope + clean check (hook guard). Nothing writes to the checkout after the commit. Outcome log `outcome plan_revision ROUND RESULT MODEL SECONDS` (new kind; `outcomes_report` ignores it; `.ai/local`, not tracked).
- Round 5 P1, initial-state contract: a missing revision store, or a valid store with no outstanding needs-human decision, lets the normal missing/invalid-report review path run (fresh install, `AI_SUPERVISE=0`); corrupt authority state, or an unverifiable report while an outstanding needs-human decision may apply, fails closed. `plan-rounds sync` treats an absent store the same way. Tests: fresh installation; forged `plan.md` replaced with `AI_SUPERVISE=0`; outstanding needs-human with missing or corrupted evidence.
- `workflow.py plan-revisions decision`: as in the plan (exit 0 + stored questions when the verified current `plan.md` has a reachable record with `needs_human > 0`; exit 1 when not; exit 2 on an unreadable store/report). Used by T005/T006.
- No pipeline change; flow unchanged. `ai-run --help`, `docs/workflow.md` describe the mode and how a needs-human decision is cleared (answer, commit, `ai-review --plan` by hand).

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, templates/.ai/prompts/plan-revision.md, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Mock Claude (new `REVISION CONTRACT` branch, modes accept/reject-only/needs-human/touch-source/edit-plan-review/no-commit) by hand: MAJOR plan review → `ai-run --approved --revise-plan` → section filled, one host commit, one host record; reject-only changes only `plan-dispositions.md` (plus the host's `run-log.md`/`state.md` lines).
- After a successful revision `git status --porcelain --untracked-files=all` is empty, the revision commit contains the new `run-log.md` line, and a following hand-run `ai-review --plan` starts (no "Commit the plan before reviewing it").
- The record holds the counts; with needs-human rows it holds the bounded questions and `plan-revisions decision` prints them (exit 0); after a hand-run `ai-review --plan` produces a new report, `decision` exits 1; a corrupt store makes it exit 2.
- Generated `--allowedTools` contains no unrestricted `Edit`/`Write`, no `ai-check`/`validate`; every `Edit(...)` is one of the R1 files; `--tools` is exactly `Read,Glob,Grep,Edit` (asserted from the mock's args; no Bash, round 5 P2).
- A session touching source, `plan.md` or a gate file stops with nothing counted; an uncommitted but complete section is recorded without a second session; `--triage` behaviour unchanged.
- Resume shapes: (a) the session wrote its rows (uncommitted; the session never commits) and the run died before the host commit; a hand-run `ai-run --revise-plan` without `--since` (START = HEAD, which already holds the section) records it without a session; (b) first revision (file absent at START) passes with the host preamble. A second `ai-run --revise-plan` for an already recorded report refuses with "already revised", no new commit or record.

### Validation
`python3 -m unittest tests.test_workflow -k revise_plan`; `.ai/bin/ai-check`

### Result / notes

## T005 — Plan-revision stage, per-run reservation and terminal recovery rules
Status: TODO
Dependencies: T001, T004
Model: opus

### Goal
A host-bound `plan-revision` stage that a crash at any point completes once, and recovery that never sends supervision stops or a recorded needs-human decision to a Claude session.

### Implementation notes
- `run-manifest stage-set plan-revision START`: binds the verified plan report digest (triage keeps the current-review digest); `stage_fields` accepts both names; messages say "Plan revision stage: ..." for this stage.
- `stage-verify` dispatches by name: plan-revision → `plan-review-info` verifies, report digest matches, `plan-revision-scope START`; no `plan-revisions` record commit in START..HEAD → `pending`; a record commit with a dirty tree → fail `Plan revision stage: uncommitted changes after the counted revision commit.` (as triage, `workflow.py:1209-1210`; never a second `ai-run`); else `committed`. Since T004 writes the outcome in the same record, `committed` implies the outcome is stored.
- `run-manifest revision-reserve DIGEST LIMIT`: digest already reserved → prints the count (no change, no limit check); else count < LIMIT → append, print the new count; else fail `plan review: supervision limit reached (N revisions this run)`. Plus `revision-count`; `start` resets the list, a resume keeps it. Reserved BEFORE `stage-set` (precedent: `ai-recover:65` reserves before anything interruptible).
- `scripts/ai-pipeline`: `plan_revision_model` (round n from `plan-rounds current "$base_sha"`, manifest-restored `AI_SUPERVISE_ESCALATE_*`) and `complete_plan_stage` exactly as in the plan's loop section: `stage-verify`; `committed` → `stage-clear`; `pending` → `revision-reserve DIGEST "$AI_SUPERVISE_PLAN_ROUNDS"` again (idempotent), `ai-run --approved --revise-plan --since START --base "$base_sha" --model "$(plan_revision_model)"` plus `--session-timeout`/`--knowledge-dir` as in `triage_args`, `stage-verify` = committed, `stage-clear`. `complete_plan_stage` writes nothing to the checkout. At start, dispatch the open stage by name (`complete_stage` for triage, `complete_plan_stage` for plan-revision). Fix the "triage stage" wording at the `open_stage` read.
- `scripts/ai-recover`: open-stage leftovers checked with the stage's own scope helper; add always-escalate patterns `*'Plan revision stage'*`, `*'supervision limit reached'*`, `*'needs your decision'*`. After the open-stage block and before the stop-recording commit and any Claude session: `plan-revisions decision` exit 0 → escalate `plan review needs your decision: <stored questions>` (also when the recorded reason is a crash or unknown); exit 2 → escalate (unreadable record).
- Flow change (recovery rules): vault `agents-flow.md` recovery part + `updated:`, `docs/workflow.md` recovery section, handoff `## Flow chart`.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-pipeline, scripts/ai-recover, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md, README.md

### Acceptance criteria
- Helper tests: stage-set/verify for plan-revision (pending, committed, dirty tree after the record commit fails, foreign report, out-of-scope file, agent commit with the revision subject does not close it); reservation idempotent per digest (also at the limit: LIMIT 1 with the digest reserved passes), a new digest at the limit fails, reset by `start`, kept by a resume.
- `complete_plan_stage` on an open stage with a committed record only clears it (no `ai-run` call, no "already revised" error); on a pending stage it passes the model `plan_revision_model` gives for the round (mock args).
- `ai-recover` with each new reason escalates without a Claude session (`recover-calls` absent) and an interrupted plan-revision stage with source leftovers escalates without a commit.
- `ai-recover` with last-error `unknown` (crash) and a recorded needs-human revision for the current report escalates with the stored questions, no `recover-calls`, no pipeline resume.
- Existing triage-stage and recovery tests pass unchanged.
- README's recovery section describes the plan-revision stage and its resume/terminal rules as implemented (round 4 P3).

### Validation
`python3 -m unittest tests.test_workflow -k plan_revision_stage`; `python3 -m unittest tests.test_workflow -k triage_completion`; `.ai/bin/ai-check`

### Result / notes

## T006 — Supervised plan-review loop in ai-pipeline
Status: TODO
Dependencies: T001, T005
Model: opus

### Goal
R1/R2/R5: the pipeline revises within limits, always re-reviews after a revision on a clean checkout, and stops for the human on limit, needs-human (also after a crash) or out-of-scope.

### Implementation notes
- Replace the single plan-review block with the loop in `.ai/current-plan.md`. It starts with `plan-rounds sync "$base_sha"`, then the open-stage dispatch, then the decision check: `plan-revisions decision` exit 0 → `plan review needs your decision (round n): <stored questions>` stop (last-error + notify, bounded text from the record), exit 2 → stop; this check runs at startup and after every `complete_plan_stage`, before any re-review, revision or implementation. Review is needed when `plan-review-info` is not current OR a `plan-revisions` record exists for the current report digest. After each review: host commit, `plan-rounds record "$base_sha" HEAD`, re-check current.
- Re-review prompt (`ai-review --plan --base "$base_sha"`, host-appended): `PLAN REVISION CONTEXT` with round n, "dispositions of round n−1: .ai/reviews/plan-dispositions.md", and `plan-history`; update `templates/.ai/prompts/plan-review.md` to say rejected findings are re-judged on their evidence. Adjust `test_review_context_plan_review_and_recheck_prompts_have_neither` (plan reviews get plan history only, never implementation rounds).
- BLOCKER+MAJOR > 0, in this order: `AI_SUPERVISE=0` → today's stop and message; `revision-reserve DIGEST "$AI_SUPERVISE_PLAN_ROUNDS"` fails → `plan review: supervision limit reached (N revisions this run); BLOCKER b, MAJOR m remain`; then `stage-set plan-revision`, `complete_plan_stage` (T005: reserves again idempotently, model from `plan_revision_model`), `ai_guard_verify`. Never `stage-set` before the reservation.
- After the stage: the decision check above; when it passes, `ai_notify "🔁 Plan revised (round n/N): accepted a, rejected r"` (N = `AI_SUPERVISE_PLAN_ROUNDS`, counts from the record) and the re-review. No `ai_log` and no other checkout write between the stage and the re-review: the revision's log entry is already in its host commit (T004, P1 of round 3).
- Tests: supervised tests set `AI_SUPERVISE='1'` (fixture default is `0`, T001). Add a mock Codex plan mode `MOCK_CODEX_PLAN=major-once` (MAJOR on the first plan-review call, APPROVE after) beside the existing always-MAJOR `major`; the mock Codex appends `git status --porcelain --untracked-files=all` (empty marker when clean) to a per-call file so tests can assert the checkout state at each plan-review call; the mock Claude's prompt assertion gains the `REVISION CONTRACT` branch (T004). Logging stays enabled (real `ai_log`, tracked `.ai/run-log.md`).
- Flow change: vault `agents-flow.md` big picture (plan-review loop, stops, escalation, durable needs-human) + `updated:`, README/`docs/workflow.md`, `ai-pipeline --help`, handoff `## Flow chart`.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-review, templates/.ai/prompts/plan-review.md, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Mock run (`MOCK_CODEX_PLAN=major-once`): plan MAJOR → revision → APPROVE → implementation → review → PR, with the notification and the revision's run-log line in the revision commit; the checkout is clean at the second plan-review call (asserted from the mock's per-call status file).
- Existing plan-stop tests (`test_pipeline_plan_review_gates_implementation`, `test_plan_review_is_bound_and_tracks_the_whole_tree`) pass unchanged under the fixture default `AI_SUPERVISE=0`.
- A needs-human row with a long multi-line question → the stop message and `.ai/local/last-error` hold the bounded single-line text (T003 cap), no second plan-review call, no implementation call.
- All-rejected dispositions-only revision → `codex-plan-calls` = 2 before any implementation call; the second prompt contains `PLAN REVISION CONTEXT`; the checkout is clean at the second call.
- Limit (`AI_SUPERVISE_PLAN_ROUNDS=1`, always-MAJOR reviewer) → limit stop after one revision; `AI_SUPERVISE=0` → today's stop, no revision call; needs-human → stop listing the question; revision touching source → stop. With `AI_AUTO_RECOVER=1` none of these run a recovery session.
- Revisions 1–2 run on `opus`, revision 3 on the escalation model (mock args), and round 3 without a Convergence line fails the stage.

### Validation
`python3 -m unittest tests.test_workflow -k supervised_plan`; `.ai/bin/ai-check`

### Result / notes

## T007 — Crash and resume scenarios for supervised plan revision
Status: TODO
Dependencies: T006
Model: opus

### Goal
A supervised run survives crashes and recoveries with exact counting, approved settings and a needs-human decision that cannot be lost.

### Implementation notes
Tests through `ai-pipeline` with mocks (patterns: `test_triage_completion_crash_after_counted_commit_does_not_count_twice`, `test_triage_completion_watchdog_crash_recovery_completes_once`). Crash points:
1. Mock Claude revision branch: kill runner + pipeline after the session's edits (uncommitted), and around the host's preamble and revision commits (round 5 P2: the session never commits).
2. Helper-level interruption after the host revision commit before `plan-revisions record`, after the record before `stage-clear`, and after `stage-clear` before the decision check / re-review.
3. Host-write windows (state written directly by the test as the crash leaves it, then `ai-pipeline` rerun): reservation present but no stage (crash between `revision-reserve` and `stage-set`), with `AI_SUPERVISE_PLAN_ROUNDS=1` so a non-idempotent limit check would wrongly stop; stage open but no reservation (a stage opened by an older ordering); plan-review host commit present but no `plan-rounds` record.
4. Round-3 model: always-MAJOR reviewer, crash during the third revision session; the resumed session runs on `AI_SUPERVISE_ESCALATE_MODEL` (mock args), not `opus`.
5. Needs-human (P2 of round 3): mock revision with a needs-human row; crash after `stage-clear` before the decision check, and after the record before `stage-clear`.
Fix any defect found in T004–T006 code within this task (record it in the result).

### Likely affected modules
tests/test_workflow.py, scripts/ai-pipeline, scripts/ai-run, scripts/ai-recover, scripts/lib/workflow.py

### Acceptance criteria
- Each crash point of 1–3, resumed by `ai-pipeline` (human rerun and `ai-watchdog --recover` path): one `plan-revisions` record, `revision-count` 1, exactly one re-review on a clean checkout, no second revision session for the same report; the plan-rounds window resumes into a revision, not a human stop, with one `plan-rounds` record for that report.
- Crash point 4: `revision-count` 3, the resumed revision's model is the escalation model, and the section carries the Convergence line.
- Crash point 5, resumed by a human rerun and by the watchdog recovery path (`AI_AUTO_RECOVER=1`): both stop with "needs your decision" and the stored questions; `codex-plan-calls` unchanged, no new revision or implementation `mock-invocations`, no `recover-calls`. After the test answers (commits a plan change) and runs `ai-review --plan` by hand with an approving mock, a rerun reaches implementation.
- A human restart after the limit gives a fresh per-run allowance but does not redo a revision already recorded for the current report (it re-reviews first).
- Config file changed between start and recovery resume: the resume uses the approved `AI_SUPERVISE_PLAN_ROUNDS` and escalation settings.

### Validation
`python3 -m unittest tests.test_workflow -k supervised_plan_resume`; `.ai/bin/ai-check`

### Result / notes

## T008 — Extra fix round from host-verified falling counts
Status: TODO
Dependencies: T001
Model: opus

### Goal
R3: one extra fix round per run, only for a strictly falling host-verified trend, reserved before it starts.

### Implementation notes
- `fix-rounds record COMMIT`: also store the verified review it triaged (`review_info_values()` at record time: head, digest, blockers, majors) as a dict record; readers accept legacy bare hashes (no counts). Keep `stage_verify`, `count` and `init` working with both shapes.
- `fix-rounds trend BASE`: the last two records reachable in BASE..HEAD that carry counts, plus the current verified review (`review-info`, must be a different review head than the last record); prints `x y z` or fails `insufficient history`.
- `run-manifest extra-round-reserve DIGEST` / `extra-round`: once per run (reset by `start`, kept by resumes).
- `ai-pipeline` at `fixes >= max_fix_rounds`: with `AI_SUPERVISE=1`, no reservation yet and x > y > z → reserve with the current review digest, `ai_log`, notify `🔁 Extra fix round: findings falling (x → y → z)`, then triage as round max+1 (the triage commit carries the log line, as today's triage); a reservation for the current review digest found on resume allows that one round; otherwise today's draft path.
- Flow change: vault `agents-flow.md` fix-round part + `updated:`, README/`docs/workflow.md`, handoff `## Flow chart`.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-pipeline, scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Falling 3 → 2 → 1 with `--max-fix-rounds 2` → one extra round, notification, then draft/PR as the review says; a further limit → draft, no second extra round.
- Flat or rising counts, legacy records, fewer than two counted rounds, agent commits imitating review/triage subjects, records from another branch → no extra round (draft as today).
- Boundary: round 1 triaged by the old toolkit (legacy bare hash), rounds 2–3 with counts and a falling current review → `trend` uses only rounds 2–3 + current (x > y > z → extra round); with only round 3 counted → `insufficient history`.
- Crash right after the reservation → resume uses the reserved round once; `AI_SUPERVISE=0` → draft as today.

### Validation
`python3 -m unittest tests.test_workflow -k extra_fix_round`; `python3 -m unittest tests.test_workflow -k fix_round_count`; `.ai/bin/ai-check`

### Result / notes

## T009 — Retry a malformed plan or code review once
Status: TODO
Dependencies: T001
Model: opus

### Goal
R4: format errors of Markdown reviews get one retry; integrity failures and re-checks never do.

### Implementation notes
- `workflow.py`: extract the content checks of `publish_review` and `publish_plan_review` into one function per mode, used by both publish paths and by `review-format-check plan|code REPORT` (no writes; prints the error, exit 1).
- `scripts/ai-review` plan and code paths only: after `run_review`, format check; on failure with `AI_SUPERVISE` ≠ 0 and no retry used yet → notify `🔁 Review format retry (<mode>): <error>`, keep the first report path in the log line, rerun `run_review` with `FORMAT ERROR: <message>. Return the full report again in the required structure.` appended (same reviewer chain incl. Claude fallback), then publish (a second format failure dies as today, prior review preserved). After a retried publish append one run-log line (`ai_log`); `ai-pipeline review_record` adds `.ai/run-log.md` when dirty; the hand-run plan path commits it with the record.
- Re-check path unchanged. Codex non-zero exit, limit handling, `unchanged` checkout check and binding writes stay `ai_die` with no retry.
- Flow change: vault `agents-flow.md` review part + `updated:`, `docs/workflow.md`, handoff `## Flow chart`.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-review, scripts/ai-pipeline, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md, README.md
- Round 5 P3: reset per-attempt reviewer metadata (label, model, fallback reason) before each reviewer call and clear Claude labels when Codex succeeds, so a retry after a Claude fallback publishes the right label, outcome attribution and fallback-log row.

### Acceptance criteria
- Codex plan and code: malformed then valid → published, 2 calls, notification, run-log line committed with the review (checkout clean afterwards); malformed twice → stop, prior report preserved; valid → 1 call; counts-lie → retried as a format error.
- Claude fallback reviewer: malformed then valid → published.
- Checkout mutated during review (`mutates`) and Codex exit error → no retry; malformed first report, then the retried `run_review` mutates the checkout → the `unchanged` check still fails on the second call (stop, prior review preserved); malformed re-check JSON → one call, upheld (as `test_recheck_command_missing_duplicate_extra_malformed_count_as_upheld`); `AI_SUPERVISE=0` → no retry.
- Every issued format retry is logged in the run log with its outcome (success or handled failure) and the first report's path, without dirtying the checkout between the two reviewer calls; tests cover malformed-twice and an integrity failure on the retry (round 4 P2).
- README describes the format retry as implemented (round 4 P3).
- Malformed Claude fallback → valid Codex retry: report label, outcome reviewer and fallback log are all Codex-consistent (test).

### Validation
`python3 -m unittest tests.test_workflow -k format_retry`; `.ai/bin/ai-check`

### Result / notes

## T010 — Docs reconciliation, flow-chart check, handoff
Status: TODO
Dependencies: T007, T008, T009
Model: haiku

### Goal
R6: docs and the flow chart match the code; the PR body has the right test instructions.

### Implementation notes
Read README, `docs/workflow.md`, `templates/CLAUDE.md`, `templates/AGENTS.md` against the code of T001–T009; fix contradictions only (no new behaviour). Add `docs_consistency` REQUIRED phrases (e.g. `ai_supervise=0`, `plan-dispositions.md`, `needs-human`, `supervision limit reached`). Docs must not promise a cumulative run budget (OR-09). Check vault `agents-flow.md` covers T005, T006, T008, T009 and its `updated:` date; append a dated hub `agents.md` Log line (no checkbox ticks). `.ai/handoff.md`: "Manual testing for the human" (Needs you: one real supervised run on a small plan with a deliberately incomplete task, including a needs-human stop, a crash/recovery attempt on it and clearing it with a hand-run `ai-review --plan`; everything else listed under "Covered by automated tests" with test names), `## Flow chart` = "Flow chart updated".

### Likely affected modules
README.md, docs/workflow.md, templates/CLAUDE.md, templates/AGENTS.md, tests/test_workflow.py, .ai/handoff.md, vault agents-flow.md, vault agents.md

### Acceptance criteria
- `docs_consistency` tests pass with the new phrases; the flow chart lists every flow change of this branch; handoff names the tests.

### Validation
`python3 -m unittest tests.test_workflow -k docs_consistency`; `python3 -m unittest tests.test_workflow -k pr_body_flow`; `.ai/bin/ai-check`

### Result / notes
