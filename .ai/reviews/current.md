<!-- Host evidence: HEAD afa91c0d1e2c738010fc15ab683f0b45069806c2; merge-base 7d22939e12957f9ba744f563498161f970fe31ab; saved 2026-10-17T00:07:00Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=2

Reviewed HEAD: `afa91c0d1e2c738010fc15ab683f0b45069806c2`

Supplied base and verified merge-base: `7d22939e12957f9ba744f563498161f970fe31ab`

## Scope and validation

Inspected repository instructions, specification, plan, tasks, state, handoff, previous reviews/dispositions, relevant documentation, complete scoped diff/history, and affected source/tests. The checkout was clean.

Validation evidence observed:

- `.ai/local/validation.json`: PASS at `2026-10-17T00:02:40Z`, recorded at `0eefd412`.
- Referenced log: **736 tests passed in 398.2 seconds**, across 48 batches on eight workers.
- Independent `stamp verify`: the fingerprint matches the reviewed checkout.

Checks independently run:

- Task queue validation, discovery of 736 tests, and comparison confirming no existing test IDs were removed.
- Three documentation consistency tests: passed.
- Python AST parsing for three changed Python files and shell syntax checks for 13 scripts/templates: passed.
- `git diff --check`: passed.
- In-memory task-filling, recovery parsing, catch-up ordering, and disposition parsing checks.
- Real-process cleanup checks described below.

The full `./scripts/ai-check` and fixture integration tests were not rerun because they write files. Process reproductions were explicitly cleaned up. No files were written and no network/MCP integrations were invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — Non-UTF-8 process names abort descendant cleanup

**Location:** `tests/run_parallel.py:205`, `tests/run_parallel.py:219`, `tests/run_parallel.py:389`.

**Requirement:** FL-27 requires terminating descendants before shutdown returns or re-raises.

**Problem:** `/proc/<pid>/stat` contains the process name as arbitrary bytes. `proc_stat()` reads it with strict text decoding and catches only `OSError`. A non-UTF-8 name raises `UnicodeDecodeError`. Because the scanner reads every visible process, an unrelated process can also trigger this.

**Evidence:** A child set its Linux process name using `prctl(PR_SET_NAME, b"\xff")`. Calling the actual `Dispatcher.stop()` with subreaping enabled produced:

```text
stop raised: UnicodeDecodeError
child alive after stop: True
stop_done: True
```

The initial descendant scan fails before batch-group termination. The dispatcher nevertheless marks shutdown complete, preventing another caller from retrying cleanup.

**Impact:** The new scanner can crash an otherwise ordinary self-check and leave fixture processes alive—the failure FL-27 is intended to eliminate. This is introduced by this range.

**Recommended direction:** Parse the numeric stat fields from bytes, or use lossless/error-tolerant decoding. Ensure a scan failure cannot skip batch termination while marking cleanup complete. Add a real-process regression with a non-UTF-8 process name.

### M2 — A targeted Codex re-check falsely covers a full Claude review

**Location:** `scripts/lib/workflow.py:3172`, `scripts/lib/workflow.py:3178`.

**Requirement:** CU-2 should remove Claude reviews from catch-up pending when Codex has covered their work.

**Problem:** Mapping every non-plan mode to the `code` family lets a later Codex `recheck` cover an earlier full Claude code review. However, `templates/.ai/prompts/recheck.md:4` explicitly restricts re-checks to rejected findings and prohibits reviewing accepted/deferred findings or raising new ones.

**Evidence:** Supplying the actual report function with these same-project/branch records:

1. Claude fallback, `mode=code`, at t1.
2. Codex, `mode=recheck`, at t2.

removes the pending entry and prints:

```text
1 Claude review(s) covered by a later Codex review or catch-up record.
```

**Impact:** Catch-up tracking silently reports a full independent review as completed after Codex examined only selected findings. This is introduced by this range; the plan’s symmetric family assumption is too broad for the existing re-check contract.

**Recommended direction:** Require a full Codex code review to cover code-family work, or establish narrower coverage using the actual reviewed scope. Add a regression proving that a targeted re-check leaves the preceding full Claude review pending.

