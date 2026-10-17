# Review dispositions (Claude)

Review HEAD: afa91c0d1e2c738010fc15ab683f0b45069806c2

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Verified: `proc_stat()` (tests/run_parallel.py:203–207) uses strict `read_text()` and catches only `OSError`, so a non-UTF-8 comm raises `UnicodeDecodeError` from `process_table()`; `terminate()` (:384) calls `live_descendants()` before any `signal_group`, and `stop()` sets `stop_done` in `finally` (:373–374), so the batch groups are never signalled and later callers return. Any visible process on the host can trigger it. | T014 |
| M2 | accepted | Verified: `family()` (scripts/lib/workflow.py:3172) maps `recheck` to `code`, so in `covered()` (:3178) a later Codex `recheck` covers an earlier Claude `code` review, while `templates/.ai/prompts/recheck.md:4` restricts a re-check to rejected findings. Spec CU-2 says "code covers code and re-check", i.e. a full Codex review covers a re-check, not the reverse. | T015 |
| P7 | accepted | Verified: writers (workflow.py:1646, :2945) escape only `\|`, so literal `\|` becomes `\\|`; `TABLE_CELL` (:985) pairs `\\` and the following `|` ends the cell, shifting columns. Cheap and in the FL-25 (b) scope; fixed with a matching backslash encoding in the same task as N1. | T016 |
| N1 | accepted | Verified: `DISPOSITION_ROW` (:994) and `PLAN_DISPOSITION_ROW` (:2445) use `\s*` around cells, which crosses the newline, so a row missing its Task cell matches an empty Task cell plus the next row's opening pipe; FL-25 (b)/T005 required such rows to stay malformed. Fix: `[ \t]*`, as `CONVERGENCE_LINE` already does. | T016 |
