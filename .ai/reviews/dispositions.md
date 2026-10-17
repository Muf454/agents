# Review dispositions (Claude)

Review HEAD: 31fb005a6b08a276d38f68b3a2b5d8235c25f123

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M3 | accepted | Confirmed in source: `process_table()` (`tests/run_parallel.py:216-221`) catches the `OSError` of `os.listdir('/proc')` and returns `{}`; `Dispatcher.scan()` (390) only maps a raised exception to None, so the kill rounds (`live == {}` → break) and the completion barrier (`live == {}` → return) accept an empty tree without `cleanup_failed`. T014's test patches `descendants()`, above this handler. `reap_adopted()` also calls `children_of()` unguarded, so simply re-raising needs a guard there too. | T017 |
| N2 | accepted | `.ai/handoff.md` "Next action" said T015/T016 TODO while both are DONE (`bd4a419`, `85c4cb2`). Workflow record only: corrected in this triage commit; T017 refreshes it again when done. | T017 |
