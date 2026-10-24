"""SMART_TRIGGERS v1.11.0 Layer 1 fixes (Wayne 2026-10-23, holdout_v3 rulings). Hand-written SYNTHETIC practice vignettes (never holdout text). No API calls."""
import copy, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L, dual_jev as D  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
SU = [{"name": "glipizide", "dose": "5 mg daily"}]; INS = [{"name": "insulin detemir", "dose": "12 units nightly"}]; AC = [{"name": "rivaroxaban", "dose": "15 mg daily"}]
HOSPICE = "hospice enrolled, comfort-focused care at home, no hospital transfer"

# a) FOUNDATION: confirmed + symptomatic drug-induced low -> urgent page, even in hospice, regardless of CKD
def test_drug_low_symptomatic_confirmed_pages():
    d = ev(pmh=["type 2 diabetes"], meds=SU, devices=["cgm", "glucometer"], trend_last_7d="Day -6 to -1: CGM minimum 95-110 mg/dL. Day 0 05:10 CGM 44 mg/dL; meter 46 mg/dL at 05:15.",
           caregiver_or_nurse_note="Husband: she was trembling and confused when he woke her.")
    assert d["rule"] == "HT_DRUG_LOW" and d["tier"] == "ABSOLUTE" and d["foundation"] and L.route(d, "silent_log")[0] == "urgent_page"
def test_drug_low_in_hospice_pages_hospice_nurse():
    d = ev(patient_goals=HOSPICE, pmh=["type 2 diabetes", "metastatic lung cancer"], meds=INS, devices=["cgm", "glucometer"],
           trend_last_7d="Day 0 02:40 CGM 41 mg/dL; meter 43 mg/dL at 02:48.", caregiver_or_nurse_note="Night aide: clammy and hard to rouse, took sugar gel after several tries.")
    assert d["rule"] == "HT_DRUG_LOW" and d["escalation_target"] == "hospice_nurse" and L.route(d, None)[0] == "urgent_page"
    assert "hospice nurse" in d["plain_reason"]
def test_drug_low_with_ckd_still_pages():
    d = ev(pmh=["type 2 diabetes", "CKD 4"], meds=SU, devices=["cgm", "glucometer"], trend_last_7d="Day 0 04:00 CGM 45 mg/dL; meter 47 mg/dL at 04:06.",
           caregiver_or_nurse_note="Daughter: sweaty and muddled, slurring.")
    assert d["rule"] == "HT_DRUG_LOW" and L.route(d, "provider_task")[0] == "urgent_page"
def test_drug_low_asymptomatic_does_not_hit_floor():
    d = ev(pmh=["type 2 diabetes"], meds=INS, devices=["cgm", "glucometer"], trend_last_7d="Day 0 04:00 CGM 50 mg/dL; meter 52 mg/dL at 04:06.", caregiver_or_nurse_note="Spouse: woke normally, chatting.")
    assert d.get("rule") != "HT_DRUG_LOW"
def test_symptomatic_low_on_metformin_alone_not_foundation():
    d = ev(pmh=["type 2 diabetes"], meds=[{"name": "metformin", "dose": "1 g BID"}], devices=["cgm", "glucometer"],
           trend_last_7d="Day 0 04:00 CGM 50 mg/dL; meter 52 mg/dL at 04:06.", caregiver_or_nurse_note="Spouse: a bit sweaty.")
    assert d.get("rule") != "HT_DRUG_LOW"
def test_unconfirmed_symptomatic_cgm_low_not_foundation():
    d = ev(pmh=["type 2 diabetes"], meds=SU, devices=["cgm"], trend_last_7d="Day 0 04:00 CGM 50 mg/dL.", caregiver_or_nurse_note="Spouse: sweaty.")
    assert d.get("rule") != "HT_DRUG_LOW"

# b) CKD dose review; no CKD single low silent; repeated lows dose review
CKD_CLEARED = dict(pmh=["type 2 diabetes", "CKD 3b"], devices=["cgm", "glucometer"],
                   trend_last_7d="Day -6 to -1: CGM nightly minimum 90-105 mg/dL. Day 0: CGM 50 mg/dL at 02:10 with no sensor flag; meter 101 mg/dL at 02:25.",
                   caregiver_or_nurse_note="Wife: he slept through and said he felt fine.")
def test_ckd_cleared_low_on_sulfonylurea_is_provider_dose_review():
    d = ev(meds=SU, **CKD_CLEARED)
    assert d["reason"] == "ckd_low_dose_review" and d["hitm_required"]
    assert L.route(d, None)[0] == "provider_task" and L.route(d, "silent_log")[0] == "provider_task" and L.route(d, "urgent_page")[0] == "provider_task"
    r, _, flag = D.dual_route(d, "silent_log", "nurse_task"); assert r == "provider_task" and flag
    assert "review the dose" in d["plain_reason"]
