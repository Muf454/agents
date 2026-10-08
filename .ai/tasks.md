# Task queue

Branch `fix/robustness-batch`: robustness batch FL-12, FL-14..FL-17 (see `.ai/project-spec.md`).
Edit `scripts/`, `templates/`, `tests/`, README and docs only; never `.ai/bin`, `.ai/prompts` or other gate files.
`feature/supervisor` (FL-04) edits the same files: keep hunks small and local, no refactors of shared code (see `.ai/current-plan.md`).

## T001 — Review report: missing 0-count section and verdict heading (FL-14)
Status: TODO
Dependencies: none
Model: opus

### Goal
R1: a code or plan review report that leaves out a `## <LEVEL> findings` section whose count is 0 is accepted, and a code review whose verdict is a `## Overall verdict` heading is accepted like the `Overall verdict:` line. Every count/ID mismatch is still rejected and the prior review is kept.

### Implementation notes
Cases seen: the Codex plan reviews raid ownership-fixes round 1 and launch-standalone round 9 (`MINOR=0` with no `## MINOR findings` section), and on 2026-10-08 a Claude (Fable) fallback code review in raid-planner launch-teams that wrote `## Overall verdict` as a heading ("Review is missing Overall verdict:").

`scripts/lib/workflow.py`:
- `publish_review`: the `required` tuple keeps only `Finding counts:`. Check the verdict with a new helper `review_verdict(content)`, placed next to `reviewer_label`. It returns the text after the first `^Overall verdict:` line. Otherwise it returns the first non-empty line of the body under a heading matching `^#{1,6}\s+Overall verdict:?\s*$` (body up to the next heading, HTML comments removed). Otherwise it returns None. If it returns None or empty text, fail with the same message as today ("Review is missing Overall verdict:; prior review preserved. …"), so the FL-04 retry and the docs that quote it still match.
- `publish_plan_review`: drop the three section headings from its required tuple and keep `Finding counts:`. Plan reviews still need no verdict.
- `review_counts` stays unchanged. A missing section gives `section(...) == ''`, so a count above 0 already fails with "counts X=n but lists none", and the ID-count check is unchanged. Verify this with tests; do not rewrite it.
- `pr_body`: the verdict text uses `review_verdict(review)` instead of its own `^Overall verdict:` regex, still falling back to `unknown`.
Keep each hunk inside its function (FL-04 edits nearby).

Tests (`tests/test_workflow.py`, new methods only, named `test_review_format_*`). At helper level, use `publish-review` and `publish-plan-review` on a written report, as `test_review_with_a_renamed_optional_section_is_accepted` does. One test goes through `ai-review` with a new mock Codex mode, for example `MOCK_CODEX='verdict-heading'`, next to `counts-lie`.

Docs: `docs/workflow.md`, where the review report format and publish rules are described (search for `Finding counts`). In `README.md`, line ~263 ("a report whose counts disagree…"), add one clause. Flow unchanged (the report format is not drawn in the flow note).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md, README.md

### Acceptance criteria
- A code review with `Finding counts: BLOCKER=0 MAJOR=1 MINOR=0`, a `## MAJOR findings` section listing `M1`, and no BLOCKER or MINOR sections is published and bound. `review-info` prints `<head> 0 1 0`.
- A plan review with `MINOR=0` and no `## MINOR findings` section is published and `plan-review-info` reports `current` with those counts.
- Still rejected, with `current.md` and `plan.md` byte-identical to before: `MINOR=1` with the MINOR section missing; `MINOR=1` with a section of only `None.`; `MAJOR=0` with a MAJOR finding listed; `MAJOR=2` with one ID; no counts line; two counts lines. The existing `test_review_counts_must_match_listed_findings` and `test_failed_or_malformed_reviews_preserve_report` pass unchanged.
- `## Overall verdict\n\nApprove with two minor notes\n` (and `## Overall verdict:`) is accepted, and the PR body says `Verdict: Approve with two minor notes.`. A heading with an empty body, or no verdict in either form, is rejected with "missing Overall verdict".
- An `ai-review --base main` run with the mock mode that writes the heading form and omits the MINOR section publishes the review.

### Validation
`python3 -m unittest tests.test_workflow -k review_format -k review_counts -k malformed -k renamed_optional_section -k pr_body`; `.ai/bin/ai-check`

### Result / notes
Not started.

