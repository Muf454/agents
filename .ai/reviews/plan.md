<!-- Plan review of plan digest 867c4eaddbf51b9623b54457dcff131ae75210c2f083d1b57869985a691e5119; saved 2026-10-07T11:56:04Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=2

Reviewed HEAD: `18e00863603f5aa41e48ea8bce5c10d2f6a520dc`.

Inspected repository instructions, spec, plan, tasks, state/handoff, affected source, existing tests, validation scripts, documentation, Git history, and the vault flow chart. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

- P19: Recovery’s explicit Checks transition conflicts with the helper’s precedence rule.

  **Location:** `.ai/tasks.md:49–58`, `.ai/tasks.md:132–134`; `scripts/ai-recover:159–165`.

  T002 calls `observe recovering "<attempt>/<max>" checks` before recovery validation. T001 applies its outer-label precedence rule to this argument, but that table contains `validation`, not `checks`. Unknown labels preserve the previous stage.

  Applying the specified rule to a recovering Build therefore leaves it on Build while validation runs. This contradicts the spec’s required `stage=checks, state=recovering`. The acceptance criteria do not explicitly test this transition.

  **Concrete plan change:** Distinguish a normalized stop label from an explicit stage key. For `recovering NOTE STAGE`, require a valid stage key and select it directly; without STAGE, preserve the current stage. Add helper and recovery-fixture assertions for Build → Checks while remaining recovering, followed by validation failure and escalation.

- P20: The shared safe-reader interface does not cover all required dashboard paths.

  **Location:** `.ai/tasks.md:36–45`, `.ai/tasks.md:184–198`; `scripts/lib/watchdog.py:90–111`.

  T001 supplies `local_dir_fd(root)`, which returns a descriptor for `.ai/local`. T003 requires every checkout file to use that interface, including `.ai/tasks.md` and Git metadata. Those files are elsewhere. This checkout demonstrates both cases: tasks are in `.ai/tasks.md`, and `.git` redirects to `/home/zack/Projects/agents/.git/worktrees/agents-dashboard`.

  The plan does not specify how to obtain safe descriptors for those locations. Using ordinary pathname reads would bypass the promised protection against FIFOs, intermediate symlinks, and directory replacement. Reading everything relative to the local descriptor would instead lose required fields.

  The reader contract should also expose metadata from the opened descriptor: watchdog liveness deliberately reads PID and marker mtime from the same file, then re-reads the marker.

  **Concrete plan change:** Extend T001’s `opus` work with explicit safe directory traversal for checkout root, `.ai`, `.ai/local`, and normal/worktree Git metadata. Define bounded reads that return content and descriptor metadata together. Make T003 consume those APIs. Add normal-repository and worktree branch/task-count tests, unsafe Git-metadata tests, and a marker-replacement test that preserves watchdog identity semantics.

## MINOR findings

- P21: T002 is too broad for one unattended task.

  **Location:** `.ai/tasks.md:104–167`.

  T002 combines notification mirroring, pause overlays, pipeline registration and stages, task-runner stages, recovery hooks, integration tests, handoff changes, and a vault update. It spans seven named files or artifacts and several distinct execution paths.

  **Concrete plan change:** Split it into smaller tasks for notification/pause hooks, pipeline hooks, and runner/recovery hooks, each with focused validation. Keep required flow-chart updates in the same task as the corresponding behavior change.

- P22: The handoff reports a future flow-chart update as completed.

  **Location:** `.ai/handoff.md:18–21`; `.ai/tasks.md:135–139`.

  The handoff says “Flow chart updated (by T002)” and describes the new dashboard note as present. T002 remains TODO, and the inspected vault note has no dashboard/observation entry and retains `updated: 2026-10-06`.

  This is a planning-record defect, preceding implementation. The existing test checks the declaration’s wording, not whether the update happened.

  **Concrete plan change:** Explicitly mark the update as pending T002 while retaining the required test marker. Replace that pending statement with completed evidence only after T002 updates the vault note and date.

## Validation observed

- Requested HEAD confirmed; working tree remained clean.
- Planning diff whitespace check passed.
- Task-queue validation passed.
- Python syntax checks passed for the two existing library modules and test module.
- Bash syntax checks passed for 13 files.
- Documentation consistency: **3 tests passed**.
- Existing flow-chart test’s first assertion now passes; its writable fixture portion was not run.
- Read-only probes confirmed the task/Git path mismatch and reproduced the literal recovery-precedence result.
- Validation-stamp verification failed: **no validation evidence exists in this checkout**.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and integration fixtures were not run because they create files, repositories, locks, and validation artifacts. Dashboard implementation tests do not exist yet.

## Security, architecture, and model assessment

The stdlib-only, advisory dashboard fits the requested scope. The earlier bounded-I/O, locking, substage, and rendering revisions substantially improve the plan.

Every task specifies a model; no failed implementation retry is recorded. Keep the additional safe traversal and marker-reading work in T001 on `opus`, allowing T003 on `sonnet` to assemble already-tested helpers.

## Manual testing recommendations

After implementation and automated validation, inspect two simultaneous tmux runs through build, checks, pause, recovery, stop, and finish. Verify scrolling, selection, expansion, resizing, role colors, and terminal restoration.

This review assesses plan readiness, not implementation correctness or human acceptance.