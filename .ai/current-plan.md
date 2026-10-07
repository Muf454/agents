# Plan: Efficiency batch (FL-11, B3, FL-03)

## Assessment (origin/feature/flow-batch-2 55383d7, PR #15 open)
- Gate: `.ai/validate` = `bash -n` over scripts/templates, then
  `python3 -m unittest discover -s tests` (serial). 224 tests, 611 s (vault hub log
  2026-10-07). Sessions run the gate through the Bash tool with a 600000 ms limit
  (runner/triage "How to work here"), so the session's own gate run now times out and the
  prompt says to mark the task BLOCKED. Host `ai-check` uses `AI_CHECK_TIMEOUT` (1800 s).
- Tests: `tests/test_workflow.py`, classes `ToolkitTest` (per-test `TemporaryDirectory`,
  subprocess-heavy with mock claude/codex/gh) and `DocsConsistencyTest`. Per-test temp dirs
  suggest shards are independent; T001 must verify (shared paths, env, ports, fixed /tmp
  names).
- Review prompt: `scripts/ai-review` ~122 builds `review.md` + REVIEW SCOPE only; Codex
  rediscovers earlier rounds from Git by itself.
- Triage: `scripts/ai-run` ~171 (`--triage`), `triage-check` in workflow.py ~746 checks
  dispositions against the current review. Fix rounds: `fix-rounds` host store (~1244).
- Each round commits `.ai/reviews/current.md` as `chore(ai): record independent review` and
  dispositions as `chore(ai): record review triage`, so history is in Git.

## Approach
1. T001 (opus, concurrency: P4) FL-11 parallel runner in `tests/` (PYTHONPATH per worker,
   P1) + its tests; docs mention. No gate edit. Full-suite timing is coordinator evidence
   (P2/P6).
2. T002 (sonnet) one shared `review_rounds` routine + `review-history` (`--base/--head`,
   `--current` from the review header, `--count`, `--last-head`) + tests (P3).
3. T003 (sonnet) B3: `ai-review --base` appends the history and the delta; `review.md`
   template wording. Flow chart note.
4. T004 (opus) FL-03: triage prompt gets `--current` history and the round; `triage.md`
   rule; `triage-check --fresh` derives the round itself and requires a same-line
   `Convergence:` from round 3 (P5); end-to-end three-round test. Flow chart.
5. T005 (haiku) docs audit (README, docs/workflow.md, docs_consistency sentences).

## Risks
- Parallel shards could expose hidden shared state → T001 acceptance requires three clean
  consecutive runs and identical test counts; fix the test isolation, never skip tests.
- Load-sensitive tests (timeouts) could flake under 8 workers → default capped at 8 and
  overridable; flaky tests are fixed or their timing made robust, not removed.
- History is read from commit subjects an agent could imitate; it is context only and
  grants nothing, so a forged entry can only mislead a reviewer, not skip a gate. Stated in
  the helper's docstring and docs.
- Context size: capped at 6000 characters.

## Human steps
- Before the run: Codex plan review, Zack approves; PR #15 merged (done, `0818f20`; see the
  spec's branch note on why `master` is not merged in).
- After the run, coordinator (host, no session): run `python3 tests/run_parallel.py` three
  times; each must pass with the serial count and finish under 200 s; record counts and wall
  times in `.ai/run-log.md` (P2/P6).
- Then Zack approves switching `.ai/validate` to `python3 tests/run_parallel.py` (gate
  file) in this PR, and later the toolkit upgrade to the project repos as its own PR.

## Authorization
Approved by Zack on 2026-10-07 in chat with Claude: run T001–T005 unattended via
`ai-pipeline` (the pipeline's Codex plan review gates the start). PR #15 merged first
(`0818f20`); this branch contains its content (`55383d7`, identical tree) but not the merge
commit (corrected after plan review P7). Switching `.ai/validate` and merging stay with Zack.
Plan revised after Codex plan review 1 (P1–P7) and re-approved by Zack the same day ("go
ahead").
