# Handoff

## What has been implemented?
T037–T043 DONE on `fix/flow-batch-8` (from `master` at c32f768, which has batch 7, #34). The plan was
written 2026-10-19 in an unattended planning session: `.ai/project-spec.md` (scope, what was
verified in the code, assumptions A1–A6), `.ai/current-plan.md` (design) and `.ai/tasks.md`
(T037–T043; T001–T036 are batches 6 and 7, DONE and unchanged because the host protects DONE blocks).
- **FL-32** (vault backlog): the ~11-minute gate outlives a session's 600 s foreground tool call,
  and the prompts said to mark the task BLOCKED then (T027, T029, T030 and T033 of batch 7).
  - T037 (DONE): the runner and triage prompt templates, the RUNNER CONTRACT and README say to
    run the gate with `run_in_background`, wait for it, make no edits meanwhile, and never block
    on an unknown gate result (the host gate decides).
  - T038 (DONE): `run-manifest gate-unblock TASK` (once per task per run, field `gate_unblocks`)
    and `stamp outcome` (a safe reading of `.ai/local/validation.json`: `WORD DIGEST`, never
    following a symlink or blocking on a FIFO). Used by `ai-run` from T040.
  - T039 (DONE): `ai-check` honours `AI_CHECK_LOCK_WAIT`; `ai-run`'s host gates (`host_gate`)
    wait (at most 900 s, within the run time) for a session's background gate that still holds
    the lock. `ai-recover` and `ai-pipeline` keep the immediate refusal.
  - T040 (DONE): `ai-run`'s `gate_only_retry`: a session that blocks its task after its own gate
    showed no failure (`stamp outcome` running/pass/changed with a new digest) gets one host gate
    after the claim `run-manifest gate-unblock`; a pass commits `chore(ai): retry TASK after a
    gate-only block`, sends 🔧 instead of ⚠ and the next session's prompt says why.
  - T041 (DONE): tests pin the neighbouring BLOCKED cases as today (session gate failed, gate
    never ran, host gate fails, no run manifest, dirty tree; no runner change needed);
    docs/workflow.md "Gate-only block retry" and session gate rule, README paragraph, flow chart.
- **N5** (PR #34 final review, MINOR): T042 (sonnet) makes `scripts/lib/common.sh` hold the one
  protected-path list, read by the guard digest (value unchanged) and by `exec-bits`, which then
  never touches `.ai/prompts/`, `.ai/permissions.allow`, `.claude/settings.json` or
  `.github/workflows/ai-validate.yml` either.
- T043 (haiku, DONE): docs, flow chart and handoff audit. The code and docs of T037–T042 agree;
  the mismatches found are listed in its Result / notes (README protected-path clause added, this
  handoff brought up to date, hub Log lines checked).
- Review round 1 (REQUEST CHANGES, M1 + N1 accepted):
  - T044 (opus, DONE, M1): `ai-check` keeps one `AI_CHECK_TIMEOUT` deadline: the lock wait is
    capped at it and deducted from the validator's budget; with no time left it exits 124
    (`Validation time limit reached while waiting for the lock.`) without starting the validator.
    `AI_CHECK_TIMEOUT` is now validated (digits) and both values are read as decimal.
  - T045 (sonnet, DONE, N1): leading-zero `AI_CHECK_LOCK_WAIT` regression tests (no script
    change: T044 already reads both values with `10#`).
- Review round 2 (REQUEST CHANGES, M2 + N2 accepted):
  - T046 (opus, TODO, M2): a lock waiter that runs out of `AI_CHECK_TIMEOUT` exits 124 without
    calling `stamp invalidate`, so it never overwrites the active gate's RUNNING record and
    content changes during that gate still fail it.
  - N2: this handoff now records T045 as DONE (fixed in the triage commit).

## Validation run
T042 tree: PASS (1027 tests, 712.6 s; run in the background and waited for).
T043 tree: `-k Docs` 3 OK and `-k flow_this_repo` 1 OK (targeted). The full gate ran in the
background and was waited for; its result is in the T043 run-log line.
T044 tree: PASS (1031 tests, 662.4 s; run in the background and waited for).
T045 tree: PASS (1033 tests, 664.2 s in the session; 665.7 s in the host stamp at 607a8e8).
`.ai/validate` is unchanged: shell syntax checks, then `tests/run_parallel.py`.

## Assumptions
- A1: the retry lives in `ai-run`'s BLOCKED branch and sets the task back to IN_PROGRESS for one
  more session, never DONE without a session.
- A2: "the session ran the gate" means `validation.json` changed during the session; "no failing
  check" means its outcome is running, pass or changed (exit 0 but the tree changed during the run).
- A3: once per task per human-started run (kept on resume, dropped by `run-manifest start`).
- A5: N5 excludes exactly the guard's list (`.github/workflows/ai-validate.yml`, not every
  workflow file); the guard digest value does not change.
- Sessions of this batch still get the frozen `.ai/prompts` (old foreground rule). The queue header's
  BATCH 8 GATE RULE tells them to run the gate in the background and not to block on it.

## Flow chart
Flow chart updated: T037 updated vault `agents-flow.md` ("Inside one task" `work` node, "Session gate runs" bullet).
T039 updated the "Inside one task" `gate` node (waits for a running gate, at most 15 min) and added a bullet.
T041 added the BLOCKED branch to "Inside one task" (gate-only block retry), a "Gate-only block
retry" bullet and the 🔧 retry row in the notifications table. T042 updates the "Executable bits" bullet.
T043 re-read the vault chart against `ai-run`, `ai-check`, `workflow.py` and the prompts: no change needed.
T044 added the "One gate deadline" bullet (lock wait counts against `AI_CHECK_TIMEOUT`).

## Manual testing for the human

### Needs you
1. Approve the run (`ai-pipeline --approved …`) after reading the plan; no gate file changes are
   needed to start.
2. After merging: run `setup-project --upgrade --apply` here and in raid-planner, family-planner and
   family-budget, so `.ai/prompts` gets the new gate bullet and `.ai/bin` the new `ai-run`,
   `ai-check`, `common.sh` and `workflow.py`. Until then installed sessions keep the old
   "mark BLOCKED" wording (T040's retry covers them).
3. On the next real run with the ~11-minute gate: check one task session's log
   (`.ai/local/claude-*.json`) shows the gate started with `run_in_background` and its result read
   before the commit, and that no task is BLOCKED with "gate result unknown". This needs a live
   `claude -p` session; no test can show the real tool's background behaviour.
4. If a task is still blocked that way on a project not yet upgraded: expect one
   `🔧 T…: blocked without a failing check and the full gate passed; running it once more.` and
   the task finished by the next session.

### Covered by automated tests
Test groups (run with `python3 -m unittest discover -s tests -k <group>`; all passing):
- `test_gate_background_prompts_tell_the_session_to_wait` (T037).
- `test_gate_unblock_manifest_*` (T038: once per task, kept on resume/dropped on start,
  wrong shape invalid, `stamp outcome` words and digest, symlink/FIFO/unsafe `.ai/local` → `none -`).
- `test_gate_lock_wait_*` (T039: waits then passes and the stamp verifies; unset refuses
  at once; held past the wait refuses; invalid value; the runner's host gate waits for a lock left
  by the session and checkpoints the task DONE).
- `test_gate_lock_wait_shares_the_timeout_during_validation`,
  `_exhausts_the_timeout_while_waiting`, `_within_the_total_budget_passes`, `_invalid_timeout`
  (T044: wait plus validation end by `AI_CHECK_TIMEOUT` with 124 and no stamp; a wait that uses
  the whole budget exits 124 with the time-limit message and never starts the validator; a short
  wait inside the budget passes; non-digit timeouts are refused).
- `test_gate_lock_wait_leading_zero_is_decimal`,
  `test_gate_lock_wait_zero_with_leading_zeros_refuses_at_once` (T045: `08` waits 8 s and passes;
  `00` refuses at once).
- `test_gate_only_block_retried_once_then_done`, `test_gate_only_block_retried_once_per_task`
  (T040: retry commit before the DONE checkpoint, 🔧 and no ⚠, the second prompt's note,
  `gate_unblocks` `["T001"]`, one extra host gate pass; a task that blocks every time is retried
  exactly once and then stays BLOCKED with ⚠).
- `test_gate_only_block_unchanged_session_gate_failed`, `_session_never_ran_the_gate`,
  `_host_gate_fails`, `_without_run_manifest`, `_dirty_tree` (T041: T001 stays BLOCKED,
  ⚠ as today, no retry commit or 🔧; a failing host gate spends the claim and the run goes on).
- `test_exec_bits_skips_every_protected_path`, `test_exec_bits_requires_the_protected_list`,
  `test_exec_bits_protected_list_is_defined_once`, `test_exec_bits_guard_digest_unchanged` (T042).

## Human todos
- After merge: the upgrades above; tick FL-32 in the vault backlog (sessions never tick it).
- Vault hub Log: each of T037–T045 appends its own dated line (the planning session could edit
  only `.ai/` files, so it added none).
- Gate files: none need changing for this batch. If you want this repo's own pipeline to use the
  new prompt before merging, upgrade `.ai/prompts` yourself (sessions must not).

## Next action
T046 (review M2), then another independent review. T037–T045 are DONE. Human review of the branch (independent review through the pipeline,
or `ai-review` by hand), then the "Needs you" steps above. Nothing is merged or deployed.
