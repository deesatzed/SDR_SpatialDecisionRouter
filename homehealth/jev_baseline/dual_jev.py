"""Dual-model Jev stage behind mandatory Layer 1 (SYNTHETIC). Wayne 2026-10-20.

Layer 1 decides first (layer1_adapter.route): ABSOLUTE / CONFIRM_FIRST -> escalate, SUPPRESSED goals_of_care -> nurse_task.
On cases Jev decides (owner jev / jev_capped), both models' picks are routed through Layer 1 and combined:
  agree_else_hitm : agree -> that route; disagree -> HITM review (provisional route = lead model, d1-ultra)
  cautious_max    : disagree -> the higher (more cautious) route
  cautious_max_hitm (DEFAULT): disagree -> the higher route AND a HITM flag
Optional Fly flag-only on top adds HITM flags and never changes a route. Without Layer 1 (fallback), the same rule is applied
to the raw model picks, led by d1-ultra (if one model has no pick, the other's is used).
"""
from __future__ import annotations
import csv, json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import score_jev as S, layer1_adapter as L  # noqa: E402

DUAL_MODELS = ["liquid/d1-ultra", "perplexity/pplx-decider-v1.2"]   # lead model first
DEFAULT_RULE = "cautious_max_hitm"
RULES = ("lead_only", "agree_else_hitm", "cautious_max", "cautious_max_hitm")
RK = S.RANK
FLY_DEFAULT = {"leak": "0.5", "threshold": 0.841072}   # flag_only threshold tuned on the train split (fly_layer/results/summary.json)

def combine(rule, lead, other):
    """lead/other: routes (or None). Returns (route, hitm_flag)."""
    if lead is None and other is None: return None, True
    if lead is None or other is None: return (lead or other), True
    if lead == other or rule == "lead_only": return lead, False
    hi = lead if RK[lead] >= RK[other] else other
    if rule == "agree_else_hitm": return lead, True
    if rule == "cautious_max": return hi, False
    if rule == "cautious_max_hitm": return hi, True
    raise ValueError(rule)

def dual_route(l1, pick_lead, pick_other, rule=DEFAULT_RULE):
    """Layer 1 first; on Jev-owned cases combine both models. Returns (route, owner, hitm_flag)."""
    r1, owner = L.route(l1, pick_lead); r2, _ = L.route(l1, pick_other)
    if owner not in ("jev", "jev_capped"): return r1, owner, False
    r, f = combine(rule, r1, r2)
    return r, owner, f

def load_picks(path):
    last = {}
    for l in open(path):
        if l.strip(): r = json.loads(l); last[(r["case"], r["variant"])] = r
    return {k[0]: v.get("pick") for k, v in last.items() if k[1] == "base"}

def _pick_path(env, *cands):
    for p in (os.environ.get(env),) + cands:
        if p and os.path.exists(p): return p
    raise SystemExit(f"stored picks not found: set {env}")

