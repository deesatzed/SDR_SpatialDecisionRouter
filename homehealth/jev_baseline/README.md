# jev_baseline: Layer 2 (OpenRouter decision models) over the homehealth library (SYNTHETIC)
- `jev_run.py` - runs models over the runner JSON (4 variants per case): policy summary v1.7 + case lines only, label-leak check, PHI pre-send guard (`phi_guard.py`), 600 s timeout, backoff, per-model checkpoint/resume (`results/parsed/*.jsonl`, parsed answers and token counts only), spend cap (`SPEND_CAP`, default $0.50). Needs `OPENROUTER_API_KEY`; `--check-only` runs the pre-send checks without calling anything.
- `score_jev.py` - scores Jev alone and Layer1+Jev: accuracy with alternates, severity-weighted critical misses, over-escalation and pages/100, breakdowns, engine-tier agreement, robustness, Brier, the clinician_override and hospice cases.
- Inputs: `RUNNER_JSON` (written by casegen/convert_casegen.py via build_outputs.py), `ACCEPTED_JSON` and `OUTCOMES_CSV` (default `../library/`).
- Tests: `python -m pytest -q homehealth/jev_baseline`. Results: `results/REPORT.md`.
- v1.8 (2026-10-18): default model `liquid/d1-ultra`; `JEV_PROMPT=v1.8` (default) adds the learning-period and crescendo sentences and a one-line monitoring status from the `baseline_status` fact; `JEV_OUT=results_v18` keeps runs apart.
- `layer1_adapter.py` - deterministic Layer 1 on every case: derives trigger_eval inputs from fact fields only and routes with `route()` (Layer 1 owns triggers; Jev decides non-trigger cases and, capped, suppressed ones). `score_l1jev.py` compares baseline / v1.8 / Layer1+Jev. Report: `results_v18/REPORT.md`.

## Dual-model Jev (default since 2026-10-20)

- **Models:** `jev_run.py` now runs both `liquid/d1-ultra` (the lead) and `perplexity/pplx-decider-v1.2` by default.
- **Layer 1 first:** Layer 1 is mandatory and decides first. ABSOLUTE and CONFIRM_FIRST cases escalate, and SUPPRESSED goals-of-care cases go to nurse_task.
- **Jev cases:** on cases Jev decides, `dual_jev.dual_route` routes each model's pick through Layer 1. The default rule is **`cautious_max_hitm`**:
  - if the models agree, the case takes that route;
  - if they disagree, it takes the higher (more cautious) route and is flagged for HITM review.
- **Fly:** a flag-only Fly layer (`../fly_layer`) can add HITM flags on top. It is optional and never changes a route.
- **No Layer 1:** the same rule is applied to the raw picks, led by d1-ultra.
- **Scoring:** `python dual_jev.py` scores every rule from the stored picks and makes no API calls.
  - Set `JEV_PICKS_D1` and `JEV_PICKS_PPLX` to point at the parsed checkpoints.
  - Results are in `results_dual/`.
