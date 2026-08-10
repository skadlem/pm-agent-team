# Compliance calendar: <project>

Template for dated, ongoing compliance obligations in `.pmos/out/legal/compliance-calendar.md`. Fill a
row per obligation using dates from the jurisdiction pack (phased obligations) and the project's launch
date.

| due | obligation | source (law/article) | owner | status |
|-----|-----------|----------------------|-------|--------|
| <date> | e.g. breach notification SLA (72h) | GDPR Art. 33 | devops | active |
| <date> | e.g. register of processing activities | GDPR Art. 30 | legal | active |

## Calendar rules
The PM folds these obligations into milestones. On resume, the coordinator checks overdue items against
elapsed time: an obligation whose due date has passed and is still `active` must be escalated or its due
date re-baselined. Dates come from the jurisdiction pack's phased application dates and the project's
launch date, not from guesses.
