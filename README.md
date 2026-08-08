# PMOS: Project Management Operating System (agent team template)

A portable jcode template that turns "Start the project <idea>" into a managed multi-agent build:
role agents, per-role hybrid knowledge bases, repo understanding via graphify, wave-based execution
with human approval gates, and hard caps so no agent ever carries more context than it needs.

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

```
install.cmd          (Windows)
sh install.sh        (macOS/Linux)
```

Then restart or refresh skills. The template root is remembered in
`~/.jcode/pmos-template-root`; the folder can live anywhere.

## Usage

In any project directory, any session:

```
Start the project <one-paragraph description>
```

or `/project-team-start`. Flow: bootstrap `.pmos/` + KB -> PM plans and proposes the minimal
team -> YOU approve roster + models -> architect/designer/business design -> KB enrichment ->
YOU approve plan -> implementation wave -> QA verification gate -> checkpoint to `.pmos/log.md`.

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
