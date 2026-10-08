# Handoff

## What has been implemented?
Nothing yet. Branch `feature/supervisor`: FL-04 bounded supervisor (see `.ai/project-spec.md`).
Plan revision 2 answers plan review round 1 (HEAD cc8c464; 10 MAJOR + 1 MINOR accepted, see
`.ai/reviews/dispositions.md` → "Plan review round 1"); 11 tasks T001–T011. Plan revision 3
answers plan review round 2 (HEAD dfc03c8; 1 MAJOR + 7 MINOR accepted, see "Plan review round 2"):
reserve before stage-set, per-base plan rounds with a crash-window sync, bounded needs-human
text, `AI_RUN_BUDGET` wiring, fixture default `AI_SUPERVISE=0`.

## Manual testing for the human
### Needs you
1. One real supervised run on a small plan (filled in by T011).

### Covered by automated tests
Listed per task when done.

## Flow chart
Flow unchanged

## Next action
Plan review round 3 of revision 3 (after `fix/catchup-review` merges and this branch is rebuilt
on master, per the plan's Coordination section).
The run budget follows Zack's Q2 decision (16 h of work per approved run, cumulative; no new
decision needed). Start it with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` so the flow-changing
tasks can update `agents-flow.md` themselves.
