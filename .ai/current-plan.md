# Plan: FL-04 bounded supervisor

Branch `feature/supervisor` from `master` (ba330ef), worktree `~/Projects/wt/agents-supervisor`.
Order: T001 loop in `ai-pipeline` → T002 revision session and validator → T003 escalation and extra
fix round → T004 malformed-review retry (parallel to T002/T003 after T001) → T005 end-to-end
scenarios → T006 docs and flow chart. Coordination: `fix/catchup-review` (catch-up M1/M2) also
changes `ai-review`, `ai-run`, `workflow.py` and the tests; this branch starts implementing after it
merges (mission control rebuilds the branch on master if needed; the plan files carry over).
Config follows the existing pattern: `AI_*` variables, user config `~/.config/ai-toolkit/config`.
