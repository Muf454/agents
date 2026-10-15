<!-- Host evidence: HEAD e36de5797c8a74888f98eed29e70735e7208fd1d; merge-base 5894c2b23e0fc29fe3ab225a2bda707889967f91; saved 2026-10-15T06:46:54Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED. Queue repair rejects a supported preamble layout; two dashboard parsing defects also remain.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

Reviewed HEAD: `e36de5797c8a74888f98eed29e70735e7208fd1d`

Supplied base and merge-base: `5894c2b23e0fc29fe3ab225a2bda707889967f91`

Checkout was clean. No files were written; no network or MCP integrations were invoked.

## Scope and validation

Inspected repository instructions, spec, plan, tasks, state, handoff, plan reviews/dispositions, relevant documentation, Git history, the supplied diff, and affected source/tests. Also inspected the vault flow chart and relevant hub Log entries: the chart contains the T002/T011 changes and `updated: 2026-10-15`.

Validation observed:

- `.ai/local/validation.json`: PASS, exit 0, timestamp `2026-10-15T06:41:30Z`.
- Referenced log: **679 tests passed in 396.1 seconds**, using 48 batches on eight workers.
- `python3 -B scripts/lib/workflow.py stamp verify` passed against the reviewed checkout.
- Changes after the recorded validation revision affect only excluded state/run-log bookkeeping.

Checks run:

- Shell syntax: 13 files passed.
- Python AST parsing: seven changed files passed.
- Current task queue validation passed.
- Test discovery collected 679 tests.
- No existing test methods were removed or renamed.
- Six documentation/sanitization tests passed.
- Three pure renderer/parser test bodies passed with filesystem setup omitted.
- In-memory checks covered batch partitioning, timeout scaling, cursor round-trip, wait change/timeout behavior, and identical-content notification replacement.
- Read-only reproductions confirmed the findings below.
- `git diff --check` passed.

The full `./scripts/ai-check` was not rerun because it writes validation records and fixture checkouts. The four-CPU CI performance target remains unverified.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M2 — Queue repair rejects non-task headings in the preamble

**Location:** `scripts/lib/workflow.py:531`, `scripts/lib/workflow.py:535`.

**Requirement:** FL-24/T001 defines the preamble as everything before the first task heading. Only a non-task `## ` section **between two tasks** should prevent reordering.

**Problem:** The rejection scans every segment before the last task, including preamble sections. Reconstruction also retains only the initial `pre` segment.

**Evidence:** Running the actual reorder function against an in-memory queue containing:

```markdown
# Queue

## Context
Keep this intro.

## T001 — ...
Dependencies: T002
...
## T002 — ...
Dependencies: none
...
```

raises `cannot reorder: section "## Context" sits between tasks`, without writing. The otherwise identical queue without `## Context` successfully becomes `T002 T001`.

**Impact:** A repairable queue with ordinary introductory Markdown sections stops planning or revision. Revision recovery then escalates to the human, defeating FL-24 for this supported layout.

**Recommended direction:** Identify the first and last task segments. Preserve everything before the first task as the preamble, and reject non-task sections only between those boundaries. Add helper and planning/revision regression coverage.

## MINOR findings

### N4 — Real plan-review reports always lose their reviewed HEAD

**Location:** `scripts/lib/dashboard.py:308`, `scripts/lib/dashboard.py:340`.

**Requirement:** DB-02/T008 requires the short reviewed HEAD for both plan and code reports, so users can identify stale results.

**Problem:** `REVIEW_HEAD` recognizes only `Host evidence: HEAD …;`. Actual plan reports use `Plan review of plan digest …; HEAD …;`, as produced by `publish_plan_review()`.

**Evidence:** Reading this checkout’s actual reports through `reviews_of()` returned:

```json
{"plan":{"blocker":0,"major":0,"minor":2,"head":""}}
```

The plan report’s header contains HEAD `e5e68b0b75e0ed3812d63ba0fec5049b9a121652`. The added test fabricates a code-review header for the plan report, hiding the mismatch.

**Impact:** JSON and expanded details omit the reviewed revision for genuine plan reviews.

**Recommended direction:** Parse both real header formats and use a genuine plan-report header in the regression test.

### N5 — A malformed finding count can crash the entire dashboard

**Location:** `scripts/lib/dashboard.py:341`.

**Requirement:** T008 explicitly requires unreadable or malformed review data to produce empty values, never an exception.

**Problem:** Finding-count conversion uses unchecked `int()` calls. The bounded reader permits count strings longer than Python’s integer-conversion limit.

**Evidence:** Supplying the actual reader function with one counts line whose `BLOCKER` value contains 5,000 digits raises:

```text
ValueError: Exceeds the limit (4300 digits) for integer string conversion
```

This exception propagates through `inspect()` and `snapshot()`.

**Impact:** One malformed agent-writable report prevents the dashboard from showing every checkout, including during `--wait`.

**Recommended direction:** Bound numeric fields and handle conversion failures per report, returning `None` for the malformed side. Test that other runs remain available.

## Missing coverage

- Preamble sections before reordered tasks.
- Genuine plan-report headers and oversized numeric counts.
- Dispatcher interruption and worker-launch failure cleanup, previously suggested by plan finding P9.
- Notification retention rollover through the real writer, previously suggested by P8. The in-memory replacement check does not replace that integration test.
- Some new dashboard tests pass literal CLI timeout values, outside the named/scaled timeout convention.

## Security concerns

N5 is an availability defect in the advisory dashboard reader. The inspected additions otherwise retain pinned, bounded, no-follow readers and keep review counts informational. No additional demonstrated authorization or security defect was found.

## Architecture concerns

The changes retain standard-library dependencies and existing host authority boundaries. Queue parsing is duplicated between `task_blocks()` and `queue_segments()`; shared classification rules would reduce drift.

Accepted plan concerns about early recovery repair, executable tmpfs probing, and notification identity have corresponding implementation and regression coverage.

T006 was explicitly deferred in commit `cb69048`; it is not counted as missing implementation. The older code-review artifact concerns a different range; its pre-existing findings are separate from this report’s introduced defects.

## Manual testing recommendations

### Needs you

- Confirm the PR’s self-check passes well under ten minutes on the intended four-CPU runner.
- Exercise a real supervised revision and crash/resume in a scratch project.
- Confirm fixture pipelines stay hidden while real pipelines remain visible.
- Check dashboard review details and cursor-based waiting on live runs.

### Covered by automated tests

- Existing coverage addresses queue ordering, cycles, DONE preservation, revision recovery, environment filtering, review counts, and wait transitions.
- Add the regressions described in M2, N4 and N5.
- Add deterministic dispatcher cleanup and notification-retention tests.

Reviewing does not constitute human acceptance.