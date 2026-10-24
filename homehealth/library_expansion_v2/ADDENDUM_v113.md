
---
## SMART_TRIGGERS v1.13 device-ticket addendum (2026-10-24; overrides anything above that conflicts; all numbers are PLACEHOLDERS)
"expected_device_ticket" (device_maintenance | supply_reference_oximeter_and_baseline | ecg_strip_request | null) is SEPARATE from the route. Rules:
1. A device problem with a stable patient (no symptoms, no acute sign, physiology otherwise flat): route silent_log, ticket filled. Examples: sync failures / upload gaps with the patient seen well, battery or charging gaps, strap/fit problems, sensor placement, single impossible or odd scale reading (0 kg, another household member, one outlier that returns), BP cuff error code or wrong cuff size with a clean repeat, CGM warm-up or expiry readings, firmware change shifting a stream, duplicated or time-shifted data.
2. A ticket can sit ON TOP of a clinical route: if the device problem coexists with a real clinical issue, route by the clinical issue (nurse_task, provider_task or urgent_page) AND fill the ticket.
3. Negative controls: a change that LOOKS like a device problem but is confirmed real (second device agrees, symptoms, carer confirms the change, recheck confirms) gets NO ticket and is routed clinically. Do not ticket real change.
4. A device problem already fixed and verified (charged, replaced, re-synced with clean data) -> no ticket.
5. A data gap in a high-risk patient that cannot be explained as a device fault (patient not seen) is NOT a device-ticket-only case; follow the gap rules.
Every decisive device fact (the error message, battery warning, the second device's value, the carer's words) must be visible in router_input text (trend_last_7d, caregiver_or_nurse_note, data_quality), never only in answer fields.
