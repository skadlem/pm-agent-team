#!/usr/bin/env python3
"""PMOS project-state detector: find where a project left off and pre-flight it.

On RESUME (a directory that already has `.pmos/`), the coordinator needs three
answers before touching anything:

  1. WHAT STAGE is the project at?  (which waves/gates have completed)
  2. WAS EVERYTHING FINE up to that stage?  (quick integrity pre-flight)
  3. WHAT IS THE NEXT STEP?  (the ORCHESTRATOR.md step to continue from)

This tool answers all three deterministically from artifacts on disk, so the
answer does not depend on the coordinator remembering anything.

Stage chain (each stage requires ALL earlier markers to hold):

  stage 0  bootstrapped        .pmos/kb.sqlite3
  stage 1  charter drafted     .pmos/charter.md
  stage 2  GATE 1 passed       .pmos/team-model.json
  stage 3  jurisdiction packed kb-sources/legal/jurisdiction-*.md   (legal_strict only)
  stage 4  wave 2 design done  primary artifact of every approved wave-2 role
  stage 5  KB enriched         .pmos/log.md mentions the enrich step
  stage 6  GATE 2 passed       .pmos/log.md has a GATE 2 entry
  stage 7  implementation      primary artifact of any approved wave-3 role
  stage 8  QA gate passed      .pmos/out/qa/test-report.md
  stage 9  checkpointed        all of the above

The stage is the HIGHEST index whose marker (and all markers before it) hold.
Log-based markers (enrich, GATE 2) are SOFT: a missing log entry produces a
warning, not a stage rollback, because artifacts may exist without the log
line having been written.

Pre-flight checks run only for stages <= the detected stage, so a project
that stopped early does not get nagged about artifacts it never reached.

Usage:
  python tools/state.py [--project <dir>] [--config <config.json>] [--json]

Exit codes: 0 = OK (or no .pmos), 1 = at least one FAILED check,
            2 = usage error. Warnings never block.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
from datetime import date

TPL = pathlib.Path(__file__).resolve().parent.parent

# role -> primary artifact that proves that role's wave completed.
# Mirrors roster.json "artifacts" (first concrete file per role). Paths are
# relative to the project's .pmos/ dir.
WAVE2_ARTIFACTS = {
    "architect": "out/architect/architecture.md",
    "designer": "out/designer/ui-spec.md",
    "business": "out/business/model.md",
    "legal": "out/legal/risk-register.md",
}
WAVE3_ARTIFACTS = {
    "backend": "out/backend/notes.md",
    "frontend": "out/frontend/notes.md",
    "devops": "out/devops/infra.md",
    "marketing": "out/marketing/positioning.md",
}
QA_ARTIFACT = "out/qa/test-report.md"

NEXT_STEP = {
    0: "step 3: Wave 1 (spawn the PM worker: charter + plan)",
    1: "step 4: GATE 1 (present roster + model table; USER approval needed)",
    2: "step 5 (strict): jurisdiction pack  |  step 6 (light): Wave 2",
    3: "step 6: Wave 2 (spawn approved design roles in parallel)",
    4: "step 7: pm-kb-enrich + kb.py budget",
    5: "step 8: GATE 2 (present plan + risks; USER approval needed)",
    6: "step 9: Wave 3 implementation",
    7: "step 10: Wave 4 QA gate",
    8: "step 11: checkpoint",
    9: "all 11 steps complete; project finished",
}


def load_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Detect PMOS project stage + pre-flight checks")
    ap.add_argument("--project", default=".", help="project directory (default: cwd)")
    ap.add_argument("--config", default=None, help="path to config.json (default: TPL/config.json)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    proj = pathlib.Path(a.project).resolve()
    config_path = pathlib.Path(a.config) if a.config else TPL / "config.json"
    cfg = load_json(config_path) or {}

    out = {"project": str(proj), "has_pmos": False, "stage": None, "stage_name": None,
           "next_step": None, "strict_legal": bool((cfg.get("legal_strict") is True)),
           "checks": [], "problems": 0, "warnings": 0}

    def add(status, name, detail=""):
        out["checks"].append({"status": status, "name": name, "detail": detail})
        if status == "FAIL":
            out["problems"] += 1
        elif status == "WARN":
            out["warnings"] += 1

    pmos = proj / ".pmos"
    if not pmos.is_dir():
        out["stage"] = -1
        out["stage_name"] = "no .pmos (fresh launch)"
        out["next_step"] = "launch per ORCHESTRATOR.md from step 1"
        out["has_pmos"] = False
        print(json.dumps(out, indent=1, ensure_ascii=False) if a.json else
              "no .pmos/ in %s: fresh launch, not a resume" % proj)
        return 0

    out["has_pmos"] = True
    strict = out["strict_legal"]

    # ---- stage detection -------------------------------------------------
    def exists(rel):
        return (pmos / rel).is_file()

    def log_mentions(*needles):
        log = pmos / "log.md"
        if not log.is_file():
            return False
        text = log.read_text(encoding="utf-8", errors="replace").lower()
        return any(n.lower() in text for n in needles)

    def qa_failures():
        """Criteria the QA report marks fail/blocked. A report that exists is not
        a gate that passed: ORCHESTRATOR step 10 sends a failed gate back to
        wave 3, so those ids are what decides whether stage 8 was reached."""
        p = pmos / QA_ARTIFACT
        if not p.is_file():
            return []
        text = p.read_text(encoding="utf-8", errors="replace")
        return sorted(set(re.findall(r"^\s*[-*]\s+(A-\d{1,4})\s*[:\-]\s*(?:fail|blocked)\b",
                                     text, re.I | re.M)))

    failing_criteria = qa_failures()
    qa_passed = exists(QA_ARTIFACT) and not failing_criteria

    markers = {
        0: exists("kb.sqlite3"),
        1: exists("charter.md"),
        2: exists("team-model.json"),
        # stage 3 exists only in strict mode; in light mode the chain skips it
        3: (not strict) or any((pmos / "kb-sources" / "legal").glob("jurisdiction-*.md")),
        4: None,  # computed below from team-model.json approved roles
        5: log_mentions("enrich"),
        6: log_mentions("gate 2"),
        7: None,  # computed below
        8: qa_passed,
        9: exists("charter.md") and exists("team-model.json") and qa_passed,
    }

    team_model = load_json(pmos / "team-model.json") if markers[2] else None
    approved_roles = []
    if isinstance(team_model, dict):
        approved_roles = sorted(k for k in team_model if k != "budget_usd")

    wave2_approved = [r for r in approved_roles if r in WAVE2_ARTIFACTS]
    markers[4] = bool(wave2_approved) and all(exists(WAVE2_ARTIFACTS[r]) for r in wave2_approved)
    wave3_approved = [r for r in approved_roles if r in WAVE3_ARTIFACTS]
    markers[7] = bool(wave3_approved) and any(exists(WAVE3_ARTIFACTS[r]) for r in wave3_approved)

    stage = -1
    for s in range(10):
        if not markers[s]:
            break
        stage = s
    if stage == -1:
        stage = 0  # kb.sqlite3 exists but nothing after; resume at wave 1
    if strict:
        stage_names = ["bootstrapped", "charter drafted", "GATE 1 passed", "jurisdiction packed",
                       "wave 2 design done", "KB enriched", "GATE 2 passed", "implementation started",
                       "QA gate passed", "checkpointed"]
        next_map = dict(NEXT_STEP)
        next_map[2] = "step 5: jurisdiction pack"
    else:
        # light legal: no jurisdiction stage, so stages are shifted down by one
        stage_names = ["bootstrapped", "charter drafted", "GATE 1 passed", "wave 2 design done",
                       "KB enriched", "GATE 2 passed", "implementation started",
                       "QA gate passed", "checkpointed"]
        next_map = {0: NEXT_STEP[0], 1: NEXT_STEP[1], 2: "step 6: Wave 2",
                    3: "step 7: pm-kb-enrich + kb.py budget",
                    4: "step 8: GATE 2 (present plan + risks; USER approval needed)",
                    5: "step 9: Wave 3 implementation",
                    6: "step 10: Wave 4 QA gate",
                    7: "step 11: checkpoint",
                    8: "all steps complete; project finished"}
    chain_stage = stage  # marker-chain index (strict numbering)
    if not strict and chain_stage >= 3:
        chain_stage -= 1  # light legal has no jurisdiction stage
    out["stage"] = chain_stage
    out["stage_name"] = stage_names[chain_stage]
    out["next_step"] = next_map[chain_stage]

    # pre-flight thresholds below use `stage`, which stays in chain (strict)
    # numbering even when the reported stage was shifted for light legal.
    # ---- pre-flight checks (stages <= detected stage) --------------------
    if stage >= 0:
        if exists("kb.sqlite3"):
            r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "budget",
                                "--db", str(pmos / "kb.sqlite3"),
                                "--config", str(config_path)],
                               capture_output=True, text=True)
            add("OK" if r.returncode == 0 else "FAIL",
                "kb.py budget runs on the project DB",
                "" if r.returncode == 0 else (r.stderr or r.stdout).strip()[:200])
        else:
            add("FAIL", "kb.sqlite3 exists", "marker said yes but file missing")

    if stage >= 1:
        for rel in ["charter.md", "plans/plan.md"]:
            p = pmos / rel
            add("OK" if p.is_file() and p.stat().st_size >= 100 else "FAIL",
                "%s present and non-empty" % rel)
        if exists("log.md"):
            add("OK", "log.md exists")
        else:
            add("FAIL", "log.md exists")

    if stage >= 1:
        # ids and references across charter / plan / ADRs / register / QA report.
        # Errors mean a handoff points at something that does not exist; warnings
        # are coverage gaps (scope with no task, task with no criterion).
        r = subprocess.run([sys.executable, str(TPL / "tools" / "artifacts.py"),
                            "--project", str(proj), "--json"],
                           capture_output=True, text=True)
        try:
            lint = json.loads(r.stdout)
        except ValueError:
            lint = None
        if lint is None:
            add("WARN", "artifact ids lint", (r.stderr or r.stdout).strip()[:200] or "no output")
        else:
            errs, warns = lint["errors"], lint["warnings"]
            out["artifacts"] = {"counts": lint["counts"], "edges": lint["edges"],
                                "errors": len(errs), "warnings": len(warns)}
            detail = "%d entities, %d references" % (sum(lint["counts"].values()), lint["edges"])
            if errs:
                add("FAIL", "artifact references all resolve",
                    "%s%s" % (errs[0]["message"],
                              "; +%d more" % (len(errs) - 1) if len(errs) > 1 else ""))
            else:
                add("OK", "artifact references all resolve", detail)
            if warns:
                add("WARN", "artifact coverage complete",
                    "%s%s" % (warns[0]["message"],
                              "; +%d more" % (len(warns) - 1) if len(warns) > 1 else ""))
            else:
                add("OK", "artifact coverage complete", detail)

    if stage >= 2:
        tm = team_model if team_model else load_json(pmos / "team-model.json")
        if isinstance(tm, dict):
            bad = [k for k in tm if k != "budget_usd" and not isinstance(tm[k], dict)]
            add("OK" if not bad and approved_roles else "FAIL",
                "team-model.json valid (roles + budget_usd)",
                "budget_usd=%s, roles=%s" % (tm.get("budget_usd"), ",".join(approved_roles) or "-"))
        else:
            add("FAIL", "team-model.json valid JSON")
        add("OK" if exists("team-model-ladder.json") else "FAIL",
            "team-model-ladder.json present (fallback ladders)")
        # spend against the cap the user approved at GATE 1
        r = subprocess.run([sys.executable, str(TPL / "tools" / "cost.py"), "report",
                            "--project", str(proj), "--json"], capture_output=True, text=True)
        try:
            cost = json.loads(r.stdout)
        except ValueError:
            cost = None
        if cost is None:
            add("WARN", "cost ledger readable", (r.stderr or r.stdout).strip()[:120])
        elif not cost["total"]["runs"]:
            add("WARN", "worker spend recorded in .pmos/costs.jsonl",
                "no runs recorded; the remaining budget is unknown, not zero")
        else:
            spent, budget = cost["total"]["usd"], cost["budget_usd"]
            detail = "$%.2f over %d run(s)%s" % (
                spent, cost["total"]["runs"],
                ", $%.2f of $%.2f budget left" % (cost["remaining_usd"], budget) if budget else "")
            add("FAIL" if budget and spent > budget else "OK", "spend within budget_usd", detail)

    if stage >= 3 and strict:
        jfiles = sorted((pmos / "kb-sources" / "legal").glob("jurisdiction-*.md"))
        for jf in jfiles:
            text = jf.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"as_?of[\s:]+(\d{4}-\d{2}-\d{2})", text, re.I)
            if not m:
                add("FAIL", "%s has an as_of date" % jf.name)
                continue
            try:
                d = date.fromisoformat(m.group(1))
                age = (date.today() - d).days
                add("OK" if age <= 180 else "WARN",
                    "%s as_of fresh (<= 6 months)" % jf.name,
                    "as_of %s, %d days old" % (m.group(1), age))
            except ValueError:
                add("FAIL", "%s as_of parseable" % jf.name, m.group(1))

    if stage >= 4:
        for r in wave2_approved:
            rel = WAVE2_ARTIFACTS[r]
            p = pmos / rel
            add("OK" if p.is_file() and p.stat().st_size >= 100 else "FAIL",
                "%s (%s) present and non-empty" % (rel, r))

    if stage >= 5:
        add("OK" if log_mentions("enrich") else "WARN",
            "log.md records the enrich step",
            "artifacts exist; the log line may be missing")

    if stage >= 6:
        add("OK" if log_mentions("gate 2") else "WARN",
            "log.md records GATE 2 approval",
            "implementation started without a logged GATE 2; confirm with the user")

    if stage >= 7:
        for r in wave3_approved:
            rel = WAVE3_ARTIFACTS[r]
            p = pmos / rel
            add("OK" if p.is_file() and p.stat().st_size >= 100 else "WARN",
                "%s (%s) present" % (rel, r),
                "implementation role; WARN not FAIL (may be mid-wave)")

    if stage >= 8:
        p = pmos / QA_ARTIFACT
        add("OK" if p.is_file() and p.stat().st_size >= 100 else "FAIL",
            "qa/test-report.md present and non-empty")

    if failing_criteria:
        add("WARN", "QA gate: every acceptance criterion passes",
            "failing: %s; rework in wave 3, then re-run the gate"
            % ", ".join(failing_criteria))

    # half-written artifacts anywhere under .pmos/out
    truncated = []
    if (pmos / "out").is_dir():
        for f in (pmos / "out").rglob("*.md"):
            if f.stat().st_size == 0:
                truncated.append(str(f.relative_to(pmos)))
            elif f.stat().st_size < 100:
                truncated.append(str(f.relative_to(pmos)) + " (tiny)")
    add("OK" if not truncated else "WARN", "no empty/truncated artifacts under .pmos/out",
        ", ".join(truncated[:5]) if truncated else "")

    # git state (report only, if a repo)
    r = subprocess.run(["git", "status", "--short"], cwd=str(proj),
                       capture_output=True, text=True)
    dirty = [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []
    outside = [l for l in dirty if not l.split(None, 1)[-1].startswith(".pmos/")]
    add("OK" if not outside else "WARN", "git tree: no modified files outside .pmos/",
        "dirty: %d path(s)" % len(dirty) if dirty else "clean")

    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    else:
        print("Project state: stage %d (%s)" % (out["stage"], out["stage_name"]))
        print("Next step:     %s" % out["next_step"])
        print("Checks:        %d OK, %d WARN, %d FAIL"
              % (sum(1 for c in out["checks"] if c["status"] == "OK"),
                 out["warnings"], out["problems"]))
        for c in out["checks"]:
            line = " [%s] %s" % (c["status"], c["name"])
            if c["detail"]:
                line += "  (%s)" % c["detail"]
            print(line)
    return 0 if out["problems"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
