"""Layer 1 adapter + router + v1.8 prompt tests (SYNTHETIC)."""
import json, os, sys, copy
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L
import jev_run as J
LABEL_FIELDS = ("expected_route", "acceptable_alternates", "hard_trigger", "hard_trigger_rule", "trigger_tier", "confirm_step", "confirm_timeout_min",
                "suppression_reason", "baseline_layer", "escalation_target", "route_basis", "rationale", "decisive_feature", "category", "difficulty",
                "subtle_deterioration", "chest_pain_eval", "router_input", "clinician_override", "secondary_triggers")
def test_router_rules():
    assert L.route({"tier": "ABSOLUTE"}, "silent_log") == ("escalate_human", "layer1")
    assert L.route({"tier": "CONFIRM_FIRST"}, "nurse_task") == ("escalate_human", "layer1_confirm")
    assert L.route({"tier": "SUPPRESSED", "reason": "goals_of_care"}, "escalate_human") == ("nurse_task", "layer1_goals")
    assert L.route({"tier": "SUPPRESSED", "reason": "explained"}, "escalate_human") == ("wake_specialist", "jev_capped")
    assert L.route({"tier": "SUPPRESSED", "reason": "explained", "acute_presentation": True}, "escalate_human") == ("escalate_human", "jev_capped")
    assert L.route({"tier": "SUPPRESSED", "reason": "below_band_threshold"}, "silent_log") == ("nurse_task", "jev_capped")
    assert L.route({"tier": None}, "silent_log") == ("silent_log", "jev")
def _lib():
    for p in (os.environ.get("ACCEPTED_JSON"), os.path.join(HERE, "..", "library", "library_v2_smart_accepted.json"),
              "/workspace/jevfly_smoke/library_v2/smart_triggers/library_v2_smart_accepted.json"):
        if p and os.path.exists(p): return json.load(open(p))["cases"]
def test_layer1_reads_fact_fields_only():
    for c in _lib():
        stripped = {k: v for k, v in copy.deepcopy(c).items() if k not in LABEL_FIELDS}
        a, b = L.evaluate_case(c), L.evaluate_case(stripped)
        assert (a["tier"], a.get("reason"), a.get("rule")) == (b["tier"], b.get("reason"), b.get("rule")), c["case_id"]
def test_layer1_never_pages_a_non_trigger_case_and_st3_001_confirms():
    cs = {c["case_id"]: c for c in _lib()}
    assert all(L.evaluate_case(c)["tier"] not in ("ABSOLUTE", "CONFIRM_FIRST") for c in cs.values() if not c.get("trigger_tier"))
    assert L.evaluate_case(cs["ST3-001"])["tier"] == "CONFIRM_FIRST"
def test_v18_monitoring_status_and_policy_have_no_labels():
    assert J.monitoring_status({"phase": "learning", "monitoring_day": 4, "learning_days_total": 10}).startswith("Monitoring status: day 4 of a 10-day learning period")
    assert J.monitoring_status(None) is None
    assert not J.LEAK.search(J.POLICY + J.POLICY_V18_ADD)
