<!-- Host evidence: HEAD be83ab5d4cfd5e36d69d08cfb5f0c2211eb0d4a1; merge-base ba330ef04b94ee86ea8ecf3a4e8dc3ace0e6c200; saved 2026-10-08T07:17:02Z. -->

# Independent review

Overall verdict: PROCEED WITH MINOR FIX — the requested reviewer restriction and stopped-attempt accounting are substantially delivered, with one localized malformed-queue gap.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=1

Reviewed HEAD: `be83ab5d4cfd5e36d69d08cfb5f0c2211eb0d4a1`  
Supplied base and merge-base: `ba330ef04b94ee86ea8ecf3a4e8dc3ace0e6c200`

Inspected AGENTS.md, specification, plan, tasks, state, handoff, previous reviews/dispositions, relevant documentation, scoped Git history/diff, affected source/tests, validation evidence, and the vault flow chart. The checkout was clean.

## Validation observed/run

- Stored validation reports **PASS**, exit 0, at `2026-10-08T07:13:02Z`, against `db4f729f1b89c5139b966c40c3b4354ed888c8a6`. Its log reports **287 tests in 126.6 seconds**, eight shards, **OK**.
- Independently verified the validation fingerprint against HEAD, committed content against the worktree, and task-queue completion. Only runner bookkeeping changed after the recorded validation.
- Discovery collected **287 tests**. Independently ran **three documentation consistency tests**, all passing.
- **12 Bash syntax checks** and **four Python syntax parses** passed. `git diff --check` passed.
- Read-only, in-memory probes confirmed the fixed reviewer allowlist and EXIT-handler classification for session exits 124/137, runner exits 130/143, ordinary errors, and unopened attempts.
- An in-memory probe of the actual outcome helper demonstrated N7 below.

Limitations: Did not rerun `./scripts/ai-check` or writing integration tests because this sandbox forbids their fixtures and validation writes. No live Claude permission-engine check, installation, network/MCP integration, or external operation was invoked. No files were written.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

## MINOR findings

### N7 — An undecodable task queue still prevents stopped-attempt logging

**Requirement:** T002 requires `outcome task` to log even when `.ai/tasks.md` no longer parses, using a tolerant title fallback or an empty title.

**Location:** `scripts/lib/workflow.py:2033`, `scripts/lib/workflow.py:2037`; outcome caller at `scripts/lib/workflow.py:2055`.

**Problem:** The initial title lookup catches `ValueError`, which includes `UnicodeDecodeError`. The fallback then rereads the same file but catches only `OSError`. If a session leaves invalid UTF-8 in the queue, the second decoding failure escapes before the outcome is appended.

**Evidence:** Patched `Path.read_text` in memory to raise the decoding error produced by byte `0x96`, then called the actual `outcome_title('T001')` and `outcome(['task', 'T001', 'error', 'sonnet', '5'])`. Both propagated `UnicodeDecodeError`; the outcome helper never opened the append sink. The normal malformed-Markdown case correctly returned its heading.

**Impact:** This corruption case still loses the failed attempt. After queue repair, a successful retry can be reported as attempt 1 with `first_pass=true`. The runner reports the failed append but closes its attempt, so it does not retry logging.

**Recommended direction:** Catch decoding failures in the fallback and return an empty title, or retain task metadata captured before the session. Add a regression that corrupts the queue’s encoding, repairs it, and verifies outcomes `error` then `done`, numbered 1 and 2.

## Missing coverage

- Invalid task-file encoding, including recovery and attempt numbering.
- An implementation-session usage-limit wait exceeding `AI_LIMIT_MAX_WAIT`, asserting one `error` outcome. The new limit-pause test covers successful retry; the new limit-exhaustion case exercises triage, which intentionally logs no task outcome.
- Live Claude tool enforcement remains pending. The mock tests inspect invocation arguments and host behavior; they do not enforce the provider’s permissions.

## Security concerns

No additional exploitable defect was demonstrated in the inspected changes.

The reviewer invocation removes Bash, Edit, and Write and ignores the project implementation allowlist. Host context commands disable external diff and text conversion. Mandatory context steps explicitly check failures before Claude starts, and the checkout-change rejection remains.

Read access remains broader than the checkout; checkout-only instructions are a prompt policy, not filesystem isolation. This limitation is acknowledged in the documentation.

## Architecture concerns

The implementation adds no dependency and reuses existing review binding, publication, and outcome machinery. Context is prepared per mode, rebuilt after usage-limit retries, and removed after sessions.

Attempt tracking excludes triage and exhausted preflight budgets. Explicit terminal outcomes close the attempt before EXIT handling. The handler avoids project helpers after a protected-gate change.

Crash-durable telemetry was explicitly deferred; missing outcomes after SIGKILL/OOM/power loss are outside this revision’s accepted scope.

**Flow chart updated:** the vault note describes the restricted reviewer and stopped-attempt lifecycle and has `updated: 2026-10-08`. Git history cannot establish the timing of edits to that external note.

Pre-existing defects excluded from these counts: the deferred mixed-model attribution, catch-up-pending reporting, and recheck-severity reporting issues remain outside this fix’s scope.

## Manual testing recommendations

### Needs you

- Perform the planned live Claude fallback review in a disposable project. Confirm the available tools, context reads, cleanup, and saved review binding.
- Approve installed-copy upgrades separately after review and acceptance.

### Covered by automated tests

- Existing regressions cover code/plan/recheck context, review delta, preparation failure, retry cleanup, reviewer arguments, timeout/error numbering, validation failure, signals, malformed Markdown, triage exclusion, and limit pauses. Their stored full-suite result is PASS.
- Add the N7 encoding-corruption regression and implementation limit-exhaustion assertion, then run `./scripts/ai-check` in a writable checkout.

This review does not constitute human acceptance.