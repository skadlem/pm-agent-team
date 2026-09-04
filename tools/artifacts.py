#!/usr/bin/env python3
"""PMOS artifact linter: stable ids and the references between them.

The waves hand work to each other as markdown. Without ids that means every
cross-artifact check ("is this requirement planned?", "is that mitigated risk
actually delivered?") is done by an agent re-reading prose. This tool makes the
same checks mechanical, and emits the node/edge list a traceability graph needs.

    python tools/artifacts.py --project .          # human report
    python tools/artifacts.py --project . --json    # machine-readable
    python tools/artifacts.py --project . --strict  # warnings fail too
    python tools/artifacts.py --project . --graph .pmos/traceability.json
    python tools/artifacts.py selftest              # fixture-based self-check

Exit code: 1 if any ERROR (2 with --strict when only warnings). Entities and
their reference fields are specified in ARTIFACT-SCHEMA.md.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# entity kind -> (id prefix, where it is defined)
KINDS = {
    "requirement": "R",
    "task": "T",
    "acceptance": "A",
    "decision": "ADR",
    "risk": "L",
}
PREFIX_KIND = {v: k for k, v in KINDS.items()}

# reference field -> (kind of the entity carrying it, kind it must point at)
REF_FIELDS = {
    "satisfies": ("task", "requirement"),
    "depends_on": ("task", "task"),
    "decided_by": ("task", "decision"),
    "verifies": ("acceptance", "task"),
    "mitigated_by": ("risk", "task"),
    "supersedes": ("decision", "decision"),
}

ID_TOKEN = re.compile(r"^(R|T|A|ADR|L)-(\d{1,4})$", re.I)
DEF_LINE = re.compile(r"^\s*[-*]\s+id:\s*([A-Za-z]+-\d{1,4})\s*$", re.I)
FIELD_LINE = re.compile(r"^\s+([a-z_]+):\s*(.*?)\s*$")
REQ_LINE = re.compile(r"^\s*[-*]\s+(R-\d{1,4})\s*[:\-]\s*(.+)$", re.I)
ADR_HEAD = re.compile(r"^#\s*(ADR-\d{1,4})\s*[:\-]?\s*(.*)$", re.I)
# QA reports come in two shapes and from two places. The expensive roster's QA
# writes out/qa/test-report.md, the lean roster's reviewer writes
# out/reviewer/test-report.md; both write either a list ("- A-001: pass - green")
# or a table row ("| A-001 title | PASS | evidence |"). Reading only one shape
# from one path is why suited's 33 reported criteria all counted as unreported.
_QA_STATUS = (r"(pass(?:ed)?|fail(?:ed|s)?|blocked|partial|n/?a|"
              r"not[- ]applicable|skipp?e?d?)")
QA_RESULT = re.compile(r"^\s*[-*]\s+(A-\d{1,4})\s*[:\-]\s*\**" + _QA_STATUS +
                       r"\**\b[\s:\-]*(.*)$", re.I)
QA_TABLE_ROW = re.compile(r"^\s*\|\s*(A-\d{1,4})\b[^|]*\|\s*\**" + _QA_STATUS +
                          r"\**[^|]*\|(.*)$", re.I)
# Only `pass` verifies a criterion. `n/a` and `partial` are REPORTED but not
# verified, which is a different (and quieter) finding than never reporting.
QA_NORMALIZE = {"pass": "pass", "passed": "pass",
                "fail": "fail", "failed": "fail", "fails": "fail",
                "blocked": "blocked", "partial": "partial"}
QA_BLOCKING = ("fail", "blocked")


def qa_status(token):
    """Normalize a status cell to the result vocabulary, or None if unknown."""
    t = token.strip().lower().replace("_", "-")
    if t in QA_NORMALIZE:
        return QA_NORMALIZE[t]
    if t.startswith("skip") or t in ("n/a", "na") or t.replace(" ", "-") == "not-applicable":
        return "n/a"
    return None


def parse_qa_line(line):
    """(id, result, evidence) for a QA line in either shape, else None."""
    for rx, ev_group in ((QA_RESULT, 3), (QA_TABLE_ROW, 3)):
        m = rx.match(line)
        if not m:
            continue
        result = qa_status(m.group(2))
        if result is None:
            continue
        return m.group(1), result, m.group(ev_group).strip().strip("|").strip()
    return None


def qa_report_paths(pmos):
    """Every QA report on disk: both rosters' locations, plus per-phase siblings
    (test-report-phase1.md). Sorted so the output is deterministic."""
    found = []
    for role in ("qa", "reviewer"):
        d = pmos / "out" / role
        if d.is_dir():
            found += sorted(f for f in d.glob("test-report*.md") if f.is_file())
    return found
QA_TREE = re.compile(r"^\s*(?:tree|Tree)\s*:\s*([0-9a-fA-F]{16,64})\s*$")
ADR_STATUS = re.compile(r"^\s*(?:status|Status)\s*:\s*([a-z\- ]+)", re.M)

# Fingerprinting skips protocol state and generated graphs: evidence is about
# the SOURCE tree, and .pmos changes on every checkpoint without invalidating it.
FINGERPRINT_SKIP = (".pmos/", "graphify-out/", ".git/")


def tree_fingerprint(proj):
    """Stable content hash of the project's source tree (the gstack-wtree
    pattern, docs/research/2026-08-24-gstack.md): identical content
    fingerprints identically across renames of history, so QA evidence can be
    bound to WHAT WAS TESTED instead of a commit SHA. Files under
    .pmos/ and graphify-out/ are excluded. Git-tracked-plus-untracked when the
    project is a repo (honors .gitignore); everything otherwise."""
    proj = Path(proj)
    names = None
    r = subprocess.run(["git", "-C", str(proj), "ls-files"], capture_output=True, text=True)
    if r.returncode == 0:
        names = sorted(set(r.stdout.split()))
        r2 = subprocess.run(["git", "-C", str(proj), "ls-files", "--others", "--exclude-standard"],
                            capture_output=True, text=True)
        if r2.returncode == 0:
            names = sorted(set(names) | set(r2.stdout.split()))
    if names is None:
        names = []
        for p in sorted(proj.rglob("*")):
            if p.is_file():
                try:
                    names.append(p.relative_to(proj).as_posix())
                except ValueError:
                    pass
    h = hashlib.sha256()
    for name in names:
        if name.startswith(FINGERPRINT_SKIP):
            continue
        p = proj / name
        if not p.is_file():
            continue
        h.update(name.encode("utf-8") + b"\x00")
        h.update(p.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()[:16]


def canonical(raw):
    """R-1 and R-001 are the same id. Returns None for a malformed token."""
    m = ID_TOKEN.match(raw.strip())
    if not m:
        return None
    return "%s-%03d" % (m.group(1).upper(), int(m.group(2)))


def split_refs(value):
    """'T-001, T-2' -> ['T-001', 'T-2']. Empty / placeholder values yield []."""
    value = value.split("#")[0].strip()
    if not value or value.lower() in ("none", "n/a", "-", "tbd"):
        return []
    return [v.strip() for v in re.split(r"[,;]", value) if v.strip()]


class Entity(object):
    def __init__(self, eid, kind, title, file, line):
        self.id, self.kind, self.title = eid, kind, title
        self.file, self.line = file, line
        self.fields = {}
        self.refs = {}          # field -> [raw id, ...]


def parse_blocks(text, file, entities, problems):
    """Read the restricted YAML subset PMOS artifacts use: a flat list of
    '- id: X' blocks whose indented 'key: value' lines follow. Tolerant of
    fences, bullet style and indentation, because agents write these files."""
    current = None
    for n, raw in enumerate(text.splitlines(), 1):
        m = DEF_LINE.match(raw)
        if m:
            cid = canonical(m.group(1))
            if cid is None or cid.split("-")[0] not in PREFIX_KIND:
                problems.append(("error", file, n,
                                 "unknown id prefix in '%s' (expected one of %s)"
                                 % (m.group(1).strip(), ", ".join(sorted(PREFIX_KIND)))))
                current = None
                continue
            current = Entity(cid, PREFIX_KIND[cid.split("-")[0]], "", file, n)
            entities.append(current)
            continue
        if current is None:
            continue
        f = FIELD_LINE.match(raw)
        if not f:
            if raw.strip() and not raw.startswith((" ", "\t")):
                current = None  # block ended at an unindented line
            continue
        key, value = f.group(1), f.group(2)
        current.fields[key] = value
        # risk entries label themselves with `risk:`, everything else with `title:`
        if key in ("title", "risk") and not (key == "risk" and current.title):
            current.title = value
        if key in REF_FIELDS:
            current.refs.setdefault(key, []).extend(split_refs(value))


def parse_project(proj):
    """Collect every id-bearing entity plus the QA results that reference them."""
    proj = Path(proj)
    pmos = proj / ".pmos"
    entities, problems, qa_results = [], [], {}

    def rel(p):
        try:
            return str(p.relative_to(proj))
        except ValueError:
            return str(p)

    charter = pmos / "charter.md"
    if charter.is_file():
        for n, line in enumerate(charter.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = REQ_LINE.match(line)
            if m:
                entities.append(Entity(canonical(m.group(1)), "requirement",
                                       m.group(2).strip(), rel(charter), n))

    plan = pmos / "plans" / "plan.md"
    if plan.is_file():
        parse_blocks(plan.read_text(encoding="utf-8", errors="replace"), rel(plan), entities, problems)

    for adr in sorted((pmos / "decisions").glob("*.md")) if (pmos / "decisions").is_dir() else []:
        text = adr.read_text(encoding="utf-8", errors="replace")
        head = next((ADR_HEAD.match(l) for l in text.splitlines() if ADR_HEAD.match(l)), None)
        if not head:
            problems.append(("warning", rel(adr), 1,
                             "no '# ADR-NNN: title' heading; decision not tracked"))
            continue
        e = Entity(canonical(head.group(1)), "decision", head.group(2).strip(), rel(adr), 1)
        st = ADR_STATUS.search(text)
        # the template ships the status choices on one line; a decided ADR keeps one
        e.fields["status"] = (st.group(1).strip().lower() if st else "")
        for line in text.splitlines():
            f = FIELD_LINE.match(line) or re.match(r"^(supersedes)\s*:\s*(.*)$", line, re.I)
            if f and f.group(1).lower() == "supersedes":
                e.refs.setdefault("supersedes", []).extend(split_refs(f.group(2)))
        entities.append(e)

    register = pmos / "out" / "legal" / "risk-register.md"
    if register.is_file():
        parse_blocks(register.read_text(encoding="utf-8", errors="replace"),
                     rel(register), entities, problems)

    reports = qa_report_paths(pmos)
    qa_tree = None
    for report in reports:
        for n, line in enumerate(report.read_text(encoding="utf-8",
                                                 errors="replace").splitlines(), 1):
            parsed = parse_qa_line(line)
            if parsed:
                aid, result, evidence = parsed
                qa_results[canonical(aid)] = {
                    "result": result, "evidence": evidence,
                    "file": rel(report), "line": n}
            elif qa_tree is None:
                mt = QA_TREE.match(line)
                if mt:
                    qa_tree = mt.group(1).lower()
    # "written but id-less" is a different state from "not written yet": a
    # charter full of scope prose with no R-NNN makes every check below vacuous.
    def substantive(f):
        return f.is_file() and len(f.read_text(encoding="utf-8", errors="replace").strip()) >= 100

    return entities, problems, qa_results, (bool(reports), register.is_file(),
                                            plan.is_file(), qa_tree,
                                            substantive(charter), substantive(plan))


def check(entities, problems, qa_results, present):
    """Validate ids and references. Errors break traceability; warnings are
    coverage gaps the coordinator should see but may knowingly accept."""
    has_qa, has_register, has_plan = present[:3]
    charter_written = present[4] if len(present) > 4 else False
    plan_written = present[5] if len(present) > 5 else False

    # An EMPTY graph must not report clean. qaida planned in "Task 1.1" / "OD-C"
    # and every traceability check passed green at GATE 2 by having nothing to
    # check -- the failure mode this linter exists to prevent.
    kinds = {}
    for e in entities:
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    if charter_written and not kinds.get("requirement"):
        problems.append(("error", ".pmos/charter.md", 1,
                         "charter has content but defines no R-NNN requirements: scope, "
                         "coverage and risk checks are all vacuous until it does "
                         "(ARTIFACT-SCHEMA.md)"))
    if plan_written and not kinds.get("task"):
        problems.append(("error", ".pmos/plans/plan.md", 1,
                         "plan has content but defines no T-NNN tasks: nothing links scope to "
                         "work, so GATE 2 would pass on an empty graph (ARTIFACT-SCHEMA.md)"))
    if plan_written and kinds.get("task") and not kinds.get("acceptance"):
        problems.append(("error", ".pmos/plans/plan.md", 1,
                         "plan defines tasks but no A-NNN acceptance criteria: nothing can "
                         "verify the work (ARTIFACT-SCHEMA.md)"))
    by_id = {}
    for e in entities:
        if e.id in by_id:
            problems.append(("error", e.file, e.line,
                             "duplicate id %s (already defined at %s:%d)"
                             % (e.id, by_id[e.id].file, by_id[e.id].line)))
            continue
        by_id[e.id] = e

    edges = []
    for e in entities:
        for field, raws in e.refs.items():
            owner_kind, target_kind = REF_FIELDS[field]
            if e.kind != owner_kind:
                problems.append(("error", e.file, e.line,
                                 "%s carries '%s:', which belongs to a %s" % (e.id, field, owner_kind)))
                continue
            for raw in raws:
                cid = canonical(raw)
                if cid is None:
                    problems.append(("error", e.file, e.line,
                                     "%s %s: '%s' is not a valid id" % (e.id, field, raw)))
                    continue
                target = by_id.get(cid)
                if target is None:
                    problems.append(("error", e.file, e.line,
                                     "%s %s: %s is not defined anywhere" % (e.id, field, cid)))
                    continue
                if target.kind != target_kind:
                    problems.append(("error", e.file, e.line,
                                     "%s %s: %s is a %s, expected a %s"
                                     % (e.id, field, cid, target.kind, target_kind)))
                    continue
                if cid == e.id:
                    problems.append(("error", e.file, e.line, "%s %s itself" % (e.id, field)))
                    continue
                edges.append({"src": e.id, "dst": cid, "kind": field})

    # dependency cycles: a task graph that cannot be ordered is not a plan
    deps = {}
    for edge in edges:
        if edge["kind"] == "depends_on":
            deps.setdefault(edge["src"], []).append(edge["dst"])
    state = {}

    def walk(node, trail):
        if state.get(node) == "done":
            return
        if state.get(node) == "open":
            cycle = trail[trail.index(node):] + [node]
            e = by_id[node]
            problems.append(("error", e.file, e.line, "dependency cycle: " + " -> ".join(cycle)))
            return
        state[node] = "open"
        for nxt in deps.get(node, []):
            walk(nxt, trail + [node])
        state[node] = "done"

    for node in list(deps):
        if state.get(node) is None:
            walk(node, [])

    # ---- coverage warnings ------------------------------------------------
    for e in entities:
        if e.title.startswith("<") and e.title.endswith(">"):
            problems.append(("warning", e.file, e.line,
                             "%s still carries the template placeholder %s" % (e.id, e.title)))

    satisfied = {e["dst"] for e in edges if e["kind"] == "satisfies"}
    verified = {e["dst"] for e in edges if e["kind"] == "verifies"}
    for e in entities:
        if e.kind == "requirement" and has_plan and e.id not in satisfied:
            problems.append(("warning", e.file, e.line,
                             "%s is in scope but no task satisfies it" % e.id))
        if e.kind == "task" and e.id not in verified:
            problems.append(("warning", e.file, e.line,
                             "%s has no acceptance criterion verifying it" % e.id))
        if e.kind == "acceptance" and has_qa:
            res = qa_results.get(e.id, {}).get("result")
            if res is None:
                problems.append(("warning", e.file, e.line,
                                 "%s is never reported on in the QA report" % e.id))
            elif res in ("n/a", "partial"):
                problems.append(("warning", e.file, e.line,
                                 "%s is reported as %s, so it is not verified" % (e.id, res)))
        if e.kind == "decision" and e.fields.get("status", "").startswith("accepted"):
            for other in entities:
                if other.kind == "decision" and e.id in [canonical(r) or r for r in
                                                         other.refs.get("supersedes", [])]:
                    problems.append(("warning", e.file, e.line,
                                     "%s is superseded by %s but still marked accepted"
                                     % (e.id, other.id)))
        if e.kind == "risk":
            sev = e.fields.get("severity", "").lower()
            status = e.fields.get("status", "").lower()
            mitigators = [canonical(r) for r in e.refs.get("mitigated_by", [])]
            if sev == "high" and status == "open" and not mitigators:
                problems.append(("warning", e.file, e.line,
                                 "%s is high severity and open with no mitigated_by task" % e.id))
            if status == "mitigated":
                if not mitigators:
                    problems.append(("warning", e.file, e.line,
                                     "%s claims mitigated with no mitigated_by task" % e.id))
                for t in mitigators:
                    passing = [a for a in entities if a.kind == "acceptance"
                               and t in [canonical(r) for r in a.refs.get("verifies", [])]
                               and qa_results.get(a.id, {}).get("result") == "pass"]
                    if has_qa and t in by_id and not passing:
                        problems.append(("warning", e.file, e.line,
                                         "%s claims mitigated by %s, which has no passing "
                                         "acceptance criterion in the QA report" % (e.id, t)))

    for aid, res in qa_results.items():
        target = by_id.get(aid)
        if target is None:
            problems.append(("error", res["file"], res["line"],
                             "QA reports on %s, which no acceptance criterion defines" % aid))
        elif target.kind != "acceptance":
            problems.append(("error", res["file"], res["line"],
                             "QA reports on %s, which is a %s" % (aid, target.kind)))
    return by_id, edges


def build_graph(by_id, edges, qa_results):
    nodes = []
    for e in sorted(by_id.values(), key=lambda e: e.id):
        node = {"id": e.id, "kind": e.kind, "title": e.title, "file": e.file, "line": e.line}
        for extra in ("role", "status", "severity", "touches", "test_strategy"):
            if e.fields.get(extra):
                node[extra] = e.fields[extra]
        if e.id in qa_results:
            node["qa"] = qa_results[e.id]["result"]
        nodes.append(node)
    return {"nodes": nodes, "edges": sorted(edges, key=lambda x: (x["src"], x["kind"], x["dst"]))}


def run(proj, as_json=False, strict=False, graph_out=None, quiet=False):
    entities, problems, qa_results, present = parse_project(proj)
    by_id, edges = check(entities, problems, qa_results, present)
    qa_tree = present[3] if len(present) > 3 else None
    if qa_tree is not None:
        current = tree_fingerprint(proj)
        if current != qa_tree:
            problems.append(("warning", ".pmos/out/qa/test-report.md", 1,
                             "QA evidence is stale: collected against tree %s, current tree is %s;"
                             " re-run QA or re-bind the evidence (artifacts.py fingerprint)"
                             % (qa_tree, current)))
    errors = [p for p in problems if p[0] == "error"]
    warnings = [p for p in problems if p[0] == "warning"]
    graph = build_graph(by_id, edges, qa_results)

    if graph_out:
        Path(graph_out).parent.mkdir(parents=True, exist_ok=True)
        Path(graph_out).write_text(json.dumps(graph, indent=1), encoding="utf-8")

    if as_json:
        print(json.dumps({
            "counts": {k: sum(1 for e in by_id.values() if e.kind == k) for k in KINDS},
            "edges": len(edges),
            "errors": [{"file": f, "line": n, "message": m} for _, f, n, m in errors],
            "warnings": [{"file": f, "line": n, "message": m} for _, f, n, m in warnings],
            "graph": graph}, indent=1))
    elif not quiet:
        for kind in KINDS:
            n = sum(1 for e in by_id.values() if e.kind == kind)
            if n:
                print("%-12s %3d" % (kind, n))
        print("%-12s %3d" % ("references", len(edges)))
        for level, f, n, msg in errors + warnings:
            print("  [%s] %s:%d  %s" % (level.upper(), f, n, msg))
        if not errors and not warnings:
            print("artifacts OK: every reference resolves, every item is covered")
        else:
            print("%d error(s), %d warning(s)" % (len(errors), len(warnings)))
    if errors:
        return 1
    if strict and warnings:
        return 2
    return 0


CLEAN_FIXTURE = {
    ".pmos/charter.md": """# Project Charter: Fixture

