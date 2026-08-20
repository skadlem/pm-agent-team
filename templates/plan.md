# Plan: {{name}}

Status: draft | Owner: PM agent | Updated: {{date}}

## Phases
<!-- Wave-aligned. One line each: what lands in it, what it unblocks. -->

## Task graph
<!-- One `- id: T-NNN` block per task, ids stable for the life of the project.
     title (required), role (an approved roster role), satisfies (the charter
     R-ids this task delivers), depends_on (tasks that must land first; no
     cycles), decided_by (the ADRs that constrain it), touches (paths or
     modules - what joins this task to the code graph). Empty means none.
     Full field reference: ARTIFACT-SCHEMA.md. -->

```yaml
- id: T-001
  title: <what lands when this is done>
  role: backend
  satisfies: R-001
  depends_on:
  decided_by:
  touches:
```

## Acceptance criteria
<!-- One `- id: A-NNN` block per criterion. Each verifies exactly ONE task and
     must be observable: QA reports it as `- A-NNN: pass|fail - evidence`.
     Every task needs at least one, or it cannot be signed off. -->

```yaml
- id: A-001
  title: <observable outcome, not "works correctly">
  verifies: T-001
  how: <the command or check that proves it>
```

## Out of plan
<!-- Work deliberately deferred, so it is not silently dropped. -->
