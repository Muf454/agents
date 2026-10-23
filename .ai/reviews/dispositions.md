# Review dispositions (Claude)

Review HEAD: 68ac201c132afc084763bebc3d4e3cb8219f0964

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M4 | accepted | Confirmed: `scripts/lib/watchdog.py:514-520` calls `start_recovery()` for a due `relaunch_at` schedule with no run-record check; `current_run()` and `stopped_by_human()` run only when `died` (line 530), and a cancelled paused run has no marker. `scripts/ai-recover:107-113` then refuses the stopped record (`stopped_by_human` exits 1) before `limit-claim` (line 164), so the schedule stays due and every later probe relaunches. No test drives the watchdog scheduled path after a cancel. | T329 |
| M5 | accepted | Confirmed: `scripts/lib/common.sh:178` sets `child=running` when `ai_stop_child` gives up after 30 s, but lines 205-230 still run `run-record end ... human_stop`, notify "STOPPED by you", drop the marker and exit. Publication children run through `ai_run_child` with no `timeout` wrapper, so nothing kills a TERM-ignoring git or gh. After that `run_stop` (`scripts/lib/workflow.py:2520-2525`) sees an ended record and exits 3, so the human can no longer reach the survivor. | T330 |
| N4 | accepted | Confirmed: `update_state()` at `scripts/lib/workflow.py:1170` computes `Tasks remaining` as all tasks minus DONE, ignoring `FINISHED = ('DONE', 'SKIPPED')` (line 438). Cheap and in scope (FR-9). | T331 |
