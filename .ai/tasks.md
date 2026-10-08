# Task queue

Branch `fix/robustness-batch`: robustness batch FL-14..FL-17 (see `.ai/project-spec.md`). FL-12 is deferred to a later batch (plan revision 3).
Edit `scripts/`, `templates/`, `tests/`, README and docs only; never `.ai/bin`, `.ai/prompts` or other gate files.
`feature/supervisor` (FL-04) edits the same files: keep hunks small and local, no refactors of shared code (see `.ai/current-plan.md`).

## T001 — Review report: missing 0-count section and verdict heading (FL-14)
Status: DONE
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
2026-10-08: `publish_review` requires only `Finding counts:` plus a verdict from the new `review_verdict` (next to `reviewer_label`); failure message unchanged ("Review is missing Overall verdict:; prior review preserved. …"). `publish_plan_review` requires only `Finding counts:`. `pr_body` uses `review_verdict`, falling back to `unknown`. `review_counts` unchanged. Small widening beyond the plan: the verdict line may be bolded (`**Overall verdict:** x`), so reports that passed the old substring check in that form are not newly rejected. New mock Codex mode `verdict-heading`; 5 new `test_review_format_*` tests cover every acceptance criterion (missing 0-count sections in code/plan reviews with `review-info`/`plan-review-info`, all six mismatch cases for both report kinds with `current.md`/`plan.md` byte-identical, heading verdict with and without colon and PR body `Verdict: Approve with two minor notes.`, empty/missing verdict rejected, `ai-review --base main` with the heading mode). Targeted command: 14 tests OK; `.ai/bin/ai-check`: 292 tests OK. Docs: `docs/workflow.md` publish rules, README review step. Flow unchanged.

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
Matrix (one test method per row, or subtests with a fresh fixture each): origin ahead; equal; no origin ref; origin behind (`test_review_base_local_ahead_of_origin`: after pushing `main`, add a commit on local `main` with `git commit-tree` + `git branch -f main <sha>` and merge it into `feature/test`, so origin/main is an ancestor of local `main`); diverged; explicit SHA (`test_review_base_explicit_sha`: `--base <sha of main>` with `--no-pr`, which needs no PR target). Each successful row asserts the printed `Review base:` line, the published review's host `merge-base` and the SHA named in the Codex prompt.

Docs: README ("Pull request"/`--base` lines ~228–274), `docs/workflow.md` (pipeline base and PR stage, ~line 353), the `ai-pipeline` usage text (`--base is the review base …`), and vault `agents-flow.md`. In the flow note, add a short bullet "Review base (FL-15, date)" under the big picture and bump `updated:`. Use `Edit`, not a rewrite. Append a dated line to the hub `agents.md` Log.

### Likely affected modules
scripts/ai-pipeline, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md, vault agents.md (Log)

### Acceptance criteria
- Local `main` behind origin/main, which the feature branch contains: `ai-pipeline --approved --base main --no-pr` prints `Review base: origin/main at <sha>`. The published review's host header `merge-base` equals origin/main's SHA, not local main's. The review prompt (mock Codex call log) names that SHA.
- Local `main` equal to origin/main, or no origin ref: prints `Review base: main at <sha>` and behaves as before (existing pipeline tests pass unchanged).
- Local `main` ahead of origin/main (origin behind), with the feature branch containing local `main`: prints `Review base: main at <local sha>` (no "is behind" suffix), and the published review's `merge-base` and the Codex prompt name local `main`'s SHA, not origin/main's.
- Local `main` and origin/main diverged: prints the divergence warning and reviews against local `main`.
- `ai-pipeline --approved --base <sha> --no-pr` completes: it prints `Review base: <sha> at <short sha>`, and the published review's `merge-base` and the Codex prompt name that SHA.
- `--base origin/develop` is unchanged, and `--base <sha>` in PR mode still stops for a missing `--pr-base` (`test_pr_base_follows_the_review_base_or_must_be_explicit` passes). With `--base main` the PR still targets `main` even when origin/main was chosen.
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
R3: when the resolved base is not an ancestor of HEAD, the pipeline stops before the plan review, implementation and code review with a message that names the case and the fix. An interrupted triage stage and a pending re-check are settled first, so the human's merge never lands in an open stage. The publish check reports the case the same way instead of "reviewed content changed". Auto-recovery escalates it without a Claude session.

### Implementation notes
Case seen: on 2026-10-08, FL-04 stopped at the PR publish check with "the review is not current for HEAD (reviewed content changed)" after a clean Codex review, and `ai-recover` escalated twice on that wording. The real cause: `review_current` requires the base (origin/master) to be an ancestor of the reviewed commit, and master had gained #19/#20.

