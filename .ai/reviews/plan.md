<!-- Plan review of plan digest 5e1d2bcd13f79d67f692381a0b50bacce6efd3e6df823d7a3569533bd62ff1c9; saved 2026-10-08T20:39:58Z. -->

# Plan review

Overall verdict: APPROVE WITH MINOR PLAN CORRECTIONS.
Finding counts: BLOCKER=0 MAJOR=0 MINOR=2

Reviewed HEAD: `96c50686eef1ce214cdd46cb241cb223a61800f5` — plan revision 3.

## BLOCKER findings

None.

## MAJOR findings

None.

## MINOR findings

- P9: The advanced-base recovery test expects the wrong resolved ref.

  **Location:** `.ai/tasks.md:105`; base selection and diagnostic construction at `.ai/tasks.md:57–61,99`.

  This fixture advances origin/main beyond local main. T002 therefore selects `origin/main`, and T003 builds its message from that resolved ref. The prescribed assertion instead requires `Review base main (`. A correct implementation would fail that assertion.

  **Concrete plan change:** require `Review base origin/main (` for the advanced-origin startup tests, including automatic recovery. Keep the `main` expectation in the separate publish-hook fixture, which does not advance origin/main.

- P10: Specify and test saved-review reuse when the resolved base advances.

  **Location:** `.ai/tasks.md:60–65`; `.ai/project-spec.md:37–38,68`; `scripts/ai-pipeline:155–160,326–337`.

  The existing `review_current` predicate checks that the resolved base is an ancestor of the reviewed commit and that reviewable content is unchanged. It does not require the saved review’s merge-base to equal the newly resolved base. Consequently, a resumed run can select newer origin/main and reuse a review covering the older, broader range without invoking `ai-review`.

  This is existing behavior, and preserving that predicate is an explicit non-goal. However, the “same commit” requirement is ambiguous for this case, and T002’s fresh fixtures do not cover it.

  **Concrete plan change:** document that the same-base guarantee applies to newly requested reviews and that a valid broader saved review remains reusable. Add a rerun regression with a saved review and an advanced origin/main already contained in the reviewed HEAD; assert the intended reuse, resolved-base diagnostic and unchanged review binding.

## Scope and risk assessment

The inspected source supports T001’s reliance on `review_counts`: missing zero-count sections pass, while the prescribed positive-count and count/ID mismatches fail. T004’s proposed non-capturing suffix preserves the groups consumed by triage, history, re-check preparation and PR summaries.

T003’s placement preserves interrupted-stage scope checks before advising a merge. Its recovery diagnostics and mandatory publish-hook fixtures address the earlier findings. FL-12 is explicitly deferred and its parser remains unchanged.

All tasks specify suitable models. No task’s own failed implementation attempt is recorded. T003’s dependency on T002 is appropriate. No dependency addition or schema migration is proposed. Planned flow-note updates respect the repository’s maintenance rule.

## Validation observed

- Confirmed the requested HEAD and clean checkout; inspected guidance, workflow records, relevant source, tests, documentation, validation entry points and the vault flow note.
- Shell syntax passed for 13 files; Python AST parsing passed for three files.
- Read-only discovery collected 287 tests.
- Three existing documentation consistency tests passed.
- In-memory checks confirmed the specified count-parser rejection cases and proposed suffix capture groups.
- `git diff --check c7d4dee..HEAD` passed.

Integration test bodies, `./scripts/ai-check` and `.ai/bin/ai-check` were not run because they require filesystem writes unavailable in this review. No current validation stamp exists. Planned regression results remain unobserved.

No files were modified and no network/MCP integrations were invoked.

## Manual testing recommendations

After implementation and the full offline gate, check resolved-base messages and notifications with recovery enabled and disabled, then verify merge-and-rerun after interrupted triage and re-check stages. Inspect the flow-note changes alongside T002/T003. Installed-copy upgrades and human acceptance remain separate actions.