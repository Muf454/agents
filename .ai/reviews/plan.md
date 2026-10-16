<!-- Plan review of plan digest 05325f13c3f01979619cc830282272c6a83602e0c903e5dfb3c2a145f92d1e3e; HEAD e5e68b0b75e0ed3812d63ba0fec5049b9a121652; saved 2026-10-14T21:18:05Z. -->

# Plan review

Scope: HEAD `e5e68b0b75e0ed3812d63ba0fec5049b9a121652`, round 2.

Overall verdict: Suitable for implementation with the minor plan improvements below.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

## BLOCKER findings

None.

## MAJOR findings

None.

## MINOR findings

- P8: Correct the notification-log assumption and test retention rollover.

  **Location:** `.ai/tasks.md:641`; `scripts/lib/workflow.py:3496`.

  T009 describes the log as append-only and says every notification changes its size. The actual writer atomically replaces the log and retains only 200 lines. Once retention fills, repeated identical notifications can leave its size and content unchanged.

  The proposed inode/mtime fingerprint already accommodates replacement, so this does not reopen P3.

  **Concrete plan change:** Describe the existing replacement and retention behavior accurately. Add a regression using `notify-log` on a full 200-line log with repeated identical messages and unchanged timestamps, asserting that the fingerprint changes despite unchanged displayed events and file size.

- P9: Add coverage for the concurrent runner’s cleanup requirement.

  **Location:** `.ai/tasks.md:354`; `.ai/tasks.md:363`.

  T004 explicitly requires terminating running batch processes and joining threads on interruption or worker exceptions. Its acceptance tests cover ordinary failures, discovery errors and count mismatches, but none exercises these new cleanup paths. Those tests could pass while interruption leaves workers or subprocesses running.

  **Concrete plan change:** Add deterministic tests with blocked batches: interrupt the runner and separately inject a worker launch exception. Require bounded termination, a failing exit status and cleanup of the running batch processes.

## Previous findings re-evaluated

P1–P7 are addressed by the current plan:

- T011 repairs interrupted revision queues before the queue-dependent checks.
- T005 adds execution probing, fallback and cleanup for tmpfs selection.
- T009 fingerprints notification identity independently of displayed text.
- T004 specifies `opus`.
- The handoff now declares `Flow unchanged`; T002 updates it when the flow changes.
- T004 explicitly updates the documentation consistency contract.
- T006 preserves existing test IDs while permitting additional tests.

## Validation observed and limitations

Inspected the instructions, spec, plan, queue, dispositions, state, handoff, relevant source, tests, documentation and `.ai/validate`.

Observed:

- HEAD matches the requested scope; working tree is clean.
- Task queue validation passes.
- Shell syntax checks pass for 13 files.
- All three documentation consistency tests pass.
- Test discovery collects 619 tests.

The full `./scripts/ai-check`, fixture integration tests and CI timing measurements were not run because this sandbox permits only filesystem reads. Implementation must still satisfy the planned regression tests and full gate; the performance target requires the documented human CI check.

No additional security, authorization or data-integrity findings were identified in the inspected plan. This review is not human acceptance.