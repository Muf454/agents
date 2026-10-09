# Review dispositions (Claude)

Review HEAD: 5b8d86b759819bc6ae78a18850fdff6d5319fcc2
## Plan review round 7 (HEAD a7956da, 2026-10-08): BLOCKER 0, MAJOR 2, MINOR 1

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 incomplete append swallows the recovery row | deferred | Real, but only in the crash-durable marker design (old T003/T004), which this fix no longer includes: Convergence: rounds 5–7 kept finding durability edge cases in an advisory telemetry log; the marker work moves to backlog CU-5 and R2 documents the SIGKILL limit. | — |
| P2 existing outcome not proven durable | deferred | Same area and reason as P1 (CU-5). | — |
| P3 README outcome contract outdated | accepted | T002 updates README's outcome section together with `docs/workflow.md`. | T002 |

## Plan review round 6 (HEAD ae9bd39)

Codex plan review, 2026-10-07: BLOCKER 0, MAJOR 3, MINOR 1 — all accepted (revision 6).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 outcome append + marker removal not crash-safe or idempotent | accepted | Confirmed: `workflow.py` `outcome` (line ~2037) always appends, numbers attempts by counting earlier rows and has no attempt identity or fsync; `outcomes-report` takes the last row per task as its result, so a spurious `crashed` after `done` makes a finished task unfinished. T003 now gives each attempt a unique ID in marker and row, `outcome task --attempt-id` skips an already-logged ID, `attempt finish`/`reconcile` remove a stale marker without appending again, and the write order is durable (marker fsynced before the session; outcome line fsynced before the marker unlink; directory fsyncs). Boundary-state tests after a normal append and after a reconciliation append, each recovered twice. Spec R2 extended. | T003 |
| P2 Sonnet for locking-sensitive crash recovery | accepted | The CLAUDE.md model rules put concurrency and locking on opus. T003 split into T003 (helper, opus) and T004 (`ai-run` wiring after `ai_lock`, SIGKILL and lock tests, docs; opus); `current-plan.md` updated. | T003, T004 |
| P3 context preparation failures fall through to the session | accepted | Confirmed: `run_review` calls `claude_attempt "$prompt" \|\| code=$?` (`ai-review` line ~152), where bash suppresses `errexit` in the called functions. T001 now requires an explicit check on every mandatory context command and write, removing the partial context and `ai_die` before `claude` runs; new test with a test-local `git` wrapper failing the context `diff --no-ext-diff` asserts no Claude call, the prior review unchanged and bound, and no context left. Spec R1 extended. | T001 |
| P4 malformed-queue retry attempt number | accepted | Confirmed: `test_runner_no_progress_denial_and_error_stop_without_retry` runs five modes on T001 in one project and never reruns, so `bad-format` is attempt 5 there. That test now asserts previous attempt + 1 per mode; the retry (attempt 1 `error`, attempt 2 `done`, `first_pass=false`) moves to a fresh fixture `test_outcome_malformed_queue_then_retry`. | T002 |

The no-Bash reviewer design is kept. The handoff's automated-coverage list is now labelled as planned.

## Plan review round 5 (HEAD 23ea938)

