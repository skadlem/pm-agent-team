# Plan

## Task graph
```yaml
- id: T-001
  title: password reset endpoint
  role: backend
  satisfies: R-001
  touches: src/auth
- id: T-002
  title: session expiry
  role: backend
  satisfies: R-002
  depends_on: T-001
  touches: src/session.py
```

## Acceptance criteria
```yaml
- id: A-001
  title: reset mail arrives and the new password works
  verifies: T-001
- id: A-002
  title: a 31 minute old session is rejected
  verifies: T-002
```
