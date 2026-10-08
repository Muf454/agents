<!-- Plan review of plan digest 02bd45d8f9ebe43d869467ac389d9a5d1458c17e3791c8e676cb7b0cb1a110db; saved 2026-10-08T05:28:45Z. -->

# Plan review — FL-04 bounded supervisor

Overall verdict: REQUEST CHANGES — clarify startup decision handling before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

Reviewed HEAD: `03d8fbad37e0a36f04f03dd22507b670fbbbbb12`.

Inspected repository instructions, specification, plan, tasks, state, handoff, prior review/dispositions, relevant scripts, tests, validation, documentation, Git history, the flow chart, and the locally available catch-up prerequisite.

## BLOCKER findings

None.

## MAJOR findings

- P1: The startup decision check lacks a safe first-run and invalid-report contract.

  **Location:** `.ai/current-plan.md:84`; `.ai/tasks.md:117`; `.ai/tasks.md:177`.

  The pipeline must call `plan-revisions decision` before its first review and stop on exit 2. The helper contract assigns exit 2 to unreadable reports without explicitly handling normal absence. Fresh installations contain no `.ai/reviews/plan.md`; the existing `plan-review-info` reports that absence as an error (`scripts/lib/workflow.py:1934`).

  There is also an existing regression requirement: `test_plan_review_is_bound_and_tracks_the_whole_tree` deliberately forges a report and expects the pipeline to replace it with a fresh review. An unconditional report-verification failure in the new startup decision check would stop before that replacement, contradicting T006’s requirement that this test pass unchanged with supervision disabled.

  **Concrete plan change:** Define the decision helper’s initial-state behavior explicitly. A missing revision store, or a valid store without outstanding needs-human decisions, must permit the normal missing/invalid-report review path. Corrupt authority state, or an unverifiable report when an outstanding human decision might apply, must still fail closed. Apply equivalent absence handling to `plan-rounds sync`. Add tests for a fresh installation, forged-report replacement with `AI_SUPERVISE=0`, and an outstanding needs-human decision with missing or corrupted evidence.

## MINOR findings

- P2: The revision-session security contract still contradicts itself.

  **Location:** `.ai/tasks.md:115`; `.ai/tasks.md:127`; `.ai/current-plan.md:158`.

  T004’s implementation instructions correctly require exactly `Read,Glob,Grep,Edit`, with no Bash. Its acceptance criteria and the main plan still require `Read,Glob,Grep,Edit,Bash`. T004 and T007 also retain crash scenarios involving a session-side commit, although the revised session must never commit.

  These contradictions leave unattended implementation and its tests without one consistent contract. The earlier Bash allowlist design has been replaced in the implementation instructions; this finding concerns the remaining inconsistent requirements.

  **Concrete plan change:** Require exactly `Read,Glob,Grep,Edit` everywhere. Replace session-commit crash scenarios with interruption after edits and around the host’s preamble/revision commits. Update the invocation assertions accordingly.

- P3: Repeated `run_review` calls can publish the wrong reviewer label.

  **Location:** `.ai/tasks.md:271`; `scripts/ai-review:128`; `scripts/ai-review:162`.

  T009 adds a second `run_review` call using the same reviewer chain. A successful Claude fallback exports `AI_REVIEW_BY` and `AI_REVIEW_LABEL`; a subsequent successful Codex call sets `review_by=codex` but does not clear those exports.

  An in-memory probe of the current function reproduced this sequence: first attempt Claude fallback, second attempt Codex, with the second attempt retaining the Claude fallback label. Publication would therefore disagree with the outcome record and fallback-log decision. The prerequisite’s locally available source retains this behavior.

  **Concrete plan change:** Reset per-attempt reviewer metadata before each call, and explicitly clear Claude labels on Codex success. Add a malformed-Claude-fallback → valid-Codex retry test asserting consistent report labeling, outcome attribution, and fallback logging.

## Ordering, models, and scope

All ten tasks have explicit model selections. No additional model-selection finding was identified, and no failed implementation attempt is recorded.

Preserve the stated prerequisite: merge `fix/catchup-review`, rebuild this branch, and review the plan against the resulting baseline before T001 starts. Removing the cumulative budget is an explicit scope decision; it is not carried forward as a defect.

## Validation observed

- Requested HEAD confirmed; checkout remained clean.
- Read-only `tasks check` and `tasks untouched` passed.
- Bash syntax checks passed for 13 files.
- Python AST parsing passed for four files.
- Discovery collected 272 tests; discovery is not a test pass.
- The in-memory reviewer-metadata probe reproduced P3.
- No local validation stamp was present.

Not run: targeted integration tests, `./scripts/ai-check`, `.ai/bin/ai-check`, or the full suite, because they create fixtures, locks, logs, or validation artifacts. No files were modified and no network/MCP integrations were invoked.

## Testing recommendations

After reconciling these contracts, run the targeted checks and full gate in a writable checkout. Retain the planned live permission check and supervised trial covering needs-human handling, crash recovery, and explicit human clearance.

This review is not human acceptance.