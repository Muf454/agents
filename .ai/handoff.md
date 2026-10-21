# Handoff

## What has been implemented?
Nothing yet in batch 10. The plan was written 2026-10-21 in an unattended planning session on
`fix/flow-batch-10` (from `fix/flow-batch-9` at 4fea72d; batch 9 is complete there apart from
T118's host verification and is not merged; this PR targets `fix/flow-batch-9` until that
merges). Zack approved the scope on 2026-10-21.
`.ai/project-spec.md` (scope, what was verified in the code, non-goals, assumptions A1–A16),
`.ai/current-plan.md` (design) and `.ai/tasks.md` (T201–T213; T001–T046 and T101–T118 are earlier
batches, unchanged because the host protects DONE blocks).
- **FL-39** (backlog FL-35): T201, plan review decided against `--base` (`tasks newly-done`), one
  `Plan review skipped: …` line on every skip.
- **TS-01 (1)**: T202, worker default `min(14, cpu - 2)` (or the measured value below) and a
  `Workers: N (…)` first line.
- **TS-01 (2)** (with FL-28): T203 `session-gate` helper and `AI_SESSION_GATE` (auto, full,
  targeted; auto = full only when the recorded gate is under 120 s), T204 RUNNER CONTRACT and
  allowance follow the mode, T205 prompt templates defer to the contract.
- **ME-01 part 1**: T206 `events.jsonl` core (schema v1, run id in the manifest, rotation keeping
  the current run, tolerant reader), T207 `gate`, T208 `stop` (fixed categories) and `recovery`,
  T209 `run` and `pr`, T210 `ruling` and `review` events.
- **ME-01 part 2**: T211 `metrics` data and JSON, T212 `ai-status --metrics` text tables and flag.
- T213: docs, flow chart and handoff audit.
- Verified and not planned: CU-1 (per-attempt model stats) and CU-5 (crash markers and
  reconcile) are already in the code; OR-04 and BR-17 stay later (spec Non-goals).

Measured worker default: not recorded yet (mission control: write the best of 8/12/14 here before
approving; T202 uses `min(14, cpu - 2)` otherwise).

## Validation run
None on this branch yet. Batch 9's last full gate: PASS, 1104 tests (T116 tree, `ai-check`,
816.3 s). Each batch 10 task runs its `Targeted:` commands and `bash -n` in the session; the host
gate after each session is the full gate (BATCH 10 GATE RULE in the queue header).

## Assumptions
Recorded as A1–A16 in `.ai/project-spec.md`. The ones that shape behaviour most:
- A3/A4: `AI_SESSION_GATE=auto` runs the full gate in the session only when the project's recorded
  gate (largest of the last 3 passes) is 1–119 s; otherwise targeted checks only and no gate
  allowance. No recorded gate → targeted.
- A6: a new `events.jsonl`, not new kinds in `outcomes.jsonl`, because outcomes must never rotate
  (attempt numbering and crash reconcile read all of it).
- A9: rotation at 8 MiB (`AI_EVENTS_MAX_BYTES`) to `events.1.jsonl`; the current run's lines are
  copied into the new file; readers dedupe by event id.
- A10: stop categories are telemetry only; recovery never reads them (OR-04 open).
- A14: "plan untouched" = no task newly DONE since `--base`; a helper error skips the review with
  a line (fails closed).
- A15: T118 stays TODO here until `fix/flow-batch-9` is merged into this branch.
- A16: this run's sessions still get the frozen `.ai/prompts`; the BATCH 10 GATE RULE in the queue
  header tells them not to run the full gate.

## Flow chart
Flow unchanged so far (planning only, 2026-10-21). T201 (plan review decision), T204 (session gate
rule) and T208 (stop and recovery events bullet) update vault `agents-flow.md` and add hub Log
lines; T213 audits them and adds the "Flow data (ME-01)" line.

## Manual testing for the human

### Needs you
1. Before approving: merge `fix/flow-batch-9` into this branch once T118 is DONE there (both are
   at 4fea72d now; otherwise this run's first session re-verifies T118, same fix). Optionally
   record the measured worker default above.
2. This repo's installed `.ai/bin/ai-pipeline` still has the FL-39 defect, so this run would skip
   its own plan review silently (T001–T117 are DONE). Run the plan review by hand first
   (`.ai/bin/ai-review --plan --base fix/flow-batch-9`), or accept the skip.
3. Read the plan (`.ai/project-spec.md` A1–A16, `.ai/current-plan.md`) and approve the run
   (`ai-pipeline --approved --base fix/flow-batch-9 --pr-base fix/flow-batch-9 …`). No gate file
   changes are needed to start.
4. After the run: run `ai-status --metrics` (and `ai-status --metrics --json`, `--since
   2026-10-21`, `--project agents`) and check the numbers look right against what you remember of
   recent runs (tasks, first-pass rate, timeouts T108/T109/T111, median gate time about 13 min,
   review rounds). Events start only with this batch's code, so older runs show under
   `(no run record)` and have no gate events beyond the `outcome gate` fallback.
5. After merging (batch 9 first, then this one): run `setup-project --upgrade --apply` here and in
   raid-planner, family-planner and family-budget, so `.ai/bin` and `.ai/prompts` get the new
   session gate rule, the FL-39 fix and the event writers. Then watch the next real run: sessions
   should no longer run `.ai/bin/ai-check` (the `Session:` line says `gate rule targeted`) and no
   task should time out during its own gate.

### Covered by automated tests
Test groups (run with `python3 -m unittest discover -s tests -k <group>`), all TODO:
- `plan_review_base` (T201): earlier DONE tasks plus new TODO tasks get a plan review; a resumed run
  with a task newly DONE since base skips with the line; `--skip-plan-review` prints the line.
- `worker_count` (T202): default and override parsing, `Workers:` first line.
- `session_gate` (T203): mode from gate time and setting, validation and manifest.
- `session_gate_contract` (T204): contract text and allowance per mode.
- `session_gate_templates` (T205): templates defer to the contract.
- `events` (T206): schema, run id, CLI errors, redaction, rotation, tolerant reader, unwritable
  state dir.
- `events_gate` (T207), `events_stop` (T208), `events_run` and `events_pr` (T209),
  `events_ruling` and `events_review` (T210).
- `metrics` (T211, T212): fixture logs to exact JSON numbers, filters, text tables,
  `ai-status --metrics`.
- `Docs` and `flow_this_repo` (T213).

## Human todos
- Gate files: none need changing for this batch.
- Before approving: items 1–3 above.
- After merge: the upgrades in item 5; tick TS-01 (1)(2), ME-01 (parts 1 and 2), FL-35/FL-39 and
  CU-1 (verified done in code) in the vault backlog yourself (sessions never tick them).
- Later batches: mission control's display of the events, the weekly `agents-metrics.md` note,
  TS-01 (3) shared fixtures, PR-to-merge time, OR-04.

## Next action
Zack: Needs you items 1–3, then approve. The runner starts with T201.
Nothing is merged or deployed.
