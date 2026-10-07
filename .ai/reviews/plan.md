<!-- Plan review of plan digest 5b0bd7758d9d088b8a835aaca8b39e2e10a7dd143e59029918b497ebbffe7ba5; saved 2026-10-07T18:59:58Z. -->

# Plan review

Overall verdict: CHANGES REQUIRED — close the remaining Git permission gap before implementation.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

Reviewed HEAD: `fbea454456fe78c1fec67f71e2aa49468dcc68e3`.

Inspected repository instructions, spec, plan, tasks, state, handoff, affected source/tests, documentation, validation, reference patches, Git history, and the vault flow chart. The checkout is clean.

## BLOCKER findings

None.

## MAJOR findings

- P5: Git option abbreviations can bypass the proposed reviewer deny list.

  **Location:** `.ai/tasks.md:15`, `.ai/tasks.md:21`; `scripts/lib/workflow.py:678`.

  T001 retains `Bash(git grep *)` and specifies denial of `--open-files-in-pager` and `-O`. Git also accepts `--open-files` as an abbreviation. Neither reference patch’s deny list matches that spelling, leaving a route to execute a caller-selected pager despite removing all test runners.

  **Evidence:** Git 2.55.0 accepted this read-only probe, returning exit 1 for no matches rather than an unknown-option error:

  ```text
  git grep --open-files=/__plan_review_never_execute__ --fixed-strings -- '__plan_review_nonexistent_71510d55e52e4a8f94ad9679cdbce86c__'
  ```

  No pager was invoked. An in-memory comparison confirmed that the command matches `git grep *` and neither prototype’s deny patterns. With matching files, the abbreviated option launches the supplied program, violating R1.

  **Concrete plan change:** Remove reviewer Bash permission for `git grep` and use native `Grep`, or explicitly cover every accepted abbreviation and clustered short-option form. Add command-policy tests for these forms alongside safe commands, and include them in mission control’s live permission checks. Assertions that canonical deny strings exist are insufficient.

## MINOR findings

- P4: The revised targeted command still misses the primary reviewer-invocation test.

  **Location:** `.ai/tasks.md:26`; `tests/test_workflow.py:2270`.

  Read-only discovery with the specified filters selects eight existing tests but excludes `test_review_falls_back_to_claude_at_the_codex_limit`. That test contains the invocation assertions the reference patch extends to check `--disallowedTools`. The full gate would cover it, but the targeted command does not satisfy the previous finding’s requested coverage.

  **Concrete plan change:** Add `-k review_falls_back` to the targeted command, or name the invocation test explicitly. Retain the full repository gate.

- P6: README will describe permissions that T001 removes.

  **Location:** `.ai/tasks.md:15`, `.ai/tasks.md:18`; `README.md:360`.

  T001 updates the workflow documentation, reviewer prompt, and flow chart, but omits README. README explicitly promises inherited `npm test` and `npx vitest run *` permissions and describes probes running project code. Those statements contradict the revised policy of inheriting no runners.

  **Concrete plan change:** Include README’s Claude fallback reviewer section in T001. Describe reading host validation evidence, the remaining command permissions, and the saved allow/deny lists consistently across the documentation and prompt.

## Validation observed

- Four affected Python files passed AST parsing.
- Five relevant shell files passed `bash -n`.
- Read-only discovery collected 272 tests.
- Targeted discovery demonstrated P4.
- Git parsing and in-memory policy checks demonstrated P5.
- `git diff --check` passed.
- No files were modified.

The full gate and integration tests were not run because they create fixtures and validation artifacts. No network/MCP integration or live provider session was invoked. `.ai/state.md` records no current validation result.

## Scope and remaining verification

The revision addresses the earlier unsafe runner inheritance, triage-attempt tracking, and same-session flow-chart concerns. T002 specifies regression cases for malformed queues, exhausted budgets, usage-limit retries, timeout, interruption, and duplicate outcomes. No additional model-selection finding was established.

After implementation, mission control should verify the generated policy with the installed Claude CLI in a disposable repository, checking dangerous forms, harmless commands, and absence of outside writes. Mock invocation and glob tests do not establish live permission enforcement.

This review is not human acceptance.