<!-- Host evidence: HEAD 9d3e9be2a0e52a975c280e7868406798d146740e; merge-base 744827a5212847d9734d197559321ca1c7f042cc; saved 2026-10-13T06:27:34Z. -->

# Independent review

Overall verdict: PASS WITH MINOR FINDINGS. The accepted previous-round findings are fixed. No BLOCKER or MAJOR finding remains in the inspected scope; two localized issues remain.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

Reviewed HEAD: `9d3e9be2a0e52a975c280e7868406798d146740e`

Supplied base and merge-base: `744827a5212847d9734d197559321ca1c7f042cc`

Checkout was clean before and after review. No files were written; no network or MCP integrations were invoked.

## Scope and validation

Inspected AGENTS.md, the spec, plan, tasks, state, handoff, review dispositions, relevant documentation, Git history, the full supplied diff, changes since `e8eb6c8`, and affected source and tests.

Validation evidence observed:

- `.ai/local/validation.json`: PASS, exit 0, unchanged content, timestamp `2026-10-13T06:20:04Z`.
- Referenced log: **619 tests passed in 355.1 seconds**, across eight shards.
- `python3 -B scripts/lib/workflow.py stamp verify` passed against the reviewed checkout. Changes after the recorded validation revision affect only excluded state/run-log bookkeeping.

Checks run:

- Shell syntax: 13 files passed.
- Python AST parsing: three affected helper modules passed.
- Test discovery: 619 tests collected.
- Thirteen pure renderer test bodies passed with the suite’s UTC setting retained; filesystem fixture setup was omitted.
- Three sanitization tests passed.
- Current task queue validation passed: 13 DONE of 13 tasks.
- Seven in-memory cases exercised the actual DONE-preservation helper.
- Actual watchdog transition statements were exercised in memory for legacy deduplication, clearing, reconfirmation and planning suppression.
- A read-only process-launch reproduction confirmed N2.
- `git diff --check` reported an extra EOF blank line in `.ai/tasks.md:872`.

The full `./scripts/ai-check` suite was not rerun because it writes validation records and temporary test checkouts. The isolated helper checks do not substitute for shell integration tests.

## Previous-round verification

**M1 — fixed by T012.** The host captures the working queue before planning and supplies that baseline to the post-session preservation check. The helper protects the union of committed and working-tree DONE tasks. In-memory checks rejected removal, status changes, result edits and fenced-content edits; unchanged blocks passed. The added integration tests cover both revision-flag variants and baseline cleanup.

**N1 — fixed by T013.** An unchanged legacy record with `active: ["stalled"]` remains confirmed without becoming fresh. The checked transitions preserved deduplication, cleared the incident when appropriate, and required confirmation when it returned. The added regression test also asserts no repeated notification or diagnosis.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N2 — Accepted large planning objectives cannot reach Claude

**Location:** `scripts/ai-run:54`, `scripts/ai-run:297`, `scripts/ai-run:263`.

**Requirement:** DB-04’s planning input contract accepts a regular prompt file up to 200 KB.

**Problem:** The file check accepts 204,800 bytes, but the complete objective, planning template and contract are passed as one command-line argument. Linux rejects sufficiently large individual arguments before the command starts.

**Evidence:** On this machine, launching `timeout` with a 102,400-byte argument succeeded; the same launch with a 153,600-byte argument raised `OSError: [Errno 7] Argument list too long`. A 150 KiB ASCII objective passes the file-size check and necessarily produces an even larger assembled prompt.

**Impact:** Some inputs within the advertised limit stop before Claude runs. Existing planning tests use small objectives and miss this boundary.

**Recommended direction:** Use a supported stdin/file transport for the assembled prompt, or validate its final encoded size and document a smaller supported limit. Add a shell integration test with a large objective within the advertised range.

The shared argument transport predates this change; the new planning mode’s accepted input range exposes the gap.

### N3 — README misstates how older observation records render

**Location:** `README.md:614`.

**Requirement:** DB-04 says every observation whose stage is not `planning` ticks Plan; only absent or unusable observations leave it unticked.

**Problem:** README groups “an old record” with missing records and says Plan remains unticked with “stage unknown”. Older valid records at `build`, for example, tick Plan.

**Evidence:** The renderer’s preceding-box rule ticks Plan for a build observation. `tests/test_dashboard.py:874` explicitly covers an older build record and expects the Plan box to be done. The pure build-renderer checks passed during this review.

**Impact:** Upgrade documentation gives users the wrong expectation for existing dashboard cards.

**Recommended direction:** Distinguish older valid observation records from checkouts with no usable observation record.

## Missing coverage

- Large accepted objectives and assembled prompt-size boundaries, as described in N2.
- Live Claude permission enforcement and real systemd scheduling remain dependent on human checks.

The previous gaps concerning uncommitted DONE tasks and already-active legacy stalls now have relevant regression coverage.

## Security concerns

No additional demonstrated security finding in the inspected changes.

Planning exposes no Bash tool and restricts Edit/Write to the six plan records. Post-session checks follow gate verification; the gate-change regression checks that an altered helper is not executed. Lock rejection preserves the owner’s records.

The documented `chmod +x` prefix rule cannot constrain paths to the checkout. Offline assertions verify the template, not real CLI enforcement.

## Architecture concerns

The implementation reuses existing scripts and standard-library helpers without adding dependencies. The new planning stage fits the observation and dashboard structure.

N2 concerns the prompt transport boundary. No separate pre-existing defect is counted.

## Manual testing recommendations

### Needs you

- Verify a real planning session’s permissions, notifications, dashboard transitions and uncommitted output in a scratch checkout.
- Verify allowed `chmod +x` and denied alternate modes with the real Claude CLI.
- Verify timer scheduling after installation/upgrade and relaunch behavior during recovery.
- Complete the handoff’s pending vault flow-chart, gate and timer-update steps before merging.

### Covered by automated tests

- Queue rejection and recovery escalation.
- Default and explicit session budgets, including runs beyond session 16.
- Lock-owner hints and preservation of existing records.
- Stall confirmation and legacy deduplication.
- Planning outcomes, gate changes and DONE-block preservation.
- Dashboard stages, widths and legacy records.
- Add the large-objective regression described in N2.

Reviewing does not constitute human acceptance.