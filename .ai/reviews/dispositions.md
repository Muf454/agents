# Review dispositions (Claude)

Review HEAD: 5c73c56d55b8e9b4548855151255aa67e19f62b3

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M2 | accepted | Confirmed in `scripts/ai-check` lines 22–33: when `flock -w "$limit" 8` fails the waiter calls `out_of_time`, which runs `ai_helper stamp invalidate` without holding the lock. `stamp invalidate` (`scripts/lib/workflow.py` ~760) rewrites `before` with the current fingerprint, and the holder's `stamp record` then compares against it, so a mid-run content change can record PASS with `unchanged: true`. `test_gate_lock_wait_exhausts_the_timeout_while_waiting` has no active stamp, so it misses this. Before T044 the wait-failure path used `ai_die` and never touched the stamp; T046 restores that for the timeout exit and adds concurrent-stamp regressions. | T046 |
| N2 | accepted | `.ai/handoff.md` listed T045 as TODO and its next action as T045, but `.ai/bin/ai-task show T045` is DONE (tests in 5d94082). Fixed in this triage commit: T045 is DONE with its validation line and test names, and the next action is T046. T046 keeps the handoff current. | T046 |