## T002 — Review base prefers a newer origin branch (FL-15)
Status: TODO
Dependencies: none
Model: opus

### Goal
R2: `ai-pipeline --base B` uses `origin/B` when it is strictly ahead of the local branch `B`, prints the resolved base, and gives `ai-review` the resolved commit, so the review never covers already-merged PRs because the local base is stale.

### Implementation notes
Case seen: raid-planner's local `main` stayed at bf52a08 while origin/main was at 824e71d, so reviews of `fix/owner-invariant-push` and PR #16 also covered PRs #12–#15.

`scripts/ai-pipeline`, at the `base_sha=$(git rev-parse …)` line (~86), keep the change in one small block:
- `base_ref=$base`. If `refs/heads/$base` and `refs/remotes/origin/$base` both exist and differ: when the local branch is an ancestor of the remote (`git merge-base --is-ancestor`), set `base_ref=origin/$base`. When neither is an ancestor of the other, keep the local branch and print `Local <B> and origin/<B> have diverged; reviewing against local <B>.`
- `base_sha=$(git rev-parse --verify --quiet "${base_ref}^{commit}")` with the same `Invalid base` failure.
- Print `Review base: <base_ref> at <short sha>` plus ` (local <B> is behind)` when it switched.
- Keep `$base` (the name) for inferring `pr_base`, which is unchanged. Pass `--base "$base_sha"` instead of `--base "$base"` to `ai-review` (line ~337). `ai-review` already accepts a SHA. `fix-rounds`, `AI_DISPUTES_BASE` and `review_current` already use `$base_sha`.
- Add a variable for the T003 message to reuse, for example `base_label="$base_ref ($(git rev-parse --short "$base_sha"))"`.
Never fetch. A resumed run re-resolves, so the base can advance between runs when someone fetches. This is accepted (T003 covers the case where it moves past the branch).

Tests (new methods named `test_review_base_*`). Fixture: `ready()`, then `add_origin()`, then push `main` to origin. Advance origin's `main` without touching the local branch: create a commit on top of `main` with `git commit-tree` (or on a throwaway branch), `git push origin <sha>:refs/heads/main`, `git fetch -q origin`, then delete the throwaway branch. For the ahead case, merge that commit into `feature/test` before the run. Name a reusable helper `advance_origin_main()`, because T003 reuses it.

Docs: README ("Pull request"/`--base` lines ~228–274), `docs/workflow.md` (pipeline base and PR stage, ~line 353), the `ai-pipeline` usage text (`--base is the review base …`), and vault `agents-flow.md`. In the flow note, add a short bullet "Review base (FL-15, date)" under the big picture and bump `updated:`. Use `Edit`, not a rewrite. Append a dated line to the hub `agents.md` Log.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md, vault agents.md (Log)

### Acceptance criteria
- Local `main` behind origin/main, which the feature branch contains: `ai-pipeline --approved --base main --no-pr` prints `Review base: origin/main at <sha>`. The published review's host header `merge-base` equals origin/main's SHA, not local main's. The review prompt (mock Codex call log) names that SHA.
- Local `main` equal to origin/main, or no origin ref: prints `Review base: main at <sha>` and behaves as before (existing pipeline tests pass unchanged).
- Local `main` and origin/main diverged: prints the divergence warning and reviews against local `main`.
- `--base origin/develop` and `--base <sha>` are unchanged (`test_pr_base_follows_the_review_base_or_must_be_explicit` passes). With `--base main` the PR still targets `main` even when origin/main was chosen.
- Docs, usage text and flow note describe the rule.

### Validation
`python3 -m unittest tests.test_workflow -k review_base -k pr_base -k pipeline_clean_review`; `.ai/bin/ai-check`

### Result / notes
Not started.

## T003 — Stop early when the base moved past the branch (FL-17)
Status: TODO
Dependencies: T002
Model: opus

### Goal
R3: when the resolved base is not an ancestor of HEAD, the pipeline stops before any agent or review with a message that names the case and the fix. The publish check reports it the same way instead of "reviewed content changed". Auto-recovery escalates it without a Claude session.

### Implementation notes
Case seen: on 2026-10-08, FL-04 stopped at the PR publish check with "the review is not current for HEAD (reviewed content changed)" after a clean Codex review, and `ai-recover` escalated twice on that wording. The real cause: `review_current` requires the base (origin/master) to be an ancestor of the reviewed commit, and master had gained #19/#20.

