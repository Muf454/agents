# Task queue

Branch `fix/catchup-review`: fixes for the Codex catch-up review M1/M2 (see `.ai/project-spec.md`).
Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts` or other gate files.

## T001 — Read-only Claude reviewer policy (M1)
Status: TODO
Dependencies: none
Model: opus

### Goal
R1: the fallback reviewer cannot write outside the probe directory through allowed Bash commands.

### Implementation notes
Convergence (plan review rounds 1–4 all found new command-argument routes: runner options, exact entries, git option abbreviations such as `git grep --open-files=`): the Claude fallback reviewer gets NO Bash tool at all. `scripts/ai-review` `claude_attempt` runs it with `--tools Read,Glob,Grep` only (no Bash, Edit or Write; no probe directory), and the host prepares the git context it used to fetch itself: before the session, write into `.ai/local/review-context/` (recreated per review, removed afterwards like the probe dir) `diff.patch` (`git diff <merge-base>..<head>`, or the plan files for plan review), `log.txt` (`git log --stat <merge-base>..<head>`), `files.txt` (changed paths) and, for rechecks, the finding text; the prompt names these files and the validation evidence (`.ai/local/validation.json`, gate logs). `scripts/lib/workflow.py` `review_allowlist` becomes just `Read`, `Glob`, `Grep` (keep the helper so the saved `.allowlist` file and tests stay meaningful; drop `REVIEW_DENY`/`--deny`). The checkout-unchanged check stays. Update `templates/.ai/prompts/claude-review.md` (no commands; use the prepared context and validation evidence), README's "Claude fallback reviewer" section (P6: it promises inherited `npm test`/vitest and probes), `docs/workflow.md` (reviewer section: no Bash, host-prepared context, why), and the vault flow chart `agents-flow.md` (reviewer policy; bump `updated:`) in this task. Reference patches inherit runners and Bash: do not copy that part. Mission control runs a live check with the Claude CLI afterwards (reviewer cannot run any Bash command); list it in the task result.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-review, templates/.ai/prompts/claude-review.md, README.md, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- The reviewer invocation (mock args) has `--tools Read,Glob,Grep`, no `--allowedTools` Bash/Edit entries, and no probe directory; a project allowlist full of runners (exact and wildcard, incl. `Bash(git grep *)`, `Bash(pytest --basetemp=/x)`, `Bash(npm test)`) changes nothing.
- The review context files exist during the session (mock reviewer reads them) for code, plan and recheck modes, and are removed afterwards; a review still publishes and binds as before.
- README, docs, prompt and flow chart describe the same policy.

### Validation
`python3 -m unittest tests.test_workflow -k review_allowlist -k claude_review -k review_falls_back -k fallback`; `.ai/bin/ai-check`

### Result / notes

## T002 — Outcome logged for stopped task attempts (M2)
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
R2: error, timeout and interruption attempts appear in the outcome log exactly once.

### Implementation notes
`scripts/ai-run`: attempt tracking is opt-in for implementation sessions only (the implementation loop passes a flag or sets a variable before calling `claude_session`; `--triage` never opens an attempt, P2). Open the attempt immediately before the actual `claude` invocation (after preflight checks such as the remaining-time budget); usage-limit pauses and retries inside `claude_session` stay part of the same attempt. Close it in `task_outcome`; the EXIT handler logs `timeout` (session exit 124/137), `interrupted` (runner exit 130/143) or `error` for an open attempt. `scripts/lib/workflow.py` `outcome task`: must log even when `.ai/tasks.md` no longer parses (title/category from metadata captured at launch, or a tolerant fallback); genuine write failures stay nonfatal. Update the "Outcome log" section of `docs/workflow.md` and the vault flow chart `agents-flow.md` (stopped-attempt lifecycle; T001 already did the reviewer policy); the PR description must say "Flow chart updated". Reference: `.ai/local/reference/catchup-m1-m2.patch` (opens the attempt too early, see P4).

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Timeout, then error, then a successful run log attempts 1, 2, 3 with results timeout, error, done and `first_pass` false for all (test fails without the fix).
- A validation failure logs exactly one `validation_failed` line.
- Exit 137 is logged as `timeout` (separate case from 124).
- SIGINT and SIGTERM to a runner with an active session (subprocess test, bounded waits, child cleanup) exit 130/143 with exactly one `interrupted` line; the retry is the next attempt.
- A session that leaves `.ai/tasks.md` unparseable (existing malformed-queue test) logs exactly one `error`; after repair the retry is attempt 2, `first_pass=false`.
- A run with zero time budget left logs no task outcome.
- Successful and failed `--triage` runs create no task outcome; a usage-limit pause and retry inside one implementation session yields exactly one outcome with the original start time.
- Vault flow chart updated.

### Validation
targeted tests; `.ai/bin/ai-check`

### Result / notes
