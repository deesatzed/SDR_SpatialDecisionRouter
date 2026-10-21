# holdout_v1: fresh out-of-sample set scored on the frozen stack (SYNTHETIC)

**Frozen code:** main @ **81820c9**. The box copies of `jev_baseline/`, `fly_layer/` and `trigger_engine/` are md5-identical to the Mac repo at that commit. Nothing was tuned on this set: Layer 1, the Jev v1.8 prompt, the Fly threshold (leak 0.5, t 0.841) and dual rule (c) are as committed.

## Cases

**Generation and grading:**
- **Prompts:** GEN_LLM2_v2.3 rev h (SMART_TRIGGERS v1.8). The Haiku hard-slice batches also used the hard-slice overrides.
- **Grader:** google/gemini-4-argon, GRADER_LLM3_v1.3 rev h.
- **Batches:** HO1–HO6 and HO9–HO10 from claude-haiku-5.5; HO7–HO8 from nemotron-3.5-super-vl.
- **Case IDs and source:** prefix `HO`, src_library `holdout_v1`. DO_NOT_REPEAT was the 270-case library.

**Counts:**
- **Generated and graded:** 135.
- **Accepted by grade_merge:** 60.
- **Removed as near-duplicates:** 0.
  - The check was decisive_feature Jaccard ≥ 0.5, or trend+note Jaccard ≥ 0.6, against the 270 library cases, any route.
  - The closest pair was HO8-004 vs NV3-012 at 0.44.
- **Final scored set:** 60.
- **Disputed:** 34, sent to `review_queue.csv` for Wayne (one case per row, background first) and excluded from scoring.
  - REJECT 22, ROUTE_DISAGREE 8, TIER_DISPUTE 4, NOVELTY_REVIEW 5, HARD_TRIGGER_DISPUTE 1. A case can carry several reasons.
- **Fix list:** 41, also excluded.

**Yield by batch (accepted/generated):**

| Batch | HO1 | HO2 | HO3 | HO4 | HO5 | HO6 | HO7 | HO8 | HO9 | HO10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Accepted | 10/11 | 6/11 | 7/10 | 3/10 | 11/11 | 3/10 | **0/25** | 6/25 | 7/11 | 7/11 |

Nemotron yields very little under the v2.3 prompt.

**Composition of the 60 scored cases:**
- **Routes:** escalate 20, nurse 15, silent 16, wake 9. Label rate is 33.3 pages/100, against 30.7 for the library.
- **Tiers:** ABSOLUTE 9, CONFIRM_FIRST 7, SUPPRESSED 4, ARTIFACT 2.
- **Other:** 3 hospice/goals-of-care cases, 1 learning-period case, 2 complete pairs, difficulty 45/60 hard or adversarial.

**Mix shortfalls against the brief:** too few pairs, learning-period, CGM and suppressed cases survived grading, so those rows rest on very small n.

**Grader drift control:** the control batch was graded at start, middle (CONTROL-end, after HO1–HO8) and end (CONTROL-end2, after the HO9–HO10 top-up).
- Routes matched on 7 of 7 cases at all three points.
- Actions matched on 7 of 7 at start and middle, and on 6 of 7 at the end (K-006 went reject → fix).
- Planted defects stayed flagged.

## Layer 1 alone, out-of-sample tier agreement

| | Holdout (60) | In-sample (270) |
|---|---|---|
| Tier match on hard-trigger cases | **16/22 (72.7%)** | 80/81 (98.8%) |
| Paging-tier match (ABSOLUTE/CONFIRM_FIRST vs not) | 18/22 | 81/81 |
| False paging triggers on non-trigger cases | 0/38 | 0 |

Layer 1 found no trigger in 6 of the 22 hard-trigger cases:
- **HO3-006** (ABSOLUTE, HT_VS_DANGER): HR 34–36 on two devices, on amiodarone plus bisoprolol. The adapter's HR danger threshold or its sentence parsing did not fire.
- **HO5-011** (ABSOLUTE, HT_SYNCOPE): witnessed loss of tone with HR 44 and SBP 84. There is no syncope pattern for this wording.
- **HO10-011** (ABSOLUTE, HT_CHEST_PAIN_VITALS): pleuritic chest pain with HR 132 and RR 31. The chest-pain rule did not match "pleuritic".
- **HO5-006** (CONFIRM_FIRST, HT_SPO2_LT88): 87% with an unanswered watch prompt while living alone. The failed-confirm wording was not parsed.
- **HO1-007** (ARTIFACT): ring RR 2/min under motion. No RR implausible-limit parse.
- **HO10-006** (ARTIFACT): a flat HR line under motion. Not detected.

This is the largest honest drop. The adapter's near-perfect in-sample agreement does not generalise: on new wording it misses about one in four triggers, including 3 ABSOLUTE.

## Full stack: holdout vs in-sample

