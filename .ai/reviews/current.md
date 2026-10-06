<!-- Host evidence: HEAD 51e020e5ca6ee9d6c45c0632186cc2ed5e909dfb; merge-base 7b0c4334bac93fb673777e01029770aa8b278db0; saved 2026-10-06T07:45:27Z. -->

# Independent review

Overall verdict: NO CHANGES REQUIRED in the inspected scope; ready for human testing.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=0

Reviewed HEAD: `51e020e5ca6ee9d6c45c0632186cc2ed5e909dfb`  
Supplied base / merge-base: `7b0c4334bac93fb673777e01029770aa8b278db0`

Inspected repository instructions, specification, plan, all six tasks, state, handoff, review template, relevant documentation, scoped Git history/diff, affected source/tests, deterministic validation evidence, and the vault flow chart. The checkout remained clean.

The inspected implementation satisfies the OR-01/OR-02 requirements:

- Every accepted DONE checkpoint and the final runner handoff require a clean tree, current validation stamp, and committed-content verification before completion notifications.
- The pipeline checks committed content before each implementation review and before and after every push attempt, including the third failure. Integrity diagnostics preserve the helper’s file-specific detail and trigger human escalation.
- Host-state consumers enforce checkout separation. Runner and pipeline startup also check the resolved knowledge directory before launching agents.
- Recovery checks the state root before reading the manifest. Watchdog installation checks the supplied target project before mutation; runtime recovery checks precede gate/manifest access.
- Regression tests exercise filters, executable-mode mismatches, final-handoff mismatches, push outcomes, symlinks/submodules, unsafe roots, and refusal behavior.

The earlier toolkit upgrade in the supplied range was also checked: all 21 stamped toolkit files match their recorded hashes and the supplied-base source/templates. The CI and license changes were inspected. No separate pre-existing defect was demonstrated.

Validation observed/run:

- Stored evidence reports **PASS**, exit 0, at `2026-10-06T07:41:59Z`, recorded at `66a1753c51ea1302920c058d2c8aeda032ed9844`; its log records **188 tests passed**.
- Current validation-stamp verification, committed-content comparison, task-queue validation, and `git diff --check` passed.
- **Three documentation tests**, **13 Bash syntax checks**, and **three Python syntax checks** passed.
- In-memory checks exercised direct, containing, relative, disjoint, knowledge-directory, and symlink-prefix state paths.
- Guarded calls to the actual watchdog functions confirmed unsafe installation refuses before mutation and unsafe runtime state refuses before subprocess/gate/manifest access.

Limitations: The full `./scripts/ai-check` gate and writable integration fixtures were not rerun because they create repositories, locks, logs, and evidence. Live providers, GitHub, and systemd were not exercised. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

None found in the inspected scope.

## Missing test coverage

Dedicated regression coverage could strengthen runtime refusal when an installed watchdog copy is relocated through a symlink, and explicitly exercise the unset-state-variable HOME fallback. These coverage gaps do not establish defects.

## Security concerns

No additional security defect was demonstrated in the inspected paths. Authority-root checks enforce the specified configuration constraints; they do not provide OS isolation.

## Architecture concerns

The changes reuse existing helpers and add no external dependencies. The repository’s frozen `.ai/bin` intentionally remains at the stamped version; the new behavior is in `scripts/` and requires deliberate installation or upgrade.

Flow chart updated: the vault note contains the new checkpoint, review, push, startup, recovery, and watchdog checks with `updated: 2026-10-06`. Same-task edit timing cannot be independently established from repository history.

## Manual testing recommendations

In an isolated writable project:

- Run the full gate and the handoff’s filter, mode, final-handoff, and push-hook scenarios.
- Verify watchdog installation from outside Git and another checkout, including refusal without host-copy or unit-file creation.
- Verify unsafe recovery preserves the configuration error, launches no recovery Claude session, and consumes no attempt.

This review does not constitute human acceptance.