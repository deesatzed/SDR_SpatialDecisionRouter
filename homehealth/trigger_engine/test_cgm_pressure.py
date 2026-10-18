"""CGM pressure-low artifact rule (trigger_params.json -> cgm_pressure_low, placeholders)."""
import trigger_eval as T
P = T.load_params("trigger_params.json")
def ev(value, cgm, goals=None):
    b = T.Baseline("p", 0.0, P)
    return T.evaluate({"vital": "glucose", "value": value, "ts": 99 * 86400.0, "activity_state": "sleep", "source": "cgm", "cgm": cgm}, b, P, {"goals": goals})

def test_pinned_sensor_low_refuted_by_fingerstick_is_suppressed_not_absolute():
    d = ev(52, {"overnight": True, "pressure_documented": True, "fingerstick": {"value": 104, "minutes_apart": 10}, "symptoms": False})
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "unreliable_reading" and d["page"] is False and d["route"] == "silent_log"
    assert "pressure_documented" in d["cgm_signs"] and "discordant_fingerstick" in d["cgm_signs"]
def test_pinned_sensor_low_without_fingerstick_is_artifact_with_fingerstick_recheck():
    d = ev(52, {"overnight": True, "pressure_documented": True, "fingerstick": None, "symptoms": False})
    assert d["tier"] == "ARTIFACT" and d["recheck"]["step"] == "fingerstick_recheck" and d["recheck"]["timeout_min"] == 15 and d["page"] is False
    d2 = ev(50, {"overnight": True, "sensor_side_sleep": True})               # sleeping on the sensor side overnight
    assert d2["tier"] == "ARTIFACT"
    d3 = ev(50, {"overnight": False, "sensor_side_sleep": True})              # sensor-side cue counts only overnight
    assert d3["tier"] == "ABSOLUTE"
    d4 = ev(48, {"drop_rebound": True})                                       # rapid drop and rebound
    assert d4["tier"] == "ARTIFACT"
def test_symptomatic_low_confirmed_by_fingerstick_is_absolute():
    d = ev(47, {"overnight": True, "fingerstick": {"value": 44, "minutes_apart": 10}, "symptoms": True})
    assert d["tier"] == "ABSOLUTE" and d["page"] is True and d["rule"] == "HT_VS_DANGER" and d["reason"].endswith("fingerstick_confirmed")
def test_confirmed_low_stays_absolute_even_with_pressure_signs():
    d = ev(50, {"overnight": True, "pressure_documented": True, "fingerstick": {"value": 51, "minutes_apart": 5}})
    assert d["tier"] == "ABSOLUTE"
def test_symptoms_keep_absolute_even_when_pressure_suspected():
    d = ev(50, {"overnight": True, "pressure_documented": True, "symptoms": True})
    assert d["tier"] == "ABSOLUTE" and d["reason"] == "hard_limit_danger_symptomatic"
def test_no_signs_no_fingerstick_falls_through_to_hard_limit():
    d = ev(50, {"overnight": True})
    assert d["tier"] == "ABSOLUTE" and d["reason"] == "hard_limit_danger"
def test_stale_fingerstick_outside_window_is_ignored():
    d = ev(52, {"overnight": True, "pressure_documented": True, "fingerstick": {"value": 110, "minutes_apart": 240}})
    assert d["tier"] == "ARTIFACT"
def test_goals_of_care_still_apply_to_confirmed_low():
    # v1.5 hospice narrowing (Wayne 2026-10-18): a single asymptomatic danger low is still suppressed to the same-shift hospice nurse ...
    d = ev(46, {"fingerstick": {"value": 45, "minutes_apart": 5}}, goals="comfort_only")
    assert d["tier"] == "SUPPRESSED" and d["reason"] == "goals_of_care" and d["route"] == "nurse_task" and d["notify"] == "hospice_nurse_same_shift"
    # ... but a SYMPTOMATIC low is an urgent, treatable, goal-consistent comfort problem: not suppressed, urgent hospice-nurse page now
    s = ev(46, {"symptoms": True}, goals="comfort_only")
    assert s["tier"] == "ABSOLUTE" and s["route"] == "escalate_human" and s["escalation_target"] == "hospice_nurse" and s["notify"] == "hospice_nurse_urgent_page"
def test_rule_only_applies_at_or_below_danger_and_only_for_cgm():
    assert ev(60, {"pressure_documented": True})["tier"] not in ("ARTIFACT", "ABSOLUTE")
    b = T.Baseline("p", 0.0, P)
    d = T.evaluate({"vital": "glucose", "value": 50, "ts": 99 * 86400.0, "source": "fingerstick"}, b, P, {})
    assert d["tier"] == "ABSOLUTE"
