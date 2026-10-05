<!-- Plan review of plan digest 1de9efc45c1b3adb5b50c9b8f0cb91196593252a7b74b51c97cb67fc8479d86f; saved 2026-10-05T06:37:35Z. -->

# Plan review

Overall verdict: REVISE PLAN — address the MAJOR findings before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=6 MINOR=3

Reviewed HEAD: `31ba4019738178e9f50275fe939906b97b367eda`

Scope: Spec, plan, all seven tasks, repository instructions, affected scripts and templates, existing tests, validation evidence, documentation, and relevant vault notes. These are plan gaps against the existing code; no implementation changes were reviewed.

## BLOCKER findings

None.

## MAJOR findings

- P1: Triage completion needs one commit owner and an idempotent recovery protocol.  
  **Location:** `.ai/current-plan.md:6`, `.ai/tasks.md:71`; `scripts/ai-run:168`, `scripts/ai-pipeline:74`, `scripts/lib/workflow.py:598`.  
  The assessment incorrectly says the pipeline creates the counted triage commit: `ai-run` currently creates it. T003 assigns completion to the pipeline without including `ai-run` or explaining how its existing completion path changes. It also specifies “commit; then clear stage” without handling a crash between those operations, which can count the round twice. Human restarts currently overwrite the manifest, and watchdog recovery supplies a generic crash stage.  
  **Plan change:** Include `ai-run`, assign one completion owner, and identify the completion commit for each persisted triage stage. Preserve and reconcile an unfinished stage before resetting its manifest or entering implementation; use the manifest’s stage during crash recovery. Test normal completion, interrupted completion, a crash after the counted commit but before stage clearing, and watchdog recovery. Each must enforce scope/fresh dispositions and count exactly one round.

- P2: Comparing remote HEAD after push does not detect uncommitted hook changes.  
  **Location:** `.ai/tasks.md:104`; `scripts/ai-pipeline:231`, `scripts/ai-pipeline:259`.  
  T004 specifies readiness checks before pushes, followed by a remote/local HEAD comparison. A pre-push hook can modify application source without committing it: remote HEAD still equals local HEAD, and the existing gate check does not hash application source. On the final push, the pipeline could then report success with a dirty, unvalidated checkout. The proposed hook test covers commits only.  
  **Plan change:** Recheck the full readiness predicate after push hooks as well as comparing remote HEAD. Place pre-push checks inside the retry loop so every attempt is checked. Add regressions for uncommitted source changes during the final push and a failed push that changes the checkout before retry.

- P3: Re-check integration omits mixed dispositions and the resume shortcut.  
  **Location:** `.ai/tasks.md:132`; `scripts/ai-review:23`, `scripts/ai-review:85`, `scripts/ai-pipeline:185`, `scripts/ai-pipeline:167`.  
  T005’s acceptance tests cover rejection-only triage. A triage that both accepts and rejects findings creates TODO fix tasks and invalidates the validation fingerprint; the existing implementation-review preflight requires a base, all tasks DONE, and a current stamp. Reusing that preflight would prevent the required immediate re-check. Separately, completed dispositions are reused through an early exit on resume, bypassing a call placed only after newly executed triage. The loop also resets `unresolved` each round.  
  **Plan change:** Specify a separate `--recheck` preflight that permits pending accepted fixes while verifying the reviewed source and review provenance. Route new and reused dispositions through the same rejection check, and derive dispute state from current verified evidence. Test mixed accepted/rejected findings and resume with completed dispositions but no re-check report.

- P4: The re-check report needs input freshness, not just an output digest.  
  **Location:** `.ai/tasks.md:134`; `scripts/lib/workflow.py:333`, `scripts/ai-pipeline:132`.  
  “Bound by digest like current.md” establishes report integrity but leaves its input binding unspecified. Dispositions and re-check reports are excluded from source freshness checks. Claude’s rejection evidence can therefore change while an earlier `withdrawn` answer remains apparently valid; finding IDs can also recur in later reviews.  
  **Plan change:** Bind each report to the implementation-review digest, rejected finding IDs and evidence, and the source context examined. Verify that binding on resume, when deciding draft status, and when generating the PR body. Require exactly one answer for every rejected significant finding. Add tests for changed evidence, reports from another review, report tampering, and missing/duplicate answers.

