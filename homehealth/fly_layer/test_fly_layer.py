"""Tests for the Fly layer (SYNTHETIC). Runs without the GoalJevFly source; the end-to-end Fly test skips if it is absent."""
import copy, json, os, sys
import pytest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fly_flags as F, score_fly as SF, run_fly as RF  # noqa: E402

LABELS = ("expected_route", "acceptable_alternates", "trigger_tier", "hard_trigger", "hard_trigger_rule", "suppression_reason",
          "rationale", "decisive_feature", "grade", "difficulty", "subtle_deterioration", "category")

@pytest.fixture(scope="module")
def cases():
    return json.load(open(RF.find_accepted()))["cases"]

def test_flags_ignore_labels(cases):
    for c in cases[::9]:
        x = copy.deepcopy(c)
        for k in LABELS: x[k] = "silent_log" if k == "expected_route" else None
        assert F.derive_flags(x) == F.derive_flags(c), c["case_id"]

def test_flag_structure(cases):
    for c in cases[::7]:
        days = F.derive_flags(c)["days"]
        assert [d["day"] for d in days] == list(range(-7, 1))
        for prev, d in zip([None] + days, days):
            assert d["repeated"] == (d["latent"] and bool(prev and prev["latent"]))
            assert not d["verified"] or d["day"] == 0
            assert d["latent"] == bool(d["why"])

def test_split_whole_batches():
    batch = {f"LIB-{b}-{i:03d}": b for b in ("AA1", "BB2", "CC3", "DD4", "EE5") for i in range(10)}
    h1 = SF.split_batches(batch); h2 = SF.split_batches(dict(reversed(list(batch.items()))))
    assert h1 == h2 and 0 < len(h1) < 5
    assert sum(1 for b in batch.values() if b in h1) >= SF.HOLDOUT_FRAC * len(batch)

def test_pairs_within_batch(cases):
    for c in cases:
        if c.get("pair_id"): assert c["pair_id"].split("-")[0] == (c.get("src_batch") or c["case_id"].split("-")[0])

@pytest.mark.parametrize("rule", SF.RULES)
def test_combine_never_lowers(rule):
    for r in SF.ROUTES:
        for owner in ("jev", "jev_capped", "layer1", "layer1_confirm", "layer1_goals"):
            for hi in (False, True):
                out, _ = SF.combine(rule, r, owner, hi)
                assert SF.RK[out] >= SF.RK[r]
                if owner.startswith("layer1"): assert out == r   # Fly never overrides a Layer 1 decision (incl. goals of care)
                if rule == "flag_only": assert out == r

def test_flag_only_flags_disagreement():
    assert SF.combine("flag_only", "silent_log", "jev", True) == ("silent_log", True)
    assert SF.combine("flag_only", "escalate_human", "jev", False) == ("escalate_human", True)
    assert SF.combine("flag_only", "escalate_human", "jev", True) == ("escalate_human", False)

def test_fly_band():
    cuts = (0.3, 0.6, 0.9)
    assert [SF.fly_band(x, cuts) for x in (0.0, 0.5, 0.7, 0.95)] == SF.ROUTES

def test_fly_end_to_end(cases):
    src = os.environ.get("GOAL_FLY_SRC", RF.DEFAULT_SRC)
    if not os.path.isdir(src): pytest.skip("GoalJevFly source not available")
    receipt, FlyPolicy, OS, AK, AP = RF.load_fly(src)
    p = FlyPolicy(receipt, leak=0.8, threshold=0.5)
    cont = AP(AK.CONTINUE, "continue", "task/", "none", ("x",), "resume"); chk = AP(AK.CHECK, "check", "task/", "local", ("x",), "verify")
    quiet = {"days": [{"latent": False, "repeated": False, "verified": False} for _ in range(8)]}
    assert max(RF.run_case(p, quiet, OS, cont, chk)) == 0.0
    r = RF.run_case(p, F.derive_flags(cases[0]), OS, cont, chk); assert len(r) == 8
    assert RF.run_case(p, F.derive_flags(cases[0]), OS, cont, chk) == r   # reset_episode makes it deterministic
