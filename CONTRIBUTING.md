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
python tools/validate.py         # 118-check self-check: budgets, costs, tiers, skills, paths, recommender
python tools/kb.py selftest      # KB engine smoke test
python tools/artifacts.py selftest  # artifact id/reference linter
python tools/trace.py selftest   # traceability join
python tools/cost.py selftest    # spend ledger
python tools/eval_project.py     # protocol harness: fixture projects end to end
```

Both must pass. CI runs them on Ubuntu and Windows.

## Common changes

- **Add a role**: the legal role (2026-08) touched every file below; do all of them:
  1. `roster.json`: role entry (name, skills, kb_namespace, when, artifacts), `role_tiers`,
     `role_effort`, `model_suggestions` purpose map (weights sum to 1), and the `waves` entry
     that spawns the role.
  2. `config.json`: a `role_weights` entry (weights sum to 1; validate.py checks the budget math).
  3. `kb-sources/<role>/*.md` fundamentals (one `## ` heading per chunk, chunks <~1KB).
  4. `tools/eval_kb.py`: add the namespace to `build_db()` AND add golden queries to GOLDEN/HARD
     (expected substrings must match the section headings exactly).
  5. `tools/validate.py`: add the namespace to the section-6 bootstrap list.
  6. `tools/state.py`: add the role's primary artifact to `WAVE2_ARTIFACTS` / `WAVE3_ARTIFACTS`.
  7. `tools/recommend.py`: mirror the purpose map in `DEFAULT_PURPOSE` (fallback).
  8. `skills/pm-kb-bootstrap/SKILL.md`: add the role to the "Roles with sources" line.
  9. README + ORCHESTRATOR.md mentions (role table, wave lists, artifact lists).
  validate.py checks roster coverage for you; eval_kb.py's standard set must still hit >= 90%.
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