Claude Fable fallback review, 2026-10-07: BLOCKER 0, MAJOR 2, MINOR 3 — all accepted.

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 spec and plan still describe the abandoned allow/deny policy | accepted | Confirmed: spec R1 still required inherited `Bash(...)` entries and `--disallowedTools`; `current-plan.md` said "positive list + deny list"; T001 said no Bash. R1 rewritten to revision 4 (Read/Glob/Grep only, host-prepared context, `.allowlist` = the three tools); the Reference paragraph's live deny-list check marked superseded; plan line updated. | T001 |
| P2 host context underspecified per mode; acceptance only checks existence | accepted | Confirmed in `scripts/ai-review`: `claude_attempt` gets only the prompt; recheck has `head` but no base in shell scope (only in the review header that `current_review_rounds` parses, `workflow.py:905-908`); plan mode has no range; the code prompt says "Inspect git diff …" and "CHANGED SINCE … inspect git diff" (`ai-review:251,258`). T001 now specifies files per mode (code incl. `since-last-review.patch`; recheck base via a new `review-range` helper sharing the header regex, plus `findings.txt`; plan `files.txt`/`log.txt`, no diff), a separate `claude_prompt` naming the files, mock changes, and acceptance on content (`T001.txt` in `files.txt` and `diff.patch` for code and recheck) and cleanup after success, `MOCK_CLAUDE_REVIEW='error'` and `limit-once`. | T001 |
| P3 SIGINT/SIGTERM test would hang | accepted | Matches bash semantics (a trapped signal runs after the foreground command returns) and `timeout` running in its own process group. T002 now prescribes a `hold` mock released by a file after the signal, `Popen(start_new_session=True)`, bounded polls and `communicate(timeout=20)`, cleanup in `finally`; 137 via a `self-kill` mock; the deferred delivery (Ctrl-C) is documented. | T002 |
| P4 targeted validation misses plan/recheck fallback tests | accepted | `-k` is a substring match; `fall_back` ≠ `fallback`, so `test_plan_review_and_recheck_fall_back_to_claude` and `test_recheck_falls_back_to_claude` were not selected. Added `-k fall_back -k reviewer_setting -k pipeline_without_codex -k review_context -k review_range`. | T001 |
| P5 SIGKILL/power loss leaves no outcome | accepted | `on_exit` cannot run on SIGKILL, and that is exactly the watchdog/`ai-recover` path where R2's "recovery is not a first-time pass" matters. Fix rather than document: host-side attempt marker in the state root (agents cannot write it), opened/closed with T002's attempt, reconciled as one `crashed` outcome after `ai_lock` at the next `ai-run` start; test with a new `crash` mock modelled on `triage-crash`. Split into its own task to keep T002 small; spec R2 extended. | T003 |

Missing-coverage notes also taken into the tasks: cleanup after a failed review and a limit retry (T001), mock changes keeping the "writes outside its scope" case (T001), the named malformed-queue test with per-subtest row indexing (T002), `error` for a limit wait beyond `AI_LIMIT_MAX_WAIT` (T002 docs). Security note (Read not limited to the checkout): one prompt line in T001's `CLAUDE REVIEWER` suffix.

## Plan review round 4 (2026-10-07): BLOCKER 0, MAJOR 1, MINOR 2 — all accepted

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P5 git option abbreviations bypass the deny list | accepted | `git grep --open-files=` (abbreviation) is accepted by git; deny globs can't enumerate abbreviations for any git subcommand. Convergence: the fallback reviewer gets no Bash at all (Read/Glob/Grep); the host prepares diff/log/files context. | T001 |
| P4 targeted tests miss the invocation test | accepted | `-k review_falls_back` added. | T001 |
| P6 README promises runner permissions | accepted | README's fallback reviewer section is in T001. | T001 |


## Plan review round 3 (HEAD e52ed76, 2026-10-07): BLOCKER 0, MAJOR 2, MINOR 2 — all accepted

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 exact runner entries also unsafe | accepted | Third round on the reviewer's runner commands. Convergence: the reviewer inherits no runners at all (exact or wildcard), only read-only file tools; it uses the host's validation evidence like Codex. Tests seeded with unsafe exact and wildcard entries. | T001 |
| P2 triage would open a task attempt | accepted | `claude_session` serves `--triage` too. Attempt tracking is opt-in for implementation; triage and limit-retry regressions added. | T002 |
| P3 flow chart deferred to T002 | accepted | T001 updates the chart for the reviewer policy itself. | T001 |
| P4 targeted tests miss reviewer tests | accepted | Explicit `-k` selection incl. `claude_review`. | T001 |


