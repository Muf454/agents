<!-- Host evidence: HEAD 845b4f925d5f5a0e227a069913eceed052052678; merge-base 662507102d51112163819c8a0bbc06706347c49a; saved 2026-10-05T15:29:10Z. -->

# Independent review

Overall verdict: NO CHANGES REQUIRED in the inspected scope; ready for human testing.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=0

Reviewed HEAD: `845b4f925d5f5a0e227a069913eceed052052678`  
Supplied base / merge-base: `662507102d51112163819c8a0bbc06706347c49a`

Inspected repository instructions, specification, plan, tasks, state, handoff, relevant documentation, scoped Git history/diff, affected source/tests, validation evidence, and the vault flow chart. The checkout was clean.

The implementation addresses the requested tool contract, permissions, model/todo guidance, triage recovery, publish checks, rejected-finding re-checks, durable disputes, toolkit upgrades, and documentation changes. No additional defect was demonstrated in these inspected areas.

Prior findings **M3 and M4 are resolved**:

- **M3:** `scripts/lib/workflow.py:1260` distinguishes inherited disputes from active branch records. Verification preserves inherited content, while PR generation counts only current-branch disputes. Regression tests cover normal publication after inheritance, tampering, and new disputes.
- **M4:** `scripts/lib/workflow.py:778` and `scripts/lib/workflow.py:879` preserve interrupted triage per branch. Regression tests cover branch transitions, legacy migration, unreadable records, and completion before implementation resumes.

Earlier parsing, upgrade rollback, executable-mode, and flow-chart-description fixes remain present. No separate pre-existing defect is counted.

Validation observed/run:

- Stored evidence reports **PASS**, exit 0, at `2026-10-05T15:23:38Z`, recorded at `75be82d967056f7dcb6d4ca5157b412017739b3c`. Its log records **168 tests passed**.
- Validation-stamp verification passed at reviewed HEAD.
- **13 read-only tests passed**, covering permissions, shared prompts, model/todo guidance, re-check parsing, executable scripts, and documentation.
- Bash syntax checks passed for **12 files**; Python syntax checks passed for **three files**.
- In-memory checks using the actual helpers confirmed stage survival across branch transitions, rejection of malformed stage JSON, historical dispute handling, and rejection of inherited-content tampering.
- Task-queue checks and `git diff --check` passed.

Limitations: The full `./scripts/ai-check` gate and writable integration fixtures were not rerun because they create repositories, locks, logs, and evidence. Live providers, GitHub, systemd, and physical filesystem failures were not exercised. The vault chart includes the changed workflow and `updated: 2026-10-05`; its same-session edit history cannot be verified from the repository diff. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

None found in the inspected scope.

## Missing test coverage

- Upgrade rollback failures are reported by the implementation but lack a dedicated regression test.
- Live permission enforcement, provider output, GitHub draft conversion, and watchdog recovery remain manual integration checks.
- The foreground gate timeout instruction is present, but its exact timeout value is not explicitly asserted by the shared-contract test.

These coverage limitations do not establish additional defects.

## Security concerns

No additional exploitable security defect was demonstrated. The new read-command permissions retain the documented ability to read outside the project. Allowlist checks and integrity checks do not establish OS isolation.

## Architecture concerns

The prior branch-lifecycle mismatches are addressed. Documented limitations remain around reusing branch names with old host dispute records or abandoned triage stages; these cases fail closed and require human reconciliation.

## Manual testing recommendations

In an isolated writable project:

- Complete the handoff’s inherited-dispute and interrupted-triage branch-transition scenarios.
- Verify publish-hook mutations stop delivery and successful delivery leaves origin at local HEAD.
- Exercise upgrade preview, apply, and filesystem-failure recovery.
- Run a supervised permission smoke test and watchdog recovery test.

Flow chart updated: the vault note reflects the inspected workflow, and the handoff declaration is carried into the generated PR body.

This review does not constitute human acceptance.