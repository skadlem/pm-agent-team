# Risk register template

## Entry schema
Every risk register entry uses exactly this schema (from the legal advisor spec, section 6). One
`- id` block per risk, stable ids starting at L-001, in the register at `.pmos/out/legal/risk-register.md`.

```yaml
- id: L-001
  risk: <short statement>
  jurisdiction: <cc> | global
  law: <specific law + article, e.g. GDPR Art. 17>
  source: <URL>
  severity: high | medium | low
  probability: high | medium | low
  obligation: <what the project must do>
  mitigation: <planned action>
  owner: <role, e.g. backend>
  status: open | mitigated | requires-counsel
```

## Citation and gating rules
Every entry must cite a specific law/article and a source URL. No citation means no entry: mark the
item `requires-counsel` instead of asserting it. A `severity: high` item with `status: open` blocks
GATE 2 unless the user explicitly accepts the risk. Risk ids are stable and diffed at wave 4: compare the
wave-4 register against the wave-2 register to ensure nothing silently disappears. `owner` names the role
responsible for the mitigation (for example backend), and `status` moves from `open` to `mitigated` only
after the mitigation is implemented and verified.
