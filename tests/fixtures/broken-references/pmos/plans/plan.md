# Plan

```yaml
- id: T-001
  title: password reset endpoint
  satisfies: R-009
  depends_on: T-002
- id: T-002
  title: session expiry
  satisfies: T-001
  depends_on: T-001
- id: A-001
  title: reset mail arrives
  verifies: T-001
- id: A-001
  title: duplicated id
  verifies: T-002
```
