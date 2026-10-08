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
copies. Symlinked workflow destinations are rejected before copying. Setup ends by
suggesting the watchdog timer; `setup-project --watchdog "$PWD"` installs it too (see
[Optional checkout watchdog](#optional-checkout-watchdog)).

### Upgrading an installed project

Setup records `.ai/toolkit-version` (JSON): the toolkit commit (or `"unknown"`) and, for
each toolkit-owned file (`.ai/bin/**`, `.ai/prompts/**`), the sha256 of the version the
toolkit installed. Plain setup only adds baselines for files it creates; it never blesses a
kept file.

```bash
~/Projects/agents/scripts/setup-project --upgrade "$PWD"          # plan only, changes nothing
~/Projects/agents/scripts/setup-project --upgrade --apply "$PWD"  # apply
```

The plan lists `REPLACE` (outdated, unedited), `CREATE` (missing in this project, e.g.
`.ai/bin/ai-task` or `.ai/prompts/recheck.md` in older installs), `EDITED` (differs from its
baseline) and `ADVICE` for project-owned files (`CLAUDE.md`, `.ai/validate`,
`.ai/permissions.allow`, ...), which are never touched. The scripts call each other and the
shared helper, so the runtime is upgraded as one group, all or nothing: if any toolkit file is
locally edited the apply refuses before changing anything and lists the files; reconcile them
or pass `--force` to overwrite. The apply itself is all or nothing too: every new file is
staged next to its target before anything is replaced, and if a write fails part-way the
already-replaced files get their previous bytes and mode back, created files are removed,
`.ai/toolkit-version` is left unchanged and the command exits non-zero (a failed rollback is
reported as such). A missing or malformed stamp (legacy install) treats every
differing toolkit file as edited. After an upgrade, reinstall the watchdog timer
(`.ai/bin/ai-watchdog --install-timer ...`). Make the upgrade its own PR.

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
   The template also allows `git rm`/`git mv`, `.ai/bin/ai-task` and read-only shell
   commands (`ls`, `grep`, `cat`, `head`, `tail`, `wc`, `echo`). Claude Code denies
   redirects, pipes and chains into commands that aren't allowed, so these can't write
   files, but they **can read files outside the project** (for example `cat ~/.ssh/...`).
   Keep secrets out of reach of the runner's user. `sed`, `rg` and `find` are left out
   on purpose: they write or execute through their own flags (`sed -i`, `rg --pre`,
   `find -exec`/`-delete`).
4. Run `.ai/bin/ai-check` in the foreground with the Bash tool's `timeout` set to 600000 ms;
   never run it in the background or poll it. Record/fix any baseline failures rather than
   suppressing them.
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
mode rejects unapproved tools. Denials are logged and the run continues: each one goes to
`.ai/local/denials.log` with a note on stderr, and the runner still requires a real
DONE/BLOCKED checkpoint, so a session that cannot work around a denial stops there. Adjust
the policy deliberately afterwards. A short supervised trial before an overnight run is useful.

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
Every accepted DONE checkpoint and the final handoff commit must contain exactly the bytes
validation hashed (committed bytes equal to the validated files on disk), or the run stops with "differs
from the validated content". Repositories using clean/smudge or eol filters (Git LFS,
`text=auto` with CRLF files, `ident`) stop there too; they are not supported.
The host state directory must be an absolute path outside the checkout and the knowledge
directory (a configuration check, not OS isolation).
BLOCKED tasks can be bypassed only by independent tasks with satisfied dependencies.

No-progress, malformed state, CLI errors, timeouts, validation
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

### Modes

| Mode | Started by | May do | May not do |
| --- | --- | --- | --- |
| Interactive Claude | you, `claude "$(cat .ai/prompts/implement.md)"` | Your normal permissions (may ask); works the whole queue; local checkpoint commits | Merge, deploy, push without your say-so |
| ai-run | you, `ai-run --approved` | One task per fresh session under `dontAsk` and `.ai/permissions.allow`; reruns the gate; commits bookkeeping and validated leftovers (secret-looking files excluded); pauses and resumes on usage limits | Change the gate, push, open PRs, merge, deploy |
| ai-pipeline | you, `ai-pipeline --approved` | Everything `ai-run` does, plus plan review, Codex review, triage and fixes, pushing the feature branch and opening/updating the PR, notifications, `ai-recover` on a stop | Force-push, push `main`, merge, deploy, change the gate |
| ai-watchdog | systemd user timer or you | Probes a checkout without AI, notifies, optional read-only diagnosis; `--recover` starts `ai-recover` after a crash | Restart or repair anything itself, edit files, push |

## Hands-off delivery: `ai-pipeline`

After the plan is approved, validation is configured, and the plan is checkpointed
on a feature branch, one command delivers it as a pull request:

```bash
tmux new -s my-app-ai
.ai/bin/ai-pipeline --approved --base main --model sonnet
```

0. **Plan review**: until the first task is DONE, Codex reviews the spec, plan and tasks
   read-only (`ai-review --plan`, prompt `.ai/prompts/plan-review.md`) and the result
   is committed as `.ai/reviews/plan.md`. BLOCKER/MAJOR findings stop the run with a
   notification before any Claude usage is spent: revise the plan and rerun, or pass
   `--skip-plan-review` (on every rerun) to proceed anyway. The verdict is reused while
   the committed tree is unchanged apart from workflow records; any plan, source or
   validation change is reviewed again. Like implementation reviews, the report is
   bound to a digest stored outside the checkout, so an edited report doesn't count.
   The gate covers a branch's plan before its first task is DONE (later fix tasks from
   review triage are covered by the implementation review). If you revise the plan
   mid-branch, run `.ai/bin/ai-review --plan` yourself before rerunning.
