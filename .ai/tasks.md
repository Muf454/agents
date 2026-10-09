# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files (this repo's `.ai/validate` and `.ai/ci-setup`
included). This run is started with `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"`
(absolute path) so the vault flow chart and hub Log can be updated. Source: Zack's request
of 2026-10-07 (pipeline dashboard, high priority; backlog OR-19 + minimal OR-12). Every task
leaves `.ai/bin/ai-check` passing. Flow-chart rule (AGENTS.md, CLAUDE.md): a task that
changes workflow behaviour updates the vault `agents-flow.md` (and its `updated:` date) in
the SAME task; T009 is only the final docs audit.
Gate note: `.ai/validate` runs the shell syntax checks and then `tests/run_parallel.py`
(parallel shards, about 4 min), inside the 600 s Bash tool limit. Should `.ai/bin/ai-check`
still time out in the session, run the task's targeted tests, record the timeout in the
result, and leave the full gate to the host's post-task `ai-check` (1800 s limit). New tests
with time bounds run inside parallel shards: assert "returns within N s" with the generous
bounds below, never a tight duration.
Read-only rule for this batch: nothing the dashboard does may write a file, take a lock or
change a run. Observation writers are best effort and never change a run's outcome.
Revision 9 (2026-10-09, rebase on master e9354d9 after FL-04 #21, FL-14–17 #22, #23, #24;
see `.ai/current-plan.md`): new Plan revision box and stop labels (`plan revision`, `start`,
`push`), stored needs-human decision, extra fix round and format retry details, `start` and
`detail` observe actions, 8 boxes with the box layout from 120 columns, line references
re-verified; old T004 split into T004 (ai-run, `ai_deps`, ai-review) and T005 (ai-recover);
old T005–T008 are now T006–T009. The review notes below keep the IDs of their time.
Revised after plan review 10 (Claude fallback reviewer, P39–P45, all accepted; revision 11 in
`.ai/current-plan.md`): T005's gate test keeps `workflow.py` intact (ai-recover runs the
checkout helper from `ai_root` on, before it compares the gate) and asserts no stop record and
no log line instead; T010's flag also covers the pipeline's own pre-approval and resume gate
stops, `gate_ok` is computed without a command substitution, and the watchdog note is corrected
(it notifies through its own installed copy); `done` records `stage=pr`; a `needs_you` run whose
record is still active renders the recorded box as stopped with the `last-error` line; task
counts come from a new `tasks counts` helper.
Revised after plan review 9 (Claude fallback reviewer, P32–P38, all accepted; revision 10 in
`.ai/current-plan.md`): new opus task T010 (gate-broken guard: no project helper runs after the
approved gate changed; runs between T001 and T002, so T002 stays sonnet); `/proc` discovery gets
an injectable process source and root filter (`AI_DASHBOARD_PROC`, `AI_DASHBOARD_ROOT`) so the
dashboard tests are deterministic in the parallel gate; ai-run records Build again as soon as
the post-task gate passed (a session-limit stop lands on Build, not Checks); `ai_die` records
a stop only once; `read_record` tail mode; `--json` prints the state root; `observe` fills
`pid`/`branch`.
Revised after plan review 7 (`.ai/reviews/plan.md`, P30–P31, all accepted): the notification
log is always rewritten via temp + rename (hard-link safe); T005 also runs its sanitize tests.
Revised after plan review 6 (P28–P29, all accepted): registration
uses `$AI_START_BRANCH` after the start/resume block; terminal sanitising moved into the opus
task T005.
Revised after plan review 5 (P26–P27, all accepted): recovery
escalation keeps the recorded substage; Setup is recorded inside `ai_deps`, also during
recovery.
Revised after plan review 4 (P23–P25, all accepted): recovery's
unexpected-exit handler records the stop; liveness split into its own opus task (T005);
pty test covers navigation, overflow, resize and an injected exception.
Revised after plan review 3 (P19–P22, all accepted): explicit
recovery stage key; safe traversal for Git metadata and `.ai/tasks.md`; old T002 split into
T002–T004; handoff flow line marked pending until T002.
Revised after plan review 2 (P11–P18, all accepted): substage wins
over an outer stop label; nonblocking opens and bounded locks; directory-descriptor-relative
I/O; one bounded safe reader (T001) used by the dashboard; handoff flow declaration restored
(P15); unknown-stage rendering; Re-check in Codex colour.
Revised after Codex plan review 1 (P1–P10, all accepted): T001 split
into safe writers (opus) and stage hooks (sonnet); overlay schema; checks inside ai-run;
watchdog liveness semantics; locking and no-follow writes; crashed runs never hidden.

## T001 — Safe record I/O: observation, notification log, host registry, bounded readers
Status: DONE
Dependencies: none
Model: opus

### Goal
The three host-written records the dashboard reads, written safely under concurrency and
never through an agent-planted symlink. Helpers only; callers come in T002–T006.

### Implementation notes
scripts/lib/workflow.py (new subcommands; every one exits 0 and prints `Warning: …` to stderr
on any failure or deadline, so callers are never blocked or failed):
- Shared safe I/O (P12–P14), used by every writer here and by the dashboard (T006, T007):
  - `local_dir_fd(root)`: open ROOT, then `.ai`, then `local` each with
    `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` relative to the previous descriptor (`dir_fd=`); a
    symlink or non-directory anywhere → refuse. All later opens, temp creation, `rename`,
    `unlink` and `flock` use that pinned descriptor (`dir_fd=`/`src_dir_fd=`), never a path
    string, so replacing `.ai` or `.ai/local` after the check cannot redirect any I/O.
  - `open_dir(base_fd, relative)`: walk each component with
    `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` relative to the previous descriptor; any symlink or
    non-directory → None. `checkout_fds(root)` returns pinned descriptors for the checkout
    root, `.ai` and `.ai/local` (P20).
  - `git_branch(root_fd)` (P20): read `.git` via `read_record`: a directory → `HEAD` inside
    it; a regular file `gitdir: <abs path>` (worktree) → open that absolute directory with
    `open_dir` from `/` (every component no-follow except that the toolkit accepts it only
    when the path is absolute and has no `..`), then `HEAD`; `ref: refs/heads/<name>` →
    name, a sha → `detached`, anything else → None. No git subprocess.
  - `read_record(dir_fd, name, limit, tail=False)` → `(text, stat)` or None: open with
    `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`, `fstat` must be a regular file, read at most `limit`
    bytes (observation 64 KiB, notifications 256 KiB with `tail=True`, marker/last-error
    4 KiB, tasks 1 MiB, git HEAD/.git 4 KiB) from that descriptor, decode UTF-8 with
    `errors='replace'`, and return the descriptor's `fstat` (mtime, size) with the text so
    callers such as the marker check get content and metadata from the same open file (P20).
    `tail=True` (P36): when `size > limit` (size from that same `fstat`), `lseek` the same
    descriptor to `size - limit`, read `limit` bytes and drop everything up to and including
    the first newline (a cut partial line), so the newest lines come back; `tail=False` reads
    the head as before. Never blocks on a FIFO or device.
  - Writes: open/create with `O_NOFOLLOW|O_NONBLOCK` (+ `O_EXCL` for temp files), `fstat`
    regular before writing; `flock` with `LOCK_EX|LOCK_NB` retried every 50 ms up to a 2 s
    deadline, then warn and skip the write.
- `observe ACTION [ARGS]` on `observation.json` (schema in the spec). The checkout root is
  `AI_ROOT` when set, else the current directory (`ai_helper` runs after `ai_root` changed
  into the checkout); `pid` is `os.getppid()` (the calling script; the helper is its direct
  child, `cmd || true` forks no subshell) and `branch` is `git_branch(root_fd)` (None →
  `null`) (P38); `updated` is the write time. Box keys:
  `plan_review plan_revision setup build checks review triage recheck pr`.
  `start` (stage `none`, state active, detail and note cleared, new `since`; a human
  (re)start), `step STAGE [DETAIL]` (state active, new `since`), `detail STAGE TEXT` (only
  `detail` changes, and only when STAGE is the recorded stage and the state is active or
  paused; otherwise no change, exit 0), `pause NOTE` (keep stage/detail/since, state paused),
  `resume` (state active, note cleared), `stop LABEL REASON`, `recovering NOTE [STAGE]`,
  `done NOTE` (P43: always `stage=pr`, `state=done`, `note=NOTE`, detail cleared, new
  `since`; the pipeline's `--no-pr` and no-origin finishes happen before its `step 'Pull
  request'`, so the record would otherwise stay on `checks`). Unknown stage keys are refused
  (warning).
  Stop precedence (P11; label list verified against ai-pipeline at master e9354d9): each
  outer label has a group of box keys and a target — `start` → {} / `none` (always none: the
  "base moved past the branch" stop happens before the flow); `plan review` →
  {plan_review, plan_revision} / plan_review; `plan revision` → {plan_revision};
  `implementation` → {setup, build, checks} / build; `validation` → {checks}; `review` →
  {review}; `triage` → {triage}; `re-check` → {recheck}; `pull request preparation`, `push`,
  `pull request`, `final push` → {pr}; empty label → any. If the recorded stage is in the
  label's group (or the label is empty/unknown), keep it; otherwise use the label's target.
  ai-recover's `--stage` text (e.g. the watchdog's `crash (pipeline killed or restarted)`) is
  never passed as a label. `recovering NOTE [STAGE]` (P19): STAGE, when given, must be a valid
  box key and is set directly (no label normalisation); without it the current stage is kept.
  Temp file + `os.replace(…, src_dir_fd=fd, dst_dir_fd=fd)` (replaces a symlink at the
  destination instead of following it); the previous record is read with `read_record`.
