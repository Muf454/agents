<!-- Host evidence: HEAD 784048818167f38d41b230f188dd845f9c2a9722; merge-base 5894c2b23e0fc29fe3ab225a2bda707889967f91; saved 2026-10-15T08:06:31Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED. Queue fixes are verified; M3 is only partially resolved because GNU `timeout` descendants survive dispatcher shutdown.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=0

Reviewed HEAD: `784048818167f38d41b230f188dd845f9c2a9722`

Supplied base and verified merge-base: `5894c2b23e0fc29fe3ab225a2bda707889967f91`

## Scope and validation

Inspected repository instructions, spec, plan, tasks, state, handoff, review dispositions, relevant documentation, scoped Git history/diff, changes since `c9d092b`, and affected source/tests. The vault flow chart contains the planning/recovery changes and `updated: 2026-10-15`.

The checkout was clean. No files were written, and no network or MCP integrations were invoked.

Validation evidence observed:

- `.ai/local/validation.json`: PASS at `2026-10-15T08:02:12Z`, recorded at `26fb3ee`.
- Referenced log: **686 tests passed in 348.5 seconds**, using 48 batches on eight workers.
- `workflow.py stamp verify` confirms the validation fingerprint matches this checkout. The final commit changes only excluded bookkeeping.

Checks independently run:

- Current queue validation and discovery of 686 tests.
- Eight documentation, sanitization and timeout-policy tests: passed.
- Shell syntax checks for 13 files and Python AST parsing for seven changed files: passed.
- Existing test methods retained across the three changed test modules.
- In-memory queue regressions, review extraction, oversized-count handling, batch partitioning and timeout scaling.
- Process cleanup reproduction described below.
- `git diff --check`: passed.

The full `./scripts/ai-check` was not rerun because it writes validation records and fixture checkouts. Four-CPU CI performance remains unverified.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M3 — Dispatcher shutdown leaves GNU `timeout` descendants running

**Location:** `tests/run_parallel.py:263`, `tests/run_parallel.py:272`, `tests/run_parallel.py:231`. Relevant callers: `scripts/ai-run:265`, `scripts/ai-review:167`.

**Requirement:** T014 requires terminating every running batch, including subprocesses its tests started, when a worker fails or execution is interrupted.

**Problem:** Cleanup signals only the batch’s process group. GNU `timeout`, used throughout fixture pipelines, creates a separate process group. Its monitored command therefore escapes both group signals. The bounded drain now lets the dispatcher return, but closing its output pipe does not terminate those surviving processes.

**Evidence/reproduction:** A read-only reproduction exercised the actual `Dispatcher` with a synthetic batch launching `timeout 120 sleep 120`:

1. The batch and GNU `timeout` had different process groups.
2. `Dispatcher.stop()` terminated the batch.
3. The dispatcher returned after approximately **10.49 seconds**.
4. GNU `timeout` and its sleeping child remained alive; the child’s `/proc` state was `S`.

The reproduction processes were explicitly cleaned up. No descendant called `setsid`; ordinary GNU `timeout` was sufficient.

**Impact:** Interrupted or failed self-checks can leave fixture commands executing after batch shutdown and temporary-directory cleanup. The new tests cover a plain `sleep` child in the batch’s group, so they miss the process structure used by actual toolkit commands.

**Recommended direction:** Track and terminate descendant process groups before their parents disappear, or provide equivalent process-tree ownership. Retain bounded output draining as a fallback. Add regressions using GNU `timeout` around a sleeping child for worker failure and interruption/SIGTERM.

**Baseline distinction:** Descendant leakage existed before this range. This remains the accepted M3 cleanup requirement; T014 fixes the unbounded wait and same-group descendants but does not complete process-tree termination.

## MINOR findings

None found in the inspected scope.

## Previous findings re-evaluated

- **M2 fixed:** Non-task preamble sections survive reordering, and the repaired queue validates.
- **M3 partially fixed:** Shutdown is bounded, but descendants in GNU `timeout` groups survive.
- **N6 fixed:** Tab-separated task headings reorder successfully and remain unchanged.
- **N4/N5 fixes retained:** The actual plan report yields HEAD `e5e68b0`; oversized counts are rejected without crashing.

T006 was explicitly deferred in commit `cb69048`; it is not counted as missing implementation.

## Missing test coverage

- Cleanup of descendants moved into GNU `timeout` process groups, as demonstrated in M3.
- Notification-retention rollover through the real notification writer; current wait tests append directly.

## Security concerns

M3 concerns process cleanup and availability. The inspected dashboard additions retain bounded, pinned readers and advisory review counts. No additional demonstrated authentication or authorization defect was found.

## Architecture concerns

Dependencies remain minimal and host authority boundaries are preserved. Process-group isolation needs to account for nested groups created by existing toolkit commands.

## Manual testing recommendations

### Needs you

- Confirm the self-check passes well under ten minutes on the intended four-CPU CI runner.
- Exercise supervised plan revision and crash/resume in a scratch project.
- Confirm fixture pipelines stay hidden while real pipelines remain visible.
- Check dashboard review details and cursor-based waiting during live runs.

### Covered by automated tests

- Existing coverage addresses queue ordering, cycles, DONE preservation, revision recovery, discovery filtering, review parsing and wait transitions.
- Extend cleanup tests to nested GNU `timeout` groups and verify descendants terminate.
- Add notification-retention rollover coverage using the real writer.

Reviewing does not constitute human acceptance.