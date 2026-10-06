# Spec: Run flow batch 2: FL-01, FL-03, FL-07, FL-09

## Objective
Run flow batch 2: FL-01, FL-03, FL-07, FL-09
Remove the avoidable stops and the misleading human work seen in the overnight runs of
2026-10-05/06: install dependencies on the host before tasks run (FL-01), make triage switch
from symptom patches to a design fix when one area keeps failing review (FL-03), make
waits and the watchdog reliable (FL-07), and make the PR say what really needs Zack (FL-09).

Source: vault [[agents-backlog]] "Run flow improvements (approved by Zack 2026-10-06)",
items FL-01, FL-03, FL-07, FL-09 (approved; first batch after OR-01/OR-02, merged as PR #14).
Planned by Claude as Zack's delegate on 2026-10-06; the pipeline's Codex plan review gates it.
Hub decisions respected: risk-based models with no usage-saving downgrades (2026-10-06),
roles vs providers, AD-5 (the watchdog only observes), "auto-recovery never changes the gate"
(gate files such as `.ai/ci-setup` are run, never edited), "don't break my system".

## Requirements
- **FL-01 Dependencies before tasks (host).** `ai-run` and `ai-pipeline` (the host, never an
  agent session) run the project's `.ai/ci-setup` when dependencies are missing or stale:
  before the first task session, before every later task session and before every host
  `ai-check` (cheap no-op when current). Staleness is generic, not npm-specific:
  - inputs: files declared by a comment line in `.ai/ci-setup`
    (`# ai-deps-inputs: package-lock.json …`), else a documented default list of well-known
    lockfiles (package-lock.json, npm-shrinkwrap.json, pnpm-lock.yaml, yarn.lock, bun.lock,
    bun.lockb, requirements*.txt, poetry.lock, uv.lock, Pipfile.lock, Gemfile.lock, go.sum,
    Cargo.lock, composer.lock) that exist in the checkout;
  - outputs: directories declared by `# ai-deps-outputs: node_modules …`, else `node_modules`
    when `package.json` exists; a missing output is stale;
  - a stamp `.ai/local/deps.json` records the SHA-256 of `.ai/ci-setup` and of every input;
    any difference, or no stamp, is stale.
  Running it: stdin `/dev/null`, a timeout (`AI_DEPS_TIMEOUT`, default 1200 s, also bounded
  by the run's remaining time), output to `.ai/local/deps-*.log`, a run-log line. Failure or
  timeout stops with "Dependency setup (.ai/ci-setup) failed …; see <log>". Afterwards the gate
  digest must be unchanged and `git status` (incl. untracked, non-ignored) must equal its state
  before, else stop ("ci-setup changed project files"). `.ai/ci-setup` contents are never
  changed by the toolkit run; the template documents the declaration lines and
  `setup-project`'s validation candidates suggest them.
- **FL-03 Review convergence.** A host helper lists the BLOCKER/MAJOR findings of every
  verified review recorded on the branch (base..HEAD, oldest first; a report counts only if
  its SHA-256 matches its host binding) and maps each to areas = tracked file paths named in
  the finding (e.g. its Location line). An area is **recurring** when it has a BLOCKER/MAJOR
  finding in each of the last 3 consecutive reviews (current included). When areas recur,
  `ai-run --triage` adds a CONVERGENCE section to the triage prompt; for every accepted
  finding in a recurring area the referenced fix task must contain a non-empty
  `### Design note` section (what the model lacks, the design-level change) and
  `Model: opus`; `triage-check --fresh` enforces it. The PR body's review section lists
  recurring areas (so a run that stops at the fix-round limit still shows them).
- **FL-07 Reliable waits.** `setup-project --watchdog` (opt-in) installs the timer after a
  successful install (`ai-watchdog <root> --install-timer --diagnose --recover`); without it
  setup prints the command as the next step. `ai-watchdog --timer-status` reports whether this
  checkout's timer is installed; `ai-pipeline` warns at start (terminal and the STARTED
  notification) when none is, never failing the run. README documents PID-based waits
  (`while kill -0 "$pid"`) and why `pgrep -f` waits are wrong (they match themselves). No
  script uses `pgrep -f` waits today (verified); a test keeps it that way.
- **FL-09 What needs Zack.** The handoff's "Manual testing for the human" section has two
  subsections: `### Needs you` (only checks a human must do: look and feel on a phone, real
  devices, live accounts, decisions; or "None") and `### Covered by automated tests` (each
  developer-level step with its test name in backticks). The PR body's "How to test" shows
  "Needs you" first and the automated list after it; bullets without a backticked test name
  are flagged. The FINISHED notification counts only "Needs you" steps ("Nothing to test by
  hand" when None). A legacy handoff without the subsections is treated as before (all steps
  need the human). Runner, triage, fix-review and review prompts plus the CLAUDE.md/AGENTS.md
  and handoff templates describe the split.
- Each task that changes flow behaviour updates the vault `agents-flow.md` (diagram/notes and
  its `updated:` date) in the same task; a final task audits the docs.

## Non-goals
FL-02, FL-04, FL-05, FL-06, FL-08; changing `.ai/ci-setup`, `.ai/validate` or other gate files
of this repo; package-manager-specific logic beyond the default lists; automatically removing
timers of deleted worktrees; enforcing test-name existence (only the presence of a name).

## Acceptance
- FL-01: a fixture project whose ci-setup creates a declared output runs it once before the
  first task (mock agent sees the output), not again while inputs are unchanged, again after
  the lockfile changes; failure/timeout stops before any agent session with the log path;
  a ci-setup that touches a tracked file stops; gate files unchanged.
- FL-03: three recorded reviews with MAJOR findings in the same file make the triage prompt
  carry CONVERGENCE for that file and `triage-check --fresh` reject an accepted finding whose
  task lacks a Design note or `Model: opus`; two reviews, or different files, don't; an
  unverifiable historic report is ignored; the PR body lists recurring areas.
- FL-07: `setup-project --watchdog` installs the timer (mock systemctl); setup without it
  prints the command; pipeline start without a timer warns and continues.
- FL-09: pr-body/finish-summary tests for the split, None, flagged bullets and legacy handoffs.
- New tests in `tests/test_workflow.py`; all existing tests pass; `.ai/validate` passes.
