# Evaluate and fix review findings — Claude Code

Read CLAUDE.md, spec, plan, tasks, current state/handoff, and
`.ai/reviews/current.md`. Inspect source/tests yourself. For each finding, record
accepted/rejected/deferred plus evidence and reason in `.ai/reviews/dispositions.md`
(create it with `python3 .ai/bin/lib/workflow.py start-dispositions <reviewed HEAD>`
if absent). Do not blindly obey Codex. Never edit `.ai/reviews/current.md`.

Add independently verifiable tasks for valid BLOCKER/MAJOR findings, with new IDs
and any dependencies. Prioritize these before acceptance. Handle MINOR findings
within approved scope or record a justified deferral. Set Phase: fixing_review.
Follow the autonomous implementation loop: targeted tests, full gate, persistent
state/handoff/run-log, and local checkpoints. Do not weaken validation to pass.

When valid significant findings are resolved and validation passes, request a
follow-up review where warranted. Record remaining risks and precise human test
steps in the handoff: "Needs you" only for what a human must do (look and feel,
phone/real devices, live accounts, external services, decisions) or "None"; steps a
test reproduces go under "Covered by automated tests" with the test name in backticks.
Human alone accepts, merges, and deploys.
