# Layer 1 v1.13.0 device tickets (params 0.13.0-placeholder), SYNTHETIC data

Every threshold is a PLACEHOLDER. Stored Jev picks only, $0 model spend.

**Contamination rule:** the rules were built only from library cases (library_expansion_v1, 72 accepted, plus the original library) and hand-written synthetic vignettes (`jev_baseline/test_layer1_v1130.py`). holdout_v3/v4 case text was not read. The holdouts were scored only after the rules were written. v4 numbers are still an upper bound, because v1.12.0 was shaped by Wayne's v4 rulings. holdout_v5 is needed for an unbiased number.

## Rules (`jev_baseline/layer1_v1130.py`, `layer1_v110.v1130`)
These apply to a stable patient only: no symptoms, no acute words, and no ABSOLUTE or CONFIRM_FIRST trigger.
- **A. Activity artifact.** One step stream moves by at least `steps_change_ratio` from baseline, and one of these holds: a second activity device stays flat, a firmware/update/re-pair flag precedes the change, or the patient or caregiver says activity is unchanged. This rule is skipped if resting HR or weight moved too far from baseline.
- **B. Transient flagged reading.** One device's reading carries a motion, fit or contact flag. A second device reads normal at the same time, and the reading resolves after a strap or fit adjustment.
- **C. Firmware shift.** A firmware or update flag appears, and the rest of the physiology is flat. This applies to no-trigger cases only.
- **D/E. Maintenance report and scale blip.** These are OFF by default and have no library support. When D was on, it put an unexpected ticket on holdout_v3 HW3-002, with the route unchanged.
- **Routing.** A no-trigger case becomes a Layer-1-owned silent_log plus a device_maintenance ticket. Every other decision keeps its route and only gains the ticket.

## Results
| Set | Tickets hit, before | Tickets hit, after | False tickets, before | False tickets, after |
|---|---|---|---|---|
| Library (13 expected) | 10/13 | 13/13 | 0 | 0 |
| holdout_v4 ruled key (9 expected) | 4/9 | 4/9 | 1 (HX7-002) | 1 (HX7-002) |
| holdout_v3 ruled key (4 expected) | 4/4 | 4/4 | 4 | 4 |

Routes did not change on either holdout.
- **holdout_v4 default stack:** 86.8%, 0 critical misses, 5.26 false pages per 100, 7.89 HITM per 100.
- **holdout_v3 default stack:** 100%, 0 critical misses, 0 false pages per 100, 11.25 HITM per 100.

The v4 misses HX1-009, HX2-011, HX5-002, HX5-003 and HX5-011 are still misses, and HX7-002 is still a false ticket. Library route errors stayed at 2, the same as before.

Files: `v4_before.json`, `v4_after.json`, `v3_before.json`, `v3_after.json`. They come from `score_ruled.py`, with `V1130_OFF=1` for the before runs.
