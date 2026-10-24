"""SMART_TRIGGERS v1.14.3 (Wayne 2026-10-24): the syncope synonym 'out cold' must be word-bounded so 'about cold fingers' is not fainting.
Hand-written SYNTHETIC vignettes + library LX10-002 only (never holdout_v3/holdout_v4 text). No API calls."""
import json, os, sys, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
from test_layer1_v1141 import r  # noqa: E402
LIB2 = os.path.join(HERE, "..", "library_expansion_v2", "library_expansion_v2_accepted.json")
B = dict(pmh=["hypertension"], devices=["watch", "fingertip_oximeter"], baseline_30d={"rest_hr": 70, "steps": 3000, "spo2_night_min": 93})
def syn(): return L.T.wording_rx(L.PARAMS, "syncope", r"(?!x)x")
def test_params_version():
    assert L.PARAMS["version"] == "0.14.3-placeholder"
    assert r"\bout cold\b" in L.T.v110(L.PARAMS)["wording"]["syncope"]
def test_about_cold_is_not_syncope():
    for t in ("He says the clip meter is fussy about cold fingers.", "She worries about cold hands in winter.", "Reading taken without cold gloves; worried about cold weather."):
        assert not re.search(syn(), t, re.I), t
def test_out_cold_still_syncope():
    for t in ("He was out cold for a minute on the floor.", "Found her out cold in the chair."):
        assert re.search(syn(), t, re.I), t
def test_cold_fingers_vignette_no_page():
    d = ev(**B, trend_last_7d="Day -7 to -1 watch SpO2 94-96%, resting HR 68-72. Day 0 watch 95% at 09:30; fingertip 91% at 09:32 after coming in from the cold; fingertip on a warmed finger at 09:40 reads 96%.",
           caregiver_or_nurse_note="Wife: he feels fine, no breathlessness. He grumbles about cold fingers making the clip meter read low.")
    assert d.get("rule") != "HT_SYNCOPE" and r(d) != "urgent_page"
def test_real_collapse_still_pages():
    d = ev(**B, trend_last_7d="Day -7 to -1 watch SpO2 94-96%, resting HR 68-72. Day 0 08:10 resting HR 70.", caregiver_or_nurse_note="Wife: he was out cold on the kitchen floor for about a minute this morning.")
    assert d.get("rule") == "HT_SYNCOPE" and r(d) == "urgent_page"
def test_lx10_002_no_false_fainting_page():
    c = next(c for c in json.load(open(LIB2))["cases"] if c["case_id"] == "LX10-002")
    d = L.evaluate_case(c)
    assert d.get("rule") != "HT_SYNCOPE" and L.route(d, None)[0] in (None, "silent_log", "nurse_task")
    assert c["expected_route"] == "silent_log" and c["expected_device_ticket"] == "device_maintenance"
