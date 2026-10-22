# Review dispositions (Claude)

Review HEAD: 93f4920ee543fc919e2d327e13987eb500ccf7f3

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in source: scripts/ai-run runs plan-keeps-done "$since" (line 600) before git commit (line 629); after the commit only ai_guard_verify, the clean-checkout check and revision_scope run, and plan-revisions record is written before them, so a hook that rewrites and stages a DONE block in .ai/tasks.md (an allowed path) is recorded as an accepted revision. plan_stage_verify (scripts/lib/workflow.py:3652) prints committed after records_scope and a clean status only, with no DONE-block check. test_plan_review_followup_revision_keeps_done_blocks covers session edits before the commit only. | T223 |
