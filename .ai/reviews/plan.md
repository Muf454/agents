<!-- Plan review of plan digest 99bb21f4737908f8f0fbfd58184c2a088c4de212db6913731ae5cd4ef6560c8f; HEAD ff863489dfa650550a5b6d46caacabede8fdebda; saved 2026-10-17T07:16:19Z. -->

# Plan review

Reviewed HEAD: `ff863489dfa650550a5b6d46caacabede8fdebda`

Overall verdict: CHANGES REQUIRED before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=7 MINOR=0

## BLOCKER findings

None.

## MAJOR findings

- P1: Terminal recovery failures leave a due schedule eligible for repeated launches.

  **Location:** `.ai/tasks.md:120`, `.ai/tasks.md:178`; `scripts/ai-recover:103`.

  T002 launches recovery whenever the schedule is due and no runner or marker exists. T003 consumes the schedule only after existing checks that can escalate. For example, switching branches during the wait makes recovery escalate at the branch check, remove its marker, and leave the schedule due. Every subsequent watchdog probe launches recovery again. The relaunch count remains unchanged, so its cap does not bound these launches.

  **Plan change:** Define a terminal schedule state or cancellation action for escalated relaunches. Add a regression that schedules, switches branches, and probes twice: one escalation, no second recovery launch.

- P2: An interrupted scheduling handoff can retry before the reset or consume the cap twice.

  **Location:** `.ai/tasks.md:190`, `.ai/current-plan.md:129`; `scripts/lib/watchdog.py:437`.

  The plan calls a crash between scheduling and exit harmless, but `pipeline.active` remains until cleanup. If recovery dies after `limit-schedule`, today’s watchdog detects a crashed pipeline and launches recovery immediately. With the original limit files intact, recovery schedules again and increments the count; after error-file removal, it can instead enter ordinary crash recovery before the reset. T002’s scheduled path explicitly excludes checkouts with a marker.

  **Plan change:** Make scheduling idempotent across interruption. Recovery must recognize an existing future schedule, restore the waiting state, and avoid another reservation or early retry. Test interruptions immediately after scheduling and during cleanup.

- P3: Ordinary edits made before a usage limit prevent the promised automatic resume.

  **Location:** `.ai/tasks.md:181`, `.ai/tasks.md:211`; `scripts/ai-run:148`.

  The due path commits only state, run-log, and handoff leftovers, then requires a clean checkout. A real implementation session can mark `.ai/tasks.md` IN_PROGRESS or edit source before hitting its limit. Those preserved changes cause escalation after the reset. The proposed `limit-far` mock returns before making such edits, so the acceptance test misses this common case.

  **Plan change:** Specify a gated resume path that reconciles preserved task work in the normal implementation session, retaining validation and checkpoint safeguards. Add a regression where the session updates task status and source before reporting its limit; the scheduled resume must preserve and reconcile that work without a recovery decision session.

- P4: A human `--draft` request does not revoke existing pipeline ownership.

  **Location:** `.ai/tasks.md:503`, `.ai/tasks.md:541`.

  T009 says an already-draft PR receives “no record change.” Sequence: a policy run drafts and records the PR; a later human run passes `--draft`; a subsequent clean run omits that flag. The old record still matches, so the pipeline un-drafts the PR despite the intervening explicit human choice. The planned `--draft` test starts without an ownership record and cannot catch this.

  **Plan change:** Clear pipeline ownership whenever `--draft` asserts human draft intent. Add the three-run regression above and require the final run to leave the PR draft.

- P5: The dashboard treats killed usage-limit waits as scheduled relaunches.

  **Location:** `.ai/tasks.md:247`, `.ai/tasks.md:267`; `scripts/lib/common.sh:108`.

  T004 maps every gone runner with observation state `paused` to status `paused`. Existing standalone runners and planning sessions also write that state during ordinary limit sleeps, without scheduling a relaunch. Killing such a planning session leaves `stage: planning, state: paused`, so the proposed rule displays an indefinite pause instead of the required planning stop. Its ordering also lets stale pause telemetry hide a newer error.

  **Plan change:** Require evidence of a current scheduled relaunch before treating a gone runner as waiting. Preserve newer-error precedence. Add killed-during-pause planning and standalone-runner cases without schedules.

- P6: The new predictable temporary-file write follows symlinks.

  **Location:** `.ai/tasks.md:39`.

  The prescribed `printf … > .ai/local/limit-stop.tmp && mv -f` follows an existing `limit-stop.tmp` symlink and truncates its target. `.ai/local` is explicitly agent-writable. Rejecting symlinks when subsequently reading `limit-stop` happens after the destructive write; a FIFO at the temporary path can also block the stop.

  **Plan change:** Use exclusive temporary-file creation and safe directory handling, then atomically replace the record. Add regressions with a temporary-path symlink pointing to a sentinel file and a FIFO; the sentinel must remain unchanged and the stop must return promptly.

- P7: T005 assigns a permissions-boundary change to `sonnet`.

  **Location:** `.ai/tasks.md:288`.

  T005 changes Claude’s accessible directories and constructs permission rules while promising that external references remain read-only. This is security/authorization work, which the review’s explicit model rule requires to use `opus`.

  **Plan change:** Set T005’s `Model:` to `opus` and update the plan’s model table. Keep its path-validation and unchanged edit-permission acceptance criteria.

## MINOR findings

None.

## Scope and validation

Inspected repository instructions, spec, plan, all ten tasks, state, handoff, relevant documentation, affected scripts/helpers, installation logic, test fixtures, and `.ai/validate`. These findings concern proposed behavior; implementation has not begun.

Observed checks passed:

- Task queue validation.
- Documentation consistency tests: **3 tests**.
- Shell syntax checks for the affected existing shell scripts and `.ai/validate`.
- Python AST parsing for affected helpers, tests, and the parallel test runner.

The full gate and fixture-based integration tests were not run because they require writes unavailable in this read-only review. Passing current syntax and documentation checks does not validate the proposed behavior. No files were modified, and no network or MCP integrations were invoked.