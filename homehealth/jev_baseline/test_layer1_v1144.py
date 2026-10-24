"""SMART_TRIGGERS v1.14.4 (Wayne 2026-10-24): fingertip-clearance device ticket, narrowed to a poor-contact flag on a resting wearable SpO2.
Library LX10-004 / LX12-007 / LX12-008 + hand-written SYNTHETIC vignettes only (never holdout_v3/holdout_v4 text). No API calls."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
LIB2 = os.path.join(HERE, "..", "library_expansion_v2", "library_expansion_v2_accepted.json")
B = dict(pmh=["hypertension"], devices=["ring", "fingertip_oximeter"], baseline_30d={"rest_hr": 72, "steps": 2600, "spo2_night_min": 94})
def lib(cid): return next(c for c in json.load(open(LIB2))["cases"] if c["case_id"] == cid)
def tk(d): return L.V141.final_ticket(d, L.route(d, None)[0] or "silent_log")
def test_params():
    V = L.T.v110(L.PARAMS)["v1141"]; assert L.PARAMS["version"] == "0.14.4-placeholder" and V["spo2_flag_vs_fingertip"] and V["spo2_contact_rest_only"]
def test_lx12_007_gets_ticket():
    d = L.evaluate_case(lib("LX12-007")); assert L.route(d, None)[0] in (None, "silent_log") and (tk(d) or {}).get("type") == "device_maintenance"
def test_lx12_008_real_low_no_ticket():
    d = L.evaluate_case(lib("LX12-008")); assert L.route(d, None)[0] == "urgent_page" and not tk(d)
def test_synthetic_contact_rest_ticket():
    d = ev(**B, trend_last_7d="Day -6 to -1 ring rest SpO2 94-96%. Day 0 10:00: ring SpO2 85% at rest with a poor-contact flag. Day 0 10:06: fingertip oximeter 96% on a good waveform.",
           caregiver_or_nurse_note="Son: she is sitting watching TV and feels fine, no breathlessness.")
    assert (tk(d) or {}).get("type") == "device_maintenance"
def test_synthetic_motion_flag_no_ticket():
    d = ev(**B, trend_last_7d="Day -6 to -1 watch rest SpO2 94-96%. Day 0 10:00: walking to the kitchen, watch SpO2 85% with a motion flag. Day 0 10:04: fingertip oximeter 96% on a good waveform; watch 95% at rest.",
           caregiver_or_nurse_note="Wife: he feels fine, no breathlessness.")
    assert not tk(d)
def test_synthetic_fit_flag_no_ticket():
    d = ev(**B, trend_last_7d="Day -6 to -1 watch rest SpO2 94-96%. Day 0 10:00: watch SpO2 86% at rest with a fit flag (band loose). Day 0 10:05: fingertip oximeter 96% on a good waveform.",
           caregiver_or_nurse_note="Daughter: she feels fine.")
    assert not tk(d)
