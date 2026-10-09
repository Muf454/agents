<!-- Host evidence: HEAD 2afe05af1f82efb46ed95aa7fba166449065ba2f; merge-base 1b914159633bff5897a4e120a9c61c094c0b5493; saved 2026-10-09T12:51:24Z. -->

> **Reviewer: Claude fallback (claude-fable-5-1, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

# Independent review

Overall verdict: REQUEST CHANGES. The observation records, gate-broken guard, safe record I/O, discovery and the renderer are implemented as the spec and tasks require, and I found no security regression. One demonstrated defect in the curses loop crashes the live view on the most natural usage path (dashboard open before the first pipeline starts), which is the view the human asked for; two minor rendering/discovery inaccuracies remain.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

Reviewed HEAD: `2afe05af1f82efb46ed95aa7fba166449065ba2f` (`feature/dashboard`)

Supplied base: `1b914159633bff5897a4e120a9c61c094c0b5493` (the merge-base is the same commit)

Inspected:
- `.ai/local/review-context/diff.patch`, `log.txt`, `files.txt`.
- Actual source: `scripts/lib/workflow.py` (safe record I/O and writers 3083–3499, `task_command` 458–528, `state_root`/`check_state_root` 1021–1051, `fingerprint` 531–564, `tree_snapshot` 1976–2007, `fail` 21), `scripts/lib/dashboard.py` (whole file), `scripts/lib/common.sh` (whole file), `scripts/ai-pipeline` 40–170 plus every `step`/`stop` call site, `scripts/ai-recover` 1–135, `scripts/ai-run` 78–133 and the diff hunks, `scripts/ai-review` hunk, `scripts/lib/watchdog.py` 60–110 and 465–483, `.gitignore`.
- Tests: `tests/test_dashboard.py` (fixtures 1–120, statuses 330–400, curses tests 730–813) and the names/locations of all `test_observation_*` tests in `tests/test_workflow.py`.
- Spec, plan tasks, handoff, state.

## Validation observed/run

- **Host evidence:** `.ai/local/validation.json` reports **PASS**, exit 0, `unchanged: true`, `2026-10-09T12:42:47Z`, `head` = `0764fcb` (one commit before HEAD). HEAD `2afe05a` changes only `.ai/run-log.md` and `.ai/state.md`, both excluded from the fingerprint (`workflow.py:537`), so the evidence covers HEAD's validated content.
- Handoff and T008/T009 results claim 541 tests OK in 8 shards. T009 notes one unreproduced failure in an earlier run (name not captured); the recorded final run passed.
- I ran no commands (no shell) and did not rerun the tests.
- Checked by reading: `.ai/local/` is excluded from the validation fingerprint (`workflow.py:544`), from the dependency tree snapshot (`:1996`) and from Git (`.gitignore:3`), so the new record writes cannot invalidate the stamp or trip `ai_deps`. `AI_BIN` is set when `common.sh` is sourced (`common.sh:4`), so the watchdog's `bash -c 'source …; ai_notify'` path logs through its own copy. Every `step` caller in `ai-pipeline` uses the new `KEY TITLE [DETAIL]` form; every `stop` label used (`start`, `plan review`, `plan revision`, `implementation`, `validation`, `review`, `triage`, `re-check`, `pull request preparation`, `push`, `pull request`, `final push`) is in `STOP_LABELS`. Lock before marker and `start` record in both `ai-pipeline` (78→84→85) and `ai-recover` (31, quiet exit before the trap at 89), so a rejected second process never overwrites a live run's record.

Limitations:
- No shell: I could not run the TUI or the suite; the MAJOR finding is from a code trace, not an observed traceback.
- I did not read the bodies of all ~60 `test_observation_*` tests; I verified their presence and read the dashboard status/curses tests in full.
- Vault notes are outside the checkout and were not read.

## Requirement assessment

- **Observation records and stop precedence:** `observation_update` (`workflow.py:3307–3354`) implements `start`/`step`/`detail`/`pause`/`resume`/`stop`/`recovering`/`done` as specified, including `done → stage=pr` (P43), `detail` only on the recorded stage, `resume` only lifting a pause, and the label → group/target table (P11). Callers are in place in `ai-pipeline`, `ai-run`, `ai_deps`, `ai-review`, `ai_limit_pause`, `ai-recover`.
- **Gate-broken guard (P32/P41/P42):** `ai_gate_check` sets `AI_GATE_BROKEN` outside command substitution; `stop()` computes `gate_ok` before `ai_observe stop` (`ai-pipeline:152–153`); `on_exit` in `ai-run:111`; the two pre-step pipeline gate stops (`:127`, `:132`); `ai-recover` 102–106, 168, 185, 196, 205; `ai_deps` (`common.sh:219`); `ai_guard_verify` (`:176–178`). `ai_observe`/`ai_notify_log` return early on the flag. Done.
- **Notification mirror:** `ai_notify` sends exactly as before and then always calls `ai_notify_log` (`common.sh:82–90`). Done.
- **Host registry:** `pipeline_register` writes under a bounded flock, re-reads before each prune (`workflow.py:3445–3484`); called after `branch=$AI_START_BRANCH` (`ai-pipeline:142`). Done.
- **Snapshot/read-only:** every checkout read goes through `checkout_fds`/`read_record`; no write path exists in `dashboard.py`. Status rules match the spec (`dashboard.py:278–288`), including the `last-error`-newer-than-record case (P44).
- **Renderer/TUI:** eight boxes from 120 columns, compact line below, overlays, stop-at-start text, `needs_you` drawn as stopped, legacy "stage unknown (older toolkit)". Keys, resize and scrolling are implemented. The TUI has the crash described in M1.
- **Install/docs:** `setup` list includes `ai-dashboard` and `lib/dashboard.py` (`workflow.py:306`); README and `docs/workflow.md` sections are present and match the code.

## BLOCKER findings

None found.

## MAJOR findings

### M1 — The TUI crashes with `TypeError` when the run list goes from empty to non-empty

**Status:** demonstrated (exact path traced).

**Location:** `scripts/lib/dashboard.py:622–643` (`interface`), specifically line 625.

**Problem:** `interface` keeps `selected` as an int, but sets it to `None` whenever the snapshot has no runs:

```python
selected = min(selected, len(runs) - 1) if runs else None   # line 625
```

On the next loop iteration after runs appear, `min(None, len(runs) - 1)` raises `TypeError: '<' not supported between instances of 'int' and 'NoneType'`. The refresh branch (lines 639–643) never restores an int: with `current = None`, `paths.index(current) if current in paths else selected` leaves `selected` as `None`.

Two realistic triggers:
1. Start `ai-dashboard` with no pipelines. The empty-state text says "Start one with .ai/bin/ai-pipeline --approved". The user starts one; within 2 s the auto-refresh returns one run and the dashboard dies.
2. All visible runs are old finished/idle ones (hidden by default) → empty view. Press `a` → runs appear → crash. The reverse (`a` to hide everything, then `a` again) crashes the same way.

`curses.wrapper` restores the terminal, so the terminal is not left broken, but the live view the user is meant to leave running in tmux (README "Keep it in tmux beside your runs") exits with a traceback.

**Evidence:** `test_dashboard_render_curses_smoke`, `..._interaction` and `..._failure_restores_the_terminal` (`tests/test_dashboard.py:775–812`) all use a fixed, non-empty `fixture_runs(...)`; no test changes the run count while the loop is running, and the empty state is tested only through `render([])` and `--once/--json` (`:330–333`, `:704–707`).

**Recommended direction:** keep `selected` an int at all times: for example `selected = min(selected, len(runs) - 1) if runs else 0` at line 625, and guard the key handlers with `if runs` (already done for ↓/↑/Enter). Add a pty test that starts with an empty state root, registers a fixture checkout while the loop runs (or toggles `a` with only old runs), waits for the card title, then quits with `q` and asserts exit 0.

## MINOR findings

### N1 — A legacy or malformed-record checkout with a `last-error` renders as "⛔ stopped before Plan check"

**Status:** demonstrated (path traced).

**Location:** `scripts/lib/dashboard.py:366–378` (`position`), `:402–409` (`marker_text`), `:272–284` (`inspect` status rule).

**Problem:** when `observation` is `None` (older toolkit, or a malformed `observation.json`) and `.ai/local/last-error` exists, `inspect` sets `observed = 0.0`, so `errored` is true and status becomes `needs_you`. `position` then returns `(None, 'stopped')` because `status == 'needs_you'` is tested before `index is None`, and `marker_text` with `index is None` prints `⛔ stopped before Plan check · <error>`. For a run on an older toolkit copy that stopped during, say, review, the card claims it stopped before the plan check. The spec says the stop-at-start wording is for a recorded `stage=none`; for no record it asks for "stage unknown (older toolkit)".

**Impact:** advisory, but it is exactly the case the handoff's human todo describes (projects whose `.ai/bin` is not yet upgraded will have `last-error` and no record), so the first real-world cards may be mislabelled.

**Recommended direction:** in `position`, when `observation` is `None`, return `(None, 'unknown')` even for `needs_you`, and let `marker_text`'s unknown branch append the `last_error` (e.g. `stage unknown (older toolkit) · ⛔ <error>`). Add a `render`/`--once` test: no `observation.json`, a `last-error` file, assert the line contains "older toolkit" and not "before Plan check".

### N2 — Discovery via the process table marks a checkout as running whenever any process names a runner script in its first three arguments

**Status:** demonstrated by code reading (trigger is realistic for this repository; not reproduced).

**Location:** `scripts/lib/dashboard.py:125–134` (`discover`) and `:170–171` (`liveness` no-marker rule), using `watchdog.is_runner` (`watchdog.py:85–87`).

**Problem:** `is_runner` matches `Path(arg).name in ('ai-run', 'ai-pipeline', 'ai-recover')` for any of the first three argv entries. `discover` applies it to every process on the machine and adds that process's cwd as a live runner. With no marker, `liveness` returns `alive` when `runners` is non-empty, so e.g. `vim scripts/ai-run`, `less .ai/bin/ai-pipeline` or `git diff scripts/ai-recover` run from a checkout with a real `.ai/` make that checkout appear as a `running` card (stage from its last record, or "stage unknown"). In the toolkit repository itself, where these scripts are edited daily, this is a routine false positive and sorts the card among live runs.

**Impact:** advisory only; no run is affected. The watchdog used the same predicate only for its orphan check, where the cost of a false match is lower.

**Recommended direction:** for discovery, require the runner name as the executable or the script argument of a shell (`args[0]` basename, or `args[0]` is `bash`/`sh` and `args[1]` is the script), not any of the first three arguments; or at least exclude processes whose first argument is a known editor/pager/VCS. Add a `dashboard_liveness_*` case: a fixture process `['vim', '/x/scripts/ai-run']` in a checkout must not make it alive.

## Missing test coverage

Checklist items checked (Python/shell tooling; no database, tenant or role surface):
- **1, lock order:** `observe` takes `observation.lock`, `notify_log` takes `notifications.lock`, `pipeline_register` takes `pipelines/.lock`; no path takes two of them, and every lock is `LOCK_NB` with a 2 s deadline (`workflow.py:3211–3233`). The dashboard takes none. No deadlock possible.
- **3, attribution:** `pid` is `os.getppid()` and `branch` is read from Git metadata, never from arguments (`:3407`). `updated` is server time.
- **4, stale results:** the TUI snapshot is synchronous per loop; no overlapping refreshes. The two-read marker check (`dashboard.py:166–169`) handles a run finishing mid-snapshot.
- **5, refresh wiring:** every `ai_notify` site now mirrors to the log; every stop path records through `stop()`/`ai_die`/`escalate`/`on_exit`, with `AI_STOP_NOTIFIED` preventing a second record (P35).
- **8, data hidden from views:** `--all`/24 h hiding applies only to `finished`/`idle`; `needs_you`, `crashed` and live runs always show (`dashboard.py:302–304`). `unknown` runs are never hidden.
- **2, 6, 7, 9, 10:** do not apply.

Gaps:
- No curses test with a changing run count (M1).
- No test for a legacy checkout with a `last-error` through `render` or `--once` (N1); `test_dashboard_snapshot_statuses` only plants `last-error` next to a valid `build` record.
- No discovery test with a non-runner process naming a runner script (N2).
- `ProcSource.start_ns` has no guard for a `stat` file without `btime`; an exception there would abort the whole snapshot. Real `/proc/stat` always has it, so this is noted, not counted.

## Security concerns

None new.
- The record helpers are project code and this change makes them run on more paths (every notification, every stage). I traced each gate-change detection site: all set `AI_GATE_BROKEN` before any `ai_observe`/`ai_notify_log` can run, in the calling shell. The remaining window (helper runs before the gate is compared at pipeline/recover start) existed before this branch (`ai_root` at `common.sh:117`) and is documented.
- Agent-writable text reaches the terminal only through `sanitize` (`dashboard.py:174–188`); the regex strips OSC/DCS/CSI/C1 sequences, controls, DEL and bidi overrides; `text_field` is applied to every checkout-derived field in `inspect`, `observation_of`, `events_of`, `tasks_of`.
- All checkout reads are no-follow, descriptor-pinned and size-capped; writes replace via `os.replace` on the pinned directory descriptor, so a planted symlink or hard link is replaced, never written through (`workflow.py:3236–3268`).
- The registry lives in the host state root and `check_state_root` refuses an overlap with the checkout.

## Architecture concerns

None. `dashboard.py` imports only `workflow.py` readers and `watchdog.is_runner`, as the plan required; the shell changes are confined to `common.sh` helpers and the existing stop/step/finish functions; `.ai/bin`, `.ai/prompts`, `.ai/validate` are untouched (`files.txt`).

Not counted: `ai_helper` runs `python3` without `-B` (pre-existing; the helper is the main script so no bytecode is written for it).

## Manual testing recommendations

### Needs you

- After M1 is fixed: start `ai-dashboard` in tmux with **no** pipeline running, then start `ai-pipeline --approved` in another checkout. The card must appear within 2 s and the dashboard must stay up. Then press `a` twice when only old runs exist.
- The live look-and-feel check already in the handoff (two runs, ↑↓ Enter a r q, resize across 120 columns).
- Open `vim scripts/ai-run` in `~/Projects/agents` while the dashboard runs and see whether that checkout appears as running (N2).
- A project whose `.ai/bin` is not yet upgraded and whose last run died: confirm the card says "older toolkit" rather than "stopped before Plan check" once N1 is addressed.

### Covered by automated tests

- Record writers, schema, stop-label mapping, pause/resume, symlink/FIFO/hard-link/held-lock safety, bounded readers, Git branch, registry, `tasks counts`: `test_observation_writer_*` (23 tests).
- Gate-broken guard at every detection site: `test_observation_gate_*` (6) plus the pre-existing `test_runner_detects_even_committed_gate_changes_before_untrusted_helpers` and the pipeline hook tests.
- Notification mirror and pause overlay: `test_observation_notify_*` (6).
- Pipeline, runner and recovery stage records end to end with mock agents: `test_observation_pipeline_*` (14), `test_observation_runner_*` (12), `test_observation_recovery_*` (10).
- Discovery, liveness, sanitising, snapshot statuses, hiding, read-only tree comparison, wrapper via symlink, setup/upgrade install: `test_dashboard_liveness_*`, `test_dashboard_sanitize_*`, `test_dashboard_snapshot_*`.
- Renderer golden widths, worst case, overlays, writer-to-renderer for all twelve stop labels, pty smoke/interaction/failure: `test_dashboard_render_*` (15).
- Should be added: a pty test for the empty → non-empty transition (M1); legacy checkout with `last-error` (N1); a non-runner process naming a runner script (N2).
- Full suite: 541 tests OK per host evidence at `0764fcb` (fingerprint unchanged at HEAD).

Review approval does not constitute human acceptance.
