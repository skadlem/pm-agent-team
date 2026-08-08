#!/bin/sh
# PMOS template installer (Unix). Copies the 3 skills into ~/.jcode/skills
# and records the template root so skills can find it.
set -e
TPL="$(cd "$(dirname "$0")" && pwd)"
SK="$HOME/.jcode/skills"
mkdir -p "$SK"
for s in project-team-start project-team-work pm-kb-bootstrap pm-kb-enrich; do
  rm -rf "$SK/$s"
  cp -r "$TPL/skills/$s" "$SK/$s"
done
printf '%s\n' "$TPL" > "$HOME/.jcode/pmos-template-root"
echo "PMOS template installed."
echo "  skills   -> $SK"
echo "  template -> $TPL"
