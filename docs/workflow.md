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
for recovery. BLOCKED tasks do not count as complete. Independent work may proceed;
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
`AI_CHECK_TIMEOUT` overrides). Use non-writing format/lint checks and deterministic
non-watch tests. Tests may write ignored build/cache artifacts. Nonignored project
changes during the gate cause a failure, even if the command itself exits zero.

Evidence in ignored `.ai/local/validation.json` includes outcome, timestamp, exit
code, log path, HEAD at check time, and a SHA-256 digest of project file paths,
contents, modes, and symlinks. It includes tracked and nonignored untracked files,
including spec, plan, tasks, and validation tooling. Clean submodules are represented
by their HEAD; dirty submodules are rejected. It omits `.ai/local/`, reviews, compact
state, handoff, and run log so normal bookkeeping does not invalidate source checks.
Ignored source cannot be validated by this digest; keep real source tracked.

A new gate invalidates old success before execution; failures/interruption never
retain a green stamp. Review requires a current successful content digest. Commits
of unchanged content don't invalidate evidence. Environment/dependency/service
changes are not represented by the digest: rerun checks when those change or when
evidence is old. This is a local convenience gate, not tamper-proof attestation or CI.

The runner independently reruns validation after each DONE task and at the end.
If a post-task gate fails, it restores that task to IN_PROGRESS and leaves evidence
for repair. If no progress was checkpointed, it stops rather than spending an
unbounded number of retries. Claude's in-session loop can fix ordinary failures;
three repeated attempts on the same failure should produce a blocker and handoff.

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
Project deny rules prevent Edit/Write on gate tooling, validation, prompts, and
permission/settings files. Existing project settings need those rules merged.

Claude's runner uses `dontAsk` and explicit `.ai/permissions.allow` entries. It loads
project settings and disables MCP integrations for that invocation. Necessary commands
outside the allowlist become denials; inspect the log and adjust permissions yourself.
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

The runner never stages application files itself. Claude commits selected task work;
the runner commits only state/run-log bookkeeping, preserving normal Git hooks. A
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
security to get a pass. The toolkit does not invoke `git push`, `git merge`, or deployment.

## Interruption, limits, and recovery

tmux handles terminal closure. A reboot, timeout, rate limit, network failure, permission
denial, or crash can stop a session. Logs and partial changes remain on disk; completed
commits remain in Git. A fresh resume reads instructions/spec/plan/tasks/state/handoff,
recent logs, history, and diffs. There is no dependency on provider-specific conversation
IDs, so model changes, days-long gaps, or temporary Codex debugging are recoverable.

Clean checkpoints can enter the runner directly. Dirty interrupted trees must first be
reconciled, validated, and committed in a supervised resume session; nothing is reset
automatically. If tools crashed mid-state-write, atomic helper writes reduce corruption,
but agent-written Markdown still needs inspection. Invalid records fail explicitly.

Limits bound new agent invocations and validation execution. GNU timeout terminates a
timed-out command, with a 10-second forced termination grace. No automatic retry of
provider failures, infinite loop, boot startup, or monetary spending guarantee is added.
Git hooks remain active and may consume additional time. Monitor your provider usage;
logs may contain sensitive source, so `.ai/local/` stays ignored and should be handled
with the same care as other local transcripts.

## Pipeline contract (`ai-pipeline`)

Stages, each resumable by rerunning: plan review (only while every task is TODO;
`ai-review --plan` saves `.ai/reviews/plan.md` bound to a digest of the spec, plan and
task files, committed as `chore(ai): record plan review`; reused while that digest is
unchanged; BLOCKER+MAJOR > 0 stops unless `--skip-plan-review`) → implement (`ai-run`) → validate if the stamp is
stale → review (`ai-review`, then the review is committed as
`chore(ai): record independent review`) → if BLOCKER+MAJOR > 0 and fewer than
`--max-fix-rounds` triage commits exist since the base: triage (`ai-run --triage`,
committed as `chore(ai): record review triage`) → implement the new tasks → review
again. A review counts as current when only `.ai/reviews`, state, run log, and handoff
changed since its recorded HEAD. Rounds are counted from those commit messages since
the base, so no hidden state is needed.

Triage: the host writes `.ai/reviews/dispositions.md` bound to the reviewed HEAD
(`start-dispositions`), Claude adds one row per finding, and `triage-check` requires a
row for every BLOCKER/MAJOR ID: accepted → existing fix task, rejected → evidence,
deferred → draft PR. Triage sessions may change only `.ai/tasks.md`,
`.ai/reviews/dispositions.md`, `.ai/state.md`, `.ai/handoff.md`, `.ai/run-log.md`, and
`.ai/current-plan.md`. No Claude session may change `.ai/reviews/current.md`: the
runner compares its digest around every session (plus a deny rule). Published
reviews need exactly one counts line that agrees with the listed finding IDs.
On rerun, complete dispositions for the current review are reused, not re-triaged.

