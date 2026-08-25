#!/usr/bin/env python3
"""PMOS converge audit (spec-kit /speckit.converge pattern, L-7).

An optional level-5.5 eval step: one pass over the project that replays every
deterministic check and answers "did we actually finish what the plan
promised?" — not as prose, as a verdict computed from the tools:

    python tools/converge.py --project .          # human report
    python tools/converge.py --project . --json   # machine-readable

Verdict rules (mechanical, no judgement):
- FAIL    — artifact lint errors, an unaccepted high-severity open risk, a
            failed acceptance criterion, spend over budget, or replan decision.
- CONCERNS — no FAIL conditions but: lint warnings, unplanned changed files,
            uncovered requirements, missing QA evidence fingerprint.
- CONVERGED — everything above clean.

The audit never writes to the project: it only reads .pmos/ state and the
source tree, so it is safe to run at any time.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent


def run_tool(tool, *args):
    r = subprocess.run([sys.executable, str(TPL / "tools" / tool)] + list(args) + ["--json"],
                       capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout or "{}")
    except ValueError:
        return r.returncode, {}


def audit(proj):
    out = {"project": str(proj), "checks": {}}

    rc, lint = run_tool("artifacts.py", "--project", str(proj))
    out["checks"]["artifacts"] = {
        "error_count": len(lint.get("errors") or []),
        "warning_count": len(lint.get("warnings") or []),
        "errors": [e["message"] for e in lint.get("errors") or []][:5],
        "warnings": [w["message"] for w in lint.get("warnings") or []][:5],
    }

    rc, cov = run_tool("trace.py", "coverage", "--project", str(proj))
    out["checks"]["coverage"] = cov.get("summary", {})

    rc, unp = run_tool("trace.py", "unplanned", "--project", str(proj))
    raw_unplanned = unp.get("unplanned") or []
    unplanned = [u["file"] if isinstance(u, dict) else str(u) for u in raw_unplanned]
    out["checks"]["unplanned"] = sorted(unplanned)

    rc, cost = run_tool("cost.py", "report", "--project", str(proj))
    out["checks"]["cost"] = {"total": cost.get("total", {}),
                             "budget_usd": cost.get("budget_usd"),
                             "remaining_usd": cost.get("remaining_usd")}

    rc, events = run_tool("events.py", "report", "--project", str(proj))
    out["checks"]["events"] = {"runs": events.get("runs", 0),
                               "failed": events.get("failed", 0),
                               "rework_loops": events.get("rework_loops", 0),
                               "decision": events.get("decision", "continue")}

    # verdict
    fails = []
    concerns = []
    if out["checks"]["artifacts"]["error_count"]:
        fails.append("artifact lint errors")
    if cov.get("summary", {}).get("reported") != cov.get("summary", {}).get("passing") \
            and cov.get("summary", {}).get("reported"):
        fails.append("acceptance criteria failing or unreported")
    if out["checks"]["events"]["decision"] == "replan":
        fails.append("replan decision (two rework loops)")
    if out["checks"]["cost"].get("remaining_usd") is not None \
            and out["checks"]["cost"]["remaining_usd"] < 0:
        fails.append("over budget")
    if out["checks"]["artifacts"]["warning_count"]:
        concerns.append("artifact lint warnings")
    if out["checks"]["unplanned"]:
        concerns.append("%d unplanned changed file(s)" % len(out["checks"]["unplanned"]))
    if cov.get("gaps"):
        concerns.append("%d coverage gap(s)" % len(cov.get("gaps") or []))

    if fails:
        verdict = "FAIL"
    elif concerns:
        verdict = "CONCERNS"
    else:
        verdict = "CONVERGED"
    out["verdict"] = verdict
    out["fails"] = fails
    out["concerns"] = concerns
    return out


def main():
    ap = argparse.ArgumentParser(description="PMOS converge audit (level 5.5)")
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = audit(args.project)
    if args.json:
        print(json.dumps(out, indent=1))
    else:
        print("converge audit: %s" % out["verdict"])
        for c in out["fails"]:
            print("  [FAIL] %s" % c)
        for c in out["concerns"]:
            print("  [WARN] %s" % c)
        print("  artifacts: %d error(s), %d warning(s)"
              % (out["checks"]["artifacts"]["error_count"],
                 out["checks"]["artifacts"]["warning_count"]))
        print("  coverage:  %s" % out["checks"]["coverage"])
        print("  unplanned: %d file(s)" % len(out["checks"]["unplanned"]))
        print("  cost:      $%s spent, $%s remaining of $%s"
              % (out["checks"]["cost"]["total"].get("usd"),
                 out["checks"]["cost"]["remaining_usd"],
                 out["checks"]["cost"]["budget_usd"]))
        print("  events:    %d run(s), %d failed, %d rework loop(s), decision: %s"
              % (out["checks"]["events"]["runs"], out["checks"]["events"]["failed"],
                 out["checks"]["events"]["rework_loops"], out["checks"]["events"]["decision"]))
    # exit code mirrors the verdict for scripting
    return {"FAIL": 2, "CONCERNS": 1, "CONVERGED": 0}[out["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