def test_ckd_cleared_low_on_insulin_is_provider_dose_review():
    assert L.route(ev(meds=INS, **CKD_CLEARED), None)[0] == "provider_task"
def test_ckd_low_with_documented_compression_keeps_v110_nurse_floor():   # v1.11.1: now an explicit rule (ckd_low_compression_explained)
    k = copy.deepcopy(CKD_CLEARED); k["trend_last_7d"] = k["trend_last_7d"].replace("with no sensor flag", "while lying on the sensor arm")
    d = ev(meds=INS, **k); assert d["reason"] == "ckd_low_compression_explained" and L.route(d, None)[0] == "nurse_task"
def test_no_ckd_single_compression_low_stays_silent():
    d = ev(pmh=["type 2 diabetes"], meds=INS, devices=["cgm", "glucometer"], trend_last_7d="Day -6 to -1: CGM nightly minimum 92-110 mg/dL, no lows. Day 0: CGM 51 mg/dL at 03:00; meter 99 mg/dL at 03:09, untreated.",
           caregiver_or_nurse_note="Son: asleep on her sensor side, comfortable.")
    assert d["reason"] == "cleared_by_repeat" and L.route(d, None)[0] == "silent_log"
def test_no_ckd_repeated_lows_dose_review():
    d = ev(pmh=["type 2 diabetes"], meds=INS, devices=["cgm", "glucometer"], trend_last_7d="Day -6 to -4: CGM minimum 95-110 mg/dL. Day -3: CGM 50 mg/dL at 03:30. Day 0: CGM 51 mg/dL at 03:00; meter 99 mg/dL at 03:09.",
           caregiver_or_nurse_note="Son: comfortable, slept well.")
    assert d["reason"] == "repeated_lows_dose_review" and L.route(d, None)[0] == "provider_task"

# c) patient-level baseline bands
BAND = dict(pmh=["COPD GOLD 3", "home oxygen 2 L/min"], devices=["watch", "fingertip_oximeter"], baseline_30d={"rest_hr": 82, "spo2_night_min": 83})
def test_reading_inside_patient_rule_band_is_silent():
    d = ev(patient_bands={"spo2": [86, 89]}, trend_last_7d="Day -6 to -1: wrist SpO2 86-89% at rest. Day 0 11:00 wrist SpO2 87% at rest, RR 18.", caregiver_or_nurse_note="Husband: breathing as usual.", **BAND)
    assert d["reason"] == "within_patient_band" and L.route(d, None)[0] == "silent_log" and L.route(d, "nurse_task")[0] == "nurse_task"
def test_clinician_documented_band_counts_as_patient_rule():
    d = ev(trend_last_7d="Day -3: respiratory nurse visit documented his usual resting SpO2 as 86-89% on air. Day 0 11:00 wrist SpO2 87% at rest, RR 18.", caregiver_or_nurse_note="Husband: breathing as usual.", **BAND)
    assert d["reason"] == "within_patient_band" and L.route(d, None)[0] == "silent_log"
def test_below_band_is_not_baseline_and_lt85_pages():
    d = ev(patient_bands={"spo2": [86, 89]}, trend_last_7d="Day -6 to -1: wrist SpO2 86-89% at rest, night minimum 81-83%. Day 0 09:00 fingertip SpO2 83% at rest, good waveform. Day 0 09:04 fingertip SpO2 83% at rest, good waveform.",
           caregiver_or_nurse_note="Husband: says he feels his usual self.", **BAND)
    assert d["tier"] == "CONFIRM_FIRST" and d["reason"] == "below_patient_band_copd_lt85" and L.route(d, None)[0] == "urgent_page"
def test_below_band_in_hospice_goes_to_goals_of_care():
    d = ev(patient_goals=HOSPICE, patient_bands={"spo2": [86, 89]}, trend_last_7d="Day 0 09:00 fingertip SpO2 83% at rest, good waveform. Day 0 09:04 fingertip SpO2 83% at rest, good waveform.",
           caregiver_or_nurse_note="Aide: comfortable in bed.", **BAND)
    assert d["reason"] != "below_patient_band_copd_lt85" and L.route(d, None)[0] != "silent_log"

