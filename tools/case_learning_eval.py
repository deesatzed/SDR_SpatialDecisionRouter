#!/usr/bin/env python3
"""Honest BASELINE for case-based learning on an import_cases.py --split experiment. NOT a model, nothing is trained.

  no_history   : predict the agent's own proposal; confidence = agent_confidence.
  with_history : nearest-prior-case. Score every train case in the same domain:
                   sim = 0.5*(same subject) + 0.3*(same complaint/topic) + 0.2*jaccard(presentation tokens)
                 If best sim >= --threshold, predict that case's observed outcome (or the human answer when no outcome
                 is recorded); confidence = 0.5 + 0.5*sim. Otherwise fall back to the agent proposal.
Metrics on held-out answers: accuracy, Brier score (lower is better), and critical-severity misses; also per subset
(repeat subject, hard trigger, ambiguous). With ~14 synthetic test cases these numbers are illustrative, not evidence.

Usage: python3 tools/case_learning_eval.py <experiment_dir> [--threshold 0.5] [--json out.json]
"""
import argparse, json, os, re, sys


def load(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def toks(s):
    return set(re.findall(r"[a-z]+", (s or "").lower())) - {"a", "the", "and", "of", "to", "in", "on", "with", "no", "for", "an"}


def sim(a, b):
    ta, tb = toks(a.get("presentation")), toks(b.get("presentation"))
    j = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    key = lambda c: c.get("chief_complaint") or c.get("topic")  # noqa: E731
    return 0.5 * (a["subject_key"] == b["subject_key"]) + 0.3 * (key(a) == key(b)) + 0.2 * j


def predict(case, pool, threshold):
    best, bs = None, -1.0
    for h in pool:
        c = h["case"]
        if c["domain"] != case["domain"] or c["day_offset"] >= case["day_offset"] and c["subject_key"] == case["subject_key"]:
            continue
        label = (h.get("outcome") or {}).get("outcome_value") or next((r["human_answer"] for r in h["human_responses"]), None)
        if label is None:
            continue
        s = sim(case, c)
        if s > bs:
            best, bs = (c["case_id"], label), s
    if best and bs >= threshold:
        return best[1], min(0.5 + 0.5 * bs, 0.99), best[0], round(bs, 3)
    return case["agent_proposal"]["answer"], case["agent_proposal"]["confidence"], None, round(max(bs, 0), 3)


def score(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    acc = sum(r["correct"] for r in rows) / n
    brier = sum((r["conf"] - r["correct"]) ** 2 for r in rows) / n
    return {"n": n, "accuracy": round(acc, 3), "brier": round(brier, 3),
            "critical_misses": sum(1 for r in rows if not r["correct"] and r["severity"] == "critical")}


def evaluate(exp, threshold=0.5):
    pool = load(os.path.join(exp, "train", "history.jsonl"))
    ans = {a["case_id"]: a for a in load(os.path.join(exp, "test", "answers.jsonl"))}
    per = []
    for row in load(os.path.join(exp, "conditions", "with_history.jsonl")):
        c = row["case"]; a = ans[c["case_id"]]
        if a["outcome_value"] is None:
            continue
        ph, pc, via, s = predict(c, pool, threshold)
        nh = c["agent_proposal"]["answer"]
        per.append({"case_id": c["case_id"], "domain": c["domain"], "truth": a["outcome_value"], "severity": a["severity_if_wrong"],
                    "repeat_subject": bool(row["subject_history"]), "hard_trigger": bool(c.get("hard_trigger")), "ambiguous": c["ambiguity"] == "ambiguous",
                    "no_history": {"pred": nh, "conf": c["agent_proposal"]["confidence"], "correct": nh == a["outcome_value"]},
                    "with_history": {"pred": ph, "conf": pc, "correct": ph == a["outcome_value"], "via_case": via, "sim": s}})
    rep = {"kind": "BASELINE (nearest prior case) — not a model; synthetic data; small n", "threshold": threshold, "overall": {}, "subsets": {}, "cases": per}
    for cond in ("no_history", "with_history"):
        sel = lambda f: [dict(p[cond], severity=p["severity"]) for p in per if f(p)]  # noqa: E731
        rep["overall"][cond] = score(sel(lambda p: True))
        for name in ("repeat_subject", "hard_trigger", "ambiguous"):
            rep["subsets"].setdefault(name, {})[cond] = score(sel(lambda p, n=name: p[n]))
        for d in sorted({p["domain"] for p in per}):
            rep["subsets"].setdefault("domain:" + d, {})[cond] = score(sel(lambda p, d=d: p["domain"] == d))
    o = rep["overall"]
    rep["difference"] = {"accuracy": round(o["with_history"]["accuracy"] - o["no_history"]["accuracy"], 3),
                         "brier": round(o["with_history"]["brier"] - o["no_history"]["brier"], 3)} if per else {}
    rep["history_hurt"] = [p["case_id"] for p in per if p["no_history"]["correct"] and not p["with_history"]["correct"]]
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment"); ap.add_argument("--threshold", type=float, default=0.5); ap.add_argument("--json")
    a = ap.parse_args(argv)
    r = evaluate(a.experiment, a.threshold)
    if a.json:
        json.dump(r, open(a.json, "w"), indent=2)
    print(r["kind"])
    print(f"{'slice':28} {'cond':13} {'n':>3} {'acc':>6} {'brier':>6} {'crit_miss':>9}")
    for name, d in [("overall", r["overall"])] + list(r["subsets"].items()):
        for cond, s in d.items():
            if s.get("n"):
                print(f"{name:28} {cond:13} {s['n']:>3} {s['accuracy']:>6} {s['brier']:>6} {s['critical_misses']:>9}")
    print("difference (with - no):", r["difference"], "| history hurt on:", r["history_hurt"] or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
