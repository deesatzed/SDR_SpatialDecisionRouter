# Dual-model Jev behind Layer 1 (SYNTHETIC, stored v1.8 picks, no new paid calls)

- **Models:** d1-ultra (the lead) and pplx-decider-v1.2.
- **Layer 1:** mandatory; it decides ABSOLUTE, CONFIRM_FIRST and SUPPRESSED cases first.
- **Fly flag:** leak 0.5, threshold 0.841, tuned on train. It never changes a route.
- **Label pages/100:** 30.7.
- **Held-out split:** batches AC1, DM2, HK1, HK6, HK9, NV1, NV5, RN1, ST2 and ST3 (92 cases).
- **HITM column:** how many cases reach review, and how many of the stack's errors land in the review queue.
- **agree_else_hitm:** the route shown is the lead model's provisional route while the HITM resolves.

## All 270 cases

| Rule | Accuracy | Critical misses | Pages/100 | False pages/100 | Suppressed | Hospice | Pairs | HITM/100 (n) | Errors in HITM |
|---|---|---|---|---|---|---|---|---|---|
| L1 + d1-ultra only (previous) | 92.6% | 0 | 35.2 | 2.6 | 20/24 | 7/7 | 30/39 | 0 | 0/20 |
| L1 + pplx only | 93.7% | 0 | 29.6 | 1.5 | 21/24 | 7/7 | 32/39 | 0 | 0/17 |
| (a) agree else HITM | 92.6% | 0 | 35.2 | 2.6 | 20/24 | 7/7 | 30/39 | 18.9 (51) | 11/20 |
| (b) cautious max | 93.3% | 0 | 35.6 | 3.0 | 21/24 | 7/7 | 31/39 | 0 | 0/18 |
| **(c) cautious max + HITM** | **93.3%** | **0** | 35.6 | 3.0 | 21/24 | 7/7 | 31/39 | **18.9 (51)** | **9/18** |
| (a) + Fly | 92.6% | 0 | 35.2 | 2.6 | 20/24 | 7/7 | 30/39 | 26.3 (71) | 13/20 |
| (b) + Fly | 93.3% | 0 | 35.6 | 3.0 | 21/24 | 7/7 | 31/39 | 12.2 (33) | 7/18 |
| (c) + Fly | 93.3% | 0 | 35.6 | 3.0 | 21/24 | 7/7 | 31/39 | 26.3 (71) | 11/18 |

## Held-out (92 cases)

| Rule | Accuracy | Critical misses | Pages/100 | False pages/100 | Pairs | HITM/100 (n) | Errors in HITM |
|---|---|---|---|---|---|---|---|
| L1 + d1-ultra only | 89.1% | 0 | 40.2 | 3.3 | 15/19 | 0 | 0/10 |
| L1 + pplx only | 93.5% | 0 | 33.7 | 1.1 | 15/19 | 0 | 0/6 |
| (a) agree else HITM | 89.1% | 0 | 40.2 | 3.3 | 15/19 | 16.3 (15) | 6/10 |
| (b) cautious max | 92.4% | 0 | 40.2 | 3.3 | 16/19 | 0 | 0/7 |
| **(c) cautious max + HITM** | **92.4%** | **0** | 40.2 | 3.3 | 16/19 | **16.3 (15)** | **3/7** |
| (c) + Fly | 92.4% | 0 | 40.2 | 3.3 | 16/19 | 21.7 (20) | 3/7 |

## Without Layer 1 (fallback: raw picks, d1-ultra-led)

| Rule | Accuracy | Critical misses | Pages/100 | False pages/100 | Suppressed | Hospice | HITM/100 | Errors in HITM | Held-out accuracy / critical misses / HITM/100 |
|---|---|---|---|---|---|---|---|---|---|
| d1-ultra only | 88.1% | 1 (LIB-HK8-005) | 38.1 | 6.3 | 9/24 | 3/7 | 0 | 0/32 | 83.7% / 0 / 0 |
| agree else HITM | 88.1% | 1 (LIB-HK8-005) | 38.1 | 6.3 | 9/24 | 3/7 | 23.3 | 16/32 | 83.7% / 0 / 18.5 |
| cautious max | 90.0% | 0 | 38.9 | 6.7 | 12/24 | 3/7 | 0 | 0/27 | 88.0% / 0 / 0 |
| **cautious max + HITM** | 90.0% | **0** | 38.9 | 6.7 | 12/24 | 3/7 | 23.3 | 11/27 | 88.0% / 0 / 18.5 |

## What the HITM resolves (rule c, Layer 1 present)

There are 51 cases, all of them Jev-owned with no paging Layer 1 trigger. All are one- or two-level disagreements:

| Disagreement | Cases |
|---|---|
| nurse_task vs wake_specialist | 24 |
| wake_specialist vs escalate_human | 13 |
| silent_log vs nurse_task | 10 |
| nurse_task vs escalate_human | 4 |

On these 51 cases:
- d1-ultra was right on 40;
- pplx was right on 43;
- the cautious route (what the system already sends) was right on 42;
- the lower route was right on 41.

So the reviewer mainly confirms or steps down a cautious route, typically "is this a same-day nurse task or a specialist wake?"

## Recommendation

Make **(c) cautious max + HITM** the default, without Fly:
- It has 0 critical misses, both in-sample and held-out, and also 0 in the no-Layer-1 fallback.
- Its accuracy (93.3% / 92.4% held-out) is above d1-ultra alone.
- It never lowers either model's route.
- The HITM load is about 19 per 100 cases (16 per 100 held-out), and half the stack errors (9/18) arrive already in the queue.

Adding Fly raises the load to 26 per 100 and catches only 2 more errors, so keep it optional.

L1 + pplx alone scores slightly higher on this library (93.7%, 29.6 pages/100). The dual rule trades about 6 pages/100 for robustness to either model failing and for a disagreement signal. It is also the rule that keeps the no-Layer-1 fallback at 0 critical misses.

## Caveats

- The Layer 1 adapter was developed on this library, so the numbers with Layer 1 present are in-sample.
- The held-out batches are held out only from the Fly tuning; no other part of the dual rule was tuned.
- The data is synthetic only.
