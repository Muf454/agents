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
  (host-checked since the stage start, committed or not). The host validates the section, makes
  the one counted commit `chore(ai): record plan revision` and records it in host state. The
  pipeline then ALWAYS runs a fresh plan review (also when only dispositions changed), with the
  revision's dispositions as context. Limit: `AI_SUPERVISE_PLAN_ROUNDS` (default 3) revisions per
  human-started run; then it stops for the human ("plan review: supervision limit reached").
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
  question, and the pipeline stops (no recovery session). Every supervised step appends to the run
  log and notifies ("🔁 Plan revised (round n/N): accepted a, rejected b"; "🔁 Extra fix round:
  findings falling (x → y → z)"; "🔁 Review format retry (mode): <error>"). Claude session time
  counts toward one host-owned run budget (see decisions). `AI_SUPERVISE=0` restores today's
  behaviour exactly: no revision, no extra fix round, no format retry.
- **R6 Docs and flow chart.** README, `docs/workflow.md`, vault `agents-flow.md` updated in the
  same task as each flow change; PR says "Flow chart updated".

## Settings
User config (`~/.config/ai-toolkit/config`) or environment, validated before any agent starts,
captured in the run manifest and restored on recovery resumes (a changed config file does not
change a running run): `AI_SUPERVISE` (0|1, default 1), `AI_SUPERVISE_PLAN_ROUNDS` (0–9, default
3), `AI_SUPERVISE_ESCALATE_ROUND` (1–9, default 3), `AI_SUPERVISE_ESCALATE_MODEL` (model name,
default `claude-fable-5-1`).

## Decisions (planning, 2026-10-07; plan review round 1)
- **Run budget (Zack's Q2 decision, 2026-10-05, OR-09 defaults: 16 h work + 12 h waiting per
  approved run, cumulative across recoveries and fix rounds).** One host-owned budget of Claude
  session time for the whole human-started pipeline run, default 57600 s (16 h, `AI_RUN_BUDGET`):
  implementation, triage, plan revisions and the extra fix round all draw from it. Each `ai-run`
  invocation keeps its own `--run-timeout` (default 14400 s) as a per-call cap inside that budget,
  so ordinary runs are not shortened. Waiting stays bounded separately (usage-limit pauses,
  `AI_LIMIT_MAX_WAIT`; a cumulative 12 h wait budget is OR-09's, not this batch). Stored in the run manifest, preserved across recovery resumes, reset only by a human
  start. Usage-limit pauses are not charged (as in `ai-run` today; bounded by
  `AI_LIMIT_MAX_WAIT`). An invocation interrupted by a crash is charged its full grant at the next
  start (fails closed). Reviews are Codex/fallback time with their own `--review-timeout` and are
  not charged, but no supervised step (revision, re-review after it, extra fix round, format
  retry) starts when the budget is exhausted; exhaustion stops for the human ("Run budget
  exhausted"). Hand-run `ai-run` keeps its per-invocation `--run-timeout`.
- **Separate plan-dispositions file.** Plan-round sections live in
  `.ai/reviews/plan-dispositions.md`, not `dispositions.md`: `start-dispositions` rewrites
  `dispositions.md` for every code review and triage/re-check scan all of its rows, so plan rows
  there would be erased or mixed into code-review checks. (This repo's manual round-1 record stays
  in `dispositions.md`, as requested.)
- **History is context, records are authority.** Limits, round numbers, revision completion and
  fix-round trends come from host state outside the checkout (run manifest, per-branch records),
  never from commit subjects or checkout files; rendered history only informs prompts.

## Acceptance criteria
- Mocked pipeline: plan MAJOR → revision → re-review APPROVE → implementation → review → PR.
- All-rejected, dispositions-only revision → a second plan-review call before any implementation.
- Limit reached, needs-human, budget exhausted, out-of-scope revision → human stop; with
  `AI_AUTO_RECOVER=1` no recovery Claude session runs.
- Crash before the revision commit, after it, and after stage closure → resume completes and
  counts the revision exactly once and runs the re-review once.
- Extra fix round only for a strictly falling host-verified trend, once per run.
- Malformed plan/code review retried once; integrity failures and re-checks never retried.
- `AI_SUPERVISE=0` → today's behaviour in all three areas.

## Non-goals
No supervisor daemon; no change to who reviews (Codex, Claude fallback); no re-check retry.
FL-02 retrospective is a separate batch.
