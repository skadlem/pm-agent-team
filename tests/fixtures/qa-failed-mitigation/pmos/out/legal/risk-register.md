# Risk register

```yaml
- id: L-001
  risk: a reset token stays valid after it has been used
  jurisdiction: EU
  law: GDPR Art. 32
  source: https://eur-lex.europa.eu/eli/reg/2016/679/oj
  severity: high
  probability: medium
  obligation: ensure integrity and confidentiality of credentials
  mitigation: single-use tokens
  owner: backend
  mitigated_by: T-001
  status: mitigated
```
