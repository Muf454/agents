# Spec: outcome telemetry and parallel test runner follow-ups (CU-1..CU-4)

## Objective
Close the MINOR follow-ups of the Codex catch-up review that the vault backlog
(`agents-backlog.md`, "Codex catch-up review follow-ups (2026-10-07, MINOR, deferred from
`chore/toolkit-upgrade-2`)") lists as CU-1..CU-4. Branch `fix/outcome-followups` from
`origin/master` c7d4dee. CU-5 (crash-durable outcomes) stays in the backlog.

**Telemetry is advisory.** Nothing here may change what the pipeline does (gates, review
flow, triage, re-checks, commits, notifications). Only what is recorded in the host outcome
log (`outcomes.jsonl`) and what `ai-status --outcomes` and the parallel test runner report
changes. Recording stays nonfatal: a failure to compute a new field drops that field, never
the line.

## Verified against the code on this branch (2026-10-08)
- **CU-4: mostly fixed already.** `tests/run_parallel.py` `run_shard` drops `FORCE_COLOR` and
  sets `NO_COLOR=1` for the shards (previous run, T006 on `fix/catchup-review`, run-log
  2026-10-07T18:40Z), so the reported trigger (`FORCE_COLOR=3`) no longer breaks parsing.
  Remaining: on Python 3.13+ `PYTHON_COLORS=1` wins over `NO_COLOR` (`_colorize.can_colorize`
  checks it first; this machine runs 3.14, whose unittest colours its summary), and no test
  covers either case. Kept as a small hardening task with a regression test.
- **CU-1: open.** `workflow.py` `outcomes_report` groups each task's *last* row (`final`) and
  sums all its attempts' seconds (`spent`), so the "Tasks by model" and "model and category"
  tables credit every attempt and minute to the final model.
- **CU-3: open.** `outcome review` skips the report for `mode == 'recheck'`; re-check lines
  carry no counts. Also, the line's `head` is `git rev-parse HEAD` at logging time, which for
  a re-check is after the triage commits, not the reviewed HEAD.
- **CU-2: open.** `outcomes_report` lists every review whose reviewer starts with `claude`
  under "Claude-only reviews (Codex catch-up pending)"; nothing records coverage. The
  catch-up outcome is a hand-written `## Codex catch-up` section in
  `.ai/reviews/fallback-log.md`. Related defect found while verifying: `fallback_record`
  appends each new row at the end of the file, so once that section exists new rows land
  below it (this repo's own log shows two rows after the section).

## Requirements
- **R1 (CU-4)** Shards run without colour whatever the caller's colour settings
  (`FORCE_COLOR`, `PYTHON_COLORS`, `NO_COLOR`): the runner sets `PYTHON_COLORS=0` and
  `NO_COLOR=1` and drops `FORCE_COLOR` for each shard, and parses the summary after stripping
  ANSI escape sequences. Regression tests with `FORCE_COLOR=3` and `PYTHON_COLORS=1`.
- **R2 (CU-1)** Per-model statistics count attempts on the model that ran them. The model
  tables are per attempt: attempts, done, not done, first-time pass (tasks whose attempt 1
  ran on this model and passed, out of tasks whose attempt 1 ran on it), avg minutes per
  attempt. The category table stays per task. A mixed-model retry (attempt 1 sonnet failed,
  attempt 2 opus done) shows one attempt and its time under each model.
- **R3 (CU-3)** A re-check outcome line carries `upheld_blocker`, `upheld_major`,
  `withdrawn_blocker`, `withdrawn_major` (from the verified, published `.ai/reviews/recheck.md`
  and the level of each rejected finding) and `reviewed_head` (full SHA). The report shows
  re-checks in their own table with these totals; plan/code reviews keep theirs.
- **R4 (CU-2)** A Codex code review's outcome line records its merge-base (`base`, full SHA,
  from the published review header) and `covers`: the Claude fallback reviews listed in the
  checkout's `.ai/reviews/fallback-log.md` whose reviewed range lies inside the Codex range
  (rule in T004). Code review lines of any reviewer record `base`. The report lists a Claude
  review as pending only when no Codex line of the same project covers it (matched on mode
  and reviewed HEAD), and shows the coverage. `fallback_record` inserts new rows into the
  table instead of after a later section. Covered work is never hidden by a guess: rows that
  cannot be resolved stay pending. Each log row is judged on its own: a row that is not
  covered or cannot be resolved never drops the coverage of the other rows.

## Constraints
- Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts`, `.ai/validate`,
  `.ai/permissions.allow` or `.claude/settings.json`. No gate change is needed.
- No change to `scripts/ai-review`, `scripts/ai-pipeline`, `scripts/ai-recover`: everything
  happens inside `workflow.py` `outcome`/`outcomes_report`/`fallback_record` (called with the
  same arguments as today) and `tests/run_parallel.py`.
- Tests offline and fast: new test methods; report tests feed hand-written JSONL files to
  `ai-status --outcomes FILE`.
- Keep the report heading text "Codex catch-up pending" (existing tests and habits use it).
- Concurrent work: PR #21 (`feature/supervisor`) and PR #22 (`fix/robustness-batch`) edit
  `scripts/lib/workflow.py` and `tests/test_workflow.py` (plus scripts this batch does not
  touch). Keep hunks local to the outcome/fallback/report functions and to new test methods.
