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
Status: DONE
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
  contains `finding` not preceded by `[A-Za-z0-9-]` and not followed by a digit
  (`(?<![A-Za-z0-9-])` + `re.escape(finding)` + `(?!\d)`, diagnostic only, so glued text such as
  `M1x` or `**M1**` is found while `M10`/`XM1` are not; those rows stay rejected) and which is
  not a matched row, return
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
Added `FINDING_CELL`, used by `DISPOSITION_ROW` and `PLAN_DISPOSITION_ROW`, and
`unmatched_cell_hint` appended to both "no disposition"/"no row" failures. Tests
`test_finding_cell_*` (6) added; `test_triage_severity_suffix_other_decorations_stay_unmatched`
changed on purpose: `M1 (MAJOR) x` moved to the matched cases
(`test_finding_cell_triage_accepts_suffix_and_title`). docs/workflow.md updated. Targeted
`finding_cell` (6), `triage_severity_suffix` (3), `disposition_pipes` (9) pass; `.ai/bin/ai-check`: 752 tests OK.


## T002 — Prompts and host contracts show the exact disposition row (FL-16, prompts)
Status: DONE
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
Triage and plan-revision prompts (`templates/.ai/prompts/triage.md`, `plan-revision.md`) show
the ID-alone row `| M1 | accepted | <evidence> | T012 |` / `| P1 | …`, with "the finding ID alone in
the first cell". `scripts/ai-run` TRIAGE and REVISION CONTRACTs and the host comments
(`start_dispositions`, `PLAN_DISPOSITIONS_PREAMBLE`) carry the same example, mid-line so the
row regex (line-anchored) never reads it as a row. Shared "How to work here" block untouched.
Test: `test_finding_cell_prompts_show_the_row` (new); the triage test
`test_task_sections_host_triage_adds_the_missing_sections` and `test_revise_plan_accept_commits_once_and_leaves_a_clean_checkout`
assert the phrase in the recorded prompts.
Test-side change, on purpose: the mock triage in `tests/test_workflow.py` decided "rows already
recorded" with `'| M1 |' in dispositions`; the example in a fresh file made it skip writing M1
(broke `test_observation_pipeline_extra_fix_round_detail`, `test_extra_fix_round_flat_counts_*`).
It now matches a row line: `re.search(r'^\| M1 \|', …, re.M)`.
Evidence: `-k finding_cell` 7 OK; `-k tool_contract` 3 OK; `.ai/bin/ai-check` 753 tests OK (387.3 s).
Limitation: the installed `.ai/prompts` copy changes only after `setup-project --upgrade --apply` (handoff).


## T007 — Outcome log I/O: readable append descriptor, complete-write check, per-line UTF-8 reader (CU-5, part 0)
Status: DONE
Dependencies: none
Model: opus

### Goal
Every outcome line is appended through one helper that can read the log's last byte, never
reports a partial write as success, and the reader keeps every valid record even when the log
ends in a torn line cut inside a multibyte UTF-8 character. (Plan review round 1, P1–P3.)

### Implementation notes
- Design: `.ai/current-plan.md` "CU-5 — attempt marker + reconcile", "Log I/O". In
  `scripts/lib/workflow.py`, next to `read_outcomes` (~2984).
- `append_outcome(path, record) -> bool`: `path.parent.mkdir(parents=True, exist_ok=True)`;
  `fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)` (READ-write: `os.pread` on
  an `O_WRONLY` descriptor raises EBADF, P1); in `try/finally: os.close(fd)`: size from
  `os.fstat(fd).st_size`; prefix `b'\n'` when `size > 0` and `os.pread(fd, 1, size - 1) != b'\n'`;
  `data = prefix + (json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n').encode()`;
  `written = os.write(fd, data)` (ONE call); `if written != len(data): return False` (no retry
  of the remainder: another checkout may have appended in between; the next append's newline
  guard isolates the fragment); `os.fsync(fd)`; return True. OSError propagates to the caller.
  Comment the three rules (readable fd for the guard, short write is a failure, why no retry).
- `outcome()` (~3080–3082) uses it for every kind instead of `path.open('a')`: on `False` or
  `OSError` → `fail('Could not append the outcome line completely: <path>.')` (exit 1, as an
  OSError exits non-zero today; `ai-run` ~210 and `ai-review` ~280 already treat a failed
  `outcome` call as best-effort, check both).
- `read_outcomes` (~2984–3000): read bytes (`Path(path).read_bytes()`, OSError → skip the
  file as today), split on `b'\n'` only, decode each line with strict `'utf-8'`; a
  `UnicodeDecodeError` or JSON `ValueError` skips that line only (P2). `_at` keeps the line
  index of the split. Comment why (a torn tail can end inside a multibyte character; the old
  whole-file `read_text()` raised before any line was parsed; `str.splitlines` also split on
  U+2028 inside `ensure_ascii=False` records).
- No marker, no `ai-run` change here (T003/T004). The cross-checkout lock and the directory
  sync of `append_outcome` are T008's (plan review round 2, P7/P8); write T007 so T008 only
  adds them. Factor the per-line decoding into `decode_outcome_lines(data: bytes) -> list[dict]`
  (line index kept) so T009's strict reader and `confirm_recorded` reuse it.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_outcome_log_io_*` in tests/test_workflow.py (with `AI_STATE_DIR` in the
  test's temp dir as the existing outcome tests do; unit cases import the module as other unit
  tests do):
  - two `outcome review …` (or `task`) calls on an empty log, then a third: three records read
    back (regression for P1: appending to a non-empty log succeeds);
  - non-empty log WITHOUT a final newline (`{"time": "x", "kin`): the next append starts on a
    new line, `read_outcomes` returns the earlier valid records and the new one, not the fragment;
    same with a log WITH its final newline: no empty line inserted;
  - torn multibyte tail: a valid record line, then the bytes `{"title": "caf\xc3` (no newline):
    `read_outcomes` returns the earlier record (no exception), a following append is readable,
    and `ai-status --outcomes` renders;
  - a record whose title contains U+2028 reads back as one record;
  - short write (unit, `os.write` patched to write the first half of `data` for real and return
    that count): `append_outcome` returns False and does not fsync; the `outcome` command exits 1
    with `Could not append the outcome line completely`; a following real append is readable and
    the fragment is skipped.
