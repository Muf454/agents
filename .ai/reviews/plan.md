<!-- Plan review of plan digest 1c62b82b91e192a4e029c5dc789ff5ca83edea8384cfc0e737363385a0b8d725; saved 2026-10-07T12:13:30Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=0

Reviewed HEAD: `b4138fec03e052031c16440220f436f0a3f5fa91`.

## BLOCKER findings

None.

## MAJOR findings

- P28: Specify a registration hook placement that cannot read an uninitialized branch variable.

  **Location:** `.ai/tasks.md:191`; `scripts/ai-pipeline:109`, `scripts/ai-pipeline:113`; `scripts/lib/common.sh:3`.

  T003 specifies calling `ai_helper pipeline-register "$AI_ROOT" "$branch" || true` after `run-manifest start` and on resume. However, the actual script assigns `branch=$AI_START_BRANCH` only after the manifest start/resume block. Placing the hook immediately after the stated boundary therefore expands an unset `$branch` under `set -u`, terminating the pipeline before implementation. `|| true` cannot catch this shell expansion failure, violating the requirement that registration never change a run’s outcome.

  **Evidence:** A read-only Bash reproduction with the same variable initialization and planned invocation exited 127 with `branch: unbound variable`.

  **Concrete plan change:** Specify one shared invocation after successful manifest start/resume verification, using the already initialized `$AI_START_BRANCH`, or explicitly place it after `branch=$AI_START_BRANCH`. Extend acceptance coverage to verify registration and unchanged outcomes on both initial start and recovery resume, including a failing registry write.

- P29: T006 assigns security-sensitive terminal sanitization to `sonnet`.

  **Location:** `.ai/tasks.md:333`, `.ai/tasks.md:352`; `.ai/project-spec.md:82`; `.ai/current-plan.md:53`.

  T006 implements removal of terminal controls and escape sequences from agent-writable checkout data. The plan explicitly relies on this protection to prevent forged records from injecting terminal escapes. This is security work, but the task specifies `Model: sonnet`, contrary to the required `opus` assignment for security tasks.

  T001’s safe file readers do not provide this protection: safe filesystem access and safe terminal output are separate responsibilities.

  **Concrete plan change:** Move sanitization and its security tests into an `opus` task, letting T006 consume the completed helper, or change T006 to `Model: opus`. Explicitly verify sanitization of every displayed checkout-derived string, including project, branch, observation detail/note, checkout path, notifications, and last error.

## MINOR findings

None.

## Validation observed

- Requested HEAD confirmed; working tree clean before and after review.
- Task-queue validation passed.
- Planning diff whitespace check passed.
- **13 Bash syntax checks** and **3 in-memory Python syntax checks** passed.
- **3 documentation consistency tests** passed.
- Registration-hook shell failure reproduced without writing files.
- Validation-stamp verification reported **no validation evidence** in this checkout.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and integration tests were not run because they create files, repositories, locks, and validation artifacts. Dashboard implementation tests do not exist yet.

## Scope, architecture, and coverage assessment

Inspected repository instructions, spec, plan, tasks, state/handoff, relevant documentation, affected source and tests, validation configuration, Git history/diff, prior review, and the vault flow chart.

The advisory, read-only, standard-library design fits the requested scope. Dependencies are ordered and every task specifies a model. The earlier recovery-substage findings are addressed in the revised plan. No task’s own failed implementation retry is recorded.

The findings concern planned changes, not demonstrated regressions in existing code. Flow-chart updates are scheduled for T002/T003 and correctly remain pending. Implementation remains subject to the recorded efficiency-batch merge prerequisite.

## Manual testing recommendations

After implementation, observe two simultaneous tmux pipelines through pause, recovery, stop, and finish. Check highlighted stages, navigation, expansion, scrolling, resize, colors, and terminal restoration.

No files were modified; no network or MCP integrations were invoked. This review assesses plan readiness, not implementation correctness or human acceptance.