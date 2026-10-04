# Claude-led development toolkit

A reusable workflow for future software projects. This repository is **not an
application**. It installs Markdown instructions, persistent workflow records,
prompts, and a few Linux-native scripts into an existing Git project.

```text
Human + Claude: requirements, architecture, task plan  →  human approves the plan
  ai-pipeline (hands-off):
    Claude implements task by task (checks + Git checkpoint each)
    → full gate → Codex independent review → Claude triages + fixes (≤ N rounds)
    → push feature branch → open/update pull request → phone notification
  Human: test the PR (e.g. its preview deploy) → merge
```

**The human's two touch points are the plan and the pull request.** Everything in
between runs unattended, survives usage limits (it pauses until the reset), and
never merges or deploys.

Claude is the primary architect, planner, coder, debugger, and test author. Codex
challenges the implementation and looks for missed requirements, bugs, regressions,
security issues, and architectural problems. It implements only when explicitly
requested. Git provides checkpoints; `.ai/` provides durable state. Compilers,
tests, type checkers, lint, and builds provide deterministic evidence.

## Requirements

Linux (including Omarchy/Arch), Bash, Git, Python 3.10+, GNU `timeout`/coreutils,
and `flock` from util-linux. Claude Code and Codex CLI must be installed and
authenticated separately. `tmux` is recommended for unattended terminal sessions.
No services, Docker, SDKs, orchestration framework, or desktop changes are needed.

The scripts use current CLI flags. Check `claude --help` and `codex exec --help`
after upgrades. Validation needs the actual project's development tools. Setup
never installs dependencies, calls an AI model, or executes detected commands.

## Set up a project

For a new project, create a Git repository first. For an existing one, begin at
its repository root and inspect any uncommitted work.

```bash
mkdir -p ~/Projects/my-app
cd ~/Projects/my-app
git init -b main

# Inspect the proposed copies first (optional).
~/Projects/agents/scripts/setup-project --dry-run "$PWD"
~/Projects/agents/scripts/setup-project "$PWD"
```

Setup prints CREATE/KEEP entries, creates `.ai/`, copies the tools to `.ai/bin/`,
and adds local-log/local-settings exclusions to `.gitignore`. Existing files,
including CLAUDE.md, AGENTS.md, docs, Claude settings, and validation, are preserved.
If a KEEP file contains different guidance, reconcile it with the toolkit template
manually. Re-running setup fills missing files; it does **not** upgrade existing
copies. Symlinked workflow destinations are rejected before copying.

**Existing projects: KEEP does not mean the workflow instructions were merged.**
Setup warns when an existing CLAUDE.md or AGENTS.md lacks the toolkit's key
sections/markers. Merge the relevant guidance before planning or unattended work;
preserve existing project knowledge. Section detection is a heuristic, not proof
that similarly named sections implement the rules. Existing Claude settings are
also preserved: merge the new deny rules explicitly.

Review the installed files, then make a bootstrap checkpoint. Stage carefully if
this is an existing project; don't include unrelated work or credentials.

```bash
git add -- CLAUDE.md AGENTS.md docs .ai .claude/settings.json .gitignore
git commit -m "chore: add AI development workflow"
git switch -c feature/initial-project
```

For an existing project, use a descriptive feature branch instead. Save the
starting branch/commit as your review base. `main` works if it remains the baseline;
otherwise record `git rev-parse HEAD` before implementation and use that SHA.

## Plan a new project or large feature

Launch Claude with the planning prompt and your actual objective:

```bash
claude "$(cat .ai/prompts/plan.md)

User objective: <describe the whole project or large feature here>"
```

Claude inspects the real repository, proposes the simplest architecture, updates
the spec and plan, and creates dependency-ordered tasks with acceptance criteria
and validation. It asks only for critical ambiguities and does not start coding.
Tell it which scope is approved after inspecting the plan, and record that in
the plan's Authorization section. Planning and implementation are separate phases.

Before leaving an implementation session unattended:

1. Review `.ai/project-spec.md`, `.ai/current-plan.md`, and `.ai/tasks.md`.
2. Configure `.ai/validate` with **real** project commands. Read detected suggestions
   in `.ai/validation-candidates.md`; inspect scripts before executing them. The
   supplied validation placeholder deliberately fails with exit 78.
3. Add necessary local commands to `.ai/permissions.allow` after inspecting them.
   Use narrow tool entries such as `Bash(npm run test *)`; dependency installation
   may need an explicit permission entry. Do not give unrestricted Bash by default.
