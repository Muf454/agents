<!-- Plan review of plan digest 018fcc2d622a84c355c69b1753ba44d3eec34f9112712ee85227785c9b8371e2; HEAD 4afd9ab637786a1be32dcf946f8b1f6ac0ffd18d; saved 2026-10-21T21:45:23Z. -->

# Plan review

Reviewed HEAD: `4afd9ab637786a1be32dcf946f8b1f6ac0ffd18d`

Overall verdict: Revise before implementation.
Finding counts: BLOCKER=0 MAJOR=4 MINOR=0

## BLOCKER findings

None.

## MAJOR findings

- P16: A stop request cannot produce `human_stop` for a stand-alone runner.

  **Location:** `.ai/tasks.md:5432` (T316), `.ai/tasks.md:5239` (T315), `.ai/tasks.md:5906` (T319).

  T316 makes stand-alone `ai-run` record every nonzero exit as `stopped`. Therefore, `ai-pipeline --stop` targeting that runner writes a stop request, sends TERM, and receives an already-ended `stopped` record. T315 forbids changing ended records, and `settle-stop` explicitly refuses them. T319 consequently cannot complete the promised human-stop records. The planned stop tests cover pipelines, recoveries and fixture processes, but not a real stand-alone runner.

  **Concrete plan change:** Make the owning runner honor a pending stop request before choosing its terminal outcome, with the decision checked under the host lock. Preserve ended-record immutability. Add an integration test stopping stand-alone `ai-run` during a sleeping fake session: require exit 0 from `--stop`, the session gone, outcome and escalation `human_stop`, and an idempotent second stop.

- P17: Detached execution changes the meaning of relative knowledge-directory arguments.

  **Location:** `.ai/tasks.md:6328` (T313); `scripts/ai-pipeline:52`; `scripts/lib/common.sh:126`.

  T313 dispatches before normal option parsing and calls `ai_root` before launching the child from the checkout root. Existing foreground parsing resolves `--knowledge-dir` against the caller’s working directory. Consequently, launching from `/repo/subdir` with `--knowledge-dir ./notes` would instead select `/repo/notes`, or fail although `/repo/subdir/notes` exists. The existing `ai-plan` wrapper already handles this explicitly at `scripts/ai-plan:23`.

  **Concrete plan change:** Resolve `--knowledge-dir` against the original working directory before `ai_root`, preserve argument order, and forward the absolute path. Add detached-launch tests from a subdirectory with different same-named directories at both levels, plus a case where only the caller-relative directory exists. Assert the child argv and recorded arguments.

- P18: A stand-alone run can receive resume commands from an unrelated earlier pipeline.

  **Location:** `.ai/tasks.md:5313` (T305), `.ai/tasks.md:5432` (T316); `scripts/lib/workflow.py:1678`.

  Escalation answers always use the checkout’s existing `run.json` manifest when one exists. A stand-alone `ai-run` creates a new run record but does not replace that pipeline manifest. After an earlier pipeline invocation, a failed stand-alone run would therefore advertise `.ai/bin/ai-pipeline` with the earlier invocation’s base, limits and publication options. Those are not the current run’s arguments; following the advertised “resume” action can invoke a different workflow.

  **Concrete plan change:** Require resume answers to belong to the current run. For `kind=ai-run`, either construct an appropriate stand-alone command from its run record or omit the pipeline resume answer. Add a regression that leaves an earlier pipeline manifest, starts stand-alone `ai-run` with different arguments, and verifies its escalation never offers the earlier pipeline command.

- P19: Fix-round escalation wiring misses two existing finish paths.

  **Location:** `.ai/tasks.md:6064` (T321); `scripts/ai-pipeline:655` and `scripts/ai-pipeline:661`.

  T321 describes “both finish paths” and adds escalation writes to the explicit `--no-pr` and completed-PR branches. The source also finishes early when no `origin` exists and when `gh` is unavailable after pushing. Both branches can follow a fix-round-limit break, but they bypass the proposed writes. The run would end `finished` without the `fix_round_limit` record required for mission control to identify the remaining human decision.

  **Concrete plan change:** Centralize conditional fix-limit escalation in finalization so every successful finish path writes it exactly once. Extend acceptance tests to cover `--no-pr`, normal PR completion, no remote, and missing `gh`, retaining outcome `finished` and the significant finding IDs.

## MINOR findings

None.

## Validation and scope

Observed checks passed:

- `python3 -B scripts/lib/workflow.py tasks check`.
- Shell syntax checks for 15 script/template/validation files.
- Python AST parsing for `scripts/lib/*.py` and `tests/test_workflow.py`.
- Three existing `DocsConsistencyTest` tests, extracted and executed without importing fixture initialization.

Inspected the relevant source, record handling, tests, validation entry points, documentation, and earlier review dispositions. Earlier findings covered by the revised tasks are not repeated here. Explicit task models fit the described risks.

The full gate and integration tests were not run because they write stamps, logs and fixtures, which this read-only review forbids. No files were modified, and no network or MCP integrations were invoked. Real Ctrl-C, watchdog and systemd acceptance remains human validation after implementation.