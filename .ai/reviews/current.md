<!-- Host evidence: HEAD f8b3aef83e38832d937ce677f4e30a93c43907ee; merge-base 0818f20c4d236072815e24552ba779e058c7e1f0; saved 2026-10-07T18:36:59Z. -->

# Independent review

Overall verdict: PROCEED WITH MINOR FIXES — the efficiency features are substantially delivered, with four localized reporting, context, documentation, and test-isolation gaps.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=4

Reviewed HEAD: `f8b3aef83e38832d937ce677f4e30a93c43907ee`
Supplied base and merge-base: `0818f20c4d236072815e24552ba779e058c7e1f0`

Inspected repository instructions, specification, plan, tasks, state, handoff, previous review/dispositions, relevant documentation, scoped Git history/diff, affected source/tests, frozen runtime files, and the vault flow chart. The checkout was clean.

## Validation observed/run

- Stored validation reports **PASS**, exit 0, at `2026-10-07T18:31:54Z`, recorded against `abe04b76913e90261a2ebab156839c4c9b3c24d0`. Its log reports **272 tests in 124.0 seconds**, eight shards, **OK**.
- Independently verified that the validation fingerprint matches the reviewed checkout. Committed-content verification passed; all six tasks are marked DONE; installed toolkit files match their recorded hashes.
- Discovery collected **272 tests**. Independently ran **three documentation consistency tests**, all passing.
- **12 Bash syntax checks** and **six Python syntax checks** passed.
- Read-only, in-memory probes exercised runner failure/error aggregation, skipped/expected-failure parsing, oversized history rendering, and fixture environment forwarding.
- The actual history helper found one earlier recorded implementation review in the scoped range.
- `git diff --check` reported trailing spaces in the previous review and an extra blank line at the workflow guide’s end. These are not counted as findings.

Limitations: Did not rerun `./scripts/ai-check`, serial integration tests, or the full parallel suite because they create fixtures, locks, logs, and validation artifacts. Live provider permissions, systemd, installation, and publication were not exercised. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

The implementation shares uncapped history collection between review context and convergence counting. Implementation reviews retain the full review range, and round-three enforcement rejects missing, empty, multiline-only, and commented-out convergence text. The merge retains the common prompt before reviewer selection.

## MINOR findings

### P8 — Runner summary omits required failure/error totals

**Location:** `tests/run_parallel.py:108`; regression assertion: `tests/test_workflow.py:4463`.

**Requirement:** `.ai/project-spec.md:29` requires an aggregate `FAILED (failures=…, errors=…)` summary.

**Problem:** The runner lists failing shard numbers without aggregating unittest failure/error totals. Its test explicitly expects this alternative format.

**Evidence:** Fed actual unittest output containing one failure and one error, across two simulated shards, through the real parser and aggregation code. It exited 1 and preserved both tracebacks, but ended with:

```text
Ran 2 tests in 0.0s (2 shards, 2 collected)
FAILED (failing shards: 1, 2)
```

**Impact:** Failures still close the gate, but the reporting contract remains unmet.

**Recommended direction:** Aggregate failure/error totals while retaining separate crash and count-mismatch diagnostics. Add a mixed-failure/error regression across shards.

### P9 — Oversized latest history silently loses findings and dispositions

**Location:** `scripts/lib/workflow.py:944`.

**Requirement:** `.ai/project-spec.md:47` requires finding IDs, titles, and dispositions; the cap drops oldest rounds with an omission notice.

**Problem:** If the latest round alone exceeds the cap, the renderer slices raw Markdown at character 6000. It can remove dispositions and later findings without stating that the retained round is incomplete.

**Evidence:** Called the actual renderer with one round containing a 6100-character first title and a second accepted finding. Output was exactly 6000 characters, omitted both task dispositions and the second finding, and said `(0 earlier rounds omitted)`.

**Impact:** Review and triage receive incomplete context that appears complete. Uncapped round counting remains correct.

**Recommended direction:** Preserve IDs/dispositions by shortening titles, or explicitly identify partial content and reference the original report. Add a regression where the newest round alone exceeds the cap.

### P10 — Gate guidance remains contradictory and timing acceptance is undocumented

**Location:** `.ai/handoff.md:14`, `README.md:673`, `.ai/run-log.md:90`.

