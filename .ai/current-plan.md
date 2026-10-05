# Plan

## Assessment
- Prompts: `templates/.ai/prompts/{runner,triage,recover}.md`; `ai-run` builds the runner and
  triage contracts; `ai-recover` reads `recover.md`.
- Triage: `ai-run --triage` checks allowed paths and `triage-check --fresh` and itself creates
  the counted `chore(ai): record review triage` commit (counted by the pipeline's
  `count_commits`). A stop inside triage
  is recovered by `ai-recover`, whose `commit_and_rerun` commits leftovers generically
  (observed 2026-10-05, family-planner commit 49f1e76).
- Publishing: `host_commit` re-verifies only the gate; `review_current` is not re-checked
  before push (ai-pipeline ~line 120-240).
- Dispositions: `triage-check` accepts a rejection with 15+ characters of evidence.
- Setup preserves every existing file; no version record.

## Approach (after Codex plan review round 1)
T001 permissions template (opus) → T002 tool contract + ai-task (sonnet) → T003 template
rules (haiku) → T004 triage completion protocol (opus) → T005 publish invariants (opus) →
T006 re-check command + binding (opus) → T007 dispute integration + PR (opus) → T008
version + upgrade (sonnet) → T009 docs (sonnet). The vault flow chart is updated in the
same task as each flow change (T004, T007). Run with `--knowledge-dir` for the vault.

## Validation
Each task names its test pattern; the targeted run must report at least one test. Then `.ai/bin/ai-check`.

## Risks
- Changing ai-run/ai-pipeline/ai-recover can break existing flows: the existing 102 tests stay
  green; new behaviour gets its own tests.
- Sessions must edit `scripts/` and `templates/`, never `.ai/bin` or `.ai/prompts` (gate).
