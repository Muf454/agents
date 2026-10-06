<!-- Plan review of plan digest 2eeff583c15f8b102041c4f88491ab3623bc08dbf0d06a975d190f0a44d03332; saved 2026-10-06T05:16:10Z. -->

# Plan review

Overall verdict: REVISE before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=1

Reviewed HEAD: `3284ee58b175ef551c5d7f0711d4e43b13ae91f0`

Scope: OR-01/OR-02 plan, task queue, affected scripts, helper functions, integration fixtures, validation, documentation, and vault workflow notes. No files modified.

## BLOCKER findings

None.

## MAJOR findings

- P1: Watchdog installation may check the wrong checkout.

  **Location:** `.ai/tasks.md:184`, `scripts/lib/watchdog.py:267`, `scripts/lib/workflow.py:773`.

  T004 permits importing and calling T003’s `check_state_root()`, which discovers the checkout through Git in the current directory. However, `ai-watchdog PROJECT --install-timer` calls `timer()` before `os.chdir(root)`. From another repository, that implementation checks the caller’s repository; from outside any repository, it rejects an otherwise valid installation. It can therefore miss state-root overlap with the supplied project. Existing fixtures always launch from the project directory.

  **Plan change:** Require the check to use the supplied `root`, either through an explicit checkout argument or a subprocess with `cwd=root`. Add installation tests launched from outside Git and from another checkout, including a state root overlapping only the target project.

- P2: Planned tests do not exercise several required committed-content gates.

  **Location:** `.ai/tasks.md:41`, `.ai/tasks.md:88`; `scripts/ai-run:234`, `scripts/ai-pipeline:160`.

  T001 requires checking the final handoff commit, but its negative tests fail at an ordinary task checkpoint. They would still pass if the final handoff check were omitted. T002’s negative publication test stops at PR preparation, so it does not establish that byte mismatches introduced during push attempts are detected. Existing push tests exercise other invariants, rather than a clean checkout with mismatching committed bytes.

  **Plan change:** Add a mismatch introduced only by the final handoff commit, plus push-hook cases producing a committed-byte mismatch during a failed and successful push. Assert the integrity reason, preserved queue/commits, and absence of subsequent retries, PR actions, or FINISHED notifications where applicable.

- P3: The specified recovery insertion point precedes its escalation function.

  **Location:** `.ai/tasks.md:139`, `scripts/ai-recover:27`, `scripts/ai-recover:35`.

  T003 places `state-root-check` immediately after `ai_root`/lock and calls `escalate` on failure. At that point, `escalate()` has not been defined, and its `branch` and `reason` variables have not been initialized. A literal implementation produces an undefined-command failure instead of the required escalation. No planned test exercises this refusal path. T004 also adds runtime recovery refusals without corresponding negative tests.

  **Plan change:** Place the recovery check after escalation setup and before the first manifest read. Preserve the configuration error in the persisted stop reason. Add tests for `ai-recover` and host-watchdog runtime refusals, asserting useful diagnostics and no recovery Claude or `systemd-run` invocation.

## MINOR findings

- P4: Specify how the ordinary-commit mode test keeps Git’s tree clean.

  **Location:** `.ai/tasks.md:35`, `.ai/tasks.md:48`; `scripts/ai-run:266`, `tests/test_workflow.py:597`.

  Committing mode `100644` while leaving an executable file normally makes Git report a mode change. The runner then enters tier-1 recovery and can restage the executable mode, bypassing the intended ordinary-commit test. The existing mode test explicitly uses `core.filemode=false`.

  **Plan change:** Require that setting in the new fixture, and assert a clean Git status alongside a demonstrable HEAD/disk mode mismatch before the new check runs.

## Validation observed

- HEAD matches the requested scope; working tree is clean.
- Existing documentation consistency tests: **3 passed**.
- Shell syntax: **13 files passed**; Python syntax: **3 files passed**.
- Task parsing and validation-stamp verification succeeded.
- Stored baseline evidence records **168 tests passing**; this suite was not rerun.
- Full gate and integration tests were not run because they require writable fixtures.

## Security and architecture concerns

The selected models fit the tasks’ risks. The planned checks remain configuration checks; they do not establish OS isolation. Explicitly targeting the correct checkout and testing recovery refusals are necessary for the authority boundary.

## Manual testing recommendations

After implementation, use a scratch checkout to verify watchdog installation from another directory, refusal before agents launch, and final-handoff mismatch diagnostics. Verify the vault flow chart’s `updated:` date and the PR’s flow-chart statement.