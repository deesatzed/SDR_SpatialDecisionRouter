# Aether Synthetic Clinician-Review Design

## Scope

Aether reviews explicitly synthetic home-health cases only. It takes the deterministic trigger-engine result, retrieves bounded current clinician-ruling evidence, and emits an auditable review packet. It never changes parameters, rulings, cases, or escalation targets.

## Authorities

The trigger engine remains the source of the initial tier and rule path. The clinical owner remains the only authority for a ruling or parameter change. `trigger_params.json` is placeholder configuration and read-only here.

## Outcomes

| Outcome | Meaning | Next step |
| --- | --- | --- |
| `agree_with_engine` | Current evidence supports the engine result. | Complete review record. |
| `needs_clinician_review` | Available evidence shows a substantive ambiguity or conflict. | Send packet to clinician review. |
| `needs_required_case_input` | A named policy-required input is missing from the case. | Name the required recheck, symptom, reliability, fingerstick, response, or goals input. |
| `system_review_unavailable` | Retrieval, provenance, schema, or typed-decision validation failed. | Do not claim agreement; repair the review record. |

`needs_required_case_input` is a case-level uncertainty. `system_review_unavailable` is a system-level failure and is never a clinical conclusion.

## Data and evaluation

Only a synthetic marker, case ID, engine tier/reasons/rule version, accepted synthetic cases, and clinician rulings are accepted. Persistent packets store bounded evidence IDs/excerpts, never full patient material. Development, held-out, and challenge cases are frozen before tuning. The mandatory initial gate is zero unsafe `agree_with_engine` outcomes on the challenge set.

This establishes synthetic review behavior only. It does not validate thresholds, patient outcomes, or real-world clinical use. Live calls require separately approved outbound fields, request limits, spend limits, and clinical authority.
