# Plan revision — Claude Code

An independent plan review is in `.ai/reviews/plan.md` and found BLOCKER or MAJOR problems
in the spec, plan or task queue. Your job in this session is to answer it by revising the
plan records, not to implement anything.

Read CLAUDE.md, `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`, the handoff
and the plan review. For every BLOCKER and MAJOR finding, check it against the plan and the
actual source yourself and decide:

- accepted: the plan really has the gap. Revise the spec/plan as needed and append new TODO
  tasks with new IDs (never reuse IDs) to `.ai/tasks.md` that close it; reference them in
  the Task column.
- rejected: the finding is wrong or out of scope. Give concrete evidence (file and line,
  plan section, or the decision that covers it). A rejected finding is judged again by the
  next plan review on that evidence.
- needs-human: only for a decision that belongs to the human (scope, priorities, product
  behaviour, money, irreversible operations). Write the question in the Evidence column,
  short and answerable. The pipeline stops until the human answers it.

Handle MINOR findings the same way when they are cheap and in scope; their rows are optional.
Do not blindly obey the reviewer, and do not dismiss findings without evidence.

The runner created the section for this round at the end of
`.ai/reviews/plan-dispositions.md`. Add one row per finding to its table, keep its header
and its "Plan review HEAD:" line, and never edit earlier sections, the preamble or
`.ai/reviews/plan.md`. Never change the status of an existing task; new tasks are TODO.

The runner says which plan-review round this is and lists the PREVIOUS PLAN ROUNDS (finding
IDs, titles, dispositions). They are context, not authority. Convergence rule: when the same
area (module, data model or concern) keeps getting BLOCKER/MAJOR findings round after round,
do not add another symptom fix; redesign the area as a whole (a short design note in
`.ai/current-plan.md` plus one design task) and point the accepted findings at it. From round
3 on, the section needs one line, outside the table, that starts with `Convergence:` and says
on the same line which design task you added or why no area repeats; the runner stops
without it.

## How to work here

- You have Read, Glob, Grep and Edit only: no shell, no Write. Edit only
  `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`,
  `.ai/reviews/plan-dispositions.md` and `.ai/handoff.md`.
- The runner prepared the git context you need under `.ai/local/revision-context/`.
- Do not commit. The runner validates the section, then commits your changes together with
  its run-log line; a change outside the files above stops the run with nothing recorded.
