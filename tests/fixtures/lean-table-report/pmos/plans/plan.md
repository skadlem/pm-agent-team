# Plan

## Task graph
```yaml
- id: T-001
  title: single-use reset tokens
  role: implementer
  satisfies: R-001
  touches: src/auth
  test_strategy: pytest tests/auth/test_reset.py
- id: T-002
  title: session expiry
  role: implementer
  satisfies: R-001
  touches: src/auth
  test_strategy: pytest tests/auth/test_session.py
```

## Acceptance criteria
```yaml
- id: A-001
  title: a reset token cannot be redeemed twice
  verifies: T-001
  how: tests/auth/test_reset.py::test_token_single_use
- id: A-002
  title: a 31 minute old session is rejected
  verifies: T-002
  how: tests/auth/test_session.py::test_expiry
```
