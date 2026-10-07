# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files (this repo's `.ai/ci-setup` included). This run is
started with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` (absolute path) so the
vault flow chart, hub Log and human todos can be updated. Source: vault backlog "Run flow
improvements (approved by Zack 2026-10-06)", FL-01, FL-07, FL-09 (FL-03 dropped from this
batch, still in the backlog). Every task leaves
`.ai/bin/ai-check` passing. Flow-chart rule (AGENTS.md, CLAUDE.md): every task that changes
workflow behaviour updates the vault `agents-flow.md` (diagram/notes and its `updated:`
frontmatter date) in the SAME task; T007 is only the final docs audit. Revised after the Codex plan review
(`.ai/reviews/plan.md`, P1–P7): FL-01 simplified (host installs only at the start of
`ai-run` and before recovery validation; no tracked-file logging) and tasks split.

## T001 — Dependency freshness, stamp and tree snapshot helpers (FL-01)
Status: DONE
Dependencies: none
Model: opus

### Goal
FL-01 building blocks: decide whether `.ai/ci-setup` must run, record that it ran, and
prove an install changed no project file. Helpers only; no caller yet (T002, T003).

### Implementation notes
scripts/lib/workflow.py:
- `deps_spec()`: read `.ai/ci-setup`; inputs from `# ai-deps-inputs: <paths/globs>` lines,
  else the default lockfile list (package-lock.json, npm-shrinkwrap.json, pnpm-lock.yaml,
  yarn.lock, bun.lock, bun.lockb, requirements*.txt, poetry.lock, uv.lock, Pipfile.lock,
  Gemfile.lock, go.sum, Cargo.lock, composer.lock) that exist at the repo root; outputs from
  `# ai-deps-outputs: <dirs>`, else `node_modules` when `package.json` exists. Declared paths
  must be relative and inside the checkout (reject absolute and `..`; resolve symlinks).
- `deps-status`: `current` or `stale <reason>`. Stale when: no stamp `.ai/local/deps.json`;
  the SHA-256 of `.ai/ci-setup` differs; the input map (path → SHA-256) differs (added,
  removed, changed); a declared/default output is missing. No shortcut: an empty input map
  with no stamp is stale (a configured installer without lockfiles runs once) (P5).
- `deps-record`: atomically write `{setup, inputs}` for the current files.
- `tree-snapshot`: one SHA-256 over HEAD's sha, the staged diff (`git diff --cached
  --binary`), and every non-ignored path (`git ls-files --cached --others
  --exclude-standard -z`, excluding `.ai/local/`) with its kind, mode and bytes (symlink:
  target; missing tracked file: a marker). Submodules (P9): a gitlink entry (mode 160000)
  is snapshotted recursively by the same function run inside the submodule (its HEAD,
  staged diff and all non-ignored files, nested submodules likewise); an uninitialised
  submodule records a marker. Unchanged submodules give equal snapshots, so projects with
  submodules keep working. Equal snapshots before/after an install prove
  that no tracked or untracked project file, mode, index entry or commit changed, even
  when the tree was already dirty (P2). Ignored paths (the installed dependencies) are not
  covered by design.
templates/.ai/ci-setup: comment lines only (behaviour stays "installing nothing"): the host
runs this file at the start of `ai-run` and before recovery validation when dependencies are
missing or stale; `# ai-deps-inputs:` / `# ai-deps-outputs:` with one npm example
(`npm ci`, `package-lock.json`, `node_modules`) and the defaults; it must only install
ignored dependencies. No flow-chart change (no behaviour yet).

### Likely affected modules
scripts/lib/workflow.py, templates/.ai/ci-setup, tests/test_workflow.py

