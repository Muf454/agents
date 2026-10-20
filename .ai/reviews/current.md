<!-- Host evidence: HEAD 5c73c56d55b8e9b4548855151255aa67e19f62b3; merge-base c32f7684f967aaa8be5935e38272a70fb00fe313; saved 2026-10-20T21:46:59Z. -->

# Independent review

Overall verdict: REQUEST CHANGES — the accepted findings are fixed, but the timeout handler introduces a validation-evidence race.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `5c73c56d55b8e9b4548855151255aa67e19f62b3`

Supplied base and verified merge-base: `c32f7684f967aaa8be5935e38272a70fb00fe313`

## Scope and validation

Inspected AGENTS.md, specification, plan, relevant tasks, state, handoff, documentation, previous review/dispositions, Git history, both requested diffs, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json`: PASS at `2026-10-20T21:44:26Z`, recorded at `607a8e8`.
- Referenced log: **1,033 tests passed in 665.7 seconds**.
- Independently recomputed fingerprint matches the reviewed checkout.
- Independent discovery also finds 1,033 tests.

Checks independently run:

- Three documentation-consistency tests passed.
- Background-gate prompt, shared prompt contract, and protected-list definition assertions passed without writable fixture setup.
- Task queue validation, Python AST parsing, and shell syntax checks across 14 files passed.
- Original and revised guard digests match.
- Read-only probes confirmed shared timeout accounting, successful execution within budget, and decimal handling of `08`.
- Reproduced M2 using actual lock/timeout control flow and the actual stamp function with in-memory storage.
- `git diff --check` reports a trailing blank line at `.ai/tasks.md:3916`.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because the sandbox is read-only. No project files were written and no network/MCP integrations were invoked.

## Previous finding verification

- **M1 fixed:** lock waiting is capped by, and deducted from, the validation budget. Exhaustion returns 124 without starting validation.
- **N1 fixed:** accepted numeric inputs are normalized with `10#`; regressions cover `08` and `00`.
- **Earlier N5 remains fixed:** executable repair receives the shared protected-path list, skips roots and descendants, and preserves the guard digest.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M2 — A waiter that never acquires the lock overwrites the active gate’s stamp

**Location:** `scripts/ai-check:22–23,31–32`; interaction with `scripts/lib/workflow.py:758–770`.

**Problem:** When lock waiting exhausts `AI_CHECK_TIMEOUT`, `out_of_time` invokes `stamp invalidate` despite never acquiring the validation lock. This replaces the active validator’s shared record, including its original `before` fingerprint.

**Impact:** The waiting check can corrupt another check’s evidence. In particular, it can conceal project changes during the active validation and let that validation record PASS. A race with completion can also replace completed evidence with RUNNING.

**Evidence/reproduction:**

1. Gate A acquires the lock and records its initial fingerprint.
2. Project content changes while A validates.
3. Gate B runs with `AI_CHECK_LOCK_WAIT=30 AI_CHECK_TIMEOUT=1`; A holds the lock beyond B’s deadline.
4. B exits 124 but first overwrites A’s stamp with a fresh fingerprint.
5. A exits zero. `stamp record` compares against B’s replacement fingerprint and records PASS with `unchanged: true`.

The read-only lock probe confirmed that the actual timeout path calls `stamp invalidate` while another descriptor holds the lock. A separate probe of the actual `stamp()` function, with storage and fingerprints substituted in memory, reproduced the false PASS.

The new test at `tests/test_workflow.py:10042` uses a lock holder without an active validation record, so it misses this interaction.

**Recommended direction:** Keep shared stamp mutations under the validation lock. A caller that times out before acquisition should report its timeout without replacing another run’s evidence. Add a concurrent-validator regression proving that the waiter preserves the active stamp and that content changes still fail validation.

## MINOR findings

### N2 — Handoff still presents completed T045 as pending

**Location:** `.ai/handoff.md:38,44,113–114`.

**Requirement:** AC7 requires the handoff to match delivered work.

**Problem:** The handoff labels T045 TODO and makes implementing its tests the next action. T045 is DONE in the queue, its tests are committed in `5d94082`, and current validation covers 1,033 tests. The validation section also stops at T044.

**Impact:** The operating guide directs the next reader toward completed work and leaves the accepted N1 fix appearing unfinished.

**Recommended direction:** Record T045 as complete, include its validation evidence, and update the next action to review and subsequent human checks.

## Missing coverage

- Concurrent validators with an active stamp when a waiter exhausts its deadline.
- Preservation of content-mutation detection across that timeout.
- End-to-end retry cases for PASS and changed-content stamps; current positive retry tests use RUNNING.

## Security concerns

M2 compromises validation-evidence integrity. No additional significant authentication, authorization, or security defect was found in the inspected changes. Safe stamp reading retains bounded, nonblocking, no-follow access.

No pre-existing defect is counted among the findings.

## Architecture concerns

The shared protected-path list removes duplication without adding dependencies or changing guard digests. Retry authority remains host-controlled and bounded once per task per run.

**Flow chart updated:** the vault note has `updated: 2026-10-20` and documents background validation, lock waiting, the shared deadline, gate-only retry, notifications, and protected-path exclusions.

## Manual testing recommendations

### Needs you

After the normal toolkit upgrade, observe a real slow-gate Claude session: confirm background execution, result reading, and no edits or commits during validation. If a gate-only block occurs, verify one retry notification and a fresh session with the explanatory prompt.

### Covered by automated tests

Recorded coverage includes prompt contracts, safe stamp reading, manifest lifecycle, lock waiting, combined budgets, decimal inputs, bounded retry, neighboring BLOCKED cases, and protected-path exclusions.

Add the concurrent-stamp regression for M2 and rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.