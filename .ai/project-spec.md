# Spec: Flow batch 5: finding IDs with severity and title (FL-16), crash-durable task outcomes (CU-5), recovery reasons cut at a boundary (R13)

## Objective
Remove the last known record-format stop in plan revisions (FL-16), make the outcome log
record task attempts whose runner died without its exit handler (CU-5), and stop recovery
notifications from ending mid-word (R13). Source: vault `agents-backlog.md`. Branch
`fix/flow-batch-5`, created from `fix/flow-batch-4` at df0d3c2 (PR #29, open, not merged;
master has #27 and #28). Planned by Claude on 2026-10-17 (unattended planning session; the run
starts ~03:45 and must finish before 09:00, so the batch is 6 tasks). Assumptions are recorded
below and in `.ai/current-plan.md` instead of being asked. Out of scope by instruction: MC-01,
DB-04, FL-05, FL-08, FL-10 and the FL-23 profiling follow-up.
Hub decisions respected: AD-4 (small files in host state / `.ai/local/`, no daemon), AD-5
(telemetry never authorizes anything), gate files are never edited by a pipeline session.

## Verified against the code (2026-10-17, df0d3c2, PR #29 included)
- **FL-16 half done.** Triage rows already accept a severity suffix in the finding cell:
  `DISPOSITION_ROW` (`scripts/lib/workflow.py:995`) has `(?:[ \t]*\((?:BLOCKER|MAJOR|MINOR)\))?`
  (robustness batch T004, 2026-10-08; tests `test_triage_severity_suffix_*`,
  tests/test_workflow.py:7351–7378). Still open: (a) `PLAN_DISPOSITION_ROW` (workflow.py:2445–2447)
  has no suffix at all, so the observed `| P1 (MAJOR) selection highlight… |` fails
  `plan-dispositions-check` with "Finding P1 has no row" (workflow.py:2631–2633); (b) neither table
  accepts title text after the ID (`test_triage_severity_suffix_other_decorations_stay_unmatched`
  pins `M1 (MAJOR) x` as unmatched); (c) the plan-revision prompt
  (`templates/.ai/prompts/plan-revision.md:29–31`) and the REVISION CONTRACT (`scripts/ai-run:415–427`)
  never show the row form; the triage prompt (`templates/.ai/prompts/triage.md:13`) names "the
  bare finding ID" but shows no full row. Both readers share `TABLE_CELL`/`table_cell` from
  PR #29's T005/T016 (workflow.py:985–996), and every reader uses groups 1–4 of the two row
  regexes (workflow.py:1036, 1112, 1555, 2483, 2624, 3386).
- **CU-5 open.** `ai-run` logs a task outcome only from `task_outcome` (scripts/ai-run:208–212),
  called on DONE/BLOCKED paths and from the EXIT handler `on_exit` (ai-run:169–196). A runner
  killed by SIGKILL, the OOM killer or a power loss runs no handler and logs nothing for that
  attempt; nothing reconciles it later. The append (`outcome()`, workflow.py:3080–3082) is a plain
  buffered `open('a')` without fsync, and a torn last line makes the next appended line part of
  the same unparsable line (`read_outcomes` skips it, workflow.py:2984–3000), losing both.
  Host state per checkout lives in `binding_dir()` (workflow.py:1247–1253), outside agent-write
  roots (`check_state_root`).
- **R13 open.** `recover_decision` cuts the reason and human action with
  `' '.join(value.split())[:300]` (workflow.py:2006), and `bounded_questions` cuts needs-human
  questions the same way (workflow.py:2564–2569); `ai-recover` puts the cut text straight into
  the ⛔ notification (scripts/ai-recover:37–42, 192). The full text is kept nowhere.
- **Already done, not planned** (verified in code; vault ticks are a human todo):
  FL-01 (`ai_deps` before the first task and in recovery, flow batch 2), FL-07 (watchdog timer
  install, PID-based waits), FL-09 (handoff/PR "Needs you" / "Covered by automated tests":
  `templates/CLAUDE.md`), FL-11 (`tests/run_parallel.py`), FL-14 (0-count sections and the
  verdict heading), FL-15 (`Review base: …`), FL-17 (`moved past the branch`,
  scripts/ai-pipeline:193, scripts/ai-recover:130–133), FL-18 (`ai-task check`; the pipeline
  validates the queue before the plan review, hub Log 2026-10-10), FL-19 (session budget default
  = unfinished tasks + 2, at least 16, scripts/ai-run:571–579; lock-owner hint), FL-22
  (`Bash(chmod +x *)` in `templates/.ai/permissions.allow:33`), FL-24, DB-02, DB-03, DB-05,
  and FL-21/CU-1..CU-4 (flow batch 4).
- **Open but not planned here:** R15 (un-draft a PR with `gh pr ready`) changes what the
  pipeline publishes on GitHub and could undo a human's own draft: Zack's call (human todo).
  FL-02, FL-20, OR-* items are M/L or need design decisions.

