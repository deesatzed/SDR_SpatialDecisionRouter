# SMART_TRIGGERS v1.10.2 (params 0.10.2-placeholder) — before/after, stored picks only, 0 model calls (SYNTHETIC)
Fixes built on hand-written practice cases (test_layer1_v1102.py, 16 tests); no holdout text in rules/tests.
CAVEAT: holdout_v2 rulings motivated these fixes, so holdout_v2 is now partly tuning data; its "after" numbers are optimistic. Need holdout_v3.

| Set | System | Acc before→after | Crit before→after | FP/100 before→after | HITM/100 before→after |
|---|---|---|---|---|---|
| library 270 | default | 93.7→93.7 | 0→0 | 2.96→2.96 | 19.63→19.63 |
| library 270 | Layer 1 alone (82 decided) | 98.8→98.8 | 1 (ST1-004)→1 | 0→0 | 70.74→70.74 |
| holdout_v1 ruled 91 | default | 90.1→90.1 | 0→0 | 2.20→2.20 | 19.78→18.68 |
| holdout_v1 ruled 91 | Layer 1 alone | 90.9 (33)→91.2 (34) | 0→0 | 2.20→2.20 | 69.23→68.13 |
| holdout_v2 ruled, 65 w/ picks | default | 92.3→96.9 | 1 (HV3-010)→0 | 3.08→3.08 | 9.23→9.23 |
| holdout_v2 ruled, 65 | Layer 1 alone | 92.6 (27)→96.7 (30) | 1→0 | 0→0 | 63.08→58.46 |
| holdout_v2 ruled, all 81 | Layer 1 alone | 94.6 (37)→97.5 (40) | 1→0 | 0→0 | 58.02→54.32 |

Changed Layer 1 decisions: library HK6-002 (unreliable_reading→possible_fall_unverified), CG1-004 & ST1-007 (fall ABSOLUTE→HT_FALL_PAIN ABSOLUTE, same route);
holdout_v1 HO8-024 (no trigger→ABSOLUTE fall, ruled urgent_page; route unchanged); holdout_v2 HV3-010 (→ABSOLUTE), HV5-002 (→HT_FALL_PAIN),
HV5-003 & HV7-005 (→possible_fall_unverified, nurse_task). No new errors/false pages anywhere. HV1-009, HV10-002 not newly paged (still the 2 model false pages).
Fix 5 (HT_SPO2_REST_DYSPNEA) fired on no stored case, incl. HV1-007 (models already page it); left as candidate.
