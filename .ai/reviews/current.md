<!-- Host evidence: HEAD 86912702b4c62e535c57fe98176b0f2689855dc5; merge-base 9e11a113f02525b2f1e10db3eb73eb571495507b; saved 2026-10-06T21:47:11Z. -->

# Independent review

Overall verdict: CHANGES REQUIRED — FL-01’s preservation check has a significant gap; two localized correctness issues also need attention.
Finding counts: BLOCKER=0 MAJOR=1 MINOR=2

Reviewed HEAD: `86912702b4c62e535c57fe98176b0f2689855dc5`  
Supplied base / verified merge-base: `9e11a113f02525b2f1e10db3eb73eb571495507b`

Inspected repository instructions, specification, plan, tasks, state, handoff, review template, relevant documentation, scoped Git history/diff, affected source/tests, validation evidence, and the vault flow chart. The checkout was clean. All findings below concern introduced code; no separate pre-existing defect was demonstrated.

Validation observed/run:

- Stored evidence reports **PASS**, exit 0, at `2026-10-06T21:42:47Z`, recorded at `7e14e4a8ae66b67248157d94f24b47181ab76a3e`. Its log records **222 tests passed** in 614.436 seconds.
- Current fingerprint matches the stored evidence. Validation-stamp verification, task-queue validation, committed-content comparison, and `git diff --check` passed.
- **Three documentation tests**, **12 Bash syntax checks**, and **three Python syntax checks** passed.
- Read-only, in-memory checks exercised the actual snapshot, PR rendering, dependency freshness, mixed-handoff counting, and timer-status functions.

Limitations: The full `./scripts/ai-check` gate and writable integration fixtures were not rerun because they create repositories, locks, logs, and validation artifacts. Reproductions using mocked filesystem/Git responses are identified below. Live providers, GitHub, package installation, and systemd were not exercised. No project files were written or network/MCP integrations invoked.

## BLOCKER findings

None found in the inspected scope.

## MAJOR findings

### M1 — Uninitialized submodule paths can change without changing the preservation snapshot

**Location:** [scripts/lib/workflow.py:1627](/home/zack/Projects/wt/agents-flow2/scripts/lib/workflow.py:1627); caller: `scripts/lib/common.sh:172`.

**Requirement:** FL-01 requires an unchanged snapshot of every non-ignored project file’s path, kind, mode and bytes, including submodules, after every installer exit.

**Problem:** Every gitlink lacking `.git` is represented only by `uninitialised`. This branch runs before symlink and file handling. It therefore gives the same representation to an empty uninitialized submodule, that path containing newly created files, and that path replaced by a symlink. Existing files within such a directory are also never inspected.

**Impact:** An installer can create or overwrite project files in this area without triggering “changed project files.” A successful installer can then receive a dependency stamp and allow the run to continue despite violating the preservation requirement.

**Evidence:** A read-only reproduction invoked the actual `tree_snapshot` function with mocked Git/filesystem responses. Empty, file-containing and symlink states for the same uninitialized gitlink returned identical hashes. The function performed no recursive content inspection or symlink-target read. Existing submodule tests cover initialized submodules only.

**Recommended direction:** Snapshot the actual kind and mode before repository handling. Preserve symlink targets explicitly, and inspect filesystem contents beneath uninitialized submodule directories using defined ignore rules. Add integration regressions for file creation, overwrite and symlink replacement, including unsuccessful installers.

## MINOR findings

### N1 — Wrapped test names receive false “no test named” warnings

**Location:** [scripts/lib/workflow.py:1896](/home/zack/Projects/wt/agents-flow2/scripts/lib/workflow.py:1896); examples: `.ai/handoff.md:68`, `:77`, `:79`, `:83`, `:87`.

**Requirement:** FL-09 flags automated bullets without a backticked test name.

**Problem:** Rendering checks only the bullet’s first physical line. A valid Markdown bullet whose test name appears on an indented continuation line is flagged incorrectly. Checking for any single backtick also does not establish a complete backticked name.

**Impact:** The PR gives misleading coverage warnings for correctly named tests.

**Evidence:** Running the actual PR renderer against this branch’s handoff produced six warnings. Five were false positives for bullets with test names on continuation lines; the unnamed placeholder at `.ai/handoff.md:97` was correctly flagged.

**Recommended direction:** Parse complete Markdown list items and check each item for a nonempty, paired backtick span. Test wrapped names, unnamed bullets and unmatched backticks.

### N2 — Dependency output files are accepted as output directories

**Location:** [scripts/lib/workflow.py:1588](/home/zack/Projects/wt/agents-flow2/scripts/lib/workflow.py:1588).

**Requirement:** FL-01 defines outputs as directories, with a missing output making dependencies stale.

**Problem:** Freshness uses `exists()` instead of checking directory type. With matching stamp/input hashes, a regular file at `node_modules` or another declared output path yields `current`.

**Impact:** The host skips dependency setup even though the required output directory is absent.

**Evidence:** A read-only check invoked the actual `deps_status` function with a matching mocked stamp/spec and an existing regular file as the declared output. It reported `current` while `is_dir()` was false.

**Recommended direction:** Require directories and report missing or incorrect output types clearly. Add regression cases for regular files and broken symlinks at output paths.

## Missing test coverage

The suite lacks the regressions described in M1, N1 and N2. The plan review’s P12 recommendation also remains absent: a committed regression for FINISHED counting when both subsections contain steps. An independent in-memory check confirmed correct counting for two human steps and three automated checks.

## Security concerns

M1 weakens the installer preservation boundary. No additional security defect was demonstrated in the inspected paths.

Host execution of package-manager code and the agent-writable dependency stamp are documented, accepted design choices. They are not sandbox isolation.

## Architecture concerns

The implementation reuses existing helpers and adds no external dependencies. The frozen `.ai/bin` remains unchanged intentionally; target projects require deliberate installation or upgrade.

Flow chart updated: the vault note contains the dependency step, recovery rule, testing split and timer warnings, with `updated: 2026-10-06`. Same-task edit timing cannot be independently established from repository history.

## Manual testing recommendations

### Needs you

After fixes, verify an opted-in timer and STARTED/RESUMED wording on real systemd and phone notifications. Inspect the resulting PR’s human-testing instructions.

### Covered by automated tests

Rerun the full gate in an isolated writable checkout after adding the missing regressions. Retain the existing dependency failure/timeout, recovery, timer-status and legacy-handoff fixtures.

This review does not constitute human acceptance.