# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files of this repo. Source: Zack's brief of 2026-10-07
(reviewer fallback while Codex is out of usage; model-choice data). Interactive session
(Claude as implementer); Codex can't review it, so the Claude fallback reviewer (Fable)
reviews the branch once T002 works; Codex catch-up later. Every task leaves
`./scripts/ai-check` passing. Flow-chart rule: T007 updates the vault `agents-flow.md`.

## T001 — Risk, label, fallback-log and outcome helpers
Status: DONE
Dependencies: none
Model: opus

### Goal
workflow.py building blocks for R3, R5, R6, R7 (spec).

### Implementation notes
- `review-risk`: `high <reason>` if any task has `Model: opus` or a title naming RLS, auth, permissions, locks/concurrency, migrations, deletion or irreversible operations; else `normal`.
- Publish helpers add a visible reviewer label line when `AI_REVIEW_LABEL` is set (review, plan review, re-check title).
- `fallback-record MODE MODEL EFFORT HEAD BASE`: append a row to `.ai/reviews/fallback-log.md` (creates the table).
- `outcome task|review ...`: append one JSON line to `$state_root/outcomes.jsonl` (host-side, never fatal to callers); `outcomes-report`.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Unit tests cover risk classification, label, fallback log rows, outcome lines and the report.

### Validation
targeted tests; ./scripts/ai-check

### Result / notes
DONE 2026-10-07: workflow.py `review-risk`, `reviewer_label` (AI_REVIEW_LABEL/AI_REVIEW_BY), `fallback-record`, `outcome`, `outcomes-report`, `claude-text`, `review-allowlist`; RUN_SETTINGS and RECHECK_RECORDS extended. Tests: review_risk_helper, review_allowlist_*, runner_logs_* (report).
Validation: ./scripts/ai-check 244 tests OK (2026-10-07, 674 s).

## T002 — ai-review: Claude fallback reviewer
Status: DONE
Dependencies: T001
Model: opus

### Goal
R1, R2, R3, R5, R8: Codex first, Claude fallback on the Codex limit, AI_REVIEWER setting.

### Implementation notes
- `AI_REVIEWER=auto|codex|claude` (default auto); `codex` keeps the pause; `claude` skips Codex; auto falls back on `limit-check` (never on other Codex errors).
- `claude_review()`: tools Read,Glob,Grep,Bash,Write; allowlist = read-only entries of `.ai/permissions.allow` + `Edit(./.ai/local/review-probes/**)`; output-format json; result text -> report; Claude limit -> `ai_limit_pause Claude` then retry (Codex first again in auto).
- Model: re-check opus 5.5; plan/code by `review-risk` (fable 5.1 / opus 5.5); effort high; overrides `AI_CLAUDE_REVIEW_MODEL/EFFORT`.
- Label, fallback log, review outcome line. Config/recovery settings lists.

### Likely affected modules
scripts/ai-review, scripts/lib/common.sh, scripts/ai-recover, scripts/lib/workflow.py, tests

### Acceptance criteria
- Codex limit in auto -> Claude review saved with label + fallback log row; codex mode still pauses; claude mode never calls Codex; recheck works with Claude; a Claude limit pauses.

### Validation
targeted tests; ./scripts/ai-check

### Result / notes
DONE 2026-10-07: ai-review `run_review` (AI_REVIEWER auto|codex|claude), `claude_attempt` (read-only allowlist, probe dir, model by risk, Claude limit pause then Codex first again), label + fallback log + outcome line; config/recovery settings. Tests: review_falls_back_*, claude_reviewer_model_*, reviewer_setting_*, claude_review_usage_limit_*, plan_review_and_recheck_*, recheck_falls_back_*; existing Codex limit test now runs with AI_REVIEWER=codex.
Validation: ./scripts/ai-check 244 tests OK (2026-10-07, 674 s).

## T003 — Stricter Claude review prompt
Status: DONE
Dependencies: T002
Model: sonnet

### Goal
R4: `templates/.ai/prompts/claude-review.md`, appended by ai-review for Claude.

### Implementation notes
Sceptical reviewer; prove findings with probes in `.ai/local/review-probes/`; checklist of past failure types; same output contract as the mode prompt.

### Likely affected modules
templates/.ai/prompts/claude-review.md, scripts/ai-review, tests

### Acceptance criteria
- The Claude review prompt contains the checklist; setup-project installs the file; missing file -> clear error.

### Validation
targeted tests; ./scripts/ai-check

### Result / notes
DONE 2026-10-07: templates/.ai/prompts/claude-review.md (stance, probes, 10-item checklist incl. all brief items). Tests: setup_installs_the_claude_review_prompt, prompt contents asserted in the fallback test.
Validation: ./scripts/ai-check 244 tests OK (2026-10-07, 674 s).

## T004 — Pipeline: reviewer-neutral flow and fallback records
Status: DONE
Dependencies: T002
Model: sonnet

### Goal
R1/R5 in ai-pipeline and the PR body.

### Implementation notes
- Codex binary optional unless AI_REVIEWER=codex.
- Commit `.ai/reviews/fallback-log.md` with plan/review/re-check records; RECHECK_RECORDS includes it.
- Neutral step names; PR body says when the last review was a Claude fallback.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/workflow.py, tests

