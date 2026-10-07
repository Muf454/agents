# Handoff

## What has been implemented?
Nothing yet. Branch `fix/catchup-review`: Codex catch-up review M1 (the Claude fallback reviewer gets no shell, only Read/Glob/Grep, and reviews from host-prepared git context) and M2 (outcomes for stopped and crashed attempts).

## Manual testing for the human
### Needs you
1. After merge, approve `setup-project --upgrade --apply` for agents, raid-planner and family-planner so their installed copies get the stricter reviewer policy.

### Pending (mission control)
1. Live check with the Claude CLI: a fallback review cannot run any Bash command or write a file, and it reads `.ai/local/review-context/`.

### Covered by automated tests
Reviewer tools and arguments (Read/Glob/Grep only); review context per mode (code, plan, re-check) with real diff content and cleanup after success, failure and a limit retry; outcome lines for timeout (124/137), error, interruption (SIGINT/SIGTERM), malformed queue, validation failure, crash recovery (SIGKILL) and triage (none).

## Next action
Run the pipeline.
