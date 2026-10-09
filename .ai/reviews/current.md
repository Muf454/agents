<!-- Host evidence: HEAD 6700246c6bafbab83682cbd100fbe61c3c000e90; merge-base 1b914159633bff5897a4e120a9c61c094c0b5493; saved 2026-10-09T14:10:01Z. -->

> **Reviewer: Claude fallback (claude-fable-5-1, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

I have what I need. The three accepted findings from round 1 are fixed in the source, the regression tests exercise the real paths, and the host gate evidence covers HEAD's validated content. Here is the review.

<!-- Host evidence: HEAD 6700246c6bafbab83682cbd100fbe61c3c000e90; merge-base 1b914159633bff5897a4e120a9c61c094c0b5493. -->

# Independent review

Overall verdict: APPROVE. Round 1's accepted findings M1, N1 and N2 are fixed in `scripts/lib/dashboard.py` with regression tests that exercise the real paths (pty loop with a changing run list, `--once`/`--json` on legacy and malformed checkouts, fixture and real processes for the runner predicate). The pre-existing flake (T014) is handled by a test-only change that keeps the test's two meaningful assertions. I found no new defect in the changed code and no regression in the rest of the range.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=0

Reviewed HEAD: `6700246c6bafbab83682cbd100fbe61c3c000e90` (`feature/dashboard`)

Supplied base: `1b914159633bff5897a4e120a9c61c094c0b5493` (the merge-base is the same commit)

Inspected:
- `.ai/local/review-context/since-last-review.patch` (whole), `log.txt`, `files.txt`, `.ai/local/validation.json` and its log `.ai/local/check-l0RjuF5y.log`.
- Actual source: `scripts/lib/dashboard.py` (whole file at HEAD: `is_runner` 28–39, `discover` 122–150, `liveness` 167–186, `inspect` 267–308, `position` 381–395, `marker_text` 419–435, `compact_card` 491–514, `wide_card` 462–488, `draw` 604–629, `interface` 632–663), `scripts/lib/watchdog.py` 74–87, 108, 286–345 (unchanged, confirmed via `files.txt`), the shebang line of every script under `scripts/`, the `ai-run`/`ai-recover` launch sites in `scripts/ai-pipeline` (158, 262, 306, 486), the limit messages in `scripts/ai-run` 184/446/488 and `scripts/lib/common.sh` 208.
- Tests: `tests/test_dashboard.py` 1–140 (fixtures, `spawn`, real-process and non-runner tests), 339–348 and 574–578 (`run_cli`), 643–728 (stop-at-start, writer-to-renderer, legacy/malformed, new legacy-with-error test), 762–830 (`pty_run`, `read_until`, `finish`, `fixture_runs`, smoke) and the two new pty tests in the patch; `tests/test_workflow.py` hunk at 4284–4288.
- `.ai/tasks.md` T011–T014, `.ai/handoff.md`, `.ai/state.md`, `.ai/reviews/current.md` (round 1), `.ai/reviews/dispositions.md`.

## Validation observed/run

- **Host evidence:** `.ai/local/validation.json` reports **PASS**, exit 0, `unchanged: true`, `2026-10-09T14:05:06Z`, `head` = `eae2a10`. Its log reads `Ran 547 tests in 344.1s (8 shards, 547 collected)` / `OK`. HEAD `6700246` changes only `.ai/run-log.md` and `.ai/state.md`, both excluded from the validation fingerprint, so the evidence covers HEAD's validated content.
- Test count moved 541 → 547 since round 1: +2 pty tests (T011), +1 legacy-with-error (T012), +1 non-runner predicate (T013); the remaining +2 are subtests/cases I did not attribute individually. The T013 run-log entry records one gate run at 546/547 with the T014 flake as the single failure, then 547 OK after T014.
- I ran no commands (no shell) and did not rerun the tests.

Limitations:
- No shell: the TUI tests' claim "fails on the old code" is from the run log, not reproduced here; I verified by reading that the old code path (`selected = None` then `min(None, …)`) is exactly what the new tests drive.
- T014's acceptance criterion (10 consecutive runs of the test alone) was not executed by the implementing session (shell allowlist); the run log records this. The fix is a widened string match, so its correctness follows from the two messages at `ai-run:184` and `common.sh:208` both containing `run time limit` case-insensitively.
- I did not re-read the bodies of the ~60 `test_observation_*` tests nor the shell callers again; nothing in the since-last-review diff touches them.

## Requirement assessment

- **M1 → T011 (TUI survives empty ↔ non-empty):** fixed. `interface` now clamps `selected = max(min(selected, len(runs) - 1), 0)` (`dashboard.py:644`), so it is always an int (0 when empty); only `shown` (`:645`) is `None` for the empty state and is what `layout`/`draw` receive, keeping their contract. The refresh branch (`:660–663`) leaves `selected` an int when `current` is `None`. Key handlers that index `runs` stay guarded (`:651–656`). `test_dashboard_render_curses_runs_appear_and_disappear` starts on an empty state root, registers a checkout while the loop runs, waits for the title through the 2 s auto-refresh, unlinks the registry entry, presses `r`, waits for the empty text, quits and asserts exit 0 and no `Traceback`; `..._all_toggle_with_only_old_runs` covers `a` with a 25 h old finished run (empty → shown → empty). Both drive the exact `None → min()` path that crashed before.
- **N1 → T012 (legacy checkout with `last-error`):** fixed. `position` returns `(None, 'unknown')` whenever there is no usable observation, before the `needs_you` test (`:388–389`); `finished` is still tested first but needs a `done` record, so it cannot apply. `marker_text`'s unknown branch appends `· ⛔ <last_error>` in style `stopped` (`:429–430`); `compact_card` emits the same marker line for `unknown` mode (`:511–513`). Status stays `needs_you` (unchanged `inspect`). The recorded `stage=none` stop still reaches `(None, 'stopped')` → "⛔ stopped before Plan check" (`:390–391`, `:425`), and `test_dashboard_render_stop_at_start` (`:646`) and the writer-to-renderer `start` case (`:676`) still assert that wording. `test_dashboard_render_legacy_checkout_with_last_error` covers no record and a record with an unknown stage, at 140 and 80 columns via `COLUMNS` (honoured by `shutil.get_terminal_size`, inherited by `run_cli`), and `needs_you` in `--json`.
- **N2 → T013 (editors naming a runner script):** fixed. Dashboard-only `is_runner` (`:28–39`): `argv[0]` basename is a runner, or is `bash`/`sh` and the first non-option argument's basename is a runner. Every runner script starts with `#!/usr/bin/env bash`, so a running runner's argv is `bash <path> …`; `ai-pipeline` execs `ai-recover` (`ai-pipeline:158`) and runs `ai-run` by path (`:262`, `:306`, `:486`), and the watchdog hands `systemd-run` the script path (`watchdog.py:315`), all of which go through the shebang and land on `bash <script>`. Used in both `discover` (`:142`) and the marker check in `liveness` (`:177`). `watchdog.py` is untouched (`files.txt`). Empty cmdlines (kernel threads) and the trailing empty element from the `\0` split are handled (`:31`, `:38`). The regression test covers `vim`, `less`, `git diff` (not discovered, `gone` when registered) and `bash <script> --approved` / bare script (discovered, `alive`); the real-process test now spawns a `#!/usr/bin/env bash` script with a trailing `:` so bash does not exec-optimise `sleep` away, which keeps argv as `bash <link>` like a real runner.
- **T014 (pre-existing flake):** test-only, as required. The limit can be hit in `ai_deps` (`common.sh:208`, "… not run: run time limit reached.") or later (`ai-run:184`); the test now matches `run time limit` case-insensitively and keeps the no-outcome-rows and no-mock-invocation assertions, so a run that starts a session still fails it.
- **Records:** tasks T011–T014 DONE with results (T011/T012/T014 result sections are empty in `tasks.md` but the run log carries the evidence); handoff names the four new tests under "Covered by automated tests" and adds the empty-start and `vim` manual check; state `ready_for_review`, 14 tasks complete.

## BLOCKER findings

None found.

## MAJOR findings

None found.

## MINOR findings

None found.

## Missing test coverage

Checklist items checked (Python tooling; no database, tenant or role surface):
- **4, stale async results:** the TUI loop is synchronous; the only state carried across refreshes is `selected`, `expanded` and `offset`, and `selected` is now re-clamped at the top of every iteration (`dashboard.py:644`), so a run list that shrinks between refreshes cannot leave an out-of-range index. Checked.
- **5, refresh wiring:** registry add/remove and `a` are both covered by the new pty tests; the auto-refresh path (`getch` → `-1`) is what the first test relies on. Checked.
- **8, data hidden from views:** `position` now reports `unknown` for every record-less run, including `crashed` and `running` legacy runs, which is the same result those statuses had before via `index is None`; `needs_you`/`crashed` are still never hidden. Checked.
- **1, 2, 3, 6, 7, 9, 10:** not touched by this round.

Gaps (not counted):
- The pty tests depend on curses emitting the whole target string on a redraw. `fixture_runs` documents the trick (a name sharing no character with its neighbours); the two new tests use the same name and the empty-state phrase, which shares no run of identical characters with the card title at the same columns, so ncurses' inline-cost rule will emit it whole. Two green gate runs agree. Noted as the one flake risk if the empty-state text or the header is ever changed.
- `spawn` now leaves an orphaned `sleep 120` per subtest when `process.kill` kills bash (two per gate run). Harmless, but a `trap`/`exec`-free cleanup or killing the process group would be tidier.
- `ProcSource.start_ns` still has no guard for a `stat` without `btime` (round 1 note, unchanged; real `/proc/stat` always has it).

## Security concerns

None new.
- The runner predicate only reads process argv already read by `ProcSource.process`; it narrows which processes count, so it cannot make the dashboard trust more than before.
- `marker_text` now prints `run['last_error']` on one more path; that value is already the sanitised first line (`inspect`, `:292`), so no new agent-controlled text reaches the terminal unsanitised.
- No gate file, `.ai/bin`, `.ai/prompts` or `.ai/validate` is in `files.txt`.

## Architecture concerns

None. The dashboard-only `is_runner` replaces the `watchdog` import and leaves the watchdog's orphan semantics unchanged, as the task prescribes; `position` keeps the "box is the observation's stage" rule and only reorders the record-less case ahead of the status check.

## Manual testing recommendations

### Needs you

- Open `ai-dashboard` in tmux with no pipeline running, then start `ai-pipeline --approved` in another checkout: the card appears within about 2 s and the dashboard stays up (handoff "Needs you" item 2).
- With only old finished runs present, press `a` twice: runs appear, then the empty state returns, no exit.
- Open `vim scripts/ai-run` in `~/Projects/agents` while the dashboard runs: that checkout must not appear as running.
- A project whose `.ai/bin` is not yet upgraded and whose last run died: the card reads "stage unknown (older toolkit) · ⛔ <error>", not "stopped before Plan check".
- The look-and-feel check from handoff item 1 (two runs, keys, resize across 120 columns, `q`).

### Covered by automated tests

- Empty ↔ non-empty run list in the live loop, auto-refresh and `r`/`a`: `test_dashboard_render_curses_runs_appear_and_disappear`, `test_dashboard_render_curses_all_toggle_with_only_old_runs`.
- Legacy and malformed-record checkouts with a `last-error` at 140 and 80 columns and `needs_you` in JSON: `test_dashboard_render_legacy_checkout_with_last_error`; the recorded stop at start keeps its wording: `test_dashboard_render_stop_at_start`, `test_dashboard_render_writer_to_renderer_stops_and_overlays`.
- Editors, pagers and git naming a runner script are not runners; `bash <script>` and a bare script are; a real bash-shebang process is alive: `test_dashboard_liveness_ignores_non_runner_processes`, `test_dashboard_liveness_real_pipeline_and_recover`.
- Time-limit stop without a session, either message: `test_outcome_no_time_left_logs_nothing` (T014).
- Full suite: 547 tests OK per host evidence at `eae2a10` (fingerprint unchanged at HEAD).

Review approval does not constitute human acceptance.
