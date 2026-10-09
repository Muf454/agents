# Plan: Pipeline dashboard (`ai-dashboard`)

## Revision 11 (plan review 10 by the Claude fallback reviewer, 2026-10-09)
P39 (MAJOR) and P40–P45 (MINOR) all accepted (`.ai/reviews/plan-dispositions.md`, round 10).
Design, scope, AD-4, AD-5 and the T010 guard design unchanged (the review traced the guard on
every stop path and found it holding); changes are precision in the task records:
1. **T005's gate test was impossible (P39).** ai-recover runs the checkout helper from
   `ai_root` (~29, `workflow.py paths`) through `reserve-attempt` (~67) before it compares the
   gate with the manifest (~97–99), so a sentinel planted in `workflow.py` fires at line 29 and
   the escalation message changes. The test now changes `.ai/validate` exactly like the
   existing fixture and asserts what the flag actually guarantees: no `stopped` record after
   the `recovering` one, no `notifications.log` line for the ⛔ the mock still receives. The
   flag mechanics stay in T010's unit tests. T010 states the pre-comparison window
   (ai-recover ~29–77, ai-pipeline ~120–129) as today's behaviour, not a new exposure.
2. **Guard precision (P40–P42).** The watchdog needs no guard and the "known limit" was
   wrong: it notifies through its own copy of common.sh (`with_name('common.sh')`,
   watchdog.py ~478) and `start_recovery` verifies the gate digest with its own copy before
   launching the checkout's ai-recover; T010, T009, the spec and the Risks below say so.
   ai-pipeline's two pre-step gate stops (~125 unreadable digest, ~129–130 resume mismatch)
   also set `AI_GATE_BROKEN`, since the marker is already set and T003's `ai_die` record
   would follow; T003's resume test asserts the record stays byte-identical. `gate_ok` is
   written out as `local gate_ok=no; if ai_gate_check …; then gate_ok=yes; fi`, never a
   command substitution (which would set the flag in a subshell only); T010 tests the form.
3. **Record details (P43–P45).** `observe done` always sets `stage=pr` (the `--no-pr` and
   no-origin finishes come before `step 'Pull request'`); T001 and T003 test it. A `needs_you`
   run whose record is not `stopped` (a `last-error` newer than an active record, the trace a
   gate-broken stop leaves) renders the recorded box in style `stopped` with the sanitised
   `last-error` line on the marker line (T008 rule, golden and snapshot cases). Task counts
   come from a new `tasks counts` helper (`<done> <total>`, T001) read by ai-run (T004), the
   same rule the snapshot applies in-process (T007); no existing `tasks` action prints bare
   counts.

## Revision 10 (plan review 9 by the Claude fallback reviewer, 2026-10-09)
P32–P38 all accepted (`.ai/reviews/plan-dispositions.md`, round 9). Design, scope, AD-4 and
AD-5 unchanged; changes:
1. **Gate-broken guard (P32, security; new opus task T010 between T001 and T002).** The
   toolkit rule "never run a project helper after the approved gate changed" (ai-run ~109,
   common.sh ~114) would be broken by T002/T003: `ai_guard_verify` → `ai_die` → `ai_notify` →
   `workflow.py notify-log` and `ai_observe stop` would execute the checkout's
   `.ai/bin/lib/workflow.py`, the very file the tampering changed; three existing gate tests
   (`UNTRUSTED_HELPER_RAN` sentinel) already assert this never happens. Design: one shell flag
   `AI_GATE_BROKEN` set by `ai_gate_check GATE` (common.sh), by `ai_guard_verify`, by
   `ai_deps`, by ai-run's `on_exit`, by ai-pipeline's `stop()` and by ai-recover's gate
   escalations; `ai_observe` and `ai_notify_log` skip the helper while it is set. The ⛔
   notification (`AI_NOTIFY_CMD`, user code) is still sent. The flag approach matches the
   existing design (every helper call after a session already follows an `ai_guard_verify`)
   and costs no extra digest per record. T002 stays sonnet: the guard is written out in T010.
