# Plan: catch-up review fixes M1, M2

Branch `fix/catchup-review` from `master` (ba330ef, after PR #18: parallel gate), worktree `~/Projects/wt/agents-catchup-fixes`.
1. T001 (opus, security boundary): the Claude fallback reviewer gets no shell (tools Read/Glob/Grep only); the host prepares the git context per mode in `.ai/local/review-context/`, stopping before Claude on any preparation failure; Claude-path prompts name those files; tests; docs.
2. T002 (sonnet): `ai-run` attempt lifecycle, outcomes for timeout/interrupted/error; tests; docs.
3. T003 (opus, crash-safe state): `workflow.py` attempt helper (marker with a unique attempt ID, durable writes, idempotent finish and reconcile); boundary-state tests.
4. T004 (opus, locking): wire the helper into `ai-run` (open/finish, reconcile after `ai_lock`); SIGKILL and lock tests; docs and flow chart.
Revision 6 (plan review round 6): T003 split into T003/T004, both opus (locking and crash recovery). The reference patch shows one way to do the M2 part (its M1 part is superseded).
