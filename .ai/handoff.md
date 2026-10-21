# Handoff

## What has been implemented?
Nothing yet in batch 10. The plan was written 2026-10-21 in an unattended planning session on
`fix/flow-batch-10` (from `fix/flow-batch-9` at 4fea72d; batch 9 is complete there apart from
T118's host verification and is not merged; this PR targets `fix/flow-batch-9` until that
merges). Zack approved the scope on 2026-10-21.
`.ai/project-spec.md` (scope, what was verified in the code, non-goals, assumptions A1–A19, plan
review round 1 dispositions), `.ai/current-plan.md` (design) and `.ai/tasks.md` (T201–T218;
T001–T046 and T101–T118 are earlier batches, unchanged because the host protects DONE blocks).
Revised 2026-10-21 after Codex's hand-run plan review (`.ai/reviews/plan.md`, BLOCKER 1, MAJOR 8,
MINOR 2): every finding was confirmed in the code; 9 accepted, 2 adjusted (P7, P8), none
rejected; five tasks added (T214–T218), which sit where their dependencies require, so IDs are
not in file order. The revision is uncommitted.
- **FL-39** (backlog FL-35): T201, plan review decided against `--base` (`tasks newly-done`), one
  `Plan review skipped: …` line on every skip; T214, the supervised plan revision and its queue
  repair use the same rule and keep earlier DONE blocks byte-identical (P2).
- **TS-01 (1)**: T202, worker default `min(14, cpu - 2)` (or the measured value below) and a
  `Workers: N (…)` first line.
- **TS-01 (2)** (with FL-28): T203 `session-gate` helper and `AI_SESSION_GATE` (auto, full,
  targeted; auto = full only when a passing gate is recorded and it is under 120 s), T204 RUNNER
  CONTRACT and allowance follow the mode (existing allowance tests migrated, P9), T205 prompt
  templates defer to the contract, T215 the task format and task-writing prompts name
  `Targeted:` lines (P11).
- **ME-01 part 1**: T206 `events.jsonl` core (reserved envelope, `ruling_kind`, stable
  `events.lock`, writers guarded so no helper runs after a gate change, tolerant reader; P1, P3,
  P5), T216 run context (`AI_RUN_ID`, `run` on outcome rows and attempt markers; P8), T217
  rotation keeping every active run (P3, P4), T207 `gate`, T208 `stop` (fixed categories) and
  `recovery`, T209 `run` start and exactly one end per finish path or terminal stop (P7), T210
  `ruling` from all three writers and `review` (P5, P6), T218 `pr` events.
- **ME-01 part 2**: T211 `metrics` data and JSON (attribution by the `run` field only), T212
  `ai-status --metrics` text tables and flag.
- T213: docs, flow chart and handoff audit.
- Test selectors: every `Targeted:` line now names a verified existing group or the task's own new
  tests (P10, spec A19).
- Verified and not planned: CU-1 (per-attempt model stats) and CU-5 (crash markers and
  reconcile) are already in the code; OR-04 and BR-17 stay later (spec Non-goals).

Measured worker default: not recorded yet (mission control: write the best of 8/12/14 here before
approving; T202 uses `min(14, cpu - 2)` otherwise).

## Validation run
None on this branch yet. Batch 9's last full gate: PASS, 1104 tests (T116 tree, `ai-check`,
816.3 s). Each batch 10 task runs its `Targeted:` commands and `bash -n` in the session; the host
gate after each session is the full gate (BATCH 10 GATE RULE in the queue header).

## Assumptions
Recorded as A1–A19 in `.ai/project-spec.md`. The ones that shape behaviour most:
- A3/A4: `AI_SESSION_GATE=auto` runs the full gate in the session only when the project has a
  recorded passing gate and the largest of its last 3 passes is under 120 s; otherwise targeted
  checks only and no gate allowance. No recorded gate → targeted.
- A6: a new `events.jsonl`, not new kinds in `outcomes.jsonl`, because outcomes must never rotate
  (attempt numbering and crash reconcile read all of it).
- A8: the run is identified only by `AI_RUN_ID`, exported by `ai-pipeline`/`ai-recover` from the
  run manifest; standalone commands and pre-batch rows have no run (`(no run record)`).
- A9: a stable `events.lock` serializes writers and readers; rotation at 8 MiB
  (`AI_EVENTS_MAX_BYTES`) to `events.1.jsonl` keeps every active run (no end event, active within
  7 days) and only rotates when it frees a quarter of the cap; readers dedupe by event id.
- A10: stop categories are telemetry only; recovery never reads them (OR-04 open).
- A11: exactly one `run end` per handled finish (`pr`, `no_pr`, `no_origin`, `no_gh`) or terminal
  stop (`stopped`); none for a hand-over to recovery, a relaunch wait or a killed pipeline.
- A14: "plan untouched" = no task newly DONE since `--base`, for the review and the revision; a
  helper error skips the review with a line (fails closed).
