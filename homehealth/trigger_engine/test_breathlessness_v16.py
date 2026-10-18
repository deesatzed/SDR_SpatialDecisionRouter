"""SMART_TRIGGERS v1.6 (Wayne 2026-10-18): distressing breathlessness that can be treated at home is on the urgent hospice-comfort list.
Synthetic inputs; no API calls."""
import trigger_eval as T
P = T.load_params("trigger_params.json")
DAY = T.DAY
BR = {"distressing": True, "home_treatable": True}
def spo2(value, ctx, vital="spo2"):
    b = T.Baseline("SYN-B", 0.0, P)
    return T.evaluate({"vital": vital, "value": value, "ts": 99 * DAY, "activity_state": "rest"}, b, P, ctx)

def test_params_list_breathlessness():
    uc = P["goals_of_care"]["urgent_comfort"]
    assert P["version"] >= "0.6-placeholder" and uc["conditions"]["breathlessness_distressing_home_treatable"] is True
    assert any(e["approved_by"] == "Wayne" and "breathlessness" in str(e["keys"]) for e in P["change_log"])
def test_hk1_007_like_breathlessness_in_hospice_pages_hospice_nurse_now():
    d = spo2(79, {"goals": "comfort_only", "breathlessness": BR})        # danger-level SpO2, few-word speech, comfort plan
    assert d["tier"] == "ABSOLUTE" and d["route"] == "escalate_human" and d["page"] is True
    assert d["escalation_target"] == "hospice_nurse" and d["notify"] == "hospice_nurse_urgent_page" and d["goals_basis"] == "breathlessness_distressing_home_treatable"
def test_rr_trigger_with_breathlessness_also_counts():
    d = spo2(38, {"goals": "comfort_only", "breathlessness": BR}, vital="rr")
    assert d["escalation_target"] == "hospice_nurse"
def test_hospital_directed_escalation_still_suppressed():
    # breathlessness that needs hospital treatment (not home-treatable) -> suppressed, same-shift hospice contact
    d = spo2(79, {"goals": "comfort_only", "breathlessness": {"distressing": True, "home_treatable": False}})
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "goals_of_care" and d["notify"] == "hospice_nurse_same_shift"
    # not distressing -> suppressed
    assert spo2(79, {"goals": "comfort_only", "breathlessness": {"distressing": False, "home_treatable": True}})["tier"] == "SUPPRESSED"
    # a non-respiratory trigger (HR danger) with breathlessness reported -> still suppressed
    assert spo2(185, {"goals": "comfort_only", "breathlessness": BR}, vital="hr")["tier"] == "SUPPRESSED"
    # chest pain in hospice with breathlessness -> still suppressed (hospital-directed)
    cp = T.evaluate_chest_pain({"ts": 0.0, "activity_state": "rest", "vitals": {"hr": {"value": 150}}, "symptoms": {"chest_pain": True, "red_flags": ["dyspnea"]}}, P,
                               context={"goals": "comfort_only", "breathlessness": BR})
    assert cp["tier"] == "SUPPRESSED" and cp["reason"] == "goals_of_care"
def test_full_goals_patient_unaffected_by_breathlessness_context():
    d = spo2(79, {"breathlessness": BR})
    assert d["tier"] == "ABSOLUTE" and "escalation_target" not in d
