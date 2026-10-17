<!-- Host evidence: HEAD 617be4b80b1f8161d56c0238ee0d1721331900e6; merge-base df0d3c2e187c9308ebd893e9151cef98a43a4d9e; saved 2026-10-17T06:59:21Z. -->

# Independent review

Overall verdict: PASS WITH MINOR FINDINGS — no demonstrated BLOCKER or MAJOR defect in the inspected changes.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

Reviewed HEAD: `617be4b80b1f8161d56c0238ee0d1721331900e6`

Supplied base and verified merge-base: `df0d3c2e187c9308ebd893e9151cef98a43a4d9e`

## Scope and validation

Inspected repository instructions, specification, plan, tasks, state, handoff, review dispositions, relevant documentation, scoped Git history/diff, and affected source/tests. The checkout was clean.

Validation evidence observed:

- `.ai/local/validation.json`: PASS at `2026-10-17T06:55:24Z`, recorded at `52ef5dd468784cd5b9d9a221f65551e7892166dc`.
- Referenced log: **817 tests passed in 434.6 seconds**.
- Independent `stamp verify` confirmed that the fingerprint matches the reviewed content.

Checks independently run:

- Task queue validation, three documentation tests, Python AST parsing, shell syntax checks, and `git diff --check`.
- Discovery of 817 tests; no baseline test methods removed.
- Four existing pure test methods without their writing fixture setup.
- Independent checks covering 480 accepted finding-cell forms, 12 rejected forms, torn UTF-8 lines, U+2028, equal-second attempt ordering, and recovery-text shortening.
- Reproduction of N2 using the actual parser with mocked filesystem endpoints.

The full `./scripts/ai-check` and writing integration fixtures were not rerun because this review is read-only. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N1 — Marker documentation describes the superseded schema and ordering

**Location:** `docs/workflow.md:935`, `docs/workflow.md:938`

The documented required marker fields omit `seq`, and the listing order is described as oldest `started` first. Actual validation requires an integer `seq`, and valid markers sort by `(seq, filename)`.

**Impact:** The maintenance documentation gives an incorrect marker contract. A marker constructed from its documented field list is rejected as invalid and can be discarded during reconciliation.

**Evidence:** `MARKER_FIELDS` and `read_marker` at `scripts/lib/workflow.py:3274` require `seq`; `marker_sort_key` at `scripts/lib/workflow.py:3299` sorts by it. T012 explicitly changed both rules.

**Recommended direction:** Add `seq` to the documented fields and describe the actual ordering. This also completes T006’s documentation-consistency requirement.

### N2 — The advertised full recovery text is silently truncated

**Location:** `scripts/lib/workflow.py:2084`; related promise at `README.md:421`

R13 requires the full recovery reason and human action in `recovery-decision.txt` when the notification is shortened. The implementation instead slices each normalized value to 4,000 characters without marking that second truncation.

**Impact:** Someone following the notification’s “Full text” pointer can miss diagnostic details or instructions at the end. The original recovery log remains available, limiting the impact.

**Evidence:** A 5,143-character reason ending in `FINAL_DIAGNOSTIC_DETAIL` produced a sidecar payload containing exactly 4,000 reason characters, without the final detail or a truncation indicator.

T005 explicitly specifies the 4,000-character bound, so the implementation follows that task detail; it conflicts with the specification and user-facing promise.

**Recommended direction:** Preserve the complete normalized values as specified, or explicitly identify truncation and point to the complete recovery log. Reconcile the specification and documentation with the chosen behavior.

## Previous findings re-evaluated

The accepted batch-5 plan findings are addressed in the inspected implementation:

- Readable append descriptors, per-line UTF-8 decoding, complete-write checks, locking, and directory synchronization.
- Separate attempt markers, strict log reads, confirmation before removal, and retention after marker-read failures.
- Reconciliation before the dirty-checkout refusal and retention of printed attempt IDs after publication failures.
- Persisted sequence ordering, including late reconciliation, equal-second starts, and legacy rows.
- Stale recovery-sidecar removal and malformed finding-cell diagnostics.

No rejected finding was re-raised. No separate pre-existing defect is reported.

## Missing coverage

Add recovery-sidecar cases exceeding 4,000 characters for both reason and human action, asserting complete retention or explicit truncation with a pointer to the original log.

The documentation tests pass but do not detect N1. Recorded integration coverage was inspected; it was not independently rerun.

## Security concerns

No additional demonstrated security or authorization defect was found in the inspected changes. Gate-change stops avoid helper execution and remove the current attempt marker through the shell path.

## Architecture concerns

The changes use standard-library dependencies and retain advisory telemetry semantics. Protected installed copies remain unchanged, with upgrades documented as human work.

The vault flow chart has `updated: 2026-10-17`, includes crash reconciliation in its outcome-log description, and has a corresponding hub log entry. **Flow chart updated.**

## Manual testing recommendations

### Needs you

- After acceptance, refresh installed tooling and prompts through the documented upgrade process.
- Optionally verify one real SIGKILL/restart cycle in a disposable checkout.

### Covered by automated tests

- Disposition parsing and diagnostics.
- Append framing, locking, sync failures, marker retention, and reconciliation.
- Attempt ordering and legacy compatibility.
- Recovery boundary cuts, sidecar creation, and stale-file removal.
- Add the long-sidecar regression described under N2.

Reviewing does not constitute human acceptance.