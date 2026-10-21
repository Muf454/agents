# Spec: Flow batch 10: faster gate (TS-01), flow events and metrics (ME-01), follow-up plan review (FL-39)

## Objective
Approved by Zack on 2026-10-21, planned 2026-10-21 in an unattended planning session on
`fix/flow-batch-10` (created from `fix/flow-batch-9` at 4fea72d; batch 9 is complete there apart
from T118's host verification and not merged; this PR targets `fix/flow-batch-9` until that
merges). Sources: vault `agents-backlog.md` TS-01, ME-01, FL-35 (called FL-39 in Zack's brief;
same defect), with FL-28, FL-23, BR-17, CU-1, CU-5 and OR-04 read for context.
1. **TS-01 (1) Worker count**: `tests/run_parallel.py` default raised from `min(8, cpu)` to
   `min(14, cpu - 2)` (at least 1) unless the handoff records another measured value;
   `AI_TEST_WORKERS` still overrides; the worker count and where it came from are printed in the
   gate output.
2. **TS-01 (2) Sessions run targeted tests; the host runs the full gate**: an implementation
   session runs its task's `Targeted:` checks and fast static checks, not `.ai/bin/ai-check`; the
   host gate after the session stays the authoritative full gate and decides DONE. Opt-in for the
   old behaviour: projects whose recorded gate is under 120 s, or `AI_SESSION_GATE=full`. The
   FL-28 session allowance follows the mode.
3. **ME-01 part 1, flow events**: one append-only, schema-versioned JSONL event log in the host
   state dir, written only by host scripts, with kinds `gate`, `stop`, `recovery`, `ruling`,
   `review`, `pr` and `run`; bounded with rotation that never loses the current run; readers
   tolerate unknown kinds.
4. **ME-01 part 2, reading it**: `ai-status --metrics [--since DATE] [--project NAME] [--json]`:
   per project and per run, tasks, first-pass rate, timeouts, median task and gate time, stops by
   category, review rounds and findings by reviewer; plain text and JSON.
5. **FL-39 (backlog FL-35) follow-up batches skip the plan review**: "untouched" is decided
   against the run's `--base`, and every skipped plan review prints one line saying why.
6. Docs: README, `docs/workflow.md` (where the data lives and how to read it), the vault flow
   chart, the handoff.

## Verified against the code (4fea72d, 2026-10-21)
- **Worker count**: `tests/run_parallel.py` `worker_count()` (~59–69): empty `AI_TEST_WORKERS` →
  `min(8, os.cpu_count() or 1)`; a non-positive or non-integer value exits with
  `run_parallel: AI_TEST_WORKERS must be a positive integer`. The worker count already appears in
  the last summary line (`Ran N tests in Xs (B batches on W workers, N collected)`, ~712) and in
  `Test time: … across W workers` (~606), but only at the end: a gate killed by its timeout prints
  neither. `.ai/validate` (gate file) runs the shell syntax checks then `python3
  tests/run_parallel.py`; nothing to change there. README and `docs/workflow.md` mention the
  `min(8, CPU count)` default.
- **Session gate rule**: the RUNNER CONTRACT is built in `scripts/ai-run` (~927–929) and says "A
  gate run that outlives a tool call is not a blocker: the full gate the runner runs after the
  session decides". The prompt templates `templates/.ai/prompts/runner.md` (~13–14 "run its
  targeted checks and `.ai/bin/ai-check`" and the "How to work here" bullet ~49–57 "Run the full
  gate as `.ai/bin/ai-check` with … `run_in_background: true`"), `triage.md` (same bullet ~55–63),
  `fix-review.md` (~12 "targeted tests, full gate") and `implement.md` (~8, interactive) tell
  sessions to run the full gate. `templates/CLAUDE.md` step 4 says the same.
