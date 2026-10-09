<!-- Host evidence: HEAD 43a705f209562af6977275e14249e33d506a7c19; merge-base 5e837acd20bd82f69d0fab38e5810e8eac076238; saved 2026-10-09T07:37:15Z. -->

> **Reviewer: Claude fallback (claude-opus-5-5, effort high; Codex usage limit). Codex catch-up review pending: see .ai/reviews/fallback-log.md.**

# Independent review

Overall verdict: APPROVE. CU-1, CU-3 and CU-4 are implemented as the spec and tasks require, and the merge of master keeps both sides of `outcome` correctly. Two MINOR record and telemetry gaps remain.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

Reviewed HEAD: `43a705f209562af6977275e14249e33d506a7c19` (merge of master into `fix/outcome-followups`)

Supplied base: `5e837acd20bd82f69d0fab38e5810e8eac076238` (the merge-base is the same commit)

Inspected:
- `.ai/local/review-context/diff.patch`, `log.txt` and `files.txt`.
- The actual source of `scripts/lib/workflow.py`:
  - `outcome` and `outcomes_report` (2713–2867)
  - `rejected_rows`, `publish_recheck` and `recheck_values` (1355–1502)
  - `pr_body` (2990–3069)
- `scripts/ai-review` (255–369) and `tests/run_parallel.py` (whole file).
- The new and updated tests in `tests/test_workflow.py` (3963–4010, 5514–5570, 6805–6890).
- The frozen `.ai/bin/lib/workflow.py` `outcome`, to check the merge resolution.
- Spec, tasks, handoff, state, `.ai/reviews/plan.md` (plan review round 5) and `.ai/reviews/dispositions.md`.

## Validation observed/run