Review provenance: when `ai-review` publishes a report it records the report's SHA-256
outside the checkout (`${AI_STATE_DIR:-${XDG_STATE_HOME:-~/.local/state}/ai-toolkit}/reviews/`,
keyed by repository path and reviewed HEAD). Every consumer (`review-info`, triage, the
pipeline's freshness check) verifies it, including on resume and after hooks; a report
that doesn't match is invalid until Codex reviews again. Agent sessions get no write
access there (only the project and an explicit `--knowledge-dir`). Accepted findings must
reference new TODO fix tasks (`triage-check --fresh`) and always lead to a new review;
`unresolved` is derived from the final review each round. The gate is re-verified after
every host commit and push; draft conversion of an existing PR is verified, not assumed.

PR stage: clean tree required; `git push -u origin <feature-branch>` (never force,
protected branches are refused earlier); `gh pr view` decides create vs. edit;
`--base` is passed when the base is a local branch; draft when `--draft` or when
significant findings remain after the round limit. The PR body is generated from the
spec objective, task list, validation stamp, review counts/verdict, and the handoff's
"Manual testing for the human" section. State becomes `ready_for_acceptance`.

Notifications (`AI_NOTIFY_CMD`) are best-effort with a 20-second timeout. Child
commands don't notify inside the pipeline (`AI_PIPELINE=1`); the pipeline reports
start, pauses, stops (with `.ai/local/last-error`), and the PR. Usage-limit pauses
are described in the README; they never write tracked files.

## Review and fixes

Review begins at a clean committed checkpoint with a complete queue and fresh successful
gate. `ai-review --base REF` pins HEAD and merge-base and checks that the checkout hasn't
changed while Codex runs. The CLI runs with read-only shell sandbox, never approvals,
and no user configuration. Project configuration/skills/integrations should still be
inspected: shell sandbox policy is not a guarantee about every possible external tool.
The host saves only the final review artifact after checking the required sections.
A failed/timed-out/malformed report preserves the previous current review. Raw results
are local; commit current reports/dispositions so Git retains earlier audits.

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
  (a killed standalone `ai-run`). A recorded stop is reported as **stop** instead.
- **hung**: a live runner whose newest activity is older than `--stale-minutes`
  (default 45). Activity is the newest mtime of `.ai/run-log.md`,
  `.ai/local/pauses.log`, `claude-*.json`, `*events.log` and `check-*.log` in
  `.ai/local/`, or `.ai/`'s mtime, and never earlier than the oldest live runner's
  start (old logs of a resumed run don't count). The latest `pauses.log` entry counts as activity until
  its resume time, so usage-limit pauses don't alarm. Claude sessions are bounded by
  `--session-timeout` (default 30 minutes), which stays below the default.
- **stop**: a `last-error` newer than the watchdog's last notification. The
  acknowledged stop remains an incident until removed or replaced.

A separate `.ai/local/watchdog.lock` serializes probes without blocking the
workflow lock. Atomic `.ai/local/watchdog.json` records active incidents and the
last notification timestamp, written via unpredictable temp files. Files that
runners delete mid-probe count as absent. Persistent incidents notify once; recovery rearms them.
Hung incidents are bound to process start identities and activity timestamps.
Healthy checks are silent. Exit codes: 0 healthy, 1 incident, 2 invalid
arguments/checkout/dedupe record. Notifications use common.sh's best-effort
`ai_notify` and reserve dedupe state before sending, so delivery failures do not
cause repeated alerts.

`--diagnose` reserves one attempt for each new incident batch before starting
`timeout ... codex exec` (default; read-only sandbox, never-approve, medium effort,
answer via an mkstemp output file) or, with `--diagnosis-agent claude`,
`timeout ... claude -p` with dontAsk, Read/Glob/Grep only, project setting sources,
empty strict MCP configuration and `AI_MODEL` when set. Stdin is `/dev/null`. It asks
for evidence and human recovery advice, never writes or repairs through Claude tools.
The host saves stdout (or failure information) to `.ai/local/diagnosis.md` and adds a
one-line summary to the alert. Existing acknowledged incidents are not diagnosed later
merely because the option is enabled. No diagnosis runs by default.

`--install-timer [--diagnose ...]` generates a per-checkout systemd user service and
10-minute timer with systemd-quoted absolute paths and the current `PATH`, then
enables it; `--uninstall-timer` disables and removes it. `SuccessExitStatus=1` treats
an incident as a successful probe. Nothing is installed by `setup-project`.
