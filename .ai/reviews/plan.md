<!-- Plan review of plan digest 0f7f90a109d1fa28c16fe6ca15cedce996e3705ed088625d99eb0c31b0b61dc4; saved 2026-10-07T18:51:30Z. -->

# Plan review — FL-04 bounded supervisor

Overall verdict: REVISE before unattended implementation. The plan has gaps in task ordering, review history, validation, permissions, budgets, and recovery.
Finding counts: BLOCKER=0 MAJOR=10 MINOR=1

Reviewed HEAD: `cc8c464b982920b31c271d23f5efbb4081863fad`.

## BLOCKER findings

None.

## MAJOR findings

- P1: T001 depends on functionality scheduled for T002.

  **Location:** `.ai/tasks.md:17`, `.ai/tasks.md:23`, `.ai/tasks.md:34`.

  T001 must demonstrate MAJOR → revision → APPROVE → implementation, but `ai-run --revise-plan` is introduced by T002, which depends on T001. The existing argument parser rejects that mode (`scripts/ai-run:24`). T001 cannot satisfy its acceptance criteria at its checkpoint.

  **Plan change:** Implement and validate the revision mode before integrating the pipeline loop. Reorder the dependencies or split out the prerequisite mode, prompt, and validator. Require each checkpoint’s tests to exercise functionality available at that checkpoint.

- P2: T002 assigns permission-boundary implementation to sonnet.

  **Location:** `.ai/tasks.md:35`, `.ai/tasks.md:48`.

  T002 implements the allowlist that prevents an unattended planning session from editing code or protected files. This is security and authorization work, requiring `opus` under the explicit model-selection rules. Choosing `opus` for the eventual revision session does not address the model implementing that boundary.

  **Plan change:** Set T002 to `Model: opus`, or separate permission enforcement into an opus task while keeping mechanical prompt work on a cheaper model.

- P3: Supervision settings are missing from configuration and recovery integration.

  **Location:** `.ai/current-plan.md:9`, `.ai/tasks.md:17`, `.ai/tasks.md:64`.

  The plan promises user-config settings and preserved behavior on resume, but omits two required modules. `scripts/lib/common.sh:37` accepts only enumerated configuration keys; `RUN_SETTINGS` in `scripts/lib/workflow.py` and the restore logic at `scripts/ai-recover:69` also enumerate existing keys. None includes the new supervision settings. Config-file values would be ignored, and recovery could lose approved limits or models.

  Additionally, only T001 explicitly checks `AI_SUPERVISE=0`; the extra fix round and malformed-review retry have no corresponding disabled-behavior criterion.

  **Plan change:** Add configuration parsing, input validation, manifest capture, and recovery restoration for every new setting. Define which behaviors `AI_SUPERVISE=0` disables and test that contract, including recovery after the configuration file changes.

- P4: The promised run-budget accounting has no shared budget mechanism.

  **Location:** `.ai/project-spec.md:35`, `.ai/tasks.md:17`.

  Existing time accounting starts anew in each `ai-run` process (`scripts/ai-run:78`, `scripts/ai-run:127`). The pipeline does not maintain a shared deadline, and it currently forwards `--run-timeout` only to implementation invocations. Repeated fresh revision processes could each receive a full allowance, followed by implementation receiving another allowance. Logging elapsed time does not enforce R5.

  **Plan change:** Specify host-owned remaining-budget accounting across revisions, subsequent reviews, retries, and implementation. Preserve it on recovery and define how usage-limit pauses count. Add tests proving that exhausted supervision leaves no fresh budget for another revision or implementation.

- P5: The existing history helper does not provide plan-review history.

  **Location:** `.ai/tasks.md:41`.

  `review-history` recognizes implementation-review commits changing `.ai/reviews/current.md` (`scripts/lib/workflow.py:872`). Its `--current` mode requires that report’s implementation-review header (`scripts/lib/workflow.py:904`). It does not recognize plan-review commits or `.ai/reviews/plan.md`.

  Reusing it as described would supply unrelated implementation history or no plan history, undermining R2’s repeated-area assessment.

  **Plan change:** Add an explicit plan-history mode that pairs plan reports with their revision dispositions. Define review-round versus revision-round numbering. Test three plan rounds with repeated and unrelated areas, plus repositories containing earlier implementation reviews.

- P6: Context-only review history is being promoted into budget authority.

  **Location:** `.ai/tasks.md:64`.

  The extra fix-round decision reads counts from review history. The existing helper explicitly documents that its results must never authorize or count anything because agents can imitate commit subjects (`scripts/lib/workflow.py:872`). Granting another implementation round based on those records crosses that boundary.

  **Plan change:** Derive the three-count trend from host-verified review records bound to the approved branch/run and review sequence. Reserve the extra allowance in host state before starting it. Test forged review commits, insufficient history, unrelated history, and interruption immediately after reservation.

