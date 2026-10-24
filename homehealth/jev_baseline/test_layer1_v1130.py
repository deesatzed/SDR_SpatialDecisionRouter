"""SMART_TRIGGERS v1.13.0 device-ticket emission. Hand-written SYNTHETIC vignettes only (never holdout_v3/holdout_v4 text). No API calls."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
def r(d): return L.route(d, None)[0]
def tk(d): return (d.get("device_ticket") or {}).get("type")
ACT = dict(pmh=["osteoarthritis", "hypertension"], devices=["watch", "ring", "scale"], baseline_30d={"rest_hr": 70, "steps": 4000, "weight_kg": 75.0})

def test_watch_steps_rise_ring_flat_is_silent_plus_ticket():
    d = ev(**ACT, trend_last_7d="Day -6: watch steps 4000, ring steps 3900; Day -4: watch 5200, ring 4000; Day 0: watch 6400, ring 4050. Rest HR 68-72, weight 75.0-75.2 kg, flat.")
    assert r(d) == "silent_log" and tk(d) == "device_maintenance"
def test_ring_steps_drop_watch_flat_is_ticket():
    d = ev(**ACT, trend_last_7d="Day -6: ring steps 4100, watch steps 4000; Day -3: ring 2900, watch 4100; Day 0: ring 2200, watch 3950. Rest HR 69-71, weight steady 75.1 kg.")
    assert r(d) == "silent_log" and tk(d) == "device_maintenance"
def test_single_stream_rise_with_activity_reported_same_is_ticket():
    d = ev(**{**ACT, "devices": ["watch", "scale"]}, trend_last_7d="Day -6: watch steps 4000; Day -3: 5000; Day 0: 6000. Rest HR 70-72, weight 75.0 kg, unchanged.",
           caregiver_or_nurse_note="Son: Dad is walking the same as always; no idea why the watch counts more.")
    assert r(d) == "silent_log" and tk(d) == "device_maintenance"
def test_firmware_then_step_jump_is_ticket():
    d = ev(**{**ACT, "devices": ["watch", "scale"]}, trend_last_7d="Day -5: app update installed on the watch. Day -6: watch steps 4000; Day -2: 5800; Day 0: 6100. Rest HR 70, weight 75.0 kg, flat.",
           data_quality={"artifact_flags": ["app update installed Day -5"]})
    assert tk(d) == "device_maintenance"
def test_transient_flagged_hr_contradicted_and_fixed_by_strap_is_ticket():
    d = ev(devices=["watch", "ring"], trend_last_7d="Day -6 to -1: rest HR 64-68 bpm. Day 0: at 11:20 watch HR 104 bpm for 4 min while ring HR 66 bpm, motion flag on watch; after strap adjustment watch HR 67 bpm.",
           caregiver_or_nurse_note="Wife: he felt fine; I tightened the strap and it went back to normal.")
    assert r(d) == "silent_log" and tk(d) == "device_maintenance"
# negatives: true clinical change is never ticketed
def test_steps_drop_with_fatigue_and_weight_gain_no_ticket():
    d = ev(**{**ACT, "pmh": ["heart failure"]}, trend_last_7d="Day -6: watch steps 4000, ring steps 3900; Day 0: watch 1800, ring 1700. Weight 75.0 to 77.0 kg, rest HR 70 to 84.",
           caregiver_or_nurse_note="Daughter: she is tired and her ankles are puffy.")
    assert not d.get("device_ticket")
def test_both_devices_drop_together_no_ticket():
    d = ev(**ACT, trend_last_7d="Day -6: watch steps 4000, ring steps 3950; Day -3: watch 3000, ring 2950; Day 0: watch 2200, ring 2150. Rest HR 70, weight 75.0 kg.")
    assert not d.get("device_ticket")
def test_single_stream_drop_caregiver_says_walking_less_no_ticket():
    d = ev(**{**ACT, "devices": ["watch"]}, trend_last_7d="Day -6: watch steps 4000; Day 0: 2200. Rest HR 70, weight 75.0 kg.",
           caregiver_or_nurse_note="Husband: she has been staying in her chair more this week.")
    assert not d.get("device_ticket")
def test_unexplained_single_stream_rise_without_report_no_ticket():
    d = ev(**{**ACT, "devices": ["watch"]}, trend_last_7d="Day -6: watch steps 4000; Day 0: 6200. Rest HR 70, weight 75.0 kg.")
    assert not d.get("device_ticket")
def test_hr_spike_with_palpitations_no_ticket():
    d = ev(devices=["watch", "ring"], trend_last_7d="Day 0: at 11:20 watch HR 104 bpm while ring HR 66 bpm, motion flag on watch; after strap adjustment watch HR 67 bpm.",
           caregiver_or_nurse_note="Wife: he had palpitations and felt dizzy.")
    assert not d.get("device_ticket")
def test_disabled_param_turns_rule_off():
    v = L.T.v110(L.PARAMS)["v1130"]; old = v["enabled"]; v["enabled"] = False
    try:
        d = ev(**ACT, trend_last_7d="Day -6: watch steps 4000, ring steps 3900; Day 0: watch 6400, ring 4050. Rest HR 70, weight 75.0 kg, flat.")
        assert not d.get("device_ticket")
    finally: v["enabled"] = old
def test_sync_failure_adds_ticket_without_changing_route():
    base = dict(trend_last_7d="Day -6 to 0: rest HR 68-72 bpm, wrist SpO2 94-96%, stable.")
    d0 = ev(**base); d = ev(**base, caregiver_or_nurse_note="Daughter: the watch keeps saying sync failed; she feels fine.")
    assert tk(d) == "device_maintenance" and r(d) == r(d0)
def test_resolved_battery_issue_no_ticket():
    d = ev(trend_last_7d="Day -6 to 0: rest HR 68-72 bpm, stable.", caregiver_or_nurse_note="Spouse: the ring had a low battery; he charged it on Day -2.")
    assert not d.get("device_ticket")
def test_scale_blip_adds_ticket():
    d = ev(devices=["watch", "scale"], baseline_30d={"rest_hr": 70, "weight_kg": 70.0}, trend_last_7d="Scale Day -3 70.1 kg, Day -2 73.4 kg, Day -1 70.2 kg, Day 0 70.0 kg. Rest HR 70, stable.")
    assert tk(d) == "device_maintenance"
def test_sustained_weight_gain_is_not_a_scale_blip():
    d = ev(devices=["watch", "scale"], pmh=["heart failure"], baseline_30d={"rest_hr": 70, "weight_kg": 70.0}, trend_last_7d="Scale Day -3 70.1 kg, Day -2 71.0 kg, Day -1 71.9 kg, Day 0 72.6 kg. Rest HR 70.")
    assert not d.get("device_ticket")

import pytest  # noqa: E402
@pytest.fixture(autouse=True)
def _hooks_on(request):
    if not any(k in request.node.name for k in ("sync", "battery", "scale")): yield; return
    v = L.T.v110(L.PARAMS)["v1130"]; old = (v["maintenance_report"], v["scale_blip"]); v["maintenance_report"] = v["scale_blip"] = True
    yield
    v["maintenance_report"], v["scale_blip"] = old
def test_off_by_default_hooks():
    v = L.T.v110(L.PARAMS)["v1130"]
    assert v["enabled"] and not v["maintenance_report"] and not v["scale_blip"] and "PLACEHOLDER" in v["_note"]
