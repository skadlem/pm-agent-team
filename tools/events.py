#!/usr/bin/env python3
"""PMOS wave-event trace: what the team actually did, machine-comparable.

The checkpoint log (.pmos/log.md) is prose; the cost ledger (.pmos/costs.jsonl)
is spend only. This adds the missing trajectory dimension: one JSON object per
worker run in `.pmos/waves.jsonl`, appended right after each `cost.py record`
with the same data plus what that ledger cannot know — the fallback-ladder
index and gate annotations. "Per-run project metrics" (README level 4) then
become diffable across projects instead of eyeballed from prose.

    python tools/events.py record --project . --ladder 0 [--gate gate1]
    python tools/events.py report --project . [--json]
    python tools/events.py selftest

`record` invents NOTHING: it merges the cost ledger's newest row (wave, role,
task, model, tokens, usd, status) and refuses to run when there is no row to
attach to — run `cost.py record` first. Identity flags (--role/--wave/--model)
guard against recording the wrong worker when several returns queue up.

`report` aggregates: per-role ok/fail, ladder usage (how often a fallback was
needed), and rework loops — wave numbers going BACKWARDS in the event sequence
(e.g. QA at wave 4 failing back into wave 3). It is informational and always
exits 0; the budget gate stays in cost.py.
"""
import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cost import read_ledger  # noqa: E402  (sibling tool: the ledger parser)

TRACE = "waves.jsonl"


def trace_path(proj):
    return Path(proj) / ".pmos" / TRACE


def read_events(proj):
    p = trace_path(proj)
    if not p.is_file():
        return []
    out = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            print("warning: %s line %d is not JSON, skipped" % (p, n), file=sys.stderr)
    return out


def cmd_record(args):
    rows = read_ledger(args.project)
    if not rows:
        print("no ledger row to attach to: run 'cost.py record' first "
              "(events never invent numbers)", file=sys.stderr)
        return 2
    last = rows[-1]
    for field, want in (("role", args.role), ("wave", args.wave), ("model", args.model)):
        if want is not None and last.get(field) != want:
            print("the ledger's newest row has %s=%r, not %r; record the right "
                  "worker's run first" % (field, last.get(field), want), file=sys.stderr)
            return 2
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wave": last.get("wave"), "role": last.get("role"), "task": last.get("task"),
        "model": last.get("model"), "ladder": args.ladder,
        "outcome": last.get("status") or "unknown",
        "tokens_in": last.get("tokens_in", 0), "tokens_out": last.get("tokens_out", 0),
        "usd": last.get("usd"), "gate": args.gate,
    }
    p = trace_path(args.project)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    print("event recorded: wave %s %s on %s, ladder=%d, outcome=%s"
          % (event["wave"], event["role"], event["model"], args.ladder, event["outcome"]))
    return 0


def summarize(events):
    out = {"runs": len(events), "ok": 0, "failed": 0, "usd": 0.0,
           "ladder_retries": 0, "rework_loops": 0, "by_role": {}, "by_model": {}}
    prev_wave = None
    for e in events:
        if e.get("outcome") == "ok":
            out["ok"] += 1
        elif e.get("outcome") not in (None, "unknown"):
            out["failed"] += 1
        if (e.get("ladder") or 0) > 0:
            out["ladder_retries"] += 1
        out["usd"] += e.get("usd") or 0
        wave = e.get("wave")
        if wave is not None and prev_wave is not None and wave < prev_wave:
            out["rework_loops"] += 1
        if wave is not None:
            prev_wave = wave
        for bucket, key in (("by_role", e.get("role")), ("by_model", e.get("model"))):
            if key is None:
                continue
            r = out[bucket].setdefault(key, {"runs": 0, "ok": 0, "failed": 0,
                                             "tokens": [], "ladder_retries": 0,
                                             "gate_passes": 0})
            r["runs"] += 1
            if e.get("gate"):
                # a gate-annotated event means this worker's output PASSED its gate
                r["gate_passes"] += 1
            if e.get("outcome") == "ok":
                r["ok"] += 1
            elif e.get("outcome") not in (None, "unknown"):
                r["failed"] += 1
            r["tokens"].append(e.get("tokens_in", 0) + e.get("tokens_out", 0))
            if (e.get("ladder") or 0) > 0:
                r["ladder_retries"] += 1
    for bucket in ("by_role", "by_model"):
        for r in out[bucket].values():
            r["median_tokens"] = int(statistics.median(r["tokens"])) if r["tokens"] else 0
            r["ok_rate"] = round(r["ok"] / r["runs"], 3) if r["runs"] else 0.0
            r["pass_rate"] = round(r["gate_passes"] / r["runs"], 3) if r["runs"] else None
            del r["tokens"]
    out["usd"] = round(out["usd"], 4)
    # L-4 failure taxonomy: the coordinator follows this decision instead of
    # improvising. QA sent work back (wave numbers went backwards) twice ->
    # stop retrying the ladder and replan; otherwise keep going (the ladder
    # handles single failures).
    # L-4 ladder: 1 loop -> continue; 2 -> replan; 3+ -> escalate to the user
    # (Magentic-One's re-plan-on-stall: if a replan already failed to break the
    # loop, continuing autonomously is how death spirals happen)
    if out["rework_loops"] >= 3:
        out["decision"] = "escalate"
    elif out["rework_loops"] == 2:
        out["decision"] = "replan"
    else:
        out["decision"] = "continue"
    return out


