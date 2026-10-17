# Task queue

Edit `scripts/`, `templates/`, `tests/`, `README.md` and `docs/` only (plus the vault flow chart
and hub Log line where a task says so). Never edit `.ai/bin`, `.ai/prompts`, `.ai/validate`,
`.ai/ci-setup`, `.ai/permissions.allow`, `.claude/settings.json` or `.github/workflows/*`
(gate files; needed gate changes are human steps in `.ai/handoff.md`). Vault: a task that
changes the flow updates `~/zWiki/zWiki/20 Projects/agents/agents-flow.md` and its `updated:`
date in the same task and appends a dated line to the Log of `agents.md`; never tick vault
checkboxes. If the vault edit is denied, record it in the result and in the handoff's
"## Flow chart" section.
Source: vault `agents-backlog.md` (MC-01 part 1, DB-04, R15; Zack's decisions of 2026-10-17 in
the `agents.md` Log), planned 2026-10-17 on `feature/limits-plan-stage` (from `fix/flow-batch-5`
at edc3dc6, PR #30 on PR #29, neither merged). Design: `.ai/current-plan.md`.
Line references are at edc3dc6 and verified by the planner; re-check them before editing.
Every behaviour change gets an offline regression test in the existing style; every task
leaves `.ai/bin/ai-check` passing and updates README.md / `docs/workflow.md` where the
behaviour it changes is described.
Gate note: `.ai/validate` runs the shell syntax checks and then `tests/run_parallel.py`
(about 7 min), inside the 600 s Bash tool limit. Should `.ai/bin/ai-check` still time out in
the session, run the task's targeted tests, record the timeout in the result, and leave the
full gate to the host's post-task `ai-check`. Tests with time bounds run in parallel: assert
"returns within N s" with generous bounds scaled by `tests/timeouts.py`, never a tight
duration. No profiling commands (denied). Test helper scripts written into temp dirs use
`os.chmod` from Python. A new executable script is made executable with `chmod +x` on the path
inside the checkout (allowed since FL-22); check its git mode is 100755 before committing.

## T001 — Limit stop record and run-manifest relaunch schedule (MC-01 part 1, helpers)
Status: TODO
Dependencies: none
Model: opus

### Goal
A usage-limit stop beyond the wait budget leaves a machine-readable record of its agent and
reset time, and the host run manifest can schedule, report and consume a bounded number of
relaunches per human-started run, giving back the recovery attempt `ai-recover` reserved.

### Implementation notes
- Design: `.ai/current-plan.md` "MC-01 part 1", bullets "Record" and "Schedule".
- `scripts/lib/common.sh` `ai_limit_pause` (~95–112): just before the budget `ai_die`, write
  `.ai/local/limit-stop` as `<agent> <reset>` (`reset` = the parsed epoch, `0` when it was not
  in the future) through `printf … > .ai/local/limit-stop.tmp && mv -f` (best effort: `|| true`,
  only when `.ai/local` is a directory). The die message stays byte-identical.
- `scripts/lib/workflow.py`: command `limit-stop` (register in `main()`): reads
  `.ai/local/last-error` and `.ai/local/limit-stop` of the current checkout (regular files only,
  not symlinks); exit 0 printing `<Agent> <relaunch epoch>` only when last-error, stripped of the
  final newline, is exactly one line matching
  `^(Claude|Codex) usage limit: the reset is beyond the \d+s wait budget\. Rerun after it resets\.$`,
  `limit-stop` is `^(Claude|Codex) \d{1,12}$` with the same agent, and
  `last-error mtime - limit-stop mtime` is between 0 and 120 s. Relaunch epoch: `reset + 60` when
  `reset > now`, `now + AI_LIMIT_RETRY` (default 1800, validated int) when `reset == 0`, else
  `now`. Optional `--now EPOCH` argument for tests. Anything else: exit 1, no output.
- `run_manifest` (~1279–1397): optional fields `limit_relaunches` (int 0–100) and
  `limit_relaunch_at` (int); a manifest with a wrong-typed field is invalid as today's fields
  are. Actions: `limit-schedule AT CAP` (validated ints; `limit_relaunches >= CAP` →
  `fail(f'usage limit: already relaunched {n} time(s) in this run')`; else count += 1, at = AT,
  `attempts = max(0, attempts - 1)`, one atomic write, print the count); `limit-due [NOW]`
  (print AT, exit 0 when set and `AT <= NOW`, default `int(time.time())`; else exit 1 silently);
  `limit-resume` (drop `limit_relaunch_at`, `attempts = max(0, attempts - 1)`, atomic, print the
  count; no schedule → exit 1); `limit-count` (print the count, 0 when absent).
  `clear-attempts` also drops both fields; `start` already writes a fresh dict (check). Comment
  why the attempt is given back (a limit wait is not a failed recovery; `ai-recover` reserves
  before it can know, ~70).
- Setting `AI_LIMIT_RELAUNCH_MAX`: add to `RUN_SETTINGS` (~1980), the `ai_config` key list
  (common.sh ~40) and both lists in `scripts/ai-recover` (~74, ~77). Validation (0–9, default 2)
  is T003's.
- No ai-recover logic, no watchdog change here (T002/T003). Flow unchanged in this task.

### Likely affected modules
scripts/lib/common.sh, scripts/lib/workflow.py, scripts/ai-recover, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_limit_relaunch_record_*` in tests/test_workflow.py:
  - `ai-run --approved` with `MOCK_CLAUDE=limit-far`, `AI_LIMIT_MAX_WAIT=60` stops (as
    `test_usage_limit_beyond_wait_budget_stops`) and leaves `.ai/local/limit-stop` =
    `Claude <epoch ≈ now + 7 days>`; `limit-stop` prints `Claude <that epoch + 60>`;
  - `limit-stop` exits 1 for: last-error with an extra line or other text, a missing or garbage
    `limit-stop`, agent mismatch, `limit-stop` older than last-error by 300 s (`os.utime`);
    with reset `0` it prints `now + AI_LIMIT_RETRY` (`--now` fixed; `AI_LIMIT_RETRY=600`), with a
    past reset it prints the `--now` value;
  - manifest units (after `run-manifest start` as `approve_run` does): `reserve-attempt` then
    `limit-schedule 100 2` → count 1, `attempts` 0, `limit-due 99` exit 1, `limit-due 100` prints
    100; `limit-resume` → count 1, schedule gone, `attempts` never below 0; second schedule →
    2; third with cap 2 fails with `already relaunched 2 time(s)`; `clear-attempts` and a new
    `start` drop both fields; a manifest with `limit_relaunches: "1"` is invalid.
- `AI_LIMIT_RELAUNCH_MAX` is recorded in the manifest `env` when set at start (as
  `AI_RECOVER_MAX` in the test at ~4705).
- `test_usage_limit_beyond_wait_budget_stops` and all existing `limit`/`recovery` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_record` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k usage_limit` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T002 — Watchdog starts a due limit relaunch; `--timer-recovers`; no stall alarm while it waits (MC-01 part 1, watchdog)
Status: TODO
Dependencies: T001
Model: opus

### Goal
The installed watchdog timer, on its 10-minute probe, starts `ai-recover` for a run whose
scheduled limit relaunch is due, reports once when it cannot, never calls the waiting run
"stalled", and can tell `ai-recover` whether a recovering timer is installed.

### Implementation notes
- Design: `.ai/current-plan.md` "MC-01 part 1", bullet "Watchdog". File `scripts/lib/watchdog.py`.
- `start_recovery(root, local, marker, stage='crash (pipeline killed or restarted)')` (~293–335):
  write the default last-error only for the crash stage; pass `stage` to `--stage`; keep every
  existing check (host copy, state root, gate digest against `run-manifest gate`). The unit name
  may stay `ai-recover-<slug>-<time>`.
- `main()` (~408–515), inside the lock, after `alive`/`marker` are known and before the incident
  logic: when `args.recover` and not `alive` and `marker_snapshot(marker)` is None, run THIS
  copy's `python3 <bin_dir>/lib/workflow.py run-manifest limit-due` in `root` (as
  `start_recovery` runs `run-manifest gate`; `AI_WATCHDOG_NOW` passed as its NOW argument when
  set, so tests control time). Exit 0 with AT → `start_recovery(…, stage='usage limit
  relaunch')`; None → nothing more (ai-recover announces itself) and continue with the normal
  probe; a refusal → notify `⛔ STOPPED, needs you: the usage-limit relaunch could not start:
  <reason>.` once per AT (key `relaunch:<AT>` kept in the dedupe record's `active` list while the
  schedule is unchanged).
- Stall incident (~443–451): add `now >= paused_until(local)` (ai-recover's pauses.log line,
  T003, ends at AT).
- New flag `--timer-recovers` (in the mutually exclusive timer group): exit 0 printing
  `recovers <timer>` when `timer_status` would report installed (reuse its logic without
  printing twice) and the service file's `ExecStart=` line contains `"--recover"`; else exit 1
  printing `no-recover <timer> (<why>)`.
- docs/workflow.md "Checkout health monitoring" (~785): the relaunch start, the refusal ⛔, the
  stall exception and `--timer-recovers`.
- Flow chart (vault): in "When something goes wrong", the usage-limit path gains "beyond the wait
  budget → relaunch scheduled; the watchdog starts it after the reset (cap
  AI_LIMIT_RELAUNCH_MAX) → else ⛔" (T003 completes the ai-recover side; writing both now is fine,
  say so in the result).

### Likely affected modules
scripts/lib/watchdog.py, tests/test_workflow.py, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_watchdog_*` in tests/test_workflow.py (fixtures as
  `test_watchdog_recover_starts_ai_recover_after_a_crash`: `approve_run`, `mock_systemd_run`,
  `host_watchdog`):
  - schedule due (`run-manifest limit-schedule <now-10> 2` via the helper, no marker, no
    runner): `host_watchdog('--recover')` launches `…/ai-recover --stage usage limit relaunch`,
    writes no last-error, sends no notification;
  - schedule in the future (`AI_WATCHDOG_NOW` before AT): nothing launched, no notification;
    with phase `implementing`, no last-error and a pauses.log line ending after now, two probes
    `STALL_CONFIRM_NS` apart raise no `stalled` incident;
  - due but refused (checkout copy, or changed gate): one ⛔ naming `usage-limit relaunch could
    not start`; a second probe sends nothing more;
  - a live `pipeline.active` marker (or runner) with a due schedule: no launch;
  - without `--recover`: no launch;
  - `--timer-recovers`: exit 1 without unit files; with units installed by `--install-timer
    --recover` (the existing timer tests' mock systemctl) exit 0; installed without `--recover` → 1.
- `test_watchdog_recover_*` and all existing watchdog tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_watchdog` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k watchdog` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T003 — ai-recover schedules a relaunch for a limit-only stop and resumes it when due (MC-01 part 1, recovery)
Status: TODO
Dependencies: T001, T002
Model: opus

### Goal
A pipeline stop whose only reason is a usage limit beyond the wait budget ends in a ⏸ pause with
a host-side relaunch instead of ⛔, and the relaunch resumes the approved run without a Claude
decision or a recovery attempt; past the per-run cap, without a recovering watchdog timer, or
with the feature off, it escalates as today.

### Implementation notes
- Design: `.ai/current-plan.md` "MC-01 part 1", bullet "ai-recover". File `scripts/ai-recover`.
- Validate `AI_LIMIT_RELAUNCH_MAX` (`^[0-9]$`, default 2) next to `max` (~98).
- Insert after the plan-revision decision block (~129) and BEFORE the hard rules (~131):
  1. Due relaunch: `ai_helper run-manifest limit-due` exit 0 → `count=$(ai_helper run-manifest
     limit-resume)`; `ai_notify "▶ RESUMED after the usage limit (relaunch $count/$cap): $branch."`;
     then the existing open-stage branch (~149–163) if a stage is open, else the
     record-stop-leftovers block (~165–171, factor it into a function used by both paths), a
     clean-checkout check (escalate `the usage-limit relaunch found uncommitted changes.` /
     `inspect and commit or discard them, then rerun ai-pipeline.`) and `resume`. `resume` takes
     an optional notification so the relaunch does not also say `🔧 Recovered (n/max)`.
  2. Limit-only stop: `read -r agent at < <(ai_helper limit-stop)` succeeds →
     cap 0 → fall through (hard rule, today's ⛔);
     `"$AI_BIN/ai-watchdog" "$AI_ROOT" --timer-recovers` fails → escalate with the reset time
     (`date -d @"$at" '+%a %H:%M'`) and the install hint (current-plan wording);
     `ai_helper run-manifest limit-schedule "$at" "$cap"` fails → escalate `usage limit again after
     $cap relaunch(es) in this run.` / `rerun ai-pipeline after the reset.`;
     else append the pauses.log line, `ai_observe pause …`, the ⏸ notification, remove
     `.ai/local/last-error`, `.ai/local/limit-stop` and `.ai/local/pipeline.active`, set
     `AI_STOP_NOTIFIED=1`, `trap - EXIT`, print `Paused at a <agent> usage limit; the watchdog
     relaunches the run after <time>.` and `exit 75`.
- Usage text (~5–18): one sentence on the limit relaunch and `AI_LIMIT_RELAUNCH_MAX`.
- Flow chart (vault): "When something goes wrong" shows the relaunch branch before the hard
  rules, the cap and the ⛔ fallbacks; the notifications table gains `▶ RESUMED` and the new ⏸
  wording. README "Recovery" (~425–440: `AI_LIMIT_MAX_WAIT` "a weekly limit beyond that stops
  with …") and docs/workflow.md "Interruption, limits, and recovery" (~234–238) and "Recovery
  contract" (~632) describe the schedule, the cap, the exit 75 and the fallbacks.

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_recover_*` in tests/test_workflow.py (pipeline fixtures as
  `test_recovery_never_passes_a_changed_gate_or_hard_stop`; `--timer-recovers` is satisfied by
  real unit files written by `ai-watchdog --install-timer --recover` with the existing timer
  tests' mock systemctl, never by editing the fixture's `.ai/bin` copy):
  - `ai-pipeline --approved … --no-pr` with `MOCK_CLAUDE=limit-far`, `AI_LIMIT_MAX_WAIT=60`,
    `AI_AUTO_RECOVER=1`, timer installed with `--recover` → exit 75; notifications contain
    `⏸ PAUSED` and `relaunches by itself after`, no `⛔`; `recovery_calls()` is empty; the manifest
    has `limit_relaunches` 1, `limit_relaunch_at` ≈ reset + 60 and `attempts` 0; last-error,
    limit-stop and pipeline.active are gone; pauses.log's last line parses with
    `watchdog.paused_until` to AT;
  - then the manifest's AT is set into the past (rewrite run.json in `AI_STATE_DIR`) and
    `ai-recover --stage 'usage limit relaunch'` runs with a normal `MOCK_CLAUDE` → the pipeline
    resumes and completes; notifications contain `▶ RESUMED after the usage limit (relaunch 1/2)`
    and no `🔧 Recovered`; `attempts` 0 at finish;
  - cap: `AI_LIMIT_RELAUNCH_MAX=1` and a second limit stop after one relaunch → ⛔ with
    `usage limit again after 1 relaunch(es)`;
  - `AI_LIMIT_RELAUNCH_MAX=0` → ⛔ `this kind of stop always needs a human` (today);
  - no timer installed → ⛔ naming the reset time and `--install-timer --recover`; no schedule;
  - a last-error with the limit message plus another line → today's hard-rule ⛔, no schedule.
- `test_recovery_*`, `test_usage_limit_*`, `test_watchdog_*` pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T004 — Dashboard: a run waiting for its limit relaunch shows paused; a killed planning session shows as a stop (MC-01, DB-04)
Status: TODO
Dependencies: T003
Model: sonnet

### Goal
`ai-dashboard` shows a run whose relaunch is scheduled as paused (not idle) with its note, and a
planning session that died without a plan as a stop on the Plan box.

### Implementation notes
- `scripts/lib/dashboard.py` `inspect` (~382–392), when `liveness` is `gone`:
  observation `state == 'paused'` → status `paused`; observation `stage == 'planning'` and
  `state == 'active'` → status `needs_you` with `run['last_error']` (when empty) set to
  `planning session ended without a plan (killed?)` so `stop_note` and the ⛔ marker show it.
  Order: `crashed`, `alive`, then these two, then today's `stopped`/errored/done/idle.
- `position`/`marker_text` already handle `paused` and `needs_you`; check the paused marker
  reads `⏸ <note>` under the stage box for a gone run, and the compact line (`✗Plan`) and the
  golden widths (`test_dashboard_plan_nine_boxes_fit_120_without_truncation`, 40–200 columns)
  still fit; add both new runs to that loop.
- `--json` (`snapshot`) carries the new statuses without schema change; `RANK` unchanged.
- docs/workflow.md "Observation records and the dashboard" (~996): the two rules.
- Flow chart: check whether it describes dashboard statuses; flow unchanged unless it does (say
  which in the result).

### Likely affected modules
scripts/lib/dashboard.py, tests/test_dashboard.py, docs/workflow.md

### Acceptance criteria
- Tests named `test_dashboard_limit_relaunch_*` and `test_dashboard_plan_killed_*` in
  tests/test_dashboard.py (fixtures as `planned_checkout`):
  - steps `('step', 'build', 'T003')`, `('pause', 'Claude limit · relaunch after Sat 09:05')`, no
    runner, no marker → `--json` status `paused`, stage `build`; the view shows `⏸` and the note;
  - steps `('step', 'planning', 'opus · first plan')`, no runner → status `needs_you`, stage
    `planning`, `║ Plan ║` styled `stopped`, the ⛔ line contains
    `planning session ended without a plan`, compact starts `  ✗Plan ·PlanCheck`;
  - the same planning observation WITH a live `ai-run --plan` runner stays `running` (as
    `test_dashboard_plan_live_ai_run_plan_is_running_on_plan`);
  - both new runs fit every width 40–200 without exceeding it.
- All existing `test_dashboard_*` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k dashboard_plan` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T005 — `ai-run --plan --read-dir DIR`: read-only reference directories for the planning session (DB-04)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
A planning session can read the directories mission control's launcher grants (vault, plans,
research) without any new edit permission.

### Implementation notes
- Design: `.ai/current-plan.md` "DB-04", bullet "Read dirs". File `scripts/ai-run`.
- Argument parsing (~47–88): `--read-dir DIR` repeatable; `[[ -d "$2" ]]`, resolved with
  `cd -- "$2" && pwd -P`; refuse a resolved path containing `*`, `?`, `[`, `]`, `(`, `)`, `,` or a
  newline (`Invalid --read-dir path: …`). Plan mode only: refuse it without `--plan`
  (`--read-dir only applies to --plan.`).
- Plan block (~351–358): for each directory append `--add-dir DIR` to the session's arguments
  (beside `knowledge_args`) and `Read(/$dir/**)` to `plan_allowed` (absolute `$dir` → `//…`).
  Contract sentence: `Read-only reference directories: <list>. Read them as needed; never edit
  them.` No Edit/Write entries are added.
- Usage text (~8–9, ~29–37) and docs/workflow.md "Plan stage" (~243–281) name the flag and that
  `--knowledge-dir` stays the knowledge base option.
- Flow unchanged (T006 updates the plan node of the flow chart for `ai-plan`).

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Tests named `test_plan_read_dir_*` in tests/test_workflow.py (fixtures as the existing
  `ai-run --plan` tests, e.g. `test_queue_repair_planning_session_reorders_without_committing`;
  the mock claude records its args in `.ai/local/mock-args`):
  - two `--read-dir` directories (one given through a symlink) → the recorded args contain
    `--add-dir <resolved>` for each and `Read(/<resolved>/**)` for each, and no `Edit(`/`Write(`
    entry outside the plan records; the prompt names both directories;
  - a missing directory, a path with `*` or `,` → exit 1 before any session (no mock call);
  - `ai-run --approved --read-dir X` → `--read-dir only applies to --plan.`
- All existing plan-stage tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k plan_read_dir` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k queue_repair_planning` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T006 — `ai-plan PROMPT_FILE` command with a confirmed `--detach` start (DB-04)
Status: TODO
Dependencies: T005
Model: opus

### Goal
Mission control (or the human) starts a planning session with one toolkit command, in the
foreground or detached, and learns its PID and log only once the session has really started, so
the hand-run `launch-plan.sh` is no longer needed.

### Implementation notes
- Design: `.ai/current-plan.md` "DB-04", bullet "Command". New file `scripts/ai-plan` (bash,
  `source …/lib/common.sh` like the other scripts; executable, git mode 100755).
- Options: `PROMPT_FILE` (first positional), `--revision`, `--model NAME`, `--session-timeout S`,
  `--knowledge-dir DIR`, `--read-dir DIR` (repeatable), `--detach`, `-h|--help`. Validation of
  the shared options is ai-run's; ai-plan checks only its own (`--detach`, the prompt file exists,
  is regular and readable; resolve it to an absolute path before any `cd`).
- Foreground: `exec "$AI_BIN/ai-run" --plan "$prompt" "${rest[@]}"` (same PID: the dashboard,
  watchdog and lock see an `ai-run` runner, nothing else changes).
- `--detach`: checks only as far as needed to find `.ai/local` (inside a Git checkout with a
  real `.ai`); log `.ai/local/plan-$(date -u +%Y%m%dT%H%M%SZ).log`;
  `setsid "$AI_BIN/ai-run" --plan "$prompt" "${rest[@]}" </dev/null >"$log" 2>&1 &` and
  `pid=$!` (comment why `$!` is the runner: a non-interactive shell's background job is not a
  process-group leader, so setsid execs without forking). Then poll every 0.2 s for at most
  `AI_PLAN_ACK_SECONDS` (default 20, validated positive int): success when
  `.ai/local/observation.json` parses with `stage == "planning"`, `state == "active"` and
  `pid == $pid` (read with `python3 -I -c`; never source it) → print
  `Planning session started: pid $pid, log $log` and exit 0; the child exited (`kill -0` fails)
  → `wait "$pid"` for its status, print `ai-plan: the planning session ended early (exit N); last
  lines of $log:` and the last 10 lines, exit N (at least 1); timeout → `ai-plan: could not
  confirm the planning session started within N s (pid $pid, log $log).` exit 1, the child is
  left running. Never kill the child. `disown` it before exiting so the shell sends no SIGHUP.
- `scripts/lib/workflow.py` setup list (~306): add `ai-plan` so `setup-project` installs it
  (check the upgrade path copies it and keeps it executable; adjust a setup test that lists
  installed files, named in the result).
- README (commands list and the "Plan" section) and docs/workflow.md "Plan stage": `ai-plan`
  is the supported way to start a planning session; mission control's `launch-plan.sh`
  equivalent is `ai-plan PROMPT --read-dir ~/zWiki --read-dir ~/Projects/wt/plans --read-dir
  ~/Projects/wt/research --detach` (the session timeout default stays 3600 s).
- Flow chart (vault): the plan node says `ai-plan objective.md` (headless, `--detach` for
  mission control) instead of `ai-run --plan objective.md`; the notifications table row
  `📝 PLANNING / Plan ready` names `ai-plan`.

### Likely affected modules
scripts/ai-plan, scripts/lib/workflow.py, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_ai_plan_*` in tests/test_workflow.py (the mock claude and planning fixtures
  as the existing `ai-run --plan` tests; `AI_DASHBOARD_IGNORE=1` stays in the test env):
  - foreground: `ai-plan prompt.md` gives the same result as `ai-run --plan prompt.md` (plan
    written, `observe planned`, exit 0, nothing committed), and the mock records `--model opus`;
  - `--detach` with a mock claude that sleeps briefly: returns within a scaled bound, prints a
    PID whose `/proc/PID/cmdline` names `ai-run` while it runs, the log file exists, and the plan
    is written once the child ends (poll with a scaled timeout); `observation.json` ends
    `planned`;
  - `--detach` while another process holds the checkout lock (as
    `test_pipeline_holds_the_shared_checkout_lock`): exit ≥ 1 and the output contains
    `ended early` and `Another runner/reviewer owns this checkout`;
  - `--detach` with `AI_PLAN_ACK_SECONDS=1`, a sleeping mock claude and
    `.ai/local/observation.json` made a directory beforehand (the observe helper then only
    warns, so the record never shows planning): exit 1 with `could not confirm`, and the child is
    still alive (the test then terminates it and waits);
  - a missing prompt file → exit 1 before anything starts; `--help` exits 0;
  - `setup-project` installs `.ai/bin/ai-plan` as executable.
- `test_dashboard_plan_live_ai_run_plan_is_running_on_plan` and all plan-stage tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k ai_plan` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k setup` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T007 — Planning sessions in the outcome log and the run log (DB-04, logging)
Status: TODO
Dependencies: T006
Model: sonnet

### Goal
Every planning session, finished or stopped, leaves one outcome record and, when it wrote a valid
plan, one run-log line committed with the plan, like other sessions.

### Implementation notes
- Design: `.ai/current-plan.md` "DB-04", bullet "Logging".
- `scripts/lib/workflow.py` `outcome()` (~3467–3573): kind `plan`:
  `outcome plan RESULT MODEL SECONDS [TASKS]` (RESULT in `done`, `stopped`, `interrupted`,
  `timeout`; TASKS an int when given); the record carries `result`, `model`, `seconds`, `tasks`
  and `revision` (bool, from a trailing `--revision` flag). Docstring updated; `outcomes_report`
  ignores the kind (check, as for `plan_revision`).
- `scripts/ai-run` plan block (~323–378): `plan_started=$SECONDS` before `claude_session`; on
  success, before `finished=yes`: `ai_helper outcome plan done "$plan_model" "$((SECONDS -
  plan_started))" "$plan_total" … || printf 'Note: …'` and
  `ai_log planning "plan written: $plan_total tasks ($plan_model, $plan_kind)" PASS 'Plan left uncommitted for review'`.
  `on_exit` (~197–200): when `active_task == planning` and the gate is intact, one `outcome
  plan` with `interrupted` (130/143), `timeout` (`session_code` 124/137) or `stopped`, seconds
  from `plan_started` (0 when the session never started). Never fatal.
- README "Outcome log" (~495) and docs/workflow.md "Outcome log" (~899): the `plan` kind; "Plan
  stage": the run-log line on success.
- Flow chart (vault): the "Outcome log" bullet mentions planning sessions.

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_plan_outcome_*` in tests/test_workflow.py (`AI_STATE_DIR` in the temp dir):
  - a successful `ai-plan` (or `ai-run --plan`) appends one `kind: plan` record with
    `result: done`, `model: opus`, int `seconds`, `tasks` equal to the queue's count, and
    `.ai/run-log.md` gains one `plan written:` row; `plan-scope` still passes;
  - a planning stop (queue invalid, as `test_queue_repair_planning_cycle_stops_and_keeps_the_file`)
    appends `result: stopped`; a session timeout (`--session-timeout 1` with a sleeping mock)
    appends `timeout`;
  - `ai-status --outcomes` renders unchanged with a `plan` record in the log.
- All existing `outcome` and plan-stage tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k plan_outcome` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T008 — Host record of a PR the pipeline drafted (R15, helper)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
The host can durably record, read and clear "the pipeline made this branch's PR a draft",
outside every checkout, failing closed (unreadable means "not ours").

### Implementation notes
- Design: `.ai/current-plan.md` "R15", bullet "Record". `scripts/lib/workflow.py`, next to
  `stage_path` (~1413).
- `pr_draft_path(branch) = binding_dir() / f'pr-draft-{sha256(branch)[:16]}.json'`.
- Command `pr-draft` (register in `main()`): `record URL HOW` (URL matches
  `^https://\S+/pull/\d+$`, HOW in `created`, `converted`; atomic write via the existing `atomic`
  of `{"branch", "url", "how", "at": now()}`; detached HEAD → fail); `get` (prints the URL and
  exits 0 only when the file parses, is a dict, its `branch` equals the current branch and `url`
  is valid; else exit 1 silently); `clear` (unlink, missing is fine).
- Comment why it lives in host state (agent sessions cannot forge "the pipeline drafted this") and
  why unreadable means not ours (never un-draft on doubt).
- No pipeline change here (T009). Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_pr_undraft_record_*` in tests/test_workflow.py: record then get prints the
  URL; clear then get exits 1; a record for another branch (switch branch) → get exits 1; a
  garbage file, a non-dict, an invalid URL → get exits 1; `record` with an invalid HOW or URL
  fails; the file is under `AI_STATE_DIR`, not in the checkout.

### Validation
Targeted: `python3 -m unittest discover -s tests -k pr_undraft_record` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T009 — PR step un-drafts only a PR the pipeline drafted (R15, pipeline)
Status: TODO
Dependencies: T008
Model: sonnet

### Goal
When the PR step runs with a clean review and no dispute, an existing draft PR that the pipeline
itself drafted becomes ready; a PR a human drafted stays a draft.

### Implementation notes
- Design: `.ai/current-plan.md` "R15", bullet "Pipeline". File `scripts/ai-pipeline` (~600–619).
- Split the draft reasons: `human_draft=yes` for `--draft`, `policy_draft=yes` for
  `unresolved == 1` or `disputes != 0`; `make_draft` as today.
- Existing PR, `make_draft=yes`: after a successful `gh pr ready --undo` + isDraft check, when
  `policy_draft=yes` and `human_draft=no` → `ai_helper pr-draft record "$url" converted`.
  Already a draft → no record change.
- New PR created with `--draft`, `policy_draft=yes`, `human_draft=no` → `pr-draft record "$url"
  created` after `gh pr create` succeeded.
- Existing PR, `make_draft=no`: `is_draft=$(gh pr view … isDraft)`; when `true` and
  `"$(ai_helper pr-draft get 2>/dev/null)" == "$url"` → `gh pr ready "$branch"`, re-check isDraft
  `false` → `ai_helper pr-draft clear`, `printf 'Marked the PR ready (the pipeline had made it a
  draft).\n'`, `ai_log none "pull request marked ready: $url" PASS 'drafted by the pipeline earlier'`
  (before the `record pull request` host commit so it is committed with it); on failure print a
  warning, keep the record and continue (no stop). When `true` without a matching record → print
  `PR is a draft set outside the pipeline; left as draft.` When `false` → `pr-draft clear`
  (stale record). Check that the `finish-summary` / `pr-body` wording about drafts stays right
  when the PR was un-drafted or stays a human draft (name what you checked in the result).
- Test mock `MOCK_GH` (tests/test_workflow.py ~620–623): `pr ready --undo` touches `gh-draft`,
  plain `pr ready` removes it (change on purpose; name it in the result).
- README pull-request part and docs/workflow.md "Pipeline contract" (~405): the rule, the
  `--draft` exception and the limitation (a human re-draft between two runs is not seen).
- Flow chart (vault): the PR step says the pipeline makes a clean PR ready again only when it
  drafted it itself; the big-picture bullet "If findings remain after two fix rounds, the PR is
  opened as a draft" gains that sentence.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_pr_undraft_*` in tests/test_workflow.py (fixtures as
  `test_deferred_finding_makes_the_pr_a_draft` and `test_existing_ready_pr_is_converted_to_draft`):
  - run 1 drafts for policy (deferral, new PR) → `pr-draft get` prints the PR URL; run 2 with
    `MOCK_GH_EXISTING=1`, `gh-draft` present and a clean review → gh calls contain
    `['pr', 'ready', 'feature/test']`, `gh-draft` gone, the record cleared, the run log has
    `pull request marked ready`;
  - converted case: an existing ready PR converted for policy records `converted`; a later
    clean run un-drafts it;
  - human draft: `gh-draft` touched by the test, no record → no plain `pr ready` call, output
    says `left as draft`, the PR stays draft;
  - `--draft` run: the PR is drafted but nothing is recorded; a later run without `--draft` and
    a clean review leaves it draft;
  - `MOCK_GH_READY_FAIL=1` on the un-draft → the pipeline finishes (exit 0), warns, keeps the record;
  - an existing ready PR with a stale record → the record is cleared.
- `test_existing_ready_pr_is_converted_to_draft`, `test_failed_draft_conversion_stops`,
  `test_deferral_in_an_earlier_round_does_not_draft_a_clean_final_review` and all other draft/PR
  tests pass (the mock change is the only test-side change).

### Validation
Targeted: `python3 -m unittest discover -s tests -k pr_undraft` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k draft` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T010 — Docs, flow chart and handoff audit (all items)
Status: TODO
Dependencies: T004, T007, T009
Model: haiku

### Goal
README, `docs/workflow.md`, the usage texts and the vault flow chart describe exactly what the
code does after T001–T009, and the handoff tells the human what to test and upgrade.

### Implementation notes
- Check against the code (not the plan): README (Recovery, limits, settings list ~550 gains
  `AI_LIMIT_RELAUNCH_MAX` and `AI_PLAN_ACK_SECONDS`, commands, Plan, Outcome log, pull request),
  docs/workflow.md sections named in T002–T009, `--help` of `ai-recover`, `ai-watchdog`,
  `ai-run`, `ai-plan`, `ai-pipeline`. Fix wording only; a behaviour mismatch is recorded in the
  result and the handoff, not fixed here.
- Vault `agents-flow.md`: the limit relaunch branch, `ai-plan`, the un-draft rule and the
  notifications table (`⏸ PAUSED` relaunch wording, `▶ RESUMED`) present and consistent;
  `updated:` date; one Log line in `agents.md` for the batch.
- `.ai/handoff.md`: "Manual testing for the human" (Needs you / Covered by automated tests) with
  the real test names; human steps: upgrade installed copies, reinstall watchdog timers (host
  copy), retire `launch-plan.sh`, mission control switches to `ai-plan`.
- Flow unchanged in this task unless the audit finds a gap (then fix the chart and say so).

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, vault agents-flow.md, vault agents.md

### Acceptance criteria
- `DocsConsistencyTest` and `test_flow_this_repo*` pass; every new setting and command is in
  README; the handoff lists each new test prefix with what it covers.

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

