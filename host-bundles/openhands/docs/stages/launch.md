# Stage: launch (steps 1-2)

Read ORCHESTRATOR.md (core rules) first. This file covers the start of a fresh launch:
bootstrap, discovery (brownfield), and the pre-GATE-1 model rule.

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
   - Brownfield: propose adding `.pmos/kb.sqlite3*` to the project `.gitignore` (binary, regenerable;
     the `-wal`/`-shm` sidecars appear once the KB runs in WAL mode; everything else in .pmos is
     plain markdown and should be committed).

Pre-GATE-1 worker model: Wave 0 (discovery) and Wave 1 (PM) spawn BEFORE the team model table
  exists (GATE 1). NEVER spawn them without an explicit model: an unmodeled spawn inherits the
  the host's default model, which may be a model the user forbids. Instead, run
  the model list once, pick the cheapest AVAILABLE model NOT in roster.json
  `forbidden_models` (the user may name a different temporary model), and pass it explicitly
  at spawn (the host's spawn-with-model primitive). Log the choice in `.pmos/log.md`. This is temporary:
  GATE 1 still decides the real per-role team models.

2. Wave 0 (DISCOVERY, brownfield only): spawn ONE architect-labeled worker with the assignment:
   map the existing system using graphify queries (never full reads). Output
   `.pmos/out/architect/current-state.md` (<300 lines): module map with ownership/responsibilities,
   tech stack + versions, conventions (naming, error handling, test layout), test suite state
   (how to run it, known red tests), top integration points, and the areas relevant to the user's
   stated goal. This artifact drives charter, roster, and enrichment.

Next: `docs/stages/gate1.md` (steps 3-4).
