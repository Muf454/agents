<!-- Host evidence: HEAD 6cca6bf6879fdc22c1e3087fdcae4c970616237b; merge-base 20fe2ab452cdd7917af6c11e715fbff0ad6b4489; saved 2026-10-21T21:29:58Z. -->

# Independent review

Overall verdict: APPROVE WITH MINOR FINDINGS — previous findings are fixed; two localized integration gaps remain.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

Reviewed HEAD: `6cca6bf6879fdc22c1e3087fdcae4c970616237b`

Supplied base and verified merge-base: `20fe2ab452cdd7917af6c11e715fbff0ad6b4489`

## Scope and validation

Inspected repository instructions, specification, plan, tasks, state, handoff, previous review/dispositions, relevant documentation, Git history, the full supplied diff, changes since round 2, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json` records PASS at `2026-10-21T21:26:19Z`, on revision `72bda9c12cd2c8c0c2f5dcbbaf8b179df7057b65`.
- Its referenced log reports **1,107 tests passed**.
- Independent `stamp verify` confirms that evidence matches the reviewed content.

Checks independently completed:

- Python AST checks across nine files and shell syntax checks across 14 files.
- Discovery of 1,107 tests and execution of three passing documentation-consistency tests.
- Task queue validation and `git diff --check`.
- Write-free reproductions using actual helpers, with storage inputs and writes mocked where necessary.

Previous findings **M1, M2, M3, N1, N2 and N3 are fixed**: registry capture precedes discovery; indirectly moved tasks consume claims; missing routing records retain Codex; routed reviews default to opus while preserving overrides; both state variables are isolated independently; advisory scans refresh the overlap report.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because the sandbox is read-only. Discovery required pinning Python’s temporary-directory value to avoid its write probe. No project files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N4 — Triage section repairs bypass ruling claims and logging

**Location:** `scripts/ai-run:658`, before `ai_queue_ruling` at line 663.

**Requirement:** R2/R3 and assumption A2 require bounded, logged rulings for section repairs after triage. The uncapped exceptions cover planning and plan-revision sessions.

**Problem:** Triage calls `tasks fill-sections` before the ruling helper scans the queue. Missing sections are therefore already repaired when preflight runs, so it neither claims `task-sections:TASK` nor writes its ruling row.

**Impact:** These triage repairs remain unlogged and can repeat despite an existing claim. The impact is limited to empty sections; queue-order claims still work.

**Evidence:** Running the actual fill and preflight helpers in sequence, with queue writes held in memory, repaired a TODO task’s missing `Result / notes`. The following preflight returned no changes, leaving nothing for the ruling helper to claim or log.

**Recommended direction:** Let the claimed preflight path perform triage section repairs before queue validation. Test first repair, refused repeat, and the resulting run-log row.

This is a gap in the new ruling contract around retained legacy behavior.

### N5 — Outcomes report incorrectly requests catch-up for routed reviews

**Location:** `scripts/lib/workflow.py:4696`.

**Requirement:** R6 and assumption A12 distinguish routed reviews from fallback reviews: routed reviews need no Codex catch-up.

**Problem:** `outcomes_report()` treats every reviewer beginning with `claude` as a fallback, including the newly introduced `claude-routed`.

**Impact:** `ai-status --outcomes` reports a successfully routed review under “Codex catch-up pending,” contradicting its review record and PR description and suggesting unnecessary work.

**Evidence:** The actual reporting function, given a Codex code-review row followed by a `claude-routed` row, listed the routed row under `## Claude-only reviews (Codex catch-up pending)`.

**Recommended direction:** Exclude routed reviews from catch-up accounting while preserving fallback behavior. Add a reporting regression alongside the existing catch-up tests.

The reporting filter predates this branch; introducing the routed reviewer category creates this integration regression.

## Missing coverage

Add automated regressions for:

- Triage section repairs consuming a claim and writing a ruling row, with repeats refused.
- Routed reviews remaining visible in reviewer statistics without appearing as catch-up pending.

The recorded suite covers the earlier accepted findings but misses these integration cases.

## Security concerns

No additional demonstrated security, authentication or authorization defect was found in the inspected changes. The previous routing authority defect, M3, is fixed.

No unrelated pre-existing defects are counted.

## Architecture concerns

The implementation retains standard-library helpers and minimal dependencies. The remaining issues concern inconsistent use of the shared ruling path and an existing report’s handling of a new reviewer category.

**Flow chart updated:** the inspected vault note has `updated: 2026-10-21` and documents the workflow changes. Same-session editing timing was not independently established.

## Manual testing recommendations

### Needs you

After the normal toolkit upgrade, observe reviewer selection, attribution, notifications and resumption during a real fix round and Codex-limit window using the actual CLIs.

### Covered by automated tests

Queue repair, ruling lifecycle, retries, routing, limit memory, attribution and registry isolation have recorded automated coverage. Add the two regressions above and run `./scripts/ai-check` after any fixes.

Reviewing does not constitute human acceptance.