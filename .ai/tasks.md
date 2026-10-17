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
  logic: when not `alive` and `marker_snapshot(marker)` is None, run THIS copy's `python3
  <bin_dir>/lib/workflow.py run-manifest limit-at` in `root` (as `start_recovery` runs
  `run-manifest gate`; the only question is "is a relaunch scheduled, and when?"). Exit 0 →
  `scheduled_ns = AT * 1e9`, else 0. With `args.recover` and `scheduled_ns <= now` →
  `start_recovery(…, stage='usage limit relaunch')`; None → nothing more (ai-recover announces
  itself) and continue with the normal probe; a refusal → notify `⛔ STOPPED, needs you: the
  usage-limit relaunch could not start: <reason>.` once per AT (key `relaunch:<AT>` kept in the
  dedupe record's `active` list while the schedule is unchanged). `scheduled_ns > now` → nothing
  launched; the value only feeds the stall rule below (a pending schedule without `--recover`
  still suppresses the stall alarm: the run is waiting, not killed).
- Stall incident (~443–451): add `now >= max(paused_until(local), scheduled_ns)`. The host
  schedule is the authority (plan review round 3, P2: `limit-hold` restores a schedule whose
  pauses.log line was never written, and `.ai/local` is agent-writable anyway); ai-recover's
  pauses.log line (T003) stays as the quiet-time input of the hung rule and as history.
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
    writes no last-error, sends no notification;
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
     the reset.`;
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


## T012 — Preserved-work binding: the relaunch exception admits the exact preserved tree (MC-01 part 1, plan review round 2 P3/P9 design task)
Status: TODO
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
  shell passes no binding value): `limit-schedule AT CAP` records `limit_head` and `limit_tree`;
  `limit-verify` (read only) recomputes both and exits 0 silently only when both equal the
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


## T014 — Relaunch binding verification contract: one verification site before any checkout mutation (MC-01 part 1, plan review round 3 P9/P10 design task)
Status: TODO
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


## T011 — Limit relaunch resumes preserved task work in the normal implementation session (MC-01 part 1, plan review round 1 P3)
Status: TODO
Dependencies: T014
Model: opus

### Goal
A usage limit that stops an implementation session after it edited source or marked its task
IN_PROGRESS no longer ends in ⛔ after the reset: the scheduled relaunch hands exactly that
preserved tree, once, to the normal implementation session of the same run, which reconciles it
under the unchanged validation and checkpoint safeguards, with no recovery decision session.

### Implementation notes
- Design: `.ai/current-plan.md` "Relaunch schedule lifecycle", part "Preserved task work", and
  "Preserved-work resume (plan review round 2 redesign)" including "Verification point (round
  3 redesign, T014)". T001/T012 provide `run-manifest limit-arm` / `limit-armed` (no arguments:
  they recompute HEAD and the tree digest, T012) / `limit-disarm`; T003/T012/T014 verify the
  checkout first and arm it in ai-recover's claimed-relaunch path only for the exact tree
  recorded at scheduling.
- An armed tree is accepted only where today's clean-checkout checks stand between the resumed
  pipeline and ai-run's first implementation session, and only when ALL hold: the process is a
  resume (`AI_RECOVERY_ATTEMPT` set; a human start runs `run-manifest start`, which drops the
  arm), `ai_helper run-manifest limit-armed` exits 0, and no stage is open. Factor the three
  conditions into one shell function per script (`armed_resume`). Sites (re-check line numbers): `scripts/ai-pipeline` ~123–125 (start-from-clean) and
  `reconcile_disputes` ~326–327 (with status `none` and a dirty tree it would `recheck_fail`;
  with an armed tree and status `none` it returns as for a clean one; a pending/verified
  re-check keeps today's rule); `scripts/ai-run` ~148–149. The `tasks untouched` plan-review
  gate (~429) needs no change (a touched queue skips the plan review, as today). Trace every
  other check on that path (e.g. `ensure_validated`, ~236; anything between ~384 and ~501) and
  list in the result which you changed and why the rest are not reached; do not relax any check
  after the first implementation session.
- No runnable task (plan review round 2, P3): the session may have marked its task DONE and
  then hit the limit before committing (the last task, or a middle one). `scripts/ai-pipeline`
  ~499 (`if ! ai_helper tasks complete; then … ai-run`) runs ai-run also when `armed_resume`
  holds, whatever `tasks complete` says, so the arm is always consumed by ai-run and the
  review/publish path never meets the dirty tree.
- ai-run consumes the arm exactly once: when the armed exception admits the dirty tree it runs
  `ai_helper run-manifest limit-disarm` (failure → `ai_die`, nothing started) before the
  session loop and prints `Resuming preserved work of the usage-limit stop.`. Then
  `newly=$(ai_helper tasks newly-done HEAD)` (T012):
  - exactly one ID → *armed checkpoint* of that task, before any session: refactor the loop's
    `DONE)` branch (ai-run ~669–703 plus the runner-bookkeeping commit and the post-commit
    `verify_checkpoint` ~713–720) into one function `checkpoint_done TASK` used by the loop and
    here, unchanged in substance: full `ai-check` (failure → task back to IN_PROGRESS, state
    blocked, `ai_die`), tier-1 commit `chore(ai): checkpoint <id> (validated; the session did
    not commit)` with `checkpoint-guard`, stamp verify and `committed-matches-worktree`, the 🔧
    notification, `ai_log`, bookkeeping commit. `task_outcome done` only if it works without an
    attempt opened in this process (say which in the result). Then the loop starts as today
    (final validation and handoff when nothing is left, else the next task);
  - none → the first iteration works on `tasks next` as today (the IN_PROGRESS task first,
    workflow.py ~642–647); its prompt already says `Reconcile interrupted work first`;
  - more than one → `ai_die 'Preserved work marks several tasks DONE; inspect it before
    continuing.'` (the arm is gone, so the next recovery takes the normal rules).
  A clean tree never consumes the arm (`clear-attempts` at finish drops it).
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
  - a tree with two tasks newly DONE → `Preserved work marks several tasks DONE`, no session;
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
    (T012's binding) → `Start from a clean checkpoint`, nothing committed.
- `test_recovery_*`, `test_usage_limit_*`, the re-check/dispute tests and all pipeline tests pass
  unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k limit_relaunch_preserved` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recheck` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
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
  the shared options is ai-run's; ai-plan checks only its own (`--detach`, the prompt file exists,
  is regular and readable; resolve it to an absolute path before any `cd`).
- Foreground: `exec "$AI_BIN/ai-run" --plan "$prompt" "${rest[@]}"` (same PID: the dashboard,
  watchdog and lock see an `ai-run` runner, nothing else changes).
- `--detach`: checks only as far as needed to find `.ai/local` (inside a Git checkout with a
  real `.ai`); log name `plan-$(date -u +%Y%m%dT%H%M%SZ)-<8 hex from /dev/urandom>.log`
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
    with `.ai/local` replaced by a symlink to an outside directory → exit ≥ 1, `ended early`,
    nothing created outside; a sentinel symlink planted at every `.ai/local/plan-*` name the
    test can predict is never written (sentinel byte-identical);
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
Dependencies: T011, T014, T004, T007, T009
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

