---
name: project-team-work
description: "Launch the PMOS multi-agent team on an EXISTING codebase (brownfield mode, forced). Triggers on 'Work on this project ...', 'work on this project', or 'take over this project'. Maps the existing code with a graphify discovery wave, writes a delta charter with a do-not-touch list, picks the roster by impact surface, then runs the wave protocol with user gates."
---

# /project-team-work

Brownfield-only launcher. The user says something like "Work on this project <description of the
change they want>". Unlike /project-team-start, this skill FORCES brownfield mode even if
auto-detection would be ambiguous.

## Step 0: locate the template

1. Read `~/.jcode/pmos-template-root` to get `TPL` (on Windows:
   `type %USERPROFILE%\.jcode\pmos-template-root`).
2. If missing, tell the user to run `install.cmd` / `install.sh` from the `pm-agent-team` folder and stop.

## Step 1: load the protocol

Read `TPL/ORCHESTRATOR.md` in full, plus `TPL/roster.json` and `TPL/config.json`.

## Step 2: existing state or fresh brownfield launch

If the current working directory already contains `.pmos/`:
- RESUME: run the state detector FIRST (do not guess from memory):
  `python TPL/tools/state.py --project . --config TPL/config.json`.
  It reports the stage (0..9), the next launch step, and pre-flight checks for everything
  completed so far (artifacts non-empty, team-model JSON valid, KB budget runs, gates logged,
  jurisdiction `as_of` fresh).
- All OK: report "project is at stage N (<name>); next: <step>", confirm with the user, proceed
  from that step. WARNs: note, continue. FAILs: fix the broken artifact from log/git, re-run
  state.py until clean; never redo a completed stage. Then ask the user what to continue with.

Otherwise:

1. Announce: "Starting in brownfield mode: I'll map the existing codebase first, then plan the change."
2. Sanity check: if the repo has NO source files at all, warn the user that they probably want
   `/project-team-start` (greenfield) instead, and ask whether to continue anyway.
3. If the git tree is dirty, ask ONCE whether agents may commit their own files (staging only
   agent-written paths) or leave commits to the user. Record the answer in `.pmos/log.md`.
4. Create `.pmos/` skeleton (plans, decisions, kb-sources, log, out) and init the KB:
   `python TPL/tools/kb.py init --db .pmos/kb.sqlite3`.
5. Run the /pm-kb-bootstrap skill (per-role fundamentals, capped).
6. Propose adding `.pmos/kb.sqlite3` to the project `.gitignore`.
7. Build/update the graphify index on the repo (load /graphify; `--update` if `graphify-out/` exists).
   If `graphify-out/graph.json` is MISSING, run `/graphify <path>` NOW and do not proceed until
   the graph exists (Wave 0 and every worker repo query depend on it).
8. Wave 0 (discovery): spawn ONE architect-labeled worker per ORCHESTRATOR.md to produce
   `.pmos/out/architect/current-state.md` via graphify queries only.
9. Wave 1: spawn the PM worker with `TPL/templates/charter-brownfield.md` + the user's change
   description + current-state.md. Wait for charter, plan, roster proposal (justified by impact surface).
   IMPORTANT: Wave 0 and Wave 1 run BEFORE the team model table exists. Spawn them with an
   EXPLICIT temporary model (cheapest AVAILABLE model not in TPL/roster.json `forbidden_models`,
   per ORCHESTRATOR.md "Pre-GATE-1 worker model"), never an unmodeled spawn (that inherits the
   swarm default, e.g. Fable 5). GATE 1 still decides the real team models.
10. GATE 1: present roster + model selection. If `~/.jcode/pmos-team-defaults.json` exists, propose
    that role -> model table as-is (user's saved preference; verify its models still appear in
    `swarm list_models`). Otherwise compute via `swarm list_models` ->
    `.pmos/available-models.txt` -> `python TPL/tools/recommend.py --available ... 
    --ladder-out .pmos/team-model-ladder.json` (the ladder file is the per-role fallback order); user
    approves/edits/removes; approved map goes to `.pmos/team-model.json`.
11. Continue waves 2-4 per ORCHESTRATOR.md, including the brownfield rules (conventions into KB
    via /pm-kb-enrich, QA baseline from the existing test suite). Checkpoint to `.pmos/log.md`
    after each gate and commit per the agreement in step 3.

## Hard rules

- Every spawned worker prompt MUST embed: role skills, KB search command with the right `--role`
  namespace, the partial-context rule, the BROWNFIELD RULE (conform to existing conventions,
  find similar patterns first), and artifact paths.
- Only spawn roles the user approved; the do-not-touch list in the charter is binding.
- Never skip the verification gate before declaring a milestone done.
- Model fallback: if a spawned worker fails (out of tokens, crash, unrecoverable error), retry the
  same task on the next model in that role's ladder (`.pmos/team-model-ladder.json`), up to
  `max_fallbacks_per_task` (config.json `context_rules`, default 4) fallbacks per task, then
  escalate to the user. See ORCHESTRATOR.md "Worker model fallback".
