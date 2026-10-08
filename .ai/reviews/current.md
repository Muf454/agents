<!-- Host evidence: HEAD 373c89c6ce828e548276a88001631ca2722383a4; merge-base c7d4deea62c4743e4212270c88ea2fa5b39bead5; saved 2026-10-08T21:27:29Z. -->

# Independent review

Overall verdict: PROCEED WITH MINOR CORRECTION — the four scoped changes are implemented, with one remaining base-resolution edge case.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `373c89c6ce828e548276a88001631ca2722383a4`  
Supplied base and merge-base: `c7d4deea62c4743e4212270c88ea2fa5b39bead5`

Inspected the full range, Git history, repository guidance, specification, plan, tasks, state, handoff, prior review/dispositions, relevant documentation, changed source/tests, and validation evidence. Checkout was clean.

## Validation observed/run

- Recorded validation: **PASS**, exit 0, at `2026-10-08T21:23:55Z`, HEAD `e498fe4`. Its log reports **309 tests passed**.
- Independently verified that the validation fingerprint matches current content. Changes after that validated revision affect only state and run-log bookkeeping.
- Ran shell syntax checks: **12 files passed**; Python AST parsing: **4 files passed**.
- Read-only test discovery collected **309 tests**.
- Ran `DocsConsistencyTest`: **3 tests passed**.
- In-memory probes passed for five verdict forms, eight count-validation cases, and nine disposition-row cases.
- `git diff --check` passed.
- Confirmed the vault flow note contains the base-selection, startup-stop, publish-check and recovery changes, with `updated: 2026-10-08`; corresponding hub log entries exist.

**Limitations:** `./scripts/ai-check` and integration tests were not rerun because they require filesystem writes. Their fixtures and assertions were inspected; execution evidence comes from the recorded gate. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N1 — Automatically selected remote base can resolve to a different ref

**Requirement:** R2 requires using `refs/remotes/origin/B` when it is strictly ahead of local branch `B`. R3 requires stopping when that resolved commit is absent from HEAD.

**Location:** `scripts/ai-pipeline:90–99`, particularly the shorthand assignment at line 94 and resolution at line 99.

**Problem:** The ancestry checks use fully qualified refs, but selection sets `base_ref=origin/$base` and subsequently resolves that shorthand. Git gives a matching tag or local branch precedence over a remote-tracking ref.

**Impact:** A local branch or tag named `origin/main` can make `--base main` resolve an older commit while claiming to use the newer remote base. This restores the stale review range and can miss the required “moved past the branch” stop.

**Evidence/reproduction:** In the new `origin_with_main()` fixture, advance remote main with `advance_origin_main()`, leave the feature branch unmerged, and create local branch `origin/main` pointing at local `main`. The ancestry check selects the remote path, but `git rev-parse 'origin/main^{commit}'` resolves the local collision. Git’s locally installed `gitrevisions` manual confirms this precedence. This collision fixture was not executed here because creating refs requires writes.

**Recommended direction:** Keep `origin/main` as the display label, but resolve the automatically selected commit through `refs/remotes/origin/main`. Add a regression asserting the remote SHA and early stop despite a colliding local branch or tag.

The ambiguity for explicitly supplied shorthand refs predates this batch; this finding concerns the newly introduced automatic selection.

## Missing coverage

- Ref-name collision described in N1.
- Plan-review P10’s suggested rerun regression remains absent: advance origin to a commit already contained in the reviewed HEAD and verify reuse of the broader saved review. The unchanged `review_current` predicate permits that reuse, consistent with the explicit non-goal.
- Suffixed disposition rows lack direct review-history and PR-body output assertions. Inspection confirms both consume the shared regex with unchanged capture groups.
- Bold verdict-line support is implemented but lacks a dedicated regression.

Earlier accepted plan concerns about interrupted stages, detailed recovery diagnostics, publish-hook detection, and the base-resolution matrix have relevant tests. P9’s incorrect expected ref is corrected. FL-12 remains deferred, and its recovery parser is unchanged.

## Security concerns

No new security defect found in the inspected changes. Count validation still precedes report replacement; review bindings, triage scope checks and re-check protections remain intact. The advanced-base recovery arm escalates before any recovery Claude session.

## Architecture concerns

Changes remain small and localized, add no dependencies, and preserve installed gate files. Verdict extraction is shared between publication and PR rendering. Flow chart updated.

Pre-existing defect excluded from counts: the prior review’s N7 queue-decoding issue remains in `outcome_title`; its fallback still catches only `OSError`. This batch does not change that code.

## Manual testing recommendations

### Needs you

- Confirm the stop message and notification in a real checkout whose remote base advanced. Merge the base only after interrupted triage/re-check processing finishes and the pipeline stops.
- After merge, approve installed-copy upgrades separately.

### Covered by automated tests

- Review format acceptance/rejection and prior-report preservation.
- Base-selection matrix and unchanged PR target.
- Startup and publish-path stops, recovery diagnostics, interrupted-stage completion, and merge/rerun behavior.
- Suffixed triage rows and re-check binding.
- Add the ref-collision regression from N1 and saved-review reuse coverage from P10.

This review does not constitute human acceptance.