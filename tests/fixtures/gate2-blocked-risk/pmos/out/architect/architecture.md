# Architecture

## Modules
- `src/auth` owns credential handling, reset tokens and the mail hand-off.
- `src/session` owns session issue/expiry. No other module writes session state.

## Contracts
Reset tokens are single-use and expire in 15 minutes. The mail sender is an interface so the
transport can be swapped without touching the token logic.
