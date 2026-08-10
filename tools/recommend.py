#!/usr/bin/env python3
"""Suggest a cost-effective model per PMOS role from the LIVE available-model list.

How it works (matches the launch flow):
  1. The coordinator runs `swarm list_models` and saves the output to a text file.
  2. This tool parses that output (or a JSON list), keeping only AVAILABLE models.
  3. For each role it computes a purpose-weighted benchmark score per model from
     benchmarks.json (per-purpose scores x cost per 1M tokens, sourced + dated).
  4. It keeps the BEST TIER (models within --tier of the best score), then picks
     the CHEAPEST of that tier by blended cost (3:1 input:output).
  5. Outputs a table + JSON, flagging models with missing benchmark data so the
     coordinator can refresh the dataset.

Fallback ladder (for the "worker failed -> retry on next best model" rule):
  each role result also carries a `ladder`: every available scored model for that
  role, ordered best-first (score desc, then cost asc). Write it to a file with
  `--ladder-out .pmos/team-model-ladder.json`. The coordinator starts a role on
  `suggested`; if that worker dies (e.g. runs out of tokens), retry the task on
  the next untried model in the ladder.

Refresh: `python tools/recommend.py refresh --benchmarks benchmarks.json`
prints the exact websearch queries to re-check current scores/prices, so a human
or the agent can update the dataset between launches.

Usage:
  python tools/recommend.py --available <list_models.txt|models.json> [--benchmarks benchmarks.json]
                           [--roster roster.json] [--tier 0.92] [--json]
                           [--ladder-out <path>] [--roles <a,b,c>]
  python tools/recommend.py refresh --benchmarks benchmarks.json
"""
import argparse
import json
import pathlib
import re
import sys

# role -> purpose weights (fallback when roster.json has no "purpose"; mirrors roster.json)
DEFAULT_PURPOSE = {
    "pm":        {"reasoning": 0.5, "business": 0.3, "writing": 0.2},
    "architect": {"reasoning": 0.6, "coding": 0.4},
    "designer":  {"design": 1.0},
    "backend":   {"coding": 1.0},
    "frontend":  {"coding": 0.6, "design": 0.4},
    "business":  {"business": 1.0},
    "marketing": {"marketing": 0.7, "writing": 0.3},
    "qa":        {"verification": 1.0},
    "devops":    {"ops": 1.0},
}

# route ids -> benchmark dataset ids (e.g. provider-prefixed or [web] routes)
ALIASES = {
    "anthropic/claude-sonnet-4": "claude-sonnet-4-20250514",
    "gpt-5.6-pro": "gpt-5.6-sol",  # [web]/oauth route for the 5.6 pro class; sol is the closest scored entry
    "deepseek-v4-flash-0731": "deepseek-v4-flash",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "claude-opus-4-5-20251101": "claude-opus-4-5-20251101",
}


def normalize_id(mid: str) -> str:
    """Map a route id to a benchmark-dataset id when they differ."""
    n = mid.strip()
    if "[" in n:
        n = n.split("[")[0].strip()
    if "/" in n:
        n = n.split("/", 1)[1]
    if n in ALIASES:
        return ALIASES[n]
    return n


def parse_available(path):
    """Parse `swarm list_models` text output or a JSON list into [{id, available, provider}]."""
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace").strip()
    if text.startswith("["):
        data = json.loads(text)
        return [{"id": m["id"], "available": m.get("available", True),
                 "provider": m.get("provider")} for m in data]
    models = []
    for line in text.splitlines():
        # - <id> via <provider> [auth-bracket] [unavailable]? (detail)
        m = re.match(r"^\s*[-*]\s+(\S+)\s+via\s+(.+?)\s*(\[[^\]]*\])\s*(?:\(.*\))?$", line)
        if m:
            models.append({"id": m.group(1),
                           "available": "[unavailable]" not in line,
                           "provider": m.group(2).strip()})
            continue
        m2 = re.match(r"^\s*[-*]\s+(\S+)\s+via\s+\S+.*?(\[unavailable\])?\s*(?:\(.*\))?$", line)
        if m2:
            models.append({"id": m2.group(1), "available": not m2.group(2)})
    # fallback: any bare id tokens on "- " lines
    if not models:
        for line in text.splitlines():
            m = re.match(r"^\s*[-*]\s+(\S+)\s*$", line)
            if m:
                models.append({"id": m.group(1), "available": True})
    return models