`scripts/ai-pipeline`:
- New function next to `review_current`: `base_reached() { git merge-base --is-ancestor "$base_sha" HEAD 2>/dev/null; }` and a message variable or function. Use the wording `Review base <base_label> moved past the branch; merge it into <branch> and rerun ai-pipeline`, with `base_label` from T002.
- Start check: directly after the top-level `reconcile_disputes` call (~line 297), before the plan review and the implementation loop. If `! base_reached`, write the message to `.ai/local/last-error` and `stop start`. Do NOT place it before the interrupted-stage completion or `reconcile_disputes`. Both settle records bound to the existing review: `stage_verify` → `triage_scope` rejects any non-record change since the stage started, and a pending re-check allows only `RECHECK_RECORDS` since the reviewed commit. A merge made while either is open would make the rerun stop with a triage or re-check scope error, so the run settles both first and only then asks for the merge. Neither step uses the base range. They are triage (Claude) and re-check (Codex) of the review already published. Preserve the triage scope protection unchanged. Reason for the placement (see plan, Decisions): the base SHA is fixed for a run and HEAD only gains commits, so this is the earliest point that leaves no stage open, and it comes before the code review. A resume re-resolves the base and checks again.
- `publish_ready`: add `elif ! base_reached; then why="…moved past the branch…"` immediately before `elif ! review_current`. Leave the existing branches and their order unchanged.
`scripts/ai-recover`: add a separate `case` arm for `*'moved past the branch'*`, placed before the generic hard-rule arm. With recovery enabled, `stop` execs `ai-recover`, and `escalate` prints only its first argument to stderr (`printf 'Error: escalated to the human: %s\n' "${1:-$reason}"`, `ai-recover` ~43), so the arm must keep the detailed reason on stderr itself: first `printf 'Error: %s\n' "${reason% }" >&2` (the complete recorded reason, e.g. `Publish check failed at pull request preparation: Review base main (…) moved past the branch; merge it into …`), then `escalate 'the review base moved past the branch.' 'merge the base into the branch, then rerun ai-pipeline.'`. Do not change `escalate` itself (shared with every other arm and with FL-04). Do not edit the shared pattern lines, because FL-04 adds patterns there.

Tests (new methods named `test_base_moved_*`; reuse `advance_origin_main()` from T002, with the feature branch NOT containing the new commit):
- Start: `ai-pipeline --approved --base main --no-pr` (and `--base origin/main`) exits 1 before any agent. There is no `.ai/local/mock-invocations` and no Codex call log, stderr and `last-error` contain `moved past the branch; merge it`, and a ⛔ notification is sent. With `AI_AUTO_RECOVER='1'`, `ai-recover` escalates with no recovery Claude call (`recovery_calls()` empty), its notification names the base, and stderr still contains the full `Review base main (` … `moved past the branch; merge it into feature/test` message as well as `escalated to the human`.
- After merging origin/main into the branch, the same run proceeds normally (review, no-pr finish).
- Pending triage stage (`test_base_moved_with_pending_triage_stage`): build the stage as `test_triage_completion_crash_after_counted_commit_does_not_count_twice` does (`ai-run`, `ai-review --base main` with `major-once`, `run-manifest start`, `stage-set triage <head>`) but without running the triage child. Set up the origin as T002's fixture does (`add_origin()`, push `main`). Then call `advance_origin_main()` (branch not containing it) and run `ai-pipeline --approved --base main --no-pr`, expected 1. Assert stdout `Completing the interrupted review triage`, `triage_rounds() == 1`, `open_stage() == ''`, the base message in stderr, and no new Codex review (the Codex call count is unchanged across the run). Then `git merge --no-edit origin/main` and rerun: it exits 0 with no `Triage stage` error and T002 DONE.
- Counted-but-open triage stage (`test_base_moved_with_counted_open_triage_stage`): the same, but run `ai-run --approved --triage --since <head>` before advancing origin (as the existing test does). The stopped run closes the stage without a second count (`triage_rounds() == 1`, `triage_calls() == 1`, `open_stage() == ''`), then stops with the base message. After the merge, the rerun completes.
- Pending re-check (`test_base_moved_with_pending_recheck`): adapt `test_disputed_findings_interrupted_before_recheck_rechecks_original_findings_first`. `ready()`, `add_origin()`, push `main` to origin and fetch, then the same first run (`MOCK_CODEX='two-major-once'`, `MOCK_CLAUDE='triage-mixed-reject'`, `MOCK_RECHECK_FAIL='1'`, expected 1) leaves `recheck-status` `pending`. Record the number of `chore(ai): record independent review` subjects, then `advance_origin_main()` (branch not containing it) and run `ai-pipeline --approved --base main` with `MOCK_RECHECK=self.UPHELD_M2`, expected 1. Assert: `len(recheck_calls()) == 2` and the second call holds `M2\tMAJOR\tthe second defect is handled by the gate` (the original findings); `recheck-status` is `verified`; one `chore(ai): record review re-check` commit and `disputes() == 1`; the base message in stderr and `last-error`; T002 still `TODO`; the independent-review subject count unchanged (no replacement code review); `triage_rounds() == 1`. Then `git merge --no-edit origin/main` and rerun the same command: it exits 0 with no `Re-check:` scope error, `len(recheck_calls()) == 2` (not re-checked again), still one re-check commit and `disputes() == 1` (no duplicate dispute), T002 `DONE`, and a draft PR.
- Publish wording (`test_base_moved_publish_check_names_the_base`, mandatory): `ready()`, `add_origin()`, then `git branch -f main HEAD`, so that `main` has two commits and the base is the plan commit. Add a `post-commit` hook via `self.hook(...)` guarded on the subject `chore(ai): record independent review` (as in `test_publish_ready_commit_hook_changing_source_while_recording_review_stops_before_push`). The hook replaces HEAD with a commit of the same tree whose parent is `main^`: `git reset -q --soft "$(git commit-tree "HEAD^{tree}" -p main^ -m 'hook: rewritten history')"`. The tree is unchanged and the checkout stays clean. A merge-base with `main` still exists, so `disputes-verify` (`inherited_disputes`) passes, but `main` is no longer an ancestor. Do not use a parentless commit: without a merge-base, `disputes-verify` fails first with "No merge-base". Run `ai-pipeline --approved --base main` (PR mode) with `AI_AUTO_RECOVER='1'`, expected 1. Assert `Publish check failed at pull request preparation: Review base main (` and `moved past the branch` in stderr and `last-error`, no `reviewed content changed`, `remote_head(origin) == ''`, no `pr create` call, `recovery_calls() == []`, ⛔ in the notifications and no FINISHED. The stderr assertion with recovery enabled fails unless the `ai-recover` arm prints the full reason (see above). A second method, `test_base_moved_publish_check_without_recovery`, builds the same fixture through a shared helper, runs with recovery disabled (the test default `AI_AUTO_RECOVER='0'`) and asserts the same stderr and `last-error` text, no push and no `pr create`, so the detailed diagnostics are checked on both paths. This test fails if the `publish_ready` branch is left out. No test hooks in product code.

