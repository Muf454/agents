# Task queue

Edit `scripts/`, `templates/`, `tests/`, `README.md` and `docs/` only (plus the vault flow chart
and hub Log line where a task says so). Never edit `.ai/bin`, `.ai/prompts`, `.ai/validate`,
`.ai/ci-setup`, `.ai/permissions.allow`, `.claude/settings.json` or `.github/workflows/*`
(gate files; needed gate changes are human steps in `.ai/handoff.md`). Vault: a task that
changes the flow updates `~/zWiki/zWiki/20 Projects/agents/agents-flow.md` and its `updated:`
date in the same task and appends a dated line to the Log of `agents.md`; never tick vault
checkboxes. If the vault edit is denied, record it in the result and in the handoff's
"## Flow chart" section.
Current batch (batch 11, `fix/flow-batch-11` from `fix/flow-batch-9` at 4fea72d, planned 2026-10-21
by an unattended planning session; scope chosen by mission control 2026-10-21 with Zack's
delegation): T301–T327, from vault `agents-backlog.md` RC-01 (gaps G1–G7, G9, G11; G8 and G10 are
later work). Revised after plan review round 1 (`.ai/reviews/plan.md` at 6bd6e3e, P1–P11),
round 2 (at 86df815: P2 again, P12–P15) and round 3, the last (at 4afd9ab: P16–P19): new tasks
T315–T327 sit in the queue where their dependencies need them, so the queue order (not the
number order) is the run order. Design: `.ai/current-plan.md` (its round-1 rules: gate first,
bound to the run, every layer forwards; round 2 adds: one escalation writer per shutdown chain;
round 3 adds: a stop request decides the terminal outcome, answers come from the current run);
scope, verified code facts, assumptions B1–B24 and the round-1 to round-3 dispositions:
`.ai/project-spec.md`. Line references in T301–T327 are at 4fea72d (same code as 4afd9ab);
re-check them before editing.
Batch 10 is built in parallel from the same commit: keep edits to the session contract in
`scripts/ai-run` and to `scripts/ai-pipeline` small and local, never touch the plan-review entry
condition (`ai-pipeline` ~478), `scripts/ai-status` or `tests/run_parallel.py`.
Tests never signal a process outside their own fixtures (start fixture runners with
`start_new_session=True` and signal only that group or a pid inside it), never call the real
`systemd-run` (fake it on `PATH`), and never touch a real checkout.
Previous batch (batch 9, `fix/flow-batch-9` from `fix/flow-batch-8` at 48fd9b5, planned 2026-10-20,
approved by Zack 2026-10-20): T101–T118, from BR-01, BR-02, BR-03, BR-14, FL-24, FL-25, FL-30 and
FL-33; T113–T118 are its review fixes. T118 stays as batch 9 left it (assumption B15).
Earlier batches' DONE tasks (T001–T046 are batches 6, 7 and 8; T101–T117 batch 9) are kept
unchanged because the host protects DONE blocks; their line references and gate notes are
historical.
Run-log rows written by the host must contain no `|` (ai_log does not escape it): use the
`ruling-row` helper (T101) or strip it.
BATCH 8 GATE RULE (still in force for batch 11; overrides the gate note below and the installed runner prompt):
run the full gate as `.ai/bin/ai-check` with the Bash tool's `run_in_background: true`, wait for
its completion notice and read the result; make no edits and no commits while it runs, and do not
end the session while it runs. If its result cannot be obtained in the session, do NOT mark the task
BLOCKED for that reason: finish on the targeted checks, write "full gate result unknown in the
session; left to the host gate" in the result and mark the task DONE when everything else is met.
The host runs the full gate after every DONE session and sets the task back to IN_PROGRESS if it
fails.
Previous batch (batch 7, `fix/flow-batch-7` from `master` at 1423b60, planned 2026-10-18): T022–T036,
from FL-28 to FL-31; T001–T021 are batch 6's.
Batch 6 source: vault `agents-backlog.md` (MC-01 part 1, DB-04, R15; Zack's decisions of 2026-10-17 in
the `agents.md` Log), planned 2026-10-17 on `feature/limits-plan-stage` (from `fix/flow-batch-5`
at edc3dc6, PR #30 on PR #29, neither merged).
Line references in T001–T021 are at edc3dc6.
Every behaviour change gets an offline regression test in the existing style; every task
leaves `.ai/bin/ai-check` passing and updates README.md / `docs/workflow.md` where the
behaviour it changes is described.
Gate note (batch 7; batch 8 uses the BATCH 8 GATE RULE above): `.ai/validate` runs the shell
syntax checks and then `tests/run_parallel.py` (about 11 min on this machine, past the 600 s Bash
tool limit). Should `.ai/bin/ai-check` still time out in the session, run the task's targeted
tests, record the timeout in the result, and leave the full gate to the host's post-task `ai-check`. Tests with time bounds run in parallel: assert
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
Status: DONE
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
- Validation: `-k limit_relaunch_consume` 10 OK; `-k limit_relaunch` 85 OK; `-k recovery` 70 OK;
  `-k Docs` 3 OK; `.ai/bin/ai-check` PASS (902 tests, 561.5 s).


## T015 — Armed-tree acceptance contract: one predicate on the whole resume path, no host write while armed (MC-01 part 1, plan review round 4 P3 design task)
Status: DONE
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
Done (the first session hit the 1800 s limit; its work was kept by the recovery checkpoint
0e4f7ea and reconciled here without code change).

Audit of the resume path (`AI_RECOVERY_ATTEMPT` set, no open stage):
- ai-pipeline, start → `ai-run --approved` call. (a) clean-checkout tests: the start check
  (`clean_or_armed`); `reconcile_disputes`' two tests (non-verified dirty tree, and "clean after
  recording it"), both `clean_or_armed`. The open-stage checks (`complete_plan_stage`,
  `complete_stage`) and the plan revision loop's check are not on the path (no open stage; loop
  guarded). `publish_ready`, the post-ai-run checks stay untouched. (b) commits/tracked writes:
  `reconcile_disputes`' `disputes-record` and `host_commit`: fail closed first (pending re-check,
  dirty `recheck.md`/`disputes.md`/`fallback-log.md`, or `disputes-record --check` failing on a
  verified re-check → `recheck_fail`, terminal by rule 6, ai-recover's armed check); otherwise
  nothing is added and nothing dirty, so no commit. `revision-queue-repair` and the plan review
  loop's `host_commit`/stage-set: `! armed_resume` in their entry conditions (T016). `run-manifest
  start` only for a human start; `fix-rounds init`, `pipeline-register`, notifications write host
  state or ignored `.ai/local` only. (c) sessions/reviews: `ai-review --recheck` only for
  `pending` (refused armed above), `ai-review --plan` and the plan revision session inside the
  guarded loop; the first is ai-run's, after the disarm. Stage order matches the plan note:
  start checks → `reconcile_disputes` → `base_reached` → `plan_decision_check` → queue check →
  `plan_decision_check` → implementation (`tasks complete || armed_resume` → ai-run).
- ai-run, start → first `claude_session`. (a) the start check (`clean_or_armed`, sets
  `AI_ARMED=yes`). (b) `outcome attempt-reconcile` (host), `approved-gate.sha256` (ignored),
  the stop handler's `ai_log` (now skipped while `AI_ARMED=yes`: was a tracked run-log write on a
  consumer stop), dependency setup (`ai_deps`, rule 7). The first tracked write is
  `checkpoint_done`'s or the loop's `ai_helper state implementing`, both after `limit-disarm`.
  (c) the first session is after `limit-disarm` (single call site, rule 8).
- `clean_or_armed`/`armed_resume` now live once in `scripts/lib/common.sh`, shared unchanged by
  both scripts (`AI_ARMED` set by the predicate, reset to `no` on load, `consumed` after the
  disarm). `disputes-record --check` (workflow.py) writes nothing and fails unless a real call
  would write nothing; a real call no longer rewrites an unchanged `disputes.md`.
- Contract comment block (rules 1–8 + the extension rule) before ai-pipeline's start check.

Matrix (`test_limit_relaunch_accept_*`, 15 tests): reviewer scenario (M1 accepted → T002, M2
rejected, re-check upheld and recorded, T002 limited, resumed, reviewed, finished, `--no-pr`);
status `none`; `verified` without disputes (fixture: M2 `withdrawn` on re-check, no
`disputes.md`); untouched queue with plan review on and `--skip-plan-review` (mock mode
`limit-far-keep`: edits `preserved.txt`, not `.ai/tasks.md`; plan reviewer not invoked, no plan
review commit); `tasks complete` true/false; fail closed: `pending` via a host-only removal of the
re-check binding (`limit-verify` still passes) and an uncommitted `recheck.md` planted by the
limited session (`MOCK_LIMIT_APPEND`), each with recovery off and on (`MOCK_RECOVER=commit_and_rerun`:
terminal, no recovery call/commit); lost host dispute records; `disputes-record --check` writes
nothing; a consumer stop writes no run-log line; one predicate (in `lib/common.sh`, three uses in
ai-pipeline before ai-run) and one `limit-disarm` (script and installed copy). Listed by name, not
repeated: `test_limit_relaunch_reenter_partial_checkpoint_*` (stale plan review),
`test_limit_relaunch_preserved_done_committed_work_is_checkpointed` (DONE in HEAD with trailing
edits), `test_limit_relaunch_preserved_done_work_failing_validation_commits_nothing` (failing
gate after the disarm), `test_limit_relaunch_consume_*` (consumer stops).

Docs: docs/workflow.md "What the resumed run does with preserved work" and the recovery
contract; README "Recovery"; vault flow chart node ("through every start check of the resumed
run").

## T004 — Dashboard: a run waiting for its limit relaunch shows paused; a killed planning session shows as a stop (MC-01, DB-04)
Status: DONE
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
`observation_of` returns `relaunch_at`; `inspect` (scripts/lib/dashboard.py) now maps a gone run with
`paused` + int `relaunch_at` to `paused` and a gone planning session still `active`/`paused` to
`needs_you` with the "ended without a plan (killed?)" note, after the stopped/errored rule. Tests:
3 `dashboard_limit_relaunch_*`, 13 `dashboard_plan*` (6 new, all pass); gate `ai-check` PASS (923
tests). docs/workflow.md updated. Vault flow chart mentions the dashboard once, not its statuses; flow unchanged.


## T005 — `ai-run --plan --read-dir DIR`: read-only reference directories for the planning session (DB-04)
Status: DONE
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
DONE 2026-10-18. `scripts/ai-run`: `--read-dir DIR` (repeatable) parsed beside `--knowledge-dir`
(existing dir, `pwd -P`, refuses `*?[]()`, `,`, newline with `Invalid --read-dir path: …`;
missing → `Read directory not found: …`); refused without `--plan`. The plan block appends
`--add-dir DIR` to `knowledge_args` and `Read(//DIR/**)` to `plan_allowed`, and the contract
sentence `Read-only reference directories: …. Read them as needed; never edit them.`; no
Edit/Write entry. Usage text and docs/workflow.md "Plan stage" updated. Tests
`test_plan_read_dir_adds_read_only_directories` (symlinked dir resolved, exact allowlist =
plan-allowlist + Read entries, prompt names both), `test_plan_read_dir_invalid_paths_run_no_session`
(missing, `*`, `,`, `(`, `?`, `]`, newline; no mock call), `test_plan_read_dir_refused_outside_plan`.
Evidence: `-k plan_read_dir` Ran 3 OK; `-k queue_repair_planning` Ran 4 OK; `-k plan_session`
Ran 12 OK; `.ai/bin/ai-check` Ran 926 tests OK. Flow chart unchanged (T006 owns the plan node).


## T013 — `workflow.py exec-logged`: a detached runner's log created exclusively in the pinned `.ai/local` (DB-04, plan review round 2 P8)
Status: DONE
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
DONE 2026-10-18. `exec_logged` in scripts/lib/workflow.py (next to `local_dir_fd`), registered
in `main()` as `exec-logged`. Usage errors (no `--`, NAME not matching `EXEC_LOG_NAME`, CMD not an
absolute executable path) exit 2 before `.ai/local` is opened; a missing/unsafe `.ai/local`, an
existing entry (`FileExistsError`: file, symlink, FIFO) or another `OSError` exit 1 through
`fail`; the fd is checked regular, `O_NONBLOCK` cleared, dup2'd to 1 and 2, then `execv`.
Tests: 7 `test_exec_logged_*` in tests/test_workflow.py (success with PID and mode 0600,
symlink to an outside sentinel, FIFO within `SHORT_TIMEOUT`, symlinked and missing `.ai/local`,
existing file not truncated, two concurrent launches, `../x.log` / `plan-x.log` / `sub/…` names,
relative and missing CMD). Validation: `python3 -m unittest discover -s tests -k exec_logged`
Ran 7 tests OK; `.ai/bin/ai-check` PASS (933 tests, 558.9 s). No ai-plan change (T006), flow
unchanged.

## T006 — `ai-plan PROMPT_FILE` command with a confirmed `--detach` start (DB-04)
Status: DONE
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
DONE 2026-10-18. The earlier block (working-tree file 0644, runner may not chmod) was cleared by
the human: `scripts/ai-plan` is now -rwxr-xr-x on disk and 100755 in Git. Re-verified: `-k ai_plan`
Ran 12 OK; `-k setup` Ran 30 OK; `-k Docs` Ran 3 OK; `-k script_modes` Ran 1 OK;
`.ai/bin/ai-check` Ran 945 tests OK.
Implemented: `scripts/ai-plan` (foreground `exec ai-run --plan`; `--detach` via `setsid python3 -I
workflow.py exec-logged plan-<stamp>-<8 hex>.log -- ai-run --plan … </dev/null &`, 0.2 s poll of
`observation.json` for `planning`/`active`/that PID, `ended early` with the log tail (or `(no log was
created)`), `could not confirm` exit 1 leaving the runner running, `disown`; `AI_PLAN_ACK_SECONDS`
validated; prompt, `--knowledge-dir` and `--read-dir` resolved from the caller's cwd before
`ai_root`, other options passed through in order). `setup-project` installs `.ai/bin/ai-plan`
(workflow.py list); the upgrade test helper `old_toolkit(drop=…)` now also strips `ai-plan`.
Mock claude: `MOCK_PLAN_SLEEP` and an `isfile` guard for the observation copy. Docs: README
(Plan section, Modes row, scripts table), docs/workflow.md "Plan stage"; vault flow chart (plan
node, notification row). Note: ai-run orders `--add-dir` as knowledge dir first, then read dirs
in the given order; the P14 test asserts that real order.
Evidence: `-k ai_plan` Ran 12 tests OK; `-k setup` Ran 30 tests OK; `-k Docs` Ran 3 tests OK;
`-k upgrade_creates_ai_plan` 1 OK; `test_dashboard_plan_live_ai_run_plan_is_running_on_plan` and
all plan-stage tests pass in the gate. Gate:
945 tests, 1 failure = the script-mode test above (nothing else).

## T007 — Planning sessions in the outcome log and the run log (DB-04, logging)
Status: DONE
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
DONE. `outcome plan RESULT MODEL SECONDS [TASKS] [--revision]` in workflow.py; ai-run records
`done` + a `plan written:` run-log row on success and `stopped`/`interrupted`/`timeout` from
on_exit (gate intact only). Docs: README Outcome log, docs/workflow.md Outcome log, vault
agents-flow.md bullet. Tests `test_plan_outcome_*` (3; mock gained `plan-timeout`).
`-k plan_outcome` 3 OK, `-k outcome` 85 OK, `-k Docs` 3 OK; `.ai/bin/ai-check` PASS (948 tests, 569.5 s).


## T008 — Host record of a PR the pipeline drafted (R15, helper)
Status: DONE
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
Added `pr-draft` (`record URL HOW`, `get`, `clear`, `take URL`) to `scripts/lib/workflow.py` beside
`stage_path`, registered in `main()`. Record under `binding_dir()/pr-draft/` (0o700), unreadable or
foreign data reads as "not ours". `clear`/`take` unlink, fsync the directory and lstat-confirm.
Six `test_pr_undraft_record_*` tests (round trip and location, per branch, garbage/invalid, bad
arguments incl. detached HEAD, take, 0o500 fault) pass: `Ran 6 tests`. Gate `.ai/bin/ai-check`: 954
tests OK. No pipeline change (T009).


## T009 — PR step un-drafts only a PR the pipeline drafted (R15, pipeline)
Status: DONE
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
- `scripts/ai-pipeline` PR step: `human_draft` (`--draft`) vs `policy_draft` (unresolved or
  disputes); `--draft` runs `pr-draft clear` right after `step pr`, before push/`gh`, and a
  failure writes `could not revoke the pipeline draft record: …; delete that file, then rerun
  ai-pipeline --draft` and stops `pull request`. A policy draft records `created` (after `gh pr
  create`) or `converted` (after `ready --undo` + isDraft check). `make_draft=no` on an existing
  draft: `pr-draft take URL` first, then `gh pr ready` + isDraft `false` → message and run-log
  `pull request marked ready` (committed with `record pull request`); a failed ready warns and
  re-records the same HOW; a failed take prints `could not consume…` when the record is still
  there, else `PR is a draft set outside the pipeline; left as draft.` A ready PR clears a stale
  record (warning only on failure).
- `scripts/ai-recover`: `*'pipeline draft record'*` added to the hard-rule patterns.
- Mock change (deliberate): `MOCK_GH` `pr ready --undo` touches `gh-draft`, plain `pr ready`
  removes it. No other existing test changed.
- Tests: 8 `test_pr_undraft_*` pipeline tests (created/converted un-draft, human draft, `--draft`
  never recorded, three-run revocation, failed revocation with auto-recovery on: ⛔ and
  last-error name the record path, no `pr edit`/`pr ready`, `recovery_calls()` empty, then a
  clean run leaves it draft with `could not consume`; `MOCK_GH_READY_FAIL` keeps the record as
  `created`; stale record cleared). With the failed revocation and recovery on, stderr carries
  the escalation summary; the reason is asserted in last-error and the ⛔.
- Wording check: `pr-body` adds draft warnings only for disputes/unresolved and
  `finish-summary` the "Decide the unresolved review findings (draft PR…)" todo only when
  unresolved, so an un-drafted PR (clean run) gets no draft wording and a human draft gets no
  claim either way. Limitation: when `gh pr ready` fails the summary does not say the PR is
  still a draft; the console warning does.
- Docs: README pull-request step, docs/workflow.md PR stage (rule, `--draft` exception,
  limitation). Vault `agents-flow.md` PR node and draft bullet updated; hub Log line.
- Validation: `-k pr_undraft` Ran 14 OK; `-k draft` Ran 25 OK; `.ai/bin/ai-check` PASS (962
  tests, 612.9 s; it went past the 600 s foreground tool timeout, finished in the background
  with exit 0).

## T010 — Docs, flow chart and handoff audit (all items)
Status: DONE
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
DONE 2026-10-18 (claude, runner session). Audit against the code; wording fixed, flow unchanged.
- README: the "weekly limit" hard rule is the code's `beyond the wait budget` escalation (fixed in
  Recovery and Usage limits); ai-watchdog `--recover` row and crash bullet cover a due usage-limit
  relaunch; `AI_LIMIT_RELAUNCH_MAX` (0–9, default 2, other values count as 2) and `AI_PLAN_ACK_SECONDS`
  (environment only, 1–999999, default 20) in a settings note; `exec-logged` named in the ai-plan row.
- docs/workflow.md: hard-rule list says "a usage limit beyond the wait budget (no relaunch covers it)".
- Usage texts: `ai-run` and `ai-pipeline` `--help` describe the watchdog relaunch; `watchdog.py --recover`
  help names a due usage-limit relaunch. No behaviour change.
- Vault `agents-flow.md`: audited, no gap, unchanged (`updated:` already 2026-10-18); the `agents.md`
  Log line is written for the batch.
- Handoff: "What has been implemented?" now says all 19 tasks DONE (was "this is the plan"); T010 in
  the validation run and the next-action; the test prefixes listed in "Covered by automated tests"
  all exist in tests/ (verified by name); human steps unchanged (upgrade, watchdog reinstall,
  retire launch-plan.sh, mission control to ai-plan).
- Mismatch recorded, not fixed (behaviour): `scripts/ai-recover` uses 2 for an `AI_LIMIT_RELAUNCH_MAX`
  outside `^[0-9]$` without a message; T001 asked for validation next to `max`.
- Validation: `-k Docs` 3 OK; `-k flow_this_repo` 1 OK; `.ai/bin/ai-check` PASS (962 tests, 617.3 s,
  exit 0; the call passed the 600 s foreground limit and finished in the background).

## T020 — Draft ownership only from a confirmed ready PR (R15, review round 1 M1)
Status: DONE
Dependencies: T009
Model: opus

### Goal
The pipeline records `pr-draft … converted` only when it established that the existing PR was
ready (`isDraft == false`) before it converted it. An unknown initial draft state never creates
ownership, so a human draft can never be un-drafted later because of a failed lookup.

### Implementation notes
- `scripts/ai-pipeline` ~667–674: the initial `is_draft` lookup suppresses failure (`|| true`);
  an empty or unparsable result currently takes the convert branch and records `converted`.
- Keep the fail-toward-draft behaviour: with `make_draft=yes` and an unknown state the pipeline
  may still run `gh pr ready --undo` and confirm draft, but it records ownership only when the
  initial lookup succeeded and returned exactly `false`. Print a short note when ownership is not
  recorded because the prior state was unknown.
- Check the other branches (`make_draft=no`) for the same unknown-state path: an unknown state
  must neither take nor clear the record.
- README / `docs/workflow.md`: the un-draft rule mentions that an unknown prior state never
  counts as a pipeline draft (only where that rule is described).

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Regression `test_pr_undraft_unknown_state_never_records_ownership`: a human-drafted existing
  PR, the first `isDraft` lookup fails, a policy-draft run → no `pr-draft` record; a later clean
  run leaves the PR draft (`left as draft`) and never calls `gh pr ready` without `--undo`.
- Existing `test_pr_undraft_*` still pass (a confirmed-ready PR converted by policy is still
  recorded and later made ready).
- Mutation: restoring the record on an unknown state fails the new test.

### Validation
Targeted: `python3 -m unittest discover -s tests -k pr_undraft` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-18 (claude opus): `scripts/ai-pipeline` records `pr-draft … converted` only when
`pipeline_drafted=yes` and the first `isDraft` lookup returned exactly `false`; with an unknown
state the conversion still runs (fail toward draft) and prints "Note: the PR draft state was
unknown before; not recorded as a pipeline draft …". Audit of the `make_draft=no` branches: they
compare `is_draft` with exactly `true`/`false`, so an unknown state neither takes nor clears the
record (no change). Mock gh gained `MOCK_GH_DRAFT_LOOKUP_FAIL_ONCE` (first `isDraft` query exits
1). New `test_pr_undraft_unknown_state_never_records_ownership`. README and docs/workflow.md
un-draft rule mention the unknown state; vault flow chart unchanged (its detail level does not
cover the record). Evidence: `-k pr_undraft` Ran 15 OK; mutation (record on `pipeline_drafted`
alone) fails the new test (`0 != 1` on `pr-draft get`); `.ai/bin/ai-check` PASS (963 tests,
609.4 s; past the 600 s tool limit, finished in the background, exit 0).

## T021 — `ai-plan --detach` reports a plan that finished before acknowledgement as success (DB-04, review round 1 N1)
Status: DONE
Dependencies: T006
Model: opus

### Goal
A detached planning session that completes successfully between two acknowledgement polls is
reported as started (PID and log, exit 0), not as "ended early".

### Implementation notes
- `scripts/ai-plan` ~72–87: `started` accepts only `planning/active` for the PID. When the
  child has exited, `wait` returned 0 and the observation is `stage == planning`,
  `state == done` with the same `pid`, print the PID and log as on a confirmed start and exit 0.
- A non-zero exit, or exit 0 without a matching `planning/done` observation, stays an
  "ended early" failure (exit status unchanged).
- Same plan-review history: P21 (plan review round 9).

### Likely affected modules
scripts/ai-plan, tests/test_workflow.py, README.md (only if the ai-plan row describes the exit)

### Acceptance criteria
- Regression `test_ai_plan_detach_finished_before_ack_is_success`: the fake runner writes
  `planning/done` with its PID and exits 0 before the parent's first poll → exit 0, output names
  the PID and the log.
- Regression `test_ai_plan_detach_exit_zero_without_done_is_failure`: exit 0 with no matching
  observation → exit 1 with `ended early`.
- Existing `test_ai_plan_*` still pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k ai_plan` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE 2026-10-18. `scripts/ai-plan`: the predicate is `observed STATE`; after the child exits,
`wait` 0 plus this PID's `planning/done` prints `Planning session started: pid N, log PATH` and
exits 0; anything else stays `ended early` (status unchanged). Usage text, README Plan section
and docs/workflow.md updated. Tests replace the fixture's `ai-run` with a script that never writes
`planning/active`, so the exit branch is always the one exercised:
`test_ai_plan_detach_finished_before_ack_is_success`,
`test_ai_plan_detach_exit_zero_without_done_is_failure` (no observation, another PID, non-zero
exit with its own `done` → exit 3). `-k ai_plan`: Ran 14 tests OK. `.ai/bin/ai-check`: Ran 965
tests OK (600.1 s; finished in the background past the 600 s tool timeout, exit 0). Flow chart
unchanged (the detached launch already ends in "started").


## T022 — Host gate-time record: `outcome gate` and `gate-seconds` (FL-28 part 1, helper)
Status: DONE
Dependencies: none
Model: opus

### Goal
The host outcome log records every host gate run with its measured seconds and result, and one
helper answers "how long does this project's gate take?" from that agent-unwritable record.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-28 part 1", bullet "Record".
- `scripts/lib/workflow.py` `outcome()` (~3772): new kind `gate RESULT SECONDS`. RESULT must be
  `pass`, `fail` or `timeout`, and SECONDS all digits; anything else fails with `Usage: outcome
  gate pass|fail|timeout SECONDS`. `record.update(result=…, seconds=int(…))` (project, branch and
  time come from the common code). Extend the docstring.
- New command `gate-seconds` (register in `main()`): call `check_state_root` as `outcome` does,
  read `outcomes_path()` with the existing reader (`read_outcomes`; torn lines ignored), keep
  records with `kind == 'gate'`, `result == 'pass'`, `project == project_name()` and an int
  `seconds >= 0`, then print `max(seconds of the last 3)`, or `0` when there are none or no log
  exists. Extra arguments → usage error.
- `outcomes_report` (~3902, `ai-status --outcomes`): check that it skips unknown kinds. If it
  does not, filter `gate` out there; the report output must stay unchanged.
- No ai-run change here (T023). Flow unchanged in this task.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_gate_time_*` in tests/test_workflow.py (fixture `AI_STATE_DIR` as the
  outcome tests use):
  - `outcome gate pass 300` appends one JSON line with `kind` `gate`, `result` `pass`, `seconds`
    300 and `project`, `branch` and `time` set; `outcome gate maybe 3`, `outcome gate pass x` and
    `outcome gate pass` exit non-zero with the usage text and append nothing;
  - `gate-seconds` prints `0` with no log, `0` with only `fail` and `timeout` lines, `300` after
    one pass of 300, and `500` after passes of 100, 500 and 200. After further passes of 120, 130
    and 140 it prints `140` (only the last 3 count). A pass line from another project (written
    with a different `project` value) is ignored, and a torn last line is ignored;
  - `ai-status --outcomes` output is byte-identical with and without gate lines in the log.
