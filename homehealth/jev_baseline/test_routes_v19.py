"""SMART_TRIGGERS v1.9 route rename (Wayne 2026-10-21): canonical ids + legacy alias on read. SYNTHETIC; no API calls."""
import csv, json, os, sys
import pytest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "casegen"))
import routes as RT, score_jev as S, layer1_adapter as L, dual_jev as D  # noqa: E402
HH = os.path.join(HERE, "..")
LEGACY = ("wake_specialist", "escalate_human")

def test_canonical_ids_labels_definitions():
    assert RT.ROUTES == ["silent_log", "nurse_task", "provider_task", "urgent_page"]
    assert [RT.label(r) for r in RT.ROUTES] == ["silent", "nurse task", "provider task", "urgent page"]
    assert "same business day" in RT.DEFINITIONS["provider_task"] and "not a page" in RT.DEFINITIONS["provider_task"]
    assert "now" in RT.DEFINITIONS["urgent_page"] and "hospice nurse" in RT.DEFINITIONS["urgent_page"]

def test_legacy_alias_maps_on_read():
    assert RT.canon("wake_specialist") == "provider_task" and RT.canon("escalate_human") == "urgent_page"
    assert RT.canon("nurse_task") == "nurse_task" and RT.canon(None) is None and RT.canon("nurse_task_with_recheck") == "nurse_task_with_recheck"
    assert RT.label("escalate_human") == "urgent page" and RT.label("wake_specialist") == "provider task"
    r = RT.canon_row({"case": "X", "variant": "base", "pick": "escalate_human", "probs": {"escalate_human": 0.7, "wake_specialist": 0.2, "silent_log": 0.1}})
    assert r["pick"] == "urgent_page" and r["probs"] == {"urgent_page": 0.7, "provider_task": 0.2, "silent_log": 0.1}
    assert RT.canon_probs({"escalate_human": 0.25, "urgent_page": 0.25}) == {"urgent_page": 0.5}

def test_scoring_accepts_legacy_and_new_ids_identically():
    c = {"id": "X", "expected": "escalate_human", "acceptable": ["wake_specialist"], "trigger_tier": None}
    for old, new in (("escalate_human", "urgent_page"), ("wake_specialist", "provider_task"), ("silent_log", "silent_log")):
        assert S.correct(old, c) == S.correct(new, c) and S.critical_miss(old, c) == S.critical_miss(new, c)
    assert S.critical_miss("silent_log", c) and not S.critical_miss("escalate_human", c)
    assert S.over_escalation("escalate_human", {"expected": "nurse_task", "acceptable": []})
    assert S.brier_multi({"escalate_human": 1.0}, "escalate_human") == 0 == S.brier_multi({"urgent_page": 1.0}, "urgent_page")

def test_layer1_and_dual_take_legacy_picks():
    assert L.route({"tier": "SUPPRESSED", "reason": "explained"}, "escalate_human") == ("provider_task", "jev_capped")
    assert L.route({}, "wake_specialist") == ("provider_task", "jev")
    assert D.dual_route({}, "wake_specialist", "escalate_human") == ("urgent_page", "jev", True)
    assert D.dual_route({}, "escalate_human", "urgent_page") == ("urgent_page", "jev", False)

def test_load_picks_maps_stored_legacy_checkpoint(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [{"case": "A", "variant": "base", "pick": "wake_specialist"},
                                                   {"case": "B", "variant": "base", "pick": "escalate_human"},
                                                   {"case": "C", "variant": "base", "pick": "urgent_page"}]) + "\n")
    assert D.load_picks(str(p)) == {"A": "provider_task", "B": "urgent_page", "C": "urgent_page"}

def test_jev_prompt_v19_uses_new_ids_and_definitions(monkeypatch):
    import importlib
    monkeypatch.setenv("JEV_PROMPT", "v1.9"); import jev_run as J; J = importlib.reload(J)
    assert list(J.ROUTES) == RT.ROUTES and "same business day" in J.ROUTES["provider_task"] and "provider task" in J.policy()
    assert not J.LEAK.search(J.policy())   # the v1.9 policy text itself must pass the label-leak check
    assert J.LEAK.search("urgent_page") and J.LEAK.search("provider_task") and J.LEAK.search("escalate_human")
    monkeypatch.setenv("JEV_PROMPT", "v1.8"); J = importlib.reload(J)
    assert list(J.ROUTES) == ["silent_log", "nurse_task", "wake_specialist", "escalate_human"]   # v1.8 kept for reproducibility
    monkeypatch.delenv("JEV_PROMPT"); importlib.reload(J)

def test_casegen_maps_legacy_case_routes():
    G = pytest.importorskip("grade_merge")   # repo layout (homehealth/casegen)
    c = G.canon_case_routes({"expected_route": "escalate_human", "acceptable_alternates": ["wake_specialist", "nurse_task_with_recheck"],
                             "secondary_triggers": [{"if_confirmed_route": "escalate_human"}]})
    assert c["expected_route"] == "urgent_page" and c["acceptable_alternates"] == ["provider_task", "nurse_task_with_recheck"]
    assert c["secondary_triggers"][0]["if_confirmed_route"] == "urgent_page"

def test_stored_labels_use_v19_ids():
    for f in ("library/library_v2_smart_accepted.json", "library/library_v2_smart_Outcomes.csv", "holdout/holdout_v1_accepted.json",
              "holdout/holdout_v1_runner.json", "holdout/review_queue.csv", "trigger_engine/trigger_params.json"):
        p = os.path.join(HH, f)
        if not os.path.exists(p): pytest.skip("repo layout only")
        s = open(p).read()
        assert not any(t in s for t in LEGACY), f

def test_review_queue_clinician_rulings_kept_and_mapped():
    p = os.path.join(HH, "holdout", "review_queue.csv")
    if not os.path.exists(p): pytest.skip("repo layout only")
    rows = {r["case_id"]: r for r in csv.DictReader(open(p))}
    got = {k: v["CLINICIAN_RULING (route)"] for k, v in rows.items()}
    assert len(got) == 34 and all(got.values())                       # Wayne ruled all 34 (2026-10-21)
    assert all(v in RT.ROUTES + ["DROP"] for v in got.values())       # mapped to v1.9 ids
    assert {k for k, v in got.items() if v == "DROP"} == {"HO8-006", "HO7-013", "HO8-001"}
    assert got["HO1-005"] == "silent_log" and got["HO2-007"] == "nurse_task" and got["HO4-008"] == "nurse_task"
    assert got["HO8-020"] == got["HO8-025"] == got["HO7-021"] == got["HO8-015"] == "urgent_page"
    assert rows["HO7-021"]["living"] == "with spouse"                  # case fix
    assert "he is hard to wake" in rows["HO8-015"]["caregiver_or_nurse_note"] and "she is" not in rows["HO8-015"]["caregiver_or_nurse_note"]
