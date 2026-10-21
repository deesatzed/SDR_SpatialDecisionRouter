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
