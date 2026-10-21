"""pytest for trigger_eval.py (three-layer VS rule). Synthetic sequences; 30-min sampling; ts in seconds."""
import json, math, shutil, copy, pytest
import trigger_eval as T
P = T.load_params("trigger_params.json")
DAY = T.DAY

def feed(b, vital, day0, day1, fn, act="rest", step_min=30):
    """Feed readings from day0 to day1; fn(t_days) -> value. Returns drift flags raised."""
    flags = []; t = day0 * DAY
    while t < day1 * DAY:
        f = b.add_sample({"vital": vital, "value": fn(t / DAY), "ts": b.enrolled_ts + t, "activity_state": act})
        if f: flags.append(f)
        t += step_min * 60
    return flags
def rd(b, vital, value, day, **kw):
    return {"vital": vital, "value": value, "ts": b.enrolled_ts + day * DAY + 10 * 3600, "activity_state": kw.pop("act", "rest"), **kw}
def wobble(t, amp=1.5): return amp * math.sin(t * 7.3) + 0.5 * math.sin(t * 31.1)
def established(vital="hr", level=78.0, days=14, params=P):
    b = T.Baseline("SYN-1", 0.0, params); feed(b, vital, 0, days, lambda t: level + wobble(t)); return b

# ---- layer 1: hard limits
def test_artifact_hr_280_rechecks_not_pages():
    b = established()
    d = T.evaluate(rd(b, "hr", 280, 14.2), b, P)
    assert d["tier"] == "ARTIFACT" and d["reason"] == "implausible_value" and d["page"] is False
    assert d["route"] == "silent_log" and d["recheck"]["step"] == "device_recheck"
    assert b.log[-1]["type"] == "DECISION" and b.log[-1]["tier"] == "ARTIFACT"
    assert not any(s[1] == 280 for s in b.samples["hr"])          # artifacts are never learned
    b.add_sample(rd(b, "hr", 280, 14.3)); assert not any(s[1] == 280 for s in b.samples["hr"])

def test_flatline_with_motion_and_fast_spo2_are_artifact():
    b = established()
    assert T.evaluate(rd(b, "hr", 72, 14.2, flat_s=90, motion=True), b, P)["reason"] == "flatline_with_motion"
    assert T.evaluate(rd(b, "hr", 72, 14.2, flat_s=90, motion=False), b, P)["tier"] == "NORMAL"
    d = T.evaluate(rd(b, "spo2", 79, 14.2, prev={"value": 97, "dt_s": 3}), b, P)   # 6 points/s
    assert d["tier"] == "ARTIFACT" and d["reason"] == "nonphysiologic_rate" and d["recheck"]["step"] == "fingertip_recheck"

def test_danger_is_absolute_regardless_of_baseline():
    b = established(level=118.0)                                    # high personal baseline
    d = T.evaluate(rd(b, "hr", 185, 14.2), b, P)
    assert d["tier"] == "ABSOLUTE" and d["rule"] == "HT_VS_DANGER" and d["page"] is True
    c = established("spo2", 88.0)                                    # COPD-like baseline 88
    assert T.evaluate(rd(c, "spo2", 79, 14.2), c, P)["tier"] == "ABSOLUTE"

def test_goals_of_care_redirects_absolute_to_hospice_nurse():
    b = established()
    d = T.evaluate(rd(b, "hr", 185, 14.2), b, P, {"goals": "comfort_only"})
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "goals_of_care" and d["route"] == "nurse_task" and d["original_tier"] == "ABSOLUTE"

def test_unreliable_low_spo2_is_suppressed_with_recheck():
    b = established("spo2", 95.0)
    d = T.evaluate(rd(b, "spo2", 85, 14.2, quality_flags=["poor_contact"]), b, P)
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "unreliable_reading" and d["recheck"]["step"] == "fingertip_recheck" and d["hitm_sample"]

