# Spec: Flow batch 10: faster gate (TS-01), flow events and metrics (ME-01), follow-up plan review (FL-39)

## Objective
Approved by Zack on 2026-10-21, planned 2026-10-21 in an unattended planning session on
`fix/flow-batch-10` (created from `fix/flow-batch-9` at 4fea72d; batch 9 is complete there apart
from T118's host verification and not merged; this PR targets `fix/flow-batch-9` until that
merges). Sources: vault `agents-backlog.md` TS-01, ME-01, FL-35 (called FL-39 in Zack's brief;
same defect), with FL-28, FL-23, BR-17, CU-1, CU-5 and OR-04 read for context. Revised
2026-10-21 after the hand-run Codex plan review (round 1, see the last section).
1. **TS-01 (1) Worker count**: `tests/run_parallel.py` default raised from `min(8, cpu)` to
   `min(14, cpu - 2)` (at least 1) unless the handoff records another measured value;
   `AI_TEST_WORKERS` still overrides; the worker count and where it came from are printed in the
   gate output.
2. **TS-01 (2) Sessions run targeted tests; the host runs the full gate**: an implementation
   session runs its task's `Targeted:` checks and fast static checks, not `.ai/bin/ai-check`; the
   host gate after the session stays the authoritative full gate and decides DONE. Opt-in for the
   old behaviour: projects whose recorded gate is under 120 s, or `AI_SESSION_GATE=full`. The
   FL-28 session allowance follows the mode. The reusable task format and the planning prompts
   name `Targeted:` lines so new queues provide them; older queues still work.
3. **ME-01 part 1, flow events**: one append-only, schema-versioned JSONL event log in the host
   state dir, written only by host scripts, with kinds `gate`, `stop`, `recovery`, `ruling`,
   `review`, `pr` and `run`; every event and outcome row of a pipeline run carries that run's id;
   bounded with rotation that never loses an active run; readers tolerate unknown kinds. No event
   helper runs once the approved gate is known to be broken.
4. **ME-01 part 2, reading it**: `ai-status --metrics [--since DATE] [--project NAME] [--json]`:
   per project and per run, tasks, first-pass rate, timeouts, median task and gate time, stops by
   category, review rounds and findings by reviewer; plain text and JSON.
5. **FL-39 (backlog FL-35) follow-up batches skip the plan review**: "untouched" is decided
   against the run's `--base` for the plan review AND the supervised plan revision (and its
   interrupted-queue repair), DONE blocks of earlier batches stay byte-identical, and every
   skipped plan review prints one line saying why.
6. Docs: README, `docs/workflow.md` (where the data lives and how to read it), the vault flow
   chart, the handoff.

## Verified against the code (4fea72d, 2026-10-21; re-checked at 1921888 for the plan review)
- **Worker count**: `tests/run_parallel.py` `worker_count()` (~59–69): empty `AI_TEST_WORKERS` →
  `min(8, os.cpu_count() or 1)`; a non-positive or non-integer value exits with
  `run_parallel: AI_TEST_WORKERS must be a positive integer`. The worker count already appears in
  the last summary line (`Ran N tests in Xs (B batches on W workers, N collected)`, ~712) and in
  `Test time: … across W workers` (~606), but only at the end: a gate killed by its timeout prints
  neither. `.ai/validate` (gate file) runs the shell syntax checks then `python3
  tests/run_parallel.py`; nothing to change there. README and `docs/workflow.md` mention the
  `min(8, CPU count)` default. Its tests are named `test_parallel_runner_*` (not `run_parallel`).
- **Session gate rule**: the RUNNER CONTRACT is built in `scripts/ai-run` (~927–929) and says "A
  gate run that outlives a tool call is not a blocker: the full gate the runner runs after the
  session decides". The prompt templates `templates/.ai/prompts/runner.md` (~13–14 "run its
  targeted checks and `.ai/bin/ai-check`" and the "How to work here" bullet ~49–57 "Run the full
  gate as `.ai/bin/ai-check` with … `run_in_background: true`"), `triage.md` (same bullet ~55–63),
  `fix-review.md` (~12 "targeted tests, full gate") and `implement.md` (~8, interactive) tell
  sessions to run the full gate. `templates/CLAUDE.md` step 4 says the same. The reusable task
  format (`templates/.ai/tasks.md` ~33) and `plan.md` (~13), `plan-revision.md` (~17),
  `triage.md` (~26) ask only for generic "exact validation commands": no `Targeted:` label.
