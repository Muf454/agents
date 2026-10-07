# Task queue

Branch `feature/supervisor` (FL-04, bounded supervisor for "needs a human" stops). Prioritised by
Zack 2026-10-07 before the dashboard (DB-01). Edit `scripts/`, `templates/`, `tests/`, docs and the
vault notes named below. Never edit `.ai/bin`, `.ai/prompts` or other gate files of this repo.
Every task leaves `.ai/bin/ai-check` passing. Flow-chart rule: T006 updates the vault `agents-flow.md`.

## T001 — Supervised plan revision loop in ai-pipeline
Status: TODO
Dependencies: none
Model: opus

### Goal
R1, R5: a plan review with BLOCKER/MAJOR findings leads to a bounded, logged revision round instead of an immediate human stop.

### Implementation notes
`scripts/ai-pipeline` plan-review block: when `plan_blockers + plan_majors > 0` and `AI_SUPERVISE` is not `0` and fewer than `AI_SUPERVISE_PLAN_ROUNDS` (default 3, from the user config like other `AI_*` settings) revisions happened in this run, run `ai-run --revise-plan` (new mode, T002), verify the gate (`ai_guard_verify`) and that only the allowed records changed since the stage start (reuse the triage `--since` record check), commit, then loop back to the plan review. Count rounds from the run manifest/state so a resumed pipeline does not reset the limit. A revision that marks any finding `needs-human` stops with that reason. Each round: `ai_log`, `ai_notify "🔁 Plan revised (round n/N): accepted a, rejected b"`, and the time counts toward the run budget. Limit reached → stop as today with "plan review: supervision limit reached".

### Likely affected modules
scripts/ai-pipeline, scripts/lib/workflow.py (round counting, record check), tests/test_workflow.py

### Acceptance criteria
- Mock run: plan review MAJOR → revision → plan review APPROVE → implementation starts (one test).
- Limit reached → human stop with the reason; `AI_SUPERVISE=0` → today's behaviour; resume keeps the count.
- A revision touching a non-record file stops the run.

### Validation
targeted tests; `.ai/bin/ai-check`

### Result / notes

## T002 — Plan revision session: prompt, dispositions round, validator
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
R1, R2: the planning session evaluates each plan finding and records a checkable decision.

### Implementation notes
`scripts/ai-run --revise-plan`: one fresh Claude session with `templates/.ai/prompts/plan-revision.md` (installed as `.ai/prompts/plan-revision.md`), the plan review, earlier plan-review rounds (reuse `review-history` from the efficiency batch) and the editable-file list from the spec. It appends a section "## Plan review round n (HEAD …)" to `.ai/reviews/dispositions.md`: one row per BLOCKER/MAJOR (accepted with the task it changed / rejected with concrete evidence / needs-human with the question for Zack). Validator `workflow.py plan-dispositions-check`: every finding ID of the current plan review has a row; rejected rows have evidence text; from round 3 a same-line `Convergence: <text>` is present. `setup-project` installs the new prompt.

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, templates/.ai/prompts/plan-revision.md, scripts/setup-project, tests/test_workflow.py

### Acceptance criteria
- Validator tests: missing row, rejected without evidence, round 3 without Convergence → fail; complete → pass.
- The session's allowlist allows edits only to the records listed in the spec (test of the generated arguments).

### Validation
targeted tests; `.ai/bin/ai-check`

### Result / notes

## T003 — Escalation model and fix-round extension
Status: TODO
Dependencies: T002
Model: opus

### Goal
R2, R3.

### Implementation notes
Plan revision model: `opus`, from round `AI_SUPERVISE_ESCALATE_ROUND` (default 3) `AI_SUPERVISE_ESCALATE_MODEL` (default `claude-fable-5-1`); logged in the outcome log as a task-like event (`kind: plan_revision`). Fix rounds: when `fixes >= max_fix_rounds` with BLOCKER/MAJOR open, allow one extra round (once per run) only if the BLOCKER+MAJOR count fell in each of the last two review rounds (read from the review history); otherwise today's draft PR. Notify "🔁 Extra fix round: findings falling (x → y → z)".

### Likely affected modules
scripts/ai-pipeline, scripts/ai-run, scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Round 3 uses the escalation model (mock args), rounds 1–2 opus.
- Extra round only when counts fall twice; at most once per run; flat or rising counts → draft as today.

### Validation
targeted tests; `.ai/bin/ai-check`

### Result / notes

## T004 — Retry a malformed review once
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
R4: a review rejected by the host's format checks is retried once with the error before stopping.

### Implementation notes
`scripts/ai-review` (plan, code and recheck modes; Codex and Claude fallback): when publishing fails a format check (missing section, counts not matching IDs, no verdict line), rerun the reviewer once with `FORMAT ERROR: <message>. Return the full report again in the required structure.` appended; the second failure stops as today. Keep the first output in `.ai/local/` for inspection.

### Likely affected modules
scripts/ai-review, scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Mock reviewer: malformed then valid → published; malformed twice → stop; valid first → one call.

### Validation
targeted tests; `.ai/bin/ai-check`

### Result / notes

## T005 — End-to-end supervision scenarios
Status: TODO
Dependencies: T003, T004
Model: sonnet

### Goal
The whole loop works through `ai-pipeline` with mocks.

### Implementation notes
Scenarios in `tests/test_workflow.py` (mock Codex/Claude like the convergence tests): MAJOR → revision → APPROVE → implementation → review → PR; needs-human finding stops with the question in the notification; three revisions then limit stop; escalation model at round 3; extra fix round when findings fall; malformed plan review retried.

### Likely affected modules
tests/test_workflow.py

### Acceptance criteria
- All scenarios pass under `tests/run_parallel.py`.

### Validation
`.ai/bin/ai-check`

### Result / notes

## T006 — Docs, flow chart, handoff
Status: TODO
Dependencies: T005
Model: haiku

### Goal
R6: docs and the flow chart match the code.

### Implementation notes
README and `docs/workflow.md` (supervision settings, limits, needs-human, escalation, extra fix round, malformed retry), `templates/CLAUDE.md`/`AGENTS.md` if they describe stops; vault `agents-flow.md` (plan-review loop and extra fix round) and a hub Log line; `.ai/handoff.md` "Manual testing for the human" (Needs you: one real supervised run on a small plan; everything else covered by named tests). PR body: "Flow chart updated".

### Likely affected modules
README.md, docs/workflow.md, templates/, .ai/handoff.md, vault agents-flow.md, agents.md

### Acceptance criteria
- `docs_consistency` tests pass with new required sentences; flow chart updated.

### Validation
`python3 -m unittest discover -s tests -k docs_consistency`; `.ai/bin/ai-check`

### Result / notes
