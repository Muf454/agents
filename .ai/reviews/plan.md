<!-- Plan review of plan digest 2955fe5bcd92fb8d375dae3910bbd61eda783b775c8d0283260761929a52ecba; saved 2026-10-06T05:22:52Z. -->

# Plan review

Overall verdict: REVISE before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=3

Reviewed HEAD: `92f5cf11becb32e12e77a415951396bf7d710792`

Scope: revised OR-01/OR-02 spec, plan, six tasks, affected scripts and helpers, integration fixtures, validation evidence, documentation, and vault flow chart. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

- P2: The last failed push bypasses the required integrity check.

  **Location:** `.ai/tasks.md:96`, `.ai/tasks.md:119`; `scripts/ai-pipeline:159–165`.

  T002 assumes `push()` already checks publication invariants after every push. It checks before each attempt and after success, but the third failure calls `stop` before the subsequent check. If two attempts fail harmlessly and the third hook introduces filtered committed bytes, the pipeline records only `git push failed (3 tries)`. It loses the required mismatch detail and escalation phrase, potentially allowing a recovery Claude session. The planned fixture mutates on the first attempt, so it misses this path.

  This is an existing control-flow gap that the proposed implementation would retain despite OR-01’s requirements.

  **Plan change:** Check `publish_ready` after every push outcome, before retry waiting or terminal failure handling. Add a fixture whose first two pushes fail unchanged and whose third creates a committed-byte mismatch and fails. Assert the file-specific integrity reason, preserved commits/tasks, no recovery Claude invocation, and no PR action or FINISHED notification.

## MINOR findings

- P4: The mode test cannot assert a completely clean tree after the runner stops.

  **Location:** `.ai/tasks.md:55–59`; `scripts/ai-run:76–84`.

  The revised fixture correctly uses `core.filemode=false`, but requires empty `git status` after the failed run. The runner’s EXIT handler appends a stop entry to tracked `.ai/run-log.md`, leaving bookkeeping dirty even when the tree was clean at the integrity check.

  **Plan change:** Assert full cleanliness at the check boundary, or assert afterward that only `.ai/run-log.md` changed. Retain assertions for the HEAD/disk mode mismatch and absence of a tier-1 checkpoint. Adjust the spec’s wording to distinguish checkpoint cleanliness from post-stop bookkeeping.

- P5: The suggested final-handoff filter also matches the initial state template.

  **Location:** `.ai/tasks.md:39–42`; `templates/.ai/state.md:15`.

  The plan says `ready_for_review` appears only at final handoff. It already appears in the template’s phases comment. A filter replacing that token globally creates a mismatch before the intended final-handoff boundary.

  **Plan change:** Specify a filter matching only the phase field, such as `^Phase: ready_for_review$`. Require ordinary task checkpoints to pass before asserting failure at the final handoff.

- P6: Flow-chart updates are deferred beyond the task that changes the flow.

  **Location:** `.ai/current-plan.md:53–56`, `.ai/tasks.md:303–329`; `AGENTS.md:12`, `CLAUDE.md:9–10`.

  T001–T005 change gates and recovery behavior, but the chart update is deferred to dependent T006. The repository requires updates in the same session, and CLAUDE.md explicitly requires the same task. Each implementation task runs in a fresh session.

  **Plan change:** Include the corresponding chart changes and `updated:` date in each task that changes workflow behavior. Keep T006 for the final documentation audit, consolidation, and manual testing instructions.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Task-queue validation passed.
- Documentation consistency tests: **3 passed**.
- Shell syntax: **13 files passed**.
- Python syntax: **3 files passed**.
- Stored baseline evidence records **168 tests passing** at `d6038f6`.
- Current validation-stamp verification failed as stale.
- Full gate and integration tests were not rerun because they create writable fixtures and validation artifacts.

## Security and architecture concerns

The explicit models fit the implementation risks. The revised target-checkout and recovery-check placement address earlier P1 and P3. The exhausted-push path still needs deterministic integrity escalation. The authority-root checks remain configuration checks and do not establish OS isolation.

## Manual testing recommendations

After implementation, verify refusal before agents launch, watchdog installation from outside Git and another checkout, final-handoff diagnostics, and integrity failure on the third failed push. Check the vault chart’s date and the PR’s flow-chart statement.