# Workflow contracts and operating notes

## Durable records

The spec defines requested behavior. The plan describes how to deliver it. Tasks
carry independently understandable work and verification. State is a compact
summary; handoff is the next person's operating guide. The append-only run log
records outcomes, not reasoning traces. Source, deterministic checks, and Git
settle disagreements with summaries. All these records are ordinary Markdown.

An optional external project knowledge base (for example an Obsidian project
folder) holds architecture, decisions, and human todos. `.ai/` is operational
state in Git and must remain sufficient for recovery without the vault. Fill the
optional Project knowledge base section in CLAUDE.md; pass `--knowledge-dir DIR`
to grant the unattended invocation access to that existing folder. Nothing is
hardcoded or discovered globally. Preserve human todos until the human confirms
completion; local docs can link/summarize vault knowledge rather than duplicate it.

Task parser contract:

- Headings `## T001 — Title` (or `## T001 - Title`), stable T + 3-or-more digit IDs.
- Exactly one `Status: TODO|IN_PROGRESS|BLOCKED|DONE` line per task.
- Exactly one `Dependencies: none` or comma-separated earlier IDs line.
- Required `###` sections match the example in `.ai/tasks.md`.
- IDs are unique; dependencies exist earlier, preventing cycles; at most one
  IN_PROGRESS; DONE/IN_PROGRESS require DONE dependencies. Code-fenced examples
  are ignored. Invalid queues stop the runner rather than being guessed at.

The first eligible TODO is selected, with an eligible IN_PROGRESS taking priority
for recovery. BLOCKED tasks do not count as complete (a block without a failing check whose
host gate passes is retried once per run: "Gate-only block retry" below). Independent work may proceed;
when no runnable work remains and the queue is incomplete, human intervention is
needed. A syntactically valid DONE is not semantic proof of acceptance: Claude must
record verification and Codex must challenge it.

Phases: planning → implementing → ready_for_review → fixing_review →
ready_for_acceptance. `blocked` describes a stop needing resolution. Review and
acceptance phases are not inferred as passed simply because a CLI succeeded.
The runner records ready_for_review, never claims that the human accepted the work.

## Validation and evidence

`.ai/validate` is the one real project gate. `.ai/bin/ai-check` invokes it from the
root with Bash error propagation and GNU timeout (default 1800 seconds;
`AI_CHECK_TIMEOUT` overrides; time spent waiting for the validation lock counts against it). Use non-writing format/lint checks and deterministic
non-watch tests. Tests may write ignored build/cache artifacts. Nonignored project
changes during the gate cause a failure, even if the command itself exits zero.

Gate speed (FL-11, FL-23): test suites can run in parallel. A stdlib-only runner
`tests/run_parallel.py` discovers every test ID, deals the sorted IDs into interleaved
batches pulled by `AI_TEST_WORKERS` workers (default `min(8, cpu count)`, six batches per
worker), and runs each batch with `python3 -m unittest`. On Linux it is a child subreaper
(FL-27): orphans of the batches are reparented to it and reaped without touching a batch's
exit status (it waits only for specific non-batch zombie pids, never `waitpid(-1)`). A stop
(worker error, interrupt, SIGTERM, also one that arrives while the workers are still being
started) is owned by its first caller: it signals the batch groups
and walks the `/proc` ppid tree below the runner, SIGTERM then up to three SIGKILL rounds
(each pid checked against its recorded start time), then a bounded completion barrier until
`/proc` shows no live descendant; survivors are printed to stderr and fail the run. The
batch groups are signalled before any scan, `/proc/<pid>/stat` is read as bytes (a process
name is arbitrary bytes), and a scan that fails (also a `/proc` that exists but cannot be
listed: an empty table proves nothing) never aborts the stop: the barrier then
reports `unknown (descendant scan failed: …)` and the run fails; a reap round that cannot
list `/proc` is skipped. No
adopted zombie is reaped until the stop has finished, so no pid is reused meanwhile. It exits non-zero when a batch
fails (its test IDs are listed), crashes, collects zero tests, or when the batches ran a
different number of tests than it collected. On Python 3.12+ it reports the 15 slowest
tests, the summed test time and each worker's busy time. Batches run
without colour whatever the caller's `FORCE_COLOR`/`NO_COLOR`/`PYTHON_COLORS`, and the
summary parser strips ANSI escapes.
Switching `.ai/validate` to the parallel runner is a gate change that a human approves.

Evidence in ignored `.ai/local/validation.json` includes outcome, timestamp, exit
code, log path, HEAD at check time, and a SHA-256 digest of project file paths,
contents, modes, and symlinks. It includes tracked and nonignored untracked files,
including spec, plan, tasks, and validation tooling. Clean submodules are represented
by their HEAD; dirty submodules are rejected. It omits `.ai/local/`, reviews, compact
state, handoff, and run log so normal bookkeeping does not invalidate source checks.
Ignored source cannot be validated by this digest; keep real source tracked.
`stamp outcome` reads that file without following a symlink or blocking (regular file, at most
64 KiB) and prints `WORD DIGEST`: `none` (missing, unsafe, unreadable or not a JSON object),
`running`, `pass`, `changed` (FAIL with exit 0 because content changed) or `fail`, and the
SHA-256 of the bytes read (`-` when nothing was read); it always exits 0 (FL-32).

A new gate invalidates old success before execution; failures/interruption never
retain a green stamp. Review requires a current successful content digest. Commits
of unchanged content don't invalidate evidence. Environment/dependency/service
changes are not represented by the digest: rerun checks when those change or when
evidence is old. This is a local convenience gate, not tamper-proof attestation or CI.

Session budget (FL-19): without `--sessions`, `ai-run` allows `max(16, unfinished tasks + 2)`
sessions, computed on every call (so each pipeline call, recovery rerun and fix round covers
the tasks it faces) and printed as `Session budget: N`. `--sessions N` overrides it. `--triage`
and `--revise-plan` run no implementation sessions and print no budget.

Dependencies (FL-01): when `ai-run` starts and a task will run (not `--triage`), the host
runs `.ai/ci-setup` if `deps-status` reports it missing/stale (no `.ai/local/deps.json`
stamp, `.ai/ci-setup` changed, an `# ai-deps-inputs:`/default lockfile changed, or an
`# ai-deps-outputs:`/`node_modules` dir is missing or is not a directory). Limit `AI_DEPS_TIMEOUT` (default 1200 s)
capped by the remaining run time; output in `.ai/local/deps-*.log`; no tracked file written.
After every installer exit the gate digest and `tree-snapshot` (HEAD, index, every
non-ignored file) must be unchanged, reported ahead of the exit status; only then is the
stamp recorded. These stops start with "Dependency setup" and `ai-recover` always
escalates them. Dependencies a task changes mid-run are installed at the next start;
`ai-recover`'s `commit_and_rerun` also runs this step (on the dirty tree) before its
`ai-check`, and a failed or file-changing install escalates with no commit.

The runner independently reruns validation after each DONE task and at the end.
If a post-task gate fails, it restores that task to IN_PROGRESS and leaves evidence
for repair. If no progress was checkpointed, it stops rather than spending an
unbounded number of retries. Claude's in-session loop can fix ordinary failures;
three repeated attempts on the same failure should produce a blocker and handoff.

Every accepted DONE checkpoint and the final `record review handoff` commit must contain
exactly the bytes validation hashed: after the runner's bookkeeping commit the tree must
be clean, the stamp current and the committed bytes equal to the validated files on disk,
otherwise the run stops with "The checkpoint of <task|final handoff> differs from the
validated content" (nothing is reset; BLOCKED tasks are not checked). Limitation:
repositories whose content passes clean/smudge or eol filters (Git LFS, `text=auto` with
CRLF files, `ident`) stop with "differs from the validated content"; they are not
supported by this check.

## Permissions and safety

