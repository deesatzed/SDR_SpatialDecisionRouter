# Jev model head-to-head: perplexity/pplx-decider-v1.2 vs liquid/d1-ultra (SYNTHETIC, v1.8 prompt)

- **Cases:** 270 × 4 variants (base, reversed option order, key line deleted, all monitoring data missing), scored on the base variant.
- **Same pipeline for both models:** `jev_run.py`, then `score_jev.py`, then the Layer 1 router (`layer1_adapter.route`), then Fly flag-only (`fly_layer/score_fly.py`, reusing the stored Fly readouts).
- **Fly threshold:** tuned on the train split only.
- **Held-out split:** batches AC1, DM2, HK1, HK6, HK9, NV1, NV5, RN1, ST2 and ST3 (92 cases).
- **Label pages/100:** 30.7.
- **pplx run:** 1,080 calls, 0 without a pick, 0 retries, 0 HTTP 429s, spend $0.0183 (cap $0.05).
  - Model listed on OpenRouter: endpoint pplx-decider-v1.2-20261016, $0.02 per M prompt tokens, $0 completion.
- **d1-ultra run (stored):** 1,080 calls, $0.0345.

## Comparison: all 270 cases

| | d1-ultra alone | pplx alone | d1-ultra + L1 | pplx + L1 | d1-ultra + L1 + Fly flag | pplx + L1 + Fly flag |
|---|---|---|---|---|---|---|
| Accuracy | 88.1% | 88.1% | 92.6% | **93.7%** | 92.6% | 93.7% |
| Critical misses | 1 (LIB-HK8-005) | **8** (see below) | 0 | 0 | 0 | 0 |
| Pages/100 (label 30.7) | 38.1 | 29.6 | 35.2 | **29.6** | 35.2 | 29.6 |
| False pages/100 | 6.3 | 4.4 | 2.6 | **1.5** | 2.6 | 1.5 |
| Suppressed correct | 9/24 | 14/24 | 20/24 | 21/24 | 20/24 | 21/24 |
| Hospice correct | 3/7 | 3/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| Pairs both correct (of 39) | 21 | 22 | 30 | 32 | 30 | 32 |
| HITM flags (on stack errors) | - | - | - | - | 32 (7) | 33 (5) |

- **pplx alone, critical misses:** LIB-HK5-002, LIB-HK8-004, LIB-NV3-005, LIB-GL1-005, LIB-ST1-001, LIB-ST1-005, LIB-ST3-001 and LIB-ST4-004.
  - Every one is a Layer 1 hard-trigger case: 7 CONFIRM_FIRST (SpO2 < 88, 48 h gap in a high-risk patient, chest pain with abnormal vitals) and 1 ABSOLUTE.
  - Layer 1 catches all 8.
- **Over-escalations with Layer 1:**
  - pplx: LIB-HK8-006, LIB-GC1-008, LIB-GC2-008 and LIB-RN1-005.
  - d1-ultra: LIB-AC1-009, LIB-GC1-008, LIB-GC2-004, LIB-GC2-007, LIB-GC2-008, LIB-RN1-002 and LIB-RN1-005.

## Held-out (92 cases)

| | d1-ultra alone | pplx alone | d1-ultra + L1 | pplx + L1 | + Fly flag (d1 / pplx) |
|---|---|---|---|---|---|
| Accuracy | 83.7% | 89.1% | 89.1% | **93.5%** | 89.1% / 93.5% |
| Critical misses | 0 | 1 (LIB-ST3-001) | 0 | 0 | 0 / 0 |
| Pages/100 | 44.6 | 35.9 | 40.2 | 33.7 | same |
| False pages/100 | 7.6 | 4.3 | 3.3 | 1.1 | same |
| Pairs both correct (of 19) | 10 | 11 | 15 | 15 | same |
| HITM flags (on stack errors) | - | - | - | - | 10 (2) / 8 (0) |

## Robustness variants and calibration (model alone)

| | d1-ultra | pplx |
|---|---|---|
| Reversed order, same pick | 90.0% | 94.8% |
| Key line deleted, pick changed | 28.1% | 29.6% |
| Key line deleted, escalate or veto | 42.6% | 27.8% |
| All data missing, escalate | **73.3%** | 52.6% |
| All data missing, escalate or veto | **89.6%** | 67.0% |
| Brier (escalate) | 0.0936 | 0.0893 |
| Brier (multiclass) | 0.4094 | 0.3691 |

## Recommendation

The default stays `liquid/d1-ultra`; it was not changed.

pplx-decider-v1.2 behind Layer 1 is the better stack on every scored metric, both in-sample and held-out:
- higher accuracy
- false pages down from 2.6 to 1.5 per 100
- a page rate that matches the label rate
- better calibration
- about half the cost

pplx alone is the less safe model:
- 8 critical misses, all hard-trigger cases
- it escalates or vetoes on only 67% of all-data-missing variants, against 90% for d1-ultra

So pplx is acceptable only with Layer 1 always in front. It is a candidate for Wayne to approve as the stack model, not as a standalone model.

## Caveats

- The Layer 1 adapter was developed on this library, so the stack numbers are in-sample. The held-out batches are held out only from the Fly threshold tuning.
- The data is synthetic only.