1. **Implement**: `ai-run` works through the queue (fresh Claude session per task,
   gate after each task).
2. **Review**: once the queue is complete and validated, `ai-review` asks Codex for a
   read-only review. The review must contain `Finding counts: BLOCKER=n MAJOR=n MINOR=n`.
   On subsequent review rounds, Codex's implementation review appends earlier round history
   and the delta since the last review as context only (history never gates anything); the
   review prompt explains that Codex should verify accepted findings are really fixed, not
   re-raise rejected findings without new evidence, and still review the full range for
   cross-cutting defects.
3. **Fix**: with BLOCKER/MAJOR findings, `ai-run --triage` has Claude record one
   row per finding in `.ai/reviews/dispositions.md` (accepted with a fix task,
   rejected with evidence, or deferred) and append fix tasks. When one area has had
   BLOCKER/MAJOR findings in three consecutive review rounds, the triage prompt advises
   adding a design task instead of another symptom fix. From round 3 on, triage requires
   a `Convergence: <text>` line in dispositions.md (naming the design task or explaining
   why no area repeats); without it the triage stops with a clear message. Triage may only
   touch workflow records; the host validates that every significant finding has a valid
   disposition. The new tasks are implemented, and Codex reviews again. At most
   `--max-fix-rounds` rounds (default 2), counted from host state per branch (never
   from commit messages). Codex's report is never edited by Claude:
   the runner stops if any session changes `.ai/reviews/current.md`, and a report
   whose counts disagree with its listed finding IDs is rejected (a findings section with
   a count of 0 may be left out, and the verdict may be an `## Overall verdict` heading).
4. **Pull request**: pushes the feature branch (never with force; never `main`) and
   opens or updates a PR with the summary, tasks, validation evidence, review result,
   and the handoff's manual test steps. Unresolved or deferred significant findings
   make it a **draft** (an existing PR is converted). So does any recorded
   **disputed finding** (a BLOCKER/MAJOR Claude rejected and Codex upheld on re-check):
   the PR body then starts with a "Disputed findings" section, and you resolve them at
   the PR; the pipeline never resolves a dispute itself. Once you merge that PR, its
   disputes are history: a later branch inherits the unchanged file without a draft,
   and only disputes recorded on that branch count. The PR targets `--pr-base`,
   inferred from `--base` when that is a local or `origin/` branch, otherwise
   required. Without an `origin` remote or `gh`, it stops at a ready local branch.
   Before every review it requires that the committed bytes equal the validated files.
   Before and after every push attempt (failed or not) it re-checks that the review is
   current for HEAD, validation is current, the tree is clean, the committed bytes
   equal the validated files and all tasks are DONE, and after a push that origin's
   branch head equals HEAD; any mismatch stops the run.
