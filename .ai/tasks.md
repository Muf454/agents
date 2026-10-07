# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files (this repo's `.ai/validate` and `.ai/ci-setup`
included). This run is started with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`
(absolute path) so the vault flow chart and hub Log can be updated. Source: Zack's request
of 2026-10-07 (pipeline dashboard, high priority; backlog OR-19 + minimal OR-12). Every task
leaves `.ai/bin/ai-check` passing. Flow-chart rule (AGENTS.md, CLAUDE.md): a task that
changes workflow behaviour updates the vault `agents-flow.md` (and its `updated:` date) in
the SAME task; T004 is only the final docs audit.
Gate note: the serial gate takes about 611 s. When `.ai/bin/ai-check` times out in the
session, run the task's targeted tests, record the timeout in the result, and leave the full
gate to the host's post-task `ai-check` (1800 s limit).
Read-only rule for this batch: nothing the dashboard does may write a file, take a lock or
change a run. Observation writers are best effort and never change a run's outcome.

## T001 — Observation records: stage snapshot, notification mirror, host registry
Status: TODO
Dependencies: none
Model: sonnet

### Goal
Let a reader see, per checkout, which flow stage runs now and the recent ntfy-style
messages, and let it find every checkout that ran a pipeline. Writers only; no reader yet.

### Implementation notes
scripts/lib/common.sh:
- `ai_observe STAGE [DETAIL]`: write `.ai/local/observation.json` atomically
  (`mktemp .ai/local/observation.XXXXXX` + `mv -f`), JSON `{"stage","detail","since","pid",
  "branch"}`; `since` = `date -u +%FT%TZ`, `pid` = `$$` of the pipeline when
  `AI_PIPELINE_MARKER`/`AI_LOCK_HELD` says one runs, else `$$`. Build the JSON with
  `python3 -c 'import json,sys; …' "$@"` (no hand escaping). Validate STAGE against the key
  list in the spec; unknown → ignore. Every failure is swallowed (`|| true`), never `ai_die`.
- `ai_notify`: after the existing send (or when `AI_NOTIFY_CMD` is unset), append
  `{"ts","message"}` (same full message as sent, with the `[project]` prefix) to
  `${AI_ROOT:-$PWD}/.ai/local/notifications.log` when that directory exists, then keep the
  last 200 lines (rewrite via temp + `mv` only when longer). Best effort.
- `ai_limit_pause`: `ai_observe paused "<agent> until <time>"` before sleeping; afterwards
  restore the stage that was current (read it back from the file before writing `paused`).
scripts/ai-pipeline:
- `step` takes a stage key first: `step KEY TITLE` → prints as today and calls
  `ai_observe KEY`. Keys: plan review → `plan_review`; implementation → `build`; validation
  → `checks`; independent review → `review`; review triage and "Completing the interrupted
  review triage" → `triage` (detail `round <n>`); re-check → `recheck`; pull request → `pr`.
- `stop` (and the pipeline-shell path of `ai_die` while `AI_PIPELINE_MARKER` is set) →
  `ai_observe stopped "<stage>: <reason>"` before notifying/exec'ing ai-recover.
- `finish` → `ai_observe done "<PR url or 'no PR'>"`.
- After `run-manifest start` (and on resume): `ai_helper pipeline-register "$AI_ROOT"
  "$branch" || printf 'Warning: …\n'`.
scripts/ai-run: `ai_observe setup` around `ai_deps` (only when it actually installs);
`ai_observe build "<id> · <model or default> · <done+1>/<total>"` when a task starts;
`--triage` → `ai_observe triage`. Keep the observation stage as-is when ai-run runs outside
a pipeline (it is still useful).
scripts/ai-recover: `ai_observe recovering "<attempt>/<max>: <stage>"` when it starts a
recovery; `ai_observe stopped "<stage>: <reason>"` in `escalate`.
scripts/lib/workflow.py: `pipeline-register CHECKOUT BRANCH`: `root = check_state_root(
checkout)`; write `root/'pipelines'/<sha256(checkout)[:16]>.json` `{"checkout","project"
(basename),"branch","started"}` with `atomic()`; delete other entries in that directory
whose `checkout` is not an existing directory or whose JSON is invalid.
Flow chart: add a short note under "Phone notifications" in the vault `agents-flow.md`: each
notification is also appended to `.ai/local/notifications.log`, and the scripts record the
current stage in `.ai/local/observation.json` (advisory, read by `ai-dashboard`; flow
unchanged). Update `updated:`.

### Likely affected modules
scripts/lib/common.sh, scripts/ai-pipeline, scripts/ai-run, scripts/ai-recover,
scripts/lib/workflow.py, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `observation_*` (existing fixture pipeline with mock claude/codex/gh, like
  `test_deps_runner_pipeline_end_to_end`):
  - a full pipeline run records the stages in order (capture each write, e.g. a mock agent
    that copies `observation.json` when called, plus the final state): `plan_review`,
    `build` with `T001 · …` detail, `checks`, `review`, `pr`, `done` with the PR URL;
  - a failing review stops with `stopped` and the reason; ai-recover's escalation records
    `stopped`, a recovery records `recovering`;
  - a Claude usage-limit pause (existing limit fixture, `AI_SLEEP`) records `paused` and the
    previous stage afterwards;
  - `notifications.log` holds one JSON line per `ai_notify` (also with `AI_NOTIFY_CMD`
    unset) and keeps only the last 200 lines;
  - an unwritable `.ai/local/observation.json` (directory in its place) and an unwritable
    state root for the registry do not change the run's exit status or outcome;
  - `pipeline-register` writes the entry and prunes entries of removed checkouts and invalid
    JSON.
- All existing tests pass unchanged (step titles/outputs unchanged).

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T002 — Snapshot model, `--once`/`--json`, `ai-dashboard` wrapper
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
A pure, read-only snapshot of all pipelines on this machine, printable as text or JSON.

### Implementation notes
New `scripts/lib/dashboard.py` (stdlib only; `sys.path` insert of its own directory to import
`state_root` from workflow.py and `process`, `is_runner` from watchdog.py, the way watchdog.py
imports workflow):
- `discover()`: checkouts from `<state root>/pipelines/*.json` (`checkout` must be an
  absolute existing directory containing `.ai/`), plus `/proc/<pid>/cwd` of live runner
  processes (`is_runner`) whose cwd contains `.ai/`; dedupe by realpath.
- `inspect(checkout, now)` → dict: `project`, `branch` (read `.git/HEAD` or the worktree's
  gitdir file; no git subprocess needed, fall back to `unknown`), `alive` (pipeline.active
  PID → `process()` is a runner), `observation` (validated fields, else none), `events` (last
  20 parsed notification lines, malformed lines skipped), `last_error`, `tasks` (done/total
  via workflow `task_blocks` on `.ai/tasks.md` text; on error none), `status`, `stage`,
  `since`, `updated` (newest mtime of the files read).
- Status rules (first match): marker PID dead but marker present → `crashed`; alive and stage
  `paused`/`recovering` → that; alive → `running`; stage `stopped` or a `last-error` newer
  than the observation with nothing alive → `needs_you`; stage `done` → `finished`; else
  `idle`. Legacy (no observation): stage `unknown`; with `alive` → `running`.
- `sanitize(text, limit=200)`: drop C0/C1 controls and ESC sequences, collapse whitespace,
  cap length with `…`.
- `snapshot(all_runs=False)`: list sorted needs_you → crashed → running/paused/recovering →
  finished → idle, then by `updated`; hides non-alive entries older than 24 h unless
  `all_runs`.
- CLI: `--once` (plain text: per run one title line, one compact stage line, last event;
  T003 replaces this with the shared renderer), `--json`, `--all`. Without `--once`/`--json`
  this task prints the text once too (T003 adds the TUI).
New `scripts/ai-dashboard` (bash, like `ai-status` but without `ai_root`: it must work outside
a checkout): `exec python3 "$AI_BIN/lib/dashboard.py" "$@"` after sourcing common.sh only
for `AI_BIN` (or compute it locally; it must not need `.ai/` in the cwd).
setup: add `ai-dashboard` to the installed script list and `lib/dashboard.py` to the lib
files in workflow.py `setup` (~line 303), with tests that a fresh setup installs both.

### Likely affected modules
scripts/lib/dashboard.py (new), scripts/ai-dashboard (new), scripts/lib/workflow.py,
tests/test_dashboard.py (new) or tests/test_workflow.py

### Acceptance criteria
- Tests named `dashboard_snapshot_*` with fixture checkouts in a temp dir and
  `AI_STATE_DIR` pointing to a temp state root:
  - one fixture per status (running via a live `sleep` process started as `ai-pipeline` via
    a symlink or `exec -a`, paused, recovering, needs_you, crashed, finished, idle) gives
    the expected status and stage;
  - a legacy checkout (no observation, no notifications) found only via `/proc` → running,
    stage unknown;
  - malformed `observation.json`, malformed log lines and an unreadable tasks file → no
    exception, fields unknown;
  - an ESC/OSC sequence in a notification and in `last-error` is absent from `--once` and
    `--json` output;
  - a run older than 24 h is hidden without `--all` and shown with it;
  - read-only: a recursive listing with mtimes of the fixture checkouts and the state root
    is identical before and after `--once` and `--json`;
  - `setup-project` installs `.ai/bin/ai-dashboard` and `.ai/bin/lib/dashboard.py`;
    `ai-dashboard --once` works from a directory that is not a Git checkout.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_snapshot` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T003 — Curses TUI with the flow as boxes
Status: TODO
Dependencies: T002
Model: sonnet

### Goal
The live view Zack asked for: every pipeline as a row of flow boxes, the active one
highlighted, one status line each; little text.

### Implementation notes
scripts/lib/dashboard.py:
- Pure `render(runs, width, selected=None, expanded=frozenset(), now)` → list of lines, each a
  list of `(text, style)` segments; styles are names (`title`, `active_claude`,
  `active_codex`, `active_script`, `done`, `pending`, `stopped`, `dim`, `event`). Used by
  `--once` (styles dropped) and by curses (styles → colour pairs / attributes).
- Stages and roles: Plan check (codex), Setup (script), Build n/N (claude), Checks (script),
  Review (codex), Triage (claude; re-check shows here as "Re-check"), PR (script). Stage key
  → box index; `done` → all passed; `stopped` → the box of the stage recorded before the stop
  (parse it from the `stopped` detail `<stage>: …`, else none) in style `stopped`.
- Width ≥ 100: three box lines (`┌─┐ │ │ └─┘`; active `╔═╗ ║ ║ ╚═╝`) joined by `──`, a
  marker line (✓ under passed boxes, the detail `T003 · sonnet · 12m` under the active box),
  then the latest event (`✅ Done …` with `HH:MM`). Overlays inside the active box: ⏸ paused,
  🔧 recovering, ⚠ crashed. Width < 100: title line, one compact line
  `✓Plan ✓Setup ▶Build 3/7 ·Checks ·Review ·Triage ·PR`, latest event. Lines never exceed
  `width` (truncate with `…`; account for wide emoji via `unicodedata.east_asian_width`).
- Header: `AI pipelines  <n> running · <n> needs you · <n> finished  HH:MM  ↑↓ ⏎ a r q`.
  Empty state: "No pipelines found. Start one with .ai/bin/ai-pipeline --approved (in tmux)."
- Expanded run (Enter): checkout path, last error, last 8 events with times.
- Curses loop (`curses.wrapper`): `halfdelay`/`timeout(2000)` refresh, `KEY_RESIZE`
  handling, keys q/↑/↓/Enter/a/r, `curses.use_default_colors()`; colour pairs matching the
  flow chart (Claude orange ≈ 208, Codex blue ≈ 33, scripts grey ≈ 245, stopped red, done
  green/dim) when `curses.COLORS >= 256`, basic colours otherwise, bold/reverse only without
  colour. Scroll when cards exceed the height (keep the selected card visible).
- Default `ai-dashboard` (no flags) on a TTY opens the TUI; not a TTY → behaves like `--once`.

### Likely affected modules
scripts/lib/dashboard.py, tests/test_dashboard.py

### Acceptance criteria
- Tests named `dashboard_render_*`:
  - golden text (styles dropped) for a running build at width 140 and 100 (double border
    around Build 3/7, ✓ under Plan check and Setup), and at width 60 (compact line);
  - a stopped review: the Review box carries style `stopped`; finished: all ✓ and the 🏁 line;
  - paused/recovering/crashed overlays; no rendered line exceeds the width (wide emoji
    counted as 2) at widths 40–200;
  - empty state text; expanded view shows at most 8 events.
- Test `dashboard_render_curses_smoke`: run `ai-dashboard` under `pty.fork()` with
  `TERM=xterm-256color`, `AI_STATE_DIR` fixture, send `q`; exits 0 within 10 s and the output
  ends with the terminal restored (contains the rmcup/normal-screen sequence or `stty -a`
  on the pty shows `icanon echo` after exit).

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_render` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T004 — Docs and final audit for the dashboard
Status: TODO
Dependencies: T003
Model: haiku

### Goal
Users find and understand the dashboard; records match the code.

### Implementation notes
- README: section "Watch all pipelines" after "Leave it running": `ai-dashboard` (from any
  project's `.ai/bin` or `~/Projects/agents/scripts/`), what the boxes and colours mean,
  keys, `--once`/`--json`/`--all`, tmux tip `tmux new -s dash ai-dashboard`, read-only and
  advisory (records in `.ai/local/` are agent-writable; never used to authorize); a row in the
  scripts table.
- docs/workflow.md: the observation records and the host registry (one paragraph).
- Vault (`--knowledge-dir`): `agents-flow.md` note checked against the code (T001 wrote it);
  hub `agents.md`: a dated Decision line ("2026-10-07 (Zack): pipeline dashboard, boxes
  layout, built ahead of OR-11/14/18") and a Log line; `agents-backlog.md`: OR-12 partially
  and OR-19 done-by-this-branch note (no checkbox ticking); `agents-human-todo.md`: optional
  `ln -s ~/Projects/agents/scripts/ai-dashboard ~/.local/bin/` and upgrading projects'
  `.ai/bin` so their runs record stages.
- `.ai/handoff.md` "Manual testing for the human" (`### Needs you` / `### Covered by
  automated tests`, naming the tests).

### Likely affected modules
README.md, docs/workflow.md, vault notes, .ai/handoff.md

### Acceptance criteria
- `DocsConsistencyTest` passes; README mentions `ai-dashboard`, `--once`, `--json`, `--all`.
- Handoff lists the manual checks (live TUI in tmux with two runs, resize, `q`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
