## Backend engineering fundamentals
Structure code around the domain, not the framework: handlers/controllers thin, business logic in
plain functions/classes, I/O isolated at the edges. Validate at boundaries, trust nothing across a
process or network line. Errors: typed, catchable, with context; never swallow exceptions silently.

## Data and APIs
Schema-first: migrations reviewed like code, no manual DB edits in prod paths. Transactions around
multi-write operations. Pagination and filtering on every list endpoint by default. Cache only what
is measured slow, always with an invalidation story. Background jobs: idempotent, retriable,
observable.

## Testing and reliability
Unit tests for logic, integration tests for boundaries (DB, HTTP), contract tests for API shape.
Test behavior, not implementation. Deterministic tests: no sleeps, no network, seeded randomness.
Log structured (level, request id, event), never secrets. Health endpoint reflects real dependency
status. Concurrency: shared state is a bug magnet; prefer message passing or immutable handoffs.
