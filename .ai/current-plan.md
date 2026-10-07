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

## Approach (revised after Codex plan reviews 1 (P1–P10) and 2 (P11–P18); all accepted)
1. T001 (opus) safe record writers in workflow.py: `observe` (schema, overlays, stop-label
   normalisation, path safety), `notify-log` (flock + O_NOFOLLOW + trim), `pipeline-register`
   (flock, race-safe prune), plus the shared safe I/O (pinned directory descriptors,
   nonblocking regular-file opens, bounded reads and locks) the dashboard reuses.
   Concurrency and path safety → opus (P4–P6, P12–P14).
2. T002 (sonnet) stage writers: `ai_observe`/`ai_notify` in common.sh call the helpers;
   ai-pipeline, ai-run (incl. its own `ai-check` calls, P2), ai-recover, pause; writer-level
   tests; vault flow note.
3. T003 (sonnet) snapshot model, `--once`/`--json`, wrapper, setup install; liveness reuses
   the watchdog semantics (P3); age filter keeps crashed runs (P7); no bytecode (P8);
   symlinked wrapper (P10).
4. T004 (sonnet) curses TUI and the shared renderer; writer-to-renderer tests (P1).
5. T005 (haiku) docs and final audit.

Dependencies: T001 → T002 → T003 → T004 → T005.

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
