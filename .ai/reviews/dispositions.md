# Review dispositions (Claude)

Review HEAD: fe6b8f4f664323dc7288f8cf795044b308b62a22

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M3 | accepted | Real. `disputes_store()` (scripts/lib/workflow.py:1147) keys host records by branch hash, while `.ai/reviews/disputes.md` is tracked and inherited. On a new branch `dispute_records()` returns `[]`, so `disputes_values()` (line 1245) requires the file to be absent and fails with "does not match the dispute records"; `disputes_verify` is called by ai-pipeline:143, 327, 348 and by `publish_ready`. The suggested remedy (restore from Git) keeps the mismatch. No test covers an inherited file. | T016 |
| M4 | accepted | Real. `run_manifest start` (workflow.py:778-799) rewrites the single per-checkout `run.json` and carries `stage` over only when the old manifest names the same branch. ai-pipeline:81 gates `complete_stage` on `run-manifest stage` being non-empty, and the clean-tree check at :82 passes when triage already committed its records, so implementation proceeds without the scope/freshness checks and the round goes uncounted. T015's per-branch fix-round store does not hold the stage. No test covers the branch switch. | T017 |