### Acceptance criteria
- Tests named `deps_status`:
  - declared inputs/outputs: stale without stamp; `current` after `deps-record`; stale after
    editing the input, adding/removing a declared input, editing `.ai/ci-setup`, or removing
    the output dir;
  - defaults: `package.json` + `package-lock.json` → stale until `node_modules` exists and a
    stamp is recorded;
  - configured installer without lockfiles or package.json: stale without stamp, `current`
    after `deps-record`, still `current` on the next check (P5);
  - an input with `..`, an absolute path, or a symlink leaving the checkout → clear error;
  - `tree-snapshot` changes when: an already modified tracked file is overwritten, a file's
    mode changes (also with `core.filemode=false`), a commit is made, the index changes, an
    untracked non-ignored file appears; it does NOT change for writes under an ignored dir
    or `.ai/local/`;
  - submodules (P9, fixture added with `git -c protocol.file.allow=always submodule add`,
    containing a committed file): snapshot equal when nothing changes; it changes when the
    submodule HEAD moves, a submodule file is overwritten, or an already modified submodule
    file is overwritten again;
  - template ci-setup passes `bash -n`, still installs nothing, contains both keywords.

### Validation
Targeted: `python3 -m unittest discover -s tests -k deps_status` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Done 2026-10-06. scripts/lib/workflow.py: `deps_spec`, `deps-status`, `deps-record`,
`tree-snapshot` (+ `checkout_root`). Declarations are lines starting `# ai-deps-inputs:` /
`# ai-deps-outputs:` (`^# ?ai-deps-…`; indented example lines in the template do not count);
inputs may be paths, globs or directories (every file below); missing declared inputs are
simply absent from the map, so adding them makes it stale. Missing `.ai/ci-setup` → error.
Stale reasons: `no dependency stamp (.ai/local/deps.json)`, `unreadable dependency stamp …`,
`.ai/ci-setup changed`, `inputs changed: added/removed/changed <path>`, `missing output <dir>`.
`tree-snapshot` hashes `git rev-parse HEAD`, `git diff --cached --binary`, and each
`ls-files --cached --others --exclude-standard` path (kind, st_mode, content sha / link
target / missing marker) except `.ai/local/`; gitlinks and untracked nested repos are
snapshotted recursively (uninitialised → marker). Template ci-setup: comment lines only.
Tests: 7 `deps_status` tests (declared, defaults, no lockfiles, outside paths, tree snapshot,
submodules, template). Evidence: `-k deps_status` Ran 7 OK; `.ai/bin/ai-check` Ran 195 OK.

## T002 — ai-run installs dependencies before its first task (FL-01)
Status: DONE
Dependencies: T001
Model: opus

### Goal
FL-01: a fresh worktree or a stale install no longer stops the run (2026-10-05 23:06): at the
start of every `ai-run` invocation that will run a task, the host (never an agent session)
runs `.ai/ci-setup` when `deps-status` says stale.

### Implementation notes
scripts/lib/common.sh `ai_deps EXPECTED_GATE LIMIT`: `deps-status`; current → return 0.
Else print `Dependency setup (.ai/ci-setup): <reason>`; `before=$(ai_helper tree-snapshot)`;
run `timeout --signal=TERM --kill-after=10s "$LIMIT" bash .ai/ci-setup < /dev/null` with
output to `.ai/local/deps-XXXXXXXX.log` (ignored) and a short summary on the terminal; no
write to any tracked file (no run-log line: P1). Then require: exit 0 (else message
"Dependency setup (.ai/ci-setup) failed (exit N[, timeout after Ns]); see <log>"),
`ai_guard_digest` equal to EXPECTED_GATE, `tree-snapshot` equal to `before` (else
"Dependency setup changed project files (.ai/ci-setup must only install ignored
dependencies); see <log>"); only then `deps-record`. The gate and snapshot checks run after
EVERY installer exit, successful or not, and a preservation violation is reported in
preference to the exit status (P8). On failure print the message and
return 1 (callers decide: ai-run uses `ai_die`; recovery escalates, T003). Limit:
`AI_DEPS_TIMEOUT` (plain environment variable, default 1200 s), capped by the run's
remaining time (`remaining_time` in ai-run; a non-positive remainder stops before running).
Recovery category (P8): every dependency-setup stop message starts with "Dependency setup";
scripts/ai-recover's hard-rule `case` (~line 102) gains `*'Dependency setup'*`, so these
stops always escalate before any recovery decision or checkpoint (never `commit_and_rerun`
or `rerun`).
scripts/ai-run: after the start checks (clean tree, gate approved) and before the loop, when
`tasks next` is not `none` (a task will run): `ai_deps "$AI_APPROVED_GATE" "$limit" ||
ai_die "$(cat .ai/local/last-error …)"` (or equivalent). Not in `--triage`, not later in the
loop, not before later gates. Scope limit (P3): dependencies changed by a task mid-run are
NOT installed by this run; that task's in-session gate failure follows the existing rules
(it can't be DONE without a passing gate). The next `ai-run` start (pipeline restart or
resume) or recovery validation (T003) installs them. No prompt change claims otherwise.
Flow chart (same task): vault `agents-flow.md` gets a host step "dependencies (.ai/ci-setup)
if missing/stale" at the start of implementation, with its ⛔ stop; bump `updated:`.

