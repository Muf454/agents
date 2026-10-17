<!-- Plan review of plan digest 43c45999d5c8eb2e15f399c577cdeecdd026372c38b52f11b55e4b53c7a7eceb; HEAD 9f5ea88d8022f97a3fde1f14994fce36766586e0; saved 2026-10-17T08:18:08Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `9f5ea88d8022f97a3fde1f14994fce36766586e0`

## BLOCKER findings

None.

## MAJOR findings

- P3: Preserved work still cannot finish when the limited session already committed its task as DONE.

  **Location:** `.ai/tasks.md:631`, `.ai/tasks.md:644`, `.ai/project-spec.md:96`.

  T011 selects the checkpoint path only when `tasks newly-done HEAD` finds a status change. A session can commit its task as DONE, make further source edits, then hit the usage limit. The preserved tree qualifies for an arm, but the task is already DONE in HEAD, so `newly-done` returns nothing.

  With a one-task queue, `tasks next` then returns `none` (`scripts/lib/workflow.py:642`). The unchanged final-handoff path validates but commits only bookkeeping (`scripts/ai-run:623`), leaving the preserved source dirty. `verify_checkpoint` rejects it, returning the run to recovery instead of fulfilling the promised automatic checkpoint.

  **Concrete plan change:** Bind preserved work to the interrupted task, including when that task is already DONE in HEAD. Route its remaining work through the validated checkpoint path before selecting another task or entering final handoff. Add a regression where the last task is committed DONE, further source edits precede the limit, and the relaunch completes without a recovery decision session.

- P14: Initializing `ai-plan` changes the meaning of relative directory arguments.

  **Location:** `.ai/tasks.md:1123`, `.ai/tasks.md:1128`.

  T006 now calls `ai_root` before forwarding options to ai-run, while resolving only the prompt path beforehand. `ai_root` changes to the repository root (`scripts/lib/common.sh:115`). Consequently, relative `--read-dir` and `--knowledge-dir` arguments reach ai-run with a different working directory.

  For example, from `/repo/subdir`, `ai-plan objective.md --read-dir ./reference` resolves `/repo/reference` instead of `/repo/subdir/reference`. It either rejects a valid invocation or supplies the wrong reference directory. Existing ai-run resolves directory arguments before changing directories (`scripts/ai-run:71`).

  **Concrete plan change:** Resolve every directory argument against the caller’s working directory before `ai_root`, preserving repeated options and existing validation. Test foreground and detached launches from a subdirectory, including distinct reference directories with the same relative name at both locations.

## MINOR findings

- P15: The needs-human regression expects an arm that recovery never creates.

  **Location:** `.ai/tasks.md:810`.

  The test plants a needs-human record after scheduling and expects the relaunch to stop with the manifest “still armed.” However, T003 retains the plan-decision check before the claimed-relaunch transitions that call `limit-arm` (`.ai/tasks.md:298`; `scripts/ai-recover:114`). Recovery therefore escalates before arming.

  **Concrete plan change:** For this end-to-end case, require the schedule consumed, no arm created, unchanged checkout, and no session. Separately test the pipeline’s decision checks by starting a resume with an already armed manifest.

## Previous findings re-evaluated

T016 addresses round 5’s stale-plan-review path, T006 addresses first-use initialization, and T002 corrects the contradictory stall-notification expectation. Those findings are not repeated. P3 remains for the distinct committed-DONE continuation case above.

The inspected scheduling, tree-verification, logging-safety and draft-ownership tasks explicitly cover the other previously reported scenarios.

## Validation and limitations

Inspected the required instructions, workflow records, dispositions, relevant documentation, source, tests, validation entry point and revision diff.

Checks passed:

- Task queue validation: 16 tasks, all with explicit models.
- Three documentation consistency tests.
- Shell syntax checks: 13 files.
- Python AST parsing of library and test modules.
- `git diff --check`.
- An in-memory probe confirming that a committed-DONE queue produces no newly-DONE IDs, no next task, and successful queue completion.

The full `./scripts/ai-check` and integration fixtures were not run because they require writes. Proposed behavior remains unimplemented. No files were modified or network/MCP integrations invoked.