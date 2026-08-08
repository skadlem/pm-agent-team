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
expected artifacts, and suggested spawn model + effort (user-approved at launch).

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
