# Spec: FL-04 bounded supervisor for "needs a human" stops

## Objective
Backlog FL-04 (vault `agents-backlog.md`, "Run flow improvements", approved by Zack 2026-10-06;
chosen as next agents work by Zack 2026-10-07). Evidence from 2026-10-07: mission control revised
plans by hand after 7 plan-review stops (raid-planner ownership fixes rounds 1–4, agents catch-up
fixes, family M2 earlier), each time: read the plan review, accept/reject each finding with
evidence, revise spec/tasks, record dispositions, commit, rerun `ai-pipeline`. Within limits Zack
sets, the toolkit does this itself; every step is logged and notified and Codex still reviews
every plan revision.

## Requirements
- **R1 Plan-review stop → bounded revision.** When `ai-pipeline`'s plan review returns BLOCKER or
  MAJOR findings and supervision is enabled, a fresh Claude planning session (`ai-run
  --revise-plan`; no implementation) evaluates each BLOCKER/MAJOR finding against the repository
  (accepted / rejected with concrete evidence / needs-human), revises the plan and fills a
  host-written section for that plan-review round in `.ai/reviews/plan-dispositions.md`. It may
  change only `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`,
  `.ai/reviews/plan-dispositions.md`, `.ai/handoff.md`, `.ai/state.md`, `.ai/run-log.md`
  (host-checked since the stage start, committed or not). The host validates the section, writes
  the revision's run-log entry, makes the one counted commit `chore(ai): record plan revision`
  (records and that log entry together) and records it with its outcome in host state. The
  checkout is therefore clean when the pipeline then ALWAYS runs a fresh plan review (also when
  only dispositions changed), with the revision's dispositions as context. Limit:
  `AI_SUPERVISE_PLAN_ROUNDS` (default 3) revisions per human-started run; then it stops for the
  human ("plan review: supervision limit reached").
- **R2 Convergence and escalation.** Plan-review round n is the n-th host-recorded plan review on
  the branch; revision n answers it. From round 3 the section needs a same-line `Convergence:
  <text>` (as FL-03 for code-review triage) and the prompt asks to redesign a repeating area as a
  whole. Earlier rounds (findings + dispositions) are supplied as context only. The revision runs
  on `opus`; from round `AI_SUPERVISE_ESCALATE_ROUND` (default 3) on `AI_SUPERVISE_ESCALATE_MODEL`
  (default `claude-fable-5-1`; Zack 2026-10-07 for raid-planner).
- **R3 Fix-round extension.** When the code-review fix-round limit is reached with BLOCKER/MAJOR
  open, allow ONE extra round per run only if the BLOCKER+MAJOR count fell in each of the last two
  rounds, judged from host-verified counts (recorded by the host when each round's verified
  review was triaged, plus the current verified review), never from commit subjects. The
  allowance is reserved in host state before the round starts. Otherwise stop as today (draft PR).
- **R4 Malformed review output.** A plan or code review (Markdown) rejected by the host's format
  checks (missing required field/section, counts line missing or not matching the listed IDs) is
  retried once with the format error appended to the prompt; the second failure stops as today.
  Integrity failures (reviewer exit/limit errors, checkout changed, provenance/binding/storage)
  are never retried. Re-checks (JSON) are out of scope: malformed answers stay "upheld"
  (fail closed), one call.
- **R5 Guard rails.** Never edits gate files, prompts, permissions or code; scope and irreversible
  decisions are escalated, not decided: the session marks such findings `needs-human` with the
  question, and the pipeline stops (no recovery session). The host stores that outcome (counts and
  the bounded questions) in its revision record before the stage closes, so the decision survives
  a crash: while the current plan report has a revision record with needs-human rows, no
  re-review, revision, implementation or recovery Claude session starts (pipeline start, loop
  entry and `ai-recover` all check it). The human answers (plan files and/or the section),
  commits and runs `ai-review --plan` by hand; the new report has no such record, so the next
  `ai-pipeline` continues. Every supervised step appends to the run log and notifies ("🔁 Plan
  revised (round n/N): accepted a, rejected b"; "🔁 Extra fix round: findings falling (x → y →
  z)"; "🔁 Review format retry (mode): <error>"). Supervision is bounded by counts only (see
  decisions). `AI_SUPERVISE=0` restores today's behaviour exactly: no revision, no extra fix
  round, no format retry.
