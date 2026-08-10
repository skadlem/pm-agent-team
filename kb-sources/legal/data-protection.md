# Data protection fundamentals

## Lawful basis analysis
Every processing purpose needs a lawful basis: consent, contract, legal obligation, or legitimate
interest. Identify the basis for each purpose and record it in the data inventory (`.pmos/out/legal/data-inventory.md`).
Consent must be specific, informed, and withdrawable. Legitimate interest requires a balancing test and
is weaker than consent or contract. A missing or wrong basis is a compliance risk, not a documentation
gap. Checklist: list every processing purpose, assign one lawful basis, and verify the basis still holds
at launch and on each major change.

## Data subject rights
Individuals can exercise access, rectification, erasure, portability, and objection. Each right maps to
an obligation (respond within the statutory window, provide data in a machine-readable format, honor
opt-outs) and to a risk entry in the risk register. Build the controls before launch: an export endpoint,
an erasure path, and a request-handling queue. Checklist: for each right, confirm the project can fulfil
it in time and record the risk entry with its law/article citation.

## Data residency and transfers
Where data is stored and processed determines which regime applies. Identify the storage region and the
countries whose residents' data you hold. Cross-border transfers need an adequacy decision or a mechanism
such as Standard Contractual Clauses (SCCs). A transfer without a valid mechanism is a serious violation.
Checklist: confirm each storage/processing location and document the transfer mechanism for every data
flow that crosses borders.

## Breach notification
Breach notification has a typical SLA, for example 72 hours to the regulator when the breach risks
individuals, with affected individuals notified where harm is likely. Notification is a legal deadline,
so an incident plan must pre-exist launch: who declares a breach, who drafts the notice, and how the
timer starts. Checklist: define the breach response plan, name the on-call owner, and record the SLA as a
compliance calendar item.
