<!-- Host evidence: HEAD 41e45a825380b1cc72ac2558606bc93ddbfa1496; merge-base 20fe2ab452cdd7917af6c11e715fbff0ad6b4489; saved 2026-10-21T13:53:14Z. -->

# Independent review

Overall verdict: REQUEST CHANGES — one MAJOR routing requirement gap and two MINOR issues remain.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

Reviewed HEAD: `41e45a825380b1cc72ac2558606bc93ddbfa1496`

Supplied base and verified merge-base: `20fe2ab452cdd7917af6c11e715fbff0ad6b4489`

## Scope and validation

Inspected the repository instructions, specification, plan, task records, state, handoff, review dispositions, relevant documentation, Git history, full supplied diff, changes since the previous review, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json` records PASS at `2026-10-21T13:46:34Z`, on revision `1aae5fee85cda463660808ace280f5ea44830429`.
- Its referenced log reports **1,103 tests passed**.
- Independent `stamp verify` confirms that evidence matches the reviewed checkout.

Checks independently completed:

- Discovery found 1,103 tests.
- Three documentation-consistency tests passed.
- Python AST checks across nine files and shell syntax checks across 14 files passed.
- Task queue validation and `git diff --check` passed.
- Write-free reproductions exercised the findings below and the previous fixes. Storage, discovery, and Git inputs were mocked where necessary.

Previous findings **M1, M2 and N1 are fixed**: registry capture precedes discovery; indirectly moved tasks consume queue-order claims; routed reviews default to opus and preserve the human’s model override.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because the sandbox is read-only. No project files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M3 — Missing host records allow routing based on commit subjects

**Location:** `scripts/lib/workflow.py:3718`.

**Requirement:** R6, assumption A10 and T108 require routing from host records, with missing records retaining Codex.

**Problem:** When `fix_round_records()` returns `None`, `route_fix_rounds()` counts commits whose subject matches the triage subject. That substitutes agent-controlled Git history for the required host record.

**Impact:** A missing or deleted fix-round store can enable a routed Claude review without the required trusted fix-round evidence.

**Evidence:** A write-free reproduction used the actual routing functions with a missing fix-round store, a matching triage commit subject, an earlier host Codex review and a one-line low-risk diff. It returned `claude small low-risk fix round (1 lines)`. With an empty host store and identical history, it returned `codex first full code review`.

**Recommended direction:** Treat a missing store as no eligible fix round. Keep legacy migration separate from routing eligibility, and test that a triage commit subject alone cannot enable routing.

## MINOR findings

### N2 — Existing temporary state skips XDG isolation

**Location:** `tests/isolation.py:18`.

**Requirement:** R8/FL-33 and T111 require both `AI_STATE_DIR` and `XDG_STATE_HOME` to be isolated for tests and subprocesses.

**Problem:** Initialization checks only `AI_STATE_DIR`. If it already points under the temporary directory, the module leaves `XDG_STATE_HOME` untouched, including when it is unset.

**Impact:** A legitimate temporary host-state setting causes the new isolation test to fail. An existing external XDG setting also remains available to children.

**Evidence:** Executing the isolation module with `AI_STATE_DIR=/tmp/reviewer-state` and no `XDG_STATE_HOME` leaves XDG unset. The existing isolation test then raises `KeyError: 'XDG_STATE_HOME'` before creating its fixture.

**Recommended direction:** Validate and initialize both variables independently. Cover temporary AI state with missing or external XDG state.

### N3 — Advisory-only scans never save the overlap report

**Location:** `scripts/lib/common.sh:362`; `scripts/ai-run:447` and `scripts/ai-run:561`.

**Requirement:** Assumption A5 requires overlap reports to be printed and written to `.ai/local/preflight.md`.

**Problem:** For a valid queue, `ai_queue_ruling()` prints dry-run overlap output and returns before invoking the report writer. Planning and revision paths likewise use only dry-run preflight output.

**Impact:** Ordinary scans leave the promised report missing or stale, despite printing current overlaps.

**Evidence:** Exercising the actual shell function with a valid overlapping queue showed only `tasks preflight --dry-run` being called. The report-writing path was never reached.

**Recommended direction:** Refresh the advisory report after successful scans independently of whether a queue repair or commit is needed.

## Missing coverage

Add regressions for:

- Missing fix-round records combined with a matching triage commit subject.
- Temporary `AI_STATE_DIR` with unset or external `XDG_STATE_HOME`.
- Creating and refreshing the saved overlap report when no repair is required.

Existing tests cover nearby behavior but do not detect these cases.

## Security concerns

M3 weakens the specified boundary between host evidence and agent-controlled history. No additional demonstrated exploitable authentication or authorization defect was found in the inspected changes.

No pre-existing defects are counted. Legacy fix-round migration predates this change; its new use for routing eligibility is the issue reported in M3.

## Architecture concerns

The implementation retains minimal dependencies and deterministic host helpers. Routing should preserve its conservative behavior when authority records are missing.

**Flow chart updated:** the inspected vault note has `updated: 2026-10-21` and documents the batch’s workflow changes. Same-session editing timing was not independently established.

## Manual testing recommendations

### Needs you

After fixes and the normal toolkit upgrade, observe reviewer selection, attribution, notifications and resumption during a real fix round and Codex-limit window using the actual CLIs.

### Covered by automated tests

The recorded suite covers queue repair, ruling lifecycle, retries, routing, limit memory, reviewer attribution and registry isolation. Add the three regressions above and rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.