- **FL-28 allowance**: `claude_session` (`scripts/ai-run` ~318–333): an implementation session
  (`track_attempt=yes`) gets `session_timeout + min(2 × gate-seconds, session_timeout)`;
  `gate-seconds` (`scripts/lib/workflow.py` ~4466) is the largest of the project's last 3 passing
  host gates from `outcome gate` rows (0 without any). `session_timeout` defaults to 1800 (3600
  in pipeline mode, ~114). Tests `test_session_gate_allowance_*` (`tests/test_workflow.py`
  ~10979–11030) seed 300 s and 900 s gates with no override and expect the allowance.
- **Host gates**: `ai-run` `host_gate` + `record_gate CODE STARTED` (~265–305) after a DONE
  session (~737), in the gate-only retry (~792) and the final gate (~884); `ai-pipeline`
  `ensure_validated` (~262–268, stage `validation`) and `ai-recover` commit_and_rerun (~303) call
  `ai-check` without recording anything. `ai-check` stores its log path in
  `.ai/local/validation.json` (`stamp record`, workflow.py ~870–883).
- **Outcome log**: `outcomes.jsonl` in `state_root()` (workflow.py ~3868), appended by
  `append_outcome` (~3957: flock on the log's own descriptor, newline guard, single write,
  fsync) and never rotated. `next_attempt_seq` (~3994) documents why a lock on a replaced inode
  no longer excludes later lockers. Kinds: `task`, `review` (with `route` since T110),
  `plan_revision`, `plan`, `catchup`, `gate` (`result`, `seconds` only). Attempt numbering
  (`attempt-info`, `next_attempt_seq`, crash reconcile) reads the whole file. `outcomes_report`
  (~4609) skips `gate` rows. Readers keep any dict line, so an extra field is compatible.
- **Attempt markers and crash rows**: `open_attempt` (~4184) writes a marker with
  `MARKER_FIELDS` (~4128; a required minimum, extra fields are allowed); `reconcile_marker`
  (~4242) writes the `crashed` row with `time: now()` at the NEXT start, possibly during a later
  run; the marker's `started` is the attempt's own start.
- **Stops and recovery**: `ai-pipeline` `stop()` (~173–189) reads `.ai/local/last-error`, runs
  `ai_gate_check` (sets `AI_GATE_BROKEN` on a changed gate), records `ai_observe stop`, then
  either `exec ai-recover --stage STAGE` or notifies ⛔ and calls `ai_die`. `ai_die`
  (`common.sh` ~11–28) in the pipeline or recovery shell (where `AI_PIPELINE_MARKER` is set) is
  the generic terminal stop. `ai-recover` decides hard rules, limit relaunch (exit 75, the run
  stays paused), commit_and_rerun and the Claude decision; `escalate()` (~44–55) and the
  unexpected-exit `on_exit` (~123) are its terminal stops. `ai_observe` and `ai_notify_log`
  (`common.sh` ~214–221) return early when `AI_GATE_BROKEN` is set, so no project helper runs
  after a detected gate change; tests `test_observation_gate_runner_tamper_stop_runs_no_helper`
  and `test_observation_pipeline_gate_changed_by_a_hook_runs_no_helper` detect any helper run
  through a tampered `workflow.py`. No structured stop category exists anywhere (OR-04 is open).
- **Successful finishes**: `ai-pipeline` `finish()` (~89–96) is called at the no-PR finish
  (~638), the missing-origin finish (~658), the missing-`gh` finish (~663) and after the PR's
  final push (~727–730); the `chore(ai): record pull request` commit (~726) precedes that push,
  and a failed push goes to `stop` (recovery).
- **Rulings** (BR-01): `ai_ruling_rows` (queue-order and task-sections rows),
  `ai_disposition_ruling` and `ai_flow_line_ruling` in `scripts/lib/common.sh` (~326–427) each
  write their own `Ruling (KIND)` run-log rows after a successful claim in the run manifest; a
  refused or repeated claim returns before any row. **Review routing** (BR-14): `ai-review` asks
  `review-route` and logs the reason in the outcome `review` row (`--route`). **PR**:
  `ai-pipeline` `gh pr create` (~719), `gh pr ready`/`--undo` (~684–698).
