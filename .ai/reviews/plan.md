<!-- Plan review of plan digest c59fd6b58d132fb72fe58e327c51cb3233f77f277782bd92e921d25fce0f0eec; saved 2026-10-08T05:22:44Z. -->

# Plan review — FL-04 bounded supervisor

Overall verdict: REQUEST CHANGES — T004 reintroduces a demonstrated command-permission bypass.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

Reviewed HEAD: `93ced44259fcb91f2ad629b37ad2e5a4803a0c0f`

Inspected repository instructions, specification, plan, tasks, state, handoff, prior reviews/dispositions, relevant source, tests, validation scripts, documentation, Git history, the vault flow chart, and the locally available prerequisite catch-up plan. No implementation changes exist in the reviewed branch.

## BLOCKER findings

None.

## MAJOR findings

- P1: The revision allowlist does not enforce the promised write boundary.

  **Location:** `.ai/tasks.md:115`; `.ai/current-plan.md:158`; `scripts/lib/workflow.py:678`; `scripts/lib/workflow.py:695`.

  T004 proposes read-only git commands and project Bash entries filtered like the existing `review-allowlist`. That filter permits wildcard git arguments, including `Bash(git diff *)` and `Bash(git grep *)`.

  These commands have writing and execution options. Git’s locally installed documentation confirms that `git diff --output=<file>` writes to a specified file and `git grep --open-files-in-pager=<program>` invokes a selected program. The prerequisite catch-up task explicitly identifies these argument bypasses and removes Bash from reviewers altogether.

  The proposed revision mode would restore those capabilities. Scoped `Edit` permissions cannot constrain writes performed through Bash, and checkout scope checks cannot detect changes to the external host-state directory. This undermines R1’s permitted-file boundary and the host authority protecting revision counts and human decisions. Existing weaknesses in the reviewer filter are pre-existing; introducing that policy into the new revision mode is the prospective defect.

  **Concrete plan change:** Give the revision session only `Read,Glob,Grep,Edit`, with Edit restricted to the R1 records. Prepare Git context and perform staging/checkpointing on the host; the existing no-commit revision scenario already supports host checkpointing. Remove inherited project Bash entries and session-side commit instructions. Add invocation assertions proving Bash is unavailable and include a live permission check in a disposable fixture. Do not resolve this by adding another keyword blacklist.

## MINOR findings

- P2: Unsuccessful format retries lack the required run-log entry.

  **Location:** `.ai/tasks.md:270`; `.ai/project-spec.md:52`.

  R5 requires every supervised step to append to the run log. T009 appends its retry entry only after a successful retried publication. If the second answer is malformed, or the second invocation fails an integrity check, the retry occurred and was notified but receives no tracked run-log entry.

  **Concrete plan change:** Record an issued format retry and its outcome on both success and handled failure, without dirtying the checkout between reviewer calls. Preserve the first report path in that entry. Add assertions for malformed-twice and integrity-failure-on-retry cases.

- P3: README updates are deferred beyond two flow-changing tasks.

  **Location:** `.ai/tasks.md:150`; `.ai/tasks.md:272`; `.ai/project-spec.md:57`.

  R6 requires README, workflow documentation, and the flow chart to be updated in the same task as each flow change. T005 and T009 specify workflow/flow-chart updates but omit README from both their instructions and affected modules. T010’s later reconciliation does not meet that timing requirement.

  **Concrete plan change:** Add the relevant README recovery and format-retry updates to T005 and T009, with acceptance criteria checking those descriptions against the implemented behavior.

## Requirements, ordering, and models

The earlier dirty-checkout and lost-human-decision findings are addressed explicitly by the revised host commit/record sequence and startup decision checks. The removed cumulative budget is an acknowledged scope decision, so the earlier budget findings are not carried forward.

All ten tasks have explicit model selections. No task’s own failed implementation attempt is recorded. The main authorization and recovery tasks use `opus`; no additional model-selection finding is raised.

The unmerged `fix/catchup-review` prerequisite remains a scope limitation. Preserve the requirement to rebuild and review against its merged implementation before T001 starts.

## Validation observed

- Confirmed the requested HEAD and clean checkout.
- Read-only `tasks check` and `tasks untouched` passed.
- Bash syntax checks passed for 13 files.
- Python AST parsing passed for four source/test files.
- Test discovery collected 272 existing tests; discovery is not a test pass.
- An in-memory probe confirmed the existing reviewer filter retains unrestricted git-diff arguments.
- No `.ai/local/validation.json` was present.

Not run: targeted integration tests, `./scripts/ai-check`, `.ai/bin/ai-check`, or the full suite, because they create fixtures, locks, logs, or validation artifacts. No files were modified and no network/MCP integrations were invoked.

## Testing recommendations

Implement the boundary and failure-audit regressions above, then run the targeted checks and full gate in a writable checkout. Retain the planned real supervised trial covering a human-decision stop, crash/recovery, and explicit clearance.

This review does not constitute human acceptance.