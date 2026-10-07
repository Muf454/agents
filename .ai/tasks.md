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
Convergence (plan review round 3, P1): stop screening runner arguments. The Claude fallback reviewer inherits NO test, lint, build or other runner commands from the project allowlist (exact or wildcard): like Codex in its read-only sandbox, it relies on the host's validation evidence (`.ai/local/validation.json`, gate logs) and reads code. `scripts/lib/workflow.py` `review_allowlist`: Read/Glob/Grep, the read-only git subcommands, `Edit(./.ai/local/review-probes/**)`, and from the project allowlist only exact or wildcard entries of a fixed set of read-only file tools (`ls`, `cat`, `head`, `tail`, `wc`, `grep`, `pwd`); everything else is dropped. `REVIEW_DENY` (printed by `review-allowlist --deny`, passed as `--disallowedTools`) still denies `--output`, `-o`, `--ext-diff`, `--textconv`, `git grep -O`/`--open-files-in-pager`, `git -c`, `git --…` and any `>` redirection for the git and file-tool entries. `scripts/ai-review` `claude_attempt`: pass `--disallowedTools`, save both lists in the `.allowlist` file. Update `templates/.ai/prompts/claude-review.md` if it tells the reviewer to run tests (it should use the validation evidence), `docs/workflow.md` (reviewer section: no runners, why) and the vault flow chart `agents-flow.md` (reviewer policy; bump its `updated:` date) in this task. Reference: `.ai/local/reference/catchup-m1-m2.patch` and `t001-wip.patch` (both inherit runners: do not copy that part). The live permission-engine check (Claude CLI in a disposable repo) is done by mission control after the task; list the commands to try in the task result.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-review, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Table-driven test seeded with unsafe project entries, exact AND wildcard: `Bash(pytest --basetemp=/outside)`, `Bash(go test -exec /outside ./...)`, `Bash(npx tsc --outDir /outside)`, `Bash(bash -n +n -c "touch /outside")`, `Bash(npm test)`, `Bash(npx vitest run *)`, `Bash(python3 -m unittest *)`, `Bash(npm install *)`, `Bash(rg *)`: none is inherited; `Bash(cat *)`, `Bash(grep *)`, `Bash(ls)` are.
- The reviewer invocation carries the deny list (`--output`, `>`, `git -c`, `--ext-diff`, ...); the reviewer-args test asserts it.
- Vault flow chart shows the reviewer policy; `updated:` bumped.

### Validation
`python3 -m unittest tests.test_workflow -k review_allowlist -k review_policy -k claude_review -k fallback`; `.ai/bin/ai-check`

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
