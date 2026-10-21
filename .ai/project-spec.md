# Spec: Flow batch 11: run controls for humans and apps (RC-01)

## Objective
Planned 2026-10-21 by an unattended planning session on `fix/flow-batch-11` (from
`fix/flow-batch-9` at 4fea72d; batch 9 is nearly complete there but not merged; this PR targets
`fix/flow-batch-9` until that merges). Scope chosen by mission control on 2026-10-21 with Zack's
delegation: vault `agents-backlog.md` **RC-01** (toolkit support for mission-control run
controls, gaps G1 to G11 found by mission-control's phase 2 planner), read with FL-04, OR-04 and
AD-4 and mission-control's phase 2 spec (`~/Projects/wt/mc-p2/.ai/project-spec.md`, "Toolkit
facts" and "Toolkit gaps").

Batch 10 (TS-01 targeted tests, ME-01 flow events and `ai-status --metrics`, FL-39 plan review
skip) is built in parallel on its own branch from the same commit. This batch therefore keeps its
edits to the session contract in `scripts/ai-run`, `tests/run_parallel.py`, `scripts/ai-status`
and the plan-review entry condition in `scripts/ai-pipeline` (~line 478) small and local, and
does not touch `ai-status` or `tests/run_parallel.py` at all.

In priority order:
1. **G1 clean human stop**: `ai-pipeline --stop [CHECKOUT]` ends the checkout's run, recorded as
   "stopped by the human", never auto-resumed. The pipeline traps INT/TERM so a terminal Ctrl-C
   or a service stop is recorded the same way.
2. **G2** an interrupt reaches the running agent session or gate under `timeout` at once; partial
   work is preserved exactly as for a timeout.
3. **G9 escalation record**: one schema-versioned JSON record in host state whenever the run
   stops for a human: kind from a fixed list, stage, task ids, evidence pointers, allowed answers
   as toolkit commands. Cleared when the run resumes.
4. **G3 run record**: one record per run (kept, bounded), with start time, process identity,
   launcher, exact argument array, log path, base, branch, end time and outcome; `ai-run` alone
   writes one too.
5. **G7, G4, G5, G6 task commands**: `ai-task` changes for humans and apps take the checkout lock,
   refuse while a run is active and can commit only `.ai/tasks.md` (`--commit`); new `retry`,
   `model` and `skip` subcommands; a SKIPPED status.
6. **G11** `ai-pipeline --detach`: start the run in its own service or session, record the log
   path, print how to follow and stop it.
7. Docs: README, `docs/workflow.md`, the vault flow chart, and a handoff note for mission control.

## Verified against the code (4fea72d, 2026-10-21)
Every gap is still open; none is dropped. Details:
- **G1 open.** `scripts/ai-pipeline` has no signal trap. It writes `.ai/local/pipeline.active`
  (~87) and removes it in `finish` (~89–96) and `ai_die` (`scripts/lib/common.sh` ~11–28). After
  a failing child, `stop()` (~173–189) execs `ai-recover` unless `AI_AUTO_RECOVER=0`, so an
  interrupted step can be resumed automatically. `ai-recover` traps INT/TERM/HUP (~132–135); its
  `on_exit` reports "auto-recovery failed unexpectedly". `ai-watchdog` (`scripts/lib/watchdog.py`
  `pipeline_died` ~104, recovery ~543) starts `ai-recover` for a marker whose process is gone, and
  stays quiet only for a stop that dropped the marker and wrote `last-error.notified`.
- **G2 open.** Sessions and gates run in the foreground as `timeout --signal=TERM
  --kill-after=10s …` at `scripts/ai-run` ~353, `scripts/ai-recover` ~358, `scripts/ai-review`
  ~137 and ~187, `scripts/ai-check` ~47 (piped to `tee`) and `ai_deps` (`common.sh` ~249). GNU
  `timeout` moves itself into its own process group, and bash runs a trap only after the
  foreground command ends, so `ai-run`'s `trap 'exit 130' INT` (~244) waits for the whole session.
- **G3 open.** `run-manifest start` (`scripts/lib/workflow.py` `run_manifest` ~1674–1698) writes
  one `run.json` per checkout (`binding_dir()` ~1454: `<state root>/reviews/<first 16 hex of
  sha256(checkout path)>/`), overwritten at every human start, with gate, branch, args, attempts
  and settings only: no start time, process, launcher, log path or outcome. `ai-run` alone writes
  none.
- **G4, G5, G6, G7 open.** `scripts/ai-task` has `set`, `show`, `check`, `reorder`; `set` rewrites
  the `Status:` line (`workflow.py` `task_command` ~797–831) without a lock or commit. Statuses
  are `TODO|IN_PROGRESS|BLOCKED|DONE` (`tasks()` ~451, `set` ~807). A task's `Model:` line wins
  over `--model`. Runner and triage sessions call `.ai/bin/ai-task set` themselves
  (`templates/.ai/prompts/runner.md` ~68, `triage.md` ~74), so plain `set` must keep working
  inside a run.
- **G9 open.** Stops are described only by English text in `.ai/local/last-error` (agent-writable)
  and the notification log; `ai-recover` classifies them with `case "$reason"` text patterns
  (~279–291; OR-04).
- **G11 open for the pipeline.** `ai-plan --detach` (`scripts/ai-plan` ~56–100) already starts a
  planning session with `setsid` + `workflow.py exec-logged` (log created exclusively in the
  pinned `.ai/local`) and waits for its observation; `ai-pipeline` has nothing similar. The
  watchdog starts recoveries with `systemd-run --user --collect --quiet --service-type=exec`
  and forwards `PATH`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `AI_*` (`watchdog.py` ~266–360).
- New scripts would have to be added to the install list (`workflow.py` ~307); new entry points
  therefore go into existing scripts (`ai-pipeline --stop`, `--detach`; new `ai-task`
  subcommands) and helpers into `workflow.py`.

## Scope
In: G1, G2, G3, G4, G5, G6, G7, G9, G11 as listed in the Objective, their regression tests,
README, `docs/workflow.md`, `templates/.ai/prompts/runner.md`/`triage.md` (one sentence each:
sessions never set SKIPPED), the vault flow chart and hub Log, the handoff note for mission
control.

Out (later work, recorded in the vault backlog by the human):
- **G8** a command that records the human's answer to needs-human plan dispositions (free text
  into `.ai/reviews/plan-dispositions.md`; needs its own design for the plan review binding).