5. **Notify** at start, pause, stop, and PR (`AI_NOTIFY_CMD`, see below).

Rerunning `ai-pipeline --approved` resumes where it stopped: finished tasks aren't
redone, a review is reused while only workflow records changed since it, completed
dispositions for that review are reused, an interrupted triage is completed (counted
once) before anything else, validation is re-verified before
publishing, and an existing PR is updated instead of duplicated. The pipeline holds
the checkout lock for its whole run and re-verifies the gate after each of its own
commits. `--no-pr` stops after the review;
`--draft` always opens a draft. The pipeline keeps its own gate digest across steps.

### Notifications you can read at a glance

| Marker | Meaning |
| --- | --- |
| ▶ STARTED / RESUMED | a run began, or resumed after auto-recovery |
| ✅ Done / ⚠ Blocked | a task finished (with progress, e.g. 1/2), or was blocked |
| ⏸ PAUSED | usage limit; it resumes by itself at the stated time |
| 🔧 Recovering / Recovered | auto-recovery is handling a stop; no action needed yet |
| ⚠ HUNG? | a runner is alive but silent for too long; it keeps running |
| ⛔ STOPPED, needs you | fully stopped; nothing automatic follows. Says why and what to do |
| 🏁 FINISHED | all tasks done: review result, PR link and your numbered todo list |

The finish summary lists: deciding unresolved findings (draft PR), the manual test
steps from `.ai/handoff.md`, merging, and every item under the handoff's "Human todos".
Manual testing is split into `### Needs you` (steps only a human can verify, e.g. look
and feel, phone notifications, external services) and `### Covered by automated tests`
(scenarios with deterministic test names); the PR shows only "Needs you" steps in the
summary.

### Auto-recovery

Stops are recovered in tiers, so a hiccup doesn't wait for you:

1. **Rules, no AI.** A task Claude finished and the full gate validated but Claude left
   uncommitted is committed by the runner (the gate verified unchanged). Sessions start
   from a clean tree, so new files are that session's own output. Automatic checkpoints stage
   the session's output except secret-looking files (everything git doesn't ignore), list
   the new files in the notification, and stop instead if a new file looks like a secret
   (`.env*`, `*.pem`, `*.key`, SSH keys, `*credentials*`, ...). Pushes retry
   3 times. Usage limits pause and resume.
2. **A Claude decision, host action.** When `ai-pipeline` stops, `ai-recover` takes over
   the same process. Hard rules escalate at once (gate, permissions, branch, review
   integrity, plan-review findings, weekly limit, a changed gate digest). A stop during
   **review triage** is never committed as leftover work: if only workflow records changed
   since the triage started, `ai-recover` reruns and the pipeline first finishes that
   triage (checks the review it belongs to, the scope and the dispositions, then records
   the round exactly once); anything else escalates. Otherwise a
   read-only Claude session (Read/Glob/Grep, prompt `.ai/prompts/recover.md`) picks one
   action that the script carries out: `rerun`, `commit_and_rerun` (only if the full
   gate passes on the leftovers and none of them looks like a secret), or
   `escalate`. Malformed answers escalate.
3. **Crashes**: `ai-watchdog --recover` starts `ai-recover` via `systemd-run` when the
   pipeline was killed or the machine restarted.

At most `AI_RECOVER_MAX` (default 2) attempts per human-started run; resumes keep the
approved gate digest from the original `--approved` start and refuse a changed gate.
Codex never steers: it diagnoses (`--diagnose`) and reviews. Disable with
`AI_AUTO_RECOVER=0` (both keys are allowed in the user config).

### Usage limits

