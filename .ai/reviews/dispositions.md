# Review dispositions (Claude)

Review HEAD: b651970c55b64ff3fccec2e4a9cd702d576da372

<!-- One row per BLOCKER/MAJOR finding (MINOR optional), the finding ID alone in the first cell,
e.g. "| M1 | accepted | evidence | T012 |". Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M2 | accepted | Confirmed in scripts/lib/workflow.py exec_bits(): os.lstat(root / name) rejects only a symlink leaf, and os.chmod(root / name) follows parent-directory symlinks, so a session-planted directory symlink lets the host chmod an external file. Fix: pinned no-follow descriptor walk plus fchmod, with an external-directory regression. | T034 |
| M3 | accepted | Confirmed in scripts/ai-run: claude_session calls ai_die for any non-zero exit (line 360) before returning, and exec-bits runs only after it returns (line 842), so exits 124 and 137 stop the run unrepaired and ai-recover's timeout commit-and-rerun can fail its gate on a lost bit. Fix: repair before the stop, with a timeout regression. | T035 |
| N3 | accepted | Handoff "Next action" and T033 lines still say T033 is BLOCKED although tasks.md has it DONE on mission control's gate pass. state.md counts are runner-managed and refresh at the next runner checkpoint. Cheap and in scope; folded into the post-fix docs task. | T036 |
| N4 | accepted | AGENTS.md requires the flow chart to show every flow step; exec-bits (ai-run line 842) is a new host mutation and T035 changes where it runs, so the chart is updated after that fix. | T036 |
