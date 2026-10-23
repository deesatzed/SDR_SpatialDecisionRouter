# holdout_v3 (SYNTHETIC) — SMART_TRIGGERS v1.10.3 frozen at fb262af

Same pipeline as holdout_v2: GEN_LLM2_v2.3 + hard slice, GRADER_LLM3_v1.3, and grade_merge (RULE_TIER now includes HT_FALL_PAIN ABSOLUTE and HT_SPO2_REST_DYSPNEA CONFIRM_FIRST). Plus ADDENDUM_v1103.md.
It uses the same 8-module category mix (HW1–HW8, 11 cases each). Generators: Haiku 5.5 for HW1 and HW3–HW7, and DeepSeek v4 pro for HW2 and HW8.
The do-not-repeat list and the near-duplicate check cover library_v2 plus all holdout_v1 and holdout_v2 generated cases.
The generator wording examples were rotated, and the v1.10.3 focal-neuro phrases were added to the avoid list, so HT_FOCAL_NEURO is tested on wording it has not seen.

## Status: PARTIAL — the run stopped at the OpenRouter per-key limit
1. [x] Generated 88 cases (HW1–HW8), at a cost of $0.4104 for generation.
2. [~] Graded 44 of 88 (HW1+HW2 and HW7+HW8), at a cost of $0.5978 for grading (two graders at about $0.29 each).
   - HW3+HW4 (CGM and SpO2 artifacts) and HW5+HW6 (falls and hospice) got HTTP 402, because the key's $14 limit ran out.
   - Those cases are kept in gen/ and have NOT been graded.
3. [x] Merge and dedupe: 21 accepted (HW1 9, HW2 1, HW7 11; HW8 0). 16 disputed and 7 on the fix list. 0 removed as near-duplicates.
4. [ ] Jev: not run, because the key limit was reached. jev/parsed is empty.
   - So the three Jev-backed systems only score the cases Layer 1 decides.
5. [x] Scoring with Layer 1 from stored rules (results/summary.json).
   - Layer 1 decided 3 of 21 cases. All 3 were correct, with 0 false pages.
   - Of the 8 labelled hard-trigger cases, Layer 1 fired on 3 and missed 5: HW1-001 to HW1-005, all labelled urgent_page.
6. [x] Built review_queue.csv: 5 Layer 1 trigger misses come first, then 16 merge disputes, ordered by route stakes.

## To resume (needs the key limit raised, or a new key)
- Re-run `python3 run_holdout_v3.py`. Checkpoints skip finished work.
- Then run finalize_holdout_v3.py, then Jev:
  `RUNNER_JSON=holdout_v3_runner.json CASES_JSON=holdout_v3_accepted.json JEV_OUT=<abs>/jev SPEND_CAP=0.10 jev_run.py`
- Then run score_holdout_v3.py.
- Remaining budget under the $3 cap: about $1.99.
