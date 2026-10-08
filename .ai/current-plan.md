# Plan: robustness batch FL-12, FL-14..FL-17

Branch `fix/robustness-batch` from origin/master c7d4dee, worktree `~/Projects/wt/agents-robustness`.
I verified all five items against the code on this branch, and none is already fixed.

1. T001 FL-14 (opus, review integrity): review reports may leave out a 0-count severity section,
   and the verdict may be a `## Overall verdict` heading. Changes: `publish_review`,
   `publish_plan_review`, the verdict line in `pr_body`, and one new helper `review_verdict`.
2. T002 FL-15 (opus, changes the reviewed range): `ai-pipeline --base B` prefers `origin/B` when
   it is strictly ahead, prints the resolved base, and passes the SHA to `ai-review`.
3. T003 FL-17 (opus, publish invariants): the pipeline stops before the code review when the base
   is not an ancestor of HEAD, the publish check names that case, and `ai-recover` escalates it
   by hard rule. Depends on T002 (same lines, and it reuses its origin-ahead test fixture).
4. T004 FL-16 (sonnet, parsing): `DISPOSITION_ROW` accepts `| M1 (MAJOR) |`.
5. T005 FL-12 (sonnet, parsing): `recover_decision` accepts one decision object after prose.

The P1 items come first, and T001, T002, T004 and T005 are independent. T002 and T003 change the
flow (start of run, publish check, recovery hard rules), so they update the vault flow note. The
other three only change parsing, so the flow is unchanged.

## Decisions
- FL-17: the base check runs once, right after the base is resolved and before any agent or
  review (it is placed after the helper functions so `stop` and auto-recovery work). The base
  SHA is fixed for a run and HEAD only gains commits, so a base that is not an ancestor at the
  start never becomes one. Today such a run always ends at the publish check, after the whole
  implementation and review. A resume re-resolves the base, so the check also catches a base
  that moved between runs. `publish_ready` still names the case as defence in depth (history
  rewritten by a hook or session).
- Interaction of FL-15 and FL-17: preferring an `origin/B` that is ahead makes the pipeline stop
  and ask for a merge when origin's base has moved past the branch. Today such a run passes
  against the stale local base, and its PR is out of date on GitHub. This is the intended,
  stricter behaviour, and the handoff tells the human.
- FL-14: dropping the severity headings from the required strings is enough, because
  `review_counts` already fails "counts X=n but lists none" when a section is missing and its
  count is above 0. The verdict is the only other required field. The counts line stays the
  authority, so a misnamed section with count 0 passes, as an empty one does today.
- FL-12: no `--json-schema`, because it depends on the CLI version and cannot be tested
  offline. "Exactly one decision" is kept: the object must end the text, and no other
  `action` object may appear before it.

## Expected overlap with `feature/supervisor` (FL-04, PR #21)
- `scripts/lib/workflow.py`: `publish_review` and `publish_plan_review` (T001), the review format
  retry of FL-04 R4 is close by, `DISPOSITION_ROW` (T004) and `recover_decision` (T005). Each
  change edits one function or constant in place.
- `scripts/ai-pipeline`: base resolution (T002, around line 86), one new check after the helper
  definitions, and one `elif` in `publish_ready` (T003). FL-04 adds plan-revision stages nearby.
- `scripts/ai-recover`: T003 adds its own `case` arm instead of extending the shared
  hard-rule pattern lines, because FL-04 adds patterns there.
- `scripts/ai-review`: no planned change, because the pipeline passes it a SHA.
- `tests/test_workflow.py`: new test methods only. Existing assertions change only where the
  behaviour intentionally changes (T005: `Decision: {...}` becomes valid).
- Vault `agents-flow.md`: both branches edit it. Use `Edit` on the specific lines only.
Whichever branch merges second rebases or merges the other. The conflicts should be textual and
local.
