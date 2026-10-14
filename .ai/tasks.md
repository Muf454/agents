# Task queue

Edit `scripts/`, `templates/`, `tests/`, `README.md` and `docs/` only (plus the vault flow chart
and hub Log line where a task says so). Never edit `.ai/bin`, `.ai/prompts`, `.ai/validate`,
`.ai/ci-setup`, `.ai/permissions.allow`, `.claude/settings.json` or `.github/workflows/*`
(gate files; needed gate changes are human steps in `.ai/handoff.md`). Vault: a task that
changes the flow updates `~/zWiki/zWiki/20 Projects/agents/agents-flow.md` and its `updated:`
date in the same task and appends a dated line to the Log of `agents.md`; never tick vault
checkboxes. If the vault edit is denied, record it in the result and in the handoff's
"## Flow chart" section.
Source: vault `agents-backlog.md`, "Dashboard follow-ups for mission control" (FL-24, FL-23,
DB-05, DB-02, DB-03), planned 2026-10-14. Line references are at 5894c2b and verified by the
planner; re-check them before editing.
Every behaviour change gets an offline regression test in the existing style; every task
leaves `.ai/bin/ai-check` passing and updates README.md / `docs/workflow.md` where the
behaviour it changes is described.
Gate note: `.ai/validate` runs the shell syntax checks and then `tests/run_parallel.py`
(about 4–6 min), inside the 600 s Bash tool limit. Should `.ai/bin/ai-check` still time out in
the session, run the task's targeted tests, record the timeout in the result, and leave the
full gate to the host's post-task `ai-check`. Tests with time bounds run in parallel: assert
"returns within N s" with generous, scaled bounds, never a tight duration.
No new executable file in this batch (this run's allowlist cannot `chmod +x`).

## T001 — `tasks reorder`: stable dependency order for the task queue (FL-24, part 1)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
A read-and-rewrite helper that repairs a queue whose tasks depend on later tasks, without
changing any task's text, and rejects what it cannot repair with a clear message.

### Implementation notes
- `scripts/lib/workflow.py`, next to `tasks()` (~425): `tasks_reorder()`, dispatched as
  `tasks reorder` from `task_command` (~465) BEFORE `tasks()` is called there (today
  `task_command` calls `tasks()` first, which fails on exactly the queues this repairs: branch
  on `arguments[0] == 'reorder'` at the top).
- Split `.ai/tasks.md` into preamble lines (before the first task heading), task blocks
  (heading line + every following line up to the next `## ` heading outside a fence, fenced
  lines included) and trailer (from the first non-task `## ` heading after the last task).
  Use the same heading and fence rules as `task_blocks` (~390; factor a shared line
  classifier if that keeps one rule; `task_blocks` output must stay identical). A non-task
  `## ` section between two tasks: fail only if a move is needed
  (`cannot reorder: section "<heading>" sits between tasks`).
- Validation (fail with `Error: …` via `fail`, file untouched): `Duplicate task IDs.`; a task
  without exactly one line starting `Dependencies:` (`T00x: expected exactly one Dependencies:
  line`); a value that is not `none` and not `T\d{3,}` IDs separated by commas with optional
  spaces (`T00x: Dependencies: must be "none" or task IDs separated by commas, found "<value>"`);
  an ID not in the queue (`T00x: dependency T0yy is not a task in the queue`); a duplicate in
  one line (`T00x: duplicate dependencies`); a self-dependency or cycle
  (`dependency cycle: T003 -> T005 -> T003`, the path in visit order).
- Order: for each task in file order, visit(task): visit its dependencies in the order they
  appear in the FILE (not the line), then emit the task (mission control's
  `~/Projects/wt/plans/sessions/reorder-queue.py` minus the prose rewriting). A valid queue
  yields the same order: then nothing is written (bytes and mtime unchanged), exit 0, no
  output.
- On a move: rebuild preamble + blocks in the new order + trailer; every block's lines are
  byte-identical; when a block that now has a successor ends without a blank line, append one
  blank line (the only whitespace change; `plan-keeps-done` ignores trailing blank lines).
  Write atomically (temp file in `.ai/`, `os.replace`, keep the file mode; reuse an existing
  atomic-write helper in workflow.py if there is one). Print
  `Task queue reordered (dependencies first): T001 T011 T002 …` (the new ID order) to stdout.
- `scripts/ai-task`: `reorder` subcommand → `ai_helper tasks reorder`; usage line updated
  (`set | show | check | reorder`). It writes the queue, so take the same lock `set` takes if
  `set` takes one (check ~5–20); `check` stays read-only.
- README (manual task commands) and `docs/workflow.md` (task queue rules): one line each. No
  flow change yet (T002 wires it in).

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-task, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_queue_reorder_*` in tests/test_workflow.py (helper through
  `workflow.py tasks reorder` in a fixture checkout, plus one through `ai-task reorder`):
  - the night's case: T001 depends on T011 (appended last), T005 on T014: after the reorder
    `tasks check` passes, the order is exactly the depth-first order (T011 right before T001,
    T014 right before T005, everything else in file order), every block's text equal to its
    original (compare per-ID raw text, trailing blank lines stripped), preamble and trailer
    sections unchanged;
  - a valid queue: exit 0, no output, file bytes and `st_mtime_ns` unchanged;
  - a DONE task between moved tasks keeps its text, and `plan-keeps-done <commit of the
    original queue>` passes on the reordered file;
  - fenced lines that look like `## T009 — …` inside a task are not headings and move with
    their block;
  - rejected, file byte-identical, exit 1, message as in the notes: cycle (T001→T002→T001 and a
    self-dependency), unknown ID, prose (`Dependencies: T002 (after the API lands)`, `T002 and
    T003`), two `Dependencies:` lines, duplicate IDs, a non-task section between tasks that
    must move;
  - `ai-task reorder` on the night's case prints `Task queue reordered` and the new order.
- All existing tests pass unchanged (`task_blocks` output identical).

### Validation
Targeted: `python3 -m unittest discover -s tests -k queue_reorder` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k queue_check` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE. `tasks_reorder()` + `queue_segments()` in scripts/lib/workflow.py, dispatched before `tasks()`;
`ai-task reorder`; README and docs/workflow.md lines. `test_queue_reorder_*` (5 tests) and
`test_queue_check_*` (7) pass; `.ai/bin/ai-check`: 624 tests OK. `task_blocks` untouched (its
rules are mirrored in `queue_segments`, not shared). `ai-task reorder` takes no lock (`set` takes none).


## T002 — The host repairs the queue after planning and plan revision; an unrepairable queue escalates at once (FL-24, part 2)
Status: DONE
Dependencies: T001
Model: opus

### Goal
A plan revision (or headless planning session) that appends a prerequisite after its
dependents no longer stops the run; a queue the host cannot repair stops once, with the queue
error, and recovery escalates without rerunning.

### Implementation notes
- `scripts/ai-run` `--revise-plan` branch: replace the bare `ai_helper tasks check` (~418,
  after the plan.md digest check) with
  `reorder_out=$(ai_helper tasks reorder 2>&1) || ai_die "Plan revision stage: task queue is
  invalid: ${reorder_out#Error: }"`, print `$reorder_out` when non-empty, then
  `queue_error=$(ai_helper tasks check 2>&1 >/dev/null) || ai_die "Plan revision stage: task
  queue is invalid: ${queue_error#Error: }"`. It sits after the `if/else` (~366–415) and
  repairs what the session just wrote. It does NOT cover an interrupted revision: an
  uncommitted out-of-order queue is rejected long before this line (ai-pipeline:416, ai-run:138,
  `tasks untouched` at ai-run:338, `plan-dispositions-check` → `tasks()` at workflow.py:2426);
  that recovery path is T011. The following `revision_scope` already allows `.ai/tasks.md`; check that the host revision
  commit stages `.ai/tasks.md` (the reordered file must be in it) and fix it if not.
- `scripts/ai-run` `--plan` branch: after `plan-keeps-done "$since" --baseline …` (~320) and
  before `tasks check` (~322): the same reorder with `ai_die "Planning: task queue is invalid:
  …"`.
- Revision contract text (~394–395): "append new TODO tasks with new IDs to .ai/tasks.md" →
  "add new TODO tasks with new IDs to .ai/tasks.md, placed before the first task that depends
  on them (the host reorders the queue into dependency order and rejects cycles, unknown IDs
  and prose in Dependencies:)". PLANNING CONTRACT (~301–303): the same sentence about the host
  reorder. Templates `templates/.ai/prompts/plan.md` and `plan-revision.md`: one sentence each
  if they describe dependency order (never `.ai/prompts`).
- `scripts/ai-recover` needs no change: `Plan revision stage` is already in the always-escalate
  list (~138). Verify with the test below; if the pipeline's `stop 'plan revision'` path
  rewrites the reason, fix it so `last-error` keeps the ai-run message.
- Tests: mock claude (tests/test_workflow.py ~127–218): revision mode `revise-accept-prereq`
  (like `revise-accept`, then sets the FIRST task's `Dependencies:` to the new ID) and
  `revise-accept-cycle` (the new task depends on T001 and T001 on the new task); planning mode
  `plan-out-of-order` (T001 depends on T002, the previous `plan-bad-queue` queue) and change
  `plan-bad-queue` to a cycle (T001↔T002). Update
  `test_plan_session_invalid_queue_stops_and_keeps_the_file` (~2814–2819) to the cycle message
  (`dependency cycle`) and name it in the result; its other assertions stay.
- Docs: README (plan revision / planning paragraphs) and `docs/workflow.md` (plan stage, plan
  revision, recovery hard rules): the host reorder and the immediate escalation.
- Vault (flow change): `agents-flow.md`: the Plan box and the revision path ("Scripts: commit +
  host record") gain "host reorders the queue (dependencies first); cycle / unknown ID / prose →
  ⛔"; the recovery hard-rules box notes "queue invalid after a revision"; bump `updated:`.
  Hub `agents.md` Log: one dated line.
- `.ai/handoff.md` "## Flow chart": replace the first line `Flow unchanged so far …` with
  `Flow chart updated: …` (what T002 changed), keep the pending T011 note below it (or
  `Flow chart updated` plus a PENDING line if the vault edit was denied).
  `test_pr_body_flow_this_repo_declares_the_flow_chart` must keep passing.

### Likely affected modules
scripts/ai-run, templates/.ai/prompts/plan.md, templates/.ai/prompts/plan-revision.md,
tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md and agents.md (Log)

### Acceptance criteria
- Tests named `test_queue_repair_*` in tests/test_workflow.py:
  - supervised pipeline (fixture as the existing supervised plan revision tests,
    `MOCK_CODEX_PLAN='major-once'`, `MOCK_CLAUDE='revise-accept-prereq'`): exit 0, no stop,
    `recover-calls` absent, one revision session; the committed `.ai/tasks.md` after the
    revision commit lists the new task before T001; `Task queue reordered` in the output; all
    tasks DONE at the end;
  - same with `revise-accept-cycle` and `AI_AUTO_RECOVER=1`: exit 1, `last-error` contains
    `Plan revision stage: task queue is invalid` and `dependency cycle`, exactly one ⛔
    notification, `recover-calls` absent (no Claude recovery decision), exactly one revision
    session (no rerun), no implementation session;
  - `ai-run --plan` with `plan-out-of-order`: exit 0, `planned` record, T002 before T001 in the
    working tree, nothing committed; with the cycle `plan-bad-queue`: exit 1, `Planning: task
    queue is invalid`, `dependency cycle`, file left as written, one ⛔;
  - `ai-run --plan --revision` on a queue with DONE T001 whose session appends T003 and makes
    TODO T002 depend on it: exit 0, T001's block unchanged (plan-keeps-done passed);
  - `ai-pipeline --approved` on a COMMITTED out-of-order queue still stops with `Task queue is
    invalid` (FL-18 unchanged; `test_queue_check_*` pass unchanged);
  - the revision prompt contains `placed before the first task that depends on them`.
- `test_plan_session_invalid_queue_stops_and_keeps_the_file` updated as in the notes; all other
  existing tests pass unchanged.
- The vault flow chart and hub Log are updated (or the denial is recorded); the handoff's
  "## Flow chart" first line reads `Flow chart updated`.

### Validation
Targeted: `python3 -m unittest discover -s tests -k queue_repair` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k plan_session` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k supervised_plan` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE. `scripts/ai-run`: `tasks reorder` (output printed, failure → `Planning: task queue is
invalid: …` / `Plan revision stage: task queue is invalid: …`) before `tasks check` on the
`--plan` and `--revise-plan` paths; the revision commit already stages `.ai/tasks.md`. Planning
and revision contracts plus templates `plan.md`/`plan-revision.md` describe the host reorder.
ai-recover and the pipeline's `stop 'plan revision'` needed no change (last-error keeps the
ai-run message). Mock modes `revise-accept-prereq`, `revise-accept-cycle`, `plan-out-of-order`,
`plan-revision-prereq`; `plan-bad-queue` is now a T001↔T002 cycle and
`test_plan_session_invalid_queue_stops_and_keeps_the_file` asserts `dependency cycle`. 7
`test_queue_repair_*` tests pass; `plan_session`/`supervised_plan`/`flow_this_repo`/`queue_check`/
`revise_plan` (67) pass; `.ai/bin/ai-check`: 631 tests OK. README, docs/workflow.md, vault
flow chart and hub Log updated.


## T011 — Revision recovery repairs the interrupted revision's queue before any queue check (FL-24, part 3)
Status: TODO
Dependencies: T002
Model: opus

### Goal
A plan revision that crashed after its session wrote an out-of-order (repairable) queue resumes
through `ai-recover` or a human rerun without a second revision session, while every committed
or non-revision queue keeps today's rejections.

### Implementation notes
- Why: an uncommitted out-of-order queue is rejected before T002's post-session reorder is
  reached: `ai-pipeline` ~416 (`tasks check` → `Task queue is invalid` → `stop`, ai-recover
  escalates at ~139), ai-run ~138 (`tasks check` for every non-plan mode), ai-run ~338
  (`tasks untouched` calls `tasks()` and dies with the misleading "a task is already DONE"),
  and the "dispositions complete" test at ~366 (`plan-dispositions-check` → `tasks()` at
  workflow.py ~2426 fails, so the run falls into the dirty-records rejection at ~371–376).
- One helper decides, in `scripts/lib/workflow.py`: `revision-queue-repair` (no arguments).
  It reorders (T001's `tasks_reorder`, same messages) ONLY when all of these hold, else it
  does nothing and exits 0 (the existing checks then reject as today):
  1. `.ai/tasks.md` differs from HEAD's (uncommitted change);
  2. `plan-revision-scope HEAD` passes (only plan revision records dirty, untracked included);
  3. HEAD's queue parses with `tasks()` rules (committed queue valid) and has no DONE task;
  4. the current plan review is verified (`verified_plan_review`) and `plan-revisions revised`
     says not yet revised (an interrupted revision of THIS report).
  A repair failure (cycle, unknown ID, prose) exits 1 with the T001 message. Prints T001's
  `Task queue reordered …` line on a move.
- Callers (before any queue check, after the gate/branch checks already there):
  - `scripts/ai-pipeline` right before ~415–419, only when `plan_review == yes`:
    `repair_out=$(ai_helper revision-queue-repair 2>&1) || { printf 'Plan revision stage: task
    queue is invalid: %s\n' "${repair_out#Error: }" > .ai/local/last-error; stop 'plan
    revision'; }`, print `$repair_out` when non-empty. (`Plan revision stage` is always-escalate
    in ai-recover ~138.)
  - `scripts/ai-run` before ~138 when `revise_plan == yes`: the same helper with
    `ai_die "Plan revision stage: task queue is invalid: …"`. Then ~138, ~338 and ~366 see the
    repaired queue and the "dispositions already complete" path records the revision without a
    new session; the host revision commit stages `.ai/tasks.md` (T002 checked that).
- Unchanged: the no-DONE rule (condition 3 plus `tasks untouched` ~338), `tasks check` on
  every path, ai-pipeline's rejection of a COMMITTED out-of-order queue (FL-18), implementation
  and review paths (no repair).
- Docs: README and `docs/workflow.md` (plan revision recovery: the host repairs an interrupted
  revision's queue first); vault `agents-flow.md` recovery box gains "interrupted revision: host
  repairs the queue first", `updated:` bumped, hub Log line; handoff "## Flow chart" keeps
  `Flow chart updated` and drops the T011 pending note.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-pipeline, scripts/ai-run, tests/test_workflow.py, README.md,
docs/workflow.md, vault agents-flow.md and agents.md (Log)

### Acceptance criteria
- Tests named `test_queue_recovery_*` in tests/test_workflow.py:
  - crash after the session (as `test_supervised_plan_resume_session_crash_*`, with
    `MOCK_REVISION_CRASH='after'` and `MOCK_CLAUDE='revise-accept-prereq'`), resumed by
    `ai-recover` (watchdog path) and by a human rerun: `assert_resumed_once()` holds (one
    revision record, exactly one revision session, re-review clean, all tasks DONE), the
    committed queue lists the new task before T001, `recovery_calls()` empty;
  - the same crash with `revise-accept-cycle`: exit 1, `last-error` contains `Plan revision
    stage: task queue is invalid` and `dependency cycle`, one ⛔, no second revision session,
    `recover-calls` absent;
  - helper unit cases (no-op, exit 0, file untouched): queue committed out of order (FL-18
    rejection still comes from ai-pipeline: `test_queue_check_*` unchanged), a dirty file outside
    the plan records, a DONE task in HEAD's queue, the current review already revised;
  - `ai-run --revise-plan` with a committed DONE task still dies with `a task is already DONE`.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k queue_recovery` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k supervised_plan_resume` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k queue_check` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T003 — Test timeouts: pipeline commands get the pipeline timeout, every bound is scaled (FL-23, part 1)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
No test fails on a slow runner because a whole pipeline ran under a single-command timeout or
a literal bound that `AI_TEST_TIMEOUT_SCALE` cannot stretch; a timeout shows what the command
was doing.

### Implementation notes
- tests/test_workflow.py `tool()` (~1290–1294): `PIPELINE_TIMEOUT` for `ai-pipeline` AND
  `ai-recover` (comment: ai-recover execs the resumed pipeline in the same process; PR #27 run
  38356827946 timed out at 25 s in `test_supervised_plan_resume_*_watchdog`). Search for other
  calls that run a pipeline under `COMMAND_TIMEOUT` (`run_cmd([... 'ai-recover' ...])`,
  `host_watchdog('--recover', …)` when its mock `systemd-run` executes the recovery, `ai-run`
  with many sessions) and give them `PIPELINE_TIMEOUT`.
- Replace every literal `timeout=<number>` / `communicate(timeout=<number>)` and literal
  "within N s" bounds in tests/test_workflow.py, tests/test_dashboard.py and
  tests/test_observation.py with named constants multiplied by the scale (e.g.
  `SHORT_TIMEOUT = 10 * TIMEOUT_SCALE`); known sites ~747, ~749, ~1272, ~3437, ~3940, ~4865,
  ~5417, ~5504, ~5509, ~8173 (re-grep). Sleeps inside mock processes (`sleep 30` owners,
  `sleep 120` runners) are not timeouts; leave them.
- Scale rule, identical in the three test modules (one small helper per module or a shared
  `tests/timeouts.py` imported by them): `AI_TEST_TIMEOUT_SCALE` when set (float > 0, else a
  clear error), else `2` when `CI` is `true`, else `1`. Comment why (GitHub's runners are
  several times slower than a workstation; the workflow file is a gate file).
- `run_cmd` (~621): catch `subprocess.TimeoutExpired` and fail with the command, the timeout
  and the captured partial stdout/stderr (last ~3000 characters each) instead of the bare
  traceback.
- README (self-check / tests section) and `docs/workflow.md` if it describes the test
  timeouts: `AI_TEST_TIMEOUT_SCALE` and the `CI` default. Flow unchanged.

### Likely affected modules
tests/test_workflow.py, tests/test_dashboard.py, tests/test_observation.py, README.md

### Acceptance criteria
- Tests named `test_test_harness_timeouts_*` in tests/test_workflow.py:
  - `tool('ai-recover', …)` and `tool('ai-pipeline', …)` use `PIPELINE_TIMEOUT` (call the
    timeout choice through a small function, e.g. `command_timeout(name)`, and assert it);
  - the scale rule: a subprocess importing the test module (or the shared helper) with
    `CI=true` and no `AI_TEST_TIMEOUT_SCALE` gets 2, with `AI_TEST_TIMEOUT_SCALE=3` gets 3,
    with neither gets 1, with `AI_TEST_TIMEOUT_SCALE=0` or `x` fails with a message;
  - a source scan of the three test modules finds no `timeout=` followed by a bare number;
  - a timed-out `run_cmd` (`bash -c 'echo started; sleep 30'`, timeout 1 s) fails with an
    assertion message containing `started` and the timeout.
- All existing tests pass unchanged apart from the timeout constants.

### Validation
Targeted: `python3 -m unittest discover -s tests -k test_harness_timeouts` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k supervised_plan_resume` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T004 — Parallel runner: per-test timings and balanced batches (FL-23, part 2)
Status: TODO
Dependencies: none
Model: opus

### Goal
Every gate run shows where the time goes, and no worker sits idle while another works through
a cluster of slow tests.

### Implementation notes
- `tests/run_parallel.py`: keep discovery, the import-error path, the count check and the
  failure output. Replace the fixed shards (~101–104) by a work queue: `batches =
  [ids[k::n] for k in range(n)]` with `n = min(len(ids), workers * 6)` (interleaved, so
  similarly named slow tests spread out), pulled by `workers` threads; each batch is one
  `python3 -m unittest` process as today.
- Timings: on Python ≥ 3.12 run batches with `--durations 0` and parse the "Slowest test
  durations" lines (`<seconds>s <test name> (<id>)`; tolerate format drift: unparsable lines
  are ignored); older Pythons: no timing. Print after the run: the 15 slowest tests with
  seconds, `Test time: <sum> s across <workers> workers; worker busy: <min>–<max> s`. Keep the
  existing final line `Ran N tests in Xs (…)` and `OK`/`FAILED (…)` (existing tests parse
  them; if the parenthesised part must change from `shards` to `batches`, update those tests
  and name them in the result).
- Failure output names the failing batch's test IDs (not a shard number only).
- `AI_TEST_WORKERS` unchanged (default `min(8, CPUs)`); document `AI_TEST_BATCHES` only if
  you add it (optional).
- Record a baseline in the result: the gate's `Ran … in …`, the test-time sum and the 15
  slowest tests on this machine (with its CPU count). T005/T006 compare against it.
- README (self-check section): one paragraph on the timing report. Flow unchanged.
- The shard description changes with the architecture: README ~813, `docs/workflow.md` ~49
  and the module docstring of `tests/run_parallel.py` (~5) say "round-robin into
  `AI_TEST_WORKERS` shards"; rewrite all three to the batch queue (e.g. "interleaved batches
  pulled by `AI_TEST_WORKERS` workers") and change the matching `DocsConsistencyTest.REQUIRED`
  phrase (tests/test_workflow.py ~8291) to the new wording, present in both docs. This is an
  intentional test change: name it in the result.
- Model opus: the dispatcher is concurrent (worker threads pulling a shared queue, results and
  timings collected across threads, interrupt/cleanup of running children): use a
  `queue.Queue` or a lock for shared state, join every thread, and on KeyboardInterrupt or a
  worker exception terminate the running batch processes before exiting.

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py (its run_parallel tests, ~8153, and
`DocsConsistencyTest.REQUIRED` ~8291), README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_parallel_runner_*` (next to the existing run_parallel tests, which use a
  generated suite in a temp dir and `AI_TEST_WORKERS=2`):
  - a generated suite with 3 tests that sleep 0.3 s and 9 fast ones: exit 0, `Ran 12 tests`,
    the slowest list starts with the three sleepers (on Python ≥ 3.12; skip that assertion
    with a reason on older Pythons), `Test time:` present;
  - with 2 workers and a suite of 4 tests sleeping 1 s that sort next to each other, wall time
    is under 3.5 s × scale (the old round-robin would also pass; the point is that batches are
    interleaved: assert the batches from a helper, e.g. `make_batches(ids, workers)`, never put
    two adjacent sorted IDs in the same batch when there are more batches than 1);
  - a failing test: exit 1, its ID in the output; a count mismatch still fails;
  - an import error in a module still fails at discovery.
- Existing run_parallel tests pass (any updated summary assertion named in the result).
- No document says "round-robin into `AI_TEST_WORKERS` shards" any more; `DocsConsistencyTest`
  passes with the new phrase (the changed REQUIRED entry named in the result).

### Validation
Targeted: `python3 -m unittest discover -s tests -k parallel` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T005 — Cheaper fixture I/O: no git fsync, temp dirs on tmpfs (FL-23, part 3)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
Fixture repositories stop paying for disk syncs and disk-backed temp files on runners whose
`/tmp` is a real disk (GitHub's), without changing what any test checks.

### Implementation notes
- tests/test_workflow.py `ToolkitTest.setUp` (~582–619) and the other test classes that build
  git fixtures (e.g. ~8033): add to the fixture env `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n`/
  `GIT_CONFIG_VALUE_n` for `core.fsync=none` and `gc.auto=0` (no background gc in
  short-lived repos). Keep `GIT_CONFIG_GLOBAL=/dev/null`.
  Respect an existing `GIT_CONFIG_COUNT` from the outer environment (append, don't clobber).
  Do not set these in toolkit scripts (only the test harness).
- `tests/run_parallel.py`: when `TMPDIR` is not set by the caller and `/dev/shm` is a writable
  directory with at least 1 GiB free (`os.statvfs`), create `tempfile.mkdtemp(prefix=
  'ai-tests-', dir='/dev/shm')`, pass it as `TMPDIR` to every batch, and remove it after the
  run (also on failure/KeyboardInterrupt); print `Temp dir: <path> (tmpfs)` once. Otherwise
  nothing changes. `AI_TEST_TMPFS=0` disables it.
- Execution probe (fixtures exec mock agents and installed toolkit scripts from their temp
  dirs, so a writable `noexec` mount would break them): after `mkdtemp`, write a two-line
  `#!/bin/sh` script into it, `os.chmod(path, 0o700)` (Python, not the `chmod` command), run it
  directly with `subprocess.run([path], timeout=…)` and require exit 0 and its expected stdout;
  `ST_NOEXEC` in `os.statvfs(...).f_flag` → fail without trying. On any failure (OSError,
  PermissionError, non-zero, timeout) remove the directory and fall back to the default temp
  dir, printing `Temp dir: default (/dev/shm not executable)`. Structure it as
  `choose_temp_dir(candidate, probe=exec_probe)` so the fallback is unit-testable; the candidate
  defaults to `/dev/shm` (a test-only override `AI_TEST_TMPFS_DIR` is allowed if it keeps the
  tests deterministic; document it as test-only).
- Measure: gate run time and test-time sum vs T004's baseline if T004 is DONE (else the plain
  `Ran … in …` before and after), recorded in the result with the machine's CPU count. Locally
  `/tmp` may already be tmpfs, so a small local gain is expected; say so.
- README (self-check section): the tmpfs temp dir and `AI_TEST_TMPFS=0`. Flow unchanged.

### Likely affected modules
tests/test_workflow.py, tests/run_parallel.py, README.md

### Acceptance criteria
- Tests named `test_fixture_io_*`:
  - a fixture's `git config --get core.fsync` prints `none` and `gc.auto` prints `0`; with an
    outer `GIT_CONFIG_COUNT=1` entry (e.g. `user.signingkey=x`) both the outer and the new
    entries apply;
  - run_parallel on a generated suite whose test writes `tempfile.gettempdir()` to a file:
    with `/dev/shm` available (skip with a reason otherwise) the path is under `/dev/shm/ai-
    tests-` and the directory is gone after the run; with `AI_TEST_TMPFS=0` or an explicit
    `TMPDIR` the path is the given/default one;
  - the same generated suite also writes an executable `#!/bin/sh` script into
    `tempfile.gettempdir()` (`os.chmod` 0o700) and runs it directly: it succeeds in the
    selected directory (integration check that the chosen dir allows execution);
  - `choose_temp_dir` with a probe that fails (fake probe returning False, and one raising
    `PermissionError`) and with a statvfs reporting `ST_NOEXEC`: returns the default temp dir
    and the created candidate directory no longer exists;
  - a source scan finds no `core.fsync` in `scripts/` or `templates/`.
- All existing tests pass unchanged; the result records the before/after timings.

### Validation
Targeted: `python3 -m unittest discover -s tests -k fixture_io` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T006 — Make the slowest tests cheaper (FL-23, part 4)
Status: TODO
Dependencies: T004, T005
Model: sonnet

### Goal
Cut the suite's total test time substantially so it runs well under 10 minutes on a 4-CPU
runner, by removing repeated work in the slowest tests, never by testing less.

### Implementation notes
- Start from the gate's slowest-15 list and test-time sum (T004). Profile the top entries
  (e.g. count processes per test: wrap `python3`/`git`/`bash` invocations through a counting
  `PATH` shim in a scratch run, or `python3 -m cProfile` on a single test) and record what
  dominates in the result before changing anything.
- Candidates, in order of expected value; do only what the measurement supports:
  1. fixture setup repeated per test (`setup_project` + bootstrap commit + `ready()`): build it
     once per test class/process into a cache dir (`setUpClass` or a module-level cache keyed
     by the toolkit source digest) and `shutil.copytree(symlinks=True)` it per test (git
     repos copy fine); tests that inspect setup itself keep the real path;
  2. supervised/pipeline tests that run more pipeline stages than their assertions need
     (e.g. a full implementation after the plan-revision assertions): stop them earlier only
     where the asserted behaviour is fully covered before that point and the test's name/goal
     does not include the later stages; list every such change in the result;
  3. redundant helper processes in hot script paths (the same `ai_helper` query several times
     in a row with nothing in between): behaviour-preserving only, every existing test
     unchanged.
- Hard constraints: every existing test ID still exists and keeps its assertions (compare the
  discovered ID list before and after: no ID removed or renamed); new tests (e.g.
  `test_fixture_cache_*`) may raise the count, documented in the result; collected and executed
  counts stay equal (the run_parallel count check); no assertion removed or weakened, no test
  skipped, no `__pycache__`/bytecode written under any `.ai/bin` (part of the
  gate digest: `dashboard.py` sets `sys.dont_write_bytecode` for this reason), no
  change to `.ai/validate`.
- Record in the result: before/after `Ran … in …`, test-time sum, slowest 15, CPU count, and
  an estimate for 4 CPUs (test-time sum / 4 × the CI slowdown observed in PR #27: ~1300 s
  shards vs ~6 min locally). Flow unchanged.

### Likely affected modules
tests/test_workflow.py, possibly scripts/ai-pipeline, scripts/ai-run, scripts/lib/workflow.py
(behaviour-preserving only)

### Acceptance criteria
- The test-time sum reported by the gate is at least 30% below T004's baseline, or the result
  shows the measurements, what was tried and why the rest is out of reach without weakening
  tests (then the task is still DONE if the measured top hot spots were addressed; say so
  plainly).
- Every test ID discovered before the task is still discovered (the result lists the before and
  after counts and any added IDs); collected equals executed; every existing test passes; no `.ai/bin/**/__pycache__`
  appears in any fixture (add `test_fixture_cache_*` tests for a fixture cache if one is added:
  a cached fixture is independent per test — a test that writes to its project does not
  affect the next one).

### Validation
Targeted: `python3 -m unittest discover -s tests -k fixture_cache` (only if a cache was added; must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T007 — Dashboard ignores test fixture runners (DB-05)
Status: TODO
Dependencies: none
Model: opus

### Goal
While the toolkit's test suite runs, `ai-dashboard` lists only real pipelines, not the
fixture checkouts under the test temp dir.

### Implementation notes
- `scripts/lib/dashboard.py` `ProcSource` (~42–79): `environ(pid)` → the set of `KEY=VALUE`
  entries of `<root>/<pid>/environ`, read with one bounded read (≤ 256 KiB; larger → treat as
  unreadable), `None` on any OSError (other users' processes, races). No symlink following
  beyond what `/proc` itself does; a FIFO or directory at that path in a fixture tree → None
  (open with `O_NONBLOCK`, check `S_ISREG` via `fstat`).
- `discover` (~122–150): skip a runner process whose environ contains exactly
  `AI_DASHBOARD_IGNORE=1` (constant `IGNORE_ENV`); unreadable → not skipped. Registered
  checkouts (host registry) are listed as today. Liveness is unchanged (it reads the marker
  process, which for an ignored checkout is never consulted).
- tests/test_workflow.py: every fixture env that starts toolkit runners gets
  `AI_DASHBOARD_IGNORE=1` (`ToolkitTest.setUp` ~588–619 and any other class whose subprocesses
  run `ai-run`/`ai-pipeline`/`ai-recover`). Check that the variable survives into resumed
  pipelines (ai-recover's resume exec, `ai_supervise_settings`, `env -i` anywhere) and into
  the watchdog's recovery start in tests; where a toolkit script deliberately rebuilds the
  environment, pass this one variable through and comment why.
  tests/test_dashboard.py `spawn` keeps real, unmarked processes (its tests need discovery);
  `FakeProc.add` gains an optional `environ` argument.
- README ("Watch all pipelines"): one sentence on `AI_DASHBOARD_IGNORE=1`; `docs/workflow.md`
  dashboard paragraph likewise. Flow unchanged unless the flow chart describes discovery (then
  update it and the hub Log as in the header).

### Likely affected modules
scripts/lib/dashboard.py, tests/test_dashboard.py, tests/test_workflow.py, README.md,
docs/workflow.md (scripts/ai-recover or scripts/lib/common.sh only if they drop the variable)

### Acceptance criteria
- Tests named `test_dashboard_ignore_*` in tests/test_dashboard.py:
  - FakeProc runner with environ `AI_DASHBOARD_IGNORE=1` in an unregistered checkout: not
    discovered; the same checkout registered: discovered (status from its records);
  - environ `AI_DASHBOARD_IGNORE=0`, `XAI_DASHBOARD_IGNORE=1`, missing, unreadable (mode
    000), a FIFO (returns within the scaled bound) or a > 256 KiB file: discovered as today;
  - a real spawned `ai-pipeline`-named process with `AI_DASHBOARD_IGNORE=1` in its env
    (`/proc`): not discovered; without it: discovered (existing
    `test_dashboard_liveness_real_pipeline_and_recover` unchanged).
- In tests/test_workflow.py, `test_dashboard_ignore_fixture_pipeline_is_hidden`: a fixture
  `ai-pipeline` run paused inside a mock session (an existing blocking mock mode, or a mock
  claude that waits for a file) is not listed by `dashboard.snapshot()` with the real `/proc`
  and `AI_DASHBOARD_ROOT` set to the fixture base, and the mock session's own environ contains
  the marker; the same for a pipeline resumed by `ai-recover`.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_ignore` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k dashboard` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T008 — PR URL and last plan/code review counts in `--json` and the details view (DB-02)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
Mission control reads a run's PR and its latest review verdicts from `ai-dashboard --json`
instead of grepping the checkout.

### Implementation notes
- `scripts/lib/dashboard.py` `inspect` (~267–308), every read through the pinned fds and
  `read_record` (bounded, no-follow), unreadable/malformed → empty values, never an exception:
  - `pr`: from `.ai/state.md` (`ai_fd`, `TASKS_LIMIT` or a small limit) the first match of
    `https://[^\s<>"']+/pull/\d+` in the `Next action:` line; else the last
    `pull request ready: <url>` in the tail of `.ai/run-log.md` (`tail=True`); else `''`.
    Sanitised with `text_field(…, 300)`.
  - `reviews`: open `.ai/reviews` with `os.open('reviews', DIR_FLAGS, dir_fd=ai_fd)` (closed in
    the `finally`); for `plan.md` → `reviews['plan']`, `current.md` → `reviews['code']`:
    exactly one `COUNTS` match (import `COUNTS` from workflow) → `{'blocker', 'major', 'minor'}`
    ints plus `head`: the short reviewed HEAD from `Host evidence: HEAD <sha>` (code) / the
    plan report's host evidence line if it has one (check `ai-review --plan`'s header), else
    `''`; zero or several count lines → `None`. Not verified against the host binding
    (comment: informational; the pipeline stays authoritative).
  - Both keys always present in a run dict (`''` / `{'plan': None, 'code': None}`), also for an
    unreadable checkout.
- `expanded_lines` (~542–550): after `path:`, `pr: <url>` when set, and `reviews: plan
  B<b> M<m> m<n> @<head> · code …` (omit a missing side; `none yet` when both are missing).
  Collapsed cards, header and goldens unchanged.
- README ("Watch all pipelines", JSON fields) and `docs/workflow.md` dashboard paragraph. Flow
  unchanged.

### Likely affected modules
scripts/lib/dashboard.py, tests/test_dashboard.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_dashboard_pr_review_*` in tests/test_dashboard.py:
  - state.md with `Next action: Human: test and merge the pull request
    https://github.com/o/r/pull/27` → `pr` is that URL; only the run log line → the URL from the
    log; neither → `''`; a URL with an escape sequence is sanitised;
  - plan.md and current.md with one counts line each and host evidence → the counts and heads;
    two counts lines, none, a FIFO or a symlink `reviews` dir → `None` (returns within the
    scaled bound), other fields intact;
  - `--json` carries `pr` and `reviews` for every run (also `unknown` ones); the expanded text
    view shows `pr:` and `reviews:` lines; existing golden tests unchanged.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_pr_review` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k dashboard` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T009 — `ai-dashboard --wait`: block until a run changes, print the changed runs (DB-03)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
Mission control waits for the next meaningful event (a stage or state change, a new
notification) with one command, and never misses an event between two waits.

### Implementation notes
- `scripts/lib/dashboard.py` `main` (~680–699): `--wait` (exclusive with `--once`; implies JSON
  output), `--since CURSOR`, `--timeout SECONDS` (default 3600, > 0), `--interval SECONDS`
  (default 2, ≥ 0.1); `--since`/`--timeout`/`--interval` without `--wait` → usage error.
- Notification identity, independent of display formatting (`events_of` sanitises and cuts
  messages to 300 characters, so two notifications sharing a prefix and timestamp, or two
  identical lines, look the same): `events_of` also returns a `notifications_mark`: 16 hex of
  sha256 over the log's `st_ino`, `st_size`, `st_mtime_ns` (from the same `fstat` as the
  bounded read) and the RAW bytes of the last complete line of the bounded tail (not
  `text_field`). The log is append-only, so every new line changes `st_size`; a rewrite changes
  the inode or size. `inspect` stores it in the run dict under `notifications_mark` (`None`
  without a log); every printer (`--json`, `--once`, TUI) drops the key, so existing goldens
  are unchanged; only `--wait` uses it.
- `fingerprint(run)` → `[status, stage, observation state or None, notifications_mark]`; keys
  by `run['checkout']`. Snapshots use
  `snapshot(all_runs=True)` (the 24 h hiding must not look like a change).
- Cursor: `base64.urlsafe_b64encode(json.dumps({checkout: fingerprint}, sort_keys=True))`
  without padding; decoding errors, non-dict or wrong shapes → `parser.error` (exit 2).
- Loop: baseline = decoded `--since` or the first snapshot; each poll (first one immediately
  when `--since` is given) compares: a checkout new to the baseline or whose fingerprint
  differs is changed (a checkout that disappeared is not reported). On a change: print
  `{"state_root", "cursor" (of the current snapshot), "timed_out": false, "runs": [the
  changed run dicts, in snapshot order]}` and exit 0. Deadline via `time.monotonic()`; on
  timeout print the same shape with `timed_out: true`, `runs: []` and the current cursor, exit
  1. Ctrl-C → exit 130 without a traceback. Writes nothing.
- README ("Watch all pipelines"): `--wait`, the cursor loop for scripts (`cursor=$(…| jq -r
  .cursor)`), exit codes; `docs/workflow.md` dashboard paragraph. Flow unchanged unless the
  flow chart describes mission control's watching (then update it and the hub Log).

### Likely affected modules
scripts/lib/dashboard.py, tests/test_dashboard.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_dashboard_wait_*` in tests/test_dashboard.py (fixture checkouts, FakeProc,
  `ai-dashboard --wait` as a subprocess with the test env, records written with
  `workflow.py observe` and the notification writer used by the existing tests):
  - waiting with `--interval 0.1 --timeout 20`, then `observe step build …` in one of two
    checkouts: exit 0 within the scaled bound, `runs` holds only that checkout with the new
    stage, `timed_out` false, `cursor` present;
  - a new notification line alone → change; a tasks.md edit alone (mtime only) → no change,
    `--timeout 1` → exit 1, `timed_out` true, `runs` [];
  - with status and stage unchanged: a second notification whose message shares the first
    300 displayed characters and the same `ts` → change; the same line appended again
    (identical bytes, same second) → change; plus a unit case that `notifications_mark` differs
    in both situations while `events` are equal, and that `--json` output has no
    `notifications_mark` key;
  - `--since <cursor from a previous call>` after a change made between the calls returns
    at once (exit 0, that run); with an unchanged state it waits until the timeout;
  - a new checkout appearing (registered) → reported; a removed one → not reported;
  - `--since garbage`, `--since` without `--wait`, `--wait --once`, `--timeout 0` → exit 2;
  - a run hidden by the 24 h rule that changes is still reported.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_wait` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k dashboard` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T010 — Docs, handoff and final audit for the batch
Status: TODO
Dependencies: T001, T002, T011, T003, T004, T005, T006, T007, T008, T009
Model: haiku

### Goal
README, `docs/workflow.md`, the vault flow chart and the handoff describe what the code now
does; the human knows which CI, vault and gate steps remain.

### Implementation notes
- Check each sentence the tasks added (README, `docs/workflow.md`) against the code once:
  `ai-task reorder`, the host reorder and the revision-recovery repair (T001/T002/T011), test timeouts and `CI` scale (T003), the
  timing report and batches (T004), tmpfs temp dir and `AI_TEST_TMPFS` (T005),
  `AI_DASHBOARD_IGNORE` (T007), `pr`/`reviews` (T008), `--wait` (T009). Fix contradictions; no
  new behaviour.
- Vault: confirm `agents-flow.md` reflects T002 (and any dashboard note the DB tasks changed)
  with a current `updated:`; hub Log has one dated line per flow-changing task. Never tick
  checkboxes.
- `.ai/handoff.md`: "## Flow chart" says `Flow chart updated` (or lists what is pending if a
  vault edit was denied); "Manual testing for the human" (`### Needs you` / `### Covered by
  automated tests` naming every new test group below); "Human todos"; record the timings from
  T004–T006.

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, vault agents-flow.md and agents.md (Log)

### Acceptance criteria
- `DocsConsistencyTest` passes; README mentions `ai-task reorder`, `AI_TEST_TIMEOUT_SCALE`,
  `AI_DASHBOARD_IGNORE`, `--wait` and `reviews`; `docs/workflow.md` mentions the host reorder
  after planning and plan revision.
- `test_pr_body_flow_this_repo_declares_the_flow_chart` passes.
- The handoff names `test_queue_reorder_*`, `test_queue_repair_*`, `test_queue_recovery_*`,
  `test_test_harness_timeouts_*`, `test_parallel_runner_*`, `test_fixture_io_*`,
  `test_dashboard_ignore_*`, `test_dashboard_pr_review_*` and `test_dashboard_wait_*` (and
  `test_fixture_cache_*` if T006 added it) under "Covered by automated tests", and every group
  exists in the tests (`python3 -m unittest discover -s tests -k <group>` runs ≥ 1 test each).

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

