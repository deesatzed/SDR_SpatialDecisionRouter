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

## v1.9 route rename (Wayne 2026-10-21)

- Routes: `silent_log` (silent), `nurse_task` (nurse task), `provider_task` (provider task: review by the clinician responsible for that condition or medication on the same business day, not a page), `urgent_page` (urgent page: page someone now; urgent hospice-comfort problems page the hospice nurse). Definitions: `routes.py`, SMART_TRIGGERS v1.9 section 0.
- Backward compatible: `wake_specialist` -> `provider_task` and `escalate_human` -> `urgent_page` are mapped on read (`routes.canon`, `canon_row`), so stored v1.8 picks and old outputs still score. Re-scored from stored picks only (no API calls): accuracy, critical misses, false pages and HITM counts are identical to 9f5ca71.
- `JEV_PROMPT=v1.9` (default) shows the new ids and the route definitions; `v1.8`/`v1.7` stay byte-identical for reproducibility.
- Layer 1 hardening list: SMART_TRIGGERS section 10 (the earlier HO8-025 hospice note was wrong and is removed).
