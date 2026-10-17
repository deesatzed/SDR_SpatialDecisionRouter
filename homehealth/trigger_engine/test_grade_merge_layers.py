"""Unit tests for grade_merge.py smart + v2.3 VS-layer label checks (no API calls)."""
import sys, copy; sys.path.insert(0, "../prompts_v2")
import grade_merge as G
BASE = {"hard_trigger": True, "hard_trigger_rule": "HT_VS_IMPLAUSIBLE", "trigger_tier": "ARTIFACT", "confirm_step": "device_recheck", "confirm_timeout_min": 10,
        "suppression_reason": None, "expected_route": "silent_log", "acceptable_alternates": [], "baseline_layer": "hard_limit_artifact",
        "baseline_status": {"phase": "established", "monitoring_day": 40, "learning_days_total": 10, "last_condition_change": None},
        "subtle_deterioration": False, "caregiver_or_nurse_note": None}
def chk(**kw):
    c = copy.deepcopy(BASE); c.update(kw); return G.smart_checks(c) + G.layer_checks(c)
def test_valid_artifact(): assert chk() == []
def test_artifact_that_pages_is_flagged(): assert any("ARTIFACT must route" in i for i in chk(expected_route="escalate_human"))
def test_implausible_must_be_artifact(): assert any("HT_VS_IMPLAUSIBLE must be tier ARTIFACT" in i for i in chk(trigger_tier="CONFIRM_FIRST", confirm_step="patient_call", expected_route="escalate_human", baseline_layer=None))
def test_danger_is_absolute():
    assert chk(hard_trigger_rule="HT_VS_DANGER", trigger_tier="ABSOLUTE", confirm_step=None, confirm_timeout_min=None, expected_route="escalate_human", baseline_layer="hard_limit_danger") == []
    assert any("labelled ABSOLUTE" in i or "hard_limit_danger" in i for i in chk(hard_trigger_rule="HT_VS_DANGER", trigger_tier="CONFIRM_FIRST", confirm_step="patient_call", expected_route="escalate_human", baseline_layer="hard_limit_danger"))
def test_learning_period_cannot_suppress_at_baseline():
    kw = dict(hard_trigger_rule="HT_SPO2_LT88", trigger_tier="SUPPRESSED", confirm_step=None, confirm_timeout_min=None, suppression_reason="at_patient_baseline",
              baseline_layer="learning_period", baseline_status={"phase": "learning", "monitoring_day": 4, "learning_days_total": 10, "last_condition_change": None})
    assert any("during learning" in i for i in chk(**kw))
    assert not any("during learning" in i for i in chk(**kw, caregiver_or_nurse_note="visit: clinician-set baseline SpO2 86-90% (pulmonology)"))
def test_drift_must_not_be_silent():
    kw = dict(hard_trigger=False, hard_trigger_rule=None, trigger_tier=None, confirm_step=None, confirm_timeout_min=None, baseline_layer="drift_not_absorbed", subtle_deterioration=True, expected_route="wake_specialist")
    assert chk(**kw) == []
    assert any("learned away" in i for i in chk(**{**kw, "expected_route": "silent_log"}))
    assert any("without subtle_deterioration" in i for i in chk(**{**kw, "subtle_deterioration": False}))
def test_reset_needs_condition_change():
    kw = dict(hard_trigger=False, hard_trigger_rule=None, trigger_tier=None, confirm_step=None, confirm_timeout_min=None, baseline_layer="baseline_reset", expected_route="silent_log")
    assert any("last_condition_change" in i for i in chk(**kw))
    assert chk(**kw, baseline_status={"phase": "relearning", "monitoring_day": 70, "learning_days_total": 10, "last_condition_change": {"type": "rate_control_med", "day": -3}}) == []
