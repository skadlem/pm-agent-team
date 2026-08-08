#!/usr/bin/env python3
"""Build benchmarks.json from Epoch AI benchmark hub CSVs (benchmark_data/).

Maps each benchmark CSV to role purposes (coding, reasoning, design, business,
marketing, verification, ops, writing), normalizes per-model scores to 0-100,
merges with a small curated pricing overlay (Epoch data has no prices), and
writes benchmarks.json for tools/recommend.py.

Run:  python tools/build_benchmarks.py [--data-dir benchmark_data] [--out benchmarks.json]
"""
import argparse
import csv
import json
import math
import pathlib

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="benchmark_data")
    ap.add_argument("--out", default="benchmarks.json")
    a = ap.parse_args()

    data_dir = pathlib.Path(a.data_dir)
    # per normalized-model -> purpose -> list of scores from its benchmarks
    model_scores = {}          # model -> purpose -> [scores]
    model_meta = {}            # model -> {org, country, release}
    model_benchmarks = {}      # model -> set of benchmark files with data

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

    models_out = {}
    for m in sorted(model_scores):
        scores = {}
        for purpose, vals in model_scores[m].items():
            # weight each benchmark equally within a purpose, keep mean
            scores[purpose] = round(sum(vals) / len(vals), 1)
        cin, cout = PRICING.get(m, (None, None))
        models_out[m] = {
            "scores": scores,
            "cost_in": cin,
            "cost_out": cout,
            "source": "Epoch AI Benchmarking Hub (epoch.ai/benchmarks) "
                      + "; benchmarks: " + ", ".join(sorted(model_benchmarks[m])),
            "confidence": "sourced",
            "meta": model_meta[m],
        }

    out = {
        "as_of": "2026-08-08",
        "note": "Generated by tools/build_benchmarks.py from Epoch AI benchmark hub CSVs "
                "(epoch.ai/benchmarks, CC BY 4.0). Scores are 0-100 purpose means across the "
                "mapped benchmarks. cost_in/cost_out are curated USD per 1M tokens estimates; "
                "models without pricing get null (recommend.py treats null cost as expensive).",
        "models": models_out,
        "purposes": sorted({p for m in models_out.values() for p in m["scores"]}),
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"\nwrote {a.out}: {len(models_out)} models, "
          f"{len(out['purposes'])} purposes ({', '.join(out['purposes'])})")


if __name__ == "__main__":
    main()
