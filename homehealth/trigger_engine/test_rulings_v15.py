"""SMART_TRIGGERS v1.5 policy changes from Wayne's review-queue rulings (2026-10-17/18). Synthetic inputs; no API calls.
a. chest-pain band math: net all modifiers first, then clamp (ST4-002)
b. unanswered patient prompt + lives alone = failed confirm -> escalate now (ST2-009)
c. hospice narrowing: goals of care suppress hospital-directed escalation only; urgent treatable comfort problems page the hospice nurse now (GC2-003)
d. CGM rule ordering: symptoms are checked before a refuting fingerstick (NV2-015)
plus grade_merge validation of the v1.5 case fields."""
import sys, copy, pytest
import trigger_eval as T
sys.path.insert(0, "../prompts_v2"); import grade_merge as G
P = T.load_params("trigger_params.json")
DAY = T.DAY

def cp(vitals, act="rest", red=None, mse=None, concordant=None, **kw):
    sym = {"chest_pain": True, "severity": "mild", "red_flags": red or [], "concordant": concordant, **kw.pop("sym", {})}
    return {"ts": 0.0, "activity_state": act, "minutes_since_exertion": mse, "vitals": {k: {"value": v} for k, v in vitals.items()}, "symptoms": sym, **kw}
E = lambda inp, **ctx: T.evaluate_chest_pain(inp, P, context=ctx)

# ---- a. band math
def test_params_record_net_then_clamp():
    assert P["chest_pain"]["band_math"]["method"] == "net_then_clamp" and P["version"] >= "0.5-placeholder"
def test_st4_002_net_modifiers_first_gives_band_c_15_min():
    # HR 50 asleep on bisoprolol: raw C, sleep -1, rate control -1; diaphoresis + dyspnoea +2 -> net 0 -> C (sequential clamping gave B, 5 min)
    d = E(cp({"hr": 50, "sbp": 118}, act="sleep", red=["diaphoresis", "dyspnea"]), rate_control_med=True)
    assert d["raw_band"] == "C" and d["band"] == "C" and d["tier"] == "CONFIRM_FIRST" and d["confirm_step"] == "patient_call" and d["timeout_min"] == 15
def test_net_below_d_is_clamped_once_at_the_end():
    d = E(cp({"hr": 50, "sbp": 118}, act="sleep"), rate_control_med=True)          # net -1 -> clamped to D
    assert d["band"] == "D" and d["tier"] == "LOG_ONLY" and any("clamped to D" in m for m in d["modifiers"])
    one = E(cp({"hr": 50, "sbp": 118}, act="sleep", red=["diaphoresis"]), rate_control_med=True)   # net 0 -> D, not C
    assert one["band"] == "D"
def test_net_above_a_is_clamped_to_a_and_floors_still_apply():
    assert E(cp({"hr": 150}, red=["diaphoresis", "radiation"]))["tier"] == "ABSOLUTE"
    d = E(cp({"hr": 38}, act="sleep"), rate_control_med=True, known_brady_range=[45, 55])   # raw A never below B
    assert d["raw_band"] == "A" and d["band"] == "B"
    crs = E(cp({"hr": 70, "sbp": 128}, red=["crescendo_pattern"], concordant=False))       # crescendo floor still applies after netting
    assert crs["band"] == "C" and crs["tier"] == "CONFIRM_FIRST"
def test_st1_010_unreliable_ecg_but_band_a_vitals_and_symptoms_is_absolute():
    d = E(cp({"hr": 102, "sbp": 156}, act="active", mse=5, red=["diaphoresis", "persistent_ge_15min"], concordant=True, sym={"ecg_change": True, "ecg_reliable": False}), rate_control_med=True)
    assert d["rule"] == "HT_CHEST_PAIN_VITALS" and d["tier"] == "ABSOLUTE" and d["route"] == "escalate_human"

