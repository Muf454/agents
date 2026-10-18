# Review dispositions (Claude)

Review HEAD: da84933830d7f33769adfcdd35c9ca276a803006

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in `scripts/ai-pipeline:667-674`: the `is_draft` lookup swallows a failure with an OR-`true` fallback and so leaves `is_draft` empty on a failed lookup, `"$is_draft" != true` then takes the convert branch, and with `pipeline_drafted=yes` it runs `pr-draft record "$url" converted` after `gh pr ready --undo` (a no-op on an already-draft PR in the test mock, `tests/test_workflow.py:672`) and the confirming query. Ownership is then derived from an unknown prior state, and a later clean run's `pr-draft take` un-drafts a human draft, breaking R15. Still converting to draft on an unknown state is fine (fails toward draft); only the record is wrong. | T020 |
| N1 | accepted | Confirmed in `scripts/ai-plan:72-87`: `started` accepts only `state == "active"`; ai-run writes `planning/done` with the same record (`scripts/lib/workflow.py:4594`, `{**record, …}` keeps the pid), so a plan that finishes between two 0.2 s polls reaches the `kill -0` branch, `wait` returns 0 and `exit $(( code > 0 ? code : 1 ))` exits 1 with "ended early (exit 0)". Cheap, in scope (T006's contract), and unresolved plan-review P21. | T021 |