# d) impact + inactivity cap
IMP = "Day -6 to -1: steps 2600-3000. Day 0 14:02 watch impact while worn; 0 steps 14:02-14:15, then steps resume; HR 74 bpm."
def test_impact_inactivity_capped_at_nurse():
    d = ev(meds=AC, trend_last_7d=IMP, caregiver_or_nurse_note="Carer looked in at 14:15: he was sitting in his armchair; he says he knocked his arm on the door and sat down. No pain.")
    assert d["reason"] == "possible_fall_unverified" and L.route(d, "urgent_page")[0] in ("nurse_task", "provider_task") and L.route(d, None)[0] == "nurse_task"
def test_impact_inactivity_with_head_strike_not_capped():
    d = ev(meds=AC, trend_last_7d=IMP, caregiver_or_nurse_note="Carer: he says he bumped his head on the shelf and sat down; no pain elsewhere.")
    assert L.route(d, None)[0] == "urgent_page"
def test_impact_inactivity_witnessed_lost_footing_not_capped():
    d = ev(meds=AC, trend_last_7d=IMP, caregiver_or_nurse_note="Daughter watched him lose his footing on the step and land on his bottom; he says he is fine.")
    assert d["tier"] == "ABSOLUTE" and L.route(d, None)[0] == "urgent_page"
def test_impact_long_inactivity_not_capped():
    d = ev(meds=AC, trend_last_7d="Day 0 01:30 watch impact while worn; 0 steps 01:30-02:40.", caregiver_or_nurse_note="She says the watch is wrong.")
    assert L.route(d, None)[0] == "urgent_page"

# e) clean repeat whatever the flag; BP cuff
def test_spo2_repeat_clears_whatever_the_flag():
    d = ev(trend_last_7d="Day 0 15:20: fingertip oximeter on the right middle finger over thick acrylic nails SpO2 83%. Day 0 15:23: fingertip oximeter on the left middle finger, bare nail, SpO2 96%.",
           caregiver_or_nurse_note="Son: chatting, colour normal.")
    assert d["reason"] == "cleared_by_repeat" and L.route(d, None)[0] == "silent_log"
def test_spo2_flagged_low_and_clean_repeat_in_one_sentence_clears():
    d = ev(trend_last_7d="Day 0: wrist SpO2 84% at 08:40 with motion flag while making the bed; fingertip recheck at 08:50 reads 95%, good waveform.", caregiver_or_nurse_note="Husband: she is fine.")
    assert d["reason"] == "cleared_by_repeat" and L.route(d, None)[0] == "silent_log"
def test_bp_cuff_flagged_low_with_normal_repeat_is_silent():
    d = ev(devices=["bp_cuff", "watch"], trend_last_7d="Day -6 to -1: cuff 128-134/76-82 mmHg. Day 0 18:02: cuff 72/48 mmHg, cuff error flagged (arm moved). Day 0 18:06: cuff repeat 130/80 mmHg.",
           data_quality={"artifact_flags": ["cuff error Day 0 18:02"]}, caregiver_or_nurse_note="Wife: he was watching TV, feels normal.")
    assert d["reason"] == "cleared_by_repeat" and L.route(d, None)[0] == "silent_log"
def test_bp_implausible_high_with_normal_repeat_is_silent():
    d = ev(devices=["bp_cuff"], trend_last_7d="Day 0 07:00: cuff 296/120 mmHg. Day 0 07:05: cuff 132/80 mmHg.", caregiver_or_nurse_note="She says she feels fine.")
    assert d.get("tier") is None or L.route(d, None)[0] == "silent_log"
def test_bp_low_with_dizziness_not_cleared():
    d = ev(devices=["bp_cuff"], trend_last_7d="Day 0 07:00: cuff 74/46 mmHg. Day 0 07:05: cuff 126/78 mmHg.", caregiver_or_nurse_note="He felt dizzy standing up.")
    assert d.get("reason") != "cleared_by_repeat"
def test_bp_low_without_repeat_still_fires():
    d = ev(devices=["bp_cuff"], trend_last_7d="Day 0 07:00: cuff 74/46 mmHg.", caregiver_or_nurse_note="")
    assert L.route(d, None)[0] == "urgent_page"

# f) device tickets

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
def test_spo2_device_disagreement_no_reference_oximeter_ticket():
    d = ev(pmh=["COPD"], devices=["watch", "ring"], trend_last_7d="Day -6 to 0: wrist SpO2 90-91% at rest every morning while the ring reads 94-95% at the same moments. No breathlessness at rest.")
    assert L.route(d, None)[0] == "silent_log" and d["device_ticket"]["type"] == "supply_reference_oximeter_and_baseline" and not d["device_ticket"]["interruptive"]
def test_spo2_clip_vs_wrist_disagreement_maintenance_ticket():
    d = ev(devices=["watch", "fingertip_oximeter"], trend_last_7d="Day -3 to 0: fingertip clip reads 90-91% each morning while the wrist reads 95-96% on the same mornings; feels well.")
    assert L.route(d, None)[0] == "silent_log" and d["device_ticket"]["type"] == "device_maintenance"
