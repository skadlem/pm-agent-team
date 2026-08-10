#!/usr/bin/env python3
"""PMOS knowledge base engine: hybrid search (BM25 + vectors) with token caps.

One SQLite store per project (.pmos/kb.sqlite3), namespaced per role.
BM25 via SQLite FTS5; semantic side is offline (deterministic hashed vectors)
by default, or a real OpenAI-compatible embeddings endpoint when configured.

Env vars for real embeddings (optional):
  PMOS_EMBEDDINGS_URL   e.g. https://api.openai.com/v1/embeddings
  PMOS_EMBEDDINGS_KEY   bearer key
  PMOS_EMBEDDINGS_MODEL e.g. text-embedding-3-small

Commands:
  init --db PATH
  add --db PATH --ns ROLE --title T [--kind K] [--source S] [--priority N] (--content TEXT | - )
  add-dir --db PATH --ns ROLE --path DIR [--glob *.md] [--priority N]
  search --db PATH "query" [--role ROLE] [-k N] [--json] [--min-score F]
  budget --db PATH --config CONFIG_JSON [--json]
  reindex-vectors --db PATH
  stats --db PATH [--json]
  clear --db PATH --ns ROLE
  selftest
"""
import argparse, hashlib, json, math, os, sqlite3, struct, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

