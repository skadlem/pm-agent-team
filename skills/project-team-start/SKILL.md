---
name: project-team-start
description: "Launch a managed multi-agent project team. Triggers on 'Start the project ...' or 'start project'. Bootstraps .pmos/ state, picks the minimal role roster (PM, architect, designer, backend, frontend, business, marketing, QA, devops) with user approval, runs wave-based execution with hybrid-KB + graphify context rules. Loads the PMOS orchestrator protocol."
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
- This is a RESUME, not a fresh start. Read `.pmos/log.md` (tail), `.pmos/charter.md`, and run
  `python TPL/tools/kb.py budget --db .pmos/kb.sqlite3 --config TPL/config.json`.
- Ask the user what they want to continue with, then continue the wave protocol from the log.

Otherwise proceed with a fresh launch per ORCHESTRATOR.md:

## Step 3: fresh launch

1. Create `.pmos/` skeleton (plans, decisions, kb-sources, log, out) and init the KB:
   `python TPL/tools/kb.py init --db .pmos/kb.sqlite3`.
2. If the user has NOT already run /pm-kb-bootstrap for this project, run the /pm-kb-bootstrap
   skill now (it fills the per-role fundamentals into the KB with the token cap enforced).
3. If the repo has code, build/update the graphify index (load the /graphify skill; use `--update`
   if `graphify-out/` already exists). Greenfield empty repo: skip and note it.
4. Wave 1: spawn the PM worker using the spawn prompt template in ORCHESTRATOR.md, passing the
   user's project description. Wait for charter + plan + roster proposal.
5. GATE 1 (STOP and ask the user): present the proposed roster and scope summary, AND the model
   selection table. For each proposed role show: role, suggested model + effort, and alternatives
   (from `TPL/roster.json` -> `model_suggestions`). The user can OK all, change a model/effort, or
   remove a role. Record the approved map in `.pmos/team-model.json`. Use exactly those models and
   efforts when spawning workers via the `swarm` tool. Adjust roster on request.
6. Continue waves 2-4 exactly as ORCHESTRATOR.md prescribes, stopping at GATE 2 before
   implementation, and checkpointing to `.pmos/log.md` after each gate. Commit at each gate.

## Hard rules

- Every spawned worker prompt MUST embed: role skills list, KB search command with the correct
  `--role` namespace, the partial-context rule (no full KB / full repo dumps), and artifact paths.
- Only spawn roles the user approved. One extra worker of an approved role is fine; new roles need approval.
- Never skip the verification gate (wave 4) before declaring a project milestone done.
