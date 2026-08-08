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
ms = {k: v for k, v in roster["model_suggestions"].items() if isinstance(v, dict) and "suggested" in v}
check("model suggestions == roster roles", set(ms) == set(roster["roles"]))
malformed = [k for k, v in ms.items() if not (v.get("suggested") and v.get("effort") and v.get("alternatives"))]
check("all model entries well-formed", not malformed)

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

print("== 10. Idempotent re-add / reindex / installer ==")
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
