# Review dispositions (Claude)

Review HEAD: 26463f1d086fe05bbd734ca884066b54a81c592a

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| N1 | accepted | Reproduced: `bash *`/`node *`/`npx *`/`npm run *`/`tee *` passed the old keyword filter. Now dropped (writers/runners by first word, open interpreters by pattern); allowlist saved per review; README no longer overstates it. Test `test_review_allowlist_keeps_only_read_and_check_commands` extended. | T008 |
| N2 | accepted | `claude-text` now appends reviewer denials to `.ai/local/review-denials.log` and prints the count. Test `test_claude_review_denials_and_allowlist_are_recorded`. | T008 |
| N3 | accepted | Reproduced false positives ("author", "Lockfile", "Race results"); whole-word patterns now, negative and positive cases in `test_review_risk_helper`. | T008 |
| N4 | accepted | PR note now quotes the label reason; forced reviews are labelled "Claude (… AI_REVIEWER=claude)"; the report lists every Claude-written review like the fallback log does. Tests in the pipeline and outcome tests. | T008 |
| N5 | accepted | Vault updated in this session: hub Decision + Log lines, human todo "Codex catch-up review" dated ~2026-10-14 (interactive session, so the author edits the vault directly). | T008 |

Other notes from the review:
- Invalid `AI_REVIEWER` in `ai-pipeline`: accepted, validated at the argument check (`test_pipeline_rejects_an_invalid_reviewer_setting_first`).
- `ai-run` doesn't tolerate a dirty fallback log while `ai-pipeline` does: rejected as a change. Inside the pipeline `ai-run` only starts after `reconcile_disputes`/review records committed the log; a hand-run `ai-run` with uncommitted review records should stop, as for any other record.
- One "↪ Codex usage limit" notification per review step: deferred (minor noise; once-per-run needs manifest state).
- Missing coverage added: Claude review failure and a reviewer writing outside the probe dir keep the prior review (`test_claude_review_failure_or_write_keeps_the_prior_review`); watchdog `--diagnosis-agent codex` never falls back (`test_watchdog_codex_diagnosis_does_not_fall_back`). Not added: Claude limit beyond `AI_LIMIT_MAX_WAIT` and a reviewer timeout; both use the shared `ai_limit_pause`/exit-124 handling already tested for Codex and the runner.
- `--diagnosis-agent claude` now uses `AI_DIAGNOSIS_MODEL` (default claude-sonnet-5-5) instead of `AI_MODEL`: intended (R3), documented.

## Plan review round 1 (HEAD cc8c464)

