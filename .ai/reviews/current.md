<!-- Host evidence: HEAD 81db302bed287fe21723b08a7b31847d16411f11; merge-base 4fea72d51a543528c79a0afab423b935757d6acf; saved 2026-10-23T06:33:36Z. -->

# Independent review

Overall verdict: APPROVE — no new actionable findings in the inspected scope; previous accepted findings are addressed.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=0

Reviewed HEAD: `81db302bed287fe21723b08a7b31847d16411f11`

Supplied base and verified merge-base: `4fea72d51a543528c79a0afab423b935757d6acf`

## Scope and validation

Inspected repository instructions, specification, plan, relevant task records, state, handoff, review dispositions, documentation, Git history, the full supplied change range, affected source and relevant tests. Also inspected changes since `68ac201c132afc084763bebc3d4e3cb8219f0964`. The checkout was clean.

Recorded validation:

- `.ai/local/validation.json` records PASS at `2026-10-23T06:27:46Z`, on revision `c7cf7521a98087bc938a797b1b8a337b51099690`.
- Its referenced log reports **1,227 tests passed** in 991.8 seconds.
- Independent `stamp verify` confirms that evidence matches the reviewed checkout.

Checks independently completed:

- Task queue validation and `git diff --check` passed.
- Python AST checks across nine files and shell syntax checks across 14 files passed.
- All four documentation-consistency tests passed.
- Read-only discovery found 1,227 tests, with the temporary-directory initializer suppressed.
- Repeated executions of the actual watchdog `main()`, with external effects mocked, launched no recovery for human-stopped, stop-requested or finished records with a due schedule.
- The actual `ai_stop_child()` terminated a real TERM-ignoring fixture process and cleared child tracking.
- The actual state updater, with writes captured in memory, reported zero remaining for DONE/SKIPPED and one remaining when TODO was added.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because this review uses a read-only sandbox. No files were written and no network/MCP integrations were invoked.

### Previous findings

- **M4 / T329:** Addressed. The watchdog checks the current record before scheduled recovery; cancellation also removes the pending schedule. Added regressions exercise repeated probes after cancellation and the record guard independently.
- **M5 / T330:** Addressed. Shutdown escalates a surviving tracked child to KILL. If it still survives, the owner remains available, records a pending stop and waits before reporting completion. The gate-broken completion branch follows that wait. Added regressions cover TERM resistance and pending shutdown.
- **N4 / T331:** Addressed. Remaining-task counts now exclude statuses in `FINISHED`; the regression covers both completed and incomplete mixed queues.

No pre-existing defects are counted in this report.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

None found in the inspected scope.

## Missing coverage

No additional required regression gap was identified in the inspected paths. The recorded integration tests provide coverage beyond the write-free checks independently executed here. Real CLI and systemd behavior remains unverified by this review.

## Security concerns

No additional demonstrated security defect was found in the inspected gate checks, process identity handling, host records or task authorization. Existing documented limitations concerning hooks and boundary-based integrity checks remain applicable.

## Architecture concerns

The changes retain Bash and Python standard-library dependencies and follow the existing checkout-lock, host-record and run-ID ownership design.

**Flow chart updated:** the inspected vault note has `updated: 2026-10-23` and includes schedule cancellation, child escalation and pending-stop behavior. Same-session edit timing was not independently established.

## Manual testing recommendations

### Needs you

- Verify Ctrl-C and `--stop` shutdown and notifications with real CLIs.
- Cancel a paused run and confirm the installed watchdog timer launches no recovery afterward.
- Confirm a detached run survives terminal closure and its printed stop command ends it.
- Confirm an authorized skip remains valid on another branch or worktree.

### Covered by automated tests

The recorded suite covers cancelled relaunch probes, stop-record guards, TERM-ignoring publication children, pending shutdown, mixed DONE/SKIPPED counts, lifecycle ownership, task controls and detach arguments.

Reviewing does not constitute human acceptance.