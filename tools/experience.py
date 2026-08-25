#!/usr/bin/env python3
"""PMOS experience namespace (L-11): read-only cross-project memory.

An optional, human-curated folder of markdown notes that survive across
projects: pitfalls, conventions, and facts the team learned on previous
projects. The coordinator searches it BEFORE the project KB when it exists:

    ~/.pmos-experience/*.md        (global, all projects)

    python tools/experience.py search "sqlite locking" --json
    python tools/experience.py search "sqlite locking" -k 3

Search is naive word-overlap scoring over markdown lines (stdlib only — this
is a curated handful of files, not a corpus). Read-only by design: nothing in
this tool ever writes to the experience dir, so it can be a symlink into a
team repo without risk.

Exit codes: 0 ok, 2 usage error. No hits is still 0 (nothing to report).
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / ".pmos-experience"

STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
        "is", "are", "was", "were", "it", "this", "that", "from", "by", "at",
        "as", "be", "do", "does", "did", "we", "you", "they", "how", "what",
        "when", "why", "not", "no", "yes", "if", "then", "else", "use", "using",
        "used", "via", "per", "our", "your", "their", "has", "have", "had"}


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9][a-z0-9._-]*", text.lower()) if t not in STOP]


def search(experience_dir, query, k=5):
    q = tokens(query)
    hits = []
    for p in sorted(Path(experience_dir).glob("*.md")):
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            lt = tokens(line)
            overlap = sum(1 for t in q if any(t in ltok or ltok in t for ltok in lt))
            if overlap:
                hits.append({"file": str(p.name), "line": n,
                             "score": overlap, "text": line[:160]})
    hits.sort(key=lambda h: (-h["score"], h["file"], h["line"]))
    return hits[:k]


def main():
    ap = argparse.ArgumentParser(description="PMOS experience search (read-only, L-11)")
    ap.add_argument("search", nargs="?", help="query")
    ap.add_argument("query", nargs="*", help="query words (when 'search' is omitted)")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="experience dir (default ~/.pmos-experience)")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    words = args.query or ([args.search] if args.search else [])
    if not words:
        print("usage: experience.py search \"query\" [--dir PATH]", file=sys.stderr)
        return 2
    d = Path(args.dir)
    if not d.is_dir():
        if args.json:
            print(json.dumps({"dir": str(d), "hits": []}))
        else:
            print("no experience dir at %s (nothing searched)" % d)
        return 0
    hits = search(d, " ".join(words), args.k)
    if args.json:
        print(json.dumps({"dir": str(d), "query": " ".join(words), "hits": hits}, indent=1))
    else:
        print("experience search (%s): %d hit(s)" % (d, len(hits)))
        for h in hits:
            print("  %s:%d  %s" % (h["file"], h["line"], h["text"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
