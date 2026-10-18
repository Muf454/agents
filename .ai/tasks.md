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
Status: DONE
Dependencies: none
Model: opus

### Goal
A usage-limit stop beyond the wait budget leaves a machine-readable record of its agent and
reset time, and the host run manifest can schedule, report and consume a bounded number of
relaunches per human-started run, giving back the recovery attempt `ai-recover` reserved.

### Implementation notes
- Design: `.ai/current-plan.md` "MC-01 part 1", bullets "Record" and "Schedule".
- `scripts/lib/common.sh` `ai_limit_pause` (~95–112): just before the budget `ai_die`, run
  `ai_helper limit-stop-write "$agent" "$reset" 2>/dev/null || true` (`reset` = the parsed
  epoch, `0` when it was not in the future). Never a shell redirection: `.ai/local` is
  agent-writable, and `> file.tmp` follows a planted symlink (truncating its target) or blocks
  on a FIFO (plan review round 1, P6). `workflow.py limit-stop-write AGENT RESET` validates
  both (`^(Claude|Codex)$`, `^\d{1,12}$`), pins `.ai/local` with `local_dir_fd(root)` (~3995;
  None → exit 1) and replaces `limit-stop` with the existing `write_record(dir_fd, 'limit-stop',
  …)` (~4106: `O_CREAT|O_EXCL|O_NOFOLLOW|O_NONBLOCK` temp on the pinned descriptor, regular-file
  check, `os.replace` relative to it), so a symlink or FIFO at the temp or final name is never
  written through. The die message stays byte-identical.
- `observe` (~4262): new action `relaunch AT NOTE` (AT validated int): `state=paused`, `note`,
  new optional field `relaunch_at` = AT, stage and detail kept. Every other action drops
  `relaunch_at`, so only a currently scheduled relaunch carries it (the dashboard's evidence,
  T004; P5).
- `scripts/lib/workflow.py`: command `limit-stop` (register in `main()`): reads
  `.ai/local/last-error` and `.ai/local/limit-stop` of the current checkout (regular files only,
  not symlinks); exit 0 printing `<Agent> <relaunch epoch>` only when last-error, stripped of the
  final newline, is exactly one line matching
  `^(Claude|Codex) usage limit: the reset is beyond the \d+s wait budget\. Rerun after it resets\.$`,
  `limit-stop` is `^(Claude|Codex) \d{1,12}$` with the same agent, and
  `last-error mtime - limit-stop mtime` is between 0 and 120 s. Relaunch epoch: `reset + 60` when
  `reset > now`, `now + AI_LIMIT_RETRY` (default 1800, validated int) when `reset == 0`, else
  `now`. Optional `--now EPOCH` argument for tests. Anything else: exit 1, no output.
- `run_manifest` (~1279–1397): optional fields `limit_relaunches` (int 0–100),
  `limit_relaunch_at` (int), `limit_head` (40-hex) and `limit_resume` (40-hex); a manifest with
  a wrong-typed field is invalid as today's fields are. Lifecycle (plan "Relaunch schedule
  lifecycle"): a schedule is pending (`AT > NOW`), then claimed exactly once, never left due
  after a recovery saw it. Actions, each one atomic write, NOW defaulting to
  `int(time.time())`:
  - `limit-schedule AT CAP HEAD` (validated; `limit_relaunch_at` already set → fail `usage limit:
    a relaunch is already scheduled`; `limit_relaunches >= CAP` →
    `fail(f'usage limit: already relaunched {n} time(s) in this run')`; else count += 1,
    at = AT, `limit_head` = HEAD, `attempts = max(0, attempts - 1)`, print the count);
  - `limit-due [NOW]` (read only, for the watchdog: print AT, exit 0 when set and `AT <= NOW`;
    else exit 1 silently);
  - `limit-at` (read only: print AT and exit 0 whenever a schedule is set, due or not; exit 1
    silently when none): the watchdog's single question "is a relaunch scheduled, and when?",
    so a pending schedule suppresses its stall alarm from host state alone (plan review round
    3, P2; T002);
  - `limit-hold [NOW]` (schedule set and `AT > NOW` → `attempts = max(0, attempts - 1)`, print
    AT, exit 0; else exit 1, nothing written): an `ai-recover` that finds the run still
    waiting gives its reservation back and restores the wait (P2);
  - `limit-claim [NOW]` (schedule set and `AT <= NOW` → drop `limit_relaunch_at`,
    `attempts = max(0, attempts - 1)`, print the count; else exit 1): consumes the schedule, so
    any later stop of that recovery is terminal and no probe launches it again (P1);
  - `limit-verify HEAD` (read only: exit 0 silently when HEAD equals `limit_head`; else exit 1
    with `the branch moved to another commit` on stderr; no schedule or no `limit_head` → exit
    1 `no scheduled relaunch`): the relaunch's first check of the checkout (T003, plan
    "Verification point"; ai-recover appends ` while the usage-limit relaunch waited; nothing
    was committed.` to the reason);
    `limit-arm HEAD` (exit 0 and set `limit_resume = HEAD` only when HEAD equals `limit_head`;
    else exit 1, nothing written); `limit-armed HEAD` (read only: exit 0 when `limit_resume ==
    HEAD`); `limit-disarm` (drop `limit_resume`; missing is fine). P3, used by T003/T011. T012
    extends `limit-verify`/`limit-arm`/`limit-armed` to the tree digest and drops the argument;
    T016 adds a STAGE argument to `limit-schedule` (`limit_stage`) and makes `limit-arm` refuse
    any stage but `implementation`;
  - `limit-count` (print the count, 0 when absent).
  `clear-attempts` also drops all four fields; `start` already writes a fresh dict (check).
  Comment why the attempt is given back (a limit wait is not a failed recovery; `ai-recover`
  reserves before it can know, ~70).
- Setting `AI_LIMIT_RELAUNCH_MAX`: add to `RUN_SETTINGS` (~1980), the `ai_config` key list
  (common.sh ~40) and both lists in `scripts/ai-recover` (~74, ~77). Validation (0–9, default 2)
  is T003's.
- No ai-recover logic, no watchdog change here (T002/T003). Flow unchanged in this task.

### Likely affected modules
scripts/lib/common.sh, scripts/lib/workflow.py, scripts/ai-recover, tests/test_workflow.py,
tests/test_dashboard.py (only if an observation schema test lists the fields)

### Acceptance criteria
- Tests named `test_limit_relaunch_record_*` in tests/test_workflow.py:
  - `ai-run --approved` with `MOCK_CLAUDE=limit-far`, `AI_LIMIT_MAX_WAIT=60` stops (as
    `test_usage_limit_beyond_wait_budget_stops`) and leaves `.ai/local/limit-stop` =
    `Claude <epoch ≈ now + 7 days>`; `limit-stop` prints `Claude <that epoch + 60>`;
  - `limit-stop` exits 1 for: last-error with an extra line or other text, a missing or garbage
    `limit-stop`, agent mismatch, `limit-stop` older than last-error by 300 s (`os.utime`);
    with reset `0` it prints `now + AI_LIMIT_RETRY` (`--now` fixed; `AI_LIMIT_RETRY=600`), with a
    past reset it prints the `--now` value;
  - manifest units (after `run-manifest start` as `approve_run` does; H = 40 hex): `reserve-attempt`
    then `limit-schedule 100 2 H` → count 1, `attempts` 0, `limit-due 99` exit 1, `limit-due 100`
    prints 100; a second `limit-schedule` while one is set fails `already scheduled` and leaves
    the count 1; `reserve-attempt`, `limit-hold 99` → prints 100, `attempts` 0, schedule kept;
    `limit-claim 99` exit 1; `limit-hold 100` exit 1; `limit-at` prints 100 before and after
    the hold and exits 1 once the schedule is claimed; `reserve-attempt`, `limit-claim 100` →
    count 1, schedule gone, `attempts` 0 (never below 0); a second `limit-claim` exits 1;
    `limit-verify <other>` exit 1 with `moved to another commit`, `limit-verify H` exit 0 and
    the manifest unchanged (same bytes), `limit-arm <other>` exit 1, `limit-arm H` exit 0, `limit-armed H` 0,
    `limit-disarm`, then `limit-armed H` 1; `limit-verify H` after `clear-attempts` → exit 1 `no
    scheduled relaunch`; second schedule → 2; third with cap 2 fails with `already relaunched 2
    time(s)`; `clear-attempts` and a new `start` drop all four fields; a manifest with
    `limit_relaunches: "1"` is invalid;
  - `limit-stop-write` safety (CLI, plus one in-process case that plants the first temp name
    `.limit-stop.<os.getpid()>.tmp` before calling the function): symlinks at
    `.ai/local/limit-stop`, `.ai/local/limit-stop.tmp` and the first temp name, each pointing at
    a sentinel file outside the checkout → the sentinel is byte-identical afterwards and
    `limit-stop` is a regular file holding the record; a FIFO at `.ai/local/limit-stop` and at the
    first temp name → returns within a scaled bound (never blocks) and `limit-stop` ends a regular
    file; `.ai/local` replaced by a symlink → exit 1, nothing written outside; the
    `limit-far` run above with a sentinel symlink at `.ai/local/limit-stop.tmp` leaves the
    sentinel unchanged and still stops with the unchanged message;
  - `observe relaunch 1700000000 'note'` → `state: paused`, `relaunch_at` 1700000000; a following
    `observe step build x` has no `relaunch_at`.
- `AI_LIMIT_RELAUNCH_MAX` is recorded in the manifest `env` when set at start (as
  `AI_RECOVER_MAX` in the test at ~4705).
- `test_usage_limit_beyond_wait_budget_stops` and all existing `limit`/`recovery` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_record` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k usage_limit` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- `common.sh` `ai_limit_pause`: before the budget `ai_die` (message unchanged), it runs
  `ai_helper limit-stop-write AGENT RESET` (reset is 0 unless it is in the future). In `workflow.py`,
  `limit-stop-write` validates its arguments, pins `.ai/local` and uses `write_record`.
  `limit-stop [--now]` reads `last-error` and `limit-stop` through `read_record`, which never
  follows symlinks or opens non-regular files. It checks the exact message, the agent and an
  age of 0–120 s, then prints `<Agent> <relaunch epoch>`.
- run-manifest: `LIMIT_FIELDS`, with validation in `limit_fields_valid`, plus
  `limit_relaunch()` for the `limit-schedule/due/at/hold/claim/verify/arm/armed/disarm/count`
  actions. `clear-attempts` drops the four fields, and `start` already writes a fresh dict.
  `limit-verify` keys on `limit_head`, which stays after a claim, so the claimed relaunch can verify.
- `observe relaunch AT NOTE` sets `relaunch_at`. `previous_observation` keeps only the base
  fields, so every other write drops it.
- `AI_LIMIT_RELAUNCH_MAX` is in `RUN_SETTINGS`, the `ai_config` keys, both `ai-recover` lists
  and the README config list. README and `docs/workflow.md` (usage limits, observation fields)
  are updated.
- Tests: 7 `test_limit_relaunch_record_*`. The planted `limit-stop.tmp` symlink comes from a
  wrapped mock `claude` mid-run, because ai-run's startup `paths` check refuses it earlier.
- Evidence: `-k limit_relaunch_record` Ran 7 OK. `-k usage_limit -k limit -k settings -k Docs`
  Ran 35 OK.
- Full gate: `ai-check` ran 824 tests in 628.5 s, longer than the 600 s tool limit. It had one
  failure, `test_pr_body_flow_this_repo_declares_the_flow_chart`, caused by the planner's
  handoff "## Flow chart" line rather than by T001 code. That line is fixed and the test now
  passes on its own (`-k flow_this_repo`). The full rerun is left to the host's post-task
  `ai-check`.
- Flow unchanged. The vault hub has a Log line for this task.


