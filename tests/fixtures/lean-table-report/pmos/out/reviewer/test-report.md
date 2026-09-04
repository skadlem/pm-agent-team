# Verification gate - reviewer (lean roster)

## Per-acceptance-criteria table

| Criterion | Status | Evidence |
|---|---|---|
| A-001 a reset token cannot be redeemed twice | **PASS** | `pytest tests/auth/test_reset.py` 6 passed; redemption and check share one transaction |
| A-002 a 31 minute old session is rejected | NOT-APPLICABLE (T-002 unbuilt) | no session module exists yet; scheduled after this phase |