A Claude or Codex usage/rate-limit failure doesn't end the run. The scripts read
the reset time from the error (or wait `AI_LIMIT_RETRY`, default 1800 s), notify,
sleep, and retry the same step. Total waiting per command is capped by
`AI_LIMIT_MAX_WAIT` (default 28800 s); a weekly limit beyond that stops with a
notification so you can rerun after the reset. Pauses are logged in the ignored
`.ai/local/pauses.log`. Most usage is Claude's (implementation); Codex mostly reviews.
A Codex limit on a review doesn't pause by default: see "Claude fallback reviewer".

### Claude fallback reviewer

`AI_REVIEWER` picks the reviewer for plan reviews, code reviews and re-checks:
`auto` (default) asks Codex first and, only when Codex reports a usage limit (or the
Codex CLI is missing), runs a fresh read-only Claude review instead; `codex` keeps the
old behaviour (pause until Codex resets); `claude` skips Codex. Codex is tried again on
every later review, so it takes over as soon as it has usage.

The Claude reviewer is a separate `claude -p` session with no access to the
implementing session and no shell: tools Read/Glob/Grep only, whatever
`.ai/permissions.allow` contains (every Bash allow/deny list tried left a route to
running code or writing files through command arguments). It runs no commands, tests
or probes. Instead the host writes the review's git context to the ignored
`.ai/local/review-context/` right before the session and deletes it right after: for
a code review the diff (`diff.patch`), commits (`log.txt`), changed paths (`files.txt`)
and, on a later round, `since-last-review.patch`; for a re-check the same for the
reviewed range plus the rejected findings (`findings.txt`); for a plan review the plan
files and recent commits. If any of that fails, the review stops before Claude starts
and the prior review stays. The reviewer works from traced code paths and the
recorded validation evidence (`.ai/local/validation.json`, gate logs). The tool list is
saved next to the review log (`.ai/local/review-*.allowlist`), denied attempts go to
`.ai/local/review-denials.log`. Read is not limited to the checkout (the prompt tells it
to stay inside, since the review is published). No MCP; project settings only. It gets
the mode's usual prompt (naming the context files instead of git commands) plus
`.ai/prompts/claude-review.md` (sceptical stance, evidence rules, a checklist of failure
types seen in these projects) and returns the same format, so the host saves it to the
same file with the same bindings; dispositions, re-checks and disputes work unchanged.
The tool list is not an OS sandbox: the checkout-unchanged check after the review and
the gate check still apply.

Model by risk: `claude-fable-5-1` for plan and code reviews when any task runs on opus
or a task title names RLS/row-level, auth/authentication/authorization, permissions,
policies, locks/lock order, concurrency, deadlocks, race conditions, migrations,
deletion, drop, payments or irreversible work (whole words: "author" or "Lockfile" don't
count); otherwise `claude-opus-5-5`; re-checks on
`claude-opus-5-5`; effort `high`. Override with `AI_CLAUDE_REVIEW_MODEL` and
`AI_CLAUDE_REVIEW_EFFORT`. Claude reviews draw from the same allowance as
implementation.

Every Claude-written review starts with a `Reviewer: Claude fallback (…)` line
(`Reviewer: Claude (…)` when forced with `AI_REVIEWER=claude`), is
listed in `.ai/reviews/fallback-log.md` (committed with the review) and is named in the
PR. When Codex has usage again, run one catch-up Codex review over the listed work
(e.g. `AI_REVIEWER=codex .ai/bin/ai-review --base <oldest listed base>` on the merged
branch) and note the result in the log.

### Outcome log (tuning the model rules)

`ai-run` appends one JSON line per task attempt and `ai-review` one per review to
`outcomes.jsonl` in the host state directory (`AI_STATE_DIR`, default
`~/.local/state/ai-toolkit`; outside every checkout, shared by all projects): project,
branch, task, title, category (security, concurrency, migration, tests, docs, ui,
feature; from the title), model, result (done, blocked, validation_failed,
no_checkpoint, or timeout, interrupted, error for a stopped attempt), attempt, first-time pass, duration; for reviews: mode, reviewer
(codex, claude-fallback, claude), model, effort, finding counts, duration.
`.ai/bin/ai-status --outcomes [FILE...]` prints first-time pass rates and attempts per
model, category and model/category, findings per reviewer and model, and the
Claude-only reviews awaiting the Codex catch-up. Use it to see which categories could
move to haiku and which keep failing on sonnet.

