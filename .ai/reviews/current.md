<!-- Host evidence: HEAD 993bd33ef53c13a7ff28cf1a2454bc5e89328e96; merge-base 9e11a113f02525b2f1e10db3eb73eb571495507b; saved 2026-10-07T08:10:57Z. -->

# Independent review

Overall verdict: PROCEED WITH MINOR FIXES — the requested behavior is substantially delivered; two localized issues remain.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

Reviewed HEAD: `993bd33ef53c13a7ff28cf1a2454bc5e89328e96`
Supplied base / verified merge-base: `9e11a113f02525b2f1e10db3eb73eb571495507b`

Inspected repository instructions, specification, plan, tasks, state, handoff, prior reviews/dispositions, relevant documentation, scoped Git history/diff, affected source/tests, validation evidence, and the vault flow chart. The checkout was clean.

Validation observed/run:

- Stored evidence reports **PASS**, exit 0, at `2026-10-07T08:05:47Z`, recorded with HEAD `6e8668ffc2f86aeed449576edfdc3ce2f8e0acad`. Its log records **229 tests passed** in 596.552 seconds. Validation-stamp verification confirms that its fingerprint matches the current checkout.
- Task-queue validation, queue-completion verification, and committed-content comparison passed.
- **Three documentation tests**, **12 Bash syntax checks**, and **three Python compilation checks** passed.
- Read-only checks exercised the actual dependency-output validation, submodule snapshot, PR rendering, mixed-handoff notification counting, and timer-status functions with mocked I/O where needed.
- `git diff --check` reported one trailing-whitespace occurrence in the existing review artifact. Excluding that artifact, it passed.

Limitations: The full `./scripts/ai-check` gate and writable integration fixtures were not rerun because they create repositories, locks, logs, and validation artifacts. Live providers, package installation, systemd, and GitHub were not exercised. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

The previous M1 submodule-preservation defect and N2 output-directory defect are addressed by the implementation and regression tests. N1’s ordinary wrapped-line and unmatched-backtick cases are fixed; the paragraph-break case below remains.

## MINOR findings

### N1 — Test names after paragraph breaks still receive false coverage warnings

**Location:** `scripts/lib/workflow.py:1842`.

**Requirement:** FL-09 flags automated bullets without a backticked test name.

**Problem:** `flag_unnamed` ends the current list item at every blank line. Markdown permits a list item to contain additional indented paragraphs, so a test name in such a paragraph is excluded from the check.

**Evidence:** Running the actual PR renderer with this automated item:

```markdown
- Scenario.

  Covered by `test_scenario`.
```

produced:

```markdown
- Scenario. ⚠ no test named

  Covered by `test_scenario`.
```

**Impact:** Correctly named automated checks receive misleading warnings. The automated-check count remains correct.

**Recommended direction:** Preserve blank lines and subsequent indented paragraphs within the list item. Add a regression covering a test name after a paragraph break.

### N3 — The workflow guide contradicts setup’s watchdog behavior

**Location:** `docs/workflow.md:507`; implementation: `scripts/lib/workflow.py:376`.

**Requirement:** FL-07 introduces opt-in timer installation through `setup-project --watchdog`; T007 requires documentation to describe implemented behavior accurately.

**Problem:** The watchdog section still states, “Nothing is installed by `setup-project`.” Setup now installs the timer when `--watchdog` is supplied. This guide also omits the new timer-status and pipeline-warning behavior.

**Impact:** Readers following the operating guide receive incorrect setup guidance and incomplete information about checkout monitoring.

**Evidence:** The source invokes the installed watchdog with `--install-timer --diagnose --recover`. README documents the new behavior, while the workflow guide retains the contradictory statement.

**Recommended direction:** Qualify the statement for setup without `--watchdog`, and document timer status and STARTED/RESUMED warnings. Extend documentation checks to cover these contracts.

Both findings concern behavior or documentation affected by this change. No separate pre-existing defect was demonstrated.

## Missing test coverage

- A named automated list item containing a blank line before its indented test-name paragraph.
- Documentation assertions covering opt-in timer installation, timer status, and pipeline warnings.

Existing added tests cover dependency freshness, installer failure/timeout and preservation, recovery installation, timer states, legacy handoffs, wrapped names, and mixed human/automated notification counting.

## Security concerns

No additional security defect was demonstrated in the inspected paths. Host execution of package-manager code and the agent-writable dependency stamp remain documented, accepted design choices; the checks provide boundary verification rather than OS isolation.

## Architecture concerns

The implementation reuses existing helpers and adds no external dependencies. The frozen `.ai/bin` remains unchanged intentionally; installed projects need a deliberate upgrade.

Flow chart updated: the vault note contains the dependency step, recovery rule, testing split, and watchdog warnings, with `updated: 2026-10-06`. Same-task edit timing cannot be established from repository history.

## Manual testing recommendations

### Needs you

Verify an opted-in timer and STARTED/RESUMED phone notifications on real systemd. Inspect the resulting PR’s testing instructions.

### Covered by automated tests

Add the paragraph-break regression and watchdog documentation assertions, then run the full gate in a writable checkout.

This review does not constitute human acceptance.