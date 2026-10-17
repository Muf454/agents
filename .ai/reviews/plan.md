<!-- Plan review of plan digest 6ae36a6ae582d84501fcdcbe6a9d907830e48fe62d505fcc764bd450ed9420ae; HEAD e957b52432fa9523e5bd4d146aafde77b1cb5dbc; saved 2026-10-17T01:43:16Z. -->

# Plan review

Review scope: HEAD `e957b52432fa9523e5bd4d146aafde77b1cb5dbc`.

Overall verdict: Revise before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=2

## BLOCKER findings

None.

## MAJOR findings

- P1: The proposed append descriptor cannot read the log tail.

  **Location:** `.ai/tasks.md:155–158` (T003).

  The plan opens the log with `O_WRONLY|O_APPEND|O_CREAT`, then calls `os.pread` on that descriptor. Reading a write-only descriptor raises `OSError: [Errno 9] Bad file descriptor`. Once the log contains a record, subsequent appends would fail, affecting task, review and reconciliation outcomes.

  **Concrete plan change:** Open with `O_RDWR|O_APPEND|O_CREAT`, or use a separate readable descriptor. Explicitly require a regression test that appends successfully to a nonempty log, both with and without its final newline.

- P2: Torn UTF-8 tails prevent reading and reconciliation before the newline guard can help.

  **Location:** `.ai/tasks.md:155–159,193–194`; `scripts/lib/workflow.py:2984–2996,3082`.

  The planned torn-tail test uses ASCII only. Existing outcomes use `ensure_ascii=False`, so a damaged tail can end inside a multibyte character. `read_outcomes` decodes the entire file before parsing individual lines; an incomplete UTF-8 character raises `UnicodeDecodeError`, bypassing the malformed-line skip. Task outcome numbering and crash reconciliation both depend on this reader.

  This is a pre-existing reader limitation that T003 must address to deliver its new torn-tail guarantee.

  **Concrete plan change:** Read and decode records independently, skipping invalid fragments while preserving valid records. Add a regression with a truncated multibyte character, verifying that earlier records remain readable, a subsequent append is readable, and reconciliation records the attempt once.

- P3: A short `os.write` can be mistaken for a completed durable append.

  **Location:** `.ai/tasks.md:152–168` (T003).

  The design specifies one `os.write`, followed by `fsync` and marker removal, without requiring a check of the returned byte count. A regular-file write can return fewer bytes than requested, including when storage fills. Fsyncing that fragment does not complete the JSON record. Reconciliation could then unlink its marker despite having written no readable outcome, permanently losing the attempt.

  **Concrete plan change:** Require the returned byte count to equal the complete encoded record length before treating the append as successful or removing its marker. Treat a short write as a best-effort telemetry failure and retain the marker. Add fault-injection coverage showing that a later reconciliation writes one complete record after the fragment and then removes the marker.

## MINOR findings

- P4: An early recovery escalation can link to a previous recovery’s full text.

  **Location:** `.ai/tasks.md:282–289`; `scripts/ai-recover:101–142,192`.

  T005 removes stale `recovery-decision.txt` only when `recover_decision` runs, but `ai-recover` has several escalation paths before that call. After a previous long decision, an early stop could therefore append “Full text” pointing to unrelated old advice.

  **Concrete plan change:** Clear the sidecar after acquiring the recovery lock, or append its pointer only when the current invocation generated it. Test a long-decision escalation followed by an early escalation.

- P5: The proposed diagnostic search cannot satisfy the `M1x` acceptance case.

  **Location:** `.ai/tasks.md:50–54,68–71`.

  The hint searches for `\bM1\b`, but the acceptance criteria require a quoted-cell hint for `M1x`. There is no word boundary between `1` and `x`, so the prescribed implementation cannot produce that hint.

  **Concrete plan change:** Add diagnostic-only recognition of glued ID suffixes while keeping those rows rejected, and retain the explicit `M1x` regression.

## Validation and limitations

Inspected repository guidance, spec, plan, all six tasks, state, handoff, relevant scripts, prompts, tests, documentation, validation entry point and Git history.

Observed:

- Task queue validation passed.
- Relevant shell syntax and Python AST checks passed.
- Existing shared-prompt-contract and table-cell-pattern test methods passed without fixture setup.
- Read-only probes reproduced the write-only descriptor error, UTF-8 reader failure and `M1x` diagnostic mismatch.

The full gate and fixture-based integration suite were not run because they require filesystem writes unavailable in this review sandbox. No files were modified. Task model selections are appropriate for the stated work; no model-selection findings were identified.