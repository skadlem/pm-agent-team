#!/usr/bin/env python3
"""PMOS spend ledger: what workers actually cost, not what we guessed.

config.json carries one flat `est_tokens_per_worker` for every role and worker,
and nothing recorded what was really spent, so the `budget_usd` guardrail agreed
with itself and with nothing else. This keeps an append-only ledger of worker
runs, prices them from benchmarks.json (cost_in / cost_out per 1M), and lets the
next wave be estimated from THIS project's history instead of the flat guess.

    python tools/cost.py record --project . --role backend --model claude-opus-5 \\
        --wave 3 --label backend-1 --in 180000 --out 24000
    python tools/cost.py report   --project . [--json]
    python tools/cost.py estimate --project . --roles backend,frontend [--json]
    python tools/cost.py calibrate --project . [--write]
    python tools/cost.py selftest

The ledger is `.pmos/costs.jsonl`, one JSON object per line: plain text, commits
with the rest of .pmos, and readable without this tool.

`record` never invents numbers. When the agent host does not report usage, pass
`--source estimated`; report keeps measured and estimated spend apart so a budget
built on guesses is visibly a guess.

Exit codes: report and estimate return 2 when spend is over `budget_usd`
(GATE 1's cap), so a wave can be gated on them.
"""
import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recommend import blended_cost, normalize_id  # noqa: E402  (sibling tool)

TPL = Path(__file__).resolve().parent.parent
LEDGER = "costs.jsonl"
CALIBRATION = "cost-model.json"
# A coding worker reads far more than it writes; used only to split the flat
# config estimate into input/output when this project has no history yet.
DEFAULT_IN_SHARE = 0.85
MIN_SAMPLES = 2


def load_prices(path=None):
    data = json.loads(Path(path or TPL / "benchmarks.json").read_text(encoding="utf-8"))
    return data.get("models", data)


def price_of(model, prices):
    """(cost_in, cost_out) per 1M tokens, or (None, None) when unpriced."""
    for key in (model, normalize_id(model)):
        entry = prices.get(key)
        if entry and entry.get("cost_in") is not None and entry.get("cost_out") is not None:
            return entry["cost_in"], entry["cost_out"]
    return None, None


def usd_of(tokens_in, tokens_out, model, prices):
    cin, cout = price_of(model, prices)
    if cin is None:
        return None
    return tokens_in / 1e6 * cin + tokens_out / 1e6 * cout


def ledger_path(proj):
    return Path(proj) / ".pmos" / LEDGER


def read_ledger(proj):
    p = ledger_path(proj)
    if not p.is_file():
        return []
    rows = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            print("warning: %s line %d is not JSON, skipped" % (p, n), file=sys.stderr)
    return rows


def budget_of(proj):
    tm = Path(proj) / ".pmos" / "team-model.json"
    if not tm.is_file():
        return None, {}
    try:
        data = json.loads(tm.read_text(encoding="utf-8"))
    except ValueError:
        return None, {}
    roles = {k: v for k, v in data.items() if k != "budget_usd" and isinstance(v, dict)}
    return data.get("budget_usd"), roles


def cmd_record(args):
    prices = load_prices(args.benchmarks)
    usd = usd_of(args.tokens_in, args.tokens_out, args.model, prices)
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "wave": args.wave, "role": args.role, "label": args.label or args.role,
           "model": args.model, "effort": args.effort or "",
           "tokens_in": args.tokens_in, "tokens_out": args.tokens_out,
           "usd": round(usd, 4) if usd is not None else None,
           "source": args.source, "status": args.status}
    if args.task:
        row["task"] = args.task
    p = ledger_path(args.project)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    total = sum(r["usd"] or 0 for r in read_ledger(args.project))
    budget, _ = budget_of(args.project)
    note = "" if usd is not None else "  (model not priced in benchmarks.json)"
    print("recorded %s %s: %d in / %d out = %s%s"
          % (row["role"], row["model"], row["tokens_in"], row["tokens_out"],
             "$%.4f" % usd if usd is not None else "unpriced", note))
    print("project total: $%.2f%s" % (total, " of $%.2f budget" % budget if budget else ""))
    if budget and total > budget:
        print("OVER BUDGET by $%.2f - stop and ask the user" % (total - budget))
        return 2
    return 0


def summarize(rows):
    out = {"runs": len(rows), "usd": 0.0, "measured_usd": 0.0, "estimated_usd": 0.0,
           "tokens_in": 0, "tokens_out": 0, "unpriced": 0, "failed": 0}
    for r in rows:
        out["tokens_in"] += r.get("tokens_in", 0)
        out["tokens_out"] += r.get("tokens_out", 0)
        if r.get("usd") is None:
            out["unpriced"] += 1
        else:
            out["usd"] += r["usd"]
            key = "measured_usd" if r.get("source") == "measured" else "estimated_usd"
            out[key] += r["usd"]
        if r.get("status") not in ("ok", None):
            out["failed"] += 1
    for k in ("usd", "measured_usd", "estimated_usd"):
        out[k] = round(out[k], 4)
    return out


