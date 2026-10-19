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
- T024: `run-manifest task` (read only) prints the session's recorded task; `run-manifest
  timeout-rerun ID` claims the one timeout commit-and-rerun per task (`timeout_reruns`, kept by
  `clear-attempts`, dropped by `start`, a wrong shape invalidates the manifest).
- T025: `ai-recover` — after the hard rules, the attempt budget and the stop leftovers — sees an
  implementation stop `Claude exited 124|137 (` whose recorded task is IN_PROGRESS with a dirty
  checkout, claims `timeout-rerun`, and then commits the work through `commit_validated` (the
  former `commit_and_rerun` body: deps, full gate, checkpoint guard, recovery checkpoint, verify)
  and resumes, without a decision session. A second timeout of that task in the run is ⛔ `timed
  out again after one commit-and-rerun`.
- T026: six `test_timeout_rerun_unchanged_*` tests pin the neighbouring cases (gate fails on the
  partial work, task not marked, non-timeout exit, `AI_AUTO_RECOVER=0`, spent attempt budget,
  only bookkeeping left): all keep today's behaviour. One fix in `ai-recover`: the rule's WHY now
  reads `the T session timed out with uncommitted partial work`, because it also prefixes the
  failing-gate ⛔, which used to say "its partial work passed the full gate; but … fails
  validation". README "Recovery", docs/workflow.md (recovery contract paragraph, one sentence in
  "Interruption, limits, and recovery") and the vault flow chart describe the rule.
- T027: `workflow.py exec-bits` (after `ai_branch` in `ai-run`) gives back the executable bit that
  git records (`100755`) to a tracked script that lost it, after each implementation session; never
  `.ai/bin/`, `.ai/validate` or `.ai/ci-setup`. Four `test_exec_bits_*` tests and a `chmod-tracked`
  mock mode.
- T028: the runner and triage prompts name `chmod +x <path>` as the only chmod form (numeric modes
  such as `chmod 755` are denied) and cover repairing a tracked script whose bit was lost; README
  says the same.
- T029: the plan-revision prompt shows the disposition table header and three example rows
  (`FINDING_CELL` already accepted the `P1 (MAJOR) title` cell, no parser change); three
  `test_finding_cell_*` regressions for the family-budget row and the restart path.
- T030: `tests/run_parallel.py` prints `Progress: d/N batches …` after each batch, a
  `run_parallel: stopped after …` summary on SIGTERM or interrupt, and lists the tests over the
  per-test budget (`AI_TEST_BUDGET`, default 30 s × the timeout scale) after the slowest 15; the list
  never changes the exit code. Five `test_parallel_runner_progress_*` tests; README describes it.
- T031: `ready()` copies a per-process bootstrapped fixture template (`ready_template()`;
  `fresh=True` opts out). Three `test_fixture_template_*` tests (equivalence masks wall-clock stamps).
- T032: audit only. No test runs the full `ai-pipeline` twice merely for setup, so nothing was
  converted (the result lists every audited test and why it stays).

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
After T028 (the last full gate on the branch, parent 01f8197, which includes T027, T029 and T030): `.ai/bin/ai-check` PASS (1002 tests, 634.3 s, run in the background); `-k exec_bits_prompts` 1 OK; `-k prompt` 17 OK; `-k Docs` 3 OK. The T027, T029 and T030 gate blocks were a tool-limit issue (FL-32): mission control ran the full gate on c797cd3 without a tool timeout (1001 tests, 637.5 s, OK). T031: `ai-check` PASS (1001 tests, 633.5 s). T032 changed no code.
After T026: `.ai/bin/ai-check` PASS (986 tests, 630.2 s); `-k timeout_rerun` 12 OK, `-k Docs` 3 OK,
`-k flow_this_repo` 1 OK.
After T025: `.ai/bin/ai-check` PASS (980 tests, 661.3 s); `-k timeout_rerun` 6 OK, `-k recovery` 72 OK.
After T024: `.ai/bin/ai-check` PASS (978 tests, 618.6 s); `-k timeout_rerun_manifest` 4 OK,
`-k limit_relaunch_record` 7 OK. After T023: `-k session_gate_allowance` 5 OK, `-k flow_this_repo` 1 OK,
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
Flow chart updated (T023: vault `agents-flow.md` "Inside one task" (session limit with the gate allowance,
timed host gate); T026: "When something goes wrong" (session timeout on an IN_PROGRESS task: gate →
recovery checkpoint → rerun once per task, else ⛔, before the Claude decision)).

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
  T026 and T033 add theirs (T023's, T026's and T033's are in).

## Next action
T022–T032 are DONE. T033 (docs and handoff audit) is BLOCKED only on its full gate: the foreground
run hit the 600 s tool limit, and its targeted checks pass (see its result). Run `.ai/bin/ai-check`
without a tool limit to finish it. FL-28 to FL-31 are otherwise complete on the branch. Remaining: the human acceptance steps above, then PR review and merge (not done here).
