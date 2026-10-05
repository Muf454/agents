# Spec: Evidence integrity: OR-01, OR-02

Source: vault [[agents-backlog]], "Epic EV — Evidence integrity", items OR-01 and OR-02 (both
P0, Source CODEX, "Suggested first batch" positions 1 and 2). Chosen and planned by Claude as
Zack's delegate on 2026-10-05; the pipeline's Codex plan review gates it. Hub decisions
respected: roles vs providers (no new provider assumptions), AD-5 (the watchdog only
observes; `ai-recover` stays the single recovery executor), "auto-recovery never changes the
gate", and OR-02's "don't advertise it as OS isolation".

## Requirements
- **OR-01 Committed bytes on every accepted checkpoint.** `committed-matches-worktree`
  (scripts/lib/workflow.py `committed_matches_worktree`) today runs only after the runner's
  tier-1 checkpoint (scripts/ai-run ~line 280) and the recovery checkpoint (scripts/ai-recover
  ~line 168). It must also run:
  - in `ai-run`, after every task accepted as DONE (validation passed), once the runner's
    bookkeeping commit `chore(ai): record T… runner checkpoint` is made, together with a clean
    tree and `stamp verify`; and after the final `chore(ai): record review handoff` commit;
  - in `ai-pipeline`, before every independent review (`ai-review --base`) and as part of
    `publish_ready` (before every push attempt and after each push).
  A mismatch (clean/smudge filter, mode difference) stops with a clear reason containing
  "differs from the validated content" (an existing phrase `ai-recover` always escalates)
  plus the helper's own detail (file and kind of difference). Nothing is reset or
  rewritten; the queue is not changed by the stop.
- **OR-02 Disjoint authority roots.** The host state root used by `binding_dir()`
  (`AI_STATE_DIR`, else `$XDG_STATE_HOME/ai-toolkit`, else `~/.local/state/ai-toolkit`) is
  refused when:
  - `AI_STATE_DIR` (or, when it is unset, a non-empty `XDG_STATE_HOME`) is a relative path;
  - the root overlaps the checkout (equal, inside, or containing), comparing both the
    absolute path as given and its real path (symlinks resolved; a not-yet-existing tail is
    resolved through its nearest existing parent);
  - the same overlap with the `--knowledge-dir` of `ai-run`/`ai-pipeline` (real path).
  The checkout check is enforced inside `binding_dir()` (every host-state consumer fails
  closed); the knowledge-dir check is a new helper command run by `ai-run` and `ai-pipeline`
  right after `ai_root`, before any agent (Claude or Codex) launches. `ai-recover` runs the
  checkout check first and escalates with its message. `ai-pipeline` resolves
  `--knowledge-dir` to its real absolute path at argument parsing (it must exist), passes
  that to `ai-run` and records it in the run manifest arguments.
- **OR-02 Watchdog host copy.** `ai-watchdog --install-timer` refuses a host copy directory
  (`$XDG_DATA_HOME/ai-toolkit/watchdog/<name>`; a relative `XDG_DATA_HOME` is refused) or a
  state root that overlaps the checkout (same rules), before writing anything.
  `start_recovery` refuses (and reports) when the running copy's directory overlaps the
  checkout by real path or the state-root check fails.
- Defaults are unchanged: with no `AI_STATE_DIR`/`XDG_STATE_HOME` set and the project outside
  `~/.local/state`, everything behaves as today.
- Docs (README, docs/workflow.md) and the vault flow chart `agents-flow.md` describe the new
  stop points; wording says this is a configuration check, not OS isolation.

## Non-goals
OS-level sandboxing; changing what the fingerprint hashes; Git LFS/eol-filter support (such
repositories stop with the clear reason; documented); other backlog items (OR-03…); checking
the watchdog against the knowledge directory (the resumed `ai-pipeline` does that before any
agent); gate files (`.ai/bin`, `.ai/prompts`, `.ai/validate`, permissions).

## Acceptance
- A clean-filter or mode mismatch in an ordinary agent commit stops `ai-run` before the next
  task and `ai-pipeline` before review/publication, with "differs from the validated content";
  repositories with committed symlinks and a submodule pass end to end.
- Overlapping (direct path, symlink, knowledge dir) or relative state roots are refused with
  a message naming both paths, before any mock agent is invoked; defaults still work.
- `ai-watchdog --install-timer` with an overlapping host copy/state root is refused and
  writes no unit files and no host copy.
- New tests in `tests/test_workflow.py`; all existing tests still pass; `.ai/validate` passes.
