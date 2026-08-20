#!/usr/bin/env python3
"""PMOS template self-check. Run from anywhere:

    python tools/validate.py

Exits non-zero if anything is broken. Covers: budget math, skill references,
model-suggestion coverage, documented CLI commands vs the real parser, skill
frontmatter, a full bootstrap with absolute paths, and query edge cases.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

TPL = pathlib.Path(__file__).resolve().parent.parent
_failures = 0
_skips = 0


def check(label, cond, detail=""):
    global _failures
    print(f"  [{'OK' if cond else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        _failures += 1


def skip(label, reason):
    global _skips
    print(f"  [SKIP] {label}  ({reason})")
    _skips += 1


print("== 1. KB budget math ==")
cfg = json.loads((TPL / "config.json").read_text(encoding="utf-8"))
total = cfg["kb"]["total_token_cap"]
shared = cfg["kb"]["shared_token_budget"]
weights = cfg["kb"]["role_weights"]
pool = total - shared
role_sum = sum(int(w * pool) for w in weights.values())
check("role budgets + shared == total cap", shared + role_sum == total, f"{shared}+{role_sum}={total}")
check("weights sum to 1.0", abs(sum(weights.values()) - 1.0) < 1e-9)
check("total cap positive", total > 0)

cost_cfg = cfg.get("cost") or {}
check("cost cap positive", (cost_cfg.get("max_project_cost_usd") or 0) > 0)
check("est_tokens_per_worker positive", (cost_cfg.get("est_tokens_per_worker") or 0) > 0)
mfb = (cfg.get("context_rules") or {}).get("max_fallbacks_per_task")
check("max_fallbacks_per_task is a positive int", isinstance(mfb, int) and mfb > 0, str(mfb))

print("== 2. Referenced skills are loadable ==")
roster = json.loads((TPL / "roster.json").read_text(encoding="utf-8"))
referenced = set(roster["common_skills"])
for r in roster["roles"].values():
    referenced.update(r["skills"])
found = set()
bases = [os.path.expanduser("~/.jcode"), os.path.expanduser("~/.agents"),
         os.path.expanduser("~/.claude/plugins/cache")]
for base in bases:
    for root, dirs, files in os.walk(base):
        if "SKILL.md" in files:
            found.add(os.path.basename(root))
if not any(os.path.isdir(b) for b in bases):
    skip("referenced skills loadable", "no jcode/claude skill dirs on this machine (fresh CI clone)")
elif not found:
    skip("referenced skills loadable", "skill dirs exist but are empty; cannot verify")
else:
    missing = sorted(s for s in referenced if s not in found)
    check("all {} referenced skills loadable".format(len(referenced)), not missing,
          ", ".join(missing) if missing else "")

print("== 3. Model suggestions cover roster ==")
bench = json.loads((TPL / "benchmarks.json").read_text(encoding="utf-8"))
valid_purposes = {p for m in bench.get("models", {}).values() for p in (m.get("scores") or {})}
ms = {k: v for k, v in roster["model_suggestions"].items() if isinstance(v, dict) and "purpose" in v}
check("model purposes == roster roles", set(ms) == set(roster["roles"]))
bad = []
for r, v in ms.items():
    if not v.get("purpose"):
        bad.append(r)
    elif not set(v["purpose"]) <= valid_purposes:
        bad.append(r)
    elif abs(sum(v["purpose"].values()) - 1.0) > 1e-9:
        bad.append(f"{r}(weights={sum(v['purpose'].values())})")
check("all purpose maps well-formed (weights sum to 1, valid purposes)", not bad, ", ".join(bad) if bad else "")

tiers = roster.get("role_tiers") or {}
tier_roles = {k for k in tiers if k != "note"}
check("role_tiers cover every role", tier_roles == set(roster["roles"]),
      "missing: " + ", ".join(sorted(set(roster["roles"]) - tier_roles)) or "")
bad_tier = [k for k, v in tiers.items() if k != "note" and not (0.5 <= v <= 1.0)]
check("role_tiers in [0.5, 1.0]", not bad_tier, ", ".join(bad_tier))
efforts = roster.get("role_effort") or {}
eff_roles = {k for k in efforts if k != "note"}
check("role_effort covers every role", eff_roles == set(roster["roles"]),
      "missing: " + ", ".join(sorted(set(roster["roles"]) - eff_roles)) or "")
allowed_efforts = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
bad_eff = [k for k, v in efforts.items() if k != "note" and v not in allowed_efforts]
check("role_effort values valid", not bad_eff, ", ".join(bad_eff))

print("== 4. Documented kb.py commands exist in the CLI ==")
kb_src = (TPL / "tools" / "kb.py").read_text(encoding="utf-8")
verbs = set(re.findall(r'sub\.add_parser\("([\w-]+)"\)', kb_src))
docs = []
for p in list((TPL / "skills").rglob("*.md")) + [TPL / "ORCHESTRATOR.md", TPL / "README.md"]:
    docs.append(p.read_text(encoding="utf-8"))
cmds = set(re.findall(r"kb\.py\s+(?:[\w-]+)", "\n".join(docs)))
used = {c.split("kb.py ")[1] for c in cmds}
unknown = sorted(v for v in used if v not in verbs)
check("all documented subcommands exist", not unknown, ", ".join(unknown) if unknown else "")

print("== 5. Skill frontmatter ==")
for skill in sorted((TPL / "skills").iterdir()):
    if not skill.is_dir():
        continue
    md = (skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\nname:\s*(\S+)\ndescription:\s*\"(.+)\"\n---", md, re.S)
    check(skill.name, bool(m and m.group(1) == skill.name and len(m.group(2)) > 40))

print("== 6. Full bootstrap with absolute paths (temp DB) ==")
tmp = pathlib.Path(tempfile.mkdtemp())
DB = tmp / "kb.sqlite3"
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "init", "--db", str(DB)],
                   capture_output=True, text=True)
check("init", r.returncode == 0)
for ns in ["shared", "pm", "architect", "backend", "frontend", "designer",
           "business", "marketing", "qa", "devops", "legal"]:
    r = subprocess.run(
        [sys.executable, str(TPL / "tools" / "kb.py"), "add-dir", "--db", str(DB),
         "--ns", ns, "--path", str(TPL / "kb-sources" / ns),
         "--priority", "10" if ns == "shared" else "8"],
        capture_output=True, text=True)
    check(f"add-dir {ns}", r.returncode == 0 and "indexed" in r.stdout, r.stderr.strip()[:80])
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "budget", "--db", str(DB),
                    "--config", str(TPL / "config.json")], capture_output=True, text=True)
check("budget", r.returncode == 0 and "shared" in r.stdout)

print("== 6b. State detector (stage detection + pre-flight) ==")
st = tmp / "proj"
(st / ".pmos" / "plans").mkdir(parents=True)
(st / ".pmos" / "out" / "pm").mkdir(parents=True)
(st / "config.json").write_text(json.dumps({"legal_strict": False}))
subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "init", "--db", str(st / ".pmos" / "kb.sqlite3")],
               capture_output=True)
(st / ".pmos" / "charter.md").write_text("# C\n" + "x" * 200)
(st / ".pmos" / "plans" / "plan.md").write_text("# P\n" + "y" * 200)
(st / ".pmos" / "team-model.json").write_text(json.dumps({"architect": {"model": "m", "effort": "low"},
                                                          "designer": {"model": "m", "effort": "low"},
                                                          "budget_usd": 20.0}))
(st / ".pmos" / "team-model-ladder.json").write_text(json.dumps({"architect": ["m"]}))
for role, rel in [("architect", "architecture.md"), ("designer", "ui-spec.md")]:
    (st / ".pmos" / "out" / role).mkdir(parents=True)
    (st / ".pmos" / "out" / role / rel).write_text("# %s\n" % role + "z" * 200)
(st / ".pmos" / "log.md").write_text("## GATE 1\nok\n## Enrich\ndone\n## GATE 2\nok\n")

def state_out(project):
    r = subprocess.run([sys.executable, str(TPL / "tools" / "state.py"), "--project", str(project),
                        "--config", str(project / "config.json"), "--json"],
                       capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, {}

rc, so = state_out(st)
check("state.py detects GATE 2 passed (light legal)", so.get("stage") == 5 and rc == 0,
      "stage=%s rc=%s" % (so.get("stage"), rc))

# rollback: delete a wave-2 artifact -> stage must roll back to 2, exit 0
broken = tmp / "proj-broken"
subprocess.run(["cp", "-r", str(st), str(broken)])
(broken / ".pmos" / "out" / "architect" / "architecture.md").unlink()
rc, so = state_out(broken)
check("state.py rolls back when a marker artifact vanished",
      so.get("stage") == 2, "stage=%s rc=%s" % (so.get("stage"), rc))

rc, so = state_out(tmp / "no-pmos")
check("state.py fresh dir -> has_pmos false", so.get("has_pmos") is False, "")

print("== 7. Query edge cases (must not crash) ==")
for label, q in [("garbage", "zzzznonsensequery"), ("empty", ""),
                 ("FTS special chars", 'C++ "quoted" (fast) [beta] *star*')]:
    r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "search", "--db", str(DB), q, "-k", "3"],
                       capture_output=True, text=True)
    check(f"search: {label}", r.returncode == 0)
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "add", "--db", str(DB),
                    "--ns", "pm", "--title", "Test fact", "--kind", "web",
                    "--source", "https://example.com", "--priority", "4",
                    "--content", "A test fact block."], capture_output=True, text=True)
check("web-kind add (bootstrap top-up command)", r.returncode == 0)

print("== 8. selftest ==")
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "selftest"],
                   capture_output=True, text=True)
check("selftest", r.returncode == 0 and "SELFTEST PASS" in r.stdout)

print("== 9. Referenced TPL paths exist ==")
docs = []
for p in list((TPL / "skills").rglob("*.md")) + [TPL / "ORCHESTRATOR.md", TPL / "README.md"]:
    docs.append(p.read_text(encoding="utf-8"))
for ref in sorted({m.group(1) for m in re.finditer(r"TPL/([\w./<>-]+)", "\n".join(docs))}):
    if "<" in ref or ">" in ref or "..." in ref:
        continue
    check(f"TPL/{ref}", (TPL / ref).exists())

print("== 10. Model recommender ==")
# fixture available list (subset of the machine's real swarm list_models output)
fixture = TPL / "_fixture_models.txt"
fixture.write_text(
    "- claude-fable-5 via Anthropic [claude-oauth]\n"
    "- claude-opus-5 via Anthropic [claude-oauth]\n"
    "- claude-opus-4-7 via Anthropic [claude-oauth]\n"
    "- claude-sonnet-5 via Anthropic [claude-oauth]\n"
    "- deepseek-v4-pro via DeepSeek [openai-compatible:deepseek] (https://api.deepseek.com)\n"
    "- qwen3.8-max via qwen [openai-compatible:qwen] (https://example.com/v1)\n"
    "- gpt-5.6-pro via OpenAI [openai-api-key] [unavailable] (requires OPENAI_API_KEY)\n",
    encoding="utf-8")
r = subprocess.run([sys.executable, str(TPL / "tools" / "recommend.py"), "--available", str(fixture)],
                   capture_output=True, text=True)
check("recommend runs", r.returncode == 0, r.stderr.strip()[:80])
out = r.stdout
check("every role gets a suggestion", all(f"{role} " in out for role in roster["roles"]))
check("unavailable models excluded", "gpt-5.6-pro " not in out)
check("newest-only drops older generations", "claude-opus-4-7 " not in out)
# semantic check: the suggested model per role must be in the best tier and cheapest of it
import importlib.util
spec = importlib.util.spec_from_file_location("recommend_mod", str(TPL / "tools" / "recommend.py"))
rmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rmod)
bench = json.loads((TPL / "benchmarks.json").read_text(encoding="utf-8"))["models"]
avail = [{"id": "claude-fable-5", "available": True}, {"id": "claude-opus-5", "available": True},
         {"id": "deepseek-v4-pro", "available": True}, {"id": "qwen3.8-max", "available": True}]
res = rmod.recommend(avail, bench, roster, 0.92)
for rr in res:
    if not rr["suggested"]:
        continue
    scores = {}
    # mirror recommend()'s forbidden_models filter so the "expected" cheapest
    # model is computed over the same set recommend actually suggests from
    forbid = set()
    for f in (roster.get("forbidden_models") or []):
        if f.endswith("*"):
            forbid.update(m["id"] for m in avail if m["id"].startswith(f[:-1]))
        else:
            forbid.add(f)
    for mid in avail:
        if mid["id"] in forbid:
            continue
        bmid = rmod.normalize_id(mid["id"])
        e = bench.get(bmid)
        if e:
            s = sum(w * (e["scores"].get(p, 0.0)) for p, w in rr["purpose"].items())
            scores[mid["id"]] = (s, rmod.blended_cost(e))
    best = max(s for s, _ in scores.values())
    r_tier = (roster.get("role_tiers") or {}).get(rr["role"], 0.92)
    tier = {m: d for m, d in scores.items() if d[0] >= r_tier * best}
    cheapest = min(tier, key=lambda m: (tier[m][1] is None, tier[m][1] or 0.0, -tier[m][0]))
    check(f"{rr['role']} suggestion is best-tier cheapest", rr["suggested"] == cheapest,
          f"{rr['suggested']} vs {cheapest}")
fixture.unlink()
r = subprocess.run([sys.executable, str(TPL / "tools" / "recommend.py"), "refresh"],
                   capture_output=True, text=True)
check("recommend refresh prints queries", r.returncode == 0 and "websearch" in r.stdout)

print("== 11. Benchmarks: bundled file integrity + generator ==")
# The shipped benchmarks.json must be complete even without the raw CSVs.
bundled = json.loads((TPL / "benchmarks.json").read_text(encoding="utf-8"))
check("bundled benchmarks.json models > 100", len(bundled.get("models", {})) > 100,
      str(len(bundled.get("models", {}))))
check("bundled purposes complete",
      {"coding", "reasoning", "design", "ops", "verification", "business", "marketing", "writing"} <= set(bundled.get("purposes", [])))
for m in ["claude-fable-5", "qwen3.8-max", "deepseek-v4-pro"]:
    e = bundled["models"].get(m)
    check(f"bundled key model {m} present", bool(e and e["scores"]))
# Regeneration check only when the raw Epoch data is available (it is gitignored;
# see README for how to obtain it).
data_dir = TPL.parent / "benchmark_data"
if not data_dir.is_dir():
    skip("benchmark generator (Epoch data)", f"no {data_dir} on this clone (raw CSVs are gitignored)")
else:
    gen_out = TPL / "_benchmarks_gen.json"
    r = subprocess.run([sys.executable, str(TPL / "tools" / "build_benchmarks.py"),
                        "--data-dir", str(data_dir), "--out", str(gen_out)],
                       capture_output=True, text=True)
    check("build_benchmarks runs", r.returncode == 0, r.stderr.strip()[:80])
    gb = json.loads(gen_out.read_text(encoding="utf-8"))
    check("generated models > 100", len(gb["models"]) > 100, str(len(gb["models"])))
    check("generated purposes complete", {"coding", "reasoning", "design", "ops", "verification", "business", "marketing", "writing"} <= set(gb["purposes"]))
    for m in ["claude-fable-5", "qwen3.8-max", "deepseek-v4-pro"]:
        e = gb["models"].get(m)
        check(f"generated key model {m} present", bool(e and e["scores"]))
    gen_out.unlink()

print("== 12. Idempotent re-add / reindex / installer ==")

def ns_chunks(ns):
    """Actual chunk count for a namespace, from stats --json."""
    r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "stats", "--db", str(DB),
                        "--json"], capture_output=True, text=True)
    return next((d["chunks"] for d in json.loads(r.stdout) if d["ns"] == ns), 0)

# Re-adding the same dir must replace chunks in place, not stack a second copy
# beside the stale one (a re-run of pm-kb-enrich after any scope change).
before = ns_chunks("pm")
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "add-dir", "--db", str(DB),
                    "--ns", "pm", "--path", str(TPL / "kb-sources" / "pm"), "--priority", "8"],
                   capture_output=True, text=True)
after = ns_chunks("pm")
check("re-add same dir does not duplicate", before == after and before > 0, f"{before} vs {after}")
check("re-add reports updates, not inserts", "0 new," in r.stdout and "0 pruned" in r.stdout,
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output")

# A section deleted from a source file must leave the KB on the next index pass
pruned_dir = tmp / "prunable"
pruned_dir.mkdir()
(pruned_dir / "facts.md").write_text("## Alpha fact\nOne.\n\n## Beta fact\nTwo.\n", encoding="utf-8")
add_prunable = [sys.executable, str(TPL / "tools" / "kb.py"), "add-dir", "--db", str(DB),
                "--ns", "qa", "--path", str(pruned_dir), "--glob", "*.md", "--priority", "8"]
base = ns_chunks("qa")
subprocess.run(add_prunable, capture_output=True, text=True)
check("add-dir indexes both sections", ns_chunks("qa") == base + 2)
(pruned_dir / "facts.md").write_text("## Alpha fact\nOne.\n", encoding="utf-8")
r = subprocess.run(add_prunable, capture_output=True, text=True)
check("deleted section is pruned on re-index", ns_chunks("qa") == base + 1 and "1 pruned" in r.stdout,
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output")
r = subprocess.run(add_prunable + ["--no-prune"], capture_output=True, text=True)
check("--no-prune keeps vanished sections", "0 pruned" in r.stdout)
subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "clear", "--db", str(DB),
                "--ns", "qa"], capture_output=True, text=True)
subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "add-dir", "--db", str(DB),
                "--ns", "qa", "--path", str(TPL / "kb-sources" / "qa"), "--priority", "8"],
               capture_output=True, text=True)
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "reindex-vectors", "--db", str(DB)],
                   capture_output=True, text=True)
check("reindex-vectors offline", r.returncode == 0 and "offline" in r.stdout)
if os.name == "nt":
    r = subprocess.run(["cmd", "/c", "install.cmd"], capture_output=True, text=True, cwd=TPL)
    check("install.cmd idempotent", r.returncode == 0)
    root = pathlib.Path(os.path.expanduser("~/.jcode/pmos-template-root"))
    check("template-root file", root.exists() and root.read_text().strip().rstrip("\\/") == str(TPL).rstrip("\\/"))

print("== 13. Artifact id schema (ids, references, linter) ==")
ART = TPL / "tools" / "artifacts.py"
r = subprocess.run([sys.executable, str(ART), "selftest"], capture_output=True, text=True)
check("artifacts.py selftest", r.returncode == 0 and "SELFTEST PASS" in r.stdout,
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:80])

# the templates must actually carry the conventions the linter enforces
tpl_checks = [
    ("charter defines R ids", TPL / "templates" / "charter.md", r"^-\s*R-\d{3}:"),
    ("brownfield charter defines R ids", TPL / "templates" / "charter-brownfield.md", r"^-\s*R-\d{3}:"),
    ("plan defines T blocks", TPL / "templates" / "plan.md", r"^-\s*id:\s*T-\d{3}"),
    ("plan defines A blocks", TPL / "templates" / "plan.md", r"^-\s*id:\s*A-\d{3}"),
    ("plan tasks carry satisfies", TPL / "templates" / "plan.md", r"^\s+satisfies:"),
    ("plan criteria carry verifies", TPL / "templates" / "plan.md", r"^\s+verifies:"),
    ("adr heading carries its id", TPL / "templates" / "adr.md", r"^#\s*ADR-"),
    ("adr declares supersedes", TPL / "templates" / "adr.md", r"^Supersedes:"),
    ("risk register carries mitigated_by",
     TPL / "kb-sources" / "legal" / "risk-register-template.md", r"^\s+mitigated_by:"),
]
for label, path, pattern in tpl_checks:
    check(label, bool(re.search(pattern, path.read_text(encoding="utf-8"), re.M)))

# doc and code must agree on the vocabulary
art_src = ART.read_text(encoding="utf-8")
schema_doc = (TPL / "ARTIFACT-SCHEMA.md").read_text(encoding="utf-8")
fields = set(re.findall(r'^    "(\w+)": \("\w+", "\w+"\),', art_src, re.M))
undocumented = sorted(f for f in fields if f"`{f}`" not in schema_doc)
check("every reference field is documented", not undocumented and len(fields) >= 6,
      ", ".join(undocumented) if undocumented else f"{len(fields)} fields")
prefixes = set(re.findall(r'^    "\w+": "([A-Z]+)",', art_src, re.M))
missing = sorted(p for p in prefixes if f"`{p}-NNN`" not in schema_doc)
check("every id prefix is documented", not missing and len(prefixes) >= 5,
      ", ".join(missing) if missing else f"{len(prefixes)} prefixes")

# a project assembled straight from the templates must lint without ERRORS
art_proj = tmp / "artproj"
(art_proj / ".pmos" / "plans").mkdir(parents=True)
(art_proj / ".pmos" / "decisions").mkdir(parents=True)
shutil.copyfile(TPL / "templates" / "charter.md", art_proj / ".pmos" / "charter.md")
shutil.copyfile(TPL / "templates" / "plan.md", art_proj / ".pmos" / "plans" / "plan.md")
shutil.copyfile(TPL / "templates" / "adr.md", art_proj / ".pmos" / "decisions" / "ADR-001.md")
r = subprocess.run([sys.executable, str(ART), "--project", str(art_proj), "--json"],
                   capture_output=True, text=True)
lint = json.loads(r.stdout) if r.stdout.strip() else {}
check("templates lint with no errors", r.returncode == 0 and not lint.get("errors"),
      "; ".join(e["message"] for e in lint.get("errors", []))[:120])
check("unfilled placeholders are warned about",
      any("placeholder" in w["message"] for w in lint.get("warnings", [])))
r = subprocess.run([sys.executable, str(ART), "--project", str(art_proj), "--strict"],
                   capture_output=True, text=True)
check("--strict fails on warnings", r.returncode == 2, f"rc={r.returncode}")

# graph export: the substrate the traceability graph is built from
gpath = art_proj / "graph.json"
subprocess.run([sys.executable, str(ART), "--project", str(art_proj), "--graph", str(gpath)],
               capture_output=True, text=True)
graph = json.loads(gpath.read_text(encoding="utf-8")) if gpath.exists() else {}
check("--graph writes nodes and edges",
      bool(graph.get("nodes")) and "edges" in graph
      and {n["kind"] for n in graph["nodes"]} <= {"requirement", "task", "acceptance", "decision", "risk"},
      f"{len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")

# a broken project must fail, or the linter is decoration
broken = tmp / "brokenproj"
(broken / ".pmos" / "plans").mkdir(parents=True)
(broken / ".pmos" / "charter.md").write_text("# C\n- R-001: real requirement\n", encoding="utf-8")
(broken / ".pmos" / "plans" / "plan.md").write_text(
    "```yaml\n- id: T-001\n  title: t\n  satisfies: R-404\n```\n", encoding="utf-8")
r = subprocess.run([sys.executable, str(ART), "--project", str(broken)], capture_output=True, text=True)
check("dangling reference fails the lint", r.returncode == 1 and "R-404" in r.stdout,
      f"rc={r.returncode}")

print("== 14. Traceability join (project graph x code graph) ==")
TRACE = TPL / "tools" / "trace.py"
r = subprocess.run([sys.executable, str(TRACE), "selftest"], capture_output=True, text=True)
check("trace.py selftest", r.returncode == 0 and "SELFTEST PASS" in r.stdout,
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:80])

trace_src = TRACE.read_text(encoding="utf-8")
verbs = set(re.findall(r'sub\.add_parser\("([\w-]+)"', trace_src))
docs = "\n".join((TPL / d).read_text(encoding="utf-8")
                 for d in ["README.md", "ORCHESTRATOR.md", "ARTIFACT-SCHEMA.md"])
used = {m.group(1) for m in re.finditer(r"trace\.py\s+([\w-]+)", docs)}
unknown = sorted(v for v in used if v not in verbs)
check("all documented trace.py subcommands exist", not unknown and len(used) >= 3,
      ", ".join(unknown) if unknown else f"{len(used)} documented")

# the queries must run on a real project tree, with and without a code graph
tr_proj = tmp / "traceproj"
(tr_proj / ".pmos" / "plans").mkdir(parents=True)
(tr_proj / ".pmos" / "out" / "qa").mkdir(parents=True)
(tr_proj / "src" / "auth").mkdir(parents=True)
(tr_proj / ".pmos" / "charter.md").write_text(
    "# C\n- R-001: reset password\n- R-002: unplanned scope\n", encoding="utf-8")
(tr_proj / ".pmos" / "plans" / "plan.md").write_text(
    "```yaml\n- id: T-001\n  title: reset endpoint\n  satisfies: R-001\n  touches: src/auth\n"
    "- id: A-001\n  title: mail arrives\n  verifies: T-001\n```\n", encoding="utf-8")
(tr_proj / ".pmos" / "out" / "qa" / "test-report.md").write_text("- A-001: pass - green\n",
                                                                 encoding="utf-8")
(tr_proj / "graphify-out").mkdir()
(tr_proj / "graphify-out" / "graph.json").write_text(json.dumps({
    "nodes": [{"id": "n1", "source_file": "src/auth/reset.py", "file_type": "code"},
              {"id": "n2", "source_file": "src/api.py", "file_type": "code"}],
    "links": [{"source": "n2", "target": "n1", "relation": "imports"}],
    "built_at_commit": "cafe"}), encoding="utf-8")

r = subprocess.run([sys.executable, str(TRACE), "coverage", "--project", str(tr_proj), "--json"],
                   capture_output=True, text=True)
cov = json.loads(r.stdout) if r.stdout.strip() else {}
check("coverage counts planned vs unplanned scope",
      cov.get("summary", {}).get("requirements") == 2 and cov["summary"]["planned"] == 1
      and any("R-002" in g for g in cov.get("gaps", [])),
      json.dumps(cov.get("summary", {})))

r = subprocess.run([sys.executable, str(TRACE), "impact", "T-001", "--project", str(tr_proj),
                    "--json"], capture_output=True, text=True)
imp = json.loads(r.stdout) if r.stdout.strip() else {}
check("impact joins a task to its code and QA",
      imp.get("touches") == ["src/auth/reset.py"]
      and imp.get("satisfies", [{}])[0].get("id") == "R-001"
      and imp.get("verified_by", [{}])[0].get("qa") == "pass"
      and any(x["file"] == "src/api.py" for x in imp.get("referenced_by", [])),
      ", ".join(imp.get("touches", [])))

r = subprocess.run([sys.executable, str(TRACE), "impact", "T-404", "--project", str(tr_proj)],
                   capture_output=True, text=True)
check("impact on an unknown id exits non-zero", r.returncode == 1)

gout = tr_proj / "trace.json"
r = subprocess.run([sys.executable, str(TRACE), "export", "--project", str(tr_proj),
                    "--out", str(gout)], capture_output=True, text=True)
g = json.loads(gout.read_text(encoding="utf-8")) if gout.exists() else {}
check("export joins file nodes into the graph",
      any(n["kind"] == "file" for n in g.get("nodes", []))
      and any(e["kind"] == "touches" for e in g.get("edges", []))
      and g.get("code_graph", {}).get("commit") == "cafe")

(tr_proj / "graphify-out" / "graph.json").unlink()
r = subprocess.run([sys.executable, str(TRACE), "coverage", "--project", str(tr_proj)],
                   capture_output=True, text=True)
check("queries work without a code graph", r.returncode == 0 and "T-001" in r.stdout,
      r.stderr.strip()[:80])

print("== 15. Protocol harness fixtures ==")
FIXTURES = TPL / "tests" / "fixtures"
names = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()) if FIXTURES.is_dir() else []
check("fixtures present", len(names) >= 3, ", ".join(names))
# read the key set from the harness itself: a second copy here would rot
EXPECT_KEYS = set(re.findall(r'"(\w+)"',
                             re.search(r"EXPECT_KEYS = \{(.+?)\}",
                                       (TPL / "tools" / "eval_project.py").read_text(encoding="utf-8"),
                                       re.S).group(1)))
check("harness expect keys readable", len(EXPECT_KEYS) >= 6, ", ".join(sorted(EXPECT_KEYS)))
for name in names:
    d = FIXTURES / name
    exp = d / "expect.json"
    if not exp.is_file():
        check(f"{name}: expect.json", False, "missing")
        continue
    try:
        e = json.loads(exp.read_text(encoding="utf-8"))
    except ValueError as err:
        check(f"{name}: expect.json parses", False, str(err)[:60])
        continue
    unknown = sorted(set(e) - EXPECT_KEYS)
    check(f"{name}: fixture well-formed",
          not unknown and len(e.get("description", "")) > 20 and (d / "pmos").is_dir()
          and (d / "pmos" / "charter.md").is_file(),
          ", ".join(unknown) if unknown else "")
# a fixture whose .pmos were literally named .pmos would be swallowed by the template .gitignore
dotted = [n for n in names if (FIXTURES / n / ".pmos").exists()]
check("fixtures keep pmos/ undotted (gitignore-safe)", not dotted, ", ".join(dotted))
r = subprocess.run(["git", "check-ignore"] + [str(FIXTURES / n) for n in names],
                   cwd=str(TPL), capture_output=True, text=True)
check("no fixture is gitignored", not r.stdout.strip(), r.stdout.strip()[:80])

print("== 16. Spend ledger ==")
COST = TPL / "tools" / "cost.py"
r = subprocess.run([sys.executable, str(COST), "selftest"], capture_output=True, text=True)
check("cost.py selftest", r.returncode == 0 and "SELFTEST PASS" in r.stdout,
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:80])
cost_src = COST.read_text(encoding="utf-8")
verbs = set(re.findall(r'sub\.add_parser\("([\w-]+)"', cost_src))
docs = "\n".join((TPL / d).read_text(encoding="utf-8") for d in ["README.md", "ORCHESTRATOR.md"])
used = {m.group(1) for m in re.finditer(r"cost\.py\s+([\w-]+)", docs)}
unknown = sorted(v for v in used if v not in verbs)
check("all documented cost.py subcommands exist", not unknown and len(used) >= 3,
      ", ".join(unknown) if unknown else f"{len(used)} documented")
# an empty project must report "unknown", never "zero spent"
cost_proj = tmp / "costproj"
(cost_proj / ".pmos").mkdir(parents=True)
(cost_proj / ".pmos" / "team-model.json").write_text(
    json.dumps({"backend": {"model": "claude-opus-5"}, "budget_usd": 10}), encoding="utf-8")
r = subprocess.run([sys.executable, str(COST), "report", "--project", str(cost_proj), "--json"],
                   capture_output=True, text=True)
empty = json.loads(r.stdout)
check("empty ledger reports zero runs, not zero cost",
      empty["total"]["runs"] == 0 and empty["budget_usd"] == 10 and r.returncode == 0)
r = subprocess.run([sys.executable, str(COST), "estimate", "--project", str(cost_proj),
                    "--roles", "backend", "--json"], capture_output=True, text=True)
est = json.loads(r.stdout)
check("estimate falls back to the flat config default without history",
      est["workers"][0]["basis"] == "flat config estimate" and est["workers"][0]["usd"] > 0,
      json.dumps(est["workers"][0]))

print("== 17. Knowledge graph (triples + SPARQL subset) ==")
KG = TPL / "tools" / "kg.py"
r = subprocess.run([sys.executable, str(KG), "selftest"], capture_output=True, text=True)
check("kg.py selftest", r.returncode == 0 and "SELFTEST PASS" in r.stdout,
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:80])

schema_doc = (TPL / "ARTIFACT-SCHEMA.md").read_text(encoding="utf-8")
kg_src = KG.read_text(encoding="utf-8")
classes = set(re.findall(r'"\w+": "(\w+)"', re.search(r"CLASS_OF = \{(.+?)\}", kg_src, re.S).group(1)))
undocumented = sorted(c for c in classes if f"pmos:{c}" not in schema_doc)
check("every RDF class is documented", not undocumented and len(classes) >= 6,
      ", ".join(undocumented) if undocumented else f"{len(classes)} classes")
preds = set(re.findall(r'"\w+": "(\w+)"', re.search(r"PREDICATE_OF = \{(.+?)\}", kg_src, re.S).group(1)))
preds |= set(re.findall(r'"\w+": "(\w+)"', re.search(r"INVERSE = \{(.+?)\}", kg_src, re.S).group(1)))
undocumented = sorted(p for p in preds if f"pmos:{p}" not in schema_doc)
check("every RDF predicate is documented", not undocumented,
      ", ".join(undocumented) if undocumented else f"{len(preds)} predicates")

# The stored SPARQL library and the Python linter are two independent
# implementations of the same protocol checks. They must agree on every fixture.
sys.path.insert(0, str(TPL / "tools"))
import eval_project as harness  # noqa: E402

def ids_from(payload, var):
    return sorted(b[var]["value"].rsplit("#", 1)[-1]
                  for b in payload["results"]["bindings"] if var in b)

def warned_ids(lint, needle):
    return sorted({m.group(1) for w in lint["warnings"]
                   for m in [re.match(r"([A-Z]+-\d+)", w["message"])]
                   if m and needle in w["message"]})

fixture_names = sorted(p.name for p in (TPL / "tests" / "fixtures").iterdir()
                       if (p / "expect.json").is_file())
agreements = 0
for name in fixture_names:
    fx = TPL / "tests" / "fixtures" / name
    exp = json.loads((fx / "expect.json").read_text(encoding="utf-8"))
    dest = pathlib.Path(tempfile.mkdtemp()) / "proj"
    harness.materialize(fx, dest, exp.get("legal_strict", True))
    harness.apply_dirty(dest, exp.get("dirty", []))
    lint = json.loads(subprocess.run(
        [sys.executable, str(TPL / "tools" / "artifacts.py"), "--project", str(dest), "--json"],
        capture_output=True, text=True).stdout)
    ok = True
    for query, var, needle in [
            ("unplanned-scope", "requirement", "is in scope but no task satisfies it"),
            ("unproven-mitigations", "risk", "has no passing acceptance criterion"),
            ("open-high-risks", "risk", "high severity and open")]:
        out = subprocess.run([sys.executable, str(KG), "query", "--project", str(dest),
                              "--name", query, "--json"], capture_output=True, text=True)
        if out.returncode != 0:
            check(f"{name}: {query} runs", False, out.stderr.strip()[:80])
            ok = False
            continue
        got, expected = ids_from(json.loads(out.stdout), var), warned_ids(lint, needle)
        if got != expected:
            check(f"{name}: SPARQL {query} agrees with the linter", False,
                  f"sparql {got} vs linter {expected}")
            ok = False
    agreements += 1 if ok else 0
    shutil.rmtree(dest.parent, ignore_errors=True)
check("stored queries agree with the linter on every fixture",
      agreements == len(fixture_names), f"{agreements}/{len(fixture_names)} fixtures")

# kg.py registers two of its parsers in a loop, so ask argparse rather than the source
usage = subprocess.run([sys.executable, str(KG), "--help"], capture_output=True, text=True).stdout
verbs = set(re.search(r"\{([\w,-]+)\}", usage).group(1).split(","))
docs = "\n".join((TPL / d).read_text(encoding="utf-8")
                 for d in ["README.md", "ORCHESTRATOR.md", "ARTIFACT-SCHEMA.md"])
used = {m.group(1) for m in re.finditer(r"kg\.py\s+([a-z][\w-]*)", docs)}  # subcommands, not flags
unknown = sorted(v for v in used if v not in verbs)
check("all documented kg.py subcommands exist", not unknown and len(used) >= 3,
      ", ".join(unknown) if unknown else f"{len(used)} documented")

# Documented snippets must be real: a README that teaches invalid syntax is worse
# than one that shows none. The SPARQL half needs no dependency - our own parser.
import kg as _kg  # noqa: E402  (sibling tool)
DOCS = ["README.md", "ARTIFACT-SCHEMA.md", "ORCHESTRATOR.md"]
sparql_blocks = turtle_blocks = 0
bad = []
for doc in DOCS:
    text = (TPL / doc).read_text(encoding="utf-8")
    for block in re.findall(r"```sparql\n(.*?)```", text, re.S):
        sparql_blocks += 1
        try:
            _kg.parse_query(block)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{doc}: {exc}")
    turtle_blocks += len(re.findall(r"```turtle\n(.*?)```", text, re.S))
check("documented SPARQL snippets parse", not bad and sparql_blocks >= 1,
      "; ".join(bad)[:100] if bad else f"{sparql_blocks} block(s)")

# Optional: if real RDF tooling is around, it must be able to read what we emit
# and reach the same answers. Skipped rather than depended on - no pip installs.
rdf_proj = pathlib.Path(tempfile.mkdtemp()) / "proj"
fx = TPL / "tests" / "fixtures" / "qa-failed-mitigation"
harness.materialize(fx, rdf_proj, False)
r = subprocess.run([sys.executable, str(KG), "build", "--project", str(rdf_proj)],
                   capture_output=True, text=True)
check("kg.py build writes graph.ttl and graph.nt",
      (rdf_proj / ".pmos" / "graph.ttl").is_file() and (rdf_proj / ".pmos" / "graph.nt").is_file(),
      r.stdout.strip()[:80])
try:
    from rdflib import Graph as _RdfGraph
except ImportError:
    skip("RDF conformance (rdflib parses our Turtle and N-Triples)",
         "rdflib not installed; `pip install rdflib` to enable this check")
    skip("SPARQL agreement (rdflib's engine vs ours)", "rdflib not installed")
else:
    sizes, parsed = {}, {}
    for fmt, name in (("turtle", "graph.ttl"), ("nt", "graph.nt")):
        g = _RdfGraph()
        g.parse(str(rdf_proj / ".pmos" / name), format=fmt)
        sizes[name] = len(g)
        parsed[name] = {(str(a), str(b), str(c)) for a, b, c in g}
    ours = json.loads(subprocess.run(
        [sys.executable, str(KG), "stats", "--project", str(rdf_proj), "--json"],
        capture_output=True, text=True).stdout)["triples"]
    check("rdflib parses our Turtle and N-Triples to the same graph",
          sizes["graph.ttl"] == sizes["graph.nt"] == ours
          and parsed["graph.ttl"] == parsed["graph.nt"],
          f"ttl {sizes['graph.ttl']}, nt {sizes['graph.nt']}, ours {ours}")
    q = ("PREFIX pmos: <https://pmos.dev/schema#>\n"
         "SELECT ?risk ?task WHERE { ?risk a pmos:Risk ; pmos:mitigatedBy ?task }")
    g = _RdfGraph()
    g.parse(str(rdf_proj / ".pmos" / "graph.ttl"), format="turtle")
    theirs = sorted(tuple(str(x) for x in row) for row in g.query(q))
    mine_json = json.loads(subprocess.run(
        [sys.executable, str(KG), "query", "--project", str(rdf_proj), "-q", q, "--json"],
        capture_output=True, text=True).stdout)
    mine = sorted((b["risk"]["value"], b["task"]["value"])
                  for b in mine_json["results"]["bindings"])
    check("our SPARQL engine agrees with rdflib's on the same query", theirs == mine,
          f"rdflib {theirs} vs ours {mine}")
    header = ('@prefix pmos: <https://pmos.dev/schema#> .\n'
              '@prefix : <https://pmos.dev/project#> .\n')
    bad = []
    for doc in DOCS:
        for block in re.findall(r"```turtle\n(.*?)```",
                                (TPL / doc).read_text(encoding="utf-8"), re.S):
            try:
                _RdfGraph().parse(data=block if "@prefix" in block else header + block,
                                  format="turtle")
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{doc}: {str(exc)[:60]}")
    check("documented Turtle snippets parse", not bad and turtle_blocks >= 1,
          "; ".join(bad)[:100] if bad else f"{turtle_blocks} block(s)")
shutil.rmtree(rdf_proj.parent, ignore_errors=True)

print()
if _failures:
    print(f"VALIDATION FAILED ({_failures} check(s), {_skips} skipped)")
    sys.exit(1)
print(f"ALL VALIDATION PASSED ({_skips} environment-dependent check(s) skipped)")
