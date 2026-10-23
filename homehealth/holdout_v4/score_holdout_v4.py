"""Score Layer 1 v1.11.2 (params 0.11.2-placeholder) on holdout_v4 (SYNTHETIC) against the AUTHOR labels (merged author+grader, accepted set). ZERO TUNING:
the accepted cases were frozen (committed) before this script was first run. Jev picks: jev/parsed (prompt v1.10, 4 variants, base scored).
Systems: Layer 1 alone (decided cases), L1 + d1-ultra, L1 + pplx, L1 + dual (cautious_max_hitm, default). Writes results/summary.json and review_queue.csv
(ranked by stakes: critical misses, over-routes (false pages first), Layer 1 trigger misses caught by Jev, then merge disputes). Under-triage that is not a
critical miss is listed after over-routes. Usage: python3 score_holdout_v4.py"""
import csv, json, os, sys, collections
HO = os.path.dirname(os.path.abspath(__file__)); JB = os.path.join(HO, "..", "jev_baseline"); sys.path.insert(0, JB)
import score_v110 as V, dual_jev as D, score_l1jev as SL, layer1_adapter as L  # noqa: E402
cases = json.load(open(f"{HO}/holdout_v4_accepted.json"))["cases"]
P = {m: D.load_picks(f"{HO}/jev/parsed/{SL.S_slug(m)}.jsonl") for m in D.DUAL_MODELS}
C0 = {c["case_id"]: c for c in cases}
res = V.run(cases, P); l1 = {c["case_id"]: L.evaluate_case(c) for c in cases}
tk = [c for c in cases if c.get("expected_device_ticket")]
tk_hit = [c["case_id"] for c in tk if (l1[c["case_id"]].get("device_ticket") or {}).get("type") == c["expected_device_ticket"]]
tk_any = [c["case_id"] for c in tk if l1[c["case_id"]].get("device_ticket")]
tk_fp = [i for i, d in l1.items() if d.get("device_ticket") and i not in {c["case_id"] for c in tk}]
dec = [i for i, d in l1.items() if d.get("tier")]
pr = [i for i in dec if l1[i].get("plain_reason") and not l1[i]["plain_reason"].startswith("Layer 1 rule")]
for s in V.SYS:
    e = res[s]["errors"]; res[s]["n_errors"] = len(e); res[s]["errors_caught_by_hitm"] = sum(1 for x in e if x["hitm"])
out = {"params": L.PARAMS.get("version"), "jev_prompt": "v1.10", "label_source": "author labels (merged author+grader accepted set); not clinician-ruled",
       "n_cases": len(cases), "missing_picks": {m: [c["case_id"] for c in cases if "LIB-" + c["case_id"] not in P[m]] for m in P},
       "systems": {s: res[s] for s in V.SYS}, "tier_agreement": res["tier_agreement"],
       "device_ticket_coverage": {"expected": len(tk), "type_match": len(tk_hit), "any_ticket": len(tk_any), "missed_ids": [c["case_id"] for c in tk if c["case_id"] not in tk_hit], "unexpected_ticket_ids": tk_fp},
       "plain_reason_coverage": {"layer1_decisions": len(dec), "with_plain_reason": len(pr), "missing_ids": [i for i in dec if i not in pr]}}
# challenger (not part of the default): dual(d1-ultra lead + nace-ai/drex-max) via the same combiner, and Jev-decided-only accuracy (cases Layer 1 leaves to Jev)
PX = D.load_picks(f"{HO}/jev/parsed/{SL.S_slug('nace-ai/drex-max')}.jsonl")
rc = V.run(cases, {"liquid/d1-ultra": P["liquid/d1-ultra"], "perplexity/pplx-decider-v1.2": PX})[V.SYS[0]]
rc["n_errors"] = len(rc["errors"]); rc["errors_caught_by_hitm"] = sum(1 for x in rc["errors"] if x["hitm"])
jd = [i for i, d in l1.items() if L.route(d, None)[0] is None]
def jd_acc(m): e = {x["case"] for x in m["errors"]}; w = [i for i in jd if i in e]; return {"n": len(jd), "correct": len(jd) - len(w), "accuracy": V.S.rate(len(jd) - len(w), len(jd)), "wrong_ids": w}
out["challenger_dual_d1_drex"] = rc; out["jev_decided_ids"] = jd
out["jev_decided_accuracy"] = {**{s: jd_acc(res[s]) for s in V.SYS if s != "Layer 1 alone"}, "L1 + dual(d1-ultra, drex-max) [challenger]": jd_acc(rc)}
out["critical_miss_detail"] = {i: {"label": C0[i]["expected_route"], "decisive_feature": C0[i].get("decisive_feature")} for s in list(res) if s in V.SYS for i in res[s]["critical_ids"]}
out["critical_miss_detail"].update({i: {"label": C0[i]["expected_route"], "decisive_feature": C0[i].get("decisive_feature")} for i in rc["critical_ids"]})
os.makedirs(f"{HO}/results", exist_ok=True); json.dump(out, open(f"{HO}/results/summary.json", "w"), indent=1)
for s in V.SYS:
    m = res[s]; print(f'{s:26s} acc={m["accuracy"]} ({m["decided"]}/{m["n"]}) crit={m["critical_misses"]} {m["critical_ids"]} fp/100={m["false_pages_per_100"]} hitm/100={m["hitm_per_100"]} err={m["n_errors"]} caught={m["errors_caught_by_hitm"]}')
