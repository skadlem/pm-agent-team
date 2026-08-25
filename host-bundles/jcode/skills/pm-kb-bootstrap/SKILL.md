---
name: pm-kb-bootstrap
description: "Form the initial knowledge base for the PMOS project team. Indexes curated per-role fundamentals (and optionally top-up web facts) into the hybrid KB with a hard token cap, so agents only ever carry truly needed fundamentals. Run once per project at launch, or standalone to (re)build a role's fundamentals."
---

# /pm-kb-bootstrap

Build the INITIAL knowledge base: the bare fundamentals each agent needs. Curated, capped, no junk.

## Locate inputs

- `TPL`: from `~/.jcode/pmos-template-root`, else ask the user where `pm-agent-team` lives.
- `DB`: `<project>/.pmos/kb.sqlite3`. If missing, run
  `python TPL/tools/kb.py init --db .pmos/kb.sqlite3` first.
- `CFG`: `TPL/config.json` (total cap, shared budget, per-role weights).

## Step 1: index the curated fundamentals (always)

The template ships curated fundamentals in `TPL/kb-sources/<role>/*.md`. Index them per role:

```
python TPL/tools/kb.py add-dir --db .pmos/kb.sqlite3 --ns <role> --path TPL/kb-sources/<role> --priority 8
```

Roles with sources: pm, architect, backend, frontend, designer, business, marketing, qa, devops, legal.
Also index `TPL/kb-sources/shared` into `--ns shared --priority 10` (agent operating rules).

## Step 2: targeted top-up (only if gaps)

Do NOT bulk-scrape. For each role, ask: does the project description mention stack/topics absent
from the curated fundamentals? If yes, run at most 1-2 `websearch` queries per gap (e.g. official
docs for the chosen framework), pick 1-3 authoritative results, `webfetch` only those, extract the
essential facts into <=1KB of markdown per fact, and add each with priority 4:

```
python TPL/tools/kb.py add --db .pmos/kb.sqlite3 --ns <role> --title "<fact title>" --kind web --source <url> --priority 4 --content "<extracted facts>"
```

Priority ordering matters: curated fundamentals = 8, shared rules = 10, scraped top-ups = 4, so if
a namespace exceeds its budget the engine drops scraped material first, then oldest/lowest value.

## Step 3: enforce and report

```
python TPL/tools/kb.py budget --db .pmos/kb.sqlite3 --config TPL/config.json
python TPL/tools/kb.py stats --db .pmos/kb.sqlite3
```

The engine auto-drops lowest-priority chunks when a namespace exceeds budget, but verify the budget
table shows no negative headroom and report used vs budget tokens per role to the user.

## Rules

- Never index entire websites, full docs trees, or anything >~2KB per chunk without extracting
  the essentials first. The cap exists; respect the intent, not just the letter.
- Keep every added chunk self-contained (title + facts), because search returns excerpts, not files.
- Offline mode is fine: vector search works without an embeddings API; mention
  PMOS_EMBEDDINGS_URL env support in the report if relevant.
