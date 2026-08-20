# Architecture

## Modules
`src/auth` owns reset tokens and the mail hand-off. Tokens are single-use and expire in 15 minutes.
