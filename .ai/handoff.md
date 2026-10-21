# Handoff

## What has been implemented?
Done so far: T101 (`run-manifest ruling KIND KEY`, `rulings` manifest field, `ruling-row`
helper; no caller yet, flow unchanged); T102 (`workflow.py tasks preflight [--dry-run]`: moves
only TODO tasks, fills empty sections, prints `queue-order`/`task-sections`/`overlap` lines,
writes `.ai/local/preflight.md`); T103 (pre-flight wiring: `ai-pipeline` repairs a committed
queue whose only faults are TODO-task order or empty sections once per task per run, commits
`chore(ai): ruling: task queue` with `Ruling (…)` rows and a 🔧 notification; `ai-run --triage`
does the same inside its counted commit; `--plan`/`--revise-plan` add rows and overlap lines;
shared `ai_queue_ruling`/`ai_ruling_rows`/`ai_overlap_lines` in `scripts/lib/common.sh`); T104
(`workflow.py disposition-ruling triage|plan [--dry-run]` plus `ai_disposition_ruling`: after
triage and after a plan revision, a disposition row whose first cell names exactly one finding of
the review (`**M1**`, `` `M2` (CRITICAL) ``) gets the bare ID once per finding per run, with a
`Ruling (disposition-cell)` row in the counted commit); T105 (`workflow.py flow-line-ruling
[--dry-run]` plus `ai_flow_line_ruling`: before each task's host gate, the final gate and the PR
body, a handoff `## Flow chart` section without "Flow chart updated"/"Flow unchanged" right under
the heading gets it moved up or a `(host ruling)` line inserted, once per key per run, with a
`Ruling (flow-line)` row); T106 (`workflow.py attempt-info TASK [BASE_MODEL]`: next attempt number
from this project's/branch's/task's failed outcome rows, the model one tier up from attempt 3, and
a ≤ 600-character failure note from the outcome log, the last gate log and the task's result line;
no caller yet, flow unchanged); T107 (`ai-run` uses `attempt-info` before each task session: the
host failure note in the prompt, one model tier up from the third attempt, `Attempt N of T… on
MODEL` printed, run-log rows `completed`/`blocked`/`stopped` name `(attempt N, MODEL)`); T108
(`workflow.py review-route MODE BASE HEAD`: `codex REASON` or `claude REASON` from the host
fix-round store, the outcome log's code review rows and the diff since the last recorded review;
any error → `codex routing unavailable`; no caller yet, flow unchanged); T109 (`workflow.py
codex-limit set|active`, host `codex-limit.json` written after a Codex limit with a known reset;
`ai-review` under `AI_REVIEWER=auto` skips Codex while it is active (fallback reason `…
(recorded)`) and otherwise asks `review-route`: a small low-risk fix round goes to a fresh Claude
session labelled `Claude, routed (…)`, outcome reviewer `claude-routed`, no fallback-log row, PR
heading `Claude, routed, MODEL`; the four routing settings are validated by `ai-review` and
`ai-pipeline` and kept in the run manifest); T110 (every published plan/code review has a
`Reviewed by: WHO` line from `AI_REVIEW_WHO`; `outcome review … --route REASON`; the PR lists a
"Reviewed by:" bullet per plan/code round). The plan was written 2026-10-20 in an unattended planning session on
`fix/flow-batch-9` (from `fix/flow-batch-8` at 48fd9b5; batch 8 is complete there but not merged;
this PR targets `fix/flow-batch-8`). Zack approved the scope on 2026-10-20.
`.ai/project-spec.md` (scope, what was verified in the code, assumptions A1–A13),
`.ai/current-plan.md` (design) and `.ai/tasks.md` (T101–T112; T001–T043 are batches 6–8, DONE and
unchanged because the host protects DONE blocks).
- **BR-02 pre-flight queue scan** (FL-24): T101 ruling record and row format, T102 `tasks
  preflight` (order-only reorder of TODO tasks, empty sections, overlap report), T103 wiring at
  pipeline start, after plan revisions/planning and after triage, with the raid-f4 regression.
