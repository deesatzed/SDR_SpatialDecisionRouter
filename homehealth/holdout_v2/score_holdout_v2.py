"""Score the FROZEN stack (e8c7aa0, SMART_TRIGGERS v1.10.1) on holdout_v2 (SYNTHETIC). Stored picks only, no API calls, no tuning.
Systems: L1 + dual (cautious_max_hitm, default), L1 + d1-ultra, L1 + pplx, Layer 1 alone (decided cases). Labels = merged author+grader labels (accepted set).
Every error lists whether the HITM flag caught it. Compares to holdout_v1 pre-fix numbers (holdout_v1/results/summary.json)."""
import json, os, sys
HO = os.path.dirname(os.path.abspath(__file__))
JB = os.environ.get("JEV_BASELINE_DIR", "/workspace/sdr_rename/homehealth/jev_baseline"); sys.path.insert(0, JB)
import score_v110 as V, dual_jev as D, score_l1jev as SL, layer1_adapter as L  # noqa: E402
cases = json.load(open(f"{HO}/holdout_v2_accepted.json"))["cases"]
P = {m: D.load_picks(f"{HO}/jev/parsed/{SL.S_slug(m)}.jsonl") for m in D.DUAL_MODELS}
res = V.run(cases, P)
for s in V.SYS:
    e = res[s]["errors"]; res[s]["errors_caught_by_hitm"] = sum(1 for x in e if x["hitm"]); res[s]["errors_not_caught"] = [x["case"] for x in e if not x["hitm"]]
    res[s]["n_errors"] = len(e)
pre = {}
for p in (os.environ.get("HO1_SUMMARY", ""), "/workspace/jevfly_smoke/holdout_v1/results/summary.json", os.path.join(HO, "..", "holdout", "results", "summary.json")):
    if p and os.path.exists(p):
        S1 = json.load(open(p))["systems"]
        pre = {k: {x: S1[k][x] for x in ("accuracy", "critical_misses", "false_pages_per_100", "hitm_per_100", "errors", "errors_in_hitm")} for k in ("L1 + dual (c) [default]", "L1 + d1-ultra", "L1 + pplx") if k in S1}
        pre["layer1_agreement"] = {x: S1 and json.load(open(p))["layer1_agreement"].get(x) for x in ("hard_trigger_cases", "tier_match")}; break
out = {"frozen_commit": "e8c7aa0", "smart_triggers": "v1.10.1", "n_cases": len(cases), "systems": {s: res[s] for s in V.SYS}, "tier_agreement": res["tier_agreement"], "l1": res["l1"], "holdout_v1_prefix_60": pre}
os.makedirs(f"{HO}/results", exist_ok=True); json.dump(out, open(f"{HO}/results/summary.json", "w"), indent=1)
for s in V.SYS:
    m = res[s]; print(f'{s:26s} acc={m["accuracy"]} ({m["decided"]}/{m["n"]}) crit={m["critical_misses"]} {m["critical_ids"]} fp/100={m["false_pages_per_100"]} hitm/100={m["hitm_per_100"]} err={m["n_errors"]} caught={m["errors_caught_by_hitm"]}')
t = res["tier_agreement"]; print("tier agreement", t["match"], "/", t["trigger_cases"], "false paging triggers", t["false_paging_triggers_on_no_trigger_cases"])
print("holdout_v1 pre-fix:", json.dumps(pre))
