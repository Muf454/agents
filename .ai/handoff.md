# Handoff

## What has been implemented?
Branch `feature/efficiency-batch`: FL-11 (parallel test runner), B3 (Codex review context),
FL-03 (review convergence rule). See `.ai/project-spec.md`, `.ai/current-plan.md`,
`.ai/tasks.md` (T001–T005). The previous batch (FL-01, FL-07, FL-09) shipped in PR #15.

- T001 (FL-11): `tests/run_parallel.py` discovers the same tests as
  `python3 -m unittest discover -s tests`, deals sorted IDs round-robin into
  `AI_TEST_WORKERS` shards (default min(8, CPU count)) and runs each as
  `python3 -m unittest <ids>` with `PYTHONPATH` = the discovery directory. Fails on a
  failing/crashed shard, zero tests, a count mismatch or an import error. `--start-dir`,
  `--collect-only`. One isolation race fixed (a `scripts/` scan skipped `__pycache__`).
  README `## Running the tests`. `.ai/validate` is unchanged (still serial).

- T002 (B3 helper): `review-history` in `scripts/lib/workflow.py` (context only, never authority).
- T003 (B3): `ai-review --base` appends `PREVIOUS ROUNDS:` and `CHANGED SINCE THE LAST REVIEW:
  inspect git diff <last>..<head>` to the implementation review prompt (not plan review or
  re-check); a helper failure warns and reviews without history. `review.md` template explains it.
- T004 (FL-03): the triage prompt gets `This review is round <n>.` and `PREVIOUS ROUNDS:`
  (`review-history --current`); `triage.md` has the convergence rule; `triage-check --fresh`
  requires a same-line `Convergence: <text>` from round 3 (round from the same routine; HTML
  comments ignored). `ai-run --triage` stops with the helper's exact reason.

## Validation run
After T004: targeted `-k convergence` Ran 5 OK; `.ai/bin/ai-check` Ran 253 tests in 112.5s OK.

After T003: targeted `-k review_context -k review_prompt_template` Ran 5 OK; `.ai/bin/ai-check`
Ran 248 tests in 106.6s (8 shards) OK.

After T001 (resumed after the coordinator's flow-chart test fix df0aefd): targeted
`-k parallel_runner -k flow_this_repo` Ran 8 OK; foreground `.ai/bin/ai-check` Ran 236 tests
in 598.682s OK. The serial gate sits right at the 600 s session tool limit, so later tasks
may still time out in-session (gate note in `.ai/tasks.md`).

## Assumptions
- An empty `AI_TEST_WORKERS` means the default; any other non-positive or non-integer value
  stops with "AI_TEST_WORKERS must be a positive integer".

## Flow chart
Flow chart updated (T003): the "Codex reviews the code" node notes the earlier rounds and the
diff since the last review. Flow chart updated (T004): triage node (round number, earlier
rounds, Convergence: line from round 3) and a convergence note.

## Manual testing for the human

### Needs you
None. (The `.ai/validate` switch to `python3 tests/run_parallel.py` was approved and applied
2026-10-07.)

### Covered by automated tests
- Parallel runner passes from the repo root, an unrelated cwd and a relative `--start-dir`
  without `PYTHONPATH`: `test_parallel_runner_all_pass_from_repo_root_and_unrelated_cwd`.
- A failing test exits 1 and prints its traceback:
  `test_parallel_runner_failing_test_prints_traceback`.
- Zero tests exit 1: `test_parallel_runner_zero_tests_fail`.
- A crashing shard (`os._exit`) exits 1 with a count mismatch:
  `test_parallel_runner_crashed_shard_fails_with_count_mismatch`.
- An import error in a test module exits 1: `test_parallel_runner_import_error_fails`.
- `AI_TEST_WORKERS=0`, `x`, `-2` rejected: `test_parallel_runner_rejects_invalid_workers`.
- `--collect-only` matches serial discovery:
  `test_parallel_runner_collect_only_matches_serial_discovery`.
- First review has no PREVIOUS ROUNDS: `test_review_context_first_review_has_no_previous_rounds`.
- Second review gets earlier rounds and the delta:
  `test_review_context_second_review_gets_rounds_and_delta`.
- Plan review and re-check prompts carry neither:
  `test_review_context_plan_review_and_recheck_prompts_have_neither`.
- A failing helper still yields a review: `test_review_context_failing_helper_still_produces_a_review`.
- Template explains the context: `test_review_prompt_template_explains_previous_rounds`.
- Three review rounds through `ai-pipeline --max-fix-rounds 3`: round 2 triage passes without
  `Convergence:`, round 3 stops with "Round 3 triage needs a Convergence: line", the rerun with
  the line completes; prompts say round 1/2/3 and list earlier finding IDs:
  `test_convergence_pipeline_requires_the_line_from_round_three`.
- Interrupted round 3 resumed through `ai-run --triage` reports round 3:
  `test_convergence_interrupted_round_three_resumes_through_ai_run_with_the_same_round`.
- History over the 6000-character cap still counts round 3:
  `test_convergence_history_over_the_cap_still_counts_round_three`.
- Empty, whitespace-only, next-line, commented-out and lowercase `Convergence:` fail; a real
  line passes; plain `triage-check` unchanged: `test_convergence_line_checked_only_with_fresh_from_round_three`.
- Round 2 needs no line: `test_convergence_round_two_needs_no_line`.
- Live handoff with wrapped bullets flags only unnamed bullets (last line), and the fixture
  still flags an unnamed and a lone-backtick bullet:
  `test_manual_testing_wrapped_this_repo_flags_only_unnamed_bullets`,
  `test_manual_testing_wrapped_unnamed_and_lone_backtick_are_flagged_on_the_last_line`.

## Human todos
None.

## Next action
T006 done (merge with master reconciled); a new independent review follows.
