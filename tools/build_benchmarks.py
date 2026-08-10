#!/usr/bin/env python3
"""Build benchmarks.json from Epoch AI benchmark hub CSVs + LiveBench.

Maps each benchmark CSV to role purposes (coding, reasoning, design, business,
marketing, verification, ops, writing), normalizes per-model scores to 0-100,
merges in LiveBench category scores (third source), overlays a curated pricing
table (Epoch has no prices; LiveBench's cost file fills gaps), and writes
benchmarks.json for tools/recommend.py.

Run:  python tools/build_benchmarks.py [--data-dir benchmark_data] [--out benchmarks.json]
      # add --livebench-date 2026_06_25 (default) to merge LiveBench, or --no-livebench
      # add --baseline benchmarks.json to seed from an existing file when CSVs are absent
"""
import argparse
import csv
import json
import math
import pathlib
import sys
import urllib.request

# benchmark file -> (purposes/weights it informs, score column, lower_is_better)
# weights are relative within a purpose; a benchmark can inform several purposes
BENCHMARKS = {
    "swe_bench_verified.csv":          ({"coding": 1.0, "verification": 1.0}, "mean_score", False),
    "frontierswe_external.csv":        ({"coding": 0.7}, "Dominance", False),
    "aider_polyglot_external.csv":     ({"coding": 0.8}, "Percent correct", False),
    "cybench_external.csv":            ({"coding": 0.6, "verification": 0.5}, "Unguided % Solved", False),
    "scicode_external.csv":            ({"coding": 0.7}, "Score", False),
    "frontiercode_external.csv":       ({"coding": 0.9}, "Main score", False),
    "deepswe_external.csv":            ({"coding": 0.8}, "Pass@1", False),
    "cad_eval_external.csv":           ({"coding": 0.5}, "Overall pass (%)", False),
    "weirdml_external.csv":            ({"coding": 0.4}, "Accuracy", False),
    "gpqa_diamond.csv":                ({"reasoning": 1.0}, "mean_score", False),
    "arc_agi_2_external.csv":          ({"reasoning": 0.9}, "Score", False),
    "arc_agi_external.csv":            ({"reasoning": 0.8}, "Score", False),
    "arc_ai2_external.csv":            ({"reasoning": 0.6}, "Challenge score", False),
    "frontiermath.csv":                ({"reasoning": 0.9}, "mean_score", False),
    "frontiermath_tier_4.csv":         ({"reasoning": 0.8}, "mean_score", False),
    "math_level_5.csv":                ({"reasoning": 0.7}, "mean_score", False),
    "hle_external.csv":                ({"reasoning": 0.7}, "Accuracy", False),
    "bbh_external.csv":                ({"reasoning": 0.6}, "Average", False),
    "mmlu_external.csv":               ({"reasoning": 0.5, "business": 0.3}, "EM", False),
    "superglue_external.csv":          ({"reasoning": 0.4}, "Score", False),
    "webdev_arena_external.csv":       ({"design": 1.0, "coding": 0.5}, "Arena Score", False),
    "spatialviz_bench_external.csv":   ({"design": 0.7}, "Overall score", False),
    "os_world_external.csv":           ({"ops": 1.0}, "Score", False),
    "osworld_2_external.csv":          ({"ops": 0.8}, "Binary accuracy", False),
    "terminalbench_external.csv":      ({"ops": 0.7, "coding": 0.3}, "Accuracy mean", False),
    "metr_time_horizons_external.csv": ({"ops": 0.6}, "Time horizon", False),
    "ale_bench_external.csv":          ({"ops": 0.5}, "Performance", False),
    "vending_bench_2_external.csv":    ({"ops": 0.5}, "Score", False),
    "apex_agents_external.csv":        ({"ops": 0.4}, "Pass@1 score", False),
    "balrog_external.csv":             ({"verification": 0.8}, "Average progress", False),
    "exploitbench_external.csv":       ({"verification": 0.7}, "Mean capability", False),
    "gdpval_external.csv":             ({"verification": 0.6}, "Win Rate (%)", False),
    "the_agent_company_external.csv":  ({"ops": 0.6, "verification": 0.4}, "% Score", False),
    "forecastbench_external.csv":      ({"business": 0.9}, "Overall score", False),
    "btf3_external.csv":               ({"business": 0.8}, "Pooled score", True),
    "deepresearchbench_external.csv":  ({"business": 0.7}, "Average score", False),
    "gdp_pdf_external.csv":            ({"business": 0.5}, "GDP.pdf score", False),
    "lech_mazur_writing_external.csv": ({"writing": 1.0, "marketing": 0.5}, "Mean score", False),
    "fictionlivebench_external.csv":   ({"writing": 0.8}, "120k token score", False),
    "live_bench_external.csv":         ({"marketing": 0.7, "writing": 0.5}, "Global average", False),
    "simplebench_external.csv":        ({"marketing": 0.5}, "Score (AVG@5)", False),
    "epoch_capabilities_index.csv":    ({"reasoning": 0.4, "coding": 0.3, "business": 0.4,
                                           "marketing": 0.3, "ops": 0.3, "design": 0.3}, "ECI Score", False),
}

