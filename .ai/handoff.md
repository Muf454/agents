# Handoff

## What has been implemented?
T001 done (supervision settings: config, validation, manifest, recovery restore; no behaviour yet).
T002 done (host plan-review round records `plan-rounds record|sync|count|current`, `plan-history`;
`ai-review --plan --base`; pipeline and hand runs record once per review).
T003 done (`start-plan-dispositions BASE`, `plan-dispositions-check --since START --base BASE
[--fresh] [--questions]`, `plan-revision-scope START`; T004 passes `--base`).
T004 done (`ai-run --revise-plan [--since] [--base]`: Read/Glob/Grep/Edit-only session on the new
`plan-revision.md` prompt, host commit `chore(ai): record plan revision` with its run-log line,
host record `plan-revisions record`, `plan-revisions revised|decision`; no pipeline caller yet).
T005 done (host `plan-revision` stage bound to the plan report, `run-manifest revision-reserve|revision-count`,
`complete_plan_stage` in `ai-pipeline` with the round's model, recovery: stored needs-human decision
escalates before the attempt limit and any resume, new always-escalate reasons, plan-revision
leftovers checked with `plan-revision-scope`).
T006 done (supervised plan-review loop in `ai-pipeline`: decision check at every pass, revision
reserved then staged, `🔁 Plan revised (round n/N)` notification, re-review with `PLAN REVISION
CONTEXT:` and `plan-history --include-current`; limit/needs-human/out-of-scope stops; plan report
header now names HEAD; `plan-revisions outcome`).
T007 done (crash/resume scenarios for every plan-revision crash point, by human rerun and by
watchdog recovery; fixes: `ai-run` resumes a host section left uncommitted by a crash
(`start-plan-dispositions --pending`), `ai-recover` closes a committed plan-revision stage when it
escalates a stored decision, the notification after a restart closed the previous run's revision
reads "(in the previous run)").
T008 done (extra fix round: `fix-rounds record` stores the triaged review's head, digest and
BLOCKER/MAJOR counts, legacy bare hashes still read; `fix-rounds trend BASE`; `run-manifest
extra-round-reserve|extra-round`; `ai-pipeline` gives one extra round per supervised run at the
limit when x > y > z, notifies `🔁 Extra fix round: findings falling (x → y → z)`).
T009 done (review format retry: `review-format-check plan|code REPORT` shares the publish
checks; supervised `ai-review --plan`/code reviews ask the reviewer once more on a format error
or empty answer, `🔁 Review format retry (<mode>): <error>`, run-log line committed with the
review; integrity failures and re-checks never retried; per-call reviewer metadata reset).

