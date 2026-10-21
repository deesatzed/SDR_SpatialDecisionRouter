"""Score on the ruled answer key (holdout_v1_ruled_key.json) from STORED picks only (SYNTHETIC; no API calls).
Picks: the 60 accepted cases from jev/parsed (v1.8 prompt, 2026-10-20); the 31 kept review-queue cases from jev_ruled/parsed
(v1.9 prompt, run 2026-10-21 with Wayne's approval, $0.0067). Every system is scored on all 91 and on both subsets."""
import json, os, sys, collections
HO = os.path.dirname(os.path.abspath(__file__)); JB = os.path.join(HO, "..", "jev_baseline"); sys.path[:0] = [JB, os.path.join(HO, "..", "fly_layer")]
import score_jev as S, layer1_adapter as L, dual_jev as D, score_l1jev as SL  # noqa: E402
K = json.load(open(os.path.join(HO, "holdout_v1_ruled_key.json")))["cases"]
PK = next(p for p in (os.environ.get("HOLDOUT_PICKS_DIR"), os.path.join(HO, "jev", "parsed"), os.path.expanduser("~/Projects/jevfly_smoke/holdout_v1/jev/parsed"), "/workspace/jevfly_smoke/holdout_v1/jev/parsed") if p and os.path.isdir(p))
P = {m: D.load_picks(os.path.join(PK, SL.S_slug(m) + ".jsonl")) for m in D.DUAL_MODELS}
for m in D.DUAL_MODELS: P[m].update(D.load_picks(os.path.join(os.environ.get("RULED_PICKS_DIR", os.path.join(HO, "jev_ruled", "parsed")), SL.S_slug(m) + ".jsonl")))
pd, pp = P["liquid/d1-ultra"], P["perplexity/pplx-decider-v1.2"]
def lab(c): return {"id": "LIB-" + c["case_id"], "expected": c["expected_route"], "acceptable": c.get("acceptable_alternates") or [], "trigger_tier": c.get("trigger_tier")}
cases = {c["case_id"]: c for c in K}; l1 = {i: L.evaluate_case(c) for i, c in cases.items()}
def stack(i, name):
    l, a, b = l1[i], pd.get("LIB-" + i), pp.get("LIB-" + i)
    if name == "L1 + dual (c) [default]": return D.dual_route(l, a, b, "cautious_max_hitm")
    if name == "L1 + d1-ultra": return (*L.route(l, a), False)
    if name == "L1 + pplx": return (*L.route(l, b), False)
    if name == "Layer 1 alone": r, o = L.route(l, None); return (r, o, r is None)   # no trigger -> no decision (would go to Jev)
def m(ids, name):
    res = {i: stack(i, name) for i in ids}; n = len(ids)
    dec = [i for i in ids if res[i][0] is not None]
    ok = [i for i in dec if S.correct(res[i][0], lab(cases[i]))]
    crit = [i for i in dec if S.critical_miss(res[i][0], lab(cases[i]))]
    fp = [i for i in dec if S.over_escalation(res[i][0], lab(cases[i]))]
    hitm = [i for i in ids if res[i][2]]
    errs = [{"case": i, "picked": res[i][0], "ruling": cases[i]["expected_route"], "key_source": cases[i]["key_source"], "owner": res[i][1],
             "l1_tier": l1[i].get("tier"), "label_tier": cases[i].get("trigger_tier"), "d1": pd.get("LIB-" + i), "pplx": pp.get("LIB-" + i),
             "critical": i in crit, "false_page": i in fp, "caught_by_hitm": res[i][2]} for i in dec if i not in ok]
    return {"n": n, "decided": len(dec), "accuracy": S.rate(len(ok), len(dec)), "accuracy_over_all": S.rate(len(ok), n), "critical_misses": len(crit), "critical_ids": crit,
            "false_pages_per_100": S.rate(100 * len(fp), n), "hitm_per_100": S.rate(100 * len(hitm), n), "errors": errs}
def tier_agree(ids):
    t = [i for i in ids if cases[i].get("trigger_tier")]
    match = [i for i in t if l1[i].get("tier") == cases[i]["trigger_tier"]]
    return {"trigger_cases": len(t), "tier_match": len(match), "rate": S.rate(len(match), len(t)),
            "mismatch": [(i, cases[i]["trigger_tier"], l1[i].get("tier")) for i in t if i not in match]}
acc60 = [c["case_id"] for c in K if c["key_source"] in ("author_label_accepted", "clinician_ruling_accepted_2026-10-21")]; ruled = [i for i in cases if i not in acc60]
SYS = ["L1 + dual (c) [default]", "L1 + d1-ultra", "L1 + pplx", "Layer 1 alone"]
out = {"n_key": len(K), "n_accepted_60": len(acc60), "n_ruled_queue": len(ruled), "paid_calls_this_run": 248, "spend_usd": 0.0067,
       "systems": {part: {s: m(ids, s) for s in SYS} for part, ids in (("all91", list(cases)), ("accepted60", acc60), ("ruled31", ruled))},
       "tier_agreement": {"accepted60": tier_agree(acc60), "ruled31": tier_agree(ruled), "all91": tier_agree(list(cases))},
       "HO7-017": {"d1": pd.get("LIB-HO7-017"), "pplx": pp.get("LIB-HO7-017"), "l1_tier": l1["HO7-017"].get("tier"), "default": stack("HO7-017", SYS[0])[:3]},
       "old_scores_9f5ca71_accepted60": json.load(open(os.path.join(HO, "results", "summary.json")))["systems"]}
os.makedirs(os.path.join(HO, "results_ruled"), exist_ok=True); json.dump(out, open(os.path.join(HO, "results_ruled", "summary.json"), "w"), indent=1)
if __name__ == "__main__":
    for part, v0 in out["systems"].items():
        for s, v in v0.items(): print(f'{part:10s} {s:26s} acc={v["accuracy"]} ({v["decided"]}/{v["n"]} decided) crit={v["critical_misses"]} {v["critical_ids"]} fp/100={v["false_pages_per_100"]} hitm/100={v["hitm_per_100"]} errors={len(v["errors"])}')
    print({k: (v["tier_match"], v["trigger_cases"], v["rate"]) for k, v in out["tier_agreement"].items()})
    print("HO7-017:", out["HO7-017"])
    for s in SYS:
        print("ERRORS", s, "(91):"); [print(" ", e["case"], e["picked"], "vs", e["ruling"], "d1", e["d1"], "pplx", e["pplx"], "l1", e["l1_tier"], "crit" if e["critical"] else "", "FP" if e["false_page"] else "", "HITM" if e["caught_by_hitm"] else "noHITM") for e in out["systems"]["all91"][s]["errors"]]
