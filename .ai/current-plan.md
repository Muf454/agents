# Plan: Flow batch 10: FL-39, TS-01 (1)(2), ME-01 parts 1 and 2

## Assessment (verified at 4fea72d, 2026-10-21; revised after plan review round 1)
Details and line references: `.ai/project-spec.md` "Verified against the code". In short:
- The plan review gate (`ai-pipeline` ~478) uses `tasks untouched` (no DONE task at all), so any
  queue that keeps earlier batches' DONE tasks skips the plan review silently. The supervised plan
  revision (`ai-run --revise-plan`, `revision-queue-repair`) has the same rule, so even a reviewed
  follow-up batch could not be revised (review P2). `tasks newly-done REV` already exists.
- The worker default is `min(8, cpu)`; on this 16-core host 14 workers is the expected best
  (mission control measures 8/12/14 before the run).
- Every runner session is told to run the ~13-minute full gate itself, and the host runs it again
  after the session. Last night's three timeouts (T108, T109, T111) were finished tasks that ran
  out of session time during their own gate. The FL-28 allowance (2 × gate) only partly covers it.
- The host already records task and review outcomes (`outcomes.jsonl`) and a bare `gate` row; it
  records nothing about stops, recovery decisions, rulings, routing reasons, PRs or run totals,
  and nothing ties a record to a run.
- CU-1 and CU-5 are already done in code (spec); OR-04 and BR-17 stay later.

## Design

### FL-39: plan review against the run's base (T201, T214)
- T201: `ai-pipeline` replaces `ai_helper tasks untouched` with a local `plan_untouched` check:
  the queue has tasks and `ai_helper tasks newly-done "$base_sha"` prints nothing (a helper error
  counts as "not untouched" and prints the skip line with the error, so a broken helper never
  runs a review on a started queue). Armed resume and `--skip-plan-review` keep skipping; every
  skip prints one `Plan review skipped: …` line (stdout, so it reaches the pipeline log). The
  loop's "already current and not revised" check stays. `tasks untouched` stays as a helper.
