# Layer 1 on every case + Jev v1.8 (liquid/d1-ultra default): results (2026-10-18; synthetic only)

Sources: `results_v18/summary_l1.json`, `results_v18/per_case_l1.csv`. Base variant, 270 cases. "Correct" = the expected route or an acceptable alternate. The labels call for escalate_human on 30.7 cases per 100.

## Headline
| system | accuracy | critical misses | pages / 100 | false pages / 100 | over-escalations | suppressed (24) | hospice (7) |
|---|---|---|---|---|---|---|---|
| d1-ultra alone, v1.7 prompt (baseline) | 88.9% | 3: AC1-002, AC1-003, ST3-001 | 35.2 | 6.3 | 17 | 45.8% | 3/7 |
| label-tier Layer 1 + d1-ultra (baseline) | 89.3% | 2: AC1-002, ST3-001 | 35.6 | 6.3 | 17 | 45.8% | 3/7 |
| d1-ultra alone, **v1.8 prompt** | 88.1% | **1: HK8-005** | 38.1 | 6.3 | 17 | 37.5% | 3/7 |
| **derived Layer 1 + d1-ultra v1.8 (new default)** | **92.6%** | **0** | **35.2** | **2.6** | **7** | 83.3% | **7/7** |
| derived Layer 1 + baseline d1-ultra picks (isolates Layer 1) | 93.7% | 0 | 33.3 | 2.6 | 7 | 87.5% | 7/7 |

- **Layer 1 removes every critical miss** and cuts false pages from 6.3 to 2.6 per 100. It fixes the hospice goals_of_care cases (Layer 1 routes them to the same-shift hospice nurse) and most suppressed-trigger over-escalations (Jev's escalate is capped at wake_specialist unless Layer 1 sees an acute presentation).
- Router ownership (v1.8 run): Jev decided 188 cases, Layer 1 ABSOLUTE 17, Layer 1 CONFIRM_FIRST 38, Layer 1 hospice goals 4, Jev-capped suppressed/artifact 23.
- The v1.8 prompt alone fixed the three baseline d1-ultra misses but added one (HK8-005), and paged more (38.1 vs 35.2 per 100). With Layer 1 in front, the baseline picks score slightly better than the v1.8 picks (93.7% vs 92.6%), so the prompt change matters less once Layer 1 runs.
- Cost of the v1.8 rerun: **$0.0345** (1,080 calls, 0 without a pick; cap $0.15). Already counted: this run happened before the billing stop and was not repeated.

## Layer 1 on every case (deterministic adapter, no model calls)
- `layer1_adapter.py` derives trigger_eval inputs from the case **fact fields only**. A test strips all label fields and gets identical decisions on all 270 cases. It runs the engine's hard limits, artifact, CGM, learning-period, banded chest-pain, goals-of-care and unanswered-prompt logic.
- **Agreement with the labels** on the 81 trigger cases:
  - tier and suppression reason match on 80/81, and the rule matches on 81/81
  - the paging decision (ABSOLUTE/CONFIRM_FIRST vs not) matches on 81/81
  - the single tier mismatch is **ST1-010**: Layer 1 says ABSOLUTE (band A), the label says CONFIRM_FIRST by Wayne's clinician override. Both escalate.
- **Non-trigger cases (189):** 0 paging triggers. One non-paging false trigger: NV3-024 (gap rule SUPPRESSED explained; expected nurse_task).
- Caveat: the adapter's text patterns were developed on this same library, so 80/81 is an in-sample figure; a held-out set is needed before relying on it.

## Why d1-ultra missed (baseline) and what v1.8 changed
- **ST3-001** (COPD, SpO2 87% on monitoring day 4): the model never saw that the patient was still in the learning period (`baseline_status` was not in its input), so 87% read as her normal. v1.8 adds a one-line monitoring status from that fact field, and the policy states the learning-period rule. P(escalate) went from 0.08 to 0.63, and the pick went from silent_log to escalate_human. The engine rule is in params 0.8 (SMART_TRIGGERS v1.8, section 9h).
- **AC1-002 / AC1-003** (4th episode of exertional chest tightness): the v1.7 policy summary did not mention the crescendo rule. v1.8 adds one sentence. P(escalate) went from 0.23 to 0.92 and from 0.43 to 0.88.
- **New v1.8 miss, HK8-005** (unexplained 50 h gap after a pneumonia discharge): P(escalate) fell from 0.43 to 0.25 and the pick was wake_specialist. Layer 1 catches it (HT_GAP48_HIGHRISK CONFIRM_FIRST).
- **v1.8 robustness:** reversed options gave the same pick 90%; deleting the key line changed the pick 28%; with all data missing it escalated 73% (90% with the veto). Brier score for P(escalate) improved from 0.0995 to 0.0936.

## Fly layer (GoalJevFly FlyPolicy gate)
- **Status: not run on the library.** It exists only as the 12-case smoke test (`jevfly_smoke/run_fly.py`, run read-only from the GoalJevFly checkout on the Mac's external volume). The gate needs per-day `(latent, repeated, verified)` failure flags, and the library runner has `days = null` for all 270 cases, so there is no mapping yet.
- **Smoke-test result (12 cases):**
  - threshold 0.2 (the repo's frozen value): flagged 5/5 escalate cases but also 6/7 non-escalate cases
  - threshold 0.7: 3/5 escalate and 5/7 non-escalate
  - threshold 0.9: 3/5 escalate and 2/7 non-escalate
  - It does not separate the classes yet.
- **To include it:** derive the day flags deterministically from Layer 1 (latent = any deviation from own baseline that day; repeated = 2+ consecutive days; verified = a Layer 1 ABSOLUTE/confirmed trigger), run FlyPolicy per case locally on the Mac (no API cost), and score it as a "check" signal against escalate/wake.
