# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files (this repo's `.ai/ci-setup` included). This run is
started with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` (absolute path) so the
vault flow chart, hub Log and human todos can be updated. Source: vault backlog "Run flow
improvements (approved by Zack 2026-10-06)", FL-01, FL-07, FL-09 (FL-03 dropped from this
batch, still in the backlog). Every task leaves
`.ai/bin/ai-check` passing. Flow-chart rule (AGENTS.md, CLAUDE.md): every task that changes
workflow behaviour updates the vault `agents-flow.md` (diagram/notes and its `updated:`
frontmatter date) in the SAME task; T004 is only the final docs audit.

## T001 — Host runs .ai/ci-setup when dependencies are missing or stale (FL-01)
Status: TODO
Dependencies: none
Model: opus

### Goal
FL-01: the host (ai-run / ai-pipeline, never an agent session) installs dependencies with the
project's approved `.ai/ci-setup` before tasks and host validation, so a fresh worktree or a
changed lockfile doesn't stop the run (2026-10-05 23:06: stale `node_modules`).

### Implementation notes
scripts/lib/workflow.py:
- `deps_spec()`: read `.ai/ci-setup`; inputs from `# ai-deps-inputs: <paths/globs>` lines,
  else the default lockfile list (package-lock.json, npm-shrinkwrap.json, pnpm-lock.yaml,
  yarn.lock, bun.lock, bun.lockb, requirements*.txt, poetry.lock, uv.lock, Pipfile.lock,
  Gemfile.lock, go.sum, Cargo.lock, composer.lock) at the repo root; outputs from
  `# ai-deps-outputs: <dirs>`, else `node_modules` when `package.json` exists. Paths must be
  relative and inside the checkout (reject `..`/absolute; no symlink escapes).
- `deps-status`: prints `current`, or `stale <reason>` (no stamp / ci-setup changed /
  `<input>` changed or added or removed / `<output>` missing). Stamp `.ai/local/deps.json`:
  `{setup: sha256, inputs: {path: sha256}}`.
- `deps-record`: write the stamp atomically for the current files.
scripts/lib/common.sh `ai_deps [TIMEOUT]`: if `deps-status` is `current`, return. Else print
`Dependency setup (.ai/ci-setup): <reason>`, snapshot `git status --porcelain
--untracked-files=all`, run `timeout --signal=TERM --kill-after=10s "$limit" bash .ai/ci-setup
< /dev/null > .ai/local/deps-XXXXXXXX.log 2>&1`, on non-zero `ai_die "Dependency setup
(.ai/ci-setup) failed (exit N; timeout after Ns when 124); see <log>"`; then `ai_guard_verify`;
status must equal the snapshot else `ai_die "Dependency setup changed project files
(.ai/ci-setup must only install ignored dependencies): <paths>"`; `deps-record`; `ai_log none
'dependencies installed (.ai/ci-setup)' …`. Limit: `AI_DEPS_TIMEOUT` (default 1200),
capped by the caller's remaining run time.
Callers: scripts/ai-run before every task session (inside the loop, after `ai_guard_verify`,
only when a task will run) and before every host `ai-check` (post-task and final);
`ai-run --triage` does not install. scripts/ai-pipeline `ensure_validated` before
`ai-check`. Add `AI_DEPS_TIMEOUT` to the `ai_config` allowlist, `RUN_SETTINGS` and the
ai-recover restore list. Runner prompt (templates/.ai/prompts/runner.md): one sentence that
the host installs dependencies from `.ai/ci-setup`; if a task changes a lockfile, note it in
the result (the host installs before its gate).
Template (folded in from the dropped template task, minimal): `templates/.ai/ci-setup`
keeps its default "installing nothing" behaviour and gains comment lines only: the host runs
this file before tasks when dependencies are missing or stale; the declaration lines
`# ai-deps-inputs:` / `# ai-deps-outputs:` with one npm example (`npm ci`,
`package-lock.json`, `node_modules`) and the defaults when absent; it must only install
ignored dependencies, never edit tracked files.
Flow chart (same task): vault `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`: a host step
"dependencies (.ai/ci-setup) when missing/stale" before each task and before the checks,
with its ⛔ stop; bump `updated:`.

### Likely affected modules
scripts/lib/workflow.py, scripts/lib/common.sh, scripts/ai-run, scripts/ai-pipeline,
scripts/ai-recover, templates/.ai/prompts/runner.md, templates/.ai/ci-setup, tests/test_workflow.py,
vault agents-flow.md

