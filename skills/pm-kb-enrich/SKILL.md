---
name: pm-kb-enrich
description: "Add project-specific knowledge to the PMOS team KB AFTER the project topic is known: extracts scope, stack, decisions, interfaces and constraints from .pmos/charter.md, plans, and wave-2 outputs (architect/designer/business) into role-namespaced KB entries so later agents search instead of re-reading everything. Run between planning and implementation waves."
---

# /pm-kb-enrich

Enrich the team KB with THIS project's specifics, so implementation agents retrieve decisions
instead of re-reading upstream artifacts. Run after wave 2 (architect/designer/business) outputs exist.

## Inputs (read these, in full; they are small by design)

- `.pmos/charter.md`
- `.pmos/plans/plan.md`
- `.pmos/decisions/*.md` (ADRs)
- `.pmos/out/architect/*`, `.pmos/out/designer/*`, `.pmos/out/business/*` (whatever exists)

## Step 1: extract role-relevant facts

For each namespace below, write 2-8 self-contained knowledge chunks (each <=1KB, title + facts)
into `.pmos/kb-sources/project/<ns>.md`, one chunk per `## ` heading. What goes where:

| ns | facts to extract |
|----|------------------|
| shared | project name, one-line goal, tech stack, hard constraints, glossary of project terms |
| pm | milestones, phase order, acceptance criteria, risks and mitigations |
| architect | accepted ADRs (decision + why), module boundaries, API contracts, data model |
| backend | endpoints/services, storage choices, auth model, integration notes |
| frontend | pages/components list, state approach, design token reference, perf targets |
| designer | visual direction, tokens, component inventory, accessibility requirements |
| business | model, pricing, target segment, success metrics |
| marketing | positioning, audience, channels, launch plan |
| qa | acceptance criteria verbatim, test strategy, environments |
| devops | hosting, CI/CD plan, secrets handling, environments, backup/observability |

Skip namespaces with no relevant facts. Quality over coverage: only facts a later agent would
actually search for. Phrase titles like search queries ("Auth flow for API tokens").

## Step 2: index with project priority

```
python TPL/tools/kb.py add-dir --db .pmos/kb.sqlite3 --ns <ns> --path .pmos/kb-sources/project --glob "<ns>*" --priority 9
```

Priority 9 = project facts rank above curated fundamentals (8) and scraped top-ups (4), but the
shared rules (10) remain top. The cap still applies; report any drops.

## Step 3: report

Run `kb.py budget` + `kb.py stats`, list what was added per role, and confirm the implementation
waves may start.

## Rules

- Never copy whole upstream artifacts into the KB; extract and compress. The original files stay
  on disk for full reads when truly needed.
- Re-run this skill after major scope changes (new ADRs, revised plan) to keep the KB current.
