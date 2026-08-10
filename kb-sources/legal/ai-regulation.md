# AI regulation fundamentals

## AI risk tiers
Classify the project's AI use per the jurisdiction's AI act: prohibited, high-risk, limited, or minimal.
Prohibited uses (e.g. social scoring) must not ship. High-risk examples include hiring, credit scoring,
and biometric identification, and they carry the heaviest obligations. Minimal-risk AI has light or no
obligations. Checklist: place every AI feature in a tier and confirm prohibited uses are absent; document
the tier for each feature in the risk register.

## Transparency and logging
Disclose that content is AI-generated, keep model inference logs, and ensure human oversight for
high-risk systems. Transparency covers user-facing notices and, where required, marking synthetic content.
Logging must be sufficient to reconstruct what the model was asked and what it returned. Checklist:
confirm AI-generated outputs are labelled, logs exist with retention, and a human reviews high-risk
decisions before they take effect.

## Phased application
Obligations phase in over time rather than all at once. For example, the EU AI Act applies prohibitions
after about 6 months, general-purpose AI rules after about 12 months, and most high-risk obligations
after about 24 months. Check the jurisdiction pack's `as_of` date against the phase calendar to know which
obligations are live. Checklist: compute which obligations are in force at launch and schedule the rest on
the compliance calendar.

## General-purpose AI model obligations
Foundational and general-purpose models have their own duties: document training data, follow copyright
policy where applicable, and provide the required transparency when used downstream. These obligations
apply at the model layer even if the product is a wrapper. Checklist: confirm training-data documentation
exists and copyright handling is defined before relying on a general-purpose model.
