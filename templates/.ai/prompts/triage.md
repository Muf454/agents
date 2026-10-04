# Review triage — Claude Code

An independent Codex review is in `.ai/reviews/current.md`. Your job in this session
is to evaluate it, not to fix anything yet.

Read CLAUDE.md, the spec, plan, tasks, handoff, and the review. For every BLOCKER
and MAJOR finding, inspect the actual source and tests yourself and decide:
accepted (real problem), rejected (with concrete evidence why it is wrong or out
of scope), or deferred (real but out of scope; explain the risk). Do not blindly
obey Codex, and do not dismiss findings without evidence. Handle MINOR findings
the same way when they are cheap and in scope; otherwise defer them.

Record each decision as a row in `.ai/reviews/dispositions.md` (finding ID,
disposition, evidence/reason, fix task). The runner created that file for this
review; keep its "Review HEAD" line. Never edit `.ai/reviews/current.md`: it is
Codex's evidence, and the runner stops if any session changes it. Every BLOCKER and
MAJOR finding needs a row: accepted rows reference an existing fix task ID,
rejected rows need concrete evidence, and deferred findings make the PR a draft. For each accepted finding, append a new task
to `.ai/tasks.md` with a new ID (never reuse IDs), Status TODO, correct
dependencies, and acceptance criteria that include a regression test where
practical. Update `.ai/handoff.md` if test steps change.

Do not edit source, tests, docs, validation, prompts, permissions, or tooling in
this session; the runner rejects triage commits that touch anything except
workflow records. Commit `.ai/reviews/dispositions.md`, `.ai/tasks.md`, and any updated
handoff/state with explicit paths, then return.
