# Runner session: one task — Claude Code

You were started by the unattended runner (`ai-run`/`ai-pipeline`) for exactly ONE
task, named in the RUNNER CONTRACT below. A fresh session handles the next task;
do not continue to other tasks in this session.

Read CLAUDE.md, relevant docs/, `.ai/project-spec.md`, `.ai/current-plan.md`,
`.ai/tasks.md`, `.ai/state.md`, `.ai/handoff.md`, recent `.ai/run-log.md` entries,
Git status/history, and recent diffs. Treat source, tests, and Git as evidence.
If the task is IN_PROGRESS from an interrupted session, reconcile the partial diff
first; preserve it, don't reset it.

For the assigned task: mark it IN_PROGRESS, implement it within scope with tests,
run its targeted checks and `.ai/bin/ai-check`, and fix failures your change
caused. Update relevant docs/decisions (and the configured knowledge base, if
any). Mark it DONE only when its acceptance criteria are met, with evidence in
"Result / notes". Update `.ai/state.md` and `.ai/handoff.md` (keep "Manual testing
for the human" current: concrete steps and expected results for the whole
feature; list actions only the human can take under "Human todos", or "None"),
append a concise `.ai/run-log.md` outcome, and commit with explicit
paths (`git add -- <files>`; never `-A`, `.`, `--no-verify`, or `-n`).

Your shell starts in the project root. Never prefix commands with `cd` (the
allowlist checks every part of a compound command, so `cd … && git commit …` is
denied, and an uncommitted task stops the whole pipeline). Run `git add -- <paths>`
and `git commit -m …` as plain commands.

Create and edit files with the Edit/Write tools, not shell redirection (`cat >`,
`printf >>`, `tee`): the shell allowlist is deliberately narrow and denied commands
are logged. If `.ai/state.md`, `.ai/run-log.md`, or `.ai/handoff.md` changes are left
uncommitted, the runner commits them with its bookkeeping; everything else must be
in your commit.

If you cannot finish after three genuine attempts at the same failure, or a human
decision/permission is needed, mark the task BLOCKED with evidence and the exact
blocker, commit, and return. Never weaken validation, change the runner,
permissions, prompts, or branch, or invent success. Then stop: the runner validates
your checkpoint and continues the queue.
