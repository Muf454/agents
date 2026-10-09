# Plan: robustness batch FL-14..FL-17 (FL-12 deferred)

Plan revision: 3 (2026-10-08, after Codex plan review round 2; see `.ai/reviews/dispositions.md`).

Branch `fix/robustness-batch` from origin/master c7d4dee, worktree `~/Projects/wt/agents-robustness`.
I verified all five original items against the code on this branch, and none is already fixed.
FL-12 is dropped from this batch (see Decisions), so four remain.

1. T001 FL-14 (opus, review integrity): review reports may leave out a 0-count severity section,
   and the verdict may be a `## Overall verdict` heading. Changes: `publish_review`,
   `publish_plan_review`, the verdict line in `pr_body`, and one new helper `review_verdict`.
2. T002 FL-15 (opus, changes the reviewed range): `ai-pipeline --base B` prefers `origin/B` when
   it is strictly ahead, prints the resolved base, and passes the SHA to `ai-review`. The test
   matrix covers origin ahead, equal, absent, behind, diverged and an explicit SHA.
3. T003 FL-17 (opus, publish invariants): the pipeline stops before the plan review,
   implementation and code review when the base is not an ancestor of HEAD, after settling an
   interrupted triage stage or pending re-check (each with an advanced-base regression). The
   publish check names that case (mandatory hook-fixture test, with recovery enabled and
   disabled), and `ai-recover` escalates it by hard rule while keeping the full message on
   stderr. Depends on T002 (same lines, and it reuses its origin-ahead test fixture).
4. T004 FL-16 (sonnet, parsing): `DISPOSITION_ROW` accepts `| M1 (MAJOR) |`.

The P1 items come first, and T001, T002 and T004 are independent. T002 and T003 change the
flow (start of run, publish check, recovery hard rules), so they update the vault flow note. The
other two only change parsing, so the flow is unchanged.

## Decisions
- FL-17: the base check runs once per start, right after the interrupted-triage completion and
  `reconcile_disputes`, and before the plan review, implementation and code review. It does not
  run earlier, because an open triage stage (`triage_scope`) and a pending re-check
  (`RECHECK_RECORDS`) reject any source change since they started. A merge made while either is
  open would strand the rerun on a scope error (plan review round 1, P2). Both steps act on the
  already published review and never use the base range, so they are settled first and the
  stop's "merge and rerun" advice is always safe. A verified re-check stays verified after the
  merge (`recheck_values` checks the review binding, not the code). The base SHA is fixed for a
  run and HEAD only gains commits, so a base that is not an ancestor at the start never becomes
  one. Today such a run always ends at the publish check, after the whole implementation and
  review. A resume re-resolves the base, so the check also catches a base that moved between
  runs. `publish_ready` still names the case as defence in depth (history rewritten by a hook
  or session), and a hook-fixture test covers it.
- FL-17 recovery arm: with recovery enabled, `stop` execs `ai-recover`, whose `escalate` prints
  only its short first argument to stderr. The new arm prints the complete recorded reason to
  stderr first, so the base ref, SHA and merge advice are visible on both paths (plan review
  round 2, P6). `escalate` itself is unchanged.
- Interaction of FL-15 and FL-17: preferring an `origin/B` that is ahead makes the pipeline stop
  and ask for a merge when origin's base has moved past the branch. Today such a run passes
  against the stale local base, and its PR is out of date on GitHub. This is the intended,
  stricter behaviour, and the handoff tells the human.
- FL-14: dropping the severity headings from the required strings is enough, because
  `review_counts` already fails "counts X=n but lists none" when a section is missing and its
  count is above 0. The verdict is the only other required field. The counts line stays the
  authority, so a misnamed section with count 0 passes, as an empty one does today.
- FL-12 deferred (2026-10-08, convergence rule): relaxing `recover_decision` to accept a
  decision after prose drew MAJOR findings in both plan review rounds (round 1 P1, round 2 P1
  and P5: ambiguous prefixes via JSON escapes, objects after unfinished containers, and an
  internally inconsistent accepted case). The decision selects automatic recovery actions,
  including committing leftovers, so another lenient parser is not worth the risk.
  `recover-decision` parsing stays exactly as on master, and
  `test_recovery_decision_parsing_is_strict` is unchanged. A later batch should take FL-12 by
  having the recovery session return structured output through the CLI's `--json-schema`
  instead of parsing prose; that batch must settle CLI version support and an offline mock.

## Expected overlap with `feature/supervisor` (FL-04, PR #21)
- `scripts/lib/workflow.py`: `publish_review` and `publish_plan_review` (T001), the review format
  retry of FL-04 R4 is close by, and `DISPOSITION_ROW` (T004). Each change edits one function or
  constant in place. `recover_decision` is not touched.
- `scripts/ai-pipeline`: base resolution (T002, around line 86), one new check after the helper
  definitions, and one `elif` in `publish_ready` (T003). FL-04 adds plan-revision stages nearby.
- `scripts/ai-recover`: T003 adds its own `case` arm instead of extending the shared
  hard-rule pattern lines, because FL-04 adds patterns there.
- `scripts/ai-review`: no planned change, because the pipeline passes it a SHA.
- `tests/test_workflow.py`: new test methods only. No existing assertion changes.
- Vault `agents-flow.md`: both branches edit it. Use `Edit` on the specific lines only.
Whichever branch merges second rebases or merges the other. The conflicts should be textual and
local.
