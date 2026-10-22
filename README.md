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

### Plan with a headless session

To write the plan without an interactive session (for example from mission control), put the
objective in a file (a regular file of at most 200 KB) and run:

```bash
.ai/bin/ai-plan objective.md [--revision] [--model NAME] [--session-timeout SECONDS] \
  [--knowledge-dir DIR] [--read-dir DIR]... [--detach]
```

`ai-plan` is the supported way to start a planning session; without `--detach` it simply becomes
`ai-run --plan objective.md …` (same options, same process). Paths (the objective,
`--knowledge-dir`, every `--read-dir`) are resolved against your working directory. With
`--detach` it starts the session in the background, its output in
`.ai/local/plan-<UTC stamp>-<8 hex>.log` (created exclusively, never through a symlink), and
returns only once `ai-dashboard`'s record shows that session planning:
`Planning session started: pid N, log PATH` (exit 0; also when the plan already finished
successfully before the first check). If the session ends first otherwise (for example another
runner holds the checkout) it prints `ended early` with the last lines of the log and exits with
the session's status (at least 1); if the start cannot be confirmed within `AI_PLAN_ACK_SECONDS`
(default 20) it exits 1 with `could not confirm …` and leaves the session running. Mission
control's equivalent of a hand-run launcher is:

```bash
.ai/bin/ai-plan objective.md --read-dir ~/zWiki --read-dir ~/Projects/wt/plans \
  --read-dir ~/Projects/wt/research --detach
```

The session limit stays 3600 seconds unless `--session-timeout` is given.

One Claude session (default model `opus`, default limit 3600 seconds; the watchdog's `hung`
warning may still fire after 45 quiet minutes) gets `.ai/prompts/plan.md`, the objective and a
planning contract. Its tools are `Read`, `Glob`, `Grep`, `Edit` and `Write`, and it may only
write `.ai/project-spec.md`, `.ai/current-plan.md`, `.ai/tasks.md`, `.ai/state.md`,
`.ai/handoff.md` and `.ai/reviews/dispositions.md`: no shell and no project allowlist, so
`--approved` is not needed. The run starts from a feature branch with no uncommitted changes
outside those records, registers the checkout for `ai-dashboard` (stage `planning` from the
first second, `📝 PLANNING` notification), then checks that only the plan records changed,
reorders `.ai/tasks.md` so every task comes after its dependencies (`ai-task reorder`; a cycle,
unknown ID or prose in `Dependencies:` stops with `Planning: task queue is invalid`) and checks
that it passes `ai-task check`. On success the record says `planned` with the task
count and `📝 Plan ready` is sent; otherwise the run stops with the reason (⛔, record `stopped`)
and leaves the session's edits as written. It never commits: review the plan, commit it, then
start `ai-pipeline --approved`. `--revision` tells the session an earlier plan exists (keep DONE
tasks). With or without `--revision`, a task that was DONE when the session started (committed or not) must keep
its block unchanged: otherwise the run stops with `Planning: DONE task T00x was changed or
removed`. `--plan` refuses to run inside a pipeline and refuses `--triage`, `--revise-plan`,
`--since`, `--base`, `--sessions` and `--run-timeout`.

Before leaving an implementation session unattended:

1. Review `.ai/project-spec.md`, `.ai/current-plan.md`, and `.ai/tasks.md`.
2. Configure `.ai/validate` with **real** project commands. Read detected suggestions
   in `.ai/validation-candidates.md`; inspect scripts before executing them. The
   supplied validation placeholder deliberately fails with exit 78.
