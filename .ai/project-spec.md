# Spec: Flow batch 9: pre-flight queue scan, rulings, fresh retries, review routing, isolated test state

## Objective
Five items, approved by Zack on 2026-10-20, planned 2026-10-20 on `fix/flow-batch-9` (from
`fix/flow-batch-8` at 48fd9b5; batch 8 is complete there but not merged; this PR targets
`fix/flow-batch-8`). Sources: vault `agents-backlog.md` "Borrowed from other projects (2026-10-20)"
(BR-01, BR-02, BR-03, BR-14), FL-24, FL-25, FL-30, FL-33, and `agents-alternatives.md`.
1. **BR-02 Pre-flight queue scan** (supersedes mission control's `auto-reorder.sh` stopgap for
   FL-24): before the first task and after every plan revision or triage, the host checks the
   queue, reorders it when only the order is wrong (logged as a ruling), and reports task pairs
   that share a likely-affected file.
2. **BR-01 Rulings instead of escalations**: record-format and queue problems the host can fix
   deterministically are fixed once per kind per task, logged as `Ruling: what, why, cost if
   wrong`, and the run continues; everything else stops as today.
3. **BR-03 Fresh retry with failure notes, stronger model later**: the next session of a task that
   failed gets a short host note of what failed; from the third attempt it runs one model tier up.
4. **BR-14 Spend Codex where it matters most**: Codex for plan reviews, the first full code review,
   re-checks and risky or large fix-round diffs; a fresh Claude opus review for small low-risk
   fix-round re-reviews; skip Codex while a recorded Codex usage limit has not reset; a
   "Reviewed by" field in review records and the PR body.
5. **FL-33**: self-check fixtures never register in the host's real run registry.
6. Docs: README, docs/workflow.md, the vault flow chart, the handoff.

## Verified against the code (48fd9b5)
- Queue rules: `tasks()` (`scripts/lib/workflow.py` ~432–468) fails `dependencies must exist
  earlier in the queue` and `missing ### <section>`. `tasks reorder` (~493–557, stable DFS in
  file order, rejects cycles, unknown IDs and prose) and `tasks fill-sections` (~576–620, TODO
  tasks only, adds an empty `Likely affected modules`/`Result / notes`) already exist.
- They run only after sessions: `ai-run --plan` (~440–446: fill, reorder, check), `--revise-plan`
  (~551–560: fill, reorder, check) and `--triage` (~641–645: fill and check, **no reorder**), plus
  `revision-queue-repair` for an interrupted uncommitted revision (~3318; `ai-pipeline` ~451–460).
  A **committed** out-of-order queue still stops at `ai-pipeline` ~461–464 (`Task queue is
  invalid: …`), and `ai-recover` ~285–290 escalates that reason as a hard rule. This is the
  raid-planner F4 stop of 2026-10-20 (T004, a docs task, depending on the later T005 and T006).
- No helper reports tasks that share a likely-affected file. Reorder output is printed, never
  logged in the run log. `ai_log` (`scripts/lib/common.sh` ~309) writes a table row without
  escaping `|`.
