<!-- Plan review of plan digest 2f0dccd32670e5957e125d5efece9181f0d45df2177548953f42cea3637c9f26; HEAD 86df81599a696087a84919cad49c3bfbbcd7af0a; saved 2026-10-21T21:33:41Z. -->

# Plan review — batch 11

Scope: `HEAD=86df81599a696087a84919cad49c3bfbbcd7af0a`, tasks T301–T322.

Overall verdict: REVISE BEFORE IMPLEMENTATION
Finding counts: BLOCKER=0 MAJOR=4 MINOR=1

## BLOCKER findings

None.

## MAJOR findings

- P2: Signal forwarding still omits blocking publication commands.

  **Location:** `.ai/tasks.md:5658`; `scripts/ai-pipeline:249`, `:255`, `:679–719`.

  T318 wraps runners, reviewers, validation and retry sleeps, but leaves `git push`, `git ls-remote` and GitHub CLI calls blocking in the foreground. A PID-only TERM cannot run the pipeline’s trap until these commands return. A stalled connection or push hook can therefore defeat the promised prompt human stop. The retry-sleep test does not exercise this case.

  **Plan change:** Extend forwarding to blocking publication commands, retaining child identity in the parent even when capturing command output. Add offline tests with sleeping fake `git push` and `gh` processes; signal only the pipeline PID and verify prompt termination and human-stop records.

- P12: The existing log launcher rejects every proposed pipeline log name.

  **Location:** `.ai/tasks.md:6201–6202`, `:6218`; `scripts/lib/workflow.py:5069–5084`.

  T313 passes `pipeline-<stamp>-<hex>.log` to `exec-logged`. Its existing `EXEC_LOG_NAME` accepts only `plan-<stamp>-<hex>.log`, so it exits before starting the pipeline. T313 neither specifies extending this validation nor lists `workflow.py` among its affected modules. Direct evaluation of the existing expression confirmed the rejection.

  **Plan change:** Include the narrowly scoped launcher change in T313. Accept both intended prefixes while preserving exclusive creation and path protections. Add coverage for both valid prefixes and invalid names.

- P13: Duplicate shutdown writes discard the specific escalation kind.

  **Location:** `.ai/tasks.md:5284–5290`, `:5918–5922`; `scripts/ai-pipeline:186–188`.

  T320 writes an escalation in both `stop()` and `ai_die()`, but the existing non-recovery `stop()` always calls `ai_die()`. T305 consumes the hint on the first write. For example, `task_blocked` is written with task IDs and actionable answers, then overwritten by the second `write other`, which has no remaining hint. The final record loses the classification the feature must provide.

  **Plan change:** Define one escalation writer for this shutdown chain, or explicitly make repeated writes preserve the established classification. Test the final record after process exit for both blocked-task and plan-review stops.

- P14: The validation rewrite loses the output logger’s failure status.

  **Location:** `.ai/tasks.md:5506–5510`; `scripts/ai-check:47–52`.

  T304 explicitly takes the result only from the validation child after replacing the pipeline with a process substitution. Today, a failing `tee` makes validation fail. Waiting for the substitution ensures completion but does not automatically propagate its exit status. A successful validator with a failed logger can therefore produce exit 0 and a PASS stamp with incomplete evidence.

  **Plan change:** Capture and check both statuses before recording the stamp, preserving the existing failure behavior. Add a regression with a successful validator and failing fake `tee`, asserting a nonzero exit and no PASS stamp.

## MINOR findings

- P15: Run IDs can collide during repeated starts by the same process.

  **Location:** `.ai/tasks.md:5163–5169`, `:5193`; `.ai/project-spec.md`, assumption B17.

  Whole-second time plus PID gives identical IDs for two starts using the same PID within one second. The prescribed atomic write then replaces the earlier record. This also makes the 23-start retention scenario dependent on fixture timing.

  **Plan change:** Guarantee uniqueness under the host lock using a nonce, sequence or finer timestamp, and update the ID format consistently. Test repeated starts with a fixed clock and PID.

## Validation observed

- Confirmed the requested HEAD and clean working tree.
- Inspected guidance, spec, plan, tasks, prior review/dispositions, state/handoff, relevant documentation, affected source, schemas, fixtures and validation entry points.
- `python3 -B scripts/lib/workflow.py tasks check` passed.
- Python AST parsing passed for nine source/test files.
- `bash -n` passed for fifteen scripts and validation entry points.
- File-free reproductions confirmed delayed traps during foreground commands and independent validator/logger exit statuses.

The full gate and integration tests were not run because their fixtures require filesystem writes. Historical gate results do not validate this proposed implementation. No files were modified; no network or MCP integrations were invoked.

## Scope and remaining acceptance

Earlier findings P1 and P3–P11 are addressed by the revised plan; P2 remains partially unresolved. All current batch tasks specify models, with no additional model-assignment findings.

The principal risks are process lifecycle correctness, host-record consistency and preservation of validation evidence. After implementation, retain the planned human checks for Ctrl-C, detached stopping, watchdog recovery suppression and committed skips across branches/worktrees. Review approval is not human acceptance.