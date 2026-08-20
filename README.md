# PMOS: Project Management Operating System (agent team template)

[![CI](https://github.com/skadlem/pm-agent-team/actions/workflows/ci.yml/badge.svg)](https://github.com/skadlem/pm-agent-team/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A portable [jcode](https://github.com/1jehuang/jcode) template that turns "Start the project <idea>" into a managed multi-agent build:
role agents, per-role hybrid knowledge bases, repo understanding via graphify, wave-based execution
with human approval gates, and hard caps so no agent ever carries more context than it needs.

**Requirements:** [jcode](https://github.com/1jehuang/jcode) (agent host with skills + swarm) and Python 3.9+ with SQLite FTS5 (bundled in CPython). No pip dependencies.

## Quick install

```bash
git clone https://github.com/skadlem/pm-agent-team.git
cd pm-agent-team
install.cmd          # Windows
sh install.sh        # macOS/Linux
```

The installer copies the 4 skills into `~/.jcode/skills` and remembers the template location in
`~/.jcode/pmos-template-root` (the folder can live anywhere; move it and re-run the installer if
needed). Global install means the skills are available in EVERY future jcode session, in any
directory. Available trigger phrases:

| you say | mode |
|---------|------|
| "Start the project …" (or `/project-team-start`) | auto-detected (greenfield or brownfield) |
| "Work on this project …" (or `/project-team-work`) | brownfield, forced |

## What's inside

```
pm-agent-team/
  ORCHESTRATOR.md          # operating manual for the main session (waves, gates, rules)
  ARTIFACT-SCHEMA.md       # stable ids (R/T/A/ADR/L) and the references between artifacts
  roster.json              # roles, per-role skills, model suggestions, wave order
  config.json              # KB caps (150K tokens total), context rules
  tools/kb.py              # hybrid KB engine: SQLite FTS5 BM25 + vectors, RRF fusion, caps
  tools/artifacts.py       # artifact id/reference linter + traceability graph export
  tools/eval_project.py    # protocol harness: replays tests/fixtures/ through the tooling
  tools/cost.py            # spend ledger: what workers actually cost vs the GATE 1 budget
  tools/kg.py              # RDF triple store over the artifacts + a SPARQL subset
  queries/                 # the protocol's own checks, as stored SPARQL
  tools/trace.py           # joins that graph to the graphify code graph; coverage/impact queries
  kb-sources/<role>/*.md   # curated fundamentals shipped per role (the "bare agent" KB)
  kb-sources/legal/        # data protection, AI regulation, licensing, register/calendar templates; per-project jurisdiction packs land in .pmos/kb-sources/legal/
  kb-sources/shared/       # agent operating rules (partial-context, evidence, etc.)
  templates/               # charter.md, plan.md, adr.md skeletons (id-bearing)
  skills/                  # project-team-start, project-team-work, pm-kb-bootstrap, pm-kb-enrich
  install.cmd / install.sh # copy skills to ~/.jcode/skills, record template root
```

## Roles

project manager/planner, architect, designer, backend, frontend, business advisor, marketing,
QA engineer, devops (security folded in), legal advisor (risk & policy): regulatory risk
assessment per deployment jurisdiction, risk register, compliance calendar (strict/light via
config.json). Each role has assigned jcode skills, a KB namespace,
expected artifacts, and a model chosen at launch (user-approved).

## Model selection (computed at launch, not hardcoded)

At GATE 1 the coordinator runs `swarm list_models`, saves its output, and runs
`python TPL/tools/recommend.py --available <file>` which:

1. Keeps only AVAILABLE models from the live list.
2. Drops models the roster forbids (`forbidden_models`: never suggested, never laddered)
   and older generations per family (`newest_only`: e.g. only claude-opus-5, never
   claude-opus-4-7/4-8; only claude-sonnet-5; only qwen3.8-max).
3. Scores each against per-purpose benchmarks (`benchmarks.json`): reasoning, coding, design,
   business, marketing, verification, ops, writing. Each role maps to a purpose mix
   (`roster.json` -> `model_suggestions` -> `purpose`, weights sum to 1).
4. Keeps each role's BEST TIER (score >= role's `role_tiers` threshold in roster.json; default
   0.92, critical roles like pm/architect/qa use 0.95, advisory roles 0.80), then picks the
   CHEAPEST of that tier by blended cost (3:1 input:output, USD per 1M tokens).
5. Outputs the role -> model table for you to OK, edit, or remove. The approved map is saved
   to `.pmos/team-model.json` and used for every spawn.

That recommended model is only the FIRST attempt. Pass `--ladder-out .pmos/team-model-ladder.json`
and `recommend.py` also writes each role's best-first fallback ladder. If a worker fails (runs out
of tokens, crashes, or hits an unrecoverable error), the coordinator retries the same task on the
next model in that role's ladder (up to `context_rules.max_fallbacks_per_task` = 4 fallbacks,
then escalates to you) instead of abandoning
it. See ORCHESTRATOR.md "Worker model fallback".

