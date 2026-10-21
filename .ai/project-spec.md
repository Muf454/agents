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
   or a service stop is recorded the same way. The shutdown path never runs a checkout helper
   before the inline gate verifier has passed (plan review P1).
2. **G2** an interrupt reaches the running agent session or gate under `timeout` at once, through
   every layer (pipeline → runner, review or gate script → `timeout`), also when only the top
   process is signalled and during sleeps; partial work is preserved exactly as for a timeout.
3. **G9 escalation record**: one schema-versioned JSON record in host state whenever the run
   stops for a human: kind from a fixed list, stage, task ids, evidence pointers, allowed answers
   as toolkit commands. Cleared when the run resumes.
4. **G3 run record**: one record per run (kept, bounded), with start time, process identity,
   launcher, exact argument array, log path, base, branch, end time and outcome; `ai-run` alone
   writes one too.
5. **G7, G4, G5, G6 task commands**: `ai-task` changes for humans and apps take the checkout lock,
   refuse while a run is active and can commit only `.ai/tasks.md` (`--commit`); new `retry`,
   `model` and `skip` subcommands; a SKIPPED status.
6. **G11** `ai-pipeline --detach`: start the run in its own `systemd-run --user` service, record
   the log path, print how to follow and stop it (no `setsid` fallback in this batch, see Out).
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
- **`--detach` without `systemd-run`** (the `setsid` + `exec-logged` fallback): cut after plan
  review P3. A background job of a non-interactive shell starts with SIGINT ignored, `exec-logged`
  keeps that through `execv`, and bash cannot trap a signal ignored on entry; doing it right
  needs a controlled launcher that resets dispositions plus its own stop test. Without
  `systemd-run`, `--detach` refuses (exit 1) and names the foreground command. Later work.
- **`--stop` under a changed gate**: `ai-pipeline --stop` is checkout code like every `.ai/bin`
  command the human runs; it does not verify the gate before its helper runs. The guard of this
  batch protects the running pipeline's own shutdown path (P1). A stop command that verifies the
  gate inline first belongs with G10. Later work.

## Functional requirements
- FR-1 (run record, G3): every human start of `ai-pipeline` and every `ai-run` started outside a
  pipeline creates `<binding dir>/runs/<id>.json` (schema 1, see the plan), points
  `<binding dir>/runs/current` at it and prints the run id, which the starter keeps (`AI_RUN_ID`)
  for every later lifecycle write. Publication is required: a run whose record cannot be written
  stops before any controlled work (agent session, review, gate). A recovery owns the current
  record as soon as it holds the checkout lock and has checked for a stop request (`own`: its
  process identity, launcher `ai-recover`, `resumes` unchanged), before any long recovery work;
  the resumed pipeline then calls `resume` (`resumes` + 1). The end writes `ended` and
  `outcome`. Every lifecycle write names the run id and is checked under the host lock against
  the record's id, the `current` pointer and the caller's process identity; a mismatch changes
  nothing (plan review P5). At most 20 records are kept per checkout (the current one never
  removed).
- FR-2 (G2): an INT or TERM to a runner script reaches its running session, review or gate within
  a second: the script sends TERM to its long child (a `timeout` or a toolkit script) and waits
  for it, then runs its existing exit path. Every long blocking call on the pipeline, runner and
  recovery paths is such a child, including host gates, dependency setup, pause or retry sleeps
  and the publication commands (`git push`, `git ls-remote`, `gh`; their output captured through
  a file, never a `$(…)`), so a signal to the top process alone works at every stage (plan review
  P2, rounds 1 and 2; limits in B21). Below the
  top process every layer is stopped by TERM (a background child of a non-interactive shell
  ignores SIGINT). Exit codes 124/137 keep their meaning. The checkout is left as the session
  left it; the task attempt is logged `interrupted` as today.
