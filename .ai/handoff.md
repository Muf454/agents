# Handoff

## What has been implemented?
T001 DONE (2026-10-14): `workflow.py tasks reorder` and `ai-task reorder`. T002 DONE
(2026-10-14): `ai-run --plan` and `ai-run --revise-plan` run the reorder before `tasks check`;
an unrepairable queue stops with `Planning: / Plan revision stage: task queue is invalid`.
T011 DONE (2026-10-15): `workflow.py revision-queue-repair`, called by `ai-run --revise-plan`
and `ai-pipeline` before their queue checks, repairs an interrupted revision's uncommitted
out-of-order queue so the resume records the revision without a second session.
T003 DONE: scaled test timeouts (`tests/timeouts.py`). T004 DONE (2026-10-15):
`tests/run_parallel.py` runs interleaved batches (6 per worker) from a shared queue and prints
the 15 slowest tests, the summed test time and the worker busy range (Python 3.12+).
T005 DONE (2026-10-15): fixture git has `core.fsync=none`/`gc.auto=0`; `run_parallel.py` uses an
exec-probed `/dev/shm/ai-tests-*` TMPDIR (`AI_TEST_TMPFS=0` off; test-only `AI_TEST_TMPFS_DIR`).
T006 removed from the batch (BLOCKED: the runner may not run profiling commands) and deferred to
the vault backlog as the FL-23 follow-up; no test was changed for it. T007 DONE (2026-10-15): dashboard
discovery skips a runner whose `/proc/<pid>/environ` holds `AI_DASHBOARD_IGNORE=1` (bounded,
non-blocking regular-file read; registered checkouts still listed); `ToolkitTest` sets it.
T012 DONE (2026-10-15, review M2): `tasks reorder` keeps ordinary `## ` sections before the first
task as preamble; only a section between two tasks blocks reordering.
Branch `fix/flow-batch-3` (from `origin/fix/night-stops`, open PR #27, at
5894c2b) plans flow batch 3 (2026-10-14, Claude planning session), in priority order:
- T001–T002 FL-24: `workflow.py tasks reorder` / `ai-task reorder` (stable dependency order,
  block text never changed; cycles, unknown IDs and prose in `Dependencies:` rejected), run by
  the host after `ai-run --plan` and `ai-run --revise-plan`; an unrepairable queue stops with
  `Plan revision stage: task queue is invalid: …`, which recovery escalates at once.
- T011 FL-24: an interrupted revision's uncommitted out-of-order queue is repaired before the
  pipeline's and ai-run's queue checks (guarded `revision-queue-repair`), so recovery resumes
  without a second revision session.
- T003–T006 FL-23: pipeline-running test commands (`ai-recover` included) get the pipeline
  timeout; every test bound scaled (`AI_TEST_TIMEOUT_SCALE`, default 2 under `CI=true`);
  run_parallel timing report and balanced batches; no git fsync in fixtures and test temp dirs
  on tmpfs; the slowest tests made cheaper (measured).
- T007 DB-05: the dashboard ignores runners started with `AI_DASHBOARD_IGNORE=1` (set by the
  test harness).
- T008 DB-02: `pr` and `reviews` (plan/code finding counts) in `ai-dashboard --json` and the
  details view.
- T009 DB-03: `ai-dashboard --wait [--since CURSOR] [--timeout S]`.
- T010: docs/handoff audit.
See `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`.

## Validation run
T001: `.ai/bin/ai-check` passed (624 tests). T002: see the task result. T011: passed (641 tests). T004: passed, baseline `Ran 648 tests in 381.8s (48 batches on 8 workers)`, test time 2841.7 s on 16 CPUs (details in the T004 result). T004–T006 record the suite timings (baseline and after). T007: passed, `Ran 667 tests in 371.4s`. T009: passed (679 tests). T010: see the task result
(final gate run after the docs audit). T012: passed (681 tests).

## Assumptions
- Prose in `Dependencies:` is rejected, not rewritten; reorder runs only on the planning and
  plan-revision paths (ai-pipeline's own queue check still stops on a committed out-of-order
  queue).
- Reorder is depth first (prerequisites pulled up before their first dependent), like mission
  control's `reorder-queue.py`; a valid queue is left untouched.
- `CI=true` defaults the test timeout scale to 2; an explicit `AI_TEST_TIMEOUT_SCALE` wins.
- DB-02 counts are read from the reports, not verified against the host binding (the reviewed
  HEAD is shown); no CI status (no network).
- DB-03 exit codes: 0 change, 1 timeout, 2 usage/cursor error; polling every 2 s by default.
- The fixture marker is `AI_DASHBOARD_IGNORE=1` (environment), not a temp-path rule.

