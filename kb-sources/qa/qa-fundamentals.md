## QA fundamentals
Test from acceptance criteria, not from implementation: write the expected observable behavior
first. Test pyramid: many unit, some integration, few end-to-end; e2e only for critical user journeys.
Every bug report: exact steps, expected vs actual, environment, minimal repro. A bug fixed without
a regression test is not fixed.

## Verification gate
Definition of done for a milestone: acceptance criteria mapped to executed checks, with evidence
(command + output) recorded. Do not pass a gate on "should work". Negative paths and edge cases
(empty input, huge input, concurrent access, offline/flaky deps) are first-class.

## Non-functional checks
Security smoke: auth bypass attempts, injection probes on all inputs, permission checks per role.
Performance smoke: p95 of the hot path under representative load. Data: backup restore actually
works. Report format: pass/fail per criterion, defects with severity (blocker/major/minor), risk
statement for anything skipped.
