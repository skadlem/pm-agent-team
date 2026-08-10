---
name: project-team-start
description: "Launch a managed multi-agent project team. Triggers on 'Start the project ...' or 'start project' (mode auto-detected; for an existing codebase you can also say 'Work on this project ...' which uses the project-team-work skill instead). Bootstraps .pmos/ state, picks the minimal role roster (PM, architect, designer, backend, frontend, business, marketing, QA, devops) with user approval, runs wave-based execution with hybrid-KB + graphify context rules. Loads the PMOS orchestrator protocol."
---

# /project-team-start

You are about to run the PMOS project-management system. Follow it exactly.

## Step 0: locate the template

1. Read the file `~/.jcode/pmos-template-root` (e.g. `type %USERPROFILE%\.jcode\pmos-template-root`
   on Windows) to get `TPL`, the template folder.
2. If that file is missing, tell the user to run `install.cmd` (or `install.sh`) in the
   `pm-agent-team` folder and stop.

## Step 1: load the protocol

Read `TPL/ORCHESTRATOR.md` in full. It is your operating manual for this launch. Also read
`TPL/roster.json` (role definitions, skills per role, wave order, gates) and `TPL/config.json`
(KB caps and context rules).

## Step 2: check for an existing project

If the current working directory already contains `.pmos/`:
- This is a RESUME, not a fresh start. Run the state detector FIRST (do not guess from memory):
  `python TPL/tools/state.py --project . --config TPL/config.json`.
  It reports the stage the project is at (0..9), the next launch step, and a pre-flight check
  list for everything completed so far (artifacts non-empty, team-model JSON valid, KB budget
  runs, gates logged, jurisdiction `as_of` fresh).
- All OK: report "project is at stage N (<name>); next: <step>", confirm with the user, and
  continue the wave protocol from that step. WARNs: note them, continue. FAILs: fix the broken
  artifact from log/git, re-run state.py until clean; never redo a completed stage.
- Ask the user what they want to continue with, then continue the wave protocol from the log.

Otherwise detect the MODE, then proceed with a fresh launch per ORCHESTRATOR.md:
- **brownfield**: the repo already contains source code (any code/config files besides .pmos).
- **greenfield**: empty repo or docs only.
State the detected mode to the user and note it applies automatically, e.g. "Starting in
brownfield mode: I'll map the existing codebase first, then plan the change." The flow differs
only where ORCHESTRATOR.md says "Brownfield:" (discovery wave, impact-based roster, delta
charter, baseline QA). No extra command or flag is needed.

## Step 3: fresh launch

1. Create `.pmos/` skeleton (plans, decisions, kb-sources, log, out) and init the KB:
   `python TPL/tools/kb.py init --db .pmos/kb.sqlite3`.
2. If the user has NOT already run /pm-kb-bootstrap for this project, run the /pm-kb-bootstrap
   skill now (it fills the per-role fundamentals into the KB with the token cap enforced).
3. If the repo has code (brownfield), build/update the graphify index (load the /graphify skill;
   use `--update` if `graphify-out/` already exists) and run WAVE 0 discovery per ORCHESTRATOR.md
   before spawning the PM. Greenfield empty repo: skip and note it.
4. Wave 1: spawn the PM worker using the spawn prompt template in ORCHESTRATOR.md, passing the
   user's project description. Wait for charter + plan + roster proposal.
   IMPORTANT: Wave 0 and Wave 1 run BEFORE the team model table exists. Spawn them with an
   EXPLICIT temporary model (cheapest AVAILABLE model not in TPL/roster.json `forbidden_models`,
   per ORCHESTRATOR.md "Pre-GATE-1 worker model"), never an unmodeled spawn (that inherits the
   swarm default, e.g. Fable 5). GATE 1 still decides the real team models.
5. GATE 1 (STOP and ask the user): present the proposed roster and scope summary, AND the model
   selection. If `~/.jcode/pmos-team-defaults.json` exists, propose it as the role -> model table
   (user's saved preference; verify its models are still in `swarm list_models`). Otherwise compute
   it LIVE:
   a. Run `swarm list_models` and save its output to `.pmos/available-models.txt`.
   b. Run `python TPL/tools/recommend.py --available .pmos/available-models.txt
      --ladder-out .pmos/team-model-ladder.json` to score each available model per role purpose
      from `TPL/benchmarks.json`, keep each role's best tier (per-role `role_tiers` in
      `TPL/roster.json`, NOT a flat threshold), and pick the cheapest of that tier. Show the
      resulting role -> model table with each role's default effort (`role_effort`) and blended
      $/1M cost. The ladder file is the per-role fallback order for the model-fallback rule
      (see ORCHESTRATOR.md "Worker model fallback").
   c. The user can OK all, change a model/effort, or remove a role. Record the approved map in
      `.pmos/team-model.json`. Use exactly those models and efforts when spawning workers via the
      `swarm` tool. Adjust roster on request.
   d. COST GUARDRAIL: ask the user for a project spend cap in USD (default
      `TPL/config.json` `cost.max_project_cost_usd`); write it as `budget_usd` in
      `.pmos/team-model.json`. Before each wave, estimate spend per worker as
      (model `cost_per_1m`) x (`est_tokens_per_worker` / 1M) and log the running total in
      `.pmos/log.md`. Stop and ask if the estimate exceeds the cap (raise cap, drop a role,
      or downgrade a model).
   e. If recommend.py flags missing benchmark data for a role, either run
      `python TPL/tools/recommend.py refresh` and update `TPL/benchmarks.json` with current
      evidence, or let the user pick manually for that role.
 Also confirm the charter's Deployment jurisdictions with the user (edit
 `.pmos/charter.md` if needed); the legal advisor's jurisdiction pack depends on it.
6. Continue waves 2-4 exactly as ORCHESTRATOR.md prescribes, stopping at GATE 2 before
   implementation, and checkpointing to `.pmos/log.md` after each gate. Commit at each gate.

## Hard rules

- Every spawned worker prompt MUST embed: role skills list, KB search command with the correct
  `--role` namespace, the partial-context rule (no full KB / full repo dumps), and artifact paths.
- Only spawn roles the user approved. One extra worker of an approved role is fine; new roles need approval.
- Never skip the verification gate (wave 4) before declaring a project milestone done.
- Model fallback: if a spawned worker fails (out of tokens, crash, unrecoverable error), retry the
  same task on the next model in that role's ladder (`.pmos/team-model-ladder.json`), up to 2
  fallbacks per task (config.json `context_rules.max_fallbacks_per_task`, default 4), then
  escalate to the user. See ORCHESTRATOR.md "Worker model fallback".