Docs: `docs/workflow.md` (publish checks ~line 340 and the recovery hard-rule list ~line 383), the README publish paragraph (~line 275), vault `agents-flow.md`. The docs say that an interrupted triage or pending re-check is completed before the stop, that a recovery escalation of this stop keeps the full message on stderr, and that the human merges only after that stop. In the flow note, add a start check node or edge after the interrupted-triage and dispute reconciliation steps ("base an ancestor of HEAD? no → ⛔ merge the base"), name the case in the `publish` node or its bullet, and add "base moved past the branch?" to the recovery `rules` node. Bump `updated:` and use `Edit` only. Append a dated line to the hub Log. The handoff `## Flow chart` says "Flow chart updated".

### Likely affected modules
scripts/ai-pipeline, scripts/ai-recover, tests/test_workflow.py, docs/workflow.md, README.md, vault agents-flow.md, vault agents.md (Log)

### Acceptance criteria
- A base not contained in the branch stops the pipeline before the plan review, implementation and code review, with the "moved past the branch; merge it into <branch>" message in stderr, `last-error` and the ⛔ notification. Without an open triage stage or a pending re-check, no Claude or Codex call happens at all.
- An open triage stage (pending or already counted) is completed exactly once before that stop and is cleared.
- A pending re-check is run once on the original findings and recorded once before that stop, with no implementation and no replacement code review. After the merge, the rerun neither re-checks again nor duplicates the dispute, and has no re-check scope error (`test_base_moved_with_pending_recheck`).
- Auto-recovery escalates that stop without a Claude session, and stderr keeps the full base message (base ref and SHA, merge advice, and the `Publish check failed at …` prefix on the publish path), with recovery enabled and disabled.
- After the human merges the base, the rerun completes, including after an interrupted triage or a pending re-check, with no triage or re-check scope error.
- The publish check reports the case as "moved past the branch" (tested by `test_base_moved_publish_check_names_the_base` and `test_base_moved_publish_check_without_recovery`, with no push, no PR and no recovery Claude call). "reviewed content changed" is still reported for a real content change (the existing publish-invariant tests pass).
- All existing pipeline and recovery tests pass unchanged. Docs and flow note updated.

### Validation
`python3 -m unittest tests.test_workflow -k base_moved -k review_base -k publish -k recover -k pr_base -k triage_completion -k stage_per_branch -k disputed`; `.ai/bin/ai-check`

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