- `notify-log ROOT MESSAGE`: `flock` on `notifications.lock` (bounded as above; opened
  without truncation, never written to). Never modify the existing log inode (P30: a hard
  link would pass `O_NOFOLLOW` and the regular-file check): read the current log with
  `read_record` (bounded), append the new JSON line `{"ts","message"}` in memory, keep the
  last 200 lines, write them to an exclusively created temp file and `os.replace` it onto
  `notifications.log` (pinned directory descriptor), all under the lock.
- `pipeline-register CHECKOUT BRANCH`: `root = check_state_root(checkout)` (workflow.py
  ~1038); under a bounded `flock` on `root/pipelines/.lock` write
  `<sha256(checkout)[:16]>.json` atomically, then prune: for each other entry, re-read it
  under the lock and delete it only when its JSON is invalid or its `checkout` is not an
  existing directory.
- `tasks counts` (P45; in the existing `tasks` subcommand next to `count` ~480 and `progress`
  ~482, which prints `<id> <title> (<done>/<total> done)` and nothing bare): prints
  `<done> <total>` (DONE blocks over all blocks, the same counting as `progress`), fails like
  `tasks count` on an unparsable queue. T004 reads it for the Build detail; T007's `inspect`
  applies the same rule to `task_blocks` in-process.
No flow-chart change (no behaviour yet).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py (or tests/test_dashboard.py)