When the same model is served by several providers on this system (e.g. `glm-5.2` via the Aliyun
MaaS gateway and `z-ai/glm-5.2` via NVIDIA NIM), `recommend.py` merges them into ONE ladder entry
and reports the providers as an ordered fallback chain (`suggested_provider` +
`suggested_fallbacks`, full map in the `providers`/`routes` JSON fields). Retry on the next
provider in the chain before moving down the ladder.

`benchmarks.json` is GENERATED from Epoch AI's benchmark hub data (CC BY 4.0,
`benchmark_data/`, ~75 benchmark CSVs: SWE-bench Verified, GPQA, ARC-AGI, MMLU, webdev,
terminalbench, etc.), merged with **LiveBench** (livebench.ai, contamination-free,
fetched from the `LiveBench/new-livebench` repo) as a third source. Regenerate it whenever
you refresh the data:

```
python TPL/tools/build_benchmarks.py --data-dir <path/to/benchmark_data> --out benchmarks.json
```

Scores are per-benchmark min-max normalized to 0-100 (handles arbitrary scales and
lower-is-better benchmarks), then averaged per purpose. LiveBench category scores
(reasoning, coding, agentic coding, math, data analysis, language, instruction-following)
are min-max normalized per category and mapped to purposes via `LIVEBENCH_PURPOSE` in the
generator. Costs come from a curated pricing overlay (Epoch has no prices), supplemented
from LiveBench's cost file for models the overlay lacks; models without pricing get null
cost, which the recommender treats as "expensive" when choosing within the best tier.

Cost guardrail: config.json `cost.max_project_cost_usd` (default 20) caps project spend. At
GATE 1 you approve a `budget_usd`, and from then on `tools/cost.py` keeps an append-only ledger
of what workers actually burned (`.pmos/costs.jsonl`, one JSON object per run), priced from
`benchmarks.json` (`cost_in`/`cost_out` per 1M):

- after each worker returns, the coordinator runs `cost.py record` with the token counts from the
  swarm result — failed runs included, since a worker that died on a context limit still cost money
- before each wave, `cost.py estimate --roles ...` prices what is about to be spawned, using THIS
  project's measured medians for roles that have history (`cost.py calibrate --write`) and the flat
  `cost.est_tokens_per_worker` default only for roles that do not
- `cost.py report` shows spend per role/wave/model against `budget_usd`, keeps measured and
  estimated spend apart, flags unpriced models rather than counting them as free, and prints how
  far the flat config estimate is from reality so it can be corrected with evidence
- `estimate` and `report` exit 2 when the cap would be or has been breached, so a wave can be
  gated on them; `state.py` reports the same on resume

Nothing is invented: if the agent host does not report usage, `record --source estimated` keeps
the guess visibly a guess. Advisory roles default to `low`
reasoning effort (roster.json `role_effort`) to cut cost further.

LiveBench flags:
- `--livebench-date <suffix>` — which release to fetch (default `2026_06_25`, the latest).
- `--no-livebench` — skip the LiveBench fetch/merge (Epoch-only build).
- `--livebench-only` — build from LiveBench alone (no Epoch CSVs, no baseline); rankings
  reflect only LiveBench category scores. Note: LiveBench has no design or verification
  categories, so those roles get no suggestion. Example:
  `python TPL/tools/build_benchmarks.py --livebench-only --out benchmarks-livebench.json`
  then `python TPL/tools/recommend.py --available <file> --benchmarks benchmarks-livebench.json`.
- `--baseline <existing benchmarks.json>` — seed from a previous file when the raw Epoch
  CSVs are absent, so a regeneration only ADDS LiveBench instead of dropping curated data.
  The baseline may itself already contain a LiveBench merge: models already carrying one are
  preserved byte-identically (regeneration is idempotent, no double-counting), and only the
  `as_of` date advances.

Route ids that differ from dataset names are aliased (e.g. `gpt-5.6-pro[web]` -> the
closest scored 5.6-class entry). Models with no benchmark data are reported explicitly and
can be picked manually by the user.

## Install