- **FL-28 allowance**: `claude_session` (`scripts/ai-run` ~318–333): an implementation session
  (`track_attempt=yes`) gets `session_timeout + min(2 × gate-seconds, session_timeout)`;
  `gate-seconds` (`scripts/lib/workflow.py` ~4466) is the largest of the project's last 3 passing
  host gates from `outcome gate` rows. `session_timeout` defaults to 1800 (3600 in pipeline mode,
  ~114).
- **Host gates**: `ai-run` `host_gate` + `record_gate CODE STARTED` (~265–305) after a DONE
  session (~737), in the gate-only retry (~792) and the final gate (~884); `ai-pipeline`
  `ensure_validated` (~262–268, stage `validation`) and `ai-recover` commit_and_rerun (~303) call
  `ai-check` without recording anything. `ai-check` stores its log path in
  `.ai/local/validation.json` (`stamp record`, workflow.py ~870–883).
- **Outcome log**: `outcomes.jsonl` in `state_root()` (workflow.py ~3868), appended by
  `append_outcome` (~3957: flock, newline guard, single write, fsync) and never rotated. Kinds:
  `task`, `review` (with `route` since T110), `plan_revision`, `plan`, `catchup`, `gate`
  (`result`, `seconds` only). Attempt numbering (`attempt-info`, `next_attempt_seq`, crash
  reconcile) reads the whole file. `outcomes_report` (~4609) skips `gate` rows.
- **Stops and recovery**: `ai-pipeline` `stop()` (~173–189) reads `.ai/local/last-error`, records
  `ai_observe stop`, then either `exec ai-recover --stage STAGE` or notifies ⛔ and dies.
  `ai-recover` decides hard rules, limit relaunch, commit_and_rerun and the Claude decision;
  `escalate()` (~44–55) is the terminal stop. No structured stop category exists anywhere (OR-04
  is open).
- **Rulings** (BR-01): `ai_ruling_rows` / `ai_queue_ruling` / `ai_disposition_ruling` /
  `ai_flow_line_ruling` in `scripts/lib/common.sh` (~326 onwards) write `Ruling (KIND)` run-log
  rows and claim keys in the run manifest. **Review routing** (BR-14): `ai-review` asks
  `review-route` and logs the reason in the outcome `review` row (`--route`). **PR**: `ai-pipeline`
  `gh pr create` (~719), `gh pr ready`/`--undo` (~684–698), `chore(ai): record pull request` (~726).
- **Run identity**: `run-manifest start` (workflow.py ~1680) writes gate, branch, args, attempts,
  env; no run id and no start time. A recovery resume keeps the manifest.
- **Plan review skip (FL-39)**: `ai-pipeline` ~478 runs the plan review loop only when
  `plan_review == yes`, no armed resume and `ai_helper tasks untouched` (workflow.py ~753: fails
  when ANY task is DONE). This repo keeps earlier batches' DONE tasks, so batches 7–9 and
  mission-control phase 2 skipped the plan review with no output. `tasks newly-done REV`
  (~757–773) already lists tasks DONE now but not at REV. Within the loop an already-current,
  unrevised plan review is not repeated (`plan-review-info` ~496).
- **CU-1** (per-attempt model stats): already done; `outcomes_report` has "Attempts by model"
  (`attempts_table`, ~4643) attributing each attempt to its own model. Nothing to build.
- **CU-5** (crash-durable outcomes): attempt markers and `outcome attempt-reconcile` exist
  (workflow.py ~4330–4361); a SIGKILLed attempt is logged `crashed` at the next start. Nothing to
  build in this batch.
- **This repo's own run**: the frozen `.ai/bin/ai-pipeline` still has the FL-39 defect, and the
  frozen `.ai/prompts/runner.md` still tells sessions to run the full gate in the background.

## Scope
- T201: FL-39, plan review decided against `--base`, skip line.
- T202: worker default and the `Workers:` line.
- T203–T205: session gate mode helper and setting, `ai-run` contract and allowance, prompt
  templates.