3. Add necessary local commands to `.ai/permissions.allow` after inspecting them.
   The template already allows `Bash(chmod +x *)` (no other chmod form; numeric modes such
   as `chmod 755` are denied) so a runner session can make a script it created executable,
   or repair a tracked script that lost its bit; the runner also restores a tracked script's
   recorded executable bit after each implementation session, even one that timed out (never a
   gate or prompt file: the guard's protected-path list). Existing projects add that
   line by hand. Use narrow tool entries such as `Bash(npm run test *)`; dependency installation
   may need an explicit permission entry. Do not give unrestricted Bash by default.
   `.ai/bin/ai-task check` validates the task queue read-only (the pipeline runs the same
   check and stops on an invalid queue, unless its pre-flight scan could fix it: only TODO tasks
   out of dependency order or missing an empty section, repaired once per task per run, committed
   as `chore(ai): ruling: task queue` with a `Ruling (…)` run-log row and a 🔧 notification). `.ai/bin/ai-task reorder` rewrites the queue so every
   task comes after its dependencies (task text unchanged); it rejects cycles, unknown IDs and
   prose in `Dependencies:`. `python3 scripts/lib/workflow.py tasks fill-sections` (host-only)
   adds a missing `### Likely affected modules` or `### Result / notes` heading to TODO tasks and
   changes nothing else.
   The template also allows `git rm`/`git mv`, `.ai/bin/ai-task` and read-only shell
   commands (`ls`, `grep`, `cat`, `head`, `tail`, `wc`, `echo`). Claude Code denies
   redirects, pipes and chains into commands that aren't allowed, so these can't write
   files, but they **can read files outside the project** (for example `cat ~/.ssh/...`).
   Keep secrets out of reach of the runner's user. `sed`, `rg` and `find` are left out
   on purpose: they write or execute through their own flags (`sed -i`, `rg --pre`,
   `find -exec`/`-delete`).
4. Run `.ai/bin/ai-check` with the Bash tool's `run_in_background: true` and wait for its
   completion notice; make no edits while it runs. Record/fix any baseline failures rather than
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
.ai/bin/ai-run --approved --session-timeout 1800 --run-timeout 14400
```

Without `--sessions` the session budget is `max(16, unfinished tasks + 2)`, recomputed on every
`ai-run` call (so fix-round tasks added by triage are covered); `Session budget: N` is printed
first. `--sessions N` sets it explicitly.

An implementation session also gets room for two runs of this project's measured gate: its limit
is `--session-timeout` plus twice the gate time, at most double the session timeout, and never
beyond the remaining run time. The gate time is the slowest of the last 3 passing host `ai-check`
runs, which `ai-run` records as `gate` lines in the host outcome log (where agents cannot write).
The cap keeps a corrupt log from more than doubling a session. Triage, plan revision and `--plan`
sessions keep the plain limit.

`ai-check` refuses with `Validation is already running.` while another gate holds its lock;
`AI_CHECK_LOCK_WAIT=N` (seconds, default 0) makes it wait up to N seconds for that gate first.
The wait counts against `AI_CHECK_TIMEOUT`: the validator gets only the seconds left, and a wait
that uses them all exits 124 with `Validation time limit reached while waiting for the lock.`
`ai-run`'s host gates wait up to 15 minutes (within the run time), so a session that ends while
its own background gate still runs does not fail the host gate.

Every session's contract says that a gate run that outlives a tool call is not a blocker: the
full gate the runner runs after the session decides. If a session still marks its task BLOCKED
although its own gate showed no failing check, and the runner's full gate then passes on the
same tree, `ai-run` sets the task back to IN_PROGRESS (commit `chore(ai): retry T… after a
gate-only block`, a 🔧 notification) and gives it one more session, once per task per run.

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
Sessions keep throwaway files under `.ai/local/scratch/`; the host empties `.ai/local/scratch`
before and after every session and never follows a symlink there.
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
| ai-run --plan | you or mission control, `ai-plan objective.md [--detach]` (or `ai-run --plan objective.md`) | One planning session with Read/Glob/Grep and Edit/Write of the six plan records; checks the scope and the queue; dashboard record and notifications | Run a shell, edit anything else, commit, implement |
| ai-run | you, `ai-run --approved` | One task per fresh session under `dontAsk` and `.ai/permissions.allow`; reruns the gate; commits bookkeeping and validated leftovers (secret-looking files excluded); pauses and resumes on usage limits | Change the gate, push, open PRs, merge, deploy |
| ai-pipeline | you, `ai-pipeline --approved` | Everything `ai-run` does, plus plan review, Codex review, triage and fixes, pushing the feature branch and opening/updating the PR, notifications, `ai-recover` on a stop | Force-push, push `main`, merge, deploy, change the gate |
| ai-watchdog | systemd user timer or you | Probes a checkout without AI, notifies, optional read-only diagnosis; `--recover` starts `ai-recover` after a crash or when a usage-limit relaunch is due | Restart or repair anything itself, edit files, push |
| ai-dashboard | you, `ai-dashboard` | Reads the host registry and each checkout's `.ai/local/` records and shows every pipeline (read-only, advisory) | Write files, take locks, change a run, authorize anything |

## Hands-off delivery: `ai-pipeline`

After the plan is approved, validation is configured, and the plan is checkpointed
on a feature branch, one command delivers it as a pull request:

```bash
tmux new -s my-app-ai
.ai/bin/ai-pipeline --approved --base main --model sonnet
```

0. **Plan review**: until the first task is DONE, Codex reviews the spec, plan and tasks
   read-only (`ai-review --plan`, prompt `.ai/prompts/plan-review.md`) and the result
   is committed as `.ai/reviews/plan.md`. On BLOCKER/MAJOR findings the supervisor
   (`AI_SUPERVISE=1`, default) has Claude revise the plan (`ai-run --revise-plan`: one row
   per finding in `.ai/reviews/plan-dispositions.md`, accepted with new tasks, rejected
   with evidence, or a question for you), notifies `🔁 Plan revised (round n/N)` and has
   the plan reviewed again with the earlier rounds as context. It stops for you when a
   revision asks you a question (`plan review needs your decision`, also after a crash),
   after `AI_SUPERVISE_PLAN_ROUNDS` revisions in one run (`supervision limit reached`) or
   when a revision leaves its scope. The host reorders the queue after each revision, so a
   new task appended after the tasks that depend on it still runs first; a cycle, unknown ID
   or prose in `Dependencies:` stops at once (`Plan revision stage: task queue is invalid`,
   no recovery attempt). A revision interrupted after its session wrote such a queue (crash,
   restart) resumes the same way (after triage, planning and each revision the host also adds a
   missing `### Likely affected modules` or `### Result / notes` to new tasks and prints
   `Task queue: added missing sections: …`; any other missing section still stops): the host repairs the uncommitted queue before any queue
   check and records the revision without a second session. From review round `AI_SUPERVISE_ESCALATE_ROUND` the
   revision runs on `AI_SUPERVISE_ESCALATE_MODEL`. With `AI_SUPERVISE=0` the findings stop
   the run before any Claude usage: revise the plan and rerun, or pass
   `--skip-plan-review` (on every rerun) to proceed anyway. A question a revision recorded
   for the current report stops every run, also with `--skip-plan-review` or a task already
   DONE, until you answer it and run `ai-review --plan`. The verdict is reused while
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
   from commit messages). Supervised (`AI_SUPERVISE=1`), a run gets one extra fix round
   when the host-verified BLOCKER+MAJOR counts fell strictly over the last two rounds and
   the current review (`🔁 Extra fix round: findings falling (x → y → z)`); otherwise the
   PR is a draft as before. Codex's report is never edited by Claude:
   the runner stops if any session changes `.ai/reviews/current.md`, and a report
   whose counts disagree with its listed finding IDs is rejected (a findings section with
   a count of 0 may be left out, and the verdict may be an `## Overall verdict` heading).
   Supervised (`AI_SUPERVISE=1`), a plan or code review that fails only these format checks
   (missing field or section, counts not matching the listed IDs, empty answer) is requested
   once more with the error appended (`🔁 Review format retry (plan|code): <error>`, one
   run-log line naming the first report, committed with the review); a second format error
   stops as before. Reviewer errors, a changed checkout and re-checks are never retried.