def group(rows, key):
    buckets = {}
    for r in rows:
        buckets.setdefault(r.get(key), []).append(r)
    return {k: summarize(v) for k, v in sorted(buckets.items(), key=lambda kv: str(kv[0]))}


def cmd_report(args):
    rows = read_ledger(args.project)
    budget, _ = budget_of(args.project)
    total = summarize(rows)
    cfg = json.loads((Path(args.config).read_text(encoding="utf-8"))) if args.config else \
        json.loads((TPL / "config.json").read_text(encoding="utf-8"))
    flat = cfg.get("cost", {}).get("est_tokens_per_worker", 400000)
    measured = [r for r in rows if r.get("source") == "measured"]
    accuracy = None
    if measured:
        actuals = [r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in measured]
        med = statistics.median(actuals)
        accuracy = {"flat_estimate": flat, "median_actual": med, "runs": len(measured),
                    "ratio": round(flat / med, 2) if med else None}
    out = {"total": total, "budget_usd": budget,
           "remaining_usd": round(budget - total["usd"], 4) if budget else None,
           "by_role": group(rows, "role"), "by_wave": group(rows, "wave"),
           "by_model": group(rows, "model"), "estimate_accuracy": accuracy}
    if args.json:
        print(json.dumps(out, indent=1))
    else:
        if not rows:
            print("no runs recorded yet (%s)" % ledger_path(args.project))
            return 0
        print("%-12s %5s %12s %12s %10s" % ("role", "runs", "tokens in", "tokens out", "usd"))
        for role, s in out["by_role"].items():
            print("%-12s %5d %12d %12d %10.2f"
                  % (role, s["runs"], s["tokens_in"], s["tokens_out"], s["usd"]))
        print("%-12s %5d %12d %12d %10.2f"
              % ("TOTAL", total["runs"], total["tokens_in"], total["tokens_out"], total["usd"]))
        if total["estimated_usd"]:
            print("  of which measured $%.2f, estimated $%.2f"
                  % (total["measured_usd"], total["estimated_usd"]))
        if total["unpriced"]:
            print("  %d run(s) on models with no price in benchmarks.json" % total["unpriced"])
        if total["failed"]:
            print("  %d failed run(s) - they cost money too" % total["failed"])
        if budget:
            print("budget $%.2f, remaining $%.2f" % (budget, out["remaining_usd"]))
        if accuracy and accuracy["ratio"]:
            verdict = "over" if accuracy["ratio"] > 1 else "under"
            print("config est_tokens_per_worker is %s by %.1fx (flat %d vs median actual %d over %d run(s))"
                  % (verdict, accuracy["ratio"] if accuracy["ratio"] > 1 else 1 / accuracy["ratio"],
                     flat, accuracy["median_actual"], accuracy["runs"]))
    if budget and total["usd"] > budget:
        return 2
    return 0


def calibration(proj):
    p = Path(proj) / ".pmos" / CALIBRATION
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def cmd_calibrate(args):
    rows = [r for r in read_ledger(args.project) if r.get("source") == "measured"]
    per_role, model = {}, {}
    for r in rows:
        per_role.setdefault(r.get("role"), []).append(r)
    for role, rs in sorted(per_role.items()):
        if len(rs) < MIN_SAMPLES:
            continue
        model[role] = {
            "tokens_in": int(statistics.median(r.get("tokens_in", 0) for r in rs)),
            "tokens_out": int(statistics.median(r.get("tokens_out", 0) for r in rs)),
            "runs": len(rs)}
    out = {"roles": model, "samples": len(rows),
           "suggested_est_tokens_per_worker":
               int(statistics.median([r.get("tokens_in", 0) + r.get("tokens_out", 0)
                                      for r in rows])) if rows else None}
    if args.write and model:
        p = Path(args.project) / ".pmos" / CALIBRATION
        p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    if args.json:
        print(json.dumps(out, indent=1))
    else:
        if not rows:
            print("no measured runs yet: nothing to calibrate")
            return 0
        for role, m in model.items():
            print("%-12s median %d in / %d out over %d run(s)"
                  % (role, m["tokens_in"], m["tokens_out"], m["runs"]))
        skipped = sorted(r for r in per_role if r not in model)
        if skipped:
            print("not enough samples (<%d) for: %s" % (MIN_SAMPLES, ", ".join(skipped)))
        print("suggested config.json est_tokens_per_worker: %s"
              % out["suggested_est_tokens_per_worker"])
        if args.write and model:
            print("wrote .pmos/%s" % CALIBRATION)
    return 0


