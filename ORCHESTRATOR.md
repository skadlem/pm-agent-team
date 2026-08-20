# PMOS Orchestrator Protocol

This file is the operating manual for the MAIN session (coordinator). Workers never see it
directly; their spawn prompts embed the parts that concern them.

Layout: `TPL` = this template folder (find it via `~/.jcode/pmos-template-root`, else the skill's
grandparent dir). `PROJ` = the project repo root. Project state lives in `PROJ/.pmos/`.

```
.pmos/
  charter.md          # PM owns; source of truth for scope
  plans/plan.md       # PM owns; phases, task graph, acceptance criteria
  decisions/          # architect ADRs
  kb.sqlite3          # hybrid KB store (never dump it; only search)
  kb-sources/         # markdown files that were indexed (audit trail)
  out/<role>/         # each worker's artifacts
  log.md              # append-only checkpoint log
```

## Rules (all agents, no exceptions)

1. Partial context only. NEVER read or dump the full KB, the full repo, or large files top-to-bottom.
2. Information retrieval order, stop as soon as you have enough:
   a. KB: `python TPL/tools/kb.py search --db PROJ/.pmos/kb.sqlite3 "query" --role <ns> -k 5`
   b. Repo questions: use the /graphify skill's query tools (never re-read the whole codebase).
      After material changes to the repo, the coordinator refreshes with `/graphify <path> --update`.
      Code-touching workers (architect, backend, frontend, devops, qa) MUST run at least one
      graphify query before editing anything and record each query in their notes
      (.pmos/out/<role>/notes.md). The coordinator checks this at every checkpoint.
   c. Targeted file read (read tool) ONLY for a specific file you already know you need.
3. Artifacts are small files (markdown) under `.pmos/out/<role>/`. Keep each under ~300 lines.
3b. Anything another role must point at carries a STABLE ID: charter requirements `R-NNN`, plan
   tasks `T-NNN` and acceptance criteria `A-NNN`, decisions `ADR-NNN`, risks `L-NNN`. References
   between them use the fields in ARTIFACT-SCHEMA.md (`satisfies`, `depends_on`, `decided_by`,
   `verifies`, `mitigated_by`, `supersedes`). Ids are never renumbered or reused. Prose stays
   prose; only the things other waves depend on need an id. Verify any time with
   `python TPL/tools/artifacts.py --project .` - it is free, deterministic, and needs no model.
4. Before claiming done, apply the verification-before-completion skill: evidence, not assertions.
5. Disagreements between roles are escalated to the coordinator, who asks the user if stakes are high.
6. Model fallback (see "Worker model fallback" below): a failed worker (out of tokens, crash,
   unrecoverable error) is retried on the NEXT model in that role's fallback ladder, never abandoned
   because of the model. Log every retry.

## Launch: user says "Start the project <description>"

(If the user says "Work on this project ..." instead, that is the /project-team-work skill:
identical protocol, but MODE is forced to brownfield, skip detection.)

First detect the MODE:
- `brownfield`: the repo contains existing code (any source files besides .pmos). Most steps below
  have brownfield-specific behavior.
- `greenfield`: empty repo / no code yet. The original flow.

If the git tree is DIRTY (uncommitted changes not from this session), ask ONCE at launch whether
agents may commit alongside your work (staging ONLY agent-written paths) or should leave commits
to you. Record the answer in `.pmos/log.md`.

1. Bootstrap:
   - `mkdir .pmos/{plans,decisions,log,kb-sources}` and `python TPL/tools/kb.py init --db .pmos/kb.sqlite3`
   - If `.pmos/kb.sqlite3` already exists, this is a resumed project: read `.pmos/log.md` tail and charter instead.
   - Load the /graphify skill and build/update the repo graph (skip if empty greenfield repo).
     Brownfield: if `graphify-out/graph.json` is missing, run `/graphify <path>` NOW and do not
     proceed to Wave 0 until the graph exists (Wave 0 and every worker repo query depends on it).
     Say so to the user when you build it.
   - Brownfield: propose adding `.pmos/kb.sqlite3` to the project `.gitignore` (binary, regenerable;
     everything else in .pmos is plain markdown and should be committed).

