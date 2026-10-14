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
   Revision recovery (T011, plan review round 1 P1): an interrupted revision's uncommitted
   queue meets four queue checks before T002's post-session reorder (ai-pipeline ~416, ai-run
   ~138, `tasks untouched` ~338, `plan-dispositions-check` → `tasks()`). One guarded helper
   `revision-queue-repair` runs before all of them (ai-pipeline with plan review on; ai-run
   `--revise-plan`); it repairs only an uncommitted queue whose dirty files are plan revision
   records, whose HEAD queue is valid with no DONE task, for a verified, not-yet-revised plan
   review, and is a no-op otherwise, so committed-queue rejection (FL-18) and the no-DONE rule
   stay as they are.
2. **Timeouts (T003).** One rule in the harness: pipeline-running commands (`ai-pipeline`,
   `ai-recover`) get `PIPELINE_TIMEOUT`; named, scaled constants replace literal timeouts;
   `CI=true` defaults the scale to 2 (the workflow file itself is a gate file).
3. **Parallel runner (T004, opus: concurrent dispatch).** Work queue of interleaved small
   batches (`ids[k::batches]`, about 6 per worker) pulled by `AI_TEST_WORKERS` threads, each
   batch one `python3 -m unittest --durations 0` process (Python ≥ 3.12; older: no timing
   lines). The summary adds the 15 slowest tests, the sum of test time and per-worker busy
   time. The docs' "round-robin into shards" wording and its `DocsConsistencyTest` phrase change
   with it.
4. **Cheaper tests (T005, T006).** T005: harness I/O (git `core.fsync=none` for fixtures via
   `GIT_CONFIG_COUNT/KEY/VALUE`, test temp dirs under a fresh `/dev/shm` directory when it is
   a writable tmpfs with room AND a probe script executes there (fixtures exec mock agents and
   toolkit scripts from temp dirs; `noexec` → default temp dir), cleaned up). T006: profile-driven reductions of the slowest
   tests from T004's report (fixture reuse, fewer redundant processes), never fewer
   assertions or tests, never bytecode under `.ai/bin` (part of the gate digest).
5. **Dashboard (T007–T009).** DB-05 filter in `discover` (environ marker). DB-02 readers in
   `inspect` via the pinned fds (`reviews` dir opened no-follow from the `.ai` fd). DB-03: a
   `--wait` loop over `snapshot(all_runs=True)` comparing per-checkout keys
   `(status, stage, observation state, notifications_mark)`; the mark hashes the log's
   inode/size/mtime_ns and its raw last line (not the sanitised 300-character display text), so
   identical or same-prefix notifications are still distinct changes; the cursor is base64url
   JSON of those keys, so successive calls lose nothing.

## Phases / tasks
Priority order (the most valuable lands first if the night runs short):
T001 (reorder helper, sonnet) → T002 (wire into planning/revision after the session, opus;
flow chart) → T011 (repair before the queue checks on revision recovery, opus; sits right after
T002 in the file) → T003 (timeouts, sonnet) → T004 (runner timing and balancing, opus) → T005
(harness I/O, sonnet) → T006 (slowest tests, sonnet) → T007 (DB-05, opus: process discovery) →
T008 (DB-02, sonnet) → T009 (DB-03, sonnet) → T010 (docs/handoff audit, haiku).
Dependencies: T002 needs T001; T011 needs T002; T006 needs T004 (its timing report) and T005
(baseline after the I/O change); T010 needs all.
The handoff's "## Flow chart" line reads `Flow unchanged so far` from plan review round 1 on
(the gate's `test_pr_body_flow_this_repo_declares_the_flow_chart` needs it before the first
task); T002 switches it to `Flow chart updated`, T010 audits it. The rest are independent so one blocked item never stops the
others.

## Risks
- Existing tests that change on purpose: `test_plan_session_invalid_queue_stops_and_keeps_the_file`
  (its `plan-bad-queue` mock now writes a cycle, since an out-of-order queue is repaired), and
  run_parallel tests that assert the shard summary (T004 keeps the existing summary line;
  anything else is named in the result), and `DocsConsistencyTest.REQUIRED`'s shard phrase
  (T004).
- Reorder moves DONE blocks relative to TODO blocks when a TODO task before them depends on a
  later task; their text is unchanged and `plan-keeps-done` keeps passing (tested).
- `/dev/shm` may be small or `noexec` in containers: T005 uses it only with enough free space
  and a passing execution probe, else the default temp dir.
- Speed-up results on GitHub's runner cannot be measured offline; T004–T006 record local
  numbers, the CI time is a human check.
- `/proc/<pid>/environ` is the environment at exec time; a runner that changes its own
  environment later is judged by the original one. Processes of other users are unreadable
  → not ignored (as today).
- `--wait` polls (default 2 s): several notifications between two polls are reported as one
  change of that run (the run dict carries the last `EVENT_COUNT` events), never lost.

## Validation strategy
Each task: its targeted `-k` tests, then `.ai/bin/ai-check` (parallel; see the gate note in
`.ai/tasks.md`). All tests offline (mock agents, fixture `/proc` trees).

## Assumptions (unattended run; recorded instead of asked)
- Prose in `Dependencies:` is rejected, not rewritten (Zack's brief), unlike mission control's
  script.
- Reorder runs only on the planning/revision paths (incl. revision recovery, T011);
  ai-pipeline's own queue check (FL-18) still stops on an out-of-order committed queue.
- `CI=true` defaults `AI_TEST_TIMEOUT_SCALE` to 2; an explicit value always wins.
- The DB-02 counts are read, not verified (a dashboard must not need the host binding to
  draw); the reviewed HEAD is shown so a stale report is visible.
- DB-03 exit codes: 0 change, 1 timeout, 2 usage/cursor error; default `--timeout 3600`,
  `--interval 2`.
- The environ marker is `AI_DASHBOARD_IGNORE=1` (general, documented), not a temp-path rule
  (real worktrees may live under `/tmp`).
- Sessions may edit the vault flow chart and append a hub Log line; if the runner's
  permissions deny the vault path, the task records it and the handoff lists the change.
