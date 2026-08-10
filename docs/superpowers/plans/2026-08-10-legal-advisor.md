# Legal Advisor Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a default-on `legal` role (risk & policy advisor) to PMOS that produces a cited, jurisdiction-scoped risk register per project and gates on unresolved high-severity items.

**Architecture:** Data-driven like the other 9 roles: `roster.json` defines the role and its purpose weights, `config.json` adds a strict/light mode knob and a KB weight, `kb-sources/legal/` ships static fundamentals, and a new launch step (jurisdiction pack) researches the deployment country's laws into the project KB. `ORCHESTRATOR.md` and `skills/pm-kb-enrich` wire it into waves 2/4, gates, resume, and cross-role propagation. `tools/recommend.py` only gains a `DEFAULT_PURPOSE` fallback entry.

**Tech Stack:** Python 3.9+, JSON config, Markdown KB files, `tools/kb.py`, `tools/validate.py` as the test harness (repo has no pytest suite).

## Global Constraints

- Purpose weights for `legal`: `reasoning 0.4`, `business 0.4`, `writing 0.2` (verbatim from spec).
- Role key is `legal`; kb namespace is `legal`; artifacts live under `.pmos/out/legal/`.
- `config.json` gains top-level `"legal_strict": true`; `kb.role_weights` must sum to exactly 1.00 after adding `legal: 0.04` (new weights: pm .15, architect .19, backend .16, frontend .16, designer .10, business .06, marketing .07, qa .04, devops .03, legal .04).
- Charter template gains a required "Deployment jurisdictions" section; the PM must ask the user for it if unknown.
- Risk register entries must cite a specific law/article + source URL; unverifiable items are `requires-counsel`, never asserted.
- `severity: high` + `status: open` blocks GATE 2 unless the user explicitly accepts the risk.
- Risk ids are stable (`L-001`, ...) and diffed between wave 2 and wave 4.
- All existing validators must pass; no change to the other 9 roles' purposes/weights.
- JSON files use indent=1 style (repo convention); markdown files keep the existing voice.

---

### Task 1: Roster role + recommend.py fallback purpose

**Files:**
- Modify: `roster.json` (add `roles.legal`, `model_suggestions.legal`)
- Modify: `tools/recommend.py` (add `legal` to `DEFAULT_PURPOSE`)
- Test: `tools/validate.py` (checks at lines 50, 71-72, 162)

**Interfaces:**
- Consumes: existing `roster.json` structure (`roles`, `model_suggestions`)
- Produces: `roster["roles"]["legal"]` (name, kb_namespace, skills, when, artifacts), `roster["model_suggestions"]["legal"]` (`{"purpose": {"reasoning": 0.4, "business": 0.4, "writing": 0.2}}`), `DEFAULT_PURPOSE["legal"]` in recommend.py

- [ ] **Step 1: Add the role to roster.json**

Insert after the `devops` role object (alphabetical position after `frontend` is fine too; keep keys sorted like the file does). Match the existing shape exactly:

```json
    "legal": {
      "name": "Legal Advisor (Risk & Policy)",
      "kb_namespace": "legal",
      "skills": [
        "verification-before-completion",
        "karpathy-guidelines"
      ],
      "when": "Every project: regulatory risk assessment for the charter's deployment jurisdictions. Strict mode (config.json legal_strict) does a jurisdiction pack + gate blocking; light mode is advisory only.",
      "artifacts": [
        ".pmos/out/legal/data-inventory.md",
        ".pmos/out/legal/licenses.md",
        ".pmos/out/legal/risk-register.md",
        ".pmos/out/legal/compliance-calendar.md"
      ]
    }
```

