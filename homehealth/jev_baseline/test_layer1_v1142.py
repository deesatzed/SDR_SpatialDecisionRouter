"""SMART_TRIGGERS v1.14.2 human-cause guard (Wayne 2026-10-24, POLICY 2). Hand-written SYNTHETIC vignettes + library cases LX2-006 / LX11-002 only
(never holdout_v3/holdout_v4 text). No API calls."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
from test_layer1_v1141 import B, with_v, tk, r  # noqa: E402
LIB = {"v1": os.path.join(HERE, "..", "library_expansion_v1", "library_expansion_v1_accepted.json"), "v2": os.path.join(HERE, "..", "library_expansion_v2", "library_expansion_v2_accepted.json")}
def lib(cid):
    for f in LIB.values():
        for c in json.load(open(f))["cases"]:
            if c["case_id"] == cid: return c

def test_guard_on_by_default():
    assert L.T.v110(L.PARAMS)["v1141"]["human_cause_guard"]
def test_cuff_fixed_by_seated_repeat_no_ticket():
    d = ev(**B, trend_last_7d="Day -7 to -1 cuff 124-132/76-82. Day 0 08:00 one reading 166/99; repeat 08:12 after the cuff was re-seated and 5 min seated rest 128/80. Rest HR 66-70.",
           caregiver_or_nurse_note="Son: the cuff pinched on the first try; she feels fine.")
    assert tk(d) is None and r(d) in (None, "silent_log")
def test_cuff_error_code_still_ticket_even_with_seated_repeat():
    d = ev(**B, trend_last_7d="Day -7 to -1 cuff 124-132/76-82. Day 0 08:01 cuff error E3 with no number; 08:08 seated repeat 128/79.", caregiver_or_nurse_note="Feels well.")
    assert tk(d) == "device_maintenance"
def test_bag_on_scale_no_ticket():
    d = ev(**B, trend_last_7d="Weights Day -7 70.1 kg, Day -4 70.0, Day -3 15:00 scale reading 9.0 kg, Day -3 15:02 repeat 70.2 kg, Day 0 70.1 kg. Rest HR 68-70.",
           caregiver_or_nurse_note="Daughter put a 9 kg bag of potatoes on the scale to weigh it; patient was not on the scale. She feels fine.")
    assert tk(d) is None and r(d) in (None, "silent_log")
def test_pet_on_scale_no_ticket():
    d = ev(**B, trend_last_7d="Weights Day -7 70.1 kg, Day -4 70.0, Day -3 15:00 scale reading 6.0 kg, Day -3 15:02 repeat 70.2 kg, Day 0 70.1 kg.",
           caregiver_or_nurse_note="Husband: the dog jumped on the scale. She is fine.")
    assert tk(d) is None
def test_impossible_weight_normal_repeat_still_ticket():
    d = ev(**B, trend_last_7d="Weights Day -7 70.1 kg, Day -4 70.0, Day -2 07:00 0.0 kg, Day -2 07:02 70.2 kg, Day 0 70.1 kg. Rest HR 68-70.")
    assert tk(d) == "device_maintenance"
def test_new_scale_offset_still_ticket():
    d = ev(**B, trend_last_7d="Weights Day -7 to -3 70.0-70.3 kg. Day -2 new scale installed, old scale retired. Day -2 to 0 71.8-72.0 kg. Rest HR 68-70, steps flat.",
           caregiver_or_nurse_note="Feels well, no swelling, breathing the same.")
    assert tk(d) in ("device_maintenance", None)   # ticket only if Layer 1 leaves a silent route
    if r(d) in (None, "silent_log"): assert tk(d) == "device_maintenance"
def test_guard_off_restores_v1141():
    t = "Weights Day -7 70.1 kg, Day -4 70.0, Day -3 15:00 scale reading 9.0 kg, Day -3 15:02 repeat 70.2 kg, Day 0 70.1 kg."
    n = "Daughter put a bag of potatoes on the scale; patient was not on the scale."
    assert with_v(lambda: tk(ev(**B, trend_last_7d=t, caregiver_or_nurse_note=n)), human_cause_guard=False) == "device_maintenance"
def test_library_lx2_006_and_lx11_002_no_ticket():
    for cid in ("LX2-006", "LX11-002"):
        c = lib(cid); d = L.evaluate_case(c); rr = L.route(d, None)[0]
        assert L.V141.final_ticket(d, rr or c["expected_route"]) is None, cid
        assert "human/external cause" in d["device_ticket_suppressed"]["why"], cid
def test_zero_reading_with_person_on_scale_keeps_ticket():
    d = ev(**B, trend_last_7d="Weights Day -7 70.1 kg, Day -4 70.0, Day -2 07:00 0.0 kg, Day -2 07:02 70.2 kg, Day 0 70.1 kg.",
           caregiver_or_nurse_note="Wife: grandson stood on the scale holding his backpack, it read zero then normal. He is fine.")
    assert tk(d) == "device_maintenance"   # extra weight cannot read 0 kg: internal fault (library LX11-001)
def test_library_lx11_001_keeps_ticket():
    c = lib("LX11-001"); d = L.evaluate_case(c)
    assert L.V141.final_ticket(d, L.route(d, None)[0] or c["expected_route"])["type"] == "device_maintenance"
