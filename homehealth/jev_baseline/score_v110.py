"""Layer 1 v1.10 before/after scorer (SYNTHETIC). Stored picks only, no API calls.
Sets: library 270 (library_v2_smart_accepted.json, author labels) and the ruled holdout key (holdout_v1_ruled_key.json, 91).
Systems: L1 + dual (cautious_max_hitm, default), L1 + d1-ultra, L1 + pplx, Layer 1 alone. Usage: python3 score_v110.py [out.json]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import score_jev as S, layer1_adapter as L, dual_jev as D, score_l1jev as SL  # noqa: E402
HH = os.path.join(HERE, "..")
def _first(*ps):
    for p in ps:
        if p and os.path.exists(p): return p
    raise SystemExit(f"not found: {ps}")
def picks(*paths):
    out = {}
    for p in paths:
        if p and os.path.exists(p): out.update(D.load_picks(p))
    return out
def sets():
    lib = json.load(open(_first(os.path.join(HH, "library", "library_v2_smart_accepted.json"))))["cases"]
    ho = json.load(open(_first(os.path.join(HH, "holdout", "holdout_v1_ruled_key.json"))))["cases"]
    J = os.environ.get("JB_DIR", HERE); HP = [os.environ.get("HOLDOUT_PICKS_DIR"), os.path.join(HH, "holdout", "jev", "parsed"), os.path.expanduser("~/Projects/jevfly_smoke/holdout_v1/jev/parsed"), "/workspace/jevfly_smoke/holdout_v1/jev/parsed"]
    hp = next(p for p in HP if p and os.path.isdir(p)); rp = os.path.join(HH, "holdout", "jev_ruled", "parsed")
    lib_p = {m: picks(*[os.path.join(d, SL.S_slug(m) + ".jsonl") for d in (os.path.join(J, "results_v18", "parsed"), os.path.join(J, "results_pplx", "parsed"),
             os.path.expanduser("~/Projects/jevfly_smoke/jev_baseline/results_v18/parsed"), os.path.expanduser("~/Projects/jevfly_smoke/jev_baseline/results_pplx/parsed"),
             "/workspace/jev_baseline/results_v18/parsed", "/workspace/jev_baseline/results_pplx/parsed")]) for m in D.DUAL_MODELS}
    ho_p = {m: picks(os.path.join(hp, SL.S_slug(m) + ".jsonl"), os.path.join(rp, SL.S_slug(m) + ".jsonl")) for m in D.DUAL_MODELS}
    return {"library270": (lib, lib_p), "holdout_ruled91": (ho, ho_p)}
SYS = ["L1 + dual (c) [default]", "L1 + d1-ultra", "L1 + pplx", "Layer 1 alone"]
def run(cases, P):
    pd, pp = P["liquid/d1-ultra"], P["perplexity/pplx-decider-v1.2"]; res = {}; l1 = {c["case_id"]: L.evaluate_case(c) for c in cases}
    lab = lambda c: {"expected": c["expected_route"], "acceptable": c.get("acceptable_alternates") or [], "trigger_tier": c.get("trigger_tier")}
    for s in SYS:
        rr = {}
        for c in cases:
            i = c["case_id"]; l, a, b = l1[i], pd.get("LIB-" + i), pp.get("LIB-" + i)
            if s == SYS[0]: rr[i] = D.dual_route(l, a, b, "cautious_max_hitm")
            elif s == SYS[1]: rr[i] = (*L.route(l, a), bool(l.get("hitm_required")))
            elif s == SYS[2]: rr[i] = (*L.route(l, b), bool(l.get("hitm_required")))
            else: r, o = L.route(l, None); rr[i] = (r, o, r is None or bool(l.get("hitm_required")))
        dec = [c for c in cases if rr[c["case_id"]][0] is not None]; n = len(cases)
        ok = [c for c in dec if S.correct(rr[c["case_id"]][0], lab(c))]; crit = [c["case_id"] for c in dec if S.critical_miss(rr[c["case_id"]][0], lab(c))]
        fp = [c["case_id"] for c in dec if S.over_escalation(rr[c["case_id"]][0], lab(c))]; hitm = [i for i in rr if rr[i][2]]
        errs = [{"case": c["case_id"], "picked": rr[c["case_id"]][0], "label": c["expected_route"], "l1": l1[c["case_id"]].get("tier"), "l1_reason": l1[c["case_id"]].get("reason"), "hitm": rr[c["case_id"]][2]} for c in dec if c not in ok]
        res[s] = {"n": n, "decided": len(dec), "accuracy": S.rate(len(ok), len(dec)), "critical_misses": len(crit), "critical_ids": crit,
                  "false_pages_per_100": S.rate(100 * len(fp), n), "false_page_ids": fp, "hitm_per_100": S.rate(100 * len(hitm), n), "errors": errs}
    t = [c for c in cases if c.get("trigger_tier")]; tm = [c for c in t if l1[c["case_id"]].get("tier") == c["trigger_tier"]]
    fpt = [c["case_id"] for c in cases if not c.get("trigger_tier") and l1[c["case_id"]].get("tier") in ("ABSOLUTE", "CONFIRM_FIRST")]
    res["tier_agreement"] = {"trigger_cases": len(t), "match": len(tm), "rate": S.rate(len(tm), len(t)), "false_paging_triggers_on_no_trigger_cases": fpt,
                             "mismatch": [(c["case_id"], c["trigger_tier"], l1[c["case_id"]].get("tier"), l1[c["case_id"]].get("reason")) for c in t if c not in tm]}
    res["l1"] = {i: {k: v.get(k) for k in ("tier", "rule", "reason", "hitm_required", "default_route")} for i, v in l1.items()}
    return res
if __name__ == "__main__":
    out = {k: run(*v) for k, v in sets().items()}
    if len(sys.argv) > 1: json.dump(out, open(sys.argv[1], "w"), indent=1)
    for k, r in out.items():
        for s in SYS: m = r[s]; print(f'{k:16s} {s:26s} acc={m["accuracy"]} ({m["decided"]}/{m["n"]}) crit={m["critical_misses"]} {m["critical_ids"]} fp/100={m["false_pages_per_100"]} hitm/100={m["hitm_per_100"]}')
        t = r["tier_agreement"]; print(f'{k:16s} tier agreement {t["match"]}/{t["trigger_cases"]} = {t["rate"]}; false paging triggers on no-trigger cases: {len(t["false_paging_triggers_on_no_trigger_cases"])}')
    print("HO2-007 L1:", out["holdout_ruled91"]["l1"].get("HO2-007"))
