# Handoff

## What has been implemented?
- T001 (FL-01 helpers, no caller yet): `workflow.py deps-status` / `deps-record` /
  `tree-snapshot`; template `.ai/ci-setup` documents `# ai-deps-inputs:` /
  `# ai-deps-outputs:` and the defaults (still installs nothing).

OR-01/OR-02 were merged via PR #14 (records in Git history).
This branch (`feature/flow-batch-2`, from origin/master 9e11a11) plans FL-01 (host runs
`.ai/ci-setup` when dependencies are missing/stale), FL-07 (watchdog timer at setup, start
warning, PID-based waits) and FL-09 (PR "Needs you" vs "Covered by automated tests"). See
`.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md` (T001–T007, revised after the
Codex plan review: FL-01 simplified, tasks split). Trimmed on
2026-10-06 to high-impact, low-investment work: FL-03 dropped (stays in the backlog). Planned by Claude as Zack's delegate on 2026-10-06; the
pipeline's Codex plan review gates the plan.

## Validation run
Baseline before planning: `.ai/bin/ai-check` (shell syntax + full unittest suite); result
PASS, 188 tests OK (2026-10-06, before planning commit).
After T001: `.ai/bin/ai-check` PASS, 195 tests OK (2026-10-06).

## Assumptions
- FL-07: timer install is opt-in (`setup-project --watchdog`); the pipeline only warns.
- FL-01: ci-setup runs only at the start of `ai-run` and before recovery validation; it
  must only install ignored dependencies (checked by a tree snapshot); mid-run dependency
  changes install at the next start.

## Flow chart
Flow chart updated: not yet for this run (T002, T003, T004 and T006 update the
vault agents-flow.md; T007 replaces this line; a test requires it to start with these words).

## Manual testing for the human

### Needs you
1. Filled in by the tasks (expected: one real run from a fresh worktree to see the
   dependency step and the watchdog warning; read the PR's "How to test" layout).

### Covered by automated tests
- Dependency freshness (declared inputs/outputs, edits, added/removed inputs, ci-setup edit,
  missing output): `test_deps_status_declared_inputs_and_outputs`.
- Default lockfiles + `node_modules`: `test_deps_status_default_lockfiles_and_node_modules`.
- Installer without lockfiles runs once: `test_deps_status_installer_without_lockfiles_runs_once`.
- Paths outside the checkout refused: `test_deps_status_rejects_paths_outside_the_checkout`.
- Tree snapshot (dirty overwrite, mode with `core.filemode=false`, index, commit, untracked;
  ignored dirs and `.ai/local/` not covered): `test_deps_status_tree_snapshot_covers_project_files`.
- Submodule snapshot: `test_deps_status_tree_snapshot_covers_submodules`.
- Template ci-setup: `test_deps_status_template_ci_setup`.
- Further scenarios are added by the remaining tasks.

## Human todos
None.

## Next action
Run the pipeline: `.ai/bin/ai-pipeline --approved --base master --knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`.