### Likely affected modules
scripts/lib/common.sh, scripts/ai-run, scripts/ai-recover, tests/test_workflow.py,
vault agents-flow.md

### Acceptance criteria
- Tests named `deps_runner` (fixture ci-setup declares `# ai-deps-inputs: deps.lock` and
  `# ai-deps-outputs: vendor-deps`, creates the git-ignored `vendor-deps/` and appends to a
  call log outside the checkout):
  - `ai-run --approved`: ci-setup runs once before the first mock claude call (the mock
    checks `vendor-deps/` exists), stamp written, no tracked file changed by the install;
    a second `ai-run` with unchanged inputs does not run it;
  - ci-setup exits 1, or times out (`AI_DEPS_TIMEOUT=1`, it sleeps) → `ai-run` exits 1 before
    any mock claude call; last-error names `.ai/ci-setup` and the log; no stamp;
  - ci-setup overwriting a tracked file, creating a non-ignored file, or committing a
    tracked change → stop "changed project files", no stamp, no claude call (P2); the same
    when it changes a file AND exits 1 (the violation is reported, P8);
  - run-time cap (P11): `--run-timeout 5`, `AI_DEPS_TIMEOUT=600`, an installer that sleeps
    60 s → `ai-run` exits 1 within the run budget (well under the 25 s test timeout), no
    stamp, no mock claude call;
  - auto-recovery (P8, `ai-pipeline --approved` with `AI_AUTO_RECOVER=1`): a fail-once
    installer (exits 1 on the first call only) and a change-once installer (modifies a
    tracked file on the first call only) → each escalates ("STOPPED, needs you" naming
    dependency setup); no recovery Claude call (`recover-calls` absent), no recovery
    checkpoint commit, no implementation session, no PR (`gh` log has no `pr create`);
  - queue already complete (`tasks next` = none) → ci-setup not run;
  - end to end (P1): `ai-pipeline --approved` on a fresh checkout with a stale stamp, a
    successful installer, mock codex clean review, bare origin and mock gh → install runs
    before the first task, the run finishes and opens the PR, `git status` clean at the end.
