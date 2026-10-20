<!-- Host evidence: HEAD 01af1d237ca1c883002dddfda908400784b17036; merge-base c32f7684f967aaa8be5935e38272a70fb00fe313; saved 2026-10-20T20:32:46Z. -->

# Independent review

Overall verdict: REQUEST CHANGES — the main workflow changes are implemented, but lock waiting can exceed the run budget; one input-handling defect also remains.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `01af1d237ca1c883002dddfda908400784b17036`

Supplied base and verified merge-base: `c32f7684f967aaa8be5935e38272a70fb00fe313`

## Scope and validation

Inspected AGENTS.md, specification, plan, tasks, state, handoff, relevant documentation, previous review/dispositions, Git history, the complete supplied diff, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json`: PASS at `2026-10-20T20:28:49Z`, recorded at `4e5976c`.
- Referenced log: **1,027 tests passed in 675.4 seconds**, matching independent test discovery.
- Independently recomputed the fingerprint: it matches the reviewed checkout.

Checks independently run:

- Three documentation-consistency tests: passed.
- Background-gate prompt regression, invoked without writable fixture setup: passed.
- Task queue validation, Python AST parsing, and shell syntax checks across 14 files: passed.
- Old and new guard digest implementations produce identical values on this checkout.
- Read-only probes verified protected-path exclusions, manifest claim/repeat handling, resume preservation, invalid manifest shapes, and stamp classifications.
- Reproduced both findings below using extracted source, with project writes intercepted.
- Test comparison: 22 methods added; none removed.
- `git diff --check` reports a trailing blank line at `.ai/tasks.md:3811`.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because the sandbox is read-only. No project files were changed and no network/MCP integrations were invoked.

## Previous finding verification

**N5 is fixed.** The runner passes the guard’s protected-path list to executable repair. The helper skips each root and its descendants while allowing similarly prefixed sibling paths. Independent probes intercepted chmod; the guard digest remains unchanged. Existing no-follow traversal and repair-before-error handling remain present.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — Lock waiting gives validation a fresh, unspent run budget

**Location:** `scripts/ai-run:296–300`; `scripts/ai-check:18–28`.

**Requirement:** R3/A4 bounds host waiting by remaining run time. The plan says host gates count against that run time, and README describes waiting “within the run time.”

`host_gate` supplies the current remaining time as `AI_CHECK_TIMEOUT`. However, `ai-check` waits for the lock first, then starts that entire timeout. Time spent waiting is never deducted.

**Evidence:** A read-only reproduction exercised the actual lock/wait/timeout control flow with real `flock` contention on an anonymous kernel file, substituted bookkeeping, and a deterministic validator. With both limits set to two seconds, lock acquisition took 1.2 seconds and validation took another 1.2 seconds. The command returned **success after 2.4 seconds**.

**Impact:** A host gate can exceed the remaining run budget by up to 900 seconds, beyond ordinary termination overhead. The final gate can return success and publish readiness after the run deadline because that path does not check remaining time again.

**Recommended direction:** Share one deadline across lock acquisition and validation, deducting elapsed waiting before starting the validator. Return a timeout when the budget is exhausted; avoid passing zero to GNU `timeout`, which disables its deadline. Add contention tests for both successful validation within the total budget and exhaustion during waiting/validation.

## MINOR findings

### N1 — Accepted decimal wait values can fail as octal arithmetic

**Location:** `scripts/ai-check:15–19`.

**Problem:** The validation regex accepts digit strings such as `08` and `09`, but Bash interprets leading-zero values as octal in `(( wait > 0 ))`.

**Evidence:** A read-only probe of the held-lock branch with `AI_CHECK_LOCK_WAIT=08` passed the regex, then emitted:

```text
((: 08: value too great for base
Error: Validation is already running.
```

It exited immediately instead of waiting.

**Impact:** Otherwise valid seconds values fail only under contention and produce a misleading lock error.

**Recommended direction:** Normalize validated input to decimal before arithmetic, or consistently reject leading-zero forms. Add a held-lock regression for `08`.

## Missing test coverage

- Existing lock tests cover acquisition and refusal separately, but do not enforce a combined waiting-plus-validation deadline.
- Invalid-value tests omit leading-zero numeric inputs.
- Positive retry integration tests use a RUNNING stamp; PASS and changed-content outcomes are classified by helper tests but lack equivalent end-to-end retry cases.

## Security concerns

No additional significant security or authorization defect was found in the inspected changes. Stamp reading uses pinned directories, no-follow/nonblocking opens, regular-file checks, and bounded reads. Retry claims remain in host state, and acceptance still requires a later DONE checkpoint and host validation.

No pre-existing defect is counted among the findings.

## Architecture concerns

The shared protected-path list removes the earlier duplication without adding dependencies or changing the guard digest. Recovery remains host-controlled and bounded to one retry per task per run.

**Flow chart updated:** the vault note has `updated: 2026-10-20` and includes background gate waiting, host lock waiting, gate-only retry, the notification, and complete protected-path exclusions.

## Manual testing recommendations

### Needs you

After the normal toolkit upgrade, inspect a real slow-gate Claude session: confirm background execution, result reading, and no edits or commits during validation. If an unknown gate result still causes a block, verify one retry notification and a fresh session with the explanatory prompt.

### Covered by automated tests

Recorded passing coverage includes prompt contracts, safe stamp reading, manifest lifecycle, lock waiting/refusal, one-time retry, neighboring BLOCKED cases, and protected-path repair exclusions.

Add regressions for M1 and N1, then rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.