Pre-GATE-1 worker model: Wave 0 (discovery) and Wave 1 (PM) spawn BEFORE the team model table
  exists (GATE 1). NEVER spawn them without an explicit model: an unmodeled spawn inherits the
  swarm default (e.g. Fable 5), which may be a model the user forbids. Instead, run
  `swarm list_models` once, pick the cheapest AVAILABLE model NOT in roster.json
  `forbidden_models` (the user may name a different temporary model), and pass it explicitly
  at spawn (`model` in the swarm tool). Log the choice in `.pmos/log.md`. This is temporary:
  GATE 1 still decides the real per-role team models.

2. Wave 0 (DISCOVERY, brownfield only): spawn ONE architect-labeled worker with the assignment:
   map the existing system using graphify queries (never full reads). Output
   `.pmos/out/architect/current-state.md` (<300 lines): module map with ownership/responsibilities,
   tech stack + versions, conventions (naming, error handling, test layout), test suite state
   (how to run it, known red tests), top integration points, and the areas relevant to the user's
   stated goal. This artifact drives charter, roster, and enrichment.
3. Wave 1 (PM): spawn one PM worker. Its prompt = template below + charter skeleton from
   `TPL/templates/charter.md` (greenfield) or `TPL/templates/charter-brownfield.md` (brownfield)
   + the user's project description + `.pmos/out/architect/current-state.md` when present.
   PM writes charter, plan (skeleton: `TPL/templates/plan.md`), and `out/pm/roster-proposal.md`
   listing the MINIMAL team needed (roles + one-line justification each).
   The charter's in-scope items get `R-NNN` ids and the plan's tasks/acceptance criteria get
   `T-NNN`/`A-NNN` blocks pointing back at them (rule 3b). Before reporting done, the PM runs
   `python TPL/tools/artifacts.py --project .` and fixes every ERROR.
   Brownfield roster rule: justify roles from the IMPACT SURFACE in current-state.md (which
   modules the change touches), not from the project type. E.g. a backend refactor that touches
   no UI gets no designer and no frontend.