- Existing ai-run/pipeline tests pass (their template ci-setup runs once, harmlessly).
- Vault flow chart shows the dependency step; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k deps_runner` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Done 2026-10-06. scripts/lib/common.sh `ai_deps GATE LIMIT`: returns 1 with `AI_DEPS_ERROR`
set (callers print it: ai-run `ai_die "$AI_DEPS_ERROR"`; T003 can reuse it). Order after
every installer exit: gate digest ("…changed the approved workflow gate"), tree snapshot
("Dependency setup changed project files …"), exit status ("failed (exit N[, timeout after
Ns])"), then `deps-record`. A `deps-status` error (bad declaration) or a non-positive limit
also stops with a "Dependency setup" message. Log `.ai/local/deps-XXXXXXXX.log`; terminal
gets the stale reason, then "Dependencies installed in Ns" or the log's last 5 lines.
scripts/ai-run: after the triage block, before the loop, only when `tasks next` ≠ none;
`AI_DEPS_TIMEOUT` must be 1–7 digits, capped by `remaining_time`; usage text mentions it.
scripts/ai-recover: hard rule `*'Dependency setup'*`. Docs: README CI section,
docs/workflow.md; vault agents-flow.md (deps node + ⛔ stop, note, recovery hard rule).
Tests: 7 `deps_runner` tests (installs once + reinstall on lock change; fail/timeout/
overwrite/untracked/commit/overwrite+fail; run-time cap + invalid timeout; complete queue;
fail-once and change-once recovery escalate; pipeline end to end). Mock claude gained
`MOCK_REQUIRE`. Evidence: `-k deps_runner` Ran 7 OK; `.ai/bin/ai-check` Ran 202 OK (579 s,
close to the 600 s tool limit).

## T003 — Recovery installs dependencies before its validation (FL-01)
Status: DONE
Dependencies: T002
Model: opus

### Goal
FL-01, recovery part (P4): `ai-recover`'s `commit_and_rerun` validates leftover work with
`ai-check`; when a lockfile changed, it must install first so valid work isn't escalated.

### Implementation notes
scripts/ai-recover `commit_and_rerun` (~line 159): before `"$AI_BIN/ai-check"`, run
`ai_deps "$approved_gate" "${AI_DEPS_TIMEOUT:-1200}"` (the tree is dirty here; the
`tree-snapshot` check from T001/T002 covers dirty trees). On failure `escalate "$why; but
dependency setup failed: <message>." 'inspect .ai/ci-setup and the log, then rerun
ai-pipeline.'`. Attempt reservation, hard rules, the gate comparisons and the checkpoint
integrity checks (`stamp verify`, `committed-matches-worktree`) stay unchanged and in order.
A dependency-setup stop that reaches ai-recover escalates via the hard rule added in T002.
Flow chart (same task): the recovery diagram's `commit_and_rerun` branch notes "installs
dependencies if stale, then the full gate"; bump `updated:`.

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `deps_recovery` (`AI_AUTO_RECOVER=1`, MOCK_RECOVER=commit_and_rerun, an
  approved run, uncommitted leftover work that changes `deps.lock`; `.ai/validate` passes
  only when `vendor-deps/` matches `deps.lock`):
  - recovery runs ci-setup, the gate passes, the recovery checkpoint commit exists and
    verifies, the pipeline resumes; attempt counter incremented once;
  - ci-setup fails → escalation notification naming dependency setup; no commit; no resume;
  - ci-setup changes a project file → escalation "changed project files"; no commit.
- Existing `recover` tests pass.
- Vault recovery diagram updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k deps_recovery` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Done 2026-10-06. scripts/ai-recover `commit_and_rerun`: after the dirty-tree check, before
`ai-check`, `ai_deps "$approved_gate" "${AI_DEPS_TIMEOUT:-1200}"`; failure escalates
"$why; but dependency setup failed: $AI_DEPS_ERROR." / 'inspect .ai/ci-setup and the log,
then rerun ai-pipeline.' Gate comparisons and checkpoint integrity checks unchanged and in
order. Tests: 3 `deps_recovery` (install + gate + checkpoint + resume, attempt 1/2; fail-later
and change-later installers escalate with no commit, no resume, deps.lock still dirty); mock
ci-setup gained `fail-later`/`change-later`. Docs: README CI paragraph, docs/workflow.md
(deps section + recovery paragraph); vault flow chart recovery diagram + hub log.
Evidence: `-k deps_recovery` Ran 3 OK; `-k recover -k deps_runner` Ran 30 OK;
`.ai/bin/ai-check` Ran 205 OK (555 s).

## T004 — PR body and notification split "Needs you" from automated checks (FL-09)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
FL-09, runtime part: the PR says exactly what Zack must check by hand; automated fault
injections are listed separately with their test names (PR #14 listed 10 automated steps
as manual).

### Implementation notes
scripts/lib/workflow.py: `manual_testing(handoff)` returns `(needs_you, automated, legacy)`
from "Manual testing for the human": subsections `### Needs you` and `### Covered by
automated tests`; without them the whole section is "needs you" (legacy). `pr_body`: the
"How to test" section renders `### Needs you` first ("None — everything below is automated"
when None/empty), then `### Covered by automated tests` inside `<details><summary>N
automated checks</summary>`; a bullet without a backticked name gets " ⚠ no test named".
`finish_summary`: counts only needs-you steps: "Test: N manual step(s) in the PR", or
"Nothing to test by hand (N automated checks in the PR)" when None; legacy unchanged.
Flow chart (same task): the PR/FINISHED part says the PR separates "Needs you" from
automated checks and the notification counts only "Needs you"; bump `updated:`.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `manual_testing_render`:
  - pr-body: needs-you steps appear before the automated list; automated list inside
    `<details>` with its count; an automated bullet without a backticked name is flagged;
  - "None" under Needs you → PR says so; finish-summary says "Nothing to test by hand (N
    automated checks in the PR)" and does not count automated steps;
  - legacy handoff (no subsections) → output identical to today's (existing tests unchanged).
