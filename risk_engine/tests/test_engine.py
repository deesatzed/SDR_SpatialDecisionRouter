"""Acceptance-style tests: hand-computed reference values on a tiny network, invalid input rejection, reproducibility.
Tolerances fixed before running: exact inference 1e-9; Monte Carlo frequency 0.01 at n=20000."""
import copy, json, threading, urllib.request, urllib.error
import pytest
from risk_engine.params import validate, load_params, ParamError, iter_entries
from risk_engine.model import RiskModel, assess, EvidenceError

def E(v): return {"value": v, "source": "placeholder", "citation": ""}

def tiny(prior=0.1):
    return validate({
        "meta": {"version": 0},
        "thresholds": {"doubt_posterior": E(0.15), "critical_severity": E(4), "critical_escalate": E(0.05), "min_ruleout": E(0.5)},
        "labels": [{"max": 0.05, "label": "very unlikely"}, {"max": 0.2, "label": "unlikely"}, {"max": 0.5, "label": "possible"}, {"max": 1.0, "label": "likely"}],
        "context_priors": {"companion": E(0.3)},
        "truths": {"pregnant": {"states": ["no", "yes"], "sensitive": True, "question": "q?", "prior": {"tiny": E(prior)},
                   "report": {"false_positive": E(0.01), "recall_miss": E(0.05), "conceal_base": E(0.3),
                              "conceal_context": {"companion": E(0.5)}, "recall_context": {}},
                   "signals": {}, "ask": {"reveal": E(0.8), "false_positive": E(0.02)}}},
        "complaints": {"tiny": {"truths": ["pregnant"], "context": ["companion"], "plan_flags": [],
                       "dx": {"ectopic": {"parents": ["pregnant"], "severity": 5, "worst_miss": "w", "plan_change": "pc", "mitigated_by": ["escalate"],
                                          "cpt": [{"when": {"pregnant": "no"}, "p": E(0.0)}, {"when": {"pregnant": "yes"}, "p": E(0.2)}]}}}},
        "loss": {"miss_cost_by_severity": {str(k): E(c) for k, c in {1: 1, 2: 5, 3: 20, 4: 60, 5: 100}.items()},
                 "modify_cost": E(1.0), "escalate_cost": E(10.0), "residual_after_mitigation": E(0.1)}})

REQ = {"complaint": "tiny", "context": {"companion": False}, "reports": {"pregnant": "neg"}}

# ---------- hand-computed reference values ----------
def test_prior_marginals():
    m = RiskModel(tiny(), "tiny")
    assert m.p_risky({}, "pregnant") == pytest.approx(0.1, abs=1e-9)
    assert m.p_dx({})["dx_ectopic"] == pytest.approx(0.02, abs=1e-9)

def test_negative_report_posterior_no_companion():
    # P(neg|yes) = 1-(1-.05)(1-.3) = .335 ; P(neg|no) = .99
    want = 0.1 * 0.335 / (0.1 * 0.335 + 0.9 * 0.99)
    r = assess(tiny(), REQ)
    assert r["truths"][0]["posterior"] == pytest.approx(want, abs=1e-9)
    assert r["truths"][0]["state"] == "Reliable"          # below doubt threshold

def test_negative_report_posterior_with_companion():
    # conceal = 1-(.7)(.5) = .65 ; P(neg|yes) = 1-(.95)(.35) = .6675
    want = 0.1 * 0.6675 / (0.1 * 0.6675 + 0.9 * 0.99)
    r = assess(tiny(), REQ | {"context": {"companion": True}})
    assert r["truths"][0]["posterior"] == pytest.approx(want, abs=1e-9)

def test_reliability_states():
    hi = tiny(prior=0.4)
    assert assess(hi, REQ | {"context": {"companion": True}})["truths"][0]["state"] == "Said differently on purpose"
    assert assess(hi, {"complaint": "tiny", "context": {"companion": False}})["truths"][0]["state"] == "Not said"
    assert assess(hi, {"complaint": "tiny", "reports": {"pregnant": "pos"}})["truths"][0]["state"] == "Reliable"

def test_if_wrong_range():
    r = assess(tiny(), REQ)
    iw = r["truths"][0]["if_wrong"]
    assert iw["low"] == pytest.approx(0.0, abs=1e-12) and iw["high"] == pytest.approx(0.2, abs=1e-9)
    assert iw["current"] == pytest.approx(0.2 * r["truths"][0]["posterior"], abs=1e-9)

def test_voi_hand_computed():
    p = 0.1 * 0.335 / (0.1 * 0.335 + 0.9 * 0.99)
    def best(pp):  # actions: sign_off=100*P(ect); modify=1+100*P; escalate=10+0.1*100*P
        e = 0.2 * pp; return min(100 * e, 1 + 100 * e, 10 + 10 * e)
    pa = p * 0.8 + (1 - p) * 0.02
    p_pos = p * 0.8 / pa; p_neg = p * 0.2 / (1 - pa)
    want = best(p) - (pa * best(p_pos) + (1 - pa) * best(p_neg))
    q = assess(tiny(), REQ)["voi"][0]
    assert q["voi"] == pytest.approx(want, abs=1e-9)
    assert q["p_answer_pos"] == pytest.approx(pa, abs=1e-9)
    assert want > 0

