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
   c. Targeted file read (read tool) ONLY for a specific file you already know you need.
3. Artifacts are small files (markdown) under `.pmos/out/<role>/`. Keep each under ~300 lines.
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
   - Brownfield: propose adding `.pmos/kb.sqlite3` to the project `.gitignore` (binary, regenerable;
     everything else in .pmos is plain markdown and should be committed).
2. Wave 0 (DISCOVERY, brownfield only): spawn ONE architect-labeled worker with the assignment:
   map the existing system using graphify queries (never full reads). Output
   `.pmos/out/architect/current-state.md` (<300 lines): module map with ownership/responsibilities,
   tech stack + versions, conventions (naming, error handling, test layout), test suite state
   (how to run it, known red tests), top integration points, and the areas relevant to the user's
   stated goal. This artifact drives charter, roster, and enrichment.
3. Wave 1 (PM): spawn one PM worker. Its prompt = template below + charter skeleton from
   `TPL/templates/charter.md` (greenfield) or `TPL/templates/charter-brownfield.md` (brownfield)
   + the user's project description + `.pmos/out/architect/current-state.md` when present.
   PM writes charter, plan, and `out/pm/roster-proposal.md` listing the MINIMAL team needed
   (roles + one-line justification each).
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
      as `budget_usd`. Before each wave, estimate spend = sum over spawned workers of
      (model's `cost_per_1m` from recommend.py --json) x (config.json `cost.est_tokens_per_worker`
      / 1M); log each wave's estimate in `.pmos/log.md`. If the running estimate exceeds
      `budget_usd`, STOP and ask: raise the cap, drop a role, or move a role to a cheaper model.
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
6. Wave 2: spawn approved roles from {architect, designer, business, legal} IN PARALLEL. Each reads
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
8. GATE 2: summarize plan + architecture + key decisions for the user. Ask for go-ahead.
   Include the risk register highlights (top risks, mitigations, jurisdiction-specific
   obligations). If any `severity: high` item is `status: open` and the user has not explicitly
   accepted it, GATE 2 is BLOCKED until resolved or accepted.
9. Wave 3: implementation. Spawn backend/frontend/devops/marketing per the task graph, parallel
   where independent. Workers read plan + their role's out dir, query KB + graphify as needed.
10. Wave 4 (QA): run the verification gate against the acceptance criteria in the plan. Fail -> back
   to wave 3 with the defect report. Pass -> checkpoint.
   Brownfield: QA FIRST runs the project's existing test suite and records the baseline in its
   report (pre-existing failures vs failures introduced by the change), and verifies nothing in
   the charter's do-not-touch list changed.
   QA also re-checks that `status: mitigated` risk register items are actually implemented (owner
   -> delivered work) and legal does a light re-run: diff risk ids against the wave 2 register
   (nothing silently disappears) and append a wave-4 section with L-ids and status changes,
   without rewriting the register.
11. Checkpoint: append to `.pmos/log.md` (date, wave, what shipped, what's next), commit if repo,
   report to user. Commit as you go at each gate. Record measurable facts too, so the run can be
   evaluated afterwards: number of workers spawned, QA gate pass/fail and defect count, rework
   loops (wave 4 -> wave 3), KB budget usage (`kb.py budget`), and acceptance criteria pass rate.
   Also log the estimated spend (see GATE 1 cost guardrail) and the remaining budget against
   `budget_usd`; stop and ask if the estimate is over the cap.

Cost-quality defaults (see roster.json for the live values): critical roles (pm, architect, qa)
  keep a 0.95 tier (near-best score only), implementation roles (backend, legal) 0.92, frontend/
  devops 0.88, and advisory roles (designer, business, marketing) 0.80 so cheap models win there.
  Advisory roles also default to `low` effort. This is the template's default balance: swap a role
  to a HIGHER tier (0.95) when its output quality matters more than cost, or LOWER (0.80) for
  one-off advisory output.

## Worker spawn prompt template

```
You are the {{role_name}} on this project. Working dir: {{PROJ}}.
Spawn model: {{model}} (effort {{effort}}) per the user-approved team-model.json.

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
5. Write outputs to {{artifacts}}. Keep them concise.
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

When `.pmos/` exists: read `.pmos/log.md` (tail), `.pmos/charter.md`, then `kb.py budget` and
`kb.py stats` to see KB health, then continue from the last checkpoint. The KB and graphify index
persist across sessions; nothing is rebuilt from scratch.
On resume: check the compliance calendar for overdue items (elapsed time vs due dates) and check
each jurisdiction file's `as_of` date — re-research if older than 6 months or if the charter's
jurisdictions changed.
