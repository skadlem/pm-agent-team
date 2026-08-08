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
MODES = ["hybrid", "bm25", "vector"]

# Hard set: paraphrased queries with minimal keyword overlap. These are the
# queries where a real semantic embedding model should beat lexical/hash
# vectors; informational (not part of the pass threshold).
HARD = [
    ("pm", "client keeps adding new requests after we agreed what to build", "Chartering and scope"),
    ("pm", "how do we decide who owns a topic and when to ask the user", "Coordination"),
    ("architect", "where do we write down why we picked one database over another", "Architecture decision records"),
    ("architect", "which service is allowed to touch the user table", "Core principles"),
    ("backend", "the API is getting slower under load", "Data and APIs"),
    ("backend", "tests pass on my machine but fail in CI", "Testing and reliability"),
    ("frontend", "parent and child both need the same toggle value", "Frontend fundamentals"),
    ("frontend", "screen reader users cannot reach the submit button", "Performance and UX basics"),
    ("designer", "palette looks washed out and text is hard to read", "Visual system"),
    ("designer", "developer built the screen but spacing is off everywhere", "Handoff"),
    ("business", "should we keep spending on the experiment", "Decisions"),
    ("business", "what single number tells us the product is working", "Metrics and viability"),
    ("marketing", "one sentence that says who this is for", "Positioning and messaging"),
    ("qa", "how do we know we are allowed to ship", "Verification gate"),
    ("qa", "found a bug, what do I write in the ticket", "QA fundamentals"),
    ("devops", "the deploy broke production, how do we undo it", "DevOps fundamentals"),
    ("devops", "where are the passwords for prod stored", "Runtime care"),
    ("shared", "do not paste the whole codebase into your context", "Agent operating rules"),
]
SETS = [("standard", GOLDEN), ("paraphrase", HARD)]


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


def search(db_path, ns, query, mode):
    kb = str(TPL / "tools" / "kb.py")
    r = subprocess.run([sys.executable, kb, "search", "--db", str(db_path),
                        query, "--role", ns, "-k", str(K), "--json", "--mode", mode],
                       capture_output=True, text=True, check=True)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


def run_mode(db_path, mode, queries):
    results = []
    hits = 0
    rr_sum = 0.0
    for ns, query, expected in queries:
        rows = search(db_path, ns, query, mode)
        rank = 0
        for i, row in enumerate(rows, 1):
            if expected.lower() in row["title"].lower():
                rank = i
                break
        if rank:
            hits += 1
            rr_sum += 1.0 / rank
        results.append({"ns": ns, "query": query, "expected": expected, "rank": rank})
    return {"mode": mode, "hits@%d" % K: round(hits / len(queries), 3),
            "mrr": round(rr_sum / len(queries), 3), "results": results}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sets", default="standard,paraphrase",
                    help="comma-separated subset of query sets to run")
    ap.add_argument("--db", default=None,
                    help="reuse an existing KB database (skips the build; it must already "
                         "be indexed with the embedding backend you want to measure)")
    args = ap.parse_args()

    if args.db:
        tmp = Path(args.db)
    else:
        tmp = Path(tempfile.mkdtemp()) / "eval.sqlite3"
        build_db(tmp)
    wanted = [n for n in args.sets.split(",") if n]
    sets = [(name, qs) for name, qs in SETS if name in wanted]
    report = {name: [dict(run_mode(tmp, m, qs), mode=m) for m in MODES]
              for name, qs in sets}
    hybrid_std = report.get("standard", [{}])[0]
    passed = (not report.get("standard")) or (hybrid_std.get("hits@%d" % K, 1) >= MIN_HITS
              and hybrid_std.get("mrr", 1) >= MIN_MRR)

    if "--json" in sys.argv or args.json:
        print(json.dumps({"pass": passed, "sets": report}, indent=1))
    else:
        for name, rows in report.items():
            print("== %s set (%d queries) ==" % (name, len(dict(SETS)[name])))
            print("%-8s %10s %8s   misses" % ("mode", "hits@%d" % K, "MRR"))
            for r in rows:
                misses = [x["query"] for x in r["results"] if not x["rank"]]
                print("%-8s %9.1f%% %8.3f   %s" % (r["mode"], r["hits@%d" % K] * 100,
                                                    r["mrr"], "; ".join(m[:40] for m in misses) if misses else "none"))
            print()
        print("pass threshold applies to hybrid on the standard set:")
        print("hits@%d >= %.0f%%, MRR >= %.2f  ->  %s"
              % (K, MIN_HITS * 100, MIN_MRR, "PASS" if passed else "FAIL"))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