def cmd_estimate(args):
    prices = load_prices(args.benchmarks)
    budget, roles_map = budget_of(args.project)
    cfg = json.loads((Path(args.config).read_text(encoding="utf-8"))) if args.config else \
        json.loads((TPL / "config.json").read_text(encoding="utf-8"))
    flat = cfg.get("cost", {}).get("est_tokens_per_worker", 400000)
    cal = calibration(args.project).get("roles", {})
    spent = summarize(read_ledger(args.project))["usd"]

    rows, total = [], 0.0
    for role in [r.strip() for r in args.roles.split(",") if r.strip()]:
        model = (roles_map.get(role) or {}).get("model") or args.model
        if not model:
            rows.append({"role": role, "error": "no model in team-model.json; pass --model"})
            continue
        if role in cal:
            tin, tout, basis = cal[role]["tokens_in"], cal[role]["tokens_out"], "calibrated"
        else:
            tin = int(flat * DEFAULT_IN_SHARE)
            tout = flat - tin
            basis = "flat config estimate"
        usd = usd_of(tin, tout, model, prices)
        total += usd or 0
        rows.append({"role": role, "model": model, "tokens_in": tin, "tokens_out": tout,
                     "usd": round(usd, 4) if usd is not None else None, "basis": basis})
    remaining = round(budget - spent, 4) if budget else None
    out = {"wave": args.wave, "workers": rows, "estimate_usd": round(total, 4),
           "already_spent_usd": spent, "budget_usd": budget, "remaining_usd": remaining,
           "over_budget": bool(budget and spent + total > budget)}
    if args.json:
        print(json.dumps(out, indent=1))
    else:
        for r in rows:
            if "error" in r:
                print("%-12s %s" % (r["role"], r["error"]))
                continue
            print("%-12s %-22s %8d in / %7d out  %8s  (%s)"
                  % (r["role"], r["model"], r["tokens_in"], r["tokens_out"],
                     "$%.2f" % r["usd"] if r["usd"] is not None else "unpriced", r["basis"]))
        print("wave estimate $%.2f; spent so far $%.2f" % (total, spent))
        if budget:
            print("budget $%.2f, remaining after this wave $%.2f"
                  % (budget, budget - spent - total))
        if out["over_budget"]:
            print("THIS WAVE WOULD EXCEED THE BUDGET - stop and ask the user to raise the cap,"
                  "\ndrop a role, or move a role to a cheaper model")
    return 2 if out["over_budget"] else 0


