<!-- Host evidence: HEAD e96e1cedfd45b4e0591f21f01d50fcea897e548a; merge-base 20fe2ab452cdd7917af6c11e715fbff0ad6b4489; saved 2026-10-21T06:07:02Z. -->

# Independent review

Overall verdict: REQUEST CHANGES — two MAJOR requirement gaps and one MINOR model-selection issue.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=1

Reviewed HEAD: `e96e1cedfd45b4e0591f21f01d50fcea897e548a`

Supplied base and verified merge-base: `20fe2ab452cdd7917af6c11e715fbff0ad6b4489`

## Scope and validation

Inspected AGENTS.md, specification, plan, relevant tasks, state, handoff, existing review, documentation, Git history, the full supplied diff, and affected source/tests. The checkout was clean.

Validation observed:

- `.ai/local/validation.json` records PASS at `2026-10-21T05:59:47Z`, on revision `30cd4eb430d1693604d78e320f09918079d6d86a`.
- Its referenced log reports **1,098 tests passed in 772.6 seconds**.
- Independent `stamp verify` confirms that evidence matches the reviewed checkout.

Checks independently run:

- Discovered 1,098 tests.
- Three documentation-consistency tests passed.
- Python AST checks across nine files and shell syntax checks across 14 files passed.
- Task queue validation and `git diff --check` passed.
- Write-free reproductions confirmed the three findings below.

The full `./scripts/ai-check` and writable integration fixtures were not rerun because the sandbox is read-only. No project files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — Registry guard captures the already-isolated environment

**Location:** `tests/run_parallel.py:637`, `tests/run_parallel.py:654`; `tests/isolation.py:18`.

**Requirement:** R8/FL-33 and T111 require the parallel runner to check the caller’s real registry and fail when fixture registrations leak there.

**Problem and impact:** `main()` calls `collect()` before capturing `real_registry()`. Discovery imports the test modules, which import `isolation` and replace `AI_STATE_DIR` and `XDG_STATE_HOME`. The later registry capture therefore selects the temporary registry. Leaks into the original host registry escape the intended check.

**Evidence:** A write-free reproduction executed the real isolation code during mocked discovery. With the original registry at `/home/reviewer/host-state/pipelines`, `main()` checked `/tmp/review-isolated-state/pipelines` instead. A simulated leak in the original registry still produced `OK` and exit 0.

**Recommended direction:** Capture the caller’s registry before discovery or any isolation import. Add a regression exercising `main()` across discovery; the existing direct `registry_problem()` test cannot detect this ordering defect.

### M2 — Queue rulings omit tasks moved indirectly

**Location:** `scripts/lib/workflow.py:699`; `scripts/lib/common.sh:365`.

**Requirement:** Assumption A2 requires one queue-order claim **per moved task**, retained across resumes. A repeat must stop without repairing the queue.

**Problem and impact:** Preflight computes every task whose position changes, but emits claimable change lines only for tasks with originally late dependencies. `ai_queue_ruling()` claims only those emitted IDs. Prerequisites and intervening tasks move without consuming their ruling, allowing subsequent repairs to move already-affected tasks again.

**Evidence:** Using the actual preflight helper and shell ruling function:

1. Queue `T001, T002, T003`, with T001 depending on T002, moves both T001 and T002 but claims only `queue-order:T001`.
2. From the resulting queue, adding T003 as T002’s dependency moves all three tasks. The second repair succeeds, claiming only `queue-order:T002`, although T001 and T002 move again.

**Recommended direction:** Claim every ID whose position changes before rewriting. Keep explanatory output separate if only dependency violations should appear in notifications. Add a regression where an indirectly moved task already has a claim and verify refusal with unchanged queue bytes.

## MINOR findings

### N1 — Routed reviews inherit the full-queue fallback model

**Location:** `scripts/ai-review:211`, using the model selection at `scripts/ai-review:73`.

**Requirement:** R6, assumption A12 and T109 specify a fresh Claude **opus** session for small, low-risk fix-round reviews.

**Problem and impact:** Routed reviews use the existing fallback model selector. That selector examines every task, including previously reviewed DONE tasks. An earlier opus task or risky title selects `claude-fable-5-1` even when the current fix round qualifies as low-risk, defeating the specified routed-review model policy.

**Evidence:** With an unchanged, previously reviewed DONE opus task and a one-line low-risk fix, `review_route_reason()` returned `claude small low-risk fix round (1 lines)`. The shell model selector then chose `claude-fable-5-1`.

**Recommended direction:** Default routed reviews explicitly to opus while preserving the human’s model override. Keep full-queue risk selection for fallback reviews and test routing after an earlier opus task.

## Missing coverage

The recorded suite lacks regressions for:

- Registry capture before discovery changes the environment.
- Repeated repairs involving indirectly moved tasks.
- Routed model selection when earlier reviewed work contains opus tasks.

Existing tests cover nearby helpers and happy paths, but their assertions do not detect these failures.

## Security concerns

No additional demonstrated exploitable security or authorization defect was found in the inspected changes. M2 weakens the promised host-controlled repair bound.

No pre-existing defect is counted among these findings.

## Architecture concerns

The changes retain deterministic host decisions and add no dependencies. The registry-check ordering and incomplete ruling claims need correction to preserve the intended boundaries.

**Flow chart updated:** the inspected vault note has `updated: 2026-10-21` and documents preflight, rulings, fresh retries, review routing, limit memory and reviewer attribution. Same-session edit timing was not independently established.

## Manual testing recommendations

### Needs you

After fixes and the normal toolkit upgrade, observe a real fix-round review and a recorded Codex-limit window. Confirm the selected model, reviewer attribution, notifications and resumption behavior with the actual CLIs.

### Covered by automated tests

The recorded suite covers queue repair, manifest lifecycle, disposition and flow-line rulings, retries, risk routing, limit memory, reviewer attribution and isolated subprocess state. Add the three missing regressions above and rerun `./scripts/ai-check`.

Reviewing does not constitute human acceptance.