See **Quick install** above. After installing, restart jcode or reload skills; verify with
`/project-team-start` showing up in your skill list.

## Usage

In any project directory, any session:

```
Start the project <one-paragraph description>
```

or `/project-team-start`. The mode is detected automatically. For an EXISTING codebase you can
also use the dedicated phrase **"Work on this project <what you want changed>"** (or
`/project-team-work`), which forces brownfield mode:

- **Greenfield** (empty repo): charter -> plan -> minimal team proposal -> YOU approve ->
  design wave -> KB enrichment -> YOU approve plan -> implementation -> QA gate -> checkpoint.
- **Brownfield** (existing code): extra Wave 0 first. An architect worker maps the
  codebase via graphify into `current-state.md` (modules, conventions, test state, impact areas);
  the PM writes a delta charter with a do-not-touch list; the roster is justified by impact
  surface (backend-only change => no designer); QA starts from the existing test baseline;
  workers must conform to existing conventions before writing code. `.pmos/kb.sqlite3` goes in
  the project `.gitignore`; all other `.pmos/` state is plain markdown and gets committed.

Resume any later session in the same directory the same way; it detects `.pmos/` and continues
from the log. The KB and graphify index persist.

## Knowledge base design

- One SQLite store per project: `.pmos/kb.sqlite3`, namespaced per role (+ `shared`).
- Hybrid search: BM25 (SQLite FTS5) + vector cosine, fused by reciprocal rank fusion.
  Offline by default (deterministic hashed vectors). For real embeddings set
  `PMOS_EMBEDDINGS_URL` + `PMOS_EMBEDDINGS_KEY` + `PMOS_EMBEDDINGS_MODEL` (OpenAI-compatible
  /embeddings endpoint), then `kb.py reindex-vectors`.
- Re-indexing is idempotent. A chunk is identified by (namespace, source file, section
  heading): re-running `add-dir` after an artifact changes REPLACES those sections in place and
  prunes the ones deleted from the file (`--no-prune` opts out). So `/pm-kb-enrich` can be re-run
  after every scope change without a superseded ADR lingering in the index next to the current
  one. Stores written before this (schema v1) are deduped automatically on first open.
- Token caps: 150K total, shared budget 15K + role-weighted pools. Overflow drops
  lowest-priority chunks first (scraped top-ups before curated fundamentals; project facts rank
  highest below shared rules). Check with `kb.py budget`.
- Agents only ever get search excerpts; repo questions go through graphify queries. Full dumps
  are forbidden by protocol.

### CLI

```
python tools/kb.py init --db <db>
python tools/kb.py add --db <db> --ns <role> --title "..." --content "..." [--priority N]
python tools/kb.py add-dir --db <db> --ns <role> --path <dir> [--priority N] [--no-prune]
python tools/kb.py search --db <db> "query" [--role <role>] [-k N] [--json]
python tools/kb.py budget --db <db> --config config.json
python tools/kb.py stats --db <db>
python tools/kb.py clear --db <db> --ns <role>
python tools/kb.py reindex-vectors --db <db>
python tools/kb.py selftest
python tools/artifacts.py --project . [--json] [--strict] [--graph out.json]
python tools/artifacts.py selftest
python tools/trace.py coverage --project .        # scope -> task -> criterion -> QA
python tools/trace.py impact T-012 --project .    # what rides on one item, down to the code
python tools/trace.py unplanned --project .       # changed files no task claims
python tools/cost.py record --project . --role backend --model <m> --in N --out N
python tools/cost.py report --project .           # spend vs budget_usd, estimate accuracy
python tools/cost.py estimate --project . --roles backend,frontend
python tools/cost.py calibrate --project . --write
python tools/kg.py build --project .              # graph.ttl + graph.nt
python tools/kg.py query --project . --name unproven-mitigations
python tools/kg.py query --project . -q "SELECT ?t WHERE { ?t a pmos:Task }"
python tools/kg.py stats --project .
python tools/state.py --project . --config config.json   # resume: stage + pre-flight checks
python tools/recommend.py --available models.txt --ladder-out .pmos/team-model-ladder.json
```

On resume, `state.py` tells you where the project left off (stage 0..9 derived from artifacts on
disk), whether everything before that stage is intact (pre-flight checks), and the next launch
step — see ORCHESTRATOR.md "Resume in a future session".

## Artifact traceability

