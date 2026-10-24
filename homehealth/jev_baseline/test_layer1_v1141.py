"""SMART_TRIGGERS v1.14.1 device-ticket policy (Wayne 2026-10-24). Hand-written SYNTHETIC vignettes only (never holdout_v3/holdout_v4 text). No API calls."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
def r(d): return L.route(d, None)[0]
def tk(d): return (d.get("device_ticket") or {}).get("type")
B = dict(pmh=["hypertension"], devices=["watch", "scale", "bp_cuff"], baseline_30d={"rest_hr": 70, "steps": 3000, "weight_kg": 70.0})
def v1141(**kw):
    V = L.T.v110(L.PARAMS)["v1141"]; old = dict(V); V.update(kw); return V, old
def with_v(fn, **kw):
    V, old = v1141(**kw)
    try: return fn()
    finally: V.clear(); V.update(old)

def test_params_defaults():
    V = L.T.v110(L.PARAMS)["v1141"]
    assert V["enabled"] and V["suppress_on_clinical_route"] and V["warmup_no_ticket"] and V["cuff_error"] and V["scale_internal"] and V["spo2_flag_vs_fingertip"] and V["spo2_contact_rest_only"]
    W = L.T.v110(L.PARAMS)["v1140"]; assert not (W["fit"] or W["cuff"] or W["scale"])
def test_policy1_no_ticket_on_urgent_route_but_kept_for_audit():
    kw = dict(pmh=["type 2 diabetes"], meds=[{"name": "insulin glargine", "dose": "20 units", "started_day": -400}], devices=["cgm", "glucometer", "watch"], baseline_30d={"rest_hr": 72, "glucose_mean": 140})
    t = "Day -1 CGM sync failed overnight (8 h gap). Day 0 07:10 glucometer 48 mg/dL, repeat 07:20 46 mg/dL."
    d = ev(**kw, trend_last_7d=t, caregiver_or_nurse_note="Wife: he is sweaty and muddled.")
    assert r(d) == "urgent_page" and tk(d) is None and d["device_ticket_suppressed"]["why"].startswith("POLICY 1")
    d0 = with_v(lambda: ev(**kw, trend_last_7d=t, caregiver_or_nurse_note="Wife: he is sweaty and muddled."), enabled=False)
    assert r(d0) == "urgent_page" and tk(d0) == "device_maintenance"
def test_policy1_jev_routed_ticket_is_conditional_on_silent_log():
    d = {"device_ticket": {"type": "device_maintenance", "ticket_if_route": "silent_log"}}
    assert L.V141.final_ticket(d, "silent_log")["type"] == "device_maintenance"
    for rr in ("nurse_task", "provider_task", "urgent_page"): assert L.V141.final_ticket(d, rr) is None
def test_sync_failure_stable_patient_still_ticketed():
    d = ev(**B, trend_last_7d="Day -7 to 0 rest HR 68-71, steps 2800-3200. Day -1 21:00 app message 'sync failed'; data back Day 0 08:00 (11 h gap).",
           caregiver_or_nurse_note="Neighbour popped in at 07:30, he was making tea and fine.")
    assert tk(d) == "device_maintenance"
def test_cgm_warmup_single_artifact_no_ticket():
    kw = dict(pmh=["prediabetes"], devices=["cgm", "glucometer"], baseline_30d={"rest_hr": 70, "glucose_mean": 110})
    d = ev(**kw, trend_last_7d="CGM means 105-115. Day 0 new sensor applied 07:00, warm-up until 09:00; CGM 08:10 reading 52 mg/dL; glucometer 08:15 reading 112 mg/dL; CGM 09:30 108 mg/dL.",
           caregiver_or_nurse_note="Husband: she feels normal and is eating breakfast.")
    assert tk(d) is None
def test_expired_cgm_sensor_ticket():
    kw = dict(pmh=["type 2 diabetes"], devices=["cgm", "glucometer"], baseline_30d={"rest_hr": 70, "glucose_mean": 120})
    d = ev(**kw, trend_last_7d="CGM daily means Day -5 121 rising to Day 0 150 mg/dL; fasting glucometer 118-124 mg/dL. Device flag Day -1: sensor past 14-day wear limit.",
           caregiver_or_nurse_note="Patient says the app warns the sensor is over time; she feels fine.")
    assert tk(d) == "device_maintenance" and r(d) in (None, "silent_log")
def test_cuff_error_code_internal_fault_ticket_but_wrong_cuff_size_no_ticket():
    d = ev(**B, trend_last_7d="Day -7 to -1 cuff 124-132/76-82. Day 0 08:01 cuff error E3 with no number; 08:08 repeat 128/79.", caregiver_or_nurse_note="Feels well.")
    assert tk(d) == "device_maintenance"
    d2 = ev(**B, trend_last_7d="Day -7 to -1 cuff 124-132/76-82. Day 0 08:01 98/60 with a too-large cuff on her thin arm; 08:10 correct cuff 127/80.", caregiver_or_nurse_note="Feels well.")
    assert tk(d2) is None   # POLICY 2: human cause (wrong cuff size)
def test_scale_impossible_weight_ticket_but_object_on_scale_no_ticket():
    d = ev(**B, trend_last_7d="Weights Day -7 70.1 kg, Day -4 70.0, Day -2 07:00 0.0 kg, Day -2 07:02 70.2 kg, Day 0 70.1 kg. Rest HR 68-70.")
    assert tk(d) == "device_maintenance"
    d2 = ev(**B, trend_last_7d="Weights Day -7 70.1 kg, Day -4 70.0, Day -2 07:00 79.4 kg with a shopping bag on the scale, Day -2 07:03 70.2 kg, Day 0 70.1 kg. Rest HR 68-70.")
    assert tk(d2) is None
def test_loose_strap_human_cause_no_ticket():
    d = ev(**B, trend_last_7d="Day -7 to -3 night HR 52-60. Day -2 new watch strap, sits loose. Day -1 night HR 112-120 with motion flags; daytime HR 66.", caregiver_or_nurse_note="Spouse: watch turns round on her wrist; she feels fine.")
    # the v1.14 fit family (human cause) stays OFF; a v1.13 artifact/refit ticket can still fire - open POLICY 2 question for Wayne (library LX10-001)
    assert (d.get("device_ticket") or {}).get("rule") != "v1140"
def test_oximeter_reference_ticket_type_is_device_maintenance():
    d = {"device_ticket": {"type": "supply_reference_oximeter_and_baseline"}}
    V = L.T.v110(L.PARAMS)["v1141"]
    out = L.V141.apply({}, {**d, "owned_route": "silent_log", "tier": "SUPPRESSED", "reason": "device_disagreement", "default_route": "silent_log"}, L, L.T, L.PARAMS, L.V14)
    assert V["oximeter_as_maintenance"] and out["device_ticket"]["type"] == "device_maintenance"
def test_v1141_off_restores_v1140():
    t = "Day -7 to 0 rest HR 66-70, steps 2500-2900. Day -2 watch battery flat overnight (9 h no data)."
    a = ev(**B, trend_last_7d=t, caregiver_or_nurse_note="Son: charger cable lost, he is fine.")
    b = with_v(lambda: ev(**B, trend_last_7d=t, caregiver_or_nurse_note="Son: charger cable lost, he is fine."), enabled=False)
    assert tk(a) == tk(b) == "device_maintenance" and r(a) == r(b)
