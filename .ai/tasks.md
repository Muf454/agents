# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files. This run is started with
`--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` (absolute path) so the vault flow
chart and hub Log can be updated. Source: vault backlog "Epic EV — Evidence integrity",
OR-01 and OR-02. Every task leaves `.ai/bin/ai-check` passing. Revised after two Codex plan
reviews (`.ai/reviews/plan.md`). Flow-chart rule (AGENTS.md, CLAUDE.md): every task that
changes workflow behaviour updates the vault `agents-flow.md` (diagram/notes and its
`updated:` frontmatter date) in the SAME task; T006 is only the final docs audit.

## T001 — Byte-check every accepted DONE checkpoint in ai-run (OR-01)
Status: DONE
Dependencies: none
Model: opus

### Goal
OR-01, runner part: an ordinary agent commit accepted as DONE (and the final handoff
commit) must contain exactly the bytes validation hashed. Today only the tier-1 checkpoint
(scripts/ai-run ~line 280) and ai-recover's `commit_and_rerun` check this.

### Implementation notes
In scripts/ai-run, `DONE` branch: after the runner's bookkeeping commit
`chore(ai): record $active_task runner checkpoint` (~line 296) and its `ai_guard_verify`,
when the task was DONE require: clean tree (`git status --porcelain --untracked-files=all`
empty), `ai_helper stamp verify`, and `ai_helper committed-matches-worktree`. On failure
`ai_die "The checkpoint of $active_task differs from the validated content: <detail>"`,
where detail is the helper's message (capture stderr, strip `Error: `) or "uncommitted
changes after the checkpoint" / "validation stamp not current". Keep the phrase
"differs from the validated content" (ai-recover's hard rules escalate on it). Do the same
after the final `chore(ai): record review handoff` commit (~line 236), before
`finished=yes` and before the "All tasks done" notification, with the label "final handoff".
Do NOT check BLOCKED tasks (unvalidated by design). Never reset, amend or change task
status on this stop. Keep the existing tier-1 check as is. The check compares every
tracked file, which is why it runs after the bookkeeping commit (workflow records
committed). Add a short comment saying so.
Test fixtures (P4): the mode case sets `git config core.filemode false` in the fixture
(as `test_committed_mode_must_match_validated_file` does) so the executable file on disk
does not show as a change; the mock session (new MOCK_CLAUDE mode in tests/test_workflow.py)
writes the file executable and commits it with mode 100644 (e.g. `git update-index
--chmod=-x` after `git add`). The final-handoff case needs a mismatch that ONLY the final
handoff commit introduces: a clean filter on `.ai/state.md` that rewrites only the phase
field line, e.g. `sed -E 's/^Phase: ready_for_review$/Phase: tampered/'` (the phases
comment in the state template also contains `ready_for_review`, so a global token filter
would fire earlier; task checkpoints have `Phase: implementing`).
Cleanliness (P4): the runner's EXIT handler appends a stop line to tracked
`.ai/run-log.md`, so after a stop the tree is not fully clean. Tests assert cleanliness at
the check boundary (the integrity check itself requires an empty `git status`; the stop
reason must be the byte mismatch, not "uncommitted changes") and afterwards assert that
`git status --porcelain` lists only `.ai/run-log.md`.
Flow chart (same task): in the vault `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`
add to "Inside one task" (or the build/checks part) that every accepted task and the final
handoff commit must contain exactly the validated bytes, else ⛔ stop; bump `updated:`.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `committed_bytes_run`:
  - filter case: `.gitattributes` with a clean filter on `*.txt` (as in
    `test_committed_content_must_match_validated_files`) and the default (self-committing)
    mock with a two-task queue → `ai-run` exits 1, last-error contains "differs from the
    validated content" and `T001.txt`; exactly one mock invocation (T002 never starts); the
    agent's commit and the bookkeeping commit are still in `git log` (nothing reset); T001
    stays DONE;
  - mode case: with `core.filemode=false`; `ai-run` exits 1 with "differs from the
    validated content" and the message names the mode (so the check ran on a clean tree,
    not the "uncommitted changes" branch); afterwards `git status --porcelain` lists only
    `.ai/run-log.md` (the EXIT handler's stop line); `git ls-tree HEAD` shows 100644 for the
    file while it is executable on disk (`os.access(..., os.X_OK)`); no tier-1 "the session
    did not commit" checkpoint commit exists;
  - final handoff only: the phase-line filter on `.ai/state.md` with a two-task queue;
    first assert both ordinary task checkpoints passed (both `chore(ai): record T00N runner
    checkpoint` commits exist, both tasks DONE, two "✅ Done" notifications); then `ai-run`
    exits 1 at the final handoff with "differs from the validated content" naming
    `.ai/state.md`; the `chore(ai): record review handoff` commit is still HEAD (not reset);
    afterwards only `.ai/run-log.md` is dirty; no "All tasks done" notification;
  - valid repo: a committed relative symlink plus a submodule (fixture repo added with
    `git -c protocol.file.allow=always submodule add`, committed before the run) → the queue
    completes (`tasks complete`), tree clean.
- Existing `test_committed_content_must_match_validated_files` and
  `test_committed_mode_must_match_validated_file` still pass.
- Vault flow chart shows the per-task/final-handoff byte check; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k committed_bytes_run` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
2026-10-06 (Claude, opus): `scripts/ai-run` gained `verify_checkpoint` (clean tree, `stamp
verify`, `committed-matches-worktree`; else `ai_die "The checkpoint of <label> differs from
the validated content: <detail>"`), called after each DONE task's bookkeeping commit and
after the `record review handoff` commit (label "final handoff"), before `finished=yes`.
BLOCKED tasks are not checked; tier-1 check unchanged. The "✅ Done" notification moved
after the check, so a rejected checkpoint never reports Done. New MOCK_CLAUDE mode
`exec-committed-644`; 4 tests `committed_bytes_run` (filter, mode, final handoff only,
symlink + submodule accepted). Targeted: `Ran 4 tests … OK`. Gate: `.ai/bin/ai-check` PASS,
172 tests (2026-10-06T05:36:13Z). Vault `agents-flow.md` "Inside one task" diagram + note
updated, `updated: 2026-10-06`.

## T002 — Byte-check before review and in the publish checks (OR-01)
Status: DONE
Dependencies: T001
Model: opus

### Goal
OR-01, pipeline part: `ai-pipeline` never sends to Codex review, and never publishes, a
HEAD whose committed bytes differ from the validated files on disk, including mismatches
introduced during a push attempt (push hooks run project code).

### Implementation notes
scripts/ai-pipeline: (1) in the main loop, right after `ensure_validated` and before
`ai-review --base` (~line 300), require a clean tree and `ai_helper committed-matches-worktree`;
on failure write `Committed content differs from the validated content: <detail>` to
`.ai/local/last-error` and `stop review` (ai-recover escalates on the phrase). (2) In
`publish_ready` (~line 127) add a clause right after the clean-tree check:
`elif ! why=$(ai_helper committed-matches-worktree 2>&1 >/dev/null); then why="committed content differs from the validated content: ${why#Error: }"`.
Order: guard, review-info, disputes, clean tree, committed bytes, tasks, review current,
stamp (committed bytes before "review current", so a hook commit with filtered bytes is
reported as a byte mismatch). (3) `push()` (~line 157): today a failed attempt goes
straight to the retry wait, and the third failure writes `git push failed (3 tries)` and
stops WITHOUT re-checking, so a hook that changed committed bytes during the last attempt
is reported as a plain push failure (which recovery may treat as transient). Restructure
so `publish_ready "$stage"` runs after EVERY push outcome (success or failure), before
the retry wait and before the terminal "3 tries" failure handling; e.g. per attempt:
`publish_ready; if git push …; then ok=1; fi; publish_ready; (( ok )) && break; try 3 →
failure stop; sleep`. Keep the pre-attempt check and the remote-equals-HEAD check after
success.
Test ideas: publish case: commit (before the run) a `.gitattributes` clean filter that
applies only to `.ai/reviews/current.md`; the pre-review check passes, the host commit
`record independent review` stores filtered bytes, so `publish_ready` must stop before any
push. Push-hook cases (P2): `.gitattributes` clean filter on `hooked.txt`; a
`.git/hooks/pre-push` that, once (marker file), writes `hooked.txt` on disk, commits it
(the filter changes the committed bytes; tree stays clean) and logs each invocation to a
file; variant A exits 1 (failed push → the retry's `publish_ready` must stop), variant B
exits 0 (successful push → the post-push `publish_ready` must stop); variant C: the hook
counts invocations and exits 1 unchanged on the first two, and on the third writes and
commits `hooked.txt` (filtered) and exits 1. Use the bare origin from `add_origin()` and
mock gh; `AI_SLEEP` is already mocked. Run variant C with `AI_AUTO_RECOVER=1` so the test
proves the stop escalates without a recovery Claude session (ai-recover's hard rule on
"differs from the validated content").
Flow chart (same task): vault `agents-flow.md` publish-checks node and bullet gain
"committed bytes = validated files", checked before every review and after every push
attempt (failed or successful); bump `updated:`.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `committed_bytes_pipeline`:
  - all tasks DONE but HEAD holds filtered bytes (fixture commit through a clean filter) →
    `ai-pipeline --approved --base main` stops during review; no codex call was made; message
    contains "differs from the validated content";
  - filter on `.ai/reviews/current.md` → stops with "Publish check failed at pull request
    preparation: committed content differs …"; nothing pushed to the bare origin, no gh call,
    no FINISHED notification;
  - push hook, failed push (variant A): last-error says "Publish check failed at push:
    committed content differs from the validated content" and names `hooked.txt`; the hook
    ran exactly once (no further push attempt after the failing check); the branch is not on
    origin; the hook's commit and every task commit are preserved (`git log`), all tasks
    DONE; no `gh pr create`/`gh pr edit` call; no FINISHED notification;
  - push hook, successful push (variant B): the same reason is recorded at stage `push`
    (after the push); hook ran once; no gh PR call; no FINISHED notification; commits and
    queue preserved;
  - push hook, third attempt (variant C): the hook ran exactly 3 times; last-error is the
    file-specific integrity reason ("committed content differs from the validated content"
    naming `hooked.txt`), NOT "git push failed (3 tries)"; no `recover-calls` file (no
    recovery Claude invocation); the hook's commit, every task commit and all DONE tasks
    preserved; branch not on origin; no gh PR call; no FINISHED notification;
  - valid repo with a committed symlink and a submodule → pipeline finishes and opens the PR
    (mock gh).
- Existing `publish` / `disputed_findings` / `triage_completion` tests still pass
  (including the push-retry tests: a harmless failed attempt still retries).
- Vault flow chart publish checks updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k committed_bytes_pipeline` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
2026-10-06 (Claude, opus): `scripts/ai-pipeline` (1) before `ai-review --base` (after
`ensure_validated`) requires a clean tree and `committed-matches-worktree`, else writes
"Committed content differs from the validated content: <detail>" and `stop review`;
(2) `publish_ready` gained the committed-bytes clause right after the clean-tree check
(before tasks/review-current/stamp); (3) `push()` runs `publish_ready` after every attempt,
failed or successful, before the retry wait and before the terminal "3 tries" handling (the
separate post-loop check is now inside the loop; remote-equals-HEAD unchanged). 7 tests
`committed_bytes_pipeline` (pre-review filter, filtered review at PR preparation, push hook
variants A/B/C incl. C with `AI_AUTO_RECOVER=1` → escalated, no `recover-calls`; harmless
failed push still retries; symlink + submodule → PR). Existing
`test_publish_ready_failed_push_that_changes_checkout_stops_before_retry` now asserts no
retry wait (the check runs before it, as this task requires). README/docs/workflow.md
publish-check paragraphs updated. Targeted: `Ran 7 tests … OK`; `-k publish_ready` 5 OK.
Gate: `.ai/bin/ai-check` PASS, 179 tests. Vault `agents-flow.md` (pre-review byte check node,
publish-checks node + bullets; `updated: 2026-10-06`) and hub Log updated.

## T003 — Refuse state roots that overlap the checkout or knowledge dir (OR-02)
Status: DONE
Dependencies: none
Model: opus

### Goal
OR-02 core: host authority state (`binding_dir()`, scripts/lib/workflow.py ~line 768) must
never live where agent sessions can write: inside (or around) the checkout or the
`--knowledge-dir`. Refused before any agent launches; defaults unchanged.

### Implementation notes
scripts/lib/workflow.py:
- `state_root()`: `AI_STATE_DIR` if non-empty, else `XDG_STATE_HOME` + `/ai-toolkit` if
  non-empty, else `~/.local/state/ai-toolkit`. A relative `AI_STATE_DIR`/`XDG_STATE_HOME` →
  `fail('AI_STATE_DIR must be an absolute path: …')` (resp. XDG_STATE_HOME).
- `overlap(a, b)`: True when either path equals or is inside the other
  (`Path.is_relative_to` both ways), checked for the lexical absolute paths
  (`os.path.abspath`) AND the real paths (`os.path.realpath`, which resolves an existing
  prefix of a not-yet-created path).
- `check_state_root(checkout, knowledge=None)`: the checkout is an EXPLICIT argument (never
  discovered from the current directory inside this function), so callers such as the
  watchdog (T005) can pass the target project. Refuse overlap with the checkout and, when
  given, with the knowledge dir. Message: `Host state directory <root> overlaps the checkout
  <path> (agent sessions can write there); set AI_STATE_DIR to a directory outside it.`
  (analogous: "overlaps the knowledge directory"). Do not claim OS isolation.
- `binding_dir()` uses `state_root()` and calls `check_state_root(<git toplevel>)`.
- New helper command `state-root-check [--checkout PATH] [KNOWLEDGE_DIR]` in `main()`
  (default checkout: `git rev-parse --show-toplevel` of the current directory).
Callers: scripts/ai-run right after `ai_root` (before the clean-tree check):
`ai_helper state-root-check ${knowledge_dir:+"$knowledge_dir"}` with `ai_die` on failure
(also covers `--triage`). scripts/ai-pipeline: resolve `--knowledge-dir` at parsing like
ai-run (`[[ -d ]]`, `cd -- "$2" && pwd -P`), store the resolved path in `run_args` and in
`orig_args` (rebuild it so the manifest records the absolute path), and after `ai_root`
run the same check before anything else (before the plan review's Codex call).
ai-recover is T004; the watchdog is T005.
Flow chart (same task): vault `agents-flow.md` gains the start check ("host state directory
must be outside the checkout and the knowledge dir; else ⛔ stop before any agent");
bump `updated:`.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, scripts/ai-pipeline, tests/test_workflow.py,
vault agents-flow.md

### Acceptance criteria
- Tests named `state_root`:
  - `AI_STATE_DIR` inside the checkout (direct path) → `ai-run --approved` and
    `ai-pipeline --approved` exit 1 with "overlaps the checkout"; no mock claude/codex
    invocation; nothing written under that directory;
  - `AI_STATE_DIR` = a symlink outside the checkout pointing into it → refused; a symlink
    inside the checkout pointing outside → refused;
  - `AI_STATE_DIR` inside / equal to / containing the `--knowledge-dir` → refused with
    "overlaps the knowledge directory" (both ai-run and ai-pipeline);
  - relative `AI_STATE_DIR` and (with AI_STATE_DIR unset) relative `XDG_STATE_HOME` →
    refused with "must be an absolute path";
  - the helpers `review-info`/`run-manifest gate` fail closed with the same message
    (binding_dir); `state-root-check --checkout <project>` run from another directory
    checks that project;
  - default: AI_STATE_DIR unset, `XDG_STATE_HOME` an absolute dir outside → works; and
    ai-pipeline with a relative `--knowledge-dir` records the absolute real path in the run
    manifest `args`.
- All existing tests still pass (fixture state root is a sibling of the project).
- Vault flow chart shows the start check; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k state_root` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
2026-10-06: `state_root()`, `overlap()`, `check_state_root(checkout, knowledge)` and the
`state-root-check [--checkout PATH] [KNOWLEDGE_DIR]` helper in scripts/lib/workflow.py;
`binding_dir()` checks against the git toplevel (key unchanged). ai-run and ai-pipeline run the
check right after `ai_root` (before lock, clean-tree check and any Codex/Claude call);
ai-pipeline resolves `--knowledge-dir` like ai-run and writes the absolute real path into
`orig_args` (run manifest) and `run_args`. Six `state_root` tests (inside/equal/containing
checkout, symlinks both ways, knowledge dir inside/equal/containing for both tools, relative
AI_STATE_DIR/XDG_STATE_HOME, helpers fail closed + `--checkout` from another dir, default XDG
path with relative `--knowledge-dir` recorded absolute). Targeted: `Ran 6 tests … OK`;
`.ai/bin/ai-check`: 185 tests OK, exit 0. docs/workflow.md and vault agents-flow.md updated
(start check node + bullet). Limitation: path check only, not OS isolation; ai-recover (T004)
and the watchdog (T005) not yet covered.

## T004 — ai-recover refuses an overlapping state root before reading the manifest (OR-02)
Status: DONE
Dependencies: T003
Model: opus

### Goal
OR-02, recovery part (P3): auto-recovery must not read authority from, or act on, a host
state directory the agents could write, and the human must learn why.

### Implementation notes
scripts/ai-recover: insert the check AFTER `escalate()` (and `resume()`) are defined and
`branch`/`reason` are initialised (~line 45), and BEFORE the first manifest read
(`approved_gate=$(ai_helper run-manifest gate …)`, ~line 52). On failure
(`check=$(ai_helper state-root-check 2>&1)`), keep the configuration error in the persisted
stop reason: set `reason="${check#Error: } (stopped during $stage: $reason)"` (or an
equivalent that contains both), then `escalate 'the host state directory is not safe for
recovery.' 'set AI_STATE_DIR to an absolute directory outside the checkout, then rerun
ai-pipeline.'`. `escalate` writes `$reason` to `.ai/local/last-error`, notifies once and
clears the marker. No Claude session, no commit, no `ai-pipeline` exec. The checkout is
checked (the knowledge dir is unknown here); the resumed ai-pipeline checks the knowledge
dir (T003).
Flow chart (same task): the auto-recovery diagram in vault `agents-flow.md` gains the
check before the run manifest is read (unsafe state dir → escalate to you); bump
`updated:`.

### Likely affected modules
scripts/ai-recover, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `recover_state_root`: with an approved run recorded in a safe state dir, then
  `AI_STATE_DIR` pointing inside the checkout (and, separately, a relative `AI_STATE_DIR`),
  `ai-recover --stage implementation` (with `AI_AUTO_RECOVER=1`) exits 1; stderr says
  "escalated to the human"; `.ai/local/last-error` contains "overlaps the checkout" (resp.
  "must be an absolute path") AND the original stop reason; exactly one "STOPPED, needs you"
  notification containing the configuration error; no `recover-calls` file (no recovery
  Claude session); no new commit; `pipeline.active` removed; the attempt budget in the safe
  state dir is unchanged.
- Existing `recover` tests still pass.
- Vault recovery diagram updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k recover_state_root` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
2026-10-06: scripts/ai-recover runs `ai_helper state-root-check` (checkout = git toplevel)
after `escalate()`/`resume()` are defined and before the first `run-manifest` read; on
failure `reason="<config error> (stopped during S: <original reason>)"` and it escalates
("the host state directory is not safe for recovery." / "set AI_STATE_DIR to an absolute
directory outside the checkout, then rerun ai-pipeline."). Test
`test_recover_state_root_unsafe_escalates_before_reading_the_manifest` (subtests: inside the
checkout, relative): exit 1, "escalated to the human", last-error holds both messages, one
new ⛔ containing the config error, no extra recover call, HEAD unchanged, marker removed,
run.json (attempt budget) byte-identical, nothing created inside the checkout. Targeted:
`Ran 1 test … OK`; `.ai/bin/ai-check`: 186 tests OK. docs/workflow.md recovery contract and
vault agents-flow.md recovery diagram + bullet updated. The test's recover-calls file
already exists from the earlier pipeline stop, so "no recovery session" is asserted as an
unchanged call count. Limitation: path check only, not OS isolation; knowledge dir is
checked by the resumed ai-pipeline, the watchdog is T005.

## T005 — Same check for the watchdog host copy, install and runtime (OR-02)
Status: DONE
Dependencies: T003
Model: opus

### Goal
OR-02, watchdog part: the timer's host copy of the scripts and the state root it uses must
not overlap the TARGET checkout (the `project` argument, not the caller's directory), so
the code that verifies the gate before crash recovery can't be agent-editable.

### Implementation notes
scripts/lib/watchdog.py `timer()` (~line 128) runs before `os.chdir(root)` (~line 267), so
the check must use the supplied `root` explicitly (P1): import `check_state_root`/`overlap`
from the sibling `workflow.py` (`sys.path` insert of `Path(__file__).resolve().parent`) and
call `check_state_root(root)`, or run `python3 <lib>/workflow.py state-root-check
--checkout <root>` with `cwd=root`; never rely on the caller's current directory. Install
path only, before `rmtree`/`copytree` and before writing any unit: refuse a relative
`XDG_DATA_HOME`; refuse when the host copy dir overlaps `root` (lexical and real paths,
both directions); run the state-root check for the environment the timer will forward.
Report as a clear error (exit 2 like other `parser.error`s), writing nothing.
`start_recovery()` (~line 190): replace the lexical `bin_dir.is_relative_to(root)` with
the real-path overlap check (both directions), and run the state-root check for `root`
BEFORE the gate digest / `run-manifest gate` calls; on failure return a reason that
contains the configuration error (e.g. `auto-recovery refused: Host state directory …
overlaps the checkout …`), so the human is notified and `systemd-run` is never called.
Uninstall stays unchanged. The watchdog does not check the knowledge dir (the resumed
ai-pipeline does, T003).
Flow chart (same task): the watchdog part of vault `agents-flow.md` notes that install and
auto-recovery refuse a host copy or state dir overlapping the checkout (⛔ notified, no
recovery started); bump `updated:`.

### Likely affected modules
scripts/lib/watchdog.py, tests/test_workflow.py, vault agents-flow.md

### Acceptance criteria
- Tests named `watchdog_host_root` (mock `systemctl` as in
  `test_watchdog_install_and_uninstall_timer`):
  - install launched from OUTSIDE any Git repository (cwd = a plain temp dir) with
    `AI_STATE_DIR` inside the target project → refused, message names the state dir and
    the project; no unit files under `XDG_CONFIG_HOME/systemd/user`, no host copy, no
    systemctl call; control: from outside Git with a safe state dir → installs;
  - install launched from ANOTHER checkout (cwd = a second git repo) with `AI_STATE_DIR`
    inside the target project only (not inside the caller's repo) → refused, nothing
    written; control: launched from another checkout with a safe state dir → installs;
  - `XDG_DATA_HOME` inside the target checkout, or a symlink pointing into it → refused,
    nothing written; relative `XDG_DATA_HOME` → refused;
  - runtime (P3): host copy (`host_watchdog`) with `--recover`, a crashed marker, an
    approved run, then `AI_STATE_DIR` inside the checkout → exit 1, one notification that
    contains the configuration error ("overlaps the checkout"), no `systemd-run.log`, no
    `recover-calls` (no Claude);
  - existing `test_watchdog_install_and_uninstall_timer` and watchdog recovery tests pass
    unchanged (default layout accepted).
- Vault watchdog part updated; `updated:` date bumped.

### Validation
Targeted: `python3 -m unittest discover -s tests -k watchdog_host_root` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
2026-10-06: scripts/lib/watchdog.py imports `check_state_root`/`overlap` from the sibling
workflow.py (`sys.dont_write_bytecode`: no `__pycache__` in the digested `.ai/bin`). Install
path (before `rmtree`/`copytree`/units) raises `Refused` for a relative `XDG_DATA_HOME`, a
host copy overlapping `root`, or `check_state_root(root)` failing → `parser.error('refusing
to install the timer: …')`, exit 2. `start_recovery()` uses `overlap(bin_dir, root)` and
runs `check_state_root(root)` before the digest/`run-manifest gate`, returning `auto-recovery
refused: Host state directory … overlaps the checkout …`. Uninstall unchanged. Tests
`test_watchdog_host_root_install_checks_the_target_checkout` (subtests: plain dir and another
checkout as cwd, refused + safe control; XDG_DATA_HOME inside / symlink into checkout;
relative) and `test_watchdog_host_root_recovery_refuses_a_state_dir_in_the_checkout`.
`python3 -m unittest discover -s tests -k watchdog_host_root`: Ran 2 tests OK; `-k watchdog`:
19 OK (existing install/recovery tests unchanged). `.ai/bin/ai-check`: Ran 188 tests OK.
Docs: docs/workflow.md, README.md; vault agents-flow.md watchdog node + note.

## T006 — Final docs audit for the new checks
Status: TODO
Dependencies: T002, T004, T005
Model: sonnet

### Goal
README and docs/workflow.md describe the OR-01/OR-02 stop points accurately; final audit
and consolidation of the vault flow chart that T001–T005 already updated task by task,
plus the PR's flow-chart line and manual testing instructions.

### Implementation notes
docs/workflow.md: next to the review-provenance paragraph (~line 234) say the state root
must be an absolute path outside the checkout and the knowledge directory (checked at
every start, by every host-state read, by ai-recover before it reads the run manifest and
by the watchdog against the target project at install and before recovery; a
configuration check, not OS isolation); in the runner/pipeline sections say every
accepted DONE checkpoint, the final handoff commit, the pre-review step and the publish
checks (before and after every push) require committed bytes = validated files on disk;
add the limitation: repositories whose content passes clean/smudge or eol filters (Git
LFS, `text=auto` with CRLF files, `ident`) stop with "differs from the validated content".
README: same in the pipeline/publish description and the watchdog install section (~line
630: the host copy and state directory must be outside the checkout). Add
`docs_consistency` required-sentence assertions for the two key sentences. Vault
`~/zWiki/zWiki/20 Projects/agents/agents-flow.md`: audit the per-task changes of T001–T005
against the final code (consistent wording, no duplicates, `updated:` date current); fix
only what is wrong or missing. Append a dated line to the hub `agents.md` Log (never tick
vault checkboxes). PR description: replace the handoff `## Flow chart` placeholder with a line
that still starts "Flow chart updated" (test
`test_pr_body_flow_this_repo_declares_the_flow_chart` requires it), e.g.
"Flow chart updated: OR-01/OR-02 checks added to agents-flow.md (date)". Update the
handoff's "Manual testing for the human" with scratch-project steps (watchdog install from
another directory, refusal before agents launch, final-handoff mismatch diagnostics).

### Likely affected modules
README.md, docs/workflow.md, tests/test_workflow.py, .ai/handoff.md, vault agents-flow.md,
vault agents.md (Log)

### Acceptance criteria
- Tests named `docs_consistency` pass, including the new required sentences.
- Docs describe only implemented behaviour (cross-check against T001–T005 results) and do
  not call the state-root check isolation or sandboxing.
- Vault flow chart audited (consistent with the code, `updated:` date current) and hub
  Log updated; handoff "Flow chart" section starts with "Flow chart updated" and states
  what changed.

### Validation
Targeted: `python3 -m unittest discover -s tests -k docs_consistency` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.
