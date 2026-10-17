<!-- Plan review of plan digest 0e6f1698d8f35c7994f2c3339324cdf0d3cb64bcfdb2c5856138ad675e0dd7b5; HEAD b62dd2920c9cda15b2adfc1b3cac3439c08d57ce; saved 2026-10-17T01:48:48Z. -->

# Plan review

Review scope: HEAD `b62dd2920c9cda15b2adfc1b3cac3439c08d57ce`, round 2.

Overall verdict: Revise before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=0

The revised plan covers P1–P5, including the requested regression cases. The findings below concern remaining gaps in the proposed CU-5 implementation.

## BLOCKER findings

None.

## MAJOR findings

- P6: Opening another attempt can overwrite a marker retained after an append failure.

  **Location:** `.ai/tasks.md:212–228`, `.ai/tasks.md:301–304`; `scripts/ai-run:208–211,677–684`.

  T003 requires `attempt-open` to reconcile the singleton marker and then replace it. Reconciliation can legitimately leave that marker intact. For example, a normal task outcome receives a short write, retains its marker, and the runner continues to another task. Reconciliation sees the same runner PID still alive and leaves the old marker; `attempt-open` then overwrites it. The failed outcome is permanently lost. Repeated reconciliation failures at startup have the same overwrite risk.

  **Concrete plan change:** Make unresolved markers survive subsequent attempt openings while preserving nonfatal telemetry behavior. For example, retain pending markers by attempt ID and reconcile them separately. Add a two-task regression where the first outcome append fails, the second task completes, and the first attempt remains recoverable and is eventually recorded exactly once.

- P7: The newline guard races with another checkout’s partial append.

  **Location:** `.ai/tasks.md:147–154,243–244`; `.ai/current-plan.md:51–57`.

  The tail check and append are separate operations without a shared lock. Writer A can observe a final newline, writer B can then append a partial record, and A can append its complete record without a leading newline. A’s record joins B’s fragment and becomes unreadable, although A reports success and removes its marker.

  An in-memory probe of the prescribed sequence reproduced this: A’s write returned its full byte count, but parsing retained only the earlier record. The claim that concurrent writers can produce only an empty line is therefore incorrect.

  **Concrete plan change:** Make framing safe across this interleaving. Either serialize the tail check and write across all checkouts, or always prefix each record with a newline and tolerate blank lines. Update the acceptance criteria and add a deterministic test that inserts B’s partial append between A’s tail check and write.

- P8: Creating the outcome log lacks the directory sync needed for power-loss durability.

  **Location:** `.ai/tasks.md:147–154,219–221`; `.ai/project-spec.md:28–32,62–73`.

  T007 creates `outcomes.jsonl` with `O_CREAT` and fsyncs its file descriptor, but never fsyncs its parent directory. File fsync alone does not guarantee persistence of a newly created directory entry. T003 can subsequently remove and durably sync the attempt marker in another directory. After power loss, the newly created log can be absent with no marker available to reconstruct the attempt.

  This affects the new outcome’s durability, which CU-5 promises; it does not require repairing historical rows.

  **Concrete plan change:** Persist the log’s directory entry before append success permits marker removal, including necessary newly created parent directories. Treat sync failures as telemetry failures that retain the marker. Add fault-injection tests for sync ordering and directory-sync failure.

## MINOR findings

None.

## Validation and limitations

Inspected repository guidance, all seven tasks, spec, plan, dispositions, state, handoff, relevant source, prompts, tests, documentation, validation scripts and revision history.

Observed:

- Task queue validation passed.
- Relevant shell syntax and Python AST checks passed.
- Three documentation consistency tests passed.
- Existing shared-prompt-contract and table-cell-pattern methods passed through direct invocation without fixture setup.
- The in-memory concurrency probe reproduced P7.

The full gate and fixture-based integration tests require filesystem writes and were not run in this read-only sandbox. Power-loss behavior was assessed from the prescribed sync ordering, not experimentally tested. Model selections are appropriate. No files were modified or network integrations invoked.