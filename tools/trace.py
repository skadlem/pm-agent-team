#!/usr/bin/env python3
"""PMOS traceability: join the project graph to the code graph and query it.

`artifacts.py` gives the project half (requirement -> task -> criterion -> risk,
from .pmos/ ids). graphify gives the code half (graphify-out/graph.json). The
join is a task's `touches:` paths, and it answers the questions the coordinator
otherwise asks an agent to answer by re-reading prose:

    python tools/trace.py coverage  --project .      # scope -> task -> criterion -> QA
    python tools/trace.py impact T-012 --project .   # everything that rides on one item
    python tools/trace.py unplanned --project .      # changed code no task claims
    python tools/trace.py export --project . --out .pmos/traceability.json
    python tools/trace.py selftest

Every subcommand takes --json. Exit code 1 when a query finds nothing to report
on (unknown id), 0 otherwise: gaps are reported, not failed on - that judgement
belongs to the gate, and `artifacts.py --strict` is what enforces it.
"""
import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artifacts  # noqa: E402  (sibling tool: parsing + lint live there)

CODE_TYPES = ("code",)


def load_project(proj):
    entities, problems, qa, present = artifacts.parse_project(proj)
    by_id, edges = artifacts.check(entities, problems, qa, present)
    return by_id, edges, qa, problems


def load_code_graph(proj):
    """File-level view of the graphify graph: which files exist, and which file
    references which. Symbol-level detail stays in graphify; here a file is the
    unit a task can plausibly claim."""
    path = Path(proj) / "graphify-out" / "graph.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    node_file, files = {}, {}
    for n in raw.get("nodes", []):
        src = n.get("source_file")
        if not src:
            continue
        node_file[n.get("id")] = src
        f = files.setdefault(src, {"file": src, "symbols": 0, "kind": n.get("file_type", "")})
        f["symbols"] += 1
        if n.get("community_name") and "community" not in f:
            f["community"] = n["community_name"]
    refs = {}
    for l in raw.get("links", []):
        a, b = node_file.get(l.get("source")), node_file.get(l.get("target"))
        if not a or not b or a == b:
            continue
        refs.setdefault(b, set()).add((a, l.get("relation", "references")))
    return {"files": files, "referenced_by": refs, "commit": raw.get("built_at_commit", "")}


def match_touches(touch, files):
    """A `touches:` entry claims a file, a directory, or a glob of them."""
    touch = touch.strip().rstrip("/")
    if not touch:
        return []
    hits = [f for f in files if f == touch
            or f.startswith(touch + "/")
            or fnmatch.fnmatch(f, touch)]
    return sorted(hits)


def task_touches(entity):
    return artifacts.split_refs(entity.fields.get("touches", ""))


def join(by_id, code):
    """task id -> claimed files, and file -> the tasks claiming it."""
    claimed, by_file = {}, {}
    files = list(code["files"]) if code else []
    for e in by_id.values():
        if e.kind != "task":
            continue
        hits = []
        for t in task_touches(e):
            hits.extend(match_touches(t, files) if files else [t])
        claimed[e.id] = sorted(set(hits))
        for f in claimed[e.id]:
            by_file.setdefault(f, []).append(e.id)
    return claimed, by_file


def outgoing(edges, src, kind):
    return [e["dst"] for e in edges if e["src"] == src and e["kind"] == kind]


def incoming(edges, dst, kind):
    return [e["src"] for e in edges if e["dst"] == dst and e["kind"] == kind]


def title_of(by_id, eid):
    e = by_id.get(eid)
    return e.title if e and e.title else ""