def selftest():
    import tempfile
    ok = True
    root = Path(tempfile.mkdtemp())
    (root / ".pmos").mkdir()
    (root / ".pmos" / "team-model.json").write_text(json.dumps({
        "backend": {"model": "claude-opus-5", "effort": "medium"},
        "designer": {"model": "claude-opus-5", "effort": "low"},
        "budget_usd": 5.0}), encoding="utf-8")

    def rec(role, tin, tout, source="measured", status="ok", wave=3):
        a = argparse.Namespace(project=str(root), role=role, model="claude-opus-5", wave=wave,
                               label=role, effort="medium", tokens_in=tin, tokens_out=tout,
                               source=source, status=status, task=None, benchmarks=None)
        return cmd_record(a)

    import io

    def quiet(fn, a):
        saved, sys.stdout = sys.stdout, io.StringIO()
        try:
            rc = fn(a)
            return rc, sys.stdout.getvalue()
        finally:
            sys.stdout = saved

    quiet(cmd_record, argparse.Namespace(
        project=str(root), role="backend", model="claude-opus-5", wave=3, label="backend-1",
        effort="medium", tokens_in=200000, tokens_out=20000, source="measured", status="ok",
        task="T-001", benchmarks=None))
    quiet(cmd_record, argparse.Namespace(
        project=str(root), role="backend", model="claude-opus-5", wave=3, label="backend-2",
        effort="medium", tokens_in=100000, tokens_out=10000, source="measured", status="failed",
        task="T-002", benchmarks=None))
    quiet(cmd_record, argparse.Namespace(
        project=str(root), role="designer", model="claude-opus-5", wave=2, label="designer",
        effort="low", tokens_in=40000, tokens_out=8000, source="estimated", status="ok",
        task=None, benchmarks=None))

    # claude-opus-5 is $5/1M in, $25/1M out in the shipped benchmarks
    rc, out = quiet(cmd_report, argparse.Namespace(project=str(root), json=True, config=None))
    rep = json.loads(out)
    expect_backend = (200000 + 100000) / 1e6 * 5 + (20000 + 10000) / 1e6 * 25
    cases = [
        ("prices runs from benchmarks.json",
         abs(rep["by_role"]["backend"]["usd"] - expect_backend) < 1e-6),
        ("keeps measured and estimated apart",
         rep["total"]["measured_usd"] > 0 and rep["total"]["estimated_usd"] > 0
         and abs(rep["total"]["usd"] - rep["total"]["measured_usd"]
                 - rep["total"]["estimated_usd"]) < 1e-6),
        ("counts failed runs, which still cost money", rep["total"]["failed"] == 1),
        ("groups by wave", set(rep["by_wave"]) == {"2", "3"}),
        ("compares the flat config estimate to reality",
         rep["estimate_accuracy"]["runs"] == 2
         and rep["estimate_accuracy"]["median_actual"] == 165000),
        ("under budget exits 0", rc == 0),
    ]

    rc, out = quiet(cmd_calibrate, argparse.Namespace(project=str(root), json=True, write=True))
    cal = json.loads(out)
    cases += [
        ("calibrates per role from measured runs only",
         cal["roles"]["backend"]["tokens_in"] == 150000 and "designer" not in cal["roles"]),
        ("suggests an evidence-based est_tokens_per_worker",
         cal["suggested_est_tokens_per_worker"] == 165000),
        ("writes the calibration file", (root / ".pmos" / CALIBRATION).is_file()),
    ]

    rc, out = quiet(cmd_estimate, argparse.Namespace(
        project=str(root), roles="backend,designer", wave=3, json=True, model=None,
        config=None, benchmarks=None))
    est = json.loads(out)
    by_role = {r["role"]: r for r in est["workers"]}
    cases += [
        ("estimates a calibrated role from its own history",
         by_role["backend"]["basis"] == "calibrated" and by_role["backend"]["tokens_in"] == 150000),
        ("falls back to the flat estimate without history",
         by_role["designer"]["basis"] == "flat config estimate"),
        ("takes the model from team-model.json", by_role["backend"]["model"] == "claude-opus-5"),
    ]

    # push past the $5 cap: the guardrail must actually trip
    quiet(cmd_record, argparse.Namespace(
        project=str(root), role="backend", model="claude-opus-5", wave=3, label="backend-3",
        effort="medium", tokens_in=900000, tokens_out=100000, source="measured", status="ok",
        task=None, benchmarks=None))
    rc_report, _ = quiet(cmd_report, argparse.Namespace(project=str(root), json=True, config=None))
    rc_est, _ = quiet(cmd_estimate, argparse.Namespace(
        project=str(root), roles="backend", wave=4, json=True, model=None, config=None,
        benchmarks=None))
    cases += [("over budget exits 2", rc_report == 2),
              ("an over-budget wave estimate exits 2", rc_est == 2)]

    # an unpriced model is reported as unpriced, never as free
    quiet(cmd_record, argparse.Namespace(
        project=str(root), role="devops", model="totally-made-up-model", wave=3, label="devops",
        effort="low", tokens_in=1000, tokens_out=100, source="measured", status="ok",
        task=None, benchmarks=None))
    _, out = quiet(cmd_report, argparse.Namespace(project=str(root), json=True, config=None))
    cases.append(("unpriced models are flagged, not counted as free",
                  json.loads(out)["total"]["unpriced"] == 1))

    for label, cond in cases:
        print("   %s %s" % ("[OK]  " if cond else "[FAIL]", label))
        ok = ok and cond
    print("SELFTEST PASS" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="PMOS spend ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--project", default=".")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("record", help="append one worker run to the ledger")
    p.add_argument("--project", default=".")
    p.add_argument("--role", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--wave", type=int, default=None)
    p.add_argument("--label", default=None)
    p.add_argument("--effort", default=None)
    p.add_argument("--task", default=None, help="the plan task id this run worked on")
    p.add_argument("--in", dest="tokens_in", type=int, required=True)
    p.add_argument("--out", dest="tokens_out", type=int, required=True)
    p.add_argument("--source", choices=["measured", "estimated"], default="measured",
                   help="'estimated' when the host does not report usage; kept apart in the report")
    p.add_argument("--status", choices=["ok", "failed", "unknown"], default="ok")
    p.add_argument("--benchmarks", default=None)

    p = sub.add_parser("report", help="spend so far against the GATE 1 budget")
    common(p)
    p.add_argument("--config", default=None)

    p = sub.add_parser("estimate", help="what the next wave will cost")
    common(p)
    p.add_argument("--roles", required=True, help="comma-separated roles about to be spawned")
    p.add_argument("--wave", type=int, default=None)
    p.add_argument("--model", default=None, help="override when team-model.json has no entry")
    p.add_argument("--config", default=None)
    p.add_argument("--benchmarks", default=None)

    p = sub.add_parser("calibrate", help="per-role token medians from this project's history")
    common(p)
    p.add_argument("--write", action="store_true", help="write .pmos/cost-model.json")

    sub.add_parser("selftest")

    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    return {"record": cmd_record, "report": cmd_report,
            "estimate": cmd_estimate, "calibrate": cmd_calibrate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
