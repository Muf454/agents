<!-- Host evidence: HEAD c9d092bf5eab8ad3c4398292651afc5fd784f77c; merge-base 5894c2b23e0fc29fe3ab225a2bda707889967f91; saved 2026-10-15T07:26:02Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED. Previous findings are fixed; dispatcher cleanup and a queue-parser edge case remain.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `c9d092bf5eab8ad3c4398292651afc5fd784f77c`

Supplied base and verified merge-base: `5894c2b23e0fc29fe3ab225a2bda707889967f91`

## Scope and validation

Inspected repository instructions, spec, plan, tasks, state, handoff, review dispositions, relevant documentation, full scoped diff, changes since round 1, and affected source/tests. Verified the vault flow chart contains the planning/recovery changes and `updated: 2026-10-15`.

The checkout was clean. No files were written, and no network or MCP integrations were invoked.

Validation observed:

- `.ai/local/validation.json`: PASS at `2026-10-15T07:22:54Z`, recorded at `afb2aeb`.
- Referenced log: **682 tests passed in 368.1 seconds**, using 48 batches on eight workers.
- `workflow.py stamp verify` confirms the fingerprint matches this checkout. Subsequent changes affect only excluded state/run-log bookkeeping.

Checks run:

- Current queue validation and discovery of 682 tests.
- Shell syntax checks: 13 files passed.
- Python AST parsing: seven changed files passed.
- Six documentation consistency and sanitization tests passed.
- No existing test methods were removed or renamed.
- Read-only checks verified previous fixes, batch partitioning, timeout scaling, cursor round-trip, wait change/timeout behavior, and both findings below.
- `git diff --check` passed.

The full `./scripts/ai-check` was not rerun because it writes validation records and fixture checkouts. Four-CPU CI performance remains unverified.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M3 — Dispatcher cleanup can hang while a test subprocess survives

**Location:** `tests/run_parallel.py:192`, `tests/run_parallel.py:224`, `tests/run_parallel.py:247`.

**Requirement:** T004 explicitly requires terminating running batches and joining every worker after interruption or a worker exception.

**Problem:** Batches start without process isolation, and `stop()` terminates only their immediate Python processes. A subprocess launched by a test survives. If it inherited the batch’s output pipe, `communicate()` continues waiting for EOF, and the dispatcher’s unbounded thread joins cannot finish.

**Evidence:** A read-only reproduction used the actual dispatcher with two workers:

1. The first batch launched a sleeping subprocess that inherited stdout.
2. The second worker’s launch raised an injected `OSError`.
3. Cleanup terminated the first batch with exit `-15`, but its subprocess remained alive and `Dispatcher.run()` remained blocked.
4. Killing that subprocess released the pipe; the dispatcher then exited with the original launch error.

All reproduction processes were cleaned up.

**Impact:** A worker failure can leave fixture commands running and stall the self-check until those descendants exit or an external timeout intervenes.

**Recommended direction:** Give each batch its own process group/session and terminate its process tree, with bounded escalation and reaping. Add deterministic worker-launch-failure and interruption tests while another batch has an active subprocess.

**Baseline distinction:** The previous runner also lacked descendant cleanup. This finding is an unmet requirement of the new T004 dispatcher, rather than a claim that the base runner handled this safely.

## MINOR findings

### N6 — Reorder crashes on tab-separated headings accepted by the task validator

**Location:** `scripts/lib/workflow.py:477`, `scripts/lib/workflow.py:539`.

**Requirement:** T001 requires queue segmentation to use the same heading and fence rules as `task_blocks()`.

**Problem:** `task_blocks()` recognizes headings with `^##\s+…`, including a tab after `##`. `queue_segments()` first requires the literal prefix `## `, so it omits those task boundaries. Reconstruction subsequently indexes a missing task ID.

**Evidence:** With otherwise valid task blocks:

```text
##<TAB>T001 — Verify T001
Dependencies: T002
…
## T002 — Verify T002
Dependencies: none
…
```

`task_blocks()` recognizes both IDs, but `tasks_reorder()` raises `KeyError: 'T001'` without writing. Manually placing T002 first makes the existing `tasks()` validator pass.

**Impact:** Automatic repair stops planning/revision for a supported heading layout and produces a traceback instead of repairing the queue.

**Recommended direction:** Share heading classification or recognize task headings before applying the literal non-task-section check. Add a tab-separated-heading regression.

## Previous findings re-evaluated

- **M2 fixed:** Introductory `## Context` sections are preserved, and the reordered queue validates.
- **N4 fixed:** The actual plan report now yields reviewed HEAD `e5e68b0`.
- **N5 fixed:** A simulated 5,000-digit count returns `None` for that report while preserving the other report.

T006 was explicitly deferred in commit `cb69048`; it is not counted as missing implementation.

## Missing coverage

- Dispatcher failure/interruption with active test subprocesses, as demonstrated in M3.
- Heading syntax parity between the validator and reorder parser.
- Notification retention rollover through the real `notify-log` writer; current wait tests append directly.
- Some new wait tests use literal CLI timeouts outside the stated scaling convention.

## Security concerns

M3 affects process cleanup and availability. The inspected dashboard additions retain bounded, pinned, no-follow readers and keep review counts advisory. No additional demonstrated authorization defect was found.

## Architecture concerns

Dependencies remain minimal, and host authority boundaries are preserved. Duplicate queue parsing rules have now produced the concrete divergence in N6; shared classification would reduce further drift.

## Manual testing recommendations

### Needs you

- Confirm the self-check passes well under ten minutes on the intended four-CPU CI runner.
- Exercise a supervised plan revision and crash/resume in a scratch project.
- Confirm fixture pipelines stay hidden while real pipelines remain visible.
- Check dashboard review details and cursor-based waiting during live runs.

### Covered by automated tests

- Existing coverage addresses ordering, cycles, DONE preservation, revision recovery, discovery filtering, review parsing, and wait transitions.
- Add deterministic regressions for M3 and N6.
- Add notification-retention rollover coverage using the real writer.

Reviewing does not constitute human acceptance.