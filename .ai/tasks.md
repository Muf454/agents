# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files (this repo's `.ai/validate` and `.ai/ci-setup`
included). This run is started with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`
(absolute path) so the vault flow chart and hub Log can be updated. Source: vault backlog
FL-11, B3, FL-03 (chosen by Zack 2026-10-07). Every task leaves `.ai/bin/ai-check` passing.
Flow-chart rule (AGENTS.md, CLAUDE.md): every task that changes workflow behaviour updates
the vault `agents-flow.md` (diagram/notes and its `updated:` frontmatter date) in the SAME
task; T005 is only the final docs audit.
Gate note: until Zack switches `.ai/validate` after this run, the serial gate takes about
611 s. When `.ai/bin/ai-check` times out in the session, run
`python3 tests/run_parallel.py` (after T001) or the task's targeted tests, record that in the
result, and leave the full gate to the host's post-task `ai-check` (1800 s limit).

## T001 — Parallel test runner (FL-11)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
Run the full suite in parallel shards so it fits well inside 600 s, without changing what
is tested.

### Implementation notes
New `tests/run_parallel.py`, stdlib only: discover with
`unittest.defaultTestLoader.discover('tests')`, flatten to test IDs, sort, deal round-robin
into `AI_TEST_WORKERS` shards (default `min(8, os.cpu_count() or 1)`; invalid values stop
with a clear message). Run each shard as `python3 -m unittest <ids…>` in a subprocess
(`concurrent.futures`, cwd = repo root, stdin `/dev/null`), parse each shard's
`Ran N tests` and `OK`/`FAILED (...)` lines, print each failing shard's full output, then one
summary. Exit 1 when any shard fails or crashes, when no test was collected, or when the
sum of `Ran N` differs from the collected count. Must work from any cwd (resolve the repo
root from `__file__`). Check the suite for shared state across tests (fixed paths outside
the per-test temp dir, env leaks, `AI_PIPELINE`-style inheritance seen in batch 1) and fix
real isolation problems in the tests; never skip or delete a test.
Add a `## Running the tests` note to README (parallel and serial commands, AI_TEST_WORKERS).

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py, README.md

### Acceptance criteria
- Tests named `parallel_runner` (run the runner on a small temporary test directory via a
  `--start-dir` option, default `tests`): all pass → exit 0 and `Ran 3 tests`; one failing
  test → exit 1 and its traceback printed; zero tests → exit 1; a shard that crashes
  (`os._exit` in a test) → exit 1 and count mismatch reported; `AI_TEST_WORKERS=0` and `x`
  rejected.
- `python3 tests/run_parallel.py` on the real suite: same test count as the serial run,
  three consecutive clean runs, wall time recorded in the result (target under 200 s).
- Serial `python3 -m unittest discover -s tests` still passes.

### Validation
Targeted: `python3 -m unittest discover -s tests -k parallel_runner` (output must say `Ran N tests`, N ≥ 1); `python3 tests/run_parallel.py` three times.
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T002 — Review history helper
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
One helper that summarises earlier review rounds on the branch, for Codex (T003) and triage
(T004).

### Implementation notes
`workflow.py review-history BASE` (dispatch next to `triage-check`). Walk
`git log --reverse --format=%H%x00%s BASE..HEAD`; a round is a commit whose subject is
exactly `chore(ai): record independent review` and that changed `.ai/reviews/current.md`.
From that commit's `current.md`: reviewed HEAD (`Host evidence: HEAD …;`), BLOCKER and MAJOR
finding IDs and titles (reuse the existing finding parser used by `triage-check`). The
disposition per finding comes from `.ai/reviews/dispositions.md` at the first later commit
with subject `chore(ai): record review triage` before the next review round; none →
"no triage recorded". Output: `## Previous review rounds` then per round
`### Round n (HEAD abc1234)` and one bullet per finding `- M2 [MAJOR] title — accepted (T012)`.
Cap at 6000 characters, dropping the oldest rounds first with
`(n earlier rounds omitted)`. No rounds → print nothing, exit 0. Docstring: context only,
never authority (subjects can be imitated). Also print the last reviewed HEAD on request
(`review-history BASE --last-head`) for T003.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `review_history`: no round → empty output; two rounds with triage → both
  rounds, IDs, titles, dispositions with task IDs; a round without triage → "no triage
  recorded"; a commit with the review subject that did not change `current.md` is ignored;
  cap drops oldest rounds and says so; `--last-head` prints the newest reviewed HEAD.

