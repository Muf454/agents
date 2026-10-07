<!-- Plan review of plan digest 9b98f99813ca9271a2e965f94138c745a5146ee84a86908c463a6e1fe6845636; saved 2026-10-07T11:12:45Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=7 MINOR=3

Reviewed HEAD: `16ada6fa394134cd048c3a104f0776a850ff2429`

Inspected repository instructions, spec, plan, tasks, state/handoff, affected scripts, parsing/install helpers, watchdog behavior, relevant tests, documentation, vault flow chart, and Git history. No files modified; no network or MCP integrations invoked.

## BLOCKER findings

None.

## MAJOR findings

- P1: Preserve the underlying workflow stage when recording pauses, recovery, and stops.

  **Location:** `.ai/tasks.md:28`, `.ai/tasks.md:38`, `.ai/tasks.md:45`, `.ai/tasks.md:175`.

  A pause replaces the stage with `paused` and records only the provider/reset time. A fresh dashboard cannot determine which box should contain ⏸. Recovery also replaces the stage, but the renderer specifies underlying-stage parsing only for `stopped`.

  Stop details have another mismatch: existing callers use `implementation`, `validation`, `plan review`, `re-check`, and `pull request`, whereas box keys use `build`, `checks`, `plan_review`, `recheck`, and `pr`.

  **Concrete plan change:** Define a canonical underlying-stage field or equivalent explicit encoding for every overlay. Preserve the previous detail and stage start time through pauses; normalize existing stop labels. Require writer-to-renderer tests for paused build/review, recovery, and actual stop callers, rather than fixtures containing only idealized stage keys.

- P2: Record Checks where validation actually runs.

  **Location:** `.ai/tasks.md:41`, `.ai/tasks.md:50`; `scripts/ai-run:257`, `scripts/ai-run:292`; `scripts/ai-pipeline:190`.

  The planned Checks writer covers `ensure_validated()`. Normal post-task and final validation run directly inside `ai-run`. Their passing stamp generally causes `ensure_validated()` to skip its check. Consequently, the dashboard would show Build during those long checks, and the expected normal-run stage sequence can omit Checks entirely.

  **Concrete plan change:** Instrument the direct host validation calls in `ai-run`, with an explicit transition back to Build when the next task starts. Define the intended display during recovery validation too. Capture observations from the mock validator and assert Checks during ordinary post-task and final gates.

- P3: Retain the watchdog’s process-identity checks and support markerless legacy runners.

  **Location:** `.ai/tasks.md:105–117`; `scripts/lib/watchdog.py:90–111`; `tests/test_workflow.py:505`.

  The proposed liveness check accepts any runner at the marker PID. The watchdog additionally checks process start time, restricts marker ownership to pipeline/recovery processes, and rereads the marker to avoid reporting a completed run as crashed.

  Discovery also finds live processes whose checkout has no marker, but inspection derives `alive` exclusively from the marker. Historical `ai-pipeline` versions before commit `3e79177` lack that marker, so they would appear idle despite running.

  **Concrete plan change:** Carry discovered process identities into inspection. Use live checkout runners when no marker exists, while retaining genuine dead-pipeline detection even when an orphaned child remains. Require PID-reuse, finish-during-snapshot, orphan-child, and markerless-legacy regressions.

- P4: Coordinate concurrent notification writes and registry pruning.

  **Location:** `.ai/tasks.md:34–37`, `.ai/tasks.md:56–59`; `scripts/lib/watchdog.py:463`.

  Notification append followed by tail-and-rename loses messages under concurrent writers: writer A snapshots the tail, writer B appends, then A replaces the log with its older snapshot. The watchdog and pipeline have separate locks, so their writes can overlap.

  Shared registry pruning has a similar read/delete race: one process can inspect an entry, another can replace it with a valid registration, and the first can delete that replacement.

  **Concrete plan change:** Specify writer coordination for append plus trimming, and race-safe registry pruning. Dashboard reads must remain lock-free. Add deterministic interleaving tests that retain recent messages and newly replaced valid registrations.

- P5: The new notification append must not follow unsafe output paths.

  **Location:** `.ai/tasks.md:34–37`; `scripts/lib/watchdog.py:332–346`, `scripts/lib/watchdog.py:463`.

  Appending directly to an agent-writable `notifications.log` follows a preplanted symlink and can modify an unrelated file or protected workflow file. The watchdog invokes `ai_notify` without `ai_root()`’s full path validation, and its output-path checks currently omit this new destination. Sanitizing dashboard text does not address this writer-side risk.

  **Concrete plan change:** Specify rejection of symlink/nonregular log destinations and no-follow append behavior, with failures remaining nonfatal. Add a sentinel-file test through the watchdog notification path: an unsafe destination must leave the sentinel unchanged and preserve the original workflow outcome.

