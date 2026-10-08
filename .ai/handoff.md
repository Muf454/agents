# Handoff

## What has been implemented?
Branch `fix/catchup-review`: Codex catch-up review M1 and M2.
- T001 (M1, done): the Claude fallback reviewer has no shell. `claude_attempt` runs `--tools Read,Glob,Grep --allowedTools Read Glob Grep`; `review-allowlist` prints just those three and ignores `.ai/permissions.allow`; the probe directory is gone. `review_context` (in `scripts/ai-review`) writes the git context per mode to `.ai/local/review-context/` right before each Claude session and removes it right after; any failed step stops before Claude with the prior review kept. New helper `review-range` (current review's HEAD and merge-base) for the re-check range. Claude-path prompts name the context files; `claude-review.md` "Evidence" replaces the probe section. README, `docs/workflow.md` and the vault flow chart describe the policy.
- T002 (M2, outcomes for stopped attempts): pending.

## Flow chart
Flow chart updated

## Manual testing for the human
### Needs you
1. After merge, approve `setup-project --upgrade --apply` for agents, raid-planner and family-planner so their installed copies get the read-only reviewer.

### Pending (mission control)
1. Live check with the Claude CLI: run a fallback review (`AI_REVIEWER=claude .ai/bin/ai-review --base master`) in a scratch project; expected: the session log shows no Bash/Edit/Write tool use (any attempt appears as a denial in `.ai/local/review-denials.log`), it read files under `.ai/local/review-context/`, and that directory is gone afterwards.

### Covered by automated tests
- Reviewer gets Read/Glob/Grep only, whatever the project allowlist holds: `test_review_allowlist_is_read_glob_grep_whatever_the_project_allows`, `test_review_falls_back_to_claude_at_the_codex_limit`, `test_claude_review_denials_and_allowlist_are_recorded`
- Code-mode context (diff, log, changed paths) and prompt: `test_claude_review_context_code_mode`
- Second round gets `since-last-review.patch`: `test_claude_review_context_second_review_has_the_delta`
- Re-check context from the review header, with findings: `test_claude_review_context_recheck_mode`
- Plan-mode context: `test_claude_review_context_plan_mode`
- Context rebuilt after a usage-limit retry and removed: `test_claude_review_context_is_rebuilt_after_a_limit_and_removed`
- Failed context command stops before Claude, prior review kept and bound: `test_claude_review_context_failure_stops_before_claude`
- Failed or checkout-changing reviewer keeps the prior review, no context left: `test_claude_review_failure_or_write_keeps_the_prior_review`
- `review-range` prints HEAD and merge-base, fails on an unbound review: `test_review_range_prints_head_and_merge_base`

## Human todos
None.

## Next action
T002 (outcomes for stopped attempts).