## MINOR findings

### P7 — Literal backslashes before pipes still shift table columns

**Location:** `scripts/lib/workflow.py:985`, `scripts/lib/workflow.py:990`.

**Problem:** The retained pipe-only writers and new paired-backslash parser lack a consistent encoding/decoding contract. This remains the previous plan-review finding P7; no rejection or implementation resolving it was found.

**Evidence:** Encoding evidence containing the literal text `literal regex \| is required` with the existing writer produces:

```text
| P7 | accepted | literal regex \\| is required | T030 |
```

Both actual disposition regexes read `is required` as the Task cell.

**Impact:** Evidence discussing escape syntax can still stop triage/revision or corrupt parsed columns.

**Recommended direction:** Define matching backslash-and-pipe encoding and decoding. Extend round-trip coverage to a literal backslash before a pipe and multiple consecutive backslashes.

### N1 — Missing Task cells can consume the following row

**Location:** `scripts/lib/workflow.py:994`, `scripts/lib/workflow.py:2445`.

**Requirement:** FL-25(b) explicitly requires rows with a missing Task cell to remain malformed.

**Problem:** Surrounding `\s*` expressions cross newlines, despite `TABLE_CELL` excluding them. A row without its Task cell can consume the next row’s opening pipe as an empty Task cell.

**Evidence:** An in-memory call to the actual `triage_check --fresh` accepted a rejected MAJOR row lacking its Task column when an optional MINOR row followed it. The regex matched only the MAJOR row, consumed the following opening pipe, and validation returned `accepted=0 deferred=0`.

**Impact:** Malformed records can pass validation and swallow subsequent optional dispositions; subsequent required rows instead cause misleading missing-disposition stops.

**Baseline distinction:** Cross-line whitespace matching predates this range, but remains an unmet explicit FL-25 requirement.

**Recommended direction:** Constrain row whitespace to spaces/tabs and parse each physical row independently. Test missing Task cells both at EOF and before another row.

## Previous findings re-evaluated

- Previous code-review **M3**: ordinary GNU `timeout` descendant cleanup is fixed. An independent real-process check terminated all three descendants. M1 identifies a separate remaining cleanup failure.
- Plan findings **P1–P6**: the descriptor-based deletion, escaped-pipe protection, recovery scanner redesign, shutdown ownership/barrier, timestamp ordering, and protected startup loop are present with relevant regression tests.
- Plan finding **P7** remains reproducible.
- The vault flow chart contains the queue-filling and scratch-clearing steps with `updated: 2026-10-17`; corresponding hub log entries exist.

## Missing coverage

Add regressions for M1, M2, P7, and N1. Existing tests cover ordinary process names, full code/plan catch-up reviews, bare escaped pipes, and missing Task cells at EOF; those cases do not expose the reported defects.

The independent recovery checks passed 15 representative acceptance/rejection cases. Task-filling checks confirmed canonical insertion, idempotence, and preservation of non-TODO tasks.

## Security concerns

M1 affects local availability and process cleanup. M2 affects audit-status accuracy; status remains advisory under AD-5.

The inspected scratch deletion uses pinned descriptors and no-follow directory opens. No additional demonstrated authentication/authorization defect was found in the inspected changes.

## Architecture concerns

Dependencies remain limited to the standard library. Gate files, installed tooling, and permissions were preserved. Catch-up coverage needs to respect the different scopes of full reviews and targeted re-checks.

## Manual testing recommendations

### Needs you

- After fixes and acceptance, refresh installed tooling/prompts using the documented upgrade process.
- Interrupt a real self-check on the intended host and inspect for leftover fixture processes.
- Compare catch-up output with the real review history, particularly branches containing targeted Codex re-checks.

### Covered by automated tests

- Retain the process-tree, startup-interruption, task-format, scratch-symlink, recovery, and catch-up regression groups.
- Add the four missing cases above.
- Rerun `./scripts/ai-check` after fixes.

Reviewing does not constitute human acceptance.