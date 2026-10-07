# Spec: Efficiency batch: gate speed (FL-11), review context (B3), review convergence (FL-03)

## Objective
Efficiency batch: gate speed (FL-11), review context (B3), review convergence (FL-03)
Cut wasted time and tokens in every pipeline run without touching safety rules: a full gate
that fits inside one session tool call, Codex reviews that start from what earlier rounds
already found, and triage that stops patching symptoms when the same area keeps failing.

Source: vault [[agents-backlog]]: FL-11 (new, 2026-10-07), B3 ("Better for both agents",
P2, S) and FL-03 ("Run flow improvements", P1, S; next in line after batch 2). Chosen by Zack
on 2026-10-07 as high-impact, low-investment work. Planned by Claude as Zack's delegate on
2026-10-07; the pipeline's Codex plan review gates it.
Hub decisions respected: risk-based models with no usage-saving downgrades (2026-10-06),
roles vs providers, "auto-recovery never changes the gate", gate files are never edited by
a pipeline session.

Branch note: planned on top of `feature/flow-batch-2` (PR #15, open) because T003/T004 touch
the same files. Start only after PR #15 is merged; then merge `master` into this branch so
its PR shows only this batch (no stacked PRs, hub decision 2026-10-04).

## Requirements
- **FL-11 Gate speed.** The full test suite (224+ tests, 611 s serial on 2026-10-07, over the
  600 s Bash tool limit that sessions use for `.ai/bin/ai-check`) runs in parallel shards.
  A stdlib-only runner `tests/run_parallel.py` collects every test ID, splits them across
  worker processes (`AI_TEST_WORKERS`, default `min(8, cpu count)`), each running its share
  with `python3 -m unittest`, and reports one summary line `Ran N tests in S s` plus
  `OK` / `FAILED (failures=…, errors=…)`. Exit status non-zero on any failure, error, crash,
  or when zero tests were collected or the collected count differs from the count run. The
  output of failing tests is shown in full. Serial `python3 -m unittest discover -s tests`
  keeps working unchanged (CI and humans can still use it).
- **Gate switch is a human step.** `.ai/validate` is a gate file. No pipeline session edits
  it. After the batch is reviewed, Zack (or the coordinating Claude session with Zack's
  approval) changes its last line to `python3 tests/run_parallel.py` in the same PR. Until
  then the gate stays serial (host `ai-check` timeout is 1800 s, so the host gate passes).
- **Review history helper.** `workflow.py review-history BASE` prints a compact Markdown
  summary of earlier review rounds on this branch: for each host commit
  `chore(ai): record independent review` in `BASE..HEAD` that changed
  `.ai/reviews/current.md` (oldest first, numbered from 1): the reviewed HEAD, the BLOCKER and
  MAJOR finding IDs with their one-line titles, and each finding's disposition from the
  `.ai/reviews/dispositions.md` committed in the following `chore(ai): record review triage`
  commit (accepted + task ID / rejected / deferred / "no triage recorded"). Output capped at
  6000 characters (oldest rounds dropped first, with a line saying how many were dropped).
  Prints nothing when there is no earlier round. It is context only: it never authorizes,
  counts or skips anything (fix-round counting stays with `fix-rounds`).
- **B3 Codex review context.** `ai-review --base` (implementation review only, not plan
  review or recheck) appends a `PREVIOUS ROUNDS` section from `review-history` and, when an
  earlier round exists, `CHANGED SINCE THE LAST REVIEW: git diff <last reviewed HEAD>..HEAD`.
  The review prompt (template `review.md`) says: verify that every earlier accepted finding is
  really fixed, do not re-raise rejected findings without new evidence, and still review the
  whole range (cross-cutting defects; Codex's objection to delta-only reviews).
- **FL-03 Convergence rule.** `ai-run --triage` appends the same `PREVIOUS ROUNDS` section to
  the triage prompt. Template `triage.md` gains the rule: when the same area (module, data
  model or concern) has had BLOCKER/MAJOR findings in three consecutive rounds counting the
  current one, do not add another symptom fix: add one design task first ("the model lacks
  X": a short design note in `.ai/current-plan.md` plus the change) and point the accepted
  findings at it. Deterministic part: when the current review is round 3 or later,
  `triage-check --fresh` requires a line `Convergence: <text>` in `dispositions.md`
  (naming the design task, or saying why no area repeats); missing → the existing triage
  failure path.

## Non-goals
- No change to `.ai/validate`, `.ai/bin`, `.ai/prompts`, permissions or the CI workflow in
  the run itself. No change to fix-round limits, dispute handling or review authority.
- No E3 (Codex effort per review type) and no E5 (validation reuse): separate backlog items.

## Acceptance
- `python3 tests/run_parallel.py` runs the full suite with the same test count as the serial
  run, passes three consecutive times locally, and takes under 200 s on this machine
  (16 cores) with default workers.
- New tests cover `review-history` (no rounds, two rounds with dispositions, missing triage,
  cap), the `ai-review` prompt content (history present only for implementation review),
  the triage prompt content, and `triage-check --fresh` with and without `Convergence:` at
  round 3.
- README / `docs/workflow.md` describe the parallel runner, the review context and the
  convergence rule; vault flow chart updated in the task that changes the flow.