4. GATE 1 (STOP and ask the user): present the roster proposal AND the model selection.
   FIRST check for the user's saved defaults in `~/.jcode/pmos-team-defaults.json`. If it
   exists, propose that role -> model table as-is (it is the user's explicit preference); only
   verify each listed model still appears in `swarm list_models`, and flag any that do not.
   Otherwise compute the model selection LIVE:
   a. Run `swarm list_models` and save its output to `.pmos/available-models.txt`.
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
        [--task T-NNN] [--status ok|failed]`, taking the token counts from the swarm result.
        Record FAILED runs too - a worker that died on a context limit still cost money.
        If the host does not report usage, pass your own numbers with `--source estimated` so
        the report can keep guesses apart from measurements. Never skip the record: an unrecorded
        run makes the remaining budget wrong for every later wave.
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
   FIRST run `python TPL/tools/artifacts.py --project .`. Any ERROR blocks the gate: a reference
   that does not resolve means a wave handed off to something that does not exist. Report the
   warnings in the summary (scope with no task, task with no acceptance criterion, high-severity
   open risk with no mitigating task); the user may accept them knowingly.
   `python TPL/tools/trace.py coverage --project .` renders the same thing as a scope -> task ->
   criterion tree, which is usually the clearest way to show the user what they are approving.
   For anything the standard reports do not answer, query the graph directly:
   `python TPL/tools/kg.py query --project . --name open-high-risks` (see `kg.py queries` for the
   stored library, ARTIFACT-SCHEMA.md for the vocabulary).
   Include the risk register highlights (top risks, mitigations, jurisdiction-specific
   obligations). If any `severity: high` item is `status: open` and the user has not explicitly
   accepted it, GATE 2 is BLOCKED until resolved or accepted.
9. Wave 3: implementation. Spawn backend/frontend/devops/marketing per the task graph, parallel
   where independent. Name the `T-NNN` ids each worker owns in its assignment, and have it record
   them in its notes; that is what later ties delivered code back to the charter. Each worker fills
   in its task's `touches:` with the paths it actually changed - that is the join between the plan
   and the code graph, and what `trace.py unplanned` checks against. Workers read plan + their role's out dir, query KB + graphify as needed.
   BEFORE spawning Wave 3, check the graph is fresh: compare the newest source file mtime under
   the project (excluding .pmos/, graphify-out/, .git/) against `graphify-out/graph.json`; if any
   source is newer, run `/graphify <path> --update` first and say so.
10. Wave 4 (QA): run the verification gate against the acceptance criteria in the plan. Fail -> back
   to wave 3 with the defect report. Pass -> checkpoint.
   `python TPL/tools/trace.py coverage --project .` prints the requirement -> task -> criterion -> QA
   matrix to work through, so no criterion is verified twice and none is silently skipped.
   Brownfield: QA FIRST runs the project's existing test suite and records the baseline in its
   report (pre-existing failures vs failures introduced by the change), and verifies nothing in
   the charter's do-not-touch list changed.
   QA reports one line per acceptance criterion in `.pmos/out/qa/test-report.md`:
   `- A-NNN: pass|fail - <evidence>`. A criterion with no line is not "passed", it is unreported.
   `python TPL/tools/artifacts.py --project .` then makes the next two checks mechanical: it errors
   on a result for a criterion nobody defined, and warns when a `status: mitigated` risk points at a
   task whose criteria did not pass. `kg.py query --name unproven-mitigations` and
   `--name untested-code` answer the same questions against the graph when you need the detail.
   QA also re-checks that `status: mitigated` risk register items are actually implemented (owner
   -> delivered work) and legal does a light re-run: diff risk ids against the wave 2 register
   (nothing silently disappears) and append a wave-4 section with L-ids and status changes,
   without rewriting the register.
11. Checkpoint: append to `.pmos/log.md` (date, wave, what shipped, what's next), commit if repo,
   report to user. Commit as you go at each gate. Also verify each code-touching worker's notes
   record the graphify queries they ran (rule 2b); flag any worker that edited without one
   (re-run its graphify queries and re-check its diff). Record measurable facts too, so the run
   can be evaluated afterwards: number of workers spawned, QA gate pass/fail and defect count,
   rework loops (wave 4 -> wave 3), KB budget usage (`kb.py budget`), and acceptance criteria
   pass rate.
   Also run `python TPL/tools/cost.py report --project .` and log actual spend, the remaining
   budget, and its estimate-accuracy line; exit code 2 means the project is over `budget_usd`, so
   stop and ask. Every few waves run `python TPL/tools/cost.py calibrate --project . --write` so
   later estimates come from this project's own measured usage instead of the flat default.
   Run `python TPL/tools/artifacts.py --project .` at every checkpoint and log its counts plus any
   findings, so traceability breaks surface in the wave that caused them rather than at QA.
   Then run `python TPL/tools/trace.py unplanned --project .`: it lists changed files no task claims.
   Each one is either work that needs a task (scope creep, caught in the wave that caused it) or a
   `touches:` entry a worker forgot. Resolve them before the checkpoint closes; log the count.

Cost-quality defaults (see roster.json for the live values): critical roles (pm, architect, qa)
  keep a 0.95 tier (near-best score only), implementation roles (backend, legal) 0.92, frontend/
  devops 0.88, and advisory roles (designer, business, marketing) 0.80 so cheap models win there.
  Advisory roles also default to `low` effort. This is the template's default balance: swap a role
  to a HIGHER tier (0.95) when its output quality matters more than cost, or LOWER (0.80) for
  one-off advisory output.

## Worker spawn prompt template

```
You are the {{role_name}} on this project. Working dir: {{PROJ}}.
Spawn model: {{model}} (effort {{effort}}). Pre-GATE-1 waves: the temporary model picked
per the "Pre-GATE-1 worker model" rule. Post-GATE-1: per the user-approved team-model.json.

Your assignment:
{{assignment}}

Mandatory procedure:
1. Load these skills: {{role_skills}} (plus verification-before-completion).
2. Context: read .pmos/charter.md and {{relevant upstream artifacts}}.
3. Knowledge base: search BEFORE answering anything domain-specific:
   python "{{TPL}}/tools/kb.py" search --db "{{PROJ}}/.pmos/kb.sqlite3" "<query>" --role {{ns}} -k 5
   You may add one --role shared search too. Never dump the DB.
4. Repo questions: use the graphify skill (query mode), never full-repo reads.
   BROWNFIELD RULE: before writing or changing any code, graphify-query for existing similar
   patterns and read .pmos/out/architect/current-state.md conventions; conform to them.
   New code must look like it belongs in this codebase.
5. Write outputs to {{artifacts}}. Keep them concise. Anything another role must reference
   carries a stable id, and every reference you make (`satisfies`, `depends_on`, `decided_by`,
   `verifies`, `mitigated_by`, `supersedes`) names an id that already exists - see
   ARTIFACT-SCHEMA.md. Check your own work with
   `python "{{TPL}}/tools/artifacts.py" --project "{{PROJ}}"` before reporting done.
6. Report back: what you did, decisions made, blockers, artifacts written.
```

Spawn via the `swarm` tool with a clear `label` like "pm", "architect", "backend-1". Use one
worker per task chunk; parallelize independent chunks.

## Worker model fallback (failed / out of tokens)

The recommended model is only the FIRST attempt. Every role has an ordered fallback ladder in
`.pmos/team-model-ladder.json` (written by `recommend.py --ladder-out`; best-first by benchmark
score, then cheapest). The `suggested` model in `.pmos/team-model.json` is the first attempt; the
ladder's next entries are the fallbacks.

When a worker reports failed or crashed (e.g. ran out of tokens / context-limit, or an
unrecoverable error) and the task is not inherently impossible, retry the SAME task on the next
untried model in that role's ladder:

1. Log the failure in `.pmos/log.md` (role, task, model tried, failure reason).
2. If the failed model is served by more than one provider on this system, first retry the SAME
   model on the next provider in its fallback chain (`suggested_fallbacks` in `recommend.py`
   output; `providers`/`routes` JSON fields map every ladder entry to its chain and route ids,
   e.g. `glm-5.2` -> `[OpenAI-compatible, NVIDIA NIM]`).
3. Spawn a FRESH worker for that task, passing the next model explicitly (`model` in the swarm
   spawn). Never continue a half-finished run; re-run the task from its clean start.
4. Reuse the task's upstream artifacts (plan, out dirs, KB); do not re-run independent
   already-completed tasks.
5. Cap fallbacks per task at `max_fallbacks_per_task` (config.json `context_rules`, default 4). After that, STOP and escalate to the user:
   give the failure reason and the models already tried. Do not loop indefinitely.
6. If a role's ladder is empty or exhausted, escalate to the user rather than guessing.

The coordinator may also apply the ladder proactively: if a cheap pick repeatedly errors mid-run,
promote that role's model to the next best entry from the start (log it). This keeps the team
moving without surfacing every transient failure to the user.

## Resume in a future session

When a project directory already has `.pmos/`, do NOT guess where it left off from memory. Run
the state detector first; it answers three questions deterministically from artifacts on disk:

1. **DETECT**: `python TPL/tools/state.py --project . --config TPL/config.json` prints the current
   stage (0..9, e.g. "GATE 1 passed", "implementation started"), the next ORCHESTRATOR step, and a
   pre-flight check list covering everything ALREADY completed up to that stage: artifacts present
   and non-empty, team-model.json / team-model-ladder.json valid, `kb.py budget` runs on the
   project DB, log.md records each passed gate, jurisdiction `as_of` dates not stale (>= 180 days
   warns). Use `--json` when scripting. Stage detection is artifact-based, so it is robust even if
   log.md is missing lines.
2. **VERIFY**: read the check list. All OK -> continue (below). Any WARN -> note it, continue. Any
   FAIL -> FIX the broken artifact, do not redo the stage: regenerate the failing file from the
   log / upstream artifacts (re-derive team-model.json from the GATE 1 log entry, re-run the role
   that owns the missing artifact, restore from git), then re-run state.py until clean.
   If a stage rolled back because its marker vanished (e.g. a wave-3 artifact is missing), the
   rolled-back stage IS the answer: resume from that step, reusing every artifact that still
   exists. Never re-run completed waves just because a marker file was lost.
3. **CONTINUE**: report "project is at stage N (<name>); next: <step>" to the user and confirm it
   matches what they want (they may want to re-open a completed stage instead). Then resume the
   launch protocol from that step. GATE 1 / GATE 2 still stop for user approval.

On resume also check the compliance calendar for overdue items (elapsed time vs due dates) and
each jurisdiction file's `as_of` date: re-research if older than 6 months (state.py warns at
180 days) or if the charter's jurisdictions changed. The KB and graphify index persist across
sessions; nothing is rebuilt from scratch.
