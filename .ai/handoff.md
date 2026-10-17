# Handoff

## What has been implemented?
- T001 (done): `tests/run_parallel.py` makes itself a child subreaper on Linux (`main()` only)
  and reaps adopted orphan zombies by pid between thread joins, never `waitpid(-1)`, so batch
  exit statuses and reports are unchanged.
- T002 (done): a stop (worker error, interrupt, SIGTERM) is owned by its first caller and, as
  subreaper, walks the `/proc` tree below the runner: SIGTERM, up to 3 SIGKILL rounds and a
  bounded completion barrier, so GNU `timeout` groups and detached sessions go too; survivors
  are printed (`could not terminate descendants`) and fail the run. No adopted zombie is
  reaped while the stop runs.
- T013 (done): `Dispatcher.run()` starts its workers inside the `try:`, so an interrupt or
  SIGTERM during a later `Thread.start()` still runs `stop()` (once) and joins only the
  threads that started.
- T003 (done): `workflow.py tasks fill-sections` adds a missing `### Likely affected modules`
  (`(not listed)`) or empty `### Result / notes` to TODO tasks only (fence-aware, atomic, silent
  no-op when nothing is missing); `tasks()` shares `REQUIRED_SECTIONS`.
- T004 (done): `ai-run` runs `tasks fill-sections` after the triage, planning and plan-revision
  sessions (before `tasks check`/`reorder`), prints `Task queue: added missing sections: …`, and
  the repair lands in the stage's own commit; the three contracts tell the session to copy the
  exact task format. A task without `### Goal` etc. still stops.
- T006 (done): the triage, plan-revision and plan prompts state the exact task format and the
  pipe rule (`\|` in a table cell); `templates/.ai/tasks.md` says `### Result / notes` starts empty.
  Installed `.ai/prompts` copies are unchanged until the upgrade.
- T011 (done): `workflow.py clear-scratch` empties `.ai/local/scratch` through the pinned
  `.ai/local` descriptor (own descriptor walk, no symlink followed; a symlink at `scratch` is
  unlinked; a symlinked `.ai`/`.ai/local` only warns). `ai-run` `claude_session` calls it before
  each `claude` call and after the post-session `ai_guard_verify`; it never fails the run.
- T007 (done): the runner and triage "How to work here" blocks (still identical) and
  `templates/CLAUDE.md` tell sessions to keep scratch files under `.ai/local/scratch/` (host
  empties it; `rm` stays denied); README and `docs/workflow.md` describe the host clear and
  record the no-permission-change decision. Installed `.ai/prompts` copies unchanged until upgrade.
- T012 (done): `recover-decision` falls back, when the whole answer is not JSON, to one
  line-start object (ending its line) inside prose that contains no `{`, `}`, `[` or `]`; the
  object must be a valid decision. Everything else still escalates with today's reason.
- T008 (done): an escalation for want of a valid decision now reads `the recovery session gave
  no valid decision; it wrote: <excerpt>` (whitespace collapsed, ≤ 300 characters) when the
  answer is non-empty; the recover prompt asks for the object alone with the diagnosis in
  `reason`; README and `docs/workflow.md` state the format and T012's bracket rule. Installed
  `.ai/prompts` copies unchanged until the upgrade.
- T009 (done, CU-2): a covered Claude review leaves "Codex catch-up pending" once a later Codex
  review of the same project, branch and family exists, or `ai-status --catch-up-done BRANCH...`
  records a catch-up (a human command). 5 `test_outcome_catchup_*` tests.
- T010 (done): README, `docs/workflow.md`, the vault flow chart and this handoff were checked
  against the code; no behaviour changed. `DocsConsistencyTest` and `flow_this_repo` pass.
- T014 (done, review M1): `/proc/<pid>/stat` is read as bytes (decoded with
  `surrogateescape`), so a non-UTF-8 process name anywhere on the host no longer makes
  `Dispatcher.stop()` raise; `terminate()` signals the batch groups before any scan, and a scan
  that raises (`Dispatcher.scan()` → None) never aborts the stop: the barrier keeps scanning to
  its deadline and then reports `unknown (descendant scan failed: …)` (run fails).
- T017 (done, review M3): `process_table()` returns `{}` only when there is no `/proc`; when
  `/proc` exists but cannot be listed the `OSError` propagates, so the stop counts it as a
  failed scan (`unknown (descendant scan failed: …)`, run fails) instead of "no descendants";
  `reap_adopted()` skips a round it cannot list and reaps on the next call.

