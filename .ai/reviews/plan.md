<!-- Plan review of plan digest 304d17cc4a953e3f044c2144f543521ae637532a12b30b95c22c6369049967be; HEAD 1281a0f2596c3f63ebdfe486fb6c5fed0eb20f22; saved 2026-10-17T19:02:51Z. -->

# Plan review — round 9

Overall verdict: APPROVE WITH MINOR PLAN CORRECTIONS
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

Reviewed HEAD: `1281a0f2596c3f63ebdfe486fb6c5fed0eb20f22`

## BLOCKER findings

None.

## MAJOR findings

None.

The current plan addresses round 8’s P16 through T011/T018/T019: consistency checks, dependency setup and routing occur before disarming, with recovery-enabled regressions requiring no recovery session or commit. T002 also covers P19’s duplicate stall notification after a due relaunch is refused. Neither finding is carried forward.

## MINOR findings

- P20: T019’s textual span test includes legitimate final-handoff code.

  **Location:** `.ai/tasks.md:1197`; `scripts/ai-run:623`.

  The proposed scan from `limit-disarm` before the task loop to its first `claude_session` would include the loop’s entire `active_task == none` branch. That branch contains three `ai_die` calls, a `git commit` and `exit 0`, which the scan explicitly forbids. These statements are unreachable on the checked session route, but a textual scan still finds them. T011’s planned extraction of `checkpoint_done` does not remove this branch.

  **Concrete plan change:** make the assertion specific to the executable session route, or explicitly extract the final-handoff branch into a separate function before scanning. Keep the behavioral regressions; do not whitelist final-handoff commits as permitted operations before the session.

- P21: A detached planner that finishes before acknowledgement is reported as failed.

  **Location:** `.ai/tasks.md:1583`; `scripts/ai-run:373`.

  T006 accepts only a matching `planning/active` observation. If the child completes between polls, its observation becomes `planning/done`; the subsequent child-exit path forces a nonzero result even when `wait` returns zero. A successful plan can therefore produce an “ended early” failure. The sleeping-child acceptance test avoids this case.

  **Concrete plan change:** specify successful completion before acknowledgement as another success case. Require the child’s zero exit status and matching PID’s `planning/done` observation, print the PID and log path, and return zero. Add a regression that deliberately delays the parent’s first observation read until the child finishes.

## Validation observed

- Task queue check passed: `python3 -B scripts/lib/workflow.py tasks check`.
- Shell syntax passed for 13 script/template files.
- Python AST parsing passed for eight source/test files.
- `git diff --check 88b28e7..HEAD` passed.
- Working tree remained clean.

The full gate and fixture-based tests were not run: they require filesystem writes unavailable in this read-only review. These static checks do not validate the proposed implementation.

## Scope, security and architecture

Inspected repository instructions, spec, plan, all 19 tasks, dispositions, state/handoff, relevant documentation, validation entry points, and affected source and test fixtures. No additional security or architecture findings were identified in those inspected areas. Explicit task models fit their described risks.

## Manual testing recommendations

Retain T010’s real limit-resume, detached planning and PR draft-ownership checks, including installed-copy upgrades and watchdog timer reinstallation. This plan review is not human acceptance.