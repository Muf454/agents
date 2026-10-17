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
  safely; T008/T009 make `--draft` revocation durable or stop. Plan review round 3: T014 makes
  the relaunch verify HEAD and the whole tree (the existing `tree_snapshot`, submodules
  included) once, before it commits, resumes or arms anything; the watchdog's stall alarm reads
  the pending schedule from the manifest, not from the local pause log. Plan review round 4:
  T015 makes the resumed run accept the armed tree through one predicate on the whole path to
  ai-run (a settled re-check no longer refuses it) with no commit while armed; T002's probe
  treats a missing schedule as absent, never as due. Plan review round 5: T016 binds the arm
  to an `implementation` stop and makes the armed resume re-enter at implementation (no plan
  review loop on the preserved tree, so a partial checkpoint that made the plan review stale
  no longer ends in a recovery decision); T006's `ai-plan` creates `.ai/local` on first use.
  Plan review round 6: T017 binds the preserved work to the task the limited session was
  working on (ai-run records it in the host manifest before every session; the arm requires
  it), so T011's resumed ai-run decides by that task's status and a task committed DONE before
  the limit with trailing edits is checkpointed, validated, before any session or the final
  handoff; T006 resolves relative directory arguments against the caller's directory before
  `ai_root`; T016's needs-human test now expects the schedule consumed and no arm on the
  relaunch, plus a separate armed-resume stop. Plan review round 7: T018 makes an armed
  manifest terminal for ai-recover (a stop of the resumed run before the preserved work is
  continued is one ⛔ with nothing committed, also with auto-recovery on, so the fail-closed
  stop can no longer end in a recovery commit of the preserved tree); T011's armed checkpoint
  runs after dependency setup, also when no runnable task remains. Plan review round 8: T019
  makes the arm end at the act (ai-run's own consistency and routing checks run while the
  manifest is still armed, so they are terminal too; `limit-disarm` is the last statement
  before the armed checkpoint or the session), and T002's probe no longer raises the ordinary
  stall alarm on top of a refused or launched due relaunch.
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
T002: `.ai/bin/ai-check` PASS, 832 tests in 460.9 s; `-k limit_relaunch_watchdog` 8 OK;
`-k watchdog` 61 OK. Mutation: dropping the "due and `--recover`" clause of `relaunch_quiet`
fails 4 of the 8 tests.

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
Flow chart updated (T002: "When something goes wrong" gained the usage-limit relaunch path,
watchdog start after the reset, cap, ⛔ otherwise; the ai-recover side lands with T003). Still to
be updated by T003/T014/T017/T011/T016/T018/T019/T015 (limit relaunch), T006 (`ai-plan`), T007 (outcome log bullet)
and T009 (un-draft rule) in `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`; T010 audits it.

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
- `test_limit_relaunch_watchdog_*` (T002: due relaunch started, refusal reported once with no stall alarm on top of it, no stall alarm while waiting, nothing launched or reported for a checkout without a schedule, `--timer-recovers`).
- `test_limit_relaunch_recover_*` (T003: pause instead of ⛔, resume without Claude, cap, off switch, no timer, mixed reason, terminal escalation after a claim, interrupted scheduling restores the wait).
- `test_limit_relaunch_binding_*` (T012: tree digest = `tree_snapshot` incl. submodules, verify/arm only for the exact scheduled tree, a human edit during the wait escalates and is preserved, `tasks newly-done`).
- `test_limit_relaunch_verify_*` (T014: the relaunch verifies before any commit or resume; bookkeeping-only edits, a moved HEAD on a clean tree, in-scope edits during an open stage and submodule changes all stop with the checkout untouched).
- `test_limit_relaunch_bound_*` (T017: the manifest records the running task, the arm names it and is refused without it, `limit-task`).
- `test_limit_relaunch_preserved_*` (T011: the relaunch continues uncommitted task work once, decided by the bound task's status; a task DONE before the limit, committed or not, is checkpointed without a session, dependency setup first; moved HEAD escalates; a human start refuses a dirty tree; a settled re-check does not refuse the preserved work).
- `test_limit_relaunch_reenter_*` (T016: the arm is granted only for an implementation stop; an armed resume skips the plan review loop, so a committed partial checkpoint with a stale plan review completes without a plan review or recovery decision; a clean resume still re-reviews; a needs-human plan decision still stops).
- `test_limit_relaunch_terminal_*` (T018: a stop of the resumed run while the tree is armed is one ⛔ with nothing committed and no recovery decision session, also with auto-recovery on; the relaunch itself and stops after the disarm are unaffected).
- `test_limit_relaunch_consume_*` (T019: ai-run's own checks of the preserved work, another task newly DONE, a wrong next task, a blocked or unknown bound task, a failing dependency setup, stop terminal with auto-recovery on and the arm retained; the disarm is the last statement before the checkpoint or the session).
- `test_limit_relaunch_accept_*` (T015: the resumed run admits the armed tree in every start-path state, accepted-plus-rejected findings with a verified re-check included, commits nothing before ai-run consumes the arm, and fails closed on inconsistent review records).
- `test_exec_logged_*` (T013: detached log created exclusively, no symlink/FIFO followed).
- `test_dashboard_limit_relaunch_*`, `test_dashboard_plan_killed_*` (T004).
- `test_plan_read_dir_*` (T005), `test_ai_plan_*` (T006, incl. first use in a fresh install where `.ai/local` does not exist yet, and relative `--read-dir`/`--knowledge-dir` from a subdirectory), `test_plan_outcome_*` (T007).
- `test_pr_undraft_record_*` (T008), `test_pr_undraft_*` (T009).

## Human todos
- Merge order: PR #29, PR #30, then this branch (it builds on both).
- Installed copies and watchdog timers: upgrade and reinstall after merging (see Needs you 1).
- Backlog (vault, sessions do not tick it): MC-01 part 1, DB-04 and R15 when this merges.

## Next action
T001–T002 done (limit-stop record and manifest schedule helpers; watchdog starts a due
relaunch, reports a refusal once, no stall alarm while waiting, `--timer-recovers`); next is
T003 (ai-recover schedules and resumes).
