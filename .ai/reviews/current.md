<!-- Host evidence: HEAD b651970c55b64ff3fccec2e4a9cd702d576da372; merge-base 1423b6092c4fe6a14d98d5c39f6380d69039141a; saved 2026-10-19T01:23:19Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED — executable-bit repair has two correctness gaps; operational records and the workflow chart also need correction.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=2

Reviewed HEAD: `b651970c55b64ff3fccec2e4a9cd702d576da372`

Supplied base and verified merge-base: `1423b6092c4fe6a14d98d5c39f6380d69039141a`

## Scope and validation

Inspected repository instructions, specification, plan, tasks, state, handoff, existing reviews/dispositions, relevant documentation, Git history, the supplied diff, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json`: PASS at `2026-10-19T01:19:39Z`, recording the reviewed HEAD.
- Referenced log: **1,002 tests passed in 634.1 seconds**, with 1,002 collected.
- Independently verified that the validation fingerprint matches current content.

Checks independently run:

- Task queue validation and test discovery.
- Three documentation-consistency tests: passed.
- Python AST parsing of three changed files and shell syntax checks across 14 files.
- `git diff --check`: passed.
- AST comparison: 37 test methods added; none removed.
- Read-only reproductions of the symlink traversal and session-exit behavior below.

The full `./scripts/ai-check` and integration fixtures were not rerun because they require writes. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M2 — Executable-bit repair follows symlinked parent directories outside the checkout

**Location:** `scripts/lib/workflow.py:4473–4478`.

**Requirement:** R3 limits repair to tracked regular files and says symlinks must never be touched. The runner prompt also restricts chmod to paths inside the checkout.

`os.lstat(path)` rejects a symlink only at the final component. Parent-directory symlinks are followed by both `lstat` and `chmod`.

For example, if the index still records executable `scripts/tool.sh`, but the working-tree `scripts` directory is replaced with a symlink to an external directory containing non-executable `tool.sh`, the host changes that external file’s permissions.

**Evidence:** Executed the actual `exec_bits()` with mocked index/root inputs and intercepted `os.chmod`. Using the real parent symlink `/proc/self/root`, the function reported restoring `root/etc/passwd` and requested chmod to `0755` on a path resolving to `/etc/passwd`. The chmod was mocked; nothing was changed.

**Impact:** A checkout-controlled path can cause the host to modify permissions outside the project.

**Recommended direction:** Traverse from a pinned checkout directory without following symlink components, verify the opened leaf is regular, and change permissions through its file descriptor. Add an external-directory symlink regression.

### M3 — Timed-out sessions exit before executable-bit repair runs

**Location:** `scripts/ai-run:838–842`; terminating path at `scripts/ai-run:360`.

**Requirement:** R3 requires restoration after each implementation session. R2 introduces deterministic recovery for timed-out IN_PROGRESS tasks.

Repair runs only after `claude_session` returns successfully. Exit codes 124 and 137 instead call `ai_die` inside that function, even after gate verification succeeds.

**Evidence:** Executed the actual post-session shell fragment and repair call with external behavior stubbed. Exit 0 reached `exec-bits`; exits 124, 137 and 1 did not. Existing repair integration coverage exercises only successful completion.

**Impact:** A timed-out task that loses a tracked script’s executable bit reaches recovery unrepaired. Recovery spends its one rerun allowance, then can fail validation solely because that script remains non-executable, preventing the intended automatic continuation.

**Recommended direction:** Run implementation-session repair after successful gate and branch verification, before terminal session-result handling. Add a timeout regression with a tracked executable whose mode is lost and a gate that requires it.

## MINOR findings

### N3 — State and handoff still describe the resolved validation block

**Location:** `.ai/handoff.md:130–132`; `.ai/state.md:7–12`.

**Requirement:** T033 requires the handoff to match delivered work; workflow documentation defines state as the queue summary and handoff as the next operator’s guide.

The queue marks all 33 tasks DONE, and current validation passes. State still reports 32 completed tasks, one remaining, failed validation and a blocked run. Handoff says T033 remains BLOCKED and directs the operator to rerun the gate.

**Impact:** The next operator receives contradictory completion status and obsolete recovery instructions.

**Recommended direction:** Synchronize state and handoff with the completed queue and current evidence, while retaining human acceptance as outstanding.

### N4 — The required workflow chart omits executable-bit repair

**Location:** `~/zWiki/zWiki/20 Projects/agents/agents-flow.md:158–169`; corresponding new step at `scripts/ai-run:841–844`.

**Requirement:** AGENTS.md requires every workflow step change to appear in the vault flow chart.

The chart includes the new gate allowance and timeout-recovery path, but its task flow proceeds directly from the session to host checks without the new permission-restoration step. No executable-bit repair appears elsewhere in the note.

**Impact:** The workflow’s designated overview omits a new host mutation.

**Recommended direction:** Add restoration to the task flow before validation and maintain the note’s `updated:` date in the correction session.

## Missing test coverage

Add regressions for:

- A tracked executable beneath a parent symlink targeting an external directory.
- Executable restoration after session timeout, including successful recovery afterward.

Existing leaf-symlink and successful-session tests do not cover these cases.

Performance improvement remains unproven: T031 records no before measurement, and T032 converted no pipeline setup runs.

## Security concerns

M2 is a demonstrated containment defect. No additional authentication or authorization defect was found in the inspected changes.

The previously recorded cap-exhaustion notification omission remains unchanged from the supplied base and is not counted as an introduced finding.

## Architecture concerns

Dependencies remain minimal, and timeout-rerun authority stays in host state. Factoring `commit_validated` preserves the existing validation safeguards.

Executable repair needs stronger filesystem boundaries and placement covering recoverable failures. **Flow chart updated** for gate allowance and timeout recovery; its repair-step omission is N4.

## Manual testing recommendations

### Needs you

After fixes and the normal toolkit upgrade, exercise a real timed-out implementation session and verify its notification, validated checkpoint and resumed task.

### Covered by automated tests

Recorded passing coverage includes gate allowance, timeout budgets, manifest persistence, disposition restart handling, progress reporting and fixture independence. Add the two repair regressions above, then rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.