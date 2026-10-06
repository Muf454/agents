# Review dispositions (Claude)

Review HEAD: 86912702b4c62e535c57fe98176b0f2689855dc5

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Confirmed in `scripts/lib/workflow.py:1627-1629`: the gitlink branch runs before the symlink/file checks and hashes the constant `uninitialised` without looking inside; `git ls-files --others` lists nothing under a gitlink path, so files created/overwritten there or a symlink replacing it leave the snapshot unchanged. `test_deps_status_tree_snapshot_covers_submodules` only covers initialised submodules. Breaks FL-01's preservation check. | T008 |
| N1 | accepted | Confirmed at `scripts/lib/workflow.py:1896`: the check looks for any backtick on the bullet's first physical line only, so bullets in `.ai/handoff.md` whose test name is on an indented continuation line (e.g. "Dependency freshness …" bullet) are falsely flagged, and a lone backtick passes. Cheap and in scope (FL-09); P12 FINISHED-count regression folded in. | T010 |
| N2 | accepted | Confirmed at `scripts/lib/workflow.py:1588`: `(root / token).exists()` accepts a regular file (or symlink to a file) as the declared output directory, so `deps-status` reports `current` and setup is skipped. Cheap and in scope (FL-01). | T009 |
