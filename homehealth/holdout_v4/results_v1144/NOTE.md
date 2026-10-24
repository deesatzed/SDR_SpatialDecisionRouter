# v1.14.4 fingertip-clearance device ticket (SYNTHETIC, Wayne 2026-10-24)

Rule: `spo2_flag_vs_fingertip` ON, narrowed (`spo2_contact_rest_only`): a ring/watch SpO2 taken at rest with a poor-contact flag, cleared by a good-waveform fingertip 94%+ (Layer 1 clears it as a repeat) -> device_maintenance ticket, only if the final route is silent_log (POLICY 1). Motion and fit flags never earn it (POLICY 2 human cause; Wayne's motion-artifact = no ticket ruling).
Designed from library LX10-004 / LX12-007 / LX12-008 + synthetic vignettes (jev_baseline/test_layer1_v1144.py). Holdout text not read; holdouts scored blind after design.

Blind re-score, stored picks, $0:
- Broad rule (any contact/motion/fit flag): library 21/21, 0 false; holdout_v3 adds unexpected HW8-007 (lib_broad_rule.json, v3_broad_rule.json).
- Narrowed rule: library tickets 20/21 -> 21/21, 0 false (LX12-007 now hit); holdout_v3 tickets 3/3, unexpected HW5-009, HW6-010, HW7-001, HW7-006 (HW8-007 no longer ticketed; unchanged vs v1.14.3); holdout_v4 2/5, missed HX1-009, HX2-011, HX5-003, unexpected HX7-002 (unchanged). Routes unchanged: v4 default 86.8%, v3 100%, crit 0.
Also fixed stale LX10-002 label assertion in test_layer1_v1143.py (relabelled nurse_task in 045ac94). 350 homehealth tests pass.
