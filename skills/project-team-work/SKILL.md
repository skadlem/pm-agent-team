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
- RESUME: read `.pmos/log.md` (tail) and `.pmos/charter.md`, run
  `python TPL/tools/kb.py budget --db .pmos/kb.sqlite3 --config TPL/config.json`,
  ask the user what to continue, proceed from the log.

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
8. Wave 0 (discovery): spawn ONE architect-labeled worker per ORCHESTRATOR.md to produce
   `.pmos/out/architect/current-state.md` via graphify queries only.
9. Wave 1: spawn the PM worker with `TPL/templates/charter-brownfield.md` + the user's change
   description + current-state.md. Wait for charter, plan, roster proposal (justified by impact surface).
10. GATE 1: present roster + live model selection (compute via `swarm list_models` ->
    `.pmos/available-models.txt` -> `python TPL/tools/recommend.py --available ... `); user
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
