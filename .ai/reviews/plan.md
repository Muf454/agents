<!-- Plan review of plan digest dacc9f4c68f39977034d5b09f3ae0fb81abee8c00a1b4fd2c9e8932e4de3663e; HEAD 4efc5cf55d4110887d13cb6a081a09fbd4cb5fbe; saved 2026-10-17T08:02:47Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `4efc5cf55d4110887d13cb6a081a09fbd4cb5fbe`

## BLOCKER findings

None.

## MAJOR findings

- P3: An armed resume can still reach a plan review before consuming the arm.

  **Location:** `.ai/current-plan.md:149`, `.ai/tasks.md:613`, `.ai/tasks.md:781`.

  The stated reason the plan-review loop is unreachable is incorrect. `tasks untouched` permits IN_PROGRESS tasks and fails only when a task is DONE (`scripts/lib/workflow.py:638`). Meanwhile, `plan_digest()` includes committed source, not just task statuses (`scripts/lib/workflow.py:2328`).

  A first task can checkpoint some source while still IN_PROGRESS, make further uncommitted edits, then hit the limit. On relaunch, the preserved tree verifies, but the queue remains “untouched” and the source checkpoint makes the plan review stale. The pipeline therefore invokes `ai-review --plan` before ai-run consumes the arm (`scripts/ai-pipeline:429`, `scripts/ai-pipeline:458`). That review refuses the dirty checkout (`scripts/ai-review:286`).

  **Concrete plan change:** Replace the unreachable-path assumption with explicit handling of an armed implementation continuation whose plan review became stale through partial checkpoints. Preserve the original plan-approval boundary while allowing the verified continuation to reach ai-run. Add an end-to-end matrix case with zero DONE tasks, a committed source change, further preserved edits, and plan review enabled. Require completion without a recovery decision session or a review/commit before disarming.

- P12: Detached planning lacks initialization of `.ai/local`.

  **Location:** `.ai/tasks.md:933`, `.ai/tasks.md:989`.

  T013 requires `.ai/local` to exist and explicitly fails when it is missing. T006 launches that helper before ai-run, but specifies no initialization of the directory. A normal `setup-project` installation does not create it (`scripts/lib/workflow.py:348`); existing commands create it through `ai_root` (`scripts/lib/common.sh:118`).

  Following the detached-launch recipe in a freshly installed checkout therefore fails before ai-run can initialize the directory or start planning.

  **Concrete plan change:** Specify safe creation of a missing `.ai/local` before `exec-logged`, while retaining rejection of symlinked or invalid components. Add a first-use regression: install the toolkit, confirm `.ai/local` is absent, then run `ai-plan --detach` successfully without first invoking another toolkit command.

## MINOR findings

- P13: The absent-schedule acceptance criteria contradict the retained stall behavior.

  **Location:** `.ai/tasks.md:222`.

  Case (b) requires no `⛔` notification while also requiring the second probe to raise `stalled` exactly as today. Today that incident explicitly sends `⛔ STOPPED` (`scripts/lib/watchdog.py:450`; existing assertion at `tests/test_workflow.py:831`). Both expectations cannot pass.

  **Concrete plan change:** Require no relaunch-related notification for all absent-schedule cases. For case (b), require exactly the normal stall notification; reserve complete silence for cases (a) and (c).

## Previous findings re-evaluated

Round 4’s settled-recheck scenario is now explicitly covered by T011/T015. P3 remains because the broader acceptance contract relies on the incorrect plan-review assumption described above.

P11’s absent-versus-due predicate is corrected. P13 concerns its contradictory test expectations.

## Validation and limitations

Inspected the required instructions, spec, plan, tasks, state, handoff, dispositions, relevant documentation, source, tests, validation entry point, and revision diff.

Checks run successfully:

- Task queue validation.
- Three documentation consistency tests.
- Shell syntax checks on the affected existing scripts.
- Python AST parsing of affected modules and test files.
- `git diff --check`.
- An in-memory probe confirming both helper behaviors underlying P3.

The full `./scripts/ai-check` and writing integration fixtures were not run because this review is read-only. Proposed behavior remains unimplemented and unvalidated. No files were modified or network/MCP integrations invoked.