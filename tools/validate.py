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
import subprocess
import sys
import tempfile

TPL = pathlib.Path(__file__).resolve().parent.parent
_failures = 0


def check(label, cond, detail=""):
    global _failures
    print(f"  [{'OK' if cond else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        _failures += 1


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

print("== 2. Referenced skills are loadable ==")
roster = json.loads((TPL / "roster.json").read_text(encoding="utf-8"))
referenced = set(roster["common_skills"])
for r in roster["roles"].values():
    referenced.update(r["skills"])
found = set()
for base in (os.path.expanduser("~/.jcode"), os.path.expanduser("~/.agents"),
             os.path.expanduser("~/.claude/plugins/cache")):
    for root, dirs, files in os.walk(base):
        if "SKILL.md" in files:
            found.add(os.path.basename(root))
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
           "business", "marketing", "qa", "devops"]:
    r = subprocess.run(
        [sys.executable, str(TPL / "tools" / "kb.py"), "add-dir", "--db", str(DB),
         "--ns", ns, "--path", str(TPL / "kb-sources" / ns),
         "--priority", "10" if ns == "shared" else "8"],
        capture_output=True, text=True)
    check(f"add-dir {ns}", r.returncode == 0 and "indexed" in r.stdout, r.stderr.strip()[:80])
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "budget", "--db", str(DB),
                    "--config", str(TPL / "config.json")], capture_output=True, text=True)
check("budget", r.returncode == 0 and "shared" in r.stdout)

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
    for mid in avail:
        bmid = rmod.normalize_id(mid["id"])
        e = bench.get(bmid)
        if e:
            s = sum(w * (e["scores"].get(p, 0.0)) for p, w in rr["purpose"].items())
            scores[mid["id"]] = (s, rmod.blended_cost(e))
    best = max(s for s, _ in scores.values())
    tier = {m: d for m, d in scores.items() if d[0] >= 0.92 * best}
    cheapest = min(tier, key=lambda m: (tier[m][1] is None, tier[m][1] or 0.0, -tier[m][0]))
    check(f"{rr['role']} suggestion is best-tier cheapest", rr["suggested"] == cheapest,
          f"{rr['suggested']} vs {cheapest}")
fixture.unlink()
r = subprocess.run([sys.executable, str(TPL / "tools" / "recommend.py"), "refresh"],
                   capture_output=True, text=True)
check("recommend refresh prints queries", r.returncode == 0 and "websearch" in r.stdout)

print("== 11. Benchmark generator (Epoch data) ==")
gen_out = TPL / "_benchmarks_gen.json"
r = subprocess.run([sys.executable, str(TPL / "tools" / "build_benchmarks.py"),
                    "--data-dir", str(TPL.parent / "benchmark_data"), "--out", str(gen_out)],
                   capture_output=True, text=True)
check("build_benchmarks runs", r.returncode == 0, r.stderr.strip()[:80])
gb = json.loads(gen_out.read_text(encoding="utf-8"))
check("generated models > 100", len(gb["models"]) > 100, str(len(gb["models"])))
check("generated purposes complete", {"coding", "reasoning", "design", "ops", "verification", "business", "marketing", "writing"} <= set(gb["purposes"]))
for m in ["claude-fable-5", "qwen3.8-max", "deepseek-v4-pro"]:
    e = gb["models"].get(m)
    check(f"key model {m} present", bool(e and e["scores"]))
gen_out.unlink()

print("== 12. Idempotent re-add / reindex / installer ==")
# Re-adding the same dir must replace docs, not duplicate
r1 = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "stats", "--db", str(DB)],
                    capture_output=True, text=True)
before = r1.stdout.count("chunks")
subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "add-dir", "--db", str(DB),
                "--ns", "pm", "--path", str(TPL / "kb-sources" / "pm"), "--priority", "8"],
               capture_output=True, text=True)
r2 = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "stats", "--db", str(DB)],
                    capture_output=True, text=True)
after = r2.stdout.count("chunks")
check("re-add same dir does not duplicate", before == after, f"{before} vs {after}")
r = subprocess.run([sys.executable, str(TPL / "tools" / "kb.py"), "reindex-vectors", "--db", str(DB)],
                   capture_output=True, text=True)
check("reindex-vectors offline", r.returncode == 0 and "offline" in r.stdout)
if os.name == "nt":
    r = subprocess.run(["cmd", "/c", "install.cmd"], capture_output=True, text=True, cwd=TPL)
    check("install.cmd idempotent", r.returncode == 0)
    root = pathlib.Path(os.path.expanduser("~/.jcode/pmos-template-root"))
    check("template-root file", root.exists() and root.read_text().strip().rstrip("\\/") == str(TPL).rstrip("\\/"))

print()
if _failures:
    print(f"VALIDATION FAILED ({_failures} check(s))")
    sys.exit(1)
print("ALL VALIDATION PASSED")