The primary boundaries are an approved scope, inspected local command permissions,
feature branches, Git checkpoints, deterministic checks, and explicit human control
of external consequences. The runner rejects main/master/develop/development/
production/release and release/* branches and checks that its starting branch hasn't
changed between sessions. Adapt that protected list in toolkit code for other names.
It does not install global Git hooks or prevent an interactive tool from changing branches.

At `--approved` time, the runner computes a SHA-256 digest of `.ai/validate`, all
files/directories under `.ai/bin/` and `.ai/prompts/`, `.ai/permissions.allow`, and
`.claude/settings.json` (including its absence). The baseline is read-only shell
state; `.ai/local/approved-gate.sha256` is only an inspection copy, never trusted
for verification. An inline verifier loaded before the agent starts checks paths,
contents, modes, additions/removals, and symlinks. It uses isolated Python so local
modules cannot replace its standard-library imports. It runs before each session,
immediately after the CLI returns (before using any local helper), after host
validation, and after runner checkpoint commits. Persistent changes stop the run,
even when the agent committed them. A legitimate gate change requires inspection,
checkpointing, and a new explicit approval; the baseline is never refreshed mid-run.
No project helper runs after the gate is known changed or unreadable: every gate comparison
(`ai_gate_check` and `ai_guard_verify` in `common.sh`, the pipeline's approval and resume
checks, `ai_deps`, each ai-recover comparison) sets the shell variable `AI_GATE_BROKEN`, and
the record helpers `ai_observe` and `ai_notify_log` (the checkout's `workflow.py`) then skip
themselves; the ⛔ notification (your `AI_NOTIFY_CMD`) is still sent. The flag is never
exported and never set inside a command substitution, which would set it in a subshell only.
Project deny rules prevent Edit/Write on gate tooling, validation, prompts, and
permission/settings files. Existing project settings need those rules merged.

Claude's runner uses `dontAsk` and explicit `.ai/permissions.allow` entries. It loads
project settings and disables MCP integrations for that invocation. Necessary commands
outside the allowlist become denials. The template allows `chmod +x` (and no other chmod
form) so a session can make a script it created executable. After every implementation session, including
one that timed out or failed (before that stop, so `ai-recover`'s rerun gate sees the bit), the
host also gives back the executable bit git records (`100755`) to a tracked script that lost it
(`workflow.py exec-bits`; never a gate file (the guard's protected-path list), and only a
regular file reached without following any symlink, so a directory a session swapped for a
symlink never leads outside the checkout). Denials are logged and the run continues
(`.ai/local/denials.log`); a session that cannot work around one ends without a checkpoint
and the run stops there. Inspect the log and adjust permissions yourself.

Scratch files: sessions put throwaway files only under `.ai/local/scratch/` (ignored by Git).
The host empties `.ai/local/scratch` before and after every session (`workflow.py
clear-scratch`) and never follows a symlink there: a symlink is removed as a link, and an unsafe
`.ai` or `.ai/local` is left alone with a warning. Decision: `rm` stays off the allowlist
(`Bash(rm *)` cannot be limited to untracked paths), so `permissions.allow` is unchanged and
sessions are told not to delete files.

| Mode | May do | May not do |
| --- | --- | --- |
| Interactive Claude | Your normal permissions (may ask); whole queue; local checkpoint commits | Merge, deploy, push without your say-so |
| ai-run | One task per fresh `dontAsk` session; gate reruns; bookkeeping and validated-leftover commits | Change the gate, push, open PRs, merge, deploy |
| ai-pipeline | `ai-run` plus reviews, triage, pushing the feature branch, opening/updating the PR, `ai-recover` | Force-push, push `main`, merge, deploy |
| ai-watchdog | Probe, notify, read-only diagnosis, `--recover` via `ai-recover` | Restart or repair anything itself |
Default entries support reading/editing, Git inspection/staging/local commits, and
the canonical validation gate. Add normal builds/tests/dependency commands as needed.
Installed Claude project deny rules are preserved if already present, so reconcile
existing settings before running. Interactive Claude uses your own normal settings.

The installed Claude Code 2.1.288 loader gates user CLAUDE.md and user rules on the
enabled user source, so `--setting-sources project` excludes them; omitting local
also excludes CLAUDE.local.md. This conclusion comes from installed source inspection,
not a live headless inference. Earlier versions had a
[reproduced filtering bug](https://github.com/anthropics/claude-code/issues/87590),
so recheck after upgrades. The [memory docs](https://code.claude.com/docs/en/memory)
explain instruction locations and directory access. Explicit project instructions
and `--knowledge-dir` keep vault integration independent of global memory loading.
Do not broaden setting sources to obtain a notes pointer: that also loads user
permissions/hooks/integrations. No global or desktop configuration is changed.

**This is not a security sandbox.** Read/Edit/Write, allowed shell commands, package
scripts, validation scripts, Git hooks, and project code can access the machine or
run arbitrary commands. Prefix deny rules aren't a complete defense against shell
composition or indirect execution. Instructions are behavioral policy, not enforceable
production isolation. Use trusted repositories, inspect scripts/settings, keep secrets
and production credentials absent, and use an externally isolated environment for
untrusted code. No bypass-permissions mode is enabled by the toolkit.

The integrity checks catch changes present at boundaries, not transient edits
restored before a check, races, malicious subprocesses, or replacement of system
executables. Protected files still live in the checkout; an OS sandbox is required
for stronger isolation. A new `--approved` invocation trusts the current inspected
gate, so never reapprove automatically after a gate-change error.

Commit-hook bypass flags (`--no-verify` and `-n`, in common argument positions) are
denied. Claude must stage explicit paths with `git add -- path/to/file ...` rather
than `git add -A`, `--all`, or `.`. The broad Git tool patterns retain residual risk:
alternate argument arrangements, Git configuration/environment, indirect shell
commands, and bulk staging are not exhaustively prevented. Inspect checkpoint
diffs and don't treat deny patterns as a complete Git policy enforcement mechanism.

Claude commits selected task work. Automatic checkpoints stage the session's output except
secret-looking files (the runner's commit of validated leftovers; see "Checkpoint scope"
below); bookkeeping is committed separately, preserving normal Git hooks. A
failed hook, absent Git identity, or dirty checkpoint stops the run. The two tools use
a kernel checkout lock, but direct CLI sessions do not: don't mutate a checkout while
another agent is using it. Git doesn't protect uncommitted changes from power loss;
short tasks and frequent checkpoints limit that exposure.

Allowed autonomously within scope: local reads/edits/tests/refactoring/builds, necessary
normal dependency installs with suitable permissions, state updates, local feature-branch
commits. Human required: meaningful external/irreversible risk, protected-branch merge,
deployment/production changes, cloud resource deletion, destructive production SQL,
credential rotation/revocation, remote publishing, shared-history rewrites, security
policy changes, and final acceptance. Never push secrets, suppress failures, or weaken
security to get a pass. Only `ai-pipeline` pushes: the pipeline pushes the feature branch
and opens the pull request (never force, never `main`). Nothing merges or deploys.

## Interruption, limits, and recovery

tmux handles terminal closure. A reboot, timeout, rate limit, network failure,
or crash can stop a session. Logs and partial changes remain on disk; completed
commits remain in Git. A fresh resume reads instructions/spec/plan/tasks/state/handoff,
recent logs, history, and diffs. There is no dependency on provider-specific conversation
IDs, so model changes, days-long gaps, or temporary Codex debugging are recoverable.

Clean checkpoints can enter the runner directly. Dirty interrupted trees must first be
reconciled, validated, and committed in a supervised resume session; nothing is reset
automatically. If tools crashed mid-state-write, atomic helper writes reduce corruption,
but agent-written Markdown still needs inspection. Invalid records fail explicitly.

Limits bound new agent invocations and validation execution. GNU timeout terminates a
timed-out command, with a 10-second forced termination grace. Usage limits pause and resume:
the scripts read the reset time, sleep and retry the same step (`AI_LIMIT_RETRY`,
`AI_LIMIT_MAX_WAIT`); pushes retry 3 times; `ai-recover` and `ai-watchdog --recover` handle
stops and crashes. A timed-out implementation session whose task is IN_PROGRESS with
uncommitted work gets its work committed (only if the full gate passes) and one rerun per task
per run, without a decision session (see "Session timeout on an IN_PROGRESS task"). A limit beyond the wait budget stops with an unchanged message and first
records `<Agent> <reset epoch or 0>` in `.ai/local/limit-stop` (`workflow.py limit-stop-write`,
through the pinned `.ai/local` and an exclusive `O_NOFOLLOW|O_NONBLOCK` temp file, never a
shell redirection). `workflow.py limit-stop` prints `<Agent> <relaunch epoch>` only when
`last-error` is exactly that one-line message and `limit-stop` names the same agent and is at
most 120 s older (relaunch: reset + 60 s, `now + AI_LIMIT_RETRY` for reset 0, `now` once
passed). The run manifest's optional `limit_relaunches`, `limit_relaunch_at`, `limit_head`,
`limit_tree` (the `worktree-digest` at scheduling), `limit_task`, `limit_stage` (the stopped
pipeline stage, 1–40 printable ASCII characters) and `limit_resume` (`{"head", "tree", "task"}`)
hold the relaunch schedule (`run-manifest limit-schedule AT CAP STAGE`, which records HEAD and
the digest itself and copies the run's `task` record into `limit_task`,
`limit-due`, `limit-at`, `limit-hold`, `limit-claim`, `limit-verify`, `limit-arm`,
`limit-armed`, `limit-task`, `limit-disarm`, `limit-count`; schedule, hold and claim give back
the attempt `ai-recover` reserved; a human start and `clear-attempts` drop them, and the `task`
record too; cap
`AI_LIMIT_RELAUNCH_MAX`). `run-manifest task` prints the recorded `task` (exit 1 silently when
there is none). The optional `timeout_reruns` (unique task IDs, at most 200; any other shape
invalidates the manifest) holds the tasks whose timed-out session was committed and rerun once:
`run-manifest timeout-rerun ID` appends ID, or fails `session timeout: ID was already committed
and rerun once in this run` and writes nothing. A human start drops the list; `clear-attempts`
keeps it, so a resumed pipeline never resets "once per task". `gate_unblocks` has the same shape
and lifetime for the one gate-only block retry per task (FL-32): `run-manifest gate-unblock ID`
appends ID, or fails `gate-only block: ID was already retried once in this run` and writes
nothing. `rulings` has the same list rules and lifetime, with `KIND:KEY` items (BR-01):
`run-manifest ruling KIND KEY` (KIND `queue-order`, `task-sections`, `disposition-cell` or
`flow-line`; KEY `[A-Za-z0-9._-]{1,48}`) appends it, or fails `ruling KIND for KEY was already
made once in this run` and writes nothing. `ruling-row KIND WHAT WHY COST` prints the run-log
action cell `Ruling (KIND): WHAT. Why: WHY. Cost if wrong: COST.` with `|`, backslashes and line
breaks turned into spaces, space runs collapsed, at most 400 characters (no caller yet). A limit-only stop inside `ai-pipeline` is not escalated: `ai-recover`
schedules a relaunch (see "Usage-limit relaunch" in the recovery contract), exits 75 with a ⏸,
and the watchdog timer (`--recover`) starts it after the reset. The relaunch accepts only the
checkout it stopped with, verified before anything else touches it (see "What a relaunch
accepts"). No infinite loop, boot startup, or monetary spending guarantee is added.

**What the resumed run does with preserved work.** When the limited session left uncommitted
task work, the relaunch arms it (`limit_resume`) and the resumed `ai-pipeline` and `ai-run`
accept exactly that tree through one predicate, `clean_or_armed` (`scripts/lib/common.sh`: a
clean `git status`, or a resume whose checkout `run-manifest limit-armed` finds equal to the
arm with no stage open), at every clean-checkout check up to ai-run's `limit-disarm`. A settled
re-check (status `none`, or `verified` with or without recorded disputes) does not block the
resume, and neither does a plan review the run already passed: the armed resume re-enters at
implementation. Nothing is committed and no tracked file is written before ai-run validates:
the disarm is the last statement before the armed checkpoint (full `ai-check`) or the bound
task's session, and after it the normal rules apply. Inconsistent review records on the armed
tree (a `pending` re-check, an uncommitted re-check report or dispute file, a dispute the host
would still have to record) fail closed with `Re-check of rejected findings: preserved task
work carries uncommitted review records; inspect them.`: one ⛔, nothing committed, the arm and
the tree kept, also with auto-recovery on. The contract is the comment block before
ai-pipeline's start check and is tested as a matrix of resume-path states
(`test_limit_relaunch_accept_*`; details under "How the resumed run continues preserved work"
in the recovery contract).
Git hooks remain active and may consume additional time. Monitor your provider usage;
logs may contain sensitive source, so `.ai/local/` stays ignored and should be handled
with the same care as other local transcripts.

## Plan stage (`ai-plan`, `ai-run --plan`)

`ai-plan PROMPT_FILE [--revision] [--model NAME] [--session-timeout S] [--knowledge-dir DIR]
[--read-dir DIR]... [--detach]` is the supported way to start a planning session (mission
control: `ai-plan PROMPT --read-dir ~/zWiki --read-dir ~/Projects/wt/plans --read-dir
~/Projects/wt/research --detach`; the session limit stays 3600 s). It checks only its own
arguments: the prompt file exists, is regular and readable, and the prompt, `--knowledge-dir`
and every `--read-dir` are resolved against the caller's working directory (with `ai-run`'s
wording for a missing directory) before `ai_root` changes to the checkout root; every other
option goes to `ai-run` unchanged, in the original order. Like every toolkit command it then
runs `ai_root` (the `paths` check refuses a symlinked `.ai` or `.ai/local` before anything is
launched, then `.ai/local` is created: `setup-project` does not create it).

- Foreground: `exec ai-run --plan PROMPT …` (same PID, so the dashboard, watchdog and lock see
  an `ai-run` runner).
- `--detach`: `setsid python3 -I workflow.py exec-logged plan-<UTC stamp>-<8 hex>.log --
  ai-run --plan PROMPT … </dev/null &`. A non-interactive shell's background job is not a
  process-group leader, so `setsid` execs without forking, and `exec-logged` creates the log
  exclusively in the pinned `.ai/local` (no symlink or FIFO followed) and execs the runner on
  it: `$!` is the runner. Then every 0.2 s for at most `AI_PLAN_ACK_SECONDS` (default 20):
  `.ai/local/observation.json` with `stage: planning`, `state: active` and `pid` equal to the
  runner's → `Planning session started: pid N, log PATH`, exit 0; the runner exited with 0 and
  the observation is its own `stage: planning`, `state: done` (the plan finished between two
  polls) → the same `Planning session started` line, exit 0; the runner exited otherwise →
  `ai-plan: the planning session ended early (exit N); last lines of PATH:` plus the log's last
  10 lines (or `(no log was created)`), exit N (at least 1); neither → `ai-plan: could not
  confirm the planning session started within N s (pid N, log PATH).`, exit 1. The runner is
  never killed; it is disowned before `ai-plan` exits.

`ai-run --plan PROMPT_FILE [--revision] [--read-dir DIR]...` writes the plan in one headless Claude session before
any pipeline runs. The prompt file is resolved when the arguments are parsed (a missing,
unreadable, non-regular or larger than 200 KB file stops before anything else). The run refuses
`AI_PIPELINE`, `--triage`, `--revise-plan`, `--since`, `--base`, `--sessions` and `--run-timeout`
(by "given" flags, so a default value never slips through); `--approved` is not required because
no project allowlist is used.

Order: supervisor settings, Claude present, checkout root, state root, checkout lock, branch
(protected branches refused), HEAD exists, `workflow.py plan-scope HEAD` (no uncommitted work
outside the plan records; the queue itself is not checked yet, a first plan starts from the
template), `plan-keeps-done HEAD --baseline .ai/tasks.md` (parses the START and working-tree
queues, so a malformed task heading stops before a session is spent), gate digest. Then the host registers the checkout for the dashboard, records
`observe step planning "<model> · first plan|revision"` and notifies `📝 PLANNING`. The session
(model `--model` or `opus`, limit `--session-timeout` or 3600 s) gets `.ai/prompts/plan.md`, the
objective and a `PLANNING CONTRACT`; its tools are `Read,Glob,Grep,Edit,Write` and its
`--allowedTools` are exactly `workflow.py plan-allowlist` (Edit/Write of `.ai/project-spec.md`,
`current-plan.md`, `tasks.md`, `state.md`, `handoff.md`, `reviews/dispositions.md`). A usage
limit pauses on the `planning` stage and resumes. Just before the session the host copies the
working-tree `.ai/tasks.md` to a `mktemp` baseline under `$TMPDIR` (outside the checkout and
the planner's allowlist; removed by the exit handler).

`--read-dir DIR` (repeatable, `--plan` only; elsewhere `--read-dir only applies to --plan.`)
gives the session read-only reference directories such as plans or research. Each must exist
(`Read directory not found: …`) and is resolved with `pwd -P`; a resolved path containing `*`,
`?`, `[`, `]`, `(`, `)`, `,` or a newline stops with `Invalid --read-dir path: …` before any
session. Each directory adds `--add-dir DIR` (beside the knowledge base's) and the allow entry
`Read(//DIR/**)` (Claude Code's absolute form); no Edit or Write entry is added, so
`plan-scope` is unchanged. The contract names them: `Read-only reference directories: <list>.
Read them as needed; never edit them.` `--knowledge-dir` stays the knowledge base option.

After the session: gate verified, branch unchanged, `plan-scope START` (the run log is also
allowed, for the exit handler's stop line), `plan-keeps-done START --baseline <copy>` (every
task DONE when the session starts, committed or not, i.e. DONE in START's `.ai/tasks.md` or in
the baseline copy, keeps its raw block; a task DONE in both must match the baseline block;
fenced lines included and trailing blank lines ignored;
unconditional, so a forgotten `--revision` cannot bypass it: `Planning: DONE task T00x was
changed or removed`), `tasks fill-sections` (a missing `### Likely affected modules` /
`### Result / notes` of a TODO task is added, `Task queue: added missing sections: …` printed),
`tasks reorder` (a task placed before one it depends on is moved after it,
block text unchanged, `Task queue reordered (dependencies first): …` printed; a cycle, unknown
ID or prose in `Dependencies:` stops with `Planning: task queue is invalid: …`) and `tasks check`
(`Planning: task queue is invalid: …` with the same text as `ai-task check`). Success records
`observe planned "<N> tasks"`, notifies `📝 Plan ready` and exits 0. Any stop after the start
records `observe stop plan <first line of last-error>` and one ⛔ notification, unless the gate
changed (then no project helper runs and the record stays `active`). The run never commits and
never reverts the session's edits: the human reviews and commits the plan.

## Plan review rounds

Each plan review is a round, numbered from host records, not commit subjects: after the host
commit `chore(ai): record plan review` the pipeline (and a hand-run `ai-review --plan`) runs
`workflow.py plan-rounds sync BASE`, which appends `{commit, report_digest, plan_digest,
blockers, majors, minors}` to `plan-rounds-<branch hash>.json` in the host review store, once
per report and only for a commit whose `plan.md` matches the stored binding. `BASE` is the
pipeline's `base_sha`; by hand it is the merge-base with `--base REF` (default `main`). Only
records whose commit is in `BASE..HEAD` count, so a merged-then-recreated branch name starts at
round 1; an agent commit with the same subject never adds a round. A branch without a store is
initialised once from existing host-subject commits (this can only raise the number). `plan-rounds
count|current BASE` read the number; `plan-history BASE [--count]` renders the earlier rounds'
BLOCKER/MAJOR findings paired with their sections of `.ai/reviews/plan-dispositions.md`. History
is context only and never approves, counts or skips anything.

Plan-review round sections (used by `ai-run --revise-plan`, below). `workflow.py start-plan-dispositions
BASE` appends `## Plan review round <n> (report <digest>)`, a `Plan review HEAD:` line and an
empty table to `.ai/reviews/plan-dispositions.md` (creating it with a host preamble), unless the
last section already is that header. `plan-dispositions-check --since START --base BASE [--fresh]
[--questions]` validates only that section: unique and last; the text above it unchanged since
START (START's text above the same header, else START's whole file, else the exact preamble);
one row per BLOCKER/MAJOR finding of the verified current plan review (MINOR optional, unknown
IDs and duplicates rejected); `accepted` names existing tasks, `rejected` has evidence,
`needs-human` has a question (both at least 15 characters); from round 3 a same-section
`Convergence:` line. `--fresh` also requires accepted tasks to be TODO, every task that existed
at START to keep its status and new tasks to be TODO. It prints `accepted=a rejected=r
needs_human=h`; `--questions` prints at most 3 needs-human questions, one line of at most 300
characters each (cut at a sentence or word boundary, ending in `…`), plus `(+k more in .ai/reviews/plan-dispositions.md)`. `plan-revision-scope
START` fails when anything outside the plan revision records (spec, plan, tasks,
plan-dispositions, handoff, state, run log) changed since START.

Plan revision (`ai-run --approved --revise-plan [--since COMMIT] [--base REF] [--model M]`; the
pipeline calls it through the plan revision stage below). It needs a verified plan review with BLOCKER+MAJOR > 0 and no task DONE
since the base (`tasks newly-done BASE` empty, so a follow-up batch whose earlier tasks were
already DONE at the base can be revised; otherwise `Plan revision: a task is already DONE since
the base (T…)`, first three ids; a helper error stops too),
syncs and reads the round (`plan-rounds current BASE`, BASE = merge-base with `--base`, default
`main`) and refuses a report that already has a revision record (`this plan review was already
revised; review again (ai-review --plan)`). When the section already validates (an interrupted
revision), it records it without a session; otherwise it appends the section, commits it as
`chore(ai): open plan dispositions` (the only uncommitted change it accepts beyond bookkeeping
is exactly that host section, `start-plan-dispositions BASE --pending`: a crash before this
commit), and runs one Claude session (default model `opus`) with
`--tools Read,Glob,Grep,Edit` and `--allowedTools` from `workflow.py plan-revision-allowlist`
(Read, Glob, Grep, and `Edit(./…)` of spec, plan, tasks, plan-dispositions and handoff; nothing
from `.ai/permissions.allow`, no Bash or Write). The prompt is `.ai/prompts/plan-revision.md`
plus the host `REVISION CONTRACT` (round, section header, editable files, the Convergence rule
from round 3, "do not commit") and `PREVIOUS PLAN ROUNDS`; git context the session cannot fetch
itself (plan history, recent diffs of the plan records) is written to the ignored
`.ai/local/revision-context/` and removed afterwards. Afterwards the host checks that
`plan.md` and the gate are byte-identical, `tasks fill-sections` (adds a missing `### Likely
affected modules` / `### Result / notes` to new TODO tasks and prints `Task queue: added missing
sections: …`; any other missing section still stops), `tasks reorder` (the contract tells the session to
place new tasks before the first task that depends on them; the host repairs a prerequisite
appended after its dependents, and the reordered queue goes into the revision commit), `tasks
check` (either failure stops with `Plan revision stage: task queue is invalid: …`, which
`ai-recover` escalates at once: no recovery session, no second revision), the scope,
`plan-keeps-done START` (every block DONE at START byte-identical; else `Plan revision stage:
DONE task T… was changed or removed`, escalated the same way) and
`plan-dispositions-check --fresh`, then in this order: `ai_log` (`plan revised (round n): accepted a, rejected r,
needs-human h`) and the state line, `git add` of the plan revision records, `git commit
--allow-empty -m 'chore(ai): record plan revision'`, the gate check, and ONE host record
`plan-revisions record BASE HEAD --accepted a --rejected r --needs-human h` (bounded questions on
stdin) in `plan-revisions-<branch hash>.json`: `{commit, report_digest, round, accepted,
rejected, needs_human, questions}`. Nothing writes to the checkout after the commit, so a
following `ai-review --plan` starts on a clean checkout. The outcome log gets a `plan_revision`
line (not part of `ai-status --outcomes`). A crash after the commit but before the record
leaves the stage `pending`: the resume records the revision with a second host commit (and a
second run-log line); only the host record counts.

`plan-revisions revised` exits 0 when the verified current plan review has a reachable revision
record, 1 when not (`plan-revisions outcome`: the same, printing `round accepted rejected
needs_human`); `plan-revisions decision` exits 0 and prints the stored questions when that
record has needs-human rows, 1 when not. Both exit 2 when the store is unreadable, or when the
plan review does not verify while the last revision is waiting for a human decision (fail
closed); with no store, or no outstanding decision, an invalid report takes the normal review
path. A needs-human decision clears only with a new report: answer the question in the plan
records, commit, and run `ai-review --plan` by hand. `ai-pipeline` runs this decision check
on every start (after the startup stage dispatch and `reconcile_disputes`, whether or not the
plan-review loop below runs), in each loop pass, and again before the implementation loop:
`--skip-plan-review` or a DONE task skips only the optional review, never a recorded decision.

Plan revision stage (`ai-pipeline`, opened by the supervised plan-review loop below). Before
the stage opens, `run-manifest revision-reserve DIGEST LIMIT` reserves the revision for that
plan-review report in `run.json`: a digest already reserved prints the count unchanged (no limit
check, so a resume never trips the limit), a new one is appended while the count is below LIMIT
(`AI_SUPERVISE_PLAN_ROUNDS`), else it fails `plan review: supervision limit reached (N revisions
this run)`. A human (re)start (`run-manifest start`) resets the list; a recovery resume keeps it
(`revision-count` prints it). `run-manifest stage-set plan-revision START` then records
`{name: plan-revision, start_head, report_digest}` (the verified plan report; a triage stage keeps
`review_digest`). `stage-verify` for this stage requires the verified plan review with that
digest and only plan revision records changed since START; a host `plan-revisions` record for
the digest whose commit is in START..HEAD means `committed` (the record holds the outcome), a
dirty tree after it fails `Plan revision stage: uncommitted changes after the counted revision
commit.`, else `pending` (an agent commit with the revision subject never closes it).
`complete_plan_stage` (every start and resume dispatches the open stage by name, before the
clean-tree check): `committed` → `stage-clear` only; `pending` → `revision-reserve` again
(idempotent), `ai-run --revise-plan --since START --base <base sha> --model M` with the run's
`--session-timeout`/`--knowledge-dir` (never its `--model`), `stage-verify` = `committed`,
`stage-clear`. M is `opus`, or `AI_SUPERVISE_ESCALATE_MODEL` from round
`AI_SUPERVISE_ESCALATE_ROUND` on (round from `plan-rounds current`; settings restored from the
manifest on resume). It writes nothing to the checkout. A failed check is a `Plan revision stage
…` stop; a failed reservation is the limit stop; both always need the human.

Supervised plan-review loop (`ai-pipeline`, while no task became DONE since the run's base,
outside an armed resume and without `--skip-plan-review`). The entry check is `tasks newly-done
BASE` (empty output = untouched; DONE tasks of earlier batches already DONE at the base do not
lift the review; a helper error fails closed and skips). A skipped review prints exactly one
line `Plan review skipped: <why>` (`--skip-plan-review`, `resuming preserved work (armed
resume)`, `tasks done since the base: T…` with the first three ids, or `cannot read the task
queue against the base`); a current, unrevised review reused on the loop's first pass prints
`Plan review skipped: the current plan review is reused (BLOCKER b, MAJOR m)`. Each pass: `plan-rounds sync BASE`; the decision check
(`plan-revisions decision`: exit 0 stops with `plan review needs your decision (round n):
<stored questions>`, the bounded text from the host record; exit 2 is a `Plan revision stage`
stop); right after a completed stage, the notification `🔁 Plan revised (round n/N): accepted a,
rejected r` (n = revisions reserved this run, N = `AI_SUPERVISE_PLAN_ROUNDS`, counts from the
record; `(in the previous run)` when a human restart closed a revision recorded before it,
which its fresh allowance does not count; no checkout write, the revision's run-log line is
already in its commit). A review is
due when the plan review is not current or the current report already has a revision record;
it runs `ai-review --plan --base <base sha>`, is host-committed and recorded as the next round.
No BLOCKER/MAJOR → implementation. Otherwise: `AI_SUPERVISE=0` → today's stop (`plan review
found …`); `revision-reserve DIGEST AI_SUPERVISE_PLAN_ROUNDS` fails → `plan review: supervision
limit reached (N revisions this run); BLOCKER b, MAJOR m remain`; else `stage-set plan-revision
HEAD`, `complete_plan_stage`, the gate and clean-checkout checks, and the next pass (which
checks the decision first and then reviews again). The startup dispatch of an open plan
revision stage (after `plan-rounds sync`) also leads into this loop. The plan report header
names HEAD, so the review after a revision commit is always a new report and round. The review
after a revision gets `PLAN REVISION CONTEXT:` (round n, "dispositions of round n−1:
.ai/reviews/plan-dispositions.md" and `plan-history BASE --include-current`, which adds the
just-revised round); never implementation-review rounds. The limit, needs-human and stage
stops are terminal for `ai-recover`.

## Pipeline contract (`ai-pipeline`)

Before the plan review (review on or off) the queue is validated like `ai-task check`; an
invalid queue stops with `Task queue is invalid: …` and recovery always escalates it.
`ai-task reorder` (`workflow.py tasks reorder`) repairs a queue whose tasks depend on later
tasks: stable depth-first order, task text unchanged, nothing written when already ordered;
cycles, unknown IDs and prose in `Dependencies:` are rejected. Everything before the first task
(including ordinary `## ` sections such as `## Context`) is kept as the preamble; only a non-task
`## ` section between two tasks blocks reordering.
`workflow.py tasks fill-sections` (host-only, not an `ai-task` subcommand) gives TODO tasks a missing `### Likely affected modules` (body `(not listed)`) or `### Result / notes` heading at its canonical position; other sections and tasks are untouched, and nothing is written when nothing is missing.
`workflow.py tasks preflight [--dry-run]` (host-only, BR-02) combines both repairs for a queue whose only faults are the order and empty sections: it fails
with the `tasks reorder` errors, or with `T: dependencies must exist earlier in the queue: DEP`
when a DONE, IN_PROGRESS or BLOCKED task would move, and with the `ai-task check` message when the
repaired queue is still invalid; in every failure nothing is written. Otherwise it prints one line per change
(`queue-order TASK placed after DEP, …` for each task whose dependencies were later, `queue-moved TASK`
for every other task whose position changes (claimed like `queue-order`, but no run-log row or notification text), `task-sections
TASK added SECTION, …`), then `overlap A B PATH, …` for each pair of TODO tasks whose `### Likely
affected modules` share a path-like token (contains `/` or `.`; at most 20 lines, then `overlap …
N more`). The real run writes the queue once (mode kept); both the real run and `--dry-run` write the overlap
lines (an empty file when there are none, so no stale report stays) to `.ai/local/preflight.md`
(skipped quietly when `.ai/local` is unsafe). `--dry-run` never changes the queue.
Pre-flight queue scan (host ruling, T103; `ai_queue_ruling` in `lib/common.sh`): right before
the queue check, on a clean checkout and never on an armed resume, `ai-pipeline` dry-runs
`tasks preflight`; when it succeeds with change lines it claims `run-manifest ruling queue-order
T` or `task-sections T` for each changed task, runs it for real, appends one run-log row per
change (task `preflight`, action `ruling-row` cell, e.g. `Ruling (queue-order): T004 placed
after T005, T006. Why: only the order was wrong; dependencies first, no DONE task moved. Cost if
wrong: a task runs later than planned.`), commits `chore(ai): ruling: task queue` (`.ai/tasks.md`
and `.ai/run-log.md`) and sends `🔧 Ruling: task queue reordered (T004 after T005, T006); see the
run log.` The changed queue makes an earlier plan review stale, so the plan is reviewed again. A
failed dry run (a DONE/IN_PROGRESS/BLOCKED task would move, a cycle, prose, another missing
section) or a refused claim (the same task already ruled on in this run; no run manifest)
changes nothing, and the queue check stops as before. A claim is spent once made, so a later
claim of the same scan failing leaves the earlier one used. The overlap lines are printed only.
`ai-run --triage` runs the same scan after `fill-sections` (task `triage`); its queue change, rows
and the notification go into the counted triage commit (no extra commit). `ai-run --plan` and
`--revise-plan` keep their unclaimed `fill-sections` + `reorder` repair and add one Ruling row
per change named by a dry run taken before it (task `planning`, left uncommitted with the plan,
or `plan-revision`, in the revision commit) and print the overlap lines; a dry run that fails
(e.g. a `--revision` plan that moves a DONE task) only means no rows.
Plan revision recovery: the host repairs an interrupted revision's queue first.
`workflow.py revision-queue-repair [--base REV]` (run by `ai-pipeline` with `--base BASE` before
this check when the plan review is on, and by `ai-run --revise-plan` before its own `tasks check`,
with `--base` the merge-base of `--base` (default `main`) and HEAD when it resolves) reorders
`.ai/tasks.md` only when it differs from HEAD's, only plan revision records are dirty
(`plan-revision-scope HEAD`), HEAD's queue is valid with no DONE task (with `--base`: no task
DONE that was not DONE at REV, so an earlier batch's DONE tasks don't count; an unknown REV does
nothing), and the verified current plan review has no revision record yet; otherwise it does
nothing and the checks reject as before (a committed out-of-order queue is the pre-flight
scan's). A repair failure stops with `Plan revision stage: task queue is invalid: …`
(escalated). The repaired queue then passes the revision's `tasks newly-done BASE` check and
`plan-dispositions-check`, so a complete section is recorded without a new session.
Stages, each resumable by rerunning: plan review (only while no task became DONE since the base;
`ai-review --plan` saves `.ai/reviews/plan.md` bound to a digest of the committed tree
minus `.ai/reviews/`, state, run log and handoff, with the report's SHA-256 stored in the
host review store; committed as `chore(ai): record plan review`; reused while that digest is
unchanged and the report matches its stored hash; BLOCKER+MAJOR > 0 gets a supervised plan
revision and a new review (above), or stops with `AI_SUPERVISE=0`; `--skip-plan-review` skips it,
but never the stored needs-human decision check) → implement (`ai-run`) → validate if the stamp is
stale → review (`ai-review`, then the review is committed as
`chore(ai): record independent review`) → if BLOCKER+MAJOR > 0 and fewer than
`--max-fix-rounds` fix rounds are recorded: triage (`ai-run --triage`,
committed as `chore(ai): record review triage`) → implement the new tasks → review
again. A review counts as current when only `.ai/reviews`, state, run log, and handoff
changed since its recorded HEAD. Rounds are counted from host state, never from commit
subjects (agents choose their own): `ai-run --triage` always makes its own counted commit
(empty if needed) and records its hash in the host store (`fix-rounds record`, a file per
branch next to the review bindings); `fix-rounds count BASE` counts recorded commits in
`BASE..HEAD`, so the count survives recovery and human restarts of the same branch and
another branch starts at zero. A branch without a host record (legacy) is initialised once
at pipeline start (`fix-rounds init`, before any session) from commits whose subject is
exactly `chore(ai): record review triage`.

Extra fix round (FL-04 R3): `fix-rounds record` also stores the verified review the round
triaged (`{commit, review_head, review_digest, blockers, majors}`; legacy bare hashes stay
valid, without counts). `fix-rounds trend BASE` prints BLOCKER+MAJOR of the last two
recorded rounds reachable in `BASE..HEAD` and of the current verified review (`x y z`); it
fails with `insufficient history` when either round has no counts (legacy) or the current
review is the one the last round triaged. When the limit is reached exactly, with
`AI_SUPERVISE=1`, no reservation in this run and x > y > z, the pipeline reserves the extra
round for the current review digest in the run manifest (`run-manifest extra-round-reserve`,
once per run: a resume keeps it, a human restart resets it), notifies
`🔁 Extra fix round: findings falling (x → y → z)`, opens the triage stage and appends a
run-log line that the triage commit carries; a resume that finds the reservation for the
current review runs that round. Anything else (`AI_SUPERVISE=0`, flat or rising counts,
fewer than two counted rounds, the reservation used) ends with the draft PR as before.

Triage: the host writes `.ai/reviews/dispositions.md` bound to the reviewed HEAD
(`start-dispositions`), Claude adds one row per finding, and `triage-check` requires a
row for every BLOCKER/MAJOR ID: accepted → existing fix task, rejected → evidence,
deferred → draft PR. In both disposition tables the finding cell starts with the ID and may carry a
severity suffix (`M1 (MAJOR)`) and a title (`M1 (MAJOR) title`, `M1 — title`, `M1: title`; a row counts
for its first ID only); other decorations (`**M1**`, `M1 (CRITICAL)`, `M1,M2`, `M1x`) do not match, and the
failure names the offending row and the row to write. Disposition-cell ruling (host, BR-01, T104;
`ai_disposition_ruling` in `lib/common.sh`): right before `triage-check --fresh` (task `triage`) and
`plan-dispositions-check` (task `plan-revision`, last section only), `workflow.py disposition-ruling
triage|plan [--dry-run]` looks at each BLOCKER/MAJOR finding of the current review that has no
matching row; when exactly one table line (comments excluded) has a first cell that, with `*`,
backticks and brackets removed, names that finding and no other finding of the review, and the line
with ` ID ` as its first cell is a row for it, that cell is rewritten (the rest of the line
byte-identical). It prints `digest <sha256-12 of the review>`, then `ID <old cell>` per rewrite. The
host claims `run-manifest ruling disposition-cell <digest12>.<ID>` for each ID of the dry run, runs it
for real, prints `Disposition cell "**M1**" read as M1.` and appends one row `Ruling
(disposition-cell): finding cell "<old cell>" read as M1. Why: the cell held exactly one finding ID
of this review. Cost if wrong: the row is counted for M1; a wrong reading shows in the PR's
dispositions.`, all inside the counted triage or revision commit. `M1/M2`, an ID the review does not
list, two lines naming M1 or a refused claim (a repeat, no run manifest) change nothing and the
check stops as before. In the Evidence and Task cells (here and in plan dispositions) write a pipe
as `\|` (and a literal backslash before it as `\\`, so `\\|` is a backslash then a separator); it is read back as `|`, while an unescaped `|` still splits the row. Triage sessions may change only `.ai/tasks.md`,
`.ai/reviews/dispositions.md`, `.ai/state.md`, `.ai/handoff.md`, `.ai/run-log.md`, and
`.ai/current-plan.md`. After the session the host runs `tasks fill-sections` (a new task that
lacks `### Likely affected modules` or `### Result / notes` gets it; the line `Task queue: added
missing sections: …` is printed and the repair goes into the triage commit), then `tasks check`
(anything else missing, such as `### Goal`, stops the run). No Claude session may change `.ai/reviews/current.md`: the
runner compares its digest around every session (plus a deny rule). Published
reviews need exactly one counts line that agrees with the listed finding IDs, plus (code
reviews only) a verdict, either an `Overall verdict: <text>` line or an `## Overall verdict`
heading (optional trailing colon) followed by non-empty text; the PR body shows that text.
A `## <LEVEL> findings` section may be left out when its count is 0 (FL-14); a count above
0 with the section missing or only `None.` is still rejected. The other sections the prompt
asks for are optional, so a renamed one doesn't discard the review.
On rerun, complete dispositions for the current review are reused, not re-triaged.

Convergence (FL-03): the triage prompt gets `This review is round <n>.` and, from round 2,
`PREVIOUS ROUNDS:` (`review-history --current`: earlier recorded reviews in
`merge-base..HEAD` of the current review's host header, with finding IDs, titles and
dispositions; context only). When one area has had BLOCKER/MAJOR findings in three
consecutive rounds, triage adds a design task instead of another symptom fix. From round 3
on (reached with `--max-fix-rounds` ≥ 3, or by the supervised extra fix round at the default
limit, see Extra fix round below), `triage-check --fresh` requires a line
`Convergence: <text>` (text on the same line, outside HTML comments) in
`dispositions.md`; without it the triage stops with "Round <n> triage needs a Convergence:
line". It computes the round from the same routine as the prompt (uncapped count + 1), so
every caller agrees; plain `triage-check` and rounds 1–2 are unchanged.

Triage completion (one counted round, even across stops and crashes): before each triage
the pipeline records `stage = {name: triage, start_head, review_digest}` per branch in
the host state directory (`stage-<branch hash>.json` beside `run.json`; `run-manifest
stage-set`, `stage` and `stage-clear` act on the current branch). A run on another branch
neither drops nor inherits it; a restart on the same branch completes it. An unreadable or
foreign stage record stops the pipeline before anything runs; a legacy stage inside
`run.json` still counts for its branch and moves to that branch's file on the next start.
Every pipeline start and resume completes an open stage first (`complete_stage`), before
the clean-tree check, plan review or implementation: `stage-verify` requires the review
binding (verified report whose SHA-256 equals `review_digest`) and that committed,
uncommitted and untracked changes since `start_head` are only triage records
(`triage-scope`). If a host-recorded triage commit already exists after `start_head`
(crash after the commit) the stage is closed without another count;
otherwise `ai-run --triage --since start_head` records it. That is the one owner of the
counted commit: when the dispositions are already complete and fresh it skips the Claude
session and commits the leftover records with the round; it then re-checks the scope (a
commit hook can't add source to the counted commit). `triage-check --fresh` must pass,
then the stage is cleared. Every failed check is a `Triage stage …` stop, which
`ai-recover` always escalates: nothing is implemented and nothing is counted. Incomplete
dispositions with only bookkeeping leftovers rerun the triage session instead.

Review provenance: when `ai-review` publishes a report it records the report's SHA-256
outside the checkout (`${AI_STATE_DIR:-${XDG_STATE_HOME:-~/.local/state}/ai-toolkit}/reviews/`,
keyed by repository path and reviewed HEAD). Every consumer (`review-info`, triage, the
pipeline's freshness check) verifies it, including on resume and after hooks; a report
that doesn't match is invalid until Codex reviews again. Agent sessions get no write
access there (only the project and an explicit `--knowledge-dir`). `ai-run` and
`ai-pipeline` refuse to start, before any agent, when that state directory overlaps the
checkout or the `--knowledge-dir` (equal, inside or containing, also through symlinks) or
when `AI_STATE_DIR`/`XDG_STATE_HOME` is relative; every helper that uses it fails closed the
same way. The state root must be an absolute path outside the checkout and the knowledge
directory; it is checked at every start, by every host-state read, by `ai-recover` before it
reads the run manifest, and by the watchdog against the target project at install and before
recovery. This is a configuration check, not OS isolation. Accepted findings must
reference new TODO fix tasks (`triage-check --fresh`) and always lead to a new review;
`unresolved` is derived from the final review each round. The gate is re-verified after
every host commit and push; draft conversion of an existing PR is verified, not assumed.

Re-check of rejected findings (`ai-review --recheck`): its own preflight needs a clean
tree, a verified review, dispositions bound to it, at least one rejected BLOCKER/MAJOR,
the reviewed commit an ancestor of HEAD and only workflow records changed since it
(triage records plus `.ai/reviews/{current,recheck,disputes,fallback-log}.md`; pending
accepted fix tasks are fine). Codex (read-only, `AI_REVIEW_MODEL` at `AI_RECHECK_EFFORT`, default
medium, prompt `.ai/prompts/recheck.md`) gets the rejected IDs with Claude's evidence and
must answer one JSON object `{"answers": [{"id", "verdict": "withdrawn|upheld", "reason"}]}`.
Parsing is strict: anything missing, duplicated, extra or malformed counts as upheld, and
an answer for an unknown ID (or an entry that is not an object with a string `id`) makes
every requested finding upheld, so no extra entry can ride along with withdrawals.
The host re-runs the preflight, writes `.ai/reviews/recheck.md` with the binding (review
digest, sha256 of the rejected rows' IDs and evidence, reviewed HEAD) and stores the
report's SHA-256 as `recheck-<review digest>.sha256` in the host review store.
`recheck-verify` fails for a missing or edited report, another review, or changed
rejection evidence. Run by hand, the report is committed as `chore(ai): record review re-check`.

Disputed findings (`reconcile_disputes` in `ai-pipeline`): right after every triage, and on
every start/resume before any task runs or the review is replaced, `recheck-status` says
`none` (no verified review, dispositions not bound to it, or no rejected BLOCKER/MAJOR),
`pending` (no verified, current re-check) or `verified`. Pending runs `ai-review --recheck`.
Then `disputes-record` appends a record for every upheld answer that has none yet (key:
review digest + finding id; fields: review digest, finding id and level, the original
finding text from the review, Claude's evidence, Codex's answer, date) to the branch's
host store (`disputes-<branch hash>.json` next to the review bindings) and rewrites
`.ai/reviews/disputes.md` from it. Report and records go into ONE host commit
(`chore(ai): record review re-check`; `chore(ai): record disputed findings` when only a
missing record was added). The file may lag behind the host store (an interrupted write)
but never differ from it; `disputes-verify` (also part of `publish_ready`) requires an
exact match, so an edited or removed file stops publishing. A start may find only an
uncommitted `recheck.md`/`disputes.md` (a stop before the host commit): it is verified and
committed by the reconciliation; anything else must be clean. Lifetime rule: a recorded
dispute is never resolved automatically (not by later fixes, a clean review or a
restart). While any record exists the PR is a draft, its body starts with "Disputed
findings" (id, original finding, Claude's reason, Codex's answer), and the FINISHED todo
list asks the human to resolve them at the PR.

Inherited disputes (T016): merging the PR is the human's resolution, and the tracked file
then reaches later branches whose host store is empty. `ai-pipeline` exports
`AI_DISPUTES_BASE=<base sha>`; the file exactly as it is at `git merge-base <base> HEAD`
is historical. The expected file is that inherited copy (or none) while the branch has no
records, else the inherited copy verbatim, a marker comment, then this branch's records
numbered on (D3, D4, ...). Only this branch's records count: they alone make the PR a
draft, appear in the PR body and the FINISHED todos. Any other content (an edited or
removed inherited part, an edited new record) fails as before. A merged review's upheld
answers that the inherited file already records (review digest + finding id) are not
recorded again on the new branch. Without `AI_DISPUTES_BASE` (a helper run by hand)
nothing is inherited. Limitation: reusing a branch name whose host records were already
merged fails verification (its old records sit both in the inherited copy and the store).

Review base (FL-15): `ai-pipeline --base B` resolves the base once per run, without
fetching. When both the local branch `B` and `origin/B` exist and differ, `origin/B` is
used if the local branch is its ancestor (local is stale); if neither contains the other
the run prints `Local B and origin/B have diverged; reviewing against local B.` and keeps
the local branch. Any other base (an `origin/` ref, a SHA) is used as given. The run
prints `Review base: <ref> at <short sha>` (with ` (local B is behind)` when it switched)
and passes the resolved SHA to `ai-review`, the fix-round counter and the dispute base.
The PR target is still inferred from the name `B`. A rerun resolves again, so the base
can advance between runs after a fetch.

Base moved past the branch (FL-17): when the resolved base is not an ancestor of HEAD,
no review can ever be current, so the run stops at the start with `Review base <ref>
(<sha>) moved past the branch; merge it into <branch> and rerun ai-pipeline`, before the
plan review, implementation and code review. An interrupted review triage and a pending
re-check are completed first (both act only on the already published review, and their
scope checks would reject a merge made while they are open); merge only after this stop.
Without either, no agent runs at all. The base is fixed for a run and HEAD only gains
commits, so one check per start suffices; a rerun re-resolves the base and checks again.
`publish_ready` names the same case (history rewritten by a hook) before its "review
current" check, and `ai-recover` escalates it by hard rule with the full message on stderr.

Publish invariants (`publish_ready`): before the PR stage, before every push attempt
(retries included) and after every push attempt (failed or successful, before the retry
wait), the review base must be an ancestor of HEAD (else "moved past the branch"), the
review must verify and be current for HEAD (only workflow records changed
since the reviewed commit), the validation stamp must be current, the tree clean
(untracked files too), the committed bytes equal to the validated files on disk
(`committed-matches-worktree`) and all tasks DONE; a push hook that commits other bytes
stops as "committed content differs from the validated content", not as a push failure.
Before every Codex review the pipeline also requires a clean tree and committed bytes
equal to the validated files. After a successful push
`git ls-remote origin refs/heads/<branch>` must equal HEAD. Any failure stops (before PR
creation and before any FINISHED notification); a hook can't slip unreviewed or
unpushed content into the PR.

PR stage: clean tree required; `git push -u origin <feature-branch>` (never force,
protected branches are refused earlier); `gh pr view` decides create vs. edit;
`--base` is passed when the base is a local branch; draft when `--draft` or when
significant findings remain after the round limit, or while any dispute is recorded.
Un-draft rule: a policy draft (findings or disputes, not `--draft`) the pipeline created or
converted is recorded in host state (`pr-draft record`, `binding_dir()/pr-draft/`); a conversion
is recorded only when the first `isDraft` lookup returned exactly `false` (an unknown prior
state, e.g. a failed lookup, still converts but never counts as a pipeline draft); a later
run that needs no draft takes (consumes) that record for the PR's URL first, then runs `gh
pr ready` and confirms `isDraft == false` (logged "pull request marked ready"). A failed
ready warns and re-records (best effort); a record that cannot be consumed or no record
leaves the PR draft ("left as draft"); a ready PR clears a stale record. `--draft` clears
the record at the start of the PR step, before any `gh` change; a failed clear stops the
run ("could not revoke the pipeline draft record", a hard rule for recovery). Limitation:
a human re-draft between two runs is not seen. The
PR body (starting with "Disputed findings" when there are any) is generated from the
spec objective, task list, validation stamp, review counts/verdict, and the handoff's
"Manual testing for the human" section (split into subsections `### Needs you` for steps
only a human can perform and `### Covered by automated tests` for deterministic test
scenarios; the PR summary counts only "Needs you" steps). An optional handoff section
`## Flow chart` (one line: "Flow chart updated" or "Flow unchanged") is copied under
Summary. Flow-line ruling (host, BR-01, T105; `ai_flow_line_ruling` in `lib/common.sh`): before
the host gate of each DONE task (key = the task, row under it), before the final gate and before
the PR body is built (key `final`, row under `none`), `workflow.py flow-line-ruling [--dry-run]`
reads the first `## Flow chart` heading outside code fences. HTML comments count as empty. When
the section's first non-empty line starts with one of the two phrases it moves right under the
heading; otherwise `Flow unchanged (host ruling)` (the section says "unchanged" or "no flow
change", any case) or `Flow chart updated (host ruling; see below)` is inserted there; the blank
lines before it go and the text below stays. A correct, empty or missing section is left alone.
The host claims `run-manifest ruling flow-line KEY` first (a refused claim, i.e. a repeat or no
run manifest, leaves the handoff as written and the gate decides as before), prints `Flow chart
line: "…" placed under the heading.` and appends one `Ruling (flow-line)` row; the handoff and
row land in the runner checkpoint, the review handoff commit or the pull request record commit.
State becomes `ready_for_acceptance`.

Notifications (`AI_NOTIFY_CMD`) are best-effort with a 20-second timeout. Child
commands don't notify inside the pipeline (`AI_PIPELINE=1`); the pipeline reports
start, pauses, stops (with `.ai/local/last-error`), and the PR. Usage-limit pauses
are described in the README; they never write tracked files.

## Recovery contract (`ai-recover`)

On a human start `ai-pipeline` writes a **run manifest** to the host state directory
(`run.json` beside the review bindings, outside the checkout, where agent sessions can't
write): approved gate digest, branch, arguments and the attempt counter. Recovery takes
its authority only from there, never from checkout files. `stop()` re-verifies the gate
digest against the pipeline's in-memory approved digest and only then execs
`ai-recover --stage S` (unless `AI_AUTO_RECOVER=0`), keeping the PID, the checkout lock
(fd 9 is handed over across exec) and the liveness marker. `ai-recover`: before reading
the manifest, the host state directory must pass `state-root-check` for the checkout
(absolute, no overlap); otherwise it escalates with the configuration error plus the
original stop reason, without a Claude session, commit or attempt; current gate
digest must equal the manifest's, the branch must be the manifest's, then one attempt is
reserved (validated integer; max `AI_RECOVER_MAX`, default 2; reset by a human start and
on finish) before any fallible work; a recorded needs-human plan revision for the current
plan report (`plan-revisions decision` exit 0) escalates with the stored questions
(`plan review needs your decision: …`), whatever the recorded reason (also a crash with no
last-error) and before the attempt limit and any stage resume; an open plan-revision stage
whose `stage-verify` says `committed` is cleared first, so the run continues once the human's
answer has a new plan review (the stage would be foreign to it); an unreadable revision store
(exit 2) escalates too; hard-rule escalation by reason (gate, permissions,
denied, branch, review integrity, plan review, a usage limit beyond the wait budget (no relaunch covers it), hook-changed checkpoints,
`Triage stage`, `Plan revision stage` (including a queue the host could not reorder after a
revision), `supervision limit reached`, `needs your decision`, and the review base that moved past the branch, whose full recorded reason is printed to
stderr before the escalation summary);
an EXIT trap guarantees one final ⛔ on unexpected exits; with an open triage or plan-revision
stage for the branch (also after a watchdog crash recovery) it never commits anything: changes
since the stage start outside that stage's records (`triage-scope` / `plan-revision-scope`)
escalate, otherwise it resumes without a Claude session and the pipeline completes the stage;
bookkeeping-only leftovers
(state, run log, handoff) are committed as `chore(ai): record stop during S`; one
read-only Claude session returns `{"action", "reason", "human_action"}`;
the decision counts only with a zero exit, a success envelope and exactly one valid
`{"action","reason"}` object; `commit_and_rerun` requires a dirty tree, installs stale
dependencies (as `ai-run` does) and requires a passing `ai-check`, then commits all non-ignored changes, re-verifies the gate and requires the
committed tree to match the validation stamp (a commit hook can't sneak content in); `rerun` requires a clean tree. Resumes run
`ai-pipeline` with the saved arguments and `AI_RECOVERY_ATTEMPT=n`, which refuses to
start if the gate digest differs from the approved one. Escalation sends one
`⛔ STOPPED, needs you` with the reason and next step, records `last-error` and removes
the marker. The manifest also stores the run's effective `AI_*` settings (notify command, models,
budgets, `AI_AUTO_RECOVER`), which `ai-recover` restores; settings the run didn't have are
cleared to their defaults, and the resumed pipeline skips the user config file
(`AI_SETTINGS_FROM_MANIFEST`).

**Session timeout on an IN_PROGRESS task.** After the hard rules, the attempt limit, an open
stage and the bookkeeping-only leftovers commit, and before the Claude decision session,
`ai-recover` handles one case itself when all of these hold: `--stage implementation`; the
reason starts with ai-run's `Claude exited 124 (` or `Claude exited 137 (`; `run-manifest task`
names the session's task; `tasks status` says that task is `IN_PROGRESS`; and the checkout is
still dirty. It first spends the task's one rerun (`run-manifest timeout-rerun TASK`), so a
failing gate uses it too. Once per task per run: `timeout_reruns` survives resumes
(`clear-attempts` keeps it) and only a human start drops it. A refusal escalates `the TASK
session timed out again after one commit-and-rerun in this run.` with `Next: split the task or
raise --session-timeout, then rerun ai-pipeline.`. Otherwise it notifies `🔧 Recovering (n/max):
<branch>: the TASK session timed out; committing its validated partial work once and
rerunning.` and commits exactly as `commit_and_rerun` does (dependencies, a passing `ai-check`,
no secret-looking files, the committed tree matches the validation stamp) as `chore(ai):
recovery checkpoint (validated leftover work)`, then resumes. A failing gate escalates `the TASK
session timed out with uncommitted partial work; but the leftover work fails validation.` with
the work left uncommitted. Every neighbouring case keeps the decision session or its
escalation: a timeout before the task was marked, a non-timeout exit, a tree clean after the
leftovers commit, `AI_AUTO_RECOVER=0` and a spent attempt budget (`test_timeout_rerun_unchanged_*`).

**Usage-limit relaunch.** Right after reserving the attempt and restoring the settings,
before any escalation, `ai-recover` decides on the manifest's relaunch schedule: *pending*
(`limit-hold`: the run is still waiting, e.g. a watchdog crash recovery after a kill between
scheduling and its cleanup) → it gives the attempt back, restores the wait (removes
`last-error`, `limit-stop` and `pipeline.active`, appends the `pauses.log` line, `observe
relaunch`, ⏸ again), prints `Still waiting for the usage-limit relaunch after <time>.` and
exits 75; *due* (`limit-claim`) → the schedule is consumed, so whatever this relaunch hits next
is its one terminal ⛔ and no probe starts it again. A claimed relaunch checks the checkout once,
right after the gate and branch checks and before anything reads it to decide
(`relaunch_verify`: `limit-verify` recomputes HEAD and `workflow.py worktree-digest`, which is
`tree-snapshot`: HEAD, the staged diff, every non-ignored path outside `.ai/local/` with kind,
mode and bytes, tracked bookkeeping and `.ai/reviews/` included, submodules recursively). The
relaunch continues exactly the tree it stopped with: any change during the wait (a human edit,
an added file, a staged change, a commit, a change inside a submodule) escalates `the branch
moved to another commit while the usage-limit relaunch waited; nothing was committed.` (HEAD)
or `the checkout changed while the usage-limit relaunch waited; nothing was committed.` (tree)
and touches nothing. After the plan-revision decision block it then notifies `▶ RESUMED after the
usage limit (relaunch k/cap): <branch>.` and resumes without a Claude session or an attempt: an
open stage resumes as above, bookkeeping-only leftovers are committed (`record stop during usage
limit relaunch`), other uncommitted work is armed (`limit-arm` recomputes both and records
`limit_resume` only on an exact match; `limit-armed` recomputes against it) and kept, a clean
tree resumes. `tasks newly-done REV` prints the tasks DONE in the working queue but not at REV.
A stop whose `last-error` is exactly the limit-beyond-budget message with a matching
`limit-stop` (`workflow.py limit-stop`) is scheduled before the hard rules: with
`AI_LIMIT_RELAUNCH_MAX` (0–9, default 2) at 0 the hard rule escalates it as before; without a
watchdog timer installed with `--recover` (`ai-watchdog --timer-recovers`) it escalates `the
usage limit resets around <time>, but no watchdog timer with --recover is installed …`; past the
cap (`limit-schedule` fails) it escalates `usage limit again after N relaunch(es) in this run.`;
otherwise it records `limit-schedule AT CAP STAGE` (relaunch at reset + 60 s; STAGE is this
ai-recover's `--stage`, kept as `limit_stage`; HEAD and the tree
digest are taken here, after the stop's bookkeeping was written and before any commit, and
after it the host writes only `.ai/local/` and host state), appends `<UTC>
paused <AT-now>s: <Agent> usage limit relaunch (resume ~<time>)` to `pauses.log`, observes
`relaunch AT`, notifies `⏸ PAUSED: <branch> stopped at a <Agent> usage limit during <stage>;
relaunches by itself after <time> (relaunch k/cap).`, removes `last-error`, `limit-stop` and the
marker, and exits 75 with no ⛔.

**What a relaunch accepts.** One verification, one site: `relaunch_verify` is called exactly
once in `ai-recover`, after the gate and branch checks and before anything that commits,
stashes, checks out, writes a tracked file, reads the checkout to decide (the plan-revision
decision, the open-stage scope check, the leftovers and dirty tests) or starts a session. It
compares HEAD and the whole tree (`worktree-digest`) with what `limit-schedule` recorded. A
change anywhere in the checkout during the wait (tracked, untracked, staged, a bookkeeping file
alone, a commit, a file or a commit inside a submodule, an in-scope edit while a triage or
plan-revision stage is open) escalates with `nothing was committed.`, `Next: inspect the
checkout, commit or discard what changed, then rerun ai-pipeline.`, and leaves the checkout
exactly as found. Only a verified tree is then transformed, in exactly four ways (the table
after the `▶ RESUMED` notification in `ai-recover`): (a) an open stage → resume (its scope
check kept); (b) dirty only in `.ai/state.md`, `.ai/run-log.md`, `.ai/handoff.md` → the
leftovers commit → gate check → resume; (c) dirty otherwise, after an `implementation` stop →
`limit-arm` → resume; (d) clean → resume. `limit-arm` refusing in (c) escalates with the verify
wording; no host step between the verification and the arm touches the checkout, and the
checkout lock is held throughout.

**Which stop can leave preserved work.** Only `ai-run --approved` in ai-pipeline's
implementation step (`stop implementation`: first tasks and fix rounds alike) legitimately
leaves uncommitted task work: triage and plan revision run under an open stage (a), and the plan
and implementation reviews start on a clean tree. `limit-arm` therefore first checks that the
`limit_stage` recorded at scheduling is `implementation` (read from the manifest, never from the
relaunch's own `--stage`, which is `usage limit relaunch`); any other stage, or none, exits 1
and (c) escalates `the usage-limit stop left uncommitted changes outside an implementation
session; nothing was committed.` with the same `Next:`, the checkout as found. `limit-verify`,
`limit-armed` and `limit-disarm` do not read the stage.

**Which task the preserved work belongs to.** The relaunch continues the task the limited
session was working on, named in the host manifest, never inferred from the queue. `ai-run`
records it (`run-manifest task-set ID`, best effort: a standalone run without a manifest prints
`Note: could not record the task in the run manifest.`) right before every implementation
session, clears it (`task-clear`) after the iteration's bookkeeping commit and once before its
task loop, and leaves it in place when the session stops at a limit. `limit-schedule` copies it
into `limit_task`; `limit-arm` arms only with a `limit_task` and records it in `limit_resume`
(`limit-task` prints it, read only). Without one, (c) escalates `the usage-limit stop left
uncommitted changes with no task recorded; nothing was committed.` with the same `Next:` and
leaves the checkout as found.

**How the resumed run continues preserved work.** A limit stop keeps the session's uncommitted
work and the relaunch continues it once, in the normal implementation session or the normal
validated checkpoint, never in a recovery decision or a recovery commit; any change during the
wait escalates (above). `ai-pipeline` and `ai-run` admit a dirty tree through one predicate,
`clean_or_armed`: an empty `git status --porcelain --untracked-files=all`, or `armed_resume`
(a resume with `AI_RECOVERY_ATTEMPT` set, no stage open, and `run-manifest limit-armed`
finding HEAD and the tree digest equal to `limit_resume`). It stands at every clean-checkout
check between the resume and ai-run's first act: ai-pipeline's start, both tests of the dispute
reconciliation and ai-run's start. A human `ai-pipeline --approved` is never a resume, so it
refuses a dirty tree with `Start from a clean checkpoint` as before (and its `run-manifest
start` drops the arm). While armed the host writes nothing: a pending re-check, an
uncommitted `.ai/reviews/recheck.md`, `disputes.md` or `fallback-log.md`, or a verified
re-check whose dispute records the host would still have to write (`workflow.py
disputes-record --check`, which writes nothing and fails unless a real call would write nothing
either) stops before the re-check or commit (`Re-check of rejected findings: preserved task work
carries uncommitted review records; inspect them.`), the plan-revision queue repair is skipped,
and ai-run's stop handler appends no run-log line until the disarm. The armed
resume re-enters the run at implementation: the plan review loop is not entered while armed
(the arm exists only after an implementation stop, so this run already passed the plan-approval
boundary; a partial checkpoint the limited session committed makes the saved plan review stale,
and `ai-review --plan` cannot run on the preserved tree; that commit is reviewed by the
implementation review like any task commit). Its path is start checks → dispute reconciliation
→ base check → `plan_decision_check` → queue check → `plan_decision_check` → implementation, so
a recorded needs-human plan decision still stops it (arm kept); a clean resume re-reviews a
stale plan as before. ai-pipeline runs ai-run while armed even when every task is DONE. ai-run then, still armed, reads the bound
task (`limit-task`), checks that `tasks newly-done HEAD` prints nothing or exactly that task
(else `Preserved work marks another task DONE; inspect it before continuing.`), runs the
dependency setup (also when `tasks next` is `none`), and routes by the bound task's status in
the working queue: DONE (in HEAD or only in the tree) → the armed checkpoint; IN_PROGRESS or
TODO → its session, which `tasks next` must name (else `Preserved work belongs to T…, but the
next task is T…; inspect the queue.`); BLOCKED → `Blocked task was not checkpointed`; an ID not
in the queue stops too. It repeats the loop head's checks, then `limit-disarm` (its only call
site), prints `Resuming preserved work of the usage-limit stop (T…).`, clears the task record
and acts: the armed checkpoint is `checkpoint_done`, the same function the loop runs after a
DONE session (full `ai-check`, failure → task back to IN_PROGRESS and stop; the tier-1 commit
`chore(ai): checkpoint T… (validated; the session did not commit)` with `checkpoint-guard`,
stamp and `committed-matches-worktree`; the outcome log's `done` line without an attempt; the
bookkeeping commit; `verify_checkpoint`), then the queue continues. A stop of the resumed run
before the preserved work is continued is final: `ai-recover` checks `limit-task` right after
the relaunch schedule and before every other rule, and while `limit_resume` exists (matching
the checkout or not) it never decides or commits, whatever `AI_AUTO_RECOVER` says; it sends one
⛔ with the stop's reason and `the resumed run stopped on the preserved work of T… before
continuing it; nothing was committed.`, keeping the checkout and the arm. After the disarm the
normal rules apply unchanged, so a later stop gets ordinary recovery, not the exception.
So the resumed run checks the preserved work (another task marked DONE, the next task not the
interrupted one, a blocked or missing task, dependency setup) before it takes the work over,
and each of those stops is final with nothing committed; only the loop head's re-checks, which
repeat what the consumer just verified under the lock, stand between the disarm and the act.

The manifest's own location (`AI_STATE_DIR`/`XDG_STATE_HOME`) can't
live inside it: install the timer with the same state directory the pipeline uses (the
default unless you changed it). `--install-timer` checks this for the TARGET checkout (the
`project` argument, not the caller's directory) before writing anything: it refuses (exit 2)
a relative `XDG_DATA_HOME`, a host copy that overlaps the checkout (equal, inside or
containing, also through symlinks) and a state directory that does. At runtime the host copy
repeats the state-directory check before reading the gate digest or the manifest; on failure
it notifies `auto-recovery refused: Host state directory … overlaps the checkout …` and
never calls `systemd-run`. `--recover` only works from the installed host copy; run
from the checkout it refuses and reports (a human running checkout scripts trusts them,
as with `ai-pipeline`; the protected path is the timer's host copy). Order in
`ai-recover`: take the lock (a rejected second process exits quietly and touches neither
`last-error` nor the marker), check the state directory, reserve the attempt, then publish the marker; TERM/INT/HUP
handlers make kills end in one ⛔. A relaunched `ai-pipeline`, `ai-run` or `ai-review` that
finds the lock held exits 1 and writes nothing (no `last-error`, marker, observation or
notification); its `Another runner/reviewer owns this checkout` message names the owner when
`pipeline.active` (a regular file only) holds the PID of a live `ai-recover` (auto-recovery,
with its PID and `kill` hint) or `ai-pipeline`. Known limit: an `ai-recover` started by
`ai-watchdog --recover` after a crash leaves `pipeline.active` naming the dead pipeline (the
watchdog's `pipeline_died` input), so a relaunch during it gets the plain message. Checkpoints must also satisfy `committed-matches-worktree`
(HEAD blobs and executable modes equal the unfiltered files on disk, defeating clean/smudge
filters and staged mode changes). The recovery decision must be exactly one JSON object:
the whole answer (optionally fenced), or one object that starts a line and ends its last
line inside prose that contains no `{`, `}`, `[` or `]` (so no enclosing container, second
object or inline example can hide it; prose with any bracket escalates, the safe side);
envelope and decision reject duplicate keys. Without a valid decision the escalation reason
is `the recovery session gave no valid decision; it wrote: <excerpt>` (whitespace collapsed,
at most 300 characters) when the answer is non-empty, else without the excerpt. A reason or
human action longer than 300 characters is cut by `shorten` at a sentence end (if that keeps
half the cap), else at a word boundary, and ends with `…`; the full text goes to
`.ai/local/recovery-decision.txt` (removed at the start of every `ai-recover` and
`recover-decision`) and the ⛔ notification ends with `Full text: <that path>`.
`ai-run` commits validated leftovers of a DONE task itself (tier 1), with the same
checks after the commit. Checkpoint scope: `git add --all` (ignored
files stay out), then `checkpoint-guard` inspects every staged addition (renames count as
additions) and unstages everything if a name matches the secret patterns (`.env*`, `*.pem`,
`*.key`, `*.p12`, `*.pfx`, SSH keys, `*credentials*`, `*secret*`, `.npmrc`, `.netrc`, ...):
tier 1 stops, recovery escalates. Rationale: each session starts from a clean tree, so new
files are its own output, the same set Claude's own commit would hold; a module allowlist
parsed from task text proved brittle (spaces, globs, renames) and agent-editable. The timer runs a host copy of `.ai/bin`
(`$XDG_DATA_HOME/ai-toolkit/watchdog/<unit>/bin`, refreshed by `--install-timer`), so the
code that verifies the gate before crash recovery isn't checkout code; it then launches the
checkout's `ai-recover`. `ai-watchdog --recover` launches `ai-recover` via
`systemd-run --service-type=exec` only if the gate digest matches the manifest, forwards
`PATH`, `XDG_*`, `AI_STATE_DIR` and `AI_*` settings, and keeps notification duty until
`ai-recover` takes over the marker (20 s), otherwise it reports ⛔ with the reason. It
re-announces a stop only if the runner didn't (`.ai/local/last-error.notified`), and only
once no runner or recovery is alive.

## Review and fixes

Review begins at a clean committed checkpoint with a complete queue and fresh successful
gate. `ai-review --base REF` pins HEAD and merge-base and checks that the checkout hasn't
changed while Codex runs. The CLI runs with read-only shell sandbox, never approvals,
and no user configuration. Project configuration/skills/integrations should still be
inspected: shell sandbox policy is not a guarantee about every possible external tool.
The host saves only the final review artifact after checking the required sections.
A failed/timed-out/malformed report preserves the previous current review. Raw results
are local; commit current reports/dispositions so Git retains earlier audits.

Format retry (FL-04 R4): `review-format-check plan|code REPORT` runs exactly the content
checks of `publish-plan-review` / `publish-review` (shared `review_format_error`, no writes;
exit 2 with the error on stdout). With `AI_SUPERVISE=1`, `ai-review --plan` and the code
review run it after the reviewer call; on a format error (including empty text from an
otherwise successful Codex or Claude call) they notify `🔁 Review format retry (<mode>):
<error>`, keep the first report in `.ai/local/`, and call the reviewer once more through the
same chain with `FORMAT ERROR: <message>. Return the full report again in the required
structure.` appended. Reviewer metadata (label, model, fallback reason) is reset per call,
so a retry Codex answers after a Claude fallback is saved and logged as a Codex review. The
run-log line (`review format retry (<mode>): published` or `stopped again, prior review
preserved`, with the first report's path) is written only after the second call, so both
calls see a clean checkout; after a publish it is committed with the review record (by
`ai-pipeline`'s `review_record`, or by the hand-run plan path). A second format error stops
as before. The checkout must stay unchanged across both calls: the review pins one HEAD
(the code review's scope HEAD, the plan scope HEAD) for both calls and the publish, and a
HEAD change or a dirty tree after the first call (e.g. from the notification) stops before
the retry (`stopped, checkout changed between the calls, prior review preserved`) and is
checked again before publishing. Never retried: reviewer exit errors, limit handling, a
checkout changed during either call, unreadable reports, binding writes, re-checks (JSON; a
malformed answer stays upheld, an empty one stops) and everything with `AI_SUPERVISE=0`.

Codex tests can be restricted by read-only execution. The report must distinguish
source inspection, validation evidence, tests actually run, and tests not run. Human
can request isolated test execution if needed; do not expand write permissions over
the implementation checkout merely to make review tests convenient.

BLOCKER/MAJOR findings are evaluated by Claude, not blindly followed. Each gets a
disposition with evidence; accepted findings become tasks, fixes get regression tests
and full validation, and important changes may receive a follow-up audit. Deferred
or disputed significant findings need human resolution before acceptance. Codex's
no-findings verdict is not proof, and human acceptance is never automated.

## Future worktrees (optional, no manager required)

Keep the primary working tree on main, implementation on a feature branch worktree,
and review in a detached snapshot of the implemented commit:

```bash
git worktree add ../project-claude -b feature/large-feature main
# Run setup/plan/implementation inside ../project-claude.
# After checkpointing implementation:
git worktree add --detach ../project-codex feature/large-feature
```

Run the gate again in the review worktree (local evidence is ignored and isn't copied).
Review that exact commit with the same base; copy/commit the review artifact back
deliberately. Use project-specific ignored build/cache directories and separate local
services/ports if testing concurrently. Do not let multiple agents edit one checkout,
and don't put the review worktree on the writable implementation branch. Human removes
worktrees when no longer needed. This future isolation doesn't require an orchestrator.

## Checkout health monitoring

The optional `ai-watchdog [PROJECT]` is a deterministic Linux `/proc` probe, not
an agent or recovery runner. It matches `ai-run`/`ai-pipeline` executable/script
arguments and the process's exact checkout working directory.

Incidents:

- **died**: `.ai/local/pipeline.active` exists but the `ai-pipeline` process it
  names is gone (an orphaned `ai-run` child doesn't count; a reused PID that started
  after the marker was written doesn't either). `ai-pipeline` writes this marker at start and removes it on every exit it controls (completion
  and `ai_die`, which also records `last-error`), so a leftover marker means it was
  killed, crashed or the machine restarted, in any phase. A new pipeline run rewrites
  the marker and rearms the incident.
- **stalled**: implementing/fixing_review, no runner, no marker and no `last-error`
  (a killed standalone `ai-run`), confirmed: the first probe that sees it only records
  `stall_seen_ns` in `watchdog.json`; a probe at least 5 minutes later that still sees it
  reports it, and any probe that doesn't drops the record (a probe just before a pipeline
  starts stays silent). A checkout whose `.ai/local/observation.json` is at stage
  `planning` is never stalled (read without following symlinks; unreadable counts as
  absent). A recorded stop is reported as **stop** instead. Nor is a checkout waiting for
  a usage-limit relaunch (below): the rule is skipped while the latest `pauses.log` pause
  runs, while a relaunch is pending, and while a due one is this `--recover` probe's to
  handle. With no schedule, or a due one probed without `--recover`, it applies as before.
- **usage-limit relaunch**: when no runner and no marker exist, the probe asks its own
  copy's `workflow.py run-manifest limit-at` for the approved run's scheduled relaunch
  (exit 1 = none scheduled: no manifest, never scheduled, claimed or finished). Pending
  (`AT > now`): nothing happens and the run counts as waiting, not killed, with or without
  a `pauses.log` line (the host manifest is the authority). Due, with `--recover`: it
  starts `ai-recover --stage 'usage limit relaunch'` through `start_recovery` (same host
  copy, state root and gate checks as crash recovery; no default `last-error` is written).
  If that is refused it sends one `⛔ STOPPED, needs you: the usage-limit relaunch could not
  start: <reason>.` per AT (dedupe key `relaunch:<AT>`).
- **hung**: a live runner whose newest activity is older than `--stale-minutes`
  (default 45). Activity is the newest mtime of `.ai/run-log.md`,
  `.ai/local/pauses.log`, `claude-*.json`, `*events.log` and `check-*.log` in
  `.ai/local/`, or `.ai/`'s mtime, and never earlier than the oldest live runner's
  start (old logs of a resumed run don't count). The latest `pauses.log` entry counts as activity until
  its resume time, so usage-limit pauses don't alarm. Claude sessions are bounded by
  `--session-timeout` (default 30 minutes), which stays below the default; an implementation
  session's gate allowance can lengthen it up to double (see `gate-seconds`).
- **stop**: a `last-error` newer than the watchdog's last notification. The
  acknowledged stop remains an incident until removed or replaced.

A separate `.ai/local/watchdog.lock` serializes probes without blocking the
workflow lock. Atomic `.ai/local/watchdog.json` records active incidents and the
last notification timestamp (and the optional `stall_seen_ns`; records without it stay
valid, and a stall such a record already lists as active stays confirmed, so upgrading
never repeats its notification or diagnosis), written via unpredictable temp files. Files that
runners delete mid-probe count as absent. Persistent incidents notify once; recovery rearms them.
Hung incidents are bound to process start identities and activity timestamps.
Healthy checks are silent. Exit codes: 0 healthy, 1 incident, 2 invalid
arguments/checkout/dedupe record. Notifications use common.sh's best-effort
`ai_notify` and reserve dedupe state before sending, so delivery failures do not
cause repeated alerts.

`--diagnose` reserves one attempt for each new incident batch before starting
`timeout ... codex exec` (read-only sandbox, never-approve, medium effort, answer via an
mkstemp output file) and, when that fails or is empty (`--diagnosis-agent auto`, the
default) or with `--diagnosis-agent claude`, `timeout ... claude -p` with dontAsk,
Read/Glob/Grep only, project setting sources, empty strict MCP configuration and
`--model ${AI_DIAGNOSIS_MODEL:-claude-sonnet-5-5}`. Stdin is `/dev/null`. It asks
for evidence and human recovery advice, never writes or repairs through Claude tools.
The host saves stdout (or failure information) to `.ai/local/diagnosis.md` and adds a
one-line summary to the alert. Existing acknowledged incidents are not diagnosed later
merely because the option is enabled. No diagnosis runs by default.

`--install-timer [--diagnose ...]` generates a per-checkout systemd user service and
10-minute timer with systemd-quoted absolute paths and the current `PATH`, then
enables it; `--uninstall-timer` disables and removes it. The first probe runs 2 minutes
after the timer starts (`OnActiveSec=2min`: after boot, and after `--install-timer`,
never at once); timers installed before this change used `OnBootSec` and need
`--install-timer` again (host copy and unit). `SuccessExitStatus=1` treats
an incident as a successful probe. Nothing is installed by `setup-project`.
`--timer-recovers` exits 0 (`recovers <timer>`) when `--timer-status` would say installed
and the service's `ExecStart=` contains `"--recover"`, else 1 (`no-recover <timer> (<why>)`).
`ai-recover` uses it to decide whether a usage-limit stop can wait for a relaunch.

## Reviewer selection and the Claude fallback

`ai-review` (all three modes) runs `run_review`: with `AI_REVIEWER=auto` (default) or
`codex` it starts Codex. A Codex exit that `limit-check` classifies as a usage limit
pauses and retries under `codex`; under `auto` it switches to `claude_attempt` for this
review (any other Codex failure stops as before; a missing Codex CLI goes straight to
Claude). `claude_attempt`: `claude -p --permission-mode dontAsk --output-format json
--tools Read,Glob,Grep --allowedTools $(workflow.py review-allowlist)
--setting-sources project --strict-mcp-config --model M --effort E`, stdin `/dev/null`,
the mode's Claude prompt plus `.ai/prompts/claude-review.md`. `review-allowlist` prints
just `Read`, `Glob`, `Grep` and does not read `.ai/permissions.allow`.

No shell, by design: plan review rounds 1–4 each found a new command-argument route
through Bash allow/deny lists (runner options, exact entries, git option abbreviations
such as `git grep --open-files=`), so the reviewer gets no Bash, Edit or Write tool. The
host prepares the git context instead: `review_context`, called by `claude_attempt` right
before each session (a retry after a Claude usage-limit pause rebuilds it), recreates the
ignored `.ai/local/review-context/` and writes, with `git … --no-ext-diff --no-textconv`
and no truncation:
- code: `diff.patch` (`git diff MERGE_BASE..HEAD`), `log.txt` (`git log --stat`),
  `files.txt` (`--name-only`), and `since-last-review.patch` when the last reviewed HEAD
  is an ancestor of HEAD;
- recheck: the same three for the current review's range from `workflow.py review-range`
  (`HEAD MERGE_BASE` of the verified review, parsed with the header regex
  `current_review_rounds` uses; it must match `recheck-prepare`'s HEAD), plus
  `findings.txt` (the rejected rows);
- plan: `files.txt` (spec, plan, tasks) and `log.txt` (`git log --stat -n 20`).

`run_review` calls `claude_attempt` in a conditional context, where bash disables
`errexit`, so every context step is checked explicitly; the first failure removes the
directory and dies (`Could not prepare the review context; prior review preserved.`)
before `claude` runs. The directory is removed right after the session, before any
result check. Each mode builds `claude_prompt` next to the Codex prompt: same template,
history and output contract, with scope lines naming the context files instead of git
commands. A Claude usage limit pauses (`ai_limit_pause Claude`) and the loop starts
again with Codex (unless a recorded Codex limit is still active, see below). The final text (`claude-text`) becomes the report (denials go to
`.ai/local/review-denials.log`; the tool list to `.ai/local/review-*.allowlist`); the
usual "checkout unchanged" check and publish helpers follow.

Model (`review-risk`): `high` when a task has `Model: opus*` or a title matching (whole
words) RLS, row-level, auth/authn/authz/authentication/authorization, permission, policy,
lock(s/ing/ed), lock order, concurrency, deadlock, race condition, data race, migration,
delete/deletion, drop, irreversible or payment → `claude-fable-5-1`; else `claude-opus-5-5`;
re-checks `claude-opus-5-5`; effort `high`; `AI_CLAUDE_REVIEW_MODEL`/`_EFFORT` override.

Records: the publish helpers add `> **Reviewer: <AI_REVIEW_LABEL>**` under the host
header (plan/code) or put `AI_REVIEW_BY` in the re-check title; the binding covers the
label. `fallback-record` appends a row to `.ai/reviews/fallback-log.md`, which
`ai-pipeline` commits with the review record (and a hand-run plan review or re-check
commits with its own record). `pr-body` titles the review section "Claude fallback,
<model>" with a catch-up note. `outcome review …` appends to the host outcome log.

"Reviewed by" (BR-14, T110): `ai-review` exports `AI_REVIEW_WHO` (Codex: `Codex (MODEL, effort E)`;
fallback and routed: `Claude … (MODEL, effort E): REASON`) and the publish helpers write
`Reviewed by: WHO` after the host header, before the digest/binding is taken. `outcome review …
--route REASON` (≤ 200 chars; fallback and routed reviews) stores `route`. `pr-body` lists a
`Reviewed by:` bullet per plan/code review row of this project and branch (oldest first, last 10:
`plan: Codex (MODEL)`, `code round K: Claude, routed (MODEL): REASON`), else the report's line.

Codex limit memory (`codex-limit`, BR-14, T109, A11): after a Codex limit with a known reset
(`limit-check` ≠ 0), `ai-review` runs `codex-limit set RESET` (any reviewer; a past or non-numeric
RESET is a usage error), which writes the state root's `codex-limit.json` `{"reset": EPOCH,
"recorded": ISO}` atomically after `check_state_root`. `codex-limit active` prints RESET and
exits 0 while it lies ahead, else exits 1 (missing, symlinked, unreadable or malformed record)
and never writes. Under `AI_REVIEWER=auto` an active record skips the Codex call: the fallback
path as above with the reason `Codex usage limit until DATE TIME (recorded)` (`↪` notification,
`fallback-record`). `AI_REVIEWER=codex` ignores the record and pauses at its limit as before.

Routed reviews (T109, A12): otherwise, under `auto` with Codex installed, `run_review` asks
`review-route MODE BASE HEAD` (BASE: the merge-base for code, the plan base for plan, `-` for
recheck; HEAD: the pinned review HEAD). `claude REASON` runs `claude_attempt` with the usual
model choice and prints `Routed to Claude: REASON` (no `↪`); `review_by=claude-routed`, label
`Claude, routed (MODEL, effort E; REASON). Codex reviewed this branch earlier; no catch-up
needed.`, `AI_REVIEW_BY="Claude (routed), MODEL"`, no `fallback-record` row; the outcome row
names `claude-routed`. `pr-body` titles the section `Claude, routed, MODEL` with a `[!NOTE]`
naming the reason. `ai-review` and `ai-pipeline` validate `AI_REVIEW_ROUTE` (empty, `risk`,
`codex`) and `AI_REVIEW_SMALL_LINES` (1–999999) before any agent runs; the four routing settings
are captured in the run manifest and restored by `ai-recover`.

Routing (`review-route MODE BASE HEAD`, BR-14, T108; called by `ai-review` since T109): prints `codex REASON` or `claude REASON` and exits 0; any error prints `codex
routing unavailable`. It reads host records only (the fix-round store, without writing; a
missing store counts no fix round, so a triage commit subject alone never routes to Claude,
T116; the outcome log's `review` rows), never review commit subjects. The
first rule that applies wins: `AI_REVIEW_ROUTE=codex` → `routing off` (a value other than
empty, `risk` or `codex` → `invalid AI_REVIEW_ROUTE`); mode `plan`/`recheck` → Codex; no
fix round recorded for BASE → `first full code review`; no `codex` code review row of this
project and branch whose head is an ancestor of HEAD → `no Codex review of this branch yet`;
LAST = the newest code review row (any reviewer) whose head is an ancestor of HEAD and not
HEAD itself, none → `no earlier review`; the diff LAST..HEAD outside `.ai/` with more than
`AI_REVIEW_SMALL_LINES` (default 200) added + deleted lines or a binary file → `fix round
diff N lines`; a changed path (renames name both) matching a risk glob (`REVIEW_RISK_PATHS`
plus `AI_REVIEW_RISK_PATHS`; under `.ai/` only globs naming `.ai/`) → `risk path PATH`; a
changed line outside `.ai/` with a risk word at a word start (`REVIEW_RISK_WORDS` plus
`AI_REVIEW_RISK_WORDS`; `_` separates words) → `risk word WORD in PATH`; a task DONE at HEAD
but not at LAST on `opus*`/`claude-opus*` → `T… runs on opus`; else `claude small low-risk
fix round (N lines)`.

## Outcome log

`workflow.py outcome task|review` appends one JSON line to `<state root>/outcomes.jsonl`
(checked with `check_state_root`: never inside the checkout). `ai-run` writes `done`,
`blocked`, `validation_failed`, `no_checkpoint`, `timeout`, `interrupted` or `error` per
task attempt with the session model and the seconds from session start to result; the
attempt number counts earlier lines for the same project (main repository name, shared by
worktrees), branch and task (kept for readers of the log; the report derives its numbers from
`seq`). `seq` orders the attempt among all attempts the host recorded (allocated at the
attempt open, or at the append for an attempt without one, from `attempt-seq` beside the log;
gaps are normal); `started` is the attempt's start (epoch seconds, informational, never an
order key). Failures to write are reported and never stop the run.

A planning session (`ai-run --plan`, so `ai-plan` too) writes one `plan` line: `outcome plan
RESULT MODEL SECONDS [TASKS] [--revision]`, RESULT `done`, `stopped`, `interrupted` or `timeout`
(`stopped`, `interrupted` and `timeout` come from the exit handler while the gate is intact;
SECONDS is 0 when the session never started; TASKS only on `done`). On `done`, `ai-run` also
appends a `plan written: N tasks (MODEL, first plan|revision)` row to `.ai/run-log.md`, left
uncommitted beside the plan (`plan-scope` allows the run log). `outcomes_report` ignores the kind.

Every line goes through `append_outcome`: on a read-write `O_APPEND` descriptor it takes
`flock(LOCK_EX)` (so the tail check and the write are one step for every writer using the
helper, across checkouts), then one `write`, prefixed with a newline when the log does not end
in one (a torn earlier line never swallows the record), then `fsync` of the file, of the log's
directory and of the parent of every directory it created; any sync error propagates, so
success means the line and its directory entries are durable. An older installed copy without
the lock in another checkout can still interleave until upgraded. A short write is a failure (`outcome` exits 1 with "Could not append
the outcome line completely"), never retried: another checkout may have appended in between,
and the next append's newline guard isolates the fragment. `read_outcomes` splits the bytes on
`\n` only and decodes each line on its own, so a torn tail (even one cut inside a multibyte
UTF-8 character) or a U+2028 in a title costs at most that one line. `read_outcomes(...,
strict=True)` treats only a missing log as empty and lets any other read error propagate, so a
transient failure never looks like "no record yet". `confirm_recorded(path, id)` opens an
existing log (never creates it), takes the same lock, reads it to EOF and, when a task record
carries `attempt_id == id`, fsyncs the file and then its directory before returning True.
Removal rule: a marker goes only after `append_outcome` returned True for a record with its id
or `confirm_recorded` returned True, so a line whose earlier sync failed is synced before its
marker is removed (a sync attempt, not recovery of pages the kernel already dropped).

Attempt markers live one file per attempt in `outcome attempt-dir` (`<review binding
dir>/attempts/<id>.json`, id `^[0-9a-f]{16}$`). `write_marker` writes a fsynced `<id>.json.tmp`
and hard-links it to the final name, which fails if the name exists, so a marker is never
overwritten; `list_markers` returns `(path, record, error)` per marker: a valid record (all of
`id`, `task`, `model`, `project`, `branch`, `started`, `pid`, `pid_start`, `id` equal to the file
name), the `OSError` when opening or reading it failed (kept: a transient error never discards
a marker), or both `None` for invalid content (discardable: the writer links only complete
files). Entries without a record sort first by name, then valid ones oldest `started` first; a
failing directory listing raises. `remove_marker` unlinks and syncs the directory.
`open_attempt(task, model, pid)` prints the new id and flushes BEFORE publishing the marker, so
a marker whose id the runner lacks cannot exist; an `OSError` after the print propagates (the
runner keeps any valid printed id whatever the exit status). Residual: a marker whose directory
sync failed may not survive a power loss, losing at most a `crashed` record.

A `review recheck` line records, instead of finding counts, how many rejected BLOCKER and
MAJOR findings Codex upheld and withdrew (`upheld_blocker`, `upheld_major`, `withdrawn_blocker`,
`withdrawn_major`) and the full SHA the re-checked review covered (`reviewed_head`), read from the
verified `recheck.md`. If that cannot be verified the line is still written without these
fields. `ai-status --outcomes` sums them in "Re-checks by reviewer"; re-checks are not listed
under "Reviews by reviewer", but a Claude re-check still appears under "Codex catch-up pending" until covered. A Claude
review (any mode) is covered by a LATER record of the same project and branch that is a Codex
review of the same family (plan covers plan; code covers code and re-check; a Codex re-check covers only a re-check, not a full review) or a `catchup`
record, which `ai-status --catch-up-done BRANCH...` appends. "Later" orders by `time`; equal
times count only within one file, by line order. Covered reviews are summarised as a count.

An attempt opens immediately before the implementation session's `claude` call (after the
dependency step and the remaining-time check; `--triage` never opens one) and closes with
exactly one line: the result above, or, when the runner stops first, from the EXIT handler:
`timeout` (the session exited 124/137), `interrupted` (the runner exited 130/143) or `error`
(anything else: a failed session, a malformed queue, a usage-limit wait beyond
`AI_LIMIT_MAX_WAIT`, ...). A usage-limit pause and retry inside the session belong to the
same attempt and keep its start time. A run with no time left before the session starts logs
nothing, and so does a stop because the approved gate changed (the handler never runs a
project helper after that, nor the plan-revision outcome line). When `.ai/tasks.md` no longer parses, the line still gets written; its title comes
from the task's heading, or is empty.

The runner backs every attempt with a marker (`outcome attempt-open TASK MODEL $$`, before the
session; the line passes `--attempt ID`, which removes the marker once appended). It keeps any
valid printed id whatever the helper's exit status (P13). A gate-change stop logs nothing, so
its EXIT handler removes only this attempt's marker with a plain `rm` (no helper). A runner
killed without its EXIT handler (SIGKILL, OOM) leaves the marker: every non-`--plan` start runs
`outcome attempt-reconcile $$` right after the branch check and before the clean-checkpoint
check, which logs it as `crashed` (attempt counted as usual, `seconds` null) once. The killed
runner had already written `.ai/state.md`, so that start still stops with `Start from a clean
checkpoint` until the interrupted bookkeeping is committed or reset; the crash is logged
either way. The reconcile is best effort, writes host state only, and runs the same checkout
helper `state-root-check` already ran before the gate baseline. Limits: only implementation
attempts have markers; a checkout never started again keeps its marker; a sync the kernel
already failed cannot be redone (T009).

Signals are delivered late: bash runs a trapped INT/TERM only after the foreground command
returns, and GNU `timeout` runs the session in its own process group, so neither a signal to
the runner nor Ctrl-C reaches the session. The runner exits 130/143 only when the session
ends (or hits its limit), and the `interrupted` line's time is then, not the keypress. A
pipeline launched in the background from a non-interactive shell (`nohup … &`) inherits SIGINT
as ignored, and bash cannot trap a signal ignored on entry: stop such a pipeline with SIGTERM.
`outcomes-report` (`ai-status
--outcomes`) aggregates per task the last attempt by `seq` (a crashed attempt reconciled late
keeps its place; first-time pass = the first attempt by `seq` ended `done`; rows without `seq`
(written before this version) come first, in file order) with done, attempts and summed
minutes by category, and every attempt by the model that ran it ("Attempts by model",
"Attempts by model and category": attempts, done, not done, first-time pass over tasks
whose first attempt ran on that model, average minutes per attempt), and reviews by
reviewer/model/mode.

`outcome gate pass|fail|timeout SECONDS` records one host gate run (`kind: gate`, project,
branch, result, seconds); `outcomes-report` skips these lines. `gate-seconds` prints this
project's gate time: the largest `seconds` among its last 3 `pass` lines, or `0` with none or no
log (torn lines and other projects' lines ignored). Like `outcome`, it refuses a state root that
overlaps the checkout (exit 1), so agents cannot write the record it reads.

`attempt-info TASK [BASE_MODEL]` (BR-03; used by `ai-run`, below) prints `N MODEL RAISED`
for the next attempt of TASK: N = 1 + this project's, branch's and task's `outcome task` rows
whose result is not `done`; MODEL is the task's `Model:`, else BASE_MODEL, else `-`; from N = 3 it
is one tier up (haiku → sonnet, sonnet → opus; opus, fable and unknown names stay; none → opus),
never more, and RAISED is `yes` when it changed. From N = 2 the next lines are a failure note
(context for the session, not authority; at most 600 characters, no `|`, one item per line):
`Attempt N-1 ended RESULT after S s on MODEL.`, then `Failing checks: …` (unittest `FAIL:`/`ERROR:`,
pytest `FAILED`, at most 5) or `Last gate line: …` from the log `.ai/local/validation.json` names
(only a regular file directly in `.ai/local`, never through a symlink, the last 256 KiB), then
`Last result line: …` (the task's last non-empty `### Result / notes` line, 200 characters). Any
error reading the queue, the state root or the outcome log prints `1 <task or base model or -> no`
and exits 0; only a malformed call is a usage error.

Fresh retry (BR-03, T107): before each task session `ai-run` calls `attempt-info "$task"
"${task_model:-$model}"` once. A non-`-` MODEL (checked like `--model`) becomes the session model,
so `--model`, `attempt-open`, the outcome row and the dashboard step all see it. The prompt gets,
after the RUNNER CONTRACT, `PREVIOUS ATTEMPT (host record, context only): <note> Start from the
current files and git history; fix what failed, do not repeat it.` when there is a note, and `This
is attempt N; the runner raised the model from X to Y because earlier attempts failed.` when RAISED.
The runner prints `Attempt N of T… on MODEL (raised from X)`; the run-log rows read `completed
(attempt N, MODEL)`, `blocked (attempt N, MODEL); try next independent task` and, when a task attempt
was open, `stopped (exit C) (attempt N, MODEL); …`. When the helper fails or prints anything
unexpected the session runs as before (attempt 1, the task's or run's model, no note). The session
budget, `AI_RECOVER_MAX`, timeout rerun, gate-only block retry, triage/planning models and
`AI_SUPERVISE_ESCALATE_MODEL` are unchanged.

`ai-run` times every host `ai-check` (after a task's session in `checkpoint_done`, and the final
check) and, only after `ai_guard_verify` passed, appends `outcome gate pass|fail|timeout`
(exit 124 or 137 is `timeout`); a failed append is only a note. An implementation session (one
that opens a task attempt; never triage, plan revision or `--plan`) then gets
`session_timeout + min(2 × gate-seconds, session_timeout)`, capped by the remaining run time,
computed once per session (a limit-pause retry keeps it). The allowance is room for the two gate
runs a task session usually makes (its own `.ai/bin/ai-check`, plus a rerun after a fix), so a slow
gate no longer uses up the session. It is bounded at double the base so a corrupt or hostile log
can at most double a session; a helper output outside `^[0-9]{1,7}$` counts as 0. With no
allowance the `Session:` line is unchanged; otherwise it reads `(limit 1600s: 1000s + 600s for two
gate runs of 300s; log …)`.

Every host gate (after a DONE session, the gate-only block retry below, and the final check)
runs with `AI_CHECK_LOCK_WAIT=min(remaining, 900)` (`host_gate`): `ai-check` then
waits up to that many seconds for a session's still-running background gate to release
`.ai/local/validation.lock` (FL-32) instead of failing with `Validation is already running.`;
the wait is part of the timed gate. `ai-check` keeps one deadline: it caps the wait at
`AI_CHECK_TIMEOUT` (validated as decimal digits) and gives `.ai/validate` only the seconds left
(`budget`); with none left it exits 124 with `Validation time limit reached while waiting for the
lock.` without starting the validator (GNU `timeout` would read 0 as no deadline), so a host gate
cannot pass after the run deadline. `.ai/local/validation.json` changes only under the lock: a
waiter whose wait runs out leaves the running gate's record (and its change detection) or a
finished gate's evidence unchanged (review M2). `ai-recover` and `ai-pipeline` keep the immediate refusal.

Session gate rule (FL-32): every implementation session's RUNNER CONTRACT says `A gate run that
outlives a tool call is not a blocker: the full gate the runner runs after the session decides.`

Gate-only block retry (FL-32, `gate_only_retry`): right before each implementation session
`ai-run` keeps the DIGEST of `stamp outcome` (`-` on a helper failure). When the session ends with
its task BLOCKED and a clean tree beyond the records, the runner records the block as before
(`blocked` outcome, run-log line, BLOCKED runner checkpoint), then retries only if all hold: the
outcome's digest is not `-` and differs from the one before the session (the session ran the
gate), its word is `running`, `pass` or `changed` (no failing check: a `fail` record keeps the
block), `run-manifest gate-unblock TASK` succeeds (a run manifest exists and TASK is not yet in its
`gate_unblocks`; the list is kept across `--resume` and recovery relaunches and dropped by a human
`run-manifest start`), and run time remains. The claim is spent before the host gate runs, so it
is once per task per run whatever the gate's result. The host gate is the one above (lock wait,
`ai_guard_verify`, a `gate` outcome line). A failing gate prints `Gate-only block retry of T…: the
full gate failed; it stays BLOCKED.` and the run goes on as for any block (⚠ notification,
independent tasks). A passing gate sets the task to IN_PROGRESS, appends a run-log line, commits
tasks/state/run-log/handoff as `chore(ai): retry T… after a gate-only block`, notifies `🔧 T…:
blocked without a failing check and the full gate passed; running it once more.` (instead of the
⚠ one), and the next session (`tasks next` prefers the IN_PROGRESS task; it counts against the
session budget) gets one extra contract sentence: `The previous session marked T… BLOCKED without
a failing check; the runner's full gate then passed on this tree. If the block was only about the
gate result, verify the acceptance criteria and mark it DONE; otherwise block it again with the
reason.` Only deterministic host evidence decides: a forged stamp buys at most one gate run and
one session, and nothing is accepted without a later DONE checkpoint and its own host gate. A
dirty tree still stops with `Blocked task was not checkpointed` before any of this.

## Observation records and the dashboard

`ai-dashboard --wait [--since CURSOR]` polls the same read-only snapshot and returns the runs
whose fingerprint (status, stage, observation state, a hash of the notification log's inode,
size, mtime and last line) differs from the baseline cursor; it writes nothing.

`ai-dashboard` (`scripts/lib/dashboard.py`) shows each pipeline's current flow stage. The
inputs are advisory records in the checkout's `.ai/local/` (ignored by Git, agent-writable):
`observation.json` holds the stage (`planning`, `plan_review`, `plan_revision`, `setup`,
`build`, `checks`, `review`, `triage`, `recheck`, `pr`; the dashboard draws nine boxes, Plan
first, and a finished `planning` record is shown as status `planned`), state (`active`,
`paused`, `recovering`, `stopped`, `done`), detail, note and `since`/`updated` times, plus `pid` and `branch`
(and `relaunch_at`, set only by `observe relaunch AT NOTE` while a usage-limit relaunch is
scheduled; every other action drops it); written by
`workflow.py observe` from `ai-pipeline`, `ai-run`, `ai-review`, `ai-recover` and the
pause/resume helpers in `common.sh`. `notifications.log` keeps the last 200 notification
lines (`notify-log`, also when no `AI_NOTIFY_CMD` is set). Every notification is mirrored
there, but a stop caused by a changed gate writes no observation and no log line (see the
gate section). The host registry is `<state root>/pipelines/<sha256(checkout)[:16]>.json`,
written by `pipeline-register` on each start and resume; entries whose checkout is gone or
whose JSON is invalid are pruned. All of these writers are best effort: they warn on
failure and never change a run's outcome. Writes go through pinned no-follow directory
descriptors, under a bounded `flock`, via temp file and rename; reads are bounded and never
block on FIFOs or devices.

The dashboard only reads these records, and the process table through `/proc` (`ProcSource`).
It writes no file, takes no lock and changes no run. Liveness follows the watchdog's marker
semantics (`pipeline.active` PID with its start time): `alive`, `crashed` (the marker names a
dead process) or `gone`. Text from the records is sanitised before it reaches the terminal.
For a `gone` run the status is decided in this order: a `stopped` state or a `last-error`
newer than the observation is `needs_you`; a `paused` state with an integer `relaunch_at` is
`paused` (waiting for the scheduled usage-limit relaunch, shown as `⏸ <note>`; a plain
`paused` state is not evidence of a relaunch, since an in-process wait writes it too); a
`planning` stage still `active` or `paused` is `needs_you` with the note `planning session
ended without a plan (killed?)` (the Plan box is drawn stopped); otherwise `planned`,
`finished` or `idle` as before.
Each run also reports `pr` (URL from state.md's `Next action:` line or the last `pull request
ready:` run-log line) and `reviews` (`plan`/`code` finding counts and short reviewed HEAD from
`.ai/reviews/plan.md` and `current.md`, from the `Plan review of plan digest …; HEAD …;` or
`Host evidence: HEAD …;` header; `null` unless exactly one counts line with counts of at most six
digits is found, so a malformed report never stops the dashboard), read
through the same pinned, bounded readers. They are not checked against the host binding: the
pipeline stays authoritative.
Discovery skips a runner process whose environment (`/proc/<pid>/environ`, one bounded
non-blocking read of a regular file, at most 256 KiB) contains exactly `AI_DASHBOARD_IGNORE=1`;
an unreadable environment is not skipped, and a registered checkout is listed regardless. The
toolkit's workflow tests set it on every fixture runner; it reaches resumed pipelines because
`ai-recover` keeps it and the watchdog forwards every `AI_*` variable to the recovery it starts.

`AI_DASHBOARD_PROC` (process-table root) and `AI_DASHBOARD_ROOT` (only checkouts under this
absolute path) are test-only variables that make the dashboard tests deterministic; they are
not user settings. The dashboard must run with the same `AI_STATE_DIR`/`XDG_STATE_HOME` as the
pipelines, because it lists only that state root's registry (`--json` prints `state_root`).

The watchdog needs no gate guard: its timer uses its own installed copy of `common.sh` and
`workflow.py`, and verifies the gate digest of that copy before it launches the checkout's
`ai-recover`.

