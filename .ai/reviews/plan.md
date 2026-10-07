<!-- Plan review of plan digest fdb666135367bd1d36c6cab66b3abf92b19658423752316c098905b9622d815d; saved 2026-10-07T19:20:35Z. -->

> **Reviewer: Claude fallback (claude-fable-5-1, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

I've traced every task against the code and have enough for the review. No file writes were needed; the one timing probe (two full mock pipeline runs) completed in about 6 s each, so the loop tests fit the fixture's 25 s per-command limit.

# Plan review — FL-04 bounded supervisor (revision 2)

Overall verdict: REVISE in one small place before unattended implementation. Revision 2 answers round 1 well: the task order is implementable at each checkpoint, host state is the authority everywhere it matters, and the model lines fit the risk. One ordering gap in the plan-revision stage would miscount or mis-model a resumed revision; the rest are contract clarifications that would otherwise cost implementation time or produce needless human stops.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=7

Reviewed HEAD: `dfc03c8e10d35d538bce5a73b7bb3aa2f794b561` (clean worktree). All findings are traced from the plan text against the current source; none required a probe beyond timing the existing pipeline tests.

## BLOCKER findings

None.

## MAJOR findings

- P1: The plan-revision stage reserves after `stage-set` and its resume path neither reserves nor chooses the round's model. (demonstrated by trace)

  **Location:** `.ai/tasks.md:193` (T007: "else stage-set, `revision-reserve`, model ..., run the stage"), `.ai/tasks.md:165` (T006: `complete_plan_stage` runs `ai-run --approved --revise-plan --since START --host-budget` with no model and no reservation), `.ai/current-plan.md:20` ("before the stage starts").

  Two consequences. First, a crash between `stage-set` and `revision-reserve` leaves an open stage with no reservation; on resume the start dispatch runs `complete_plan_stage`, which completes the revision without ever reserving it, so `revision-count` ends one below the real number and the run gets one extra revision. The existing precedent reserves first: `scripts/ai-recover:65` reserves the attempt "before anything that can be interrupted", and T009 itself orders "reserve ... then triage". Second, `complete_plan_stage` on the start path passes no `--model`, so T005's default (`opus`) applies; a crash during a round ≥ `AI_SUPERVISE_ESCALATE_ROUND` revision resumes on `opus` instead of the escalation model. T008's crash points as listed would not detect either (they kill around the session's commit, not between the two host writes, and nothing says the crash tests run at round 3).

  Related wording in T006: "`committed` iff a record commit is in START..HEAD and the tree is clean, else `pending`" makes a dirty tree after the counted commit `pending`, which re-runs `ai-run --revise-plan` and writes a second host commit and `plan-revisions` record for the same report. The triage analog fails closed instead (`scripts/lib/workflow.py:1209-1210`).

  **Plan change:** In T007 call `revision-reserve DIGEST` before `stage-set`, and in T006 have `complete_plan_stage` call it again (idempotent) before launching `ai-run`. Store the chosen model in the stage record at `stage-set` (or recompute it in `complete_plan_stage` from `plan-rounds current` and the manifest's `AI_SUPERVISE_ESCALATE_*`), so a resume uses the same model; assert it in a T008 test that crashes a round-3 revision. Make `stage-verify` fail on a dirty tree after the record commit, as triage does. Add "crash between stage-set and reserve" to T008's crash list with the expected `revision-count` 1.

## MINOR findings

- P2: `plan-rounds` has no base, so a reused branch name inherits rounds from merged history. (suspected, high confidence)

  **Location:** `.ai/tasks.md:80` ("records reachable from HEAD"; legacy init "from exact-subject commits in the branch history").

  Records are per branch name (`binding_dir()/plan-rounds-<hash>.json`). After `feature/x` is merged and deleted, a new `feature/x` created from master reaches the old commits, so the old records count, round numbering starts above 1, and Convergence and the escalation model apply from the first review. `fix-rounds` avoids this with `count BASE` restricted to `BASE..HEAD` (`scripts/lib/workflow.py:1486-1495`); the pipeline already has `base_sha`. The legacy-init range is also unspecified.

  **Plan change:** Give `plan-rounds count|current` and the legacy init a `BASE` argument (the pipeline's `base_sha`, `ai-review --plan` by hand uses `merge-base` with the default base or `--base`), count only records in `BASE..HEAD`, and add a test with a merged-then-recreated branch name.

- P3: A crash between the plan-review host commit and `plan-rounds record` turns into a human stop. (demonstrated by trace)

  **Location:** `.ai/tasks.md:79-80` (`current` "fails when plan.md's digest is not the last reachable record"), `.ai/tasks.md:191`.

  On resume the review is `current` with no revision record, so the loop goes straight to the BLOCKER/MAJOR branch, `ai-run --revise-plan` requires `plan-rounds current`, that fails, and the "Plan revision stage" pattern escalates. The triage path survives the same window because `fix-rounds record` is re-run from `ai-run --triage` on completion (`scripts/ai-run:227-230`).

  **Plan change:** Make the pipeline (and `ai-review --plan`) call `plan-rounds record` idempotently on every pass for the newest commit with the host subject whose committed `plan.md` equals the current verified report, before deciding anything; or let `plan-rounds current` record such a commit itself. Add this window to T008's crash list.

- P4: The dispositions-section contract is underspecified for two resume shapes and for a second hand-run revision. (demonstrated by trace)

  **Location:** `.ai/current-plan.md:41-42` ("everything above it byte-identical to the file at the stage start"), `.ai/tasks.md:107-108`, `.ai/tasks.md:134`.

  Hand-run `ai-run --revise-plan` without `--since` uses `since=HEAD`; after a session that committed its rows and crashed before the host commit, the file at START already contains the section, so "above the header" cannot equal the whole START file and the T005 acceptance "an uncommitted but complete section is recorded without a second session" fails. When the file did not exist at START, the host preamble (title and comment) sits above the header with nothing to compare against. Separately, a second hand-run `--revise-plan` for the same report reuses the header, passes the check, and writes a second allow-empty host commit and record.

  **Plan change:** Define the check as: text above the current header equals START's content above the same header when START has it, else the whole START file, else the host preamble. Make `ai-run --revise-plan` refuse when a `plan-revisions` record exists for the current report ("already revised; review again"). Add both resume shapes to T005's tests.

- P5: The test fixture's default for `AI_SUPERVISE` is undecided, and existing tests assume today's stops. (demonstrated)

  **Location:** `tests/test_workflow.py:391` (`setUp` sets `AI_AUTO_RECOVER='0'` because "recovery has its own tests"), `tests/test_workflow.py:1560-1593` (`test_pipeline_plan_review_gates_implementation`, `test_plan_review_is_bound_and_tracks_the_whole_tree` expect the plan stop), `tests/test_workflow.py:1443-1449` and `2593` (malformed and counts-lie reviews).

  With the spec default `AI_SUPERVISE=1` the plan-MAJOR tests would launch a revision session the mock Claude rejects (`assert 'RUNNER CONTRACT' in prompt or 'TRIAGE CONTRACT'`), and malformed-review tests would get a retry call. T007 and T010 would have to rewrite unrelated tests, and the acceptance lines "existing tests unchanged" (T002, T006) become ambiguous.

  **Plan change:** T001 sets `AI_SUPERVISE='0'` in `ToolkitTest.setUp` with the same comment pattern; supervised tests opt in per call. Note in T007 that the mock Codex needs a once-MAJOR plan mode (`MOCK_CODEX_PLAN=major-once`) beside the always-MAJOR one.

- P6: `AI_RUN_BUDGET` is not wired like the other settings, and the validated values are not exported to children. (demonstrated by trace)

  **Location:** `.ai/tasks.md:52` (T002: "init the budget at a human start from `AI_RUN_BUDGET`"), `.ai/tasks.md:21-24` (T001's key lists and the identity test), `.ai/tasks.md:273` (T010: `ai-review` reads `AI_SUPERVISE`).

  `ai_config` reads only enumerated keys (`scripts/lib/common.sh:37`), so `AI_RUN_BUDGET` in the user config is ignored; adding it to `ai_config` but not to `RUN_SETTINGS` breaks T001's list-identity test, while adding it to `RUN_SETTINGS` is pointless because the total is already in the manifest. `ai_supervise_settings` "sets shell variables"; unless exported, `ai-review` and `ai-run` children see the raw or unset value.

  **Plan change:** State that `AI_RUN_BUDGET` is read from config and environment, validated in `ai_supervise_settings` (`^[1-9][0-9]{0,6}$`), captured only as the manifest budget total, and explicitly excluded from the identity test. Have `ai_supervise_settings` export the four `AI_SUPERVISE*` values and make `ai-review` and `ai-run` call it too (or validate on read).

- P7: Budget exhaustion inside `ai-run --host-budget` goes through a recovery session before the pipeline's own stop. (demonstrated by trace)

  **Location:** `.ai/tasks.md:50-52`, `scripts/ai-run:143` ("Run time limit reached; checkpoint and resume later."), `scripts/ai-recover:102-106`.

  Between sessions `remaining_time` ≤ 0 makes `ai-run` die with the existing message, which is not an escalate pattern, so `AI_AUTO_RECOVER=1` spends one Claude recovery session whose `rerun` then hits the pipeline's `run-budget remaining` check and stops. A tiny grant (say 30 s) also starts a Claude session that the timeout kills immediately.

  **Plan change:** Under `--host-budget`, phrase the limit message as `Run budget exhausted (used U of T s)` and treat a grant below a floor (e.g. 60 s) as exhausted in `run-budget open`; add both to T002's tests (no `recover-calls`, no `mock-invocations`).

- P8: Hardening of the needs-human stop text and the revision session's tool list. (suspected)

  **Location:** `.ai/tasks.md:194` (stop message built from `--questions`), `.ai/tasks.md:136` (`claude_session` allowlist), `scripts/ai-run:154` (`--tools Read,Glob,Grep,Edit,Write,Bash`).

  The questions are model output written to `.ai/local/last-error` and a notification; `ai-recover` reads last-error with `tr '\n' ' '` and the notification command gets it as an argument, so length and newlines should be bounded like `recover_decision` does (`scripts/lib/workflow.py:1666`). The revision session keeps `Write` in `--tools` and relies on `dontAsk` denials alone; dropping it costs nothing.

  **Plan change:** Cap each question (whitespace-collapsed, ~300 chars, at most a few questions) in `--questions`; pass `--tools Read,Glob,Grep,Edit,Bash` for `--revise-plan` and assert it from the mock's args in T005.

## Missing coverage

- Checked against the checklist: lock order (one pipeline per checkout via `ai_lock`; host files written with `atomic`, no new lock), irreversible operations (new host records are append-only JSON, commits are allow-empty host commits, nothing deletes), stale async results (crash windows: P1, P3), data hidden from views (`plan-history` shows only rounds before the current one and only this branch's records: acceptable). Account deletion, tenant isolation, main/alt identity and attribution columns do not apply.
- T008 lists crash points around the session's commit only; add the two host-write windows from P1 and P3 and a round-3 crash for the model check.
- T009's trend test should include a run where round 1 was triaged by the old toolkit (legacy bare hash) and rounds 2–3 carry counts, to pin "insufficient history" versus "falling" at the boundary.
- T010 should assert that the retried review's second `run_review` still fails the `unchanged` checkout check (the `mutates` mock on the second call), not only on the first.

## Security concerns

- The revision allowlist is the right boundary and lands on `opus` (T005). `.claude/settings.json` holds only deny rules, so `--setting-sources project` cannot widen it; the post-session scope check and the byte-identical `plan.md` check give defense in depth. `Bash(git commit *)` still permits `--amend` of commits after START, as in triage today; the scope check covers the resulting tree, so no new exposure.
- `python3 -m unittest *` survives the review-style filter and can import arbitrary modules; the revision session cannot create files outside the record set, so the exposure matches the existing reviewer allowlist and is not new.

## Validation observed

- Clean worktree at the scoped HEAD; `.ai/validate` runs `bash -n` on all scripts and `tests/run_parallel.py` (same discovery as serial), so every task's `.ai/bin/ai-check` line is a real gate.
- Timed three existing pipeline tests including two full mock runs: 17.7 s total, about 6 s per run, so the supervised-loop tests (up to three revisions and four plan reviews) fit the fixture's 25 s per-command timeout with margin.
- Not run: no new code exists to probe; the findings above are traced from the plan text against `scripts/ai-pipeline`, `scripts/ai-run`, `scripts/ai-recover`, `scripts/ai-review` and `scripts/lib/workflow.py` at this HEAD.