## Plan review (HEAD 00e644d, 2026-10-07): BLOCKER 0, MAJOR 3, MINOR 2 — all accepted, tasks revised

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 retained runners keep write/exec options | accepted | `pytest --junitxml`, `go test -exec`, `tsc --noEmit false` pass the reference policy. T001 now enumerates runners and dangerous forms with a table-driven test; wildcards only where all are denied; live check by mission control. | T001 |
| P2 outcome logging needs a parseable queue | accepted | `outcome task` reads titles via `tasks()`. T002 makes it tolerant + malformed-queue test. | T002 |
| P3 no interruption test | accepted | SIGINT/SIGTERM subprocess tests and a separate 137 case added to T002. | T002 |
| P4 attempt opened before launch | accepted | Attempt now opens right before the invocation; zero-budget case. | T002 |
| P5 flow chart | accepted | Vault `agents-flow.md` update and "Flow chart updated" in T002. | T002 |


Review HEAD: 26463f1d086fe05bbd734ca884066b54a81c592a

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in source: `plan_decision_check` is defined at `scripts/ai-pipeline:361` and called only at `:379`, inside `if [[ "$plan_review" == yes ]] && ai_helper tasks untouched` (`:376`). With `--skip-plan-review` (`:36`) or any DONE task the loop is skipped and the implementation loop (`:440`) starts without a decision check; a completed startup plan-revision stage (`:344-351`) is also not followed by a check in that case. Spec R5 explicitly requires the check at "pipeline start, loop entry and `ai-recover`". `plan-revisions decision` keys on the verified report (`workflow.py:2553-2569`), not on task state, so an unconditional check is feasible. Existing needs-human tests only use the plan-review-enabled, untouched-queue path. | T011 |
| M2 | accepted | Confirmed in source: `run_review` captures `start_head` per call (`scripts/ai-review:121`) and `unchanged` compares against it (`:124-125`); `review_with_format_retry` calls `run_review` twice (`:190`, `:199`) with the format check and `ai_notify` in between, so a committed checkout change between the calls becomes the retry's baseline. The code path then publishes against the outer `$head` (`:318`, `:336`) and the plan path against the pre-review `digest` (`:235`, `:259`). Spec R4 / T009 require checkout integrity before the retry; tests only mutate during a reviewer call. | T012 |
| N1 | accepted | Confirmed: `docs/workflow.md:373` says round-three triage is "only reachable with `--max-fix-rounds` ≥ 3", but `scripts/ai-pipeline:479-494` grants a supervised extra round at the default limit 2, exercised by `test_extra_fix_round_falling_counts_get_one_round_then_draft`; the vault `agents-flow.md` Convergence note repeats the restriction. Cheap and in scope (R6). | T013 |
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

## Plan review round 1 (robustness)

Codex plan review of HEAD 4cc7d2e, 2026-10-08: BLOCKER 0, MAJOR 3, MINOR 1. All accepted (plan revision 2).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 recovery suffix scanning accepts malformed or ambiguous decisions | accepted | Confirmed against the planned algorithm: treating a duplicate-key `ValueError` as "no object here" hides the earlier `action` object, and `raw_decode` from a `{` inside `[{…}` extracts an object from a malformed container. `recover_decision` (`workflow.py:1625`) feeds `ai-recover`, where `commit_and_rerun` commits leftovers. Replaced with the narrowest line-based form: the whole text is one object (as today), or one object on the last non-empty line, optionally alone in a closing fence. Any `"action":` text before it escalates. No `{` scanning. Both reproductions and the multi-line, extra-data and array cases are now required escalate tests. Spec R5 and plan decision updated. | T005 |
| P2 early base stop's merge advice strands an interrupted triage | accepted | Confirmed: `complete_stage` → `stage_verify` → `triage_scope` (`workflow.py:1162–1191`) fails on any non-record change since the stage start, and a pending re-check allows only `RECHECK_RECORDS` (`workflow.py:1228`). A merge made while either is open therefore fails the rerun. The base check moves to right after the top-level `reconcile_disputes` (`ai-pipeline` ~297), so the stage and re-check are settled against their review first (neither uses the base range), and the stop's "merge and rerun" advice is then safe. The scope protection is unchanged. New regressions cover a pending and a counted-but-open triage stage with origin advanced. Docs, flow note and handoff wording say "merge only after the stop". | T003 |
| P3 T005 model too weak for recovery integrity | accepted | The decision selects automatic recovery actions, including committing leftovers (`ai-recover` ~153–184), so it is integrity-sensitive under the model policy. T005 is now `Model: opus`, and the plan and handoff summaries are updated. | T005 |
| P4 publish-path regression optional | accepted | The hook fixtures (`tests/test_workflow.py:2934–2952`) support it without product test hooks. The test is now mandatory. With `main` moved to the plan commit, a guarded `post-commit` hook on the review record re-parents HEAD onto `main^` with the same tree (`git commit-tree -p main^` + `git reset --soft`). The checkout is clean, the content matches and a merge-base exists for `disputes-verify`, but the base is not an ancestor. It asserts the base wording, no "reviewed content changed", no push, no `pr create` and no recovery Claude call. | T003 |

