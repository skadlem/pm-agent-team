# Running PMOS on Hermes Agent

1. Install the skills: copy `skills/*` from the template root to `~/.hermes/skills/`, and
   write the template root path to `~/.hermes/pmos-template-root`.
2. Enumerate models: use the configured providers (`hermes models`), save the id list to
   `.pmos/available-models.txt`, then run the recommender.
3. Spawn workers: `delegate_task(goal=<spawn prompt>, model=<m>, effort=<e>)` with the
   prompt from `host-bundles/hermes/spawn-prompt.md`.
4. Read usage: token counts come from the subagent result's usage block, for `cost.py record`.
5. Team defaults: `~/.hermes/pmos-team-defaults.json` (same shape as the reference host's).

All protocol docs in this bundle already name Hermes tools — the coordinator reads
`host-bundles/hermes/ORCHESTRATOR.md` and `host-bundles/hermes/docs/stages/*.md`.