- FR-3 (G1 trap): `ai-pipeline` traps INT and TERM before it writes the marker. On either, it
  ends its child as FR-2, then verifies the approved gate with the inline verifier
  (`ai_gate_check`) before any checkout helper runs (plan review P1). Gate unchanged: it records a
  human stop exactly once: a run-log row `stopped by the human (<signal or ai-pipeline --stop>)`,
  the run record outcome `human_stop`, the escalation record kind `human_stop`, the observation
  `stop`, a bookkeeping commit `chore(ai): record stop by the human` when only `.ai/state.md`,
  `.ai/run-log.md`, `.ai/handoff.md` are dirty (never while armed; the gate re-checked after it),
  the notification `⛔ STOPPED by you: <branch> during <stage>. …` (wording fixed in the plan),
  `last-error` + `last-error.notified`, and the marker removed. Gate changed, unreadable or not
  yet approved (a signal before the baseline): no checkout helper and no commit at all; only the
  notification (`AI_NOTIFY_CMD`, which is the human's command, not checkout code), `last-error`
  and `last-error.notified` by plain shell writes, the marker removed. It never execs
  `ai-recover`. `stop()` checks the gate first as today and only then asks the run record for a
  stop request; with one it takes the human stop path.
- FR-4 (G1 recovery): `ai-recover` treats INT/TERM like FR-3 (outcome `human_stop`, never "failed
  unexpectedly"), and right after the lock, before reserving an attempt, escalates without a
  Claude session when its run carries a stop request or has ended (its `own` call refuses). The
  watchdog never starts a recovery for such a run and reports it once as stopped by the human.
- FR-5 (`ai-pipeline --stop [CHECKOUT] [--wait SECONDS]`, G1): finds the run only through the
  current run record (never by command-line matching) and keeps that run id for every later step,
  verifies the recorded process identity (pid and start ticks from `/proc/<pid>/stat`), writes
  the stop request into that record, signals SIGTERM to the recorded process group when the
  recorded pid leads it, otherwise to the pid alone, waits up to `--wait` (default 60) seconds,
  and completes the host records itself if the process ended without them: only for its own run
  id, only while that id is still `current` and only while it holds the checkout lock without
  waiting (another runner owning the checkout means the run was replaced: nothing is written).
  Outcomes (plan review P9): a live run → stopped, exit 0; a record still `running` or `paused`
  whose process is gone (killed, or a scheduled usage-limit relaunch) → the stop request and
  `human_stop` are recorded so nothing resumes it, exit 0 with a message that says so; no record
  or an ended record → exit 3, nothing changed (a repeated stop says "already stopped by you");
  signalled and still ending after the wait → exit 4 (rerun to wait again); refused or error → 1.
  The run may be a pipeline, a recovery or a stand-alone `ai-run`: the owning runner that ends a
  stop-requested run as `stopped` gets `human_stop` (decided by `run-record end` under the host
  lock; plan review round 3, P16), so the signalled run ends `human_stop` itself; a run that
  ended with another outcome before the signal took effect (e.g. `finished`) is reported, exit 0,
  and never rewritten.
- FR-6 (escalation record, G9): whenever a pipeline, recovery or stand-alone `ai-run` stops for a
  human, `<binding dir>/escalation.json` (schema 1) holds kind, stage, run id, branch, time, task
  ids, evidence (redacted last-error excerpt, review file, finding ids, run log path) and the
  allowed answers as argument arrays of toolkit commands. Kinds: `plan_review_limit`,
  `fix_round_limit`, `task_blocked`, `needs_human_question`, `validation`, `usage_limit`,
  `crash`, `human_stop`, `other`. It is written only for the run that is `current` (checked under
  the host lock). Every new run record (`run-record start`, a pipeline or a stand-alone `ai-run`)
  and every automatic resume (`run-record resume`) removes it (plan review P7). The record a
  stopped process leaves is the specific kind of its stop: one write per shutdown chain, and a
  later unclassified write of the same run never replaces a specific kind (B22, plan review P13).
  The answers belong to that run: built from its run record (kind and argv), never from the
  checkout's `run.json` of an earlier pipeline (B24, plan review round 3, P18). The fix-round
  limit record is written once in `finish()`, whichever finish path the run takes (P19).
  Readers treat an unknown kind as `other` and an unknown schema as absent.
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
  in the task and a host skip authorization. The authorization is host-wide per repository, not
  per checkout or branch (plan review P6): `<state root>/skips/<64 hex>`, the hex being sha256 of
  the repository's root commit(s), the task's heading line and its `Skipped (…)` line. So a
  committed skip stays valid on a new branch, after a merge and in another worktree of the same
  repository on this host. On another host (or after the state directory was lost) the human
  re-authorizes an already committed skip with `ai-task skip ID --reauthorize`, which works while
  that skip makes the queue invalid. The queue treats a SKIPPED task with a matching
  authorization as finished (not eligible, satisfies dependencies, counts toward "complete"); a
  SKIPPED task without one makes the queue invalid. `tasks set` refuses SKIPPED. The PR body
  lists skipped tasks with their reasons.
- FR-10 (G11): `ai-pipeline --detach <pipeline arguments>` validates `--approved`, requires an
  executable `systemd-run` (else exit 1, nothing started, the foreground command named), starts
  the pipeline under `systemd-run --user` with its output in
  `.ai/local/pipeline-<UTC stamp>-<hex>.log` (created by `exec-logged`, whose name check accepts
  this prefix beside `plan-…`; plan review P12), records launcher and log
  path in the run record, waits up to `AI_PLAN_ACK_SECONDS` (default 20) for the new run record
  and prints the pid, the log, `tail -f <log>` and `.ai/bin/ai-pipeline --stop <checkout>`.
  A `--knowledge-dir` value is resolved against the caller's working directory before the
  dispatch changes to the checkout root, as in the foreground (plan review round 3, P17).

## Non-functional requirements
- Host records live in the host state directory (never the checkout), are written atomically
  (temp + `os.replace`), and read-modify-writes of the run record and the escalation record take
  a host lock (`<binding dir>/runs/.lock`, `flock`, bounded wait). Atomic writes prevent torn
  records; the run id and identity checks under that lock prevent writes to the wrong run.
- No test signals a process outside its own fixtures (they start fixture runners with
  `start_new_session=True` and signal only that group or a pid inside it) and no test touches a
  real checkout, calls the real `systemd-run` launcher, or starts a real agent.
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
  human reruns `ai-pipeline --approved …`. `--detach` keeps running after the terminal closes
  and its printed `--stop` command ends it. A recovery the watchdog started after a kill is
  stopped by `--stop` and not resumed. A task skipped on this branch is still accepted by the
  queue on the next feature branch.

## Assumptions (unattended planning; recorded instead of asked)
- B1: `ai-pipeline --stop` and `--detach` instead of a new `ai-stop` script: one entry point
  mission control already calls, no change to the install list (`workflow.py` ~307) or to the
  installed copy layout. Both must be the first argument; the rest is parsed as today.
- B2 (revised after plan review P3): The stop signals SIGTERM, not SIGINT: a run started as a
  background job of a non-interactive shell (e.g. `ai-plan --detach`) has SIGINT ignored and
  cannot trap it, while TERM is never ignored that way and is what a service stop sends. A
  terminal Ctrl-C (INT) is still a human stop (B4). The process group is signalled only when the
  recorded pid leads it (terminal job, `systemd-run`: the normal cases); otherwise only the pid,
  and the pipeline's own trap ends its child (FR-2). Sessions in `timeout`'s own group are
  reached through FR-2, not by the stopper. No SIGKILL: a run that does not end in time is
  reported (exit 4) and the human decides; even if it is killed later, the stop request keeps
  recovery and the watchdog from resuming it.
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
  else `detach-systemd` (set by `--detach`), `ai-recover` for a recovery that owns the run,
  `systemd` when `INVOCATION_ID` is set, `terminal` when stdin is a TTY, else `other`. Log path:
  `AI_RUN_LOG` when set by `--detach`, else the target of `/proc/self/fd/1` when it is a regular
  file, else null.
- B7: The pipeline's run record is written right after `run-manifest start` (base resolved), a
  stand-alone `ai-run`'s right after its exit traps are installed (so a refusal after publication
  still ends the record; plan review P7), using `AI_START_BRANCH`. A `--stop` in the first
  seconds before it exists answers "no run active" (exit 3); mission control already waits 15 s
  after a start.
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
- B13 (revised after plan review P6): SKIPPED needs a host authorization so an agent session
  cannot skip a task by editing the status line. It is one empty file per authorization,
  `<state root>/skips/<sha256 of root commit(s), heading line and Skipped line>`, created
  exclusively (no read-modify-write, no lock): valid for every checkout and branch of the
  repository on this host, bound to the task's heading and exact reason line, so a forged line
  or a reused task id with another title does not match. Sessions cannot create it: the state
  root is outside their write scope and `ai-task skip` refuses while a run holds the checkout
  lock. Planning prompts keep SKIPPED blocks like DONE ones.
- B14 (revised after plan review P3): Detach uses `systemd-run --user` only (a `setsid` child
  stays in the caller's cgroup and dies when a service manager stops the caller, mission
  control's C5; the `setsid` fallback is cut, see Out). The log stays in the ignored
  `.ai/local/` (created exclusively by `exec-logged`, no symlink followed).
- B15: T118 (batch 9) stays as batch 9 left it (TODO, fix committed in 38f671c). If
  `fix/flow-batch-9` finishes it first, the human merges that branch here before approving;
  otherwise this run verifies T118 first.
- B16 (revised after plan review rounds 1, 2 and 3): 27 tasks (T301–T327; the queue order, not
  the number order, is the run order). The review's process-chain, ownership and skip findings
  and the split of the old T301, T302, T306, T308, T309 and T313 added work; round 2 added T323
  (publication commands, split from T318) and T324 (the log name check, split from T313); round
  3 added T325 (stand-alone `ai-run` stop), T326 (detach path resolution, split from T313) and
  T327 (plan kinds, split from T321); each task is still sized for one 30-minute session
  including the ~13-minute self-check.
- B17 (plan review P5, revised after round 2 P15): Run ids are `<UTC %Y%m%dT%H%M%SZ>-<pid>-<seq>`,
  `seq` one more than the highest of the checkout's kept records, chosen under the host lock, the
  record created exclusively, so two starts by one pid in one second never collide; retention
  orders by `seq`. The starter keeps the printed id
  in `AI_RUN_ID` (exported so `ai-recover`, which the pipeline execs, and the resumed pipeline
  get it; a watchdog-started recovery reads `current` while it holds the checkout lock). The id is
  not authority: every lifecycle write is also checked against the record's process identity
  under the host lock.
- B18 (plan review P4): `own` (recovery) refuses a record that has a stop request or has ended
  (`outcome` other than `running` or `paused`), replaces `process` and sets `launcher`
  `ai-recover`; `resumes` counts automatic resumes, incremented only by `resume` in the resumed
  pipeline. A pipeline that execs `ai-recover` keeps its pid, so `own` there changes only the
  launcher.
- B19 (plan review P2): The pipeline's own long children (runner, review and gate scripts, push
  retry sleeps) become background children in T318, after T306's trap exists: before that trap,
  a PID-only signal would end the pipeline at once and leave its child running. T308 (the
  PID-only signal source) therefore depends on T318.
- B20 (plan review P1): The gate check comes first in every shutdown path of the pipeline
  (`stop()`, `ai_human_stop`, the new record writes in `ai_die`); `ai-recover` keeps its present
  order because the watchdog verifies the gate before it starts a recovery and the pipeline
  verifies it before its `exec`.
- B21 (plan review round 2, P2): the publication commands `git push`, `git ls-remote` and `gh`
  become background children (T323, after T306 as B19 says); output that the script reads is
  captured through a file under `.ai/local`. `ai_stop_child` ends the `git` or `gh` process; a
  push hook it started may outlive it, and `git commit` (with its hooks) and the short local
  helper calls stay in the foreground, so a blocking commit hook still delays the trap. Both are
  recorded limitations, not later tasks.
- B22 (plan review round 2, P13): one escalation writer per shutdown chain. The non-recovery
  `stop()` writes with its stage and sets `AI_ESCALATION_WRITTEN`; the `ai_die` it always ends in
  then writes nothing; a direct `ai_die` writes once. The helper keeps a same-run record with a
  specific kind against a later write that is still `other` after its refinement.
- B23 (plan review round 3, P16): a stand-alone `ai-run` interrupted by INT/TERM without a
  recorded stop request keeps ending `stopped` with today's "needs you" notification (it is not
  auto-recovered, so nothing changes for it); only a stop request (`ai-pipeline --stop`) makes
  it `human_stop`. Extending B4 to stand-alone runners is not needed for mission control.