### Models

`--model NAME` (or `AI_MODEL`) picks the Claude model for implementation and triage.
Planning writes an explicit `Model:` on every task by risk (haiku for mechanical, sonnet for ordinary work, opus for
security, auth/RLS, concurrency, destructive migrations or tasks that failed before), and
the Codex plan review flags a mismatch before any Claude usage.
A task may override it with an optional line under its `Dependencies:` line, e.g.
`Model: opus` for a hard task while routine tasks use `sonnet`. Lighter models
stretch subscription limits.

Codex reviews (plan and implementation) use `AI_REVIEW_MODEL` (default: Codex's own
default model) at `AI_REVIEW_EFFORT` reasoning (low, medium, high, xhigh, max;
default **high**). Reviews are where a stronger model pays off most: findings caught
there save Claude fix rounds. The narrower re-check of rejected findings
(`ai-review --recheck`) uses `AI_RECHECK_EFFORT` (default **medium**).

### Notifications

Set `AI_NOTIFY_CMD` to any command; it runs via `bash -c` with the message as `$1`
and can never break the workflow. For phone notifications, install the free ntfy app,
subscribe to a hard-to-guess topic, and put this in
`~/.config/ai-toolkit/config` (read, never sourced; only `AI_NOTIFY_CMD`, `AI_MODEL`,
`AI_LIMIT_RETRY`, `AI_LIMIT_MAX_WAIT`, `AI_REVIEW_MODEL`, `AI_REVIEW_EFFORT`, `AI_RECHECK_EFFORT`,
`AI_REVIEWER`, `AI_CLAUDE_REVIEW_MODEL`, `AI_CLAUDE_REVIEW_EFFORT`, `AI_DIAGNOSIS_MODEL`,
`AI_AUTO_RECOVER`, `AI_RECOVER_MAX`; environment variables win):

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
`ai-run` also runs `.ai/ci-setup` on the host before its first task when dependencies
are missing or stale (a fresh worktree, a changed lockfile; `AI_DEPS_TIMEOUT`, default
1200 s); a tree-snapshot before and after verifies no project files were changed by the
install, or the run stops. Auto-recovery does the same before validating leftover work
that changed a lockfile. Dependencies a task changes mid-run are installed at the next start.

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

## Review with Codex (Claude fallback)

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
At a Codex usage limit the same command runs the Claude fallback reviewer (see
"Claude fallback reviewer"); `AI_REVIEWER` chooses.
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

When Claude rejected a BLOCKER/MAJOR finding, commit the dispositions and run
`.ai/bin/ai-review --recheck`: Codex (read-only, `AI_RECHECK_EFFORT`, default medium)
re-checks only the rejected findings against Claude's evidence and answers `withdrawn`
or `upheld` per finding; a missing, duplicate or malformed answer counts as upheld, and an
answer for an unknown finding makes every finding upheld.
It refuses unless the review verifies and only workflow records changed since the
reviewed commit (pending fix tasks are fine). The host writes `.ai/reviews/recheck.md`,
bound to the review, the rejected rows (IDs and evidence) and the reviewed HEAD;
`python3 .ai/bin/lib/workflow.py recheck-verify` prints its verified answers.
`ai-pipeline` runs this re-check itself right after every triage (and on every start
or resume, before any task runs) and records each upheld finding as a durable dispute
in `.ai/reviews/disputes.md` (host-written, append-only, verified before publishing).

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

Outside `ai-pipeline`, nothing in this toolkit pushes. The pipeline pushes the feature branch and opens the pull request
(updating it on reruns), and nothing else. Nothing ever merges or deploys.

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
| `scripts/ai-review` | Revision-bound, read-only Codex review (Claude fallback at its limit) and report preservation |
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

## Running the tests

