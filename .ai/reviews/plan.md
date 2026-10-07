<!-- Plan review of plan digest 98f198555ec77bcf27a5d2805ec0c1af15a463361c8b84082798bd1d73b5b4d4; saved 2026-10-07T12:09:29Z. -->

# Plan review

Overall verdict: APPROVE WITH MINOR IMPROVEMENTS
Finding counts: BLOCKER=0 MAJOR=0 MINOR=3

Reviewed HEAD: `df0aefd1f762808bcf2d2914ad3357c40e40f243`

Inspected repository instructions, specification, plan, task queue, state/handoff, affected source and tests, prompt templates, validation configuration/evidence, relevant documentation, Git history/diff, and the vault flow chart.

T001 is already partially implemented at this revision; T002–T005 remain planned. Findings retain the earlier review’s IDs. No files were modified, and no network or MCP integrations were invoked.

## BLOCKER findings

None.

## MAJOR findings

None.

## MINOR findings

- P8: Runner acceptance does not enforce the required failure/error summary.

  **Location:** `.ai/project-spec.md:29`, `.ai/tasks.md:37`, `.ai/tasks.md:50`; existing implementation: `tests/run_parallel.py:112`, `tests/test_workflow.py:3860`.

  The spec requires an aggregate `FAILED (failures=…, errors=…)` summary. T001’s acceptance criteria check failure exit status and traceback output without asserting those totals. The implemented runner instead prints `FAILED (failing shards: 1)`, and its regression explicitly expects that format.

  An in-memory probe using an actual unittest error summary confirmed that the runner exits 1 and prints the traceback, but omits aggregate error/failure counts. This is a localized reporting gap; failure still closes the gate.

  **Concrete plan change:** Amend T001 to aggregate and assert failure/error totals, retaining separate diagnostics for crashes and count mismatches. Add ordinary exception, mixed failure/error, and skipped-test cases. The skipped summary is currently accepted correctly, but lacks regression coverage.

- P9: History truncation leaves oversized-round behavior undefined.

  **Location:** `.ai/tasks.md:118`, `.ai/tasks.md:132`, `.ai/tasks.md:215`.

  Dropping whole oldest rounds does not specify what happens when the newest round alone exceeds 6000 characters. Dropping it removes the most relevant context; retaining it exceeds the cap. Existing planned tests do not require a useful fallback or explain how triage obtains omitted evidence.

  **Concrete plan change:** Define a capped fallback preserving the round number and review commit reference. Tell reviewers and triage to inspect original reports when omitted context affects their assessment. Add a single oversized newest-round regression checking the cap, fallback reference, and unchanged uncapped count.

- P10: T005 could remove outstanding coordinator timing requirements from the handoff.

  **Location:** `.ai/tasks.md:239`; required evidence: `.ai/current-plan.md:46`, `.ai/project-spec.md:78`.

  T005 instructs the handoff to list approving/applying the gate switch and timing one gate run, with everything else classified as automated. The spec requires three consecutive full parallel runs, matching the serial count and each finishing under 200 seconds, before switching the gate.

  The current handoff correctly retains that requirement. The run log reports one coordinator measurement, so the final task must preserve the remaining obligation.

  **Concrete plan change:** Require T005 to retain the three-run requirement until qualifying evidence is recorded. Once complete, link the counts and wall times and list only the remaining human steps.

## Missing test coverage

Add aggregate runner-summary and oversized-history cases described above. The planned pipeline and interrupted-triage tests otherwise cover the important convergence-counting paths.

## Security and architecture concerns

No additional demonstrated concern in the inspected scope. Explicit task models fit their risks, including the interrupted T001 retry. Preserve frozen gate files, host-owned fix-round accounting, triage scope restrictions, and full-range implementation review.

The convergence check validates that an explanation exists; assessing repeated areas remains agent judgment, as specified. Planned same-task flow-chart updates cover T003 and T004.

## Validation observed

- Discovery collected **236 tests**.
- **Three documentation consistency tests passed**.
- Python syntax checks passed for four relevant files.
- Bash syntax checks passed for six relevant scripts/gates.
- Task-queue validation and scoped `git diff --check` passed.
- In-memory runner probes exercised real summary parsing and aggregation with mocked subprocess I/O.
- The checkout remained clean.

Stored host validation reports **FAIL** at predecessor `d92c621`: one handoff assertion failed among 236 tests. HEAD changes that assertion; a passing full gate at HEAD was not independently observed. The run log reports a coordinator parallel run of 236 tests in 129 seconds.

The full gate and writable integration fixtures were not rerun because they create files and workflow artifacts.

## Manual testing recommendations

Retain and record the required coordinator timing evidence before approving the gate switch. Run the full gate in a writable environment after implementation.

This review is plan approval with minor improvements, not implementation verification or human acceptance.