# Plan: Pipeline dashboard (`ai-dashboard`)

## Assessment (master 0818f20, after PR #15)
- No record says which stage a run is in: `ai-pipeline`'s `step()` (scripts/ai-pipeline
  ~132) only prints `== title ==`; `.ai/state.md` has Phase/Current task only.
- Notifications go out through `ai_notify` (scripts/lib/common.sh) and nowhere else; the
  watchdog calls the same function via bash (scripts/lib/watchdog.py ~463).
- Liveness: `.ai/local/pipeline.active` holds the pipeline PID (ai-pipeline ~71);
  `process()`/`is_runner()`/`runners()` in watchdog.py already read `/proc` safely.
- Host state root: `state_root()`/`check_state_root()` (workflow.py ~782); per-checkout keys
  as in `binding_dir()`. Nothing lists all checkouts that ran a pipeline.
- Concurrent work: `feature/efficiency-batch` (running) touches ai-review, ai-run --triage,
  workflow.py triage code and adds `tests/run_parallel.py`. Overlap with this batch is small
  (ai-run lines near the task loop); the second PR to merge resolves conflicts.
- Gate: the serial suite takes ~611 s (FL-11 in the efficiency batch speeds it up later).

## Approach (revised after Codex plan reviews 1–5, P1–P27; all accepted)
1. T001 (opus) safe record writers in workflow.py: `observe` (schema, overlays, stop-label
   normalisation, path safety), `notify-log` (flock + O_NOFOLLOW + trim), `pipeline-register`
   (flock, race-safe prune), plus the shared safe I/O (pinned directory descriptors,
   nonblocking regular-file opens, bounded reads returning stat, Git metadata incl.
   worktrees, bounded locks) the dashboard reuses.
   Concurrency and path safety → opus (P4–P6, P12–P14).
2. T002 (sonnet) notification mirror + pause overlay (common.sh); vault note.
3. T003 (sonnet) ai-pipeline stage records, stop/finish, registration; vault note extended.
4. T004 (sonnet) ai-run/ai-recover stage records (checks inside ai-run, P2; explicit
   recovery stage, P19; substage precedence end to end, P11; unexpected recovery exit, P23; escalation keeps the substage, P26; Setup recorded in
   `ai_deps`, also during recovery, P27).
5. T005 (opus) discovery and liveness: registry + `/proc` runners, marker/process identity
   with the watchdog semantics on bounded descriptor reads (P3, P14, P20, P24).
6. T006 (sonnet) snapshot model, status rules, `--once`/`--json`, wrapper, setup install;
   age filter keeps crashed runs (P7); no bytecode (P8); symlinked wrapper (P10).
7. T007 (sonnet) curses TUI and the shared renderer; writer-to-renderer tests (P1, P17, P18);
   pty interaction test (P25).
8. T008 (haiku) docs and final audit.

Dependencies: linear, T001 → T008. Plan reviews 1–5 (P1–P27): all findings accepted.

## Sequencing (Zack, 2026-10-07)
Implementation starts only after `feature/efficiency-batch` is merged: both runs edit
`scripts/lib/workflow.py`, `scripts/ai-run`, `tests/test_workflow.py`, README and the vault
flow note, and two agents test suites at once push the ~610 s gate over the session limit.
Before starting: merge `master` into `feature/dashboard` (by hand, coordinator), resolve the
mechanical conflicts, adjust the gate note in tasks.md if FL-11 changed `.ai/validate`, and
rerun the plan review if the plan changed.

## API / data changes
- New files (ignored, host-written): `.ai/local/observation.json`,
  `.ai/local/notifications.log`; host `<state root>/pipelines/<key>.json`.
- New helper: `workflow.py pipeline-register`. New scripts: `ai-dashboard`, `lib/dashboard.py`.

## Risks
- `.ai/local/` is agent-writable: a session can forge an observation or a notification
  line. The dashboard is advisory only (AD-5): it shows, never acts; strings are sanitised
  so a forged line cannot inject terminal escapes. Accepted and documented.
- Concurrent writers (pipeline and watchdog have separate locks): the notification log and
  the registry serialise their own writes with dedicated flock files; readers stay lock-free.
- `/proc` scan sees only this user's processes in practice; fine for a single-user machine.
- The pipeline running this batch uses the frozen `.ai/bin`; the new records appear in a
  project after its `.ai/bin` is upgraded. Older runs still show via `/proc` (stage unknown).

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; see the gate note in tasks.md).