`scripts/ai-pipeline`:
- New function next to `review_current`: `base_reached() { git merge-base --is-ancestor "$base_sha" HEAD 2>/dev/null; }` and a message variable or function. Use the wording `Review base <base_label> moved past the branch; merge it into <branch> and rerun ai-pipeline`, with `base_label` from T002.
- Start check: after the helper functions are defined (so `stop` and the recovery handover work) and before the STARTED notification, the interrupted-stage completion, `reconcile_disputes`, the plan review and implementation. If `! base_reached`, write the message to `.ai/local/last-error` and `stop start`. Reason (see plan, Decisions): the base SHA is fixed for a run and HEAD only gains commits, so this is the earliest point and it covers the code review. A resume re-resolves the base and checks again.
- `publish_ready`: add `elif ! base_reached; then why="…moved past the branch…"` immediately before `elif ! review_current`. Leave the existing branches and their order unchanged.
`scripts/ai-recover`: add a separate `case` arm for `*'moved past the branch'*` that escalates with `the review base moved past the branch.` / `merge the base into the branch, then rerun ai-pipeline.`, placed before the generic hard-rule arm. Do not edit the shared pattern lines, because FL-04 adds patterns there.

Tests (new methods named `test_base_moved_*`; reuse `advance_origin_main()` from T002, with the feature branch NOT containing the new commit):
- Start: `ai-pipeline --approved --base main --no-pr` (and `--base origin/main`) exits 1 before any agent. There is no `.ai/local/mock-invocations` and no Codex call log, stderr and `last-error` contain `moved past the branch; merge it`, and a ⛔ notification is sent. With `AI_AUTO_RECOVER='1'`, `ai-recover` escalates with no recovery Claude call (`recovery_calls()` empty) and its notification names the base.
- After merging origin/main into the branch, the same run proceeds normally (review, no-pr finish).
- Publish wording (defence in depth): reach `publish_ready` with the base no longer an ancestor of HEAD. For example, use a `post-commit` hook on `chore(ai): record independent review`, as the publish-invariant tests do, that re-parents HEAD below the base with the same tree (`git reset --soft <commit before base>` and re-commit; the fixture needs base = a branch with at least two commits). Assert `Publish check failed at …: Review base … moved past the branch` and no `reviewed content changed`. If no deterministic fixture exists without a test hook in `scripts/`, record that in the result and cover the start check only. Do not add test hooks to product code.

Docs: `docs/workflow.md` (publish checks ~line 340 and the recovery hard-rule list ~line 383), the README publish paragraph (~line 275), vault `agents-flow.md`. In the flow note, add a start check node or edge ("base an ancestor of HEAD? no → ⛔ merge the base"), name the case in the `publish` node or its bullet, and add "base moved past the branch?" to the recovery `rules` node. Bump `updated:` and use `Edit` only. Append a dated line to the hub Log. The handoff `## Flow chart` says "Flow chart updated".

### Likely affected modules
scripts/ai-pipeline, scripts/ai-recover, tests/test_workflow.py, docs/workflow.md, README.md, vault agents-flow.md, vault agents.md (Log)

### Acceptance criteria
- A base not contained in the branch stops the pipeline before any Claude or Codex call, with the "moved past the branch; merge it into <branch>" message in stderr, `last-error` and the ⛔ notification.
- Auto-recovery escalates that stop without a Claude session.
- After the human merges the base, the rerun completes.
- The publish check reports the case as "moved past the branch" (or the result records why only the start check is tested). "reviewed content changed" is still reported for a real content change (the existing publish-invariant tests pass).
- All existing pipeline and recovery tests pass unchanged. Docs and flow note updated.

### Validation
`python3 -m unittest tests.test_workflow -k base_moved -k review_base -k publish -k recovery -k pr_base`; `.ai/bin/ai-check`

### Result / notes
Not started.

## T004 — Triage accepts a severity suffix in the finding cell (FL-16)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
R4: a disposition row `| M1 (MAJOR) | accepted | … | T004 |` counts as the disposition of `M1`, so triage no longer stops with "MAJOR finding M1 has no disposition".

### Implementation notes
Case seen: family M3 triage failed twice because the session wrote `| M1 (MAJOR) |`.