## Flow chart
Flow chart updated (T002, 2026-10-14): `~/zWiki/zWiki/20 Projects/agents/agents-flow.md` Plan
box and the revision node ("Scripts: host reorders the queue (dependencies first), commit +
host record"), the plan stop ("queue cycle / unknown ID / prose"), the recovery hard-rules box
("also queue invalid after a revision"), a "Host queue repair" bullet; `updated:` 2026-10-14;
hub Log line.
Flow chart updated (T011, 2026-10-15): recovery box "interrupted revision: host repairs the
queue first" and an "Interrupted revision with an out-of-order queue" bullet; `updated:`
2026-10-15; hub Log line. T003–T009: flow unchanged (unless a task notes a dashboard
description in the chart).

## Manual testing for the human

### Needs you
1. CI time: on this PR's GitHub Actions run, the self-check finishes well under 10 minutes
   (and green). Compare with PR #27's ~24 min; note the runner's CPU count from the log
   (`Ran … (B batches on N workers, …)` line, `Test time:` and the slowest-tests list).
2. A real supervised plan revision that adds a prerequisite task at the end
   (e.g. a scratch project, `AI_SUPERVISE=1`, a plan review with one MAJOR finding): the run
   continues with `Task queue reordered` in the log and no ⛔; the committed queue has the new
   task before its dependent.
3. While the agents test suite runs (`bash .ai/validate` in one tmux window), `ai-dashboard`
   in another shows no fixture cards (`ai-toolkit-test-*` in the default temp dir, or
   `ai-tests-*` under `/dev/shm`); your real pipelines are still listed.
4. `ai-dashboard --json` on a checkout with an open PR shows its URL and the last plan/code
   review counts; `ai-dashboard --wait --timeout 600` returns when a running pipeline moves
   to its next stage, and `--since <cursor>` loses nothing between two calls.

### Covered by automated tests
Each group below is a name prefix; `python3 -m unittest discover -s tests -k <group>` runs its tests.
- `test_queue_reorder_*` (T001), `test_queue_repair_*` (T002), `test_queue_recovery_*` (T011).
  A `## Context` section before the first task is kept (T012):
  `test_queue_reorder_preamble_sections_are_kept`, `test_queue_repair_planning_preamble_section_reorders`.
- `test_test_harness_timeouts_*` (T003), `test_parallel_runner_*` (T004), `test_fixture_io_*` (T005).
  `test_fixture_cache_*` (T006) was not added: T006 is deferred.
- `test_dashboard_ignore_*` (T007): `test_dashboard_ignore_marked_runner_unless_registered`,
  `test_dashboard_ignore_other_environments_are_discovered`, `test_dashboard_ignore_environ_reader`,
  `test_dashboard_ignore_real_processes`, `test_dashboard_ignore_fixture_pipeline_is_hidden`; the
  watchdog forwarding it is in `test_watchdog_recover_starts_ai_recover_after_a_crash`.
- `test_dashboard_pr_review_*` (T008): `_url_sources`, `_counts_and_heads`, `_unsafe_entries`,
  `_json_every_run`, `_expanded_lines`.
- `test_dashboard_wait_*` (T009).

## Human todos
- Deferred FL-23 follow-up (T006, cheaper slowest tests): profiling needs commands the runner may
  not run; the notes and measurements are in the vault backlog (FL-23). Decide whether to run it
  by hand or as a supervised task.
- Merge order: PR #27 (`fix/night-stops`) first; then rebase or retarget this branch's PR onto
  master.
- Optional CI workflow change (gate file `.github/workflows/self-check.yml`, yours to edit):
  set `env: AI_TEST_TIMEOUT_SCALE` only if 2 (the `CI=true` default) proves wrong; you may
  lower `timeout-minutes` from 40 once the run time is confirmed.
- Other projects: `setup-project --upgrade --apply` so `.ai/bin` and `.ai/prompts` get the
  reorder, the revision prompt sentence and the dashboard changes.
- Mission control: retire `~/Projects/wt/plans/sessions/reorder-queue.py` after this merges
  (use `ai-task reorder`; it rejects prose dependencies instead of rewriting them), and switch
  its watcher to `ai-dashboard --wait`.
- Vault: backlog status lines for FL-23, FL-24, DB-02, DB-03, DB-05 (sessions do not tick
  them).

## Next action
T001–T005 and T007–T012 are DONE (T006 deferred, see Human todos). Review fix T013 (N4, N5) is
next; then another independent review. Human afterwards: the checks under
"Needs you", the merge order and the PR review.
