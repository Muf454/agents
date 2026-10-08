<!-- Plan review of plan digest a8dc7ad5a5e9422612a4930e79e20b620bf475917845a9bae171705e9d93ce07; saved 2026-10-08T05:33:45Z. -->

# Plan review — FL-04 bounded supervisor

Overall verdict: REQUEST CHANGES — correct the trend calculation and incomplete format-retry path before implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `15fa38f371167ceb9a39db6d1347a55e7caa34d8`.

Inspected repository instructions, spec, plan, tasks, state, handoff, prior review/dispositions, affected scripts and tests, validation entry points, documentation, flow chart, Git history, and locally available prerequisite source.

## BLOCKER findings

None.

## MAJOR findings

- P1: The trend calculation can skip a recent round whose counts are unknown.

  **Location:** `.ai/tasks.md:243`; `.ai/project-spec.md:33`.

  T008 selects the last two reachable records **that carry counts**. R3 instead requires findings to fall across the last two rounds. These differ when a legacy record follows or separates counted records.

  For example, recorded counts `3, 2, legacy-unknown`, followed by a current count of `1`, produce the proposed trend `3 → 2 → 1`. That grants an extra round despite lacking evidence for the most recent transition. Supporting legacy records must not turn unknown counts into permission for another unattended round.

  **Concrete plan change:** Select the last two reachable round records first, then require both to contain verified counts. Otherwise return `insufficient history`. Add tests with a legacy record most recently and between counted records. Retain the existing boundary test where legacy round 1 precedes fully counted rounds 2–3.

- P2: Successful empty reviewer responses never reach the proposed format retry.

  **Location:** `.ai/tasks.md:272`; `scripts/ai-review:167`; `scripts/lib/workflow.py:670`.

  T009 runs its format check only after `run_review` returns. Currently, `run_review` terminates on a zero-byte report, even when Codex exits successfully and the checkout is unchanged. Claude’s successful envelope with empty final text also terminates in `claude-text`. The locally available catch-up prerequisite retains these guards.

  Consequently, empty content—missing every required field—gets no retry under the proposed implementation. Existing malformed-then-valid acceptance criteria do not explicitly exercise this path.

  **Concrete plan change:** Route empty text from an otherwise successful reviewer invocation through Markdown format validation. Preserve immediate failure for unsuccessful invocations, invalid result envelopes, missing/unreadable report storage, and checkout mutation. Add empty-then-valid and empty-twice tests for Codex plan/code reviews and Claude fallback, plus supervision-disabled coverage. Verify checkout integrity before permitting the retry.

## MINOR findings

- P3: Recovery’s decision-check placement contradicts its direct-escalation acceptance criterion.

  **Location:** `.ai/tasks.md:150`; `.ai/tasks.md:160`; `scripts/ai-recover:108`; `scripts/ai-recover:115`.

  T005 places `plan-revisions decision` after the open-stage block. That block calls `resume`, which execs the pipeline; the new check is therefore unreachable while a stage remains open. A crash after storing a needs-human outcome but before clearing its stage resumes the pipeline instead of directly escalating as T005 requires. An exhausted recovery-attempt allowance can also escalate before reading the stored questions.

  T006 should still stop the resumed pipeline, so this does not demonstrate an implementation bypass. It leaves the recovery contract and its tests inconsistent.

  **Concrete plan change:** Check stored needs-human decisions after validating host authority, but before the attempt-limit and open-stage resume paths. Add an open-stage crash test asserting direct escalation with stored questions and no pipeline resume, including an exhausted recovery allowance.

## Ordering, models, and scope

All ten tasks specify models. No additional model-selection finding was identified. No failed implementation attempt is recorded.

Preserve the prerequisite: merge `fix/catchup-review`, rebuild this branch, and review the resulting baseline before T001. The cumulative budget’s removal is an explicit scope decision.

## Validation observed

- Requested HEAD confirmed; checkout remained clean.
- `tasks check` and `tasks untouched` passed.
- Bash syntax checks passed for 13 files.
- Python AST parsing passed for four files.
- Discovery collected 272 tests; these tests were not executed.
- No local validation stamp was present.

Not run: integration tests, `./scripts/ai-check`, `.ai/bin/ai-check`, or the full suite, because they create fixtures, locks, logs, or validation artifacts. No files were modified and no network/MCP integrations were invoked.

After revision, run the targeted checks and full gate in a writable checkout. Retain the planned live permission check and supervised needs-human/crash-recovery trial.

This review is not human acceptance.