<!-- Host evidence: HEAD 3eb87051e6bf02ad37fbef16e45cbea9f1e6722b; merge-base 662507102d51112163819c8a0bbc06706347c49a; saved 2026-10-05T12:23:29Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED — two branch-lifecycle defects and one stale handoff issue remain.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `3eb87051e6bf02ad37fbef16e45cbea9f1e6722b`  
Supplied base / merge-base: `662507102d51112163819c8a0bbc06706347c49a`

Inspected AGENTS.md, specification, plan, tasks, state, handoff, relevant documentation, Git history and scoped diff, affected source/tests, validation evidence, and the vault flow chart. The checkout was clean.

The previous review’s M1, M2, N1, and N2 have corresponding source fixes and regression coverage. They are not counted again. The findings below concern this change; no separate pre-existing defect is counted.

Validation observed/run:

- Stored validation reports **PASS** for the reviewed HEAD at `2026-10-05T12:15:02Z`; its log records **154 tests passed**.
- Read-only validation-stamp verification passed.
- Three documentation tests passed.
- Directly ran two parser regression methods and the script-executability method without their writable fixture setup; all passed.
- Bash syntax checks passed for 12 files; Python AST checks passed for three files.
- `git diff --check` passed.
- Ran in-memory reproductions using the actual dispute and run-manifest helpers.
- Generated the PR body and finish summary read-only.

Limitations: The full `./scripts/ai-check` gate and integration suite were not rerun because they create repositories, logs, locks, and evidence. Branch-lifecycle reproductions mocked filesystem storage; complete pipeline scenarios remain to be exercised in an isolated writable checkout. No project files were written and no network/MCP integrations were invoked. Live providers, GitHub, systemd, and physical upgrade failures were not exercised. The flow chart contains R1/R2/R3 and `updated: 2026-10-05`; its same-session update history cannot be established from the repository diff.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M3 — Inherited dispute records block subsequent feature branches

**Location:** `scripts/lib/workflow.py:1146`, `scripts/lib/workflow.py:1184`; consumer: `scripts/ai-pipeline:141`.

**Problem:** The host dispute store is keyed by the current branch, but `.ai/reviews/disputes.md` is a tracked file inherited by later branches. A new branch has no matching host store, so an authentic inherited file fails verification.

**Impact:** After the human resolves a disputed PR and merges it, a subsequent feature branch carrying its workflow records cannot complete dispute reconciliation or publishing. The error recommends restoring the file from Git, which preserves the same mismatch.

**Evidence:** An in-memory reproduction using the actual helpers verified one record on `feature/first`. With unchanged Markdown and `current_branch()` changed to `feature/next`, verification failed with:

> `.ai/reviews/disputes.md does not match the dispute records the host wrote`

This follows directly from the new branch returning an empty record list while the inherited Markdown remains present.

**Recommended direction:** Distinguish immutable historical records from disputes active for the current PR. Preserve origin information and verification, and provide an explicit human-controlled archival transition if needed. Do not automatically resolve disputes within the active PR.

### M4 — Starting another branch’s pipeline erases interrupted triage recovery state

**Location:** `scripts/lib/workflow.py:782`, `scripts/lib/workflow.py:795`; consumers: `scripts/ai-pipeline:81`, `scripts/ai-pipeline:246`.

**Requirement:** R1 requires resumed triage to enforce its original scope, verify fresh dispositions, and count the round exactly once before implementation continues.

**Problem:** All branches in a checkout share one `run.json`. Starting a run on another branch overwrites that manifest and retains an interrupted stage only when the previous manifest names the same branch.

**Impact:** Returning to the original branch loses its triage start HEAD and review digest. If triage already committed dispositions and new TODO tasks but stopped before the counted commit, the pipeline can implement those tasks without completing or counting that round. Its original scope check is also skipped.

**Evidence:** Using the actual `run_manifest` helper with in-memory storage:

1. Started `feature/first` and supplied an open triage stage.
2. Confirmed `run-manifest stage` returned that stage.
3. Started `feature/next`, then restarted `feature/first`.
4. Confirmed `run-manifest stage` returned empty.

The pipeline calls `complete_stage` on startup only when that query is populated.

**Recommended direction:** Preserve interrupted manifests per branch, or refuse to overwrite an open stage belonging to another branch until the human explicitly reconciles it. Add a regression covering committed triage records without the counted commit across this branch transition.

## MINOR findings

### N3 — The finish notification requests an already-completed executable-bit fix

**Location:** `.ai/handoff.md:129`, `.ai/handoff.md:132`; consumer: `scripts/lib/workflow.py:1332`.

**Problem:** The handoff still asks the human to make `scripts/ai-task` executable and lists T013 as the next action, although the reviewed HEAD contains that fix.

**Impact:** The generated FINISHED notification gives the human obsolete work and contradicts the completed task queue.

**Evidence:** Git records `scripts/ai-task` as `100755`; the executable-mode check passes. Read-only `finish-summary` generation nevertheless includes:

> Run `chmod +x scripts/ai-task` (and commit the mode)

**Recommended direction:** Refresh the handoff’s implementation summary, human todos, and next action to match the reviewed revision.

## Missing test coverage

- An authentic dispute file inherited by a subsequent feature branch after human resolution and merge.
- Switching away from interrupted triage, starting another branch’s pipeline, and returning before the original round was counted.
- Final delivery instructions remaining consistent with completed handoff tasks.

Existing tests cover same-branch restarts and dispute durability through later reviews, but do not cover these branch transitions.

## Security concerns

No exploitable security defect was demonstrated in the inspected changes. M4 can bypass the intended triage scope verification after its host stage record is lost. The previous parser issue is fixed; the inspected integrity checks and allowlists do not establish complete isolation.

## Architecture concerns

M3 combines branch-specific authoritative storage with a shared tracked artifact. M4 stores resumable branch state in a single overwriteable checkout manifest. Both need explicit lifecycle handling. The inspected upgrade rollback addresses the prior compatibility finding without adding dependencies.

## Manual testing recommendations

In an isolated writable checkout:

- Resolve and merge a disputed PR, then start a new feature carrying its workflow records and verify normal delivery.
- Interrupt triage after its dispositions/tasks commit but before its counted commit; run another branch’s pipeline, return, and verify scope enforcement and exactly one counted round.
- Confirm the final PR body, draft status, and notification todos after refreshing the handoff.

This review does not constitute human acceptance.