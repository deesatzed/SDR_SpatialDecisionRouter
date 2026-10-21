import score_jev as S
E = lambda **k: {"id": "X", "expected": "urgent_page", "acceptable": [], "trigger_tier": None, "difficulty": "hard", "hard_trigger": False, "pair_id": None, **k}
def test_alternates_and_alias():
    c = E(expected="provider_task", acceptable=["nurse_task_with_recheck"])
    assert S.correct("nurse_task", c) and S.correct("provider_task", c) and not S.correct("silent_log", c)
def test_critical_miss_only_for_escalate_needed_and_not_alternate():
    assert S.critical_miss("provider_task", E())
    assert not S.critical_miss("provider_task", E(acceptable=["provider_task"]))
    assert not S.critical_miss("urgent_page", E()) and not S.critical_miss(None, E())
    assert not S.critical_miss("silent_log", E(expected="nurse_task"))
def test_over_escalation_and_under_triage():
    assert S.over_escalation("urgent_page", E(expected="nurse_task"))
    assert not S.over_escalation("urgent_page", E(expected="nurse_task", acceptable=["urgent_page"]))
    assert S.under_triage("silent_log", E(expected="nurse_task")) and not S.under_triage("provider_task", E(expected="nurse_task"))
def test_layer1_absolute_forces_escalate_only_for_absolute():
    assert S.l1_pick("silent_log", E(trigger_tier="ABSOLUTE")) == "urgent_page"
    assert S.l1_pick("silent_log", E(trigger_tier="CONFIRM_FIRST")) == "silent_log"
    assert S.l1_pick(None, E(trigger_tier="ABSOLUTE")) == "urgent_page"
def test_brier():
    assert S.brier_bin(1.0, 1.0) == 0 and S.brier_bin(0.0, 1.0) == 1
    assert S.brier_multi({"urgent_page": 1.0}, "urgent_page") == 0
    assert abs(S.brier_multi({"silent_log": 1.0}, "urgent_page") - 2.0) < 1e-9
def test_score_system_weighted_pages_pairs():
    cs = [E(id="A", pair_id="P"), E(id="B", expected="silent_log", pair_id="P"), E(id="C", expected="nurse_task")]
    ex = {i: {"categories": ["x"], "subtle": False} for i in "ABC"}
    r = S.score_system(cs, {"A": "nurse_task", "B": "silent_log", "C": "urgent_page"}, {"A": "critical"}, ex)
    assert r["critical_miss_ids"] == ["A"] and r["critical_miss_weighted"] == 3
    assert r["over_escalation_ids"] == ["C"] and r["pages_per_100"] == round(100 / 3, 4) and r["over_escalation_rate"] == 0.5
    assert r["pairs_complete"] == 1 and r["pairs_both_correct"] == 0 and r["accuracy"] == round(1 / 3, 4)
def test_robustness():
    cs = [E(id="A")]
    rows = [{"case": "A", "variant": "base", "pick": "urgent_page"}, {"case": "A", "variant": "reversed", "pick": "nurse_task"},
            {"case": "A", "variant": "key_deleted", "pick": "nurse_task", "veto": 0.9}, {"case": "A", "variant": "missing_all", "pick": "urgent_page"}]
    r = S.robustness(cs, rows)
    assert r["reversed_same_pick"] == 0 and r["key_deleted_escalate_or_veto"] == 1 and r["missing_all_escalate"] == 1
def test_phi_guard_day_allowance():
    import phi_guard as G
    assert G.phi_hits("Day -7 to -1: HR 70; Day -2 14:00 to Day 0 16:00; HRV 29 ms. Sleep 6 h") == []
    assert [l for l, _ in G.phi_hits("Mrs. Smith, DOB 03/04/1931, jane@x.com")] == ["email", "date", "dob / birth", "name"]
