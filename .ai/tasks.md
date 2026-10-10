# Task queue

Edit `scripts/`, `templates/`, `tests/`, `README.md` and `docs/` only. Never edit `.ai/bin`,
`.ai/prompts`, `.ai/validate`, `.ai/ci-setup`, `.ai/permissions.allow`, `.claude/settings.json`
or `.github/workflows/*` (gate files; needed gate changes are human steps in `.ai/handoff.md`),
and never edit the Obsidian vault (the handoff's "## Flow chart" section lists the flow-chart
changes for mission control). Source: vault `agents-backlog.md`, "Stop analysis 2026-10-07"
(FL-18, FL-19, FL-21) and "Dashboard follow-ups" (FL-22, DB-04), queued by Zack on 2026-10-09.
Line references are at 744827a and verified by the planner; re-check them before editing.
Every behaviour change gets an offline regression test in the existing style; every task
leaves `.ai/bin/ai-check` passing and updates README.md / `docs/workflow.md` where the
behaviour it changes is described.
Gate note: `.ai/validate` runs the shell syntax checks and then `tests/run_parallel.py`
(parallel shards, about 4–6 min), inside the 600 s Bash tool limit. Should `.ai/bin/ai-check`
still time out in the session, run the task's targeted tests, record the timeout in the
result, and leave the full gate to the host's post-task `ai-check`. Tests with time bounds
run inside parallel shards: assert "returns within N s" with generous bounds, never a tight
duration.
No new executable file in this batch: this run's own allowlist cannot `chmod +x` (FL-22 is
the fix, for the template only), which is why DB-04 is a mode of `ai-run` (see
`.ai/current-plan.md`).

## T001 — Queue check: `ai-task check` and the plan review stops on an invalid queue (FL-18)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
An invalid task queue stops the pipeline at the plan review with the queue error instead of
silently skipping the review; planners have a read-only queue check they may run.

### Implementation notes
- `scripts/ai-task` (~5–11): new `check` (no further argument) → `ai_helper tasks check` (fails
  with the existing `Error: …` text, exit 1), then on success print
  `Task queue OK: <total> tasks, <done> DONE` from `ai_helper tasks counts`. Read-only: no
  lock, no record. Update the usage lines (`set | show | check`).
- `scripts/ai-pipeline` ~414: before `if [[ "$plan_review" == yes ]] && ai_helper tasks
  untouched …`, ALWAYS (plan review on or off; plan review round 1 P7):
  `queue_error=$(ai_helper tasks check 2>&1 >/dev/null) || { printf 'Task queue is invalid: %s\n'
  "${queue_error#Error: }" > .ai/local/last-error; stop "$queue_stage"; }` with
  `queue_stage='plan review'` when `plan_review == yes`, else `implementation`, so the
  `Task queue is invalid` prefix always reaches ai-recover's escalation.
  The `tasks untouched` gate stays (a queue with a DONE task skips the review as today).
- `scripts/ai-recover` ~136: add `*'Task queue is invalid'*` to the always-escalate patterns
  (a rerun cannot repair a plan; the read-only recovery session cannot edit it).
- `templates/.ai/prompts/plan.md`: one sentence: "Check the queue with `.ai/bin/ai-task check`
  when you have a shell; a headless planning session (`ai-run --plan`) gets the same check
  from the host after it ends."
- README (manual task commands) and `docs/workflow.md` (plan review step): one line each.

### Likely affected modules
scripts/ai-task, scripts/ai-pipeline, scripts/ai-recover, templates/.ai/prompts/plan.md,
tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_queue_check_*` in tests/test_workflow.py:
  - `ai-task check` on a valid queue prints `Task queue OK: 1 tasks, 0 DONE` (fixture) and
    exits 0; on a queue where T001 depends on a later T002 it exits 1 with
    `dependencies must exist earlier in the queue: T002` on stderr, and the file is unchanged;
    on an empty template queue it exits 1 with `No real tasks`;
  - `ai-pipeline --approved` with that invalid queue (fixture as the existing plan review
    pipeline tests, mock codex): exit 1, no codex call, no Claude implementation session
    (`mock-invocations` absent), `last-error` starts with `Task queue is invalid:` and names
    T002, one ⛔ notification containing that text, observation `stage=plan_review,
    state=stopped`;
  - with `AI_AUTO_RECOVER=1` the same stop escalates without a recovery Claude session
    (`recover-calls` absent) and the ⛔ names the queue error;
  - with a DONE task in an otherwise valid queue the plan review is still skipped (existing
    behaviour; no codex plan call);
  - `ai-pipeline --approved --skip-plan-review` with the invalid queue: exit 1, no Claude
    session, `last-error` starts with `Task queue is invalid:`, observation
    `stage=build, state=stopped` (`implementation` stop label), and with
    `AI_AUTO_RECOVER=1` no recovery session (`recover-calls` absent);
  - `templates/.ai/prompts/plan.md` mentions `.ai/bin/ai-task check`.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k queue_check` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-10. `ai-task check` added; `ai-pipeline` validates the queue before the plan review
(stage `plan review`, or `implementation` with `--skip-plan-review`); `ai-recover` always
escalates `Task queue is invalid`; plan prompt, README, docs/workflow.md updated. Tests
`test_queue_check_*` (7) pass; `.ai/bin/ai-check`: 554 tests OK. Note: the final `last-error` reads
`Pipeline stopped during <stage>: Task queue is invalid: …` (ai_die adds the stage prefix), so
tests assert containment, not a bare prefix.

## T002 — Default session budget covers the remaining queue (FL-19, part 1)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
A pipeline with more than 16 tasks no longer stops at "Session limit reached" by default.

