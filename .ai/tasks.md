# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs and the vault notes named below. Never edit
`.ai/bin`, `.ai/prompts` or other gate files. This run is started with
`--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` (absolute path) so the vault flow
chart and hub Log can be updated. Source: vault backlog "Epic EV — Evidence integrity",
OR-01 and OR-02. Every task leaves `.ai/bin/ai-check` passing.

## T001 — Byte-check every accepted DONE checkpoint in ai-run (OR-01)
Status: TODO
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
after the final `chore(ai): record review handoff` commit (~line 236), task label `none`/
"final handoff". Do NOT check BLOCKED tasks (unvalidated by design). Never reset, amend or
change task status on this stop. Keep the existing tier-1 check as is. The check compares
every tracked file, which is why it runs after the bookkeeping commit (workflow records
committed). Add a short comment saying so.
Tests: add mock claude modes in tests/test_workflow.py MOCK_CLAUDE (runner path) as needed,
e.g. one that commits normally after writing its file (the default may already do this),
one that stages an executable file then runs `git update-index --chmod=-x` before
committing (mode case), one that commits a relative symlink.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py

### Acceptance criteria
- Tests named `committed_bytes_run`:
  - filter case: `.gitattributes` with a clean filter on `*.txt` (as in
    `test_committed_content_must_match_validated_files`) and the default (self-committing)
    mock → `ai-run` exits 1, last-error contains "differs from the validated content" and the
    file name; only one mock invocation (the next task never starts); the task's commit is
    not reset;
  - mode case: committed 100644 while the file on disk is executable → same stop, message
    names the mode;
  - valid repo: a committed relative symlink plus a submodule (fixture repo added with
    `git -c protocol.file.allow=always submodule add`, committed before the run) → the queue
    completes (`tasks complete`), tree clean.
- Existing `test_committed_content_must_match_validated_files` still passes.

### Validation
Targeted: `python3 -m unittest discover -s tests -k committed_bytes_run` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T002 — Byte-check before review and in the publish checks (OR-01)
Status: TODO
Dependencies: T001
Model: opus

### Goal
OR-01, pipeline part: `ai-pipeline` never sends to Codex review, and never publishes, a
HEAD whose committed bytes differ from the validated files on disk.

### Implementation notes
scripts/ai-pipeline: (1) in the main loop, right after `ensure_validated` and before
`ai-review --base` (~line 300), require a clean tree and `ai_helper committed-matches-worktree`;
on failure write `Committed content differs from the validated content: <detail>` to
`.ai/local/last-error` and `stop review` (ai-recover escalates on the phrase). (2) In
`publish_ready` (~line 127) add a clause after the clean-tree check:
`elif ! why=$(ai_helper committed-matches-worktree 2>&1 >/dev/null); then why="committed content differs from the validated content: ${why#Error: }"`.
Keep the order: guard, review-info, disputes, clean tree, committed bytes, tasks, review
current, stamp. No other behaviour change.
Test idea for publish: commit (before the run) a `.gitattributes` clean filter that applies
only to `.ai/reviews/current.md`; the pre-review check passes (file not yet committed by the
pipeline), the host commit `record independent review` stores filtered bytes, so
`publish_ready` must stop before any push/`gh` call.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py

### Acceptance criteria
- Tests named `committed_bytes_pipeline`:
  - all tasks DONE but HEAD holds filtered bytes (fixture commit through a clean filter) →
    `ai-pipeline --approved --base main` stops during review; no codex call was made; message
    contains "differs from the validated content";
  - filter on `.ai/reviews/current.md` → stops with "Publish check failed at pull request
    preparation: committed content differs …"; no push to the bare origin, no gh call, no
    FINISHED notification;
  - valid repo with a committed symlink and a submodule → pipeline finishes and opens the PR
    (mock gh).
