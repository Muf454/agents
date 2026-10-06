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

## Approach (revised after Codex plan reviews 1 (P1–P4) and 2 (P2, P4–P6))
1. T001 (opus) OR-01 in `ai-run`: after the bookkeeping commit of a DONE task, and after
   the final handoff commit, require clean tree + `stamp verify` + `committed-matches-worktree`
   (same triple as tier-1), else `ai_die "The checkpoint of $T differs from the validated
   content: <helper detail>"`. Tier-1 keeps its own earlier check. Tests include a mismatch
   introduced only by the final handoff commit (filter on the `^Phase: ready_for_review$`
   line only; ordinary checkpoints must pass first) and a mode case with
   `core.filemode=false` (clean at the check; afterwards only `.ai/run-log.md` dirty;
   HEAD/disk mode mismatch).
2. T002 (opus) OR-01 in `ai-pipeline`: a committed-bytes check before each
   `ai-review --base` (after `ensure_validated`; stop stage `review`) and a new
   `publish_ready` clause after the clean-tree check (before "review current"). `push()`
   runs `publish_ready` after every push outcome, before the retry wait and before the
   terminal "3 tries" failure (today the third failure stops without re-checking). Tests:
   hook mismatch on a failed push, a successful push, and the third of three failed pushes
   (integrity reason, commits/queue preserved, no further retry, no recovery Claude, no PR
   action, no FINISHED).
3. T003 (opus) OR-02 core: `state_root()` + `overlap(a, b)` + `check_state_root(checkout,
   knowledge=None)` (explicit checkout, P1) in workflow.py; `binding_dir()` enforces
   relative/checkout rules; helper `state-root-check [--checkout PATH] [KNOWLEDGE_DIR]`;
   called by ai-run and ai-pipeline right after `ai_root` (before any agent); ai-pipeline
   resolves `--knowledge-dir` at parsing and records the resolved path.
4. T004 (opus) OR-02 in ai-recover (P3): check after `escalate()`/`branch`/`reason` setup,
   before the first `run-manifest` read; the configuration error goes into the persisted
   stop reason; tests assert no recovery Claude call, no commit, budget unchanged.
5. T005 (opus) OR-02 watchdog: install-time refusal checked against the supplied project
   root (P1; tests from outside Git and from another checkout), host copy and state root;
   runtime refusal in `start_recovery` before gate/manifest reads with the error in the
   notification, no `systemd-run` (P3).
6. T006 (sonnet) final docs audit: README, docs/workflow.md, audit of the vault chart,
   hub Log line, handoff flow-chart line and manual steps; `docs_consistency` sentences.

Flow chart: T001–T005 each update the vault `agents-flow.md` (diagram/notes and the
`updated:` date) in the same task as their behaviour change (AGENTS.md/CLAUDE.md rule;
each task runs in a fresh session). T006 only audits and consolidates.

Dependencies: T001 → T002; T003 → T004, T005; T006 after T002, T004, T005. T001 and T003
are independent.

## API / data changes
- New helper command `state-root-check [--checkout PATH] [KNOWLEDGE_DIR]` (silent on success; an `Error:`
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
- `ai-watchdog --install-timer` runs `timer()` before `chdir(root)`; any check that
  discovered the checkout from the current directory would test the caller's repo (plan
  review P1), hence the explicit checkout argument.
- Git worktrees: the shared `.git` common dir is not checked (out of scope).

## Validation
Each task names its `-k` test pattern (must report `Ran N tests`, N ≥ 1), then
`.ai/bin/ai-check` in the foreground (600000 ms Bash timeout; the gate takes ~5 min).
