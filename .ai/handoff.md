# Handoff

## What has been implemented?
Nothing yet. Branch `fix/flow-batch-3` (from `origin/fix/night-stops`, open PR #27, at
5894c2b) plans flow batch 3 (2026-10-14, Claude planning session), in priority order:
- T001–T002 FL-24: `workflow.py tasks reorder` / `ai-task reorder` (stable dependency order,
  block text never changed; cycles, unknown IDs and prose in `Dependencies:` rejected), run by
  the host after `ai-run --plan` and `ai-run --revise-plan`; an unrepairable queue stops with
  `Plan revision stage: task queue is invalid: …`, which recovery escalates at once.
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
None yet for this batch. T004–T006 record the suite timings (baseline and after).

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
Flow chart: T002 changes the flow and updates `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`
in the same task (Plan box and plan-revision path: "host reorders the queue (dependencies
first); cycle / unknown ID / prose → ⛔"; recovery hard rules: "queue invalid after a
revision"; `updated:` bumped; hub Log line). If the vault edit is denied, the task lists it
here as PENDING. T003–T009: flow unchanged (unless a task notes a dashboard description in the
chart).

## Manual testing for the human

### Needs you
1. CI time: on this PR's GitHub Actions run, the self-check finishes well under 10 minutes
   (and green). Compare with PR #27's ~24 min; note the runner's CPU count from the log
   (`Ran … (N workers …)` line and the slowest-tests list).
2. A real supervised plan revision that adds a prerequisite task at the end
   (e.g. a scratch project, `AI_SUPERVISE=1`, a plan review with one MAJOR finding): the run
   continues with `Task queue reordered` in the log and no ⛔; the committed queue has the new
   task before its dependent.
3. While the agents test suite runs (`bash .ai/validate` in one tmux window), `ai-dashboard`
   in another shows no `/tmp/ai-toolkit-test-*` cards.
4. `ai-dashboard --json` on a checkout with an open PR shows its URL and the last plan/code
   review counts; `ai-dashboard --wait --timeout 600` returns when a running pipeline moves
   to its next stage, and `--since <cursor>` loses nothing between two calls.

### Covered by automated tests
Filled in by the tasks (T010 checks it): `test_queue_reorder_*` (T001), `test_queue_repair_*`
(T002), `test_test_harness_timeouts_*` (T003), `test_parallel_runner_*` (T004),
`test_fixture_io_*` (T005), `test_fixture_cache_*` (T006, if added),
`test_dashboard_ignore_*` (T007), `test_dashboard_pr_review_*` (T008),
`test_dashboard_wait_*` (T009).

## Human todos
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
Implement T001–T010 in queue order. Human afterwards: the checks under "Needs you", the merge
order and the PR review.
