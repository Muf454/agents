<!-- Host evidence: HEAD 5b8d86b759819bc6ae78a18850fdff6d5319fcc2; merge-base ba330ef04b94ee86ea8ecf3a4e8dc3ace0e6c200; saved 2026-10-08T13:00:40Z. -->

# Independent review

Overall verdict: REQUEST CHANGES — FL-04 is substantially implemented, but two host-guard gaps remain.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `5b8d86b759819bc6ae78a18850fdff6d5319fcc2`  
Supplied base: `c7d4deea62c4743e4212270c88ea2fa5b39bead5`  
Inspected diff: `ba330ef04b94ee86ea8ecf3a4e8dc3ace0e6c200..5b8d86b759819bc6ae78a18850fdff6d5319fcc2`

Inspected repository instructions, specification, plan, tasks, state, handoff, review/disposition records, relevant documentation, Git history, affected source/tests, validation evidence, and the vault flow chart. The checkout was clean.

## Validation observed/run

- Stored evidence reports **PASS**, exit 0, at `2026-10-08T12:53:27Z`, against `7c7d1ec844789a6adcd753275305c061022a019a`. Its log reports **359 tests in 226.5 seconds**, eight shards, **OK**.
- Independently verified that the validation fingerprint matches this checkout. Changes after the recorded validation revision affect only excluded workflow bookkeeping.
- Committed-content verification and task-completion checks passed.
- Test discovery collected **359 tests**.
- Independently ran **three documentation consistency tests**, all passing.
- Syntax checks passed for **12 Bash files** and **four Python files**.
- Read-only shell probes exercised the actual pipeline control-flow block and review/retry functions with external commands mocked.
- `git diff --check` passed.

Limitations: Did not rerun `./scripts/ai-check` or integration tests because they write fixtures, locks, logs, and validation artifacts. The probes establish control-flow defects; they do not constitute live-provider integration runs. No project files were written and no network/MCP integrations were invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — Stored needs-human decisions can be bypassed before implementation

**Requirement:** Spec R5 requires that while the current plan report has a revision record containing needs-human rows, no implementation session starts. The prescribed clearance is a human answer followed by a hand-run plan review producing a new report.

**Location:** `scripts/ai-pipeline:376`, `scripts/ai-pipeline:379`, `scripts/ai-pipeline:440`.

**Problem:** `plan_decision_check` runs only inside the optional plan-review loop. That loop is skipped with `--skip-plan-review` or whenever any task is DONE. The implementation loop then starts without checking the stored decision.

**Evidence:** Executed the actual pipeline block with mocked helpers representing an outstanding needs-human decision and incomplete tasks:

```text
plan_review=no, tasks_untouched=yes:
implementation agent reached
decision checks: 0

plan_review=yes, tasks_untouched=no:
implementation agent reached
decision checks: 0
```

The existing needs-human tests exercise the enabled, untouched-task path and miss both bypasses.

**Impact:** The durable human-decision gate becomes dependent on optional review settings and queue status. An unresolved scope or irreversible-operation question can remain recorded while implementation starts.

**Recommended direction:** Check stored decisions unconditionally before startup paths that can launch agents, and before implementation-loop entry. Preserve the check inside the plan loop. `--skip-plan-review` should skip the optional review, without clearing a separate recorded decision. Add regressions for both bypasses.

### M2 — Format retries reset the checkout baseline while retaining the original scope

**Requirement:** Spec R4 excludes checkout-integrity failures from format retries. T009 also requires checkout-integrity verification before retrying.

**Location:** `scripts/ai-review:121`, `scripts/ai-review:197`, `scripts/ai-review:199`, `scripts/ai-review:336`.

**Problem:** Every `run_review` invocation captures a new `start_head`. Between the first call and the retry, format checking and notification run without preserving the first call’s checkout baseline. A committed checkout change during that interval is therefore accepted as the retry’s new baseline.

