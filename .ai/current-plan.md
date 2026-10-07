# Plan: Reviewer fallback and model-choice data

## Assessment (master 0818f20, after PR #15)
- `scripts/ai-review` `codex_review()` loops: Codex exit != 0 and `limit-check` finds a limit
  → `ai_limit_pause Codex` → retry; a reset beyond `AI_LIMIT_MAX_WAIT` dies.
- Publish helpers (`workflow.py publish-review`, `publish-plan-review`, `publish-recheck`)
  validate format and bind the saved file's SHA-256 outside the checkout; reviewer-neutral.
- `ai-pipeline` requires `codex` on PATH and commits `.ai/reviews/{plan,current,recheck}.md`
  after each review; `.ai/reviews/` is already excluded from the validation fingerprint,
  the plan digest and `review_current`; `RECHECK_RECORDS` needs the fallback log.
- `ai-run` `claude_session` knows each task's model and outcome (DONE/BLOCKED/validation
  failure) but logs nothing structured.
- `watchdog.py` has `--diagnosis-agent codex|claude`; Claude uses `AI_MODEL`.
- Claude CLI 2.1.291: `--model claude-fable-5-1|claude-opus-5-5|claude-sonnet-5-5` and
  `--effort high` verified live; in dontAsk mode `Edit(./dir/**)` allows the Write tool
  inside dir only (verified: writes elsewhere denied; `Write(...)` rules did not match).

## Approach
1. T001 `workflow.py`: `review-risk` (risk + reason from tasks), outcome log append and
   report helpers (`outcome-task`, `outcome-review`, `outcomes-report`), `fallback-record`,
   reviewer label support in the publish helpers (env `AI_REVIEW_LABEL`).
2. T002 `ai-review`: reviewer selection (`AI_REVIEWER`), `claude_review()` with the read-only
   allowlist, model by risk, fallback on Codex limit, Claude limit pause, probe dir cleanup,
   label + fallback log + review outcome; settings plumbing (config, recovery manifest).
3. T003 Prompt template `templates/.ai/prompts/claude-review.md`.
4. T004 `ai-pipeline`: Codex optional in auto/claude mode, commit the fallback log with each
   review, neutral step names; `RECHECK_RECORDS`; PR body names fallback reviews.
5. T005 `ai-run` per-task outcome lines; `ai-status --outcomes`.
6. T006 Watchdog `--diagnosis-agent auto` + `AI_DIAGNOSIS_MODEL` (default sonnet 5.5).
7. T007 Docs (README, docs/workflow.md, docs/decisions.md), vault flow chart.
Then: Claude fallback review (Fable) of this branch, dispositions, fixes.

## Risks
- A Claude reviewer with Bash can run project code (tests); mitigated by the allowlist
  (project-approved commands only), the existing post-review clean-checkout/HEAD check and
  the gate digest check. Not an OS sandbox (documented).
- Claude reviews use Zack's Max allowance: only on Codex limit or when forced.
