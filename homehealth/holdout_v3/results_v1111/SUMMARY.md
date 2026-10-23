# Layer 1 v1.11.1 vs v1.11.0 (SYNTHETIC; params 0.11.1-placeholder)

Wayne's 2026-10-23 rulings:
- **HO2-007, HV3-004:** keep nurse_task. The low is a compression-explained CKD low.
- **HV3-005:** keep nurse_task. The low is exertion-explained.
- **HW4-002:** provider_task, for a home-oxygen evaluation. Added to review_queue.csv and rebuilt into the ruled key.
- **HW2-006:** nurse_task, SUPPRESSED (explained gap).
- **HW3-007:** provider_task (Day -2 low, 72 h lookback).

The fixes were built from new synthetic practice vignettes in `jev_baseline/test_layer1_v1111.py`. All new numbers are PLACEHOLDERS. Stored Jev picks only; no API calls ($0). Each version is scored against the same current keys.

| Holdout / system | Version | Accuracy | Critical misses | False pages/100 | HITM/100 |
|---|---|---|---|---|---|
| holdout_v1 all91, default dual | v1.11.0 | 90.11% | 0 | 1.10 | 18.68 |
| holdout_v1 all91, default dual | v1.11.1 | 91.21% | 0 | 1.10 | 17.58 |
| holdout_v1 all91, Layer 1 alone | v1.11.0 | 91.18% (34 decided) | 0 | 1.10 | 62.64 |
| holdout_v1 all91, Layer 1 alone | v1.11.1 | 94.12% (34) | 0 | 1.10 | 62.64 |
| holdout_v2 accepted65, default dual | v1.11.0 | 93.85% | 0 | 3.08 | 9.23 |
| holdout_v2 accepted65, default dual | v1.11.1 | 96.92% | 0 | 3.08 | 9.23 |
| holdout_v2 accepted65, Layer 1 alone | v1.11.0 | 93.33% (30) | 0 | 0.00 | 58.46 |
| holdout_v2 accepted65, Layer 1 alone | v1.11.1 | 100% (30) | 0 | 0.00 | 58.46 |
| holdout_v2 all81, Layer 1 alone | v1.11.0 | 95.12% (41) | 0 | 0.00 | 53.09 |
| holdout_v2 all81, Layer 1 alone | v1.11.1 | 100% (41) | 0 | 0.00 | 53.09 |
| holdout_v3 ruled80, default dual | v1.11.0 | 90.0% | 0 | 2.50 | 16.25 |
| holdout_v3 ruled80, default dual | v1.11.1 | 92.5% | 0 | 1.25 | 13.75 |
| holdout_v3 ruled80, Layer 1 alone | v1.11.0 | 95.0% (40) | 0 | 1.25 | 53.75 |
| holdout_v3 ruled80, Layer 1 alone | v1.11.1 | 100% (41) | 0 | 0.00 | 52.50 |
| library 270, default dual | v1.11.0 | 93.70% | 0 | 2.96 | 19.63 |
| library 270, default dual | v1.11.1 | 93.70% | 0 | 2.96 | 18.89 |
| library 270, Layer 1 alone | v1.11.0 | 98.78% (82) | 1 (ST1-004) | 0.00 | 70.74 |
| library 270, Layer 1 alone | v1.11.1 | 98.81% (84) | 1 (ST1-004) | 0.00 | 70.00 |

holdout_v3 coverage is unchanged: device tickets 4/4, and plain reasons on 41/41 Layer 1 decisions.

**Remaining default-stack errors on holdout_v3** come from Jev-side routes: HW4-008, HW6-011 (conditional ruling), HW2-008, HW8-010, HW8-011 and HW8-003. Raw data is in `v1110.json` and `v1111.json`.

**Open question:** holdout_v1 HO3-004 has repeated nightly lows that a compression sleeve explains. It is ruled nurse_task. v1.11.1 therefore lets a repeat escalate to provider only for exertion-explained or unexplained lows. Repeated lows explained by compression stay nurse_task. Wayne should confirm this reading.

**CAVEAT:** holdout_v1, v2 and v3 are now all partly tuning data. A fresh, frozen **holdout_v4** is required for an unbiased estimate.
