#!/usr/bin/env python3
"""PMOS GitHub issues export (L-8): T-NNN plan tasks -> GitHub issues.

The most valuable brownfield flow: a change to an existing repo is planned as
T-NNN tasks; exporting them as GitHub issues gives humans (and other tools) a
tracked backlog to assign, comment on, and close.

    python tools/issues.py export --project . --repo owner/repo --dry-run
    python tools/issues.py export --project . --repo owner/repo   # uses gh CLI

Dry-run prints the issue title + body that WOULD be created. Real export calls
`gh issue create` once per task; a task is skipped when an issue with the same
title already exists (idempotent, safe to re-run). The body carries the stable
ids (T-NNN, satisfies R-NNN, acceptance A-NNN, decided_by ADR-NNN) so the
issues stay traceable back into the plan.

Exit codes: 0 ok (or dry-run), 1 export error, 2 usage error.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TPL / "tools"))
import artifacts  # noqa: E402  (sibling tool: shared id parsing)

BLOCK = re.compile(r"^- id:\s*(T-\d{1,4})\s*$", re.M)
FIELD = re.compile(r"^(\s+)([a-z_]+):\s*(.*?)\s*$")


def parse_tasks(plan_path):
    """Extract T-NNN task blocks from plan.md, keeping id + fields.

    Blocks are consecutive `- id: T-NNN` + indented `key: value` lines (the
    yaml fence inside plan.md). A block ends at the next `- id:`, a dedent to
    fence level, or a non-field line."""
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    tasks = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = BLOCK.match(line)
        if not m:
            continue
        tid = artifacts.canonical(m.group(1))
        fields = {}
        for nxt in lines[i + 1:]:
            fm = FIELD.match(nxt)
            if not fm:
                break
            indent, key, val = len(fm.group(1)), fm.group(2), fm.group(3).strip()
            if indent < 2 or key == "id":
                break
            if key in fields:  # a repeated key means the next block started
                break
            fields[key] = val
        tasks.append({"id": tid, "fields": fields})
    return tasks


def task_issue(task):
    f = task["fields"]
    title = "%s: %s" % (task["id"], f.get("title", "(untitled)"))
    body = ["### %s" % task["id"], "", f.get("title", "")]
    for key in ("satisfies", "depends_on", "decided_by", "verifies", "role"):
        if f.get(key):
            body.append("- %s: %s" % (key, f[key]))
    if f.get("touches"):
        body.append("- touches: %s" % f["touches"])
    body.append("")
    body.append("_exported by PMOS tools/issues.py from .pmos/plans/plan.md_")
    return title, "\n".join(body)


def gh(args, *argv):
    return subprocess.run(["gh"] + list(argv), capture_output=True, text=True,
                          cwd=str(Path(args.project)))


def cmd_export(args):
    plan = Path(args.project) / ".pmos" / "plans" / "plan.md"
    if not plan.is_file():
        print("no plan at %s" % plan, file=sys.stderr)
        return 2
    tasks = parse_tasks(plan)
    if not tasks:
        print("no T-NNN tasks in %s" % plan, file=sys.stderr)
        return 2

    # dedupe: existing issue titles that match an id make the export idempotent
    existing = set()
    if not args.dry_run:
        r = gh(args, "issue", "list", "--repo", args.repo, "--limit", "200",
               "--json", "title")
        if r.returncode != 0:
            print("gh issue list failed: %s" % r.stderr.strip()[:200], file=sys.stderr)
            return 1
        existing = {i["title"] for i in json.loads(r.stdout or "[]")}

    created, skipped = 0, 0
    for task in tasks:
        title, body = task_issue(task)
        if not args.dry_run and title in existing:
            skipped += 1
            continue
        if args.dry_run:
            print("== %s" % title)
            print(body)
            print()
            continue
        r = gh(args, "issue", "create", "--repo", args.repo,
               "--title", title, "--body", body)
        if r.returncode != 0:
            print("gh issue create failed for %s: %s"
                  % (title, r.stderr.strip()[:200]), file=sys.stderr)
            return 1
        created += 1
        print("created %s" % title)
    print("issues: %d created, %d already existed%s"
          % (created, skipped, " (dry run)" if args.dry_run else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description="PMOS plan tasks -> GitHub issues")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export", help="export T-NNN tasks as GitHub issues")
    p.add_argument("--project", default=".")
    p.add_argument("--repo", required=True, help="owner/repo on GitHub")
    p.add_argument("--dry-run", action="store_true",
                   help="print the issues that would be created; nothing is sent")
    args = ap.parse_args()
    return cmd_export(args)


if __name__ == "__main__":
    sys.exit(main())