### Acceptance criteria
- Tests named `deps_setup` (fixture `.ai/ci-setup` declares `# ai-deps-inputs: deps.lock`
  and `# ai-deps-outputs: vendor-deps`, creates `vendor-deps/` and appends to a call log;
  `vendor-deps/` is git-ignored):
  - first `ai-run --approved`: ci-setup runs once before the first mock claude call (the mock
    asserts `vendor-deps/` exists), stamp written, run-log line present;
  - a second task with unchanged inputs: no second ci-setup call; after a task changes
    `deps.lock`: ci-setup runs again before the post-task gate;
  - missing output dir with a current stamp → runs again;
  - ci-setup exits 1 → `ai-run` exits 1 before any mock claude call, last-error names
    `.ai/ci-setup` and the log path; timeout (`AI_DEPS_TIMEOUT=1`, ci-setup sleeps) → same
    with "timeout";
  - ci-setup modifying a tracked file (or creating a non-ignored file) → stop "changed project
    files"; no stamp written;
  - default spec without declarations: `package.json` + `package-lock.json` → stale until
    `node_modules` exists; no lockfiles and no package.json → `current` with no ci-setup run;
  - an input path with `..` or absolute → `deps-status` fails with a clear error;
  - ai-pipeline: `ensure_validated` installs before `ai-check` (all tasks DONE, no stamp).
  - the template `templates/.ai/ci-setup` passes `bash -n`, still installs nothing and
    contains both declaration keywords.
- Gate files never modified (existing guard tests pass); all existing tests pass.
- Vault flow chart shows the dependency step; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k deps_setup` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T002 — "Needs you" vs "Covered by automated tests" in handoff and PR (FL-09)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
FL-09: the PR says exactly what Zack must check by hand; automated fault injections are
listed separately with their test names (PR #14 listed 10 automated steps as manual).

### Implementation notes
scripts/lib/workflow.py: `manual_testing(handoff)` returns `(needs_you, automated, legacy)`
from "Manual testing for the human": subsections `### Needs you` and `### Covered by
automated tests`; without them the whole section is "needs you" (legacy). `pr_body`: the
"How to test" section renders `### Needs you` first ("None — everything below is automated"
when None/empty), then `### Covered by automated tests` inside `<details><summary>N
automated checks</summary>`; a bullet without a backticked name gets " ⚠ no test named".
`finish_summary`: counts only needs-you steps: "Test: N manual step(s) in the PR", or
"Nothing to test by hand (N automated checks in the PR)" when None; legacy unchanged.
Templates: `templates/.ai/handoff.md` section with both subsections and comments;
runner.md and triage.md (keep "How to work here" identical where shared), fix-review.md,
review.md ("Manual testing recommendations": what a human must check vs what should be or is
an automated test), templates/CLAUDE.md (~line 75) and templates/AGENTS.md (~line 29).
Rule text: "Needs you" only for things a human must do (look and feel, phone/real devices,
live accounts, external services, decisions); every step reproducible by a test goes under
"Covered by automated tests" with the test name.
Flow chart (same task): the PR/FINISHED part says the PR separates "Needs you" from
automated checks and the notification counts only "Needs you"; bump `updated:`.

### Likely affected modules
scripts/lib/workflow.py, templates/.ai/handoff.md, templates/.ai/prompts/{runner,triage,fix-review,review}.md,
templates/CLAUDE.md, templates/AGENTS.md, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `manual_testing_split`:
  - pr-body: needs-you steps appear before the automated list; automated list inside
    `<details>` with its count; an automated bullet without a backticked name is flagged;
  - "None" under Needs you → PR says so; finish-summary says "Nothing to test by hand (N
    automated checks in the PR)" and does not count automated steps;
  - legacy handoff (no subsections) → output identical to today's (existing tests unchanged);
  - template texts: runner/triage "How to work here" sections still identical
    (`tool_contract` tests), handoff template has both subsections, review.md mentions both.