## T002 — Watchdog starts a due limit relaunch; `--timer-recovers`; no stall alarm while it waits (MC-01 part 1, watchdog)
Status: DONE
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
  logic: when not `alive` and `marker_snapshot(marker)` is None, run THIS copy's `python3
  <bin_dir>/lib/workflow.py run-manifest limit-at` in `root` (as `start_recovery` runs
  `run-manifest gate`; the only question is "is a relaunch scheduled, and when?"). The answer
  is a three-way state, written out as such (plan review round 4, P11: "exit 1 → 0" made
  `0 <= now` true for every unscheduled checkout): `scheduled_ns = None` when the helper exits
  non-zero or prints no valid integer (absent: no manifest, an approved run without a
  schedule, a finished run), else `AT * 1_000_000_000`. Launch only when `args.recover and
  scheduled_ns is not None and scheduled_ns <= now` → `start_recovery(…, stage='usage limit
  relaunch')`; None → nothing more (ai-recover announces itself) and continue with the normal
  probe; a refusal → notify `⛔ STOPPED, needs you: the usage-limit relaunch could not start:
  <reason>.` once per AT (key `relaunch:<AT>` kept in the dedupe record's `active` list while
  the schedule is unchanged). Absent → nothing launched, nothing notified, no `relaunch:` key.
  Pending (`scheduled_ns > now`) → nothing launched; the value only feeds the stall rule below
  (a pending schedule without `--recover` still suppresses the stall alarm: the run is
  waiting, not killed). Comment the three states at the site.
- Stall incident (~443–451): one predicate `relaunch_quiet`, written out beside the three
  states and commented: the stall rule is skipped while `now < paused_until(local)`, while the
  schedule is pending (`scheduled_ns is not None and scheduled_ns > now`), and while a due
  schedule is this probe's to handle (`scheduled_ns is not None and scheduled_ns <= now and
  args.recover`: launched, so ai-recover announces itself, or refused, so the `relaunch:<AT>`
  ⛔ is the one report). Plan review round 8, P19: a refusal writes no last-error, the phase
  stays `implementing`, `alive` was computed before the launch, and the `relaunch:<AT>` key does
  not dedupe `stalled`, so without this the second probe `STALL_CONFIRM_NS` later raised the
  ordinary `killed runner?` ⛔ on top of the refusal ⛔. Absent (`None`) → the stall rule as
  today; due without `--recover` → as today too (nothing relaunches; the killed-runner alarm is
  right). The host schedule is the authority (plan review round 3, P2:
  `limit-hold` restores a schedule whose pauses.log line was never written, and `.ai/local` is
  agent-writable anyway); ai-recover's pauses.log line (T003) stays as the quiet-time input of
  the hung rule and as history.
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
  - schedule due (`run-manifest limit-schedule <now-10> 2 <HEAD>` via the helper, no marker, no
    runner): `host_watchdog('--recover')` launches `…/ai-recover --stage usage limit relaunch`,
    writes no last-error, sends no notification, and with phase `implementing` and no
    last-error records no `stall_seen_ns` and no `stalled` key (the launch is this probe's
    handling of the due schedule, P19);
  - schedule in the future (`AI_WATCHDOG_NOW` before AT): nothing launched, no notification;
    with phase `implementing`, no last-error and a pauses.log line ending after now, two probes
    `STALL_CONFIRM_NS` apart raise no `stalled` incident;
  - P2 regression: schedule in the future persisted by the helper, phase `implementing`, no
    last-error, no marker, and NO `pauses.log` (or one whose last line ended in the past): two
    `--recover` probes `STALL_CONFIRM_NS` apart with `AI_WATCHDOG_NOW` before AT → no `stalled`
    incident, no ⛔, nothing launched (`systemd-run` never recorded), `watchdog.json` `active`
    empty; the same two probes without `--recover` → the same; then a probe with
    `AI_WATCHDOG_NOW` after AT and `--recover` launches `--stage usage limit relaunch`; with the
    schedule claimed (`limit-claim` via the helper) and still no pauses.log, the two probes
    DO raise `stalled` as today (the suppression is tied to the schedule, not to the phase);
  - due but refused (checkout copy, or changed gate): one ⛔ naming `usage-limit relaunch could
    not start`; a second probe sends nothing more; the P19 regression: the same refusal with
    phase `implementing`, no last-error, no marker, no runner and no `pauses.log` entry, two
    `--recover` probes more than `STALL_CONFIRM_NS` apart (`AI_WATCHDOG_NOW`) → exactly one
    notification overall (the refusal ⛔), no `stalled` key and no `stall_seen_ns` in
    `watchdog.json` after either probe; the same due schedule probed twice WITHOUT `--recover`
    → no launch, no relaunch notification, and the second probe raises the ordinary `stalled`
    ⛔ as today (the probe cannot handle it); after `run-manifest start` via the helper (a human
    rerun drops the schedule) two further `--recover` probes on an unchanged checkout raise
    `stalled` as today (the suppression is tied to the schedule);
  - absent schedule (P11), each as two `--recover` probes `STALL_CONFIRM_NS` apart with no
    runner and no marker: (a) no run manifest at all (fresh checkout under `AI_STATE_DIR`);
    (b) an approved run (`approve_run`) that never scheduled, phase `implementing`, no
    last-error (the stall rule's own case); (c) a completed run (`run-manifest finish` via the
    helper, or the fixture's `--no-pr` pipeline run to completion), phase `ready_for_review`
    → `systemd-run` never recorded, no relaunch-related notification (nothing containing
    `usage-limit relaunch`, no `relaunch:` key in `watchdog.json`); (a) and (c) send no
    notification at all; (b) sends exactly one, the normal `stalled` ⛔ of the second probe
    (`killed runner?`, as `test_watchdog_confirm_killed_runner_reported_once_after_five_minutes`
    asserts today: absence does not suppress the stall rule, and the stall incident IS a ⛔, so
    "no ⛔" holds only for (a) and (c); plan review round 5, P13); the same three without
    `--recover` → the same;
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
Done 2026-10-17. `scripts/lib/watchdog.py`: `relaunch_at(bin_dir)` runs THIS copy's
`run-manifest limit-at` and returns epoch ns or None (non-zero exit or no integer = absent).
`main()` computes `scheduled_ns` only with no runner and no marker; due + `--recover` →
`start_recovery(…, stage='usage limit relaunch')` (the default crash last-error is now written
only for a `crash…` stage; `--stage` passes the stage); refusal → incident `relaunch:<AT>`
`⛔ STOPPED, needs you: the usage-limit relaunch could not start: <reason>.`, deduped by
`active`. `relaunch_quiet` (pause running, pending schedule, or due with `--recover`) skips the
stall rule. `--timer-recovers` reuses `timer_state` (split out of `timer_status`, output
unchanged) and checks the service's `ExecStart=` for `"--recover"`.
Tests: 8 `test_limit_relaunch_watchdog_*` (due launch; pending with pauses.log; P2 schedule
alone with/without `--recover` then due launch then claimed → stalled; P19 refusal once over
three probes, then human start → stalled; checkout copy refused, due without `--recover` →
stalled; absent a/b/c with/without `--recover`; live marker / live pipeline; `--timer-recovers`).
`-k limit_relaunch_watchdog` 8 OK, `-k watchdog` 61 OK, ai-check PASS (832 tests, 460.9 s).
Mutation: removing the due-and-`--recover` clause fails 4 tests. docs/workflow.md "Checkout
health monitoring" updated; vault flow chart "When something goes wrong" gained the relaunch path
for both sides (ai-recover's scheduling/cap/resume is T003; written now on purpose).


## T003 — ai-recover schedules a relaunch for a limit-only stop and resumes it when due (MC-01 part 1, recovery)
Status: DONE
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
- Schedule lifecycle first (plan "Relaunch schedule lifecycle", P1/P2): right after
  `reserve-attempt` (~70–71) and the settings restoration (~72–80, which cannot escalate and
  gives `ai_notify` the run's `AI_NOTIFY_CMD`), before the trap (~91), the marker (~97) and
  every later escalation:
  a. `at=$(ai_helper run-manifest limit-hold)` exit 0 → the run is still waiting (a probe
     launched crash recovery after an interrupted scheduling or cleanup, or anything else
     started recovery early): restore the waiting state without Claude, a new reservation
     (`limit-hold` gave it back) or a count change: remove `.ai/local/last-error` (the limit
     message or the watchdog's crash default), `.ai/local/limit-stop` and the stale
     `.ai/local/pipeline.active`, append the pauses.log line exactly as the scheduling path
     does (one function `pause_line AT` used by both: a kill between `limit-schedule` and the
     append left none, plan review round 3 P2; the watchdog no longer needs it for the stall
     rule, T002, but the hung rule's quiet time and the history do), `ai_observe relaunch
     "$at" …`, notify the same ⏸ PAUSED line as the scheduling path (a repeat is harmless; none
     at all is not), print `Still waiting for the usage-limit relaunch after <time>.` and
     `exit 75` (no trap is set yet, so nothing else reports it).
  b. `count=$(ai_helper run-manifest limit-claim)` exit 0 → `relaunch=yes`. The schedule is
     consumed now, so a later escalation (`AI_AUTO_RECOVER=0`, gate, branch, plan decision,
     leftovers) is that relaunch's one terminal ⛔ and no probe starts it again.
- Verification first (plan "Verification point", round 3 P9; T014 owns the contract and its
  regressions, this task puts the site in place): one function `relaunch_verify` called at
  exactly ONE site, right after the branch check (~109–110) and BEFORE `args` are read, the
  plan-revision decision block (~114–129), the hard rules, the open-stage branch (~149–163)
  and the leftovers commit (~165–171). Body: `[[ $relaunch == yes ]] || return 0`;
  `why=$(ai_helper run-manifest limit-verify "$(git rev-parse HEAD)" 2>&1) || escalate "${why#Error: }
  while the usage-limit relaunch waited; nothing was committed." 'inspect the checkout, commit
  or discard what changed, then rerun ai-pipeline.'` (the helper's reason is `the branch moved
  to another commit` here; T012 adds `the checkout changed` and drops the argument; the full
  texts in the plan note are `the branch moved to another commit while the usage-limit relaunch
  waited; nothing was committed.` / `the checkout changed while the usage-limit relaunch
  waited; nothing was committed.`, so build the message from the helper's reason and never
  hard-code it twice). Nothing before this site may commit, stash, check out,
  write a tracked file or start a session; `escalate` writes only `.ai/local` and host state.
  Comment the rule at the site: every later step transforms a VERIFIED tree.
