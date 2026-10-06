# Plan: Run flow batch 2 (FL-01, FL-07, FL-09)

## Assessment (origin/master 9e11a11, after PR #14)
- `.ai/ci-setup` (template: installs nothing) runs only in GitHub CI
  (`templates/.github/workflows/ai-validate.yml`). It is a protected gate file
  (`ai_guard_digest` roots in scripts/lib/common.sh ~106). No host step installs
  dependencies; the runner may not run `npm ci`, hence the 2026-10-05 23:06 stop.
- `ai-recover` `commit_and_rerun` (~line 159) runs `ai-check` on uncommitted leftovers.
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

## Approach (revised after the Codex plan review P1–P7; FL-03 dropped earlier)
FL-01 was simplified instead of extended: the host installs only at the start of `ai-run`
and before recovery validation, writes nothing tracked (P1), proves the install changed no
project file with a full tree snapshot (P2), does not claim mid-run dependency changes are
handled (P3), covers recovery (P4) and has no "no lockfile" shortcut (P5).
1. T001 (opus) FL-01 helpers: `deps-status`, `deps-record`, `tree-snapshot` in workflow.py;
   template ci-setup comment lines. No caller yet.
2. T002 (opus) FL-01 runner: `ai_deps` in common.sh; ai-run calls it once before its first
   task; end-to-end pipeline test. Flow chart: dependency step.
3. T003 (opus) FL-01 recovery: `commit_and_rerun` installs before `ai-check`; escalates on
   failure. Flow chart: recovery branch.
4. T004 (sonnet) FL-09 runtime: `pr_body` "How to test" split with flagged bullets,
   `finish_summary` counts "Needs you" only. Flow chart: PR/FINISHED.
5. T005 (sonnet) FL-09 guidance: handoff template, prompts, CLAUDE.md/AGENTS.md templates.
6. T006 (sonnet) FL-07: `setup-project --watchdog`, `ai-watchdog --timer-status`, pipeline
   start warning, README waits section, no executable `pgrep -f` waits (docs may explain it),
   vault human-todo entry. Flow chart: setup and start warning.
7. T007 (haiku) final docs audit.

Dependencies: T001 → T002 → T003; T004 → T005; T006 independent; T007 after all six.

## API / data changes
- New helpers: `deps-status` (prints `current` or `stale <reason>`), `deps-record`,
  `tree-snapshot`.
- New files: `.ai/local/deps.json`, `.ai/local/deps-*.log` (ignored, host-written).
- New options: `setup-project --watchdog`, `ai-watchdog --timer-status`; environment
  variable `AI_DEPS_TIMEOUT` (not a config/manifest setting).
- Handoff format: `### Needs you` / `### Covered by automated tests` under "Manual testing
  for the human" (legacy format still accepted).

## Risks
- Running `.ai/ci-setup` on the host executes package-manager code (lifecycle scripts) from
  lockfiles an agent may have changed in a task. Same exposure as CI and the gate, which
  already run project code; documented, not sandboxed.
- `.ai/local/deps.json` is agent-writable: a forged stamp can only skip an install, which
  makes validation fail or pass on the actually installed tree (validation stays the
  authority). Accepted.
- A task that adds a dependency: its in-session gate may fail (sessions can't install); it
  is handled by the existing rules (BLOCKED or a stop), and the next `ai-run` start or
  recovery validation installs. Deliberately not solved in this batch.
- A completed queue validated only by ai-pipeline's `ensure_validated` (no `ai-run` start,
  e.g. a review-only restart in a fresh worktree) does not install; it stops at validation
  as today. Documented limitation.
- Watchdog timers of removed worktrees keep firing (exit 2); out of scope, documented
  (`--uninstall-timer` before removing a worktree).
- The pipeline running this batch uses the frozen `.ai/bin`; new behaviour applies after
  merge/upgrade.

## Choices for Zack (defaults chosen)
- FL-07 timer install is opt-in (`--watchdog`) rather than default, since it writes systemd
  units outside the project; the pipeline warns when missing.
- FL-01 runs only at `ai-run` start and in recovery validation (not before every gate),
  to keep it small; mid-run dependency changes install at the next start.

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; the gate takes ~7 min).
