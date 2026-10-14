# Plan: Flow batch 3: FL-24, FL-23, DB-05, DB-02, DB-03

## Assessment (verified at 5894c2b, 2026-10-14)
All five backlog items are open; details and line references are in `.ai/project-spec.md` →
"Verified against the code". Only FL-23's CI job timeout (40 min) is already applied. Two
corrections to the backlog wording: FL-24's escalation comes from a revision-stage queue
failure that leaves no `last-error` (so recovery cannot classify it), and FL-23's reported
timeouts are partly a harness bug: `tool('ai-recover')` runs a whole resumed pipeline under the
25 s single-command timeout.

## Architecture
Small, local changes; no new runtime dependency, no new executable, no daemon.
1. **Queue reorder (T001, T002).** A pure helper `workflow.py tasks reorder` next to
   `tasks()`. It splits the file into preamble, task blocks (heading + every raw line, fences
   included, same fence rules as `task_blocks`) and trailer, validates the dependency lines
   itself (`tasks()` stops at the first out-of-order dependency, so it cannot be reused for
   that), and emits a depth-first order:
   ```mermaid
   flowchart LR
     S[session edits .ai/tasks.md] --> K[plan-keeps-done / revision scope]
     K --> R{tasks reorder}
     R -- cycle / unknown id / prose --> X[ai_die ... task queue is invalid → ⛔, recovery escalates at once]
     R -- ok: moved or unchanged --> C{tasks check}
     C -- invalid --> X
     C -- valid --> D[planned / revision commit]
   ```
   Depth-first (mission control's `reorder-queue.py`) rather than Kahn: it pulls a new
   prerequisite up to just before its first dependent and keeps earlier tasks early, which is
   what "insert new tasks before their first dependent" means; a valid queue is unchanged.
   Block text never changes, so `plan-keeps-done` (which compares blocks by ID, trailing blank
   lines ignored) still holds after a move.
2. **Timeouts (T003).** One rule in the harness: pipeline-running commands (`ai-pipeline`,
   `ai-recover`) get `PIPELINE_TIMEOUT`; named, scaled constants replace literal timeouts;
   `CI=true` defaults the scale to 2 (the workflow file itself is a gate file).
3. **Parallel runner (T004).** Work queue of interleaved small batches
   (`ids[k::batches]`, about 6 per worker) pulled by `AI_TEST_WORKERS` threads, each batch one
   `python3 -m unittest --durations 0` process (Python ≥ 3.12; older: no timing lines). The
   summary adds the 15 slowest tests, the sum of test time and per-worker busy time.
4. **Cheaper tests (T005, T006).** T005: harness I/O (git `core.fsync=none` for fixtures via
   `GIT_CONFIG_COUNT/KEY/VALUE`, test temp dirs under a fresh `/dev/shm` directory when it is
   a writable tmpfs with room, cleaned up). T006: profile-driven reductions of the slowest
   tests from T004's report (fixture reuse, fewer redundant processes), never fewer
   assertions or tests, never bytecode under `.ai/bin` (part of the gate digest).
5. **Dashboard (T007–T009).** DB-05 filter in `discover` (environ marker). DB-02 readers in
   `inspect` via the pinned fds (`reviews` dir opened no-follow from the `.ai` fd). DB-03: a
   `--wait` loop over `snapshot(all_runs=True)` comparing per-checkout keys
   `(status, stage, observation state, last event (ts, message))`; the cursor is base64url JSON
   of those keys, so successive calls lose nothing.

## Phases / tasks
Priority order (the most valuable lands first if the night runs short):
T001 (reorder helper, sonnet) → T002 (wire into planning/revision + recovery, opus; flow
chart) → T003 (timeouts, sonnet) → T004 (runner timing and balancing, sonnet) → T005 (harness
I/O, sonnet) → T006 (slowest tests, sonnet) → T007 (DB-05, opus: process discovery) → T008
(DB-02, sonnet) → T009 (DB-03, sonnet) → T010 (docs/handoff audit, haiku).
Dependencies: T002 needs T001; T006 needs T004 (its timing report) and T005 (baseline after the
I/O change); T010 needs all. The rest are independent so one blocked item never stops the
others.

## Risks
- Existing tests that change on purpose: `test_plan_session_invalid_queue_stops_and_keeps_the_file`
  (its `plan-bad-queue` mock now writes a cycle, since an out-of-order queue is repaired), and
  run_parallel tests that assert the shard summary (T004 keeps the existing summary line;
  anything else is named in the result).
- Reorder moves DONE blocks relative to TODO blocks when a TODO task before them depends on a
  later task; their text is unchanged and `plan-keeps-done` keeps passing (tested).
- `/dev/shm` may be small in containers: T005 uses it only with enough free space, else the
  default temp dir.
- Speed-up results on GitHub's runner cannot be measured offline; T004–T006 record local
  numbers, the CI time is a human check.
- `/proc/<pid>/environ` is the environment at exec time; a runner that changes its own
  environment later is judged by the original one. Processes of other users are unreadable
  → not ignored (as today).
- `--wait` polls (default 2 s); two identical notification lines in the same second count as
  one change.

## Validation strategy
Each task: its targeted `-k` tests, then `.ai/bin/ai-check` (parallel; see the gate note in
`.ai/tasks.md`). All tests offline (mock agents, fixture `/proc` trees).

## Assumptions (unattended run; recorded instead of asked)
- Prose in `Dependencies:` is rejected, not rewritten (Zack's brief), unlike mission control's
  script.
- Reorder runs only on the planning/revision paths; ai-pipeline's own queue check (FL-18) still
  stops on an out-of-order committed queue.
- `CI=true` defaults `AI_TEST_TIMEOUT_SCALE` to 2; an explicit value always wins.
- The DB-02 counts are read, not verified (a dashboard must not need the host binding to
  draw); the reviewed HEAD is shown so a stale report is visible.
- DB-03 exit codes: 0 change, 1 timeout, 2 usage/cursor error; default `--timeout 3600`,
  `--interval 2`.
- The environ marker is `AI_DASHBOARD_IGNORE=1` (general, documented), not a temp-path rule
  (real worktrees may live under `/tmp`).
- Sessions may edit the vault flow chart and append a hub Log line; if the runner's
  permissions deny the vault path, the task records it and the handoff lists the change.