Report: `.ai/reviews/plan.md` (plan digest 0f7f90a1…, BLOCKER=0 MAJOR=10 MINOR=1). Planner
(Claude, interactive, for mission control) 2026-10-07. All findings verified against the code;
none rejected. Plan rewritten as revision 2 (T001–T011).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 | accepted | `scripts/ai-run:24-51` parser knows only `--triage`/`--since`; old T001 needed `--revise-plan` from old T002. Revision mode is now standalone and hand-tested (T005) before the pipeline loop (T007), each checkpoint testing only what exists. | T005, T007 |
| P2 | accepted | The revision allowlist is an authorization boundary; `claude_session` (`scripts/ai-run:152-157`) passes the full project allowlist today. New `plan-revision-allowlist` + scope/plan.md checks run on opus. | T005 |
| P3 | accepted | `ai_config` key list (`scripts/lib/common.sh:37`), `RUN_SETTINGS` (`workflow.py:1625`) and both lists in `scripts/ai-recover:69,72` enumerate keys; new settings would be ignored/lost on resume. T001 wires all four plus a list-consistency test; `AI_SUPERVISE=0` now disables revision, extra round and format retry (spec R5), tested in T007/T009/T010. | T001, T007, T009, T010 |
| P4 | accepted | `ai-run` budget is per process (`started=$SECONDS`, `remaining_time`, `scripts/ai-run:78,127`); the pipeline passes `--run-timeout` only to implementation (`triage_args`, `ai-pipeline:210-213`). Host `run-budget` in the run manifest, shared by all `ai-run --host-budget` calls, pauses not charged, crash charges the grant; exhaustion is a terminal stop. | T002 |
| P5 | accepted | `review_rounds` matches only `chore(ai): record independent review` commits changing `current.md` (`workflow.py:872-901`); `--current` needs the code-review header (`:904-912`). New host `plan-rounds` records + `plan-history` pairing each round with its section by report digest; tests include earlier implementation reviews. | T003 |
| P6 | accepted | `review_rounds` docstring: "Context only, never authority" (`workflow.py:873-875`). Trend now from host `fix-rounds` records extended with the verified review counts at triage time, extra round reserved in the run manifest before it starts; forged/legacy/insufficient/interrupted cases tested. | T009 |
| P7 | accepted | `triage_check` builds `rows` from the whole file and searches `CONVERGENCE_LINE` anywhere (`workflow.py:824,847`); copying that for appended sections would accept old rounds. Host-written section per round + report digest, validated alone, earlier text immutable, duplicates/unknown IDs/task refs/questions/no-DONE checked. Moved to `.ai/reviews/plan-dispositions.md` because `start_dispositions` rewrites `dispositions.md` per code review (`workflow.py:790-807`). | T004 |
| P8 | accepted | `stage-set` accepts only `triage` (`workflow.py:1094`), `stage_fields` likewise (`:1161`); `ai-recover:102-106` has no pattern for supervision stops and `:113-121` uses `triage-scope` for any stage. New `plan-revision` stage, per-digest reservation, terminal patterns, crash scenarios. | T006, T008 |
| P9 | accepted | `PLAN_BOOKKEEPING` excludes `.ai/reviews/` from `plan_digest` (`workflow.py:1905-1914`) and the pipeline skips a `current` plan review (`ai-pipeline:300`). A host `plan-revisions` record for the current report forces a fresh review with the dispositions as context; dispositions-only test asserts two plan-review calls. | T007 |
| P10 | accepted | `parse_recheck` turns malformed JSON into upheld answers and `publish_recheck` succeeds (`workflow.py:1300-1314,1343`), so a publish-failure retry never fires for re-checks. R4 limited to Markdown plan/code reviews via a shared `review-format-check`; integrity failures stay `ai_die`; re-check behaviour pinned by a test. | T010 |
| P11 | accepted | AGENTS.md "Keep the flow chart current" requires the chart and `updated:` in the same session as the flow change. Each flow-changing task (T002, T006, T007, T009, T010) updates it; T011 only reconciles. Also found: the live handoff lacked `## Flow chart`, which `test_pr_body_flow_this_repo_declares_the_flow_chart` requires; added ("Flow unchanged" until T002). | T002, T006, T007, T009, T010, T011 |

Also from the review's limitations: the `fix/catchup-review` prerequisite is unmerged; the plan
keeps "implement after it merges, rebuild on master, review the plan again" (current-plan
Coordination).

## Plan review round 2 (HEAD dfc03c8)

