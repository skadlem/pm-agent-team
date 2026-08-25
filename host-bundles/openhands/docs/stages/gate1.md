# Stage: GATE 1 (steps 3-4)

Read ORCHESTRATOR.md (core rules) first. This file covers the PM wave and the first user gate
(roster + model table + budget).

3. Wave 1 (PM): spawn one PM worker. Its prompt = template below + charter skeleton from
   `TPL/templates/charter.md` (greenfield) or `TPL/templates/charter-brownfield.md` (brownfield)
   + the user's project description + `.pmos/out/architect/current-state.md` when present.
   PM writes charter, plan (skeleton: `TPL/templates/plan.md`), and `out/pm/roster-proposal.md`
   listing the MINIMAL team needed (roles + one-line justification each).
   The charter template opens with six forcing questions (section 0); the PM answers them FIRST
   and asks the user for anything unknown — a charter that skips them builds the wrong thing
   well.
   The charter's in-scope items get `R-NNN` ids and the plan's tasks/acceptance criteria get
   `T-NNN`/`A-NNN` blocks pointing back at them (rule 3b). Before reporting done, the PM runs
   `python TPL/tools/artifacts.py --project .` and fixes every ERROR.
   Brownfield roster rule: justify roles from the IMPACT SURFACE in current-state.md (which
   modules the change touches), not from the project type. E.g. a backend refactor that touches
   no UI gets no designer and no frontend.
4. GATE 1 (STOP and ask the user): present the roster proposal AND the model selection.
   FIRST check for the user's saved defaults in `~/.openhands/pmos-team-defaults.json`. If it
   exists, propose that role -> model table as-is (it is the user's explicit preference); only
   verify each listed model still appears in your LiteLLM provider's model list, and flag any that do not.
   Otherwise compute the model selection LIVE:
   a. Run your LiteLLM provider's model list and save its output to `.pmos/available-models.txt`.
   b. Run `python TPL/tools/recommend.py --available .pmos/available-models.txt --json
      --ladder-out .pmos/team-model-ladder.json` to score each available model per role purpose
      (benchmarks.json), keep each role's best tier (per-role `role_tiers` in roster.json, NOT a
      flat threshold), and pick the cheapest of that tier. Show that table, including each role's
      default effort (roster.json `role_effort`) and its blended $/1M cost.
      The `--ladder-out` file holds each role's best-first fallback ladder for the model-fallback rule.
   c. The user may OK the table, change a model/effort, or remove a role entirely.
      Record the approved (role -> model, effort) map in `.pmos/team-model.json`.
   d. If a role has no benchmark data (marked by recommend.py), refresh first:
      `python TPL/tools/recommend.py refresh` and update benchmarks.json, or let the
      user pick manually for that role. Do not proceed without approval.
   e. COST GUARDRAIL: ask the user for a project spend cap in USD (default: config.json
      `cost.max_project_cost_usd`, currently 20). Write it to `.pmos/team-model.json`
      as `budget_usd`. From then on the ledger, not arithmetic in your head, tracks spend:

      - BEFORE each wave: `python TPL/tools/cost.py estimate --project . --roles <roles> --wave N`.
        It prices each role's approved model and uses THIS project's measured history for roles
        that have any (`--write`n by calibrate), the flat config estimate for the rest. Exit code
        2 means the wave would breach `budget_usd`: STOP and ask the user to raise the cap, drop
        a role, or move a role to a cheaper model. Log the estimate.
      - AFTER each worker returns: `python TPL/tools/cost.py record --project . --role <role>
        --model <model> --wave N --label <label> --in <tokens_in> --out <tokens_out>
        [--task T-NNN] [--status ok|failed]`, taking the token counts from the runner's JSON result.
        Record FAILED runs too - a worker that died on a context limit still cost money.
        If the host does not report usage, pass your own numbers with `--source estimated` so
        the report can keep guesses apart from measurements. Never skip the record: an unrecorded
        run makes the remaining budget wrong for every later wave.
      - THEN the event: `python TPL/tools/events.py record --project . --ladder <index>
        [--role <role> --wave N --model <model>]` — it attaches the ledger row just written to
        the wave-event trace (`.pmos/waves.jsonl`), with the fallback-ladder index used (0 =
        first attempt; the ladder rule below increments it on every retry). Pass the identity
        flags when several workers return in a burst. This is what makes per-run metrics
        comparable across projects; `state.py` reports it on resume.

Cost-quality defaults (see roster.json for the live values): critical roles (pm, architect, qa)
  keep a 0.95 tier (near-best score only), implementation roles (backend, legal) 0.92, frontend/
  devops 0.88, and advisory roles (designer, business, marketing) 0.80 so cheap models win there.
  Advisory roles also default to `low` effort. This is the template's default balance: swap a role
  to a HIGHER tier (0.95) when its output quality matters more than cost, or LOWER (0.80) for
  one-off advisory output.

Next: `docs/stages/wave2.md` (steps 5-8).
