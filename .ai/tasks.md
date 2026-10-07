# Task queue

Branch `fix/catchup-review`: fixes for the Codex catch-up review M1/M2 (see `.ai/project-spec.md`).
Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts` or other gate files.

## T001 — Read-only Claude reviewer policy (M1)
Status: TODO
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

Prompts. The shared mode prompts keep their git commands for Codex. Each mode also builds `claude_prompt` (same template, history and output contract) whose scope lines name the context files instead of commands: code `REVIEW SCOPE: HEAD=…; merge-base=…. You have no shell: the diff is .ai/local/review-context/diff.patch, the commits log.txt, the changed paths files.txt …` and `CHANGED SINCE THE LAST REVIEW: .ai/local/review-context/since-last-review.patch`; recheck adds `findings.txt`; plan names `files.txt`/`log.txt`. `run_review "$prompt" "$claude_prompt"` passes it to `claude_attempt`. The `CLAUDE REVIEWER` suffix drops the probe sentence and says: tools Read/Glob/Grep only, read only the checkout (including `.ai/local`), never files outside it (review security note: Read is not limited to the checkout and the review text is published).

Docs. Rewrite `templates/.ai/prompts/claude-review.md` "Prove findings with probes" into "Evidence": no commands or probes; trace exact code paths, read the prepared context, tests and the validation evidence (`.ai/local/validation.json`, gate logs); **demonstrated** = traced path or validation output, **suspected** = reasoned; no vitest/PGlite probe instructions. README "Claude fallback reviewer" section (it promises inherited `npm test`/vitest and probes), `docs/workflow.md` reviewer section (lines ~530–546: no Bash, `.ai/local/review-context/` per mode, `review-range`, why), vault flow chart `agents-flow.md` (reviewer policy; bump `updated:`).

Tests (`tests/test_workflow.py`). The harness mock `claude` (`CLAUDE REVIEWER` branch, lines ~55–60) stops asserting/writing the probe directory: it asserts `.ai/local/review-probes` does not exist and the prompt has no `inspect git diff`, and appends per call to `MOCK_STATE_DIR/claude-review-context.log` the mode, the sorted file names in `.ai/local/review-context/`, `files.txt` and the `diff --git` lines of `diff.patch` (when present). Keep a marker line in the mock that `test_claude_review_failure_or_write_keeps_the_prior_review` rewrites to write `stray.txt` (the "reviewer changes the checkout" case). Update the probe-directory assertions at lines ~2286, ~2293, ~2438, ~2460, ~2486. New tests named `test_claude_review_context_*`.

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
- `review-range` prints the current review's HEAD and merge-base and fails on an unbound review.
- README, docs, prompt and flow chart describe the same policy.

### Validation
`python3 -m unittest tests.test_workflow -k review_allowlist -k claude_review -k review_falls_back -k fallback -k fall_back -k reviewer_setting -k pipeline_without_codex -k review_context -k review_range`; `.ai/bin/ai-check`

### Result / notes

## T002 — Outcome logged for stopped task attempts (M2)
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
R2: error, timeout and interruption attempts appear in the outcome log exactly once.

### Implementation notes
`scripts/ai-run`: attempt tracking is opt-in for implementation sessions only (the implementation loop passes a flag or sets a variable before calling `claude_session`; `--triage` never opens an attempt). Open the attempt immediately before the actual `claude` invocation (after preflight checks such as the remaining-time budget); usage-limit pauses and retries inside `claude_session` stay part of the same attempt. Close it in `task_outcome`; the EXIT handler logs `timeout` (session exit 124/137), `interrupted` (runner exit 130/143) or `error` for an open attempt. `error` also covers an `ai_limit_pause` beyond `AI_LIMIT_MAX_WAIT` after the attempt opened (one line in the docs, no extra result value). `scripts/lib/workflow.py` `outcome task`: must log even when `.ai/tasks.md` no longer parses (title/category from metadata captured at launch, or a tolerant fallback); genuine write failures stay nonfatal.

Signal behaviour (plan review round 5, P3, probed): bash runs a trapped INT/TERM only after the foreground command returns, and GNU `timeout` puts itself in its own process group, so neither a signal to the runner nor to its group reaches the session; the runner exits 130/143 when the session ends. Document this in the "Outcome log" section of `docs/workflow.md` (Ctrl-C on an interactive `ai-run` lets the session run to its end or limit; the `interrupted` line's time is then, not the keypress). Do not try to change that behaviour here.

Signal test design (bounded, no 30 s sleeps): a new mock mode `MOCK_CLAUDE='hold'` writes its PID to `.ai/local/mock-session.pid`, then waits (poll 0.05 s, at most 10 s) for `.ai/local/mock-release`, then prints an error result and exits 1. The test starts the runner with `subprocess.Popen(..., start_new_session=True)`, polls (at most 10 s) for the PID file, sends the signal to the runner PID only, creates `mock-release`, then `communicate(timeout=20)`; a `finally` kills the mock PID and the runner's process group if still alive. Assert exit 143 (SIGTERM) or 130 (SIGINT) and exactly one new `interrupted` row; the next run's row has the next attempt number. Exit 137: mock mode `self-kill` does `os.kill(os.getpid(), signal.SIGKILL)` (`timeout` returns 137 at once); do not ignore TERM and wait for `--kill-after`.

Malformed queue: the existing test is `test_runner_no_progress_denial_and_error_stop_without_retry` (`bad-format` mode, line ~1084); it runs five modes in one project, so outcome assertions index rows per subtest (filter by task and mode order), not by total count.

Update the "Outcome log" section of `docs/workflow.md` and the vault flow chart `agents-flow.md` (stopped-attempt lifecycle; T001 already did the reviewer policy); the PR description must say "Flow chart updated". New tests named `test_outcome_*`. Reference: `.ai/local/reference/catchup-m1-m2.patch` (opens the attempt too early).

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Timeout, then error, then a successful run log attempts 1, 2, 3 with results timeout, error, done and `first_pass` false for all (test fails without the fix).
- A validation failure logs exactly one `validation_failed` line.
- Exit 137 (`self-kill` mock) is logged as `timeout` (separate case from 124).
- SIGTERM and SIGINT to the runner PID during a `hold` session, per the design above, exit 143/130 within the bounded waits with exactly one `interrupted` line each; the retry is the next attempt; no mock or runner process is left.
- In `test_runner_no_progress_denial_and_error_stop_without_retry`, the `bad-format` session logs exactly one `error`; after repair the retry is attempt 2, `first_pass=false`.
- A run with zero time budget left logs no task outcome.
- Successful and failed `--triage` runs create no task outcome; a usage-limit pause and retry inside one implementation session yields exactly one outcome with the original start time.
- Docs describe the deferred signal delivery and the limit-wait `error` case; vault flow chart updated.

### Validation
`python3 -m unittest tests.test_workflow -k outcome -k runner_no_progress`; `.ai/bin/ai-check`

### Result / notes

## T003 — Crashed attempts are logged at the next start (R2, SIGKILL/power loss)
Status: TODO
Dependencies: T002
Model: sonnet

### Goal
R2: an attempt whose runner dies without its EXIT handler is logged once as `crashed`, so the recovered run is attempt 2 and not a first-time pass.

### Implementation notes
Plan review round 5, P5: the EXIT handler cannot run on SIGKILL, OOM kill or power loss (the watchdog/`ai-recover` path). Host-side attempt marker in the state root (agent sessions cannot write there; `check_state_root`): `<state root>/attempts/<sha16 of checkout root>-<sha16 of branch>.json` (same keying idea as `binding_dir`/`fix_rounds_store`) with task, model, start time and the title/category captured at launch (T002's launch metadata). New `workflow.py` helper `attempt open|close|reconcile`: `open` writes it atomically when T002 opens the attempt; `close` removes it wherever T002 closes the attempt (`task_outcome` and the EXIT handler); `reconcile` runs in `ai-run` right after `ai_lock` (so a live runner's marker is never reconciled; inside `ai-pipeline` the pipeline holds the lock) and, for an orphan marker of this checkout and branch, appends one `crashed` outcome (seconds 0: the end time is unknown; the docs say crashed attempts add no time) and removes the marker. Marker or outcome write failures stay nonfatal (a note on stderr). Docs: "Outcome log" section of `docs/workflow.md` (marker, `crashed`, seconds 0) and the vault flow chart (one node on the start path).

Test: a new mock mode `MOCK_CLAUDE='crash'` SIGKILLs the runner like `triage-crash` does (runner = parent of the mock's parent `timeout`, read from `/proc/<ppid>/stat`), without killing a pipeline. Run `ai-run --approved` with it (expect the kill), then a normal `ai-run --approved`: rows attempt 1 `crashed`, attempt 2 `done`, `first_pass` false, and no marker left. A normal successful run leaves no marker; a second runner refused by the lock (the test holds the checkout lock itself) does not reconcile the first runner's marker. New tests named `test_outcome_crashed_*`.

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- After a SIGKILLed implementation session and a successful rerun, the outcome log has exactly attempt 1 `crashed` and attempt 2 `done` with `first_pass=false`; no attempt marker remains.
- Normal, timeout, error and interrupted attempts (T002 tests) leave no marker and log no extra `crashed` row.
- A runner that fails at `ai_lock` while another holds the lock leaves the other's marker untouched.
- `--triage` never writes a marker.
- Docs and flow chart describe the marker and `crashed`.

### Validation
`python3 -m unittest tests.test_workflow -k outcome -k runner_no_progress`; `.ai/bin/ai-check`

### Result / notes
