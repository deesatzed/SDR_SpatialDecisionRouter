# Layer 1 v1.12.0 scoring (params 0.12.0-placeholder), 2026-10-23

All data is synthetic. Every threshold is a PLACEHOLDER. Jev picks are the stored picks (prompt v1.10); no new model calls were made for v1.12.0. Spend is in spend.json: $0.0012 total, against a $3 cap.

## Contamination caveat (read first)

- **holdout_v4 is now partly contaminated.** v1.12.0 targets Wayne's rulings on holdout_v4's review queue. Those rulings were expressed as abstract patterns, and no v3 or v4 case text was read while writing rules or tests.
- **One change was made after seeing v4 results.** After the first v4 score showed two new critical misses (case IDs and routes only, no text), the gap rule was changed from an owned nurse_task to a nurse *floor* that Jev may raise. That matches the brief's wording ("nurse floor"), but it is still a post-hoc change.
- **What this means.** Treat the v4 gains as an upper bound. A fresh holdout_v5 is needed for an unbiased estimate.
- **holdout_v3 regression check.** No v1.12.0 rule was derived from v3. holdout_v3 has no drex-max picks, so the v3 challenger and drex-max rows are not valid (they fall back to Layer 1 alone or d1-ultra only).

## holdout_v4, ruled key (76 cases)

### v1.11.2 baseline
| System | Accuracy (decided/n) | Critical misses | False pages /100 | HITM /100 | Errors |
|---|---|---|---|---|---|
| L1 + dual(d1-ultra, pplx) [default] | 75.0% (76/76) | 1 HX7-011 | 9.21 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 11.84 | 19 |
| L1 + dual(d1-ultra, drex-max) [challenger] | 75.0% (76/76) | 1 HX7-011 | 9.21 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 7.89 | 19 |
| L1 + d1-ultra | 76.3% (76/76) | 1 HX7-011 | 9.21 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 2.63 | 18 |
| L1 + pplx | 76.3% (76/76) | 1 HX7-011 | 7.89 (HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 2.63 | 18 |
| L1 + drex-max | 75.0% (76/76) | 1 HX7-011 | 7.89 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003) | 2.63 | 19 |
| Layer 1 alone | 74.3% (35/76) | 1 HX7-011 | 5.26 (HX4-004, HX6-001, HX6-003, HX7-003) | 56.58 | 9 |

### v1.12.0
| System | Accuracy (decided/n) | Critical misses | False pages /100 | HITM /100 | Errors |
|---|---|---|---|---|---|
| L1 + dual(d1-ultra, pplx) [default] | 88.2% (76/76) | 0  | 3.95 (HX2-003, HX2-004, HX7-005) | 7.89 | 9 |
| L1 + dual(d1-ultra, drex-max) [challenger] | 88.2% (76/76) | 0  | 3.95 (HX2-003, HX2-004, HX7-005) | 5.26 | 9 |
| L1 + d1-ultra | 88.2% (76/76) | 0  | 3.95 (HX2-003, HX2-004, HX7-005) | 2.63 | 9 |
| L1 + pplx | 89.5% (76/76) | 0  | 2.63 (HX2-004, HX7-005) | 2.63 | 8 |
| L1 + drex-max | 89.5% (76/76) | 0  | 2.63 (HX2-003, HX2-004) | 2.63 | 8 |
| Layer 1 alone | 91.1% (45/76) | 2 HX6-006 HX6-009 | 0.00 (-) | 43.42 | 4 |

Device tickets (Layer 1): 4/9 expected hit, 4 with any ticket; missed HX1-009, HX2-011, HX5-002, HX5-003, HX5-011; unexpected HX7-002.

