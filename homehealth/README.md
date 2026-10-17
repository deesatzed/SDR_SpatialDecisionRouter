# homehealth/ — smart hard-trigger engine and synthetic case library

This folder holds the home-monitoring side of the Spatial Decision Router:
- a deterministic **trigger engine** that decides whether a hard-trigger alert should page now, confirm first, or be suppressed or logged
- the **case-generation pipeline** (prompts, merge and grade scripts)
- the resulting **synthetic case library** in SDR Cases/Outcomes CSV format

> **All data here is synthetic. Every threshold, band, timeout and window in `trigger_engine/trigger_params.json` is a PLACEHOLDER.** The clinical owner must set them before any real use. Parameter changes go only through `apply_param_change(..., approved_by=<named human>)`, which validates the change and logs it in `change_log`.

## Layout
| folder | contents |
|---|---|
| `trigger_engine/` | `trigger_params.json` (placeholders), `trigger_eval.py` (engine), pytest suites |
| `casegen/` | `prompts/` (policy `SMART_TRIGGERS.md`, generator `GEN_LLM2_v2.3`, grader `GRADER_LLM3_v1.3`, `VARIANTS.md`, older v2.2/v1.2), `grade_merge.py`, `convert_casegen.py` (SDR CSV export), pipeline/run scripts, `recheck/` |
| `library/` | `library_v2_smart_accepted.json` (261 cases), `library_v2_smart_Cases_Medical.csv` / `_Outcomes.csv`, `review_queue.csv`, `fix_list.csv`, `DIFF_SUMMARY.md`, `summary.json` |

## Policy and engine layers (see `casegen/prompts/SMART_TRIGGERS.md`)
- **Four checks per fired trigger:** a reliable reading, a change from the patient's own baseline, unexplained, and within the goals of care.
- **Tiers:** ABSOLUTE (page now), CONFIRM_FIRST (recheck or call with a timeout, then escalate), SUPPRESSED (with a logged reason) and ARTIFACT (device recheck, no page).
- **Vital-sign layers:**
  1. Hard limits are fixed and never learned. An implausible value is an ARTIFACT; a danger value is ABSOLUTE.
  2. During a per-patient learning period, population defaults apply and borderline readings get a wider confirm-first.
  3. Ongoing adaptation:
     - a rolling median/MAD baseline
     - a partial reset after a condition change (e.g. starting a beta-blocker)
     - a drift guard, so a slow monotonic drift toward abnormal is flagged, not absorbed
     - everything is clamped inside the hard limits and logged
- **Chest pain** (HT_CHEST_PAIN_VITALS) is banded A–D, with modifiers for sleep, exertion, rate-control drugs, pacemakers, a known brady or tachy range, device reliability, red flags and symptom concordance. A crescendo angina pattern with normal vitals is CONFIRM_FIRST.
- **CGM pressure-low artifact rule:**
  - A suspected compression low (pinned or pressed sensor, overnight sensor-side sleep, a rapid drop and rebound) with no fingerstick → ARTIFACT with a fingerstick recheck.
  - A fingerstick above the danger limit → SUPPRESSED unreliable_reading.
  - A fingerstick-confirmed or symptomatic low stays ABSOLUTE.

## Running the tests
From the repo root (Python 3.13; pytest only, no other dependencies):
```
python -m pytest -q homehealth/trigger_engine
```
`conftest.py` puts the engine and `casegen/grade_merge.py` on the path. The suites cover the engine, chest pain, the CGM pressure rule and the grade_merge label checks.

## Notes
- The pipeline scripts in `casegen/` (`smart_run.py`, `build_outputs.py`, `apply_*.py`, `recheck/`) are included for provenance. They use the relative paths of the original working layout (`casegen/prompts_v2/`, `library_v2/smart_triggers/`) and call OpenRouter through `orcall.py`, which reads `OPENROUTER_API_KEY` from the environment. No keys, `.env` files or raw API responses are committed.
- `library/DIFF_SUMMARY.md` records every relabel, rule change, review item and API cost. Open clinical review items are in `library/review_queue.csv`.
