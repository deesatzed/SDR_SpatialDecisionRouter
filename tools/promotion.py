#!/usr/bin/env python3
"""M4 frozen-replay promotion harness (docs/SYMBIOSIS_PLAN.md M4; mirrors SpatialDecisionRouter/Core/PromotionEngine.swift).

  critic      proposes candidate per-area rules from HELD-IN ledger evidence. Deterministic by default; the LLM hook is a stub
              (no external calls) and, like the deterministic critic, can only PROPOSE (non-negotiable 8).
  evaluate    scores champion vs champion+candidate on a frozen, blinded replay pack (exporter output). Refuses if the manifest
              hashes do not match (tamper), if cases carry labels/outcomes or the candidate's evidence overlaps the held-out set
              (leakage), or if the evaluator source / pre-registered margin changed without a new lock (evaluator tamper).
  promotion   is NOT done here. A passing candidate only becomes eligible for a Principal card; only a human signature in the
              app promotes (there is no self-graded apply path).

Usage: python3 tools/promotion.py --train data/replay_seed/train.jsonl --replay data/replay_seed/replay/seed [-o report.json]
"""
from __future__ import annotations
import argparse, collections, hashlib, inspect, json, os, sys

EVALUATOR_VERSION = "replay-eval-v1"
# pre-registered BEFORE any candidate is seen; changing it changes the evaluator hash (needs a new lock = new version)
MARGIN = {"delta_min": 0.05, "n_min": 20, "sign_lo_min": 0.5, "interval": "90% normal approx",
          "clinical_areas": ["ed_triage"], "escalate_answers": ["Escalate"]}
CASE_KEYS = {"case_id", "domain", "context_id", "card", "options", "agent_proposal", "features"}
FORBIDDEN = ("outcome", "human_answer", "human_label", "demo_human_call", "source_id", "split_rating")
LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluator.lock")


class ReplayTampered(Exception): pass
class LeakageError(Exception): pass
class EvaluatorTampered(Exception): pass


def posterior(s, f):
    a, b = 1 + s, 1 + f; m = a / (a + b); sd = (a * b / ((a + b) ** 2 * (a + b + 1))) ** 0.5
    r = lambda x: round(x, 3)
    return {"successes": s, "failures": f, "n": s + f, "mean": r(m), "lo": r(max(0, m - 1.645 * sd)), "hi": r(min(1, m + 1.645 * sd))}


def matches(when, feats):
    if "conf_lt" in when: return (feats.get("agent_confidence") or 1.0) < when["conf_lt"]
    if "severity" in when: return feats.get("severity") == when["severity"]
    return False


def apply_policy(rules, case):
    """the candidate/champion sees ONLY blinded case fields"""
    extra = set(case) - CASE_KEYS
    if extra: raise LeakageError(f"case carries non-input fields: {sorted(extra)}")
    f = case.get("features") or {}
    for r in rules:
        if r["area"] == f.get("area") and matches(r["when"], f): return r["answer"]
    return case["agent_proposal"]


def score(champ_rules, cand_rules, cases, answers, area):
    rows = []
    for c in cases:
        if (c.get("features") or {}).get("area") != area: continue
        a, b = apply_policy(champ_rules, c), apply_policy(cand_rules, c)
        out = answers[c["case_id"]]["outcome"]; crit = c["features"].get("severity") == "critical"
        rows.append({"case_id": c["case_id"], "title": c["card"].split("title: ")[-1].split("\n")[0], "before": a, "after": b,
                     "outcome": out, "critical": crit})
    n = len(rows)
    ca = sum(r["before"] == r["outcome"] for r in rows); cb = sum(r["after"] == r["outcome"] for r in rows)
    w = sum(r["after"] == r["outcome"] != r["before"] for r in rows); l = sum(r["before"] == r["outcome"] != r["after"] for r in rows)
    d = (cb - ca) / n if n else 0.0
    var = ((w + l) / n - d * d) if n else 0.0
    se = (max(var, 0) / n) ** 0.5 if n else 0.0
    return {"n": n, "champion_correct": ca, "candidate_correct": cb, "accuracy_delta": round(d, 3),
            "delta_interval": [round(d - 1.645 * se, 3), round(d + 1.645 * se, 3)], "wins": w, "losses": l,
            "sign": posterior(w, l),
            "critical_misses": {"champion": sum(r["critical"] and r["before"] != r["outcome"] for r in rows),
                                "candidate": sum(r["critical"] and r["after"] != r["outcome"] for r in rows)},
            "escalations_removed": sum(r["before"] in MARGIN["escalate_answers"] and r["after"] not in MARGIN["escalate_answers"] for r in rows),
            "changed": [r for r in rows if r["before"] != r["after"]]}


def evaluate_rules(m, area):
    why = []
    if m["n"] < MARGIN["n_min"]: why.append(f"n {m['n']} < {MARGIN['n_min']}")
    if m["accuracy_delta"] < MARGIN["delta_min"]: why.append(f"Δaccuracy {m['accuracy_delta']} < margin {MARGIN['delta_min']}")
    if m["sign"]["lo"] <= MARGIN["sign_lo_min"]: why.append(f"wins/losses {m['wins']}/{m['losses']}: 90% low {m['sign']['lo']} ≤ {MARGIN['sign_lo_min']}")
    if m["critical_misses"]["candidate"] > m["critical_misses"]["champion"]:
        why.append(f"critical misses rise {m['critical_misses']['champion']}→{m['critical_misses']['candidate']}")
    if area in MARGIN["clinical_areas"] and m["escalations_removed"] > 0:
        why.append(f"clinical guard: would remove {m['escalations_removed']} escalation(s)")
    return ("passed" if not why else "failed"), why


