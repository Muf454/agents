# Spec: flow hardening, batch 1

Source: [[agents-backlog]] (vault), "Suggested first batch", plus Zack's decisions of
2026-10-05 (recorded in the vault hub `agents.md`, Decisions). Every item fixes something
observed in real runs or found by both reviews.

## Requirements
- **B1/E1 Shared tool contract**: one identical "How to work here" section in the runner,
  triage and recovery prompt templates: Read/Grep/Glob for reading files, Edit/Write for
  changes (no heredoc/sed edits), plain commands without `cd`, `git rm`/`git mv` for tracked
  files, `.ai/bin/ai-task` to change a task
  status; recovery gets the reading rules only (it is read-only). Checks: the full gate via
  `.ai/bin/ai-check` plus a task's own targeted test command when it names one. Template
  `permissions.allow` adds the approved read-only shell commands (ls, grep, cat, head, tail,
  wc, echo; NOT sed, rg or find, which can write or execute through flags), `git rm`,
  `git mv` and `.ai/bin/ai-task *`. New
  script `ai-task` (`ai-task set T003 IN_PROGRESS|DONE|BLOCKED|TODO`, `ai-task show T003`)
  wrapping the existing task helper; setup installs it.
- **B6 Model rule**: templates say: choose each task's model by its own risk (haiku
  mechanical, sonnet ordinary, opus for security/auth/RLS, concurrency/locking, destructive
  data migrations); a task whose own earlier attempt failed validation or review is retried
  on opus; review-fix tasks get a model by their own risk (no blanket promotion).
- **R6 Human todos**: runner and triage prompts: never tick or untick checkboxes in the
  knowledge base; append dated progress to the project's log instead.
- **R1 Recovery completes the interrupted stage**: if a run stops during triage, the resume
  must still enforce the triage rules (only workflow records changed since the triage
  started; dispositions complete and fresh for the current review) and count the round
  exactly once (the `chore(ai): record review triage` commit). Recovery must never commit
  triage-stage leftovers as a generic checkpoint.
- **R2 Publish invariants**: after every host commit and immediately before each push, the
  pipeline requires: review current for HEAD (only workflow records changed since the
  reviewed commit), validation stamp current, clean tree, all tasks DONE. After the push,
  the remote branch head equals local HEAD.
- **R3 Disputed findings**: when triage rejects any BLOCKER/MAJOR, Codex re-checks only
  those findings against Claude's evidence (`ai-review --recheck`, read-only, medium effort
  by default). Per finding: `withdrawn` or `upheld`. Any upheld finding is recorded as a durable dispute (never auto-resolved) and makes the PR
  a draft whose body starts with a "Disputed findings" section (finding, Claude's reason,
  Codex's answer); Zack resolves disputes at the PR. Re-check reports and dispute records are
  host-written and digest-bound like other reviews.
- **R4/R5 Toolkit version + upgrade**: setup writes `.ai/toolkit-version` (toolkit commit
  and per-file SHA-256 of installed toolkit-owned files). `setup-project --upgrade PATH`
  previews, `--upgrade --apply PATH` replaces toolkit-owned files (`.ai/bin/**`,
  `.ai/prompts/**`) and keeps project-owned ones (`.ai/validate`, `.ai/ci-setup`,
  `.ai/permissions.allow`, `.claude/settings.json`, CLAUDE.md, AGENTS.md, docs); it lists
  template changes to project-owned files as advice, locally edited toolkit-owned files as
  warnings, and reminds to reinstall the watchdog timer. README: upgrades go in their own PR.
- **R10 Docs match the code** in README and docs/workflow.md (Codex listed: denials logged
  not fatal; runner/recovery stage application files; the pipeline pushes and opens PRs;
  provider-limit retries and recovery exist), with a short table of modes (interactive
  Claude, ai-run, ai-pipeline, watchdog) and what each may do. Update the vault flow chart
  `agents-flow.md` for R3 and R1.

## Non-goals
Automated plan loop (E2), browser tests (B4), orchestrator, usage reserve; refactors.

## Acceptance
Each requirement covered by tests in `tests/test_workflow.py` (mock claude/codex), including
the family-run scenario for R1 (triage commit denied → stop → recovery → resume counts the
round and enforces scope). `.ai/validate` passes.
