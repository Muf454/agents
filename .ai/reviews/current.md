<!-- Host evidence: HEAD bc9d029e042679b8152f855ad72a454ed373fb29; merge-base 4fea72d51a543528c79a0afab423b935757d6acf; saved 2026-10-22T15:05:46Z. -->

# Independent review

Overall verdict: APPROVE WITH NITS — accepted finding M1 is fixed; one minor metrics requirement gap remains.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `bc9d029e042679b8152f855ad72a454ed373fb29`

Supplied base and verified merge-base: `4fea72d51a543528c79a0afab423b935757d6acf`

## Scope and validation

Inspected repository instructions, specification, plan, relevant task records, state, handoff, review dispositions, documentation, Git history, the full scoped diff, affected source, and relevant tests. Also inspected the changes since round 1 (`93f4920`). The checkout was clean.

Validation observed:

- `.ai/local/validation.json` records PASS at `2026-10-22T15:01:18Z`, on revision `4ee19d1ff59c47c0998fab0ac192067a008764e5`.
- Its referenced log reports **1,189 tests passed**, using 14 workers.
- Independently running `stamp verify` confirmed that the evidence matches the reviewed tree’s content.

Independent checks completed:

- Python AST parsing across 10 files and shell syntax checks across 14 files.
- Task queue validation, `git diff --check`, and merge-base verification.
- Write-free assertions covering gate parsing/merging, redaction, active-run detection, and session-gate thresholds and overrides.
- Execution of the actual post-commit shell block with command doubles: rewritten DONE content is rejected before recording a revision.
- Execution of actual recovery verification functions with mocked Git/store inputs: intact DONE content succeeds; rewritten content fails.
- Write-free reproduction of N1 below.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because this sandbox is read-only. No files were changed, and no network/MCP integrations were invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

**Previous M1 — fixed:** T223 checks DONE preservation after the revision commit and before recording acceptance. Recovery checks preservation against the same stage START before reporting `committed`. The added tests cover both the pre-commit-hook rewrite and recorded-stage recovery cases.

## MINOR findings

### N1 — Metrics can omit runs represented only by plan-revision outcomes

**Requirement:** Specification A13 and T211 require the run list to include run IDs from outcome rows and retained events. T211 explicitly specifies outcome rows of every kind, preserving runs after their events rotate away.

**Location:** `scripts/lib/workflow.py:5445`.

**Problem:** `metrics_data()` discards all outcome kinds except `task`, `review`, and `gate` before discovering run groups. Valid `plan_revision` outcomes therefore cannot preserve a run’s presence.

**Impact:** A run stopped during plan revision can disappear from metrics after its events rotate away, understating `runs` and `runs_without_events`. For example, a new run can reuse an existing plan review and stop after a revision records a needs-human decision.

**Evidence:** Calling the actual `metrics_data()` with one valid `plan_revision` outcome carrying a run ID and no retained events returns:

```json
{"v": 1, "projects": [], "runs": []}
```

The equivalent input with kind `review` retains the run with `result: "unknown"` and `events: 0`.

**Recommended direction:** Discover run groups from all supported outcome kinds, while retaining the narrower filters for individual metric calculations.

## Missing test coverage

Add a regression with a run represented only by a `plan_revision` outcome and no retained events. Require the run to remain listed with unknown lifecycle, zero events, null stops, and inclusion in project run counts.

Existing rotation coverage retains task/gate outcomes, so it misses N1.

## Security concerns

No additional demonstrated authentication, authorization, or exploitable security defect was found in the inspected changes. The accepted historical-record integrity finding M1 is addressed.

No pre-existing defects are counted.

## Architecture concerns

The separate event log, bounded stable lock, explicit run attribution, and shared gate-merging function follow the planned design. N1 is a localized filtering issue.

The vault flow chart shows `updated: 2026-10-22` and includes the revised plan-review decision and session-gate rule. **Flow chart updated** for the batch; T223 leaves that flow unchanged. Same-session editing timing was not independently established.

## Manual testing recommendations

### Needs you

After upgrading the installed toolkit, observe one real targeted-mode run and one follow-up plan revision. Check notifications and resumption, and compare one run’s metrics with its raw outcome/event records.

### Covered by automated tests

The recorded passing suite covers the new hook and recovery regressions, session contracts, event locking/rotation, gate identity, lifecycle events, and metrics attribution. Add the N1 regression and rerun `./scripts/ai-check` after fixing it.

Reviewing does not constitute human acceptance.