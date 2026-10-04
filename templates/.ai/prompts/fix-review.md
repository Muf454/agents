# Evaluate and fix review findings — Claude Code

Read CLAUDE.md, spec, plan, tasks, current state/handoff, and
`.ai/reviews/current.md`. Inspect source/tests yourself. For each finding, record
accepted/rejected/deferred plus evidence and reason in the review dispositions.
Do not blindly obey Codex. Keep original findings intact.

Add independently verifiable tasks for valid BLOCKER/MAJOR findings, with new IDs
and any dependencies. Prioritize these before acceptance. Handle MINOR findings
within approved scope or record a justified deferral. Set Phase: fixing_review.
Follow the autonomous implementation loop: targeted tests, full gate, persistent
state/handoff/run-log, and local checkpoints. Do not weaken validation to pass.

When valid significant findings are resolved and validation passes, request a
follow-up review where warranted. Record remaining risks and precise human test
steps. Human alone accepts, merges, and deploys.