### Implementation notes
- `scripts/ai-run`: `sessions=''` by default (~32); `--sessions` keeps setting it and sets
  `sessions_given=yes` (initialised `no` beside it; T007 uses the same flag, add it only once).
  Choose the `(--sessions)` / `(default: …)` wording by `sessions_given`. In the
  implementation path only (after the `--triage` branch ends at ~415, before the dependency
  step ~423): when `sessions` is empty, `read -r done total < <(ai_helper tasks counts)` and
  `sessions=$(( total - done + 2 ))`, raised to 16 when smaller; print
  `Session budget: <n> (default: <total-done> unfinished tasks + 2, at least 16)` or
  `Session budget: <n> (--sessions)`. The queue was already validated at ~87, so the helper
  cannot fail on syntax; still `|| ai_die`.
- Each pipeline call of ai-run recomputes the budget: fix-round tasks added by triage before
  the next call are covered (note this in the usage text). Recovery reruns start ai-pipeline
  with the manifest's arguments, so the default applies there too.
- Usage text (~9 "Defaults: 16 sessions") and README (~166 example, ~550) describe the new
  default; `docs/workflow.md` where sessions are described.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_session_budget_*` in tests/test_workflow.py:
  - a fixture queue of 20 TODO tasks: `ai-run --approved` prints `Session budget: 22` (the
    run may stop after the first session through an existing failing mock mode; the line is
    printed before any session);
  - 3 TODO tasks: `Session budget: 16`; with 1 DONE of 20: `Session budget: 21`;
  - `--sessions 1` with two TODO tasks still stops with `Session limit reached` after one
    session and prints `Session budget: 1 (--sessions)`;
  - every case above stays within `tool()`'s 25 s: at most two sessions run (stop the run
    early with an existing failing mock mode or `--sessions`). The 17-session end-to-end
    runs are T010 (they need the pipeline timeout; plan review round 1 P2).
  - `--triage` and `--revise-plan` do not print a session budget.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k session_budget` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-10. `ai-run` computes `max(16, unfinished + 2)` when `--sessions` is not given and prints
`Session budget: …` (implementation path only; `sessions_given` flag added for T007). Usage, README and
docs/workflow.md updated. Tests `test_session_budget_*` (5) pass; `.ai/bin/ai-check`: 559 tests OK.
The 22/16/21 cases stop after one session via `MOCK_CLAUDE=error`.

## T003 — A relaunch during auto-recovery says who holds the lock and changes nothing (FL-19, part 2)
Status: DONE
Dependencies: none
Model: opus

### Goal
Relaunching `ai-pipeline` (or `ai-run`/`ai-review`) while an in-pipeline recovery holds the
checkout lock prints a clear message naming the owner, and the rejected process leaves the
running recovery's records alone.

### Implementation notes
- `scripts/lib/common.sh` `ai_lock` (~236–248), non-quiet rejection (the `AI_LOCK_QUIET` path
  for ai-recover stays as is): replace `ai_die` by `printf 'Error: %s\n' "$message" >&2;
  exit 1`. Today's `ai_die` writes `.ai/local/last-error` (the real stop reason that
  ai-recover, the watchdog and the dashboard read); a rejected process owns nothing, so it
  writes nothing (no last-error, no marker, no observation, no notification). Callers set
  the marker only after `ai_lock` (ai-pipeline ~78–84), so nothing else changes.
