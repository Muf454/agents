<!-- Host evidence: HEAD 9b01351b48d0be63837370d4e3bba25dd7e442bd; merge-base 55383d7e69c0c7d18afd3665c4220e76d88b994f; saved 2026-10-07T17:33:30Z. -->

# Independent review

Overall verdict: PROCEED WITH MINOR FIXES — the efficiency features are substantially delivered, but reporting, oversized-history handling, acceptance records, and fallback probe permissions need correction.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=4

Reviewed HEAD: `9b01351b48d0be63837370d4e3bba25dd7e442bd`  
Supplied base: `0818f20c4d236072815e24552ba779e058c7e1f0`  
Reviewed merge-base: `55383d7e69c0c7d18afd3665c4220e76d88b994f`

The supplied base and merge-base have identical trees. The checkout was clean. Inspected repository instructions, specification, plan, tasks, state, handoff, prior review evidence, documentation, scoped history/diff, affected source/tests, frozen runtime changes, and the vault flow chart.

## Validation observed/run

- Stored validation reports **PASS**, exit 0, at `2026-10-07T17:26:20Z`, recorded against `f729822bd9f7573cdb3225fef2e6e879432e8390`. Its log records **253 tests in 107.8 seconds**, eight shards, **OK**.
- Independently verified that the validation fingerprint matches HEAD.
- Task-queue checks, queue completion, and committed-content comparison passed.
- Discovery collected **253 tests**; **three documentation consistency tests passed**.
- **18 Bash syntax checks** and **six Python syntax checks** passed.
- In-memory probes exercised the runner with real unittest failure/error, skipped-test, and expected-failure output, using mocked subprocess I/O. Skips and expected failures were accepted correctly.
- Exercised history rendering, historical review extraction, and the frozen reviewer allowlist. Toolkit-owned files match their recorded hashes.
- Scoped `git diff --check` passed; the checkout remained clean.

Limitations: Did not rerun `./scripts/ai-check` or writable integration fixtures because they create repositories, locks, logs, and validation artifacts. Live providers, systemd, installations, and publication were not exercised. No files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

None found in the inspected scope.

The implementation uses one uncapped history routine for review context and convergence counting. Implementation-review prompts retain the full review range; convergence checks require same-line text and exclude HTML comments. Added integration tests cover round-three enforcement and interrupted triage.

## MINOR findings

### P8 — The runner omits required aggregate failure/error counts

**Location:** `tests/run_parallel.py:105`; regression assertion: `tests/test_workflow.py:4147`.

**Requirement:** `.ai/project-spec.md:29` requires an aggregate `FAILED (failures=…, errors=…)` summary.

**Problem:** The final summary reports failing shard numbers without aggregating failure/error totals. The new regression explicitly expects this different format.

**Evidence:** An in-memory probe passed actual unittest output containing one failure and one error through the real parser and aggregation logic. The runner exited 1 and printed both tracebacks, but ended with:

```text
Ran 2 tests in 0.0s (1 shards, 2 collected)
FAILED (failing shards: 1)
```

**Impact:** Failure still closes the gate, but the specified reporting contract is unmet. This remains unresolved from the plan review.

**Recommended direction:** Aggregate ordinary failure/error counts, retain crash and count-mismatch diagnostics, and test mixed failures/errors across shards.

### P9 — Oversized newest rounds silently lose findings and dispositions

**Location:** `scripts/lib/workflow.py:883`.

**Requirement:** `.ai/project-spec.md:45` requires finding IDs, titles, and dispositions, capped by dropping oldest rounds with an omission notice.

**Problem:** When the newest round alone exceeds the cap, the fallback slices raw Markdown at character 6000. It can remove dispositions and later findings without indicating that the retained round is incomplete.

**Evidence:** Calling the actual renderer with one round containing a 6100-character first finding title and a second accepted finding produced exactly 6000 characters. Neither accepted-task disposition nor the second finding survived. The output said `(0 earlier rounds omitted)` and contained no truncation notice.

