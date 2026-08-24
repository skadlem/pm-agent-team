# Stage: checkpoint (step 11)

Read ORCHESTRATOR.md (core rules) first. This file covers what every checkpoint does.

11. Checkpoint: append to `.pmos/log.md` (date, wave, what shipped, what's next), commit if repo,
   report to user. Commit as you go at each gate. Also verify each code-touching worker's notes
   record the graphify queries they ran (rule 2b); flag any worker that edited without one
   (re-run its graphify queries and re-check its diff). Record measurable facts too, so the run
   can be evaluated afterwards: number of workers spawned, QA gate pass/fail and defect count,
   rework loops (wave 4 -> wave 3), KB budget usage (`kb.py budget`), and acceptance criteria
   pass rate.
   Also run `python TPL/tools/cost.py report --project .` and log actual spend, the remaining
   budget, and its estimate-accuracy line; exit code 2 means the project is over `budget_usd`, so
   stop and ask. Every few waves run `python TPL/tools/cost.py calibrate --project . --write` so
   later estimates come from this project's own measured usage instead of the flat default.
   Also run `python TPL/tools/events.py report --project .` and log the rework-loop count and
   ladder retries — two rework loops (wave 4 -> wave 3) is the signal to stop and re-plan with
   the user instead of looping a third time.
   Run `python TPL/tools/artifacts.py --project .` at every checkpoint and log its counts plus any
   findings, so traceability breaks surface in the wave that caused them rather than at QA.
   Then run `python TPL/tools/trace.py unplanned --project .`: it lists changed files no task claims.
   Each one is either work that needs a task (scope creep, caught in the wave that caused it) or a
   `touches:` entry a worker forgot. Resolve them before the checkpoint closes; log the count.
