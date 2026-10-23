"""SMART_TRIGGERS v1.11.1 Layer 1 fixes (Wayne 2026-10-23 rulings). Hand-written SYNTHETIC practice vignettes (never holdout text). No API calls."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
SU = [{"name": "gliclazide", "dose": "80 mg daily"}]; INS = [{"name": "insulin degludec", "dose": "14 units daily"}]
CKD = dict(pmh=["type 2 diabetes", "CKD stage 4"], devices=["cgm", "glucometer", "watch"])
def r(d): return L.route(d, None)[0]

# 1) CKD low explained by sensor compression -> nurse_task (check placement), not a dose review
def test_ckd_low_compression_by_witness_is_nurse():
    d = ev(meds=INS, trend_last_7d="Day -6 to -1: CGM overnight lows 95-112 mg/dL. Day 0 01:30 CGM 48 mg/dL; meter 104 mg/dL at 01:45.",
           caregiver_or_nurse_note="Daughter: she slept curled on her right side all night and the sensor is on her right arm; she woke normally and feels fine.", **CKD)
    assert d["reason"] == "ckd_low_compression_explained" and r(d) == "nurse_task" and "sensor placement" in d["plain_reason"]
def test_ckd_low_compression_by_artifact_flag_is_nurse():
    d = ev(meds=SU, trend_last_7d="Day -6 to -1: CGM minimum 98-115 mg/dL. Day 0 04:00 CGM 50 mg/dL; meter 97 mg/dL at 04:12.",
           caregiver_or_nurse_note="Husband: he said he felt fine.", data_quality={"artifact_flags": ["sensor-side lying 01:00-05:00 Day 0"], "wear_time_pct_7d": 95, "longest_gap_h": 1}, **CKD)
    assert d["reason"] == "ckd_low_compression_explained" and r(d) == "nurse_task"
# 2) CKD low after exertion -> nurse_task (exercise teaching); a repeat -> provider
EX = "Day 0 15:00-16:10 mowing the back lawn. Day 0 16:20 CGM 52 mg/dL; meter 102 mg/dL at 16:40."
def test_ckd_low_after_exertion_is_nurse_teaching():
    d = ev(meds=INS, trend_last_7d="Day -6 to -1: CGM daily minimum 96-118 mg/dL. " + EX, caregiver_or_nurse_note="Wife: he had a juice and said he felt fine, no shakes.", **CKD)
    assert d["reason"] == "ckd_low_exertion_explained" and r(d) == "nurse_task" and "exercise" in d["plain_reason"]
def test_repeat_exertion_low_goes_to_provider():
    d = ev(meds=INS, trend_last_7d="Day -6 to -4: CGM minimum 96-118 mg/dL. Day -3 11:00 CGM 50 mg/dL after a walk, meter 95 mg/dL. " + EX, caregiver_or_nurse_note="Wife: he said he felt fine, no shakes.", **CKD)
    assert d["reason"] == "repeated_lows_dose_review" and r(d) == "provider_task"
def test_unexplained_ckd_low_still_dose_review():
    d = ev(meds=SU, trend_last_7d="Day -6 to -1: CGM minimum 98-112 mg/dL. Day 0 03:20 CGM 49 mg/dL; meter 99 mg/dL at 03:35.", caregiver_or_nurse_note="Son: she slept on her back and felt well this morning.", **CKD)
    assert d["reason"] == "ckd_low_dose_review" and r(d) == "provider_task"
def test_symptomatic_explained_low_still_pages():
    d = ev(meds=INS, trend_last_7d="Day -6 to -1: CGM minimum 96-118 mg/dL. Day 0 15:00-16:10 mowing the lawn. Day 0 16:20 CGM 44 mg/dL; meter 47 mg/dL at 16:25.",
           caregiver_or_nurse_note="Wife: he was sweaty and confused, gave him juice.", **CKD)
    assert d["rule"] == "HT_DRUG_LOW" and r(d) == "urgent_page"

# 3) COPD in-band without home oxygen -> provider (evaluate for home oxygen); with oxygen -> silent
COPD = dict(devices=["watch", "fingertip_oximeter"], baseline_30d={"rest_hr": 80, "spo2_night_min": 82})
T3 = "Day -6 to -1: wrist SpO2 84-86% at rest. Day 0 09:40 fingertip SpO2 85% seated, clean trace."
N3 = "Visit: pulmonology clinic note documented his usual resting SpO2 as 84-86%. Wife: breathing as usual."
def test_copd_band_without_oxygen_is_provider():
    d = ev(pmh=["COPD GOLD 3", "hypertension"], meds=[{"name": "umeclidinium", "dose": "62.5 mcg daily"}], trend_last_7d=T3, caregiver_or_nurse_note=N3, **COPD)
    assert d["reason"] == "within_band_low_no_home_o2" and r(d) == "provider_task" and "home oxygen" in d["plain_reason"]
def test_copd_band_with_oxygen_stays_silent():
    d = ev(pmh=["COPD GOLD 3", "home oxygen 1.5 L/min"], meds=[{"name": "umeclidinium", "dose": "62.5 mcg daily"}], trend_last_7d=T3, caregiver_or_nurse_note=N3, **COPD)
    assert d["reason"] == "within_patient_band" and r(d) == "silent_log"

# 4a) gap explained by a contact whose detail sits in the next sentence -> suppressed, nurse_task, no page
def test_gap_contact_detail_in_next_sentence_not_paged():
    d = ev(pmh=["heart failure", "COPD"], meds=[{"name": "furosemide", "dose": "40 mg daily"}], devices=["watch", "scale"],
           trend_last_7d="Day -7 to -4: stable. Watch offline from Day -3 07:00, gap now 52 hours; scale weigh-ins continue.",
           caregiver_or_nurse_note="Niece: I phoned Aunt May on Day -1 at 18:30. She was chatty and said she felt well.",
           data_quality={"wear_time_pct_7d": 55, "artifact_flags": [], "longest_gap_h": 52})
    assert d["rule"] == "HT_GAP48_HIGHRISK" and d["tier"] == "SUPPRESSED" and r(d) == "nurse_task"
# 4b) 72 h lookback: a recovered drug-related CKD low on Day -2 -> provider dose review
def test_day_minus2_ckd_low_is_seen():
    d = ev(meds=INS, trend_last_7d="Day -6 to -3: CGM minimum 90-104 mg/dL. Day -2 04:40 CGM 51 mg/dL; meter 92 mg/dL at 05:00. Day -1 to 0: CGM minimum 88-96 mg/dL.",
           caregiver_or_nurse_note="He felt fine all week.", **CKD)
    assert d["reason"] == "recent_ckd_low_dose_review" and r(d) == "provider_task"
def test_low_older_than_lookback_ignored():
    d = ev(meds=INS, trend_last_7d="Day -6 04:40 CGM 51 mg/dL; meter 92 mg/dL at 05:00. Day -5 to 0: CGM minimum 88-96 mg/dL.", caregiver_or_nurse_note="He felt fine all week.", **CKD)
    assert d.get("reason") != "recent_ckd_low_dose_review"