- Existing `finish_summary` and `pr_body` tests pass.
- Vault flow chart updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k manual_testing_render` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
`manual_testing()` added; `pr_body` and `finish_summary` use it (legacy output unchanged).
`manual_testing_render` Ran 4 OK; `.ai/bin/ai-check` Ran 209 OK (564 s). Vault flow chart
(PR and FINISHED nodes, notification table) updated; `updated:` was already 2026-10-06.

## T005 — Prompts and templates describe the "Needs you" split (FL-09)
Status: DONE
Dependencies: T004
Model: sonnet

### Goal
FL-09, guidance part: agents write the two-part section that T004 renders.

### Implementation notes
`templates/.ai/handoff.md`: "Manual testing for the human" with `### Needs you` and
`### Covered by automated tests` and short comments. Prompts: runner.md and triage.md (keep
the shared "How to work here" section identical), fix-review.md, review.md ("Manual testing
recommendations": what a human must check vs what is or should be an automated test);
templates/CLAUDE.md (~line 75) and templates/AGENTS.md (~line 29). Rule text: "Needs you"
only for things a human must do (look and feel, phone/real devices, live accounts, external
services, decisions) or "None"; every step reproducible by a test goes under "Covered by
automated tests" with its test name in backticks. No flow-chart change (T004 covers the
visible behaviour).

### Likely affected modules
templates/.ai/handoff.md, templates/.ai/prompts/{runner,triage,fix-review,review}.md,
templates/CLAUDE.md, templates/AGENTS.md, tests/test_workflow.py

### Acceptance criteria
- Tests named `manual_testing_prompts`: handoff template has both subsections; runner,
  triage, fix-review, review prompts and the CLAUDE.md/AGENTS.md templates mention "Needs
  you" and "Covered by automated tests"; runner/triage "How to work here" sections still
  identical (`tool_contract` tests pass); a fresh `setup-project` handoff renders through
  `pr-body` without error.
