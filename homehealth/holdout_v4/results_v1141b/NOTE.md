# Key relabel 2026-10-24 (SYNTHETIC)

Holdout keys and library labels were brought in line with Wayne's device-ticket policies on 2026-10-24
(POLICY 1: no ticket on nurse/provider/urgent routes; POLICY 2: tickets only for internal device faults). Routes unchanged.

- holdout_v4 ruled key: HX4-010, HX5-004 (nurse_task) ticket dropped.
- holdout_v3 ruled key: HW2-008 (nurse_task) ticket dropped; HW2-009 ticket type supply_reference_oximeter_and_baseline -> device_maintenance.
- Library: LX2-006, LX10-001, LX10-011, LX11-002, LX11-003 (silent_log, human cause) ticket dropped.
- Still open for Wayne: LX2-010 (oximeter reference on nurse route), LX8-010 (ECG strip request, clinical order), LX10-002 (L1 urgent via fainting vs silent_log label).

Script: `relabel_20261024.py`. Blind re-score with stored picks, $0: `v4.*` (holdout_v4/jev + jev_disputes), `v3.*` (holdout_v3/jev_v110), `library_expansion_v2/lib_tickets_v1141_relabel.json`.
