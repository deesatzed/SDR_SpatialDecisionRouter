# v1.11.2 re-score (SYNTHETIC DATA ONLY) — 2026-10-23

Params `0.11.2-placeholder`; all new thresholds are PLACEHOLDERS (not clinically validated). Approved by Wayne.

## Changes
1. **Device-disagreement ownership** — with no acute signs, Layer 1 owns `HT_DEVICE_DISAGREE` routes (`layer1_device_ticket`), so Jev no longer overrides them.
2. **Explained fall-on-anticoagulant floor** — `HT_FALL_ANTICOAG:explained` now has a `nurse_task` floor.
3. **Stable-angina nurse_task owner — KEPT.** The gates are all PLACEHOLDERS:
   - chest pain band D
   - an angina/CAD history
   - exertional onset, eased by rest or GTN
   - explicit "same as usual / unchanged" wording
   - no red flags, no onset at rest, no new, longer or more frequent episodes, no sweating or nausea
   - episodes under 10 min

   It was built from 5 practice vignettes (`jev_baseline/test_layer1_v1112_angina.py`): 1 stable positive and 4 crescendo/red-flag negatives (more frequent, at rest, sweating/nausea, longer). The negatives stay at provider_task or above.

   It caused no change and no new critical misses on the library, holdout_v1 or holdout_v2. **It does not fire on HW4-008** (that case's wording does not meet the gates). We did not tune it to the holdout text, so HW4-008 is still an error.
4. **Jev prompt v1.10 — KEPT, now the default.** v1.10 is v1.9 plus a computed 7-day trend summary line (`jev_baseline/trend_summary.py`). The line gives the direction and size of change for HR, RR, weight, steps and SpO2, using PLACEHOLDER flat thresholds. Jev was re-run on holdout_v3 only (80 cases, base variant, 2 models). Spend: $0.0102 in total, from 2 runs of $0.0051. Run 1 was discarded because of a steps-parser bug. Both runs are recorded in `spend.json`, and the run stays under the $0.05 cap.

## Before / after
| Set | System | v1.11.1 | v1.11.2 |
|---|---|---|---|
| holdout_v1 all91 | default | 91.21%, crit 0, fp 1.10, HITM 17.58 | unchanged |
| holdout_v1 all91 | L1 alone (34) | 94.12%, crit 0, fp 1.10, HITM 62.64 | unchanged |
| holdout_v2 accepted65 | default | 96.92%, crit 0, fp 3.08, HITM 9.23 | unchanged |
| holdout_v2 accepted65 | L1 alone (30) | 100%, crit 0, fp 0, HITM 58.46 | unchanged |
| holdout_v3 ruled80 | default (Jev v1.9 picks) | 92.5%, crit 0, fp 1.25, HITM 13.75 | 96.25%, crit 0, fp 1.25, HITM 11.25 |
| holdout_v3 ruled80 | default (Jev v1.10 picks) | — | **98.75%, crit 0, fp 0, HITM 11.25** |
| holdout_v3 ruled80 | L1 alone (41) | 100%, crit 0, fp 0, HITM 52.5 | unchanged |
| library270 | default (stored v1.9 picks) | 93.70%, crit 0, fp 2.96, HITM 18.89 | unchanged |
| library270 | L1 alone (84) | 98.81%, crit 1 (ST1-004), fp 0, HITM 70.0 | unchanged |

With the v1.10 picks, the remaining holdout_v3 default-stack error is HW4-008 (expected nurse_task, got provider_task; an over-escalation). HW8-010 (drift) is fixed by the trend summary. HW6-011 is no longer a false page with the v1.10 picks, but this may be model variance from a single run. The library was not re-run under v1.10 (its picks are v1.9).

## Caveats
- **holdout_v1, v2 and v3 are now partly tuning data.** Clinician rulings on these cases set the direction of the v1.10.x and v1.11.x fixes, and the v1.10 prompt was kept based on its holdout_v3 result. **A fresh holdout_v4 is needed** for an unbiased estimate.
- Files: `v1111.json`, `v1112_prompt_v19.json`, `v1112_prompt_v110.json`, from `score_v1112.py <jev_baseline> <label> [picks dir]`. The picks are in `jev_v110/`.
