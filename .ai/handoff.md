# Handoff

## What has been implemented?
Branch `fix/outcome-followups` (from `origin/master` c7d4dee): outcome telemetry and parallel test runner follow-ups CU-1..CU-4 from the vault backlog. Planned, nothing implemented yet.
- T001 (CU-4, TODO): parallel runner shards ignore `PYTHON_COLORS`/`FORCE_COLOR`; ANSI-safe summary parsing. The `FORCE_COLOR` case itself was already fixed on `fix/catchup-review` (T006); this adds the `PYTHON_COLORS=1` case and regression tests.
- T002 (CU-1, TODO): `ai-status --outcomes` model tables per attempt.
- T003 (CU-3, TODO): re-check outcome lines carry upheld/withdrawn totals by severity and the reviewed HEAD; re-check table in the report.
- T004 (CU-2, TODO): Codex code review outcome lines record `base` and the Claude fallback reviews they cover (from `.ai/reviews/fallback-log.md`); the report lists only uncovered ones as "Codex catch-up pending"; fallback rows are inserted into the log's table.

Telemetry only: `ai-review`, `ai-pipeline`, `ai-recover`, `ai-run` and the gates are unchanged.

## Flow chart
Flow chart updated (T004: outcome log and catch-up text in `agents-flow.md`)

## Manual testing for the human
### Needs you
1. After merge, run `.ai/bin/ai-status --outcomes` on the host (after `setup-project --upgrade` installs the new copy) and check the report reads sensibly on real data: "Attempts by model" rows, "Re-checks by reviewer", and which Claude reviews are still "Codex catch-up pending". Reviews from before this change (including those the 2026-10-07 hand-run catch-up covered) stay listed as pending by design.
2. Approve `setup-project --upgrade --apply` for the projects that should get the new report (agents, raid-planner, family-planner).

### Covered by automated tests
- Parallel runner with `FORCE_COLOR=3` / `PYTHON_COLORS=1`, ANSI-safe summary parsing: `test_parallel_runner_*` (T001)
- Per-attempt model statistics with a mixed-model retry and old attempt-less lines: `test_outcome_report_*` (T002)
- Re-check upheld/withdrawn totals and `reviewed_head`, line still written when the report cannot be verified: `test_outcome_recheck_*` (T003)
- Catch-up coverage: the rule as a unit test on one mixed log (covered, merged-branch row with an older base, later base, other branch, plan row, unknown HEAD/base, escaped `\|`, a `plan` ref), one end-to-end Claude-then-Codex run, missing log / missing header, cross-project report; fallback row placement: `test_outcome_catchup_*`, `test_fallback_record_*` (T004)

## Human todos
None.

## Next action
Implement T001.
