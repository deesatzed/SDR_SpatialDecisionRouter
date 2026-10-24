# v1.14.3 + open-item relabels (SYNTHETIC, Wayne 2026-10-24)

Rulings:
- HX5-002 (holdout_v4 key): silent_log, ticket dropped (motion artifact). Was supply_reference_oximeter_and_baseline.
- HX5-011 (holdout_v4 key): silent_log, ticket dropped (ECG strip already cleared as sinus). Was ecg_strip_request.
- LX2-010, LX8-010 (library v1): nurse_task kept, ticket dropped (POLICY 1, the nurse route covers it).
- LX10-002 (library v2): label kept silent_log + device_maintenance; Layer 1 fixed.
Keys edited by case ID only (relabel_20261024b.py); holdout text not read.

Layer 1 v1.14.3 (params 0.14.3-placeholder): the v1.10 syncope synonym "out cold" was unbounded and matched "about cold fingers" in LX10-002, firing HT_SYNCOPE (urgent). Now `\bout cold\b`. Built from LX10-002 + synthetic vignettes (jev_baseline/test_layer1_v1143.py, 6 tests). LX10-002 now: Layer 1 nurse_task via HT_DEVICE_DISAGREE (acceptable alternate), device ticket suppressed by POLICY 1, so its expected ticket is still a miss.

Blind re-score, stored picks, $0:
- Library (score_library.py, Layer 1 alone): tickets 20/24 -> 20/22 hit, 0 false; missed LX10-002, LX12-007; route errors LX6-004, LX10-002 -> LX6-004.
- holdout_v4: default 86.8%, crit 0 (unchanged); tickets 2/7 -> 2/5, missed HX1-009, HX2-011, HX5-003, unexpected HX7-002. HX5-002/HX5-011: final silent_log, no ticket (now correct).
- holdout_v3: default 100%, crit 0; tickets 3/3, unexpected HW5-009, HW6-010, HW7-001, HW7-006 (unchanged).
Files: lib_after.json, v4.json/.md, v3.json/.md. 344 homehealth tests pass.
