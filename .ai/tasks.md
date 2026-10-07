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
`scripts/lib/workflow.py` `review_allowlist`: replace the drop filters (`REVIEW_DROP_FIRST`, `REVIEW_DROP_OPEN`) with a positive `REVIEW_KEEP` list; add `REVIEW_DENY` printed by `review-allowlist --deny`. `scripts/ai-review` `claude_attempt`: pass `--disallowedTools` and save both lists in the `.allowlist` file. Update `docs/workflow.md` (reviewer section). Reference: `.ai/local/reference/catchup-m1-m2.patch` (its KEEP list is too broad, see plan review P1). Enumerate each runner the reviewer may inherit and its writing/executing/emitting options (e.g. `pytest --junitxml/--basetemp/-p`, `go test -exec/-o/-coverprofile`, `tsc --noEmit false/--outDir/--build`, `vitest --outputFile/-u/--coverage/--reporter=…`, `npm test -- …` passing them through), including attached values (`--opt=value`, `-ovalue`). A wildcard entry is inherited only for runners whose dangerous options are all denied by `REVIEW_DENY` patterns; otherwise inherit only exact (no-wildcard) entries of that runner or drop it. Keep the trusted-project-code limitation stated in the docs. A first T001 session (2026-10-07, on the pre-#18 serial gate) left uncommitted work, saved as `.ai/local/reference/t001-wip.patch` (unvalidated; reuse after checking). The live permission-engine check (Claude CLI in a disposable repo) is done by mission control after the task, not by the session; list the commands to try in the task result.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-review, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `python3 -c *`, `bash -c *`, `rg *`, `npm install *`, `npm run build`, `npx eslint *` are not inherited; `npm test`, `npx vitest run *`, `npm run lint`, `python3 -m unittest *`, `cat *` are.
- The reviewer invocation carries the deny list (`--output`, `>`, `git -c`, `--ext-diff`, ...); the reviewer-args test asserts it.
- A table-driven test: for every inherited runner, each enumerated dangerous form (`pytest --junitxml=/x`, `go test -exec /x ./...`, `npx tsc --noEmit --noEmit false`, `npx vitest run --outputFile=/x`, ...) is either not allowed by any inherited entry or matched by a deny pattern (fnmatch of the Claude glob), and the safe forms stay allowed.

### Validation
targeted tests (`-k review_allowlist -k fallback`); `.ai/bin/ai-check`

### Result / notes

## T002 — Outcome logged for stopped task attempts (M2)
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
R2: error, timeout and interruption attempts appear in the outcome log exactly once.

### Implementation notes
`scripts/ai-run`: open the attempt immediately before the actual `claude` invocation (after preflight checks such as the remaining-time budget); usage-limit pauses and retries inside `claude_session` stay part of the same attempt. Close it in `task_outcome`; the EXIT handler logs `timeout` (session exit 124/137), `interrupted` (runner exit 130/143) or `error` for an open attempt. `scripts/lib/workflow.py` `outcome task`: must log even when `.ai/tasks.md` no longer parses (title/category from metadata captured at launch, or a tolerant fallback); genuine write failures stay nonfatal. Update the "Outcome log" section of `docs/workflow.md` and the vault flow chart `agents-flow.md` (stricter reviewer policy from T001 and the stopped-attempt lifecycle); the PR description must say "Flow chart updated". Reference: `.ai/local/reference/catchup-m1-m2.patch` (opens the attempt too early, see P4).

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Timeout, then error, then a successful run log attempts 1, 2, 3 with results timeout, error, done and `first_pass` false for all (test fails without the fix).
- A validation failure logs exactly one `validation_failed` line.
- Exit 137 is logged as `timeout` (separate case from 124).
- SIGINT and SIGTERM to a runner with an active session (subprocess test, bounded waits, child cleanup) exit 130/143 with exactly one `interrupted` line; the retry is the next attempt.
- A session that leaves `.ai/tasks.md` unparseable (existing malformed-queue test) logs exactly one `error`; after repair the retry is attempt 2, `first_pass=false`.
- A run with zero time budget left logs no task outcome.
- Vault flow chart updated.

### Validation
targeted tests; `.ai/bin/ai-check`

### Result / notes
