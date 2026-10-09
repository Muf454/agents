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
Layout chosen by Zack: boxes. Planned by Claude on 2026-10-07; rebased on master e9354d9
(FL-04 supervisor, FL-14–17) on 2026-10-09 with the plan revision as its own box (Zack,
2026-10-09); the pipeline's Codex plan review gates it.
Hub decisions respected: AD-4 (runtime observations are small atomic files in `.ai/local/`,
no SQLite, no daemon), AD-5 (status never authorizes; the watchdog only observes), roles vs
providers, gate files are never edited by a pipeline session.

## Requirements
- **Observation records (scripts only; revised after plan review 1, P1/P2/P4/P5/P9).**
  One record per checkout, `.ai/local/observation.json`:
  `{"stage", "state", "detail", "since", "note", "pid", "branch", "updated"}`.
  `stage` is always a flow box key: `plan_review plan_revision setup build checks review
  triage recheck pr` (or `none` before the first step and after a stop at start); `state` is
  `active`, `paused`, `recovering`, `stopped` or `done`. A human (re)start of ai-pipeline
  records `start` (stage `none`, state active, detail/note cleared) so an earlier run's record
  never shows on the new run; a recovery resume keeps the recovering record. Overlays never
  replace the underlying stage: a pause keeps `stage`, `detail` and `since` and sets
  `state=paused`, `note=<agent> until <time>`; afterwards `state=active` again. `detail STAGE
  TEXT` changes only the detail, and only when STAGE is the recorded stage (review format
  retry). A stop sets `state=stopped`, `note=<reason>`, with the stage normalised from the
  existing stop labels (revision 9, verified against the code): `start`→none (always; the
  "base moved past the branch" early stop), `plan review`→plan_review (kept when the recorded
  stage is plan_review or plan_revision), `plan revision`→plan_revision,
  `implementation`→build (kept on setup/build/checks), `validation`→checks, `review`→review,
  `triage`→triage, `re-check`→recheck, `pull request preparation`/`push`/`pull request`/`final
  push`→pr; an empty or unknown label keeps the last stage. Recovery sets
  `state=recovering`, `note=<attempt>/<max>`, keeping the stage that stopped. `done`:
  `stage=pr`, `note=<PR url or "no PR">`.
  Writers: `ai-pipeline` (`start`; each `step`, including the plan revision step with detail
  `<r>/<max> · round <n>`, the interrupted revision (`resumed`), the stored needs-human
  decision (Plan revision, `needs your decision`) and the triage round with `· extra (…)` for
  the supervised extra fix round; `stop`; the pipeline-shell `ai_die`; `finish`),
  `ai_deps` in common.sh (`setup` at an actual install, as a recovering overlay during
  recovery), `ai-run` (`build` per task with detail
  `<id> · <model> · <n>/<N>`; `checks` around its post-task and final `ai-check` calls,
  then `build` again when the next task starts; `triage`/`plan_revision` for `--triage` and
  `--revise-plan` only outside a pipeline, whose own record they would overwrite),
  `ai-review` (`detail <stage> format retry` after its 🔁 format retry notification),
  `ai_limit_pause` (pause overlay), `ai-recover` (`recovering`; its recovery validation
  shows `stage=checks, state=recovering`; a stored decision → Plan revision; escalation →
  `stopped`, keeping the substage recovery last recorded), `ensure_validated` in the
  pipeline (`checks`).
  All writes go through one Python helper (`workflow.py observe`), which refuses a missing,
  symlinked or non-directory `.ai/local`, writes via a temp file in `.ai/local` + `rename`
  (never following a symlink at the destination) and never fails the caller (exit 0, warning
  on stderr).
- **Safety and bounds (plan review 2, P11–P14).** A recorded substage wins over an outer stop
  label from the same group (`implementation` covers setup/build/checks), so a failed
  validation or install stays on Checks/Setup. All record I/O (writers and the dashboard's
  reads) goes through one helper set in workflow.py: directories opened with
  `O_DIRECTORY|O_NOFOLLOW` and used as pinned descriptors; files opened `O_NOFOLLOW|O_NONBLOCK`,
  regular files only, reads size-capped; locks `LOCK_NB` with a 2 s deadline. Unsafe input or
  a deadline → warning and skip, never a blocked or failed run, never a frozen dashboard.
- **Notification mirror.** `ai_notify` also records each message through
  `workflow.py notify-log` into `${AI_ROOT:-$PWD}/.ai/local/notifications.log` (JSON lines
  `{"ts","message"}`, kept to the last 200), whether or not `AI_NOTIFY_CMD` is set. Writers
  (every script that notifies, and the watchdog) serialise append + trim with `flock` on
  `.ai/local/notifications.lock`; the existing log inode is never written (hard-link
  safe): each update reads it bounded, appends and trims in memory, and replaces it with an
  exclusively created temp file + `rename` under the lock. Readers take no lock
  and skip a malformed or partial last line. Never fatal.
- **Host registry.** `ai-pipeline` start (and resume) runs `workflow.py pipeline-register`:
  under `flock` on `<state root>/pipelines/.lock` it writes
  `<state root>/pipelines/<sha256(checkout)[:16]>.json` `{"checkout","project","branch",
  "started"}` atomically and removes entries whose checkout is no longer an existing
  directory or whose JSON is invalid (re-read under the lock before each delete). Only this
  helper writes there. A failure (e.g. `pipelines` is not a directory) prints a warning and
  never stops the run; the run manifest stays mandatory as today.
