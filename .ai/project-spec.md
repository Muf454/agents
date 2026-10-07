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
  MAJOR findings, and supervision is enabled, a fresh Claude planning session (no implementation;
  may edit only `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`,
  `.ai/reviews/dispositions.md`, `.ai/run-log.md`, `.ai/state.md`, `.ai/handoff.md`) evaluates each
  finding against the repository (accepted / rejected with concrete evidence), revises the plan,
  records a dispositions section for that plan-review round and commits. The pipeline then reruns
  the Codex plan review. Limit: `AI_SUPERVISE_PLAN_ROUNDS` (default 3) revisions per run;
  then it stops for the human as today.
- **R2 Convergence and escalation.** From the third plan-review round in the same area the
  revision must state a `Convergence:` line (as FL-03 does for code review triage) and redesign the
  area as a whole instead of patching. The planning session runs on `opus`; from round
  `AI_SUPERVISE_ESCALATE_ROUND` (default 3) on `AI_SUPERVISE_ESCALATE_MODEL` (default
  `claude-fable-5-1`; Zack 2026-10-07 for raid-planner).
- **R3 Fix-round limit.** When the code-review fix-round limit is reached with BLOCKER/MAJOR still
  open, allow ONE extra round only if the BLOCKER+MAJOR count fell in each of the last two rounds;
  otherwise stop as today (draft PR).
- **R4 Malformed review output.** A Codex review rejected by the host's format checks (e.g. missing
  `## MINOR findings` section, counts not matching IDs) is retried once with the format error
  appended to the prompt before stopping.
- **R5 Guard rails.** Never edits gate files, prompts, permissions or code; scope and
  irreversible decisions (a finding that needs Zack's decision, e.g. repairing production data)
  are escalated, not decided: the session marks such findings `needs-human` and the pipeline stops.
  Every supervised step appends to the run log, notifies ("🔁 plan revised (round n): accepted a/b,
  rejected c") and counts toward the run budget. Disabled with `AI_SUPERVISE=0`.
- **R6 Docs and flow chart.** README, `docs/workflow.md`, vault `agents-flow.md` updated; PR says
  "Flow chart updated".

## Non-goals
No supervisor daemon; no change to who reviews (Codex, Claude fallback). FL-02 retrospective is a
separate batch.