- P5: Upgrade baselines are undefined for existing installations and preserved edits.  
  **Location:** `.ai/tasks.md:163`; `scripts/lib/workflow.py:158`, `tests/test_workflow.py:665`.  
  Existing installations have no version stamp, yet T006 only tests fresh setup followed by upgrade. It does not define how legacy files are classified. It also says to rewrite the stamp after apply without defining what happens to hashes for locally edited files that were kept. Recording their current hashes would make those edits look unmodified on the next upgrade, allowing replacement without `--force`. Repeated ordinary setup presents the same risk if it refreshes baselines for preserved files.  
  **Plan change:** Define conservative behavior for missing/malformed stamps and retain the previous installation baseline for skipped files. Ordinary setup must not bless preserved edits as toolkit originals. Test legacy installations, repeated setup after a local edit, two consecutive upgrade applies, and a genuine version-A-to-version-B upgrade.

- P6: T001 assigns permission-policy work to `sonnet`.  
  **Location:** `.ai/tasks.md:8`, `.ai/tasks.md:17`.  
  T001 changes unattended shell/Git authorization through `permissions.allow`, including file-removal/move commands and shell matching patterns. This is security-policy work, which the requested model rule assigns to `opus`.  
  **Plan change:** Split the permission-policy portion into an explicit `Model: opus` task. Keep wrapper/setup and prompt work separately scoped. Include negative permission assertions alongside the approved entries.

## MINOR findings

- P7: The new re-check effort setting is absent from recovery/settings integration.  
  **Location:** `.ai/tasks.md:138`; `scripts/lib/common.sh:37`, `scripts/lib/workflow.py:659`, `scripts/ai-recover:53`.  
  The plan introduces `AI_RECHECK_EFFORT` without adding it to captured/restored run settings. Crash recovery could use a different effort from the approved run.  
  **Plan change:** Include the setting in manifest capture, recovery clearing/restoration, and supported user configuration. Add a recovery regression verifying the original value.

- P8: The vault-update task needs an explicit unattended access prerequisite.  
  **Location:** `.ai/tasks.md:194`; `scripts/ai-run:27`, `scripts/ai-run:61`; `README.md:329`.  
  T007 requires an external vault write, but the plan does not specify launching this run with `--knowledge-dir`. Repository guidance alone does not grant that access. The flow-chart update is also deferred until T007, despite `CLAUDE.md` requesting updates in the same task as flow changes.  
  **Plan change:** Record the required invocation with the vault directory, and update the diagram alongside T003/T005 or explicitly reconcile the documentation timing rule.

- P9: Validation commands remain placeholders and omit checks for some acceptance criteria.  
  **Location:** `.ai/current-plan.md:22`, `.ai/tasks.md:31`, `.ai/tasks.md:202`.  
  Every targeted command uses `<name>` or `<relevant>`, and T007’s grep check provides neither patterns nor a command. A mistyped unittest filter can select zero tests successfully. T001’s listed tests also omit the required `ai-task show` behavior.  
  **Plan change:** Supply concrete targeted commands, add `show` coverage, and identify executable checks for the documentation criteria. Retain the full toolkit gate.

## Validation observed

- HEAD matched the requested revision; the working tree was clean.
- Task-queue parsing passed.
- Bash syntax passed for 11 scripts/templates; Python AST parsing passed for the two helper modules and test file.
- The stored log reports **102 tests passed** at `2026-10-05T06:29:14Z`, on earlier HEAD `7edb78b`.
- Current `stamp verify` failed as stale. The stored PASS does not establish validation of this plan commit.
- The integration suite and full gate were not run: they create files and temporary repositories, which this read-only sandbox does not permit.
- No files were modified; no network or MCP integrations were invoked.

## Security and architecture concerns

Keep triage authority in host state, centralize completion ownership, and verify re-check provenance at every consumer. Upgrade writes should retain the existing symlink/path checks and derive replacement destinations from the toolkit inventory.

## Manual testing recommendations

After implementation, perform a supervised interrupted-triage resume and inspect the round count. Exercise preview/apply twice on an older installation with local edits, and verify an upheld dispute converts an existing ready PR to draft with the dispute section first. Human acceptance remains outstanding.