def cmd_report(args):
    events = read_events(args.project)
    out = summarize(events)
    if args.json:
        print(json.dumps(out, indent=1))
        return 0
    if not events:
        print("no events recorded yet (%s)" % trace_path(args.project))
        return 0
    print("%-12s %5s %4s %7s %12s %8s" % ("role", "runs", "ok", "failed", "median tokens", "retries"))
    for role, r in sorted(out["by_role"].items()):
        print("%-12s %5d %4d %7d %12d %8d"
              % (role, r["runs"], r["ok"], r["failed"], r["median_tokens"], r["ladder_retries"]))
    print("TOTAL %d run(s): %d ok, %d failed, $%.2f; %d ladder retry(ies), %d rework loop(s)"
          % (out["runs"], out["ok"], out["failed"], out["usd"],
             out["ladder_retries"], out["rework_loops"]))
    if out["rework_loops"]:
        print("  wave numbers went backwards %d time(s) - QA sent work back for rework"
              % out["rework_loops"])
    for model, r in sorted(out["by_model"].items()):
        if r["runs"] >= 3 and r["ok_rate"] < 0.5:
            print("  ! %s: %d/%d runs ok (%.0f%%) - historically fails here; "
                  "prefer another ladder entry" % (model, r["ok"], r["runs"], 100 * r["ok_rate"]))
    print("DECISION: %s" % out["decision"])
    if out["decision"] == "replan":
        print("  two rework loops: stop retrying the ladder, replan the task (see "
              "docs/stages/spawn-fallback.md)")
    return 0


