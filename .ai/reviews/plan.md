<!-- Plan review of plan digest 5a35a8ca8f7abd561b0f66d54ed83e85c1ca419e7c339cfbe32611c96a3da4cb; HEAD 2c1e273a61e2a59266a3d09d4f5bb7b36e3e5c38; saved 2026-10-21T21:04:57Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=1 MAJOR=8 MINOR=2

Reviewed HEAD: `2c1e273a61e2a59266a3d09d4f5bb7b36e3e5c38`

Scope: T201–T213, checked against repository instructions, source, tests, documentation, and `.ai/validate`.

## BLOCKER findings

- P1: Event recording would execute helpers after detecting a compromised gate.

  **Location:** `.ai/tasks.md:5417`, `.ai/tasks.md:5515`, `.ai/tasks.md:5562`.

  T206 specifies an unconditional `ai_event` wrapper; T208 invokes it from pipeline stop and recovery escalation paths. Those paths also handle gate tampering. Existing `ai_observe` and `ai_notify_log` deliberately skip helpers when `AI_GATE_BROKEN` is set (`scripts/lib/common.sh:197–220`). The proposed wrapper would execute the potentially modified `workflow.py` during that stop. Direct calls to the proposed category and totals helpers have the same risk.

  **Plan change:** Guard every telemetry helper invocation when the gate is known unsafe, including argument preparation. Extend the existing tampered-helper regressions to assert that event, category, manifest, and totals helpers never execute after detection. Explicitly permit missing telemetry for these security stops.

## MAJOR findings

- P2: Follow-up batches still cannot enter supervised plan revision.

  **Location:** `.ai/tasks.md:5147`; `scripts/ai-run:476`; `scripts/lib/workflow.py:3613`.

  T201 changes only the pipeline’s review-entry predicate. If that review finds a significant problem, `ai-run --revise-plan` still calls `tasks untouched` and rejects any queue containing a DONE task, including historical tasks already DONE at the base. Interrupted revision queue repair has the same assumption. The new acceptance tests cover entering review, but not revising a failing review.

  **Plan change:** Apply the base-relative eligibility rule throughout plan revision and its recovery path while preserving historical DONE blocks. Add an end-to-end fixture with historical DONE tasks, a MAJOR plan review, successful revision, re-review, and subsequent implementation.

- P3: Rotation cannot safely reuse the outcome log’s inode lock.

  **Location:** `.ai/tasks.md:5405–5408`; `scripts/lib/workflow.py:3963–3969`.

  The existing append pattern opens the log and locks that file descriptor. Renaming the locked file does not transfer its lock to the replacement. A waiting writer can retain the archived inode while another writer locks the new live file. Subsequent rotation can then lose writes or replace an archive still being written. The existing attempt-counter implementation explicitly documents this replaced-inode problem at `scripts/lib/workflow.py:3997–3999`.

  **Plan change:** Specify a separate, stable lock file acquired before opening or rotating event files. Define how readers obtain a consistent view of both files. Add a synchronized multi-process regression that forces waiting writers across rotation and verifies every event appears exactly once.

- P4: Rotation can discard another project’s still-active run.

  **Location:** `.ai/project-spec.md:145–149`; `.ai/tasks.md:5406–5408`.

  The log is host-wide, but rotation preserves only the writing event’s run. Suppose runs A and B are active: B rotates, leaving A’s earlier events only in the archive; B rotates again before A writes. The archive is replaced and A’s events disappear while A is still running. This happens even with perfectly serialized writers.

  **Plan change:** Define retention for all active runs sharing the state root, including paused recovery runs, rather than only the current writer. Add a two-project fixture where B rotates twice while A remains active and verify both runs retain their complete histories.

- P5: Ruling events collide with the event discriminator.

  **Location:** `.ai/tasks.md:5403`, `.ai/tasks.md:5603`, `.ai/tasks.md:5616`.

  Every event needs top-level `kind: ruling`, but T210 also passes `kind=queue-order` and expects that value in `kind`. A flat JSON record cannot represent both. Overwriting the discriminator makes `read_events()` discard the record as an unknown event kind; preserving it loses the ruling category.

  **Plan change:** Reserve envelope fields and name the ruling field separately, such as `ruling_kind`. Update the schema, CLI, documentation, and tests to assert both `kind == "ruling"` and the specific ruling category, including successful reader round-tripping.