- All existing `outcome` tests pass unchanged (`-k outcome`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_log_io` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-17: `append_outcome` (O_RDWR|O_APPEND|O_CREAT, pread newline guard, one write, short
write → False without fsync, no retry) and `decode_outcome_lines` (split on b'\n', strict
per-line UTF-8, line index kept) in `scripts/lib/workflow.py`; `read_outcomes` uses it;
`outcome` appends through `append_outcome` and fails `Could not append the outcome line
completely: <path>.` (exit 1) on False/OSError; `ai-run`/`ai-review` already ignore a failed
`outcome` call (`|| printf 'Note: …'`). Five `test_outcome_log_io_*` tests (non-empty append,
torn line with/without final newline, torn multibyte tail + `ai-status --outcomes`, U+2028
title, short write unit + CLI exit 1 via runpy). `-k outcome_log_io` Ran 5 OK; `-k outcome`
Ran 28 OK; `.ai/bin/ai-check` PASS (758 tests). `docs/workflow.md` "Outcome log" describes it.
No lock or directory fsync (T008).


## T008 — CU-5 write protocol: locked append with directory sync, one marker file per attempt (CU-5, part 0b)
Status: DONE
Dependencies: T007
Model: opus

### Goal
The outcome append is framed safely against every other `append_outcome` writer on the host
and its new directory entries survive a power loss before any marker is removed; attempt
markers live one file per attempt and are never overwritten, so an attempt whose outcome could
not be appended stays recoverable while the same runner opens further attempts. (Plan review
round 2, P6–P8; design note `.ai/current-plan.md` "CU-5 write protocol (round 2 redesign)".)

### Implementation notes
- `append_outcome` (T007, `scripts/lib/workflow.py`), new order, all on the one
  `O_RDWR|O_APPEND|O_CREAT` descriptor: before `mkdir`, collect the ancestors of `path.parent`
  that do not exist yet; `mkdir(parents=True, exist_ok=True)`; open; `fcntl.flock(fd,
  LOCK_EX)` (blocking; released by `os.close` in the `finally`); THEN `fstat`, `pread` the last
  byte, build `data`, one `os.write`, the short-write check, `os.fsync(fd)`; then
  `fsync_dir(path.parent)` and, for each ancestor created above (deepest first), `fsync_dir`
  of its parent; only then return True. `fsync_dir(d)`: `os.open(d, O_RDONLY | O_DIRECTORY)`,
  `os.fsync`, close. The log's directory is synced on every append (one cheap fsync; no
  race over who created the file). An `OSError` from any sync propagates like other OSErrors
  (the `outcome` command fails, the marker is kept, T003). Comment: the lock makes "tail check
  then write" one step for every writer using this helper (P7); a file fsync does not persist a
  new directory entry (P8).
- Known limit (comment + plan Risks): an older installed copy (`path.open('a')`, no lock) in
  another checkout can still interleave until `setup-project --upgrade`; its buffered write
  only leaves a partial line on a crash or a full disk.
- Marker store (used by T003): `attempts_dir() = binding_dir() / 'attempts'`;
  `write_marker(record)`: create the dir (fsync the parent dirs of every created dir as above),
  write `<id>.json.tmp` (`O_WRONLY|O_CREAT|O_EXCL`, 0o600), fsync, `os.link` to `<id>.json`
  (fails if it exists: never overwrites; on `FileExistsError` raise), unlink the tmp, fsync the
  dir; `list_markers()`: `*.json` files sorted by (`started`, name), each `(path, record or None)`
  (invalid content → None; T010 refines this into a three-way classification that keeps a
  read error apart from invalid content, so write the reader so that T010 only adds the third
  case; T012 adds the marker field `seq` and sorts by (`seq`, name), so keep the sort key in
  one place); `remove_marker(path)`: unlink (missing is fine), fsync the dir.
  Ids are `secrets.token_hex(8)` and validated `^[0-9a-f]{16}$` before use in a file name.
- `outcome attempt-dir` prints `attempts_dir()` (for T004's `on_exit`); there is no singleton
  `attempt.json` and no `attempt-path` (T003/T004 updated accordingly).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_outcome_write_protocol_*` in tests/test_workflow.py (unit, `AI_STATE_DIR`
  in the test's temp dir):
  - P7 interleaving: the test opens the log itself and holds `flock(LOCK_EX)`; an
    `append_outcome` in a thread does not change the file while the lock is held (size
    unchanged after a short scaled wait, thread alive); the test then appends a partial
    fragment `{"time": "x", "kin` (no newline) and releases; the thread finishes (join with a
    scaled timeout), its record starts on a new line and `read_outcomes` returns it;
  - P8 ordering (`os.fsync` wrapped to record `os.fstat(fd).st_ino`): with the state dir absent,
    one append syncs the log file, then its directory, then each newly created ancestor's
    parent, all before True is returned; with the dir present, file then directory;
  - directory-sync failure (the wrapper raises `OSError` for the directory inode): the
    `outcome` command exits non-zero and `append_outcome` has not returned True (the
    marker-retention half of this case is T003's P9 acceptance bullet, since `--attempt` is
    T003's interface; plan review round 4, P14);
  - marker store: two `write_marker` calls give two files; writing an existing id raises and
    leaves the first file byte-identical; `list_markers` returns both in `started` order and a
    garbage file as `(path, None)`; `remove_marker` of a missing file is fine; an invalid id is
    refused.
- All existing `outcome` tests pass unchanged (`-k outcome`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_write_protocol` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE 2026-10-17. `append_outcome` now: `make_dirs` (records created ancestors) → open →
`flock(LOCK_EX)` → tail check → one write → fsync file → `fsync_dir(path.parent)` →
`sync_created` (parent of each created dir, deepest first) → True; sync OSErrors propagate.
Marker store: `attempts_dir`, `marker_path` (id validated `^[0-9a-f]{16}$`), `write_marker`
(tmp O_EXCL 0o600 + fsync + `os.link` + tmp unlink + dir fsync), `read_marker` (one place for
T010's read-error case), `marker_sort_key` (one place for T012's `seq`), `list_markers`,
`remove_marker`; `outcome attempt-dir`. Tests: 4 `test_outcome_write_protocol_*` (lock
interleaving, sync order with/without new dirs, dir-sync failure via `outcome`, marker store).
Evidence: `-k outcome_write_protocol` Ran 4 OK; `-k outcome` Ran 32 OK; ai-check PASS (762
tests, 413.8 s). docs/workflow.md "Outcome log" updated. Flow unchanged.


## T009 — CU-5 marker-removal gate: strict log read and `confirm_recorded` (CU-5, part 0c, round 3 redesign)
Status: DONE
Dependencies: T008
Model: opus

### Goal
Reconcile can tell an unreadable outcome log from an empty one, and no attempt marker is ever
removed on the "already recorded" path without a successful sync of the log file and its
directory, so the round 2 invariant ("a marker goes only when the log durably holds its id")
holds on every path. (Plan review round 3, P9 and P10; design note `.ai/current-plan.md`
"CU-5 marker-removal gate (round 3 redesign)".)

### Implementation notes
- `scripts/lib/workflow.py`, next to `read_outcomes` (~2984) and T008's `append_outcome`.
- `read_outcomes(paths, strict=False)`: the lenient default is today's behaviour (`OSError`
  → skip the file; `outcomes_report` and `outcome task` numbering keep using it). With
  `strict=True`: `FileNotFoundError` on a path → that file contributes no records (a missing
  log IS empty); any other `OSError` propagates to the caller. Comment why (P10: a transient
  read failure must not look like "no record yet"; reconcile would append a duplicate).
- `confirm_recorded(path, attempt_id) -> bool`: `fd = os.open(path, os.O_RDWR)`
  (`FileNotFoundError` → return False without creating the log); in `try/finally: os.close`:
  `fcntl.flock(fd, LOCK_EX)`; read the descriptor to EOF (loop on `os.read`); decode with
  T007's `decode_outcome_lines`; no task record with `attempt_id == attempt_id` → False;
  found → `os.fsync(fd)`, then T008's `fsync_dir(path.parent)` → True. Every other `OSError`
  propagates. Comment the rule (P9): a complete write whose file or directory sync failed
  leaves a readable line and a kept marker; the retry must finish the sync before the marker
  may go. Comment the residual: after a failed `fsync` the kernel may already have marked the
  dirty pages clean, so this persists what is still dirty; it guarantees a successful sync
  attempt before removal, not recovery of dropped data (advisory telemetry).
- Removal rule for T003 (write it as a comment on `confirm_recorded`): a marker is removed only
  after `append_outcome` returned True for a record carrying its id, or after
  `confirm_recorded` returned True; `confirm_recorded` and a following `append_outcome` lock
  separately, which is safe because a checkout's attempts are sequential under its lock, so no
  other writer appends that id in between.
- No marker store change, no reconcile, no `ai-run` change here (T003/T004).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_outcome_removal_gate_*` in tests/test_workflow.py (unit, `AI_STATE_DIR`
  in the test's temp dir):
  - strict read: a missing log gives `[]`; `os.read` (or `Path.read_bytes`, whichever the
    implementation uses; name it in the result) patched to raise `OSError(EIO)` once → `strict=True`
    raises, `strict=False` returns `[]` (lenient mode unchanged); a `PermissionError` likewise;
  - `confirm_recorded`: id absent → False and no fsync; id present → True after `os.fsync` of
    the log inode and then of its directory inode (wrapper records inodes in order); a missing
    log → False and the log is not created; `os.fsync` patched to raise for the file inode →
    `OSError` propagates; patched to raise for the directory inode only → `OSError` propagates
    (file sync observed first);
  - `confirm_recorded` waits for the log lock: the test holds `flock(LOCK_EX)` on the log, calls
    it in a thread, asserts the thread is alive after a short scaled wait and finishes (scaled
    join) with True after the release;
  - a torn multibyte tail after the record (as in T007) does not hide the record.
- All existing `outcome` tests pass unchanged (`-k outcome`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_removal_gate` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-17 (claude opus): `read_outcomes(paths, strict=False)` (missing file → no records in
both modes; other `OSError` propagates with `strict=True`) and `confirm_recorded(path,
attempt_id)` (O_RDWR open without create, `flock(LOCK_EX)`, `os.read` loop to EOF,
`decode_outcome_lines`, match on `kind == 'task'` and `attempt_id`, then `os.fsync(fd)` and
`fsync_dir(path.parent)`; removal rule and fsync residual in its docstring) in
`scripts/lib/workflow.py`. The strict-read test patches `Path.read_bytes` (what the
implementation uses) to raise `OSError(EIO)` / `PermissionError` once. Tests:
`test_outcome_removal_gate_strict_read`, `_confirm_recorded`, `_waits_for_the_log_lock`,
`_torn_multibyte_tail`. Evidence: `-k outcome_removal_gate` Ran 4 tests OK; `-k outcome` Ran 36
tests OK; `.ai/bin/ai-check` PASS (766 tests, 403.5 s). docs/workflow.md "Outcome log" updated;
flow unchanged (no caller yet: T003 wires it into reconcile).


## T010 — CU-5 marker failure contract: three-way marker read, id printed before publish (CU-5, part 0d, round 4 redesign)
Status: DONE
Dependencies: T009
Model: opus

### Goal
A transient error while reading one attempt marker never discards it (the other markers are
still processed), and a failure of `attempt-open` after the marker is linked never leaves the
runner without the id, so a task that finished normally is never reported `crashed` later.
(Plan review round 4, P12 and P13; design note `.ai/current-plan.md` "CU-5 marker failure
contract (round 4 redesign)".)

### Implementation notes
- `scripts/lib/workflow.py`, in T008's marker store.
- Read: `list_markers()` returns `[(path, record, error)]` sorted by (`started` when known,
  name); exactly one of `record`/`error` is set, or both are `None` for invalid content:
  `record` is a dict when the file was read completely and holds the required fields
  (`id` matching the file name and `^[0-9a-f]{16}$`, `task`, `model`, `project`, `branch`,
  `started`, `pid`, `pid_start`; keep them as one tuple: T012 appends `seq`, allocated from
  the persisted sequence before the print, and sorts the listing by it); `error` is the `OSError` instance when opening or reading the
  file failed (P12: the marker is the only durable evidence of an unrecorded attempt; a
  transient `EIO`/`EACCES` must not look like garbage); both `None` when the content was read
  completely but is not a valid marker (JSON error, missing field, id mismatch). Comment why
  invalid content may be discarded (our writer links only complete, fsynced files, so invalid
  content under the final name is foreign or corrupt, never a torn marker of ours).
  `os.scandir` failing raises; the caller (T003's reconcile) notes it and touches nothing.
  Adjust T008's `list_markers` test to the new shape.
- Publish: `open_attempt(task, model, pid, out=sys.stdout) -> str`: build the record (fields as
  T003 lists, `pid_start` from `/proc/PID/stat`), `print(id, file=out, flush=True)` FIRST, then
  `write_marker(record)` (T012 inserts the `seq` allocation before the print, so a failed
  allocation prints nothing and publishes nothing). Comment the contract (P13): the id reaches the caller before the
  marker can exist, so a marker without an id in the runner is impossible (a failed write to
  the pipe raises before the link); an id without a marker is harmless (the outcome carries
  it, `remove_marker` of a missing file is a no-op, nothing reconciles it). An `OSError` from
  `write_marker` propagates after the print; the `attempt-open` command (T003) turns it into
  a stderr note and exit 1. `open_attempt` does not reconcile (T003's `attempt-open` does,
  before calling it).
- Runner contract for T004 (write it as a comment on `open_attempt`):
  `attempt_id=$(ai_helper outcome attempt-open … 2>/dev/null) || true` then
  `[[ "$attempt_id" =~ ^[0-9a-f]{16}$ ]] || attempt_id=`; the exit status is ignored after
  the id is validated.
- Residual (comment + plan Risks): a marker whose directory sync failed after the link may not
  survive a power loss; that loses at most a `crashed` record, never produces a false one.
- No reconcile, no `attempt-open` command, no `ai-run` change here (T003/T004).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_outcome_marker_contract_*` in tests/test_workflow.py (unit, `AI_STATE_DIR`
  in the test's temp dir):
  - `list_markers` with three files, a valid marker, a garbage file and a valid marker whose
    read fails (`os.open`/`Path.read_bytes`, whichever the implementation uses, patched to raise
    `OSError(EIO)` for that path only; variant: `chmod 0o000`, skipped when running as root):
    returns three entries, the valid one with its record, the garbage one as `(path, None,
    None)`, the failing one as `(path, None, <OSError>)`, the files unchanged;
  - a marker whose `id` field differs from its file name, and one with a missing field, are
    invalid content, not errors;
  - `open_attempt` on a healthy store: the id is written to `out` before `write_marker` runs
    (wrap `write_marker` to assert `out` already holds the id), the marker exists, the return
    value equals the printed id;
  - `open_attempt` with `os.fsync` patched to raise for the attempts-directory inode only (P13:
    the failure after the link): the id was printed, `OSError` propagates, `<id>.json` exists
    and holds that id; with the attempts directory read-only (`chmod 0o500`, skipped as root):
    the id was printed, `OSError` propagates, no marker exists;
  - `write_marker` is not called when the print fails (`out` whose `write` raises `OSError`):
    no marker, no tmp file.
- All existing `outcome` tests pass unchanged (`-k outcome`), T008's `list_markers` case
  updated to the new shape and named in the result.

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_marker_contract` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE 2026-10-17. `read_marker` returns `(record, error)` and `list_markers` `[(path, record,
error)]` via `os.scandir` (listing failure raises; missing dir = `[]`); required fields in
`MARKER_FIELDS`, `started` numeric; entries without a record sort first by name, then by
(`started`, name). `process_start(pid)` (bytes, split after last `)`, field 22 or None);
`open_attempt(task, model, pid, out=None)` prints and flushes the id before `write_marker`,
with the P13 contract, T004 runner lines and power-loss residual in its docstring. Tests: 5
`test_outcome_marker_contract_*` (three-way read incl. EIO patch, chmod 000 variant and
scandir failure; invalid content; id printed before publish; dir-fsync failure after link and
read-only dir; no publish when the print fails); `test_outcome_write_protocol_marker_store`
updated to the 3-tuple shape with full-field markers. docs/workflow.md Outcome log updated.
Validation: `-k outcome_marker_contract` Ran 5 OK; `-k outcome` Ran 41 OK; `.ai/bin/ai-check`
PASS (771 tests). Flow unchanged (no caller until T003).


## T012 — CU-5 attempt sequence: one persisted `seq` allocated at open or append under the log lock; attempts ordered by it (CU-5, part 0e, round 6 redesign)
Status: DONE
Dependencies: T010
Model: opus

### Goal
Every task attempt the host records gets a sequence number from one persisted counter at the
moment it is first recorded (the attempt open, or the append for an attempt without an open),
so two attempts of one task never share an order key, whatever their wall-clock seconds, and
`ordered_attempts` orders a task's rows by that number with pre-upgrade rows first in file
order. (Plan review round 6, P15 and P16; design note `.ai/current-plan.md` "CU-5 attempt
sequence (round 6 redesign)", which replaces the start-time key of round 5.)

### Implementation notes
- `scripts/lib/workflow.py`, next to `outcomes_path` (~2958), `outcome()` (~3029) and T010's
  `open_attempt`.
- `attempt_seq_path() = state_root() / 'attempt-seq'` (beside `outcomes.jsonl`, same state
  root: they live and die together). `next_attempt_seq() -> int`: open the log with
  `O_RDWR|O_APPEND|O_CREAT` (create its directories as `append_outcome` does) and
  `fcntl.flock(fd, LOCK_EX)` on THAT descriptor (the lock every writer uses, T008; comment why
  the lock is on the log and not on the counter: the counter is replaced atomically, and a
  lock on a replaced inode no longer excludes later lockers); `current` = int content of the
  counter (missing, unreadable as int → 0); `recorded` = highest int `seq` of any `kind ==
  'task'` record in `read_outcomes([path], strict=True)` (T009; 0 when none); `n = max(current,
  recorded) + 1`; write `str(n)` to `attempt-seq.tmp` (`O_WRONLY|O_CREAT|O_TRUNC`, 0o644),
  fsync, `os.replace` to `attempt-seq`, T008's `fsync_dir` of the directory; close the log
  (releases the lock); return `n`. Every `OSError` propagates. Comment the self-heal (a lost
  counter continues after the highest recorded seq; markers allocated but unrecorded may then
  duplicate one, `_at` decides) and the cost (one log read, what `outcome task` already does
  for `attempt`, ~3045).
- `outcome task` (~3042–3050): the record gets `seq` from `next_attempt_seq()` (T003 later
  passes the marker's `seq` for `--attempt` rows with a readable marker; write it as "seq
  given → use it, else allocate"), and keeps `attempt`/`first_pass` as today. An `OSError`
  from the allocation → `fail('Could not allocate the attempt sequence: <path>.')` (exit 1,
  nothing appended; comment: a row is never written without `seq`, because a row without one
  would sort as a pre-upgrade row, before every real attempt).
- `open_attempt` (T010): call `next_attempt_seq()` BEFORE the print; the marker record gets
  `seq`; `list_markers` requires `seq` (int) and sorts by (`seq`, name) instead of (`started`,
  name) (T008/T010 tests adjusted and named in the result). An `OSError` from the allocation
  propagates before anything is printed (the `attempt-open` command, T003, turns it into a note
  and exit 1 with nothing printed: the runner runs the attempt untracked, as a helper failure
  does today).
- `attempt_seq(record) -> int | None`: `record['seq']` when an int and not a bool, else None.
- `ordered_attempts(task_rows) -> dict[key, list[record]]`, `key = (project, branch, task)`
  as in the report: per key, rows with `attempt_seq` None first in `_at` order, then the rest
  by `(seq, _at)`. Comment why (round 6): every row the new helper writes has a `seq`; rows
  without one are pre-upgrade rows, all older than any new row and appended in attempt order
  by one writer per checkout, so file order is exact for them; `_at` never orders two new rows
  unless the counter was lost. The sequence is host-wide (one counter per state root), so a
  task's numbers have gaps: an order key, not a count.
- `started` (round 5) stays an informational field written by `outcome task` and the marker
  (T011/T003); no `attempt_start`, no `time` minus `seconds` derivation anywhere.
- No report change (T011 consumes `ordered_attempts`), no reconcile, no `--attempt`, no
  `ai-run` change here (T003/T004). Docs are T011's.

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py

### Acceptance criteria
- Tests named `test_outcome_attempt_seq_*` in tests/test_workflow.py (unit and helper level,
  `AI_STATE_DIR` in the test's temp dir):
  - a fresh state root: three `next_attempt_seq()` calls give 1, 2, 3 and `attempt-seq` holds
    `3`; a new process (the `outcome task` command) continues at 4;
  - self-heal: the counter removed while the log holds task rows with `seq` 7 and 2 → the next
    allocation is 8 and the counter holds `8`; the counter holding `5` behind a log maximum of
    9 → 10; counter content `garbage` → treated as 0 (then the log maximum rules);
  - the allocation waits for the log lock: the test holds `flock(LOCK_EX)` on the log, calls
    `next_attempt_seq()` in a thread, asserts the thread is alive after a short scaled wait and
    finishes (scaled join) after the release with the counter advanced by one;
  - allocation failure (`os.replace` patched to raise `OSError`; variant: the state root made
    read-only, skipped as root): `outcome task T001 done m 5` exits 1 with `Could not allocate
    the attempt sequence`, the log gains no line; `open_attempt` raises before anything is
    written to `out` and leaves no marker and no tmp file;
  - `open_attempt` on a healthy store: the marker holds the `seq` the counter advanced to, and
    an `outcome task T002 done m 5` afterwards (no `--attempt` yet) gets a higher `seq`;
  - `ordered_attempts` units (rows written by hand with `_at`): the round 6 reproduction, B
    `done` (`seq` 2, `started` 1000) at an earlier `_at` than A `crashed` (`seq` 1, `started`
    1000) → [A, B], and the same with the `_at` values swapped; rows without `seq` only → `_at`
    order; two rows without `seq` after a row with `seq` 3 in the file → the two first in file
    order, then the `seq` row; duplicate `seq` → `_at` decides; `seq` given as `true` or `"2"`
    counts as none;
  - a real log: after `outcome task T001 done m 5` the line has an int `seq` ≥ 1 and the
    counter file holds that value.
- All existing `outcome` tests pass unchanged (`-k outcome`); T008's `list_markers` order case
  and T010's required-field case updated to `seq` and named in the result.

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_attempt_seq` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-17 (claude, opus): `attempt_seq_path`, `next_attempt_seq` (log `flock`, max(counter,
highest task `seq` read strictly) + 1, tmp + fsync + `os.replace` + `fsync_dir`; the tmp is
removed when the write or replace fails), `attempt_seq`, `ordered_attempts` in
`scripts/lib/workflow.py`. `outcome task` writes `seq` (allocated; "given → use it" slot left
for T003) and fails `Could not allocate the attempt sequence: <path>.` with nothing appended;
`open_attempt` allocates before the print; `read_marker` requires an int `seq` (`MARKER_FIELDS`)
and `marker_sort_key` sorts by (`seq`, name). Tests: 7 `test_outcome_attempt_seq_*` (fresh
store + new process, self-heal, lock wait, allocation failure incl. read-only root and
`open_attempt`, open then outcome, real log row, `ordered_attempts` units). Adjusted: the
`marker_record` helper takes `seq` (T008 `test_outcome_write_protocol_marker_store` order now
by `seq`), T010 `test_outcome_marker_contract_invalid_content` adds missing / `true` / `"3"`
`seq` cases. Validation: `-k outcome_attempt_seq` Ran 7 OK; `-k outcome` Ran 48 OK;
`.ai/bin/ai-check` PASS (778 tests, 407.3 s). No report, docs or runner change (T011/T003/T004).


## T011 — CU-5 report derives result, attempts and first pass from the attempt sequence; `started` on task records; docs (CU-5, part 0f, round 5 redesign as revised in round 6)
Status: DONE
Dependencies: T012
Model: opus

### Goal
`ai-status --outcomes` reports a task by the order its attempts were recorded by the host
(T012's `seq`), not by the order their lines reached the log, so a `crashed` record that
reconcile appends late (after a later attempt of the same task already logged `done`, even
one that opened within the same second) never turns the task into "not done", never makes
the later attempt the first-time pass, and both attempts are counted. (Plan review round 5,
P15; round 6, P15 and P16; design notes `.ai/current-plan.md` "CU-5 attempt ordering (round
5 redesign)" and "CU-5 attempt sequence (round 6 redesign)".)

### Implementation notes
- `scripts/lib/workflow.py`, `outcome()` (~3029) and `outcomes_report` (~3085).
- `outcome task` (~3042–3050): every task record also gets `started: int(time.time()) -
  int(seconds)` (epoch seconds; informational, the attempt's start as the runner measured it).
  T003 refines this: with `--attempt ID` naming a readable marker the record takes the marker's
  `started` (and, T012, its `seq`) instead, and reconcile's `crashed` record carries both from
  the marker. Keep `attempt` and `first_pass` exactly as today (count at append time) and
  comment that the report no longer reads them. There is NO ordering by `started`: the order
  key is `seq` (T012); do not add `attempt_start` or a `time` minus `seconds` derivation.
- `outcomes_report`: use T012's `ordered_attempts(task_rows)`; build `final` from the LAST row
  of each ordered list; `spent` unchanged (sum); the per-category table's `first-time pass` =
  the FIRST row of the ordered list has `result == 'done'`, `avg attempts` = mean of the list
  lengths; `first_row` = the first row of the ordered list (replaces "first line in file
  order"); `attempts_table`'s `first` = count of first rows whose `result == 'done'`. Drop
  every read of `first_pass` and `attempt` from the report. Comment at `final` (replacing "a
  task's last line is its result"): "a task's last attempt in sequence order is its result; a
  crashed attempt may be appended late; rows without `seq` are pre-upgrade rows in file order".
- Docs: README "Outcome log" (~495, ~499): the record's `seq` (host-wide order key, allocated
  when the attempt opens, gaps are normal) and `started` (epoch seconds, informational), and
  that the report orders a task's attempts by `seq`; `docs/workflow.md` ~899–900 ("the attempt
  number counts earlier lines…") gains "`seq` orders the attempt among all attempts the host
  recorded (allocated at the attempt open, or at the append for an attempt without one, from
  `attempt-seq` beside the log); `started` is the attempt's start (epoch seconds)", and
  ~930–935 ("aggregates the last line per task") becomes "the last attempt by `seq` (a crashed
  attempt reconciled late keeps its place); first-time pass = the first attempt by `seq` ended
  `done`; rows without `seq` (written before this version) come first, in file order". Flow
  unchanged.
- No marker, no reconcile, no `ai-run` change here (T003/T004).

### Likely affected modules
scripts/lib/workflow.py, tests/test_workflow.py, README.md, docs/workflow.md

### Acceptance criteria
- Tests named `test_outcome_attempt_order_*` in tests/test_workflow.py (report rows written
  by hand as `outcome_report_for` does):
  - round 6 reproduction (equal wall-clock seconds): rows for T001 in file order `done` (model
    `m`, `attempt` 1, `first_pass` true, `seconds` 5, `started` 1000, `seq` 2) then `crashed`
    (`attempt` 2, `first_pass` false, `seconds` null, `started` 1000, `seq` 1): the task summary
    shows done 1, not done 0, first-time pass 0/1, avg attempts 2.0; "Attempts by model" shows
    2 attempts, 1 done, 1 not done, first-time pass 0/1; the same two rows in the other file
    order give the same report; the variant with `started` 900 on the `crashed` row and 1000
    on the `done` row gives the same report (the start never orders);
  - pre-upgrade rows (no `seq`; P16): an `error` at `2026-10-17T10:05:00Z` with `seconds` 60
    appended first, then a `done` at `2026-10-17T10:00:00Z` with `seconds` 600 → the task is
    done (file order rules for rows without `seq`, whatever their times); the same two rows in
    the other file order → the task is NOT done, final result `error`;
  - mixed: two rows without `seq` (`error`, then `done`) followed in the file by `crashed`
    with `seq` 1 and `done` with `seq` 2 → 4 attempts, done, first-time pass 0/1; the two
    `seq` rows swapped in the file → identical report;
  - a real log: after `outcome task T001 done m 5` the line has an int `started` within a few
    seconds of `time` minus 5 and an int `seq`.
- `test_outcome_report_credits_each_attempt_to_its_model`, `test_outcome_report_old_lines_without_model_or_attempt`,
  `test_outcome_report_old_line_followed_by_new_attempt` and `test_runner_logs_task_outcomes_and_report`
  pass unchanged (their rows have no `seq`, so file order applies and the derived numbers
  equal the stored ones; name any test that had to change on purpose).
- `DocsConsistencyTest` passes; all existing `outcome` tests pass.

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_attempt_order` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
DONE 2026-10-17 (claude opus). `outcome task` rows carry `started` (`int(time.time()) - seconds`);
`attempt`/`first_pass` still written, commented as unread by the report. `outcomes_report` uses
`ordered_attempts`: `final` = last row, `first_row` = first row, first-time pass = first row
`done`, avg attempts = list length; no read of `first_pass`/`attempt` remains. Tests:
`test_outcome_attempt_order_round6_equal_seconds`, `_pre_upgrade_rows_follow_file_order`,
`_mixed_rows`, `_real_log_started`. Existing report tests (credits_each_attempt, old_lines,
old_line_followed_by_new_attempt, runner_logs_task_outcomes_and_report) pass unchanged.
README "Outcome log" and docs/workflow.md "Outcome log" document `seq`/`started` and the seq
order. Evidence: -k outcome_attempt_order 4 OK; -k outcome 52 OK; -k Docs 3 OK; ai-check PASS
(782 tests, 403.7 s). Flow unchanged.


## T003 — Outcome helper: durable attempt marker, idempotent crash reconcile, torn-line-safe append (CU-5, part 1)
Status: DONE
Dependencies: T010, T011
Model: opus

### Goal
The host can record that an implementation attempt is open, and a later start turns an
attempt whose runner died without its exit handler into exactly one `crashed` outcome line,
without ever losing or duplicating a line.

### Implementation notes
- Design: `.ai/current-plan.md` "CU-5 — attempt marker + reconcile", "CU-5 write protocol
  (round 2 redesign)", "CU-5 marker-removal gate (round 3 redesign)", "CU-5 marker failure
  contract (round 4 redesign)", "CU-5 attempt ordering (round 5 redesign)" and "CU-5 attempt
  sequence (round 6 redesign)". `scripts/lib/workflow.py`,
  next to `outcome()` (~3029–3082). Markers: one file per attempt through T008's store
  (`attempts_dir()` = `binding_dir() / 'attempts'`, `write_marker`, `list_markers` (T010's
  three-way shape), `remove_marker`; `binding_dir` ~1247 runs `check_state_root`). Never a
  singleton file, never an overwrite (plan review round 2, P6).
- `outcome attempt-open TASK MODEL PID`: first reconcile leftover markers with own PID = PID
  (same function as below), then T010's `open_attempt(TASK, MODEL, PID)`, which prints the id
  BEFORE publishing `{"id": secrets.token_hex(8), "task", "model", "project", "branch",
  "started": int(time.time()), "seq": next_attempt_seq() (T012, allocated before the print),
  "pid": PID, "pid_start": <field 22 of /proc/PID/stat or null>}` (P13). An `OSError` from the
  allocation (before the print) → stderr `Note: could not allocate the attempt sequence.`,
  nothing printed, exit 1 (the attempt runs untracked). An `OSError` after the print → stderr
  `Note: could not publish the attempt marker.`, exit 1 (the runner keeps the printed id,
  T004). Hand-written markers in tests carry a `seq` (T010's required fields plus T012's).
  Read `/proc/PID/stat` as bytes and
  split after the last `)` (comm can hold spaces, parentheses, non-UTF-8: see
  `tests/run_parallel.py` `parse_stat`).
- `outcome task TASK RESULT MODEL SECONDS [--attempt ID]`: the record gets `attempt_id` when
  given, and `seq` and `started` from the marker `<ID>.json` when it is readable and valid
  (T012's order key and the attempt's open time, so the row, its marker and a `crashed` row
  reconciled for the same marker agree; an absent or unreadable marker, P13, allocates a fresh
  `seq` with T012's `next_attempt_seq()` and keeps T011's derived `int(time.time()) - seconds`;
  a failed allocation fails the command as T012 defines, nothing appended, marker kept); after
  a SUCCESSFUL append (`append_outcome` returned True, T007/T008), remove the
  marker file `<ID>.json` (`remove_marker`). Other markers are left alone; a failed or short
  append keeps the marker (the `outcome` call fails as T007 defines).
- Append: every write goes through `append_outcome` (T007 + T008: readable `O_RDWR|O_APPEND`
  descriptor, `flock`, newline guard, complete-write check, file and directory fsync);
  `read_outcomes` is T007's per-line reader. Do not add a second append path.
- `outcome attempt-reconcile [OWN_PID]`: handles EVERY marker of `list_markers()` in order,
  each on its own (a failure on one keeps it and goes on to the next). No marker → silent exit
  0. The listing itself failing (`OSError` from `list_markers`) → stderr `Note: could not list
  the attempt markers.`, exit 0, nothing touched. Per entry (T010's three-way shape, P12): a
  read error → keep the marker, stderr `Note: could not read an attempt marker; keeping it.`,
  continue with the next marker; invalid content (`record` and `error` both `None`) →
  `remove_marker`, stderr `Note: discarded an invalid attempt marker.`; a valid record →
  below. Runner alive (pid exists and its current start time equals `pid_start`;
  `pid_start` null → pid exists) AND pid ≠ OWN_PID → leave it, silent. A marker of OWN_PID
  (with a matching start time) is an earlier, finished attempt of the calling runner whose
  outcome append failed (attempts are sequential under the lock), so it is reconciled like a
  dead runner's (P6). Otherwise, per marker, inside one `try` whose `OSError` keeps the marker
  (stderr `Note: could not read or sync the outcome log; keeping the attempt marker.`, exit 0):
  `confirm_recorded(path, id)` (T009: strict read under the lock, then file + directory sync)
  → True → only remove (P9: the earlier append's failed sync is finished here first); False →
  number the attempt from `read_outcomes([path], strict=True)` (P10: never the lenient reader
  here) and append a
  task record with `result: "crashed"`, task/model/project/branch from the marker (not the
  current branch), `seconds: null`, `seq` = the marker's `seq` and `started` = the marker's
  `started` (T012: the report orders attempts by `seq`, so a record appended late keeps its
  place, also when a later attempt opened within the same second), `attempt` numbered as
  `outcome task` does (count at append time; informational, P15), `first_pass:
  false`, `attempt_id`, and title/category as today; then remove ONLY if `append_outcome`
  returned True (a short write keeps the marker, stderr `Note: could not log the crashed
  attempt completely; will retry at the next start.`). stderr `Note: logged a crashed
  attempt of <task> (the runner was killed without its exit handler).` Never raises: any
  `OSError`/`ValueError` → stderr note, exit 0, marker kept. No other code path removes a
  readable marker (T009's removal rule).
- Known limit (comment + T004 docs): a short write of a normal `outcome task --attempt` line
  keeps the marker, so the next start logs that attempt as `crashed` (storage was full; the
  conservative record).
- `outcome attempt-dir` (T008) gives T004 the marker directory; the current attempt's file is
  `<dir>/<id>.json`.
- `outcomes_report` (T011's ordered version): check `crashed` rows with `seconds: null` are
  counted as not done and add 0 minutes (it uses `r.get('seconds') or 0`); the per-model
  attempts table counts them; a `crashed` row ordered before a later `done` of the same task
  leaves the task done.
- Concurrency: called only by `ai-run` under the checkout lock; the log is shared by all
  checkouts and serialised by T008's `flock` inside `append_outcome`. No other lock.
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
  - transient marker read failure (P12): two dead runners' markers A and B; the read of A
    patched to raise `OSError(EIO)` once (in-process; variant at command level with A
    `chmod 0o000`, skipped as root): reconcile keeps A byte-identical, appends nothing for A,
    prints the "could not read" note, still records B once and removes B, exit 0; the
    unpatched retry records A exactly once and removes it;
  - the attempts directory unlistable (`os.scandir` patched to raise `OSError`): the "could not
    list" note, exit 0, markers unchanged, nothing appended;
  - delayed reconcile after a successful retry within the same second (round 5 and round 6
    P15): a dead runner's marker A for T001 is written with `seq` from `next_attempt_seq()`
    and `started = int(time.time())` taken immediately before the next step (so A's and B's
    `started` are normally equal; the assertions must not depend on whether they are), then
    made unreadable (`chmod 0o000`, skipped as root; in-process variant: the read patched to
    raise `OSError(EIO)` until released); `attempt-open T001 m <own pid>` keeps A (note) and
    prints B, and marker B's `seq` is A's + 1; `outcome task T001 done m 5 --attempt B` appends
    one `done` line whose `seq` and `started` equal marker B's and removes B; `ai-status
    --outcomes` shows T001 done; A is made readable again; `attempt-reconcile` appends exactly
    one `crashed` record for A (its `seq` and `started` = marker A's, `attempt_id` A) AFTER B's
    line and removes A; `ai-status --outcomes` still shows T001 done 1, not done 0, 2 attempts,
    first-time pass 0/1; a second and third `attempt-reconcile` append nothing and the report
    is unchanged; variant: A's marker `started` is now − 100 → same report;
  - `outcome task T001 done m 5 --attempt <id>` with a readable marker: the line's `seq` and
    `started` equal the marker's; with no marker for that id (P13 variant): `seq` is a fresh
    allocation above the marker's would-be value (the counter advanced) and `started` is
    within a few seconds of `time` minus 5; with the counter unwritable (`os.replace` patched
    to raise) and no readable marker: exit 1, `Could not allocate the attempt sequence`, nothing
    appended, the marker (when present) kept and recorded `crashed` by the next unpatched
    reconcile with the marker's `seq`;
  - `attempt-open` with `write_marker` failing after the print (`os.fsync` patched to raise for
    the attempts-directory inode, P13): stdout is the id, exit 1, the "could not publish"
    note, the marker exists; `outcome task T001 done m 5 --attempt <that id>` then appends one
    line with that `attempt_id` and removes the marker; a following reconcile appends nothing.
    Variant with the attempts directory read-only (skipped as root): stdout is the id, exit 1,
    no marker; `outcome task … --attempt <id>` appends one line carrying it; reconcile appends
    nothing;
  - torn tail: the log ends with `{"time": "x", "kin` (no newline); the next `outcome` append
    starts on a new line and `read_outcomes` returns the new record (and not the fragment);
  - torn multibyte tail (P2): a valid record, then `{"title": "caf\xc3` (no newline), and a dead
    runner's marker: reconcile appends exactly one readable `crashed` record, earlier records
    stay readable, a second reconcile appends nothing;
  - short write during reconcile (P3; unit, `os.write` patched as in T007 to write half and
    return that count): nothing readable appended, the marker is kept, the note is printed,
    exit 0; a later unpatched reconcile appends one complete `crashed` record after the
    fragment and removes the marker; `outcome task … --attempt <id>` with a short write keeps
    the marker;
  - `outcome task --attempt X` with a marker of another id leaves the marker;
  - two attempts, first append fails (P6; `os.write` patched short for the first
    `outcome task … --attempt A` only): marker A kept; `attempt-open T002 m <own pid>` (the
    test's pid and start time, i.e. the same live runner) reconciles A: exactly one `crashed`
    record with `attempt_id` A, marker A removed, marker B written as a new file; `outcome task
    T002 done … --attempt B` removes B; a further `attempt-reconcile` appends nothing; A has
    exactly one record in the log. Variant: the reconcile of A fails too (short write again):
    A and B both exist afterwards, A byte-identical, and a later unpatched reconcile records A
    once;
  - two markers of dead runners: one reconcile records both, once each;
  - failed sync after a complete write (P9; `os.fsync` wrapped to raise for the log's file
    inode, variant: for its directory inode only): `outcome task T001 done m 5 --attempt A`
    exits non-zero, the line is readable, marker A kept; reconcile with the same fault still
    active → nothing appended, marker kept, the "could not read or sync" note; reconcile
    unpatched → the wrapper records a file fsync then a directory fsync, marker A removed, the
    log still has exactly one record with `attempt_id` A;
  - unreadable log (P10; a dead runner's marker whose record is already in the log; the read
    primitive T009 names patched to raise `OSError(EIO)` once): reconcile appends nothing,
    keeps the marker, prints the note, exit 0; the unpatched retry removes the marker and the
    log has exactly one record for A; variant without a record: the failed reconcile appends
    nothing, the retry appends exactly one `crashed` record;
  - missing log with a dead runner's marker: reconcile creates the log with exactly one
    `crashed` record and removes the marker;
  - `ai-status --outcomes` on a log with a `crashed` row (seconds null) renders without error
    and counts it as not done.
- All existing `outcome` tests pass unchanged (`-k outcome`).

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_attempt` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-17 (claude opus): DONE. `scripts/lib/workflow.py`: `reconcile_attempts(own_pid)` /
`reconcile_marker` / `runner_alive` (pid + `pid_start` via `process_start`; own pid reconciled,
P6); read error kept with note, invalid content removed with note, listing failure (`OSError`,
also a state-root `ValueError` or git error) noted and nothing touched; per marker
`confirm_recorded` → remove only, else strict `read_outcomes` numbering and one `crashed` row
(task/model/project/branch/`seq`/`started` from the marker, `seconds` null, `first_pass` false,
`attempt_id`), removed only when `append_outcome` returned True; any `OSError`/`ValueError` keeps
the marker with the "could not read or sync" note, exit 0. `outcome attempt-open TASK MODEL PID`
(reconcile, then `open_attempt`; new `AttemptSeqError(OSError)` from `open_attempt` tells the
pre-print allocation failure (note, nothing printed, exit 1) from a post-print publish failure
(note, exit 1)); `outcome attempt-reconcile [OWN_PID]`; `outcome task … --attempt ID` (row gets
`attempt_id`, `seq`/`started` from a readable marker, else fresh `seq`; marker removed only after
a durable append; a failed directory sync of that removal is suppressed, since a resurrected
marker is confirmed by `confirm_recorded`). Report needed no change (`seconds or 0`).
Tests: 26 new `test_outcome_attempt_*` covering every acceptance bullet (delayed reconcile in
three variants: same second, `started` −100, `chmod 0o000`; chmod/read-only variants skipped as
root). Mutation: dropping the `confirm_recorded` check fails 4 tests, dropping the own-pid
exception fails 2. Validation: `-k outcome_attempt` Ran 37 OK; `-k outcome` Ran 78 OK;
`.ai/bin/ai-check` PASS (808 tests, 428.8 s). No `ai-run` or docs change (T004). Flow unchanged.

## T004 — `ai-run` opens, closes and reconciles task attempts; a SIGKILLed runner's attempt is logged at the next start (CU-5, part 2)
Status: DONE
Dependencies: T003
Model: opus

### Goal
A runner killed by SIGKILL during a task session leaves an attempt that the next
`ai-run --approved` start logs as `crashed`, once; normal stops behave exactly as today.

### Implementation notes
- `scripts/ai-run`: right after `ai_branch` (~114) and BEFORE the mode branch at ~126 (so
  before the clean-checkpoint refusal at ~136–137 and the gate baseline at ~148), guarded by
  `[[ -n "$plan_file" ]] ||` (every non-`--plan` mode; triage/revision never open attempts but
  may reconcile leftovers):
  `attempt_dir=$(ai_helper outcome attempt-dir 2>/dev/null) || attempt_dir=` and
  `ai_helper outcome attempt-reconcile "$$" || true`. Comment (plan review round 3, P11, plan
  note "CU-5 start order in ai-run"): `ai_helper state implementing` (~626) dirties tracked
  `.ai/state.md` before every session, so a killed runner always leaves a dirty checkout and the
  restart refuses at ~136 before anything later could run; the reconcile is best effort, writes
  host state only and runs the same checkout helper that `state-root-check` (~109) already runs
  before the baseline, so it adds no new trust class. Do not move the gate baseline.
- Attempt open (~262–267, inside `claude_session` where `attempt_open=yes` is set), T010's
  runner contract (plan review round 4, P13):
  `attempt_id=$(ai_helper outcome attempt-open "$active_task" "${task_model:-$model}" "$$" 2>/dev/null) || true`
  then `[[ "$attempt_id" =~ ^[0-9a-f]{16}$ ]] || attempt_id=`, before `attempt_open=yes` (a
  limit retry stays in the same attempt, as today). Comment: the helper prints the id before
  it publishes the marker, so a marker can only exist once this shell holds its id; clearing
  the id on a non-zero exit would leave a published marker behind and the next start would
  log a finished task as `crashed` (a false record, whatever the report's order). Never clear
  a valid printed id because of the exit status.
- `task_outcome` (~208–212): pass `--attempt "$attempt_id"` when set, then clear `attempt_id`.
- `on_exit` (~169–196): when `attempt_open == yes` and `gate_ok == no` (no helper may run),
  `[[ -z "$attempt_dir" || -z "$attempt_id" ]] || rm -f -- "$attempt_dir/$attempt_id.json"`
  with a comment (a deliberate no-log stop must not be reported as a crash later; only this
  attempt's file, other retained markers stay for the next start).
- Mock claude (tests/test_workflow.py mock modes): `sigkill-runner` finds the `ai-run` process
  by walking `/proc/<pid>/stat` ppids from the mock upward to the first `bash` whose
  `/proc/<pid>/cmdline` contains `ai-run`, writes its pid to a file in the test base dir, sends
  it SIGKILL and exits. The test SIGKILLs every pid it recorded (and the `timeout` parent) in
  `addCleanup`.
- Docs: README "Outcome log" and `docs/workflow.md` outcome section: a killed runner's attempt
  is logged as `crashed` (seconds unknown) at the next `ai-run --approved` start, before the
  clean-checkpoint check, so that start still stops with `Start from a clean checkpoint`
  until the interrupted bookkeeping (`.ai/state.md` at least) is committed or reset; limits
  (only implementation attempts; a checkout never started again keeps its marker; a sync that
  the kernel already failed cannot be redone, T009).
- Vault (flow change in a described step): `agents-flow.md` "Outcome log" bullet (~147) gains
  "an attempt whose runner was killed is logged as crashed at the next start"; `updated:`
  bumped; hub Log line.

### Likely affected modules
scripts/ai-run, tests/test_workflow.py, README.md, docs/workflow.md, vault agents-flow.md and
agents.md (Log)

### Acceptance criteria
- Tests named `test_outcome_crash_*` in tests/test_workflow.py:
  - `ai-run --approved` with `MOCK_CLAUDE=sigkill-runner`: the runner dies (exit -9 / 137), the
    outcome log has no line for the task, the marker exists and `git status --porcelain` names
    `.ai/state.md` (P11: the runner wrote it at ~626); a second ordinary `ai-run --approved`
    exits 1 with `Start from a clean checkpoint`, ran no session, and the log now has exactly
    one `crashed` line (attempt 1, `attempt_id` = the marker's id, `seconds` null) with the
    marker gone; the test then checkpoints the fixture's leftovers (stage and commit everything
    `git status --porcelain` lists, in the temp repo); a third `ai-run --approved` (mock mode
    that implements and checkpoints the task) logs `done` (attempt 2, its own `attempt_id`)
    and no second `crashed`; a fourth start appends nothing;
  - the existing interrupted/timeout/error outcome paths (e.g. `test_runner_logs_task_outcomes_and_report`
    and the session-timeout outcome tests) log exactly what they did before, now with
    `attempt_id`, and leave no marker;
  - failed attempt open, id kept (P13, end to end): before an `ai-run --approved` whose mock
    implements and checkpoints the task, the test creates the fixture's attempts directory
    (`outcome attempt-dir` under the fixture's `AI_STATE_DIR`) and makes it read-only
    (`chmod 0o500`, restored in `addCleanup`, skipped as root), so `attempt-open` prints an id
    and exits 1 after it: the run completes, the task's `done` line carries a 16-hex
    `attempt_id`, stderr/log has no `crashed`, and the next `ai-run --approved` start appends
    nothing; the post-link variant (marker exists, exit 1) is covered at helper level by
    T003's `attempt-open` cases, since a directory-sync failure cannot be injected into the
    runner's helper from outside;
  - a gate-changing session (existing gate-change mock mode): no outcome line (as today) and no
    marker afterwards, and the next start logs nothing for it.
- All existing tests pass unchanged; the vault flow chart and hub Log are updated (or the
  denial is recorded in the result and the handoff).

### Validation
Targeted: `python3 -m unittest discover -s tests -k outcome_crash` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k outcome` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
2026-10-17 (claude opus): DONE. `scripts/ai-run`: after `ai_branch`, every non-`--plan` start
reads `outcome attempt-dir` and runs `outcome attempt-reconcile "$$" || true` before the
clean-checkpoint refusal (gate baseline unmoved); `claude_session` opens the attempt with
`attempt-open … "$$"`, keeping any printed 16-hex id whatever the exit status; `task_outcome`
passes `--attempt` and clears the id; `on_exit` with the gate broken removes only this
attempt's marker with `rm -f`. Mock mode `sigkill-runner` (ppid walk to the `bash … ai-run`,
pids recorded for cleanup). Tests: `test_outcome_crash_killed_runner_logged_once_at_next_start`,
`…_normal_stops_carry_attempt_id_and_leave_no_marker` (timeout/error/done),
`…_failed_attempt_open_keeps_the_printed_id` (read-only attempts dir),
`…_gate_change_leaves_no_marker`. README "Outcome log", docs/workflow.md outcome section, vault
flow bullet and hub Log updated. Validation: `-k outcome_crash` 4 OK, `-k outcome` 82 OK,
`.ai/bin/ai-check` PASS (812 tests).

## T005 — Recovery reasons and plan questions are cut at a sentence or word boundary; the full text is kept (R13)
Status: DONE
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
- `scripts/ai-recover`: right after `ai_lock` (~31), `rm -f -- .ai/local/recovery-decision.txt`
  (plain shell, no helper, so it is safe before the gate check) with a comment: escalations
  before `recover-decision` (~59–171) must never point at a previous invocation's text
  (plan review P4).
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
  - stale sidecar (P4): after that long-decision escalation, a second `ai-recover` that escalates
    early (e.g. `AI_AUTO_RECOVER=0`) sends a ⛔ without `Full text:` and leaves no
    `recovery-decision.txt`;
  - `bounded_questions` with a 400-character question ends with `…` at a word boundary.
- `test_recovery_decision_*` and all other existing tests pass (any test that asserted a hard
  300-character cut is updated on purpose and named in the result).

### Validation
Targeted: `python3 -m unittest discover -s tests -k recovery_reason_shorten` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k recovery` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
Done. `shorten(text, cap)` in scripts/lib/workflow.py; `recover_decision` uses it (300), writes/removes
`.ai/local/recovery-decision.txt`; `ai-recover` removes it after the lock and `escalate` appends
`Full text: …`; `bounded_questions` uses `shorten`. README and docs/workflow.md updated. Tests
`test_recovery_reason_shorten_*` (5, mock mode `escalate-long`);
`test_recovery_decision_prose_only_escalates_with_an_excerpt` updated on purpose (no longer a hard
300 cut). Gate PASS (817 tests). Vault `agents-flow.md` does not state the 300-character cut: flow unchanged.


## T006 — Docs, handoff and final audit for the batch
Status: DONE
Dependencies: T001, T002, T007, T008, T009, T010, T012, T011, T003, T004, T005
Model: haiku

### Goal
README, `docs/workflow.md`, the vault flow chart and the handoff describe what the code now
does; the human knows which upgrade, vault and backlog steps remain.

### Implementation notes
- Check each sentence the tasks added (README, `docs/workflow.md`) against the code once:
  finding cells (T001/T002), attempt marker and `crashed` outcomes (T003/T004), `seq`,
  `started` and the report's sequence ordering (T012/T011), boundary cut and
  `recovery-decision.txt` (T005).
  Fix contradictions; no new behaviour.
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
- The handoff names `test_finding_cell_*`, `test_outcome_log_io_*`, `test_outcome_write_protocol_*`, `test_outcome_removal_gate_*`, `test_outcome_marker_contract_*`, `test_outcome_attempt_seq_*`, `test_outcome_attempt_order_*`, `test_outcome_attempt_*`, `test_outcome_crash_*` and
  `test_recovery_reason_shorten_*` under "Covered by automated tests", and every group exists
  (`python3 -m unittest discover -s tests -k <group>` runs ≥ 1 test each).

### Validation
Targeted: `python3 -m unittest discover -s tests -k Docs` (must say `Ran N tests`, N ≥ 1).
Targeted: `python3 -m unittest discover -s tests -k flow_this_repo` (must say `Ran N tests`, N ≥ 1).
Gate: `.ai/bin/ai-check` in the FOREGROUND with the Bash tool timeout set to 600000 ms (see the gate note above if it times out).

### Result / notes
- Audit: README and `docs/workflow.md` checked against the code for the sentences T001–T012
  added. Finding cell rule (`docs/workflow.md` triage paragraph) matches `FINDING_CELL` in
  `scripts/lib/workflow.py`. `crashed` / reconcile wording (`docs/workflow.md` attempt-marker
  paragraph) matches `ai-run` (reconcile at every non-`--plan` start). Fixed: README's
  `crashed` sentence said `ai-run --approved` start; now "`ai-run` start other than `--plan`".
  `recovery-decision.txt` and `seq`/`started`/report ordering wording match the code; no other
  contradiction found.
- Vault: `agents-flow.md` already `updated: 2026-10-17` and has the T004 "Outcome log" bullet;
  T005/T006 change no flow. Hub Log line added for the batch-5 planner finding.
- Handoff: flow chart line, "Manual testing" (Needs you / Covered by automated tests naming
  every group) and Human todos checked; Next action updated.
- Validation: `python3 -m unittest discover -s tests -k Docs` → Ran 3 tests, OK;
  `-k flow_this_repo` → Ran 1 test, OK; `.ai/bin/ai-check` → Ran 817 tests, OK.
- Limitation: installed copies (`.ai/bin`, `.ai/prompts` of other projects) unchanged; upgrade
  is a human step (handoff Human todos).

