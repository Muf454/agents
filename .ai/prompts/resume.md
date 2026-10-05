# Resume from durable evidence — fresh Claude Code session

Read CLAUDE.md and relevant docs/ (architecture, conventions, decisions), then
`.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`, `.ai/state.md`, and
`.ai/handoff.md`. Read recent `.ai/run-log.md` entries as needed, not the full
history by default. Inspect Git status, branch, recent history, and recent diffs.

Determine intended work, what is actually finished, what remains, cleanliness of
the checkout, interrupted work, and the next safe task with DONE dependencies.
Treat files/source/tests/Git as evidence, not an old session's claims. Reconcile
stale state or IN_PROGRESS tasks; preserve partial and unrelated changes. Check
existing validation results and rerun relevant checks when stale or uncertain.

Implementation authorization is the approved scope already recorded in the plan;
if it is absent, return to planning rather than guessing permission. If returning
from Codex, read its review and recorded dispositions too. Repair compact state,
then follow the autonomous loop in `.ai/prompts/implement.md`. Continue until all
work is finished or a genuine blocker requires the human. A model/context change
does not justify discarding checkpointed work.
