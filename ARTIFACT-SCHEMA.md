# PMOS artifact schema: stable ids and references

Every wave hands its work to the next as markdown. Ids make that handoff checkable: a task can
say which requirement it delivers, a risk can say which task mitigates it, and QA can report
against criteria instead of prose. `tools/artifacts.py` reads these ids, fails on references
that do not resolve, and emits the node/edge list a traceability graph is built from.

The rule for agents: **prose stays prose, but anything another role must point at gets an id.**

## Entities

| id | kind | defined in | how |
|----|------|-----------|-----|
| `R-NNN` | requirement | `.pmos/charter.md` | a list item: `- R-001: users can reset their password` |
| `T-NNN` | task | `.pmos/plans/plan.md` | a `- id: T-001` block |
| `A-NNN` | acceptance criterion | `.pmos/plans/plan.md` | a `- id: A-001` block |
| `ADR-NNN` | decision | `.pmos/decisions/ADR-*.md` | the `# ADR-001: title` heading |
| `L-NNN` | risk / obligation | `.pmos/out/legal/risk-register.md` | a `- id: L-001` block |

Ids are stable for the life of the project: never renumber, never reuse. `R-1` and `R-001` are
the same id (ids are canonicalized to three digits), so padding drift is not an error.

## Reference fields

Each field points at exactly one kind. Values are comma-separated; empty means none.

| field | on | points at | means |
|-------|----|-----------|-------|
| `satisfies` | task | requirement | this task delivers that scope item |
| `depends_on` | task | task | must land first (the graph must stay acyclic) |
| `decided_by` | task | decision | the ADR that constrains how it is built |
| `verifies` | acceptance | task | this criterion proves that task is done |
| `mitigated_by` | risk | task | the work that discharges the obligation |
| `supersedes` | decision | decision | this ADR replaces an earlier one |

`touches:` on a task takes paths or module names rather than ids. It is not checked against the
repo, but it is what joins this graph to the graphify code graph.

QA reports results in `.pmos/out/qa/test-report.md`, one line per criterion:

```
- A-001: pass - 12 tests green in tests/auth/
- A-002: fail - session still valid after 31 minutes
```

## What the linter enforces

**Errors** (`exit 1`) break traceability and must be fixed:

- a reference to an id nothing defines, or that is not a valid id
- an id defined twice
- a reference pointing at the wrong kind (`satisfies: T-002`)
- a reference field on the wrong kind of entity, or an entity referencing itself
- a `depends_on` cycle
- a QA result for a criterion no plan defines

**Warnings** are coverage gaps. The coordinator may accept them knowingly, and `--strict`
(`exit 2`) refuses to:

- a charter requirement no task satisfies (scope that was never planned)
- a task no acceptance criterion verifies (work that cannot be signed off)
- a criterion the QA report never mentions
- a `severity: high`, `status: open` risk with no `mitigated_by` task
- a risk marked `status: mitigated` whose mitigating task has no passing criterion in the QA
  report — the check ORCHESTRATOR step 10 asks QA to make by hand
- an ADR still marked `accepted` after another ADR supersedes it

## Usage

```
python TPL/tools/artifacts.py --project .                      # report
python TPL/tools/artifacts.py --project . --json               # machine-readable
python TPL/tools/artifacts.py --project . --strict             # warnings fail too
python TPL/tools/artifacts.py --project . --graph .pmos/traceability.json
python TPL/tools/artifacts.py selftest                         # fixture self-check
```

Run it at every gate. It is cheap, deterministic, and needs no model.

## Graph output

`--graph` writes `{"nodes": [...], "edges": [...]}`: one node per entity (with `kind`, `title`,
`file`, `line`, and `role`/`status`/`severity`/`touches`/`qa` when known) and one edge per
reference. That is the project half of the traceability graph; the code half comes from
graphify, joined on a task's `touches` paths.

`tools/trace.py` performs that join and queries it:

```
python TPL/tools/trace.py coverage  --project .    # scope -> task -> criterion -> QA, with gaps
python TPL/tools/trace.py impact T-012 --project . # what rides on one item, down to the code
python TPL/tools/trace.py unplanned --project .    # changed files no task claims
python TPL/tools/trace.py export --project . --out .pmos/traceability.json
```