- Dispositions: `FINDING_CELL`/`DISPOSITION_ROW` (~1056–1066) already accept `ID (SEVERITY)
  title`, `ID: title` and `ID — title` (FL-16, FL-30's family-budget row: T029 regression), and
  `TABLE_CELL` accepts `\|` (FL-25b). Still unmatched: an ID wrapped in markup (`**M1**`,
  `` `M1` ``, `[M1]`) or followed by a non-severity parenthesis (`M1 (CRITICAL)`); triage then fails
  `… has no disposition` (`triage_check` ~1105) and the revision `… has no row` (~3077).
- Handoff `## Flow chart`: `pr_body` (~4282) copies the section; only this repo's gate test
  `test_pr_body_flow_this_repo_declares_the_flow_chart` (tests ~12918) requires the line right
  after the heading to start with `Flow chart updated` or `Flow unchanged`. A blank line or other
  wording there fails the host gate here.
- Retries: a failed session ends `ai-run` (`ai_die`; timeout, error, failed host gate); a
  BLOCKED task continues with independent tasks (`gate_only_retry`, batch 8). The next session of a
  task after `ai-recover` resumes is always a fresh `claude -p`, but its prompt says nothing about
  the earlier attempt (prompt ~884–892), and the model is always `tasks model` (~880). The host
  outcome log (`outcome task`, ~3914–3946, state root `outcomes.jsonl`) already records every
  attempt's task, result, model and seconds per project and branch. Attempt limits today:
  the session budget, `AI_RECOVER_MAX` (2), `timeout-rerun` and `gate-unblock` (once per task).
- Reviews: `ai-review` `run_review` (~152–217) always tries Codex first in `auto`; on a Codex limit
  it falls back to Claude for that one call (`↪` notification, `fallback-log.md` for a Codex
  catch-up). Nothing remembers the limit for the next review, so every review in a limit window
  spends a Codex call first. `review-risk` (~3369) only picks the Claude fallback model. The Codex
  report gets no reviewer line (`reviewer_label` ~961); the PR body heading names Codex or the
  Claude fallback (~4300). `review_rounds` (~1168) is documented "context only, never authority:
  … nothing here may approve, count or skip anything", so routing must read host records
  (`fix-rounds count`, the outcome log), never review commit subjects.
- FL-33: the main test fixture sets `AI_STATE_DIR` (tests ~880), but some tests clear it (e.g.
  ~2348, ~2373) and the dashboard/observation tests patch `os.environ` only in-process; any child
  process started from the plain environment registers in `~/.local/state/ai-toolkit/pipelines`
  (`pipeline_register` ~4911).

## Scope
- R1 `tasks preflight` (new helper action): on the working queue, when the only fault is order,
  reorder as `tasks reorder` does, but only when every task whose position changes is TODO; add
  missing empty sections to TODO tasks as `fill-sections`; print one `Ruling:` line per change and
  an overlap report (earlier/later TODO task pairs sharing a path in `### Likely affected
  modules`). Any other fault prints nothing new and fails as today.
- R2 Host ruling record: `run-manifest ruling KIND KEY` (once per kind per key per human-started
  run; field `rulings`; same lifecycle as `timeout_reruns`), and one run-log row format `Ruling
  (KIND): WHAT. Why: WHY. Cost if wrong: COST.` with `|` and newlines removed.
- R3 Pre-flight call sites: `ai-pipeline` start (committed queue, before the plan review and
  before `tasks check`; the host commits `chore(ai): ruling: task queue`), after every plan revision
  and planning session (ruling rows), and after triage (reorder added).
- R4 Record-format rulings: (a) a disposition row whose first cell holds exactly one finding ID of
  the current review wrapped in markup or followed by other text the parser rejects is rewritten to
  the bare ID before `triage-check`/`plan-dispositions-check`; (b) the handoff's `## Flow chart`
  section gets a first line starting `Flow chart updated` or `Flow unchanged` right after the
  heading before every host gate and before the PR body. Both claim a ruling; a repeat stops as
  today.
- R5 Fresh retry: `attempt-info TASK BASE_MODEL` (host outcome log) gives the attempt number,
  the effective model (one tier up from the third attempt) and a short failure note; `ai-run` uses
  them for the session, appends the note to the prompt, and names attempt and model in the run log.
- R6 Review routing: `review-route MODE BASE HEAD` decides Codex or Claude from host records and
  the diff; `codex-limit set|active` remembers a Codex limit with a known reset in host state;
  `ai-review` (auto reviewer only) skips Codex while the limit is active (fallback as today) and
  sends routed reviews to a fresh Claude opus session (labelled "routed", not a fallback, no
  catch-up entry). Settings `AI_REVIEW_ROUTE`, `AI_REVIEW_SMALL_LINES`, `AI_REVIEW_RISK_PATHS`,
  `AI_REVIEW_RISK_WORDS` are captured in the run manifest like the other `AI_*` settings.
- R7 "Reviewed by": every published plan/code review carries a `Reviewed by:` line; the outcome
  log's review row carries the route reason; the PR body lists who reviewed each round.
- R8 FL-33: test modules isolate host state for themselves and every child process; the parallel
  runner fails when the suite left a registry entry under its temp directory in the real registry.
- Every behaviour change gets an offline regression test in the existing style; each task that
  changes the flow updates the vault flow chart in the same task.

## Non-goals
- Any edit to gate files: `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/ci-setup`,
  `.ai/permissions.allow`, `.claude/settings.json`, `.github/workflows/*`. The new behaviour
  reaches this repo's own pipeline only after the human's upgrade (handoff).
- Rulings for anything else: cycles, unknown IDs, prose in `Dependencies:`, a moved DONE task,
  missing Goal/Implementation notes/Acceptance criteria/Validation, a plan that contradicts itself,
  gate, policy, branch, provenance, security or outside-the-checkout problems all stop as today.
- `ai-recover` rule changes: with the pre-flight at every pipeline start, no `Task queue is
  invalid` stop remains that a ruling could fix (A3).
- Changing the plan review (always Codex, high effort; Zack's answer Q3 of 2026-10-05) or the
  re-check (cross-family by design, R3 of batch 1).
- Usage display in mission control (separate app) and lower Codex effort for small reviews
  (small reviews go to Claude instead).
- BR-04 to BR-17 other than BR-14; LP-01.

## Assumptions (unattended; recorded instead of asking)
- A1 "Only the order is wrong" = `tasks reorder` succeeds (no cycle, every dependency an existing
  ID, `none` or IDs only) and every task whose index changes is TODO. A queue that would move a
  DONE, IN_PROGRESS or BLOCKED task stops as today.
- A2 "Once per kind per task": the ruling claim key is the moved task ID (queue order: one claim
  per moved task), the task ID (sections), `<review digest 12>.<finding ID>` (disposition cell) and
  the active task or `final` (flow line). A repeat claim fails and the run stops as today. Without
  a run manifest (standalone `ai-run`, a hand-run triage) the claim fails and nothing changes,
  except the existing uncapped repairs after planning and plan-revision sessions, which stay as
  they are and only gain ruling rows.
- A3 Recovery: `ai-recover` keeps escalating `Task queue is invalid`; the pre-flight runs on every
  pipeline start (resumes included), so the stop only remains for unfixable queues.
- A4 The pipeline-start reorder makes an existing plan review stale (the queue changed), so the
  plan is reviewed again; this only happens when the committed order was wrong.
- A5 Overlap report: paths are the comma- or whitespace-separated tokens of `### Likely affected
  modules` that contain `/` or a `.`; pairs of TODO tasks only, earlier task first; printed and
  written to `.ai/local/preflight.md` (ignored); a run-log row only together with a ruling commit
  (no commit just for a report). It never stops a run.
- A6 Flow-line ruling: the first non-empty line of the section; when it starts with neither
  phrase, the host inserts `Flow unchanged (host ruling)` when the section text matches
  `unchanged` or `no flow change` (case-insensitive), else `Flow chart updated (host ruling; see
  below)`; blank lines between the heading and that line are removed. A missing section is left
  alone (it is optional in installed projects).
- A7 Attempt number = 1 + earlier outcome rows of this project, branch and task whose result is
  not `done` (limit pauses inside an attempt add no row). From attempt 3 the model is one tier up
  from the task's `Model:` (else the run's `--model`/`AI_MODEL`): haiku → sonnet, sonnet → opus;
  opus and fable stay; no model known → opus. One tier only, however many attempts. Session
  budget, `AI_RECOVER_MAX`, `timeout-rerun` and `gate-unblock` are unchanged.
- A8 Failure note (context, not authority; at most 600 characters, no `|`): the last failed
  attempt's result, seconds and model from the outcome log; failing check names (at most 5,
  unittest `FAIL:`/`ERROR:`, pytest `FAILED`, else the last non-empty line) from the validation
  log named by `.ai/local/validation.json`, read without following symlinks; the last non-empty
  line of the task's `### Result / notes`.