def main(out_dir=os.path.join(HERE, "results_dual")):
    sys.path.insert(0, os.path.join(HERE, "..", "fly_layer")); import score_fly as SF
    cases = json.load(open(S.find_input("RUNNER_JSON", "library_v2_smart_runner.json")))
    A = {c["case_id"]: c for c in json.load(open(S.find_input("ACCEPTED_JSON", "library_v2_smart_accepted.json")))["cases"]}
    sev = {r["case_id"]: r["severity_if_wrong"] for r in csv.DictReader(open(S.find_input("OUTCOMES_CSV", "library_v2_smart_Outcomes.csv")))}
    extra = {c["id"]: {"categories": [c["kind"]], "subtle": False} for c in cases}
    pd = load_picks(_pick_path("JEV_PICKS_D1", os.path.join(HERE, "results_v18", "parsed", "liquid_d1-ultra.jsonl")))
    pp = load_picks(_pick_path("JEV_PICKS_PPLX", os.path.join(HERE, "results_pplx", "parsed", "perplexity_pplx-decider-v1.2.jsonl")))
    R = json.load(open(os.environ.get("FLY_READOUTS", os.path.join(HERE, "..", "fly_layer", "results", "fly_readouts.json"))))["cases"]
    l1 = {c["id"]: L.evaluate_case(A[c["id"][4:]]) for c in cases}
    supp = {c["id"] for c in cases if c.get("trigger_tier") == "SUPPRESSED"}
    hosp = {c["id"] for c in cases if c.get("escalation_target") == "hospice_nurse" or c.get("suppression_reason") == "goals_of_care"}
    batch = {c["id"]: A[c["id"][4:]].get("src_batch") or c["id"][4:].split("-")[0] for c in cases}
    held_b = SF.split_batches(batch); parts = {"all": cases, "heldout": [c for c in cases if batch[c["id"]] in held_b]}
    fly_hi = {c["id"]: max(R[c["id"][4:]]["readouts"][FLY_DEFAULT["leak"]]) > FLY_DEFAULT["threshold"] for c in cases}
    systems = {}
    def add(name, res):   # res: id -> (route, owner, flag)
        picks = {k: v[0] for k, v in res.items()}; flags = {k for k, v in res.items() if v[2]}; out = {}
        for p, cs in parts.items():
            m = SF.metrics(cs, picks, sev, extra, supp, hosp); ids = {c["id"] for c in cs}; f = flags & ids
            err = {c["id"] for c in cs if not S.correct(picks[c["id"]], c)}
            out[p] = {k: m[k] for k in ("n_cases", "accuracy", "critical_misses", "critical_miss_ids", "pages_per_100", "false_pages_per_100", "over_escalation_ids", "pairs_both_correct", "pairs_complete")}
            out[p].update(suppressed=f'{m["suppressed_cases"]["correct"]}/{m["suppressed_cases"]["n"]}', hospice=f'{m["hospice_cases"]["correct"]}/{m["hospice_cases"]["n"]}',
                          hitm=len(f), hitm_per_100=S.rate(100 * len(f), len(cs)), errors=len(err), errors_in_hitm=len(err & f), errors_not_in_hitm=sorted(err - f))
        systems[name] = {"metrics": out, "res": res}
    for rule in RULES:
        res = {c["id"]: dual_route(l1[c["id"]], pd.get(c["id"]), pp.get(c["id"]), rule) for c in cases}
        add(f"L1+{rule}", res)
        add(f"L1+{rule}+fly", {k: (r, o, f or SF.combine("flag_only", r, o, fly_hi[k])[1]) for k, (r, o, f) in res.items()})
    for rule in RULES:   # fallback: no Layer 1
        add(f"noL1+{rule}", {c["id"]: (*combine(rule, pd.get(c["id"]), pp.get(c["id"]))[:1], "jev", combine(rule, pd.get(c["id"]), pp.get(c["id"]))[1]) for c in cases})
    add("L1+pplx_only", {c["id"]: (*L.route(l1[c["id"]], pp.get(c["id"])), False) for c in cases})
    # what the HITM resolves under the default rule
    dis = [c for c in cases if systems[f"L1+{DEFAULT_RULE}"]["res"][c["id"]][2]]
    def kind(c):
        r1 = L.route(l1[c["id"]], pd.get(c["id"]))[0]; r2 = L.route(l1[c["id"]], pp.get(c["id"]))[0]; return f"{min(r1, r2, key=RK.get)} vs {max(r1, r2, key=RK.get)}"
    hitm = {"n": len(dis), "pairs_of_routes": dict(collections.Counter(kind(c) for c in dis).most_common()),
            "lead_correct": sum(S.correct(L.route(l1[c["id"]], pd.get(c["id"]))[0], c) for c in dis),
            "other_correct": sum(S.correct(L.route(l1[c["id"]], pp.get(c["id"]))[0], c) for c in dis),
            "cautious_correct": sum(S.correct(systems[f"L1+{DEFAULT_RULE}"]["res"][c["id"]][0], c) for c in dis),
            "lower_correct": sum(S.correct(min(L.route(l1[c["id"]], pd.get(c["id"]))[0], L.route(l1[c["id"]], pp.get(c["id"]))[0], key=RK.get), c) for c in dis),
            "case_ids": [c["id"] for c in dis]}
    out = {"label_pages_per_100": S.rate(100 * sum(S.norm(c["expected"]) == S.ESC for c in cases), len(cases)), "models": DUAL_MODELS,
           "default_rule": DEFAULT_RULE, "fly": FLY_DEFAULT, "heldout_batches": sorted(held_b), "new_paid_calls": 0,
           "systems": {k: v["metrics"] for k, v in systems.items()}, "hitm_queue_default": hitm}
    os.makedirs(out_dir, exist_ok=True); json.dump(out, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    with open(os.path.join(out_dir, "per_case.csv"), "w", newline="") as fh:
        w = csv.writer(fh); names = list(systems)
        w.writerow(["case_id", "expected", "acceptable", "l1_tier", "pick_d1", "pick_pplx"] + [f"{n}_route" for n in names] + [f"{n}_hitm" for n in names])
        for c in cases:
            i = c["id"]; w.writerow([i, c["expected"], ";".join(c.get("acceptable") or []), l1[i].get("tier") or "", pd.get(i), pp.get(i)]
                                    + [systems[n]["res"][i][0] for n in names] + [int(systems[n]["res"][i][2]) for n in names])
    return out

if __name__ == "__main__":
    o = main()
    for n, s in o["systems"].items():
        for p in ("all", "heldout"):
            m = s[p]; print(f'{n:28s} {p:7s} acc={m["accuracy"]} crit={m["critical_misses"]} {m["critical_miss_ids"]} pages={m["pages_per_100"]} fp={m["false_pages_per_100"]} supp={m["suppressed"]} hosp={m["hospice"]} pairs={m["pairs_both_correct"]} hitm={m["hitm"]} ({m["hitm_per_100"]}) err={m["errors"]} in_hitm={m["errors_in_hitm"]}')
    print(json.dumps({k: v for k, v in o["hitm_queue_default"].items() if k != "case_ids"}))
