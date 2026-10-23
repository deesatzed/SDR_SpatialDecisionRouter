"""SMART_TRIGGERS v1.10.2 Layer 1 fixes (Wayne 2026-10-23). Hand-written SYNTHETIC practice cases (not holdout text). No API calls."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import case, ev  # noqa: E402
AC = [{"name": "edoxaban", "dose": "30 mg daily"}]

# 1. witnessed fall is not cleared by reassurance
def test_witnessed_fall_on_anticoag_not_cleared_by_reassurance():
    d = ev(meds=AC, trend_last_7d="Day -6 to -1: steps 3000-3400. Day 0 10:15 watch impact; HR 80 bpm.",
           caregiver_or_nurse_note="Neighbour: I saw him fall on the garden path. He got up and says he is fine and walking normally.")
    assert d["tier"] == "ABSOLUTE" and L.route(d, "silent_log")[0] == "urgent_page"
def test_unwitnessed_caregiver_check_still_nurse_task():
    d = ev(meds=AC, trend_last_7d="Day 0 15:02 watch impact; HR 76 bpm.", caregiver_or_nurse_note="Son checked on her a few minutes later; she was sitting knitting and says she did not fall.")
    assert d["reason"] == "explained_caregiver_check" and L.route(d, "silent_log")[0] == "nurse_task"

# 2. pain after a fall escalates, even off anticoagulant
def test_pain_after_fall_off_anticoag_pages():
    d = ev(trend_last_7d="Day 0 07:20 watch impact; steps 0 since.", caregiver_or_nurse_note="Husband: she fell getting out of the car and can't bear weight on the left leg.")
    assert d["rule"] == "HT_FALL_PAIN" and d["tier"] == "ABSOLUTE" and L.route(d, None)[0] == "urgent_page"
def test_pain_after_witnessed_slide_pages():
    d = ev(caregiver_or_nurse_note="Daughter watched it happen: he slid off the sofa arm onto the rug and is holding his wrist.")
    assert d["rule"] == "HT_FALL_PAIN"
def test_no_pain_after_fall_off_anticoag_no_page():
    d = ev(caregiver_or_nurse_note="Wife: he fell onto the bed while dressing, no pain, walking about as usual.")
    assert d.get("rule") != "HT_FALL_PAIN"
def test_chronic_pain_without_fall_does_not_fire():
    d = ev(pmh=["osteoarthritis"], caregiver_or_nurse_note="Her knee hurts as it always does after the shopping trip.")
    assert d.get("rule") != "HT_FALL_PAIN"
def test_pain_after_fall_hospice_goes_to_goals_of_care():
    d = ev(patient_goals="hospice, comfort only, no hospital transfer", caregiver_or_nurse_note="Aide: she fell beside the bed and is holding her hip.")
    assert d["rule"] == "HT_FALL_PAIN" and d["reason"] == "goals_of_care" and L.route(d, None)[0] == "nurse_task"

# 3. off-wrist/charging does not suppress a possible fall on an anticoagulant
def test_offwrist_possible_fall_on_anticoag_floor_nurse_task():
    d = ev(meds=AC, trend_last_7d="Day 0 21:40 watch impact, then off-wrist from 21:41.", caregiver_or_nurse_note="")
    assert d["reason"] == "possible_fall_unverified"
    assert L.route(d, None)[0] == "nurse_task" and L.route(d, "silent_log")[0] == "nurse_task"

# 4. on-wrist impact + inactivity on an anticoagulant, explained away
def test_onwrist_impact_inactivity_explained_still_fires():
    d = ev(meds=AC, trend_last_7d="Day -6 to -2: steps 2500-3000. Day -1 11:05 watch impact, on-wrist; no steps for 25 min afterwards. Day 0 HR 72 bpm.",
           caregiver_or_nurse_note="Patient on the phone: the noise was just the watch knocking the cupboard door.")
    assert d["rule"] == "HT_FALL_ANTICOAG" and d["reason"] == "possible_fall_unverified" and L.route(d, "silent_log")[0] == "nurse_task"
def test_impact_brief_pause_explained_stays_suppressed_explained():
    d = ev(meds=AC, trend_last_7d="Day 0 11:05 watch impact, on-wrist; no steps for 3 min. ", caregiver_or_nurse_note="She knocked the watch on the sink; she caught herself and kept washing up.")
    assert d["reason"] == "explained"
def test_impact_inactivity_off_anticoag_no_fall_trigger():
    d = ev(trend_last_7d="Day 0 11:05 watch impact, on-wrist; no steps for 30 min.", caregiver_or_nurse_note="He says he banged the watch on the door frame and then read the paper.")
    assert d.get("rule") not in ("HT_FALL_ANTICOAG", "HT_FALL_PAIN")

# 5. candidate: confirmed SpO2 <= 90 + rest dyspnea in HF/COPD
def test_copd_confirmed_spo2_90_rest_dyspnea_pages():
    d = ev(pmh=["COPD GOLD 2"], trend_last_7d="Day -6 to -1: fingertip SpO2 93-95% at rest. Day 0 09:00 fingertip SpO2 90% seated, good signal. Day 0 09:04 fingertip SpO2 89% seated, good signal.",
           caregiver_or_nurse_note="Wife: he can only manage a few words at a time sitting in his chair.")
    assert d["rule"] == "HT_SPO2_REST_DYSPNEA" and L.route(d, None)[0] == "urgent_page"
def test_spo2_90_without_rest_dyspnea_no_fire():
    d = ev(pmh=["heart failure"], trend_last_7d="Day 0 09:00 fingertip SpO2 90% seated. Day 0 09:04 fingertip SpO2 90% seated.",
           caregiver_or_nurse_note="Feels well, short of breath only on the stairs as usual.")
    assert d.get("rule") != "HT_SPO2_REST_DYSPNEA"
def test_spo2_rest_dyspnea_single_reading_no_fire():
    d = ev(pmh=["heart failure"], trend_last_7d="Day 0 09:00 wrist SpO2 90% seated.", caregiver_or_nurse_note="Breathless sitting in the chair.")
    assert d.get("rule") != "HT_SPO2_REST_DYSPNEA"
def test_spo2_rest_dyspnea_no_hf_copd_no_fire():
    d = ev(trend_last_7d="Day 0 09:00 fingertip SpO2 90% seated. Day 0 09:04 fingertip SpO2 89% seated.", caregiver_or_nurse_note="Breathless sitting in the chair.")
    assert d.get("rule") != "HT_SPO2_REST_DYSPNEA"
def test_spo2_rest_dyspnea_hospice_excluded():
    d = ev(pmh=["COPD"], patient_goals="hospice, comfort only", trend_last_7d="Day 0 09:00 fingertip SpO2 89% at rest. Day 0 09:03 fingertip SpO2 89% at rest.",
           caregiver_or_nurse_note="Breathless at rest, as she has been all week.")
    assert d.get("rule") != "HT_SPO2_REST_DYSPNEA"
