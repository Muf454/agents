# Review dispositions (Claude)

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

## Plan review round 1 (outcome follow-ups)

Claude fallback plan review (Codex usage limit), plan digest a62a92a1, HEAD 3ec6936, 2026-10-08: BLOCKER 0, MAJOR 1, MINOR 5. All accepted (plan revision 2).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 blanket `try` drops all coverage on the first non-covered row | accepted | Confirmed: `git()` is `check_output` (`workflow.py:27-28`), so `merge-base --is-ancestor` exit 1 raises; this repo's `fallback-log.md` already holds rows from merged branches whose base is older than any later Codex base. T004 now uses a pure helper `catchup_covers(text, base, head, cwd=None)` that judges each row on its own (per-row `CalledProcessError` handling for `rev-parse`; ancestry via `subprocess.run(...).returncode`, 0 yes / 1 no / else skip, as `recheck_preflight` does at `workflow.py:1269-1271`); the outer `try` covers only reading `current.md`/the log and the header. New mixed-row unit test on one log asserts exactly the covered entries. Spec R4 states the per-row rule. | T004 |
| P2 row parsing (`plan`/`recheck` bases, escaped `\|`) | accepted | Confirmed: `ai-review` passes the literals `plan`/`recheck` as base (`ai-review:231,264`) and `cell()` escapes `\|` (`workflow.py:1971`). T004: split on unescaped pipes, exactly 8 cells, mode/branch/HEAD/base from cells 2-5; `plan`/`recheck` compared as strings before any git call; only `^[0-9a-f]{7,40}$` cells are resolved. The unit test includes an escaped reason and a ref named `plan`. | T004 |
| P3 end-to-end test conflicts with `stamp verify`; other-branch fixture | accepted | Confirmed: `ai-review:284` runs `stamp verify`, whose fingerprint (`workflow.py:526-546`) hashes everything except state/handoff/run-log/reviews. The end-to-end test reruns `ai-check` after the further code commit; later-base, other-branch, unknown-row and plan-row cases move to the helper unit test on a scratch repo, loaded like `recheck_module`. | T004 |
| P4 colour tests inherit host `NO_COLOR`/`PYTHON_COLORS` | accepted | Confirmed: `ParallelRunnerTest.setUp` copies `os.environ` (`tests/test_workflow.py:4669`). Each subtest removes `NO_COLOR`, `FORCE_COLOR`, `PYTHON_COLORS` before setting its own; the mutation check is recorded with the Python version (fails only on 3.14+). | T001 |
| P5 first-time-pass denominator for attempt-less rows | accepted | T002 defines one attempt-1 row per task key (first `attempt == 1` row, else the first row in file order; x from that row's `first_pass`) and adds an old-line test expecting `0/1`. | T002 |
| P6 re-check table grouping and sort order | accepted | T003 groups by (`reviewer`, `model`, missing → `default`), sorts with `key=str` like "Reviews by reviewer", and does not print `reviewed_head`. | T003 |

## Plan review round 2 (outcome follow-ups)

Claude fallback plan review (Codex usage limit), HEAD 5626730: BLOCKER 0, MAJOR 1, MINOR 4. Recorded late (round 3 P2); P1, P2, P5 were applied in plan revision 3; P3 and P4 were left unaddressed in revision 3 and are now deferred with CU-2 (plan revision 4).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 T001 env line has no test; mutation check unsatisfiable | accepted | Confirmed: `summary()` strips escapes, so the passing-suite cases cannot see the `PYTHON_COLORS=0` line. T001 adds a failing-suite test with only `PYTHON_COLORS=1` asserting no `\x1b[` in the echoed shard output (`run_parallel.py:106`), keeps the `summary()` unit test for the stripping, and records two mutation checks with the Python version. | T001 |
| P2 `rejected_rows()` returns tuples, not a dict | accepted | Confirmed (`workflow.py:1250-1253`). T003 now builds `{finding: level for finding, level, _ in rejected_rows()[1]}` and the counting helper takes `(answers, levels)`. | T003 |
| P3 coverage rule leaves reviews pending after a master merge or rebase | deferred | Real (`.ai/run-log.md:108` shows master merged into a feature branch), but it is the CU-2 coverage rule, which is dropped from this batch by the convergence rule after round 3 raised it again as P1. Risk: none for this batch; the report keeps listing every Claude review as pending, as today. Carried to the CU-2 design question. | — |
| P4 re-check row covered while its parent code row is not | deferred | Same area and reason as P3 (CU-2 dropped). | — |
| P5 existing report assertion would depend on wall-clock minutes | accepted | Confirmed (`tests/test_workflow.py:2640` stops before minutes). T002 asserts the row prefix up to the first-time-pass cell. | T002 |

## Plan review round 3 (outcome follow-ups)

Claude fallback plan review (Codex usage limit), plan digest d85a5ce7, HEAD 55e5382, 2026-10-09: BLOCKER 0, MAJOR 1, MINOR 4. Convergence: the MAJOR is the third round of findings on T004's coverage rule (rounds 1, 2, 3), in advisory telemetry, so CU-2/T004 leaves this batch instead of being patched again (plan revision 4). The hand-written `## Codex catch-up` section in `.ai/reviews/fallback-log.md` stays the record; open question recorded in `.ai/current-plan.md` "Deferred: CU-2".

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 coverage rule incomplete after a master merge (carried from round 2 P3) | deferred | Real (same evidence as round 2 P3), but CU-2/T004 is dropped from this batch by the convergence rule. Risk: Claude-only reviews stay listed as "Codex catch-up pending" in `ai-status --outcomes`, which is today's behaviour; nothing is hidden. The exact-containment rule proposed here is the leading candidate for the later CU-2 batch. | — |
| P2 round 2 dispositions missing; plan revision not bumped | accepted | Confirmed. Round 2 section added above; `current-plan.md` now says revision 4 with this round. | — |
| P3 re-check row vs parent code row (carried from round 2 P4) | deferred | Only in T004's rule; deferred with CU-2, reason as P1. | — |
| P4 vault flow-note edit may be denied in an unattended run | deferred | Only T004 edited the vault; T001–T003 leave the flow unchanged and write nothing outside the checkout. Deferred with CU-2; the later batch must plan for `--knowledge-dir` or a handoff fallback. | — |
| P5 ambiguous "number of Claude reviews covered" | deferred | Only in T004's report section; deferred with CU-2. | — |

Also taken from the round 3 notes: T001 sets the test env on `self.env` before `self.runner()` copies it.

## Plan review round 4 (outcome follow-ups)

Claude fallback plan review (Codex usage limit), plan digest 02a8c7d2, HEAD 828c4fe, 2026-10-09: BLOCKER 0, MAJOR 1, MINOR 2. All accepted (plan revision 5).

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| P1 moving re-checks to their own table can silently drop Claude re-checks from "Codex catch-up pending" | accepted | Confirmed: `outcomes_report` builds `fallback` from the same `reviews` list inside `if reviews:` (`workflow.py:2116-2133`), and the only catch-up assertion counts `'code HEAD'` (`tests/test_workflow.py:2647-2648`). Applied as written: T003's notes say the catch-up list is built from all review lines (plan, code, recheck), independent of the table split and of whether any plan/code review exists; the JSONL report test gets a `claude-fallback` recheck line asserted under "Codex catch-up pending" and absent as `\| recheck \|` from "Reviews by reviewer", plus a re-check-only JSONL; new acceptance criterion "Claude re-checks remain listed under Codex catch-up pending". Spec R3 notes it. | T003 |
| P2 attempt-1 rule undefined for an old attempt-less row followed by a new row | accepted | Confirmed: `outcome` numbers attempts by counting all earlier lines of the task (`workflow.py:2056-2058`), so such a task has no `attempt == 1` row. T002 now takes a task's first row in file order (files in argument order) as its attempt-1 row; the T009 old-line expectation is unchanged, and a mixed T010 fixture (old row, then `attempt` 2 on opus) expects `0/1 (0%)` under default. Spec R2 notes it. | T002 |
| P3 T003 targeted filter skips the pipeline re-check paths | accepted (amended) | Confirmed, but the suggested `-k outcome -k recheck` still misses dispute tests that run a re-check without "recheck" in their names (`test_disputed_findings_all_withdrawn_open_a_normal_pr`, `..._one_upheld_makes_a_draft_...`, `tests/test_workflow.py:3590,3603`). T003 validation is `-k outcome -k recheck -k disput`. | T003 |
