# Spec: Run flow batch 2: FL-01, FL-07, FL-09

## Objective
Run flow batch 2: FL-01, FL-07, FL-09
Remove the avoidable stops and the misleading human work seen in the overnight runs of
2026-10-05/06: install dependencies on the host before tasks run (FL-01), make waits and the
watchdog reliable (FL-07), and make the PR say what really needs Zack (FL-09).

Source: vault [[agents-backlog]] "Run flow improvements (approved by Zack 2026-10-06)",
items FL-01, FL-07, FL-09 (approved; first batch after OR-01/OR-02, merged as PR #14).
Trimmed 2026-10-06 to high-impact, low-investment work: FL-03 (review convergence) was
dropped from this batch and stays in the backlog, not started.
Planned by Claude as Zack's delegate on 2026-10-06; the pipeline's Codex plan review gates it.
Hub decisions respected: risk-based models with no usage-saving downgrades (2026-10-06),
roles vs providers, AD-5 (the watchdog only observes), "auto-recovery never changes the gate"
(gate files such as `.ai/ci-setup` are run, never edited), "don't break my system".

## Requirements
- **FL-01 Dependencies before tasks (host), kept small** (revised after the plan review).
  The host, never an agent session, runs the project's `.ai/ci-setup` when dependencies are
  missing or stale at exactly two points: the start of every `ai-run` invocation that will
  run a task (so every pipeline start, resume and fix round), and in `ai-recover`'s
  `commit_and_rerun` before its validation. Staleness is generic, not npm-specific:
  - inputs: files declared by a comment line in `.ai/ci-setup`
    (`# ai-deps-inputs: package-lock.json …`), else a documented default list of well-known
    lockfiles (package-lock.json, npm-shrinkwrap.json, pnpm-lock.yaml, yarn.lock, bun.lock,
    bun.lockb, requirements*.txt, poetry.lock, uv.lock, Pipfile.lock, Gemfile.lock, go.sum,
    Cargo.lock, composer.lock) that exist at the repo root;
  - outputs: directories declared by `# ai-deps-outputs: node_modules …`, else `node_modules`
    when `package.json` exists; a missing output is stale;
  - a stamp `.ai/local/deps.json` records the SHA-256 of `.ai/ci-setup` and of every input;
    any difference, or no stamp, is stale (also with no inputs at all: a configured
    installer without lockfiles runs once).
  Running it: stdin `/dev/null`, a timeout (`AI_DEPS_TIMEOUT` environment variable, default
  1200 s, bounded by the run's remaining time, tested), output only to the ignored
  `.ai/local/deps-*.log` and the terminal; nothing tracked is written. Failure or timeout
  stops ("Dependency setup (.ai/ci-setup) failed …; see <log>"; recovery escalates). After
  it the gate digest must be unchanged and a project-tree snapshot (HEAD, index, and the
  path, kind, mode and bytes of every non-ignored file, tracked or untracked, excluding
  `.ai/local/`; submodules included recursively) must equal the one taken before, also after
  a failed installer run, else stop ("changed project files"); the stamp is recorded only
  after these checks. Every dependency-setup stop starts with "Dependency setup" and is a
  hard escalation in `ai-recover` (never auto-recovered). `.ai/ci-setup` contents are never changed by the
  toolkit run; the ci-setup template only gains comment lines documenting the declaration
  lines (one npm example).
  Not in scope: installing dependencies a task changes mid-run (that task's in-session gate
  failure follows the existing rules; the next `ai-run` start or recovery validation
  installs them), installs before every gate, ai-pipeline's own validation step.
- **FL-07 Reliable waits.** `setup-project --watchdog` (opt-in) installs the timer after a
  successful install (`ai-watchdog <root> --install-timer --diagnose --recover`); without it
  setup prints the command as the next step. `ai-watchdog --timer-status` reports whether this
  checkout's timer is installed (both unit files, enabled and active per `systemctl --user`;
  otherwise missing, or unknown when systemd can't be asked); `ai-pipeline` warns at start
  (terminal and the STARTED/RESUMED notification) when it is missing or unknown, never
  failing the run. README documents PID-based waits
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
FL-02, FL-03, FL-04, FL-05, FL-06, FL-08; validation-candidate suggestions for ci-setup; changing `.ai/ci-setup`, `.ai/validate` or other gate files
of this repo; package-manager-specific logic beyond the default lists; automatically removing
timers of deleted worktrees; enforcing test-name existence (only the presence of a name).

## Acceptance
- FL-01: a fixture project whose ci-setup creates a declared output runs it once at the
  start of `ai-run` (mock agent sees the output), not again while inputs are unchanged;
  failure/timeout stops before any agent session with the log path; a ci-setup that
  overwrites an already modified file, creates a non-ignored file or commits stops without a
  stamp; a full pipeline with a stale stamp finishes with a clean tree and a PR; recovery
  installs changed dependencies before its validation and commits valid leftover work; the
  template ci-setup documents the declaration lines and still installs nothing.
- FL-07: `setup-project --watchdog` installs the timer (mock systemctl); setup without it
  prints the command; pipeline start without a timer warns and continues.
- FL-09: pr-body/finish-summary tests for the split, None, flagged bullets and legacy handoffs.
- New tests in `tests/test_workflow.py`; all existing tests pass; `.ai/validate` passes.