Format is holdout (60) / in-sample (270). Label pages/100 are 33.3 / 30.7.

| System | Accuracy | Critical misses | Pages/100 | False pages/100 | Suppressed | Hospice | Pairs | HITM/100 | Errors in HITM queue |
|---|---|---|---|---|---|---|---|---|---|
| d1-ultra alone | 86.7% / 88.1% | 0 / 1 | 33.3 / 38.1 | 3.3 / 6.3 | 0/4 / 9/24 | 1/3 / 3/7 | 2/2 / 21/39 | – | – |
| pplx alone | 81.7% / 88.1% | **3** / 8 | 25.0 / 29.6 | 1.7 / 4.4 | 1/4 / 14/24 | 2/3 / 3/7 | 2/2 / 22/39 | – | – |
| L1 + d1-ultra | 90.0% / 92.6% | 0 / 0 | 30.0 / 35.2 | 0.0 / 2.6 | 2/4 / 20/24 | 3/3 / 7/7 | 2/2 / 30/39 | – | – |
| L1 + pplx | 86.7% / 93.7% | **1** / 0 | 26.7 / 29.6 | 0.0 / 1.5 | 2/4 / 21/24 | 3/3 / 7/7 | 2/2 / 32/39 | – | – |
| **L1 + dual (c), default** | **91.7% / 93.3%** | **0 / 0** | 30.0 / 35.6 | 0.0 / 3.0 | 2/4 / 21/24 | 3/3 / 7/7 | 2/2 / 31/39 | 18.3 / 18.9 | **1/5** / 9/18 |
| L1 + dual (c) + Fly flag | 91.7% / 93.3% | 0 / 0 | 30.0 / 35.6 | 0.0 / 3.0 | 2/4 / 21/24 | 3/3 / 7/7 | 2/2 / 31/39 | 25.0 / 26.3 | 1/5 / 11/18 |
| No-L1 fallback: dual (c) | 88.3% / 90.0% | 0 / 0 | 33.3 / 38.9 | 3.3 / 6.7 | 0/4 / 12/24 | 1/3 / 3/7 | 2/2 / 25/39 | 23.3 / 23.3 | 2/7 / 11/27 |

**Critical misses:**
- **pplx alone, 3:**
  - HO1-003: chest pressure with SBP 97 (band B).
  - HO2-004: SpO2 86–87% on learning-period day 3.
  - HO5-006: unanswered prompt while living alone.
  - In all three, pplx chose wake_specialist.
- **L1 + pplx, 1:** HO5-006. Layer 1 missed the trigger and pplx under-called it.
- **Dual rule (c):** 0. d1-ultra escalated all three cases, and cautious-max takes the higher route. This is the dual rule working as intended.
- **Layer 1 misses that were still routed correctly:** HO3-006, HO5-011 and HO10-011 went to escalate through both models under the dual rule.

**Dual (c) errors (5) and the HITM queue:** only 1 of the 5 reached the queue. The other 4 are cases where both models agreed and were both wrong (all under-triage), which a disagreement queue cannot catch by design:
- HO1-006 and HO1-011: both models said silent_log; label nurse_task.
- HO8-009: both models said silent_log; label nurse_task or wake_specialist.
- HO5-007: both models said nurse_task; label wake_specialist or escalate_human.

## Jev robustness and calibration on the holdout

| | d1-ultra | pplx |
|---|---|---|
| Reversed option order, same pick | 95.0% | 96.7% |
| Key line deleted, escalate or veto | 41.7% | 28.3% |
| All data missing, escalate or veto | 78.3% (89.6% in-sample) | **50.0%** (67.0% in-sample) |
| Brier, escalate | 0.038 | 0.071 |
| Brier, multiclass | 0.333 | 0.363 |
| Calls / without a pick / retries | 240 / 0 / 0 | 240 / 0 / 0 |

## Drops, called out

1. **Layer 1 adapter:** tier agreement falls from 98.8% to 72.7%, with 3 ABSOLUTE and 1 CONFIRM_FIRST missed. The in-sample result was overfit to the library's wording.
2. **pplx:** alone it falls from 88.1% to 81.7% with 3 critical misses. Behind Layer 1 it now has 1 critical miss (0 in-sample), so it is not safe as the single stack model.
3. **Dual (c):** accuracy falls slightly (93.3% → 91.7%) but critical misses stay at 0, and it is the best system on the holdout. Its HITM queue captured fewer errors, 1 of 5 against 9 of 18 in-sample.
4. **Small n:** suppressed (n=4), hospice (n=3) and pairs (n=2) are too small to compare.

## Cost

Total spend was **$2.3188** of the $3.00 cap:
- generation and grading: $2.3071 over 20 calls, summed from saved usage fields;
- Jev: d1-ultra $0.0076, pplx $0.0041.

The HO6 first try timed out without returning usage. Its cost is unknown and not included.
