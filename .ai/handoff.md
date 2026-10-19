# Handoff

## What has been implemented?
T037 DONE on `fix/flow-batch-8` (from `master` at c32f768, which has batch 7, #34). The plan was
written 2026-10-19 in an unattended planning session: `.ai/project-spec.md` (scope, what was
verified in the code, assumptions A1–A6), `.ai/current-plan.md` (design) and `.ai/tasks.md`
(T037–T043; T001–T036 are batches 6 and 7, DONE and unchanged because the host protects DONE blocks).
- **FL-32** (vault backlog): the ~11-minute gate outlives a session's 600 s foreground tool call,
  and the prompts said to mark the task BLOCKED then (T027, T029, T030 and T033 of batch 7).
  - T037 (DONE): the runner and triage prompt templates, the RUNNER CONTRACT and README say to
    run the gate with `run_in_background`, wait for it, make no edits meanwhile, and never block
    on an unknown gate result (the host gate decides).
  - T038 (opus): `run-manifest gate-unblock TASK` (once per task per run) and `stamp outcome` (a
    safe reading of `.ai/local/validation.json`).
  - T039 (opus): `ai-check` honours `AI_CHECK_LOCK_WAIT`; `ai-run`'s host gates wait (at most
    900 s) for a session's background gate that still holds the lock.
  - T040 (opus): a session that blocks its task after its own gate showed no failure gets one
    host gate; a pass sets the task back to IN_PROGRESS for one more session, once per task.
  - T041 (opus): the neighbouring cases stay as today (tests), docs and flow chart.
- **N5** (PR #34 final review, MINOR): T042 (sonnet) makes `scripts/lib/common.sh` hold the one
  protected-path list, read by the guard digest (value unchanged) and by `exec-bits`, which then
  never touches `.ai/prompts/`, `.ai/permissions.allow`, `.claude/settings.json` or
  `.github/workflows/ai-validate.yml` either.
- T043 (haiku): docs, flow chart and handoff audit.

## Validation run
T037 tree: PASS (1006 tests, 644.5 s; run in the background and waited for).
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
T037 updated vault `agents-flow.md` ("Inside one task" `work` node, "Session gate runs" bullet).
T039, T041 and T042 update the notifications table and the "Executable bits" bullet.

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
Planned (group names fixed by the tasks; run with `python3 -m unittest discover -s tests -k <group>`):
- `test_gate_background_prompts_tell_the_session_to_wait` (T037, passing).
- `test_gate_unblock_manifest_*` (T038).
- `test_gate_lock_wait_*` (T039).
- `test_gate_only_block_*` (T040), `test_gate_only_block_unchanged_*` (T041).
- `test_exec_bits_skips_every_protected_path`, `test_exec_bits_requires_the_protected_list`,
  `test_exec_bits_protected_list_is_defined_once`, `test_exec_bits_guard_digest_unchanged` (T042).

## Human todos
- After merge: the upgrades above; tick FL-32 in the vault backlog (sessions never tick it).
- Vault: this planning session could edit only `.ai/` files, so it left no hub Log line; T037,
  T039, T041, T042 and T043 add theirs.
- Gate files: none need changing for this batch. If you want this repo's own pipeline to use the
  new prompt before merging, upgrade `.ai/prompts` yourself (sessions must not).

## Next action
Implement T038–T043 in queue order (T038, T039, T040, T041, T042, T043).
