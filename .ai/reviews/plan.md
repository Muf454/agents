<!-- Plan review of plan digest e6dc5a34b2203ff038fdb8c959cf870d084f4dee68adea3a38d6ac866b351090; HEAD 6bd6e3ef0767ecf01c1e8016e3a3a11aee114f1c; saved 2026-10-21T21:11:20Z. -->

# Plan review — batch 11

Scope: `HEAD=6bd6e3ef0767ecf01c1e8016e3a3a11aee114f1c`, tasks T301–T314.

Overall verdict: REVISE BEFORE IMPLEMENTATION
Finding counts: BLOCKER=1 MAJOR=7 MINOR=3

## BLOCKER findings

- P1: The new stop paths can execute a changed checkout helper before verifying the gate.

  **Location:** `.ai/tasks.md:5403`, `.ai/tasks.md:5408`, `.ai/tasks.md:5410`.

  T306 explicitly puts `ai_helper run-record stop-requested` first in `stop()`, before its existing gate check (`scripts/ai-pipeline:178`). The signal handler also calls helpers before checking the gate. Merely checking `AI_GATE_BROKEN` is insufficient: the interrupted child’s flag is not exported, and the pipeline may not have checked the changed files yet. A session that changes `.ai/bin/lib/workflow.py` can therefore cause that changed code to execute during shutdown—the condition the current guard prevents.

  **Plan change:** After stopping and reaping the child, verify the approved gate with the already-loaded inline verifier before invoking any checkout helper or making a bookkeeping commit. Define a shutdown path that uses no checkout helper when the gate is changed, unreadable, or not yet approved. Add pipeline tests for helper tampering followed by both a child failure and an interrupt; assert that the tampered helper never executes.

## MAJOR findings

- P2: Signal forwarding does not cover the full parent-to-child chain.

  **Location:** `.ai/current-plan.md:48`, `.ai/tasks.md:5405`; existing calls at `scripts/ai-pipeline:265`, `scripts/ai-pipeline:552`, `scripts/ai-run:304`, `scripts/ai-recover:303`.

  T303/T304 wrap the leaf `timeout` commands, but T306 leaves the pipeline waiting on foreground runner/reviewer/gate scripts. Its `AI_CHILD_PID` therefore does not identify those children. The runner and recovery also invoke host validation in the foreground. A PID-only stop cannot run the ancestor’s trap until that foreground child finishes. Ordinary sleeps, including usage-limit waits, have the same problem.

  A process-only reproduction of the proposed trap/helper arrangement delayed the pipeline trap until its foreground child exited. Existing proposed integration tests mostly signal entire process groups, masking this gap.

  **Plan change:** Wrap every potentially long blocking call along the pipeline, runner, and recovery paths, including host gates and pause/retry sleeps. Add PID-only INT/TERM tests during implementation, review, validation, dependency setup, and waits. Make T306 depend on the completed forwarding work.

- P3: The detached `setsid` fallback inherits ignored SIGINT.

  **Location:** `.ai/tasks.md:5759`, `.ai/tasks.md:5778`; `scripts/lib/workflow.py:5112`.

  The proposed `setsid python3 … exec-logged … &` launch inherits ignored SIGINT from the noninteractive shell’s background job. `exec-logged` preserves that disposition through `execv`; the eventual Bash pipeline cannot make its INT trap effective. Consequently, the advertised `--stop`, which sends SIGINT, can time out while the fallback run continues.

  A process-only reproduction of this launch chain confirmed that SIGINT remained ignored and the Bash INT trap never ran. The fallback acceptance test checks launch metadata and logging, but never stops the detached run.

  **Plan change:** Reset signal dispositions before executing the detached Bash runner, using a controlled launcher. Add an end-to-end fallback test that starts a sleeping fixture pipeline and successfully stops it through `ai-pipeline --stop`.

- P4: A watchdog-started recovery retains the dead pipeline’s process identity until recovery finishes deciding.

  **Location:** `.ai/tasks.md:5214`, `.ai/tasks.md:5456`; `scripts/ai-recover:137`, `scripts/ai-recover:358`.

  T302 updates the run’s process identity only when the resumed pipeline starts. A recovery launched after a crash has a different PID and may spend minutes validating or running its decision session first. During that interval, the current run record still identifies the dead pipeline. T308 therefore returns “no run active” instead of stopping the active recovery.

  **Plan change:** Once recovery owns the checkout lock and has checked the stop request, publish its own identity before any long recovery work. Keep the run ID and define when `resumes` increments. Add a test that starts recovery with a new PID and invokes `--stop` during its sleeping decision session; verify that no subsequent resume occurs.

- P5: Atomic writes do not bind stop and completion operations to the run they originally inspected.

  **Location:** `.ai/tasks.md:5163`, `.ai/tasks.md:5213`, `.ai/tasks.md:5512`.

  `request-stop` and `end` operate on whichever record is current when called. The stop command intentionally holds no checkout lock while waiting. Run A can exit, run B can acquire the checkout and replace `current`, and A’s stopper can then mark B `human_stop` or write stale escalation/local error records into B’s run. Locking individual JSON mutations prevents torn writes, but does not prevent this ownership race.

  T302’s best-effort `start` creates a related problem: a run can continue without publishing its identity, leaving later current-record mutations aimed at an older run.

  **Plan change:** Return and retain a run ID at successful start. Require the expected run ID and appropriate process identity for lifecycle mutations, checking them under the host lock. Condition escalation/local cleanup on the same ownership. Require successful record publication before controlled work starts. Add deterministic interleaving tests where B starts before A’s stopper finishes.