Report: `.ai/reviews/plan.md` (plan digest fdb66613…, Claude fallback claude-fable-5-1,
BLOCKER=0 MAJOR=1 MINOR=7). Planner (Claude, for mission control) 2026-10-08. Each finding
verified against the code at dfc03c8; none rejected. Plan rewritten as revision 3 (same T001–T011;
T006 now also depends on T001). Run budget unchanged (Zack's Q2: 16 h cumulative, per-call
`--run-timeout` cap).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 | accepted | Old T007 ordered "stage-set, `revision-reserve`" and T006's `complete_plan_stage` neither reserved nor passed `--model`; the precedent `scripts/ai-recover:63-65` (comment + `reserve-attempt`) reserves before anything interruptible, and triage fails closed on a dirty tree after its counted commit (`scripts/lib/workflow.py:1209-1210`). Now: `revision-reserve DIGEST LIMIT` (idempotent, a reserved digest passes even at the limit) before `stage-set`; `complete_plan_stage` (fresh and resume) verifies first (committed → clear only), else reserves again and takes the model from one `plan_revision_model` function (round from host records, settings from the manifest); `stage-verify` fails on a dirty tree after the record commit. T008 adds the reserve/stage windows (with limit 1) and a round-3 crash asserting the escalation model. | T006, T007, T008 |
| P2 | accepted | `fix-rounds count BASE` filters `BASE..HEAD` (`workflow.py:1489-1497`) while `plan-rounds` had no base; per-branch-name stores would inherit merged rounds. All `plan-rounds`/`plan-history`/`start-plan-dispositions` actions take BASE (pipeline `base_sha`, `ai-pipeline:86`; by hand `--base REF`, default `main` as `ai-pipeline:24`; `ai-review` already parses `--base`, `scripts/ai-review:26`); legacy init limited to `BASE..HEAD`; recreated-branch test. | T003, T004, T005, T007 |
| P3 | accepted | `ai-run --triage` re-records its round on completion (`scripts/ai-run:227-230`); the plan-review record had no such repair, so a crash between `host_commit 'chore(ai): record plan review'` (`ai-pipeline:305`) and its record made `plan-rounds current` fail → human stop. New `plan-rounds sync BASE` at the top of every loop pass and in `ai-review --plan`/`ai-run --revise-plan`; records idempotent per report digest; window added to T003 and T008 tests. | T003, T007, T008 |
| P4 | accepted | Hand-run `ai-run` sets `since=HEAD` (`scripts/ai-run:182`), so after a committed section START already holds the header, and with no file at START there was nothing to compare the preamble with. Three-case rule (START's text above the same header / START's whole file / exact host preamble) in the plan contract and T004 tests; `ai-run --revise-plan` refuses an already recorded report ("already revised; review again"), and `complete_plan_stage` clears a committed stage without calling it. Both resume shapes in T005 tests. | T004, T005, T006 |
| P5 | accepted | `ToolkitTest.setUp` sets `AI_AUTO_RECOVER='0'` (`tests/test_workflow.py:389`); the mock Claude asserts `RUNNER CONTRACT`/`TRIAGE CONTRACT` (`:78`) and the plan-stop tests use `MOCK_CODEX_PLAN='major'` (`:1562-1598`), which a default `AI_SUPERVISE=1` would turn into revision calls. Decision: fixture default `AI_SUPERVISE='0'` (T001), supervised tests opt in; T007 adds `MOCK_CODEX_PLAN=major-once` and asserts the existing plan-stop tests pass unchanged. | T001, T007 |
| P6 | accepted | `ai_config` reads only enumerated keys (`scripts/lib/common.sh:37`). `AI_RUN_BUDGET` added there, validated only at a human `ai-pipeline` start and kept only as the manifest budget total (a resume never reads it), named as the single exception in the key-list identity test. `ai_supervise_settings` exports the four validated values and `ai-review`/`ai-run` call it too. | T001, T002 |
| P7 | accepted | Between sessions `ai-run` dies with `Run time limit reached ...` (`scripts/ai-run:143`), which matches no always-escalate pattern (`scripts/ai-recover:102-106`), so a recovery session would be spent. Under `--host-budget` the message is `Run budget exhausted (used U of T s)` when the budget (not the per-call cap) ran out, and a remainder below `BUDGET_FLOOR` 60 s counts as exhausted; T002 tests assert no `recover-calls`/`mock-invocations`. | T002 |
| P8 | accepted | `ai_die` writes last-error and `ai_notify` passes it as an argument (`scripts/lib/common.sh:11-24,62-67`); `recover_decision` already bounds model text (`workflow.py:1666`). `--questions` now prints ≤ 3 questions, single-line, ≤ 300 chars each, plus a "+k more" pointer. `claude_session` gets the tool list as a parameter; `--revise-plan` uses `Read,Glob,Grep,Edit,Bash` (no `Write`; the host creates the file), asserted from mock args. | T004, T005, T007 |

Also from the review's "Missing coverage": T009 gains the legacy-round-1 trend boundary test and
T010 asserts the retried `run_review` still fails the `unchanged` check on a mutating second call.
