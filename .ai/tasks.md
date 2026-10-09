# Task queue

Branch `fix/outcome-followups`: outcome telemetry and parallel runner follow-ups CU-1, CU-3, CU-4 (see `.ai/project-spec.md`). CU-2 (Codex catch-up coverage, was T004) is deferred: see `.ai/current-plan.md` "Deferred: CU-2".
Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts` or other gate files. Telemetry only: no change to what the pipeline does.

## T001 — Parallel runner ignores every colour setting (CU-4)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
R1: `tests/run_parallel.py` parses every shard's summary whatever the caller's colour settings. The reported trigger (`FORCE_COLOR`) is already handled (`run_shard` drops it and sets `NO_COLOR=1`); close the remaining gap and add the missing regression tests.

### Implementation notes
On Python 3.13+ `_colorize.can_colorize` checks `PYTHON_COLORS` before `NO_COLOR`, so a caller with `PYTHON_COLORS=1` still gets coloured `Ran N tests`/`OK` lines (Python 3.14 here colours unittest output). In `run_shard` also set `env['PYTHON_COLORS'] = '0'`; update the comment. Factor the parsing into a small function `summary(output)` returning `(ran, status)` that first removes ANSI escape sequences (`re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', output)`), so a future colour source cannot break it either; print the original output for failing shards as today. Docs: one sentence in README "Running the tests" (shards run without colour; `FORCE_COLOR`/`PYTHON_COLORS` are ignored for them) and the matching `docs/workflow.md` paragraph (line ~49). Flow unchanged.