2. **Deterministic discovery (P33).** `/proc` discovery gets an injectable process source
   (`ProcSource(root)`, `AI_DASHBOARD_PROC` → fixture tree of fake `<pid>/{stat,cmdline,cwd}`)
   and a root filter (`AI_DASHBOARD_ROOT`); the parallel gate runs real fixture pipelines in
   other temp checkouts (`tests/run_parallel.py` shards), and Zack's machine runs real ones,
   so every dashboard test sets both. Test-only variables, documented as such (T009).
3. **Build after the post-task gate (P34).** ai-run records `step build "<id> · checkpointed
   · <done>/<total>"` right after a passing post-task `ai-check`, so a stop between two tasks
   (the common `Session limit reached`, the loop-head gate/branch/queue checks, checkpoint
   stops) shows on Build, not on a Checks box whose gate passed; after the passing final gate
   the Checks detail becomes `final · passed`. T004 carries a stop-site table for the loop.
4. MINOR, all taken: `ai_die` records a stop only when `AI_STOP_NOTIFIED` is empty (P35, one
   record per stop); `read_record(…, tail=True)` for the notification log (P36); `--json`
   field `state_root` and the empty state name the state root, README says to run the
   dashboard with the pipelines' `AI_STATE_DIR`/XDG settings (P37); `observe` records `pid` as
   the caller's PID (`os.getppid()`) and `branch` via `git_branch` (P38).

