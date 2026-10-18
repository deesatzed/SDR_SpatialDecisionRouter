# jev_baseline: Layer 2 (OpenRouter decision models) over the homehealth library (SYNTHETIC)
- `jev_run.py` - runs models over the runner JSON (4 variants per case): policy summary v1.7 + case lines only, label-leak check, PHI pre-send guard (`phi_guard.py`), 600 s timeout, backoff, per-model checkpoint/resume (`results/parsed/*.jsonl`, parsed answers and token counts only), spend cap (`SPEND_CAP`, default $0.50). Needs `OPENROUTER_API_KEY`; `--check-only` runs the pre-send checks without calling anything.
- `score_jev.py` - scores Jev alone and Layer1+Jev: accuracy with alternates, severity-weighted critical misses, over-escalation and pages/100, breakdowns, engine-tier agreement, robustness, Brier, the clinician_override and hospice cases.
- Inputs: `RUNNER_JSON` (written by casegen/convert_casegen.py via build_outputs.py), `ACCEPTED_JSON` and `OUTCOMES_CSV` (default `../library/`).
- Tests: `python -m pytest -q homehealth/jev_baseline`. Results: `results/REPORT.md`.
