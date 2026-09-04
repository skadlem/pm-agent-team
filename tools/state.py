#!/usr/bin/env python3
"""PMOS project-state detector: find where a project left off and pre-flight it.

On RESUME (a directory that already has `.pmos/`), the coordinator needs three
answers before touching anything:

  1. WHAT STAGE is the project at?  (which waves/gates have completed)
  2. WAS EVERYTHING FINE up to that stage?  (quick integrity pre-flight)
  3. WHAT IS THE NEXT STEP?  (the ORCHESTRATOR.md step to continue from)

This tool answers all three deterministically from artifacts on disk, so the
answer does not depend on the coordinator remembering anything.

Stage markers (independent evidence on disk, not a chain):

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

The stage is the HIGHEST index whose marker holds. Earlier markers that do
NOT hold are reported as GAPS (warnings), never as a rollback: a project whose
QA gate passed is at stage 8 even if it never wrote team-model.json -- which is
exactly what happens on a host that cannot pin a model per spawn. A pre-flight
check whose evidence belongs to a gap marker is downgraded from FAIL to WARN
for the same reason: it is missing, not broken.

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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from events import read_events, summarize  # noqa: E402  (sibling tool)

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

# lean team (rosters/lean.json waves): planner designs, implementer builds,
# reviewer runs the gate. Wave 3 is the implementer, not an empty map.
LEAN_WAVE2 = {"planner": "out/planner/architecture.md"}
LEAN_WAVE3 = {"implementer": "out/implementer/notes.md"}

# What proves each stage marker, for the gap warnings.
MARKER_EVIDENCE = {
    0: ".pmos/kb.sqlite3",
    1: ".pmos/charter.md",
    2: ".pmos/team-model.json (the GATE 1 model table)",
    3: "kb-sources/legal/jurisdiction-*.md",
    4: "wave 2 artifact for every approved design role",
    5: "enrich line in log.md",
    6: "GATE 2 line in log.md",
    7: "wave 3 implementation artifact",
    8: "QA report with no failing criteria",
    9: "charter + team-model + passing QA",
}

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

# Which stage file the coordinator reads to continue from a given step.
STAGE_FILE = {
    "step 3": "docs/stages/gate1.md",
    "step 4": "docs/stages/gate1.md",
    "step 5": "docs/stages/wave2.md",
    "step 6": "docs/stages/wave2.md",
    "step 7": "docs/stages/wave2.md",
    "step 8": "docs/stages/wave2.md",
    "step 9": "docs/stages/wave3.md",
    "step 10": "docs/stages/wave3.md",
    "step 11": "docs/stages/checkpoint.md",
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

    def artifact_files(rel, any_md=True):
        """Files that count as the artifact `rel`, and whether the named one was
        found. Workers do not reliably use the exact filename: suited's
        implementer wrote notes-002.md .. notes-022.md, qaida's designer wrote
        four *-spec.md files instead of ui-spec.md. Accept the named file, its
        numbered/suffixed siblings, and (when any_md) anything else non-trivial
        the role left in its out/ dir -- the wave demonstrably ran."""
        p = pmos / rel
        if p.is_file() and p.stat().st_size >= 100:
            return [p], True
        d = p.parent
        if not d.is_dir():
            return [], False
        sibs = sorted(f for f in d.glob(p.stem + "*.md") if f.stat().st_size >= 100)
        if sibs or not any_md:
            return sibs, False
        return sorted(f for f in d.glob("*.md") if f.stat().st_size >= 100), False

    team_info = load_json(pmos / "team.json")
    qa_artifact = ("out/reviewer/test-report.md"
                   if isinstance(team_info, dict) and team_info.get("team") == "lean"
                   else QA_ARTIFACT)

    # The QA marker is the most consequential one, so it does NOT accept any
    # stray markdown in the role dir (any_md=False): a screenshot log next to
    # the report is not a gate result.
    qa_reports = artifact_files(qa_artifact, any_md=False)[0]

    def qa_failures():
        """Criteria the QA report marks fail/blocked. A report that exists is not
        a gate that passed: ORCHESTRATOR step 10 sends a failed gate back to
        wave 3, so those ids are what decides whether stage 8 was reached."""
        ids = set()
        for p in qa_reports:
            text = p.read_text(encoding="utf-8", errors="replace")
            ids |= set(re.findall(r"^\s*[-*]\s+(A-\d{1,4})\s*[:\-]\s*(?:fail|blocked)\b",
                                  text, re.I | re.M))
        return sorted(ids)

    failing_criteria = qa_failures()
    qa_passed = bool(qa_reports) and not failing_criteria

    markers = {
        0: exists("kb.sqlite3"),
        1: exists("charter.md"),
        2: exists("team-model.json"),
        # stage 3 exists only in strict mode; in light mode it is N/A (None),
        # which is neither evidence of a stage nor a gap.
        3: (any((pmos / "kb-sources" / "legal").glob("jurisdiction-*.md"))
            if strict else None),
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
        approved_roles = sorted(k for k in team_model
                                if k != "budget_usd" and not k.startswith("_"))

    # lean team: different role names + artifact paths (rosters/lean.json waves)
    is_lean = isinstance(team_info, dict) and team_info.get("team") == "lean"
    wave2_map = LEAN_WAVE2 if is_lean else WAVE2_ARTIFACTS
    wave3_map = LEAN_WAVE3 if is_lean else WAVE3_ARTIFACTS
    if not approved_roles:
        # No GATE 1 table on disk is not proof that no wave ran: a host that
        # cannot pin a model per spawn never writes team-model.json (see
        # hosts/hermes.json). Fall back to the roles that actually produced
        # output -- never to every role in the roster, which would demand
        # artifacts from roles the team never had.
        approved_roles = sorted(d.name for d in (pmos / "out").glob("*") if d.is_dir())

    wave2_approved = [r for r in approved_roles if r in wave2_map]
    markers[4] = bool(wave2_approved) and all(artifact_files(wave2_map[r])[0]
                                              for r in wave2_approved)
    wave3_approved = [r for r in approved_roles if r in wave3_map]
    markers[7] = bool(wave3_approved) and any(artifact_files(wave3_map[r])[0]
                                              for r in wave3_approved)

    # Highest marker that holds -- NOT the longest unbroken prefix. Evidence of
    # a later stage is not erased by a marker nobody wrote on the way there.
    stage = max((s for s in range(10) if markers[s]), default=-1)
    if stage == -1:
        stage = 0  # kb.sqlite3 exists but nothing after; resume at wave 1
    gaps = [s for s in range(stage) if markers[s] is False]
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
    # The protocol is split into stage files; name the one to read next.
    m = re.search(r"step (\d+)", out["next_step"])
    if m and "step %s" % m.group(1) in STAGE_FILE:
        out["read_next"] = STAGE_FILE["step %s" % m.group(1)]

    out["gaps"] = [{"marker": g, "evidence": MARKER_EVIDENCE[g]} for g in gaps]
    for g in gaps:
        add("WARN", "stage marker skipped: no %s" % MARKER_EVIDENCE[g],
            "later evidence puts this project at stage %d (%s); not a rollback"
            % (out["stage"], out["stage_name"]))

    def add_for(marker, status, name, detail=""):
        """A check whose evidence belongs to a SKIPPED marker is a gap, not a
        failure: the stage came from later evidence, so missing paperwork must
        not block a resume."""
        if status == "FAIL" and marker in gaps:
            status = "WARN"
            detail = ((detail + "; " if detail else "")
                      + "skipped marker: %s" % MARKER_EVIDENCE[marker])
        add(status, name, detail)

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
            add_for(1, "OK" if p.is_file() and p.stat().st_size >= 100 else "FAIL",
                    "%s present and non-empty" % rel)
        add_for(1, "OK" if exists("log.md") else "FAIL", "log.md exists")

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
            bad = [k for k in tm
                   if k != "budget_usd" and not k.startswith("_")
                   and not isinstance(tm[k], dict)]
            add_for(2, "OK" if not bad and approved_roles else "FAIL",
                    "team-model.json valid (roles + budget_usd)",
                    "budget_usd=%s, roles=%s" % (tm.get("budget_usd"),
                                                 ",".join(approved_roles) or "-"))
        else:
            add_for(2, "FAIL", "team-model.json valid JSON")
        add_for(2, "OK" if exists("team-model-ladder.json") else "FAIL",
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
        for role in wave2_approved:
            rel = wave2_map[role]
            files, named = artifact_files(rel)
            if named:
                add_for(4, "OK", "%s (%s) present and non-empty" % (rel, role))
            elif files:
                add("WARN", "%s (%s) present and non-empty" % (rel, role),
                    "role produced %s instead of the named artifact"
                    % ", ".join(f.name for f in files[:3]))
            else:
                add_for(4, "FAIL", "%s (%s) present and non-empty" % (rel, role))

    if stage >= 5:
        add("OK" if log_mentions("enrich") else "WARN",
            "log.md records the enrich step",
            "artifacts exist; the log line may be missing")

    if stage >= 6:
        add("OK" if log_mentions("gate 2") else "WARN",
            "log.md records GATE 2 approval",
            "implementation started without a logged GATE 2; confirm with the user")

    if stage >= 7:
        for role in wave3_approved:
            rel = wave3_map[role]
            files, named = artifact_files(rel)
            add("OK" if files else "WARN", "%s (%s) present" % (rel, role),
                ("%d file(s): %s" % (len(files), ", ".join(f.name for f in files[:3]))
                 if files and not named else
                 "" if named else "implementation role; WARN not FAIL (may be mid-wave)"))

    if stage >= 8:
        add_for(8, "OK" if qa_reports else "FAIL",
                "%s present and non-empty" % qa_artifact,
                ", ".join(f.name for f in qa_reports[:3]))

    if qa_reports and stage >= 7:
        # A gate is only evidence for the tree it ran against (the stale-evidence
        # rule, applied to the clock rather than the fingerprint).
        newest_qa = max(f.stat().st_mtime for f in qa_reports)
        newer = sorted(f.name for role in wave3_approved
                       for f in artifact_files(wave3_map[role])[0]
                       if f.stat().st_mtime > newest_qa)
        if newer:
            add("WARN", "QA report is the newest evidence",
                "%d implementation artifact(s) changed after the gate (%s); re-run the "
                "gate before treating it as passed" % (len(newer), ", ".join(newer[:3])))

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

    # wave-event trace (informational: how the team has been running so far)
    events = read_events(proj)
    if events:
        ev = summarize(events)
        out["events"] = {"runs": ev["runs"], "ok": ev["ok"], "failed": ev["failed"],
                         "ladder_retries": ev["ladder_retries"],
                         "rework_loops": ev["rework_loops"], "decision": ev["decision"]}
        add("OK" if not ev["rework_loops"] else "WARN",
            "wave-event trace healthy (.pmos/waves.jsonl)",
            "%d run(s), %d failed, %d ladder retry(ies), %d rework loop(s), decision: %s"
            % (ev["runs"], ev["failed"], ev["ladder_retries"], ev["rework_loops"],
               ev["decision"]))
        if ev["decision"] == "replan":
            add("WARN", "replan recommended (L-4)",
                "QA sent work back twice: stop retrying the ladder, re-split or re-plan "
                "the failing task before another run (docs/stages/spawn-fallback.md)")
        elif ev["decision"] == "escalate":
            add("FAIL", "stall: escalate to the user (Magentic-One pattern)",
                "three or more rework loops - the replan did not break the loop. STOP: present "
                "the failure story and a re-plan proposal to the user; do not spawn again without "
                "an explicit user decision (docs/stages/spawn-fallback.md)")

    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    else:
        print("Project state: stage %d (%s)" % (out["stage"], out["stage_name"]))
        print("Next step:     %s" % out["next_step"])
        if out.get("read_next"):
            print("Read next:     TPL/%s  (plus TPL/ORCHESTRATOR.md core rules)" % out["read_next"])
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