- T214: the same rule for the revision. `ai-run --revise-plan` checks `tasks newly-done
  "$plan_base"` (after `plan_base` is resolved) instead of `tasks untouched`, and runs
  `plan-keeps-done "$since"` after the session so earlier batches' DONE blocks stay
  byte-identical. `revision-queue-repair` takes an optional `--base REV` (both callers pass the
  run's base) and accepts a HEAD queue whose DONE tasks were all DONE at REV; without `--base` it
  keeps today's rule. One Python function `newly_done_ids(rev, blocks)` serves `tasks
  newly-done` and the repair.

### TS-01 (1): worker default (T202)
`worker_count()` returns `(count, source)`; default `max(1, min(14, (cpu or 1) - 2))` (or the
measured value in the handoff, A1); `main()` prints `Workers: …` first. Unit tests import the
module and patch `os.cpu_count` and the environment.

### TS-01 (2): session gate mode (T203, T204, T205, T215)
- T203 helper `workflow.py session-gate`: reads `AI_SESSION_GATE` (`auto|full|targeted`, empty =
  auto) and the recorded passes (shared function with `gate-seconds`, which keeps printing 0
  without any); prints `MODE SECONDS`; never fails (`targeted 0` on any error). The setting joins
  `RUN_SETTINGS`, the `ai_config` key list, both `ai-recover` lists and a validator in
  `scripts/lib/common.sh` next to the routing ones.
- T204 `ai-run`: `read -r gate_mode gate_secs < <(ai_helper session-gate)`; `claude_session`
  computes the allowance only in `full` mode; the RUNNER CONTRACT gets one of two gate sentences
  (A5, with the fallback for tasks without `Targeted:` lines) and the `Session:` line shows `gate
  rule targeted` or the current allowance breakdown. The existing `test_session_gate_allowance_*`
  tests that expect an allowance set `AI_SESSION_GATE=full` (review P9).
- T205 templates: `runner.md`, `triage.md`, `fix-review.md` say the gate rule comes from the
  RUNNER CONTRACT; `templates/CLAUDE.md` step 4 notes it.
- T215 task format (review P11): `templates/.ai/tasks.md`'s example Validation section shows
  `Targeted:` and `Gate:` lines; `plan.md`, `plan-revision.md` and `triage.md` ask for them; a
  test checks the four texts and the contract fallback agree.

### ME-01 part 1: event log (T206, T216, T217, T207–T210, T218)
- T206 core in `scripts/lib/workflow.py`: `events_path()`, `events_lock_path()` (stable
  `events.lock`), `EVENT_SCHEMA = 1`, `EVENT_ENVELOPE` (reserved names) and `EVENT_KINDS` (A7,
  ruling category in `ruling_kind`), `redact()`, `append_event(kind, fields)` (validates, adds the
  envelope with `run` from `AI_RUN_ID`, takes `events.lock` exclusively, then opens and appends to
  `events.jsonl` with the `append_outcome` newline guard, one write and fsync), `read_events()`
  (shared lock, archive then live, dedupe by id, skip unknown `v`/kind/non-dict), CLI `event KIND
  key=value…`. `common.sh`: `ai_event` whose first statement is the `AI_GATE_BROKEN` guard (A17).
- T216 run context (review P8): `run-manifest start` adds `run_id`/`started`, `run-manifest
  run-id`; `ai-pipeline` and `ai-recover` export `AI_RUN_ID` from the manifest (A8); `outcome`
  rows and attempt markers carry `run`; a reconciled `crashed` row takes the marker's run.
- T217 rotation (review P3, P4): inside the exclusive lock, A9's active-run retention, the
  quarter-cap rule and the copy-then-replace order; regression tests with two projects and with
  concurrent writers.
- T207 `gate`: `event-gate TASK_OR_STAGE START SECONDS RESULT` helper (parses the stamp's log,
  A12) called through a guarded `ai_gate_event` from `record_gate` in `ai-run`, `ensure_validated`
  in `ai-pipeline` and the `ai-recover` commit_and_rerun gate.
- T208 `stop` and `recovery`: `stop-category STAGE` helper (A10); guarded `ai_stop_event` and
  `ai_recovery_event` in `common.sh` compute the category and the last-error excerpt after the
  guard; `ai-pipeline stop()` after `ai_gate_check`; `ai-recover` at each decision and in
  `escalate()`.
- T209 `run` (review P7): `run start`/`resume` after the run context; guarded `ai_run_end RESULT`
  (no `AI_RUN_ID`, a broken gate, a subshell or `AI_RUN_ENDED` → nothing) computes totals with a
  `run-totals` helper from this run's own records and is called by `finish()` (each finish path
  passes its result) and by the terminal paths (`ai_die`'s pipeline branch, `escalate`, the
  recovery `on_exit`).
- T210 `ruling` and `review` (review P5, P6): one `ai_ruling_event KIND KEY TASK` emitter called
  right after each Ruling row in `ai_ruling_rows`, `ai_disposition_ruling` and
  `ai_flow_line_ruling`; `ai-review` emits `review`.
- T218 `pr`: after `gh pr create` and each successful draft/ready change.

### ME-01 part 2: metrics (T211, T212)
- T211 `workflow.py metrics [--since DATE] [--project NAME] [--json]` builds the data (A13) from
  `read_outcomes` + `read_events`, grouping by the `run` field only (no time windows; rows without
  it → `(no run record)`), into `{"v": 1, "projects": [...], "runs": [...]}`.
- T212 the plain-text tables (no `|` inside cells: Markdown-free aligned columns) and
  `ai-status --metrics …`.

### Docs (T213)
README and `docs/workflow.md` sections "Flow data (events.jsonl)" and "Reading the metrics";
vault flow chart and handoff audit. Flow-changing tasks (T201, T204, T208, T209) update the chart
themselves; T213 checks.

## Affected components
`scripts/ai-pipeline`, `scripts/ai-run`, `scripts/ai-recover`, `scripts/ai-review`,
`scripts/ai-status`, `scripts/lib/workflow.py`, `scripts/lib/common.sh`, `tests/run_parallel.py`,
`tests/test_workflow.py` (and a new `tests/test_events.py` for the event core, rotation and
metrics, to keep the huge file from growing), `templates/.ai/prompts/{runner,triage,fix-review,
plan,plan-revision}.md`, `templates/.ai/tasks.md`, `templates/CLAUDE.md`, README.md,
docs/workflow.md, vault `agents-flow.md` (+ hub Log lines).

## Phases and order (file order of `.ai/tasks.md`)
T201 (FL-39 pipeline, opus) → T214 (FL-39 revision, opus) → T202 (workers, sonnet) → T203
(session-gate helper and setting, opus) → T204 (ai-run contract and allowance, opus) → T205
(templates, sonnet) → T215 (Targeted lines, sonnet) → T206 (event core, opus) → T216 (run
context, opus) → T217 (rotation, opus) → T207 (gate events, sonnet) → T208 (stop and recovery
events, opus) → T209 (run start and end, opus) → T210 (ruling and review events, sonnet) → T218
(pr events, sonnet) → T211 (metrics data, sonnet) → T212 (metrics text and ai-status flag,
sonnet) → T213 (docs audit, haiku).
Eighteen tasks: each must fit about 10–15 minutes of a 30-minute session that also waits for the
~13-minute host gate; the review's additions became their own tasks instead of growing others.

## Risks
- Sessions that skip the full gate leave more failures for the host gate, which sets the task
  back to IN_PROGRESS; the next attempt gets the failure note (BR-03). Acceptable: the gate ran
  twice per task before.
- A fast-gate project whose gate slows down switches to `targeted` automatically (last 3 passes).
- An event write must never change a run: every writer is guarded and best effort with a `Note:`;
  tests assert an unwritable state dir leaves the run's exit status and output unchanged except
  the note.
- An event helper must never run after a detected gate change (A17): tested with the tampered
  `workflow.py` fixtures, which detect any helper run.
- Stop categories from text can be wrong; telemetry only, never read by recovery (A10).
- Rotation: concurrent writers and several active runs on one host (A9); covered by the
  multi-process and two-project regressions. Many long active runs can keep the file above the
  cap (documented).
- `run end` exactly once: a subshell `ai_die` or a second terminal path in the same process must
  not add another (`AI_RUN_ENDED`, `BASHPID` check, tested per finish path).
- FL-39: a helper failure must not trigger a review on a started queue (fails closed to skip with
  a line); a revision must not rewrite earlier DONE blocks (`plan-keeps-done`).
- This repo's own run still uses the frozen `.ai/bin` (FL-39 present: Zack runs the plan review
  by hand, see the handoff) and frozen prompts (BATCH 10 GATE RULE in the queue header).

## Validation strategy
Every task: its `Targeted:` commands (new-test selectors and verified existing-regression
selectors, spec A19; each must say `Ran N tests`, N ≥ 1) and `bash -n` on changed shell scripts,
in the session. The full gate is the host's post-task `ai-check` (BATCH 10 GATE RULE in the queue
header). No profiling commands.
