#!/bin/sh
# PMOS template installer. Usage: sh install.sh [host]
# host: claude (default) | jcode | openhands | hermes
#
# Copies the 4 skills (the HOST's rendered bundle, so another host's idioms are
# already rewritten) into the host's global skills dir and records the template root,
# exactly the paths hosts/<host>.json declares.
set -e
TPL="$(cd "$(dirname "$0")" && pwd)"
HOST="${1:-claude}"

if [ ! -f "$TPL/hosts/$HOST.json" ]; then
    echo "unknown host '$HOST'; hosts with adapters:" >&2
    ls "$TPL"/hosts/*.json | sed 's|.*/||; s/\.json$//; s/^/  /' >&2
    exit 2
fi

# skills_dir + template_root_file come from the adapter config; python3 is
# already a PMOS requirement, so parsing JSON with it adds no dependency
host_json="$TPL/hosts/$HOST.json"
SK="$(python3 -c "import json,os,sys; print(os.path.expanduser(json.load(open(sys.argv[1]))['skills_dir']))" "$host_json")"
ROOT="$(python3 -c "import json,os,sys; print(os.path.expanduser(json.load(open(sys.argv[1]))['template_root_file']))" "$host_json")"

SRC="$TPL/host-bundles/$HOST/skills"
[ -d "$SRC" ] || SRC="$TPL/skills"   # hosts without a rendered bundle

mkdir -p "$SK"
for s in project-team-start project-team-work pm-kb-bootstrap pm-kb-enrich; do
    rm -rf "$SK/$s"
    cp -r "$SRC/$s" "$SK/$s"
done
mkdir -p "$(dirname "$ROOT")"
printf '%s\n' "$TPL" > "$ROOT"

echo "PMOS template installed for host: $HOST"
echo "  skills   -> $SK"
echo "  template -> $ROOT"
if [ -f "$TPL/host-bundles/$HOST/README.md" ]; then
    echo "  next steps -> host-bundles/$HOST/README.md"
fi
