# Plan: outcome telemetry and parallel runner follow-ups (CU-1, CU-3, CU-4; CU-2 deferred)

Branch `fix/outcome-followups` from `origin/master` c7d4dee, worktree `~/Projects/wt/agents-outcomes`.
Spec: `.ai/project-spec.md` (each item verified against this branch first; CU-4 was mostly fixed).
Revision: 4 (plan review round 3, Claude fallback: CU-2/T004 dropped by the convergence rule, P2
accepted; rounds 1–3 dispositions in `.ai/reviews/dispositions.md`).

1. T001 (sonnet, CU-4 residual): `tests/run_parallel.py` sets `PYTHON_COLORS=0` for shards and
   strips ANSI codes before parsing; regression tests with `FORCE_COLOR=3` / `PYTHON_COLORS=1`.
2. T002 (sonnet, CU-1): per-attempt model tables in `outcomes_report`; mixed-model retry test.
3. T003 (sonnet, CU-3): re-check outcome lines carry upheld/withdrawn totals by severity and
   the reviewed HEAD; re-check table in the report.

Order: T001 is independent; T002 → T003 are chained because both edit `outcomes_report`.

Telemetry only: no change to `ai-review`, `ai-pipeline`, `ai-recover`, `ai-run`, gates or
review flow. Flow unchanged (PR says "Flow unchanged").

## Deferred: CU-2 (Codex catch-up coverage, was T004)
Dropped from this batch after plan review round 3. Rounds 1, 2 and 3 each found a MAJOR or
MINOR in the same coverage rule (row isolation and parsing; then merged-master and re-check
pairing; then the merged-master case again), and the report section is advisory telemetry, so
the convergence rule applies: stop patching it here. The hand-written `## Codex catch-up`
section in `.ai/reviews/fallback-log.md` stays the record of which Claude reviews a Codex
review has covered, and `ai-status --outcomes` keeps listing every Claude review under
"Codex catch-up pending", as today.

Open design question for a later batch: when does a Codex catch-up review cover a Claude
fallback review across merges? The candidate rules so far: (a) X ≤ H and B ≤ R (sound, but
leaves reviews pending forever once master is merged into the branch, which this project does,
`.ai/run-log.md:108`); (b) exact containment, X ≤ H and `rev-list --count R..X` equal to
`rev-list --count R..X ^B` (handles the merged-master case; not yet reviewed). Still open
alongside it: rebased branches (X no longer in H's history), whether a re-check row inherits
its parent code row's base, what the coverage section counts (log rows or matched outcome
lines), and vault access for the flow-note update in an unattended run. The
`fallback_record` row-placement defect (new rows land below a later section) moves with CU-2.

## Expected overlap with concurrent PRs
PR #21 (`feature/supervisor`) and PR #22 (`fix/robustness-batch`) edit `scripts/ai-pipeline`,
`scripts/ai-review`, `scripts/ai-recover`, `scripts/lib/workflow.py`, `tests/test_workflow.py`.
This batch touches none of the three scripts. In `workflow.py` it edits only `outcome` and
`outcomes_report` (around lines 2040–2135) and may add small helpers next to them;
in `tests/test_workflow.py` it adds new test methods (outcome section near
`test_runner_logs_task_outcomes_and_report`, `ParallelRunnerTest`) and changes one existing
assertion (the "Tasks by model" row in `test_runner_logs_task_outcomes_and_report`). Expect
textual conflicts only if those PRs also touch these functions; resolve by keeping both sides.