- Existing `publish` / `disputed_findings` / `triage_completion` tests still pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k committed_bytes_pipeline` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T003 — Refuse state roots that overlap the checkout or knowledge dir (OR-02)
Status: TODO
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
- `check_state_root(knowledge=None)`: refuse overlap with the checkout
  (`git rev-parse --show-toplevel`) and, when given, with the knowledge dir. Message:
  `Host state directory <root> overlaps the checkout <path> (agent sessions can write
  there); set AI_STATE_DIR to a directory outside it.` (analogous for the knowledge dir).
  Do not claim OS isolation.
- `binding_dir()` uses `state_root()` and calls `check_state_root()` (checkout only).
- New helper command `state-root-check [KNOWLEDGE_DIR]` in `main()`.
Callers: scripts/ai-run right after `ai_root` (before the clean-tree check):
`ai_helper state-root-check ${knowledge_dir:+"$knowledge_dir"}` with `ai_die` on failure
(also covers `--triage`). scripts/ai-pipeline: resolve `--knowledge-dir` at parsing like
ai-run (`[[ -d ]]`, `cd -- "$2" && pwd -P`), store the resolved path in `run_args` and in
`orig_args` (rebuild it so the manifest records the absolute path), and after `ai_root`
run the same check before anything else (before the plan review's Codex call).
scripts/ai-recover: right after `ai_root`/lock, `ai_helper state-root-check` (checkout only)
or `escalate` with its message.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-run, scripts/ai-pipeline, scripts/ai-recover,
tests/test_workflow.py

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
  - the helper `review-info`/`run-manifest` fails closed with the same message (binding_dir);
  - default: AI_STATE_DIR unset, `XDG_STATE_HOME` an absolute dir outside → works; and
    ai-pipeline with a relative `--knowledge-dir` records the absolute real path in the run
    manifest `args`.
- All existing tests still pass (fixture state root is a sibling of the project).

### Validation
Targeted: `python3 -m unittest discover -s tests -k state_root` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T004 — Same check for the watchdog host copy (OR-02)
Status: TODO
Dependencies: T003
Model: opus

### Goal
OR-02, watchdog part: the timer's host copy of the scripts and the state root it forwards
must not overlap the checkout, so the code that verifies the gate before crash recovery
can't be agent-editable.

### Implementation notes
scripts/lib/watchdog.py `timer()` (~line 128), install path only, before `rmtree`/`copytree`
and before writing any unit: refuse a relative `XDG_DATA_HOME`; refuse when the host copy
dir overlaps `root` (lexical and real paths, both directions; reuse T003's semantics:
import `overlap`/`check_state_root` from the sibling `workflow.py` via `sys.path` of
`Path(__file__).parent`, or run `python3 <lib>/workflow.py state-root-check` with
`cwd=root`, whichever is simpler and works for the host copy too); run the state-root check
for the environment the timer will forward. Report via `parser.error`-style exit 2 with a
clear message, writing nothing. `start_recovery()` (~line 190): replace the lexical
`bin_dir.is_relative_to(root)` with the real-path overlap check (both directions) and
return a refusal reason when `state-root-check` fails, before launching `ai-recover`.
Uninstall stays unchanged. The watchdog does not check the knowledge dir (the resumed
ai-pipeline does, T003).

### Likely affected modules
scripts/lib/watchdog.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `watchdog_host_root`:
  - `XDG_DATA_HOME` inside the checkout → `--install-timer` exits non-zero with a message
    naming both paths; no unit files under `XDG_CONFIG_HOME/systemd/user`, no host copy;
  - `XDG_DATA_HOME` a symlink pointing into the checkout → same refusal;
  - `AI_STATE_DIR` inside the checkout → `--install-timer` refused, nothing written;
  - relative `XDG_DATA_HOME` → refused;
  - existing `test_watchdog_install_and_uninstall_timer` and watchdog recovery tests pass
    unchanged (default layout accepted).

### Validation
Targeted: `python3 -m unittest discover -s tests -k watchdog_host_root` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.

## T005 — Docs and flow chart for the new checks
Status: TODO
Dependencies: T002, T004
Model: sonnet

### Goal
README, docs/workflow.md and the vault flow chart describe the OR-01/OR-02 stop points
accurately (the behaviour visible in the flow changes: a check before review, the publish
checks, and a start check).

### Implementation notes
docs/workflow.md: next to the review-provenance paragraph (~line 234) say the state root
must be an absolute path outside the checkout and the knowledge directory (checked at
every start and by every host-state read; a configuration check, not OS isolation); in the
runner/pipeline sections say every accepted DONE checkpoint, the final handoff commit, the
pre-review step and the publish checks require committed bytes = validated files on disk;
add the limitation: repositories whose content passes clean/smudge or eol filters (Git LFS,
`text=auto` with CRLF files, `ident`) stop with "differs from the validated content".
README: same in the pipeline/publish description and the watchdog install section (~line
630: the host copy and state directory must be outside the checkout). Add
`docs_consistency` required-sentence assertions for the two key sentences. Vault
`~/zWiki/zWiki/20 Projects/agents/agents-flow.md`: add "committed bytes = validated files"
to the publish-checks node and bullet, a note that the same check runs after every task and
before every review, and the start check on the state directory; append a dated line to the
hub `agents.md` Log (never tick vault checkboxes). PR description: replace the handoff
`## Flow chart` placeholder with a line that still starts "Flow chart updated" (test
`test_pr_body_flow_this_repo_declares_the_flow_chart` requires it), e.g.
"Flow chart updated: OR-01/OR-02 checks added to agents-flow.md (date)".

### Likely affected modules
README.md, docs/workflow.md, tests/test_workflow.py, vault agents-flow.md, vault agents.md (Log)

### Acceptance criteria
- Tests named `docs_consistency` pass, including the new required sentences.
- Docs describe only implemented behaviour (cross-check against T001–T004 results) and do
  not call the state-root check isolation or sandboxing.
- Vault flow chart and hub Log updated; handoff "Flow chart" section present.

### Validation
Targeted: `python3 -m unittest discover -s tests -k docs_consistency` (output must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms.

### Result / notes
Pending.
