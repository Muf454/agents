<!-- Host evidence: HEAD 92d1e9277994d5701fbf7e9153f90d69fe387bfc; merge-base 1423b6092c4fe6a14d98d5c39f6380d69039141a; saved 2026-10-19T03:05:56Z. -->

# Independent review

Overall verdict: APPROVE WITH MINOR FINDING — both prior major findings are fixed; one localized R3 requirement gap remains.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `92d1e9277994d5701fbf7e9153f90d69fe387bfc`

Supplied base and verified merge-base: `1423b6092c4fe6a14d98d5c39f6380d69039141a`

## Scope and validation

Inspected repository instructions, specification, plan, tasks, state, handoff, dispositions, relevant documentation, Git history, the full supplied diff, changes since the previous review, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json`: PASS at `2026-10-19T03:02:55Z`, recorded at `2ff4074`.
- Referenced log: **1,005 tests passed in 668.0 seconds**, matching 1,005 collected.
- Independently verified that the validation fingerprint matches the reviewed checkout despite subsequent metadata commits.

Checks independently run:

- Task queue validation and test discovery: 1,005 tests.
- Three documentation-consistency tests: passed.
- Python AST parsing of three affected files and shell syntax checks across 14 files: passed.
- `git diff --check`: passed.
- AST comparison against the base: 40 test methods added; none removed.
- Read-only checks of the actual gate-time selection and timeout-manifest validation functions.
- Read-only reproductions of executable repair and post-session handling, with mutations intercepted or external behavior stubbed.

The full `./scripts/ai-check` and integration fixtures were not rerun because they require filesystem writes. No project files were changed and no network/MCP integrations were invoked.

## Previous-round verification

- **M2 fixed:** repair uses a pinned root, no-follow directory traversal, a regular-file check, and descriptor-based `fchmod`. The added regression covers an external parent-directory symlink. An independent read-only probe rejected a real parent symlink without requesting chmod.
- **M3 fixed:** repair runs inside `claude_session` before nonzero-result termination. Independent shell-fragment checks reached repair for exit codes 0, 124, 137 and 1. Added tests cover timeout repair and successful recovery afterward.
- **N3 fixed:** state reports 36 completed tasks, PASS validation and readiness for review; handoff gives current next actions.
- **N4 fixed:** the vault chart now includes executable repair before host checks and timeout handling, with `updated: 2026-10-19`.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N5 — Executable repair omits several protected gate paths

**Location:** `scripts/lib/workflow.py:4467–4478`; complete protected-path list at `scripts/lib/common.sh:152–154`.

**Requirement:** R3 explicitly requires that gate paths are never touched by executable-bit repair.

The helper excludes `.ai/bin/`, `.ai/validate` and `.ai/ci-setup`, but does not exclude `.ai/prompts/`, `.ai/permissions.allow`, `.claude/settings.json` or `.github/workflows/ai-validate.yml`.

**Evidence:** Called the actual `exec_bits()` against this checkout with an intercepted `fchmod` and a mocked index entry equivalent to staging:

```bash
git add --chmod=+x -- .ai/permissions.allow
```

The helper reported restoring `.ai/permissions.allow` and requested mode `0755`. No permissions were actually changed.

An index-only mode change leaves the working-tree gate digest unchanged, so the pre-repair guard does not prevent this case.

**Impact:** The host can modify a protected gate file itself, contrary to R3, and cause a subsequent integrity check to stop the run. This is a localized reliability gap; no gate-bypass execution was demonstrated.

**Recommended direction:** Exclude every protected gate root and descendant. Add regressions using staged executable modes for the omitted protected paths.

## Missing test coverage

- Repair exclusions need coverage for the complete protected-path set described in N5.
- Exit 137 reaches repair in the independent fragment check, but the added end-to-end timeout tests exercise exit 124.
- FL-31’s performance improvement remains unverified: T031 lacks before measurements, and T032 made no pipeline-run conversions. The plan expressly permits an explained no-conversion result.

## Security concerns

The prior symlink-containment defect is fixed. N5 permits an unintended protected-file permission change, but subsequent integrity checks remain in place. No additional significant security or authorization defect was found in the inspected changes.

No pre-existing defect is counted among the findings.

## Architecture concerns

Dependencies remain minimal. Gate timing and timeout-rerun authority remain in host state, and the factored recovery commit retains dependency setup, full validation, checkpoint screening and committed-content verification.

**Flow chart updated:** the required vault note now includes executable repair and timeout recovery.

## Manual testing recommendations

### Needs you

After the normal toolkit upgrade, exercise a real slow-gate run and verify the displayed allowance, timeout notification, validated recovery checkpoint and resumed task. Human acceptance and merge remain outstanding.

### Covered by automated tests

Recorded passing coverage includes gate-time selection, session caps, timeout recovery limits, neighboring recovery cases, executable repair, decorated disposition restart handling, progress reporting, budget reporting and fixture independence.

Add the protected-path regressions from N5 and rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.