- B24 (plan review round 3, P18): the `resume` answer of a stand-alone `ai-run` is offered only
  for a task run (`--approved` and none of `--plan`, `--triage`, `--revise-plan`): rerunning a
  planning, triage or revision session from an escalation is not a safe default. Its argv is
  recorded with the resolved `--knowledge-dir` (the only path option of a task run).

## Plan review round 1 (hand-run Codex review)
Source: `.ai/reviews/plan.md` (HEAD 6bd6e3e, BLOCKER 1, MAJOR 7, MINOR 3), run by hand because the
frozen pipeline would have skipped it (FL-35). Revised 2026-10-21 by an interactive planning
session; every finding was checked against the cited code at 6bd6e3e (same code as 4fea72d).

| Finding | Disposition | Reason or task |
| --- | --- | --- |
| P1 (BLOCKER) gate check after helpers on stop | Accepted | Confirmed: `stop()` checks the gate at `scripts/ai-pipeline:178`, and the old T306 put `run-record stop-requested` and `request-stop` before it. FR-3, B20: gate first in `stop()`, `ai_human_stop` and `ai_die`; no helper or commit when the gate is changed, unreadable or not yet approved. T306 adds tamper tests for a child failure and an interrupt; T302 gate-checks the `ai_die` record write. |
| P2 (MAJOR) signal chain not covered | Accepted | Confirmed: the pipeline runs `ai-run`, `ai-review` and `ai-check` in the foreground (`ai-pipeline:265`, `:288`, `:509`, `:552`, `:566`), `ai-run:304` and `ai-recover:303` run `ai-check` in the foreground, and `ai_limit_pause` and the push retry sleep in the foreground. New T317 (runner and recovery gates, limit sleeps) before T306; new T318 (pipeline children and sleeps, PID-only INT/TERM tests in implementation, review, validation, dependency setup and the retry wait) after T306, because a background child without the trap would be orphaned (B19). T308 depends on T318. |
| P3 (MAJOR) setsid fallback ignores SIGINT | Adjusted | Confirmed: `ai-plan:62` launches with `setsid … &` and `exec_logged` keeps dispositions through `os.execv` (`workflow.py:5112`). Cut the `setsid` fallback from this batch (spec Out; `--detach` refuses without `systemd-run`), and `--stop` sends SIGTERM instead of SIGINT (B2), which no launcher leaves ignored. The end-to-end stop test is kept for the remaining mode (T313, through a fake `systemd-run` that starts a new session). |
| P4 (MAJOR) watchdog recovery keeps the dead identity | Accepted | Confirmed: a watchdog-started `ai-recover` is a new process (`watchdog.py:326`), and the old T302 updated identity only at the pipeline resume. New T316: `own` right after the lock and the stop check, before any long work; `resumes` defined in B18. The stop-during-recovery test is in T319. |
| P5 (MAJOR) stop and end not bound to the run | Accepted | The old `request-stop` and `end` acted on whatever was `current`, and `--stop` holds no checkout lock. New T315: run-id and identity checks under the host lock for every lifecycle write; `start` prints the id and is required (T302, T316 make a failed start fatal); escalation writes only for the current run (T305); `--stop` completes records only for its run id, while it is current and while it holds the checkout lock (T319, with an interleaving test). |
| P6 (MAJOR) committed SKIPPED invalid on the next branch | Accepted | Confirmed: `binding_dir()` (`workflow.py:1454`) is per checkout path and the old record per branch, while the status is committed. B13 revised: host-wide authorization per repository bound to the heading and reason line (T311, with new-branch and second-worktree regressions); new T322 `ai-task skip ID --reauthorize` for another host, usable while the queue is invalid only for that reason. |
| P7 (MAJOR) stand-alone ai-run lifecycle | Accepted | Confirmed: `ai-run` has no `branch` variable (`AI_START_BRANCH` at `ai-run:129`), and `on_exit` is installed at `ai-run:243`, after the lock at `:127`. T316 publishes the record after the traps with `AI_START_BRANCH`, ends it from `on_exit` only when `AI_RUN_ID` is set; `run-record start` clears the escalation (T305), tested for a fresh `ai-run` in T316 and T320. |
| P8 (MAJOR) models of lifecycle tasks | Accepted | T302, T316 and T313 are opus, as are T312 and T322 (they take the checkout lock or authorize a skip). sonnet is left only for T309 and T321 (hint and record wiring on the T305 schema); haiku for T314 docs. |
| P9 (MINOR) dead-process stop contradiction | Accepted | One behaviour (FR-5): a record still `running` or `paused` whose process is gone gets the stop request and `human_stop` so nothing resumes it, exit 0 with its own message; exit 3 only for no record or an ended record. Plan, FR-5, T308 and T319 aligned; the scheduled relaunch cancel is its own message and test. |
| P10 (MINOR) skip test conflicts with refusal | Accepted | The refusal rule stays. T311's test skips a leaf task and then adds a committed dependent of it, which becomes eligible. |
| P11 (MINOR) old T309 too broad | Accepted | Split into T309 (producer hints, sonnet), T320 (writes at stops and clearing, opus) and T321 (fix-round limit and plan kinds end to end, sonnet). |