# ---- layer 2: learning period
def test_learning_period_patient_uses_population_defaults_and_widened_confirm_first():
    b = T.Baseline("SYN-2", 0.0, P)
    feed(b, "hr", 0, 3, lambda t: 80 + wobble(t)); feed(b, "spo2", 0, 3, lambda t: 88.5 + 0.8 * math.sin(t * 9))
    assert b.phase("hr", 3 * DAY) == "learning"
    d = T.evaluate(rd(b, "hr", 112, 3), b, P)
    assert d["tier"] == "CONFIRM_FIRST" and d["reason"] == "outside_population_default_learning" and d["recheck"]["step"] == "patient_call"
    assert T.evaluate(rd(b, "hr", 84, 3), b, P)["tier"] == "NORMAL"
    d = T.evaluate(rd(b, "spo2", 87, 3), b, P)                       # COPD 87 during learning: no at-baseline suppression
    assert d["tier"] == "CONFIRM_FIRST" and d["recheck"]["step"] == "fingertip_recheck"
    # after onboarding the learned COPD baseline (87-90) allows at-baseline suppression; a real deviation still confirms first
    feed(b, "spo2", 3, 12, lambda t: 88.5 + 0.8 * math.sin(t * 9))
    assert b.phase("spo2", 12 * DAY) == "established"
    d = T.evaluate(rd(b, "spo2", 87, 12), b, P)
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "at_patient_baseline" and d["hitm_sample"]
    assert T.evaluate(rd(b, "spo2", 83, 12), b, P)["reason"] == "baseline_deviation"

def test_clinician_set_baseline_allows_suppression_during_learning():
    b = T.Baseline("SYN-3", 0.0, P, clinician_set={"spo2": {"rest": [86, 90], "set_by": "pulmonologist note"}})
    d = T.evaluate(rd(b, "spo2", 87, 2), b, P)
    assert d["tier"] == "SUPPRESSED" and d["basis"] == "clinician_set_baseline"

# ---- layer 3: adaptation
def test_baseline_reset_after_beta_blocker_start():
    b = established(level=78.0)
    pre = T.evaluate(rd(b, "hr", 60, 14.1), b, P)
    assert pre["tier"] == "CONFIRM_FIRST" and pre["reason"] == "baseline_deviation"   # without a reset, 60 looks like a deviation
    b.condition_change("rate_control_med", 14.2 * DAY, "metoprolol succinate 25 mg started")
    assert any(e["type"] == "PARTIAL_RESET" for e in b.log) and b.phase("hr", 14.3 * DAY) == "relearning"
    d = T.evaluate(rd(b, "hr", 60, 14.3), b, P)
    assert d["tier"] == "NORMAL" and d["reason"] == "relearning_within_population"
    assert T.evaluate(rd(b, "hr", 112, 14.3), b, P)["tier"] == "CONFIRM_FIRST"       # still bounded: outside population -> confirm
    feed(b, "hr", 14.2, 18.5, lambda t: 60 + wobble(t))
    assert b.phase("hr", 18.5 * DAY) == "established"
    st = b.stats("hr", "rest", b.enrolled_ts + 18.5 * DAY + 10 * 3600)
    assert 57 <= st["median"] <= 63
    assert T.evaluate(rd(b, "hr", 60, 18.5), b, P)["tier"] == "NORMAL"
    assert T.evaluate(rd(b, "hr", 78, 18.5), b, P)["tier"] == "CONFIRM_FIRST"        # the old normal is now a deviation

def drift_patient(params):
    b = T.Baseline("SYN-4", 0.0, params)
    feed(b, "hr", 0, 14, lambda t: 70 + wobble(t))
    flags = feed(b, "hr", 14, 35, lambda t: 70 + 0.6 * (t - 14) + wobble(t))     # +0.6 bpm/day for 21 days
    return b, flags

