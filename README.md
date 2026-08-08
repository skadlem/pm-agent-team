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

The installer copies the 3 skills into `~/.jcode/skills` and remembers the template location in
`~/.jcode/pmos-template-root` (the folder can live anywhere; move it and re-run the installer if needed).

## What's inside

```
pm-agent-team/
  ORCHESTRATOR.md          # operating manual for the main session (waves, gates, rules)
  roster.json              # roles, per-role skills, model suggestions, wave order
  config.json              # KB caps (150K tokens total), context rules
  tools/kb.py              # hybrid KB engine: SQLite FTS5 BM25 + vectors, RRF fusion, caps
  kb-sources/<role>/*.md   # curated fundamentals shipped per role (the "bare agent" KB)
  kb-sources/shared/       # agent operating rules (partial-context, evidence, etc.)
  templates/               # charter.md, adr.md skeletons
  skills/                  # project-team-start, pm-kb-bootstrap, pm-kb-enrich
  install.cmd / install.sh # copy skills to ~/.jcode/skills, record template root
```

## Roles

project manager/planner, architect, designer, backend, frontend, business advisor, marketing,
QA engineer, devops (security folded in). Each role has assigned jcode skills, a KB namespace,
expected artifacts, and a model chosen at launch (user-approved).

## Model selection (computed at launch, not hardcoded)

At GATE 1 the coordinator runs `swarm list_models`, saves its output, and runs
`python TPL/tools/recommend.py --available <file>` which:

1. Keeps only AVAILABLE models from the live list.
2. Scores each against per-purpose benchmarks (`benchmarks.json`): reasoning, coding, design,
   business, marketing, verification, ops, writing. Each role maps to a purpose mix
   (`roster.json` -> `model_suggestions` -> `purpose`, weights sum to 1).
3. Keeps the BEST TIER (score >= 92% of the best), then picks the CHEAPEST of that tier
   by blended cost (3:1 input:output, USD per 1M tokens).
4. Outputs the role -> model table for you to OK, edit, or remove. The approved map is saved
   to `.pmos/team-model.json` and used for every spawn.

`benchmarks.json` is GENERATED from Epoch AI's benchmark hub data (CC BY 4.0,
`benchmark_data/`, ~75 benchmark CSVs: SWE-bench Verified, GPQA, ARC-AGI, MMLU, webdev,
terminalbench, etc.). Regenerate it whenever you refresh the data:

```
python TPL/tools/build_benchmarks.py --data-dir <path/to/benchmark_data> --out benchmarks.json
```

Scores are per-benchmark min-max normalized to 0-100 (handles arbitrary scales and
lower-is-better benchmarks), then averaged per purpose. Costs come from a curated pricing
overlay inside the generator (Epoch data has no prices); models without pricing get null
cost, which the recommender treats as "expensive" when choosing within the best tier.

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

or `/project-team-start`. The mode is detected automatically:

- **Greenfield** (empty repo): charter -> plan -> minimal team proposal -> YOU approve ->
  design wave -> KB enrichment -> YOU approve plan -> implementation -> QA gate -> checkpoint.
- **Brownfield** (existing code): same command, extra Wave 0 first. An architect worker maps the
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
- Token caps: 150K total, shared budget 15K + role-weighted pools. Overflow drops
  lowest-priority chunks first (scraped top-ups before curated fundamentals; project facts rank
  highest below shared rules). Check with `kb.py budget`.
- Agents only ever get search excerpts; repo questions go through graphify queries. Full dumps
  are forbidden by protocol.

### CLI

```
python tools/kb.py init --db <db>
python tools/kb.py add --db <db> --ns <role> --title "..." --content "..." [--priority N]
python tools/kb.py add-dir --db <db> --ns <role> --path <dir> [--priority N]
python tools/kb.py search --db <db> "query" [--role <role>] [-k N] [--json]
python tools/kb.py budget --db <db> --config config.json
python tools/kb.py stats --db <db>
python tools/kb.py reindex-vectors --db <db>
python tools/kb.py selftest
```

## Customizing

- Caps/weights: `config.json`. Roles/skills/waves/models: `roster.json`.
- Fundamentals: edit `kb-sources/<role>/*.md` (markdown, one `## ` heading per fact block).
- Protocol behavior: `ORCHESTRATOR.md`. Skills are plain markdown; tweak freely.
- After any edit, run `python tools/validate.py` to verify budget math, skill references,
  model suggestions, documented CLI commands, skill frontmatter, bootstrap, and edge cases.

## Measuring performance

Four levels, cheapest first:

1. **Component correctness (CI, automatic):** `python tools/kb.py selftest` and
   `python tools/validate.py` (39 checks: budget math, frontmatter, bootstrap, edge cases,
   recommender semantics, installer idempotency).
2. **Retrieval quality (CI, automatic):** `python tools/eval_kb.py` runs two golden query sets
   (27 standard + 18 paraphrased queries) against a freshly built KB and reports hits@5 and MRR,
   comparing the default hybrid search against its single-signal baselines (ablation):

   | set | mode | hits@5 | MRR |
   |-----|------|-------:|----:|
   | standard | hybrid (shipped default) | 100% | 1.000 |
   | standard | BM25 only | 100% | 1.000 |
   | standard | offline vectors only | 100% | 0.932 |
   | paraphrase | hybrid | 100% | 0.806 |
   | paraphrase | BM25 only | 83.3% | 0.778 |
   | paraphrase | offline vectors only | 100% | 0.588 |
   | paraphrase | **Gemini embedding-2 vectors** (measured) | **100%** | **0.889** |
   | standard | **Gemini embedding-2 vectors** (measured) | **100%** | **1.000** |

   Pass threshold for hybrid on the standard set: hits@5 >= 90% and MRR >= 0.65. If you edit
   `kb-sources/`, keep the golden set in `tools/eval_kb.py` aligned.

   **Using real embeddings:** set `PMOS_EMBEDDINGS_URL`, `PMOS_EMBEDDINGS_KEY`,
   `PMOS_EMBEDDINGS_MODEL` and run `kb.py reindex-vectors`. Gemini's native endpoint
   (generativelanguage.googleapis.com) is auto-detected and authenticated with the API key
   (`x-goog-api-key`); other URLs use OpenAI-compatible `Authorization: Bearer`. Rate-limit
   responses (429) are retried with backoff. Rerun the API-backed benchmark with
   `python tools/eval_kb_api.py`. Full recorded results, methodology and the weight-tuning
   sweep: [EVALUATION.md](EVALUATION.md). Headline: Gemini embedding-2 lifts vector MRR on
   paraphrased queries from 0.588 to 0.889 (recall already 100%); the gain grows with KB size.
3. **Per-run project metrics:** every checkpoint in `.pmos/log.md` records workers spawned,
   QA gate results, defect counts, rework loops, KB budget usage, and acceptance pass rate.
   Compare these across projects to see if the system improves.
4. **Outcome evaluation (manual):** after a project, judge the deliverables themselves:
   did the acceptance criteria actually hold under real use, how much rework was needed after
   handoff, and whether the KB enrichment step saved workers from re-reading upstream artifacts
   (spot-check a worker's KB search logs against its behavior).

## License and attribution

- Code and template: [MIT](LICENSE).
- `benchmarks.json` scores derive from [Epoch AI's benchmark hub](https://epoch.ai/benchmark-data) dataset (CC BY 4.0). Keep attribution when redistributing derived data.