`touches:` accepts a file, a directory, or a glob, resolved against the files in
`graphify-out/graph.json` — a task claiming `src/auth` picks up every file under it. Without a
code graph the entries stay literal and every other query still works.


## The RDF projection

The markdown is the source of truth; `tools/kg.py` projects it into a triple store so the graph
can be queried instead of traversed by hand. Entity ids become IRIs under
`https://pmos.dev/project#` (`:T-001`), the vocabulary lives under `https://pmos.dev/schema#`
(`pmos:`), and every field and reference becomes one triple.

### Classes

| class | from |
|-------|------|
| `pmos:Requirement` | a charter `R-NNN` |
| `pmos:Task` | a plan `T-NNN` |
| `pmos:AcceptanceCriterion` | a plan `A-NNN` |
| `pmos:Decision` | an `ADR-NNN` |
| `pmos:Risk` | a register `L-NNN` |
| `pmos:File` | a source file a task claims, joined from the graphify code graph |

### Predicates

Asserted from the markdown: `pmos:satisfies`, `pmos:dependsOn`, `pmos:decidedBy`,
`pmos:verifies`, `pmos:mitigatedBy`, `pmos:supersedes`, `pmos:touches`, plus the literal-valued
`pmos:id`, `pmos:title`, `pmos:status`, `pmos:severity`, `pmos:role`, `pmos:law`,
`pmos:jurisdiction`, `pmos:owner`, `pmos:definedIn`, `pmos:path`, `pmos:community`,
`pmos:qaResult`, `pmos:qaEvidence`, `pmos:references`, `pmos:referenceKind`.

Entailed by the inverse rule, so a query can walk either direction: `pmos:satisfiedBy`,
`pmos:blocks`, `pmos:constrains`, `pmos:verifiedBy`, `pmos:mitigates`, `pmos:supersededBy`,
`pmos:touchedBy`. `kg.py stats` reports asserted and entailed counts separately;
`--no-infer` asserts only.

```turtle
@prefix pmos: <https://pmos.dev/schema#> .
@prefix : <https://pmos.dev/project#> .

:T-001 a pmos:Task ;
    pmos:title "password reset endpoint" ;
    pmos:role "backend" ;
    pmos:satisfies :R-001 ;
    pmos:touches :file:src/auth/reset.py .
```

`kg.py build` writes both `graph.ttl` (Turtle, for reading and for other tools) and `graph.nt`
(N-Triples, which `kg.py --from-file` reads back).

### Querying

```
python TPL/tools/kg.py query --project . -q "SELECT ?t WHERE { ?t a pmos:Task }"
python TPL/tools/kg.py query --project . --name unproven-mitigations
python TPL/tools/kg.py ask   --project . -q "ASK { :L-001 pmos:mitigatedBy ?t }"
python TPL/tools/kg.py stats --project .
python TPL/tools/kg.py queries      # list the stored library
```

Supported SPARQL: `SELECT` (with `DISTINCT`) and `ASK`; basic graph patterns with `;` and `,`
lists and `a` for `rdf:type`; `OPTIONAL` (left join); `FILTER` with `BOUND`, comparisons, `&&`,
`||`, `!`, `REGEX`, `CONTAINS`, `STR`; property paths `p+` and `p*` for transitive closure;
`ORDER BY` with `ASC`/`DESC`; `LIMIT`. Results come back as SPARQL 1.1 Query Results JSON with
`--json`.

Deliberately absent: `UNION`, sub-`SELECT`, aggregates, `CONSTRUCT`, named graphs, blank nodes.
The boundary is stated so it is not discovered mid-query.

### The stored library

`queries/*.rq` holds the protocol's own checks as SPARQL — `unplanned-scope`,
`unverified-tasks`, `unproven-mitigations`, `open-high-risks`, `superseded-but-accepted`,
`blast-radius`, `risk-to-code`, `requirement-coverage`, `untested-code`. They are not examples:
`validate.py` asserts that they return the same findings as the Python linter on every fixture
project, so two independent implementations have to agree before the suite goes green.

The linter and the query library are kept as separate views on purpose. `artifacts.py` is the
gate check: no code graph needed, `file:line` diagnostics, runs on every project. The query
library answers open-ended questions the linter was never asked, and `trace.py` uses a
`pmos:dependsOn+` path for its blast radius rather than a second hand-written walk.
