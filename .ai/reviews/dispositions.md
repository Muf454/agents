# Review dispositions (Claude)

Review HEAD: c9d092bf5eab8ad3c4398292651afc5fd784f77c

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M3 | accepted | Confirmed in source: `tests/run_parallel.py:192` starts each batch with `subprocess.Popen(...)` without `start_new_session`/process group; `stop()` (:224–234) calls `terminate()`/`kill()` only on that direct child; `run_batch` blocks in `communicate()` (:197) until EOF, which a surviving grandchild holding the inherited stdout pipe never sends; `run()` then joins threads without a bound (:242–247). Many suite tests spawn fixture pipelines (`ai-run`, git, mock agents), so descendants are realistic. T004 required terminating running batches and joining every worker on interrupt/worker error. | T014 |
| N6 | accepted | Confirmed: `queue_segments()` gates on the literal `line.startswith('## ')` (`scripts/lib/workflow.py:477`) while `task_blocks()` uses `^##\s+` (:409), so a `##<TAB>T001 — …` heading is a task to the validator but not a segment; `tasks_reorder()` then does `by_id[task_id]` (:539) → `KeyError` traceback. Cheap, in scope (T001 required the same heading/fence rules). | T015 |