DIM = 64
RRF_K = 60
FTS_LANG = "english"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY,
  ns TEXT NOT NULL,
  title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'doc',
  source TEXT NOT NULL DEFAULT '',
  priority INTEGER NOT NULL DEFAULT 5,
  n_tokens INTEGER NOT NULL,
  body TEXT NOT NULL,
  added TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(title, body, content='chunks', content_rowid='id', tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS vectors(id INTEGER PRIMARY KEY, vec BLOB NOT NULL, dim INTEGER NOT NULL, mode TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chunks_ns ON chunks(ns);
"""

def tokens_of(text):
    return max(1, len(text) // 4)

def tokenize(text):
    out = []
    for tok in text.lower().replace("_", " ").split():
        tok = "".join(c for c in tok if c.isalnum())
        if len(tok) >= 2:
            out.append(tok)
    return out

def offline_vector(text):
    v = [0.0] * DIM
    for tok in tokenize(text):
        h = hashlib.shake_256(tok.encode("utf-8")).digest(2 * DIM)
        for i in range(DIM):
            v[i] += struct.unpack_from("<h", h, 2 * i)[0] / 32768.0
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        return v
    return [x / n for x in v]

def pack_vec(v):
    return struct.pack("<%df" % len(v), *v)

def unpack_vec(b):
    n = len(b) // 4
    return struct.unpack("<%df" % n, b)

def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))

def _http_post_json(url, headers, payload, max_attempts=4):
    for attempt in range(max_attempts):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode('utf-8'),
            headers=headers, method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < max_attempts - 1:
                wait = e.headers.get('Retry-After')
                delay = float(wait) if wait else min(15 * 2 ** attempt, 70)
                print('embeddings API %d; retrying in %.0fs (%d/%d)'
                      % (e.code, delay, attempt + 1, max_attempts), file=sys.stderr)
                time.sleep(delay)
            else:
                raise

def _gemini_embeddings(texts, key, model):
    base = 'https://generativelanguage.googleapis.com/v1beta/models/' + model
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': key}
    out = []
    for i in range(0, len(texts), 99):  # batchEmbedContents allows up to 100 requests
        batch = texts[i:i + 99]
        payload = {'requests': [{'model': 'models/' + model,
                                 'content': {'parts': [{'text': t}]}} for t in batch]}
        data = _http_post_json(base + ':batchEmbedContents', headers, payload)
        out.extend(e['values'] for e in data['embeddings'])
    return out

def api_embeddings(texts):
    url = os.environ.get('PMOS_EMBEDDINGS_URL')
    key = os.environ.get('PMOS_EMBEDDINGS_KEY', '')
    model = os.environ.get('PMOS_EMBEDDINGS_MODEL', 'text-embedding-3-small')
    if not url:
        return None
    if 'generativelanguage.googleapis.com' in url:
        return _gemini_embeddings(texts, key, model)  # native API-key auth
    out = []
    for i in range(0, len(texts), 64):
        batch = texts[i:i + 64]
        payload = {'model': model, 'input': batch}
        data = _http_post_json(
            url,
            {'Content-Type': 'application/json', 'Authorization': '***' + key},
            payload,
        )
        for item in sorted(data['data'], key=lambda d: d['index']):
            out.append(item['embedding'])
    return out

def connect(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        con.close()
        raise RuntimeError(
            "db %s is schema v%d but this kb.py only knows v%d; upgrade kb.py "
            "before opening it" % (db_path, version, SCHEMA_VERSION))
    if version < SCHEMA_VERSION:
        # v0 -> v1: SCHEMA is idempotent (CREATE IF NOT EXISTS), so the tables
        # were just created above; nothing else to migrate.
        con.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
    return con

def compute_vector(con, text):
    mode = "api"
    vecs = api_embeddings([text])
    if vecs is None:
        mode = "offline"
        vec = offline_vector(text)
    else:
        vec = vecs[0]
    return vec, mode

def insert_doc(con, ns, title, kind, source, priority, body):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n_tokens = tokens_of(body)
    cur = con.execute(
        "INSERT INTO chunks(ns,title,kind,source,priority,n_tokens,body,added) VALUES(?,?,?,?,?,?,?,?)",
        (ns, title, kind, source, priority, n_tokens, body, now),
    )
    cid = cur.lastrowid
    con.execute("INSERT INTO kb_fts(rowid,title,body) VALUES(?,?,?)", (cid, title, body))
    vec, mode = compute_vector(con, title + "\n" + body[:800])
    con.execute("INSERT INTO vectors(id,vec,dim,mode) VALUES(?,?,?,?)", (cid, pack_vec(vec), len(vec), mode))
    return cid, n_tokens

def enforce_cap(con, ns, cap_tokens):
    """Drop lowest-priority (then oldest) chunks until namespace fits its budget."""
    dropped = []
    while True:
        total = con.execute("SELECT COALESCE(SUM(n_tokens),0) FROM chunks WHERE ns=?", (ns,)).fetchone()[0]
        if total <= cap_tokens:
            break
        row = con.execute(
            "SELECT id FROM chunks WHERE ns=? ORDER BY priority ASC, added ASC, id ASC LIMIT 1", (ns,)
        ).fetchone()
        if not row:
            break
        cid = row[0]
        t = con.execute("SELECT title FROM chunks WHERE id=?", (cid,)).fetchone()[0]
        con.execute("DELETE FROM kb_fts WHERE rowid=?", (cid,))
        con.execute("DELETE FROM vectors WHERE id=?", (cid,))
        con.execute("DELETE FROM chunks WHERE id=?", (cid,))
        dropped.append(t)
    return dropped

def _rank_all(blobs, qvec):
    """Cosine similarity of every packed vector against qvec, in input order.

    numpy fast path when available (one matmul instead of a Python loop over
    every chunk); pure-Python fallback keeps the stdlib-only promise.
    """
    if not blobs:
        return []
    try:
        import numpy as np
        arr = np.frombuffer(b"".join(blobs), dtype="<f4").reshape(len(blobs), len(qvec))
        return (arr @ np.asarray(qvec, dtype="<f4")).tolist()
    except Exception:
        pass  # numpy missing or malformed blobs; fall back to pure Python
    return [cosine(qvec, unpack_vec(b)) for b in blobs]


def fts_query(text):
    toks = tokenize(text)
    if not toks:
        return None
    return " OR ".join('"%s"' % t for t in toks[:24])

def cmd_search(con, args, config):
    q = " ".join(args.query)
    fq = fts_query(q)
    k = args.k or config.get("context_rules", {}).get("search_k_default", 5)
    max_chars = config.get("context_rules", {}).get("excerpt_max_chars", 1200)
    scope = "AND c.ns=?" if args.role else ""
    params = [args.role] if args.role else []
    mode = getattr(args, "mode", "hybrid")

    fts_rank = {}
    if mode != "vector" and fq:
        try:
            if args.role:
                rows = con.execute(
                    "SELECT kb_fts.rowid, bm25(kb_fts) AS s FROM kb_fts "
                    "JOIN chunks c ON c.rowid = kb_fts.rowid "
                    "WHERE kb_fts MATCH ? AND c.ns = ? ORDER BY s LIMIT ?",
                    (fq, args.role, k * 6),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT rowid, bm25(kb_fts) AS s FROM kb_fts WHERE kb_fts MATCH ? ORDER BY s LIMIT ?",
                    (fq, k * 6),
                ).fetchall()
            for i, (cid, s) in enumerate(rows):
                fts_rank[cid] = i
        except sqlite3.OperationalError:
            pass

    vec_rank = {}
    if mode != "bm25":
        vec, vmode = compute_vector(con, q)
        vrows = con.execute(
            "SELECT v.id, v.vec FROM vectors v JOIN chunks c ON c.id=v.id WHERE 1=1 " + scope, params
        ).fetchall()
        ids, blobs = [], []
        for cid, blob in vrows:
            if len(blob) // 4 != len(vec):
                continue  # backend changed without reindex-vectors; skip stale dims
            ids.append(cid)
            blobs.append(blob)
        sims = sorted(zip(ids, _rank_all(blobs, vec)), key=lambda x: -x[1])
        vec_rank = {cid: i for i, (cid, _) in enumerate(sims)}

    w_bm25 = w_vec = 0.5
    if mode == "hybrid":
        row = con.execute(
            "SELECT v.mode FROM vectors v JOIN chunks c ON c.id=v.id WHERE 1=1 " + scope + " LIMIT 1",
            params).fetchone()
        if row and row[0] == "api":
            w_bm25, w_vec = 0.35, 0.65  # real semantic embeddings get the larger share
    ids = set(fts_rank) | set(vec_rank)
    scored = []
    for cid in ids:
        score = 0.0
        if cid in fts_rank:
            score += w_bm25 / (RRF_K + fts_rank[cid] + 1)
        if cid in vec_rank:
            score += w_vec / (RRF_K + vec_rank[cid] + 1)
        scored.append((cid, score))
    scored.sort(key=lambda x: -x[1])
    if not scored:
        print("no results")
        return

    results = []
    for cid, score in scored:
        row = con.execute(
            "SELECT ns,title,kind,source,body FROM chunks WHERE id=?", (cid,)
        ).fetchone()
        if not row:
            continue
        ns, title, kind, source, body = row
        if args.role and ns != args.role:
            continue
        if score < args.min_score:
            continue
        results.append({"score": round(score, 4), "ns": ns, "title": title, "kind": kind,
                        "source": source, "id": cid, "excerpt": body[:max_chars]})
        if len(results) >= k:
            break

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    elif not results:
        print("no results above min-score")
    else:
        for r in results:
            print("=" * 72)
            print("[%.4f] [%s] %s  (kind=%s id=%s)" % (r["score"], r["ns"], r["title"], r["kind"], r["id"]))
            if r["source"]:
                print("source: %s" % r["source"])
            print("-" * 72)
            print(r["excerpt"])

def cmd_budget(con, args):
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)
    kb = config.get("kb", {})
    total_cap = kb.get("total_token_cap", 150000)
    shared = kb.get("shared_token_budget", 15000)
    weights = kb.get("role_weights", {})
    pool = total_cap - shared
    report = {}
    namespaces = list(weights) + (["shared"] if shared else [])
    for ns in namespaces:
        used = con.execute("SELECT COALESCE(SUM(n_tokens),0), COUNT(*) FROM chunks WHERE ns=?", (ns,)).fetchone()
        budget = shared if ns == "shared" else int(weights[ns] * pool)
        report[ns] = {"used_tokens": used[0], "chunks": used[1], "budget_tokens": budget,
                      "headroom": budget - used[0]}
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print("%-12s %10s %8s %10s %10s" % ("namespace", "used", "chunks", "budget", "headroom"))
        for ns, r in report.items():
            flag = "  <-- OVER" if r["headroom"] < 0 else ""
            print("%-12s %10d %8d %10d %10d%s" % (ns, r["used_tokens"], r["chunks"], r["budget_tokens"], r["headroom"], flag))

def split_markdown_sections(text):
    """Split markdown on '## ' headings into (title, body) chunks."""
    import re
    parts = re.split(r"(?m)^##\s+(.+)$", text)
    sections = []
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].strip()
        body = parts[i + 1].strip()
        if body:
            sections.append((title, body))
    return sections

def cmd_add(con, args, config):
    body = sys.stdin.read() if args.content == "-" else args.content
    if args.file:
        body = Path(args.file).read_text(encoding="utf-8", errors="replace")
    body = body.strip()
    if not body:
        print("empty content, nothing added", file=sys.stderr)
        return 1
    weights = config.get("kb", {}).get("role_weights", {})
    if args.ns not in weights and args.ns != "shared":
        print("warning: namespace '%s' is not a known role" % args.ns, file=sys.stderr)
    cid, n = insert_doc(con, args.ns, args.title, args.kind, args.source or "manual", args.priority, body)
    con.commit()
    total_cap = config.get("kb", {}).get("total_token_cap", 150000)
    shared = config.get("kb", {}).get("shared_token_budget", 15000)
    w = config.get("kb", {}).get("role_weights", {}).get(args.ns, 0)
    cap = shared if args.ns == "shared" else int(w * (total_cap - shared))
    dropped = enforce_cap(con, args.ns, cap)
    con.commit()
    print("added id=%d ns=%s tokens~%d title=%s" % (cid, args.ns, n, args.title))
    if dropped:
        print("cap enforced: dropped %d lower-priority chunk(s): %s" % (len(dropped), "; ".join(dropped[:5])))

def cmd_add_dir(con, args, config):
    root = Path(args.path)
    files = sorted(root.glob(args.glob)) if args.glob else sorted(p for p in root.rglob("*") if p.is_file())
    n_docs = 0
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        sections = split_markdown_sections(text) or [(p.stem, text)]
        for title, sec in sections:
            args2 = argparse.Namespace(ns=args.ns, title=title, kind="doc", source=str(p),
                                       priority=args.priority, content=sec, file=None)
            cmd_add(con, args2, config)
            n_docs += 1
    print("indexed %d chunk(s) from %s" % (n_docs, root))

def cmd_reindex(con, args):
    rows = con.execute("SELECT id, title, body FROM chunks").fetchall()
    mode_used = None
    if os.environ.get("PMOS_EMBEDDINGS_URL"):
        texts = [t + "\n" + b[:800] for _, t, b in rows]
        vecs = api_embeddings(texts)
        mode_used = "api"
        con.execute("DELETE FROM vectors")
        for (cid, _, _), v in zip(rows, vecs):
            con.execute("INSERT INTO vectors(id,vec,dim,mode) VALUES(?,?,?,?)", (cid, pack_vec(v), len(v), "api"))
    else:
        con.execute("DELETE FROM vectors")
        for cid, t, b in rows:
            v = offline_vector(t + "\n" + b[:800])
            con.execute("INSERT INTO vectors(id,vec,dim,mode) VALUES(?,?,?,?)", (cid, pack_vec(v), DIM, "offline"))
        mode_used = "offline"
    con.commit()
    print("reindexed %d chunk(s), mode=%s" % (len(rows), mode_used))

def cmd_stats(con, args):
    rows = con.execute(
        "SELECT ns, COUNT(*), SUM(n_tokens) FROM chunks GROUP BY ns ORDER BY ns").fetchall()
    data = [{"ns": ns, "chunks": c, "tokens": t or 0} for ns, c, t in rows]
    if args.json:
        print(json.dumps(data, indent=1))
    else:
        total = 0
        for d in data:
            print("%-12s %6d chunks  ~%8d tokens" % (d["ns"], d["chunks"], d["tokens"]))
            total += d["tokens"]
        print("%-12s %6d chunks  ~%8d tokens total" % ("ALL", sum(d["chunks"] for d in data), total))

def cmd_clear(con, args):
    count = con.execute("SELECT COUNT(*) FROM chunks WHERE ns=?", (args.ns,)).fetchone()[0]
    rows = con.execute("SELECT id FROM chunks WHERE ns=?", (args.ns,)).fetchall()
    for (cid,) in rows:
        con.execute("DELETE FROM kb_fts WHERE rowid=?", (cid,))
        con.execute("DELETE FROM vectors WHERE id=?", (cid,))
    con.execute("DELETE FROM chunks WHERE ns=?", (args.ns,))
    con.commit()
    print("cleared %d chunk(s) from namespace '%s'" % (count, args.ns))

def cmd_selftest(args):
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "selftest.sqlite3"
    con = connect(str(tmp))
    assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION, "schema version"
    config = {"kb": {"total_token_cap": 1000000, "shared_token_budget": 1000,
                     "role_weights": {"pm": 0.5, "backend": 0.5}},
              "context_rules": {"search_k_default": 5, "excerpt_max_chars": 400}}
    insert_doc(con, "pm", "Scope management", "doc", "selftest", 5,
               "A project charter defines scope, milestones and success metrics. Avoid scope creep.")
    insert_doc(con, "backend", "SQLite WAL mode", "doc", "selftest", 5,
               "Write-ahead logging lets SQLite handle concurrent readers with a single writer.")
    insert_doc(con, "backend", "HTTP caching", "doc", "selftest", 5,
               "ETag and Cache-Control headers reduce load; validate conditional requests.")
    con.commit()

    args2 = argparse.Namespace(query=["database", "concurrency"], role="backend", k=2,
                               json=False, min_score=0.0)
    print("-- search 'database concurrency' in backend ns:")
    cmd_search(con, args2, config)

    dropped = enforce_cap(con, "backend", 40)
    con.commit()
    left = con.execute("SELECT COUNT(*) FROM chunks WHERE ns='backend'").fetchone()[0]
    assert left < 3, "cap enforcement failed"
    print("-- cap enforcement dropped %d chunk(s), backend chunks left: %d" % (len(dropped), left))

    before = con.execute("SELECT COUNT(*) FROM chunks WHERE ns='pm'").fetchone()[0]
    args3 = argparse.Namespace(ns="pm")
    cmd_clear(con, args3)
    after = con.execute("SELECT COUNT(*) FROM chunks WHERE ns='pm'").fetchone()[0]
    assert after == 0, "clear failed: %d chunks remain" % after
    print("-- clear: removed %d pm chunk(s), %d remaining" % (before, after))
    print("SELFTEST PASS")

def main():
    ap = argparse.ArgumentParser(description="PMOS hybrid KB engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_db(p):
        p.add_argument("--db", required=True)
    def add_cfg(p):
        p.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json"))

    p = sub.add_parser("init"); add_db(p)
    p = sub.add_parser("add"); add_db(p); add_cfg(p)
    p.add_argument("--ns", required=True); p.add_argument("--title", required=True)
    p.add_argument("--kind", default="doc"); p.add_argument("--source")
    p.add_argument("--priority", type=int, default=5)
    p.add_argument("--content", default=None); p.add_argument("--file", default=None)
    p = sub.add_parser("add-dir"); add_db(p); add_cfg(p)
    p.add_argument("--ns", required=True); p.add_argument("--path", required=True)
    p.add_argument("--glob", default=None); p.add_argument("--priority", type=int, default=5)
    p = sub.add_parser("search"); add_db(p); add_cfg(p)
    p.add_argument("query", nargs="+"); p.add_argument("--role", default=None)
    p.add_argument("-k", type=int, default=None); p.add_argument("--json", action="store_true")
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--mode", choices=["hybrid", "bm25", "vector"], default="hybrid",
                   help="hybrid = BM25+vector fusion (default); bm25/vector alone for ablations")
    p = sub.add_parser("budget"); add_db(p)
    p.add_argument("--config", required=True); p.add_argument("--json", action="store_true")
    p = sub.add_parser("reindex-vectors"); add_db(p)
    p = sub.add_parser("stats"); add_db(p); p.add_argument("--json", action="store_true")
    p = sub.add_parser("clear"); add_db(p)
    p.add_argument("--ns", required=True)
    sub.add_parser("selftest")

    args = ap.parse_args()
    if args.cmd == "selftest":
        cmd_selftest(args)
        return
    if args.cmd == "init":
        connect(args.db).close()
        print("initialized %s" % args.db)
        return
    con = connect(args.db)
    config_path = getattr(args, "config", None)
    config = {}
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    if args.cmd == "add":
        cmd_add(con, args, config)
    elif args.cmd == "add-dir":
        cmd_add_dir(con, args, config)
    elif args.cmd == "search":
        cmd_search(con, args, config)
    elif args.cmd == "budget":
        cmd_budget(con, args)
    elif args.cmd == "reindex-vectors":
        cmd_reindex(con, args)
    elif args.cmd == "stats":
        cmd_stats(con, args)
    elif args.cmd == "clear":
        cmd_clear(con, args)

if __name__ == "__main__":
    main()
