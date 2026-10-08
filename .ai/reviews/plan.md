<!-- Plan review of plan digest 1249c96c3d6bafee6cc962ff605900499191cc5e231c3f39dd6635cbe0751004; saved 2026-10-08T05:10:28Z. -->

# Plan review — FL-04 bounded supervisor

Overall verdict: REQUEST CHANGES — resolve the findings below before unattended implementation.
Finding counts: BLOCKER=1 MAJOR=4 MINOR=2

Reviewed HEAD: `dbe85f5cb6cc3f5ae8c507816c125f09db2c67cf`

Scope: Revision 3 of the spec, plan and T001–T011, checked against the existing scripts, host-state formats, task parser, tests and validation entry point. These are prospective implementation defects; no FL-04 implementation exists yet.

## BLOCKER findings

- P1: The successful revision path dirties the checkout immediately before mandatory re-review.

  **Location:** `.ai/tasks.md:205`; `.ai/current-plan.md:100`; `scripts/lib/common.sh:208`; `scripts/ai-review:184`.

  T007 explicitly calls `ai_log` after completing and clearing the revision stage, then loops into `ai-review --plan`. `ai_log` appends to tracked `.ai/run-log.md`, while plan review refuses any dirty checkout. Neither the loop nor T006 commits this new entry. T010’s change to `review_record` happens after review and cannot fix its startup precondition.

  Implementing this sequence literally makes a successful revision stop with “Commit the plan before reviewing it” instead of completing R1’s re-review.

  **Concrete plan change:** Persist the revision log entry within the revision’s host commit, or define a guarded bookkeeping commit before stage closure and re-review. Keep the reviewer’s clean-checkout requirement. T007’s end-to-end test must run with logging enabled and assert a clean checkout immediately before the second reviewer call.

## MAJOR findings

- P2: Clearing the stage before handling `needs-human` loses the terminal decision across a crash.

  **Location:** `.ai/current-plan.md:85`; `.ai/current-plan.md:98`; `.ai/current-plan.md:103`; `.ai/tasks.md:205`; `.ai/tasks.md:236`.

  `complete_plan_stage` clears the stage before its caller checks the section for `needs-human`. If the process dies between those operations, the next run finds no open stage and a recorded revision, so it goes directly to re-review. The planned loop does not check that completed revision’s unresolved questions first.

  A subsequent approving review can therefore lead to implementation despite the revision having escalated a scope or irreversible decision. The existing `ai-recover` message patterns cannot protect a stop whose message was never written.

  **Concrete plan change:** Persist the validated revision outcome, including its terminal `needs-human` status, in host state before clearing the stage. Check that outcome at startup and loop entry before re-review or implementation. Add crash tests between stage closure and question handling, resumed through both a human rerun and watchdog recovery; assert no reviewer or implementation session starts while the decision remains unresolved.

- P3: The specified crash accounting contradicts the approved full-grant charge.

  **Location:** `.ai/project-spec.md:71`; `.ai/tasks.md:51`; `.ai/tasks.md:62`.

  The spec says a crashed invocation consumes its **full grant** at the next start. T002 instead instructs `open` to charge `min(now − start, grant)` for a stale record.

  For example, an invocation granted 300 seconds and killed after 10 seconds is charged only 10 seconds under the implementation notes, although the spec and acceptance criteria require 300. A recovery budget could consequently retain time the approved fail-closed rule intended to consume.

  **Concrete plan change:** Make stale-record reconciliation charge the stored grant once, clear the stale record atomically, and share that logic between `open` and `remaining`. Test an immediate crash, recovery after a long delay, and repeated reconciliation; each must charge exactly one full grant.

