# Handoff

## What has been implemented?
Nothing yet. Branch `fix/catchup-review`: Codex catch-up review M1 (read-only reviewer policy) and M2 (outcomes for stopped attempts).

## Manual testing for the human
### Needs you
1. After merge, approve `setup-project --upgrade --apply` for agents, raid-planner and family-planner so their installed copies get the stricter reviewer policy.

### Covered by automated tests
Reviewer allow/deny lists and reviewer arguments; outcome lines for timeout, error, recovery and validation failure.

## Next action
Run the pipeline.
