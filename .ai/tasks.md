# Task queue

Edit `scripts/`, `templates/`, `tests/`, docs. Never edit `.ai/bin`, `.ai/prompts` or other gate files.

## T001 — Shared tool contract, ai-task, permissions template
Status: TODO
Dependencies: none
Model: sonnet

### Goal
B1/E1 of `.ai/project-spec.md`.

### Implementation notes
Add the identical "How to work here" section to templates/.ai/prompts/runner.md,
triage.md and recover.md (recover is read-only: only the reading rules apply). New
`scripts/ai-task` (bash wrapper like the others) calling the existing `tasks set` helper,
plus `show`; add it to setup's copy list. Template permissions.allow: the approved read-only
commands, `git rm`, `git mv`, `.ai/bin/ai-task *`. Also make ai-run's runner/triage contract
strings point to the section instead of repeating rules.

### Likely affected modules
templates/.ai/prompts/{runner,triage,recover}.md, templates/.ai/permissions.allow,
scripts/ai-task, scripts/lib/workflow.py (setup list), scripts/ai-run, tests

### Acceptance criteria
- Tests: the three prompts contain the same section; setup installs ai-task; `ai-task set`
  changes status and rejects bad values; the permissions template contains the new entries
  and still no network, install or push commands.

### Validation
`python3 -m unittest discover -s tests -k <relevant>`, then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T002 — Model rule and human-todo rule in templates
Status: TODO
Dependencies: T001
Model: haiku

### Goal
B6 and R6 of `.ai/project-spec.md`.

### Implementation notes
Update the model-selection text in templates/CLAUDE.md and templates/.ai/prompts/plan.md
and plan-review.md (and triage.md for review-fix tasks) to the B6 wording. Add the R6
rule (never tick/untick knowledge-base checkboxes; append dated log lines) to runner.md
and triage.md.

### Likely affected modules
templates/CLAUDE.md, templates/.ai/prompts/{plan,plan-review,runner,triage}.md, tests

### Acceptance criteria
- Tests assert the new wording exists and the old "already failed review or validation
  once → opus" blanket wording is gone.

### Validation
`python3 -m unittest discover -s tests -k <relevant>`, then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T003 — Recovery completes an interrupted triage
Status: TODO
Dependencies: T002
Model: opus

### Goal
R1 of `.ai/project-spec.md`.

### Implementation notes
Record the triage start in host-trusted state (the run manifest, e.g. `stage: {name,
start_head, review_digest}`) before `ai-run --triage`. `ai-recover` must not commit leftovers
of a triage stage generically: for stage triage it either reruns (after committing nothing
but allowed workflow records) or escalates. On resume, ai-pipeline sees the open triage stage
and completes it: paths changed since start_head ⊆ triage-allowed files, `triage-check
--fresh` passes, then exactly one `chore(ai): record review triage` commit; then clears the
stage. Keep all existing tests green.

### Likely affected modules
scripts/ai-pipeline, scripts/ai-recover, scripts/lib/workflow.py (manifest stage), tests

### Acceptance criteria
- Test reproducing 2026-10-05: triage session leaves its records uncommitted (commit
  denied) → stop → recovery → resumed pipeline commits exactly one counted triage round and
  continues; the fix-round limit still applies.
- Test: triage leftovers that touch source → escalation, nothing committed.

### Validation
`python3 -m unittest discover -s tests -k <relevant>`, then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T004 — Publish invariants
Status: TODO
Dependencies: T003
Model: opus

### Goal
R2 of `.ai/project-spec.md`.

### Implementation notes
One function in ai-pipeline (e.g. `publish_ready`) checking: review current for HEAD,
validation stamp current, clean tree, tasks complete; call it after every host commit on the
publish path and immediately before each push; after the push compare
`git ls-remote origin <branch>` with HEAD. Failures go through `stop`.

### Likely affected modules
scripts/ai-pipeline, tests

### Acceptance criteria
- Tests: a commit hook that changes a source file while recording the review stops the
  pipeline before push; a pre-push hook that commits stops after; the normal path still
  opens the PR.

### Validation
`python3 -m unittest discover -s tests -k <relevant>`, then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T005 — Disputed findings: Codex re-check, draft on dispute
Status: TODO
Dependencies: T004
Model: opus

### Goal
R3 of `.ai/project-spec.md`.

### Implementation notes
`ai-review --recheck`: Codex reads `.ai/reviews/current.md`, the rejected BLOCKER/MAJOR rows
in dispositions.md and the code, and returns per finding `withdrawn` or `upheld` with a
reason (one JSON object, parsed strictly; anything else counts as upheld). Host writes
`.ai/reviews/recheck.md` bound by digest like current.md. ai-pipeline runs it after triage
whenever a BLOCKER/MAJOR is rejected; any upheld → unresolved → draft PR; pr-body starts
with "Disputed findings" (id, Claude's reason, Codex's answer). Default effort medium
(AI_RECHECK_EFFORT), model AI_REVIEW_MODEL.

### Likely affected modules
scripts/ai-review, scripts/ai-pipeline, scripts/lib/workflow.py (recheck parse, pr-body),
templates/.ai/prompts/recheck.md, tests (mock codex modes)

### Acceptance criteria
- Tests: rejection withdrawn by Codex → normal PR; upheld → draft with the section on top;
  malformed re-check answer → treated as upheld; no rejected BLOCKER/MAJOR → no re-check call.

### Validation
`python3 -m unittest discover -s tests -k <relevant>`, then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T006 — Toolkit version stamp and setup --upgrade
Status: TODO
Dependencies: T005
Model: sonnet

### Goal
R4/R5 of `.ai/project-spec.md`.

### Implementation notes
setup writes `.ai/toolkit-version` (JSON: toolkit commit from `git -C <toolkit> rev-parse
HEAD` or "unknown", per-file sha256 of installed toolkit-owned files). `setup-project
--upgrade PATH` prints the plan (replace / keep / advice / warning) and changes nothing;
`--upgrade --apply PATH` replaces toolkit-owned files and rewrites the stamp. A file whose
current hash differs from the stamp (local edit) is a warning and is only replaced with
`--force`. Mention reinstalling the watchdog timer. README: upgrades are their own PR.

### Likely affected modules
scripts/setup-project, scripts/lib/workflow.py, README.md, tests

### Acceptance criteria
- Tests: fresh setup writes the stamp; upgrade preview changes nothing; apply replaces an
  outdated .ai/bin file and keeps .ai/validate and permissions; a locally edited toolkit file
  is reported and kept without --force.

### Validation
`python3 -m unittest discover -s tests -k <relevant>`, then `.ai/bin/ai-check`.

### Result / notes
(pending)

## T007 — Docs match the code; flow chart updated
Status: TODO
Dependencies: T006
Model: sonnet

### Goal
R10 of `.ai/project-spec.md`.

### Implementation notes
Fix the contradictions listed in the spec in README.md and docs/workflow.md; add the modes
table. Update the vault flow chart `~/zWiki/zWiki/20 Projects/agents/agents-flow.md`: the
re-check step (R3), triage completion after recovery (R1), and its `updated:` date; keep the
Mermaid valid and plain-language.

### Likely affected modules
README.md, docs/workflow.md, the vault agents-flow.md

### Acceptance criteria
- grep finds none of the stale claims; the modes table exists; agents-flow.md shows the
  re-check step and has today's `updated:` date.

### Validation
`python3 -m unittest discover -s tests -k <relevant>`, then `.ai/bin/ai-check`.

### Result / notes
(pending)

