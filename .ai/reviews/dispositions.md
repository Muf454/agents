# Review dispositions (Claude)

Review HEAD: 5b8d86b759819bc6ae78a18850fdff6d5319fcc2

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in source: `plan_decision_check` is defined at `scripts/ai-pipeline:361` and called only at `:379`, inside `if [[ "$plan_review" == yes ]] && ai_helper tasks untouched` (`:376`). With `--skip-plan-review` (`:36`) or any DONE task the loop is skipped and the implementation loop (`:440`) starts without a decision check; a completed startup plan-revision stage (`:344-351`) is also not followed by a check in that case. Spec R5 explicitly requires the check at "pipeline start, loop entry and `ai-recover`". `plan-revisions decision` keys on the verified report (`workflow.py:2553-2569`), not on task state, so an unconditional check is feasible. Existing needs-human tests only use the plan-review-enabled, untouched-queue path. | T011 |
| M2 | accepted | Confirmed in source: `run_review` captures `start_head` per call (`scripts/ai-review:121`) and `unchanged` compares against it (`:124-125`); `review_with_format_retry` calls `run_review` twice (`:190`, `:199`) with the format check and `ai_notify` in between, so a committed checkout change between the calls becomes the retry's baseline. The code path then publishes against the outer `$head` (`:318`, `:336`) and the plan path against the pre-review `digest` (`:235`, `:259`). Spec R4 / T009 require checkout integrity before the retry; tests only mutate during a reviewer call. | T012 |
| N1 | accepted | Confirmed: `docs/workflow.md:373` says round-three triage is "only reachable with `--max-fix-rounds` ≥ 3", but `scripts/ai-pipeline:479-494` grants a supervised extra round at the default limit 2, exercised by `test_extra_fix_round_falling_counts_get_one_round_then_draft`; the vault `agents-flow.md` Convergence note repeats the restriction. Cheap and in scope (R6). | T013 |
