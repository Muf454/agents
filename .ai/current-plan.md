# Plan: Evidence integrity (OR-01, OR-02)

## Assessment (origin/master d6038f6)
- `committed_matches_worktree` (scripts/lib/workflow.py ~1416, dispatched at ~1727): every
  HEAD blob must equal `git hash-object --no-filters` of the file on disk; modes 100755/100644
  must match the executable bit; symlinks compared by target; submodules (160000) skipped
  (the fingerprint checks them). It compares ALL tracked files, so it needs a tree where the
  workflow records are committed too.
- Callers: only ai-run:280 (tier-1 checkpoint) and ai-recover:168 (`commit_and_rerun`). The
  normal path (the session commits itself, ai-run ~274 `DONE`) only runs `ai-check` on the
  worktree and then commits bookkeeping (ai-run ~296). `ai-pipeline` checks `stamp verify`
  (`ensure_validated`, `publish_ready`) but never committed bytes.
- `fingerprint()` (~512) hashes worktree content minus state/handoff/run-log, `.ai/local/`,
  `.ai/reviews/`; validation = worktree bytes. So "HEAD == disk" + "stamp current" =
  "committed bytes were validated".
- `binding_dir()` (~768) takes `AI_STATE_DIR` / `XDG_STATE_HOME` unchecked; used by the run
  manifest, stages, review/recheck/plan bindings, disputes and fix rounds.
- `ai-run` resolves `--knowledge-dir` with `pwd -P` at parse time; `ai-pipeline` passes it
  through raw (and records raw `orig_args` in the manifest).
- Watchdog (scripts/lib/watchdog.py): `timer()` (~128) copies scripts to
  `$XDG_DATA_HOME/ai-toolkit/watchdog/<name>`; `start_recovery()` (~190) refuses only when its
  own bin dir `is_relative_to(root)`; `FORWARDED_ENV` (~181) forwards `AI_STATE_DIR` and
  `XDG_STATE_HOME`.
- Tests: `tests/test_workflow.py` (168 tests, unittest, mock claude/codex/gh). The fixture's
  state root `base/host-state` and project `base/project with spaces` are siblings
  (disjoint), so existing tests are unaffected by OR-02.
  `test_committed_content_must_match_validated_files` covers only the tier-1 filter case.

## Approach
1. T001 (opus) OR-01 in `ai-run`: after the bookkeeping commit of a DONE task, and after
   the final handoff commit, require clean tree + `stamp verify` + `committed-matches-worktree`
   (same triple as tier-1), else `ai_die "The checkpoint of $T differs from the validated
   content: <helper detail>"`. Tier-1 keeps its own earlier check.
2. T002 (opus) OR-01 in `ai-pipeline`: a committed-bytes check before each
   `ai-review --base` (after `ensure_validated`; stop stage `review`) and a new
   `publish_ready` clause after the clean-tree check.
3. T003 (opus) OR-02 core: `state_root()` + `overlap(a, b)` in workflow.py; `binding_dir()`
   enforces relative/checkout rules; new helper `state-root-check [KNOWLEDGE_DIR]`; called by
   ai-run and ai-pipeline right after `ai_root` (before any agent) and by ai-recover (escalate);
   ai-pipeline resolves `--knowledge-dir` at parsing and records the resolved path.
4. T004 (opus) OR-02 watchdog: install-time refusal (host copy dir and state root vs
   checkout) before any file is written; `start_recovery` uses real-path overlap and the
   state-root check of its own copy.
5. T005 (sonnet) docs: README, docs/workflow.md, vault agents-flow.md (pre-review check,
   publish check, start check), hub Log line; `docs_consistency` sentences.

Dependencies: T001 → T002; T003 → T004; T005 after all. T001 and T003 are independent.

## API / data changes
- New helper command `state-root-check [KNOWLEDGE_DIR]` (silent on success; an `Error:`
  message naming the state root and the overlapping directory otherwise).
- `binding_dir()` may now fail (ValueError → `Error:`, exit 1) for relative/overlapping roots.
- Run manifest `args` holds the resolved absolute `--knowledge-dir` for new runs.
- No change to file formats, hashes or the fingerprint.

## Risks
- **Filtered repositories** (Git LFS, `text=auto`/`eol` conversion of CRLF files, `ident`)
  now stop at every DONE task, not only on tier-1 checkpoints. Intended (fail closed), but
  such projects can't use the pipeline until supported; documented as a limitation.
- The pipeline running THIS change uses the frozen `.ai/bin` (old code); the new checks
  take effect only for runs after merge/upgrade. Tests exercise `scripts/`.
- "Overlap" is bidirectional: a state root that CONTAINS the checkout or knowledge dir (e.g.
  `AI_STATE_DIR=$HOME`) is refused too. Assumption: acceptable, clearer than one-way.
- Symlinked roots: refused when the given path or its real path overlaps; a symlink to a
  disjoint location is accepted (assumption: the backlog's "symlinked roots are refused"
  means "overlapping through a symlink"; refusing every symlink could break dotfile setups).
- The watchdog does not know the knowledge dir; the resumed `ai-pipeline` checks it before
  any agent. Recovery's own Claude decision is read-only with no `--add-dir`.
- Git worktrees: the shared `.git` common dir is not checked (out of scope).

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; the gate takes ~5 min).
