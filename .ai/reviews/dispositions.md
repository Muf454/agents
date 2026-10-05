# Review dispositions (Claude)

Review HEAD: 28049e444739e2b9e480813c5d6530fa552b110b

<!-- One row per BLOCKER/MAJOR finding (MINOR optional). Disposition: accepted (needs a
fix task ID), rejected (needs concrete evidence), or deferred (real but out of scope;
explain the risk; makes the PR a draft). Never edit .ai/reviews/current.md. -->

| Finding | Disposition | Evidence / reason | Fix task |
| --- | --- | --- | --- |
| M1 | accepted | Verified: `parse_recheck` (workflow.py:974) only notes and skips unknown ids, so a fully withdrawn answer set plus an extra id still returns withdrawn; T006 requires extra answers to count as upheld. | T011 |
| M2 | accepted | Verified: the apply loop (workflow.py:208) calls `install_bytes` sequentially with no rollback and writes the stamp last, so a later failure leaves new and old files mixed; T008 requires all-or-nothing. | T012 |
| N1 | accepted | Verified: scripts/ai-task is 0644 in Git (T002 notes). Cheap to fix. | T013 |
| N2 | accepted | Verified: `pr_body` (workflow.py:1483) only copies the "Manual testing for the human" section, so the declaration in the handoff summary never reaches the PR. | T014 |