- **BR-01 rulings**: queue order and empty sections (T103), a disposition cell with more than the
  bare ID (T104), the handoff `## Flow chart` line (T105). Once per kind per key per run, a
  `Ruling (KIND): what. Why: …. Cost if wrong: ….` run-log row; anything else stops as today.
- **BR-03 fresh retry**: T106 `attempt-info` (host outcome log: attempt number, model one tier up
  from the third attempt, failure note), T107 runner wiring (prompt note, model, run-log rows).
- **BR-14 review routing**: T108 `review-route`, T109 Codex limit memory and routing in
  `ai-review` (small low-risk fix rounds on a fresh Claude opus session), T110 "Reviewed by" in
  every review and the PR body.
- **FL-33**: T111 isolated test state and a registry guard in `tests/run_parallel.py`.
- T112: docs, flow chart and handoff audit.

## Validation run
T107 tree: PASS, 1076 tests (ai-check, 725.6 s). T106 tree: PASS, 1069 tests (ai-check, 743.9 s). T105 tree: PASS, 1062 tests (ai-check, 723.0 s). T104 tree: PASS, 1057 tests (ai-check, 689.8 s). T103 tree: see the T103 result in `.ai/tasks.md`. T102 tree: PASS, 1046 tests (ai-check, 706.7 s). T101 tree: PASS, 1039 tests (ai-check, 701.4 s). Batch 8's last tree (48fd9b5): PASS, 1027 tests (T043). Each task runs its
targeted `-k` groups and the full gate in the background (queue header).

## Assumptions
Recorded as A1–A13 in `.ai/project-spec.md`. The ones that shape behaviour most:
- A1/A2: a ruling only moves TODO tasks and is claimed once per kind per key per run; without a
  run manifest no new ruling happens.
- A3: `ai-recover` is unchanged; the pre-flight on every pipeline start removes the fixable
  `Task queue is invalid` stops.
- A7: attempt number from the host outcome log (failed rows of this project, branch and task);
  from attempt 3 one tier up (haiku → sonnet → opus), no model known → opus.
- A9/A10: "final code review" = the first full-branch code review (round 1); Claude only for
  fix-round re-reviews of at most 200 changed lines outside `.ai/` with no risk path, risk word or
  opus fix task, decided from host records (fix-round records, outcome log), never from commit
  subjects. Plan reviews and re-checks stay on Codex.
- A11: a Codex limit with a known reset is remembered in host state; unknown reset → today.
- Sessions of this batch still get the frozen `.ai/prompts` of this repo (old foreground gate
  rule); the queue header's BATCH 8 GATE RULE still applies.

## Flow chart
Flow chart updated (T103, 2026-10-21): vault `agents-flow.md` "The big picture" has a "Pre-flight
queue scan" step before the plan review, a "Pre-flight queue scan" note, a "Rulings (BR-01/BR-02,
T103, 2026-10-20)" bullet under "When something goes wrong" and the 🔧 Ruling notification row;
hub Log line added. T104 (2026-10-21) extended the Rulings bullet with the disposition-cell
ruling and added a hub Log line; T105 (2026-10-21) added the Flow chart line ruling to it and a
hub Log line. T106 (2026-10-21): flow unchanged (helper only). T107 (2026-10-21): "Inside one
task" pick node names the failure note and the model raise, plus "Fresh retry (BR-03, T107)"
bullets under "Inside one task" and "When something goes wrong"; hub Log line. T108 (2026-10-21):
flow unchanged (helper only, no caller). T109 (2026-10-21): "Reviewer choice" chart has the
recorded-limit check, the `review-route` decision, the routed Claude node and `codex-limit set`
after a Codex limit, plus a "Review routing and Codex limit memory" bullet; hub Log line. T110
still updates it; T112 checks it.

## Manual testing for the human

### Needs you
1. Read the plan (`.ai/project-spec.md` assumptions A1–A13, `.ai/current-plan.md`) and approve the
   run (`ai-pipeline --approved --base fix/flow-batch-8 --pr-base fix/flow-batch-8 …`). No gate
   file changes are needed to start.