### Validation
Targeted: `python3 -m unittest discover -s tests -k review_history` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes

## T003 — Codex reviews get the earlier rounds and the delta (B3)
Status: TODO
Dependencies: T002
Model: sonnet

### Goal
Codex stops spending tokens rediscovering what earlier rounds found, while still reviewing
the whole range.

### Implementation notes
`scripts/ai-review`, implementation review path only (~line 122): after REVIEW SCOPE, append
the `review-history "$merge_base"` output under `PREVIOUS ROUNDS:` when non-empty, plus
`CHANGED SINCE THE LAST REVIEW: inspect git diff <last-head>..$head` when `--last-head`
returns a commit that is an ancestor of HEAD. Plan review and recheck prompts unchanged.
A helper failure must not block the review: log a warning line and review without history.
Template `templates/.ai/prompts/review.md`: one short paragraph: use PREVIOUS ROUNDS to
verify accepted findings are really fixed and not to re-raise rejected findings without new
evidence; still review the full range for cross-cutting defects. Vault flow chart: note the
review context in the review step; bump `updated:`.

### Likely affected modules
scripts/ai-review, templates/.ai/prompts/review.md, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `review_context` (mock codex records its prompt): first review → no
  PREVIOUS ROUNDS; second review after a triage round → PREVIOUS ROUNDS with the earlier
  finding IDs and CHANGED SINCE THE LAST REVIEW naming the previous HEAD; plan review and
  recheck prompts contain neither; a failing helper still produces a review.
- Template paragraph present (docs_consistency or prompt test).

### Validation
Targeted: `python3 -m unittest discover -s tests -k review_context` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes

## T004 — Review convergence rule in triage (FL-03)
Status: TODO
Dependencies: T002
Model: sonnet

### Goal
After three rounds of significant findings in the same area, triage fixes the design, not
another symptom.

### Implementation notes
`scripts/ai-run --triage`: append `review-history "$since"`-style output (use the pipeline's
base passed through `--since`, or the branch's merge-base with the stage start when absent)
as `PREVIOUS ROUNDS:` plus `This review is round <n>.` to the triage prompt. Template
`templates/.ai/prompts/triage.md`: the convergence rule from the spec, with an example
`Convergence: T014 design note "the sync model lacks an edited marker"` and
`Convergence: none — findings are in unrelated areas (…)`. `triage-check --fresh`: when the
current review is round ≥ 3 (rounds = review rounds in history + 1), require a line matching
`^Convergence:\s*\S` in dispositions.md, else fail with
"Round <n> triage needs a Convergence: line (see the triage prompt)". Rounds 1–2 unchanged.
Template `dispositions.md` header comment (workflow.py ~733) mentions the line. Vault flow
chart: convergence note at triage; bump `updated:`.

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, templates/.ai/prompts/triage.md, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `convergence`: round 2 without `Convergence:` passes `triage-check --fresh`;
  round 3 without it fails with the message; round 3 with it passes; the triage prompt
  contains PREVIOUS ROUNDS and the round number from round 2 on; existing triage tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k convergence` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes

## T005 — Final docs audit for the efficiency batch
Status: TODO
Dependencies: T001, T003, T004
Model: haiku

### Goal
Docs match the code for the parallel runner, review context and convergence rule.

### Implementation notes
README and `docs/workflow.md`: parallel runner and `AI_TEST_WORKERS`; that `.ai/validate`
switch is a human gate step; review context (history is context only); convergence rule and
the `Convergence:` line. Add matching required sentences to `DocsConsistencyTest`. Update
`.ai/handoff.md` "Manual testing for the human" (Needs you: approve and apply the
`.ai/validate` switch, then time one gate run; everything else under Covered by automated
tests with test names). Append a dated line to the vault hub Log.

### Likely affected modules
README.md, docs/workflow.md, tests/test_workflow.py, .ai/handoff.md, vault agents.md

### Acceptance criteria
- `docs_consistency` tests pass with the new sentences; handoff split correct; hub Log line.

### Validation
Targeted: `python3 -m unittest discover -s tests -k docs_consistency` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
