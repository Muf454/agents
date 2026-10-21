# Review dispositions (Claude)

Review HEAD: e96e1cedfd45b4e0591f21f01d50fcea897e548a

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in source: main() in tests/run_parallel.py calls collect(start_dir) at :637, which does in-process unittest discovery and imports the test modules. Those import tests/isolation.py, which rewrites os.environ AI_STATE_DIR and XDG_STATE_HOME at :18-22. real_registry() at :654 then reads os.environ (:135), so it gets the temp registry. The existing test calls registry_problem() directly and cannot catch the ordering. | T113 |
| M2 | accepted | Confirmed: tasks_preflight in scripts/lib/workflow.py computes moved, but it prints queue-order lines only for tasks with a late dependency. ai_queue_ruling in scripts/lib/common.sh claims only the IDs on those lines. So prerequisites and intervening tasks move unclaimed, contrary to A2 ("one claim per moved task"). | T114 |
| N1 | accepted | Confirmed: in scripts/ai-review, the routed branch calls claude_model, which uses review-risk. review_risk in workflow.py scans every task, DONE ones included, so an earlier opus task or risky title selects claude-fable-5-1. A12 and the spec's R6 text specify opus. Cheap and in scope. | T115 |