- **G10** the gate digest as a plain command: not trivial, because the digest is deliberately an
  inline verifier that never asks checkout code to verify itself (mission control's C6 runs the
  bash function the same way the watchdog does). Left as is.
- OR-04 in full (categories for every stop, recovery decided from them). This batch records a
  kind for the stops that wait for a human; `ai-recover`'s text rules stay unchanged.
- `ai-status` and dashboard display of the new records (batch 10 owns `ai-status`; the dashboard
  can follow later).

## Functional requirements
- FR-1 (run record, G3): every human start of `ai-pipeline` and every `ai-run` started outside a
  pipeline creates `<binding dir>/runs/<id>.json` (schema 1, see the plan) and points
  `<binding dir>/runs/current` at it. A recovery resume updates the current record (new process
  identity, `resumes` + 1) instead of creating one. The end writes `ended` and `outcome`. At most
  20 records are kept per checkout (oldest ended ones removed first; the current one never).
- FR-2 (G2): an INT or TERM to a runner script reaches its running session, review or gate within
  a second: the script sends TERM to the `timeout` child (which forwards it and kills after 10 s)
  and waits for it, then runs its existing exit path. Exit codes 124/137 keep their meaning. The
  checkout is left as the session left it; the task attempt is logged `interrupted` as today.
- FR-3 (G1 trap): `ai-pipeline` traps INT and TERM before it writes the marker. On either, it
  ends its foreground child as FR-2, then records a human stop exactly once: a run-log row
  `stopped by the human (<signal>)`, a bookkeeping commit `chore(ai): record stop by the human`
  when only `.ai/state.md`, `.ai/run-log.md`, `.ai/handoff.md` are dirty (never while armed),
  the observation `stop`, the notification `⛔ STOPPED by you: <branch> during <stage>. Partial
  work is kept uncommitted.` (wording fixed in the plan), `last-error` + `last-error.notified`,
  the run record outcome `human_stop`, the escalation record kind `human_stop`, and the marker
  removed. It never execs `ai-recover`. `stop()` takes the same path when the current run record
  carries a stop request.
