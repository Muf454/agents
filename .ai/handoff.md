# Handoff

## What has been implemented?
Branch `fix/outcome-followups` (from `origin/master` c7d4dee): outcome telemetry and parallel test runner follow-ups CU-1, CU-3 and CU-4 from the vault backlog. Planned (revision 4), nothing implemented yet.
- T001 (CU-4, TODO): parallel runner shards ignore `PYTHON_COLORS`/`FORCE_COLOR`; ANSI-safe summary parsing. The `FORCE_COLOR` case itself was already fixed on `fix/catchup-review` (T006); this adds the `PYTHON_COLORS=1` case and regression tests.
- T002 (CU-1, TODO): `ai-status --outcomes` model tables per attempt.
- T003 (CU-3, TODO): re-check outcome lines carry upheld/withdrawn totals by severity and the reviewed HEAD; re-check table in the report.

Telemetry only: `ai-review`, `ai-pipeline`, `ai-recover`, `ai-run` and the gates are unchanged.

### Deferred: CU-2 (Codex catch-up coverage, was T004)
Dropped from this batch after plan review round 3 by the convergence rule: rounds 1, 2 and 3 each found problems in the same coverage rule, and the result is advisory telemetry. The hand-written `## Codex catch-up` section in `.ai/reviews/fallback-log.md` stays the record, and `ai-status --outcomes` keeps listing every Claude review as "Codex catch-up pending". Open design question: when does a Codex catch-up review cover a Claude fallback review across merges (master merged into the branch, rebases, a re-check's parent range)? Candidate rules and sub-questions: `.ai/current-plan.md` "Deferred: CU-2". The `fallback_record` row-placement defect (new rows land below the `## Codex catch-up` section) moves with it. Dispositions: `.ai/reviews/dispositions.md`, plan review rounds 2 and 3 (deferred rows).

## Flow chart
Flow unchanged

## Manual testing for the human
### Needs you
1. After merge, run `.ai/bin/ai-status --outcomes` on the host (after `setup-project --upgrade` installs the new copy) and check the report reads sensibly on real data: "Attempts by model" rows and "Re-checks by reviewer" (re-checks from before this change count with zero totals). "Codex catch-up pending" still lists every Claude review (CU-2 deferred).
2. Approve `setup-project --upgrade --apply` for the projects that should get the new report (agents, raid-planner, family-planner).

### Covered by automated tests
- Parallel runner with `FORCE_COLOR=3` / `PYTHON_COLORS=1`, ANSI-safe summary parsing, no escapes in a failing shard's output: `test_parallel_runner_*` (T001)
- Per-attempt model statistics with a mixed-model retry and old attempt-less lines: `test_outcome_report_*` (T002)
- Re-check upheld/withdrawn totals and `reviewed_head`, line still written when the report cannot be verified: `test_outcome_recheck_*` (T003)

## Human todos
- Keep CU-2 open in the vault backlog (`agents-backlog.md`) with the deferral reason and the open design question above, plus the `fallback_record` row-placement defect; a later batch should be started with `ai-run --knowledge-dir ~/zWiki/zWiki` if it edits the flow note (round 3 P4).

## Next action
Implement T001.
