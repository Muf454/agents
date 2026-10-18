# Spec: Flow batch 7: session limit vs a slow gate and timeout recovery (FL-28), executable bits (FL-29), disposition finding cells (FL-30), a faster self-check with progress (FL-31)

## Objective
Four backlog items from the vault `agents-backlog.md` (FL-28 to FL-31), planned 2026-10-18 on
`fix/flow-batch-7`. The branch was created from `master` at 1423b60, which contains batch 6 (#31),
the CI cap raise (#32) and the toolkit self-upgrade (#33).
1. **FL-28.** Implementation sessions get extra time sized from the measured gate time, so a
   ~9-minute gate no longer uses up a 30-minute session. Also, a session timeout on an
   IN_PROGRESS task is recovered once per task by the host: it commits the validated partial work
   and reruns, without escalating.
2. **FL-29.** The runner can make a tracked script executable inside the checkout. Finish what is
   left: the host restores the recorded mode, and the prompts give the exact allowed command.
3. **FL-30.** Disposition finding cells accept a leading finding ID followed by text, and the
   revision prompt template shows the exact row format.
4. **FL-31.** The self-check gets faster (a shared fixture repository, fewer full `ai-pipeline`
   fixture runs, the slowest-15 list kept as a budget) and prints progress, so a timeout shows how
   far the run got. No test is weakened or skipped.

## Verified against the code (2026-10-18, 1423b60)
- **FL-28, session limit.** `scripts/ai-run` sets `session_timeout=1800` (`--session-timeout`,
  3600 for `--plan`). `claude_session` (~291–345) caps it only by the remaining run time. Nothing
  measures the gate. The host gate runs in `checkpoint_done` (~669) and the final check (~777).
  `.ai/local/validation.json` keeps only start and end timestamps, in an agent-writable directory.
  The host outcome log (`outcomes.jsonl` under the host state root, outside every checkout)
  records task, review, plan and plan-revision lines, but not the gate.
- **FL-28, recovery.** A session timeout makes `claude_session` stop with `ai_die "Claude exited
  124 (timeout/interruption/error). Preserve partial work; …"` (exit 137 after `--kill-after`).
  ai-pipeline stops with stage `implementation` (~541), and `ai-recover` gets a reason that
  matches no hard rule. A read-only Claude session then decides; for an unfinished task it
  usually escalates. `commit_and_rerun` (~322–344) already runs dependency setup and the full
  gate, commits only on a pass and checks the commit. The host manifest records the session's
  task (`run-manifest task-set`, ~1526). That record survives a stop and is cleared at the runner
  checkpoint. There is no read action for it outside `limit-task`.
- **FL-29.** `templates/.ai/permissions.allow` (~33) and this repository's allowlist (~42) already
  contain `Bash(chmod +x *)`. `templates/.ai/prompts/runner.md` (~58) and `triage.md` (~64)
  already say to run `chmod +x <path>` on a new script. README (~179) and docs/workflow.md (~149)
  mention it. Still missing, from the incident (batch 6 T006, `chmod 755` denied while git already
  recorded 100755): (a) the prompts never say that only the `+x` form is allowed, or how to fix a
  TRACKED script whose working-tree file lost its bit; (b) nothing on the host side re-aligns such
  a file with the mode git recorded, so the post-session gate (`test_script_modes`) fails.
- **FL-30.** Already done in the parser: `FINDING_CELL` (`workflow.py` ~1017) accepts `P1
  (MAJOR) title`, `P1 — title`, `P1: title` and `P1 title`, for triage and plan dispositions.
  Tests `test_finding_cell_*` (~11279–11345) cover this, including `P1 (MAJOR) selection highlight
  is lost`. The unmatched-cell hint names the row to write. `plan-revision.md` (~30–32) shows
  `| P1 | accepted | <evidence> | T012 |`. The family-budget incident ran on an older installed copy
  (its toolkit upgrade PR #2 was opened later the same day). Still missing: a regression test for
  the exact incident row, and for the restart path (a complete but uncommitted section with
  decorated cells is recorded without a session). The prompt shows one row but not the table
  header or the rejected and needs-human row shapes.
- **FL-31.** `.ai/validate` runs `python3 tests/run_parallel.py`. That script prints nothing until
  every batch has finished, then prints the failing batches, the slowest 15 tests and `Ran N tests`.
  A SIGTERM from `ai-check`'s `timeout` stops it without any summary, so the output shows nothing
  about how far it got. Every `ToolkitTest` builds its project in `ready()` (~1615:
  `setup-project`, a bootstrap commit, a branch switch, a second commit). The FL-23 notes
  (`plans/sessions/agents-T006-deferred.md`) measured that setup at under 0.1 s and the slow
  25–29 s tests as spending their time inside the pipeline. Profiling commands are denied to
  sessions; `python3 -m unittest …` and `.ai/bin/ai-check` are allowed.

## Scope
- `scripts/lib/workflow.py`: outcome kind `gate` and command `gate-seconds`; run-manifest actions
  `task` and `timeout-rerun TASK` with field `timeout_reruns`; command `exec-bits` (restore the
  recorded executable bit of tracked files).
- `scripts/ai-run`: measure and record its own gate runs; give implementation sessions an
  allowance for the gate; run `exec-bits` after each session.
- `scripts/ai-recover`: the session-timeout rule (validated commit and rerun, once per task),
  using the existing `commit_and_rerun` steps factored into one function.
- `templates/.ai/prompts/runner.md`, `triage.md`, `plan-revision.md`: wording only.
- `tests/run_parallel.py`: progress lines, a stop summary and a per-test budget report.
- `tests/test_workflow.py`: new regression tests, a shared `ready()` template and fewer
  redundant pipeline runs (assertions kept).
- README.md, docs/workflow.md, the vault flow chart and the hub Log.

## Non-goals
- No change to gate files: `.ai/bin`, `.ai/prompts`, `.ai/validate`, `.ai/ci-setup`,
  `.ai/permissions.allow`, `.claude/settings.json` and `.github/workflows/*`. The installed copy
  gets the new scripts and prompts through the human's `setup-project --upgrade` after merge.
- No change to the CI timeout (the job and `AI_CHECK_TIMEOUT` in the workflow); lowering it again
  is the human's decision.
- No profiling, no new allowlist entries, no new setting unless needed (none is planned).
- No removal, skipping or weakening of a test; no test ID removed or renamed.
- No change to the parser's accepted cell shapes (FL-30 already accepts them); no change to triage
  or to the decision prompt's actions.
- No unvalidated commit: the timeout rule commits only after the full gate passes, as
  `commit_and_rerun` does today.

## Constraints
- Sessions are capped at 30 minutes including a ~9-minute gate, so every task is about 15 minutes
  of work.
- Host authority stays out of the checkout (AD-4, AD-5). The gate time comes from the host outcome
  log, which agents cannot write; the once-per-task record lives in the host run manifest.
- Tests with time bounds assert "within N s" with generous bounds scaled by `tests/timeouts.py`.
- A changed flow updates `agents-flow.md` (vault) in the same task, plus a hub Log line.

## Requirements and acceptance criteria
- **R1 (FL-28, gate allowance).** An implementation session's limit is `session_timeout +
  min(2 × G, session_timeout)`. G is the largest `seconds` among the last 3 `gate` outcome lines
  with result `pass` for this project (0 when there are none). The result is still capped by the
  remaining run time. Triage, plan revision and planning sessions are unchanged. The `Session:`
  line names the allowance. Each host gate run of `ai-run` appends a `gate` outcome line (`pass`,
  `fail` or `timeout`, measured seconds). Observable: with `gate pass 300` recorded,
  `--session-timeout 1000` gives `limit 1600s`; with nothing recorded, today's line is printed
  byte for byte.
- **R2 (FL-28, timeout recovery).** In `ai-recover`, stage `implementation`, a reason starting
  `Claude exited 124 (` or `Claude exited 137 (`, the manifest's task IN_PROGRESS in the working
  queue and a dirty checkout after the leftovers commit lead to: a 🔧 notification, dependency
  setup, the full gate, a `recovery checkpoint` commit and a resume, with no Claude decision
  session, the first time for that task in the run. A second such timeout of the same task is one
  ⛔ `timed out again`. A failing gate escalates as `commit_and_rerun` does today, with nothing
  committed. Every other case behaves as today: the hard rules, the attempt budget,
  `AI_AUTO_RECOVER=0`, the armed rule, a TODO task and a clean checkout.
- **R3 (FL-29).** After each implementation session, `ai-run` restores the executable bit of
  tracked regular files whose index mode is 100755 and whose working-tree file lacks it. Gate
  paths, symlinks and untracked files are never touched, and each restored path is printed. The
  runner and triage prompts say that `chmod +x <path>` is the only allowed form (never `chmod 755`)
  and that it also repairs a tracked script whose bit was lost (`git diff` shows `old mode
  100755`).
- **R4 (FL-30).** The incident row `| P1 (MAJOR) dev proxy vs Origin check | accepted | … | T002 |`
  passes `plan-dispositions-check`. An interrupted revision whose complete, uncommitted section
  uses such cells is recorded by the restarted pipeline without a session. `plan-revision.md`
  shows the table header and one row of each kind (accepted, rejected, needs-human).
- **R5 (FL-31, progress).** `run_parallel.py` prints one flushed progress line per finished
  batch: batches done/total, tests run, failing batches and elapsed seconds. On SIGTERM or an
  interrupt it prints a stop summary (finished and running batches, tests run, failing batch
  numbers) before it exits non-zero. The final report is unchanged.
- **R6 (FL-31, budget).** Every finished test over a per-test budget (30 s × the
  `tests/timeouts.py` scale; `AI_TEST_BUDGET` overrides it) is listed as a warning after the
  slowest 15. The budget never changes the exit code. The docs state the budget rule.
- **R7 (FL-31, speed).** `ready()` copies a per-process template of the bootstrapped project
  instead of rebuilding it, with the same files, modes, branch and commit subjects. Tests that run
  `ai-pipeline` more than once only to reach a precondition are trimmed where the precondition is
  already asserted elsewhere; every change is listed. The discovered test ID set only grows, every
  test passes, and no assertion is removed.

## Assumptions (unattended planning; recorded instead of asked)
- A1: "Scale with the measured gate time" means room for two gate runs (one failing, one
  passing), capped at doubling the base limit. The measurement comes from the host outcome log
  (agent-unwritable), not from `.ai/local/validation.json` (agent-writable). The first run on a
  project, with no measurement yet, behaves as today.
- A2: Only implementation sessions run the gate, so only they get the allowance.
- A3: "Once per task" is per human-started run: `run-manifest start` drops the record and
  `clear-attempts` keeps it, so a resumed pipeline cannot reset it. A second timeout of the same
  task escalates instead of going to the decision session, which could choose `commit_and_rerun`
  again.
- A4: A timeout on a TODO task (the session never marked it) or on a clean checkout is left to
  today's decision session (usually `rerun`).
- A5: FL-30's parser part is done (verified above); only the regression and the prompt remain.
- A6: FL-31's speed work cannot be profiled. The fixture template is built because Zack asked for
  it, even though the FL-23 measurement predicts a small gain. Its result records before and after
  `-k` timings. Pipeline-run trimming is limited to provably redundant setup runs.
- A7: The previous queue's 21 DONE tasks (batch 6) stay in `.ai/tasks.md` unchanged because the
  host refuses a plan that removes them. The new tasks are T022–T033.