## 4. Scope
### In scope (this project)
- R-001: users can reset their own password
- R-002: sessions expire after 30 minutes
""",
    ".pmos/plans/plan.md": """# Plan

```yaml
- id: T-001
  title: password reset endpoint
  role: backend
  satisfies: R-001
  decided_by: ADR-001
- id: T-002
  title: session expiry
  role: backend
  satisfies: R-002
  depends_on: T-001
- id: A-001
  title: reset mail arrives and the new password works
  verifies: T-001
- id: A-002
  title: a 31 minute old session is rejected
  verifies: T-002
```
""",
    ".pmos/decisions/ADR-001.md": "# ADR-001: store sessions in Redis\n\nStatus: accepted\n",
    ".pmos/out/legal/risk-register.md": """# Risk register

```yaml
- id: L-001
  risk: password reset mail leaks a reusable token
  law: GDPR Art. 32
  severity: high
  status: mitigated
  owner: backend
  mitigated_by: T-001
```
""",
    ".pmos/out/qa/test-report.md": "# QA\n\n- A-001: pass - 12 tests green\n- A-002: pass - expiry suite green\n",
}

BROKEN_FIXTURE = dict(CLEAN_FIXTURE, **{
    ".pmos/plans/plan.md": """# Plan

```yaml
- id: T-001
  title: password reset endpoint
  satisfies: R-009
  depends_on: T-002
- id: T-002
  title: session expiry
  satisfies: T-001
  depends_on: T-001
- id: A-001
  title: reset mail arrives
  verifies: T-001
- id: A-001
  title: duplicate id
  verifies: T-002
```
""",
    ".pmos/out/qa/test-report.md": "# QA\n\n- A-001: pass - green\n- A-404: fail - nothing defines this\n",
})


def selftest():
    import tempfile
    ok = True

    def build(fixture):
        root = Path(tempfile.mkdtemp())
        for rel, body in fixture.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        return root

    clean = build(CLEAN_FIXTURE)
    entities, problems, qa, present = parse_project(clean)
    by_id, edges = check(entities, problems, qa, present)
    errs = [p for p in problems if p[0] == "error"]
    warns = [p for p in problems if p[0] == "warning"]
    assert not errs, "clean fixture reported errors: %s" % (errs,)
    assert not warns, "clean fixture reported warnings: %s" % (warns,)
    assert len(by_id) == 8, "expected 8 entities, got %d" % len(by_id)
    assert {"src": "T-001", "dst": "R-001", "kind": "satisfies"} in edges
    assert {"src": "L-001", "dst": "T-001", "kind": "mitigated_by"} in edges
    print("-- clean fixture: %d entities, %d references, no findings" % (len(by_id), len(edges)))

    broken = build(BROKEN_FIXTURE)
    entities, problems, qa, present = parse_project(broken)
    by_id, edges = check(entities, problems, qa, present)
    msgs = [m for level, _, _, m in problems if level == "error"]
    expected = [
        ("dangling requirement", "R-009 is not defined"),
        ("wrong target kind", "T-001 is a task, expected a requirement"),
        ("duplicate id", "duplicate id A-001"),
        ("dependency cycle", "dependency cycle"),
        ("unknown QA target", "A-404"),
    ]
    for label, needle in expected:
        hit = any(needle in m for m in msgs)
        print("   %s %-22s %s" % ("[OK]  " if hit else "[FAIL]", label,
                                  "" if hit else "not reported: " + needle))
        ok = ok and hit
    rc = run(broken, quiet=True)
    print("   %s exit code on errors      %s" % ("[OK]  " if rc == 1 else "[FAIL]", rc))
    ok = ok and rc == 1
    rc = run(clean, quiet=True, strict=True)
    print("   %s clean project exits 0    %s" % ("[OK]  " if rc == 0 else "[FAIL]", rc))
    ok = ok and rc == 0

    # the mitigated-risk check: QA must actually show the mitigating task passing
    unproven = dict(CLEAN_FIXTURE,
                    **{".pmos/out/qa/test-report.md": "# QA\n\n- A-001: fail - token still reusable\n- A-002: pass\n"})
    root = build(unproven)
    entities, problems, qa, present = parse_project(root)
    check(entities, problems, qa, present)
    hit = any("claims mitigated by T-001" in m for level, _, _, m in problems if level == "warning")
    print("   %s unproven mitigation warned" % ("[OK]  " if hit else "[FAIL]"))
    ok = ok and hit

    # -- an EMPTY graph must not report clean. This is the qaida shape: a real
    # charter and plan, planned as "Task 1.1" / "OD-C", zero ids -- which used to
    # print "artifacts OK: every reference resolves" and exit 0 at GATE 2.
    idless = {
        ".pmos/charter.md": "# Charter\n\n## Scope\n- users can reset their own password\n"
                            "- admins can see an audit log\n" + "x" * 120,
        ".pmos/plans/plan.md": "# Plan\n\n## Phase 1\n- Task 1.1: reset endpoint\n"
                               "- Task 1.2: audit log\n" + "y" * 120,
    }
    root = build(idless)
    entities, problems, qa, present = parse_project(root)
    check(entities, problems, qa, present)
    emsgs = [m for lvl, _, _, m in problems if lvl == "error"]
    cases = [
        ("id-less charter is an error", any("no R-NNN requirements" in m for m in emsgs)),
        ("id-less plan is an error", any("no T-NNN tasks" in m for m in emsgs)),
        ("an empty graph exits non-zero", run(root, quiet=True) == 1),
    ]
    # tasks without criteria: nothing can verify the work
    notests = {
        ".pmos/charter.md": idless[".pmos/charter.md"].replace(
            "- users can reset", "- R-001: users can reset"),
        ".pmos/plans/plan.md": "# Plan\n\n```yaml\n- id: T-001\n  title: reset endpoint\n"
                               "  satisfies: R-001\n```\n" + "y" * 120,
    }
    root2 = build(notests)
    entities, problems, qa, present = parse_project(root2)
    check(entities, problems, qa, present)
    e2 = [m for lvl, _, _, m in problems if lvl == "error"]
    cases.append(("tasks with no acceptance criteria is an error",
                  any("no A-NNN acceptance criteria" in m for m in e2)))
    # and a project that never started planning is NOT accused of anything
    stub = {".pmos/charter.md": "# Charter\n\ndraft\n"}
    root3 = build(stub)
    entities, problems, qa, present = parse_project(root3)
    check(entities, problems, qa, present)
    cases.append(("a stub charter is not an error yet",
                  not [m for lvl, _, _, m in problems if lvl == "error"]))
    for label, hit in cases:
        print("   %s %-42s" % ("[OK]  " if hit else "[FAIL]", label))
        ok = ok and hit

    # -- the lean roster's reviewer writes a TABLE in out/reviewer/, not a list
    # in out/qa/. Reading only one shape from one path made suited's 33 reported
    # criteria all count as unreported, so both must land, and n/a must not be
    # mistaken for a pass.
    lean = dict(CLEAN_FIXTURE)
    del lean[".pmos/out/qa/test-report.md"]
    lean[".pmos/out/reviewer/test-report.md"] = (
        "# Gate\n\n| Criterion | Status | Evidence |\n|---|---|---|\n"
        "| A-001 reset mail arrives | **PASS** | 12 tests green |\n"
        "| A-002 session expiry | NOT-APPLICABLE (T-002 unbuilt) | no code yet |\n")
    root = build(lean)
    entities, problems, qa, present = parse_project(root)
    check(entities, problems, qa, present)
    cases = [
        ("table row parsed", qa.get("A-001", {}).get("result") == "pass"),
        ("evidence captured", "12 tests green" in qa.get("A-001", {}).get("evidence", "")),
        ("n/a is not a pass", qa.get("A-002", {}).get("result") == "n/a"),
        ("n/a warned as unverified",
         any("A-002 is reported as n/a" in m for lvl, _, _, m in problems if lvl == "warning")),
        ("reviewer path counts as a QA report", present[0] is True),
        # a pass read out of a TABLE must satisfy the mitigation check too:
        # if the row failed to parse, L-001 would be warned as unproven
        ("table pass proves the mitigation",
         not any("claims mitigated by T-001" in m
                 for lvl, _, _, m in problems if lvl == "warning")),
    ]
    for label, hit in cases:
        print("   %s %-32s" % ("[OK]  " if hit else "[FAIL]", label))
        ok = ok and hit

    # -- QA evidence bound to the tree fingerprint (gstack G3): evidence
    # collected against the tested tree passes silently; a changed tree is
    # flagged stale instead of silently gating on old results.
    import contextlib
    import io

    def lint_warnings(root):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run(root, as_json=True)
        return [w["message"] for w in json.loads(buf.getvalue())["warnings"]]

    rooted = build(CLEAN_FIXTURE)
    (rooted / "src").mkdir()
    (rooted / "src" / "app.py").write_text("print('v1')\n", encoding="utf-8")
    rep = rooted / ".pmos" / "out" / "qa" / "test-report.md"
    rep.write_text(rep.read_text(encoding="utf-8") + "\ntree: %s\n" % tree_fingerprint(rooted),
                   encoding="utf-8")
    clean_ws = [w for w in lint_warnings(rooted) if "stale" in w]
    hit = not clean_ws
    print("   %s fresh evidence not flagged        %s" % ("[OK]  " if hit else "[FAIL]", clean_ws))
    ok = ok and hit
    (rooted / "src" / "app.py").write_text("print('v2')\n", encoding="utf-8")
    stale_ws = [w for w in lint_warnings(rooted) if "QA evidence is stale" in w]
    hit = len(stale_ws) == 1
    print("   %s changed tree flagged stale       %s" % ("[OK]  " if hit else "[FAIL]", stale_ws))
    ok = ok and hit

    print("SELFTEST PASS" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="PMOS artifact id/reference linter")
    ap.add_argument("mode", nargs="?", default="lint",
                    choices=["lint", "selftest", "fingerprint"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")
    ap.add_argument("--graph", default=None, help="write the node/edge list to this JSON file")
    args = ap.parse_args()
    if args.mode == "selftest":
        return selftest()
    if args.mode == "fingerprint":
        print(tree_fingerprint(args.project))
        return 0
    if not (Path(args.project) / ".pmos").is_dir():
        print("no .pmos/ in %s: nothing to lint" % args.project, file=sys.stderr)
        return 0
    return run(args.project, args.json, args.strict, args.graph)


if __name__ == "__main__":
    sys.exit(main())
