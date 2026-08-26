#!/usr/bin/env python3
"""Task complexity analysis at GATE 2 prep (Task Master's analyze-complexity, made
deterministic).

Scores every plan task on three measurable axes and flags the ones that should be
split into subtasks BEFORE implementation burns a worker spawn on them:

- dependency depth:  longest depends_on chain ending at this task
- touches breadth:   number of distinct top-level paths the task claims
- criterion load:    acceptance criteria verifying this task (a task with many
                     criteria promises many things)

Each axis is normalized 0..1 against the plan's own max, then averaged. Tasks in
the top band are flagged `consider splitting`; the report is advisory (exit 0)
-- the GATE 2 reviewer decides.

Usage:
    python tools/complexity.py --project .
    python tools/complexity.py --project . --json --threshold 0.7

Deterministic and offline: no model is spawned.
"""
import argparse
import json
import sys
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TPL / "tools"))
from artifacts import parse_project


def depth_of(task, tasks_by_id, memo):
    """Longest depends_on chain ending at this task (1 if none)."""
    if task.id in memo:
        return memo[task.id]
    deps = task.refs.get("depends_on", [])
    best = 1 + max((depth_of(tasks_by_id[d], tasks_by_id, memo)
                    for d in deps if d in tasks_by_id), default=0)
    memo[task.id] = best
    return best


def touches_count(task):
    """Distinct top-level directories/files claimed."""
    raw = task.fields.get("touches", "")
    return len({p.strip().split("/")[0] for p in raw.split(",") if p.strip()})


def analyze(entities):
    tasks = {e.id: e for e in entities if e.kind == "task"}
    criteria = [e for e in entities if e.kind == "acceptance"]
    crit_load = {}
    for c in criteria:
        for t in c.refs.get("verifies", []):
            crit_load[t] = crit_load.get(t, 0) + 1

    memo = {}
    rows = []
    for tid, t in sorted(tasks.items()):
        rows.append({
            "id": tid,
            "title": t.title,
            "role": t.fields.get("role", ""),
            "dep_depth": depth_of(t, tasks, memo),
            "touches": touches_count(t),
            "criteria": crit_load.get(tid, 0),
        })

    # absolute floors first (a 2-task plan should not flag both tasks just for
    # being the plan's biggest), then normalize within what remains
    ABS = {"dep_depth": 3, "touches": 2, "criteria": 3}
    for r in rows:
        # each axis: base contribution up to its absolute floor, then a rising
        # penalty for how far past the floor it is (overload is the smell)
        def axis(v, floor, w):
            base = w if v >= floor else w * v / floor
            over = max(0, v - floor) / floor
            return base + w * min(over, 1.0)
        score = (axis(r["dep_depth"], ABS["dep_depth"], 0.4) +
                 axis(r["touches"], ABS["touches"], 0.3) +
                 axis(r["criteria"], ABS["criteria"], 0.3))
        r["score"] = round(min(score, 1.0), 3)
    return rows


def main():
    ap = argparse.ArgumentParser(description="task complexity analysis (GATE 2 prep)")
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="score above which splitting is recommended (0..1)")
    a = ap.parse_args()

    entities, _problems, _qa, _present = parse_project(a.project)
    rows = analyze(entities)
    flagged = [r for r in rows if r["score"] >= a.threshold]
    out = {"tasks": rows, "flagged": [r["id"] for r in flagged],
           "threshold": a.threshold}
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        if not rows:
            print("no tasks found under .pmos/plans/plan.md")
            return 0
        print("%-8s %-6s %-5s %-5s %-5s  %s" % ("TASK", "SCORE", "DEP", "TCH", "CRT", "TITLE"))
        for r in sorted(rows, key=lambda r: -r["score"]):
            flag = " <-- consider splitting" if r["id"] in out["flagged"] else ""
            print("%-8s %-6s %-5s %-5s %-5s  %s%s"
                  % (r["id"], "%.2f" % r["score"], r["dep_depth"], r["touches"],
                     r["criteria"], (r["title"] or "")[:48], flag))
        if not flagged:
            print("no task scores above %.2f - plan granularity looks fine" % a.threshold)
    return 0


if __name__ == "__main__":
    sys.exit(main())