4. **Pull request**: pushes the feature branch (never with force; never `main`) and
   opens or updates a PR with the summary, tasks, validation evidence, review result,
   and the handoff's manual test steps. Unresolved or deferred significant findings
   make it a **draft** (an existing PR is converted). So does any recorded
   **disputed finding** (a BLOCKER/MAJOR Claude rejected and Codex upheld on re-check):
   the PR body then starts with a "Disputed findings" section, and you resolve them at
   the PR; the pipeline never resolves a dispute itself. Once you merge that PR, its
   disputes are history: a later branch inherits the unchanged file without a draft,
   and only disputes recorded on that branch count. A later run whose review is clean
   (no unresolved findings, no dispute) makes the PR ready again, but only when the
   pipeline drafted it itself (recorded in host state, outside the checkout); a PR you
   drafted, or one drafted with `--draft`, stays a draft ("left as draft"). An existing
   PR whose draft state could not be read first is never counted as a pipeline draft. `--draft`
   also revokes an earlier pipeline draft, so that PR is never made ready automatically;
   if that record cannot be removed the run stops and names the file to delete. A human
   re-draft between two runs is not seen: the record still says the pipeline drafted it.
   The PR targets `--pr-base`,
   inferred from `--base` when that is a local or `origin/` branch, otherwise
   required. The review itself compares against `origin/<base>` when that is strictly
   ahead of your local `<base>` (a stale local `main` would otherwise pull already merged
   PRs into the review); the run prints `Review base: <ref> at <sha>`, warns when the two
   have diverged (then local wins), and never fetches. If that base has moved past your
   branch, the run stops at the start ("Review base … moved past the branch; merge it
   into <branch> and rerun"), after finishing any interrupted triage or re-check and
   before any other agent runs: merge the base only after that stop, then rerun.
   Recovery escalates this stop and keeps the full message. Without an `origin` remote or `gh`, it stops at a ready local branch.
   Before every review it requires that the committed bytes equal the validated files.
   Before and after every push attempt (failed or not) it re-checks that the base is
   still contained in HEAD, that the review is current for HEAD, validation is current, the tree is clean, the committed bytes
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
| 🔧 Ruling | the host fixed a task queue whose only fault was the order or an empty section, once per task per run; see the run log |
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
   integrity, plan-review findings, a usage limit beyond the wait budget that no relaunch covers, a changed gate digest). A stop during
   **review triage** is never committed as leftover work: if only workflow records changed
   since the triage started, `ai-recover` reruns and the pipeline first finishes that
   triage (checks the review it belongs to, the scope and the dispositions, then records
   the round exactly once); anything else escalates. A **plan revision** stage works the
   same way: only plan records changed → rerun, and the pipeline closes the stage when the
   host revision record exists or runs the revision once (reserved per plan report, so a
   resume never counts it twice; model `opus`, or `AI_SUPERVISE_ESCALATE_MODEL` from round
   `AI_SUPERVISE_ESCALATE_ROUND`); anything else escalates. A revision that recorded
   questions for you (needs-human) always escalates with those questions, even after a
   crash and before the attempt limit, and so do a failed plan-revision stage and the
   supervision limit (`AI_SUPERVISE_PLAN_ROUNDS` revisions per human-started run).
   A **session timeout** of an implementation task that is IN_PROGRESS with uncommitted
   work needs no decision: the host commits that work as a recovery checkpoint only if the
   full gate passes on it, and reruns, once per task per human-started run; a failing gate or
   a second timeout of the same task escalates.
   Otherwise a
   read-only Claude session (Read/Glob/Grep, prompt `.ai/prompts/recover.md`) picks one
   action that the script carries out: `rerun`, `commit_and_rerun` (only if the full
   gate passes on the leftovers and none of them looks like a secret), or
   `escalate`. The answer is one JSON decision object; a diagnosis written before or after it
   still counts when the object starts its own line and the prose around it contains no `{`,
   `}`, `[` or `]`. Any other answer escalates, and the ⛔ reason quotes the start of what the
   session wrote (`the recovery session gave no valid decision; it wrote: …`). A reason or
   human action over 300 characters is cut at a sentence or word boundary (never mid-word);
   the full text is then in `.ai/local/recovery-decision.txt` and the ⛔ says so.
