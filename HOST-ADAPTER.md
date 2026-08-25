# Host Adapter Contract

PMOS is host-agnostic by design: roster, waves, gates, KB, KG, cost ledger, event trace,
artifact ids, and the protocol harness all run anywhere. The jcode-specific surface is tiny,
and this file is the contract that lets a new host run PMOS with a declarative config and no
code changes (the gstack defineHost() pattern, docs/research/2026-08-24-gstack.md).

## The jcode surface (everything else is host-agnostic)

| primitive | jcode | what a host must provide |
|---|---|---|
| locate template | `~/.jcode/pmos-template-root` | a file that names the template root |
| spawn a worker with an explicit model | `swarm` tool (`model`, `effort`) | spawn-with-model: label, model, effort, prompt |
| enumerate models | `swarm list_models` | a text list of available model ids |
| read usage | tokens_in/out in the swarm result | per-run token counts for the cost ledger |
| saved team defaults | `~/.jcode/pmos-team-defaults.json` | a user-approved role->model table file |
| skills location | `~/.jcode/skills` | where the protocol skills install |

Everything else (`tools/*.py`, `docs/stages/*.md`, `ORCHESTRATOR.md`, `roster.json`,
`config.json`, `templates/*`) is already host-neutral.

## The adapter: hosts/<host>.json

One JSON file per host, modeled on gstack's `defineHost()` config (paths, spawn command,
model/effort flags, tool-name rewrites, suppressed features):

```json
{
  "name": "claude",
  "display_name": "Claude Code",
  "template_root_file": "~/.claude/pmos-template-root",
  "skills_dir": "~/.claude/skills",
  "agents_dir": ".claude/agents",
  "defaults_file": "~/.claude/pmos-team-defaults.json",
  "spawn": {"doc": "...", "command": "...", "model_flag": "--model <model>", "effort_flag": "..."},
  "list_models": "claude models list",
  "usage": {"doc": "...", "flag": "--output-format json"},
  "tool_rewrites": [{"from": "`swarm` tool", "to": "`claude -p` headless session"}, ...],
  "suppressed": ["gstack"]
}
```

- `tool_rewrites` maps every jcode-ism in the protocol docs to the host's equivalent. The
  generator applies them to the worker spawn prompt and the protocol docs when rendering a
  host bundle; `hostgen.py --check` fails when a rewrite source never appears (dead entry) or
  a jcode-ism survives (missed entry).
- `suppressed` lists features the host cannot run (e.g. `gstack` when the host has no gstack
  install); the generator drops the corresponding methodology-upgrade instructions from the
  spawn prompt rather than sending workers to a nonexistent tool.

## Rendering a host bundle

```
python tools/hostgen.py --host claude          # render host-bundles/claude/
python tools/hostgen.py --check                # CI: every host renders clean
```

`hostgen.py` renders per host:

- `host-bundles/<host>/spawn-prompt.md` — the worker spawn prompt template
  (docs/stages/spawn-fallback.md) with tool rewrites applied and suppressed features removed.
- `host-bundles/<host>/agents/<role>.md` — one agent definition per roster role (subagent
  format for hosts that support agents: Claude Code `.claude/agents/`, jcode skills).
- `host-bundles/<host>/README.md` — how to run PMOS on this host: locate the template,
  enumerate models, spawn a worker, read usage, where defaults live.
- `host-bundles/<host>/ORCHESTRATOR.md` + `docs/stages/*.md` — the protocol docs with
  rewrites applied, so the coordinator's instructions name the host's real tools.

The bundled files are GENERATED — edit `hosts/<host>.json` or the source docs, never the
bundle. `hostgen.py --check` verifies bundles are in sync (freshness + rewrite coverage).

## Adding a host

1. Copy `hosts/jcode.json` to `hosts/<name>.json` and fill in the six primitives.
2. Add tool rewrites for every jcode-ism that appears in `docs/stages/*.md`
   (`grep -n 'swarm\|jcode' docs/stages/` is the checklist).
3. Run `python tools/hostgen.py --check` until clean.
4. Optional: a mock backend (Stage M of the roadmap) lets the eval harness run the protocol
   against the new host without spending tokens.

## The three primitives in practice

spawn-with-model: the coordinator passes label + model + effort + prompt. jcode: `swarm`
tool. Claude Code: `claude -p --model <m> --permission-mode acceptEdits ...`. Hermes:
`delegate_task(goal=..., model=<m>, effort=<e>)`. All three go through `tools/host.py`:

```
python tools/host.py list-models --host claude --out .pmos/available-models.txt
python tools/host.py spawn --host claude --model <m> --label backend-1 --prompt "$(cat prompt.md)"
python tools/host.py usage --host claude --result .pmos/host-run.json
```

For real hosts, spawn/list-models require the host CLI (missing CLI -> exit 1 with a hint;
`--dry-run` prints the exact command). The **mock backend** (`--host mock`) is deterministic
and spends no tokens: list-models returns a fixture set, spawn returns ok/failed with usage
derived from the prompt length, and every run is appended to `.pmos/host-runs.jsonl`. The
harness exercises the whole pipeline against the mock (validate.py section 9d: list-models ->
spawn -> usage -> cost record -> events record -> report), so the adapter contract is tested
without ever paying a model.

list_models: the coordinator saves the output to `.pmos/available-models.txt` and feeds it to
`recommend.py --available`. jcode: `swarm list_models`. Claude Code: `claude models list`.

usage: every spawn result must yield tokens_in/tokens_out for `cost.py record`. jcode: in the
spawn result. Claude Code: `--output-format json` usage block. Hermes: the subagent result.
The mock backend reports usage derived from the prompt length.

## Host limitations are feature flags, not forks

A host that cannot do something (no subagents, no gstack, no browser, no file-scope hooks)
declares it in `suppressed` / `file_scope_hooks` — the protocol degrades to what the host can
do, exactly like gstack's "suppressed resolvers". The gates, budget, and harness never change
shape; only the tool names in the instructions do.

`file_scope_hooks.available: true` means the host can DENY edits outside a worker's `touches`
set at edit time (Claude Code PreToolUse hooks — the gstack /freeze mechanism). For such
hosts the generator ships `host-bundles/<host>/hooks-pretool-edit.json`; the coordinator
installs it per worker with the task's touches paths filled in, turning do-not-touch from a
checkpoint detection into a prevention. Hosts without hooks (jcode, Hermes today) rely on
`trace.py unplanned` at the checkpoint instead.
