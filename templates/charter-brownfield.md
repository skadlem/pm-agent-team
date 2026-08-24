# Project Charter: {{name}} (change to an existing project)

Status: draft | Owner: PM agent | Updated: {{date}} | Mode: brownfield

## 0. Before you write this charter (forcing questions)
<!-- Answer these BEFORE drafting; record the answers here, one line each. Adapted from
     gstack's /office-hours methodology (docs/research/2026-08-24-gstack.md), tuned for a
     change to code that already exists. Unknown answers: ASK THE USER, do not invent. -->
1. Demand reality: what specific evidence shows this change is worth the regression risk?
2. Status quo: what happens today without the change, and why is that no longer acceptable?
3. Desperate specificity: which user/operator/hit hurts most, in what concrete case?
4. Narrowest wedge: what is the smallest delta that delivers the value? Everything else is
   out of scope until proven (brownfield scope creep is the top failure mode).
5. Alternatives considered: at least two other ways to reach the same outcome (different
   module, config, no-code), and why this one wins.
6. Premises challenged: which assumptions about the existing code are verified by discovery
   (current-state.md) vs still believed?

## 1. Current state
<!-- Summarized from .pmos/out/architect/current-state.md; link to it for details. -->

## 2. Desired change
<!-- What the user asked for, phrased as a delta on the current state. Give each distinct change
     an id: `- R-NNN: <change>`. Plan tasks point at these with `satisfies:`, so a delta nobody
     planned shows up as a warning rather than as a surprise at QA. See ARTIFACT-SCHEMA.md. -->
- R-001: <change>

## 3. Impact surface
<!-- Which modules/files/areas the change touches, from discovery. Drives the roster. -->

## 4. Do-not-touch list
<!-- Explicit areas, files, or behaviors that must NOT change. Binding for all agents. -->

## 5. Success metrics and acceptance criteria
<!-- Observable, testable. Include "existing behavior unchanged" criteria where relevant. -->

## 6. Compatibility constraints
<!-- API contracts, data formats, config, deployed environments that must keep working. -->

## 7. Tech stack and conventions (from discovery)
<!-- The stack AS IT IS, plus the conventions new code must follow. -->

## 8. Risks
<!-- Include regression risk and its mitigation (existing test baseline, feature flags). -->

## 9. Team
<!-- Role -> responsibility. Justified by the impact surface, not by project type. -->