### Acceptance criteria
- Tests named `observation_writer_*`:
  - each action produces the schema; a pause keeps stage/detail/since and `resume` restores
    `active`; `start` after a `stopped` or `done` record gives `stage=none, state=active`
    with detail and note cleared; `detail review "format retry"` after `step review` changes
    only the detail (`since` kept), after `step build` changes nothing; `done 'no PR'`
    after `step checks` gives `stage=pr, state=done, note='no PR'` with a new `since`
    (P43); called through
    `bash -c 'python3 … observe step build; echo $$'` the record's `pid` equals that bash's
    `$$` and `branch` the fixture branch (P38);
  - every stop label in ai-pipeline (`start`, `plan review`, `plan revision`,
    `implementation`, `validation`, `review`, `triage`, `re-check`, `pull request
    preparation`, `push`, `pull request`, `final push`) maps to its target when the recorded
    stage is outside its group; `stop start` after `step triage` gives `stage=none`;
    `stop 'plan review'` after `step plan_revision` keeps plan_revision and after
    `step build` gives plan_review; `stop implementation` after `step checks` or
    `step setup` keeps checks/setup (P11); an unknown label keeps the stage;
    `recovering 1/2 checks` after `step build` gives `stage=checks, state=recovering`,
    `recovering 1/2` keeps the stage, an invalid STAGE is refused (P19);
  - `.ai` or `.ai/local` as a symlink, `observation.json` as a symlink to a sentinel, the
    temp name pre-planted as a symlink, and `.ai/local` replaced by a symlink AFTER
    validation (in-process test that swaps the directory between `local_dir_fd` and the
    write): outside sentinels unchanged, exit 0;
  - FIFO `observation.json` / `notifications.log` / `notifications.lock` and a lock held by
    another process: the helper returns within 5 s (test timeout), exit 0, warning;
  - `read_record`: FIFO, symlink to `/dev/zero`, a 10 MiB file and invalid UTF-8 return
    within 5 s with None or a bounded, decoded result; its stat matches the opened file;
    a 10 MiB log of numbered lines read with `limit=256 KiB, tail=True` returns exactly the
    last complete lines (its first line is complete, its last line is the file's last line,
    the head is absent), and with `tail=False` the first lines (P36);
  - `git_branch`: a normal repository and a `git worktree add` checkout give the branch; a
    detached HEAD gives `detached`; `.git` as a FIFO, a symlinked `.git`, a `gitdir:` with
    `..` or a relative path, and a symlink inside the gitdir path give None within 5 s;
  - `checkout_fds`/`open_dir`: `.ai` symlinked → None; `.ai/tasks.md` read through the
    pinned `.ai` descriptor after `.ai` is swapped for a symlink reads the original;
  - `notify-log`: `notifications.log` and `observation.json` hard-linked to a sentinel
    file outside `.ai/local` (P30): after notifications/observations the sentinel's bytes
    are unchanged; through the pipeline fixture the outcome is unchanged too;
  - `notify-log`: a symlinked log and a symlinked lock leave the sentinel unchanged; 250
    messages keep the last 200 in order; with 200 older lines prefilled, two processes
    appending 100 uniquely numbered messages each concurrently (production limit) leave
    exactly those 200 new messages, once each, every line valid JSON (P16);
  - `pipeline-register`: writes the entry; prunes a removed checkout and invalid JSON; a
    registration replaced between the prune's listing and its delete (simulated by a hook
    or by holding the lock in the test and rewriting the entry) is kept; `pipelines` being
    a regular file → warning, exit 0, other state files untouched;
  - `tasks counts` on a queue with 2 DONE of 5 prints `2 5`; on the fixture `task('T001')`
    prints `0 1`; an unparsable queue fails with the same error as `tasks count` (P45).

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_writer` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude opus): done. `scripts/lib/workflow.py` gains the safe record I/O section
(`open_dir`, `checkout_fds`, `local_dir_fd`, `read_record` with `tail`, `lock_record`,
`write_record`, `git_branch`) and the writers `observe`, `notify-log`, `pipeline-register`
(dispatched through `record_command`: always exit 0, `Warning: …` on stderr), plus
`tasks counts`. Tests: `tests/test_observation.py`, 23 `test_observation_writer_*` tests
(`python3 -m unittest discover -s tests -k observation_writer`: Ran 23, OK). Full gate
`.ai/bin/ai-check`: 434 tests OK.
Choices: the checkout root itself is opened following symlinks (it is the human's path; every
component below it is no-follow); `observe` serialises its read-modify-write with
`.ai/local/observation.lock` (same bounded flock); `resume` only lifts a `paused` record (a
stop or recovery recorded meanwhile stays); a symlink/FIFO at `observation.json` or
`notifications.log` is replaced with a warning; `notify-log` drops non-JSON lines on rewrite;
registry entries that cannot be read safely are left alone (only invalid JSON or a missing
checkout is pruned); `PRUNE_HOOK` is a test-only hook.
Limitation: "through the pipeline fixture the outcome is unchanged" for hard-linked records
needs the callers (T002/T003); the helper-level hard-link test passes here.
Also fixed test isolation in `tests/test_workflow.py` setUp: `AI_SUPERVISE_PLAN_ROUNDS`,
`AI_SUPERVISE_ESCALATE_ROUND`, `AI_SUPERVISE_ESCALATE_MODEL` exported by a supervised pipeline
leaked into the fixture and failed two supervisor-settings tests in this run's gate.

## T010 — Gate-broken guard: no project helper runs after the approved gate changed
Status: DONE
Dependencies: T001
Model: opus

### Goal
The observation and notification-log helpers (`.ai/bin/lib/workflow.py`, part of the approved
gate) are never executed on a stop whose cause is a changed or unreadable gate, in ai-run,
ai-pipeline, `ai_deps` and ai-recover (P32, security). The ⛔ notification itself (the user's
`AI_NOTIFY_CMD`, not project code) is still sent. Helpers only; T002–T005 call them.

### Implementation notes
Rule being enforced: `scripts/ai-run` ~109 ("Never run a project helper after the approved gate
changed") and `common.sh` ~114. Today `ai_die` (~11) runs no project code; T002/T003 would
make it run `notify-log` and `observe` after `ai_guard_verify` (~156) found the gate changed.
The existing gate tests `test_runner_detects_even_committed_gate_changes_before_untrusted_helpers`
(tamper target `.ai/bin/lib/workflow.py`, sentinel `UNTRUSTED_HELPER_RAN`),
`test_pipeline_*` with the post-commit hook (~4585) and the pre-push hook (~4933) already
assert the sentinel is never created on that stop, so without this task T002 breaks the gate.
scripts/lib/common.sh:
- `ai_gate_check GATE`: `actual=$(ai_guard_digest 2>/dev/null) && [[ "$actual" == "$GATE" ]]`
  → return 0; otherwise set the shell variable `AI_GATE_BROKEN=1` (never exported; every
  script sources common.sh itself) and return 1. An unreadable digest counts as broken.
- `ai_guard_verify` (~156): set `AI_GATE_BROKEN=1` before each of its two `ai_die` calls
  (digest unreadable; digest differs).
- `ai_deps` (~187): `if ! ai_gate_check "$gate"; then AI_DEPS_ERROR=…` (same message).
- `ai_observe ACTION ARGS…`: `[[ -z "${AI_GATE_BROKEN:-}" ]] || return 0`, then
  `ai_helper observe "$@" || true`. Defined here; T002 adds the first callers.
- `ai_notify_log MESSAGE`: same guard, then `python3 -B "$AI_BIN/lib/workflow.py" notify-log
  "${AI_ROOT:-$PWD}" "$MESSAGE" 2>/dev/null || true`. Defined here; T002 calls it from
  `ai_notify` (which stays byte-identical in what it sends).
`AI_GATE_BROKEN` is a plain shell variable, so it must never be set inside a command
substitution (P42): `gate_ok=$(ai_gate_check …)` would set it in a subshell only. The form,
written out, everywhere `gate_ok` is needed:
`local gate_ok=no; if ai_gate_check "$AI_APPROVED_GATE"; then gate_ok=yes; fi`
(in ai-run's `on_exit` without `local` if it is not a function-local there; `AI_APPROVED_GATE`
is readonly at ai-run ~90 and ai-pipeline ~126 before either trap/function runs, so `set -u`
cannot trip).
scripts/ai-run `on_exit` (~110): compute `gate_ok` once with the form above (sets the flag on
mismatch, so the ⛔ notification of a standalone run skips the log helper) and use
`"$gate_ok" == yes` in the existing `attempt_open` condition; behaviour otherwise unchanged.
scripts/ai-pipeline:
- `stop()` (~148): hoist the digest comparison to the top of the function in the form above;
  the recovery `if` tests `"$gate_ok" == yes` instead of the inline digest. T003 places its
  `ai_observe stop` AFTER that line.
- The two gate stops before the first step, both after the marker is set (~84) and so on
  the pipeline-shell `ai_die` path that T003 makes record a stop (P41): ~125
  `AI_APPROVED_GATE=$(ai_guard_digest) || ai_die …` (digest unreadable) and ~129–130 (resume:
  current digest ≠ manifest gate) become `… || { AI_GATE_BROKEN=1; ai_die '…'; }` with the
  messages unchanged. (The helper already ran before both decisions, ~120 and ~129; the flag
  only prevents one more call after the gate is known bad.)
scripts/ai-recover: the comparisons at ~97–99, ~160, ~187, ~197, ~207 set the flag:
~97 (`current_gate=$(ai_guard_digest) || …`) sets `AI_GATE_BROKEN=1` before its `escalate`,
~98 and the others become `ai_gate_check "$approved_gate" || escalate …` (messages
unchanged). T005's `ai_observe stop` in `escalate` and `on_exit` is then skipped on exactly
those paths. ai-recover and ai-pipeline do run the checkout helper before they compare the
gate with the manifest (`ai_root` ~29 → `workflow.py paths`, then ~58–77; ai-pipeline
~120–129), today and unchanged; the guard covers the stop itself, not that window, which
is why T005's gate test cannot plant a sentinel in `workflow.py` (P39).
Watchdog (P40; record in docs/workflow.md with T009): no guard is needed. The watchdog
notifies through its OWN copy of common.sh, `Path(__file__).resolve().with_name('common.sh')`
(watchdog.py ~478), so `AI_BIN` there is the timer's installed copy and T002's `notify-log`
runs that copy's `workflow.py`, never the checkout's; `start_recovery` (~286–305) refuses to
run from inside a checkout and compares `ai_guard_digest` of its own copy with the manifest
gate before it launches the checkout's `.ai/bin/ai-recover`.
No flow-chart change.

### Likely affected modules
scripts/lib/common.sh, scripts/ai-run, scripts/ai-pipeline, scripts/ai-recover,
tests/test_workflow.py

### Acceptance criteria
- Tests named `observation_gate_*`:
  - sourcing common.sh in a fixture whose `.ai/bin/lib/workflow.py` is replaced by a script
    that creates a sentinel: `AI_GATE_BROKEN=1 ai_observe step build` and `AI_GATE_BROKEN=1
    ai_notify_log m` return 0 and create no sentinel; without the flag both run the helper;
  - `ai_gate_check "$digest"` returns 0 and leaves `AI_GATE_BROKEN` unset on an intact gate;
    after a byte changes under `.ai/bin` it returns 1 and sets the flag; with `.ai/bin`
    replaced by a symlink (digest unreadable) it returns 1 and sets the flag;
  - the written-out `gate_ok` form (P42), run in a function of a script that sources
    common.sh with `AI_APPROVED_GATE` set to a stale digest: afterwards `gate_ok` is `no` AND
    `AI_GATE_BROKEN` is set in the calling shell (printed after the function returns); the
    same with a command substitution is the counter-example and must not be used;
  - the pipeline's resume gate stop (P41): `ai-pipeline --approved` run with
    `AI_RECOVERY_ATTEMPT=1` after the manifest's gate was recorded from a different
    `.ai/validate` exits 1 with `Gate files changed since the run was approved` on stderr and
    one ⛔ notification, exactly as today (the "no stop record" effect of the flag on this
    path is T003's assertion, since T003 adds the record);
  - `ai_deps` whose `.ai/ci-setup` rewrites `.ai/bin/lib/workflow.py` leaves
    `AI_GATE_BROKEN=1` set and its existing error message unchanged;
  - ai-run `on_exit` after a tampering session (fixture as in
    `test_runner_detects_even_committed_gate_changes_before_untrusted_helpers`): exit code
    and stderr unchanged, `UNTRUSTED_HELPER_RAN` absent; the three existing gate tests named
    above pass unchanged (they are the end-to-end check once T002/T003 add the callers).
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_gate` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k gate_changes` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude opus): done. `scripts/lib/common.sh`: `ai_gate_check GATE` (unreadable
digest = broken; sets `AI_GATE_BROKEN=1`, never exported), `ai_guard_verify` sets the flag
before both `ai_die` calls, `ai_deps` uses `ai_gate_check`, new `ai_observe` and
`ai_notify_log` skip themselves when the flag is set. ai-run `on_exit` and ai-pipeline
`stop()` compute `gate_ok` with the written-out form; the pipeline's approval and resume gate
stops set the flag; ai-recover's first check (`ai_guard_digest >/dev/null || { flag; escalate }`)
and its five comparisons use `ai_gate_check` (escalate messages unchanged; the `current_gate`
variable was unused otherwise and is gone). Extra, same rule: ai-run's EXIT handler no
longer runs `ai_helper outcome plan_revision` when the gate changed (it is project code).
Tests: 6 `test_observation_gate_*` in `tests/test_workflow.py` (`-k observation_gate`: Ran 6,
OK; `-k gate_changes`: Ran 2, OK). Full gate `.ai/bin/ai-check`: 440 tests OK.
Docs: `docs/workflow.md` (gate section, outcome-log note). No flow-chart change.
Note: ai-recover's later comparisons now discard the verifier's stderr detail (only the
escalate message prints), as `ai_deps` and the pipeline already did.

## T002 — Notification mirror and pause overlay (common.sh)
Status: DONE
Dependencies: T001, T010
Model: sonnet

### Goal
Every notification is also kept locally, and usage-limit pauses show on the current stage.
No change to what is sent or printed.

### Implementation notes
scripts/lib/common.sh: `ai_observe` and `ai_notify_log` exist since T010 (both skip the
helper when `AI_GATE_BROKEN` is set; never bypass them with a direct `workflow.py` call).
`ai_notify` (~79) currently returns early when `AI_NOTIFY_CMD` is unset: restructure it so
`ai_notify_log "[$project] $*"` runs in both cases (after sending when it is set); what is
sent stays byte-identical. The watchdog's `bash -c 'source common.sh; AI_ROOT=…; ai_notify …'`
path (watchdog.py ~478) then logs too, as do ai-review's ↪ fallback and 🔁 format retry and
ai-pipeline's 🔁 plan revised / extra fix round notifications.
`ai_limit_pause` (~89): `ai_observe pause "<agent> until <time>"` before sleeping, `ai_observe
resume` after.
Vault `agents-flow.md`: a note under "Phone notifications": every notification is also kept
in `.ai/local/notifications.log` (read by `ai-dashboard`; advisory; flow unchanged); update
`updated:`. Then change `.ai/handoff.md` "## Flow chart" from "pending" to the completed
wording (still starting with `Flow chart updated`, test
`test_pr_body_flow_this_repo_declares_the_flow_chart`).

### Likely affected modules
scripts/lib/common.sh, tests/test_workflow.py, vault agents-flow.md, .ai/handoff.md

### Acceptance criteria
- Tests named `observation_notify_*`:
  - `notifications.log` holds the same messages the mock `AI_NOTIFY_CMD` received in an
    existing fixture run, and lines also with `AI_NOTIFY_CMD` unset;
  - the watchdog's notification (existing watchdog fixture) is logged; a symlinked log
    (sentinel) leaves the sentinel and the watchdog outcome unchanged;
  - a FIFO `notifications.log` and a `notifications.lock` held by another process for the
    whole run: the run completes with its normal outcome (P12);
  - a Claude usage-limit pause (existing limit fixture with `AI_SLEEP`) after `observe step
    build …`: `state=paused` with the stage kept during the sleep (captured by the `AI_SLEEP`
    mock), `state=active` afterwards; same for a Codex pause during a review;
  - gate-changed stop (P32; fixture as in
    `test_runner_detects_even_committed_gate_changes_before_untrusted_helpers` with tamper
    target `.ai/bin/lib/workflow.py`): the ⛔ notification reaches the mock `AI_NOTIFY_CMD`,
    `UNTRUSTED_HELPER_RAN` is absent, `notifications.log` gains no line, exit code unchanged.
- All existing tests pass unchanged (the three gate tests named in T010 included).

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_notify` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude sonnet): done. `scripts/lib/common.sh`: `ai_notify` sends exactly as before
(only when `AI_NOTIFY_CMD` is set) and then always calls `ai_notify_log "[$project] $*"`;
`ai_limit_pause` calls `ai_observe pause "<agent> until <time>"` before the sleep and
`ai_observe resume` after. Tests: 6 `test_observation_notify_*` in `tests/test_workflow.py`
(`-k observation_notify`: Ran 6, OK); full gate `.ai/bin/ai-check`: 446 tests OK. Vault
`agents-flow.md` note added, `updated:` 2026-10-09; handoff "Flow chart" wording completed.