- P4: Budget exhaustion during an active session still follows the ordinary timeout recovery path.

  **Location:** `.ai/tasks.md:52`; `.ai/tasks.md:64`; `scripts/ai-run:145`; `scripts/ai-run:171`; `scripts/ai-run:267`; `scripts/ai-run:303`; `scripts/ai-recover:147`.

  T002 changes the between-session exhaustion message, but does not address the normal case where GNU `timeout` terminates a session at the budget boundary. That case currently exits with “Claude exited 124 …”, which does not match the proposed always-escalate budget pattern. An implementation stop can therefore launch a Claude recovery session after budget exhaustion.

  The remaining-time checks before final and post-task validation also retain separate ordinary timeout messages. Additionally, `capped_by_budget: remaining < LIMIT` classifies equal limits as a per-call timeout even when the host budget is exhausted simultaneously.

  **Concrete plan change:** Define one exhaustion classifier for every budget-bound exit, including timeout results, validation boundaries and equal budget/per-call limits. Reconcile the budget before choosing recovery, and emit the terminal budget reason whenever the host budget is exhausted. Add active-session timeout and equal-limit tests with `AI_AUTO_RECOVER=1`, asserting no recovery session; retain a separate recoverable per-call timeout test.

- P5: The mandatory re-review path has no budget gate.

  **Location:** `.ai/project-spec.md:73`; `.ai/current-plan.md:87`; `.ai/current-plan.md:93`; `.ai/tasks.md:202`.

  The spec explicitly prohibits starting a re-review after a revision when the budget is exhausted. The loop checks budget only after a significant review, before reserving a revision. Its “review needed” branch starts `ai-review` directly.

  A completed revision that leaves less than the 60-second floor—or a resume that exhausts the budget while reconciling a crashed grant—can therefore start the supervised re-review before stopping.

  **Concrete plan change:** Add an exhaustion check immediately before every revision-triggered re-review, including startup after a recorded revision. Preserve the pending re-review obligation for a later human-started run. Add tests asserting that an exhausted resume makes no new reviewer call and starts no recovery session.

## MINOR findings

- P6: T002’s dependency declaration omits its config prerequisite.

  **Location:** `.ai/tasks.md:43`; `.ai/tasks.md:21`; `.ai/tasks.md:53`.

  T002 requires `AI_RUN_BUDGET` to work from user config, but adding that key to `ai_config` belongs to T001. `Dependencies: none` incorrectly presents T002 as independently implementable and verifiable. The current queue order happens to mask the omission.

  **Concrete plan change:** Set T002’s dependencies to `T001`.

- P7: The planned budget documentation gives the wrong control for the shared allowance.

  **Location:** `.ai/tasks.md:55`; `.ai/current-plan.md:142`; `.ai/project-spec.md:65`.

  T002 says to document pipeline `--run-timeout` as the “whole run” limit, and the risk section advises raising it for the new shared budget. The spec instead makes `AI_RUN_BUDGET` the shared allowance and retains `--run-timeout` as a per-invocation cap. Raising the latter does not increase the manifest budget.

  **Concrete plan change:** Consistently document `AI_RUN_BUDGET` as the cumulative allowance and `--run-timeout` as the per-call cap. Replace the incorrect risk guidance and add a documentation assertion for this distinction.

## Validation observed

- Confirmed the scoped HEAD and a clean worktree.
- Read repository guidance, spec, plan, tasks, state, handoff, relevant docs and prior review dispositions.
- Independently inspected pipeline, runner, reviewer, recovery, host-state helpers and relevant regression tests.
- Read-only `tasks check` and `tasks untouched` passed.
- Shell syntax checks and Python AST parsing passed.
- `tests/run_parallel.py --collect-only` discovered 272 existing tests. Discovery is not a test pass.

Not run: `./scripts/ai-check`, `.ai/bin/ai-check`, targeted runtime tests or the full suite. They write test checkouts, logs, locks or validation evidence and cannot run within this read-only review. No `.ai/local/validation.json` was present.

## Security and architecture concerns

The principal authorization gap is P2: a persisted human-decision requirement must survive stage closure and recovery. Budget accounting and terminal exhaustion must likewise have one authoritative host-side interpretation.

Every task has an explicit `Model:` line. No task’s own failed implementation attempt exists at this scope. The revision allowlist and post-session scope checks remain necessary; they should not be weakened to resolve P1.

The unmerged `fix/catchup-review` prerequisite remains a scope limitation. Preserve the plan’s requirement to rebuild and review against the merged baseline before implementation.

## Testing recommendations

Add the regression cases specified in P1–P5 to the relevant task acceptance criteria. After implementation and deterministic validation, perform T011’s real supervised CLI trial, including a `needs-human` stop and recovery attempt. Mock results must not be recorded as human acceptance.