- Existing `finish_summary`, `pr_body`, `tool_contract` tests pass.
- Vault flow chart updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k manual_testing_split` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T003 — Watchdog timer at setup, start warning, PID-based waits (FL-07)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
FL-07: every checkout that runs a pipeline has its watchdog timer, missing timers are
visible at start, and documented waits loop on a PID (two `pgrep -f` waits died on
2026-10-05/06 by matching themselves).

### Implementation notes
scripts/lib/watchdog.py: `--timer-status` (mutually exclusive with install/uninstall):
prints `installed <timer unit>` (exit 0) or `missing <timer unit>` (exit 1) using the same
unit-name logic as `timer()` (factor out `unit_name(root)`). scripts/lib/workflow.py
`setup`: new `--watchdog` (not with `--dry-run`/`--upgrade`): after a successful install run
`<root>/.ai/bin/ai-watchdog <root> --install-timer --diagnose --recover` (stdin /dev/null);
a failure exits non-zero with its output ("files were installed; the timer was not"). Without
the flag, the final message adds "Next: install the watchdog timer: .ai/bin/ai-watchdog
--install-timer --diagnose --recover". scripts/ai-pipeline at start: if `ai-watchdog
--timer-status` exits 1, print "No watchdog timer for this checkout; …" and append
"(no watchdog timer for this checkout)" to the STARTED/RESUMED notification; never stop.
README: "Waiting for a run" (coordinator/scripts): wait on the pipeline PID
(`while kill -0 "$pid" 2>/dev/null; do sleep 60; done`, or `.ai/local/pipeline.active`
contents), never `pgrep -f <pattern>` loops (the loop's own command line matches); remove
the timer with `--uninstall-timer` before deleting a worktree. Test: no `pgrep -f` in
scripts/, templates/, docs/, README.md. Vault `agents-human-todo.md`: add one open item
(don't tick anything): "Watchdog timers: confirm/install for agents, raid-planner,
family-planner and each new run worktree (Claude can do it: `.ai/bin/ai-watchdog
--install-timer --diagnose --recover`)".
Flow chart (same task): setup step mentions the optional timer and the start warning;
bump `updated:`.

### Likely affected modules
scripts/lib/watchdog.py, scripts/lib/workflow.py, scripts/ai-pipeline, README.md,
tests/test_workflow.py, vault agents-flow.md, vault agents-human-todo.md

### Acceptance criteria
- Tests named `watchdog_setup` (mock systemctl):
  - `setup-project --watchdog` installs files and the timer units (unit files exist, host
    copy exists, systemctl enable called); `--watchdog --dry-run` and `--watchdog --upgrade`
    are rejected; a failing systemctl → non-zero exit with the message, files installed;
  - plain setup prints the "Next: install the watchdog timer" line and writes no units;
  - `--timer-status` → `missing …` exit 1 before install, `installed …` exit 0 after;
  - ai-pipeline without a timer prints the warning and the STARTED notification carries the
    note; the run continues (existing pipeline test flow passes);
  - no `pgrep -f` in scripts/, templates/, docs/, README.md.
- Existing watchdog tests pass.
- Vault flow chart and human-todo updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k watchdog_setup` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T004 — Final docs audit for batch 2
Status: TODO
Dependencies: T001, T002, T003
Model: haiku

### Goal
README, docs/workflow.md and the vault notes describe batch 2 accurately; the PR carries
the flow-chart line and the two-part manual testing section.

### Implementation notes
Cross-check against the code and the T001–T003 results: docs/workflow.md (dependency step:
inputs/outputs, declaration lines, stamp, timeout, stops, risk that ci-setup runs
package-manager code on the host; Needs you vs automated; timer status/warning; waits),
README (CI section ~line 374: the host also runs `.ai/ci-setup` before tasks; modes table and
setup steps if affected; config keys incl. `AI_DEPS_TIMEOUT`). Add
`docs_consistency` required sentences for the dependency step and the "Needs you" split.
Vault `agents-flow.md`: consistent wording, no duplicates, `updated:` current; fix only what
is wrong. Hub `agents.md`: append a dated Log line (never tick vault checkboxes). This repo's
`.ai/handoff.md`: `## Flow chart` line starting "Flow chart updated" (required by
`test_pr_body_flow_this_repo_declares_the_flow_chart`), and "Manual testing for the human"
in the new format: "Needs you" only for real human checks (e.g. a real overnight run with a
fresh worktree, phone notification wording), every scripted scenario under "Covered by
automated tests" with its test name.

### Likely affected modules
README.md, docs/workflow.md, tests/test_workflow.py, .ai/handoff.md, vault agents-flow.md,
vault agents.md (Log)

### Acceptance criteria
- Tests named `docs_consistency` pass, including the new required sentences.
- Docs describe only implemented behaviour; no FL-02/03/04/05/06 promises.
- Vault chart audited, hub Log line added; handoff flow-chart line and two-part manual
  testing present (every automated bullet names a test).

### Validation
Targeted: `python3 -m unittest discover -s tests -k docs_consistency` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.