**Requirements:** T005 requires documentation to match the implementation. `.ai/project-spec.md:78` requires three consecutive parallel runs with matching serial counts, each under 200 seconds, recorded before the gate switch.

**Problem:** T006 correctly clears the obsolete gate-switch todo, but the handoff’s implementation summary and README still say the gate is serial. `.ai/validate` already runs the parallel runner.

The run log records “timing run 1 of 3,” followed by successful runs over changing suite sizes. It does not establish three consecutive qualifying runs of the same suite with a matching serial count, or record an approved waiver.

**Impact:** Operating guidance contradicts the actual gate, and the stated performance acceptance remains unverified.

**Recommended direction:** Reconcile README, handoff, and plan/spec with the approved coordinator switch. Record the required comparison and repeated measurements, or an explicit approved waiver. The recorded approval means this is not classified as an unauthorized gate change.

### N6 — Reviewer overrides leak into integration-test fixtures

**Location:** `tests/test_workflow.py:367`, `tests/test_workflow.py:955`; affected test: `tests/test_workflow.py:2124`.

**Problem:** Fixtures copy the parent environment without normalizing the newly supported `AI_REVIEWER` and Claude-review model/effort overrides. Tests that assume default reviewer selection therefore depend on exported user settings.

**Evidence:** Exercised the actual fixture setup and `tool()` environment construction with filesystem/Git operations mocked. Both `AI_REVIEWER=claude` and `AI_CLAUDE_REVIEW_MODEL=override-model` reached the child environment unchanged.

Source tracing shows that forced Claude selection bypasses Codex, while `test_review_context_first_review_has_no_previous_rounds` indexes the Codex prompt log. That log is absent on this path. The writable integration reproduction was not run.

**Reproduction in a writable checkout:**

```bash
AI_REVIEWER=claude python3 -m unittest discover -s tests -k review_context_first_review
```

**Impact:** A supported reviewer setting can make the toolkit gate fail for fixture configuration rather than product behavior. Model overrides similarly invalidate default-model assertions.

**Recommended direction:** Normalize reviewer-related environment settings in fixture setup, then apply explicit per-test overrides. Add coverage proving that exported user settings do not alter unrelated fixtures.

## Missing test coverage

- Aggregate runner failure/error totals.
- A newest history round that alone exceeds the cap.
- Documentation assertions against the actual gate.
- Fixture isolation from exported reviewer settings.
- T006’s requested fallback-context assertion: existing context tests inspect Codex prompts; fallback tests do not assert previous rounds and the delta.
- Recorded repeated timing and serial-count comparison.

## Security concerns

No additional exploitable defect was demonstrated in the inspected paths. Checked reviewer allowlist filtering, denial logging, checkout-change rejection, host-state boundaries, and review-record handling. History remains separate from host-owned fix-round authority.

The previous concern based solely on missing explicit `Write` permission is not carried forward: documentation reports that scoped `Edit` permits probe creation through Write in live `dontAsk` mode. Live enforcement was not independently verified here.

## Architecture concerns

The efficiency work adds no external dependency and reuses one history routine. Frozen runtime adoption remains a coordinating step, consistent with the stated non-goal.

**Flow chart updated:** the vault note includes review context, convergence, reviewer selection, and recovery behavior, with `updated: 2026-10-07`. Repository history cannot establish same-session vault-edit timing.

Pre-existing issue, excluded from finding counts: the workflow guide’s claim that setup installs nothing predates this range and conflicts with its existing optional watchdog installation behavior.

## Manual testing recommendations

### Needs you

- Inspect representative repeated findings to confirm that Claude creates a design task when the same concern persists.
- Confirm the real Claude CLI permits scratch-probe creation and denies writes outside the intended directory.
- Approve any waiver of the specified timing acceptance if the required evidence will not be supplied.

### Covered by automated tests

- Existing tests cover runner failures/crashes, import errors, history/dispositions, review context, convergence enforcement, interrupted triage, and wrapped handoff bullets; their stored full-suite result is PASS.
- Add regressions for the gaps listed above, including fallback prompt context.
- Run `./scripts/ai-check` after fixes in a writable checkout.
- Record three consecutive default-worker runs under 200 seconds and compare counts with serial execution of the same revision.

This review does not constitute human acceptance.