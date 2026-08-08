# PMOS: Project-Management Agent Team Template

Portable project-management system you can load into ANY future jcode session. When you say
"Start the project <description>", it bootstraps a managed team of role agents, each with its own
hybrid-search knowledge base and strict partial-context rules.

## What you get

- **9 role agents**: project manager/planner, architect, designer, backend developer, frontend
  developer, business advisor, marketing manager, QA/test engineer, devops engineer.
- **Per-role knowledge bases** with hybrid search (BM25 via SQLite FTS5 + vector cosine, fused
  with Reciprocal Rank Fusion). Offline by default; real embeddings optional.
- **Per-role token caps**: the initial KB holds only fundamentals; the engine evicts the
  lowest-priority chunks when a role exceeds its budget.
- **graphify integration**: repo questions go through the /graphify skill's query tools, never
  full-repo dumps.
- **Model approval gate**: at launch, the system lists a suggested model + effort per agent and
  asks you to OK, change, or remove before any worker spawns.
- **Wave-based execution** with user gates between waves, and a resume story for future sessions.

## Install (one time)

Windows:

```
install.cmd
```

Unix:

```
./install.sh
```

This copies the 3 skills into `~/.jcode/skills` and records the template root in
`~/.jcode/pmos-template-root` so the skills can find `tools/kb.py`, `roster.json`, and `config.json`
in any future session.

## Use

In any future session, in the project repo:

```
Start the project <description>
```

The launch skill (`/project-team-start`) then runs the ORCHESTRATOR protocol:

1. Creates `.pmos/` (charter, plans, decisions, KB store, artifacts, log).
2. Seeds the KB with curated fundamentals (`/pm-kb-bootstrap`).
3. Builds the graphify index if the repo has code.
4. Wave 1: the PM writes charter, plan, and a minimal roster proposal.
5. GATE 1: you approve the roster AND the per-agent model/effort table (edit/remove allowed).
6. Waves 2-4: design/architecture, implementation, QA verification, with gates and checkpoints.

Standalone skills you can also invoke directly:

- `/pm-kb-bootstrap` — (re)build a role's fundamentals in the KB.
- `/pm-kb-enrich` — add project-specific facts after planning so later agents search instead of
  re-reading upstream artifacts.

## Layout

```
pm-agent-team/
  ORCHESTRATOR.md        # operating manual for the main session (the only file read in full)
  roster.json            # role definitions, skills, waves, model suggestions
  config.json            # KB caps (total + per-role weights) and context rules
  templates/             # charter + ADR skeletons given to workers
  kb-sources/<role>/     # curated fundamentals indexed at bootstrap (the initial KB)
  tools/kb.py            # hybrid KB engine: init/add/add-dir/search/budget/reindex/stats/selftest
  skills/                # the 3 skills installed into ~/.jcode/skills
```

## Knowledge-base engine

All commands take `--db <project>/.pmos/kb.sqlite3`.

```
python tools/kb.py init --db .pmos/kb.sqlite3
python tools/kb.py add-dir --db .pmos/kb.sqlite3 --ns <role> --path kb-sources/<role> --priority 8
python tools/kb.py search --db .pmos/kb.sqlite3 "query" --role <role> -k 5
python tools/kb.py budget --db .pmos/kb.sqlite3 --config config.json
python tools/kb.py stats --db .pmos/kb.sqlite3
python tools/kb.py selftest
```

Real embeddings (optional): set `PMOS_EMBEDDINGS_URL` (OpenAI-compatible `/embeddings`),
`PMOS_EMBEDDINGS_KEY`, `PMOS_EMBEDDINGS_MODEL`, then `reindex-vectors`. Offline mode uses
deterministic hashed vectors and works with zero config.

## Rules that keep context bounded

1. Partial context only: KB search and graphify queries, never full-dump the KB or repo.
2. Retrieval order: KB first, graphify for repo questions, targeted file reads last.
3. Every query caps results (`-k`, default 5) and excerpt length (1200 chars).
4. KB eviction: lowest-priority chunks drop first when a role exceeds its cap.
