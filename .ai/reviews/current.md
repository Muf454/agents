<!-- Host evidence: HEAD 68ac201c132afc084763bebc3d4e3cb8219f0964; merge-base 4fea72d51a543528c79a0afab423b935757d6acf; saved 2026-10-23T03:58:00Z. -->

# Independent review

Overall verdict: REQUEST CHANGES — two MAJOR stop-path defects and one MINOR status-reporting gap.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `68ac201c132afc084763bebc3d4e3cb8219f0964`

Supplied base and verified merge-base: `4fea72d51a543528c79a0afab423b935757d6acf`

## Scope and validation

Inspected repository instructions, specification, plan, relevant task records, state, handoff, review dispositions, documentation, Git history, the supplied diff, affected source and relevant tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json` records PASS at `2026-10-23T03:48:18Z`, on revision `0b5e32a498a9a24004fed22aa19eacaad41c8b68`.
- Its referenced log reports **1,222 tests passed** in 955.7 seconds.
- Independent `stamp verify` confirms that the evidence matches the reviewed checkout.

Checks independently completed:

- Task queue validation and `git diff --check` passed.
- Python AST checks across nine files and shell syntax checks across 14 files passed.
- All four documentation-consistency tests passed.
- Read-only discovery found 1,222 tests; the temporary-directory initializer was suppressed for discovery.
- Write-free reproductions exercised the three findings below.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because this review uses a read-only sandbox. No project files were written or network/MCP integrations invoked.

The existing review artifact concerns an earlier batch. Code inspection confirms its accepted findings M3, N2 and N3 are addressed. No pre-existing defects are counted below.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M4 — Cancelling a scheduled relaunch leaves the watchdog launching recovery

**Requirement:** FR-4 requires the watchdog never to start recovery for a human-stopped run. FR-5 and T319 require stopping a paused run to cancel its scheduled relaunch.

**Location:** `scripts/lib/watchdog.py:516` and `scripts/lib/watchdog.py:530`.

**Problem:** The scheduled-relaunch path calls `start_recovery()` before checking the run record. The new human-stop check runs only when a dead pipeline marker exists. Stopping a paused run removes that marker but leaves `run.json`’s `limit_relaunch_at`.

The launched recovery refuses the stopped record before reaching `limit-claim`, so the due schedule remains available to every later watchdog probe.

**Impact:** A cancelled run continues spawning recovery processes. A quiet refusal also leaves the watchdog without its expected acknowledgement, producing a misleading “usage-limit relaunch could not start” alert. The recovery correctly refuses to resume agent work, but cancellation does not suppress the recovery launches.

**Evidence:** A write-free execution of the actual watchdog `main()`, with filesystem and launch effects mocked, supplied a current `human_stop` record, no pipeline marker and a due schedule. Two probes called `start_recovery()` twice and never called `current_run()`. The existing cancellation test invokes `ai-recover` directly; it does not exercise the watchdog’s scheduled path.

**Recommended direction:** Check the current run’s stop/terminal state before scheduled recovery. Ensure cancellation prevents subsequent probes from launching recovery, with a regression that runs multiple watchdog probes after cancelling a paused run.

### M5 — Shutdown reports success while its tracked publication child remains alive

**Requirement:** FR-2 and FR-3 require shutdown to end the running child. FR-5 provides exit 4 for a run still ending, rather than reporting a completed stop.

**Location:** `scripts/lib/common.sh:178`, `scripts/lib/common.sh:206` and `scripts/lib/common.sh:229`.

**Problem:** When `ai_stop_child()` exhausts its 30-second wait, `ai_human_stop()` sets `child=running` but continues to end the run as `human_stop`, announce “STOPPED by you,” remove the marker and exit. That flag only prevents the bookkeeping commit.

Publication commands run directly through `ai_run_child`, without a timeout wrapper. A tracked `git` or `gh` process that survives TERM can therefore continue after the owner exits. Its inherited checkout lock can remain held. Subsequent `--stop` calls refuse the already-ended record.

**Impact:** Publication can continue after the human is told it stopped, while the normal stop command can no longer reach it. This concerns the tracked publication process itself; B21’s documented push-hook limitation does not cover it.

**Evidence:** A write-free reproduction used the actual shutdown functions and a real TERM-ignoring fixture process. Polling delays were accelerated, bookkeeping was mocked and local output redirected to `/dev/null`. The handler exited 143 after issuing `run-record end … human_stop`, announcing the stop and dropping the marker; the tracked child remained alive.

The existing wait-expiry test uses an owner that ignores TERM, so it does not exercise this handler failure.

**Recommended direction:** Preserve a pending stop while a tracked child survives. Keep an owner capable of completing shutdown, report the survivor, and let `--stop --wait` return 4 until termination is confirmed. Add a TERM-ignoring publication-child regression.

## MINOR findings

### N4 — Authorized skipped tasks remain counted as unfinished in persistent state

**Requirement:** FR-9 defines an authorized SKIPPED task as finished for the queue.

**Location:** `scripts/lib/workflow.py:1170`.

**Problem:** `update_state()` calculates `Tasks remaining` as total tasks minus DONE tasks. It does not exclude authorized SKIPPED tasks.

**Impact:** A fully finished queue can reach `ready_for_review` while its persistent state still reports remaining work, misleading humans and app consumers.

**Evidence:** With one DONE task and one authorized SKIPPED task, the actual `tasks complete` action succeeded. The actual state updater nevertheless produced:

```text
Tasks complete: 1
Tasks remaining: 1
```

**Recommended direction:** Calculate remaining work from statuses outside `FINISHED`. Keep completed and skipped counts distinguishable where displayed, and cover mixed DONE/SKIPPED queues.

## Missing coverage

Add regressions for:

- Repeated watchdog probes after cancelling a scheduled usage-limit relaunch.
- A real shutdown handler whose tracked publication child survives TERM.
- Persistent state for a complete queue containing authorized SKIPPED tasks.

Nearby tests cover direct recovery refusal, an unresponsive owner and skip eligibility, but miss these integrations.

## Security concerns

M5 can leave an already-started publication command executing after shutdown is reported. No additional demonstrated exploitable defect was found in the inspected gate handling, record I/O or task authorization.

## Architecture concerns

The implementation retains minimal dependencies and generally follows the host-record and run-ID locking design. Stop decisions need consistent enforcement across scheduled recovery and shutdown completion.

**Flow chart updated:** the inspected vault note has `updated: 2026-10-23` and documents human stop, escalation, SKIPPED and detach. Corresponding hub log entries exist; same-session edit timing was not independently established.

## Manual testing recommendations

### Needs you

After fixes and installation, verify with the real CLIs and systemd timer:

- Ctrl-C and `--stop` produce accurate notifications and complete shutdown.
- Cancelling a paused run causes no recovery launch when its reset becomes due.
- A detached run survives terminal closure and its printed stop command ends it.

### Covered by automated tests

The recorded suite covers lifecycle records, ordinary signal forwarding, recovery refusal, detach arguments, escalation and task controls. Add the three regressions above and rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.