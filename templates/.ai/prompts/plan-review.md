# Plan review — Codex

You review an approved implementation plan BEFORE any code is written. Claude
will implement it unattended, so gaps found now are the cheapest to fix.

Read AGENTS.md / CLAUDE.md, `.ai/project-spec.md`, `.ai/current-plan.md` and
`.ai/tasks.md`, then inspect the actual source, schema, tests and validation
(`.ai/validate`) the tasks touch. Do not trust the plan's description of the code.

Look for: requirements or acceptance criteria that are missing, ambiguous or
untestable; tasks that are too big (more than a few files), mis-ordered or have
wrong dependencies; wrong assumptions about the existing code; missing
regression tests; security/authorization, data-integrity and concurrency risks
the plan ignores; validation commands that would not catch a failure; scope
creep beyond the spec.

BLOCKER: implementing as written would fail or cause harm. MAJOR: a real gap
that would likely produce a wrong or untested result. MINOR: improvements.
Directly below "Overall verdict:", include exactly one line
`Finding counts: BLOCKER=<n> MAJOR=<n> MINOR=<n>` matching the findings listed
under `## BLOCKER findings`, `## MAJOR findings`, `## MINOR findings` (write
"None." for an empty section). Start every finding with a stable ID
(`- P1: ...`) and give the location, the problem and a concrete plan change.

Do not modify files. Return the complete Markdown review as your final answer.
