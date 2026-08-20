# Plan

## Task graph
```yaml
- id: T-001
  title: password reset endpoint
  role: backend
  satisfies: R-001
  touches: src/auth
```

## Acceptance criteria
```yaml
- id: A-001
  title: reset mail arrives and the new password works
  verifies: T-001
```
