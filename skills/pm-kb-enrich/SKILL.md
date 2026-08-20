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
- `.pmos/out/architect/*` (includes `current-state.md` in brownfield mode), `.pmos/out/designer/*`,
  `.pmos/out/business/*` (whatever exists)

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
| qa | acceptance criteria verbatim, test strategy, environments, existing-suite baseline (brownfield) |
| legal | deployment jurisdictions, obligations per risk id (e.g. `L-001`), compliance calendar dates |
| devops | hosting, CI/CD plan, secrets handling, environments, backup/observability |

Propagation: when `.pmos/out/legal/risk-register.md` exists, also include its
obligations in the business (market entry), marketing (claims/ads compliance), and
pm (milestone gating) chunks, each tagged with the risk id (e.g. "Obligation
L-001: ..."). Keep legal facts out of other namespaces unless an obligation
actually applies to that role.

Brownfield extras: from `current-state.md`, distill CONVENTIONS into `shared` (naming, error
handling, test layout, commit style), the MODULE MAP into `architect`/`backend`/`frontend`
(who owns what, integration points), and how-to-run-tests into `qa`. These let later agents
answer "how does this repo do X" from the KB instead of re-querying graphify.

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
  Re-running is safe and is the intended way to retire stale facts: chunks are keyed by
  (namespace, source file, `## ` heading), so rewriting `.pmos/kb-sources/project/<ns>.md` and
  re-running step 2 updates those chunks in place and DELETES the ones you dropped from the file.
  A superseded decision must be edited or removed there - leaving it in the file keeps it
  searchable. Check the reported `N new, N updated, N pruned` line.
