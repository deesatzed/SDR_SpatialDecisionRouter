"""v1.8 learning-period rule (Wayne 2026-10-18). SYNTHETIC."""
import copy, os, sys, pytest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import trigger_eval as T
P = T.load_params(os.path.join(HERE, "trigger_params.json"))
DAY = T.DAY
def ev(vital, x, day, act="rest", p=P, base=None):
    b = base or T.Baseline("t", 0.0, p)
    return T.evaluate({"vital": vital, "value": x, "ts": day * DAY + 9 * 3600, "activity_state": act}, b, p, {})
def test_param_present_and_versioned():
    assert P["learning"]["outside_population_default_tier"] == "CONFIRM_FIRST"
    assert tuple(int(x) for x in P["version"].split("-")[0].split(".")) >= (0, 8)   # v1.10 bumped to 0.10
    assert any(e.get("keys") == ["learning", "outside_population_default_tier"] and e["approved_by"] == "Wayne" for e in P["change_log"])
def test_spo2_87_on_learning_day4_confirms_not_silent():   # the ST3-001 pattern
    d = ev("spo2", 87, 4)
    assert d["tier"] == "CONFIRM_FIRST" and d["route"] == "urgent_page" and d["reason"] == "outside_population_default_learning"
@pytest.mark.parametrize("vital,x", [("hr", 112), ("hr", 44), ("rr", 26), ("spo2", 90)])
def test_beyond_population_default_during_learning_confirms(vital, x):
    lo, hi = P["population_defaults"][vital]["rest"]
    assert not (lo <= x <= hi)
    assert ev(vital, x, 3)["tier"] == "CONFIRM_FIRST"
def test_within_population_default_during_learning_is_silent():
    assert ev("hr", 72, 3)["tier"] == "NORMAL" and ev("spo2", 96, 3)["tier"] == "NORMAL"
def test_no_at_baseline_suppression_while_learning():
    assert ev("spo2", 87, 2)["tier"] != "SUPPRESSED"
def test_clinician_set_baseline_still_allows_suppression_while_learning():
    b = T.Baseline("t", 0.0, P); b.clinician_set["spo2"] = {"rest": [85, 90]}
    assert ev("spo2", 87, 2, base=b)["tier"] == "SUPPRESSED"
def test_danger_limit_still_absolute_while_learning():
    assert ev("spo2", P["hard_limits"]["spo2"]["danger_low"], 2)["tier"] == "ABSOLUTE"
def test_silent_learning_tier_is_rejected():
    p = copy.deepcopy(P); p["learning"]["outside_population_default_tier"] = "NORMAL"
    with pytest.raises(ValueError): T.validate_params(p)
