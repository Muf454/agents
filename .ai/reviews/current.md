<!-- Host evidence: HEAD 31fb005a6b08a276d38f68b3a2b5d8235c25f123; merge-base 7d22939e12957f9ba744f563498161f970fe31ab; saved 2026-10-17T01:03:56Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `31fb005a6b08a276d38f68b3a2b5d8235c25f123`

Supplied base and verified merge-base: `7d22939e12957f9ba744f563498161f970fe31ab`

## Scope and validation

Inspected repository instructions, specification, plan, tasks, state, handoff, prior reviews/dispositions, relevant documentation, scoped Git history/diffs, and affected source/tests. Reviewed changes since `afa91c0` and the full supplied range. The checkout remained clean.

Validation evidence observed:

- `.ai/local/validation.json`: PASS at `2026-10-17T01:00:52Z`, recorded at `b92fd0b`.
- Referenced log: **744 tests passed in 384.7 seconds**, across 48 batches on eight workers.
- Independent `stamp verify` confirmed that the validation fingerprint matches HEAD.

Checks independently run:

- Task queue validation and discovery of 744 tests.
- Three documentation consistency tests: passed.
- Changed Python AST parsing, 13 shell syntax checks, and `git diff --check`: passed.
- Comparison confirmed no baseline test IDs were removed.
- In-memory checks: 1,365 cell round-trips through both disposition grammars, missing-cell row boundaries, nine catch-up cases, 15 recovery cases, and four task-section combinations.
- Real-process cleanup checks for a non-UTF-8 process name and a batch → separate GNU `timeout` group → sleeper: passed.
- Real-process reproduction of the scan-error defect below.

The full `./scripts/ai-check` and writing fixture tests were not rerun because this review is read-only. All reproduction processes were explicitly terminated and reaped. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M3 — Failed `/proc` enumeration falsely confirms cleanup completion

**Location:** `tests/run_parallel.py:216`, `tests/run_parallel.py:390`, `tests/run_parallel.py:437`.

**Requirement:** FL-27 requires confirming that descendants are gone or zombies before shutdown completes; inability to confirm cleanup must be reported. T014 additionally hardens scan-failure handling.

**Problem:** `process_table()` catches an `OSError` from `os.listdir('/proc')` and returns `{}`. Consequently, `Dispatcher.scan()` receives a successful empty result instead of recording a scan failure. Both the kill loop and completion barrier interpret this as confirmation that no descendants remain.

**Evidence:** In an isolated Python process, I enabled subreaping, started a real `sleep 120` child in its own session, confirmed it appeared in `live_descendants()`, then patched `/proc` enumeration to raise `PermissionError` and called the actual `Dispatcher.stop()`:

```text
Enumeration failure: scan() = {}
After stop: child alive = True
cleanup_failed = []
scan_error = None
stop_done = True
```

The detached child was explicitly killed and reaped afterward.

**Impact:** When `/proc` cannot be enumerated, detached fixture processes can survive while shutdown silently claims completion. The new test patches `descendants()` to raise, which bypasses the lower-level handler responsible for this defect.

**Baseline distinction:** Introduced within this review range; `process_table()` did not exist at the supplied base. The original non-UTF-8 failure is fixed, but this distinct scan-failure path remains.

**Recommended direction:** Preserve enumeration failure as an explicit unavailable result or propagate it to `scan()`. Keep batch-group termination independent, and let the completion barrier report unconfirmed cleanup after its deadline. Handle unavailable scans safely in the adopted-child reaper as well.

## MINOR findings

### N2 — Final handoff still identifies completed fixes as TODO

**Location:** `.ai/handoff.md:154`.

**Problem:** “Next action” says T015 and T016 are TODO and should precede re-review. Both tasks are DONE in `.ai/tasks.md`, their implementations are committed, and `.ai/state.md` identifies T016 as the last completed task.

**Requirement:** T010 requires the handoff to describe delivered behavior and remaining human steps accurately.

**Impact:** The final handoff gives the next reviewer or human an incorrect account of remaining work.

**Evidence:** Commits `bd4a419` and `85c4cb2` implement the two tasks; the recorded final validation includes their regressions.

**Recommended direction:** Update the handoff to acknowledge both completed fixes and state the actual next action.

## Previous findings re-evaluated

- **M1 / T014:** The non-UTF-8 process-name defect is fixed. An independent real-process cleanup check passed. M3 concerns a separate enumeration-error path.
- **M2 / T015:** Fixed. A targeted Codex re-check leaves a full Claude code review pending; a full Codex code review covers code and re-check records.
- **P7 / T016:** Fixed. Backslash/pipe encoding and decoding round-trip without shifting columns in the checked cases.
- **N1 / T016:** Fixed. Missing Task cells no longer consume the following row in either disposition grammar.

No rejected findings were re-raised.

## Missing coverage

Add a regression at the actual failure boundary: make `os.listdir('/proc')` raise an `OSError` while a detached descendant exists. Assert that shutdown records unconfirmed cleanup and emits a diagnostic instead of accepting an empty tree.

The existing injected `descendants()` exception test does not exercise this handler.

## Security concerns

M3 affects local process containment and availability. No additional demonstrated authentication or authorization defect was found in the inspected changes.

Scratch deletion uses pinned directory descriptors and no-follow opens. Its writing integration tests were inspected but not independently rerun.

## Architecture concerns

Dependencies remain limited to the standard library, and protected installed files and permission templates were preserved.

The process scanner must distinguish “no descendants found” from “descendants could not be inspected.”

The vault flow chart contains the task-section repair and scratch-clearing steps with `updated: 2026-10-17`; corresponding dated hub entries were observed. **Flow chart updated.**

## Manual testing recommendations

### Needs you

- After fixes and acceptance, refresh installed tooling and prompts through the documented upgrade process.
- Interrupt a real self-check on the intended host and inspect for leftover fixture processes.
- Compare catch-up output with real branch review history.

### Covered by automated tests

- Add the lower-level `/proc` enumeration-failure regression for M3.
- Retain the existing process-tree, startup-interruption, disposition, scratch, recovery, and catch-up regressions.
- Rerun `./scripts/ai-check` after fixes.

Reviewing does not constitute human acceptance.