<!-- Plan review of plan digest 53953b0ac615406ae481243ca9c78d0605be1a88bd6b61c7e2fbf7e04ab7eef9; saved 2026-10-05T07:10:38Z. -->

# Plan review

Overall verdict: REVISE — upgrade consistency needs an explicit policy and regression test before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=1

Reviewed HEAD: `bd93b3b27328fc08a05b6340b525b7b0a83999d9`

## BLOCKER findings

None.

## MAJOR findings

- P11: Per-file upgrade decisions can leave incompatible toolkit components installed.
  
  **Location:** `.ai/tasks.md:282` — T008 replacement and preservation rules.
  
  **Problem:** T008 replaces unchanged files independently while retaining locally edited files. It does not address dependencies between those files. All shell tools invoke the installed shared helper through `ai_helper` in `scripts/lib/common.sh`. T004 and T006 require new helper behavior for triage stages and re-check bindings; the existing helper lacks that behavior.
  
  For example, an older installation with a locally edited `lib/workflow.py` would keep that helper while receiving the newer pipeline and reviewer. The resulting installation could fail when those callers request the new functionality. Conversely, retaining an older caller can prevent the new recovery or dispute rules from taking effect. The listed upgrade tests check preservation and creation, but do not require a compatible installed runtime.
  
  **Concrete plan change:** Treat dependent runtime files as a compatible upgrade group. If retained local edits prevent installing that group coherently, refuse its upgrade before mutation and explain which files require reconciliation or explicit `--force`. Add an A→B regression with a locally edited older shared helper: ordinary apply must preserve a working installation, and a deliberate complete upgrade must pass an installed pipeline smoke test.

## MINOR findings

- P12: Flow-chart maintenance omits the publishing gates and PR declaration.
  
  **Location:** `.ai/current-plan.md:23`, `.ai/tasks.md:154`, `.ai/tasks.md:319`; requirement in `AGENTS.md:15`.
  
  **Problem:** The plan schedules chart updates for T004 and T007 only. T005 adds publishing gates, but its task omits a chart update. T009 checks only R1/R3 coverage. No task explicitly ensures the PR description contains “Flow chart updated” or “Flow unchanged,” as repository instructions require.
  
  **Concrete plan change:** Add the publishing checks and remote-HEAD verification to the chart during T005, updating its date in that session. Audit other changed defaults and steps against the chart, and require the appropriate declaration in this change’s PR description.

## Scope and assessment

Inspected repository instructions, spec, plan, all nine tasks, affected scripts and prompt templates, relevant tests, documentation, vault flow chart, Git history, and stored validation evidence.

The plan explicitly covers triage reconciliation, publish checks, re-check provenance, durable disputes, and conservative upgrade baselines. Every task specifies a model; no model-selection mismatch was identified. P11 concerns planned upgrade behavior, not a demonstrated defect in implemented upgrade code.

## Validation observed

- Requested HEAD matched; working tree was clean.
- Task-queue parsing passed.
- Bash syntax passed for 12 script and validation files.
- Python AST parsing passed for both helper modules and the test file.
- Stored validation evidence reports **102 tests passed** at `2026-10-05T06:29:14Z`, on earlier HEAD `7edb78b`.
- Current validation-stamp verification failed as stale.

The full gate and integration suite were not run because they create temporary repositories, locks, logs, and evidence files prohibited by this read-only sandbox. No files were modified; no network or MCP integrations were invoked.

## Security, architecture, and manual validation

Host-side bindings and verification remain central to the proposed recovery and dispute protocols. Upgrade planning must preserve compatibility between callers and those verification helpers.

After implementation, supervise interrupted triage and re-check recovery, verify remote/local HEAD equality, confirm upheld disputes keep an existing PR in draft, and exercise upgrade preview/apply with locally edited runtime files.

Implementation review and human acceptance remain outstanding.