# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files (this repo's `.ai/validate` and `.ai/ci-setup`
included). This run is started with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`
(absolute path) so the vault flow chart and hub Log can be updated. Source: Zack's request
of 2026-10-07 (pipeline dashboard, high priority; backlog OR-19 + minimal OR-12). Every task
leaves `.ai/bin/ai-check` passing. Flow-chart rule (AGENTS.md, CLAUDE.md): a task that
changes workflow behaviour updates the vault `agents-flow.md` (and its `updated:` date) in
the SAME task; T007 is only the final docs audit.
Gate note: the serial gate takes about 611 s. When `.ai/bin/ai-check` times out in the
session, run the task's targeted tests, record the timeout in the result, and leave the full
gate to the host's post-task `ai-check` (1800 s limit).
Read-only rule for this batch: nothing the dashboard does may write a file, take a lock or
change a run. Observation writers are best effort and never change a run's outcome.
Revised after Codex plan review 1 (P1–P10, all accepted): T001 split
into safe writers (opus) and stage hooks (sonnet); overlay schema; checks inside ai-run;
watchdog liveness semantics; locking and no-follow writes; crashed runs never hidden.
Revised after plan review 3 (`.ai/reviews/plan.md`, P19–P22, all accepted): explicit
recovery stage key; safe traversal for Git metadata and `.ai/tasks.md`; old T002 split into
T002–T004; handoff flow line marked pending until T002.
Revised after plan review 2 (P11–P18, all accepted): substage wins
over an outer stop label; nonblocking opens and bounded locks; directory-descriptor-relative
I/O; one bounded safe reader (T001) used by the dashboard; handoff flow declaration restored
(P15); unknown-stage rendering; Re-check in Codex colour.

## T001 — Safe record I/O: observation, notification log, host registry, bounded readers
Status: TODO
Dependencies: none
Model: opus

### Goal
The three host-written records the dashboard reads, written safely under concurrency and
never through an agent-planted symlink. Helpers only; callers come in T002–T005.

### Implementation notes
scripts/lib/workflow.py (new subcommands; every one exits 0 and prints `Warning: …` to stderr
on any failure or deadline, so callers are never blocked or failed):
- Shared safe I/O (P12–P14), used by every writer here and by the dashboard (T005):
  - `local_dir_fd(root)`: open ROOT, then `.ai`, then `local` each with
    `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` relative to the previous descriptor (`dir_fd=`); a
    symlink or non-directory anywhere → refuse. All later opens, temp creation, `rename`,
    `unlink` and `flock` use that pinned descriptor (`dir_fd=`/`src_dir_fd=`), never a path
    string, so replacing `.ai` or `.ai/local` after the check cannot redirect any I/O.
  - `open_dir(base_fd, relative)`: walk each component with
    `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` relative to the previous descriptor; any symlink or
    non-directory → None. `checkout_fds(root)` returns pinned descriptors for the checkout
    root, `.ai` and `.ai/local` (P20).
  - `git_branch(root_fd)` (P20): read `.git` via `read_record`: a directory → `HEAD` inside
    it; a regular file `gitdir: <abs path>` (worktree) → open that absolute directory with
    `open_dir` from `/` (every component no-follow except that the toolkit accepts it only
    when the path is absolute and has no `..`), then `HEAD`; `ref: refs/heads/<name>` →
    name, a sha → `detached`, anything else → None. No git subprocess.
  - `read_record(dir_fd, name, limit)` → `(text, stat)` or None: open with
    `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`, `fstat` must be a regular file, read at most `limit`
    bytes (observation 64 KiB, notifications 256 KiB tail, marker/last-error 4 KiB, tasks
    1 MiB, git HEAD/.git 4 KiB) from that descriptor, decode UTF-8 with `errors='replace'`,
    and return the descriptor's `fstat` (mtime, size) with the text so callers such as the
    marker check get content and metadata from the same open file (P20). Never blocks on a
    FIFO or device.
  - Writes: open/create with `O_NOFOLLOW|O_NONBLOCK` (+ `O_EXCL` for temp files), `fstat`
    regular before writing; `flock` with `LOCK_EX|LOCK_NB` retried every 50 ms up to a 2 s
    deadline, then warn and skip the write.
- `observe ACTION [ARGS]` on `observation.json` (schema in the spec):
  `step STAGE [DETAIL]` (state active, new `since`), `pause NOTE` (keep stage/detail/since,
  state paused), `resume` (state active, note cleared), `stop LABEL REASON`,
  `recovering NOTE [STAGE]`, `done NOTE`. Unknown stage keys are refused (warning).
  Stop precedence (P11): each outer label has a group of box keys — `implementation` →
  {setup, build, checks}; `validation` → {checks}; `plan review` → {plan_review}; `review` →
  {review}; `triage` → {triage}; `re-check` → {recheck}; `pull request`, `pull request
  preparation`, `final push` → {pr}; empty label → any. If the recorded stage is in the
  label's group (or the label is empty/unknown), keep it; otherwise use the label's first
  key. `recovering NOTE [STAGE]` (P19): STAGE, when given, must be a valid box key and is
  set directly (no label normalisation); without it the current stage is kept.
  Temp file + `os.replace(…, src_dir_fd=fd, dst_dir_fd=fd)` (replaces a symlink at the
  destination instead of following it); the previous record is read with `read_record`.
- `notify-log ROOT MESSAGE`: `flock` on `notifications.lock` (bounded as above); append one
  JSON line `{"ts","message"}` to `notifications.log` (regular file, nonblocking open);
  over 200 lines → write the last 200 to a temp file and `os.replace`, still under the lock.
- `pipeline-register CHECKOUT BRANCH`: `root = check_state_root(checkout)`; under a bounded
  `flock` on `root/pipelines/.lock` write `<sha256(checkout)[:16]>.json` atomically, then
  prune: for each other entry, re-read it under the lock and delete it only when its JSON is
  invalid or its `checkout` is not an existing directory.
No flow-chart change (no behaviour yet).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py (or tests/test_dashboard.py)

### Acceptance criteria
- Tests named `observation_writer_*`:
  - each action produces the schema; a pause keeps stage/detail/since and `resume` restores
    `active`; every existing stop label (`implementation`, `validation`, `plan review`,
    `review`, `triage`, `re-check`, `pull request`, `pull request preparation`, `final push`)
    maps to its box key when the recorded stage is outside its group; `stop implementation`
    after `step checks` or `step setup` keeps checks/setup (P11); an unknown label keeps the
    stage; `recovering 1/2 checks` after `step build` gives `stage=checks,
    state=recovering`, `recovering 1/2` keeps the stage, an invalid STAGE is refused (P19);
  - `.ai` or `.ai/local` as a symlink, `observation.json` as a symlink to a sentinel, the
    temp name pre-planted as a symlink, and `.ai/local` replaced by a symlink AFTER
    validation (in-process test that swaps the directory between `local_dir_fd` and the
    write): outside sentinels unchanged, exit 0;
  - FIFO `observation.json` / `notifications.log` / `notifications.lock` and a lock held by
    another process: the helper returns within 5 s (test timeout), exit 0, warning;
  - `read_record`: FIFO, symlink to `/dev/zero`, a 10 MiB file and invalid UTF-8 return
    within 5 s with None or a bounded, decoded result; its stat matches the opened file;
  - `git_branch`: a normal repository and a `git worktree add` checkout give the branch; a
    detached HEAD gives `detached`; `.git` as a FIFO, a symlinked `.git`, a `gitdir:` with
    `..` or a relative path, and a symlink inside the gitdir path give None within 5 s;
  - `checkout_fds`/`open_dir`: `.ai` symlinked → None; `.ai/tasks.md` read through the
    pinned `.ai` descriptor after `.ai` is swapped for a symlink reads the original;
  - `notify-log`: a symlinked log and a symlinked lock leave the sentinel unchanged; 250
    messages keep the last 200 in order; with 200 older lines prefilled, two processes
    appending 100 uniquely numbered messages each concurrently (production limit) leave
    exactly those 200 new messages, once each, every line valid JSON (P16);
  - `pipeline-register`: writes the entry; prunes a removed checkout and invalid JSON; a
    registration replaced between the prune's listing and its delete (simulated by a hook
    or by holding the lock in the test and rewriting the entry) is kept; `pipelines` being
    a regular file → warning, exit 0, other state files untouched.

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_writer` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T002 — Notification mirror and pause overlay (common.sh)
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
Every notification is also kept locally, and usage-limit pauses show on the current stage.
No change to what is sent or printed.

