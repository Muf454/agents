# Plan: Night-stop fixes (FL-18, FL-19, FL-21, FL-22) and a Plan stage (DB-04)

## Assessment (verified at 744827a, 2026-10-09)
Every backlog item was checked against the code; none is fixed by FL-04 (#21) or DB-01 (#25).
Details and line references are in `.ai/project-spec.md` → "Verified against the code". Two
corrections to the backlog wording: FL-18 no longer prints the Plan review header (FL-04 moved
it into the loop), the review is still skipped silently; FL-21's immediate probe comes from
systemd (`OnBootSec=2min` already elapsed when the timer is started), not from
`--install-timer` itself. FL-19's lock collision also overwrote `last-error` with "Another
runner/reviewer owns this checkout", a second defect fixed with it.

## Architecture
Small, local changes in the existing scripts; no new runtime dependency, no new process.
1. **Queue check (T001).** `ai-task check` → `workflow.py tasks check` (existing, read-only)
   plus a one-line summary from `tasks counts`. ai-pipeline validates the queue before its
   `tasks untouched` gate (the gate stays: a queue with a DONE task skips the review as
   today). New hard-escalate pattern in ai-recover: `*'Task queue is invalid'*`.
2. **Session budget (T002).** Default `sessions` empty; after the triage/revise-plan
   branches (which never use it) and before the dependency step, `tasks counts` →
   `max(16, total - done + 2)`; `--sessions` wins.
3. **Lock owner message (T003, opus).** In `ai_lock`'s non-quiet rejection: no `ai_die`
   (it writes `last-error`); print and `exit 1`. Owner detection reads the marker only when
   it is a regular, non-symlink file (no FIFO block), parses a PID, reads
   `/proc/PID/cmdline` and matches the runner name like the dashboard's `is_runner`
   (argv[0] basename, or bash/sh + first non-option argument).
4. **Watchdog confirmation (T004, opus).** Timer `OnActiveSec=2min` + `OnUnitActiveSec=10min`.
   `watchdog.json` gains optional int `stall_seen_ns`; the `stalled` incident needs a prior
   sighting ≥ 5 min old. Observation stage `planning` (bounded `read_record` of
   `.ai/local/observation.json`) suppresses `stalled`. Old `watchdog.json` files stay valid.
5. **chmod +x (T005, opus).** Template allowlist line `Bash(chmod +x *)` and runner prompt
   template line. Claude Code's Bash rules are prefix matches and cannot restrict the path
   to the checkout; the prompt rule plus "only `+x`" keeps it narrow, and the allowlist was
   never a sandbox (`.ai/bin/ai-check` already runs project code). `git update-index
   --chmod=+x` was rejected: it leaves the working-tree mode at 644, which is what failed.
6. **Plan stage (T006–T009).**
   - **Why `ai-run --plan` and not a new `scripts/ai-plan`:** this run's frozen runner
     allowlist (this repo's `.ai/permissions.allow`) cannot `chmod +x` a new script until
     FL-22 reaches this repo's gate (a human step), so a new executable would block exactly
     like DB-01 T007. As a mode of the installed `ai-run` (beside `--triage` and
     `--revise-plan`) it reuses `claude_session` (limit pauses, timeouts, session logs,
     post-session gate verify), `ai_lock`, the protected-branch check and the exit handler
     (⛔ notification, `last-error`), needs no setup change (ai-run is installed and
     upgraded already) and is discovered by the dashboard and watchdog as a runner
     (`ai-run`). The backlog entry allows either form.
   - Records (T006, workflow.py): box key `planning` (first), stop label `plan`, action
     `planned NOTE`; `plan-allowlist` (like `plan-revision-allowlist`, plus `Write`) and
     `plan-scope START` (`records_scope` with the six editable records + `.ai/run-log.md`).
   - Command (T007, ai-run). Flow:

     ```mermaid
     flowchart LR
       A[ai-run --plan P] --> B{lock, branch, scope}
       B -- fail --> X[⛔ stop: planning]
       B --> C[register + observe planning + 📝 notify]
       C --> D[Claude session: Read/Glob/Grep + Edit/Write of 6 plan records]
       D --> E{gate same, plan-scope, tasks check}
       E -- fail --> X
       E --> F[observe planned + 📝 Plan ready]
       F --> G[human/mission control commits, starts ai-pipeline]
       G --> H[pipeline start record: Plan ✓]
     ```
     Plan mode's session timeout defaults to 3600 s (`--session-timeout` wins). After the
     session the host also runs `workflow.py plan-keeps-done START` (T011, plan review
     round 1 P1): every task DONE at START must keep its identical block. The comparison is
     on the raw text of the block (heading to the line before the next `## ` outside a
     fence, fenced lines included, trailing blank lines ignored), not on the parsed `lines`
     of `task_blocks`, which drop fenced content (rounds 2–3, P9/P13: one rule for the whole
     block instead of per-symptom exceptions); also run on HEAD before the session to
     validate the START queue. The check is unconditional (a template queue has no DONE
     tasks, so a first plan passes), so the "keep DONE tasks" contract is enforced, not
     prompt-only.
   - Dashboard (T008): `FLOW` gains `('planning', 'Plan', 'Plan', 'claude')` first; Plan
     check's compact label becomes `PlanCheck`; `BOX_OF['recheck']` computed from Triage's
     index; joiners `─` (one column). Worst case at 120 columns: labels 4 + 10 + 13 + 5 + 11
     + 6 + 6 + 8 + 2 = 65, + 4 per box × 9 = 101, + overlay 3 = 104, + 8 joiners × 1 = 112,
     + indent 2 = 114 ≤ 120 (two-column joiners would need 122). `position()`: stage `none`
     with an observation → Plan ✓ (index 0 passed); status `planned` for
     `(planning, done)`, ranked after the live runs and before `finished`, hidden after
     24 h like finished/idle.
   - Docs (T009).

## Phases / tasks
T001 (FL-18, sonnet) → T002 (FL-19 budget, sonnet) → T003 (FL-19 lock, opus) → T004 (FL-21,
opus) → T005 (FL-22, sonnet) → T006 (plan records, sonnet) → T007 (`ai-run --plan`, opus) →
T008 (dashboard Plan box, sonnet) → T009 (docs and audit, sonnet) → T010 (17-session budget
end to end under a dedicated `LONG_RUN_TIMEOUT` = 600 s × scale, sonnet) → T011
(`plan-keeps-done`, opus). T010/T011 come from plan review round 1 and document their own
one-line changes. Round 2 refined them in place: T010's bound (P2), T011's trailing-blank
comparison and pre-session START check (P9), T007's `sessions_given` flag so it does not
depend on T002 (P10), and T003's documented limit for a watchdog-started recovery (P11).
Round 3: T009 (the audit) now depends on T010 and T011 too, so `tasks next` runs it last
although it sits before them in the file (P14); T005 names the existing permissions test it
must update (P12); T011's comparison is on raw block text (P13); T007's lock case asserts
only the stable message prefix (P15).
The ai-pipeline queue check runs whether or not the plan review is on (round 1 P7). The FL items are
independent (`Dependencies: none`) so one blocked item never stops the others; DB-04 comes
after them in queue order, and T007 depends on T001 (queue check) and T006.

## Risks
- Golden dashboard outputs, `test_watchdog_health_stall_recovery_and_checkout_scope` and
  `test_permissions_template_excludes_network_installs_and_writers` change on purpose (T008,
  T004, T005): each task updates them with the new expectation and says so in its result.
  The permissions test drops `chmod` from its forbidden programs and instead requires every
  `Bash(chmod` entry to be exactly `Bash(chmod +x *)` (round 3 P12). No other existing test
  is weakened.
- Stall confirmation delays the markerless "killed runner" notice by one timer period
  (~10 min). Accepted: the `died` rule (marker with a dead PID) is the real crash detector and
  stays immediate; FL-21 was a false alarm from exactly this rule.
- `Bash(chmod +x *)` also matches paths outside the checkout; mitigated by the prompt rule.
  Real Claude matching cannot be tested offline (human check).
- A planning session killed with SIGKILL leaves `planning/active` with no process: the
  dashboard shows it idle (not stopped). Accepted; ai-run's exit handler covers every other
  exit.
- Every change lands in `scripts/` and `templates/`; this run's frozen `.ai/bin` keeps the old
  behaviour, so the pipeline itself is unaffected.

## Validation strategy
Each task: its targeted `-k` tests, then `.ai/bin/ai-check` (parallel shards; see the gate
note in `.ai/tasks.md`). Tests are offline (mock claude/codex/gh/systemctl, fixture `/proc`
trees, `AI_WATCHDOG_NOW`).

## Assumptions (unattended run; recorded instead of asked)
- DB-04 is `ai-run --plan` (reason above); `--plan` does not need `--approved`.
- The planner allowlist is the six files Zack listed, incl. `.ai/reviews/dispositions.md`;
  no Bash, so headless planners get the queue check from the host, interactive ones run
  `.ai/bin/ai-task check`.
- Session default slack `+2` covers tasks a session appends; fix-round tasks are covered by
  recomputation per ai-run call.
- Stall confirmation: second sighting ≥ 5 minutes after the first (the timer probes every 10
  minutes).
- `planned` is a new dashboard status; the header counts stay running / needs you /
  finished.
- Human steps (gate files, vault, timers) are listed in `.ai/handoff.md`.
