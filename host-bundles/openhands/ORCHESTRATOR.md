# PMOS Orchestrator Protocol

This file is the operating manual for the MAIN session (coordinator). Workers never see it
directly; their spawn prompts embed the parts that concern them.

**Read this core file in full, then ONLY the stage file `state.py` names** (or the one the
stage map below points to). The wave-by-wave instructions live in `TPL/docs/stages/*.md` so a
session resuming mid-project loads ~30% of the protocol instead of all of it.

Layout: `TPL` = this template folder (find it via the host's template-root file —
`hosts/<host>.json` names it per host — else the skill's
grandparent dir). `PROJ` = the project repo root. Project state lives in `PROJ/.pmos/`.

```
.pmos/
  charter.md          # PM owns; source of truth for scope
  plans/plan.md       # PM owns; phases, task graph, acceptance criteria
  decisions/          # architect ADRs
  kb.sqlite3          # hybrid KB store (never dump it; only search)
  kb-sources/         # markdown files that were indexed (audit trail)
  out/<role>/         # each worker's artifacts
  costs.jsonl         # spend ledger (one row per worker run, cost.py)
  waves.jsonl         # wave-event trace (one row per run, events.py)
  log.md              # append-only checkpoint log
```

## Rules (all agents, no exceptions)

1. Partial context only. NEVER read or dump the full KB, the full repo, or large files top-to-bottom.
2. Information retrieval order, stop as soon as you have enough:
   a. Experience: if `~/.pmos-experience/` exists (read-only cross-project notes, L-11),
      search it FIRST with `python TPL/tools/experience.py search "<query>"` — a past
      project's hard-won pitfall outranks anything the fresh KB might guess.
   b. KB: `python TPL/tools/kb.py search --db PROJ/.pmos/kb.sqlite3 "query" --role <ns> -k 5`
   c. Repo questions: use the /graphify skill's query tools (never re-read the whole codebase).
      After material changes to the repo, the coordinator refreshes with `/graphify <path> --update`.
      Code-touching workers (architect, backend, frontend, devops, qa) MUST run at least one
      graphify query before editing anything and record each query in their notes
      (.pmos/out/<role>/notes.md). The coordinator checks this at every checkpoint.
   d. Targeted file read (read tool) ONLY for a specific file you already know you need.
3. Artifacts are small files (markdown) under `.pmos/out/<role>/`. Keep each under ~300 lines.
3b. Anything another role must point at carries a STABLE ID: charter requirements `R-NNN`, plan
   tasks `T-NNN` and acceptance criteria `A-NNN`, decisions `ADR-NNN`, risks `L-NNN`. References
   between them use the fields in ARTIFACT-SCHEMA.md (`satisfies`, `depends_on`, `decided_by`,
   `verifies`, `mitigated_by`, `supersedes`). Ids are never renumbered or reused. Prose stays
   prose; only the things other waves depend on need an id. Verify any time with
   `python TPL/tools/artifacts.py --project .` - it is free, deterministic, and needs no model.
4. Before claiming done, apply the verification-before-completion skill: evidence, not assertions.
5. Disagreements between roles are escalated to the coordinator, who asks the user if stakes are high.
6. Model fallback (`docs/stages/spawn-fallback.md`): a failed worker (out of tokens, crash,
   unrecoverable error) is retried on the NEXT model in that role's fallback ladder, never abandoned
   because of the model. Log every retry.

## Stage map (where the steps live)

| stage file | covers |
|------------|--------|
| `docs/stages/launch.md` | step 1-2: bootstrap, mode detection, dirty-tree question, pre-GATE-1 model rule, Wave 0 (brownfield discovery) |
| `docs/stages/gate1.md` | step 3-4: Wave 1 (PM), GATE 1 (roster + model table + budget guardrail) |
| `docs/stages/wave2.md` | step 5-8: jurisdiction pack, Wave 2 (design), KB enrich, GATE 2 verdict |
| `docs/stages/wave3.md` | step 9-10: Wave 3 (implementation), Wave 4 (QA gate) |
| `docs/stages/checkpoint.md` | step 11: checkpoint routine (log, cost report, events report, lint, unplanned) |
| `docs/stages/spawn-fallback.md` | the worker spawn prompt template + model fallback ladder (every wave) |
| `docs/stages/resume.md` | resuming an existing `.pmos/` project (state.py first, then the named stage file) |

Fresh launch: read `launch.md`, then follow each file's "Next:" pointer. Resume: read
`resume.md`; `state.py` prints which stage file to continue with. GATE 1 / GATE 2 always stop
for user approval.
