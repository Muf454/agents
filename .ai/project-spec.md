# Spec: Night-stop fixes (FL-18, FL-19, FL-21, FL-22) and a Plan stage (DB-04)

## Objective
Remove the flow defects that stopped real night runs on 2026-10-07/08/09 and make planning
sessions visible as a first pipeline stage. Source: vault `agents-backlog.md`, sections "Stop
analysis 2026-10-07" (FL-18, FL-19, FL-21) and "Dashboard follow-ups" (FL-22, DB-04); Zack
queued them into the night run `fix/night-stops` on 2026-10-09. Planned by Claude on
2026-10-09 against `fix/night-stops` at 744827a (master after #25, the dashboard).
Hub decisions respected: AD-4 (small atomic files in `.ai/local/`, no daemon), AD-5 (status
never authorizes), gate files are never edited by a pipeline session.

## Verified against the code (2026-10-09, 744827a)
- **FL-18 open.** `scripts/ai-pipeline:414` runs the plan review only when
  `ai_helper tasks untouched 2>/dev/null` succeeds; `tasks()` (workflow.py ~418) fails on an
  invalid queue, so the review is skipped silently and `ai-run` stops in implementation with
  the queue error. (Since FL-04 the `Plan review` header sits inside the loop, so it is no
  longer printed; the silent skip remains.) `scripts/ai-task` has only `set`/`show`; the
  runner allowlist template already allows `Bash(.ai/bin/ai-task *)`.
- **FL-19 open.** `scripts/ai-run:32` `sessions=16` fixed default. `ai_lock` (common.sh ~236)
  rejects a second process with `ai_die 'Another runner/reviewer owns this checkout.'`, which
  also overwrites `.ai/local/last-error` (the real stop reason) and says nothing about who owns
  the lock. During an in-pipeline recovery the owner is `ai-recover` (exec'd by `stop()`,
  same PID, lock on fd 9, PID in `.ai/local/pipeline.active`).
- **FL-21 open.** `ai-watchdog --install-timer` runs no probe itself; the timer unit has
  `OnBootSec=2min` (watchdog.py ~231), and systemd fires an elapsed `OnBootSec` timer
  immediately when it is started late (`enable --now`). The probe's `stalled` rule
  (watchdog.py ~418: no runner, no `last-error`, Phase `implementing`/`fixing_review`)
  notifies on the first sighting.
- **FL-22 open.** `templates/.ai/permissions.allow` has no `chmod`; `git add --chmod=+x` is
  allowed (via `git add *`) but leaves the working-tree file 644, so
  `test_script_modes_all_shebang_scripts_are_executable` fails (DB-01 T007).
- **DB-04 open.** Observation box keys (workflow.py ~3098) start at `plan_review`; the
  dashboard draws eight boxes (`dashboard.py` ~330); no planning command exists. Planning
  sessions are started by hand (`claude -p` with an `.ai`-only edit allowlist).

## Requirements
- **FL-18 queue check.** `ai-task check` (new subcommand) validates `.ai/tasks.md` read-only
  with the same rules as the runner (`workflow.py tasks check`) and prints
  `Task queue OK: <total> tasks, <done> DONE` or the exact error (exit 1). `ai-pipeline`, when
  the plan review is enabled, validates the queue BEFORE the `tasks untouched` gate and on
  failure stops with `stop 'plan review'` and last-error
  `Task queue is invalid: <error>`; ai-recover always escalates that reason (a rerun cannot
  fix a plan). `templates/.ai/prompts/plan.md` tells planners with a shell to run
  `.ai/bin/ai-task check` (already allowed by the runner template); headless planners
  (DB-04) get the same check from the host after their session.
- **FL-19 session budget.** Without `--sessions`, `ai-run` uses
  `max(16, <not DONE tasks> + 2)` sessions, computed after the queue check and printed
  (`Session budget: N (…)`). Each pipeline call of ai-run recomputes it, so fix-round tasks
  (added by triage before the next call) are covered; `--sessions N` still wins.
- **FL-19 relaunch while recovery holds the lock.** A process rejected by `ai_lock` never
  writes `last-error`, the marker, observations or notifications; its message keeps the
  prefix `Another runner/reviewer owns this checkout` and names the owner when the marker's
  PID is a live `ai-recover` ("auto-recovery (PID N) is deciding whether to resume the
  pipeline itself; wait for its 🔧 Recovered or ⛔ STOPPED notification, or stop it with
  `kill N` before relaunching") or `ai-pipeline` ("a pipeline (PID N) is running here").
- **FL-21 watchdog false stop.** The timer unit uses `OnActiveSec=2min` instead of
  `OnBootSec=2min` (first probe 2 min after the timer starts: at boot as before, and no
  longer at once after `--install-timer`). The `stalled` incident needs confirmation: the
  first probe that sees it records `stall_seen_ns` in `watchdog.json` and stays silent; a
  later probe at least 5 minutes after that sighting that still sees it reports it (once, as
  today); any probe that does not see it clears the record. A checkout whose observation
  record is at stage `planning` is never stalled. `died` (marker whose process is gone),
  `hung` and `stop` incidents are unchanged and stay immediate.
- **FL-22 executable scripts.** The runner permission TEMPLATE gains exactly
  `Bash(chmod +x *)` (no other chmod form) with a comment; the runner prompt TEMPLATE says:
  make a new script executable with `chmod +x <path inside the checkout>`, never other modes
  or paths outside the checkout, then `git add -- <path>`. This repo's own gate copy is a
  human step.
- **DB-04 plan stage.**
  - Command: `ai-run --plan PROMPT_FILE [--model M] [--revision] [--session-timeout S]
    [--knowledge-dir DIR]` (a mode of the installed `ai-run`, like `--triage` and
    `--revise-plan`; see the plan for why not a new script). Does not need `--approved`
    (no project allowlist is used); refused inside a pipeline (`AI_PIPELINE` set) and with
    `--triage`, `--revise-plan`, `--since`, `--base`, `--sessions`, `--run-timeout`.
    Default model opus. One headless Claude session (`claude_session`, so usage-limit
    pauses, timeouts, `.ai/local/claude-*.json` logs and the post-session gate check apply)
    with tools `Read,Glob,Grep,Edit,Write` and the allowlist from `workflow.py
    plan-allowlist`: `Read`, `Glob`, `Grep`, and `Edit(./X)`/`Write(./X)` for X in
    `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`, `.ai/state.md`,
    `.ai/handoff.md`, `.ai/reviews/dispositions.md`. No Bash. Never commits.
  - Prompt: `.ai/prompts/plan.md` (if present) + the prompt file + a host PLANNING CONTRACT
    (editable files, no shell, no commit, no implementation; the host validates the queue
    with the `ai-task check` rules afterwards; `--revision`: an earlier plan exists, keep
    DONE tasks and their results unchanged).
  - Before the session: lock, protected-branch check, uncommitted changes only in the plan
    records (`workflow.py plan-scope HEAD`), checkout registered (`pipeline-register`),
    observation `step planning "<model> · first plan|revision"`, notification
    `📝 PLANNING on <branch> (<model>)`.
  - After the session: gate unchanged (existing check), `plan-scope <start HEAD>` (only the
    six records plus the host's `.ai/run-log.md` changed), `tasks check`. Success →
    `observe planned "<n> tasks"` (stage `planning`, state `done`) and
    `📝 Plan ready on <branch>: <n> tasks. Review and commit it, then start ai-pipeline
    --approved.`; failure → `last-error` = the reason, observation `stop plan <reason>`
    (stage `planning`, state `stopped`), one ⛔ notification (ai-run's existing exit
    handler). Changes are never reverted.
  - Observation schema: box key `planning` first; stop label `plan` → planning; new action
    `planned NOTE`.
  - Dashboard: nine boxes, **Plan** (Claude orange) before Plan check; still fits 120
    columns (one-column `─` joiners). Plan is ✓ for every record whose stage is not
    `planning` (a pipeline's `start` record, stage `none`, included: the pipeline marks Plan
    passed when it starts); no observation (legacy) leaves Plan unticked as `stage unknown`,
    never a failure. Stage `planning`: active → Plan box active; stopped → Plan box stopped
    with the reason; done → new status `planned` (Plan ✓, marker `📝 <note>`). Compact line
    `✓Plan ·PlanCheck ·Revise …`; `--json` carries stage `planning` and status `planned`.
- **Docs.** README ("Watch all pipelines", planning, scripts/modes tables, session default,
  watchdog timer) and `docs/workflow.md` describe each change. The vault flow chart is NOT
  edited by sessions in this run: the handoff lists the needed flow-chart changes.

## Non-goals
No change to `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/permissions.allow`,
`.claude/settings.json` or `.github/workflows/*` of this repo (human steps). No FL-20
(per-run record paths), FL-23 (CI speed), DB-02/DB-03. No automatic commit of a plan, no
dashboard actions, no change to what the watchdog does after a real crash.

## Acceptance
- Offline regression tests for every behaviour change (names per task in `.ai/tasks.md`),
  in the existing styles of `tests/test_workflow.py`, `tests/test_observation.py`,
  `tests/test_dashboard.py`; existing tests pass (golden dashboard outputs and the watchdog
  stall test are updated to the new behaviour on purpose).
- `.ai/validate` passes.
- README and `docs/workflow.md` describe the changes; the handoff lists the vault
  flow-chart changes and the human steps.
