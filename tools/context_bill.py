#!/usr/bin/env python3
"""PMOS context bill: what loading the protocol costs in tokens.

The protocol is split (ORCHESTRATOR.md core + docs/stages/*.md) so a session
resuming mid-project loads a stage file instead of the whole manual — the
gstack-context-bill pattern (docs/research/2026-08-24-gstack.md), stdlib-only.
This tool prices that split so a future edit that bloats the always-on load
fails CI instead of silently taxing every session:

    python tools/context_bill.py                # human report
    python tools/context_bill.py --json         # machine-readable
    python tools/context_bill.py --budget 3000  # exit 2 when the session
                                                # baseline exceeds the ceiling

Tokens are estimated the same way the KB caps them (kb.py tokens_of):
len(text)//4, minimum 1. The baseline a session pays is the always-on core
plus the LARGEST stage file (worst case); the spawn template is added on top
whenever workers are spawned.

Exit codes: 0 = within budget (or no --budget), 2 = over budget.
"""
import argparse
import json
import re
import sys
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent


def tokens_of(text):
    return max(1, len(text) // 4)


def spawn_template_tokens():
    """The fenced worker prompt template inside docs/stages/spawn-fallback.md —
    embedded in every spawn prompt, so it is part of what a session pays."""
    p = TPL / "docs" / "stages" / "spawn-fallback.md"
    text = p.read_text(encoding="utf-8")
    blocks = re.findall(r"```\n(.*?)```", text, re.S)
    return tokens_of(blocks[0]) if blocks else 0


def main():
    ap = argparse.ArgumentParser(description="Token bill-of-materials for the PMOS protocol")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--budget", type=int, default=None,
                    help="ceiling in tokens for the session baseline; exit 2 when exceeded")
    args = ap.parse_args()

    core = TPL / "ORCHESTRATOR.md"
    core_tok = tokens_of(core.read_text(encoding="utf-8"))
    stages = []
    for p in sorted((TPL / "docs" / "stages").glob("*.md")):
        stages.append({"file": "docs/stages/%s" % p.name,
                       "tokens": tokens_of(p.read_text(encoding="utf-8"))})
    stages.sort(key=lambda s: -s["tokens"])
    spawn_tok = spawn_template_tokens()
    total_stages = sum(s["tokens"] for s in stages)
    largest = stages[0] if stages else {"file": "-", "tokens": 0}
    baseline = core_tok + largest["tokens"]

    out = {
        "always_on": {"file": "ORCHESTRATOR.md", "tokens": core_tok},
        "stage_files": stages,
        "stage_files_total": total_stages,
        "worst_case_stage": largest,
        "session_baseline_tokens": baseline,
        "spawn_template_tokens": spawn_tok,
        "with_spawn_tokens": baseline + spawn_tok,
    }

    if args.json:
        out["budget"] = args.budget
        out["over_budget"] = bool(args.budget is not None and baseline > args.budget)
        print(json.dumps(out, indent=1))
    else:
        print("PMOS context bill (tokens ~= chars/4, same estimate as the KB caps)")
        print("%-32s %8s" % ("always on (every session)", core_tok))
        print("%-32s %8s" % ("  ORCHESTRATOR.md (core)", core_tok))
        print("%-32s %8s" % ("stage files (one per session):", total_stages))
        for s in stages:
            print("  %-30s %8s" % (s["file"], s["tokens"]))
        print("%-32s %8s" % ("session baseline (core + worst stage)", baseline))
        print("%-32s %8s" % ("worker spawn template (per spawn)", spawn_tok))
        print("%-32s %8s" % ("baseline + one spawn", baseline + spawn_tok))
        if args.budget is not None:
            if baseline > args.budget:
                print("OVER BUDGET: baseline %d > %d" % (baseline, args.budget))
            else:
                print("within budget: baseline %d <= %d" % (baseline, args.budget))
    return 2 if (args.budget is not None and baseline > args.budget) else 0


if __name__ == "__main__":
    sys.exit(main())
