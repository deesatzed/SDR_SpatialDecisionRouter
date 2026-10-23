"""Re-score holdout_v3 (SYNTHETIC) against the clinician-ruled key (holdout_v3_ruled_key.json, 80 cases): Layer 1 v1.10.3 vs v1.11.0.
Systems: Layer 1 alone and the default L1 + dual (cautious_max_hitm). Stored Jev picks only: jev/parsed (63 accepted) + jev_disputes/parsed (17 disputes, run 2026-10-23, $0.0037).
Usage: python3 score_v1112.py <jev_baseline dir> <label> [picks dir ...]  (v1.11.2: optional picks dirs override the stored v1.9 picks, e.g. jev_v110/parsed for the v1.10 trend-summary prompt)  -> prints one JSON line (run by run_v1110_compare.sh; does NOT rewrite review_queue.csv).
CAVEAT: v1.11.0 rule fixes were built from library PRACTICE cases, but the clinician rulings on these holdout_v3 cases set the direction of the fixes, so holdout_v3 is now partly tuning data. A fresh holdout_v4 is needed for an unbiased estimate."""
import json, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); JB, LABEL, OVR = sys.argv[1], sys.argv[2], sys.argv[3:]; sys.path.insert(0, JB)
import score_v110 as V, dual_jev as D, score_l1jev as SL, layer1_adapter as L  # noqa: E402
cases = json.load(open(f"{HO}/holdout_v3_ruled_key.json"))["cases"]
P = {}
for m in D.DUAL_MODELS:
    P[m] = D.load_picks(f"{HO}/jev/parsed/{SL.S_slug(m)}.jsonl"); P[m].update(D.load_picks(f"{HO}/jev_disputes/parsed/{SL.S_slug(m)}.jsonl"))
    for o in OVR: P[m].update(D.load_picks(f"{o}/{SL.S_slug(m)}.jsonl"))
res = V.run(cases, P); l1 = {c["case_id"]: L.evaluate_case(c) for c in cases}
tk = [c for c in cases if c.get("expected_device_ticket")]
tk_hit = [c["case_id"] for c in tk if (l1[c["case_id"]].get("device_ticket") or {}).get("type") == c["expected_device_ticket"]]
dec = [i for i, d in l1.items() if d.get("tier")]
pr = [i for i in dec if l1[i].get("plain_reason") and not l1[i]["plain_reason"].startswith("Layer 1 rule")]
out = {"label": LABEL, "n": len(cases), "missing_picks": {m: [c["case_id"] for c in cases if "LIB-" + c["case_id"] not in P[m]] for m in P},
       "ticket_coverage": {"expected": len(tk), "hit": len(tk_hit), "hit_ids": tk_hit},
       "plain_reason_coverage": {"layer1_decisions": len(dec), "with_plain_reason": len(pr)}}
for s in (V.SYS[0], V.SYS[-1]):
    m = res[s]; out[s] = {k: m[k] for k in ("n", "decided", "accuracy", "critical_misses", "critical_ids", "false_pages_per_100", "false_page_ids", "hitm_per_100")}
    out[s]["errors"] = [(e["case"], e["label"], e["picked"]) for e in m["errors"]]
print(json.dumps(out))
