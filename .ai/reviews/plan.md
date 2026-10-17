<!-- Plan review of plan digest 8118993f2167523afa944932b06f9916c3b22c36120f089b94285b18a81cb4e5; HEAD a557aff4702622ea8f1f437b7fc72c68bcecb718; saved 2026-10-17T02:19:48Z. -->

# Plan review — round 6

Overall verdict: REVISE BEFORE IMPLEMENTATION
Finding counts: BLOCKER=0 MAJOR=2 MINOR=0

Reviewed HEAD: `a557aff4702622ea8f1f437b7fc72c68bcecb718`

The revision addresses P15 when attempt start timestamps differ. Equal timestamps still reproduce the defect, and one new acceptance criterion contradicts the proposed ordering rule.

## BLOCKER findings

None.

## MAJOR findings

- P15: Delayed reconciliation can still overwrite a successful retry when attempts start in the same second.

  **Location:** `.ai/tasks.md:436`, `.ai/tasks.md:474`, `.ai/tasks.md:513`; `.ai/current-plan.md:194`.

  Markers store `started: int(time.time())`, and T011 breaks timestamp ties using append position. Suppose A opens and dies early, then B opens within the same second while A’s marker remains unreadable. B eventually succeeds; A becomes readable afterward and reconciliation appends its `crashed` row. Both starts are equal, so A sorts last: the task becomes not done and B incorrectly counts as a first-time pass.

  The claim that delayed reconciliation makes equal starts impossible does not hold. Neither the runner nor the helper imposes a minimum interval between opens; B’s duration and the later reconciliation delay do not change its start timestamp.

  **Evidence:** An in-memory evaluation of T011’s specified sort with B’s `done` followed by A’s `crashed`, both with `started=1000`, selects `crashed` as the final result and reports first-time pass as true. The planned regression artificially separates starts by 100 seconds and misses this case.

  **Concrete plan change:** Assign new attempts an ordering key at open that distinguishes sequential attempts independently of append order, such as a persisted sequence, and carry it unchanged into normal and reconciled outcomes. Define legacy compatibility separately. Add a deterministic regression with equal wall-clock seconds and A unreadable through B’s successful completion; repeated reconciliation must leave B as the final attempt.

- P16: T011’s legacy-row acceptance case requires the wrong final result.

  **Location:** `.ai/tasks.md:469`.

  The specified `done` row starts at 09:50, while the `error` row starts at 10:04. Ordering by start time therefore makes `error` the final result, yet the acceptance criterion requires the task to be done. Correct implementation cannot satisfy both this test and T011’s implementation instructions. The stated expectation instead preserves the existing last-appended-line behavior.

  **Concrete plan change:** Keep these inputs and require not done, with `error` as the final result regardless of file order. If a successful final result is intended, change the timestamps so `done` starts later. Explicitly test both file orders.

## MINOR findings

None.

## Validation and scope

Inspected repository instructions, spec, plan, all eleven tasks, prior dispositions, state, handoff, affected source, prompts, tests, documentation and `.ai/validate`.

Observed passing checks:

- Task queue validation.
- Three `DocsConsistencyTest` tests.
- Python syntax parsing for four relevant files.
- Shell syntax checks for five relevant files.

The ordering reproductions ran entirely in memory against the specified algorithm. The full gate and integration tests were not run because they require writable fixtures and artifacts. Implementation remains absent.

No additional authorization or model-selection findings were identified in the inspected scope. After implementation, verify that delayed reconciliation preserves a successful retry’s reported result.

No files were modified. No network or MCP integrations were invoked.