- Existing `tool_contract` and template tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k manual_testing_prompts` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
DONE. Handoff template, runner/triage/fix-review/review prompts, review template, and
templates CLAUDE.md/AGENTS.md describe "Needs you" vs "Covered by automated tests"; shared
"How to work here" untouched. Tests `manual_testing_prompts` (2) added. Targeted run with
`tool_contract`: Ran 5 tests OK; `.ai/bin/ai-check`: Ran 211 tests OK.

## T006 — Watchdog timer at setup, start warning, PID-based waits (FL-07)
Status: DONE
Dependencies: none
Model: sonnet

### Goal
FL-07: every checkout that runs a pipeline has its watchdog timer, missing timers are
visible at start, and documented waits loop on a PID (two `pgrep -f` waits died on
2026-10-05/06 by matching themselves).

### Implementation notes
scripts/lib/watchdog.py: `--timer-status` (mutually exclusive with install/uninstall), using
the same unit-name logic as `timer()` (factor out `unit_name(root)`). Defined check (P10):
`installed <timer>` (exit 0) only when both unit files exist AND `systemctl --user
is-enabled <timer>` prints `enabled` AND `systemctl --user is-active <timer>` prints
`active`; `missing <timer> (<reason>: no unit files / not enabled / not active)` (exit 1)
otherwise; `unknown <timer> (<reason>)` (exit 2) when systemctl is unavailable or errors
for another reason. scripts/lib/workflow.py
`setup`: new `--watchdog` (not with `--dry-run`/`--upgrade`): after a successful install run
`<root>/.ai/bin/ai-watchdog <root> --install-timer --diagnose --recover` (stdin /dev/null);
a failure exits non-zero with its output ("files were installed; the timer was not"). Without
the flag, the final message adds "Next: install the watchdog timer: .ai/bin/ai-watchdog
--install-timer --diagnose --recover". scripts/ai-pipeline at start: if `ai-watchdog
--timer-status` exits 1, print "No watchdog timer for this checkout; …" and append
"(no watchdog timer for this checkout)" to the STARTED/RESUMED notification; exit 2 →
"(watchdog timer status unknown)" likewise; never stop.
README: "Waiting for a run" (coordinator/scripts): wait on the pipeline PID
(`while kill -0 "$pid" 2>/dev/null; do sleep 60; done`, or `.ai/local/pipeline.active`
contents), never `pgrep -f <pattern>` loops (the loop's own command line matches); remove
the timer with `--uninstall-timer` before deleting a worktree. Test (P6): no executable
`pgrep -f` wait in scripts/ and templates/ (shell/python code; docs may explain the
pitfall), and README contains the PID-based example and the self-matching warning. Vault `agents-human-todo.md`: add one open item
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
  - `--timer-status` (mock systemctl answering is-enabled/is-active): `missing` exit 1
    before install; `installed` exit 0 after a full install; unit files present but
    `enable --now` failed (partial install) → `missing … not enabled`; enabled but stopped
    → `missing … not active`; systemctl absent from PATH → `unknown` exit 2 (P10);
  - ai-pipeline with a missing/partial/stopped timer prints the warning and the STARTED
    notification carries the note; a recovery resume's RESUMED notification carries it too;
    unknown status → "(watchdog timer status unknown)"; the run continues in every case;
  - no `pgrep -f` in executable files under scripts/ and templates/; README has the
    `kill -0` example and the warning that `pgrep -f` waits match themselves.
- Existing watchdog tests pass.
- Vault flow chart and human-todo updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k watchdog_setup` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Done. `--timer-status` (unit_name/units_dir factored out), `setup-project --watchdog` and the
"Next" line, ai-pipeline start warning plus STARTED/RESUMED note, README "Waiting for a run".
`python3 -m unittest discover -s tests -k watchdog_setup`: Ran 11 tests, OK. `.ai/bin/ai-check`:
Ran 222 tests, OK (590 s). Vault flow chart (updated 2026-10-06), hub Log and human-todo item
done. Limit: the real systemd path is only exercised through a mock systemctl.

## T007 — Final docs audit for batch 2
Status: DONE
Dependencies: T001, T002, T003, T004, T005, T006
Model: haiku

### Goal
README, docs/workflow.md and the vault notes describe batch 2 accurately; the PR carries
the flow-chart line and the two-part manual testing section.

### Implementation notes
Cross-check against the code and the T001–T006 results: docs/workflow.md (dependency step:
when it runs (start of `ai-run`, recovery validation), inputs/outputs, declaration lines,
stamp, timeout, snapshot check, stops, the limit that dependencies changed mid-run install at
the next start, the risk that ci-setup runs package-manager code on the host; Needs you vs
automated; timer status/warning; waits), README (CI section ~line 374: the host also runs
`.ai/ci-setup`; modes table and setup steps if affected; `AI_DEPS_TIMEOUT`). Add
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

## T008 — Tree snapshot covers uninitialised submodule paths (review M1)
Status: DONE
Dependencies: T001, T002
Model: opus

### Goal
Codex review M1: `tree_snapshot` (scripts/lib/workflow.py ~1627) records every gitlink
without `.git` as the constant `uninitialised`, before its symlink/file checks. An installer
that creates or overwrites files under an uninitialised submodule path, or replaces it with a
symlink, leaves the snapshot unchanged, so FL-01's "installer changed no project file" check
passes and the stamp is recorded.

