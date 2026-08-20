#!/usr/bin/env python3
"""PMOS knowledge graph: an RDF-style triple store with a SPARQL subset.

The markdown under .pmos/ stays the source of truth. This builds a materialized,
queryable projection of it: every entity and every reference becomes a triple,
joined to the graphify code graph through each task's `touches:` paths.

    python tools/kg.py build  --project .            # write .pmos/graph.ttl + graph.nt
    python tools/kg.py query  --project . -q "SELECT ?t WHERE { ?t a pmos:Task }"
    python tools/kg.py query  --project . --name unverified-tasks
    python tools/kg.py ask    --project . -q "ASK { :L-001 pmos:mitigatedBy ?t }"
    python tools/kg.py stats  --project .
    python tools/kg.py selftest

Vocabulary (see ARTIFACT-SCHEMA.md for the full ontology):
  classes     pmos:Requirement pmos:Task pmos:AcceptanceCriterion pmos:Decision
              pmos:Risk pmos:File
  predicates  pmos:satisfies pmos:dependsOn pmos:decidedBy pmos:verifies
              pmos:mitigatedBy pmos:supersedes pmos:touches pmos:title
              pmos:status pmos:severity pmos:role pmos:qaResult pmos:definedIn

Supported SPARQL: SELECT (DISTINCT) and ASK; basic graph patterns with `;` and
`,` lists and `a` for rdf:type; OPTIONAL; FILTER with BOUND, comparison, &&, ||,
!, REGEX, CONTAINS; property paths `p+` and `p*`; ORDER BY (ASC/DESC); LIMIT.
Not supported: UNION, sub-SELECT, aggregates, named graphs, CONSTRUCT, blank
nodes. Those are named here so the boundary is stated rather than discovered.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artifacts  # noqa: E402
import trace as tracetool  # noqa: E402

TPL = Path(__file__).resolve().parent.parent
QUERY_DIR = TPL / "queries"

SCHEMA = "https://pmos.dev/schema#"
PROJECT = "https://pmos.dev/project#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
PREFIXES = {"pmos": SCHEMA, "": PROJECT,
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"}

CLASS_OF = {"requirement": "Requirement", "task": "Task", "acceptance": "AcceptanceCriterion",
            "decision": "Decision", "risk": "Risk", "file": "File"}
# markdown reference field -> RDF predicate, and the inverse we entail from it
PREDICATE_OF = {"satisfies": "satisfies", "depends_on": "dependsOn", "decided_by": "decidedBy",
                "verifies": "verifies", "mitigated_by": "mitigatedBy", "supersedes": "supersedes",
                "touches": "touches"}
INVERSE = {"satisfies": "satisfiedBy", "dependsOn": "blocks", "decidedBy": "constrains",
           "verifies": "verifiedBy", "mitigatedBy": "mitigates", "supersedes": "supersededBy",
           "touches": "touchedBy"}


def iri(value):
    return ("iri", value)


def lit(value):
    return ("lit", str(value))


def ent(eid):
    """Entity IRI. File nodes keep their path, so the id round-trips readably."""
    return iri(PROJECT + eid)


def pred(name):
    return iri(SCHEMA + name)


class Store(object):
    """Triple store with the three classic indexes, so any of the eight access
    patterns resolves without scanning."""

    def __init__(self):
        self.spo, self.pos, self.osp = {}, {}, {}
        self.size = 0
        self.inferred = 0

    def add(self, s, p, o, inferred=False):
        if o in self.spo.setdefault(s, {}).setdefault(p, set()):
            return False
        self.spo[s][p].add(o)
        self.pos.setdefault(p, {}).setdefault(o, set()).add(s)
        self.osp.setdefault(o, {}).setdefault(s, set()).add(p)
        self.size += 1
        if inferred:
            self.inferred += 1
        return True

    def match(self, s=None, p=None, o=None):
        """Yield (s, p, o) for a pattern where None is a wildcard."""
        if s is not None:
            for pp, objs in (self.spo.get(s, {}) if p is None else
                             {p: self.spo.get(s, {}).get(p, set())}).items():
                for oo in ({o} & objs if o is not None else objs):
                    yield (s, pp, oo)
        elif p is not None:
            for oo, subs in (self.pos.get(p, {}) if o is None else
                             {o: self.pos.get(p, {}).get(o, set())}).items():
                for ss in subs:
                    yield (ss, p, oo)
        elif o is not None:
            for ss, preds in self.osp.get(o, {}).items():
                for pp in preds:
                    yield (ss, pp, o)
        else:
            for ss, ps in self.spo.items():
                for pp, objs in ps.items():
                    for oo in objs:
                        yield (ss, pp, oo)

    def objects(self, s, p):
        return self.spo.get(s, {}).get(p, set())

    def subjects(self, p, o):
        return self.pos.get(p, {}).get(o, set())


# ---------------------------------------------------------------- build ----

def build(proj, infer=True):
    """Project the markdown artifacts (plus the code join) into triples."""
    by_id, edges, qa, _ = tracetool.load_project(proj)
    code = tracetool.load_code_graph(proj)
    claimed, _ = tracetool.join(by_id, code)
    st = Store()

    for e in by_id.values():
        s = ent(e.id)
        st.add(s, iri(RDF_TYPE), iri(SCHEMA + CLASS_OF[e.kind]))
        st.add(s, pred("id"), lit(e.id))
        if e.title:
            st.add(s, pred("title"), lit(e.title))
        st.add(s, pred("definedIn"), lit("%s:%d" % (e.file, e.line)))
        for field in ("role", "status", "severity", "law", "jurisdiction", "owner"):
            if e.fields.get(field):
                st.add(s, pred(field), lit(e.fields[field]))
        if e.id in qa:
            st.add(s, pred("qaResult"), lit(qa[e.id]["result"]))
            if qa[e.id].get("evidence"):
                st.add(s, pred("qaEvidence"), lit(qa[e.id]["evidence"]))

    for edge in edges:
        st.add(ent(edge["src"]), pred(PREDICATE_OF[edge["kind"]]), ent(edge["dst"]))

    files = (code or {}).get("files", {})
    for tid, paths in claimed.items():
        for path in paths:
            f = ent("file:" + path)
            st.add(f, iri(RDF_TYPE), iri(SCHEMA + "File"))
            st.add(f, pred("path"), lit(path))
            meta = files.get(path, {})
            if meta.get("community"):
                st.add(f, pred("community"), lit(meta["community"]))
            st.add(ent(tid), pred("touches"), f)
    for target, sources in ((code or {}).get("referenced_by", {}) or {}).items():
        if target not in files:
            continue
        for src, relation in sources:
            st.add(ent("file:" + src), pred("references"), ent("file:" + target))
            st.add(ent("file:" + src), pred("referenceKind"), lit(relation))

    if infer:
        entail(st)
    return st


def entail(st):
    """Materialize the inverse of every asserted relation. Small, closed rule
    set: enough that queries can walk either direction without every caller
    remembering which way the markdown happened to point."""
    for field, name in list(PREDICATE_OF.items()):
        inv = INVERSE.get(name)
        if not inv:
            continue
        for s, _, o in list(st.match(p=pred(name))):
            st.add(o, pred(inv), s, inferred=True)
    return st


# ------------------------------------------------------ serialization ----

# Turtle PN_LOCAL: letters, digits, _ - . :  but no slashes, and never a trailing dot.
SAFE_LOCAL = re.compile(r"^[A-Za-z_][\w:-]*(?:\.[\w:-]+)*$")


def shorten(term):
    """Prefixed name when the local part is legal Turtle, full IRI otherwise.
    File subjects carry a path, so `:file:src/auth/x.py` would not be valid."""
    kind, value = term
    if kind == "lit":
        return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')
    if value == RDF_TYPE:
        return "a"
    for prefix, base in PREFIXES.items():
        if value.startswith(base):
            local = value[len(base):]
            if SAFE_LOCAL.match(local):
                return "%s:%s" % (prefix, local)
    return "<%s>" % value


def to_turtle(st):
    out = ["@prefix %s: <%s> ." % (p, b) for p, b in sorted(PREFIXES.items())] + [""]
    for s in sorted(st.spo, key=lambda t: t[1]):
        preds = st.spo[s]
        lines = []
        for p in sorted(preds, key=lambda t: (t[1] != RDF_TYPE, t[1])):
            objs = " , ".join(sorted(shorten(o) for o in preds[p]))
            lines.append("    %s %s" % (shorten(p), objs))
        out.append("%s\n%s .\n" % (shorten(s), " ;\n".join(lines)))
    return "\n".join(out)


def nt_term(term):
    kind, value = term
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"') if kind == "lit" \
        else "<%s>" % value


def to_ntriples(st):
    rows = ["%s %s %s ." % (nt_term(s), nt_term(p), nt_term(o)) for s, p, o in st.match()]
    return "\n".join(sorted(rows)) + "\n"


NT_LINE = re.compile(r'^(<[^>]*>)\s+(<[^>]*>)\s+(<[^>]*>|"(?:[^"\\]|\\.)*")\s*\.\s*$')


def from_ntriples(text):
    """Read back what to_ntriples wrote, so the store round-trips."""
    st = Store()
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = NT_LINE.match(line)
        if not m:
            raise ValueError("line %d is not a triple: %s" % (n, line[:60]))
        def term(tok):
            if tok.startswith("<"):
                return iri(tok[1:-1])
            return lit(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        st.add(term(m.group(1)), term(m.group(2)), term(m.group(3)))
    return st


# ------------------------------------------------------------ SPARQL ----

TOKEN = re.compile(r"""
    (?P<ws>\s+|\#[^\n]*)
  | (?P<iriref><[^<>\s"{}|^`\\]*>)
  | (?P<var>[?$][A-Za-z_]\w*)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<pname>(?:[A-Za-z_]\w*)?:(?:[A-Za-z_][\w:/-]*(?:\.[\w:/-]+)*)?)
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<op><=|>=|!=|&&|\|\||[=<>!])
  | (?P<punct>[{}.;,()+*])
  | (?P<word>[A-Za-z_]\w*)
""", re.X)

KEYWORDS = {"select", "distinct", "where", "optional", "filter", "bound", "regex", "contains",
            "order", "by", "asc", "desc", "limit", "ask", "prefix", "a", "str", "true", "false"}


class QueryError(Exception):
    pass


def tokenize(text):
    out, pos = [], 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            raise QueryError("cannot tokenize at %r" % text[pos:pos + 20])
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        value = m.group()
        if kind == "word":
            low = value.lower()
            if low not in KEYWORDS:
                raise QueryError("unknown keyword %r" % value)
            kind, value = "kw", low
        out.append((kind, value))
    return out


class Parser(object):
    def __init__(self, tokens, prefixes):
        self.t, self.i = tokens, 0
        self.prefixes = dict(prefixes)

    def peek(self, n=0):
        return self.t[self.i + n] if self.i + n < len(self.t) else (None, None)

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def accept(self, kind, value=None):
        k, v = self.peek()
        if k == kind and (value is None or v == value):
            self.i += 1
            return v
        return None

    def expect(self, kind, value=None):
        v = self.accept(kind, value)
        if v is None:
            k, got = self.peek()
            raise QueryError("expected %s%s, got %r" % (kind, " %r" % value if value else "", got))
        return v

    def resolve(self, kind, value):
        if kind == "iriref":
            return iri(value[1:-1])
        if kind == "pname":
            prefix, local = value.split(":", 1)
            base = self.prefixes.get(prefix)
            if base is None:
                raise QueryError("unknown prefix %r" % (prefix + ":"))
            return iri(base + local)
        if kind == "string":
            return lit(value[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        if kind == "number":
            return lit(value)
        raise QueryError("not a term: %r" % value)

    def term(self):
        k, v = self.peek()
        if k == "var":
            self.next()
            return ("var", v[1:])
        if k in ("iriref", "pname", "string", "number"):
            self.next()
            return self.resolve(k, v)
        raise QueryError("expected a term, got %r" % v)

    def verb(self):
        if self.accept("kw", "a"):
            return {"pred": iri(RDF_TYPE), "mod": None}
        k, v = self.peek()
        if k == "var":
            self.next()
            return {"pred": ("var", v[1:]), "mod": None}
        p = self.term()
        mod = self.accept("punct", "+") or self.accept("punct", "*")
        return {"pred": p, "mod": mod}

    def parse(self):
        while self.accept("kw", "prefix"):
            name = self.expect("pname")
            target = self.expect("iriref")
            self.prefixes[name.rstrip(":").split(":")[0]] = target[1:-1]
        form = "SELECT"
        variables, distinct = [], False
        if self.accept("kw", "ask"):
            form = "ASK"
        else:
            self.expect("kw", "select")
            distinct = bool(self.accept("kw", "distinct"))
            if self.accept("punct", "*"):
                variables = None
            else:
                while self.peek()[0] == "var":
                    variables.append(self.next()[1][1:])
                if not variables:
                    raise QueryError("SELECT needs variables or *")
        self.accept("kw", "where")
        patterns = self.group()
        order, limit = [], None
        if self.accept("kw", "order"):
            self.expect("kw", "by")
            while True:
                direction = "asc"
                if self.accept("kw", "desc"):
                    direction = "desc"
                    self.expect("punct", "(")
                elif self.accept("kw", "asc"):
                    self.expect("punct", "(")
                var = self.expect("var")[1:]
                if direction == "desc" or self.peek() == ("punct", ")"):
                    self.accept("punct", ")")
                order.append((var, direction))
                if self.peek()[0] != "var" and self.peek()[1] not in ("asc", "desc"):
                    break
        if self.accept("kw", "limit"):
            limit = int(self.expect("number"))
        if self.i != len(self.t):
            raise QueryError("trailing input at %r" % (self.peek()[1],))
        return {"form": form, "vars": variables, "distinct": distinct,
                "where": patterns, "order": order, "limit": limit}

    def group(self):
        self.expect("punct", "{")
        patterns = []
        while not self.accept("punct", "}"):
            if self.accept("kw", "optional"):
                patterns.append({"type": "optional", "patterns": self.group()})
                self.accept("punct", ".")
                continue
            if self.accept("kw", "filter"):
                patterns.append({"type": "filter", "expr": self.expression()})
                self.accept("punct", ".")
                continue
            patterns.extend(self.triples())
        return patterns

    def triples(self):
        subject = self.term()
        out = []
        while True:
            v = self.verb()
            while True:
                obj = self.term()
                out.append({"type": "triple", "s": subject, "p": v["pred"],
                            "mod": v["mod"], "o": obj})
                if not self.accept("punct", ","):
                    break
            if not self.accept("punct", ";"):
                break
            if self.peek() in (("punct", "."), ("punct", "}")):
                break
        self.accept("punct", ".")
        return out

    # ---- FILTER expressions
    def expression(self):
        return self.or_expr()

    def or_expr(self):
        left = self.and_expr()
        while self.accept("op", "||"):
            left = ("or", left, self.and_expr())
        return left

    def and_expr(self):
        left = self.cmp_expr()
        while self.accept("op", "&&"):
            left = ("and", left, self.cmp_expr())
        return left

    def cmp_expr(self):
        left = self.unary()
        k, v = self.peek()
        if k == "op" and v in ("=", "!=", "<", ">", "<=", ">="):
            self.next()
            return ("cmp", v, left, self.unary())
        return left

    def unary(self):
        if self.accept("op", "!"):
            return ("not", self.unary())
        return self.primary()

    def primary(self):
        if self.accept("punct", "("):
            e = self.expression()
            self.expect("punct", ")")
            return e
        for name in ("bound", "regex", "contains", "str"):
            if self.accept("kw", name):
                self.expect("punct", "(")
                args = [self.expression()]
                while self.accept("punct", ","):
                    args.append(self.expression())
                self.expect("punct", ")")
                return ("call", name, args)
        if self.accept("kw", "true"):
            return ("const", lit("true"))
        if self.accept("kw", "false"):
            return ("const", lit("false"))
        k, v = self.peek()
        if k == "var":
            self.next()
            return ("var", v[1:])
        return ("const", self.term())


def parse_query(text, prefixes=None):
    return Parser(tokenize(text), prefixes or PREFIXES).parse()


# ---------------------------------------------------------- evaluation ----

def subst(term, binding):
    return binding.get(term[1]) if term[0] == "var" else term


def walk_path(st, p, s, o, mod):
    """Property path `p+` / `p*`: the transitive (and with `*`, reflexive)
    closure of one predicate. Walks forward from a bound subject, backward from
    a bound object, and over every subject when neither is bound."""
    if p is None or p[0] == "var":
        raise QueryError("a property path needs a concrete predicate")

    def reach(start, forward):
        seen, frontier = set(), [start]
        while frontier:
            nxt = []
            for node in frontier:
                step = st.objects(node, p) if forward else st.subjects(p, node)
                for other in step:
                    if other not in seen:
                        seen.add(other)
                        nxt.append(other)
            frontier = nxt
        if mod == "*":
            seen.add(start)
        return seen

    if s is not None:
        for target in reach(s, True):
            if o is None or target == o:
                yield (s, target)
    elif o is not None:
        for source in reach(o, False):
            yield (source, o)
    else:
        for source in list(st.pos.get(p, {}).values()):
            for node in source:
                for target in reach(node, True):
                    yield (node, target)


def eval_triple(st, pat, bindings):
    out = []
    for b in bindings:
        s, p, o = (subst(pat[k], b) for k in ("s", "p", "o"))
        if pat["mod"]:
            for sv, ov in walk_path(st, p, s, o, pat["mod"]):
                nb = dict(b)
                if pat["s"][0] == "var":
                    nb[pat["s"][1]] = sv
                if pat["o"][0] == "var":
                    nb[pat["o"][1]] = ov
                out.append(nb)
            continue
        for triple in st.match(s, p, o):
            nb, ok = dict(b), True
            for term, value in zip((pat["s"], pat["p"], pat["o"]), triple):
                if term[0] == "var":
                    if nb.get(term[1], value) != value:
                        ok = False
                        break
                    nb[term[1]] = value
            if ok:
                out.append(nb)
    return out


def eval_patterns(st, patterns, bindings):
    for pat in patterns:
        if pat["type"] == "triple":
            bindings = eval_triple(st, pat, bindings)
        elif pat["type"] == "optional":          # left join: keep the row either way
            out = []
            for b in bindings:
                found = eval_patterns(st, pat["patterns"], [b])
                out.extend(found if found else [b])
            bindings = out
        elif pat["type"] == "filter":
            bindings = [b for b in bindings if truthy(eval_expr(pat["expr"], b))]
        if not bindings:
            break
    return bindings


def truthy(value):
    return bool(value) and value[1] not in ("false", "")


def as_number(term):
    try:
        return float(term[1])
    except (TypeError, ValueError):
        return None


def compare(op, left, right):
    if left is None or right is None:
        return lit("false")
    a, b = as_number(left), as_number(right)
    if a is None or b is None:
        a, b = left[1], right[1]
    result = {"=": a == b, "!=": a != b, "<": a < b, ">": a > b,
              "<=": a <= b, ">=": a >= b}[op]
    return lit("true" if result else "false")


def eval_expr(node, binding):
    kind = node[0]
    if kind == "var":
        return binding.get(node[1])
    if kind == "const":
        return node[1]
    if kind == "not":
        return lit("false" if truthy(eval_expr(node[1], binding)) else "true")
    if kind == "and":
        return lit("true" if truthy(eval_expr(node[1], binding))
                   and truthy(eval_expr(node[2], binding)) else "false")
    if kind == "or":
        return lit("true" if truthy(eval_expr(node[1], binding))
                   or truthy(eval_expr(node[2], binding)) else "false")
    if kind == "cmp":
        return compare(node[1], eval_expr(node[2], binding), eval_expr(node[3], binding))
    if kind == "call":
        name, args = node[1], node[2]
        if name == "bound":
            return lit("true" if eval_expr(args[0], binding) is not None else "false")
        values = [eval_expr(a, binding) for a in args]
        if any(v is None for v in values):
            return lit("false")
        if name == "str":
            return lit(values[0][1])
        if name == "contains":
            return lit("true" if values[1][1] in values[0][1] else "false")
        if name == "regex":
            flags = re.I if len(values) > 2 and "i" in values[2][1] else 0
            return lit("true" if re.search(values[1][1], values[0][1], flags) else "false")
    raise QueryError("cannot evaluate %r" % (node,))


def execute(st, query):
    bindings = eval_patterns(st, query["where"], [{}])
    if query["form"] == "ASK":
        return None, bool(bindings)
    names = query["vars"]
    if names is None:
        names = sorted({k for b in bindings for k in b})
    rows = [tuple(b.get(v) for v in names) for b in bindings]
    if query["distinct"]:
        seen, unique = set(), []
        for row in rows:
            if row not in seen:
                seen.add(row)
                unique.append(row)
        rows = unique
    for var, direction in reversed(query["order"]):
        idx = names.index(var) if var in names else None
        if idx is None:
            continue
        rows.sort(key=lambda r: (r[idx] is None, r[idx][1] if r[idx] else ""),
                  reverse=direction == "desc")
    if query["limit"] is not None:
        rows = rows[:query["limit"]]
    return names, rows


def results_json(names, rows):
    """SPARQL 1.1 Query Results JSON."""
    if names is None:
        return {"head": {}, "boolean": rows}
    out = []
    for row in rows:
        binding = {}
        for name, term in zip(names, row):
            if term is None:
                continue
            binding[name] = {"type": "uri" if term[0] == "iri" else "literal", "value": term[1]}
        out.append(binding)
    return {"head": {"vars": names}, "results": {"bindings": out}}


def render(names, rows):
    if names is None:
        return "true" if rows else "false"
    if not rows:
        return "(no results)"
    cells = [[shorten(t) if t else "" for t in row] for row in rows]
    widths = [max(len(names[i]), max(len(c[i]) for c in cells)) for i in range(len(names))]
    head = "  ".join(n.ljust(widths[i]) for i, n in enumerate(names))
    line = "  ".join("-" * w for w in widths)
    body = "\n".join("  ".join(c[i].ljust(widths[i]) for i in range(len(names))) for c in cells)
    return "%s\n%s\n%s\n\n%d row(s)" % (head, line, body, len(rows))


def load_named(name):
    path = QUERY_DIR / (name + ".rq")
    if not path.is_file():
        available = sorted(p.stem for p in QUERY_DIR.glob("*.rq")) if QUERY_DIR.is_dir() else []
        raise QueryError("no stored query %r (have: %s)" % (name, ", ".join(available)))
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- CLI ----

def store_for(args):
    if getattr(args, "from_file", None):
        return from_ntriples(Path(args.from_file).read_text(encoding="utf-8"))
    return build(args.project, infer=not getattr(args, "no_infer", False))


def cmd_build(args):
    st = store_for(args)
    out = Path(args.out) if args.out else Path(args.project) / ".pmos" / "graph"
    out.parent.mkdir(parents=True, exist_ok=True)
    ttl, nt = out.with_suffix(".ttl"), out.with_suffix(".nt")
    ttl.write_text(to_turtle(st), encoding="utf-8")
    nt.write_text(to_ntriples(st), encoding="utf-8")
    print("%d triple(s) (%d asserted, %d entailed) -> %s, %s"
          % (st.size, st.size - st.inferred, st.inferred, ttl, nt))
    return 0


def cmd_query(args):
    text = args.query or (load_named(args.name) if args.name else
                          Path(args.file).read_text(encoding="utf-8"))
    st = store_for(args)
    names, rows = execute(st, parse_query(text))
    if args.json:
        print(json.dumps(results_json(names, rows), indent=1))
    else:
        print(render(names, rows))
    if names is None:
        return 0 if rows else 1
    return 0


def cmd_stats(args):
    st = store_for(args)
    classes, predicates = {}, {}
    for s, p, o in st.match():
        predicates[shorten(p)] = predicates.get(shorten(p), 0) + 1
        if p == iri(RDF_TYPE):
            classes[shorten(o)] = classes.get(shorten(o), 0) + 1
    if args.json:
        print(json.dumps({"triples": st.size, "asserted": st.size - st.inferred,
                          "entailed": st.inferred, "subjects": len(st.spo),
                          "classes": classes, "predicates": predicates}, indent=1))
        return 0
    print("%d triple(s): %d asserted, %d entailed, over %d subject(s)"
          % (st.size, st.size - st.inferred, st.inferred, len(st.spo)))
    print("\nclasses")
    for name, n in sorted(classes.items()):
        print("  %-28s %4d" % (name, n))
    print("\npredicates")
    for name, n in sorted(predicates.items(), key=lambda kv: -kv[1]):
        print("  %-28s %4d" % (name, n))
    return 0


def cmd_queries(args):
    if not QUERY_DIR.is_dir():
        print("no stored queries at %s" % QUERY_DIR)
        return 1
    for path in sorted(QUERY_DIR.glob("*.rq")):
        head = next((l[1:].strip() for l in path.read_text(encoding="utf-8").splitlines()
                     if l.startswith("#")), "")
        print("%-26s %s" % (path.stem, head))
    return 0


FIXTURE = dict(tracetool.FIXTURE)


def selftest():
    import tempfile
    ok = True
    root = Path(tempfile.mkdtemp())
    for rel, body in FIXTURE.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    st = build(root)

    def rows(q):
        names, data = execute(st, parse_query(q))
        return [tuple(shorten(t) if t else None for t in row) for row in data]

    def ask(q):
        return execute(st, parse_query(q))[1]

    cases = [
        ("entities become typed triples",
         rows("SELECT ?t WHERE { ?t a pmos:Task } ORDER BY ?t") == [(":T-001",), (":T-002",)]),
        ("references become predicates",
         ask("ASK { :T-001 pmos:satisfies :R-001 }")),
        ("attributes become literal triples",
         rows("SELECT ?s WHERE { :L-001 pmos:severity ?s }") == [('"high"',)]),
        ("the code join is in the graph",
         ask("ASK { :T-001 pmos:touches ?f . ?f pmos:path \"src/auth/reset.py\" }")),
        ("inverse relations are entailed, not asserted",
         ask("ASK { :R-001 pmos:satisfiedBy :T-001 }") and st.inferred > 0),
        ("joins across shared variables",
         rows("SELECT ?r WHERE { ?t a pmos:Task ; pmos:satisfies ?r . "
              "?c pmos:verifies ?t ; pmos:qaResult \"pass\" } ORDER BY ?r")
         == [(":R-001",), (":R-002",)]),
        ("OPTIONAL keeps the unmatched row",
         len(rows("SELECT ?t ?x WHERE { ?t a pmos:Task OPTIONAL { ?t pmos:decidedBy ?x } }")) == 2),
        ("FILTER !BOUND finds the missing edge",
         rows("SELECT ?r WHERE { ?r a pmos:Requirement OPTIONAL { ?t pmos:satisfies ?r } "
              "FILTER (!BOUND(?t)) }") == []),
        ("FILTER compares literals",
         rows("SELECT ?l WHERE { ?l a pmos:Risk ; pmos:severity ?s FILTER (?s = \"high\") }")
         == [(":L-001",)]),
        ("REGEX over literals",
         len(rows("SELECT ?t WHERE { ?t a pmos:Task ; pmos:title ?ti "
                  "FILTER REGEX(?ti, \"^session\", \"i\") }")) == 1),
        ("property path walks the dependency chain",
         ask("ASK { :T-002 pmos:dependsOn+ :T-001 }")),
        ("reflexive path includes the start",
         len(rows("SELECT ?x WHERE { :T-002 pmos:dependsOn* ?x }")) == 2),
        ("path from an unbound subject",
         len(rows("SELECT ?a ?b WHERE { ?a pmos:dependsOn+ ?b }")) == 1),
        ("DISTINCT collapses duplicates",
         len(rows("SELECT DISTINCT ?k WHERE { ?s a ?k }")) == len(set(
             r for r in rows("SELECT DISTINCT ?k WHERE { ?s a ?k }")))),
        ("LIMIT truncates", len(rows("SELECT ?s WHERE { ?s ?p ?o } LIMIT 3")) == 3),
        ("ORDER BY DESC reverses",
         rows("SELECT ?t WHERE { ?t a pmos:Task } ORDER BY DESC(?t)") == [(":T-002",), (":T-001",)]),
        ("ASK is false when the pattern misses",
         ask("ASK { :T-001 pmos:dependsOn :T-002 }") is False),
        ("PREFIX declarations are honoured, as any pasted SPARQL carries",
         rows('PREFIX p: <https://pmos.dev/schema#> '
              'SELECT ?t WHERE { ?t a p:Task } ORDER BY ?t') == [(":T-001",), (":T-002",)]),
        ("a redeclared prefix wins over the default",
         rows('PREFIX pmos: <https://pmos.dev/schema#> '
              'SELECT ?r WHERE { ?r a pmos:Risk }') == [(":L-001",)]),
    ]

    # serialization round-trips through N-Triples
    reloaded = from_ntriples(to_ntriples(st))
    cases.append(("N-Triples round-trips", reloaded.size == st.size))
    ttl = to_turtle(st)
    cases.append(("Turtle carries prefixes and types",
                  "@prefix pmos:" in ttl and "a pmos:Task" in ttl))

    # every stored query must parse and run against a real graph
    if QUERY_DIR.is_dir():
        for path in sorted(QUERY_DIR.glob("*.rq")):
            try:
                execute(st, parse_query(path.read_text(encoding="utf-8")))
                cases.append(("stored query %s runs" % path.stem, True))
            except Exception as exc:  # noqa: BLE001 - report, do not mask
                cases.append(("stored query %s runs (%s)" % (path.stem, exc), False))

    # a broken query must be rejected with a message, not a traceback
    for bad, why in [("SELECT ?x WHERE { ?x foo:bar ?y }", "unknown prefix"),
                     ("SELECT WHERE { ?x ?y ?z }", "no variables"),
                     ("SELECT ?x WHERE { ?x pmos:p+ ?y", "unclosed brace")]:
        try:
            parse_query(bad)
            cases.append(("rejects bad query (%s)" % why, False))
        except QueryError:
            cases.append(("rejects bad query (%s)" % why, True))

    for label, cond in cases:
        print("   %s %s" % ("[OK]  " if cond else "[FAIL]", label))
        ok = ok and cond
    print("SELFTEST PASS" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="PMOS knowledge graph: triples + SPARQL subset")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--project", default=".")
        p.add_argument("--json", action="store_true")
        p.add_argument("--from-file", default=None,
                       help="query a serialized .nt store instead of rebuilding from markdown")
        p.add_argument("--no-infer", action="store_true", help="assert only, entail nothing")

    p = sub.add_parser("build", help="write graph.ttl and graph.nt")
    common(p)
    p.add_argument("--out", default=None)
    for name, help_text in (("query", "run SELECT/ASK"), ("ask", "run an ASK query")):
        p = sub.add_parser(name, help=help_text)
        common(p)
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("-q", "--query", default=None)
        g.add_argument("-f", "--file", default=None)
        g.add_argument("--name", default=None, help="a stored query from queries/")
    p = sub.add_parser("stats", help="triple, class and predicate counts")
    common(p)
    sub.add_parser("queries", help="list the stored queries")
    sub.add_parser("selftest")

    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "queries":
        return cmd_queries(args)
    try:
        return {"build": cmd_build, "query": cmd_query, "ask": cmd_query,
                "stats": cmd_stats}[args.cmd](args)
    except QueryError as exc:
        print("query error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
