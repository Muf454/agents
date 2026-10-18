<!-- Host evidence: HEAD da84933830d7f33769adfcdd35c9ca276a803006; merge-base edc3dc645116166472720cebd2d982b649ab14ff; saved 2026-10-18T06:38:58Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED — one MAJOR requirement gap and one MINOR defect.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `da84933830d7f33769adfcdd35c9ca276a803006`

Supplied base and verified merge-base: `edc3dc645116166472720cebd2d982b649ab14ff`

## Scope and validation

Inspected repository instructions, specification, plan, tasks, state, handoff, plan-review dispositions, relevant documentation, scoped Git history/diff, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json`: PASS at `2026-10-18T06:35:31Z`, recorded at `143b3fc216621981adac2510c9552e4bf57a7882`.
- Referenced log: **962 tests passed in 617.5 seconds**.
- Independently verified that the validation fingerprint matches the reviewed content.

Checks independently run:

- Task queue validation.
- Python AST parsing and shell syntax checks.
- Three documentation-consistency tests.
- `git diff --check`.
- In-memory shell reproductions of both findings using the actual affected control-flow blocks and mocked process/provider behavior.

The full `./scripts/ai-check` and writing integration fixtures were not rerun because the review is read-only. No files were written or network/MCP integrations invoked. No live GitHub or model-provider behavior was tested.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — A failed draft-state lookup can falsely establish pipeline ownership

**Location:** `scripts/ai-pipeline:667–674`; subsequent un-draft at `scripts/ai-pipeline:679`.

**Requirement:** R15 permits automatic un-drafting only when the pipeline created or converted the PR to draft. A human-drafted PR must stay draft.

The initial `isDraft` query suppresses failure with `|| true`. Its empty result satisfies `"$is_draft" != true`, so a policy-draft run attempts `gh pr ready --undo`. If that command succeeds as a no-op on an already-draft PR, and the following query confirms draft status, the pipeline records `how: converted` despite never establishing that the PR was ready beforehand.

**Impact:** A transient lookup failure can turn a human draft into a purported pipeline draft. A later clean run consumes that false ownership record and marks the human PR ready.

**Evidence:** A two-run simulation of the actual shell branches, using the supplied mock’s successful no-op behavior for `ready --undo`, produced:

1. Human PR already draft; initial state lookup unavailable.
2. Pipeline records `pr-draft record … converted`.
3. Later clean run prints `Marked the PR ready (the pipeline had made it a draft).`

This does not require the documented human un-draft/re-draft limitation. The permissive initial-state fallback pre-existed; assigning durable ownership from it is introduced by this change.

**Recommended direction:** Require a successfully parsed initial `isDraft == false` before recording conversion ownership. An unknown initial state must not create ownership. Add a regression spanning the failed lookup and later clean run.

## MINOR findings

### N1 — A successfully completed detached plan can be reported as failed

**Location:** `scripts/ai-plan:72–87`.

The acknowledgement predicate accepts only `planning/active`. If the planner finishes between polls, its observation becomes `planning/done`; the child-exit branch then forces exit status 1 even when `wait` returns 0.

**Impact:** Mission control receives a launch failure for a successfully written plan and may unnecessarily retry it.

**Evidence:** Executing the actual exit branch with acknowledgement missed and a zero-exit child returned 1 and printed:

```text
ai-plan: the planning session ended early (exit 0)
```

The existing successful detached-start test deliberately keeps the child running. This issue was also identified as P21 in plan review round 9 and remains unresolved.

**Recommended direction:** Accept zero-exit completion with a matching PID’s `planning/done` observation as success, print the PID and log path, and return 0. Add a test that delays the parent’s first poll until planning finishes.

## Previous findings re-evaluated

Inspected the current-batch accepted plan findings against their implementations and regression tests: schedule hold/claim, exact-tree verification, task-bound preservation, implementation re-entry, terminal armed stops, dependency startup ordering, dispute reconciliation, safe detached logs, relative paths, draft-record revocation, and watchdog stall suppression.

Their corresponding mechanisms and tests are present. P21 remains as N1. No rejected finding is re-raised.

No separate pre-existing defect is reported.

## Missing coverage

- Failed initial PR draft-state lookup followed by a successful no-op draft command and a later clean run.
- Detached planning that completes successfully before acknowledgement.

Recorded tests cover many recovery transitions, but the full suite was not independently rerun.

## Security concerns

M1 crosses the intended human-control boundary for PR draft status. No additional demonstrated security defect was found in the inspected changes.

## Architecture concerns

The implementation retains standard-library dependencies and host-side authority records. The preserved-work recovery path is complex but has explicit contracts and substantial regression coverage.

**Flow chart updated:** the vault note has `updated: 2026-10-18` and describes the new planning, relaunch, and PR ownership flows. Same-session update timing was not independently established.

## Manual testing recommendations

### Needs you

- After fixes and acceptance, upgrade installed toolkit copies and reinstall watchdog timers.
- Verify a real usage-limit pause/resume and a real detached planning launch.
- Confirm human drafts remain draft on GitHub.

### Covered by automated tests

- Existing recovery, tree-binding, dashboard, planning, and draft-record tests.
- Add the two regressions described above; neither requires a human-only test.

Reviewing does not constitute human acceptance.