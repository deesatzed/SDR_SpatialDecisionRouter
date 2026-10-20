# Fly layer (Layer 3): local connectome gate, SYNTHETIC

Layer 3 runs the GoalJevFly `FlyPolicy` (EPG top-12 graph receipt) locally, one step per day (Day -7 to Day 0), and compares it
with Layer 1 + Jev. It makes no network or model calls.

- `fly_flags.py` derives the per-day inputs from case fact fields (`layer1_adapter.facts_only`) plus the Layer 1 decision. It never reads labels.
  - `latent` = any deviation from the patient's own baseline that day (HR, SpO2, RR, SBP, temperature, glucose, steps, weight,
    a data gap of 12 h or more in the last 48 h, a Day-0 symptom report, or a Layer 1 CONFIRM_FIRST).
  - `repeated` = latent on two or more consecutive days.
  - `verified` = Layer 1 ABSOLUTE on Day 0, including an ABSOLUTE suppressed for goals of care.
  - All cut-offs were fixed before scoring and were not tuned.
- `run_fly.py` needs the GoalJevFly source.
  - Set `GOAL_FLY_SRC`. It defaults to the external-volume path and exits with a clear message if the volume is missing.
  - It writes `results/fly_readouts.json`, with per-day readouts for leak values 0.5, 0.8 and 0.95.
- `score_fly.py` scores Fly alone and Layer 1 + Jev + Fly.
  - It uses the stored v1.8 `liquid/d1-ultra` picks in `../jev_baseline/results_v18/parsed/` and makes no new calls.
  - Combination rules: `flag_only`, `confirm_first` and `bump_wake`. Fly can raise a route or flag a disagreement. It never lowers a route or overrides Layer 1.
  - Thresholds are tuned on the train split only. The held-out split is whole source batches, chosen in sha256 order until it holds at least 30% of cases. Pairs never straddle batches.

```bash
GOAL_FLY_SRC=/path/to/GoalJevFly/src python homehealth/fly_layer/run_fly.py
python homehealth/fly_layer/score_fly.py
python -m pytest -q homehealth/fly_layer   # the end-to-end Fly test skips without GOAL_FLY_SRC
```

The runner JSON and the v1.8 parsed picks are not committed. Point `RUNNER_JSON` and `JEV_PICKS` at the pipeline copies (e.g.
`jevfly_smoke/library_v2/smart_triggers/library_v2_smart_runner.json` and `jevfly_smoke/jev_baseline/results_v18/parsed/liquid_d1-ultra.jsonl`).
