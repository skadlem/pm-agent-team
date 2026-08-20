# Plan

## Task graph
```yaml
- id: T-001
  title: single-use reset tokens
  role: backend
  satisfies: R-001
  touches: src/auth
```

## Acceptance criteria
```yaml
- id: A-001
  title: a reset token cannot be redeemed twice
  verifies: T-001
  how: tests/auth/test_reset.py::test_token_single_use
```
