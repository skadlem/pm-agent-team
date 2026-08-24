# PMOS Evaluation Report

Two things are measured automatically: how well the KB retrieves (below), and whether the
protocol behaves correctly end to end ([protocol harness](#protocol-harness-toolseval_projectpy)).

## Retrieval

Recorded 2026-08-08 on the shipped corpus (10 role namespaces + shared, 30 chunks total,
~2.4K tokens). Re-measured 2026-08-10 after the legal role's fundamentals joined the corpus
(11 role namespaces + shared, 44 chunks total, ~4.1K tokens) and the golden set grew to 30
standard + 20 paraphrase queries (3 legal queries in each set). Re-measured 2026-08-24 after
the golden set grew again to 45 standard + 33 paraphrase queries so that EVERY corpus section
has at least one standard query (a coverage guard in eval_kb.py enforces this; before 2026-08-24,
15 of 44 sections — the whole 2026-08 legal template corpus plus 3 older sections — had none,
and the "100% standard" result only covered the sections that happened to be queried). Benchmark:
`tools/eval_kb.py` with two golden query sets:

- **standard** (45 queries): phrased like the fundamentals' vocabulary; every corpus section
  has at least one (coverage guard).
- **paraphrase** (33 queries): reworded with minimal keyword overlap, e.g.
  "the deploy broke production, how do we undo it" -> DevOps fundamentals.
  This set exists because a perfect score on the standard set proves nothing about
  real agent behavior.

Metric: hits@5 (correct chunk in top 5) and MRR (mean reciprocal rank, 1.0 = always rank 1).

## Results

Current corpus (44 chunks), golden set 45 standard + 33 paraphrase, measured 2026-08-24:

| set | mode | hits@5 | MRR |
|-----|------|-------:|----:|
| standard | hybrid, offline vectors | 100% | 1.000 |
| standard | BM25 only | 100% | 1.000 |
| standard | offline vectors only | 100% | 0.948 |
| paraphrase | hybrid, offline vectors | 93.9% | 0.725 |
| paraphrase | BM25 only | 90.9% | 0.843 |
| paraphrase | offline vectors only | 81.8% | 0.519 |

Note the honest shift vs the pre-2026-08-24 rows (paraphrase hybrid 100%/0.792): the new
paraphrase queries deliberately include vocabulary-gap cases ("make a table of every
dependency", "the model provider's terms forbid what we planned to build") where no lexical
signal matches the corpus wording. Those are exactly the queries real embeddings should win;
the offline engine's misses are now visible instead of unmeasured.

Earlier corpus measurements (30-44 chunks, 30+20 queries):

| set | mode | hits@5 | MRR |
|-----|------|-------:|----:|
| standard | hybrid, offline vectors | 100% | 1.000 |
| standard | BM25 only | 100% | 1.000 |
| standard | offline vectors only | 100% | 0.922 |
| standard | **hybrid, Gemini embedding-2** | **100%** | **1.000** |
| standard | Gemini vectors only | 100% | 1.000 |
| paraphrase | hybrid, offline vectors | 100% | 0.792 |
| paraphrase | BM25 only | 85.0% | 0.800 |
| paraphrase | offline vectors only | 100% | 0.604 |
| paraphrase | **hybrid, Gemini embedding-2** | **100%** | **0.833** |
| paraphrase | Gemini vectors only | 100% | **0.889** |

## What Gemini embedding-2 actually improved (measured 2026-08-08, pre-legal corpus)

- **Recall (hits@5): no change.** Even offline hashed vectors find the right chunk at this
  corpus size; BM25 alone misses 3/18 paraphrase queries that vectors catch.
- **Ranking (MRR): vector MRR 0.588 -> 0.889 (+0.30) on paraphrase queries.** The right
  excerpt now lands at rank 1 instead of 3-4 when agents ask in their own words.
- **Hybrid MRR 0.806 -> 0.833 (+0.027).** Hybrid uses additive reciprocal-rank fusion
  (RRF), which structurally cannot beat its best input list: a chunk at vector rank 1
  and BM25 rank 2 ties a chunk at rank 1 in both, and ordering between ties is insertion
  order. Weights (tested 0.50-0.90 for the vector share) do not change this at the top of
  the list. The hybrid stays at >= min(inputs), i.e. strictly safer than either signal alone.
- **Capacity:** bootstrapping a project KB costs ~60 embedding calls; each search costs 1.
  Comfortably within 100 RPM.

The Gemini rows above and in the table were recorded on the pre-legal corpus (30 chunks,
27+18 queries). The 2026-08-10 offline re-measurement covers 44 chunks and 30+20 queries;
re-run `python tools/eval_kb_api.py` with an embeddings backend configured to refresh the
Gemini rows on the current corpus.

On 2026-08-10 role-scoped search (`--role`) also changed: the BM25 pass is now scoped to the
namespace like the vector pass already was, instead of fetching the global top-k and filtering.
Paraphrase BM25 recall rose 80% -> 85% (a role chunk is no longer drowned out by other
namespaces), hybrid paraphrase MRR moved 0.850 -> 0.792, and vector rows are unchanged.

## Expectation for larger corpora

The gain is understated here because the corpus is tiny (44 chunks). As role namespaces grow
with `pm-kb-enrich` project facts and scraped top-ups toward their budgets, BM25 lexical
collisions increase and offline hashing degrades; real embeddings' advantage compounds.
Re-run this benchmark after a few real projects to confirm.

## Engine tuning tried and rejected (2026-08-24, current corpus)

Measured on both golden sets before changing anything; every variant either lost on
paraphrase or only moved tie noise:

- **Stopword removal in the FTS5 query** — paraphrase MRR 0.792 -> 0.771 (one recovery,
  two regressions). The porter tokenizer already absorbs most of the value.
- **FTS5 prefix queries** (`"token"*`) — fixes morphological misses ("experiment" matching
  "experimental") but loses elsewhere: 0.792 -> 0.733. Porter stemming on both sides makes
  prefix expansion net-negative at this corpus size.
- **bm25() column weights** (title 2.0x) — 0.733. Titles are already chunk identity; the
  collision is body vocabulary, not title weight.
- **Score-level fusion** (normalized BM25 + cosine, weights 0.35-0.65) vs RRF — 0.775 at
  best. RRF's rank-only fusion is at least as good here.
- **Deterministic RRF tie-break** (higher vector similarity) — 0.667: WORSE. At 44 chunks the
  top-of-list RRF scores differ in the 4th decimal; any tie-break is a coin flip and the
  current insertion-order one happens to be the better coin.
- **Offline vector dimension 64 -> 128 -> 256** — vector-only paraphrase MRR 0.604 -> 0.633
  -> 0.667, hybrid 0.792 -> 0.775 -> 0.800. Not worth the storage and re-index cost at this
  corpus size; revisit with real corpora.
- **IDF-weighted hashed vectors** — hybrid 0.792 -> ~0.80, vector 0.604 -> 0.729. Modest, but
  it needs corpus-global IDF at index time (a schema/flow change) for a gain that real
  embeddings dwarf.

Conclusion: at this corpus size the offline engine is at its ceiling; the remaining paraphrase
gap is vocabulary mismatch, which is what semantic embeddings are for. The productive lever was
measurement (full section coverage + honest vocabulary-gap queries), not the fusion knobs.

## Recency decay (2026-08-24)

Search now multiplies each fused score by `0.5^(age_days / half_life)` (half-life from
`config.json` `kb.recency_half_life_days`, default 180), floored at 1/3 so age alone can never
demote a chunk more than 3x. Motivation: once a project KB accumulates facts over months, a
superseding ADR should outrank the one it replaced without waiting for a prune. On a FRESHLY
BUILT KB every chunk shares one index date, so the factor is 1.0 and the decay is a no-op —
measured here: all hybrid/BM25/vector numbers above are identical with the decay on.
`kb.py search --no-decay` switches it off for ablations; `kb.py selftest` pins the ordering
property (a 400-day-old twin loses its near-tie to the fresh copy).

## Reproducing

```
python tools/eval_kb.py                    # offline baseline (no API needed)
python tools/eval_kb_api.py                # same benchmark using PMOS_EMBEDDINGS_* env vars
```

Gemini setup (native endpoint auto-detected, `x-goog-api-key` auth, 429 retried with backoff):

```
setx PMOS_EMBEDDINGS_URL "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"
setx PMOS_EMBEDDINGS_KEY "***"
setx PMOS_EMBEDDINGS_MODEL "gemini-embedding-2"
```
(then `python tools/kb.py reindex-vectors --db <db>` for existing KBs).

Optional tuning: `PMOS_HYBRID_VEC_WEIGHT` (default 0.65) sets the vector share of hybrid
fusion when the KB was indexed with an embeddings API. Measured flat 0.50-0.90 on the
current corpus; only worth revisiting on larger corpora.

## Baseline policy

- CI fails if hybrid on the standard set drops below hits@5 90% or MRR 0.65.
- This report is the recorded baseline; update it (with date) whenever kb-sources,
  kb.py fusion, or the embedding backend changes materially.


## Protocol harness (tools/eval_project.py)

Retrieval quality is one component. The harness measures the layer above it: given a `.pmos/`
tree at some stage, does the tooling tell the coordinator the right thing? Each fixture in
`tests/fixtures/` is a whole project — charter, plan, ADRs, risk register, QA report, optionally a
source tree and a graphify graph — plus an `expect.json` stating what `state.py`, `artifacts.py`
and `trace.py` must report.

| fixture | pins |
|---------|------|
| `greenfield-planning` | wave 1 complete: all scope planned and verifiable, no findings |
| `broken-references` | a handoff to ids nothing defines: dangling ref, wrong kind, duplicate id, dependency cycle |
| `gate2-blocked-risk` | unplanned scope plus an open high-severity GDPR risk: GATE 2 must block |
| `qa-failed-mitigation` | QA failed the only criterion while legal claims the risk mitigated |
| `scope-creep` | a do-not-touch file changed that no task claims |
| `over-budget` | a retried worker pushed measured spend past the GATE 1 cap |

The GATE 2 verdict is derived from tool output (`errors > 0`, or an open high-severity risk),
not from a judgement call, so the harness also checks that the tools surface enough to make the
gate decision mechanically.

Spend is checked the same way: the harness reads `cost.py report --json` for the fixture's
ledger and asserts the totals, the remaining budget, and that an over-budget project exits 2.

**What it does not cover.** No model is spawned, so it says nothing about the quality of what
agents write — whether a charter is any good, whether an ADR chose well. That remains the manual
outcome evaluation (README level 5). What it does cover is every deterministic decision the
protocol makes about a project's state.

### What it caught on the first run

`state.py` reported a project whose QA gate **failed** as stage "checkpointed / all 11 steps
complete; project finished". Stage 8's marker was "a test report exists", but ORCHESTRATOR step 10
sends a failed gate back to wave 3. On resume, the coordinator would have been told a project
needing rework was done. Stage 8 now requires the report to show no `fail`/`blocked` criterion, and
a failed gate rolls the stage back to implementation with "Wave 4 QA gate" as the next step.

### Keeping it honest

Every fixture was mutation-tested: reverting the stage-8 marker, removing the linter's
dangling-reference error, and dropping untracked files from `unplanned` each made exactly one
fixture fail. A fixture that cannot fail is not a test — see the two checks in this repo's history
that passed without asserting anything.

### Adding a fixture

```
tests/fixtures/<name>/
  expect.json     stage, lint findings (substring match), coverage summary, unplanned, gate2
  pmos/           becomes .pmos/ (undotted so the template's .gitignore keeps it)
  files/          optional source tree
  graphify/       optional graph.json, becomes graphify-out/
```

`expect.json` matches messages by substring, so wording changes do not break fixtures; counts and
stages are exact. Add one whenever you change protocol behaviour.


## RDF conformance

`kg.py` emits Turtle and N-Triples and runs its own SPARQL subset, so the obvious question is
whether that is real RDF or merely RDF-shaped. `validate.py` answers it when
[rdflib](https://rdflib.dev) is importable, and skips rather than depending on it (the template
takes no pip dependencies):

- rdflib parses both `graph.ttl` and `graph.nt` into the **identical triple set** our store holds
  — not just the same count.
- rdflib's SPARQL engine and ours return the same bindings for the same query.

Measured 2026-08-21 against rdflib 7.6.0 on the shipped fixtures: 70/70 triples matching on the
demo project, identical sets, and agreement on basic graph patterns, `FILTER`, and the
`pmos:dependsOn+` property path.

Two bugs came out of that check, both of which self-written tests had missed:

- `:file:src/auth/reset.py` was emitted as a prefixed name, which Turtle forbids — `PN_LOCAL`
  has no `/`. Such IRIs are now written in full, and rdflib accepts the output.
- `PREFIX pmos: <...>` failed to tokenize, because the prefixed-name pattern required a non-empty
  local part. Every SPARQL query copied from any tutorial opens with a `PREFIX` line, so the
  engine would have rejected essentially all pasted queries.

## Two implementations, one answer

`artifacts.py` (Python linter) and `queries/*.rq` (stored SPARQL) check the same protocol rules by
different routes. `validate.py` asserts they return the same findings on **every** fixture project,
so a change to either that alters behaviour breaks the suite. The linter stays the gate check — it
needs no code graph and gives `file:line` diagnostics — while the query library answers questions
nobody thought to hard-code.