- Message: always starts `Another runner/reviewer owns this checkout` (existing test ~4775
  and ai-recover's `*'Another runner'*` escalation keep matching). Owner hint, best effort:
  read `.ai/local/pipeline.active` only when `[[ -f … && ! -L … ]]` (never a FIFO or
  symlink: no blocking), at most 32 bytes, digits only → PID; then
  `mapfile -d '' -t argv < /proc/$pid/cmdline` (absent → no hint). Runner identity like
  `dashboard.is_runner` (`scripts/lib/dashboard.py` ~28): basename of `argv[0]`, or
  `argv[0]` basename `bash`/`sh` and the basename of the first argument not starting with
  `-`. `ai-recover` → append `: auto-recovery (PID <pid>) is deciding whether to resume the
  pipeline itself. Wait for its 🔧 Recovered or ⛔ STOPPED notification (ai-dashboard shows
  it as recovering), or stop it with kill <pid> before relaunching.`; `ai-pipeline` →
  `: a pipeline (PID <pid>) is running here; watch it with ai-dashboard or stop it first.`;
  anything else → no hint (today's text).
- README (troubleshooting/recovery) and `docs/workflow.md` (lock and recovery): one
  sentence each on relaunching during recovery, plus the known limit (plan review round 2
  P11): an `ai-recover` started by `ai-watchdog --recover` after a crash does not rewrite
  `pipeline.active` (it still names the dead pipeline), so a relaunch during that recovery
  gets the plain `Another runner/reviewer owns this checkout` message without a hint. Not
  changed here: rewriting the marker from ai-recover would alter the watchdog's
  `pipeline_died` input (`scripts/lib/watchdog.py` ~99–111) for a cosmetic hint.

### Likely affected modules
scripts/lib/common.sh, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_lock_owner_*` in tests/test_workflow.py (the owner is a helper bash
  script in the temp dir: `exec 9>.ai/local/workflow.lock; flock 9; printf '%s\n' $$ >
  .ai/local/pipeline.active; exec -a <name> sleep 30`, or a symlinked script named
  `ai-recover` run through bash so its argv is `bash …/ai-recover`; started with
  `subprocess.Popen` and stopped through `self.addCleanup` (kill + wait) registered right
  after the start, so a failing assertion in a parallel shard leaves no lock holder behind):
  - owner `ai-recover`, `.ai/local/last-error` pre-written with `Session limit reached; …`,
    a planted `observation.json` (`recovering`) and an empty notification log:
    `ai-pipeline --approved --sessions 20` exits 1 within 10 s, stderr contains `Another
    runner/reviewer owns this checkout`, `auto-recovery (PID <pid>)` and `kill <pid>`;
    afterwards `last-error`, `pipeline.active` and `observation.json` are byte-identical,
    no notification was sent or logged, no mock agent ran;
  - owner `ai-pipeline`: the hint names the pipeline and its PID;
  - lock held without a marker (the existing `test_pipeline_holds_the_shared_checkout_lock`
    setup) and with a marker naming a dead PID or a non-runner process: the plain message,
    no hint, `last-error` not created;
  - a FIFO `pipeline.active` and a symlinked one: returns within 10 s with the plain
    message;
  - `ai-run --approved` and `ai-review` under the same `ai-recover` owner print the same
    hint;
  - ai-recover's own quiet rejection (`AI_LOCK_QUIET`) is unchanged
    (`Another runner owns this checkout; nothing to recover.`).
- `test_pipeline_holds_the_shared_checkout_lock` and all other existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k lock_owner` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k shared_checkout_lock` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-10: `ai_lock` non-quiet rejection prints `Error: Another runner/reviewer owns this
checkout` plus `ai_lock_owner_hint` and exits 1 without `ai_die` (no last-error, marker,
observation or notification). Tests `test_lock_owner_*` (6) pass; `shared_checkout_lock` (1)
passes unchanged; `.ai/bin/ai-check` PASS, 565 tests. Deviation: a symlinked
`pipeline.active` never reaches `ai_lock` because `ai_root` (workflow.py `paths`) refuses
any symlink under `.ai` first ("Unsafe symlink in workflow path", exit 1, no last-error); the
test asserts that, and `test_lock_owner_hint_never_follows_a_symlink_or_fifo` calls the hint
directly for the symlink/FIFO guard. README and docs/workflow.md note the hint and the
watchdog-started recovery limit.

## T004 — Watchdog: no false STOPPED right after the timer is installed (FL-21)
Status: DONE
Dependencies: none
Model: opus

### Goal
Installing the timer shortly before a pipeline starts never sends "⛔ STOPPED … (killed
runner?)"; a real crash (marker whose process is gone) is still reported at the first probe.

### Implementation notes
- `scripts/lib/watchdog.py` `timer()` ~231: `OnBootSec=2min` → `OnActiveSec=2min` (relative
  to the timer's activation: 2 min after boot as before, since timers.target activates it at
  boot, and 2 min after `--install-timer`'s `enable --now` instead of at once; systemd fires
  an already elapsed `OnBootSec` immediately). `OnUnitActiveSec=10min` unchanged. Comment the
  reason.
- `main()` ~401–421, the `stalled` rule (no runner, no `last-error`, Phase `implementing` or
  `fixing_review`), needs confirmation:
  - `watchdog.json` gains the optional int `stall_seen_ns` (validated like `notified_at_ns`
    ~390–394: present and not an int → the existing `parser.error`; absent → none; files of
    the previous version stay valid).
  - Condition holds and no `stall_seen_ns` → record `stall_seen_ns = now`, no incident.
    Condition holds and `now - stall_seen_ns >= 5 min` (`STALL_CONFIRM_NS`) → the
    `stalled` incident exactly as today (same key, text and dedupe). Condition holds but
    younger → keep the field, no incident. Condition does not hold → drop the field.
  - The record is written in every branch that writes `watchdog.json` today (incl. the
    no-incident `else` ~481) and keeps `active`/`notified_at_ns` semantics.
  - A checkout whose `.ai/local/observation.json` (read with workflow's bounded
    `read_record` on a no-follow `.ai/local` descriptor from `checkout_fds`; unreadable or
    malformed → ignored) has `"stage": "planning"` is not stalled: a planning session or a
    plan waiting for approval is not an implementation (the key arrives with T006; compare
    the plain string).
  - `died`, `hung` and `stop` incidents, `--recover`, `--diagnose` are unchanged.
- `docs/workflow.md` (watchdog section ~702) and README (~820 timer) describe the 2-minute
  first probe and the confirmed stall; note that existing timers need `--install-timer` again
  (host copy and unit).

### Likely affected modules
scripts/lib/watchdog.py, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_watchdog_confirm_*` in tests/test_workflow.py (time via
  `AI_WATCHDOG_NOW`, existing helpers `watchdog`, `watchdog_phase`, `watchdog_runner`):
  - the installed timer unit (existing install test's mock `systemctl`) contains
    `OnActiveSec=2min` and `OnUnitActiveSec=10min` and no `OnBootSec`;
  - install scenario: Phase `implementing`, no runner, no marker: probe at t exits 0 with no
    notification and `watchdog.json` holds `stall_seen_ns`; then a fake `ai-pipeline` runner
    with its marker starts; probe at t+10 min exits 0, no notification, `stall_seen_ns`
    dropped;
  - real killed runner (no marker): probe at t silent, at t+2 min silent, at t+6 min one
    ⛔ `killed runner?` notification (exit 1), at t+16 min no second notification;
  - crash with a marker whose PID is gone: the first probe reports `ai-pipeline is gone`
    (existing `test_watchdog_pipeline_marker_detects_killed_pipeline` unchanged);
  - observation `stage=planning` (active or done) with Phase `implementing` and no runner:
    no `stalled` incident over two probes 10 min apart (the test writes `observation.json`
    by hand, e.g. `{"stage": "planning", "state": "active", …}`: `observe step planning`
    is refused until T006 adds the key); a FIFO `observation.json` returns within 10 s and
    is ignored;
  - a `watchdog.json` without `stall_seen_ns` (previous version) is accepted; one with
    `"stall_seen_ns": "x"` fails like any invalid dedupe record.
- `test_watchdog_health_stall_recovery_and_checkout_scope` is updated to the confirmation
  (first sighting silent, the confirmed one notifies; its other assertions kept); the
  update is named in the result. All other existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k watchdog` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-10, claude: timer unit `OnActiveSec=2min` (commented); `stalled` needs confirmation via
`stall_seen_ns` in `watchdog.json` (`STALL_CONFIRM_NS` 5 min; dropped when the condition stops
holding or a `died` incident takes precedence; validated like `notified_at_ns`); a checkout
whose `observation.json` (pinned `checkout_fds` + `read_record`) has `stage == "planning"` is
never stalled. New tests: `test_watchdog_confirm_timer_first_probe_two_minutes_after_activation`,
`_install_before_pipeline_start_is_silent`, `_killed_runner_reported_once_after_five_minutes`,
`_dead_pipeline_marker_reported_at_first_probe`, `_planning_stage_is_not_stalled` (incl. FIFO
within 10 s), `_dedupe_record_versions`. Updated: `test_watchdog_health_stall_recovery_and_checkout_scope`
(first sighting silent, confirmed probe notifies; other assertions kept). Deviation from "all
other tests unchanged": six tests that used the immediate stall only to trigger a diagnosis or
notification (`test_watchdog_diagnosis_failure_is_not_retried_and_usage`,
`_diagnosis_defaults_to_codex`, `_diagnosis_timeout_and_concurrent_dedupe`,
`_codex_diagnosis_does_not_fall_back`, `_auto_diagnosis_falls_back_to_claude_sonnet`,
`test_observation_notify_watchdog_notification_is_logged_and_symlink_safe`) now call the new
helper `watchdog_stalled(phase)`, which seeds an old `stall_seen_ns` so the stall is confirmed;
their assertions are unchanged. `test_watchdog_pipeline_marker_detects_killed_pipeline`
unchanged. Docs: README watchdog list and timer paragraph, docs/workflow.md stalled incident,
dedupe record and timer (reinstall note). Validation: `-k watchdog` Ran 51 tests OK;
`.ai/bin/ai-check` PASS, 571 tests.

## T005 — Runner template may make a new script executable (FL-22)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
A runner session can make a script it created executable, with the narrowest rule the
allowlist can express, so a new script no longer blocks a task.

### Implementation notes
- `templates/.ai/permissions.allow`: add exactly `Bash(chmod +x *)` after the `git` lines,
  with a comment: only `+x`, only for scripts the task creates inside the checkout (the
  prompt says so); Claude Code's Bash rules are prefix matches and cannot restrict the path,
  and this allowlist is not a sandbox (`.ai/bin/ai-check` already runs project code). No
  other chmod form (no `Bash(chmod *)`, no numeric modes). `git update-index --chmod=+x` /
  `git add --chmod=+x` are NOT the fix: they leave the working-tree file 644 (DB-01 T007).
- `templates/.ai/prompts/runner.md` "How to work here": one bullet: "A new script must be
  executable: run `chmod +x <path>` on the file you created inside this checkout (never other
  modes, never paths outside the checkout), then `git add -- <path>`."
- This repo's own `.ai/permissions.allow` and the copies in other projects are gate files:
  listed as human steps in the handoff (`setup-project --upgrade` updates `.ai/prompts` but
  never `.ai/permissions.allow`).
- README (permissions section) and `docs/workflow.md` (allowlist description): one line each.
- Existing test changed on purpose (plan review round 3 P12):
  `test_permissions_template_excludes_network_installs_and_writers` (tests/test_workflow.py
  ~1369–1379) takes `command.split()[0]` of every `Bash(...)` entry and asserts it is not in
  `programs`, which lists `chmod` (~1372), so the new line fails that subTest as written.
  In that test: remove `chmod` from `programs` and add the assertion that every entry
  starting with `Bash(chmod` equals exactly `Bash(chmod +x *)` (so `Bash(chmod *)`, numeric
  modes and `Bash(chmod -R *)` stay forbidden). Do not weaken anything else in it; name the
  updated test in the result.

### Likely affected modules
templates/.ai/permissions.allow, templates/.ai/prompts/runner.md, tests/test_workflow.py,
README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_permissions_chmod_*` in tests/test_workflow.py:
  - the template's non-comment lines contain `Bash(chmod +x *)` exactly once and no other
    line starting with `Bash(chmod`;
  - a fresh `setup-project` installs a `.ai/permissions.allow` with that line, and ai-run's
    `--allowedTools` (mock claude `mock-args`) includes `Bash(chmod +x *)`;
  - `templates/.ai/prompts/runner.md` contains `chmod +x` and the "inside this checkout"
    rule; the installed `.ai/prompts/runner.md` after `setup-project --upgrade --apply` of an
    older install contains it too.
- `test_permissions_template_excludes_network_installs_and_writers` is updated as in the
  notes (`chmod` removed from `programs`; every `Bash(chmod` entry must equal
  `Bash(chmod +x *)`) and passes; the update is named in the result. All other existing
  tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k permissions_chmod` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-10. `Bash(chmod +x *)` added to the template with a comment; runner prompt bullet
added (also to `triage.md`, because `test_tool_contract_section_is_shared_by_prompts` requires
the two sections to be identical); README and docs/workflow.md one line each. New tests
`test_permissions_chmod_*` (3). Updated on purpose:
`test_permissions_template_excludes_network_installs_and_writers` (`chmod` removed from
`programs`; any `chmod` entry must equal `chmod +x *`). Gate: `.ai/bin/ai-check` PASS, 574
tests (one earlier run had a 25 s timeout in an unrelated recover test, passed on rerun).

## T006 — Plan stage records: `planning` box key, `plan` stop label, `planned`, allowlist and scope helpers (DB-04)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
The helper side of the plan stage, so T007 can record and confine a planning session.

### Implementation notes
scripts/lib/workflow.py:
- `BOX_KEYS` (~3098): `planning` first. `STOP_LABELS` (~3102): `'plan': (('planning',),
  'planning')`. `observation_update` (~3307): new action `planned NOTE` → `{**record,
  'stage': 'planning', 'state': 'done', 'detail': '', 'note': NOTE, 'since': now}`
  (`needs((1, 1), 'planned NOTE')`). Schema check (~3382) follows `BOX_KEYS`.
- `PLAN_EDITABLE = ('.ai/project-spec.md', '.ai/current-plan.md', '.ai/tasks.md',
  '.ai/state.md', '.ai/handoff.md', '.ai/reviews/dispositions.md')`;
  `plan-allowlist` (dispatch beside `plan-revision-allowlist` ~3585): prints `Read`, `Glob`,
  `Grep`, then `Edit(./X)` and `Write(./X)` for each X, one per line; nothing from
  `.ai/permissions.allow`, no Bash.
- `plan-scope START`: `records_scope(START, PLAN_EDITABLE + ('.ai/run-log.md',),
  'Planning')` (`.ai/run-log.md` is written by ai-run's exit handler, never by the session).
- The dashboard imports `BOX_KEYS` (`dashboard.py` ~18, ~206): a `planning` record is
  accepted there and renders as `stage unknown` until T008. Check that no existing test
  iterates `BOX_KEYS` expecting a drawn box; if one does, keep it passing by excluding
  `planning` there with a comment pointing to T008.
No flow change yet.

### Likely affected modules
scripts/lib/workflow.py, tests/test_observation.py

### Acceptance criteria
- Tests named `test_observation_writer_plan_*` in tests/test_observation.py:
  - `observe step planning 'opus · first plan'` → `stage=planning, state=active` with the
    detail; `observe planned '7 tasks'` → `stage=planning, state=done, note='7 tasks'`,
    detail cleared, new `since`; `observe stop plan 'Task queue is invalid: …'` after
    `step planning` keeps `planning`, after `step build` gives `planning`; `stop ''` keeps
    `planning`; `observe pause …`/`resume` keep `planning`;
  - `plan-allowlist` prints exactly the 15 lines (3 read tools + Edit/Write for the six
    records) and nothing containing `Bash`;
  - `plan-scope HEAD` passes with uncommitted changes to each of the six records and
    `.ai/run-log.md`, fails naming `src.txt` when `src.txt` changed, and fails when
    `.ai/reviews/plan.md` changed;
  - `ai-dashboard --json` on a `planning` record (fixture as `test_dashboard_snapshot_*`)
    returns without an exception.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_writer` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-10. `planning` is the first `BOX_KEYS` entry; `plan` stop label; `observe planned NOTE`; `plan-allowlist` and `plan-scope` helpers in workflow.py. Tests `test_observation_writer_plan_*` (5; one in tests/test_dashboard.py for the dashboard fixture). `.ai/bin/ai-check` PASS, 579 tests. No existing test iterated `BOX_KEYS`. The editable dispositions record is `.ai/reviews/dispositions.md` as the task specifies (not `plan-dispositions.md`).

## T007 — `ai-run --plan PROMPT_FILE`: headless planning session as a registered stage (DB-04)
Status: TODO
Dependencies: T001, T006
Model: opus

### Goal
Mission control starts planning sessions with one toolkit command that confines the session
to the plan records, shows it on the dashboard from the first second, and ends with a valid
queue or a recorded stop.

### Implementation notes
scripts/ai-run (structure like the `--revise-plan` branch ~225–351):
- Options: `--plan PROMPT_FILE` (resolved to an absolute path while parsing, before
  `ai_root` changes directory; must be a readable regular file ≤ 200 KB), `--revision`
  (only with `--plan`). With `--plan`: `--approved` is not required (no project allowlist is
  used); `--model`, `--session-timeout`, `--knowledge-dir` allowed; `--triage`,
  `--revise-plan`, `--since`, `--base`, `--sessions`, `--run-timeout` refused; refused when
  `AI_PIPELINE` is set (`ai_die 'ai-run --plan runs outside a pipeline.'`). Usage text.
  Option refusal uses "given" flags set by the parser, never the values: the `--sessions`
  case sets `sessions_given=yes` (initialised `no` beside `sessions` at ~32; add it here if
  T002 has not), likewise for the other refused options, so `--plan p --sessions 16` is
  refused whatever the default is and T007 does not depend on T002 (plan review round 2
  P10).
  Plan mode's session timeout defaults to 3600 s unless `--session-timeout` is given (an
  opus first plan on a real repo can exceed the 1800 s runner default, ai-run:32); usage
  text and README say so and that the watchdog's `hung` warning (45 quiet minutes,
  watchdog.py ~427) may still fire on a long plan (plan review round 1 P5).
- Order in plan mode: `ai_supervise_settings`, claude check, `ai_root`, state-root check,
  `ai_lock`, `rm -f last-error`, branch (`AI_START_BRANCH`, `ai_branch`: protected branches
  refused), HEAD exists. Skip the clean-checkpoint check (~85) and `tasks check` (~87) (a
  first plan starts from the template queue); instead `ai_helper plan-scope HEAD` → on
  failure `ai_die "Planning: …"` (uncommitted work outside the plan records). Gate digest as
  today (~89–92).
- `active_task=planning`, `since=$(git rev-parse HEAD)`, `plan_model=${explicit_model:-opus}`,
  kind `revision` or `first plan`. `ai_helper pipeline-register "$AI_ROOT" "$AI_START_BRANCH"
  || printf 'Warning: …'`; `ai_observe step planning "$plan_model · $kind"`;
  `ai_notify "📝 PLANNING on $AI_START_BRANCH ($plan_model, $kind)."`.
- Prompt: `.ai/prompts/plan.md` when present, then `OBJECTIVE (from <prompt file name>):` and
  the file, then `PLANNING CONTRACT:` you may edit/write only the six records (listed), no
  shell, do not commit, do not implement anything; the host validates `.ai/tasks.md` with the
  same rules as `.ai/bin/ai-task check` after you finish (dependencies only on earlier tasks,
  one `Status:`/`Dependencies:` line, the required sections), plus for `--revision`: "an
  earlier plan exists: keep DONE tasks, their status and results unchanged". Then
  `knowledge_prompt`. Session: `claude_session "$prompt" "$plan_model"
  Read,Glob,Grep,Edit,Write "${plan_allowed[@]}"` with `mapfile -t plan_allowed < <(ai_helper
  plan-allowlist)`; `ai_branch` after.
- After the session: `ai_helper plan-scope "$since"` → `ai_die "Planning: …"`; queue:
  `queue_error=$(ai_helper tasks check 2>&1 >/dev/null) || ai_die "Planning: task queue is
  invalid: ${queue_error#Error: }"`; counts from `tasks counts`. Success: `ai_observe planned
  "<total> tasks"`, `ai_notify "📝 Plan ready on <branch>: <total> tasks. Review and commit
  it, then start ai-pipeline --approved."`, `finished=yes`, print the same, exit 0. Never
  commits, never reverts the session's edits.
- `on_exit` (~107): when `active_task == planning`, not finished and `gate_ok == yes`:
  `ai_observe stop plan "$(head -n 1 .ai/local/last-error 2>/dev/null || echo "exit $code")"`
  before the existing ⛔ notification (which already runs outside a pipeline). The existing
  `ai_log` stop line stays (plan-scope allows `.ai/run-log.md`).
- `scripts/lib/watchdog.py` needs nothing (the process is `ai-run`, already a runner).
- tests/test_workflow.py mock claude (~66–170): a `PLANNING CONTRACT` branch before the final
  `assert 'RUNNER CONTRACT' …` (~170): logs args/prompt to `MOCK_STATE_DIR/plan-args.log` /
  `plan-prompts.log`, appends the current `observation.json` to `.ai/local/obs-history`,
  then by `MOCK_CLAUDE`: `plan-ok` (writes a valid two-task queue from
  `MOCK_TASK_TEMPLATE` and a spec line), `plan-bad-queue` (T001 depends on T002),
  `plan-outside` (also writes `src.txt`), `plan-gate` (rewrites `.ai/bin/lib/workflow.py` to
  create `UNTRUSTED_HELPER_RAN`), `plan-error` (error result).
- README: a "Plan with a headless session" paragraph (command, allowlist, what it records,
  that it never commits) and the Modes table row; `docs/workflow.md`: the plan stage
  (T009 audits).

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_plan_session_*` in tests/test_workflow.py:
  - `plan-ok`: exit 0; claude got `--tools Read,Glob,Grep,Edit,Write`, `--allowedTools`
    exactly the `plan-allowlist` lines (no `Bash`), `--permission-mode dontAsk`,
    `--model opus` (and `--model sonnet` with `--model sonnet`); the prompt holds the prompt
    file's text and `PLANNING CONTRACT`; during the session the record is
    `stage=planning, state=active`, detail `opus · first plan` (`revision` with
    `--revision`); afterwards `stage=planning, state=done, note='2 tasks'`; the host
    registry has the checkout; notifications `📝 PLANNING` and `📝 Plan ready`; HEAD
    unchanged (no commit), the plan files changed in the working tree;
  - a relative PROMPT_FILE given from a subdirectory of the checkout is found;
    a missing one fails before any session;
  - `plan-bad-queue`: exit 1, stderr and `last-error` contain `task queue is invalid` and
    the same `dependencies must exist earlier` text as `ai-task check`; record
    `stage=planning, state=stopped` with that note; exactly one ⛔ notification; the
    invalid `.ai/tasks.md` is left as written;
  - `plan-outside`: exit 1 naming `src.txt`, record stopped, `src.txt` still present;
  - `plan-gate`: exit 1 with `Approved workflow gate changed`, `UNTRUSTED_HELPER_RAN`
    absent, no stop record written after the change (record still `active`);
  - `plan-error`: exit 1, record stopped;
  - refusals: `AI_PIPELINE=1`, `--plan p --triage`, `--plan p --sessions 2`,
    `--plan p --sessions 16`, `--revision`
    without `--plan`, uncommitted `src.txt` before the start (no session ran in each case);
    a held checkout lock (holder set up as in `test_pipeline_holds_the_shared_checkout_lock`):
    exit 1, stderr contains the stable prefix `Another runner/reviewer owns this checkout`,
    no session ran; the owner hint and the "no `last-error` written" guarantee are T003's
    tests and are NOT asserted here, so this case passes whether or not T003 is done (T007
    does not depend on T003; plan review round 3 P15);
  - a usage-limit pause (mock `limit-once` applied to the planning branch, `AI_SLEEP`) shows
    `state=paused` on `planning` and the run then completes;
  - the plan session's timeout is 3600 s by default and the `--session-timeout` value when
    given (visible through the existing session-timeout mechanism, e.g. a mock `timeout`
    wrapper's arguments or the session log).
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k plan_session` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T008 — Dashboard: nine boxes with Plan first, `planned` status (DB-04)
Status: TODO
Dependencies: T006, T007
Model: sonnet

### Goal
The dashboard shows a run from the moment its plan is being written: a Plan box (Claude)
before Plan check, with old records never shown as a failed Plan.

### Implementation notes
scripts/lib/dashboard.py:
- `FLOW` (~330): `('planning', 'Plan', 'Plan', 'claude')` first; Plan check's compact label
  `PlanCheck`. `BOX_OF['recheck']` = Triage's index computed from `FLOW` (no literal 6).
- Joiners `─` (one column) instead of `──` (~469) so nine boxes fit from 120 columns:
  worst case labels 4 + 10 + 13 + 5 + 11 + 6 + 6 + 8 + 2 = 65, + 4 per box × 9 = 101,
  + overlay 3 = 104, + 8 joiners = 112, + indent 2 = 114 ≤ 120. `WIDE_FROM` stays 120.
- `position()` (~381): an observation with stage `none` (a pipeline's `start` record, also the
  stop at start) → the Plan box counts as passed (✓), nothing highlighted, marker texts as
  today (`⛔ stopped before Plan check` keeps its wording). Every stage after `planning`
  ticks Plan through the existing `i < index` rule. No observation (legacy/malformed) →
  unchanged: no box ticked, `stage unknown (older toolkit)`, Plan never in style `stopped`.
- Status (`inspect` ~293–303): `state == 'done'` and stage `planning` → `planned` (checked
  before `finished`); liveness/stopped rules first as today (a running `ai-run --plan` is
  `running` on Plan, a stopped one `needs_you` on Plan with the note). `RANK`: `planned`
  after the live statuses and before `finished`; hidden after 24 h like `finished`/`idle`.
  `position()` for `planned`: Plan ✓, nothing active, marker `📝 <note>` (style `dim`) at the
  Plan check box; compact line `✓Plan ·PlanCheck …` plus no extra line.
- Header unchanged (running · needs you · finished). `--json`: runs carry `stage:
  "planning"` and `status: "planned"` as plain values.
- Update the golden outputs of the existing `test_dashboard_render_*` tests to nine boxes and
  `─` joiners (name every updated test in the result); their other assertions stay.

### Likely affected modules
scripts/lib/dashboard.py, tests/test_dashboard.py

### Acceptance criteria
- Tests named `test_dashboard_plan_*` in tests/test_dashboard.py (fixtures as the existing
  dashboard tests, `AI_DASHBOARD_ROOT`/`AI_DASHBOARD_PROC` set; records produced by
  `workflow.py observe`, not hand-written, where a writer exists):
  - golden text at 140, 120, 119 and 60 columns for a running planning session (Plan box
    double-bordered in `active_claude`, detail `opus · first plan` under it, no ✓) and for a
    running build (✓ under Plan, Plan check, Plan revision, Setup);
  - worst case at 120 (Plan revision active and paused, `Build 99/99`, Re-check) renders all
    nine boxes without truncation; no line exceeds the width at 40–200;
  - `planned` (`observe planned '7 tasks'`, no process): `--json` status `planned`, stage
    `planning`; text shows ✓ under Plan and `📝 7 tasks`; sorted after a running run and
    before a finished one; hidden after 24 h without `--all`;
  - stopped planning (`observe stop plan 'Task queue is invalid: …'`, no process): status
    `needs_you`, Plan box in style `stopped`, the note on the marker line; compact
    `✗Plan`;
  - pipeline start record (`observe start`, live fake `ai-pipeline` process): Plan ✓, no
    box active; the stop at start still says `⛔ stopped before Plan check` with Plan ✓;
  - an old record at `build` (written as before DB-04) → Plan ✓; legacy checkout without an
    observation → Plan not ticked and not `stopped`, `stage unknown (older toolkit)`;
  - a fixture process `['bash', '/x/.ai/bin/ai-run', '--plan', 'p.md']` in a checkout with
    a `planning` record → `running` on Plan;
  - `recheck` still renders in the Triage box as `Re-check` (`active_codex`).
- All other existing dashboard tests pass with only their golden texts updated.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T010 — Session budget end to end under a long-run test timeout (FL-19, plan review rounds 1–2 P2)
Status: TODO
Dependencies: T002
Model: sonnet

### Goal
Prove the default budget end to end (17 tasks run past session 16) without the test
exceeding or racing the harness's 25 s `tool()` timeout.

### Implementation notes
- `tool()` (tests/test_workflow.py ~1130) gives every command except `ai-pipeline`
  `COMMAND_TIMEOUT` (25 s); one mock session costs ~5 s in parallel shards (the existing
  budget test ~1266 already needs the full window for 5 sessions). Add
  `LONG_RUN_TIMEOUT = 600 * TIMEOUT_SCALE` next to `COMMAND_TIMEOUT`/`PIPELINE_TIMEOUT`
  (~19–20) with a comment (17 mock sessions in parallel shards; CI runs on a 2-core runner
  without `AI_TEST_TIMEOUT_SCALE`; plan review round 2 P2). Run `ai-run` here through
  `self.run_cmd([...ai-run path..., '--approved'], timeout=LONG_RUN_TIMEOUT)` (or add a
  `timeout=` keyword to `tool()` that defaults to today's rule; existing callers unchanged).
  `PIPELINE_TIMEOUT` (120 s) is NOT enough margin for 17 sessions.
- Use the cheapest mock: the default mode whose session completes its task; no extra work
  per session. Generous bounds only (gate note).
- The two cases share nothing mutable; each builds its own fixture.

### Likely affected modules
tests/test_workflow.py

### Acceptance criteria
- Tests named `test_session_budget_end_to_end_*` in tests/test_workflow.py:
  - 17 TODO tasks, no `--sessions`: output contains `Session budget: 19` and
    `Iteration 17/19`, ends with `Tasks complete and validation passed`, no
    `Session limit reached`;
  - 17 TODO tasks, `--sessions 16`: stops with `Session limit reached`, never prints
    `Iteration 17/`.
- Both run under `LONG_RUN_TIMEOUT` (600 s × `TIMEOUT_SCALE`), neither `COMMAND_TIMEOUT` nor
  `PIPELINE_TIMEOUT`. All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k session_budget_end_to_end` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T011 — Planning never loses DONE tasks: host check `plan-keeps-done` (DB-04, plan review round 1 P1)
Status: TODO
Dependencies: T006, T007
Model: opus

### Goal
A planning session (first plan or `--revision`) cannot remove or alter a task that was
DONE at its start; the host stops the run naming the task instead of
leaving the loss for mission control to commit unseen.

### Implementation notes
- `scripts/lib/workflow.py`: `plan-keeps-done START`: parse `git show START:.ai/tasks.md`
  (absent at START → pass) and the working-tree `.ai/tasks.md` with `task_blocks`; every
  task whose `Status:` was `DONE` at START must still exist with the identical block.
  Comparison rule (plan review round 2 P9 and round 3 P13, one rule for the whole block):
  compare the RAW text slice of each DONE task, i.e. every source line from its `## Txxx`
  heading up to the line before the next `## ` heading outside a fence, fenced lines
  included, after stripping trailing empty lines. `task_blocks` drops fenced lines from
  `lines` (~403–404: lines inside a code fence are skipped) and keeps the blank lines before
  the next `## `, so the parsed `lines` are NOT the comparison input: add an optional
  `raw` list to each block in `task_blocks` (every line after the heading until the next
  heading or non-task `## ` section, fences included; `lines` and all existing callers
  unchanged) and compare heading + `raw`. Failure: `fail('DONE task T00x was changed or
  removed')`, first offending ID in queue order. Reuse the existing git/`records_scope`
  helpers for reading START; no shell.
- The check is unconditional (not tied to `--revision`): a START queue without DONE tasks
  passes trivially, so a first plan from the template stays free to replace the queue, and
  a forgotten `--revision` cannot bypass it.
- `scripts/ai-run` plan mode, after `plan-scope "$since"` and before `tasks check`:
  `keep_error=$(ai_helper plan-keeps-done "$since" 2>&1 >/dev/null) || ai_die "Planning:
  ${keep_error#Error: }"`. Same stop path as the other post-session failures (record
  `stop plan`, one ⛔). The PLANNING CONTRACT sentence for this rule now applies to every
  plan with DONE tasks and says the host checks it.
- Also call `ai_helper plan-keeps-done HEAD` in the pre-session checks right after
  `plan-scope HEAD` (same `ai_die "Planning: …"`): it passes trivially but parses the START
  queue, so a malformed task heading at START fails before a Claude session is spent.
- Mock claude: mode `plan-revision-drops-done` (removes or flips a DONE task) and
  `plan-revision-ok` (appends a TODO task, keeps DONE blocks).
- README planning paragraph and `docs/workflow.md` plan stage: one sentence.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, tests/test_workflow.py, tests/test_observation.py,
README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_plan_keeps_done_*` (helper) and `test_plan_session_revision_*`
  (ai-run):
  - helper: passes when a DONE block is unchanged and TODO tasks are added/removed/edited;
    fails naming the ID when a DONE task is removed, set to TODO, or its result text changed;
    fails naming the ID when only text INSIDE a code fence of a DONE task's
    `### Result / notes` changed (e.g. a line of command output in a code-fence block; plan
    review round 3 P13); passes when START has no `.ai/tasks.md` or no DONE task; passes when the
    last DONE block only gains or loses trailing blank lines because a task was appended
    after it; `task_blocks(...)['lines']` of a fixture with a fence is unchanged by the new
    `raw` list;
  - `ai-run --plan p` on a committed queue with a malformed `## T0x` heading: exit 1 with
    `Malformed task heading`, no Claude session ran;
  - `ai-run --plan p --revision` with `plan-revision-drops-done` on a queue with DONE
    T001: exit 1, stderr and `last-error` contain `DONE task T001 was changed or removed`,
    record `stage=planning, state=stopped`, one ⛔, the edited file left as written;
  - same with `plan-revision-ok`: exit 0, `planned` record, note counts the new task;
  - the same drop without `--revision` is also refused.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k plan_keeps_done` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k plan_session_revision` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
## T009 — Docs, handoff and final audit for the batch
Status: TODO
Dependencies: T001, T002, T003, T004, T005, T006, T007, T008, T010, T011
Model: sonnet

### Goal
README, `docs/workflow.md` and the handoff describe what the code now does; the human knows
which gate, vault and timer steps remain.

### Implementation notes
- README: "Watch all pipelines" (~566): nine boxes (Plan first, Claude), when Plan is ✓
  (any pipeline record; a pipeline start marks it), `planned` status and `📝` line, old
  records and older toolkits (Plan unticked, never failed), the `─` box layout from 120
  columns; the planning paragraph and Modes/scripts tables from T007 checked; session
  default (T002), `ai-task check` (T001), relaunch during recovery (T003), watchdog first
  probe and stall confirmation (T004), `chmod +x` rule (T005) each present once.
- `docs/workflow.md`: plan stage (command, allowlist, records `planning`/`planned`/`plan`
  stop, registration, queue check, `plan-keeps-done` (T011), never commits), observation
  schema line updated, and the T001–T005 changes checked against the code.
- This task is the last of the batch: it depends on T010 and T011 as well (plan review
  round 3 P14), so `tasks next` runs them first and the audit covers their tests and docs
  sentences (T010's `LONG_RUN_TIMEOUT` tests, T011's README/docs sentence).
- `.ai/handoff.md`: "## Flow chart" starts `Flow chart updated: PENDING` (keep the planner's
  list of vault changes, add anything the tasks changed); "Manual testing for the human"
  (`### Needs you` / `### Covered by automated tests` naming every new test); "Human todos"
  (gate line, upgrades, timer reinstall, vault).
- Search the tests for any remaining `eight boxes` / `OnBootSec` / `16 sessions` wording in
  docs and fix it.

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md

### Acceptance criteria
- `DocsConsistencyTest` passes; README mentions `ai-run --plan`, `ai-task check`, `planned`,
  `Session budget`, `OnActiveSec` (or "2 minutes after install") and `chmod +x`;
  `docs/workflow.md` mentions `planning`, `plan-allowlist` and `stall_seen_ns`.
- `test_pr_body_flow_this_repo_declares_the_flow_chart` passes.
- The handoff names every `test_queue_check_*`, `test_session_budget_*`, `test_lock_owner_*`,
  `test_watchdog_confirm_*`, `test_permissions_chmod_*`, `test_observation_writer_plan_*`,
  `test_plan_session_*`, `test_dashboard_plan_*`, `test_session_budget_end_to_end_*`,
  `test_plan_keeps_done_*` and `test_plan_session_revision_*` group under "Covered by
  automated tests", and every group exists in the tests (T010 and T011 are DONE before this
  task runs).

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

