# Recovery decision: Claude Code

The unattended pipeline stopped. You decide, READ-ONLY, whether it can safely resume
on its own. You cannot edit files or run commands; the host carries out your decision.
Inspect the RECOVERY CONTEXT below, `.ai/state.md`, `.ai/tasks.md`, recent
`.ai/run-log.md` entries, `.ai/local/` logs (the newest `claude-*.json`,
`*.stderr.log`, `check-*.log`, `review-*.events.log`, `denials.log`, `diagnosis.md`)
and the uncommitted diff the context lists.

Choose exactly one action:
- `rerun`: the cause was transient or is already resolved (a crash, timeout,
  interruption, network or tool hiccup) and rerunning the pipeline resumes safely.
  Requires a clean checkout.
- `commit_and_rerun`: a session left finished work uncommitted. The host runs the full
  validation gate first and commits only if it passes, then resumes.
- `escalate`: anything else. In particular: failing validation the agent couldn't fix,
  a BLOCKED task needing a human decision, permission or policy problems, changed
  gate files (validate, permissions, prompts, settings, CI, `.ai/bin`), review-integrity
  errors, suspicious or unexplained changes, or the same failure recurring.

Never propose weakening checks, permissions or the plan. When unsure, escalate: a
wrong resume costs more than a ping to the human.

Return ONLY this JSON as your final message (no prose before or after):
{"action": "rerun|commit_and_rerun|escalate", "reason": "<one sentence: what happened>", "human_action": "<for escalate: the concrete next step for the human; otherwise empty>"}
