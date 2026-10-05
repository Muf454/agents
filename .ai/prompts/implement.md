# Autonomous implementation — Claude Code

Implementation of the approved scope is authorized. Read CLAUDE.md, relevant docs,
spec, plan, tasks, state, handoff, Git status/history, and recent diffs. Resolve
disagreements between summaries and repository evidence before editing.

Select the next unblocked task (dependencies DONE), mark IN_PROGRESS, implement,
run targeted deterministic validation and `.ai/bin/ai-check`, and fix failures
caused by the changes. Update docs where needed. Mark DONE only if acceptance
criteria are satisfied with evidence. Update state and handoff, append outcomes to
the run log, and create meaningful local checkpoint commits on the feature branch.
Continue to the next task without asking permission between ordinary tasks.

Keep reads focused, logs concise, and checkpoints recoverable. For interrupted
IN_PROGRESS work, preserve partial changes and reconcile before resuming. Do not
blindly restart or reset. Stop for genuine blockers, external/irreversible risk,
or repeated failures. Preserve truthful failure evidence and an actionable handoff.
Try other independent tasks when a task is blocked and safe work remains.

When the queue is complete, run the full gate, set Phase to ready_for_review, and
provide manual test steps. Do not merge, deploy, or claim human acceptance.
