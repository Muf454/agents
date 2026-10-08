# Handoff

## What has been implemented?
T001 done (supervision settings: config, validation, manifest, recovery restore; no behaviour yet).
T002 done (host plan-review round records `plan-rounds record|sync|count|current`, `plan-history`;
`ai-review --plan --base`; pipeline and hand runs record once per review).
T003 done (`start-plan-dispositions BASE`, `plan-dispositions-check --since START --base BASE
[--fresh] [--questions]`, `plan-revision-scope START`; T004 passes `--base`).
T004 done (`ai-run --revise-plan [--since] [--base]`: Read/Glob/Grep/Edit-only session on the new
`plan-revision.md` prompt, host commit `chore(ai): record plan revision` with its run-log line,
host record `plan-revisions record`, `plan-revisions revised|decision`; no pipeline caller yet). Branch `feature/supervisor`: FL-04 bounded supervisor (see `.ai/project-spec.md`).
Plan revision 2 answers plan review round 1 (HEAD cc8c464; 10 MAJOR + 1 MINOR accepted, see
`.ai/reviews/dispositions.md` → "Plan review round 1"). Plan revision 3 answers plan review
round 2 (HEAD dfc03c8; 1 MAJOR + 7 MINOR accepted, see "Plan review round 2"). Plan revision 4
answers plan review round 3 (HEAD dbe85f5; 1 BLOCKER + 4 MAJOR + 2 MINOR, see "Plan review
round 3"): the shared run budget is removed from this batch (mission control's convergence
decision; OR-09 keeps Zack's 16 h + 12 h cumulative budget), supervision is bounded by counts plus
the per-call timeouts; the revision's run-log entry is committed in its host commit (clean
re-review); the needs-human outcome is stored in the host revision record before the stage
closes and checked by the pipeline and `ai-recover`. 10 tasks T001–T010.

## Manual testing for the human
### Needs you
1. One real supervised run on a small plan, including a needs-human stop, a recovery attempt on
   it and clearing it with a hand-run `ai-review --plan` (filled in by T010).
2. This repo's frozen `.ai/prompts` has no `plan-revision.md` yet: run `setup-project --upgrade`
   on this checkout before using `ai-run --revise-plan` here (it stops naming that command).
   Mission control: a live `ai-run --revise-plan` with real Claude in a disposable fixture, checking
   that the session can Edit the plan records and nothing else (T004 notes).

### Covered by automated tests
- T001 settings: invalid values stop before any agent `test_supervise_settings_invalid_values_stop_before_any_agent`,
  `test_supervise_settings_invalid_supervise_stops_hand_run_tools`; manifest capture and resume
  `test_supervise_settings_are_captured_and_survive_a_config_change`; key lists
  `test_supervise_settings_key_lists_are_identical`.
- T002 plan rounds: history pairing `test_plan_rounds_history_pairs_findings_with_dispositions`,
  `test_plan_history_marks_rounds_without_a_revision`; forged/agent commits
  `test_plan_rounds_ignore_agent_commits_and_tampered_reports`; pipeline + hand run
  `test_plan_rounds_pipeline_and_hand_run_record_once_per_review`; recreated branch
  `test_plan_rounds_restart_when_a_branch_name_is_recreated`; crash sync
  `test_plan_rounds_sync_records_a_crashed_review_once`, `test_plan_rounds_sync_ignores_a_forged_report`.
- T003 plan-dispositions section: complete section, resume and START-with-header
  `test_plan_dispositions_complete_section_passes_and_counts`; MINOR optional, round 2 without
  Convergence `test_plan_dispositions_minor_rows_optional_and_round_two_needs_no_convergence`;
  adversarial rows/tasks/preamble/headers `test_plan_dispositions_reject_adversarial_sections`;
  older sections never count `test_plan_dispositions_check_only_the_current_round`,
  `test_plan_dispositions_round_three_needs_its_own_convergence_line`; bounded questions
  `test_plan_dispositions_questions_are_bounded`; scope `test_plan_dispositions_revision_scope`.
- T004 `ai-run --revise-plan`: one host commit + record, clean checkout, run-log line in the
  commit, session tools/allowlist, "already revised" refusal, hand re-review starts
  `test_revise_plan_accept_commits_once_and_leaves_a_clean_checkout`; reject-only scope
  `test_revise_plan_reject_only_changes_only_the_dispositions`; needs-human record, bounded
  questions, decision 0/1/2 and clearing by a new report `test_revise_plan_needs_human_record_and_decision`;
  initial state `test_revise_plan_forged_report_without_a_decision_takes_the_normal_path`; out of
  bounds `test_revise_plan_touching_source_stops_with_nothing_counted`,
  `test_revise_plan_editing_the_plan_review_stops_with_nothing_counted`,
  `test_revise_plan_touching_a_gate_file_stops_with_nothing_counted`; resume without a session
  `test_revise_plan_resumes_an_uncommitted_complete_section_without_a_session`; exclusivity,
  missing prompt, round 3 Convergence `test_revise_plan_preconditions_and_round_three_contract`.

## Flow chart
Flow unchanged

## Next action
Plan review round 4 of revision 4 (after `fix/catchup-review` merges and this branch is rebuilt
on master, per the plan's Coordination section). No run budget in this batch (OR-09). Start it
with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` so the flow-changing tasks can
update `agents-flow.md` themselves.