- **Snapshot model** (`scripts/lib/dashboard.py`, Python stdlib only). Discovers checkouts
  from the registry and from a `/proc` scan for live runner processes (`process()`,
  `is_runner()` from `scripts/lib/watchdog.py`; cwd → checkout root containing `.ai/`), so
  runs on an older toolkit copy also appear. Per checkout: project, branch, liveness
  (as the watchdog decides it: `marker_snapshot`/`pipeline_died` semantics in watchdog.py,
  i.e. PID, process start time not after the marker, `ai-pipeline`/`ai-recover` only, marker
  re-read; with no marker, live runner processes found in that checkout count, so legacy
  versions without `pipeline.active` show as running), observation, last notifications,
  `last-error`, task counts (existing `tasks()` parser) → status one of `running`, `paused`,
  `recovering`, `needs_you` (stopped/escalated), `crashed` (marker left but its process is
  gone), `finished`, `idle`, with stage `unknown` when no observation exists. Missing or
  malformed files degrade to `unknown`, never a crash. Strictly read-only: no writes, no
  locks, no git commands that write.
- **Sanitising.** Every string read from a checkout (agent-writable) has control characters
  and escape sequences removed and is length-capped before output.
- **Output modes.** `ai-dashboard --once` prints a plain-text rendering (no curses; for pipes,
  Remote Control and tests) and `--json` the snapshot; plain `ai-dashboard` opens the TUI.
  `--all` includes `finished`, `needs_you` and `idle` runs whose newest record is older than
  24 h (hidden by default); `crashed`, `running`, `paused` and `recovering` are always shown.
  No bytecode is written (`sys.dont_write_bytecode` before sibling imports; wrapper uses
  `python3 -B`); the wrapper resolves its real path (`readlink -f`) so a symlink in
  `~/.local/bin` works.
- **TUI** (Python `curses`, `scripts/ai-dashboard` bash wrapper). Header: counts
  (running / needs you / finished), clock, key help. One card per run, sorted needs you →
  crashed → running/paused/recovering → finished → idle: title line
  (`<icon> <project> · <branch>` and `<status> <age>`); at width ≥ 120 (revision 9: eight
  boxes need up to 112 columns) a row of eight boxes
  Plan check → Plan revision → Setup → Build n/N → Checks → Review → Triage (incl. re-check)
  → PR joined by `──`; the active box has a double border, bold and the role colour of the
  flow chart (Claude orange: plan revision/build/triage; Codex blue: plan check/review/
  re-check; scripts grey: setup/checks/PR); passed boxes dim with ✓ below; a stopped run's box
  red with the stop reason (e.g. a plan decision's questions) on the marker line; a stop at
  start (stage none) highlights no box and says `⛔ stopped before Plan check`; paused ⏸,
  recovering 🔧, crashed ⚠ inside the box; detail (`T003 · sonnet · 12m`, `round 3 · extra
  (5 → 3 → 1)`, `format retry`) under the active box; last notification line (▶ ✅ ⏸ 🔧 🔁 ⚠
  ⛔ 🏁 …) with its time. Width < 120: one compact line
  `✓Plan ✓Revise ✓Setup ▶Build 3/7 ·Checks ·Review ·Triage ·PR`. Finished: all ✓ and the 🏁
  line.
  Keys: `q` quit, `↑/↓` select, `Enter` toggles details (last 8 notifications, last error,
  checkout path), `a` toggle all, `r` refresh; auto refresh every 2 s; resize handled;
  terminal restored on exit and on exceptions; no colours → bold/reverse only.
- **Install.** `setup-project` (and `setup-project --upgrade`, which uses the same list)
  installs `ai-dashboard` and `lib/dashboard.py` into `.ai/bin` like the other scripts; it
  also runs from `~/Projects/agents/scripts/`.

## Non-goals
No control actions (stop, resume, approve) from the dashboard; no event history (OR-17); no
`ai-status --json`/`--watch` (OR-11/OR-18 stay in the backlog); no web or phone view; no
change to `.ai/validate`, `.ai/bin`, `.ai/prompts`, permissions or the CI workflow of this
repo; no new runtime dependency (curses is stdlib); no change to what ntfy sends.

## Acceptance
- Fixture pipeline runs (mock claude/codex) leave the expected `observation.json` stages and
  notification lines; a stop records `stopped` with its reason; a pause records `paused`; a
  supervised plan revision, a stored needs-human decision, an extra fix round, a review format
  retry and the base-moved early stop each leave their box and detail;
  observation and registry failures never change a run's outcome.
- `ai-dashboard --once` / `--json` on fixture checkouts show each status correctly, including
  a legacy checkout with no observation and malformed files; escape sequences are removed;
  nothing is written anywhere (verified by a before/after tree comparison).
- `render()` golden outputs at widths 60, 119, 120 and 140 (double-bordered active box, red
  stopped box, compact line below 120); a curses smoke test under a pty quits on `q` and
  restores the terminal.
- README and `docs/workflow.md` describe it; vault notes updated.
- All existing tests pass; `.ai/validate` passes.
