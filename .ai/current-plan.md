# Plan: Flow batch 10: FL-39, TS-01 (1)(2), ME-01 parts 1 and 2

## Assessment (verified at 4fea72d, 2026-10-21)
Details and line references: `.ai/project-spec.md` "Verified against the code". In short:
- The plan review gate (`ai-pipeline` ~478) uses `tasks untouched` (no DONE task at all), so any
  queue that keeps earlier batches' DONE tasks skips the plan review silently. `tasks newly-done
  REV` already exists.
- The worker default is `min(8, cpu)`; on this 16-core host 14 workers is the expected best
  (mission control measures 8/12/14 before the run).
- Every runner session is told to run the ~13-minute full gate itself, and the host runs it again
  after the session. Last night's three timeouts (T108, T109, T111) were finished tasks that ran
  out of session time during their own gate. The FL-28 allowance (2 × gate) only partly covers it.
- The host already records task and review outcomes (`outcomes.jsonl`) and a bare `gate` row; it
  records nothing about stops, recovery decisions, rulings, routing reasons, PRs or run totals.
- CU-1 and CU-5 are already done in code (spec); OR-04 and BR-17 stay later.

## Design

### FL-39: plan review against the run's base (T201)
`ai-pipeline` replaces `ai_helper tasks untouched` with a local `plan_untouched` check: the queue
has tasks and `ai_helper tasks newly-done "$base_sha"` prints nothing (a helper error counts as
"not untouched" and prints the skip line with the error, so a broken helper never runs a review
on a started queue). Armed resume and `--skip-plan-review` keep skipping; every skip prints one
`Plan review skipped: …` line (stdout, so it reaches the pipeline log). The loop's "already
current and not revised" check stays, so a resumed run with a current plan review does not repeat
it. `tasks untouched` stays as a helper (other callers and old tests).

### TS-01 (1): worker default (T202)
`worker_count()` returns `(count, source)`; default `max(1, min(14, (cpu or 1) - 2))` (or the
measured value in the handoff, A1); `main()` prints `Workers: …` first. Unit tests import the
module and patch `os.cpu_count` and the environment.

### TS-01 (2): session gate mode (T203, T204, T205)
- T203 helper `workflow.py session-gate`: reads `AI_SESSION_GATE` (`auto|full|targeted`, empty =
  auto) and `gate-seconds`'s value (shared function, not a subprocess); prints `MODE SECONDS`;
  never fails (`targeted 0` on any error, an invalid setting is caught earlier by the validators).
  The setting joins `RUN_SETTINGS`, the `ai_config` key list, both `ai-recover` lists and a
  validator in `scripts/lib/common.sh` next to the routing ones (used by `ai-run` and
  `ai-pipeline`).
- T204 `ai-run`: before the task session, `read -r gate_mode gate_secs < <(ai_helper
  session-gate)`; `claude_session` computes the allowance only in `full` mode; the RUNNER CONTRACT
  gets one of two gate sentences (A5) and the `Session:` line shows `gate rule: targeted` or the
  current allowance breakdown. Tests drive `ai-run` with the mock `claude` used by the existing
  `test_fresh_retry_*` tests and read the captured prompt and the `Session:` line.
- T205 templates: `runner.md`, `triage.md`, `fix-review.md` "How to work here"/loop text says the
  gate rule comes from the RUNNER CONTRACT (targeted checks by default; the host's full gate
  decides); keep the background-run instructions for the `full` case. `templates/CLAUDE.md` step 4
  gets "(an unattended runner session follows the RUNNER CONTRACT's gate rule)". The shared
  "How to work here" blocks stay identical where a test compares them.

### ME-01 part 1: event log (T206–T210)
- T206 core in `scripts/lib/workflow.py`: `events_path()` (= `state_root()/events.jsonl`),
  `EVENT_KINDS` (kind → allowed fields with types), `append_event(kind, fields)` (validates,
  adds `v`, `id`, `time`, `project`, `branch`, `run`; rotation A9 under the lock; uses the
  `append_outcome` write pattern), `read_events(paths=None)` (both files, dedupe by id, skip
  non-dict, unknown `v` or kind), `redact(text, limit=200)`, CLI `event KIND key=value…`
  (values typed per schema; unknown kind/field → exit 2 with usage; write failure → `Note:` on
  stderr, exit 1, callers use `|| true`). `run-manifest start` adds `run_id`/`started`;
  `run-manifest run-id` reads it. `ai_event` wrapper in `common.sh`
  (`ai_helper event "$@" 2>/dev/null || printf 'Note: could not record the %s event.\n' "$1" >&2`).
- T207 `gate`: `record_gate` in `ai-run` gets a third argument (task id or stage `final`/`retry`)
  and calls `ai_helper event gate-from-stamp …`-style subcommand (`event gate --from-log` reading
  the stamp's log path, A12); `ensure_validated` in `ai-pipeline` and the `ai-recover`
  commit_and_rerun gate record a gate event too (stage `validation`/`recovery`).
- T208 `stop` and `recovery`: `stop-category STAGE` helper (fixed table A10); `ai-pipeline
  stop()` writes `stop` (stage, category, message excerpt, `handed_to_recovery` yes/no) before the
  `exec`; `ai-recover` writes `recovery` at each decision and `stop` at `escalate`.
- T209 `run` and `pr`: `run start`/`resume` after the manifest step (~163), `run end` at the PR
  record and at terminal stops (the shared stop/escalate paths from T208) with totals; `pr` after
  `gh pr create` and the draft/ready calls.
- T210 `ruling` and `review`: `ai_ruling_rows` emits one `ruling` per row (kind, key, task when
  the key names one); `ai-review` emits `review` with mode, reviewer (`codex|claude|claude-routed|
  claude-fallback`), model and the routing reason.

### ME-01 part 2: metrics (T211, T212)
- T211 `workflow.py metrics [--since DATE] [--project NAME] [--json]` builds the data (A13) from
  `read_outcomes` + `read_events` into a dict `{"v": 1, "projects": [...], "runs": [...]}` and
  prints it with `--json`.
- T212 the plain-text tables (projects, then runs; no `|` inside cells: Markdown-free aligned
  columns) and `ai-status --metrics …` (usage line, argument pass-through, `ai-status` help).

### Docs (T213)
README and `docs/workflow.md` sections "Flow data (events.jsonl)" and "Reading the metrics";
vault flow chart and handoff audit. Flow-changing tasks (T201, T204, T206/T208 for the new
records under "When something goes wrong") update the chart themselves; T213 checks.

## Affected components
`scripts/ai-pipeline`, `scripts/ai-run`, `scripts/ai-recover`, `scripts/ai-review`,
`scripts/ai-status`, `scripts/lib/workflow.py`, `scripts/lib/common.sh`, `tests/run_parallel.py`,
`tests/test_workflow.py` (and a new `tests/test_events.py` for the event core and metrics, to keep
the huge file from growing), `templates/.ai/prompts/{runner,triage,fix-review}.md`,
`templates/CLAUDE.md`, README.md, docs/workflow.md, vault `agents-flow.md` (+ hub Log lines).

## Phases and order
T201 (FL-39, opus) → T202 (workers, sonnet) → T203 (session-gate helper and setting, opus) →
T204 (ai-run contract and allowance, opus) → T205 (templates, sonnet) → T206 (event core, opus)
→ T207 (gate events, sonnet) → T208 (stop and recovery events, opus) → T209 (run and pr events,
sonnet) → T210 (ruling and review events, sonnet) → T211 (metrics data, sonnet) → T212 (metrics
text and ai-status flag, sonnet) → T213 (docs audit, haiku).
Thirteen tasks rather than 7–10: each must fit about 10–15 minutes of a 30-minute session that
also waits for the ~13-minute host gate.

## Risks
- Sessions that skip the full gate leave more failures for the host gate, which sets the task
  back to IN_PROGRESS; the next attempt gets the failure note (BR-03). Acceptable: the gate ran
  twice per task before.
- A fast-gate project whose gate slows down switches to `targeted` automatically (last 3 passes).
- An event write must never change a run: every writer is `|| true` with a `Note:`; tests assert
  an unwritable state dir leaves the run's exit status and output unchanged except the note.
- Stop categories from text can be wrong; telemetry only, never read by recovery (A10).
- Rotation copies the current run's lines; a reader must dedupe by id (tested).
- FL-39: a helper failure must not trigger a review on a started queue (fails closed to skip with
  a line).
- This repo's own run still uses the frozen `.ai/bin` (FL-39 present: Zack runs the plan review
  by hand, see the handoff) and frozen prompts (BATCH 10 GATE RULE in the queue header).

## Validation strategy
Every task: its targeted `python3 -m unittest discover -s tests -k <group>` commands (must say
`Ran N tests`, N ≥ 1) and `bash -n` on changed shell scripts, in the session. The full gate is the
host's post-task `ai-check` (BATCH 10 GATE RULE in the queue header). No profiling commands.