3. **Crashes**: `ai-watchdog --recover` starts `ai-recover` via `systemd-run` when the
   pipeline was killed or the machine restarted, and when a usage-limit relaunch (below) is due.

At most `AI_RECOVER_MAX` (default 2) attempts per human-started run; resumes keep the
approved gate digest from the original `--approved` start and refuse a changed gate.
Codex never steers: it diagnoses (`--diagnose`) and reviews. Disable with
`AI_AUTO_RECOVER=0` (both keys are allowed in the user config).

### Usage limits

A Claude or Codex usage/rate-limit failure doesn't end the run. The scripts read
the reset time from the error (or wait `AI_LIMIT_RETRY`, default 1800 s), notify,
sleep, and retry the same step. Total waiting per command is capped by
`AI_LIMIT_MAX_WAIT` (default 28800 s). A usage limit whose reset is beyond that, inside
`ai-pipeline` with auto-recovery on, pauses instead of stopping: `ai-recover` schedules a
relaunch for just after the reset (⏸, exit 75) and the watchdog timer installed with
`--recover` starts it then (▶ RESUMED, no Claude decision, no recovery attempt), at most
`AI_LIMIT_RELAUNCH_MAX` (0–9, default 2; any other value counts as 2) times per run. Past that cap, without such a timer, with
`AI_LIMIT_RELAUNCH_MAX=0` or outside the pipeline it stops with a notification so you can rerun
after the reset (it records the agent and reset time in `.ai/local/limit-stop`). A relaunch
first checks that HEAD and the whole checkout (submodules included) are exactly as the stop left
them: any change during the wait, even to a bookkeeping file, stops it with nothing committed.
A limit stop of an implementation session keeps its uncommitted work, and the relaunch continues it
once, going straight back to implementation (no plan review re-run on the preserved work): the task's
own session reconciles it, or, when the task was already DONE, the runner validates and commits
it (`checkpoint T… (validated; the session did not commit)`), never a recovery commit; a stop
before that, including the resumed run's own checks of the preserved work (queue, task status,
dependency setup), is final (⛔, nothing committed, even with auto-recovery on). Every start check
of the resumed run accepts exactly that preserved tree, so a settled re-check or recorded disputes
don't block it; only inconsistent uncommitted review records stop it, before anything is written. Pauses are logged in the ignored `.ai/local/pauses.log`. Most usage is Claude's (implementation); Codex mostly reviews.
A Codex limit on a review doesn't pause by default: see "Claude fallback reviewer".

