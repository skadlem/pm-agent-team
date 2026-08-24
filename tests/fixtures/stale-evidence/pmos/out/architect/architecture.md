# Architecture

## Modules
`src/auth` owns reset tokens: issue, redeem, invalidate. Tokens are stored hashed and marked
redeemed in the same transaction that accepts them, so a replay cannot succeed.