- P7: Appended dispositions lack a round-specific validation contract.

  **Location:** `.ai/tasks.md:41`, `.ai/tasks.md:47`.

  The validator requirements cover row presence, rejection evidence, and a `Convergence:` line, but do not require those values to come from the section for the exact current report. With appended sections, finding IDs can recur and an earlier convergence line can remain present. A whole-file scan could satisfy a new round using old decisions.

  The contract also omits checks for duplicate/conflicting rows, valid accepted task references, and nonempty `needs-human` questions. “Every finding ID” conflicts with the specified BLOCKER/MAJOR-only rows when a review contains MINOR findings.

  **Plan change:** Bind the active section to a host-supplied round and report digest. Validate only that section, require exactly one valid disposition per BLOCKER/MAJOR, validate referenced tasks and questions, and require convergence text in the current section. Reject planning changes that invent DONE work, which could bypass the existing “no task DONE” plan gate. Add adversarial validator tests for these cases.

- P8: Recovery does not yet understand revision stages or terminal human stops.

  **Location:** `.ai/tasks.md:17`, `.ai/tasks.md:109`.

  Existing stage records and verification support only `triage` (`scripts/lib/workflow.py:1094`, `scripts/lib/workflow.py:1161`). The recovery path likewise handles interrupted triage specifically. Its terminal-stop patterns match `plan review found`, but not the proposed `plan review: supervision limit reached` or a general `needs-human` reason (`scripts/ai-recover:102`).

  Without planned integration, these stops can enter generic recovery and another Claude session instead of stopping directly. Interrupted revisions also lack a defined path that preserves records and counts the attempt exactly once.

  **Plan change:** Add a distinct, host-bound revision stage and explicit terminal escalation rules. Define completion and counting across crashes before commit, after commit, and before stage closure. Test with `AI_AUTO_RECOVER=1`, including that `needs-human` and exhausted limits launch no recovery planning session.

- P9: A dispositions-only revision can reuse the rejected plan review.

  **Location:** `.ai/tasks.md:17`, `.ai/project-spec.md:18`.

  An all-rejected revision can legitimately change only dispositions and bookkeeping. Those files are excluded from `plan_digest` (`scripts/lib/workflow.py:1905`). Returning to the existing plan-review block therefore finds the report current and skips the reviewer (`scripts/ai-pipeline:300`).

  This consumes revision rounds without the required independent review of the new rejection evidence.

  **Plan change:** Require a fresh plan-review invocation after every completed revision, even when spec, plan, and tasks are unchanged. Supply the current round’s dispositions as review context. Test an all-rejected, dispositions-only revision and assert that a second reviewer call occurs before any implementation.

- P10: T004 assumes rechecks use the Markdown publication contract.

  **Location:** `.ai/tasks.md:87`, `.ai/tasks.md:93`.

  Rechecks return JSON, not Markdown. Malformed answers currently publish successfully as **upheld**, with parsing notes (`scripts/lib/workflow.py:1300`, `scripts/lib/workflow.py:1343`). Thus retrying only when publication fails will never retry malformed recheck JSON. This behavior has explicit regression coverage at `tests/test_workflow.py:3212`.

  The plan also needs to distinguish format failures from provenance, checkout-change, and storage failures; retrying all publication failures would be unsafe.

  **Plan change:** Either limit T004 to the Markdown plan/code reports required by R4, or explicitly specify a separate JSON retry contract preserving fail-closed recheck behavior. Classify retryable format errors separately from integrity and publication errors. Test each supported mode and reviewer, prior-report preservation, and that integrity failures never trigger format retries.

## MINOR findings

- P11: Deferring the flow chart to T006 violates the same-session rule.

  **Location:** `.ai/tasks.md:6`, `.ai/tasks.md:131`; `AGENTS.md:15`.

  Tasks run in fresh sessions, but flow changes occur in T001–T004 while their chart updates are deferred to T006. The repository requires each flow change and its `updated:` date to be recorded in the same session.

  **Plan change:** Include the relevant chart/date update in each task that changes flow. Keep T006 for final documentation reconciliation, handoff, and the PR’s “Flow chart updated” statement.

## Validation observed

- Confirmed the scoped HEAD and a clean working tree.
- Read instructions, spec, plan, tasks, state, handoff, relevant documentation, source, tests, and validation entry points.
- Shell syntax checks passed for 13 files; Python parsing passed for four files.
- Task-queue structural validation passed.
- Test discovery collected 272 tests.
- All three existing documentation-consistency tests passed.
- `git diff --check HEAD^ HEAD` passed.
- A read-only parser probe confirmed malformed recheck JSON becomes an upheld answer rather than a publication error.

## Limitations and required validation

The full `./scripts/ai-check` / `.ai/bin/ai-check` gate was not run: it writes validation evidence and its integration tests create temporary repositories. No implementation or network/MCP operation was performed.

The planned `fix/catchup-review` prerequisite is absent from this HEAD. Reconcile and review the plan against the merged baseline before implementation.

After the changes above, validation should include crash/resume scenarios, approved-setting restoration, budget exhaustion, stale disposition rejection, verified trend accounting, and terminal human stops with automatic recovery enabled. Human acceptance should include the proposed real supervised run; this review does not constitute that acceptance.