- T206–T210: event log core, then the writers (gate; stop and recovery; run and pr; ruling and
  review).
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
  `targeted`. `auto` → `full` when the project's `gate-seconds` is between 1 and 119, otherwise
  `targeted` (no recorded gate → `targeted`: the host gate runs anyway and records the first
  time). Helper `workflow.py session-gate` prints `full SECONDS` or `targeted SECONDS`; any
  error → `targeted 0`. Validated in `ai-run` and `ai-pipeline`, kept in the run manifest and the
  `ai-recover` setting lists like `AI_REVIEW_ROUTE`.
- **A4 Allowance**: `full` keeps today's allowance (`min(2 × gate, session_timeout)`); `targeted`
  gets none (the session no longer runs the gate). The `Session:` line names the mode.
- **A5 Contract text**: `targeted`: "Run the task's `Targeted:` checks in the foreground and the
  fast static checks it names; do not run `.ai/bin/ai-check`: the runner's full gate after the
  session is authoritative and decides DONE; a DONE task whose gate fails returns to IN_PROGRESS."
  `full`: today's wording plus "run `.ai/bin/ai-check` with run_in_background". The templates say
  "follow the RUNNER CONTRACT's gate rule" instead of fixing one rule. Interactive `implement.md`
  keeps the full gate (no runner, no session cap). The gate-only retry is unchanged.
- **A6 Event file**: a new `events.jsonl` beside `outcomes.jsonl`, not new kinds in
  `outcomes.jsonl`. Why: `outcomes.jsonl` must never rotate (attempt numbering, `first_pass` and
  crash reconcile read all of it), and old installed copies read it with fixed kind filters;
  events need rotation and a schema version. The existing `outcome gate` row stays (it feeds
  `gate-seconds`); the `gate` event is written next to it.
- **A7 Event record**: one JSON object per line, `{"v": 1, "id": 16 hex, "time": ISO UTC,
  "kind", "project", "branch", "run": run id or null, …kind fields}`; written with the same
  locked single-write append as outcomes. Strings are capped (message excerpts ≤ 200 characters,
  one line, secrets redacted by a new `redact()` with a fixed token pattern list: no text
  redaction helper exists today; `SECRET_PATTERNS` (~1039) is about file names). A
  write failure prints one `Note:` line and never changes the caller's exit status or flow.
- **A8 Run id**: `run-manifest start` adds `run_id` (16 hex) and `started` (epoch); a resume
  keeps both; `run-manifest run-id` prints it. Events outside a pipeline (standalone `ai-run`)
  have `run: null`.
- **A9 Rotation**: when `events.jsonl` exceeds `AI_EVENTS_MAX_BYTES` (default 8 MiB, validated
  int ≥ 65536) before an append, under the same lock it is renamed to `events.1.jsonl` (replacing
  the older one) and the new file starts with every line of the writing event's run copied from
  the old file. A run larger than the cap is kept whole. Readers read `events.1.jsonl` then
  `events.jsonl` and drop duplicate ids.
- **A10 Stop categories** (fixed list): `timeout`, `validation_failed`, `record_format`,
  `queue_order`, `review_round_limit`, `usage_limit`, `needs_human`, `crash`, `other`; derived by
  `workflow.py stop-category STAGE` from the stage and the host's last-error text (first match in
  a fixed table). Telemetry only; recovery never reads it (OR-04 stays open).
- **A11 Event points**: `stop` at `ai-pipeline stop()` (before handing over or dying) and at
  `ai-recover escalate`; `recovery` for each `ai-recover` decision (`rerun`, `commit_and_rerun`,
  `relaunch`, `escalate`, with task and attempt); `run` `start` at a human start and `resume` at a
  recovery start, `end` at the PR record (`result: pr`) or a terminal stop (`result: stopped`) with
  totals (tasks newly DONE since base, gates, gate failures, seconds since `started`); `pr` after
  `gh pr create` and each draft/ready change (`state: draft|ready`, url); `ruling` in
  `ai_ruling_rows` (kind, key, task); `review` in `ai-review` (mode, reviewer, route reason).