- **Run identity**: `run-manifest start` (workflow.py ~1680) writes gate, branch, args, attempts,
  env; no run id and no start time. A recovery resume keeps the manifest, and so does a finished
  run (`clear-attempts` ~1736 keeps it), so "the manifest of this branch" does not mean "a run is
  active".
- **Plan review skip (FL-39)**: `ai-pipeline` ~478 runs the plan review loop only when
  `plan_review == yes`, no armed resume and `ai_helper tasks untouched` (workflow.py ~753: fails
  when ANY task is DONE). The supervised plan revision has the same rule twice: `ai-run
  --revise-plan` (~476) dies when any task is DONE, and `revision-queue-repair` (workflow.py
  ~3596–3615, called by `ai-pipeline` ~457 and `ai-run` ~173) does nothing when HEAD's queue has
  any DONE task. This repo keeps earlier batches' DONE tasks, so batches 7–9 and mission-control
  phase 2 skipped the plan review with no output. `tasks newly-done REV` (~757–773) already lists
  tasks DONE now but not at REV. `plan-keeps-done START` (~3450) checks DONE blocks stay
  unchanged; only planning calls it. Within the loop an already-current, unrevised plan review is
  not repeated (`plan-review-info` ~496).
- **CU-1** (per-attempt model stats): already done; `outcomes_report` has "Attempts by model"
  (`attempts_table`, ~4643) attributing each attempt to its own model. Nothing to build.
- **CU-5** (crash-durable outcomes): attempt markers and `outcome attempt-reconcile` exist
  (workflow.py ~4330–4361); a SIGKILLed attempt is logged `crashed` at the next start. Nothing to
  build in this batch beyond carrying the run id (A8).
- **This repo's own run**: the frozen `.ai/bin/ai-pipeline` still has the FL-39 defect, and the
  frozen `.ai/prompts/runner.md` still tells sessions to run the full gate in the background.

## Scope
- T201: FL-39, plan review decided against `--base`, skip line.
- T214: FL-39 for the supervised plan revision and its queue repair; DONE blocks kept.
- T202: worker default and the `Workers:` line.
- T203–T205: session gate mode helper and setting, `ai-run` contract and allowance, prompt
  templates. T215: `Targeted:` lines in the task format and the task-writing prompts.
- T206: event core (envelope, schema, stable lock, guarded writer, reader). T216: run context (run
  id in the manifest, `AI_RUN_ID`, `run` on outcome rows and attempt markers). T217: rotation
  that keeps every active run.
- T207–T210, T218: the writers (gate; stop and recovery; run start and end; ruling and review;
  pr).
- T211–T212: `ai-status --metrics`.
- T213: docs, flow chart and handoff audit.

## Non-goals (out of scope, for later batches)
- Mission control's display of these events.
- The weekly vault summary note (`agents-metrics.md`).
- TS-01 (3): shared prepared fixtures for the slow end-to-end pipeline tests (with FL-23's
  follow-up).
- PR open to merge time from `gh` (needs network; leave for later).
- OR-04's authoritative stop categories for recovery: this batch's `stop` category is telemetry
  only; `ai-recover` keeps deciding on its own rules and text.
- BR-17 per-role tokens and rework; only findings per reviewer are reported here.
- Mission-control hand fixes as events (they are not host scripts).
- Run attribution of outcome rows written before this batch (no `run` field): they stay in the
  `(no run record)` group; no time-window guessing (review P8).
- Events for stops after a detected gate change, and for a pipeline killed without its handlers:
  telemetry is allowed to be missing there (review P1); the notification and last-error remain
  the record.
- Any change to `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/permissions.allow`,
  `.claude/settings.json` or `.github/workflows/*` (gate files; human steps in the handoff).

## Assumptions (unattended; recorded instead of asking)
- **A1 Worker default**: `max(1, min(14, cpu - 2))`; `cpu_count() is None` → 1. If mission control
  records a measured value in the handoff ("Measured worker default: N") before the run starts,
  T202 uses `min(N, cpu - 2)` instead. `AI_TEST_WORKERS` keeps its validation.
