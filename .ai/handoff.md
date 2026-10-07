# Handoff

## What has been implemented?
Reviewer fallback and model-choice data (`feature/reviewer-fallback`, from master 0818f20),
interactive session 2026-10-07, T001–T007 (see `.ai/tasks.md`):
- `ai-review` (plan, code, re-check): `AI_REVIEWER=auto|codex|claude` (default auto). Auto
  uses Codex and, only on a Codex usage limit (or a missing Codex CLI), a fresh read-only
  `claude -p` reviewer: read-only git, the project's non-writing allowlisted commands,
  writes only in `.ai/local/review-probes/` (verified live: `Edit(./dir/**)` lets Write
  create files there only). Model by risk: claude-fable-5-1 (a task on opus or a risky
  title), else claude-opus-5-5; re-checks claude-opus-5-5; effort high; overrides
  `AI_CLAUDE_REVIEW_MODEL/EFFORT`. Prompt addendum `.ai/prompts/claude-review.md`.
- Every Claude review is labelled in its file, listed in `.ai/reviews/fallback-log.md`
  (committed with the review), named in the PR body.
- Host-side outcome log `<state root>/outcomes.jsonl` (tasks: model, result, attempt,
  first-time pass, seconds; reviews: reviewer, model, findings); `ai-status --outcomes`.
- Watchdog `--diagnosis-agent auto` (default): Codex, then Claude `claude-sonnet-5-5`.

## Validation run
`./scripts/ai-check` (bash -n of scripts + full unittest suite): 244 tests OK in 674 s
(2026-10-07). Live CLI checks: model IDs claude-fable-5-1 / claude-opus-5-5 /
claude-sonnet-5-5 with `--effort high` answered; path-scoped write permission verified.

## Known limitations
- The allowlist is not an OS sandbox: approved test commands run project code. The
  existing "checkout unchanged after review" check and the gate digest still apply.
- Projects get the new scripts/prompt only through `setup-project --upgrade` (after Zack
  inspects the diff); reinstall watchdog timers after upgrading.
- Codex couldn't review this branch: Claude fallback (Fable) bootstrap review; Codex
  catch-up when it has usage (~2026-10-14).

## Manual testing for the human
### Needs you
- Inspect the diff summary and approve upgrading the projects.
- After upgrading a project, watch the first real fallback review (notification "↪ Codex
  usage limit …", label in the review file, row in `.ai/reviews/fallback-log.md`).

### Covered by automated tests
- Fallback at the Codex limit: `test_review_falls_back_to_claude_at_the_codex_limit`
- Model by risk and overrides: `test_claude_reviewer_model_follows_risk_and_overrides`
- AI_REVIEWER codex/claude/config: `test_reviewer_setting_codex_and_claude_only`
- Pipeline on the fallback: `test_pipeline_runs_on_the_claude_fallback_reviewer`, `test_pipeline_fallback_recheck_is_committed_with_the_log`
- Outcome log/report: `test_runner_logs_task_outcomes_and_report`
- Watchdog fallback: `test_watchdog_auto_diagnosis_falls_back_to_claude_sonnet`