- A17: no event helper runs after a detected gate change; those stops have no event.
- A15: T118 stays TODO here until `fix/flow-batch-9` is merged into this branch.
- A16: this run's sessions still get the frozen `.ai/prompts`; the BATCH 10 GATE RULE in the queue
  header tells them not to run the full gate.

## Flow chart
Flow unchanged so far (planning only, 2026-10-21). T201 (plan review decision), T204 (session gate
rule), T208 (stop and recovery events bullet) and T209 (run end recorded) update vault
`agents-flow.md` and add hub Log lines; T213 audits them and adds the "Flow data (ME-01)" line.

## Manual testing for the human

### Needs you
1. Before approving: merge `fix/flow-batch-9` into this branch once T118 is DONE there (both are
   at 4fea72d now; otherwise this run's first session re-verifies T118, same fix). Optionally
   record the measured worker default above.
2. This repo's installed `.ai/bin/ai-pipeline` still has the FL-39 defect, so this run would skip
   its own plan review silently (T001–T117 are DONE). Round 1 was run by hand (Codex, BLOCKER 1,
   MAJOR 8, MINOR 2) and the plan was revised (spec "Plan review round 1"; uncommitted). Commit
   the revision, then either re-run the plan review by hand on it
   (`.ai/bin/ai-review --plan --base fix/flow-batch-9`) or accept the revision without a second
   round. The frozen pipeline also cannot run a supervised revision here (the T214 defect), so
   any further round is by hand too.
3. Read the plan (`.ai/project-spec.md` A1–A19, `.ai/current-plan.md`) and approve the run
   (`ai-pipeline --approved --base fix/flow-batch-9 --pr-base fix/flow-batch-9 …`). No gate file
   changes are needed to start.
4. After the run: run `ai-status --metrics` (and `ai-status --metrics --json`, `--since
   2026-10-21`, `--project agents`) and check the numbers look right against what you remember of
   recent runs (tasks, first-pass rate, timeouts T108/T109/T111, median gate time about 13 min,
   review rounds), and against the raw `outcomes.jsonl`/`events.jsonl` lines of one run. Events
   and the `run` field start only with this batch's code, so older runs show under
   `(no run record)` and have no gate events beyond the `outcome gate` fallback.
5. After merging (batch 9 first, then this one): run `setup-project --upgrade --apply` here and in
   raid-planner, family-planner and family-budget, so `.ai/bin` and `.ai/prompts` get the new
   session gate rule, the FL-39 fix and the event writers. Then watch the next real run: sessions
   should no longer run `.ai/bin/ai-check` (the `Session:` line says `gate rule targeted`), the
   host gate decides DONE, no task should time out during its own gate, and a local-only finish
   (`--no-pr`) leaves exactly one `run end` event (the reviewer's manual check).

### Covered by automated tests
Test groups (run with `python3 -m unittest discover -s tests -k <group>`), all TODO:
- `plan_review_base` (T201): earlier DONE tasks plus new TODO tasks get a plan review; a resumed run
  with a task newly DONE since base skips with the line; `--skip-plan-review` prints the line.
- `plan_review_followup` (T214): a MAJOR plan review on a follow-up batch is revised, re-reviewed
  and implemented with earlier DONE blocks unchanged; base-relative queue repair.
- `worker_count` (T202): default and override parsing, `Workers:` first line.
- `session_gate_mode`, `session_gate_setting` (T203): mode from gate time and setting, validation
  and manifest.
- `session_gate_contract` and the migrated `session_gate_allowance` (T204): contract text and
  allowance per mode, fallback without `Targeted:` lines.
- `session_gate_templates` (T205) and `session_gate_targeted_lines` (T215): templates defer to the
  contract; task format and prompts name `Targeted:`.
- `events_core` (T206): envelope, `ruling_kind`, CLI errors, redaction, concurrent appends,
  tolerant reader, unwritable state dir, no helper after a gate change.
- `events_run_context` (T216): run id, rows carry the run, consecutive runs, crash in a later run.
- `events_rotation` (T217): every active run kept across two rotations, waiting writers lose
  nothing, stale runs, crash between replaces.
- `events_gate` (T207), `events_stop` (T208), `events_run_end` (T209), `events_ruling` and
  `events_review` (T210), `events_pr` (T218).
- `test_metrics` (T211, T212): fixture logs to exact JSON numbers, attribution by run field,
  filters, text tables, `ai-status --metrics`.
- `Docs` and `flow_this_repo` (T213).

## Human todos
- Gate files: none need changing for this batch.
- Before approving: items 1–3 above.
- After merge: the upgrades in item 5; tick TS-01 (1)(2), ME-01 (parts 1 and 2), FL-35/FL-39 and
  CU-1 (verified done in code) in the vault backlog yourself (sessions never tick them).
- Later batches: mission control's display of the events, the weekly `agents-metrics.md` note,
  TS-01 (3) shared fixtures, PR-to-merge time, OR-04.

## Next action
Zack: commit the plan revision, Needs you items 1–3, then approve. The runner starts with T201.
Nothing is merged or deployed.
