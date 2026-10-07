<!-- Plan review of plan digest 0e0bd79b77e1b623ea1a06fb397fc017cb56c35999dd58030aebd35f0195fd08; saved 2026-10-07T12:17:54Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `b64ac77ea93e6b19ae79f1c01708c6f57ad084f9`.

## BLOCKER findings

None.

## MAJOR findings

- P30: Notification appends can modify files outside `.ai/local` through hard links.

  **Location:** `.ai/tasks.md:70`, `.ai/tasks.md:86`; `.ai/project-spec.md:55`.

  T001 specifies appending directly to an existing `notifications.log`, protected by `O_NOFOLLOW`, a regular-file check, and a lock. These checks permit hard links. If an agent creates `notifications.log` as a hard link to a tracked source or gate file, the next notification appends JSON to that file. Atomic replacement during later trimming does not undo the modification.

  This violates target-file preservation and the requirement that observation failures leave pipeline outcomes unchanged. This is a planned vulnerability; no filesystem reproduction was performed during this read-only review.

  **Concrete plan change:** Update T001 and the spec so notification updates never modify the existing log inode: read the bounded retained records, append and trim in memory, then atomically replace the destination using an exclusively created temporary file under the existing lock and pinned directory descriptor. Add a hard-linked sentinel fixture proving that notifications leave the sentinel’s bytes unchanged and preserve the pipeline’s outcome.

## MINOR findings

- P31: T005’s targeted validation excludes its sanitizer tests.

  **Location:** `.ai/tasks.md:335`, `.ai/tasks.md:342`; `.ai/tasks.md:11`.

  T005 now requires `dashboard_sanitize_*` tests, but its targeted command selects only `dashboard_liveness`. It can report passing tests without exercising the security-sensitive helper added in this revision. This matters when the session’s full gate times out and targeted checks become its immediate validation evidence. The host’s full gate remains a later safeguard.

  **Concrete plan change:** Add a separate targeted invocation with `-k dashboard_sanitize`, requiring at least one test, alongside the liveness invocation.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Task-queue format/dependency validation passed.
- Planning diff whitespace check passed.
- **13 Bash syntax checks** and **3 in-memory Python syntax checks** passed.
- **3 documentation consistency tests** passed.
- Validation-stamp verification reported **no validation evidence**.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and integration suite were not run because they create repositories, locks, logs, and validation artifacts. Dashboard implementation tests do not exist yet.

## Scope, architecture, and coverage assessment

Inspected repository guidance, spec, plan, tasks, state/handoff, relevant docs and vault flow chart, Git history/diff, affected source, existing test fixtures, and validation configuration.

The previous P28 registration-placement and P29 model-assignment findings are addressed. Dependencies are ordered, every task specifies a model, and no failed implementation retry is recorded. The advisory dashboard, standard-library dependencies, and frozen gate-file boundary fit the requested scope.

The findings concern proposed behavior and validation, rather than demonstrated regressions in current application code. Flow-chart updates remain scheduled for T002/T003. Implementation also remains subject to the recorded efficiency-batch merge prerequisite.

## Manual testing recommendations

After implementation, observe two simultaneous tmux pipelines through pause, recovery, stop, and finish. Check stage highlighting, scrolling, expansion, resize, colors, and terminal restoration.

No files were modified; no network or MCP integrations were invoked. This review assesses plan readiness, not implementation correctness or human acceptance.