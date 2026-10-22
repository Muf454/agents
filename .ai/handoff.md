# Handoff

## What has been implemented?
- T201 (FL-39, 2026-10-22): `ai-pipeline` enters the plan review when `tasks newly-done BASE`
  is empty (earlier batches' DONE tasks no longer skip it; a helper error fails closed and
  skips). Every skipped review prints one `Plan review skipped: <why>` line: `--skip-plan-review`,
  `resuming preserved work (armed resume)`, `tasks done since the base: T…` (first three ids),
  or, on the loop's first pass, `the current plan review is reused (BLOCKER b, MAJOR m)`.
  `tasks untouched` stays as a helper (still used by `ai-run --revise-plan`; T214).
- T214 (FL-39 review P2, 2026-10-22): `ai-run --revise-plan` refuses only when a task became DONE
  since the base (`a task is already DONE since the base (T…)`), and after the session checks
  `plan-keeps-done START` (an edited DONE block stops with `Plan revision stage: …`).
  `revision-queue-repair --base REV` ignores tasks already DONE at REV (`ai-pipeline` passes its
  base, `ai-run` the merge-base of `--base`); without `--base` the old rule stays. The helper
  `newly_done_ids` is shared with `tasks newly-done`. `tasks untouched` is now unused by the
  runner scripts (kept as a helper).
- T203 (TS-01 (2), 2026-10-22): helper `session-gate` prints `MODE SECONDS` (`full` when
  `AI_SESSION_GATE` is empty/auto and a recorded passing gate is under 120 s, else `targeted`;
  `full`/`targeted` force it; any error or invalid value → `targeted 0`, exit 0). `AI_SESSION_GATE`
  is a run setting (config, manifest, recovery restore) validated by `ai-run` and `ai-pipeline`.
  No caller yet (T204).
