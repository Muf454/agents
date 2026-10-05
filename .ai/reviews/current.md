<!-- Host evidence: HEAD 28049e444739e2b9e480813c5d6530fa552b110b; merge-base 662507102d51112163819c8a0bbc06706347c49a; saved 2026-10-05T11:15:05Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED — two significant requirement gaps and two minor issues remain.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=2

Reviewed HEAD: `28049e444739e2b9e480813c5d6530fa552b110b`
Comparison base / merge-base: `662507102d51112163819c8a0bbc06706347c49a`

Inspected repository instructions, specification, plan, tasks, state, handoff, review template, relevant documentation, vault flow chart, Git history and supplied diff, affected source, and relevant tests. The checkout was clean. All findings below concern this change; no separate pre-existing defect is counted.

Validation observed/run:

- Stored validation reports PASS at `2026-10-05T11:09:35Z`; its log records **149 tests passed**.
- `python3 -B scripts/lib/workflow.py stamp verify` passed. The stamp remains current despite subsequent workflow-record commits.
- Read-only documentation tests passed: **3 tests**.
- Bash syntax checks passed for **12 files**; Python AST checks passed for **3 files**.
- `git diff --check` passed.
- Ran read-only parser and PR-body reproductions, plus an in-memory upgrade failure reproduction.

Limitations: The full gate and integration suite were not rerun because they write temporary repositories, logs, locks, and evidence. No project files were written, and no network/MCP integrations were invoked. Live provider, GitHub, watchdog/systemd, and filesystem upgrade behavior were not exercised. The external flow chart contains R1/R2/R3 and `updated: 2026-10-05`; its same-session update history is not established by the repository diff.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — Extra re-check answers do not fail closed

**Location:** `scripts/lib/workflow.py:974`; `tests/test_workflow.py:2028`.

**Requirement:** T006 requires missing, duplicate, extra, or malformed answers to count as upheld.

**Problem and impact:** Unknown finding IDs are logged and ignored. Valid-looking withdrawals for all requested findings remain accepted, so a response violating the required answer set can avoid dispute recording and allow a normal PR.

**Evidence:** Calling `parse_recheck` for requested IDs `M1` and `M2`, with both marked withdrawn plus an extra `M9` answer, returned both requested findings as **withdrawn**. Its only parsing note said that `M9` was ignored.

The existing “extra” test supplies `M2` as **upheld** before adding `M9`. Consequently, it passes without demonstrating that the extra answer changes the result.

**Recommended direction:** Validate the complete answer set before accepting withdrawals. Unknown or unassignable extra entries should conservatively uphold the requested findings. Test an otherwise valid, entirely withdrawn response containing an extra ID or malformed extra entry.

### M2 — Upgrade write failures can leave an incompatible runtime

**Location:** `scripts/lib/workflow.py:208`.

**Requirement:** T008 requires upgrading the runtime as one compatible group, “all or nothing,” because scripts depend on their shared helpers.

**Problem and impact:** Apply replaces destination files sequentially, without rollback. An error writing a later file leaves earlier replacements installed and the version stamp unchanged. This can leave new scripts calling commands absent from the old helper.

**Evidence:** An in-memory reproduction used the actual source and installed-file contents, with `install_bytes` raising `OSError` on its second replacement. After failure, `.ai/bin/ai-run` contained the new version, `.ai/bin/lib/workflow.py` retained the old version, and the stamp had not been written. No disk files were changed during this reproduction.

The implementation preflights local edits, but that does not provide all-or-nothing behavior when replacement itself fails.

**Recommended direction:** Stage the complete compatible group before activation and provide rollback or recoverable transactional activation. Add an injected later-write failure test asserting that the installed runtime and stamp remain consistent.

## MINOR findings

### N1 — The source `ai-task` command is not executable

**Location:** `scripts/ai-task:1` — Git mode `100644`.

**Problem and impact:** The new source command cannot be invoked directly like the other toolkit scripts. Setup installs an executable copy, so installed projects are unaffected, but the source command remains unfinished.

**Evidence:** `git ls-tree HEAD scripts/ai-task` reports `100644`; `os.access(..., os.X_OK)` returned false. The handoff explicitly leaves changing this mode as a human todo.

**Recommended direction:** Commit the executable bit and verify direct invocation.

### N2 — The generated PR body omits the required flow-chart declaration

**Location:** `.ai/handoff.md:52`; `scripts/lib/workflow.py:1483`.

**Requirement:** AGENTS.md and T009 require this change’s PR description to contain “Flow chart updated.”

**Problem and impact:** The declaration appears in the handoff’s implementation summary, but `pr_body` copies only its manual-testing section. The generated description therefore omits the required declaration.

**Evidence:** Read-only generation with `pr_body(['0', '0'])` produced neither “Flow chart updated” nor “Flow unchanged,” although the handoff contains the former.

**Recommended direction:** Put the declaration in content carried into this PR description, or add an explicit summary field consumed by the generator. Check the generated body.

## Missing test coverage

- Extra re-check answers accompanying otherwise valid withdrawals.
- Failure during a later runtime replacement, including consistency of the version stamp.
- Executability of the source `ai-task` command.
- The required flow-chart declaration in the generated PR body.

## Security concerns

M1 weakens the conservative dispute gate. No exploitable security flaw was demonstrated in the inspected changes. Host-side digest verification, triage scope checks, and secret-name guards were inspected; these do not establish complete isolation.

## Architecture concerns

M2 violates the compatibility guarantee motivating grouped upgrades. Otherwise, the inspected implementation extends the existing shell/Python structure without adding dependencies.

## Manual testing recommendations

After fixes, use an isolated writable checkout to exercise interrupted triage recovery, upheld disputes surviving a later clean review and restart, publish-hook failures, and upgrade preview/apply with a deliberately unwritable later destination. Verify the final PR body and draft status.

This review does not constitute human acceptance.