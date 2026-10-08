# Handoff

## What has been implemented?
Branch `fix/catchup-review`: Codex catch-up review M1 and M2.
- T001 (M1, done): the Claude fallback reviewer has no shell. `claude_attempt` runs `--tools Read,Glob,Grep --allowedTools Read Glob Grep`; `review-allowlist` prints just those three and ignores `.ai/permissions.allow`; the probe directory is gone. `review_context` (in `scripts/ai-review`) writes the git context per mode to `.ai/local/review-context/` right before each Claude session and removes it right after; any failed step stops before Claude with the prior review kept. New helper `review-range` (current review's HEAD and merge-base) for the re-check range. Claude-path prompts name the context files; `claude-review.md` "Evidence" replaces the probe section. README, `docs/workflow.md` and the vault flow chart describe the policy.
- T002 (M2, done): a task attempt opens right before the implementation session's `claude` call and is logged exactly once: `done`/`blocked`/`validation_failed`/`no_checkpoint`, or from the EXIT handler `timeout` (session exit 124/137), `interrupted` (runner exit 130/143) or `error`. Limit pauses stay in one attempt; `--triage` and a run with no time left log nothing; `outcome task` logs even when `.ai/tasks.md` no longer parses. `docs/workflow.md` "Outcome log" documents the lifecycle and the deferred signal delivery; README and the vault flow chart updated.

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
- Timeout, error, then success log attempts 1, 2, 3: `test_outcome_stopped_attempts_are_logged_and_numbered`
- One `validation_failed` line: `test_outcome_validation_failure_logs_once`
- Exit 137 is a `timeout`: `test_outcome_killed_session_is_a_timeout`
- SIGTERM/SIGINT to the runner log one `interrupted` line, retry is the next attempt: `test_outcome_signal_to_runner_logs_interrupted_once`
- Malformed queue logs `error`, retry is attempt 2: `test_outcome_malformed_queue_then_retry`, `test_runner_no_progress_denial_and_error_stop_without_retry`
- No time left logs nothing: `test_outcome_no_time_left_logs_nothing`
- Triage logs no task outcome: `test_outcome_triage_runs_log_no_task_outcome`
- Limit pause stays in one attempt: `test_outcome_limit_pause_stays_in_one_attempt`

## Human todos
None.

## Next action
None: all tasks done; final validation and review.
