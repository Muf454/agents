# Review dispositions (Claude)

## Plan review round 4 (2026-10-07): BLOCKER 0, MAJOR 1, MINOR 2 — all accepted

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P5 git option abbreviations bypass the deny list | accepted | `git grep --open-files=` (abbreviation) is accepted by git; deny globs can't enumerate abbreviations for any git subcommand. Convergence: the fallback reviewer gets no Bash at all (Read/Glob/Grep); the host prepares diff/log/files context. | T001 |
| P4 targeted tests miss the invocation test | accepted | `-k review_falls_back` added. | T001 |
| P6 README promises runner permissions | accepted | README's fallback reviewer section is in T001. | T001 |


## Plan review round 3 (HEAD e52ed76, 2026-10-07): BLOCKER 0, MAJOR 2, MINOR 2 — all accepted

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 exact runner entries also unsafe | accepted | Third round on the reviewer's runner commands. Convergence: the reviewer inherits no runners at all (exact or wildcard), only read-only file tools; it uses the host's validation evidence like Codex. Tests seeded with unsafe exact and wildcard entries. | T001 |
| P2 triage would open a task attempt | accepted | `claude_session` serves `--triage` too. Attempt tracking is opt-in for implementation; triage and limit-retry regressions added. | T002 |
| P3 flow chart deferred to T002 | accepted | T001 updates the chart for the reviewer policy itself. | T001 |
| P4 targeted tests miss reviewer tests | accepted | Explicit `-k` selection incl. `claude_review`. | T001 |


## Plan review (HEAD 00e644d, 2026-10-07): BLOCKER 0, MAJOR 3, MINOR 2 — all accepted, tasks revised

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 retained runners keep write/exec options | accepted | `pytest --junitxml`, `go test -exec`, `tsc --noEmit false` pass the reference policy. T001 now enumerates runners and dangerous forms with a table-driven test; wildcards only where all are denied; live check by mission control. | T001 |
| P2 outcome logging needs a parseable queue | accepted | `outcome task` reads titles via `tasks()`. T002 makes it tolerant + malformed-queue test. | T002 |
| P3 no interruption test | accepted | SIGINT/SIGTERM subprocess tests and a separate 137 case added to T002. | T002 |
| P4 attempt opened before launch | accepted | Attempt now opens right before the invocation; zero-budget case. | T002 |
| P5 flow chart | accepted | Vault `agents-flow.md` update and "Flow chart updated" in T002. | T002 |


Review HEAD: 26463f1d086fe05bbd734ca884066b54a81c592a

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| N1 | accepted | Reproduced: `bash *`/`node *`/`npx *`/`npm run *`/`tee *` passed the old keyword filter. Now dropped (writers/runners by first word, open interpreters by pattern); allowlist saved per review; README no longer overstates it. Test `test_review_allowlist_keeps_only_read_and_check_commands` extended. | T008 |
| N2 | accepted | `claude-text` now appends reviewer denials to `.ai/local/review-denials.log` and prints the count. Test `test_claude_review_denials_and_allowlist_are_recorded`. | T008 |
| N3 | accepted | Reproduced false positives ("author", "Lockfile", "Race results"); whole-word patterns now, negative and positive cases in `test_review_risk_helper`. | T008 |
| N4 | accepted | PR note now quotes the label reason; forced reviews are labelled "Claude (… AI_REVIEWER=claude)"; the report lists every Claude-written review like the fallback log does. Tests in the pipeline and outcome tests. | T008 |
| N5 | accepted | Vault updated in this session: hub Decision + Log lines, human todo "Codex catch-up review" dated ~2026-10-14 (interactive session, so the author edits the vault directly). | T008 |

Other notes from the review:
- Invalid `AI_REVIEWER` in `ai-pipeline`: accepted, validated at the argument check (`test_pipeline_rejects_an_invalid_reviewer_setting_first`).
- `ai-run` doesn't tolerate a dirty fallback log while `ai-pipeline` does: rejected as a change. Inside the pipeline `ai-run` only starts after `reconcile_disputes`/review records committed the log; a hand-run `ai-run` with uncommitted review records should stop, as for any other record.
- One "↪ Codex usage limit" notification per review step: deferred (minor noise; once-per-run needs manifest state).
- Missing coverage added: Claude review failure and a reviewer writing outside the probe dir keep the prior review (`test_claude_review_failure_or_write_keeps_the_prior_review`); watchdog `--diagnosis-agent codex` never falls back (`test_watchdog_codex_diagnosis_does_not_fall_back`). Not added: Claude limit beyond `AI_LIMIT_MAX_WAIT` and a reviewer timeout; both use the shared `ai_limit_pause`/exit-124 handling already tested for Codex and the runner.
- `--diagnosis-agent claude` now uses `AI_DIAGNOSIS_MODEL` (default claude-sonnet-5-5) instead of `AI_MODEL`: intended (R3), documented.
