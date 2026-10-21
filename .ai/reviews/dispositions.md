# Review dispositions (Claude)

Review HEAD: 41e45a825380b1cc72ac2558606bc93ddbfa1496

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M3 | accepted | Confirmed: `route_fix_rounds` (scripts/lib/workflow.py:3712) counts `TRIAGE_COMMIT` subjects in BASE..HEAD when `fix_round_records()` returns None (missing store), so agent-controlled history can make the round count non-zero and route to Claude. A10 says routing reads host records only and anything missing means Codex. | T116 |
| N2 | accepted | Confirmed: tests/isolation.py:18 checks only `AI_STATE_DIR`; when it is already under the temp dir, `XDG_STATE_HOME` stays unset or external, contrary to A13 (both variables isolated). Cheap, test-only. | T117 |
| N3 | accepted | Confirmed: `ai_queue_ruling` (scripts/lib/common.sh) returns after `tasks preflight --dry-run` when nothing needs repair, and ai-run planning and revision only use `--dry-run`; `tasks_preflight` writes `.ai/local/preflight.md` only without `--dry-run` (workflow.py ~718). A5 says the report is printed and written. Cheap, in scope. | T118 |
