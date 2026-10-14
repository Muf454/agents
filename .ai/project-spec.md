# Spec: Flow batch 3: queue repair (FL-24), fast CI self-check (FL-23), dashboard follow-ups (DB-05, DB-02, DB-03)

## Objective
Stop losing nights to queues that a plan revision left out of order, make the toolkit's own CI
self-check fast and deterministic, and give mission control what it still greps logs for:
fixture-free discovery, PR and review counts, and a blocking wait for changes. Source: vault
`agents-backlog.md`, section "Dashboard follow-ups for mission control" (FL-24, FL-23, DB-05,
DB-02, DB-03). Branch `fix/flow-batch-3`, created from `origin/fix/night-stops` (open PR #27,
not merged). Planned by Claude on 2026-10-14 against 5894c2b. Unattended planning: the
assumptions are recorded below and in `.ai/current-plan.md`, not asked.
Hub decisions respected: AD-4 (small atomic files in `.ai/local/`, no daemon), AD-5 (status
never authorizes), gate files are never edited by a pipeline session.

## Verified against the code (2026-10-14, 5894c2b)
- **FL-24 open.** No reorder exists in `scripts/`. `ai-run --revise-plan` tells the session to
  "append new TODO tasks with new IDs to .ai/tasks.md" (`scripts/ai-run` ~394–395), then runs a
  bare `ai_helper tasks check` (~418). On failure that writes no `last-error` (not `ai_die`), so
  `ai-pipeline` `stop 'plan revision'` (~307) records `stopped during plan revision (see
  terminal)`, which matches none of ai-recover's hard rules (`scripts/ai-recover` ~135–141):
  recovery reruns (the resume finds the dispositions complete and re-runs the same check) and
  escalates after `AI_RECOVER_MAX` (2) attempts. `ai-run --plan` validates the queue after the
  session (~322) and stops on an out-of-order queue. Mission control's workaround
  `~/Projects/wt/plans/sessions/reorder-queue.py` does a DFS order (dependencies pulled up
  before their first dependent) and rewrites prose `Dependencies:` lines to ids; this spec
  rejects prose instead (Zack's brief, 2026-10-14).
- **FL-23 open.** CI (`.github/workflows/self-check.yml`, `timeout-minutes: 40` already applied
  by Zack) runs `./scripts/ai-check` → `.ai/validate` → `tests/run_parallel.py` with
  `min(8, CPUs)` static round-robin shards. In PR #27 run 38356827946 the
  `test_supervised_plan_resume_*_watchdog` tests failed: `tool('ai-recover', …)`
  (tests/test_workflow.py ~3480) runs under `COMMAND_TIMEOUT` (25 s) because `tool()`
  (~1290–1294) gives `PIPELINE_TIMEOUT` only to `ai-pipeline`, although ai-recover execs a
  whole resumed pipeline (plan review → revision → re-review → implementation). Sleeps are
  mocked (`AI_SLEEP`, `AI_NOTIFY_CMD` writes a local file, `gh`/`codex`/`claude` are local
  mocks), so the cost is CPU and I/O: thousands of short processes (bash, python3 helpers,
  git) per pipeline test. Locally `/tmp` is tmpfs; the GitHub runner's is disk. Several tests
  still pass bare literal timeouts (`timeout=10/15/20/25/60/120`, e.g. ~747, ~1272, ~3437,
  ~3940, ~4865, ~5417, ~5504, ~8173) that `AI_TEST_TIMEOUT_SCALE` does not stretch. No
  per-test timing is reported, so nobody knows which tests dominate.
- **DB-05 open.** `dashboard.discover` (`scripts/lib/dashboard.py` ~122–150) lists every
  checkout a live runner process (`/proc/<pid>/cwd`) works in; fixture pipelines of the test
  suite (`/tmp/ai-toolkit-test-*/project with spaces`) qualify. Fixtures use a temp
  `AI_STATE_DIR`, so they are never in the real host registry.
- **DB-02 open.** A run dict (`inspect` ~267–308) has no PR or review fields. The PR URL is in
  `.ai/state.md` (`Next action: Human: test and merge the pull request <url>`, written by
  ai-pipeline ~611) and in the run log (`pull request ready: <url>`, ~612). Review counts are
  the `Finding counts: BLOCKER=n MAJOR=n MINOR=n` line of `.ai/reviews/current.md` and
  `.ai/reviews/plan.md` (`workflow.py` `COUNTS` ~729).
- **DB-03 open.** `ai-dashboard` has `--once`, `--json`, `--all` only (~680–699).
- Nothing in this section is already done; the 40-minute CI job timeout mentioned in FL-23 is
  already in the workflow file.

## Requirements
- **FL-24 queue repair.**
  - `workflow.py tasks reorder` (also `ai-task reorder`) rewrites `.ai/tasks.md` into a stable
    dependency order: tasks keep their file order except that a task's missing dependencies are
    pulled up right before it (depth first, in file order); a valid queue is left byte-identical
    and unwritten. Block text is never changed (headings, `Dependencies:` lines and every other
    line, DONE tasks included); only whole blocks move. Rejected with a clear `Error:` and the
    file untouched: duplicate IDs, a task without exactly one `Dependencies:` line, a
    `Dependencies:` value that is not `none` or task IDs separated by commas (prose), an unknown
    ID, a self-dependency or cycle (`dependency cycle: T003 -> T005 -> T003`), a non-task `## `
    section between two tasks when a move is needed. Atomic replace.
  - Called by the host only on the planning paths: `ai-run --plan` (after `plan-keeps-done`,
    before `tasks check`) and `ai-run --revise-plan` (before its `tasks check`, which covers the
    "dispositions already complete" resume too). Not by `ai-pipeline`'s pre-review queue check,
    `ai-run` implementation or `ai-review`.
  - A queue the host cannot repair, or that is still invalid after the reorder, stops
    `--revise-plan` through `ai_die "Plan revision stage: task queue is invalid: <error>"` and
    `--plan` through `ai_die "Planning: task queue is invalid: <error>"`. `Plan revision stage`
    is an always-escalate pattern in ai-recover, so recovery escalates at once (no rerun).
  - The revision contract asks for new tasks before their first dependent; the host repairs
    the order anyway.
- **FL-23 CI self-check.**
  - The test harness gives every command that runs a pipeline (ai-pipeline, ai-recover) the
    pipeline timeout; every subprocess timeout and time bound in the tests is a named constant
    scaled by `AI_TEST_TIMEOUT_SCALE`; under `CI=true` without an explicit value the scale
    defaults to 2. A timed-out command fails with its captured partial output.
  - `tests/run_parallel.py` reports the slowest tests and per-worker time, and balances work
    dynamically (many small interleaved batches pulled by `AI_TEST_WORKERS` workers) instead of
    fixed shards; it still fails on a count mismatch.
  - Fixture repositories and test temp files avoid needless disk syncs (git `core.fsync`
    off in fixtures; test temp dirs on tmpfs when available), and the slowest tests are made
    cheaper without weakening any assertion. Target: the whole suite well under 10 minutes on a
    4-CPU GitHub runner; verified by the human on the PR's CI run.
- **DB-05.** Runner processes whose environment contains `AI_DASHBOARD_IGNORE=1` are not used
  for discovery (read from `/proc/<pid>/environ`, bounded; unreadable → not ignored). The
  test harness sets it for every fixture it starts. Registered checkouts are unaffected.
- **DB-02.** Each run in `--json` gains `pr` (URL or `''`) and `reviews` (`{'plan': …, 'code':
  …}`, each `{'blocker', 'major', 'minor', 'head'}` or `null`); the details (expanded) view
  shows `pr:` and `reviews:` lines. Read through the existing pinned, bounded readers; the
  counts are informational (not verified against the host binding; the pipeline stays
  authoritative). CI state is not fetched (no network).
- **DB-03.** `ai-dashboard --wait [--since CURSOR] [--timeout S] [--interval S]` blocks until
  a run appears or changes status, stage or observation state, or gets a new notification
  line, then prints `{state_root, cursor, timed_out: false, runs: [changed runs]}` and exits
  0; on timeout prints the same with `timed_out: true`, `runs: []` and exits 1; an invalid
  cursor is a usage error (exit 2). `--since` compares against the previous call's cursor at
  once, so nothing is lost between calls. Read-only like the rest of the dashboard.
- **Docs.** README and `docs/workflow.md` describe each change; the vault flow chart
  (`agents-flow.md`) is updated in the same task for every flow change (FL-24); tasks append a
  dated line to the hub's Log, never tick vault checkboxes.

## Non-goals
No change to `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/permissions.allow`,
`.claude/settings.json` or `.github/workflows/*` (human steps in the handoff). No reorder in
ai-pipeline's own queue check or in implementation sessions. No rewriting of prose
dependencies. No CI status in the dashboard. No dashboard actions or daemon.

## Acceptance
- Offline regression tests per task (names in `.ai/tasks.md`), in the existing styles; existing
  tests pass (the ones changed on purpose are named in the task results).
- `.ai/validate` passes; T004–T006 record measured before/after suite timings.
- README, `docs/workflow.md` and the vault flow chart match the code.