- A9 "Final code review" = the full-branch review once all tasks are DONE (round 1, as in "PR
  #34's final review"). Codex also reviews: plans, re-checks, and every fix-round re-review unless
  it is small and low-risk. Small = at most `AI_REVIEW_SMALL_LINES` (default 200) changed lines
  outside `.ai/` since the last host-recorded code review. Low-risk = no changed path matches the
  risk globs, no changed diff line matches the risk words, and no task DONE since that review runs
  on opus. Defaults: paths `*migration*`, `*.sql`, `supabase/*`, `*auth*`, `*polic*`, `*rls*`,
  `*security*`, `*payment*`, `*billing*`, `.github/*`, `.claude/*`, `.ai/permissions.allow`,
  `scripts/lib/common.sh`, `scripts/ai-check`; words `auth`, `RLS`, `row level`, `polic(y|ies)`,
  `grant`, `revoke`, `security definer`, `migrat`, `payment`, `billing`, `invoice`, `money`,
  `price`, `lock`, `mutex`, `concurren`, `race`, `transaction`, `deadlock`, `secret`, `token`,
  `password`, `crypt`, `permission`. `AI_REVIEW_RISK_PATHS`/`AI_REVIEW_RISK_WORDS` add to the
  defaults (space-separated); `AI_REVIEW_ROUTE=codex` turns routing off. Routing applies only to
  `AI_REVIEWER=auto`.
- A10 Routing reads host records only: a re-review is routable only when the host fix-round
  record for the base is at least 1 and the outcome log has a Codex code review of this branch
  whose HEAD is an ancestor of HEAD; the diff is measured from the newest host-recorded code review
  HEAD (any reviewer) that is an ancestor of HEAD. Anything missing or unreadable → Codex.
- A11 Codex limit memory: a host record (state root `codex-limit.json`) written when a Codex call
  reports a limit with a known reset; while `reset > now` an `auto` review skips Codex and runs the
  Claude fallback as today (catch-up entry, `↪` notification). Unknown reset (0) → no record
  (today's behaviour). `AI_REVIEWER=codex` ignores the record (it pauses as today).
- A12 A routed Claude review uses the existing `claude-review.md` prompt, opus (`claude_model`
  normal risk), effort high; it is labelled `Claude (routed: REASON)`, written to the outcome log as
  reviewer `claude-routed`, and gets no fallback-log entry (Codex reviewed the branch in round 1).
- A13 FL-33: each test module sets `AI_STATE_DIR` and `XDG_STATE_HOME` to its own temp directory
  at import (removed at exit), so subprocesses that start from `os.environ` are isolated too; the
  guard compares only entries that point under the suite's temp directory, because real pipelines
  (including the one running this gate) may register during the suite.

## Acceptance criteria (observable)
- AC1 `tasks preflight` on the raid-f4 shape (T001–T006, T004 depending on T005 and T006, all
  TODO) reorders to T001 T002 T003 T005 T006 T004 (stable), prints `Ruling` lines naming T004, and
  `tasks check` then passes; a cycle, an unknown ID, prose, or a moved DONE task fails with the
  same message as today and leaves the file unchanged; the overlap report names a pair sharing a
  path (`test_preflight_*`).
- AC2 `run-manifest ruling KIND KEY` succeeds once and fails the second time with the manifest
  bytes unchanged; kept by `clear-attempts`, dropped by `start`; a wrong shape invalidates the
  manifest; the ruling row has no `|` (`test_ruling_manifest_*`).
- AC3 A pipeline started on a committed raid-f4 queue commits `chore(ai): ruling: task queue`
  with a run-log `Ruling (queue-order)` row, reviews the plan and completes; a second start in the
  same run that needs the same ruling stops as today; after triage an out-of-order fix task is
  reordered (`test_preflight_pipeline_*`).
- AC4 Disposition rows `| **M1** | accepted | … |` and `| M1 (CRITICAL) | … |` are rewritten to
  `| M1 |` with a ruling row and triage completes; a cell with two IDs or an ID not in the review is
  not rewritten and stops as today; the same for a plan revision row (`test_ruling_disposition_*`).
- AC5 A handoff whose `## Flow chart` has a blank line and `Flow chart: updated X` gets `Flow chart
  updated (host ruling; see below)` right after the heading before the host gate, with a ruling
  row; `no flow change` text gets `Flow unchanged (host ruling)`; a correct or missing section is
  untouched (`test_ruling_flow_line_*`).
- AC6 `attempt-info` gives attempt 1 with no note on a fresh task, attempt 2 with the note of a
  `timeout` row, and from attempt 3 sonnet for a haiku task, opus for sonnet, opus unchanged; the
  runner's third session of a twice-failed sonnet task runs with `--model opus`, its prompt holds
  the note, and the run log names attempt and model (`test_attempt_info_*`, `test_fresh_retry_*`).
- AC7 `review-route` returns codex for plan, recheck, the first code review, a large or risky
  fix-round diff, an opus fix task, missing host records or `AI_REVIEW_ROUTE=codex`, and claude for
  a small low-risk fix round (`test_review_route_*`).
- AC8 With a recorded active Codex limit an auto review makes no Codex call and runs the Claude
  fallback; after the reset it calls Codex again; a routed review makes no Codex call, is labelled
  routed and adds no fallback-log row (`test_review_routing_*`, `test_codex_limit_*`).
- AC9 Every published review has a `Reviewed by:` line; the PR body lists the reviewer of each
  round including the route reason (`test_reviewed_by_*`).
- AC10 After a full self-check the real registry has no entry under the suite's temp directory,
  and the runner fails when one appears (`test_state_isolation_*`).
- AC11 `.ai/bin/ai-check` passes; README, docs/workflow.md, the vault flow chart and the handoff
  match the code.