def test_escalation_rule():
    r = assess(tiny(prior=0.5), {"complaint": "tiny", "context": {"companion": True}})
    e = r["escalation"]
    assert e["p_critical"] == pytest.approx(0.1, abs=1e-9)
    assert e["recommend"] == (e["p_critical"] > 0.05 and e["best_question_ruleout"] < 0.5)
    assert assess(tiny(), REQ)["escalation"]["recommend"] is False

def test_answer_updates_posterior():
    p = 0.1 * 0.335 / (0.1 * 0.335 + 0.9 * 0.99)
    pa = p * 0.8 + (1 - p) * 0.02
    r = assess(tiny(), REQ | {"answers": {"pregnant": "pos"}})
    assert r["truths"][0]["posterior"] == pytest.approx(p * 0.8 / pa, abs=1e-9)
    assert r["voi"] == []    # already asked

# ---------- invalid input rejection ----------
@pytest.mark.parametrize("mut,msg", [
    (lambda d: d["truths"]["pregnant"]["report"].__setitem__("false_positive", E(1.5)), "outside"),
    (lambda d: d["truths"]["pregnant"]["report"].__setitem__("recall_miss", {"value": 0.1, "source": "literature", "citation": ""}), "citation"),
    (lambda d: d["truths"]["pregnant"]["report"].__setitem__("recall_miss", {"value": 0.1, "source": "placeholder", "citation": "Smith 2020"}), "citation"),
    (lambda d: d["truths"]["pregnant"]["report"].__setitem__("recall_miss", {"value": 0.1, "source": "guess", "citation": ""}), "source"),
    (lambda d: d["complaints"]["tiny"]["dx"]["ectopic"]["cpt"].pop(), "exactly once"),
    (lambda d: d["complaints"]["tiny"]["dx"]["ectopic"].__setitem__("parents", ["bogus"]), "parent"),
    (lambda d: d["loss"].__setitem__("escalate_cost", E(-1)), ">= 0"),
])
def test_invalid_params(mut, msg):
    d = copy.deepcopy(tiny()); mut(d)
    with pytest.raises(ParamError, match=msg):
        validate(d)

@pytest.mark.parametrize("req", [
    {"complaint": "nope"},
    {"complaint": "tiny", "context": {"martian": True}},
    {"complaint": "tiny", "context": {"companion": "yes"}},
    {"complaint": "tiny", "reports": {"pregnant": "maybe"}},
    {"complaint": "tiny", "reports": {"anticoag": "neg"}},
    {"complaint": "tiny", "answers": {"pregnant": True}},
    {"complaint": "tiny", "extra": 1},
])
def test_invalid_requests(req):
    with pytest.raises(EvidenceError):
        assess(tiny(), req)

# ---------- reproducibility ----------
def test_sampling_reproducible_and_calibrated():
    m = RiskModel(tiny(), "tiny")
    assert m.sample(50, 7) == m.sample(50, 7)
    assert m.sample(50, 7) != m.sample(50, 8)
    s = m.sample(20000, 1)
    assert sum(x["pregnant"] == "yes" for x in s) / 20000 == pytest.approx(0.1, abs=0.01)

def test_assess_deterministic():
    assert json.dumps(assess(tiny(), REQ), sort_keys=True) == json.dumps(assess(tiny(), REQ), sort_keys=True)

# ---------- shipped parameter file ----------
def test_shipped_params_all_placeholder_and_all_complaints_run():
    p = load_params()
    assert {e["source"] for _, e in iter_entries(p)} == {"placeholder"}
    for c in p["complaints"]:
        r = assess(p, {"complaint": c})
        assert r["engine"] == "bn" and r["param_source"] == "placeholder"
        for t in r["truths"]:
            assert 0 <= t["posterior"] <= 1 and t["state"] in ("Reliable", "Not said", "Said wrong", "Said differently on purpose")

# ---------- HTTP service ----------
def test_http_service():
    from http.server import ThreadingHTTPServer
    from risk_engine import service
    srv = ThreadingHTTPServer(("127.0.0.1", 0), service.H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    def post(path, body):
        rq = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(rq, timeout=5))
    try:
        assert json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5))["ok"]
        r = post("/assess", {"complaint": "chest_pain", "reports": {"substance": "neg"}})
        assert r["engine"] == "bn"
        assert "voi" in post("/voi", {"complaint": "head_injury"})
        with pytest.raises(urllib.error.HTTPError) as ei:
            post("/assess", {"complaint": "nope"})
        assert ei.value.code == 400
    finally:
        srv.shutdown()

def test_known_truth_fixes_posterior():
    r = assess(tiny(), {"complaint": "tiny", "known": {"pregnant": "no"}})
    assert r["truths"][0]["posterior"] == 0.0 and r["dx"]["ectopic"]["p"] == 0.0
