# Handoff

## What has been implemented?
T001 done (supervision settings: config, validation, manifest, recovery restore; no behaviour yet).
T002 done (host plan-review round records `plan-rounds record|sync|count|current`, `plan-history`;
`ai-review --plan --base`; pipeline and hand runs record once per review). Branch `feature/supervisor`: FL-04 bounded supervisor (see `.ai/project-spec.md`).
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

## Flow chart
Flow unchanged

## Next action
Plan review round 4 of revision 4 (after `fix/catchup-review` merges and this branch is rebuilt
on master, per the plan's Coordination section). No run budget in this batch (OR-09). Start it
with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` so the flow-changing tasks can
update `agents-flow.md` themselves.
