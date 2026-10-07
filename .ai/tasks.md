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
611 s. When `.ai/bin/ai-check` times out in the session, run the task's targeted tests,
record the timeout in the result, and leave the full gate to the host's post-task
`ai-check` (1800 s limit). Sessions cannot run `python3 tests/run_parallel.py` directly (not
on the frozen allowlist; plan review P2); the full-suite parallel runs are host evidence
recorded by the coordinator after the run (see the plan's "Human steps").
Revised after Codex plan review 1 (`.ai/reviews/plan.md`, P1–P7).

## T001 — Parallel test runner (FL-11)
Status: DONE
Dependencies: none
Model: opus

### Goal
Run the full suite in parallel shards so it fits well inside 600 s, without changing what
is tested.

### Implementation notes
New `tests/run_parallel.py`, stdlib only: discover with
`unittest.defaultTestLoader.discover('tests')`, flatten to test IDs, sort, deal round-robin
into `AI_TEST_WORKERS` shards (default `min(8, os.cpu_count() or 1)`; invalid values stop
with a clear message). Run each shard as `python3 -m unittest <ids…>` in a subprocess
(`concurrent.futures`, cwd = repo root, stdin `/dev/null`). Discovery IDs such as
`test_workflow.DocsConsistencyTest.…` only import with the discovery directory on the
import path (P1: a bare subprocess fails with `ModuleNotFoundError`), so every worker gets
`PYTHONPATH` = the resolved start directory (absolute, also for `--start-dir`), prepended to
any existing value. Add `--collect-only` (print the collected count and exit 0). Parse each shard's
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
- Tests named `parallel_runner` (run the runner as a subprocess on a small temporary test
  directory via a `--start-dir` option, default `tests`, with `PYTHONPATH` removed from the
  environment): all pass → exit 0 and `Ran 3 tests`; launched once with cwd = repo root and
  once with cwd = an unrelated temp directory, both pass; one failing test → exit 1 and its
  traceback printed; zero tests → exit 1; a shard that crashes (`os._exit` in a test) →
  exit 1 and count mismatch reported; `AI_TEST_WORKERS=0` and `x` rejected; on the real
  `tests` directory `--collect-only` reports the same count as
  `unittest.defaultTestLoader.discover('tests').countTestCases()`.
- Serial `python3 -m unittest discover -s tests` still passes (host gate).
- Not session evidence (P2/P6): the three full parallel runs, each under 200 s with default
  workers and the same count as serial, are run and recorded by the coordinator after the
  pipeline and are a precondition for the `.ai/validate` switch, not for T001 DONE.

### Validation
Targeted: `python3 -m unittest discover -s tests -k parallel_runner` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-07 (Claude, opus): `tests/run_parallel.py` (stdlib; `--start-dir`, `--collect-only`,
`AI_TEST_WORKERS` with default min(8, CPU count); empty value = default; 0/negative/non-integer
rejected on stderr, exit 1). Each shard gets `PYTHONPATH` = resolved start dir + existing value,
cwd = repo root, stdin /dev/null. Exit 1 on failing/crashed shard (full output printed), zero
tests, count mismatch, or a module that fails to import (its error is printed; discovery
`_FailedTest` IDs cannot be loaded by name in a shard). `ParallelRunnerTest`: 7
`parallel_runner` tests (all pass from repo root, an unrelated cwd and a relative
`--start-dir`; failing test traceback; zero tests; `os._exit` crash + count mismatch; import
error; invalid workers; `--collect-only` equals a fresh `TestLoader().discover('tests')`
count). Targeted: `python3 -m unittest discover -s tests -k parallel_runner` → Ran 7 tests OK.
Isolation audit: `ToolkitTest` uses a per-test temp dir, copied env (pipeline vars popped),
mocked systemd/gh/claude/codex and per-test XDG/AI_STATE_DIR; the watchdog's runner scan is
scoped by process cwd (per-test dir); no in-process env/cwd mutation. One real race fixed:
`test_watchdog_setup_no_pgrep_f_waits…` walked `scripts/` and could read a `__pycache__`
temp file another shard was writing; it now skips `__pycache__`. README `## Running the tests`.
Session cannot run `python3 tests/run_parallel.py` itself (denied by the allowlist, as
expected per P2), so full-suite parallel runs remain coordinator evidence. Gate: foreground
`.ai/bin/ai-check` exceeded the 600 s Bash tool limit and finished in the background with
`Ran 236 tests in 618.180s OK`, then "Validation modified project content" because this
session edited `.ai/` records while it ran; the host's post-task `ai-check` on the committed
tree is the gate of record (gate note).
2026-10-07 resume (Claude, opus): host gate had failed on
`test_pr_body_flow_this_repo_declares_the_flow_chart` (live handoff says "Flow unchanged");
coordinator fix df0aefd accepts either wording. Re-verified: targeted `-k parallel_runner
-k flow_this_repo` Ran 8 OK; foreground `.ai/bin/ai-check` Ran 236 tests in 598.682s OK
(inside the 600 s limit, barely). DONE.

## T002 — Review history helper
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
One helper that summarises earlier review rounds on the branch, for Codex (T003) and triage
(T004).

### Implementation notes
One shared routine (P3) `review_rounds(base, head)` in workflow.py returning the list of
earlier rounds (uncapped) and a renderer that applies the cap, so the count never depends
on rendering. Two entry points (dispatch next to `triage-check`):
- `review-history --base B --head H` (used by ai-review before the new review exists:
  earlier rounds = rounds in `B..H`);
- `review-history --current` (used by triage and convergence): read the current review's
  host header `<!-- Host evidence: HEAD H; merge-base M; … -->` from
  `.ai/reviews/current.md` and use rounds in `M..H`. The current review's own commit comes
  after H, so it is excluded by construction; no `--since` and no branch base needed, and
  the result is the same in every caller (pipeline triage, ai-run triage, interrupted-triage
  recovery). `--since` stays only the triage scope boundary.
- `--count` prints only the uncapped number of earlier rounds.
Walk `git log --reverse --format=%H%x00%s B..H`; a round is a commit whose subject is
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
(`--last-head`, with `--base/--head`) for T003.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `review_history`: no round → empty output; two rounds with triage → both
  rounds, IDs, titles, dispositions with task IDs; a round without triage → "no triage
  recorded"; a commit with the review subject that did not change `current.md` is ignored;
  cap drops oldest rounds and says so while `--count` still reports the uncapped number;
  `--last-head` prints the newest reviewed HEAD; `--current` built from real host commit
  order (review commit, triage commit, fix commits, second review committed as current)
  lists exactly the first round and `--count` is 1 (the current review is excluded);
  `--current` without a host header fails clearly.

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
the `review-history --base "$merge_base" --head "$head"` output under `PREVIOUS ROUNDS:` when non-empty, plus
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
Model: opus

### Goal
After three rounds of significant findings in the same area, triage fixes the design, not
another symptom.

### Implementation notes
`scripts/ai-run --triage`: append `review-history --current` output as `PREVIOUS ROUNDS:`
plus `This review is round <n>.` (n = `review-history --current --count` + 1) to the triage
prompt. `--since` is unchanged (scope boundary only). Template
`templates/.ai/prompts/triage.md`: the convergence rule from the spec, with an example
`Convergence: T014 design note "the sync model lacks an edited marker"` and
`Convergence: none — findings are in unrelated areas (…)`. `triage-check --fresh`: compute
the round itself from the same routine (`review_rounds` via the current header, uncapped
count + 1), so all its callers (ai-pipeline ~221 and ~348, ai-run ~183 and ~205) agree with
no new arguments; when the round is ≥ 3, require a line matching
`^Convergence:[ \t]*[^ \t\r\n]` (P5: same-line text; `\s` would cross newlines) in
dispositions.md, else fail with "Round <n> triage needs a Convergence: line (see the
triage prompt)". Rounds 1–2 unchanged. Plain `triage-check` (without `--fresh`) unchanged.
Template `dispositions.md` header comment (workflow.py ~733) mentions the line. Vault flow
chart: convergence note at triage; bump `updated:`.

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, templates/.ai/prompts/triage.md, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `convergence`:
  - end to end through `ai-pipeline` with mock codex/claude and the real host commit order,
    three review rounds with BLOCKER/MAJOR findings (`--max-fix-rounds 3`): round 2 triage
    passes without `Convergence:`; round 3 triage without it stops with the message; with
    it the round passes; the triage prompt says "round 2"/"round 3" and lists the earlier
    rounds' finding IDs;
  - an interrupted round-3 triage resumed through `ai-run --triage` reports the same round
    number; a history long enough to hit the 6000-character cap still counts round 3;
  - `Convergence:` empty, whitespace only, or followed only by the table on the next line
    fails; `Convergence: T014 design note …` passes;
  - existing triage tests pass.

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
