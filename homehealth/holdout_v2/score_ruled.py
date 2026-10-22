"""Re-score holdout_v2 on the ruled key (holdout_v2_ruled_key.json) from STORED picks only (SYNTHETIC; no API calls).
Picks exist only for the 65 accepted cases (jev/parsed, frozen e8c7aa0). The 16 queued disputes were never sent to Jev, so model
stacks are scored on accepted65; Layer 1 alone is also scored on all81 and disputed16. 'before' = results/summary.json (author labels)."""
import json, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); JB = os.path.join(HO, "..", "jev_baseline"); sys.path.insert(0, JB)
import score_v110 as V, dual_jev as D, score_l1jev as SL  # noqa: E402
K = json.load(open(os.path.join(HO, "holdout_v2_ruled_key.json")))["cases"]
P = {m: D.load_picks(os.path.join(HO, "jev", "parsed", SL.S_slug(m) + ".jsonl")) for m in D.DUAL_MODELS}
acc = [c for c in K if c["key_source"] != "clinician_ruling_2026-10-22"]; disp = [c for c in K if c["key_source"] == "clinician_ruling_2026-10-22"]
KEEP = ("n", "decided", "accuracy", "critical_misses", "critical_ids", "false_pages_per_100", "false_page_ids", "hitm_per_100", "errors")
def run(cs): r = V.run(cs, P); return {s: {k: r[s][k] for k in KEEP} for s in V.SYS}
before = json.load(open(os.path.join(HO, "results", "summary.json")))["systems"]
out = {"frozen_commit": "e8c7aa0", "smart_triggers": "v1.10.1", "paid_calls_this_run": 0,
       "before_accepted65": {s: {k: before[s][k] for k in KEEP if k in before[s]} for s in V.SYS},
       "after_accepted65": run(acc), "after_all81_layer1_only": run(K)["Layer 1 alone"], "after_disputed16_layer1_only": run(disp)["Layer 1 alone"]}
os.makedirs(os.path.join(HO, "results_ruled"), exist_ok=True); json.dump(out, open(os.path.join(HO, "results_ruled", "summary.json"), "w"), indent=1)
if __name__ == "__main__":
    f = lambda v: f'acc={v["accuracy"]} ({v["decided"]}/{v["n"]}) crit={v["critical_misses"]} {v["critical_ids"]} fp/100={v["false_pages_per_100"]} {v.get("false_page_ids")} hitm/100={v["hitm_per_100"]} err={len(v["errors"])}'
    for part in ("before_accepted65", "after_accepted65"):
        for s, v in out[part].items(): print(part, s, f(v))
    print("all81 L1", f(out["after_all81_layer1_only"])); print("disp16 L1", f(out["after_disputed16_layer1_only"]))
    for s in ("L1 + dual (c) [default]", "Layer 1 alone"):
        print("ERRORS after", s); [print(" ", e) for e in out["after_accepted65"][s]["errors"]]
    print("ERRORS disp16 L1"); [print(" ", e) for e in out["after_disputed16_layer1_only"]["errors"]]
