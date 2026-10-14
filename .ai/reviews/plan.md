<!-- Plan review of plan digest 0ba144a3003df6ee8c93e3d4298c40816cc9050e50f5333967d585f7a208f715; HEAD d511650392b90a5f2f8afe67c5f87e210dfc3bdf; saved 2026-10-14T21:10:20Z. -->

# Plan review

Scope: HEAD `d511650392b90a5f2f8afe67c5f87e210dfc3bdf`.

Overall verdict: Revise the plan before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=5 MINOR=2

## BLOCKER findings

None.

## MAJOR findings

- P1: Revision recovery validates the queue before reaching the proposed repair.
  **Location:** `.ai/tasks.md:111`; `scripts/ai-run:338`, `scripts/ai-run:366`; `scripts/lib/workflow.py:2426`.

  T002 places reorder after the revision-session/completed-dispositions branch. However, the earlier `tasks untouched` invokes `tasks()`, which rejects out-of-order dependencies. The completed-dispositions check also invokes `tasks()`. An interrupted revision with the repairable queue described in T002 therefore cannot reach the repair hook. Bypassing only the first check would still make the dispositions appear incomplete and encounter the dirty-record rejection.

  **Concrete plan change:** Restructure revision recovery so repair occurs before these queue-dependent decisions, after the applicable scope and provenance checks. Preserve the no-DONE restriction, status checks and committed-queue rejection outside revision recovery. Keep the planned crash/resume test and require it to demonstrate no second revision session.

- P2: Automatic tmpfs selection can put executable fixtures on a `noexec` filesystem.
  **Location:** `.ai/tasks.md:311`; `tests/test_workflow.py:602`, `tests/test_workflow.py:631`, `tests/test_workflow.py:1293`.

  T005 selects `/dev/shm` using writability and free space. A writable `noexec` mount satisfies those conditions, but fixtures directly execute mock agents and installed toolkit scripts from their temporary directories. Those executions fail with permission errors. The proposed temp-path test only exercises Python file I/O and would miss this incompatibility.

  **Concrete plan change:** Require execution capability before selecting the temporary filesystem, with fallback and cleanup when execution is denied. Add deterministic coverage for that fallback and an integration check that directly executes a fixture script from the selected directory.

- P3: The wait fingerprint can miss distinct notifications.
  **Location:** `.ai/tasks.md:524`; `scripts/lib/dashboard.py:248`; `.ai/project-spec.md:93`.

  T009 hashes the last event’s displayed message. `events_of()` sanitizes and truncates messages to 300 characters before returning them. Distinct notifications sharing that prefix and timestamp therefore produce identical fingerprints. I reproduced this in memory with two different messages. Repeated identical lines in one second also collide, as the plan acknowledges, despite the requirement that a new notification line triggers a change.

  **Concrete plan change:** Track notification identity using bounded raw content and file-version metadata, or a persistent notification revision, independently of display formatting. Test distinct messages with identical displayed prefixes and repeated identical notifications while status and stage remain unchanged.

- P4: The concurrent scheduler task uses the wrong model.
  **Location:** `.ai/tasks.md:245`, `.ai/tasks.md:252`.

  T004 explicitly changes concurrent work dispatch from fixed shards to batches consumed by worker threads, but specifies `Model: sonnet`. This falls under the required `opus` classification for concurrency work.

  **Concrete plan change:** Set T004 to `opus`, or split concurrent scheduling into an `opus` task and retain ordinary reporting/documentation work separately.

- P5: A known gate failure is deferred until the final task.
  **Location:** `.ai/handoff.md:37`; `.ai/tasks.md:585`; `tests/test_workflow.py:7210`.

  The current handoff starts its flow section with `Flow chart: T002 changes…`. The existing test requires `Flow chart updated` or `Flow unchanged` immediately below the heading. The current text deterministically fails that assertion. T010 repairs the declaration only after every implementation task, although every task must pass the full gate.

  This is a baseline problem present at the reviewed HEAD, rather than a future script regression.

  **Concrete plan change:** Repair the declaration before the first implementation gate, recording the current flow truthfully and retaining pending work below it. Update it when T002 actually changes the flow; leave the final audit in T010.

## MINOR findings

- P6: Documentation tests still require the obsolete shard description.
  **Location:** `.ai/tasks.md:269`; `tests/test_workflow.py:8291`.

  `DocsConsistencyTest.REQUIRED` requires both documentation files to contain “round-robin into `AI_TEST_WORKERS` shards.” T004 changes that architecture, but explicitly permits updates only to tests asserting runner summaries. Keeping the old wording leaves contradictory documentation; replacing it breaks the existing consistency assertion.

  **Concrete plan change:** Include the consistency-test contract and both documentation descriptions in T004, and name that intentional test change in its result.

- P7: T006’s unchanged-count criterion conflicts with adding cache regression tests.
  **Location:** `.ai/tasks.md:369`, `.ai/tasks.md:386`.

  T006 requires the collected count to remain unchanged while also requiring new `test_fixture_cache_*` tests if caching is introduced. The runner’s count check compares discovery with execution within one invocation; it does not establish that existing tests were preserved.

  **Concrete plan change:** Require preservation of existing test IDs and assertions, allow documented count increases for new coverage, and retain equality between collected and executed counts.

## Validation observed and limitations

- Read the repository instructions, spec, plan, tasks, state, handoff, relevant documentation, source, tests and validation entry point.
- Confirmed HEAD and a clean working tree.
- Shell syntax checks: 13 files checked, zero failures.
- Documentation consistency tests: three passed.
- Read-only probes confirmed the premature revision queue rejection, invalid handoff declaration and notification-display collision.
- Full `./scripts/ai-check`, fixture integration tests, tmpfs execution and CI timing measurements were not run because they require filesystem writes. No `.ai/local/validation.json` was present.

The reviewed plan preserves human control of merge and deployment and specifies bounded dashboard readers. The findings above concern recovery, event detection, validation sequencing and task contracts; this review is not human acceptance.