def cmd_coverage(by_id, edges, qa, code, args):
    reqs = sorted([e for e in by_id.values() if e.kind == "requirement"], key=lambda e: e.id)
    tasks = sorted([e for e in by_id.values() if e.kind == "task"], key=lambda e: e.id)
    claimed, _ = join(by_id, code)
    rows, gaps = [], []
    planned = 0
    for r in reqs:
        ts = sorted(incoming(edges, r.id, "satisfies"))
        if ts:
            planned += 1
        else:
            gaps.append("%s is in scope but no task satisfies it" % r.id)
        row = {"id": r.id, "title": r.title, "tasks": []}
        for tid in ts:
            crits = sorted(incoming(edges, tid, "verifies"))
            if not crits:
                gaps.append("%s has no acceptance criterion" % tid)
            row["tasks"].append({
                "id": tid, "title": title_of(by_id, tid),
                "role": by_id[tid].fields.get("role", ""),
                "files": claimed.get(tid, []),
                "criteria": [{"id": c, "title": title_of(by_id, c),
                              "qa": qa.get(c, {}).get("result", "")} for c in crits]})
        rows.append(row)
    verified = sum(1 for t in tasks if incoming(edges, t.id, "verifies"))
    reported = sum(1 for e in by_id.values() if e.kind == "acceptance" and e.id in qa)
    crit_total = sum(1 for e in by_id.values() if e.kind == "acceptance")
    for c in sorted(e.id for e in by_id.values() if e.kind == "acceptance"):
        if qa and c not in qa:
            gaps.append("%s has no QA result" % c)
    summary = {"requirements": len(reqs), "planned": planned, "tasks": len(tasks),
               "verified": verified, "criteria": crit_total, "reported": reported,
               "passing": sum(1 for c, v in qa.items() if v["result"] == "pass")}
    if args.json:
        print(json.dumps({"summary": summary, "requirements": rows, "gaps": gaps}, indent=1))
        return 0
    for row in rows:
        print("%s  %s" % (row["id"], row["title"]))
        if not row["tasks"]:
            print("    (nothing planned)")
        for t in row["tasks"]:
            print("    %s  %s%s" % (t["id"], t["title"],
                                    ("  [%s]" % t["role"]) if t["role"] else ""))
            if t["files"]:
                print("        touches: %s" % ", ".join(t["files"][:4])
                      + (" (+%d)" % (len(t["files"]) - 4) if len(t["files"]) > 4 else ""))
            if not t["criteria"]:
                print("        (no acceptance criterion)")
            for c in t["criteria"]:
                mark = {"pass": "PASS", "fail": "FAIL", "blocked": "BLOCKED"}.get(c["qa"], "not reported")
                print("        %s  %-44s %s" % (c["id"], c["title"][:44], mark))
    print()
    print("%d/%d requirements planned | %d/%d tasks verified | %d/%d criteria reported, %d passing"
          % (summary["planned"], summary["requirements"], summary["verified"], summary["tasks"],
             summary["reported"], summary["criteria"], summary["passing"]))
    for g in gaps:
        print("  gap: %s" % g)
    return 0


