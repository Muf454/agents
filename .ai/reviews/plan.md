<!-- Plan review of plan digest f18ab505182d458edd64af6d8c9ab8db75094321b0434fee8cd895d356bc14f1; saved 2026-10-07T10:46:58Z. -->

# Plan review

Overall verdict: APPROVE WITH MINOR IMPROVEMENTS
Finding counts: BLOCKER=0 MAJOR=0 MINOR=3

Reviewed HEAD: `f5403df49b78ccf3fa0ea39a25f6c43e2022dbf1`

Inspected repository instructions, spec, plan, tasks, state/handoff, affected scripts, prompt templates, tests, validation configuration, documentation, flow chart, and Git history. No files modified; no network or MCP integrations invoked.

The revised plan resolves the earlier worker import-path, permission, round-counting, model-selection, convergence-regex, and performance-acceptance issues. The corrected branch explanation matches local Git history.

## BLOCKER findings

None.

## MAJOR findings

None.

## MINOR findings

- P8: Runner acceptance omits error-only and skipped-test summaries.

  **Location:** `.ai/tasks.md:37–39`, `.ai/tasks.md:49–57`.

  The runner must parse unittest summaries, but acceptance covers ordinary failures and crashes without exercising `FAILED (errors=1)` or `OK (skipped=1)`. These are distinct output formats; rejecting a valid skipped-test run or misreporting error totals could escape the proposed tests.

  **Concrete plan change:** Add temporary-suite cases containing an ordinary test exception and a skipped test. Verify exit status, aggregated error/failure counts, complete exception output, and collected-versus-run count agreement.

- P9: History truncation does not define oversized-round behavior.

  **Location:** `.ai/tasks.md:97–111`, `.ai/tasks.md:169–195`.

  Dropping whole oldest rounds handles a long history, but does not define useful output when the newest round alone exceeds 6000 characters. Dropping that round would remove the most relevant context while convergence still requires an explanation based on earlier findings. The planned cap test verifies counting, not this rendering boundary.

  **Concrete plan change:** Define an oversized-round fallback that stays within the cap and preserves a reference to the original report. Tell triage to inspect original reports when truncation removes context needed to assess recurrence. Add a regression with a single oversized newest round, checking the hard cap, fallback reference, and unchanged uncapped count.

- P10: The handoff instructions omit the required coordinator timing evidence.

  **Location:** `.ai/tasks.md:218–220`; `.ai/current-plan.md`, “Human steps”; `.ai/project-spec.md`, “Acceptance”.

  T005 instructs the handoff to list approving the gate switch and timing one gate run, with everything else classified as automated. The spec instead requires three consecutive full parallel runs, matching the serial count and each finishing under 200 seconds, **before** the switch. Those runs are explicitly coordinator evidence outside the unattended tasks.

  **Concrete plan change:** Require the handoff to retain these three runs as outstanding coordinator work until their evidence is recorded. Once completed, link the recorded counts and timings and leave only the remaining approval/application steps under “Needs you.”

## Missing test coverage

Add the runner summary and oversized-history cases above. The planned three-round pipeline and interrupted-triage regressions otherwise address the important round-counting paths.

## Security and architecture concerns

No additional demonstrated concern in the inspected scope. Preserve frozen gate files, host-owned fix-round accounting, triage scope restrictions, and full-range implementation review. Explicit task models fit the assigned work.

The convergence design checks that an explanation exists; whether it correctly identifies recurring areas remains an agent judgment, as specified.

## Validation observed

- Discovery collected **229 tests**, matching `countTestCases()`.
- **Three documentation consistency tests passed.**
- Python syntax checks passed for the workflow helper, watchdog helper, and existing test module.
- Bash syntax checks passed for eight relevant scripts/gate templates.
- Task-queue validation and `git diff --check` passed.
- The checkout remained clean.

The full `./scripts/ai-check` and integration suite were not run because they require writable fixtures and workflow artifacts. No current validation stamp was available. These checks assess the existing baseline, not the proposed implementation.

## Manual testing recommendations

### Needs you

After implementation review, obtain and record the three required parallel-run measurements before approving the gate switch. Keep gate changes and merge under human control.

### Covered by automated tests

Worker imports and result aggregation, review-history rendering/counting, prompt isolation, convergence enforcement, and interrupted-triage recovery should be verified by the planned tests plus P8–P9.

This is plan approval with minor improvements, not implementation verification or human acceptance.