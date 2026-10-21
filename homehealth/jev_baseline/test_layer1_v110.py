"""SMART_TRIGGERS v1.10 Layer 1 fixes (Wayne 2026-10-21). Hand-written SYNTHETIC practice cases (not holdout text). No API calls."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L, dual_jev as D  # noqa: E402
EST = {"phase": "established", "monitoring_day": 120, "learning_days_total": 10, "last_condition_change": None}
def case(**k):
    c = {"age_band": "75-79", "sex": "F", "living": "with spouse", "pmh": ["hypertension"], "meds": [{"name": "amlodipine", "dose": "5 mg daily"}],
         "recent_med_changes": [], "devices": ["watch", "fingertip_oximeter"], "baseline_30d": {"rest_hr": 70, "spo2_night_min": 94},
         "baseline_status": EST, "trend_last_7d": "Day -6 to -1: resting HR 68-72 bpm, wrist SpO2 94-96%.", "caregiver_or_nurse_note": "", "data_quality": {}}
    c.update(k); return c
def ev(**k): return L.evaluate_case(case(**k))

# 1. artifact cleared by a clean repeat -> SUPPRESSED cleared_by_repeat, silent_log
def test_spo2_cleared_by_contralateral_repeat_is_silent():
    d = ev(trend_last_7d="Day -6 to -1: fingertip SpO2 95-97% at rest. Day 0 08:05 fingertip right index SpO2 83% at rest with low perfusion flag. Day 0 08:08 fingertip left index SpO2 95% at rest, good waveform.",
           caregiver_or_nurse_note="Spouse: her hands were cold from the garden; she is chatting normally.")
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "cleared_by_repeat"
    assert L.route(d, None) == ("silent_log", "layer1_cleared") and L.route(d, "provider_task") == ("silent_log", "layer1_cleared")
def test_symptomatic_low_is_not_cleared():
    d = ev(trend_last_7d="Day 0 08:05 fingertip SpO2 84% at rest. Day 0 08:08 fingertip left index SpO2 93% at rest.", caregiver_or_nurse_note="Spouse says she is breathless sitting in the chair.")
    assert d.get("reason") != "cleared_by_repeat"
def test_cgm_low_cleared_by_normal_fingerstick_without_insulin_ckd_is_silent():
    d = ev(pmh=["type 2 diabetes"], meds=[{"name": "metformin", "dose": "1 g BID"}], devices=["cgm"],
           trend_last_7d="Day -6 to -1: CGM overnight minimum 82-95 mg/dL. Day 0: CGM 50 mg/dL at 02:30 while lying on the sensor arm; fingerstick glucometer 98 mg/dL at 02:45.",
           caregiver_or_nurse_note="Spouse: slept through, normal breakfast.")
    assert d["reason"] == "cleared_by_repeat" and not d["hitm_required"] and L.route(d, None)[0] == "silent_log"
def test_insulin_ckd_low_always_hitm_nurse_task():
    d = ev(pmh=["type 2 diabetes", "CKD 3b"], meds=[{"name": "insulin glargine", "dose": "16 units at bedtime"}], devices=["cgm"],
           trend_last_7d="Day -6 to -1: CGM overnight minimum 85-100 mg/dL. Day 0: CGM 51 mg/dL at 02:30 while lying on the sensor arm; fingerstick glucometer 96 mg/dL at 02:45.",
           caregiver_or_nurse_note="Spouse: slept through, normal breakfast.")
    assert d["hitm_required"] and L.route(d, None) == ("nurse_task", "layer1_default") and L.route(d, "silent_log")[0] == "nurse_task"
    r, _, flag = D.dual_route(d, "silent_log", "silent_log"); assert r == "nurse_task" and flag   # hard HITM flag even when the models agree
def test_confirming_low_fingerstick_is_not_a_clean_repeat():
    d = ev(pmh=["type 2 diabetes"], meds=[{"name": "glipizide", "dose": "5 mg daily"}], devices=["cgm"],
           trend_last_7d="Day 0: CGM 52 mg/dL at 03:00; fingerstick glucometer 58 mg/dL at 03:10.")
    assert d.get("reason") != "cleared_by_repeat"

# 2. suppressed fallback derived per rule (no blanket provider_task)
def test_suppressed_fallback_is_per_rule():
    assert L.route({"tier": "SUPPRESSED", "reason": "explained"}, None) == ("nurse_task", "layer1_default")
    assert L.route({"tier": "SUPPRESSED", "reason": "unreliable_reading"}, None) == ("nurse_task", "layer1_default")
    assert L.route({"tier": "ARTIFACT", "reason": "nonphysiologic_rate"}, None) == ("silent_log", "layer1_default")

# 3. falls on an anticoagulant
AF = dict(pmh=["atrial fibrillation"], meds=[{"name": "apixaban", "dose": "5 mg BID"}])
def test_unwitnessed_impact_cleared_by_caregiver_check_is_nurse_task():
    d = ev(**AF, trend_last_7d="Day 0 21:40 watch logged an impact event; HR 74 bpm at 21:45.",
           caregiver_or_nurse_note="Daughter checked on her at 21:50: she was sitting in bed, pain-free, and says the watch knocked the bedside table.")
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "explained_caregiver_check"
    assert L.route(d, None)[0] == "nurse_task" and L.route(d, "silent_log")[0] == "nurse_task"
def test_watch_on_floor_is_not_a_confirmed_fall():
    d = ev(**AF, trend_last_7d="Day 0 22:00 watch logged an impact while off wrist.",
           caregiver_or_nurse_note="Husband found the watch on the kitchen floor at 22:10 and checked her: she was walking to bed, pain-free.")
    assert d["tier"] != "ABSOLUTE" and d["reason"] == "explained_caregiver_check"
def test_confirmed_fall_on_anticoagulant_is_absolute():
    d = ev(**AF, trend_last_7d="Day 0 07:30 watch logged an impact; HR 110 bpm for 5 minutes.", caregiver_or_nurse_note="Husband saw her slip in the hallway and fall; no head strike.")
    assert d["tier"] == "ABSOLUTE" and d["rule"] == "HT_FALL_ANTICOAG" and L.route(d, None)[0] == "urgent_page"

# 4. COPD / known low baseline SpO2
def test_copd_at_documented_baseline_is_nurse_task_not_page():
    d = ev(pmh=["COPD GOLD 3, usual resting SpO2 86-89%"], baseline_30d={"rest_hr": 80},
           trend_last_7d="Day -6 to -1: watch resting SpO2 87-89%, RR 18. Day 0 10:00 fingertip SpO2 86% at rest, good waveform.", caregiver_or_nurse_note="Spouse: same as usual, no new breathlessness.")
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "at_patient_baseline"
    assert L.route(d, None)[0] == "nurse_task" and L.route(d, "silent_log")[0] == "nurse_task"
def test_drop_below_own_baseline_still_confirms():
    d = ev(pmh=["COPD, usual resting SpO2 90-92%"], trend_last_7d="Day -6 to -1: watch resting SpO2 90-92%. Day 0 10:00 fingertip SpO2 84% at rest, good waveform; repeat fingertip 84%.")
    assert d["tier"] == "CONFIRM_FIRST"

# 5. wording synonyms
def test_syncope_synonyms():
    for w in ("she collapsed in the kitchen and was unresponsive briefly", "he slumped in his chair with loss of tone for a minute", "she passed out at the sink"):
        assert ev(caregiver_or_nurse_note=f"Spouse: {w}.")["rule"] == "HT_SYNCOPE", w
def test_near_faint_is_not_syncope():
    assert ev(caregiver_or_nurse_note="Spouse: she felt faint when she stood up but did not lose consciousness.").get("rule") != "HT_SYNCOPE"
def test_focal_neuro_synonyms():
    for w in ("his face is drooping on the left", "she has trouble speaking and her words came out jumbled", "he cannot lift the right arm since 09:00"):
        assert ev(caregiver_or_nurse_note=f"Spouse: {w}.")["rule"] == "HT_FOCAL_NEURO", w
def test_chest_pain_synonym_reaches_chest_rule():
    d = ev(trend_last_7d="Day 0 09:00 resting HR 118 bpm, BP 92/60 mmHg.", caregiver_or_nurse_note="Spouse: crushing pain since 08:40, sweaty and grey.")
    assert d["rule"] == "HT_CHEST_PAIN_VITALS" and d["tier"] in ("ABSOLUTE", "CONFIRM_FIRST")
def test_symptomatic_bradycardia_on_amiodarone_confirms():
    d = ev(meds=[{"name": "amiodarone", "dose": "200 mg daily"}], trend_last_7d="Day -6 to -1: resting HR 58-62 bpm. Day 0 11:00 resting HR 41 bpm, seated.",
           caregiver_or_nurse_note="Spouse: she is dizzy and light-headed when she stands.")
    assert d["rule"] == "HT_BRADY_RATE_DRUG" and d["tier"] == "CONFIRM_FIRST"
def test_asymptomatic_bradycardia_makes_no_decision():
    d = ev(meds=[{"name": "bisoprolol", "dose": "5 mg daily"}], trend_last_7d="Day 0 11:00 resting HR 43 bpm, seated.", caregiver_or_nurse_note="Spouse: feels well.")
    assert d.get("rule") != "HT_BRADY_RATE_DRUG"

# 6. scale weigh-ins are not contact
HF = dict(pmh=["HFrEF EF 30%"], living="alone", data_quality={"longest_gap_h": 52, "artifact_flags": ["watch offline from Day -2 08:00"]})
def test_scale_weighins_do_not_explain_a_gap():
    d = ev(**HF, trend_last_7d="Day -6 to -3: resting HR 70-74 bpm. Day -1 07:30 scale weigh-in 80.1 kg transmitted, stable. Day 0 07:35 scale weighed 80.2 kg, stable.")
    assert d["rule"] == "HT_GAP48_HIGHRISK" and d["tier"] == "CONFIRM_FIRST"
def test_timed_video_call_explains_a_gap():
    d = ev(**HF, trend_last_7d="Day -6 to -3: resting HR 70-74 bpm.", caregiver_or_nurse_note="Son: video call on Day -1 at 15:00, he was eating and talking normally.")
    assert d["rule"] == "HT_GAP48_HIGHRISK" and d["tier"] == "SUPPRESSED"

# v1.10.1: sulfonylurea + CKD danger-level low -> hard HITM, at least nurse_task, never silent (practice cases)
def test_sulfonylurea_ckd_low_is_hard_hitm_nurse_task():
    for drug in ("glimepiride", "glipizide", "glyburide", "gliclazide"):
        d = ev(pmh=["type 2 diabetes", "CKD G3a"], meds=[{"name": drug, "dose": "standard dose"}], devices=["cgm"],
               trend_last_7d="Day -6 to -1: CGM overnight minimum 80-96 mg/dL. Day 0: CGM 50 mg/dL at 03:00 while lying on the sensor arm; fingerstick glucometer 95 mg/dL at 03:15.",
               caregiver_or_nurse_note="Spouse: slept through, normal breakfast.")
        assert d["hitm_required"], drug
        assert L.route(d, None)[0] == "nurse_task" and L.route(d, "silent_log")[0] == "nurse_task", drug
        r, _, flag = D.dual_route(d, "silent_log", "silent_log"); assert r == "nurse_task" and flag, drug
def test_sulfonylurea_without_ckd_cleared_low_stays_silent():
    d = ev(pmh=["type 2 diabetes"], meds=[{"name": "gliclazide", "dose": "80 mg daily"}], devices=["cgm"],
           trend_last_7d="Day 0: CGM 51 mg/dL at 02:40 while lying on the sensor arm; fingerstick glucometer 97 mg/dL at 02:55.")
    assert not d["hitm_required"] and L.route(d, None)[0] == "silent_log"
def test_meter_danger_low_on_sulfonylurea_ckd_flags():
    d = ev(pmh=["CKD stage 4"], meds=[{"name": "glipizide", "dose": "5 mg daily"}], devices=["glucometer"],
           trend_last_7d="Day 0 07:10 fingerstick glucometer 49 mg/dL before breakfast.", caregiver_or_nurse_note="Spouse: a little shaky, ate toast.")
    assert d["hitm_required"]
def test_metformin_ckd_low_not_flagged():
    d = ev(pmh=["CKD 3a"], meds=[{"name": "metformin", "dose": "500 mg BID"}], devices=["cgm"],
           trend_last_7d="Day 0: CGM 52 mg/dL at 02:40 while lying on the sensor arm; fingerstick glucometer 96 mg/dL at 02:55.")
    assert not d["hitm_required"]
