#!/usr/bin/env python3
"""PMOS runner for the Hermes Agent backend (headless one-shot).

Hermes has no one-shot spawn in the agent sense (`hermes -z` does: prompt in,
final response out, `--usage-file` writes a JSON usage report), but its result
shape differs from what host.py's usage primitive parses. This runner bridges
the two: host.py's spawn command invokes it via env vars (same shape as the
openhands backend), it runs `hermes -z` with the per-spawn model/effort pinned,
and prints ONE claude-shaped JSON object so every host parses identically.

    PMOS_PROMPT_FILE=<file> PMOS_MODEL=<id> [PMOS_EFFORT=low] [PMOS_WORKSPACE=$PWD] <python> <runner>
    <python> <runner> list-models

list-models writes the "- <id>" bullet list recommend.py expects, from Hermes'
own model-catalog cache (the picker's source of truth; `hermes model --refresh`
refetches it). Zero deps, stdlib only.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# reasoning levels hermes accepts (auxiliary_client validation list); effort
# values PMOS roles use are a subset, anything else is dropped with a note.
_VALID_EFFORT = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def cmd_list_models() -> int:
    """Emit '- <model id>' bullets from Hermes' model-catalog caches."""
    home = _hermes_home()
    ids = []
    seen = set()
    for cache in (home / "cache" / "openrouter_curated.json",
                  home / "cache" / "model_catalog.json"):
        if not cache.is_file():
            continue
        try:
            doc = json.loads(cache.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        providers = doc.get("providers") or {}
        if not isinstance(providers, dict):
            continue
        for pconf in providers.values():
            for m in (pconf or {}).get("models") or []:
                mid = str((m or {}).get("id") or "").strip()
                if mid and mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
    if not ids:
        sys.stderr.write(
            "no model catalog cache under %s/cache; open the model picker once or "
            "run `hermes model --refresh`, then re-run list-models\n" % home)
        return 1
    sys.stdout.write("".join("- %s\n" % m for m in ids))
    return 0


def cmd_spawn() -> int:
    hermes = shutil.which("hermes")
    if not hermes:
        sys.stderr.write("hermes CLI not on PATH; install Hermes Agent or run with --dry-run\n")
        return 3
    pfile = os.environ.get("PMOS_PROMPT_FILE", "").strip()
    if not pfile or not Path(pfile).is_file():
        sys.stderr.write("PMOS_PROMPT_FILE must name a readable file (host.py writes it)\n")
        return 3
    prompt = Path(pfile).read_text(encoding="utf-8")
    model = os.environ.get("PMOS_MODEL", "").strip()
    effort = os.environ.get("PMOS_EFFORT", "").strip().lower()
    workspace = os.environ.get("PMOS_WORKSPACE", "").strip() or os.getcwd()

    argv = [hermes, "-z", prompt]
    # --ignore-user-config so a worker from an EXTERNAL session can't rewrite this
    # box's global Hermes config (oneshot forces YOLO anyway; .env auth still
    # loads). Auto-detecting the provider from the model id mis-routes when the
    # same id exists on several configured providers, so PMOS_PROVIDER (caller's
    # env, or the hosts/hermes.json "env" provider as fallback) passes an explicit
    # --provider; empty leaves the decision to Hermes.
    argv.append("--ignore-user-config")
    provider = os.environ.get("PMOS_PROVIDER", "").strip()
    if model:
        argv += ["--model", model]
        if provider:
            argv += ["--provider", provider]
    effort_note = None
    if effort and effort in _VALID_EFFORT:
        argv += ["--reasoning", effort]
    elif effort:
        effort_note = "effort %r is not a hermes --reasoning level; run on model default" % effort

    fd, usage_file = tempfile.mkstemp(suffix=".json", prefix="pmos-hermes-usage-")
    os.close(fd)  # hermes writes it; close our handle (Windows leaves no lock)
    argv += ["--usage-file", usage_file]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, cwd=workspace)
    finally:
        usage = {}
        try:
            usage = json.loads(Path(usage_file).read_text(encoding="utf-8"))
            Path(usage_file).unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    text = (r.stdout or "").strip()
    failed = bool(usage.get("failed")) or r.returncode != 0 or not text
    out = {
        "type": "result",
        "subtype": "error" if failed else "success",
        "is_error": failed,
        "duration_ms": usage.get("duration_ms") or 0,
        "result": text or (usage.get("failure") or (r.stderr or "").strip()[:500]),
        "model": usage.get("model") or model or None,
        "provider": usage.get("provider") or None,
        "session_id": usage.get("session_id") or None,
        "num_turns": usage.get("api_calls") or 0,
        "usage": {
            "input_tokens": usage.get("input_tokens") or 0,
            "output_tokens": usage.get("output_tokens") or 0,
            "cache_read_input_tokens": usage.get("cache_read_tokens") or 0,
        },
        "total_cost_usd": usage.get("estimated_cost_usd"),
    }
    if effort_note:
        out["pmos_note"] = effort_note
    print(json.dumps(out, ensure_ascii=False))
    return 0  # the RESULT file records failure; the runner itself succeeded


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "list-models":
        return cmd_list_models()
    return cmd_spawn()


if __name__ == "__main__":
    sys.exit(main())