### Claude fallback reviewer

`AI_REVIEWER` picks the reviewer for plan reviews, code reviews and re-checks:
`auto` (default) asks Codex first and, only when Codex reports a usage limit (or the
Codex CLI is missing), runs a fresh read-only Claude review instead; `codex` keeps the
old behaviour (pause until Codex resets); `claude` skips Codex. When Codex names its reset
time, the host remembers it (`codex-limit.json` in the host state directory): until then
`auto` reviews go straight to the Claude fallback (labelled `(recorded)`) without calling
Codex; afterwards Codex takes over again. `codex` ignores that record.

Review routing (`auto` only): Codex reviews the plan, re-checks, the first full code review and
every large or risky fix round. A small low-risk fix-round re-review goes to a fresh read-only
Claude session instead, labelled `Claude, routed (…)`, with no catch-up entry (Codex reviewed
the branch earlier). Small: at most `AI_REVIEW_SMALL_LINES` (default 200) changed lines outside
`.ai/` since the last host-recorded code review. Risky: a changed path matching the risk globs
(migrations, SQL, Supabase, auth, policies, RLS, security, payment, billing, `.github/`,
`.claude/`, permissions, `scripts/lib/common.sh`, `scripts/ai-check`; add globs with
`AI_REVIEW_RISK_PATHS`), a changed line with a risk word (auth, RLS, grant, migration, payment,
lock, race, transaction, secret, token, password, permission and similar; add words with
`AI_REVIEW_RISK_WORDS`), or a task finished since that review running on opus. The decision
reads host records only; anything missing sends the review to Codex. `AI_REVIEW_ROUTE=codex`
turns routing off.

Every published plan and code review names its reviewer in a `Reviewed by:` line (BR-14), and the
PR lists one `Reviewed by:` bullet per plan and code round, so a Claude fallback or routed review is
visible in the PR itself.

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
branch) and note the result in the log. `ai-status --outcomes` lists a Claude review under
"Codex catch-up pending" only until a later Codex review of the same project, branch and
family (plan or code; a full code review also covers a re-check, but a Codex re-check covers
only a re-check, never a full review) exists, or you record a catch-up done on another branch with
`ai-status --catch-up-done BRANCH...` (a human command; agents do not run it).

### Outcome log (tuning the model rules)

`ai-run` appends one JSON line per task attempt and `ai-review` one per review to
`outcomes.jsonl` in the host state directory (`AI_STATE_DIR`, default
`~/.local/state/ai-toolkit`; outside every checkout, shared by all projects): project,
branch, task, title, category (security, concurrency, migration, tests, docs, ui,
feature; from the title), model, result (done, blocked, validation_failed,
no_checkpoint, or timeout, interrupted, error for a stopped attempt, or crashed for a runner
that was killed: logged, with unknown duration, at the next `ai-run` start other than `--plan`, before
its clean-checkpoint check, so that start still stops with `Start from a clean checkpoint`
until the interrupted bookkeeping (`.ai/state.md` at least) is committed or reset; only
implementation attempts, and a checkout never started again keeps its record pending), attempt, first-time pass, duration,
`seq` (host-wide order key, allocated when the attempt opens; gaps are normal) and `started`
(epoch seconds, informational); for reviews: mode, reviewer
(codex, claude-fallback, claude), model, effort, finding counts, duration; a re-check
line carries `upheld_blocker`, `upheld_major`, `withdrawn_blocker`, `withdrawn_major` and
`reviewed_head` instead (omitted when the re-check report cannot be verified). Each planning
session (`ai-plan`, `ai-run --plan`) appends a `plan` line (result done, stopped, interrupted or
timeout; model, seconds, task count when it wrote a plan, `revision`); a written plan also adds a
`plan written:` row to `.ai/run-log.md`, left uncommitted with the plan. The report ignores `plan` lines.
`.ai/bin/ai-status --outcomes [FILE...]` prints first-time pass rates and attempts per
category (per task) and per model and model/category (per attempt, each credited to the
model that ran it), findings per reviewer and model, upheld/withdrawn totals of re-checks
per reviewer, and the
Claude-only reviews awaiting the Codex catch-up. It orders a task's attempts by `seq`, so an
attempt recorded late keeps its place (rows written before `seq` existed come first, in file
order). Use it to see which categories could
move to haiku and which keep failing on sonnet.

