# Layer 1 v1.14.1 device-ticket policy (params 0.14.1-placeholder), SYNTHETIC data — Wayne rulings 2026-10-24

Every threshold is a PLACEHOLDER. Stored Jev picks only, $0 model spend. Holdout keys NOT changed.

**Contamination rule:** rules built from Wayne's rulings on library_expansion_v2 disputes, library cases and synthetic vignettes (`jev_baseline/test_layer1_v1141.py`). Holdout text not read; only per-ID route/ticket outputs were inspected after blind scoring.

## Rules (`jev_baseline/layer1_v1141.py`, `layer1_v110.v1141`)
- POLICY 1: no device ticket when the route is nurse/provider/urgent (kept as `device_ticket_suppressed` for audit). Jev-routed tickets are conditional on a final silent_log (`final_ticket`; `score_ruled.py` gates on the default-stack route).
- POLICY 2: tickets only for internal device faults. v1.14 fit family and human-cause cuff/scale parts stay OFF.
- CGM warm-up reading: no ticket. Expired CGM sensor (wear-limit flag): ticket.
- Oximeter-disagreement tickets are `device_maintenance` (no separate oximeter-reference type).
- New internal sub-families ON after blind check: `cuff_error` (error code, no number), `scale_internal` (impossible weight with normal repeat, new scale offset). Raw scale_internal ticket on HX4-006 is on a provider route and is dropped by POLICY 1.
- `spo2_flag_vs_fingertip` (from LX12-007) OFF: one unexpected ticket on holdout_v3 (HW8-007) when scored blind.

## Results (before = v1.14.0, `V1141_OFF=1`)
| Set | Ticket hits before | after | Wrong tickets before | after |
|---|---|---|---|---|
| Library v1+v2 (29 expected, relabelled key) | 15/29 | 22/29 | 1 (LX11-005) | 0 |
| holdout_v4 ruled (9 expected) | 4/9 | 2/9 | 1 (HX7-002) | 1 (HX7-002) |
| holdout_v3 ruled (4 expected) | 4/4 | 2/4 | 4 | 4 |

Holdout drops are key-vs-policy conflicts, not rule faults: HX4-010, HX5-004, HW2-008 are labelled nurse_task + ticket (POLICY 1 says no ticket); HW2-009 expects the old oximeter-reference type. Routes unchanged: v4 default 86.8%, crit 0, false pages 5.26/100, HITM 7.89/100 (challenger 86.8/0/5.26/5.26); v3 default 100%, crit 0, 0, 11.25.
