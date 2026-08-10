# Legal Advisor Agent (risk & policy) — Design

Date: 2026-08-10
Status: Approved for implementation (user approved all 5 improvement suggestions)

## 1. Goal

Add a `legal` role to PMOS: a risk & policy advisor that produces a
jurisdiction-specific regulatory risk assessment for every project. It is a
default role (shown at GATE 1 like the other 9, removable per project), acts in
wave 2 as an advisor, and its findings are machine-readable and enforced at
gates instead of being advisory-only prose.

## 2. Role definition (roster.json)

- Key: `legal`, name "legal advisor (risk & policy)".
- Skills: `verification-before-completion`, `karpathy-guidelines`.
  (Evidence-before-claims and surgical scope fit risk work; the agent must
  never assert a law it cannot cite.)
- Artifact: `.pmos/out/legal/risk-register.md`.
- Model suggestion purpose weights: `reasoning 0.4`, `business 0.4`,
  `writing 0.2`. No "legal" benchmark purpose exists; this mix scores from
  existing data. Mirror the same weights in `DEFAULT_PURPOSE` in
  `tools/recommend.py` as the fallback.
- Default on: added to `roles` and `model_suggestions` so it appears in the
  GATE 1 roster proposal and the model table; the user may remove it.

## 3. Knowledge base

### 3.1 Static fundamentals (kb-sources/legal/)

- `data-protection.md` — how to analyze a data protection regime (GDPR-type
  principles: lawful basis, rights, breach notification, data residency).
- `ai-regulation.md` — AI-specific obligations frameworks (risk tiers,
  transparency, logging, human oversight).
- `licensing.md` — open-source vs commercial, API ToS, dependency risk.
- `risk-register-template.md` — the structured entry format (see section 5).

### 3.2 Jurisdiction pack (dynamic, per project)

- New launch step between GATE 1 and wave 2: "jurisdiction pack".
- Input: the charter's Deployment jurisdictions section (required, see 4).
- The coordinator researches the deployment country's actual laws with web
  search, guided by the ORCHESTRATOR.md checklist:
  1. data protection act (and data residency rules),
  2. AI-specific regulation,
  3. consumer / e-commerce law,
  4. licensing / export rules,
  5. industry-specific rules (fintech, health, etc. when in scope).
- Output: `.pmos/kb-sources/legal/jurisdiction-<cc>.md` (one per country,
  e.g. `jurisdiction-de.md`), each entry citing the specific law and source
  URL, plus an `as_of` date.
- Ingest: `python TPL/tools/kb.py add-dir --db .pmos/kb.sqlite3 --ns legal
  .pmos/kb-sources/legal` (or `kb.py add` per file), so the legal worker
  searches country-specific law first.
- Laws-change refresher: on resume, if a jurisdiction file's `as_of` is older
  than 6 months, or the charter's jurisdictions changed, re-research before
  wave 2. Note the EU AI Act's phased application explicitly in the checklist.

## 4. Deployment jurisdiction capture

- `templates/charter.md` gains a required section "Deployment jurisdictions"
  (countries/regions where the project will be deployed or reach users,
  e.g. EU, US, CN), placed after Risks, with Team renumbered.
- Start flow (ORCHESTRATOR.md, wave 1): the PM must include this section; if
  the user has not stated where the project deploys, the PM asks the user
  before finalizing the charter. GATE 1 also lets the user confirm/edit it.
- pm-kb-enrich pushes the jurisdictions into the legal KB namespace so
  downstream work is jurisdiction-scoped.

## 5. Risk register format (machine-readable)

Every entry in `.pmos/out/legal/risk-register.md`:

```yaml
- id: L-001
  risk: <short statement>
  jurisdiction: <cc> | global
  law: <specific law + article, e.g. GDPR Art. 17>
  source: <URL>
  severity: high | medium | low
  probability: high | medium | low
  obligation: <what the project must do>
  mitigation: <planned action>
  owner: <role, e.g. backend>
  status: open | mitigated | requires-counsel
```

Rules:
- Every entry cites a specific law/article and a source URL. No citation =
  no entry; if the agent cannot verify a requirement it marks the entry
  `requires-counsel` instead of asserting.
- `severity: high` + `status: open` blocks GATE 2 (escalate to user; the
  user may accept the risk explicitly and unblock).

## 6. Orchestration changes (ORCHESTRATOR.md)

- Wave 2: spawn set becomes {architect, designer, business, legal} in
  parallel. Legal reads charter + its KB namespace (jurisdiction pack first),
  writes the risk register.
- GATE 2 summary: add risk register highlights (top risks, mitigations,
  jurisdiction-specific obligations). If any high-severity item is open and
  not user-accepted, GATE 2 blocks.
- Wave 4 (QA): the verification pass re-checks that `owner`-assigned
  mitigations for `status: mitigated` items are actually implemented in the
  delivered work; unmitigated high items surface in the QA report.
- Mode knob: `config.json` gains `legal_strict: true|false` (default true).
  Strict = full jurisdiction pack + gate blocking. Light = skip jurisdiction
  pack, advisory only, no gate block. The knob can be set per project.
- Cross-role propagation: the `pm-kb-enrich` skill is extended so that once
  `.pmos/out/legal/risk-register.md` exists, it copies each entry's
  obligations into the business (market entry), marketing (claims/ads
  compliance), and pm (milestone gating) KB namespaces, tagged with the risk
  id (e.g. `L-001`).

## 7. Scoring / model selection

- `recommend.py` gains `legal` in `DEFAULT_PURPOSE` and the roster carries the
  same weights; no benchmark data changes needed.
- `.pmos/team-model-ladder.json` refreshes to include the legal ladder; the
  multi-provider fallback chain behavior applies as usual.

## 8. Validation and docs

- `tools/validate.py` keeps passing (roster/suggestions consistency, fixture
  untouched); legal appears in the recommend table with a suggestion.
- README.md role table + "What's inside" kb-sources list updated.
- ORCHESTRATOR.md: wave 2 set, GATE 2 gate, jurisdiction pack step + country
  checklist, wave 4 re-check, mode knob, cross-role propagation.

## 9. Out of scope

- Actual legal advice: the agent flags `requires-counsel`; it never replaces
  a lawyer. No per-country law database shipped in the template; packs are
  researched per project (fresh, dated, citable).
- No change to existing 9 roles' purposes or weights.
