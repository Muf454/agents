# Task queue

Edit `scripts/`, `templates/`, `tests/`, `README.md` and `docs/` only (plus the vault flow chart
and hub Log line where a task says so). Never edit `.ai/bin`, `.ai/prompts`, `.ai/validate`,
`.ai/ci-setup`, `.ai/permissions.allow`, `.claude/settings.json` or `.github/workflows/*`
(gate files; needed gate changes are human steps in `.ai/handoff.md`). Vault: a task that
changes the flow updates `~/zWiki/zWiki/20 Projects/agents/agents-flow.md` and its `updated:`
date in the same task and appends a dated line to the Log of `agents.md`; never tick vault
checkboxes. If the vault edit is denied, record it in the result and in the handoff's
"## Flow chart" section.
Source: vault `agents-backlog.md` (FL-27, FL-25, FL-26, FL-12, CU-2), planned 2026-10-16.
Already done and not planned: FL-21, CU-4, CU-1, CU-3 (evidence in `.ai/project-spec.md`).
Line references are at 7d22939 and verified by the planner; re-check them before editing.
Every behaviour change gets an offline regression test in the existing style; every task
leaves `.ai/bin/ai-check` passing and updates README.md / `docs/workflow.md` where the
behaviour it changes is described.
Gate note: `.ai/validate` runs the shell syntax checks and then `tests/run_parallel.py`
(about 4–6 min), inside the 600 s Bash tool limit. T001/T002 change that runner, so the gate
runs your change: a gate failure there is yours to repair. Should `.ai/bin/ai-check` still
time out in the session, run the task's targeted tests, record the timeout in the result, and
leave the full gate to the host's post-task `ai-check`. Tests with time bounds run in
parallel: assert "returns within N s" with generous bounds scaled by `tests/timeouts.py`,
never a tight duration. No profiling commands (denied).
No new executable file in this batch (this run's allowlist cannot `chmod +x`); test helper
scripts written into temp dirs use `os.chmod` from Python.

## T001 — Self-check runner becomes a child subreaper and reaps adopted orphans (FL-27, part 1)
Status: DONE
Dependencies: none
Model: opus

### Goal
On Linux every process a batch starts stays a descendant of `tests/run_parallel.py`, even
after its parent exits or it leaves the batch's process group, without zombies piling up and
without changing any batch's exit status or summary.

### Implementation notes
- `tests/run_parallel.py`: `enable_subreaper()` → True when
  `ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0` on `sys.platform` starting
  with `linux` (36 = `PR_SET_CHILD_SUBREAPER`, name it as a constant), False otherwise or on
  any `OSError`/`AttributeError`. Called from `main()` only, before the Dispatcher starts
  (comment: never at import; tests import the module).
- `/proc` helpers (Linux): `proc_stat(pid)` → `(state, ppid, starttime)` from
  `/proc/<pid>/stat`, parsing the fields after the LAST `)` (comm may contain spaces and
  parentheses), `None` on `OSError`/parse error. `children_of(pid)` scans numeric
  `/proc` entries once.
- `Dispatcher(…, reap=False)`: when True, `run()` joins threads with
  `thread.join(timeout=DRAIN_POLL)` in a loop and between joins calls `reap_adopted()`, and once
  more after the last join. `reap_adopted()` holds `self.lock` (batches start under it, so a
  just-started batch is always in `self.running`), finds children of `os.getpid()` in state
  `Z` whose pid is not a running batch, and `os.waitpid(pid, os.WNOHANG)` each, tolerating
  `ChildProcessError`. Never `os.waitpid(-1, …)` (comment why: it can take a batch's status,
  and Popen then reports exit 0). `main()` passes `reap=enable_subreaper()`.
- No kill changes here (T002). Keep the KeyboardInterrupt/BaseException path of `run()` as is.
- Module docstring: one sentence (Linux: the runner adopts orphaned descendants and reaps them).

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py (run_parallel tests, ~8546–8700)

### Acceptance criteria
- Tests named `test_parallel_runner_subreaper_*` in tests/test_workflow.py (skip with a reason
  when not Linux):
  - a generated suite whose test starts `sh -c 'sleep 1 & echo $! > <pidfile>'` (the sleeper is
    orphaned at once): run through the real script (`AI_TEST_WORKERS=2`), output `OK`; while the
    run lasts (a second test waits until the sleeper has exited, bounded) the sleeper's
    `/proc/<pid>/stat` ppid was the runner's pid (the test writes what it read to a file), and
    after the sleeper exits no zombie child of the runner remains (the test lists
    `/proc/*/stat` with ppid == runner pid and state `Z`, scaled bound);
  - with the subreaper on, a failing test still makes the run exit 1 with `FAILED` and a
    crashing batch still shows `crashed … without a unittest summary` (existing failure-path
    expectations hold);
  - `proc_stat` parses a comm with `) (` and spaces (unit case on a helper that takes the stat
    text), and `enable_subreaper()` is called only inside `main()` (source check with `ast`:
    no call at module level or in `Dispatcher`).
- Existing `test_parallel_runner_*` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k parallel_runner` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-16. `tests/run_parallel.py`: `PR_SET_CHILD_SUBREAPER`, `enable_subreaper()` (called
only in `main()`), `parse_stat()`/`proc_stat()`/`children_of()`, `Dispatcher(reap=…)` with
`reap_adopted()` (under the lock, per-pid `waitpid(pid, WNOHANG)` for non-batch zombies only)
between `join(timeout=DRAIN_POLL)` polls and once after the last join; `reap=False` keeps the
old plain joins. Tests `test_parallel_runner_subreaper_adopts_and_reaps_orphans`,
`…_keeps_failure_and_crash_reports`, `…_stat_parse_and_main_only`. Mutation check: with
`reap` forced off, the adopts test fails (orphan zombie never reaped). Targeted
`-k parallel_runner`: Ran 19 tests OK. `.ai/bin/ai-check`: PASS (689 tests, 424.6 s).
README and docs/workflow.md describe the subreaper. Flow unchanged (no vault edit).


## T002 — Stopping the self-check terminates the whole descendant tree, GNU `timeout` included (FL-27, part 2)
Status: DONE
Dependencies: T001
Model: opus

### Goal
A worker failure, an interrupt or SIGTERM leaves no process the self-check started: GNU
`timeout` and its child (own process group) go too, within a bounded time.

### Implementation notes
- `tests/run_parallel.py` `stop()` (~256–272): keep the batch group signals. When the runner
  is a subreaper (Dispatcher knows it: store the `reap` flag), also `descendants()`: walk the
  `/proc` ppid map from `os.getpid()` (exclude the runner itself) → `{pid: starttime}`.
  SIGTERM every pid; wait until each is gone or a zombie, up to `TERMINATE_GRACE` in total
  (poll ~0.1 s); then re-walk and SIGKILL every live descendant whose `/proc` starttime still
  equals the recorded one (new pids from forks during the stop get SIGKILL in that walk too);
  repeat the walk + SIGKILL up to 3 rounds until no live (non-zombie) descendant remains.
  Tolerate `ProcessLookupError`/`PermissionError`.
- Completion barrier (plan review P4): after the kill rounds, a bounded final wait
  (`FINAL_WAIT = TERMINATE_GRACE`, poll ~0.1 s, re-walking each poll and SIGKILLing any new
  live descendant) until every descendant is gone or a zombie. If the bound expires, store
  the survivors in `self.cleanup_failed` and print `run_parallel: could not terminate
  descendants: <pid> <pid> …` to stderr; `main()` then exits 1 even on a path that would
  otherwise exit 0 (SIGTERM keeps 143). SIGKILL is asynchronous: never treat "signal sent" as
  "gone"; only `/proc` state counts.
- Shutdown ownership (P4): `stop()` is idempotent and owned by its first caller: under
  `self.lock` the first caller sets `self.terminating = True` and does the kill rounds and the
  final wait outside the lock; every later caller (second worker, `run()`'s except path)
  waits on `self.stop_done` (a `threading.Event` set at the end, also on exception, in a
  `finally`). `reap_adopted()` checks `self.terminating` under the lock and returns at once
  while it is set and `stop_done` is not, so the main-thread reap loop of T001 never reaps
  during the kill rounds or the final wait (zombies keep their pids, so no reuse). The owner
  calls `reap_adopted()` itself after `stop_done` is set (a flag argument bypasses the check),
  and `run()` reaps once more after joining.
- `drain()` / `DRAIN_GRACE` stay as the fallback for a pipe held by a process the walk cannot
  see (non-Linux).
- SIGTERM handling in `main()` (`terminated` → `SystemExit(143)`) and the KeyboardInterrupt
  path both go through `stop()`; check SIGINT delivered to the runner alone (not the group:
  batches are in their own sessions) reaches `run()` as KeyboardInterrupt.
- Concurrency: `stop()` can run in a worker thread while `run()` joins; keep the
  "start checked under the lock" invariant; the walk runs outside the lock (no batch can start
  once `stopping` is set).
- Tests must not make the TEST process a subreaper: run the Dispatcher in a child Python driver
  script written to the test's temp dir (it imports `run_parallel`, calls `enable_subreaper()`,
  patches `subprocess.Popen` inside the driver to raise `OSError` on the second batch launch
  after the pid files exist, prints the exception type and exits). Every recorded pid is
  SIGKILLed in `addCleanup` whatever the outcome.
- Module docstring and README self-check paragraph (if it describes stop behaviour): GNU
  `timeout` groups and other descendants are terminated on Linux.

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py (run_parallel tests), README.md

### Acceptance criteria
- Tests named `test_parallel_runner_tree_*` (skip when not Linux or `timeout` is missing):
  - worker failure: the driver's batch test runs `timeout 120 sh -c 'echo $$ > <child.pid>;
    exec sleep 120'` (writes the timeout pid from Popen too) and waits; the second launch
    raises `OSError`; the driver exits with that error within `TERMINATE_GRACE + 10` s × scale
    and both the `timeout` pid and the sleeper pid are gone (no `/proc/<pid>` or state `Z`
    with a dead parent; poll briefly);
  - SIGTERM: the real `run_parallel.py` on a generated suite with the same test, SIGTERM to
    the runner once both pid files exist: exit 143 within the bound, both pids gone;
  - SIGINT to the runner alone: it exits non-zero within the bound, both pids gone;
  - stubborn detached descendant: the batch test starts `setsid sh -c 'trap "" TERM; echo $$ >
    <stub.pid>; exec sleep 120' </dev/null >/dev/null 2>&1 &` (ignores SIGTERM, own session,
    inherited output closed, so no batch reader waits on it) and waits; SIGTERM to the runner →
    exit 143 within `TERMINATE_GRACE * 2 + 10` s × scale and the stub pid is gone or a zombie
    when the runner has returned (checked right after exit, no extra polling);
  - fork during shutdown: the batch test runs `sh -c 'trap "sleep 120 & echo \$! > <forked.pid>;
    wait" TERM; echo $$ > <parent.pid>; while :; do sleep 1; done'`; worker-failure stop → both
    the parent and the pid in `forked.pid` (if written) are gone after the driver exits;
  - completion barrier failure: a driver that patches the "is descendant alive" check to always
    report one live pid → stderr has `could not terminate descendants` and the exit code is
    non-zero, within `FINAL_WAIT + TERMINATE_GRACE + 10` s × scale;
  - concurrent stop and reaping: in a driver, two batches fail at once (both workers call
    `stop()`) while `run()`'s reap loop runs; a patched `os.waitpid` records the calls made while
    `terminating` is set and `stop_done` is not → none; `stop()`'s kill rounds ran exactly once
    (a counter); both workers returned and `run()` re-raised the first error;
  - mutation check recorded in the result: with the descendant walk disabled, the three
    original tests and the stubborn-descendant test fail (`timeout` or the stub survives).
- Existing `test_parallel_runner_*` tests (T014's three `*_kills_batch_descendants` included)
  pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k parallel_runner` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-16. `tests/run_parallel.py`: `process_table()`, `descendants(root)` (ppid walk of
one /proc scan), `signal_pid()` (signals only while /proc shows the recorded starttime);
`Dispatcher.stop()` is owned by its first caller (`terminating` under the lock, later callers
wait on `stop_done`, set in a `finally`), `terminate()` keeps the group signals and, with
`reap`, SIGTERMs the `live_descendants()` walk, waits ≤ `TERMINATE_GRACE`, then up to
`KILL_ROUNDS` = 3 walk + SIGKILL rounds and a `FINAL_WAIT` completion barrier; survivors go to
`cleanup_failed` + stderr `run_parallel: could not terminate descendants: …`, and `main()`
adds a problem (exit 1). `reap_adopted()` returns at once while a stop runs (owner passes
`after_stop=True`); `run()`'s except path reaps after its joins. Deviation noted: each walk
kills whatever it finds below the runner (a walk-found pid is ours by construction), with the
starttime re-checked right before each signal, instead of only pids from the first snapshot.
Tests: 8 `test_parallel_runner_tree_*` (worker failure, SIGTERM, SIGINT to the runner alone,
stubborn detached descendant, fork during stop, barrier failure, main exit on
`cleanup_failed`, concurrent stops never reap). Mutation checks: walk disabled
(`live_descendants` → {}) → 6 of 8 fail, incl. worker-failure, SIGTERM, SIGINT and stubborn;
the reap-during-stop guard disabled → the concurrent test fails (5 waitpids recorded).
Targeted `-k parallel_runner`: Ran 27 tests OK. `.ai/bin/ai-check`: PASS (697 tests, 408.3 s).
README and docs/workflow.md updated. Flow unchanged (no vault flow edit).


## T013 — An interrupt during worker startup still runs the shutdown (FL-27, part 3; plan review round 2 P6)
Status: DONE
Dependencies: T002
Model: opus

### Goal
SIGINT or SIGTERM that arrives while `Dispatcher.run()` is still starting its worker threads
(after the first worker launched a batch) goes through T002's `stop()` like any later
interrupt: no batch, `timeout` or detached descendant survives.

### Implementation notes
- Verified at 92167cd: `run()` (tests/run_parallel.py:274–286) calls `thread.start()` for every
  worker BEFORE its `try:`; a `KeyboardInterrupt` (SIGINT) or the `SystemExit(143)` of
  `terminated()` (SIGTERM, :304–305) raised in the main thread during a later `start()` escapes
  without `stop()` while the first worker already runs a batch.
- `run()`: keep a `started` list; the `try:` covers the start loop as well as the joins (and
  T001's reap loop): `for thread in threads: thread.start(); started.append(thread)`. The
  `except BaseException:` path calls `self.stop()`, then joins only `started` threads (a
  `Thread` that was never started cannot be joined: `RuntimeError`), then re-raises. A
  thread whose `start()` raised is not in `started`. Keep T002's ownership (`stop()` idempotent,
  later callers wait on `stop_done`) and the final reap after the joins.
- Signals between `Dispatcher(...)` construction and `run()`'s `try:` start no batch, so they
  need nothing; check `main()` creates no child before `run()` (comment if relevant).
- Concurrency: `stop()` from the main thread may race a worker's own `stop()` (first one owns
  it, T002); a worker started just before the interrupt either launches its batch under the
  lock before `stopping` is set (then `stop()` sees it in `self.running`) or sees `stopping`
  and returns, the existing invariant.
- Test via a child Python driver as in T002 (never make the test process a subreaper): the
  driver imports `run_parallel`, calls `enable_subreaper()`, builds a Dispatcher with
  `workers=2` and two batches whose test starts `timeout 120 sh -c 'echo $$ > <child.pid>;
  exec sleep 120'` (Popen pid of `timeout` written too) plus a detached
  `setsid sh -c 'trap "" TERM; echo $$ > <stub.pid>; exec sleep 120' </dev/null >/dev/null 2>&1 &`,
  and patches `threading.Thread.start` (within the driver) so the SECOND call first waits
  (bounded) until both pid files of the first batch exist and then raises `KeyboardInterrupt`.
  The driver counts `stop()` kill-round entries, prints the exception type and the count, and
  exits non-zero. Every recorded pid is SIGKILLed in `addCleanup`.

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py (run_parallel tests)

### Acceptance criteria
- Tests named `test_parallel_runner_startup_*` in tests/test_workflow.py (skip when not Linux
  or `timeout`/`setsid` is missing):
  - interrupt on the second `thread.start()` after the first batch launched: the driver prints
    `KeyboardInterrupt` and a kill-round count of exactly 1, exits non-zero within
    `TERMINATE_GRACE * 2 + FINAL_WAIT + 10` s × scale, no `RuntimeError` about joining an
    unstarted thread, and right after it exits the `timeout` pid, the sleeper pid and the stub
    pid are each gone or a zombie;
  - the same with `SystemExit(143)` raised instead (the SIGTERM path): exit 143 reported by the
    driver, same process checks;
  - mutation check recorded in the result: with the start loop moved back outside the `try:`,
    the first case fails (stop count 0 or a survivor).
- `test_parallel_runner_*` (T001's `subreaper_*`, T002's `tree_*` included) pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k parallel_runner` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-16 (claude, opus): `Dispatcher.run()` keeps a `started` list; the start loop is inside
the `try:`, the `except BaseException:` path calls `stop()` and joins only `started`, then the
final reap and re-raise as before. `main()` starts no child between `Dispatcher(...)` and
`run()`; its earlier `exec_probe` is a bounded `subprocess.run` in the runner's own group.
Tests `test_parallel_runner_startup_sigint_during_worker_start_stops_batch` and
`..._sigterm_...` (driver patches the main thread's second `Thread.start()` to wait for the
`timeout`, sleeper and detached TERM-ignoring stub pid files, then raise `KeyboardInterrupt` /
`SystemExit(143)`): driver prints the exception, `rounds 1`, exits non-zero within
`(TERMINATE_GRACE*2 + FINAL_WAIT + 10) × scale`, no `RuntimeError`, all three pids gone or
zombie right after exit. Mutation (start loop back outside the `try:`): both fail with
`rounds 0`. `-k parallel_runner`: Ran 29 tests OK. `.ai/bin/ai-check`: PASS, 699 tests.

## T003 — `tasks fill-sections`: add the two content-free sections to TODO tasks (FL-25 a, part 1)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
A deterministic helper that gives TODO tasks a missing `### Likely affected modules` or
`### Result / notes` heading, changes nothing else, and writes nothing when nothing is missing.

### Implementation notes
- `scripts/lib/workflow.py`, next to `tasks_reorder` (~527): `tasks_fill_sections()`,
  dispatched as `tasks fill-sections` from `task_command` before `tasks()` is called there
  (like `reorder`: branch on `arguments[0]` at the top, since `tasks()` fails on exactly these
  queues).
- Use `queue_segments` (fence-aware; fenced `### …` lines are not sections). For each task
  block whose single `Status:` line is `TODO` (no or several Status lines → leave it, `tasks
  check` reports it): required order is `REQUIRED_SECTIONS` = the tuple `tasks()` uses (~430;
  hoist it to a module constant and use it in both places). For each of `Likely affected
  modules` and `Result / notes` missing as an exact `### <name>` line: insert it right before
  the first later required section present in the block, else at the block end before its
  trailing blank lines. Inserted text: `### Likely affected modules` + `(not listed)`, and
  `### Result / notes` with an empty body; separate with one blank line as the template does.
- Other missing sections are not added (content; `tasks check` keeps rejecting them).
- No change → exit 0, no output, file bytes and `st_mtime_ns` unchanged. Change → atomic
  write (the helper `tasks_reorder` uses), print
  `Task queue: added missing sections: T019 (Likely affected modules, Result / notes), T020 (Result / notes)`.
- `scripts/ai-task`: no new subcommand (host-only helper); README task-queue paragraph and
  `docs/workflow.md` one line each. Flow unchanged here (T004 wires it in).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_task_sections_fill_*` in tests/test_workflow.py (through `workflow.py tasks
  fill-sections` in a fixture checkout):
  - the raid case: TODO T019 without both sections, T020 without `### Result / notes`, a DONE
    T001 without `### Likely affected modules` in a DONE-preserving fixture: after the helper,
    T019/T020 have the headings at the canonical positions and `tasks check` passes for them;
    T001's block is byte-identical (and `tasks check` still reports T001); the printed line
    names T019 and T020 with their sections;
  - a complete queue: exit 0, no output, bytes and `st_mtime_ns` unchanged;
  - a fenced `### Result / notes` inside a TODO task's notes does not count as present; a task
    missing `### Goal` gets only the two sections and `tasks check` still fails with
    `missing ### Goal`;
  - preamble, trailer and other tasks are byte-identical.
- `tasks()` uses the shared constant; all existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k task_sections_fill` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k queue_reorder` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Added `workflow.py tasks fill-sections` (`tasks_fill_sections`, `fill_task_sections`,
`section_positions`) and the shared `REQUIRED_SECTIONS` constant used by `tasks()`. Fence-aware,
TODO tasks with exactly one Status line only; atomic write, mode kept; silent no-op otherwise.
Tests `test_task_sections_fill_{raid_case,complete_queue_is_untouched,ignores_fences_and_adds_only_two}`
pass; `-k queue_reorder`: 7 OK; `.ai/bin/ai-check`: PASS, 702 tests. README and docs/workflow.md updated.

## T004 — The host fills missing task sections after triage, planning and plan revision (FL-25 a, part 2)
Status: TODO
Dependencies: T003
Model: sonnet

### Goal
A triage, planning or revision session that forgets `### Likely affected modules` or
`### Result / notes` on a new task no longer stops the run; the repaired queue is committed
with the stage's own record.

### Implementation notes
- `scripts/ai-run` triage path: after the `dirty_beyond_records` check (~516) and before
  `ai_helper tasks check` (~519): `fill_out=$(ai_helper tasks fill-sections 2>&1) || ai_die
  "Triage stage: task queue is invalid: ${fill_out#Error: }"`, print `$fill_out` when
  non-empty. The host's triage commit (~525–532) already stages `.ai/tasks.md`; verify.
  The "dispositions already complete" path (~494) is not changed (recorded limitation).
- Planning path: the same call before `tasks reorder` (~331) with `Planning: task queue is
  invalid: …`. Revision path: before `tasks reorder` (~434) with `Plan revision stage: task
  queue is invalid: …` (always escalated by ai-recover). The revision commit (~457) stages
  `.ai/tasks.md`; `revision_scope` already allows it.
- Contracts: TRIAGE CONTRACT (~507) gains "Copy the task format of .ai/tasks.md exactly: the
  heading, Status:, Dependencies:, Model: and every ### section (Goal, Implementation notes,
  Likely affected modules, Acceptance criteria, Validation, an empty Result / notes); the host
  adds a missing Likely affected modules or Result / notes, anything else missing stops the
  run." PLANNING CONTRACT (~305–311) and REVISION CONTRACT (~404–414): the same host sentence.
- Mock claude (tests/test_workflow.py mock modes): `triage-missing-sections` (like the existing
  accepting triage mode, but the new task lacks both sections, committed by the session),
  `revise-accept-missing-sections`, `plan-missing-sections`, and `triage-missing-goal`.
- Docs: README (triage / planning paragraphs) and `docs/workflow.md` (triage, plan, plan
  revision): the host step.
- Vault (flow change): `agents-flow.md` triage node and the plan/revision script boxes gain
  "host adds missing Likely affected modules / Result / notes"; `updated:` bumped; hub Log line.
- `.ai/handoff.md` "## Flow chart": replace `Flow unchanged so far …` with `Flow chart updated:
  …` (what T004 changed); `test_pr_body_flow_this_repo_declares_the_flow_chart` must pass.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md and
agents.md (Log), .ai/handoff.md

### Acceptance criteria
- Tests named `test_task_sections_host_*` in tests/test_workflow.py:
  - a pipeline whose review has one MAJOR, `MOCK_CLAUDE` triage mode `triage-missing-sections`:
    no stop at triage, `Task queue: added missing sections` in the output, the host's
    `chore(ai): record review triage` commit has the new task with both headings, the fix task
    runs and the run finishes as the existing accepting-triage tests do;
  - `triage-missing-goal`: stops with `missing ### Goal` (as today), no fill line for Goal;
  - `ai-run --plan` with `plan-missing-sections`: exit 0, `planned` record, headings present in
    the working tree, nothing committed;
  - a supervised plan revision with `revise-accept-missing-sections`: one revision session, the
    committed revision has the headings, no stop;
  - the triage prompt (recorded by the mock) contains `Copy the task format of .ai/tasks.md exactly`.
- All existing tests pass unchanged; the vault flow chart and hub Log are updated (or the
  denial is recorded); the handoff's "## Flow chart" first line reads `Flow chart updated`.

### Validation
Targeted: `python3 -m unittest discover -s tests -k task_sections` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k triage` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T005 — Escaped pipes inside disposition and plan-disposition cells (FL-25 b)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
A disposition row whose Evidence cell contains `\|` (raid polish P11: `--yes \| --no`) is read
with the right Task column instead of stopping the run.

### Implementation notes
- `scripts/lib/workflow.py`: one cell pattern `TABLE_CELL = r'((?:\\.|[^\\|\n])*?)'` used for the
  evidence and task cells (plan review P2: a backslash is only ever consumed together with the
  character after it, so `\|` can never be split into a cell ending in `\` and a separator;
  the earlier `(?:\\\||[^|\n])` let `[^|\n]` eat the backslash on backtracking; comment why) of `DISPOSITION_ROW` (~911) and `PLAN_DISPOSITION_ROW` (~2329) in
  place of `(.*?)`; keep the ID and disposition groups and flags as they are. A helper
  `table_cell(text)` → `text.replace('\\|', '|').strip()` applied where the captured cells are
  turned into values (triage_check ~951, review_rounds ~1027, rejected rows ~1470, disputes
  ~1625, plan history ~2367, plan-dispositions-check ~2508; grep for `DISPOSITION_ROW` to catch
  every site). Writers that already escape (`cell` lambdas ~1563, ~2831) stay; check that a
  value read with `|` and re-rendered comes out escaped once (no `\\|`).
- An unescaped `|` inside a cell still splits the row (unchanged; documented).
- `docs/workflow.md` (dispositions format) one sentence. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Tests named `test_disposition_pipes_*` in tests/test_workflow.py:
  - `triage-check --fresh` on dispositions with `| M1 | accepted | use `--yes \| --no` | T019 |`
    and a TODO T019: passes (`accepted=1`); the same with `rejected` and 20+ characters of
    evidence containing `\|`: passes;
  - `plan-dispositions-check` on the P11 row (`| P11 | accepted | flag `--no\|--yes` … | T030 |`)
    with T030 TODO: passes and counts it accepted (the Task cell reads `T030`, not `--no\`);
  - the re-check prompt / dispute record of a rejected row with `\|` carries the evidence with
    `|`, and the PR body renders it escaped once;
  - an unescaped `|` in the evidence still fails as today (row misread → the existing error);
  - malformed rows (P2), for both `triage-check --fresh` and `plan-dispositions-check`: the
    missing-task-cell row `| P11 | accepted | discussion of fix \| T030 |` (and `| M1 | accepted
    | discussion of fix \| T019 |`) with T030/T019 TODO fails as a malformed row (no Task cell;
    it is never read as evidence `discussion of fix \` + task `T030`); a unit case on
    `TABLE_CELL` itself shows `a \| b` matches as one cell; a backslash elsewhere (`C:\path`)
    is kept as is;
  - round trip: evidence read from `x \| y`, rendered by the existing `cell` writers and read
    again gives `x | y` both times.
- All existing tests pass unchanged (`test_triage_severity_suffix_*` included).

### Validation
Targeted: `python3 -m unittest discover -s tests -k disposition_pipes` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k triage_severity_suffix` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T006 — Template prompts show the exact task format and the pipe rule (FL-25, prompts)
Status: TODO
Dependencies: T004, T005
Model: haiku

### Goal
Sessions see the exact task format and how to write a pipe in a table, so the host repairs of
T004/T005 are rarely needed.

### Implementation notes
- `templates/.ai/prompts/triage.md` (task paragraph ~18–21): new tasks copy the format of
  `.ai/tasks.md` exactly: heading `## T0NN — Title`, `Status: TODO`, `Dependencies:` (`none` or
  IDs), `Model:`, then `### Goal`, `### Implementation notes`, `### Likely affected modules`,
  `### Acceptance criteria`, `### Validation`, and an empty `### Result / notes`. Dispositions
  paragraph (~13): in a table cell write a pipe as `\|` (better: avoid it, e.g. "or"); an
  unescaped `|` splits the row and the runner stops.
- `templates/.ai/prompts/plan-revision.md` (accepted bullet ~11–15 and the dispositions
  paragraph ~26–29) and `templates/.ai/prompts/plan.md` (where it describes the queue): the
  same two rules, one sentence each.
- `templates/.ai/tasks.md` preamble: one sentence that every section heading is required and
  `### Result / notes` starts empty.
- Keep the shared "## How to work here" block identical in runner/triage
  (`test_tool_contract_section_is_shared_by_prompts`); this task does not touch it.
- Never edit `.ai/prompts` (installed copy; handoff lists the upgrade). Flow unchanged.

### Likely affected modules
templates/.ai/prompts/triage.md, templates/.ai/prompts/plan-revision.md,
templates/.ai/prompts/plan.md, templates/.ai/tasks.md, tests/test_workflow.py

### Acceptance criteria
- Test `test_task_sections_prompts_show_the_format` in tests/test_workflow.py: triage.md,
  plan-revision.md and plan.md each contain `### Likely affected modules` and
  `### Result / notes` and the phrase `write a pipe as`; templates/.ai/tasks.md mentions that
  `### Result / notes` starts empty.
- `test_tool_contract_section_is_shared_by_prompts` and all other existing tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k task_sections` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k tool_contract` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T011 — Host clears `.ai/local/scratch` through pinned directory descriptors (FL-26, deletion)
Status: TODO
Dependencies: none
Model: opus

### Goal
The host empties `.ai/local/scratch` before and after every Claude session and can never
delete anything outside it, even when a session replaced `scratch`, `.ai/local` or `.ai` with
a symlink (plan review P1).

### Implementation notes
- Why not `rm -rf -- .ai/local/scratch`: it follows a symlinked parent (`.ai/local` or `.ai`)
  and the gate digest does not cover `.ai/local`, so a session could point the host's delete
  at an external directory. Startup `safe_paths` (workflow.py:44–63, via `ai_root`) runs
  before the session and does not help after it.
- `scripts/lib/workflow.py`, next to `local_dir_fd` (~3352): `clear_scratch(root)` dispatched
  as `workflow.py clear-scratch` (root from `AI_ROOT`, else cwd). `local_fd =
  local_dir_fd(root)` (every component opened `O_NOFOLLOW`); None → `warn('could not clear
  .ai/local/scratch: unsafe or missing .ai/local')`. Then `os.stat('scratch', dir_fd=local_fd,
  follow_symlinks=False)`: missing → nothing; a symlink or any non-directory →
  `os.unlink('scratch', dir_fd=local_fd)`; a directory → `shutil.rmtree('scratch',
  dir_fd=local_fd)` only when `shutil.rmtree.avoids_symlink_attacks` is True (fd-based walk,
  never follows inner symlinks), else warn and skip. Every `OSError` → warning. Always exit 0
  (never fails its caller), warning text starts `Warning: could not clear .ai/local/scratch`.
  Comment: never a path-based delete; the pinned descriptor is the protection.
- `scripts/ai-run` `claude_session` (~244–289): `clear_scratch() { ai_helper clear-scratch ||
  true; }`. Called (a) inside the loop right before the `timeout … claude -p` call (~265; also
  before a retry after a limit pause), and (b) right after the post-session `ai_guard_verify`
  (~274), never before it: the helper is the checkout's `.ai/bin/lib/workflow.py`, which is
  only trusted once the gate digest has been verified. If the verify dies, no clear runs; the
  next start's `safe_paths` rejects a symlinked `scratch` with `Unsafe symlink in workflow
  path` (existing behaviour, kept: reconciles P1's "startup rejection vs cleanup" point — a
  pre-existing `scratch` symlink stops the run at startup, one created during a session is
  removed after it).
- No permission change; prompts and docs are T007.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_scratch_clear_*` in tests/test_workflow.py:
  - helper level (`workflow.py clear-scratch` in a fixture checkout, an external temp dir
    `victim/` holding `scratch/keep` and `keep`): (1) `.ai/local` replaced by a symlink to
    `victim/` → exit 0, warning, `victim/scratch/keep` still exists; (2) `.ai` replaced by a
    symlink to a dir whose `local/scratch/keep` exists → exit 0, warning, file survives;
    (3) `.ai/local/scratch` a symlink to `victim/` → link gone, `victim/keep` exists; (4) a real
    `scratch/` holding a nested dir and an inner symlink to `victim/` → `scratch` gone,
    `victim/keep` exists; (5) no `scratch` → exit 0, no output; (6) `scratch` a regular file →
    removed;
  - end to end (`ai-run --approved`, mock claude): mode `scratch-leftover` implements the task,
    commits and writes `.ai/local/scratch/tmp.test.sh` plus a nested dir → task DONE, no
    `.ai/local/scratch` afterwards, nothing under it committed; a pre-existing
    `.ai/local/scratch/old` is gone when the session starts (the mock records whether it saw
    it: it must not); mode `scratch-parent-symlink` moves `.ai/local` aside and replaces it by a
    symlink to `victim/` (with `scratch/keep`) → whatever the run's exit code,
    `victim/scratch/keep` still exists; mode `scratch-symlink` makes `.ai/local/scratch` a
    symlink to `victim/` → link removed after the session, `victim/keep` exists;
  - a pre-existing `.ai/local/scratch` symlink at start → the run stops with `Unsafe symlink
    in workflow path` and the target is untouched.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k scratch_clear` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T007 — Scratch files go to `.ai/local/scratch/`, which the host empties around every session (FL-26, prompts and docs)
Status: TODO
Dependencies: T011
Model: sonnet

### Goal
A session that needs a throwaway file never leaves one in source or test directories, and
leftover scratch files never reach the gate or a commit.

### Implementation notes
- The host clear (`workflow.py clear-scratch`, called in `claude_session`) is T011; this task
  only tells sessions and readers about it. Do not change `scripts/ai-run` or the helper.
- Template prompts, shared "## How to work here" block of `templates/.ai/prompts/runner.md` and
  `triage.md` (keep both identical; `test_tool_contract_section_is_shared_by_prompts`), plus
  any other template prompt that has that block and a shell: a bullet "Scratch files
  (experiments, throwaway scripts or tests) go only under `.ai/local/scratch/` (ignored by Git;
  the runner empties it before and after every session). Never create them in source or test
  directories, never name them like tests (`*.test.*`, `test_*.py`), and do not try to delete
  files: `rm` is not allowed."
- `templates/CLAUDE.md` (Persistence and recovery: "Raw logs live in ignored `.ai/local/`"): one
  sentence on `.ai/local/scratch/`.
- No permission change (`templates/.ai/permissions.allow` untouched; `Bash(rm *)` cannot be
  limited to untracked paths). Record this decision in `docs/workflow.md` next to the allowlist
  description.
- Docs: README (runner sessions / how sessions work) and `docs/workflow.md` (session contract).
- Vault (flow change): `agents-flow.md` one-task diagram/box: "host empties .ai/local/scratch
  before and after each session"; `updated:` bumped; hub Log line.

### Likely affected modules
templates/.ai/prompts/runner.md, templates/.ai/prompts/triage.md,
templates/CLAUDE.md, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md
and agents.md (Log)

### Acceptance criteria
- Tests named `test_scratch_dir_*` in tests/test_workflow.py:
  - the runner prompt (recorded by the mock) contains `.ai/local/scratch/`; the shared "How to
    work here" blocks stay identical;
  - README and `docs/workflow.md` mention that the host empties `.ai/local/scratch` and never
    follows a symlink there (string checks).
- T011's `test_scratch_clear_*` still pass.
- All existing tests pass unchanged; vault flow chart and hub Log updated (or the denial
  recorded).

### Validation
Targeted: `python3 -m unittest discover -s tests -k scratch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k tool_contract` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T012 — Recovery answer scanner: one line-start object inside bracket-free prose (FL-12 redesign, plan review round 2 P3)
Status: TODO
Dependencies: none
Model: opus

### Goal
`recover_decision` accepts a decision written after or before prose only when no JSON container
can enclose it, with a rule that needs no string parsing outside the object: the prose around
the one candidate object contains no `{`, `}`, `[` or `]` at all.

### Implementation notes
- Why (design note "Recovery answer scanner" in `.ai/current-plan.md`): rounds 1 and 2 found
  ways to put a candidate inside an enclosing container (a scan at each `{`; then character
  counts fooled by a bracket inside a JSON string, `Diagnostic: ["]",` + object + `]`). Any
  string-aware count over prose is ill-defined (prose has unbalanced quotes). An enclosing
  container needs an opening bracket before the object and a closing one after it; forbidding
  every bracket character outside the object rules that out without parsing prose.
- `scripts/lib/workflow.py` `recover_decision` (~1886–1916). Envelope checks unchanged.
  1. `text` = fence-stripped result as today. If `json.loads(text)` (duplicate-key hook)
     succeeds: a dict is validated as today; any other JSON value escalates.
  2. Otherwise: `start` = index of the first `{` in `text`; none → escalate (no decision).
     Escalate unless ALL hold:
     - `text[:start]` contains none of `{}[]` (so in particular no `[` opens before it) and
       the characters between the last newline before `start` and `start` are whitespace
       (line start; inline, backticked or quoted objects are prose, so they escalate);
     - `JSONDecoder(object_pairs_hook=…).raw_decode(text, start)` succeeds (a
       `DuplicateKey(ValueError)` from the hook or a decode error → escalate) and returns a dict;
     - the rest of the object's last line is whitespace, and `text[end:]` contains none of
       `{}[]` (no second object, no closing bracket of an enclosing container);
     - the dict's `action` is in `RECOVER_ACTIONS` and its fields pass today's checks.
     Then use it. Fence marker lines are plain prose here (backticks are not brackets).
     Comment the rule and the reason above the scanner. No character counting, no string
     parsing outside the object.
  3. Leave the escalation reason as today; T008 adds the excerpt.
- Trade-off (recorded in the plan's Risks): prose with any bracket (`[1]`, a markdown link,
  an inline example object) escalates even when a valid decision follows. Escalation is the
  safe side and the recover prompt asks for the object alone.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_recovery_decision_scan_*` in tests/test_workflow.py (helper
  `recover-decision` on envelopes, as the strict test does):
  - accepted: diagnosis paragraph then, on its own line, `{"action": "escalate", "reason": "x",
    "human_action": "y"}` → `escalate\tx\ty`; prose on the lines after the object → still
    accepted; a fenced object after prose → accepted; a decision spread over several lines
    (line-start `{`, closing `}` alone on the last line) → accepted; a decision whose string
    values contain `[`, `]`, `{` or `}` → accepted (inside the object the JSON parser decides);
  - escalate, the P3 round 2 reproduction: `Diagnostic: ["]",` / `{"action":"commit_and_rerun",
    "reason":"example"}` / `]` (three lines); the same with `"{"` and `"}"` strings in the
    prefix line; a lone `]` or `}` on a line after a valid decision; a `[` in the prose before it;
  - escalate, the round 1 cases: `Broken diagnostic: {"details":{"action":"commit_and_rerun",
    "reason":"example"}, BROKEN}`; the same broken object at a line start; `Diagnostic:
    [{"action":"rerun","reason":"example"}]`; a line `Diagnostic: [`, the object on its own line,
    then `]`; a quoted example `"{\"action\": \"rerun\", \"reason\": \"x\"}"`; an inline
    backticked decision; prose quoting the template inline followed by a real decision on its
    own line (the inline braces are brackets in the prose);
  - escalate: two decisions (same or different actions, separate lines); a duplicate key in the
    candidate; a valid action without `reason`; a line-start object with text after it on the
    same line; a candidate without a known `action`;
  - a decision with a nested object containing another action → only the outer one counts.
- `test_recovery_decision_parsing_is_strict` passes unchanged (`Decision: {…}` → not at a line
  start; `{…} {…}` → text after the object; `[{…}]` → whole-text JSON that is not an object).
- All other existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k recovery_decision` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T008 — Recovery decision: one decision object inside prose is accepted; the escalation keeps what the session wrote (FL-12)
Status: TODO
Dependencies: T012
Model: opus

### Goal
A recovery session that writes its diagnosis before (or after) its JSON decision is acted on;
an answer without exactly one valid decision still escalates, now with the session's words in
the reason.

### Implementation notes
- Plan review round 2 (P3): the prose scanner is T012's (design "Recovery answer scanner" in
  `.ai/current-plan.md`) and replaces the line-anchored scan and character-count enclosure
  check planned here before. This task builds on T012's `recover_decision` and adds the excerpt, the prompt,
  the docs and the end-to-end run; do not change T012's scanning rules.
- `scripts/lib/workflow.py` `recover_decision` (~1886–1916), after T012:
  1. (T012) whole-text JSON as today; otherwise the bracket-free-prose scan.
  2. (T012) exactly one valid decision → use it; anything else escalates.
  3. Escalation for want of a decision: reason `the recovery session gave no valid decision;
     it wrote: <excerpt>` when the result text is non-empty (excerpt: whitespace collapsed,
     tabs removed, so the total stays within the existing 300-character `clean` cap), else as
     today.
- `templates/.ai/prompts/recover.md` (~24–25): "Your final message is the JSON object alone:
  it starts with `{` and ends with `}`; put your diagnosis into `reason`. Never write a second
  object or an example object."
- `scripts/ai-recover` needs no change (it reads the three tab-separated fields); verify the
  notification shows the excerpt reason.
- `test_recovery_decision_parsing_is_strict` (~4156) passes unchanged (T012 checks it too).
- Docs: README and `docs/workflow.md` (recovery decision format, stating T012's rule: the
  prose around the object may contain no `{`, `}`, `[` or `]`). Vault: update the recovery
  box of `agents-flow.md` only if it describes the answer format (then `updated:` + hub Log
  line); otherwise say "flow unchanged" in the result.

### Likely affected modules
scripts/lib/workflow.py, templates/.ai/prompts/recover.md, tests/test_workflow.py, README.md,
docs/workflow.md

### Acceptance criteria
- Tests named `test_recovery_decision_prose_*` in tests/test_workflow.py (helper
  `recover-decision` on envelopes, as the strict test does); the scanner cases are T012's
  `test_recovery_decision_scan_*`, which must still pass:
  - prose only → `escalate` with reason starting `the recovery session gave no valid decision;
    it wrote:` and containing the start of the prose, no tab inside the reason, ≤ 300 characters;
  - prose with a bracket and no valid decision (e.g. the P3 `Diagnostic: ["]",` reproduction)
    → the same excerpt reason;
  - an end-to-end `ai-recover` run with a mock recovery answer of prose + `rerun` resumes the
    pipeline (an existing MOCK_RECOVER mode extended, e.g. `prose-rerun`).
- `test_recovery_decision_parsing_is_strict`, T012's `test_recovery_decision_scan_*` and all
  other existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k recovery_decision` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T009 — Outcome report: covered Claude reviews leave "Codex catch-up pending" (CU-2)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
`ai-status --outcomes` lists only Claude reviews that still wait for Codex, and the human can
record a catch-up done on another branch.

### Implementation notes
- `scripts/lib/workflow.py` `outcomes_report` (~3050–3055): a Claude review record
  (`reviewer` starting with `claude`) is covered when a LATER record of the same `project`
  and `branch` is (a) a `review` with `reviewer == 'codex'` of the same family (plan covers
  plan; code covers code and recheck), or (b) a `catchup` record. "Later" (plan review P5:
  `now()` has whole seconds, so equal `time` strings happen): order every record by the key
  `(time, file index, line index)` from `read_outcomes` (have it keep each record's position;
  the log is append-only, so line order is write order within a file). A record covers only
  when its `time` is strictly greater, or the `time` is equal and it is in the same file at a
  higher line index; equal times in different files never cover (stays pending: the safe side).
  The section lists only uncovered ones; below it (or instead, when none is pending) a line
  `<n> Claude review(s) covered by a later Codex review or catch-up record.`
- `outcome catchup BRANCH`: appends `{"time", "kind": "catchup", "project", "branch": BRANCH}`
  (project from `project_name()`, `check_state_root` as for other kinds). `scripts/ai-status`:
  `--catch-up-done BRANCH...` → one `outcome catchup` per branch, prints
  `Recorded Codex catch-up for <branch>`; usage text updated. Not on any agent allowlist
  (human command; `.ai/bin/ai-status *` is not allowed there; check).
- README (fallback reviews paragraph ~468–473 and Outcome log ~475–491) and `docs/workflow.md`
  (~857, ~873: the "Claude re-checks still appear" sentence becomes the coverage rule). Flow
  unchanged.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-status, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_outcome_catchup_*` in tests/test_workflow.py (fixture report files as
  `outcome_report_for` builds them, plus one real `ai-status --catch-up-done`):
  - Claude code review at t1, Codex code review at t2 on the same project/branch → not pending,
    `1 Claude review(s) covered`; Codex review at t0 (earlier) → still pending; on another
    branch → still pending; a Codex plan review does not cover a Claude code review;
  - a Claude re-check covered by a later Codex code review; a Claude plan review covered by a
    later Codex plan review;
  - `ai-status --catch-up-done feature/x` appends a `catchup` line (project, branch, time) to
    the host outcomes log; afterwards that branch's earlier Claude reviews are covered and a
    later Claude review on it is pending again;
  - equal timestamps (P5): Claude review and catch-up with the same `time`, catch-up on the
    later line → covered; a Claude review with the same `time` on a line after the catch-up →
    pending; the same pair with equal `time` in two different report files → pending;
  - `test_runner_logs_task_outcomes_and_report` passes unchanged (both its Claude reviews stay
    pending).
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_catchup` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T010 — Docs, handoff and final audit for the batch
Status: TODO
Dependencies: T001, T002, T003, T004, T005, T006, T007, T008, T009, T011, T012, T013
Model: haiku

### Goal
README, `docs/workflow.md`, the vault flow chart and the handoff describe what the code now
does; the human knows which upgrade, vault and backlog steps remain.

### Implementation notes
- Check each sentence the tasks added (README, `docs/workflow.md`) against the code once:
  subreaper and tree termination (T001/T002/T013), `tasks fill-sections` and the host step
  (T003/T004), escaped pipes (T005), prompt wording (T006), `.ai/local/scratch` (T011/T007),
  recovery decision with prose (T012/T008), catch-up coverage and `--catch-up-done` (T009). Fix
  contradictions; no new behaviour.
- Vault: confirm `agents-flow.md` reflects T004 and T007 (and T008 if it changed the chart)
  with a current `updated:`; hub Log has one dated line per flow-changing task. Append one
  hub Log line noting FL-21, CU-1, CU-3 and CU-4 were found already done (2026-10-16). Never
  tick checkboxes.
- `.ai/handoff.md`: "## Flow chart" says `Flow chart updated` (or lists what is pending);
  "Manual testing for the human" (`### Needs you` / `### Covered by automated tests` naming
  every new test group below); "Human todos" kept current.

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, vault agents-flow.md and agents.md (Log)

### Acceptance criteria
- `DocsConsistencyTest` passes; README mentions `.ai/local/scratch`, `--catch-up-done` and the
  self-check's descendant termination; `docs/workflow.md` mentions `tasks fill-sections` and
  the recovery-decision rule.
- `test_pr_body_flow_this_repo_declares_the_flow_chart` passes.
- The handoff names `test_parallel_runner_subreaper_*`, `test_parallel_runner_tree_*`,
  `test_parallel_runner_startup_*`, `test_recovery_decision_scan_*`,
  `test_task_sections_fill_*`, `test_task_sections_host_*`,
  `test_task_sections_prompts_show_the_format`, `test_disposition_pipes_*`,
  `test_scratch_clear_*`, `test_scratch_dir_*`, `test_recovery_decision_prose_*` and `test_outcome_catchup_*` under
  "Covered by automated tests", and every group exists
  (`python3 -m unittest discover -s tests -k <group>` runs ≥ 1 test each).

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