Planned: Branch `fix/flow-batch-4` (from `origin/master` at 7d22939, after
PRs #27 and #28 merged) plans flow batch 4 (2026-10-16, Claude planning session), in priority
order:
- T001–T002 FL-27: `tests/run_parallel.py` becomes a child subreaper on Linux, reaps adopted
  orphans without touching batch exit statuses, and on a worker failure, interrupt or SIGTERM
  terminates the whole descendant tree, GNU `timeout` groups included (PR #28 final review M3).
  T013: an interrupt while workers are still being started goes through the same shutdown
  (plan review round 2 P6).
- T003–T004 FL-25 (a): `workflow.py tasks fill-sections` adds a missing `### Likely affected
  modules` / empty `### Result / notes` to TODO tasks; the host runs it after triage, planning
  and plan-revision sessions.
- T005 FL-25 (b): `\|` inside disposition and plan-disposition cells is part of the cell.
- T006: template prompts show the exact task format and the pipe rule.
- T011 + T007 FL-26: sessions put scratch files under `.ai/local/scratch/`; `ai-run` empties it
  before and after every session through `workflow.py clear-scratch`, which deletes only via
  descriptors pinned without following symlinks (T011, opus; plan review P1); T007 adds the
  prompt rule and docs (no permission change).
- T012 + T008 FL-12: `recover-decision` accepts exactly one valid line-start decision object
  inside prose that contains no `{}[]` (T012, scanner redesign after plan review rounds 1–2
  P3); T008 adds the escalation excerpt of what the session wrote, the prompt and docs.
- T009 CU-2: `ai-status --outcomes` drops Claude reviews covered by a later Codex review of the
  same branch or by `ai-status --catch-up-done BRANCH`.
- T010: docs/handoff audit.
Found already done and not planned (verified 2026-10-16): FL-21 (watchdog stall confirmed
after 5 min), CU-4 (colour variables stripped for batches), CU-1 (attempts per model), CU-3
(re-check severity totals). See `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`.

## Validation run
2026-10-16 after T001: `.ai/bin/ai-check` PASS (689 tests, 424.6 s on 8 workers).
2026-10-16 after T002: `.ai/bin/ai-check` PASS (697 tests, 408.3 s on 8 workers).
2026-10-16 after T013: `.ai/bin/ai-check` PASS (699 tests, 416.7 s on 8 workers).
2026-10-16 after T003: `.ai/bin/ai-check` PASS (702 tests, 406.1 s on 8 workers).
2026-10-16 after T004: `.ai/bin/ai-check` PASS (706 tests, 365.4 s on 8 workers).
2026-10-17 after T006: `.ai/bin/ai-check` PASS (713 tests, 385.2 s on 8 workers).
2026-10-17 after T011: `.ai/bin/ai-check` PASS (721 tests, 396.2 s on 8 workers).
2026-10-17 after T007: `.ai/bin/ai-check` PASS (723 tests, 386.4 s on 8 workers).
2026-10-17 after T012: `.ai/bin/ai-check` PASS (727 tests, 389.6 s on 8 workers).
2026-10-17 after T008: `.ai/bin/ai-check` PASS (731 tests, 390.6 s on 8 workers).
2026-10-17 after T009: `.ai/bin/ai-check` PASS (736 tests; recorded in the run log, not re-run here).
2026-10-17 after T010: targeted `-k Docs` (3 tests) and `-k flow_this_repo` (1 test) OK; full gate: see the run log entry for T010.
2026-10-17 after T014: `.ai/bin/ai-check` PASS (739 tests, 394.3 s on 8 workers); `-k parallel_runner` 32 OK.
2026-10-17 after T017: `.ai/bin/ai-check` PASS (746 tests, 394.6 s on 8 workers); `-k parallel_runner` 34 OK.

## Assumptions
- FL-27: `PR_SET_CHILD_SUBREAPER` + `/proc` walk (Linux only), no cgroups; non-Linux keeps the
  T014 behaviour; a normal run does not kill leftovers.
- FL-25: only the two content-free sections are added, only to TODO tasks, only right after a
  session; escaped pipes are accepted, unescaped ones still split a row.
- FL-26: no `rm`/`git clean` on the allowlist; the host clears `.ai/local/scratch`.
- FL-12: no `--json-schema`; prose around exactly one valid decision is accepted only when the
  prose has no brackets (otherwise escalate: safe side).
- CU-2: a later Codex review of the same project+branch and family covers earlier Claude
  reviews; other branches need `--catch-up-done`.

## Flow chart
Flow chart updated: T004 added the host step `tasks fill-sections` (adds a missing Likely
affected modules / Result / notes) after the triage, planning and plan-revision sessions, in
`~/zWiki/zWiki/20 Projects/agents/agents-flow.md` (triage node, plan/revision script boxes). T007
added "empty .ai/local/scratch" to the pick and gate boxes of "Inside one task". T008, T009
and T012 left the chart unchanged (the recovery box does not describe the answer format; the
catch-up rule is a reviewer-log rule, not a chart box). Nothing pending.

## Manual testing for the human

### Needs you
1. After merging, refresh the installed copies (`setup-project --upgrade --apply` here and in
   raid-planner / family-planner) so `.ai/bin` and `.ai/prompts` get the new behaviour; then on
   one real triage that adds a fix task, check the log shows either no fill line or
   `Task queue: added missing sections …` and no stop.
2. Interrupt a real self-check (`bash .ai/validate`, Ctrl-C after a minute) and confirm with
   `pgrep -af 'ai-toolkit-test|ai-tests-'` that no fixture process is left.
3. Run `.ai/bin/ai-status --outcomes` on your real outcome log: Claude reviews of branches that
   later got a full Codex review are no longer listed as pending (a Codex re-check alone does
   not cover them, review M2); record any other branch's catch-up with `--catch-up-done`.

### Covered by automated tests
Each group below is a name prefix; `python3 -m unittest discover -s tests -k <group>` runs its
tests (the groups are added by the tasks named).
- `test_parallel_runner_subreaper_*` (T001), `test_parallel_runner_tree_*` (T002; T014 added
  `test_parallel_runner_tree_non_utf8_name`, `test_parallel_runner_tree_non_utf8_stat_parse`
  and `test_parallel_runner_tree_scan_failure_still_signals_batch_groups`; T017 added
  `test_parallel_runner_tree_proc_listdir_failure` and
  `test_parallel_runner_tree_proc_listdir_failure_skips_reap_round`), `test_parallel_runner_startup_*` (T013).
- `test_task_sections_fill_*` (T003), `test_task_sections_host_*` (T004),
  `test_task_sections_prompts_show_the_format` (T006).
- `test_disposition_pipes_*` (T005; T016 adds `test_disposition_pipes_missing_task_before_next_row`
  and `test_disposition_pipes_literal_backslash_round_trip`).
- `test_scratch_clear_*` (T011: symlinked `.ai`/`.ai/local` refused, `scratch` symlink unlinked,
  tree removed without entering inner symlinks, cleared before and after a real `ai-run` session,
  a pre-existing `scratch` symlink stops the run at startup), `test_scratch_dir_*` (T007).
- `test_recovery_decision_scan_*` (T012), `test_recovery_decision_prose_*` (T008: prose-only and
  bracketed answers escalate with the excerpt; a mock prose + `rerun` answer resumes the
  pipeline end to end; a prose-only answer's ⛔ notification quotes the session).
- `test_outcome_catchup_*` (T009; T015 adds `test_outcome_catchup_recheck_does_not_cover_code`
  and `test_outcome_catchup_code_covers_recheck`).

## Human todos
- Installed copies: `.ai/bin` and `.ai/prompts` of this repo and other projects keep the old
  behaviour until `setup-project --upgrade --apply` (gate files; sessions never edit them).
- Permissions: no change proposed for FL-26 (`rm` stays denied by design); decide if you want
  more than the scratch-dir rule.
- Backlog (vault, sessions do not tick it): mark FL-21, CU-1, CU-3, CU-4 as already done, and
  FL-25/26/27, FL-12, CU-2 when this merges. Still open and related: FL-16 (plan-disposition
  ID cells with a severity suffix, same regex area as T005).

## Next action
Review round 1 (M1, M2, P7, N1) is fixed: T014, T015 and T016 are DONE. Review round 2
triaged (`.ai/reviews/dispositions.md`): M3 and N2 accepted, none rejected or deferred; T017
(M3: a failed `/proc` listing counts as a scan failure) is DONE and N2 is this section. All
tasks T001–T017 are DONE. Next: re-review, the human's acceptance steps and the merge.
