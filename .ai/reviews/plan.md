<!-- Plan review of plan digest aef218245ec9a5755c814fe403f34621ee648a83e268566a16d989c24d9f7ed1; saved 2026-10-08T20:20:22Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=1

Reviewed HEAD: `4cc7d2e12e7cef3b294213ca9cb67f98e86563a5`.

## BLOCKER findings

None.

## MAJOR findings

- P1: Recovery suffix scanning can accept malformed or ambiguous decisions.

  **Location:** `.ai/tasks.md:170–171`; `.ai/project-spec.md:48–53`.

  T005 treats duplicate-key parsing failures as “no object here,” including during the prefix ambiguity check. Consequently, this answer accepts `commit_and_rerun`:

  ```text
  Diagnosis.
  {"action":"escalate","action":"rerun","reason":"first"}
  {"action":"commit_and_rerun","reason":"second"}
  ```

  The proposed scanner also accepts an object inside an unterminated array:

  ```text
  Diagnosis. [{"action":"commit_and_rerun","reason":"x"}
  ```

  An in-memory reproduction of the specified algorithm confirmed both outcomes. These violate R5’s duplicate-key, ambiguity and non-object rejection requirements. The returned action drives automatic recovery, including checkpointing leftovers.

  **Concrete plan change:** distinguish malformed decision objects from ordinary non-JSON prose; retain duplicate-key information during prefix inspection and reject earlier action-bearing objects even when their keys repeat. Require the final decision to be a standalone object rather than a suffix extracted from a malformed container. Add these exact rejection cases.

- P2: The early base stop’s merge-and-rerun advice can strand interrupted triage.

  **Location:** `.ai/tasks.md:97,103,114`; `scripts/lib/workflow.py:1162–1171,1174–1189`.

  T003 places the base stop before completing an open triage stage. If origin advances during an interrupted triage, the pipeline therefore tells the human to merge first while leaving that stage open. A merge that changes source then causes `stage_verify` → `triage_scope` to reject changes outside `TRIAGE_RECORDS`. The promised rerun does not complete; it stops again with a triage scope error.

  This follows from the existing source checks. The planned fresh-run fixture does not exercise it. The scope protection is pre-existing; the new ordering and recovery advice create the interaction.

  **Concrete plan change:** define a stage-aware recovery procedure before prescribing a merge. Explain how the human safely settles the interrupted stage against its prior approved base before merging, and provide corresponding stop wording and handoff instructions. Preserve the triage scope protection. Add regressions for both pending and already-counted-but-open triage stages when origin advances.

- P3: T005’s model assignment does not fit its recovery integrity risk.

  **Location:** `.ai/tasks.md:160`; `scripts/ai-recover:153–184`.

  T005 specifies `Model: sonnet` while broadening acceptance of untrusted output that selects automatic recovery actions. `commit_and_rerun` validates and commits non-ignored leftovers, then resumes the pipeline. Preserving malformed-response rejection is an integrity control, as P1 demonstrates, rather than ordinary presentation parsing.

  **Concrete plan change:** assign T005 `Model: opus`, consistent with the required model policy for security-sensitive work. Update the model summaries in the plan and handoff.

## MINOR findings

- P4: Publish-path regression coverage is optional despite an available fixture.

  **Location:** `.ai/tasks.md:104,115`; `tests/test_workflow.py:2934–2952`.

  T003 permits documenting why the publish wording was not tested instead of verifying it. Existing hook fixtures support deterministic history manipulation without product test hooks. Start-check coverage would still pass if the new `publish_ready` branch were omitted.

  **Concrete plan change:** make the publish-path test mandatory. Use a guarded post-commit hook to create HEAD with the same tree but ancestry excluding the base. Assert the specific base error, no push or PR creation, and no recovery Claude session.

## Requirements and task assessment

T001’s assumption about missing zero-count sections matches `review_counts`. T002 correctly preserves the PR target name while passing the resolved SHA to code review. T004’s proposed non-capturing suffix preserves existing disposition groups and shared consumers.

T003’s dependency on T002 is appropriate. All tasks specify models; no task’s own failed attempt is recorded. No new dependencies or schema migrations are proposed. The planned frozen-gate boundaries and flow-note updates match repository guidance.

## Validation observed

- Confirmed the requested HEAD and clean checkout.
- Read repository instructions, spec, plan, tasks, state, handoff, relevant source, tests, prompts, documentation, validation entry points and local vault references.
- Python syntax checks passed for four source/test files.
- Bash syntax checks passed for 13 script/validation files.
- Read-only discovery collected 287 existing tests.
- `git diff --check c7d4dee..HEAD` passed.
- Reproduced P1 using the proposed algorithm in memory.

Test bodies, `./scripts/ai-check` and `.ai/bin/ai-check` were not run because they require filesystem writes unavailable in this review. No current `.ai/local/validation.json` exists. Implementation has not started, so new regression results remain unobserved.

No files were modified and no network/MCP integrations were invoked.

## Security and architecture concerns

Recovery parsing must preserve rejection before an action reaches host automation. Base recovery must preserve interrupted-stage integrity and human ownership of merges. No additional demonstrated issue was identified in the inspected T001, T002 or T004 paths.

## Manual testing recommendations

After the revised regressions and full gate pass, verify resolved-base output, stop notifications and merge-and-rerun instructions in a disposable checkout. Inspect the flow-note changes alongside T002/T003. Installed-copy upgrades remain a separate human action.

This review is not human acceptance.