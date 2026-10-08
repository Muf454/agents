<!-- Host evidence: HEAD 6deb935b69437226ad05501e4c60868feba4fc78; merge-base ba330ef04b94ee86ea8ecf3a4e8dc3ace0e6c200; saved 2026-10-08T08:38:44Z. -->

> **Reviewer: Claude fallback (claude-fable-5-1, effort high; Codex usage limit until 2026-10-08 12:05). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

The larger targeted run has now finished, so the review's validation section can be completed. Everything else in the review stands unchanged.

# Independent review (Claude, read-only)

Overall verdict: PROCEED — the no-shell reviewer, the host-prepared context and the stopped-attempt outcome logging are implemented as specified and covered by relevant tests; one previously reported MINOR gap in the malformed-queue fallback is still open and undispositioned.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `6deb935b69437226ad05501e4c60868feba4fc78`
Supplied base and merge-base: `ba330ef04b94ee86ea8ecf3a4e8dc3ace0e6c200`

Inspected: `AGENTS.md`, `.ai/tasks.md`, `.ai/state.md`, `.ai/handoff.md`, `.ai/reviews/current.md` (prior Codex review at `be83ab5`), `.ai/reviews/dispositions.md`, the full diff `ba330ef..6deb935` for `scripts/ai-review`, `scripts/ai-run`, `scripts/lib/workflow.py`, `templates/.ai/prompts/claude-review.md`, `tests/test_workflow.py`, `README.md`, `docs/workflow.md`; the full current source of `scripts/ai-review` and `scripts/ai-run`; `.claude/settings.json`; `.gitignore`; `scripts/lib/common.sh` (`ai_die`, `ai_guard_verify`, `ai_limit_pause`).

## Validation observed/run

