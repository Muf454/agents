<!-- Plan review of plan digest e319a0ea6e4cc1378ea7620adf2af4d3eb9b8c57d43d8ad03c077f8d68acba50; saved 2026-10-08T05:08:00Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED — crash recovery needs to handle incomplete and not-yet-durable outcome writes.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `a7956da09f0237964ad174ac2a9b7c61de2bbbea`.

Inspected repository guidance, spec, plan, tasks, state, handoff, relevant scripts/helpers, tests, validation entry points, reviewer prompts, documentation, previous review and reference material. Implementation remains pending.

## BLOCKER findings

None.

## MAJOR findings

- P1: **An incomplete outcome append can swallow the recovery row.**

  **Location:** `.ai/tasks.md:103`, `.ai/tasks.md:108`; `scripts/lib/workflow.py:2020`.

  T003 covers crashes after complete appends but does not specify recovery from a partially persisted final JSONL record. A single append followed by `fsync` does not protect against power loss before that `fsync` completes.

  If the partial record lacks its terminating newline, reconciliation appends `crashed` directly onto it. The existing reader skips the resulting malformed line, losing the recovery outcome too. Reconciliation then removes the marker, so the subsequent successful attempt can again appear as a first-time pass. A partial UTF-8 character can also prevent the reader from decoding the entire log.

  **Evidence:** an in-memory probe using the actual `read_outcomes` function retained a recovery row after a complete preceding line, but discarded it after an incomplete preceding line.

  **Concrete plan change:** specify safe handling of incomplete final records before appending recovery outcomes, including partial UTF-8. Preserve complete historical rows and coordinate repair with other writers because the log is shared across checkouts. Add boundary-state tests with a truncated record and a truncated multibyte character; repeated recovery must retain exactly one readable outcome for the attempt.

  The reader weakness is pre-existing; the gap concerns R2’s newly promised power-loss recovery.

- P2: **Finding an existing outcome does not prove it is durable.**

  **Location:** `.ai/tasks.md:103`, `.ai/tasks.md:108`; `.ai/project-spec.md:40`.

  The duplicate-ID path returns success without appending, and reconciliation removes an already-logged marker. Neither path explicitly requires syncing the existing outcome log first.

  A helper can be killed after flushing a complete row into the kernel cache but before `fsync`. Its successor can read that row, recognize the ID, and durably remove the marker. A subsequent power loss can then lose the unsynced outcome while retaining the marker deletion. This violates the required outcome-before-marker-removal durability order.

  The proposed tests construct existing rows through the helper’s completed, fsynced append, so they cannot catch this boundary.

  **Concrete plan change:** require the duplicate-ID success path to establish durability of the existing outcome before allowing marker removal. Add a test observing the synchronization order when the row already exists: outcome-log synchronization must precede unlinking and syncing the marker directory. Use test-side mocks rather than production crash hooks.

## MINOR findings

- P3: **The README’s outcome contract would remain outdated.**

  **Location:** `.ai/tasks.md:70`, `.ai/tasks.md:140`; `README.md:397`.

  T002/T004 update the workflow documentation and flow chart, but the README still enumerates only `done`, `blocked`, `validation_failed`, and `no_checkpoint`. It would omit the new stopped/crashed results and attempt identity.

  **Concrete plan change:** include the README’s “Outcome log” section in the documentation updates, covering the new results, attempt IDs, and crash reconciliation.

## Missing coverage

Add the incomplete-record and existing-but-unsynced-record tests above. The planned tests otherwise cover the principal review modes, context preparation failures, timeout/interruption outcomes, malformed queues, retry numbering, triage exclusion, and checkout-lock rejection.

## Security and architecture

The shell-free reviewer design addresses the accepted command-execution finding. Explicit models fit the planned risks.

Read access remains broader than the checkout; the prompt restriction does not provide filesystem isolation. The planned live Claude CLI check remains pending.

The host-state design reuses existing mechanisms without new dependencies. Its crash guarantees need the additional boundaries identified above.

## Validation observed

- Python syntax parsing passed for four source/test files.
- Bash syntax checks passed for 13 scripts and validation entry points.
- Test discovery collected 272 cases; test bodies were not executed.
- The read-only, in-memory outcome-reader probe reproduced P1.
- HEAD and Git status remained unchanged.

Not run: `./scripts/ai-check`, `.ai/bin/ai-check`, integration tests, or live CLI checks. They require filesystem writes unavailable in this review. No files were modified and no network/MCP integrations were invoked.

## Manual testing recommendations

### Needs you

Complete the planned live Claude reviewer tool-enforcement check in a disposable fixture. Installed-copy upgrades remain under human control.

### Covered by automated tests

Implement the planned regressions and the two additional crash-boundary cases above.

This review is not human acceptance.