<!-- Plan review of plan digest a70e5936fe89668020348201ab089b45866676ff16f2db6abcfc14336cb4d043; HEAD 0848f4b0b325a83cf154073299c4b96d2373ab73; saved 2026-10-21T21:23:53Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=5 MINOR=0

Reviewed HEAD: `0848f4b0b325a83cf154073299c4b96d2373ab73`

Scope: batch 10, T201–T218, including the previous review and revised dispositions, affected source, tests, templates, documentation, and `.ai/validate`.

## BLOCKER findings

None.

## MAJOR findings

- P12: The compatibility fallback still instructs targeted sessions to run full gates.

  **Location:** `.ai/tasks.md:5382`; `.ai/project-spec.md`, A5.

  The fallback runs every Validation command except `.ai/bin/ai-check`. Valid existing queues can invoke the same gate through `bash .ai/validate`, `./scripts/ai-check`, or another entry point. The repository’s own fixture task uses `bash .ai/validate` (`tests/test_workflow.py:106`). Such a session would still run the full gate, now without its gate allowance, defeating TS-01 and preserving the timeout problem.

  **Concrete plan change:** Exclude full validation entry points from the compatibility fallback, including direct `.ai/validate` invocation. Specify behavior when an older task provides only a full-gate command. Add a regression using that existing fixture format, alongside a task-specific check.

- P13: Event locking can indefinitely block the workflow.

  **Location:** `.ai/tasks.md:5562`, `.ai/tasks.md:5567`.

  T206 specifies blocking exclusive and shared `flock` calls without a deadline. A writer stopped while holding the host-wide event lock would therefore stall other pipelines inside synchronous telemetry calls, including stop notifications and completion handling. The wrapper’s error handling cannot help because the helper never returns. Existing observation locking explicitly uses a deadline (`scripts/lib/workflow.py:5244`).

  **Concrete plan change:** Keep the stable lock, but acquire it with a bounded wait. Writers should skip recording with a Note when the deadline expires; readers should report unavailable telemetry without hanging. Add a separate-process lock-holder regression proving that pipeline completion and terminal stops remain bounded and retain their exit status.

- P14: The recovery hook omits failed recovery gates.

  **Location:** `.ai/tasks.md:5772`; `scripts/ai-recover:303`.

  The planned hook runs after the existing recovery `ai_gate_check`. However, `commit_validated()` currently executes `ai-check || escalate ...` before reaching that check. A failing or timed-out recovery gate exits through escalation without writing a gate event. This violates T207’s “every host-run full gate” requirement and undercounts gate failures in metrics and run totals. The proposed acceptance criteria do not explicitly exercise this path.

  **Concrete plan change:** Capture the recovery gate’s exit code and timing, verify gate integrity, emit its event when trusted, then preserve the existing escalation behavior. Test passing, failing, and timed-out recovery gates, plus a gate change that must emit nothing.

- P15: T204’s required prompt assertion contradicts both existing and planned templates.

  **Location:** `.ai/tasks.md:5404`, `.ai/tasks.md:5451`.

  T204 requires the captured targeted-mode prompt to contain no `run_in_background`. The prompt includes the runner template (`scripts/ai-run:929`), which already contains that text. T205 deliberately retains it as conditional full-mode guidance. The existing regression also requires that guidance in both templates (`tests/test_workflow.py:1995`). Consequently, the new assertion cannot pass under either template version, and T204 precedes T205.

  **Concrete plan change:** Assert the selected rule within the appended RUNNER CONTRACT, rather than banning text throughout the complete prompt. Retain separate assertions that template background instructions are conditional. Ensure T204’s tests pass before T205 is implemented and remain valid afterward.

- P16: Gate-log inspection lacks a complete safe-read contract and uses the wrong model for that risk.

  **Location:** `.ai/tasks.md:5748`, `.ai/tasks.md:5755`.

  T207 introduces host reads of the agent-writable validation stamp and its referenced log. It specifies `O_NOFOLLOW` for the log, but does not specify nonblocking opens, safe stamp reads, or protection against parent-directory substitution. `O_NOFOLLOW` alone does not prevent an open from blocking on a FIFO before the regular-file check. These telemetry reads run synchronously after validation and could hang the host.

  The repository already provides pinned-directory, bounded, nonblocking reads through `local_dir_fd()` and `read_record()` (`scripts/lib/workflow.py:5060`, `scripts/lib/workflow.py:5207`). T207’s symlink and gate-integrity handling crosses this security boundary, yet its explicit model is `sonnet`.

  **Concrete plan change:** Specify safe reads for both stamp and log, reusing the existing primitives where applicable. Require bounded reads, nonblocking opens, and descriptor-based regular-file checks. Add FIFO and symlinked-parent regressions that return promptly with unknown fields and leave the workflow unchanged. Assign this portion to `opus`, optionally splitting it from routine event wiring.

## Validation and limitations

- Inspected the affected shell/Python source, fixture machinery, existing regressions, templates, and validation entry point.
- Shell syntax checks passed for the inspected workflow scripts and `.ai/validate`.
- AST parsing passed for nine Python files under `scripts/lib` and `tests`.
- Static inspection found matches for all existing-regression selectors in the revised batch.
- Did not run `ai-check` or unittest suites: their fixtures require writes prohibited by this read-only review.
- Historical validation evidence was read but not independently reproduced.
- No files were modified; no network or MCP integrations were invoked.

## Manual testing recommendations

After implementation and upgrade, observe one targeted-mode run using an older queue without `Targeted:` labels. Confirm that only task-specific checks run in the session, the host gate decides DONE, and recorded gate failures and completion events agree with the raw logs.