### Acceptance criteria
- Pipeline completes with Codex limited (auto) and the fallback log committed; PR body shows the fallback note.

### Validation
targeted tests; ./scripts/ai-check

### Result / notes
DONE 2026-10-07: ai-pipeline accepts a missing Codex CLI unless AI_REVIEWER=codex, commits the fallback log with plan/review/re-check records, tolerates a pending fallback log at start/reconcile; PR body titles the review "Claude fallback, <model>" with a catch-up note. Tests: pipeline_runs_on_the_claude_fallback_reviewer, pipeline_fallback_recheck_*, pipeline_without_codex_cli_* (PATH limited to mocks + /usr/bin so a real Codex is never found).
Validation: ./scripts/ai-check 244 tests OK (2026-10-07, 674 s).

## T005 — Per-task outcome log and report
Status: DONE
Dependencies: T001
Model: sonnet

### Goal
R6, R7: ai-run logs task outcomes; `ai-status --outcomes` reports.

### Implementation notes
- After each session: done/blocked; on validation failure: validation_failed; attempt = 1 + earlier lines for branch+task; duration = session seconds.
- `ai-status --outcomes [FILE]`.

### Likely affected modules
scripts/ai-run, scripts/ai-status, scripts/lib/workflow.py, tests

### Acceptance criteria
- ai-run writes one line per task with model and result; report groups by model/category/reviewer and lists Claude-only reviews.

### Validation
targeted tests; ./scripts/ai-check

### Result / notes
DONE 2026-10-07: ai-run `task_outcome` (done/blocked/validation_failed/no_checkpoint, model, seconds, attempt); `ai-status --outcomes [FILE...]`. Host-side file `<state root>/outcomes.jsonl`. Tests: runner_logs_task_outcomes_and_report, runner_logs_blocked_*.
Validation: ./scripts/ai-check 244 tests OK (2026-10-07, 674 s).

## T006 — Watchdog diagnosis: auto with Claude Sonnet fallback
Status: DONE
Dependencies: none
Model: sonnet

### Goal
R3 watchdog part.

### Implementation notes
- `--diagnosis-agent auto` (default): Codex, then Claude on any Codex failure/empty output. Claude uses `AI_DIAGNOSIS_MODEL` (default claude-sonnet-5-5).

### Likely affected modules
scripts/lib/watchdog.py, tests

### Acceptance criteria
- Codex failure -> Claude diagnosis with --model claude-sonnet-5-5; codex/claude choices unchanged.

### Validation
targeted tests; ./scripts/ai-check

### Result / notes
DONE 2026-10-07: watchdog `--diagnosis-agent auto` (default) with `diagnose()`; Claude uses AI_DIAGNOSIS_MODEL or claude-sonnet-5-5. Tests: watchdog_auto_diagnosis_falls_back_to_claude_sonnet; existing codex/claude diagnosis tests unchanged.
Validation: ./scripts/ai-check 244 tests OK (2026-10-07, 674 s).

## T007 — Docs and flow chart
Status: DONE
Dependencies: T002, T003, T004, T005, T006
Model: haiku

### Goal
README, docs/workflow.md, docs/decisions.md, templates CLAUDE.md/AGENTS.md where they name Codex as the only reviewer; vault agents-flow.md.

### Implementation notes
Settings table (AI_REVIEWER, AI_CLAUDE_REVIEW_MODEL/EFFORT, AI_DIAGNOSIS_MODEL), fallback log, catch-up, outcomes report.

### Likely affected modules
README.md, docs/*.md, templates/*.md, vault agents-flow.md

### Acceptance criteria
- Docs describe the fallback and the report; flow chart updated with its date.

### Validation
./scripts/ai-check

### Result / notes
DONE 2026-10-07: README (fallback reviewer, outcome log, config keys, diagnosis), docs/workflow.md (reviewer selection, outcome log), templates/CLAUDE.md wording, ai-pipeline usage; vault agents-flow.md reviewer chart + roles (updated 2026-10-07).
Validation: ./scripts/ai-check 244 tests OK (2026-10-07, 674 s).

## T008 — Fixes from the Claude (Fable) bootstrap review N1–N5
Status: DONE
Dependencies: T007
Model: opus

### Goal
Fix the five MINOR findings of `.ai/reviews/current.md` (see `.ai/reviews/dispositions.md`).

### Implementation notes
N1 stricter reviewer allowlist + saved allowlist; N2 reviewer denials logged; N3 whole-word
risk patterns; N4 reason in the PR note, forced reviews labelled and reported; N5 vault
decision/log/human todo. Also: `ai-pipeline` validates `AI_REVIEWER` first.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-review, scripts/ai-pipeline, tests/test_workflow.py, README.md, docs/workflow.md, vault

### Acceptance criteria
- Each finding's reproduction is covered by a test or (N5) the vault notes exist.

### Validation
targeted tests; ./scripts/ai-check

### Result / notes
DONE 2026-10-07: see dispositions; new/extended tests listed there.

