# holdout_v3 (SYNTHETIC) — SMART_TRIGGERS v1.10.3 frozen at fb262af

Same pipeline as holdout_v2: GEN_LLM2_v2.3 + hard slice, GRADER_LLM3_v1.3, and grade_merge (RULE_TIER now includes HT_FALL_PAIN ABSOLUTE and HT_SPO2_REST_DYSPNEA CONFIRM_FIRST). Plus ADDENDUM_v1103.md.
It uses the same 8-module category mix (HW1–HW8, 11 cases each). Generators: Haiku 5.5 for HW1 and HW3–HW7, and DeepSeek v4 pro for HW2 and HW8.
The do-not-repeat list and the near-duplicate check cover library_v2 plus all holdout_v1 and holdout_v2 generated cases.
The generator wording examples were rotated, and the v1.10.3 focal-neuro phrases were added to the avoid list, so HT_FOCAL_NEURO is tested on wording it has not seen.

## Status: COMPLETE (2026-10-23)
Run 1 stopped at the OpenRouter per-key limit (HTTP 402). Wayne raised the limit, and run 2 graded HW3+HW4 and HW5+HW6.

1. [x] Generated 88 cases; generation cost $0.4104.
2. [x] Graded 88 of 88; grading cost $1.0670.
3. [x] Merged 64, with 1 removed as a near-duplicate (HW6-008, close to HV5-009 on the decisive feature, Jaccard 0.522).
   - 63 accepted. 17 disputed and 7 on the fix list.
4. [x] Jev: 63 cases x 4 variants x 2 models, every row with a pick, cost $0.0141.
5. [x] Scored (results/summary.json):

| System | Decided | Accuracy | Critical misses | False pages/100 | HITM/100 | Errors (HITM caught) |
|---|---|---|---|---|---|---|
| Layer 1 alone | 26/63 | 80.8% | 2 | 4.76 | 63.49 | 5 (0) |
| L1 + d1-ultra | 63/63 | 79.4% | 2 | 6.35 | 4.76 | 13 (1) |
| L1 + pplx | 63/63 | 84.1% | 2 | 4.76 | 4.76 | 10 (1) |
| L1 + dual (cautious_max_hitm), default | 63/63 | 82.5% | 2 | 6.35 | 14.29 | 11 (2) |

Both critical misses come from Layer 1 suppressing a real danger; Jev cannot override a suppression.
- HW3-008: confirmed symptomatic sulfonylurea low (46/47 mg/dL) in a hospice patient. goals_of_care sent it to nurse_task, but the label is an urgent comfort problem for the hospice nurse.
- HW4-003: COPD patient with a documented 85-87% band and two good readings at 82%. at_patient_baseline sent it to nurse_task or provider_task, but this is a drop below the band.

Layer 1 missed the triggers in HW1-001 to HW1-005 (unseen wording). All three Jev-backed systems routed all five to urgent_page.

6. [x] review_queue.csv has 37 rows, in this order:
   - 2 critical misses
   - 4 false pages
   - 4 under-triage
   - 3 over-triage
   - 7 Layer 1 trigger misses caught by Jev
   - 17 disputes
   HW1-001 is flagged as a near-duplicate of holdout_v2 HV2-001, with a suggestion to drop it.

Total spend: $1.4915 of the $3 cap.