def evaluator_sha():
    src = "".join(inspect.getsource(f) for f in (matches, apply_policy, score, evaluate_rules)) + json.dumps(MARGIN, sort_keys=True) + EVALUATOR_VERSION
    return hashlib.sha256(src.encode()).hexdigest()


def check_evaluator():
    lock = json.load(open(LOCK))
    if lock.get("version") != EVALUATOR_VERSION or lock.get("sha256") != evaluator_sha():
        raise EvaluatorTampered(f"evaluator {EVALUATOR_VERSION} hash {evaluator_sha()[:12]} ≠ lock {lock.get('sha256', '')[:12]}")
    return lock


def load_pack(rdir):
    m = json.load(open(os.path.join(rdir, "manifest.json")))
    for fn, k in (("cases.jsonl", "cases_sha256"), ("answers.jsonl", "answers_sha256")):
        h = hashlib.sha256(open(os.path.join(rdir, fn), "rb").read()).hexdigest()
        if h != m[k]: raise ReplayTampered(f"{fn} sha256 {h[:12]} ≠ manifest {m[k][:12]}")
    if not m.get("blinded"): raise LeakageError("replay pack is not marked blinded")
    cases = [json.loads(l) for l in open(os.path.join(rdir, "cases.jsonl"))]
    for c in cases:
        blob = json.dumps(c)
        bad = [k for k in FORBIDDEN if f'"{k}"' in blob]
        if bad: raise LeakageError(f"case {c.get('case_id')} exposes {bad}")
    answers = {a["case_id"]: a for a in (json.loads(l) for l in open(os.path.join(rdir, "answers.jsonl")))}
    return m, cases, answers


def critic(train, champion_rules, exclude_ids=()):
    """deterministic rule proposer: per area, the predicate whose held-in evidence most favours a different answer"""
    ex = set(exclude_ids); recs = [r for r in train if r.get("id") not in ex and r.get("outcome")]
    out = []
    for area in sorted({r["domain"].split(":", 1)[-1] for r in recs}):
        best = None
        for when in ({"conf_lt": 0.6}, {"conf_lt": 0.65}, {"conf_lt": 0.7}, {"severity": "critical"}):
            m = [r for r in recs if r["domain"].endswith(area) and matches(when, {"agent_confidence": r["agent_proposal"].get("confidence"),
                                                                                   "severity": (r.get("card_payload") or {}).get("severity", "normal")})]
            wrong = collections.Counter(r["outcome"]["value"] for r in m if r["outcome"]["value"] != r["agent_proposal"]["answer"])
            if not wrong: continue
            ans, c = sorted(wrong.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            gain = c - sum(r["outcome"]["value"] == r["agent_proposal"]["answer"] for r in m)
            if c >= 3 and gain > 0 and (best is None or gain > best["train_gain"]):
                best = {"area": area, "when": when, "answer": ans, "train_gain": gain, "n_matched": len(m), "evidence_refs": [r["id"] for r in m]}
        if best and not any(r["area"] == area and r["when"] == best["when"] and r["answer"] == best["answer"] for r in champion_rules):
            rule = {"area": area, "when": best["when"], "answer": best["answer"]}
            best["id"] = hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()[:12]
            best["rule"] = rule; best["critic"] = "deterministic-v1"
            out.append(best)
    return out


def critic_llm(*_a, **_k):
    """optional LLM critic hook — STUB. No external calls. Even when wired it may only propose; its output goes through evaluate()."""
    return []


def evaluate(rdir, champion_rules, cand):
    lock = check_evaluator()
    m, cases, answers = load_pack(rdir)
    held = {a["source_id"] for a in answers.values()}
    overlap = held & set(cand.get("evidence_refs", []))
    if overlap: raise LeakageError(f"candidate evidence overlaps held-out replay: {sorted(overlap)[:3]}")
    met = score(champion_rules, champion_rules + [cand["rule"]], cases, answers, cand["area"])
    verdict, why = evaluate_rules(met, cand["area"])
    return {"candidate": cand["id"], "area": cand["area"], "rule": cand["rule"], "verdict": verdict, "reasons": why, "metrics": met,
            "replay": {"name": m["name"], "cases_sha256": m["cases_sha256"], "answers_sha256": m["answers_sha256"]},
            "evaluator": {"version": lock["version"], "sha256": lock["sha256"]}}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--train", required=True); ap.add_argument("--replay", required=True)
    ap.add_argument("-o"); ap.add_argument("--write-lock", action="store_true", help="re-pin the evaluator (new version only)")
    a = ap.parse_args(argv)
    if a.write_lock:
        json.dump({"version": EVALUATOR_VERSION, "sha256": evaluator_sha()}, open(LOCK, "w"), indent=2); print("locked", evaluator_sha()); return 0
    train = [json.loads(l) for l in open(a.train)]
    _, _, answers = load_pack(a.replay)
    held = {x["source_id"] for x in answers.values()}
    res = [evaluate(a.replay, [], c) for c in critic(train, [], exclude_ids=held) + critic_llm()]
    rep = {"evaluations": res, "note": "eligible ≠ promoted: only a signed Principal approval in the app promotes"}
    s = json.dumps(rep, indent=2, ensure_ascii=False)
    if a.o: open(a.o, "w").write(s)
    print(json.dumps([{k: r[k] for k in ("area", "rule", "verdict", "reasons")} | {"Δ": r["metrics"]["accuracy_delta"], "n": r["metrics"]["n"]} for r in res], indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
