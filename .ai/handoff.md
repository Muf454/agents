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

## Validation run
After T001 (resumed after the coordinator's flow-chart test fix df0aefd): targeted
`-k parallel_runner -k flow_this_repo` Ran 8 OK; foreground `.ai/bin/ai-check` Ran 236 tests
in 598.682s OK. The serial gate sits right at the 600 s session tool limit, so later tasks
may still time out in-session (gate note in `.ai/tasks.md`).

## Assumptions
- An empty `AI_TEST_WORKERS` means the default; any other non-positive or non-integer value
  stops with "AI_TEST_WORKERS must be a positive integer".

## Flow chart
Flow unchanged by T001 (the gate still runs the serial suite until Zack switches
`.ai/validate`).

## Manual testing for the human

### Needs you
1. Parallel runner timing (precondition for the gate switch): on the host, from the repo
   root, run `python3 tests/run_parallel.py` three times. Expected each time: `OK`, a
   `Ran N tests` line where N equals `python3 tests/run_parallel.py --collect-only`
   (and the serial `Ran N tests`), finishing in under 200 s. Record counts and wall times
   in `.ai/run-log.md`.
2. Then approve and apply switching `.ai/validate` to `python3 tests/run_parallel.py`, and
   time one `.ai/bin/ai-check` run.

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
- Further scenarios are added by the remaining tasks.

## Human todos
- Run the three timed parallel runs and approve the `.ai/validate` switch (see Needs you).

## Next action
Runner continues with T002 (review history helper).
