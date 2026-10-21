# Handoff

## What has been implemented?
Nothing in batch 11 yet: this is the plan. Batch 11 (RC-01, run controls for humans and apps) was
planned 2026-10-21 by an unattended planning session on `fix/flow-batch-11` (from
`fix/flow-batch-9` at 4fea72d; batch 9 is nearly complete there but not merged; this PR targets
`fix/flow-batch-9` until that merges). Mission control chose the scope on 2026-10-21 with Zack's
delegation. Batch 10 (TS-01, ME-01, FL-39) is built in parallel from the same commit.

- `.ai/project-spec.md`: scope, what was verified in the code at 4fea72d (every gap G1–G7, G9,
  G11 is still open; G8 and G10 are later work), FR-1 to FR-10, assumptions B1–B20, and "Plan
  review round 1 (hand-run Codex review)" with the disposition of P1–P11.
- `.ai/current-plan.md`: three round-1 rules (gate first, bound to the run, every layer
  forwards), record schemas and paths, the human-stop flow, the task map in queue order.
- `.ai/tasks.md`: T301–T322 (earlier batches' DONE tasks unchanged; T118 of batch 9 left as is).
  New tasks T315–T322 sit where their dependencies need them: the queue order is the run order.

Revised 2026-10-21 after the hand-run Codex plan review (`.ai/reviews/plan.md`: BLOCKER 1, MAJOR
7, MINOR 3). All eleven findings were confirmed in the code; ten accepted, P3 adjusted (the
`setsid` fallback of `--detach` is cut and `--stop` sends SIGTERM). Two items moved to later work
(spec Out): `--detach` without `systemd-run`, and a `--stop` that verifies the gate before its
own helper runs.

Planned tasks (queue order):
- **G3 run record**: T301 helper (schema 1, start prints the run id, host lock, 20 kept), T315
  lifecycle bound to run id and process identity (P5), T302 pipeline wiring (start required,
  `ai_die` write after a gate check), T316 recovery owns the run early (P4) and the stand-alone
  `ai-run` record (P7).
- **G9 helper**: T305 (kinds, redaction, answers; current run only; cleared by every new run and
  resume).
- **G2 interrupts reach the child**: T303 sessions, T304 reviews, gate and dependency setup, T317
  runner and recovery host gates and limit sleeps, T318 the pipeline's own children and sleeps
  with PID-only stop tests at every stage (P2).
- **G1 human stop**: T306 pipeline trap with the gate check first and tamper tests (P1), T307
  recovery and watchdog never resume it, T308 `ai-pipeline --stop` (SIGTERM; a run whose process is
  gone is recorded as stopped, P9), T319 completion bound to its run, relaunch cancel, stopping a
  watchdog-started recovery.
- **G9 wiring**: T309 hints, T320 writes at every stop (gate first), T321 fix-round limit and plan
  kinds end to end (P11 split).
- **G7, G4, G5, G6 task commands**: T310 lock and `--commit`, T311 SKIPPED with a host-wide
  authorization that survives new branches and worktrees (P6), T312 `ai-task retry`, `model`,
  `skip`, T322 `ai-task skip ID --reauthorize` for another host.
- **G11**: T313 `ai-pipeline --detach` (systemd-run only) with an end-to-end stop test.
- T314 docs, flow chart audit, mission-control note.

## Validation run
None on this branch yet (the plan revision changed only `.ai/` planning records; no shell was
available in the revision session, so the queue was checked by reading, not with `ai-task
check`). Batch 9's last full gate: PASS, 1104 tests (T116 tree, 816.3 s).

## Assumptions
Recorded as B1–B20 in `.ai/project-spec.md`. The ones that shape behaviour most:
- B1: `ai-pipeline --stop` and `--detach` (first argument) instead of a new `ai-stop` script: one
  entry point mission control already calls, no change to the installed file list.
- B2 (revised): the stop sends SIGTERM (not SIGINT, which a background job may have ignored) to
  the recorded process group only when the recorded pid leads it, else to the pid alone; no
  SIGKILL; a run that does not end in time is reported (exit 4).
- B3: a human stop never commits partial task work; only pure bookkeeping is committed.
- B4: INT and TERM from anywhere count as a human stop; HUP is unchanged.
- B8: escalation kinds come from host-side hints written by the producer, never from
  `last-error` text; `ai-recover`'s text rules stay (OR-04 later).
- B13 (revised): SKIPPED is valid only with a host-wide skip authorization per repository, so a
  session cannot skip a task by editing its status line, and a committed skip stays valid on the
  next branch or worktree on this host.
- B14 (revised): `--detach` uses `systemd-run --user` only; without it, it refuses.
- B15: T118 (batch 9) is left as batch 9 left it.
- B16 (revised): 22 tasks, each sized for one 30-minute session with the ~13-minute self-check.
- B17–B20: run ids and `AI_RUN_ID`, recovery ownership and `resumes`, why T318 follows T306, gate
  first on every pipeline shutdown path.

## Flow chart
Flow unchanged so far (planning only). T303, T306, T307, T308, T311, T313 and T320 change the
flow and update the vault `agents-flow.md` and the hub Log in their own task; T314 audits them.

## For mission control (phase 2 switch; filled in by T314)
Planned commands (exact forms land with their tasks; T314 checks this list against the code):
- `<checkout>/.ai/bin/ai-pipeline --stop <checkout> [--wait SECONDS]`: sends SIGTERM; exit 0
  stopped and recorded (also: a run whose process was already gone is recorded as stopped so
  nothing resumes it, or a scheduled usage-limit relaunch cancelled), 3 no run active (or
  already stopped), 4 signalled and still ending, 1 refused or error. Replaces FR-K's own `/proc`
  walk and signals (C3, C4, C19). Also stops a recovery the watchdog started.
- `<checkout>/.ai/bin/ai-pipeline --detach --approved …`: replaces the app's `systemd-run`
  builder for resume (FR-P4); prints pid and log; needs `systemd-run` (exit 1 without it).
- `<checkout>/.ai/bin/ai-task set ID STATUS --commit`, `retry ID --note TEXT --commit`, `model ID
  MODEL --commit`, `skip ID --reason TEXT --commit`, `skip ID --reauthorize`: exit 75 while a run
  holds the checkout. Replaces FR-Q3's `flock` + `git commit` steps; adds the "retry with a
  note", "raise the model" and "skip" choices FR-E3 left out.
- Records (host state, `<state root>/reviews/<first 16 hex of sha256(checkout path)>/`):
  `runs/current` (id) and `runs/<id>.json` (run record schema 1: process identity, launcher,
  argv, log, base, branch, outcome; the owner's process identity is always the live one, also
  during a recovery), `escalation.json` (schema 1: kind, stage, run id, tasks, evidence, answers
  as argv arrays; treat unknown kinds as `other`). Skip authorizations: `<state
  root>/skips/<64 hex>` (host-wide per repository). Detached logs:
  `<checkout>/.ai/local/pipeline-<UTC stamp>-<hex>.log`.
- FR-E1's wording classifier can be replaced by `escalation.json`'s `kind`; FR-K4's "auto-recovery
  may start the run again" no longer applies after a stop through `--stop` (G1).

## Manual testing for the human

### Needs you
1. Read the revised plan (`.ai/project-spec.md` with B1–B20 and "Plan review round 1",
   `.ai/current-plan.md`) and commit it (this revision is uncommitted). Decide whether the plan
   review must run again on the revision before approving; the hand-run round-1 review covers
   6bd6e3e, not this revision. Then approve the run (`ai-pipeline --approved --base
   fix/flow-batch-9 --pr-base fix/flow-batch-9 …`). No gate file changes are needed to start.
2. Before approving: if `fix/flow-batch-9` has meanwhile finished T118, merge it into this branch
   first, so T118 arrives DONE and this run does not verify it again.
3. After T308 is merged and installed (`setup-project --upgrade --apply`): on a real run in a
   terminal, press Ctrl-C during a Claude session and check that it ends within about 15 s, the
   phone gets one "⛔ STOPPED by you" message, and the watchdog timer does not restart it. Rerun
   `ai-pipeline --approved …` and check that it continues.
4. On another real run, from a second terminal: `.ai/bin/ai-pipeline --stop <checkout>`; check the
   exit status 0, the message and the same records; a second `--stop` says "No run active" (exit 3).
5. `.ai/bin/ai-pipeline --detach --approved …` on the PC: close the terminal and check that the run
   keeps going (`systemctl --user list-units 'ai-pipeline-*'`), that the printed `tail -f` shows
   its output, and that the printed stop command ends it.
6. Kill a real pipeline (`kill -9 <pid>`), let the watchdog timer start its recovery, and while
   it shows "recovering" run `.ai/bin/ai-pipeline --stop <checkout>`: exit 0, one "⛔ STOPPED by
   you", and no later resume.
7. With a real BLOCKED task: `ai-task retry T… --note "…" --commit`, then resume; the next session
   should read the note.
8. Skip a task with `ai-task skip T… --reason "…" --commit`, finish or merge the branch, then
   start the next feature branch from it and check that `ai-task check` (and the pipeline start)
   accept the queue.
9. Mission control: switch phase 2 to the commands and records in "For mission control" above.

### Covered by automated tests
Planned test groups (run with `python3 -m unittest discover -s tests -k <group>`):
- `run_record` (T301, T315, T302, T316): schema, current pointer, retention, identity, bounded
  lock; lifecycle bound to the run id (interleaving of two runs); pipeline start required,
  resume, `ai_die` after a gate change; recovery owns the run before its session; stand-alone
  `ai-run` records, refusal after publication, escalation cleared at start.
- `interrupt` (T303, T304, T317): SIGINT/SIGTERM (group and pid only) end a sleeping fake
  session, recovery session, review, gate, the runner's and recovery's host gate and a limit
  pause within a scaled bound; partial work kept; exit codes unchanged.
- `escalation` (T305, T309, T320, T321): kinds, answers, redaction, hint consumption, current run
  only, cleared by a new run and a resume; hints at the producers; writes for blocked tasks,
  validation through recovery, stand-alone `ai-run`, not after a gate change, no classification
  from text; fix-round limit and plan kinds end to end.
- `human_stop` (T306, T318, T307): trap records, bookkeeping commit, stop request in `stop()`,
  gate tampering with a child failure and with an interrupt; PID-only stop in implementation,
  review, validation, dependency setup and the retry wait; recovery refuses, interrupt during
  recovery, watchdog does not recover.
- `stop_command` (T308, T319): stop, non-leader, no run, process already gone, identity mismatch,
  wait expiry; completion, a replacing run untouched, cancelled relaunch, stopping a recovery.
- `ai_task` (T310, T312, T322): lock, `--commit`, dirty or protected refusal, hook failure, plain
  `set` unchanged; retry, model, skip; reauthorize and its refusals.
- `skip` (T311): SKIPPED semantics, forged status refused, new branch, merge and second worktree,
  refusals, `tasks set`, planning guard.
- `detach` (T313): `systemd-run` arguments, detach then `--stop`, refusals.
- `Docs` (T314).

## Human todos
- Gate files: none need changing for this batch. After merge, `setup-project --upgrade --apply` in
  each project so `.ai/bin` gets the new commands (mission control needs them installed there).
- Add G8 (answers to plan questions) and G10 (gate check command) to the vault backlog as later
  work, if wanted, plus the two items cut in round 1: the `--detach` fallback without
  `systemd-run` (needs a launcher that resets signal dispositions) and a `--stop` that verifies
  the gate before its helper runs; tick RC-01's done gaps yourself after merge (sessions never
  tick them).

## Next action
Zack (or mission control on Zack's behalf) commits the revised plan, decides on a second plan
review, and approves; then the runner starts with T118 if it is still TODO, otherwise T301.
Nothing is merged or deployed.