```bash
python3 tests/run_parallel.py                 # parallel shards, works from any directory
AI_TEST_WORKERS=4 python3 tests/run_parallel.py
python3 tests/run_parallel.py --collect-only  # print the number of tests only
python3 -m unittest discover -s tests         # serial, what the gate runs today
python3 -m unittest discover -s tests -k parallel_runner   # one group by name
```

`tests/run_parallel.py` discovers the same tests as the serial command and splits them
round-robin into `AI_TEST_WORKERS` shards (default: the CPU count, at most 8). Each shard
runs as `python3 -m unittest` in its own process. The runner fails when a shard fails or
crashes, when it collects no tests, or when the shards ran a different number of tests than
it collected. Switching `.ai/validate` to the parallel runner is a gate change that a human
approves.

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

`--diagnose` opts into one headless, read-only diagnosis per newly detected
incident batch, bounded by `--diagnosis-timeout` (default 120 seconds, plus 10
seconds kill grace). By default (`--diagnosis-agent auto`) Codex diagnoses (`codex exec
--sandbox read-only`, medium effort), because Codex has its own limit while Claude's is
shared with your interactive sessions; when Codex fails (e.g. at its usage limit) Claude
diagnoses instead. `--diagnosis-agent codex|claude` forces one. Claude: Read/Glob/Grep
only, project settings, MCP disabled, model `AI_DIAGNOSIS_MODEL` (default
`claude-sonnet-5-5`). Reinstall the timer after upgrading so it uses the new default. Stdin is `/dev/null`. The watchdog saves the response to
ignored `.ai/local/diagnosis.md` and includes its first line in the notification.
Inspect trusted project settings/hooks before opting in; tool restrictions are not
an OS sandbox. Failed or interrupted attempts are not retried for that incident.

Run it every 10 minutes with a systemd user timer (one per checkout):

```bash
.ai/bin/ai-watchdog --install-timer --diagnose --recover   # writes, enables and starts the units
systemctl --user list-timers 'ai-watchdog-*'
.ai/bin/ai-watchdog --uninstall-timer              # stops and removes them
```

`ai-watchdog --timer-status` prints `installed`, `missing (reason)` or `unknown (reason)`
(exit 0, 1, 2); `installed` needs both unit files, `enabled` and `active`. `ai-pipeline`
checks it at every start and says so in the screen output and the STARTED/RESUMED
notification when the timer is missing or unknown; the run continues. `setup-project
--watchdog` installs the timer right after the files (not with `--dry-run` or
`--upgrade`); plain setup ends with a "Next: install the watchdog timer" line. Each new
run worktree is its own checkout and needs its own timer; remove it with
`--uninstall-timer` before deleting the worktree.

`--install-timer` writes `ai-watchdog-<project>-<hash>.{service,timer}` to
`~/.config/systemd/user/` with the absolute checkout path, the given options and the
installing shell's `PATH`, `XDG_*`, `AI_STATE_DIR` and `AI_*` settings, and runs a copy of
the scripts kept outside the checkout (rerun `--install-timer` after updating the toolkit;
it refuses, writing nothing, when that copy or the host state directory would lie inside the
checkout or `XDG_DATA_HOME` is relative) (so the timer
finds `claude`, `curl` and your notification command; the unit file is readable like your
user config). Notification
settings come from the user config described above. Existing projects need the new
`ai-watchdog` and `lib/watchdog.py` copied into `.ai/bin/` deliberately, because setup
preserves existing files.

### Waiting for a run

Wait on the pipeline's PID (the contents of `.ai/local/pipeline.active`), never on a
`pgrep -f <pattern>` loop: the waiting shell's own command line contains the pattern, so
the loop matches itself and never ends (or ends wrongly).

```bash
pid=$(cat .ai/local/pipeline.active)
while kill -0 "$pid" 2>/dev/null; do sleep 60; done
```

## License

MIT, see [LICENSE](LICENSE). Third-party code may only be added with its license, retained notices and a note of the upstream source and changes (none so far; OpenRig ideas are reimplemented, not copied).