Default-stack errors: HX2-001 nurse_task->silent_log (L1 None/no_trigger); HX2-003 provider_task->urgent_page (L1 None/no_trigger); HX2-004 provider_task->urgent_page (L1 None/no_trigger); HX2-007 nurse_task->silent_log (L1 None/no_trigger); HX5-001 silent_log->nurse_task (L1 SUPPRESSED/below_band_threshold); HX6-005 nurse_task->provider_task (L1 SUPPRESSED/explained); HX6-008 nurse_task->provider_task (L1 SUPPRESSED/unwitnessed_probable_fall_age85); HX7-005 nurse_task->urgent_page (L1 None/no_trigger); HX8-005 nurse_task->provider_task (L1 None/no_trigger)

## holdout_v3 regression check, ruled key (80 cases)

### v1.11.2 baseline
| System | Accuracy (decided/n) | Critical misses | False pages /100 | HITM /100 | Errors |
|---|---|---|---|---|---|
| L1 + dual(d1-ultra, pplx) [default] | 98.8% (80/80) | 0  | 0.00 (-) | 11.25 | 1 |
| L1 + dual(d1-ultra, drex-max) [challenger] | 97.5% (80/80) | 0  | 0.00 (-) | 52.50 | 2 |
| L1 + d1-ultra | 97.5% (80/80) | 0  | 0.00 (-) | 3.75 | 2 |
| L1 + pplx | 96.2% (80/80) | 1 HW2-003 | 0.00 (-) | 3.75 | 3 |
| L1 + drex-max | 100.0% (41/80) | 0  | 0.00 (-) | 3.75 | 0 |
| Layer 1 alone | 100.0% (41/80) | 0  | 0.00 (-) | 52.50 | 0 |

### v1.12.0
| System | Accuracy (decided/n) | Critical misses | False pages /100 | HITM /100 | Errors |
|---|---|---|---|---|---|
| L1 + dual(d1-ultra, pplx) [default] | 98.8% (80/80) | 1 HW6-004 | 0.00 (-) | 11.25 | 1 |
| L1 + dual(d1-ultra, drex-max) [challenger] | 97.5% (80/80) | 1 HW6-004 | 0.00 (-) | 45.00 | 2 |
| L1 + d1-ultra | 97.5% (80/80) | 1 HW6-004 | 0.00 (-) | 3.75 | 2 |
| L1 + pplx | 96.2% (80/80) | 2 HW6-004 HW2-003 | 0.00 (-) | 3.75 | 3 |
| L1 + drex-max | 97.9% (47/80) | 1 HW6-004 | 0.00 (-) | 3.75 | 1 |
| Layer 1 alone | 97.9% (47/80) | 1 HW6-004 | 0.00 (-) | 45.00 | 1 |

Device tickets (Layer 1): 4/4 expected hit, 4 with any ticket; missed -; unexpected HW5-009, HW6-010, HW7-001, HW7-006.

Default-stack errors: HW6-004 urgent_page->provider_task (L1 CONFIRM_FIRST/learning_spo2_85_88_no_recheck)

## Notes

- **v4 default stack.** Accuracy goes from 75.0% to 88.2%, and critical misses from 1 (HX7-011) to 0. False pages per 100 go from 9.21 to 3.95, and HITM per 100 from 11.84 to 7.89. Device tickets go from 0/9 to 4/9.
- **v4 Layer 1 alone.** It now decides 45 of 76 cases (was 35), with 2 critical misses (HX6-006 and HX6-009). These are gap-floor cases where Layer 1 alone stops at the nurse floor, and the stacks escalate them correctly.
- **v3 default stack.** Accuracy is unchanged at 98.8%, but there is **1 new critical miss, HW6-004**. The learning-period 85–87% rule turns a CONFIRM_FIRST page into provider_task.
  - Original-library case ST3-001 shows the same conflict.
  - This needs Wayne's ruling. Setting v1120.learning_spo2_low to 88 disables the rule.
- **v3 device tickets.** There are 4 unexpected tickets on v3 (HW5-009, HW6-010, HW7-001, HW7-006). These are non-interruptive.
- **Tests.** 284 pass: 269 existing plus 15 in test_layer1_v1120.py.
- **library_expansion_v1.** 30 Layer 1 routes changed, all 30 toward the label, 0 broken. Original library: 1 changed (ST3-001, see above).
