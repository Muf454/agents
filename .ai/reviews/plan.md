<!-- Plan review of plan digest 1a8f34e84c951787a7ecf3f91d1a7b21f16858796dbf5fbaafbd44f1f3a5a30c; HEAD ca16a66bc778a6e9b89983db067e947e30b88d4b; saved 2026-10-17T01:53:53Z. -->

# Plan review

Review scope: HEAD `ca16a66bc778a6e9b89983db067e947e30b88d4b`, round 3.

Overall verdict: Revise before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=0

The current plan addresses P1–P8. The remaining findings concern reconciliation failure paths and the proposed restart test.

## BLOCKER findings

None.

## MAJOR findings

- P9: Reconciliation can remove a marker after its outcome failed to sync.

  **Location:** `.ai/tasks.md:291–312`; `.ai/current-plan.md:74–82`.

  A complete `os.write` followed by a failed file or directory sync leaves a readable outcome line and retains its marker. At the next reconciliation, T003 finds that `attempt_id` in the log and specifies “only remove,” without completing the failed sync. The marker can therefore be durably deleted while the outcome remains vulnerable to power loss.

  This concerns the newly attempted append whose sync failed, within CU-5’s promised durability. It does not require repairing unrelated historical rows.

  **Concrete plan change:** Before removing a retained marker on the existing-record path, successfully sync the log and necessary directory entries. Preserve the marker on failure. Add fault-injection tests covering a complete write followed by file-sync and directory-sync failures, then reconciliation; assert that marker removal requires successful durability checks and introduces no duplicate record.

- P10: Reconciliation cannot distinguish an unreadable log from an empty one.

  **Location:** `.ai/tasks.md:160–161,304–312`; `scripts/lib/workflow.py:2987–3000`.

  T007 explicitly preserves the reader’s behavior of silently skipping a file on `OSError`. T003 then uses that reader to decide whether an attempt already has a record. A transient read failure returns no records, so reconciliation can append a second `crashed` outcome and remove the marker, violating the exactly-once requirement.

  A read-only fault-injection probe confirmed that the existing reader returns `[]` on an injected read error. The proposed byte reader retains this behavior.

  **Concrete plan change:** Give reconciliation a strict read mode that distinguishes a missing log from other read failures. On a read failure, retain the marker, emit a note, and continue without appending. Test an already-recorded attempt with a retained marker: inject one read failure, verify no append or removal, then verify a successful retry removes the marker without duplication.

- P11: The SIGKILL restart test assumes a clean checkout that the runner does not leave.

  **Location:** `.ai/tasks.md:383–386,395–417`; `scripts/ai-run:136–148,626`; `scripts/lib/workflow.py:760–785`.

  Before launching Claude, the runner writes tracked `.ai/state.md` with phase `implementing` and a new next action. The proposed `sigkill-runner` mock kills the runner without checkpointing that change. Consequently, the second ordinary `ai-run --approved` invocation specified by T004 fails the existing clean-checkpoint check before reaching the current gate-baseline location or running the task.

  The plan neither includes the necessary checkpoint reconciliation in this test nor explicitly resolves whether crash-outcome reconciliation must run before that startup refusal.

  **Concrete plan change:** Define the ordering explicitly while preserving the clean-checkpoint requirement. If the first restart must record the crash even with dirty leftovers, perform trusted, best-effort outcome reconciliation before refusing implementation. Test that refusal and exactly-once crash logging, then explicitly checkpoint the fixture’s bookkeeping before the successful task restart. Otherwise, document the checkpoint prerequisite and include it in the test and restart instructions.

## MINOR findings

None.

## Validation and limitations

Inspected guidance, all eight tasks, spec, plan, dispositions, state, handoff, relevant source, prompts, tests, documentation, validation entry points, and revision history. Model selections are appropriate.

Observed:

- Task queue validation passed.
- Relevant shell syntax and Python AST checks passed.
- Three documentation consistency tests passed.
- The shared prompt-contract test passed by direct invocation.
- Injected outcome-log read failure returned an empty record list.

The full gate and fixture-based integration tests require filesystem writes and were not run in this read-only sandbox. Durability findings follow the prescribed operation ordering; power-loss behavior was not experimentally tested. No files were modified or network integrations invoked.