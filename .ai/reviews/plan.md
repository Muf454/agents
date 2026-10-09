<!-- Plan review of plan digest adfc338063877515a48bd7a0a5fc6d199c826fddc3c1e8eb3fcc960b1bb5a7cc; saved 2026-10-09T05:07:02Z. -->

> **Reviewer: Claude fallback (claude-opus-5-5, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

**Plan review: outcome follow-ups, revision 5 (HEAD c690c62)**

Overall verdict: Approve. T001–T003 match the code on this branch, and their order and size are right. Each `Model: sonnet` fits the risk: this is advisory telemetry and a test-runner fix, with no security, locking or data-migration surface. The round 4 findings are applied as their dispositions describe. I checked the plan's claims against the source, and all of them hold:
- `run_shard` (`tests/run_parallel.py:56-68`), and `outcome` / `outcomes_report` (`scripts/lib/workflow.py:2042-2134`) are as described.
- `recheck_values()` returns `(head, digest, rows_hash, answers)` (`workflow.py:1360-1382`).
- `rejected_rows()` returns `(head, [(finding, level, evidence)])` (`workflow.py:1235-1253`).
- `fail()` raises `ValueError` (`workflow.py:19-20`), so the planned `except` tuple catches verifier failures.
- `ai-review` writes the re-check outcome line right after `publish-recheck` and before any record commit (`scripts/ai-review:263-264`). At that point the current HEAD is the triage commit, so the `reviewed_head` test can tell the two apart.
- The expected T002 rows check out by hand, for example sonnet (600+60)/2/60 = 5.5 and the T010 default row `0/1 (0%)`. The updated `test_runner_logs_task_outcomes_and_report` prefix `| sonnet | 1 | 1 | 0 | 1/1 (100%) |` matches its log (`tests/test_workflow.py:2632-2633`).

What remains are two small test and consistency gaps.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

## BLOCKER findings

None.

## MAJOR findings

None.

## MINOR findings

- P1: T002, "Attempts by model and category" has no test, and the category it groups by is ambiguous (`.ai/tasks.md:44-47`). **Demonstrated** (plan text).
  - **Problem 1, no test:** the plan replaces two tables, but every planned assertion targets "Attempts by model" or "Tasks by category". The updated `assertIn('## Attempts by model', …)` is a substring of "## Attempts by model and category", so it would pass even if only the combined table were printed.
  - **Problem 2, which category:** the plan groups by "each attempt row's own `model` … and the task's category". Every row carries its own `category`, computed from the title at logging time (`workflow.py:2059`). If a task's title changes between attempts, the rows of one task can disagree. "The task's category" could then mean that row's category or the final row's, and the plan does not say which.
  - **Plan change, category:** state that the combined table uses each attempt row's own `category` (missing → `feature`), matching how `model` is taken per row.
  - **Plan change, test:** give T001 and T002 in the mixed-model fixture the same `category` (for example `tests`). Assert `| sonnet / tests | 2 | 1 | 1 | 1/2 (50%) | 5.5 |` and `| opus / tests | 1 | 1 | 0 | - | 5.0 |`. Also assert the exact heading line `## Attempts by model\n` (or the column header) rather than the substring.

- P2: T003, the catch-up line for a Claude re-check prints the logging-time HEAD (the triage commit), while `fallback-log.md` records the reviewed HEAD (`.ai/tasks.md:74,76`). **Demonstrated** (traced).
  - **Trace:** `ai-review:264` calls `review_records "$head" recheck`, where `$head` is the reviewed HEAD from `recheck-prepare`. `fallback_record` writes `head[:12]` into the log row (`workflow.py:1978`). The outcome line's `head` is `git rev-parse HEAD` at logging time (`workflow.py:2065`), which is after the triage commit. "Codex catch-up pending" prints that value (`workflow.py:2131-2132`).
  - **Effect:** for the same re-check, the two records a human compares show different SHAs.
  - **Plan pins it:** T003's test asserts `recheck HEAD <first 12 of head>`, which locks the mismatch in, even though T003 now records `reviewed_head` precisely for later matching.
  - **Plan change:** in the catch-up list, print `reviewed_head` when present, else `head`. The hand-written recheck line in the JSONL test then carries both fields with different values and asserts the `reviewed_head` prefix. Old lines without `reviewed_head` fall back to `head`, so nothing that exists today disappears.
  - **If you skip it:** to keep T003 strictly additive, record the mismatch as a known limitation in the README "Outcome log" paragraph.

## Missing coverage

- Checklist item 4 (stale async results) and item 5 (refresh wiring): checked. Neither applies. The report is computed offline from the log, and the re-check line is written once, after `publish-recheck` (`ai-review:263-264`). A failed publish exits before `review_records`, so the counts can never come from an earlier re-check.
- Item 3 (attribution and spoofing): checked.
  - The counts come only from the host-bound `.ai/reviews/recheck.md` (sha256 binding under `binding_dir()`, `workflow.py:1370-1372`), checked against the current review digest and the rejected-rows digest. They never come from the raw `$report` argument (Codex's unbound answer), which the plan correctly does not read for `mode == 'recheck'`.
  - `reviewed_head` is resolved by `git rev-parse --verify` from that bound header.
- Item 8 (data hidden from views): checked.
  - Re-checks leave "Reviews by reviewer" on purpose but stay in the summary count.
  - T003 now explicitly keeps them in "Codex catch-up pending", including a log that holds only re-checks.
  - Old lines without `mode` stay in the plan/code table, because `r.get('mode') != 'recheck'`.
- T003 failure path: the planned test covers the `ValueError` branch ("No re-check report"). The `CalledProcessError` branch (`rev-parse` of an unresolvable head) has no test. That is acceptable: the head comes from a bound header the verifier has just matched.
- T001: the env clean-up is required, not cosmetic. Once T001 lands, the gate runs `ParallelRunnerTest` inside a shard whose env already has `NO_COLOR=1` and `PYTHON_COLORS=0`. Without the per-case removal, the colour cases would pass vacuously. The plan handles this.
- Items 1, 2, 6, 7, 9 and 10 (locking, deletion, tenancy, roles, main/alt identity, migrations) do not apply: there is no database or authorization surface.

## Security concerns

None.
- T001 edits `tests/run_parallel.py`, which the gate runs (`.ai/validate:10`). It is not one of the protected gate files, and the change cannot produce a false pass: a shard only counts as passing with `returncode == 0` from unittest itself, and the collected-vs-ran count check stays (`run_parallel.py:98,111`). Changing the parsing can only cause false failures.
- T003 reads only through the existing verifier, writes nothing new, and stays nonfatal (`ai-review:214-215`, `2>/dev/null || printf …`).
