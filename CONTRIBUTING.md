# Contributing to PMOS

Thanks for helping make the agent team template better.

## Setup for development

```
git clone https://github.com/skadlem/pm-agent-team.git
cd pm-agent-team
install.cmd          # Windows
sh install.sh        # macOS/Linux
```

Requirements: Python 3.9+ (stdlib only, SQLite with FTS5), jcode with swarm support.
No pip dependencies.

## Before you open a PR

```
python tools/validate.py      # 70-check self-check: budgets, costs, tiers, skills, paths, recommender
python tools/kb.py selftest   # KB engine smoke test
```

Both must pass. CI runs them on Ubuntu and Windows.

## Common changes

- **Add a role**: add it to `roster.json` (skills, kb_namespace, when, artifacts, purpose map),
  create `kb-sources/<role>/*.md` fundamentals, mention it in README. validate.py checks roster
  coverage for you.
- **Edit fundamentals**: markdown files under `kb-sources/<role>/`, one `## ` heading per fact
  block (the indexer chunks per heading). Keep chunks self-contained and small (<~1KB).
- **Change caps/weights**: `config.json`. Role weights must sum to 1; validate.py checks the
  budget math against the total cap.
- **Change protocol**: `ORCHESTRATOR.md` and the skills under `skills/`. Keep frontmatter
  `name`/`description` intact (jcode parses them).
- **Refresh model benchmarks**: `python tools/recommend.py refresh` prints the search queries to
  update `benchmarks.json`, or regenerate from Epoch AI hub CSVs with
  `python tools/build_benchmarks.py --data-dir <benchmark_data> --out benchmarks.json`
  (data: Epoch AI benchmark hub, CC BY 4.0; keep the attribution in README).

## Conventions

- Stdlib-only Python; no new dependencies without strong justification.
- Windows cmd AND POSIX shell compatibility for anything user-facing (installers, documented commands).
- Keep the template self-contained: everything must work from a fresh clone with just Python.
