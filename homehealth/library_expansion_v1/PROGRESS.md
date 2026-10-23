# library_expansion_v1 (SYNTHETIC practice/library batch) — SMART_TRIGGERS v1.11.2, params 0.11.2-placeholder, seed 20261024
Pipeline = holdout_v4 (GEN_LLM2_v2.3 + hard slice, GRADER_LLM3_v1.3 / gemini-4-argon, grade_merge, story dedupe with pair partners exempt) adapted:
- DO_NOT_REPEAT sent to generators/grader = library_v2 + holdout_v1/v2 only. holdout_v3/v4 text NEVER entered any prompt; it is used only in the LOCAL dedupe (finalize_lx1.py).
- Batches weighted to weak areas: LX1/LX8 slow drift, LX2 device disagreement wording, LX3 falls on anticoagulants, LX4 stable angina vs chest pain, LX5 COPD bands, LX6 CKD drug lows, LX7 mixed near-miss pairs.
## Round log
1. Gen LX1-LX7 (78) + grade: 39 accepted. Systemic failures: banned word "artifact(s)" in visible text, weight without scale in devices, "no hard trigger" in router_input.
2. Mechanical repair (no label/clinical fact changed; originals in gen/*.batch.orig.json): artifact -> "device-quality flag(s)/issue", added "scale" to devices when weight given, removed "no hard trigger". Regraded LX1+LX2, LX3+LX4, LX7 (round-1 grades in grade_round1/). 58 accepted; LX1 still 0 (grader content fixes, 1 dedupe, 5 disputes).
3. Top-up LX8 (10 drift cases, stricter hygiene) -> 10 accepted. Final 68 accepted, 5 in merge_disputes.csv for Wayne, 8 on fix_list.csv, 7 dedupe removed.
Author route = expected_route on every case. Spend: see spend.json.
