import json, os, shutil, sys
import pytest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import promotion as pm

SEED = os.path.join(ROOT, "data", "replay_seed")
PACK = os.path.join(SEED, "replay", "seed")


def train():
    return [json.loads(l) for l in open(os.path.join(SEED, "train.jsonl"))]


def held():
    return {a["source_id"] for a in pm.load_pack(PACK)[2].values()}


def cands():
    return {c["area"]: c for c in pm.critic(train(), [], exclude_ids=held())}


def copy_pack(tmp_path):
    d = tmp_path / "pack"; shutil.copytree(PACK, d); return str(d)


def test_critic_proposes_and_real_pattern_wins():
    c = cands()
    assert set(c) == {"personal_finance", "ed_triage"}
    e = pm.evaluate(PACK, [], c["personal_finance"])
    assert e["verdict"] == "passed" and e["metrics"]["n"] >= pm.MARGIN["n_min"]
    assert e["metrics"]["accuracy_delta"] >= pm.MARGIN["delta_min"] and e["metrics"]["delta_interval"][0] > 0
    assert e["metrics"]["changed"] and all(r["after"] == "Hold — gather info" for r in e["metrics"]["changed"])
    assert e["evaluator"]["version"] == pm.EVALUATOR_VERSION and e["replay"]["cases_sha256"]


def test_spurious_clinical_candidate_loses_on_every_rule():
    e = pm.evaluate(PACK, [], cands()["ed_triage"])
    assert e["verdict"] == "failed"
    r = " | ".join(e["reasons"])
    assert "critical misses rise" in r and "clinical guard" in r and "margin" in r


def test_margin_rules():
    base = {"n": 30, "accuracy_delta": 0.1, "sign": {"lo": 0.7}, "wins": 5, "losses": 1,
            "critical_misses": {"champion": 0, "candidate": 0}, "escalations_removed": 0}
    assert pm.evaluate_rules(base, "personal_finance") == ("passed", [])
    assert pm.evaluate_rules(base | {"n": 10}, "personal_finance")[0] == "failed"
    assert pm.evaluate_rules(base | {"accuracy_delta": 0.04}, "personal_finance")[0] == "failed"
    assert pm.evaluate_rules(base | {"sign": {"lo": 0.5}}, "personal_finance")[0] == "failed"
    assert pm.evaluate_rules(base | {"critical_misses": {"champion": 0, "candidate": 1}}, "personal_finance")[0] == "failed"
    assert pm.evaluate_rules(base | {"escalations_removed": 1}, "ed_triage")[0] == "failed"
    assert pm.evaluate_rules(base | {"escalations_removed": 1}, "personal_finance")[0] == "passed"   # guard is clinical-only


def test_replay_tamper_detected(tmp_path):
    d = copy_pack(tmp_path)
    p = os.path.join(d, "answers.jsonl"); s = open(p).read().replace("Hold — gather info", "Accept plan", 1); open(p, "w").write(s)
    with pytest.raises(pm.ReplayTampered):
        pm.evaluate(d, [], cands()["personal_finance"])


def test_leak_in_cases_detected(tmp_path):
    d = copy_pack(tmp_path)
    rows = [json.loads(l) for l in open(os.path.join(d, "cases.jsonl"))]
    rows[0]["outcome"] = "Accept plan"
    with open(os.path.join(d, "cases.jsonl"), "w") as f:
        for r in rows: f.write(json.dumps(r, sort_keys=True) + "\n")
    m = json.load(open(os.path.join(d, "manifest.json")))
    import hashlib; m["cases_sha256"] = hashlib.sha256(open(os.path.join(d, "cases.jsonl"), "rb").read()).hexdigest()   # re-hashed: not tamper, still a leak
    json.dump(m, open(os.path.join(d, "manifest.json"), "w"))
    with pytest.raises(pm.LeakageError):
        pm.evaluate(d, [], cands()["personal_finance"])


def test_policy_sees_only_blinded_fields():
    case = json.loads(open(os.path.join(PACK, "cases.jsonl")).readline())
    with pytest.raises(pm.LeakageError):
        pm.apply_policy([], case | {"human_answer": "x"})


def test_candidate_trained_on_held_out_is_refused():
    c = dict(cands()["personal_finance"]); c["evidence_refs"] = c["evidence_refs"] + [sorted(held())[0]]
    with pytest.raises(pm.LeakageError):
        pm.evaluate(PACK, [], c)
    # and the critic itself drops held-out ids when told to
    leaky = pm.critic(train() + [{"id": "x"}], [], exclude_ids={"x"})
    assert all("x" not in c["evidence_refs"] for c in leaky)


def test_evaluator_tamper_detected(monkeypatch):
    monkeypatch.setitem(pm.MARGIN, "delta_min", 0.0)   # loosening the pre-registered margin after the fact
    with pytest.raises(pm.EvaluatorTampered):
        pm.evaluate(PACK, [], cands()["personal_finance"])


def test_champion_already_has_rule_no_reproposal():
    c = cands()["personal_finance"]
    assert all(x["area"] != "personal_finance" for x in pm.critic(train(), [c["rule"]], exclude_ids=held()))


def test_llm_critic_is_a_stub_that_only_proposes():
    assert pm.critic_llm() == []


def test_app_bundle_copy_is_identical():
    app = os.path.join(ROOT, "SpatialDecisionRouter", "Resources", "ReplaySeed")
    for s, d in (("train.jsonl", "replay_train.jsonl"), ("replay/seed/cases.jsonl", "replay_cases.jsonl"),
                 ("replay/seed/answers.jsonl", "replay_answers.jsonl"), ("replay/seed/manifest.json", "replay_manifest.json")):
        assert open(os.path.join(SEED, s), "rb").read() == open(os.path.join(app, d), "rb").read(), d
