# Layer 1 v1.14.0 named device-fault tickets (params 0.14.0-placeholder), SYNTHETIC data

Every threshold is a PLACEHOLDER. Stored Jev picks only, $0 model spend for scoring.

**Contamination rule:** rules built only from library cases (library_expansion_v2 device-fault batch, 31 accepted; library_expansion_v1, 72) and hand-written synthetic vignettes (`jev_baseline/test_layer1_v1140.py`). holdout_v3/v4 case text was not read; holdouts were scored once after the rules were written. Only rule-family names were looked up for the unexpected holdout tickets, never case text.

## Rules (`jev_baseline/layer1_v1140.py`, `layer1_v110.v1140`)
- Ticket only: adds a device_maintenance ticket, never changes a route (a ticket can sit on top of nurse/provider/urgent).
- ON: sync/upload failure; battery/charger failure (not if charged/replaced with continuous data since); app/firmware update that changes how a stream is measured or exported; duplicated records or device clock/time-zone shift; CGM warm-up or expired sensor named in the trend/note.
- ON: firmware-shift guard: withdraws a v1.13 firmware-shift ticket (and its silent_log ownership) when nothing was measured after the re-pair/update flag or new positional-breathing words appear (fixed library false ticket LX12-002).
- OFF after blind scoring (one unexpected holdout_v4 ticket each, routes unchanged): scale (HX4-006), fit/strap/patch (HX5-006), BP cuff (HX6-004).
- Not ticketed: CGM compression lows (library_expansion_v1 labels them nurse_task with no ticket; LX11-007 says ticket — conflict for Wayne).

## Results
| Set | Tickets hit before (v1.13) | after (v1.14) | False tickets before | after |
|---|---|---|---|---|
| Library LX1-LX8 (13 expected) | 13/13 | 13/13 | 0 | 0 |
| Library LX9-LX12 (19 expected) | 5/19 | 8/19 (18/19 with scale/fit/cuff on) | 1 (LX12-002) | 0 |
| holdout_v4 ruled key (9 expected) | 4/9 | 4/9 (4/9 with all families on, + 3 false) | 1 (HX7-002) | 1 (HX7-002) |
| holdout_v3 ruled key (4 expected) | 4/4 | 4/4 | 4 | 4 |

Routes unchanged on both holdouts. holdout_v4 default 86.8%, crit 0, false pages 5.26/100, HITM 7.89/100; challenger 86.8%, crit 0, 5.26, 5.26. holdout_v3 default 100%, crit 0, 0, 11.25 (challenger has no stored drex-max picks for v3).
Legacy library_v2 (270, unlabeled for tickets): 2 new tickets (HK8-003, HK8-004, lost charger on top of the gap route; routes unchanged).

Files: `v4_before/after.json`, `v3_before/after.json` (+ .txt), `v4_after_allfamilies.*` (all families on). `score_ruled.py` with `V1140_OFF=1` for before.