# ---- b. unanswered prompt, lives alone
CF = {"tier": "CONFIRM_FIRST", "reason": "x", "route": "escalate_human", "page": "if_confirmed_or_timeout", "rule": "HT_FALL_ANTICOAG", "confirm_step": "watch_prompt", "timeout_min": 10}
def test_unanswered_watch_prompt_living_alone_escalates_now():
    d = T.resolve_confirm(CF, "no_answer", P, {"lives_alone": True})
    assert d["page"] is True and d["confirm_step"] == "already_confirmed" and d["timeout_min"] is None and d["confirm_result"] == "unanswered_prompt_lives_alone"
    pc = T.resolve_confirm({**CF, "confirm_step": "patient_call"}, "no_answer", P, {"lives_alone": True})
    assert pc["page"] is True and pc["confirm_step"] == "already_confirmed"
def test_unanswered_prompt_not_living_alone_waits_for_timeout():
    d = T.resolve_confirm(CF, "no_answer", P, {"lives_alone": False})
    assert d["page"] == "if_confirmed_or_timeout" and d["timeout_min"] == 10 and d["confirm_result"] == "no_answer_waiting_for_timeout"
def test_unanswered_caregiver_ping_is_not_a_patient_prompt():
    d = T.resolve_confirm({**CF, "confirm_step": "caregiver_ping", "timeout_min": 30}, "no_answer", P, {"lives_alone": True})
    assert d["page"] == "if_confirmed_or_timeout" and d["timeout_min"] == 30
def test_confirmed_pending_and_bad_outcome():
    assert T.resolve_confirm(CF, "confirmed", P)["confirm_step"] == "already_confirmed"
    assert T.resolve_confirm(CF, "pending", P) == CF
    assert T.resolve_confirm({"tier": "ABSOLUTE"}, "no_answer", P, {"lives_alone": True}) == {"tier": "ABSOLUTE"}
    with pytest.raises(ValueError): T.resolve_confirm(CF, "maybe", P)

# ---- c. hospice narrowing
def cgm(b, value, t_min, **g):
    return T.evaluate({"vital": "glucose", "value": value, "ts": 99 * DAY + t_min * 60, "activity_state": "sleep", "source": "cgm", "cgm": {"overnight": True, **g}}, b, P, {"goals": "comfort_only"})
def test_gc2_003_recurrent_symptomatic_low_pages_hospice_nurse_now():
    b = T.Baseline("SYN-GC", 0.0, P)
    first = cgm(b, 46, 0)                         # 02:10 CGM 46, no symptoms recorded -> same-shift hospice contact
    assert first["tier"] == "SUPPRESSED" and first["reason"] == "goals_of_care" and first["notify"] == "hospice_nurse_same_shift"
    again = cgm(b, 49, 55, symptoms=True)         # 03:05 CGM 49 after gel, drowsy
    assert again["tier"] == "ABSOLUTE" and again["route"] == "escalate_human" and again["page"] is True
    assert again["escalation_target"] == "hospice_nurse" and again["notify"] == "hospice_nurse_urgent_page" and again["hospital_directed"] is False
def test_v17_recurrent_low_without_symptoms_is_suppressed_same_shift():
    # v1.7 (Wayne 2026-10-18): recurrence within 6 h WITHOUT symptoms no longer pages urgently
    assert P["goals_of_care"]["urgent_comfort"]["conditions"]["hypoglycemia_recurrent"] is False
    b = T.Baseline("SYN-GC2", 0.0, P); cgm(b, 46, 0)
    d = cgm(b, 50, 60)
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "goals_of_care" and d["notify"] == "hospice_nurse_same_shift" and "escalation_target" not in d
    s = cgm(b, 49, 90, symptoms=True)                    # a symptomatic low still pages the hospice nurse now
    assert s["tier"] == "ABSOLUTE" and s["escalation_target"] == "hospice_nurse" and s["goals_basis"] == "hypoglycemia_symptomatic"
    b2 = T.Baseline("SYN-GC3", 0.0, P); cgm(b2, 46, 0)
    assert cgm(b2, 50, 60 * 7)["tier"] == "SUPPRESSED"