- FR-4 (G1 recovery): `ai-recover` treats INT/TERM like FR-3 (outcome `human_stop`, never "failed
  unexpectedly"), and at its start, before reserving an attempt, escalates without a Claude
  session when the current run record carries a stop request or ended `human_stop`. The watchdog
  never starts a recovery for such a run and reports it once as stopped by the human.
- FR-5 (`ai-pipeline --stop [CHECKOUT] [--wait SECONDS]`, G1): finds the run only through the
  current run record (never by command-line matching), verifies the recorded process identity
  (pid and start ticks from `/proc/<pid>/stat`), writes the stop request into the record, signals
  SIGINT to the recorded process group when the recorded pid leads it, otherwise to the pid
  alone, waits up to `--wait` (default 60) seconds, and completes the host records itself if the
  process ended without them. Exit 0 = stopped and recorded (also: a scheduled usage-limit
  relaunch cancelled); 3 = no run active (nothing changed; a repeated stop of a stopped run says
  so); 4 = signalled, still ending after the wait (rerun to wait again); 1 = refused or error.
- FR-6 (escalation record, G9): whenever a pipeline, recovery or stand-alone `ai-run` stops for a
  human, `<binding dir>/escalation.json` (schema 1) holds kind, stage, run id, branch, time, task
  ids, evidence (redacted last-error excerpt, review file, finding ids, run log path) and the
  allowed answers as argument arrays of toolkit commands. Kinds: `plan_review_limit`,
  `fix_round_limit`, `task_blocked`, `needs_human_question`, `validation`, `usage_limit`,
  `crash`, `human_stop`, `other`. A human start and an automatic resume remove it. Readers treat
  an unknown kind as `other` and an unknown schema as absent.
- FR-7 (G7): `ai-task set ID STATUS --commit`, and every new subcommand, takes the checkout lock
  without waiting (held: exit 75, "A run is active in this checkout; nothing changed."), refuses
  protected or detached branches, and with `--commit` refuses unless the checkout is clean before,
  then commits only `.ai/tasks.md` with a standard message (`chore(ai): … (ai-task)`), hooks
  enabled. Plain `ai-task set ID STATUS` (sessions) is unchanged.
- FR-8 (G4, G5): `ai-task retry ID --note TEXT [--commit]` (BLOCKED → TODO, or a note on a TODO
  task) appends `Human note (DATE, ai-task retry): TEXT` to the task's `### Result / notes`;
  `ai-task model ID MODEL [--commit]` sets or inserts the task's `Model:` line (TODO or BLOCKED
  tasks only).
- FR-9 (G6): status `SKIPPED`, set only by `ai-task skip ID --reason TEXT [--commit]` on a TODO
  or BLOCKED task no unfinished task depends on. It writes `Skipped (DATE, ai-task skip): TEXT`
  in the task and a host skip record. The queue treats a SKIPPED task with a matching host record
  as finished (not eligible, satisfies dependencies, counts toward "complete"); a SKIPPED task
  without one makes the queue invalid. `tasks set` refuses SKIPPED. The PR body lists skipped
  tasks with their reasons.
- FR-10 (G11): `ai-pipeline --detach <pipeline arguments>` validates `--approved`,
  starts the pipeline under `systemd-run --user` (fallback `setsid` when `systemd-run` is missing)
  with its output in `.ai/local/pipeline-<UTC stamp>-<hex>.log` (created by `exec-logged`),
  records launcher and log path in the run record, waits up to `AI_PLAN_ACK_SECONDS` (default 20)
  for the new run record and prints the pid, the log, `tail -f <log>` and
  `.ai/bin/ai-pipeline --stop <checkout>`.

## Non-functional requirements
- Host records live in the host state directory (never the checkout), are written atomically
  (temp + `os.replace`), and read-modify-writes of the run record take a host lock
  (`<binding dir>/runs/.lock`, `flock`, bounded wait).
- No test signals a process outside its own fixtures (they start fixture runners with
  `start_new_session=True` and signal only that group) and no test touches a real checkout,
  calls the real `systemd-run`/`setsid` launcher on a real pipeline, or starts a real agent.
- Time bounds in tests are generous and scaled by `tests/timeouts.py`.
- No new dependencies. Bash and Python 3 standard library only.

## Acceptance criteria
- AC-1: `.ai/bin/ai-check` passes (or, per the queue header gate rule, the host gate after each
  task).
- AC-2: each FR has offline regression tests named in its task.
- AC-3: README and `docs/workflow.md` describe stop, escalation record, run record, task commands
  and detach; the vault flow chart shows the human stop, the escalation record and detach; the
  handoff lists the new commands and record paths for mission control.
- AC-4 (human): a real run stopped with Ctrl-C and with `ai-pipeline --stop` ends within about
  15 s, is reported "stopped by you", is not resumed by the watchdog timer, and resumes when the
  human reruns `ai-pipeline --approved …`. `--detach` keeps running after the terminal closes.

