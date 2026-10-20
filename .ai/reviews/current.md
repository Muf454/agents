<!-- Host evidence: HEAD 74034f7904b8b0f181c2e9e6d6d56bd3ba07fa21; merge-base c32f7684f967aaa8be5935e38272a70fb00fe313; saved 2026-10-20T22:29:18Z. -->

# Independent review

Overall verdict: PASS — no findings in the inspected scope; both accepted MAJOR findings are fixed.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=0

Reviewed HEAD: `74034f7904b8b0f181c2e9e6d6d56bd3ba07fa21`

Supplied base and verified merge-base: `c32f7684f967aaa8be5935e38272a70fb00fe313`

Previous-round delta: `5c73c56d55b8e9b4548855151255aa67e19f62b3..74034f7904b8b0f181c2e9e6d6d56bd3ba07fa21`

## Scope and validation

Inspected AGENTS.md, specification, plan, relevant tasks, state, handoff, review/dispositions, documentation, Git history, both requested diffs, and affected source/tests. The checkout was clean before and after review.

Validation observed:

- `.ai/local/validation.json` records PASS at `2026-10-20T22:27:42Z`, on revision `c7955203b5ce3675d9998f0414015e6a05a746d3`.
- Its referenced log reports **1,035 tests passed in 685.2 seconds**.
- Independent `stamp verify` confirms the recorded fingerprint matches this checkout. Subsequent changes affect only excluded workflow records.
- Independent discovery finds 1,035 tests.

Checks independently run:

- Three documentation-consistency tests passed.
- Fixture-free assertions passed for background-gate instructions, shared prompt contracts, and the protected-path list.
- Task queue validation, Python AST parsing, and shell syntax checks across 14 files passed.
- Original and revised guard digests match.
- `git diff --check` reports an extra blank line at `.ai/tasks.md:3984`; this is cosmetic.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because the sandbox is read-only. No project files were written or network/MCP integrations invoked.

## Previous finding verification

- **M1 fixed:** lock waiting is capped by `AI_CHECK_TIMEOUT` and deducted from the validator’s remaining budget. Exhaustion returns 124 without starting validation.
- **M2 fixed:** the pre-acquisition timeout path no longer invokes `stamp invalidate`. Remaining stamp mutations occur after lock acquisition.
- T046’s regressions directly cover preservation of RUNNING/PASS evidence and concurrent content-change detection. Their assertions would detect the original stamp-overwrite defect.
- **N1 remains fixed:** decimal normalization and leading-zero regressions remain present.
- **N2 fixed:** the handoff identifies T045 as DONE and directs the next reader to review.
- **N5 remains fixed:** executable repair uses the guard’s shared protected-path list and skips roots and descendants.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

None found in the inspected scope.

## Missing coverage

Positive retry integration tests use RUNNING evidence. Equivalent end-to-end cases for PASS and changed-content evidence would strengthen coverage; helper tests already verify their classification. This is not a demonstrated correctness gap.

## Security concerns

No additional significant security or authorization defect found in the inspected changes. Stamp outcome reading remains bounded, nonblocking, and protected against symlink following. A retry still requires a host gate, and eventual completion requires a later DONE checkpoint with validation.

No pre-existing defect is counted among the findings.

## Architecture concerns

The changes preserve host-controlled, bounded retries and add no dependencies. The protected-path refactor preserves guard-digest compatibility.

**Flow chart updated:** the inspected vault note documents background validation, lock waiting, shared timeout accounting, stamp preservation, retry notifications, and protected-path exclusions.

## Manual testing recommendations

### Needs you

After the normal toolkit upgrade, observe a real slow-gate Claude session: confirm background execution, result reading, and no edits or commits during validation. If a gate-only block occurs, confirm one retry notification and a fresh session.

### Covered by automated tests

Recorded coverage includes manifest lifecycle, safe stamp reading, combined timeout budgets, concurrent stamp preservation and change detection, one-time retry, neighboring BLOCKED cases, and protected-path exclusions.

Reviewing does not constitute human acceptance.