- P6: The planned ruling hook misses two ruling implementations.

  **Location:** `.ai/tasks.md:5603`; `scripts/lib/common.sh:389–426`.

  `ai_ruling_rows()` handles queue-order and task-sections rows only. Disposition and flow-line rulings write their run-log rows directly in `ai_disposition_ruling()` and `ai_flow_line_ruling()`. Adding events only to `ai_ruling_rows()` cannot satisfy “every BR-01 ruling,” including T210’s flow-line acceptance criterion.

  **Plan change:** Add event hooks to all three row-writing paths, or introduce one shared emitter used by them. Test queue-order, task-sections, disposition-cell, and flow-line rulings, and verify refused or repeated claims emit nothing.

- P7: Run completion events omit successful paths and precede actual PR completion.

  **Location:** `.ai/tasks.md:5562`; `scripts/ai-pipeline:632–663`, `scripts/ai-pipeline:726–730`.

  T209 emits successful `run end` only after the PR record commit. Successful `--no-pr`, missing-origin, and missing-`gh` paths all call `finish()` elsewhere and would remain open indefinitely. On the PR path, the proposed end event precedes the final push, which can still fail and trigger recovery or terminal escalation.

  **Plan change:** Emit successful completion from the shared `finish()` path after required publishing work succeeds, with explicit results for local-only finishes. Require exactly one terminal end event and test every finish path plus a failed final push. Cover safe terminal failures that bypass `stop()` as well.

- P8: Run ownership cannot reliably be inferred from branch and append time.

  **Location:** `.ai/tasks.md:5404`, `.ai/tasks.md:5649`; `scripts/lib/workflow.py:1736–1742`, `scripts/lib/workflow.py:4257`.

  The manifest survives pipeline completion. Looking up its ID solely by branch therefore tags a later standalone command with a completed run, contradicting A8’s `run: null` requirement. Outcome attribution has another failure: crash reconciliation writes `time: now()` when a later runner starts, although the attempt belongs to the earlier run. Time-window matching assigns that crash to the new run or creates overlapping candidates.

  **Plan change:** Establish explicit active pipeline/recovery context for event tagging and carry run ownership into new task/review outcomes and attempt markers. Preserve compatibility for historical records with a documented fallback. Test standalone commands after completion, consecutive runs on one branch, and a crash reconciled during a later run.

- P9: Existing allowance tests contradict the new default mode.

  **Location:** `.ai/tasks.md:5328`; `tests/test_workflow.py:10979–10999`.

  T204 requires existing allowance tests to pass with only contract-text adjustments. Those tests seed gates of 300 or 900 seconds without an override and expect an increased session limit. Under the proposed `auto` behavior, both cases become targeted mode with zero allowance. The remaining-run-time test likewise expects a limit above its base timeout.

  **Plan change:** Explicitly migrate these regressions: set `AI_SESSION_GATE=full` where testing allowance growth and capping, and retain separate assertions that slow-gate `auto` sessions receive no allowance. Include these existing tests in T204’s targeted validation.

## MINOR findings

- P10: Several regression selectors match no existing tests.

  **Location:** `.ai/tasks.md:5230`, `.ai/tasks.md:5488`, `.ai/tasks.md:5705`.

  Static inspection found zero existing matches for `run_parallel`, `gate_seconds`, `outcomes_report`, `ai_status`, and `session_allowance`. For example, existing runner tests use `parallel_runner`, and timing tests use `gate_time`. These commands cannot establish the claimed existing regression coverage.

  **Plan change:** Replace them with verified selectors or explicit test names. Keep the nonzero-test-count requirement, and distinguish new-test selectors from existing regression selectors.

- P11: The reusable task format does not provide the new targeted-check contract.

  **Location:** `.ai/tasks.md:5351`; `templates/.ai/tasks.md:33`; `templates/.ai/prompts/plan.md:12`.

  Runner instructions will require `Targeted:` lines, but the reusable task example and task-producing prompts only require generic validation commands. Existing valid queues can contain no such lines, leaving the session’s required checks undefined.

  **Plan change:** Update task-format and planning/triage guidance to identify targeted checks separately from the full gate. Define compatible behavior for older queues without those labels, and test that the instructions agree.

## Validation and limitations

- Inspected the relevant shell/Python implementations, fixture machinery, existing regressions, templates, and gate entry point.
- Shell syntax checks and Python AST parsing passed for inspected files.
- Verified test-selector counts statically without importing test modules.
- Did not run `./scripts/ai-check`, `.ai/bin/ai-check`, or unittest suites: their fixtures require writes prohibited by this read-only review.
- Historical gate results in the handoff were not independently reproduced.
- No files were modified; no network or MCP integrations were invoked.

The findings concern planned changes or existing assumptions those changes must update. Earlier batches were inspected only where they affect this plan.

## Manual testing recommendations

After the fixes and upgrade, observe one real targeted-mode run and compare `ai-status --metrics` with its raw outcome/event records. Confirm the session skips its full gate, the host gate decides DONE, and local-only completion closes the run correctly.