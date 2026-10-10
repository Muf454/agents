# Handoff

## What has been implemented?
Nothing yet. Branch `fix/night-stops` (from master 744827a, after the dashboard #25) plans
the night-stop fixes and the plan stage (2026-10-09, Claude planning session):
- T001 FL-18: `ai-task check`; the pipeline validates the queue before the plan review and
  stops with the queue error (ai-recover escalates it).
- T002 FL-19: default session budget `max(16, unfinished tasks + 2)`.
- T003 FL-19: a relaunch rejected by the checkout lock names the owner (auto-recovery or a
  pipeline, with its PID) and no longer overwrites `last-error`.
- T004 FL-21: watchdog timer `OnActiveSec=2min` (no immediate probe after install) and a
  confirmed `stalled` incident (second sighting ≥ 5 min later); planning is never stalled.
- T005 FL-22: `Bash(chmod +x *)` in the runner permission TEMPLATE and a runner prompt rule.
- T006–T008 DB-04: `ai-run --plan PROMPT_FILE [--model M] [--revision]` (headless planning
  session, plan-records-only allowlist, registered, `planning`/`planned` records, host queue
  check), and a ninth dashboard box **Plan** before Plan check.
- T009: docs and audit.
See `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`.

## Validation run
T001 done (2026-10-10): `.ai/bin/ai-check` PASS, 554 tests; `test_queue_check_*` (7) cover
`ai-task check`, the plan-review and `--skip-plan-review` stops, recover escalation and the
plan prompt.

T002 done (2026-10-10): `.ai/bin/ai-check` PASS, 559 tests; `test_session_budget_*` (5) cover
the 22/16/21 budgets, `--sessions 1` and the triage/revise-plan runs.

T003 done (2026-10-10): `.ai/bin/ai-check` PASS, 565 tests; `test_lock_owner_*` (6) cover the
auto-recovery/pipeline hints, unknown owners, ai-run/ai-review, the symlink/FIFO guard and the
unchanged quiet ai-recover rejection. A symlinked marker is refused earlier by `ai_root`.

T004 done (2026-10-10): `.ai/bin/ai-check` PASS, 571 tests; `test_watchdog_confirm_*` (6)
cover the `OnActiveSec` unit, the silent install-then-start probe, the confirmed killed runner
(once), the immediate dead-marker crash, the planning exemption (FIFO ignored) and old/invalid
dedupe records. Six diagnosis/notification tests now seed an old sighting
(`watchdog_stalled`) instead of relying on the immediate stall.

T005 done (2026-10-10): `.ai/bin/ai-check` PASS, 574 tests; `test_permissions_chmod_*` (3)
cover the template line (exactly `+x`), the install and ai-run `--allowedTools`, and the runner
prompt rule (also after an upgrade). The runner and triage prompts share the section, so both
got the bullet.

## Assumptions
- DB-04 is a mode of `ai-run` (`--plan`), not a new `scripts/ai-plan`: this run's frozen
  allowlist cannot `chmod +x` a new script (FL-22 fixes the template only), and the mode
  reuses ai-run's session, lock, gate and exit handling. `--plan` does not need `--approved`.
- Planner allowlist: Read/Glob/Grep + Edit/Write of `.ai/project-spec.md`,
  `.ai/current-plan.md`, `.ai/tasks.md`, `.ai/state.md`, `.ai/handoff.md`,
  `.ai/reviews/dispositions.md`; no Bash. Headless planners get the queue check from the
  host; interactive ones run `.ai/bin/ai-task check`.
- Session default `+2` slack; fix-round tasks are covered because each ai-run call
  recomputes the budget.
- Stall confirmation window 5 minutes; a markerless killed runner is reported one timer
  period later (~10 min); a crash with a marker stays immediate.
- `planned` is a new dashboard status (sorted after live runs, hidden after 24 h like
  finished); the header counts are unchanged.
- The Plan box is ✓ for every observation whose stage is not `planning` (a pipeline's start
  record included); without an observation it stays unticked ("stage unknown"), never failed.

## Flow chart
Flow chart updated: PENDING, not done by this run (sessions do not edit the vault). Mission
control / Zack: apply to `~/zWiki/zWiki/20 Projects/agents/agents-flow.md` (and its
`updated:`) before merging:
- Big picture: a first stage **Plan** (Claude, `ai-run --plan PROMPT_FILE`, plan records
  only, never commits) → human/mission control commits → `ai-pipeline --approved`.
- Plan review step: the queue is validated first (`ai-task check` rules); an invalid queue
  stops at the plan review ("Task queue is invalid"), recovery always escalates it.
- Implementation: default session budget `max(16, unfinished tasks + 2)`.
- Recovery: a relaunch while auto-recovery holds the lock is rejected with the owner and
  PID and changes nothing.
- Watchdog: first probe 2 min after the timer starts (boot or install); "nothing is
  running" (stalled) needs two sightings ≥ 5 min apart; crash with a marker unchanged.
- Dashboard note: nine boxes, Plan first; `planned` status.

## Manual testing for the human

### Needs you
1. After the gate line below is added: in a test project, a real runner task that creates a
   script runs `chmod +x <script>` without a permission denial, and a session attempt like
   `chmod 777 x` is denied (Claude Code's matcher cannot be tested offline).
2. Real planning session: in a scratch worktree run
   `.ai/bin/ai-run --plan /tmp/objective.md` (after `setup-project --upgrade --apply`) with
   `ai-dashboard` open in another tmux window. Expected: the card appears at once with the
   Plan box active (orange), `📝 PLANNING` and later `📝 Plan ready` notifications, the plan
   files changed but not committed, the card then shows ✓ Plan and `📝 <n> tasks`; after you
   commit and start `ai-pipeline --approved`, Plan stays ✓ and Plan check becomes active.
3. Watchdog on real systemd: reinstall a checkout's timer
   (`.ai/bin/ai-watchdog --install-timer --diagnose --recover`) with `Phase: implementing`
   and no pipeline, then start a pipeline within 2 minutes. Expected: no ⛔ notification;
   `systemctl --user list-timers` shows the next run about 2 minutes after install.
4. Relaunch during recovery: start `ai-pipeline` while an in-pipeline recovery is deciding.
   Expected: the message names `ai-recover` with a PID that `kill` would stop, and
   `.ai/local/last-error` still holds the original stop reason afterwards. (A recovery
   started by the watchdog timer gets the plain message without a hint: documented limit.)

### Covered by automated tests
Filled in by the tasks (T009 checks it): `test_queue_check_*`, `test_session_budget_*`,
`test_lock_owner_*`, `test_watchdog_confirm_*` (timer unit, install-then-start silence,
killed runner confirmed once, dead marker immediate, planning exemption, dedupe record
versions), `test_permissions_chmod_*`,
`test_observation_writer_plan_*`, `test_plan_session_*`, `test_dashboard_plan_*`,
`test_session_budget_end_to_end_*` (T010), `test_plan_keeps_done_*` and
`test_plan_session_revision_*` (T011).

## Human todos
- Gate (this repo, before a run that needs it): add `Bash(chmod +x *)` to
  `.ai/permissions.allow` and reapprove; not needed by this batch (no new executable).
- Other projects: add the same line to each `.ai/permissions.allow` by hand
  (`setup-project --upgrade` never changes it), and run `setup-project --upgrade --apply` so
  `.ai/bin` and `.ai/prompts` (runner and plan prompts) get the changes.
- Reinstall every watchdog timer after merging (`ai-watchdog --install-timer --diagnose
  --recover`): the timer runs a host copy and the old unit still has `OnBootSec`.
- Vault: apply the flow-chart changes above; backlog FL-18/19/21/22 and DB-04 status lines;
  hub Log line.
- No CI workflow change needed.

## Next action
Runner: implement T001–T011 in dependency order (T010/T011 added by plan review round 1;
T009, the audit, depends on T010 and T011 since round 3 and runs last). Human afterwards: the
checks under "Needs you", the gate/vault/timer todos, and the PR review.
