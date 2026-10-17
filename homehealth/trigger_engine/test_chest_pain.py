"""Chest-pain parametric rule (HT_CHEST_PAIN_VITALS) tests: sleep, exertion, rate control, pacemaker, known brady/tachy, device reliability, symptom concordance."""
import trigger_eval as T
P = T.load_params("trigger_params.json")
def cp(vitals, act="rest", red=None, mse=None, concordant=None, sev="mild", **kw):
    return {"ts": 0.0, "activity_state": act, "minutes_since_exertion": mse,
            "vitals": {k: (v if isinstance(v, dict) else {"value": v}) for k, v in vitals.items()},
            "symptoms": {"chest_pain": True, "severity": sev, "red_flags": red or [], "concordant": concordant, **kw.pop("sym", {})}, **kw}
E = lambda inp, **ctx: T.evaluate_chest_pain(inp, P, context=ctx)

def test_sleeping_hr50_on_beta_blocker_mild_discomfort_is_not_a_page():
    d = E(cp({"hr": 50, "sbp": 118}, act="sleep"), rate_control_med=True)
    assert d["tier"] in ("LOG_ONLY", "CONFIRM_FIRST") and d["page"] is not True
    assert d["tier"] == "LOG_ONLY" and d["route"] == "nurse_task" and any("sleep" in m for m in d["modifiers"]) and any("rate-control" in m for m in d["modifiers"])
def test_hr150_at_rest_with_chest_pain_is_absolute():
    d = E(cp({"hr": 150, "sbp": 132}))
    assert d["tier"] == "ABSOLUTE" and d["page"] is True and d["route"] == "escalate_human" and d["rule"] == "HT_CHEST_PAIN_VITALS"
def test_sbp85_with_chest_pain_is_absolute():
    d = E(cp({"hr": 88, "sbp": 85}))
    assert d["tier"] == "ABSOLUTE" and d["band"] == "A"
def test_hr118_after_exertion_confirms_with_longer_timeout():
    rest = E(cp({"hr": 118, "sbp": 138}))
    ex = E(cp({"hr": 118, "sbp": 138}, act="active", mse=5))
    assert rest["tier"] == ex["tier"] == "CONFIRM_FIRST"
    assert rest["band"] == "B" and rest["timeout_min"] == 5
    assert ex["band"] == "C" and ex["timeout_min"] == 30 and ex["timeout_min"] > rest["timeout_min"]
def test_poor_contact_reading_triggers_recheck():
    d = E(cp({"hr": {"value": 135, "quality_flags": ["poor_contact"]}}))
    assert d["tier"] == "CONFIRM_FIRST" and d["confirm_step"].startswith("device_recheck") and d["timeout_min"] == 5 and d["unreliable_vitals"] == ["hr"]
    d2 = E(cp({"hr": {"value": 280, "quality_flags": []}}))          # implausible value -> recheck, not a page
    assert d2["tier"] == "CONFIRM_FIRST" and d2["confirm_step"].startswith("device_recheck")
def test_unreliable_hr_but_reliable_band_A_bp_still_absolute():
    assert E(cp({"hr": {"value": 135, "quality_flags": ["motion"]}, "sbp": 86}))["tier"] == "ABSOLUTE"
# ---- modifiers and floors
def test_band_A_never_downgraded_to_log_only():
    d = E(cp({"hr": 38}, act="sleep"), rate_control_med=True, known_brady_range=[45, 55])
    assert d["raw_band"] == "A" and d["tier"] == "CONFIRM_FIRST" and d["band"] == "B" and d["timeout_min"] == 5
def test_hard_danger_limit_is_absolute_regardless_of_context():
    d = E(cp({"hr": 34}, act="sleep"), rate_control_med=True, known_brady_range=[30, 40])
    assert d["tier"] == "ABSOLUTE" and d["rule"] == "HT_VS_DANGER"
def test_reliable_ecg_change_absolute_unreliable_not():
    assert E(cp({"hr": 80}, sym={"ecg_change": True, "ecg_reliable": True}))["rule"] == "HT_CHEST_PAIN_ECG"
    assert E(cp({"hr": 80}, sym={"ecg_change": True, "ecg_reliable": False}))["tier"] == "LOG_ONLY"
