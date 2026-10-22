<!-- Plan review of plan digest ea0dcdee9c4d062b008c7b7a733e96ba897a4dbce68cc55b15a18e3bde344e09; HEAD 01f4093ceb09134fb143bddcb8b74a3c29acf7ad; saved 2026-10-21T21:35:51Z. -->

# Plan review

Overall verdict: REVISE BEFORE IMPLEMENTATION.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=2

Reviewed HEAD: `01f4093ceb09134fb143bddcb8b74a3c29acf7ad`

Scope: batch 10, T201–T221; repository guidance, plan/spec/tasks, previous review, affected source, event schema, tests, templates, documentation and validation.

## BLOCKER findings

None.

## MAJOR findings

- P17: Gate-event wiring mixes elapsed time with epoch time.

  **Location:** `.ai/tasks.md:5912–5918`; `scripts/ai-run:265–269`, `scripts/ai-run:736–739`.

  T220’s new `ai_gate_event` interprets STARTED as epoch seconds. However, `record_gate` currently receives Bash `$SECONDS`, an elapsed counter. Its checkpoint, retry and final-gate callers all use that clock. Simply adding the specified wrapper call would record starts near 1970 and durations approaching the current Unix timestamp, corrupting gate metrics. The proposed runner regression checks result and test count without checking timing.

  **Concrete plan change:** Define the clock conversion explicitly. Preserve elapsed duration measurement and supply a separate epoch start, or change the wrapper interface accordingly. Test checkpoint, retry and final events for plausible epoch starts and durations agreeing with their outcome rows.

- P18: Gate metrics lack a reliable fallback and deduplication rule.

  **Location:** `.ai/tasks.md:6274–6276`; `scripts/lib/workflow.py:4447–4450`.

  T211 specifies “events, fallback outcome gate rows,” but both records describe the same runner gates, and the existing outcome schema has no shared gate identifier. Partial event coverage is expected because writes may fail and events rotate. For example, two outcome gates of 10 and 100 seconds, with only the second event retained, should produce two gates and a median of 55. Choosing events whenever available loses the first gate; combining both sources counts the second twice. Current acceptance fixtures do not exercise overlapping, incomplete coverage.

  **Concrete plan change:** Specify how each gate is counted exactly once. For example, introduce a shared gate ID on both records and merge by ID, with an explicit policy for legacy rows. Add tests for complete overlap, partial event loss, rotation and legacy outcomes alongside new events.

- P19: Rotation makes historical outcome runs disappear from the run table.

  **Location:** `.ai/tasks.md:5805–5810`, `.ai/tasks.md:6277–6282`; `.ai/project-spec.md:257–259`.

  T217 explicitly tests that an ended run disappears after subsequent rotations. Its task/review outcomes remain indefinitely, including their `run` fields. T211 nevertheless lists runs only from retained `run` events, and reserves `(no run record)` for rows without a run ID. Consequently, those surviving outcomes have no defined run entry: per-project totals can include work absent from every per-run row. A missing lifecycle event also cannot reliably mean the run is open.

  **Concrete plan change:** Build run groups from the union of outcome and event run IDs. Define unavailable lifecycle metadata and event coverage explicitly, without labeling expired history as open or reporting missing event counts as complete zeroes. Add an integration regression that retains outcomes, performs multiple rotations, then checks both metrics views.

## MINOR findings

- P20: The revised triage prompt refers to a contract it never receives.

  **Location:** `.ai/tasks.md:5476–5479`; `scripts/ai-run:644–652`.

  T205 makes triage follow the RUNNER CONTRACT’s gate rule. The actual triage path appends a TRIAGE CONTRACT, with no gate rule, and T204 changes only implementation prompts. Thus the revised triage instructions depend on absent context; the proposed template string assertions would still pass.

  **Concrete plan change:** Give triage an explicit rule or add the appropriate rule to its TRIAGE CONTRACT. Test the captured triage prompt, including its behavior without a RUNNER CONTRACT.

- P21: Reusing a current plan review still skips silently.

  **Location:** `.ai/tasks.md:5162–5166`; `scripts/ai-pipeline:494–522`.

  T201 prints the skip line only when the review loop is not entered. An eligible queue with an already-current, unrevised review enters the loop, sets `review_due=no`, and exits without printing a skip explanation. This misses the stated requirement that every skipped plan review prints why.

  **Concrete plan change:** Print one explanation when reusing the current review, and add a regression asserting the line and absence of another reviewer invocation.

## Validation and limitations

- Read-only task-queue validation passed.
- Shell syntax checks passed for the affected workflow scripts and `.ai/validate`.
- Python AST parsing passed for the helper, parallel runner and existing test modules.
- Previous round findings P12–P16 are covered by the revised plan and are not repeated.
- Unittest suites and `ai-check` were not run because their fixtures require writes prohibited by this review sandbox. Historical gate evidence was not independently reproduced.
- No files were modified; no network or MCP integrations were invoked.

## Manual testing recommendations

After implementation and upgrade, compare one run’s gate durations with its raw records. Exercise metrics with retained outcomes after multiple event rotations, checking that run attribution and missing-data indicators remain understandable.