Tests in `ParallelRunnerTest` (new methods `test_parallel_runner_*`): run a two-test suite through the runner with `FORCE_COLOR=3`, with `PYTHON_COLORS=1`, and with both (subtests): exit 0, `Ran 2 tests`, no `crashed`. `setUp` copies the host environment, so each subtest first removes `NO_COLOR`, `FORCE_COLOR` and `PYTHON_COLORS` from its env copy and then sets only that case's variables (a host `NO_COLOR=1` or CI `PYTHON_COLORS=0` must not make a case pass without exercising the fix). Set the env on `self.env` before calling `self.runner()`, which copies it (`tests/test_workflow.py` ~4676). Load the runner with `importlib.util.spec_from_file_location` (as `recheck_module` does for the helper) and check `summary()` on a coloured sample (`'\x1b[1mRan 3 tests in 0.1s\x1b[0m\n\n\x1b[32mOK\x1b[0m\n'` → `(3, 'OK')`; `FAILED (failures=1)` → `'FAILED'`). Because `summary()` strips escapes, the passing-suite cases cannot tell whether the env line is there; the env line gets its own test: run a *failing* two-test suite (as `test_parallel_runner_failing_test_prints_traceback`) with only `PYTHON_COLORS=1` set (same env clean-up) and assert the runner's echoed shard output (`print(output.rstrip())`) contains no `\x1b[`. On Python 3.14+ `_colorize.can_colorize` returns true for `PYTHON_COLORS=1` before any other check, so without the env line unittest's failure output is coloured. Two mutation checks, each run once with the result recorded: removing the `PYTHON_COLORS=0` line fails the no-escape test (Python 3.14+); removing the stripping in `summary()` fails the `summary()` unit test. On older Pythons unittest does not colour, so the first check is vacuous there; record `sys.version_info` used for the checks and their outcome in the result.

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- With `FORCE_COLOR=3`, `PYTHON_COLORS=1` or both in the caller's environment, the runner reports `OK` with the right count for a passing suite.
- `summary()` parses coloured and plain summaries identically.
- With `PYTHON_COLORS=1` in the caller's environment, no escape sequence reaches the echoed output of a failing shard.
- Each colour case runs with only its own colour variables set (host `NO_COLOR`/`FORCE_COLOR`/`PYTHON_COLORS` removed first).
- Mutation checks (once, Python version and outcome recorded in the result): on Python 3.14+ removing the `PYTHON_COLORS=0` line fails the no-escape test; removing the stripping in `summary()` fails the `summary()` unit test.
- Existing `parallel_runner` tests still pass; `--collect-only` unchanged.

### Validation
`python3 -m unittest tests.test_workflow -k parallel_runner`; `.ai/bin/ai-check`

### Result / notes

## T002 — Per-attempt model statistics in the outcome report (CU-1)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
R2: `ai-status --outcomes` credits each attempt and its time to the model that ran it instead of the task's final model.

### Implementation notes
`scripts/lib/workflow.py` `outcomes_report`: today `table()` groups `final[key]` (each task's last row) and `spent[key]` (sum of all attempts). Keep that for the category table ("Tasks by category", per task, unchanged columns). Replace "Tasks by model" and "Tasks by model and category" with per-attempt tables "Attempts by model" and "Attempts by model and category", grouped by each attempt row's own `model` (missing → `default`) and the task's category:
`| model | attempts | done | not done | first-time pass | avg minutes |` where attempts = rows on that model, done = rows with `result == 'done'`, not done = the rest, first-time pass = `x/y (z%)` over tasks whose attempt-1 row ran on this model (x = those whose attempt-1 row has `first_pass` true; print `-` when y is 0), avg minutes = that model's seconds / its attempts / 60. Each task key (`project`, `branch`, `task`) has at most one attempt-1 row: its first row with `attempt == 1`, or, when none of its rows has an `attempt` field, its first row in file order. So a task counts at most once in y, even with several old attempt-less rows. Keep the summary line (`N task(s), M attempt(s), R review(s).`). Keep the hunk inside `outcomes_report` (a nested helper is fine).

Tests (new `test_outcome_report_*` methods; offline): write a JSONL file by hand in the test's temp dir and run `ai-status --outcomes FILE` in the fixture project: T001 attempt 1 `sonnet` `error` 600 s, attempt 2 `opus` `done` 300 s (`first_pass` false); T002 attempt 1 `sonnet` `done` 60 s (`first_pass` true). Expect the sonnet row `| sonnet | 2 | 1 | 1 | 1/2 (50%) | 5.5 |` and opus `| opus | 1 | 1 | 0 | - | 5.0 |`; the category table still has one row per task with summed time. Old-line case (separate JSONL): task T009 with two rows lacking `model`, `attempt` and `first_pass` (`error` 60 s, then `done` 60 s) gives `| default | 2 | 1 | 1 | 0/1 (0%) | 1.0 |`, so it counts once in y. Update the one existing assertion in `test_runner_logs_task_outcomes_and_report` (`## Tasks by model` and its `| sonnet | 1 | 1/1 (100%) …` row) to the new table: assert `## Attempts by model` and the row prefix up to the first-time-pass cell, `| sonnet | 1 | 1 | 0 | 1/1 (100%) |`, without the avg-minutes cell (wall-clock time of a real mock run, now the last column), as the current assertion's values do not depend on time; this is a format change, not a weakened check. Docs: README "Outcome log" and `docs/workflow.md` "Outcome log" describe per-attempt model tables. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py (outcomes_report only), tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- The mixed-model fixture shows one attempt and its minutes under each model (rows above); the old code fails this test.
- The category table is per task as before.
- Old lines without `model` or `attempt` still report (as `default`; a task's first row is its attempt 1, counted once in the first-time-pass denominator).
- `test_runner_logs_task_outcomes_and_report` passes with the updated table assertion.

### Validation
`python3 -m unittest tests.test_workflow -k outcome`; `.ai/bin/ai-check`

### Result / notes

## T003 — Re-check outcome lines carry upheld/withdrawn totals (CU-3)
Status: TODO
Dependencies: T002
Model: sonnet

### Goal
R3: a re-check's outcome line records how many rejected BLOCKER/MAJOR findings were upheld and withdrawn, and which HEAD was reviewed; the report sums them per reviewer.

### Implementation notes
`scripts/lib/workflow.py` `outcome`, branch `kind == 'review'` and `mode == 'recheck'` (`ai-review` calls `outcome review recheck …` right after `publish-recheck`; do not change `ai-review`). Read the published report with the existing verifier: `head, _, _, answers = recheck_values()` and the levels from `rejected_rows()`, which returns `(head, rows)` with `rows` a list of `(finding, level, evidence)` tuples: `levels = {finding: level for finding, level, _ in rejected_rows()[1]}`. The counting helper takes `(answers, levels)` and returns the four ints, so it can be unit-tested with a BLOCKER level directly. Add `upheld_blocker`, `upheld_major`, `withdrawn_blocker`, `withdrawn_major` (ints, zero included) and `reviewed_head` (`git rev-parse --verify <head>^{commit}`, full SHA). Wrap it in `try … except (OSError, ValueError, subprocess.CalledProcessError)`: on failure omit these fields and still write the line (as the plan/code `review_counts` branch does). Read-only: no new writes, no change to verification.

Report (`outcomes_report`): plan/code reviews stay in "Reviews by reviewer"; re-checks move to a new table "## Re-checks by reviewer": `| reviewer | model | re-checks | upheld BLOCKER | upheld MAJOR | withdrawn BLOCKER | withdrawn MAJOR | avg minutes |`, one row per (`reviewer`, `model`) (missing `model` → `default`), rows sorted with `key=str` like "Reviews by reviewer" (missing fields count 0; old lines still count as re-checks). `reviewed_head` is recorded on the line but not printed in this table (kept for later matching, e.g. the deferred CU-2).

Tests (new `test_outcome_recheck_*`): reuse `rejected_review` (two MAJOR, M1/M2 rejected) and `MOCK_RECHECK` with M1 withdrawn, M2 upheld (as `test_recheck_command_parses_withdrawn_and_upheld`): the last outcome line has `upheld_major == 1`, `withdrawn_major == 1`, both BLOCKER fields 0, `reviewed_head` = the review's HEAD (full SHA, which differs from the current HEAD after the triage commit). A malformed answer (every finding upheld) gives `upheld_major == 2`. BLOCKER counting: a report test with hand-written JSONL (`upheld_blocker` 1 …) checks the new table row; a module-level check of the counting helper with a BLOCKER level is enough if no mock produces a BLOCKER review. Failure case: call the helper directly (`outcome review recheck codex MODEL EFFORT 1`) in a fixture with no re-check report, so `recheck_values` fails, and assert exactly one new line without the count fields. Docs: README and `docs/workflow.md` "Outcome log" list the new fields. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py (outcome, outcomes_report), tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- After a re-check with one withdrawn and one upheld MAJOR, the outcome line carries those totals by severity and the reviewed HEAD.
- A line is still written, without the new fields, when the re-check report cannot be verified.
- The report's "Re-checks by reviewer" table sums the totals; "Reviews by reviewer" no longer lists re-checks with zero findings.
- `ai-review --recheck` behaviour and its existing tests are unchanged.

### Validation
`python3 -m unittest tests.test_workflow -k outcome -k recheck_command -k recheck_falls_back`; `.ai/bin/ai-check`

### Result / notes
