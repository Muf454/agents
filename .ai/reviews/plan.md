<!-- Plan review of plan digest 7abd705ecfc63bce079b0e82a0551c2467c728c003281bfec6466adec247c9a3; HEAD 0fcb163092dcf7627f8ae611aa85280fd2ae1827; saved 2026-10-17T07:27:43Z. -->

# Plan review

Reviewed HEAD: `0fcb163092dcf7627f8ae611aa85280fd2ae1827`

Overall verdict: CHANGES REQUIRED before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=4 MINOR=0

## BLOCKER findings

None.

## MAJOR findings

- P3: Preserved work still cannot resume when the limited session already marked the last task DONE.

  **Location:** `.ai/tasks.md:338`, `.ai/tasks.md:346`; `scripts/ai-pipeline:499`, `scripts/ai-pipeline:507`.

  T011 assumes the resumed pipeline reaches an implementation session. A session can mark its last task DONE and then hit the limit before committing—the existing runner explicitly supports validated checkpoints of uncommitted DONE work. On relaunch, `tasks complete` skips `ai-run`, so the arm is never consumed. The review/publish path subsequently refuses the dirty checkout. The new IN_PROGRESS-only regression does not cover this case.

  **Plan change:** Define how an armed resume reconciles the interrupted task when no runnable task remains. Preserve validation and checkpoint safeguards, and add a regression where the last task is marked DONE with uncommitted source before the limit; relaunch must complete without a recovery decision session.

- P4: Failed ownership revocation can still let a later run override human `--draft` intent.

  **Location:** `.ai/tasks.md:680`, `.ai/tasks.md:686`.

  The revision clears ownership during `--draft`, but explicitly treats a failed clear as a warning. If deletion fails while the old record remains readable, the run can finish successfully with that ownership intact. A subsequent clean run reads the matching record and un-drafts the PR. The three-run test covers only successful deletion.

  **Plan change:** Require durable revocation before reporting a successful `--draft` run. If revocation cannot be persisted, stop with an explicit state-repair requirement. Add fault injection for a failed clear with an existing readable record, followed by a clean run, and verify human draft intent remains protected.

- P8: The detached launcher’s predictable log redirection can truncate another file or block.

  **Location:** `.ai/tasks.md:521`.

  T006 prescribes a second-resolution filename and `>"$log"` before the child performs its checkout checks. A planted symlink at that path redirects the write outside the checkout; a FIFO can block startup. Two launches within the same second also reuse and truncate the same log, including when the second child subsequently fails to acquire the lock. T001’s safe limit-record writer does not protect this separate write.

  **Plan change:** Create each detached log exclusively through a safe `.ai/local` directory, and redirect through the already-open descriptor. Add sentinel-symlink, FIFO, unsafe-directory and simultaneous-launch regressions; logs must remain distinct and outside files unchanged.

- P9: The preserved-work exception identifies a commit, not the preserved tree.

  **Location:** `.ai/tasks.md:80`, `.ai/tasks.md:331`; `.ai/current-plan.md:60`; `scripts/ai-run:689`.

  Both `limit-arm` and `limit-armed` compare only HEAD. Scheduling releases the checkout lock, potentially for days. Human edits made during that wait leave HEAD unchanged and therefore pass the exception. The resumed session can modify those edits, and its validated automatic checkpoint stages all remaining files. This breaks the stated promise to admit exactly the limited session’s preserved work and removes the existing protection against absorbing unrelated human changes.

  **Plan change:** Bind the resume exception to the preserved index/worktree contents when scheduling, and verify that binding after reacquiring the lock, accounting explicitly for host bookkeeping. Add a regression that edits or adds an unrelated file during the wait without changing HEAD; recovery must preserve it and refuse automatic reconciliation.

## MINOR findings

None.

## Scope and validation

Inspected repository instructions, spec, revised plan and all eleven tasks, dispositions, state, handoff, relevant documentation, affected scripts/helpers, installation logic, test fixtures and `.ai/validate`.

The revised plan covers P1, P2, P5, the original P6 limit-record write, and P7. P3 and P4 remain incomplete in the cases above.

Observed checks passed:

- Task queue validation.
- Documentation consistency: **3 tests**.
- Shell syntax: **13 files**.
- Python AST parsing: **6 files**.

The full gate and fixture-based integration tests were not run because they require writes unavailable in this read-only review. These checks validate the existing baseline, not the proposed behavior. No files were modified; no network or MCP integrations were invoked.