- After the plan-revision decision block (~129) and BEFORE the hard rules (~131):
  1. `relaunch == yes`: `ai_notify "▶ RESUMED after the usage limit (relaunch $count/$cap):
     $branch."`; then the transitions of the verified tree, in this order: the existing
     open-stage branch (~149–163) if a stage is open (its scope check stays; a human in-scope
     edit was already caught by `relaunch_verify`); else the record-stop-leftovers block
     (~165–171, factor it into a function used by both paths: a dirty tree confined to
     `.ai/state.md`, `.ai/run-log.md`, `.ai/handoff.md` is the stopped run's own bookkeeping,
     committed as today); then, when the checkout is still dirty: `ai_helper run-manifest
     limit-arm "$(git rev-parse HEAD)"` exit 0 → keep the preserved task work uncommitted and
     `resume` (the resumed pipeline and ai-run accept exactly this tree once, T011); exit 1 is
     an internal inconsistency (nothing may have touched the checkout since the verification,
     under the lock) → escalate with the same wording as `relaunch_verify`. Clean → `resume`.
     `resume` takes an optional notification so the relaunch does not also say `🔧 Recovered
     (n/max)`.
  2. Limit-only stop: `read -r agent at < <(ai_helper limit-stop)` succeeds →
     cap 0 → fall through (hard rule, today's ⛔);
     `"$AI_BIN/ai-watchdog" "$AI_ROOT" --timer-recovers` fails → escalate with the reset time
     (`date -d @"$at" '+%a %H:%M'`) and the install hint (current-plan wording);
     `ai_helper run-manifest limit-schedule "$at" "$cap" "$(git rev-parse HEAD)"` fails →
     escalate `usage limit again after $cap relaunch(es) in this run.` / `rerun ai-pipeline after
     the reset.` (T012 drops the HEAD argument; T016 adds `"$stage"`, the `--stage` this
     ai-recover was started with, i.e. the pipeline's stop stage: the arm is later granted only
     for `implementation`);
     else `pause_line "$at"` (the pauses.log line), `ai_observe relaunch "$at" …` (not `pause`:
     the dashboard's evidence of a scheduled relaunch, T004), the ⏸ notification, remove
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
    and no `🔧 Recovered`; `attempts` 0 at finish; the stop's bookkeeping leftovers are in a
    `record stop during` commit made AFTER the verification (the run log of ai-recover's
    stderr, or the commit's parent being the scheduled HEAD);
  - HEAD moved during the wait, clean tree (round 3 P9): schedule as above, the test makes one
    commit (any tracked file), AT into the past, relaunch → exactly one ⛔ containing `moved to
    another commit while the usage-limit relaunch waited` and `nothing was committed`,
    `recovery_calls()` empty, no session, HEAD still the test's commit, no new commit, no
    `limit_resume`, the manifest has no `limit_relaunch_at` (claimed: terminal);
  - cap: `AI_LIMIT_RELAUNCH_MAX=1` and a second limit stop after one relaunch → ⛔ with
    `usage limit again after 1 relaunch(es)`;
  - `AI_LIMIT_RELAUNCH_MAX=0` → ⛔ `this kind of stop always needs a human` (today);
  - no timer installed → ⛔ naming the reset time and `--install-timer --recover`; no schedule;
  - a last-error with the limit message plus another line → today's hard-rule ⛔, no schedule;
  - terminal escalation after a claim (P1): schedule (as above), switch the fixture to another
    branch, set AT into the past, then two `host_watchdog('--recover')` probes with
    `mock_systemd_run` (if the mock only records the command, the test runs the recorded
    `ai-recover` command itself between the probes, as the existing watchdog-recover tests do):
    exactly one ⛔ naming `not the approved run's branch`, `recovery_calls()` empty, the manifest
    has no `limit_relaunch_at`, and the second probe launches nothing (`systemd-run` recorded
    once);
  - interrupted scheduling (P2), three variants after a real scheduling run, each followed by
    `ai-recover --stage 'crash (pipeline killed or restarted)'` while AT is still in the future:
    (i) last-error and limit-stop restored as they were and `pipeline.active` holding a dead PID
    (a kill right after `limit-schedule`); (ii) last-error removed, `pipeline.active` with a dead
    PID (a kill during cleanup; the watchdog's crash last-error written as `start_recovery`
    does); (iii) a watchdog probe on (ii) with `--recover`, which launches crash recovery for the
    dead marker; (iv) as (i) but with `pauses.log` removed (a kill right after
    `limit-schedule`, before the append) → every variant exits 75 with `Still waiting`,
    `limit_relaunches` still 1, `attempts` 0, no `recovery_calls()`, no `🔧`/`⛔`, last-error,
    limit-stop and pipeline.active gone, observation `relaunch_at` = AT, and pauses.log's last
    line parses with `watchdog.paused_until` to AT (also in (iv)); then two
    `host_watchdog('--recover')` probes `STALL_CONFIRM_NS` apart with `AI_WATCHDOG_NOW` before
    AT send nothing and launch nothing (round 3 P2); then with AT in the past one relaunch
    resumes as above (`relaunch 1/2`).
- `test_recovery_*`, `test_usage_limit_*`, `test_watchdog_*` pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-17. `scripts/ai-recover`: `cap` (`AI_LIMIT_RELAUNCH_MAX`, `^[0-9]$`, default 2) is
validated right after the settings restore, because the hold path needs it before `max`. One
function, `relaunch_wait AT LIMIT WHAT COUNT`, serves the hold and schedule paths: the pauses.log
line (stamp and length share one clock, so `paused_until` == AT), `observe relaunch`, the ⏸
line, and removal of last-error/limit-stop/pipeline.active. `limit-hold` → `Still waiting …`,
exit 75 (no trap yet). `limit-claim` → `relaunch=yes`; with no last-error the reason becomes
`stopped at a usage limit; relaunched after the reset`. `relaunch_verify` is called once, after
the branch check and before `args`; its reason comes from the helper (`relaunch_moved`).
`resume WHY [NOTE]` (an empty NOTE notifies nothing). The open-stage and leftovers blocks were
factored into `resume_open_stage [quiet]` and `record_stop_leftovers`, used by both paths. After
the decision block, a claimed relaunch sends ▶ RESUMED, then runs the open stage / leftovers
commit / `limit-arm` (refusal → same wording) and resumes. A limit-only stop then checks
`--timer-recovers` and `limit-schedule`, runs `relaunch_wait`, sets `AI_STOP_NOTIFIED`, runs
`trap - EXIT` and exits 75. Usage text updated.
The relaunch's leftovers commit is `record stop during usage limit relaunch` (its `--stage`).
Tests: 7 `test_limit_relaunch_recover_*` (schedule then resume, with the parent of the record
commit == the scheduled HEAD; moved HEAD; cap 1; off; no timer + limit message with an extra
line + positive control; claimed relaunch on another branch stops once and the second probe
launches nothing; interrupted scheduling variants i–iv, then quiet probes, then resume 1/2).
Evidence: `-k limit_relaunch` 22 OK, `-k recovery` 65 OK, `-k Docs` 3 OK, `ai-check` PASS (839
tests, 490.9 s). Mutation: dropping the `relaunch_verify` call fails the moved-HEAD test.
Docs: README "Usage limits", docs/workflow.md "Interruption, limits, and recovery" and the new
"Usage-limit relaunch" paragraph in "Recovery contract". Vault: the flow chart's "When something
goes wrong" (limit-only decision, fallbacks, relaunch check) and its notifications table were
updated, and a hub Log line was added.
Limitation until T011/T015: an armed relaunch (with uncommitted task work) resumes into
ai-pipeline's clean-checkpoint stop.


## T012 — Preserved-work binding: the relaunch exception admits the exact preserved tree (MC-01 part 1, plan review round 2 P3/P9 design task)
Status: DONE
Dependencies: T003
Model: opus

### Goal
The usage-limit resume exception is bound to the preserved HEAD, index and worktree contents
recorded when the relaunch is scheduled, re-verified under the lock before it is armed and at
every acceptance site, so a change made during the wait is never absorbed; and the helpers
T011 needs to tell "task marked DONE before the limit" from "task still in progress" exist.

### Implementation notes
- Design: `.ai/current-plan.md` "Preserved-work resume (plan review round 2 redesign)". This
  replaces the HEAD-only binding of T001/T003 (round 1 P3); T011 consumes it.
- `scripts/lib/workflow.py` `worktree_digest(root)` + command `worktree-digest` (prints the
  hex): it IS the existing `tree_snapshot(root)` (~2245–2276), called with the checkout root;
  write no second digest (plan review round 3, P10). `tree_snapshot` already covers HEAD, the
  staged diff (`git diff --cached --binary`: binds staged-only changes), every path of
  `git ls-files --cached --others --exclude-standard -z` outside `.ai/local/` with kind, mode
  and bytes or link target, submodules recursively (`repo` + the nested snapshot of their HEAD,
  index and working contents) and uninitialised submodules walked on the filesystem; it does
  NOT skip `.ai/state.md`, `.ai/run-log.md`, `.ai/handoff.md` or `.ai/reviews/` (a human edit
  there during the wait must count). Document in the docstring that the relaunch binding
  relies on it, so a future "skip" there needs this comment changed. Comment the plan's
  "Verification point" rule where the digest is recorded: the digest is taken by
  `limit-schedule` after the stop's bookkeeping was written and before any commit, and the
  relaunch verifies it before it touches the checkout (T003 `relaunch_verify`, T014).
- `run_manifest`: new optional field `limit_tree` (64-hex); `limit_resume` becomes an object
  `{"head": 40-hex, "tree": 64-hex}` (wrong type → invalid manifest, as T001's fields).
  Signatures change (T001's HEAD argument removed; the helper computes from the checkout, the
  shell passes no binding value): `limit-schedule AT CAP` records `limit_head` and `limit_tree`
  (T016 appends a STAGE argument and `limit_stage`; T017 copies the manifest's `task` into
  `limit_task` and adds `task` to `limit_resume`; write the parser so one more positional is
  a one-line change); `limit-verify` (read only) recomputes both and exits 0 silently only when both equal the
  recorded ones, else exit 1 with `the branch moved to another commit` (head) or `the checkout
  changed` (tree) on stderr (ai-recover appends ` while the usage-limit relaunch waited;
  nothing was committed.`), `no scheduled relaunch` when `limit_head`/`limit_tree` are absent;
  `limit-arm` recomputes both and sets `limit_resume` only on an exact match of both, else
  exit 1 with the same reasons, nothing written; `limit-armed` recomputes and exits 0 only when
  both equal `limit_resume`; `limit-disarm` unchanged; `clear-attempts`/`start` drop
  `limit_tree` too.
- `scripts/ai-recover` (T003's claimed-relaunch path): `limit-schedule "$at" "$cap"`;
  `relaunch_verify` calls `limit-verify` without an argument and the dirty branch calls
  `limit-arm` without an argument; both escalate with the helper's reason followed by ` while
  the usage-limit relaunch waited; nothing was committed.` / `inspect the checkout, commit or
  discard what changed, then rerun ai-pipeline.`. The order (verify before anything else) is
  T003's; do not move the site. No commit, no stash, no checkout before or on a failing path.
- `tasks newly-done REV` (in `task_command`): parse `git show REV:.ai/tasks.md` with
  `tasks(text)` and the working queue with `tasks()`; print the IDs DONE in the working queue
  and not DONE (or absent) at REV, one per line, file order; an unparsable queue fails as
  `tasks check` does. Used by T011.
- No pipeline/ai-run acceptance change here (T011). Docs: docs/workflow.md "Interruption,
  limits, and recovery" says the relaunch continues exactly the tree it stopped with
  (submodules included) and that any change during the wait escalates. Flow unchanged in this
  task (T011 updates the chart).

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-recover, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_binding_*` in tests/test_workflow.py:
  - `worktree-digest` unit cases on a fixture checkout: equals `tree_snapshot` of the same
    checkout (the test's existing `tree_snapshot()` helper, ~9634); unchanged when only
    `.ai/local/` files change; changes for each of: an edited tracked file, an edited
    `.ai/state.md`, an edited `.ai/reviews/dispositions.md`, a new untracked file, a deleted
    tracked file, a staged-only change (an edit staged with `git add`, then the worktree file
    restored to HEAD's bytes: only the index differs), a mode change, a symlink target change,
    a new commit; with a submodule (fixture as `test_deps_status_tree_snapshot_covers_submodules`,
    ~9663): an edited submodule file and a new commit inside the submodule each change the
    digest while the parent's HEAD and `git diff --cached` are unchanged (round 3 P10);
  - manifest: `limit-schedule 100 2` records `limit_head` = HEAD and `limit_tree` = the digest;
    `limit-verify` exits 0 and leaves the manifest byte-identical; `limit-arm` arms on the same
    tree and `limit-armed` exits 0; after writing one byte to an unrelated tracked file
    `limit-verify` exits 1 with `the checkout changed` and `limit-armed` exits 1; a fresh
    schedule, then a new untracked file → `limit-verify` and `limit-arm` exit 1 naming `the
    checkout changed`, no `limit_resume`; a fresh schedule, then a commit → both name `moved
    to another commit`; a fresh schedule, then an edit inside the submodule only → both exit 1
    `the checkout changed`; a manifest with `limit_resume` as a string is invalid;
  - end-to-end (fixtures as T003's `test_limit_relaunch_recover_*` with `limit-far`; T011's
    dirty mock does not exist yet, and the dirty-at-scheduling case is covered by the manifest
    units above and by T011): schedule, then the test edits an unrelated tracked file AND adds an untracked file without
    changing HEAD, sets AT into the past and runs `ai-recover --stage 'usage limit relaunch'` →
    exactly one ⛔ naming `changed while the usage-limit relaunch waited`, both human changes
    byte-identical on disk, no commit made (HEAD unchanged), no `limit_resume`,
    `recovery_calls()` empty, no implementation session ran (the bookkeeping-only, open-stage
    and submodule end-to-end cases are T014's);
  - `tasks newly-done HEAD`: none on a clean queue; `T002` after the test sets T002 DONE in the
    working file; a task DONE at HEAD and in the file is not printed; a malformed working queue
    fails.
- T001's and T003's tests updated for the new signatures (named in the result); all
  `test_limit_relaunch_*`, `test_recovery_*` and `test_usage_limit_*` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-17 Claude: done. `workflow.py`: `worktree_digest = tree_snapshot` (no second digest;
the docstring states the relaunch binding relies on it covering bookkeeping) + command
`worktree-digest`; `limit_binding()`/`limit_mismatch()`; manifest field `limit_tree` (64-hex),
`limit_resume` = `{"head","tree"}` (exact keys, else invalid); `limit-schedule AT CAP` computes
both itself (Verification point comment there); `limit-verify`/`limit-arm` take no argument,
fail `no scheduled relaunch` / `the branch moved to another commit` / `the checkout changed`;
`limit-armed` recomputes against `limit_resume`; `clear-attempts`/`start` drop `limit_tree`
(LIMIT_FIELDS). `tasks newly-done REV` (unknown REV fails; no queue at REV = all DONE are new).
`ai-recover`: no HEAD arguments; the dirty-branch `limit-arm` escalates with the helper's reason.
docs/workflow.md updated. New tests: `test_limit_relaunch_binding_worktree_digest_covers_the_whole_tree`,
`..._worktree_digest_covers_submodules`, `..._manifest_records_and_verifies_the_tree`,
`..._recover_human_change_escalates_untouched`, `..._tasks_newly_done`. Updated for the new
signatures: `limit_relaunch_fixture`, `test_limit_relaunch_watchdog_absent_schedule_changes_nothing`,
`test_limit_relaunch_record_manifest_schedule_lifecycle`. Evidence: `-k limit_relaunch` Ran 27 OK,
`-k recovery` Ran 65 OK, `-k usage_limit` Ran 6 OK, `.ai/bin/ai-check` Ran 844 OK.


## T014 — Relaunch binding verification contract: one verification site before any checkout mutation (MC-01 part 1, plan review round 3 P9/P10 design task)
Status: DONE
Dependencies: T003, T012
Model: opus

### Goal
A claimed usage-limit relaunch accepts the checkout only after one verification of HEAD and the
whole tree (submodules included) against what was recorded at scheduling, performed before any
commit, resume, arm or session; every change made during the wait, wherever it lives, stops the
relaunch with the checkout exactly as found, and the transitions the relaunch may then apply to
the verified tree are stated and tested as one contract.

### Implementation notes
- Design: `.ai/current-plan.md` "Preserved-work resume", part "Verification point (plan review
  round 3 redesign, T014)". T003 placed `relaunch_verify` and T012 made `limit-verify` compare
  HEAD and the `tree_snapshot` digest; this task owns the contract as a whole: audit the site,
  pin the transitions, cover the cases the earlier design missed, and document it.
- Audit `scripts/ai-recover` from the claim to `resume`: list in the result every statement that
  writes to the checkout (git commit/add/stash/checkout, any write outside `.ai/local`), reads
  the checkout to decide (open-stage scope check, leftovers test, dirty test) or starts a
  session, and show each is after the single `relaunch_verify` call. Any that is not → move it
  below the site. `relaunch_verify` has exactly one call site (a `grep -c` in a test of the
  installed script is fine: `tests/test_workflow.py` already reads scripts for such checks).
- Transition table as a comment block right after the `▶ RESUMED` notification, matching the
  plan: (a) open stage → `resume` (scope check kept); (b) dirty confined to `.ai/state.md`,
  `.ai/run-log.md`, `.ai/handoff.md` → leftovers commit → `ai_gate_check` → `resume`; (c) dirty
  otherwise → `limit-arm` → `resume`; (d) clean → `resume`. Nothing else is permitted; a new
  branch there needs the table changed. `limit-arm` failing in (c) escalates with the verify
  wording (an internal inconsistency; the result records that it cannot be reached by a human
  change, since the lock is held from the verification on).
- Reasons: the ⛔ texts are built from the helper's reason (`the branch moved to another
  commit` / `the checkout changed`) + ` while the usage-limit relaunch waited; nothing was
  committed.`; `Next:` is `inspect the checkout, commit or discard what changed, then rerun
  ai-pipeline.` for both. Check T003's and T012's tests assert these exact texts; adjust them
  here if they drifted (named in the result).
- docs/workflow.md "Interruption, limits, and recovery" and "Recovery contract": one paragraph
  "What a relaunch accepts": the verification, the four transitions, and that a change anywhere
  in the checkout during the wait (tracked, untracked, staged, bookkeeping, a commit, a
  submodule) escalates with nothing committed. README "Recovery": one sentence.
- Flow chart (vault): the relaunch branch reads "verify HEAD and tree first, else ⛔ (nothing
  committed)"; T011 adds the preserved-work wording after it.

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py, docs/workflow.md, README.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_verify_*` in tests/test_workflow.py (fixtures as T003's
  `test_limit_relaunch_recover_*` with `limit-far`, timer installed with `--recover`; each case
  schedules a relaunch, changes the checkout as stated, sets AT into the past and runs
  `ai-recover --stage 'usage limit relaunch'`; unless stated, every case asserts: exactly one
  ⛔ containing `while the usage-limit relaunch waited` and `nothing was committed`, HEAD
  unchanged, `git status --porcelain` identical before and after (same bytes), every changed
  file byte-identical, no `limit_resume`, no `limit_relaunch_at`, `recovery_calls()` empty, the
  mock recorded no session, no `▶ RESUMED` notification):
  - bookkeeping-only human edit (round 3 P9): the test appends one line to `.ai/state.md` (the
    tree stays confined to the three bookkeeping files) → ⛔ `the checkout changed`; no
    `record stop during` commit exists for the relaunch;
  - clean checkout whose HEAD moved (P9): the test commits the stop's leftovers itself, then
    one more commit → ⛔ `moved to another commit`; no further commit;
  - in-scope edit during an open stage (P9): after scheduling the test opens a triage stage in
    host state (`run-manifest stage-set triage <HEAD>` through the helper, as ai-pipeline does
    at ~561) and edits `.ai/reviews/dispositions.md` (inside `triage-scope`) → ⛔ `the checkout
    changed`; the stage record is still open and unchanged; no `🔧 Recovering` notification; the
    same with a `plan-revision` stage and an edit to `.ai/reviews/plan-dispositions.md`;
  - submodule file (P10): fixture with a submodule as `test_deps_status_tree_snapshot_covers_submodules`;
    after scheduling the test edits a file inside the submodule (parent HEAD and `git diff
    --cached` unchanged) → ⛔ `the checkout changed`, the submodule edit preserved;
  - submodule HEAD (P10): after scheduling the test commits inside the submodule (parent HEAD
    and index unchanged) → ⛔ `the checkout changed`, the submodule's HEAD and the parent's
    gitlink unchanged by recovery (no `git add` of the submodule path);
  - positive control: no change during the wait → the relaunch resumes (`▶ RESUMED`), the
    leftovers commit `record stop during` exists and its parent is the scheduled HEAD, the
    pipeline completes; the same with a submodule present and untouched;
  - `relaunch_verify` is called from exactly one site in `scripts/ai-recover` (and the installed
    `.ai/bin/ai-recover` of the fixture), and the escalation texts of T003/T012 match the exact
    wording above.
- `test_limit_relaunch_*`, `test_recovery_*`, `test_usage_limit_*` and `test_watchdog_*` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_verify` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- Audit of `scripts/ai-recover` (lock → `resume`). Before the single `relaunch_verify` call:
  only `.ai/local/` writes (`recovery-decision.txt` removal, `pauses.log`, `last-error`,
  `pipeline.active`, via `relaunch_wait`/`escalate`), host-state actions (`state-root-check`,
  `run-manifest gate`/`reserve-attempt`/`env`/`limit-hold`/`limit-claim`), observations and
  notifications, and the read-only gate/branch checks (`ai_guard_digest`, `ai_gate_check`,
  `git symbolic-ref`). After it: `run-manifest args`, `plan-revisions decision` (+ its
  `stage-clear`), `resume_open_stage` (`run-manifest stage`, `triage-scope`/`plan-revision-scope`,
  `resume`), `record_stop_leftovers` (`git status`, `git add`, `git commit`, `ai_gate_check`),
  the dirty test and `limit-arm`, `resume` (exec ai-pipeline); the non-relaunch path (limit
  schedule, hard rules, Claude session, `git add --all`/commit/reset) also lies below it. No
  statement needed moving: T003 already placed the call there.
- Transition table added as a comment right after `▶ RESUMED` (a)–(d) as the plan states.
  `limit-arm` refusing in (c) escalates with the verify wording; no host step between the
  verification and the arm touches the checkout and the checkout lock is held, so only an
  out-of-band writer ignoring the lock could reach it.
- Escalation texts: T003's and T012's tests assert the helper reason + `while the usage-limit
  relaunch waited` and `nothing was committed` (no drift, unchanged); the new tests assert the
  whole `Recovery: … nothing was committed. Next: inspect the checkout, commit or discard what
  changed, then rerun ai-pipeline.` text.
- 9 `test_limit_relaunch_verify_*` tests: bookkeeping-only edit, clean moved HEAD, in-scope edit
  with an open triage stage (`.ai/reviews/dispositions.md`) and with an open plan-revision stage
  (`.ai/reviews/plan-dispositions.md`), submodule file edit, submodule commit (gitlink and sub
  HEAD unchanged), positive controls without and with an untouched submodule, single call site
  in `scripts/ai-recover` and the fixture's `.ai/bin/ai-recover` with no mutating/deciding
  statement before it. Deviation: the open-stage tests write the host stage record that
  `run-manifest stage-set` writes (same file, fields and branch) instead of calling
  `stage-set`, which requires a published review/plan review that this fixture (stopped during
  implementation) does not have; `run-manifest stage` reads it back before the relaunch.
- Mutation: the call moved below `record_stop_leftovers` fails all 9 tests.
- docs/workflow.md: "What a relaunch accepts" paragraph in the recovery contract, a pointer in
  "Interruption, limits, and recovery"; README recovery sentence; vault flow chart relaunch node.
- Validation: `-k limit_relaunch_verify` 9 OK; `-k limit_relaunch` 36 OK; `-k recovery` 65 OK;
  `-k usage_limit` 6 OK; `-k watchdog` 61 OK; `-k Docs` 3 OK; `.ai/bin/ai-check` PASS (853
  tests, 464.9 s).


## T017 — Preserved work is bound to the interrupted task: manifest task record, task-bound arm (MC-01 part 1, plan review round 6 P3 design task)
Status: DONE
Dependencies: T003, T012
Model: opus

### Goal
The usage-limit arm names the task whose output the preserved tree is, recorded in host state by
ai-run before every implementation session, so the resumed ai-run decides what to do with the
preserved work from that task's status instead of inferring the task from the queue's diff; a
task committed DONE before the limit, with further edits preserved, is then checkpointed under
full validation before any session or the final handoff (T011 places the consumer rule on this
binding).

### Implementation notes
- Design: `.ai/current-plan.md` "Preserved-work resume", part "Preserved work is bound to the
  interrupted task (plan review round 6 redesign, T017)". Verified at the revision: T011's
  consumer chose by counting `tasks newly-done HEAD`; a session that committed its task DONE
  (queue and source in HEAD), edited more and hit the limit leaves `newly-done` empty, `tasks
  next` prints `none` for a one-task queue (scripts/lib/workflow.py ~642–647), and ai-run's
  final-handoff path (scripts/ai-run ~623–648) validates the dirty tree but commits only
  `.ai/state.md`/`.ai/run-log.md`, so `verify_checkpoint 'final handoff'` (~242–254) dies on
  `uncommitted changes after the checkpoint`; with more tasks the next session would start on
  the finished task's leftovers.
- `scripts/lib/workflow.py` `run_manifest` (~1279): optional field `task` (string matching
  `^T\d{3,}$`, the queue's ID pattern; wrong type → invalid manifest, as T001's fields). New
  actions `task-set ID` (validate, write) and `task-clear` (drop; missing is fine), each one
  atomic write; `start` writes a fresh dict (drops it), `clear-attempts` drops it. Comment: the
  field is read only by `limit-schedule`; it is host state written by ai-run (host code, like
  `outcome attempt-open`), never read from the checkout.
- `limit-schedule AT CAP [STAGE]` (T012's signature; T016 adds STAGE) copies `task` into
  `limit_task` (absent when `task` is absent). `limit-arm` (after T016's stage check, before
  T012's HEAD/tree comparison): `limit_task` absent → exit 1 with `the usage-limit stop left
  uncommitted changes with no task recorded` on stderr, nothing written; on success
  `limit_resume = {"head", "tree", "task"}` (T012's object plus `task`; a `limit_resume`
  without a string `task` is invalid). `limit-armed` compares head and tree as T012 (the task is
  not recomputed); `limit-disarm` unchanged. New read-only action `limit-task`: print
  `limit_resume.task`, exit 0; not armed → exit 1 silently. `clear-attempts`/`start` drop
  `limit_task`.
- `scripts/ai-recover` (T003's transition (c)): a failing `limit-arm` already escalates with
  the helper's reason; for the task reason the ⛔ reads `the usage-limit stop left uncommitted
  changes with no task recorded; nothing was committed.` / `inspect the checkout, commit or
  discard what changed, then rerun ai-pipeline.` (built from the helper's reason as T014
  prescribes; add the row to T014's transition table comment).
- `scripts/ai-run` (implementation mode only: `-z "$plan_file"` and not triage): right before
  `claude_session` of the task loop (~663, beside `ai_helper state implementing`),
  `ai_helper run-manifest task-set "$active_task" 2>/dev/null || printf '%s\n' 'Note: could
  not record the task in the run manifest.' >&2` (best effort: a standalone `ai-run --approved`
  has no manifest and no relaunch; inside a pipeline a lost record makes a later `limit-arm`
  fail closed); after the iteration's bookkeeping commit (~716) `ai_helper run-manifest
  task-clear 2>/dev/null || true`; the same `task-clear` once before the loop (after T011's arm
  consumption, which reads `limit_resume.task`, never `task`), so a stale value from an
  interrupted run never binds a later stop. `on_exit` does not touch it: the limit stop is an
  `ai_die` inside the session and the record must survive it.
- The consumer rule is T011's (plan note, rule 3): `bound=$(ai_helper run-manifest limit-task)`
  read BEFORE `limit-disarm`, then by `tasks status "$bound"`. This task only provides the
  binding and the recording; before T011 the resumed pipeline still refuses the armed tree with
  `Start from a clean checkpoint` (say so in the result).
- docs/workflow.md "Interruption, limits, and recovery" (the paragraph T011/T014/T016 write):
  the relaunch continues the task the limited session was working on, named in the host
  manifest. Flow unchanged in this task (T011 updates the chart).

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-recover, scripts/ai-run, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_bound_*` in tests/test_workflow.py:
  - manifest units (after `run-manifest start`): `task-set T001` → `task` recorded; `task-set
    x1` → exit 1, nothing written; `task-clear` drops it, twice (idempotent); `limit-schedule
    100 2 [STAGE]` after `task-set T001` → `limit_task` `T001`; without a task → no
    `limit_task`; `limit-arm` on the dirty scheduled tree with `limit_task` → `limit_resume.task`
    is `T001` and `limit-task` prints `T001`; without `limit_task` → exit 1 `no task recorded`,
    no `limit_resume`, the manifest otherwise byte-identical; `limit-task` exits 1 when not
    armed; a manifest with `task: 7` or a `limit_resume` lacking `task` is invalid;
    `clear-attempts` and a new `start` drop `task` and `limit_task`;
  - ai-run records: a two-task run with a mock that copies `run.json` (via `AI_STATE_DIR`) into
    `.ai/local/` during its session → the copy taken during T001's session holds `task: T001`,
    the one during T002's session `task: T002`, and the manifest holds no `task` after the run
    completes; a `limit-far` stop in the first session (`AI_LIMIT_MAX_WAIT=60`) leaves `task:
    T001` in the manifest; a standalone `ai-run --approved` without a manifest prints the note
    once and completes;
  - end-to-end (fixtures as T016's stage-bound case: last-error the limit message, a valid
    `limit-stop`, an uncommitted source edit, `ai-recover --stage implementation` with the
    timer installed): with no `task` in the manifest → scheduled with no `limit_task`; AT into
    the past; relaunch → exactly one ⛔ containing `no task recorded` and `nothing was
    committed`, the edit byte-identical, HEAD unchanged, no `limit_resume`, no
    `limit_relaunch_at` (claimed: terminal), `recovery_calls()` empty, no session; the positive
    control with `task-set T001` before the stop → `limit_task` `T001` at scheduling and, after
    the relaunch's `limit-arm`, `limit_resume.task` `T001` (the resumed run's handling of the
    armed tree is T011's; assert only the manifest here).
- T001's, T003's and T012's tests updated for the new fields (named in the result); all
  `test_limit_relaunch_*`, `test_recovery_*` and `test_usage_limit_*` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_bound` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE 2026-10-17.
- `scripts/lib/workflow.py`: manifest `task` (`^T\d{3,}$`, else invalid), `task-set ID` /
  `task-clear` (idempotent); `limit_task` added to `LIMIT_FIELDS`; `limit-schedule` copies
  `task` into `limit_task`; `limit-arm` without `limit_task` fails `the usage-limit stop left
  uncommitted changes with no task recorded` before the HEAD/tree comparison, writing nothing;
  `limit_resume = {head, tree, task}` (a resume without a valid `task` is invalid); new read-only
  `limit-task`; `clear-attempts` and `start` drop `task` and `limit_task`. T016's STAGE argument
  does not exist yet (T016 is TODO): the signature stays `limit-schedule AT CAP`.
- `scripts/ai-recover`: transition (c) escalates the task reason as `…no task recorded; nothing
  was committed.` / `inspect the checkout, commit or discard what changed, then rerun
  ai-pipeline.`; other refusals keep the verify wording; table comment updated.
- `scripts/ai-run`: `task-clear` once before the task loop, `task-set "$active_task"` right
  before each implementation session (note on failure), `task-clear` after the bookkeeping commit;
  `on_exit` untouched, so a limit stop keeps the record.
- Tests: 6 `test_limit_relaunch_bound_*` (manifest units, ai-run records per session with a
  `MOCK_COPY_MANIFEST` mock hook, limit stop keeps the task, standalone note once, end-to-end
  relaunch without a task → one ⛔ and nothing touched, positive control arms `T001`). Updated
  T001's `test_limit_relaunch_record_manifest_schedule_lifecycle` and T012's
  `test_limit_relaunch_binding_manifest_records_and_verifies_the_tree` (task-set before
  scheduling, `task` in `limit_resume`, new invalid cases). T003's tests needed no change (the
  pipeline's ai-run records T001 before the limited session).
- Validation: `-k limit_relaunch_bound` 6 OK; `-k limit_relaunch` 42 OK; `-k recovery` 65 OK;
  `-k usage_limit` 6 OK; `.ai/bin/ai-check` PASS (859 tests).
- Limitation: nothing consumes the binding yet (T011). The resumed pipeline still refuses the
  armed tree with `Start from a clean checkpoint`. Flow chart unchanged (T011 updates it).

## T011 — Limit relaunch resumes preserved task work in the normal implementation session (MC-01 part 1, plan review round 1 P3)
Status: DONE
Dependencies: T014, T017
Model: opus

### Goal
A usage limit that stops an implementation session after it edited source or marked its task
IN_PROGRESS no longer ends in ⛔ after the reset: the scheduled relaunch hands exactly that
preserved tree, once, to the normal implementation session of the same run, which reconciles it
under the unchanged validation and checkpoint safeguards, with no recovery decision session.

### Implementation notes
- Design: `.ai/current-plan.md` "Relaunch schedule lifecycle", part "Preserved task work", and
  "Preserved-work resume (plan review round 2 redesign)" including "Verification point (round
  3 redesign, T014)" and "Preserved work is bound to the interrupted task (round 6 redesign,
  T017)". T001/T012 provide `run-manifest limit-arm` / `limit-armed` (no arguments: they
  recompute HEAD and the tree digest, T012) / `limit-disarm`; T017 provides the manifest `task`
  record, `limit_task`, `limit_resume.task` and `limit-task`; T003/T012/T014 verify the
  checkout first and arm it in ai-recover's claimed-relaunch path only for the exact tree
  recorded at scheduling.
- An armed tree is accepted only where today's clean-checkout checks stand between the resumed
  pipeline and ai-run's first implementation session, and only when ALL hold: the process is a
  resume (`AI_RECOVERY_ATTEMPT` set; a human start runs `run-manifest start`, which drops the
  arm), `ai_helper run-manifest limit-armed` exits 0, and no stage is open. Factor the three
  conditions into one shell function per script (`armed_resume`) and the acceptance into ONE
  predicate `clean_or_armed` (true for an empty `git status --porcelain --untracked-files=all`
  or when `armed_resume` holds; plan "Armed-tree acceptance (plan review round 4 redesign,
  T015)": T015 owns the contract and its matrix, this task puts the predicate at every site).
  Sites (re-check line numbers): `scripts/ai-pipeline` ~123–125 (start-from-clean);
  `reconcile_disputes` BOTH tests: ~326–327 (status `none` with a dirty tree would
  `recheck_fail`; `clean_or_armed` admits the armed tree) and the final ~349 (`the checkout is
  not clean after recording it.`, reached with a settled `verified` re-check whatever happened
  before: plan review round 4 P3, the case that defeated the resume); `scripts/ai-run`
  ~148–149. No host write while armed (contract rule 2): inside `reconcile_disputes`, when
  `armed_resume` holds and the status is `pending` (its re-check would review a dirty tree and
  commit) or any of `.ai/reviews/recheck.md`, `disputes.md`, `fallback-log.md` is dirty (the
  ~339–345 `host_commit` would move HEAD under the arm), `recheck_fail 'preserved task work
  carries uncommitted review records; inspect them.'` BEFORE `ai-review --recheck`,
  `disputes-record` and the commit; the arm stays, nothing is committed, and the stop takes
  today's re-check rules (a limit stop in an implementation session cannot produce this state:
  `reconcile_disputes` commits those records on every start, resume and triage before any task
  runs). The `tasks untouched` plan-review gate (~429) needs no change (a touched queue skips
  the plan review; an untouched one with the current plan review breaks out of the loop without
  a commit, T015 tests it). Trace every other check on that path (e.g. `ensure_validated`,
  ~236; anything between ~384 and ~501) and list in the result which you changed and why the
  rest are not reached; do not relax any check after the first implementation session.
- No runnable task (plan review round 2, P3): the session may have marked its task DONE and
  then hit the limit before committing (the last task, or a middle one). `scripts/ai-pipeline`
  ~499 (`if ! ai_helper tasks complete; then … ai-run`) runs ai-run also when `armed_resume`
  holds, whatever `tasks complete` says, so the arm is always consumed by ai-run and the
  review/publish path never meets the dirty tree.
- ai-run consumes the arm exactly once, by the task the arm names (T017; plan note "Preserved
  work is bound to the interrupted task (plan review round 6 redesign, T017)", rule 3), and
  only as the last statement before it acts (plan review round 8 P16; plan note "The arm ends
  at the act, not at the entry (round 8 redesign, T019)": every check below runs while the
  manifest is still armed, so each of its stops is T018's terminal ⛔, with recovery on too):
  when the armed exception admits the dirty tree, `bound=$(ai_helper run-manifest
  limit-task)` (failure → `ai_die`), then the consistency check: `tasks newly-done HEAD`
  (T012) must print nothing or exactly `$bound`, else `ai_die 'Preserved work marks another
  task DONE; inspect it before continuing.'` (armed, terminal). The
  consumer sits where a first session's startup is complete (plan review round 7 P17; plan
  note "Recovery never acts on an armed tree; the armed checkpoint comes after the complete
  startup (round 7 redesign, T018)", rule 2): after `clean_or_armed` admitted the tree
  (~148–149), `attempt-reconcile`, the mode checks and the session budget (~596–604), and
  right BEFORE the dependency setup block (~606–614), whose condition widens to `[[
  "$(ai_helper tasks next)" != none || -n "$bound" ]]`: the preserved tree may carry a changed
  dependency input (a lockfile) that `.ai/validate` needs installed, and with the last task DONE
  `tasks next` is `none`, so the existing condition would skip the install and the armed
  checkpoint's `ai-check` would fail with stale dependencies (ordinary recovery instead of the
  promised checkpoint). `ai_deps` installs ignored files only (`tree-snapshot` unchanged, else it
  fails) and its failure is `ai_die "$AI_DEPS_ERROR"` (`Dependency setup …`, a hard rule for
  recovery; armed, it is terminal as well), so an installer failure commits nothing. The route
  decision below, the disarm and `checkpoint_done` come AFTER that block (order: `bound` read
  and consistency check → dependency setup → route by status → loop-head checks → `limit-disarm`
  → `checkpoint_done` or the loop). Then the ROUTE, decided while still armed, by
  `status=$(ai_helper tasks status "$bound")`:
  - DONE, whether HEAD already has it DONE or only the working queue does (a session that
    committed its task DONE and edited further before the limit, plan review round 6 P3, takes
    this path too) → route `checkpoint`: *armed checkpoint* `checkpoint_done "$bound"` before any session: refactor
    the loop's `DONE)` branch (ai-run ~669–703 plus the runner-bookkeeping commit and the
    post-commit `verify_checkpoint` ~713–720) into one function `checkpoint_done TASK` used by
    the loop and here, unchanged in substance: full `ai-check` (failure → task back to
    IN_PROGRESS, state blocked, `ai_die`), tier-1 commit `chore(ai): checkpoint <id> (validated;
    the session did not commit)` with `checkpoint-guard`, stamp verify and
    `committed-matches-worktree`, the 🔧 notification, `ai_log`, bookkeeping commit,
    `verify_checkpoint`, ✅. For a task already DONE in HEAD this is a second, validated commit
    of that task's own after-commit edits (the implementation review covers the range like any
    task commit). `task_outcome done` only if it works without an attempt opened in this
    process (say which in the result). Then the loop starts as today (final validation and
    handoff when nothing is left, else the next task);
  - IN_PROGRESS or TODO → route `session`: the first iteration as today, which must work on
    `$bound`: `tasks next` prints it (IN_PROGRESS first, workflow.py ~642–647; a TODO bound
    task is the first eligible unless the session changed the queue), checked HERE, armed;
    another ID → `ai_die "Preserved work belongs to $bound, but the next task is <id>; inspect
    the queue."`. Its prompt already says `Reconcile interrupted work first`;
  - BLOCKED → `ai_die 'Blocked task was not checkpointed; inspect and commit before resuming.'`
    (today's rule, ~705–706); an ID not in the queue → `ai_die`.
  `newly-done` is no longer the decision, only the consistency check. Every `ai_die` above
  fires with the arm kept, so the next recovery is T018's terminal ⛔ carrying that message
  (T019 runs each with recovery on). Once the route is decided: repeat the loop head's checks
  once (`ai_guard_verify`, `ai_branch`, `ai_helper tasks check`; still armed), then `ai_helper
  run-manifest limit-disarm` (failure → `ai_die`, nothing started; the single call site, before
  the `for` loop), print `Resuming preserved work of the usage-limit stop ($bound).`,
  `ai_helper run-manifest task-clear` (T017), then the act: route `checkpoint` →
  `checkpoint_done "$bound"`, then the loop as today; route `session` → the loop, whose first
  iteration works on `$bound`. Nothing else stands between the disarm and the act (the loop
  head's re-checks, `state implementing` and the prompt only; T019 asserts the span). A clean
  tree never consumes the arm (`clear-attempts` at finish drops it).
- After the session nothing is relaxed: DONE → `ai-check`, tier-1 commit with
  `checkpoint-guard`, `committed-matches-worktree` (~669–701; update the comment "The session
  started from a clean tree" to say an armed resume started from its own preserved task work);
  BLOCKED → must be checkpointed; anything else → `no_checkpoint` stop as today.
- ai-recover's later stops after an armed resume follow the normal recovery rules (the arm is
  gone, so a second crash does not get the exception).
- docs/workflow.md "Interruption, limits, and recovery" and README "Recovery": a limit stop
  keeps the session's uncommitted work and the relaunch continues it once; any change during
  the wait escalates (T014's paragraph; add the preserved-work sentence to it).
- Flow chart (vault): the relaunch branch notes "uncommitted task work is continued, not
  committed by recovery".

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_preserved_*` in tests/test_workflow.py (fixtures as T003's
  `test_limit_relaunch_recover_*`):
  - new mock mode `MOCK_CLAUDE=limit-far-dirty`: the session sets the active task IN_PROGRESS in
    `.ai/tasks.md` and writes a source file, then reports the far limit (as `limit-far`).
    `ai-pipeline --approved … --no-pr` → exit 75 and scheduled as in T003, the tree still holds
    both edits; AT set into the past; `ai-recover --stage 'usage limit relaunch'` with a normal
    mock that completes the task → the pipeline completes; the source file is in a validated
    checkpoint commit; `recovery_calls()` empty (no recovery decision session); notifications
    contain `▶ RESUMED after the usage limit` and no `⛔`; the manifest has no `limit_resume`;
  - HEAD moved after scheduling (a commit made by the test, tree still dirty) → ⛔ `moved to
    another commit while the usage-limit relaunch waited`, nothing committed by recovery, no
    session ran, the session's edits byte-identical;
  - DONE before the limit (round 2 P3): new mock mode `MOCK_CLAUDE=limit-far-done`: the session
    sets the active task DONE in `.ai/tasks.md`, writes a source file, then reports the far
    limit. With a one-task queue: scheduled (exit 75); AT into the past; `ai-recover --stage
    'usage limit relaunch'` → the pipeline completes (review and `--no-pr` finish), the source
    file is in a `checkpoint T001 (validated; the session did not commit)` commit, the mock
    records NO implementation session after the relaunch (count the mock's calls),
    `recovery_calls()` empty, no `⛔`, no `limit_resume`; the same with a two-task queue (T001
    limited after DONE) → T001 checkpointed before T002's session, T002 then runs normally;
    a failing `.ai/validate` on that tree → `Validation failed; T001 returned to IN_PROGRESS.`,
    nothing committed by the runner;
  - DONE committed before the limit (round 6 P3, the reviewer's case): new mock mode
    `MOCK_CLAUDE=limit-far-done-committed`: the session sets its task DONE in `.ai/tasks.md`,
    writes a source file, COMMITS both, writes a second source change without committing, then
    reports the far limit. One-task queue → scheduled (exit 75), `tasks newly-done HEAD` prints
    nothing, the manifest holds `limit_task` `T001`; AT into the past; relaunch → the pipeline
    completes with no recovery decision session: the second change is in a `checkpoint T001
    (validated; the session did not commit)` commit whose parent is the relaunch's `record stop
    during` commit or the session's own commit, the mock records NO implementation session
    after the relaunch, exactly one `Resuming preserved work of the usage-limit stop (T001).`,
    `recovery_calls()` empty, no `⛔`, no `limit_resume`, no `task` left in the manifest; the
    same with a two-task queue → T001's checkpoint precedes T002's session, which starts on a
    clean tree; a failing `.ai/validate` on that tree → `Validation failed; T001 returned to
    IN_PROGRESS.`, nothing committed by the runner (HEAD is the session's commit);
  - a tree whose bound task is DONE while a second task is also newly DONE → `Preserved work
    marks another task DONE`, no session, nothing committed, the manifest still armed; a bound
    task left TODO while the session marked another task IN_PROGRESS (mock variant) →
    `Preserved work belongs to T001, but the next task is T002`, no session, the manifest
    still armed; both with the fixtures' `AI_AUTO_RECOVER=0` here (T019 runs them with
    recovery on and `MOCK_RECOVER=commit_and_rerun`: terminal, nothing committed);
  - round 2 P9 end-to-end with preserved work: `limit-far-dirty` scheduled, then the test edits
    an unrelated tracked file and adds an untracked file (HEAD unchanged), AT into the past,
    relaunch → one ⛔ `changed while the usage-limit relaunch waited`, the session's edits and
    both human changes byte-identical, HEAD unchanged, no session, no `limit_resume`;
  - an armed tree reaching a session that does NOT complete (mock returns without DONE) → the
    existing `No completed/blocked checkpoint` stop, the arm is gone, and a following
    `ai-recover --stage implementation` takes the normal path (dirty tree → Claude decision),
    not the exception;
  - a human `ai-pipeline --approved` on a dirty tree with an armed manifest → refused with
    `Start from a clean checkpoint` (`run-manifest start` dropped the arm);
  - `ai-run --approved` on a dirty tree with an arm for a different HEAD → `Start from a clean
    checkpoint`; the same with the arm's HEAD but one more edited file than the armed tree
    (T012's binding) → `Start from a clean checkpoint`, nothing committed;
  - settled re-check (round 4 P3, the minimal case; T015 has the matrix and the full
    accepted-plus-rejected scenario): a fixture whose review was triaged with one rejected
    BLOCKER/MAJOR and whose re-check is verified and committed (`recheck-status` prints
    `verified`, as the existing re-check tests set up), then `limit-far-dirty` on the fix task
    → scheduled; AT into the past; relaunch → the resumed pipeline passes
    `reconcile_disputes` without a commit and without `Re-check of rejected findings` in any
    last-error, ai-run consumes the arm, the task completes, `recovery_calls()` empty;
  - fail closed (contract rule 2): the same fixture with the arm set and an extra uncommitted
    line in `.ai/reviews/disputes.md` (planted before the limit stop so the digest includes it)
    → stop with `preserved task work carries uncommitted review records`, no new commit (HEAD
    unchanged), the manifest still armed, no session; this case runs with the fixtures'
    `AI_AUTO_RECOVER=0`; with recovery ON the same stop is terminal in ai-recover, which is
    T018's `test_limit_relaunch_terminal_*` (round 7 P16);
  - dependency setup before the armed checkpoint (round 7 P17): the `deps.lock` fixture of
    `deps_recovery_run` (tests/test_workflow.py ~9862–9871: `.ai/validate` is `cmp -s deps.lock
    vendor-deps/deps.lock`, `MOCK_DEPS=ok`, `MOCK_REQUIRE=vendor-deps/deps.lock`, the session's
    extra file `deps.lock`) combined with `limit-far-done` and with `limit-far-done-committed`,
    one-task queues each → scheduled; AT into the past; relaunch → the pipeline completes with
    `recovery_calls()` empty and no `⛔`; `deps_calls()` is one more than before the relaunch
    (the resumed ai-run installed although `tasks next` was `none`); the gate passing proves the
    install preceded the validation; the `checkpoint T001 (validated; the session did not
    commit)` commit contains `deps.lock`; `vendor-deps/` is not tracked; with `MOCK_DEPS`
    failing on the resumed run's install (`fail-later`) → exactly one ⛔ containing `Dependency
    setup`, `recovery_calls()` empty (hard rule), nothing committed by the runner (HEAD is the
    scheduled HEAD or the session's own commit), the edits byte-identical, no session, the
    manifest still armed (the install runs before the disarm, T019).
- `test_recovery_*`, `test_usage_limit_*`, the re-check/dispute tests and all pipeline tests pass
  unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_preserved` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recheck` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE (2026-10-18; the first session timed out, its WIP `f6f7bf2` was reconciled and needed no
code change). `armed_resume` and `clean_or_armed` in `scripts/ai-pipeline` (start-from-clean,
both `reconcile_disputes` tests; the `pending`/dirty-review-record fail-closed stop before
`ai-review --recheck`, `disputes-record` and `host_commit`; `revision-queue-repair` skipped while
armed; ai-run runs while armed even when `tasks complete`) and `scripts/ai-run` (start check;
`armed=yes` when the exception admitted the tree). ai-run consumer order: `limit-task` →
`newly-done HEAD` consistency → dependency setup (condition widened with `-n "$bound"`) → route
by status → `ai_guard_verify`/`ai_branch`/`tasks check` → `limit-disarm` (single call site) →
`Resuming preserved work …` → `task-clear` → `checkpoint_done` or the loop. The loop's `DONE)`
branch plus the bookkeeping commit and `verify_checkpoint` are now `checkpoint_done` /
`runner_checkpoint` (BLOCKED uses `runner_checkpoint` too); the tier-1 comment names the armed
resume. `task_outcome done` works without an attempt (no `--attempt` argument), so the armed
checkpoint logs a `done` line. Other checks on the path not changed: `ensure_validated` and the
review/publish steps are not reached while armed (ai-run runs first and consumes or stops);
the `tasks untouched` plan-review gate needs no change (T015). Nothing after the first act is
relaxed. Tests: 20 `test_limit_relaunch_preserved_*` (mock modes `limit-far-dirty`,
`limit-far-done`, `limit-far-done-committed`, `limit-far-keep`). Validation: `-k
limit_relaunch_preserved` Ran 20 OK; `-k recheck` Ran 32 OK; `-k recovery` Ran 65 OK;
`.ai/bin/ai-check` PASS (879 tests, 520.3 s). Docs: docs/workflow.md "How the resumed run
continues preserved work", README "Recovery"; vault flow chart relaunch node.


## T016 — Armed resume re-enters at implementation: stage-bound arm, plan review loop not entered while armed (MC-01 part 1, plan review round 5 P3 design task)
Status: DONE
Dependencies: T011
Model: opus

### Goal
The usage-limit arm is granted only for an `implementation` stop and the resumed run re-enters
the run at implementation: it never enters the plan review loop on an armed tree, so a partial
checkpoint committed by the limited session (source in HEAD while its task is still
IN_PROGRESS, more edits preserved) cannot make the resume run `ai-review --plan` on a dirty
checkout and fall into a recovery decision session; the plan-approval boundary stays where it
was, before the run's first implementation session.

### Implementation notes
- Design: `.ai/current-plan.md` "Preserved-work resume", part "Armed resume re-enters at
  implementation (plan review round 5 redesign, T016)". Verified at the revision: `tasks
  untouched` (scripts/lib/workflow.py ~638–641) fails only when a task is DONE; `plan_digest()`
  (~2328–2334) hashes HEAD's `ls-tree` minus `.ai/reviews/`, `.ai/state.md`, `.ai/run-log.md`,
  `.ai/handoff.md`, so a committed source change makes the saved plan review `stale`;
  ai-pipeline ~429 enters the loop on `tasks untouched`, ~447 sets `review_due=yes`, ~460 runs
  `ai-review --plan`, which dies at ai-review ~286 (`Commit the plan before reviewing it.`) on a
  dirty tree → `stop 'plan review'` → ai-recover's Claude decision (not a hard rule, not
  bookkeeping-only).
- `scripts/lib/workflow.py` `run_manifest`: new optional field `limit_stage` (string matching
  `^[ -~]{1,40}$`; wrong type → invalid manifest, as T001's fields). `limit-schedule AT CAP
  STAGE` (T012's signature plus STAGE, validated the same way) records it beside `limit_head`
  and `limit_tree`; `clear-attempts` and `start` drop it. `limit-arm` (no argument) arms only
  when `limit_stage == 'implementation'` AND `limit_task` is set (T017) AND HEAD and the tree
  digest match (T012); the stage is checked first: a mismatch exits 1 with `the usage-limit
  stop left uncommitted changes outside an implementation session` on stderr, nothing written;
  then T017's task check, then T012's reasons.
  `limit-verify`, `limit-armed` and `limit-disarm` are unchanged (the stage is judged once, at
  the arm; `limit_resume` can only exist for an implementation stop).
- `scripts/ai-recover`: `limit-schedule "$at" "$cap" "$stage"` (`$stage` is this ai-recover's
  `--stage`, which ai-pipeline's `stop()` (~147–158) passes: `implementation` for ai-run at
  ~501, first tasks and fix rounds alike; on the relaunch itself `--stage` is `usage limit
  relaunch`, which is why the stage is recorded at scheduling and read from the manifest at the
  arm, never from the relaunch's arguments). Transition (c) (T003/T014: dirty, not
  bookkeeping-only → `limit-arm`) escalates a failing arm by building the ⛔ from the helper's
  reason as T014 prescribes: for the stage reason `the usage-limit stop left uncommitted
  changes outside an implementation session; nothing was committed.` / `Next: inspect the
  checkout, commit or discard what changed, then rerun ai-pipeline.` (the tree reasons keep
  T014's ` while the usage-limit relaunch waited; nothing was committed.`). Update T014's
  transition table comment: (c) requires `limit_stage == implementation`; otherwise ⛔.
- `scripts/ai-pipeline` ~429: `if [[ "$plan_review" == yes ]] && ! armed_resume && ai_helper
  tasks untouched 2>/dev/null; then` (T011's `armed_resume`; the site is after
  `reconcile_disputes` ~384 and `plan_decision_check` ~410, so a needs-human decision still
  stops first). Comment at the site: the arm is bound to an `implementation` stop, which exists
  only after this loop broke out in the same run; a committed partial checkpoint makes
  `plan-review-info` stale and `ai-review --plan` cannot run on the preserved tree; the
  committed part is reviewed by the implementation review like any task commit. The second
  `plan_decision_check` (~494), `--skip-plan-review` and a clean resume are unchanged.
- Audit ai-pipeline from the resume to `ai-run --approved` against the plan note's stage list
  (start checks → `reconcile_disputes` → `base_reached` → `plan_decision_check` → queue check →
  `plan_decision_check` → implementation): list in the result every statement on that path that
  runs a session, a review, or `host_commit`, and show it is inside a stage of the list or
  guarded by `! armed_resume` / T011's fail-closed stop. Anything else → fix it here under the
  same rules (T015 then audits the finished path for its contract).
- docs/workflow.md "Interruption, limits, and recovery" (the paragraph T011/T014 write; T015
  extends it later): the relaunch continues an implementation session's work only, and the
  resumed run goes straight to implementation (no plan review re-run on the preserved tree; a
  clean resume behaves as today). README "Recovery": one clause in T011's sentence.
- Flow chart (vault): the relaunch branch note (T011) gains "re-enters at implementation".

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-recover, scripts/ai-pipeline, tests/test_workflow.py, docs/workflow.md, README.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_reenter_*` in tests/test_workflow.py (fixtures as T011's
  `test_limit_relaunch_preserved_*`, plan review enabled by default with the plan reviewer mock
  of the existing plan-review pipeline tests, `--no-pr`):
  - the reviewer's case (round 5 P3): new mock mode `MOCK_CLAUDE=limit-far-dirty-checkpoint`:
    the session sets its task IN_PROGRESS, writes a source file and COMMITS both (a partial
    checkpoint: the task stays IN_PROGRESS, zero DONE tasks), writes a second source change
    without committing, then reports the far limit → scheduled (exit 75); `plan-review-info`
    now prints `stale`; AT into the past; relaunch with a normal mock that completes the task →
    the pipeline completes; the plan reviewer mock is NOT invoked after the relaunch and no
    `chore(ai): record plan review` commit follows `▶ RESUMED`; `Commit the plan before
    reviewing it` appears nowhere (notifications, last-error history, run log); no commit
    between the relaunch's `record stop during` commit (or the partial checkpoint when there is
    none) and ai-run's checkpoint of the task; exactly one `Resuming preserved work of the
    usage-limit stop (T001).` (T011's task-bound message with the fixture's bound task ID,
    plan review round 7 P18); `recovery_calls()` empty; no `⛔`; the manifest has no
    `limit_resume`;
  - the same with `--skip-plan-review` → the same result;
  - control, clean resume unchanged: a mock that commits its partial checkpoint and reports the
    far limit with a CLEAN tree → no arm (`limit_resume` never set), the relaunch resumes
    (transition (d)), and the plan review loop runs as today: the plan reviewer mock is
    invoked once after `▶ RESUMED` (the stale review is re-reviewed on the clean checkout), the
    run then completes; this pins that only the armed resume skips the loop;
  - a recorded needs-human plan decision on the relaunch itself: plant the needs-human revision
    record in host state (as the existing `plan_decision_check` tests do) after scheduling →
    ai-recover's plan-revision decision block (~114–129) runs BEFORE the transitions that call
    `limit-arm`, so the relaunch escalates there: exactly one ⛔ containing `plan review needs
    your decision`, the schedule consumed (no `limit_relaunch_at`: terminal), NO arm
    (`limit_resume` absent), HEAD unchanged, the checkout byte-identical, nothing committed, no
    session (plan review round 6, P15: recovery never arms in this case);
  - a recorded needs-human plan decision still stops an ARMED resume: arm at helper level
    (`limit-schedule 100 2 implementation` on the dirty tree after `task-set T001`, then
    `limit-arm`), plant the needs-human record, then start `ai-pipeline` exactly as ai-recover's
    `resume` does (the same environment variables, `AI_RECOVERY_ATTEMPT` set) → stops at the
    first `plan_decision_check` (~410) with `plan review needs your decision`, HEAD unchanged,
    the manifest still armed, nothing committed, no session, no `limit-disarm` call;
  - stage-bound arm, helper level (after `run-manifest start`): `limit-schedule 100 2
    implementation` on a dirty tree → `limit-arm` arms, `limit_stage` recorded; a fresh
    `limit-schedule 100 2 review` on the same dirty tree → `limit-arm` exits 1 with `outside an
    implementation session`, no `limit_resume`, the manifest otherwise byte-identical;
    `limit-schedule 100 2 ''` and a 41-character STAGE → exit 1 (validation), nothing written;
    a manifest with `limit_stage: 7` is invalid; `clear-attempts` drops `limit_stage`;
  - stage-bound arm, end-to-end: a fixture whose last-error is the limit message, whose
    `limit-stop` is valid and whose tree has an uncommitted source edit, run through
    `ai-recover --stage review` with the timer installed → scheduled with `limit_stage`
    `review`; AT into the past; relaunch → exactly one ⛔ containing `outside an implementation
    session` and `nothing was committed`, the edit byte-identical, HEAD unchanged, no
    `limit_resume`, no `limit_relaunch_at` (claimed: terminal), `recovery_calls()` empty, no
    session; the same fixture with a clean tree → resumes (`▶ RESUMED`) as today;
  - T001's, T003's, T012's, T014's and T011's tests updated for the STAGE argument (named in the
    result); `relaunch_verify` and `limit-disarm` call-site counts (T014/T015) unchanged.
- `test_limit_relaunch_*`, `test_recovery_*`, `test_usage_limit_*`, the plan-review and plan
  decision pipeline tests (`-k plan_review`, `-k plan_decision`, `-k supervise`) and all
  pipeline tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_reenter` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k plan_review` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- `workflow.py`: `limit_stage` in `LIMIT_FIELDS` (so `clear-attempts` drops it; `start` writes a
  fresh manifest), validated by `limit_stage_valid` (`[ -~]{1,40}`; wrong type → invalid
  manifest). `limit-schedule AT CAP STAGE` (3 arguments, STAGE validated, nothing written on a
  usage error) records it. `limit-arm` checks `limit_stage == 'implementation'` first (else exit 1
  `the usage-limit stop left uncommitted changes outside an implementation session`, nothing
  written), then T017's task, then T012's binding. `limit-verify`/`-armed`/`-disarm` unchanged.
- `ai-recover`: schedules with `"$stage"`; transition (c) escalates the stage reason as
  `…; nothing was committed.` with the `Next:` of T014 (the tree reasons keep `while the
  usage-limit relaunch waited`); the transition table comment says (c) requires an
  implementation stop.
- `ai-pipeline`: the plan review loop is entered only when `! armed_resume`, with the comment
  at the site. `relaunch_verify` (1 call) and `limit-disarm` (1 call site, ai-run) unchanged.
- Audit of ai-pipeline from the resume to `ai-run --approved` (statements that run a session, a
  review or `host_commit`): open-stage completion (`ai-run --triage`/`--revise-plan`) — not
  reachable armed (`armed_resume` requires no open stage); `reconcile_disputes` (`ai-review
  --recheck`, `host_commit` of re-check/dispute records) — a listed stage, and armed it fails
  closed on a pending re-check or dirty review records before either runs (T011/T015);
  `revision-queue-repair` — guarded by `! armed_resume`; plan review loop (`ai-review --plan`,
  `host_commit 'chore(ai): record plan review'`, `complete_plan_stage` → `ai-run --revise-plan`)
  — now guarded by `! armed_resume`; `ai-run --approved` — implementation. Everything else on the
  path (`run-manifest start` only on a human start, `fix-rounds init`, timer status, ▶ notify,
  `base_reached`, both `plan_decision_check`, `tasks check`) only reads or stops. Nothing else to fix.
- Tests (tests/test_workflow.py), 8 `test_limit_relaunch_reenter_*`: `partial_checkpoint_skips_the_plan_review`
  (new mock `limit-far-dirty-checkpoint`; `plan-review-info` stale; no plan reviewer call or
  plan-review commit after the relaunch; `Commit the plan before reviewing it` nowhere; only the
  session's own commit between the partial checkpoint and ai-run's checkpoint; one `Resuming
  preserved work … (T001).`; no recovery call, no ⛔, no `limit_resume`),
  `partial_checkpoint_with_skip_plan_review`, `clean_resume_re_reviews_the_plan` (mock
  `limit-far-clean-checkpoint`: never armed, second plan review on a clean checkout, completes),
  `plan_decision_on_the_relaunch_escalates_unarmed`, `plan_decision_stops_an_armed_resume`,
  `stage_bound_arm_helper`, `stage_bound_arm_end_to_end` (`ai-recover --stage review`),
  `stage_bound_clean_tree_resumes`. Without the new guard the first test fails with `Commit the
  plan before reviewing it.` → recovery decision (round 5 P3 reproduced).
- Updated for STAGE: `test_limit_relaunch_record_manifest_schedule_lifecycle` (also asserts
  `limit_stage` recorded/dropped and invalid values), `test_limit_relaunch_bound_manifest_task_record_and_arm`,
  the T012/T014 helper-level arm tests using `limit-schedule 100 2`, the watchdog fixtures at
  the `limit-schedule str(at) 2` / `str(start - 10) 2` sites, and `bound_limit_stop` (stage and
  edit parameters; drops `limit_stage` on reset). T003/T011 end-to-end tests go through
  ai-recover and needed no change.
- Docs: docs/workflow.md (schedule signature, manifest field, transition (c), new "Which stop
  can leave preserved work" paragraph, armed resume re-enters at implementation); README
  Recovery clause; vault flow chart relaunch branch and hub log.
- Validation: `-k limit_relaunch_reenter` 8 OK; `-k limit_relaunch` 70 OK; `-k plan_review` 20
  OK; `-k recovery` 65 OK; `-k Docs` 3 OK; `.ai/bin/ai-check` PASS (887 tests, 531.5 s). The
  first session timed out at 1800 s during its gate (WIP 7088074); the rerun reconciled it with
  no code change.


## T018 — Recovery is terminal while the tree is armed; the armed checkpoint comes after ai-run's complete startup (MC-01 part 1, plan review round 7 P16/P17 design task)
Status: DONE
Dependencies: T011, T017
Model: opus

### Goal
A stop of the resumed run while the preserved tree is still armed (between the relaunch's
`exec ai-pipeline` and ai-run's `limit-disarm`) never reaches a recovery decision session or a
recovery commit, whatever its reason and whatever the recovery settings: ai-recover treats an
armed manifest as terminal (one ⛔ carrying the stop's reason, nothing committed, the checkout
and the arm as found). The resumed ai-run gives the armed checkpoint everything a session's
checkpoint gets, dependency setup first (rule implemented by T011, audited here).

### Implementation notes
- Design: `.ai/current-plan.md` "Preserved-work resume", part "Recovery never acts on an armed
  tree; the armed checkpoint comes after the complete startup (plan review round 7 redesign,
  T018)". Verified at the revision: `recheck_fail` (scripts/ai-pipeline ~314–317) calls `stop
  're-check'`, and `stop()` (~147–163) execs `ai-recover --stage re-check` whenever
  `AI_AUTO_RECOVER` is not 0 and the gate holds; the reason `Re-check of rejected findings:
  preserved task work carries uncommitted review records; inspect them.` matches none of the
  hard rules (scripts/ai-recover ~137–141), the tree is not bookkeeping-only (~166–171), so the
  Claude decision session runs (~188) and `commit_and_rerun` (~200–222) runs `ai_deps`,
  `ai-check`, `git add --all` and commits the armed tree, review records included, while the
  manifest still holds `limit_resume` for a HEAD that no longer exists. The "fail closed, arm
  kept" of T011/T015 therefore held only with recovery off (the fixtures' default,
  tests/test_workflow.py ~713).
- `scripts/ai-recover`: right after `reserve-attempt`, the settings restore and T003's
  `limit-hold`/`limit-claim` (which act only on a scheduled relaunch), and BEFORE the limit-stop
  scheduling check, the plan-revision decision block (~114–129), the hard rules and every other
  rule: `if bound=$(ai_helper run-manifest limit-task 2>/dev/null); then escalate "the resumed
  run stopped on the preserved work of $bound before continuing it; nothing was committed."
  'inspect the checkout and .ai/local/last-error, commit or discard the preserved work, then
  rerun ai-pipeline.'; fi`. `limit-task` (T017) exits 0 exactly when `limit_resume` exists,
  matching HEAD/tree or not: a mismatch is an inconsistency too, because only ai-run's
  `limit-disarm` (T015 rule 3) or a human `run-manifest start` may remove `limit_resume`.
  `escalate` prints `$reason` in the ⛔ as always, so the original stop (for instance
  `preserved task work carries uncommitted review records`) stays visible to the human and to
  T015's assertions. Add the row to T014's transition table comment: "`limit_resume` present
  at entry → terminal, nothing touched". No `limit-disarm` call in ai-recover (T015's
  single-call-site test).
- Why the relaunch is unaffected: when ai-recover runs `--stage 'usage limit relaunch'` the
  manifest is scheduled, not armed (`limit_resume` is written later in the same process by
  transition (c)), so the check cannot fire on the relaunch; after ai-run's `limit-disarm` the
  normal rules apply unchanged (a later limit in a session schedules again, T003). A
  watchdog-started recovery for a resumed pipeline killed before the disarm hits the rule → ⛔
  with the preserved work intact; the human reruns (residual recorded in the plan's Risks).
- Audit of the startup order (round 7 P17, rule 2 of the design note): list in the result every
  statement of `scripts/ai-run` from its start to the first `claude_session` of the task loop on
  the resume path and show that T011's consumer runs after every startup step a first session
  gets (`ai_guard_verify`, `ai_branch`, `tasks check`, `attempt-reconcile`, the session budget,
  the dependency setup block ~606–614 with T011's widened condition) and that `checkpoint_done`
  is reached only after them, and that `limit-disarm` is the last statement before
  `checkpoint_done` / the `for` loop, after the consistency check, the dependency setup and the
  route decision (plan review round 8 P16; T019 owns that rule and its span test); a step the
  armed checkpoint skips, or a check placed after the disarm, is a defect to fix here under
  T011's rules (and say so in the result).
- docs/workflow.md "Interruption, limits, and recovery" (the paragraph T011/T014/T015/T016/T017
  write): one sentence: a stop of the resumed run before the preserved work is continued is
  final; recovery never commits or decides on it, whatever `AI_AUTO_RECOVER` says. README
  "Recovery": half a sentence. Flow unchanged in this task (T011's relaunch branch note gains
  "a stop while armed is terminal", written by T011 if it runs first, else here).

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py, docs/workflow.md, README.md

### Acceptance criteria
- Tests named `test_limit_relaunch_terminal_*` in tests/test_workflow.py (fixtures as T011's
  `test_limit_relaunch_preserved_*`):
  - the reviewer's case (round 7 P16): T011's fail-closed fixture (the armed tree with an extra
    uncommitted line in `.ai/reviews/disputes.md`, planted before the limit stop so the digest
    includes it) relaunched with `AI_AUTO_RECOVER=1` and `MOCK_RECOVER=commit_and_rerun` →
    exactly one ⛔, containing `preserved task work carries uncommitted review records` and
    `nothing was committed`; `recovery_calls()` empty (no decision session); no `recovery
    checkpoint` commit and HEAD unchanged; the session's edits and the planted line
    byte-identical; the manifest still holds `limit_resume` (arm retained); no `🔧 Recovered` and
    no second `▶ RESUMED`; `.ai/local/pipeline.active` gone; the same for T015's host-only
    `pending` state when its fixture can produce it (else say so);
  - direct, any reason: an armed manifest at helper level (`limit-schedule 100 2 implementation`
    after `task-set T001`, `limit-arm` on a dirty tree), `last-error` a plain non-limit reason,
    `ai-recover --stage implementation` with `AI_AUTO_RECOVER=1` and
    `MOCK_RECOVER=commit_and_rerun` → one ⛔ containing `stopped on the preserved work of T001`
    and the recorded reason, `recovery_calls()` empty, nothing committed, the edits
    byte-identical, `limit_resume` retained, attempt counted (`reserve-attempt` ran, as for every
    hard rule); the same with the arm's HEAD moved by the test (a `limit_resume` that no longer
    matches) → the same ⛔ (presence decides, not the match);
  - controls: T011's `limit-far-dirty` happy path with `AI_AUTO_RECOVER=1` still arms and
    resumes (`▶ RESUMED`, the task completes, no ⛔): the relaunch stage is not caught; T011's
    "armed tree reaching a session that does NOT complete" case with `AI_AUTO_RECOVER=1` → the
    following recovery runs the normal path (`recovery_calls()` has one entry): after the disarm
    nothing is terminal because of the arm;
  - `limit-disarm` appears exactly once in `scripts/ai-run` and nowhere in `scripts/ai-recover`
    (the fixture's installed copies included).
- `test_limit_relaunch_*`, `test_recovery_*`, `test_usage_limit_*`, the re-check/dispute tests
  and all pipeline tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_terminal` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- Reconciled WIP 5a25637 (the first session hit the 1800 s limit); no further code change needed.
- scripts/ai-recover: after `reserve-attempt`, the settings restore, `limit-hold`/`limit-claim`,
  the handlers and the marker, and before `AI_AUTO_RECOVER`, the gate/branch checks,
  `relaunch_verify`, the plan-revision decision and every rule: `limit-task` succeeds → `escalate`
  (⛔ with `$reason` and `the resumed run stopped on the preserved work of T… before continuing
  it; nothing was committed.`). Transition table comment gains the row. No `limit-disarm` in
  ai-recover.
- Tests (5 `test_limit_relaunch_terminal_*`): the reviewer's re-check case with recovery on
  (bound task T002 in that fixture; T015's host-only `pending` state has no fixture yet, T015 adds
  that variant); helper-level arm, any reason, matching and moved HEAD (attempt counted); controls:
  relaunch with recovery on resumes, after the disarm recovery is normal (one decision call);
  `limit-disarm` once in ai-run, never in ai-recover (installed copies included).
- Startup audit (scripts/ai-run, resume path, in order): `ai_supervise_settings`, `command -v
  claude`, `ai_root`, `state-root-check`, `ai_lock`, `rm last-error`, start branch, `ai_branch`,
  HEAD exists, `attempt-dir`/`attempt-reconcile`, `clean_or_armed` (sets `armed`), `tasks check`,
  gate digest/approval, allowlist load, traps, prompt load, session budget (~612–620); armed block
  (~685–691: `limit-task`, `newly-done` HEAD); dependency setup (~696–702, T011's widened
  condition `|| -n "$bound"`); route by status (~704–717); `ai_guard_verify`, `ai_branch`, `tasks
  check`; `limit-disarm` (~722), the last check-bearing statement before `checkpoint_done` / the
  `for` loop (only the resume printf and the best-effort `task-clear` follow). No skipped startup
  step and no check placed only after the disarm: no defect. The loop head repeats
  `ai_guard_verify`/`ai_branch`/`tasks check` after the disarm (already passed armed); T019 owns
  the span rule and its test.
- Docs: docs/workflow.md "Interruption, limits, and recovery" and README "Recovery" (sentence
  added); vault flow chart's relaunch edge already says "a stop while armed is terminal" (T011).


## T019 — The arm ends at the act: every consumer check runs armed, the disarm is the last statement before the checkpoint or the session (MC-01 part 1, plan review round 8 P16 design task)
Status: IN_PROGRESS
Dependencies: T011, T018
Model: opus

### Goal
Between the relaunch's `exec ai-pipeline` and the resumed ai-run's first act (the armed
checkpoint or the bound task's session) the manifest stays armed through every check ai-run
makes, its own consistency and routing checks included, so each of those stops is T018's
terminal ⛔ (no recovery decision session, no recovery commit, the preserved work and the arm
intact) with auto-recovery on; `limit-disarm` is the last statement before the act, and nothing
that can stop for a plan state sits between the two.

### Implementation notes
- Design: `.ai/current-plan.md` "Preserved-work resume", part "The arm ends at the act, not at
  the entry (plan review round 8 redesign, T019)". Verified at the revision: T011's consumer as
  planned before this round ran `limit-disarm` first and the `tasks newly-done HEAD` check and
  the routing (`tasks next` must print the bound task; BLOCKED; unknown ID) afterwards, each an
  `ai_die`; ai-run's `ai_die` writes `.ai/local/last-error` (scripts/lib/common.sh ~11–14),
  ai-pipeline ~501 turns the non-zero exit into `stop implementation`, `stop()` (~147–163)
  execs ai-recover when `AI_AUTO_RECOVER` is not 0 and the gate holds, T018's check sees no
  `limit_resume` (already dropped), neither `Preserved work marks another task DONE` nor
  `Preserved work belongs to` matches a hard rule (scripts/ai-recover ~137–141), the tree is
  not bookkeeping-only (~166–171), and `commit_and_rerun` (~200–222) validates and commits the
  inconsistent queue with the preserved source; with both tasks DONE the resumed pipeline then
  skips implementation (`tasks complete`, ai-pipeline ~499). The fixtures' default
  `AI_AUTO_RECOVER=0` (tests/test_workflow.py ~713) hid it.
- T011 implements the order (its consumer bullet, revised this round): `bound` read →
  `newly-done` consistency check → dependency setup → route by `tasks status "$bound"`
  (session route: `tasks next` must print `$bound`) → one repetition of the loop head's checks
  (`ai_guard_verify`, `ai_branch`, `ai_helper tasks check`) → `limit-disarm` → `Resuming
  preserved work …` line, `task-clear` → `checkpoint_done "$bound"` or the `for` loop. This
  task audits and pins it: if T011 ran first and left a check after the disarm, move it before
  the disarm here under T011's rules and say so in the result. `limit-disarm` keeps its single
  call site (T015 rule 3); it stays before the `for` loop, so the loop head's re-checks
  (`ai_guard_verify`, `ai_branch`, `tasks check`, `tasks next`, the iteration-1 session limit,
  which cannot fail: `--sessions` accepts 1 or more, scripts/ai-run ~78, and the default is at
  least 16) are the only `ai_die`s between the disarm and the first `claude_session`; they
  repeat state the consumer verified moments earlier in the same process under the lock with no
  write or session in between, so a failure there needs a concurrent change to the checkout and
  takes today's rules (recorded in the plan's Risks as a residual).
- Span test, on the script text: in `scripts/ai-run` (and the fixture's installed copy) the
  lines from the `limit-disarm` call to the first `claude_session` of the loop, and from the
  `limit-disarm` call to the `checkpoint_done "$bound"` call, contain no `ai_die`, `exit`,
  `git commit` or `claude_session` other than the loop head's four re-checks and the
  iteration-1 session-limit line (match them by their exact text; a new statement in the span
  fails the test with its line). Keep it narrow enough to survive unrelated edits (anchor on
  the `limit-disarm` line and the two act lines, not on line numbers).
- No change to `scripts/ai-recover` (T018's check is the rule that makes the armed stops
  terminal) and none to the helpers; this task is ai-run order, tests and docs.
- docs/workflow.md "Interruption, limits, and recovery" (the paragraph T011/T014/T015/T016/
  T017/T018 write): one sentence: the resumed run checks the preserved work (another task
  marked DONE, the next task not the interrupted one, a blocked task, dependency setup) before
  it takes the work over, and each of those stops is final with nothing committed. README
  "Recovery": half a sentence. Flow (vault): the relaunch branch's armed note gains "checks
  first, then the arm ends" (written by T011 if it runs first, else here).

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, docs/workflow.md, README.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_consume_*` in tests/test_workflow.py (fixtures as T011's
  `test_limit_relaunch_preserved_*`; every case below runs with `AI_AUTO_RECOVER=1` and
  `MOCK_RECOVER=commit_and_rerun`, and asserts: exactly one ⛔, containing `stopped on the
  preserved work of T001` and the consumer's own message; `recovery_calls()` empty (no decision
  session); no `recovery checkpoint` and no `checkpoint T001` commit, HEAD unchanged; the
  session's edits and `.ai/tasks.md` byte-identical; the manifest still holds `limit_resume`;
  no `Resuming preserved work` line; no `🔧 Recovered`; `.ai/local/pipeline.active` gone):
  - another task newly DONE (T011's `Preserved work marks another task DONE` fixture);
  - the next task is not the bound one (T011's `Preserved work belongs to T001, but the next
    task is T002` fixture);
  - the bound task BLOCKED in the preserved queue (mock variant: the session marks its task
    BLOCKED, edits source, reports the far limit) → `Blocked task was not checkpointed`;
  - the bound task's ID not in the preserved queue (the test rewrites the heading of the bound
    task before the limit stop so the digest includes it, if the mock can; else arm at helper
    level as T018's direct case does and start `ai-pipeline` as `resume` does);
  - dependency setup failing on the resumed run (T011's `fail-later` case) → the ⛔ also
    contains `Dependency setup`;
  - the span test on `scripts/ai-run` and the fixture's installed copy (above);
  - controls: T011's `limit-far-dirty` and `limit-far-done` happy paths with
    `AI_AUTO_RECOVER=1` complete as before (one `Resuming preserved work of the usage-limit
    stop (T001).`, no ⛔, `limit_resume` gone); T011's "armed tree reaching a session that does
    NOT complete" with `AI_AUTO_RECOVER=1` → the following recovery runs the normal path
    (`recovery_calls()` has one entry), and T011's failing-validate armed checkpoint with
    `AI_AUTO_RECOVER=1` → `Validation failed; T001 returned to IN_PROGRESS.` followed by the
    normal recovery rules (the arm is gone: the act had started), nothing committed by the
    runner.
- `test_limit_relaunch_*`, `test_recovery_*`, `test_usage_limit_*`, the re-check/dispute tests
  and all pipeline tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_consume` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- Audit: T011 already implemented the planned order in `scripts/ai-run` (limit-task → newly-done
  → deps → route → loop-head re-checks → single `limit-disarm` → Resuming line, task-clear → act).
  Nothing was after the disarm, so no code move was needed and `scripts/ai-run` is unchanged.
- 10 `test_limit_relaunch_consume_*` tests (all with `AI_AUTO_RECOVER=1`; the stops also use
  `MOCK_RECOVER=commit_and_rerun`): another task newly DONE, next task not the bound one, bound
  task BLOCKED (`MOCK_LIMIT_ALSO=T001:BLOCKED`), bound ID missing from the queue (new mock
  `MOCK_LIMIT_RENAME=T001:T009` renames the heading before the limit, so it is in the digest), and
  dependency setup `fail-later`. Each is T018's terminal ⛔ via `assert_terminal_armed`, with no
  Resuming line, no `checkpoint T001` commit and one session. The span test covers `scripts/ai-run`
  and the installed copy. Controls: in-progress and done happy paths; an incomplete session
  and failing validation of the armed checkpoint both take normal recovery (`MOCK_RECOVER=escalate`
  so the control has one decision and no commit; the arm is gone).
- Span test deviation: the text between the disarm and the first `claude_session` includes the
  loop's `active_task == none` branch (final validation, `ai_die`, `exit 0`). The test skips that
  block: the session route reaches the loop only after `tasks next` printed the bound task under
  the lock. Quoted text (the runner prompt mentions `git commit`) is ignored.
- Mutation: moving `limit-disarm` to just after the `limit-task` read fails all five terminal
  cases and all four span subtests. Reverted.
- Docs: docs/workflow.md (one sentence), README "Recovery" (half sentence), vault flow chart
  ("checks first, then the arm ends"), hub log.
- Validation: `-k limit_relaunch_consume` 10 OK; `-k limit_relaunch` 85 OK.


## T015 — Armed-tree acceptance contract: one predicate on the whole resume path, no host write while armed (MC-01 part 1, plan review round 4 P3 design task)
Status: TODO
Dependencies: T016, T018, T019
Model: opus

### Goal
The resumed run accepts the armed tree through one predicate at every cleanliness check between
the relaunch's `exec ai-pipeline` and ai-run's consumption of the arm, makes no commit and no
tracked write while the tree is armed, and this is verified as a matrix of resume-path states
(including a settled, verified re-check with accepted and rejected findings) rather than as a
list of sites, so that no path state can refuse the preserved work and force a recovery
decision session.

### Implementation notes
- Design: `.ai/current-plan.md` "Preserved-work resume", part "Armed-tree acceptance (plan
  review round 4 redesign, T015)". T011 placed `clean_or_armed` at the four sites and the
  fail-closed rule in `reconcile_disputes`; this task owns the contract as a whole (as T014
  does for the relaunch's verification): audit the path, pin the rules, cover every state,
  document it.
- Audit `scripts/ai-pipeline` from its start to the `ai-run --approved` call (~501) and
  `scripts/ai-run` from its start to the first `claude_session` of the task loop, on the
  resume path (`AI_RECOVERY_ATTEMPT` set, no open stage): list in the result every statement
  that (a) tests `git status` or otherwise requires a clean checkout, (b) commits or writes a
  tracked file, (c) runs a session or a review. Show that every (a) is `clean_or_armed`, every
  (b) is either not entered with an armed tree (the plan review loop: T016's `! armed_resume`
  in its entry condition; never argue from `tasks untouched`, which tolerates IN_PROGRESS, or
  from the plan digest, which a committed partial checkpoint changes: plan review round 5, P3)
  or guarded by the fail-closed stop of T011, and every (c) is after `limit-disarm`. The
  path must match the stage list of the plan note "Armed resume re-enters at implementation"
  (start checks → `reconcile_disputes` → `base_reached` → `plan_decision_check` → queue check →
  `plan_decision_check` → implementation). Anything else → fix it here under the same rules.
  Checks after ai-run's first session (`~507`, `publish_ready`, `ensure_validated`) stay
  untouched.
- `limit-disarm` has exactly one call site in `scripts/ai-run` (a `grep -c` test on the script
  and the fixture's installed copy, as T014 does for `relaunch_verify`); `clean_or_armed` lives
  in `scripts/lib/common.sh` if both scripts can share it unchanged (`armed_resume` needs
  `run-manifest stage` and `limit-armed`, both via `ai_helper`), else once per script with the
  same body; say which in the result.
- Contract comment block in ai-pipeline right before the start-from-clean check: the four
  rules of the plan note (one predicate, no host write while armed, one consumer, after the
  disarm the normal rules) plus T016's fifth (an armed resume re-enters at implementation: no
  earlier stage, plan review or plan revision, runs on an armed tree) and T018's sixth and
  seventh (an armed manifest is terminal for recovery: every stop between the resume and the
  disarm is one ⛔ with nothing committed, whatever its reason and whatever `AI_AUTO_RECOVER`
  says; the consumer runs after ai-run's complete startup, dependency setup included) and
  T019's eighth (the arm ends at the act: every check of the consumer runs armed and is
  therefore terminal; `limit-disarm` is the last statement before the armed checkpoint or the
  first session), and that
  a new cleanliness check, commit, review or session on this path must use `clean_or_armed` /
  the fail-closed stop / the `! armed_resume` guard and extend the matrix, and a new check of
  the consumer goes before the disarm. The audit's
  "fail closed" claims for (b) are argued from rule 6 (T018's ai-recover check), never from a
  stop reason matching a hard rule (plan review round 7, P16: `recheck_fail`'s reason matches
  none).
- docs/workflow.md "Interruption, limits, and recovery": one paragraph "What the resumed run
  does with preserved work": the predicate, that a settled re-check or recorded disputes do not
  block the resume, that nothing is committed before ai-run validates, and the fail-closed
  stop for inconsistent review records. README "Recovery": one sentence.
- Flow chart (vault): the relaunch branch's "uncommitted task work is continued" note (T011)
  gains "through every start check of the resumed run".

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md, README.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_limit_relaunch_accept_*` in tests/test_workflow.py (fixtures as T011's
  `test_limit_relaunch_preserved_*`: `limit-far-dirty` schedules, AT set into the past,
  `ai-recover --stage 'usage limit relaunch'` relaunches; unless stated, each admitted case
  asserts: the pipeline completes, exactly one `Resuming preserved work of the usage-limit
  stop (<ID>).` where `<ID>` is the fixture's bound task (`T001` unless stated; the fix task's
  ID in the re-check scenario; T011's task-bound message, plan review round 7 P18), the
  manifest has no `limit_resume`, no commit between the relaunch's `record stop
  during` commit (or the scheduled HEAD when there is none) and ai-run's checkpoint of the task
  (`git log` parents), `recovery_calls()` empty, no `⛔`, no `Re-check of rejected findings`
  or `Start from a clean checkpoint` anywhere in the notifications or last-error history):
  - the reviewer's scenario (round 4 P3): a review with two BLOCKER/MAJOR findings, triage
    accepts one (a fix task is added to the queue) and rejects the other, the re-check
    (`MOCK_CODEX` recheck as the existing dispute tests) upholds the rejection and
    `reconcile_disputes` records it (`chore(ai): record review re-check`, `disputes.md`
    present, `recheck-status` `verified`); the fix task's session is `limit-far-dirty` →
    scheduled; relaunch → admitted (above), the fix task completes, a new review runs on the
    checkpointed fix, the run finishes; with `--no-pr`;
  - status `none` (no rejected finding) → admitted; status `verified` with recorded disputes
    (the scenario above) → admitted; status `verified` without a disputes file (every
    rejection withdrawn on re-check, if the fixtures can produce it; else say so) → admitted;
  - plan review on (default) with a `tasks untouched` queue: `limit-far-dirty` variant that
    edits the source file but NOT `.ai/tasks.md` (new mock mode or a mock flag, named in the
    result) → on the relaunch no plan review runs (the loop is not entered while armed, T016:
    the plan reviewer mock is not invoked after `▶ RESUMED` and no `chore(ai): record plan
    review` commit follows it), nothing is committed and ai-run runs; the same with
    `--skip-plan-review` → admitted; the stale-review variant (a committed partial checkpoint)
    is T016's `test_limit_relaunch_reenter_*` and is listed in the matrix by name;
  - `tasks complete` true (`limit-far-done` with a one-task queue, T011) and false → both
    reach ai-run (the arm is consumed either way); the bound task already DONE in HEAD with
    trailing edits (`limit-far-done-committed`, T011/T017) → reaches ai-run and is checkpointed
    before the final handoff (listed in the matrix by T011's test name; the armed checkpoint
    is a commit AFTER `limit-disarm`, so rule 2 holds);
  - inconsistent states fail closed with the arm kept and HEAD unchanged, no session, no
    `limit-disarm`: (i) `recheck-status` `pending` (the test removes the host binding of the
    re-check report, or rewrites dispositions to reject a finding without a re-check, after
    scheduling and before AT is moved: the relaunch's `limit-verify` must still pass, so only
    host state may change; if no host-only way exists, plant the state before the limit stop
    and say so) → stop `preserved task work carries uncommitted review records` or today's
    `Re-check` stop, nothing committed; (ii) an uncommitted `.ai/reviews/recheck.md` on the
    armed tree (planted before the limit stop so the digest includes it) → the same stop
    before any commit, the file byte-identical; both (i) and (ii) run twice: with the fixtures'
    `AI_AUTO_RECOVER=0` (the stop is the pipeline's) and with `AI_AUTO_RECOVER=1` plus
    `MOCK_RECOVER=commit_and_rerun` (the stop hands over to ai-recover, which is terminal on
    the armed manifest, T018: `recovery_calls()` empty, no `recovery checkpoint` commit, the
    ⛔ contains the re-check reason and `nothing was committed`, `limit_resume` retained);
  - `limit-disarm` appears exactly once in `scripts/ai-run` and in the fixture's installed
    copy; after the disarm a failing `.ai/validate` on the armed tree still gives T011's
    `Validation failed; T001 returned to IN_PROGRESS.` (nothing relaxed after the consumer).
- `test_limit_relaunch_*`, `test_recovery_*`, `test_usage_limit_*`, the re-check/dispute tests
  (`-k recheck`, `-k dispute`) and all pipeline tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_accept` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recheck` (must say `Ran N tests`, N ≥ 1).
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
- `observation_of` (~250–264) also returns `relaunch_at` (an int from the record, else None;
  T001's `observe relaunch` is its only writer and every other action drops it).
- `scripts/lib/dashboard.py` `inspect` (~382–392), when `liveness` is `gone`, in this order
  (plan review round 1, P5: a plain `paused` state is NOT evidence of a relaunch, since
  `ai_limit_pause` writes it for every in-process wait, and a newer error always wins):
  `crashed`; `alive`; `state == 'stopped'` or `errored` (a last-error newer than the
  observation) → `needs_you` (today, unchanged); `state == 'paused'` with an int `relaunch_at`
  → status `paused` (waiting for the scheduled relaunch); `stage == 'planning'` and `state` in
  `active`, `paused` → status `needs_you` with `run['last_error']` set to `planning session
  ended without a plan (killed?)` so `stop_note` and the ⛔ marker show it; then today's
  done/idle (a gone standalone runner killed during an in-process pause stays `idle`, as today).
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
  - steps `('step', 'build', 'T003')`, `('relaunch', '1700000000', 'Claude limit · relaunch after
    Sat 09:05')`, no runner, no marker → `--json` status `paused`, stage `build`; the view shows
    `⏸` and the note;
  - the same relaunch observation plus a `last-error` written after it → `needs_you` with that
    error (newer error wins);
  - killed during an in-process pause, no schedule: steps `('step', 'build', 'T003')`,
    `('pause', 'Claude until Sat 09:05')`, no runner → status `idle` (as today), never `paused`;
    steps `('step', 'planning', 'opus · first plan')`, `('pause', 'Claude until Sat 09:05')`, no
    runner → `needs_you` with `planning session ended without a plan`;
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
Model: opus

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


## T013 — `workflow.py exec-logged`: a detached runner's log created exclusively in the pinned `.ai/local` (DB-04, plan review round 2 P8)
Status: TODO
Dependencies: none
Model: opus

### Goal
A detached runner writes its output to a log file that was created new, inside the real
`.ai/local`, never through a symlink, FIFO or existing file, and becomes its stdout/stderr through
the already-open descriptor; the runner keeps the launcher's PID.

### Implementation notes
- Design: `.ai/current-plan.md` "Detached log (plan review round 2, P8)". `scripts/lib/workflow.py`,
  command `exec-logged NAME -- CMD [ARGS...]` (register in `main()`).
- NAME must match `^plan-\d{8}T\d{6}Z-[0-9a-f]{8}\.log$` (no path separators); else exit 2.
  Root = `git rev-parse --show-toplevel` of the cwd; `dir_fd = local_dir_fd(root)` (~3995,
  O_NOFOLLOW per component; None → `Error: .ai/local is missing or unsafe`, exit 1).
- `fd = os.open(NAME, O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC, 0o600,
  dir_fd=dir_fd)`: `FileExistsError` (any existing entry: file, symlink, FIFO) → `Error: log
  NAME already exists`, exit 1, the entry untouched; other `OSError` → exit 1 with its strerror.
  `fstat` must be a regular file (else close, exit 1); clear `O_NONBLOCK` (`fcntl`); close
  `dir_fd`; `os.dup2(fd, 1)`, `os.dup2(fd, 2)` (dup2 targets are inheritable), close `fd`;
  `os.execv(CMD, [CMD, *ARGS])` (CMD must be an absolute path to an executable; else exit 2
  before creating anything). Errors before the dup2 go to the caller's stderr. Comment why: the
  shell redirection `>"$log"` follows a planted symlink or blocks on a FIFO, and a
  second-resolution name is shared by two launches.
- No ai-plan change here (T006 uses it). Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_exec_logged_*` in tests/test_workflow.py (a fixture checkout with `.ai/local`;
  CMD a test script written with `os.chmod` 0o700 that prints `$$` to stdout and a line to
  stderr):
  - success: the log holds both lines, the printed PID equals the `Popen` PID (exec kept it),
    the file mode is 0600;
  - a symlink at NAME pointing at a sentinel file outside the checkout → exit 1 `already
    exists`, the sentinel byte-identical, the script never ran (its marker file absent);
  - a FIFO at NAME → returns within a scaled bound with exit 1, nothing blocks;
  - `.ai/local` replaced by a symlink to an outside directory → exit 1, nothing created there;
  - an existing regular file at NAME → exit 1, its content unchanged (never truncated);
  - two calls with different names run concurrently → two logs, each with only its own output;
  - NAME `../x.log`, `plan-x.log` and a relative CMD → exit 2, nothing created.

### Validation
Targeted: `python3 -m unittest discover -s tests -k exec_logged` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T006 — `ai-plan PROMPT_FILE` command with a confirmed `--detach` start (DB-04)
Status: TODO
Dependencies: T005, T013
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
  the shared options is ai-run's; ai-plan checks only its own (`--detach`; the prompt file
  exists, is regular and readable) and resolves every PATH argument against the caller's
  working directory BEFORE `ai_root` (which `cd`s to the checkout root, common.sh ~115): the
  prompt file, `--knowledge-dir DIR` and each `--read-dir DIR` (`[[ -d "$2" ]]` with ai-run's
  wording for a missing directory, then `cd -- "$2" && pwd -P`), rebuilding `rest` with the
  absolute values in the original order and multiplicity; every other option is passed through
  unchanged (plan review round 6, P14: `ai-run` resolves its directories at parse time from the
  caller's cwd, scripts/ai-run ~71–75 and T005, so a relative `--read-dir ./reference` from
  `/repo/subdir` would otherwise reach ai-run as `/repo/reference`, or be refused although the
  caller's directory exists).
- Foreground: `exec "$AI_BIN/ai-run" --plan "$prompt" "${rest[@]}"` (same PID: the dashboard,
  watchdog and lock see an `ai-run` runner, nothing else changes).
- Both modes start with `ai_root` (scripts/lib/common.sh ~113–119), as every toolkit command
  does: it runs the `paths` safety check (`safe_paths`, workflow.py ~45–63, whose default list
  includes `.ai/local`: a symlinked `.ai` or `.ai/local` dies here, before anything is launched)
  and then `mkdir -p .ai/local`. This is what creates `.ai/local` in a freshly installed
  checkout: `setup-project` copies files only (workflow.py ~348–360) and lists `.ai/local` just
  for the safety check (~312), so without `ai_root` the detached `exec-logged` (T013), which
  requires the pinned `.ai/local` to exist, would fail on first use (plan review round 5, P12).
  T013 keeps rejecting a missing or symlinked `.ai/local`: it is the second line of defence
  inside the child, not the creator. Comment this at the call.
- `--detach`: log name `plan-$(date -u +%Y%m%dT%H%M%SZ)-<8 hex from /dev/urandom>.log`
  (`log=.ai/local/$name` for messages only). Never redirect to the log path in the shell (plan
  review round 2, P8): `setsid python3 -I "$AI_BIN/lib/workflow.py" exec-logged "$name" --
  "$AI_BIN/ai-run" --plan "$prompt" "${rest[@]}" </dev/null &` and `pid=$!` (comment why `$!`
  is the runner: a non-interactive shell's background job is not a process-group leader, so
  setsid execs without forking, and `exec-logged` (T013) creates the log exclusively in the
  pinned `.ai/local` and execs the runner on that descriptor). Before the exec the child's
  errors reach ai-plan's stderr; the "ended early" path prints `(no log was created)` when the
  log file does not exist. Then poll every 0.2 s for at most
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
  - P8: two `ai-plan --detach` started at the same moment (two `Popen`s, sleeping mock) → two
    distinct `plan-*.log` files; the one whose child lost the lock holds `Another
    runner/reviewer owns this checkout`, the other holds its own session output (not truncated);
    with `.ai/local` replaced by a symlink to an outside directory → exit ≥ 1 BEFORE any launch
    (`ai_root`'s `paths` check refuses it; no child started, no `ended early`), nothing created
    outside (T013's own test covers `exec-logged`'s refusal when the symlink appears after the
    check); a sentinel symlink planted at every `.ai/local/plan-*` name the test can predict is
    never written (sentinel byte-identical);
  - first use (round 5 P12): `setup-project` into a fresh repository (the fixture's installer),
    assert `.ai/local` does NOT exist, then `ai-plan prompt.md --detach` with the sleeping mock
    as the first toolkit command run in that checkout → exit 0, `Planning session started`,
    `.ai/local` is a real directory and holds exactly one `plan-*.log`; the foreground
    `ai-plan prompt.md` on another fresh install likewise creates `.ai/local` and succeeds;
  - a missing prompt file → exit 1 before anything starts; `--help` exits 0;
  - relative directories from a subdirectory (round 6 P14): with `sub/reference`, `reference`,
    `sub/kb` and `kb` all present in the checkout, each holding a differently named marker
    file, run from cwd `sub/` `ai-plan ../prompt.md --read-dir ./reference --read-dir
    ../reference --knowledge-dir ./kb` in the foreground and with `--detach` → the mock's
    recorded args contain `--add-dir <abs>/sub/reference`, `--add-dir <abs>/reference` and the
    knowledge dir `<abs>/sub/kb`, in that order, and the `Read(//<abs>/sub/reference/**)`
    entry; a relative `--read-dir` that exists only at the checkout root (`--read-dir ./only-at-root`
    from `sub/`) → exit 1 with ai-run's missing-directory wording, nothing started;
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
- `pr_draft_path(branch) = binding_dir() / 'pr-draft' / f'{sha256(branch)[:16]}.json'` (own
  subdirectory, created 0o700 on `record`: revocation faults are confined to it and testable
  without touching the run manifest or stage records; plan "R15 revocation", round 2 P4).
- Command `pr-draft` (register in `main()`): `record URL HOW` (URL matches
  `^https://\S+/pull/\d+$`, HOW in `created`, `converted`; atomic write via the existing `atomic`
  of `{"branch", "url", "how", "at": now()}`; detached HEAD → fail); `get` (prints the URL and
  exits 0 only when the file parses, is a dict, its `branch` equals the current branch and `url`
  is valid; else exit 1 silently); `clear` (durable revocation: unlink — `FileNotFoundError` is
  fine — then fsync the `pr-draft` directory when it exists, then confirm the path is absent
  with `os.lstat`; any other `OSError` → `fail(f'cannot remove the draft record {path}:
  {strerror}')`, exit 1); `take URL` (consume a matching record: exit 1 silently when `get`
  would not print URL; else unlink + directory fsync + absence check as `clear`, print the
  record's HOW and exit 0; any `OSError` → exit 1 with the reason on stderr, the caller then
  never un-drafts).
- Comment why it lives in host state (agent sessions cannot forge "the pipeline drafted this") and
  why unreadable means not ours (never un-draft on doubt).
- No pipeline change here (T009). Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_pr_undraft_record_*` in tests/test_workflow.py: record then get prints the
  URL; clear then get exits 1; a record for another branch (switch branch) → get exits 1; a
  garbage file, a non-dict, an invalid URL → get exits 1; `record` with an invalid HOW or URL
  fails; the file is under `AI_STATE_DIR`, not in the checkout, in the `pr-draft` subdirectory;
  `take URL` prints the HOW and removes the record, `take` of another URL exits 1 and keeps it;
  fault (skipped when `os.geteuid() == 0`): the `pr-draft` directory made 0o500 with a readable
  record → `clear` exits 1 naming the path and `take URL` exits 1, and `get` still prints the URL
  (the record is intact; the callers in T009 then stop or leave the PR draft); the directory
  mode restored by `addCleanup`.

### Validation
Targeted: `python3 -m unittest discover -s tests -k pr_undraft_record` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T009 — PR step un-drafts only a PR the pipeline drafted (R15, pipeline)
Status: TODO
Dependencies: T008
Model: opus

### Goal
When the PR step runs with a clean review and no dispute, an existing draft PR that the pipeline
itself drafted becomes ready; a PR a human drafted stays a draft.

### Implementation notes
- Design: `.ai/current-plan.md` "R15", bullet "Pipeline". File `scripts/ai-pipeline` (~600–619).
- Split the draft reasons: `human_draft=yes` for `--draft`, `policy_draft=yes` for
  `unresolved == 1` or `disputes != 0`; `make_draft` as today.
- Existing PR, `make_draft=yes`: after a successful `gh pr ready --undo` + isDraft check, when
  `policy_draft=yes` and `human_draft=no` → `ai_helper pr-draft record "$url" converted`.
  Already a draft → no record change, except under `--draft` (below).
- `human_draft=yes` (`--draft` given) revokes pipeline ownership: whatever the PR's state (new,
  converted, already a draft), `ai_helper pr-draft clear` runs at the start of the PR step,
  right after `step pr`, BEFORE any `gh pr edit`/`ready --undo`/`create` (plan review round 1
  P4, round 2 P4). Its failure is NOT a warning: `printf 'could not revoke the pipeline draft
  record: %s; delete that file, then rerun ai-pipeline --draft\n' "${why#Error: }" >
  .ai/local/last-error` and `stop 'pull request'`, so the run never reports success with the
  record intact. Add `*'pipeline draft record'*` to ai-recover's hard-rule patterns
  (`scripts/ai-recover` ~138–141) so recovery escalates it (⛔ names the file) instead of
  retrying. Nothing is recorded in a `--draft` run.
- New PR created with `--draft`, `policy_draft=yes`, `human_draft=no` → `pr-draft record "$url"
  created` after `gh pr create` succeeded.
- Existing PR, `make_draft=no`: `is_draft=$(gh pr view … isDraft)`; when `true` and
  `how=$(ai_helper pr-draft take "$url" 2>/dev/null)` succeeds (ownership consumed BEFORE
  acting, round 2 P4: a record that cannot be removed never un-drafts) → `gh pr ready
  "$branch"`, re-check isDraft `false` → `printf 'Marked the PR ready (the pipeline had made it a
  draft).\n'`, `ai_log none "pull request marked ready: $url" PASS 'drafted by the pipeline earlier'`
  (before the `record pull request` host commit so it is committed with it); a failed ready or
  re-check prints a warning, re-records with `pr-draft record "$url" "$how"` (best effort; if
  that fails too the PR just stays a draft: fails closed) and continues (no stop). When `true`
  and `take` fails: if `pr-draft get` still prints this URL (a record that could not be
  removed) print `Warning: could not consume the pipeline draft record; PR left as draft.`,
  else print `PR is a draft set outside the pipeline; left as draft.` When `false` →
  `pr-draft clear` (stale record; a failure only warns here, it never un-drafts anything). Check that the `finish-summary` / `pr-body` wording about drafts stays right
  when the PR was un-drafted or stays a human draft (name what you checked in the result).
- Test mock `MOCK_GH` (tests/test_workflow.py ~620–623): `pr ready --undo` touches `gh-draft`,
  plain `pr ready` removes it (change on purpose; name it in the result).
- README pull-request part and docs/workflow.md "Pipeline contract" (~405): the rule, the
  `--draft` exception and the limitation (a human re-draft between two runs is not seen).
- Flow chart (vault): the PR step says the pipeline makes a clean PR ready again only when it
  drafted it itself; the big-picture bullet "If findings remain after two fix rounds, the PR is
  opened as a draft" gains that sentence.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-recover, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

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
  - three runs (P4): run 1 drafts for policy (record written); run 2 passes `--draft` with
    `MOCK_GH_EXISTING=1` and the PR still draft → the record is cleared, no plain `pr ready`;
    run 3 without `--draft`, clean review → no plain `pr ready` call, `gh-draft` still present,
    output says `left as draft`;
  - failed revocation (round 2 P4; skipped when `os.geteuid() == 0`): run 1 drafts for policy
    (record written); the test makes the `pr-draft` directory 0o500 (restored by
    `addCleanup`); run 2 with `--draft`, `MOCK_GH_EXISTING=1` → exit non-zero, last-error and
    the ⛔ contain `could not revoke the pipeline draft record` and the record's path, no `gh pr
    edit`/`pr ready` call recorded in that run, `recovery_calls()` empty (hard rule); run 3
    without `--draft`, clean review, the fault still in place → no plain `pr ready` call,
    `gh-draft` still present, output says `could not consume the pipeline draft record`, exit 0;
  - `MOCK_GH_READY_FAIL=1` on the un-draft → the pipeline finishes (exit 0), warns, and the
    record is back (`pr-draft get` prints the URL, same HOW);
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
Dependencies: T011, T014, T017, T016, T018, T019, T015, T004, T007, T009
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