The retry still receives the original scope prompt. Code-review publication also retains the original outer `$head`.

**Evidence:** Executed the actual `run_review` and retry wrapper with Git/provider/storage commands mocked and host logging redirected to `/dev/null`. Simulating a HEAD change during the notification, with a clean tree afterwards, produced:

```text
between-attempt checkout HEAD changed; tree remains clean
publish: original HEAD=original, current HEAD=changed
exit: 0
```

Both per-call integrity checks pass because the second call adopts the changed HEAD. Existing mutation tests cover changes during either reviewer call, not between calls.

**Impact:** A retry can review a different checkout from its stated scope and reach publication with the original revision binding. Subsequent pipeline freshness checks may reject that stale report, but the review command itself does not enforce the required integrity boundary.

**Recommended direction:** Capture one expected revision for the entire review operation and require both attempts to use it. Recheck after notification and before publication. Stop if HEAD or checkout cleanliness changes. Add a between-attempt committed-mutation regression for plan and code reviews.

## MINOR findings

### N1 — Convergence guidance excludes the new default-limit extra round

**Requirement:** Spec R6 and T010 require documentation and the flow chart to match the implemented workflow.

**Location:** `docs/workflow.md:373`; the vault flow chart’s “Convergence rule” note repeats the restriction.

**Problem:** The guide says round-three triage is “only reachable with `--max-fix-rounds` ≥ 3.” FL-04 now permits a third triage at the default limit of 2 when verified findings fall.

**Evidence:** `scripts/ai-pipeline:479` permits the extra round at that limit. `scripts/lib/workflow.py:877` requires convergence text for round three regardless of the configured limit. `test_extra_fix_round_falling_counts_get_one_round_then_draft` explicitly exercises three triages with `--max-fix-rounds 2`.

**Impact:** Operators receive incorrect guidance about when the convergence requirement applies.

**Recommended direction:** Update the guide and flow note to include supervised extra rounds. Add a documentation assertion tied to this behavior.

## Missing test coverage

- Outstanding needs-human decisions combined with `--skip-plan-review`.
- Outstanding needs-human decisions when an existing task is DONE and another remains pending.
- A clean committed checkout change between malformed output and its format retry, for both review modes.
- Accurate convergence guidance for an extra round at the default fix-round limit.

The inspected tests otherwise provide substantial coverage of reservations, crash recovery, escalation models, dispositions, verified trends, reviewer attribution, and malformed output.

## Security concerns

M1 weakens the human-decision boundary; M2 weakens review provenance. No additional exploitable defect was demonstrated in the inspected paths.

Revision sessions use a narrow tool set and explicit editable paths, with host-side scope and gate checks. Actual provider permission enforcement remains a live-testing limitation.

## Architecture concerns

The implementation adds no dependency and keeps authoritative reservations, outcomes, and trends outside the checkout. History remains contextual rather than authoritative. The two MAJOR findings concern guard placement and operation-wide integrity.

**Flow chart updated:** The vault note has `updated: 2026-10-08` and covers the new supervisor flow. N1 identifies one remaining inconsistency. Repository history alone cannot verify same-session timing of external vault edits.

Pre-existing issue, excluded from finding counts: `README.md:710` still describes serial discovery as what the gate runs today, although `.ai/validate` uses the parallel runner. This wording predates the reviewed range.

## Manual testing recommendations

### Needs you

- After fixes and automated checks, perform the handoff’s disposable-project trial with real Claude and Codex: revision, clean re-review, notification, needs-human stop, crash recovery, and clearance through a hand-run plan review.
- Confirm actual revision-session permissions restrict edits to the intended plan records.

### Covered by automated tests

- Existing tests cover ordinary supervision, durable decision recovery, reservations, crash windows, escalation, falling-count extensions, and review-format handling; their stored suite result is PASS.
- Add regressions for M1, M2, and N1.
- Run `./scripts/ai-check` in a writable checkout after fixes.

This review does not constitute human acceptance.