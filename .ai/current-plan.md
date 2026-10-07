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

## Approach
1. T001 (sonnet) observation records: `ai_observe`, notification mirror, registry helper and
   all writers; tests via the existing fixture pipeline. Flow-chart note (flow unchanged:
   observation only).
2. T002 (sonnet) `scripts/lib/dashboard.py` snapshot model: discovery, status derivation,
   sanitising, `--once` text and `--json`; `scripts/ai-dashboard` wrapper; setup installs.
3. T003 (sonnet) curses TUI: pure `render(snapshot, width)` shared with `--once`, flow boxes,
   colours, compact mode, keys, resize, cleanup.
4. T004 (haiku) docs: README, docs/workflow.md, vault notes.

Dependencies: T001 → T002 → T003 → T004.

## API / data changes
- New files (ignored, host-written): `.ai/local/observation.json`,
  `.ai/local/notifications.log`; host `<state root>/pipelines/<key>.json`.
- New helper: `workflow.py pipeline-register`. New scripts: `ai-dashboard`, `lib/dashboard.py`.

## Risks
- `.ai/local/` is agent-writable: a session can forge an observation or a notification
  line. The dashboard is advisory only (AD-5): it shows, never acts; strings are sanitised
  so a forged line cannot inject terminal escapes. Accepted and documented.
- `/proc` scan sees only this user's processes in practice; fine for a single-user machine.
- The pipeline running this batch uses the frozen `.ai/bin`; the new records appear in a
  project after its `.ai/bin` is upgraded. Older runs still show via `/proc` (stage unknown).

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; see the gate note in tasks.md).
