# Plan: Limits and plan stage: MC-01 part 1, DB-04, R15

## Assessment (verified at edc3dc6, 2026-10-17)
See `.ai/project-spec.md` "Verified against the code". In short: limit stops beyond the wait
budget escalate as a hard rule and nothing relaunches them; `ai-run --plan` and the nine-box
dashboard exist, but there is no `ai-plan` command, no read-only reference directories, no
detached start, no outcome/run-log record and a killed planning session looks idle; the PR step
can draft but never un-drafts and does not remember that it drafted.

## Architecture

### MC-01 part 1 — limit-only stop → scheduled relaunch (T001 helpers, T002 watchdog, T003 ai-recover, T004 dashboard)
```mermaid
flowchart TD
  pause["ai_limit_pause: wait > budget"] --> rec["writes .ai/local/limit-stop (agent, reset epoch)<br/>then ai_die (message unchanged)"]
  rec --> stop["ai-pipeline stop → exec ai-recover"]
  stop --> only{"last-error is exactly the limit message<br/>and limit-stop valid? (workflow.py limit-stop)"}
  only -- no --> rules["hard rules / Claude decision as today"]
  only -- yes --> cap{"AI_LIMIT_RELAUNCH_MAX > 0,<br/>timer installed with --recover,<br/>relaunches < cap?"}
  cap -- no --> esc["⛔ escalate (names the reset time)"]
  cap -- yes --> sched["run-manifest limit-schedule AT CAP HEAD<br/>(gives the reserved attempt back)<br/>pauses.log line, observe relaunch AT, ⏸ notify,<br/>drop last-error, limit-stop, pipeline.active; exit 75"]
  sched --> probe["watchdog probe (every 10 min, --recover):<br/>no runner, no marker, run-manifest limit-due"]
  probe --> launch["start_recovery(stage 'usage limit relaunch')"]
  launch --> claim["ai-recover, right after reserve-attempt:<br/>limit-hold (still waiting → restore wait, exit 75)<br/>or limit-claim (schedule consumed: later stops are terminal)"]
  claim --> due["gate/branch checks, record stop leftovers;<br/>dirty at the scheduled HEAD → limit-arm (T011);<br/>▶ RESUMED, exec ai-pipeline"]
  due -. "limit again" .-> only
```
- **Record (T001).** `ai_limit_pause` writes `.ai/local/limit-stop` (`<Agent> <reset epoch or 0>`,
  via a temp file and `mv`) just before its `ai_die`; the die message stays byte-identical (the
  existing hard-rule pattern and docs keep working). `workflow.py limit-stop` prints
  `<Agent> <relaunch epoch>` and exits 0 only when `.ai/local/last-error` holds exactly one line
  matching `^(Claude|Codex) usage limit: the reset is beyond the \d+s wait budget\. Rerun after
  it resets\.$`, `limit-stop` parses, names the same agent, and is not older than last-error by
  more than 120 s (a stale file from an earlier stop never qualifies). Relaunch epoch:
  `reset + 60` when the reset is in the future, `now + AI_LIMIT_RETRY` (default 1800) when it is
  0, `now` when it has passed. "Only reason" = the whole last-error is the limit message.
- **Schedule (T001).** New run-manifest actions, all atomic on `run.json` (fields
  `limit_relaunches`, `limit_relaunch_at`, `limit_head`, `limit_resume` optional, so existing
  manifests stay valid; a human `start` drops them; `clear-attempts`, called by `finish`, resets
  them): `limit-schedule AT CAP HEAD`, `limit-due [NOW]` (read only, watchdog), `limit-hold
  [NOW]`, `limit-claim [NOW]`, `limit-arm HEAD` / `limit-armed HEAD` / `limit-disarm`,
  `limit-count`; exact semantics in T001 and "Relaunch schedule lifecycle" below. New setting
  `AI_LIMIT_RELAUNCH_MAX` (0–9, default 2) in `RUN_SETTINGS`, `ai_config`'s key list and both
  lists in `ai-recover`. `limit-stop` is written by `workflow.py limit-stop-write` through the
  pinned `.ai/local` descriptor and `write_record` (exclusive `O_NOFOLLOW|O_NONBLOCK` temp,
  `os.replace` on the descriptor), never by a shell redirection (P6).
