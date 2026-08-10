## Agent operating rules (all roles)
1. Partial context only: retrieve what you need via KB search and graphify queries; never dump the
   full knowledge base or the full repository into your context.
2. Retrieval order: KB search first, then graphify for repo questions, then targeted file reads.
   Stop as soon as you have enough. Code-touching roles (architect, backend, frontend, devops,
   qa): run at least one graphify query before editing code and record each query in your notes
   (.pmos/out/<role>/notes.md).
3. Artifacts are small markdown files under .pmos/out/<role>/; keep each focused and under ~300 lines.
4. Evidence before claims: run the check, paste the result. No "should work".
5. Decisions get written down with the reason, where future agents can search them.
6. Blockers are escalated immediately with context, not silently worked around.
7. Respect scope: the charter's out-of-scope list is binding unless the user changes it.
