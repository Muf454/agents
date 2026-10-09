<!-- Host evidence: HEAD 70e2c1310d8f79bd1e2ff2027513c97eaf8bea3e; merge-base feea5d2970c28fb777031fe46bd6dcb756f7019e; saved 2026-10-09T05:34:06Z. -->

> **Reviewer: Claude fallback (claude-fable-5-1, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

# Independent review

Overall verdict: APPROVE — the merge of master into FL-04 is sound; both accepted findings of round 1 are fixed in source; one MINOR recovery-path inefficiency remains.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `70e2c1310d8f79bd1e2ff2027513c97eaf8bea3e`

Supplied base: `feea5d2970c28fb777031fe46bd6dcb756f7019e` (merge-base is the same commit)

Inspected: `.ai/local/review-context/diff.patch` (script and helper hunks), `.ai/local/review-context/since-last-review.patch` (merge of #19/#20/#22: scripts, prompts, tests), the actual merged source of `scripts/ai-pipeline`, `scripts/ai-review`, `scripts/ai-run`, `scripts/ai-recover`, `scripts/lib/common.sh`, the plan-round/revision/stage/fix-round helpers in `scripts/lib/workflow.py` (lines 1067–1346, 1550–1640, 2063–2602), the format-retry, supervised-plan, decision-gate and resume tests in `tests/test_workflow.py`, spec, plan, tasks, handoff, state, dispositions and the previous review.

## Validation observed/run

- `.ai/local/validation.json`: **PASS**, exit 0, at `2026-10-09T05:26:04Z`, `head` = reviewed HEAD, `unchanged: true`. Its log `.ai/local/check-bpatblo0.log` ends `Ran 401 tests in 256.5s (8 shards, 401 collected)` / `OK`.
- Merge-commit claims checked against the source: format retry runs on master's relaxed format checks (`review_format_error` with `review_verdict`, `workflow.py:778`; `review-format-check` used by `ai-review:230`); the base-moved stop (`ai-pipeline:380`) precedes the needs-human decision check (`:402`); attempt tracking brackets only the implementation session (`ai-run:468–470`, `track_attempt` never set for `--revise-plan` or `--triage`); one `PIPELINE_TIMEOUT` definition (`tests/test_workflow.py:18–20`, used at `:1119`).
- No commands were run (no shell in this review).

Limitations: tests were not rerun here; the frozen `.ai/bin` copies were not compared line by line with `scripts/`; README, `docs/workflow.md` and the vault were only spot-checked (N1 wording at `docs/workflow.md:381`); Claude Code's actual enforcement of the `Edit(./path)` allowlist and of "read only inside the checkout" cannot be established from mocks.

## Requirement assessment

- **R1/R2 (bounded revision, convergence, escalation):** the plan loop (`ai-pipeline:406–469`) reserves per report before `stage-set`, completes the stage through `ai-run --revise-plan`, re-reviews on a clean checkout, and escalates the model by round (`:269–278`). Round ≥ 3 requires a Convergence line in both the prompt (`ai-run:290–294`) and the validator (`workflow.py:2436`).
- **R3 (extra fix round):** `fix-rounds trend` uses only dict records with verified counts and rejects a current review equal to the last record (`workflow.py:1630–1638`); the reservation is written before `stage-set` (`ai-pipeline:521–535`).
- **R4 (format retry):** one retry for plan/code, never for re-checks (`ai-review:270–271`); integrity failures stay fatal inside `run_review`.
- **R5 (guard rails, durable decision):** `plan_decision_check` runs unconditionally at start (`:402`), per loop pass (`:409`) and before implementation (`:470`); `ai-recover` checks the stored decision before the attempt limit and any resume (`ai-recover:105–119`) and closes a committed stage so the human's new review can proceed.
- **Previous rounds:** M1 fixed as traced above (`test_needs_human_decision_gate_*` cover skip, partly-done queue, unreadable store, recovery). M2 fixed: `review_head` pinned per review (`ai-review:294`, `:378`), checked after the notification and before the retry (`:238–241`) and before publish (`:244`, `:246–249`); `test_format_retry_stops_when_the_checkout_changes_between_the_calls` covers committed and dirty mutations for code and plan. N1 fixed (`docs/workflow.md:381`; the old phrase is absent).

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N1 — A failed plan-revision section check is retried by auto-recovery although a resume can never succeed, and the final stop loses the concrete reason

**Status:** demonstrated (exact path traced; not exercised by tests).

**Location:** `scripts/ai-recover:127–133` (always-escalate patterns), `scripts/ai-run:309–310` and `:260–264`, `scripts/ai-pipeline:299–300`.

**Problem:** when the revision session returns but the host validator rejects its section (`ai-run:309`: `Plan revision incomplete: <reason>`, e.g. `Plan review round 3 needs a Convergence: line`, a missing row, an accepted finding without a TODO task), the pipeline calls `stop 'plan revision'` and hands over to `ai-recover`. That reason matches none of the hard rules (`'Plan revision stage'`, `'supervision limit reached'`, `'needs your decision'`, …), the attempt is within `AI_RECOVER_MAX`, the open stage's scope passes (the session's rows in `plan-dispositions.md` and the runner's `run-log.md` line are both in `PLAN_REVISION_RECORDS`, `workflow.py:2270`), so `ai-recover:141–153` resumes the pipeline. The resumed `complete_plan_stage` finds the stage pending and runs `ai-run --revise-plan` again, which cannot start a session on a section that already holds rows: `start-plan-dispositions --pending` requires the file to differ from HEAD by exactly the host header (`workflow.py:2314–2320`), so it dies with `Plan revision stage: incomplete plan revision records are uncommitted` (`ai-run:264`). The second `ai-recover` escalates on the `'Plan revision stage'` rule and overwrites `.ai/local/last-error` with that generic message (`ai-recover:40`).

**Impact:** one recovery attempt of the run's budget and one pipeline restart are spent on a resume that is guaranteed to fail; the human's final stop message and `last-error` name "incomplete records uncommitted" instead of the validator's reason (which survives only in the earlier "🔧 Recovering" notification and the terminal). Nothing is counted twice and no record is lost. This is the likely real-world shape of a model forgetting the round-3 Convergence line.

**Evidence:** `test_supervised_plan_escalation_model_and_round_three_convergence` (`tests/test_workflow.py:2606`) asserts the first stop but runs under the fixture default `AI_AUTO_RECOVER='0'` (`:549`); no test runs this stop with recovery on.

**Recommended direction:** make these stops terminal for recovery, e.g. prefix the validator failure in `ai-run` with `Plan revision stage: ` or add `*'Plan revision incomplete'*` to the always-escalate case (gate copy in `.ai/bin` needs the human's upgrade). Add a test variant of the round-3 case with `AI_AUTO_RECOVER='1'` asserting direct escalation, no resume, and the Convergence message in `last-error` and the notification.

## Missing test coverage

Checklist items checked for this change (shell/Python tooling, no database or UI): 1 lock order (single `flock` on `.ai/local/workflow.lock`, inherited by children, hand-over by `exec`; no second lock introduced), 3 attribution (round counts, reservations, revision outcomes and fix-round trends come from host state, never from commit subjects: `workflow.py:1147–1176`, `2172–2204`, `2510–2534`, `1599–1638`), 10 irreversible operations (reservations and stage records are written before any interruptible step; a human restart resets per-run allowances only). Items 2, 4–9 do not apply.

- Recovery path after a validator-rejected revision section (N1 above): no test with `AI_AUTO_RECOVER=1`.
- The Claude fallback plan review's `files.txt` lists only spec/plan/tasks (`ai-review:93`); after a revision the Codex and Claude prompts name `.ai/reviews/plan-dispositions.md`, which the Claude reviewer can still `Read`. Not a defect; `test_claude_review_context_plan_mode` only covers the pre-revision case.
- No test runs a format retry on a plan review inside the pipeline after a revision (the `PLAN REVISION CONTEXT` prompt plus `FORMAT ERROR` suffix). The composition is purely string concatenation (`ai-review:300–316`, `:242–243`) and the pieces are tested separately, so this is low value.

## Security concerns

No new defect demonstrated. Two known limitations the handoff already lists remain unverifiable here: the plan-revision session's `Edit(./<record>)` allowlist and the absence of Bash/Write are only asserted from mock arguments (`ai-run:300–301`, `workflow.py:2470–2473`), and the Claude reviewer's "read only inside this checkout" is an instruction, since the `Read` tool is not path-scoped (inherited from master #19, documented in the prompt). The revision session may change `.ai/tasks.md` text that later implementation sessions follow; that is the same trust boundary as today's planning session, and the host still enforces status immutability, TODO-only new tasks and the no-source scope (`workflow.py:2438–2448`, `2456–2460`).

## Architecture concerns

None. Authority stays in host state outside the checkout; rendered history is context only. The merge kept both sides without duplicating logic: master's base resolution (`origin/<base>` when strictly ahead) feeds `base_sha` into plan rounds, revisions and reviews consistently, and the base-moved check sits after stage completion and before the decision check, matching the "merge only after the stop" rule from #22.

Pre-existing, excluded from counts: the previous review's note about `README.md` describing serial test discovery was not re-checked in this round.

## Manual testing recommendations

### Needs you

- The live supervised trial in `.ai/handoff.md` "Needs you" (real Claude and Codex on a throwaway project): plan revision, clean re-review, needs-human stop, `ai-recover` on that stop, clearing it with a hand-run `ai-review --plan`.
- In that trial, confirm the revision session can edit only the five plan records (try to make it touch a source file or `plan.md`) and that the pipeline stops with nothing counted.
- Before using `--revise-plan` in this repository, run `setup-project --upgrade` so the frozen `.ai/prompts` gets `plan-revision.md` and `.ai/bin` matches `scripts/`.
- If N1 is accepted, verify once with `AI_AUTO_RECOVER=1` that a revision rejected by the validator escalates directly with the validator's message.

### Covered by automated tests

- Decision gate on every start, skip path and partly-done queue: `test_needs_human_decision_gate_*`; decision survives crashes and recovery: `test_supervised_plan_resume_decision_after_*`.
- One checkout per format retry: `test_format_retry_stops_when_the_checkout_changes_between_the_calls`; retry matrix for Codex, Claude fallback, plan by hand, pipeline commits, re-check never retried: `test_format_retry_*`.
- Supervised loop, limits, escalation model, round-3 Convergence, out-of-scope revision, `AI_SUPERVISE=0`: `test_supervised_plan_*`; crash points: `test_supervised_plan_resume_*`.
- Extra fix round trend, reservation and resume: `test_extra_fix_round_*`.
- Merged master behaviour: review base resolution and base-moved stops `test_review_base_*`, `test_base_moved_*`; no-shell reviewer context `test_claude_review_context_*`; stopped-attempt outcomes `test_outcome_*`; relaxed format checks `test_review_format_*`.
- Full suite at HEAD: 401 tests OK (host validation evidence above).

Review approval does not constitute human acceptance.
