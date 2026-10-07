# Spec: Reviewer fallback and model-choice data

## Objective
Reviewer fallback and model-choice data: when Codex is at its usage limit, reviews fall
back to a read-only headless Claude reviewer instead of pausing for days; every task and
review outcome is logged so the risk-based model rules can be tuned from data.

Source: Zack's brief of 2026-10-07 (interactive session). Codex is out of usage until about
2026-10-14; today `ai-review` would pause on its limit (and stop when the reset is beyond
`AI_LIMIT_MAX_WAIT`). Zack is on Claude Max 5x: Claude reviews draw from the same allowance
as implementation, so the fallback is used only when Codex can't review (or when forced).

## Requirements
### Goal 1: reviewer fallback
- R1 `ai-review` (plan, code and recheck modes) uses Codex first. When Codex reports a usage
  limit (the existing `limit-check` detection), it falls back to a headless Claude review
  instead of pausing. Codex is tried again on every later review (no sticky state).
  Setting `AI_REVIEWER=auto|codex|claude` (default `auto`): `codex` keeps today's pause
  behaviour, `claude` skips Codex. Settable in the user config and kept by recovery.
- R2 The Claude reviewer is a fresh `claude -p` session: tools Read, Grep, Glob, Bash, Write;
  allowed: read-only git commands, the project's own allowlisted test/check commands (from
  `.ai/permissions.allow`, minus writes: Edit/Write, git add/commit/rm/mv, ai-task,
  ai-check/validate), and Write/Edit only under `.ai/local/review-probes/` (scratch probes,
  ignored, removed afterwards). No MCP, project setting sources only, stdin /dev/null. It
  returns the review as its final text; the host saves it through the same publish helpers,
  so the format, file locations and bindings are unchanged (findings, dispositions,
  re-checks and disputes keep working). The existing "checkout changed during review" check
  stays and covers Claude too.
- R3 Reviewer model by risk: `claude-fable-5-1` for plan and code reviews of risky work,
  `claude-opus-5-5` for other plan/code reviews and all re-checks, effort `high`.
  Risky = any task with `Model: opus` (the planning rules already put RLS/permissions,
  auth, locking/concurrency, data-moving migrations and irreversible operations there), or
  a task title naming RLS, auth, permissions, locks/concurrency, migrations, deletion or
  irreversible operations. Overrides: `AI_CLAUDE_REVIEW_MODEL`, `AI_CLAUDE_REVIEW_EFFORT`.
  Watchdog diagnosis: `--diagnosis-agent auto` (new default) uses Codex and falls back to
  Claude on any Codex failure; the Claude diagnosis runs on `claude-sonnet-5-5`
  (`AI_DIAGNOSIS_MODEL`). Model IDs and `--effort` were verified live with CLI 2.1.291.
- R4 A stricter Claude review prompt (`.ai/prompts/claude-review.md`, appended to the mode
  prompt): sceptical, don't trust handoff notes or DONE labels, prove findings with
  scenario probes (e.g. real migrations in the project's in-memory PGlite test setup,
  small scripts against the code), and a checklist of past failure types: lock order and
  deadlocks; account/user deletion with FK cleanup and triggers; attribution/timestamp
  spoofing; stale async results; realtime/refresh wiring; cross-guild/tenant isolation;
  who may do what per role; data hidden from views (e.g. assignments to non-mains);
  main/alt identity changes.
- R5 Every fallback review is labelled in its file ("Reviewer: Claude fallback (model,
  effort) …") and appended to `.ai/reviews/fallback-log.md` (date, mode, branch, HEAD,
  base, model, effort, reason), committed with the review. The PR body names a fallback
  review. Codex does ONE catch-up review of all Claude-only-reviewed work when back (human
  todo with the date).

### Goal 2: model choice data
- R6 Per-task outcome log: one JSON line per task attempt in a host-side file
  (`$AI_STATE_DIR/outcomes.jsonl`, outside every checkout, so agents can't edit it and one
  report covers all projects): time, project, branch, task, title, category, model, result
  (done/blocked/validation_failed), attempt number, first-time pass, duration. Review
  events go to the same file: mode, reviewer (codex/claude-fallback/claude), model, effort,
  finding counts by severity, duration.
- R7 `ai-status --outcomes` prints first-pass rate, attempts and duration per model and per
  category, and reviews/findings per reviewer and model, plus the list of Claude-only
  reviews awaiting the Codex catch-up.
- R8 The reviewer model is chosen by the same risk rules (R3) and logged (R6).
- No external routing library. Existing risk rules stay as they are.

## Out of scope
- Upgrading other projects (done after Zack inspects the diff, via `setup-project --upgrade`).
- Codex as implementer; automatic model escalation in the runner.

## Constraints
- Gate files of this repo (`.ai/bin`, `.ai/prompts`, `.ai/validate`, …) are not edited;
  changes go to `scripts/`, `templates/`, `tests/`, docs.
- Tests for every script change; `./scripts/ai-check` passes.
- Codex can't review this change: once the fallback works, the Claude fallback (Fable)
  reviews it; findings get dispositions; Codex catch-up later.
