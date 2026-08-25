#!/usr/bin/env python3
"""PMOS host shim: the three host primitives behind one CLI (HOST-ADAPTER.md).

The protocol only touches a host through three primitives (spawn-with-model,
list_models, usage) plus two paths. This tool resolves them for any host
declared in hosts/*.json:

    python tools/host.py list-models --host mock --out .pmos/available-models.txt
    python tools/host.py spawn --host mock --model claude-opus-5 --label backend-1 \
        --effort medium --prompt "$(cat prompt.md)" --out .pmos/host-run.json
    python tools/host.py usage --host mock --result .pmos/host-run.json

Backends:
- mock   deterministic, zero tokens: list-models returns a fixture set,
         spawn returns ok/failed with usage derived from prompt length, and
         every run is appended to .pmos/host-runs.jsonl. This is what the
         eval harness uses (Stage M) so the adapter contract is testable
         without spending money.
- jcode / claude / hermes   resolve the primitive to the host's documented
         command (hosts/<name>.json). --dry-run prints the exact command;
         without it, the tool checks the CLI exists and executes list-models.

Exit codes: 0 ok, 1 host/CLI error, 2 usage error.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent

MOCK_MODELS = ["claude-opus-5", "claude-sonnet-5", "deepseek-v4-flash-0731",
               "qwen3.8-max", "glm-5.2", "kimi-k2.7-code"]


def load_host(name):
    p = TPL / "hosts" / ("%s.json" % name)
    if not p.is_file():
        print("unknown host %r; hosts: %s" % (name, ", ".join(
            sorted(q.stem for q in (TPL / "hosts").glob("*.json")))), file=sys.stderr)
        sys.exit(2)
    return json.loads(p.read_text(encoding="utf-8"))


def mock_list_models():
    return MOCK_MODELS


def mock_spawn(model, label, effort, prompt, out_file, project):
    tokens_in = max(1, len(prompt) // 4) * 2
    tokens_out = max(1, len(prompt) // 4 // 3)
    result = {"label": label, "model": model, "effort": effort,
              "tokens_in": tokens_in, "tokens_out": tokens_out,
              "status": "failed" if model.startswith("mock-fail") else "ok",
              "host": "mock", "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())}
    if project:
        runs = Path(project) / ".pmos" / "host-runs.jsonl"
        runs.parent.mkdir(parents=True, exist_ok=True)
        with runs.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
    if out_file:
        Path(out_file).parent.mkdir(parents=True, exist_ok=True)
        Path(out_file).write_text(json.dumps(result), encoding="utf-8")
    else:
        print(json.dumps(result))
    return result


def real_command(cfg, verb, args):
    """Resolve a primitive to the host's documented command string."""
    if verb == "list-models":
        return cfg.get("list_models", ""), {}
    if verb == "spawn":
        cmd = cfg.get("spawn", {}).get("command", "")
        # <tpl> and env-block placeholders resolve from the adapter config:
        # hosts/*.json "env": {"python": "...", "runner": "<tpl>/tools/..."}
        env_cfg = {k: str(v).replace("<tpl>", str(TPL))
                   for k, v in (cfg.get("env") or {}).items()}
        for k, v in env_cfg.items():
            cmd = cmd.replace("<%s>" % k, shlex.quote(os.path.expanduser(v)))
        cmd = cmd.replace("<model>", args.model).replace("<effort>", args.effort or "")
        # shell-quote the prompt: it is arbitrary protocol text, not shell source
        cmd = cmd.replace("<prompt>", shlex.quote(args.prompt or ""))
        # script-based hosts (openhands): <prompt-file> -> a temp file holding the
        # prompt, so the runner reads it from OH_PROMPT_FILE instead of an argv
        # (SDK prompts can be long and contain anything)
        if "<prompt-file>" in cmd:
            import tempfile
            fd, pfile = tempfile.mkstemp(suffix=".md", prefix="pmos-prompt-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(args.prompt or "")
            cmd = cmd.replace("<prompt-file>", shlex.quote(pfile))
        return cmd, {}
    if verb == "usage":
        flag = (cfg.get("usage") or {}).get("flag", "")
        return flag, {}
    return "", {}


def cmd_list_models(args):
    if args.host == "mock":
        models = mock_list_models()
        text = "\n".join("- %s" % m for m in models) + "\n"
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    cfg = load_host(args.host)
    cmd, _ = real_command(cfg, "list-models", args)
    if not cmd:
        note = cfg.get("list_models_note") or "the host declares no list_models command"
        print("host %s has no CLI list-models command: %s" % (args.host, note), file=sys.stderr)
        print("write the model list to --out yourself, then re-run without list-models",
              file=sys.stderr)
        return 2
    if args.dry_run:
        print(cmd)
        return 0
    exe = shutil.which(cmd.split()[0])
    if not exe:
        print("host CLI %r not installed; rerun with --dry-run" % cmd.split()[0], file=sys.stderr)
        return 1
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if args.out and r.stdout:
        Path(args.out).write_text(r.stdout, encoding="utf-8")
    else:
        sys.stdout.write(r.stdout)
    return r.returncode


def cmd_spawn(args):
    if args.host == "mock":
        mock_spawn(args.model, args.label, args.effort, args.prompt,
                   args.out, args.project)
        return 0
    cfg = load_host(args.host)
    cmd, _ = real_command(cfg, "spawn", args)
    if not cmd:
        print("host %s declares no spawn command" % args.host, file=sys.stderr)
        return 2
    # $PWD in a spawn command means the PROJECT the worker acts on (the
    # coordinator runs from the project root; --project overrides when given)
    workdir = os.path.abspath(args.project) if args.project else os.getcwd()
    cmd = cmd.replace("$PWD", shlex.quote(workdir))
    if args.dry_run:
        print(cmd)
        return 0
    # env-prefixed commands (VAR=x ... cmd): find the real executable past the
    # VAR=value assignments
    first = next((p for p in cmd.split()
                  if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", p)), "")
    exe = shutil.which(first)
    if not exe:
        print("host CLI %r not installed; rerun with --dry-run" % first, file=sys.stderr)
        return 1
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(r.stdout or "", encoding="utf-8")
    else:
        sys.stdout.write(r.stdout)
    return r.returncode


def cmd_usage(args):
    if args.host == "mock":
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        print(json.dumps({"tokens_in": result.get("tokens_in", 0),
                          "tokens_out": result.get("tokens_out", 0),
                          "status": result.get("status", "ok")}))
        return 0
    # real hosts: try to parse the result file's usage block (claude -p
    # --output-format json and the openhands runner both emit
    # .usage.input_tokens / .usage.output_tokens; the openhands file may carry
    # SDK log noise before the JSON, so scan for the result object)
    p = Path(args.result)
    if p.is_file():
        raw = p.read_text(encoding="utf-8")
        candidates = [raw]
        j = raw.find('{"type": "result"')
        if j >= 0:
            candidates.insert(0, raw[j:])
        for text in candidates:
            try:
                result = json.loads(text)
            except ValueError:
                continue
            u = result.get("usage") or {}
            if u.get("input_tokens") is not None:
                print(json.dumps({"tokens_in": u["input_tokens"],
                                  "tokens_out": u.get("output_tokens", 0),
                                  "status": "ok" if not result.get("is_error") else "failed"}))
                return 0
    cfg = load_host(args.host)
    flag, _ = real_command(cfg, "usage", args)
    print("# usage: %s" % ((cfg.get("usage") or {}).get("doc", "") or flag or "see host docs"))
    return 0


def main():
    ap = argparse.ArgumentParser(description="PMOS host shim (HOST-ADAPTER.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list-models")
    p.add_argument("--host", default="jcode")
    p.add_argument("--out", default=None)
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("spawn")
    p.add_argument("--host", default="jcode")
    p.add_argument("--model", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--effort", default=None)
    p.add_argument("--prompt", default="")
    p.add_argument("--out", default=None)
    p.add_argument("--project", default=None)
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("usage")
    p.add_argument("--host", default="jcode")
    p.add_argument("--result", required=True)

    args = ap.parse_args()
    if args.cmd == "list-models":
        return cmd_list_models(args)
    if args.cmd == "spawn":
        return cmd_spawn(args)
    if args.cmd == "usage":
        return cmd_usage(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
