# Handoff

## What has been implemented?
Nothing in batch 11 yet: this is the plan. Batch 11 (RC-01, run controls for humans and apps) was
planned 2026-10-21 by an unattended planning session on `fix/flow-batch-11` (from
`fix/flow-batch-9` at 4fea72d; batch 9 is nearly complete there but not merged; this PR targets
`fix/flow-batch-9` until that merges). Mission control chose the scope on 2026-10-21 with Zack's
delegation. Batch 10 (TS-01, ME-01, FL-39) is built in parallel from the same commit.

- `.ai/project-spec.md`: scope, what was verified in the code at 4fea72d (every gap G1–G7, G9,
  G11 is still open; G8 and G10 are later work), FR-1 to FR-10, assumptions B1–B16.
- `.ai/current-plan.md`: record schemas and paths, the human-stop flow, the task map.
- `.ai/tasks.md`: T301–T314 (earlier batches' DONE tasks unchanged; T118 of batch 9 left as is).

Planned tasks:
- **G3 run record**: T301 helper (schema 1, host lock, 20 kept), T302 wiring (pipeline, recovery,
  stand-alone `ai-run`).
- **G2 interrupts reach the child**: T303 sessions in `ai-run` and `ai-recover`, T304 reviews,
  gate and dependency setup.
- **G9 escalation record**: T305 helper (kinds, redaction, answers), T309 hints and writes at
  every stop for a human, cleared on resume.
- **G1 human stop**: T306 pipeline INT/TERM trap, T307 recovery and watchdog never resume it, T308
  `ai-pipeline --stop [CHECKOUT] [--wait SECONDS]`.
- **G7, G4, G5, G6 task commands**: T310 lock and `--commit`, T311 SKIPPED with a host skip
  record, T312 `ai-task retry`, `model`, `skip`.
- **G11**: T313 `ai-pipeline --detach`.
- T314 docs, flow chart audit, mission-control note.

## Validation run
None on this branch yet. Batch 9's last full gate: PASS, 1104 tests (T116 tree, 816.3 s).

## Assumptions
Recorded as B1–B16 in `.ai/project-spec.md`. The ones that shape behaviour most:
- B1: `ai-pipeline --stop` and `--detach` (first argument) instead of a new `ai-stop` script: one
  entry point mission control already calls, no change to the installed file list.
- B2: the stop sends SIGINT to the recorded process group only when the recorded pid leads it,
  else to the pid alone; no SIGKILL; a run that does not end in time is reported (exit 4).
- B3: a human stop never commits partial task work; only pure bookkeeping is committed.
- B4: INT and TERM from anywhere count as a human stop; HUP is unchanged.
- B8: escalation kinds come from host-side hints written by the producer, never from
  `last-error` text; `ai-recover`'s text rules stay (OR-04 later).
- B13: SKIPPED is valid only with a host skip record, so a session cannot skip a task by editing
  its status line.
- B14: `--detach` prefers `systemd-run --user`, falls back to `setsid` (the `ai-plan` pattern).
- B15: T118 (batch 9) is left as batch 9 left it.
- B16: 14 tasks rather than about 12, because each one has to fit a 30-minute session that
  includes the ~13-minute self-check.

## Flow chart
Flow unchanged so far (planning only). T303, T306, T307, T308, T309, T311 and T313 change the
flow and update the vault `agents-flow.md` and the hub Log in their own task; T314 audits them.

## For mission control (phase 2 switch; filled in by T314)
Planned commands (exact forms land with their tasks; T314 checks this list against the code):
- `<checkout>/.ai/bin/ai-pipeline --stop <checkout> [--wait SECONDS]`: exit 0 stopped and
  recorded (or a scheduled usage-limit relaunch cancelled), 3 no run active, 4 signalled and
  still ending, 1 refused or error. Replaces FR-K's own `/proc` walk and signals (C3, C4, C19).
- `<checkout>/.ai/bin/ai-pipeline --detach --approved …`: replaces the app's `systemd-run`
  builder for resume (FR-P4); prints pid and log.
- `<checkout>/.ai/bin/ai-task set ID STATUS --commit`, `retry ID --note TEXT --commit`, `model ID
  MODEL --commit`, `skip ID --reason TEXT --commit`: exit 75 while a run holds the checkout.
  Replaces FR-Q3's `flock` + `git commit` steps; adds the "retry with a note", "raise the model"
  and "skip" choices FR-E3 left out.
- Records (host state, `<state root>/reviews/<first 16 hex of sha256(checkout path)>/`):
  `runs/current` (id) and `runs/<id>.json` (run record schema 1: process identity, launcher,
  argv, log, base, branch, outcome), `escalation.json` (schema 1: kind, stage, tasks, evidence,
  answers as argv arrays; treat unknown kinds as `other`), `skips-<16 hex of sha256(branch)>.json`.
  Detached logs: `<checkout>/.ai/local/pipeline-<UTC stamp>-<hex>.log`.
- FR-E1's wording classifier can be replaced by `escalation.json`'s `kind`; FR-K4's "auto-recovery
  may start the run again" no longer applies after a stop through `--stop` (G1).

## Manual testing for the human

### Needs you
1. Read the plan (`.ai/project-spec.md` with B1–B16, `.ai/current-plan.md`) and approve the run
   (`ai-pipeline --approved --base fix/flow-batch-9 --pr-base fix/flow-batch-9 …`). No gate file
   changes are needed to start.
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
6. With a real BLOCKED task: `ai-task retry T… --note "…" --commit`, then resume; the next session
   should read the note.
7. Mission control: switch phase 2 to the commands and records in "For mission control" above.

### Covered by automated tests
Planned test groups (run with `python3 -m unittest discover -s tests -k <group>`):
- `run_record` (T301, T302): schema, current pointer, resume, stop request, retention, identity,
  bounded lock; pipeline, recovery and stand-alone `ai-run` records.
- `interrupt` (T303, T304): SIGINT/SIGTERM end a sleeping fake session, recovery session, review
  and gate within a scaled bound; partial work kept; exit codes unchanged.
- `escalation` (T305, T309): kinds, answers, redaction, hint consumption, schema check; wiring for
  blocked tasks, plan limits and questions, validation, fix-round limit, clear on resume, no
  classification from text.
- `human_stop` (T306, T307): trap records, bookkeeping commit, stop request in `stop()`,
  recovery refuses, interrupt during recovery, watchdog does not recover.
- `stop_command` (T308): stop, no run, identity mismatch, non-leader, wait expiry, cancelled
  relaunch.
- `ai_task` (T310, T312): lock, `--commit`, dirty or protected refusal, hook failure, plain `set`
  unchanged; retry, model, skip.
- `skip` (T311): SKIPPED semantics, forged status refused, refusals, `tasks set`, planning guard.
- `detach` (T313): `systemd-run` arguments, `setsid` fallback, refusals.
- `Docs` (T314).

## Human todos
- Gate files: none need changing for this batch. After merge, `setup-project --upgrade --apply` in
  each project so `.ai/bin` gets the new commands (mission control needs them installed there).
- Add G8 (answers to plan questions) and G10 (gate check command) to the vault backlog as later
  work, if wanted; tick RC-01's done gaps yourself after merge (sessions never tick them).

## Next action
Zack (or mission control on his behalf) approves the plan; then the runner starts with T118 if it
is still TODO, otherwise T301. Nothing is merged or deployed.