def test_wrist_finger_within_variance_no_ticket():
    d = ev(devices=["watch", "fingertip_oximeter"], trend_last_7d="Day -3 to 0: fingertip reads 95% each morning while the wrist reads 96-97% on the same mornings.")
    assert "device_ticket" not in d
def test_rhythm_disagreement_ecg_strip_ticket():
    d = ev(pmh=["paroxysmal atrial fibrillation"], meds=[{"name": "edoxaban", "dose": "60 mg daily"}], devices=["watch", "ring"],
           trend_last_7d="Day -4 to 0: the watch flagged an irregular rhythm 3 times while the ring reads a regular 66 bpm throughout; no palpitations.")
    assert L.route(d, None)[0] == "silent_log" and d["device_ticket"]["type"] == "ecg_strip_request"
@_pre_v1141
def test_hr_disagreement_after_rate_drug_increase_is_nurse_plus_ticket():
    d = ev(meds=[{"name": "metoprolol", "dose": "50 mg BID"}], devices=["watch", "ring"], recent_med_changes=[{"name": "metoprolol", "change": "dose_increased", "day": -8}],
           trend_last_7d="Day -6 to 0: since the metoprolol increase the watch rest HR reads 47-50 but the ring rest HR remained 61-65; no dizziness.")
    assert L.route(d, None)[0] == "nurse_task" and L.route(d, "silent_log")[0] == "nurse_task" and d["device_ticket"]["type"] == "device_maintenance"
    assert "manual pulse" in d["plain_reason"]
def test_hr_disagreement_without_rate_change_is_silent_ticket():
    d = ev(devices=["watch", "ring"], trend_last_7d="Day -6 to 0: the watch rest HR reads 50-54 but the ring rest HR remained 64-67 every day; feels well.")
    assert L.route(d, None)[0] == "silent_log" and d["device_ticket"]["type"] == "device_maintenance"
def test_symptomatic_patient_gets_no_device_silencing():
    d = ev(devices=["watch", "ring"], trend_last_7d="Day -6 to 0: the watch rest HR reads 50-54 but the ring rest HR remained 64-67 every day.", caregiver_or_nurse_note="Wife: he is dizzy and short of breath.")
    assert d.get("reason") not in ("device_disagreement",)
def test_single_motion_artifact_is_not_a_device_ticket():
    d = ev(trend_last_7d="Day 0: wrist SpO2 84% at 08:40 with motion flag; fingertip recheck at 08:50 reads 95%.", caregiver_or_nurse_note="The watch beeped but her clip said 95 and she felt fine.")
    assert "device_ticket" not in d

# g) plain reasons on every routed alert
def test_every_layer1_routed_alert_has_plain_reason():
    cases = [ev(caregiver_or_nurse_note="Wife: his face is drooping on the left and his speech is slurred."),
             ev(meds=AC, trend_last_7d=IMP, caregiver_or_nurse_note="Carer: sat in the chair, says he knocked his arm. No pain."),
             ev(meds=SU, **CKD_CLEARED)]
    for d in cases:
        r, o = L.route(d, None); assert r != "silent_log" and L.route_reason(d, r, o)
def test_jev_owned_route_has_plain_reason_and_silent_has_none():
    d = ev(); assert L.route_reason(d, "nurse_task", "jev") and L.route_reason(d, "silent_log", "jev") is None

# h) serotonergic confusion candidate (disabled by default)
SER = dict(pmh=["depression"], meds=[{"name": "sertraline", "dose": "100 mg"}, {"name": "tramadol", "dose": "50 mg TID"}])
def test_serotonergic_candidate_off_by_default():
    assert ev(caregiver_or_nurse_note="Husband: she is more confused now than this morning, shaky.", **SER).get("rule") != "HT_SEROTONERGIC_CONFUSION"
def test_serotonergic_candidate_when_enabled(monkeypatch):
    P = copy.deepcopy(L.PARAMS); P["layer1_v110"]["v1110"]["serotonergic_confusion"]["enabled"] = True; monkeypatch.setattr(L, "PARAMS", P)
    d = ev(caregiver_or_nurse_note="Husband: she is more confused now than this morning, shaky.", **SER)
    assert d["rule"] == "HT_SEROTONERGIC_CONFUSION" and L.route(d, None)[0] == "urgent_page"
    d = ev(caregiver_or_nurse_note="Husband: she got a little confused yesterday evening, back to herself today.", **SER)
    assert d["rule"] == "HT_SEROTONERGIC_CONFUSION" and L.route(d, None)[0] == "provider_task"