- T204 (TS-01 (2), 2026-10-22): `ai-run` asks `session-gate` before each task session and appends
  one gate rule to the RUNNER CONTRACT: `full` = Targeted: checks, then `.ai/bin/ai-check` with
  `run_in_background`, waited for (keeps `is not a blocker`); `targeted` = Targeted: checks and
  fast static checks only, without Targeted: lines the task-specific Validation commands but never
  a full-gate entry point; the host gate decides DONE. The FL-28 allowance applies only under
  `full`; a targeted session's `Session:` line reads `gate rule targeted (host gate Ns after the
  session)`. docs/workflow.md updated.
- T206 (ME-01 part 1, 2026-10-22): `workflow.py event KIND key=value…` appends schema-v1 events
  to `<state root>/events.jsonl` (envelope `v,id,time,kind,project,branch,run`; `run` only from a
  16-hex `AI_RUN_ID`; `EVENT_KINDS` per spec A7, `ruling_kind`; gate needs a 16-hex `gate_id`;
  strings one line ≤ 200). Stable `events.lock` (exclusive writers, shared readers), every wait
  bounded by `AI_EVENTS_LOCK_SECONDS` (default 5 s, timer-interrupted flock): busy → `Note: …
  (event log busy).` exit 1; `read_events` raises `EventsBusy`, dedupes ids, skips unknown
  kinds/versions. Schema errors exit 2, nothing written. `common.sh` `ai_event` (gate-broken guard,
  one Note, status 0). No writer calls it yet; flow unchanged. Rotation hook left for T217.
- T219 (ME-01 part 1, 2026-10-22): `redact(text)` in workflow.py replaces secret-looking tokens
  (`EVENT_SECRET_PATTERNS`: `sk-`, `ghp_`, `github_pat_`, `xox[abp]-`, `AKIA`, `Bearer`, values of
  `key=`/`token=`/`secret=`/`password=`) with `[redacted]`; `event_text` calls it before folding
  and the 200-character cut. Best effort, not a secret scanner. docs/workflow.md one sentence.
- T217 (ME-01 part 1, 2026-10-22): `append_event` calls `rotate_events` inside the exclusive lock
  before the append. Over `AI_EVENTS_MAX_BYTES` (int ≥ 65536, default 8 MiB) the whole live file
  goes to `events.1.jsonl` and only lines of active runs (no `run action=end`, latest event ≤ 7
  days old; any project) stay live; no rotation when less than a quarter of the cap would be
  dropped. Temp file + fsync + `os.replace` for the archive, then the live file, then a directory
  sync; a rotation failure is silent and the append still happens. docs/workflow.md paragraph.
- T222 (ME-01 part 1, review P18, 2026-10-22): `outcome gate … [--id GATE_ID]` stores a 16-hex
  `gate_id` (malformed → exit 2, nothing written); `common.sh` `ai_new_id`; pure
  `workflow.py merge_gates(rows, events)` counts each gate once across outcome rows and gate
  events (id join, row's seconds/result/run win, event adds the counts; id-less rows and
  event-only gates count alone). No caller passes `--id` yet (T220); T209/T211 use the merge.
- T220 (ME-01 part 1, review P14/P17, 2026-10-22): every host full gate on an unchanged gate writes
  one `gate` event through `common.sh` `ai_gate_event`: `ai-run` `record_gate` (task id for the
  checkpoint gate and the gate-only retry, `final`) with the same `seconds` and `gate_id` as its
  `outcome gate` row and an epoch start; `ai-pipeline` `ensure_validated` (`validation`) and
  `ai-recover` `commit_validated` (`recovery`), failed and timed-out gates included. Exit paths and
  messages unchanged; a changed gate records nothing.
- T208 (ME-01 part 1, 2026-10-22): `stop` events with a fixed category (`workflow.py
  stop-category STAGE` on the first 4 KiB of `.ai/local/last-error`, telemetry only) and
  `recovery` events (decision, manifest task, reserved attempt) through `common.sh`
  `ai_stop_event`/`ai_recovery_event`, guarded so nothing runs after a gate change; written by
  `ai-pipeline` `stop()` and at each `ai-recover` decision and escalation. Stop behaviour unchanged.

The plan was written 2026-10-21 in an unattended planning session on
`fix/flow-batch-10` (from `fix/flow-batch-9` at 4fea72d; batch 9 is complete there apart from
T118's host verification and is not merged; this PR targets `fix/flow-batch-9` until that
merges). Zack approved the scope on 2026-10-21.
`.ai/project-spec.md` (scope, what was verified in the code, non-goals, assumptions A1–A20, plan
review round 1, 2 and 3 dispositions), `.ai/current-plan.md` (design) and `.ai/tasks.md`
(T201–T222; T001–T046 and T101–T118 are earlier batches, unchanged because the host protects DONE
blocks). Round 1 (Codex by hand, BLOCKER 1, MAJOR 8, MINOR 2; committed in 0848f4b): 9 accepted,
2 adjusted (P7, P8), none rejected; T214–T218 added. Round 2 (HEAD 0848f4b, MAJOR 5; committed
in 369aca1): P12–P16 all accepted; T219–T221 added, T207 split into T207 and T220. Round 3, the
last plan review (`.ai/reviews/plan.md`, HEAD 01f4093, MAJOR 3, MINOR 2): P17–P21 all confirmed
in the code and accepted: gate events take an epoch start separately from the `$SECONDS`
duration (P17, T220); one `gate_id` on the outcome row and the event, each gate counted once
(P18, new T222, used by T209 and T211); metrics list runs from outcomes and events with explicit
`unknown`/`events 0` instead of guessed `open` or zeroes after rotation (P19, T211 now opus,
T212); the TRIAGE CONTRACT gets its own gate rule (P20, T205); a reused current plan review
prints its skip line (P21, T201). IDs are not in file order. The round 3 revision is uncommitted.
- **FL-39** (backlog FL-35): T201, plan review decided against `--base` (`tasks newly-done`), one
  `Plan review skipped: …` line on every skip; T214, the supervised plan revision and its queue
  repair use the same rule and keep earlier DONE blocks byte-identical (P2).
- **TS-01 (1)**: T202, worker default `min(14, cpu - 2)` (or the measured value below) and a
  `Workers: N (…)` first line.
- **TS-01 (2)** (with FL-28): T203 `session-gate` helper and `AI_SESSION_GATE` (auto, full,
  targeted; auto = full only when a passing gate is recorded and it is under 120 s), T204 RUNNER
  CONTRACT and allowance follow the mode (existing allowance tests migrated, P9), T205 prompt
  templates defer to the contract, T215 the task format and task-writing prompts name
  `Targeted:` lines (P11).
- **ME-01 part 1**: T206 `events.jsonl` core (reserved envelope, `ruling_kind`, stable
  `events.lock` with a bounded wait, writers guarded so no helper runs after a gate change,
  tolerant reader; P1, P3, P5, P13), T219 secret redaction, T216 run context (`AI_RUN_ID`, `run`
  on outcome rows and attempt markers; P8), T217 rotation keeping every active run (P3, P4), T207
  `event-gate` helper with safe reads (P16), T222 shared `gate_id` and count-once merge (P18),
  T220 `gate` events from every host gate with epoch starts, failed recovery gates included
  (P14, P17), T208 `stop` (fixed categories) and `recovery`, T209 `run` start
  and exactly one end per finish path or terminal stop (P7), T221 a held event lock never stalls
  a run (P13), T210 `ruling` from all three writers and `review` (P5, P6), T218 `pr` events.
- **ME-01 part 2**: T211 `metrics` data and JSON (attribution by the `run` field only; runs from
  outcomes and events, lifecycle `unknown` and `events 0` when events rotated away; P19), T212
  `ai-status --metrics` text tables and flag.
- T213: docs, flow chart and handoff audit.
- Test selectors: every `Targeted:` line now names a verified existing group or the task's own new
  tests (P10, spec A19).
- Verified and not planned: CU-1 (per-attempt model stats) and CU-5 (crash markers and
  reconcile) are already in the code; OR-04 and BR-17 stay later (spec Non-goals).

Measured worker default: not recorded yet (mission control: write the best of 8/12/14 here before
approving; T202 uses `min(14, cpu - 2)` otherwise).

## Validation run
None on this branch yet. Batch 9's last full gate: PASS, 1104 tests (T116 tree, `ai-check`,
816.3 s). Each batch 10 task runs its `Targeted:` commands and `bash -n` in the session; the host
gate after each session is the full gate (BATCH 10 GATE RULE in the queue header).

## Assumptions
Recorded as A1–A20 in `.ai/project-spec.md`. The ones that shape behaviour most:
- A3/A4: `AI_SESSION_GATE=auto` runs the full gate in the session only when the project has a
  recorded passing gate and the largest of its last 3 passes is under 120 s; otherwise targeted
  checks only and no gate allowance. No recorded gate → targeted.
- A6: a new `events.jsonl`, not new kinds in `outcomes.jsonl`, because outcomes must never rotate
  (attempt numbering and crash reconcile read all of it).
- A8: the run is identified only by `AI_RUN_ID`, exported by `ai-pipeline`/`ai-recover` from the
  run manifest; standalone commands and pre-batch rows have no run (`(no run record)`).
- A9: a stable `events.lock` serializes writers and readers; rotation at 8 MiB
  (`AI_EVENTS_MAX_BYTES`) to `events.1.jsonl` keeps every active run (no end event, active within
  7 days) and only rotates when it frees a quarter of the cap; readers dedupe by event id.
- A10: stop categories are telemetry only; recovery never reads them (OR-04 open).
- A11: exactly one `run end` per handled finish (`pr`, `no_pr`, `no_origin`, `no_gh`) or terminal
  stop (`stopped`); none for a hand-over to recovery, a relaunch wait or a killed pipeline.
- A14: "plan untouched" = no task newly DONE since `--base`, for the review and the revision; a
  helper error skips the review with a line (fails closed).
- A17: no event helper runs after a detected gate change; those stops have no event.
- A15: T118 stays TODO here until `fix/flow-batch-9` is merged into this branch.
- A16: this run's sessions still get the frozen `.ai/prompts`; the BATCH 10 GATE RULE in the queue
  header tells them not to run the full gate.

## Flow chart
Flow chart updated (so far by T201; more to come).
T201 updated the vault `agents-flow.md` plan review node ("no task DONE since the base?", skip
line printed) and its skip edge (2026-10-22). T214: flow unchanged (checked the chart's plan
revision nodes: the entry rule is T201's; an edited DONE block is a revision stop like the
others). T204 updated the "Inside one task" session node (targeted checks; full gate in the
session only under 120 s or `AI_SESSION_GATE=full`), the host gate node (decides DONE) and added
the "Session gate rule" bullet. T208 added the "Stop and recovery events" bullet under "When
something goes wrong" (2026-10-22). Still to come: T209 (run end recorded) updates vault
`agents-flow.md` and add hub Log lines; T213 audits them and adds the "Flow data (ME-01)" line.

## Manual testing for the human

### Needs you
1. Before approving: merge `fix/flow-batch-9` into this branch once T118 is DONE there (both are
   at 4fea72d now; otherwise this run's first session re-verifies T118, same fix). Optionally
   record the measured worker default above.
2. This repo's installed `.ai/bin/ai-pipeline` still has the FL-39 defect, so this run skips
   its own plan review silently (T001–T117 are DONE). Rounds 1–3 were run by hand (Codex; round 3,
   the last: MAJOR 3, MINOR 2, all accepted, spec "Plan review round 3"; uncommitted). Commit the
   revision; no further plan review is planned (the code reviews after implementation check it).
3. Read the plan (`.ai/project-spec.md` A1–A20, `.ai/current-plan.md`) and approve the run
   (`ai-pipeline --approved --base fix/flow-batch-9 --pr-base fix/flow-batch-9 …`). No gate file
   changes are needed to start.
4. After the run: run `ai-status --metrics` (and `ai-status --metrics --json`, `--since
   2026-10-21`, `--project agents`) and check the numbers look right against what you remember of
   recent runs (tasks, first-pass rate, timeouts T108/T109/T111, median gate time about 13 min,
   review rounds), and against the raw `outcomes.jsonl`/`events.jsonl` lines of one run: one
   run's gate durations and starts should match its raw gate rows and events (round 3 reviewer's
   check). Events and the `run` field start only with this batch's code, so older runs show under
   `(no run record)` and their gates come from the id-less `outcome gate` rows. Once events have
   rotated a few times, check that older runs still appear with `unknown` and `events 0` and that
   this reads understandably.
5. After merging (batch 9 first, then this one): run `setup-project --upgrade --apply` here and in
   raid-planner, family-planner and family-budget, so `.ai/bin` and `.ai/prompts` get the new
   session gate rule, the FL-39 fix and the event writers. Then watch the next real run: sessions
   should no longer run `.ai/bin/ai-check` (the `Session:` line says `gate rule targeted`), the
   host gate decides DONE, no task should time out during its own gate, and a local-only finish
   (`--no-pr`) leaves exactly one `run end` event (the reviewer's manual check). Also observe one
   targeted-mode run on an older queue without `Targeted:` lines (round 2 reviewer's check): only
   task-specific checks run in the session, the host gate decides DONE, and the recorded gate
   failures and the `run end` totals agree with the raw logs.

### Covered by automated tests
Test groups (run with `python3 -m unittest discover -s tests -k <group>`); DONE ones marked:
- `plan_review_base` (T201, DONE): earlier DONE tasks plus new TODO tasks get a plan review
  (`test_plan_review_base_earlier_done_tasks_get_a_plan_review`); a resumed run with a task newly
  DONE since base skips with the line (`test_plan_review_base_resumed_run_with_new_done_task_skips`);
  `--skip-plan-review` prints the line (`test_plan_review_base_skip_flag_prints_the_line`); a
  reused current plan review prints its line once and calls no reviewer
  (`test_plan_review_base_current_review_is_reused_with_a_line`).
- `session_gate_templates` / `session_gate_triage` (T205, DONE): runner, triage, fix-review and
  `templates/CLAUDE.md` defer to the session contract's gate rule
  (`test_session_gate_templates_defer_to_the_contract`); a triage session's TRIAGE CONTRACT forbids
  the full gate and carries no RUNNER CONTRACT
  (`test_session_gate_triage_contract_has_its_own_gate_rule`).
- `plan_review_followup` (T214, DONE): a MAJOR plan review on a follow-up batch is revised,
  re-reviewed and implemented with earlier DONE blocks unchanged
  (`test_plan_review_followup_major_revised_rereviewed_and_implemented`); a revision that edits a
  DONE block stops with `Plan revision stage:` and records nothing
  (`test_plan_review_followup_revision_keeps_done_blocks`); a task newly DONE since the base still
  stops the revision (`test_plan_review_followup_newly_done_still_stops`); the queue repair with
  `--base` reorders, without it does nothing (`test_plan_review_followup_queue_repair_with_base`).
- `worker_count` (T202): default and override parsing, `Workers:` first line.
- `session_gate_mode`, `session_gate_setting` (T203, DONE): mode from gate time and setting, errors
  → `targeted 0` (`test_session_gate_mode_from_gate_time_and_setting`); `AI_SESSION_GATE=x` stops
  `ai-run` and `ai-pipeline`, the value is kept in the run manifest
  (`test_session_gate_setting_is_validated_and_kept`).
- `session_gate_contract` and the migrated `session_gate_allowance` (T204, DONE): a slow gate gets
  the targeted rule and no allowance (`test_session_gate_contract_targeted_on_a_slow_gate`); a
  fast gate gets the full rule and the allowance (`test_session_gate_contract_full_on_a_fast_gate`);
  `AI_SESSION_GATE` overrides both ways (`test_session_gate_contract_setting_overrides`); the
  fallback without `Targeted:` lines excludes every full-gate entry point
  (`test_session_gate_contract_fallback_excludes_full_gate_entry_points`); the allowance tests run
  with `AI_SESSION_GATE=full` and the default gives `gate rule targeted`
  (`test_session_gate_allowance_limit_grows_with_the_measured_gate`).
- `session_gate_templates` and `session_gate_triage` (T205) and `session_gate_targeted_lines`
  (T215): templates defer to the contract, the triage prompt carries its own TRIAGE CONTRACT gate
  rule; task format and prompts name `Targeted:`.
- `events_core` (T206, DONE): envelope and run tag (`test_events_core_envelope_and_run_tag`), CLI
  errors (`test_events_core_cli_rejects_unknown_kind_field_type_and_envelope_names`), bounded
  strings (`test_events_core_strings_are_one_bounded_line`), held lock is bounded
  (`test_events_core_held_lock_is_bounded`, `test_events_core_lock_seconds_setting`), tolerant
  reader (`test_events_core_reader_tolerates_unknown_kinds_and_versions`), concurrent appends
  (`test_events_core_concurrent_appends_are_whole_lines`), unwritable state dir
  (`test_events_core_unwritable_state_dir_is_a_note`), no helper after a gate change
  (`test_events_core_gate_broken_runs_no_helper`). `events_redact` (T219, DONE): each secret
  pattern → `[redacted]`, `password=hunter2` → `password=[redacted]`, ordinary text and short ids
  unchanged, a token across the 200th character redacted whole, a CLI `stop message=…` reads back
  redacted (`test_events_redact_tokens`).
- `events_run_context` (T216, DONE): the manifest's 16-hex `run_id`/`started`, new per start, kept
  by `clear-attempts`, wrong types invalid (`test_events_run_context_manifest_id_and_resume`); a
  fixture pipeline's task, review and gate rows carry its id, an inherited `AI_RUN_ID` is ignored,
  a later standalone `ai-run` writes rows without `run` and an event with `run: null`
  (`test_events_run_context_rows_carry_the_run`); two starts on one branch, two ids
  (`test_events_run_context_consecutive_runs_on_one_branch`); a crashed marker of run A
  reconciled under run B logs `run: A`, a marker without `run` a row without it
  (`test_events_run_context_crash_reconciled_in_a_later_run`).
- `events_rotation` (T217, DONE): project A's open run keeps all its lines live while project B's
  ended runs rotate out twice, the first gone for good
  (`test_events_rotation_keeps_every_active_run`); 6 writers with active runs plus filler rotate
  under contention with all 1200 run events kept once, valid JSON lines and no busy Note
  (`test_events_rotation_waiting_writers_lose_nothing`); `AI_EVENTS_MAX_BYTES` parsing, no
  rotation when only active runs fill the file, 8-day-old open run, null-run, unknown-kind and
  torn lines dropped (`test_events_rotation_small_gain_and_stale_runs`); archive already a full
  copy reads each id once, a failing rename leaves both files and no temp while the append
  happens, the next rotation succeeds (`test_events_rotation_crash_between_replaces_duplicates_only`).
- `events_gate` T207 part (DONE): `event-gate` parses unittest OK/FAILED and run_parallel
  `Workers:`/`failing batches:`/`on W workers` logs, truncated log and missing stamp give null
  counts with the event written, bad START/RESULT/GATE_ID exit 2 with nothing written
  (`test_events_gate_parses_the_gate_log`); a FIFO stamp or log, a symlinked log or `.ai/local`,
  an outside log path and an oversized stamp return promptly with null counts, every planted entry
  unchanged (`test_events_gate_unsafe_records_return_promptly`).
- `events_gate_id` / `events_gate_merge` (T222, DONE): `outcome gate pass 12 --id <16 hex>` stores
  `gate_id`, a 15-hex, upper-case, missing or extra `--id` exits 2 with no row, a row without
  `--id` has no `gate_id`, `gate-seconds` is the same with and without ids, `ai_new_id` prints 16
  lowercase hex and differs per call (`test_events_gate_id_on_outcome_rows`); `merge_gates` counts
  complete overlap, partial event loss, rotated-away events, legacy id-less rows, an event-only
  validation gate and a duplicate event once each, the row's seconds win
  (`test_events_gate_merge_counts_each_gate_once`).
- `events_gate_written` / `events_gate_clock` / `events_gate_pipeline` / `events_gate_recovery`
  (T220, DONE): an `ai-run` task gets a `task: T001`, `pass` event with `tests` ≥ 1 beside its
  `outcome gate` row, a failing final gate gives `stage: final`, `fail`
  (`test_events_gate_written_by_the_runner`); the gate-only retry, the checkpoint gate and the
  final gate have epoch starts inside the run and the same `seconds`/`result` as the row with their
  `gate_id`, one event per row (`test_events_gate_clock_is_epoch_and_matches_the_row`);
  `ensure_validated` writes `validation` `pass`, an unwritable event log adds only the Note, a
  failing gate writes `fail` and stops as before (`test_events_gate_pipeline_validation`); the
  recovery gate writes `recovery` `pass` with the checkpoint commit, `fail` and `timeout` with the
  same "fails validation" escalation, and nothing (helper never run) when the gate swapped a gate
  file (`test_events_gate_recovery_gate_outcomes_pass`, `_fail`, `_timeout`, `_changed_gate`).
- `events_stop` (T208, DONE): one last-error text per category, reworded/missing/symlinked →
  `other` (`test_events_stop_category_table`); a failing gate recovered by rerun writes `stop`
  (`validation_failed`, `recovery: yes`) then `recovery` (`rerun`, attempt 1) with the run id
  (`test_events_stop_and_recovery_written_on_a_recovered_stop`); an escalation writes `stop` with
  `recovery: no` and a secret as `[redacted]` (`test_events_stop_on_escalation`); an unwritable
  state dir keeps the notification, last-error and exit status
  (`test_events_stop_unwritable_state_dir_keeps_the_stop`); a gate changed by a hook or during
  recovery runs no event helper and writes no event (`test_events_stop_gate_change_runs_no_event_helper`).
- Later parts: `events_run_end` (T209), `events_lock_held` (T221: pipeline completion,
  terminal stop and escalation bounded with a held lock), `events_ruling` and `events_review`
  (T210), `events_pr` (T218).
- `test_metrics` (T211, T212): fixture logs to exact JSON numbers, attribution by run field,
  runs that survive three rotations (`unknown`, `events 0`, sums agree), gates counted once,
  filters, text tables, `ai-status --metrics`.
- `Docs` and `flow_this_repo` (T213).

## Human todos
- Gate files: none need changing for this batch.
- Before approving: items 1–3 above.
- After merge: the upgrades in item 5; tick TS-01 (1)(2), ME-01 (parts 1 and 2), FL-35/FL-39 and
  CU-1 (verified done in code) in the vault backlog yourself (sessions never tick them).
- Later batches: mission control's display of the events, the weekly `agents-metrics.md` note,
  TS-01 (3) shared fixtures, PR-to-merge time, OR-04.

## Next action
The runner continues with the next task after T208 (the next unblocked task in `.ai/tasks.md`).
Nothing is merged or deployed.