m = rc; print(f'{"dual(d1+drex) challenger":26s} acc={m["accuracy"]} ({m["decided"]}/{m["n"]}) crit={m["critical_misses"]} {m["critical_ids"]} fp/100={m["false_pages_per_100"]} hitm/100={m["hitm_per_100"]} err={m["n_errors"]}')
print("jev-decided", json.dumps(out["jev_decided_accuracy"]))
print("crit", json.dumps(out["critical_miss_detail"]))
print("tickets", out["device_ticket_coverage"], "plain", out["plain_reason_coverage"])
RANK = {"silent_log": 0, "nurse_task": 1, "provider_task": 2, "urgent_page": 3}
C = {c["case_id"]: c for c in cases}; rows = {}
def stake(e):
    lab, pk = e["label"], e["picked"]
    if lab == "urgent_page" and pk != "urgent_page": return 0, "critical_miss"
    if RANK.get(pk, 0) > RANK[lab]: return 1, ("over_route_false_page" if pk == "urgent_page" else "over_route")
    return 2, "under_triage"
for s_ in V.SYS:
    for e in res[s_]["errors"]:
        k, why = stake(e); r = rows.setdefault(e["case"], {"k": k, "why": why, "sys": [], "label": e["label"]})
        r["sys"].append(f'{s_}: picked {e["picked"]} (L1 {e["l1"]}/{e["l1_reason"]}, HITM {"yes" if e["hitm"] else "no"})')
        if k < r["k"]: r["k"], r["why"] = k, why
cols = ["case_id", "age_band", "sex", "living", "patient_goals", "pmh", "meds", "recent_med_changes", "devices", "baseline_30d", "baseline_status", "trend_last_7d", "caregiver_or_nurse_note", "data_quality"]
def bg(c): return [json.dumps(c.get(k), ensure_ascii=False) if isinstance(c.get(k), (dict, list)) else (c.get(k) if c.get(k) is not None else "") for k in cols]
out_rows = []
for cid, r in rows.items():
    c = C[cid]; out_rows.append((r["k"], -RANK[r["label"]], cid, [r["why"]] + bg(c) + [c["expected_route"], c.get("hard_trigger_rule") or "", c.get("trigger_tier") or "", "", "", " | ".join(r["sys"]), "scoring_error", "", ""]))
for cid, tier, l1t, why in res["tier_agreement"]["mismatch"]:
    if cid in rows: continue
    c = C[cid]; out_rows.append((3, -RANK[c["expected_route"]], cid, ["layer1_trigger_miss_caught_by_jev"] + bg(c) + [c["expected_route"], c.get("hard_trigger_rule") or "", tier or "", "", "", f"Layer 1: {l1t or 'no tier'} / {why}; every Jev-backed system routed it correctly", "layer1_trigger_miss", "", ""]))
for d in csv.DictReader(open(f"{HO}/merge_disputes.csv")):
    hi = max(RANK.get(d["author_route"], 0), RANK.get(d["grader_route"], 0))
    out_rows.append((4, -hi, d["case_id"], ["merge_dispute"] + [d[k] for k in cols] + [d["author_route"], d["author_trigger_rule"], d["author_tier"], d["grader_route"], d["grader_tier"], d["queue_reasons"] + ": " + d["grader_reasoning"], "merge_dispute (not in accepted set; no stack score)", "", ""]))
out_rows.sort(key=lambda x: (x[0], x[1], x[2]))
with open(f"{HO}/review_queue.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["stakes", "rank"] + cols + ["label_or_author_route", "rule", "tier", "grader_route", "grader_tier", "detail", "queue_source", "CLINICIAN_RULING (route)", "CLINICIAN_NOTE"])
    for i, x in enumerate(out_rows, 1): w.writerow([x[3][0], i] + x[3][1:])
print("review_queue rows", len(out_rows), dict(collections.Counter(x[3][0] for x in out_rows)))
