# Running PMOS on Hermes Agent

1. Install the skills: copy `skills/*` from the template root to `~/.hermes/skills/`, and
   write the template root path to `~/.hermes/pmos-template-root`.
2. Enumerate models: `python TPL/tools/host.py list-models --host hermes --out .pmos/available-models.txt`
   reads Hermes' model-catalog caches (the picker's source of truth). Run `hermes model --refresh`
   first if the list looks stale. Then `python TPL/tools/recommend.py --available
   .pmos/available-models.txt` for the roster table.
3. Spawn workers through the shim so the ledgers fill themselves:
   `python TPL/tools/host.py spawn --host hermes --model <m> --label <label> --role <role>
   --effort <e> [--ladder N] --project . --out .pmos/host-run.json --prompt "$(cat prompt.md)"`,
   with the spawn prompt from `host-bundles/hermes/spawn-prompt.md`. The shim runs
   `tools/hermes_run.py` -> `hermes -z` headless with the per-spawn model pinned
   (`--ignore-user-config` so a worker can't rewrite this Hermes install; `.env` auth still loads),
   and `--role` parses the usage report into `.pmos/costs.jsonl` + `.pmos/waves.jsonl`.
   If Hermes' provider auto-detection mis-routes an id on your account, set the
   `provider` key in `hosts/hermes.json` "env" to the right Hermes provider name.
4. In-process fallback: `delegate_task` has NO per-spawn model (children inherit the
   coordinator's) and returns no usage block — use it only when spawning `hermes -z` is
   impossible, and hand-record each run via `cost.py record --source estimated ... --event`.
5. Team defaults: `~/.hermes/pmos-team-defaults.json` (same shape as the reference host's).

All protocol docs in this bundle already name Hermes tools — the coordinator reads
`host-bundles/hermes/ORCHESTRATOR.md` and `host-bundles/hermes/docs/stages/*.md`.
