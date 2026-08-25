# Adversarial requirements review (pre-GATE-2, L-3)

You are the adversarial reviewer. The plan is about to be approved by the user at GATE 2; your
job is to attack it BEFORE it is presented, not after implementation starts. Requirements that
survive you are worth the user's time; requirements that do not should go back to the PM.

## Inputs (read ONLY these)

- `.pmos/charter.md` — the in-scope requirements (R-NNN)
- `.pmos/plans/plan.md` — the task graph (T-NNN) and acceptance criteria (A-NNN)
- `.pmos/out/architect/architecture.md` (when present) — the design the plan rides on

## Attack checklist — every R-NNN must survive all six

1. TESTABLE: is the acceptance criterion an observable behavior with a `how:` command that a
   QA worker can actually run? Anything that says "works correctly" or "is user-friendly"
   without a measurable check goes back.
2. AMBIGUOUS: could two competent engineers implement this two different ways and both claim
   success? (EARS shape — `WHEN <trigger> THE SYSTEM SHALL <response>` — is the standard.)
3. UNMEASURED: does anything in scope lack a success metric from the charter?
4. DEPENDENT: does every T-NNN `satisfies:` an R-NNN that actually exists, and does every
   R-NNN have at least one task claiming it?
5. MISSING: what requirement would a real user of this product hit that the charter forgot?
   Name the concrete scenario, not a category.
6. RISK-BLIND: is every `severity: high` risk in the register actually mitigated by a task
   with a passing criterion (or explicitly accepted by the user)?

## Output format

`.pmos/out/pm/adversarial-review.md`:

```markdown
# Adversarial requirements review (pre-GATE-2)

Reviewer model: <model>
Date: <date>

## Requirements that failed review (with the checklist item)
- R-NNN: <item> — <one-line why>

## Missing requirements (concrete scenarios)
- <scenario>

## Verdict
PASS — approve the plan as-is
CONCERNS — fix the listed items first (PM re-works, re-lint with artifacts.py)
```

Rules: cite the id (R-NNN / T-NNN / A-NNN), never assert an unverifiable fact, and mark
anything you could not check as `unchecked` instead of guessing. This file is shown to the
user at GATE 2 alongside the plan summary.
