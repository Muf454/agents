# Plan: catch-up review fixes M1, M2

Branch `fix/catchup-review` from `master` (ba330ef, after PR #18: parallel gate), worktree `~/Projects/wt/agents-catchup-fixes`.
1. T001 (opus, security boundary): the Claude fallback reviewer gets no shell (tools Read/Glob/Grep only); the host prepares the git context per mode in `.ai/local/review-context/`, stopping before Claude on any preparation failure; Claude-path prompts name those files; tests; docs.
2. T002 (sonnet): `ai-run` attempt lifecycle, outcomes for timeout/interrupted/error; tests; docs.
Revision 7 (mission control, after plan review round 7): crash-durable attempt markers (old T003/T004) dropped to the backlog (CU-5); T001 + T002 remain.
