<!-- Plan review of plan digest 22390372577645d2befbb04e95ecb16ac3ea88ccf100256daeae9db6e464193d; HEAD 68d6d707a09066343b59b7c1690f82cce76ee0ac; saved 2026-10-17T07:52:12Z. -->

# Plan review — round 4

Overall verdict: REVISE — two MAJOR gaps remain.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=0

Reviewed HEAD: `68d6d707a09066343b59b7c1690f82cce76ee0ac`

## BLOCKER findings

None.

## MAJOR findings

- P3: Preserved work still cannot resume after a verified re-check.

  **Location:** `.ai/tasks.md:582–584`; `scripts/ai-pipeline:349`.

  T011 permits an armed dirty tree through dispute reconciliation only when re-check status is `none`; it explicitly preserves existing behavior for `verified`. That path ends with an unconditional clean-checkout requirement.

  A pipeline can accept one review finding, reject another, complete the rejection’s re-check, then hit a usage limit while implementing the accepted fix. On relaunch, the preserved tree passes verification and is armed, but dispute reconciliation rejects its uncommitted source changes before ai-run consumes the arm. This defeats the promised automatic continuation of limited implementation work.

  **Evidence:** An in-memory execution of the actual `reconcile_disputes` function, with helper responses representing an already-settled verified re-check and dirty source, exited 1 with `the checkout is not clean after recording it.`

  **Concrete plan change:** Extend T011 to handle the settled `verified` path while preserving report and dispute verification. Admit the exact armed tree through its final cleanliness check without committing or changing that tree before ai-run consumes the arm. Add an end-to-end regression with accepted and rejected findings, a verified re-check, and a limit during the subsequent fix task; require validated completion without a recovery decision session.

- P11: The revised watchdog predicate treats an absent schedule as due.

  **Location:** `.ai/tasks.md:167–175`.

  T002 specifies `scheduled_ns = 0` when `limit-at` fails, then launches recovery whenever `args.recover` and `scheduled_ns <= now`. With no schedule, that comparison is true.

  Implementing this literally attempts usage-limit recovery for ordinary idle, finished, or explicitly stopped checkouts. A surviving approved manifest can pass `start_recovery`’s checks and launch ai-recover despite there being no scheduled relaunch; a missing manifest produces a spurious refusal instead.

  **Concrete plan change:** Require a successfully parsed schedule before testing whether it is due—for example, represent absence as `None` and launch only when `scheduled_ns is not None and scheduled_ns <= now`. Keep absence equivalent to zero only for stall-time calculations. Add repeated-probe tests for no manifest, an approved unscheduled run, and a completed run, asserting no relaunch or relaunch-refusal notification.

## MINOR findings

None.

## Previous findings re-evaluated

The current plan covers round 3’s P2, P9 and P10 through manifest-based stall suppression, verification before checkout mutations, and reuse of the recursive `tree_snapshot` digest. P3 remains incomplete for the verified re-check path described above.

## Scope and validation

Inspected instructions, spec, plan, all 14 tasks, dispositions, state/handoff, relevant documentation, Git history/diffs, affected source, existing tests and `.ai/validate`.

Independent read-only checks passed: task-queue validation, eight Python AST parses, 13 shell syntax checks, and `git diff --check`. The two predicates above were checked in memory.

The full `./scripts/ai-check` and integration tests were not run because their fixtures require filesystem writes. No files were modified or network/MCP integrations invoked.