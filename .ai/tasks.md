# Task queue

Branch `fix/catchup-review`: fixes for the Codex catch-up review M1/M2 (see `.ai/project-spec.md`).
Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts` or other gate files.

## T001 — Read-only Claude reviewer policy (M1)
Status: DONE
Dependencies: none
Model: opus

### Goal
R1: the Claude fallback reviewer has no shell and no write tool (Read/Glob/Grep only) and reviews from host-prepared git context, in code, plan and re-check mode.

### Implementation notes
Convergence (plan review rounds 1–4 each found a new command-argument route through Bash allow/deny lists: runner options, exact entries, git option abbreviations such as `git grep --open-files=`): the reviewer gets NO Bash tool at all. Reference patches inherit runners and Bash: do not copy that part.

Tools. `scripts/ai-review` `claude_attempt` runs `claude -p` with `--tools Read,Glob,Grep --allowedTools Read Glob Grep` (no Bash, Edit or Write; no `review-probes` directory, drop its `mkdir`/`rm`). `scripts/lib/workflow.py` `review_allowlist` prints just `Read`, `Glob`, `Grep` and no longer reads `.ai/permissions.allow` (keep the helper so the saved `.allowlist` file and tests stay meaningful; drop `REVIEW_GIT`, `REVIEW_DROP_FIRST`, `REVIEW_DROP_OPEN`). The checkout-unchanged check stays.

Context. New function `review_context` in `scripts/ai-review`, called by `claude_attempt` right before the session (so a retry after a Claude usage-limit pause rebuilds it): `rm -rf` and recreate `.ai/local/review-context/` (ignored by git, so `unchanged` is not affected), write the files for the mode, and `rm -rf` it right after the session, before any result check, so every `ai_die` path after the session leaves nothing behind (an interrupted ai-review may leave it until the next review recreates it). Host git commands use `--no-ext-diff --no-textconv`; no truncation (the reviewer pages large files with Read offset/limit). Per mode, from globals each mode sets before `run_review` (`context_base`, `context_head`, `context_last`, `context_findings`):
- code: `diff.patch` = `git diff $merge_base..$head`; `log.txt` = `git log --stat $merge_base..$head`; `files.txt` = `git diff --name-only $merge_base..$head`; `since-last-review.patch` = `git diff $last_head..$head` only under today's condition (`last_head` known and an ancestor of `head`).
- recheck: the base is not in shell scope today. Add helper `review-range` to `workflow.py` printing `HEAD MERGE_BASE` of the current review: verify it with `review_info_values` (binding), then parse with the header regex `current_review_rounds` uses (factor it into one function both call). `ai-review` dies before the session if that HEAD differs from `recheck-prepare`'s `head` or the header has no merge-base. Files: `diff.patch`, `log.txt`, `files.txt` for `base..head` as in code mode, plus `findings.txt` = the rejected-row lines `recheck-prepare` printed. `current.md` and `dispositions.md` stay where they are (the prompt names them).
- plan: no `diff.patch`; `files.txt` = `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`; `log.txt` = `git log --stat -n 20 HEAD`.

Preparation failures (plan review round 6, P3). `run_review` calls `claude_attempt "$prompt" || code=$?`, and bash suppresses `errexit` inside a function called in that context and in everything it calls, so a failed git command or write in `review_context` would otherwise fall through to the session. Check every mandatory context command and write explicitly (`… > file || fail`); on the first failure `rm -rf .ai/local/review-context` and `ai_die 'Could not prepare the review context; prior review preserved.'` before `claude` is invoked (`ai_die` exits even from the conditional context; nothing is published, `current.md`/`plan.md` stay). The `since-last-review.patch` ancestor test is a condition, not a failure; the `review-range` check (recheck) dies the same way.

Prompts. The shared mode prompts keep their git commands for Codex. Each mode also builds `claude_prompt` (same template, history and output contract) whose scope lines name the context files instead of commands: code `REVIEW SCOPE: HEAD=…; merge-base=…. You have no shell: the diff is .ai/local/review-context/diff.patch, the commits log.txt, the changed paths files.txt …` and `CHANGED SINCE THE LAST REVIEW: .ai/local/review-context/since-last-review.patch`; recheck adds `findings.txt`; plan names `files.txt`/`log.txt`. `run_review "$prompt" "$claude_prompt"` passes it to `claude_attempt`. The `CLAUDE REVIEWER` suffix drops the probe sentence and says: tools Read/Glob/Grep only, read only the checkout (including `.ai/local`), never files outside it (review security note: Read is not limited to the checkout and the review text is published).

Docs. Rewrite `templates/.ai/prompts/claude-review.md` "Prove findings with probes" into "Evidence": no commands or probes; trace exact code paths, read the prepared context, tests and the validation evidence (`.ai/local/validation.json`, gate logs); **demonstrated** = traced path or validation output, **suspected** = reasoned; no vitest/PGlite probe instructions. README "Claude fallback reviewer" section (it promises inherited `npm test`/vitest and probes), `docs/workflow.md` reviewer section (lines ~530–546: no Bash, `.ai/local/review-context/` per mode, `review-range`, why), vault flow chart `agents-flow.md` (reviewer policy; bump `updated:`).

Tests (`tests/test_workflow.py`). The harness mock `claude` (`CLAUDE REVIEWER` branch, lines ~55–60) stops asserting/writing the probe directory: it asserts `.ai/local/review-probes` does not exist and the prompt has no `inspect git diff`, and appends per call to `MOCK_STATE_DIR/claude-review-context.log` the mode, the sorted file names in `.ai/local/review-context/`, `files.txt` and the `diff --git` lines of `diff.patch` (when present). Keep a marker line in the mock that `test_claude_review_failure_or_write_keeps_the_prior_review` rewrites to write `stray.txt` (the "reviewer changes the checkout" case). Update the probe-directory assertions at lines ~2286, ~2293, ~2438, ~2460, ~2486. New tests named `test_claude_review_context_*`. Failure test: a test-local `git` wrapper in the mock bin delegates to the real git (path resolved before the mock bin is prepended) and exits 1 only for a `diff` invocation carrying `--no-ext-diff` (used only by the context commands, so preflight such as `merge-base`/`rev-parse` passes); no test hook in `scripts/`.

Mission control runs a live check with the Claude CLI afterwards (the reviewer cannot run any Bash command or write a file); list it in the task result as pending.

### Likely affected modules
scripts/ai-review, scripts/lib/workflow.py, templates/.ai/prompts/claude-review.md, README.md, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- The reviewer invocation (mock args) has `--tools Read,Glob,Grep`, `--allowedTools` only `Read Glob Grep`, and no probe directory exists during the session; a project allowlist full of runners (exact and wildcard, incl. `Bash(git grep *)`, `Bash(pytest --basetemp=/x)`, `Bash(npm test)`) changes nothing; the saved `.allowlist` lists exactly `Read`, `Glob`, `Grep`.
- Code mode (`AI_REVIEWER=claude`): during the session `files.txt` lists the fixture file `T001.txt` and `diff.patch` contains `diff --git a/T001.txt b/T001.txt`; `log.txt` exists; the Claude prompt names `.ai/local/review-context/diff.patch` and contains no `inspect git diff`.
- Second code review (fixture `first_review_round()`, Claude reviewer): `since-last-review.patch` exists and the prompt names it; the first review has none.
- Re-check mode (`test_recheck_falls_back_to_claude` path): `files.txt` lists `T001.txt`, `diff.patch` contains its `diff --git` line (base from the review header) and `findings.txt` contains `M1`.
- Plan mode: `files.txt` lists `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`; no `diff.patch`.
- `.ai/local/review-context` does not exist after a successful review, after a failed one (`MOCK_CLAUDE_REVIEW='error'`) and after a `limit-once` retry (where the mock saw it on both calls); a review still publishes and binds as before.
- A context `git diff` that fails after preflight (wrapper above, `AI_REVIEWER=claude`, code mode, with a prior bound review): `ai-review` exits nonzero, the mock `claude` was never invoked (no call in its log), the prior `current.md` is byte-identical and still bound, and `.ai/local/review-context` does not exist.
- `review-range` prints the current review's HEAD and merge-base and fails on an unbound review.
- README, docs, prompt and flow chart describe the same policy.

### Validation
`python3 -m unittest tests.test_workflow -k review_allowlist -k claude_review -k review_falls_back -k fallback -k fall_back -k reviewer_setting -k pipeline_without_codex -k review_context -k review_range`; `.ai/bin/ai-check`

### Result / notes
Done 2026-10-08. `scripts/ai-review`: `claude_attempt` runs `--tools Read,Glob,Grep --allowedTools Read Glob Grep` (from `review-allowlist`), no probe directory; new `review_context`/`context_fail` write `.ai/local/review-context/` per mode (`--no-ext-diff --no-textconv`, every step checked, dies before `claude` on failure) and the directory is removed right after the session; each mode builds `claude_prompt` naming the context files, Codex prompts are byte-identical to before. `scripts/lib/workflow.py`: `review_allowlist` prints Read/Glob/Grep only (`REVIEW_GIT`/`REVIEW_DROP_*` removed); `review_header` shared by `current_review_rounds` and new `review-range`. Prompt template "Evidence" section, README, `docs/workflow.md`, vault `agents-flow.md` updated. Tests: mock asserts no probe dir and no `inspect git diff`, logs the context per call; new `test_claude_review_context_*` (code, delta, recheck, plan, limit retry, failure before Claude), `test_review_range_prints_head_and_merge_base`, `test_review_allowlist_is_read_glob_grep_whatever_the_project_allows`. Targeted command: 25 tests OK; `.ai/bin/ai-check`: 279 tests OK (first run failed only `test_pr_body_flow_this_repo_declares_the_flow_chart` because the handoff lacked `## Flow chart`; added "Flow chart updated").
Pending (mission control): live Claude CLI check that the reviewer can run no Bash command, write no file, and reads `.ai/local/review-context/`.

