# Task queue

No project tasks have been defined. Planning must replace this sentence with real
tasks before implementation. Do not count examples as work.

Use headings `## T001 — Title` (a hyphen is also accepted), IDs `T` plus at least
three digits, and exactly one `Status:` and `Dependencies:` line per task.
Dependencies are `none` or comma-separated IDs. Put tasks in dependency order.
Statuses are exactly TODO, IN_PROGRESS, BLOCKED, DONE. Keep at most one task
IN_PROGRESS. DONE requires all dependencies DONE and verified acceptance criteria.
Do not reuse IDs or remove old task results; append review-fix tasks with new IDs.

The following is a FORMAT EXAMPLE ONLY inside a code fence, ignored by tooling:

```markdown
## T001 — <real task title>
Status: TODO
Dependencies: none

### Goal
<Intended outcome and linked specification requirements.>

### Implementation notes
<Constraints and approach; enough for a fresh session.>

### Likely affected modules
<Actual paths discovered in the repository.>

### Acceptance criteria
- <Observable, independently verifiable outcome.>

### Validation
- <Exact deterministic commands and expected outcomes.>

### Result / notes
<Evidence, deviations, failures, or blocker; populated as work proceeds.>
```
