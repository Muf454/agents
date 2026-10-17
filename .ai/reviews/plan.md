<!-- Plan review of plan digest 1523cdac4a49f5e31ce3aec581fcab9762e56f9b987d59de0be8bd0181273523; HEAD b018ef0fe925529b881b012e1989ccd2a82148b7; saved 2026-10-17T02:01:58Z. -->

# Plan review — round 4

Overall verdict: REVISE BEFORE IMPLEMENTATION
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `b018ef0fe925529b881b012e1989ccd2a82148b7`

The revised tasks address P1–P11, including round 3’s sync confirmation, strict log reads and startup ordering. Two additional marker failure paths remain insufficiently specified.

## BLOCKER findings

None.

## MAJOR findings

- P12: Transient marker read failures permanently discard recoverable attempts.

  **Location:** `.ai/tasks.md:233`, `.ai/tasks.md:365`.

  T008 makes `list_markers()` return `None` for both unreadable and invalid markers. T003 then unlinks either kind. A single `OSError(EIO)` while reading an otherwise valid marker therefore deletes the only durable evidence of an unrecorded attempt, without appending its outcome. The strict-read protection added for P10 covers the outcome log, but leaves this equivalent marker-side failure intact.

  **Concrete plan change:** Distinguish read errors from successfully read, malformed content. Keep markers on read errors, warn, and continue processing other markers. Add a regression where one marker read fails transiently: the marker remains unchanged, nothing is appended for it, and a later successful reconciliation records exactly one crash.

- P13: A marker publication failure can lose its ID and later turn a successful task into a reported crash.

  **Location:** `.ai/tasks.md:231`, `.ai/tasks.md:350`, `.ai/tasks.md:479`.

  Marker creation links `<id>.json` before syncing its directory. If that sync fails, the marker already exists, but the runner’s prescribed `attempt-open … || attempt_id=` clears its ID. Implementation continues because telemetry is best effort. A successful task then logs `done` without `attempt_id`, leaving the published marker behind. Subsequent reconciliation cannot associate that outcome with the marker and appends `crashed`. Since the existing report uses the last outcome per task (`scripts/lib/workflow.py:3093`), it can report the completed task as not done.

  **Concrete plan change:** Specify a publication-failure contract that preserves the chosen ID in the runner even when registration fails after linking. Carry that ID into the normal outcome and marker cleanup. Add a regression injecting an attempts-directory sync failure immediately after publication, followed by successful task completion and reconciliation; require one outcome for the attempt and no false crash.

## MINOR findings

- P14: T008’s acceptance criteria require functionality implemented by its downstream dependency.

  **Location:** `.ai/tasks.md:253`, `.ai/tasks.md:335`.

  T008 requires checking that `outcome task … --attempt` retains its marker after a directory-sync failure. T003 introduces that interface and depends on T009, which depends on T008. Consequently, T008 cannot satisfy all its acceptance criteria at its own checkpoint.

  **Concrete plan change:** Keep the append failure assertion in T008 and move the marker-retention assertion explicitly into T003’s acceptance criteria.

## Validation and scope

Inspected the spec, plan, all nine tasks, dispositions, state, handoff, relevant documentation, source, templates, existing tests and `.ai/validate`.

Observed passing checks:

- `python3 -B scripts/lib/workflow.py tasks check`
- Three `DocsConsistencyTest` tests
- Shell syntax checks for five relevant files
- Python syntax parsing for the helper and relevant test files

The full gate and integration tests were not run because they create writable fixtures and validation artifacts. The planned implementation is absent, so these checks validate the current baseline only.

No files were modified. No network or MCP integrations were invoked. The remaining findings concern telemetry integrity; no additional authorization issue was identified in the inspected scope.