# Per-patient rule overrides — design (NOT implemented)

Status: draft for Wayne, 2026-10-22. **Revised 2026-10-23:** ABSOLUTE rules are now setting-level FOUNDATION rules
(see `RULE_GOVERNANCE_DESIGN.md`). Patient overrides apply to **non-foundation rules only**; that doc's evaluation order
(setting profile -> patient overrides -> safety floors) replaces the precedence section below. SYNTHETIC examples only. All numbers below are **placeholders** unless they quote an existing rule.

## Why
The holdout_v2 review showed the same finding needs different routes for different patients (hospice HV10-002 / HV2-002 / HV6-001 vs.
full-care patients). Today Layer 1 handles this with one global `goals_of_care` suppression. Wayne's direction: each patient can have
rules agreed **in advance** by the responsible provider **with the patient/family**, covering acceptable and unacceptable variance for
their condition (hospice: ADLs, pain, mental status, goals; but any condition).

## Schema (one record per override; a patient has a plan = list of overrides)
```yaml
override_id: OVR-<patient_id>-<seq>
patient_id: <pseudonymous id>                 # never name/MRN in this store
rule_id: HT_BRADY_RATE_DRUG                   # SMART_TRIGGERS rule being changed, or "*" for plan-wide (e.g. no transfer)
override_type: threshold_change | variance_range | route_change | suppression
params:                                       # by type
  threshold_change: {field: rest_hr, op: "<", value: <placeholder>}
  variance_range:   {field: spo2, low: <placeholder>, high: <placeholder>, confirm: two_readings}   # inside range = acceptable
  route_change:     {from: urgent_page, to: nurse_task, recipient: hospice_nurse}
  suppression:      {reason: goals_of_care, min_route: nurse_task}                               # never below min_route
condition_context:
  program: hospice | palliative | full_care | post_discharge
  goals_of_care: "comfort only, no hospital transfer; calls OK"
  polst: {present: true, transfer: no}
  adl_baseline: "bed-chair transfers with aide"     # free text + optional coded level
  pain_baseline: "<placeholder> / 10 at rest"
  mental_status_baseline: "oriented to person; drowsy on morphine"
  still_escalate_if: ["new uncontrolled pain", "distress", "family requests"]   # explicit carve-backs
agreed_by:
  provider: {id, role, attestation: true}      # required
  patient_or_family: {who: "patient | health-care proxy | family member", method: visit | phone | portal}
agreed_on: YYYY-MM-DD
review_by: YYYY-MM-DD                          # required; expired override is ignored and raises a nurse_task to renew
hard_safety_attestation: false                 # must be true (plus provider attestation text) to touch an ABSOLUTE rule
rationale: "short clinical reason"
version: 3                                     # edits create a new version; old versions kept
```
Validation: unknown `rule_id` rejected; `review_by` required and ≤ <placeholder> days out; `suppression` must carry `min_route`
(default `nurse_task`); `silent_log` as a target for an ABSOLUTE rule is never allowed.

## Precedence in Layer 1
1. Evaluate the standard SMART_TRIGGERS rules exactly as today → `{tier, rule, reason, default_route}` (unchanged, logged).
2. Load the patient's **active** overrides (`agreed_on ≤ today ≤ review_by`). Expired → ignore + add `nurse_task` "renew plan".
3. Apply overrides matching the fired `rule_id` (or `*`), most specific first (rule-specific beats plan-wide; later version wins).
4. Guards:
   - ABSOLUTE rules can be re-routed only if `hard_safety_attestation: true`; even then the minimum is `nurse_task` and the hard
     HITM flag stays on. Existing hard floors stay (insulin/sulfonylurea + CKD danger lows: hard HITM, ≥ nurse_task).
   - CONFIRM_FIRST / non-hard rules can be changed by any active, provider-attested override.
   - `variance_range` can only *widen what counts as expected*; it never lowers a reading that is outside the range.
   - `still_escalate_if` carve-backs beat the override (e.g. new pain or distress in hospice → standard route).
5. Output adds `override_applied: [override_id@version]` and `route_before_override`. The dual-model `cautious_max_hitm` rule then runs
   with the override-adjusted Layer 1 result as the floor/ceiling.

## Audit logging
Append-only record per evaluation: case/event id, patient_id, standard result, overrides considered/applied/ignored (with reason:
expired, guard blocked, carve-back), final route, HITM flag, SMART_TRIGGERS version, override version. Separate log for plan edits
(who, when, diff, attestation). No PHI to cloud: logs keep pseudonymous ids; the override text sent to models is redacted locally first.