- **Relaunch schedule lifecycle (plan review round 1, P1–P3).** The schedule has three states
  and every `ai-recover` decides on it right after `reserve-attempt` and the settings restore,
  before any escalation can run:
  - *pending* (`AT > now`): `limit-hold` gives the reservation back; ai-recover restores the
    wait (removes last-error, limit-stop, the stale marker; `observe relaunch`; ⏸ again) and
    exits 75. This makes scheduling idempotent across a kill between `limit-schedule` and the
    cleanup: the watchdog's crash recovery for the dead marker, or any early recovery, never
    schedules twice (cap unchanged) and never retries before the reset.
  - *due* (`AT <= now`): `limit-claim` consumes it in the same write that gives the attempt
    back. From here every stop is that relaunch's own terminal ⛔ (or the normal recovery rules
    after the resume); no later probe sees a due schedule, so a branch switch, a changed gate or
    `AI_AUTO_RECOVER=0` produce exactly one ⛔ and no launch loop.
  - *none*: today's behaviour.
  *Preserved task work (T011).* A limit stop inside an implementation session leaves its edits
  (task IN_PROGRESS, source). The claimed relaunch does not commit them and does not escalate:
  when the tree is dirty after recording the bookkeeping leftovers and HEAD still equals
  `limit_head`, it arms the manifest (`limit_resume = HEAD`). The resumed `ai-pipeline` and
  `ai-run` accept exactly that tree at their start-from-clean checks (ai-pipeline ~123,
  `reconcile_disputes` ~326 with no re-check, ai-run ~148), only on a resume, and ai-run
  consumes the arm before its first session. The normal session reconciles the work ("Reconcile
  interrupted work first"); DONE still needs `ai-check`, the checkpoint guard and
  committed-matches-worktree, as for any task. Chosen over a recovery WIP commit (would commit
  unvalidated content) and over the Claude decision session (the reviewer's and the decision's
  point: a limit is not a human problem). HEAD moved since the stop → ⛔.
- **Watchdog (T002).** Under its lock, before the incident logic: with `--recover`, no runner
  alive and no `pipeline.active` marker, it asks THIS host copy's `workflow.py run-manifest
  limit-due` (same trust path as the gate check in `start_recovery`); when due it calls
  `start_recovery(root, local, marker, stage='usage limit relaunch')` (generalised: the default
  crash last-error is written only for the crash stage). Refused → one `⛔ STOPPED, needs you: the
  usage-limit relaunch could not start: <reason>.` per AT (dedupe key `relaunch:<AT>` in
  `watchdog.json` `active`). Not due → nothing. The stall incident is skipped while
  `now < paused_until(local)` (ai-recover's pauses.log line carries the wait until AT). New flag
  `--timer-recovers`: exit 0 when `timer_status(root)` is installed and the service's ExecStart
  contains `"--recover"`, else 1 (one line on stdout).
- **ai-recover (T003).** Right after `reserve-attempt` and the settings: `limit-hold` /
  `limit-claim` (lifecycle above). After the plan-revision decision block and BEFORE the hard
  rules: (1) claimed relaunch → notify
  `▶ RESUMED after the usage limit (relaunch k/cap): <branch>`, then the existing open-stage
  branch (resume) or record-stop-leftovers, then a dirty tree is armed (or ⛔ when HEAD moved)
  + `resume` (no Claude, no `AI_RECOVER_MAX` count). (2) limit-only stop: `limit-stop` exits 0 → when
  `AI_LIMIT_RELAUNCH_MAX` is 0 fall through to the hard rules (today); when
  `"$AI_BIN/ai-watchdog" "$AI_ROOT" --timer-recovers` fails → escalate `the usage limit resets
  around <time>, but no watchdog timer with --recover is installed to relaunch the run.` /
  `install it (ai-watchdog --install-timer --recover) or rerun ai-pipeline after the reset.`;
  `limit-schedule` fails (cap) → escalate `usage limit again after N relaunch(es) in this run.`;
  else schedule: append `pauses.log` line `<UTC> paused <AT-now>s: <Agent> usage limit relaunch
  (resume ~<a H:M>)`, `ai_observe relaunch AT "<Agent> limit · relaunch after <a H:M>"`, notify
  `⏸ PAUSED: <branch> stopped at a <Agent> usage limit during <stage>; relaunches by itself after
  <a H:M> (relaunch k/cap).`, remove last-error, `limit-stop` and `pipeline.active`, mark the stop
  announced (no ⛔ from `on_exit`), print one line and exit 75.
- **Dashboard (T004).** No live runner, no marker, no newer last-error, observation
  `state: paused` WITH `relaunch_at` (written only by `observe relaunch`, dropped by every other
  action) → status `paused` (waiting for a relaunch), marker text keeps the note; ranks with the
  live paused runs. A plain `paused` (an in-process `ai_limit_pause` wait whose runner was
  killed) is no evidence: it falls through to the planning-stop rule or today's idle (P5).

### DB-04 — `ai-plan` (T005 read dirs, T006 command, T007 logging, T004 killed planning)
- **Read dirs (T005).** `ai-run --plan … --read-dir DIR` (repeatable, plan mode only; existing
  directory, resolved with `pwd -P`, refused when it contains `*`, `?`, `[`, `(`, `)`, a newline
  or a comma): each adds `--add-dir DIR` and the allow entry `Read(/DIR/**)` (an absolute DIR
  gives `Read(//abs/**)`, Claude Code's absolute-path form, as in `launch-plan.sh`). No Edit or
  Write outside `plan-allowlist`. The contract names them as read-only reference directories.
- **Command (T006).** `scripts/ai-plan PROMPT_FILE [--revision] [--model NAME]
  [--session-timeout S] [--knowledge-dir DIR] [--read-dir DIR]... [--detach]`: without
  `--detach` it execs `ai-run --plan …` (same process, so the dashboard and watchdog see an
  `ai-run` runner and nothing else changes). With `--detach`: prompt path made absolute, log
  `.ai/local/plan-<UTC stamp>.log`, `setsid "$AI_BIN/ai-run" --plan … </dev/null >log 2>&1 &`
  (a non-interactive shell's background job is not a group leader, so `setsid` execs without
  forking and `$!` is the runner's PID), then wait up to `AI_PLAN_ACK_SECONDS` (default 20) for
  `.ai/local/observation.json` to show `stage: planning` with `pid` equal to that PID (success:
  `Planning session started: pid N, log PATH`, exit 0), or for the child to exit (print the log's
  last lines, exit with its status), else `could not confirm …` exit 1 (the child keeps running).
  Installed by `setup-project` (list at workflow.py:306).
- **Logging (T007).** Outcome kind `plan` (`outcome plan RESULT MODEL SECONDS [TASKS]`, not in
  `outcomes_report`), written on success (`done`, task count) and from `on_exit` for a planning
  stop (`interrupted` 130/143, `timeout` 124/137 session code, else `stopped`), only with the
  gate intact. On success one run-log line (`ai_log planning "plan written: N tasks (<model>,
  <kind>)" PASS 'Plan left uncommitted for review'`); `.ai/run-log.md` is already in plan scope.
- **Killed planning (T004).** No runner, no marker, observation `stage: planning`,
  `state` `active` or `paused` → status `needs_you`, note `planning session ended without a plan (killed?)`,
  so the Plan box shows ✗ like a recorded `stop plan`.

### R15 — un-draft only pipeline-drafted PRs (T008 record, T009 pipeline)
- **Record (T008).** Host state per branch, beside the stage records: `binding_dir() /
  pr-draft-<sha256(branch)[:16]>.json` = `{"branch", "url", "how": "created"|"converted",
  "at"}` written atomically. Helper `pr-draft record URL HOW`, `pr-draft get` (prints the URL,
  exit 1 when none or unreadable/foreign: fails closed = "not ours"), `pr-draft clear`.
- **Pipeline (T009).** Draft reasons: `--draft` (the human's request: never recorded) versus
  the pipeline's policy (`unresolved` or disputes). Recorded when the pipeline creates the PR
  with `--draft` for policy, or converts an existing ready PR with `gh pr ready --undo` for policy
  (after the isDraft check confirms). When `make_draft=no` and the existing PR is a draft: if
  `pr-draft get` equals this PR's URL → `gh pr ready "$branch"`, confirm `isDraft == false`, clear
  the record, log it; a failure warns and keeps the record (the run still finishes; the summary
  says the PR is still a draft). No record or another URL → leave it draft and print
  `PR is a draft set outside the pipeline; left as draft.` An existing ready PR clears a stale
  record (a human un-drafted it). A run with `--draft` clears the record whatever the PR's state:
  the human's explicit draft intent revokes pipeline ownership (P4).

## Phases / tasks
| Task | Item | What | Model |
| --- | --- | --- | --- |
| T001 | MC-01 | limit-stop record, run-manifest relaunch schedule, setting | opus |
| T002 | MC-01 | watchdog starts the due relaunch, `--timer-recovers`, stall skip | opus |
| T003 | MC-01 | ai-recover schedules instead of escalating; hold/claim lifecycle; due path resumes | opus |
| T011 | MC-01 | relaunch continues preserved task work once (armed resume) | opus |
| T004 | MC-01, DB-04 | dashboard: waiting relaunch is paused, killed planning is a stop | sonnet |
| T005 | DB-04 | `ai-run --plan --read-dir` (permission boundary) | opus |
| T006 | DB-04 | `scripts/ai-plan` with `--detach` | opus |
| T007 | DB-04 | planning sessions in the outcome log and run log | sonnet |
| T008 | R15 | host record of a pipeline-drafted PR | sonnet |
| T009 | R15 | PR step un-drafts only a recorded pipeline draft | sonnet |
| T010 | all | docs, flow chart and handoff audit | haiku |

## Risks
- A crash between `limit-schedule` and the exit leaves `pipeline.active` with a dead PID, so the
  watchdog starts crash recovery at once: `limit-hold` restores the wait (no second schedule, no
  early retry; plan review round 1 P2). A relaunch that escalates after `limit-claim` is
  terminal (P1). Residual: a kill between `reserve-attempt` and `limit-claim` in the relaunched
  ai-recover leaves the schedule due with no marker, so the next probe (10 min later) relaunches
  once more; that is a retry of the same relaunch, not a new one (the relaunch count does not
  change) and needs an external kill in a window of two helper calls each time. Accepted.
- Preserved task work (T011) is admitted only on a resume, at the HEAD recorded when the stop
  was scheduled, once; it is the session's own uncommitted output, exactly what the in-process
  `ai_limit_pause` wait would have continued with, and it is validated before any commit.
- Watchdog not installed or installed without `--recover`: detected by `--timer-recovers`; the
  stop escalates as today. A timer removed after scheduling: nobody relaunches; the ⏸
  notification states the time, so the human can rerun. Accepted (no daemon, AD-4).
- Weekly limits: the relaunch may be days away; the run waits without a process (no lock held).
  A human start in between drops the schedule (`run-manifest start` rewrites the manifest).
- `limit-stop` lives in `.ai/local/` (agent-writable). It only selects between "schedule a
  relaunch of the approved run" and "escalate"; the relaunch runs under the same gate, branch and
  manifest checks as any recovery, and the cap bounds it. AD-5 holds: it authorizes nothing new.
- The un-draft rule cannot see a human who un-drafted and re-drafted between two pipeline runs
  (the record still says "ours"). Only a pipeline run that observes the PR ready clears it.
  Accepted limitation, documented.
- `setsid` behaviour: `--detach` relies on the background job not being a process-group leader;
  the test asserts the printed PID is the runner's (`/proc/PID/cmdline` names `ai-run`).

## Validation strategy
Targeted `python3 -m unittest discover -s tests -k <prefix>` per task, then `.ai/bin/ai-check`
(about 7 min; see the gate note in `.ai/tasks.md`). New test prefixes: `test_limit_relaunch_*` (incl. `test_limit_relaunch_preserved_*`),
`test_dashboard_limit_relaunch_*`, `test_dashboard_plan_killed_*`, `test_plan_read_dir_*`,
`test_ai_plan_*`, `test_plan_outcome_*`, `test_pr_undraft_*`.

## Assumptions (unattended run; recorded instead of asked)
- The relaunch covers both agents' limit stops (the message and mechanism are shared); Zack's
  decision names Claude, and a Codex-only limit stop is the same "not a human problem".
- `AI_LIMIT_RELAUNCH_MAX` default 2 per human-started run; 0 restores today's escalation.
- A due relaunch needs auto-recovery on (`AI_AUTO_RECOVER=0` still escalates) and does not count
  against `AI_RECOVER_MAX`.
- A scheduled pause exits 75 (EX_TEMPFAIL) so callers never read it as success.
- "⛔ if the relaunch stops again": a later limit stop schedules again up to the cap, then ⛔; any
  other stop after a relaunch follows the normal recovery rules (which end in ⛔ when they give up).
- DB-04 "same allowlist": `ai-plan` uses `plan-allowlist` unchanged (it also allows
  `.ai/reviews/dispositions.md`, which the hand launcher lacked; it is a plan record).
- The Plan box already exists (nine boxes, goldens at 120/119/60 columns pass); DB-04 only adds
  the killed-session stop. A finished plan keeps today's view (Plan ✓, 📝 under Plan check) until
  the pipeline starts.
- R15: a PR drafted because the human passed `--draft` is never recorded, so never un-drafted.
- An un-draft failure does not stop the run (the PR is published; the record is kept for the next
  run); a draft conversion failure still stops as today.
