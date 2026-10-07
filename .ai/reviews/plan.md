<!-- Plan review of plan digest d545e7c240c63337edd97eefbdf5511efc40a410716a49b80f2c051e1ca3cecb; saved 2026-10-07T22:43:47Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED — make crash logging idempotent, require successful context preparation, and correct T003’s model.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=1

Reviewed HEAD: `ae9bd39065ef9b5ea22a85cea55c5d1d32b665b4`.

Inspected repository guidance, spec, plan, tasks, state, handoff, previous review dispositions, relevant scripts and helpers, test fixtures, validation entry points, reviewer prompts, workflow documentation, reference patches, and the vault flow chart. This is a review of the proposed implementation; the changes have not been implemented.

## BLOCKER findings

None.

## MAJOR findings

- P1: **Appending an outcome and removing its marker is not crash-safe or idempotent.**

  **Location:** `.ai/tasks.md:96`; `.ai/project-spec.md:28`; `scripts/lib/workflow.py:2049` and `:2069`.

  T003 prescribes two separate operations: append an outcome, then remove the marker. A SIGKILL between them leaves both the outcome and its marker. The next reconciliation appends another `crashed` outcome for the same attempt. Reconciliation itself has the same append-before-remove window.

  The existing outcome helper always appends and calculates the attempt number from previous rows; it has no attempt identity or duplicate check. Consequently, a previously recorded `done` can be followed by a spurious `crashed`, inflating attempts and making the report treat the completed task as unfinished. This violates R2’s single-outcome requirement. Atomic marker replacement alone also does not establish durability across the explicitly supported power-loss case.

  **Concrete plan change:** Give each attempt a unique ID stored in both its marker and outcome. Make finalization and reconciliation recognize an already recorded ID and remove the stale marker without appending again. Specify durable ordering for successful marker/outcome writes before starting the session or removing the marker. Add fault-injection tests at the boundary after a normal outcome append and after a reconciliation append; repeated recovery must preserve exactly one outcome and its original result.

- P2: **T003 uses Sonnet for locking-sensitive crash recovery.**

  **Location:** `.ai/tasks.md:90` and `:96`; `.ai/current-plan.md:6`; `CLAUDE.md`, task-model selection rules.

  T003 establishes whether another runner is live, places reconciliation behind the checkout lock, and coordinates atomic persistent state with outcome logging. This is concurrency and locking work. The explicit `Model: sonnet` conflicts with the required Opus assignment for that risk category.

  **Concrete plan change:** Set T003 to `Model: opus` and update the corresponding model in `.ai/current-plan.md`. Keep its locking and crash-boundary tests in the task.

- P3: **Context preparation needs explicit failure handling before the reviewer starts.**

  **Location:** `.ai/tasks.md:19`; `scripts/ai-review:152`.

  T001 specifies the context commands and cleanup but does not require checking each preparation failure. The existing caller invokes `claude_attempt "$prompt" || code=$?`. Bash suppresses `errexit` inside functions called in that conditional context, including nested functions. A straightforward `review_context` containing consecutive commands therefore can continue after a failed Git command or file write and launch Claude with incomplete context.

  A read-only shell reproduction using that call structure confirmed that a failing context command continued to the simulated session and returned status zero. With Bash removed from the reviewer, the reviewer cannot regenerate the missing diff independently.

  **Concrete plan change:** Require explicit failure checks for every mandatory context command and write. On failure, remove partial context, stop before invoking Claude, and preserve the prior review. Add a test that fails a context-generation Git command after preflight and asserts no Claude invocation, no publication, and cleanup.

## MINOR findings

- P4: **The malformed-queue retry criterion assumes the wrong attempt number for its named fixture.**

  **Location:** `.ai/tasks.md:65` and `:77`; `tests/test_workflow.py:1084`.

  The existing test runs five modes against the same checkout, branch, and T001, repairing and committing between modes. With the planned logging, `bad-format` follows four recorded attempts. Its subsequent successful retry cannot be attempt 2 in that fixture; it would be attempt 6.

  **Concrete plan change:** Put the malformed-queue-and-retry case in a fresh fixture if asserting attempts 1 and 2, or assert that recovery increments the preceding attempt number by one. Retain `first_pass=false`.

## Missing test coverage

Add the crash-boundary and context-preparation failure tests identified above. The proposed tests otherwise cover the main reviewer modes, timeout codes, interruptions, malformed results, validation failures, usage-limit retries, and triage exclusion.

The handoff’s “Covered by automated tests” list currently describes planned coverage; it is not implementation evidence.

## Security concerns

Removing Bash, Edit, Write, and inherited runner permissions addresses the accepted reviewer command-execution finding. The plan appropriately retains publication bindings and checkout checks.

Read access remains broader than the checkout; the proposed prompt restriction is an instruction, not filesystem isolation. The pending live Claude CLI check remains necessary to verify actual tool enforcement.

## Architecture concerns

The changes reuse existing host-state and review-publication mechanisms without adding dependencies. The new attempt marker needs an idempotent finalization contract, as described in P1.

The deferred outcome-report findings remain outside this review’s implementation scope.

## Validation observed

- Python syntax parsing passed for four source/test files.
- Bash syntax checks passed for 13 scripts and validation entry points.
- Test discovery collected 272 cases; test bodies were not executed.
- A reduced shell reproduction confirmed conditional function invocation suppresses `errexit`.
- HEAD and tracked/untracked Git status remained unchanged.

Not run: `./scripts/ai-check`, `.ai/bin/ai-check`, integration tests, or live Claude CLI checks. Those checks require filesystem writes unavailable in this read-only review. No files were modified and no network or MCP integrations were invoked.

## Manual testing recommendations

### Needs you

Perform the planned live Claude reviewer tool-enforcement check in a disposable fixture. Installed-copy upgrades remain subject to human approval.

### Covered by automated tests

Implement the proposed regression coverage plus P1’s interrupted-finalization tests and P3’s failed-context test.

This review is not human acceptance.