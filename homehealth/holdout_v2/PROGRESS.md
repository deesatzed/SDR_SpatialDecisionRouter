# holdout_v2 PROGRESS (SYNTHETIC) — restart notes
Frozen: Layer 1 / params / prompts at e8c7aa0 (FREEZE_md5.txt). No tuning on v2.
Only pipeline change: grade_merge accepts v1.10 labels (HT_FALL_ANTICOAG ABSOLUTE, HT_BRADY_RATE_DRUG, watch_prompt).
## Estimate (from holdout_v1 per-call costs)
- gen: 8 batches x 11 cases. Haiku ~$0.045 per batch, DeepSeek v4 pro less (~$0.03): about $0.30
- grade: 4 pairs x ~$0.26 (gemini-4-argon): about $1.05; retries/splits reserve $0.40
- Jev d1+pplx on ~45 accepted cases: about $0.01 (holdout_v1 60 cases = $0.012); cap $0.10
- total estimate ~$1.4; hard guard GEN_CAP $2.50 + Jev SPEND_CAP $0.10, so at most $2.60 < $3
## Steps (each leaves files; rerun skips finished parts)
1. [x] (spend $1.570; HV1+HV2 grade needed a 2nd try) gen+grade: `OPENROUTER_API_KEY=... python3 run_holdout_v2.py` (state.json, gen/, grade/)
2. [x] (110 gen incl. HV9-HV10 Haiku top-up; 65 accepted, 0 near-dupes, 16 queued, 29 fix_list; spend $1.885) finalize: `python3 finalize_holdout_v2.py` (dedupe vs library_v2 + holdout_v1; accepted / review_queue / runner)
3. [x] (Jev 65 cases x4 variants x2 models, 0 without pick, $0.0143) Jev: jev_run.py on the accepted runner -> jev/parsed
4. [x] (results/summary.json; review_queue.csv = 16 merge disputes + 9 scoring errors) score: score_holdout_v2.py -> results/
5. [x] commit on Mac under homehealth/holdout_v2 (explicit paths, no push)
## Notes
- Generators: Haiku 5.5 high yield (HV1/3/5/7/9/10: 61/66 accepted); DeepSeek v4 pro low yield (HV2 4/11, HV4/6/8 0/33), all schema/consistency rejects
  (weight without a scale device, router_input omissions, missing v2.3 fields, banned words), not clinical. HV9/HV10 = Haiku re-runs of the HV4/HV6 specs.
- Scripts use box paths (/workspace/jevfly_smoke/..., /workspace/sdr_rename/homehealth); see top of each script.
- Total spend: gen+grade $1.8846 + Jev $0.0143 = $1.8989 (cap $3).

## Review + re-score (2026-10-22)
- [x] review_queue.csv: all 25 ruled by Wayne. Key: `python3 build_ruled_key.py` -> holdout_v2_ruled_key.json (65 accepted, 9 re-ruled, + 16 disputes = 81).
  Data fixes in key: HV9-006 living -> "with spouse and adult child"; HV4-007 last_condition_change -> medication_change.
- [x] `python3 score_ruled.py` -> results_ruled/summary.json (stored picks, 0 calls). Disputed 16 have no picks: Layer 1 alone only.
- [x] Design doc: ../docs/PATIENT_OVERRIDES_DESIGN.md (per-patient overrides; not implemented).
## Layer 1 v1.10.2 fixes — IMPLEMENTED 2026-10-23 (params 0.10.2-placeholder; jev_baseline/test_layer1_v1102.py; results jev_baseline/results_v1102/SUMMARY.md) (from holdout_v2 rulings; build with practice cases, NOT holdout text; not implemented)
- [x] Witnessed fall ("saw her fall", "watched it happen") cannot be cleared by caregiver/patient reassurance (HV3-010).
- [x] Pain after (rule HT_FALL_PAIN) a fall (e.g. holding hip) blocks suppression and escalates, even off anticoagulant (HV3-010, HV5-002).
- [x] unreliable_reading (now possible_fall_unverified, floor nurse_task) suppression does not apply to a possible fall on anticoagulant (HV5-003).
- [x] On anticoagulant: on-wrist (inactivity_min 10, placeholder) impact + post-impact inactivity fires the fall trigger even if the patient explains it away (HV7-005).
- [x] (candidate, HT_SPO2_REST_DYSPNEA, spo2_max 90 placeholder; fired on no stored case) Candidate: confirmed SpO2 <= 90% + dyspnea at rest (HF) -> escalate (HV1-007). Threshold is Wayne's call.
- Dropped by Wayne: digoxin/hospice bradycardia page rule (HV10-002); HF weight-gain trigger (HV5-007).
- Caveat: holdout_v2 is now partly tuning data for v1.10.2; next unbiased check needs holdout_v3.
