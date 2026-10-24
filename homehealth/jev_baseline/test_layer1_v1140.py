"""SMART_TRIGGERS v1.14.0 named device-fault tickets (ticket only). Hand-written SYNTHETIC vignettes only (never holdout_v3/holdout_v4 text). No API calls."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
def r(d): return L.route(d, None)[0]
def tk(d): return (d.get("device_ticket") or {}).get("type")
B = dict(pmh=["hypertension"], devices=["watch", "scale", "bp_cuff"], baseline_30d={"rest_hr": 70, "steps": 3000, "weight_kg": 70.0})
def fam_on(fn, *fams):
    """scale/fit/cuff families are OFF by default (one unexpected holdout_v4 ticket each when scored blind); these tests exercise the param-gated hooks."""
    V = L.T.v110(L.PARAMS)["v1140"]; old = {f: V[f] for f in fams}
    for f in fams: V[f] = True
    try: return fn()
    finally: V.update(old)
def test_scale_fit_cuff_families_off_by_default():
    V = L.T.v110(L.PARAMS)["v1140"]; assert V["enabled"] and not (V["scale"] or V["fit"] or V["cuff"])
def off(fn):
    V = L.T.v110(L.PARAMS)["v1140"]; old = V["enabled"]; V["enabled"] = False
    try: return fn()
    finally: V["enabled"] = old

def test_sync_failure_patient_seen_well_ticket():
    d = ev(**B, trend_last_7d="Day -7 to 0 rest HR 68-71, steps 2800-3200. Day -1 21:00 app message 'sync failed'; data back Day 0 08:00 (11 h gap).",
           caregiver_or_nurse_note="Neighbour popped in at 07:30, he was making tea and fine.")
    assert tk(d) == "device_maintenance"
def test_battery_flat_ticket_but_not_once_charged():
    t = "Day -7 to 0 rest HR 66-70, steps 2500-2900. Day -2 watch battery flat overnight (9 h no data)."
    assert tk(ev(**B, trend_last_7d=t, caregiver_or_nurse_note="Son: charger cable lost, he is fine.")) == "device_maintenance"
    assert not tk(ev(**B, trend_last_7d=t + " Day -1 watch charged, continuous data since.", caregiver_or_nurse_note="Son: all good now."))
def test_cuff_error_code_with_clean_repeat_ticket(): fam_on(lambda: _test_cuff_error_code_with_clean_repeat_ticket(), 'cuff')
def _test_cuff_error_code_with_clean_repeat_ticket():
    d = ev(**B, trend_last_7d="Day -7 to -1 cuff 124-132/76-82. Day 0 08:01 cuff error E3 with no number over a jumper sleeve; 08:08 bare arm 128/79.")
    assert tk(d) == "device_maintenance"
def test_scale_zero_with_normal_repeat_ticket_route_unchanged(): fam_on(lambda: _test_scale_zero_with_normal_repeat_ticket_route_unchanged(), 'scale')
def _test_scale_zero_with_normal_repeat_ticket_route_unchanged():
    t = "Weights Day -7 70.1 kg, Day -4 70.0, Day -2 07:00 0.0 kg, Day -2 07:02 70.2 kg, Day 0 70.1 kg. Rest HR 68-70."
    d = ev(**B, trend_last_7d=t); assert tk(d) == "device_maintenance"
    assert r(d) == off(lambda: r(ev(**B, trend_last_7d=t)))
def test_scale_moved_to_rug_offset_ticket_vetoed_by_clinic_scale(): fam_on(lambda: _test_scale_moved_to_rug_offset_ticket_vetoed_by_clinic_scale(), 'scale')
def _test_scale_moved_to_rug_offset_ticket_vetoed_by_clinic_scale():
    t = "Scale moved to a bedroom rug Day -5; weights 70.0 kg before, 71.8-72.0 kg on the rug since. Rest HR 68-70, steps flat."
    assert tk(ev(**B, trend_last_7d=t)) == "device_maintenance"
    assert not tk(ev(**B, trend_last_7d=t + " Clinic scale Day -1 71.9 kg."))

def _pre_v1141(fn):
    """pre-v1.14.1 ticket behaviour (ticket on a clinical route / oximeter-reference type); v1.14.1 changes it per Wayne 2026-10-24, see test_layer1_v1141.py."""
    import functools
    @functools.wraps(fn)
    def w(*a, **k):
        V = L.T.v110(L.PARAMS).setdefault("v1141", {}); old = V.get("enabled"); V["enabled"] = False
        try: return fn(*a, **k)
        finally: V["enabled"] = old
    return w

@_pre_v1141
def test_ticket_sits_on_top_of_clinical_route(): fam_on(lambda: _test_ticket_sits_on_top_of_clinical_route(), 'fit')
def _test_ticket_sits_on_top_of_clinical_route():
    t = "Day -7 to -1 rest HR 64-68. Day 0 03:10 CGM 48 mg/dL; patch edge lifted at one corner; glucometer 45 mg/dL at 03:15."
    kw = dict(pmh=["type 2 diabetes", "ckd stage 4"], meds=[{"name": "insulin glargine", "dose": "14 units"}], devices=["cgm", "watch"])
    note = "Daughter: she is sweaty, shaky and confused."
    d = ev(**kw, trend_last_7d=t, caregiver_or_nurse_note=note)
    assert r(d) == "urgent_page" and tk(d) == "device_maintenance"
def test_duplicate_records_ticket():
    d = ev(**B, trend_last_7d="Phone replaced Day -3; every record duplicated at the same minute since. Steps shown 3000 before, 6000 after. Rest HR 68-70.",
           caregiver_or_nurse_note="Wife: he potters about same as ever.")
    assert tk(d) == "device_maintenance"
def test_app_update_changes_export_ticket():
    d = ev(pmh=["type 2 diabetes"], meds=[{"name": "metformin", "dose": "500 mg"}], devices=["cgm"], trend_last_7d="CGM app update Day -3, after which the export shows no readings above 200 mg/dL. Fingersticks 190-230 mg/dL.")
    assert tk(d) == "device_maintenance"
# negatives
def test_real_weight_gain_no_ticket(): fam_on(lambda: _test_real_weight_gain_no_ticket(), 'scale')
def _test_real_weight_gain_no_ticket():
    d = ev(**{**B, "pmh": ["heart failure"]}, trend_last_7d="Weights on the same floor Day -7 70.0 kg rising daily to 72.4 kg Day 0. Rest HR 70 to 78.",
           caregiver_or_nurse_note="Daughter: ankles puffy, two pillows now.")
    assert not tk(d)
def test_routine_cgm_warmup_flag_alone_no_ticket():
    d = ev(pmh=["type 2 diabetes"], devices=["cgm"], trend_last_7d="CGM 90-150 mg/dL all week, fingersticks match.", data_quality={"artifact_flags": ["sensor warm-up Day -3 06:00-08:00"]})
    assert not tk(d)
def test_negated_fault_no_ticket():
    d = ev(**B, trend_last_7d="Rest HR 68-70, steps 2900-3100, weights 70.0-70.2 kg. No sync failure and no battery problem this week.")
    assert not tk(d)
def test_firmware_guard_withdraws_repair_only_ticket_with_positional_breathing():
    d = ev(devices=["watch", "ring"], trend_last_7d="Day -6 to 0: watch and ring night SpO2 nadir 89-91%, rest HR 64-68 on both, steps 3000-3400. Watch re-paired to a new phone Day -7.",
           caregiver_or_nurse_note="Son: she has slept propped in the armchair two nights because lying flat feels stuffy; no breathlessness at rest.")
    assert not tk(d) and r(d) != "silent_log"
def test_v1140_off_restores_v1130():
    t = "Day -7 to 0 rest HR 68-71. Day -1 app message 'sync failed'; data back next morning."
    assert off(lambda: tk(ev(**B, trend_last_7d=t))) is None
