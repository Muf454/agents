<!-- Plan review of plan digest 2922b086d6f89b92c75cee9f5b71efca3e0c85956f8d61994149588461dcfb5b; saved 2026-10-05T07:00:18Z. -->

# Plan review

Overall verdict: REVISE PLAN — close the dispute-persistence interruption window before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=0

Reviewed HEAD: `840b9bad2e11a52419cfad3a746582e9b34a4112`

Scope: Repository instructions, spec, plan, all nine tasks, affected scripts and templates, existing tests, documentation, relevant vault notes, and stored validation evidence. No files were modified.

## BLOCKER findings

None.

## MAJOR findings

- P17: A saved re-check can bypass persistence of its upheld disputes on resume.  
  **Location:** `.ai/tasks.md:228–235`, `.ai/tasks.md:243–251`; `scripts/ai-pipeline:169–179`.  
  T007 triggers a re-check when no verified current report exists, then checkpoints its artifacts. It separately requires upheld answers to become durable dispute records. A crash after saving and checkpointing a valid re-check but before persisting those records leaves a report that satisfies the stated resume predicate. No reconciliation step explicitly imports missing disputes from an already valid report. Accepted fixes can then run and replace the original review, losing the upheld finding and allowing a normal PR. The planned interruption test stops before the re-check, so it misses this window.  
  **Concrete plan change:** On every start/resume, reconcile both the re-check report and dispute persistence. For an already verified report, ensure every upheld answer has a verified, checkpointed dispute record keyed by review digest and finding ID before implementation or review replacement. Make appending idempotent. Add a regression that interrupts after the re-check is checkpointed but before disputes are saved: resume must persist the original upheld answer exactly once, then run accepted fixes, and retain the dispute through a clean later review into a draft PR.

## MINOR findings

None.

## Validation observed

- Requested HEAD matched; the working tree was clean.
- Task-queue parsing passed.
- Bash syntax passed for 12 script/validation files.
- Python AST parsing passed for both helper modules and the test file.
- Inspected the mock-agent harness and relevant setup, recovery, review, and publishing tests; the suite contains 102 test methods.
- Stored evidence reports **102 tests passed** at `2026-10-05T06:29:14Z`, on earlier HEAD `7edb78b`.
- Current validation-stamp verification failed as stale.
- The integration suite and full gate were not run because they create temporary repositories, locks, logs, and evidence files, which this read-only sandbox prohibits.
- No network or MCP integrations were invoked.

## Security and architecture assessment

The revised plan addresses the previously reported restart and remote-HEAD gaps. No additional model-selection mismatch was identified. The remaining concern is completing dispute persistence across interruption; the finding above concerns the proposed protocol, not a demonstrated implementation regression.

## Manual testing recommendations

After implementation, interrupt execution between re-check publication and dispute persistence. Confirm that resume retains the upheld finding, avoids duplicate records, and opens or converts the PR to draft. Human acceptance remains outstanding.