## Assumptions (unattended planning; recorded instead of asked)
- B1: `ai-pipeline --stop` and `--detach` instead of a new `ai-stop` script: one entry point
  mission control already calls, no change to the install list (`workflow.py` ~307) or to the
  installed copy layout. Both must be the first argument; the rest is parsed as today.
- B2: The stop signals SIGINT (what a terminal Ctrl-C delivers). The process group is signalled
  only when the recorded pid leads it (terminal job, `systemd-run`, `setsid`: the normal cases);
  otherwise only the pid, and the pipeline's own trap ends its child (FR-2). Sessions in
  `timeout`'s own group are reached through FR-2, not by the stopper. No SIGKILL: a run that does
  not end in time is reported (exit 4) and the human decides; even if it is killed later, the
  stop request keeps recovery and the watchdog from resuming it.
- B3: A human stop never commits partial task work; it is preserved uncommitted, as after a
  timeout. Only pure bookkeeping (state, run log, handoff) is committed, as `ai-recover`'s
  `record_stop_leftovers` does. A resume then needs a clean checkout, so the escalation's
  answers name what to do with the partial work.
- B4: INT and TERM from anywhere (terminal, `systemctl --user stop`, `kill`) count as a human
  stop. HUP keeps today's behaviour.
- B5: Run record identity is `pid`, `pgid`, `sid` and `start_ticks` (field 22 of
  `/proc/<pid>/stat`); pid plus start ticks identifies the process, so a reused pid never
  matches.
- B6: Launcher: `AI_LAUNCHER` when set (validated `^[a-z0-9._-]{1,32}$`, e.g. `mission-control`),
  else `detach-systemd`/`detach-setsid` (set by `--detach`), `ai-recover` for a recovery resume,
  `systemd` when `INVOCATION_ID` is set, `terminal` when stdin is a TTY, else `other`. Log path:
  `AI_RUN_LOG` when set by `--detach`, else the target of `/proc/self/fd/1` when it is a regular
  file, else null.
- B7: The run record is written right after `run-manifest start` (base resolved). A `--stop` in
  the first seconds before it exists answers "no run active" (exit 3); mission control already
  waits 15 s after a start.
- B8: The escalation kind comes from host-side hints written by the producer right before it
  stops (`escalation hint KIND …`), else from the stage (`validation` → `validation`), else
  `other`; never from `last-error` text. `ai-recover`'s text rules are unchanged (OR-04 later).
- B9: `fix_round_limit` is written when the fix-round limit ends the review loop with significant
  findings; the run still publishes a draft PR as today, and the record says the human decides.
- B10: Redaction of the last-error excerpt: one line, at most 400 characters, and values after
  `token`, `password`, `secret`, `key`, `authorization`, `bearer` (case-insensitive, `=`, `:` or
  space) and strings that look like provider keys (`sk-…`, `ghp_…`, `gho_…`, `github_pat_…`,
  `xox…-`) replaced by `[redacted]`.
- B11: Allowed answers are argument arrays relative to the checkout (`.ai/bin/…`), with
  placeholders `{note}`, `{reason}`, `{model}` the caller fills; never a shell string.
- B12: `ai-task` "refuse while a run is active" is the checkout lock: the pipeline, `ai-run` and
  `ai-recover` hold it for their whole run. Plain `ai-task set` stays lock-free because sessions
  inside a run use it.
- B13: SKIPPED needs a host record so an agent session cannot skip a task by editing the status
  line; host record `<binding dir>/skips-<16 hex of sha256(branch)>.json` mapping task id to the
  sha256 of the recorded reason line. Planning prompts keep SKIPPED blocks like DONE ones.
- B14: Detach prefers `systemd-run --user` (a `setsid` child stays in the caller's cgroup and dies
  when a service manager stops the caller, mission control's C5); `setsid` + `exec-logged` (the
  `ai-plan --detach` pattern) when `systemd-run` is not executable. The log stays in the ignored
  `.ai/local/` (created exclusively, no symlink followed).
- B15: T118 (batch 9) stays as batch 9 left it (TODO, fix committed in 38f671c). If
  `fix/flow-batch-9` finishes it first, the human merges that branch here before approving;
  otherwise this run verifies T118 first.
- B16: 14 tasks instead of about 12: each is sized for one 30-minute session including the
  ~13-minute self-check; merging any two would exceed it.
