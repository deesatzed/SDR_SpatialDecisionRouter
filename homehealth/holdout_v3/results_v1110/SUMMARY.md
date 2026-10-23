# holdout_v3 re-score: Layer 1 v1.10.3 vs v1.11.0 (SYNTHETIC, clinician-ruled key)

Key: `holdout_v3_ruled_key.json`, 80 cases (63 accepted + 17 ruled merge disputes; 37 clinician rulings). Jev picks: stored (`jev/parsed`) + new run on the 17 disputes (`jev_disputes/`, $0.0037, 136 calls). Script: `score_v1110.py`; raw output `v1103.json`, `v1110.json`.

| System | Version | Accuracy | Critical misses | False pages /100 | HITM /100 |
|---|---|---|---|---|---|
| Layer 1 alone (decided) | v1.10.3 | 75.0% (27/36) | 2 (HW3-008, HW4-003) | 5.00 | 58.75 |
| Layer 1 alone (decided) | v1.11.0 | 95.0% (38/40) | 0 | 1.25 | 53.75 |
| L1 + dual cautious_max_hitm (default) | v1.10.3 | 83.75% (67/80) | 2 (HW3-008, HW4-003) | 6.25 | 16.25 |
| L1 + dual cautious_max_hitm (default) | v1.11.0 | 90.0% (72/80) | 0 | 2.50 | 16.25 |

| Coverage | v1.10.3 | v1.11.0 |
|---|---|---|
| Device tickets (expected 4) | 0/4 | 4/4 (HW7-007, HW2-008, HW2-009, HW8-011) |
| Plain reasons on Layer 1 decisions | 0/36 | 40/40 |

Remaining v1.11.0 errors. Layer 1: HW4-002 (85% inside the 85-87% band -> silent, label nurse; conflicts with the band principle, needs a ruling), HW2-006 (gap explained by a video call, still pages). Default stack adds Jev-side errors: HW4-008, HW2-008, HW8-010, HW8-011 (Jev route; ticket filed correctly), HW8-003, HW6-011 (conditional ruling; serotonergic rule shipped disabled).

Other regression checks: library 270 unchanged; holdout_v1 HO1-005 false page fixed, HO2-007 now provider vs nurse label; holdout_v2 HV10-011 fixed, HV3-004/HV3-005 now provider vs nurse labels (dose-review direction; need re-ruling).

**CAVEAT: holdout_v3 is now partly tuning data.** The rule fixes were written from library practice cases, but the clinician rulings on these very cases set their direction, so these numbers overstate generalisation. A fresh, frozen **holdout_v4** is required for an unbiased estimate. All new thresholds are placeholders.