### Models

`--model NAME` (or `AI_MODEL`) picks the Claude model for implementation and triage.
Planning writes an explicit `Model:` on every task by risk (haiku for mechanical, sonnet for ordinary work, opus for
security, auth/RLS, concurrency, destructive migrations or tasks that failed before), and
the Codex plan review flags a mismatch before any Claude usage.
A task may override it with an optional line under its `Dependencies:` line, e.g.
`Model: opus` for a hard task while routine tasks use `sonnet`. Lighter models
stretch subscription limits.

A task that failed before starts each new session fresh with a short host note of what failed
(the last attempt's result, failing checks, its last result line). From the third attempt the
runner raises the model one tier (haiku → sonnet → opus; opus stays) and says so in the prompt;
the run log names each attempt's number and model, e.g. `completed (attempt 3, opus)`.

Codex reviews (plan and implementation) use `AI_REVIEW_MODEL` (default: Codex's own
default model) at `AI_REVIEW_EFFORT` reasoning (low, medium, high, xhigh, max;
default **high**). Reviews are where a stronger model pays off most: findings caught
there save Claude fix rounds. The narrower re-check of rejected findings
(`ai-review --recheck`) uses `AI_RECHECK_EFFORT` (default **medium**).

### Supervisor settings

Used by the supervisor; validated before any agent runs and captured with the approved
run (a recovery resume keeps the approved values):

| Setting | Default | Valid |
|---|---|---|
| `AI_SUPERVISE` | `1` | `0` or `1` |
| `AI_SUPERVISE_PLAN_ROUNDS` | `3` | `0`-`9` |
| `AI_SUPERVISE_ESCALATE_ROUND` | `3` | `1`-`9` |
| `AI_SUPERVISE_ESCALATE_MODEL` | `claude-fable-5-1` | `[A-Za-z0-9._:-]{1,64}` |

Limits and planning (not supervisor settings): `AI_LIMIT_RELAUNCH_MAX` (config or environment;
`0`-`9`, default `2`, `0` turns the usage-limit relaunch off; see Usage limits) and
`AI_PLAN_ACK_SECONDS` (environment only, not read from the config file; `1`-`999999`, default `20`:
how long `ai-plan --detach` waits for the planning session to start, see Plan).

### Notifications

Set `AI_NOTIFY_CMD` to any command; it runs via `bash -c` with the message as `$1`
and can never break the workflow. For phone notifications, install the free ntfy app,
subscribe to a hard-to-guess topic, and put this in
`~/.config/ai-toolkit/config` (read, never sourced; only `AI_NOTIFY_CMD`, `AI_MODEL`,
`AI_LIMIT_RETRY`, `AI_LIMIT_MAX_WAIT`, `AI_REVIEW_MODEL`, `AI_REVIEW_EFFORT`, `AI_RECHECK_EFFORT`,
`AI_REVIEWER`, `AI_CLAUDE_REVIEW_MODEL`, `AI_CLAUDE_REVIEW_EFFORT`, `AI_DIAGNOSIS_MODEL`,
`AI_AUTO_RECOVER`, `AI_RECOVER_MAX`, `AI_LIMIT_RELAUNCH_MAX`, `AI_SUPERVISE`, `AI_SUPERVISE_PLAN_ROUNDS`,
`AI_SUPERVISE_ESCALATE_ROUND`, `AI_SUPERVISE_ESCALATE_MODEL`, `AI_REVIEW_ROUTE`, `AI_REVIEW_SMALL_LINES`,
`AI_REVIEW_RISK_PATHS`, `AI_REVIEW_RISK_WORDS`; environment variables win):

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
not a stale lock to delete. Relaunching while auto-recovery holds the lock is refused
without touching its records; the message names `auto-recovery (PID n)`, so wait for its
🔧 Recovered or ⛔ STOPPED notification or `kill n` first. (A recovery the watchdog started
after a crash gets the plain "Another runner/reviewer owns this checkout" message.)

Do not rely on this to survive machine shutdown or sleep as a live process. It
survives those events through saved files/checkpoints and a new session. No daemon
or automatic reboot startup is installed.

## Watch all pipelines

`ai-dashboard` shows every pipeline on this machine in one terminal. Run it from any
checkout's `.ai/bin/` or from `scripts/ai-dashboard` in this toolkit (a symlink works
too). It lists the pipelines registered in the host state directory and the runners
alive now, one card per checkout:

