# Plan

## Assessment
- Prompts: `templates/.ai/prompts/{runner,triage,recover}.md`; `ai-run` builds the runner and
  triage contracts; `ai-recover` reads `recover.md`.
- Triage: `ai-run --triage` checks allowed paths and `triage-check --fresh`, and the pipeline
  commits `chore(ai): record review triage` (counted by `count_commits`). A stop inside triage
  is recovered by `ai-recover`, whose `commit_and_rerun` commits leftovers generically
  (observed 2026-10-05, family-planner commit 49f1e76).
- Publishing: `host_commit` re-verifies only the gate; `review_current` is not re-checked
  before push (ai-pipeline ~line 120-240).
- Dispositions: `triage-check` accepts a rejection with 15+ characters of evidence.
- Setup preserves every existing file; no version record.

## Approach (tasks in order)
T001 tool contract + ai-task + permissions template (sonnet) → T002 model rule + human-todo
rule in templates (haiku: text only) → T003 recovery completes triage (opus) → T004 publish
invariants (opus) → T005 disputed findings re-check (opus) → T006 version stamp + upgrade
(sonnet) → T007 docs + vault flow chart (sonnet).

## Validation
`python3 -m unittest discover -s tests -k <name>` while working, then `.ai/bin/ai-check`.

## Risks
- Changing ai-run/ai-pipeline/ai-recover can break existing flows: the existing 102 tests stay
  green; new behaviour gets its own tests.
- Sessions must edit `scripts/` and `templates/`, never `.ai/bin` or `.ai/prompts` (gate).
