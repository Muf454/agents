<!-- Plan review of plan digest 20f0c1e5d470a3ff12616e40e2cd19662cd512c3242920c959fbdde4c0dcde66; HEAD 87943881a1a6b0e8c71f8c46c7eb4abf692ef6e8; saved 2026-10-17T02:10:42Z. -->

# Plan review — round 5

Overall verdict: REVISE BEFORE IMPLEMENTATION
Finding counts: BLOCKER=0 MAJOR=1 MINOR=0

Reviewed HEAD: `87943881a1a6b0e8c71f8c46c7eb4abf692ef6e8`

The revised plan addresses P12–P14. One interaction between retained markers, successful retries and outcome reporting remains uncovered.

## BLOCKER findings

None.

## MAJOR findings

- P15: Delayed reconciliation of an older attempt can overwrite a successful retry’s reported result.

  **Location:** `.ai/tasks.md:449`, `.ai/tasks.md:463`, `.ai/tasks.md:524`; `scripts/lib/workflow.py:3093`.

  Reconciliation keeps unreadable markers and allows implementation to continue. Consider attempt A of T001, whose runner dies. A’s marker remains unreadable during startup and attempt-open reconciliation. A later attempt B of T001 succeeds and logs `done`. When A becomes readable, reconciliation appends its `crashed` record after B’s outcome.

  The existing report chooses the last appended record per task, so it now reports T001 as not done. Distinct, correctly preserved attempt IDs do not prevent this. Numbering attempts from existing outcome rows also assigns the older A a higher number than B.

  **Evidence:** An in-memory invocation of the actual `outcomes_report` function with B’s `done` followed by A’s delayed `crashed` produces `done=0, not done=1` in the task summary. T003’s planned two-attempt regression uses T001 followed by T002, so it misses this same-task interaction.

  **Concrete plan change:** Define logical attempt ordering independently of append order for normal and reconciled outcomes, including a tie-breaker and compatibility with existing rows. Use that ordering when selecting a task’s final result and calculating attempt statistics. Preserve best-effort reconciliation. Add a regression where A’s marker remains unreadable through B’s successful completion, then becomes readable: reconciliation records A exactly once, both attempts remain counted, and T001 remains reported as done after repeated reconciliation.

## MINOR findings

None.

## Validation and scope

Inspected repository instructions, spec, plan, all ten tasks, prior dispositions, state, handoff, relevant source, templates, tests, documentation and `.ai/validate`.

Observed passing checks:

- `python3 -B scripts/lib/workflow.py tasks check`
- Three `DocsConsistencyTest` tests
- Python syntax parsing for four relevant files
- Shell syntax checks for five relevant files

The report-ordering reproduction ran entirely in memory. The full gate and integration tests were not run because they require writable fixtures and artifacts. These checks validate the current baseline; implementation is still absent.

The remaining finding concerns telemetry integrity and missing regression coverage. No additional authorization issue was identified in the inspected scope. After implementation, manually confirm that a recovered older attempt cannot change a successfully retried task’s reported status.

No files were modified. No network or MCP integrations were invoked.