# Spec: Flow batch 8: the gate outlives a session's tool call (FL-32), executable-bit repair skips every gate path (N5)

## Objective
Two items, planned 2026-10-19 on `fix/flow-batch-8` (from `master` at c32f768, which has batch 7,
#34):
1. **FL-32** (vault `agents-backlog.md`): the full gate takes about 630–670 s here, longer than the
   600 000 ms limit of a foreground Bash tool call. Sessions told to run `.ai/bin/ai-check` in the
   foreground (and "if it still times out, mark the task BLOCKED") marked finished work BLOCKED with
   "gate result unknown": T027, T029, T030 and T033 of batch 7. Mission control had to run the gate
   and set them DONE by hand. Two sessions that did wait (T033, T036) edited records during the run,
   and the stamp then failed with `Validation modified project content`.
2. **N5** (open MINOR of PR #34's final review): `exec_bits()` skips `.ai/bin/`, `.ai/validate` and
   `.ai/ci-setup` but not `.ai/prompts/`, `.ai/permissions.allow`, `.claude/settings.json` or
   `.github/workflows/ai-validate.yml`, which the gate guard protects.

## Verified against the code (c32f768)
- `templates/.ai/prompts/runner.md` lines 49–52 and `templates/.ai/prompts/triage.md` lines 55–58
  (one shared "How to work here" block, asserted equal by `test_tool_contract_section_is_shared_by_prompts`)
  say: foreground, `timeout` 600000 ms, "never run it in the background or poll it", "If it still
  times out, mark the task BLOCKED". README line 198 (setup step 4) says the same. The RUNNER
  CONTRACT string in `scripts/ai-run` (~842) says "Complete and checkpoint it, or mark it BLOCKED
  with evidence".
- A session gets the tools `Read,Glob,Grep,Edit,Write,Bash` (`scripts/ai-run` ~189). Batch 7
  sessions whose foreground call was moved to the background did read the finished result later
  (T024, T025, T028, T034, T035 results), so waiting works with this tool set.
- `scripts/ai-run` ~857–863: a BLOCKED task with a clean tree gets `task_outcome blocked`, a ⚠
  notification and `runner_checkpoint TASK BLOCKED`; the host never validates it and the run
  goes on with independent tasks. A DONE task gets `checkpoint_done` (host `ai-check`; a failure
  sets it back to IN_PROGRESS and stops).
- `scripts/ai-check` takes `.ai/local/validation.lock` with `flock -n` and dies `Validation is
  already running.`; `stamp invalidate` writes `.ai/local/validation.json` `{"result": "RUNNING"}`,
  `stamp record` writes `PASS`/`FAIL` with `exit_code` and `unchanged`.
- `run-manifest timeout-rerun TASK` (`scripts/lib/workflow.py` ~1559, field `timeout_reruns`,
  `timeout_reruns_valid` ~1329, kept by `clear-attempts`, dropped by `start`) is the model for a
  once-per-task host record.
- The protected list lives only inside the inline `python3 -I -` heredoc of `ai_guard_digest`
  (`scripts/lib/common.sh` ~152–155: roots `.ai/validate`, `.ai/ci-setup`, `.ai/bin`,
  `.ai/prompts`, `.ai/permissions.allow`, `.claude/settings.json`,
  `.github/workflows/ai-validate.yml`; optional: the last two). `exec_bits()`
  (`scripts/lib/workflow.py` ~4460) has its own partial list; `ai-run` calls `ai_helper exec-bits`
  (~364). The guard must not ask the project helper to verify itself, so the shared list has to be
  shell data that both read, not a Python constant the guard imports.

## Scope
- R1 Prompt templates (`templates/.ai/prompts/runner.md`, `triage.md`, the shared block), the
  RUNNER CONTRACT string in `scripts/ai-run`, README setup step 4 and docs: run the full gate with
  the Bash tool's `run_in_background`, wait for it to finish and read its result. Make no edits and
  no commits while it runs. Do not end the session while it runs. Never mark a task BLOCKED only
  because the gate outlived a tool call or its result could not be read: then finish the task on its
  targeted evidence, say so in the result, and leave the verdict to the host gate after the session
  (which already returns a DONE task whose gate fails to IN_PROGRESS).
- R2 Host record: `run-manifest gate-unblock TASK` (once per task per human-started run, field
  `gate_unblocks`, same lifecycle as `timeout_reruns`), and a safe `stamp outcome` reading of
  `.ai/local/validation.json` (no symlink following, never blocks).
- R3 The host gate waits for a running gate: `ai-check` honours `AI_CHECK_LOCK_WAIT` (seconds,
  default 0 = today's immediate refusal); `ai-run` sets a bounded wait for its own gate runs, so a
  session's background gate that is still running cannot fail the host gate.
- R4 Gate-only block retry in `ai-run`: after a session that marks its task BLOCKED, with a clean
  tree beyond the records, that started a gate run during the session (validation.json changed) and
  whose own gate shows no failing check (`running`, `pass` or `changed`, never `fail`), the host
  claims `gate-unblock TASK` and runs the full gate. A pass sets the task back to IN_PROGRESS
  (committed), notifies once and the loop gives it one more session. A failed gate, a second block
  of the task, no manifest, or any other case keeps today's BLOCKED path.
- R5 N5: one protected-path list (`scripts/lib/common.sh`) feeds both the guard digest (digest
  value unchanged) and `exec-bits`; `exec-bits` never touches any path at or below a protected root.
- Every behaviour change gets an offline regression test in the existing style; the vault flow
  chart is updated in the task that changes the flow.

## Non-goals
- Making the suite faster (FL-31 follow-up) or changing `.ai/validate`.
- Any edit to gate files: `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/ci-setup`,
  `.ai/permissions.allow`, `.claude/settings.json`, `.github/workflows/*`. The new prompts reach
  this repo's own pipeline only after the human's upgrade (handoff).
- Killing a session's leftover processes (FL-27 territory); R3 only waits for the lock.
- Setting a BLOCKED task DONE without a session: the host only sets it back for one rerun.
- `ai-recover` changes: a BLOCKED task does not stop the run, so the runner is the place that sees
  the case while the session's evidence is fresh.

## Assumptions (unattended; recorded instead of asking)
- A1 "Let recovery set it back" is implemented in `ai-run`'s BLOCKED branch (host recovery inside the
  runner) and means BLOCKED → IN_PROGRESS for one more session, not DONE. A real human blocker then
  re-blocks once and stays BLOCKED; the cost is one host gate and one session per task at most.
- A2 "The session ran the gate" = `.ai/local/validation.json` differs (bytes digest) after the
  session from before it. "No failing check" = its outcome is `running`, `pass` or `changed` (exit 0
  but the tree changed during the run, the T033/T036 case). `.ai/local` is agent-writable, so a
  forged file can at most buy one host gate run and one rerun: nothing is accepted without the
  host gate and a later DONE checkpoint.
- A3 Once per task per human-started run: `gate_unblocks` is kept by `clear-attempts` (resume) and
  dropped by `run-manifest start`. Without a run manifest (standalone `ai-run`) the claim fails and
  today's path runs.
- A4 The lock wait for host gates is `min(remaining run time, 900)` seconds; `ai-recover` and
  `ai-pipeline` keep today's immediate refusal.
- A5 N5 covers the guard's list exactly, so `.github/workflows/ai-validate.yml` (the guarded
  workflow file), not every file in `.github/workflows/`; other workflow files are not gate files
  of an installed project. The guard digest value must not change (approved runs keep verifying).
- A6 The prompt still allows a foreground call for short commands; only the full gate goes to the
  background. Targeted `-k` tests stay foreground.

## Acceptance criteria (observable)
- AC1 Both template prompts tell the session to run `.ai/bin/ai-check` with `run_in_background`,
  wait and read the result, not edit or commit meanwhile, and never mark BLOCKED only for an unknown
  gate result; the old "never run it in the background" and "If it still times out, mark the task
  BLOCKED" are gone; README step 4 and the RUNNER CONTRACT agree (prompt tests).
- AC2 `run-manifest gate-unblock T001` succeeds once, fails the second time with the manifest bytes
  unchanged; `stamp outcome` prints the right word and digest for missing, RUNNING, PASS, exit-0
  FAIL, non-zero FAIL, a symlink and a FIFO (returns promptly) (`test_gate_unblock_manifest_*`).
- AC3 `ai-check` with `AI_CHECK_LOCK_WAIT=N` waits for a held lock and then validates; with 0 it
  refuses as today; an invalid value is an error; `ai-run`'s host gates pass the wait
  (`test_gate_lock_wait_*`).
- AC4 A mock session that blocks its task with a RUNNING stamp gets one host gate, `🔧` notification,
  task set back to IN_PROGRESS in a commit, a second session that finishes it, and the run completes;
  a task that blocks twice stays BLOCKED after one retry (`test_gate_only_block_*`).
- AC5 No retry when: the stamp is a non-zero FAIL, the session did not run the gate, the host gate
  fails (the task stays BLOCKED and the run goes on as today), no run manifest, or the tree is dirty
  (`test_gate_only_block_unchanged_*`).
- AC6 `exec-bits` restores nothing at or below any protected root (each one tested), the list is
  defined once in `scripts/lib/common.sh`, the guard digest is unchanged, and `exec-bits` without
  the list is a usage error (`test_exec_bits_*`).
- AC7 `.ai/bin/ai-check` passes; README, docs/workflow.md, the vault flow chart and the handoff
  match the code.
