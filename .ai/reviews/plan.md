<!-- Plan review of plan digest 3b56b21771e979df8c7e819ae7762d0483f8e7f1f5a6399ae777cef6a0854a68; saved 2026-10-07T10:37:12Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION
Finding counts: BLOCKER=1 MAJOR=3 MINOR=3

Reviewed HEAD: `dff09092150705c89df22645404c326b9ed60b5e`

Inspected repository instructions, spec, plan, tasks, state/handoff, affected scripts and prompt templates, test fixtures, validation configuration, documentation, and local Git history. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

- P1: The specified shard command cannot import the discovered tests.

  **Location:** `.ai/tasks.md:26–33`; `tests/test_workflow.py:1`.

  Discovery produces IDs such as `test_workflow.DocsConsistencyTest.test_docs_consistency_modes_table`. It temporarily adds the discovery directory to the parent process’s import path. A fresh `python3 -m unittest <ids…>` subprocess running at the repository root does not inherit that Python import path. The proposed command therefore fails before executing the intended tests.

  **Evidence:** Read-only discovery collected **229 tests**. Running a discovered documentation-test ID from the repository root failed with `ModuleNotFoundError: No module named 'test_workflow'`. The same test passed with `PYTHONPATH=tests`.

  **Concrete plan change:** Explicitly provide the resolved discovery import root to every worker, including temporary directories supplied through `--start-dir`. Add regressions that launch the runner from both the repository root and an unrelated directory, with no caller-provided `PYTHONPATH`.

## MAJOR findings

- P2: Required runner validation is unavailable under the frozen command allowlist.

  **Location:** `.ai/tasks.md:11–14`, `.ai/tasks.md:48–54`; `.ai/permissions.allow:23–27`; `scripts/ai-run:146–149`.

  T001 requires three full `python3 tests/run_parallel.py` runs, and the queue recommends that command after session gate timeouts. The installed allowlist permits `python3 -m unittest …`, but does not permit the runner command. Sessions use `dontAsk`, so they cannot obtain approval interactively. The host’s post-task check remains serial and does not provide the required parallel-run evidence.

  **Concrete plan change:** Add a human preparation step approving the exact runner command before unattended execution, while keeping permission changes outside pipeline sessions. Alternatively, assign the three full runs to the coordinating host and explicitly require its recorded evidence before T001 acceptance.

- P3: Triage history boundaries and round counting do not match the actual pipeline.

  **Location:** `.ai/tasks.md:143–161`; `.ai/tasks.md:68–80`; `scripts/ai-pipeline:216`, `scripts/ai-pipeline:324–346`; `scripts/ai-run:176–205`.

  `--since` is the **triage stage’s starting commit**, not the pipeline comparison base. The pipeline records that start after committing the current review. Consequently, `review-history "$since"` sees no earlier reviews during normal triage. The proposed fallback involving the stage start also does not establish a branch comparison base.

  Conversely, querying the actual branch base through `HEAD` includes the already committed **current** review. Adding one to that count makes round 2 appear to be round 3. `triage-check --fresh` currently receives neither base nor round metadata and is called from several normal and recovery paths; the plan does not define how those calls obtain consistent values.

  **Concrete plan change:** Define one shared routine that uses the current report’s recorded merge-base and reviewed HEAD to select earlier rounds, excludes the current review, and returns an uncapped count separately from rendered history. Use it for the prompt and every convergence-check path. Preserve `--since` exclusively as the triage scope boundary.

  Add an end-to-end three-round pipeline regression using the real host commit order: round 2 must pass without `Convergence:`, round 3 must fail without it and pass with it. Also verify unchanged numbering after interrupted-triage recovery and history truncation.

- P4: T001’s explicit model does not fit its concurrency work.

  **Location:** `.ai/tasks.md:19`, `.ai/tasks.md:26–36`; `CLAUDE.md:60–65`.

  T001 assigns `sonnet` to concurrent worker orchestration, shard crash handling, and shared-state isolation. The requested review policy and repository model rules require `opus` for concurrency work.

  **Concrete plan change:** Set T001 to `Model: opus` and update the plan’s model summary. Mechanical documentation work can remain separate on a cheaper model.

## MINOR findings

- P5: The proposed convergence regex accepts an empty line.

  **Location:** `.ai/tasks.md:149–151`; `.ai/project-spec.md:56–58`.

  In Python, `\s*` includes newlines. The proposed `^Convergence:\s*\S` therefore accepts `Convergence:` with no explanation when the following nonblank line contains the disposition table.

  **Evidence:** An in-memory check matched `Convergence:\n\n| Finding …` as a valid convergence entry.

  **Concrete plan change:** Require nonblank content on the same line, using horizontal whitespace explicitly, such as `^Convergence:[ \t]*[^ \t\r\n]`. Add empty, whitespace-only, and following-table regressions.

- P6: T001 weakens the specified performance acceptance criterion.

  **Location:** `.ai/tasks.md:48–49`; `.ai/project-spec.md:67–69`.

  The spec requires a runtime under 200 seconds on this machine. T001 calls that threshold a “target,” allowing acceptance without meeting it.

  **Concrete plan change:** Make the threshold mandatory and define how it is assessed—for example, require each of the three consecutive default-worker runs to finish under 200 seconds, recording counts and wall times.

- P7: The authorization record incorrectly says the prerequisite merge is present.

  **Location:** `.ai/current-plan.md:47–49`; `.ai/project-spec.md:17–19`.

  Local `master` contains merge commit `0818f20`, but that commit is not an ancestor of the reviewed HEAD. The branch shares the merged source history through `55383d7`; it has not completed the explicitly required merge of `master`.

  **Concrete plan change:** Correct the record and retain the merge as an outstanding human preparation step before starting the unattended run. Reconfirm the resulting HEAD and comparison base afterward.

## Missing test coverage

The plan should add the worker import-path cases and real pipeline round-count/recovery cases described above. Tiny-suite runner coverage should also include an ordinary test exception and skipped-test output, verifying error counts and summary parsing.

## Security and architecture concerns

The human-controlled gate switch, frozen installed tooling, and separation of review from implementation are appropriate boundaries. P2 must be resolved without an unattended permission change. P3 must preserve the existing triage scope guard and host-owned fix-round accounting.

No additional security finding was demonstrated in the inspected scope.

## Validation observed

- Discovery collected **229 tests**, exceeding the plan’s historical 224-test baseline.
- **Three documentation consistency tests passed.**
- The worker import failure and proposed import-path correction were reproduced.
- The empty convergence-line regex defect was reproduced.
- Python syntax checks passed for three inspected files.
- Bash syntax checks passed for six affected or relevant scripts.
- Task-queue validation and `git diff --check` passed; the checkout remained clean.

The full `./scripts/ai-check` gate and integration suite were not rerun because they require writable fixtures, locks, logs, and validation artifacts. No current `.ai/local/validation.json` was available. Historical handoff evidence does not validate the proposed implementation.

## Manual testing recommendations

### Needs you

Complete and record the prerequisite merge and validation-command preparation. After implementation review, approve the `.ai/validate` switch and time a full gate run.

### Covered by automated tests

Worker loading, shard result handling, review prompt isolation, correct triage history and numbering, convergence-line validation, and interrupted-triage recovery should be verified before approval.

This review does not constitute implementation verification or human acceptance.