4. Run `.ai/bin/ai-check`. Record/fix any baseline failures rather than suppressing them.
5. Checkpoint the approved plan, validation, permissions, and task queue on the feature branch.

For example, in a project that really defines these package scripts:

```bash
# .ai/validate — example only, not an assumption about your project
#!/usr/bin/env bash
set -euo pipefail
npm run format:check
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

Adapt to the actual project, including integration tests where applicable. Missing
commands/test coverage must be visible. Do not create fake passing checks.

## Start autonomous implementation

For the recoverable bounded runner, start from a clean committed feature branch:

```bash
.ai/bin/ai-status
.ai/bin/ai-run --approved --sessions 16 --session-timeout 1800 --run-timeout 14400
```

`--approved` records your intent to implement the inspected plan using the inspected
permissions and checks. It does not authorize merge, deployment, or production
operations. There are no approval prompts between normal tasks. Claude's `dontAsk`
mode rejects unapproved tools, and the runner stops on reported permission denials
so you can adjust policy deliberately. This can block a legitimate command if it
wasn't allowed; a short supervised trial before an overnight run is useful.

At approval, the runner hashes `.ai/validate`, all `.ai/bin/` and `.ai/prompts/`
contents, the permission allowlist, and project Claude settings. It keeps the
baseline in shell memory, records a local inspection copy, and stops if protected
files change at session/check/checkpoint boundaries. Verification runs before
project-local helpers can execute. Edit/Write deny rules protect these gate paths;
needed gate changes require human inspection and a new approved run.

The runner selects one eligible task per fresh Claude invocation. Claude reads
state, reconciles interrupted work, marks IN_PROGRESS, implements, validates, records
results, marks DONE, and commits. The runner reruns the full gate, verifies a clean
checkpoint, records its own small state/log checkpoint, then starts the next session.
BLOCKED tasks can be bypassed only by independent tasks with satisfied dependencies.

No-progress, malformed state, CLI errors, denied permissions, timeouts, validation
failure, an unexpected branch change, or uncommitted work stop the runner. A task
marked DONE whose post-task validation fails is restored to IN_PROGRESS. Session
limits are deliberate boundaries; rerun the same command to continue after inspection.
The run-time budget bounds agent/check execution, with a 10-second termination grace;
ordinary Git bookkeeping/hooks also consume time. It is not a token/cost guarantee.

For an interactive Claude session that handles the whole queue itself:

```bash
claude "$(cat .ai/prompts/implement.md)"
```

Interactive Claude uses your normal permission configuration, so it may ask for
commands not yet authorized. The bounded runner is the no-prompt unattended path.

## Hands-off delivery: `ai-pipeline`

After the plan is approved, validation is configured, and the plan is checkpointed
on a feature branch, one command delivers it as a pull request:

```bash
tmux new -s my-app-ai
.ai/bin/ai-pipeline --approved --base main --model sonnet
```

1. **Implement**: `ai-run` works through the queue (fresh Claude session per task,
   gate after each task).
2. **Review**: once the queue is complete and validated, `ai-review` asks Codex for a
   read-only review. The review must contain `Finding counts: BLOCKER=n MAJOR=n MINOR=n`.
3. **Fix**: with BLOCKER/MAJOR findings, `ai-run --triage` has Claude record one
   row per finding in `.ai/reviews/dispositions.md` (accepted with a fix task,
   rejected with evidence, or deferred) and append fix tasks. Triage may only touch
   workflow records; the host validates that every significant finding has a valid
   disposition. The new tasks are implemented, and Codex reviews again. At most
   `--max-fix-rounds` rounds (default 2). Codex's report is never edited by Claude:
   the runner stops if any session changes `.ai/reviews/current.md`, and a report
   whose counts disagree with its listed finding IDs is rejected.
4. **Pull request**: pushes the feature branch (never with force; never `main`) and
   opens or updates a PR with the summary, tasks, validation evidence, review result,
   and the handoff's manual test steps. Unresolved or deferred significant findings
   make it a **draft** (an existing PR is converted). The PR targets `--pr-base`,
   inferred from `--base` when that is a local or `origin/` branch, otherwise
   required. Without an `origin` remote or `gh`, it stops at a ready local branch.
5. **Notify** at start, pause, stop, and PR (`AI_NOTIFY_CMD`, see below).

Rerunning `ai-pipeline --approved` resumes where it stopped: finished tasks aren't
redone, a review is reused while only workflow records changed since it, completed
dispositions for that review are reused, validation is re-verified before
publishing, and an existing PR is updated instead of duplicated. The pipeline holds
the checkout lock for its whole run and re-verifies the gate after each of its own
commits. `--no-pr` stops after the review;
`--draft` always opens a draft. The pipeline keeps its own gate digest across steps.

### Usage limits

A Claude or Codex usage/rate-limit failure doesn't end the run. The scripts read
the reset time from the error (or wait `AI_LIMIT_RETRY`, default 1800 s), notify,
sleep, and retry the same step. Total waiting per command is capped by
`AI_LIMIT_MAX_WAIT` (default 28800 s); a weekly limit beyond that stops with a
notification so you can rerun after the reset. Pauses are logged in the ignored
`.ai/local/pauses.log`. Most usage is Claude's (implementation); Codex mostly reviews.

### Models

`--model NAME` (or `AI_MODEL`) picks the Claude model for implementation and triage.
A task may override it with an optional line under its `Dependencies:` line, e.g.
`Model: opus` for a hard task while routine tasks use `sonnet`. Lighter models
stretch subscription limits.

### Notifications

Set `AI_NOTIFY_CMD` to any command; it runs via `bash -c` with the message as `$1`
and can never break the workflow. For phone notifications, install the free ntfy app,
subscribe to a hard-to-guess topic, and put this in
`~/.config/ai-toolkit/config` (read, never sourced; only `AI_NOTIFY_CMD`, `AI_MODEL`,
`AI_LIMIT_RETRY`, `AI_LIMIT_MAX_WAIT`; environment variables win):

```bash
AI_NOTIFY_CMD=curl -fsS -d "$1" https://ntfy.sh/<your-secret-topic>
```

### Claude as coordinator (remote use)

When you drive everything through an interactive Claude Code session (for example
from a phone via Remote Control), that session is the coordinator: plan with it,
then ask it to start `ai-pipeline` in tmux, poll `.ai/bin/ai-status` and
`.ai/local/pauses.log`, and relay results. Codex never needs a window or an
approval: the review runs headless in a read-only sandbox. The interactive session
uses your normal permissions; the unattended runner keeps its restricted ones.

### CI on every pull request

Setup installs `.github/workflows/ai-validate.yml`, which runs `.ai/ci-setup`
(install dependencies, e.g. `npm ci`) and then `.ai/validate` on every PR and push
to `main`, so the PR shows an independent green/red check. Add toolchain setup steps
there if needed. Both files are protected like the rest of the gate. Hosting
platforms such as Vercel add a preview deploy per PR, which is where you test.

## Optional project knowledge base

Use the optional section in the project's CLAUDE.md to identify an external notes
folder, such as an Obsidian project folder. `.ai/` remains operational state in
Git: spec/plan, queue, state, handoff, and run log. The vault holds architecture,
decisions, and human todos; local docs can summarize or link those records. Human
todos and acceptance are not marked complete on the human's behalf. No vault is
required, and this toolkit does not discover or edit your notes itself.

To grant explicit access to only the relevant existing notes folder:

```bash
.ai/bin/ai-run --approved --knowledge-dir "/absolute/path/to/vault/project folder"
```

The runner passes it through Claude's `--add-dir` and supplies the knowledge-base
contract in its prompt. Quote paths with spaces; repeat the option when resuming.
Without that option, adding a notes path to CLAUDE.md alone does not grant external
write access. Do not enable all user settings just to obtain vault instructions.

The runner retains `--setting-sources project`. Inspection of the installed Claude
Code 2.1.288 memory loader shows user CLAUDE.md and user rules gated on the `user`
source, so global instructions are excluded here. `CLAUDE.local.md` is excluded by
omitting `local` too. Older releases had a
[reported user-memory filtering bug](https://github.com/anthropics/claude-code/issues/87590).
This was source inspection, not a live model test; check instruction loading after
CLI upgrades. See [Claude memory documentation](https://code.claude.com/docs/en/memory).
Put the required workflow/knowledge instructions in the project's CLAUDE.md or
pass the explicit knowledge-directory option rather than depending on global memory.

## Leave it running

Keep the runner in tmux so closing the terminal doesn't kill it:

```bash
tmux new -s my-app-ai
.ai/bin/ai-run --approved --sessions 32 --session-timeout 1800 --run-timeout 28800
# Detach with Ctrl-b, then d. Later:
tmux attach -t my-app-ai
```

While you're away, Claude moves through the queue and persists outcomes outside
conversation context. Full CLI/validation logs are ignored under `.ai/local/`;
compact state, tasks, handoff, and run log are checkpointed in Git. Do not run a
second implementation agent in the same checkout. The tools use a per-checkout
kernel lock; it releases when the process exits. A copied `workflow.lock` file is
not a stale lock to delete.

Do not rely on this to survive machine shutdown or sleep as a live process. It
survives those events through saved files/checkpoints and a new session. No daemon
or automatic reboot startup is installed.

## Resume after interruption

```bash
cd ~/Projects/my-app
.ai/bin/ai-status
git status
git log -5 --oneline
git diff
```

If clean, rerun `.ai/bin/ai-run --approved`. Every invocation uses a fresh-session
resume prompt; it does not need an old session ID, model, or transcript.

If dirty, inspect the partial changes and let Claude reconcile and checkpoint
them before returning to the runner:

```bash
claude "$(cat .ai/prompts/resume.md)

