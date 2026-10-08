<!-- Plan review of plan digest ea4fbf0555f18e4ae0456d9a58b89bca6c8b7d2446bfa8719b20149ddd89c299; saved 2026-10-08T20:29:15Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=2

Reviewed HEAD: `3f722ccdca85ce7d43bd2cda8a633811c89853ec` — plan revision 2.

Finding IDs continue from the previous review; P1 remains unresolved for additional inputs.

## BLOCKER findings

None.

## MAJOR findings

- P1: Recovery parsing still accepts ambiguous decisions and malformed containers.

  **Location:** `.ai/tasks.md:173–174`; `.ai/project-spec.md:52–60`.

  An in-memory reproduction of the revised algorithm accepts `commit_and_rerun` for both answers below:

  ```text
  {"\u0061ction":"escalate","reason":"unsafe"}
  {"action":"commit_and_rerun","reason":"second"}
  ```

  ```text
  Diagnosis.
  [
  {"action":"commit_and_rerun","reason":"x"}
  ```

  In the first answer, JSON decodes the earlier key to `action`, but the prefix regex misses it. In the second, taking the final line extracts a decision from an unfinished array. Both violate R5’s rejection requirements. These inputs currently escalate because the whole response cannot parse; the proposed fallback introduces their acceptance. The resulting action can validate and checkpoint leftovers through `scripts/ai-recover:159`.

  **Concrete plan change:** require the final object to be outside any preceding unfinished JSON container. Conservatively reject prefix escapes that could conceal an earlier action key; detecting ambiguity must never authorize recovery. Add both exact inputs as required escalation regressions while retaining the accepted `{foo}` prose case.

- P5: T005 requires an inline-prefixed object to pass an algorithm that explicitly rejects it.

  **Location:** `.ai/tasks.md:173,178–179`; `tests/test_workflow.py:1769`.

  T005 requires changing `Decision: {"action":"rerun","reason":"crash"}` to return `rerun`. Form A cannot parse that text. Form B also rejects it: the last line starts with `Decision:`, rather than `{`, and there is no preceding non-empty line. The in-memory reproduction returns `escalate`.

  Implementing the specified algorithm therefore fails the prescribed tests. Making those tests pass by extracting an inline object would contradict R5’s explicit prohibition.

  **Concrete plan change:** retain the existing inline case’s `escalate` expectation and remove it from the accepted cases. Add `Decision:\n{"action":"rerun","reason":"crash"}` as the accepted alternative. Update the claim that one existing assertion must change.

- P6: T003’s recovery arm loses the detailed stderr message required by its acceptance tests.

  **Location:** `.ai/tasks.md:99,106,114`; `scripts/ai-pipeline:128–132`; `scripts/ai-recover:35–43`.

  With automatic recovery enabled, `stop` replaces the pipeline process with `ai-recover`. The proposed arm calls `escalate` with the generic first argument `the review base moved past the branch.`. Existing `escalate` prints that argument to stderr, while preserving the original reason only in `last-error` and the notification.

  Consequently, stderr omits the base ref/SHA, merge instructions and `Publish check failed at pull request preparation:` prefix. The mandatory publish fixture explicitly enables recovery and asserts that detailed prefix in stderr, so the planned implementation will fail it.

  **Concrete plan change:** have the new arm print the complete recorded reason to stderr before escalating, or pass the complete reason as the first escalation argument. Keep the mandatory assertions and verify detailed diagnostics with recovery both enabled and disabled.

## MINOR findings

- P7: The pending re-check exception lacks a regression with an advanced base.

  **Location:** `.ai/tasks.md:101–106,113–119`; `tests/test_workflow.py:3696`.

  T003 specifies advanced-base tests for interrupted triage, but none for a pending re-check. Existing interrupted-recheck coverage keeps the base unchanged and therefore cannot establish the new ordering relative to the base stop.

  **Concrete plan change:** adapt the interrupted-recheck fixture to advance origin before resuming. Assert that the original findings are re-checked and recorded once, the base stop occurs before implementation or a replacement code review, and merge-and-rerun succeeds without a scope error or duplicate dispute.

- P8: T002’s regression matrix omits two required outcomes.

  **Location:** `.ai/tasks.md:71–75`; `.ai/project-spec.md:32–37`; `tests/test_workflow.py:2908`.

  R2 preserves local-base behavior when origin is behind, but T002 does not prescribe that test. Its referenced SHA test stops because `--pr-base` is missing; it does not demonstrate successful review against an explicit SHA.

  **Concrete plan change:** add a remote-behind case and a successful explicit-SHA run with `--no-pr` or an explicit PR target. Assert the resolved base and published review range.

## Scope and task assessment

T001’s reliance on existing `review_counts` matches the inspected source: absent sections produce empty bodies, and positive counts remain rejected. T004’s non-capturing suffix preserves the disposition groups used by triage, history, re-check preparation and PR summaries.

T003’s revised check placement addresses the prior interrupted-triage finding. T005 now specifies `opus`, and the publish regression is mandatory. Every task specifies a model; no task’s own failed implementation attempt is recorded. The model assignments and T003’s dependency on T002 are appropriate.

No new dependency, schema migration or external publishing action is proposed. Planned flow-note updates and frozen-gate boundaries match repository guidance.

## Validation observed

- Confirmed the requested HEAD and a clean checkout.
- Read repository guidance, spec, plan, tasks, state, handoff, prior review/dispositions, relevant documentation, source, tests, prompts and validation entry points.
- Shell syntax passed for 13 script/validation files.
- Python AST parsing passed for `workflow.py`, `test_workflow.py` and `run_parallel.py`.
- Read-only discovery collected 287 existing tests.
- `git diff --check c7d4dee..HEAD` passed.
- Reproduced P1 and P5 using the proposed algorithm in memory.

Test bodies, `./scripts/ai-check` and `.ai/bin/ai-check` were not run because they require filesystem writes unavailable in this review. No current `.ai/local/validation.json` exists. New regression results remain unobserved. The external vault flow note was not inspected.

No files were modified, and no network/MCP integrations were invoked.

## Manual testing recommendations

After the revised tests and full gate pass, verify base diagnostics and notifications with automatic recovery enabled and disabled in a disposable checkout. Inspect the flow-note changes alongside T002/T003. Installed-copy upgrades and human acceptance remain separate actions.