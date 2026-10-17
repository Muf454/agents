# Handoff

## What has been implemented?
Nothing yet on this branch: this is the plan. Branch `feature/limits-plan-stage` (from
`fix/flow-batch-5` at edc3dc6; PR #30 on PR #29, neither merged) plans three items Zack decided
on 2026-10-17 (Claude planning session, unattended):
- **MC-01 part 1** (T001–T004): a pipeline stop whose only reason is a usage limit beyond the
  wait budget schedules a relaunch in host state and pauses (⏸, exit 75) instead of ⛔; the
  watchdog timer (`--recover`) starts `ai-recover` once the reset has passed and the run resumes
  without a Claude decision (▶ RESUMED). Cap `AI_LIMIT_RELAUNCH_MAX` (default 2) per human-started
  run; past it, without a recovering timer, or with the cap at 0, ⛔ as today. No mission tick.
  Plan review round 1: the schedule is held/claimed right after the attempt reservation (no
  launch loop, no double schedule), and T011 lets the relaunch continue the limited session's
  uncommitted task work once, validated as usual. Plan review round 2: T012 binds that exception
  to the exact preserved tree (a change during the wait escalates, nothing absorbed) and T011
  also checkpoints a task marked DONE just before the limit; T013 creates the `--detach` log
  safely; T008/T009 make `--draft` revocation durable or stop.
- **DB-04** (T004–T007): `ai-plan PROMPT_FILE [--read-dir DIR]... [--detach]` replaces
  `launch-plan.sh` (same edit allowlist as `ai-run --plan`, read-only reference directories,
  confirmed detached start printing PID and log), planning sessions in the outcome log and run
  log, and a killed planning session shown as a stop on the dashboard's Plan box (the nine-box
  dashboard with the Plan box already exists).
- **R15** (T008–T009): the PR step un-drafts an existing draft PR only when host state records
  that the pipeline drafted it; human drafts and `--draft` runs stay draft.
- T010: docs, flow chart and handoff audit.
See `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`.

## Validation run
Not run on this branch yet. PR #30's last gate: `.ai/bin/ai-check` PASS (817 tests, 434.3 s on 8 workers).

## Assumptions
- MC-01: the relaunch also covers a Codex limit stop (same message and mechanism); default cap 2;
  a due relaunch needs `AI_AUTO_RECOVER` on and does not use `AI_RECOVER_MAX`; a scheduled pause
  exits 75; any non-limit stop after a relaunch follows the normal recovery rules.
- DB-04: `ai-plan` keeps `plan-allowlist` unchanged (it also allows
  `.ai/reviews/dispositions.md`, which `launch-plan.sh` did not); a finished plan keeps today's
  dashboard view (Plan ✓, 📝 under Plan check) until the pipeline starts.
- R15: a PR drafted because of `--draft` is the human's choice and never recorded; a `--draft`
  run that cannot remove the pipeline's record stops (⛔ names the file); an un-draft
  failure warns and does not stop the run; a human who un-drafts and re-drafts between two runs
  is not detected (documented limitation).

## Flow chart
To be updated by T002/T003/T011 (limit relaunch), T006 (`ai-plan`), T007 (outcome log bullet) and
T009 (un-draft rule) in `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`; T010 audits it.

## Manual testing for the human

### Needs you
1. After merging (#29, then #30, then this branch), refresh the installed copies
   (`setup-project --upgrade --apply` here and in raid-planner / family-planner) so `.ai/bin`
   gets `ai-plan`, the new `ai-recover` and `ai-watchdog`; then REINSTALL each watchdog timer
   (`.ai/bin/ai-watchdog <checkout> --install-timer --recover`): the timer runs a host copy made
   at install time.
2. Limit relaunch on a real limit (or a disposable checkout with `AI_LIMIT_MAX_WAIT=60`): when a
   run hits a Claude limit far away, check the phone shows `⏸ PAUSED … relaunches by itself after
   <time>` (no ⛔), `ai-dashboard` shows the run paused, and within ~10 min after the reset the
   run continues with `▶ RESUMED after the usage limit`.
3. Start a planning session with `ai-plan <prompt> --read-dir ~/zWiki --read-dir
   ~/Projects/wt/plans --read-dir ~/Projects/wt/research --detach`: it prints a PID and log, the
   dashboard shows the Plan box active, the plan is left uncommitted. Then retire
   `~/Projects/wt/plans/sessions/launch-plan.sh` and update mission control's notes to use
   `ai-plan`.
4. R15 on a real PR: a run that drafted its PR because of a dispute or deferral becomes ready
   after a later clean run; a PR you drafted yourself stays draft.

### Covered by automated tests
Each group is a name prefix; `python3 -m unittest discover -s tests -k <group>` runs it (added by
the task named).
- `test_limit_relaunch_record_*` (T001: limit-stop record, relaunch time, manifest schedule/cap/attempt give-back).
- `test_limit_relaunch_watchdog_*` (T002: due relaunch started, refusal reported once, no stall alarm while waiting, `--timer-recovers`).
- `test_limit_relaunch_recover_*` (T003: pause instead of ⛔, resume without Claude, cap, off switch, no timer, mixed reason, terminal escalation after a claim, interrupted scheduling restores the wait).
- `test_limit_relaunch_binding_*` (T012: tree digest, arm only for the exact scheduled tree, a human edit during the wait escalates and is preserved, `tasks newly-done`).
- `test_limit_relaunch_preserved_*` (T011: the relaunch continues uncommitted task work once; a task DONE before the limit is checkpointed without a session; moved HEAD escalates; a human start refuses a dirty tree).
- `test_exec_logged_*` (T013: detached log created exclusively, no symlink/FIFO followed).
- `test_dashboard_limit_relaunch_*`, `test_dashboard_plan_killed_*` (T004).
- `test_plan_read_dir_*` (T005), `test_ai_plan_*` (T006), `test_plan_outcome_*` (T007).
- `test_pr_undraft_record_*` (T008), `test_pr_undraft_*` (T009).

## Human todos
- Commit this plan, then start `ai-pipeline --approved` on `feature/limits-plan-stage`.
- Merge order: PR #29, PR #30, then this branch (it builds on both).
- Installed copies and watchdog timers: upgrade and reinstall after merging (see Needs you 1).
- Backlog (vault, sessions do not tick it): MC-01 part 1, DB-04 and R15 when this merges.

## Next action
Commit the plan and start the pipeline; the first task is T001.
