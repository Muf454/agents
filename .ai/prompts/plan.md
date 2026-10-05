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

Pick each task's Claude model by risk and write it explicitly as a `Model:` line
under `Dependencies:` on EVERY task (don't rely on the run default, which may differ):
- `haiku`: mechanical work (docs, renames, copy changes, simple config).
- `sonnet`: ordinary features, UI, tests, routine fixes.
- `opus`: security, authentication/authorization or RLS policies, concurrency and
  locking, data migrations that move or delete data, payment or irreversible
  operations. A task whose own earlier attempt failed validation or review is
  retried on opus; review-fix tasks get a model by their own risk (no blanket promotion).
Keep tasks small enough that the cheaper model fits; split rather than upgrade.

Update compact state and handoff for the next session. Do NOT start implementation
unless explicitly instructed. Finish with a concrete plan and any critical choices
for the human. Do not fill templates with fictional requirements or tasks.
