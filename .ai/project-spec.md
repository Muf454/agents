# Spec: Pipeline dashboard (`ai-dashboard`)

## Objective
Pipeline dashboard (`ai-dashboard`)
One read-only terminal view of every AI pipeline on this machine: the pipeline flow drawn as
boxes with the active stage highlighted, plus one short ntfy-style status line per run
(▶ / ✅ / ⏸ / 🔧 / ⚠ / ⛔ / 🏁). Zack runs several pipelines at once (worktrees under
`~/Projects/wt/`, each in its own tmux session); tmux only keeps them alive and `ai-status`
covers one checkout and says nothing about where in the flow a run is.

Source: Zack, 2026-10-07 ("high prio": a TUI overview of the whole flow, where each run is,
all running pipelines, statuses like the ntfy app, active boxes highlighted, no overflow of
information). It implements the approved terminal-first direction (Q1, 2026-10-05): backlog
OR-19 plus the minimum of OR-12 (an observation snapshot) it needs, ahead of OR-11/14/18.
Layout chosen by Zack: boxes. Planned by Claude on 2026-10-07; the pipeline's Codex plan
review gates it.
Hub decisions respected: AD-4 (runtime observations are small atomic files in `.ai/local/`,
no SQLite, no daemon), AD-5 (status never authorizes; the watchdog only observes), roles vs
providers, gate files are never edited by a pipeline session.

## Requirements
- **Observation records (scripts only).** `common.sh` gains `ai_observe STAGE [DETAIL]`
  which atomically writes `.ai/local/observation.json`
  `{"stage", "detail", "since" (UTC ISO), "pid", "branch"}` (temp file + `mv`; best effort:
  a failure never changes a run's outcome or exit status). Stage keys:
  `plan_review setup build checks review triage recheck pr done stopped paused recovering`.
  Writers: `ai-pipeline` (each `step`, `stop`/pipeline `ai_die` → `stopped` with the reason,
  `finish` → `done` with the PR URL when there is one), `ai-run` (`setup` around `ai_deps`;
  `build` per task with detail `<id> · <model> · <n>/<N>`; `triage` for `--triage`),
  `ai_limit_pause` (`paused`, detail `<agent> until <time>`; afterwards the previous stage is
  restored), `ai-recover` (`recovering`, detail `<attempt>/<max>`; escalation → `stopped`).
  Validation inside the pipeline (`ensure_validated`) → `checks`.
- **Notification mirror.** `ai_notify` also appends one JSON line `{"ts", "message"}` to
  `${AI_ROOT:-$PWD}/.ai/local/notifications.log` when that `.ai/local` directory exists,
  whether or not `AI_NOTIFY_CMD` is set; the file keeps the last 200 lines. Never fatal.
  Messages from the watchdog (it notifies through `ai_notify`) land there too.
- **Host registry.** `ai-pipeline` start (and resume) runs a new helper
  `workflow.py pipeline-register` that writes `<state root>/pipelines/<key>.json`
  `{"checkout", "project", "branch", "started"}` (key: sha256 of the checkout path, first 16
  hex, like `binding_dir`; state root from `state_root()`/`check_state_root`) and removes
  entries whose checkout directory no longer exists. Failure prints a warning, never stops.
- **Snapshot model** (`scripts/lib/dashboard.py`, Python stdlib only). Discovers checkouts
  from the registry and from a `/proc` scan for live runner processes (`process()`,
  `is_runner()` from `scripts/lib/watchdog.py`; cwd → checkout root containing `.ai/`), so
  runs on an older toolkit copy also appear. Per checkout: project, branch, liveness
  (`.ai/local/pipeline.active` PID alive and a runner), observation, last notifications,
  `last-error`, task counts (existing `tasks()` parser) → status one of `running`, `paused`,
  `recovering`, `needs_you` (stopped/escalated), `crashed` (marker left but its process is
  gone), `finished`, `idle`, with stage `unknown` when no observation exists. Missing or
  malformed files degrade to `unknown`, never a crash. Strictly read-only: no writes, no
  locks, no git commands that write.
- **Sanitising.** Every string read from a checkout (agent-writable) has control characters
  and escape sequences removed and is length-capped before output.
- **Output modes.** `ai-dashboard --once` prints a plain-text rendering (no curses; for pipes,
  Remote Control and tests) and `--json` the snapshot; plain `ai-dashboard` opens the TUI.
  `--all` includes finished/stopped/idle runs older than 24 h (hidden by default).
- **TUI** (Python `curses`, `scripts/ai-dashboard` bash wrapper). Header: counts
  (running / needs you / finished), clock, key help. One card per run, sorted needs you →
  crashed → running/paused/recovering → finished → idle: title line
  (`<icon> <project> · <branch>` and `<status> <age>`); at width ≥ 100 a row of seven boxes
  Plan check → Setup → Build n/N → Checks → Review → Triage (incl. re-check) → PR joined by
  `──`; the active box has a double border, bold and the role colour of the flow chart
  (Claude orange: build/triage; Codex blue: plan check/review/re-check; scripts grey:
  setup/checks/PR); passed boxes dim with ✓ below; a stopped run's box red; paused ⏸,
  recovering 🔧, crashed ⚠ inside the box; detail (`T003 · sonnet · 12m`) under the active
  box; last notification line with its time. Width < 100: one compact line
  `✓Plan ✓Setup ▶Build 3/7 ·Checks ·Review ·Triage ·PR`. Finished: all ✓ and the 🏁 line.
  Keys: `q` quit, `↑/↓` select, `Enter` toggles details (last 8 notifications, last error,
  checkout path), `a` toggle all, `r` refresh; auto refresh every 2 s; resize handled;
  terminal restored on exit and on exceptions; no colours → bold/reverse only.
- **Install.** `setup-project` installs `ai-dashboard` and `lib/dashboard.py` into `.ai/bin`
  like the other scripts; it also runs from `~/Projects/agents/scripts/`.

## Non-goals
No control actions (stop, resume, approve) from the dashboard; no event history (OR-17); no
`ai-status --json`/`--watch` (OR-11/OR-18 stay in the backlog); no web or phone view; no
change to `.ai/validate`, `.ai/bin`, `.ai/prompts`, permissions or the CI workflow of this
repo; no new runtime dependency (curses is stdlib); no change to what ntfy sends.

## Acceptance
- Fixture pipeline runs (mock claude/codex) leave the expected `observation.json` stages and
  notification lines; a stop records `stopped` with its reason; a pause records `paused`;
  observation and registry failures never change a run's outcome.
- `ai-dashboard --once` / `--json` on fixture checkouts show each status correctly, including
  a legacy checkout with no observation and malformed files; escape sequences are removed;
  nothing is written anywhere (verified by a before/after tree comparison).
- `render()` golden outputs at widths 60, 100 and 140 (double-bordered active box, red
  stopped box, compact line); a curses smoke test under a pty quits on `q` and restores
  the terminal.
- README and `docs/workflow.md` describe it; vault notes updated.
- All existing tests pass; `.ai/validate` passes.