`scripts/lib/workflow.py`, `DISPOSITION_ROW` (~line 758): after the ID group, allow an optional `\s*\((?:BLOCKER|MAJOR|MINOR)\)` before `\s*\|`. The regex is already `re.I`. Group numbering must stay the same, so use a non-capturing group. This one change covers all users: `triage_check`, review history (~874), `recheck_prepare` (~1246) and `pr_body` (~2320). Check that `recheck_prepare`'s printed rows and rows digest still behave for suffixed rows: the rows feed `findings.txt` and the re-check binding.
`templates/.ai/prompts/triage.md` line ~13: add "(the bare ID, e.g. `M1`)" after "finding ID". This is the template only; the installed `.ai/prompts` copy is a gate file and updates by upgrade.

Tests (new methods named `test_triage_severity_suffix_*`): a mock triage mode or a hand-written `dispositions.md` with `| M1 (MAJOR) |` passes `triage-check --fresh` with `accepted=1`. A suffixed rejected row is picked up by `recheck-prepare`. The PR body counts suffixed rows. `| M1 (CRITICAL) |` and `| **M1** |` still do not match (the finding has no disposition).

Docs: one sentence in `docs/workflow.md` triage paragraph (~line 228). Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, templates/.ai/prompts/triage.md, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- `| M1 (MAJOR) |`, `| M1 (major) |` and `| M1(MAJOR) |` rows satisfy `triage-check` for MAJOR finding `M1`. Accepted rows still need an existing TODO fix task, and rejected rows still need evidence of 15 or more characters.
- `recheck-prepare` lists a suffixed rejected BLOCKER/MAJOR row, and the re-check binding verifies.
- Unknown suffixes and other decorations are still unmatched ("has no disposition").
- Existing triage and re-check tests pass unchanged.

### Validation
`python3 -m unittest tests.test_workflow -k triage -k recheck -k disposition`; `.ai/bin/ai-check`

### Result / notes
Not started.

## T005 — Recovery decision after prose (FL-12)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
R5: `recover-decision` accepts a decision object that follows the session's diagnosis prose, while keeping "exactly one decision". An ambiguous answer still escalates as "gave no valid decision".

### Implementation notes
Case seen: twice on 2026-10-07 the recovery session wrote its diagnosis first. The stop said "gave no valid decision" and lost the real reason (it was escalate both times).

`scripts/lib/workflow.py` `recover_decision` (~line 1625), changed in place:
- Keep the envelope checks unchanged. First try the whole text, as today (fence-stripped `json.loads` with `_no_duplicate_keys`).
- Only if that fails to parse: strip one trailing closing fence (```` ``` ````) and trailing whitespace, then find the object that ends the text. For each `{` position, `json.JSONDecoder(object_pairs_hook=_no_duplicate_keys).raw_decode(text, i)`. The decision is the dict whose end equals `len(text)`; at most one position can reach the end. Duplicate-key `ValueError`s at a position count as "no object here". Escalate if there is none.
- Ambiguity: escalate if the prefix before that object contains any `{` position that decodes to a dict with an `action` key (including fenced examples).
- The field validation after it is unchanged. Update the docstring (it describes a "first '{' to last '}'" span that the code does not implement).
Do not touch `scripts/ai-recover` (FL-04 edits it). Leave the prompt template `templates/.ai/prompts/recover.md` as it is (it still asks for JSON only; the parser is tolerant).

Tests: in `test_recovery_decision_parsing_is_strict`, change the `Decision: {"action": "rerun", "reason": "crash"}` case from `escalate` to `rerun`. This is the only existing assertion that changes; say so in the result. Add cases or a new method `test_recovery_decision_after_prose`:
- Accepted: multi-line prose then a bare object; prose then a ```` ```json ```` fenced object; prose with non-JSON braces (`{foo}`) then an object.
- Escalate: the object followed by more prose; two objects after prose; an `action` example in the prose plus a final object; prose then an object with duplicate keys; prose only; prose then `[{…}]`.

Docs: `docs/workflow.md` ~line 416 ("must be exactly one JSON object (optionally fenced)"), described as one decision object at the end of the answer, after optional prose, with no other `action` object. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- The accepted cases above yield the object's action, reason and human_action. Every escalate case prints the "gave no valid decision" line.
- All other cases in `test_recovery_decision_parsing_is_strict` keep their expected result.
- Recovery flow tests (`-k recover`) pass unchanged.

### Validation
`python3 -m unittest tests.test_workflow -k recovery_decision -k recover`; `.ai/bin/ai-check`

### Result / notes
Not started.
