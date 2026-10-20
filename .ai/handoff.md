# Handoff

## What has been implemented?
Nothing yet in batch 9: this is the plan, written 2026-10-20 in an unattended planning session on
`fix/flow-batch-9` (from `fix/flow-batch-8` at 48fd9b5; batch 8 is complete there but not merged;
this PR targets `fix/flow-batch-8`). Zack approved the scope on 2026-10-20.
`.ai/project-spec.md` (scope, what was verified in the code, assumptions A1–A13),
`.ai/current-plan.md` (design) and `.ai/tasks.md` (T101–T112; T001–T043 are batches 6–8, DONE and
unchanged because the host protects DONE blocks).
- **BR-02 pre-flight queue scan** (FL-24): T101 ruling record and row format, T102 `tasks
  preflight` (order-only reorder of TODO tasks, empty sections, overlap report), T103 wiring at
  pipeline start, after plan revisions/planning and after triage, with the raid-f4 regression.
- **BR-01 rulings**: queue order and empty sections (T103), a disposition cell with more than the
  bare ID (T104), the handoff `## Flow chart` line (T105). Once per kind per key per run, a
  `Ruling (KIND): what. Why: …. Cost if wrong: ….` run-log row; anything else stops as today.
- **BR-03 fresh retry**: T106 `attempt-info` (host outcome log: attempt number, model one tier up
  from the third attempt, failure note), T107 runner wiring (prompt note, model, run-log rows).
- **BR-14 review routing**: T108 `review-route`, T109 Codex limit memory and routing in
  `ai-review` (small low-risk fix rounds on a fresh Claude opus session), T110 "Reviewed by" in
  every review and the PR body.
- **FL-33**: T111 isolated test state and a registry guard in `tests/run_parallel.py`.
- T112: docs, flow chart and handoff audit.

## Validation run
None for batch 9 yet. Batch 8's last tree (48fd9b5): PASS, 1027 tests (T043). Each task runs its
targeted `-k` groups and the full gate in the background (queue header).

## Assumptions
Recorded as A1–A13 in `.ai/project-spec.md`. The ones that shape behaviour most:
- A1/A2: a ruling only moves TODO tasks and is claimed once per kind per key per run; without a
  run manifest no new ruling happens.
- A3: `ai-recover` is unchanged; the pre-flight on every pipeline start removes the fixable
  `Task queue is invalid` stops.
- A7: attempt number from the host outcome log (failed rows of this project, branch and task);
  from attempt 3 one tier up (haiku → sonnet → opus), no model known → opus.
- A9/A10: "final code review" = the first full-branch code review (round 1); Claude only for
  fix-round re-reviews of at most 200 changed lines outside `.ai/` with no risk path, risk word or
  opus fix task, decided from host records (fix-round records, outcome log), never from commit
  subjects. Plan reviews and re-checks stay on Codex.
- A11: a Codex limit with a known reset is remembered in host state; unknown reset → today.
- Sessions of this batch still get the frozen `.ai/prompts` of this repo (old foreground gate
  rule); the queue header's BATCH 8 GATE RULE still applies.

## Flow chart
Flow chart updated: planned only. T103, T104, T105, T107, T109 and T110 update vault
`agents-flow.md` (pre-flight scan and rulings, fresh retry, reviewer choice); the planning session
could edit only `.ai/` files, so the vault is not edited yet. T112 checks it.

## Manual testing for the human

### Needs you
1. Read the plan (`.ai/project-spec.md` assumptions A1–A13, `.ai/current-plan.md`) and approve the
   run (`ai-pipeline --approved --base fix/flow-batch-8 --pr-base fix/flow-batch-8 …`). No gate
   file changes are needed to start.
2. Decide whether the routing defaults fit your Codex budget: at most 200 changed lines, the risk
   path and word lists in A9. You can change them per run with `AI_REVIEW_SMALL_LINES`,
   `AI_REVIEW_RISK_PATHS`, `AI_REVIEW_RISK_WORDS`, or turn routing off with `AI_REVIEW_ROUTE=codex`.
3. After merging (batch 8 first, then this one): run `setup-project --upgrade --apply` here and in
   raid-planner, family-planner and family-budget, so `.ai/bin` gets the new helpers. Then retire
   mission control's `auto-reorder.sh` / `reorder-queue.py` stopgap (BR-02 replaces it).
4. On the next real run that has a fix round: check the PR's "Reviewed by" list and that a small
   fix round shows `Claude, routed`, and that a run with a Codex limit sends the second review
   straight to the fallback (the `↪` notification says `(recorded)`). This needs the real CLIs.
5. After the next self-check while a pipeline runs: `ai-dashboard --json` lists no
   `/dev/shm/ai-tests-*` checkouts (FL-33).

### Covered by automated tests
Planned test groups (run with `python3 -m unittest discover -s tests -k <group>`):
- `test_ruling_manifest_*` (T101: claim once, kept on resume, dropped on start, wrong shape
  invalid, row without `|`).
- `test_preflight_helper_*` (T102: raid-f4 order, sections, moved DONE task, cycle/unknown/prose,
  overlap report).
- `test_preflight_pipeline_*` (T103: committed raid-f4 queue repaired and run completed, repeat
  stops, DONE task would move stops, triage reorder, planning ruling row).
- `test_ruling_disposition_*` (T104: markup and CRITICAL cells rewritten, ambiguous cells left,
  plan section only, repeat stops).
- `test_ruling_flow_line_*` (T105: blank line, wording, unchanged text, missing section, runner and
  PR body).
- `test_attempt_info_*` (T106) and `test_fresh_retry_*` (T107: note, model raise, run-log rows).
- `test_review_route_*` (T108: every routing rule, forged history ignored).
- `test_codex_limit_*`, `test_review_routing_*` (T109: limit memory, routed review, risky fix
  round on Codex, reviewer settings).
- `test_reviewed_by_*` (T110) and `test_state_isolation_*` (T111).

## Human todos
- Gate files: none need changing for this batch.
- After merge: the upgrades above; retire the reorder stopgap; tick BR-01, BR-02, BR-03, BR-14,
  FL-24, FL-25, FL-30 and FL-33 in the vault backlog yourself (sessions never tick them).
- Vault hub Log: each flow-changing task appends its own dated line (the planning session could
  edit only `.ai/` files, so it added none).

## Next action
Approve and start the run; the runner begins with T101. Nothing is merged or deployed.
