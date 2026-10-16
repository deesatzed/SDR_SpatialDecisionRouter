"""M6: the promotion gate cannot be bypassed from the Python harness.
Thresholds are the pre-registered PLACEHOLDERS in promotion.MARGIN; tests read them, never restate numbers."""
import json, os, sys
import pytest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import promotion as pm

SEED = os.path.join(ROOT, "data", "replay_seed")
PACK = os.path.join(SEED, "replay", "seed")
M = pm.MARGIN


def base(**kw):
    m = {"n": M["n_min"], "accuracy_delta": M["delta_min"], "sign": {"lo": M["sign_lo_min"] + 0.01}, "wins": 1, "losses": 0,
         "critical_misses": {"champion": 0, "candidate": 0}, "escalations_removed": 0}
    m.update(kw); return m


def test_boundaries_are_inclusive_where_preregistered():
    assert pm.evaluate_rules(base(), "personal_finance")[0] == "passed"           # n == n_min, Δ == margin
    assert pm.evaluate_rules(base(n=M["n_min"] - 1), "personal_finance")[0] == "failed"
    assert pm.evaluate_rules(base(sign={"lo": M["sign_lo_min"]}), "personal_finance")[0] == "failed"  # must be strictly above


@pytest.mark.parametrize("area", sorted(M["clinical_areas"]))
def test_clinical_guard_applies_to_every_clinical_area(area):
    v, why = pm.evaluate_rules(base(escalations_removed=1), area)
    assert v == "failed" and any("clinical guard" in w for w in why)


def test_failures_accumulate_not_short_circuit():
    v, why = pm.evaluate_rules(base(n=0, accuracy_delta=-1, sign={"lo": 0}, critical_misses={"champion": 0, "candidate": 2}), "personal_finance")
    assert v == "failed" and len(why) == 4


def test_policy_refuses_unblinded_case():
    with pytest.raises(pm.LeakageError):
        pm.apply_policy([], {"case_id": "x", "agent_proposal": "a", "features": {}, "card": "", "outcome": "leak"})


def test_harness_never_promotes(tmp_path):
    out = tmp_path / "r.json"
    assert pm.main(["--train", os.path.join(SEED, "train.jsonl"), "--replay", PACK, "-o", str(out)]) == 0
    rep = json.load(open(out))
    assert "only a signed Principal approval" in rep["note"]
    for e in rep["evaluations"]:
        assert e["verdict"] in ("passed", "failed")
        assert not ({"promoted", "champion_generation", "decision", "rules_after"} & set(e))