## T003 — Pipeline stage records and registration (ai-pipeline)
Status: DONE
Dependencies: T002
Model: sonnet

### Goal
`ai-pipeline` records each flow stage (plan revision included), its stops (stored decision
and the base-moved early stop included), its finish, and registers the checkout.

### Implementation notes
scripts/ai-pipeline (line numbers at master e9354d9):
- `step KEY TITLE [DETAIL]` (~158; prints `== TITLE ==` exactly as today, then
  `ai_observe step KEY [DETAIL]`): "Completing the interrupted plan revision" (~364) →
  `plan_revision` `resumed`; "Completing the interrupted review triage" (~372) → `triage`;
  "Re-check of rejected findings" (~324) → `recheck`; "Plan review" (~436) → `plan_review`;
  "Plan revision r/max, review round n" (~461) → `plan_revision` with detail
  `<reserved>/<AI_SUPERVISE_PLAN_ROUNDS> · round <n>`; "Implementation" (~476) → `build`;
  "Validation" (`ensure_validated` ~231) → `checks`; "Independent review" (~490) → `review`;
  "Review triage, round n" (~533) → `triage` with detail `round <n>`, plus
  ` · extra (<x> → <y> → <z>)` when `$extra` holds the trend and ` · extra` when it is
  `resumed` (the supervised extra fix round); "Pull request" (~563) → `pr`.
- Start: right after the marker is written (~84), `[[ -n "${AI_RECOVERY_ATTEMPT:-}" ]] ||
  ai_observe start` (a recovery resume keeps the recovering record until its first step).
- `stop()` (~143): `ai_observe stop "$stage" "$reason"` after `reason` is computed AND after
  T010's `ai_gate_check` line at the top of the function (so a changed gate skips the helper),
  before both the exec into ai-recover and the notification. `stop start` (base moved, ~382)
  thereby records `stage=none` (T001).
- `plan_decision_check` (~388), case 0: `ai_observe step plan_revision 'needs your decision'`
  before its `stop 'plan review'`, so the stored needs-human decision always shows on the
  Plan revision box with the questions as the stop note (also on a restart and with
  `--skip-plan-review`).
- common.sh `ai_die`, pipeline-shell path (marker set): `[[ -n "${AI_STOP_NOTIFIED:-}" ]] ||
  ai_observe stop '' "$*" 2>/dev/null || true`, gated exactly like its notification (~17), so
  the `stop()` fall-through (`AI_AUTO_RECOVER=0` or a changed gate, ~154–156) does not record
  a second stop with the longer "Pipeline stopped during …" note (P35). Keeps the stage;
  silent so existing stderr assertions hold; T010's flag already skips it on a gate stop.
- `finish()` (~85) takes an optional note: `ai_observe done "${1:-no PR}"` (T001's `done`
  sets `stage=pr` itself, P43: the `--no-pr` finish at ~561 and the no-origin finish at ~567
  happen before `step 'Pull request'` ~563, so the record is still on `checks` from
  `ensure_validated` ~552 at that point); the final call passes `$url`, the `--no-pr` call
  nothing (`no PR`), the no-origin and no-gh calls `no PR (local only)` / `pushed, no PR (gh
  missing)`.
- The two gate stops before the first step (~125, ~129–130) set `AI_GATE_BROKEN` since T010
  (P41), so the `ai_die` record below is skipped there: nothing to add, one assertion below.
- Registration (P28): one call after `branch=$AI_START_BRANCH` (~139; after the manifest
  start/resume block, so initial start and recovery resume both pass it): `ai_helper
  pipeline-register "$AI_ROOT" "$AI_START_BRANCH" || printf 'Warning: …\n' >&2` (no unset
  variable can reach it under `set -u`).
Vault `agents-flow.md`: extend the T002 note: the scripts also record the current stage in
`.ai/local/observation.json` and each pipeline registers its checkout in the host state
directory (`pipelines/`); `updated:`.

