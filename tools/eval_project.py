#!/usr/bin/env python3
"""PMOS protocol harness: replay whole fixture projects through the tooling.

The retrieval benchmark scores one component. This scores the coordinator's
view of a project: given a `.pmos/` tree at some stage, does the tooling report
the right stage, the right traceability findings, the right coverage, and enough
information to make the gate decision the protocol calls for?

Every fixture is a directory under tests/fixtures/:

    <name>/
      expect.json     what the tooling must report (see EXPECT_KEYS below)
      pmos/           becomes .pmos/ in a temp copy (kept undotted so the
                      template's own .gitignore does not swallow the fixtures)
      graphify/       becomes graphify-out/
      files/          becomes the project's source tree

    python tools/eval_project.py            # human report
    python tools/eval_project.py --json
    python tools/eval_project.py --only qa-failed

Deterministic and offline: no model is spawned. It proves the machinery and the
gate decisions, NOT the quality of what agents write - that stays a human call.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent
FIXTURES = TPL / "tests" / "fixtures"

EXPECT_KEYS = {"description", "legal_strict", "dirty", "state", "artifacts", "trace",
               "cost", "gate2"}


def run_json(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout), r.returncode
    except ValueError:
        return {"_stdout": r.stdout, "_stderr": r.stderr}, r.returncode


def materialize(fixture, dest, legal_strict):
    """Build a throwaway project from the fixture, then make it a git repo whose
    HEAD is the clean baseline, so 'changed files' means what the fixture says."""
    dest.mkdir(parents=True, exist_ok=True)
    for src, target in (("pmos", ".pmos"), ("graphify", "graphify-out"), ("files", ".")):
        s = fixture / src
        if s.is_dir():
            shutil.copytree(s, dest / target, dirs_exist_ok=True)
    (dest / ".pmos").mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "init",
                    "--db", str(dest / ".pmos" / "kb.sqlite3")], capture_output=True)
    cfg = json.loads((TPL / "config.json").read_text(encoding="utf-8"))
    cfg["legal_strict"] = legal_strict
    (dest / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    git = ["git", "-c", "user.email=fixture@pmos", "-c", "user.name=fixture"]
    subprocess.run(["git", "init", "-q"], cwd=str(dest), capture_output=True)
    subprocess.run(git + ["add", "-A"], cwd=str(dest), capture_output=True)
    subprocess.run(git + ["commit", "-qm", "fixture baseline"], cwd=str(dest), capture_output=True)
    return dest


def apply_dirty(dest, dirty):
    """Files the fixture says changed since the baseline commit."""
    for rel in dirty:
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write("\n# changed after the baseline\n")


def collect(dest, cfg_path):
    """Everything the coordinator would look at, in one pass."""
    state, _ = run_json([sys.executable, str(TPL / "tools" / "state.py"),
                         "--project", str(dest), "--config", str(cfg_path), "--json"])
    lint, lint_rc = run_json([sys.executable, str(TPL / "tools" / "artifacts.py"),
                              "--project", str(dest), "--json"])
    cov, _ = run_json([sys.executable, str(TPL / "tools" / "trace.py"), "coverage",
                       "--project", str(dest), "--json"])
    unp, _ = run_json([sys.executable, str(TPL / "tools" / "trace.py"), "unplanned",
                       "--project", str(dest), "--json"])
    cost, cost_rc = run_json([sys.executable, str(TPL / "tools" / "cost.py"), "report",
                              "--project", str(dest), "--json"])
    return {"state": state, "artifacts": lint, "lint_rc": lint_rc, "coverage": cov,
            "unplanned": unp, "cost": cost, "cost_rc": cost_rc}


def gate2_verdict(got):
    """The GATE 2 rule, read off the tools instead of off an agent's judgement:
    a broken reference blocks, and so does an unaccepted high-severity open risk."""
    if got["artifacts"].get("errors"):
        return "blocked"
    for w in got["artifacts"].get("warnings", []):
        if "high severity and open" in w["message"]:
            return "blocked"
    return "clear"


def check_fixture(name, verbose=False):
    fixture = FIXTURES / name
    expect = json.loads((fixture / "expect.json").read_text(encoding="utf-8"))
    unknown = set(expect) - EXPECT_KEYS
    findings = []
    if unknown:
        findings.append("expect.json has unknown key(s): %s" % ", ".join(sorted(unknown)))

    tmp = Path(tempfile.mkdtemp()) / "proj"
    materialize(fixture, tmp, expect.get("legal_strict", True))
    apply_dirty(tmp, expect.get("dirty", []))
    got = collect(tmp, tmp / "config.json")

    def want(section, key, actual, expected):
        if actual != expected:
            findings.append("%s.%s: expected %r, got %r" % (section, key, expected, actual))

    st = expect.get("state", {})
    if "stage" in st:
        want("state", "stage", got["state"].get("stage"), st["stage"])
    if "stage_name" in st:
        want("state", "stage_name", got["state"].get("stage_name"), st["stage_name"])
    for level in ("FAIL", "WARN"):
        key = "fail_checks" if level == "FAIL" else "warn_checks"
        if key not in st:
            continue
        actual = [c["name"] for c in got["state"].get("checks", []) if c["status"] == level]
        for needle in st[key]:
            if not any(needle in a for a in actual):
                findings.append("state.%s: nothing matching %r (got %s)" % (key, needle, actual))
        if st.get("exact_" + key) and len(actual) != len(st[key]):
            findings.append("state.%s: expected %d, got %d" % (key, len(st[key]), len(actual)))

    art = expect.get("artifacts", {})
    for level in ("errors", "warnings"):
        if level not in art:
            continue
        actual = [e["message"] for e in got["artifacts"].get(level, [])]
        for needle in art[level]:
            if not any(needle in a for a in actual):
                findings.append("artifacts.%s: nothing matching %r (got %s)" % (level, needle, actual))
    if "error_count" in art:
        want("artifacts", "error_count", len(got["artifacts"].get("errors", [])), art["error_count"])
    if "counts" in art:
        for kind, n in art["counts"].items():
            want("artifacts", "counts." + kind, got["artifacts"].get("counts", {}).get(kind), n)

    tr = expect.get("trace", {})
    if "summary" in tr:
        for key, n in tr["summary"].items():
            want("trace", "summary." + key, got["coverage"].get("summary", {}).get(key), n)
    if "gaps" in tr:
        actual = got["coverage"].get("gaps", [])
        for needle in tr["gaps"]:
            if not any(needle in a for a in actual):
                findings.append("trace.gaps: nothing matching %r (got %s)" % (needle, actual))
    if "unplanned" in tr:
        actual = sorted(r["file"] for r in got["unplanned"].get("unplanned", []))
        want("trace", "unplanned", actual, sorted(tr["unplanned"]))

    co = expect.get("cost", {})
    if co:
        total = got["cost"].get("total", {})
        if "runs" in co:
            want("cost", "runs", total.get("runs"), co["runs"])
        if "usd" in co and abs((total.get("usd") or 0) - co["usd"]) > 0.005:
            findings.append("cost.usd: expected ~%.2f, got %r" % (co["usd"], total.get("usd")))
        if "over_budget" in co:
            want("cost", "over_budget", got["cost_rc"] == 2, co["over_budget"])
        if "remaining_usd" in co and abs((got["cost"].get("remaining_usd") or 0)
                                         - co["remaining_usd"]) > 0.005:
            findings.append("cost.remaining_usd: expected ~%.2f, got %r"
                            % (co["remaining_usd"], got["cost"].get("remaining_usd")))

    if "gate2" in expect:
        want("gate2", "verdict", gate2_verdict(got), expect["gate2"])

    if verbose:
        print(json.dumps(got, indent=1))
    shutil.rmtree(tmp.parent, ignore_errors=True)
    return findings, expect.get("description", "")


def main():
    ap = argparse.ArgumentParser(description="Replay fixture projects through the PMOS tooling")
    ap.add_argument("--only", default=None, help="run one fixture by directory name")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="dump the collected tool output")
    args = ap.parse_args()

    if not FIXTURES.is_dir():
        print("no fixtures at %s" % FIXTURES, file=sys.stderr)
        return 1
    names = sorted(p.name for p in FIXTURES.iterdir()
                   if p.is_dir() and (p / "expect.json").is_file())
    if args.only:
        names = [n for n in names if n == args.only]
        if not names:
            print("no fixture named %r" % args.only, file=sys.stderr)
            return 1

    results, failed = [], 0
    for name in names:
        findings, desc = check_fixture(name, args.verbose)
        results.append({"fixture": name, "description": desc, "findings": findings})
        failed += 1 if findings else 0

    if args.json:
        print(json.dumps({"fixtures": len(results), "failed": failed, "results": results}, indent=1))
    else:
        for r in results:
            print("[%s] %-26s %s" % ("PASS" if not r["findings"] else "FAIL",
                                     r["fixture"], r["description"]))
            for f in r["findings"]:
                print("        %s" % f)
        print("\n%d fixture(s), %d failed" % (len(results), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