def test_slow_monotonic_drift_is_flagged_not_absorbed():
    b, flags = drift_patient(P)
    assert flags and flags[0]["flag"] == "SUBTLE_DETERIORATION_TREND"
    assert "hr" in b.frozen and any(e["type"] == "DRIFT_FLAG" for e in b.log)
    t = b.enrolled_ts + 35 * DAY + 10 * 3600
    assert b.stats("hr", "rest", t)["median"] < 71.5                  # the drift was not learned as the new normal
    d = T.evaluate(rd(b, "hr", 82, 35), b, P)
    assert d["route"] == "provider_task" and d["drift_flag"]["reason"] == "SUBTLE_DETERIORATION_TREND"
    b.clear_drift("hr", t, approved_by="reviewing clinician", note="reviewed")
    assert "hr" not in b.frozen and b.log[-1]["type"] == "DRIFT_CLEARED"
    with pytest.raises(PermissionError): b.clear_drift("hr", t, approved_by="")

def test_without_drift_guard_the_drift_would_be_absorbed():
    p = copy.deepcopy(P); p["adaptation"]["drift_guard"]["enabled"] = False
    b, flags = drift_patient(p)
    assert not flags
    t = b.enrolled_ts + 35 * DAY + 10 * 3600
    assert b.stats("hr", "rest", t)["median"] > 72.5                  # baseline crept up with the drift: why the guard is needed
    assert T.evaluate(rd(b, "hr", 82, 35), b, p)["tier"] in ("NORMAL", "WATCH")

def test_drift_explained_by_condition_change_is_not_flagged():
    b = T.Baseline("SYN-5", 0.0, P)
    feed(b, "hr", 0, 14, lambda t: 62 + wobble(t))
    b.condition_change("rate_control_med", 14 * DAY, "beta-blocker stopped (planned)")
    flags = feed(b, "hr", 14, 26, lambda t: 62 + 1.2 * (t - 14) + wobble(t))
    assert not flags and any(e["type"] == "DRIFT_EXPLAINED" for e in b.log)

def test_learned_baseline_is_clamped_inside_bounds_and_logged():
    b = established(level=130.0)                                      # learn_bounds hr [40,120]
    st = b.stats("hr", "rest", b.enrolled_ts + 14.2 * DAY)
    assert st["median"] == 120 and any(e["type"] == "BOUND_CLAMP" for e in b.log)

def test_params_change_only_by_named_human(tmp_path):
    f = tmp_path / "p.json"; shutil.copy("trigger_params.json", f)
    for who in ("", None, "engine", "auto-tuner"):
        with pytest.raises(PermissionError): T.apply_param_change(str(f), ["hard_limits", "hr", "implausible_high"], 240, who, "x")
    with pytest.raises(ValueError):                                   # would put danger above implausible
        T.apply_param_change(str(f), ["hard_limits", "hr", "implausible_high"], 170, "W. Allen Satz", "test")
    p = T.apply_param_change(str(f), ["hard_limits", "hr", "implausible_high"], 240, "W. Allen Satz", "test change")
    assert p["change_log"][-1]["approved_by"] == "W. Allen Satz" and p["hard_limits"]["hr"]["implausible_high"] == 240
    assert json.load(open("trigger_params.json"))["hard_limits"]["hr"]["implausible_high"] == 250   # repo file untouched

def test_shipped_params_validate_and_are_placeholders():
    T.validate_params(P); assert "PLACEHOLDER" in P["status"]
    # only named-human changes in the log (Wayne's crescendo decision, 2026-10-17)
    assert all(e["approved_by"] and not e["approved_by"].lower().startswith(("engine", "auto", "system", "model")) for e in P["change_log"])

def test_state_roundtrip():
    b, _ = drift_patient(P)
    c = T.Baseline.from_dict(json.loads(json.dumps(b.to_dict())), P)
    t = b.enrolled_ts + 35 * DAY + 10 * 3600
    assert c.stats("hr", "rest", t) == b.stats("hr", "rest", t) and c.frozen == b.frozen and len(c.log) == len(b.log)
