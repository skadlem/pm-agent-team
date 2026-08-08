## Chartering and scope
A project charter is the contract on scope: problem, users, success metrics, in/out scope, stack,
milestones, risks, team. Write it BEFORE any implementation. Scope creep is defeated by an explicit
out-of-scope list. Every feature request after sign-off is a change request: note cost, re-prioritize,
get user decision. Prefer a small MVP scope that proves the core value loop over a big-bang scope.

## Planning
Plan in phases with exit criteria, not just tasks. Each task needs: owner, inputs, outputs, done-
criteria. Sequence by dependencies (task graph); parallelize independents. Keep work-in-progress
low: finish wave N before wave N+1 except for truly independent tracks. Estimate in relative sizes
(S/M/L), not hours. Every plan ends with an explicit verification gate tied to the success metrics.

## Coordination
One decision owner per topic; escalate ties upward. Keep status updates factual: done / next /
blocked. Record decisions where they can be searched later (ADR or log entry with the reason),
because future agents will not remember conversations. Checkpoints after each gate: what shipped,
evidence, what is next. Risk register: likelihood x impact, only act on the top 3-5.
