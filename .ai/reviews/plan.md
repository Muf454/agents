<!-- Plan review of plan digest 5d54898abf2e136d8eeeafea128291b98155c188dc4c10f957763a42a04b0bbb; HEAD de8df736121f5d25b187dc7c1ab1dac51919cb5b; saved 2026-10-16T20:13:43Z. -->

# Plan review

Overall verdict: Changes required before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=0

Reviewed HEAD: `de8df736121f5d25b187dc7c1ab1dac51919cb5b`.

## BLOCKER findings

None.

## MAJOR findings

- P3: Recovery scanning can still promote a nested example into an executable decision.

  **Location:** `.ai/tasks.md:535–540` (T008).

  The revised enclosure check uses plain character counts without recognizing JSON strings. This answer passes that check:

  ```text
  Diagnostic: ["]",
  {"action":"commit_and_rerun","reason":"example"}
  ]
  ```

  Before the candidate, the opening array bracket is balanced numerically by the bracket **inside the string**. The candidate starts and ends its line, so the proposed scanner accepts `commit_and_rerun`, although the object belongs to an enclosing array. The trailing array bracket receives no enclosure check.

  An in-memory reproduction confirmed both that the proposed checks pass and that the diagnostic container parses as an array. Line anchoring therefore does not fully resolve the earlier finding.

  **Concrete plan change:** Replace character counts with an enclosure scan that respects quoted strings, escapes and bracket nesting, and handles the remaining suffix. Never promote objects inside enclosing containers. Add this reproduction and equivalent quoted-brace cases as negative tests, retaining the intended prose-plus-decision cases.

- P6: Interrupts during worker startup can bypass shutdown entirely.

  **Location:** `.ai/tasks.md:120–122` (T002); `tests/run_parallel.py:274–286`.

  `Dispatcher.run()` starts worker threads before entering its `try/except BaseException`. Once the first worker launches a batch, SIGINT or SIGTERM during a later `thread.start()` escapes without calling `stop()`. The new descendant cleanup and completion barrier cannot protect this path.

  A read-only reproduction patched the second thread startup to raise `KeyboardInterrupt`: one worker had started, and `stop()` was never invoked. This is a pre-existing hole within the planned FL-27 guarantee; the proposed signal tests wait for child PID files and do not exercise startup interruption.

  **Concrete plan change:** Extend T002’s cleanup-protected region to include worker startup. Handle partially started workers and avoid joining unstarted threads. Add deterministic startup-interruption coverage after the first batch launches, asserting that cleanup completes and its detached descendants are gone or zombies.

## MINOR findings

None.

## Previous-round assessment

The revised plan adequately addresses P1, P2, P4 and P5 at the design level. P3 remains open for the counterexample above. Every task has an explicit `Model:` line; no model-risk mismatch was found.

## Validation observed

- Parsed the current queue: 11 tasks, all with explicit models.
- Checked the revised disposition regex against valid escaped pipes and missing-task-cell examples.
- Reproduced P3’s proposed parsing behavior and P6’s existing exception-path gap in memory.
- Python AST parsing and shell syntax checks passed for inspected files.
- `DocsConsistencyTest`: 3 tests passed.

## Scope and limitations

Inspected repository instructions, spec, plan, tasks, state, handoff, prior dispositions, relevant source, prompts, tests, documentation and `.ai/validate`.

The integration suite and full gate were not run because they write fixtures and validation artifacts in this read-only environment. No files were modified or network integrations invoked. After implementation, retain the planned real-process signal tests and manual self-check interruption check.