<!-- Plan review of plan digest 963df3514ddd179831021d7f7f516b7efeda6b7300b89fe3ca368403624580da; HEAD a48e3bdf44c7fd4a2400284ee0e91f34139e20a0; saved 2026-10-17T07:39:04Z. -->

# Plan review

Reviewed HEAD: `a48e3bdf44c7fd4a2400284ee0e91f34139e20a0`

Overall verdict: CHANGES REQUIRED before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=0

## BLOCKER findings

None.

## MAJOR findings

- P2: Restoring an interrupted schedule can leave watchdog stall suppression missing.

  **Location:** `.ai/tasks.md:223`, `.ai/tasks.md:252`, `.ai/tasks.md:294`; `scripts/lib/watchdog.py:119`, `scripts/lib/watchdog.py:443`.

  Scheduling persists the manifest before appending `pauses.log`. A kill between those operations leaves a pending schedule without its pause entry. The prescribed `limit-hold` path restores the observation and removes the error and marker, but never restores `pauses.log`. T002 suppresses stalls using only `paused_until(local)`, which returns zero without that entry. Two subsequent probes can therefore announce a stalled implementation while its scheduled relaunch is still days away.

  The proposed interrupted-scheduling tests start from a completed scheduling run, so they retain the pause entry and miss this case.

  **Plan change:** Make pending-wait restoration rebuild stall-suppression evidence through AT, or make the watchdog recognize pending host schedules directly. Add a regression with a persisted schedule and no pause entry, then recover and run two probes before AT; neither may emit ⛔ or launch an early retry.

- P9: Tree verification can be bypassed by the bookkeeping commit or an early resume path.

  **Location:** `.ai/tasks.md:237`, `.ai/tasks.md:337`, `.ai/tasks.md:348`; `scripts/ai-recover:149`, `scripts/ai-recover:165`.

  T012 verifies the saved tree only through `limit-arm`, called when the checkout remains dirty **after** recording stop leftovers. The existing leftovers block commits changes confined to `.ai/state.md`, `.ai/run-log.md` and `.ai/handoff.md`. A human edit to one of those files during the wait is therefore committed before verification; the resulting clean checkout skips `limit-arm` entirely. This contradicts the explicit promise to include bookkeeping changes in the binding and escalate with nothing committed.

  Clean checkouts whose HEAD changed during the wait also skip verification. The open-stage resume branch returns before reaching it.

  **Plan change:** Verify the scheduled HEAD/index/worktree binding immediately after claiming and passing authority checks, before any checkout mutation or resume branch. Define permitted host bookkeeping transitions only after that verification. Add regressions for a bookkeeping-only human edit, a clean changed HEAD, and an in-scope human edit during an open stage; each must stop without committing or starting a session.

- P10: The proposed tree digest ignores changes inside submodules.

  **Location:** `.ai/tasks.md:329`; `scripts/lib/workflow.py:2245`; `tests/test_workflow.py:9663`.

  T012 hashes a gitlink/submodule directory as `dir`. The parent index and HEAD do not change when someone edits files or creates a commit inside an initialized submodule. Consequently, those human changes leave the proposed digest unchanged and pass `limit-arm`. A later automatic checkpoint can stage the changed gitlink and absorb the human’s submodule commit.

  Submodules are supported by existing runner tests. The existing `tree_snapshot()` already recursively includes submodule HEAD, index and working contents, with additional handling for uninitialized submodules.

  **Plan change:** Reuse or extend the existing recursive snapshot implementation instead of treating directories as constants. Add digest and relaunch regressions for a changed submodule file and a changed submodule HEAD while the parent HEAD/index remain unchanged; recovery must preserve the changes and refuse automatic continuation.

## MINOR findings

None.

## Scope and validation

Inspected repository instructions, spec, revised plan, all thirteen tasks, latest dispositions, state, handoff, relevant documentation, affected scripts/helpers, installation logic, test fixtures and `.ai/validate`.

The revised plan covers P1, P3–P8. P2 and P9 remain incomplete in the cases above. These findings concern proposed behavior; implementation has not begun.

Observed checks passed:

- Task queue validation.
- Documentation consistency: **3 tests**.
- Shell syntax: **13 files**.
- Python AST parsing: **8 files**.

The full gate and fixture-based integration tests were not run because they require writes unavailable in this read-only review. These checks validate the baseline, not the proposed behavior.

After implementation, retain the planned supervised checks for real limit recovery, detached planning and PR draft ownership. No files were modified; no network or MCP integrations were invoked.