- **Host evidence:** `.ai/local/validation.json` reports **PASS**, exit 0, `unchanged: true`, timestamp `2026-10-09T07:34:11Z`, `head` = `1d07424` (the pre-merge parent, not the reviewed HEAD). Its log `.ai/local/check-3tqUH4WJ.log` reads `Ran 411 tests in 237.1s (8 shards, 411 collected)` / `OK`.
- **Which tree it covers:** the branch had 297 tests before the merge (T003 result). The merge commit (07:34:20Z, 9 s after the evidence) claims 411, so this run almost certainly covered the merged working tree before the merge was committed. I cannot compare the fingerprint to HEAD's tree without a shell.
- **Merge resolution:** checked against `.ai/bin/lib/workflow.py:2713–2751` (master's `outcome`). The merged `outcome` is master's function plus the branch's `elif mode == 'recheck'` arm, and master's `plan_revision` kind is kept (`workflow.py:2743–2765`).
- **Duplicate test methods:** none among the new or helper names (`outcome_report_for`, `recheck_outcomes`, `colour_env`, `test_outcome_*`, `test_parallel_runner_*`). A duplicate name would silently shadow a test.
- I ran no commands (this review has no shell).

Limitations:
- I did not rerun the tests.
- I could not confirm that the validation fingerprint equals the tree at `43a705f`.
- I did not open the vault notes, which are outside the checkout.
- The mutation checks recorded in T001 (Python 3.14.7) are claims; I did not reproduce them.

## Requirement assessment

- **R1 (CU-4):** done.
  - `run_shard` drops `FORCE_COLOR` and sets `NO_COLOR=1` and `PYTHON_COLORS=0` (`run_parallel.py:71–73`).
  - `summary()` strips SGR escapes before parsing (`:56–64`). The task notes suggested a broader escape regex; the narrower one matches what `_colorize` emits.
  - Before each case, the tests remove the host's `NO_COLOR`, `FORCE_COLOR` and `PYTHON_COLORS` (`test_workflow.py:6854–6857`), so no case passes on inherited settings.
  - The failing-shard test asserts that no `\x1b` reaches the echoed output (`:6868–6874`). On Python < 3.13 this test proves nothing, as the task records.
- **R2 (CU-1):** done.
  - `attempts_table` groups each task row by its own model (`workflow.py:2808–2824`).
  - The first-time-pass denominator counts each task once, via its first row in file order (`first_row`, `:2804–2806`, identity check at `:2812`).
  - The category table is still per task (`:2830`).
  - The expected rows in `test_outcome_report_credits_each_attempt_to_its_model` check out by hand: sonnet (600+60)/2/60 = 5.5; opus `-`; category row 1.5 attempts, 8.0 min.
- **R3 (CU-3):** done.
  - Counts come only from the host-bound `recheck.md`, through `recheck_values()` and `rejected_rows()` (`workflow.py:2753–2762`).
  - `reviewed_head` is resolved with `rev-parse --verify`.
  - Any failure drops the new fields but still writes the line. `fail()` raises `ValueError`, which the `except` catches.
  - `ai-review` writes the line right after `publish-recheck` (`ai-review:354–355`), so the counts cannot come from an earlier re-check.
  - The report splits plan/code reviews from re-checks and builds the catch-up list from all reviews, outside both table blocks (`workflow.py:2833–2866`).
- **R4 (CU-2):** deferred as the spec says. The report behaves as before for Claude reviews.
- **Constraints:** `ai-review`, `ai-pipeline`, `ai-recover`, `.ai/bin` and the gate files are untouched (`files.txt`). The changes stay inside `outcome`, `outcomes_report`, `run_parallel.py`, new tests and docs.

## BLOCKER findings

None found.

## MAJOR findings

None found.

## MINOR findings

### N1 — "Codex catch-up pending" shows the wrong HEAD for a Claude re-check, and plan review round 5 was never dispositioned

**Status:** demonstrated (path traced; the branch's own test confirms the two SHAs differ).

**Location:** `scripts/lib/workflow.py:2746` (outcome `head`), `:2864–2865` (catch-up list), `scripts/ai-review:355` → `:277` (fallback record), `.ai/reviews/plan.md:34–39` (round 5 P2), `.ai/reviews/dispositions.md` (no round 5 section).

**Problem:** a Claude re-check is logged in two places, and the catch-up line uses the wrong one of the two HEADs available:
- `ai-review` writes the re-check's row in `fallback-log.md` with the *reviewed* HEAD (`review_records "$head" recheck`, where `$head` comes from `recheck-prepare`).
- The outcome line's `head` is `git rev-parse HEAD` when the line is written. For a re-check that is after the triage commit, because `ai-review:342` requires a committed triage.
- The "Codex catch-up pending" list prints `head`, not the new `reviewed_head`.

`test_outcome_recheck_records_upheld_and_withdrawn_totals` asserts `reviewed_head != head` (test line ~5530), which proves the mismatch. The JSONL report test also locks it in (`recheck HEAD abcdef012345`, taken from `head`).

Plan review round 5 raised exactly this (P2): use `reviewed_head` when present, or else document the mismatch in the README "Outcome log". It also raised P1, which category the combined table uses. Neither was applied or recorded:
- `dispositions.md` stops at round 4.
- README:1345–1347 and `docs/workflow.md:785` describe `reviewed_head` but not the mismatch.
- Per P1, the code uses the task's final row's category (`last.get('category')`, `:2832`). That is a reasonable reading of the spec's "the task's category", but it is undocumented.

**Impact:** advisory telemetry only. A human matching catch-up entries against `fallback-log.md` sees two different SHAs for the same Claude re-check. The field that would match (`reviewed_head`) is recorded but not used. CU-2 will need to match on it later. Nothing in the pipeline's behaviour changes.

**Recommended direction:** in the catch-up line, print `r.get('reviewed_head') or r.get('head')`. Old lines fall back to `head`, so nothing disappears. Update the JSONL test to give the line both fields with different values and assert the `reviewed_head` prefix. Add a "Plan review round 5" section to `dispositions.md` recording P1 (final-row category; a one-line note in docs) and P2.

### N2 — `.ai/handoff.md` still says T003 is TODO and that nothing is implemented

**Status:** demonstrated.

**Location:** `.ai/handoff.md:4` ("Planned (revision 5), nothing implemented yet."), `:7` ("T003 (CU-3, TODO)"), `:30–31` ("Next action: Implement T003.").

**Problem:** the handoff contradicts the actual state:
- `.ai/tasks.md` marks T001–T003 DONE with evidence.
- `.ai/state.md` says `Phase: ready_for_review`, `Tasks remaining: 0`.
- The source contains T003's code and tests.

The project rules require keeping the handoff current at each checkpoint. The T003 commit (`f89b08c`) and the two later record commits did not update it, and the merge kept "this branch's versions" of `.ai/` records.

**Impact:** a person or a fresh session resuming from the handoff would try to implement T003 again. The PR body takes only "Flow chart" and "Manual testing for the human" from the handoff (`workflow.py:3020`, `:3060`), and both are correct, so the published PR is not affected.

**Recommended direction:**
- Mark T003 DONE in "What has been implemented?" and drop "nothing implemented yet".
- Set "Next action" to the review/acceptance step.
- Mention the master merge (toolkit upgrade 4), so the human knows the branch also carries master's changes.

## Missing test coverage

Checklist items checked (Python/shell telemetry; no database, UI or authorization surface):
- **3, attribution:** re-check counts and `reviewed_head` come only from the sha256-bound `recheck.md`, re-verified against the current review and rejected-rows digests (`workflow.py:1490–1497`), never from Codex's raw `$report`.
- **4, stale results:** the line is written once, right after `publish-recheck`. A failed publish exits before `review_records`, so an earlier re-check's counts cannot be logged.
- **8, data hidden from views:**
  - Re-checks leave "Reviews by reviewer" on purpose and are still counted in the summary line.
  - Claude re-checks stay in the catch-up list, including a log that holds only re-checks (tested).
  - `plan_revision` lines are ignored by the report, as master documents.
- **1, 2, 5, 6, 7, 9, 10:** do not apply.

Gaps:
- "Attempts by model and category" is asserted only for `sonnet / feature`. There is no `opus / feature` row assertion. The `## Attempts by model` assertion is a substring of the combined heading, but the `| sonnet | 2 | …` row assertion can only match the per-model table, so that table is effectively covered.
- No test has a task whose rows have different categories, which is what decides `last` versus the row's own category (N1).
- The `CalledProcessError` arm in the re-check outcome (an unresolvable reviewed head) is untested. That is acceptable: the head comes from a bound header that was just verified.
- The JSONL report tests do not cover multiple input files (file order across arguments for `first_row`).

## Security concerns

None.
- `tests/run_parallel.py` runs inside the gate. The change can only cause false failures: a shard still passes only on `returncode == 0` plus a parsed `OK`, and the collected-versus-ran count check is unchanged (`run_parallel.py:110`, `:123`).
- The re-check outcome is read-only and nonfatal: `ai-review:279–280` runs it as `2>/dev/null || printf …`.

## Architecture concerns

None. The hunks stay inside `outcome`, `outcomes_report` and the test runner, as the spec's concurrency constraint asks. The merge kept master's `plan_revision` kind next to the new re-check arm with no duplicated logic.

Not counted: `tests/test_workflow.py:4009` now reads `path =self.base / …`. This is a whitespace slip from the T002 edit, harmless.

## Manual testing recommendations

### Needs you

- Re-run `.ai/bin/ai-check` at `43a705f` (or confirm the fingerprint), because the recorded evidence names the pre-merge parent `1d07424`.
- After `setup-project --upgrade` installs the new copy, run `.ai/bin/ai-status --outcomes` on real host data. Check:
  - "Attempts by model" reads sensibly for tasks retried on a different model.
  - Older re-check lines show as zero totals under "Re-checks by reviewer".
  - "Codex catch-up pending" still lists every Claude review. If N1 is not fixed, Claude re-check entries show the triage-commit HEAD, not the HEAD in `fallback-log.md`.
- On Python 3.14, run `PYTHON_COLORS=1 FORCE_COLOR=3 python3 tests/run_parallel.py` once and confirm that it ends with `OK` and that failing-shard output has no escape codes.

### Covered by automated tests

- Colour settings set by the caller, ANSI-safe summary parsing, and no escapes in a failing shard's echoed output: `test_parallel_runner_passes_with_caller_colour_settings`, `..._failing_shard_output_has_no_escapes`, `..._summary_parses_coloured_and_plain`.
- Per-attempt model credit, old attempt-less lines, and an old line followed by `attempt=2`: `test_outcome_report_*`. The updated `test_runner_logs_task_outcomes_and_report` covers the end-to-end table.
- Re-check upheld/withdrawn totals with `reviewed_head` after a real mocked re-check, a malformed answer (all upheld), BLOCKER counting through the helper, a line still written when unverifiable, and the separate re-check table plus a re-check-only catch-up list: `test_outcome_recheck_*`.
- Should be added (N1): a catch-up line that prefers `reviewed_head`, and a task whose rows have mixed categories in "Attempts by model and category".
- Full suite: 411 tests OK on the merged tree (host evidence above, labelled with the pre-merge head).

Review approval does not constitute human acceptance.