- **R6 Docs and flow chart.** README, `docs/workflow.md`, vault `agents-flow.md` updated in the
  same task as each flow change; PR says "Flow chart updated".

## Settings
User config (`~/.config/ai-toolkit/config`) or environment, validated before any agent starts,
captured in the run manifest and restored on recovery resumes (a changed config file does not
change a running run): `AI_SUPERVISE` (0|1, default 1), `AI_SUPERVISE_PLAN_ROUNDS` (0–9, default
3), `AI_SUPERVISE_ESCALATE_ROUND` (1–9, default 3), `AI_SUPERVISE_ESCALATE_MODEL` (model name,
default `claude-fable-5-1`). The validated values are exported, and `ai-review`/`ai-run` validate
them too, so children never see a raw value.

## Decisions (planning, 2026-10-07; plan review rounds 1–3)
- **Bounded by counts; no run budget in this batch (mission control, 2026-10-08, after plan
  review round 3).** Supervision is bounded by: at most `AI_SUPERVISE_PLAN_ROUNDS` plan revisions
  and at most one extra fix round per human-started run, at most one format retry per review
  call, plus the existing per-call limits (`ai-run --run-timeout` and `--session-timeout`,
  `--review-timeout`, `AI_LIMIT_MAX_WAIT`). A revision is an ordinary `ai-run` call under those
  limits. The host-owned cumulative budget of Zack's Q2 decision (2026-10-05: 16 h work + 12 h
  waiting per approved run, cumulative across recoveries and fix rounds) stays backlog item
  **OR-09**: the shared budget drew findings in every plan-review round (1–3) and is removed from
  FL-04 so this batch converges. No `AI_RUN_BUDGET` setting, no `--host-budget` flag, no manifest
  budget here.
- **Separate plan-dispositions file.** Plan-round sections live in
  `.ai/reviews/plan-dispositions.md`, not `dispositions.md`: `start-dispositions` rewrites
  `dispositions.md` for every code review and triage/re-check scan all of its rows, so plan rows
  there would be erased or mixed into code-review checks. (This repo's manual round-1 record stays
  in `dispositions.md`, as requested.)
- **History is context, records are authority.** Limits, round numbers, revision completion and
  outcome (needs-human), and fix-round trends come from host state outside the checkout (run
  manifest, per-branch records), never from commit subjects or checkout files; rendered history
  only informs prompts.

## Acceptance criteria
- Mocked pipeline: plan MAJOR → revision → re-review APPROVE → implementation → review → PR; the
  checkout is clean right before the re-review (the revision's run-log entry is committed).
- All-rejected, dispositions-only revision → a second plan-review call before any implementation.
- Limit reached, needs-human, out-of-scope revision → human stop; with `AI_AUTO_RECOVER=1` no
  recovery Claude session runs.
- Needs-human survives a crash between stage closure and question handling: a human rerun and a
  watchdog recovery both stop with the questions and start no reviewer, revision, implementation
  or recovery session; after the human's hand-run `ai-review --plan` the pipeline continues.
- Crash between reservation and stage start, before the revision commit, after it, and after
  stage closure, and between a plan review's host commit and its round record → resume completes
  and counts the revision exactly once, runs the re-review once, and a round-≥3 revision resumes
  on the escalation model.
- Plan rounds count only from the run's base, so a re-created branch name starts at round 1.
- Extra fix round only for a strictly falling host-verified trend, once per run.
- Malformed plan/code review retried once; integrity failures and re-checks never retried.
- `AI_SUPERVISE=0` → today's behaviour in all three areas.

## Non-goals
No supervisor daemon; no change to who reviews (Codex, Claude fallback); no re-check retry; no
cumulative run or wait budget (OR-09). FL-02 retrospective is a separate batch.