# curated pricing overlay, USD per 1M tokens (Epoch data has no prices)
# missing entries -> cost null in output; recommend.py treats unknown cost as "expensive"
PRICING = {
    "claude-fable-5": (3.0, 15.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5.6-pro": (10.0, 40.0),
    "gpt-5.5-pro": (8.0, 32.0),
    "deepseek-v4-pro": (0.28, 1.10),
    "deepseek-v4-flash": (0.14, 0.55),
    "qwen3.8-max": (0.4, 1.2),
    "qwen3.7-max": (0.4, 1.2),
    "qwen3.6-flash": (0.2, 0.6),
    "glm-5.2": (1.0, 3.0),
}

# ---------------------------------------------------------------------------
# LiveBench (livebench.ai) third source.
#
# LiveBench publishes per-model scores on ~23 subtasks, grouped into 7
# categories, refreshed roughly every 6 months as dated files under the
# `LiveBench/new-livebench` GitHub repo. It is contamination-free and gives
# objective category scores that complement Epoch (aggregate) data.
# ---------------------------------------------------------------------------

# date suffix -> public files. The latest release is the default.
LIVEBENCH_BASE = "https://raw.githubusercontent.com/LiveBench/new-livebench/main/public"
LIVEBENCH_TABLE = "table_{date}.csv"
LIVEBENCH_CATEGORIES = "categories_{date}.json"
LIVEBENCH_COST = "cost_{date}.csv"

# livebench model id -> our clean model id (in benchmarks.json / recommend.py)
# Provider-prefixed duplicates and unscored variants are omitted.
LIVEBENCH_ALIAS = {
    "claude-opus-5-max-effort": "claude-opus-5",
    "claude-opus-4-8-max-effort": "claude-opus-4-8",
    "claude-opus-4-7-xhigh-effort": "claude-opus-4-7",
    "claude-opus-4-6-thinking-auto-high-effort": "claude-opus-4-6",
    "claude-opus-4-5-20251101-thinking-64k-high-effort": "claude-opus-4-5-20251101",
    "claude-sonnet-5-xhigh-effort": "claude-sonnet-5",
    "claude-sonnet-4-6-thinking-auto-medium-effort": "claude-sonnet-4-6",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek-v4-flash-0731": "deepseek-v4-flash-0731",
    "qwen3.8-max": "qwen3.8-max",
    "qwen3.7-max": "qwen3.7-max",
    "glm-5.2": "glm-5.2",
    "kimi-k2.7-code": "kimi-k2.7-code",
}

# LiveBench category -> role-purpose weights it informs (weights sum to 1 per category).
# LiveBench has no design/verification categories, so those purposes keep Epoch only.
LIVEBENCH_PURPOSE = {
    "Reasoning":        {"reasoning": 1.0},
    "Coding":           {"coding": 1.0},
    "Agentic Coding":   {"coding": 0.6, "ops": 0.4},
    "Mathematics":      {"reasoning": 1.0},
    "Data Analysis":    {"business": 1.0},
    "Language":         {"writing": 1.0},
    "IF":               {"marketing": 0.5, "business": 0.5},
}


def norm_model(name: str) -> str:
    """Normalize Epoch model names to plain ids (strip effort/scorer/context suffixes)."""
    n = name.strip()
    n = n.split(" [")[0]
    n = n.split("(")[0].strip()
    for suf in ["_max", "_high", "_xhigh", "_low", "_medium", "_pre-release",
                "_1K", "_12K", "_16K", "_32K", "_120K", "_128K", "_unknown", "_none"]:
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    return n.strip()


def norm_score(col, value) -> float | None:
    """Parse a raw score value; min-max normalization later maps any scale to 0-100."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def fetch_livebench(date: str, dest_dir: pathlib.Path) -> bool:
    """Download the LiveBench table/categories/cost for `date` into dest_dir.

    Returns True if all three files are present afterwards (downloaded or already
    cached). Never raises on network failure; returns False so main() can degrade
    to the Epoch-only build.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    files = {
        LIVEBENCH_TABLE.format(date=date): "table",
        LIVEBENCH_CATEGORIES.format(date=date): "categories",
        LIVEBENCH_COST.format(date=date): "cost",
    }
    ok = True
    for fname, _label in files.items():
        local = dest_dir / fname
        if local.exists():
            continue
        url = f"{LIVEBENCH_BASE}/{fname}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pmos-build-benchmarks/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                local.write_bytes(resp.read())
            print(f"  fetched {fname}")
        except Exception as e:  # noqa: BLE001 - degrade gracefully offline
            print(f"  ! could not fetch {url}: {e}")
            ok = False
    return ok


def _category_mean(row, subtasks) -> float | None:
    vals = []
    for s in subtasks:
        v = norm_score(s, row.get(s))
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return sum(vals) / len(vals)


def ingest_livebench(model_scores, model_meta, model_benchmarks, pricing,
                     date: str, dest_dir: pathlib.Path) -> dict:
    """Merge LiveBench category scores into model_scores as a third source.

    Scores are min-max normalized per category across ALL models in the table
    (consistent with the per-benchmark normalization already used for Epoch),
    then mapped to role purposes via LIVEBENCH_PURPOSE. Also fills cost pricing
    for alias-mapped models missing from the curated PRICING overlay.

    Returns {"models": int, "purposes": [...]} for reporting.
    """
    tfile = dest_dir / LIVEBENCH_TABLE.format(date=date)
    cfile = dest_dir / LIVEBENCH_CATEGORIES.format(date=date)
    costfile = dest_dir / LIVEBENCH_COST.format(date=date)
    if not (tfile.exists() and cfile.exists()):
        return {"models": 0, "purposes": []}

    categories = json.loads(cfile.read_text(encoding="utf-8"))
    with open(tfile, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    # 1) category -> model -> normalized score (0-100) across all table models
    cat_scores = {}  # category -> {clean_id: score} (only alias-mapped kept later)
    for cat, subtasks in categories.items():
        raw = {}  # model -> category mean
        for row in rows:
            name = (row.get("model") or "").strip()
            m = _category_mean(row, subtasks)
            if name and m is not None:
                raw[name] = m
        if not raw:
            continue
        lo, hi = min(raw.values()), max(raw.values())
        span = hi - lo
        norm = {}
        for name, v in raw.items():
            clean = LIVEBENCH_ALIAS.get(name)
            if clean is None:
                continue
            norm[clean] = round(((v - lo) / span * 100.0) if span > 0 else 100.0, 1)
        if norm:
            cat_scores[cat] = norm

    # 2) map normalized category scores to purposes and append to model_scores
    purposes = []
    lb_models = set()
    for clean, weights in LIVEBENCH_PURPOSE.items():
        per_cat = cat_scores.get(clean)
        if not per_cat:
            continue
        for purpose, w in weights.items():
            if purpose not in purposes:
                purposes.append(purpose)
            for m, cscore in per_cat.items():
                # Skip models whose baseline already includes LiveBench (idempotent regen).
                if "already_livebenched" in model_benchmarks.get(m, set()):
                    continue
                model_scores.setdefault(m, {})
                model_meta.setdefault(m, {})
                model_benchmarks.setdefault(m, set()).add(f"livebench_{date}")
                lb_models.add(m)
                model_scores[m].setdefault(purpose, []).append(cscore * w)

    # 3) fill cost pricing for alias-mapped models missing from PRICING
    added_prices = 0
    if costfile.exists():
        with open(costfile, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                clean = LIVEBENCH_ALIAS.get((row.get("model") or "").strip())
                if clean is None or clean in pricing:
                    continue
                try:
                    cin = float(row.get("input_price_per_million"))
                    cout = float(row.get("output_price_per_million"))
                except (TypeError, ValueError):
                    continue
                pricing[clean] = (cin, cout)
                added_prices += 1
    if added_prices:
        print(f"  livebench: added cost pricing for {added_prices} models")

    return {"models": len(lb_models), "purposes": purposes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="benchmark_data")
    ap.add_argument("--out", default="benchmarks.json")
    ap.add_argument("--livebench-date", default="2026_06_25",
                    help="LiveBench release date suffix (e.g. 2026_06_25)")
    ap.add_argument("--no-livebench", action="store_true",
                    help="skip LiveBench fetch/merge (Epoch-only build)")
    ap.add_argument("--baseline", default=None,
                    help="existing benchmarks.json to seed Epoch scores from when the "
                         "benchmark_data CSVs are absent (non-destructive regeneration)")
    a = ap.parse_args()

    data_dir = pathlib.Path(a.data_dir)
    # per normalized-model -> purpose -> list of scores from its benchmarks
    model_scores = {}          # model -> purpose -> [scores]
    model_meta = {}            # model -> {org, country, release}
    model_benchmarks = {}      # model -> set of benchmark files with data
    baseline_entries = {}      # model -> original entry (for non-destructive regen)

    # Seed from an existing benchmarks.json when the Epoch CSVs are absent, so a
    # regeneration only ADDS LiveBench instead of dropping the curated Epoch data.
    if a.baseline:
        with open(a.baseline, encoding="utf-8") as fh:
            base = json.load(fh)
        for m, e in (base.get("models") or {}).items():
            if not e.get("scores"):
                continue
            baseline_entries[m] = e
            model_scores.setdefault(m, {})
            model_meta.setdefault(m, e.get("meta") or {})
            model_benchmarks.setdefault(m, set())
            # If the baseline already carries a LiveBench merge, remember it so a
            # re-run doesn't merge LiveBench a second time (keeps regen idempotent).
            if " + LiveBench (" in (e.get("source") or ""):
                model_benchmarks[m].add("already_livebenched")
            for p, v in e["scores"].items():
                model_scores[m].setdefault(p, []).append(v)
        print(f"  baseline: seeded {len(baseline_entries)} models from {a.baseline}")

    for fname, (purposes, col, lower) in BENCHMARKS.items():
        f = data_dir / fname
        if not f.exists():
            print(f"  ! missing {fname}")
            continue
        with open(f, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        # collect (model, score) pairs, then min-max normalize THIS benchmark to 0-100
        pairs = []
        for row in rows:
            name = (row.get("Model version") or "").strip()
            score = norm_score(col, row.get(col))
            if name and score is not None:
                pairs.append((norm_model(name), score))
        if not pairs:
            print(f"  {fname}: 0 rows used")
            continue
        vals = [s for _, s in pairs]
        lo, hi = min(vals), max(vals)
        span = hi - lo
        for m, raw in pairs:
            if span > 0:
                z = (hi - raw) / span if lower else (raw - lo) / span
                score = round(z * 100.0, 1)
            else:
                score = 100.0
            model_scores.setdefault(m, {})
            model_meta.setdefault(m, {})
            # metadata from the first row for this model (org may be blank in some files)
            model_meta[m].setdefault("org", "")
            for row in rows:
                if (row.get("Model version") or "").strip() == name and (row.get("Organization") or row.get("Company") or ""):
                    model_meta[m]["org"] = row.get("Organization") or row.get("Company") or ""
                    model_meta[m]["country"] = row.get("Country") or ""
                    model_meta[m]["release"] = (row.get("Release date") or "")[:10]
                    break
            model_benchmarks.setdefault(m, set()).add(fname)
            for purpose, w in purposes.items():
                model_scores[m].setdefault(purpose, []).append(score)
        print(f"  {fname}: {len(pairs)} rows used")

    # --- third source: LiveBench ----------------------------------------------
    lb_stats = None
    if not a.no_livebench:
        lb_dir = data_dir / f"livebench_{a.livebench_date}"
        if fetch_livebench(a.livebench_date, lb_dir):
            lb_stats = ingest_livebench(model_scores, model_meta, model_benchmarks,
                                        PRICING, a.livebench_date, lb_dir)
            if lb_stats["models"]:
                print(f"  livebench {a.livebench_date}: merged into "
                      f"{lb_stats['models']} models across purposes "
                      f"{', '.join(sorted(lb_stats['purposes']))}")
            else:
                print(f"  livebench {a.livebench_date}: no alias-mapped models found "
                      "(check LIVEBENCH_ALIAS against the table)")
        else:
            print("  livebench: data unavailable, building Epoch-only (use --no-livebench to silence)")

    models_out = {}
    for m in sorted(model_scores):
        base = baseline_entries.get(m)
        # Baseline model untouched by Epoch CSVs and LiveBench (or already carrying a
        # prior LiveBench merge, so a re-run is idempotent) -> keep as-is.
        if base and not [b for b in model_benchmarks[m] if b != "already_livebenched"]:
            models_out[m] = base
            continue
        lb_files = sorted(b for b in model_benchmarks[m] if b.startswith("livebench_"))
        scores = {p: round(sum(vals) / len(vals), 1)
                  for p, vals in model_scores[m].items()}
        if base:
            entry = dict(base)
            entry["scores"] = scores
            cin, cout = PRICING.get(m, (None, None))
            if cin is not None:
                entry["cost_in"], entry["cost_out"] = cin, cout
            if lb_files and " + LiveBench (" not in entry.get("source", ""):
                entry["source"] = (entry.get("source", "").rstrip()
                                   + f" + LiveBench ({', '.join(lb_files)})")
            entry["confidence"] = "sourced"
            models_out[m] = entry
            continue
        # Brand-new model from the Epoch CSV loop (no baseline).
        cin, cout = PRICING.get(m, (None, None))
        srcs = ["Epoch AI Benchmarking Hub (epoch.ai/benchmarks)"]
        if lb_files:
            srcs.append(f"LiveBench ({', '.join(lb_files)})")
        src = " + ".join(srcs)
        epoch_files = sorted(b for b in model_benchmarks[m] if not b.startswith("livebench_"))
        if epoch_files:
            src += "; benchmarks: " + ", ".join(epoch_files)
        models_out[m] = {
            "scores": scores,
            "cost_in": cin,
            "cost_out": cout,
            "source": src,
            "confidence": "sourced",
            "meta": model_meta[m],
        }

    as_of = "2026-08-08"
    lb_note = ""
    lb_present = bool(lb_stats and lb_stats["models"]) or any(
        "already_livebenched" in bset for bset in model_benchmarks.values()
    )
    if lb_present:
        as_of = "2026-08-10"
        lb_note = (f" LiveBench release {a.livebench_date} (livebench.ai, "
                   "contamination-free) was merged as a third source: category scores "
                   "min-max normalized per category then mapped to purposes via "
                   "tools/build_benchmarks.py LIVEBENCH_PURPOSE. cost prices for models "
                   "missing from the curated overlay were filled from LiveBench's cost file.")
    out = {
        "as_of": as_of,
        "note": "Generated by tools/build_benchmarks.py from Epoch AI benchmark hub CSVs "
                "(epoch.ai/benchmarks, CC BY 4.0). Scores are 0-100 purpose means across the "
                "mapped benchmarks. cost_in/cost_out are USD per 1M tokens estimates; "
                "models without pricing get null (recommend.py treats null cost as expensive)."
                + lb_note,
        "models": models_out,
        "purposes": sorted({p for m in models_out.values() for p in m["scores"]}),
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"\nwrote {a.out}: {len(models_out)} models, "
          f"{len(out['purposes'])} purposes ({', '.join(out['purposes'])})")


if __name__ == "__main__":
    main()