def test_red_flags_raise_band_even_with_normal_vitals():
    d = E(cp({"hr": 82, "sbp": 128}, red=["diaphoresis", "radiation"]))
    assert d["tier"] == "CONFIRM_FIRST" and d["band"] == "B" and d["timeout_min"] == 5
    assert E(cp({"hr": 118, "sbp": 96}, red=["diaphoresis"]))["tier"] == "ABSOLUTE"   # B + multi-vital + red flag
def test_rate_control_med_makes_tachycardia_more_severe():
    assert E(cp({"hr": 112}))["band"] == "B"
    assert E(cp({"hr": 112}), rate_control_med=True)["tier"] == "ABSOLUTE"
def test_pacemaker_lower_rate_and_failure():
    assert E(cp({"hr": 60}), pacemaker_lower_rate=60)["tier"] == "LOG_ONLY"
    d = E(cp({"hr": 46}), pacemaker_lower_rate=60)
    assert d["tier"] == "ABSOLUTE" and any("below lower rate" in m for m in d["modifiers"])
def test_known_tachy_af_rate_lowers_band():
    assert E(cp({"hr": 108}))["band"] == "C"
    assert E(cp({"hr": 108}), known_tachy_range=[95, 110])["tier"] == "LOG_ONLY"
    assert E(cp({"hr": 135}), known_tachy_range=[95, 110])["tier"] == "ABSOLUTE"        # outside known range: no credit
def test_concordance():
    assert E(cp({"hr": 104}, concordant=True))["band"] == "B"
    assert E(cp({"hr": 114}, concordant=False))["band"] == "C"
    assert E(cp({"hr": 150}, concordant=False))["tier"] == "ABSOLUTE"                    # discordance never lowers A
def test_already_confirmed_escalates_now():
    d = E(cp({"hr": 116}, already_confirmed=True))
    assert d["tier"] == "CONFIRM_FIRST" and d["confirm_step"] == "already_confirmed" and d["timeout_min"] is None and d["page"] is True
def test_hospice_goals_redirect():
    d = E(cp({"hr": 150}), goals="comfort_only")
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "goals_of_care" and d["original_tier"] == "ABSOLUTE"
def test_no_chest_pain_returns_none_and_decision_logged():
    inp = cp({"hr": 150}); inp["symptoms"]["chest_pain"] = False
    assert T.evaluate_chest_pain(inp, P) is None
    b = T.Baseline("SYN-CP", 0.0, P); T.evaluate_chest_pain(cp({"hr": 150}), P, base=b)
    assert b.log[-1]["type"] == "CHEST_PAIN_DECISION" and b.log[-1]["tier"] == "ABSOLUTE"

# Decided rule (Wayne 2026-10-17): crescendo angina pattern with normal vitals -> CONFIRM_FIRST
def test_crescendo_pattern_with_normal_vitals_is_confirm_first():
    d = E(cp({"hr": 74, "sbp": 134}, act="active", mse=0, red=["crescendo_pattern"]), rate_control_med=True)
    assert d["raw_band"] == "D" and d["band"] == "C" and d["tier"] == "CONFIRM_FIRST" and d["route"] == "escalate_human"
    assert d["confirm_step"] == "patient_call" and d["timeout_min"] == 15          # no post-exertion x2 when vitals are normal
    disc = E(cp({"hr": 70, "sbp": 128}, red=["crescendo_pattern"], concordant=False))   # discordance cannot drop it back to log-only
    assert disc["tier"] == "CONFIRM_FIRST" and disc["band"] == "C"
    conf = E(cp({"hr": 70, "sbp": 128}, red=["crescendo_pattern"], already_confirmed=True))
    assert conf["tier"] == "CONFIRM_FIRST" and conf["confirm_step"] == "already_confirmed" and conf["page"] is True
def test_stable_frequency_with_normal_vitals_is_no_trigger():
    d = E(cp({"hr": 74, "sbp": 134}, act="active", mse=0, red=[]), rate_control_med=True)
    assert d["tier"] == "LOG_ONLY" and d["page"] is False and d["route"] == "nurse_task" and d["reason"] == "below_band_threshold"
    assert d["tier"] not in ("ABSOLUTE", "CONFIRM_FIRST")