## Requirements
- **FL-16 finding cell.** In both `dispositions.md` and `plan-dispositions.md` rows, the first
  cell is read as: a finding ID, optionally a severity suffix `(BLOCKER|MAJOR|MINOR)` (any case,
  optional space before it), optionally title text separated from the ID/suffix by whitespace
  (optionally with `—`, `–`, `-` or `:`), on the same line, without an unescaped `|`. The row
  counts only for that first ID. Still unmatched: decoration before the ID (`**M1**`), an
  unknown parenthesised word (`M1 (CRITICAL)`, also with text after it), a list of IDs joined
  by `,` or `/` without a space (`M1,M2`, `M1/M2`), an ID glued to text (`M1x`). A required
  finding without a row fails as today; the message additionally quotes a table line whose
  first cell contains that ID but did not match, with the exact form to use. The prompts and
  host contracts show the exact row form for both tables.
- **CU-5 crash-durable task outcomes.** When an implementation attempt opens, the host writes
  an attempt marker (unique id, task, model, branch, start time, runner pid and its `/proc`
  start time) atomically and durably (temp file, fsync, link, directory fsync) as its own file
  in the checkout's host state directory; no marker is ever overwritten. The normal outcome
  line carries the attempt id and is written in one `write` on a readable append descriptor
  under an exclusive `flock` (so the tail check and the write are one step for every writer
  using the helper), with a newline first when the log's last byte is not one (a torn line
  never swallows the next record); the file and its directory (and any directory just created)
  are fsynced; a write that returns fewer bytes than the line, or a failed sync, is a failure;
  a marker is removed only after a complete, synced append of a record with its id.
  The reader decodes each line on its own, so a torn tail (also inside a multibyte UTF-8
  character) skips only that line.
  At the next attempt open or `ai-run --approved` start (under the checkout lock, before the
  clean-checkpoint refusal, since a killed runner always leaves `.ai/state.md` dirty) every
  leftover marker whose runner is not alive (pid gone or start time different), or which
  belongs to an earlier attempt of the calling runner itself, is reconciled: exactly one
  `crashed` outcome for that attempt (seconds unknown), never a second one when the log
  already has its id, then the marker is removed. Reconcile decides on a strict read of the
  log (a missing log is empty; any other read failure keeps the marker, appends nothing and
  prints a note) and removes a marker whose record already exists only after it has
  successfully synced the log file and its directory under the log lock (a complete write whose
  sync failed is finished here). A marker that cannot be read (open or read error) is kept and
  skipped with a note, and the other markers are still processed; only content that was read
  completely and is not a valid marker is discarded. `attempt-open` prints the attempt id
  before it publishes the marker, and the runner keeps a printed id even when the command
  fails afterwards, so a finished task is never logged `crashed` because its marker outlived
  a failed open (an id without a marker is harmless). A stop that deliberately logs nothing
  (approved gate changed) removes the marker without running a helper. Every new task record
  carries `seq`, a number from one persisted host-wide counter (`attempt-seq` beside the log,
  advanced under the log lock, self-healing from the highest recorded `seq`) allocated when
  the attempt opens (stored in its marker and copied to its outcome and to a reconciled
  `crashed` record) or, for an attempt without an open, when its row is appended; a row is
  never written without one (an allocation failure fails that append). It also carries
  `started` (the attempt's open time from its marker, else the append time minus the
  duration; informational). `ai-status --outcomes` orders a task's attempts by `seq`, rows
  without one (written before this version) first in file order, deriving the task's result
  (last attempt), its attempt count and its first-time pass (first attempt done) from that
  order, so a `crashed` record reconciled late, after a later attempt of the same task
  succeeded, never changes the task's reported result, even when both attempts opened within
  the same second; the stored `attempt` and `first_pass` fields remain the count at append
  time. Advisory telemetry only: never fatal, never a stop; a sync the kernel already failed
  cannot be redone (dirty pages may be gone).
- **R13 recovery text.** Reasons, human actions and needs-human questions longer than their
  300-character cap are cut at a sentence end, else a word boundary, and end with `…`; the full
  recovery reason and human action are written to `.ai/local/recovery-decision.txt` when cut,
  and the ⛔ notification names that file. `last-error` keeps the original stop reason.
- **Docs.** README and `docs/workflow.md` describe each change; the vault flow chart
  (`agents-flow.md`, `updated:`) is updated in the task that changes a described step (CU-5:
  the "Outcome log" bullet), with a dated hub Log line; sessions never tick vault checkboxes.

## Non-goals
No change to `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/ci-setup`, `.ai/permissions.allow`,
`.claude/settings.json` or `.github/workflows/*` (human steps in the handoff). No rewrite or
fsync repair of existing outcome rows (append-only; their durability is out of scope, as in the
dropped `fix/catchup-review` revision 7). No crash detection for triage, review or plan-revision
sessions. No `gh pr ready` (R15). No profiling.

## Acceptance
- Offline regression tests per task (names in `.ai/tasks.md`), in the existing styles;
  existing tests pass (tests changed on purpose are named in the task results).
- `.ai/validate` passes.
- README, `docs/workflow.md` and the vault flow chart match the code.
