# Handoff

## What has been implemented?
Nothing yet for this run. Batch 1 (flow hardening, T001–T017) was merged via PR #11; its
records are in Git history. This branch (`feature/evidence-or01-or02`, from origin/master
d6038f6) plans backlog items OR-01 (committed bytes on every accepted checkpoint) and OR-02
(disjoint authority/state roots, incl. the watchdog host copy). See `.ai/project-spec.md`,
`.ai/current-plan.md`, `.ai/tasks.md` (T001–T005). Planned by Claude as Zack's delegate on
2026-10-05; the pipeline's Codex plan review gates the plan.

## Validation
Baseline before planning: `.ai/bin/ai-check` (shell syntax + 168 unittest tests).

## Open assumptions (for the plan review and Zack)
- Overlap is bidirectional (a state root containing the checkout/knowledge dir is refused).
- A symlinked state root is refused only when it (or its real path) overlaps; a symlink to
  a disjoint location is accepted.
- Repositories with clean/smudge/eol filters (Git LFS, CRLF with `text=auto`) now stop at
  every accepted task; documented limitation, not supported here.
- The watchdog checks the checkout only; the resumed ai-pipeline checks the knowledge dir.

## Flow chart
Flow chart updated: not yet for this run (T005 updates the vault agents-flow.md and
replaces this line; a test requires the section to start with these words).

## Manual testing for the human
1. Filled in by the tasks as they complete (scratch-project steps for the committed-bytes
   stop and the state-root refusal).

## Human todos
None.

## Next action
Run the pipeline: `.ai/bin/ai-pipeline --approved --base master --knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`.
