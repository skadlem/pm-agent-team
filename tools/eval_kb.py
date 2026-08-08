#!/usr/bin/env python3
"""PMOS retrieval-quality benchmark.

Boots a temporary KB from the shipped kb-sources, runs a golden query set
(2 queries per role + shared), and scores how well hybrid search retrieves
the intended chunk: hits@k and Mean Reciprocal Rank.

    python tools/eval_kb.py            # human report
    python tools/eval_kb.py --json     # machine-readable

Pass criteria (exit 0): hits@5 >= 0.90 and MRR >= 0.65. Deterministic and
offline; safe for CI. If you edit kb-sources, keep the golden set aligned:
each query targets one section title from kb-sources.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent

# (namespace, query, expected substring of the chunk title)
GOLDEN = [
    ("pm", "how to handle scope creep", "Chartering and scope"),
    ("pm", "plan phases exit criteria dependencies", "Planning"),
    ("pm", "risk register likelihood impact", "Coordination"),
    ("architect", "record why a decision was made", "Architecture decision records"),
    ("architect", "module boundaries data ownership", "Core principles"),
    ("architect", "API error contract validation idempotency", "Data and APIs"),
    ("backend", "cache invalidation slow endpoint", "Data and APIs"),
    ("backend", "unit integration contract tests deterministic", "Testing and reliability"),
    ("frontend", "component state lifting derived state", "Frontend fundamentals"),
    ("frontend", "accessibility contrast keyboard focus", "Performance and UX basics"),
    ("frontend", "form validation errors next to field", "Forms and state"),
    ("designer", "WCAG contrast ratio colors", "Visual system"),
    ("designer", "empty loading error states wireframes", "Design process"),
    ("designer", "spacing scale token values handoff", "Handoff"),
    ("business", "north star metric guardrail", "Metrics and viability"),
    ("business", "reversible irreversible decisions sign-off", "Decisions"),
    ("business", "value proposition riskiest assumption", "Business fundamentals"),
    ("marketing", "positioning formula audience category", "Positioning and messaging"),
    ("marketing", "launch checklist landing analytics", "Channels and launch"),
    ("qa", "definition of done evidence executed checks", "Verification gate"),
    ("qa", "regression test bug fixed", "QA fundamentals"),
    ("qa", "injection probes auth bypass permission", "Non-functional checks"),
    ("devops", "deploy rollback one command", "DevOps fundamentals"),
    ("devops", "backup restore test scheduled", "Runtime care"),
    ("devops", "least privilege service accounts secrets", "Security operations"),
    ("shared", "never dump full repository partial context", "Agent operating rules"),
    ("shared", "retrieval order KB graphify targeted read", "Agent operating rules"),
]

K = 5
MIN_HITS = 0.90
MIN_MRR = 0.65


def build_db(db_path):
    kb = str(TPL / "tools" / "kb.py")
    subprocess.run([sys.executable, kb, "init", "--db", str(db_path)],
                   check=True, capture_output=True, text=True)
    for ns in ["shared", "pm", "architect", "backend", "frontend", "designer",
               "business", "marketing", "qa", "devops"]:
        subprocess.run([sys.executable, kb, "add-dir", "--db", str(db_path),
                        "--ns", ns, "--path", str(TPL / "kb-sources" / ns),
                        "--priority", "10" if ns == "shared" else "8"],
                       check=True, capture_output=True, text=True)


def search(db_path, ns, query):
    kb = str(TPL / "tools" / "kb.py")
    r = subprocess.run([sys.executable, kb, "search", "--db", str(db_path),
                        query, "--role", ns, "-k", str(K), "--json"],
                       capture_output=True, text=True, check=True)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


def main():
    tmp = Path(tempfile.mkdtemp()) / "eval.sqlite3"
    build_db(tmp)

    results = []
    hits = 0
    rr_sum = 0.0
    for ns, query, expected in GOLDEN:
        rows = search(tmp, ns, query)
        rank = 0
        for i, row in enumerate(rows, 1):
            if expected.lower() in row["title"].lower():
                rank = i
                break
        if rank:
            hits += 1
            rr_sum += 1.0 / rank
        results.append({"ns": ns, "query": query, "expected": expected, "rank": rank})

    hits_at_k = hits / len(GOLDEN)
    mrr = rr_sum / len(GOLDEN)
    passed = hits_at_k >= MIN_HITS and mrr >= MIN_MRR

    if "--json" in sys.argv:
        print(json.dumps({"hits@%d" % K: round(hits_at_k, 3), "mrr": round(mrr, 3),
                          "pass": passed, "results": results}, indent=1))
    else:
        print("%-10s %-48s %-32s %s" % ("ns", "query", "expected", "rank"))
        for r in results:
            print("%-10s %-48s %-32s %s" % (r["ns"], r["query"][:48], r["expected"][:32],
                                             r["rank"] if r["rank"] else "MISS"))
        print()
        print("hits@%d = %.1f%%  (%d/%d)   MRR = %.3f" % (K, hits_at_k * 100, hits, len(GOLDEN), mrr))
        print("thresholds: hits@%d >= %.0f%%, MRR >= %.2f  ->  %s"
              % (K, MIN_HITS * 100, MIN_MRR, "PASS" if passed else "FAIL"))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
