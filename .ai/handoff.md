# Handoff

## What has been implemented?
Nothing yet. Branch `feature/dashboard` (from master 0818f20) plans the pipeline dashboard
Zack asked for on 2026-10-07: observation records written by the scripts (T001), a read-only
snapshot of all pipelines (T002), a curses TUI showing the flow as boxes with the active
stage highlighted (T003), docs (T004). See `.ai/project-spec.md`, `.ai/current-plan.md`,
`.ai/tasks.md`. The previous batch (FL-01, FL-07, FL-09) shipped in PR #15.

## Validation run
Not run on this branch yet (master passed the gate for PR #15).

## Assumptions
- Finished/stopped/idle runs older than 24 h are hidden by default (`--all` shows them).
- The dashboard is advisory and read-only; `.ai/local/` records are agent-writable.

## Flow chart
T001 adds a note (stages observed, notifications mirrored locally); the flow itself is unchanged.

## Manual testing for the human

### Needs you
1. Filled in by T004.

### Covered by automated tests
- Filled in by the tasks.

## Human todos
None yet (T004 adds the optional PATH symlink and the `.ai/bin` upgrade of projects).

## Next action
Run the pipeline: `.ai/bin/ai-pipeline --approved --base master --knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`.
