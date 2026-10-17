# Spec: Limits and plan stage: limit-only stops relaunch by themselves (MC-01 part 1), `ai-plan` planning command (DB-04), un-draft only pipeline-drafted PRs (R15)

## Objective
Three items Zack decided on 2026-10-17 (vault `agents.md` Log, `agents-backlog.md`):
1. **MC-01 part 1 only.** A pipeline stop whose only reason is a usage limit (the reset is
   beyond `AI_LIMIT_MAX_WAIT`) is not a human problem: `ai-recover` schedules a relaunch at the
   parsed reset time in host state and exits without ⛔; the installed watchdog timer (wakes every
   10 min, `--recover`) starts `ai-recover` again once that time has passed, and `ai-recover`
   resumes the approved run without a Claude decision. A per-run cap (`AI_LIMIT_RELAUNCH_MAX`)
   bounds it; past the cap, or without a watchdog timer that recovers, the stop escalates with ⛔
   as today. Part 2 (mission tick, headless mission-control session) is NOT built.
2. **DB-04.** A toolkit command `ai-plan PROMPT_FILE` replaces mission control's hand-run
   launcher (`~/Projects/wt/plans/sessions/launch-plan.sh`): same `.ai`-only edit allowlist,
   read-only reference directories (`--read-dir`), registered in the host registry, a `planning`
   stage on the dashboard from the moment the session starts, logged like other sessions
   (session JSON log, outcome log, run-log line), optional detached start (`--detach`) that
   prints the PID and log. It never commits. The dashboard Plan box shows a planning session
   that died without a plan as a stop.
3. **R15.** When the PR step runs with a clean review and no dispute, `ai-pipeline` runs
   `gh pr ready` only on a PR the pipeline itself converted to (or created as) draft, recorded
   durably in host state when it drafts; a PR a human set to draft is never un-drafted.

Branch `feature/limits-plan-stage`, created from `fix/flow-batch-5` at edc3dc6 (PR #30, open,
built on open PR #29; master has #27 and #28). Planned by Claude on 2026-10-17 (unattended
planning session; no human until 09:00, so assumptions are recorded, not asked). Hub decisions
respected: AD-4 (small files in host state / `.ai/local/`, no daemon: the existing watchdog timer
does the waking), AD-5 (telemetry never authorizes anything), gate files are never edited by a
pipeline session.

## Verified against the code (2026-10-17, edc3dc6)
- **MC-01 open.** `ai_limit_pause` (`scripts/lib/common.sh:95–112`) sleeps until the reset + 60 s
  (or `AI_LIMIT_RETRY`, default 1800 s, when the reset is unknown) and dies with
  `<Agent> usage limit: the reset is beyond the <max>s wait budget. Rerun after it resets.` when
  `AI_WAITED + wait > AI_LIMIT_MAX_WAIT` (default 28800). The parsed reset epoch is not written
  anywhere. Inside `ai-pipeline`, `stop()` (`scripts/ai-pipeline:147–163`) execs `ai-recover`,
  whose hard rules (`scripts/ai-recover:137–143`) match `*'beyond the'*'wait budget'*` and
  escalate (⛔). The watchdog (`scripts/lib/watchdog.py:370–515`) starts `ai-recover` only for a
  `died:` incident (`start_recovery`, 293–335, which always passes `--stage 'crash (pipeline
  killed or restarted)'` and writes a default last-error); it already treats a usage-limit pause
  as quiet until its end (`paused_until`, 119–132, from `.ai/local/pauses.log`). The run manifest
  (`run_manifest`, `scripts/lib/workflow.py:1279–1397`) holds the attempt budget (`attempts`,
  `reserve-attempt`, `clear-attempts`) and the approved settings (`RUN_SETTINGS`, 1980).
  `ai-recover` reserves an attempt (70) before the hard rules, so a limit path must give it back.
  Tests: `test_usage_limit_beyond_wait_budget_stops` (tests/test_workflow.py:5062, standalone
  `ai-run`, stays as is), mock `limit-far` (tests/test_workflow.py:312), watchdog recovery tests
  with `mock_systemd_run` (1067–1107).