- **A2 Worker line**: `run_parallel.py` prints `Workers: W (AI_TEST_WORKERS)` or `Workers: W
  (default, CPU count C)` as its first line, before discovery output, so a timed-out gate log still
  has it; the summary line keeps its current format (tests parse it).
- **A3 Session gate mode**: new run setting `AI_SESSION_GATE` = `auto` (default), `full` or
  `targeted`. `auto` → `full` when the project has a recorded passing host gate and the largest of
  its last 3 passes is under 120 s (0 s included: a sub-second gate), otherwise `targeted` (no
  recorded gate → `targeted`: the host gate runs anyway and records the first time). Helper
  `workflow.py session-gate` prints `full SECONDS` or `targeted SECONDS`; any error → `targeted
  0`. Validated in `ai-run` and `ai-pipeline`, kept in the run manifest and the `ai-recover`
  setting lists like `AI_REVIEW_ROUTE`.
- **A4 Allowance**: `full` keeps today's allowance (`min(2 × gate, session_timeout)`); `targeted`
  gets none (the session no longer runs the gate). The `Session:` line names the mode. Existing
  allowance tests set `AI_SESSION_GATE=full` explicitly (review P9).
- **A5 Contract text**: `targeted`: "Run the task's `Targeted:` checks (a task without them: the
  commands of its ### Validation section other than `.ai/bin/ai-check`) in the foreground and fast
  static checks; do not run `.ai/bin/ai-check`: the runner's full gate after the session is
  authoritative and decides DONE; a DONE task whose gate fails returns to IN_PROGRESS." `full`:
  today's wording plus "run `.ai/bin/ai-check` with run_in_background". The templates say "follow
  the RUNNER CONTRACT's gate rule" instead of fixing one rule. Interactive `implement.md` keeps the
  full gate (no runner, no session cap). The gate-only retry is unchanged.
- **A6 Event file**: a new `events.jsonl` beside `outcomes.jsonl`, not new kinds in
  `outcomes.jsonl`. Why: `outcomes.jsonl` must never rotate (attempt numbering, `first_pass` and
  crash reconcile read all of it), and old installed copies read it with fixed kind filters;
  events need rotation and a schema version. The existing `outcome gate` row stays (it feeds
  `gate-seconds`); the `gate` event is written next to it.
- **A7 Event record**: one JSON object per line. Envelope (reserved; no kind may use these
  names): `v` (1), `id` (16 hex), `time` (ISO UTC), `kind`, `project`, `branch`, `run` (run id or
  null). Kind fields: `gate` {task, stage, start, seconds, tests, failures, workers, result};
  `stop` {stage, category, message, recovery}; `recovery` {decision, task, attempt}; `ruling`
  {ruling_kind, key, task}; `review` {mode, reviewer, model, reason}; `pr` {action, state, url};
  `run` {action, result, base, args, tasks, gates, gate_failures, seconds}. A ruling event is
  `kind: ruling` with the BR-01 category in `ruling_kind` (review P5). Strings are capped
  (message excerpts ≤ 200 characters, one line, secrets redacted by a new `redact()` with a fixed
  token pattern list: no text redaction helper exists today; `SECRET_PATTERNS` (~1039) is about
  file names). A write failure prints one `Note:` line and never changes the caller's exit status
  or flow.
- **A8 Run context** (review P8): `run-manifest start` adds `run_id` (16 hex) and `started`
  (epoch); a resume keeps both; `run-manifest run-id` prints the id. The run is identified only
  by explicit context, never by branch or time: `ai-pipeline` exports `AI_RUN_ID` from its own
  manifest after the manifest step (human start or resume); `ai-recover` exports it from the
  manifest it is recovering; children (`ai-run`, `ai-review`, `ai-check`) inherit it. Writers
  read `AI_RUN_ID` (valid only as 16 hex); without it (standalone commands, also after a run
  finished) `run` is null. New outcome rows (`task`, `review`, `gate`, `plan`, `plan_revision`,
  `catchup`) get a `run` field when `AI_RUN_ID` is set; attempt markers record it and a `crashed`
  row reconciled during a later run takes the marker's run, not the reconciling one. Rows without
  `run` (history, standalone) are reported under `(no run record)`.
