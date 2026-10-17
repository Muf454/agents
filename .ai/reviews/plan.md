<!-- Plan review of plan digest 5c86f63b7318b1cab628639074466e24ddc111e4d2a396ae9be98f6d32c5d7dd; HEAD 1057dc3434c60e201ec723b009f842b63e7fd5c3; saved 2026-10-17T08:30:46Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `1057dc3434c60e201ec723b009f842b63e7fd5c3`

## BLOCKER findings

None.

## MAJOR findings

- P16: The preserved-work “fail closed” stop still permits recovery to commit and rerun.

  **Location:** `.ai/tasks.md:717`, `.ai/tasks.md:1074`.

  T011 routes inconsistent review records through `recheck_fail`, while requiring the arm retained and nothing committed. T015 additionally requires no session. However, `recheck_fail` calls `stop 're-check'` (`scripts/ai-pipeline:314`), which invokes ordinary auto-recovery when enabled (`scripts/ai-pipeline:155`).

  The prescribed error matches none of ai-recover’s hard rules (`scripts/ai-recover:137`). With the schedule already claimed and application work still dirty, recovery reaches its Claude decision session. A `commit_and_rerun` decision can then validate and commit the tree (`scripts/ai-recover:200`), defeating the promised terminal stop.

  **Concrete plan change:** Make preserved-work consistency failures terminal before ordinary recovery inference, preserving the arm and checkout. Add regressions with approved `AI_AUTO_RECOVER=1` and `MOCK_RECOVER=commit_and_rerun`, asserting one escalation, no recovery session, unchanged HEAD/files, and the arm retained.

- P17: The armed DONE checkpoint bypasses dependency setup before validation.

  **Location:** `.ai/tasks.md:735`, `.ai/tasks.md:744`.

  T011 requires the consumer to run before `tasks next` and immediately checkpoint a DONE task through the existing post-task path. That path begins with `ai-check`; it does not install dependencies. Existing startup dependency setup comes later and is conditional on `tasks next` returning a runnable task (`scripts/ai-run:606`).

  Consequently, a limited session that changes a dependency lockfile and marks its task DONE can resume into validation with stale dependencies. With the last task DONE, the existing setup condition also skips installation entirely. This produces a validation failure and ordinary recovery instead of the promised automatic checkpoint. The repository already contains a suitable gate fixture requiring installed dependencies to match `deps.lock` (`tests/test_workflow.py:9862`).

  **Concrete plan change:** After consuming the arm, run the existing bounded, guarded dependency setup before validating preserved DONE work, even when no runnable task remains. Add one-task regressions for DONE in the working queue and DONE already committed, with a changed dependency input. Assert installation precedes validation, completion needs no recovery decision, and installer failure commits nothing.

## MINOR findings

- P18: Later tasks still assert the superseded resume message.

  **Location:** `.ai/tasks.md:939`, `.ai/tasks.md:1047`.

  T011 now requires `Resuming preserved work of the usage-limit stop (T001).` (`.ai/tasks.md:739`). T016 and T015 still require exactly one occurrence of `Resuming preserved work of the usage-limit stop.` That literal does not occur in the new message.

  **Concrete plan change:** Update both acceptance criteria to the task-bound message, using the fixture’s bound task ID.

## Previous findings re-evaluated

Round 6’s P3 is addressed by T017’s task binding and T011’s status-based consumer, including committed-DONE trailing edits. P14 is addressed by resolving directory arguments before `ai_root`. P15 now correctly separates recovery’s pre-arm decision stop from an already armed pipeline resume.

The other previously reported scenarios remain explicitly covered by the revised tasks and acceptance criteria; they are not repeated.

## Validation and limitations

Inspected the instructions, spec, plan, all 17 tasks, state, handoff, dispositions, relevant documentation, source, tests, validation entry point, and revision history.

Observed checks passed:

- Task queue validation; all tasks specify a model.
- Three documentation consistency tests.
- Shell syntax checks for 13 files.
- AST parsing for eight Python modules.
- `git diff --check`.

An in-memory probe confirmed that the prescribed fail-closed reason bypasses the existing recovery hard rules.

The full `./scripts/ai-check` and integration fixtures were not run because they require filesystem writes. Proposed behavior remains unimplemented. No files were modified or network/MCP integrations invoked.