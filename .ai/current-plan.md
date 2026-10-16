# Plan: Flow batch 4: FL-27, FL-25, FL-26, FL-12, CU-2

## Assessment (verified at 7d22939, 2026-10-16)
Open: FL-27, FL-25 (a and b), FL-26, FL-12, CU-2. Already done and dropped: FL-21 (5-minute
stall confirmation in the watchdog), CU-4 (colour variables stripped for batches, ANSI-tolerant
summary), CU-1 (attempts credited to their own model), CU-3 (re-check severity totals).
Evidence and line references: `.ai/project-spec.md` → "Verified against the code".

## Architecture
Small, local changes; no new runtime dependency, no new executable, no daemon.
1. **Process ownership in the self-check (T001, T002; opus: process handling, signals,
   concurrency).** `run_parallel.py main()` calls `enable_subreaper()` (Linux `prctl(36, 1)`
   through `ctypes.CDLL(None, use_errno=True)`; False elsewhere). The Dispatcher gets a
   `reap` flag: `run()` joins its threads with a short timeout in a loop and, under the
   dispatcher lock, reaps adopted zombies (`/proc/<pid>/stat`: ppid == own pid, state `Z`,
   pid not a running batch) with `waitpid(pid, WNOHANG)`. Never `waitpid(-1)`: it would steal
   a batch's exit status (Popen then reports 0). `stop()` additionally walks the `/proc` tree
   below the runner (ppid map; `comm` parsed after the last `)`), SIGTERMs every descendant,
   waits up to `TERMINATE_GRACE` for them to be gone or zombies, re-walks and SIGKILLs
   survivors whose start time still matches, up to a few rounds (forks during the stop).
   ```mermaid
   flowchart LR
     M[main: enable_subreaper] --> D[Dispatcher.run: workers + reap loop]
     D -- worker error / SIGINT / SIGTERM --> S[stop: batch groups + /proc descendant tree]
     S --> T[SIGTERM all, grace]
     T --> K[re-walk, SIGKILL survivors with same start time]
     K --> R[reap adopted zombies, join, re-raise]
   ```
   Tests run the dispatcher in a child Python driver (the flag must never be set on a test
   process) and the real script for SIGTERM/SIGINT, with `timeout 120 sleep 120`.
2. **Record-format tolerance (T003–T006).** A pure helper `workflow.py tasks fill-sections`
   (fence-aware through `queue_segments`, atomic write, TODO tasks only) runs on the host after
   triage, planning and plan-revision sessions, before the reorder / `tasks check` there. The
   two disposition regexes read cells as `(?:\\\||[^|\n])*?` and unescape `\|`; one shared cell
   pattern for both. Prompts and contracts show the task format and the pipe rule.
3. **Scratch files (T007).** Prompt rule plus a host step in `ai-run`'s `claude_session`
   (`rm -rf -- .ai/local/scratch` before and after each `claude` call). No permission change:
   `Bash(rm *)` cannot be limited to untracked or in-checkout paths.
4. **Recovery answer (T008; opus: recovery authority).** `recover_decision` keeps the strict
   path for a whole-text JSON value; otherwise it scans top-level objects with
   `JSONDecoder.raw_decode` (skipping past each decoded object, so nested objects are never
   candidates) and accepts exactly one valid decision. A duplicate key in any candidate
   escalates. Escalation keeps a cleaned excerpt.
5. **Catch-up coverage (T009).** Pure report logic in `outcomes_report` plus a `catchup`
   outcome kind written by `ai-status --catch-up-done BRANCH...`.

## Phases / tasks
Priority order (the most valuable lands first if the night runs short):
T001 (subreaper + reaping, opus) → T002 (stop kills the descendant tree, opus) → T003
(`tasks fill-sections`, sonnet) → T004 (host runs it after sessions, sonnet; flow chart) → T005
(escaped pipes, sonnet) → T006 (FL-25 prompt wording, haiku) → T007 (scratch dir, sonnet; flow
chart) → T008 (recovery decision, opus; flow chart if it describes the answer) → T009 (CU-2,
sonnet) → T010 (docs/handoff audit, haiku).
Dependencies: T002 needs T001; T004 needs T003; T006 needs T004 and T005 (it describes them);
T010 needs all. T001/T002 first because the gate itself runs `tests/run_parallel.py`: a
regression there shows up at once in every later gate run.
The handoff's "## Flow chart" line reads `Flow unchanged so far` until T004 switches it to
`Flow chart updated` (`test_pr_body_flow_this_repo_declares_the_flow_chart` needs one of them).

## Risks
- The gate runs the changed runner (T001/T002). A reaper that steals a batch's status would
  turn failures into passes: T001 asserts a failing batch still fails with the subreaper on.
- Subreaper adoption keeps orphaned fixture processes as the runner's children during a normal
  run; they are reaped when they exit and, as before, reparent to init when the runner exits.
  Normal runs do not kill leftovers (unchanged behaviour).
- PID reuse during a stop: start-time check before SIGKILL; zombies are not reaped until the
  kill rounds end, so adopted PIDs cannot be reused meanwhile.
- `test_recovery_decision_parsing_is_strict` changes on purpose (`Decision: {…}` → rerun);
  named in T008's result. Accepting prose widens what counts as a decision: guarded by
  "exactly one valid object" and duplicate-key escalation.
- Filling `### Likely affected modules` with `(not listed)` hides a planner omission; the host
  prints which tasks it filled, so the log shows it.
- Installed copies (`.ai/bin`, `.ai/prompts` here and in other projects) keep the old
  behaviour until the human runs `setup-project --upgrade` (handoff).

## Validation strategy
Each task: its targeted `-k` tests, then `.ai/bin/ai-check` (parallel; gate note in
`.ai/tasks.md`). All tests offline (mock agents, generated suites, real `/proc` on Linux with
skips elsewhere).

## Assumptions (unattended run; recorded instead of asked)
- FL-27 uses `PR_SET_CHILD_SUBREAPER` plus a `/proc` walk, not cgroups (no systemd/root
  dependency); non-Linux keeps the T014 behaviour.
- FL-25 repairs only the two content-free sections, only in TODO tasks, only on the host paths
  right after a session; an interrupted triage whose committed queue lacks them still stops
  (rare after this fix; recorded limitation).
- FL-25 (b): escaped pipes are accepted, unescaped pipes still split (a row cannot be
  repaired without guessing).
- FL-26: no permission change; the host clears `.ai/local/scratch` (gitignored, so the tier-1
  `git add --all` never stages it).
- FL-12: prose around one decision is accepted; no `--json-schema` (the CLI flag and the mock
  would both change; not verifiable offline).
- CU-2: a later Codex review of the same project and branch covers earlier Claude reviews of
  the same family; a catch-up on another branch needs the explicit `--catch-up-done` record.
- Sessions may edit the vault flow chart and append a hub Log line; if denied, the task
  records it and the handoff lists the pending change.
