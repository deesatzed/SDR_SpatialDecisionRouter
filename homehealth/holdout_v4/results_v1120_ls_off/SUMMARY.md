# Layer 1 v1.12.0 with the learning-period SpO2 rule dropped, 2026-10-24

Wayne ruled: drop `v1120.learning_spo2_low` (learning-period SpO2 85–87%, no recheck → provider_task). Those cases page urgent again. Disabled by setting the param to 88 (empty range). All data synthetic; thresholds PLACEHOLDER. Stored Jev picks reused; $0 spend. Same contamination caveat as results_v1120/SUMMARY.md: v4 numbers are an upper bound.

## holdout_v4, ruled key (76 cases)
| System | v1.11.2 acc / crit / FP per 100 / HITM per 100 | now acc / crit / FP per 100 / HITM per 100 |
|---|---|---|
| Default L1 + dual(d1-ultra, pplx) | 75.0% / 1 (HX7-011) / 9.21 / 11.84 | 86.8% / 0 / 5.26 / 7.89 |
| Challenger L1 + dual(d1-ultra, drex-max) | 75.0% / 1 / 9.21 / 7.89 | 86.8% / 0 / 5.26 / 5.26 |
| Layer 1 alone | 74.3% (35/76) / 1 / 5.26 / 56.58 | 88.9% (45/76) / 2 (HX6-006, HX6-009) / 1.32 / 43.42 |

HX7-003: Wayne's label stays provider_task. Layer 1 now pages urgent, so it scores as an over-route (false page) in every stack. That accounts for the drop from 88.2% to 86.8% versus v1.12.0 with the rule on.

## holdout_v3 regression, ruled key (80 cases)
Default 100.0% (80/80), 0 critical misses (HW6-004 now urgent_page, correct). Challenger 98.75%, 0 crit (v3 has no drex-max picks; row not valid). Layer 1 alone 100% (47/80), 0 crit.
