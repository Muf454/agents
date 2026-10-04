# Independent audit — Codex

Read AGENTS.md, relevant docs, `.ai/project-spec.md`, `.ai/current-plan.md`,
`.ai/tasks.md`, `.ai/state.md`, `.ai/handoff.md`, and deterministic validation
evidence. Inspect Git history, diff against the supplied base, actual relevant
source/tests, and untracked work if reviewing a dirty checkout explicitly.

Independently assess whether Claude satisfied the requested work. Do not trust the
handoff summary, DONE labels, or passing tests without checking their relevance.
Look for requirement gaps, logic bugs, regressions, incorrect assumptions,
architecture violations, needless complexity, security/auth/authz issues, data
consistency, races, state bugs, error handling gaps, and missing edge-case tests.

Directly below "Overall verdict:", include exactly one machine-readable line
`Finding counts: BLOCKER=<n> MAJOR=<n> MINOR=<n>` matching the findings you list;
the pipeline uses it to decide whether fixes are needed. Count only real findings.
Start every finding with its stable ID as a heading or bullet (`### B1 — ...`,
`- M2: ...`); counts must match the listed IDs or the report is rejected.

Use the structure in `.ai/reviews/current.md`: overall verdict; BLOCKER, MAJOR,
MINOR findings; missing coverage; security concerns; architecture concerns; manual
testing recommendations. Each finding needs a stable ID, problem, location,
impact, evidence/reproduction where practical, and recommended direction. Record
reviewed revision/base, checks actually observed/run, and limitations. Include
the requirement behind a requirement-gap finding. Separate pre-existing defects.

Do not modify application code. Save only the review artifact when file writing
is authorized. If running in the scripted read-only review, return the complete
Markdown review as your final answer; the host writes `.ai/reviews/current.md`.
