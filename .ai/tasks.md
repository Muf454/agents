# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files (this repo's `.ai/ci-setup` included). This run is
started with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` (absolute path) so the
vault flow chart, hub Log and human todos can be updated. Source: vault backlog "Run flow
improvements (approved by Zack 2026-10-06)", FL-01, FL-03, FL-07, FL-09. Every task leaves
`.ai/bin/ai-check` passing. Flow-chart rule (AGENTS.md, CLAUDE.md): every task that changes
workflow behaviour updates the vault `agents-flow.md` (diagram/notes and its `updated:`
frontmatter date) in the SAME task; T007 is only the final docs audit.

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
Flow chart (same task): vault `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`: a host step
"dependencies (.ai/ci-setup) when missing/stale" before each task and before the checks,
with its ⛔ stop; bump `updated:`.

### Likely affected modules
scripts/lib/workflow.py, scripts/lib/common.sh, scripts/ai-run, scripts/ai-pipeline,
scripts/ai-recover, templates/.ai/prompts/runner.md, tests/test_workflow.py, vault agents-flow.md

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
- Gate files never modified (existing guard tests pass); all existing tests pass.
- Vault flow chart shows the dependency step; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k deps_setup` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T002 — ci-setup template and setup-project suggest dependency declarations (FL-01)
Status: TODO
Dependencies: T001
Model: sonnet

### Goal
FL-01, template part: new projects learn how the host decides when to run `.ai/ci-setup`
and get a concrete suggestion for their ecosystem.

### Implementation notes
templates/.ai/ci-setup: keep the default "installing nothing" behaviour; add comments that
the host runs this file before tasks when dependencies are missing or stale, with the
declaration lines `# ai-deps-inputs:` / `# ai-deps-outputs:` (examples for npm, pnpm, Python
venv) and the defaults when absent; it must only install ignored dependencies (never edit
tracked files). `candidates()` in scripts/lib/workflow.py (`.ai/validation-candidates.md`):
add a "Dependencies (.ai/ci-setup)" section per detected ecosystem (npm/pnpm/yarn/bun from
the lockfile: `npm ci` etc.; Python: venv + pip install -r; Rust/Go: `cargo fetch`,
`go mod download`) with the matching declaration lines. README (CI section ~line 374): the
host also runs `.ai/ci-setup` before tasks (link to docs/workflow.md for details; T007
audits). `setup-project --upgrade` treats ci-setup as project-owned (unchanged; its template
change shows as advice).

### Likely affected modules
templates/.ai/ci-setup, scripts/lib/workflow.py, README.md, tests/test_workflow.py

### Acceptance criteria
- Tests named `deps_template`: the template ci-setup passes `bash -n`, still installs
  nothing, and contains both declaration keywords; `deps-status` on a fresh setup with the
  template ci-setup and no lockfiles is `current` after one run; candidates for a pnpm
  fixture suggest `pnpm install --frozen-lockfile` with `# ai-deps-inputs: pnpm-lock.yaml`;
  for a Python fixture a venv command; upgrade preview lists ci-setup as advice only.
- Existing setup/upgrade tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k deps_template` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T003 — Review history and recurring areas (FL-03, host side)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
FL-03 detection: from the verified reviews recorded on the branch, find areas (files) that
had a BLOCKER/MAJOR finding in each of the last 3 consecutive reviews. Read-only helpers;
shown in the PR body.

### Implementation notes
scripts/lib/workflow.py:
- `review_history(base)`: commits in `base..HEAD` that change `.ai/reviews/current.md`
  (`git log --reverse --format=%H base..HEAD -- .ai/reviews/current.md`); for each, the report
  blob at that commit; keep it only if it has `Host evidence: HEAD <sha>` and its SHA-256
  equals the binding `binding_dir()/<sha>.sha256` (else skip and count as unverified);
  collapse consecutive identical digests. Per report: BLOCKER and MAJOR ids (`finding_ids`)
  and text (`finding_text`); areas = path-like tokens in the finding text (e.g.
  `src/lib/merge.ts:42`, backticked or not; strip `:line[-line]`) that are tracked files at
  the reviewed HEAD (`git ls-tree -r --name-only <sha>`).
- `recurring_areas(base, rounds=3)`: areas present in each of the last `rounds` verified
  reviews (the newest is the current one); returns `[(area, [ids per review])]`.
- Helper commands `review-history [BASE]` and `recurring-areas [BASE]` (BASE defaults to
  `$AI_DISPUTES_BASE`; none → empty output). Output `area<TAB>3<TAB>M1,M2;M1;B1`.
- `pr_body`: under "Independent review", when recurring areas exist add "Recurring areas
  (BLOCKER/MAJOR in the last 3 reviews): `path` (ids)…, a design-level fix is recommended".
No triage behaviour change here (T004). No flow-chart change needed beyond T004's.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `review_convergence` (fixture: three host-published reviews committed on a
  branch via the real publish path or `publish-review`, mock codex):
  - MAJOR findings naming `src/merge.ts:10` in all 3 → `recurring-areas` lists `src/merge.ts`
    with the ids per review;
  - only 2 reviews, or the middle review names a different file → nothing;
  - a non-existent path or a directory in the text is not an area; `:12-40` suffix stripped;
  - a historic report edited after recording (digest ≠ binding) is skipped (and a third
    review is then not enough);
  - reviews from before `base` (merged history) are not counted;
  - `pr-body` shows the recurring-areas line only when areas exist.
- Existing review/pr_body tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k review_convergence` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T004 — Triage switches to a design fix for recurring areas (FL-03)
Status: TODO
Dependencies: T003
Model: opus

