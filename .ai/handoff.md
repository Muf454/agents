# Handoff

## What has been implemented?
Nothing yet. Branch `feature/dashboard` (master e9354d9 merged in) plans the pipeline
dashboard Zack asked for on 2026-10-07: safe record writers and readers (T001), stage
writers in common.sh (T002), ai-pipeline (T003), ai-run/`ai_deps`/ai-review (T004) and
ai-recover (T005), discovery and liveness (T006), a read-only snapshot of all pipelines
(T007), a curses TUI showing the flow as eight boxes with the active stage highlighted
(T008), docs (T009). Revised after Codex plan review 1 (P1–P10), 2 (P11–P18) 3 (P19–P22)
4 (P23–P25) 5 (P26–P27) 6 (P28–P29) and 7 (P30–P31), all accepted; round 8 clean. Revision 9
(2026-10-09) rebases it on master e9354d9 (FL-04 supervisor, FL-14–17): Plan revision box,
stored decision, extra fix round, format retry, base-moved stop, box layout from 120
columns; see the top of `.ai/current-plan.md`. See also `.ai/project-spec.md`, `.ai/tasks.md`.

## Validation run
Not run on this branch yet (master passed the gate for PR #15).

## Assumptions
- Finished/stopped/idle runs older than 24 h are hidden by default (`--all` shows them).
- The dashboard is advisory and read-only; `.ai/local/` records are agent-writable.
- Eight boxes need up to 112 columns, so the box layout starts at 120 columns (compact
  line below); the plan revision box label is "Plan revision" ("Revise" in the compact line).

## Flow chart
Flow chart updated: PENDING (T002/T003 will add a note under "Phone notifications" in the
vault `agents-flow.md`: notifications mirrored to `.ai/local/notifications.log`, stages
recorded in `.ai/local/observation.json`, for `ai-dashboard`; the flow itself is unchanged).
Not done yet.

## Manual testing for the human

### Needs you
1. Filled in by T009.

### Covered by automated tests
- Filled in by the tasks.

## Human todos
None yet (T009 adds the optional PATH symlink and the `.ai/bin` upgrade of projects).

## Next action
Zack reviews revision 9 of the plan (rebased on master e9354d9; uncommitted), then it is
committed and gets a plan review. The pipeline's own plan review covers it when started with:
`.ai/bin/ai-pipeline --approved --base master --knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`.
