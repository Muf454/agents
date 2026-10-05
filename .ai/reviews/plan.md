<!-- Plan review of plan digest 11d13891f178b1709ccc69a32b67930657e3091db1a85b70c56e503bb13d3bad; saved 2026-10-05T06:42:35Z. -->

# Plan review

Overall verdict: REVISE PLAN — address the MAJOR findings before unattended implementation.
Finding counts: BLOCKER=0 MAJOR=3 MINOR=1

Reviewed HEAD: `4afb3b3b1838483d14284b749e879995f56b1a7e`

Scope: Repository guidance, spec, plan, all nine tasks, affected scripts and templates, existing tests, validation evidence, documentation, and the vault flow chart. This reviews proposed implementation; no files were modified.

## BLOCKER findings

None.

## MAJOR findings

- P10: The proposed “read-only” permissions allow writes and program execution.  
  **Location:** `.ai/tasks.md:16–20`; `templates/.claude/settings.json:17`.  
  `Bash(sed -n *)` also matches `sed -n -i …`, which edits files. Sed scripts themselves support writing and executing commands. `Bash(rg *)` permits `rg --pre=COMMAND`, which executes a preprocessor. These require no shell redirects, pipes, or command chains, so the claimed protection does not address them. Edit/Write deny rules do not constrain these Bash operations. The proposed tests inspect allowlist text and would miss this capability expansion.  
  **Concrete plan change:** Replace these broad entries with constrained commands or a host-maintained read helper that validates arguments. Add negative cases covering in-place sed, sed execution/write commands, and ripgrep preprocessors. Document the actual residual capabilities rather than describing these patterns as read-only. Local command help confirmed these capabilities; live Claude permission matching was not tested.

- P11: Every targeted validation command conflicts with the unattended permissions and tool contract.  
  **Location:** `.ai/tasks.md:32`, `.ai/tasks.md:49`, `.ai/current-plan.md:25`; `.ai/permissions.allow`.  
  All nine tasks require direct `python3 -m unittest discover …` commands. The frozen run allowlist does not authorize them, and T001’s proposed additions do not authorize them for future installations either. T002 additionally instructs sessions to run checks only through `.ai/bin/ai-check`. The full gate can execute the suite, but that does not satisfy the explicitly required targeted invocation and nonzero test-count evidence.  
  **Concrete plan change:** Choose one consistent validation route. Either require the full gate and inspection of its executed tests, or provide an approved targeted-check interface. Specify how this self-hosted run obtains that interface without editing frozen gate files during implementation. Require tests that verify the resulting validation command is authorized.

- P12: Upgrade behavior is undefined for newly introduced toolkit files.  
  **Location:** `.ai/tasks.md:247–266`; `scripts/lib/workflow.py:117–121`.  
  T008 defines replacement through matching an existing installation baseline, but does not define creation when a destination and baseline are absent. This batch introduces `.ai/bin/ai-task` and `.ai/prompts/recheck.md`; older installations necessarily lack them. The acceptance tests cover replacing an outdated file, not installing newly added files. An upgrade could satisfy those tests while leaving the new task command or dispute flow unusable.  
  **Concrete plan change:** Define an inventory-based `CREATE` action for absent toolkit-owned files, distinct from existing unbaselined files requiring conservative handling. Include creations in preview and apply, preserve path/symlink checks, set executable modes, and record their baselines. Test upgrading a genuine older inventory lacking both new files and then invoking the installed command and re-check flow.

## MINOR findings

- P8: The recorded knowledge-directory invocation uses a literal quoted tilde.  
  **Location:** `.ai/tasks.md:5`; `scripts/ai-run:27–30`.  
  `--knowledge-dir "~/zWiki/zWiki/20 Projects/agents"` does not expand `~` in Bash. `ai-run` checks the supplied directory directly and rejects it. The literal path does not exist here; the expanded path does.  
  **Concrete plan change:** Record `--knowledge-dir "$HOME/zWiki/zWiki/20 Projects/agents"` or the absolute path in the launch prerequisite.

## Validation observed

- HEAD matched the requested revision; the working tree was clean.
- Task-queue parsing passed.
- Bash syntax passed for 11 scripts/templates; Python AST parsing passed for both helper modules and the test file.
- Stored evidence reports **102 tests passed** at `2026-10-05T06:29:14Z`, on earlier HEAD `7edb78b`.
- Current validation-stamp verification failed as stale. That stored PASS does not validate this plan revision.
- The integration suite and full gate were not run: they create files and temporary repositories, which this read-only sandbox does not permit.
- No network or MCP integrations were invoked.

## Security and architecture concerns

The revised triage ownership, crash reconciliation, push-retry checks, and re-check bindings address the corresponding first-review gaps at the planning level. Their correctness remains dependent on implementation and regression tests. The new permission expansion needs capability-level checks, and upgrades need complete inventory handling.

## Manual testing recommendations

After implementation, supervise interrupted-triage recovery, upgrade an older installation missing the new files, and verify that an upheld dispute converts an existing ready PR to draft with the dispute section first. Human acceptance remains outstanding.