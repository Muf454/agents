<!-- Host evidence: HEAD 26463f1d086fe05bbd734ca884066b54a81c592a; merge-base 0818f20c4d236072815e24552ba779e058c7e1f0; saved 2026-10-07T16:12:48Z. -->

> **Reviewer: Claude fallback (claude-fable-5-1, effort high; Codex usage limit; bootstrap review run by hand with the templates' prompts). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

# Independent review

Overall verdict: PROCEED WITH MINOR FIXES. The reviewer fallback, its records and bindings, the pipeline commits, the outcome log and the watchdog fallback match the spec and the traced code paths; the remaining issues are localized (allowlist breadth, denied-tool logging, false-positive risk words, wording in records, a missing human-todo entry).
Finding counts: BLOCKER=0 MAJOR=0 MINOR=5

Reviewed HEAD: `26463f1d086fe05bbd734ca884066b54a81c592a` (branch `feature/reviewer-fallback`, one commit)
Supplied base: `master`; merge-base: `0818f20c4d236072815e24552ba779e058c7e1f0`

Inspected: `AGENTS.md`, `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`, `.ai/state.md`, `.ai/handoff.md`, `.ai/permissions.allow`, `.claude/settings.json`, the full `git diff 0818f20..26463f1` (scripts, lib, templates, tests, docs, records), the actual source of `scripts/ai-review`, `scripts/ai-pipeline`, `scripts/ai-run`, `scripts/ai-recover`, `scripts/lib/workflow.py`, `scripts/lib/watchdog.py`, `scripts/lib/common.sh`, the vault notes `agents.md`, `agents-flow.md`, `agents-human-todo.md`, `agents-backlog.md`. The checkout was clean.

Validation observed/run:
- Stored evidence `.ai/local/validation.json`: PASS, exit 0, 2026-10-07T16:03:30Z, `unchanged: true`, recorded with HEAD `0818f20` (the dirty tree before the single commit; the fingerprint binds the content, and the host accepted it for this review). Its log `.ai/local/check-nrMLDYV5.log` ends with `Ran 244 tests in 674.490s / OK`.
- Run by me: `python3 -m unittest tests.test_workflow -k review_falls_back_to_claude -k claude_review_usage_limit -k recheck_falls_back -k reviewer_setting_codex -k watchdog_auto_diagnosis` → 5 tests OK in 11 s.
- Run by me: 5 scenario probes in `.ai/local/review-probes/probe_test.py` against the real `workflow.py` functions (`RISK_TITLE`, `review_allowlist`, the `pr_body` label regex, `limit_check`, `outcomes_report`); output quoted in the findings below.

Limitations: the full `./scripts/ai-check` gate (674 s) was not rerun (over the tool time limit; evidence above is content-bound). No live `claude`/`codex` call was made, so the live claim that `Edit(./.ai/local/review-probes/**)` confines the Write tool was not re-verified here. Two of my shell commands were denied by the reviewer allowlist (a `sed … | diff` pipe and a vault `ls && grep` chain); I used the Read/Grep tools instead. No project files were written; the probe directory is removed by the host.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

Traced and found correct: `run_review` loop (Codex first in `auto`/`codex`; limit → pause in `codex`, fallback in `auto`; non-limit Codex errors die; Claude limit → `ai_limit_pause Claude` then Codex again; `unchanged()` checked after the pause and after the review); `claude_attempt` (probe dir recreated/removed, `--strict-mcp-config`, `--setting-sources project`, stdin `/dev/null`, exit 124/137 never treated as a limit); `review_records` after publish (label in file, `fallback-record` row, outcome line); pipeline `review_record()` committing `fallback-log.md` with plan/review records and `reconcile_disputes` with the re-check; `RECHECK_RECORDS` and `review_current()` tolerate the log; `ai-recover` restores the four new settings (`test_recovery_restores_the_approved_runs_settings` compares both lists with `RUN_SETTINGS`); `setup-project --upgrade` CREATEs `.ai/prompts/claude-review.md` because `.ai/prompts/` is a toolkit group; `diagnose()` auto path keys on the `Diagnosis unavailable` prefix. The deny rules in `.claude/settings.json` do not cover `.ai/local/`, so probes are possible.

## MINOR findings

### N1 — The reviewer allowlist filter is a keyword denylist; broad interpreter and `tee` entries pass through unchanged (demonstrated for the filter, suspected for impact)
- Location: `scripts/lib/workflow.py:585-603` (`review_allowlist`), documented in `README.md` "Claude fallback reviewer" ("allowed only to read, run read-only git and the project's own approved check commands … write scratch probes under …").
- Problem: entries are dropped only when the command starts with `git|sudo|rm|mv|cp|chmod|chown|curl|wget|ssh|scp` or contains `ai-task|ai-check|ai-run|ai-pipeline|.ai/validate|push|deploy|supabase|vercel`. Anything else is kept verbatim.
- Evidence (probe, permissions.allow with typical project entries):
  ```
  ALLOWLIST: [..., 'Bash(npx *)', 'Bash(node *)', 'Bash(python3 *)', 'Bash(bash *)', 'Bash(npm run *)', 'Bash(echo *)', 'Bash(tee *)']
  ```
  `Bash(tee *)` is a pure write command. `Bash(bash *)`, `Bash(python3 *)`, `Bash(node *)` and `Bash(npx *)` let the reviewer run arbitrary code, including `bash -c 'git push …'`, which the `.claude/settings.json` deny rule `Bash(git push *)` does not match. Writes outside the checkout (host state root, bindings) are not caught by the "checkout unchanged" check. This repo's own allowlist gives the reviewer `Bash(echo *)`; whether Claude Code permits a file redirect (`echo … > .ai/local/validation.json`) under that rule was not verified here (suspected).
- Impact: the review-integrity model (an independent read-only reviewer) depends on each project's `permissions.allow` being conservative; the docs state it as a property of the toolkit. Low likelihood (the reviewer is instructed not to), but the fallback runs unattended at night.
- Direction: also drop entries whose command is a bare shell/interpreter/package runner with a wildcard (`bash *`, `sh *`, `python3 *`, `node *`, `npx *`, `npm run *` without a fixed script) and known writers (`tee`, `dd`, `install`, `truncate`, `sed`), or whitelist only entries that match `Bash(<fixed check command> …)`; print the resulting allowlist into the review log so the human can see what the reviewer got; soften the README claim accordingly. Add a test with such entries.

### N2 — Denied tool calls of the Claude reviewer are not logged (demonstrated by trace)
- Location: `scripts/lib/workflow.py:570-577` (`claude_text` calls `claude_result(source, check_only=True)`); `claude_result` writes `.ai/local/denials.log` only when `check_only` is false.
- Problem: for the reviewer, denied attempts are exactly the audit signal the human wants ("the reviewer tried to write/run X"), and they are silently dropped. During this review two of my own commands were denied; nothing records that.
- Impact: no visibility into reviewer behaviour at the boundary, in contrast to runner sessions.
- Direction: log the reviewer's `permission_denials` (to `.ai/local/denials.log` or a `review-denials.log`) and mention the count in the `ai-review` summary line and the outcome record. One unit test with a mocked `permission_denials` list.

### N3 — `RISK_TITLE` escalates to Fable on unrelated words (demonstrated)
- Location: `scripts/lib/workflow.py:1797-1799`; same wording in `README.md` and `docs/workflow.md`.
- Evidence (probe):
  ```
  'Add author column to notes': True   (\bauth matches "author")
  'Lockfile update': True              (\block matches "Lockfile")
  'Authoring guide for docs': True
  'Race results page': True
  ```
- Impact: cost only (claude-fable-5-1 instead of claude-opus-5-5 draws from the shared Claude Max allowance the spec is trying to protect); never a safety downgrade. R3 says "a task title naming RLS, auth, …", which these titles do not.
- Direction: anchor the words (`\bauth(?:n|z|entication|orization|orisation)?\b`, `\block(?:s|ing|ed)?\b`, `\brace(?:s)?\b` only with "condition"/"data race"), and add negative cases to `test_review_risk_helper`.

### N4 — Fallback wording hard-codes "Codex was at its usage limit" and "Claude fallback" for every reason, and the report's catch-up list ignores forced Claude reviews (demonstrated)
- Locations: `scripts/lib/workflow.py:2144-2148` (`pr_body` NOTE text), `scripts/ai-review:158-159` (`AI_REVIEW_BY`/`AI_REVIEW_LABEL` always say "Claude fallback"), `scripts/lib/workflow.py:1967` (`reviewer == 'claude-fallback'` filter).
- Evidence (probes): the PR-body regex extracts the model for all three reasons but the reason is unused, so with `AI_REVIEWER=claude` or a missing Codex CLI the PR says "Codex was at its usage limit". The outcomes report lists only `claude-fallback` rows under "Claude-only reviews (Codex catch-up pending)", while `fallback_record` writes `AI_REVIEWER=claude` reviews into `.ai/reviews/fallback-log.md` (asserted by `test_reviewer_setting_codex_and_claude_only`):
  ```
  | claude          | claude-opus-5-5 | code | 1 | …
  | claude-fallback | claude-opus-5-5 | code | 1 | …
  ## Claude-only reviews (Codex catch-up pending)
  - t p b code HEAD def (claude-opus-5-5)        <- only the fallback row
  ```
- Impact: an inaccurate statement in a published PR; the two catch-up lists (file vs report) disagree, so R7's "list of Claude-only reviews awaiting the Codex catch-up" is incomplete when Claude was forced.
- Direction: carry the reason into the PR note (it is already in the label's parenthesis); label forced reviews "Claude (AI_REVIEWER=claude)"; include `reviewer in ('claude', 'claude-fallback')` in the report list, or exclude forced reviews from `fallback-log.md`, but make the two agree. Tests for a non-limit reason in `pr_body` and for the report list.

### N5 — Requirement R5's human todo and the vault's dated records for this change are missing (demonstrated)
- Requirement: R5 "Codex does ONE catch-up review of all Claude-only-reviewed work when back (human todo with the date)"; `~/.claude/CLAUDE.md` ("Things only I can do or decide go in `<project>-human-todo.md`"; "After meaningful changes: update … dated decisions … and a log entry").
- Evidence: `20 Projects/agents/agents-human-todo.md` has no catch-up item (grep for `catch-up|catch up|fallback`: no match). `agents.md` has no 2026-10-07 Log line and no Decision for the reviewer fallback; `agents-flow.md` (updated 2026-10-07) is the only vault note touched. Backlog safety notes OR-21 "no silent fallback" and OR-25 "no automatic fallback on quota exhaustion" are now qualified by this change (labelled, bounded fallback for the reviewer role) without a recorded decision saying so.
- Impact: the catch-up review (the control that compensates for a Claude-only review) has no owner or date; the vault and the toolkit disagree on the fallback policy.
- Direction: add the open human-todo "Codex catch-up review of `.ai/reviews/fallback-log.md` entries (Codex usage back ~2026-10-14)", a dated Decision line ("2026-10-07: reviewer role falls back to a read-only Claude session at the Codex limit; labelled, logged, catch-up by Codex; implementer never falls back"), and a Log line. Interactive session, so the author may tick/add directly.

## Missing test coverage
- Claude reviewer hard failure: the mock supports `MOCK_CLAUDE_REVIEW=error` (exit 3) but no test uses it; the "Claude review failed (exit N); prior review preserved" path and the preservation of `.ai/reviews/current.md` are untested.
- A reviewer that writes outside the probe directory: the mock only writes `probe.txt` inside `.ai/local/review-probes/`; no test shows the Claude path dying with "Checkout changed during review" and leaving the prior review intact.
- Claude limit beyond `AI_LIMIT_MAX_WAIT` on the review path, and a Claude review timeout (exit 124) → die, not pause.
- `review-allowlist` with broad entries (N1) and `review-risk` negative cases (N3).
- `pr_body` with a non-limit fallback reason; `outcomes-report` with `reviewer=claude` rows (N4).
- Watchdog `--diagnosis-agent codex` when Codex fails (must not fall back; the task notes claim "codex/claude choices unchanged" but only the success path is tested). Note also that `--diagnosis-agent claude` no longer honours `AI_MODEL` (now `AI_DIAGNOSIS_MODEL`): intended per R3, documented, but a behaviour change for existing timers.
- Checklist items checked for this change (the guild/RLS items do not apply to this toolkit): irreversible operations (host commits stage explicit paths; `rm -rf` limited to the probe dir), resume paths (crash between review and host commit falls into the existing dirty-checkout → recovery path; no new state), attribution (label and fallback row are written by the host after publish, bound by `bind_review`).

## Security concerns
- The reviewer's write boundary rests on Claude Code permission rules plus the project allowlist (N1) and on the "checkout unchanged" check, which does not see writes to ignored paths or outside the checkout. The README says so for the gate; the "allowed only to read …" sentence overstates it.
- Reviewer denials are invisible (N2).
- The Read tool is not path-scoped: the reviewer can read files outside the checkout (as can Codex's read-only sandbox); unchanged by this branch, worth a sentence in the docs.
- `limit_check` treats any failed Claude run whose text matches "try again later", "429" or "rate limit" as a usage limit (probe: an "Internal server error. Please try again later." result → limit, reset 0 → 1800 s pause and retry, bounded by `AI_LIMIT_MAX_WAIT`). Same heuristic as the pre-existing Codex path; acceptable, noted.

## Architecture concerns
- `ai-pipeline` tolerates a dirty `.ai/reviews/fallback-log.md` at start (`:!.ai/reviews/fallback-log.md`) but `ai-run` (`scripts/ai-run:66`) does not; the state is practically unreachable (every writer also dirties `current.md`/`plan.md`/`recheck.md`), so this is a latent inconsistency rather than a bug. Either drop the exclusion or make `ai-run`'s check match.
- `AI_REVIEWER` is validated in `ai-review` only; `ai-pipeline` with an invalid value runs setup and dependency steps before stopping at the plan review. Cheap to validate at the pipeline's argument check.
- `fallback_notified` is per `ai-review` process, so a pipeline run notifies "↪ Codex usage limit" once per review step (plan, review, re-check, re-review). Acceptable, but could be once per run via the manifest.
- The label line is prepended under the host header and included in the binding, so an edited label invalidates the review like any other edit. Good.

## Manual testing recommendations

### Needs you
- After `setup-project --upgrade --apply` on one project, run `AI_REVIEWER=claude .ai/bin/ai-review --base <ref>` once and inspect `.ai/local/review-*.claude.json` for `permission_denials`; confirm the reviewer could write only under `.ai/local/review-probes/` (N1/N2 are about what you cannot currently see).
- Inspect the generated `--allowedTools` list (`python3 .ai/bin/lib/workflow.py review-allowlist`) in raid-planner and family-planner before the first unattended fallback review.
- Add the catch-up human todo and the decision/log lines in the vault (N5); when Codex has usage, run the catch-up review over the fallback-log entries and record the outcome in the log file.
- Reinstall watchdog timers after upgrading so `--diagnosis-agent auto` applies.

### Covered by automated tests
- Codex limit → Claude review, label, fallback row, outcome line, probe dir removed: `test_review_falls_back_to_claude_at_the_codex_limit`
- Model by risk and overrides: `test_claude_reviewer_model_follows_risk_and_overrides`, `test_review_risk_helper`
- `AI_REVIEWER` codex/claude/config, no fallback on other Codex errors: `test_reviewer_setting_codex_and_claude_only`, `test_codex_usage_limit_pauses_then_retries`
- Claude limit pause then Codex first: `test_claude_review_usage_limit_pauses_then_retries_codex_first`
- Plan review and re-check on the fallback, committed with the log: `test_plan_review_and_recheck_fall_back_to_claude`, `test_recheck_falls_back_to_claude`
- Pipeline end to end on the fallback, PR body note, missing Codex CLI: `test_pipeline_runs_on_the_claude_fallback_reviewer`, `test_pipeline_fallback_recheck_is_committed_with_the_log`, `test_pipeline_without_codex_cli_uses_claude`
- Allowlist filter (current keywords): `test_review_allowlist_keeps_only_read_and_check_commands`
- Outcome log and report: `test_runner_logs_task_outcomes_and_report`, `test_runner_logs_blocked_and_failed_validation_attempts`
- Watchdog auto fallback: `test_watchdog_auto_diagnosis_falls_back_to_claude_sonnet`
- Recovery settings list stays in sync: `test_recovery_restores_the_approved_runs_settings`
- Should be added: the gaps listed under "Missing test coverage".

## Pre-existing defects (not introduced by this branch)
- `limit_check`'s broad `LIMIT_TEXT` heuristic (above) already applied to Codex.
- `Bash(echo *)` in this repo's `permissions.allow` may permit file redirects for the implementer; now inherited by the reviewer (N1, suspected).
- The Read tool is not path-scoped for any Claude session.
