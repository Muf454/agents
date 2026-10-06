# Plan: Run flow batch 2 (FL-01, FL-03, FL-07, FL-09)

## Assessment (origin/master 9e11a11, after PR #14)
- `.ai/ci-setup` (template: installs nothing) runs only in GitHub CI
  (`templates/.github/workflows/ai-validate.yml`). It is a protected gate file
  (`ai_guard_digest` roots in scripts/lib/common.sh ~106). No host step installs
  dependencies; the runner may not run `npm ci`, hence the 2026-10-05 23:06 stop.
- `ai-run` (scripts/ai-run) loop: `ai_guard_verify` → `tasks next` → session → post-task
  `ai-check`; final `ai-check` when the queue is complete. `ai-pipeline`'s
  `ensure_validated` (~line 190) runs `ai-check` before review and publication.
- Triage: `ai-run --triage` builds the TRIAGE CONTRACT prompt; `triage_check`
  (scripts/lib/workflow.py ~732) validates dispositions (`DISPOSITION_ROW`); `finding_ids`
  (~685) and `finding_text` (~1362) parse reports; host bindings `<head>.sha256` in
  `binding_dir()` verify each published report. Each review is committed by the host as
  `chore(ai): record independent review` (`.ai/reviews/current.md`), so the branch history
  holds every report; `AI_DISPUTES_BASE` (exported by ai-pipeline) is the base sha.
- With the default `--max-fix-rounds 2` a single run has at most 3 reviews, so a
  3-in-a-row rule fires on the third review (shown in the PR) and in later rounds or restarts
  (fix rounds are counted per branch across runs).
- Watchdog: `ai-watchdog --install-timer` exists (scripts/lib/watchdog.py `timer()`);
  setup-project never installs it; nothing tells the coordinator when a checkout (e.g. a
  new worktree) has no timer. `grep -rn pgrep scripts docs templates README.md` finds
  nothing: the self-matching waits were coordinator shell loops, so FL-07's wait part is
  documentation plus a regression test.
- PR body (`pr_body`, ~1647) copies the handoff's "Manual testing for the human" verbatim;
  `finish_summary` (~1491) counts every bullet there as a manual step.
- Tests: `tests/test_workflow.py`, 188 tests (unittest, mock claude/codex/gh/systemctl).

## Approach
1. T001 (opus) FL-01 host dependency step: helpers `deps-status` / `deps-record` in
   workflow.py; `ai_deps` in common.sh (run ci-setup with timeout, log, gate and tree checks,
   stamp); called by ai-run before each task session and before host `ai-check`, by
   ai-pipeline in `ensure_validated`. `AI_DEPS_TIMEOUT` joins the config keys and
   `RUN_SETTINGS`. Flow chart: dependency step before the first task.
2. T002 (sonnet) FL-01 template and setup: `templates/.ai/ci-setup` documents the
   declaration lines (comments only, still installs nothing by default); validation
   candidates suggest a ci-setup command and declarations per detected ecosystem; README.
3. T003 (sonnet) FL-03 review history: helper `review-history` (verified reports on the
   branch, BLOCKER/MAJOR findings, file areas) and `recurring-areas`; the PR body lists
   recurring areas.
4. T004 (opus) FL-03 triage rule: CONVERGENCE section in the triage prompt, `triage-check
   --fresh` enforcement (Design note + `Model: opus`), triage/fix-review prompt text. Flow
   chart: convergence rule in the triage step.
5. T005 (sonnet) FL-09: handoff subsections, `pr_body` "How to test" split with flagged
   bullets, `finish_summary` counts "Needs you" only, prompts and templates. Flow chart:
   PR "How to test" and the FINISHED todo list.
6. T006 (sonnet) FL-07: `setup-project --watchdog`, `ai-watchdog --timer-status`, pipeline
   start warning, README waits section, no-`pgrep -f` test, a vault human-todo entry for
   existing checkouts. Flow chart: watchdog at setup and the start warning.
7. T007 (haiku) final docs audit: README, docs/workflow.md, vault chart consistency, hub
   Log, handoff flow-chart line and manual testing in the new two-part format.

Dependencies: T001 → T002; T003 → T004; T005, T006 independent; T007 after all.

## API / data changes
- New helpers: `deps-status` (prints `current` or `stale <reason>`), `deps-record`,
  `review-history`, `recurring-areas` (`area<TAB>reviews<TAB>finding ids`).
- New files: `.ai/local/deps.json`, `.ai/local/deps-*.log` (ignored, host-written).
- New options: `setup-project --watchdog`, `ai-watchdog --timer-status`; setting
  `AI_DEPS_TIMEOUT`.
- Handoff format: `### Needs you` / `### Covered by automated tests` under "Manual testing
  for the human" (legacy format still accepted).
- Task format: optional `### Design note` section (required only by the convergence rule).

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
- Area detection by file path can miss findings that name only symbols or directories, and
  over-match a hub file. Threshold and granularity are choices for Zack (below).
- Watchdog timers of removed worktrees keep firing (exit 2); out of scope, documented
  (`--uninstall-timer` before removing a worktree).
- The pipeline running this batch uses the frozen `.ai/bin`; new behaviour applies after
  merge/upgrade.

## Choices for Zack (defaults chosen)
- FL-03 threshold 3 reviews, area = file path (not directory/module).
- FL-07 timer install is opt-in (`--watchdog`) rather than default, since it writes systemd
  units outside the project; the pipeline warns when missing.
- FL-01 also runs before every host gate, not only before the first task, so a lockfile
  change by a task is installed before validation.

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; the gate takes ~7 min).