def selftest():
    import io
    import tempfile

    def quiet(fn, a):
        saved, sys.stdout = sys.stdout, io.StringIO()
        try:
            return fn(a), sys.stdout.getvalue()
        finally:
            sys.stdout = saved

    ok = True
    root = Path(tempfile.mkdtemp())
    (root / ".pmos").mkdir()
    ledger = root / ".pmos" / "costs.jsonl"

    def add_ledger_row(wave, role, status, tin, tout, usd, task=None):
        row = {"ts": "2026-08-24T00:00:00+00:00", "wave": wave, "role": role,
               "label": role, "model": "claude-opus-5", "effort": "medium",
               "tokens_in": tin, "tokens_out": tout, "usd": usd,
               "source": "measured", "status": status}
        if task:
            row["task"] = task
        with ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    cases = []

    # recording with no ledger row must refuse, not invent
    saved_err, sys.stderr = sys.stderr, io.StringIO()
    try:
        rc = cmd_record(argparse.Namespace(project=str(root), ladder=0, gate=None,
                                           role=None, wave=None, model=None))
    finally:
        sys.stderr = saved_err
    cases.append(("refuses to record without a ledger row", rc == 2))

    add_ledger_row(2, "architect", "ok", 240000, 20000, 1.7)
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))
    add_ledger_row(3, "backend", "failed", 120000, 8000, 0.8, task="T-001")
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))
    add_ledger_row(3, "backend", "ok", 300000, 30000, 2.25, task="T-001")
    # identity guard: claiming the wrong role must not record
    saved_err, sys.stderr = sys.stderr, io.StringIO()
    rc = cmd_record(argparse.Namespace(project=str(root), ladder=1, gate=None,
                                       role="qa", wave=None, model=None))
    sys.stderr = saved_err
    cases.append(("identity guard rejects a mismatched --role", rc == 2))
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=1,
                                                      gate=None, role=None, wave=None, model=None))
    # a QA failure sends wave 4 back to wave 3: the loop must be counted
    add_ledger_row(4, "qa", "failed", 40000, 5000, 0.3)
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))
    add_ledger_row(3, "backend", "ok", 90000, 9000, 0.6, task="T-001")
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))

    rc, out = quiet(lambda a: cmd_report(a), argparse.Namespace(project=str(root), json=True))
    rep = json.loads(out)
    cases += [
        ("counts runs, ok, and failed from the ledger's statuses",
         rep["runs"] == 5 and rep["ok"] == 3 and rep["failed"] == 2),
        ("ladder retries counted separately", rep["ladder_retries"] == 1),
        ("a wave-4 -> wave-3 return counts as one rework loop", rep["rework_loops"] == 1),
        ("keeps per-role medians and retry counts",
         rep["by_role"]["backend"]["runs"] == 3
         and rep["by_role"]["backend"]["ladder_retries"] == 1
         and rep["by_role"]["backend"]["median_tokens"] == 128000),
        ("by_model slice carries ok_rate per model (L-13)",
         rep["by_model"]["claude-opus-5"]["runs"] == 5
         and rep["by_model"]["claude-opus-5"]["ok_rate"] == 0.6),
        ("single rework loop keeps the decision on continue",
         rep["decision"] == "continue"),
        ("report always exits 0 (informational, not a gate)", rc == 0),
    ]

    # a SECOND wave-4 -> wave-3 return: the ladder has done its job twice and
    # failed twice; the decision must flip to replan (L-4)
    add_ledger_row(4, "qa", "failed", 40000, 5000, 0.3)
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))
    add_ledger_row(3, "backend", "ok", 90000, 9000, 0.6, task="T-001")
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))
    rc, out = quiet(lambda a: cmd_report(a), argparse.Namespace(project=str(root), json=True))
    rep2 = json.loads(out)
    cases += [
        ("two rework loops flips the decision to replan (L-4)",
         rep2["rework_loops"] == 2 and rep2["decision"] == "replan"),
    ]

    # a THIRD return: the replan failed to break the loop - escalate to the user
    add_ledger_row(4, "qa", "failed", 40000, 5000, 0.3)
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))
    add_ledger_row(3, "backend", "ok", 90000, 9000, 0.6, task="T-001")
    quiet(lambda a: cmd_record(a), argparse.Namespace(project=str(root), ladder=0,
                                                      gate=None, role=None, wave=None, model=None))
    rc, out = quiet(lambda a: cmd_report(a), argparse.Namespace(project=str(root), json=True))
    rep3 = json.loads(out)
    cases += [
        ("three rework loops escalates to the user",
         rep3["rework_loops"] == 3 and rep3["decision"] == "escalate"),
    ]

    for label, cond in cases:
        print("   %s %s" % ("[OK]  " if cond else "[FAIL]", label))
        ok = ok and cond
    print("SELFTEST PASS" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="PMOS wave-event trace")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record", help="append the newest ledger row as a wave event")
    p.add_argument("--project", default=".")
    p.add_argument("--ladder", type=int, default=0,
                   help="fallback-ladder index used for this run (0 = first attempt)")
    p.add_argument("--gate", default=None, help="optional annotation: gate1|gate2")
    p.add_argument("--role", default=None, help="must match the newest ledger row")
    p.add_argument("--wave", type=int, default=None, help="must match the newest ledger row")
    p.add_argument("--model", default=None, help="must match the newest ledger row")

    p = sub.add_parser("report", help="aggregate the trace: ok/fail, retries, rework loops")
    p.add_argument("--project", default=".")
    p.add_argument("--json", action="store_true")

    sub.add_parser("selftest")

    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    return {"record": cmd_record, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
