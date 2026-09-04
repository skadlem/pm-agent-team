# Stage: Wave 3 + Wave 4 (steps 9-10)

Read ORCHESTRATOR.md (core rules) first. This file covers implementation and the QA gate.

9. Wave 3: implementation. Spawn backend/frontend/devops/marketing per the task graph, parallel
   where independent. Name the `T-NNN` ids each worker owns in its assignment, and have it record
   them in its notes; that is what later ties delivered code back to the charter. Each worker fills
   in its task's `touches:` with the paths it actually changed - that is the join between the plan
   and the code graph, and what `trace.py unplanned` checks against. Workers read plan + their role's out dir, query KB + graphify as needed.
   BEFORE spawning Wave 3, check the graph is fresh: compare the newest source file mtime under
   the project (excluding .pmos/, graphify-out/, .git/) against `graphify-out/graph.json`; if any
   source is newer, run `/graphify <path> --update` first and say so.
10. Wave 4 (QA): run the verification gate against the acceptance criteria in the plan. Fail -> back
   to wave 3 with the defect report. Pass -> checkpoint.
   `python TPL/tools/trace.py coverage --project .` prints the requirement -> task -> criterion -> QA
   matrix to work through, so no criterion is verified twice and none is silently skipped.
   Brownfield: QA FIRST runs the project's existing test suite and records the baseline in its
   report (pre-existing failures vs failures introduced by the change), and verifies nothing in
   the charter's do-not-touch list changed.
   QA reports one entry per acceptance criterion in `.pmos/out/qa/test-report.md` (lean roster:
   `.pmos/out/reviewer/test-report.md`), as a list line `- A-NNN: pass|fail - <evidence>` or as a
   table row `| A-NNN <title> | PASS | <evidence> |` — both are read by the tooling, so write
   whichever suits the evidence. `pass` is the only status that verifies; `partial` and `n/a`
   are reported-but-unverified. A criterion with no entry is not "passed", it is unreported.
   Check the report landed before closing the gate: `trace.py coverage` prints
   `N/M criteria reported, K passing` — if that reads 0/M, the results are not being parsed and
   the gate has no machine-readable evidence behind it.
   QA also binds the report to the tree it tested: run
   `python TPL/tools/artifacts.py fingerprint --project .` and add a `tree: <hash>` line to the
   report. `artifacts.py` then warns "QA evidence is stale" whenever the source tree changes
   after the evidence was collected, so the gate never approves old results against new code.
   `python TPL/tools/artifacts.py --project .` then makes the next two checks mechanical: it errors
   on a result for a criterion nobody defined, and warns when a `status: mitigated` risk points at a
   task whose criteria did not pass. `kg.py query --name unproven-mitigations` and
   `--name untested-code` answer the same questions against the graph when you need the detail.
   QA also re-checks that `status: mitigated` risk register items are actually implemented (owner
   -> delivered work) and legal does a light re-run: diff risk ids against the wave 2 register
   (nothing silently disappears) and append a wave-4 section with L-ids and status changes,
   without rewriting the register.

Next: `docs/stages/checkpoint.md` (step 11).