### Implementation notes
Determine the real kind first: a symlink at a gitlink/nested-repo path is recorded as `link`
plus its target (never followed); an initialised repository recurses as today; an
uninitialised gitlink directory records its mode plus a recursive filesystem walk of its
contents (relative path, kind, mode, bytes or link target; symlinks not followed); a
non-directory file at that path records `file` with bytes; absence records `missing`. Git
reports no untracked files under a gitlink path, so the walk must be filesystem-based; no
ignore rules apply inside (an uninitialised submodule should be empty). Keep the docstring
accurate. Prefer direct `tree-snapshot` calls in tests over full runner fixtures: the gate is
already near the 600 s session limit; at most one runner-level regression.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `tree_snapshot_uninitialised_submodule`: with a real repository containing a
  committed but uninitialised gitlink, the snapshot changes when a file is created inside the
  path, when an existing file there is overwritten, when its mode changes, and when the
  directory is replaced by a symlink; it is unchanged when nothing is touched.
- One runner regression: an installer that creates a file inside an uninitialised submodule
  path (exit 0 and exit 1) stops with "Dependency setup changed project files" and records no
  stamp.
- Existing `deps_status` / `deps_runner` / `deps_recovery` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k tree_snapshot_uninitialised_submodule` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Done 2026-10-07. `tree_snapshot` now uses `snapshot_path` (link target / file mode+bytes /
dir mode / missing, symlinks never followed); a gitlink or nested-repo path that is not an
initialised repository directory records `uninitialised` plus a filesystem walk of its
contents. Tests: `test_tree_snapshot_uninitialised_submodule` (create, overwrite, chmod,
nested dir and symlink, dir mode, replaced by symlink, by file, removed; untouched equal) and
`test_deps_runner_installer_writing_into_uninitialised_submodule_stops` (exit 0 and 1: stop
"Dependency setup changed project files", no `deps.json`). Targeted: Ran 1 test OK. Gate:
`.ai/bin/ai-check` PASS, 224 tests in 611 s. Limitation: the gate now exceeds the 600 s Bash
tool limit; it was auto-moved to the background and completed with exit 0.

## T009 — Dependency outputs must be directories (review N2)
Status: IN_PROGRESS
Dependencies: T001
Model: sonnet

### Goal
Codex review N2: `deps_status` (scripts/lib/workflow.py ~1588) treats any existing path as
a present output, so a regular file or a broken symlink at `node_modules` reports `current`.

### Implementation notes
Use `is_dir()` for declared outputs; report `stale missing output <p>` when absent and
`stale output <p> is not a directory` when something else is there (a symlink to a directory
counts as present). Unit-level tests only (no runner fixtures).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md (only if it describes the
output check)

### Acceptance criteria
- Tests named `deps_status_output_kind`: matching stamp with a regular file at the output →
  stale "not a directory"; broken symlink → stale; symlink to a directory → current; real
  directory → current.
- Existing `deps_status` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k deps_status_output_kind` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T010 — Wrapped automated test bullets are not flagged; FINISHED count regression (review N1)
Status: TODO
Dependencies: T004
Model: sonnet

### Goal
Codex review N1: `pr_body` (scripts/lib/workflow.py ~1896) checks only a bullet's first
physical line for a backtick, so this branch's own handoff gets five false "⚠ no test named"
warnings for test names on continuation lines; a lone backtick also passes. Also add the
missing plan-review P12 regression (FINISHED counting with both subsections populated).

### Implementation notes
Group the automated section into list items (a bullet line plus its indented continuation
lines); flag an item unless it contains a nonempty paired backtick span (e.g.
`` `[^`\n]+` `` across the joined item). Append the warning to the item's last line so the
Markdown stays valid. Item count logic unchanged. Unit-level tests only.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `manual_testing_wrapped`: a bullet whose test name is on a continuation line
  gets no warning; an unnamed bullet and a bullet with an unmatched single backtick are
  flagged; the count of automated checks is unchanged; rendering this repo's own
  `.ai/handoff.md` flags only bullets that truly name no test.
- A `finish_summary` test with two "Needs you" steps and three automated checks reports
  "Test: 2 manual step(s)" (P12).
- Existing `manual_testing_render` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k manual_testing_wrapped` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.
