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
- T007/T008 CU-5 (opus): one outcome append path (readable descriptor, `flock` across
  checkouts, newline guard, complete-write check, file and directory fsync), a per-line UTF-8
  reader, and a store of one never-overwritten marker file per attempt (`outcome attempt-dir`).
- T009 CU-5 (opus): the marker-removal gate: a strict log reader (missing log = empty, any
  other read failure keeps the marker) and `confirm_recorded` (locked read, then file and
  directory sync before a marker whose record exists may go).
- T010 CU-5 (opus): the marker failure contract: a marker that cannot be read is kept (only
  invalid content is discarded), and `attempt-open` prints the id before it publishes the
  marker so the runner always holds the id of a marker that exists.
- T012 CU-5 (opus): the attempt sequence: one persisted counter beside the outcome log
  (advanced under the log lock) gives every attempt a `seq` when it opens, or when its row is
  appended if it had no open; markers and rows carry it; `ordered_attempts` orders a task's
  rows by it, rows without one (older versions) first in file order.
- T011 CU-5 (opus): the report: every new task record also carries `started` (informational),
  and `ai-status --outcomes` derives a task's result, attempt count and first-time pass from
  the `seq` order, so a `crashed` record reconciled late never changes a successfully retried
  task's result, even when the retry opened within the same second.
- T003 CU-5 (opus): `workflow.py outcome attempt-open / attempt-reconcile`, durable attempt
  markers in host state, `attempt_id`, `seq` and `started` on task outcomes; a marker whose
  outcome could not be appended survives later attempts and is recorded once.
- T004 CU-5 (opus): `ai-run` reconciles leftover markers at start (before the clean-checkpoint
  check), opens one per attempt (keeping a printed id even when the open fails) and removes
  it on a gate-broken stop; a SIGKILLed runner's attempt is logged as `crashed` once at the
  next start.
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
- CU-5: limited design (one marker file per attempt, idempotent by attempt id, locked
  newline-guarded append, fsync of new data and its directories only); durability of earlier outcome rows is a non-goal; only
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
3. Optional: on a disposable checkout, `kill -9` a running `ai-run` during a task session and
   start it again: that start logs the attempt and then stops with `Start from a clean
   checkpoint` (the killed runner left `.ai/state.md` dirty); check `.ai/bin/ai-status
   --outcomes` shows the attempt as `crashed`, commit or reset the leftovers, and start again.

### Covered by automated tests
Each group below is a name prefix; `python3 -m unittest discover -s tests -k <group>` runs its
tests (the groups are added by the tasks named).
- `test_finding_cell_*` (T001: severity suffix and title accepted in both tables, decorations
  still rejected with a hint; T002: `test_finding_cell_prompts_show_the_row`).
- `test_outcome_log_io_*` (T007: append to a non-empty log, newline guard, torn multibyte tail
  skipped, short write reported as failure).
- `test_outcome_write_protocol_*` (T008: append waits for the log lock so a concurrent partial
  line cannot swallow it, file/directory fsync order, directory-sync failure, marker store
  never overwrites).
- `test_outcome_removal_gate_*` (T009: strict reader tells a missing log from an unreadable
  one, `confirm_recorded` syncs file then directory before confirming and waits for the log
  lock).
- `test_outcome_marker_contract_*` (T010: a marker read error is kept apart from invalid
  content, `open_attempt` prints the id before publishing, a failed publish after the link
  leaves the marker with the printed id).
- `test_outcome_attempt_seq_*` (T012: the counter advances per attempt and persists, heals
  from the log when lost, waits for the log lock, an allocation failure appends nothing;
  `ordered_attempts` puts rows without `seq` first in file order and the rest by `seq`).
- `test_outcome_attempt_order_*` (T011: a crashed attempt appended after a later `done` of
  the same task keeps its place by `seq`, also with equal wall-clock seconds, so the task
  stays done with both attempts counted; rows without `seq` keep today's file order).
- `test_outcome_attempt_*` (T003: marker, reconcile once, crash between append and unlink, live
  runner kept, garbage marker, an unreadable marker kept while the others are processed,
  torn last line, short write keeps the marker, a failed first outcome survives the second
  attempt and is recorded once, a failed sync is finished before the marker goes, an
  unreadable log keeps the marker and never duplicates, a failed open still removes its
  marker on the normal outcome, a marker reconciled only after a successful retry leaves the
  task reported done).
- `test_outcome_crash_*` (T004: SIGKILLed runner logged as `crashed` at the next start, which
  then refuses the dirty checkout; a failed attempt open keeps the id and the task is never
  reported `crashed`; normal paths unchanged, gate-broken stop leaves no marker).
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