Reconcile the interrupted task and partial diff. Preserve unrelated changes.
Validate and create a local checkpoint, then stop so I can restart the runner."
.ai/bin/ai-check
git status
.ai/bin/ai-run --approved
```

Don't reset or delete partial work to obtain a clean checkout. An interrupted
IN_PROGRESS task is verified against source/tests and resumed; DONE is not assumed.
The runner refuses a dirty initial tree precisely to avoid guessing ownership.
Latest uncommitted edits may need reconciliation after a crash; previous commits
and checkpoint records remain recoverable. Local validation evidence may be lost
on another machine: rerun the gate there.

## Review with Codex

When Claude finishes, inspect the handoff, ensure the task queue is complete,
checkpoint any final updates, and run the full gate. Use an explicit review base:

```bash
.ai/bin/ai-check
git status
.ai/bin/ai-review --base main
cat .ai/reviews/current.md
```

Alternatively pass the saved pre-implementation SHA with `--base SHA`. The review
uses the merge-base with HEAD; an empty range, incomplete task queue, dirty tree,
or stale/failed validation is rejected. Codex independently checks requirements,
plan/tasks, diff/history, relevant source, tests, and validation evidence. Its
shell sandbox is read-only, approvals are disabled, and its final Markdown is
saved by the host script. Codex must not edit the application during this step.
User Codex configuration is omitted by the script to reduce incidental integrations;
project configuration and CLI capabilities should still be inspected in trusted repos.

The report records reviewed HEAD and merge-base. Existing review content is only
replaced after a successful nonempty report with the expected sections. Raw output
and a report copy remain in `.ai/local/`. A read-only review may be unable to run
tests that write cache/build artifacts: it should report that limitation, inspect
the validation evidence, and recommend further checks rather than pretending it ran them.

To ask Codex interactively, give it the review prompt and explicit base/revision.
Keep it in read-only mode and save its final answer as the review artifact yourself.
For example, `codex --sandbox read-only "$(cat .ai/prompts/review.md) ..."`.
The scripted workflow above provides the stricter validation/revision checks.

## Send findings back to Claude

```bash
claude "$(cat .ai/prompts/fix-review.md)"
```

Claude evaluates each finding against actual source, spec, architecture, and tests.
It records acceptance/rejection/deferral with evidence, adds tasks for valid
BLOCKER/MAJOR findings, fixes them, and reruns validation. It does not blindly obey
Codex. Preserve the original findings and record why any finding is rejected.

For a long fix queue, let Claude evaluate findings and create the tasks first;
checkpoint the review/dispositions/plan, then run `.ai/bin/ai-run --approved` again.
After fixes, run `.ai/bin/ai-check` and another `.ai/bin/ai-review --base main` when
appropriate. Commit the previous report/dispositions before replacing it so history
retains the discussion. Review output is an artifact, not merge authorization.

## Human acceptance testing and finish

Read the handoff and review, inspect `git diff main...HEAD` (or your saved base),
and check scope, unresolved findings, assumptions, migrations, and validation evidence.
Perform the handoff's real manual test steps and acceptance criteria, including
important failure paths. A green test gate doesn't substitute for your acceptance.

Record your acceptance and any outstanding risks in the handoff. Commit final
workflow artifacts and rerun the full gate. You decide whether to push/create a PR,
merge, and deploy. For example, after acceptance:

```bash
# Optional publishing, performed by you:
git push -u origin feature/initial-project
gh pr create
# Inspect the PR/CI, then merge manually when satisfied.
```

Outside `ai-pipeline`, nothing in this toolkit pushes. `ai-pipeline` pushes only
the feature branch and opens/updates a PR. Nothing ever merges or deploys.

## Components

| Component | Purpose |
| --- | --- |
| `templates/CLAUDE.md` | Primary agent responsibilities, loop, persistence, safety |
| `templates/AGENTS.md` | Independent Codex review contract |
| `templates/docs/` | Project architecture, conventions, decision records |
| `templates/.ai/` | Spec, plan, task queue, state, handoff, append-only run log, review |
| `templates/.ai/prompts/` | Planning, implementation, runner (one task), recovery, review, triage, review-fix prompts |
| `templates/.github/workflows/ai-validate.yml`, `.ai/ci-setup` | CI running the same gate on every PR |
| `.ai/validate` | Real project-specific deterministic gate (fails until configured) |
| `.ai/permissions.allow`, `.claude/settings.json` | Inspected command permissions and deny rules |
| `scripts/setup-project` | Non-overwriting bootstrap and simple ecosystem detection |
| `scripts/ai-status` | Compact status derived from records, task queue, Git, validation |
| `scripts/ai-check` | Bounded full gate, logs, and content-bound evidence |
| `scripts/ai-run` | Bounded fresh-session implementation loop and checkpoint checks |
| `scripts/ai-review` | Revision-bound, read-only Codex review and report preservation |
| `scripts/ai-pipeline` | Hands-off implement → review → triage/fix → PR → notify, resumable |
| `scripts/lib/` | Small Bash helpers and standard-library Python Markdown/copy/evidence helpers |
| `tests/` | Offline integration tests; mock CLI agents, no model calls |

Installed scripts live under `.ai/bin/` to avoid colliding with existing project
scripts. You can make your project's `scripts/ai-check` delegate there if desired.
See [docs/workflow.md](docs/workflow.md) for state contracts, permission limits,
review isolation, and future worktrees.

## Validate this toolkit

```bash
cd ~/Projects/agents
./scripts/ai-check
```

CI runs the same `./scripts/ai-check` on every push and pull request.

This checks Bash syntax and runs offline integration tests for setup, task parsing,
validation evidence, runner behavior, and review safety. It does not spend tokens
or validate the models' reasoning. Do a short supervised real CLI run in your first
project before trusting long unattended execution.

## Deliberately manual for now

Requirements/critical decisions, approval of scope and permissions, acceptance,
merge/deploy, and risky external actions. The review-fix loop is bounded and ends
in a PR, never a merge. Not yet: Codex as fallback implementer while Claude is
limited, parallel agents, auto-restart daemon, worktree manager, cost estimator,
or automatic template upgrades. More automation can follow real usage.

CLI behavior was checked against installed help and the official
[Claude headless documentation](https://code.claude.com/docs/en/headless),
[Claude permissions documentation](https://code.claude.com/docs/en/permissions), and
[Codex CLI reference](https://developers.openai.com/codex/cli/reference).

## Optional checkout watchdog

`.ai/bin/ai-watchdog [PROJECT]` checks one checkout (default: the current directory)
without AI and stays silent when healthy. It notifies through `AI_NOTIFY_CMD` when:

- `ai-pipeline` is gone without finishing or reporting a stop (killed, crashed or
  machine restarted), in any phase, even if an orphaned `ai-run` child survives;
- an implementing/fixing_review checkout has no runner and no recorded stop
  (e.g. a killed standalone `ai-run`);
- an alive runner has no log activity for `--stale-minutes` (default 45), not
  counting a usage-limit pause until its announced resume time or logs from before
  the current run started;
- a new `last-error` records a stop.

Exit codes are 0 healthy, 1 incident (including already notified), 2 usage error.
It never restarts or repairs the workflow.

`--diagnose` opts into one headless Claude attempt per newly detected incident
batch, bounded by `--diagnosis-timeout` (default 120 seconds, plus 10 seconds kill
grace). Only Read/Glob/Grep tools and project settings are enabled; MCP is disabled
and stdin is `/dev/null`; `AI_MODEL` applies. The watchdog saves the response to
ignored `.ai/local/diagnosis.md` and includes its first line in the notification.
Inspect trusted project settings/hooks before opting in; tool restrictions are not
an OS sandbox. Failed or interrupted attempts are not retried for that incident.

Run it every 10 minutes with a systemd user timer (one per checkout):

```bash
.ai/bin/ai-watchdog --install-timer --diagnose     # writes, enables and starts the units
systemctl --user list-timers 'ai-watchdog-*'
.ai/bin/ai-watchdog --uninstall-timer              # stops and removes them
```

`--install-timer` writes `ai-watchdog-<project>-<hash>.{service,timer}` to
`~/.config/systemd/user/` with the absolute checkout path, the given options and the
installing shell's `PATH` (so the timer finds `claude`, `curl` and friends). Notification
settings come from the user config described above. Existing projects need the new
`ai-watchdog` and `lib/watchdog.py` copied into `.ai/bin/` deliberately, because setup
preserves existing files.