- P6: T001’s model and size do not fit its concurrency risk.

  **Location:** `.ai/tasks.md:20`, `.ai/tasks.md:65`; `.ai/current-plan.md:18`.

  T001 assigns `sonnet` to concurrent notification retention and shared registry mutation. The requested model-routing rule requires `opus` for concurrency/locking work. It also combines five runtime modules, integration tests, and a vault update in one task, exceeding the requested “few files” checkpoint size.

  **Concrete plan change:** Split T001 into smaller tasks. Assign `opus` to concurrent writer/path-safety work; retain cheaper models for routine stage hooks and documentation. Update dependencies and acceptance criteria accordingly.

- P7: The default age filter unintentionally hides crashed runs.

  **Location:** `.ai/tasks.md:120–122`; `.ai/project-spec.md:56`.

  The spec hides old finished, stopped, and idle runs. The task instead hides every non-alive entry older than 24 hours, which includes `crashed`. An unresolved crash would therefore disappear from the normal dashboard.

  **Concrete plan change:** Enumerate the statuses eligible for age filtering and retain crashed runs by default. Add an old-crash fixture alongside old finished/stopped/idle fixtures, checking both default output and `--all`.

## MINOR findings

- P8: Make bytecode suppression explicit and test the executable’s own directory.

  **Location:** `.ai/tasks.md:102–104`, `.ai/tasks.md:149–150`; `scripts/lib/watchdog.py:18–21`.

  Normal sibling imports can create `__pycache__` in the toolkit or installed `.ai/bin/lib`, violating the strict read-only requirement and potentially changing the approved gate digest. The watchdog explicitly disables bytecode before importing workflow; the new task should require that same ordering. Comparing only fixture checkouts and their state root can miss writes into the source executable’s directory.

  **Concrete plan change:** Require bytecode suppression before sibling imports. Run fresh source and installed entry points, comparing their directories as well as observed checkouts and host state.

- P9: Isolate registry failure from the existing mandatory manifest failure.

  **Location:** `.ai/tasks.md:81–82`; `scripts/ai-pipeline:109`; `scripts/lib/workflow.py:824–830`.

  Making the entire state root unwritable also prevents the existing required run manifest from being written. The pipeline already stops in that situation, so this fixture cannot demonstrate that registry failure is harmless.

  **Concrete plan change:** Keep manifest storage writable and fail only the `pipelines/` destination or registration helper. Assert a warning and unchanged outcome, without weakening existing manifest requirements.

- P10: Test the documented symlink installation.

  **Location:** `.ai/tasks.md:126–128`, `.ai/tasks.md:236`; `scripts/lib/common.sh:4`.

  The suggested `~/.local/bin/ai-dashboard` symlink does not work with the shown wrapper pattern: deriving sibling paths from the invoked symlink locates `lib/` under `~/.local/bin`, rather than beside the toolkit script.

  **Concrete plan change:** Resolve the wrapper’s actual file location before locating its library, or document a launcher that uses the absolute script path. Add a symlink invocation test from outside a checkout.

## Validation observed

- Requested HEAD confirmed; working tree clean.
- Planning diff whitespace check and task-queue validation passed.
- Python syntax: **3 files passed**.
- Bash syntax: **13 files passed**.
- Documentation consistency: **3 tests passed**.
- A read-only process probe confirmed that `is_runner()` alone accepts a process the existing watchdog rejects for an older marker timestamp.
- Git history confirmed a legacy pipeline version without `pipeline.active`.
- Validation-stamp verification failed: **no validation evidence exists in this checkout**.

The full `./scripts/ai-check`, `.ai/bin/ai-check`, and writable integration fixtures were not run because they create files, locks, repositories, and validation artifacts. Prior review evidence belongs to earlier revisions and does not validate this plan.

## Missing test coverage

Add the writer-to-renderer, normal-validation, process-identity, concurrent-writer, unsafe-path, old-crash, read-only-import, registry-failure, and symlink cases described above. Run the targeted checks and required full gate after implementation.

## Security concerns

Advisory observations and read-only dashboard behavior are appropriate boundaries. P5 concerns newly introduced host writes through unsafe paths; P8 concerns unintended interpreter writes. No authorization changes are needed to implement the dashboard.

## Architecture concerns

The stdlib-only snapshot/TUI approach fits the spec. Preserve existing pipeline/watchdog lifecycle semantics, and define shared observation semantics before implementing writers and rendering independently.

## Manual testing recommendations

### Needs you

After automated checks pass, inspect two simultaneous tmux runs through build, checks, pause/recovery, stop, and finish. Verify selection, expansion, scrolling, resize, colors, and terminal restoration.

### Covered by automated tests

The planned snapshot/render fixtures and pty smoke test should cover deterministic behavior, supplemented by the regressions above.

This review assesses the plan; it does not establish implementation correctness or human acceptance.