Add to `model_suggestions` (after `frontend`, mirroring `business`'s shape):

```json
    "legal": {
      "purpose": {
        "reasoning": 0.4,
        "business": 0.4,
        "writing": 0.2
      }
    }
```

- [ ] **Step 2: Add the fallback purpose in recommend.py**

In `tools/recommend.py`, `DEFAULT_PURPOSE` (line ~38), after `"frontend"`:

```python
    "legal":     {"reasoning": 0.4, "business": 0.4, "writing": 0.2},
```

- [ ] **Step 3: Verify**

Run: `python3 tools/validate.py`
Expected: `ALL VALIDATION PASSED (1 environment-dependent check(s) skipped)` (checks: every role has required keys, `model_suggestions` purposes == roles, every role gets a suggestion).

Run: `python3 tools/recommend.py --available /tmp/list_models.txt --json 2>/dev/null | python3 -c "import json,sys; [print(r['role'], r['suggested']) for r in json.load(sys.stdin) if r['role']=='legal']"`
Expected: `legal claude-opus-5` (best reasoning/business mix among eligible models; exact pick may differ, but it must print a model, not `None`).

- [ ] **Step 4: Commit**

```bash
git add roster.json tools/recommend.py
git commit -m "add legal role with reasoning/business/writing purpose weights"
```

---

### Task 2: Static KB fundamentals for the legal namespace

**Files:**
- Create: `kb-sources/legal/data-protection.md`, `kb-sources/legal/ai-regulation.md`, `kb-sources/legal/licensing.md`, `kb-sources/legal/risk-register-template.md`, `kb-sources/legal/compliance-calendar-template.md`
- Test: `python3 tools/kb.py selftest` + `add-dir` on a scratch db

**Interfaces:**
- Consumes: existing `kb-sources/<role>/*.md` conventions (small files, `## ` chunk headings, <=1KB chunks)
- Produces: files the jurisdiction pack and legal worker read; `risk-register-template.md` defines the YAML entry schema from spec section 6

- [ ] **Step 1: Write data-protection.md**

Content: how to analyze a data protection regime. Chunks: (1) "Lawful basis analysis" — identify legal basis per processing purpose (consent, contract, legal obligation, legitimate interest) and document it in the data inventory; (2) "Data subject rights" — access, rectification, erasure, portability, objection; each maps to an obligation and a risk entry; (3) "Data residency and transfers" — storage/processing location determines which regime applies; cross-border transfers need adequacy/mechanisms (e.g. SCCs); (4) "Breach notification" — typical SLA (e.g. 72h to the regulator when risk to individuals), requires an incident plan. Every chunk ends with "checklist: what the legal agent must verify for this jurisdiction".

- [ ] **Step 2: Write ai-regulation.md**

Chunks: (1) "AI risk tiers" — classify the project's AI use (prohibited / high / limited / minimal) per the jurisdiction's AI act; high-risk examples: hiring, credit, biometric ID; (2) "Transparency and logging" — disclosure that content is AI-generated, model logging, human oversight for high-risk systems; (3) "Phased application" — obligations phase in over time (e.g. EU AI Act: 6 months for prohibitions, 12 for GPAI, 24 for most high-risk); check the jurisdiction pack's `as_of` date against the phase calendar; (4) "General-purpose AI model obligations" — training-data documentation, copyright policy where applicable.

- [ ] **Step 3: Write licensing.md**

Chunks: (1) "License compatibility" — permissive (MIT, Apache-2.0, BSD) vs copyleft (GPL, AGPL, LGPL); copyleft can force source disclosure of derivative works; AGPL extends to network use; (2) "Audit the manifest" — scan package.json/requirements.txt/go.mod/Cargo.toml for licenses; record dependency -> license -> compatible? in `licenses.md`; (3) "API and ToS constraints" — model/data APIs may ban output for competing products, training, or certain industries; read the ToS before relying on it; (4) "Project license choice" — pick the project license at the plan stage so compatibility can be checked.

- [ ] **Step 4: Write risk-register-template.md**

The exact schema from spec section 6 (verbatim):

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

Plus rules: every entry cites law/article + URL; no citation = no entry (`requires-counsel` instead); `high`+`open` blocks GATE 2; ids stable and diffed at wave 4.

- [ ] **Step 5: Write compliance-calendar-template.md**

Template for dated ongoing obligations:

```markdown
# Compliance calendar: <project>

| due | obligation | source (law/article) | owner | status |
|-----|-----------|----------------------|-------|--------|
| <date> | e.g. breach notification SLA (72h) | GDPR Art. 33 | devops | active |
| <date> | e.g. register of processing activities | GDPR Art. 30 | legal | active |
```

Rules: dates come from the jurisdiction pack (phased obligations) and the project's launch date; the PM folds these into milestones; on resume the coordinator checks overdue items against elapsed time.

- [ ] **Step 6: Verify**

Run: `python3 tools/kb.py selftest`
Expected: selftest passes.

Run:
```bash
python3 tools/kb.py init --db /tmp/kb-legal-test.sqlite3
python3 tools/kb.py add-dir --db /tmp/kb-legal-test.sqlite3 --ns legal --path kb-sources/legal
python3 tools/kb.py search --db /tmp/kb-legal-test.sqlite3 --ns legal "breach notification" | head -5
```
Expected: search returns chunks from the new files (non-empty output).

- [ ] **Step 7: Commit**

```bash
git add kb-sources/legal/
git commit -m "add legal KB fundamentals: data protection, AI regulation, licensing, register/calendar templates"
```

---

### Task 3: config.json — legal_strict knob + KB weight rebalance

**Files:**
- Modify: `config.json`
- Test: `python3 tools/kb.py budget --db /tmp/kb-legal-test.sqlite3 --config config.json`

**Interfaces:**
- Consumes: existing `config.json` keys
- Produces: `config["legal_strict"]` (bool, default true), rebalanced `config["kb"]["role_weights"]` summing to 1.00 with `legal: 0.04`

- [ ] **Step 1: Rebalance role_weights and add the knob**

Replace `kb.role_weights` so the values are: pm 0.15, architect 0.19, backend 0.16, frontend 0.16, designer 0.10, business 0.06, marketing 0.07, qa 0.04, devops 0.03, legal 0.04 (sum = 1.00). Add after `context_rules` (top level, keep indent=2):

```json
  "legal_strict": true,
```

- [ ] **Step 2: Verify**

Run: `python3 -c "import json; w=json.load(open('config.json'))['kb']['role_weights']; print(sum(w.values()))"`
Expected: `1.0`

Run: `python3 tools/kb.py budget --db /tmp/kb-legal-test.sqlite3 --config config.json`
Expected: budget prints without error (role_weights accepted, legal present).

- [ ] **Step 3: Commit**

```bash
git add config.json
git commit -m "add legal_strict mode knob and legal KB weight (role weights sum to 1)"
```

---

### Task 4: Charter template — required Deployment jurisdictions section

**Files:**
- Modify: `templates/charter.md`
- Test: grep for the section + rendering sanity

**Interfaces:**
- Consumes: existing `templates/charter.md` structure
- Produces: a required "Deployment jurisdictions" section the PM must fill (source of truth for the jurisdiction pack and the legal worker)

- [ ] **Step 1: Add the section and renumber**

Insert after `## 7. Risks` and before `## 8. Team` (rename `## 8. Team` to `## 9. Team`):

```markdown
## 8. Deployment jurisdictions (required)
<!-- Where the project will be deployed or reach users: country/region codes, e.g. EU, US, CN.
     The PM must ask the user if this is unknown. Drives the legal advisor's jurisdiction pack. -->

## 9. Team
```

- [ ] **Step 2: Verify**

Run: `grep -n "Deployment jurisdictions\|## 9. Team" templates/charter.md`
Expected: both lines present, section order correct (1..9, no duplicates).

- [ ] **Step 3: Commit**

```bash
git add templates/charter.md
git commit -m "require Deployment jurisdictions section in charter template"
```

---

### Task 5: ORCHESTRATOR.md — jurisdiction pack, wave 2/4 wiring, gates, resume

**Files:**
- Modify: `ORCHESTRATOR.md`
- Test: grep-based checks for each new section

**Interfaces:**
- Consumes: existing wave protocol (GATE 1 -> wave 2 -> GATE 2 -> wave 3 -> wave 4), resume section, worker spawn prompt template
- Produces: the jurisdiction pack step + checklist, legal's wave 2 flow, GATE 2 blocking rule, wave 4 risk diff, resume checks

- [ ] **Step 1: Add the jurisdiction pack step (between GATE 1 and wave 2)**

Insert a new numbered step after the GATE 1 step (currently step 3, before "4. Wave 2"):

```markdown
4. Jurisdiction pack (legal): read the charter's Deployment jurisdictions section.
   For each country/region, research and write `.pmos/kb-sources/legal/jurisdiction-<cc>.md`
   with an `as_of` date, citing each law and its source URL. Checklist:
   a. data protection act (and data residency rules),
   b. AI-specific regulation (incl. phased application dates, e.g. EU AI Act),
   c. consumer / e-commerce law,
   d. licensing / export rules,
   e. industry-specific rules when in scope (fintech, health, ...).
   Ingest: `python TPL/tools/kb.py add-dir --db .pmos/kb.sqlite3 --ns legal --path .pmos/kb-sources/legal`.
   Light mode (config.json `legal_strict: false`): skip this step and the data inventory.
   Renumber the following steps accordingly (wave 2 becomes 5, etc.).
```

- [ ] **Step 2: Wave 2 set + legal worker flow**

In the wave 2 step, change the spawn set to `{architect, designer, business, legal}` and add:

```markdown
   Legal (strict mode): reads charter + legal KB namespace (jurisdiction pack first),
   then produces, in order: data inventory -> license audit -> risk register ->
   compliance calendar (all under `.pmos/out/legal/`). Rules: every risk register
   entry cites a specific law/article + source URL; unverifiable items are marked
   `requires-counsel`, never asserted. Light mode: skip data inventory, advisory
   only, no gate block.
```

- [ ] **Step 3: GATE 2 blocking rule**

In the GATE 2 step, append: `Include the risk register highlights (top risks, mitigations, jurisdiction-specific obligations). If any `severity: high` item is `status: open` and the user has not explicitly accepted it, GATE 2 is BLOCKED until resolved or accepted.`

- [ ] **Step 4: Wave 4 risk diff + mitigation re-check**

In the wave 4 step, append: `QA also re-checks that `status: mitigated` risk register items are actually implemented (owner -> delivered work) and legal does a light re-run: diff risk ids against the wave 2 register (nothing silently disappears) and append a wave-4 section with L-ids and status changes, without rewriting the register.`

- [ ] **Step 5: Resume checks**

In the resume section, add: `On resume: check the compliance calendar for overdue items (elapsed time vs due dates) and check each jurisdiction file's `as_of` date — re-research if older than 6 months or if the charter's jurisdictions changed.`

- [ ] **Step 6: Verify**

Run: `grep -n "Jurisdiction pack\|risk register\|as_of\|Deployment jurisdictions\|legal" ORCHESTRATOR.md | head -20`
Expected: all new sections present; wave numbering renumbered consistently (grep `^[0-9]*\.` on the wave block shows 1..N without duplicates).

- [ ] **Step 7: Commit**

```bash
git add ORCHESTRATOR.md
git commit -m "wire legal into waves, gates, resume: jurisdiction pack, gate blocking, risk diff"
```

---

### Task 6: pm-kb-enrich — legal namespace + cross-role propagation

**Files:**
- Modify: `skills/pm-kb-enrich/SKILL.md`
- Test: grep checks

**Interfaces:**
- Consumes: existing ns table + add-dir step
- Produces: `legal` row in the extraction table; obligations from the risk register propagated into business/marketing/pm chunks

- [ ] **Step 1: Add legal row to the extraction table**

In the table, after the `qa` row:

```markdown
| legal | deployment jurisdictions, obligations per risk id (e.g. `L-001`), compliance calendar dates |
```

- [ ] **Step 2: Add cross-role propagation rule**

After the table, append a paragraph:

```markdown
Propagation: when `.pmos/out/legal/risk-register.md` exists, also include its
obligations in the business (market entry), marketing (claims/ads compliance), and
pm (milestone gating) chunks, each tagged with the risk id (e.g. "Obligation
L-001: ..."). Keep legal facts out of other namespaces unless an obligation
actually applies to that role.
```

- [ ] **Step 3: Verify**

Run: `grep -n "legal" skills/pm-kb-enrich/SKILL.md`
Expected: the table row and the propagation paragraph present.

- [ ] **Step 4: Commit**

```bash
git add skills/pm-kb-enrich/SKILL.md
git commit -m "extend pm-kb-enrich: legal namespace and cross-role risk propagation"
```

---

### Task 7: Start skill GATE 1 + README role list

**Files:**
- Modify: `skills/project-team-start/SKILL.md`
- Modify: `README.md`
- Test: grep checks

**Interfaces:**
- Consumes: GATE 1 step in the start skill, README roles section
- Produces: jurisdiction confirmation at GATE 1; README documents the 10th role and kb-sources/legal

- [ ] **Step 1: GATE 1 jurisdiction confirmation**

In `skills/project-team-start/SKILL.md` step "GATE 1" (the model-selection step), append: `Also confirm the charter's Deployment jurisdictions with the user (edit `.pmos/charter.md` if needed); the legal advisor's jurisdiction pack depends on it.`

- [ ] **Step 2: README roles table**

In `README.md` "Roles" section, add: `legal advisor (risk & policy): regulatory risk assessment per deployment jurisdiction, risk register, compliance calendar (strict/light via config.json).` Keep it one line matching the existing style.

- [ ] **Step 3: README "What's inside"**

In the `kb-sources/<role>/*.md` bullet, extend the list: `kb-sources/legal/` (data protection, AI regulation, licensing, register/calendar templates; per-project jurisdiction packs land in `.pmos/kb-sources/legal/`).

- [ ] **Step 4: Verify**

Run: `grep -n "Deployment jurisdictions" skills/project-team-start/SKILL.md README.md; grep -n "legal" README.md`
Expected: matches in both files.

- [ ] **Step 5: Commit**

```bash
git add skills/project-team-start/SKILL.md README.md
git commit -m "confirm deployment jurisdictions at GATE 1; document legal role in README"
```

---

### Task 8: End-to-end validation

**Files:**
- No new files; regenerates `.pmos/team-model-ladder.json` (gitignored runtime artifact)
- Test: `tools/validate.py`, recommend run on the real system list

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces: proof the system is consistent end to end

- [ ] **Step 1: Run the full validator**

Run: `python3 tools/validate.py`
Expected: `ALL VALIDATION PASSED (1 environment-dependent check(s) skipped)`

- [ ] **Step 2: Refresh the ladder on the real system list**

Run: `python3 tools/recommend.py --available /tmp/list_models.txt --ladder-out .pmos/team-model-ladder.json`
Expected: the table includes a `legal` row with a suggestion (model + provider chain); ladder file regenerates without error.

- [ ] **Step 3: Sanity-check the legal suggestion**

Run: `python3 tools/recommend.py --available /tmp/list_models.txt --json 2>/dev/null | python3 -c "import json,sys; r=[x for x in json.load(sys.stdin) if x['role']=='legal'][0]; print(r['suggested'], r['suggested_provider'], r['suggested_fallbacks'], r['ladder'])"`
Expected: prints the legal suggested model, provider, fallbacks, and a non-empty ladder.

- [ ] **Step 4: Commit any leftover doc drift**

```bash
git status --short
git add -A && git commit -m "final legal advisor validation pass"  # only if changes exist
```

---

## Self-Review Notes

- Spec coverage: role+weights (Task 1), KB fundamentals (Task 2), strict/light knob (Task 3), charter jurisdictions (Task 4), jurisdiction pack + waves/gates/resume (Task 5), cross-role propagation (Task 6), GATE 1 confirm + README (Task 7), risk diff and compliance calendar live in Task 5 (steps 4-5) and the KB templates (Task 2 steps 4-5), validation (Task 8).
- No placeholders: all JSON/MD/YAML content is written out inline.
- Type consistency: `legal` key, `legal_strict`, `kb.role_weights` values, `DEFAULT_PURPOSE["legal"]`, and artifact paths are identical across tasks.