- **DB-04 mostly built, gaps remain.** `ai-run --plan PROMPT_FILE` (`scripts/ai-run:29–37,
  90–99, 323–379`) already runs the headless opus session with `workflow.py plan-allowlist`
  (Read/Glob/Grep + Edit/Write of the five plan records and `reviews/dispositions.md`,
  workflow.py:2752–2764), registers the checkout (`pipeline-register`), records
  `observe step planning`, `planned`, `stop plan` (on_exit 197–200), never commits; the
  dashboard already has nine boxes with Plan first (`FLOW`, `scripts/lib/dashboard.py:422–426`;
  tests `test_dashboard_plan_*`, tests/test_dashboard.py:1056–1170, golden widths at 120/119/60
  columns already pass). Gaps against the decision: (a) no `ai-plan` command; (b) no way to grant
  the read-only reference directories mission control's launcher grants (`Read(//home/zack/zWiki/**)`,
  `Read(//home/zack/Projects/wt/plans/**)`, `Read(//home/zack/Projects/wt/research/**)`;
  `--knowledge-dir` grants one directory and its prompt says "Read/update"); (c) no detached
  start (mission control uses `nohup … &` and `echo pid`); (d) a planning session is not in the
  outcome log and writes no run-log line on success; (e) a planning `ai-run` killed by SIGKILL
  leaves `stage planning, state active` with no runner, which the dashboard shows as `idle`
  (`inspect`, dashboard.py:382–392), not as a stop.
- **R15 open.** The PR step (`scripts/ai-pipeline:600–619`) sets `make_draft=yes` for `--draft`,
  an unresolved fix round or a recorded dispute; creates the PR with `--draft` or converts an
  existing ready PR with `gh pr ready --undo`; it never runs `gh pr ready`, and records nowhere
  that it drafted. The test mock `MOCK_GH` (tests/test_workflow.py:608–630) treats every
  `pr ready` call as "make draft" (it ignores `--undo`).

## Scope
In: `scripts/lib/common.sh`, `scripts/ai-recover`, `scripts/lib/watchdog.py`, `scripts/ai-watchdog`
(only if its argument passing needs it), `scripts/lib/workflow.py`, `scripts/lib/dashboard.py`,
`scripts/ai-run`, new `scripts/ai-plan`, `scripts/ai-pipeline`, `tests/`, `README.md`,
`docs/workflow.md`, the vault flow chart `agents-flow.md` and the hub Log line.
Out: MC-01 part 2 (mission tick / `ai-mission` / headless mission-control session); changing the
standalone `ai-run`/`ai-review` limit behaviour outside a pipeline; any gate file (`.ai/bin`,
`.ai/prompts`, `.ai/validate`, `.ai/permissions.allow`, `.claude/settings.json`,
`.github/workflows/*`); deleting mission control's `launch-plan.sh` (outside the repo; human step).

## Acceptance criteria (whole batch)
- A pipeline whose Claude (or Codex, same message) session hits a limit beyond the wait budget,
  with auto-recovery on and the watchdog timer installed with `--recover`, ends with
  `⏸ PAUSED … relaunches by itself after <time>`, no ⛔, no recovery Claude session, and a host
  schedule; a watchdog probe after that time starts `ai-recover`, which resumes the approved run
  (`▶ RESUMED`) without consuming the `AI_RECOVER_MAX` budget. A further limit stop beyond
  `AI_LIMIT_RELAUNCH_MAX` (default 2) relaunches, a missing/non-recovering timer, or
  `AI_LIMIT_RELAUNCH_MAX=0`, escalates with ⛔ as today (the message names the reset time).
  A due schedule is consumed by the first recovery that sees it (a later escalation is one
  terminal ⛔, never a launch loop); a recovery started while the schedule is still in the
  future restores the wait without counting a relaunch or retrying early; uncommitted work of
  the limited implementation session is continued once by the normal implementation session
  (validated before any commit), not escalated (plan review round 1, P1–P3).
- The dashboard shows a gone run as paused only with evidence of a currently scheduled
  relaunch (`relaunch_at` in the observation); a newer last-error still wins.
- `ai-plan PROMPT_FILE [--read-dir DIR]... [--detach]` runs the planning session with the same
  edit allowlist as `ai-run --plan`, Read access to each `--read-dir`, a `planning` dashboard
  stage while it runs, an outcome record `kind: plan` and a run-log line; `--detach` returns
  after the session has confirmably started and prints its PID and log path. The session never
  commits. A planning session killed without a plan shows as a stop on the Plan box.
- `ai-pipeline` un-drafts an existing draft PR only when host state records that the pipeline
  drafted that PR, the review is clean and no dispute remains; a human-drafted PR stays draft,
  and a run with `--draft` clears the pipeline's record, so a later run never un-drafts it.
- Every behaviour change has an offline regression test in the existing style; `.ai/bin/ai-check`
  passes; README.md and `docs/workflow.md` describe the new behaviour; the vault flow chart is
  updated in the tasks that change the flow.
