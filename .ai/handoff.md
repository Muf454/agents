# Handoff

## What has been implemented?
On `fix/flow-batch-7` (from `master` at 1423b60), done so far:
- T022: `workflow.py outcome gate pass|fail|timeout SECONDS` records a host gate run;
  `gate-seconds` prints the largest seconds of this project's last 3 passes (or 0);
  `ai-status --outcomes` skips gate lines (it did not before, for a log of only gate lines).
- T023: `ai-run` times and records every host `ai-check` (`gate pass|fail|timeout`, after
  `ai_guard_verify`); an implementation session's limit is base + min(2 × gate-seconds, base),
  capped by the remaining run time; the `Session:` line shows the breakdown. Triage, plan
  revision and `--plan` keep the plain limit.

The plan for batch 7 was written 2026-10-18 in an unattended planning session. See `.ai/project-spec.md` (scope, what was verified
in the code, assumptions A1–A7), `.ai/current-plan.md` (design) and `.ai/tasks.md` (T022–T033).
T001–T021 are batch 6's DONE tasks (merged in #31). They stay in the queue unchanged because the
host refuses a plan that removes DONE blocks.
- **FL-28** (T022–T026, opus): an implementation session gets room for two measured gate runs
  (from host `gate` outcome lines, at most double the base limit). `ai-recover` commits a
  timed-out IN_PROGRESS task's partial work once per task per run, without a decision session,
  and only when the full gate passes. A second timeout of the same task is ⛔.
- **FL-29** (T027 sonnet, T028 haiku): the template allowlist already has `Bash(chmod +x *)`.
  Left to do: the host restores the executable bit that git records (100755) after a session, and
  the prompts say `chmod +x` is the only form (never `chmod 755`), including for a tracked script
  that lost its bit.
- **FL-30** (T029 sonnet): the parser already accepts `P1 (MAJOR) title` (`FINDING_CELL`,
  `test_finding_cell_*`). The family-budget stop came from an older installed copy. Left to do: a
  regression for the exact row and the restart path, and a full table example in the revision
  prompt.
- **FL-31** (T030–T032 sonnet): progress lines and a stop summary in `tests/run_parallel.py`, an
  over-budget list (30 s × the timeout scale) beside the slowest 15, a shared `ready()` fixture
  template, and an audit that trims redundant pipeline setup runs. No test is weakened.
- T033 (haiku): docs, flow chart and handoff audit.

## Validation run
After T023: `.ai/bin/ai-check` PASS (974 tests, 610.2 s); `-k session_gate_allowance` 5 OK,
`-k timeout` 12 OK, `-k outcome` 86 OK, `-k Docs` 3 OK. `.ai/validate` is unchanged: shell syntax checks, then
`tests/run_parallel.py`. Batch 6's last full gate: 965 tests, about 600 s on this machine.

## Assumptions
- Gate allowance = min(2 × G, session_timeout), where G is the largest of the last 3 passing host
  gate runs of this project. Implementation sessions only. No measurement yet means no change.
- "Once per task" holds per human-started run. It survives resumes (`clear-attempts` keeps it)
  and is dropped by `run-manifest start`.
- A timeout on a TODO task, or with nothing left but bookkeeping, still goes to today's decision
  session.
- FL-31 cannot be profiled (denied), so the speed tasks record before and after `-k` timings and
  convert only provably redundant setup runs. The FL-23 measurement predicts only a small gain
  from the fixture template.

## Flow chart
T023 updated the vault `agents-flow.md` "Inside one task" (session limit with the gate allowance,
timed host gate). T026 (timeout rerun) changes the flow next. T026 sets this line to "Flow chart updated (…)".

## Manual testing for the human

### Needs you
1. (Done: plan committed in 9bc2228 and the run approved.)
2. After merging: run `setup-project --upgrade --apply` here and in raid-planner, family-planner
   and family-budget, so `.ai/bin` gets the new `ai-run` and `ai-recover` and `.ai/prompts` gets
   the new runner, triage and plan-revision wording. Reinstall each watchdog timer
   (`ai-watchdog <checkout> --install-timer --recover`).
3. On the next real run with a ~9-minute gate: check that the `Session:` line shows the allowance
   (`+ …s for two gate runs`) from the second task on, and that a session timeout on an
   IN_PROGRESS task ends in `🔧 … committing its validated partial work once` instead of ⛔.
4. Decide whether CI's `AI_CHECK_TIMEOUT`/job timeout (raised to 3000 s / 55 min in #32) can
   come down after FL-31. The workflow file is a gate file; only you change it.
5. If T031 and T032 report a small gain: profile one slow pipeline test yourself (e.g.
   `python3 -m cProfile -s cumtime -m unittest discover -s tests -k
   extra_fix_round_clean_review_after_it_opens_a_ready_pr`), or allow a profiling command, so a
   follow-up can target the dominant cost (FL-23 follow-up).

### Covered by automated tests
Added by the tasks named (each group runs with `python3 -m unittest discover -s tests -k <group>`):
- `test_gate_time_*` (T022), `test_session_gate_allowance_*` (T023).
- `test_timeout_rerun_manifest_*` (T024), `test_timeout_rerun_recover_*` (T025),
  `test_timeout_rerun_unchanged_*` (T026).
- `test_exec_bits_*` (T027, T028).
- `test_finding_cell_plan_dispositions_incident_row`,
  `test_finding_cell_plan_revision_restart_records_decorated_rows`,
  `test_finding_cell_prompts_show_the_table` (T029).
- `test_parallel_runner_progress_*` (T030), `test_fixture_template_*` (T031).

## Human todos
- After merge: the upgrades and timer reinstall above; tick FL-28 to FL-31 in the vault backlog
  (sessions never tick it).
- Vault: this planning session could edit only `.ai/` files, so it left no hub Log line. T023,
  T026 and T033 add theirs.

## Next action
T022 is DONE; T023 is next (or any task without dependencies: T024, T027, T029, T030, T031). FL-28 runs
T022 → T023 and T024 → T025 → T026. T032 waits for T030 and T031. T033 comes last.