- **A12 Gate event fields**: `project`, `branch`, `task` or `stage`, `start` (epoch), `seconds`,
  `tests`, `failures`, `workers`, `result` (`pass|fail|timeout`); tests, failures and workers are
  parsed from the gate log named by `.ai/local/validation.json` (regular file, last 256 KiB,
  integers only: `Ran N tests`, `FAILED (failures=a, errors=b)`, `Workers: W`, `on W workers`);
  unknown → null.
- **A13 Metrics**: from `outcomes.jsonl` (task and review rows) and the event log. Per run = rows
  of the same project and branch between that run's `run start` and `run end` (or now); rows with
  no run → a `(no run record)` group. First-pass rate = tasks whose first attempt was `done` ÷
  tasks. Timeouts = task attempts with `result == timeout`. Median task time per task (sum of its
  attempts), median gate time from `gate` events (fallback `outcome gate` rows). Review rounds =
  code review rows (not re-checks) per run; findings by reviewer = BLOCKER/MAJOR/MINOR sums.
  `--since YYYY-MM-DD` (UTC, inclusive), `--project NAME`; `--json` prints one object
  `{"v": 1, "projects": […], "runs": […]}`.
- **A14 FL-39**: "untouched" = `tasks newly-done "$base_sha"` prints nothing (and the queue has
  tasks). An armed resume still skips (as today). An already-current, unrevised plan review is
  not repeated (as today, inside the loop). "New tasks already started" = a task newly DONE since
  base; IN_PROGRESS/BLOCKED do not lift the review (as today). Skip line:
  `Plan review skipped: <why>` for `--skip-plan-review`, an armed resume, or tasks newly DONE since
  base (first three ids).
- **A15 T118**: T118 (batch 9, review N3) is TODO here because both branches are at 4fea72d; its
  fix (38f671c) is committed and awaits host verification on `fix/flow-batch-9`. Its block stays
  unchanged. Zack merges `fix/flow-batch-9` into this branch after T118 is DONE there, before
  approving; otherwise this run's first session verifies T118 (harmless, same fix).
- **A16 This run's gate rule**: the frozen `.ai/prompts` still say "run the full gate in the
  background"; the queue header's BATCH 10 GATE RULE overrides it for this batch: sessions run
  only targeted checks and `bash -n`, the host gate decides.

## Acceptance criteria (observable)
- `AI_TEST_WORKERS` unset on a 16-CPU host → `Workers: 14 (default, CPU count 16)`; set to 3 →
  `Workers: 3 (AI_TEST_WORKERS)`; `0`/`x` → the existing error.
- A pipeline task session on a project whose gate takes 800 s gets a contract without
  "`.ai/bin/ai-check`" as an instruction to run, and no gate allowance; one on a 60 s gate (or
  `AI_SESSION_GATE=full`) gets today's behaviour. The templates carry no fixed full-gate rule for
  runner sessions.
- After a pipeline run, `events.jsonl` holds `run`, `gate`, `pr` (and on failure `stop`,
  `recovery`) events with `v: 1`; a rotation keeps all lines of the current run; unknown kinds and
  versions are skipped by readers.
- `ai-status --metrics` prints per-project and per-run tables; `--json` is valid JSON with the same
  numbers; `--since` and `--project` filter.
- A queue with earlier DONE tasks and new TODO tasks gets a plan review; a resumed run whose new
  tasks already have one DONE since base does not, and prints `Plan review skipped: …`.
- `.ai/bin/ai-check` passes on the final tree; README and `docs/workflow.md` describe the event
  log, its location, rotation and `--metrics`; the vault flow chart shows the new session gate rule
  and the plan review decision.
