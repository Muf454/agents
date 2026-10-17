# Handoff

## What has been implemented?
Nothing yet in this batch. Branch `fix/flow-batch-5` (from `fix/flow-batch-4` at df0d3c2;
PR #29 open, not merged) plans flow batch 5 (2026-10-17, Claude planning session):
- T001 FL-16 (sonnet): both disposition tables read a first cell `ID`, `ID (SEVERITY)` or
  `ID (SEVERITY) title` (also `ID — title`, `ID: title`); decoration before the ID, unknown
  parenthesised words and glued ID lists stay unmatched; the "no row" errors quote the line
  that did not match and show the form to write.
- T002 FL-16 (haiku): the triage and plan-revision prompts, both host contracts and the
  host-written table comments show an example row with the ID alone.
- T003 CU-5 (opus): `workflow.py outcome attempt-open / attempt-reconcile / attempt-path`, a
  durable per-checkout attempt marker in host state, `attempt_id` on task outcomes, and a
  newline-guarded, fsynced single-write append.
- T004 CU-5 (opus): `ai-run` reconciles a leftover marker at start, opens one per attempt and
  removes it on a gate-broken stop; a SIGKILLed runner's attempt is logged as `crashed` once at
  the next start.
- T005 R13 (sonnet): recovery reasons, human actions and needs-human questions are cut at a
  sentence or word boundary with `…`; a cut recovery decision is kept in full in
  `.ai/local/recovery-decision.txt`, named in the ⛔ notification.
- T006 (haiku): docs, vault and handoff audit.
Found already done and not planned (verified 2026-10-17): FL-01, FL-07, FL-09, FL-11, FL-14,
FL-15, FL-17, FL-18, FL-19, FL-22, FL-24, DB-02, DB-03, DB-05 and the triage half of FL-16.
See `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`.

## Validation run
None yet in this batch. PR #29's last gate: `.ai/bin/ai-check` PASS (746 tests, 394.6 s on 8 workers).

## Assumptions
- FL-16: tolerating title text after the ID is fine; a row counts only for its first ID.
- CU-5: limited design (one marker per checkout, idempotent by attempt id, newline guard,
  fsync of new data only); durability of earlier outcome rows is a non-goal; only
  implementation attempts are tracked.
- R13: the 300-character caps stay; only the cut position and the full-text file are new.
- R15 (un-draft PRs) is not planned: it changes what the pipeline publishes (human decision).

## Flow chart
Flow unchanged so far. T004 will update the "Outcome log" bullet of
`~/zWiki/zWiki/20 Projects/agents/agents-flow.md` (crashed attempts logged at the next start);
T005 updates the notifications text only if the chart states the 300-character cut.

## Manual testing for the human

### Needs you
1. After merging (#29 first, then this branch), refresh the installed copies
   (`setup-project --upgrade --apply` here and in raid-planner / family-planner) so `.ai/bin`
   and `.ai/prompts` get the new behaviour.
2. On the next real plan revision or triage, glance at the dispositions table: rows use the
   bare ID (the prompts now show it); if a session still writes `P1 (MAJOR) title`, the run
   continues instead of stopping.
3. Optional: on a disposable checkout, `kill -9` a running `ai-run` during a task session,
   start it again, and check `.ai/bin/ai-status --outcomes` shows that attempt as `crashed`.

### Covered by automated tests
Each group below is a name prefix; `python3 -m unittest discover -s tests -k <group>` runs its
tests (the groups are added by the tasks named).
- `test_finding_cell_*` (T001: severity suffix and title accepted in both tables, decorations
  still rejected with a hint; T002: `test_finding_cell_prompts_show_the_row`).
- `test_outcome_log_io_*` (T007: append to a non-empty log, newline guard, torn multibyte tail
  skipped, short write reported as failure).
- `test_outcome_attempt_*` (T003: marker, reconcile once, crash between append and unlink, live
  runner kept, garbage marker, torn last line, short write keeps the marker).
- `test_outcome_crash_*` (T004: SIGKILLed runner logged as `crashed` at the next start, normal
  paths unchanged, gate-broken stop leaves no marker).
- `test_recovery_reason_shorten_*` (T005: boundary cuts, full-text file, ⛔ notification names it).

## Human todos
- Installed copies: `.ai/bin` and `.ai/prompts` of this repo and other projects keep the old
  behaviour until `setup-project --upgrade --apply` (gate files; sessions never edit them).
- Backlog (vault, sessions do not tick it): mark FL-01, FL-07, FL-09, FL-11, FL-14, FL-15,
  FL-17, FL-18, FL-19, FL-22, FL-24, DB-02, DB-03, DB-05 done if not already; FL-16, CU-5 and
  R13 when this merges.
- Decide R15 (should `ai-pipeline` run `gh pr ready` on an existing draft PR once its review is
  clean and no dispute remains?).
- Merge order: PR #29 before this branch (it builds on #29).

## Next action
Start the pipeline on `fix/flow-batch-5` (plan review, then T001).