def test_artifact_or_unreliable_low_does_not_count_as_recurrent():
    b = T.Baseline("SYN-GC4", 0.0, P)
    assert cgm(b, 48, 0, pressure_documented=True)["tier"] == "ARTIFACT"
    assert cgm(b, 50, 30)["tier"] == "SUPPRESSED"
def test_hospital_directed_triggers_stay_suppressed_in_hospice():
    b = T.Baseline("SYN-H", 0.0, P)
    d = T.evaluate({"vital": "spo2", "value": 79, "ts": 99 * DAY, "activity_state": "rest"}, b, P, {"goals": "comfort_only"})
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "goals_of_care" and d["notify"] == "hospice_nurse_same_shift"   # no breathlessness context -> still suppressed (same-shift)
    c = E(cp({"hr": 150}), goals="comfort_only")
    assert c["tier"] == "SUPPRESSED" and c["reason"] == "goals_of_care"
def test_declared_comfort_treatable_problem_pages_hospice_nurse():
    b = T.Baseline("SYN-H2", 0.0, P)
    d = T.evaluate({"vital": "spo2", "value": 79, "ts": 99 * DAY, "activity_state": "rest"}, b, P, {"goals": "comfort_only", "comfort_treatable": True})
    assert d["tier"] == "ABSOLUTE" and d["escalation_target"] == "hospice_nurse" and d["goals_basis"] == "declared_comfort_treatable"
def test_full_goals_patient_unaffected():
    b = T.Baseline("SYN-F", 0.0, P)
    d = T.evaluate({"vital": "glucose", "value": 46, "ts": 99 * DAY, "source": "cgm", "cgm": {"symptoms": True}}, b, P, {})
    assert d["tier"] == "ABSOLUTE" and "escalation_target" not in d

# ---- d. CGM ordering (NV2-015)
def test_nv2_015_fingerstick_58_plus_confusion_is_absolute():
    b = T.Baseline("SYN-NV", 0.0, P)
    d = T.evaluate({"vital": "glucose", "value": 50, "ts": 99 * DAY, "source": "cgm", "cgm": {"overnight": True, "fingerstick": {"value": 58, "minutes_apart": 10}, "symptoms": True}}, b, P, {})
    assert d["tier"] == "ABSOLUTE" and d["reason"] == "hard_limit_danger_symptomatic" and d["page"] is True
    # same data without symptoms: the fingerstick above 54 refutes the CGM low -> shows the symptom check runs first
    n = T.evaluate({"vital": "glucose", "value": 50, "ts": 99 * DAY, "source": "cgm", "cgm": {"overnight": True, "fingerstick": {"value": 58, "minutes_apart": 10}, "symptoms": False}}, T.Baseline("x", 0.0, P), P, {})
    assert n["tier"] == "SUPPRESSED" and n["reason"] == "unreliable_reading"

# ---- grade_merge v1.5 field checks
BASE = {"hard_trigger": True, "hard_trigger_rule": "HT_FALL_ANTICOAG", "trigger_tier": "SUPPRESSED", "confirm_step": None, "confirm_timeout_min": None,
        "suppression_reason": "explained", "expected_route": "nurse_task", "acceptable_alternates": ["wake_specialist"], "category": ["fall"]}
SEC = {"hard_trigger_rule": "HT_VS_BASELINE", "trigger_tier": "CONFIRM_FIRST", "confirm_step": "device_recheck", "confirm_timeout_min": 10, "if_confirmed_route": "escalate_human"}
def chk(**kw): c = copy.deepcopy(BASE); c.update(kw); return G.smart_checks(c)
def test_hk7_009_secondary_hr_recheck_is_valid():
    assert chk(secondary_triggers=[SEC]) == []
    assert any("if_confirmed_route" in i for i in chk(secondary_triggers=[{**SEC, "if_confirmed_route": "nurse_task"}]))
    assert any("timeout" in i for i in chk(secondary_triggers=[{**SEC, "confirm_timeout_min": None}]))
    assert any("silent_log" in i for i in chk(expected_route="silent_log", secondary_triggers=[SEC]))
    assert any("repeats the primary" in i for i in chk(secondary_triggers=[{**SEC, "hard_trigger_rule": "HT_FALL_ANTICOAG"}]))
