# Spawn template + model fallback

Read ORCHESTRATOR.md (core rules) first. These two sections apply to EVERY wave, so they are
kept out of the per-wave stage files; load this file whenever you are about to spawn workers
or a worker has failed.

## Worker spawn prompt template

```
You are the {{role_name}} on this project. Working dir: {{PROJ}}.
Spawn model: {{model}} (effort {{effort}}). Pre-GATE-1 waves: the temporary model picked
per the "Pre-GATE-1 worker model" rule. Post-GATE-1: per the user-approved team-model.json.

Your assignment:
{{assignment}}

Mandatory procedure:
1. Load these skills: {{role_skills}} (plus verification-before-completion).
2. Context: read .pmos/charter.md and {{relevant upstream artifacts}}.
3. Knowledge base: search BEFORE answering anything domain-specific:
   python "{{TPL}}/tools/kb.py" search --db "{{PROJ}}/.pmos/kb.sqlite3" "<query>" --role {{ns}} -k 5
   You may add one --role shared search too. Never dump the DB.
4. Repo questions: use the graphify skill (query mode), never full-repo reads.
   BROWNFIELD RULE: before writing or changing any code, graphify-query for existing similar
   patterns and read .pmos/out/architect/current-state.md conventions; conform to them.
   New code must look like it belongs in this codebase.
6. Write outputs to {{artifacts}}. Keep them concise. Anything another role must reference
   carries a stable id, and every reference you make (`satisfies`, `depends_on`, `decided_by`,
   `verifies`, `mitigated_by`, `supersedes`) names an id that already exists - see
   ARTIFACT-SCHEMA.md. Check your own work with
   `python "{{TPL}}/tools/artifacts.py" --project "{{PROJ}}"` before reporting done.
7. Report back: what you did, decisions made, blockers, artifacts written.
```

Spawn via the an OpenHands one-shot spawn (tools/openhands_run.py) with a clear `label` like "pm", "architect", "backend-1". Use one
worker per task chunk; parallelize independent chunks.

## Worker model fallback (failed / out of tokens)

The recommended model is only the FIRST attempt. Every role has an ordered fallback ladder in
`.pmos/team-model-ladder.json` (written by `recommend.py --ladder-out`; best-first by benchmark
score, then cheapest). The `suggested` model in `.pmos/team-model.json` is the first attempt; the
ladder's next entries are the fallbacks.

When a worker reports failed or crashed (e.g. ran out of tokens / context-limit, or an
unrecoverable error) and the task is not inherently impossible, retry the SAME task on the next
untried model in that role's ladder:

1. Log the failure in `.pmos/log.md` (role, task, model tried, failure reason).
2. If the failed model is served by more than one provider on this system, first retry the SAME
   model on the next provider in its fallback chain (`suggested_fallbacks` in `recommend.py`
   output; `providers`/`routes` JSON fields map every ladder entry to its chain and route ids,
   e.g. `glm-5.2` -> `[OpenAI-compatible, NVIDIA NIM]`).
3. Spawn a FRESH worker for that task, passing the next model explicitly (OH_MODEL on the openhands runner
   spawn). Never continue a half-finished run; re-run the task from its clean start.
4. Reuse the task's upstream artifacts (plan, out dirs, KB); do not re-run independent
   already-completed tasks.
5. Cap fallbacks per task at `max_fallbacks_per_task` (config.json `context_rules`, default 4). After that, STOP and escalate to the user:
   give the failure reason and the models already tried. Do not loop indefinitely.
6. If a role's ladder is empty or exhausted, escalate to the user rather than guessing.

The coordinator may also apply the ladder proactively: if a cheap pick repeatedly errors mid-run,
promote that role's model to the next best entry from the start (log it). This keeps the team
moving without surfacing every transient failure to the user.

## Failure taxonomy: retry vs replan (L-4)

The ladder answers ONE question: "was this failure the model's fault?" When the same task keeps
coming back, retrying it on another model is the wrong fix. Decide mechanically — the decision
comes from the event trace, not from how the coordinator feels:

1. Run `python TPL/tools/events.py report --project .` at every checkpoint. Its `decision` field
   is the taxonomy:
   - `continue` (fewer than 2 rework loops) — keep going; single failures are ladder business.
   - `replan` (2 or more rework loops, i.e. QA sent work back twice) — STOP retrying. The task
     as defined is not being understood; a new model on the same prompt will fail the same way.
2. On `replan`, do NOT burn more ladder fallbacks on the failing task. Instead:
   a. PM re-splits the task into smaller tasks (decompose) OR rewrites the acceptance criteria
      and spawn instructions (replan), then re-enters it at the wave it belongs to.
   b. Log the decision and the reason in `.pmos/log.md` (the events trace records the runs; the
      log records the reasoning).
   c. The next checkpoint re-runs `events.py report`; only a fresh failure of the NEW task
      increments the loop counter again (the trace is append-only and wave-ordered).
3. `state.py` prints the same decision on resume (`decision: replan` with a WARN), so a session
   that comes back after the rework does not quietly restart the ladder loop.
