# Handoff

## What has been implemented?
- T001 (OR-01, runner): `scripts/ai-run` byte-checks every accepted DONE checkpoint and the
  final `record review handoff` commit (`verify_checkpoint`: clean tree, current stamp,
  `committed-matches-worktree`); a mismatch stops with "The checkpoint of <task|final
  handoff> differs from the validated content: <detail>" and nothing is reset. "✅ Done" is
  now sent only after the check passes. BLOCKED tasks are not checked.

Batch 1 (flow hardening, T001–T017) was merged via PR #11; its
records are in Git history. This branch (`feature/evidence-or01-or02`, from origin/master
d6038f6) plans backlog items OR-01 (committed bytes on every accepted checkpoint) and OR-02
(disjoint authority/state roots, incl. the watchdog host copy). See `.ai/project-spec.md`,
`.ai/current-plan.md`, `.ai/tasks.md` (T001–T006, revised 2026-10-06 after two Codex plan reviews). Planned by Claude as Zack's delegate on
2026-10-05; the pipeline's Codex plan review gates the plan.

## Validation
Baseline before planning: `.ai/bin/ai-check` (shell syntax + 168 unittest tests).
After T001: `.ai/bin/ai-check` PASS, 172 tests (2026-10-06T05:36:13Z).

## Open assumptions (for the plan review and Zack)
- Overlap is bidirectional (a state root containing the checkout/knowledge dir is refused).
- A symlinked state root is refused only when it (or its real path) overlaps; a symlink to
  a disjoint location is accepted.
- Repositories with clean/smudge/eol filters (Git LFS, CRLF with `text=auto`) now stop at
  every accepted task; documented limitation, not supported here.
- The watchdog checks the checkout only; the resumed ai-pipeline checks the knowledge dir.

## Flow chart
Flow chart updated: T001 added the committed-bytes check to "Inside one task" in
agents-flow.md (2026-10-06); T002–T005 add theirs, T006 finalizes this line (a test
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
3. Later tasks add steps for the pipeline checks and the state-root refusal.

## Human todos
None.

## Next action
The pipeline continues with T002/T003.