### Likely affected modules
scripts/ai-pipeline, scripts/lib/common.sh, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `observation_pipeline_*` (existing fixture pipelines with mock claude/codex/gh,
  like `test_deps_runner_pipeline_end_to_end`, capturing `observation.json` inside the mocks):
  - a normal run records `plan_review`, `build`, `review`, `pr`, then `done` with the PR URL;
    a `--no-pr` run (fixture as the second run of `test_base_moved_stops_before_any_agent`,
    `Pipeline complete (no PR requested)`) ends `stage=pr, state=done, note='no PR'` although
    `step 'Pull request'` never ran (P43);
  - a review failure → `stage=review, state=stopped` with the reason; a plan-review stop →
    `plan_review`;
  - supervised plan revision (fixture as in `test_revise_plan_accept_*`/the supervised plan
    tests): `stage=plan_revision`, detail `1/3 · round 1` during the revision session, then
    `plan_review` again for the re-review;
  - stored needs-human decision (fixture as in
    `test_supervised_plan_needs_human_stops_with_the_bounded_question` and
    `test_needs_human_decision_gate_holds_with_skip_plan_review`): ends
    `stage=plan_revision, state=stopped`, the note contains the question;
  - extra fix round (fixture as in `test_extra_fix_round_falling_counts_get_one_round_then_draft`):
    triage detail `round 3 · extra (…)` during that triage;
  - base moved (fixture as in `test_base_moved_stops_before_any_agent`, with a previous
    run's `done` record planted): ends `stage=none, state=stopped`, note names the base;
  - a human start that dies at the clean-checkpoint check with a planted `stage=pr,
    state=done` record ends `stage=none, state=stopped`; a resume (`AI_RECOVERY_ATTEMPT`
    set) that dies at its gate check (manifest gate recorded from a different
    `.ai/validate`; T010's fixture) leaves the planted record byte-identical (no `stopped`
    record: the flag skips `ai_die`'s record, P41), `notifications.log` gains no line while
    the mock `AI_NOTIFY_CMD` receives the ⛔, exit code and stderr unchanged;
  - a review failure with `AI_AUTO_RECOVER=0` (the `stop()` → `ai_die` fall-through) leaves
    exactly one stop record whose note is the last-error reason, not "Pipeline stopped
    during …" (P35; count the helper's `observe stop` calls through a logging wrapper or
    compare the record before and after `ai_die`);
  - gate changed by a post-commit hook (fixture as the existing pipeline hook test ~4585,
    sentinel in `.ai/bin/lib/workflow.py`): exit and stderr unchanged, `UNTRUSTED_HELPER_RAN`
    absent, `observation.json` unchanged since the last step (P32);
  - the registry entry exists after an initial start and after a recovery resume (P28);
    `pipelines` replaced by a regular file in the state root: warning, run outcome unchanged
    on both start and resume, run manifest still written;
  - terminal output of `step` unchanged (existing tests pass unchanged).

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_pipeline` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
`ai-pipeline`: `step KEY TITLE [DETAIL]` records the box (terminal output unchanged); start record
(skipped on `AI_RECOVERY_ATTEMPT`), `stop()` records after the gate check, `finish [NOTE]` records
`done`, needs-human decision records `plan_revision`, registration after `branch=`. `ai_die` records
`stop ''` only when `stop()` did not already notify. Tests: 14 `observation_pipeline_*` OK; mock
agents now append `observation.json` to `.ai/local/obs-history` per session. Full gate
`.ai/bin/ai-check`: 460 tests OK. Vault `agents-flow.md` note extended.

## T004 — Runner, setup and review records (ai-run, ai_deps, ai-review)
Status: DONE
Dependencies: T003
Model: sonnet

### Goal
Setup, build and checks inside `ai-run`, standalone triage/revision, and the review format
retry show on the right box, including after failures.

### Implementation notes
- scripts/lib/common.sh `ai_deps` (~167, P27): at the real stale-install boundary (after the
  `stale*` check ~173, before running `.ai/ci-setup`) record Setup: when
  `AI_OBSERVE_RECOVERY` is set → `ai_observe recovering "$AI_OBSERVE_RECOVERY" setup`
  (state stays recovering), else `ai_observe step setup`. Nothing is recorded when
  dependencies are current. (T005 sets `AI_OBSERVE_RECOVERY` in ai-recover.)
- scripts/ai-run: `ai_observe step build "<id> · <model or default> · <done+1>/<total>"`
  when a task starts (after `task_model` ~461; counts via `read -r done total < <(ai_helper
  tasks counts)` from T001's `tasks counts` (P45: no existing `tasks` action prints bare
  counts; `progress` prints a sentence), read once per loop iteration, after
  `ai_guard_verify` ~430 like every helper call; on a helper failure skip the record);
  `ai_observe step checks "<id>"` before its post-task `ai-check` (~478) and `ai_observe step
  checks final` before the final one (~441). After a PASSING post-task gate, right after the
  `ai_guard_verify` at ~485 and before the dirty-tree bookkeeping: `ai_observe step build
  "<id> · checkpointed · <done>/<total>"` (P34), so every stop between two tasks lands on
  Build: the loop head of the next iteration (~430–459: `ai_guard_verify`, `ai_branch`,
  `tasks check`, `tasks complete` with no runnable task, and the common `Session limit
  reached` at ~459), the secret-file and commit-hook checkpoint stops (~494, ~501) and
  `verify_checkpoint` (~522). After a passing FINAL gate (after ~446): `ai_observe detail
  checks 'final · passed'`, so the rare handoff-checkpoint stop (~453) reads as a passed
  gate with its note. Stop-site table for the task loop (test the starred ones): run time
  limit before the post-task gate (~477) → build; a failing post-task gate (~483) → checks*;
  session limit (~459) → build* (`note` contains `Session limit reached`); no runnable task
  (~437) → build; failing final gate (~444) → checks*; `No completed/blocked checkpoint`
  (~513) → build. `--triage` (~350) → `step triage` and
  `--revise-plan` (~223) → `step plan_revision "round <n> · <model>"`, both only when
  `AI_PIPELINE` is empty (inside a pipeline the pipeline's own record with its round/extra
  detail stays).
- scripts/ai-review: right after the 🔁 format retry notification (~235) → `ai_observe
  detail <plan_review|review> 'format retry'` (plan mode → plan_review, code mode → review;
  re-checks never retry).
No new flow-chart change (T003's note covers stage records).

### Likely affected modules
scripts/lib/common.sh, scripts/ai-run, scripts/ai-review, tests/test_workflow.py

### Acceptance criteria
- Tests named `observation_runner_*` (fixture pipeline, observations captured inside the mock
  agent and the mock validator):
  - a normal run shows `build` (detail `T001 · …`) during the session and `checks` during
    ai-run's own post-task and final validation;
  - substage precedence end to end (P11): a failing post-task validation and a failing final
    validation end with `stage=checks, state=stopped`; a failing dependency install ends
    with `stage=setup, state=stopped`; a run with current dependencies records no Setup;
  - between tasks (P34): `ai-run --approved --sessions 1` with two TODO tasks, run inside
    the fixture pipeline, ends `stage=build, state=stopped`, detail `T001 · checkpointed ·
    1/2`, note contains `Session limit reached`; a failing post-task gate still ends on
    `checks`; after the final gate passes the record reads `stage=checks`, detail `final ·
    passed` until the pipeline's next step;
  - `ai_deps` with `AI_OBSERVE_RECOVERY=1/2` set records `stage=setup, state=recovering`;
  - inside a pipeline the triage session sees the pipeline's `triage` record with detail
    `round 1` unchanged; standalone `ai-run --approved --triage` records `triage`, standalone
    `--revise-plan` records `plan_revision` with detail `round 1 · opus`;
  - format retry in a pipeline (fixture as in
    `test_format_retry_pipeline_commits_the_run_log_line_with_each_review`): the second
    reviewer call sees `stage=review`, detail `format retry`; a plan review retry inside the
    pipeline shows `stage=plan_review`, detail `format retry`; a by-hand plan review retry
    with a recorded `build` stage leaves the record unchanged.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_runner` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude sonnet): `ai_deps` records Setup (`recovering … setup` when `AI_OBSERVE_RECOVERY`
is set, else `step setup`) once the install is known stale. `ai-run` records `build` (id · model or
`default` · done+1/total, from `tasks counts`), `checks` before the post-task and final gates,
`build … checkpointed` after a passing post-task gate, `detail checks 'final · passed'` after the
final gate; standalone `--triage` / `--revise-plan` record `triage` / `plan_revision` (skipped when
`AI_PIPELINE` is set). `ai-review` sets the `format retry` detail on `plan_review`/`review`. 12
`observation_runner_*` tests OK; the T002 usage-limit pause test now expects the resumed run to end
on `checks`. Full gate `.ai/bin/ai-check`: 472 tests OK.

## T005 — Recovery records (ai-recover)
Status: DONE
Dependencies: T004
Model: sonnet

### Goal
Recovery, its validation and install, the stored decision, escalation and unexpected exits
show on the right box with the right state.

### Implementation notes
scripts/ai-recover (line numbers at master e9354d9):
- After `max` is set (~95), before the first rule that can escalate on it: set the shell
  variable `AI_OBSERVE_RECOVERY="$attempt/$max"` (never exported; `resume` (~49) execs
  ai-pipeline through `env` with explicit variables, so it does not reach the resumed
  pipeline) and `ai_observe recovering "$AI_OBSERVE_RECOVERY"` (keeps the stage the pipeline
  stop recorded).
- Decision branch (~105–116, a stored needs-human plan decision, also after a crash):
  `ai_observe recovering "$AI_OBSERVE_RECOVERY" plan_revision` before its `escalate`, so the
  stop shows on the Plan revision box with the questions in the note.
- `commit_and_rerun`: `ai_observe recovering "$AI_OBSERVE_RECOVERY" checks` before its
  leftover validation `ai-check` (~196) (explicit stage key, P19); its `ai_deps` (~193)
  records Setup through T004.
- `escalate` (~37) → `ai_observe stop '' "<reason> (stopped during $stage)"` (P26): the empty
  label keeps the substage recovery last recorded (the original stop stage, plan_revision,
  setup or checks; `none` after the base-moved stop); the original label is only text.
  Escalations before the recovering record (state root, manifest, attempt) keep the
  pipeline's stopped stage. The gate escalations (~97–99, ~160, ~187, ~197, ~207) run with
  `AI_GATE_BROKEN` set by T010, so `ai_observe` skips the helper there (P32): the record
  stays at `recovering` and the dashboard shows `needs_you` from the newer `last-error`.
- `on_exit` (~79), existing failure branch (P23) → `ai_observe stop '' "auto-recovery failed
  unexpectedly (exit $code)"` before the notification (keeps the substage; best effort).
- The stage-resume path (~139–153) records nothing more: the resumed pipeline's first step
  replaces the recovering record.
No new flow-chart change.

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py

### Acceptance criteria
- Tests named `observation_recovery_*` (existing recovery fixtures, observations captured
  inside the mock agent and the mock validator):
  - recovery: `state=recovering` with the stopped stage kept; recovery validation of a
    stopped build shows `stage=checks, state=recovering`; its failure and escalation end
    with `state=stopped` (P19); after a `rerun` decision the resumed pipeline's first step
    shows `state=active`;
  - unexpected recovery exits (P23): TERM and an injected failing command during recovery
    end with `state=stopped`, the substage kept, the same exit code as today and exactly one
    STOPPED notification;
  - recovery validation failing after original stops `review`, `re-check` and `pull
    request` (P26) ends with `stage=checks, state=stopped` (dashboard input for
    `needs_you`), the original label in the note;
  - the existing recovery-install fixtures (`fail-later`, `change-later`, see
    `test_deps_recovery_*`) additionally assert `stage=setup, state=recovering` during the
    install and `stage=setup, state=stopped` after the failure (P27); their existing exit,
    notification and checkpoint assertions are unchanged;
  - a stored needs-human decision found by ai-recover (`--stage 'crash (pipeline killed or
    restarted)'`, planted `stage=plan_review, state=active`) ends `stage=plan_revision,
    state=stopped` with the questions in the note and exactly one ⛔ notification;
  - base moved (fixture as in `test_base_moved_recovery_escalates_without_claude`) ends
    `stage=none, state=stopped`;
  - gate changed before recovery (P32, P39; fixture exactly as
    `test_recovery_never_passes_a_changed_gate_or_hard_stop`, i.e. `.ai/validate` changed
    and committed, `workflow.py` intact: ai-recover runs the checkout helper from `ai_root`
    (~29) through ~77 before it compares the gate at ~97–99, so a sentinel in `workflow.py`
    would fire at line 29 and `reserve-attempt` would escalate with another message; that
    assertion is impossible and the flag's mechanics are T010's unit tests): the ⛔ with
    `gate files changed since you approved the run` reaches the mock `AI_NOTIFY_CMD` (existing
    assertion), the record read afterwards is the `recovering` one written at ~95
    (`state=recovering`, stage of the original stop, no `stopped` record: `escalate`'s
    `ai_observe` was skipped), and `notifications.log` has no line for that ⛔ (the flag
    skips `ai_notify_log`); exit code and `recovery_calls()` unchanged.
- All existing tests pass unchanged.