2. Decide whether the routing defaults fit your Codex budget: at most 200 changed lines, the risk
   path and word lists in A9. You can change them per run with `AI_REVIEW_SMALL_LINES`,
   `AI_REVIEW_RISK_PATHS`, `AI_REVIEW_RISK_WORDS`, or turn routing off with `AI_REVIEW_ROUTE=codex`.
3. After merging (batch 8 first, then this one): run `setup-project --upgrade --apply` here and in
   raid-planner, family-planner and family-budget, so `.ai/bin` gets the new helpers. Then retire
   mission control's `auto-reorder.sh` / `reorder-queue.py` stopgap (BR-02 replaces it).
4. On the next real run that has a fix round: check the PR's "Reviewed by" list and that a small
   fix round shows `Claude, routed`, and that a run with a Codex limit sends the second review
   straight to the fallback (the `↪` notification says `(recorded)`). This needs the real CLIs.
5. After the next self-check while a pipeline runs: `ai-dashboard --json` lists no
   `/dev/shm/ai-tests-*` checkouts (FL-33).

### Covered by automated tests
Planned test groups (run with `python3 -m unittest discover -s tests -k <group>`):
- `test_ruling_manifest_*` (T101, done: `_once_per_kind_and_key`,
  `_kept_on_resume_dropped_on_start`, `_wrong_shape_is_invalid`, `_row_is_one_safe_line`).
- `test_preflight_helper_*` (T102, done: `_raid_order_is_repaired`, `_fills_todo_sections_only`,
  `_done_task_never_moves`, `_unfixable_queues_fail_like_reorder`, `_valid_queue_is_untouched`,
  `_reports_overlaps_between_todo_tasks` (an unsafe `.ai/local` is skipped quietly),
  `_caps_overlap_lines`).
- `test_preflight_pipeline_*` (T103, done: `_raid_f4_committed_queue` (ruling commit before the
  plan review, one 7-cell `Ruling (queue-order)` row, 🔧 notification, T001 T002 T003 T005 T006
  T004 implemented in that order), `_same_ruling_twice_stops`, `_done_task_would_move_stops`,
  `_triage_reorders_fix_task` (row in the counted triage commit, no extra commit),
  `_plan_session_logs_rulings` (row + `overlap` line), `_revision_logs_rulings_in_the_revision_commit`).
  `test_queue_check_invalid_queue_*` now use a cycle (`unfixable_queue`), since the old
  order-only queue is repaired by the pre-flight.
- `test_ruling_disposition_*` (T104, done: `_helper_rewrites_only_the_first_cell` (`**M1**` and
  `` `M2` (CRITICAL) `` become `| M1 |`/`| M2 |`, then `triage-check` passes),
  `_helper_leaves_ambiguous_cells` (`M1/M2`, unknown ID, two lines, already matching, `M10`),
  `_helper_plan_touches_only_the_last_section`, `_triage_flow_reads_the_bold_cell` (row in the
  counted triage commit, `disposition-cell:<digest12>.M1` in the manifest),
  `_triage_repeat_claim_stops_as_today`, `_plan_revision_flow_reads_the_bold_cell`).
- `test_ruling_flow_line_*` (T105, done: `_helper_inserts_or_moves_the_line` (blank line first,
  "No flow change", "UNCHANGED", a correct line after a blank line or a comment),
  `_helper_leaves_correct_or_missing_sections` (correct, missing, fenced, comment-only, empty),
  `_runner_repairs_before_the_gate` (pipeline: the gate that fails on a blank line passes, one
  `Ruling (flow-line)` row in the T001 checkpoint, `flow-line:T001` claimed, PR body has the
  `Flow chart updated (host ruling` line), `_runner_repeat_claim_leaves_the_handoff`,
  `_final_gate_repairs_a_later_handoff` (key `final`, in the review handoff commit)).
