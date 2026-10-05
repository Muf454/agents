<!-- Plan review of plan digest c3d2b83d9f6a87abebb9e63ccf8e73d2adeb772a7bfedde0f02659cac0e6f12e; saved 2026-10-05T06:51:53Z. -->

# Plan review

Overall verdict: REVISE PLAN — close the restart gap before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `04f43d1bbfc251ea1ba8a2573cf9e03587ea169d`

Scope: Repository instructions, spec, plan, nine tasks, affected scripts and templates, existing tests, validation evidence, documentation, and relevant vault notes. No files were modified.

## BLOCKER findings

None.

## MAJOR findings

- P15: A restart can skip re-checking rejected findings when accepted fixes remain TODO.  
  **Location:** `.ai/tasks.md:226`, `.ai/tasks.md:242`; `scripts/ai-pipeline:169`, `scripts/ai-pipeline:185`.  
  T007 places restart handling in the completed-dispositions “early-exit path.” In the actual pipeline, pending tasks run before that path, and the path requires all tasks DONE. Consider mixed accepted/rejected findings followed by a crash after triage’s stage is cleared but before the re-check. On restart, accepted fixes can run first, causing a new review to replace the original report before its rejected findings receive a re-check or durable dispute record. T004’s triage reconciliation does not close this window. The proposed mixed-disposition test restarts after a later clean review, missing this earlier interruption.  
  **Concrete plan change:** On every start/resume, reconcile pending re-checks and persist upheld disputes before running any task or replacing the implementation review, regardless of task completion. Keep this obligation pending until the bound artifacts are checkpointed. Add a regression that interrupts after mixed triage completes but before re-check: resume must re-check the original rejected findings first, then implement accepted fixes, and retain any upheld dispute through a later clean review and draft PR.

## MINOR findings

- P16: The remote-HEAD invariant lacks a regression that isolates its failure.  
  **Location:** `.ai/tasks.md:158`, `.ai/tasks.md:164`; `tests/test_workflow.py:1028`.  
  T005 requires comparing remote branch HEAD with local HEAD, but its acceptance scenarios exercise source changes, dirty trees, and failed pushes. Those can fail other readiness checks without exercising remote equality. The existing successful publishing test asserts that the remote branch exists, not that its commit equals final local HEAD.  
  **Concrete plan change:** Assert exact final SHA equality on the successful path. Add a successful-push scenario where a pre-push hook creates a workflow-only commit, leaving the checkout clean and other readiness checks satisfied while remote HEAD differs. Require a stop before PR creation or a successful-finish notification. Query the exact `refs/heads/<branch>` ref.

## Validation observed

- Requested HEAD matched; the working tree was clean.
- Task-queue parsing passed.
- Bash syntax passed for 12 scripts/validation files.
- Python AST parsing passed for both helper modules and the test file.
- Inspected 102 existing test methods and their mock-agent harness.
- Stored evidence reports **102 tests passed** at `2026-10-05T06:29:14Z`, on earlier HEAD `7edb78b`.
- Current validation-stamp verification failed as stale.
- Neither the integration suite nor the full gate was run: they write temporary repositories, logs, locks, and validation evidence, which this read-only sandbox prohibits.
- No network or MCP integrations were invoked.

## Security and architecture assessment

The revised plan explicitly addresses the previous recovery-scope, dispute-lifetime, contract-consistency, and documentation findings. No additional model-selection mismatch was identified. The remaining significant concern is preserving the re-check obligation across interruption before accepted fixes change the reviewed source.

## Manual testing recommendations

After implementation, supervise mixed-disposition recovery at the triage-to-re-check boundary, verify the final remote commit, and preview/apply an older-installation upgrade. Confirm that upheld disputes remain visible and convert an existing ready PR to draft. Human acceptance remains outstanding.