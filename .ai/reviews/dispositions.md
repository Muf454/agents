# Review dispositions (Claude)

Review HEAD: 01af1d237ca1c883002dddfda908400784b17036

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in source: `scripts/ai-check` waits up to AI_CHECK_LOCK_WAIT at `flock -w` (line 21), then starts the full `${AI_CHECK_TIMEOUT:-1800}` for `.ai/validate` (line 27) with no deduction; `host_gate` (`scripts/ai-run` ~296) passes remaining as both values, and the final gate (~854–866) does not re-check remaining after host_gate, so a gate can pass up to 900 s past the run deadline. Existing `test_gate_lock_wait_*` tests check wait and refusal only, not a combined deadline. | T044 |
| N1 | accepted | Confirmed: line 16 accepts `^[0-9]{1,5}$` (e.g. 08) and line 19 evaluates `(( wait > 0 ))`, which Bash reads as octal and errors on 08 or 09, so the held-lock branch dies at once. Cheap and in scope. | T045 |