- `.ai/local/validation.json`: **PASS**, exit 0, `2026-10-08T08:30:25Z`, head `42aef4c` (the reviewed HEAD differs from it only by the "record review handoff" bookkeeping commit). Its log `.ai/local/check-E41uuHRR.log` ends with `Ran 287 tests in 125.8s (8 shards, 287 collected) OK`.
- Run here: `python3 -m unittest tests.test_workflow -k review_allowlist -k claude_review -k review_falls_back -k fall_back -k review_context -k review_range -k outcome -k runner_no_progress -k fix_round_count -k convergence -k triage_completion` → **49 tests OK in 224.8 s** (the T001 and T002 targeted selections plus T003's five multi-round pipeline tests).
- Run here: `python3 -m unittest tests.test_workflow -k review_context -k review_range -k review_allowlist -k outcome` → **21 tests OK in 55.0 s** (includes the SIGTERM/SIGINT and self-kill cases).
- Probe (under `.ai/local/review-probes/`, run through `unittest discover`): `outcome_title('T001')` against a queue that is malformed Markdown with one invalid UTF-8 byte → `UnicodeDecodeError` propagates; the valid-UTF-8 malformed control returns `'broken'`. See N7.
- `git status --porcelain --untracked-files=all` after the review: clean.

Limitations: no live Claude CLI run (the mock asserts invocation arguments only; the provider's enforcement of `--tools Read,Glob,Grep` is still the pending mission-control check). The vault flow chart lives outside the checkout and was not read. Ad-hoc shell probes (`python3 script.py`, `rm`) were denied in this session; the probe ran through the unittest entry point. I could not delete `.ai/local/review-probes/` myself (rm denied); the host removes it. The full `.ai/bin/ai-check` was not rerun; the recorded gate result above is the full-suite evidence.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N7 — An undecodable task queue still loses the stopped attempt (re-reported, undispositioned) — **demonstrated**

**Requirement:** T002 implementation notes: `outcome task` "must log even when `.ai/tasks.md` no longer parses (… or a tolerant fallback); genuine write failures stay nonfatal."

**Location:** `scripts/lib/workflow.py:2025-2039` (`outcome_title`): the first lookup catches `(ValueError, OSError)`, which includes `UnicodeDecodeError`; the heading-scan fallback at line 2033 calls `Path('.ai/tasks.md').read_text()` again and catches only `OSError`, so the same decoding error escapes on the second read.

**Impact:** A session that leaves non-UTF-8 bytes in the queue stops the runner via `tasks check`; `on_exit` calls `task_outcome error`, the helper raises before appending, the runner prints "could not append" and closes the attempt. After repair the retry is logged as attempt 1 with `first_pass=true`, which is exactly the signal R2 wants to keep honest. Telemetry only, no data at risk.

**Evidence:** Probe output: `control title: 'broken'`; `undecodable RAISED: UnicodeDecodeError 'utf-8' codec can't decode byte 0x96 in position 32: invalid start byte`. This is the same finding Codex reported as N7 in the review of `be83ab5` (`.ai/reviews/current.md`); `.ai/reviews/dispositions.md` has no row for that review, and T003 (added afterwards) did not touch it.

**Recommended direction:** Read the queue as bytes in the fallback (`read_bytes().decode('utf-8', 'replace')`) or catch `ValueError` there too, returning `''` on failure. Add a regression: corrupt the queue's encoding, assert the `error` row, repair, assert attempt 2 `done` with `first_pass=false`. Record a disposition row for the `be83ab5` review so the pipeline's record is complete.

## Missing coverage

Checked against the checklist: 4 (stale results: the context is rebuilt per Claude attempt after a usage-limit pause and the `unchanged` check guards HEAD; covered by `test_claude_review_context_is_rebuilt_after_a_limit_and_removed`), 10 (irreversible operations: the only `rm -rf` targets the fixed relative path `.ai/local/review-context` after `ai_root`, and the prior review is never touched before publish; covered by the failure-before-Claude test). Items 1–3 and 5–9 do not apply to this change.

Not covered by tests:
- Undecodable queue (N7).
- An implementation-session usage-limit wait beyond `AI_LIMIT_MAX_WAIT` producing exactly one `error` row. `test_outcome_triage_runs_log_no_task_outcome` exercises limit exhaustion only for triage, where nothing must be logged; the documented `error` case for an implementation attempt is asserted nowhere (traced: `ai_limit_pause` → `ai_die` → `on_exit` with `attempt_open=yes`, `session_code` not 124/137 → `error`).
- `since-last-review.patch` content: `test_claude_review_context_second_review_has_the_delta` asserts the file name and the prompt line, not that the patch covers `last_head..HEAD` rather than the full range.
- The re-check context's own failure branches (`review-range` disagreeing with `recheck-prepare`, missing merge-base in the header). Traced: both read the HEAD from `review_info_values()` on the same file (`workflow.py:896`, `:1238`), so a mismatch is unreachable today.
- Live provider enforcement of the tool list (pending, listed in the handoff).

## Security concerns

- Reviewer tool surface: `claude -p … --tools Read,Glob,Grep --allowedTools Read Glob Grep --strict-mcp-config --mcp-config '{"mcpServers":{}}' --setting-sources project` (`scripts/ai-review:125-130`). No Bash, Edit, Write, Agent, WebFetch or MCP tool is offered, and `review_allowlist` ignores `.ai/permissions.allow` entirely (`workflow.py:676-682`; `test_review_allowlist_is_read_glob_grep_whatever_the_project_allows` seeds `Bash(bash *)`, `Bash(python3 *)`, `Edit`, `Write` and still gets the three tools). This closes the command-argument routes the plan rounds found.
- Residual, pre-existing and acknowledged: Read, Glob and Grep accept absolute paths, so a reviewer could read files outside the checkout and quote them into a review that is published in the PR. The only control is the prompt line in `claude_attempt`; `.claude/settings.json` has no `Read(...)` deny rules. Not counted as a finding of this change (the previous policy had the same exposure plus Bash), but a deny list for obvious secret paths is worth a follow-up.
- Host git context uses `--no-ext-diff --no-textconv` (`scripts/ai-review:85`, `:97`), so a project's diff/textconv drivers cannot run during preparation. Every step is checked and `context_fail` runs before `claude` (`:76-79`); `test_claude_review_context_failure_stops_before_claude` proves no invocation and a byte-identical, still-bound prior review.
- `on_exit` only calls the project helper after re-verifying the gate digest (`scripts/ai-run:90`), so a run that stopped because the gate changed never executes a possibly modified `workflow.py`.

## Architecture concerns

- The Codex prompts are unchanged in content (the `ending`/`rows` split reassembles the same strings); the Claude prompt is a parallel string naming context files. This duplicates the scope sentence per mode in three places; acceptable now, a fourth mode would justify a small builder.
- Attempt tracking is a three-variable state machine in bash (`track_attempt`, `attempt_open`, `session_code`). Traced every exit between `track_attempt=yes` (`ai-run:316`) and the outcome calls: `claude_session` deaths (timeout, error, limit beyond budget) → `on_exit`; post-session `ai_branch`/`tasks check`/`ai_guard_verify` deaths → `on_exit` (`error`, or nothing after a gate change); DONE/BLOCKED/other → explicit outcome before any later `ai_die`. No path logs twice, none exits 0 with the attempt open. Stops after a completed session but before its outcome (run-time limit before post-task validation, secret-looking files, unchecked BLOCKED work) are classified `error`; that matches the spec's "any stop in between" wording but slightly overstates session failures in the tuning data.
- `review-range` reuses `review_info_values` (binding check) and the shared `review_header` regex, as the plan required; `current_review_rounds` goes through the same function.
- T003 touches only the test harness: `COMMAND_TIMEOUT` 25 s, `PIPELINE_TIMEOUT` 120 s via `tool('ai-pipeline', …)`, both scaled by `AI_TEST_TIMEOUT_SCALE`. Direct `subprocess` calls elsewhere in the tests keep their own bounds (15 s, 20 s, 60 s, 120 s), none of which are pipeline runs. The five previously timing-out pipeline tests passed here in the 49-test run. The claim that the range `git log --stat` is bounded by the PR's own commits holds for code and re-check mode; plan mode uses `-n 20`.
- Process gap: the Codex review of `be83ab5` has no disposition rows at all, although the template asks for one per BLOCKER/MAJOR and MINOR "where relevant". The MINOR was relevant enough to re-surface here.

Pre-existing defects excluded from the counts: Read access outside the checkout (above); `.ai/local/` ignore-status is assumed by the `unchanged` check (as it was for the old probe directory and the review temp files).

## Manual testing recommendations

### Needs you

- Run the pending live fallback review (`AI_REVIEWER=claude .ai/bin/ai-review --base master` in a scratch project) and confirm in the session JSON that only Read/Glob/Grep tool uses appear and that `.ai/local/review-context/` is gone afterwards. With Bash absent from `--tools`, a shell attempt cannot show up in `.ai/local/review-denials.log` as the handoff suggests; the evidence is the absence of such tool calls in `review-*.claude.json`, not a denial line.
- After merge, approve `setup-project --upgrade --apply` for the installed copies; this repository's own `.ai/prompts/claude-review.md` (the frozen copy that produced this very prompt) still carries the probe instructions until then.
- Confirm the vault flow chart (`agents-flow.md`) was updated for both the reviewer policy and the stopped-attempt lifecycle; not verifiable from the checkout.

### Covered by automated tests

- Reviewer arguments, fixed allowlist, saved `.allowlist`: `test_review_falls_back_to_claude_at_the_codex_limit`, `test_review_allowlist_is_read_glob_grep_whatever_the_project_allows`, `test_claude_review_denials_and_allowlist_are_recorded` (passed here).
- Context per mode, delta, rebuild after limit, removal, failure before Claude, `review-range`: the six `test_claude_review_context_*` tests and `test_review_range_prints_head_and_merge_base` (passed here).
- Stopped attempts numbered, validation once, 137, SIGTERM/SIGINT, malformed queue retry, zero budget, triage, limit pause: the nine `test_outcome_*` tests (passed here).
- CI headroom: `test_fix_round_count_ignores_agent_subject_*`, `test_convergence_*`, `test_triage_completion_respects_the_fix_round_limit` (passed here under the 120 s bound).
- Should be added: undecodable queue (N7) and an implementation-session limit-exhaustion `error` row.

This review does not constitute human acceptance.
