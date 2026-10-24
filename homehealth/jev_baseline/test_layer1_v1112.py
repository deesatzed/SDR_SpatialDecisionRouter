"""SMART_TRIGGERS v1.11.2 (Wayne 2026-10-23). Hand-written SYNTHETIC practice vignettes (never holdout text). No API calls."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L, dual_jev as D  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
AC = [{"name": "apixaban", "dose": "5 mg BID"}]

# 1) Layer 1 owns device-disagreement routes when there are no acute signs
def test_device_disagreement_silent_ticket_not_raised_by_jev():
    d = ev(devices=["watch", "ring"], trend_last_7d="Day -5 to 0: the watch rest HR reads 51-55 but the ring rest HR remained 66-69 every day; she feels well.")
    assert d["rule"] == "HT_DEVICE_DISAGREE" and D.dual_route(d, "provider_task", "urgent_page", "cautious_max_hitm")[0] == "silent_log"

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
def test_device_disagreement_could_change_care_stays_nurse_with_jev():
    d = ev(meds=[{"name": "bisoprolol", "dose": "5 mg daily"}], devices=["watch", "ring"], recent_med_changes=[{"name": "bisoprolol", "change": "dose_increased", "day": -6}],
           trend_last_7d="Day -5 to 0: since the bisoprolol increase the watch rest HR reads 46-49 but the ring rest HR remained 60-63; no light-headedness.")
    assert D.dual_route(d, "provider_task", "silent_log", "cautious_max_hitm")[0] == "nurse_task" and d["device_ticket"]
def test_rhythm_disagreement_stays_silent_with_jev_provider():
    d = ev(pmh=["paroxysmal atrial fibrillation"], meds=[{"name": "rivaroxaban", "dose": "20 mg daily"}], devices=["watch", "ring"],
           trend_last_7d="Day -3 to 0: the watch flagged an irregular rhythm twice while the ring reads a regular 70 bpm throughout; no palpitations.")
    assert D.dual_route(d, "provider_task", "nurse_task", "cautious_max_hitm")[0] == "silent_log"
def test_acute_patient_device_disagreement_not_owned():
    d = {"rule": "HT_DEVICE_DISAGREE", "tier": "SUPPRESSED", "reason": "device_disagreement", "default_route": "silent_log", "acute_presentation": True}
    assert L.route(d, "provider_task")[0] == "provider_task"

# 2) explained impact on an anticoagulant floors at nurse_task
def test_explained_impact_on_anticoag_floors_nurse():
    d = ev(meds=AC, trend_last_7d="Day 0 19:40 watch impact, on-wrist; no steps for 2 min. Day 0 rest HR 70.",
           caregiver_or_nurse_note="Husband: she knocked the watch on the kettle; she caught herself and kept making the tea.")
    assert d["rule"] == "HT_FALL_ANTICOAG" and d["reason"] == "explained" and L.route(d, "silent_log")[0] == "nurse_task"
    assert D.dual_route(d, "silent_log", "silent_log", "cautious_max_hitm")[0] == "nurse_task"
