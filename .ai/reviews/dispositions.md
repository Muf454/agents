# Review dispositions (Claude)

Review HEAD: 2afe05af1f82efb46ed95aa7fba166449065ba2f

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). From review round 3 on, also add a line starting
with "Convergence:" (see the triage prompt). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in `scripts/lib/dashboard.py:625`: an empty snapshot sets `selected = None`; the next pass evaluates `min(None, len(runs) - 1)` → `TypeError` once runs appear (auto-refresh after starting a pipeline, or `a` toggling between empty and non-empty). The refresh branch (`:639–643`) keeps `None` because `current` is `None`. The pty tests (`tests/test_dashboard.py` curses tests) only use a fixed non-empty run list. | T011 |
| N1 | accepted | Confirmed: with no/malformed `observation.json`, `inspect` uses `observed = 0.0` (`dashboard.py:268`), so any `last-error` makes the run `needs_you`; `position` (`:366–378`) tests `needs_you` before `index is None` and returns `(None, 'stopped')`, and `marker_text` (`:402–409`) prints "⛔ stopped before Plan check". The spec reserves that wording for a recorded `stage=none`; un-upgraded projects (handoff human todo) hit this path. Cheap and in scope. | T012 |
| N2 | accepted | Confirmed: `discover` (`dashboard.py:125–134`) uses `watchdog.is_runner`, which matches a runner basename in any of `args[:3]` (`watchdog.py:85–87`), so `vim scripts/ai-run` in a checkout with `.ai/` adds a runner and `liveness` (`:170–171`) returns `alive` when there is no marker. Real runners start through `#!/usr/bin/env bash`, so their argv is `bash <script> …` (or the script itself): a stricter dashboard-only predicate is cheap. The watchdog's own use is left unchanged. | T013 |
