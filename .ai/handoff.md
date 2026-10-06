# Handoff

## What has been implemented?
- T001 (OR-01, runner): `scripts/ai-run` byte-checks every accepted DONE checkpoint and the
  final `record review handoff` commit (`verify_checkpoint`: clean tree, current stamp,
  `committed-matches-worktree`); a mismatch stops with "The checkpoint of <task|final
  handoff> differs from the validated content: <detail>" and nothing is reset. "✅ Done" is
  now sent only after the check passes. BLOCKED tasks are not checked.
- T002 (OR-01, pipeline): `scripts/ai-pipeline` requires a clean tree and committed bytes =
  validated files before every Codex review ("Committed content differs from the validated
  content: …", stop review); `publish_ready` checks committed bytes right after the
  clean-tree check; `push()` runs `publish_ready` after every attempt (failed or successful)
  before the retry wait, so a push hook's filtered commit is reported as an integrity stop
  (ai-recover escalates) rather than "git push failed (3 tries)".
- T003 (OR-02 core): ai-run/ai-pipeline refuse an overlapping or relative host state
  directory before any agent; helpers fail closed.
- T004 (OR-02, recovery): `scripts/ai-recover` checks the state directory before reading the
  run manifest and escalates (config error + original stop reason) without a Claude
  session, commit or attempt.
- T005 (OR-02, watchdog): `scripts/lib/watchdog.py` `--install-timer` checks the target
  checkout (not the caller's directory) before writing anything: relative `XDG_DATA_HOME`,
  a host copy overlapping the checkout, or an overlapping state dir → exit 2. At runtime
  `start_recovery()` uses the real-path overlap check for its own copy and the state-root
  check before the gate digest/manifest; refusal is notified, `systemd-run` never called.

Batch 1 (flow hardening, T001–T017) was merged via PR #11; its
records are in Git history. This branch (`feature/evidence-or01-or02`, from origin/master
d6038f6) plans backlog items OR-01 (committed bytes on every accepted checkpoint) and OR-02
(disjoint authority/state roots, incl. the watchdog host copy). See `.ai/project-spec.md`,
`.ai/current-plan.md`, `.ai/tasks.md` (T001–T006, revised 2026-10-06 after two Codex plan reviews). Planned by Claude as Zack's delegate on
2026-10-05; the pipeline's Codex plan review gates the plan.

## Validation
Baseline before planning: `.ai/bin/ai-check` (shell syntax + 168 unittest tests).
After T001: `.ai/bin/ai-check` PASS, 172 tests (2026-10-06T05:36:13Z).
After T002: `.ai/bin/ai-check` PASS, 179 tests.
After T004: `.ai/bin/ai-check` PASS, 186 tests (2026-10-06).
After T005: `.ai/bin/ai-check` PASS, 188 tests (2026-10-06).

## Open assumptions (for the plan review and Zack)
- Overlap is bidirectional (a state root containing the checkout/knowledge dir is refused).
- A symlinked state root is refused only when it (or its real path) overlaps; a symlink to
  a disjoint location is accepted.
- Repositories with clean/smudge/eol filters (Git LFS, CRLF with `text=auto`) now stop at
  every accepted task; documented limitation, not supported here.
- The watchdog checks the checkout only; the resumed ai-pipeline checks the knowledge dir.

## Flow chart
Flow chart updated: T001 added the committed-bytes check to "Inside one task" in
agents-flow.md (2026-10-06); T002 added the pre-review byte check and the byte check in the
publish checks (after every push attempt); T003–T005 add theirs, T006 finalizes this line (a test
requires the section to start with these words).

## Manual testing for the human
1. Committed-bytes stop (T001): in a scratch project set up with this branch's
   `setup-project` and a one-task approved plan, commit `.gitattributes` with
   `*.txt filter=sneaky` and run `git config filter.sneaky.clean 'sed s/a/b/'`. Run
   `.ai/bin/ai-run --approved`; when the session commits a `.txt` file containing "a",
   expect exit 1 with "The checkpoint of T001 differs from the validated content:
   Committed content of <file> differs …", no "✅ Done" notification, the agent and
   `record T001 runner checkpoint` commits still in `git log`, and only `.ai/run-log.md`
   dirty.
2. Without the filter the same run completes normally ("✅ Done", "All tasks done").
3. Push-hook stop (T002): in a scratch project with a bare `origin` remote and a finished
   one-task plan, commit `.gitattributes` with `hooked.txt filter=hooked`, run
   `git config filter.hooked.clean 'sed s/original/tampered/'`, and add a
   `.git/hooks/pre-push` that runs `echo original > hooked.txt; git add hooked.txt;
   git commit -qm hook` and exits 1. Run `.ai/bin/ai-pipeline --approved --base main`:
   expect exit 1 with "Publish check failed at push: committed content differs from the
   validated content: Committed content of hooked.txt differs …", one hook run (no retry),
   no PR opened, no FINISHED notification and the hook's commit still in `git log`. With
   auto-recovery on, expect it to be escalated to you, without a recovery Claude session.
4. Without the hook the same pipeline pushes and opens the PR normally.
5. State-root refusal (T003): in a scratch project with an approved plan, run
   `AI_STATE_DIR="$PWD/host-state" .ai/bin/ai-run --approved` and the same with
   `.ai/bin/ai-pipeline --approved --base main --no-pr`: expect exit 1 with "Host state
   directory … overlaps the checkout … set AI_STATE_DIR to a directory outside it.", no
   Claude/Codex session, and no `host-state` directory created. With `--knowledge-dir ~/notes`
   and `AI_STATE_DIR=~/notes/state` expect "overlaps the knowledge directory";
   `AI_STATE_DIR=relative` expects "AI_STATE_DIR must be an absolute path". With
   `AI_STATE_DIR` unset (default location) both run normally.
6. Recovery refusal (T004): in that scratch project, let an approved
   `ai-pipeline --approved --base main --no-pr` stop (e.g. a failing check) with the default
   state directory, then run `AI_STATE_DIR="$PWD/host-state" AI_AUTO_RECOVER=1
   .ai/bin/ai-recover --stage implementation`: expect exit 1 with "escalated to the human:
   the host state directory is not safe for recovery.", one "⛔ STOPPED, needs you" message
   naming "overlaps the checkout" and the original stop reason, the same text in
   `.ai/local/last-error`, no Claude session, no new commit, no `.ai/local/pipeline.active`,
   and an unchanged `attempts` in the default state dir's `run.json`. `AI_STATE_DIR=relative`
   gives "AI_STATE_DIR must be an absolute path" the same way.
7. Watchdog install refusal (T005): from a plain directory outside any Git repository, run
   `AI_STATE_DIR=<project>/host-state <project>/.ai/bin/ai-watchdog <project> --install-timer`:
   expect exit 2 with "refusing to install the timer: Host state directory … overlaps the
   checkout <project> …", and no new `ai-watchdog-*` unit in `~/.config/systemd/user`, no
   copy under `~/.local/share/ai-toolkit/watchdog`. The same with
   `XDG_DATA_HOME=<project>/data` gives "Host copy … overlaps the checkout";
   `XDG_DATA_HOME=relative` gives "XDG_DATA_HOME must be an absolute path". Without these
   overrides it installs normally (then `--uninstall-timer`).
8. Watchdog recovery refusal (T005): with the timer installed with `--recover` and a crashed
   pipeline (`.ai/local/pipeline.active` holding a dead PID) after an approved run, run the
   host copy (`~/.local/share/ai-toolkit/watchdog/<unit>/bin/ai-watchdog <project> --recover`)
   with `AI_STATE_DIR=<project>/host-state AI_AUTO_RECOVER=1`: expect exit 1, one ⛔ message
   ending "(auto-recovery refused: Host state directory … overlaps the checkout …)" and no
   `ai-recover-*` systemd unit started.

## Human todos
None.

## Next action
The pipeline continues with T006.
