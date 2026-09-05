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
4. Optional: a mock backend (Stage M of the roadmap) lets the eval harness run the
   protocol against the new host without spending tokens.

### Script-based hosts (no one-shot CLI)

A host whose spawn is a program rather than a CLI command (OpenHands SDK: an
LLM -> Agent -> Conversation Python program) declares its spawn command with two
extra placeholders and an `env` block:

```json
"spawn": {"command": "OH_PROMPT_FILE=<prompt-file> OH_MODEL=<model> OH_WORKSPACE=$PWD OH_API_KEY=$OH_API_KEY <python> <runner>"},
"env": {"python": "~/.venvs/openhands/bin/python", "runner": "<tpl>/tools/openhands_run.py"}
```

- `<prompt-file>` — host.py writes the prompt to a temp file and substitutes its
  path (SDK prompts are long and arbitrary; argv is not a channel for them).
- `<name>` placeholders resolve from `env`, expanding `<tpl>` to the template
  root and `~` to home, shell-quoted.
- `$PWD` means the project the worker acts on (`--project`, else cwd).
- The runner must print ONE JSON object shaped like claude's
  `--output-format json` result (`usage.input_tokens/output_tokens`), so the
  usage primitive parses every host identically.

## The three primitives in practice

spawn-with-model: the coordinator passes label + model + effort + prompt. jcode: `swarm`
tool. Claude Code: `claude -p --model <m> --permission-mode acceptEdits ...`. Hermes:
`tools/hermes_run.py` -> `hermes -z --model <m>` headless (delegate_task only as the
in-process fallback — no per-spawn model, no usage block). All of these go through
`tools/host.py`:

```
python tools/host.py list-models --host claude --out .pmos/available-models.txt
# (claude has no CLI list-models in 2.1.x: write .pmos/available-models.txt by hand)
python tools/host.py spawn --host claude --model <m> --label backend-1 --prompt "$(cat prompt.md)" --out .pmos/host-run.json
# add --role backend [--ladder N] and the run lands in .pmos/costs.jsonl and .pmos/waves.jsonl
# automatically, parsed from --out; no follow-up command to forget
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
`recommend.py --available`. jcode: `swarm list_models`. Claude Code: no CLI command in 2.1.x —
the adapter's `default_models` seed the file (hosts/claude.json), the user corrects it to what
the account serves. Hermes: `tools/hermes_run.py list-models` reads the model-catalog caches
(`hermes model --refresh` refetches).

usage: every spawn result must yield tokens_in/tokens_out for `cost.py record`. jcode: in the
spawn result. Claude Code: `--output-format json` usage block. Hermes: the `-z --usage-file`
report, reshaped by the runner.
The mock backend reports usage derived from the prompt length.

## Host limitations are feature flags, not forks

A host that cannot do something (no subagents, no gstack, no browser, no file-scope hooks)
declares it in `suppressed` / `file_scope_hooks` — the protocol degrades to what the host can
do, exactly like gstack's "suppressed resolvers". The gates, budget, and harness never change
shape; only the tool names in the instructions do.

`file_scope_hooks.available: true` means the host can DENY edits outside a worker's `touches`
set at edit time (Claude Code PreToolUse hooks — the gstack /freeze mechanism) AND run a
command when a worker's turn ends (Claude Code Stop hooks). For such hosts the generator ships
two templates the coordinator installs per worker:

- `host-bundles/<host>/hooks-pretool-edit.json` — denies Edit/Write outside the task's touches
  paths, turning do-not-touch from a checkpoint detection into a prevention (gstack G6).
- `host-bundles/<host>/hooks-stop-verify.json` — runs `artifacts.py --strict` before the
  worker's "done" report lands, so a worker cannot report done with unresolved artifact errors
  (L-12, the gstack-verify-gate pattern). A worker whose turn cannot end until the linter
  passes is a worker that never hands off broken references.

Hosts without hooks (jcode, Hermes today) rely on `trace.py unplanned` at the checkpoint and
the coordinator's `artifacts.py` check instead.
