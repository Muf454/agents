<!-- Plan review of plan digest f3557e3c1bdd66f4681e51012306d8f2291a9eff339d3289ff1efba97f410838; saved 2026-10-06T08:50:37Z. -->

# Plan review

Overall verdict: REVISE before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=2

Reviewed HEAD: `31cec2ccd79541d3858f9e9e7828216c7156787f`

Scope: FL-01, FL-07 and FL-09; repository instructions, spec, plan, task queue, affected scripts/templates, tests, documentation, relevant vault notes and validation evidence. No files modified; no network or MCP integrations invoked. New finding IDs continue after the earlier P1–P7 review.

## BLOCKER findings

None.

## MAJOR findings

- P8: Dependency setup stops can enter automatic recovery instead of escalating.

  **Location:** `.ai/tasks.md:95`, `.ai/tasks.md:147`; `.ai/project-spec.md:37`; `scripts/ai-pipeline:117`; `scripts/ai-recover:102`.

  T002 reports dependency failures through `ai_die`. Inside the pipeline, that stop reaches `ai-recover`. Its hard rules do not recognize either “Dependency setup … failed” or “Dependency setup changed project files,” and T003 explicitly keeps those rules unchanged.

  Consequently, a rejected installer that changes source can be followed by a recovery decision of `commit_and_rerun`. If its second execution is harmless or succeeds, the new snapshot accepts the already changed tree as its baseline. Recovery can then validate, commit and resume with the installer’s unwanted changes. A one-time installer failure can likewise be retried despite the spec requiring escalation.

  **Concrete plan change:** Make dependency setup failures and project-preservation violations mandatory escalation reasons before recovery inference or checkpointing. Check gate/tree preservation after unsuccessful installer executions too, retaining the integrity violation when applicable. Add pipeline tests with auto-recovery enabled for a fail-once installer and a change-once installer; neither may produce a recovery checkpoint, resume implementation or open a PR.

- P9: The tree snapshot does not define preservation of submodule contents.

  **Location:** `.ai/tasks.md:37`; `scripts/lib/workflow.py:536`; `tests/test_workflow.py:1833`.

  The proposed `git ls-files --cached --others --exclude-standard -z` enumeration returns a submodule’s directory entry, not its internal files. T001 specifies representations for regular files, symlinks and missing paths, but none for submodule HEAD, index or working-tree content. Hashing only the directory’s kind/mode would miss changes inside it; attempting to read it as file bytes would fail.

  Submodules are already supported explicitly by the validation fingerprint and an existing pipeline test. That test uses an empty submodule, so it cannot establish that the new installer guard preserves nested source or already dirty submodule content during recovery.

  **Concrete plan change:** Define a submodule snapshot that includes its HEAD, staged state and tracked/non-ignored untracked content, recursively where necessary. Preserve unchanged submodules without rejecting this existing supported project shape. Add regressions for changing submodule HEAD, overwriting a submodule file and overwriting an already modified submodule file; each installation must stop without recording a stamp.

## MINOR findings

- P10: “Timer installed” needs a defined operational check.

  **Location:** `.ai/tasks.md:268`, `.ai/tasks.md:296`; `scripts/lib/watchdog.py:183`.

  T006 defines status text and unit naming, but not how installation status is determined. The current installer writes both unit files before calling `systemctl daemon-reload` and `enable --now`. A failed installation therefore leaves files that an existence-only status check could report as installed, suppressing the pipeline warning even though the timer never started.

  **Concrete plan change:** Define the condition explicitly, preferably requiring the expected units and an enabled, active timer. Treat unavailable systemd status as a warning without stopping the pipeline. Extend the mock-systemctl tests to cover partial installation failure and disabled/stopped timers, including the resulting STARTED/RESUMED notification.

- P11: The timeout tests do not verify the remaining-run-time cap.

  **Location:** `.ai/tasks.md:97`, `.ai/tasks.md:119`; `scripts/ai-run:119`.

  The only planned timeout scenario sets `AI_DEPS_TIMEOUT=1`. It would pass even if the implementation always used that setting without capping it to `remaining_time()`, leaving the spec’s run-budget requirement untested.

  **Concrete plan change:** Add a runner regression with a short `--run-timeout`, a much larger `AI_DEPS_TIMEOUT` and a sleeping installer. Require termination within the run budget, no successful dependency stamp and no implementation-agent invocation.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Task-queue validation passed.
- Documentation consistency tests: **3 passed**.
- Shell syntax: **12 files passed**.
- Python syntax: **3 files passed**.
- Stored baseline evidence records **188 tests passing** at `9e11a11`, before planning.
- Current validation-stamp verification failed as stale; the stored baseline is not validation of this revision.
- Full `./scripts/ai-check`, `.ai/bin/ai-check` and integration tests were not run because they require writable fixtures and validation artifacts.

## Scope, models and architecture

The revision addresses the earlier logging, task-contract and no-lockfile gaps. The dependency ordering is coherent, every task has an explicit model, and FL-01’s integrity-sensitive work uses `opus`. No failed implementation attempt is recorded for these TODO tasks.

Host execution of package-manager code and the agent-writable dependency stamp are acknowledged risks in the plan. P8 and P9 concern enforcement of the separate stop and project-preservation requirements. No additional findings were identified in the inspected FL-09 rendering approach.

## Validation after revision

Add the regressions above and run the required full gate. Human acceptance should include a fresh-worktree run, confirmation that the opted-in timer is active, and inspection of the PR’s testing split and phone notifications.