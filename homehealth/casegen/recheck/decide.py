"""Combine det.py (evaluator), proposals.json (Haiku) and grades.json (argon v1.3) into decisions.json. Local only, no API calls."""
import json, sys, os, collections
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
sys.path.insert(0, "../../casegen/prompts_v2"); import grade_merge as G
LIB = {c["case_id"]: c for c in json.load(open("pre_recheck/library_v2_smart_accepted.json"))["cases"]}
DET = {o["case_id"]: o for o in json.load(open("recheck/det_results.json"))["results"]}
PROP = {p["case_id"]: p for p in json.load(open("recheck/proposals.json"))["results"]}
GR = {v["case_id"]: v for v in json.load(open("recheck/grades.json"))["verdicts"]} if os.path.exists("recheck/grades.json") else {}
DET_RULES = {"HT_VS_DANGER", "HT_VS_IMPLAUSIBLE", "HT_SPO2_LT88", "HT_CHEST_PAIN_VITALS", "HT_GAP48_HIGHRISK"}
TMAP = {"LOG_ONLY": "SUPPRESSED"}
FIELDS = ["hard_trigger_rule", "trigger_tier", "suppression_reason", "confirm_step", "confirm_timeout_min", "baseline_layer"]
dec, review = [], []
for cid, p in PROP.items():
    c = LIB[cid]; d = DET[cid]; v = GR.get(cid); reasons = []; notes = []
    firm = [f for f in d["det_findings"] if not f["tier"].startswith("NEEDS_")]
    soft = [f for f in d["det_findings"] if f["tier"].startswith("NEEDS_")]
    mrule, mtier = (p.get("hard_trigger_rule"), p.get("trigger_tier")) if p.get("trigger_present") else (None, None)
    disagree = []
    for f in firm:
        ft = TMAP.get(f["tier"], f["tier"]); fr = f["rule"]
        if mrule != fr: disagree.append(f"evaluator {fr} {ft} ({f.get('vital', '')} {f.get('value', '')} day {f.get('day', '')}) vs model {mrule} {mtier}")
        elif mtier != ft: disagree.append(f"tier: evaluator {ft} vs model {mtier} ({fr})")
    for f in soft:
        if mrule != f["rule"]: notes.append(f"evaluator candidate {f['rule']} ({f['reason']}) not adopted by model")
    if mrule in DET_RULES and not any(f["rule"] == mrule for f in d["det_findings"]):
        disagree.append(f"model {mrule} {mtier} not found by evaluator screen" + ("" if d["scoreable"] else " (case not scoreable)"))
    if disagree: reasons.append("EVAL_MODEL_DISAGREE")
    cur_routes = [c["expected_route"]] + list(c.get("acceptable_alternates") or [])
    route_change = bool(p.get("route_change_needed")) or (p.get("trigger_present") and p.get("policy_route") not in cur_routes)
    if p.get("trigger_present") and mtier in ("ABSOLUTE", "CONFIRM_FIRST") and c["expected_route"] != "urgent_page": route_change = True
    if route_change: reasons.append("ROUTE_CHANGE")
    if p.get("critical_miss_risk"): reasons.append("CRITICAL_MISS")
    if any(f["tier"] == "ABSOLUTE" for f in firm) and c["expected_route"] != "urgent_page": reasons.append("CRITICAL_MISS_EVALUATOR")   # evaluator says ABSOLUTE, label does not escalate
    labelled = None
    if p.get("trigger_present"):
        labelled = {**c, "hard_trigger": True, **{f: p.get(f) for f in FIELDS}}
        sc = G.smart_checks(labelled) if hasattr(G, "smart_checks") else []
        if sc: reasons.append("SCRIPT_CHECK"); notes += sc
        if v is None: reasons.append("NOT_GRADED")
        else:
            b = v["blind"]; t = v.get("trigger_tier_correct") or {}
            if (v.get("baseline_layer_correct") or {}).get("drift_miss"): reasons.append("DRIFT_MISS")
            if t.get("critical_miss"): reasons.append("CRITICAL_MISS")
            g_ok = (b.get("grader_hard_trigger_rule") == mrule and b.get("grader_trigger_tier") == mtier and (mtier != "SUPPRESSED" or b.get("grader_suppression_reason") == p.get("suppression_reason"))
                    and t.get("ok") is not False and (v.get("expected_route_agree") or {}).get("verdict") == "agree" and v.get("action") == "keep")
            if not g_ok: reasons.append("GRADER_DISAGREE")
    elif firm: pass   # evaluator-only finding: already EVAL_MODEL_DISAGREE
    reasons = list(dict.fromkeys(reasons))
    apply_ = bool(p.get("trigger_present")) and not reasons
    rec = {"case_id": cid, "current_route": c["expected_route"], "current_alternates": c.get("acceptable_alternates"), "det_scoreable": d["scoreable"], "det_findings": d["det_findings"], "det_past_hard_limit": d["past_hard_limit"],
           "proposal": p, "grade": v, "disagreements": disagree, "notes": notes, "queue_reasons": reasons, "apply": apply_}
    dec.append(rec)
    if reasons:
        b = (v or {}).get("blind") or {}
        review.append({"case_id": cid, "queue_reasons": "|".join("RECHECK_" + r for r in reasons), "expected_route": c["expected_route"], "grader_route": b.get("grader_route", ""),
                       "decisive_feature": c.get("decisive_feature"), "proposed_rule": mrule, "proposed_tier": mtier, "proposed_suppression_reason": p.get("suppression_reason"),
                       "proposed_confirm_step": p.get("confirm_step"), "proposed_timeout_min": p.get("confirm_timeout_min"), "proposed_route": p.get("policy_route"),
                       "grader_rule": b.get("grader_hard_trigger_rule"), "grader_trigger_tier": b.get("grader_trigger_tier"), "grader_suppression_reason": b.get("grader_suppression_reason"),
                       "grader_reasoning": " || ".join(x for x in [b.get("reasoning") or "", ("evaluator: " + " ; ".join(disagree)) if disagree else "", " ; ".join(notes)] if x),
                       "evidence": p.get("evidence"), "grader_issue": ((v or {}).get("trigger_tier_correct") or {}).get("issue"), "grader_action": (v or {}).get("action"), "grader_score": (v or {}).get("score"), "pass": "recheck", "CLINICIAN_RULING (route)": "", "CLINICIAN_NOTE": ""})
