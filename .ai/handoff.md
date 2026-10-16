# Handoff

## What has been implemented?
Nothing yet on this branch. Branch `fix/flow-batch-4` (from `origin/master` at 7d22939, after
PRs #27 and #28 merged) plans flow batch 4 (2026-10-16, Claude planning session), in priority
order:
- T001–T002 FL-27: `tests/run_parallel.py` becomes a child subreaper on Linux, reaps adopted
  orphans without touching batch exit statuses, and on a worker failure, interrupt or SIGTERM
  terminates the whole descendant tree, GNU `timeout` groups included (PR #28 final review M3).
- T003–T004 FL-25 (a): `workflow.py tasks fill-sections` adds a missing `### Likely affected
  modules` / empty `### Result / notes` to TODO tasks; the host runs it after triage, planning
  and plan-revision sessions.
- T005 FL-25 (b): `\|` inside disposition and plan-disposition cells is part of the cell.
- T006: template prompts show the exact task format and the pipe rule.
- T007 FL-26: sessions put scratch files under `.ai/local/scratch/`; `ai-run` empties it before
  and after every session (no permission change).
- T008 FL-12: `recover-decision` accepts exactly one valid decision object inside prose; the
  escalation reason keeps an excerpt of what the session wrote.
- T009 CU-2: `ai-status --outcomes` drops Claude reviews covered by a later Codex review of the
  same branch or by `ai-status --catch-up-done BRANCH`.
- T010: docs/handoff audit.
Found already done and not planned (verified 2026-10-16): FL-21 (watchdog stall confirmed
after 5 min), CU-4 (colour variables stripped for batches), CU-1 (attempts per model), CU-3
(re-check severity totals). See `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`.

## Validation run
None yet on this branch.

## Assumptions
- FL-27: `PR_SET_CHILD_SUBREAPER` + `/proc` walk (Linux only), no cgroups; non-Linux keeps the
  T014 behaviour; a normal run does not kill leftovers.
- FL-25: only the two content-free sections are added, only to TODO tasks, only right after a
  session; escaped pipes are accepted, unescaped ones still split a row.
- FL-26: no `rm`/`git clean` on the allowlist; the host clears `.ai/local/scratch`.
- FL-12: no `--json-schema`; prose around exactly one valid decision is accepted.
- CU-2: a later Codex review of the same project+branch and family covers earlier Claude
  reviews; other branches need `--catch-up-done`.

## Flow chart
Flow unchanged so far. T004 (host fills task sections after sessions) and T007 (host empties
`.ai/local/scratch`) change the flow and update `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`;
T008 updates it only if the chart describes the recovery answer format.

## Manual testing for the human

### Needs you
1. After merging, refresh the installed copies (`setup-project --upgrade --apply` here and in
   raid-planner / family-planner) so `.ai/bin` and `.ai/prompts` get the new behaviour; then on
   one real triage that adds a fix task, check the log shows either no fill line or
   `Task queue: added missing sections …` and no stop.
2. Interrupt a real self-check (`bash .ai/validate`, Ctrl-C after a minute) and confirm with
   `pgrep -af 'ai-toolkit-test|ai-tests-'` that no fixture process is left.
3. Run `.ai/bin/ai-status --outcomes` on your real outcome log: Claude reviews of branches that
   later got a Codex review are no longer listed as pending; record any other branch's catch-up
   with `--catch-up-done`.

### Covered by automated tests
Each group below is a name prefix; `python3 -m unittest discover -s tests -k <group>` runs its
tests (the groups are added by the tasks named).
- `test_parallel_runner_subreaper_*` (T001), `test_parallel_runner_tree_*` (T002).
- `test_task_sections_fill_*` (T003), `test_task_sections_host_*` (T004),
  `test_task_sections_prompts_show_the_format` (T006).
- `test_disposition_pipes_*` (T005).
- `test_scratch_dir_*` (T007).
- `test_recovery_decision_prose_*` (T008).
- `test_outcome_catchup_*` (T009).

## Human todos
- Installed copies: `.ai/bin` and `.ai/prompts` of this repo and other projects keep the old
  behaviour until `setup-project --upgrade --apply` (gate files; sessions never edit them).
- Permissions: no change proposed for FL-26 (`rm` stays denied by design); decide if you want
  more than the scratch-dir rule.
- Backlog (vault, sessions do not tick it): mark FL-21, CU-1, CU-3, CU-4 as already done, and
  FL-25/26/27, FL-12, CU-2 when this merges. Still open and related: FL-16 (plan-disposition
  ID cells with a severity suffix, same regex area as T005).

## Next action
Implement T001, then the queue in order (T002 depends on T001; T004 on T003; T006 on T004 and
T005; T010 last).
