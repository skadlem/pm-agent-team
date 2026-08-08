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
   b. Run `python TPL/tools/recommend.py --available .pmos/available-models.txt --json`
      to score each available model per role purpose (benchmarks.json), keep the best
      tier, and pick the cheapest of that tier. Show that table.
   c. The user may OK the table, change a model/effort, or remove a role entirely.
      Record the approved (role -> model, effort) map in `.pmos/team-model.json`.
   d. If a role has no benchmark data (marked by recommend.py), refresh first:
      `python TPL/tools/recommend.py refresh` and update benchmarks.json, or let the
      user pick manually for that role. Do not proceed without approval.
4. Wave 2: spawn approved roles from {architect, designer, business} IN PARALLEL. Each reads
   `.pmos/charter.md` and searches its KB namespace first. Brownfield: each also reads
   `.pmos/out/architect/current-state.md` and MUST design the change to fit existing conventions,
   not idealized ones. Outputs go to `.pmos/out/<role>/`.
5. Enrich: run the /pm-kb-enrich skill (adds project-specific facts to each role namespace from
   charter + wave 2 outputs; brownfield: also from current-state.md). Budget check: `kb.py budget`.
6. GATE 2: summarize plan + architecture + key decisions for the user. Ask for go-ahead.
7. Wave 3: implementation. Spawn backend/frontend/devops/marketing per the task graph, parallel
   where independent. Workers read plan + their role's out dir, query KB + graphify as needed.
8. Wave 4 (QA): run the verification gate against the acceptance criteria in the plan. Fail -> back
   to wave 3 with the defect report. Pass -> checkpoint.
   Brownfield: QA FIRST runs the project's existing test suite and records the baseline in its
   report (pre-existing failures vs failures introduced by the change), and verifies nothing in
   the charter's do-not-touch list changed.
9. Checkpoint: append to `.pmos/log.md` (date, wave, what shipped, what's next), commit if repo,
   report to user. Commit as you go at each gate. Record measurable facts too, so the run can be
   evaluated afterwards: number of workers spawned, QA gate pass/fail and defect count, rework
   loops (wave 4 -> wave 3), KB budget usage (`kb.py budget`), and acceptance criteria pass rate.

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
worker per task chunk; parallelize independent chunks (see /dispatching-parallel-agents).

## Resume in a future session

When `.pmos/` exists: read `.pmos/log.md` (tail), `.pmos/charter.md`, then `kb.py budget` and
`kb.py stats` to see KB health, then continue from the last checkpoint. The KB and graphify index
persist across sessions; nothing is rebuilt from scratch.
