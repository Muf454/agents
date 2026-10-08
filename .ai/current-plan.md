# Plan: outcome telemetry and parallel runner follow-ups (CU-1..CU-4)

Branch `fix/outcome-followups` from `origin/master` c7d4dee, worktree `~/Projects/wt/agents-outcomes`.
Spec: `.ai/project-spec.md` (each item verified against this branch first; CU-4 was mostly fixed).
Revision: 2 (plan review round 1, Claude fallback: P1–P6 accepted, see `.ai/reviews/dispositions.md`).

1. T001 (sonnet, CU-4 residual): `tests/run_parallel.py` sets `PYTHON_COLORS=0` for shards and
   strips ANSI codes before parsing; regression tests with `FORCE_COLOR=3` / `PYTHON_COLORS=1`.
2. T002 (sonnet, CU-1): per-attempt model tables in `outcomes_report`; mixed-model retry test.
3. T003 (sonnet, CU-3): re-check outcome lines carry upheld/withdrawn totals by severity and
   the reviewed HEAD; re-check table in the report.
4. T004 (opus, CU-2): Codex code review lines record `base` and `covers` (from
   `.ai/reviews/fallback-log.md`, via a pure helper `catchup_covers` that judges each log row
   on its own and tests ancestry by exit code); report drops covered Claude reviews from "pending";
   `fallback_record` inserts rows into the table. Opus because a wrong coverage rule would
   hide Claude-only work that still needs a Codex review. Updates the vault flow note.

Order: T001 is independent; T002 → T003 → T004 are chained because all three edit
`outcomes_report` (T004 also needs T003's `reviewed_head` to match re-check rows).

Telemetry only: no change to `ai-review`, `ai-pipeline`, `ai-recover`, `ai-run`, gates or
review flow. Flow chart: T004 updates the outcome-log / catch-up text in `agents-flow.md`
(PR says "Flow chart updated"); T001–T003 leave the flow unchanged.

## Expected overlap with concurrent PRs
PR #21 (`feature/supervisor`) and PR #22 (`fix/robustness-batch`) edit `scripts/ai-pipeline`,
`scripts/ai-review`, `scripts/ai-recover`, `scripts/lib/workflow.py`, `tests/test_workflow.py`.
This batch touches none of the three scripts. In `workflow.py` it edits only `fallback_record`,
`outcome` and `outcomes_report` (around lines 1960–2135) and may add small helpers next to them;
in `tests/test_workflow.py` it adds new test methods (outcome section near
`test_runner_logs_task_outcomes_and_report`, `ParallelRunnerTest`) and changes one existing
assertion (the "Tasks by model" row in `test_runner_logs_task_outcomes_and_report`). Expect
textual conflicts only if those PRs also touch these functions; resolve by keeping both sides.
