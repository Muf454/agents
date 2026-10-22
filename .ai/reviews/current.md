<!-- Host evidence: HEAD 93f4920ee543fc919e2d327e13987eb500ccf7f3; merge-base 4fea72d51a543528c79a0afab423b935757d6acf; saved 2026-10-22T14:01:51Z. -->

# Independent review

Overall verdict: REQUEST CHANGES — the DONE-block preservation requirement has a gap around commit hooks.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=0

Reviewed HEAD: `93f4920ee543fc919e2d327e13987eb500ccf7f3`

Supplied base and verified merge-base: `4fea72d51a543528c79a0afab423b935757d6acf`

## Scope and validation

Inspected repository instructions, specification, plan, task records, state, handoff, plan-review dispositions, relevant documentation, Git history, scoped diff, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json` records PASS at `2026-10-22T13:56:47Z`, on revision `89086476c5ab60e95ca19e2462bd524313bc2498`.
- Its referenced log reports **1,187 tests passed**, using 14 workers.
- Independent `stamp verify` confirms that evidence matches the reviewed content.

Checks independently completed:

- Python AST parsing across 10 files and shell syntax checks across 12 scripts.
- Task queue validation and `git diff --check`.
- Write-free assertions for gate parsing and merging, active-run retention, metrics attribution and unavailable-data handling, redaction, and session-mode thresholds.
- Write-free reproductions of the finding below.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because the sandbox is read-only. No files were changed, and no network/MCP integrations were invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — Commit hooks can bypass DONE-block preservation

**Requirement:** Specification objective 5, assumption A14, and T214 require earlier DONE task blocks to remain unchanged during supervised plan revision.

**Location:** `scripts/ai-run:600`, `scripts/ai-run:629`, `scripts/ai-run:637`; recovery verification in `scripts/lib/workflow.py:3652`.

**Problem:** `plan-keeps-done` runs before the revision commit. A pre-commit hook can subsequently rewrite and stage an earlier DONE task. The remaining checks verify gate integrity, checkout cleanliness, and allowed paths; `.ai/tasks.md` is an allowed path. They never repeat the DONE-content check.

The host records the revision as accepted, and `plan_stage_verify()` can close its stage without detecting the altered block.

**Impact:** A follow-up revision can silently rewrite historical completion evidence despite the explicit preservation guarantee. Before this batch, supervised revision rejected queues containing any DONE task, so this path is newly enabled.

**Evidence:** A write-free harness executed the actual post-validation shell block with command doubles simulating a hook that changes and stages DONE content. The block recorded the revision and exited successfully. Separately, the actual `plan_stage_verify()` returned `committed` with mocked Git/store inputs representing that clean, in-scope commit. The actual `plan_keeps_done()` rejected the same rewritten task content when invoked.

This was not a writable end-to-end Git-hook test.

**Recommended direction:** Recheck DONE preservation after the commit and before recording an accepted revision. Enforce it when verifying a recorded stage during recovery as well, so interruption cannot bypass the check.

## MINOR findings

None found in the inspected scope.

## Missing test coverage

Add a follow-up revision regression whose pre-commit hook changes and stages an earlier DONE task’s result text while preserving valid statuses, allowed paths, gate files, and a clean checkout. Require rejection without an accepted revision record.

Cover recovery of the equivalent recorded stage. The existing `test_plan_review_followup_revision_keeps_done_blocks` checks session edits before the commit, so it misses this window.

## Security concerns

M1 concerns historical-record integrity across project hooks. No additional demonstrated exploitable authentication or authorization defect was found in the inspected changes.

No pre-existing defects are counted.

## Architecture concerns

The separate event log, stable bounded lock, explicit run attribution, and shared gate-merging function follow the planned design.

The vault flow chart has `updated: 2026-10-22` and includes the revised plan-review decision and session-gate rule. **Flow chart updated**; same-session editing timing was not independently established.

## Manual testing recommendations

### Needs you

After upgrading the installed toolkit, verify actual CLI behavior, notifications, and resumption for a follow-up plan revision and a usage-limit relaunch. Compare one real run’s metrics with its raw records.

### Covered by automated tests

The recorded suite covers session contracts, follow-up revisions, event locking/rotation, gate identity, lifecycle events, and metrics after rotation. Add the hook and recovery regressions above, then rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.