## Plan review round 2 (hand-run Codex review)
Source: `.ai/reviews/plan.md` (HEAD 86df815, BLOCKER 0, MAJOR 4, MINOR 1), run by hand because the
frozen pipeline would have skipped it (FL-35). Revised 2026-10-21 by an interactive planning
session; every finding was checked against the cited code at 86df815 (scripts unchanged since
4fea72d).

| Finding | Disposition | Reason or task |
| --- | --- | --- |
| P2 (MAJOR) publication commands still block the trap | Accepted | Confirmed: `push()` runs `git push` (`scripts/ai-pipeline:249`) and `git ls-remote` piped to `awk` (`:255`) in the foreground, and every `gh` call of the PR stage (`:679–719`) is foreground or inside `$(…)`. New T323 (opus, after T318): `ai_run_child` or `ai_run_capture` (output through a file) for each, offline PID-only tests with a sleeping fake `git push`, `git ls-remote` and `gh pr view`; T308 depends on T323. A push hook outliving `git push` and foreground `git commit` hooks are recorded limitations (B21). |
| P12 (MAJOR) exec-logged rejects pipeline log names | Adjusted | Confirmed: `EXEC_LOG_NAME` (`scripts/lib/workflow.py:5069`) is `plan-…` only. The change goes into a new small task T324 (sonnet; a name pattern, the exclusive no-symlink creation unchanged) instead of T313, which is already a full session; T313 depends on T324. T324 tests both prefixes and invalid names. |
| P13 (MAJOR) second escalation write loses the kind | Accepted | Confirmed: the non-recovery `stop()` always calls `ai_die` (`scripts/ai-pipeline:186–188`), and the first write consumes the hint. B22: one writer per shutdown chain (`AI_ESCALATION_WRITTEN`, T320) plus a helper backstop (T305: a same-run `other` write keeps a specific kind). T320 tests the final record after exit for a blocked-task stop and a plan-review stop; T305 tests the repeated write. |
| P14 (MAJOR) ai-check rewrite drops the logger status | Accepted | Confirmed: today a failing `tee` fails the gate (`scripts/ai-check:48–51`, `PIPESTATUS`). T304 now starts the logger on its own descriptor, waits for its pid and keeps today's rule (the logger's code when it failed) before `stamp record`; new regression with a passing validator and a failing fake `tee`: nonzero exit, no PASS stamp. |
| P15 (MINOR) run ids collide within one second | Accepted | Confirmed by the format in B17 (stamp and pid only). B17 revised: id `<stamp>-<pid>-<seq>` with `seq` chosen under the host lock and exclusive creation; retention by `seq`. T301 adds a fixed-clock, fixed-pid test, and the 23-start retention test uses the fixed clock. |

