# Spec: Flow batch 4: self-check process ownership (FL-27), record-format tolerance (FL-25), scratch files (FL-26), recovery answer with prose (FL-12), catch-up coverage (CU-2)

## Objective
Stop the overnight stops that come from record formatting and session hygiene rather than from
real problems, and make the toolkit's own self-check clean up every process it starts. Source:
vault `agents-backlog.md` (FL-27, FL-25, FL-26, FL-12, FL-21, CU-1..CU-4). Branch
`fix/flow-batch-4`, created from `origin/master` at 7d22939 (after PRs #27 and #28 merged).
Planned by Claude on 2026-10-16. Unattended planning: assumptions are recorded below and in
`.ai/current-plan.md` instead of being asked. Out of scope by instruction: MC-01, DB-04 (need
Zack's design decisions) and the FL-23/T006 profiling follow-up.
Hub decisions respected: AD-4 (small files in `.ai/local/`, no daemon), AD-5 (status never
authorizes), gate files are never edited by a pipeline session.

## Verified against the code (2026-10-16, 7d22939)
- **FL-27 open.** `tests/run_parallel.py` starts each batch with `start_new_session=True` and
  `stop()` (~256–272) signals only each batch's process group (`signal_group`, ~160). GNU
  `timeout`, used by every fixture pipeline (`scripts/ai-run` ~265, `scripts/ai-review`,
  `scripts/ai-recover` ~186), calls `setpgid` and so runs itself and its child in a new group:
  both survive a worker failure, an interrupt or SIGTERM. PR #28's final review M3
  (`.ai/reviews/current.md`) reproduced it with `timeout 120 sleep 120`; `drain()` (~221) only
  bounds the wait (`DRAIN_GRACE`), it kills nothing outside the group.
- **FL-25 (a) open.** `tasks()` (`scripts/lib/workflow.py` ~425–462) requires `### Likely
  affected modules` and `### Result / notes` in every task. After a triage session `ai-run`
  runs a bare `ai_helper tasks check` (~519) and stops; after planning (~331) and plan revision
  (~434) the host reorders, then `tasks check` stops. Nothing adds the two content-free
  sections. The TRIAGE CONTRACT (~507) and `templates/.ai/prompts/triage.md` never show the
  task format.
- **FL-25 (b) open.** `DISPOSITION_ROW` (~911) and `PLAN_DISPOSITION_ROW` (~2329) read cells
  with `(.*?)\s*\|`, so an escaped `\|` ends a cell (raid polish P11: the Task column read
  `--no\`). Every reader of either table uses these two regexes (triage-check ~951,
  review_rounds ~1027, rejected rows ~1470, disputes ~1625, plan history ~2367,
  plan-dispositions-check ~2508, PR body ~3242). The host's own writers already escape `|`
  as `\|` (~1563, ~2831).
- **FL-26 open.** No template prompt says where scratch files go; `rm` is not on the
  allowlist (`templates/.ai/permissions.allow`, deliberately: Bash rules are prefix matches and
  cannot restrict a path). A throwaway test file in `src/` then fails the gate and the session
  ends without a checkpoint. `.ai/local/` is git-ignored by `setup-project` (workflow.py ~319).
- **FL-12 open.** `recover_decision` (workflow.py ~1886–1916) accepts only a text that is
  exactly one JSON object (optionally fenced); prose before it escalates with "gave no valid
  decision" and the session's diagnosis is lost. `test_recovery_decision_parsing_is_strict`
  (tests/test_workflow.py ~4156) pins `Decision: {…}` → escalate.
- **FL-21 already done.** `scripts/lib/watchdog.py` `STALL_CONFIRM_NS` (~24–26, ~443–451): a
  stall must hold 5 minutes after its first sighting, with the install-time probe named in the
  comment; tests `test_watchdog_confirm_*` (~744–836). Dropped.
- **CU-4 already done.** `Dispatcher.env()` (~189–200) drops `FORCE_COLOR` and sets
  `NO_COLOR=1`, `PYTHON_COLORS=0`; `summary()` strips ANSI codes; tests
  `test_parallel_runner_passes_with_caller_colour_settings` and siblings (~8637–8668). Dropped.
- **CU-1 already done.** `outcomes_report` "Attempts by model" (~2997–3013) credits each attempt
  to its own model; `test_outcome_report_credits_each_attempt_to_its_model` (~5175). Dropped.
- **CU-3 already done.** A re-check outcome carries `upheld_blocker`, `upheld_major`,
  `withdrawn_blocker`, `withdrawn_major` (~2942–2951) and the report sums them ("Re-checks by
  reviewer", ~3036–3049). Dropped.
- **CU-2 open.** "Claude-only reviews (Codex catch-up pending)" (~3050–3055) lists every Claude
  review forever; there is no record that a Codex review covered it.

## Requirements
- **FL-27 the self-check owns its process tree.**
  - On Linux, `run_parallel.py` makes itself a child subreaper (`prctl(PR_SET_CHILD_SUBREAPER)`
    via `ctypes`), so every descendant of every batch stays its descendant even after its
    parent exits or it changes process group or session. Adopted orphans that exit are reaped
    during the run (no zombie build-up), without ever reaping a batch process (exit codes and
    summaries stay exactly as today).
  - On a worker failure, an interrupt (SIGINT) or SIGTERM, every descendant process is
    terminated (SIGTERM, grace, SIGKILL; identity checked by `/proc` start time before SIGKILL)
    before `run()` returns or re-raises, including GNU `timeout` and its child; a bounded
    final wait confirms each is gone or a zombie, and survivors after it are named on stderr
    with a non-zero exit. One `stop()` caller owns termination, and no adopted zombie is
    reaped while it runs. Elsewhere
    (no `prctl`, not Linux) the behaviour stays as today.
  - The flag is set only by the runner's `main()`, never in a process that imports the module.
- **FL-25 record formats.**
  - (a) After a triage, planning or plan-revision session, the host adds a missing
    `### Likely affected modules` (body `(not listed)`) and a missing empty `### Result / notes`
    to TODO tasks only, at their canonical position; any other missing section still stops
    the run as today. Nothing is written when nothing is missing. DONE, IN_PROGRESS and
    BLOCKED blocks are never touched.
  - (b) Disposition and plan-disposition rows accept `\|` inside a cell (it is part of the
    cell, read back as `|`, and never split into a cell ending in `\`); an unescaped `|`
    still splits a row, and a row whose Task cell is missing stays malformed.
  - The template prompts (triage, plan, plan revision) and the host contracts show the exact
    task format and say how to write a pipe in a table cell.
- **FL-26 scratch files.** Template prompts tell sessions to put throwaway files only under
  `.ai/local/scratch/` (ignored by Git, never named like a test file) and never in source or
  test directories. `ai-run` empties `.ai/local/scratch` before and after every Claude
  session through directory descriptors pinned without following symlinks (a symlink at
  `scratch` is removed, not followed; a symlinked `.ai/local` or `.ai` means a warning and no
  delete; the clear after a session runs only once the gate digest is verified; a failure is
  reported and never stops the run). The permission template is unchanged (no `rm`).
- **FL-12 recovery answer with prose.** `recover-decision` accepts a result whose text holds
  prose around exactly one decision object (a JSON object that starts at a line start, ends its
  line, sits in no unclosed `{`/`[`, and whose `action` is one of the three actions and whose
  fields are valid). Zero or several such objects, a duplicate key anywhere in a candidate
  object, a malformed line-start object, a whole-text JSON value that is not an object, or a
  failed envelope escalate as today; objects inline in prose or nested in another value are
  never decisions. When it escalates for want of a decision, the reason carries a
  short, cleaned excerpt of what the session wrote. The recover prompt template asks for the
  JSON object alone, with the diagnosis inside `reason`.
- **CU-2 catch-up coverage.** `ai-status --outcomes` lists under "Codex catch-up pending" only
  Claude reviews that no later Codex review of the same project and branch (same family:
  plan covers plan; code covers code and re-check) and no explicit catch-up record covers. A
  human command `ai-status --catch-up-done BRANCH...` appends a `catchup` outcome per branch
  (covers that project+branch's Claude reviews up to that time; with equal timestamps only
  records earlier in the same log file). The report says how many
  Claude reviews are covered.
- **Docs.** README and `docs/workflow.md` describe each change; every flow change updates the
  vault flow chart (`agents-flow.md`, `updated:`) and appends a dated hub Log line in the same
  task; sessions never tick vault checkboxes.

## Non-goals
No change to `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/ci-setup`, `.ai/permissions.allow`,
`.claude/settings.json` or `.github/workflows/*` (human steps in the handoff). No `rm` or
`git clean` on the allowlist. No cgroups. No structured-output (`--json-schema`) flag for the
recovery session. No repair of content sections (Goal, Implementation notes, Acceptance
criteria, Validation). FL-16 (severity suffix in plan-disposition IDs), MC-01, DB-04 and the
FL-23 profiling follow-up stay in the backlog.

## Acceptance
- Offline regression tests per task (names in `.ai/tasks.md`), in the existing styles;
  existing tests pass (tests changed on purpose are named in the task results).
- `.ai/validate` passes (it runs the changed `tests/run_parallel.py` itself).
- README, `docs/workflow.md` and the vault flow chart match the code.
