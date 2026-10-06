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
5. Later tasks add steps for the state-root refusal.

## Human todos
None.

## Next action
The pipeline continues with T003.
