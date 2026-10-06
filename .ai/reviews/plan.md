<!-- Plan review of plan digest 6ce64ff07420b37532932fcf693ade0b5a736bdefe00f3cdd2271e00be4047b9; saved 2026-10-06T05:27:14Z. -->

# Plan review

Overall verdict: APPROVE WITH MINOR adjustment to T002’s regression-test instructions.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `783bd2248aae40f9aa151ff8b583235a69046e0a`

Scope: OR-01/OR-02 spec, plan, tasks, affected scripts and helpers, integration tests, validation configuration and evidence, documentation, and vault workflow notes. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

None.

## MINOR findings

- P7: Update the existing retry-sleep assertion for the intentionally earlier integrity stop.

  **Location:** `.ai/tasks.md:115–118`, `.ai/tasks.md:163–164`; `tests/test_workflow.py:1728–1734`.

  T002 correctly requires `publish_ready` after every failed push, before the retry wait. However, the existing dirty-push regression test explicitly expects a 20-second sleep. With the planned implementation, its hook dirties the checkout, the immediate post-push check stops, and `sleep.log` is never created. The existing assertion therefore fails despite correct behavior.

  **Concrete plan change:** Explicitly include updating this test to assert no retry sleep and exactly one push-hook invocation. Preserve its assertions for the cleanliness diagnostic, absent remote branch, and absent PR creation. Keep separate coverage proving harmless failed pushes still sleep and retry.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Task-queue validation passed.
- Documentation consistency tests: **3 passed**.
- Shell syntax: **13 files passed**.
- Python syntax: **3 files passed**.
- Stored baseline evidence records **168 tests passing** at `d6038f6`; this was not rerun.
- Current validation-stamp verification failed as stale.
- Full gate and integration tests were not run because they create writable fixtures and validation artifacts.

## Security and architecture concerns

The revised plan addresses prior findings P1–P6 in the inspected paths. Explicit models fit the tasks’ risks, dependencies are coherent, and workflow changes now include flow-chart updates in the same task. Authority-root checks remain configuration checks and do not establish OS isolation.

## Manual testing recommendations

After implementation, verify watchdog installation from outside Git and another checkout, refusal before agent launch, final-handoff mismatch diagnostics, and integrity escalation on the third failed push. Confirm the vault chart’s date and the handoff’s flow-chart statement.