# Handoff

## What has been implemented?
Nothing yet. Branch `feature/supervisor`: FL-04 bounded supervisor (see `.ai/project-spec.md`).
Plan revision 2 answers plan review round 1 (HEAD cc8c464; 10 MAJOR + 1 MINOR accepted, see
`.ai/reviews/dispositions.md` → "Plan review round 1"). Plan revision 3 answers plan review
round 2 (HEAD dfc03c8; 1 MAJOR + 7 MINOR accepted, see "Plan review round 2"). Plan revision 4
answers plan review round 3 (HEAD dbe85f5; 1 BLOCKER + 4 MAJOR + 2 MINOR, see "Plan review
round 3"): the shared run budget is removed from this batch (mission control's convergence
decision; OR-09 keeps Zack's 16 h + 12 h cumulative budget), supervision is bounded by counts plus
the per-call timeouts; the revision's run-log entry is committed in its host commit (clean
re-review); the needs-human outcome is stored in the host revision record before the stage
closes and checked by the pipeline and `ai-recover`. 10 tasks T001–T010.

## Manual testing for the human
### Needs you
1. One real supervised run on a small plan, including a needs-human stop, a recovery attempt on
   it and clearing it with a hand-run `ai-review --plan` (filled in by T010).

### Covered by automated tests
Listed per task when done.

## Flow chart
Flow unchanged

## Next action
Plan review round 4 of revision 4 (after `fix/catchup-review` merges and this branch is rebuilt
on master, per the plan's Coordination section). No run budget in this batch (OR-09). Start it
with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` so the flow-changing tasks can
update `agents-flow.md` themselves.
