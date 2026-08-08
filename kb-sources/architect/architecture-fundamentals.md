## Architecture decision records
Every significant choice gets an ADR: context, options (pro/con), decision, consequences. Statuses:
proposed/accepted/rejected. ADRs are immutable once accepted; supersede with a new ADR instead of
editing. This is how future agents learn WHY, not just WHAT.

## Core principles
Design for the constraints you have now, not a speculative future (YAGNI). Prefer boring, proven
technology for the core and isolate novelty behind interfaces. Define module boundaries by data
ownership: one module owns each entity, others go through its API. Contracts first: agree on
interfaces (types, endpoints, error shapes) before parallel implementation.

## Data and APIs
Pick the simplest storage that satisfies query patterns and consistency needs; SQL first unless
there is a concrete reason otherwise. APIs: versioned paths, explicit error contracts, input
validation at the boundary, authn/authz at the gateway layer. Idempotency for anything with side
effects. Design for failure: timeouts, retries with backoff, graceful degradation.

## Quality attributes
Performance budgets early (p95 latency, payload sizes). Security by default: least privilege,
secrets out of code, validation everywhere, OWASP top-10 awareness. Operability: if it cannot be
observed (logs/metrics/health), it cannot be run. Prefer deleting complexity over adding abstraction;
each layer must justify its existence.