## T002 — Outcome logged for stopped task attempts (M2)
Status: DONE
Dependencies: T001
Model: sonnet

### Goal
R2: error, timeout and interruption attempts appear in the outcome log exactly once.

### Implementation notes
`scripts/ai-run`: attempt tracking is opt-in for implementation sessions only (the implementation loop passes a flag or sets a variable before calling `claude_session`; `--triage` never opens an attempt). Open the attempt immediately before the actual `claude` invocation (after preflight checks such as the remaining-time budget); usage-limit pauses and retries inside `claude_session` stay part of the same attempt. Close it in `task_outcome`; the EXIT handler logs `timeout` (session exit 124/137), `interrupted` (runner exit 130/143) or `error` for an open attempt. `error` also covers an `ai_limit_pause` beyond `AI_LIMIT_MAX_WAIT` after the attempt opened (one line in the docs, no extra result value). `scripts/lib/workflow.py` `outcome task`: must log even when `.ai/tasks.md` no longer parses (title/category from metadata captured at launch, or a tolerant fallback); genuine write failures stay nonfatal.

Signal behaviour (plan review round 5, P3, probed): bash runs a trapped INT/TERM only after the foreground command returns, and GNU `timeout` puts itself in its own process group, so neither a signal to the runner nor to its group reaches the session; the runner exits 130/143 when the session ends. Document this in the "Outcome log" section of `docs/workflow.md` (Ctrl-C on an interactive `ai-run` lets the session run to its end or limit; the `interrupted` line's time is then, not the keypress). Do not try to change that behaviour here.

Signal test design (bounded, no 30 s sleeps): a new mock mode `MOCK_CLAUDE='hold'` writes its PID to `.ai/local/mock-session.pid`, then waits (poll 0.05 s, at most 10 s) for `.ai/local/mock-release`, then prints an error result and exits 1. The test starts the runner with `subprocess.Popen(..., start_new_session=True)`, polls (at most 10 s) for the PID file, sends the signal to the runner PID only, creates `mock-release`, then `communicate(timeout=20)`; a `finally` kills the mock PID and the runner's process group if still alive. Assert exit 143 (SIGTERM) or 130 (SIGINT) and exactly one new `interrupted` row; the next run's row has the next attempt number. Exit 137: mock mode `self-kill` does `os.kill(os.getpid(), signal.SIGKILL)` (`timeout` returns 137 at once); do not ignore TERM and wait for `--kill-after`.

Malformed queue: the existing test `test_runner_no_progress_denial_and_error_stop_without_retry` (line ~1084) runs five modes against the same project, branch and T001 and never reruns after its repair, so `bad-format` is T001's fifth logged attempt there. In that test assert per subtest that the mode added exactly one T001 row whose attempt is the previous T001 row's attempt + 1 (for `bad-format`: result `error`). The retry case gets its own fresh fixture, `test_outcome_malformed_queue_then_retry`: `bad-format` run, repair and commit the queue, rerun successfully.

Update the "Outcome log" section of `docs/workflow.md` and the vault flow chart `agents-flow.md` (stopped-attempt lifecycle; T001 already did the reviewer policy); the PR description must say "Flow chart updated". New tests named `test_outcome_*`. Reference: `.ai/local/reference/catchup-m1-m2.patch` (opens the attempt too early).

### Likely affected modules
README.md (outcome section), scripts/ai-run, scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Timeout, then error, then a successful run log attempts 1, 2, 3 with results timeout, error, done and `first_pass` false for all (test fails without the fix).
- A validation failure logs exactly one `validation_failed` line.
- Exit 137 (`self-kill` mock) is logged as `timeout` (separate case from 124).
- SIGTERM and SIGINT to the runner PID during a `hold` session, per the design above, exit 143/130 within the bounded waits with exactly one `interrupted` line each; the retry is the next attempt; no mock or runner process is left.
- In `test_runner_no_progress_denial_and_error_stop_without_retry`, each mode adds exactly one T001 row with the previous T001 attempt + 1, and `bad-format`'s row is `error`. In the fresh fixture `test_outcome_malformed_queue_then_retry`, rows are attempt 1 `error`, attempt 2 `done`, `first_pass=false`.
- A run with zero time budget left logs no task outcome.
- Successful and failed `--triage` runs create no task outcome; a usage-limit pause and retry inside one implementation session yields exactly one outcome with the original start time.
- Docs describe the deferred signal delivery and the limit-wait `error` case; vault flow chart updated.

### Validation
`python3 -m unittest tests.test_workflow -k outcome -k runner_no_progress`; `.ai/bin/ai-check`

### Result / notes
Fixed 2026-10-08 (sonnet): the test starts the runner with `preexec_fn` resetting SIGINT to SIG_DFL; the 0.5 s sleep is gone (the pid-file wait remains); `docs/workflow.md` notes that background-launched pipelines ignore SIGINT (use SIGTERM). Targeted: 10 tests OK; `.ai/bin/ai-check`: 287 OK (122.6 s). Not verified: the run from a SIGINT-ignoring shell (the `python3 -c` wrapper was denied in this session), so the host gate is the real check.
Mission control 2026-10-08 (second failure, root cause): not timing. The host gate runs under a pipeline started in the background (`setsid nohup … &` from a non-interactive shell), so SIGINT is SIG_IGN on entry for every child; bash cannot trap a signal that was ignored on entry, so the runner never sees SIGINT and exits 1. The session's own foreground gate passed for the same reason. Fix in the test: start the runner with SIGINT restored, e.g. `subprocess.Popen(..., preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))` (or `restore_signals` plus an explicit reset), and keep the ready-marker wait; verify by running the test from a shell started with SIGINT ignored (`python3 -c 'import signal,subprocess;signal.signal(signal.SIGINT,signal.SIG_IGN);subprocess.run([...])'`). Remove the 0.5 s sleep if it is no longer needed. Note in docs/workflow.md that background-launched pipelines ignore SIGINT (use SIGTERM to stop them).
Mission control 2026-10-08: the full gate after the checkpoint (38dcdaa) failed in `test_outcome_signal_to_runner_logs_interrupted_once` (SIGINT run exited 1 instead of 130, then a dirty checkout), although the earlier gate on the same code passed 287/287: the signal test is timing-dependent under the parallel runner. Make it deterministic (wait for the runner's own ready marker before signalling; the runner must reach its trap before the signal), then re-run the gate twice.
Done 2026-10-08. `scripts/ai-run`: `track_attempt` (set only around the implementation `claude_session`) makes `claude_session` open the attempt (`attempt_open`, `task_started`) right before the `claude` call; `task_outcome` closes it; `on_exit` logs `interrupted` (exit 130/143), `timeout` (session exit 124/137) or `error` for a still-open attempt, but only while the approved gate digest is intact (no project helper runs after a gate change; found by `test_runner_detects_even_committed_gate_changes_before_untrusted_helpers`). `scripts/lib/workflow.py`: `outcome_title` falls back to a heading scan, then an empty title, when `.ai/tasks.md` no longer parses. Docs: `docs/workflow.md` Outcome log (lifecycle, limit-wait `error`, deferred signal delivery, gate-change exception), README result list, vault `agents-flow.md` + hub log. Tests: mock modes `hold`/`self-kill`; new `test_outcome_*` (stopped attempts numbered, validation once, 137, SIGTERM/SIGINT, malformed queue retry, no time left, triage, limit pause); `test_runner_no_progress_denial_and_error_stop_without_retry` asserts one row per mode. Mutation check: with tracking disabled the stopped-attempt, 137, signal and malformed-queue tests fail. Targeted: 11 tests OK; `.ai/bin/ai-check`: 287 tests OK.

## T003 — CI headroom for multi-round pipeline tests
Status: DONE
Dependencies: T002
Model: sonnet

### Goal
PR #19's CI self-check fails twice in a row (also on a rerun) with `subprocess.TimeoutExpired` for 5 multi-round `ai-pipeline` tests (`test_fix_round_count_ignores_agent_subject_*`, `test_convergence_pipeline_requires_the_line_from_round_three`, `test_convergence_interrupted_round_three_resumes_*`, `test_triage_completion_respects_the_fix_round_limit`): "timed out after 25 seconds". Locally each takes ~12 s on branch and master; the GitHub runner (4 shards, ~500 s per shard) is several times slower, and this branch adds host-side context preparation per Claude review, pushing those tests past 25 s. Master's CI passed.

### Implementation notes
Find where the test harness sets the 25 s per-command timeout (`tests/test_workflow.py`, `tool`/`run_cmd`). Give whole-pipeline invocations a larger bound (e.g. a module constant `PIPELINE_TIMEOUT = 120`, overridable with `AI_TEST_TIMEOUT_SCALE` for slow machines) instead of 25 s; keep short commands short so a real hang still fails fast. Do not change product code. Check whether the context preparation does avoidable work per review (e.g. full `git log --stat` over long ranges) and bound it if so (limit lines/commits, as the plan-mode `-n 20` does).

### Likely affected modules
tests/test_workflow.py, scripts/ai-review (only if the context preparation is unbounded)

### Acceptance criteria
- The five tests pass locally with the new bound; a deliberately hung pipeline still fails within the bound.
- The PR's CI self-check passes after the pipeline pushes.

### Validation
`python3 -m unittest tests.test_workflow -k fix_round_count -k convergence -k triage_completion`; `.ai/bin/ai-check`

### Result / notes
`tests/test_workflow.py`: `COMMAND_TIMEOUT` (25 s) and `PIPELINE_TIMEOUT` (120 s), both scaled by `AI_TEST_TIMEOUT_SCALE`; `run_cmd` takes a `timeout`, `tool('ai-pipeline', ...)` uses the pipeline bound. A hung pipeline still raises `TimeoutExpired` at 120 s. `ai-review`'s range `git log --stat` spans only the PR's commits, so left unbounded. Targeted run: 19 OK; `.ai/bin/ai-check`: 287 OK. CI re-run on the pushed PR not yet observed.
