"""Score the frozen stack (main @ FROZEN) on holdout_v1 (SYNTHETIC). No tuning: Layer 1, prompts, Fly threshold and dual rule as committed."""
import csv, json, os, sys, collections
JB = os.environ.get("JEV_BASELINE_DIR", "/workspace/jev_baseline"); FL = os.environ.get("FLY_DIR", "/workspace/fly_layer")
HO = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("RUNNER_JSON", f"{HO}/holdout_v1_runner.json"); os.environ.setdefault("ACCEPTED_JSON", f"{HO}/holdout_v1_accepted.json"); os.environ.setdefault("OUTCOMES_CSV", f"{HO}/holdout_v1_Outcomes.csv")
sys.path[:0] = [JB, FL]
import score_jev as S, layer1_adapter as L, score_l1jev as SL, dual_jev as D, score_fly as SF
FROZEN = os.environ.get("FROZEN_COMMIT", "81820c9")
cases = json.load(open(os.environ["RUNNER_JSON"])); A = {c["case_id"]: c for c in json.load(open(os.environ["ACCEPTED_JSON"]))["cases"]}
sev = {r["case_id"]: r["severity_if_wrong"] for r in csv.DictReader(open(os.environ["OUTCOMES_CSV"]))}
extra = {c["id"]: {"categories": A[c["id"][4:]].get("category") or [c["kind"]], "subtle": bool(A[c["id"][4:]].get("subtle_deterioration"))} for c in cases}
P = {m: D.load_picks(f"{HO}/jev/parsed/{SL.S_slug(m)}.jsonl") for m in D.DUAL_MODELS}
pd, pp = P["liquid/d1-ultra"], P["perplexity/pplx-decider-v1.2"]
R = json.load(open(f"{HO}/fly_readouts.json"))["cases"]
l1 = {c["id"]: L.evaluate_case(A[c["id"][4:]]) for c in cases}
supp = {c["id"] for c in cases if c.get("trigger_tier") == "SUPPRESSED"}
hosp = {c["id"] for c in cases if c.get("escalation_target") == "hospice_nurse" or c.get("suppression_reason") == "goals_of_care"}
fly_hi = {c["id"]: max(R[c["id"][4:]]["readouts"][D.FLY_DEFAULT["leak"]]) > D.FLY_DEFAULT["threshold"] for c in cases}
def m_of(res):
    picks = {k: v[0] for k, v in res.items()}; flags = {k for k, v in res.items() if v[2]}
    m = SF.metrics(cases, picks, sev, extra, supp, hosp); err = {c["id"] for c in cases if not S.correct(picks.get(c["id"]), c)}
    keep = {k: m[k] for k in ("n_cases", "n_with_pick", "accuracy", "critical_misses", "critical_miss_ids", "critical_miss_weighted", "pages_per_100", "false_pages_per_100", "over_escalation_ids", "pairs_both_correct", "pairs_complete", "escalation_sensitivity")}
    keep.update(suppressed=f'{m["suppressed_cases"]["correct"]}/{m["suppressed_cases"]["n"]}', hospice=f'{m["hospice_cases"]["correct"]}/{m["hospice_cases"]["n"]}', hospice_wrong=m["hospice_cases"]["wrong_ids"],
                hitm=len(flags), hitm_per_100=S.rate(100 * len(flags), len(cases)), errors=len(err), errors_in_hitm=len(err & flags), errors_not_in_hitm=sorted(err - flags))
    return keep, picks