Waves hand work to each other as markdown, so anything another role must point at carries a
stable id: charter requirements `R-NNN`, plan tasks `T-NNN`, acceptance criteria `A-NNN`,
decisions `ADR-NNN`, risks `L-NNN`. Tasks say what they `satisfy`, criteria say what they
`verify`, risks say what task `mitigates` them. Full field reference: [ARTIFACT-SCHEMA.md](ARTIFACT-SCHEMA.md).

`python tools/artifacts.py --project .` turns checks that used to need an agent re-reading prose
into a deterministic pass:

- **errors** (block GATE 2): a reference to an id nothing defines, a duplicate id, a reference
  pointing at the wrong kind, a `depends_on` cycle, a QA result for a criterion no plan defines.
- **warnings**: scope no task claims, a task no criterion verifies, a criterion QA never
  reported on, a high-severity open risk with no mitigating task, and a risk marked `mitigated`
  whose task has no passing criterion — the check ORCHESTRATOR step 10 previously asked QA to
  make by eye.

`state.py` runs the same lint in its resume pre-flight.

### Querying the graph

Each task's `touches:` paths join the project graph to the graphify code graph, and
`tools/trace.py` queries the result:

```
$ python tools/trace.py coverage --project .
R-001  users can reset their own password
    T-001  password reset endpoint  [backend]
        touches: src/auth/mail.py, src/auth/reset.py
        A-001  reset mail arrives and new password works    PASS
R-003  admins can see an audit log
    (nothing planned)

2/3 requirements planned | 2/2 tasks verified | 2/2 criteria reported, 1 passing
  gap: R-003 is in scope but no task satisfies it

$ python tools/trace.py impact L-001 --project .
L-001  reset token stays valid after use
  mitigated_by   T-001
  evidence       A-001 via T-001 (pass)
  touches        src/auth/mail.py, src/auth/reset.py
  status         mitigated
  severity       high
```

`impact` walks either direction from any id — a task shows the requirement it serves, the ADR that
constrains it, the criteria and their QA results, the work it transitively blocks, the files it
touches and the code importing those files. `unplanned` inverts it: changed files no task claims,
which catches scope creep in the wave that caused it rather than at QA. `export` writes the whole
joined graph, code files included, as JSON.

`touches:` resolves a file, a directory, or a glob against `graphify-out/graph.json`; without a code
graph the entries stay literal and every query still works.

## The knowledge graph

The markdown under `.pmos/` is the source of truth; `tools/kg.py` projects it into an RDF-style
triple store so the graph can be queried rather than traversed by hand. Entities become IRIs
(`:T-001`), fields and references become triples under a `pmos:` vocabulary, and the code join
brings in `pmos:File` subjects from graphify:

```turtle
:T-001 a pmos:Task ;
    pmos:title "password reset endpoint" ;
    pmos:satisfies :R-001 ;
    pmos:touches :file:src/auth/reset.py .
```

An inverse rule entails `pmos:satisfiedBy`, `pmos:blocks`, `pmos:verifiedBy`, `pmos:mitigates`
and friends, so queries walk either direction; `kg.py stats` reports asserted and entailed
triples separately.

`kg.py query` runs a SPARQL subset — `SELECT`/`ASK`, basic graph patterns, `OPTIONAL`, `FILTER`
(`BOUND`, comparisons, `REGEX`, `CONTAINS`), property paths `p+`/`p*`, `ORDER BY`, `LIMIT` —
and returns SPARQL 1.1 Results JSON with `--json`. The full vocabulary and the exact supported
grammar are in [ARTIFACT-SCHEMA.md](ARTIFACT-SCHEMA.md).

`queries/` holds the protocol's own checks as stored SPARQL. This one is the four-hop join from a
legal obligation to the code that discharges it and the test that proves it:

```sparql
SELECT ?risk ?law ?task ?file ?result WHERE {
    ?risk a pmos:Risk ; pmos:mitigatedBy ?task .
    OPTIONAL { ?risk pmos:law ?law }
    OPTIONAL { ?task pmos:touches ?f . ?f pmos:path ?file }
    OPTIONAL { ?criterion pmos:verifies ?task ; pmos:qaResult ?result }
}
```

They are not decoration: `validate.py` asserts the stored queries return the same findings as the
Python linter on every fixture project, so two independent implementations must agree before the
suite passes.

## Customizing

- Caps/weights: `config.json`. Roles/skills/waves/models: `roster.json`.
- Fundamentals: edit `kb-sources/<role>/*.md` (markdown, one `## ` heading per fact block).
- Protocol behavior: `ORCHESTRATOR.md`. Skills are plain markdown; tweak freely.
- After any edit, run `python tools/validate.py` to verify budget math, skill references,
  model suggestions, documented CLI commands, skill frontmatter, bootstrap, and edge cases.