## Plan review round 3 (hand-run Codex review, last round)
Source: `.ai/reviews/plan.md` (HEAD 4afd9ab, BLOCKER 0, MAJOR 4, MINOR 0), run by hand because the
frozen pipeline would have skipped it (FL-35). There is no further plan review; the Codex code
reviews after implementation check the result, so every fix is a concrete acceptance criterion
or test. Revised 2026-10-21 by an interactive planning session; every finding was checked
against the cited code at 4afd9ab (scripts unchanged since 4fea72d). Nothing was cut.

| Finding | Disposition | Reason or task |
| --- | --- | --- |
| P16 (MAJOR) `--stop` of a stand-alone `ai-run` cannot end `human_stop` | Accepted | Confirmed: T316's `on_exit` ends every nonzero exit `stopped`, T315 keeps ended records immutable and `settle-stop` refuses them, and T308 then called `settle-stop` on an ended record. Fix in the owning runner's end, under the host lock: T315's `end` stores `human_stop` for `stopped` when `stop_requested` is set (new test); T305 refines `other` to `human_stop` for such a run; T308 reports a run that ended otherwise before the signal (exit 0, nothing rewritten). New T325 (opus): end-to-end `--stop` of a stand-alone `ai-run` with a sleeping fake session (exit 0, session gone, outcome and escalation `human_stop`, second stop exit 3 with bytes unchanged) and its "stopped by you" notification. B23 records that a plain INT/TERM of a stand-alone `ai-run` stays `stopped`. |
| P17 (MAJOR) detach changes relative `--knowledge-dir` | Accepted | Confirmed: the foreground parser resolves it against the caller (`scripts/ai-pipeline:52–58`), `ai_root` changes to the checkout root (`scripts/lib/common.sh:126–128`), and `scripts/ai-plan:23–28` already resolves first. New T326 (opus, after T313; T313 is already a full session): the dispatch resolves the value before `ai_root`, keeps argument order and forwards the absolute path; tests from a subdirectory with same-named directories at both levels, only the caller-relative one, and neither (exit 1, nothing launched), asserting the `systemd-run` argv, the run record argv and the manifest args. FR-10 extended. |
| P18 (MAJOR) stand-alone run offers an earlier pipeline's resume | Accepted | Confirmed: `run_manifest` writes one `run.json` per checkout (`scripts/lib/workflow.py:1678`) only at a pipeline start, and T305 built answers from it. T305 now builds every answer from the run record named by `--run` (kind and argv): pipeline runs resume with their own argv, a stand-alone task run with `.ai/bin/ai-run` and its argv, other `ai-run` modes get no resume answer, pipeline-only answers only for pipelines (B24). T316 records the stand-alone argv with the resolved `--knowledge-dir`. Regressions: T305 `test_escalation_answers_belong_to_the_current_run` (earlier manifest left, different arguments) and the extended T320 stand-alone wiring test; T325 and T327 assert no stale pipeline answer. |
| P19 (MAJOR) fix-round record misses two finish paths | Accepted | Confirmed: besides `--no-pr` (`scripts/ai-pipeline:638`) and the PR stage (`:730`), the run finishes at `:658` (no `origin`) and `:663` (`gh` missing), and all four call `finish()`. T321 now writes the record once inside `finish()` when the loop broke at the limit, with the BLOCKER and MAJOR ids from `finding_ids`; tests cover all four paths (exit 0, outcome `finished`, the finding ids) plus a source check that the write exists only in `finish()`. The plan-kinds tests moved to the new T327 (sonnet) to keep T321 one session. |
