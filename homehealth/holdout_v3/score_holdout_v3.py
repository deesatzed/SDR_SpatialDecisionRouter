"""Score the FROZEN stack (fb262af, SMART_TRIGGERS v1.10.3) on holdout_v3 (SYNTHETIC). Stored picks only, no API calls, no tuning.
Systems: L1 + dual (cautious_max_hitm, default), L1 + d1-ultra, L1 + pplx, Layer 1 alone (decided cases). Labels = merged author+grader labels (accepted set).
Every error lists whether the HITM flag caught it. Compares to holdout_v1 pre-fix numbers (holdout_v1/results/summary.json)."""
import json, os, sys
HO = os.path.dirname(os.path.abspath(__file__))
JB = os.environ.get("JEV_BASELINE_DIR", "/workspace/sdr_rename/homehealth/jev_baseline"); sys.path.insert(0, JB)
import score_v110 as V, dual_jev as D, score_l1jev as SL, layer1_adapter as L  # noqa: E402
cases = json.load(open(f"{HO}/holdout_v3_accepted.json"))["cases"]
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
out = {"frozen_commit": "fb262af", "smart_triggers": "v1.10.3", "n_cases": len(cases), "systems": {s: res[s] for s in V.SYS}, "tier_agreement": res["tier_agreement"], "l1": res["l1"], "holdout_v1_prefix_60": pre}
os.makedirs(f"{HO}/results", exist_ok=True); json.dump(out, open(f"{HO}/results/summary.json", "w"), indent=1)
for s in V.SYS:
    m = res[s]; print(f'{s:26s} acc={m["accuracy"]} ({m["decided"]}/{m["n"]}) crit={m["critical_misses"]} {m["critical_ids"]} fp/100={m["false_pages_per_100"]} hitm/100={m["hitm_per_100"]} err={m["n_errors"]} caught={m["errors_caught_by_hitm"]}')
t = res["tier_agreement"]; print("tier agreement", t["match"], "/", t["trigger_cases"], "false paging triggers", t["false_paging_triggers_on_no_trigger_cases"])
print("holdout_v1 pre-fix:", json.dumps(pre))

# review_queue.csv = scoring errors (any system) + merge disputes, ordered by stakes: critical miss > false page > under-triage > over-triage > dispute (urgent first)
import csv
RANK = {"silent_log": 0, "nurse_task": 1, "provider_task": 2, "urgent_page": 3}
C = {c["case_id"]: c for c in cases}; rows = {}
def stake(e):
    lab, pk = e["label"], e["picked"]
    if lab == "urgent_page" and pk != "urgent_page": return 0, "critical_miss"
    if pk == "urgent_page": return 1, "false_page"
    return (2, "under_triage") if RANK.get(pk, 0) < RANK[lab] else (3, "over_triage")
for s_ in V.SYS:
    for e in res[s_]["errors"]:
        k, why = stake(e); r = rows.setdefault(e["case"], {"k": k, "why": why, "sys": [], "label": e["label"]})
        r["sys"].append(f'{s_}: picked {e["picked"]} (L1 {e["l1"]}/{e["l1_reason"]}, HITM {"yes" if e["hitm"] else "no"})')
        if k < r["k"]: r["k"], r["why"] = k, why
G = {c["case_id"]: c for f in sorted(os.listdir(f"{HO}/gen")) if f.endswith(".batch.json") for c in json.load(open(f"{HO}/gen/{f}"))["cases"]}
cols = ["case_id", "age_band", "sex", "living", "patient_goals", "pmh", "meds", "recent_med_changes", "devices", "baseline_30d", "baseline_status", "trend_last_7d", "caregiver_or_nurse_note", "data_quality"]
def bg(c): return [json.dumps(c.get(k), ensure_ascii=False) if isinstance(c.get(k), (dict, list)) else (c.get(k) if c.get(k) is not None else "") for k in cols]
out_rows = []
for cid, r in rows.items():
    c = C[cid]; out_rows.append((r["k"], -RANK[r["label"]], cid, [r["why"]] + bg(c) + [c["expected_route"], c.get("hard_trigger_rule") or "", c.get("trigger_tier") or "", "", "", " | ".join(r["sys"]), "scoring_error", "", ""]))
for cid, tier, l1t, why in res["tier_agreement"]["mismatch"]:   # Jev not run (key limit): a labelled trigger Layer 1 did not fire = unprotected by the hard floor
    if cid in rows: continue
    c = C[cid]; out_rows.append((3.5, -RANK[c["expected_route"]], cid, ["layer1_trigger_miss_caught_by_jev (all 3 Jev systems correct)"] + bg(c) + [c["expected_route"], c.get("hard_trigger_rule") or "", tier or "", "", "", f"Layer 1: {l1t or 'no tier'} / {why}; every Jev-backed system routed it correctly", "layer1_trigger_miss", "", ""]))
for d in csv.DictReader(open(f"{HO}/merge_disputes.csv")):
    hi = max(RANK.get(d["author_route"], 0), RANK.get(d["grader_route"], 0))
    out_rows.append((4, -hi, d["case_id"], ["merge_dispute"] + [d[k] for k in cols] + [d["author_route"], d["author_trigger_rule"], d["author_tier"], d["grader_route"], d["grader_tier"], d["queue_reasons"] + ": " + d["grader_reasoning"], "merge_dispute (not in accepted set; no stack score)", "", ""]))
# manual near-dup flag (Wayne 2026-10-23): HW1-001 repeats holdout_v2 HV2-001 ("went down like a sack of potatoes", eyes rolled back, unresponsive, came to on the floor); Jaccard check missed it
ND = {"HW1-001": "NEAR-DUP of holdout_v2 HV2-001 (same syncope narrative: 'went down like a sack of potatoes', eyes rolled back, came to on the floor) - SUGGEST DROP"}
for i, x in enumerate(out_rows):
    if x[2] in ND: x[3][-1] = ND[x[2]]
if not any(x[2] in ND for x in out_rows) and "HW1-001" in C:
    c = C["HW1-001"]; out_rows.append((5, 0, "HW1-001", ["near_dup_suggest_drop"] + bg(c) + [c["expected_route"], c.get("hard_trigger_rule") or "", c.get("trigger_tier") or "", "", "", "scored correctly; flagged for provenance only", "near_dup", "", ND["HW1-001"]]))
out_rows.sort(key=lambda x: (x[0], x[1], x[2]))
with open(f"{HO}/review_queue.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["stakes", "rank"] + cols + ["label_or_author_route", "rule", "tier", "grader_route", "grader_tier", "detail", "queue_source", "CLINICIAN_RULING (route)", "CLINICIAN_NOTE"])
    for i, x in enumerate(out_rows, 1): w.writerow([x[3][0], i] + x[3][1:])
print("review_queue rows", len(out_rows), dict(__import__("collections").Counter(x[3][0] for x in out_rows)))
