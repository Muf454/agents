<!-- Host evidence: HEAD fe6b8f4f664323dc7288f8cf795044b308b62a22; merge-base 662507102d51112163819c8a0bbc06706347c49a; saved 2026-10-05T13:00:09Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED — two branch-lifecycle defects remain.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=0

Reviewed HEAD: `fe6b8f4f664323dc7288f8cf795044b308b62a22`
Supplied base / merge-base: `662507102d51112163819c8a0bbc06706347c49a`

Inspected AGENTS.md, specification, plan, tasks, state, handoff, relevant documentation, Git history and scoped diff, affected source/tests, validation evidence, and the vault flow chart. The checkout was clean.

T015 implements host-recorded fix-round accounting and has relevant regression coverage. No additional defect was demonstrated in that change. Earlier findings M3 and M4 remain reproducible and retain their IDs. N3’s obsolete human todo and next action have been corrected. The findings below concern changes introduced within the supplied review range; no separate pre-existing defect is counted.

Validation observed/run:

- Stored validation reports **PASS** at `2026-10-05T12:55:23Z`, recorded at `2162f6fd782cb3fc6d044ca96cc3f4570db8c9ee`; its log records **161 tests passed**.
- Read-only validation-stamp verification passed at reviewed HEAD.
- **12 read-only tests passed**, covering documentation, tool contracts, model/todo rules, permissions entries, re-check parsing, and script executability. Writable integration fixtures were deliberately omitted.
- Bash syntax checks passed for **13 files**; Python AST checks passed for **three files**.
- Both findings reproduced using the actual helpers with in-memory storage.
- Read-only PR-body and finish-summary generation confirmed the flow-chart declaration and removal of the obsolete executable-bit todo.
- `git diff --check` reported trailing whitespace in `.ai/reviews/current.md:8`, an existing review artifact.

Limitations: The full `./scripts/ai-check` gate and integration suite were not rerun because they write repositories, locks, logs, and evidence. The reproductions demonstrate helper behavior; complete branch-transition pipeline scenarios were not executed. Live providers, GitHub, systemd, and physical upgrade failures were not exercised. The vault flow chart includes R1/R2/R3 and T015 with `updated: 2026-10-05`; same-session update history cannot be established from the repository diff. No files were written and no network/MCP integrations were invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M3 — Inherited dispute records block subsequent feature branches

**Location:** `scripts/lib/workflow.py:1147`, `scripts/lib/workflow.py:1241`; consumer: `scripts/ai-pipeline:143`.

**Problem:** Dispute authority is stored per branch, but `.ai/reviews/disputes.md` is tracked and inherited by subsequent branches. A new branch has no corresponding host records, so an unchanged, authentic inherited file fails verification.

**Impact:** After the human resolves and merges a disputed PR, a subsequent feature branch carrying that file cannot finish publishing. Depending on its review state, it stops during dispute reconciliation or the publish check. The suggested remedy—restoring the file from Git—preserves the mismatch.

**Evidence:** Using the actual `disputes_store`, `render_disputes`, and `disputes_verify` helpers with in-memory storage:

1. One authentic record verified on `feature/first`.
2. With unchanged dispute Markdown, switching the branch identity to `feature/next` failed with:

> `.ai/reviews/disputes.md does not match the dispute records the host wrote`

The new branch’s absent host store returns an empty record list, while verification requires the tracked file to be absent for that list.

**Recommended direction:** Distinguish historical disputes from disputes active for the current PR. Preserve provenance and integrity, and define a human-controlled archival transition where necessary. Keep active-PR disputes durable without making their inherited artifact block unrelated branches.

### M4 — Another branch’s pipeline erases interrupted triage recovery state

**Location:** `scripts/lib/workflow.py:782`, `scripts/lib/workflow.py:795`; consumers: `scripts/ai-pipeline:81`, `scripts/ai-pipeline:248`, `scripts/ai-pipeline:277`.

**Requirement:** R1 requires resumed triage to enforce its original scope, verify fresh dispositions, and count the round exactly once before implementation continues. T015 also requires preserving that completion protocol.

**Problem:** Every branch in a checkout shares `run.json`. Starting another branch’s pipeline overwrites it; an interrupted stage survives only when the immediately preceding manifest names the same branch.

**Impact:** Returning to the original branch loses its triage start HEAD and review digest. If triage committed dispositions and new TODO tasks before interruption, the checkout can be clean. Startup then skips `complete_stage` and proceeds to implementation, bypassing the original scope/freshness checks and leaving that round uncounted.

**Evidence:** An in-memory reproduction using the actual `run_manifest` helper:

1. Started `feature/first` and recorded an open triage stage.
2. Confirmed `run-manifest stage` returned that stage.
3. Started `feature/next`, then restarted `feature/first`.
4. Confirmed `run-manifest stage` returned empty.

The source calls `complete_stage` only when that query is populated, then runs pending tasks. T015’s per-branch fix-round records do not preserve the lost stage.

**Recommended direction:** Preserve interrupted manifests per branch, or refuse to overwrite another branch’s open stage until the human explicitly reconciles it. Add an integration regression covering committed triage records without the counted commit across this branch transition.

## MINOR findings

None found in the inspected scope.

## Missing test coverage

- A dispute file inherited by a subsequent feature branch after human resolution and merge.
- Starting another branch’s pipeline while the original branch has interrupted triage, then returning before its round was counted.

The inspected tests cover same-branch recovery/restarts, dispute persistence through later reviews, and per-branch completed-round counts. They do not cover these lifecycle transitions.

## Security concerns

No exploitable security defect was demonstrated in the inspected changes. M4 bypasses intended triage scope verification after its authoritative stage record is lost. The inspected permission and integrity checks do not establish complete isolation.

## Architecture concerns

M3 combines branch-specific authoritative storage with an inherited tracked artifact. M4 places resumable branch state in one overwriteable checkout manifest. Both need explicit lifecycle handling.

T015’s host-recorded accounting addresses the observed commit-subject counting problem, but does not resolve M4.

## Manual testing recommendations

In an isolated writable checkout:

- Resolve and merge a disputed PR, create a subsequent feature branch carrying its workflow records, and verify normal delivery.
- Interrupt triage after its dispositions/tasks commit but before its counted commit. Start another branch’s pipeline, return, and verify original scope checks, fresh dispositions, and exactly one counted round before implementation.
- Run `./scripts/ai-check` after the fixes and retain validation evidence for the resulting revision.

This review does not constitute human acceptance.