Branch `feature/supervisor`: FL-04 bounded supervisor (see `.ai/project-spec.md`).
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
1. One real supervised run with live Claude and Codex on a throwaway project (not this repo).
   Steps: install the toolkit there with `setup-project`, configure `.ai/validate`, write a small
   plan with one deliberately vague task, commit it on a feature branch, then run
   `.ai/bin/ai-pipeline --approved --base main` in tmux.
   Expected: a BLOCKER/MAJOR plan finding gives `🔁 Plan revised (round 1/3)` on the phone and a
   new Codex plan review on a clean checkout; the run continues to implementation once a review is
   clean. If Claude asks you a question, the run stops with `⛔ plan review needs your decision`
   and the question text; nothing is implemented.
   Then: (a) run `ai-recover` (or `ai-watchdog --recover` after a kill) on that stop; expected: no
   Claude session, the stop stays and names the question; (b) answer the question in
   `.ai/reviews/plan-dispositions.md`, commit, run `ai-review --plan --base main` by hand, then
   rerun `ai-pipeline`; expected: the plan review is clean and the run goes on to the first task.
   Set `AI_SUPERVISE=0` in the environment for one rerun; expected: the old stop, no revision.
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
- T005 plan-revision stage: pending/committed/dirty/foreign report/out of scope/agent commit
  `test_plan_revision_stage_set_and_verify`; reservation idempotent, limit, reset by start, kept
  on resume `test_plan_revision_stage_reservation_per_run`; committed stage only cleared
  `test_plan_revision_stage_committed_record_only_clears_the_stage`; model by round (opus, then
  the escalation model; not the run's `--model`) `test_plan_revision_stage_pending_runs_the_round_model`;
  limit stop without a session `test_plan_revision_stage_limit_stops_before_the_session`; new
  reasons escalate without Claude `test_plan_revision_stage_recovery_reasons_always_escalate`;
  source leftovers escalate, nothing committed
  `test_plan_revision_stage_source_leftovers_escalate_without_a_commit`; stored needs-human
  decision after a crash escalates with its questions, also with the allowance used up
  `test_plan_revision_stage_stored_decision_escalates_before_any_resume`.
- T006 supervised loop: MAJOR → revision → clean re-review → implementation → PR, notification and
  run-log line in the revision commit `test_supervised_plan_major_once_revises_reviews_again_and_opens_the_pr`;
  reject-only revision re-reviewed before implementation with `PLAN REVISION CONTEXT:`
  `test_supervised_plan_reject_only_reviews_again_on_a_clean_checkout`; needs-human stop with the
  bounded question, no re-review/implementation, rerun with auto-recovery runs no session
  `test_supervised_plan_needs_human_stops_with_the_bounded_question`; limit
  `test_supervised_plan_limit_stops_without_recovery`; `AI_SUPERVISE=0`
  `test_supervised_plan_off_keeps_todays_stop`; revision touching source
  `test_supervised_plan_revision_touching_source_stops_without_recovery`; opus, opus, escalation
  model and round 3 Convergence `test_supervised_plan_escalation_model_and_round_three_convergence`.
- T007 crash and resume (each by a human rerun and by `ai-recover` after a crash: one revision
  record, one session, one clean re-review, then implementation): during the session's edits
  `test_supervised_plan_resume_session_crash_human_rerun`/`_watchdog`; before/after the host's
  preamble commit `test_supervised_plan_resume_before_the_preamble_commit_*`,
  `test_supervised_plan_resume_after_the_preamble_commit_*`; before/after the revision commit
  `test_supervised_plan_resume_before_the_revision_commit_*`,
  `test_supervised_plan_resume_after_the_revision_commit_*`; after the record and after
  stage-clear `test_supervised_plan_resume_after_the_record_*`,
  `test_supervised_plan_resume_after_stage_clear_*`; reservation without stage (limit 1)
  `test_supervised_plan_resume_reserved_without_a_stage_*`; stage without reservation
  `test_supervised_plan_resume_stage_without_a_reservation_*`; plan review committed without its
  round record `test_supervised_plan_resume_plan_review_without_its_round_record_*`; round-3 crash
  resumes on the escalation model with Convergence
  `test_supervised_plan_resume_round_three_crash_runs_on_the_escalation_model`; approved settings
  after a config change `test_supervised_plan_resume_keeps_the_approved_settings_after_a_config_change`;
  needs-human decision survives (no reviewer, revision, implementation or recovery session; the
  answer + hand `ai-review --plan` continues) `test_supervised_plan_resume_decision_after_*`;
  restart after the limit reviews first `test_supervised_plan_resume_human_restart_after_the_limit_reviews_first`;
  host header pending check `test_plan_dispositions_pending_accepts_only_the_host_header`;
  simulated crashes never kill a process outside the test fixture (the host runner)
  `test_supervised_plan_resume_crash_kill_stays_inside_the_fixture`.
- T008 extra fix round: falling 4 → 3 → 2 with `--max-fix-rounds 2` gets one extra round,
  notification, run-log line in the triage commit, then draft at the next limit although still
  falling `test_extra_fix_round_falling_counts_get_one_round_then_draft`; clean review after it →
  ready PR `test_extra_fix_round_clean_review_after_it_opens_a_ready_pr`; flat counts with agent
  commits imitating the triage subject `test_extra_fix_round_flat_counts_and_imitated_subjects_draft`;
  rising `test_extra_fix_round_rising_counts_draft`; `AI_SUPERVISE=0`
  `test_extra_fix_round_unsupervised_draft`; legacy round 1 + counted 2–3 boundary, only round 3
  counted, legacy record between/last, same review as the last round, unreachable record,
  another branch `test_extra_fix_round_trend_history_boundaries`; reservation once per run, reset
  by a restart `test_extra_fix_round_reservation_once_per_run`; crash right after the
  reservation resumes into that round once `test_extra_fix_round_crash_after_reservation_resumes_it_once`.
- T009 format retry: Codex code review malformed/empty/counts-lie then valid → published with 2
  calls, notification, `FORMAT ERROR:` prompt, first report kept and named in the run log;
  malformed or empty twice → stop, prior review kept; valid → 1 call; `mutates` and Codex error →
  no retry; malformed then a mutating or failing retry → stop, logged
  `test_format_retry_code_review_once_then_publish_or_stop`; the same for a hand-run plan review
  (clean checkout for both calls, run-log line in the record commit)
  `test_format_retry_plan_review_by_hand`; Claude fallback malformed/empty then valid, empty or
  malformed twice, plan on the fallback `test_format_retry_claude_fallback_reviewer`; malformed
  Claude fallback then Codex retry saved, logged and attributed as Codex
  `test_format_retry_after_claude_fallback_attributes_the_codex_review`; pipeline commits each
  retry's run-log line with the plan and code review records, checkout clean
  `test_format_retry_pipeline_commits_the_run_log_line_with_each_review`; malformed re-check →
  one call, upheld `test_format_retry_never_for_a_malformed_recheck`; `AI_SUPERVISE=0` → no retry
  `test_format_retry_off_without_supervision`; helper = publish checks
  `test_review_format_check_helper_matches_publish`.
- T010 docs: README and `docs/workflow.md` wording guarded by `test_docs_consistency_no_wrong_sentences`,
  `test_docs_consistency_required_sentences`, `test_docs_consistency_modes_table`; this handoff's flow
  line and PR body by `test_pr_body_flow_this_repo_declares_the_flow_chart`.

## Human todos
None beyond "Needs you" above.

## Flow chart
Flow chart updated

## Next action
All ten tasks (T001–T010) are DONE with the gate passing (see `.ai/run-log.md`). Next: an independent
Codex review of the branch, then the live supervised trial in "Needs you" above. No run budget in
this batch (OR-09).
