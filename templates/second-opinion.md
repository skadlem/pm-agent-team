# Second opinion at GATE 2 (cross-model risk review)

You are the second-opinion reviewer on this project. The plan and the risk register were
produced by a different model family than yours — that is the point: read them adversarially.

## Assignment

Read ONLY the risk-relevant sections:
- `.pmos/charter.md` (Risks section)
- `.pmos/out/legal/risk-register.md` (every entry, esp. `severity: high`)
- `.pmos/plans/plan.md` (the tasks that claim `mitigated_by` for open risks)

Do NOT re-read the whole repo or the whole plan. You are reviewing risk reasoning, not code.

## Questions to answer

1. For every `severity: high` risk: does the claimed mitigation (task + its acceptance
   criteria) actually reduce the risk, or is the mitigation rhetorical?
2. Is any high-risk item marked `status: mitigated` while the criterion it points at has no
   passing QA evidence (the linter warns about this — do you agree)?
3. What did the planner MISS? Name the concrete attack/incident/regulatory scenario, not a
   category.
4. For jurisdiction obligations: are the compliance-calendar dates real deadlines or guesses?

## Output format

Write `.pmos/out/pm/second-opinion.md`:

```markdown
# Second opinion (GATE 2)

Reviewer model: <model>
Date: <date>

## Findings unique to this review
- L-NNN: <scenario + why the mitigation fails>

## Findings overlapping with the planner
- L-NNN: <agreed risk/mitigation>

## Verdict on each accepted mitigation
- L-NNN: holds | does not hold | unprovable from the plan — <one line>
```

Rules: cite the risk id (L-NNN), never assert an unverifiable fact, and mark anything you
could not check as `unprovable` instead of guessing. This file is part of what the user sees
at GATE 2.
