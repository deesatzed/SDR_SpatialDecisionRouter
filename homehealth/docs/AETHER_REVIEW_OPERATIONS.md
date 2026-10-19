# Aether Synthetic Review Operations

## Allowed operation

The review package accepts only explicitly synthetic cases and local clinician-ruling evidence. It returns one of `agree_with_engine`, `needs_clinician_review`, `needs_required_case_input`, or `system_review_unavailable`.

## Prohibited operation

It must not receive patient data, use a model or network by default, modify `trigger_params.json`, write clinician rulings, relabel library cases, or execute an escalation. The trigger engine and clinical owner retain those authorities.

## Future live-evaluation gate

Before any live model request, record clinical-owner authorization, an allowed synthetic outbound field list, maximum request count, maximum spend, and stop conditions. Connection checks and synthetic test doubles do not establish clinical validity.
