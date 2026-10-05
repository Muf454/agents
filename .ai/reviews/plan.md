<!-- Plan review of plan digest 530e626ef0840ac52f27f7288b5f4970f860d505a68e4bc95d22b13482ecca3b; saved 2026-10-05T06:47:15Z. -->

# Plan review

Overall verdict: REVISE PLAN — resolve the recovery and dispute-lifecycle gaps before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=2 MINOR=2

Reviewed HEAD: `a8ebae7a2b9508330bf8ca11cdb9c16ae434259e`

Scope: Repository instructions, spec, plan, all nine tasks, affected scripts and templates, existing tests, validation evidence, documentation, and relevant vault notes. These findings concern the proposed implementation; no files were modified.

## BLOCKER findings

None.

## MAJOR findings

- P1: The recovered completion-commit path skips triage invariants.  
  **Location:** `.ai/tasks.md:114–119`; `scripts/ai-run:160–169`.  
  T004 says to mark the stage complete when its counted triage commit already exists. Scope and fresh-disposition checks are specified only for the alternative path that creates the commit. Existing `ai-run` checks scope before that commit, then checks only gate integrity afterward. A commit hook can therefore change application source without changing gate files; a subsequent crash before stage clearing would enter the proposed shortcut and bypass the required scope check.  
  **Concrete plan change:** Require review binding, allowed-path scope, and fresh dispositions to verify before closing the stage in both reconciliation paths. Check committed and uncommitted changes against the persisted start boundary. Add a regression where the completion commit exists but a hook changed source: resume must escalate without entering implementation or counting another round.

- P3: Upheld disputes lack a defined lifetime across subsequent reviews.  
  **Location:** `.ai/tasks.md:190–192`, `.ai/tasks.md:223–237`; `scripts/lib/workflow.py:482`, `scripts/lib/workflow.py:525–527`.  
  T007 requires disputes to survive rounds, but T006 defines one report bound to the current implementation review. Existing publication replaces `current.md`, and a subsequent triage replaces dispositions. In the mixed accepted/rejected case, accepted fixes trigger another review, making the earlier re-check’s current-review binding invalid. The plan does not specify how to retain and verify the upheld finding, its original text, and Claude’s evidence—or what evidence may resolve it. The proposed mixed-disposition test checks that fixes proceed, without asserting the eventual PR status and body.  
  **Concrete plan change:** Define durable dispute records keyed by review digest and finding ID, retaining the original finding, rejection evidence, answer, and provenance. Specify an explicit resolution rule after source changes. Test an upheld rejection alongside accepted fixes through a subsequent clean review and a restart: it must remain visible and keep the PR draft until the defined resolution evidence exists.

## MINOR findings

- P13: The spec still contradicts the revised tool contract.  
  **Location:** `.ai/project-spec.md:8–13`; `.ai/tasks.md:18–20`, `.ai/tasks.md:49–53`.  
  The spec requires allowing `rg` and `sed -n` and running checks only through `ai-check`. The revised tasks deliberately exclude those shell commands and permit targeted test commands. It also requires an identical recovery section while T002 provides only reading rules for recovery. These discrepancies leave conflicting acceptance instructions for unattended implementation.  
  **Concrete plan change:** Update B1/E1 to the revised command policy, targeted-check allowance, and explicit read-only recovery variant.

- P14: Documentation checks miss existing contradictory statements.  
  **Location:** `.ai/tasks.md:308–310`; `docs/workflow.md:144`; `README.md:152`.  
  T009’s forbidden phrases do not match existing claims such as “The toolkit does not invoke `git push`” or the statement grouping denied permissions among conditions that stop a run. A modes heading alone also does not verify the required four modes or their capabilities. The checks could pass while these documented behavior errors remain.  
  **Concrete plan change:** Cover the actual contradictory wording and assert the four required mode rows. Add coverage for the positive statements about logged denials, automatic checkpoints, publishing, and provider-limit recovery.

## Validation observed

- HEAD matched the requested revision; the working tree was clean.
- Task-queue parsing passed.
- Bash syntax passed for 11 scripts/templates.
- Python AST parsing passed for both helper modules and the test file.
- Stored evidence reports **102 tests passed** at `2026-10-05T06:29:14Z`, on earlier HEAD `7edb78b`.
- Current validation-stamp verification failed as stale.
- The integration suite and full gate were not run because they create files and temporary repositories, which this read-only sandbox does not permit.
- No network or MCP integrations were invoked.

## Security and architecture concerns

The revised permission exclusions, separate re-check preflight, input/output bindings, and upgrade creation rules address the earlier gaps at the planning level. Recovery must verify invariants even when completion evidence exists, and dispute provenance must remain usable across review replacement. No additional model-selection findings were identified.

## Manual testing recommendations

After implementation, supervise triage recovery with a completion-hook source change, a mixed-disposition flow across review and restart, and an older-installation upgrade. Verify dispute text and conversion of an existing ready PR to draft. Human acceptance remains outstanding.