**Impact:** Review and triage receive incomplete context that appears complete. Uncapped round counting remains correct.

**Recommended direction:** Provide an explicit oversized-round fallback with an original-report reference, or shorten titles while preserving IDs and dispositions. Add a single oversized newest-round regression.

### P10 — Final guidance contradicts the gate and lacks qualifying timing evidence

**Location:** `.ai/handoff.md:14`, `.ai/handoff.md:48`, `README.md:614`; evidence: `.ai/run-log.md:90`.

**Requirement:** T005 requires accurate final documentation. `.ai/project-spec.md:78` requires three consecutive parallel runs with matching serial counts, each under 200 seconds, with counts and times recorded.

**Problem:** The handoff says the gate remains serial and asks the human to approve/apply the switch. README likewise calls serial discovery today’s gate. Commit `becd1bf` already switched `.ai/validate`, recording coordinator approval.

The records do not demonstrate the specified three consecutive matching-count runs. They report successful parallel runs over different suite sizes, followed by the final 253-test validation.

**Impact:** The operating instructions are stale, and the performance acceptance evidence is incomplete. The approval record means the switch is not being classified as an unauthorized action.

**Recommended direction:** Reconcile the spec, plan, README, and handoff with the coordinator exception. Record qualifying repeated measurements and the serial comparison, or explicitly record any approved waiver.

### N4 — The fallback reviewer cannot create its promised scratch probes

**Location:** `.ai/bin/lib/workflow.py:695`; caller: `.ai/bin/ai-review:86`.

**Requirement:** The newly imported `.ai/prompts/claude-review.md:17` permits scenario probe files under `.ai/local/review-probes/`.

**Problem:** The generated allowlist grants directory-scoped `Edit`, but no directory-scoped `Write`. The host deletes and recreates an empty probe directory before every review. Creating a new probe therefore lacks an approved tool.

**Evidence:** Executing the actual allowlist helper produced `Edit(./.ai/local/review-probes/**)` and no `Write` entry. The CLI exposes Write but uses `dontAsk` with that allowlist. This is a source-traced permission gap; live enforcement was not exercised.

**Impact:** Fallback reviewers cannot use the promised file-based scenario probes through the intended tools.

**Recommended direction:** Add narrowly scoped Write permission through the coordinating toolkit update. Test probe creation and denial of writes outside the directory.

## Missing test coverage

- Required aggregate runner failure/error totals.
- A newest round that alone exceeds the history cap.
- Final documentation assertions against the actual gate.
- Fallback probe creation and permission boundaries. The integration harness installs `scripts/`; its passing results do not establish the newly imported frozen fallback behavior.
- Recorded three-run timing evidence and comparison with the final serial suite.

## Security concerns

No additional exploitable security defect was demonstrated in the inspected paths. History does not replace host-owned fix-round accounting or authorize bypasses. The fallback permission finding concerns missing intended access.

## Architecture concerns

The efficiency implementation adds no external dependency and reuses existing helpers. Frozen runtime adoption remains a separate coordinating operation.

Flow chart updated: the vault note includes review context and convergence behavior, with `updated: 2026-10-07`. Same-task edit timing cannot be established from repository history.

Known pre-existing issues remain outside the new finding counts: paragraph-break coverage warnings and the workflow guide’s statement that setup installs nothing. Their relevant source/documentation predates this reviewed range.

## Manual testing recommendations

### Needs you

- Smoke-test the corrected fallback permissions with the real Claude CLI.
- Inspect representative convergence decisions to confirm that repeated concerns produce a design task.
- Confirm that final acceptance records accurately describe the already approved gate switch.

### Covered by automated tests

- Add the summary, oversized-history, documentation, and allowlist regressions above.
- Run `./scripts/ai-check` in a writable checkout after fixes.
- Record three consecutive default-worker runs under 200 seconds and compare their counts with a serial run of the same revision.

This review does not constitute human acceptance.