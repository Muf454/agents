# Spec: fixes from the Codex catch-up review of the reviewer fallback (M1, M2)

## Objective
Fix the two MAJOR findings of Codex's catch-up review of `0818f20..b98aa66` (PRs #16/#17,
merged 2026-10-07). Report: `.ai/local/reference/catchup-review-b98aa66.md` (ignored copy;
also `~/Projects/agents/.ai/reviews/current.md` on the old branch). Triage by Claude (mission
control) 2026-10-07: M1, M2 accepted; N1–N3 (outcome-report MINORs) deferred to vault backlog
CU-1..3. Zack: development goes through the toolkit pipeline.

## Requirements
- **R1 (M1) Read-only reviewer policy.** The Claude fallback reviewer inherits only project
  `Bash(...)` entries positively known to read or check (read-only file tools; test, lint and
  type-check runners), never interpreters, installers, `bash -c`, `rg` (`--pre` runs commands)
  or builds. `ai-review` passes `--disallowedTools` entries that deny options writing files or
  running programs (`--output`, `-o`, `--ext-diff`, `--textconv`, `git grep -O`, `--fix`,
  `--update`/`-u`, `--coverage`, `git -c`, `git --…`, `>` redirection); deny wins over allow.
  The saved `.allowlist` file lists both. Docs (`docs/workflow.md`) describe it.
- **R2 (M2) Outcome per stopped attempt.** `ai-run` logs exactly one task outcome for a
  session that stops before its result: `timeout` (session exit 124/137), `interrupted`
  (runner exit 130/143), else `error`. A later recovery counts as a further attempt and is
  not a first-time pass. Existing outcomes (`done`, `blocked`, `validation_failed`,
  `no_checkpoint`) stay single.

## Reference
`.ai/local/reference/catchup-m1-m2.patch` is a prototype of both fixes with tests, written by
hand in the mission-control session (not committed, not gated). Its deny rules were checked
live with the Claude CLI in a scratch repo: `git log -1 --output=f` and `git log -1 > f`
denied and nothing written; `git log -1 --oneline` allowed. The implementer may reuse it
after checking it; it is not evidence of correctness.

## Constraints
Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts` or other gate files. The
repo's installed copy picks the fixes up later via `setup-project --upgrade` (Zack approves).
