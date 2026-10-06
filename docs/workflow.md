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
outside the allowlist become denials. Denials are logged and the run continues
(`.ai/local/denials.log`); a session that cannot work around one ends without a checkpoint
and the run stops there. Inspect the log and adjust permissions yourself.

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
stops and crashes. No infinite loop, boot startup, or monetary spending guarantee is added.
Git hooks remain active and may consume additional time. Monitor your provider usage;
logs may contain sensitive source, so `.ai/local/` stays ignored and should be handled
with the same care as other local transcripts.

## Pipeline contract (`ai-pipeline`)

Stages, each resumable by rerunning: plan review (only while no task is DONE;
`ai-review --plan` saves `.ai/reviews/plan.md` bound to a digest of the committed tree
minus `.ai/reviews/`, state, run log and handoff, with the report's SHA-256 stored in the
host review store; committed as `chore(ai): record plan review`; reused while that digest is
unchanged and the report matches its stored hash; BLOCKER+MAJOR > 0 stops unless `--skip-plan-review`) → implement (`ai-run`) → validate if the stamp is
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

Triage: the host writes `.ai/reviews/dispositions.md` bound to the reviewed HEAD
(`start-dispositions`), Claude adds one row per finding, and `triage-check` requires a
row for every BLOCKER/MAJOR ID: accepted → existing fix task, rejected → evidence,
deferred → draft PR. Triage sessions may change only `.ai/tasks.md`,
`.ai/reviews/dispositions.md`, `.ai/state.md`, `.ai/handoff.md`, `.ai/run-log.md`, and
`.ai/current-plan.md`. No Claude session may change `.ai/reviews/current.md`: the
runner compares its digest around every session (plus a deny rule). Published
reviews need exactly one counts line that agrees with the listed finding IDs, plus the
verdict and the BLOCKER/MAJOR/MINOR sections; the other sections the prompt asks for are
optional, so a renamed one doesn't discard the review.
On rerun, complete dispositions for the current review are reused, not re-triaged.

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
same way. This is a path check, not OS isolation. Accepted findings must
reference new TODO fix tasks (`triage-check --fresh`) and always lead to a new review;
`unresolved` is derived from the final review each round. The gate is re-verified after
every host commit and push; draft conversion of an existing PR is verified, not assumed.

Re-check of rejected findings (`ai-review --recheck`): its own preflight needs a clean
tree, a verified review, dispositions bound to it, at least one rejected BLOCKER/MAJOR,
the reviewed commit an ancestor of HEAD and only workflow records changed since it
(triage records plus `.ai/reviews/{current,recheck,disputes}.md`; pending accepted fix
tasks are fine). Codex (read-only, `AI_REVIEW_MODEL` at `AI_RECHECK_EFFORT`, default
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

Publish invariants (`publish_ready`): before the PR stage, before every push attempt
(retries included) and after every push attempt (failed or successful, before the retry
wait), the review must verify and be current for HEAD (only workflow records changed
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
significant findings remain after the round limit, or while any dispute is recorded. The
PR body (starting with "Disputed findings" when there are any) is generated from the
spec objective, task list, validation stamp, review counts/verdict, and the handoff's
"Manual testing for the human" section. An optional handoff section `## Flow chart` (one
line: "Flow chart updated" or "Flow unchanged") is copied under Summary. State becomes `ready_for_acceptance`.

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
(fd 9 is handed over across exec) and the liveness marker. `ai-recover`: current gate
digest must equal the manifest's, the branch must be the manifest's, then one attempt is
reserved (validated integer; max `AI_RECOVER_MAX`, default 2; reset by a human start and
on finish) before any fallible work; hard-rule escalation by reason (gate, permissions,
denied, branch, review integrity, plan review, weekly limit, hook-changed checkpoints,
`Triage stage`);
an EXIT trap guarantees one final ⛔ on unexpected exits; with an open triage stage for the
branch (also after a watchdog crash recovery) it never commits anything: changes since
the stage start outside triage records escalate, otherwise it resumes without a Claude
session and the pipeline completes the stage; bookkeeping-only leftovers
(state, run log, handoff) are committed as `chore(ai): record stop during S`; one
read-only Claude session returns `{"action", "reason", "human_action"}`;
the decision counts only with a zero exit, a success envelope and exactly one valid
`{"action","reason"}` object; `commit_and_rerun` requires a dirty tree and a passing
`ai-check`, then commits all non-ignored changes, re-verifies the gate and requires the
committed tree to match the validation stamp (a commit hook can't sneak content in); `rerun` requires a clean tree. Resumes run
`ai-pipeline` with the saved arguments and `AI_RECOVERY_ATTEMPT=n`, which refuses to
start if the gate digest differs from the approved one. Escalation sends one
`⛔ STOPPED, needs you` with the reason and next step, records `last-error` and removes
the marker. The manifest also stores the run's effective `AI_*` settings (notify command, models,
budgets, `AI_AUTO_RECOVER`), which `ai-recover` restores; settings the run didn't have are
cleared to their defaults, and the resumed pipeline skips the user config file
(`AI_SETTINGS_FROM_MANIFEST`). The manifest's own location (`AI_STATE_DIR`/`XDG_STATE_HOME`) can't
live inside it: install the timer with the same state directory the pipeline uses (the
default unless you changed it). `--recover` only works from the installed host copy; run
from the checkout it refuses and reports (a human running checkout scripts trusts them,
as with `ai-pipeline`; the protected path is the timer's host copy). Order in
`ai-recover`: take the lock (a rejected second process exits quietly and touches neither
`last-error` nor the marker), reserve the attempt, then publish the marker; TERM/INT/HUP
handlers make kills end in one ⛔. Checkpoints must also satisfy `committed-matches-worktree`
(HEAD blobs and executable modes equal the unfiltered files on disk, defeating clean/smudge
filters and staged mode changes). The recovery decision must be exactly one JSON object
(optionally fenced); envelope and decision reject duplicate keys.
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