### Goal
FL-03 rule: when an area recurs (T003), triage must not patch the symptom again: accepted
findings in that area need a design-level fix task with a short design note, enforced by
the host (live sync needed review rounds 2–7 for what one design change fixed).

### Implementation notes
scripts/ai-run `--triage`: before the session, `areas=$(ai_helper recurring-areas)`; when
non-empty, append to the prompt a "CONVERGENCE RULE" block: the areas, their finding ids
per review, and the instruction: for accepted findings in these areas write ONE design-level
fix task (title starting "Design:"), with a `### Design note` section (3–10 lines: what the
model/data structure lacks, the design change, why it removes the class of findings) and
`Model: opus` (same-area repeated failures fall under the opus retry rule); reference it from
those findings' rows; rejections still need evidence. `triage_check` with `--fresh`: for each
accepted row whose finding (in the current review) names a recurring area, every referenced
task must have a non-empty `### Design note` section and `Model: opus`; else fail
"Finding <id> is in recurring area <path> (<n> reviews): its fix task needs a Design note
and Model: opus". Without `AI_DISPUTES_BASE` (standalone ai-run) there is no history: rule
off, documented. Templates: triage.md and fix-review.md get the rule text (the host adds the
specifics); the task-format note mentions the optional `### Design note` section.
Flow chart (same task): the triage step notes the convergence rule (same file flagged in 3
reviews in a row → design note + design fix task); bump `updated:`.

### Likely affected modules
scripts/ai-run, scripts/lib/workflow.py, templates/.ai/prompts/triage.md,
templates/.ai/prompts/fix-review.md, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `convergence_triage` (three recorded reviews with a MAJOR in `src/merge.ts`,
  pipeline-style env with `AI_DISPUTES_BASE`):
  - the triage prompt (mock claude records it) contains "CONVERGENCE RULE" and `src/merge.ts`;
  - a triage mode that accepts with a plain task → `ai-run --triage` stops with the
    "recurring area" message; the round is not recorded (no `fix-rounds` record);
  - a mode that writes a "Design:" task with a `### Design note` and `Model: opus` → passes;
  - a rejected row with evidence passes; findings outside the area are not affected;
  - with two reviews only, the prompt has no CONVERGENCE block and plain tasks pass.
- Existing `triage_completion`, `fix_round_count`, `disputed_findings` tests pass.
- Vault flow chart triage step updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k convergence_triage` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T005 — "Needs you" vs "Covered by automated tests" in handoff and PR (FL-09)
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

## T006 — Watchdog timer at setup, start warning, PID-based waits (FL-07)
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

## T007 — Final docs audit for batch 2
Status: TODO
Dependencies: T002, T004, T005, T006
Model: haiku

### Goal
README, docs/workflow.md and the vault notes describe batch 2 accurately; the PR carries
the flow-chart line and the two-part manual testing section.

### Implementation notes
Cross-check against the code and the T001–T006 results: docs/workflow.md (dependency step:
inputs/outputs, stamp, timeout, stops, risk that ci-setup runs package-manager code on the
host; convergence rule and its limits; Needs you vs automated; timer status/warning; waits),
README (modes table and setup steps if affected, config keys incl. `AI_DEPS_TIMEOUT`). Add
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
- Docs describe only implemented behaviour; no FL-02/04/05/06 promises.
- Vault chart audited, hub Log line added; handoff flow-chart line and two-part manual
  testing present (every automated bullet names a test).

### Validation
Targeted: `python3 -m unittest discover -s tests -k docs_consistency` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.
