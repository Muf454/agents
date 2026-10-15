# Review dispositions (Claude)

Review HEAD: e36de5797c8a74888f98eed29e70735e7208fd1d

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M2 | accepted | `scripts/lib/workflow.py` `tasks_reorder`: `queue_segments` emits a `section` segment for every non-task `## ` heading, including ones before the first task; the loop `for segment in segments[:last]` rejects them all, and the rebuild keeps only `segments[0]` (the `pre` segment), so a preamble `## Context` would be dropped even if not rejected. The spec defines the preamble as everything before the first task heading. | T012 |
| N4 | accepted | `scripts/lib/dashboard.py` `REVIEW_HEAD` matches only `Host evidence: HEAD …;`, but `publish_plan_review()` (`workflow.py:2174`) writes `<!-- Plan review of plan digest …; HEAD …; saved …. -->`, so real plan reports always get `head: ''`. `test_dashboard_pr_review_counts_and_heads` uses a code-style header for plan.md. Cheap, in T008 scope. | T013 |
| N5 | accepted | `reviews_of` calls `int()` on `COUNTS` groups (`\d+`, unbounded, `workflow.py:819`) with no exception handling; a >4300-digit count raises `ValueError` out of `inspect()`/`snapshot()`, contradicting T008's "malformed → empty values, never an exception". Cheap, in T008 scope. | T013 |