- The flow is nine boxes in order: Plan (Claude), Plan check (Codex), Plan revision
  (Claude), Setup (script), Build (Claude), Checks (script), Review (Codex), Triage
  (Claude), PR (script). Plan is ticked ✓ as soon as any pipeline record exists (a
  pipeline start marks it); a card with no record, an old record or an older toolkit
  leaves Plan unticked ("stage unknown"), never failed. A finished `ai-run --plan` shows
  the status `planned` with a `📝 <n> tasks` line and Plan check as the next box.
  The active box is double-bordered in its role colour (orange Claude, blue Codex, grey
  script); a ✓ under each finished box. Re-check shares the Triage box and is drawn in
  Codex's colour. The Build box is labelled with its task count (`Build 2/5`). The marker
  line under the active box shows the recorded detail, such as the task and model during
  Build, `round 3 · extra (…)` during an extra fix round, or `format retry` after a
  review's format retry. A usage-limit pause shows ⏸ on the box with the wait time.
- A stopped run shows its box in red with the stop reason (`⛔ …`). A stop before the
  first box (for example, the base moved) is marked `stopped before Plan check`.
- Keys in the terminal view: ↑↓ move, Enter shows or hides a card's details, `a` toggles
  old finished and idle runs, `r` refreshes, `q` quits and restores the terminal.
- The boxes, joined by `─`, need 120 columns; below that each card becomes one compact line.
- `ai-dashboard --once` prints the same view once (also used when output is piped).
  `--json` prints the snapshot (`state_root` and the runs) for other tools. `--all` shows
  finished or idle runs older than 24 hours; by default they are hidden, while crashed and
  needs-you runs are never hidden.
- Each run in `--json` also carries `pr` (the pull request URL from `.ai/state.md`'s
  `Next action:` line, else the last `pull request ready:` run-log line, else `''`) and
  `reviews`: `{'plan': …, 'code': …}`, each `{'blocker', 'major', 'minor', 'head'}` from the
  review report's single `Finding counts:` line (`head` is the short reviewed commit), or
  `null` when the report is missing, unreadable or ambiguous. Informational only; the
  details view (Enter) shows `pr:` and `reviews:` lines.
- `ai-dashboard --wait` blocks until a run changes (status, stage, observation state or a new
  notification line; edits to `tasks.md` alone do not count) and prints JSON
  `{state_root, cursor, timed_out, runs}` with only the changed runs; a checkout that
  appeared since the baseline counts, one that vanished does not, and runs hidden by the 24 h
  rule are still watched. `--timeout SECONDS` (default 3600), `--interval SECONDS` (default 2,
  at least 0.1). Exit 0 on a change, 1 on timeout (`timed_out: true`), 130 on Ctrl-C, 2 on a
  usage error. Pass the printed cursor back with `--since` so nothing between two calls is
  lost (a change made in between returns at once):
  `cursor=$(ai-dashboard --wait | jq -r .cursor); …; ai-dashboard --wait --since "$cursor"`.
  `--wait` cannot be combined with `--once`; it writes nothing.
- Run it with the same `AI_STATE_DIR` or `XDG_STATE_HOME` as the pipelines and the
  watchdog timer: it only lists the registry of that state root. The default is
  `~/.local/state/ai-toolkit`.
- A runner started with `AI_DASHBOARD_IGNORE=1` in its environment is not listed unless its
  checkout is registered; the toolkit's own test suite sets it so its fixture runs stay hidden.
- Keep it in tmux beside your runs: `tmux new -s dash ai-dashboard`.

