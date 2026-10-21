"""Dual-model Jev stage tests (SYNTHETIC, no API calls)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import dual_jev as D, jev_run as J  # noqa: E402

def test_defaults():
    assert J.DEFAULT_MODELS == D.DUAL_MODELS == ["liquid/d1-ultra", "perplexity/pplx-decider-v1.2"]
    assert D.DEFAULT_RULE == "cautious_max_hitm"

def test_combine_rules():
    assert D.combine("cautious_max_hitm", "nurse_task", "nurse_task") == ("nurse_task", False)
    assert D.combine("cautious_max_hitm", "nurse_task", "urgent_page") == ("urgent_page", True)
    assert D.combine("cautious_max", "provider_task", "silent_log") == ("provider_task", False)
    assert D.combine("agree_else_hitm", "silent_log", "nurse_task") == ("silent_log", True)
    assert D.combine("cautious_max_hitm", None, "nurse_task") == ("nurse_task", True)
    assert D.combine("cautious_max_hitm", None, None) == (None, True)

def test_never_lowers_either_model():
    R = D.S.ROUTES
    for a in R:
        for b in R:
            r, _ = D.combine("cautious_max", a, b); assert D.RK[r] == max(D.RK[a], D.RK[b])

def test_layer1_first():
    absolute = {"tier": "ABSOLUTE"}; goals = {"tier": "SUPPRESSED", "reason": "goals_of_care"}; none = {"tier": None}
    assert D.dual_route(absolute, "silent_log", "silent_log") == ("urgent_page", "layer1", False)
    assert D.dual_route(goals, "urgent_page", "urgent_page") == ("nurse_task", "layer1_goals", False)
    assert D.dual_route(none, "silent_log", "provider_task") == ("provider_task", "jev", True)
