# Handoff

## What has been implemented?
- T001 (FL-01 helpers, no caller yet): `workflow.py deps-status` / `deps-record` /
  `tree-snapshot`; template `.ai/ci-setup` documents `# ai-deps-inputs:` /
  `# ai-deps-outputs:` and the defaults (still installs nothing).
- T002 (FL-01 runner): `ai-run` runs `.ai/ci-setup` on the host before its first task when
  `deps-status` is stale (`ai_deps` in common.sh; `AI_DEPS_TIMEOUT`, default 1200 s, capped
  by the run time; log `.ai/local/deps-*.log`). Gate and tree snapshot must be unchanged
  after every installer exit, else "Dependency setup changed project files"; `ai-recover`
  always escalates "Dependency setup" stops.
- T003 (FL-01 recovery): `ai-recover`'s `commit_and_rerun` runs the same dependency step
  on the dirty tree before `ai-check`; a failed or file-changing install escalates
  "dependency setup failed: …" with no commit and no resume.
- T004 (FL-09 runtime): `workflow.py manual_testing(handoff)` splits the section into
  `### Needs you` / `### Covered by automated tests` (no subsections = legacy, unchanged).
  `pr-body` renders Needs you first ("None — everything below is automated." when empty) and
  the automated list in `<details>` with its count (bullets without a backticked test name
  get "⚠ no test named"); `finish-summary` counts only Needs-you steps or says "Nothing to
  test by hand (N automated checks in the PR)". Vault flow chart updated.

- T008 (review M1): `tree_snapshot` walks an uninitialised submodule directory on the
  filesystem (path, kind, mode, bytes or link target; no ignore rules; symlinks never
  followed) and records a symlink/file at a gitlink path as such, so installer writes there
  are caught.

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
After T002: `.ai/bin/ai-check` PASS, 202 tests OK (2026-10-06), but it took 579 s: the
suite is close to the 600 s Bash tool limit sessions use for the gate.
After T003: `.ai/bin/ai-check` PASS, 205 tests OK (2026-10-06, 555 s).
After T004: `.ai/bin/ai-check` PASS, 209 tests OK (2026-10-06, 564 s).
After T008: `.ai/bin/ai-check` PASS, 224 tests OK (2026-10-07, 611 s): now over the 600 s
Bash tool limit, so sessions see the gate moved to the background before it finishes.

## Assumptions
- FL-07: timer install is opt-in (`setup-project --watchdog`); the pipeline only warns.
- FL-01: ci-setup runs only at the start of `ai-run` and before recovery validation; it
  must only install ignored dependencies (checked by a tree snapshot); mid-run dependency
  changes install at the next start.

## Flow chart
Flow chart updated: T001–T006 on 2026-10-06 added the dependency step (node, ⛔ stop, note, recovery hard rule),
recovery installs dependencies before validating leftovers, "Needs you" vs "Covered by automated tests" split in PR,
and watchdog timer (status check, setup option, start warning).

## Manual testing for the human

### Needs you
1. Fresh worktree dependency step: in a real npm project with this toolkit installed,
   create a new worktree (no `node_modules`), add `# ai-deps-inputs: package-lock.json`,
   `# ai-deps-outputs: node_modules` and `npm ci` to `.ai/ci-setup`, commit, and run
   `.ai/bin/ai-pipeline --approved`. Expected: before the first task the terminal shows
   "Dependency setup (.ai/ci-setup): no dependency stamp …" then "Dependencies installed in
   Ns (log .ai/local/deps-….log)"; `.ai/local/deps.json` exists; `git status` stays clean.
   A second run with an unchanged lockfile shows no dependency step.
2. Watchdog warning on a real checkout: in a worktree without a timer, start
   `.ai/bin/ai-pipeline --approved`. Expected: "No watchdog timer for this checkout; …" on
   screen and "(no watchdog timer for this checkout)" in the phone STARTED notification.
   Then `.ai/bin/ai-watchdog --install-timer --diagnose --recover`, run
   `.ai/bin/ai-watchdog --timer-status` (expect `installed …`), and start again: no warning.

### Covered by automated tests
- Dependency freshness (declared inputs/outputs, edits, added/removed inputs, ci-setup edit,
  missing output): `test_deps_status_declared_inputs_and_outputs`.
- Default lockfiles + `node_modules`: `test_deps_status_default_lockfiles_and_node_modules`.
- Installer without lockfiles runs once: `test_deps_status_installer_without_lockfiles_runs_once`.
- Paths outside the checkout refused: `test_deps_status_rejects_paths_outside_the_checkout`.
- Tree snapshot (dirty overwrite, mode with `core.filemode=false`, index, commit, untracked;
  ignored dirs and `.ai/local/` not covered): `test_deps_status_tree_snapshot_covers_project_files`.
- Submodule snapshot: `test_deps_status_tree_snapshot_covers_submodules`.
- Uninitialised submodule path (file created, overwritten, chmod, nested dir/symlink, dir
  mode, replaced by symlink/file, removed; untouched = equal):
  `test_tree_snapshot_uninitialised_submodule`; installer writing into it (exit 0 and 1)
  stops with no stamp: `test_deps_runner_installer_writing_into_uninitialised_submodule_stops`.
- Template ci-setup: `test_deps_status_template_ci_setup`.
- Host install before the first task, once; reinstall after a lockfile change:
  `test_deps_runner_installs_once_before_the_first_task`.
- Installer fails, times out, overwrites/creates/commits a project file (also with exit 1):
  stop before Claude, no stamp: `test_deps_runner_failed_or_changing_installer_stops_before_claude`.
- Run-time cap and invalid `AI_DEPS_TIMEOUT`: `test_deps_runner_install_is_capped_by_the_run_time`.
- Complete queue installs nothing: `test_deps_runner_complete_queue_installs_nothing`.
- Auto-recovery escalates dependency stops without a recovery session or commit:
  `test_deps_runner_failed_install_escalates_without_recovery`,
  `test_deps_runner_changing_install_escalates_without_recovery`.
- Pipeline end to end with install, PR and clean tree: `test_deps_runner_pipeline_end_to_end`.
- Recovery installs dependencies before validating leftover work that changed a lockfile,
  then commits and resumes: `test_deps_recovery_installs_before_the_gate_and_resumes`;
  a failing or file-changing install escalates with no commit:
  `test_deps_recovery_failed_install_escalates_without_a_commit`,
  `test_deps_recovery_changing_install_escalates_without_a_commit`.
- Watchdog timer (T006): `--timer-status` missing/installed/partial/stopped/unknown, setup
  `--watchdog` (files + units, rejected with `--dry-run`/`--upgrade`, failing systemctl),
  plain setup's "Next" line, pipeline start warning and notification note (missing, stopped,
  unknown, recovery resume, quiet when installed), no `pgrep -f` waits and README PID example:
  `test_watchdog_setup_*` (11 tests in `tests/test_workflow.py`).
- Further scenarios are added by the remaining tasks.

## Human todos
None.

## Next action
Run the pipeline: `.ai/bin/ai-pipeline --approved --base master --knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`.
