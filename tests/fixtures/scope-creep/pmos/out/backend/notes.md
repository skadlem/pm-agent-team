# Backend notes

Implemented T-001 in `src/auth`. graphify queries run first: `query_graph "reset token"`.
While in there, also tidied the billing helper - it was calling the same mail sender.
