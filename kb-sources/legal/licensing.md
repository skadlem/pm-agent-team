# Licensing fundamentals

## License compatibility
Permissive licenses (MIT, Apache-2.0, BSD) allow reuse with few conditions. Copyleft licenses (GPL, AGPL,
LGPL) can force source disclosure of derivative works, and AGPL extends that to network use. Mixing
copyleft code into a closed-source product can create a violation. Checklist: for each dependency,
classify its license as permissive or copyleft and record the compatibility verdict in
`.pmos/out/legal/licenses.md`.

## Audit the manifest
Scan the dependency manifests (package.json, requirements.txt, go.mod, Cargo.toml) for licenses. Record
each dependency, its license, and a compatibility verdict in `licenses.md`. A dependency without a
declared license is a risk, not an all-clear. Checklist: produce dependency to license to compatible?
rows for every runtime dependency, and flag unlicensed or copyleft entries for review.

## API and ToS constraints
Model and data APIs may ban output used for competing products, training, or certain industries. Read the
terms of service before relying on an API; a violation can kill the feature or the project. Checklist:
verify each external API's ToS against the project's use case and record any restriction as a risk entry
with its source URL.

## Project license choice
Pick the project's own license at the plan stage so compatibility can be checked against every dependency.
Choosing the license late can force a rewrite or a dependency swap. Checklist: choose a project license,
record it in the charter, and re-check compatibility as dependencies change.