The dashboard is read-only and advisory. It writes no file, takes no lock and changes no
run. Its inputs are the records under each checkout's `.ai/local/` (`observation.json`,
`notifications.log`, `pipeline.active`), which agents can write, so they show status
only; they never authorize anything. Text from those records is sanitised before it reaches
the terminal.

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
| `scripts/ai-plan` | Starts a headless planning session (`ai-run --plan`), in the foreground or `--detach`ed with a confirmed start (the detached log is written by `scripts/lib/workflow.py exec-logged`) |
| `scripts/ai-review` | Revision-bound, read-only Codex review (Claude fallback at its limit) and report preservation |
| `scripts/ai-pipeline` | Hands-off implement → review → triage/fix → PR → notify, resumable |
| `scripts/ai-dashboard` | Read-only view of every pipeline on the machine (TUI, `--once`, `--json`, `--all`); see [Watch all pipelines](#watch-all-pipelines) |
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
python3 tests/run_parallel.py                 # parallel batches, works from any directory
AI_TEST_WORKERS=4 python3 tests/run_parallel.py
python3 tests/run_parallel.py --collect-only  # print the number of tests only
python3 -m unittest discover -s tests         # serial, what the gate runs today
python3 -m unittest discover -s tests -k parallel_runner   # one group by name
```

`tests/run_parallel.py` discovers the same tests as the serial command and deals the sorted
IDs into interleaved batches pulled by `AI_TEST_WORKERS` workers (default: the CPU count minus 2,
at most 14, at least 1; the first output line is `Workers: W (source)`; six batches per worker, so neighbouring and often similarly slow tests land in
different batches and no worker idles while another works through a slow cluster). Each
batch runs as `python3 -m unittest` in its own process. On Linux the runner is a child
subreaper: processes the batches orphan stay its descendants and it reaps them. A stop (a
worker error, an interrupt or SIGTERM) then terminates every descendant, GNU `timeout` groups
and detached sessions included, and waits until none is alive; if some survive it prints
`run_parallel: could not terminate descendants: <pids>` (or `unknown (descendant scan failed: …)`
when `/proc` could not be scanned) and exits non-zero. The runner fails when a batch fails
or crashes (listing that batch's test IDs), when it collects no tests, or when the batches
ran a different number of tests than it collected. Batches always run without colour (whatever `FORCE_COLOR`, `NO_COLOR` or
`PYTHON_COLORS` the caller sets), and the summary parser ignores ANSI escapes. Switching
`.ai/validate` to the parallel runner is a gate change that a human approves.

Every run ends with a timing report before the `Ran N tests …` line: on Python 3.12+ the
batches run with `--durations 0` and the runner lists the 15 slowest tests with their
seconds, then `Test time: <sum> s across <workers> workers; worker busy: <min>–<max> s`
(the busy range shows how evenly the batches spread). Older Pythons get the busy range
only. Duration lines that do not parse are ignored. After each finished batch the runner prints
`Progress: d/N batches, t tests, f failing, E s`. When a SIGTERM or interrupt stops the run it
first prints `run_parallel: stopped after E s: d/N batches finished (t tests); running: <batch
numbers or none>; failing: <batch numbers or none>` and the slowest finished tests, then exits
as before. The report also lists, after the slowest 15, the tests over the per-test budget
(`Over the per-test budget of B s: n tests`, slowest first): `AI_TEST_BUDGET` (a number greater
than 0, otherwise the runner stops with an error), else 30 s times the timeout scale below. The
list never changes the exit code. A new or changed test over the budget is made cheaper, or its
task result says why.

Fixture I/O is kept cheap: test fixture repositories run git with `core.fsync=none` and
`gc.auto=0` (test harness only; the toolkit scripts never set them), and when the caller sets
no `TMPDIR` and `/dev/shm` is a writable tmpfs with 1 GiB free, `run_parallel.py` gives every
batch a temp directory there (`Temp dir: /dev/shm/ai-tests-… (tmpfs)`, removed after the run).
The directory is probed by running a script from it; a `noexec` mount falls back to the
default temp dir. `AI_TEST_TMPFS=0` turns it off (`AI_TEST_TMPFS_DIR` replaces `/dev/shm`, for
the tests only).

Test runs keep host state out of the real registry (FL-33): `tests/isolation.py`, imported first by
every test module, points `AI_STATE_DIR` and `XDG_STATE_HOME` at throwaway temp directories unless a
parallel worker already set a temp one. `run_parallel.py` then fails the run (`self-check registered
fixture runs in the real registry: …`) if the real registry lists a checkout under its temp dir.

Test timeouts are all scaled by one factor (`tests/timeouts.py`): `AI_TEST_TIMEOUT_SCALE`
when set (a number greater than 0, otherwise the tests stop with an error), else 2 when
`CI=true` (GitHub's runners are several times slower than a workstation), else 1.
`ai-pipeline` and `ai-recover` (which execs the resumed pipeline) run under the longer
pipeline timeout. A command that times out fails with its command line and the tail of its
output.

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
  (e.g. a killed standalone `ai-run`), still so at a probe at least 5 minutes after the
  first one that saw it (a planning session is never stalled);
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

The first probe runs 2 minutes after the timer starts (after boot or after
`--install-timer`), so installing it just before starting a pipeline raises no alarm.
Timers installed before this change fire at once after install: run `--install-timer`
again to update the host copy and unit.

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
