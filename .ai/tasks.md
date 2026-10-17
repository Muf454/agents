# Task queue

Edit `scripts/`, `templates/`, `tests/`, `README.md` and `docs/` only (plus the vault flow chart
and hub Log line where a task says so). Never edit `.ai/bin`, `.ai/prompts`, `.ai/validate`,
`.ai/ci-setup`, `.ai/permissions.allow`, `.claude/settings.json` or `.github/workflows/*`
(gate files; needed gate changes are human steps in `.ai/handoff.md`). Vault: a task that
changes the flow updates `~/zWiki/zWiki/20 Projects/agents/agents-flow.md` and its `updated:`
date in the same task and appends a dated line to the Log of `agents.md`; never tick vault
checkboxes. If the vault edit is denied, record it in the result and in the handoff's
"## Flow chart" section.
Source: vault `agents-backlog.md` (FL-16, CU-5, R13), planned 2026-10-17 on `fix/flow-batch-5`
(from `fix/flow-batch-4` at df0d3c2, PR #29 not merged). Already done and not planned: FL-01,
FL-07, FL-09, FL-11, FL-14, FL-15, FL-17, FL-18, FL-19, FL-22, FL-24, DB-02, DB-03, DB-05 and
the triage half of FL-16 (evidence in `.ai/project-spec.md`).
Line references are at df0d3c2 and verified by the planner; re-check them before editing.
Every behaviour change gets an offline regression test in the existing style; every task
leaves `.ai/bin/ai-check` passing and updates README.md / `docs/workflow.md` where the
behaviour it changes is described.
Gate note: `.ai/validate` runs the shell syntax checks and then `tests/run_parallel.py`
(about 6–7 min), inside the 600 s Bash tool limit. Should `.ai/bin/ai-check` still time out in
the session, run the task's targeted tests, record the timeout in the result, and leave the
full gate to the host's post-task `ai-check`. Tests with time bounds run in parallel: assert
"returns within N s" with generous bounds scaled by `tests/timeouts.py`, never a tight
duration. No profiling commands (denied). Test helper scripts written into temp dirs use
`os.chmod` from Python.

## T001 — Finding cells accept a severity suffix and a title in both disposition tables (FL-16)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
A plan-revision or triage row whose first cell reads `P1 (MAJOR) selection highlight…` or
`M1 — title` is read as the row for that finding instead of stopping the run, and a row that
still does not match says which line was wrong and what to write.

### Implementation notes
- `scripts/lib/workflow.py` (~985–996): new string constant `FINDING_CELL` with exactly one
  capturing group (the ID `[A-Z][A-Z0-9]{0,4}-?\d+`); the severity suffix
  `(?:[ \t]*\((?:BLOCKER|MAJOR|MINOR)\))?` and the title text are non-capturing. Title text:
  a separator (whitespace, or `:` right after the ID/suffix; a `—`, `–` or `-` only after
  whitespace or the suffix), then text that does not start with `(` built from the `TABLE_CELL`
  alternation `(?:\\.|[^\\|\n])` (no unescaped `|`, no newline). Comment the rule and why
  (FL-16: sessions write `ID (SEVERITY) title`; a row only ever counts for its first ID).
- Use it in `DISPOSITION_ROW` (~995) and `PLAN_DISPOSITION_ROW` (~2445–2447) so that groups
  1–4 (ID, disposition, evidence, task) are unchanged; flags stay `re.M | re.I`. Readers at
  ~1036, ~1112, ~1555, ~2483, ~2624, ~3386 need no change; check each still gets the right group.
- `unmatched_cell_hint(text, finding)`: for the first line starting with `|` whose first cell
  contains `finding` as a word (`\b…\b`) and which is not a matched row, return
  ` (the row starting "| <first cell, max 60 chars> |" does not match; write "| <finding> | <disposition> | <evidence> | <task> |")`,
  else `''`. Append it to `MAJOR/BLOCKER finding X has no disposition.` (triage_check ~1042) and
  `Finding X has no row in the round N section.` (~2633), after the existing text (the
  existing prefixes stay, so tests that `assertIn` them keep passing).
- `docs/workflow.md` (~462: "The finding cell may carry a severity suffix (`M1 (MAJOR)`); other
  decorations do not match."): state the new rule for both tables. Flow unchanged.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, docs/workflow.md

### Acceptance criteria
- Tests named `test_finding_cell_*` in tests/test_workflow.py:
  - `plan-dispositions-check` (fixture as in `test_disposition_pipes_plan_dispositions_read_the_task_cell`)
    passes with first cells `P1 (MAJOR)`, `P1(major)`, `P1 (MAJOR) selection highlight is lost`,
    `P1 — title`, `P1: title`, `P1 title`, and counts the row as accepted with the right task;
  - `triage-check --fresh` (fixture as in `test_triage_severity_suffix_satisfies_triage_check`)
    passes with `M1 (MAJOR) title text`, `M1 — title`, `M1: title`;
  - still unmatched in both tables (the check fails with the existing "has no disposition" /
    "has no row" text): `**M1**`, `M1 (CRITICAL)`, `M1 (CRITICAL) x`, `M1,M2`, `M1/M2`, `M1x`;
    and the failure message quotes the offending first cell and contains `write "| M1 |`;
  - a unit case on the compiled regexes: title text containing `\|` stays in the ID cell
    (evidence and task cells read correctly), and an ID `SEC-12` with title `- fix` reads `SEC-12`;
  - a row `| M1 (MAJOR) about M2 | accepted | … | T001 |` counts for M1 only: a MAJOR M2 without
    its own row still fails.
- `test_triage_severity_suffix_other_decorations_stay_unmatched` changed on purpose: `M1 (MAJOR) x`
  moves to the matched cases (named in the result); its other cases stay.
- All other existing tests pass unchanged (`test_disposition_pipes_*`, `test_triage_severity_suffix_*`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k finding_cell` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k triage_severity_suffix` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k disposition_pipes` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T002 — Prompts and host contracts show the exact disposition row (FL-16, prompts)
Status: TODO
Dependencies: T001
Model: haiku

### Goal
Triage and plan-revision sessions see one example row of their table, so T001's tolerance is
rarely needed.

### Implementation notes
- `templates/.ai/prompts/triage.md` (~13–15): after "the bare finding ID, e.g. `M1`" add the
  row example `| M1 | accepted | <evidence> | T012 |` and "the ID alone in the first cell (no
  severity or title; the runner tolerates them, nothing before the ID)".
- `templates/.ai/prompts/plan-revision.md` (~29–31): the same for
  `| P1 | accepted | <evidence> | T012 |` (Task cell empty for rejected / needs-human rows,
  as the preamble comment says).
- `scripts/ai-run` REVISION CONTRACT (~415–427) and TRIAGE CONTRACT (~523): one clause each:
  `one row per finding, e.g. "| P1 | accepted | evidence | T012 |" with the finding ID alone in
  the first cell` (`M1` for triage). Keep the existing sentences.
- Host-written comments: `start_dispositions` (workflow.py ~1011–1014) and
  `PLAN_DISPOSITIONS_PREAMBLE` (~2492–2499): the same example row.
- Keep the shared "## How to work here" block identical in runner/triage
  (`test_tool_contract_section_is_shared_by_prompts`); this task does not touch it.
- Never edit `.ai/prompts` (installed copy; the handoff lists the upgrade). Flow unchanged.

### Likely affected modules
templates/.ai/prompts/triage.md, templates/.ai/prompts/plan-revision.md, scripts/ai-run,
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Test `test_finding_cell_prompts_show_the_row` in tests/test_workflow.py: triage.md contains
  `| M1 | accepted |`, plan-revision.md contains `| P1 | accepted |`; the triage prompt and the
  revision prompt recorded by the mock claude in an existing triage / supervised revision test
  contain `ID alone in the first cell`; a fresh `start-dispositions` file contains `| M1 | accepted |`.
- `test_tool_contract_section_is_shared_by_prompts` and all other existing tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k finding_cell` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k tool_contract` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T003 — Outcome helper: durable attempt marker, idempotent crash reconcile, torn-line-safe append (CU-5, part 1)
Status: TODO
Dependencies: none
Model: opus

### Goal
The host can record that an implementation attempt is open, and a later start turns an
attempt whose runner died without its exit handler into exactly one `crashed` outcome line,
without ever losing or duplicating a line.

### Implementation notes
- Design: `.ai/current-plan.md` "CU-5 — attempt marker + reconcile". `scripts/lib/workflow.py`,
  next to `outcome()` (~3029–3082). Marker path `binding_dir() / 'attempt.json'`
  (`binding_dir` ~1247; it runs `check_state_root`).
- `outcome attempt-open TASK MODEL PID`: first reconcile any leftover marker (same function as
  below), then write `{"id": secrets.token_hex(8), "task", "model", "project", "branch",
  "started": int(time.time()), "pid": PID, "pid_start": <field 22 of /proc/PID/stat or null>}`
  via a temp file in the same directory, `os.fsync`, `os.replace`, then fsync the directory
  (`os.open(dir, O_RDONLY)`). Print the id. Read `/proc/PID/stat` as bytes and split after the
  last `)` (comm can hold spaces, parentheses, non-UTF-8: see `tests/run_parallel.py`
  `parse_stat`).
- `outcome task TASK RESULT MODEL SECONDS [--attempt ID]`: the record gets `attempt_id` when
  given; after the append, unlink the marker only if its `id` equals ID (fsync the directory).
  A marker with another id is left alone.
- Append (every kind, one helper `append_outcome(path, record)`): `os.open(path,
  O_WRONLY|O_APPEND|O_CREAT, 0o644)`; if the file is non-empty and its last byte is not `\n`
  (`os.pread` of the last byte), prefix the line with `\n`; ONE `os.write` of prefix + line;
  `os.fsync`; close. Comment why (a torn last line from a killed writer must not swallow the next
  record; `read_outcomes` skips the fragment).
- `outcome attempt-reconcile`: no marker → silent exit 0. Unreadable or invalid marker → unlink,
  stderr `Note: discarded an unreadable attempt marker.`. Runner alive (pid exists and its
  current start time equals `pid_start`; `pid_start` null → pid exists) → leave it, silent.
  Otherwise: if any task record in the log has `attempt_id == id` → only unlink. Else append a
  task record with `result: "crashed"`, task/model/project/branch from the marker (not the
  current branch), `seconds: null`, `attempt` numbered as `outcome task` does, `first_pass:
  false`, `attempt_id`, and title/category as today; then unlink. stderr `Note: logged a crashed
  attempt of <task> (the runner was killed without its exit handler).` Never raises: any
  `OSError`/`ValueError` → stderr note, exit 0.
- `outcome attempt-path`: prints the marker path (for T004's `on_exit`).
- `outcomes_report` (~3085): check `crashed` rows with `seconds: null` are counted as not done
  and add 0 minutes (it uses `r.get('seconds') or 0`); the per-model attempts table counts them.
- Concurrency: called only by `ai-run` under the checkout lock; the log is shared by all
  checkouts (one `write` per line on `O_APPEND`). No new lock.
- No `scripts/ai-run` change here (T004). Docs are T004's.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_outcome_attempt_*` in tests/test_workflow.py (helper level, with
  `AI_STATE_DIR` in the test's temp dir as the existing outcome tests do):
  - open → marker exists with a 16-hex id that the command printed; `outcome task T001 done m 5
    --attempt <id>` → one line with `attempt_id`, marker gone; reconcile → nothing appended;
  - dead runner (marker written with the pid of a finished child process): reconcile appends one
    `crashed` line (task, model, branch from the marker, `seconds` null, `attempt` 1), unlinks,
    prints the note; a second reconcile appends nothing; a later `outcome task … done` for the
    same task gets `attempt` 2;
  - crash between append and unlink (a line with the marker's `attempt_id` already in the log,
    marker still there): reconcile appends nothing and unlinks;
  - live runner (marker with the test process's own pid and start time): left in place, nothing
    appended; same pid with a different `pid_start` → reconciled as dead;
  - a garbage marker → unlinked with the note, exit 0, nothing appended;
  - torn tail: the log ends with `{"time": "x", "kin` (no newline); the next `outcome` append
    starts on a new line and `read_outcomes` returns the new record (and not the fragment);
  - `outcome task --attempt X` with a marker of another id leaves the marker;
  - `ai-status --outcomes` on a log with a `crashed` row (seconds null) renders without error
    and counts it as not done.
- All existing `outcome` tests pass unchanged (`-k outcome`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_attempt` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T004 — `ai-run` opens, closes and reconciles task attempts; a SIGKILLed runner's attempt is logged at the next start (CU-5, part 2)
Status: TODO
Dependencies: T003
Model: opus

### Goal
A runner killed by SIGKILL during a task session leaves an attempt that the next
`ai-run --approved` start logs as `crashed`, once; normal stops behave exactly as today.

### Implementation notes
- `scripts/ai-run`: after `ai_lock` (~111) and once the approved gate is verified (the first
  point where other `ai_helper` calls are trusted; check the order), in every `--approved` mode:
  `attempt_marker=$(ai_helper outcome attempt-path 2>/dev/null) || attempt_marker=` and
  `ai_helper outcome attempt-reconcile || true`. Not in `--plan` mode (no attempts there).
- Attempt open (~262–267, inside `claude_session` where `attempt_open=yes` is set):
  `attempt_id=$(ai_helper outcome attempt-open "$active_task" "${task_model:-$model}" "$$" 2>/dev/null) || attempt_id=`
  before `attempt_open=yes` (a limit retry stays in the same attempt, as today).
- `task_outcome` (~208–212): pass `--attempt "$attempt_id"` when set, then clear `attempt_id`.
- `on_exit` (~169–196): when `attempt_open == yes` and `gate_ok == no` (no helper may run),
  `[[ -z "$attempt_marker" ]] || rm -f -- "$attempt_marker"` with a comment (a deliberate
  no-log stop must not be reported as a crash later).
- Mock claude (tests/test_workflow.py mock modes): `sigkill-runner` finds the `ai-run` process
  by walking `/proc/<pid>/stat` ppids from the mock upward to the first `bash` whose
  `/proc/<pid>/cmdline` contains `ai-run`, writes its pid to a file in the test base dir, sends
  it SIGKILL and exits. The test SIGKILLs every pid it recorded (and the `timeout` parent) in
  `addCleanup`.
- Docs: README "Outcome log" and `docs/workflow.md` outcome section: a killed runner's attempt
  is logged as `crashed` (seconds unknown) at the next `ai-run --approved` start; limits
  (only implementation attempts; a checkout never started again keeps its marker).
- Vault (flow change in a described step): `agents-flow.md` "Outcome log" bullet (~147) gains
  "an attempt whose runner was killed is logged as crashed at the next start"; `updated:`
  bumped; hub Log line.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md and
agents.md (Log)

### Acceptance criteria
- Tests named `test_outcome_crash_*` in tests/test_workflow.py:
  - `ai-run --approved` with `MOCK_CLAUDE=sigkill-runner`: the runner dies (exit -9 / 137), the
    outcome log has no line for the task and the marker exists; a second `ai-run --approved`
    (mock mode that implements and checkpoints the task) logs `crashed` (attempt 1,
    `attempt_id` = the marker's id, `seconds` null) then `done` (attempt 2, its own
    `attempt_id`), and the marker is gone; a third start appends nothing;
  - the existing interrupted/timeout/error outcome paths (e.g. `test_runner_logs_task_outcomes_and_report`
    and the session-timeout outcome tests) log exactly what they did before, now with
    `attempt_id`, and leave no marker;
  - a gate-changing session (existing gate-change mock mode): no outcome line (as today) and no
    marker afterwards, and the next start logs nothing for it.
- All existing tests pass unchanged; the vault flow chart and hub Log are updated (or the
  denial is recorded in the result and the handoff).

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_crash` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T005 — Recovery reasons and plan questions are cut at a sentence or word boundary; the full text is kept (R13)
Status: TODO
Dependencies: none
Model: sonnet

### Goal
A ⛔ notification never ends mid-word; when the recovery reason or human action was shortened,
the full text is in `.ai/local/recovery-decision.txt` and the notification says so.

### Implementation notes
- `scripts/lib/workflow.py`: `shorten(text, cap)`: whitespace collapsed; ≤ cap → unchanged;
  else cut to the longest prefix within `cap - 1` characters that ends at a sentence end (`.`,
  `!` or `?` followed by a space in the original) if that prefix is at least `cap // 2` long,
  else at the last space, else hard; strip trailing space and append `…` (total ≤ cap).
- `recover_decision` (~2000–2060; `clean` at ~2006): use `shorten(…, 300)` for the reason and
  human action, keeping tabs out as today. At the start of every call remove a stale
  `.ai/local/recovery-decision.txt` (missing is fine); when either value was cut, write
  `reason: <full>\nhuman_action: <full>\n` (collapsed, each at most 4000 characters) with
  `atomic`. Output stays three tab-separated fields; envelope failures unchanged.
- `scripts/ai-recover` `escalate` (~37–42): when `.ai/local/recovery-decision.txt` exists,
  append ` Full text: .ai/local/recovery-decision.txt` to the ⛔ notification. `last-error`
  keeps the original stop reason (unchanged).
- `bounded_questions` (~2564–2569): `shorten(…, QUESTION_CAP)` instead of `[:QUESTION_CAP]` (no
  file: the pointer line already names `plan-dispositions.md`).
- README (Auto-recovery) and `docs/workflow.md` (recovery decision, needs-human questions): one
  sentence each. Vault: if the notifications section of `agents-flow.md` states the
  300-character cut, update it (`updated:` + hub Log line); else "flow unchanged" in the result.

### Likely affected modules
scripts/lib/workflow.py, scripts/ai-recover, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_recovery_reason_shorten_*` in tests/test_workflow.py:
  - unit cases on `shorten`: a 400-character text of sentences ends with `.…` at a sentence end
    within 300 characters; one long sentence ends at a word boundary plus `…`; a single 400-char
    word is hard-cut to 299 + `…`; a short text is unchanged;
  - `recover-decision` on an envelope whose decision reason is 600 characters: the reason field
    ends with `…`, has no tab, ≤ 300 characters, and `.ai/local/recovery-decision.txt` holds the
    full reason; a short decision leaves no file (and removes a stale one);
  - the `prose-only` excerpt path (T008 of PR #29) still starts with `the recovery session gave
    no valid decision; it wrote:` and stays ≤ 300 characters;
  - an end-to-end `ai-recover` escalation with a long mock reason (extend an existing
    `MOCK_RECOVER` mode, e.g. `escalate-long`): the recorded ⛔ notification ends with
    `Full text: .ai/local/recovery-decision.txt` and no word is cut before the `…`;
  - `bounded_questions` with a 400-character question ends with `…` at a word boundary.
- `test_recovery_decision_*` and all other existing tests pass (any test that asserted a hard
  300-character cut is updated on purpose and named in the result).

### Validation
Targeted: `python3 -m unittest discover -s tests -k recovery_reason_shorten` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes


## T006 — Docs, handoff and final audit for the batch
Status: TODO
Dependencies: T001, T002, T003, T004, T005
Model: haiku

### Goal
README, `docs/workflow.md`, the vault flow chart and the handoff describe what the code now
does; the human knows which upgrade, vault and backlog steps remain.

### Implementation notes
- Check each sentence the tasks added (README, `docs/workflow.md`) against the code once:
  finding cells (T001/T002), attempt marker and `crashed` outcomes (T003/T004), boundary cut
  and `recovery-decision.txt` (T005). Fix contradictions; no new behaviour.
- Vault: confirm `agents-flow.md` reflects T004 (and T005 if it changed the chart) with a
  current `updated:`; hub Log has one dated line per flow-changing task. Append one hub Log
  line: "flow batch 5 planner found FL-01, FL-07, FL-09, FL-11, FL-14, FL-15, FL-17, FL-18,
  FL-19, FL-22, FL-24, DB-02, DB-03, DB-05 and the triage half of FL-16 already done
  (2026-10-17)". Never tick checkboxes.
- `.ai/handoff.md`: "## Flow chart" says `Flow chart updated` (or lists what is pending);
  "Manual testing for the human" (`### Needs you` / `### Covered by automated tests` naming
  every new test group below); "Human todos" kept current.

### Likely affected modules
README.md, docs/workflow.md, .ai/handoff.md, vault agents-flow.md and agents.md (Log)

### Acceptance criteria
- `DocsConsistencyTest` passes; README mentions `crashed` outcomes and
  `.ai/local/recovery-decision.txt`; `docs/workflow.md` states the finding-cell rule for both
  tables.
- `test_pr_body_flow_this_repo_declares_the_flow_chart` passes.
- The handoff names `test_finding_cell_*`, `test_outcome_attempt_*`, `test_outcome_crash_*` and
  `test_recovery_reason_shorten_*` under "Covered by automated tests", and every group exists
  (`python3 -m unittest discover -s tests -k <group>` runs ≥ 1 test each).

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes

