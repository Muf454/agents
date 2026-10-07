<!-- Plan review of plan digest b550a05ce26b9da82269aed81db878e1d8f8984ed91f2e8245a129aac498bf0a; saved 2026-10-07T18:51:29Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED — tighten command screening and distinguish task sessions from triage before implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=2

Reviewed HEAD: `e52ed76de2049b2a25f8aaf3d3e0132b206f9f61`.

Inspected repository instructions, spec, plan, tasks, state, handoff, relevant documentation, affected scripts/tests, validation entry point, reference patches, and vault flow chart. The checkout is clean.

## BLOCKER findings

None.

## MAJOR findings

- P1: Exact runner entries need argument screening too.

  **Location:** `.ai/tasks.md:15`, `.ai/tasks.md:23`.

  The plan permits inheriting exact entries when a runner’s dangerous options cannot all be denied. Absence of a wildcard does not establish that the command is safe. The planned tests need to exercise unsafe exact entries supplied by the project, rather than only dangerous expansions of wildcard entries.

  An in-memory probe of the referenced `t001-wip.patch` policy confirmed that all these exact entries are inherited without matching any deny rule:

  ```text
  pytest --basetemp=/outside
  go test -exec /outside ./...
  npx tsc --outDir /outside
  bash -n +n -c "touch /outside"
  ```

  These permit deletion/writes or program execution, contrary to R1. No dangerous command was executed.

  **Concrete plan change:** Require argument screening for every inherited entry, including exact commands. When safety cannot be established, drop the entry. Seed the table-driven tests with unsafe exact permissions as well as wildcard permissions, and assert that none grants the dangerous command. Explicitly prohibit treating “no wildcard” as sufficient evidence of safety.

- P2: Opening attempts inside the shared session function can record triage as a failed task.

  **Location:** `.ai/tasks.md:39`; `scripts/ai-run:137`, `scripts/ai-run:209`, `scripts/ai-run:235`, `scripts/ai-run:296`.

  The proposed launch hook belongs inside `claude_session`, but that function serves both implementation and `--triage`. Triage sets `active_task=triage`, invokes the same function, and exits without calling `task_outcome`. Opening an attempt unconditionally there leaves it open even after successful triage; the proposed EXIT handler would consequently emit an erroneous task `error` outcome. Task timing/metadata initialization currently also belongs to the implementation path.

  **Concrete plan change:** Make task-attempt tracking explicitly opt-in for implementation sessions. Keep triage outside that lifecycle. Add regression assertions that successful and failed triage create no task outcomes, and that usage-limit retries within an implementation session still produce exactly one outcome and retain the original attempt start time.

## MINOR findings

- P3: T001 defers its required flow-chart update to another session.

  **Location:** `.ai/tasks.md:18`, `.ai/tasks.md:39`; `AGENTS.md:15`.

  T001 changes reviewer policy, while T002 owns both flow-chart updates. The runner executes one task per fresh session, so this contradicts the repository’s same-session update requirement and leaves the chart stale if execution stops after T001.

  **Concrete plan change:** Put the reviewer-policy chart update and `updated:` date in T001’s affected files and acceptance criteria. Let T002 update the stopped-attempt lifecycle separately. Retain “Flow chart updated” in the PR description.

- P4: T001’s targeted test selection misses relevant reviewer tests.

  **Location:** `.ai/tasks.md:26`; `tests/test_workflow.py:2477`.

  Filtering with `-k review_allowlist -k fallback` does not select existing tests named `test_claude_review_denials_and_allowlist_are_recorded` or `test_claude_review_failure_or_write_keeps_the_prior_review`. It also misses the reference patch’s new `test_review_policy_denies_every_writing_form_of_inherited_runners`.

  **Concrete plan change:** Specify an executable targeted command selecting the allowlist, policy-matrix, reviewer invocation, denial-recording, and failure-preservation tests. Also run the repository-required `./scripts/ai-check`.

## Validation observed

- Four affected Python files passed AST parsing.
- Five relevant shell files passed individual `bash -n` checks.
- Read-only discovery collected 272 tests.
- In-memory policy probes demonstrated the unsafe exact-entry behavior above.
- `git diff --check` passed; no files were modified.

The full gate and integration tests were not run because they create fixtures and validation artifacts. No current validation result is recorded in `.ai/state.md`. No network/MCP integration or live provider session was invoked.

## Scope and remaining verification

The timeout, malformed-queue, validation-failure, and pre-launch budget cases are substantially specified. T001’s `opus` model fits its security risk; T002’s routine outcome bookkeeping does not independently establish a model-selection violation.

After implementation, mission control should perform the planned disposable-repository permission checks using the generated policy, including unsafe exact entries, attached/clustered options, and alternate executable configuration paths. Matcher tests alone do not establish live enforcement. Deferred outcome-report findings remain outside this scope.

This review is not human acceptance.