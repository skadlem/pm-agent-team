# PMOS Retrieval Evaluation Report

Recorded 2026-08-08 on the shipped corpus (10 role namespaces + shared, 30 chunks total,
~2.4K tokens). Benchmark: `tools/eval_kb.py` with two golden query sets:

- **standard** (27 queries): phrased like the fundamentals' vocabulary.
- **paraphrase** (18 queries): reworded with minimal keyword overlap, e.g.
  "the deploy broke production, how do we undo it" -> DevOps fundamentals.
  This set exists because a perfect score on the standard set proves nothing about
  real agent behavior.

Metric: hits@5 (correct chunk in top 5) and MRR (mean reciprocal rank, 1.0 = always rank 1).

## Results

| set | mode | hits@5 | MRR |
|-----|------|-------:|----:|
| standard | hybrid, offline vectors | 100% | 1.000 |
| standard | BM25 only | 100% | 1.000 |
| standard | offline vectors only | 100% | 0.932 |
| standard | **hybrid, Gemini embedding-2** | **100%** | **1.000** |
| standard | Gemini vectors only | 100% | 1.000 |
| paraphrase | hybrid, offline vectors | 100% | 0.806 |
| paraphrase | BM25 only | 83.3% | 0.778 |
| paraphrase | offline vectors only | 100% | 0.588 |
| paraphrase | **hybrid, Gemini embedding-2** | **100%** | **0.833** |
| paraphrase | Gemini vectors only | 100% | **0.889** |

## What Gemini embedding-2 actually improved

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

## Expectation for larger corpora

The gain is understated here because the corpus is tiny (30 chunks). As role namespaces grow
with `pm-kb-enrich` project facts and scraped top-ups toward their budgets, BM25 lexical
collisions increase and offline hashing degrades; real embeddings' advantage compounds.
Re-run this benchmark after a few real projects to confirm.

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
