# Spec: robustness batch from the stop analysis of 2026-10-07 (FL-12, FL-14..FL-17)

## Objective
Remove five pipeline stops seen in real runs whose cause was a format or wording problem, not
a real defect. Source: vault backlog `agents-backlog.md`, section "Stop analysis 2026-10-07
(mission control)". Planned 2026-10-08 on branch `fix/robustness-batch` from origin/master
c7d4dee. Each item was checked against this branch; all five are still open (nothing dropped):
- FL-14: `publish_review` (`scripts/lib/workflow.py`) requires the literal strings
  `Overall verdict:` and all three `## <LEVEL> findings` headings. `publish_plan_review` requires
  the three headings.
- FL-15: `ai-pipeline` resolves `--base` with `git rev-parse "$base^{commit}"` (local branch
  first) and passes the name, not the SHA, to `ai-review`, which resolves it again.
- FL-17: `review_current` in `ai-pipeline` returns false when the base is not an ancestor of the
  reviewed commit, and `publish_ready` reports every false as "reviewed content changed".
  Nothing checks the base before the code review.
- FL-16: `DISPOSITION_ROW` only matches a bare ID cell (`| M1 |`).
- FL-12: `recover_decision` only accepts a text that is one JSON object (optionally fenced).
  `test_recovery_decision_parsing_is_strict` pins `Decision: {...}` to `escalate`.

## Requirements
- **R1 (FL-14, P1): review report tolerance.** A code or plan review report may leave out a
  `## <LEVEL> findings` section whose count on the `Finding counts:` line is 0. Every existing
  mismatch is still rejected and the prior review is kept: a count above 0 with the section
  missing or empty, a count of 0 with findings listed, a number of IDs that differs from the
  count, and zero or more than one counts line. A code review's verdict can be the line
  `Overall verdict: <text>` or a `## Overall verdict` heading (an optional trailing colon is
  allowed) followed by non-empty text. A report with neither form, or with an empty heading
  section, is still rejected. The PR body shows the verdict text for both forms.
- **R2 (FL-15, P1): fresh review base.** When `--base B` names a local branch and
  `refs/remotes/origin/B` exists and is strictly ahead of it (the local branch is an ancestor
  and the two differ), `ai-pipeline` uses `origin/B`. If they have diverged, it uses the local
  branch and prints a warning. If the remote branch is absent, equal or behind, or the base is
  not a local branch name (`origin/B`, a SHA), the behaviour is unchanged. No fetch (offline;
  the pipeline never reaches the network before the push). The pipeline prints the resolved
  base (ref and short SHA) and passes the resolved SHA to `ai-review`, so the review, fix-round
  count, dispute base and publish check all use the same commit. Inferring the PR target is
  unchanged (`--base main` still targets `main`).
- **R3 (FL-17, P2): base moved past the branch.** When the resolved base commit is not an
  ancestor of HEAD, the pipeline stops before the code review with "Review base `<ref>`
  (`<sha>`) moved past the branch; merge it into `<branch>` and rerun". The publish check
  reports the same case with that wording, not as "reviewed content changed". Auto-recovery
  escalates this stop without a Claude session, because merging the base is a human decision.
- **R4 (FL-16, P2): severity suffix in triage IDs.** A disposition row whose finding cell is
  `M1 (MAJOR)` counts as the row for `M1`. This applies to `triage-check`, the review history,
  re-check preparation and the PR body, which all use `DISPOSITION_ROW`. The suffix may be
  BLOCKER, MAJOR or MINOR in any letter case. The finding ID stays the key and the suffix is not
  checked against the finding's level. Other decorations (bold, links) stay unmatched.
- **R5 (FL-12, P2): recovery decision after prose.** The decision is valid when the session's
  text is exactly one decision object, as today, or prose followed by exactly one JSON object
  that ends the text (optionally inside a closing code fence). It escalates when anything
  follows the object, when the prose holds another JSON object with an `action` key, or in
  every case that escalates today (exit code, envelope, duplicate keys, unknown action, missing
  reason, non-object).

## Non-goals
- No retry of malformed reviews. FL-04 R4 on `feature/supervisor` adds a review format retry,
  and this batch only widens what is accepted.
- No `git fetch` and no `--json-schema` structured output. Both need the network or a newer
  CLI, and neither can be tested offline.
- No change to how the review range is computed (`merge-base..HEAD`) or to what
  `review_current` requires.

## Constraints
- Pipeline sessions edit `scripts/`, `templates/`, `tests/`, `README.md` and `docs/` only. They
  never edit `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/permissions.allow` or
  `.claude/settings.json`. This repo's installed copy picks up the fixes later through
  `setup-project --upgrade`, which Zack approves.
- Concurrent work: `feature/supervisor` (FL-04, PR #21, not merged) also edits
  `scripts/ai-pipeline`, `scripts/ai-review`, `scripts/ai-recover`, `scripts/lib/workflow.py`
  and `tests/test_workflow.py`. Keep hunks small and local. Do not refactor or move shared
  code. New tests go in new methods, and new helpers go next to the code they serve.
- Every flow change updates the vault flow note `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`
  (with `Edit`, never a whole-file rewrite, because FL-04 edits the same note) and its
  `updated:` date in the same task. Unattended sessions never tick vault checkboxes. They append
  a dated line to the hub `agents.md` Log instead.
- All tests run offline in `tests/` (mock `claude`, `codex` and `gh`, local bare `origin`).