## The ruled cases as overrides
| Case | Standard result | Override | Resulting route |
|---|---|---|---|
| HV10-002 hospice, digoxin, symptomatic HR ~41 | (no L1 trigger today) | `route_change` on bradycardia/hypotension → `nurse_task` to hospice nurse; carve-back: unresponsive or distress → urgent | nurse_task (Wayne's ruling) |
| HV2-002 hospice, apixaban, stroke signs | ABSOLUTE stroke | `suppression` reason goals_of_care, min_route nurse_task, `hard_safety_attestation: true`; trigger still logged | nurse_task, SUPPRESSED |
| HV6-001 hospice COPD, confirmed SpO2 86% | SpO2 trigger | `variance_range` documented low baseline (values are placeholders, set by provider) + `suppression` goals_of_care, min_route nurse_task | nurse_task, SUPPRESSED |
| HV6-002 hospice, hypoglycaemia (spouse treated) | ABSOLUTE danger low | No override applies to the page: danger low is a hard floor; plan says *recipient* = hospice nurse, no transfer | urgent_page (hospice nurse) |
| HO8-025 hospice, insulin, danger low | ABSOLUTE | Same as HV6-002: hard floor kept; override only sets recipient and "no transfer" | urgent_page (hospice nurse) |

HV6-002 / HO8-025 show the intended limit: goals of care change *who* is called and *what* happens, not whether a treatable
dangerous low is acted on promptly.

## How the models see it
Jev prompt gets a structured `care_plan` block (after the case, before the route question), e.g.
`care_plan: {program: hospice, goals: "comfort only, no transfer; calls OK", overrides: [{rule: HT_BRADY_RATE_DRUG, type: route_change, to: nurse_task, still_escalate_if: [...]}], layer1: {standard: ..., after_override: ...}}`.
Models may route *up* from the override result freely; routing *down* below `min_route` is clamped by Layer 1. Fly sees the same block
and flags if the event looks like a carve-back. Prompt change = new prompt version; re-run baselines before use.

## Test plan (practice cases only, never holdout text)
1. Unit tests in `jev_baseline/test_overrides.py`: each override type; expiry; version precedence; ABSOLUTE without attestation is
   blocked; min_route clamp; carve-back wins; invalid rule_id rejected.
2. Paired practice cases: same event, with and without a plan (hospice vs full-care) → expect different routes only where intended.
3. Regression: library_v2 + holdout_v1/v2 ruled keys with no plans attached must score identically to v1.10.x.
4. Model check: re-run d1-ultra + pplx on the paired practice cases with the `care_plan` block (spend cap set by Wayne).
5. New holdout_v3 slice with plans, generated after the design is frozen.

## Open questions for Wayne
1. Who may author/attest: attending only, or also hospice medical director / NP? Does a nurse ever enter on a provider's verbal order?
2. Default and maximum `review_by` interval (hospice vs other programs)?
3. Should any ABSOLUTE rule be fully suppressible with attestation, or is `nurse_task` always the floor (as drafted)?
4. Is a coded ADL / pain / mental-status scale wanted, or free text plus carve-backs?
5. What happens when the family's wishes and the patient's differ, or the proxy changes?
6. Should the plan be visible to the family in the app, and can they request a review?
7. HV10-002: is "drowsy + grey + HR ~41 on digoxin" inside the plan, or should digoxin toxicity be a carve-back?

## v1.11.0 partial implementation: patient-level SpO2 bands (2026-10-23)

- Layer 1 now honours a **patient-level SpO2 band** when it is structured (`patient_bands`) or documented by a clinician (e.g. "COPD, target 85-87%"). A pmh-only mention ("COPD, baseline high 80s") is NOT a band; it keeps the v1.10 `at_patient_baseline` nurse check.
- A reading **within** the band -> `within_patient_band`, SUPPRESSED, silent_log. Below the band's lower bound: normal SpO2 logic using the band floor instead of the population 88%.
- **Hard floor that a band cannot override:** COPD confirmed below 85% (`copd_urgent_below`, placeholder) -> `below_patient_band_copd_lt85`, never suppressed.
- The drug-low foundation rule (RULE_GOVERNANCE_DESIGN section 10) cannot be overridden by any patient plan, including hospice; hospice changes the receiver, not the page.
- Conditional clinician rulings are recorded as overrides with a condition string and stay advisory (not enforced) until the condition is expressible as a tested rule.
- Known conflict: holdout_v3 HW4-002 (accepted label nurse_task, 85% inside a documented 85-87% band) now routes silent under the band principle; needs a ruling on whether a reading at the band floor should still get a nurse check.
