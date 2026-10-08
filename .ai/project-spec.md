# Spec: fixes from the Codex catch-up review of the reviewer fallback (M1, M2)

## Objective
Fix the two MAJOR findings of Codex's catch-up review of `0818f20..b98aa66` (PRs #16/#17,
merged 2026-10-07). Report: `.ai/local/reference/catchup-review-b98aa66.md` (ignored copy;
also `~/Projects/agents/.ai/reviews/current.md` on the old branch). Triage by Claude (mission
control) 2026-10-07: M1, M2 accepted; N1–N3 (outcome-report MINORs) deferred to vault backlog
CU-1..3. Zack: development goes through the toolkit pipeline.

## Requirements
- **R1 (M1) Read-only reviewer policy** (revision 4: plan review rounds 1–4 each found a new
  command-argument route through a Bash allow/deny scheme, so the reviewer gets no shell).
  The Claude fallback reviewer runs with tools `Read`, `Glob`, `Grep` only: no Bash, Edit or
  Write, no probe directory, nothing inherited from `.ai/permissions.allow`. Before the session
  the host writes the git context the reviewer used to fetch itself into
  `.ai/local/review-context/` (ignored; recreated per attempt, removed right after the session,
  also when the review fails):
  - code review: diff, `log --stat` and changed paths of `merge-base..HEAD`, plus the diff since
    the last reviewed HEAD when that HEAD is known and an ancestor;
  - re-check: the same for the reviewed range (base from the current review's host header
    `HEAD h; merge-base m`, head from `recheck-prepare`) plus the rejected findings;
  - plan review: no diff; the plan file paths and recent history.
  The Claude-path prompt names these files instead of git commands (the Codex prompt keeps its
  commands); the reviewer also reads the validation evidence (`.ai/local/validation.json`, gate
  logs) and the source. If any mandatory context command or write fails, the host removes the
  partial context and stops before Claude starts; the prior review stays (plan review round 6
  P3). The saved `.allowlist` file lists `Read`, `Glob`, `Grep`. The
  checkout-unchanged check stays. README, `docs/workflow.md`,
  `templates/.ai/prompts/claude-review.md` and the vault flow chart describe the same policy.
- **R2 (M2) Outcome per stopped attempt.** `ai-run` logs exactly one task outcome for a
  session that stops before its result: `timeout` (session exit 124/137), `interrupted`
  (runner exit 130/143), else `error`. A later recovery counts as a further attempt and is
  not a first-time pass. Existing outcomes (`done`, `blocked`, `validation_failed`,
  `no_checkpoint`) stay single. A runner killed without its EXIT handler (SIGKILL, OOM kill, power loss)
  logs nothing for that attempt; this is an accepted limit of this fix (the outcome log is
  advisory model-tuning data). Crash-durable attempt markers were planned in revisions 5–6 and
  moved to the vault backlog (CU-5) by mission control after plan review round 7, to keep this
  fix small.

## Reference
`.ai/local/reference/catchup-m1-m2.patch` is a prototype of both fixes with tests, written by
hand in the mission-control session (not committed, not gated). **Superseded for M1:** its
reviewer allow/deny lists, and the live deny-list check done with them (`git log -1
--output=f` and `git log -1 > f` denied), belong to the abandoned Bash policy; do not copy
that part. Its M2 part opens the attempt too early (plan review round 1, P4). The implementer
may reuse what still fits after checking it; it is not evidence of correctness.

## Constraints
Edit `scripts/`, `tests/`, docs only; never `.ai/bin`, `.ai/prompts` or other gate files. The
repo's installed copy picks the fixes up later via `setup-project --upgrade` (Zack approves).