## Revision 9 (rebase on master e9354d9, 2026-10-09)
Zack reviewed revision 9 with the mockups (2026-10-09) and decided: keep the 120-column box
layout; compact line shows a stopped stage as `✗<label>` (red) and paused/recovering/crashed as
`▶<label>` + ⏸/🔧/⚠; `needs_you` runs are never hidden by the 24 h filter; no actions in the
dashboard; plan and code review by Claude now (Codex catch-up later).
Master gained the efficiency batch (#18), FL-04 bounded supervisor (#21), the robustness batch
(#22, FL-14/15/16/17), toolkit upgrade 4 (#23) and the outcome follow-ups (#24) since revision 8
(master 0818f20). Design, scope, AD-4 and AD-5 are unchanged; changes:
1. Code references re-verified against the current scripts and corrected (Assessment below):
   every line number moved; `state_root()`/`check_state_root()` are at workflow.py ~1016/~1038
   (were ~782); the setup list (~303) is also what `setup-project --upgrade` installs, so the
   install test covers `--upgrade` too; `ai_notify` returns early when `AI_NOTIFY_CMD` is unset
   (T002 must restructure it, not append after it); ai-run's checks are at ~441 (final) and
   ~478 (post-task), `ai_deps` is called once before the task loop (~426); ai-recover's
   leftover validation is `commit_and_rerun` (~193 `ai_deps`, ~196 `ai-check`); the watchdog
   notifies at watchdog.py ~478.
2. New flow box **Plan revision** (key `plan_revision`, Claude orange; Zack 2026-10-09) between
   Plan check and Setup: written by ai-pipeline's revision step and the "Completing the
   interrupted plan revision" step, by `ai-run --revise-plan` outside a pipeline; new stop label
   `plan revision` → `plan_revision`; `plan review` now covers {plan_review, plan_revision} so
   a stop right after a revision stays on its box.
3. Stored needs-human plan decision: ai-pipeline's `plan_decision_check` and ai-recover's
   decision branch record the Plan revision box (detail `needs your decision`) before stopping;
   the dashboard shows `needs_you` with the decision's reason (observation note) on the marker
   line.
4. Base-moved early stop (FL-17, `stop start` at ai-pipeline ~382, ai-recover hard rule ~122):
   new label `start` → stage `none`; rendered as "⛔ stopped before Plan check" with no box
   highlighted. A human (re)start records a new `start` action (stage `none`, state active) right
   after the marker, so an earlier run's stopped/done record never colours the new run; a
   recovery resume keeps the recovering record.
5. Supervised extra fix round: Triage detail `round <n> · extra (<x → y → z>)` (or `· extra`
   when resumed); review format retry: new `observe detail STAGE TEXT` action (detail only,
   only when STAGE is the recorded stage), written by ai-review after its 🔁 notification.
   Inside a pipeline, `ai-run --triage`/`--revise-plan` no longer overwrite the pipeline's
   stage record (they would erase the round/extra detail); standalone they record it.
6. Stop-label normalisation completed from the code: `push` (ai-pipeline ~569) was missing;
   `start`, `plan revision` added; ai-recover's `--stage` text (including the watchdog's `crash
   (pipeline killed or restarted)`) is never normalised (recovery passes an empty label or an
   explicit box key).
7. 8 boxes. 100 columns no longer fit the box row (worst case 112 columns incl. card indent and
   an overlay, see T008), so the box layout starts at **120** columns; goldens at 140 and 120
   (boxes), 119 and 60 (compact line).
8. Removed the obsolete "concurrent work: efficiency batch" note and the "Sequencing" section
   (both merged); gate note: `.ai/validate` runs `tests/run_parallel.py`, ~4 min, inside the
   600 s tool limit; timing bounds in new tests stay generous because shards run in parallel.
9. Tasks: old T004 split into T004 (ai-run, `ai_deps`, ai-review) and T005 (ai-recover) to keep
   the sonnet tasks small; old T005–T008 are now T006–T009 (liveness, snapshot, TUI, docs).
   Review history notes in tasks.md keep the old IDs.

## Assessment (master e9354d9)
- No record says which stage a run is in: `ai-pipeline`'s `step()` (~158) only prints
  `== title ==`; `stop()` (~143) notifies or execs `ai-recover --stage LABEL`; `finish()` (~85)
  drops the marker. `.ai/state.md` has Phase/Current task only.
- Stop labels in ai-pipeline: `start` (base moved, ~382), `plan review`, `plan revision`,
  `implementation`, `validation` (`ensure_validated` ~229), `review`, `triage`, `re-check`,
  `pull request preparation`, `push`, `pull request`, `final push`. The pipeline-shell `ai_die`
  (common.sh ~11) is the remaining stop path. ai-recover uses `escalate` (~37), `resume` (~49,
  `exec env … ai-pipeline`) and `on_exit` (~79).
- FL-04: plan loop ~406–469 (step "Plan revision r/max, review round n" ~461), interrupted
  revision ~363, `plan_decision_check` ~388 (stop `plan review` with the stored questions),
  extra fix round ~509–532 (🔁 notification ~524), triage step ~533. ai-run `--revise-plan`
  ~223, `--triage` ~350. ai-review format retry ~225–245 (🔁 notification ~235).
  ai-recover decision branch ~103–119, base-moved hard rule ~121–126, stage resume ~139–153.
- Notifications go out through `ai_notify` (common.sh ~79) only; the watchdog calls it via
  `bash -c 'source common.sh; …'` (watchdog.py ~478). `ai_limit_pause` common.sh ~89;
  `ai_deps` ~167 (stale boundary after ~173).
- Liveness: `.ai/local/pipeline.active` (ai-pipeline ~83, ai-recover ~92); `process()` ~74,
  `is_runner()` ~85, `start_ns()` ~65, `marker_snapshot()` ~90, `pipeline_died()` ~99,
  `runners()` ~331 in watchdog.py.
- Host state root: `state_root()`/`check_state_root()` (workflow.py ~1016/~1038), per-checkout
  keys as in `binding_dir()` (~1058). Nothing lists all checkouts that ran a pipeline.
  Installed scripts: `setup` list (~303), shared with `--upgrade` (~306).
- Gate: `.ai/validate` runs shell syntax checks, then `tests/run_parallel.py` (~4 min).

## Approach (revised after plan reviews 1–10, P1–P45; all accepted; revisions 9–11 above)
1. T001 (opus) safe record writers in workflow.py: `observe` (schema, overlays, `start`,
   `detail`, stop-label normalisation, path safety, caller pid/branch, `done` → `pr`),
   `notify-log` (flock + O_NOFOLLOW + trim), `pipeline-register` (flock, race-safe prune),
   `tasks counts`, plus the shared safe I/O (pinned directory descriptors, nonblocking
   regular-file opens, bounded head/tail reads returning stat, Git metadata incl. worktrees,
   bounded locks) the dashboard reuses. Concurrency and path safety → opus.
1b. T010 (opus) gate-broken guard: `ai_gate_check`, `AI_GATE_BROKEN`, guarded `ai_observe` and
   `ai_notify_log`; ai-run/ai-pipeline (incl. its two pre-step gate stops)/ai-recover gate
   comparisons set the flag without a command substitution (P32, P41, P42).
2. T002 (sonnet) notification mirror + pause overlay (common.sh); vault note.
3. T003 (sonnet) ai-pipeline stage records incl. plan revision, decision, extra round, start
   and base-moved stop, finish, registration; vault note extended.
4. T004 (sonnet) ai-run (build, checks, build again after the post-task gate, standalone
   triage/revision), Setup in `ai_deps`, ai-review format retry detail.
5. T005 (sonnet) ai-recover records (recovering, recovery checks, decision, escalation,
   unexpected exit).
6. T006 (opus) discovery and liveness (registry + injectable process source with root filter,
   marker/process identity on bounded descriptor reads) and terminal sanitising.
7. T007 (sonnet) snapshot model, status rules, `--once`/`--json` (with `state_root`), wrapper,
   setup/upgrade install.
8. T008 (sonnet) curses TUI and the shared renderer (8 boxes, 120-column threshold).
9. T009 (haiku) docs and final audit.

Dependencies: linear, T001 → T010 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009.

## API / data changes
- New files (ignored, host-written): `.ai/local/observation.json`,
  `.ai/local/notifications.log`; host `<state root>/pipelines/<key>.json`.
- New helper: `workflow.py observe|notify-log|pipeline-register`, new action `tasks counts`.
  New scripts: `ai-dashboard`, `lib/dashboard.py`. New common.sh functions: `ai_gate_check`,
  `ai_observe`, `ai_notify_log`; shell flag `AI_GATE_BROKEN` (never exported, never set in a
  command substitution). Test-only environment: `AI_DASHBOARD_PROC`, `AI_DASHBOARD_ROOT`.

## Risks
- `.ai/local/` is agent-writable: a session can forge an observation or a notification
  line. The dashboard is advisory only (AD-5): it shows, never acts; strings are sanitised
  so a forged line cannot inject terminal escapes. Accepted and documented.
- Concurrent writers (pipeline and watchdog have separate locks): the notification log and
  the registry serialise their own writes with dedicated flock files; readers stay lock-free.
- `/proc` scan sees only this user's processes in practice; fine for a single-user machine.
  In tests it would also see other shards' fixture pipelines and Zack's live runs, so every
  dashboard test pins the process source and the root filter (P33).
- A stop caused by a changed gate records nothing (the helpers are project code): the
  dashboard then shows `needs_you` from the newer `last-error` and draws the last recorded
  stage's box as stopped with that line (P32, P44). ai-recover and ai-pipeline still run the
  checkout helper before they compare the gate with the manifest (ai-recover ~29–77,
  ai-pipeline ~120–129), as today; the watchdog notifies through its own installed copy and
  verifies the digest before launching recovery, so it needs no guard (P40).
- The pipeline running this batch uses the frozen `.ai/bin`; the new records appear in a
  project after its `.ai/bin` is upgraded. Older runs still show via `/proc` (stage unknown).
- New timing-bounded tests (5–15 s) run inside parallel shards: bounds stay generous and
  assert "returns", never a tight duration.

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; the parallel gate takes ~4 min;
see the gate note in tasks.md for a timeout).
