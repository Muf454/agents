# Handoff

## What has been implemented?
T001 (2026-10-09): `scripts/lib/workflow.py` safe record I/O (pinned no-follow directory
descriptors, bounded nonblocking reads incl. tail mode, bounded flock, temp + rename writes,
`git_branch` without git) and the writers `observe`, `notify-log`, `pipeline-register`
(always exit 0, warning on failure), plus `tasks counts`. No caller yet (T002–T005).
Tests in `tests/test_observation.py`. Also: the `tests/test_workflow.py` fixture now drops
the `AI_SUPERVISE_*` limits a supervised pipeline exports (they leaked into two tests).
T010 (2026-10-09): gate-broken guard in `scripts/lib/common.sh` (`ai_gate_check`,
`AI_GATE_BROKEN` set by every gate comparison incl. `ai_guard_verify` and `ai_deps`; record
helpers `ai_observe` and `ai_notify_log` skip themselves once it is set; no callers until
T002). ai-run `on_exit`, ai-pipeline `stop()` and its approval/resume gate stops, and every
ai-recover comparison set it; ai-run's EXIT handler also no longer writes the plan-revision
outcome line after a gate change. Messages and exit codes unchanged.

Plan: Branch `feature/dashboard` (master e9354d9 merged in) plans the pipeline
dashboard Zack asked for on 2026-10-07: safe record writers and readers (T001), the
gate-broken guard (T010, runs second), stage writers in common.sh (T002), ai-pipeline (T003),
ai-run/`ai_deps`/ai-review (T004) and ai-recover (T005), discovery and liveness (T006), a
read-only snapshot of all pipelines (T007), a curses TUI showing the flow as eight boxes with
the active stage highlighted (T008), docs (T009). Revised after Codex plan review 1 (P1–P10),
2 (P11–P18) 3 (P19–P22) 4 (P23–P25) 5 (P26–P27) 6 (P28–P29) and 7 (P30–P31), all accepted;
round 8 clean. Revision 9 (2026-10-09) rebases it on master e9354d9 (FL-04 supervisor,
FL-14–17): Plan revision box, stored decision, extra fix round, format retry, base-moved
stop, box layout from 120 columns. Revision 10 (2026-10-09, plan review 9 by the Claude
fallback reviewer, P32–P38 all accepted): no project helper runs after the approved gate
changed (T010), deterministic `/proc` discovery in tests, Build recorded again after the
post-task gate, plus four minor record details. Revision 11 (2026-10-09, plan review 10 by
the Claude fallback reviewer, P39–P45 all accepted): T005's gate test made possible (no
sentinel in `workflow.py`; ai-recover runs the checkout helper before it compares the gate),
the flag also on the pipeline's pre-step gate stops and never in a command substitution,
the watchdog note corrected, `done` → `stage=pr`, a `needs_you` run with an active record
renders as stopped, `tasks counts`; see the top of `.ai/current-plan.md`. See also
`.ai/project-spec.md`, `.ai/tasks.md`.

## Validation run
2026-10-09 after T010: `.ai/bin/ai-check` OK (440 tests, 8 shards); targeted
`-k observation_gate`: 6 OK, `-k gate_changes`: 2 OK, `-k observation_writer` (T001): 23 OK.

## Assumptions
- Finished/stopped/idle runs older than 24 h are hidden by default (`--all` shows them).
- The dashboard is advisory and read-only; `.ai/local/` records are agent-writable.
- Eight boxes need up to 112 columns, so the box layout starts at 120 columns (compact
  line below); the plan revision box label is "Plan revision" ("Revise" in the compact line).
- A stop caused by a changed gate records no observation (the record helpers are project
  code); the dashboard still shows `needs_you` from `last-error` and draws the last recorded
  box as stopped with that line. The watchdog notifies through its own installed copy and
  needs no guard.
- `AI_DASHBOARD_PROC` and `AI_DASHBOARD_ROOT` are test-only; the dashboard must run with the
  same `AI_STATE_DIR`/XDG settings as the pipelines.

## Flow chart
Flow chart updated: PENDING (T002/T003 will add a note under "Phone notifications" in the
vault `agents-flow.md`: notifications mirrored to `.ai/local/notifications.log`, stages
recorded in `.ai/local/observation.json`, for `ai-dashboard`; the flow itself is unchanged).
Not done yet.

## Manual testing for the human

### Needs you
1. Filled in by T009.

### Covered by automated tests
- Observation record actions, schema, pause/resume, `detail`, `done`, `pid`/`branch`:
  `test_observation_writer_actions_and_schema`, `test_observation_writer_detail_only_on_recorded_stage`,
  `test_observation_writer_done_records_pr`, `test_observation_writer_pid_and_branch`.
- Stop label → box mapping and recovery stage: `test_observation_writer_stop_labels`,
  `test_observation_writer_recovering`.
- Symlink, swapped-directory, hard-link, FIFO and held-lock safety (exit 0, warning, outside
  files unchanged, bounded time): `test_observation_writer_refuses_symlinked_directories`,
  `test_observation_writer_replaces_symlinked_record`, `test_observation_writer_preplanted_temp_symlink`,
  `test_observation_writer_local_swapped_after_validation`, `test_observation_writer_hard_links_untouched`,
  `test_observation_writer_fifos_and_held_locks_return`, `test_observation_writer_notify_log_symlinks`.
- Bounded readers and Git metadata: `test_observation_writer_read_record_bounds`,
  `test_observation_writer_read_record_tail`, `test_observation_writer_git_branch`,
  `test_observation_writer_checkout_fds`.
- Notification log trimming and concurrency: `test_observation_writer_notify_log_keeps_last_200`,
  `test_observation_writer_notify_log_concurrent`.
- Host registry: `test_observation_writer_pipeline_register`,
  `test_observation_writer_pipeline_register_keeps_replaced_entry`,
  `test_observation_writer_pipeline_register_unusable_directory`.
- `tasks counts`: `test_observation_writer_tasks_counts`.
- No project helper after a changed gate: `test_observation_gate_flag_skips_record_helpers`,
  `test_observation_gate_check_sets_flag_on_changed_or_unreadable_gate`,
  `test_observation_gate_ok_form_sets_flag_in_calling_shell`,
  `test_observation_gate_pipeline_resume_gate_stop_unchanged`,
  `test_observation_gate_deps_installer_changing_gate_sets_flag`,
  `test_observation_gate_runner_tamper_stop_runs_no_helper`, and the existing
  `test_runner_detects_even_committed_gate_changes_before_untrusted_helpers`.

## Human todos
None yet (T009 adds the optional PATH symlink and the `.ai/bin` upgrade of projects).

## Next action
T001 and T010 done; next T002 (notification mirror and pause overlay).