- **A9 Rotation** (review P3, P4): writers and readers serialize on a separate, stable
  `events.lock` in the state root (created once, never renamed or deleted), taken before
  `events.jsonl` is opened; writers hold it exclusively, readers shared, so a reader sees both
  files consistently. When `events.jsonl` exceeds `AI_EVENTS_MAX_BYTES` (default 8 MiB, int ≥
  65536, invalid → default) before an append, the writer keeps the lines of every ACTIVE run in
  the new live file: a run id with no `run` end event in the live file whose latest event is
  newer than 7 days (`EVENT_RUN_STALE_DAYS`; a paused recovery or a relaunch wait is active, a
  run killed without an end goes stale). Rotation happens only when it would drop at least a
  quarter of the cap (otherwise the file may exceed the cap while that many runs are active).
  Order: copy the whole live file to a temp file and replace `events.1.jsonl` with it, then
  replace `events.jsonl` with a temp file holding the kept lines; each file fsynced before its
  replace. A crash in between leaves duplicates, never a loss; readers read `events.1.jsonl` then
  `events.jsonl` and drop repeated ids.
- **A10 Stop categories** (fixed list): `timeout`, `validation_failed`, `record_format`,
  `queue_order`, `review_round_limit`, `usage_limit`, `needs_human`, `crash`, `other`; derived by
  `workflow.py stop-category STAGE` from the stage and the host's last-error text (first match in
  a fixed table). Telemetry only; recovery never reads it (OR-04 stays open).
- **A11 Event points** (review P6, P7): `stop` at `ai-pipeline stop()` (before handing over or
  dying) and at `ai-recover escalate`; `recovery` for each `ai-recover` decision (`rerun`,
  `commit_and_rerun`, `relaunch`, `escalate`, with task and attempt); `run` `start` at a human
  start and `resume` at a recovery start, after `AI_RUN_ID` is exported. Exactly one `run end`
  per run that ends in a handled way: from `finish()` after the required publishing work
  succeeded (`result`: `pr` after the final push, `no_pr`, `no_origin`, `no_gh`), and with
  `result: stopped` from the terminal paths: `ai_die` in the pipeline or recovery shell itself
  (not a subshell), `ai-recover escalate` and its unexpected-exit handler; a shell variable
  `AI_RUN_ENDED` prevents a second end in the same process. A recovery hand-over (`exec
  ai-recover`), a relaunch wait (exit 75) or a failed final push (it goes to `stop`) is not an
  end. Totals (tasks DONE in this run, gates, gate failures, seconds since `started`) come from
  this run's own records. `pr` after `gh pr create` and each draft/ready change (`state:
  draft|ready`, url); `ruling` from one shared emitter used by all three ruling writers
  (`ai_ruling_rows`, `ai_disposition_ruling`, `ai_flow_line_ruling`), only for rows actually
  written; `review` in `ai-review` (mode, reviewer, route reason).
- **A12 Gate event fields**: `project`, `branch`, `task` or `stage`, `start` (epoch), `seconds`,
  `tests`, `failures`, `workers`, `result` (`pass|fail|timeout`); tests, failures and workers are
  parsed from the gate log named by `.ai/local/validation.json` (regular file, last 256 KiB,
  integers only: `Ran N tests`, `FAILED (failures=a, errors=b)`, `Workers: W`, `on W workers`);
  unknown → null.
- **A13 Metrics**: from `outcomes.jsonl` (task and review rows) and the event log. Per run = rows
  and events whose `run` equals that run's id; runs are listed from their `run` events (start,
  resume, end; no end → `open`); rows and events with no run → a `(no run record)` group. No
  time-window matching. First-pass rate = tasks whose first attempt was `done` ÷ tasks. Timeouts
  = task attempts with `result == timeout`. Median task time per task (sum of its attempts),
  median gate time from `gate` events (fallback `outcome gate` rows). Review rounds = code review
  rows (not re-checks) per run; findings by reviewer = BLOCKER/MAJOR/MINOR sums. `--since
  YYYY-MM-DD` (UTC, inclusive), `--project NAME`; `--json` prints one object `{"v": 1,
  "projects": […], "runs": […]}`.
- **A14 FL-39**: "untouched" = `tasks newly-done "$base_sha"` prints nothing (and the queue has
  tasks). An armed resume still skips (as today). An already-current, unrevised plan review is
  not repeated (as today, inside the loop). "New tasks already started" = a task newly DONE since
  base; IN_PROGRESS/BLOCKED do not lift the review (as today). Skip line:
  `Plan review skipped: <why>` for `--skip-plan-review`, an armed resume, or tasks newly DONE since
  base (first three ids). The same base-relative rule applies to `ai-run --revise-plan` (base
  from `--base`, default `main`, as `plan_base` today) and to `revision-queue-repair --base REV`;
  without `--base` the repair keeps today's rule. A plan revision must leave every DONE block
  byte-identical (`plan-keeps-done`, as after planning) (review P2).
- **A15 T118**: T118 (batch 9, review N3) is TODO here because both branches are at 4fea72d; its
  fix (38f671c) is committed and awaits host verification on `fix/flow-batch-9`. Its block stays
  unchanged. Zack merges `fix/flow-batch-9` into this branch after T118 is DONE there, before
  approving; otherwise this run's first session verifies T118 (harmless, same fix).
- **A16 This run's gate rule**: the frozen `.ai/prompts` still say "run the full gate in the
  background"; the queue header's BATCH 10 GATE RULE overrides it for this batch: sessions run
  only targeted checks and `bash -n`, the host gate decides.
- **A17 Gate-broken telemetry** (review P1): every event write goes through a `common.sh`
  function whose first statement is the `ai_observe` guard (`[[ -z "${AI_GATE_BROKEN:-}" ]] ||
  return 0`); every helper call that prepares an event (stop category, run totals, last-error
  excerpt) happens inside such a function after the guard, never in the caller's arguments. So an
  event helper runs exactly where `ai_observe` would and never after a detected gate change.
  Missing telemetry for those security stops is accepted.
- **A18 Targeted lines** (review P11): the task format's `### Validation` section uses one
  `Targeted: <command>` line per task-specific check (fast, deterministic, with its expected
  result) and a `Gate: .ai/bin/ai-check` line; the planning, plan-revision and triage prompts ask
  for that form. Older queues without `Targeted:` lines stay valid; the contract falls back to the
  task's other Validation commands (A5).
