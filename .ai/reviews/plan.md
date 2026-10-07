<!-- Plan review of plan digest cec50d28ebdb553e3dba5e86aa45fd7ba4768fe6c1cddf62274d6b0f653970f4; saved 2026-10-07T11:20:43Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=5 MINOR=3

Reviewed HEAD: `f400448d1acf3afb95b02f7bcee2b2c98e1371c8`

Inspected repository instructions, spec, plan, tasks, state/handoff, affected scripts and helpers, relevant tests, validation entry points, documentation, Git history, and the vault flow chart. No files modified; no network or MCP integrations invoked. New finding IDs continue after the previous review’s P1–P10.

## BLOCKER findings

None.

## MAJOR findings

- P11: Outer stop labels overwrite the actual failed substage.

  **Location:** `.ai/tasks.md:34`, `.ai/tasks.md:98`; `scripts/ai-pipeline:308`; `scripts/ai-run:292`.

  T002 records Checks before post-task and final validation. However, any failure returned by `ai-run` reaches the pipeline’s `stop implementation`. T001 then normalizes `implementation` to Build, overwriting the recorded Checks stage. Recovery escalation receives the same coarse label and repeats the overwrite. Dependency setup failures have the equivalent Setup → Build problem.

  The dashboard would therefore highlight the wrong box for ordinary validation and setup failures, despite recording their active stages correctly.

  **Concrete plan change:** Define precedence between a recorded substage and an outer phase label. Preserve the current substage when the pipeline reports failure of its nested implementation runner; use label normalization as a fallback. Add pipeline fixtures for post-task validation failure, final validation failure, and dependency installation failure, including recovery escalation, asserting Checks or Setup remains highlighted.

- P12: Best-effort writers can block the workflow indefinitely.

  **Location:** `.ai/tasks.md:39`, `.ai/tasks.md:41–47`, `.ai/tasks.md:63`; `.ai/tasks.md:89–91`.

  The prescribed notification open uses `O_WRONLY|O_APPEND|O_CREAT|O_NOFOLLOW`. Opening a FIFO this way blocks until a reader connects, before the subsequent `fstat` can reject it. Consequently, the specified FIFO acceptance case cannot reliably return. Reading a previous observation can similarly block on a FIFO.

  The new `flock` operations also have no acquisition deadline. An agent-writable notification lock can be held indefinitely. Returning exit status 0 or adding `|| true` only helps after the helper returns; neither prevents a pipeline or watchdog from hanging.

  **Concrete plan change:** Require nonblocking opens followed by descriptor-based regular-file checks, and bounded lock acquisition with retry. On deadline or unsafe input, warn and return successfully without changing the run’s outcome. Add timeout-bounded tests for FIFO observations/logs and locks held by another process, including a caller-level test proving the pipeline continues.

- P13: Checking `.ai/local` before pathname writes does not provide the promised symlink safety.

  **Location:** `.ai/tasks.md:26–27`, `.ai/tasks.md:37–45`; `scripts/lib/watchdog.py:463`.

  An `lstat` check followed by operations using `.ai/local/...` leaves a directory replacement race. Another process can replace `.ai/local` with a symlink between the check and the open or rename. `O_NOFOLLOW` protects the final path component, not intermediate directories. The same issue applies to a symlinked `.ai` ancestor.

  A read-only probe confirmed that `O_NOFOLLOW` still follows an intermediate symlink. Destination-file protection therefore does not establish the task’s “never through an agent-planted symlink” guarantee.

  **Concrete plan change:** In T001, open and validate the `.ai` and `local` directories without following symlinks, then perform reads, temp creation, lock operations, replacement, and cleanup relative to pinned directory descriptors. Add deterministic tests that replace a directory after validation and verify outside sentinel files remain unchanged. Keep this security/concurrency work on `opus`.

- P14: Dashboard reads need bounded handling of unsafe file types.

  **Location:** `.ai/tasks.md:152–164`, `.ai/tasks.md:198`; `scripts/lib/watchdog.py:90–95`.

  T003 reads agent-writable records and explicitly reuses watchdog marker helpers. The existing `marker_snapshot()` opens the marker normally and reads it to EOF. A FIFO marker can block the dashboard; a symlink to a device or an excessively large record can make reading unbounded. Notification, observation, task, and error reads need equivalent protection.

  Output sanitization and malformed-JSON tests do not catch these failures. One damaged checkout could freeze the whole dashboard, including its refresh and quit handling.

  **Concrete plan change:** Specify a shared bounded reader that opens nonblocking, validates the descriptor as a regular file, limits bytes read, and handles decoding errors. Preserve watchdog process-identity and marker-reread semantics without blindly inheriting its unrestricted reads. Put security-sensitive reader work in T001 (`opus`) and reuse it in T003. Test FIFO/device-link inputs, oversized records, and invalid UTF-8 while another healthy checkout remains visible.

