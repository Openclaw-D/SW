# Indicator-source registry

This registry records primary-source directions for the deterministic V1 business-rule reference dataset. It is not evidence that a source was fetched at runtime, that a customer complies with it, that a rule is legally determinative, or that signal-council has statistically validated a risk model.

The canonical source titles and authority names remain in Chinese where they are official Mainland China primary-source names. They are cited as source identifiers, not as untranslated public operating instructions. Before any real-data or decision use, recheck the current official text, effective date, scope, jurisdiction, customer authorisation, and source completeness.

## Permitted use

- Use legal, regulatory, accounting, registry, financial-institution, and manufacturer material to define transparent field dictionaries, consistency checks, evidence requests, and manual-review prompts.
- Keep source ID, title, institution, URL, access date, scope, rule version, denominator, period, and unit with each rule.
- Use actual project equipment documents and authorised source material before treating a manufacturer specification as project evidence.
- Separate equipment capability, observed operation, materials, quality, energy, inventory, and time/batch context.

## Prohibited inference

- Do not treat a public registry record, an empty report, a manufacturer marketing page, a rated maximum, or an industry source as proof of customer fact, ownership, capacity, revenue, cashflow, creditworthiness, or compliance.
- Do not convert an anomaly, missing source, policy match, or AML-style monitoring signal directly into fraud, default, rejection, or a hard gate.
- Do not use a single signal to calculate precise capacity, yield, or operating truth. Missing or conflicting source material lowers confidence or creates manual review.
- Do not silently change historic score, decision, confidence, hard-gate, or snapshot results when a source changes.

## Rule-maintenance gate

Before adding a threshold, document the sample basis, definition, version, industry/region, missing-value behaviour, and human-review gate. Without validated samples, use only transparent demonstration anchors or relative consistency checks. Public-source count or authority never removes the simulated-data disclosure: V1 responses remain `dataStatus=simulated` with `source=deterministic_business_rules` and a human-review disclaimer.
