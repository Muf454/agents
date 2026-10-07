<!-- Plan review of plan digest a398de7d9bffa1a00b2c53517ee3f8ba105d0248bffb395cf42f43b3dff0b2c0; saved 2026-10-07T12:08:40Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=0

Reviewed HEAD: `3368b065331966fe70c244cc7785bf4d47730ea3`.

Inspected repository instructions, spec, plan, tasks, state/handoff, affected scripts and tests, validation configuration, relevant documentation, prior review, Git history/diff, and the vault flow chart. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

- P26: Recovery escalation can overwrite the substage where recovery failed.

  **Location:** `.ai/tasks.md:71–76`, `.ai/tasks.md:227–249`; `scripts/ai-recover:35–44`, `scripts/ai-recover:165`.

  T004 explicitly sets `stage=checks, state=recovering` before recovery validation, but its escalation hook calls `observe stop "$stage"` using the **original pipeline stop label**.

  Under T001’s normalization rules, an original label such as `review`, `re-check`, or `pull request` replaces the recorded Checks stage. Thus recovery validation can fail while the dashboard highlights Review, Re-check, or PR. The planned acceptance test covers recovery from Build, where the `implementation` group happens to preserve Checks, so it misses this behavior.

  **Evidence:** A read-only evaluation of the planned transition rules produced `checks → review`, `checks → recheck`, and `checks → pr` when escalating those original labels. The actual recovery script retains its original `$stage` throughout validation.

  **Concrete plan change:** Track the current recovery substage separately from the original stop label, and preserve it when escalation records the stop. Keep the original label in explanatory text. Add recovery-validation failure tests starting from stages outside the implementation group, asserting final `stage=checks, state=stopped` and dashboard status `needs_you`.

- P27: Recovery’s dependency installer has no planned Setup observation.

  **Location:** `.ai/tasks.md:223–235`, `.ai/tasks.md:242–247`; `scripts/lib/common.sh:150–167`; `scripts/ai-recover:159–165`; `tests/test_workflow.py:3745–3793`.

  T004 places the Setup observation in `ai-run`, but the actual install decision and command live in `common.sh`’s `ai_deps`. Recovery independently calls that function before validating leftovers.

  When a failed build leaves a changed lockfile, recovery starts with the Build stage preserved. As written, its dependency install never records Setup. If that install fails, escalation with label `implementation` preserves Build. The dashboard therefore reports a Build failure for a failed recovery dependency install, contrary to the requirement that failed installs remain on Setup.

  Existing fixtures already exercise this exact path with `fail-later` and `change-later`; their assertions check notifications and checkpoint preservation, not observations.

  **Concrete plan change:** Include `scripts/lib/common.sh` in T004 and place the observation hook at the actual stale-install boundary in `ai_deps`, with caller context that preserves `state=recovering` during recovery. Extend the existing recovery-install fixtures to assert Setup during installation and `stage=setup, state=stopped` after failure, while preserving existing exit, notification, and checkpoint behavior.

## MINOR findings

None.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Task-queue validation passed.
- Planning diff whitespace check passed.
- **14 Bash syntax checks** and **3 Python syntax checks** passed.
- **3 documentation consistency tests** passed.
- Planned recovery-stop normalization evaluated read-only.
- Validation-stamp verification reported **no validation evidence** in this checkout.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and integration fixtures were not run because they create files, repositories, locks, and validation artifacts. Dashboard implementation tests do not exist yet.

## Scope, architecture, and model assessment

The advisory, read-only, stdlib-only design fits the requested scope. Dependencies are ordered, every task specifies a model, and the security/concurrency tasks use `opus`. No task’s own failed implementation retry is recorded.

The findings concern planned observation behavior; they are not demonstrated regressions in existing code. Flow-chart updates are correctly scheduled for T002/T003 and marked pending in the handoff.

## Manual testing recommendations

After implementation, observe two simultaneous tmux pipelines through pause, recovery, stop, and finish. Include recovery dependency-install and validation failures; verify their highlighted boxes. Check navigation, expansion, scrolling, resize, colors, and terminal restoration.

This review assesses plan readiness, not implementation correctness or human acceptance.