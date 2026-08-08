## DevOps fundamentals
Environments: dev = staging = prod in shape, differ only in scale/secrets. Infrastructure as code
or at minimum as a documented script; no snowflake manual setups. CI on every push: build, lint,
test, artifact. CD: one-command deploy, with rollback that is tested at least once.

## Runtime care
Observability minimum: structured logs with request id, error alerting, one latency dashboard,
health checks. Secrets: never in code or logs; env/vault per environment, rotated. Backups:
scheduled, plus periodic restore tests (an untested backup is a hope). Resource hygiene: disk/log
rotation, cost check on cloud spend.

## Security operations
Least privilege everywhere: service accounts scoped per service, no shared keys. Dependencies:
pinned versions, update cadence, vulnerability scan in CI. Incident handling: log what happened,
fix root cause, add the check that would have caught it. Change management: every prod change has a
reversal plan before it happens.
