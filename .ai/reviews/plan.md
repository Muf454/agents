<!-- Plan review of plan digest 397eb2ed29850b64636aa435f5a4b52cb7c99a5572d48f06fe02ce5b0da86515; saved 2026-10-06T08:42:40Z. -->

# Plan review

Overall verdict: REVISE before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=5 MINOR=2

Reviewed HEAD: `79b794470c52a53d7942d6523026ba103e3f59b3`

Scope: repository instructions, FL-01/FL-07/FL-09 spec and tasks, affected scripts and templates, tests, validation evidence, documentation, and relevant vault notes. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

- P1: Dependency logging leaves the pipeline dirty before review.

  **Location:** `.ai/tasks.md:41`, `.ai/tasks.md:46`; `scripts/ai-pipeline:190`, `scripts/ai-pipeline:302`.

  T001 makes `ai_deps` append to tracked `.ai/run-log.md`. When `ensure_validated` installs dependencies for an already completed queue, that append remains uncommitted. Immediately after validation, the pipeline requires a clean checkout before review; publication also requires cleanliness. A successful installation therefore causes an integrity stop. The planned test at `.ai/tasks.md:83` only requires installation before validation and does not explicitly require the pipeline to finish.

  **Concrete plan change:** Define how pipeline-owned dependency bookkeeping is checkpointed before review/publication, preserving the existing gate and committed-content checks. Add an end-to-end fixture with all tasks DONE, stale dependency and validation evidence, and a successful installer; require successful review and completion with a clean tree.

- P2: Equal Git status does not prove the installer preserved project files.

  **Location:** `.ai/tasks.md:35`; `.ai/project-spec.md:35`; `scripts/ai-run:264`, `scripts/ai-run:277`.

  The proposed guard compares only `git status --porcelain` output. If a tracked file is already modified, an installer can overwrite it while its status remains ` M`. This is relevant because the runner changes state before launching a task, and its supported DONE path can contain uncommitted implementation files. An installer can also edit and commit a previously clean file, leaving status clean before and after. Neither case necessarily changes the protected gate digest.

  This fails the requirement that setup only install ignored dependencies and preserve project files.

  **Concrete plan change:** Strengthen the spec and task to compare project content and modes, index state, and HEAD before/after setup, excluding ignored dependency outputs. Retain status comparison for additions and removals. Add regressions for overwriting an already modified source file and for an installer committing a tracked-file change; both must stop without recording a successful dependency stamp.

- P3: The dependency-change checkpoint protocol contradicts the current task contract.

  **Location:** `.ai/current-plan.md:54`; `.ai/tasks.md:48`; `templates/.ai/prompts/runner.md:13`; `templates/CLAUDE.md:65`; `scripts/ai-run:277`.

  The plan expects a task that changes dependencies to survive an in-session validation failure and rely on the host installation and gate. Existing instructions require passing validation before DONE and eventually require BLOCKED on unresolved failures. The runner executes its post-task gate only for DONE; BLOCKED skips it, and IN_PROGRESS stops the run. The proposed sentence about noting a lockfile change does not reconcile these rules.

  The planned mock that changes a lockfile and unconditionally reports DONE would miss this failure.

  **Concrete plan change:** Specify an explicit protocol for deferring dependency-related validation to the host, and update the runner and CLAUDE instructions consistently. Record the actual in-session failure without claiming PASS; require host installation and successful validation before accepting completion, and preserve failure handling for other validation errors. Test a task whose in-session gate fails until the changed dependencies are installed.

- P4: Recovery validation omits dependency setup.

  **Location:** `.ai/tasks.md:44`; `.ai/tasks.md:47`; `scripts/ai-recover:159`.

  T001 enumerates setup calls in `ai-run` and `ai-pipeline`, but changes `ai-recover` only for setting restoration. Recovery’s `commit_and_rerun` action runs another host `ai-check`. If an interrupted session changed a lockfile, recovery validates against stale dependencies and can escalate work that would pass after setup. This leaves the “before every host ai-check” requirement incomplete.

  **Concrete plan change:** Include dependency setup before recovery validation, using the manifest-approved gate digest and preserving attempt limits, escalation rules, and checkpoint integrity checks. Extend the recovery fixture with a changed dependency input whose validation succeeds only after setup.

- P5: The no-lockfile shortcut contradicts generic stamp-based freshness.

  **Location:** `.ai/tasks.md:80`; `.ai/project-spec.md:23`, `.ai/project-spec.md:30`.

  T001 requires `current` without running setup when no recognized lockfile or `package.json` exists. The spec instead makes a missing stamp or changed setup script stale. Existing projects can have a configured installer without recognized lockfiles—for example, a Python project installed from `pyproject.toml`, or custom ignored tooling. The shortcut silently skips that approved setup.

  **Concrete plan change:** Remove the inference that absent recognized files means setup is unnecessary. Apply the setup digest and missing-stamp rules even with an empty input map. Replace the shortcut test with a configured no-lockfile fixture that runs setup once, records a stamp, and skips subsequent unchanged runs.

## MINOR findings

- P6: The proposed wait regression test forbids its required documentation.

  **Location:** `.ai/tasks.md:168`, `.ai/tasks.md:192`.

  T003 requires README text explaining why `pgrep -f` waits are wrong, then requires no `pgrep -f` anywhere in README, docs, scripts, or templates. A literal absence assertion fails on the mandated explanation.

  **Concrete plan change:** Restrict the prohibition to executable wait implementations. Allow explanatory documentation, and separately assert that README includes the PID-based example and self-matching warning.

- P7: T001 and T002 are too broad for the requested bounded tasks.

  **Location:** `.ai/tasks.md:61`, `.ai/tasks.md:124`.

  T001 spans nine artifacts across freshness parsing, execution integrity, three host scripts, settings, templates, tests, and the flow chart. T002 spans roughly ten artifacts across runtime parsing/rendering and prompt guidance. Each combines independently verifiable changes in one checkpoint.

  **Concrete plan change:** Split T001 into freshness/stamp helpers, runner integration, and pipeline/recovery integration. Split T002 into runtime rendering and template guidance. Declare dependencies explicitly, keep flow-chart updates with each behavioral change, and make T004 depend on every resulting task. Preserve risk-appropriate explicit models.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Task-queue validation passed.
- Documentation consistency tests: **3 passed**.
- Shell syntax: **12 files passed**.
- Python syntax: **3 files passed**.
- No existing `pgrep -f` occurrences found in the proposed scan locations.
- Stored baseline evidence records **188 tests passing** at `9e11a11`, before planning.
- Current validation-stamp verification failed as stale.
- Full `./scripts/ai-check`, `.ai/bin/ai-check`, and integration tests were not run because they create fixtures and validation artifacts requiring write access.

## Security and architecture concerns

The host package-manager execution risk and agent-writable dependency stamp are explicitly acknowledged by the plan. P2 concerns enforcement of the separate project-preservation requirement.

All four tasks specify models; their assignments fit the described risks. Dependencies are coherent at the current task granularity, and behavioral tasks include same-task flow-chart updates. No additional findings were identified in the inspected FL-09 rendering and watchdog installation design, beyond the coverage and decomposition issues above.

## Validation after revision

Add the regressions described in P1–P5. Also exercise symlink escapes, added/removed glob inputs, and the remaining run-time budget after setup consumes time.

After implementation, manually inspect the PR split and phone notification, run from a fresh worktree, and confirm the opted-in timer is active. Human acceptance remains separate from review.