## Measuring performance

Four levels, cheapest first:

1. **Component correctness (CI, automatic):** `python tools/kb.py selftest` and
   `python tools/validate.py` (127 checks: budget math, frontmatter, bootstrap, edge cases,
   recommender semantics, re-index idempotency and pruning, artifact id schema, installer
   idempotency), `python tools/artifacts.py selftest` and `python tools/trace.py selftest`.
2. **Retrieval quality (CI, automatic):** `python tools/eval_kb.py` runs two golden query sets
   (30 standard + 20 paraphrased queries) against a freshly built KB and reports hits@5 and MRR,
   comparing the default hybrid search against its single-signal baselines (ablation):

   | set | mode | hits@5 | MRR |
   |-----|------|-------:|----:|
   | standard | hybrid (shipped default) | 100% | 1.000 |
   | standard | BM25 only | 100% | 1.000 |
   | standard | offline vectors only | 100% | 0.922 |
   | paraphrase | hybrid | 100% | 0.792 |
   | paraphrase | BM25 only | 85.0% | 0.800 |
   | paraphrase | offline vectors only | 100% | 0.604 |
   | standard | **hybrid, Gemini embedding-2** (measured 2026-08-08, pre-legal corpus) | **100%** | **1.000** |
   | standard | Gemini vectors only (measured 2026-08-08, pre-legal corpus) | 100% | **1.000** |
   | paraphrase | **hybrid, Gemini embedding-2** (measured 2026-08-08, pre-legal corpus) | **100%** | **0.833** |
   | paraphrase | Gemini vectors only (measured 2026-08-08, pre-legal corpus) | 100% | **0.889** |

   Pass threshold for hybrid on the standard set: hits@5 >= 90% and MRR >= 0.65. If you edit
   `kb-sources/`, keep the golden set in `tools/eval_kb.py` aligned.

   **Using real embeddings:** set `PMOS_EMBEDDINGS_URL`, `PMOS_EMBEDDINGS_KEY`,
   `PMOS_EMBEDDINGS_MODEL` and run `kb.py reindex-vectors`. Gemini's native endpoint
   (generativelanguage.googleapis.com) is auto-detected and authenticated with the API key
   (`x-goog-api-key`); other URLs use OpenAI-compatible `Authorization: Bearer`. Rate-limit
   responses (429) are retried with backoff. Rerun the API-backed benchmark with
   `python tools/eval_kb_api.py`. Full recorded results, methodology and the weight-tuning
   sweep: [EVALUATION.md](EVALUATION.md). Headline: Gemini embedding-2 lifts vector MRR on
   paraphrased queries from 0.604 to 0.889 (recall already 100%); the gain grows with KB size.
   When `--role` is given, search ranks within that namespace only (BM25 and vectors alike), so a
   small namespace is never drowned out by a large one; role-scoped search also skips the
   cross-namespace fusion pass entirely.
3. **Protocol behaviour (CI, automatic):** `python tools/eval_project.py` replays the fixture
   projects in `tests/fixtures/` through `state.py`, `artifacts.py` and `trace.py` and asserts what
   the coordinator would be told: the stage and next step, the traceability findings, the coverage
   summary, and whether GATE 2 blocks. Each fixture pins one failure mode — a broken handoff, an
   open high-severity risk, a QA gate that failed while legal claimed the risk mitigated, code
   changed that no task claims. No model is spawned, so it is deterministic and free; it proves the
   machinery and the gate decisions, not the quality of what agents write. Add a fixture whenever
   you change protocol behaviour: `tests/fixtures/<name>/` with `expect.json`, a `pmos/` tree
   (undotted so the template's own `.gitignore` keeps it), optional `files/` and `graphify/`.

4. **Per-run project metrics:** every checkpoint in `.pmos/log.md` records workers spawned,
   QA gate results, defect counts, rework loops, KB budget usage, and acceptance pass rate.
   Compare these across projects to see if the system improves.
5. **Outcome evaluation (manual):** after a project, judge the deliverables themselves:
   did the acceptance criteria actually hold under real use, how much rework was needed after
   handoff, and whether the KB enrichment step saved workers from re-reading upstream artifacts
   (spot-check a worker's KB search logs against its behavior).

## License and attribution

- Code and template: [MIT](LICENSE).
- `benchmarks.json` scores derive from [Epoch AI's benchmark hub](https://epoch.ai/benchmark-data) dataset (CC BY 4.0). Keep attribution when redistributing derived data.