def test_route_basis_allows_clinician_ruled_escalation_on_suppressed_trigger():
    kw = dict(hard_trigger_rule="HT_SPO2_LT88", suppression_reason="at_patient_baseline", expected_route="escalate_human", acceptable_alternates=[])
    assert any("SUPPRESSED but expected escalate_human" in i for i in chk(**kw))
    assert chk(**kw, route_basis="clinical_presentation") == []
    assert any("route_basis" in i for i in chk(route_basis="clinical_presentation"))
def test_escalation_target_hospice_nurse():
    kw = dict(hard_trigger_rule="HT_VS_DANGER", trigger_tier="ABSOLUTE", suppression_reason=None, expected_route="escalate_human", acceptable_alternates=[], category=["hypoglycemia", "goals_of_care"])
    assert chk(**kw, escalation_target="hospice_nurse") == []
    assert any("goals_of_care category" in i for i in chk(**{**kw, "category": ["hypoglycemia"]}, escalation_target="hospice_nurse"))
    assert any("non-suppressed tier" in i for i in chk(escalation_target="hospice_nurse", category=["fall", "goals_of_care"], expected_route="escalate_human"))
def test_hard_limit_layer_does_not_need_baseline_status():
    c = {"hard_trigger": True, "hard_trigger_rule": "HT_VS_DANGER", "trigger_tier": "ABSOLUTE", "confirm_step": None, "confirm_timeout_min": None, "suppression_reason": None,
         "expected_route": "escalate_human", "acceptable_alternates": [], "baseline_layer": "hard_limit_danger", "category": ["hypoglycemia", "fall"]}
    assert G.smart_checks(c) + G.layer_checks(c) == []
    assert any("baseline_status" in i for i in G.layer_checks({**c, "baseline_layer": "learning_period", "trigger_tier": "SUPPRESSED"}))
    assert any("baseline_status" in i for i in G.layer_checks({**c, "baseline_status": {"phase": "bogus"}}))

# ---- v1.7 clinician override of the engine tier (ST1-010, Wayne 2026-10-18)
OV_CASE = {"case_id": "SYN-OV", "hard_trigger": True, "hard_trigger_rule": "HT_CHEST_PAIN_VITALS", "trigger_tier": "CONFIRM_FIRST", "confirm_step": "patient_call", "confirm_timeout_min": 5,
           "suppression_reason": None, "expected_route": "escalate_human", "acceptable_alternates": [], "category": ["acs"],
           "chest_pain_eval": {"band": "A", "raw_band": "C", "tier": "ABSOLUTE"}}
OV = {"engine_tier": "ABSOLUTE", "label_tier": "CONFIRM_FIRST", "approved_by": "Wayne", "date": "2026-10-18", "reason": "clinician ruling"}
def test_band_a_labelled_confirm_first_needs_override():
    assert any("implies ABSOLUTE" in i for i in G.smart_checks(OV_CASE))
    ok = {**OV_CASE, "clinician_override": OV}
    assert G.smart_checks(ok) == [] and G.override_note(ok).startswith("CLINICIAN_OVERRIDE SYN-OV: engine ABSOLUTE -> label CONFIRM_FIRST")
def test_override_must_be_complete_named_and_match():
    assert any("named human" in i for i in G.smart_checks({**OV_CASE, "clinician_override": {**OV, "approved_by": "engine"}}))
    assert any("does not match" in i for i in G.smart_checks({**OV_CASE, "clinician_override": {**OV, "label_tier": "ABSOLUTE"}}))
    assert any("missing" in i for i in G.smart_checks({**OV_CASE, "clinician_override": {"engine_tier": "ABSOLUTE", "label_tier": "CONFIRM_FIRST"}}))
    assert G.override_note({"case_id": "x"}) is None