- **A19 Test selectors** (review P10): every `Targeted:` command names a selector that matches at
  least one test today (existing regressions) or a test the task itself adds (new tests), and
  must print `Ran N tests` with N ≥ 1. Verified existing groups: `parallel_runner`, `gate_time`,
  `session_gate_allowance`, `fresh_retry`, `gate_only`, `plan_review`, `preflight_pipeline`,
  `revise_plan`, `queue_recovery`, `plan_revision_stage`, `ruling`, `review_routing`,
  `runs_no_helper`, `observation_gate`, `observation_pipeline`, `recovery_escalates`,
  `outcome_attempt`, `outcome_crash`, `outcome_report`, `runner_logs_task_outcomes`,
  `ruling_manifest`, `timeout_rerun_manifest`, `pr_undraft`, `failed_final_push`,
  `pipeline_without_remote`, `template_rules`, `Docs`, `flow_this_repo`.

## Acceptance criteria (observable)
- `AI_TEST_WORKERS` unset on a 16-CPU host → `Workers: 14 (default, CPU count 16)`; set to 3 →
  `Workers: 3 (AI_TEST_WORKERS)`; `0`/`x` → the existing error.
- A pipeline task session on a project whose gate takes 800 s gets a contract without
  "`.ai/bin/ai-check`" as an instruction to run, and no gate allowance; one on a 60 s gate (or
  `AI_SESSION_GATE=full`) gets today's behaviour. The templates carry no fixed full-gate rule for
  runner sessions; the task format and planning prompts ask for `Targeted:` lines.
- After a pipeline run, `events.jsonl` holds `run`, `gate`, `pr` (and on failure `stop`,
  `recovery`) events with `v: 1` and that run's id, and exactly one `run end` for every handled
  finish or terminal stop (local-only finishes included); outcome rows of the run carry the same
  id; a standalone command afterwards writes `run: null`. A rotation keeps every line of every
  active run, also with concurrent writers; unknown kinds and versions are skipped by readers. A
  stop after a detected gate change runs no event helper.
