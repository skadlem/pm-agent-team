# Stage: Wave 2 + GATE 2 (steps 5-8)

Read ORCHESTRATOR.md (core rules) first. This file covers the jurisdiction pack, the design
wave, KB enrichment, and the second user gate.

5. Jurisdiction pack (legal): read the charter's Deployment jurisdictions section.
   For each country/region, research and write `.pmos/kb-sources/legal/jurisdiction-<cc>.md`
   with an `as_of` date, citing each law and its source URL. Checklist:
   a. data protection act (and data residency rules),
   b. AI-specific regulation (incl. phased application dates, e.g. EU AI Act),
   c. consumer / e-commerce law,
   d. licensing / export rules,
   e. industry-specific rules when in scope (fintech, health, ...).
   Ingest: `python TPL/tools/kb.py add-dir --db .pmos/kb.sqlite3 --ns legal --path .pmos/kb-sources/legal`.
   Light mode (config.json `legal_strict: false`): skip this step and the data inventory.
   Renumber the following steps accordingly (wave 2 becomes 6, etc.).
6. Wave 2: spawn approved roles from {architect, designer, business, legal} IN PARALLEL.
   Architect: every ADR keeps its `# ADR-NNN: title` heading id and names what it `Supersedes:`;
   tasks it constrains cite it with `decided_by:` in the plan. Legal: each risk entry carries
   `mitigated_by: <task id>` once the mitigating work exists in the plan. Each reads
   `.pmos/charter.md` and searches its KB namespace first. Brownfield: each also reads
   `.pmos/out/architect/current-state.md` and MUST design the change to fit existing conventions,
   not idealized ones. Outputs go to `.pmos/out/<role>/`.
   Legal (strict mode): reads charter + legal KB namespace (jurisdiction pack first),
   then produces, in order: data inventory -> license audit -> risk register ->
   compliance calendar (all under `.pmos/out/legal/`). Rules: every risk register
   entry cites a specific law/article + source URL; unverifiable items are marked
   `requires-counsel`, never asserted. Light mode: skip data inventory, advisory
   only, no gate block.
7. Enrich: run the /pm-kb-enrich skill (adds project-specific facts to each role namespace from
   charter + wave 2 outputs; brownfield: also from current-state.md). Budget check: `kb.py budget`.
   Re-run it after ANY later scope change (new/superseded ADR, revised plan): re-indexing updates
   chunks in place and prunes facts deleted from their source file, so workers stop retrieving a
   decision the project has moved off. Log the `N new, N updated, N pruned` line.
8. GATE 2: summarize plan + architecture + key decisions for the user. Ask for go-ahead.
   FIRST run `python TPL/tools/artifacts.py --project .`. Present the gate as a VERDICT, not a
   dump — one line up front, computed from the linter:
   - `PASS` — exit 0, no warnings: clean handoff.
   - `CONCERNS` — exit 0 with warnings: list the top warnings as bullets; the user may accept
     them knowingly.
   - `FAIL` — any ERROR (exit 1): a reference that does not resolve means a wave handed off to
     something that does not exist. The gate is blocked until fixed.
   `python TPL/tools/trace.py coverage --project .` renders the same thing as a scope -> task ->
   criterion tree, which is usually the clearest way to show the user what they are approving.
   For anything the standard reports do not answer, query the graph directly:
   `python TPL/tools/kg.py query --project . --name open-high-risks` (see `kg.py queries` for the
   stored library, ARTIFACT-SCHEMA.md for the vocabulary).
   Include the risk register highlights (top risks, mitigations, jurisdiction-specific
   obligations). If any `severity: high` item is `status: open` and the user has not explicitly
   accepted it, the verdict is FAIL and GATE 2 is BLOCKED until resolved or accepted.
   SECOND OPINION (cross-model, gstack /codex pattern, docs/research/2026-08-24-gstack.md):
   whenever a high-severity open risk exists at this gate, run ONE extra worker BEFORE
   presenting — a reviewer on the cheapest model of a DIFFERENT family than the pm's model
   (they planned the work; the second set of eyes must not be the same brain). Pick it
   deterministically: `python TPL/tools/recommend.py second-opinion --pm-model <pm model>
   --available .pmos/available-models.txt` (never a forbidden model, never the pm's family).
   The task: adversarially re-read ONLY the risk-relevant sections (charter Risks, the risk
   register, the plan's tasks that claim `mitigated_by`), using `TPL/templates/second-opinion.md`;
   the output is `.pmos/out/pm/second-opinion.md` listing overlapping vs unique findings and
   whether any accepted mitigation actually holds. Record the run in the cost ledger like any
   worker. Two families disagreeing is normal — the unique findings are what the user must
   see at the gate, not the agreement.
   ADVERSARIAL REQUIREMENTS REVIEW (pre-GATE-2, L-3): before presenting the plan, run ONE
   reviewer worker on the cheapest available model with `TPL/templates/adversarial-review.md`.
   The reviewer attacks every R-NNN against six checklist items (testable, unambiguous,
   measured, dependent, missing, risk-blind) and writes `.pmos/out/pm/adversarial-review.md`.
   A CONCERNS verdict sends the plan back to the PM (fix + `artifacts.py` re-lint + re-review)
   BEFORE the user sees it — a requirement that dies at the gate is cheap; one that dies in
   wave 3 costs a rework loop.

Next: `docs/stages/wave3.md` (steps 9-10).
