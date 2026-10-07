<!-- Plan review of plan digest ffa37e046e7a96b96351b28771b9d87f40d7c8980607d88101f12fa287add770; saved 2026-10-07T19:12:03Z. -->

> **Reviewer: Claude fallback (claude-fable-5-1, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

# Plan review

Overall verdict: CHANGES REQUIRED — reconcile the spec with revision 4 and pin down the host-prepared review context per mode before implementing.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=3

Reviewed HEAD: `23ea9385d7af62a8f24f80732b45b23595db4bf3` (clean checkout, confirmed before and after the review).

Inspected: `AGENTS.md`, `CLAUDE.md`, `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`, `.ai/state.md`, `.ai/reviews/plan.md` (round 4), `.ai/reviews/dispositions.md`, `.ai/validate`, `scripts/ai-review` (whole), `scripts/ai-run` (whole), `scripts/lib/common.sh` (`ai_die`, `ai_limit_pause`), `scripts/lib/workflow.py` (`review_allowlist`, `claude_text`, `tasks`, `review_info_values`, `review_history` header parsing, `recheck_prepare`, `outcome`, `outcomes_report`, `plan_digest`), `templates/.ai/prompts/claude-review.md`, `templates/.ai/prompts/review.md`, `docs/workflow.md` (reviewer and outcome sections), `README.md` (fallback reviewer section), the test harness mock `claude`/`codex` and the reviewer/outcome tests in `tests/test_workflow.py`, both reference patches under `.ai/local/reference/`, and the vault `agents-flow.md` reviewer/outcome lines.

## BLOCKER findings

None.

## MAJOR findings

- P1: The spec and the plan file still require the policy revision 4 abandoned. **Demonstrated** (read the files).

  **Location:** `.ai/project-spec.md` R1 (lines 12–18) and its "Reference" paragraph; `.ai/current-plan.md:4`; versus `.ai/tasks.md` T001 implementation notes and acceptance criteria.

  R1 says the reviewer "inherits only project `Bash(...)` entries positively known to read or check", that `ai-review` passes `--disallowedTools` entries for `--output`, `--ext-diff`, `git grep -O`, `>` and so on, and that "the saved `.allowlist` file lists both". The plan file says "reviewer allowlist positive list + deny list". T001 (revision 4) says the opposite: no Bash tool at all, drop `REVIEW_DENY`/`--deny`, `review_allowlist` is just `Read`, `Glob`, `Grep`. The implementer is told to read the spec first, and the later code review (Codex catch-up or the Claude fallback) is told to "reconcile requested scope with delivered behavior" against the spec, so an implementation that follows T001 will be reported as not meeting R1, and an implementer that follows R1 reintroduces the runner routes rounds 1–4 removed. The spec is part of `plan_digest`, so it must be fixed in this planning round anyway.

  **Concrete plan change:** Rewrite R1 to the revision-4 policy: the Claude fallback reviewer runs with tools Read/Glob/Grep only (no Bash, Edit or Write, no probe directory), reads host-prepared context under `.ai/local/review-context/` plus the validation evidence, and the saved `.allowlist` lists those three tools. Mark the "Reference" paragraph's live deny-list check as superseded. Update the plan file's T001 line to match.

- P2: The host-prepared context is underspecified per mode, and the acceptance only checks that the files exist. **Demonstrated** (traced `scripts/ai-review`).

  **Location:** `.ai/tasks.md` T001 implementation notes ("`diff.patch` (`git diff <merge-base>..<head>`, or the plan files for plan review), `log.txt` (`git log --stat <merge-base>..<head>`) …") and acceptance ("The review context files exist during the session"); `scripts/ai-review:74-105` (`claude_attempt`), `:210-224` (recheck), `:249-258` (code prompt).

  `claude_attempt` receives only the prompt. In code mode the globals `merge_base` and `head` exist (`ai-review:245-247`). In recheck mode only `head` (the reviewed HEAD from `recheck-prepare`) exists; the base is not in shell scope at all. It is recoverable only from the current review's host header (`Host evidence: HEAD h; merge-base m`, parsed by `review_history` at `workflow.py:905-908`), which the task does not say. In plan mode there is no range, so `log.txt` and `files.txt` as written are undefined. The code-mode prompt also keeps two instructions the reviewer can no longer follow: "Inspect git diff $merge_base..$head" and "CHANGED SINCE THE LAST REVIEW: inspect git diff $last_head..$head" (`ai-review:251,258`). A recheck or code review that gets an empty or wrong `diff.patch` still passes the acceptance criterion as written, because the mock only asserts the files exist.

  **Concrete plan change:** Spell out per mode in T001: code = `git diff $merge_base..$head`, `git log --stat $merge_base..$head`, `git diff --name-only $merge_base..$head`, plus `since-last-review.patch` when `last_head` is known (or drop that prompt line for the Claude reviewer); recheck = base parsed from the current review's host header with the same regex `review_history` uses, range `base..reviewed head`, plus the rejected rows text and the paths of `current.md`/`dispositions.md`; plan = no diff, `files.txt` = spec/plan/tasks paths, `log.txt` = `git log --stat -n 20 HEAD` or omitted. Reword the mode prompts for the Claude path to name the files instead of commands. Add acceptance: in the code and recheck tests the mock asserts `diff.patch` names the fixture file (`T001.txt`) and `files.txt` lists it; the context directory is also removed after a failed review (`MOCK_CLAUDE_REVIEW='error'`).

## MINOR findings

- P3: The SIGINT/SIGTERM acceptance test needs an explicit delivery design, or it will hang or time out. **Demonstrated** by probe.

  **Location:** `.ai/tasks.md` T002 acceptance ("SIGINT and SIGTERM to a runner with an active session (subprocess test, bounded waits, child cleanup) exit 130/143"); `scripts/ai-run:93-94,152`.

  Probe (bash runner with `trap 'exit 143' TERM` / `trap 'exit 130' INT` waiting on `timeout --signal=TERM --kill-after=10s 20 sleep 20`, started with `start_new_session=True`, signalled after 0.5 s, 6 s bounded wait):

  ```text
  SIGTERM to runner PID only: still running after 6s (bash defers the trap until the foreground child exits)
  SIGTERM to process group:   still running after 6s (bash defers the trap until the foreground child exits)
  SIGINT to process group:    still running after 6s (bash defers the trap until the foreground child exits)
  ```

  Bash runs a trapped signal's handler only after the foreground command returns, and GNU `timeout` moves itself into its own process group, so even a group signal on the runner never reaches `timeout`/`claude`. A test that signals the runner while the existing `MOCK_CLAUDE='timeout'` session sleeps 30 s waits the full 30 s. The same holds in production: Ctrl-C on an interactive `ai-run` reaches the runner but not the session; the `interrupted` outcome is logged when the session ends.

  **Concrete plan change:** In T002 state the test design: a mock session that exits on its own after ~2 s (or the test kills the mock's PID), signal the runner PID once the session log exists, `communicate(timeout=…)` of a few seconds, assert runner exit 130/143 and one `interrupted` row. For the 137 case use a mock that SIGKILLs itself (`timeout` then returns 137 immediately) instead of ignoring TERM and waiting for `--kill-after`. Note the Ctrl-C behaviour in the Outcome log docs so the `interrupted` timestamp is not misread.

- P4: The targeted validation for T001 still misses the plan-mode and recheck-mode fallback tests. **Demonstrated** (test names).

  **Location:** `.ai/tasks.md` T001 Validation (`-k review_allowlist -k claude_review -k review_falls_back -k fallback`); `tests/test_workflow.py:2367` `test_plan_review_and_recheck_fall_back_to_claude`, `:2377` `test_recheck_falls_back_to_claude`, `:2333` `test_reviewer_setting_codex_and_claude_only`, `:2417` `test_pipeline_without_codex_cli_uses_claude`.

  `-k` is a substring match; `fall_back` does not contain `fallback`, so the two tests that exercise the plan and recheck modes (which the acceptance criterion names) are not in the targeted run. The full gate covers them, but the task's own check does not.

  **Concrete plan change:** Add `-k fall_back -k reviewer_setting -k pipeline_without_codex` or name the tests explicitly.

- P5: A SIGKILL or power loss leaves no outcome, so the recovered rerun is logged as attempt 1 with `first_pass=true`. **Suspected** (reasoned from `on_exit` and the `triage-crash` mock at `tests/test_workflow.py:149-153`; not run).

  **Location:** `.ai/tasks.md` T002 implementation notes; `scripts/ai-run:81-94`; `.ai/project-spec.md` R2 ("A later recovery counts as a further attempt and is not a first-time pass").

  The EXIT handler cannot run on SIGKILL (the watchdog/recovery path the toolkit already models with the `triage-crash` mock). R2's literal list (124/137, 130/143, else error) is satisfied, but its purpose, that a recovery is never a first-time pass, is not for crash recovery via `ai-recover`.

  **Concrete plan change:** Either add to T002 a small marker in the host state root written when the attempt opens and removed when it closes, with the next `ai-run` start logging `crashed` for an orphan marker (one test using the existing crash mock), or record the limitation explicitly in the Outcome log section and the task result so the outcome report is read correctly.

## Validation observed

- Probe `.ai/local/review-probes/test_probe.py` run with `python3 -m unittest discover -s .ai/local/review-probes -v`: the trap-delivery probe produced the output quoted in P3. A second probe (test selection via `unittest.discover`) errored on import of the `tests` start directory; P4 was established from the test names instead.
- `git status --porcelain --untracked-files=all` empty before and after; HEAD unchanged.
- No project files modified. Removal of `.ai/local/review-probes/` is left to the host (the `rm` command is outside this reviewer's allowlist).
- Not run: the full gate (`python3 tests/run_parallel.py`), any live Claude CLI session, network or MCP.

## Missing coverage

- T001: no test asserts the context directory is removed after a failed Claude review or after a usage-limit retry (`claude_attempt` is re-entered). Add both to the existing failure and `limit-once` tests.
- T001: the harness mock `claude` currently asserts the probe directory exists and writes `probe.txt` (`tests/test_workflow.py:58-59`), and `test_claude_review_failure_or_write_keeps_the_prior_review` rewrites that line to produce `stray.txt`. The task should say the mock changes to assert the context files and no probe directory, keeping the "reviewer writes outside its scope" case.
- T002: the "existing malformed-queue test" is `test_runner_no_progress_denial_and_error_stop_without_retry` (`bad-format` mode, `tests/test_workflow.py:1084`); it runs five modes in one project, so the outcome assertions must index rows per subtest. Naming the test in T002 avoids a wrong assumption.
- T002: `error` also covers an `ai_limit_pause` that exceeds `AI_LIMIT_MAX_WAIT` after the attempt opened; a one-line note in the docs is enough, no separate result value needed.

## Security concerns

- Checked: command-execution routes for the reviewer (closed by removing Bash), checkout-unchanged check (kept), gate files untouched by the tasks, no new network or credential use.
- Pre-existing, not introduced by this plan: the Read tool is not limited to the checkout, and the review text is committed and posted to the pull request, so content in a reviewed diff could steer the reviewer into quoting files outside the repository. Worth a line in the reviewer prompt ("read only the checkout and `.ai/local`"), but out of R1's scope.

## Scope and model check

- Both tasks carry a `Model:` line. T001 `opus` fits a permission boundary; T002 `sonnet` fits runner lifecycle work without security impact.
- T002 depends on T001 although they touch different lines of `scripts/lib/workflow.py` and the docs; the serialization is harmless.
- No scope creep found beyond the spec, except that the spec itself is behind the plan (P1).

This review is not human acceptance.
