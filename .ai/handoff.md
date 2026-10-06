# Handoff

## What has been implemented?
Nothing yet for this run. OR-01/OR-02 were merged via PR #14 (records in Git history).
This branch (`feature/flow-batch-2`, from origin/master 9e11a11) plans FL-01 (host runs
`.ai/ci-setup` when dependencies are missing/stale), FL-03 (review convergence rule), FL-07
(watchdog timer at setup, start warning, PID-based waits) and FL-09 (PR "Needs you" vs
"Covered by automated tests"). See `.ai/project-spec.md`, `.ai/current-plan.md`,
`.ai/tasks.md` (T001–T007). Planned by Claude as Zack's delegate on 2026-10-06; the
pipeline's Codex plan review gates the plan.

## Validation run
Baseline before planning: `.ai/bin/ai-check` (shell syntax + full unittest suite); result
PASS, 188 tests OK (2026-10-06, before planning commit).

## Assumptions
- FL-03: threshold 3 consecutive verified reviews; area = tracked file path named in a
  BLOCKER/MAJOR finding; off without `AI_DISPUTES_BASE` (standalone ai-run).
- FL-07: timer install is opt-in (`setup-project --watchdog`); the pipeline only warns.
- FL-01: ci-setup also runs before every host gate when inputs changed (a task may change a
  lockfile); it must only install ignored dependencies.

## Flow chart
Flow chart updated: not yet for this run (T001, T004, T005 and T006 update the vault
agents-flow.md; T007 replaces this line; a test requires it to start with these words).

## Manual testing for the human

### Needs you
1. Filled in by the tasks (expected: one real run from a fresh worktree to see the
   dependency step and the watchdog warning; read the PR's "How to test" layout).

### Covered by automated tests
- Filled in by the tasks, one bullet per scenario with its test name.

## Human todos
None.

## Next action
Run the pipeline: `.ai/bin/ai-pipeline --approved --base master --knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`.
