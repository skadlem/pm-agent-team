# Resume in a future session

Read ORCHESTRATOR.md (core rules) first. This file is the ONLY thing to read when a project
directory already has `.pmos/` — state.py tells you which stage file to continue with.

When a project directory already has `.pmos/`, do NOT guess where it left off from memory. Run
the state detector first; it answers three questions deterministically from artifacts on disk:

1. **DETECT**: `python TPL/tools/state.py --project . --config TPL/config.json` prints the current
   stage (0..9, e.g. "GATE 1 passed", "implementation started"), the next ORCHESTRATOR step, and a
   pre-flight check list covering everything ALREADY completed up to that stage: artifacts present
   and non-empty, team-model.json / team-model-ladder.json valid, `kb.py budget` runs on the
   project DB, log.md records each passed gate, jurisdiction `as_of` dates not stale (>= 180 days
   warns), and the wave-event trace (`.pmos/waves.jsonl`) health. Use `--json` when scripting.
   Stage detection is artifact-based, so it is robust even if log.md is missing lines.
2. **VERIFY**: read the check list. All OK -> continue (below). Any WARN -> note it, continue. Any
   FAIL -> FIX the broken artifact, do not redo the stage: regenerate the failing file from the
   log / upstream artifacts (re-derive team-model.json from the GATE 1 log entry, re-run the role
   that owns the missing artifact, restore from git), then re-run state.py until clean.
   A `stage marker skipped` WARN is NOT a rollback: the stage came from later evidence and the
   named marker was simply never written (a host that cannot pin a model per spawn never writes
   team-model.json; a wave whose log line was missed). Resume from the reported stage and produce
   the missing marker only if a later step needs it. Never re-run completed waves because a
   marker file is absent.
3. **CONTINUE**: report "project is at stage N (<name>); next: <step>" to the user and confirm it
   matches what they want (they may want to re-open a completed stage instead). Then resume the
   launch protocol from that step: `state.py` prints `read next:` with the stage file to load.
   GATE 1 / GATE 2 still stop for user approval.

On resume also check the compliance calendar for overdue items (elapsed time vs due dates) and
each jurisdiction file's `as_of` date: re-research if older than 6 months (state.py warns at
180 days) or if the charter's jurisdictions changed. The KB and graphify index persist across
sessions; nothing is rebuilt from scratch.
