# Running PMOS on Claude Code

1. Install the skills: copy `skills/*` from the template root to `~/.claude/skills/`, and
   write the template root path to `~/.claude/pmos-template-root`.
2. Enumerate models: Claude Code has no CLI model-list command, so
   `python TPL/tools/host.py list-models --host claude --out .pmos/available-models.txt`
   writes the adapter's `default_models` (the current Claude family) for you. Show that list
   to the user and correct it to what the account can actually serve — do not block the gate
   on a hand-written file. Then `python TPL/tools/recommend.py --available
   .pmos/available-models.txt --ladder-out .pmos/team-model-ladder.json` for the roster.
3. Spawn workers through the shim so the ledgers fill themselves:
   `python TPL/tools/host.py spawn --host claude --model <m> --label <label> --role <role>
   [--ladder N] --project . --out .pmos/host-run.json --prompt "$(cat prompt.md)"`, with the
   spawn prompt from `host-bundles/claude/spawn-prompt.md`. `--role` parses the usage out of
   `--out` and appends both `.pmos/costs.jsonl` and `.pmos/waves.jsonl` — there is no
   follow-up command to forget.
4. Read usage (only when spawning by hand instead): run `claude -p` with `--output-format
   json`, read `usage.input_tokens` / `usage.output_tokens`, and pass them to
   `cost.py record ... --event`.
5. Team defaults: `~/.claude/pmos-team-defaults.json` (same shape as the reference host's).

All protocol docs in this bundle already name Claude Code tools — the coordinator reads
`host-bundles/claude/ORCHESTRATOR.md` and `host-bundles/claude/docs/stages/*.md`.
