# Task queue

Branch `fix/outcome-followups`: outcome telemetry and parallel runner follow-ups CU-1..CU-4 (see `.ai/project-spec.md`).
Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts` or other gate files. Telemetry only: no change to what the pipeline does.

## T001 — Parallel runner ignores every colour setting (CU-4)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
R1: `tests/run_parallel.py` parses every shard's summary whatever the caller's colour settings. The reported trigger (`FORCE_COLOR`) is already handled (`run_shard` drops it and sets `NO_COLOR=1`); close the remaining gap and add the missing regression tests.

### Implementation notes
On Python 3.13+ `_colorize.can_colorize` checks `PYTHON_COLORS` before `NO_COLOR`, so a caller with `PYTHON_COLORS=1` still gets coloured `Ran N tests`/`OK` lines (Python 3.14 here colours unittest output). In `run_shard` also set `env['PYTHON_COLORS'] = '0'`; update the comment. Factor the parsing into a small function `summary(output)` returning `(ran, status)` that first removes ANSI escape sequences (`re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', output)`), so a future colour source cannot break it either; print the original output for failing shards as today. Docs: one sentence in README "Running the tests" (shards run without colour; `FORCE_COLOR`/`PYTHON_COLORS` are ignored for them) and the matching `docs/workflow.md` paragraph (line ~49). Flow unchanged.

Tests in `ParallelRunnerTest` (new methods `test_parallel_runner_*`): run a two-test suite through the runner with `FORCE_COLOR=3`, with `PYTHON_COLORS=1`, and with both (subtests): exit 0, `Ran 2 tests`, no `crashed`. Load the runner with `importlib.util.spec_from_file_location` (as `recheck_module` does for the helper) and check `summary()` on a coloured sample (`'\x1b[1mRan 3 tests in 0.1s\x1b[0m\n\n\x1b[32mOK\x1b[0m\n'` → `(3, 'OK')`; `FAILED (failures=1)` → `'FAILED'`). Mutation check: without the `PYTHON_COLORS` line the `PYTHON_COLORS=1` case fails on this machine's Python 3.14 (on Python < 3.13 unittest does not colour, so it would pass anyway; note that in the result).

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- With `FORCE_COLOR=3`, `PYTHON_COLORS=1` or both in the caller's environment, the runner reports `OK` with the right count for a passing suite.
- `summary()` parses coloured and plain summaries identically.
- Removing the `PYTHON_COLORS=0` line makes the `PYTHON_COLORS=1` case fail (checked once, recorded in the result).
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
`| model | attempts | done | not done | first-time pass | avg minutes |` where attempts = rows on that model, done = rows with `result == 'done'`, not done = the rest, first-time pass = `x/y (z%)` over tasks whose attempt-1 row ran on this model (x = those with `first_pass`; print `-` when y is 0), avg minutes = that model's seconds / its attempts / 60. Rows without an `attempt` field count as attempt 1. Keep the summary line (`N task(s), M attempt(s), R review(s).`). Keep the hunk inside `outcomes_report` (a nested helper is fine).

Tests (new `test_outcome_report_*` methods; offline): write a JSONL file by hand in the test's temp dir and run `ai-status --outcomes FILE` in the fixture project: T001 attempt 1 `sonnet` `error` 600 s, attempt 2 `opus` `done` 300 s (`first_pass` false); T002 attempt 1 `sonnet` `done` 60 s (`first_pass` true). Expect the sonnet row `| sonnet | 2 | 1 | 1 | 1/2 (50%) | 5.5 |` and opus `| opus | 1 | 1 | 0 | - | 5.0 |`; the category table still has one row per task with summed time. Update the one existing assertion in `test_runner_logs_task_outcomes_and_report` (`## Tasks by model` and its `| sonnet | 1 | 1/1 (100%) …` row) to the new table; this is a format change, not a weakened check. Docs: README "Outcome log" and `docs/workflow.md` "Outcome log" describe per-attempt model tables. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py (outcomes_report only), tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- The mixed-model fixture shows one attempt and its minutes under each model (rows above); the old code fails this test.
- The category table is per task as before.
- Old lines without `model` or `attempt` still report (as `default` / attempt 1).
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
`scripts/lib/workflow.py` `outcome`, branch `kind == 'review'` and `mode == 'recheck'` (`ai-review` calls `outcome review recheck …` right after `publish-recheck`; do not change `ai-review`). Read the published report with the existing verifier: `head, _, _, answers = recheck_values()` and the levels from `rejected_rows()[1]` (`{id: level}`). Add `upheld_blocker`, `upheld_major`, `withdrawn_blocker`, `withdrawn_major` (ints, zero included) and `reviewed_head` (`git rev-parse --verify <head>^{commit}`, full SHA). Wrap it in `try … except (OSError, ValueError, subprocess.CalledProcessError)`: on failure omit these fields and still write the line (as the plan/code `review_counts` branch does). Read-only: no new writes, no change to verification.

Report (`outcomes_report`): plan/code reviews stay in "Reviews by reviewer"; re-checks move to a new table "## Re-checks by reviewer": `| reviewer | model | re-checks | upheld BLOCKER | upheld MAJOR | withdrawn BLOCKER | withdrawn MAJOR | avg minutes |` (missing fields count 0; old lines still count as re-checks).

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

