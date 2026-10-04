# Plan significant work — Claude Code

Read CLAUDE.md. Understand the user's objective supplied with this prompt. Inspect
the actual repository and Git state, existing architecture, conventions, and
decisions. Ask questions only if critical ambiguity prevents reasonable planning;
otherwise state reasonable assumptions explicitly.

Create/update `.ai/project-spec.md` with scope, non-goals, constraints, requirements,
and observable acceptance criteria. Create/update `.ai/current-plan.md` with the
current assessment, simplest architecture, affected components, phases, API/data
changes, risks, and validation strategy. Decompose into `.ai/tasks.md` using its
exact format and TODO/IN_PROGRESS/BLOCKED/DONE statuses. Each task needs clear
dependencies, acceptance criteria, actual modules, and exact validation commands.

Inspect `.ai/validation-candidates.md` if present. Propose a real `.ai/validate`
entry point using existing tooling; distinguish missing tools/tests and baseline
failures. Do not execute candidate commands without inspecting them. Identify
destructive/external operations and permission needs in `.ai/permissions.allow`.
Do not broaden permissions yourself.

Update compact state and handoff for the next session. Do NOT start implementation
unless explicitly instructed. Finish with a concrete plan and any critical choices
for the human. Do not fill templates with fictional requirements or tasks.