def cmd_impact(by_id, edges, qa, code, args):
    eid = artifacts.canonical(args.id) or args.id.upper()
    e = by_id.get(eid)
    if e is None:
        print("no artifact with id %s (known: %s)"
              % (eid, ", ".join(sorted(by_id)[:12]) or "none"), file=sys.stderr)
        return 1
    claimed, by_file = join(by_id, code)
    out = {"id": e.id, "kind": e.kind, "title": e.title, "file": "%s:%d" % (e.file, e.line)}

    if e.kind == "task":
        out["satisfies"] = [{"id": r, "title": title_of(by_id, r)} for r in outgoing(edges, e.id, "satisfies")]
        out["decided_by"] = [{"id": a, "title": title_of(by_id, a)} for a in outgoing(edges, e.id, "decided_by")]
        out["depends_on"] = sorted(outgoing(edges, e.id, "depends_on"))
        out["verified_by"] = [{"id": c, "title": title_of(by_id, c),
                               "qa": qa.get(c, {}).get("result", "")}
                              for c in sorted(incoming(edges, e.id, "verifies"))]
        out["risks"] = [{"id": r, "severity": by_id[r].fields.get("severity", ""),
                         "status": by_id[r].fields.get("status", "")}
                        for r in sorted(incoming(edges, e.id, "mitigated_by"))]
        # transitive blast radius through the task graph
        blocked, frontier = [], [e.id]
        while frontier:
            nxt = []
            for t in frontier:
                for d in incoming(edges, t, "depends_on"):
                    if d not in blocked and d != e.id:
                        blocked.append(d)
                        nxt.append(d)
            frontier = nxt
        out["blocks"] = sorted(blocked)
        out["touches"] = claimed.get(e.id, [])
        if code:
            reach = []
            for f in out["touches"]:
                for other, rel in sorted(code["referenced_by"].get(f, [])):
                    reach.append({"file": other, "relation": rel, "via": f})
            out["referenced_by"] = reach
            out["also_claimed_by"] = sorted({t for f in out["touches"]
                                             for t in by_file.get(f, []) if t != e.id})
    elif e.kind == "requirement":
        out["tasks"] = sorted(incoming(edges, e.id, "satisfies"))
        out["criteria"] = sorted({c for t in out["tasks"] for c in incoming(edges, t, "verifies")})
        out["qa"] = {c: qa.get(c, {}).get("result", "not reported") for c in out["criteria"]}
        out["touches"] = sorted({f for t in out["tasks"] for f in claimed.get(t, [])})
    elif e.kind == "risk":
        out["severity"] = e.fields.get("severity", "")
        out["status"] = e.fields.get("status", "")
        out["mitigated_by"] = sorted(outgoing(edges, e.id, "mitigated_by"))
        out["evidence"] = [{"task": t, "criterion": c, "qa": qa.get(c, {}).get("result", "not reported")}
                           for t in out["mitigated_by"] for c in sorted(incoming(edges, t, "verifies"))]
        out["touches"] = sorted({f for t in out["mitigated_by"] for f in claimed.get(t, [])})
    elif e.kind == "decision":
        out["status"] = e.fields.get("status", "")
        out["supersedes"] = sorted(outgoing(edges, e.id, "supersedes"))
        out["superseded_by"] = sorted(incoming(edges, e.id, "supersedes"))
        out["constrains"] = sorted(incoming(edges, e.id, "decided_by"))
        out["touches"] = sorted({f for t in out["constrains"] for f in claimed.get(t, [])})
    elif e.kind == "acceptance":
        out["verifies"] = sorted(outgoing(edges, e.id, "verifies"))
        out["qa"] = qa.get(e.id, {}).get("result", "not reported")
        out["evidence"] = qa.get(e.id, {}).get("evidence", "")

    if args.json:
        print(json.dumps(out, indent=1))
        return 0
    print("%s  %s%s" % (out["id"], out["title"], "  [%s]" % e.fields.get("role") if e.fields.get("role") else ""))
    print("  defined in     %s" % out["file"])
    order = ["satisfies", "decided_by", "depends_on", "verified_by", "verifies", "constrains",
             "supersedes", "superseded_by", "blocks", "risks", "mitigated_by", "evidence",
             "tasks", "criteria", "qa", "touches", "referenced_by", "also_claimed_by", "status",
             "severity"]
    for key in order:
        if key not in out or not out[key]:
            continue
        val = out[key]
        if isinstance(val, str):
            print("  %-14s %s" % (key, val))
        elif isinstance(val, dict):
            print("  %-14s %s" % (key, ", ".join("%s: %s" % kv for kv in sorted(val.items()))))
        else:
            parts = []
            for v in val:
                if isinstance(v, dict):
                    label = v.get("id") or v.get("file") or v.get("task") or ""
                    extra = v.get("qa") or v.get("status") or v.get("relation") or ""
                    if v.get("criterion"):
                        label = "%s via %s" % (v["criterion"], v["task"])
                    elif v.get("title"):
                        label = "%s %s" % (label, v["title"][:52])
                    parts.append("%s%s" % (label, " (%s)" % extra if extra else ""))
                else:
                    parts.append(str(v))
            print("  %-14s %s" % (key, ", ".join(parts)))
    return 0


def changed_files(proj, since):
    """Files this branch touched: working tree + index vs `since` (default HEAD)."""
    cmds = [["git", "diff", "--name-only", since], ["git", "diff", "--name-only", "--cached"],
            ["git", "ls-files", "--others", "--exclude-standard"]]
    out = set()
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=str(proj), capture_output=True, text=True)
        if r.returncode == 0:
            out.update(l.strip() for l in r.stdout.splitlines() if l.strip())
    # .pmos/ and graphify-out/ are the system's own generated state, not project work
    return sorted(f for f in out
                  if not f.startswith(".pmos/") and not f.startswith("graphify-out/"))


def cmd_unplanned(by_id, edges, qa, code, args):
    proj = Path(args.project)
    claimed, by_file = join(by_id, code)
    changed = changed_files(proj, args.since)
    rows = []
    for f in changed:
        owners = by_file.get(f, [])
        if owners:
            continue
        near = sorted({tid for tid, files in claimed.items()
                       for c in files if c and (f.startswith(c.rstrip("/") + "/") or
                                                os.path.dirname(f) == os.path.dirname(c))})
        rows.append({"file": f, "nearest_tasks": near})
    covered = len(changed) - len(rows)
    if args.json:
        print(json.dumps({"since": args.since, "changed": len(changed), "claimed": covered,
                          "unplanned": rows}, indent=1))
        return 0
    print("changed since %s: %d file(s), %d claimed by a task" % (args.since, len(changed), covered))
    if not rows:
        print("every changed file is claimed by a plan task")
        return 0
    for r in rows:
        hint = ("  nearest: " + ", ".join(r["nearest_tasks"])) if r["nearest_tasks"] else ""
        print("  unplanned  %s%s" % (r["file"], hint))
    print("\n%d changed file(s) no task claims. Either add them to a task's `touches:`,"
          "\nor plan the work before it ships." % len(rows))
    return 0