sysres = {
 "d1-ultra alone": {c["id"]: (pd.get(c["id"]), "jev", False) for c in cases},
 "pplx alone": {c["id"]: (pp.get(c["id"]), "jev", False) for c in cases},
 "L1 + d1-ultra": {c["id"]: (*L.route(l1[c["id"]], pd.get(c["id"])), False) for c in cases},
 "L1 + pplx": {c["id"]: (*L.route(l1[c["id"]], pp.get(c["id"])), False) for c in cases},
 "L1 + dual (c) [default]": {c["id"]: D.dual_route(l1[c["id"]], pd.get(c["id"]), pp.get(c["id"]), "cautious_max_hitm") for c in cases},
}
sysres["L1 + dual (c) + Fly flag"] = {k: (r, o, f or SF.combine("flag_only", r, o, fly_hi[k])[1]) for k, (r, o, f) in sysres["L1 + dual (c) [default]"].items()}
sysres["no-L1 fallback: dual (c)"] = {c["id"]: (*D.combine("cautious_max_hitm", pd.get(c["id"]), pp.get(c["id"]))[:1], "jev", D.combine("cautious_max_hitm", pd.get(c["id"]), pp.get(c["id"]))[1]) for c in cases}
out = {"frozen_commit": FROZEN, "n_cases": len(cases), "label_pages_per_100": S.rate(100 * sum(S.norm(c["expected"]) == S.ESC for c in cases), len(cases)),
       "routes": dict(collections.Counter(c["expected"] for c in cases)), "tiers": dict(collections.Counter(c.get("trigger_tier") for c in cases if c.get("trigger_tier"))),
       "fly": D.FLY_DEFAULT, "systems": {}, "layer1_agreement": SL.agreement(cases, A, l1)}
per = {}
for n, res in sysres.items(): out["systems"][n], per[n] = m_of(res)
# critical-miss reasons
def why(i):
    c = next(x for x in cases if x["id"] == i); a = A[i[4:]]
    return {"expected": c["expected"], "label_tier": c.get("trigger_tier"), "label_rule": c.get("hard_trigger_rule"), "l1_tier": l1[i].get("tier"), "l1_rule": l1[i].get("rule"), "l1_reason": l1[i].get("reason"),
            "d1": pd.get(i), "pplx": pp.get(i), "decisive_feature": a.get("decisive_feature")}
out["critical_miss_detail"] = {i: why(i) for s in out["systems"].values() for i in s["critical_miss_ids"]}
# Jev robustness / calibration / cost
for m in D.DUAL_MODELS:
    rows = [S.RT.canon_row(json.loads(l)) for l in open(f"{HO}/jev/parsed/{SL.S_slug(m)}.jsonl") if l.strip()]
    last = {}; [last.__setitem__((r["case"], r["variant"]), r) for r in rows]; rows = list(last.values())
    out.setdefault("jev_runs", {})[m] = {"calls": len(rows), "without_pick": sum(1 for r in rows if not r.get("pick")), "retried": sum(1 for r in rows if (r.get("attempts") or 1) > 1),
        "errors": dict(collections.Counter(r.get("error") for r in rows if not r.get("pick"))), "cost_usd": round(sum(r.get("cost") or 0 for r in rows), 6),
        "robustness": S.robustness(cases, rows), "calibration": S.calibration(cases, {r["case"]: r for r in rows if r["variant"] == "base"})}
json.dump(out, open(f"{HO}/results/summary.json", "w"), indent=1)
with open(f"{HO}/results/per_case.csv", "w", newline="") as fh:
    w = csv.writer(fh); names = list(sysres)
    w.writerow(["case_id", "expected", "acceptable", "severity_if_wrong", "label_tier", "label_reason", "label_rule", "l1_tier", "l1_reason", "l1_rule", "pick_d1", "pick_pplx", "fly_high"] + [f"{n} route" for n in names] + [f"{n} hitm" for n in names])
    for c in cases:
        i = c["id"]; w.writerow([i, c["expected"], ";".join(c.get("acceptable") or []), sev.get(i), c.get("trigger_tier") or "", c.get("suppression_reason") or "", c.get("hard_trigger_rule") or "",
                                 l1[i].get("tier") or "", l1[i].get("reason") or "", l1[i].get("rule") or "", pd.get(i), pp.get(i), int(fly_hi[i])] + [per[n].get(i) for n in names] + [int(sysres[n][i][2]) for n in names])
for n, s in out["systems"].items(): print(f'{n:28s} acc={s["accuracy"]} crit={s["critical_misses"]} {s["critical_miss_ids"]} pages={s["pages_per_100"]} fp={s["false_pages_per_100"]} supp={s["suppressed"]} hosp={s["hospice"]} pairs={s["pairs_both_correct"]}/{s["pairs_complete"]} hitm={s["hitm_per_100"]} err={s["errors"]} in_hitm={s["errors_in_hitm"]}')
a = out["layer1_agreement"]; print({k: a[k] for k in ("hard_trigger_cases", "tier_match", "tier_and_suppression_reason_match", "rule_match", "paging_tier_match", "non_trigger_cases", "false_paging_triggers")}, a["confusion_label_vs_layer1"])
