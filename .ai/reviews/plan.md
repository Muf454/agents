<!-- Plan review of plan digest 02a8c7d2b280767c34e0872fe8dfd6480d923fa14c07fef65fdfce8d3fe95c22; saved 2026-10-09T05:01:32Z. -->

> **Reviewer: Claude fallback (claude-opus-5-5, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

**Plan review: outcome follow-ups, revision 4 (HEAD 828c4fe)**

Overall verdict: Approve with one change. T001–T003 are scoped, ordered and sized correctly. Each `Model: sonnet` fits: these are telemetry and test-runner tasks with no security, concurrency or data-migration risk. The plan describes the code correctly: `run_shard` (`tests/run_parallel.py:56-68`), `outcome` / `outcomes_report` (`scripts/lib/workflow.py:2042-2134`), `recheck_values` / `rejected_rows` (`workflow.py:1235-1253`, `1360-1382`), and `fail()` raises `ValueError` (`workflow.py:19-20`), so the planned `except` does catch verifier failures. One real gap remains in T003's report change: R4's catch-up list has no test.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

## BLOCKER findings

None.

## MAJOR findings

- P1: T003 "Report" (`.ai/tasks.md:74`, acceptance criteria at `:82-85`). Moving re-checks out of "Reviews by reviewer" can quietly drop Claude re-checks from "Codex catch-up pending", and no test would catch it. **Demonstrated** (code path traced; the effect on the implementation is a risk).
  - **Trace:** today the catch-up list is built from the same `reviews` list as the reviewer table, inside the same `if reviews:` block (`workflow.py:2116-2133`: `fallback = [r for r in reviews if str(r.get('reviewer','')).startswith('claude')]`).
  - **Likely implementation:** the obvious way to "move re-checks to their own table" is to filter `reviews` to plan/code before grouping. That removes `mode == 'recheck'` rows from the catch-up list. And when every review in the log is a re-check, `if reviews:` is false, so the whole section disappears.
  - **Why it matters:** this contradicts R4 (`.ai/project-spec.md:51-54`: "the report keeps listing every Claude review under 'Codex catch-up pending'") and the plan's "Deferred: CU-2" promise (`.ai/current-plan.md:25-26`).
  - **No test catches it:** Claude fallback re-checks do write outcome lines (`ai-review:264` → `review_records` → `outcome review recheck claude-fallback …`; exercised by `test_recheck_falls_back_to_claude`, `tests/test_workflow.py:2408`). But the only catch-up assertion counts `'code HEAD'` (`tests/test_workflow.py:2647-2648`).
  - **Plan change:**
    - In T003's implementation notes, state that "Claude-only reviews (Codex catch-up pending)" is still built from *all* review lines (plan, code and recheck), independent of the table split.
    - Extend T003's hand-written JSONL report test with a `claude-fallback` recheck line. Assert it appears under "Codex catch-up pending" (`recheck HEAD …`) and that the "Reviews by reviewer" section has no `| recheck |` row. Acceptance criterion 3 claims the second point, but no planned test asserts it.
    - Add a matching acceptance criterion: "Claude re-checks remain listed under Codex catch-up pending."

## MINOR findings

- P2: T002 attempt-1 rule (`.ai/tasks.md:45`). The rule says "its first row with `attempt == 1`, or, when none of its rows has an `attempt` field, its first row". That leaves one case undefined: a task with an old attempt-less row followed by a new row. `outcome` numbers the new row `attempt=2`, because it counts all earlier lines for the task (`workflow.py:2056-2058`). That task then has no attempt-1 row and drops out of the first-time-pass denominator.
  - **Fix:** use the simpler rule "a task's first row in file order (files in argument order) is its attempt-1 row". Within one log this is identical, because attempts are numbered in file order. It covers the mixed case, and the existing T009 old-line fixture gives the same expected `0/1 (0%)` result.
- P3: T003 validation (`.ai/tasks.md:88`). The targeted filter `-k outcome -k recheck_command -k recheck_falls_back` skips the pipeline re-check paths that now also run the new `outcome` code: `test_pipeline_fallback_recheck_is_committed_with_the_log` (`tests/test_workflow.py:2436`) and the dispute tests (around `:3565-3821`). `.ai/bin/ai-check` runs the full suite, so this is not a gate gap, but the per-task check would miss a regression there.
  - **Fix:** use `-k outcome -k recheck`, which covers all of them.

## Missing coverage

- Checklist items checked: 4 (stale async results) and 5 (refresh wiring). Not applicable: the report is computed offline from the log, and the outcome line is written once, after `publish-recheck` (`ai-review:263-264`).
- Item 3 (attribution and spoofing): checked. The re-check counts come only from the host-bound `recheck.md` (sha256 binding in `binding_dir()`, `workflow.py:1370-1372`), never from the raw `$report` the agent produced. The plan's use of `recheck_values()` is correct.
- Item 8 (data hidden from views): this is P1. Re-check rows could drop out of the catch-up view.
- Items 1, 2, 6, 7, 9 and 10 (locking, deletion, tenancy, roles, main/alt identity, migrations) do not apply: there is no database or authorization surface.
- T001: the plan already covers the env clean-up for each case, the separate no-escape test with a failing suite, and the two mutation checks. On Python older than 3.14 the `PYTHON_COLORS` mutation check proves nothing, and the plan records that.

## Security concerns

None. The change is read-only telemetry. `outcome` stays nonfatal (`ai-review:214-215`, `2>/dev/null || printf …`), and the new `try/except` keeps line-writing independent of the re-check verifier.