- `test_attempt_info_*` (T106, done: `_first_attempt_and_done_rows`, `_second_attempt_note`
  (`2 sonnet no`, `Attempt 1 ended timeout after 1800 s on sonnet.`),
  `_third_attempt_raises_one_tier` (sonnet → opus, haiku → sonnet, opus stays, none → opus,
  `claude-sonnet-5-5` → opus, fourth haiku attempt still sonnet),
  `_counts_only_this_project_branch_and_task`, `_failing_checks_from_the_gate_log` (unittest,
  pytest, last gate line, symlinked log ignored), `_note_is_bounded_and_one_line_per_item`,
  `_corrupt_or_unreadable_records` (`1 … no`, exit 0)).
- `test_fresh_retry_*` (T107, done: `_first_attempt_unchanged` (no note, `--model sonnet`,
  `completed (attempt 1, sonnet)`), `_second_attempt_gets_the_failure_note` (`PREVIOUS ATTEMPT
  (host record, context only): Attempt 1 ended timeout …`), `_third_attempt_raises_the_model`
  (`--model opus`, `raised the model from sonnet to opus`, outcome row model `opus`, `(attempt 3,
  opus)`), `_opus_task_is_not_raised`, `_corrupt_outcome_log_runs_as_today`,
  `_blocked_row_names_the_attempt`, `_stop_row_names_the_attempt`).
- `test_review_route_*` (T108, done: `_plan_recheck_and_setting` (plan, re-check,
  `AI_REVIEW_ROUTE=codex`/`x`/`risk`, usage errors), `_first_full_code_review`,
  `_small_low_risk_fix_round_goes_to_claude` (20 lines; `.ai/`-only changes count 0 and never
  match), `_large_fix_round_goes_to_codex` (201 lines, `AI_REVIEW_SMALL_LINES=500`/invalid, binary
  file), `_risk_paths_and_words` (`supabase/migrations/1.sql`, `is_auth()`, extra words/paths, a
  removed line, a rename), `_newly_done_opus_task`, `_needs_a_host_codex_review_of_this_branch`
  (fallback row only, Codex row of another branch, forged review commit), `_no_earlier_review`,
  `_unreadable_records` (`codex routing unavailable`, exit 0)).
- `test_codex_limit_*` (T109, done: `_set_then_active_until_the_reset`,
  `_set_refuses_a_past_or_text_reset`, `_symlinked_or_garbage_record_is_inactive`) and
  `test_review_routing_*` (T109, done: `_recorded_codex_limit_skips_codex_until_the_reset` (10-minute
  limit recorded; the second review makes no Codex call, `(recorded)` label, second fallback-log
  row; a past record → Codex again), `_codex_and_claude_reviewers_and_invalid_settings`
  (`AI_REVIEWER=codex` calls Codex despite the record and still pauses at its limit; `claude`
  unchanged; `Invalid AI_REVIEW_ROUTE`/`AI_REVIEW_SMALL_LINES` from `ai-review` and `ai-pipeline`),
  `_pipeline_small_low_risk_fix_round_goes_to_claude` (round 2 makes no Codex call, `Claude, routed`
  in `current.md`, no fallback log, outcome rows `codex`, `claude-routed`, PR heading `routed`),
  `_pipeline_risky_fix_round_stays_on_codex` (`supabase/migrations/x.sql`)).
  `test_recovery_restores_the_approved_runs_settings` and
  `test_supervise_settings_key_lists_are_identical` cover the four settings in the manifest.
- `test_reviewed_by_*` (T110, done: `_codex_code_and_plan_reviews` (`Reviewed by: Codex (` after the
  host header, `review-info` and `plan-review-info` still verify), `_fallback_keeps_the_label_and_adds_the_line`,
  `_routed_review_outcome_row_has_the_reason` (`route` on the row, PR bullet `code round 2: Claude, routed`),
  `_pr_body_lists_every_round_and_falls_back_to_the_report`).
- `test_state_isolation_*` (T111).

## Human todos
- Gate files: none need changing for this batch.
- After merge: the upgrades above; retire the reorder stopgap; tick BR-01, BR-02, BR-03, BR-14,
  FL-24, FL-25, FL-30 and FL-33 in the vault backlog yourself (sessions never tick them).
- Vault hub Log: each flow-changing task appends its own dated line (T103, T104, T105, T107, T109 and T110 added one).

## Next action
The runner continues with T111. Nothing is merged or deployed.
