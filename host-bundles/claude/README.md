# Running PMOS on Claude Code

1. Install the skills: copy `skills/*` from the template root to `~/.claude/skills/`, and
   write the template root path to `~/.claude/pmos-template-root`.
2. Enumerate models: `claude models list` > `.pmos/available-models.txt`, then
   `python TPL/tools/recommend.py --available .pmos/available-models.txt` for the roster.
3. Spawn workers: `claude -p --model <m> --permission-mode acceptEdits \
   --allowedTools 'Bash,Read,Write,Edit,Grep,Glob'` with the spawn prompt from
   `host-bundles/claude/spawn-prompt.md`.
4. Read usage: run with `--output-format json` and read `usage.input_tokens` /
   `usage.output_tokens` for `cost.py record`.
5. Team defaults: `~/.claude/pmos-team-defaults.json` (same shape as the reference host's).

All protocol docs in this bundle already name Claude Code tools — the coordinator reads
`host-bundles/claude/ORCHESTRATOR.md` and `host-bundles/claude/docs/stages/*.md`.
