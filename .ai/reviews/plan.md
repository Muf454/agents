<!-- Plan review of plan digest 392914fc2e6fbdde37e3d95642386d7e59f3170217bb7cf819bc08f6a899141a; HEAD ff5f8fdbd7c337918d0b72a02ed987d2462dc885; saved 2026-10-17T08:43:06Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `ff5f8fdbd7c337918d0b72a02ed987d2462dc885`

## BLOCKER findings

None.

## MAJOR findings

- P16: Disarming before task-consistency checks still permits recovery to commit rejected preserved work.

  **Location:** `.ai/tasks.md:735`, `.ai/tasks.md:778`, `.ai/tasks.md:832`; `.ai/current-plan.md:234`.

  T018 protects the earlier re-check stop, but T011 explicitly removes the arm **before** checking whether another task became DONE or whether the next runnable task matches the bound task. It then states that these failures use normal recovery.

  With approved `AI_AUTO_RECOVER=1`, either consistency failure reaches `stop implementation` and ordinary recovery (`scripts/ai-pipeline:155`). Neither prescribed message matches the recovery hard rules (`scripts/ai-recover:137`), and T018’s new check cannot fire because the arm is gone. A `commit_and_rerun` decision can therefore validate and commit the inconsistent task queue and preserved source (`scripts/ai-recover:200`). If both tasks were marked DONE, the resumed pipeline can skip implementation altogether.

  This defeats T011’s acceptance criterion requiring no session and nothing committed for the additional-DONE case. The fixture’s default `AI_AUTO_RECOVER=0` conceals it.

  **Concrete plan change:** Keep the arm until the preserved-work consistency checks and bound-task routing checks pass. These failures must reach T018’s terminal recovery rule with the arm retained. Run both inconsistent-queue regressions with `AI_AUTO_RECOVER=1` and `MOCK_RECOVER=commit_and_rerun`; assert one escalation, no recovery session, unchanged HEAD/files, and the arm retained. Ordinary recovery may resume after a successful handoff to the bound task.

## MINOR findings

- P19: A refused due relaunch can also trigger the ordinary stalled-run alarm.

  **Location:** `.ai/tasks.md:169`, `.ai/tasks.md:185`, `.ai/tasks.md:222`.

  T002 continues normal incident detection after handling a due schedule, while suppressing stalls only until AT. A scheduled implementation run retains phase `implementing`. When recovery is refused because the gate changed, no runner starts and no last-error is written (`scripts/lib/watchdog.py:311`).

  The first due probe records `stall_seen_ns`; a second probe ten minutes later emits the ordinary “killed runner?” escalation (`scripts/lib/watchdog.py:443`). Deduplicating `relaunch:<AT>` does not suppress this separate `stalled` incident. Consequently, the second probe sends another notification despite the acceptance criterion requiring silence.

  **Concrete plan change:** Exclude a due relaunch handled by the probe from ordinary stall detection. Preserve normal stall handling once the schedule is absent. Extend the refusal regression with phase `implementing`, no last-error, and two probes separated by more than `STALL_CONFIRM_NS`; assert exactly one notification overall.

## Previous findings re-evaluated

T018 covers P16’s original uncommitted-review-record scenario. The remaining P16 finding concerns the same recovery bypass at T011’s subsequent consistency checks.

P17 is addressed by dependency setup before the preserved DONE checkpoint, including the no-runnable-task case and installer-failure coverage. P18’s message assertions now match the task-bound output. Other previously reported scenarios remain covered by explicit tasks and acceptance criteria.

All 18 tasks specify a model; no additional model-selection finding was identified.

## Validation and limitations

Inspected repository instructions, spec, plan, all tasks, state, handoff, dispositions, revision history, relevant source, tests, documentation, and `.ai/validate`.

Observed checks passed:

- Task queue validation.
- Three documentation consistency tests.
- Shell syntax checks for 13 files.
- AST parsing for eight Python files.
- `git diff --check 47e2eab..HEAD`.

Read-only, in-memory probes confirmed that both consistency-error messages bypass existing recovery hard rules, and that the planned stall predicate permits the second alarm described in P19.

The full `./scripts/ai-check` and integration fixtures were not run because they require filesystem writes. Proposed behavior remains unimplemented. No files were modified or network/MCP integrations invoked.