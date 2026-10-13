# Review dispositions (Claude)

Review HEAD: e8eb6c8c561a47656b740c91f8609ef24783efbf

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed: `plan_keeps_done` (scripts/lib/workflow.py:2510) builds its DONE set only from `git show START:.ai/tasks.md` and returns early when that has no DONE task; `scripts/ai-run:130` calls it with HEAD and `:311` with `$since`, so a DONE task present only in the uncommitted working-tree queue at session entry (planning allows uncommitted records) can be dropped without a stop. Existing `test_plan_keeps_done_*` commit their baseline first. | T012 |
| N1 | accepted | Confirmed: scripts/lib/watchdog.py:447 sets `stall_seen = previous.get('stall_seen_ns', now)`; a legacy record with `active: ["stalled"]` and no `stall_seen_ns` gets no `stalled` incident on the first upgraded probe (record `active` becomes []), so the confirming probe sees it as fresh and re-notifies/diagnoses. Cheap, in scope (FL-21 dedupe compatibility). | T013 |