- `ai-status --metrics` prints per-project and per-run tables; `--json` is valid JSON with the same
  numbers; `--since` and `--project` filter.
- A queue with earlier DONE tasks and new TODO tasks gets a plan review, and a MAJOR finding on it
  is revised, re-reviewed and implemented, with the earlier DONE blocks unchanged; a resumed run
  whose new tasks already have one DONE since base does not, and prints `Plan review skipped: …`.
- `.ai/bin/ai-check` passes on the final tree; README and `docs/workflow.md` describe the event
  log, its location, rotation and `--metrics`; the vault flow chart shows the new session gate rule
  and the plan review decision.

## Plan review round 1 (hand-run Codex review)
Report `.ai/reviews/plan.md` (HEAD 2c1e273, BLOCKER 1, MAJOR 8, MINOR 2), each finding checked
against the cited code on 2026-10-21.

| ID | Severity | Disposition | Reason or task |
| --- | --- | --- | --- |
| P1 | BLOCKER | accepted | Confirmed: `ai_observe`/`ai_notify_log` skip on `AI_GATE_BROKEN` (common.sh ~214), a plain `ai_event` and helper calls in its arguments would not. A17; guarded writer and wrapper rule in T206, used by T207–T210 and T218; no-helper regressions in T206, T208, T209. |
| P2 | MAJOR | accepted | Confirmed: `ai-run --revise-plan` (~476) and `revision-queue-repair` (~3613) reject any DONE task. New T214 (base-relative revision and repair, `plan-keeps-done` after the revision, end-to-end fixture with a MAJOR plan review). A14. |
| P3 | MAJOR | accepted | Confirmed: `append_outcome` locks the log's own descriptor and `next_attempt_seq` documents the replaced-inode problem. Stable `events.lock` for writers (exclusive) and readers (shared) in T206; rotation and the multi-process regression in new T217. A9. |
| P4 | MAJOR | accepted | Confirmed: keeping only the writer's run loses another active run on the second rotation. T217 keeps every active run (no end event, latest event within 7 days) with the two-project double-rotation fixture. A9. |
| P5 | MAJOR | accepted | Confirmed: a flat record cannot carry `kind: ruling` and `kind: queue-order`. Envelope fields reserved and the category named `ruling_kind` (A7); schema in T206, writer and round-trip tests in T210. |
| P6 | MAJOR | accepted | Confirmed: disposition and flow-line rulings write their own rows (common.sh ~389–427). T210 adds one shared emitter called from all three writers, tests all four ruling kinds and the refused or repeated claim. A11. |
| P7 | MAJOR | adjusted | Confirmed: three local finishes bypass the PR record and the final push follows it. T209 emits the end from `finish()` after publishing (one result per finish path) and from the terminal paths (`ai_die` in the pipeline or recovery shell, `escalate`, the unexpected-exit handler), once per process. Adjusted: a pipeline killed without handlers and stops after a gate change have no end (Non-goals); the run then shows as `open` or stale. |
| P8 | MAJOR | adjusted | Confirmed: the manifest outlives the run and the crash row uses the reconcile time. New T216: explicit `AI_RUN_ID` context, `run` on new outcome rows and attempt markers, crash rows take the marker's run. Adjusted: no fallback inference for historical rows; they go to `(no run record)` (A8, A13, T211), simpler than time windows and never wrong. |
| P9 | MAJOR | accepted | Confirmed: `test_session_gate_allowance_limit_grows_with_the_measured_gate` and `..._capped_by_the_remaining_run_time` seed 300 and 900 s gates with no override. T204 sets `AI_SESSION_GATE=full` there, adds the auto no-allowance assertion and runs `-k session_gate_allowance`. |
| P10 | MINOR | accepted | Confirmed: no test matches `run_parallel`, `gate_seconds`, `outcomes_report`, `ai_status` or `session_allowance` (and `run_manifest` only matches `timeout_rerun_manifest`). Every task's selectors replaced by verified groups (A19); new-test and existing-regression selectors listed separately. |
| P11 | MINOR | accepted | Confirmed: `templates/.ai/tasks.md` ~33 and `plan.md` ~13 ask only for generic validation commands. New T215 (task format, plan, plan-revision and triage prompts); the fallback for older queues is in the T204 contract text (A5, A18). |
