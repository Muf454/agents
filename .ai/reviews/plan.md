<!-- Plan review of plan digest 806b1898b82331542c62a52611a845867355b767ed26246beedbbf73dc256ef1; HEAD 3ce16d17d78b5a664d02ffeb0bd3779e1e944322; saved 2026-10-16T20:05:52Z. -->

# Plan review

Overall verdict: Changes required before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=4 MINOR=1

Reviewed HEAD: `3ce16d17d78b5a664d02ffeb0bd3779e1e944322`.

## BLOCKER findings

None.

## MAJOR findings

- P1: Scratch deletion does not protect parent paths, and its model understates the risk.

  **Location:** `.ai/tasks.md:353`, `.ai/tasks.md:360`; `scripts/lib/common.sh:113`, `scripts/lib/common.sh:130`.

  Removing the trailing slash protects a symlink at `scratch` itself. It does not protect `.ai/local` or `.ai`: if a session replaces either parent with a symlink, the proposed host `rm -rf` follows that parent and deletes an external `scratch` directory. Startup path checks precede the session, and the gate digest excludes `.ai/local`. Cleanup is expressly placed before post-session verification.

  **Concrete plan change:** Use deletion relative to directory descriptors opened without following symlinks, retaining the warning-and-continue behavior for unsafe paths. Existing `local_dir_fd` machinery provides a useful precedent. Add tests where the mock session replaces a parent with an external symlink and verify external contents survive. Reconcile startup rejection of pre-existing scratch symlinks with the promised cleanup behavior. Assign this security-sensitive deletion work to `opus`; prompt and documentation changes can remain separate cheaper tasks.

- P2: The proposed cell regex can reinterpret an escaped pipe as a separator.

  **Location:** `.ai/tasks.md:272`.

  The fallback alternative `[^|\n]` also matches backslashes. Regex backtracking can therefore split `\|` when the remaining columns would otherwise fail to match. An in-memory reproduction using the exact proposed pattern parsed:

  ```text
  | P11 | accepted | discussion of fix \| T030 |
  ```

  as evidence `discussion of fix \` and task `T030`. This row actually has no task cell: its escaped pipe belongs to the evidence. The disposition checker could consequently accept a malformed row and infer a fix-task link.

  **Concrete plan change:** Make escaped separators indivisible through a deterministic cell scanner or a pattern whose fallback cannot consume the escape prefix. Add malformed-row tests for both disposition formats, including this missing-task-cell example, alongside valid escaping and round-trip tests.

- P3: Recovery scanning can promote nested examples into executable decisions.

  **Location:** `.ai/tasks.md:422`.

  Advancing past successfully decoded objects protects their nested objects, but advancing to the next `{` after a decode error does not. The proposed algorithm accepts the nested `commit_and_rerun` in:

  ```text
  Broken diagnostic: {"details":{"action":"commit_and_rerun","reason":"example"}, BROKEN}
  ```

  It also accepts the object inside a prose-prefixed array such as `Diagnostic: [{"action":"rerun","reason":"example"}]`. Both outcomes were reproduced in memory following the proposed scan. These are nested objects, contrary to the stated top-level requirement, and can authorize recovery.

  **Concrete plan change:** Specify container and quotation handling before implementation. Reject ambiguous or malformed enclosing structures, and never reconsider their nested objects as standalone decisions. Add negative tests for prose-prefixed arrays, malformed outer objects, and quoted examples while retaining the intended prose-plus-decision cases.

- P4: Shutdown lacks a completion barrier and conflicts with ongoing reaping.

  **Location:** `.ai/tasks.md:47`, `.ai/tasks.md:94`, `.ai/tasks.md:123`.

  Three walk-and-SIGKILL rounds do not establish that every descendant has terminated before `run()` returns: SIGKILL delivery is asynchronous, and descendants with closed output streams do not keep batch readers waiting. The plan specifies no final wait or failure behavior if live descendants remain. Additionally, T001’s main-thread reaping loop continues while a worker executes `stop()` outside the lock, contradicting T002’s instruction not to reap during kill rounds.

  The proposed process tests use descendants that normally terminate on SIGTERM, leaving these paths untested.

  **Concrete plan change:** Define coordinated shutdown ownership, suspend ordinary reaping during termination, and add a bounded final wait that confirms descendants are gone or zombies. Report cleanup failure explicitly if the bound expires. Add tests for detached descendants that ignore SIGTERM and close inherited output streams, forks during shutdown, and concurrent stop/reaping activity.

## MINOR findings

- P5: Timestamp precision cannot distinguish every later catch-up record.

  **Location:** `.ai/tasks.md:487`; `scripts/lib/workflow.py:25`.

  Coverage uses strictly later timestamp strings, but `now()` records whole seconds. A catch-up appended after a Claude review within the same second will leave that review pending. Simply changing the comparison to `>=` could instead cover a subsequent Claude review from that second.

  **Concrete plan change:** Define deterministic ordering for equal timestamps, using an explicit sequence/cutoff or another suitable ordering field. Test both an earlier and a subsequent Claude review sharing the catch-up timestamp.

## Validation observed

- `workflow.py tasks check` passed.
- Shell syntax checks passed for the inspected runner, review, recovery, status, check and validation scripts.
- AST parsing passed for the inspected Python modules.
- `DocsConsistencyTest` passed: 3 tests.
- In-memory reproductions confirmed P2 and P3.

## Scope and limitations

Inspected the instructions, spec, plan, task queue, state, handoff, relevant source, prompts, tests, documentation, validation entry point and flow-chart references.

The integration suite and full gate were not run because they create fixture files and validation artifacts in this read-only environment. No files were modified or network integrations invoked. The findings concern the proposed design and acceptance coverage; implementation has not begun.