### Implementation notes
scripts/lib/common.sh: `ai_observe ACTION ARGS…` → `ai_helper observe "$@" || true`;
`ai_notify` → after sending (or when `AI_NOTIFY_CMD` is unset) `python3 -B
"$AI_BIN/lib/workflow.py" notify-log "${AI_ROOT:-$PWD}" "[$project] $*" 2>/dev/null || true`
(the watchdog's `bash -c 'source common.sh; ai_notify …'` path then logs too).
`ai_limit_pause`: `ai_observe pause "<agent> until <time>"` before sleeping, `ai_observe
resume` after.
Vault `agents-flow.md`: a note under "Phone notifications": every notification is also kept
in `.ai/local/notifications.log` (read by `ai-dashboard`; advisory; flow unchanged); update
`updated:`. Then change `.ai/handoff.md` "## Flow chart" from "pending" to the completed
wording (still starting with `Flow chart updated`, test
`test_pr_body_flow_this_repo_declares_the_flow_chart`).

### Likely affected modules
scripts/lib/common.sh, tests/test_workflow.py, vault agents-flow.md, .ai/handoff.md

### Acceptance criteria
- Tests named `observation_notify_*`:
  - `notifications.log` holds the same messages the mock `AI_NOTIFY_CMD` received in an
    existing fixture run, and lines also with `AI_NOTIFY_CMD` unset;
  - the watchdog's notification (existing watchdog fixture) is logged; a symlinked log
    (sentinel) leaves the sentinel and the watchdog outcome unchanged;
  - a FIFO `notifications.log` and a `notifications.lock` held by another process for the
    whole run: the run completes with its normal outcome (P12);
  - a Claude usage-limit pause (existing limit fixture with `AI_SLEEP`) after `observe step
    build …`: `state=paused` with the stage kept during the sleep (captured by the `AI_SLEEP`
    mock), `state=active` afterwards; same for a Codex pause during a review.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_notify` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T003 — Pipeline stage records and registration (ai-pipeline)
Status: TODO
Dependencies: T002
Model: sonnet

### Goal
`ai-pipeline` records each flow stage, its stop and its finish, and registers the checkout.

### Implementation notes
scripts/ai-pipeline: `step KEY TITLE` (prints exactly as today, then `ai_observe step KEY`):
plan review → `plan_review`; implementation → `build`; validation → `checks`; independent
review → `review`; review triage and "Completing the interrupted review triage" → `triage`
(detail `round <n>`); re-check → `recheck`; pull request → `pr`. `stop STAGE` →
`ai_observe stop "$STAGE" "$reason"` before notifying or exec'ing ai-recover; the
pipeline-shell `ai_die` path (marker set) → `ai_observe stop '' "$*"` (keeps the stage);
`finish` → `ai_observe done "<url or 'no PR'>"`. After `run-manifest start` and on resume:
`ai_helper pipeline-register "$AI_ROOT" "$branch" || true`.
Vault `agents-flow.md`: extend the T002 note: the scripts also record the current stage in
`.ai/local/observation.json` and each pipeline registers its checkout in the host state
directory (`pipelines/`); `updated:`.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `observation_pipeline_*` (existing fixture pipeline with mock claude/codex/gh,
  like `test_deps_runner_pipeline_end_to_end`, capturing `observation.json` inside the mocks):
  - a normal run records `plan_review`, `build`, `review`, `pr`, then `done` with the PR URL;
  - a review failure → `stage=review, state=stopped` with the reason; a plan-review stop →
    `plan_review`;
  - the registry entry exists after a run; `pipelines` replaced by a regular file in the
    state root: warning, run outcome unchanged, run manifest still written;
  - terminal output of `step` unchanged (existing tests pass unchanged).

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_pipeline` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T004 — Runner and recovery stage records (ai-run, ai-recover)
Status: TODO
Dependencies: T003
Model: sonnet

### Goal
Setup, build, checks and recovery inside `ai-run`/`ai-recover` show on the right box,
including after failures.

### Implementation notes
scripts/ai-run: `ai_observe step setup` only when `ai_deps` actually installs (stale);
`ai_observe step build "<id> · <model or default> · <done+1>/<total>"` when a task starts;
`ai_observe step checks "<id>"` before its post-task `ai-check` (~line 292) and
`ai_observe step checks final` before the final one (~257); `--triage` → `step triage`.
scripts/ai-recover: `ai_observe recovering "<attempt>/<max>"` when recovery starts;
`ai_observe recovering "<attempt>/<max>" checks` before its leftover validation (explicit
stage key, P19); `escalate` → `ai_observe stop "$stage" "<reason>"`.
No new flow-chart change (T003's note covers stage records).

### Likely affected modules
scripts/ai-run, scripts/ai-recover, tests/test_workflow.py

### Acceptance criteria
- Tests named `observation_runner_*` (fixture pipeline, observations captured inside the mock
  agent and the mock validator):
  - a normal run shows `build` (detail `T001 · …`) during the session and `checks` during
    ai-run's own post-task and final validation;
  - substage precedence end to end (P11): a failing post-task validation and a failing final
    validation end with `stage=checks, state=stopped`; a failing dependency install ends
    with `stage=setup, state=stopped`; the same after ai-recover escalation;
  - recovery: `state=recovering` with the stopped stage kept; recovery validation of a
    stopped build shows `stage=checks, state=recovering`; its failure and escalation end
    with `state=stopped` (P19).
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_runner` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T005 — Snapshot model, `--once`/`--json`, `ai-dashboard` wrapper
Status: TODO
Dependencies: T004
Model: sonnet

### Goal
A pure, read-only snapshot of all pipelines on this machine, printable as text or JSON.

### Implementation notes
New `scripts/lib/dashboard.py` (stdlib only; `sys.dont_write_bytecode = True` BEFORE the
`sys.path` insert of its own directory, then import `state_root` from workflow.py and
`process`, `is_runner`, `start_ns` from watchdog.py, the way watchdog.py imports workflow).
Every checkout file is read only through T001's `checkout_fds`/`read_record`/`git_branch`
(bounded, nonblocking, regular files only, pinned descriptors; P14, P20), including
`pipeline.active` (content and mtime from one open), `.ai/tasks.md` and Git metadata; a
checkout whose records cannot be read safely shows as `unknown` while the others render:
- `discover()`: checkouts from `<state root>/pipelines/*.json` (`checkout` must be an
  absolute existing directory containing `.ai/`), plus `/proc/<pid>/cwd` of live runner
  processes (`is_runner`) whose cwd contains `.ai/`; dedupe by realpath.
- `inspect(checkout, now)` → dict: `project`, `branch` (read `.git/HEAD` or the worktree's
  gitdir file; no git subprocess needed, fall back to `unknown`), `alive` (pipeline.active
  PID → `process()` is a runner), `observation` (validated fields, else none), `events` (last
  20 parsed notification lines, malformed lines skipped), `last_error`, `tasks` (done/total
  via workflow `task_blocks` on `.ai/tasks.md` text; on error none), `status`, `stage`,
  `since`, `updated` (newest mtime of the files read).
- Status rules (first match): crashed → `crashed`; alive and state `paused`/`recovering` →
  that; alive → `running`; state `stopped`, or a `last-error` newer than the observation,
  with nothing alive → `needs_you`; state `done` → `finished`; else `idle`. Legacy (no
  observation): stage `unknown`; alive → `running`.
- `sanitize(text, limit=200)`: drop C0/C1 controls and ESC sequences, collapse whitespace,
  cap length with `…`.
- `snapshot(all_runs=False)`: list sorted needs_you → crashed → running/paused/recovering →
  finished → idle, then by `updated`; hides only `finished`, `needs_you` and `idle` entries
  whose `updated` is older than 24 h unless `all_runs` (crashed and live runs always show).
- CLI: `--once` (plain text: per run one title line, one compact stage line, last event;
  T006 replaces this with the shared renderer), `--json`, `--all`. Without `--once`/`--json`
  this task prints the text once too (T006 adds the TUI).
New `scripts/ai-dashboard` (bash; must work outside a checkout and through a symlink): resolve
its real location with `readlink -f -- "${BASH_SOURCE[0]}"`, then
`exec python3 -B "$dir/lib/dashboard.py" "$@"`. Do not source common.sh (it reads user
config and needs nothing here).
setup: add `ai-dashboard` to the installed script list and `lib/dashboard.py` to the lib
files in workflow.py `setup` (~line 303), with tests that a fresh setup installs both.

### Likely affected modules
scripts/lib/dashboard.py (new), scripts/ai-dashboard (new), scripts/lib/workflow.py,
tests/test_dashboard.py (new) or tests/test_workflow.py

### Acceptance criteria
- Tests named `dashboard_snapshot_*` with fixture checkouts in a temp dir and
  `AI_STATE_DIR` pointing to a temp state root:
  - one fixture per status (running via a live process named `ai-pipeline` through a
    symlinked script, paused, recovering, needs_you, crashed, finished, idle) gives the
    expected status and stage;
  - process identity: a marker whose PID is reused by a newer process → crashed, not
    running; a marker removed during the snapshot → not crashed; a dead pipeline with an
    orphaned live `ai-run` child → crashed; a legacy checkout with no marker and no
    observation, found only via `/proc` → running, stage unknown;
  - malformed `observation.json`, malformed log lines and an unreadable tasks file → no
    exception, fields unknown;
  - an ESC/OSC sequence in a notification and in `last-error` is absent from `--once` and
    `--json` output;
  - a checkout with a FIFO marker, a FIFO observation and a 10 MiB notification log, next to
    a healthy checkout: `--once` returns within 5 s and shows the healthy run correctly;
  - old (> 24 h) finished, needs_you and idle runs are hidden without `--all` and shown with
    it; an old crashed run is shown in both;
  - read-only: a recursive listing with mtimes of the fixture checkouts, the state root, the
    toolkit `scripts/` directory and a freshly installed `.ai/bin` is identical before and
    after `--once` and `--json` run from both the toolkit and the installed copy (no
    `__pycache__` appears);
  - `ai-dashboard --once` through a symlink in a temp `bin/` directory outside any checkout
    works;
  - `setup-project` installs `.ai/bin/ai-dashboard` and `.ai/bin/lib/dashboard.py`;
    `ai-dashboard --once` works from a directory that is not a Git checkout.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_snapshot` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

## T006 — Curses TUI with the flow as boxes
Status: TODO
Dependencies: T005
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
  Review (codex), Triage (claude; `recheck` shows in this box as "Re-check" with style
  `active_codex`, P18), PR (script).
  The box is always the observation's `stage`; `state` only decorates it: `stopped` → that box
  in style `stopped`, `paused` ⏸ / `recovering` 🔧 inside it, `done` → all passed. No parsing
  of free text. Stage `none`, `unknown`, or no/malformed observation (P17): no box is
  highlighted or ticked, the marker line says `stage unknown` (legacy runs: `stage unknown
  (older toolkit)`), and the title/status and last event still render.
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
  - writer-to-renderer: observations produced by the T001 `observe` helper (not hand-written
    fixtures) for a paused build, a paused review, a recovery and a stop from each real
    stop label render the overlay in the right box;
  - `recheck` renders the Triage box as "Re-check" in `active_codex`;
  - legacy and malformed-observation snapshots render with no active box and `stage
    unknown`, through `render()` and through `ai-dashboard --once`;
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

## T007 — Docs and final audit for the dashboard
Status: TODO
Dependencies: T006
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
- Vault (`--knowledge-dir`): `agents-flow.md` note checked against the code (T002/T003 wrote it);
  hub `agents.md`: a dated Decision line ("2026-10-07 (Zack): pipeline dashboard, boxes
  layout, built ahead of OR-11/14/18") and a Log line; `agents-backlog.md`: OR-12 partially
  and OR-19 done-by-this-branch note (no checkbox ticking); `agents-human-todo.md`: optional
  `ln -s ~/Projects/agents/scripts/ai-dashboard ~/.local/bin/` and upgrading projects'
  `.ai/bin` so their runs record stages.
- `.ai/handoff.md`: "## Flow chart" still starts with `Flow chart updated` and matches the
  vault note; "Manual testing for the human" (`### Needs you` / `### Covered by
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
