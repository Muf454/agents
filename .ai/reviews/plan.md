<!-- Plan review of plan digest 4b8de92023cfad1a13cdabd31d97945b17193c9b106af9c8d098f9707190de65; saved 2026-10-07T12:02:46Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `82369e63a611b5276c2c4163ce0149636c0b97a2`.

Inspected repository instructions, spec, plan, tasks, state/handoff, prior review, affected source, existing tests, validation scripts, relevant documentation, Git history/diff, and the vault flow chart. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

- P23: Unexpected recovery exits would be displayed as idle.

  **Location:** `.ai/tasks.md:224–226`, `.ai/tasks.md:276–279`; `scripts/ai-recover:77–88`.

  T004 adds observations for recovery start, validation, and `escalate`, but omits recovery’s existing EXIT handler. On TERM, INT, HUP, or an unexpected command failure, that handler announces a stop and removes the pipeline marker without updating `last-error`.

  After the planned recovery-start observation, the original error is older than the observation. Once the handler removes the marker and recovery exits, T005’s rules see no live runner, no crash marker, `state=recovering`, and an older error. They therefore select `idle`, despite the announced stop.

  **Evidence:** A read-only probe executed the actual EXIT handler with all side effects mocked. Exit 143 announced STOPPED and removed the marker. Applying the proposed status rules to the resulting timestamps and state produced `idle`.

  **Concrete plan change:** Add a best-effort `observe stop '' <unexpected-exit reason>` inside the handler’s existing guarded failure branch, preserving the current substage. Add recovery-fixture tests for handled signals and unexpected failures, asserting `state=stopped`, dashboard status `needs_you`, preserved stage, unchanged exit outcome, and one stop notification.

- P24: T005 assigns new concurrency-sensitive liveness logic to sonnet.

  **Location:** `.ai/tasks.md:254`, `.ai/tasks.md:260–278`, `.ai/tasks.md:305–308`; `.ai/current-plan.md:28–30`.

  T005 must implement PID-reuse checks, marker re-reading during concurrent removal, orphan-child handling, and marker-free process discovery. Its explicit model is `sonnet`.

  T001 currently supplies bounded reads and descriptor metadata, but does not own the liveness decision protocol. The existing watchdog implementation cannot simply be called unchanged: `marker_snapshot()` uses an ordinary pathname open, conflicting with the dashboard’s required bounded descriptor-based reads. Consequently, T005 still requires concurrency-sensitive adaptation. Under the requested model policy, this requires `opus`.

  **Concrete plan change:** Move the bounded marker/liveness helper and its PID-reuse, marker-removal, and orphan-child tests into T001 on `opus`. Let T005 on `sonnet` consume that tested interface. Alternatively, explicitly change T005 to `opus`.

## MINOR findings

- P25: The curses smoke test does not exercise navigation or resize behavior.

  **Location:** `.ai/tasks.md:364–391`.

  T006 requires selection, scrolling, expansion, resize handling, and terminal restoration on exceptions. Its automated interaction test only sends `q`; pure renderer tests cannot verify viewport behavior or terminal cleanup after failure.

  **Concrete plan change:** Extend the pty coverage with enough cards to overflow the viewport, arrow-key navigation and Enter, a terminal resize, and an injected exception. Assert that selection remains visible and the terminal is restored. Keep tests bounded and independent of live providers.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Task-queue validation passed.
- Planning diff whitespace check passed.
- **13 Bash syntax checks** and **3 Python syntax checks** passed.
- Documentation consistency: **3 tests passed**.
- Recovery EXIT-handler probe confirmed the P23 execution path.
- Validation-stamp verification failed: **no validation evidence exists in this checkout**.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and writable integration fixtures were not run because they create files, repositories, locks, and validation artifacts. Dashboard implementation tests do not exist yet.

## Security, architecture, and scope assessment

The advisory, stdlib-only dashboard fits the spec. T001 appropriately uses `opus` for path safety and locking. Every task specifies a model; no failed implementation retry is recorded.

The flow-chart update is accurately marked pending T002/T003. No additional pre-existing defect was demonstrated in the inspected scope.

## Manual testing recommendations

After implementation and automated validation, inspect two simultaneous tmux pipelines through pause, recovery, stop, and finish. Verify navigation, expansion, scrolling, resizing, role colors, and terminal restoration.

This review assesses plan readiness, not implementation correctness or human acceptance.