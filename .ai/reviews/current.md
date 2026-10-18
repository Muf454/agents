<!-- Host evidence: HEAD e3c724e38d7b984219d4c0181094050d8f9db5db; merge-base edc3dc645116166472720cebd2d982b649ab14ff; saved 2026-10-18T07:42:58Z. -->

# Independent review

Overall verdict: PASS WITH MINOR FINDING — prior findings resolved; one notification requirement remains unmet.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `e3c724e38d7b984219d4c0181094050d8f9db5db`

Supplied base and verified merge-base: `edc3dc645116166472720cebd2d982b649ab14ff`

## Scope and validation

Inspected repository instructions, specification, plan, task records, state, handoff, review dispositions, relevant documentation, Git history, full production-code diff, and selected affected tests. Reviewed changes since `da84933830d7f33769adfcdd35c9ca276a803006` and the broader supplied range. The checkout was clean.

Validation observed:

- `.ai/local/validation.json`: PASS at `2026-10-18T07:40:16Z`, recorded at `d9b95042b9bfcdc7a303ef6740aae4ef0cbadaee`.
- Referenced log: **965 tests passed in 596.0 seconds**.
- Independently verified that the validation fingerprint matches the reviewed content.

Checks independently run:

- Task queue validation.
- Python AST parsing and shell syntax checks across 14 scripts/templates.
- Three documentation-consistency tests.
- `git diff --check`.
- In-memory executions of the actual cap-exhaustion branch and completed-before-acknowledgement branch, with external behavior mocked.

The full `./scripts/ai-check` and integration fixtures were not rerun because they require writes. No files were written or network/MCP integrations invoked. Live provider, systemd, and GitHub behavior remain untested.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N2 — Cap-exhaustion notification omits the known reset time

**Location:** `scripts/ai-recover:268–269`.

**Requirement:** `.ai/project-spec.md:85` requires escalation after exhausting `AI_LIMIT_RELAUNCH_MAX` to name the reset time.

When `limit-schedule` refuses another relaunch, recovery already holds the parsed timestamp in `at`, but its escalation only says:

```text
usage limit again after 1 relaunch(es) in this run.
Next: rerun ai-pipeline after the reset.
```

**Impact:** The human receives a stop requiring manual action without the promised time for retrying.

**Evidence:** Executing the actual scheduling branch with `limit-stop` returning `Claude 2000000000`, a recovering timer, and a refused schedule produced the message above. Existing cap-exhaustion coverage checks escalation and schedule consumption, but does not assert that the notification includes the reset time.

**Recommended direction:** Include the formatted `at` value in the cap-exhaustion escalation and extend its regression test to assert it. This is an incomplete requirement in the newly introduced cap path.

## Previous findings re-evaluated

- **M1:** Resolved. Conversion ownership now requires the initial draft-state result to equal `false`. The added regression covers a failed lookup on a human draft followed by a later clean run.
- **N1:** Resolved. A zero-exit child with its own `planning/done` observation now reports successful launch. Tests cover matching completion, absent observation, another PID, and nonzero completion.

Also inspected schedule hold/claim, tree verification, task-bound preservation, armed-stop handling, startup ordering, dispute reconciliation, detached logging, and draft-record revocation. No rejected finding is re-raised, and no separate pre-existing defect is reported.

## Missing test coverage

Add an assertion that cap-exhaustion notifications contain the parsed reset time. Broader integration coverage was inspected and its recorded results verified, but was not independently rerun.

## Security concerns

No additional demonstrated security defect found in the inspected changes. The M1 human-draft ownership issue is addressed.

## Architecture concerns

The implementation retains minimal dependencies and host-side authority records. Recovery remains complex, with explicit transition contracts and substantial regression coverage.

**Flow chart updated:** the vault note has `updated: 2026-10-18` and includes planning, relaunch, and draft-ownership flows. Same-session update timing was not independently established.

## Manual testing recommendations

### Needs you

- Verify real usage-limit pause/resume after upgrading installed copies and reinstalling watchdog timers.
- Verify detached planning and human-draft preservation against actual providers.

### Covered by automated tests

- Recovery transitions, tree/task binding, planning acknowledgements, safe logging, dashboard states, and draft ownership.
- Add the reset-time notification assertion described in N2.

Reviewing does not constitute human acceptance.