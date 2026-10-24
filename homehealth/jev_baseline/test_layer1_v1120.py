"""SMART_TRIGGERS v1.12.0 Layer 1 generalized wording/matching (Wayne 2026-10-23 rulings as abstract patterns).
Hand-written SYNTHETIC practice vignettes. Never holdout_v3/holdout_v4 text. No API calls. All thresholds PLACEHOLDER."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev, EST  # noqa: E402
def r(d): return L.route(d, None)[0]
LEARN = {"phase": "learning", "monitoring_day": 3, "learning_days_total": 10, "last_condition_change": None}
COPD = dict(pmh=["COPD", "hypertension"], meds=[{"name": "tiotropium", "dose": "18 mcg daily"}], devices=["watch", "fingertip_oximeter"])
DOAC = [{"name": "apixaban", "dose": "5 mg twice daily"}]
ANG = dict(pmh=["stable angina", "hypertension"], meds=[{"name": "GTN spray", "dose": "400 mcg PRN"}, {"name": "bisoprolol", "dose": "2.5 mg daily"}])
CKD = dict(pmh=["type 2 diabetes", "CKD stage 4"], meds=[{"name": "gliclazide", "dose": "80 mg daily"}], devices=["cgm", "glucometer", "watch"])

# 1) device disagreement
def test_stable_hr_disagreement_is_silent_plus_ticket():
    d = ev(devices=["watch", "ring"], trend_last_7d="Day -6 to 0: ring resting HR 64-68 bpm. Day -6 to 0: watch resting HR 78-82 bpm. Steps 2500-3000.",
           caregiver_or_nurse_note="Daughter: she feels her usual self; wonders which gadget is right.")
    assert r(d) == "silent_log" and d["device_ticket"]["type"] == "device_maintenance"
def test_spo2_disagreement_with_pending_o2_decision_is_nurse_plus_ticket():
    d = ev(**COPD, trend_last_7d="Day -4 to 0: watch SpO2 at rest 87-88%. Day -4 to 0: fingertip oximeter at rest 91-92%, good waveform.",
           caregiver_or_nurse_note="Husband: the clinic is deciding about home oxygen next week. She feels her usual self.")
    assert r(d) == "nurse_task" and d.get("device_ticket")
def test_refit_then_trusted_fingertip_is_silent_even_with_pending_decision():
    d = ev(**COPD, trend_last_7d="Day -2 watch strap refitted by the nurse. Day -1 to 0: watch SpO2 at rest 89-90%. Day -1 to 0: fingertip oximeter at rest 94-95%, good waveform.",
           caregiver_or_nurse_note="Husband: oxygen review is pending. She is breathing as usual.")
    assert r(d) == "silent_log" and d.get("device_ticket")

# 2) COPD band
def test_inside_band_with_home_o2_is_silent():
    d = ev(**{**COPD, "pmh": ["COPD", "on home oxygen 2 L/min"]}, patient_goals="Respiratory team: happy if sats stay 86-90% on her home oxygen.",
           trend_last_7d="Day -6 to -1: fingertip SpO2 87-90% at rest. Day 0 10:00 fingertip SpO2 87% at rest, good waveform.", caregiver_or_nurse_note="Son: her usual breathing.")
    assert r(d) == "silent_log"
def test_band_at_88_without_home_o2_is_provider_not_urgent():
    d = ev(**COPD, patient_goals="Target saturations 85-88% per respiratory clinic; home oxygen not prescribed.",
           trend_last_7d="Day -6 to -1: fingertip SpO2 86-88% at rest. Day 0 10:00 fingertip SpO2 86% at rest, good waveform.", caregiver_or_nurse_note="Son: her usual breathing.")
    assert r(d) == "provider_task"

# 3) learning period
def test_learning_87_without_recheck_is_urgent():
    # Wayne ruling 2026-10-24: rule dropped; learning-period 85-87% with no recheck pages urgent (ST3-001-like synthetic vignette)
    d = ev(**{**COPD, "devices": ["ring"]}, baseline_status=LEARN, trend_last_7d="Ring rest SpO2 87-89% Day -2 to -1. Day 0 09:00 ring rest SpO2 87%, no motion flag.",
           caregiver_or_nurse_note="Wife: usual morning cough.")
    assert r(d) == "urgent_page"
def test_learning_85_without_recheck_is_urgent():
    d = ev(**{**COPD, "devices": ["watch"]}, baseline_status={**LEARN, "monitoring_day": 4}, trend_last_7d="Day -3 to -1: watch rest SpO2 88-90%. Day 0 07:30 watch rest SpO2 85%, no motion flag.",
           caregiver_or_nurse_note="Husband: she seems her usual self.")
    assert r(d) == "urgent_page"
def test_learning_spo2_param_is_disabled():
    assert L.T.v110(L.PARAMS)["v1120"]["learning_spo2_low"] >= 88

# 4) anticoagulant falls
def test_heavy_sit_on_doac_no_pain_is_nurse():
    d = ev(age_band="80-84", meds=DOAC, pmh=["atrial fibrillation"], trend_last_7d="Day 0 15:10 watch impact detected. Steps 2000-2400.",
           caregiver_or_nurse_note="Husband saw her sit down heavily on the sofa edge; she did not hit her head and has no pain.")
    assert r(d) == "nurse_task"
def test_unwitnessed_probable_fall_age_85_on_doac_is_provider():
    d = ev(age_band="85-89", living="alone", meds=DOAC, pmh=["atrial fibrillation"], trend_last_7d="Day 0 06:40 watch impact detected; no one present. Steps 1500 later.",
           caregiver_or_nurse_note="She thinks she may have slipped by the bed but is not sure; no head strike, no pain.")
    assert r(d) == "provider_task"

# 5) stable angina
def test_unchanged_angina_with_usual_gtn_is_nurse():
    d = ev(**ANG, trend_last_7d="Day -5 and Day -1 brief chest tightness on the stairs, eased within 4 min with one spray as usual. Day 0 rest HR 64.",
           caregiver_or_nurse_note="He says the pattern is the same as usual and the spray works as always.")
    assert r(d) == "nurse_task"
def test_angina_episode_of_20_minutes_is_urgent():
    d = ev(**ANG, trend_last_7d="Day 0 chest tightness at the sink lasting about 20 min, eased slowly. Day 0 rest HR 76.",
           caregiver_or_nurse_note="Wife: it took longer than his usual ones.")
    assert r(d) == "urgent_page"
def test_activity_minutes_are_not_episode_minutes():
    d = ev(**ANG, trend_last_7d="Day 0 walked on the flat for about 20 min, then brief chest tightness, eased within 3 min with rest as usual.",
           caregiver_or_nurse_note="He says it is the same as always.")
    assert r(d) != "urgent_page"

# 6) CKD exertion low
def test_ckd_low_after_digging_is_nurse_even_after_food_recheck():
    d = ev(**CKD, baseline_status=EST, trend_last_7d="Day -6 to -1: CGM minimum 96-120 mg/dL. Day 0 14:00-15:00 digging the vegetable plot. Day 0 15:20 CGM 52 mg/dL; meter 101 mg/dL at 15:50 after a biscuit.",
           caregiver_or_nurse_note="Wife: he feels fine.")
    assert r(d) == "nurse_task"

# 7) motion-flagged BP cleared by clean repeat
def test_motion_flagged_bp_cleared_by_repeat_is_silent():
    d = ev(devices=["bp_cuff", "watch"], trend_last_7d="Day -6 to -1: cuff 126-134/74-80. Day 0 09:00 cuff 182/96 with motion flag. Day 0 09:08 cuff 130/78, seated, no flag.",
           caregiver_or_nurse_note="Husband: she was talking and moving her arm on the first one.")
    assert r(d) == "silent_log"

# guard: device disagreement never silences symptoms or out-of-range readings
def test_device_disagreement_with_symptoms_is_not_silenced():
    d = ev(devices=["cgm", "glucometer"], pmh=["type 2 diabetes"], trend_last_7d="Day 0: CGM 150-170 mg/dL; glucometer 190 mg/dL at 08:00. Watch resting HR 104 bpm.",
           caregiver_or_nurse_note="Son: she has vomited twice and is nauseous.")
    assert r(d) != "silent_log"
def test_v1120_params_are_placeholders():
    V = L.T.v110(L.PARAMS)["v1120"]
    assert L.PARAMS["version"].endswith("-placeholder") and V["enabled"] and "PLACEHOLDER" in V["_note"]
