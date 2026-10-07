# Plan: catch-up review fixes M1, M2

Branch `fix/catchup-review` from `master` (ba330ef, after PR #18: parallel gate), worktree `~/Projects/wt/agents-catchup-fixes`.
1. T001 (opus, security boundary): the Claude fallback reviewer gets no shell (tools Read/Glob/Grep only); the host prepares the git context per mode in `.ai/local/review-context/`; Claude-path prompts name those files; tests; docs.
2. T002 (sonnet): `ai-run` attempt lifecycle, outcomes for timeout/interrupted/error; tests; docs.
3. T003 (sonnet): host-side attempt marker so a SIGKILL/power loss is logged `crashed` at the next `ai-run` start; test; docs.
All are small; the reference patch shows one way to do the M2 part (its M1 part is superseded).
