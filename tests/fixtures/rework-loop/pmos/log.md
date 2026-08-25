# Log

- GATE 1 passed.
- wave 2 delivered; pm-kb-enrich run (12 new, 3 updated, 0 pruned).
- GATE 2 passed: user approved the plan.
- wave 3: backend delivered T-001.
- wave 4: QA failed A-001 (token replay still possible).
- wave 3: backend reworked T-001.
- wave 4: QA failed A-001 again (different race, same root cause: check and redeem not atomic).
- wave 3: backend reworked T-001 a second time.
- events.py report decision: replan — stop retrying the ladder, re-split the task.
