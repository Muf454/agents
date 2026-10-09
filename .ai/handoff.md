# Handoff

## What has been implemented?
Branch `fix/robustness-batch` (from origin/master c7d4dee): a robustness batch from the
2026-10-07 stop analysis. Queue (see `.ai/tasks.md`):
- T001 FL-14 (opus): review reports may leave out a 0-count severity section, and the verdict may be a `## Overall verdict` heading (`review_verdict` in `scripts/lib/workflow.py`, also used by the PR body; a bold `**Overall verdict:**` line is accepted too). DONE.
- T002 FL-15 (opus): `--base B` prefers `origin/B` when it is ahead, prints the resolved base, and passes the SHA to `ai-review` (diverged: warning, local wins; the PR still targets `B`). DONE.
- T003 FL-17 (opus): the pipeline stops early when the base moved past the branch, after settling an interrupted triage stage or pending re-check. The publish check names the case, and recovery escalates it without Claude, keeping the full message on stderr. DONE.
- T004 FL-16 (sonnet): triage accepts `| M1 (MAJOR) |` (also `(major)` and `M1(MAJOR)`); other decorations still count as no disposition. DONE.

FL-12 (recovery decision after prose) is deferred, not part of this batch: the lenient `recover-decision` parser drew MAJOR plan-review findings in both rounds, so parsing stays exactly as on master. A later batch should use the CLI's structured output (`--json-schema`) instead of a lenient parser.

Plan revision 2 (2026-10-08) addressed Codex plan review round 1 (P1–P4, all accepted). Plan revision 3 (2026-10-08) addresses round 2: P6–P8 accepted, P1 and P5 deferred with FL-12 (see `.ai/reviews/dispositions.md`).

## Flow chart
Flow chart updated (T002, T003; T001 and T004 leave the flow unchanged)

## Manual testing for the human
### Needs you
1. Behaviour change to know about: with T002 and T003, `--base main` in a checkout whose local `main` is behind origin/main reviews against origin/main. If origin/main has moved past your branch, the run now stops at the start with "Review base … moved past the branch; merge it into <branch> and rerun". Before, it reviewed and then failed at the publish check. Merge origin/main into the branch and rerun. If a review triage or re-check was interrupted, the run completes it first against the review it started on and stops only afterwards. Merge only after that stop, never while a triage stage is open, because the triage scope check would reject the merged source.
2. After merge, approve `setup-project --upgrade --apply` for agents, raid-planner and family-planner so their installed copies get the fixes. That includes the template triage prompt line from T004.
3. If `feature/supervisor` (PR #21) merges first, expect small textual conflicts in `scripts/lib/workflow.py`, `scripts/ai-pipeline`, `scripts/ai-recover` and `tests/test_workflow.py` (see `.ai/current-plan.md`).
4. FL-12 stays open: a recovery session that writes prose before its decision still escalates as "gave no valid decision". Keep it in the backlog for a later batch based on `--json-schema` structured output.

### Covered by automated tests
- Missing 0-count section (code and plan review), heading verdict and PR body verdict, empty/missing verdict and count mismatches still rejected with the prior review kept, `ai-review` with a heading-verdict report: `test_review_format_missing_zero_count_sections_are_accepted`, `test_review_format_count_mismatches_are_still_rejected`, `test_review_format_verdict_heading_is_accepted`, `test_review_format_missing_or_empty_verdict_is_rejected`, `test_review_format_verdict_heading_through_ai_review`, `test_review_counts_must_match_listed_findings`, `test_failed_or_malformed_reviews_preserve_report`
- Base resolution (origin ahead with and without a PR, equal, absent, local ahead, diverged, explicit SHA run; explicit `origin/` ref): `test_review_base_origin_ahead_of_local`, `test_review_base_origin_ahead_pr_still_targets_main`, `test_review_base_equal_to_origin`, `test_review_base_without_origin_ref`, `test_review_base_local_ahead_of_origin`, `test_review_base_diverged_uses_local`, `test_review_base_explicit_sha`, `test_pr_base_follows_the_review_base_or_must_be_explicit`
- Base moved past the branch: stop before any agent, recovery escalates without Claude and keeps the full message on stderr, rerun after merge, pending and counted-but-open triage stages and a pending re-check settled before the stop, publish wording via a history-rewriting hook with recovery enabled and disabled: `test_base_moved_stops_before_any_agent`, `test_base_moved_recovery_escalates_without_claude`, `test_base_moved_with_pending_triage_stage`, `test_base_moved_with_counted_open_triage_stage`, `test_base_moved_with_pending_recheck`, `test_base_moved_publish_check_names_the_base`, `test_base_moved_publish_check_without_recovery`
- Severity suffix in disposition rows: `test_triage_severity_suffix_satisfies_triage_check`, `test_triage_severity_suffix_other_decorations_stay_unmatched`, `test_triage_severity_suffix_rejected_row_is_rechecked_and_counted`

## Human todos
None yet (see "Needs you").

## Next action
All tasks DONE; ready for review.
