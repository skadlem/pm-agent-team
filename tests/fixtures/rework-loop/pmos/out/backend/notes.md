# Backend notes

Implemented T-001. graphify queries run before editing: `query_graph "reset token"`,
`get_neighbors src_auth_reset`. Reworked twice after QA failures: the check and the update
are STILL not in one transaction on the second attempt.
