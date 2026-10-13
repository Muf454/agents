<!-- Host evidence: HEAD e8eb6c8c561a47656b740c91f8609ef24783efbf; merge-base 744827a5212847d9734d197559321ca1c7f042cc; saved 2026-10-13T05:44:27Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED. The requested features are implemented and the validation evidence is current, but planning can silently remove an uncommitted DONE task. The watchdog also repeats an already-announced stall after upgrading.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `e8eb6c8c561a47656b740c91f8609ef24783efbf`

Supplied base and merge-base: `744827a5212847d9734d197559321ca1c7f042cc`

Checkout: clean before and after review. No files written; no network or MCP integrations invoked.

## Scope and validation

Inspected repository instructions, spec, plan, tasks, state, handoff, existing review structure, plan-review dispositions, relevant documentation, Git history, the full change range, affected source and regression tests.

Validation observed:

- `.ai/local/validation.json` reports PASS, exit 0, unchanged content, at `2026-10-10T10:37:13Z`.
- Its log reports **609 tests passed in 350.5 seconds**, across eight shards.
- `python3 -B scripts/lib/workflow.py stamp verify` passed against the current checkout. Changes after the recorded validation revision affect only excluded bookkeeping files.

Checks run during this review:

- Shell syntax checks: 13 scripts/templates passed.
- Python AST parsing: all three affected helper modules passed.
- Test discovery: 609 tests collected.
- Eleven pure dashboard renderer test bodies passed; filesystem fixture setup was deliberately omitted.
- Current queue validation passed; counts are 11 DONE of 11 tasks.
- In-memory reproductions confirmed both findings below.

The full `./scripts/ai-check` suite was not rerun because it creates validation records and temporary test checkouts, which this read-only review does not permit. The reproductions exercise actual helper logic, but are not complete shell integration runs.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — DONE-task preservation ignores uncommitted completed tasks

**Location:** `scripts/lib/workflow.py:2522`; callers at `scripts/ai-run:130`, `scripts/ai-run:284` and `scripts/ai-run:311`.

**Requirement:** DB-04/T011 requires every task DONE when planning starts to retain its identical block. Planning explicitly permits uncommitted plan records. README.md:144 promises this protection for tasks DONE when the session starts.

**Problem:** Both preservation checks use the committed HEAD queue as their baseline. `plan_keeps_done` reads `git show START:.ai/tasks.md` and returns immediately when that committed version has no DONE tasks. It never captures DONE tasks present only in the working tree at session entry.

**Evidence:** Using the repository’s valid task fixture and the actual helper with in-memory Git/file inputs:

1. Committed HEAD contains TODO T001.
2. The working queue contains DONE T001 before planning.
3. The pre-session preservation check passes.
4. The session replaces that queue with valid TODO T002, removing T001.
5. The post-session preservation check and final `tasks check` both pass.

Changing only `.ai/tasks.md` also satisfies the planning scope check. Consequently, this path can announce “Plan ready” after losing a completed task and its results.

Existing preservation tests commit their DONE-task baseline before invoking planning, so they miss this case.

**Impact:** An allowed planning revision can silently discard completed-task records, contradicting T011’s central integrity guarantee. This is introduced by the new planning mode.

**Recommended direction:** Capture the working queue before starting the session in a host-controlled baseline, and compare its DONE blocks after the session. Retain any committed-baseline protection that is still needed. Add integration coverage for uncommitted DONE tasks with and without `--revision`.

## MINOR findings

### N1 — Upgrading repeats an already-announced watchdog stall

**Location:** `scripts/lib/watchdog.py:447`, `scripts/lib/watchdog.py:468`; coverage at `tests/test_workflow.py:745`.

**Requirement:** FL-21 preserves notification deduplication and compatibility with older watchdog records.

**Problem:** An old record containing `active: ["stalled"]` but no `stall_seen_ns` loses its active incident on the first upgraded probe. The next confirming probe treats the unchanged stall as fresh and announces it again.

**Evidence:** Executing the actual incident/state-transition statements in memory produced:

- First upgraded probe: `fresh=[]`, `active=[]`, new `stall_seen_ns`.
- Probe ten minutes later, with the same stall: `fresh=["stalled"]`.

The subsequent notification branch therefore sends another STOPPED notification. With diagnosis enabled, it can also repeat diagnosis for the same incident.

This was previously identified as plan-review finding P18. No disposition for it is recorded, and it remains reproducible. The compatibility test checks only an older record with an empty active list.

**Impact:** One duplicate alarm per still-stalled checkout during upgrade, contrary to the notification-preservation requirement. This regression comes from the new confirmation logic.

**Recommended direction:** When the stall condition still holds and the previous active list already contains `stalled`, preserve it as confirmed. Clear it when the condition clears. Test an older record with an already-active stall across multiple upgraded probes.

## Missing test coverage

- Working-tree DONE tasks absent from the committed baseline: removal, status changes and result-text changes.
- Older watchdog records with an already-announced active stall.
- Real Claude permission matching and actual systemd scheduling remain dependent on the documented human checks.

The accepted plan-review work is substantially present: explicit session-option detection, long-run budget tests, raw DONE-block comparison including fenced content, corrected executable-permission assertions, and final-audit task ordering. M1 exposes a remaining baseline gap in the DONE-preservation fix.

## Security concerns

No additional demonstrated security finding in the inspected changes.

Planning supplies no Bash tool, and post-session scope/queue checks follow gate verification. The changed-gate test checks that an altered helper is not executed. Lock rejection avoids `ai_die`, preserving the owner’s error and notification records.

The documented `chmod +x` prefix rule cannot constrain paths to the checkout. Its prompt restriction and required human permission check remain relevant; offline string assertions do not prove real CLI enforcement.

## Architecture concerns

The changes reuse existing scripts and standard-library helpers without adding dependencies. The planning mode and dashboard stage fit the existing workflow structure.

M1 requires the preservation baseline to represent the queue the session actually receives. N1 requires migration to preserve already-confirmed incident state.

No separate pre-existing defect is counted in this report.

## Manual testing recommendations

### Needs you

- Verify a real planning session’s permissions, notifications, dashboard transitions and uncommitted output in a scratch project.
- Verify allowed `chmod +x` and denied alternate modes with the real Claude CLI.
- Verify timer scheduling after installation and upgrade with systemd.
- Verify relaunch during recovery names the owner and preserves the original stop reason.
- Complete the handoff’s pending vault flow-chart, gate and timer-update steps before merging.

### Covered by automated tests

- Existing regression groups cover invalid queues, session budgets, lock rejection, stall confirmation, planning outcomes, gate changes, dashboard stages and committed DONE-block preservation.
- Add shell integration tests for M1 using an uncommitted DONE task at session entry.
- Add watchdog integration coverage for N1 asserting no repeated notification or diagnosis for an already-active legacy stall.

Reviewing does not constitute human acceptance.