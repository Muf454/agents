# Handoff

## What has been implemented?
Branch `fix/robustness-batch` (from origin/master c7d4dee): a robustness batch from the
2026-10-07 stop analysis. Only the plan exists so far. Queue (see `.ai/tasks.md`):
- T001 FL-14 (opus): review reports may leave out a 0-count severity section, and the verdict may be a `## Overall verdict` heading. TODO.
- T002 FL-15 (opus): `--base B` prefers `origin/B` when it is ahead, prints the resolved base, and passes the SHA to `ai-review`. TODO.
- T003 FL-17 (opus): the pipeline stops early when the base moved past the branch, the publish check names the case, and recovery escalates it without Claude. TODO.
- T004 FL-16 (sonnet): triage accepts `| M1 (MAJOR) |`. TODO.
- T005 FL-12 (sonnet): the recovery decision may follow prose (still exactly one decision). TODO.

## Flow chart
Flow chart updated (T002, T003; T001, T004 and T005 leave the flow unchanged)

## Manual testing for the human
### Needs you
1. Behaviour change to know about: with T002 and T003, `--base main` in a checkout whose local `main` is behind origin/main reviews against origin/main. If origin/main has moved past your branch, the run now stops at the start with "Review base … moved past the branch; merge it into <branch> and rerun". Before, it reviewed and then failed at the publish check. Merge origin/main into the branch and rerun.
2. After merge, approve `setup-project --upgrade --apply` for agents, raid-planner and family-planner so their installed copies get the fixes. That includes the template triage prompt line from T004.
3. If `feature/supervisor` (PR #21) merges first, expect small textual conflicts in `scripts/lib/workflow.py`, `scripts/ai-pipeline`, `scripts/ai-recover` and `tests/test_workflow.py` (see `.ai/current-plan.md`).

### Covered by automated tests
- Missing 0-count section, heading verdict, mismatches still rejected (planned): `test_review_format_*`, `test_review_counts_must_match_listed_findings`, `test_failed_or_malformed_reviews_preserve_report`
- Base resolution (ahead, equal, diverged, explicit `origin/`/SHA) (planned): `test_review_base_*`, `test_pr_base_follows_the_review_base_or_must_be_explicit`
- Base moved past the branch: stop before any agent, recovery escalates without Claude, rerun after merge, publish wording (planned): `test_base_moved_*`
- Severity suffix in disposition rows (planned): `test_triage_severity_suffix_*`
- Recovery decision after prose, ambiguity still escalates (planned): `test_recovery_decision_parsing_is_strict`, `test_recovery_decision_after_prose`

## Human todos
None yet (see "Needs you").

## Next action
Implement T001.
