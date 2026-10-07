<!-- Plan review of plan digest 158d34543c9a722093a850185f30f3534023994a62efead0f28d7550e000fd9f; saved 2026-10-06T10:52:56Z. -->

# Plan review

Overall verdict: PROCEED with one minor regression-test improvement.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `02a910dae69a159f05ee3086c340bfb9903490ff`

Inspected repository instructions, spec, plan, all seven tasks, state/handoff, affected source and templates, relevant tests, documentation, Git history, vault notes, and validation evidence. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

None.

## MINOR findings

- P12: Explicitly test notification counting for a mixed handoff.

  **Location:** `.ai/tasks.md:227`; `tests/test_workflow.py:1274`; `tests/test_workflow.py:1850`.

  T004 explicitly tests PR ordering for the split and FINISHED wording when “Needs you” is None. It does not explicitly require a notification assertion when both subsections contain steps. Existing notification tests use legacy handoffs, so they cannot establish that the new format counts human steps correctly while excluding automated checks.

  **Concrete plan change:** Add a `manual_testing_render` case with two human steps and three named automated checks. Assert that `finish-summary` reports exactly two manual steps, excludes the automated checks from that count, and does not say “Nothing to test by hand.” This verifies FL-09’s central notification requirement.

## Assessment

The revision addresses P8–P11 at the planning level: dependency setup stops must escalate, preservation checks run after unsuccessful installers, submodule snapshots recurse, timer status requires enabled and active units, and the remaining-run-time cap has a regression scenario.

Task dependencies are coherent, every task specifies a model, and the integrity-sensitive dependency work uses `opus`. No failed implementation attempt is recorded for these TODO tasks. The frozen `.ai/bin` boundary and same-task flow-chart updates remain explicit.

No additional security or architecture finding was identified in the inspected scope. Host execution of package-manager code, the writable dependency stamp, and the limits on mid-run dependency installation are acknowledged design choices.

## Validation observed

- Requested HEAD confirmed; working tree clean; `git diff --check` passed.
- Task-queue validation passed.
- Python syntax: **3 files passed**.
- Bash syntax: **12 files passed**.
- Documentation consistency: **3 tests passed**.
- Stored baseline log reports **188 tests passed** at `9e11a11`, before planning.
- Current validation-stamp verification failed as stale.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and integration fixtures were not rerun because they require writable fixtures, locks, logs, and validation artifacts. The stored baseline does not validate this revision.

## Validation and human acceptance

Implement the planned regressions plus P12, then run the required full gate. Human acceptance should include a fresh-worktree run, confirmation that the opted-in timer is active, and inspection of the PR testing split and phone notifications.

This plan review does not constitute implementation verification or human acceptance.