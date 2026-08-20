# Backend notes

Implemented T-001. graphify queries run before editing: `query_graph "reset token"`,
`get_neighbors src_auth_reset`. Token redemption marks the row redeemed, but the check and the
update are not yet in one transaction.