- P6: A committed SKIPPED task invalidates the queue on the next branch or checkout.

  **Location:** `.ai/tasks.md:5657`, `.ai/tasks.md:5660`; `scripts/lib/workflow.py:1454`.

  The skip authorization is keyed by checkout path and branch, while `Status: SKIPPED` is committed in Git. After creating the next feature branch, merging the work, or opening another worktree, the same task has no matching host record and `tasks check` fails. The plan provides no way to authorize inherited skips; ordinary task commands also begin by parsing the now-invalid queue.

  **Plan change:** Specify a human-authorized carry-forward or reauthorization mechanism for committed skip records across branches and checkouts. Preserve the protection against sessions inventing skips. Add regressions covering a committed skip followed by a new branch and a separate worktree.

- P7: The standalone runner’s record and escalation lifecycle is incomplete.

  **Location:** `.ai/tasks.md:5220`, `.ai/tasks.md:5568`, `.ai/tasks.md:5571`; `scripts/ai-run:127`, `scripts/ai-run:129`, `scripts/ai-run:243`.

  T302 prescribes `run-record start ai-run "$branch"` after acquiring the lock, but `ai-run` has no `branch` variable; it uses `AI_START_BRANCH`, initialized later. With `set -u`, the prescribed call fails. Starting a record before installing `on_exit` also leaves early startup refusals without the promised terminal record.

  Separately, T309 clears escalation only at pipeline manifest start or recovery resume. A fresh standalone `ai-run` calls neither, so a previous escalation remains visible while the new run is active, contrary to FR-6.

  **Plan change:** Specify the standalone startup order using the actual branch variable, install lifecycle cleanup before publishing a run, and clear the previous escalation when that new run becomes current. Test a fresh start after escalation and a startup refusal after publication.

- P8: The models assigned to process lifecycle work do not match its concurrency risk.

  **Location:** `.ai/tasks.md:5205`, `.ai/tasks.md:5744`.

  T302 assigns `sonnet` to process ownership and recovery handoff. T313 assigns `sonnet` to asynchronous service/session launch and startup acknowledgement. These tasks determine which concurrent process owns a run and whether it can be stopped; the review’s model rule requires `opus` for concurrency work.

  **Plan change:** Set these tasks to `Model: opus`, or split out the lifecycle and concurrency implementation into explicit opus tasks, leaving sonnet only mechanically bounded wiring after those contracts are complete.

## MINOR findings

- P9: The dead-process stop contract contradicts itself.

  **Location:** `.ai/current-plan.md:82`, `.ai/tasks.md:5531`, `.ai/project-spec.md:120`.

  The design writes a stop request for a dead process with outcome `running`; FR-5 and T308’s acceptance test require exit 3 with no changes for a dead PID.

  **Plan change:** Choose one behavior and align the design, specification, messages, and tests. Distinguish cancellation of a scheduled relaunch explicitly.

- P10: The skip acceptance scenario conflicts with the dependency refusal rule.

  **Location:** `.ai/tasks.md:5667`, `.ai/tasks.md:5683`, `.ai/tasks.md:5688`.

  One test expects skipping a task to make its dependent eligible, while another requires refusal whenever an unfinished dependent exists.

  **Plan change:** Preserve the specified refusal and test dependency satisfaction by adding a dependent after an authorized leaf skip, or explicitly revise the intended dependency rule.

- P11: T309 is too broad for one bounded implementation session.

  **Location:** `.ai/tasks.md:5558`, `.ai/tasks.md:5579`.

  It spans producer classification, shutdown writers, clearing, fix-round completion, seven repository files, documentation, vault updates, and multiple integration scenarios. This exceeds the requested few-file task size and leaves little implementation time after the stated full-gate duration.

  **Plan change:** Split producer hints, lifecycle writes/clearing, and completion/escalation integration into separately validated tasks with explicit dependencies.

## Validation observed

- Confirmed the requested HEAD and a clean working tree.
- Inspected repository guidance, spec, plan, current tasks, state/handoff, relevant documentation, source, schemas, fixtures, and validation entry points.
- Python AST parsing passed for nine source/test files.
- `bash -n` passed for fifteen scripts and validation entry points.
- Ran two isolated, process-only signal reproductions supporting P2 and P3; they created no files and signalled only fixture processes.

The full gate and integration suite were not run because their fixtures require filesystem writes. The handoff’s earlier gate result is historical evidence, not validation of this plan. No files were modified and no network or MCP integrations were invoked.

## Scope and manual validation

These findings concern the proposed batch; the current lack of run controls is pre-existing. No application schema or authentication/RLS changes are involved. The principal safety concerns are gate verification and concurrent ownership of processes and host records.

After implementation, retain the specified human acceptance checks and include stopping both detached launch modes, stopping a watchdog-started recovery, and confirming that a subsequent branch can use a queue containing committed SKIPPED tasks.