## Plan review round 2 (robustness)

Codex plan review of HEAD 3f722cc (plan revision 2), 2026-10-08: BLOCKER 0, MAJOR 3, MINOR 2. P6–P8 accepted, P1 and P5 deferred with FL-12 (plan revision 3).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 recovery parsing still accepts ambiguous decisions and malformed containers | deferred | Convergence rule: relaxing the `recover-decision` parser drew MAJOR findings in both plan review rounds (round 1 P1, round 2 P1 and P5). The decision selects automatic recovery actions (`commit_and_rerun` commits leftovers, `scripts/ai-recover` ~159), so FL-12/T005 is dropped from this batch instead of patching the parser again. `recover_decision` and `test_recovery_decision_parsing_is_strict` stay exactly as on master, so neither reproduction can be accepted (both still fail to parse as one object and escalate). Risk of deferring: a recovery session that writes prose first still escalates as "gave no valid decision", which is safe. A later batch should use the CLI's structured output (`--json-schema`) rather than a lenient parser. | — |
| P5 T005 requires an inline-prefixed object that its algorithm rejects | deferred | Same as P1: T005 is removed with FL-12, so the inconsistent accepted case is gone and the existing `Decision: {...}` → `escalate` assertion stays unchanged. | — |
| P6 T003's recovery arm loses the detailed stderr message | accepted | Confirmed: with recovery enabled `stop` execs `ai-recover` (`scripts/ai-pipeline:128–132`), and `escalate` prints only `${1:-$reason}` to stderr (`scripts/ai-recover:43`), so the generic first argument would replace the base ref/SHA, merge advice and `Publish check failed at …` prefix the mandatory test asserts. The new arm now prints the complete recorded reason to stderr before escalating; `escalate` stays unchanged. The start test asserts the full message on stderr with recovery enabled, and a new `test_base_moved_publish_check_without_recovery` checks the publish path with recovery disabled next to the enabled one. Spec R3 updated. | T003 |
| P7 pending re-check exception lacks an advanced-base regression | accepted | Confirmed: `test_disputed_findings_interrupted_before_recheck_rechecks_original_findings_first` (`tests/test_workflow.py:3696`) never moves the base. New `test_base_moved_with_pending_recheck` advances origin before resuming and asserts the original findings are re-checked and recorded once, the base stop comes before implementation and any replacement code review, and merge-and-rerun succeeds with no re-check scope error, no second re-check and no duplicate dispute. A verified re-check stays verified after the merge, because `recheck_values` (`workflow.py:1360`) checks the review binding, not the code. | T003 |
| P8 T002's regression matrix omits two outcomes | accepted | Confirmed: R2 keeps the local base when origin is behind, but no test was prescribed, and `test_pr_base_follows_the_review_base_or_must_be_explicit` (`tests/test_workflow.py:2908`) only shows that `--base <sha>` stops for a missing `--pr-base`. Added `test_review_base_local_ahead_of_origin` and `test_review_base_explicit_sha` (`--no-pr`), each asserting the printed base, the review's `merge-base` and the SHA in the Codex prompt. | T002 |
