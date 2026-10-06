# Plan: Run flow batch 2 (FL-01, FL-07, FL-09)

## Assessment (origin/master 9e11a11, after PR #14)
- `.ai/ci-setup` (template: installs nothing) runs only in GitHub CI
  (`templates/.github/workflows/ai-validate.yml`). It is a protected gate file
  (`ai_guard_digest` roots in scripts/lib/common.sh ~106). No host step installs
  dependencies; the runner may not run `npm ci`, hence the 2026-10-05 23:06 stop.
- `ai-run` (scripts/ai-run) loop: `ai_guard_verify` → `tasks next` → session → post-task
  `ai-check`; final `ai-check` when the queue is complete. `ai-pipeline`'s
  `ensure_validated` (~line 190) runs `ai-check` before review and publication.
- Watchdog: `ai-watchdog --install-timer` exists (scripts/lib/watchdog.py `timer()`);
  setup-project never installs it; nothing tells the coordinator when a checkout (e.g. a
  new worktree) has no timer. `grep -rn pgrep scripts docs templates README.md` finds
  nothing: the self-matching waits were coordinator shell loops, so FL-07's wait part is
  documentation plus a regression test.
- PR body (`pr_body`, ~1647) copies the handoff's "Manual testing for the human" verbatim;
  `finish_summary` (~1491) counts every bullet there as a manual step.
- FL-03 (convergence) is out of this batch (stays in the backlog, not started).
- Tests: `tests/test_workflow.py`, 188 tests (unittest, mock claude/codex/gh/systemctl).

## Approach (trimmed 2026-10-06: FL-03 dropped, stays in the backlog)
1. T001 (opus) FL-01 host dependency step: helpers `deps-status` / `deps-record` in
   workflow.py; `ai_deps` in common.sh (run ci-setup with timeout, log, gate and tree checks,
   stamp); called by ai-run before each task session and before host `ai-check`, by
   ai-pipeline in `ensure_validated`. `AI_DEPS_TIMEOUT` joins the config keys and
   `RUN_SETTINGS`. Template ci-setup gains comment lines only (declarations, npm example).
   Flow chart: dependency step before each task and the checks.
2. T002 (sonnet) FL-09: handoff subsections, `pr_body` "How to test" split with flagged
   bullets, `finish_summary` counts "Needs you" only, prompts and templates. Flow chart:
   PR "How to test" and the FINISHED todo list.
3. T003 (sonnet) FL-07: `setup-project --watchdog`, `ai-watchdog --timer-status`, pipeline
   start warning, README waits section, no-`pgrep -f` test, a vault human-todo entry for
   existing checkouts. Flow chart: watchdog at setup and the start warning.
4. T004 (haiku) final docs audit: README, docs/workflow.md, vault chart consistency, hub
   Log, handoff flow-chart line and manual testing in the new two-part format.

Dependencies: T001, T002, T003 independent; T004 after all.

## API / data changes
- New helpers: `deps-status` (prints `current` or `stale <reason>`), `deps-record`.
- New files: `.ai/local/deps.json`, `.ai/local/deps-*.log` (ignored, host-written).
- New options: `setup-project --watchdog`, `ai-watchdog --timer-status`; setting
  `AI_DEPS_TIMEOUT`.
- Handoff format: `### Needs you` / `### Covered by automated tests` under "Manual testing
  for the human" (legacy format still accepted).

## Risks
- Running `.ai/ci-setup` on the host executes package-manager code (lifecycle scripts) from
  lockfiles an agent may have changed in a task. Same exposure as CI and the gate, which
  already run project code; documented, not sandboxed.
- `.ai/local/deps.json` is agent-writable: a forged stamp can only skip an install, which
  makes validation fail or pass on the actually installed tree (validation stays the
  authority). Accepted.
- A task that adds a dependency: the agent's own in-session `ai-check` may fail because it
  can't install; the host installs before its post-task gate. The runner prompt tells the
  agent to note it and rely on the host gate (task stays DONE only if the host gate passes).
- Watchdog timers of removed worktrees keep firing (exit 2); out of scope, documented
  (`--uninstall-timer` before removing a worktree).
- The pipeline running this batch uses the frozen `.ai/bin`; new behaviour applies after
  merge/upgrade.

## Choices for Zack (defaults chosen)
- FL-07 timer install is opt-in (`--watchdog`) rather than default, since it writes systemd
  units outside the project; the pipeline warns when missing.
- FL-01 also runs before every host gate, not only before the first task, so a lockfile
  change by a task is installed before validation.

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; the gate takes ~7 min).