- All existing `test_*outcome*` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_time` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-18. `scripts/lib/workflow.py`: `outcome gate pass|fail|timeout SECONDS` (exactly two
arguments, SECONDS `isdigit`, else `Usage: outcome gate pass|fail|timeout SECONDS`, nothing
appended) records `result` and int `seconds` with the common time/project/branch. New
`gate_seconds` (command `gate-seconds`, no arguments): `check_state_root` as `outcome` does,
lenient `read_outcomes`, keeps `kind gate`, `result pass`, `project == project_name()` and an
int (not bool) `seconds >= 0`, prints `max` of the last 3, default 0. `outcomes_report` did NOT
skip unknown kinds at its "No outcomes recorded yet" check (a log of only gate lines printed a
report header), so it now drops `gate` records first. docs/workflow.md describes both.
Tests `test_gate_time_*` (4): record + usage errors (incl. `-1` and 3 args), last-3 max
(0/0/300/500/140, extra argument → exit 1), other project / non-int seconds / torn tail
ignored, `ai-status --outcomes` byte-identical with gate lines (empty log and task+review log).
Evidence: `-k gate_time` Ran 4 OK; `-k outcome` Ran 86 OK; `.ai/bin/ai-check` PASS (969 tests,
618.5 s, finished in the background past the 600 s tool timeout). Flow unchanged.


## T023 — ai-run records its gate runs and gives implementation sessions room for the gate (FL-28 part 1, runner)
Status: DONE
Dependencies: T022
Model: opus

### Goal
An implementation session's limit grows with this project's measured gate time (room for two
gate runs, at most double the base), so a slow gate no longer uses up the session. Every host gate
run of `ai-run` is measured and recorded.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-28 part 1", bullet "Runner". File `scripts/ai-run`.
- `checkpoint_done` (~664–702) and the final check (~774–783): `gate_started=$SECONDS` before
  `AI_CHECK_TIMEOUT=$remaining "$AI_BIN/ai-check"`, capturing its exit code without
  `set -e` surprises. After `ai_guard_verify` (never a helper before that check: the gate may have
  changed), add `ai_helper outcome gate <pass|fail|timeout> "$(( SECONDS - gate_started ))"
  2>/dev/null || printf '%s\n' 'Note: could not record the gate time.' >&2`. The result is
  `timeout` for exit 124 or 137, `pass` for 0, `fail` otherwise. One small function
  `record_gate CODE STARTED` serves both sites. The existing failure handling after it is unchanged.
- `claude_session` (~291–345): when `track_attempt == yes`, `gate=$(ai_helper gate-seconds
  2>/dev/null)`; a value not matching `^[0-9]{1,7}$` counts as 0. Then `allowance=$(( 2 * gate ))`,
  capped at `session_timeout`, and `limit=$(( session_timeout + allowance ))`, before the existing
  `remaining` cap. Compute it once per `claude_session` call, before the `while` loop (a limit
  pause retry keeps it). Triage, plan-revision and `--plan` sessions are untouched
  (`track_attempt` is `no` there; check).
- `Session:` line (~303): with allowance 0 it stays byte-identical. Otherwise it reads `Session: T001
  [model x] (limit 1600s: 1000s + 600s for two gate runs of 300s; log …)`. When the remaining-time
  cap cut the limit, the printed limit is the capped value; the breakdown may still name the
  allowance.
- Usage text (~11–12): "1800 seconds/session (an implementation session also gets twice the
  measured gate time, at most another session_timeout)". README (run defaults, wherever
  `--session-timeout` is described) and docs/workflow.md (session limits): the rule, the source
  (host outcome log, `gate` lines, last 3 passes) and why it is bounded.
- Flow chart (vault `agents-flow.md`, "One task" section): the session node notes "limit = base
  + room for two measured gate runs (max double)", plus its `updated:` date and a hub Log line.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md

### Acceptance criteria
- Tests named `test_session_gate_allowance_*` in tests/test_workflow.py (fixture `ready()`;
  gate lines seeded through `python3 HELPER outcome gate pass N` in the fixture env):
  - no gate lines: `ai-run --approved --session-timeout 1000` prints exactly today's
    `(limit 1000s; log` form;
  - `gate pass 300` seeded: the same run prints `limit 1600s` and `1000s + 600s`; with
    `gate pass 900` seeded it prints `limit 2000s` (cap: allowance ≤ 1000);
  - `--run-timeout 1200` with `gate pass 300` seeded prints a limit ≤ 1200 (remaining-time cap);
  - a triage session (`ai-run --approved --triage`, as the existing triage tests start it) with
    gate lines seeded prints no allowance;
  - after a run where the task's checkpoint ran the host gate, the outcome log has exactly one
    new `gate` line with `result` `pass` and int `seconds` ≥ 0 (two when the final check also ran);
    a fixture `.ai/validate` that exits 1 records `fail`;
  - mutation evidence in the result: dropping the `track_attempt` condition makes the triage
    case fail.
- Existing tests asserting the `Session:` line or session timeouts (`-k session_timeout`,
  `-k timeout`, `-k outcome`) pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k session_gate_allowance` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k timeout` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done 2026-10-18. `scripts/ai-run`: `record_gate CODE STARTED` (pass for 0, timeout for 124/137,
else fail; a failed append is only a note) runs after `ai_guard_verify` at both host gate sites
(`checkpoint_done`, final check), which now capture the exit code (`|| gate_code=$?`) and keep
their failure handling. `claude_session` computes the allowance once, before its loop, only when
`track_attempt == yes`: `gate-seconds` checked against `^[0-9]{1,7}$` (else 0), `min(2 × G,
session_timeout)`, limit = base + allowance, then the remaining-time cap. `Session:` line is
byte-identical with allowance 0, else `(limit 1600s: 1000s + 600s for two gate runs of 300s; log …)`.
Usage text, README (after the session budget), docs/workflow.md (after `gate-seconds`; the
watchdog "hung" note), vault flow "Inside one task".
Tests `test_session_gate_allowance_*` (5): plain/1600/2000 limits, run-timeout cap, triage plain,
one `pass` gate line per checkpoint gate (three after the second run: checkpoint + final), failing
`.ai/validate` records `fail`. Mutation: `if true` instead of the `track_attempt` check fails the
triage test (`limit 2400s: 1800s + 600s …`).
Three existing tests read every outcome line and now see the runner's gate lines, so they filter
them (`test_runner_logs_task_outcomes_and_report`, `test_runner_logs_blocked_and_failed_validation_attempts`,
`test_outcome_crash_killed_runner_logged_once_at_next_start`); their assertions are otherwise unchanged.
Evidence: `-k session_gate_allowance` Ran 5 OK; `-k timeout` Ran 12 OK; `-k Docs` Ran 3 OK;
`-k outcome` Ran 86 OK after the filter; `.ai/bin/ai-check` PASS (974 tests, 610.2 s, finished in the
background past the 600 s tool timeout).
The runner's post-checkpoint gate then failed only on `test_pr_body_flow_this_repo_declares_the_flow_chart`
(the handoff "## Flow chart" line did not start with "Flow chart updated (…)"); mission control fixed
the line in 0166a48. Re-verified in a fresh session: `-k flow_this_repo -k session_gate_allowance`
Ran 6 OK; `.ai/bin/ai-check` PASS (974 tests, 608.9 s, finished in the background past the 600 s tool timeout).


## T024 — Run manifest: read the session's task, record a timeout rerun once per task (FL-28 part 2, helper)
Status: DONE
Dependencies: none
Model: opus

### Goal
`ai-recover` can ask the host manifest which task the stopped session worked on, and can claim
the one timeout commit-and-rerun allowed per task per human-started run.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-28 part 2", bullet "Helper". File `scripts/lib/workflow.py`
  `run_manifest` (task-set ~1526, task-clear ~1534, `LIMIT_FIELDS`/`limit_fields_valid` ~1299–1325
  as the model for validation).
- `task` (read only, no arguments): print `data['task']` and exit 0 when present; else exit 1 with
  no output.
- `timeout-rerun TASK`: `task_id_valid(TASK)` or a usage error. The optional field
  `timeout_reruns` is a list of unique `task_id_valid` strings, at most 200 entries; any other
  shape makes the manifest invalid, as a wrong limit field does (extend the validity check, and
  name it in the comment above `LIMIT_FIELDS` or beside it). TASK already present →
  `fail(f'session timeout: {task} was already committed and rerun once in this run')`, nothing
  written. Otherwise append and write atomically, exit 0.
- `start` writes a fresh dict (check it drops the field). `clear-attempts` keeps
  `timeout_reruns`. Find its callers and comment at the site why: a resumed pipeline must not
  reset "once per task" (spec A3).
- No ai-recover change here (T025). Flow unchanged in this task.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_timeout_rerun_manifest_*` in tests/test_workflow.py (after `run-manifest
  start` as `approve_run` does):
  - `run-manifest task` exits 1 with empty output before `task-set`; prints `T003` after
    `task-set T003`; exits 1 again after `task-clear`;
  - `timeout-rerun T003` exits 0 and the manifest holds `timeout_reruns: ["T003"]`; a second
    `timeout-rerun T003` exits 1 with `already committed and rerun once` and the manifest bytes
    are unchanged; `timeout-rerun T004` then exits 0 (per task); `timeout-rerun bad` and no
    argument exit non-zero with usage;
  - `clear-attempts` keeps `timeout_reruns`; a new `start` drops it;
  - a manifest with `timeout_reruns: "T003"`, `["T003", "T003"]` or `["x"]` is invalid (an
    action that validates, e.g. `gate`, fails as for a wrong limit field).
- All `test_limit_relaunch_record_*` and `run-manifest` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k timeout_rerun_manifest` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_record` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- `workflow.py`: `run-manifest task` (read only; exit 1 silently without a record) and
  `timeout-rerun ID` (usage error unless `task_id_valid`; a repeat fails `session timeout: ID was
  already committed and rerun once in this run` with the manifest bytes unchanged; else one atomic
  append). `timeout_reruns_valid` (list, ≤ 200, unique valid IDs) joins the manifest validity
  check, named in the comment above `LIMIT_FIELDS`. `start` writes a fresh dict (verified by test);
  `clear-attempts` keeps the field, commented there and at its only caller, `finish()` in
  `scripts/ai-pipeline`. docs/workflow.md describes both actions and the field. Flow unchanged.
- Tests: `test_timeout_rerun_manifest_{task_reads_the_recorded_task,once_per_task,
  kept_on_resume_dropped_on_start,wrong_shape_is_invalid}`.
- Validation: `-k timeout_rerun_manifest` Ran 4 OK; `-k limit_relaunch_record` Ran 7 OK
  (unchanged); `-k run_manifest` Ran 4 OK; `.ai/bin/ai-check` PASS (978 tests, 618.6 s; finished in
  the background past the 600 s tool timeout).


## T025 — ai-recover commits a timed-out IN_PROGRESS task's validated work once and reruns (FL-28 part 2, recovery)
Status: DONE
Dependencies: T024
Model: opus

### Goal
A pipeline stopped by a session timeout on an IN_PROGRESS task with uncommitted work resumes on
its own: the host validates and commits the partial work and reruns, without a Claude decision,
the first time for that task in the run. A second timeout of the same task escalates.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-28 part 2" (chart and bullet "ai-recover"). File
  `scripts/ai-recover`.
- Move the body of the `commit_and_rerun)` case (~322–344) unchanged into `commit_validated()`.
  WHY and HUMAN become `$1` and `$2`; it keeps the `ai_observe recovering … checks` step. The
  case becomes `commit_and_rerun) commit_validated "$why" "$human" ;;`. Behaviour is identical:
  the existing `test_recovery_*` tests are the proof.
- New rule right after the second `record_stop_leftovers` call (~293), before the `recover.md`
  check (~294). All of these must hold: `[[ $stage == implementation ]]`; the reason matches
  `'Claude exited 124 ('*` or `'Claude exited 137 ('*`; `task=$(ai_helper run-manifest task
  2>/dev/null)`; `[[ "$(ai_helper tasks status "$task" 2>/dev/null)" == IN_PROGRESS ]]`; and
  `git status --porcelain --untracked-files=all` is non-empty. Then:
  - `why_once=$(ai_helper run-manifest timeout-rerun "$task" 2>&1)` fails → `escalate "the $task
    session timed out again after one commit-and-rerun in this run." 'split the task or raise
    --session-timeout, then rerun ai-pipeline.'`;
  - else `ai_notify "🔧 Recovering ($attempt/$max): $branch: the $task session timed out;
    committing its validated partial work once and rerunning."`, then `commit_validated "the $task
    session timed out; its partial work passed the full gate" 'fix or discard the uncommitted
    work, then rerun ai-pipeline.'`, then `resume "the $task session timed out; its validated
    partial work was committed."`.
  Comment the rule: why it is deterministic (no decision session), why once per task (the record
  is spent before the gate runs, so a failing gate also uses it), and that the attempt budget was
  already checked above.
- The match is on ai-run's existing message (`claude_session`, `ai_die "Claude exited $code
  (timeout/interruption/error)…"`); do not change that message. Check that no hard-rule pattern
  matches it.
- The usage text (~5–21) gets one sentence. Docs and the flow chart are T026's (say so in the
  result).

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_timeout_rerun_recover_*` in tests/test_workflow.py, with pipeline fixtures as
  `test_recovery_never_passes_a_changed_gate_or_hard_stop` and `AI_AUTO_RECOVER=1`. Add a mock
  claude mode (e.g. `timeout-once`, using a counter file in `MOCK_STATE_DIR`). On its first call
  it runs `.ai/bin/ai-task set T001 IN_PROGRESS`, writes a tracked-path file such as
  `partial.txt`, and sleeps past `--session-timeout 1`. Later calls behave as the normal mock
  (complete T001):
  - first timeout: the pipeline resumes and completes; `recovery_calls()` is empty (no decision
    session); git log has a `chore(ai): recovery checkpoint (validated leftover work)` commit
    containing `partial.txt`, before T001's DONE checkpoint; the notifications contain
    `the T001 session timed out; committing its validated partial work once` and no `⛔`; the
    manifest has `timeout_reruns` `["T001"]`;
  - second timeout of the same task (a mode that always times out after marking IN_PROGRESS, with
    `AI_RECOVER_MAX=2`): exactly one `⛔` containing `timed out again after one commit-and-rerun`;
    exactly one recovery checkpoint commit; `recovery_calls()` empty.
- All `test_recovery_*`, `test_limit_relaunch_*` and `test_usage_limit_*` tests pass unchanged.
- Mutation evidence in the result: without the `timeout-rerun` call the second case loops until
  the attempt budget and fails the test.

### Validation
Targeted: `python3 -m unittest discover -s tests -k timeout_rerun` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- `scripts/ai-recover`: the `commit_and_rerun)` body moved unchanged into `commit_validated WHY
  HUMAN` (`$why`/`$human` → `$1`/`$2`, keeps `ai_observe recovering … checks`); the case calls it.
  New rule after the second `record_stop_leftovers`, before the `recover.md` check, with the exact
  predicate from the notes (stage implementation, reason `Claude exited 124 (`/`137 (`,
  `run-manifest task`, `tasks status` IN_PROGRESS, dirty checkout); `timeout-rerun` refusal → ⛔
  `the T session timed out again after one commit-and-rerun in this run.`; else 🔧 line,
  `commit_validated`, `resume`. Commented (deterministic, once per task spent before the gate,
  budget checked above). Usage text: one sentence. ai-run's message unchanged; no hard-rule
  pattern matches `Claude exited 124 (timeout/interruption/error). Preserve partial work; see
  .ai/local/claude-XXXXXXXX.json …` (only a random mktemp name containing e.g. `gate` could match).
- Tests: mock claude modes `timeout-once`/`timeout-always` (counter `timeout-session-calls` in
  `MOCK_STATE_DIR`; `ai-task set T001 IN_PROGRESS`, `partial.txt`, sleep past `--session-timeout
  1`); `test_timeout_rerun_recover_commits_the_partial_work_once_and_finishes`,
  `test_timeout_rerun_recover_second_timeout_of_the_task_escalates`.
- Mutation: with `timeout-rerun` replaced by `true`, the second test fails: two 🔧 recoveries,
  then ⛔ `already tried 2 time(s)` (loops to the attempt budget).
- Evidence: `-k timeout_rerun` 6 OK; `-k recovery` 72 OK; `.ai/bin/ai-check` PASS (980 tests,
  661.3 s, finished in the background past the 600 s tool timeout), which includes all
  `test_limit_relaunch_*` and `test_usage_limit_*` (a separate targeted run of those two groups
  was stopped by the tool's time limit, so the gate is their evidence).
- README, docs/workflow.md, the flow chart and the vault hub Log line are T026's (vault not
  accessible from this session).

## T026 — Timeout rerun: the cases that stay as today, docs and flow chart (FL-28 part 2, contract)
Status: DONE
Dependencies: T025
Model: opus

### Goal
The timeout rule fires only in its exact case. Every neighbouring case keeps today's behaviour,
pinned by tests. The docs and the flow chart describe both FL-28 changes.

### Implementation notes
- Tests only, plus docs. If a case fails, fix the predicate in `scripts/ai-recover` narrowly and
  say so in the result.
- Docs: README "Recovery" (the list of actions, ~443) gets one bullet for the host's
  timeout rule. docs/workflow.md "Recovery contract" (~749) gets a paragraph "Session timeout on
  an IN_PROGRESS task": the predicate, once per task per run (kept across resumes, dropped by a
  human start), the gate requirement, the ⛔ wording. "Interruption, limits, and recovery" gets one
  sentence.
- Flow chart (vault `agents-flow.md`, "When something goes wrong"): before the Claude decision
  node, add "session timeout, task IN_PROGRESS, dirty → gate passes → recovery checkpoint → rerun
  (once per task), else ⛔". Update the `updated:` date and add a hub Log line. Then set the handoff's
  "## Flow chart" line to "Flow chart updated (…)".

### Likely affected modules
tests/test_workflow.py, scripts/ai-recover (only if a case fails), README.md, docs/workflow.md,
vault agents-flow.md, .ai/handoff.md

### Acceptance criteria
- Tests named `test_timeout_rerun_unchanged_*` in tests/test_workflow.py (fixtures as T025's):
  - the gate fails on the partial work (the fixture `.ai/validate` fails while `partial.txt`
    exists) → one ⛔ containing `fails validation`, no recovery checkpoint commit, `partial.txt`
    still uncommitted on disk, `timeout_reruns` `["T001"]` (spent);
  - the session timed out before marking the task (mock `timeout`: T001 still TODO) → the
    Claude decision session runs (`recovery_calls()` has one entry) as today;
  - a non-timeout stop on an IN_PROGRESS task with a dirty tree (e.g. `Claude exited 1 (`) → the
    decision session runs as today;
  - `AI_AUTO_RECOVER=0` with the timeout case → ⛔ `auto-recovery is off`, nothing committed;
  - the attempt budget spent (`AI_RECOVER_MAX=0`) → ⛔ `already tried 0 time(s)`, nothing
    committed;
  - a timeout whose only leftovers are the bookkeeping files (clean after the leftovers commit)
    → the decision session runs, no `timeout_reruns` entry.
- `-k Docs` passes (README and docs agree with the code).

### Validation
Targeted: `python3 -m unittest discover -s tests -k timeout_rerun` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- Tests `test_timeout_rerun_unchanged_{gate_fails_on_the_partial_work,task_not_marked_in_progress,
  non_timeout_stop,auto_recovery_off,attempt_budget_spent,only_bookkeeping_left}` (new mock modes
  `error-in-progress`: IN_PROGRESS + `partial.txt`, exit 1; `timeout-committed`: IN_PROGRESS
  committed, nothing else left, sleeps past the timeout). `auto_recovery_off` runs the pipeline
  with `AI_AUTO_RECOVER=0`, then `ai-recover` as the watchdog would, with ai-run's exact reason:
  the manifest's setting gives ⛔ `auto-recovery is off`. All cases kept today's behaviour; the
  predicate is unchanged.
- One narrow fix in `scripts/ai-recover`: the rule's WHY was `the T session timed out; its
  partial work passed the full gate`, which also prefixes commit_validated's escalations, so the
  failing-gate ⛔ read "…passed the full gate; but the leftover work fails validation". It is now
  `the T session timed out with uncommitted partial work` (also the recovery commit's `Recovery:`
  line). The gate-fail test asserts the old wording is gone (it failed before the fix).
- Docs: README "Recovery" item 2 (one paragraph), docs/workflow.md "Session timeout on an
  IN_PROGRESS task" in the recovery contract and one sentence in "Interruption, limits, and
  recovery". Vault `agents-flow.md` "When something goes wrong": timeout decision node before the
  Claude decision, a dated bullet, `updated: 2026-10-19`; hub Log line added. Handoff "## Flow
  chart" line updated.
- Evidence: `-k timeout_rerun` 12 OK; `-k Docs` 3 OK; `-k flow_this_repo` 1 OK; `.ai/bin/ai-check`
  PASS (986 tests, 630.2 s, finished in the background past the 600 s tool timeout).


## T027 — The host restores a tracked script's recorded executable bit after a session (FL-29, runner)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
After an implementation session, every tracked file that git records as 100755 but whose
working-tree file lost its execute bit gets that bit back, so the post-session gate sees git's own
record.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-29", first bullet.
- `scripts/lib/workflow.py` new command `exec-bits` (no arguments): walk `git ls-files -s -z`
  (index modes) at the checkout root. For each `100755` entry not under `.ai/bin/` and not
  `.ai/validate` or `.ai/ci-setup` (gate files: never touched by the host here), `os.lstat` the
  path. If it is a regular file (`stat.S_ISREG`; symlinks and missing files skipped) with no
  `0o111` bit, `os.chmod(path, mode | ((mode & 0o444) >> 2))` and print the relative path. Exit 0;
  a git failure fails as other helpers do.
- `scripts/ai-run`: after the implementation session's `ai_guard_verify` and `ai_branch`
  (~815), run `ai_helper exec-bits`. When it prints paths, show `Restored the executable bit
  recorded in git: <paths>` on stdout. No notification, no commit (the session's commit or the
  tier-1 checkpoint takes the tree as is).
- docs/workflow.md (near ~149, where `chmod +x` is described): one sentence on the host restore.
  Flow unchanged (a host detail inside the task step); say so in the result.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Tests named `test_exec_bits_*` in tests/test_workflow.py:
  - helper units on a fixture repository: a committed 100755 script chmodded to 0644 is
    restored to 0755 and printed; a committed 0644 file stays 0644 and is not printed; a 100755
    entry that is now a symlink (to a 0644 file) is not followed (the target's mode is unchanged);
    a deleted 100755 file is skipped; an untracked 0644 file is untouched; a 100755 file under
    `.ai/bin/` chmodded to 0644 stays 0644; a staged `git add --chmod=+x` file with a 0644
    worktree is restored;
  - runner: a mock session that chmods a tracked 100755 script to 0644 and marks the task DONE
    → ai-run prints `Restored the executable bit`, the host gate passes, the task's checkpoint
    is accepted, the script's mode at HEAD is still 100755 (`git ls-tree HEAD -- <path>`), no
    commit of the run has a `mode change` for it (`git log --summary`), and the file is 0755.
- `test_script_modes_all_shebang_scripts_are_executable` and the existing `ai-run` tests pass.
- Mutation evidence in the result: without the `ai_helper exec-bits` call the runner test fails.

### Validation
Targeted: `python3 -m unittest discover -s tests -k exec_bits` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k script_modes` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
BLOCKED: implementation complete, but the full gate `.ai/bin/ai-check` exceeded the 600000 ms
foreground timeout in this session, so a green gate is not established.
Done: `exec-bits` helper (scripts/lib/workflow.py), `ai_helper exec-bits` call plus the
`Restored the executable bit recorded in git: <paths>` line in scripts/ai-run after `ai_branch`,
one sentence in docs/workflow.md, 4 `test_exec_bits_*` tests plus a `chmod-tracked` mock mode.
Evidence: `-k exec_bits` Ran 4 OK; `-k script_modes` Ran 1 OK. Mutation: with the helper call
replaced by `true`, `test_exec_bits_runner_restores_the_bit_a_session_lost` fails.
Flow unchanged (a host detail inside the task step).
Blocker: run `.ai/bin/ai-check` (longer timeout) to confirm; then set DONE.

Mission control 2026-10-19: full `.ai/bin/ai-check` on c797cd3 (this task's work included), run with no tool timeout: Ran 1001 tests in 637.5s, OK, exit 0. The block was the session's 600 s tool limit (FL-32), not a failure; set DONE on that evidence.

## T028 — Prompts: `chmod +x` is the only form and also repairs a tracked script (FL-29, templates)
Status: DONE
Dependencies: T027
Model: haiku

### Goal
A runner or triage session that needs an executable bit uses the one allowed command, also for
a tracked script whose bit was lost, and never tries a numeric mode.

### Implementation notes
- `templates/.ai/prompts/runner.md` (~58–59) and `templates/.ai/prompts/triage.md` (~64): replace
  the bullet with: "A script must be executable: run `chmod +x <path>` on a file inside this
  checkout, then `git add -- <path>`. `chmod +x` is the only chmod form allowed (never numeric
  modes such as `chmod 755`, never paths outside the checkout). It also repairs a tracked script
  that lost its executable bit (`git diff` shows `old mode 100755` / `new mode 100644`); the
  runner restores such a bit after the session too."
- README (~179–181): add "(numeric modes such as `chmod 755` are denied)" and one clause on the
  host restore (T027).
- Do not edit `.ai/prompts/` (gate copy): the installed prompts change with the human's upgrade
  (handoff).
- Flow unchanged; say so in the result.

### Likely affected modules
templates/.ai/prompts/runner.md, templates/.ai/prompts/triage.md, README.md, tests/test_workflow.py

### Acceptance criteria
- Test `test_exec_bits_prompts_name_the_only_form` in tests/test_workflow.py: both template
  prompts contain `chmod +x <path>`, `chmod 755` and `old mode 100755`; README contains
  `chmod 755`.
- `-k Docs` and every existing prompt test (`-k prompt`) pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k exec_bits_prompts` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k prompt` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE: `templates/.ai/prompts/runner.md` and `triage.md` bullet now reads "A script must be
executable: run `chmod +x <path>` on a file inside this checkout ...", names `chmod +x` as the
only chmod form (numeric modes such as `chmod 755` denied) and says it repairs a tracked script
whose bit was lost (`old mode 100755` / `new mode 100644`; the runner restores it after the
session). README (`Bash(chmod +x *)` paragraph) gets the numeric-mode denial and the host restore.
Test: `test_exec_bits_prompts_name_the_only_form` (both prompts and README).
Evidence: `-k exec_bits_prompts` Ran 1 OK; `-k prompt` Ran 17 OK; `-k Docs` Ran 3 OK; full
`.ai/bin/ai-check` Ran 1002 tests in 634.3 s, OK, exit 0 (run in the background after the 600 s
foreground limit; output read from the completed run).
Mutation: not run. Flow unchanged (wording inside prompts and README). `.ai/prompts/` not edited.


## T029 — Plan dispositions: regression for the family-budget row and the restart path; prompt shows the table (FL-30)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
The exact cell that stopped family-budget (`P1 (MAJOR) dev proxy vs Origin check`) is accepted
both by the check and by the restarted pipeline's recording of an interrupted revision, and the
revision prompt shows the whole table shape.

### Implementation notes
- Verified at 1423b60: `FINDING_CELL` (`scripts/lib/workflow.py` ~1017) already accepts
  this cell; `test_finding_cell_*` (~11279–11345) covers similar ones. This task adds the incident
  regression and the restart path. A parser change only if a test proves it necessary; then the
  narrowest fix, named in the result.
- Restart path: an interrupted plan revision whose section is complete but uncommitted is
  recorded without a session (`ai-run --revise-plan`: "a complete but uncommitted section is
  recorded without a session"; ai-pipeline `complete_plan_stage` ~316). Find the existing test
  of that path (grep `without a session` / `revise_plan` in tests) and add a variant whose rows
  use decorated cells.
- `templates/.ai/prompts/plan-revision.md` (~29–36): after the sentence on the first cell, show
  the table header as the host writes it (copy it from `plan_section_opened`, do not invent
  column names) and three example rows: accepted with a task, rejected with evidence and an empty
  Task cell, needs-human with a question and an empty Task cell. Keep "the finding ID alone in
  the first cell" and the existing `| P1 | accepted |` text (asserted by
  `test_finding_cell_prompts_show_the_row`). Never put a pipe inside a cell of the examples.
- Flow unchanged; say so in the result.

### Likely affected modules
tests/test_workflow.py, templates/.ai/prompts/plan-revision.md, scripts/lib/workflow.py (only if a test proves a gap)

### Acceptance criteria
- Tests in tests/test_workflow.py:
  - `test_finding_cell_plan_dispositions_incident_row`: the section with
    `| P1 (MAJOR) dev proxy vs Origin check | accepted | real | T002 |` and a P2 row passes
    `plan-dispositions-check` (`accepted=1 rejected=1 needs_human=0`), also with `--fresh`;
  - `test_finding_cell_plan_revision_restart_records_decorated_rows`: an interrupted revision
    (stage open, complete section with decorated cells such as `P1 (MAJOR) title` and
    `P2: title`, uncommitted) is recorded by the restart without a Claude session (the mock
    records no call), in one `chore(ai): record plan revision` commit;
  - `test_finding_cell_prompts_show_the_table`: `plan-revision.md` contains the host's header
    line and one example row each for `accepted`, `rejected` and `needs-human`.
- All `test_finding_cell_*`, `-k plan_revision` and `-k plan_dispositions` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k finding_cell` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k plan_revision` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
BLOCKED on the gate timeout, not on a failure. Implementation is complete and the targeted checks pass:
`-k finding_cell` Ran 10 OK, `-k plan_revision` Ran 15 OK, `-k plan_dispositions` Ran 12 OK.
`.ai/bin/ai-check` run in the foreground with timeout 600000 ms did not finish within 600 s (same
condition as T027). No parser change was needed: `FINDING_CELL` already accepts the incident cell.
Added the three tests in tests/test_workflow.py and the table header plus three example rows in
`templates/.ai/prompts/plan-revision.md`. Flow unchanged. Needs a full gate run with a longer limit.

Mission control 2026-10-19: full `.ai/bin/ai-check` on c797cd3 (this task's work included), run with no tool timeout: Ran 1001 tests in 637.5s, OK, exit 0. The block was the session's 600 s tool limit (FL-32), not a failure; set DONE on that evidence.

## T030 — Self-check prints progress, a stop summary and the tests over the per-test budget (FL-31, runner output)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
A self-check that is cut off shows how far it got and what had failed, and every run lists the
tests over the per-test budget beside the slowest 15.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-31", bullets "Progress" and "Budget". File
  `tests/run_parallel.py` (stdlib only). `.ai/validate` is unchanged.
- Progress: `Dispatcher` gets an optional `on_result` callback, called in `work()` under the lock
  right after `self.results[number] = result`. `main` passes one that prints `Progress: d/N
  batches, t tests, f failing, E s` (`flush=True`; d = results so far, t = sum of `ran`, f =
  batches not OK by the same rule as the final report, E = seconds since start).
- Stop summary: `main` wraps `dispatcher.run()`. On `SystemExit` (from `terminated`) or
  `KeyboardInterrupt` it prints, before re-raising, `run_parallel: stopped after E s: d/N batches
  finished (t tests); running: <batch numbers or none>; failing: <batch numbers or none>`, plus
  the slowest finished tests (the same `timing_report` lines when timings exist). Then it lets
  the exception propagate (exit code unchanged). The existing `finally` (tmpdir removal) still
  runs.
- Budget: `SLOW_BUDGET` = `AI_TEST_BUDGET` (a float > 0; invalid → `sys.exit` with a message in
  the style of `worker_count`) else `30 * TIMEOUT_SCALE` (import from `timeouts.py`, same
  directory). `timing_report` gains the budget: after the slowest list, `Over the per-test budget
  of B s: n tests` and each name with its seconds (slowest first), only when n > 0. The exit code
  never depends on it.
- README (the self-check / `run_parallel` description; grep `run_parallel`): progress and stop
  lines, the budget, `AI_TEST_BUDGET`, and the rule: "a new or changed test over the budget is
  made cheaper, or its task result says why".
- Flow unchanged; say so in the result.

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py (ParallelRunnerTest), README.md

### Acceptance criteria
- Tests named `test_parallel_runner_progress_*` in tests/test_workflow.py (`ParallelRunnerTest`
  fixtures, a small `--start-dir` suite as the existing tests use):
  - a run of 3 batches prints 3 `Progress:` lines, the last `3/3 batches`, before `Ran N tests`;
    the final report lines are unchanged (the existing assertions still pass);
  - SIGTERM to a run whose suite has one fast test and one that sleeps (bounded by
    `tests/timeouts.py`) prints `run_parallel: stopped after`, `1/2 batches finished` (or the
    counts the fixture yields) and `running:` naming the sleeping batch, then exits non-zero;
  - `AI_TEST_BUDGET=0.5` with a test sleeping 1 s prints `Over the per-test budget of 0.5 s: 1
    tests` and its name, exit 0 when all pass; `AI_TEST_BUDGET=x` exits non-zero with a message;
    with the default budget and fast tests no `Over the per-test budget` line appears.
- All existing `test_parallel_runner_*` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k parallel_runner` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Implemented: `Dispatcher(on_result=)` and `Progress:` lines, `run_parallel: stopped after …` summary
(state captured at the start of `stop()`, so batches killed by the stop are not counted as finished),
`AI_TEST_BUDGET` / `SLOW_BUDGET` default `30 * TIMEOUT_SCALE` and the `Over the per-test budget` list,
README paragraph. `run_parallel.py` now puts its own directory on `sys.path` before importing
`timeouts` (the runpy wrapper in the sigint test does not). Five `test_parallel_runner_progress_*`
tests added. Flow unchanged.
Evidence: `python3 -m unittest discover -s tests -k parallel_runner` → `Ran 39 tests`, OK.
BLOCKED: `.ai/bin/ai-check` in the foreground with timeout 600000 ms did not finish within 600 s
(moved to background), so the gate result is unknown, same as the earlier tasks blocked on the gate timeout.

Mission control 2026-10-19: full `.ai/bin/ai-check` on c797cd3 (this task's work included), run with no tool timeout: Ran 1001 tests in 637.5s, OK, exit 0. The block was the session's 600 s tool limit (FL-32), not a failure; set DONE on that evidence.

## T031 — Shared fixture template for `ready()` (FL-31, fixtures)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
`ToolkitTest.ready()` copies a per-process template of the bootstrapped project instead of
running `setup-project` and the bootstrap commit for every test, with an identical result and
independent copies.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-31", bullet "Fixture template". File
  `tests/test_workflow.py` (`setUp` ~737, `ready` ~1615).
- Template: a module-level lazy builder that creates `tempfile.mkdtemp(prefix='ai-ready-template-')`
  (removed with `atexit`) and a project path whose name matches `'project with spaces'`. It runs
  `git init -b main` and the same three `git config` calls as `setUp`, then `setup-project`, the
  `bootstrap` commit and `git switch -c feature/test`, with an env built like `setUp`'s
  (`git_fixture_env()`, mock PATH not needed for setup; check what `setup-project` reads from the
  environment and keep it equal). The template is built per process; batches are separate
  processes.
- `ready(queue=None, fresh=False)`: when not `fresh` and the project holds only `.git` from
  setUp's `git init` (no other entries) and `self.config` is empty, remove the project's `.git`,
  `shutil.copytree(template, self.project, symlinks=True, dirs_exist_ok=True)`, then continue
  as today (queue, validate, second commit). Otherwise run today's path. Tests that check setup
  behaviour itself, absolute paths or commit times pass `fresh=True`; find them by running the
  suite, and list each in the result.
- Guard: nothing may write `__pycache__` into the template's `.ai/bin` (tests import nothing from
  there; assert it).
- Measure: before the change, `python3 -m unittest discover -s tests -k finding_cell` and
  `-k plan_revision`; after, the same. Record both `Ran N tests in X s` lines in the result.
- Flow unchanged; say so in the result.

### Likely affected modules
tests/test_workflow.py

### Acceptance criteria
- Tests named `test_fixture_template_*` in tests/test_workflow.py:
  - equivalence: a `ready()` project and a `ready(fresh=True)` project in the same test have
    the same set of tracked and untracked paths outside `.git`, the same file bytes and modes,
    the same current branch, and the same `git log --format=%s` list;
  - independence: a test that writes a file into its `ready()` project and commits it, then
    builds a second `ready()` project (another base dir), finds the second one without that file
    or commit;
  - no `__pycache__` under the template's or any copy's `.ai/bin`.
- The full suite passes with the same discovered test IDs plus the new ones (record before and
  after counts from `ai-check`'s `collected`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k fixture_template` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k finding_cell` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Implemented in `tests/test_workflow.py`: `ready_template()` (lazy, per process, `ai-ready-template-` tempdir
removed by `atexit`, project dir `project with spaces`) and `ready(queue=None, fresh=False)`, which copies
the template (`copytree(symlinks=True)`, after removing setUp's `.git`) only when the project holds just
`.git` and the XDG config dir is empty; otherwise the old path runs. `setup-project` reads nothing from the
environment, so the template env is `git_fixture_env()`. It records the directory name and a wall-clock
stamp in `.ai/state.md`, so the equivalence test builds the fresh project in a `project with spaces`
directory and masks ISO timestamps (the first gate run failed on that; fixed). New tests:
`test_fixture_template_equivalence`, `_copies_are_independent`, `_has_no_bytecode`. No test needed
`fresh=True` (the full suite passes without it). Timings after: `-k finding_cell` Ran 10 tests in 8.766s;
`-k plan_revision` Ran 15 tests in 70.936s. Before-numbers were not taken (avoided stashing or checking
out the old file in a shared worktree), so no speed-up is claimed. Gate: 1001 collected (998 + 3 new),
OK, 633.5 s (finished in the background past the 600 s tool timeout). Flow unchanged.

## T032 — Fewer full `ai-pipeline` fixture runs per test (FL-31, slow tests)
Status: DONE
Dependencies: T030, T031
Model: sonnet

### Goal
Tests that run the full `ai-pipeline` more than once only to build a precondition stop doing so
where that precondition is already proven by another test, so the suite does less repeated
pipeline work with the same assertions.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-31", bullet "Pipeline runs". No profiling (denied); measure
  only with `python3 -m unittest discover -s tests -k <name>` (`Ran N tests in X s`) and the
  gate's slowest-15 and over-budget lists (T030).
- Audit by reading: `grep -n "'ai-pipeline'" tests/test_workflow.py` and the helpers that wrap it
  (e.g. `limit_relaunch_fixture`, `approve_run`, pipeline helpers). For each test with two or
  more pipeline runs, classify each run as asserted on or only a setup run. Do this for the
  slowest-15 first.
- Change a setup run only when (a) another named test already asserts that the pipeline
  produces exactly that state, and (b) the state can be built with existing helpers (helper
  calls, git commands, the same files) so that the later assertions see the same inputs. Never
  change what a test asserts, its name, or the run it is about. Shared host state (run manifest,
  review bindings) is keyed by the checkout path, so never copy a post-pipeline checkout between
  tests.
- Budget: at most about 5 conversions in this task. List every audited test in the result as
  converted (with the covering test), or kept (with the reason).
- "No safe candidate" is acceptable when the result shows the audit. The task is then DONE with
  the list and the timings, stated plainly.
- Flow unchanged; say so in the result.

### Likely affected modules
tests/test_workflow.py

### Acceptance criteria
- The result lists the audited tests, the conversions with their covering tests, and before and
  after `-k` timings for each converted test.
- Every converted test keeps all its assertions (the diff shows only setup lines changed) and
  passes. The discovered test IDs are unchanged by this task, collected equals executed, and
  the full suite passes.

### Validation
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
No safe candidate: 0 conversions, no test file changed (test IDs unchanged; flow unchanged).
Audit by reading, slowest-15 first (last gate: 969 tests, 618.5 s, 8 workers). The two slowest
(`test_session_budget_end_to_end_*`, 36.7 s and 34.2 s) run `ai-run` once, not `ai-pipeline`. All
other slowest-15 tests run `ai-pipeline` once (`test_extra_fix_round_*`, `test_observation_*`,
`test_convergence_*`, `test_pr_undraft_*`), so no setup run exists to drop. Kept, with reason:
- `test_fix_round_count_survives_human_restart`: both runs asserted (triage_calls 1 then 2).
- `test_pipeline_rerun_updates_existing_pr_without_new_review`: run 1 is the setup, but the rerun
  depends on the review binding and run manifest keyed by the checkout path, which only a real run
  writes (no helper builds them byte for byte).
- `test_pipeline_plan_review_gates_implementation`, `test_plan_review_is_bound_and_tracks_the_whole_tree`:
  every run is asserted (plan-call counts, stops).
- `test_recovery_is_bounded_per_run`, `test_queue_check_invalid_queue_stops_with_skip_plan_review`:
  the first run's stop state and recovery-attempt budget are what the second run asserts on.
- `test_triage_completion_*`, `test_fix_round_count_*`: the second run resumes a stopped stage,
  so the first run is the thing under test.
Before/after `-k` timings: not applicable, nothing converted.


## T033 — Docs, flow chart and handoff audit (batch 7)
Status: DONE
Dependencies: T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032
Model: haiku

### Goal
README, docs/workflow.md, the usage texts, the vault flow chart and the handoff match the code
of this batch.

### Implementation notes
- Check against the code: `ai-run --help` (session limit), `ai-recover --help` (timeout rule),
  README (session limits, Recovery, chmod, self-check budget and progress) and docs/workflow.md
  (session limits, Recovery contract, `chmod +x`). Wording fixes only. A behaviour mismatch is
  recorded in the handoff, not fixed here.
- Vault `agents-flow.md`: the session-limit note (T023) and the timeout-rerun node (T026) are
  present and match. Fix the wording if needed (update `updated:` then) and add one hub Log line.
- `.ai/handoff.md`: "What has been implemented", "Validation run", "## Flow chart" (one line
  starting `Flow chart updated`), and "Manual testing for the human" with `### Needs you` and
  `### Covered by automated tests` (each test group with its task).

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- `-k Docs` and `-k flow_this_repo` pass; the handoff names every new test group of T022–T032.
- The result lists every mismatch found and how it was fixed or recorded.

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
BLOCKED on the full gate, not on a found mismatch. Audit by reading (code is the source of truth):
- `ai-run` usage (session limit: base, plus twice the gate time, at most the base), `ai-recover`
  usage (timeout rule), README (session limits, Recovery, chmod paragraph, self-check progress and
  budget) and docs/workflow.md (outcome gate lines, gate allowance, `Session:` format, chmod, exec-bits):
  all match the code. No wording change was needed, so no file was edited for them.
- Vault `agents-flow.md` ("Gate allowance" bullet, timeout branch in "When something goes wrong")
  matches `ai-run` and `ai-recover`. Its `updated:` date stays as it was.
- handoff: "What has been implemented" lacked T027–T032 (added); "Validation run" lacked T027–T032
  (added); "Next action" was stale (rewritten); the Human todos line now names the T023, T026 and T033 log lines.
- Every test group named in the handoff exists (`test_gate_time_*`, `test_session_gate_allowance_*`,
  `test_timeout_rerun_*`, `test_exec_bits_*`, `test_finding_cell_*`, `test_parallel_runner_progress_*`,
  `test_fixture_template_*`).
- Targeted: `-k Docs` Ran 3 OK; `-k flow_this_repo` Ran 1 OK.
- Gate: `.ai/bin/ai-check` in the foreground with timeout 600000 ms did not finish within 600 s; the
  harness moved it to the background (task ID bkhdtjkke, output in the session's tasks folder). It then
  finished: `Ran 1002 tests in 634.9s … OK`, but the stamp exited 1 with `Validation modified project
  content`. Cause: this session edited the record files and committed `1e84615` while the gate was
  running, so the fingerprint at the end differed from the start (`scripts/lib/workflow.py` `stamp`).
  No gate pass is established on any tree. A rerun on a clean tree with no edits during the run is needed. Human or mission control: run it without
  a tool limit (last full gate on the branch: PASS, 1002 tests, parent 01f8197, which includes T027–T030).
- Flow: unchanged in this task (the audit found no flow change).
Mission control 2026-10-19: full `.ai/bin/ai-check` on d2614df without a tool timeout: Ran 1002 tests in 638.7s, OK, exit 0. Blocked only by the session's 600 s tool limit (FL-32); set DONE on that evidence.

## T034 — exec-bits never follows a symlinked parent directory (review M2)
Status: DONE
Dependencies: T027
Model: opus

### Goal
`workflow.py exec-bits` changes the mode only of a regular file inside the checkout, reached
without following any symlink component, so a session that replaces a tracked directory by a
symlink cannot make the host chmod a file outside the checkout.

### Implementation notes
- Today `exec_bits()` (`scripts/lib/workflow.py`, about line 4460) does `os.lstat(root / name)`
  and `os.chmod(root / name, …)`: `lstat` refuses only a symlink leaf; parent symlinks are
  followed by both calls.
- Open the checkout root once, then walk each path component with
  `os.open(part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=…)`; open the leaf with
  `O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, `fstat` it, skip it unless `S_ISREG` and no
  execute bit, then `os.fchmod(fd, …)`. Close every descriptor (see `read_record`, `checkout_fds`
  and `remove_tree` for the existing pinned-descriptor style). Any component that is a symlink,
  missing or not a directory skips the entry silently, as today.
- Keep the gate-file exclusions (`.ai/bin/`, `.ai/validate`, `.ai/ci-setup`) and the output
  format (restored relative paths, one per line).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- New regression `test_exec_bits_skips_a_symlinked_parent_directory`: index records
  `scripts/tool.sh` as 100755, the working-tree `scripts` is replaced by a symlink to a directory
  outside the checkout holding a non-executable `tool.sh`; after `exec-bits` the external file's
  mode is unchanged and nothing is printed for it.
- The existing `test_exec_bits_*` tests still pass (leaf symlink, deleted, untracked, gate files,
  staged bit, runner restore).

### Validation
Targeted: `python3 -m unittest discover -s tests -k exec_bits` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE (81ca76a). `exec_bits()` pins the checkout root once; new `exec_bit_restored()` opens the
parent with `open_dir` (every component `O_NOFOLLOW`), the leaf with
`O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, `fstat`s it and `fchmod`s only a regular file
with no execute bit; any unsafe component skips silently. Gate exclusions and output unchanged.
`test_exec_bits_skips_a_symlinked_parent_directory` added; mutation (parent opened following
symlinks) fails it. `-k exec_bits` Ran 6 tests OK; `-k Docs` 3 OK; `.ai/bin/ai-check` PASS
(1003 tests, 654.9 s; it outgrew the 600 s tool timeout and finished in the background with the
tree unchanged, exit 0). docs/workflow.md notes the no-follow rule. Flow unchanged.

## T035 — Restore executable bits before a timed-out session stops the run (review M3)
Status: DONE
Dependencies: T027, T025
Model: opus

### Goal
A timed-out (124/137) or otherwise failed implementation session still gets its tracked
executables' bits restored before the runner stops, so `ai-recover`'s timeout commit-and-rerun
does not fail the gate only because a script lost its bit.

### Implementation notes
- Today `scripts/ai-run` calls `ai_helper exec-bits` (about line 842) only after
  `claude_session` returns; `claude_session` calls `ai_die "Claude exited $code …"` (about line
  360) for any non-zero exit, so the repair never runs on a timeout.
- Run the repair for implementation sessions only (`track_attempt=yes`) inside `claude_session`
  after `ai_guard_verify` and the branch check (`ai_branch`), before the non-zero-exit `ai_die`;
  keep it out of triage, plan revision and `--plan` sessions. Avoid running it twice on success
  (move it rather than duplicate it). A repair failure must not hide the original exit code in
  the stop message.
- Alternative if cleaner: also call `exec-bits` in `ai-recover`'s `commit_validated` before the
  gate. Pick one place and say why in the result.

### Likely affected modules
scripts/ai-run, possibly scripts/ai-recover, tests/test_workflow.py

### Acceptance criteria
- New regression `test_exec_bits_restored_after_a_session_timeout`: a mock session on an
  IN_PROGRESS task drops the bit of a tracked executable the gate requires and exits 124; the
  runner output shows `Restored the executable bit recorded in git: …` and the file is executable
  again after the stop.
- New regression `test_timeout_rerun_recover_after_lost_exec_bit` (or an extension of an existing
  `test_timeout_rerun_recover_*` test): `ai-recover` then commits the validated partial work and
  resumes, as for a timeout without the lost bit.
- Existing `test_exec_bits_*`, `test_timeout_rerun_*` and `test_session_gate_allowance_*` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k exec_bits` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k timeout_rerun` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE (implementation 440feb4). Placement: inside `claude_session` (implementation sessions only,
`track_attempt=yes`), after `ai_guard_verify`, the review-digest check and the limit-pause retry,
then `ai_branch` and `exec-bits`, before the non-zero-exit `ai_die`. Moved, not duplicated: the
post-session `ai_branch`/`exec-bits` block in the task loop is gone. Chosen over `ai-recover`'s
`commit_validated` because the runner is where R3 restores bits for every implementation session
(also a plain error exit or a human resuming after a stop), and recovery stays a gate-and-commit
step. A repair failure on a non-zero exit stops with `Claude exited N (…); also cannot restore
recorded executable bits.`, keeping the `Claude exited 124 (` prefix `ai-recover` matches.
Tests: `test_exec_bits_restored_after_a_session_timeout`, `test_timeout_rerun_recover_after_lost_exec_bit`
(gate `test -x scripts/tool.sh`; mock `timeout-once` honours `MOCK_CHMOD_PATH`). Mutation (repair
only when `code == 0`) fails both. `-k exec_bits -k timeout_rerun` 20 OK; `-k Docs -k
session_gate_allowance -k exec_bits` 15 OK; `.ai/bin/ai-check` PASS (1005 tests, 668.5 s, exit 0,
finished in the background past the 600 s tool timeout, tree unchanged during the run). README and
docs/workflow.md say the repair also runs on a timed-out session. Flow chart: T036.

## T036 — State, handoff and flow chart after the review fixes (review N3, N4)
Status: DONE
Dependencies: T034, T035
Model: haiku

### Goal
`.ai/handoff.md` and the vault flow chart match the delivered work, including the
executable-bit repair step and its placement after T035.

### Implementation notes
- Handoff: "Next action" and the T033 lines still say T033 is BLOCKED and ask for a gate rerun;
  rewrite them from the queue (T033 DONE on mission control's gate pass) and add T034–T036 to
  "What has been implemented", "Validation run" and "Covered by automated tests" (with the new
  test names in backticks). `.ai/state.md` counts are runner-managed; do not hand-edit them, but
  check they are current after the runner's checkpoint and record a mismatch in the result.
- Vault `agents-flow.md` "Inside one task": add the host step "restore executable bits git
  records (exec-bits)" between the session and the host checks, and show that it also runs on a
  timed-out or failed session (T035's placement). Update `updated:`, keep the handoff's
  `Flow chart updated` line current, and append one dated hub Log line (never tick checkboxes).

### Likely affected modules
.ai/handoff.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- The handoff no longer calls T033 BLOCKED and names `test_exec_bits_skips_a_symlinked_parent_directory`
  and `test_exec_bits_restored_after_a_session_timeout`.
- The flow chart shows the exec-bits step in the task flow, including the timeout path.
- `-k Docs` and `-k flow_this_repo` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE. Gate PASS on the unchanged tree at 31e7f7c: `.ai/bin/ai-check` `Ran 1005 tests in 667.7s … OK`, exit 0 (background task bjq3hh48h, past the 600 s tool limit). The earlier run (bab5c28ty) was an exit 1 caused by this session's own edits during the run; see below.
- Done: handoff "Next action" and the flow-chart line rewritten (T033 DONE; T034–T036 named, with `test_exec_bits_skips_a_symlinked_parent_directory` and `test_exec_bits_restored_after_a_session_timeout` under "Covered by automated tests"). Vault `agents-flow.md` "Inside one task" shows the exec-bits step between the session and the host checks, with the timeout/error/signal path; plus the "Executable bits" bullet and the timeout bullet. Hub Log line added. No code changed.
- Targeted: `python3 -m unittest discover -s tests -k Docs` → Ran 3 tests, OK; `-k flow_this_repo` → Ran 1 test, OK.
- Gate: the foreground `.ai/bin/ai-check` hit the 600000 ms tool limit and kept running in the background (task bab5c28ty). It finished with `Ran 1005 tests … OK` (668 s, 0 failing), then exit 1 `Error: Validation modified project content`. Cause: this session's own record edits and the T036 record commit b7fa6f0 were made during the run, which changes the fingerprint (the same cause as T033's FAIL). No clean PASS yet; a rerun on an unchanged tree is needed (FL-32).
- `.ai/state.md` counts are runner-managed and were not edited.

## T037 — Prompts: run the full gate in the background and wait; never block on an unknown gate result (FL-32, templates)
Status: DONE
Dependencies: none
Model: opus

### Goal
A runner or triage session runs the ~11-minute gate so that it can read the result, does not
invalidate the run by editing meanwhile, and never marks finished work BLOCKED only because the
gate outlived a tool call.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-32 part 1".
- `templates/.ai/prompts/runner.md` (~49–52) and `templates/.ai/prompts/triage.md` (~55–58): the
  shared "How to work here" block must stay byte-identical in both
  (`test_tool_contract_section_is_shared_by_prompts`). Replace the gate bullet with, in substance:
  "Run the full gate as `.ai/bin/ai-check` with the Bash tool's `run_in_background: true`, then
  wait for its completion notice and read its result (exit status, `Ran N tests`, `OK` or
  `FAILED`). While it runs, make no edits and no commits (the gate hashes the tree before and after;
  a change fails it with `Validation modified project content`) and do not end the session. Never
  mark a task BLOCKED only because the gate outlived a tool call or its result could not be read:
  finish on the targeted checks, write `full gate result unknown in the session; left to the host
  gate` in the result, and mark the task DONE when everything else is met. The runner runs the full
  gate after the session and sets a DONE task whose gate fails back to IN_PROGRESS. Run a task's
  targeted test command as written, in the foreground." Remove "never run it in the background or
  poll it" and "If it still times out, mark the task BLOCKED".
- `templates/.ai/prompts/runner.md` intro (~14): keep "run its targeted checks and
  `.ai/bin/ai-check`" (no change needed unless it contradicts the bullet).
- `scripts/ai-run` RUNNER CONTRACT string (~842): after "or mark it BLOCKED with evidence." add
  "A gate run that outlives a tool call is not a blocker: the runner's full gate after the session
  decides."
- README setup step 4 (~198–200): replace the foreground sentence with the background rule (one
  or two sentences; keep "Record/fix any baseline failures rather than suppressing them.").
- Do not edit `.ai/prompts/` (gate copy).
- Flow chart (vault `agents-flow.md`, "Inside one task"): the `work` node's "run checks" becomes
  "run checks (full gate in the background, waited for)"; add one bullet "Session gate runs
  (FL-32, T037, 2026-10-19)": background + wait, no edits meanwhile, never BLOCKED for an unknown
  result, the host gate decides. Update `updated:`; append a dated hub Log line in `agents.md`
  (never tick checkboxes). If the vault edit is denied, record it in the result and in the handoff's
  "## Flow chart" section.

### Likely affected modules
templates/.ai/prompts/runner.md, templates/.ai/prompts/triage.md, scripts/ai-run, README.md,
tests/test_workflow.py, vault agents-flow.md and agents.md Log

### Acceptance criteria
- Test `test_gate_background_prompts_tell_the_session_to_wait` in tests/test_workflow.py: the
  shared block of both template prompts contains `run_in_background`, `Validation modified project
  content` and `left to the host gate`, and does not contain `never run it in the background` or
  `mark the task BLOCKED with the evidence instead`; README contains `run_in_background`;
  `scripts/ai-run` contains `is not a blocker`.
- `test_tool_contract_section_is_shared_by_prompts`, `-k prompt` and `-k Docs` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_background` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k prompt` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
Done (2026-10-19; partial work from the timed-out session in 1b2d620, reconciled and kept as is).
Shared gate bullet in `templates/.ai/prompts/runner.md` and `triage.md` now says background +
wait, no edits/commits meanwhile, never BLOCKED for an unknown gate result; RUNNER CONTRACT in
`scripts/ai-run` adds "A gate run that outlives a tool call is not a blocker"; README step 4 uses
the background rule. Test `test_gate_background_prompts_tell_the_session_to_wait`.
Evidence: `-k gate_background` Ran 1 OK; `-k prompt` Ran 18 OK; `-k Docs` Ran 3 OK; full gate
`.ai/bin/ai-check` run in the background and waited for: Ran 1006 tests in 644.5 s, OK, exit 0
(the earlier session's 2 failing subtests did not recur on this tree). Vault flow chart ("Inside
one task" `work` node, "Session gate runs" bullet) and hub Log line were already written by the
earlier session; checked present.

## T038 — Host record of a gate-only block retry and a safe reading of the validation stamp (FL-32, helpers)
Status: DONE
Dependencies: none
Model: opus

### Goal
The runner can claim the one gate-only block retry allowed per task per human-started run, and can
read what the session's own gate run left in `.ai/local/validation.json` without following a
symlink or blocking.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-32 part 2". File `scripts/lib/workflow.py`.
- `run_manifest` (`timeout-rerun` ~1559 and `timeout_reruns_valid` ~1329 are the model): action
  `gate-unblock TASK` (`task_id_valid` or usage error); optional field `gate_unblocks`, a list of
  unique valid IDs, at most 200, any other shape invalidates the manifest (extend the validity
  check ~1508 and the comment ~1299). A repeat fails `gate-only block: TASK was already retried
  once in this run` with the bytes unchanged; else one atomic append. `clear-attempts` keeps it
  (comment beside the `timeout_reruns` one ~1532); `start` writes a fresh dict (check).
- `stamp outcome` (in `stamp()` ~755): pin `.ai/local` with `local_dir_fd` and read
  `validation.json` with `read_record` (regular file only, no symlink, no FIFO block; a size bound
  such as 64 KiB). Print one line `WORD DIGEST`: WORD is `none` (missing, unsafe, unreadable or not
  a JSON object), `running` (`result` RUNNING), `pass` (`result` PASS), `changed` (`result` FAIL,
  `exit_code` 0 and `unchanged` false) or `fail` (anything else); DIGEST is the sha256 hex of the
  bytes read, or `-` when nothing was read. Always exit 0. `stamp verify`/`record`/`invalidate` are
  unchanged.
- No ai-run change here (T040). Flow unchanged in this task; say so in the result.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md (the run-manifest field list
and the stamp description, if they list actions)

### Acceptance criteria
- Tests named `test_gate_unblock_manifest_*` in tests/test_workflow.py (after `run-manifest start`
  as `approve_run` does):
  - `gate-unblock T001` exits 0 and the manifest holds `gate_unblocks: ["T001"]`; a second one
    exits 1 with `already retried once` and identical manifest bytes; `gate-unblock T002` exits 0;
    `gate-unblock bad` and no argument exit non-zero with usage;
  - `clear-attempts` keeps `gate_unblocks`; a new `start` drops it; a manifest with
    `gate_unblocks` `"T001"`, `["T001", "T001"]` or `["x"]` is invalid (an action that validates
    fails, as for `timeout_reruns`);
  - `stamp outcome`: no file → `none -`; after `stamp invalidate` → `running <64 hex>`; a written
    PASS record → `pass …`; FAIL with exit 0 and `unchanged` false → `changed …`; FAIL with exit 1 →
    `fail …`; garbage → `none …`; a symlink at `validation.json` to a PASS file outside → `none -`;
    a FIFO at `validation.json` → `none -` within a bound scaled by `tests/timeouts.py`; the digest
    equals `hashlib.sha256` of the file bytes.
- All `test_timeout_rerun_manifest_*` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_unblock_manifest` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k timeout_rerun_manifest` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
Done (2026-10-20). `scripts/lib/workflow.py`: `run-manifest gate-unblock ID` (usage error for a
bad/missing ID; a repeat fails `gate-only block: ID was already retried once in this run` with the
bytes unchanged; at most 200); `gate_unblocks` is validated with `timeout_reruns` through a shared
`task_list_valid`, kept by `clear-attempts`, dropped by `start`. `stamp outcome` (`stamp_outcome`)
pins `.ai/local` with `local_dir_fd`, reads `validation.json` with `read_record(..., raw=True)` (new
`raw` flag returns undecoded bytes so the digest is of the file bytes), a 64 KiB bound (larger →
`none -`), and prints `none|running|pass|changed|fail DIGEST`; always exits 0 (JSON errors and
deep nesting → `none DIGEST`). docs/workflow.md: run-manifest field list and the evidence paragraph.
Tests: `test_gate_unblock_manifest_once_per_task`, `_kept_on_resume_dropped_on_start`,
`_wrong_shape_is_invalid`, `_stamp_outcome_words`, `_stamp_outcome_never_follows_or_blocks`
(symlinked file, FIFO within `SHORT_TIMEOUT`, symlinked `.ai/local`).
Evidence: `-k gate_unblock_manifest` Ran 5 OK; `-k timeout_rerun_manifest` Ran 4 OK (unchanged);
`-k stamp -k manifest -k Docs` Ran 20 OK; full gate `.ai/bin/ai-check` in the background, waited
for, on f136412 with no edits meanwhile: Ran 1011 tests in 651.6 s, OK, exit 0.
No ai-run change (T040). Flow unchanged in this task.

## T039 — The host gate waits for a validation that is still running (FL-32, gate lock)
Status: DONE
Dependencies: none
Model: opus

### Goal
A session's background `ai-check` that is still running when the session ends cannot make the
host's post-session gate fail with `Validation is already running.`; the host waits for it, within
a bound.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-32 part 3".
- `scripts/ai-check` (~15–16): `wait=${AI_CHECK_LOCK_WAIT:-0}`, `[[ $wait =~ ^[0-9]{1,5}$ ]]` else
  `ai_die "Invalid AI_CHECK_LOCK_WAIT: $wait"`. `flock -n 8` first; when it fails and `wait > 0`,
  print `Waiting up to ${wait}s for a running validation to finish.` (stderr) and `flock -w
  "$wait" 8`; any failure → `ai_die 'Validation is already running.'` (same message). With 0 the
  behaviour is today's. The toolkit-repo branch (~4–12) takes no lock; leave it.
- `scripts/ai-run`: `checkpoint_done` (~702) and the final gate (~813) run
  `AI_CHECK_LOCK_WAIT=$lock_wait AI_CHECK_TIMEOUT=$remaining "$AI_BIN/ai-check"` with `lock_wait` =
  min(remaining, 900) (one small function; T040 reuses it for its retry gate). Comment why: a
  session may end with its own background gate still holding the lock (FL-32). `ai-recover` and
  `ai-pipeline` keep today's immediate refusal.
- README (the `ai-check` / configuration description; grep `AI_CHECK_TIMEOUT`) and docs/workflow.md
  (~1266, host gate timing) get one sentence each.
- Flow chart (vault `agents-flow.md` "Inside one task"): the `gate` node mentions "waits for a
  running gate (at most 15 min)". Update `updated:` and append a hub Log line (or record a denied
  vault edit as in T037).

### Likely affected modules
scripts/ai-check, scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md, vault
agents-flow.md and agents.md Log

### Acceptance criteria
- Tests named `test_gate_lock_wait_*` in tests/test_workflow.py, on a `ready()` fixture (its
  `.ai/validate` is fast):
  - a helper process holds `.ai/local/validation.lock` (`fcntl.flock`) and releases it after about
    1 s: `.ai/bin/ai-check` with `AI_CHECK_LOCK_WAIT=30` prints `Waiting up to 30s`, then passes and
    `stamp verify` succeeds; with `AI_CHECK_LOCK_WAIT` unset it exits non-zero with `Validation is
    already running.` at once (within a scaled bound) while the lock is held;
  - lock held past the wait (`AI_CHECK_LOCK_WAIT=1`, held for a scaled 10 s) → non-zero with
    `Validation is already running.` and returns within a scaled bound;
  - `AI_CHECK_LOCK_WAIT=x` → non-zero with `Invalid AI_CHECK_LOCK_WAIT`;
  - runner: a mock session that marks its task DONE and leaves a process holding the lock for about
    2 s (the mock starts a detached `python3 -c` holder; bound its life with `tests/timeouts.py`)
    → the host gate waits, passes and the task is checkpointed DONE.
- Existing `-k session_gate_allowance` and `-k gate_time` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_lock_wait` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k gate_time` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE. `scripts/ai-check`: `AI_CHECK_LOCK_WAIT` (`^[0-9]{1,5}$`, default 0, invalid → `Invalid
AI_CHECK_LOCK_WAIT: …`); `flock -n` first, then with a wait prints `Waiting up to Ns for a running
validation to finish.` and `flock -w N`; a timeout dies `Validation is already running.`.
`scripts/ai-run`: new `host_gate` (lock wait = min(remaining, 900), sets `gate_code`) used by
`checkpoint_done` and the final gate; T040 can reuse it. `ai-recover`/`ai-pipeline` unchanged.
Mock mode `lock-held` (detached `python3 -c` holder, `MOCK_LOCK_HOLD` scaled by `TIMEOUT_SCALE`,
pid recorded and killed in cleanup). Tests: `test_gate_lock_wait_passes_after_a_running_gate_ends`,
`_unset_refuses_at_once`, `_held_past_the_wait_refuses`, `_invalid_value`,
`_runner_waits_for_the_session_gate`. README + docs/workflow.md one paragraph each; vault flow chart
gate node, bullet, `updated:` and hub Log line.
Evidence: `-k gate_lock_wait` Ran 5 OK; `-k gate_time` Ran 4 OK; `-k session_gate_allowance` Ran 5
OK; `.ai/bin/ai-check` PASS (1016 tests, 654.5 s, background and waited, no edits meanwhile).

## T040 — Runner retries a gate-only block once per task (FL-32, recovery)
Status: DONE
Dependencies: T038, T039
Model: opus

### Goal
When a session marks its task BLOCKED although its own gate run showed no failing check, and the
host's full gate then passes on the same tree, the runner sets the task back to IN_PROGRESS and
gives it one more session, without a human, once per task per run.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-32 part 4" (chart and bullets). File `scripts/ai-run`.
- In the task loop, right before `claude_session` (~850): `stamp_before` = the DIGEST field of
  `ai_helper stamp outcome` (`-` on any helper failure).
- BLOCKED branch (~857–863): keep the dirty check and `task_outcome blocked` / `ai_log` /
  `runner_checkpoint TASK BLOCKED` as today, but send the ⚠ notification only when no retry
  happens. Then `gate_only_retry TASK` (new function) returns 0 when it set the task back:
  1. `read -r word digest < <(ai_helper stamp outcome)`; require `digest != stamp_before`,
     `digest != -` and `word` in `running pass changed`;
  2. `ai_helper run-manifest gate-unblock TASK 2>/dev/null` succeeds;
  3. the host gate as in `checkpoint_done` (T039's lock wait, `AI_CHECK_TIMEOUT=$remaining`,
     `ai_observe step checks TASK`, `ai_guard_verify`, `record_gate`); no remaining time → return 1;
     a failing gate → print `Gate-only block retry of TASK: the full gate failed; it stays
     BLOCKED.` and return 1 (never `ai_die`; the run continues as today);
  4. on a pass: `ai_helper tasks set TASK IN_PROGRESS`; `git add -- .ai/tasks.md .ai/state.md
     .ai/run-log.md .ai/handoff.md`; commit `chore(ai): retry TASK after a gate-only block`;
     `ai_guard_verify`; `ai_notify "🔧 TASK: blocked without a failing check and the full gate
     passed; running it once more."`; `ai_log TASK 'gate-only block; host gate passed; retrying
     once' PASS 'See task result'`; set `retry_note=TASK`.
  Comment the rule: deterministic host evidence only, once per task (the claim is spent before the
  gate runs, so a failing gate spends it too), a forged stamp buys at most one gate run and one
  session, nothing is accepted without a later DONE checkpoint.
- Prompt: when `retry_note` equals the task being started, append once to the RUNNER CONTRACT:
  "The previous session marked TASK BLOCKED without a failing check; the runner's full gate then
  passed on this tree. If the block was only about the gate result, verify the acceptance criteria
  and mark it DONE; otherwise block it again with the reason." Clear `retry_note` after use.
- The loop needs no other change: `tasks next` prefers an IN_PROGRESS task; the session budget
  counts the extra session.
- Usage text of `ai-run` (if it lists runner behaviours) gets one sentence. Docs and flow chart are
  T041's (say so in the result).

### Likely affected modules
scripts/ai-run, tests/test_workflow.py (mock claude modes)

### Acceptance criteria
- Tests named `test_gate_only_block_*` in tests/test_workflow.py, pipeline or `ai-run --approved`
  fixtures as the `blocked-first` mock tests (~542, ~9717), with a run manifest (`approve_run`):
  - new mock mode `blocked-gate-unknown` (counter in `MOCK_STATE_DIR`): on its first T001 call it
    runs `.ai/bin/ai-task set T001 BLOCKED`, writes a result line, commits the queue, and leaves
    `.ai/local/validation.json` as `stamp invalidate` would (RUNNING; e.g. by running
    `python3 .ai/bin/lib/workflow.py stamp invalidate`); later calls complete the task normally.
    The run completes; T001 is DONE; notifications contain `blocked without a failing check` and no
    `⚠ Blocked`; git log has `chore(ai): retry T001 after a gate-only block` before T001's DONE
    checkpoint; the second session's prompt (mock-recorded) contains `marked T001 BLOCKED without a
    failing check`; the manifest has `gate_unblocks` `["T001"]`; the host outcome log has one more
    `gate pass` line than a run without the retry;
  - mode `blocked-gate-unknown-always` (blocks every time the same way): exactly one retry
    commit, then T001 stays BLOCKED with the ⚠ notification, and the run continues/ends as the
    `blocked-first` tests expect today.
- `-k blocked`, `-k timeout_rerun` and `-k exec_bits` pass unchanged.
- Mutation evidence in the result: without the `gate-unblock` claim the second case retries more
  than once (or loops to the session budget) and fails.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_only_block` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k blocked` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-20. `scripts/ai-run`: `stamp_before` (DIGEST of `stamp outcome`, `-` on failure) right
before `claude_session`; new `gate_only_retry TASK` after the BLOCKED `runner_checkpoint` (outcome
`running|pass|changed` with a new digest → `run-manifest gate-unblock` → `host_gate` (T039 lock
wait) + `ai_guard_verify` + `record_gate`; a fail prints `Gate-only block retry of TASK: the full gate
failed; it stays BLOCKED.`; a pass sets IN_PROGRESS, logs, commits `chore(ai): retry TASK after a
gate-only block` with tasks/state/run-log/handoff, notifies 🔧, sets `retry_note`). The ⚠ notification
is sent only when no retry happened. The function is called as a plain command (not in a `||`
list) so errexit still guards its commits; the `ai_log` line runs before the commit so it is
included. The next prompt for that task gets the contract sentence once; `retry_note` is cleared
after use. Usage text: one sentence. Tests: mock modes `blocked-gate-unknown(-always)` (record every
prompt in `MOCK_STATE_DIR/gate-unknown-prompts.log`); `test_gate_only_block_retried_once_then_done`
and `test_gate_only_block_retried_once_per_task`.
Evidence: `-k gate_only_block` Ran 2 OK; `-k gate_only_block -k blocked -k timeout_rerun -k exec_bits`
Ran 26 OK; `.ai/bin/ai-check` PASS (1018 tests, 677.9 s, background and waited for, no edits
meanwhile). Mutation: with the `gate-unblock` line removed, the `-always` case loops (ai-run timed
out at the 25 s command bound) and the first case fails (no `gate_unblocks`); restored.
Docs (docs/workflow.md, README) and the flow chart are T041's; no vault edit here.


## T041 — Gate-only block retry: the cases that stay as today, docs and flow chart (FL-32, contract)
Status: DONE
Dependencies: T040
Model: opus

### Goal
The retry fires only in its exact case; every neighbouring BLOCKED case keeps today's behaviour,
pinned by tests; the docs and the flow chart describe FL-32.

### Implementation notes
- Tests only, plus docs. If a case fails, fix the predicate in `scripts/ai-run` narrowly and say so
  in the result.
- Docs: docs/workflow.md, where the runner's BLOCKED handling is described (grep `BLOCKED` ~30,
  ~113, ~896) and the host gate paragraph (~1266): a paragraph "Gate-only block retry" with the
  predicate, once per task per run (kept across resumes, dropped by a human start), the host gate,
  the IN_PROGRESS commit and the notification. README "Recovery" (or the runner section): one
  sentence. README and docs also state the session gate rule of T037 if T037 did not.
- Flow chart (vault `agents-flow.md`, "Inside one task"): after the session, a BLOCKED branch
  "BLOCKED, own gate showed no failure → host gate passes → back to IN_PROGRESS, once per task;
  else ⚠ Blocked"; the notifications table gains the 🔧 line. Update `updated:`; append a hub Log
  line; set the handoff's "## Flow chart" line (or record a denied vault edit there).

### Likely affected modules
tests/test_workflow.py, scripts/ai-run (only if a case fails), README.md, docs/workflow.md, vault
agents-flow.md and agents.md Log, .ai/handoff.md

### Acceptance criteria
- Tests named `test_gate_only_block_unchanged_*` in tests/test_workflow.py (fixtures and mock
  modes as T040's; each asserts: T001 stays BLOCKED, the ⚠ notification as today, no `retry`
  commit, no `blocked without a failing check` notification):
  - the session's gate failed: the mock leaves a FAIL record with `exit_code` 1 (via `stamp
    record 1 <log>` on a fixture) → no host gate run for the retry (no extra `gate` outcome line)
    and no `gate_unblocks` entry;
  - the session never ran the gate (`blocked-first`: validation.json unchanged since before the
    session) → no retry, no `gate_unblocks`;
  - the host gate fails (the fixture `.ai/validate` fails while a marker file exists that the mock
    creates and commits) → one extra `gate fail` line, `gate_unblocks` `["T001"]` (spent), the run
    goes on as today and is not stopped by the retry;
  - no run manifest (plain `ai-run --approved` without `run-manifest start`, if the fixture allows
    it; otherwise say in the result why this case is not covered) → no retry;
  - a dirty tree beyond the records → `Blocked task was not checkpointed` as today.
- `-k Docs` and `-k flow_this_repo` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_only_block` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-20. No runner change: every case already behaved as today. Mock: the
`blocked-gate-unknown(-always)` modes take `MOCK_BLOCK_VARIANT` (`fail`: `stamp record 1 <log>`
after the invalidate; `marker`: also commits `gate-marker`; `dirty`: also leaves `stray.txt`).
Tests (queue T001 + independent T002, so the run goes on and ends on `Unfinished tasks exist but
none can run.` as today): `test_gate_only_block_unchanged_session_gate_failed` (gate rows `[pass]`
= T002's only, `gate_unblocks` `[]`), `_session_never_ran_the_gate` (`blocked-first` after a prior
`ai-check` PASS, so the digest is real and unchanged), `_host_gate_fails` (fixture gate fails while
`gate-marker` exists and T002.txt does not: gate rows `[fail, pass]`, the `Gate-only block retry of
T001: the full gate failed` line, `gate_unblocks` `["T001"]`), `_without_run_manifest` (plain
`ai-run --approved`; no run.json), `_dirty_tree` (`Blocked task was not checkpointed`, no ⚠ since
today's dirty stop precedes it, no gate run). Each asserts T001 BLOCKED, no retry commit, no
`blocked without a failing check`. Mutations: accepting `fail` in the word list fails
`_session_gate_failed`; dropping the `stamp_before` comparison fails `_session_never_ran_the_gate`;
both restored. Docs: docs/workflow.md "Gate-only block retry" + session gate rule paragraphs, the
host-gate paragraph and the queue-selection sentence; README one paragraph. Vault: flow chart
"Inside one task" BLOCKED branch, bullet and 🔧 row in the notifications table (`updated:` already
2026-10-20); hub Log line. Evidence: `-k gate_only_block` Ran 7 OK; `-k Docs` Ran 3 OK;
`-k flow_this_repo` Ran 1 OK; `.ai/bin/ai-check` PASS (1023 tests, 654.7 s, background, waited for).


## T042 — One protected-path list for the guard and the executable-bit repair (review N5)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
`exec-bits` never changes the mode of any gate file, because it and the gate guard read the same
protected-path list, defined once.

### Implementation notes
- Design: `.ai/current-plan.md`, "N5: one protected list".
- `scripts/lib/common.sh` (~142–184): define `AI_PROTECTED_PATHS=(.ai/validate .ai/ci-setup .ai/bin
  .ai/prompts .ai/permissions.allow .claude/settings.json .github/workflows/ai-validate.yml)` and
  `AI_PROTECTED_OPTIONAL=(.claude/settings.json .github/workflows/ai-validate.yml)` once, with a
  comment that this is the only list. `ai_guard_digest` passes them as arguments to the inline
  `python3 -I -` (e.g. the roots, then `--`, then the optional ones) and the heredoc reads
  `sys.argv`; the loop, the order and therefore the digest stay the same. The guard still never
  runs the project helper.
- `scripts/lib/workflow.py` `exec_bits()` (~4460) and its `main()` entry (~4967): `exec-bits
  ROOT...`; no ROOT → usage error (exit non-zero, nothing changed); skip an index entry equal to a
  ROOT or starting with `ROOT/`. Drop the hard-coded `gate` tuple and the `.ai/bin/` prefix; update
  the docstring.
- `scripts/ai-run` (~364): `ai_helper exec-bits "${AI_PROTECTED_PATHS[@]}"`.
- Existing `test_exec_bits_*` unit tests call `helper('exec-bits')` without arguments: pass the
  list (read it from `scripts/lib/common.sh` with a small test helper, or a constant compared to
  it once).
- docs/workflow.md (the exec-bits sentence) and README (the chmod paragraph, if it lists the
  excluded paths): "never a gate file (the protected-path list)".
- Flow chart (vault `agents-flow.md`): the "Executable bits" bullet's "Never `.ai/bin/`,
  `.ai/validate` or `.ai/ci-setup`" becomes "never a gate file (the guard's protected-path list,
  N5)". Update `updated:`; append a hub Log line (or record a denied vault edit).

### Likely affected modules
scripts/lib/common.sh, scripts/lib/workflow.py, scripts/ai-run, tests/test_workflow.py,
docs/workflow.md, README.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- Tests in tests/test_workflow.py:
  - `test_exec_bits_skips_every_protected_path`: on a fixture repository, a regular file at each
    protected root (or one file inside each directory root: `.ai/bin/tool`, `.ai/prompts/x.md`)
    staged with `git add --chmod=+x` and left 0644 on disk → `exec-bits <list>` prints nothing and
    every mode stays 0644, while a `scripts/tool.sh` in the same state is restored and printed;
    a path that only shares a prefix (e.g. `.ai/prompts-extra/x.sh`) IS restored;
  - `test_exec_bits_requires_the_protected_list`: `exec-bits` without arguments exits non-zero
    and changes nothing;
  - `test_exec_bits_protected_list_is_defined_once`: `scripts/lib/common.sh` defines
    `AI_PROTECTED_PATHS` once, the guard heredoc contains no literal `.ai/permissions.allow`, and
    `scripts/ai-run` passes `"${AI_PROTECTED_PATHS[@]}"` to `exec-bits`;
  - `test_exec_bits_guard_digest_unchanged`: on a fixture checkout, `ai_guard_digest` from
    `scripts/lib/common.sh` equals a reference digest computed in the test with the pre-change
    algorithm (the old tuples copied into the test).
- All existing `test_exec_bits_*` tests and the gate-change tests (`-k gate_change`, e.g.
  `test_runner_detects_gate_changes_made_by_git_hooks`) pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k exec_bits` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k gate_change` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
`AI_PROTECTED_PATHS`/`AI_PROTECTED_OPTIONAL` defined once in common.sh; `ai_guard_digest` takes them
as argv (digest unchanged, checked against the old algorithm). `exec-bits ROOT...` skips a ROOT and
anything below it; no ROOT is a usage error. `ai-run` passes the list. 4 new `test_exec_bits_*` tests,
existing ones pass the list. docs/workflow.md and vault flow chart/hub Log updated; README does not
list the excluded paths, so unchanged. Validation: -k exec_bits 11 OK, -k gate_change 6 OK, ai-check
1027 tests OK (712.6 s, background and waited).


## T043 — Docs, flow chart and handoff audit (batch 8)
Status: DONE
Dependencies: T037, T038, T039, T040, T041, T042
Model: haiku

### Goal
README, docs/workflow.md, the prompt templates, the vault flow chart and the handoff match the code
of this batch.

### Implementation notes
- Check against the code: README (setup step 4, `ai-check` lock wait, Recovery, chmod paragraph),
  docs/workflow.md (BLOCKED handling, gate-only block retry, host gate, exec-bits),
  `templates/.ai/prompts/runner.md` and `triage.md` (gate bullet) and `scripts/ai-run`'s RUNNER
  CONTRACT. Wording fixes only; a behaviour mismatch is recorded in the handoff, not fixed here.
- Vault `agents-flow.md`: the T037, T039, T041 and T042 changes are present and agree. Fix the
  wording if needed (update `updated:` then) and append one hub Log line.
- `.ai/handoff.md`: "What has been implemented", "Validation run", "## Flow chart" (one line
  starting `Flow chart updated`), and "Manual testing for the human" with `### Needs you` and
  `### Covered by automated tests` (each test group with its task). `.ai/state.md` counts are
  runner-managed; do not hand-edit them.

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- `-k Docs` and `-k flow_this_repo` pass; the handoff names every new test group of T037–T042.
- The result lists every mismatch found and how it was fixed or recorded.

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
- Targeted: `-k Docs` Ran 3 OK; `-k flow_this_repo` Ran 1 OK.
- Gate: `.ai/bin/ai-check` in the background, waited for: 1027 tests, 0 failing, 673.6 s, OK, exit 0.
- Mismatches found and how they were handled:
  - README chmod paragraph did not say the exec-bit restore skips the protected-path list (N5): clause added.
  - `.ai/handoff.md` was stale (T037–T041 heading, "Next action: Implement T042", test groups "planned"): rewritten for T037–T043.
  - Handoff "Human todos" said only some tasks add a hub Log line: corrected to T037–T043 each adding theirs (T038 and T040 did too).
- Checked, no change needed: `docs/workflow.md` gate-only retry, lock wait and exec-bits sections; `scripts/ai-run` RUNNER CONTRACT, `gate_only_retry`, `host_gate` (`min(remaining, 900)`); `runner.md` and `triage.md` gate bullets; `workflow.py` `tasks next` (prefers IN_PROGRESS); vault `agents-flow.md` (consistent with the code, not edited).
- Every test group named in the handoff exists in `tests/test_workflow.py`.

## T044 — Lock waiting and validation share one `AI_CHECK_TIMEOUT` deadline (review M1)
Status: DONE
Dependencies: none
Model: opus

### Goal
`ai-check` never runs longer than `AI_CHECK_TIMEOUT` (plus GNU `timeout`'s kill-after) in total:
seconds spent waiting for `.ai/local/validation.lock` are deducted from the validator's budget, so
a host gate (`host_gate` in `scripts/ai-run`, which passes `AI_CHECK_TIMEOUT=$remaining`) cannot
return success after the run deadline.

### Implementation notes
- Review M1: `scripts/ai-check` (~15–28) waits up to `AI_CHECK_LOCK_WAIT` for the lock, then starts
  the whole `${AI_CHECK_TIMEOUT:-1800}` for `.ai/validate`; the final gate in `scripts/ai-run`
  (~854–866) does not re-check remaining time after `host_gate`.
- Validate `AI_CHECK_TIMEOUT` (default 1800) as decimal digits like the wait (reuse one pattern;
  T045 handles leading zeros, so normalise with `10#` here already if convenient). Record the start
  (`SECONDS`) before `flock -n`; cap the lock wait at the timeout (`flock -w min(wait, timeout)`).
  After the lock is acquired compute `budget = timeout - (SECONDS - start)`; if `budget <= 0`
  print `Error: Validation time limit reached while waiting for the lock.` and exit 124 (the same
  code GNU `timeout` returns) WITHOUT starting the validator. Never pass 0 to `timeout` (0 disables
  its deadline). Otherwise run `timeout … "$budget" bash .ai/validate`.
- A lock wait that runs out because the timeout cap was hit (not the wait) also exits 124 with
  that message; a wait that runs out first keeps `Validation is already running.` (exit 1).
- Keep the toolkit-repo branch (~4–12) unchanged. `host_gate` keeps passing `remaining`; no
  ai-run change is needed beyond a comment if the behaviour is now exact.
- docs/workflow.md (~1286 "the wait is part of the timed gate") and README (~240) get a clause:
  the wait counts against `AI_CHECK_TIMEOUT`.

### Likely affected modules
scripts/ai-check, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- New tests `test_gate_lock_wait_*` in tests/test_workflow.py on a `ready()` fixture (the test may
  rewrite the fixture's `.ai/validate` to sleep), using `gate_lock_holder`:
  - `_shares_the_timeout_during_validation`: lock held ~2 s (scaled), `AI_CHECK_LOCK_WAIT=30`,
    `AI_CHECK_TIMEOUT` = a scaled 3 s, validator sleeps a scaled 3 s → non-zero (124), total time
    below the timeout plus the 10 s kill-after plus a scaled margin, and `stamp verify` fails;
  - `_exhausts_the_timeout_while_waiting`: lock held a scaled 10 s, `AI_CHECK_LOCK_WAIT=30`,
    `AI_CHECK_TIMEOUT=1` → exit 124 with `Validation time limit reached while waiting`, returns
    within a scaled bound while the holder still runs, and the validator never ran (marker file
    absent);
  - `_within_the_total_budget_passes`: lock held ~1 s, `AI_CHECK_LOCK_WAIT=30`,
    `AI_CHECK_TIMEOUT=30`, fast validator → passes and `stamp verify` succeeds.
- `AI_CHECK_TIMEOUT=x` → non-zero with `Invalid AI_CHECK_TIMEOUT`.
- Existing `-k gate_lock_wait`, `-k gate_time` and `-k session_gate_allowance` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_lock_wait` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k gate_time` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-20. `scripts/ai-check` validates `AI_CHECK_TIMEOUT` (`^[0-9]{1,9}$`, default 1800;
the wait keeps `^[0-9]{1,5}$`), normalises both with `10#` (so T045 only needs its tests), records
`SECONDS` before `flock -n`, caps the wait at the timeout when the timeout is the smaller limit
(running out then → `out_of_time`: stamp invalidated, `Error: Validation time limit reached while
waiting for the lock.`, exit 124), and runs `.ai/validate` with `budget = limit - elapsed`, exiting
124 the same way without starting the validator when `budget <= 0`. `ai-run` `host_gate` got a
comment only. Tests: `test_gate_lock_wait_shares_the_timeout_during_validation`,
`_exhausts_the_timeout_while_waiting`, `_within_the_total_budget_passes`, `_invalid_timeout`.
Mutation (`budget=$limit`) fails the shares test. README, docs/workflow.md (Validation section and
host-gate paragraph), vault flow chart note and hub Log updated.
Evidence: `-k gate_lock_wait` Ran 9 OK (three runs); `-k gate_time` Ran 4 OK;
`-k session_gate_allowance` Ran 5 OK; `-k test_validation_content_mutation_and_timeout_fail` OK;
`-k Docs` Ran 3 OK; full `.ai/bin/ai-check` in the background, waited, no edits meanwhile:
1031 tests OK in 662.4 s, exit 0.

## T045 — `AI_CHECK_LOCK_WAIT` with leading zeros is read as decimal (review N1)
Status: DONE
Dependencies: T044
Model: sonnet

### Goal
An accepted `AI_CHECK_LOCK_WAIT` such as `08` or `09` waits that many seconds under contention
instead of failing Bash octal arithmetic with a misleading `Validation is already running.`.

### Implementation notes
- Review N1: `scripts/ai-check` (~16–19) accepts `^[0-9]{1,5}$` then evaluates `(( wait > 0 ))`;
  `08` errors as an invalid octal number and the script dies at once.
- After the regex check normalise: `wait=$((10#$wait))` (same for `AI_CHECK_TIMEOUT` if T044 did
  not already). The printed `Waiting up to Ns` then shows the decimal value.

### Likely affected modules
scripts/ai-check, tests/test_workflow.py

### Acceptance criteria
- New test `test_gate_lock_wait_leading_zero_is_decimal`: lock held ~1 s (`gate_lock_holder`),
  `AI_CHECK_LOCK_WAIT=08` → prints `Waiting up to 8s`, passes, `stamp verify` succeeds, and stderr
  has no `value too great for base`.
- `AI_CHECK_LOCK_WAIT=00` with the lock held refuses at once with `Validation is already running.`.
- Existing `-k gate_lock_wait` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_lock_wait` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-20. No script change needed: T044 already normalises `AI_CHECK_LOCK_WAIT` and
`AI_CHECK_TIMEOUT` with `10#` (`scripts/ai-check` line 19). Added
`test_gate_lock_wait_leading_zero_is_decimal` (`08` → `Waiting up to 8s`, passes, stamp verifies, no
`value too great for base`) and `test_gate_lock_wait_zero_with_leading_zeros_refuses_at_once` (`00`).
Evidence: `-k gate_lock_wait` Ran 11 OK; full `.ai/bin/ai-check` in the background, waited, no edits
meanwhile: 1033 tests OK in 664.2 s, exit 0.

## T046 — A lock waiter that times out leaves the active gate's stamp alone (review M2)
Status: DONE
Dependencies: T044
Model: opus

### Goal
`ai-check` mutates `.ai/local/validation.json` only while it holds `.ai/local/validation.lock`. A
caller whose lock wait runs out against `AI_CHECK_TIMEOUT` exits 124 with its time-limit message
but never replaces the running validator's RUNNING record (and its `before` fingerprint), so a
content change during the active validation still makes that validation FAIL.

### Implementation notes
- Review M2: `scripts/ai-check` (~22–33): `flock -w "$limit" 8 || out_of_time` runs
  `out_of_time`, which calls `ai_helper stamp invalidate` without the lock. `stamp invalidate`
  (`scripts/lib/workflow.py` ~760) rewrites `before` with the current fingerprint, so the holder's
  later `stamp record` compares against the waiter's fingerprint and can record PASS with
  `unchanged: true` after the content changed; racing the holder's `stamp record` can also replace
  finished evidence with RUNNING.
- Split the two exits: the lock-wait failure path prints `Error: Validation time limit reached
  while waiting for the lock.` and exits 124 without any stamp call (same as the `ai_die` paths,
  which never touched the stamp before T044). The `budget <= 0` path after the lock is acquired
  may keep invalidating (it holds the lock). Add a short comment: stamp changes only under the lock.
- Keep the toolkit-repo branch (~4–12) unchanged. No ai-run change expected; check `host_gate`
  and `gate_only_retry` do not rely on the waiter invalidating (they read `stamp outcome`).
- docs/workflow.md "One gate deadline"/lock-wait paragraph: one clause that a timed-out waiter
  leaves the stamp unchanged, if the paragraph describes the stamp at all.

### Likely affected modules
scripts/ai-check, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- New test `test_gate_lock_wait_timeout_keeps_the_active_stamp` on a `ready()` fixture: write a
  RUNNING `validation.json` with a known `before` value while `gate_lock_holder` holds the lock
  (a scaled 10 s), run `ai-check` with `AI_CHECK_LOCK_WAIT=30 AI_CHECK_TIMEOUT=1` → exit 124 with
  the time-limit message, and `validation.json` is byte-for-byte unchanged afterwards.
- New test `test_gate_lock_wait_timeout_keeps_change_detection`: gate A runs a validator that
  waits for a release file (signalled by the test), the test changes a tracked file while A runs,
  gate B times out waiting (`AI_CHECK_LOCK_WAIT=30 AI_CHECK_TIMEOUT=1`, 124), then A is released
  and exits non-zero with `Validation modified project content`, the stamp is FAIL with
  `unchanged: false`, and `stamp verify` fails. Mutation check: re-adding `stamp invalidate` to
  the wait-failure path makes this test fail (record it in the result).
- A PASS stamp from a finished gate is also left unchanged by a timed-out waiter (subtest or part
  of the first test).
- Existing `-k gate_lock_wait`, `-k gate_time`, `-k session_gate_allowance` and `-k gate_only`
  tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k gate_lock_wait` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k gate_only` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
Done 2026-10-21 (claude opus). `scripts/ai-check`: `out_of_time` no longer calls
`stamp invalidate`; only the `budget <= 0` exit (lock held) invalidates before calling it, with
the comment "The stamp changes only under the lock". New tests
`test_gate_lock_wait_timeout_keeps_the_active_stamp` (PASS and RUNNING `validation.json` subtests,
byte-for-byte unchanged after a 124 waiter; holder still alive) and
`test_gate_lock_wait_timeout_keeps_change_detection` (gate A FAILs with `Validation modified
project content`, `unchanged: false`, `stamp verify` fails). Mutation check: re-adding
`ai_helper stamp invalidate` on the `flock -w "$limit"` failure path made both tests fail (3
failures: change detection `0 == 0`, PASS and RUNNING stamps overwritten); reverted. `host_gate`
uses only the exit code and `gate_only_retry` reads `stamp outcome` before its gate, so neither
relied on the waiter invalidating. docs/workflow.md lock-wait paragraph and the vault "One gate
deadline" bullet updated; hub Log line appended.
Validation: `-k gate_lock_wait` Ran 13 OK; `-k gate_only` Ran 7 OK; `-k gate_time` Ran 4 OK;
`-k session_gate_allowance` Ran 5 OK; `.ai/bin/ai-check` PASS (1035 tests, 675.5 s, background
and waited for).

## T101 — Host ruling record and run-log row format (BR-01, helpers)
Status: DONE
Dependencies: none
Model: opus

### Goal
The host can claim a ruling once per kind per key per human-started run, and write it as one
run-log row in the `Ruling: what, why, cost if wrong` shape that cannot break the table.

### Implementation notes
- Design: `.ai/current-plan.md`, "Rulings: one record, one row format". File `scripts/lib/workflow.py`.
- `run_manifest`: action `ruling KIND KEY` modelled on `gate-unblock` (batch 8, T038; grep
  `gate-unblock` and `task_list_valid`). KIND in `queue-order`, `task-sections`,
  `disposition-cell`, `flow-line` (else usage error); KEY `[A-Za-z0-9._-]{1,48}` (else usage
  error). Optional field `rulings`: list of unique `KIND:KEY` strings, at most 200; any other shape
  invalidates the manifest (extend the validity check and its comment). A repeat fails `ruling KIND
  for KEY was already made once in this run` with the bytes unchanged; else one atomic append.
  `clear-attempts` keeps it; `start` drops it.
- New action `ruling-row KIND WHAT WHY COST`: prints `Ruling (KIND): WHAT. Why: WHY. Cost if
  wrong: COST.` with each `|`, backslash, CR and LF replaced by a space, runs of spaces collapsed,
  cut to 400 characters at a word boundary; wrong argument count → usage error.
- No caller yet (T103–T105). Flow unchanged in this task; say so in the result.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md (the run-manifest field list)

### Acceptance criteria
- Tests named `test_ruling_manifest_*` in tests/test_workflow.py (after `run-manifest start` as
  `approve_run` does):
  - `ruling queue-order T004` exits 0 and the manifest holds `rulings: ["queue-order:T004"]`; a
    second identical call exits 1 with `already made once` and identical manifest bytes;
    `ruling task-sections T004` and `ruling queue-order T005` exit 0;
  - `ruling bogus T004`, `ruling queue-order 'a b'`, a 49-character key and missing arguments exit
    non-zero with usage;
  - `clear-attempts` keeps `rulings`; a new `start` drops it; a manifest with `rulings` `"x"`,
    `["a:b", "a:b"]` or `[1]` is invalid (an action that validates fails, as for `gate_unblocks`);
  - `ruling-row queue-order 'moved T004 | after T006' 'only the order was wrong' 'none'` prints one
    line starting `Ruling (queue-order): moved T004 after T006.` with no `|`, no newline inside, and
    at most 400 characters for a 2000-character WHAT.
- All `test_gate_unblock_manifest_*` and `test_timeout_rerun_manifest_*` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k ruling_manifest` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k gate_unblock_manifest` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-21 (claude opus). `scripts/lib/workflow.py`: `RULING_KINDS`, `ruling_valid`, the
`rulings` check inside `timeout_reruns_valid` (list, ≤200, unique, each `KIND:KEY` with a known
kind and a valid key), `run-manifest ruling KIND KEY` (usage error on bad kind/key/count; repeat
fails `ruling KIND for KEY was already made once in this run`, bytes unchanged; `too many` at
200), `clear-attempts` keeps it, `start` drops it; top-level helper `ruling-row KIND WHAT WHY COST`
(KIND validated too; `|`, `\`, CR, LF → space, space runs collapsed, ≤400 chars cut at the last
word boundary, or hard-cut when that boundary would keep under 300 chars, e.g. one 2000-char
word). docs/workflow.md run-manifest paragraph updated. Tests: `test_ruling_manifest_once_per_kind_and_key`,
`_kept_on_resume_dropped_on_start`, `_wrong_shape_is_invalid`, `_row_is_one_safe_line`.
Validation: `-k ruling_manifest` Ran 4 OK; `-k gate_unblock_manifest` Ran 5 OK;
`-k timeout_rerun_manifest` Ran 4 OK; `.ai/bin/ai-check` PASS (1039 tests, 701.4 s, background
and waited). No caller yet (T103–T105); flow unchanged, vault flow chart not edited.

## T102 — `tasks preflight`: order-only reorder, empty sections, overlap report (BR-02, helper)
Status: DONE
Dependencies: none
Model: opus

### Goal
One host helper decides whether a queue's only faults are order and empty sections, repairs only
TODO tasks, says what it changed, and reports task pairs that share a likely-affected file.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-02 pre-flight"; assumptions A1 and A5 in
  `.ai/project-spec.md`. File `scripts/lib/workflow.py` (`tasks_reorder` ~493–557,
  `fill_task_sections` ~576–598, `tasks_fill_sections` ~601–620, `task_command` ~623).
- Factor the order computation out of `tasks_reorder` (parse + DFS → `order`, `ids`) so both use
  it; `tasks reorder` keeps its behaviour and output exactly.
- `tasks preflight [--dry-run]`:
  1. order: when `order != ids` and every task whose index differs between `ids` and `order` has
     `Status: TODO`, the order is fixable; a non-TODO task that moves → fail with `{T}:
     dependencies must exist earlier in the queue: {dep}` (the `tasks()` wording, first offending
     dependency) and leave the file unchanged. Cycles, unknown IDs, prose, duplicates: the
     `tasks_reorder` errors, unchanged;
  2. sections: TODO tasks missing `Likely affected modules`/`Result / notes` (as `fill-sections`);
  3. print one line per change, `queue-order TASK placed after DEP[, DEP]` (the dependencies that
     were later) and `task-sections TASK added SECTION[, SECTION]`;
  4. overlap: for each pair of TODO tasks A before B whose `### Likely affected modules` tokens
     (split on commas and whitespace; tokens containing `/` or `.`; strip trailing `,.;:` and
     backticks) intersect, print `overlap A B PATH[, PATH]` (at most 20 lines, then `overlap …
     N more`); write the same lines to `.ai/local/preflight.md` through the safe local writer used
     for observation records (skip quietly when `.ai/local` is unsafe);
  5. without `--dry-run` apply 1–2 in one atomic write (mode kept), then run `tasks()` on the
     result; a remaining fault fails with its message. With `--dry-run` write nothing (no
     preflight.md either) and exit 0 when 1–2 would make the queue valid, else fail as in 5.
- No caller yet (T103). Flow unchanged in this task; say so in the result.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md (the `ai-task`/helper list)

### Acceptance criteria
- Tests named `test_preflight_helper_*` in tests/test_workflow.py, on queues built with the
  existing `task()` fixture helper:
  - raid-f4 shape (T001–T006 TODO; T004 `Dependencies: T001, T005, T006`): `--dry-run` prints
    `queue-order T004 placed after T005, T006`, leaves the bytes unchanged; the real run gives the
    order T001 T002 T003 T005 T006 T004 with every block's text unchanged, and `tasks check` passes;
  - a TODO task without `### Result / notes` and `### Likely affected modules` gets both and a
    `task-sections` line; a DONE task missing one is not touched and the queue still fails;
  - DONE T001, DONE T002 depending on a later TODO T003 → fails `T002: dependencies must exist
    earlier in the queue: T003`, file unchanged;
  - a cycle, an unknown ID and `Dependencies: after T002` fail with the `tasks reorder` messages,
    file unchanged; a valid queue prints no `queue-order`/`task-sections` line and is unchanged;
  - T002 and T005 both list `scripts/ai-run` → `overlap T002 T005 scripts/ai-run` and the same
    line in `.ai/local/preflight.md`; DONE tasks never appear in overlap lines.
- Existing `-k reorder` and `-k fill_sections` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k preflight_helper` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k reorder` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-21. `scripts/lib/workflow.py`: `queue_order` (parse + DFS) and `reordered_text`
factored out of `tasks_reorder` (behaviour and output unchanged), `filled_text` out of
`tasks_fill_sections` (output unchanged), new `tasks_preflight` (`tasks preflight [--dry-run]`),
`likely_paths`, `task_status`. One deliberate tightening of the notes: the repaired text is checked
with `tasks()` *before* the write, so a remaining fault fails with its message and leaves the file
unchanged in both modes (the caller dry-runs first anyway). The moved-non-TODO failure names the
moved task's own first later dependency, else the queue's first one. `preflight.md` is written on
every successful real run (empty when there are no overlaps) through `write_record` on the pinned
`.ai/local`; an unsafe or missing `.ai/local` is skipped quietly. docs/workflow.md helper paragraph.
Evidence: `-k preflight_helper` Ran 7 tests OK; `-k reorder` Ran 12 OK; `-k task_sections` Ran 8 OK
(the `-k fill_sections` filter matches no test names; the fill tests are `test_task_sections_fill_*`);
`.ai/bin/ai-check` PASS, 1046 tests, 706.7 s (moved to the background at 600 s and waited for,
no edits meanwhile). No caller yet (T103); flow unchanged, vault not edited.

## T103 — Pre-flight at pipeline start, after plan revisions and after triage (BR-02, FL-24, wiring)
Status: DONE
Dependencies: T101, T102
Model: opus

### Goal
A committed queue whose only fault is order no longer stops the run: the pipeline repairs it once,
commits it with a ruling row and continues; plan revisions, planning sessions and triage log their
repairs the same way.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-02 pre-flight" (chart). Assumptions A1, A2, A4.
- `scripts/ai-pipeline` (~451–464): after the `revision-queue-repair` block and before
  `tasks check`, when not `armed_resume` and the tree is clean: `ai_helper tasks preflight
  --dry-run`; on success with change lines: for each `queue-order T`/`task-sections T` line claim
  `run-manifest ruling KIND T` (any failure → fall through to `tasks check`, which stops as
  today); then `tasks preflight` (real), one `ai_log` row per change built with `ruling-row`
  (WHY `only the order was wrong; dependencies first, no DONE task moved` or `empty section added
  to a TODO task`; COST `a task runs later than planned` or `none, the section is empty`), and
  `host_commit 'chore(ai): ruling: task queue' .ai/tasks.md .ai/run-log.md`; print the overlap
  lines. A dry-run failure changes nothing (today's `tasks check` stop follows).
- `scripts/ai-run --triage` (~641–645): after `fill-sections`, the same claim + `tasks preflight`
  + rows, inside the counted triage commit (no extra commit). `--plan` (~440–446) and
  `--revise-plan` (~551–560): keep today's `fill-sections` + `reorder` (no claim: no run manifest
  in a planning session), and add one ruling row per printed change plus the overlap lines on
  stdout; the rows land in the plan's run log (planning) or the revision commit.
- Notify once per ruling commit: `🔧 Ruling: task queue reordered (T004 after T005, T006); see the
  run log.`
- Flow chart (vault `agents-flow.md`, "The big picture" before the plan review, and "When
  something goes wrong"): a "Pre-flight queue scan" step and a bullet "Rulings (BR-01/BR-02, T103,
  2026-10-20)": order-only faults and empty sections of TODO tasks are fixed once per task per run,
  logged `Ruling (…)`, else the stop as today; the notifications table gains the 🔧 Ruling row.
  Update `updated:`; append a dated hub Log line in `agents.md` (never tick checkboxes); set the
  handoff's `## Flow chart` line. If the vault edit is denied, record it in the result and in the
  handoff's "## Flow chart" section.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, tests/test_workflow.py, docs/workflow.md, README.md, vault
agents-flow.md and agents.md Log, .ai/handoff.md

### Acceptance criteria
- Tests named `test_preflight_pipeline_*` in tests/test_workflow.py (pipeline fixtures with a run
  manifest, mock Codex/Claude as the existing pipeline tests):
  - `raid_f4_committed_queue`: the raid-f4 queue (T004 depends on the later T005, T006) committed
    → the pipeline commits `chore(ai): ruling: task queue` before `chore(ai): record plan review`,
    the run log has a `Ruling (queue-order)` row naming T004 with no extra `|` cells, the
    notifications contain `Ruling: task queue reordered`, the plan is reviewed and the run
    completes with T001 T002 T003 T005 T006 T004 DONE in that order;
  - `same_ruling_twice_stops`: the manifest already holds `queue-order:T004` (claimed) and the
    committed queue is out of order again → stops with `Task queue is invalid: T004: dependencies
    must exist earlier in the queue` as today, no ruling commit;
  - `done_task_would_move_stops`: a DONE task depending on a later TODO task → today's stop;
  - `triage_reorders_fix_task`: a mock triage appends two fix tasks, T010 (`Dependencies: T011`)
    and then T011 → after triage T011 is before T010 in the queue, the triage commit holds the
    ruling row, and the run goes on;
  - `plan_session_logs_rulings`: `ai-run --plan` whose mock session writes an out-of-order queue →
    `Ruling (queue-order)` row in the run log and the overlap line on stdout.
- Existing `-k revision_queue_repair`, `-k plan_revision` and `-k triage` tests pass unchanged
  (update only expected run-log rows where a ruling row is now added, and say which in the result).

### Validation
Targeted: `python3 -m unittest discover -s tests -k preflight_pipeline` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k revision_queue_repair` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-21 (claude opus). `scripts/lib/common.sh`: `ai_queue_ruling TASK` (dry run →
`run-manifest ruling` per `queue-order`/`task-sections` line → real `tasks preflight` → one
`ai_log` row per change via `ruling-row` → one `🔧 Ruling: task queue reordered (T004 after T005,
T006); see the run log.`; returns 1 and changes nothing on a failed dry run or the first refused
claim; earlier claims of the same scan stay spent), `ai_ruling_rows`, `ai_overlap_lines`.
`ai-pipeline`: after the `revision-queue-repair` block, not armed and clean →
`ai_queue_ruling preflight` → `host_commit 'chore(ai): ruling: task queue' .ai/tasks.md
.ai/run-log.md`, then `tasks check` as before. `ai-run --triage`: `ai_queue_ruling triage` after
`fill-sections`, inside the counted triage commit (also notifies). `--plan`/`--revise-plan`: a
dry run before today's fill+reorder names the changes; rows (`planning`/`plan-revision`) and
overlap lines added after the check (no claim, no notification). Tests: `test_preflight_pipeline_*`
(6: `raid_f4_committed_queue`, `same_ruling_twice_stops` (manifest claimed, resumed with
`AI_RECOVERY_ATTEMPT=1`), `done_task_would_move_stops`, `triage_reorders_fix_task` (mock
`triage-out-of-order`: T002 depends on T003; IDs follow the fixture queue instead of T010/T011),
`plan_session_logs_rulings` (mock `plan-out-of-order-shared`), `revision_logs_rulings_in_the_revision_commit`).
Changed existing tests: `test_queue_check_invalid_queue_stops_plan_review`, `_escalates_without_recovery_session`,
`_stops_with_skip_plan_review` now use `unfixable_queue()` (a cycle), because the old order-only
queue is now repaired; `test_queue_repair_committed_out_of_order_queue_still_stops_the_pipeline`
removed (its behaviour is reversed by this task; covered by the new raid-f4 and repeat tests). No
expected run-log rows in `-k revision_queue_repair`/`plan_revision`/`triage` tests needed changes.
Docs: docs/workflow.md "Pre-flight queue scan" paragraph, README queue sentence and 🔧 Ruling
row; vault flow chart (pre-flight step, note, Rulings bullet, 🔧 Ruling row, `updated:`) and hub Log.
Validation: `-k preflight_pipeline` Ran 6 OK; `-k revision_queue_repair` Ran 0 (matches no test
name; the tests are `test_queue_repair_*`/`test_queue_recovery_*`: with `-k queue_check`,
`-k task_sections` Ran 32 OK); `-k plan_revision -k triage` Ran 49 OK; `-k Docs -k flow_this_repo
-k preflight` Ran 18 OK; `.ai/bin/ai-check` PASS (1051 tests, 678.6 s, background and waited, no
edits meanwhile).

## T104 — Ruling: a disposition cell with more than the bare finding ID (BR-01, FL-30, FL-25)
Status: DONE
Dependencies: T101
Model: opus

### Goal
A triage or plan-revision row whose first cell wraps the one finding ID in markup or adds text the
parser rejects is repaired once by the host instead of stopping the run.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-01 record-format rulings". File `scripts/lib/workflow.py`
  (`FINDING_CELL`/`DISPOSITION_ROW` ~1056–1066, `unmatched_cell_hint` ~1069, `triage_check`
  ~1105, `PLAN_DISPOSITION_ROW` ~2897 and its check ~3077).
- New action `disposition-ruling triage|plan [--dry-run]`: target `.ai/reviews/dispositions.md`
  (triage, the whole table) or the last section of `.ai/reviews/plan-dispositions.md` (plan); the
  known IDs are the current review's BLOCKER/MAJOR (and MINOR) finding IDs (`finding_ids` on
  `.ai/reviews/current.md` or `.ai/reviews/plan.md`). For each known ID with no matching row
  (same regex as the check), find table lines whose first cell, after removing `*`, `` ` ``, `[`
  and `]`, contains that ID word-bounded and no other known ID; exactly one such line → rewrite its
  first cell to ` ID ` (the rest of the line byte-identical); print `ID`. Zero or several lines →
  no change for that ID. Never touch the header, `Review HEAD:` line, comments or other sections.
  Print also `digest <sha256-12 of the review>` first, for the claim key.
- `scripts/ai-run --triage`, before `triage-check --fresh` (~647): run the dry run; for each ID
  claim `run-manifest ruling disposition-cell <digest12>.<ID>` (failure → skip all rewrites;
  today's check stops); then the real run and one `ruling-row` row per ID (WHAT `finding cell
  "<old cell, 60 chars>" read as ID`, WHY `the cell held exactly one finding ID of this review`,
  COST `the row is counted for ID; a wrong reading shows in the PR's dispositions`), all inside the
  counted triage commit. `--revise-plan`, before `plan-dispositions-check` (~562): the same with
  `plan`.
- Prompts unchanged (`templates/.ai/prompts/` already show the bare-ID row).
- Flow chart: the "Rulings" bullet (T103) gains "a disposition cell with more than the bare ID".
  Update `updated:`, hub Log line (or record a denied vault edit). If T103's bullet is missing, add
  the bullet here.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, tests/test_workflow.py, docs/workflow.md, vault
agents-flow.md and agents.md Log

### Acceptance criteria
- Tests named `test_ruling_disposition_*` in tests/test_workflow.py:
  - helper: review with MAJOR M1 and M2; rows `| **M1** | accepted | evidence | T012 |` and
    `` | `M2` (CRITICAL) | rejected | concrete evidence here | - | `` → both first cells become
    `| M1 |`/`| M2 |`, the rest of each line byte-identical, `triage-check` then passes;
  - helper, no change: a cell `M1/M2`, a cell naming an ID not in the review, two lines both
    mentioning M1, an already matching row → output without IDs and file bytes unchanged;
  - helper `plan`: the same rewrite only inside the last plan-dispositions section; an earlier
    section's identical bad cell stays;
  - triage flow: a mock triage writes `| **M1** | accepted | … | T012 |` → triage completes, the
    triage commit has a `Ruling (disposition-cell)` row, the manifest holds
    `disposition-cell:<digest12>.M1`; with that key already claimed → `Triage incomplete: MAJOR
    finding M1 has no disposition` as today;
  - plan revision flow: the mock revision writes `| **P1** | accepted | … | T009 |` → the revision
    is recorded and the run continues.
- Existing `-k disposition` and `-k triage_check` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k ruling_disposition` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k disposition` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
Done 2026-10-21. `workflow.py disposition-ruling triage|plan [--dry-run]` prints `digest
<sha256-12>` and then `ID <old cell>` for each rewrite. Only BLOCKER/MAJOR findings without a
counted row are rewritten. The rest of the line must stay byte-identical and the rewritten line
must match the row pattern for that ID, so a ruling that would not fix the row claims nothing.
Comment lines are skipped. `ai_disposition_ruling` in `scripts/lib/common.sh` does dry run →
claims → real run → `Ruling (disposition-cell)` rows. `ai-run` calls it before `triage-check
--fresh` (task `triage`) and before `plan-dispositions-check` (task `plan-revision`), so both
land in the counted commit. Mock modes added: `triage-bold-cell`, `revise-accept-bold`.
Evidence: `-k ruling_disposition` Ran 6 tests OK (helper rewrite, ambiguous cells (`M1/M2`,
unknown ID, two lines, already matching, `M10`), plan last section only, triage flow, repeat claim
stops as today, plan revision flow). `-k disposition` Ran 31 OK, `-k triage_check` Ran 1 OK,
`-k preflight` Ran 14 OK. Full gate `.ai/bin/ai-check`: PASS, 1057 tests in 689.8 s.
docs/workflow.md (Triage paragraph), vault agents-flow.md Rulings bullet and the agents.md Log
line are updated. One deviation from the criteria: the helper criterion uses `T012`, but the
fixture uses `T001`, the existing TODO task, so `triage-check` passes.

## T105 — Ruling: the handoff's `## Flow chart` line (BR-01, wiring)
Status: DONE
Dependencies: T101
Model: opus

### Goal
A handoff whose `## Flow chart` section does not start with `Flow chart updated` or `Flow
unchanged` is repaired once before the host gate and the PR body, instead of failing the gate.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-01 record-format rulings"; assumption A6.
- New action `flow-line-ruling [--dry-run]` (workflow.py; reuse `section()` boundaries as
  `pr_body` ~4282 does): only when `.ai/handoff.md` has a `## Flow chart` heading outside code
  fences. Let L be its first non-empty line. When L starts with `Flow chart updated` or `Flow
  unchanged` and directly follows the heading: no change. When L starts with one of them but blank
  lines precede it: remove those blank lines. Otherwise insert, right after the heading,
  `Flow unchanged (host ruling)` when the section text matches `\bunchanged\b` or `no flow change`
  (case-insensitive), else `Flow chart updated (host ruling; see below)`, and drop the blank lines
  between the heading and L. Print the inserted or moved line; nothing when unchanged. A missing
  section: no change.
- `scripts/ai-run`: in `checkpoint_done` and before the final `host_gate` (~856): `--dry-run`; when
  it prints, claim `run-manifest ruling flow-line <task or final>` (failure → no change), run it
  and `ai_log` one `ruling-row` row (WHY `the section must start with one of the two phrases`,
  COST `the PR says the flow changed or not when the other is true; the section text below it
  stays`). The handoff and run log are records, so the runner checkpoint commits them as today.
- `scripts/ai-pipeline`, before the PR body is built: the same with key `final` (already claimed →
  skip) and the rows in the PR's record commit.
- Flow chart: the "Rulings" bullet gains "the handoff's Flow chart line". Update `updated:`, hub Log
  line (or record a denied vault edit).

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, scripts/ai-pipeline, tests/test_workflow.py,
docs/workflow.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- Tests named `test_ruling_flow_line_*` in tests/test_workflow.py:
  - helper: `## Flow chart\n\nFlow chart: updated the Inside one task node.\n` → the line after the
    heading is `Flow chart updated (host ruling; see below)` followed by the original text;
    `## Flow chart\nNo flow change in this batch.\n` → `Flow unchanged (host ruling)`;
    `## Flow chart\n\nFlow unchanged.\n` → the blank line removed only; a correct section and a
    handoff without the section → no output, bytes unchanged; a `## Flow chart` line inside a code
    fence is ignored;
  - runner: a mock session finishes T001 with a handoff whose section has a blank line first → the
    host gate passes, the run log has a `Ruling (flow-line)` row, the PR body (pipeline fixture)
    contains `Flow chart updated (host ruling`; with `flow-line:T001` already claimed the handoff
    is left as the session wrote it.
- `test_pr_body_flow_this_repo_declares_the_flow_chart` and `-k pr_body` pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k ruling_flow_line` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k pr_body` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-21. `workflow.py flow-line-ruling [--dry-run]` (first `## Flow chart` heading outside
code fences; HTML comments count as empty, so the template's comment-only section is left alone;
an empty section too). `ai_flow_line_ruling KEY TASK` in `scripts/lib/common.sh`: dry run, claim
`run-manifest ruling flow-line KEY`, real run, `Flow chart line: "…" placed under the heading.` and
one `Ruling (flow-line)` row. Called in `ai-run` `checkpoint_done` before `host_gate` (key = task)
and before the final gate (key `final`, row under `none`; `.ai/handoff.md` added to the `record
review handoff` commit), and in `ai-pipeline` before `pr-body` (key `final`; `.ai/handoff.md` added
to the `record pull request` commit). Deviation: a correct phrase line preceded by a comment is
moved above the comment (the comment stays below it). Tests: 5 `test_ruling_flow_line_*` (mock
mode `flow-blank`; fixture gate fails on a blank line under the heading). Evidence: `-k
ruling_flow_line` Ran 5 OK; `-k pr_body` Ran 4 OK (unchanged); `-k ruling -k preflight` Ran 29 OK;
`.ai/bin/ai-check` PASS, 1062 tests, 723.0 s (the 600 s foreground call was moved to the
background by the tool and waited for). docs/workflow.md, vault agents-flow.md Rulings bullet and
agents.md Log updated.

## T106 — `attempt-info`: attempt number, raised model and failure note from the host outcome log (BR-03, helper)
Status: DONE
Dependencies: none
Model: opus

### Goal
The runner can ask the host record how many times a task already failed, which model the next
session should use, and what to tell it about the last failure.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-03 fresh retry"; assumptions A7 and A8. File
  `scripts/lib/workflow.py` (`outcome` ~3865, `read_outcomes`, `project_name` ~3416,
  `outcomes_path` ~3412, `stamp_outcome` for the safe `.ai/local` read).
- `attempt-info TASK [BASE_MODEL]` (TASK must be a valid task ID, else usage error):
  - rows = outcome rows with `kind` task, this `project_name()`, current branch and `task` TASK,
    in `seq` order; failures = rows whose `result` is not `done`; N = len(failures) + 1;
  - model: the task's `Model:` from `.ai/tasks.md`, else BASE_MODEL, else none. When N ≥ 3: a
    model containing `haiku` → `sonnet`, containing `sonnet` → `opus`, containing `opus` or
    `fable` → unchanged, none → `opus`; RAISED is `yes` when the printed model differs from the
    task's or base model;
  - line 1: `N MODEL RAISED` (`-` for no model);
  - note (only when N ≥ 2), at most 600 characters in total, `|` and newlines removed per item:
    `Attempt N-1 ended RESULT after S s on MODEL.`; `Failing checks: a, b, c.` from the validation
    log (read `.ai/local/validation.json` like `stamp outcome`, then its log path only when it is
    a regular file directly inside `.ai/local`, opened without following symlinks, at most 256 KiB
    from the end; unittest `FAIL: name`/`ERROR: name`, pytest `FAILED name`, at most 5; else `Last
    gate line: …` with the last non-empty line; nothing when no log); `Last result line: …` (the
    last non-empty line of the task's `### Result / notes`, 200 characters);
  - any error reading the outcome log or the queue → `1 <task or base model or -> no` and exit 0.
- No ai-run change here (T107). Flow unchanged in this task; say so in the result.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md (helper list / outcome log)

### Acceptance criteria
- Tests named `test_attempt_info_*` in tests/test_workflow.py (outcome rows written with the
  `outcome task` helper under the test state root):
  - no rows → `1 sonnet no` for a sonnet task and no note; a `done` row only → still attempt 1;
  - one `timeout` row (1800 s, sonnet) → `2 sonnet no` and a note with `Attempt 1 ended timeout
    after 1800 s on sonnet.`;
  - two failed rows → `3 opus yes` for a sonnet task, `3 sonnet yes` for a haiku task, `3 opus no`
    for an opus task, `3 opus yes` for a task without `Model:` and no BASE_MODEL, `3 opus yes` for
    BASE_MODEL `claude-sonnet-5-5`; a fourth attempt of a haiku task is still `sonnet`;
  - rows of another branch, project or task are not counted;
  - a validation log with `FAIL: test_a (tests.T)` and `ERROR: test_b (tests.T)` → `Failing checks:
    test_a (tests.T), test_b (tests.T).`; a symlinked log path → no failing-checks item;
  - the note has no `|`, no newline inside an item, and at most 600 characters with a huge result
    line; a corrupt outcome log → `1 … no`, exit 0.

### Validation
Targeted: `python3 -m unittest discover -s tests -k attempt_info` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-21 (claude opus). `workflow.py attempt-info TASK [BASE_MODEL]` (`attempt_info`,
`raised_model`, `attempt_note_item`, `gate_log_lines`, `failing_checks_item`, `result_notes_line`):
rows from `read_outcomes(strict=True)` filtered to kind task, `project_name()`, branch and TASK,
ordered by `ordered_attempts`; N = failed rows + 1; tier raise from N ≥ 3 (unknown model names stay);
note items one per line, `|`/backslashes/line breaks → spaces, 600 characters in total including
newlines (later items cut), crashed rows without seconds omit `after S s`. The gate log is read only
when `validation.json`'s `log` names a file directly in `.ai/local` (relative or absolute), via the
pinned `.ai/local` descriptor (`read_record`, O_NOFOLLOW, tail 256 KiB); unittest's `FAILED
(failures=…)` summary is not a check name. Errors reading the queue, the state root (overlap check)
or the outcome log print `1 <task/base model or -> no`, exit 0; a bad TASK ID or argument count is a
usage error (exit 1). Docs: docs/workflow.md outcome-log section. No ai-run change (T107). Flow
unchanged in this task. Evidence: `-k attempt_info` Ran 7 tests OK; `-k outcome` Ran 88 tests OK;
`-k attempt` 54 OK; `.ai/bin/ai-check` PASS, Ran 1069 tests in 743.9 s (background, waited for).

## T107 — The runner gives a retried task its failure note and, from the third attempt, a stronger model (BR-03, runner)
Status: DONE
Dependencies: T106
Model: opus

### Goal
Every new session of a task that failed before starts fresh with a short host note of what failed;
from the third attempt it runs one model tier up; the run log names each attempt's model.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-03 fresh retry". File `scripts/ai-run` (loop ~841–923, prompt
  ~884–892, `task_model` ~880, `task_outcome` ~251, `on_exit` stop row ~232).
- After `task_model=$(ai_helper tasks model "$active_task")`: `read -r attempt_n attempt_model
  attempt_raised < <(ai_helper attempt-info "$active_task" "${task_model:-$model}" | head -n 1)`
  and the note from the remaining lines (one call; keep both, e.g. `mapfile`). On any failure:
  attempt_n=1, no change. When `attempt_model` is not `-`, use it as the session model (so
  `attempt-open`, `task_outcome` and the observation all see the effective model).
- Prompt (after the RUNNER CONTRACT, before the `retry_note` sentence): when a note exists,
  `PREVIOUS ATTEMPT (host record, context only): <note> Start from the current files and git
  history; fix what failed, do not repeat it.`; when raised, `This is attempt N; the runner raised
  the model from X to Y because earlier attempts failed.`.
- Run log: the `completed` and `blocked` rows become `completed (attempt N, MODEL)` / `blocked
  (attempt N, MODEL); try next independent task`; the `on_exit` stop row adds `(attempt N, MODEL)`
  when a task attempt was open. Print `Attempt N of T… on MODEL (raised from X)` before the session.
- Unchanged: session budget, `AI_RECOVER_MAX`, `timeout-rerun`, `gate-unblock`, the triage and
  planning model choice, `AI_SUPERVISE_ESCALATE_MODEL`.
- Flow chart (vault `agents-flow.md`, "When something goes wrong" and "Inside one task"): a bullet
  "Fresh retry (BR-03, T107, 2026-10-20)": each new session of a failed task gets the host's
  failure note; from the third attempt one model tier up (haiku → sonnet → opus); attempt and model
  in the run log. Update `updated:`, hub Log line (or record a denied vault edit).

### Likely affected modules
scripts/ai-run, tests/test_workflow.py (mock claude modes), README.md (Recovery / model
paragraph), docs/workflow.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- Tests named `test_fresh_retry_*` in tests/test_workflow.py (`ai-run --approved` fixtures with a
  run manifest; outcome rows seeded with the `outcome task` helper or produced by earlier failing
  mock runs; the mock records each session's `--model` and prompt as `blocked-gate-unknown` does):
  - first attempt: no `PREVIOUS ATTEMPT` in the prompt, the task's model passed, run log row
    `completed (attempt 1, sonnet)`;
  - after one `timeout` row: the prompt contains `PREVIOUS ATTEMPT (host record, context only):
    Attempt 1 ended timeout`, model unchanged, row `(attempt 2, sonnet)`;
  - after two failed rows of a sonnet task: `--model opus`, the prompt says `raised the model from
    sonnet to opus`, the host outcome row of this attempt has model `opus`, the run log row says
    `(attempt 3, opus)`;
  - an opus task after two failures: `--model opus`, no `raised` sentence;
  - `attempt-info` failing (corrupt outcome log): the session runs as today.
- `-k gate_only_block`, `-k timeout_rerun`, `-k session_gate_allowance` and `-k blocked` pass
  (update only expected run-log row texts, and list them in the result).

### Validation
Targeted: `python3 -m unittest discover -s tests -k fresh_retry` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k gate_only_block` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-21 (claude opus). `scripts/ai-run`: one `attempt-info "$task" "${task_model:-$model}"`
call (mapfile) right after `tasks model`, before the dashboard step; line 1 is accepted only when
N is a number, RAISED yes/no and MODEL `-` or matching the `--model` pattern (`model_pattern` now
global), else attempt 1 and nothing changes. A non-`-` MODEL becomes `task_model`, so `--model`,
`attempt-open`, `task_outcome` and the observation see it. Prompt sentences (`PREVIOUS ATTEMPT (host
record, context only): …` with the note lines joined by spaces; `This is attempt N; the runner raised
the model from X to Y because earlier attempts failed.`) after the RUNNER CONTRACT, before the
gate-only retry sentence; `Attempt N of T… on MODEL (raised from X)` printed; run-log rows `completed
(attempt N, MODEL)`, `blocked (attempt N, MODEL); try next independent task`, and the `on_exit` stop
row `stopped (exit C) (attempt N, MODEL); …` when an attempt was open (the armed-checkpoint route
keeps a plain `completed`). Mock claude records each task prompt in `.ai/local/mock-prompts`. 7
`test_fresh_retry_*` tests. No existing test checked those run-log row texts, so no expected texts
changed. Docs: README Models, docs/workflow.md (Fresh retry paragraph); vault flow chart pick node +
two Fresh retry bullets, hub Log line. Evidence: `-k fresh_retry` Ran 7 tests OK; `-k gate_only_block
-k timeout_rerun -k session_gate_allowance -k blocked` Ran 30 tests OK; `.ai/bin/ai-check` PASS, Ran
1076 tests in 725.6 s (foreground call moved to background by the tool, waited for).

## T108 — `review-route`: Codex or Claude by risk, from host records and the diff (BR-14, helper)
Status: DONE
Dependencies: none
Model: opus

### Goal
One host helper decides, deterministically and from records agent sessions cannot forge, whether a
review needs Codex or can go to a fresh Claude session.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-14 review routing"; assumptions A9 and A10. File
  `scripts/lib/workflow.py` (`review_risk` ~3369 and `RISK_TITLE` ~3363 for the style; the
  `fix-rounds` host record helpers; outcome review rows ~3947; `review_rounds` ~1168 is context
  only and must NOT be used).
- `review-route MODE BASE HEAD` (MODE plan, code or recheck; BASE and HEAD commits): print one line
  `codex REASON` or `claude REASON`, exit 0; any exception → `codex routing unavailable`. Rules, the
  first that applies wins:
  1. `AI_REVIEW_ROUTE` = `codex` → `codex routing off`; any value other than empty, `risk` or
     `codex` → `codex invalid AI_REVIEW_ROUTE`;
  2. MODE plan → `codex plan review`; recheck → `codex re-check`;
  3. host fix-round records for BASE (the same reader as `fix-rounds count`) = 0 → `codex first
     full code review`;
  4. outcome review rows of this project and branch with mode `code`: none with reviewer `codex`
     whose `head` is an ancestor of HEAD → `codex no Codex review of this branch yet`; LAST = the
     newest row (any reviewer) whose head is an ancestor of HEAD and differs from HEAD, none →
     `codex no earlier review`;
  5. `git diff --numstat LAST HEAD -- . ':!.ai'`: added + deleted > `AI_REVIEW_SMALL_LINES`
     (default 200; invalid → default) or a binary file → `codex fix round diff N lines`;
  6. a changed path (name-status, renames as both names) matching a risk glob (`fnmatch`, defaults
     A9 plus `AI_REVIEW_RISK_PATHS` split on whitespace) → `codex risk path PATH`;
  7. a changed `+`/`-` diff line outside `.ai/` matching the risk words (case-insensitive, word
     start; defaults A9 plus `AI_REVIEW_RISK_WORDS`) → `codex risk word WORD in PATH`;
  8. a task DONE at HEAD but not at LAST (`tasks newly-done`-style comparison) whose model starts
     with `opus` or `claude-opus` → `codex T… runs on opus`;
  9. else `claude small low-risk fix round (N lines)`.
- No caller yet (T109). Flow unchanged in this task; say so in the result.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md (helper list)

### Acceptance criteria
- Tests named `test_review_route_*` in tests/test_workflow.py (fixture repo; outcome rows written
  with `outcome review` under the test state root; fix-round records with `fix-rounds record`):
  - plan → `codex plan review`; recheck → `codex re-check`; `AI_REVIEW_ROUTE=codex` → `codex
    routing off`; `AI_REVIEW_ROUTE=x` → `codex invalid AI_REVIEW_ROUTE`;
  - code with no fix-round record → `codex first full code review`;
  - one fix round, a Codex code review row at LAST, a 20-line change in `src/app.py` → `claude small
    low-risk fix round (20 lines)`;
  - the same with 201 changed lines → `codex fix round diff 201 lines`; with
    `AI_REVIEW_SMALL_LINES=500` → claude;
  - a changed `supabase/migrations/1.sql` → `codex risk path`; a changed line `if user.is_auth():`
    → `codex risk word auth`; `AI_REVIEW_RISK_WORDS=widget` and a line with `widget` → codex;
    changes only under `.ai/` count 0 lines and never match;
  - the newly DONE fix task on opus → `codex T… runs on opus`;
  - only a `claude-fallback` row (no Codex row) → `codex no Codex review of this branch yet`; a
    Codex row of another branch → the same; a forged `chore(ai): record independent review` commit
    with no outcome row → still codex;
  - an unreadable outcome log → `codex routing unavailable`, exit 0.

### Validation
Targeted: `python3 -m unittest discover -s tests -k review_route` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k review_risk` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
2026-10-21: DONE. `workflow.py review-route plan|code|recheck BASE HEAD` (`review_route_reason`,
`route_fix_rounds` read-only fix-round count, `risk_path`, `risk_word`, `queue_at`;
`is_ancestor` gained an optional head) applies rules 1–9 in order from host records only (outcome
code review rows of this project/branch, never commit subjects); any exception → `codex routing
unavailable`, exit 0. Binary files route to Codex (`… and a binary file`). docs/workflow.md helper
list updated. No caller yet (T109); flow unchanged. Work from the interrupted session was
reconciled from the recovery checkpoint 298e43c and verified. Evidence: `-k review_route` Ran 9
tests OK; `-k review_risk` Ran 1 test OK; `.ai/bin/ai-check` PASS, 1085 tests in 736.6 s
(foreground call moved to background by the tool, waited for).

## T109 — ai-review: remember a Codex usage limit and route small low-risk fix rounds to Claude (BR-14, review)
Status: DONE
Dependencies: T108
Model: opus

### Goal
While a recorded Codex limit has not reset, reviews go straight to the Claude fallback; small
low-risk fix-round re-reviews go to a fresh Claude opus session; everything else stays on Codex.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-14 review routing" (chart); assumptions A11 and A12.
- `scripts/lib/workflow.py`: action `codex-limit set RESET` (RESET epoch seconds > now, else usage
  error) writes state root `codex-limit.json` `{"reset": RESET, "recorded": now()}` atomically
  (`check_state_root` first); `codex-limit active` prints RESET and exits 0 while `reset > now`,
  else exits 1 (missing, unreadable, past, not a JSON object: exit 1; never writes).
- `scripts/ai-review` `run_review` (~152–217): compute `try_codex` as today; then, only when
  `reviewer == auto` and `try_codex == yes`:
  1. `until=$(ai_helper codex-limit active)` succeeds → `try_codex=no`, `fallback="Codex usage
     limit until $(date -d "@$until" '+%F %H:%M') (recorded)"` (the fallback branch as today:
     `↪` notification, `claude-fallback`, catch-up entry);
  2. else `route=$(ai_helper review-route "$mode" "$route_base" "$start_head")` (route_base: the
     merge-base for code, `$plan_base` or `-` for plan, `-` for recheck; the helper answers codex for
     plan/recheck anyway); `claude *` → `try_codex=no`, `routed=${route#claude }`.
  On the Claude path with `routed` set: `review_by=claude-routed`, `who='Claude (routed)'`,
  `AI_REVIEW_BY="Claude (routed), $claude_model"`, `AI_REVIEW_LABEL="Claude, routed ($claude_model,
  effort $claude_effort; $routed). Codex reviewed this branch earlier; no catch-up needed."`;
  print `Routed to Claude: $routed`; no `↪` notification; `review_reason=$routed`.
  `review_records`: no `fallback-record` for `claude-routed`. Reset `routed` per call like the
  other per-call variables.
- After a Codex limit (~177–186) with `reset != 0`: `ai_helper codex-limit set "$reset" || true`
  before falling back (also when `reviewer == codex`, which still pauses as today).
- `pr_body` (~4300): its fallback regex must not mistake the routed label for a fallback; the
  heading reads `Independent review (Claude, routed, MODEL)` and the `[!NOTE]` says `routed to a
  fresh Claude session: REASON` instead of the catch-up text.
- Settings `AI_REVIEW_ROUTE`, `AI_REVIEW_SMALL_LINES`, `AI_REVIEW_RISK_PATHS`,
  `AI_REVIEW_RISK_WORDS`: add to the manifest capture/restore lists (`scripts/lib/common.sh` ~40,
  workflow.py ~2374, `scripts/ai-recover` ~81 and ~84); `ai-review` validates `AI_REVIEW_ROUTE`
  (empty, `risk`, `codex`) and `AI_REVIEW_SMALL_LINES` (`^[1-9][0-9]{0,5}$`) with `ai_die
  "Invalid …"`. Usage text of `ai-review` and `ai-pipeline`: one sentence each.
- Flow chart (vault `agents-flow.md`, "Reviewer choice"): Codex for plan, re-check, first full code
  review and large or risky fix rounds; small low-risk fix rounds on a fresh Claude opus session
  (routed, no catch-up); a recorded Codex limit sends reviews to the fallback until its reset.
  Update `updated:`, hub Log line (or record a denied vault edit).

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-review, scripts/ai-recover, scripts/lib/common.sh,
scripts/ai-pipeline (usage text), tests/test_workflow.py (mock codex), README.md,
docs/workflow.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- Tests named `test_codex_limit_*` (helper) and `test_review_routing_*` (ai-review / pipeline) in
  tests/test_workflow.py:
  - `codex-limit set <now+600>` then `active` prints it, exit 0; a past reset or no file → exit 1;
    `set` with a past value or text → usage error; a symlinked or garbage file → exit 1;
  - a mock Codex that reports a usage limit with a reset in 10 minutes → the first review falls back
    and writes the record; a second review in the same window makes no Codex call (the mock counts
    calls), runs the Claude fallback with `(recorded)` in the label and adds a fallback-log row;
    with the record in the past → Codex is called again;
  - pipeline fixture with one fix round of a 10-line low-risk change after a Codex round 1 → the
    round-2 review makes no Codex call, `.ai/reviews/current.md` carries `Claude, routed`, no new
    fallback-log row, the outcome row has reviewer `claude-routed`, and the PR body heading says
    `routed`;
  - the same fix round touching `supabase/migrations/x.sql` → Codex reviews round 2;
  - `AI_REVIEWER=codex` → Codex called despite an active record (and pauses on its limit as today);
    `AI_REVIEWER=claude` → unchanged; `AI_REVIEW_ROUTE=bogus` → `Invalid AI_REVIEW_ROUTE`;
  - `ai-recover` restores the four settings from the manifest (extend the existing settings test).
- Existing `-k fallback`, `-k reviewer` and `-k recheck` tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k review_routing` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k codex_limit` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k fallback` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
DONE 2026-10-21 (opus). `workflow.py codex-limit set RESET|active` (state root `codex-limit.json`,
atomic after `check_state_root`; a symlink is replaced; `active` never writes; symlinked, garbage,
non-object, non-int or past record → exit 1). `ai-review` `run_review`: under `auto` with Codex
installed, an active record → fallback `Codex usage limit until DATE TIME (recorded)`; else
`review-route MODE BASE HEAD` (code: merge-base, plan: plan base, recheck: `-`; helper failure →
Codex); `claude …` → `review_by=claude-routed`, `Routed to Claude: REASON`, label `Claude, routed
(MODEL, effort E; REASON). Codex reviewed this branch earlier; no catch-up needed.`, no `↪`, no
`fallback-record`. A Codex limit with a known reset runs `codex-limit set` (also for
`AI_REVIEWER=codex`, which still ignores the record and pauses). `pr_body`: heading `Claude, routed,
MODEL` with a routed `[!NOTE]`. `ai_review_route_settings` (common.sh) validates `AI_REVIEW_ROUTE`
and `AI_REVIEW_SMALL_LINES` in `ai-review` and `ai-pipeline`; the four settings added to the
manifest/config/recover lists. Tests: 3 `test_codex_limit_*`, 4 `test_review_routing_*`, the
recovery settings and key-list tests extended. Test fixture: `AI_REVIEW_ROUTE=codex` by default in
`setUp` (routing has its own tests; old pipeline fixtures would otherwise route their fix rounds),
`route()` drops it. Two existing tests changed for A11: `test_claude_review_usage_limit_pauses_then_retries_codex_first`
now uses an unknown reset for the "Codex first again" case and adds the recorded case;
`test_format_retry_after_claude_fallback_attributes_the_codex_review` uses mock mode
`limit-once-unknown` (a 3-minute reset would now be remembered). Docs: README, docs/workflow.md,
usage text of both scripts; vault flow chart "Reviewer choice" + bullet, hub Log line.
Validation: -k codex_limit -k review_routing -k review_route 17 OK; -k fallback -k reviewer
-k recheck (+ claude_review_usage, recovery_restores, key_lists, pr_body, codex_usage) 55 run, 1
failure fixed as above, then -k format_retry -k limit_once -k codex_usage 11 OK; fix-round
pipeline/convergence/review_context/outcomes 21 OK; ai-check PASS, 1092 tests (787.0 s; moved to
the background by the tool timeout and waited for).

## T110 — "Reviewed by" in every review record and in the PR body (BR-14, records)
Status: DONE
Dependencies: T109
Model: sonnet

### Goal
Every published review says which family and model reviewed it and why, and the PR shows who
reviewed each round.

### Implementation notes
- Design: `.ai/current-plan.md`, "BR-14 review routing", last bullet.
- `scripts/lib/workflow.py` `publish_review` (~943) and the plan publisher (`publish-plan-review`):
  after the host header, one line `Reviewed by: WHO` for every reviewer: Codex → `Codex (MODEL,
  effort E)` from new env `AI_REVIEW_WHO` set by `ai-review` before publishing (Codex: `Codex
  (${AI_REVIEW_MODEL:-default}, effort $codex_effort)`; fallback and routed: the existing
  `AI_REVIEW_BY` text plus the reason). Keep the existing Claude `> **Reviewer: …**` label. The line
  goes before the content, after the bindings' header, so digests are taken over the final text
  (check `bind_review` and the plan binding). Re-check reports: the heading already names the
  reviewer; leave them.
- `outcome review`: optional trailing `--route REASON` (≤ 200 chars) stored as `route`;
  `ai-review` `review_records` passes `$review_reason` for routed and fallback reviews.
- `pr_body` (~4300–4320): under "Independent review", a line `Reviewed by:` followed by one bullet
  per review row of this project and branch from the outcome log (mode plan or code, oldest first,
  at most 10, newest kept): `plan: Codex (MODEL)`, `code round K: Claude, routed (MODEL): REASON`;
  when the log is unreadable or empty, the current report's `Reviewed by:` line.
- Update tests that pin the exact bytes of a published Codex report (say which in the result).
- Flow unchanged in the chart's steps; the "Reviewer choice" section gets one sentence "Every
  review and the PR say who reviewed it" (update `updated:`, hub Log line).

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-review, tests/test_workflow.py, docs/workflow.md, README.md,
vault agents-flow.md and agents.md Log

### Acceptance criteria
- Tests named `test_reviewed_by_*` in tests/test_workflow.py:
  - a Codex code review publishes `.ai/reviews/current.md` with `Reviewed by: Codex (` after the
    host header and `review-info` still verifies; a Codex plan review the same in
    `.ai/reviews/plan.md` and `plan-review-info` still says current;
  - a fallback review has both the `> **Reviewer:` label and `Reviewed by: Claude fallback`;
  - a routed review's outcome row has `route` `small low-risk fix round (10 lines)`;
  - `pr-body` with outcome rows plan/codex, code/codex, code/claude-routed lists three bullets in
    that order with the route reason; with no outcome log it shows the report's `Reviewed by:` line.
- Existing `-k pr_body`, `-k publish` and `-k review_info` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k reviewed_by` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k pr_body` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
Done. `reviewed_by_line()` writes `Reviewed by: WHO` (env `AI_REVIEW_WHO`, set by `ai-review` for
Codex, fallback and routed reviews) after the host header in `publish_review` and
`publish_plan_review`, before the binding digest. `outcome review … --route REASON` stores `route`
(≤ 200 chars); `review_records` passes the reason for non-Codex reviews. `pr_body` lists a
"Reviewed by:" bullet per plan/code row (`reviewed_by_entries`), else the report's line. No existing
test pinned the exact bytes of a Codex report (none changed). 4 new `test_reviewed_by_*` tests pass;
`-k pr_body` (5) OK. Gate: first run had one failure, `test_gate_lock_wait_runner_waits_for_the_session_gate`
("could not record the task in the run manifest"), which passes alone and is unrelated; the rerun
passed (OK).

## T111 — Self-check fixtures never register in the real run registry (FL-33, tests)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
A whole self-check leaves no fixture run in the host's real `ai-toolkit` registry, and the
parallel runner fails if one appears.

### Implementation notes
- Design: `.ai/current-plan.md`, "FL-33 isolated test state"; assumption A13.
- New `tests/isolation.py`: at import, unless `AI_STATE_DIR` is already a path under
  `tempfile.gettempdir()`, create `tempfile.mkdtemp(prefix='ai-test-state-')`, set
  `os.environ['AI_STATE_DIR']` to it and `os.environ['XDG_STATE_HOME']` to a sibling dir, and
  remove both at exit (`atexit`, `shutil.rmtree(..., ignore_errors=True)`). Import it first in
  `tests/test_workflow.py`, `tests/test_dashboard.py` and `tests/test_observation.py`.
- Find the leaking tests: those that clear `AI_STATE_DIR` (grep `AI_STATE_DIR=''`, ~2348, ~2373)
  or build an environment from scratch without it; make each pass a temp `XDG_STATE_HOME` or
  `AI_STATE_DIR` explicitly. Name every one you changed in the result.
- `tests/run_parallel.py`: before building the workers' env, compute the caller's real registry
  directory the same way `state_root()` does (from the caller's environment) + `/pipelines`; after
  the batches, list it (skip if missing; do not follow symlinks; read each entry as the dashboard
  does or by its recorded checkout path) and fail with `self-check registered fixture runs in the
  real registry: PATH…` (exit non-zero) when an entry names a checkout under the suite's temp dir
  (`self.tmpdir` / the chosen `ai-tests-*` dir or `tempfile.gettempdir()` for the default).
  Entries for other paths are ignored (real pipelines may register during the suite).
- Flow unchanged; say so in the result.

### Likely affected modules
tests/isolation.py (new), tests/test_workflow.py, tests/test_dashboard.py,
tests/test_observation.py, tests/run_parallel.py

### Acceptance criteria
- Tests named `test_state_isolation_*` in tests/test_workflow.py:
  - at import `os.environ['AI_STATE_DIR']` and `os.environ['XDG_STATE_HOME']` are under the temp
    dir, and a child `python3 workflow.py pipeline-register` started with plain `os.environ`
    writes under them;
  - `run_parallel.py`'s registry guard, called on a fake real registry dir holding an entry for a
    checkout under the suite temp dir, reports it and returns failure; an entry for another path
    passes; a missing registry passes (unit-test the guard function directly).
- The tests changed for the leak still pass; `-k dashboard` and `-k observation` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k state_isolation` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k dashboard` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
- New `tests/isolation.py` (temp `AI_STATE_DIR` and `XDG_STATE_HOME`, removed at exit; kept when
  `AI_STATE_DIR` is already under the temp dir), imported first in test_workflow, test_dashboard
  and test_observation.
- No individual test needed changing: the ones clearing `AI_STATE_DIR` (`''`) already pass a temp
  `XDG_STATE_HOME`, and the others copy `os.environ`, which is now isolated.
- `tests/run_parallel.py`: `real_registry`, `registry_leaks`, `registry_problem`; main() fails
  with `self-check registered fixture runs in the real registry: PATH…` after the batches.
- Tests `test_state_isolation_env_under_temp_and_child_registers_there` and
  `test_state_isolation_registry_guard` pass; `-k dashboard` (108) and `-k observation` (76) pass.
- Flow unchanged.
- Gate: the session timed out (exit 124) before committing and recovery had used its two tries; mission control ran `.ai/bin/ai-check` on this tree: 1098 tests, 0 failing, 766.4 s, OK (2026-10-21).

## T112 — Docs, flow chart and handoff audit (batch 9)
Status: DONE
Dependencies: T101, T102, T103, T104, T105, T106, T107, T108, T109, T110, T111
Model: haiku

### Goal
README, docs/workflow.md, the vault flow chart and the handoff match the code of this batch.

### Implementation notes
- Check against the code: README (pre-flight and rulings, fresh retry and model raise, review
  routing and the four new settings, Codex limit memory, "Reviewed by"), docs/workflow.md (the
  same, plus the helper list: `tasks preflight`, `run-manifest ruling`, `ruling-row`,
  `disposition-ruling`, `flow-line-ruling`, `attempt-info`, `review-route`, `codex-limit`, the
  `rulings` manifest field). Wording fixes only; a behaviour mismatch is recorded in the handoff,
  not fixed here.
- Vault `agents-flow.md`: the T103, T104, T105, T107, T109 and T110 changes are present and agree.
  Fix the wording if needed (update `updated:` then) and append one hub Log line.
- `.ai/handoff.md`: "What has been implemented", "Validation run", "## Flow chart" (one line
  starting `Flow chart updated`), and "Manual testing for the human" with `### Needs you` and
  `### Covered by automated tests` (each test group with its task). `.ai/state.md` counts are
  runner-managed; do not hand-edit them.

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, vault agents-flow.md and agents.md Log

### Acceptance criteria
- `-k Docs` and `-k flow_this_repo` pass; the handoff names every new test group of T101–T111.
- The result lists every mismatch found and how it was fixed or recorded.

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the background, waited for (BATCH 8 GATE RULE in the header).

### Result / notes
Done. Audit of README.md, docs/workflow.md, the vault flow chart and the handoff against the code.
Helpers (`tasks preflight`, `run-manifest ruling`, `ruling-row`, `disposition-ruling`,
`flow-line-ruling`, `attempt-info`, `review-route`, `codex-limit`) and the four routing settings
exist and match the docs. Vault `agents-flow.md` agrees (Reviewer choice, Pre-flight, Rulings,
Fresh retry, Review routing bullets); no change. Mismatches found and fixed:
- README lacked the "Reviewed by:" lines (T110): added a paragraph after the routing text.
- README lacked the FL-33 test isolation (T111): added a paragraph in the test-harness section.
- Handoff: T111 missing from "What has been implemented", no validation entries for T108–T111,
  "Next action" still said T111, and the live `ai-dashboard` check (FL-33) moved to covered tests
  as `test_state_isolation_*`; flow-chart paragraph updated.
Vault hub Log: one dated T112 line in `agents.md`.
Targeted: `-k Docs` 3 OK; `-k flow_this_repo` 1 OK; `-k state_isolation` 2 OK.
Gate: `.ai/bin/ai-check` (background): 1098 tests OK, 770.0 s, exit 0.

## T113 — Registry guard reads the caller's registry before discovery (review M1, FL-33)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
`tests/run_parallel.py` checks the caller's real registry, not the temp registry that
`tests/isolation.py` installs when discovery imports the test modules.

### Implementation notes
- Review round 1, M1: `main()` calls `collect(start_dir)` (in-process `unittest` discovery, which
  imports every test module and with it `isolation`, which rewrites `os.environ['AI_STATE_DIR']`
  and `XDG_STATE_HOME`) before `registry = real_registry()`. So the guard lists the temp registry.
- Capture `real_registry()` from the caller's environment before `collect()`, e.g. as the first
  step of `main()` after argument parsing, or from a copy of `os.environ` taken at module import
  of `run_parallel` (that is safe only if `isolation` cannot have been imported first, so the
  start of `main()` is simpler). Leave the workers' env and the rest of the guard unchanged.
- Flow unchanged (test harness only); say so in the result.

### Likely affected modules
tests/run_parallel.py, tests/test_workflow.py

### Acceptance criteria
- A regression test `test_state_isolation_guard_reads_the_registry_before_discovery` in
  tests/test_workflow.py runs `run_parallel.main()` (or the script as a subprocess) with
  `AI_STATE_DIR` pointing at a fake "real" registry outside the suite temp dir, a discovery that
  imports `isolation` (or that changes `AI_STATE_DIR` the way it does), and a leaked entry in the fake
  registry. It asserts that the guard reports that entry and exits non-zero. It fails on the
  current ordering.
- The existing `test_state_isolation_*` tests still pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k state_isolation` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Done. `main()` in tests/run_parallel.py now captures `real_registry()` first (before `worker_count()`
and `collect()`), so the guard lists the caller's registry, not the one `isolation` installs during
discovery. Workers' env and the rest of the guard are unchanged. Flow unchanged (test harness only).
New `test_state_isolation_guard_reads_the_registry_before_discovery` runs the script as a subprocess
with a fake host registry holding a leaked entry and a fake test module that rewrites `AI_STATE_DIR`
on import; it asserts a non-zero exit and the leak path in the output. Verified it fails with the old
ordering (temporarily restored) and passes with the fix.
Targeted: `-k state_isolation` 3 OK.
Gate: `.ai/bin/ai-check`: 1099 tests OK, 795.5 s, exit 0 (the harness moved it to the background past 600 s; waited for it).

## T114 — Queue ruling claims every task the repair moves (review M2, BR-02, A2)
Status: DONE
Dependencies: none
Model: opus

### Goal
A pre-flight queue repair claims `queue-order:<ID>` for every task whose position changes, not
only for tasks with late dependencies. So a later repair that would move an already-moved task
is refused and leaves the queue unchanged (A2).

### Implementation notes
- Review round 1, M2: `tasks_preflight` (`scripts/lib/workflow.py`) computes `moved`, but it prints
  `queue-order ID placed after …` only for `task_id in order if late[task_id]`.
  `ai_queue_ruling` (`scripts/lib/common.sh`) claims only the IDs it parses from those lines.
  Prerequisites and intervening tasks move without a claim.
- Make the claimed set equal to `moved`: e.g. emit one `queue-order ID …` line per moved task
  (with `placed after DEPS` for late-dependency tasks and a neutral wording such as `moved` for
  the others). Or add a separate claim line kind that `ai_queue_ruling` claims but that is kept
  out of the Ruling rows and notification text. Keep `ai_ruling_rows` and the 🔧 summary
  readable. Update the T102/T103 tests that pin the exact output lines.
- All claims stay before the rewrite (a refused claim changes nothing).
- Flow unchanged in shape. If the vault Rulings bullet says "per task with a late dependency",
  correct it and add a hub Log line.

### Likely affected modules
scripts/lib/workflow.py, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_preflight_helper_*`: queue `T001, T002, T003` with T001 depending on T002 prints a claimable
  line for both T001 and T002.
- Regression `test_preflight_pipeline_indirectly_moved_task_repeat_stops`: after a first repair
  that moved T001 and T002, a second queue fault that would move T001 again (with T002 or T003 as
  the late-dependency task) is refused: no new ruling row, `.ai/tasks.md` bytes unchanged, and
  the run stops as the existing `_same_ruling_twice_stops` does.
- Existing `test_preflight_*` and `test_ruling_*` groups pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k preflight` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k ruling` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Mission control 2026-10-21 12:35Z: returned to TODO (was BLOCKED on the gate only; the run stopped). The fix is committed (3d84f5a). Verify it against the acceptance criteria, run the targeted checks, then run `.ai/bin/ai-check` once in the background and wait for its result WITHOUT editing or committing anything until it finishes (an earlier attempt edited files during the gate and got "Validation modified project content"). Model raised to opus because the task failed once.

2026-10-21 (opus, re-run): verified 3d84f5a against the criteria with no further source change.
`tasks preflight` prints `queue-order T placed after …` for late-dependency tasks and
`queue-moved T` for every other moved task; `ai_queue_ruling` claims both as `queue-order` before
the rewrite, and `ai_ruling_rows` skips `queue-moved` (no Ruling row; the 🔧 summary lists only
late-dependency tasks). `test_preflight_helper_claims_indirectly_moved_tasks` (T001→T002, T003
prints lines for T001 and T002) and `test_preflight_pipeline_indirectly_moved_task_repeat_stops`
(T002 already claimed: refused, tasks.md bytes and HEAD unchanged, no Ruling row, no 🔧) pass.
Evidence: `-k preflight` Ran 16 OK; `-k ruling` Ran 18 OK; `.ai/bin/ai-check` PASS, 1103 tests,
764.1 s, with no edits during the gate. Vault Rulings text already says "one ruling per changed
task" and needed no correction; flow unchanged.

## T115 — Routed reviews default to opus (review N1, BR-14, A12)
Status: DONE
Dependencies: none
Model: opus

### Goal
A routed Claude review (a small low-risk fix round) runs on opus as A12 specifies, even when the
queue holds an earlier, already reviewed opus task. `AI_CLAUDE_REVIEW_MODEL` still overrides the
model.

### Implementation notes
- Review round 1, N1: `scripts/ai-review` calls `claude_model` for routed reviews too, and that
  function calls `review-risk`, which scans every task (DONE included). So an earlier opus task or
  a risky title picks `claude-fable-5-1`.
- When `routed` is set, use `claude_model=claude-opus-5-5`, `claude_risk='routed'` (or similar),
  then apply the `AI_CLAUDE_REVIEW_MODEL` override and the effort validation as `claude_model` does
  today. Fallback and `AI_REVIEWER=claude` reviews keep the full-queue risk selection.
- Flow unchanged. If the vault "Review routing" bullet names the model, check that it says opus.

### Likely affected modules
scripts/ai-review, tests/test_workflow.py

### Acceptance criteria
- Regression `test_review_routing_routed_review_uses_opus_after_an_opus_task`: with an earlier
  DONE opus task already reviewed and a one-line low-risk fix round, the routed Claude call gets
  `--model claude-opus-5-5`, and `Reviewed by:` names it. With `AI_CLAUDE_REVIEW_MODEL=x-model`,
  the call gets `x-model`. A fallback review on the same queue still picks `claude-fable-5-1`.
- Existing `test_review_routing_*` and `test_reviewed_by_*` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k review_routing` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k reviewed_by` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Mission control 2026-10-21 12:35Z: returned to TODO (was BLOCKED on the gate only; the run stopped). The fix is committed (a13ffad). Verify it against the acceptance criteria, run the targeted checks, then run `.ai/bin/ai-check` once in the background and wait for its result WITHOUT editing or committing anything until it finishes (an earlier attempt edited files during the gate and got "Validation modified project content"). Model raised to opus because the task failed once.
BLOCKED on the gate only. Implemented: `claude_model` in `scripts/ai-review` uses opus with risk `routed` when a
routed review is set (the `AI_CLAUDE_REVIEW_MODEL` override and effort validation still apply). Added
`test_review_routing_routed_review_uses_opus_after_an_opus_task` and
`test_review_routing_routed_review_honours_the_model_override`; `routed_pipeline` takes a queue and env.
`-k review_routing` ran 6 tests with only the since-fixed test assertion failing; the new routed-opus test then
passes alone (`-k routed_review_uses_opus`, Ran 1, OK). `.ai/bin/ai-check` exceeded the 600000 ms foreground
timeout with no output, so the full gate result is unknown. The `reviewed_by` targeted run was not done.
DONE (2026-10-21 re-run, opus): verified a13ffad against the criteria (routed branch in `claude_model` sets opus
before the `AI_CLAUDE_REVIEW_MODEL` override; the non-routed `AI_REVIEWER=claude` review on the same queue still
picks `claude-fable-5-1`). Targeted: `-k review_routing` Ran 6 OK; `-k reviewed_by` Ran 4 OK.
Gate: `.ai/bin/ai-check` Ran 1103 tests, OK, exit 0 (766.5 s; the harness moved it to the background past 600 s;
no edits until it finished). Vault flow chart routed node now says "(opus)" instead of "(usual model)".

## T116 — Routing never counts fix rounds from commit subjects (review M3, BR-14, A10)
Status: DONE
Dependencies: none
Model: opus

### Goal
`review-route` treats a missing host fix-round store as zero eligible fix rounds, so a
triage commit subject alone (agent-controlled Git history) can never route a review to Claude.
Missing or unreadable host records keep Codex, as A10 requires.

### Implementation notes
- Review round 2, M3: `route_fix_rounds` (`scripts/lib/workflow.py`, ~line 3712) falls back to
  counting `TRIAGE_COMMIT` subjects in `BASE..HEAD` when `fix_round_records()` returns `None`.
  With a missing store and a matching subject, `review_route_reason` returns
  `claude small low-risk fix round …`.
- Make `route_fix_rounds` return 0 when `fix_round_records()` is `None` (no Git-subject
  fallback). Keep the legacy migration in `fix-rounds init`/`count` (around the
  `TRIAGE_SUBJECT` handling, ~line 1316) unchanged: it is a separate path and not routing
  eligibility. Fix the docstring.
- Check that the normal pipeline path (store written by the host at triage) still routes round 2
  to Claude: `test_review_routing_pipeline_small_low_risk_fix_round_goes_to_claude` must still pass.
- Flow unchanged. Only update the vault "Review routing" bullet if it mentions commit subjects.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Regression `test_review_route_triage_subject_without_host_record_stays_on_codex`: missing
  fix-round store, a commit with the triage subject, an earlier host Codex code review of this
  branch and a one-line low-risk diff → `codex first full code review` (or another `codex …`
  reason), never `claude …`. With a host store holding that round, the same history returns
  `claude small low-risk fix round …`.
- `fix-rounds` legacy migration tests still pass unchanged.
- Existing `test_review_route_*` and `test_review_routing_*` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k review_route` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k fix_round` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
DONE 2026-10-21 (claude opus). `route_fix_rounds` returns 0 when `fix_round_records()` is `None`
(no `TRIAGE_COMMIT` subject fallback) and only counts host records reachable in BASE..HEAD;
docstring fixed. `fix-rounds init`/`count` legacy migration untouched. `route_project` gained
`record=True`. Regression `test_review_route_triage_subject_without_host_record_stays_on_codex`:
missing store + triage subject + host Codex code review + one-line diff → `codex first full code
review` and no store written; after `fix-rounds record` → `claude small low-risk fix round (1
lines)`. docs/workflow.md routing paragraph names the rule. Evidence: `-k review_route` Ran 10 OK;
`-k fix_round` Ran 21 OK; `-k review_routing` Ran 6 OK (incl. the pipeline round-2 test);
ai-check PASS, 1104 tests, 816.3 s (no edits during the gate). Flow unchanged; the vault flow
note already says counts never come from commit subjects.

## T117 — Test isolation sets AI_STATE_DIR and XDG_STATE_HOME independently (review N2, FL-33, A13)
Status: DONE
Dependencies: none
Model: opus

### Goal
`tests/isolation.py` ensures both `AI_STATE_DIR` and `XDG_STATE_HOME` point under the temp dir,
each checked on its own, so a temporary `AI_STATE_DIR` with an unset or external
`XDG_STATE_HOME` still gets an isolated XDG state for the tests and their children.

### Implementation notes
- Review round 2, N2: the module checks only `AI_STATE_DIR`; when it is already under the temp
  dir it leaves `XDG_STATE_HOME` untouched (unset or external), and
  `test_state_isolation_env_under_temp_and_child_registers_there` then raises
  `KeyError: 'XDG_STATE_HOME'`.
- Apply `under_temp` to each variable separately: keep a value already under the temp dir
  (the parallel runner's workers inherit both), otherwise create its own `mkdtemp` and register
  its cleanup. Update the module docstring.
- Test-only; flow unchanged.

### Likely affected modules
tests/isolation.py, tests/test_workflow.py

### Acceptance criteria
- Regression `test_state_isolation_temp_ai_state_with_missing_or_external_xdg`: running the
  isolation module in a child with `AI_STATE_DIR` under the temp dir and (a) no `XDG_STATE_HOME`,
  (b) `XDG_STATE_HOME` outside the temp dir, leaves `AI_STATE_DIR` unchanged and sets
  `XDG_STATE_HOME` to a directory under the temp dir. Both already under the temp dir → both kept.
- Existing `test_state_isolation_*` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k state_isolation` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Mission control 2026-10-21 20:45Z: returned to TODO (was BLOCKED on the gate only; the run stopped). The fix is committed (905bf68). Verify it against the acceptance criteria and run the targeted tests. Do NOT run the full `.ai/bin/ai-check` in the foreground: it takes about 14 minutes, longer than the 10-minute tool limit. Run it once with run_in_background and wait for the result without editing or committing anything until it finishes; or, if the targeted tests pass, mark the task DONE and let the runner's own gate after the session verify it.
2026-10-21 (opus): verified 905bf68 against the criteria: `tests/isolation.py` applies `under_temp` to `AI_STATE_DIR` and `XDG_STATE_HOME` separately, each with its own `mkdtemp` and cleanup; docstring updated. Regression `test_state_isolation_temp_ai_state_with_missing_or_external_xdg` covers unset, external and both-under-temp XDG. Targeted `-k state_isolation`: Ran 4 tests, OK. Full `.ai/bin/ai-check` not run in this session (≈816 s, beyond the 600 s tool limit; the runner prompt forbids backgrounding it); the runner's post-session gate is the gate evidence. Test-only; flow unchanged.

## T118 — Advisory scans write the overlap report (review N3, BR-02, A5)
Status: DONE
Dependencies: none
Model: opus

### Goal
Every successful pre-flight scan that prints overlap lines also writes (or refreshes)
`.ai/local/preflight.md`, as A5 requires, whether or not a queue repair or commit happens.

### Implementation notes
- Review round 2, N3: `ai_queue_ruling` (`scripts/lib/common.sh`) returns after
  `tasks preflight --dry-run` when there is nothing to repair, and `scripts/ai-run` (planning
  ~line 447, plan revision ~line 563) only uses `--dry-run`; `tasks_preflight`
  (`scripts/lib/workflow.py`, ~line 718) writes `preflight.md` only when not a dry run.
- Simplest fix: let `tasks preflight --dry-run` still write the ignored advisory report (it is not
  a queue change), keeping the queue untouched; or add a `--report` mode that writes only the
  report and call it on the no-repair paths. Keep the unsafe `.ai/local` skip quiet (as
  `_reports_overlaps_between_todo_tasks` expects). A scan with no overlaps writes an empty report
  so a stale one is not left behind. No run-log row or commit just for a report (A5).
- Update docs/workflow.md if it says the report is written only on repair. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, scripts/lib/common.sh, scripts/ai-run, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Regression `test_preflight_helper_valid_queue_writes_the_overlap_report`: a valid queue with
  two overlapping TODO tasks leaves `.ai/tasks.md` bytes unchanged and writes the overlap lines to
  `.ai/local/preflight.md`; after removing the overlap, a second scan refreshes it (no stale line).
- Regression `test_preflight_pipeline_no_repair_saves_the_overlap_report`: a pipeline start with a
  valid overlapping queue makes no ruling commit and no Ruling row, and `.ai/local/preflight.md`
  holds the printed overlap lines.
- Existing `test_preflight_*` and `test_ruling_*` pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k preflight` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Mission control 2026-10-21 20:45Z: returned to TODO (was BLOCKED on the gate only; the run stopped). The fix is committed (38f671c). Verify it against the acceptance criteria and run the targeted tests. Do NOT run the full `.ai/bin/ai-check` in the foreground: it takes about 14 minutes, longer than the 10-minute tool limit. Run it once with run_in_background and wait for the result without editing or committing anything until it finishes; or, if the targeted tests pass, mark the task DONE and let the runner's own gate after the session verify it.
Implemented: `tasks_preflight` (scripts/lib/workflow.py) now writes `.ai/local/preflight.md` on
`--dry-run` too (empty file when no overlaps); queue still untouched on dry run. docs/workflow.md
updated; added the two named regressions and adjusted two existing dry-run assertions.
Evidence: `-k preflight` Ran 18 tests OK; `-k ruling` Ran 18 tests OK.
BLOCKED: `.ai/bin/ai-check` exceeded the 600000 ms foreground timeout (same as T117), so no green
gate was obtained; a second invocation said "Validation is already running". Human: rerun the gate.
2026-10-21 rerun (opus): verified 38f671c against the criteria (dry-run writes the report, empty
when no overlaps, queue bytes unchanged; both named regressions present). `-k preflight` Ran 18
tests OK; `-k ruling` Ran 18 tests OK. Full ai-check (≈816 s > 600 s tool limit) left to the
runner's post-session gate. Flow unchanged; docs/workflow.md already updated in 38f671c.

## T301 — Run record helper: schema 1, start, show, alive, host lock, retention (RC-01 G3, helper)
Status: DONE
Dependencies: none
Model: opus

### Goal
`workflow.py run-record` creates one schema-versioned host record per run under
`<binding dir>/runs/`, with a `current` pointer, the starter's process identity, a bounded host
lock for every write and bounded retention; `start` prints the run id. The lifecycle actions
(own, resume, pause, end, stop requests) are T315. No caller yet.

### Implementation notes
- Design: `.ai/current-plan.md` "Run record, schema 1" (T301 actions). Records beside `run.json`
  (`binding_dir()`, `scripts/lib/workflow.py` ~1454): `runs/<id>.json`, `runs/current` (one line,
  the id), `runs/.lock`.
- `start KIND BRANCH BASE_REF BASE_SHA --pid PID -- ARGS…` (KIND `pipeline` or `ai-run`; `-` for
  an absent base; id `<UTC %Y%m%dT%H%M%SZ>-<pid>-<seq>`, format `^\d{8}T\d{6}Z-\d{1,10}-\d{1,9}$`,
  where `seq` is 1 + the highest `seq` among the valid record names in `runs/`, chosen under the
  lock, and the record file is created with `O_CREAT|O_EXCL` (an existing name → fail, never
  replace; plan review P15: two starts with the same pid in one second must not collide); the
  UTC stamp comes from one small function (`run_stamp()`) so tests can fix the clock; launcher and
  log from spec B6: `AI_LAUNCHER` validated `^[a-z0-9._-]{1,32}$` else `systemd` when
  `INVOCATION_ID` is set, else `terminal` when `os.isatty(0)`, else `other`; `AI_RUN_LOG` when
  absolute and without NUL or newline, else `os.readlink('/proc/<pid>/fd/1')` when it names a
  regular file, else null): under the lock, writes the record, then `current`, prunes, and
  prints the id on stdout (nothing else on stdout; callers keep it as `AI_RUN_ID`).
- `current` (prints the id; exit 1 when none or invalid), `show [ID]` (prints the JSON; default
  the current one), `alive [ID]` (exit 0 when the recorded pid exists, is not a zombie and has
  the recorded start ticks).
- Process identity from `/proc/<pid>/stat` (parse after the last `)`: state, pgid (field 5), sid
  (field 6), start ticks (field 22)); `os.getpgid`/`os.getsid` are acceptable for pgid and sid.
- Every write: `fcntl.flock` on `runs/.lock` (blocking, but bounded: `LOCK_NB` retries for 5 s,
  then fail `run record is locked`), then `atomic()` (the new record of `start`: exclusive
  creation, above). Retention: after `start`, keep the 20 records with the highest `seq` (compared
  as numbers); never remove the current one; ignore names that are not `<id>.json`.
- Validation on read: a dict with `schema == 1` and the field types of the plan; anything else
  (unknown schema, wrong types, symlink, > 64 KB, a `current` that is not an id) is "no record"
  (`current`/`show` exit 1).
- Keep the lock, the reader and the identity function as plain module functions (`run_lock`,
  `read_run`, `process_identity`): T315, T305 and `run-stop` (T308) use them.
- Register `run-record` in `main()`. Flow unchanged (no caller).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- `test_run_record_start_and_show`: `start pipeline fix/x origin/main <sha> --pid <own pid> --
  --approved --base main` prints only the id and writes schema 1 with the exact argv, base,
  branch, launcher `other` (`AI_LAUNCHER=mission-control` → `mission-control`, invalid value →
  `other`), log null or the `AI_RUN_LOG` path, process identity equal to `/proc/self/stat`,
  outcome `running`; `current` prints that id; `show` prints the record.
- `test_run_record_ids_unique_with_fixed_clock`: in process (module loaded with `importlib`,
  `run_stamp` patched to one fixed value), two starts with the same `--pid` give two different ids
  and two records; the first record's bytes are unchanged by the second start.
- `test_run_record_retention_keeps_twenty`: 23 starts with the same fixed clock and pid leave 20
  records (the 20 highest `seq`), the current one included.
- `test_run_record_alive_identity`: own pid alive; a wrong start-ticks value, a dead pid and a
  record with an unknown schema → not alive / no record.
- `test_run_record_lock_is_bounded`: with `runs/.lock` held by the test, `start` fails within the
  scaled bound with `run record is locked` and writes no record and no `current`.
- `test_run_record_invalid_records`: a symlinked record, a 65 KB record and a `current` holding
  `../x` → `current` and `show` exit 1.

### Validation
Targeted: `python3 -m unittest discover -s tests -k run_record` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (opus): `scripts/lib/workflow.py` gains `run-record start|current|show|alive` (after
`run_manifest`) with module functions `run_stamp`, `runs_dir`, `process_identity`, `run_lock`,
`read_run`, `start_run` for T315/T305/T308. Ids `<stamp>-<pid>-<seq>`, record created with
`O_CREAT|O_EXCL|O_NOFOLLOW`, `current` via `atomic()`, retention to the 20 highest `seq`, bounded
flock (5 s, `run record is locked`), reads refuse symlinks, non-regular files, > 64 KB, wrong
schema/types and a `current` that is not an id. Extra checks beyond the criteria: KIND outside
`pipeline`/`ai-run`, a half `-` base and `--pid 0` fail and write nothing; BASE_SHA must be 40 or
64 hex. Six tests named in the criteria added (`tests/test_workflow.py`, end of `ToolkitTest`;
fixtures are own `sleep` children in their own session, the zombie case included).
`docs/workflow.md` "Durable records" describes the helper. Flow unchanged (no caller).
Targeted `-k run_record`: Ran 9 tests OK. Full `.ai/bin/ai-check`: Ran 1113 tests OK (1229 s).

## T315 — Run record lifecycle bound to the run id and process identity (RC-01 G3, plan review P5)
Status: DONE
Dependencies: T301
Model: opus

### Goal
The lifecycle actions `own`, `resume`, `pause`, `end`, `request-stop`, `settle-stop` and
`stop-requested` each name their run and are checked under the host lock, so a stopper or a late
writer of run A can never change run B, and a reused pid never passes for the owner. No caller
yet.

### Implementation notes
- Design: `.ai/current-plan.md` "Run record, schema 1" (T315 lifecycle actions) and the round-1
  rule "bound to the run"; spec FR-1, B17, B18. Use T301's `run_lock`, `read_run`,
  `process_identity`.
- Common rule: under `runs/.lock`, refuse with exit 3 and no change ("not the owner of run ID")
  when ID is not `current`, the record is invalid, or the identity check of the action fails.
  "Ended" = outcome other than `running` and `paused`; an ended record never changes again (so a
  first `human_stop` is kept).
- `own --run ID --pid PID --launcher NAME` (recovery) and `resume --run ID --pid PID` (resumed
  pipeline): refuse a stop request, an ended record, and a recorded process that is alive and is
  not PID; then `process` = PID's identity, outcome `running`; `own` sets `launcher`, `resume`
  adds 1 to `resumes`.
- `pause --run ID --pid PID` (outcome `paused`, not ended) and `end --run ID --pid PID OUTCOME
  [DETAIL]` (OUTCOME `finished`, `stopped`, `human_stop`, `crashed`; sets `ended`): the recorded
  process must be PID with PID's current start ticks. DETAIL: one line, ≤ 200 characters, `|`
  removed.
- A pending stop request decides the terminal outcome (plan review round 3, P16): under the same
  lock, `end … stopped` on a record whose `stop_requested` is set stores `human_stop` instead
  (the caller's DETAIL kept), so the owning runner (a stand-alone `ai-run`, an `ai_die` or an
  `ai-recover` `escalate()` racing a `--stop`) never ends a stop-requested run as `stopped`.
  `finished` and `crashed` are stored as given. Ended records stay immutable.
- `request-stop --run ID --via VIA [--expect-pid P --expect-ticks T]` (VIA `ai-pipeline --stop`
  or `signal`): refuses an ended record and, with `--expect-*`, a recorded process that differs;
  a second request keeps the first.
- `settle-stop --run ID` (also a Python function for `run-stop`): only with a stop request, the
  recorded process not alive and the record not ended → `end human_stop`; else exit 3.
- `stop-requested --run ID`: exit 0 when a stop is requested or the outcome is `human_stop`, 1
  when not, 3 when ID is not current or invalid.
- Flow unchanged (no caller).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- `test_run_record_end_keeps_human_stop`: `end --run ID --pid <own pid> human_stop` sets `ended`
  and the outcome; a second `end … stopped` exits 3 and keeps `human_stop`; `pause` then `end
  finished` works and `pause` leaves `ended` null.
- `test_run_record_end_after_stop_request_is_human_stop` (P16): `request-stop --run ID --via
  'ai-pipeline --stop'`, then `end --run ID --pid <own pid> stopped "exit 143"` exits 0 and
  stores outcome `human_stop` with that detail; a second `end … stopped` exits 3, bytes
  unchanged; on another record `request-stop` then `end … finished` stores `finished`.
- `test_run_record_own_and_resume`: `own` with a fixture child's pid replaces `process`, sets
  launcher `ai-recover`, keeps `resumes` 0; `resume` → `resumes` 1; `own` is refused (exit 3,
  bytes unchanged) with a stop request, after `end`, and while another live process is recorded.
- `test_run_record_stop_request_identity`: `request-stop --expect-pid` with wrong start ticks →
  exit 3; with the right ones → `stop-requested` exit 0; `settle-stop` while the process lives →
  exit 3, after it died → `human_stop`.
- `test_run_record_interleaving_never_touches_another_run`: start A, `request-stop A`, start B
  (now current); then `end --run A`, `request-stop --run A`, `own --run A`, `settle-stop --run A`
  all exit 3 and B's record bytes are unchanged; `end --run B --pid <a pid that is not B's>` →
  exit 3.

### Validation
Targeted: `python3 -m unittest discover -s tests -k run_record` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Mission control 2026-10-22 01:35Z: returned to TODO (BLOCKED only on the gate time limit; work committed 939c66f). Verify, run targeted checks, do not run the full gate in the foreground; the runner's gate decides.
- 2026-10-22 (claude, opus): implemented and committed in 939c66f: `run-record own|resume|pause|
  end|request-stop|settle-stop|stop-requested` plus `settle_stop()` in `scripts/lib/workflow.py`,
  the five acceptance tests in `tests/test_workflow.py`, docs/workflow.md "Durable records".
  Targeted `python3 -m unittest discover -s tests -k run_record`: Ran 14 tests, OK (47.9 s).
- BLOCKED on the gate only (FL-32 again): `.ai/bin/ai-check` ran 600 s in the foreground, was
  moved to the background and stopped at the background limit (~1200 s total) with no result;
  T301's gate took 1229 s. The runner rules forbid restarting it in the background. Code looks
  complete; next step: rerun `.ai/bin/ai-check` outside the session limit (or let the runner's
  checkpoint validation run it) and, on PASS, set T315 DONE.
- 2026-10-22 (claude, opus, rerun): re-verified 939c66f against the five acceptance criteria and
  the implementation notes (exit 3 under `runs/.lock` for non-current/invalid/identity failures;
  ended records immutable; `end stopped` after a stop request stores `human_stop`). Targeted
  `-k run_record`: Ran 14 tests, OK (51.9 s). Full gate not run in session per mission control;
  the runner's checkpoint gate decides. DONE.

## T305 — Escalation record helper: schema 1, redaction, allowed answers (RC-01 G9, helper)
Status: DONE
Dependencies: T315
Model: opus

### Goal
`workflow.py escalation` writes, shows and clears one schema-versioned host record that says why
the run waits for a human, with redacted evidence and the allowed answers as argument arrays;
it is written only for the current run, and every new run record and automatic resume removes
it. No other caller yet.

### Implementation notes
- Design: `.ai/current-plan.md` "G9". Path `<binding dir>/escalation.json`; pending hint
  `<binding dir>/escalation-hint.json`. Both written with `atomic()` under T301's `runs/.lock`;
  read only as regular files ≤ 64 KB.
- `write KIND STAGE --run ID [--task ID]… [--finding ID]… [--review PATH]`: refuses (exit 3,
  nothing written) when ID is not the current run (plan review P5). KIND from the fixed list
  (`plan_review_limit`, `fix_round_limit`, `task_blocked`, `needs_human_question`, `validation`,
  `usage_limit`, `crash`, `human_stop`, `other`; anything else → `other`). KIND `other` is
  refined: a run record with `stop_requested` set or outcome `human_stop` → `human_stop` (plan
  review round 3, P16; any pending hint of that run is removed), else a pending hint of the same
  run overrides it and adds its tasks and findings (then is removed), else stage `validation` →
  `validation`, a stage starting with `crash` → `crash`.
  Task ids `^T\d{3,}$`, finding ids `^[A-Z]{1,3}\d{1,4}$`, review path one of
  `.ai/reviews/plan.md`, `.ai/reviews/current.md`, `.ai/reviews/recheck.md`. Evidence:
  `last_error` from `.ai/local/last-error` through `local_dir_fd` (regular file only), redacted
  (spec B10), one line, ≤ 400 characters; `log` from the run record. `run` and `branch` from the
  run record.
- A repeated write never loses the classification (plan review P13): when the existing record
  belongs to the same run and has a kind other than `other`, a write whose kind is still `other`
  after the refinement above leaves the record unchanged (exit 0). An explicit specific kind
  (e.g. `human_stop`) replaces it. This is the backstop; the shell side has one writer per
  shutdown chain (T320).
- Answers per kind as in the plan, built only from the current run record named by `--run`
  (its `kind` and `argv`), never from `run.json` (plan review round 3, P18: the manifest belongs
  to the last pipeline start, which may be an unrelated earlier run). Run kind `pipeline` →
  `resume` is `.ai/bin/ai-pipeline` + the record's argv, and `resume_more_rounds` /
  `resume_skip_plan_review` are derived from that argv. Run kind `ai-run` → `resume` is
  `.ai/bin/ai-run` + the record's argv only when that argv contains `--approved` and none of
  `--plan`, `--triage`, `--revise-plan`; otherwise no `resume` answer; never a pipeline-only
  answer (`resume_more_rounds`, `resume_skip_plan_review`). `resume_more_rounds` only when the
  recorded `--max-fix-rounds` (default 2) + 1 ≤ 5. `usage_limit` adds `not_before` (epoch) from
  `.ai/local/limit-stop` when valid.
- `hint KIND --run ID [--task ID]… [--finding ID]…` (same current-run rule), `show` (prints the
  JSON; exit 1 when none or invalid), `clear` (removes record and hint; no error when absent).
- `run-record start` and `run-record resume` (T301, T315) call the clear after they publish
  (plan review P7: a fresh stand-alone `ai-run` clears it too).
- Register `escalation` in `main()`. Flow unchanged (no caller beyond the clear).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- `test_escalation_record_kinds_and_answers`: one write per kind gives schema 1, the kind, stage,
  tasks, and answers whose `argv` are arrays starting with `.ai/bin/`; `task_blocked` with two
  tasks has `retry_task`, `skip_task`, `set_model` for each plus `resume` with the recorded args;
  an unknown kind is stored as `other`; `other` with stage `validation` → `validation`.
- `test_escalation_record_redacts_last_error`: `token=abc123`, `Authorization: Bearer x.y.z`,
  `sk-ant-…`, `ghp_…` become `[redacted]`; multi-line and 2 KB input give one line ≤ 400 chars; a
  symlinked last-error is ignored.
- `test_escalation_hint_is_consumed_once`: `hint task_blocked --run A --task T005` then `write
  other implementation --run A` → kind `task_blocked`, tasks `["T005"]`, hint removed.
- `test_escalation_repeated_write_keeps_kind`: after that, a second `write other implementation
  --run A` leaves the record bytes unchanged; `write human_stop implementation --run A` replaces
  it with kind `human_stop`.
- `test_escalation_only_for_the_current_run`: after run B starts, `write … --run A` and `hint …
  --run A` exit 3 and write nothing.
- `test_escalation_cleared_by_new_run_and_resume`: a record of run A is removed by `run-record
  start` (run B) and, in a second case, by `run-record resume --run A`.
- `test_escalation_clear_and_invalid`: `clear` removes it; a record with schema 2 → `show` exit 1;
  recorded `--max-fix-rounds 5` → no `resume_more_rounds`.
- `test_escalation_answers_belong_to_the_current_run` (P18): a `run.json` from an earlier
  pipeline start (`--approved --base main --max-fix-rounds 3 --no-pr`) and its ended pipeline
  record are left in place; a stand-alone record `start ai-run … -- --approved --sessions 2`
  becomes current; `write task_blocked implementation --run <ai-run id> --task T001` → no answer
  `argv` starts with `.ai/bin/ai-pipeline`, `resume` is exactly `[".ai/bin/ai-run", "--approved",
  "--sessions", "2"]`, no `resume_more_rounds`; a stand-alone record with `--plan /abs/p.md` → no
  `resume` answer; a pipeline record's `resume` equals its own argv, not the manifest's.
- `test_escalation_stop_request_wins` (P16): with a stop request on run A and a pending
  `task_blocked` hint, `write other implementation --run A` → kind `human_stop`, hint removed.

### Validation
Targeted: `python3 -m unittest discover -s tests -k escalation` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22: `workflow.py escalation write|hint|show|clear` (record and hint beside `runs/`,
under `runs/.lock`, current run only, exit 3 otherwise); `run_change` gained an `after` hook so
`run-record resume` clears it under the same lock, and `start_run` clears it after publishing
`current` (a recovery's `own` does not clear). Redaction per spec B10 (`redact_error`). Answers
from the named run record only. Documented in `docs/workflow.md` "Escalation record".
Evidence: `python3 -m unittest discover -s tests -k escalation` Ran 11 OK (the 9 new
`test_escalation_*` plus two older plan-escalation tests); `-k test_run_record` Ran 11 OK;
`DocsConsistencyTest` Ran 3 OK. Full gate result unknown in the session; left to the host gate
(the background `.ai/bin/ai-check` hit the 20-minute background limit and was stopped).
Note: `ai-task retry|skip|model` named in the answers land with T312.
2026-10-22 (resume): the host gate after b99ceac failed 1 of 1131 tests,
`test_gate_lock_wait_runner_waits_for_the_session_gate` (no `Waiting up to` in stderr): a timing
race in the lock-holder mock (2 s hold), not this change (T305 touches only the escalation code
in workflow.py, which has no caller in ai-run). The runner's recovery gate on b13bd5e (same
source as b99ceac) PASSED at 2026-10-22T03:23:47Z. Re-checked: `-k escalation` Ran 11 OK;
that gate-lock test plus `-k test_run_record` Ran 12 OK. DONE.

## T302 — Run records from ai-pipeline: required start, resume, finish, ai_die (RC-01 G3, wiring)
Status: DONE
Dependencies: T305
Model: opus

### Goal
Every human start of `ai-pipeline` publishes its run record before any controlled work and keeps
the run id; a resumed pipeline resumes that record; every pipeline end records its outcome, and
the `ai_die` record write runs only after a passing gate check.

### Implementation notes
- Design: `.ai/current-plan.md` "Run record" and round-1 rules 1 and 2; spec FR-1, B7, B17, B20.
- `scripts/ai-pipeline`, human start: right after `run-manifest start` (~163)
  `AI_RUN_ID=$(ai_helper run-record start pipeline "$AI_START_BRANCH" "$base_ref" "$base_sha"
  --pid $$ -- "${orig_args[@]}") || ai_die 'Cannot record the run in the host state directory.'`,
  check the id format, `export AI_RUN_ID` (plan review P5: required, never a warning).
- Resume branch (~155–160), after the gate and branch checks: `AI_RUN_ID=${AI_RUN_ID:-$(ai_helper
  run-record current)}` (the resumed pipeline holds the checkout lock, so `current` is this
  checkout's run; T316 passes the id explicitly), then `ai_helper run-record resume --run
  "$AI_RUN_ID" --pid $$ || ai_die 'The run record refuses this resume (stopped by you or
  replaced); rerun ai-pipeline --approved yourself.'`.
- `finish` (~89): `ai_helper run-record end --run "$AI_RUN_ID" --pid $$ finished "${1:-no PR}"
  2>/dev/null || printf 'Warning: …'`.
- `scripts/lib/common.sh` `ai_die` (~11–28), inside the `AI_PIPELINE_MARKER` branch: only when
  `AI_RUN_ID` and `AI_APPROVED_GATE` are set and `ai_gate_check "$AI_APPROVED_GATE"` passes:
  `ai_helper run-record end --run "$AI_RUN_ID" --pid $$ stopped "<first 200 chars>" 2>/dev/null ||
  true` (plan review P1: the gate check comes first). `ai-recover` does not set
  `AI_APPROVED_GATE`, so its `ai_die` writes nothing here (T316 covers `escalate()`).
- Docs: `docs/workflow.md` "Pipeline contract" gets a short "Run record" paragraph (path, fields,
  run id, retention, required at start). Flow unchanged (records only).

### Likely affected modules
scripts/ai-pipeline, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_run_record_pipeline_start_and_finish`: a fixture pipeline run (`--no-pr`) leaves one
  record, kind `pipeline`, argv equal to the command's arguments, base and branch set, outcome
  `finished`.
- `test_run_record_pipeline_stop_ends_stopped`: a run that stops (`AI_AUTO_RECOVER=0`) ends
  `stopped` with the reason as detail.
- `test_run_record_pipeline_refuses_without_record`: a state directory where `runs` is a regular
  file → the pipeline exits 1 before the fake session starts (its sentinel file is absent).
- `test_run_record_pipeline_resume_keeps_one_record`: a stop handed to `ai-recover` that resumes
  → still one record, same id, `resumes` 1, outcome `finished`.
- `test_run_record_ai_die_after_gate_change`: a fake session that changes `.ai/bin/lib/workflow.py`
  to write a sentinel when run → the pipeline stops, the sentinel is absent and the record is
  still `running` (no helper ran).
- Existing pipeline and recovery tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k run_record` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (claude opus): implementation complete. `scripts/ai-pipeline`: human start runs
`run-record start pipeline …` right after `run-manifest start` (required, `ai_die` on failure),
recovery resume runs `run-record resume` (id from `AI_RUN_ID` or `run-record current`), the id
format is checked and `AI_RUN_ID` exported; `finish` ends the record `finished` (warning on
failure). `scripts/lib/common.sh` `ai_die` (pipeline shell only) ends it `stopped` with the
first 200 characters of the reason, only with `AI_RUN_ID`, `AI_APPROVED_GATE`, no
`AI_GATE_BROKEN` and a passing `ai_gate_check`. Docs: `docs/workflow.md` "Pipeline contract".
Flow unchanged. Evidence: `-k run_record` 19 OK (all five new tests included; the no-PR detail
is `no PR`); `-k test_pipeline_` 14 OK; `-k test_recovery_` 23 OK.
BLOCKED only on the gate: `.ai/bin/ai-check` ran past the session's 600 s foreground limit, and
the background run was killed at its limit (no result). Needs: the host gate on this checkpoint;
when it passes, set T302 DONE (no source change expected).
2026-10-22 (T303 session): the host gate after b6a4386 fails 7 tests, and they are T302's, not
T303's (T303's script change is 1e06212, before f77e511; no script changed after a428a3c, and
a428a3c's gate never ran because T302 was gate-blocked). All 7 die in the T302 resume check
(`scripts/ai-pipeline` ~166, "The run record refuses this resume"):
`test_preflight_pipeline_same_ruling_twice_stops` and `_indirectly_moved_task_repeat_stops`
create only `run-manifest start` and resume with `AI_RECOVERY_ATTEMPT=1` (no run record);
the four `test_supervised_plan_resume_*_watchdog` resumes get an empty `AI_RUN_ID`
("Usage: run-record resume --run ID --pid PID"); and
`test_observation_pipeline_registers_the_checkout_on_start_and_resume` gets "not the owner".
This fails the acceptance line "Existing pipeline and recovery tests pass". Needs: a T302 fix
(test fixtures that resume must start a run record; check how the watchdog and observation resume
paths obtain the id and owner), then the host gate.
Mission control 2026-10-22 07:45Z: returned to TODO. The host gate now shows that this task's resume check breaks 7 tests: test_supervised_plan_resume_after_stage_clear_watchdog, test_supervised_plan_resume_after_the_record_watchdog, test_supervised_plan_resume_reserved_without_a_stage_watchdog, test_supervised_plan_resume_stage_without_a_reservation_watchdog, test_preflight_pipeline_same_ruling_twice_stops, test_preflight_pipeline_indirectly_moved_task_repeat_stops, test_observation_pipeline_registers_the_checkout_on_start_and_resume. Diagnosis from T303's session (ad420a2): `run-record resume` gets a usage error, then 'The run record refuses this resume'. Run exactly these tests one per call, fix the resume path (a resume without a matching record, e.g. from a watchdog or an older run, must behave as these tests expect), keep the new run-record tests green, and mark DONE. Do not run the full gate in the foreground.
2026-10-22 (claude opus, reconcile): the fix is in recovery checkpoint 086ff5f (written by a
timed-out session). `scripts/ai-pipeline` resume: a named run (`AI_RUN_ID`) must resume; without
one, the current record is resumed if it accepts; otherwise a stop request on it refuses, and no
record or an ended one without a stop request starts this run's record ("No run record to resume;
recording this resumed run."). New tests `test_run_record_pipeline_resume_without_a_record_starts_one`,
`test_run_record_pipeline_resume_refuses_a_stop_request_or_a_named_unknown_run`. Evidence: host
gate PASS 2026-10-22T06:39:33Z, Ran 1138 OK (fingerprint of the tree committed as 086ff5f); in
session `-k run_record` Ran 21 OK; the seven tests above OK (2+2+3, run separately); Docs OK.
`docs/workflow.md` "Pipeline contract" now describes the resume fallback. DONE.

## T316 — ai-recover owns the run early (RC-01 G3, plan review P4)
Status: DONE
Dependencies: T302
Model: opus

### Goal
A recovery, also one the watchdog started with a new pid, owns the run record before any long
recovery work, so the record always names the live process.

### Implementation notes
- Design: spec FR-1, B7, B17, B18; plan "Run record" (`own`, `pause`).
- `scripts/ai-recover`: right after `state-root-check` (~68–72) and before `reserve-attempt`
  (~77): `AI_RUN_ID=${AI_RUN_ID:-$(ai_helper run-record current 2>/dev/null)}` (it holds the
  checkout lock), then `ai_helper run-record own --run "$AI_RUN_ID" --pid $$ --launcher
  ai-recover`; no record → `escalate 'there is no run record to resume.' 'rerun ai-pipeline
  --approved by hand.'`; refused → `escalate 'the run was stopped by you or replaced; not resumed
  automatically.' 'rerun ai-pipeline --approved … to continue.'` (T307 turns the stop case into
  the human-stop path). Nothing long runs before it.
- `escalate()` (~44–55): `run-record end --run "$AI_RUN_ID" --pid $$ stopped "<reason, 200
  chars>"`, skipped when `AI_GATE_BROKEN` is set or `AI_RUN_ID` is empty (spec B20: the watchdog
  and the pipeline verified the gate before this process started). `relaunch_wait` (~94–106):
  `run-record pause`. `on_exit` (unexpected exit): `end stopped`, same conditions. `resume()`
  (~58–64): pass `AI_RUN_ID="$AI_RUN_ID"` in the `exec env`.
- Docs: `docs/workflow.md` "Recovery contract" (the recovery owns the run record first). Flow
  unchanged (records only).
- The stand-alone `ai-run` record moved to T328 (mission control split this task after two
  sessions hit the time limit).

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_run_record_recovery_owns_before_its_session`: a record whose pipeline pid is dead and an
  `ai-recover --stage 'crash (pipeline killed or restarted)'` started directly (new pid) whose fake
  decision session saves `run-record show` → the saved record names the recovery's pid and
  launcher `ai-recover`, `resumes` 0; after the resume, `resumes` 1 and one record.
- `test_run_record_recovery_refuses_a_stopped_run`: a record with a stop request → `ai-recover`
  exits 1, manifest `attempts` unchanged, no session started.
- Existing recovery, watchdog and runner tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k run_record_recovery` plus the recovery tests named in the notes below (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes

Mission control 2026-10-22 10:10: the first opus session hit the 1800 s limit (empty session log)
and left an unfinished diff, committed as WIP. The gate then failed 35 tests, nearly all
recovery and watchdog tests (`observation_recovery_*`, `supervised_plan_resume_*_watchdog`,
`limit_relaunch_*`, `recovery_*`, `plan_revision_stage_*`, `preflight_pipeline_*`,
`interrupt_reaches_the_recovery_session`, `timeout_rerun_unchanged_auto_recovery_off`,
`resume_ignores_user_config_*`, `supervise_settings_are_captured_*`), with
"escalated to the human: the run was stopped by you or replaced; not resumed automatically"
(1 != 128): the new `run-record own` refuses in fixtures where the existing flow must keep
working (e.g. no record, or a record owned by the dead pipeline pid). Fix the semantics or the
shared fixtures, never weaken an assertion. Check those tests with targeted `-k` runs (the
names above), not the full gate: leave the full gate to the runner, it outlives the tool limit.

Mission control 2026-10-22 10:40: a second opus session also hit the 1800 s limit (empty log).
Its uncommitted test changes (a `crashed_run_record()` helper that `tool('ai-recover', ...)` and
the direct `ai-recover` Popen fixtures call, so they start from a crashed pipeline's running
record) are committed as WIP: continue from them. Task split: only the ai-recover part stays
here; the stand-alone ai-run record is T328. Budget the session: run the failing tests in a few
`-k` groups of at most ~10 tests each, never the whole file or the full gate (the runner runs
the gate), and checkpoint as soon as the named tests pass.

Mission control 2026-10-22 11:25: a third session hit the limit after changing only
`.ai/handoff.md` (kept: its T316 entry and the next action). Mission control then ran the 30
tests that matter on the committed source (030fc61), each alone, eight in parallel: the 28
that failed at 10:05 plus `test_run_record_recovery_owns_before_its_session` and
`test_run_record_recovery_refuses_a_stopped_run`. All 30 OK (Ran 1 each, 3–46 s). So the code
is finished. Do NOT rerun them: check the diff against the notes and acceptance criteria in a
few minutes, check `docs/workflow.md` "Recovery contract", record this result and checkpoint at
once. The runner runs the full gate.

Result 2026-10-22 (fourth session, wrap-up): the diff 8df58cb..a40f19e matches the notes.
`scripts/ai-recover` sets `AI_RUN_ID` (or `run-record current`) and runs `run-record own --pid $$
--launcher ai-recover` right after `state-root-check`, before `run-manifest gate` and
`reserve-attempt`; no record → `there is no run record to resume.`, refusal → `the run was
stopped by you or replaced; not resumed automatically.`. `escalate()` and `on_exit` end the
record `stopped` (200 chars) only with `AI_RUN_ID` set and no `AI_GATE_BROKEN`; `relaunch_wait`
pauses it; `resume()` passes `AI_RUN_ID`. Tests: `test_run_record_recovery_owns_before_its_session`
and `test_run_record_recovery_refuses_a_stopped_run` exist as in the acceptance criteria; the
shared fixture `crashed_run_record()` gives a direct `ai-recover` a crashed pipeline's record
(no assertion weakened). Evidence: mission control's 30 targeted runs on 030fc61 (all OK, Ran 1
each); not rerun in this session per the note above; the full gate is left to the runner.
`docs/workflow.md` "Recovery contract" describes the early own; this session corrected the
stand-alone `ai-run` record paragraph's task label to T328 (its code stays for T328 to check).
(Moved here from T304's notes by the T304 session, where they had been appended by mistake.)

## T303 — Interrupts reach the agent session: ai-run and ai-recover (RC-01 G2)
Status: DONE
Dependencies: none
Model: opus

### Goal
An INT or TERM to `ai-run` or `ai-recover` ends the running Claude session within seconds instead
of after the session; partial work stays exactly as after a timeout.

### Implementation notes
- Design: `.ai/current-plan.md` "G2" and round-1 rule 3. `scripts/lib/common.sh`: `ai_run_child
  CMD…` (start in the background, `AI_CHILD_PID=$!`, `wait`, return the child's status) and
  `ai_stop_child` (TERM the recorded child, here `timeout`, which forwards TERM and kills after
  10 s; wait for it up to 30 s; return 1 if it is still alive; idempotent, so a second signal
  during the trap is harmless; no-op without a child). A non-interactive shell's background child
  ignores SIGINT and cannot trap it, which is fine: below the top process only the TERM from
  `ai_stop_child` is meant to reach a layer (T317, T318 build on this).
- `scripts/ai-run` `claude_session` (~353): `timeout …` → `ai_run_child timeout …`, redirections
  unchanged; traps (~244–245) → `trap 'ai_stop_child; exit 130' INT` and `trap 'ai_stop_child;
  exit 143' TERM`. `scripts/ai-recover` (~358, traps ~133–134) the same. Keep `code=$?`,
  `session_code` and the 124/137 handling as they are; no other change to the session code
  (batch 10).
- Tests: a fake `claude` on `PATH` that writes its pid to a file and sleeps 300 s; start the
  runner with `start_new_session=True`, wait for the `Session:` line, `os.killpg(runner_pgid,
  SIGINT)`; never signal anything else.
- Docs: `docs/workflow.md` "Interruption, limits, and recovery": an interrupt now ends the running
  session at once. Flow chart: the vault `agents-flow.md` recovery part says an interrupt ends the
  session at once; update its `updated:` date and add a dated hub Log line in `agents.md`.

### Likely affected modules
scripts/lib/common.sh, scripts/ai-run, scripts/ai-recover, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_interrupt_reaches_the_session_ai_run`: SIGINT to the fixture runner's group while the fake
  session sleeps: the runner exits 130 within a scaled 30 s, the fake claude process is gone, the
  task attempt is logged `interrupted`, the run-log row `stopped (exit 130)` is written, and the
  uncommitted file the fake session wrote is still there.
- `test_interrupt_reaches_the_session_term`: the same with SIGTERM sent to the runner's pid only
  (not its group) → exit 143, the fake claude process is gone.
- `test_interrupt_reaches_the_recovery_session`: `ai-recover` interrupted during its decision
  session ends within the bound and its fake session is gone.
- `test_session_exit_codes_unchanged`: a session timeout still yields 124 handling, a failing
  session its code (existing timeout tests pass).

### Validation
Targeted: `python3 -m unittest discover -s tests -k interrupt` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Mission control 2026-10-22 01:35Z: the session timed out; its partial edits are committed as WIP. Reconcile them, run targeted checks only, then mark DONE.
2026-10-22 reconcile: WIP 1e06212 holds the complete change (`ai_run_child`/`ai_stop_child` in
`scripts/lib/common.sh`; `ai-run` session and traps; `ai-recover` session and INT/TERM/HUP traps;
fake `sleep` modes and 4 tests; `docs/workflow.md`; vault flow chart and hub Log). This session only
fixed a spacing nit in the mock. Evidence: `python3 -m unittest discover -s tests -k interrupt -k
test_session_exit_codes_unchanged` → Ran 13 tests OK (incl. `test_interrupt_reaches_the_session_ai_run`,
`_term`, `_the_recovery_session`, `test_session_exit_codes_unchanged`); `-k timeout` → Ran 31 tests OK.
Full gate not run here per the mission-control note (gate exceeds the session limit); the runner
validates the checkpoint.
Mission control 2026-10-22 07:12Z: the host gate after b6a4386 failed 7 tests that passed after T302 (a428a3c), so T303's changes caused them: test_supervised_plan_resume_after_stage_clear_watchdog, test_supervised_plan_resume_after_the_record_watchdog, test_supervised_plan_resume_reserved_without_a_stage_watchdog, test_supervised_plan_resume_stage_without_a_reservation_watchdog, test_preflight_pipeline_same_ruling_twice_stops, test_preflight_pipeline_indirectly_moved_task_repeat_stops, test_observation_pipeline_registers_the_checkout_on_start_and_resume. Run exactly these (`python3 -m unittest tests.test_workflow.ToolkitTest.<name>`, one per call), find the regression in the interrupt forwarding, fix it without weakening the tests, then run the targeted checks and mark DONE. Do not run the full gate in the foreground.
2026-10-22 05:2xZ (claude opus): no regression in the interrupt forwarding; the 7 failures are
T302's. Evidence: T303's whole script change is WIP 1e06212, committed before T302's f77e511, and
`git diff a428a3c b6a4386 --stat` touches only `.ai/` records and one test line, so "passed after
a428a3c" was never measured (T302 was gate-blocked, so no gate ran there). Each of the 7 run alone
fails in T302's resume check, `scripts/ai-pipeline` ~166 ("The run record refuses this resume"):
the two preflight tests and the four watchdog tests resume without a run record or id
("Usage: run-record resume"); the observation test gets "run-record resume: not the owner". None of
them reaches `ai_run_child`/`ai_stop_child`. Diagnosis recorded under T302. T303 targeted:
`python3 -m unittest discover -s tests -k interrupt -k test_session_exit_codes_unchanged` → Ran 13
tests OK. No source change in this session. The full gate stays red until T302 is fixed; it is not
claimed clean.
Mission control 2026-10-22 07:45Z: set DONE: its session showed the seven gate failures come from T302's resume check, not this task (ad420a2); T302's rerun and its host gate cover this commit too.

## T304 — Interrupts reach reviews, the gate and dependency setup (RC-01 G2)
Status: DONE
Dependencies: T303
Model: opus

### Goal
`ai-review`, `ai-check` and `ai_deps` end their `timeout` child at once on INT/TERM, so a stop
during a 13-minute gate or a review does not wait for it.

### Implementation notes
- `scripts/ai-review` ~137 (Claude) and ~187 (Codex): `ai_run_child timeout …`; add or extend
  INT/TERM traps with `ai_stop_child` before the existing exit (read the script's current traps
  first and keep their behaviour).
- `scripts/ai-check` ~47–51: `timeout … bash .ai/validate 2>&1 | tee "$log"` becomes a logger
  started first on its own descriptor, `exec 7> >(tee "$log"); tee_pid=$!`, then `ai_run_child
  timeout … bash .ai/validate >&7 2>&1` (so `AI_CHILD_PID` is `timeout`), `exec 7>&-`, and
  `wait "$tee_pid"` for the logger's own status. Both statuses are kept exactly as today's
  `PIPESTATUS` rule (~50–51; plan review P14): `result` is the validator's code, replaced by the
  logger's when the logger failed; only then `stamp record "$result" "$log"`. A successful
  validator with a failed logger therefore exits nonzero and never records PASS. Keep the lock
  wait and the progress output exactly as they are. Traps: `ai_stop_child`, close fd 7, wait for
  the logger (bounded), then the existing exit path (the stamp stays RUNNING/FAIL as today for an
  interrupted gate).
- `scripts/lib/common.sh` `ai_deps` ~249: `ai_run_child timeout …`.
- `ai-review` and `ai-check` may themselves run as background children (T317, T318): their INT
  trap is then ineffective and TERM is what ends them, so the TERM trap must do the full job.
- Docs: one sentence in `docs/workflow.md` (the same paragraph as T303). Flow unchanged beyond
  T303's note.

### Likely affected modules
scripts/ai-review, scripts/ai-check, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_interrupt_reaches_the_gate`: `ai-check` with a fake `.ai/validate` that sleeps 300 s,
  SIGINT to its group → exits within a scaled 30 s, the validate process is gone, the stamp is not
  PASS, the log holds the output written before the interrupt.
- `test_interrupt_reaches_the_review`: `ai-review` with a fake `codex` and a fake `claude` that
  sleep: both end within the bound, also with SIGTERM to the `ai-review` pid only.
- `test_check_logger_failure_fails_the_gate`: a fake `tee` first on `PATH` that reads all its
  input and exits 1, with a fake `.ai/validate` that exits 0 → `ai-check` exits nonzero and the
  stamp is not PASS (plan review P14).
- Existing `ai-check` output, stamp and lock-wait tests pass (exit codes and the log unchanged).

### Validation
Targeted: `python3 -m unittest discover -s tests -k interrupt` and `-k check` (must say `Ran N
tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (claude opus): `scripts/ai-review` runs the Codex and the Claude reviewer through
`ai_run_child` and traps INT/TERM (`ai_stop_child; exit 130/143`; it had no INT/TERM traps; the
format retry's EXIT trap still logs). `scripts/ai-check` starts `tee` as a logger on fd 7
(`exec 7> >(tee "$log")`, `tee_pid=$!`), runs `ai_run_child timeout … bash .ai/validate >&7 2>&1`,
closes fd 7 and waits for the logger; a failed logger replaces the result (P14), then `stamp
record`. Its INT/TERM traps (installed right before the logger, so the lock wait is unchanged)
stop the child, close fd 7, wait up to 5 s for the logger and exit 130/143, leaving the
invalidated stamp. `ai_deps` runs `.ai/ci-setup` through `ai_run_child`. Mocks: `MOCK_CODEX=sleep`
and `MOCK_CLAUDE_REVIEW=sleep`. New tests: `test_interrupt_reaches_the_gate` (group SIGINT → 130
and pid-only SIGTERM → 143, validator gone, stamp not PASS, log and output hold the line written
before), `test_interrupt_reaches_the_review` (Codex and Claude × group SIGINT / pid-only SIGTERM,
reviewer gone, current review unchanged), `test_check_logger_failure_fails_the_gate`. Evidence:
`-k interrupt` Ran 14 OK; `-k check` Ran 98 OK (805 s); `-k gate_lock -k validation_ -k
test_check -k ai_check` Ran 27 OK; `-k test_review_` Ran 49 OK; review/deps groups (`-k
failed_or_malformed -k concurrent_checkout -k falls_back_to_claude -k format_retry -k deps`) Ran
35 OK; `-k limit_relaunch_verify -k fallback` Ran 14 OK. Full gate not run in session (≈1300 s,
over the 600 s tool limit); the runner's gate decides. `docs/workflow.md` sentence added; hub Log
line added. T316's last three notes, appended here by mistake, were moved back to T316.

## T328 — Stand-alone ai-run publishes and ends its run record (RC-01 G3, plan review P7, P18)
Status: DONE
Dependencies: T316
Model: opus

### Goal
A stand-alone `ai-run` publishes its record after its exit handler is installed, using the real
branch variable and an argv with absolute paths, and ends it on every exit.

### Implementation notes
- Design: spec FR-1, B7; plan "Run record". Split from T316 by mission control (2026-10-22).
  The first T316 session already added part of this to `scripts/ai-run` (WIP commit 8df58cb):
  check it against these notes and finish it.
- `scripts/ai-run`: save the original arguments at the top (`run_argv=("$@")`); the
  `--knowledge-dir` branch (~78–82) replaces its value in `run_argv` with the resolved
  `knowledge_dir`, as `ai-pipeline` does (~57), so the recorded argv (and T305's `resume`
  answer, run from the checkout root) never holds a caller-relative path (plan review round 3,
  P18). Only when `AI_PIPELINE` is unset: right after the traps (~243–245) `AI_RUN_ID=$(ai_helper
  run-record start ai-run "$AI_START_BRANCH" - - --pid $$ -- "${run_argv[@]}") || ai_die 'Cannot
  record the run in the host state directory.'` (plan review P7: `AI_START_BRANCH`, not
  `branch`; after `on_exit` is installed). `on_exit`: when `AI_RUN_ID` is set and `gate_ok=yes`,
  `end finished` on code 0 else `end stopped` (T315 stores `human_stop` when a stop was
  requested; P16). Keep both additions small (batch 10 edits the session code).
- Docs: the T302 "Run record" paragraph in `docs/workflow.md` (stand-alone `ai-run`). Flow
  unchanged (records only).
- Run only the targeted tests below (`-k run_record_standalone`), never the full gate.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_run_record_standalone_ai_run`: `ai-run --approved` alone writes a kind `ai-run` record
  with `AI_START_BRANCH` as branch, ended `finished`; inside a pipeline no second record appears;
  started from a subdirectory with `--knowledge-dir ./notes`, the recorded argv holds the
  absolute path of `<subdir>/notes`.
- `test_run_record_standalone_refusal_after_publication`: a stand-alone run whose only task is
  BLOCKED ("none can run") → its record ended `stopped`, not `running`.
- `test_run_record_standalone_start_clears_escalation`: an `escalation.json` of an earlier run is
  gone once a fresh stand-alone `ai-run` has started.
- Existing runner tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k run_record_standalone` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (opus): the WIP from 8df58cb in `scripts/ai-run` already matched every note:
`run_argv=("$@")` at the top, the `--knowledge-dir` branch writes the resolved path into
`run_argv`, `run-record start ai-run "$AI_START_BRANCH" - - --pid $$ -- "${run_argv[@]}"` only
without `AI_PIPELINE` and right after the traps (refuses with `Cannot record the run in the host
state directory.`), and `on_exit` ends it `finished`/`stopped` only when `gate_ok=yes`. No source
change was needed. The three tests and the `docs/workflow.md` "Pipeline contract" paragraph were
already in place. Evidence: `python3 -m unittest discover -s tests -k run_record_standalone` →
`Ran 3 tests … OK`. Full gate result unknown in the session; left to the host gate (the notes
say to run only the targeted tests).

## T317 — Interrupts reach the runner's and recovery's host gates and limit sleeps (RC-01 G2, plan review P2)
Status: DONE
Dependencies: T304
Model: opus

### Goal
A TERM to `ai-run` or `ai-recover` alone (not their group) ends them within seconds also while
they run the full host gate or wait out a usage-limit pause.

### Implementation notes
- Design: `.ai/current-plan.md` "G2" (T317 call sites) and round-1 rule 3; spec FR-2.
- `scripts/ai-run` ~304: `AI_CHECK_LOCK_WAIT=$lock_wait AI_CHECK_TIMEOUT=$remaining
  "$AI_BIN/ai-check" || gate_code=$?` becomes `ai_run_child env AI_CHECK_LOCK_WAIT="$lock_wait"
  AI_CHECK_TIMEOUT="$remaining" "$AI_BIN/ai-check" || gate_code=$?` (one line; batch 10 edits
  nearby code).
- `scripts/ai-recover` ~303 (`commit_validated`): `ai_run_child "$AI_BIN/ai-check" || escalate …`.
- `scripts/lib/common.sh` `ai_limit_pause` ~122: `ai_run_child ${AI_SLEEP:-sleep} "$wait"`
  (`ai-run` ~371 and `ai-review` ~204, ~226 use it).
- The trap of the calling script (T303, T304) already calls `ai_stop_child`; `ai-check` is a
  background child here, so it is ended by TERM (T304's TERM trap).
- Tests signal only the fixture runner's pid (`os.kill(pid, SIGTERM)`), never a group. Docs: the
  T303 paragraph in `docs/workflow.md` also names the gate and the limit pause. Flow unchanged
  beyond T303's note.

### Likely affected modules
scripts/ai-run, scripts/ai-recover, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_interrupt_pid_only_runner_gate`: a stand-alone `ai-run` in its host gate with a fake
  `.ai/validate` that sleeps 300 s, SIGTERM to the `ai-run` pid → exit 143 within a scaled 40 s,
  the validate process is gone, the stamp is not PASS.
- `test_interrupt_pid_only_recovery_gate`: `ai-recover` in `commit_validated`'s gate (the
  session-timeout rerun case) with the same fake validate, SIGTERM to its pid → it ends within the
  bound, the validate process is gone, nothing committed.
- `test_interrupt_pid_only_limit_pause`: `ai-run` paused at a usage limit (fake claude prints a
  limit message, `AI_SLEEP` a fixture that sleeps 300 s), SIGTERM to its pid → ends within the
  bound, the sleep process is gone.
- Existing gate, limit and recovery tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k interrupt` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (claude opus): `scripts/ai-run` `host_gate` runs `ai_run_child env AI_CHECK_LOCK_WAIT=…
AI_CHECK_TIMEOUT=… ai-check`, `scripts/ai-recover` `commit_validated` runs `ai_run_child ai-check`,
`scripts/lib/common.sh` `ai_limit_pause` runs `ai_run_child ${AI_SLEEP:-sleep}`. New tests (pid-only
SIGTERM): `test_interrupt_pid_only_runner_gate` (exit 143, fake validate gone, stamp not PASS),
`test_interrupt_pid_only_recovery_gate` (the pipeline's own timeout-rerun recovery: the ai-recover
pid found from the fake validate's ancestry gets TERM, ends within INTERRUPT_TIMEOUT, validate gone,
no recovery checkpoint, partial.txt untracked, "auto-recovery failed unexpectedly (exit 143)"),
`test_interrupt_pid_only_limit_pause` (exit 143, the sleep fixture gone). The bound used is
INTERRUPT_TIMEOUT (scaled 30 s), tighter than the 40 s criterion. Evidence: `python3 -m unittest
discover -s tests -k interrupt` → Ran 17 tests, OK. The full gate ran past the 600 s tool limit
in this session, so the runner's gate is the evidence for it. docs/workflow.md "Interruption,
limits, and recovery" names the host gates and the limit pause.

## T306 — ai-pipeline traps INT/TERM and records a human stop, gate first (RC-01 G1, pipeline)
Status: DONE
Dependencies: T302, T317
Model: opus

### Goal
An interrupt of `ai-pipeline` (Ctrl-C, `kill -TERM`, a service stop) is recorded as "stopped by
the human" exactly once and never handed to auto-recovery; `stop()` does the same when the run
record carries a stop request; no checkout helper runs and nothing is committed on these paths
before the inline gate verifier has passed (plan review P1).

### Implementation notes
- Design: `.ai/current-plan.md` "G1: human stop" (the order of `ai_human_stop` and `stop()`) and
  round-1 rule 1; spec FR-3, B20. Function `ai_human_stop SIGNAL` in `scripts/lib/common.sh`,
  idempotent via `AI_HUMAN_STOPPED`, starting with `trap '' INT TERM`.
- Gate first: `ai_stop_child` (plain shell), then the gate decision: `AI_APPROVED_GATE` unset
  (a signal before the baseline at ~153) or `ai_gate_check "$AI_APPROVED_GATE"` failing → the
  gate-broken path of the plan (notify, `last-error` and `last-error.notified` by shell writes,
  `ai_drop_marker`, exit; no `ai_helper`, no `git commit`). Otherwise the full path in the plan's
  order: request-stop (via `signal` when none is recorded), run-log row naming the recorded `via`,
  `run-record end --run "$AI_RUN_ID" --pid $$ human_stop`, `escalation write human_stop <stage>
  --run "$AI_RUN_ID"`, observation, bookkeeping commit (only records dirty and the child ended;
  never while armed), `ai_gate_check` again, notification, `last-error`, `last-error.notified`,
  marker, exit 130 or 143.
- `scripts/ai-pipeline`: `trap 'ai_human_stop INT' INT` and `trap 'ai_human_stop TERM' TERM`
  before the marker is written (~84–87). `step` records the stage key in a shell variable
  `AI_STAGE` (used by the notification and the escalation); before the first step it is `start`.
- `stop()` (~173): keep `ai_gate_check` first (~178); only when `gate_ok=yes`: `if ai_helper
  run-record stop-requested --run "$AI_RUN_ID" 2>/dev/null; then ai_human_stop TERM; fi`, before
  the `exec ai-recover` branch, so an `ai-run` that exited under a requested stop never reaches
  recovery.
- This task signals the fixture's whole group (children receive it too); PID-only signals need
  T318.
- Docs: `docs/workflow.md` "Interruption, limits, and recovery" (human stop; what happens when the
  gate changed). Flow chart: vault `agents-flow.md` gains the "Stopped by you" path (interrupt →
  gate check → record → no recovery), `updated:` date, hub Log line.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_human_stop_during_session`: a fixture pipeline (`AI_AUTO_RECOVER` default 1) whose fake
  claude sleeps, SIGINT to its group: exits 130 within a scaled 40 s; no `ai-recover` ran (no
  🔧 notification); notification log has exactly one `⛔ STOPPED by you:` line; run record outcome
  `human_stop`; escalation kind `human_stop`; marker gone; `last-error.notified` newer than
  `last-error`; the fake session's uncommitted file is kept.
- `test_human_stop_bookkeeping_commit`: a stop while only the run log is dirty leaves a clean
  checkout with the commit `chore(ai): record stop by the human`.
- `test_human_stop_request_wins_in_stop`: with a recorded stop request, an `ai-run` failure goes
  to the human stop path, not `ai-recover`.
- `test_human_stop_gate_tamper_child_failure`: the fake session replaces the fixture's
  `.ai/bin/lib/workflow.py` with code that writes a sentinel file whenever it runs, then exits 1
  → the pipeline stops, the sentinel never appears, no `ai-recover` ran, no new commit, one ⛔
  notification (from `AI_NOTIFY_CMD`), marker gone.
- `test_human_stop_gate_tamper_interrupt`: the same tampering, then the fake session sleeps;
  SIGINT to the group → exit 130, the sentinel never appears, no commit, one ⛔ notification,
  marker gone.

### Validation
Targeted: `python3 -m unittest discover -s tests -k human_stop` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22: `ai_human_stop SIGNAL` in `scripts/lib/common.sh` (idempotent via `AI_HUMAN_STOPPED`,
`trap '' INT TERM` first, `ai_stop_child`, then the inline gate check: unset baseline or a changed
gate → shell-only ⛔ STOPPED by you, `last-error`/`last-error.notified`, marker dropped, exit; else
stop request `via signal` when none, run-log row `stopped by the human (<via>)` (not while armed),
`run-record end … human_stop`, `escalation write human_stop <stage>` (sets
`AI_ESCALATION_WRITTEN`), observation, bookkeeping commit only when the dirty paths are a subset
of state/run log/handoff and the child ended, gate re-check, ⛔ STOPPED by you (with ` Partial work
is kept uncommitted.` when dirty), exit 130/143). Deviation: `last-error` (`stopped by the human
during <stage>`) is written before the escalation write, so the escalation's evidence is this
stop rather than a stale reason. `scripts/ai-pipeline`: INT/TERM traps before the marker,
`AI_STAGE` set by `step` (`start` before the first step), `stop()` calls `ai_human_stop TERM`
after its gate check when `run-record stop-requested` succeeds. Docs: `docs/workflow.md`
"Interruption, limits, and recovery"; vault `agents-flow.md` "Stopped by you" path, bullet and
notification row, hub Log line.
Evidence: `python3 -m unittest discover -s tests -k human_stop` → Ran 8 tests OK (57.8 s; the 5
new `test_human_stop_*` plus 3 existing). Full `.ai/bin/ai-check` exceeded the 600 s tool limit in
session (the suite takes ≈ 20 min), so the runner's host gate decides, as for T317.
Limitation (by design, T318): a PID-only TERM waits for the pipeline's foreground stage.

## T318 — The pipeline forwards a stop to its children and sleeps; PID-only stop at every stage (RC-01 G2, G1, plan review P2)
Status: DONE
Dependencies: T306
Model: opus

### Goal
A SIGINT or SIGTERM to the `ai-pipeline` process alone ends the run within seconds in every long
stage (implementation, review, validation, dependency setup, retry waits) with the same human
stop records as a group signal.

### Implementation notes
- Design: `.ai/current-plan.md` "G2" (T318 call sites); spec FR-2, B19. Comes after T306: without
  its trap a PID-only signal would end the pipeline at once and orphan the background child.
- `scripts/ai-pipeline`: `ai_run_child` before `"$AI_BIN/ai-run"` (~288, ~332, ~552),
  `"$AI_BIN/ai-review"` (~369, ~509, ~566), `"$AI_BIN/ai-check"` (~265) and the push retry sleep
  `${AI_SLEEP:-sleep}` (~253); `|| stop …` stays as is. Nothing near the plan-review entry
  condition (~478) changes. The publication commands (`git push`, `git ls-remote`, `gh`) are T323
  (plan review round 2, P2).
- The child is ended by TERM from `ai_human_stop`'s `ai_stop_child`; the child's own TERM trap
  (T303, T304, T317) ends its `timeout`. A child exit code of 130 or 143 under a stop goes to the
  pipeline's trap, not to `stop()`. If `ai_stop_child` reports the child still alive after 30 s,
  `ai_human_stop` skips the bookkeeping commit and says so in the run-log row.
- Tests signal only the fixture pipeline's pid (`os.kill(pid, sig)`), share one fixture helper,
  and check the leaf fake process is gone and the T306 records exist. Docs: `docs/workflow.md`
  (a stop reaches every stage). Flow unchanged beyond T306.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_human_stop_pid_only_implementation`: SIGTERM to the pipeline pid while the fake session
  sleeps → exit 143 within a scaled 40 s, the fake claude is gone, outcome `human_stop`; the same
  with SIGINT → exit 130.
- `test_human_stop_pid_only_review`: during `ai-review` with a sleeping fake reviewer → ends, the
  reviewer process is gone.
- `test_human_stop_pid_only_validation`: during `ensure_validated`'s gate with a sleeping fake
  `.ai/validate` → ends, the validate process is gone, the stamp is not PASS.
- `test_human_stop_pid_only_dependency_setup`: during `ai-run`'s dependency setup with a sleeping
  fake `.ai/ci-setup` → ends, the setup process is gone.
- `test_human_stop_pid_only_retry_wait`: while waiting between push retries (fake failing `git
  push`, `AI_SLEEP` fixture that sleeps) → ends, the sleep process is gone, same records.
- Existing pipeline tests pass (exit codes and stop paths unchanged without a signal).

### Validation
Targeted: `python3 -m unittest discover -s tests -k human_stop` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (claude opus): `scripts/ai-pipeline` runs `ai-run` (triage, plan revision,
implementation), `ai-review` (re-check, plan review, review), `ai-check` (`ensure_validated`) and
the push retry sleep through `ai_run_child`; `|| stop …` unchanged, plan-review entry untouched,
publication commands left to T323. Under a signal the trap (`ai_human_stop`) runs as soon as
`wait` returns, so a 130/143 child never reaches `stop()`; the 30 s still-alive case is T306's.
Tests: shared `pid_only_stop` helper (signals only the pipeline pid via `os.kill`, scaled 40 s
bound through a new `limit` argument of `interrupt_session`, leaf gone, `human_stop` record with
via `signal`, escalation stage, marker gone, run-log row, no recovery);
`test_human_stop_pid_only_implementation` (TERM 143, INT 130), `_review` (`--skip-plan-review`,
sleeping Codex), `_validation` (DONE queue, sleeping `.ai/validate`, stamp not PASS),
`_dependency_setup` (sleeping `.ai/ci-setup`, no `vendor-deps`), `_retry_wait` (failing pre-push
hook, sleeping `AI_SLEEP`, stage `pr`). `python3 -m unittest discover -s tests -k human_stop`:
Ran 13 tests OK (118.4 s). Docs: `docs/workflow.md` (a stop reaches every stage). Flow unchanged.
Full gate: started in session, exceeded the 600 s tool limit (≈1500 s); the runner's gate decides.
2026-10-22 (claude opus, resume): the runner's post-task gate exited 124 (its time budget ran out
mid-gate, not a test failure); the recovery gate on the same code passed (state: PASS at
2026-10-22T13:42:50Z, checkpoint 4591022). Re-ran `-k human_stop`: Ran 13 tests OK (119.5 s).

## T323 — The pipeline forwards a stop to its publication commands: git push, ls-remote, gh (RC-01 G2, G1, plan review round 2 P2)
Status: DONE
Dependencies: T318
Model: opus

### Goal
A SIGINT or SIGTERM to the `ai-pipeline` process alone also ends the run within seconds while a
`git push` (with its hooks), `git ls-remote` or a `gh` call of the publication stage blocks, with
the same human stop records; captured output keeps working.

### Implementation notes
- Design: `.ai/current-plan.md` "G2" (T323 call sites); spec FR-2, B21. Comes after T318 (same
  reason as B19).
- `scripts/lib/common.sh`: `ai_run_capture FILE CMD…` runs `ai_run_child CMD… > FILE`, so the
  parent keeps the child's pid in `AI_CHILD_PID` and its trap can end it, while the output lands
  in a file instead of a command substitution (a trap does not run while the shell waits on
  `$(…)`). Returns the child's status.
- `scripts/ai-pipeline` `push()` (~249, ~255): `ai_run_child git push "$@"`; `ai_run_capture
  "$pub_out" git ls-remote origin "refs/heads/$branch"`, then the existing `awk` reads the file
  (the `|| remote=''` fallback stays). PR stage (~679–719): every `gh pr view`, `gh pr edit`,
  `gh pr ready` and `gh pr create` through `ai_run_child` (output discarded) or `ai_run_capture`
  (output read from the file; `gh pr create … | tail -n 1` → capture, then `tail -n 1` of the
  file); each existing `||` / `&&` branch keeps its meaning and messages exactly. `pub_out` is one
  `mktemp .ai/local/publish-XXXXXXXX.out` made at the first use, removed (best effort) in
  `finish` and `ai_human_stop`.
- `ai_stop_child` TERMs the `git` or `gh` process only. A push hook that git started may outlive
  it; that is a known limitation (spec B21), not tested here.
- Tests: share T318's PID-only fixture helper; fake `git` first on `PATH` that delegates to the
  real git except `push` (and, in the second case, `ls-remote`), which sleeps 300 s after writing
  its pid; fake `gh` (`MOCK_GH` style) whose `pr view` sleeps. Signal only the fixture pipeline's
  pid. Docs: the `docs/workflow.md` sentence of T318 names the publication stage. Flow unchanged
  beyond T306.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_human_stop_pid_only_push`: SIGTERM to the pipeline pid while the fake `git push` sleeps
  → exit 143 within a scaled 40 s, the fake push process is gone, run record outcome
  `human_stop`, escalation kind `human_stop`, one `⛔ STOPPED by you:` notification, marker gone.
- `test_human_stop_pid_only_ls_remote`: the same while the fake `git ls-remote` sleeps.
- `test_human_stop_pid_only_gh`: the same while the fake `gh pr view` sleeps; no PR is created
  (the fake `gh pr create` was never called).
- Existing PR-stage tests pass (PR URL, draft handling, push retry and `ls-remote` mismatch
  messages unchanged without a signal).

### Validation
Targeted: `python3 -m unittest discover -s tests -k human_stop` and `-k pr_` (must say `Ran N
tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
- `scripts/lib/common.sh`: `ai_run_capture FILE CMD…` (`ai_run_child CMD… > FILE`); `ai_human_stop`
  removes the pipeline's `pub_out` after `ai_stop_child` (best effort).
- `scripts/ai-pipeline`: `pub_capture` (one `mktemp .ai/local/publish-XXXXXXXX.out` at first use,
  removed by `finish`) and `pub_read` (output into `pub_text`); `push()` runs `git push` via
  `ai_run_child` and `git ls-remote` via `pub_capture` + `awk` on the file (`remote=''` fallback
  kept); every `gh pr view/edit/ready/create` via `ai_run_child` or `pub_read`/`pub_capture`
  (`gh pr create` → `tail -n 1` of the file); each `||`/`&&` branch and message unchanged.
- Tests: `test_human_stop_pid_only_push`, `test_human_stop_pid_only_ls_remote` (fake `git` first
  on `PATH`, delegating to the real git except the held subcommand), `test_human_stop_pid_only_gh`
  (`MOCK_GH_HOLD`: `pr view` sleeps; only `pr view` was called, so no PR created); each also
  checks no `publish-*.out` is left. Docs: `docs/workflow.md` stop paragraph names the
  publication stage and the push-hook limitation. Flow unchanged.
- Evidence: `-k human_stop` Ran 16 OK (171 s); `-k pr_` Ran 33 OK (436 s); `-k push` Ran 13 OK
  (264 s). Full gate: see the run-log entry.

- Mission control 2026-10-22 17:23: the session's own gate outlived its time limit (FL-38); mission control ran `.ai/bin/ai-check` on a648352 by hand: Ran 1162 tests, OK (942 s). DONE stands.

## T307 — ai-recover and the watchdog never resume a human stop (RC-01 G1, recovery)
Status: DONE
Dependencies: T306, T316
Model: opus

### Goal
A run the human stopped is never resumed automatically: `ai-recover` and the watchdog hand it to
the human, and an interrupt during recovery is a human stop too.

### Implementation notes
- `scripts/ai-recover`: T316's `own` call (right after the state-root check, before the attempt
  reservation and the relaunch schedule) is the stop check. When it refuses and `run-record
  stop-requested --run "$AI_RUN_ID"` exits 0: `run-record settle-stop --run "$AI_RUN_ID"` (no-op
  when already `human_stop`), `escalation write human_stop "$stage" --run "$AI_RUN_ID"`, one
  notification `⛔ STOPPED by you: <branch>; not resumed automatically. Rerun ai-pipeline
  --approved … to continue.` only when `last-error.notified` is older than `last-error` (else
  quiet), drop the marker, exit 1. No attempt is reserved, no Claude session. Other refusals keep
  T316's escalation.
- `ai-recover` sets `AI_APPROVED_GATE="$approved_gate"` once the manifest gate is read (~73), so
  `ai_human_stop` can verify the gate; before that point an interrupt takes the gate-broken path
  (no helper). Traps (~133–134): `trap 'ai_human_stop INT' INT`, `trap 'ai_human_stop TERM' TERM`
  (HUP unchanged); `on_exit` stays for other unexpected exits. `ai_human_stop`'s `run-record end
  --pid $$` works because `own` recorded this process.
- `scripts/lib/watchdog.py`: before `start_recovery` (~543) and before the "died" message, read
  the current run record directly in watchdog.py (`runs/current` and the record JSON, same
  validation rules as T301; the watchdog never runs the checkout's helper for this): a stop
  request or `human_stop` → incident text `⛔ STOPPED by you: the run was stopped by the human;
  not resumed automatically.` once, no recovery. Otherwise, a `died` incident it does not recover
  marks outcome `crashed`: a direct atomic write under `runs/.lock`, only when the id it read is
  still `current`, the record is not ended and its process is not alive (plan review P5), best
  effort.
- Docs: `docs/workflow.md` "Recovery contract" and "Checkout health monitoring". Flow chart: the
  recovery part of `agents-flow.md` shows "stopped by you → no recovery"; `updated:` date; hub Log
  line.

### Likely affected modules
scripts/ai-recover, scripts/lib/watchdog.py, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_human_stop_recovery_refuses`: with a stop request in the current record, `ai-recover
  --stage implementation` exits 1, reserves no attempt (manifest `attempts` unchanged), starts no
  session, writes escalation `human_stop`.
- `test_human_stop_interrupt_during_recovery`: SIGINT to the group, and in a second case SIGTERM
  to the recovery's pid only, during the fixture recovery's sleeping decision session →
  `human_stop`, no "auto-recovery failed unexpectedly" notification, no resumed pipeline.
- `test_human_stop_watchdog_does_not_recover`: a marker whose process is gone plus a stop request:
  `ai-watchdog --recover` starts no recovery (fake `systemd-run` not called) and reports the human
  stop once; without the request it starts the recovery as today and an unrecovered death marks
  the record `crashed`.
- Existing recovery and watchdog tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k human_stop` and `-k watchdog` (must say `Ran N
tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22: `scripts/ai-recover`: a refused `own` whose run has a stop request calls
`stopped_by_human` (`settle-stop`, else `end … stopped` which stores `human_stop`; `escalation
write human_stop <stage key>`; one `⛔ STOPPED by you: <branch>; not resumed automatically. Rerun
ai-pipeline <manifest args> to continue.` only when `last-error` is newer than
`last-error.notified`; marker removed; exit 1, before the attempt reservation, the relaunch
schedule and any session). Other refusals keep T316's escalation. `AI_STAGE` is the stage as a
step key (`crash (…)` → `crash`, spaces → `-`), `AI_APPROVED_GATE` is set once the manifest gate
is read and `orig_args` from the manifest; INT/TERM traps run `ai_human_stop` (HUP unchanged),
and `AI_ARMED=yes` after a relaunch's `limit-arm` so a stop then writes nothing tracked.
`scripts/lib/watchdog.py`: `current_run()` reads `runs/current` and the record with this copy's
`workflow` functions (`read_run`, T301 validation; no checkout helper process); a died marker
whose run has a stop request or `human_stop` becomes incident `human_stop:<id>` (`⛔ STOPPED by
you: the run was stopped by the human; not resumed automatically.`, once) and no recovery; a
fresh death not recovered (no `--recover`, or refused) runs `mark_crashed` (`run_change` under
`runs/.lock`: still current, not ended, process gone; best effort).
Tests: new `test_human_stop_recovery_refuses`, `test_human_stop_watchdog_does_not_recover`;
`test_interrupt_reaches_the_recovery_session` became `test_human_stop_interrupt_during_recovery`
(group SIGINT → 130 and pid-only SIGTERM → 143, record and escalation `human_stop`, `resumes` 0,
no "failed unexpectedly", no resume). Updated to the new contract (a TERM during recovery is a
human stop): `test_interrupt_pid_only_recovery_gate`,
`test_observation_recovery_term_stops_once_and_keeps_the_substage` (renamed from
`…unexpected_term…`), `test_recovery_signal_and_rejected_process_handling`;
`test_run_record_recovery_refuses_a_stopped_run` matches the new stderr. Docs: `docs/workflow.md`
"Recovery contract" and "Checkout health monitoring". Vault: flow chart recovery part, hub Log.
Validation: `-k human_stop` Ran 19 OK (144.9 s); the eight targeted recovery/watchdog tests OK;
first full gate: 1163/1164, the one failure was `test_recovery_signal_and_rejected_process_handling`
(old contract), now updated and passing alone; final gate result below / in the run log.
2026-10-22 (resume): the implementing session timed out in the full gate; the runner's recovery
checkpoint 8d45821 holds the code above and its gate passed (PASS 16:08:15Z). Diff reviewed against
the notes (`mark_crashed` relies on `run_change`'s still-current check). Rerun on 8d45821:
`-k human_stop` Ran 19 OK, `-k watchdog` Ran 62 OK. No source change in this session.

## T308 — `ai-pipeline --stop [CHECKOUT] [--wait SECONDS]`: find, verify, signal, wait (RC-01 G1, command)
Status: DONE
Dependencies: T307, T318, T323
Model: opus

### Goal
One command stops the checkout's run cleanly: found from the run record and kept by its id,
verified by process identity, sent SIGTERM (its group when the pid leads it, else the pid alone),
waited for, recorded as a human stop; one behaviour for a run whose process is already gone;
idempotent with clear exit statuses.

### Implementation notes
- Design: `.ai/current-plan.md` "G1", `--stop` paragraph; spec FR-5, B1, B2 (SIGTERM), B17.
- `scripts/ai-pipeline`: before `orig_args` (~30): `if [[ "${1:-}" == --stop ]]; then …` parse
  `[CHECKOUT]` (default `.`) and `--wait N` (`^[1-9][0-9]{0,3}$`, default 60); `cd` to `git -C
  CHECKOUT rev-parse --show-toplevel`; run the `paths` safety check (`ai_root`, no lock); `exec
  python3 "$AI_BIN/lib/workflow.py" run-stop --wait N`. Usage text gains the line.
- `workflow.py run-stop`: read `current` once and keep that id for every later step. No record →
  exit 3 `No run active in <checkout>.`; an ended record → exit 3 `Run <id> was already stopped by
  you.` (outcome `human_stop`) or `No run active in <checkout> (run <id> ended <outcome>).`.
  Outcome `running`/`paused` with the process not alive (plan review P9) → `request-stop --run
  ID`, `settle-stop`, exit 0 `Run <id> was not running (its process is gone); recorded as stopped
  by you, it will not be resumed.` (T319 adds the local completion and the relaunch message).
  Live → identity check, `request-stop --run ID --via 'ai-pipeline --stop' --expect-pid
  --expect-ticks`, identity check again, `os.killpg(pgid, SIGTERM)` only when `pgid == pid` and
  the pgid is not the caller's own process group, else `os.kill(pid, SIGTERM)`; never PID 1;
  poll every 0.2 s up to `--wait`: ended `human_stop` → exit 0 `Run <id> stopped (stopped by
  you).`; ended with another outcome (the run finished or ended before the signal took effect;
  plan review round 3, P16: never `settle-stop` on an ended record, it refuses) → exit 0 `Run
  <id> ended (<outcome>) before the stop took effect; nothing will resume it.`; the process gone
  but the record not ended → `settle-stop` (T319 adds the completion), exit 0; still alive → exit
  4 `Signalled run <id>; still ending after N s. Rerun to wait again.` Errors exit 1.
- Docs: README (command list) and `docs/workflow.md` (stop section, exit statuses). Flow chart:
  the "Stopped by you" path names `ai-pipeline --stop`; `updated:` date; hub Log line.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/workflow.py, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- `test_stop_command_stops_a_running_pipeline`: a fixture pipeline started with
  `start_new_session=True` and a sleeping fake session; `ai-pipeline --stop <checkout>` exits 0
  within a scaled 60 s, the pipeline process is gone, records as in T306, the run-log row names
  `ai-pipeline --stop`.
- `test_stop_command_not_group_leader`: a fixture pipeline started by a fixture shell so it does
  not lead its group → only its pid is signalled (a sibling in the group survives) and it still
  ends within the bound with `human_stop` (T318).
- `test_stop_command_no_run`: no record and an ended record → exit 3, record bytes identical; a
  second `--stop` after a stop → exit 3 with "already stopped by you".
- `test_stop_command_dead_process_is_recorded`: a `running` record whose process is gone →
  exit 0 with the "was not running" message, outcome `human_stop`; a later `ai-watchdog
  --recover` starts no recovery (fake `systemd-run` not called).
- `test_stop_command_identity_mismatch`: a record whose start ticks do not match a live pid (the
  test's own sleeping child) → treated as gone (exit 0, "was not running"), that child not
  signalled.
- `test_stop_command_wait_expires`: a fixture runner that ignores SIGTERM → exit 4 after `--wait
  2`; the stop request is recorded and a later `ai-recover` refuses.

### Validation
Targeted: `python3 -m unittest discover -s tests -k stop_command` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22: `ai-pipeline --stop [CHECKOUT] [--wait SECONDS]` dispatches before option parsing
(cd into the checkout, paths check, no lock, no `last-error` write) to `workflow.py run-stop`
(`run_stop`, `stop_gone`, `stop_signal`): run found only through `runs/current`, id kept;
identity → `request_stop(expect=…)` → identity → SIGTERM (group only when pgid == pid and not
the caller's group, else the pid; never PID ≤ 1) → poll 0.2 s (liveness read before the record).
Exit 0 / 3 / 4 / 1 with the planned messages; an ended record is never rewritten. Evidence:
`-k stop_command` Ran 7 OK (15.6 s): the six acceptance tests plus `test_stop_command_arguments`;
`.ai/bin/ai-check` PASS, Ran 1171 tests OK (936 s). Docs: README, `docs/workflow.md` (exit-status
table), vault flow chart and hub Log. T319 adds the local completion and relaunch message.

## T319 — `--stop` completion bound to its run; relaunch cancel; stopping a recovery (RC-01 G1, plan review P4, P5, P9)
Status: DONE
Dependencies: T308
Model: opus

### Goal
When the stopped process ended without its own records, `--stop` completes them only for the run
it inspected and only while no other runner owns the checkout; it cancels a scheduled usage-limit
relaunch, and it stops a recovery the watchdog started so that nothing resumes.

### Implementation notes
- Design: `.ai/current-plan.md` "G1", "Completion (T319)"; spec FR-5, B17, B18.
- Completion after the process ended (live case) or was found gone (T308's case), for the kept id
  only: `settle-stop --run ID` (refused → the run was replaced or ended: report it, write
  nothing more); then take `.ai/local/workflow.lock` with `flock -n` through the pinned
  `.ai/local` (held → `Run <id> ended; another runner owns <checkout> now; nothing else
  recorded.`, exit 0) and, holding it and with ID still `current`: `escalation write human_stop
  <stage or unknown> --run ID`, remove `.ai/local/pipeline.active` only when it holds the recorded
  pid, write `last-error` (`stopped by the human during <stage>`) and `last-error.notified`
  through the pinned `.ai/local`; release the lock.
- Scheduled relaunch: outcome `paused` and the manifest has `limit_relaunch_at` → the same as
  T308's gone case plus completion, message `Cancelled the scheduled usage-limit relaunch of
  <id>.`, exit 0.
- A recovery owns the record (T316), so `--stop` during a recovery signals the recovery process;
  its trap (T307) records the human stop.
- Docs: `docs/workflow.md` stop section (completion, relaunch cancel, recovery). Flow unchanged
  beyond T308.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_stop_command_completes_records`: a fixture runner recorded as the run that exits on TERM
  without writing records → exit 0, outcome `human_stop`, escalation `human_stop`, marker removed
  (it held the recorded pid), `last-error.notified` newer than `last-error`.
- `test_stop_command_never_touches_a_replacing_run`: the fixture runner A, on TERM, starts run B
  (a new record for a fixture process B that holds `.ai/local/workflow.lock`) and exits; `--stop`
  of A → exit 0 with the "another runner owns" or "replaced" message; B's record bytes, the
  escalation record (absent) and B's marker are unchanged.
- `test_stop_command_cancels_scheduled_relaunch`: a `paused` record, no live process and a
  manifest with `limit_relaunch_at` → exit 0 with the cancel message, `human_stop`, and a later
  due relaunch is refused by `ai-recover`.
- `test_stop_command_stops_a_watchdog_recovery`: a record whose pipeline pid is dead and an
  `ai-recover` started directly (new pid) with a sleeping fake decision session → `--stop` exits 0
  within the bound, the recovery is gone, outcome `human_stop`, no resumed pipeline (no ▶ RESUMED
  notification, the fake implementation session never starts).

### Validation
Targeted: `python3 -m unittest discover -s tests -k stop_command` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (claude, opus): `workflow.py` `stop_gone` → `stop_complete` (settle for the kept id;
refused → its own ended message or "another run replaced it", nothing more; then
`.ai/local/workflow.lock` LOCK_EX|LOCK_NB through the pinned `.ai/local`, held → "another runner
owns <checkout> now; nothing else recorded."; with the id still current: escalation `human_stop`
at the observation stage or `unknown`, marker unlinked only when it holds the recorded pid,
`last-error` `stopped by the human during <stage>`, `last-error.notified` set 1 µs newer) and
`stop_relaunch_scheduled` (paused + manifest `limit_relaunch_at` → cancel message). `.ai/local`
is created on the pinned `.ai` when missing (as `ai_root`). Recovery: no code change needed
(T316 ownership + T307 trap), covered by the new test. docs/workflow.md "Completion (T319)";
ai-pipeline dispatch comment. Evidence: `-k stop_command` Ran 11 OK (21.0 s; 4 new tests);
`.ai/bin/ai-check` PASS, Ran 1175 OK (943.6 s). Implementation commit 01bd5ff.

## T309 — Escalation hints at the producers of stops for a human (RC-01 G9, hints)
Status: DONE
Dependencies: T316, T328
Model: sonnet

### Goal
Each producer of a stop that waits for a human leaves a host-side hint with the kind (and task or
finding ids) right before it stops, so the escalation record never classifies from `last-error`
text. No escalation record is written yet (T320).

### Implementation notes
- Design: `.ai/current-plan.md` "G9", "Hints (T309)"; spec B8. Each hint is one line,
  `ai_helper escalation hint KIND --run "$AI_RUN_ID" … 2>/dev/null || true`, right before the
  existing stop, without changing the stop itself; skipped when `AI_RUN_ID` is empty.
- `scripts/ai-pipeline`: `plan_decision_check` (~436–442: `needs_human_question`, finding ids from
  the questions when the helper output has them), the two `revision-reserve` refusals (~327–330,
  ~529–531) and the `AI_SUPERVISE != 1` stop (~523–526) (`plan_review_limit`),
  `ensure_validated` (~265, `validation`). `scripts/ai-run` "none can run" (~877, `task_blocked`
  with the BLOCKED ids from `ai_helper tasks` output; inside a pipeline it inherits the exported
  `AI_RUN_ID`). `scripts/lib/common.sh` `ai_limit_pause` beyond the budget (~112,
  `usage_limit`).
- Keep the `ai-run` edit to the one line named (batch 10). Docs: none yet (T320 writes the
  section). Flow unchanged.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, scripts/lib/common.sh, tests/test_workflow.py

### Acceptance criteria
- `test_escalation_hint_task_blocked`: a fixture pipeline whose only task is BLOCKED
  (`AI_AUTO_RECOVER=0`) leaves `escalation-hint.json` with kind `task_blocked`, tasks `["T001"]`
  and its run id.
- `test_escalation_hint_plan_kinds`: `AI_SUPERVISE=0` with a BLOCKER plan review →
  `plan_review_limit`; a recorded needs-human plan revision → `needs_human_question`.
- `test_escalation_hint_validation_and_limit`: a failing gate (`AI_AUTO_RECOVER=0`) →
  `validation`; a usage limit beyond the wait budget → `usage_limit`.
- Existing pipeline and runner tests pass (stop messages unchanged).

### Validation
Targeted: `python3 -m unittest discover -s tests -k escalation` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22 (claude, sonnet): `common.sh` `ai_escalation_hint KIND [--task|--finding ID]…` (skips
without `AI_RUN_ID`, best effort); called right before the stop in `ai-pipeline`
(`plan_decision_check` → `needs_human_question` with finding ids grepped from the questions, the
two `revision-reserve` refusals and the `AI_SUPERVISE != 1` stop → `plan_review_limit`,
`ensure_validated` → `validation`), `ai-run` "none can run" (`task_blocked`, ids from the new
`workflow.py tasks blocked`), `ai_limit_pause` beyond the budget (`usage_limit`). Stop messages
unchanged. Tests: `test_escalation_hint_task_blocked`, `_plan_kinds`, `_needs_human_question`,
`_validation_and_limit`, `_usage_limit`. Evidence: `-k escalation_hint` Ran 6 OK;
`.ai/bin/ai-check` PASS, Ran 1180 OK (892.5 s).

## T320 — Escalation records written at every stop for a human, gate first (RC-01 G9, writes)
Status: DONE
Dependencies: T307, T309
Model: opus

### Goal
Every stop that waits for a human (pipeline, recovery, stand-alone `ai-run`) leaves an escalation
record for its own run with the kind from the hint or the stage, never from `last-error` text;
no record is written by a checkout helper after the gate changed.

### Implementation notes
- Design: `.ai/current-plan.md` "G9", "Writes (T320)"; spec FR-6, B20, B22. Each write is
  `ai_helper escalation write other "$stage" --run "$AI_RUN_ID" 2>/dev/null || true` (the hint or
  the stage refines `other`), only after a passing gate check in that path.
- One writer per shutdown chain (plan review P13): the non-recovery `stop()` always ends in
  `ai_die` (`scripts/ai-pipeline` ~186–188), and the first write consumes the hint, so a second
  write would lose the kind. Every shell write site sets `AI_ESCALATION_WRITTEN=1` after its
  call (also when the helper failed: one attempt per chain); `ai_die` writes only when it is
  unset. T305's helper rule (a same-run `other` write keeps a specific kind) is the backstop.
  - `stop()` non-recovery path (~186–188): after the existing `ai_gate_check` with `gate_ok=yes`,
    with `$stage`; then `ai_die` skips its write.
  - `ai_die` in the pipeline branch (`common.sh`): beside T302's record write, same condition,
    only when `AI_ESCALATION_WRITTEN` is unset (a direct `ai_die` without `stop()`), stage
    `${AI_STAGE:-other}`.
  - `ai-recover` `escalate()` (~44–55): skipped when `AI_GATE_BROKEN` is set or `AI_RUN_ID` is
    empty; the watchdog's crash stage (`crash (pipeline killed or restarted)`) gives kind
    `crash`.
  - Stand-alone `ai-run` `on_exit` stop path (~238–240): with `gate_ok=yes` and `AI_RUN_ID` set.
- Clearing is T305's (`run-record start` and `resume`); nothing else clears it.
- Keep the `ai-run` edit to the one line named (batch 10).
- Docs: `docs/workflow.md` gets an "Escalation record" section (path, schema, kinds, answers,
  written for the current run only, cleared by a new run or a resume, "readers treat an unknown
  kind as other"). Flow chart: "When something goes wrong" bullet "Escalation record (G9)";
  `updated:` date; hub Log line.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, scripts/ai-recover, scripts/lib/common.sh, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_escalation_wiring_task_blocked`: a fixture pipeline whose only task is BLOCKED
  (`AI_AUTO_RECOVER=0`): read after the pipeline process has exited, the record has kind
  `task_blocked`, tasks `["T001"]`, a `retry_task` answer, its run id (plan review P13: the final
  record, after `stop()` and `ai_die`).
- `test_escalation_wiring_plan_review_stop_final_record`: `AI_SUPERVISE=0`, `AI_AUTO_RECOVER=0`
  and a BLOCKER plan review: read after exit, kind `plan_review_limit` with the
  `resume_skip_plan_review` answer.
- `test_escalation_wiring_validation_and_recovery`: a failing gate with auto-recovery that
  escalates → kind `validation` written by `ai-recover`; a recovery that resumes removes the
  record.
- `test_escalation_wiring_standalone_ai_run`: a stand-alone `ai-run` whose only task is BLOCKED →
  `task_blocked`; a fresh stand-alone `ai-run` then removes it (plan review P7). Run after an
  earlier fixture pipeline left its `run.json` (other arguments, e.g. `--max-fix-rounds 3`): no
  answer's argv starts with `.ai/bin/ai-pipeline`, and `resume` is `.ai/bin/ai-run` with the
  stand-alone run's own arguments (plan review round 3, P18).
- `test_escalation_wiring_cleared_on_human_start`: a new `ai-pipeline --approved` removes it.
- `test_escalation_wiring_ignores_last_error_text`: a `last-error` that says "plan review needs
  your decision" without a hint → kind `other`.
- `test_escalation_wiring_not_after_gate_change`: a fake session that tampers
  `.ai/bin/lib/workflow.py` (sentinel as in T306) → no escalation record, no sentinel.

### Validation
Targeted: `python3 -m unittest discover -s tests -k escalation` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes

- Mission control 2026-10-22 21:42: both sessions timed out (slow in-session gate, FL-38/FL-32). The uncommitted work covers every listed module and the handoff describes it. Mission control ran on that working tree: `python3 -m unittest -k escalation_wiring test_workflow` 9 tests OK (66 s), and the full `.ai/bin/ai-check`: Ran 1189 tests, OK (973 s). Next session: check the work against the acceptance criteria, finish anything missing, run only targeted tests (do NOT run the full `ai-check`; the runner's gate follows the session), then checkpoint.
- 2026-10-22 (claude, opus, resume): the checkpointed work in 0c0fe6e checked against every acceptance criterion: `test_escalation_wiring_task_blocked`, `_plan_review_stop_final_record`, `_validation_and_recovery`, `_recovery_crash_and_resume` (crash kind; a resuming recovery removes the record), `_standalone_ai_run`, `_cleared_on_human_start`, `_ignores_last_error_text`, `_not_after_gate_change` and `_standalone`. One write per chain: `ai_escalation_write` and `ai_human_stop` set `AI_ESCALATION_WRITTEN`; `ai_die` writes only when unset. The `ai-run` edit is one line. Docs in `docs/workflow.md` "Writers (T320)"; vault flow chart and hub Log already updated. No source change in this session. Targeted: `python3 -m unittest discover -s tests -k escalation` Ran 26 tests OK (141 s). Full gate: mission control's run on this same tree, 1189 OK (973 s); not rerun here, the runner's gate follows.
- 2026-10-22 (claude, opus, second resume): the runner's gate after c666859 failed on one timeout in an unrelated test (`test_committed_bytes_run_stops_on_a_filtered_final_handoff`, 25 s limit; whole run 1868 s against the usual ~900–970 s, so machine load). Recovery checkpoint 87b0099 recorded a gate PASS at 20:38:14Z on the same code. No source change. Targeted: `python3 -m unittest discover -s tests -k escalation` Ran 26 tests OK (134 s).

## T321 — Fix-round limit escalation on every finish path (RC-01 G9, B9, plan review round 3 P19)
Status: DONE
Dependencies: T320
Model: sonnet

### Goal
A run that ends at the fix-round limit with significant findings still finishes as today (draft
PR, local only, or pushed without `gh`) and leaves exactly one `fix_round_limit` escalation
record, whichever of the four finish paths it takes.

### Implementation notes
- Design: `.ai/current-plan.md` "G9"; spec B9. `scripts/ai-pipeline` has four successful finish
  paths, all through `finish()` (~89): `--no-pr` (~638), no `origin` remote (~658), `gh` missing
  after the push (~663) and the PR stage (~730) (plan review round 3, P19: the old plan covered
  only the first and the last).
- When the review loop breaks at the limit (~602–606, the `unresolved=1; … break` branch) set
  `fix_round_limit_hit=yes` (initialised `no` beside `unresolved=0` ~546; the deferred-only break
  ~622 does not set it).
- Centralised write in `finish()`, so every finish path writes it once and none can bypass it:
  before T302's `run-record end … finished`, `if [[ "$fix_round_limit_hit" == yes ]]; then
  ai_helper escalation write fix_round_limit review --run "$AI_RUN_ID" --review
  .ai/reviews/current.md 2>/dev/null || true; fi`. `finish` exits, so the write happens at most
  once per run; no write at the four call sites.
- `scripts/lib/workflow.py` `escalation write`: for kind `fix_round_limit` with `--review` and no
  `--finding`, the finding ids are the review's BLOCKER and MAJOR ids from the existing
  `finding_ids(content, level)` (~1108), read as a regular file ≤ 1 MB under the checkout; an
  unreadable review gives `findings: []`, never a failure.
- No change to the stop paths (T320) or the plan-review entry condition (~478).
- Docs: the "Escalation record" section names the fix-round case (the run finished, the human
  decides; written on every finish path). Flow unchanged beyond T320.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_escalation_wiring_fix_round_limit_paths`: one shared fixture (`--max-fix-rounds 1`, a
  fake review that always reports `M1` and `M2` as MAJOR and a minor `N1`), four subtests read
  after the pipeline process exited: (a) `--no-pr`; (b) a PR completed through the mock `gh`
  (draft PR created); (c) no `origin` remote; (d) an `origin` (local bare repo) and no `gh` on
  `PATH`. Each: exit 0, kind `fix_round_limit`, stage `review`, `findings` exactly `["M1",
  "M2"]`, review `.ai/reviews/current.md`, a `resume_more_rounds` answer whose argv has
  `--max-fix-rounds 2`, run record outcome `finished`.
- `test_fix_round_limit_written_only_in_finish`: a source check on `scripts/ai-pipeline`: the
  text `escalation write fix_round_limit` occurs exactly once, inside the body of `finish()`
  (written once per run because `finish` exits).
- `test_escalation_wiring_no_fix_round_record_without_limit`: a run whose review loop ends with
  no significant findings finishes (`--no-pr`) with no `escalation.json`.

### Validation
Targeted: `python3 -m unittest discover -s tests -k escalation` and `-k fix_round` (must say `Ran N
tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Implemented: `fix_round_limit_hit` set at the limit break in `scripts/ai-pipeline`, written once in
`finish()` before the run-record end; `escalation write` in `scripts/lib/workflow.py` fills the
BLOCKER/MAJOR ids from the review; `docs/workflow.md` updated; mock codex mode
`two-major-minor-always` added. Targeted: `python3 -m unittest discover -s tests -k fix_round_limit
-k no_fix_round_record` → `Ran 4 tests`, OK (105 s). Full gate `.ai/bin/ai-check`: NOT confirmed. It
exceeded the 600000 ms foreground timeout in this session (T320 saw a load-induced timeout too), so
no pass is claimed. Needs one rerun of the gate on an unloaded machine, then `ai-task set T321 DONE`.

## T327 — Plan-review escalation kinds end to end (RC-01 G9, split from T321 after plan review round 3)
Status: DONE
Dependencies: T320
Model: sonnet

### Goal
The three plan-review stops for a human leave the right escalation record after the pipeline
has exited: the supervision limit, `AI_SUPERVISE=0` and a needs-human plan disposition.

### Implementation notes
- Design: `.ai/current-plan.md` "G9" (answers per kind); T309 hints and T320 writes are the code
  under test; this task adds end-to-end tests and fixes only what they find in the hint or write
  wiring of these three stops (`scripts/ai-pipeline` `plan_decision_check` ~436–442, the
  `revision-reserve` refusals ~327–330 and ~529–531, the `AI_SUPERVISE != 1` stop ~523–526).
- No change to the plan-review entry condition (~478; batch 10). Read every record after the
  pipeline process exited (`AI_AUTO_RECOVER=0`).
- Docs: none beyond T320's section unless a test shows it is wrong. Flow unchanged.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py

### Acceptance criteria
- `test_escalation_wiring_plan_kinds`: a plan review over the supervision limit
  (`AI_SUPERVISE_PLAN_ROUNDS=1`, two BLOCKER plan reviews) → `plan_review_limit` with
  `resume_skip_plan_review` (argv = the run record's argv plus `--skip-plan-review`);
  `AI_SUPERVISE=0` with a BLOCKER plan review → `plan_review_limit`; a needs-human plan
  disposition → `needs_human_question` with a `review_plan` answer and the question's finding id.
- Each record's `run` is the pipeline's run id and its answers never contain an argv from an
  earlier manifest (P18).

### Validation
Targeted: `python3 -m unittest discover -s tests -k escalation` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Added `test_escalation_wiring_plan_kinds` (three subtests: supervision limit, `AI_SUPERVISE=0`,
needs-human disposition). It passes (`python3 -m unittest tests.test_workflow -k
escalation_wiring_plan_kinds`: Ran 1 test, OK); the wiring needed no script change. BLOCKED only
because `.ai/bin/ai-check` did not finish within the 600 s foreground limit (no failure output;
same load-induced timeout seen for T320). Rerun the gate; if green, set DONE.

## T325 — `--stop` of a stand-alone `ai-run` is a human stop (RC-01 G1, plan review round 3 P16)
Status: DONE
Dependencies: T319, T320
Model: opus

### Goal
`ai-pipeline --stop` on a checkout whose run is a stand-alone `ai-run` ends the session and
leaves outcome and escalation `human_stop`, exit 0, and a second `--stop` changes nothing; the
runner's own notification says "stopped by you".

### Implementation notes
- Mechanism (no new record logic): T315's `end` stores `human_stop` for `stopped` when the
  record has a stop request (under `runs/.lock`), T305's write refines `other` to `human_stop` for
  such a run, T316's `on_exit` ends the record and T320's `on_exit` writes the escalation. This
  task verifies the chain end to end and fixes what the test finds.
- `scripts/ai-run` `on_exit` stand-alone notification (~238–240): when `AI_RUN_ID` is set,
  `gate_ok=yes` and `ai_helper run-record stop-requested --run "$AI_RUN_ID"` exits 0 → `⛔ STOPPED
  by you: runner stopped at $active_task. Rerun ai-run --approved … to continue.` instead of the
  "needs you" text; otherwise unchanged. One `if`, kept small (batch 10).
- `ai-run` has no marker and no auto-recovery, so `--stop`'s completion (T319) finds nothing more
  to do; `run-stop` returns at "ended `human_stop`" (T308).
- Tests: a fixture stand-alone `ai-run --approved` started with `start_new_session=True` and a
  fake `claude` that writes its pid and sleeps 300 s; the test signals nothing itself, `--stop`
  does (it signals only the fixture's recorded group or pid).
- Docs: `docs/workflow.md` stop section: `--stop` also stops a stand-alone `ai-run`. Flow
  unchanged beyond T308.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_stop_command_stops_a_standalone_ai_run`: while the fake session sleeps, `ai-pipeline
  --stop <checkout>` exits 0 within a scaled 60 s with `Run <id> stopped (stopped by you).`; the
  `ai-run` process and the fake claude are gone; the run record (kind `ai-run`) has outcome
  `human_stop` and `stop_requested.via` `ai-pipeline --stop`; `escalation.json` has kind
  `human_stop`, that run id and no answer whose argv starts with `.ai/bin/ai-pipeline`; the
  notification log has one `⛔ STOPPED by you:` line and no `needs you` line.
- In the same test a second `--stop` exits 3 with "already stopped by you"; record and
  escalation bytes unchanged.
- `test_standalone_ai_run_interrupt_without_request`: SIGTERM to the fixture `ai-run` pid without
  a stop request still ends `stopped` with today's "needs you" notification (spec B23).

### Validation
Targeted: `python3 -m unittest discover -s tests -k stop_command` and `-k standalone` (must say
`Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-22: `scripts/ai-run` `on_exit`: one `if` — stand-alone, `AI_RUN_ID` set, gate ok and
`run-record stop-requested` exits 0 → `⛔ STOPPED by you: runner stopped at $active_task. Rerun
ai-run ${run_argv[*]} to continue.`; otherwise the "needs you" text as before. The record and
escalation chain (T315 `end`, T305 refinement, T320 `on_exit` write) needed no change: the new
test confirmed `human_stop` for both. Tests: `test_stop_command_stops_a_standalone_ai_run`,
`test_standalone_ai_run_interrupt_without_request`. Docs: docs/workflow.md stop section, README.
Evidence: `-k stop_command` Ran 12 OK (23.6 s); `-k standalone` Ran 10 OK (61.4 s). The full
`.ai/bin/ai-check` (~900 s) is longer than the session's 600 s tool limit, so the runner's gate
gives the full result.

## T310 — ai-task takes the checkout lock and can commit `.ai/tasks.md` (RC-01 G7)
Status: DONE
Dependencies: none
Model: opus

### Goal
Humans and apps change a task safely: `ai-task set ID STATUS --commit` refuses while a run holds
the checkout and commits only `.ai/tasks.md` with a standard message, so a stopped pipeline
accepts the checkout afterwards. Plain `set` (sessions) is unchanged.

### Implementation notes
- Design: `.ai/current-plan.md` "Task commands", function `task_change` in `scripts/ai-task`.
- Lock: `exec 9>.ai/local/workflow.lock; flock -n 9 || { echo 'A run is active in this checkout;
  nothing changed.' >&2; exit 75; }` (never waits; never `ai_lock`, whose PPID shortcut and
  messages are for runners). Branch: `git symbolic-ref --quiet --short HEAD`, refuse detached and
  `main|master|develop|development|production|release|release/*`.
- `--commit` (last argument): before the change `git status --porcelain --untracked-files=all`
  must be empty (refuse, exit 1, nothing changed); after it `git commit --only -m "chore(ai): set
  ID to STATUS (ai-task)" -- .ai/tasks.md` (hooks run; never `--no-verify`), then the checkout
  must be clean; a failed commit → `ID is STATUS but not committed; commit .ai/tasks.md yourself.`
  exit 1, nothing reverted.
- After the helper writes, `ai_helper tasks check`; failure → restore the saved original bytes,
  exit 1.
- Usage lines and README task-command paragraph. Flow unchanged (a command, not a step).

### Likely affected modules
scripts/ai-task, tests/test_workflow.py, README.md

### Acceptance criteria
- `test_ai_task_commit_sets_and_commits`: in a temp repo, `ai-task set T001 TODO --commit` on a
  BLOCKED task makes one commit touching only `.ai/tasks.md` with the standard subject; the
  checkout is clean.
- `test_ai_task_commit_refuses_while_locked`: the test holds `.ai/local/workflow.lock` → exit 75,
  bytes unchanged, no commit.
- `test_ai_task_commit_refuses_dirty_or_protected`: another dirty file, a `master` branch, a
  detached HEAD → exit 1, nothing changed.
- `test_ai_task_commit_hook_failure`: a failing `pre-commit` hook → exit 1 with the "not committed"
  message, status changed in the file.
- `test_ai_task_plain_set_unchanged`: `ai-task set T001 DONE` without `--commit` works while the
  lock is held (sessions inside a run).

### Validation
Targeted: `python3 -m unittest discover -s tests -k ai_task` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-23: `scripts/ai-task` `task_change COMMIT SUBJECT NOT-COMMITTED-MESSAGE HELPER-ARGS…`
(for T312/T322): `exec 9>.ai/local/workflow.lock; flock -n 9` (exit 75 "A run is active in this
checkout; nothing changed."), branch via `git symbolic-ref` (detached and protected names → exit
1), with COMMIT a clean `git status --porcelain --untracked-files=all` first; the original bytes
are saved under `.ai/local/`, the helper and `tasks check` run, and on failure the bytes are
restored ("Nothing changed.", exit 1). Then `git commit --quiet --only -m SUBJECT -- .ai/tasks.md`
(hooks run) and a clean check; failure → "ID is STATUS but not committed; commit .ai/tasks.md
yourself.", exit 1, nothing reverted. Setting the current status again makes no commit (no empty
commit, exit 0). `set ID STATUS --commit` uses it; plain `set` is unchanged. Usage lines and
README task-command paragraph updated; flow unchanged. Tests: the five named above (the refusal
test also covers a change that breaks the queue). Evidence: `-k ai_task` Ran 7 OK (3.2 s). The
full `.ai/bin/ai-check` (~900 s) exceeds the session's 600 s tool limit, so the runner's gate
gives the full result.

## T311 — SKIPPED status with a host skip record (RC-01 G6, queue)
Status: DONE
Dependencies: none
Model: opus

### Goal
A task can be skipped with a recorded reason: SKIPPED counts as finished for the queue only when
the host authorized the skip, so no agent session can skip a task by editing its status line;
the authorization holds for every branch and worktree of the repository on this host, so a
committed skip stays valid on the next branch (plan review P6).

### Implementation notes
- Design: `.ai/current-plan.md` "SKIPPED"; spec FR-9, B13. Authorization: an empty file
  `<state root>/skips/<64 hex>` (via `check_state_root`, like `binding_dir()`), the hex being
  sha256 of `<sorted root commits (git rev-list --max-parents=0 HEAD), space-joined>\0<the task's
  heading line>\0<its Skipped line>`; created with `O_CREAT|O_EXCL` (an existing one is fine), no
  lock, never read-modify-written. A function `skip_authorized(task)` keeps the rule in one place
  (T322 uses it).
- `scripts/lib/workflow.py` `tasks()` (~451): accept SKIPPED; a SKIPPED task must have exactly one
  `Skipped (YYYY-MM-DD, ai-task skip): …` line whose authorization exists, else fail `T…: SKIPPED
  without a host skip record (use ai-task skip, or ai-task skip ID --reauthorize on another
  host)`. Give `tasks()` a keyword to turn only this check off (T322). The dependency rule (~465): a
  DONE/IN_PROGRESS task needs each dependency DONE or SKIPPED. `next` (~774): SKIPPED is not
  eligible and satisfies dependencies. `complete` (~750): every task DONE or SKIPPED (an empty
  queue still fails). `untouched`, `newly-done`, `counts`, `progress` unchanged
  (DONE only). `tasks set` (~807) refuses SKIPPED (`use ai-task skip`).
- `workflow.py tasks skip ID REASON`: refuses DONE, IN_PROGRESS, SKIPPED and any task that a task
  not DONE or SKIPPED depends on (names them); REASON one line, 1–500 chars, no control
  characters or backticks; creates the authorization for the new lines first, then writes
  `Status: SKIPPED` and appends the `Skipped (…)` line under `### Result / notes` (a failed write
  leaves only an unused authorization, never an unauthorized SKIPPED).
- Planning DONE-block guard (grep `DONE task was changed or removed` in `scripts/ai-run` and its
  helper in `workflow.py`): SKIPPED blocks are protected the same way.
- `pr-body`: a "Skipped tasks" line listing `T…: reason` when any task is SKIPPED.
- `templates/.ai/prompts/runner.md` (~68) and `triage.md` (~74): add "Never set SKIPPED; only the
  human skips a task (`ai-task skip`)." (templates only, not `.ai/prompts`).
- Docs: `docs/workflow.md` task statuses. Flow chart: "Inside one task" pick node says SKIPPED
  tasks are passed over; `updated:` date; hub Log line.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, templates/.ai/prompts/runner.md, templates/.ai/prompts/triage.md, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_skipped_task_with_host_record`: `tasks skip T002 "not needed"` on a TODO leaf task: `next`
  passes over it, `complete` passes when the others are DONE, `pr-body` lists `T002: not needed`;
  then a committed new TODO task with `Dependencies: T002` is eligible (plan review P10: the
  refusal rule stays; dependency satisfaction is tested on a dependent added after the skip).
- `test_skipped_task_without_host_record_is_invalid`: hand-editing `Status: SKIPPED` (with or
  without a forged `Skipped (…)` line), and an authorized line moved to a task with another
  heading, fail `tasks check` with the named message.
- `test_skipped_task_survives_new_branch_and_worktree`: after a committed skip, `tasks check`
  passes on a new branch created from it, after merging it into another branch, and in a second
  `git worktree` of the same repository (same state root); with an empty state root it fails.
- `test_skip_refuses`: DONE, IN_PROGRESS, already SKIPPED, a task with an unfinished dependent, a
  two-line reason → refused, bytes unchanged.
- `test_tasks_set_refuses_skipped`: `tasks set T001 SKIPPED` fails.
- `test_planning_keeps_skipped_blocks`: the planning guard stops when a SKIPPED block changed.

### Validation
Targeted: `python3 -m unittest discover -s tests -k skip` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-23 (Claude): done. `workflow.py`: `STATUSES`/`FINISHED`, `skip_key`, `skips_dir`,
`skip_authorized(task)`; `tasks(text, check_skips=True)`; `tasks skip ID REASON` (`tasks_skip`,
authorization created exclusively before the queue write, queue mode kept); `tasks set` refuses
SKIPPED ("use ai-task skip"); `next`/`complete`/dependency rule accept SKIPPED; `newly-done`'s
earlier queue parsed with `check_skips=False`; `plan-keeps-done` protects SKIPPED blocks;
`pr-body` "Skipped tasks:" line. `scripts/ai-run` planning prompt names SKIPPED; runner/triage
templates say only the human skips. Tests: the six acceptance tests (names as in the criteria);
`test_plan_session_revision_keeping_done_tasks_completes` follows the new prompt wording.
Evidence: `-k skip` Ran 23 tests OK; plan_keeps_done/plan_session_revision/pr_body/Docs Ran 29 OK;
`.ai/bin/ai-check` PASS, Ran 1206 tests OK (977.7 s). The `ai-task skip` wrapper is T312.

## T312 — `ai-task retry`, `model` and `skip` (RC-01 G4, G5, G6)
Status: DONE
Dependencies: T310, T311
Model: opus

### Goal
Humans and apps return a task to TODO with a note, set a task's model, or skip it with a reason,
each under the checkout lock, optionally committed.

### Implementation notes
- `scripts/ai-task` on T310's `task_change`: `retry ID --note TEXT [--commit]` (helper `tasks
  retry ID TEXT`: BLOCKED → TODO, TODO keeps its status; refuses DONE, IN_PROGRESS, SKIPPED;
  appends `Human note (YYYY-MM-DD, ai-task retry): TEXT` under `### Result / notes`; subject
  `chore(ai): return ID to TODO (ai-task)` or `chore(ai): note on ID (ai-task)`); `model ID MODEL
  [--commit]` (helper `tasks set-model ID MODEL`: TODO or BLOCKED only, MODEL
  `^[A-Za-z0-9._:\[\]-]{1,64}$`, replaces the `Model:` line or inserts it right after
  `Dependencies:`; subject `chore(ai): set ID model to MODEL (ai-task)`); `skip ID --reason TEXT
  [--commit]` (T311's `tasks skip`; subject `chore(ai): skip ID (ai-task)`). All three take the
  lock even without `--commit`.
- Text validation as T311 (one line, 1–500 chars, no control characters or backticks).
- Usage text, README task commands. Flow unchanged beyond T311.

### Likely affected modules
scripts/ai-task, scripts/lib/workflow.py, tests/test_workflow.py, README.md

### Acceptance criteria
- `test_ai_task_retry_with_note`: BLOCKED → TODO with the note line, one commit with the subject;
  a TODO task gets only the note; DONE refused.
- `test_ai_task_model`: replaces `Model: sonnet` with `opus`; inserts a missing `Model:` line after
  `Dependencies:`; an invalid model and a DONE task are refused; `tasks model T…` prints the new
  value.
- `test_ai_task_skip_command`: `skip T002 --reason "covered by T003" --commit` → SKIPPED, the
  reason line, the host record, one commit; `tasks check` passes.
- `test_ai_task_subcommands_refuse_while_locked`: each of the three → exit 75 while the lock is
  held, bytes unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k ai_task` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
DONE 2026-10-23. `scripts/ai-task`: `retry ID --note TEXT`, `model ID MODEL`, `skip ID --reason
TEXT` (each `[--commit]`, through `task_change`, so the lock is taken even without `--commit`;
retry's subject is chosen under the lock). `workflow.py`: `tasks retry`, `tasks set-model`;
`task_line_positions` returns a dict; `append_note`/`write_queue` shared with `tasks skip`.
Tests `test_ai_task_retry_with_note`, `test_ai_task_model`, `test_ai_task_skip_command`,
`test_ai_task_subcommands_refuse_while_locked`. README, docs/workflow.md. Flow unchanged.
Validation: `-k ai_task` Ran 11 OK; `-k skip -k task_set -k tasks` Ran 43 OK;
`.ai/bin/ai-check` PASS, Ran 1210 OK (956.2 s).

## T322 — `ai-task skip ID --reauthorize` for a committed skip on another host (RC-01 G6, plan review P6)
Status: DONE
Dependencies: T312
Model: opus

### Goal
On another host, or after the state directory was lost, the human re-authorizes a skip that is
already committed, even though that skip makes the queue invalid until then; a session inside a
run still cannot.

### Implementation notes
- Design: `.ai/current-plan.md` "Reauthorize (T322)"; spec FR-9, B13.
- `workflow.py tasks skip-reauthorize ID`: parse with T311's skip check off; require `Status:
  SKIPPED` and exactly one `Skipped (YYYY-MM-DD, ai-task skip): …` line; create the
  authorization with T311's function; then run the normal `tasks check` and report its result
  (another fault still fails). No queue change, no commit.
- `scripts/ai-task skip ID --reauthorize`: T310's lock (exit 75 while a run holds the checkout)
  and branch check; no `--commit` (nothing to commit; refuse the combination). The `tasks check`
  inside `task_change` is the final one above. Usage text and README line. Flow unchanged.

### Likely affected modules
scripts/ai-task, scripts/lib/workflow.py, tests/test_workflow.py, README.md

### Acceptance criteria
- `test_ai_task_skip_reauthorize`: a committed SKIPPED task with an empty state root fails `tasks
  check`; `ai-task skip T002 --reauthorize` makes it pass, changes no file in the checkout and
  makes no commit.
- `test_ai_task_skip_reauthorize_refuses`: a TODO task, a SKIPPED task without a `Skipped (…)`
  line, `--commit`, and a held checkout lock (exit 75) → refused, no authorization created.

### Validation
Targeted: `python3 -m unittest discover -s tests -k ai_task` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
2026-10-23: `workflow.py tasks skip-reauthorize ID` (handled before the normal parse, queue read
with `check_skips=False`; requires SKIPPED and exactly one valid Skipped line; shared
`create_skip_authorization`) and `ai-task skip ID --reauthorize` (`task_change`, no commit;
`--commit` → exit 2; a failed final `tasks check` says the skip is authorized but the queue has
another fault). Tests `test_ai_task_skip_reauthorize`, `test_ai_task_skip_reauthorize_refuses`.
Evidence: `-k ai_task` Ran 13 tests OK; `.ai/bin/ai-check` PASS, Ran 1212 tests OK (978.6 s).
README, docs/workflow.md; flow unchanged.

## T324 — `exec-logged` accepts the detached pipeline's log name (RC-01 G11, plan review round 2 P12)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
`workflow.py exec-logged` accepts `pipeline-<UTC stamp>-<8 hex>.log` beside today's
`plan-<UTC stamp>-<8 hex>.log`, with the same exclusive, no-symlink creation in the pinned
`.ai/local`, so T313 can launch the pipeline through it. Nothing else changes.

### Implementation notes
- `scripts/lib/workflow.py` `EXEC_LOG_NAME` (~5069): `(?:plan|pipeline)-\d{8}T\d{6}Z-[0-9a-f]{8}\.log`
  with `fullmatch` as today. No other change to `exec_logged` (~5072–5112): the `O_EXCL |
  O_NOFOLLOW | O_NONBLOCK` creation, the regular-file check and the pinned `.ai/local` stay
  exactly as they are.
- Extend the existing tests (`exec_logged_fixture`, `tests/test_workflow.py` ~2516–2607). Docs:
  the `exec-logged` mention in `docs/workflow.md`, if it names the log pattern. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `test_exec_logged_accepts_both_log_prefixes`: `plan-20261021T210000Z-0123abcd.log` and
  `pipeline-20261021T210000Z-0123abcd.log` both create their log and run the command.
- `test_exec_logged_rejects_bad_names_and_a_relative_command` additionally refuses (exit 2,
  nothing created) `pipelines-…`, `pipeline-…` with 7 hex or uppercase hex, `pipeline-….log.x`,
  `../pipeline-….log` and a `pipeline/` prefix.
- Existing `test_exec_logged_*` pass (symlink, FIFO, symlinked `.ai/local`, no truncation,
  concurrent launches).

### Validation
Targeted: `python3 -m unittest discover -s tests -k exec_logged` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes
Implemented: `EXEC_LOG_NAME` accepts `(?:plan|pipeline)-…`; `test_exec_logged_accepts_both_log_prefixes`
added, bad-name test extended, `docs/workflow.md` notes the second prefix. Targeted
`python3 -m unittest discover -s tests -k exec_logged`: Ran 8 tests, OK.
BLOCKED only on the gate: `.ai/bin/ai-check` exceeded the 600000 ms foreground timeout (the previous
full gate rerun took 973 s) and was moved to the background, so no gate result was seen. The
runner's own gate run decides; rerun it and set the task DONE if it passes.

## T313 — `ai-pipeline --detach`: own systemd user service, recorded log path (RC-01 G11)
Status: IN_PROGRESS
Dependencies: T319, T324
Model: opus

### Goal
`ai-pipeline --detach <arguments>` starts the run in its own `systemd-run --user` service, its
output in a log the run record names, confirms the start through the run record, and prints how
to follow and stop it; the printed stop command really stops it. Without `systemd-run` it refuses
(the `setsid` fallback is cut, spec Out, plan review P3).

### Implementation notes
- Design: `.ai/current-plan.md` "G11"; spec FR-10, B14. Dispatch at the top of `ai-pipeline`
  beside `--stop` (T308's dispatch block: add the branch there). `--approved` must be among the
  remaining arguments (else the usual message). `systemd-run` not executable → exit 1 with the
  plan's message, nothing started. `ai_root` first (paths check); no lock (the child takes it).
  Pass the remaining arguments through unchanged; resolving a caller-relative `--knowledge-dir`
  before `ai_root` is T326 (plan review round 3, P17), so this task's tests use absolute paths.
- Log name `pipeline-$(date -u +%Y%m%dT%H%M%SZ)-<8 hex>.log` in `.ai/local`, created by
  `workflow.py exec-logged` (as `scripts/ai-plan` ~56–64), which accepts this prefix since T324
  (plan review P12). The unit form of the plan (env: `PATH`,
  `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and every `AI_*` variable without NUL or newline, except
  `AI_RUN_ID`, plus `AI_LAUNCHER=detach-systemd`, `AI_RUN_LOG=<abs log>`), unit name
  `ai-pipeline-<checkout base name, [A-Za-z0-9._-] only>-<epoch>`.
- Confirm: poll `ai_helper run-record show` every 0.2 s up to `AI_PLAN_ACK_SECONDS` (default 20,
  validated as in `ai-plan`) for a record started after the launch whose `log` equals the log
  path; print `Pipeline started: pid N, log PATH`, `Follow: tail -f PATH`, `Stop:
  <AI_BIN>/ai-pipeline --stop <checkout>`; not confirmed → the log's last 10 lines (regular file
  only), exit 1, nothing stopped.
- Tests use a fake `systemd-run` (Python on `PATH`) that records its argv and starts the command
  with `start_new_session=True` and default signal dispositions, as systemd does; never the real
  one. The test cleans up by stopping the fixture through `--stop`.
- Docs: README and `docs/workflow.md` (detach; systemd only). Flow chart: the start of "The big
  picture" notes `--detach`; `updated:` date; hub Log line.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- `test_detach_systemd_run_arguments`: the fake `systemd-run` records its argv and runs the
  command: the argv has `--user`, `--collect`, `--service-type=exec`, the working directory,
  `AI_LAUNCHER=detach-systemd`, `AI_RUN_LOG`, no `--detach` in the pipeline arguments; the fixture
  pipeline's run record has launcher `detach-systemd` and that log; the output names pid, log,
  `tail -f` and `--stop`.
- `test_detach_then_stop`: a detached fixture pipeline with a sleeping fake session; the printed
  `--stop` command exits 0 within a scaled 60 s, the pipeline and the fake session are gone,
  outcome `human_stop`, the log holds the pipeline output.
- `test_detach_refuses_without_systemd_run`, `test_detach_refuses_without_approved` and
  `test_detach_not_confirmed`: no `systemd-run` on `PATH` → exit 1 with the message; missing
  `--approved` → exit 1; both start nothing; a fake launcher that starts nothing → exit 1 within
  the scaled bound.
- The run manifest's args never contain `--detach`.

### Validation
Targeted: `python3 -m unittest discover -s tests -k detach` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes

## T326 — `--detach` resolves `--knowledge-dir` against the caller's directory (RC-01 G11, plan review round 3 P17)
Status: TODO
Dependencies: T313
Model: opus

### Goal
`ai-pipeline --detach … --knowledge-dir DIR` means the same directory as the foreground command:
DIR is resolved against the caller's working directory before the dispatch changes to the
checkout root, and the detached child gets the absolute path in the same argument position.

### Implementation notes
- Cause: the `--detach` dispatch (T313) calls `ai_root` (`scripts/lib/common.sh` ~126–132, `cd`
  to the checkout root) before it launches the child, which then resolves `--knowledge-dir`
  (`scripts/ai-pipeline` ~52–58) against the root. `scripts/ai-plan` ~23–28 resolves it first.
- In the dispatch, before `ai_root`: walk the remaining arguments once, copying them into
  `detach_args` in order; for `--knowledge-dir` require a value (else `Missing knowledge
  directory`, exit 1, nothing started) and an existing directory (else `Knowledge directory must
  already exist.`, exit 1, nothing started), and copy `--knowledge-dir "$(cd -- "$2" && pwd -P)"`.
  A value of another option is copied as is and never inspected as an option (the pipeline's
  own parser validates everything else). Only `--knowledge-dir` takes a path in `ai-pipeline`'s
  options (`--base` and `--pr-base` are refs).
- `systemd-run` gets `exec-logged … -- <AI_BIN>/ai-pipeline "${detach_args[@]}"`.
- Tests reuse T313's fake `systemd-run` (argv recorded, command started with
  `start_new_session=True`) and stop the fixture with the printed `--stop` command.
- Docs: README/`docs/workflow.md` detach paragraph: paths are resolved against your working
  directory, as in the foreground. Flow unchanged.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- `test_detach_knowledge_dir_is_caller_relative`: checkout root with `notes/` holding file
  `root-marker` and `sub/notes/` holding `sub-marker`; run `ai-pipeline --detach --approved
  --no-pr --knowledge-dir ./notes --sessions 1` with `cwd=<checkout>/sub` → the recorded
  `systemd-run` argv ends with `ai-pipeline --approved --no-pr --knowledge-dir <abs
  checkout>/sub/notes --sessions 1` (order kept), and the detached fixture pipeline's run record
  `argv` and the manifest `args` hold `<abs checkout>/sub/notes`, never `<abs checkout>/notes`.
- `test_detach_knowledge_dir_only_caller_relative_exists`: only `sub/notes/` exists (no root
  `notes/`), launched from `sub` → started, and the child argv holds `<abs checkout>/sub/notes`.
- `test_detach_knowledge_dir_missing`: only the root `notes/` exists (not `sub/notes/`) and the
  launch is from `sub`, neither exists, or `--knowledge-dir` is the last argument
  → exit 1 with the message, the fake `systemd-run` never called, no log created.

### Validation
Targeted: `python3 -m unittest discover -s tests -k detach` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes

## T314 — Docs, flow chart audit and the mission-control handoff note (batch 11)
Status: TODO
Dependencies: T313, T321, T322, T325, T326, T327
Model: haiku

### Goal
README, `docs/workflow.md`, the vault flow chart and the handoff agree with the code for stop,
escalation record, run record, task commands and detach, and mission control has one note listing
the new commands and record paths.

### Implementation notes
- Read the code first (`ai-pipeline --help`, `ai-task` usage, `workflow.py` `run-record`,
  `escalation`, `run-stop`) and fix any doc mismatch; the code is the source of truth.
- README: command list (`ai-pipeline --stop`, `--detach` (systemd only), `ai-task retry`,
  `model`, `skip`, `skip --reauthorize`, `--commit`). `docs/workflow.md`: one "Run controls"
  section that links the stop, escalation record, run record and task command paragraphs added
  by T301–T327, and says that `--detach` needs `systemd-run` (the `setsid` fallback is later
  work).
- Vault `agents-flow.md`: check the "Stopped by you" path, the escalation record bullet, the
  SKIPPED note and `--detach` exist and match; `updated:` date; one hub Log line in `agents.md`
  for the audit. Never tick vault checkboxes.
- `.ai/handoff.md`: "For mission control (phase 2 switch)" with every command (exact argv,
  exit statuses 0/1/3/4/75), record paths (`<state root>/reviews/<16 hex>/runs/current`,
  `runs/<id>.json`, `escalation.json`, `<state root>/skips/<64 hex>`, `.ai/local/pipeline-*.log`),
  schema versions, the run id format (`<stamp>-<pid>-<seq>`), the kinds list, and that `--stop`
  sends SIGTERM; "Manual testing for the human"
  updated; `## Flow chart` first line "Flow chart updated (…)".
- Add a docs consistency check if the existing `DocsConsistencyTest` pattern covers command lists
  (e.g. every `ai-task` subcommand in the usage text appears in README).

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, tests/test_workflow.py

### Acceptance criteria
- README and `docs/workflow.md` name every new command, record path and exit status exactly as the
  code does.
- The vault flow chart shows the human stop, the escalation record, SKIPPED and `--detach`; its
  `updated:` date is the task's date; a hub Log line exists.
- The handoff has the mission-control note and a `## Flow chart` section starting with "Flow chart
  updated".
- `DocsConsistencyTest` passes.

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` (gate rule in the queue header).

### Result / notes