## T004 — Codex catch-up coverage in the outcome report (CU-2)
Status: TODO
Dependencies: T003
Model: opus

### Goal
R4: the outcome report knows which Claude fallback reviews a later Codex code review covered, from `.ai/reviews/fallback-log.md`, records it explicitly in the Codex review's outcome line and lists only uncovered Claude reviews as "Codex catch-up pending".

### Implementation notes
Opus: a wrong coverage rule would silently hide Claude-only work that still needs a Codex review. When unsure, leave a review pending.

Recording (`workflow.py` `outcome`, `kind == 'review'`, `mode == 'code'`; arguments unchanged, no change to `ai-review`): `publish-review` has already written `.ai/reviews/current.md`; take `review_header(content)`; when its HEAD matches the recorded `head` (prefix comparison), add `base` = full SHA of its merge-base (any reviewer). When the reviewer is `codex` and `base` is known, add `covers`: a list of `{"mode": …, "head": <full SHA>}` for each row of `FALLBACK_LOG` (table rows `| date | mode | branch | HEAD | base | model | effort | reason |` anywhere in the file, skip the header/separator; hand-written lines are ignored) where:
- the row's HEAD resolves (`git rev-parse --verify <h>^{commit}`) to X, and X is an ancestor of or equal to the reviewed HEAD H (`git merge-base --is-ancestor X H`);
- the Codex base B is an ancestor of or equal to R, where R = the row's base resolved to a commit for code rows, or X for rows whose base is not a commit (`plan`, `recheck`);
- a code row whose base does not resolve is not covered.
Then the Codex review B..H contains every commit the Claude review R..X saw. Record `covers` (possibly empty) only for Codex code reviews; any exception in this step drops `base`/`covers`, never the line. No writes to the checkout (fallback-log stays as is; the hand-written `## Codex catch-up` section remains for humans).

Report: a Claude review line (reviewer starts with `claude`) is covered when a Codex line of the same `project` has a `covers` entry with the same mode and the same reviewed HEAD: for re-check lines `reviewed_head` (T003), else `head`; full-SHA equality. "## Claude-only reviews (Codex catch-up pending)" lists only uncovered ones (heading text unchanged; omit the section when none are pending). New section "## Codex catch-up coverage": one line per Codex line with a non-empty `covers` (time, project, branch, `base12..head12`, number of Claude reviews covered). Old Claude lines (re-checks without `reviewed_head`) and old catch-ups (before this change, e.g. the 2026-10-07 hand-run one) stay pending; say so in the docs.

Row placement (`fallback_record`): insert the new row directly after the last row of the log's table (the contiguous `|` lines following the `| Date (UTC) |` header) instead of at the end of the file; a file without that header keeps today's behaviour (append). Do not rewrite or reorder existing rows.

Tests (new `test_outcome_catchup_*` and `test_fallback_record_*`; offline, mock reviewers):
- Claude fallback code review (round 1, `MOCK_CODEX_LIMIT`), then a further commit and a Codex code review of the same branch from the same base: the Codex line has `base` and `covers` with round 1's mode/HEAD; the report no longer lists round 1 as pending and shows it under coverage.
- Not covered: a Codex review whose base is a descendant of the Claude row's base (e.g. `--base` at a later commit of the branch), and a Codex review on another branch that does not contain the Claude HEAD; both leave it pending.
- Plan-mode Claude row inside the Codex range is covered; a row with an unknown HEAD is skipped without error.
- A Claude (forced, `AI_REVIEWER=claude`) code review line gets `base` and no `covers`.
- Report from hand-written JSONL across two projects: a covers entry in project A does not cover the same HEAD in project B.
- `fallback_record` with an existing `## Codex catch-up` section after the table: the new row lands in the table, the section text is unchanged and stays below.
Keep `test_runner_logs_task_outcomes_and_report` passing (its two Claude reviews stay pending).

Docs: README (Claude fallback reviewer catch-up paragraph and "Outcome log"), `docs/workflow.md` (Records and "Outcome log": `base`, `covers`, the rule, what stays pending), and the vault flow note `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`: "Outcome log" bullet and the "one catch-up review" sentence of the fallback reviewer bullet (a Codex code review records which fallback reviews it covers; the report drops them from pending); bump `updated:`. Append a dated line to the hub `agents.md` Log (do not tick vault checkboxes). The handoff's `## Flow chart` says "Flow chart updated".

### Likely affected modules
scripts/lib/workflow.py (fallback_record, outcome, outcomes_report), tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md, vault agents.md (Log)

### Acceptance criteria
- A Codex code review whose range contains a Claude fallback review's range records it in `covers`; the report stops listing it as pending and lists it under coverage.
- Ranges not contained (later base, other branch, unresolvable rows) stay pending; no exception reaches the caller and the outcome line is always written.
- Coverage never crosses projects; re-checks match on `reviewed_head`.
- New fallback rows land inside the table even when a `## Codex catch-up` section follows it.
- No change to `ai-review`/`ai-pipeline`; existing review, fallback and outcome tests pass.
- README, `docs/workflow.md` and the vault flow note describe the same rule.

### Validation
`python3 -m unittest tests.test_workflow -k outcome -k fallback -k fall_back -k catchup`; `.ai/bin/ai-check`

### Result / notes