### Validation
Targeted: `python3 -m unittest discover -s tests -k observation_recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE 2026-10-09. `scripts/ai-recover`: `AI_OBSERVE_RECOVERY="$attempt/$max"` plus `ai_observe recovering` after `max`
is set; `plan_revision` before the stored-decision escalate; `checks` before the leftover `ai-check`; `escalate` and
`on_exit` record `ai_observe stop ''` (substage kept; note `<reason> (stopped during $stage)` /
`auto-recovery failed unexpectedly (exit N)`). Gate escalations are skipped by `AI_GATE_BROKEN` (T010).
Tests: 10 `test_observation_recovery_*` (kept stage + resumed pipeline replaces it, validation on checks and its
failure, later-stop labels review/re-check/pull request, TERM exit 143, failing `git add` exit 128, failed and
changing recovery install on setup, stored decision, base moved, changed gate). Mocks now snapshot the record
(`obs-recover`, `deps-obs`; `MOCK_RECOVER_KILL`). Targeted: Ran 10 tests OK; `.ai/bin/ai-check`: 482 tests OK.

## T006 — Discovery and liveness (marker + process identity)
Status: DONE
Dependencies: T005
Model: opus

### Goal
Decide, read-only and race-safely, which checkouts have pipelines and whether each pipeline
is alive, crashed or gone, with the watchdog's semantics on bounded descriptor reads (P3, P24).

### Implementation notes
New `scripts/lib/dashboard.py` (stdlib only; `sys.dont_write_bytecode = True` BEFORE the
`sys.path` insert of its own directory, then import `state_root` and T001's
`checkout_fds`/`read_record` from workflow.py and `is_runner` (~85) from watchdog.py). Do
not call watchdog.py's `marker_snapshot` (~90) / `pipeline_died` (~99) (they open by path
and read unbounded) nor its `process` (~74) / `start_ns` (~65) (they hard-code `/proc`);
reimplement their semantics on an injectable process source (P33):
- `ProcSource(root)`: `root` defaults to `Path(os.environ.get('AI_DASHBOARD_PROC', '/proc'))`.
  `process(pid)` reads `<root>/<pid>/stat` and `cmdline` exactly like watchdog.py ~74–82
  (None for absent or zombie); `cwd(pid)` is `os.readlink(<root>/<pid>/cwd)` (a fixture tree
  uses a plain symlink); `start_ns(ticks)` takes `btime` from `<root>/stat` (cached per
  source); `pids()` lists the numeric entries of `root`. Only `/proc` and the fixture tree
  are ever read; nothing is written.
- `discover(source=ProcSource(), only_under=os.environ.get('AI_DASHBOARD_ROOT'))` → list of
  `(checkout, runners)`: checkouts from `<state root>/pipelines/*.json` (read with
  `read_record` on a no-follow descriptor of that directory; `checkout` must be an absolute
  existing directory with a real `.ai/`), plus the cwd of every live runner process
  (`source.cwd(pid)` for every pid whose `process()` passes `is_runner`) whose cwd has a
  real `.ai/`; when `only_under` is set (absolute path), a checkout from either source whose
  realpath is not inside it is ignored; dedupe by realpath; keep the runner processes found
  per checkout as `(pid, start ticks)`. Both variables exist for the tests (the parallel
  gate runs real fixture pipelines in other temp checkouts, and Zack's machine runs real
  ones); T009 documents them as test-only.
- `liveness(local_fd, runners, source)` → `alive` / `crashed` / `gone`: marker read with
  `read_record(local_fd, 'pipeline.active', 4096)` (PID and mtime from the same open).
  Marker present: alive iff `source.process(pid)` is a live `ai-pipeline`/`ai-recover` whose
  `source.start_ns` is not after the marker mtime + 1 s; otherwise crashed iff a second
  `read_record` returns the same (pid, mtime) (a run finishing during the snapshot is not a
  crash; an orphaned child runner does not make a dead pipeline alive). No marker: alive iff
  `runners` is not empty (legacy versions without `pipeline.active`), else gone.
- `sanitize(text, limit=200)` (P29, security: agent-writable text reaches the terminal):
  remove ESC-introduced sequences (CSI, OSC, DCS, APC/PM/SOS, single-char escapes) including
  their parameters, every remaining C0/C1 control and DEL, bidi override/isolate characters
  (U+202A–U+202E, U+2066–U+2069); collapse whitespace; cap by length with `…`. Applied to
  every checkout-derived string before it leaves the snapshot layer (T007 must call it for
  project, branch, observation detail/note, checkout path, notifications, last error, task
  titles).

### Likely affected modules
scripts/lib/dashboard.py (new), tests/test_dashboard.py (new) or tests/test_workflow.py

### Acceptance criteria
- Tests named `dashboard_liveness_*` (fixture checkouts in a temp dir, `AI_STATE_DIR` temp;
  every test sets `AI_DASHBOARD_ROOT` to its temp base and, unless it needs a real process,
  `AI_DASHBOARD_PROC` to a fixture tree of fake `<pid>/{stat,cmdline,cwd}` entries plus a
  `stat` with `btime`, built by a shared helper; P33):
  - a live process named `ai-pipeline` (symlinked script) holding the marker → alive;
    `ai-recover` likewise (real `/proc`, filtered by `AI_DASHBOARD_ROOT`);
  - a marker whose PID is reused by a newer process (fake entry with start ticks after the
    marker mtime) → crashed, not alive;
  - a marker removed between the two reads (hook/monkeypatch) → gone, not crashed;
  - a dead pipeline with an orphaned live `ai-run` child in the checkout → crashed;
  - a legacy checkout with no marker found only via the process source → alive; no marker
    and no runner (empty fixture tree) → gone;
  - a live runner whose cwd is outside `AI_DASHBOARD_ROOT` is not discovered; a registry
    entry outside it is not listed; without the variable both are;
  - a FIFO marker and a symlinked `.ai/local` → returns within 5 s, treated as unreadable
    (not alive, not crashed), no exception;
  - discovery: registry entries with a relative path, a missing directory, a symlinked `.ai`
    or invalid JSON are skipped; duplicates from the registry and the process source merge
    into one; a fixture `<pid>` entry with a missing `stat`, a zombie state or a non-numeric
    name is skipped.
- Tests named `dashboard_sanitize_*`: CSI colour/cursor moves, OSC 8 hyperlinks and OSC 52
  clipboard writes (BEL- and ST-terminated), DCS, 8-bit C1 CSI (U+009B), a bare ESC at the
  end, CR/backspace overwrite tricks, DEL and bidi overrides are all removed; plain UTF-8
  (emoji, accents) is kept; the length cap holds.
- No file is written (directory listing with mtimes unchanged; no `__pycache__`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_liveness` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k dashboard_sanitize` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude opus): `scripts/lib/dashboard.py` with `ProcSource`, `discover`, `marker`,
`liveness`, `sanitize` as specified; imports `checkout_fds`/`read_record`/`state_root` from
workflow.py and `is_runner` from watchdog.py only. `discover`'s `only_under` defaults to
`AI_DASHBOARD_ROOT` at call time (sentinel; `None` disables the filter). A marker that changes
(not vanishes) between the reads is re-evaluated, at most three times, then the no-marker rule
applies. An unreadable marker (FIFO, symlink, garbage, symlinked `.ai/local`) counts as no
marker. Evidence: `-k dashboard_liveness` Ran 10 tests OK; `-k dashboard_sanitize` Ran 3
tests OK; `.ai/bin/ai-check` OK (495 tests, 8 shards). Mutation checks: skipping the second
marker read fails `..._marker_removed_between_reads_is_gone`; dropping the start-time check
fails `..._reused_pid_is_crashed`. No-write test runs the module from a copied lib via
`runpy.run_path` and compares the temp tree's mtimes and checks for `__pycache__`.

## T007 — Snapshot model, `--once`/`--json`, `ai-dashboard` wrapper
Status: DONE
Dependencies: T006
Model: sonnet

### Goal
A pure, read-only snapshot of all pipelines on this machine, printable as text or JSON.

### Implementation notes
Extend `scripts/lib/dashboard.py` (T006). Every checkout file is read only through T001's
`checkout_fds`/`read_record`/`git_branch` (bounded, nonblocking, regular files only, pinned
descriptors; P14, P20), including `.ai/tasks.md` and Git metadata; a checkout whose records
cannot be read safely shows as `unknown` while the others render:
- `inspect(checkout, runners, now)` → dict: `project`, `branch` (`git_branch`; fall back to
  `unknown`), `liveness` (T006), `observation` (validated fields: known stage keys incl.
  `plan_revision` and `none`, known states; else none), `events` (last 20 parsed
  notification lines from `read_record(local_fd, 'notifications.log', 256 KiB, tail=True)`,
  P36; malformed lines skipped), `last_error`, `tasks` (done/total via
  workflow `task_blocks` (~388) on `.ai/tasks.md` text, counted exactly as T001's `tasks
  counts` (DONE over all blocks, P45); on error none), `status`, `stage`,
  `since`, `updated` (newest mtime of the files read).
- `snapshot()` also returns `state_root` (the `state_root()` path as a string); `--json`
  prints it as a top-level field next to `runs`, and the empty-state text names it (P37:
  the dashboard only sees pipelines registered under the same `AI_STATE_DIR`/XDG root).
- Status rules (first match): liveness crashed → `crashed`; alive and state `paused`/`recovering` →
  that; alive → `running`; state `stopped` (any stage, including `none` after a stop at
  start), or a `last-error` newer than the observation, with nothing alive → `needs_you`;
  state `done` → `finished`; else `idle`. Legacy (no observation): stage `unknown`; alive →
  `running`. The `last-error` case (P44) is what a gate-broken stop leaves behind (T010: no
  record written, state still `active` or `recovering`): the snapshot then carries
  `last_error` (first line, sanitised) and T008 draws it as a stop.
- Pass every checkout-derived string (project, branch, observation detail/note, checkout
  path, notifications, last error, task titles) through T006's `sanitize()` before it enters
  the snapshot (P29).
- `snapshot(all_runs=False)`: list sorted needs_you → crashed → running/paused/recovering →
  finished → idle, then by `updated`; hides only `finished` and `idle` entries whose `updated`
  is older than 24 h unless `all_runs` (needs_you, crashed and live runs always show; Zack
  2026-10-09).
- CLI: `--once` (plain text: per run one title line, one compact stage line, last event;
  T008 replaces this with the shared renderer), `--json`, `--all`. Without `--once`/`--json`
  this task prints the text once too (T008 adds the TUI).
New `scripts/ai-dashboard` (bash; must work outside a checkout and through a symlink): resolve
its real location with `readlink -f -- "${BASH_SOURCE[0]}"`, then
`exec python3 -B "$dir/lib/dashboard.py" "$@"`. Do not source common.sh (it reads user
config and needs nothing here).
setup: add `ai-dashboard` and `lib/dashboard.py` to the installed list in workflow.py `setup`
(~303; the same `copies` drive `--upgrade`, ~306), with tests that a fresh setup and an
upgrade of an older install both install them.

### Likely affected modules
scripts/lib/dashboard.py, scripts/ai-dashboard (new), scripts/lib/workflow.py,
tests/test_dashboard.py or tests/test_workflow.py

### Acceptance criteria
- Tests named `dashboard_snapshot_*` with fixture checkouts in a temp dir and
  `AI_STATE_DIR` pointing to a temp state root, `AI_DASHBOARD_ROOT` set to the temp base
  and `AI_DASHBOARD_PROC` to a fixture tree except where a real process is needed (P33; the
  read-only tree comparison and the wrapper/symlink runs use the same variables):
  - `--json` has `state_root` equal to the temp state root; the empty state (no registry
    entry, empty fixture process tree) prints the text with that path (P37);
  - one fixture per status (running via a live process named `ai-pipeline` through a
    symlinked script, paused, recovering, needs_you, crashed, finished, idle) gives the
    expected status and stage; a stopped `plan_revision` record whose note holds a decision
    question → `needs_you`, stage `plan_revision`, the question in the snapshot; a stop at
    start (`stage=none, state=stopped`) → `needs_you`, stage `none`; a planted `build`
    record with `state=active` older than a planted `last-error` and no process →
    `needs_you`, stage `build`, `last_error` = that file's first line (P44);
  - a legacy checkout with no marker and no observation, found only via `/proc` → running,
    stage unknown (process identity cases are T006's tests);
  - malformed `observation.json` (incl. an unknown stage key), malformed log lines and an
    unreadable tasks file → no exception, fields unknown;
  - an ESC/OSC sequence planted in each checkout-derived field (branch name via a crafted
    HEAD ref, observation detail and note, a notification, `last-error`, a task title,
    checkout path via a registry entry) is absent from `--once` and `--json` output (P29);
  - a checkout with a FIFO marker, a FIFO observation and a 10 MiB notification log, next to
    a healthy checkout: `--once` returns within 5 s and shows the healthy run correctly;
  - old (> 24 h) finished and idle runs are hidden without `--all` and shown with it; an old
    needs_you run and an old crashed run are shown in both;
  - read-only: a recursive listing with mtimes of the fixture checkouts, the state root, the
    toolkit `scripts/` directory and a freshly installed `.ai/bin` is identical before and
    after `--once` and `--json` run from both the toolkit and the installed copy (no
    `__pycache__` appears);
  - `ai-dashboard --once` through a symlink in a temp `bin/` directory outside any checkout
    works;
  - `setup-project` installs `.ai/bin/ai-dashboard` and `.ai/bin/lib/dashboard.py`, and
    `setup-project --upgrade --apply` adds them to an install that lacks them;
    `ai-dashboard --once` works from a directory that is not a Git checkout.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_snapshot` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude sonnet): BLOCKED on one permission, implementation otherwise complete.
`dashboard.py` gained `inspect`, `snapshot`, `render_text`, `main` (`--once/--json/--all`);
`scripts/ai-dashboard` wrapper added; `setup` installs `ai-dashboard` and `lib/dashboard.py`;
11 `dashboard_snapshot_*` tests in tests/test_dashboard.py pass. Full gate: 515 of 516 pass; the
one failure is `test_script_modes_all_shebang_scripts_are_executable` (script='ai-dashboard'):
the working-tree file is mode 644 because `chmod +x scripts/ai-dashboard` was denied by the
session's permissions ("don't ask mode"). The git index already has mode 100755
(`git add --chmod=+x`), so a human or a session allowed to chmod only needs to run
`chmod +x scripts/ai-dashboard` (or `git checkout -- scripts/ai-dashboard`), rerun
`.ai/bin/ai-check`, and set T007 DONE.
2026-10-09 (mission control): the committed mode was 100644 (not 100755 as noted above); ran
`chmod +x scripts/ai-dashboard`, full gate PASS (516 tests OK), T007 set DONE.

## T008 — Curses TUI with the flow as boxes
Status: DONE
Dependencies: T007
Model: sonnet

### Goal
The live view Zack asked for: every pipeline as a row of flow boxes, the active one
highlighted, one status line each; little text.

### Implementation notes
scripts/lib/dashboard.py:
- Pure `render(runs, width, selected=None, expanded=frozenset(), now)` → list of lines, each a
  list of `(text, style)` segments; styles are names (`title`, `active_claude`,
  `active_codex`, `active_script`, `done`, `pending`, `stopped`, `dim`, `event`). Used by
  `--once` (styles dropped) and by curses (styles → colour pairs / attributes).
- Stages and roles, eight boxes in flow order: Plan check (codex), Plan revision (claude;
  Zack 2026-10-09: its own box), Setup (script), Build n/N (claude), Checks (script), Review
  (codex), Triage (claude; `recheck` shows in this box as "Re-check" with style
  `active_codex`, P18), PR (script).
  The box is always the observation's `stage`; `state` only decorates it: `stopped` → that box
  in style `stopped` and the note (stop reason, e.g. a decision's questions) on the marker
  line, `paused` ⏸ / `recovering` 🔧 inside it, `done` → all passed. Status `needs_you`
  with a state other than `stopped` (P44: a `last-error` newer than the record, the
  gate-broken stop of T010) → the recorded stage's box in style `stopped` too, with the
  snapshot's `last_error` (already sanitised, first line) as the marker-line note; stage
  `none` there reads like the stop at start. No parsing of free text.
  Stage `none` with state `stopped` (stop at start, e.g. base moved): no box highlighted, the
  marker line says `⛔ stopped before Plan check` and the note follows. Stage `none` otherwise,
  `unknown`, or no/malformed observation (P17): no box is highlighted or ticked, the marker
  line says `stage unknown` (legacy runs: `stage unknown (older toolkit)`), and the
  title/status and last event still render.
- Width ≥ 120: three box lines (`┌─┐ │ │ └─┘`; active `╔═╗ ║ ║ ╚═╝`) joined by `──`, a
  marker line (✓ under passed boxes, the detail under the active box: `T003 · sonnet · 12m`,
  `1/3 · round 2`, `round 3 · extra (5 → 3 → 1)`, `format retry`), then the latest event
  (`✅ Done …`, `🔁 …` with `HH:MM`). Overlays inside the active box: ⏸ paused, 🔧 recovering,
  ⚠ crashed. A Build label longer than 11 columns (e.g. `Build 100/120`) is truncated with
  `…`. Worst case at the threshold: labels 10 + 13 + 5 + 11
  + 6 + 6 + 8 + 2 = 61, plus 4 per box (`│ ` … ` │`) = 93, an overlay in the active box (+3)
  = 96, seven `──` joiners = 110, card indent 2 = 112 ≤ 120 (100 no longer fits eight boxes).
  Width < 120: title line, one compact line
  `✓Plan ✓Revise ✓Setup ▶Build 3/7 ·Checks ·Review ·Triage ·PR`, latest event; a stopped stage
  renders `✗<label>` in style `stopped`, a paused/recovering/crashed stage `▶<label>` followed by
  ⏸ / 🔧 / ⚠ (Zack 2026-10-09; golden test at width 60/119 includes one stopped and one paused
  run). Lines never
  exceed `width` (truncate with `…`; account for wide emoji via
  `unicodedata.east_asian_width`).
- Header: `AI pipelines  <n> running · <n> needs you · <n> finished  HH:MM  ↑↓ ⏎ a r q`.
  Empty state: "No pipelines found (state root <path>). Start one with .ai/bin/ai-pipeline
  --approved (in tmux)." (P37: a dashboard started without the pipelines' `AI_STATE_DIR`
  shows why runs are missing).
- Expanded run (Enter): checkout path, last error, last 8 events with times.
- Curses loop (`curses.wrapper`): `halfdelay`/`timeout(2000)` refresh, `KEY_RESIZE`
  handling, keys q/↑/↓/Enter/a/r, `curses.use_default_colors()`; colour pairs matching the
  flow chart (Claude orange ≈ 208, Codex blue ≈ 33, scripts grey ≈ 245, stopped red, done
  green/dim) when `curses.COLORS >= 256`, basic colours otherwise, bold/reverse only without
  colour. Scroll when cards exceed the height (keep the selected card visible).
- Default `ai-dashboard` (no flags) on a TTY opens the TUI; not a TTY → behaves like `--once`.

### Likely affected modules
scripts/lib/dashboard.py, tests/test_dashboard.py

### Acceptance criteria
- Tests named `dashboard_render_*`:
  - golden text (styles dropped) for a running build at width 140 and 120 (double border
    around Build 3/7, ✓ under Plan check, Plan revision and Setup), and at widths 119 and 60
    (compact line, truncated with `…` at 60);
  - the worst case (Plan revision active and paused, `Build 99/99`, Re-check label) at width
    120 renders the box row without truncation;
  - a stopped review: the Review box carries style `stopped`; finished: all ✓ and the 🏁 line;
  - a running plan revision: the Plan revision box active in `active_claude` with detail
    `1/3 · round 2`; a stored decision: Plan revision box `stopped`, the question on the
    marker line; an extra fix round: detail `round 3 · extra (…)` under Triage; a format
    retry: `format retry` under Review;
  - a stop at start: no box highlighted, `⛔ stopped before Plan check`;
  - `needs_you` with an `active` `build` record and a `last_error` (P44, golden): the Build
    box in style `stopped`, the `last_error` line on the marker line, no active-style box;
    the same through `ai-dashboard --once` on T007's planted fixture;
  - writer-to-renderer: observations produced by the T001 `observe` helper (not hand-written
    fixtures) for a paused build, a paused review, a paused plan revision, a recovery and a
    stop from each real stop label (the twelve labels of T001) render the overlay in the
    right box (`start` in none);
  - `recheck` renders the Triage box as "Re-check" in `active_codex`;
  - legacy and malformed-observation snapshots render with no active box and `stage
    unknown`, through `render()` and through `ai-dashboard --once`;
  - paused/recovering/crashed overlays; no rendered line exceeds the width (wide emoji
    counted as 2) at widths 40–200;
  - empty state text; expanded view shows at most 8 events.
- Test `dashboard_render_curses_smoke`: run `ai-dashboard` under `pty.fork()` with
  `TERM=xterm-256color`, `AI_STATE_DIR` fixture, `AI_DASHBOARD_ROOT`/`AI_DASHBOARD_PROC`
  fixtures (P33; the interaction test too, so the header counts and the 10 cards are
  exactly the fixture's), send `q`; exits 0 within 10 s and the output
  ends with the terminal restored (contains the rmcup/normal-screen sequence or `stty -a`
  on the pty shows `icanon echo` after exit).
- Test `dashboard_render_curses_interaction` (P25): under a pty sized 30×140 with 10 fixture
  runs (more than fit): ↓ past the viewport keeps the selected card visible (its title in
  the screen dump), Enter shows its details, a resize to 20×100 (`TIOCSWINSZ` + SIGWINCH)
  switches to compact lines, then `q` exits 0; with an injected exception in `render`
  (test-only monkeypatch via a small importable entry point) the process exits nonzero and
  the terminal is restored. Each test bounded to 15 s.

### Validation
Targeted: `python3 -m unittest discover -s tests -k dashboard_render` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude sonnet): DONE. `dashboard.py` gained the pure renderer (`layout`/`render`,
segments of `(text, style)`; box layout from 120 columns, compact line below, `fit`/`cols`/`clip`
count wide characters), `render_text` (shared by `--once`/pipes; width from the terminal, else 140),
the curses view (`terminal_attributes`, `draw`, `interface`: q ↑ ↓ Enter a r, resize, scrolling that
keeps the selected card visible, 256-colour pairs or basic/bold/reverse) and `main` (TUI on a TTY,
otherwise `--once`; Ctrl-C exits 0). Deviations: a `selected` style was added for the selected
title; compact mode adds one `⛔ note` line for stopped/unknown runs so a decision's question stays
visible; the T007 text format (`stage … (state)`) is gone, one T007 assertion was updated to count
✓ marks. 15 `dashboard_render_*` tests (golden 140/120/119/60, worst case, stop/finished, plan
revision/decision/extra round/format retry, recheck, stop at start, P44 incl. `--once`, writer →
renderer for the 12 stop labels and overlays via `workflow.py observe`, legacy/malformed, widths
40–200, empty/expanded, pty smoke/interaction/failure). Targeted `-k dashboard_render` 15 OK;
`.ai/bin/ai-check` OK (541 tests, 8 shards).

## T009 — Docs and final audit for the dashboard
Status: DONE
Dependencies: T008
Model: haiku

### Goal
Users find and understand the dashboard; records match the code.

### Implementation notes
- README: section "Watch all pipelines" after "Leave it running": `ai-dashboard` (from any
  project's `.ai/bin` or `~/Projects/agents/scripts/`), what the eight boxes and colours mean
  (incl. Plan revision, the extra fix round and format retry details, a stop before Plan
  check), keys, `--once`/`--json`/`--all`, the 120-column box layout, tmux tip `tmux new -s
  dash ai-dashboard`, read-only and advisory (records in `.ai/local/` are agent-writable;
  never used to authorize); run it with the same `AI_STATE_DIR`/`XDG_STATE_HOME` as the
  pipelines and the watchdog timer (it lists the registry of that state root only; `--json`
  prints `state_root`, P37); a row in the scripts table.
- docs/workflow.md: the observation records and the host registry (one paragraph); the
  gate-broken guard (T010: no project helper runs after the approved gate changed; the
  watchdog notifies through its own installed copy of common.sh/workflow.py and verifies the
  gate digest before launching the checkout's ai-recover, so it needs no guard, P40; ai-recover
  and ai-pipeline do run the checkout helper before they compare the gate with the manifest,
  as today); `AI_DASHBOARD_PROC` and
  `AI_DASHBOARD_ROOT` as test-only variables (process source and root filter of the
  dashboard's discovery, P33), not user settings.
- Vault (`--knowledge-dir`): `agents-flow.md` note checked against the code (T002/T003 wrote it);
  hub `agents.md`: dated Decision lines ("2026-10-07 (Zack): pipeline dashboard, boxes
  layout, built ahead of OR-11/14/18" and "2026-10-09 (Zack): plan revision as its own
  dashboard box") and a Log line; `agents-backlog.md`: OR-12 partially and OR-19
  done-by-this-branch note, DB-01 now T001–T009 (no checkbox ticking);
  `agents-human-todo.md`: optional `ln -s ~/Projects/agents/scripts/ai-dashboard
  ~/.local/bin/` and upgrading projects' `.ai/bin` so their runs record stages.
- `.ai/handoff.md`: "## Flow chart" still starts with `Flow chart updated` and matches the
  vault note; "Manual testing for the human" (`### Needs you` / `### Covered by
  automated tests`, naming the tests).

### Likely affected modules
README.md, docs/workflow.md, vault notes, .ai/handoff.md

### Acceptance criteria
- `DocsConsistencyTest` passes; README mentions `ai-dashboard`, `--once`, `--json`, `--all`
  and the state-root note; docs/workflow.md mentions `AI_GATE_BROKEN`, `AI_DASHBOARD_PROC`
  and `AI_DASHBOARD_ROOT`.
- Handoff lists the manual checks (live TUI in tmux with two runs, resize across 120
  columns, `q`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-09 (claude haiku): done. README "Watch all pipelines" section (keys, `--once`/`--json`/`--all`,
120-column layout, tmux tip, state root, read-only) plus `ai-dashboard` rows in the Components and Modes
tables; `docs/workflow.md` "Observation records and the dashboard" (records, registry, read-only rule,
`AI_DASHBOARD_PROC`/`AI_DASHBOARD_ROOT` as test-only, watchdog needs no guard; `AI_GATE_BROKEN` was already
in the gate section). Vault: hub Decisions (2026-10-09 and 2026-10-07 lines) and Log, human-todo items (live
TUI check, optional PATH symlink and `.ai/bin` upgrade), backlog DB-01 status. Handoff: Needs you (two runs,
keys, resize, q), Human todos, Next action. Evidence: `python3 -m unittest discover -s tests -k Docs`: Ran 3
tests, OK; `.ai/bin/ai-check`: Ran 541 tests, OK (8 shards) on the final run; an earlier run had one failure in shard 2 (name not captured, not reproduced in the next run; flaky under load, to check). Limitation: the live TUI check in a real
terminal is not done here (human todo). Flow unchanged.