S = {"n_checked": len(dec), "det_scoreable": sum(r["det_scoreable"] for r in dec), "det_with_findings": sum(bool(r["det_findings"]) for r in dec),
     "model_trigger_present": sum(bool(r["proposal"].get("trigger_present")) for r in dec), "graded": sum(r["grade"] is not None for r in dec),
     "applied": sum(r["apply"] for r in dec),
     "applied_by_tier_reason": collections.Counter(f"{r['proposal'].get('trigger_tier')}/{r['proposal'].get('suppression_reason')}" for r in dec if r["apply"]),
     "applied_by_rule": collections.Counter(r["proposal"].get("hard_trigger_rule") for r in dec if r["apply"]),
     "proposed_by_tier_reason": collections.Counter(f"{r['proposal'].get('trigger_tier')}/{r['proposal'].get('suppression_reason')}" for r in dec if r["proposal"].get("trigger_present")),
     "route_changes_proposed": [r["case_id"] for r in dec if "ROUTE_CHANGE" in r["queue_reasons"]],
     "eval_model_disagree": [r["case_id"] for r in dec if "EVAL_MODEL_DISAGREE" in r["queue_reasons"]],
     "critical_miss": [r["case_id"] for r in dec if "CRITICAL_MISS" in r["queue_reasons"]], "critical_miss_evaluator_only": [r["case_id"] for r in dec if "CRITICAL_MISS_EVALUATOR" in r["queue_reasons"]], "drift_miss": [r["case_id"] for r in dec if "DRIFT_MISS" in r["queue_reasons"]],
     "grader_disagree": [r["case_id"] for r in dec if "GRADER_DISAGREE" in r["queue_reasons"]], "script_check": [r["case_id"] for r in dec if "SCRIPT_CHECK" in r["queue_reasons"]],
     "review_rows": len(review), "soft_notes": {r["case_id"]: r["notes"] for r in dec if r["notes"] and not r["queue_reasons"]}}
json.dump({"summary": S, "decisions": dec, "review_rows": review}, open("recheck/decisions.json", "w"), indent=1)
print(json.dumps(S, indent=1))