- P15: The planning revision already breaks a required existing gate assertion.

  **Location:** `.ai/handoff.md:18–19`; `tests/test_workflow.py:3399–3403`; `.ai/tasks.md:7–8`, `.ai/tasks.md:301`.

  The existing test requires the handoff to contain `## Flow chart\nFlow chart updated`. The revised handoff removed that declaration. Invoking the test’s first assertion without its writable fixture setup reproduced the failure.

  This is a planning-revision regression, preceding implementation. Every task requires a passing gate, but the queue does not schedule its repair before T001, and T005 only specifies updating manual-testing content.

  **Concrete plan change:** Restore a truthful flow-chart declaration expected by the existing test before implementation starts. Require T002 to update that declaration alongside its vault note, and have T005 audit the resulting PR wording. Preserve the existing assertion.

## MINOR findings

- P16: Clarify the concurrent notification retention test.

  **Location:** `.ai/tasks.md:64–67`.

  The test requires retaining all 200 new messages while also suggesting a “small” test-only retention limit to force trimming. A limit below 200 makes those expectations incompatible.

  **Concrete plan change:** Prefill the log with 200 older messages, then append 100 messages from each concurrent writer using the production limit. Assert that the final log contains exactly the 200 new message IDs, once each, with valid JSON. This forces trimming without adding a runtime environment override.

- P17: Define rendering for absent or unknown observations.

  **Location:** `.ai/tasks.md:167–168`, `.ai/tasks.md:196–199`, `.ai/tasks.md:236`.

  T003 deliberately produces legacy runs with no observation and stage `unknown`, but T004 says the active box always comes from the observation’s stage. Its rendering tests cover valid observations only. Behavior for `none`, `unknown`, and a missing observation remains unspecified.

  **Concrete plan change:** Require these cards to render without selecting a flow box, with a clear unknown-stage indication. Add shared-renderer and executable-output tests for legacy and malformed-observation snapshots.

- P18: Explicitly assign Codex styling to Re-check.

  **Location:** `.ai/project-spec.md:88`; `.ai/tasks.md:234–235`.

  The spec assigns Re-check to Codex blue. T004 assigns the combined Triage box to Claude and mentions only changing its label for `recheck`, leaving its role styling ambiguous.

  **Concrete plan change:** Explicitly map `recheck` to the Triage box with `active_codex` styling and add a renderer assertion for that mapping.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Planning diff whitespace check passed.
- Task-queue validation passed.
- Python syntax checks passed for both existing library modules and the test module.
- Bash syntax checks passed for 13 scripts/validation files.
- Documentation consistency: **3 tests passed**.
- Existing flow-chart test: **first assertion failed**, reproduced without invoking writable fixture setup.
- Read-only `O_NOFOLLOW` probe confirmed intermediate symlinks are followed.
- Validation-stamp verification failed because this checkout has **no validation evidence**.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and integration fixtures were not run because they create files, locks, repositories, and validation artifacts. Dashboard implementation tests do not exist yet. Earlier gate results do not validate this revision.

## Missing test coverage

Add the nested-failure stage tests, bounded writer/reader tests, directory-replacement tests, and legacy/Re-check rendering tests described above. Repair the existing handoff assertion failure before the first implementation gate.

## Security and architecture concerns

The stdlib-only, advisory dashboard fits the spec. The remaining security concerns concern newly introduced host filesystem operations and reads; advisory status must remain separate from authorization.

Every task specifies a model. T001 appropriately uses `opus` for locking and safe writes. Any shared security-sensitive reader work added for P14 should also run under `opus`. No implementation retry is recorded.

## Manual testing recommendations

After automated checks pass, inspect two simultaneous tmux runs through build, checks, pause, recovery, stop, and finish. Verify selection, expansion, scrolling, resizing, role colors, and terminal restoration.

This review assesses implementation readiness; it does not establish implementation correctness or human acceptance.