def cmd_export(by_id, edges, qa, code, args):
    graph = artifacts.build_graph(by_id, edges, qa)
    claimed, _ = join(by_id, code)
    seen = {n["id"] for n in graph["nodes"]}
    for tid, files in sorted(claimed.items()):
        for f in files:
            node_id = "file:" + f
            if node_id not in seen:
                meta = (code or {}).get("files", {}).get(f, {})
                graph["nodes"].append({"id": node_id, "kind": "file", "title": f, "file": f,
                                       "symbols": meta.get("symbols", 0),
                                       "community": meta.get("community", "")})
                seen.add(node_id)
            graph["edges"].append({"src": tid, "dst": node_id, "kind": "touches"})
    graph["code_graph"] = {"present": bool(code),
                           "commit": (code or {}).get("commit", ""),
                           "files": len((code or {}).get("files", {}))}
    text = json.dumps(graph, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print("wrote %s: %d nodes, %d edges (%d file node(s))"
              % (args.out, len(graph["nodes"]), len(graph["edges"]),
                 sum(1 for n in graph["nodes"] if n["kind"] == "file")))
    else:
        print(text)
    return 0


FIXTURE = {
    ".pmos/charter.md": "# C\n### In scope (this project)\n"
                        "- R-001: users can reset their own password\n"
                        "- R-002: sessions expire after 30 minutes\n",
    ".pmos/plans/plan.md": """```yaml
- id: T-001
  title: password reset endpoint
  role: backend
  satisfies: R-001
  touches: src/auth
- id: T-002
  title: session expiry
  role: backend
  satisfies: R-002
  depends_on: T-001
  touches: src/session.py
- id: A-001
  title: reset mail arrives and the new password works
  verifies: T-001
- id: A-002
  title: a 31 minute old session is rejected
  verifies: T-002
```
""",
    ".pmos/out/legal/risk-register.md": """```yaml
- id: L-001
  risk: reset token stays valid after use
  severity: high
  status: mitigated
  mitigated_by: T-001
```
""",
    ".pmos/out/qa/test-report.md": "- A-001: pass - 12 tests green\n- A-002: pass - expiry suite green\n",
    "graphify-out/graph.json": json.dumps({
        "nodes": [
            {"id": "src_auth_reset", "label": "reset.py", "source_file": "src/auth/reset.py",
             "file_type": "code", "community_name": "auth"},
            {"id": "src_auth_mail", "label": "mail.py", "source_file": "src/auth/mail.py",
             "file_type": "code", "community_name": "auth"},
            {"id": "src_session", "label": "session.py", "source_file": "src/session.py",
             "file_type": "code", "community_name": "core"},
            {"id": "src_api", "label": "api.py", "source_file": "src/api.py",
             "file_type": "code", "community_name": "core"}],
        "links": [{"source": "src_api", "target": "src_auth_reset", "relation": "imports"}],
        "built_at_commit": "deadbeef"}),
}


def selftest():
    import tempfile
    ok = True
    root = Path(tempfile.mkdtemp())
    for rel, body in FIXTURE.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    by_id, edges, qa, problems = load_project(root)
    code = load_code_graph(root)
    assert code and len(code["files"]) == 4, "code graph not loaded"
    claimed, by_file = join(by_id, code)

    cases = [
        ("directory touch expands to files",
         claimed["T-001"] == ["src/auth/mail.py", "src/auth/reset.py"]),
        ("file touch resolves", claimed["T-002"] == ["src/session.py"]),
        ("reverse index maps file to task", by_file["src/auth/reset.py"] == ["T-001"]),
    ]

    args = argparse.Namespace(json=True, project=str(root), id="T-001", since="HEAD", out=None)
    import io

    def capture(fn, *a):
        sys.stdout = io.StringIO()
        try:
            fn(*a)
            return json.loads(sys.stdout.getvalue())
        finally:
            sys.stdout = sys.__stdout__

    impact = capture(cmd_impact, by_id, edges, qa, code, args)
    cov = capture(cmd_coverage, by_id, edges, qa, code, args)

    cases += [
        ("impact reaches the requirement", impact["satisfies"][0]["id"] == "R-001"),
        ("impact reaches QA result", impact["verified_by"][0]["qa"] == "pass"),
        ("impact lists the risk riding on it", impact["risks"][0]["id"] == "L-001"),
        ("impact finds transitively blocked work", impact["blocks"] == ["T-002"]),
        ("impact reports code that imports the touched file",
         any(r["file"] == "src/api.py" for r in impact["referenced_by"])),
        ("coverage counts planned scope", cov["summary"] == {
            "requirements": 2, "planned": 2, "tasks": 2, "verified": 2,
            "criteria": 2, "reported": 2, "passing": 2}),
        ("coverage reports no gaps on a complete project", cov["gaps"] == []),
    ]

    # a requirement nobody planned must show up as a gap
    (root / ".pmos" / "charter.md").write_text(
        (root / ".pmos" / "charter.md").read_text(encoding="utf-8") + "- R-003: audit log\n",
        encoding="utf-8")
    by_id2, edges2, qa2, _ = load_project(root)
    cov2 = capture(cmd_coverage, by_id2, edges2, qa2, code, args)
    cases.append(("unplanned scope becomes a gap",
                  any("R-003" in g for g in cov2["gaps"]) and cov2["summary"]["planned"] == 2))

    # unplanned: a changed file no task claims
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True)
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "billing.py").write_text("# not in any task\n", encoding="utf-8")
    (root / "src" / "session.py").write_text("# claimed by T-002\n", encoding="utf-8")
    unp = capture(cmd_unplanned, by_id, edges, qa, code, args)
    flagged = {r["file"] for r in unp["unplanned"]}
    cases.append(("unclaimed changed file is flagged", "src/billing.py" in flagged))
    cases.append(("claimed changed file is not flagged", "src/session.py" not in flagged))
    cases.append(("nearest task is suggested",
                  any(r["file"] == "src/billing.py" and r["nearest_tasks"] == ["T-002"]
                      for r in unp["unplanned"])))

    # export: code files become nodes joined by touches edges
    out = root / "trace.json"
    args.out = str(out)
    sys.stdout = io.StringIO()          # export prints a summary; the file is what we assert on
    try:
        cmd_export(by_id, edges, qa, code, args)
    finally:
        sys.stdout = sys.__stdout__
    g = json.loads(out.read_text(encoding="utf-8"))
    file_nodes = [n for n in g["nodes"] if n["kind"] == "file"]
    cases.append(("export adds file nodes", len(file_nodes) == 3))
    cases.append(("export links tasks to files",
                  {"src": "T-001", "dst": "file:src/auth/reset.py", "kind": "touches"} in g["edges"]))
    cases.append(("export records the code graph commit", g["code_graph"]["commit"] == "deadbeef"))

    # no graphify graph: touches stay literal instead of crashing
    (root / "graphify-out" / "graph.json").unlink()
    claimed3, _ = join(load_project(root)[0], load_code_graph(root))
    cases.append(("works without a code graph", claimed3["T-002"] == ["src/session.py"]))

    for label, cond in cases:
        print("   %s %s" % ("[OK]  " if cond else "[FAIL]", label))
        ok = ok and cond
    print("SELFTEST PASS" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="PMOS traceability queries")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--project", default=".")
        p.add_argument("--json", action="store_true")

    common(sub.add_parser("coverage", help="requirement -> task -> criterion -> QA, with gaps"))
    p = sub.add_parser("impact", help="everything that rides on one id")
    p.add_argument("id")
    common(p)
    p = sub.add_parser("unplanned", help="changed code no task claims")
    common(p)
    p.add_argument("--since", default="HEAD")
    p = sub.add_parser("export", help="write the joined project+code graph")
    common(p)
    p.add_argument("--out", default=None)
    sub.add_parser("selftest")

    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    if not (Path(args.project) / ".pmos").is_dir():
        print("no .pmos/ in %s: nothing to trace" % args.project, file=sys.stderr)
        return 1
    by_id, edges, qa, _ = load_project(args.project)
    code = load_code_graph(args.project)
    if not hasattr(args, "since"):
        args.since = "HEAD"
    if not hasattr(args, "out"):
        args.out = None
    return {"coverage": cmd_coverage, "impact": cmd_impact,
            "unplanned": cmd_unplanned, "export": cmd_export}[args.cmd](by_id, edges, qa, code, args)


if __name__ == "__main__":
    sys.exit(main())