def load_benchmarks(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("models", data)


def load_roster(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data


def blended_cost(entry):
    cin = entry.get("cost_in")
    cout = entry.get("cost_out")
    if cin is None or cout is None:
        return None
    return (3 * cin + cout) / 4.0


def _fmt_cost(c):
    if c is None:
        return "?"
    if c >= 1:
        return f"{c:.2f}"
    return f"{c:.3f}".rstrip("0").rstrip(".")


def role_purpose(roster, role):
    # roster.json "model_suggestions" -> purpose is authoritative (per README);
    # DEFAULT_PURPOSE below is only the fallback when the roster has no entry.
    if roster:
        p = ((roster.get("model_suggestions") or {}).get(role) or {}).get("purpose")
        if p:
            return p
        p = ((roster.get("roles") or {}).get(role) or {}).get("purpose")
        if p:
            return p
    return DEFAULT_PURPOSE.get(role, {"reasoning": 1.0})


def eligible_models(ids, roster):
    """Apply forbidden_models + newest_only filters to a set of model ids.

    forbidden_models: never suggested or in any ladder. A trailing "*" is a prefix
    match (e.g. "gpt-*" blocks every OpenAI GPT route, but not "openai/gpt-oss-120b"
    which is a different id served by NVIDIA NIM). newest_only keeps only the newest
    generation per model family (e.g. claude-opus-5, never claude-opus-4-7/4-8).
    """
    avail = set(ids)
    forbidden = set()
    for f in (roster or {}).get("forbidden_models") or []:
        if f.endswith("*"):
            forbidden.update(m for m in avail if m.startswith(f[:-1]))
        else:
            forbidden.add(f)
    if forbidden:
        avail = {m for m in avail if m not in forbidden}
    for fam, keep_id in ((roster or {}).get("newest_only") or {}).items():
        if fam == "note" or not keep_id:
            continue
        avail = {m for m in avail if not (m.startswith(fam) and m != keep_id)}
    return avail


def recommend(available, benchmarks, roster, tier, role_filter=None):
    avail = eligible_models({m["id"] for m in available if m.get("available", True)}, roster)
    roles = [r for r in roster["roles"] if role_filter is None or r in role_filter]
    out = []
    for role in roles:
        purpose = role_purpose(roster, role)
        scores = {}
        for mid in avail:
            bmid = normalize_id(mid)
            entry = benchmarks.get(bmid)
            if not entry:
                continue
            s = 0.0
            missing = []
            for p, w in purpose.items():
                v = (entry.get("scores") or {}).get(p)
                if v is None:
                    missing.append(p)
                else:
                    s += w * v
            if missing and s == 0.0:
                continue
            scores[mid] = {"score": s, "missing": missing, "entry": entry}
        if not scores:
            out.append({"role": role, "suggested": None, "suggested_provider": None,
                        "reason": "no benchmark data for any available model",
                        "tier": [], "ladder": [], "providers": {}, "purpose": purpose})
            continue
        best = max(s["score"] for s in scores.values())
        in_tier = {m: d for m, d in scores.items() if d["score"] >= tier * best}
        def cost_key(item):
            c = blended_cost(item[1]["entry"])
            return (c is None, c if c is not None else 0.0, -item[1]["score"])
        pick, picked = min(in_tier.items(), key=cost_key)
        alt = sorted(in_tier, key=lambda m: (-scores[m]["score"], blended_cost(scores[m]["entry"]) or 1e12))[:3]
        ladder = [m for m in sorted(scores, key=lambda m: (-scores[m]["score"],
                 blended_cost(scores[m]["entry"]) or 1e12))]
        prov = {m["id"]: m.get("provider") for m in available}
        providers = {m: prov.get(m) for m in scores}
        out.append({
            "role": role,
            "suggested": pick,
            "suggested_provider": prov.get(pick),
            "reason": "score {:.1f}, cost ${}/1M blended".format(picked["score"],
                     _fmt_cost(blended_cost(picked["entry"]))),
            "missing_data": picked["missing"],
            "tier": alt,
            "ladder": ladder,
            "providers": providers,
            "purpose": purpose,
        })
    return out


def fmt_table(results, benchmarks):
    lines = ["%-12s %-22s %-30s %s" % ("role", "suggested", "basis", "alternatives")]
    for r in results:
        if not r["suggested"]:
            lines.append("%-12s %-22s %s" % (r["role"], "(none)", r["reason"]))
            continue
        sp = r.get("suggested_provider")
        shown = "%s @%s" % (r["suggested"], sp) if sp else r["suggested"]
        lines.append("%-12s %-22s %-30s %s" % (
            r["role"], shown, r["reason"],
            ", ".join(a for a in r["tier"] if a != r["suggested"]) or "-"))
        if r["missing_data"]:
            lines.append("  ! no data for purposes: %s (refresh benchmarks)" % ", ".join(r["missing_data"]))
    return "\n".join(lines)


def refresh_queries(benchmarks_path):
    with open(benchmarks_path, encoding="utf-8") as f:
        data = json.load(f)
    purposes = sorted({p for m in data.get("models", {}).values()
                       for p in (m.get("scores") or {})})
    queries = [
        "site:llm-stats.com OR site:morphllm.com SWE-bench Verified MMLU scores 2026",
        "LLM API pricing per 1M tokens 2026 claude gpt deepseek qwen",
    ] + [f"best models {p} benchmark 2026 leaderboard" for p in purposes]
    return queries


def main():
    ap = argparse.ArgumentParser(description="Cost-effective model suggestion per PMOS role")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("suggest", help="suggest models from the live available list (default)")
    p.add_argument("--available", required=True, help="swarm list_models output or JSON list file")
    p.add_argument("--benchmarks", default=None)
    p.add_argument("--roster", default=None)
    p.add_argument("--tier", type=float, default=0.92, help="best-tier threshold as fraction of best score")
    p.add_argument("--roles", default=None, help="comma-separated role filter")
    p.add_argument("--ladder-out", default=None,
                   help="write per-role fallback ladders to this JSON file (e.g. .pmos/team-model-ladder.json)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("refresh", help="print websearch queries to refresh benchmarks.json")
    p.add_argument("--benchmarks", default=None)

    # allow `recommend.py --available X` (suggest as default) and `recommend.py refresh`
    raw = sys.argv[1:]
    if raw and raw[0] not in ("suggest", "refresh"):
        raw = ["suggest"] + raw
    a = ap.parse_args(raw)
    base = pathlib.Path(__file__).resolve().parent.parent
    benchmarks_path = pathlib.Path(a.benchmarks) if a.benchmarks else base / "benchmarks.json"
    roster_path = pathlib.Path(a.roster) if getattr(a, "roster", None) else base / "roster.json"

    if a.cmd == "refresh":
        print("Refresh benchmarks.json with these websearch queries, then edit the file:")
        for q in refresh_queries(benchmarks_path):
            print("  - " + q)
        return

    available = parse_available(a.available)
    if not available:
        print("no models parsed from %s" % a.available, file=sys.stderr)
        sys.exit(1)
    benchmarks = load_benchmarks(benchmarks_path)
    roster = load_roster(roster_path)
    role_filter = a.roles.split(",") if a.roles else None
    results = recommend(available, benchmarks, roster, a.tier, role_filter)
    if a.json:
        print(json.dumps(results, indent=1, ensure_ascii=False))
    else:
        print(fmt_table(results, benchmarks))
    if a.ladder_out:
        ladder_map = {r["role"]: r["ladder"] for r in results}
        lp = pathlib.Path(a.ladder_out)
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(
            json.dumps(ladder_map, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\nfallback ladders written to %s" % a.ladder_out, file=sys.stderr)
    # availability summary (stderr when --json so stdout stays pure JSON)
    out = sys.stderr if a.json else sys.stdout
    avail = eligible_models({m["id"] for m in available if m.get("available", True)}, roster)
    known = set(benchmarks)
    covered = {m for m in avail if normalize_id(m) in known}
    print("\n%s available models; %d with benchmark data (refresh to expand)"
          % (len(avail), len(covered)), file=out)
    uncovered = sorted(m for m in avail if normalize_id(m) not in known)
    if uncovered:
        print("  no benchmark data: %s" % ", ".join(uncovered), file=out)


if __name__ == "__main__":
    main()
