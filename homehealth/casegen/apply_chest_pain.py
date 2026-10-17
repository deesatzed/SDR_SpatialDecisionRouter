"""Run chest-pain cases through trigger_eval.evaluate_chest_pain and update labels (relabels + smart library).
Non-trigger partners are reported, not changed, EXCEPT kind relabel_crescendo (Wayne's decided crescendo rule, 2026-10-17), which are relabelled and added to relabeled_cases, and kind new_partner (manual_cases.json)."""
import json, csv, sys, subprocess, copy
sys.path.insert(0, "../../casegen/trigger_engine"); import trigger_eval as T
P = T.load_params("../../casegen/trigger_engine/trigger_params.json")
CI = json.load(open("chest_inputs.json"))["cases"]
TIER_LABEL = {"ABSOLUTE": "ABSOLUTE", "CONFIRM_FIRST": "CONFIRM_FIRST", "LOG_ONLY": "SUPPRESSED"}
rows, changes, disputes = [], {}, []
for cid, x in CI.items():
    d = T.evaluate_chest_pain({"ts": 0.0, **x["inp"]}, P, context=x["ctx"])
    rows.append({"case_id": cid, "kind": x["kind"], "rule": d["rule"], "engine_tier": d["tier"], "band": d["band"], "raw_band": d["raw_band"], "confirm_step": d.get("confirm_step"),
                 "timeout_min": d.get("timeout_min"), "route": d["route"], "modifiers": " ; ".join(d["modifiers"]), "inputs_quote": x["quote"]})
    changes[cid] = d
json.dump({k: v for k, v in changes.items()}, open("chest_pain_eval.json", "w"), indent=1)
def apply(c, d):
    """Update one trigger case's labels from the engine decision. Returns a list of change strings."""
    old = {k: c.get(k) for k in ("trigger_tier", "confirm_step", "confirm_timeout_min", "expected_route", "acceptable_alternates", "suppression_reason", "hard_trigger_rule")}
    t = TIER_LABEL[d["tier"]]
    c["hard_trigger_rule"] = d["rule"] if d["rule"] != "HT_VS_DANGER" else c["hard_trigger_rule"]
    c["trigger_tier"] = t
    if t == "ABSOLUTE": c.update(confirm_step=None, confirm_timeout_min=None, suppression_reason=None, expected_route="escalate_human", acceptable_alternates=[])
    elif t == "CONFIRM_FIRST":
        c.update(confirm_step=d["confirm_step"], confirm_timeout_min=d["timeout_min"], suppression_reason=None, expected_route="escalate_human")
        if d["confirm_step"] == "already_confirmed": c["acceptable_alternates"] = []
    else: c.update(confirm_step=None, confirm_timeout_min=None, suppression_reason="below_band_threshold", expected_route="nurse_task")
    c["chest_pain_eval"] = {"band": d["band"], "raw_band": d["raw_band"], "modifiers": d["modifiers"], "tier": d["tier"], "timeout_min": d.get("timeout_min"), "engine": "trigger_eval.evaluate_chest_pain params " + P["version"]}
    new = {k: c.get(k) for k in old}
    return [f"{k}: {old[k]} -> {new[k]}" for k in old if old[k] != new[k]]
rel = json.load(open("relabeled_cases.json")); log = {}
for c in rel["cases"]:
    if c["case_id"] in changes and CI[c["case_id"]]["kind"].startswith("relabel"):
        log[c["case_id"]] = apply(c, changes[c["case_id"]])
        if log[c["case_id"]] or "chest_pain_update" not in c["relabel"]:
            c["relabel"]["chest_pain_update"] = log[c["case_id"]] or ["no label change (band recorded)"]
        log[c["case_id"]] = [x for x in c["relabel"]["chest_pain_update"] if "->" in x]
# --- Wayne's decided crescendo rule (2026-10-17 16:49 EDT): relabel non-trigger crescendo cases; re-pair AC1-P01 ---
LIBNOW = {c["case_id"]: c for c in json.load(open("library_v2_smart_accepted.json"))["cases"]}
TXT = {"AC1-002": [("so no hard trigger applies and the risk is in the pattern, not in a single reading.", "so no vital band is crossed, but the crescendo pattern itself is HT_CHEST_PAIN_VITALS CONFIRM_FIRST under the decided crescendo rule, and the 11:00 phone check already confirms the worsening."),
                   ("Same-day clinician review with an ECG and cardiology input is the right route, with escalation held in reserve if episodes occur at rest.", "Escalate now for clinician review with an ECG; the paired case is the same picture at his usual, unchanged frequency.")],
       "AC2-005": [("so this needs a same-day deeper review and a repeat haemoglobin rather than a routine follow-up.", "so no vital band is crossed; the new crescendo of stair-climbing episodes is HT_CHEST_PAIN_VITALS CONFIRM_FIRST under the decided crescendo rule (patient call, then escalate), with a repeat haemoglobin.")]}
new_rel = []
for cid, x in CI.items():
    if x["kind"] != "relabel_crescendo": continue
    if cid in {c["case_id"] for c in rel["cases"]}: continue
    c = copy.deepcopy(LIBNOW[cid]); c.pop("chest_pain_eval", None)
    c["prev_labels"] = {k: c.get(k) for k in ("expected_route", "acceptable_alternates", "hard_trigger", "hard_trigger_rule", "trigger_tier")}
    c["prev_grade"] = c.pop("grade", None)
    c["hard_trigger"] = True
    for a, b in TXT.get(cid, []):
        assert a in c["rationale"], (cid, a); c["rationale"] = c["rationale"].replace(a, b)
    ch = apply(c, changes[cid])
    if changes[cid]["confirm_step"] == "patient_call": c["acceptable_alternates"] = ["wake_specialist"]
    c["relabel"] = {"model": "deterministic (trigger_eval.evaluate_chest_pain + decided crescendo rule)", "checks": {"reliable_reading": "pass", "own_baseline_change": "pass (episode frequency rising)", "unexplained": "pass", "within_goals": "pass"},
                    "label_note": f"Was non-trigger {c['prev_labels']['expected_route']}. Now CONFIRM_FIRST under Wayne's decided crescendo rule (2026-10-17).", "policy": "SMART_TRIGGERS v1.3 section 7", "chest_pain_update": ch + ["hard_trigger: False -> True"]}
    rel["cases"].append(c); new_rel.append(cid); log[cid] = c["relabel"]["chest_pain_update"]
for c in rel["cases"]:
    if c["case_id"] == "AC1-003" and c.get("pair_id") == "AC1-P01":
        c["pair_id"] = None; c["pair_note"] = "Unpaired 2026-10-17: former partner AC1-002 now also escalates (crescendo rule); AC1-P01 is now AC1-002 (crescendo) vs AC1-012 (stable)."
        c["decisive_feature"] = c["decisive_feature"].replace(" (the paired case stays at 66 bpm)", "")
        c["relabel"].setdefault("chest_pain_update", []); c["relabel"]["chest_pain_update"] = [x for x in c["relabel"]["chest_pain_update"] if "pair_id" not in x] + ["pair_id: AC1-P01 -> None"]
        log["AC1-003"] = [x for x in c["relabel"]["chest_pain_update"] if "->" in x]
MANUAL = []
for c in json.load(open("manual_cases.json"))["cases"]:
    c = copy.deepcopy(c); c["hard_trigger"] = True
    ch = apply(c, changes[c["case_id"]]); c["acceptable_alternates"] = ["wake_specialist"]
    import os
    if os.path.exists("raw/CPRL2.grader.json"):
        v = {x["case_id"]: x for x in json.load(open("raw/CPRL2.grader.json"))["verdicts"]}.get(c["case_id"])
        if v: c["grade"] = {"grader": "google/gemini-4-argon GRADER_LLM3_v1.3 rev c", "batch": "CPRL2", "action": v.get("action"), "score": v.get("score"), "blind": v.get("blind")}
    c["pair_complete_in_accepted"] = True; MANUAL.append(c); log[c["case_id"]] = ["new case (stable-pattern partner of AC1-002)"]
json.dump(rel, open("relabeled_cases.json", "w"), indent=1)
R = {c["case_id"]: c for c in rel["cases"]}
# relabeled_cases.csv: refresh tier columns
rr = list(csv.DictReader(open("relabeled_cases.csv")))
for r in rr:
    c = R[r["case_id"]]; r.update(trigger_tier=c["trigger_tier"], confirm_step=c["confirm_step"], confirm_timeout_min=c["confirm_timeout_min"], new_route=c["expected_route"],
                                  route_changed=r["old_route"] != c["expected_route"], new_alternates="|".join(c["acceptable_alternates"] or []), new_rule=c["hard_trigger_rule"],
                                  chest_pain_band=(c.get("chest_pain_eval") or {}).get("band", ""), chest_pain_update=" ; ".join(log.get(r["case_id"], [])))
have = {r["case_id"] for r in rr}
for cid in [c["case_id"] for c in rel["cases"] if c["case_id"] not in have]:
    c = R[cid]; pl = c["prev_labels"]
    rr.append({"case_id": cid, "src_library": c.get("src_library"), "old_rule": pl.get("hard_trigger_rule"), "new_rule": c["hard_trigger_rule"], "trigger_tier": c["trigger_tier"], "confirm_step": c["confirm_step"],
               "confirm_timeout_min": c["confirm_timeout_min"], "suppression_reason": c["suppression_reason"], "old_route": pl["expected_route"], "new_route": c["expected_route"], "route_changed": pl["expected_route"] != c["expected_route"],
               "old_alternates": "|".join(pl["acceptable_alternates"] or []), "new_alternates": "|".join(c["acceptable_alternates"] or []), "merge_status": "accepted (crescendo rule relabel)", "checks": json.dumps(c["relabel"]["checks"]),
               "label_note": c["relabel"]["label_note"], "chest_pain_band": c["chest_pain_eval"]["band"], "chest_pain_update": " ; ".join(log.get(cid, []))})
for r in rr:
    r["pair_id"] = R[r["case_id"]].get("pair_id") or ""
# blind v1.3 regrades of chest-pain relabels (CPRL = banded rule, CPRL2 = crescendo rule)
import os
GR = {}
for tag in ("CPRL", "CPRL2"):
    if os.path.exists(f"raw/{tag}.grader.json"):
        for v in json.load(open(f"raw/{tag}.grader.json"))["verdicts"]: GR[v["case_id"]] = (tag, v)
for r in rr:
    if r["case_id"] in GR:
        tag, v = GR[r["case_id"]]; b = v["blind"]
        r.update(cp_regrade=tag, cp_regrade_route=b.get("grader_route"), cp_regrade_tier=b.get("grader_trigger_tier"), cp_regrade_band=b.get("grader_chest_pain_band"), cp_regrade_action=v.get("action"), cp_regrade_score=v.get("score"))
keys = []
for r in rr: keys += [k for k in r if k not in keys]
with open("relabeled_cases.csv", "w", newline="") as f: w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rr)
# smart library + new pairs
lib = json.load(open("library_v2_smart_accepted.json")); np_ = json.load(open("new_pairs.json"))
for coll in (lib["cases"], np_["cases"]):
    for i, c in enumerate(coll):
        cid = c["case_id"]
        if cid in R and cid in log: coll[i] = R[cid]
        elif cid in changes and CI[cid]["kind"] == "pair_ecg":
            log[cid] = apply(c, changes[cid]) or log.get(cid, [])
        elif cid in changes and CI[cid]["kind"] in ("pair_partner", "non_trigger_chest_pain"):
            c["chest_pain_eval"] = {**{k: changes[cid][k] for k in ("band", "raw_band", "modifiers", "tier")}, "timeout_min": changes[cid].get("timeout_min"), "note": "non-trigger case: evaluator output recorded, labels NOT changed"}
            if changes[cid]["tier"] in ("ABSOLUTE", "CONFIRM_FIRST") and c["expected_route"] != "escalate_human":
                disputes.append({"case_id": cid, "queue_reasons": "CP_RULE_DISPUTE", "expected_route": c["expected_route"], "grader_route": "", "decisive_feature": c.get("decisive_feature"),
                                 "grader_reasoning": f"evaluator: {changes[cid]['tier']} band {changes[cid]['band']} ({' ; '.join(changes[cid]['modifiers'])}); case is labelled non-trigger {c['expected_route']}", "pass": "chest_pain", "CLINICIAN_RULING (route)": "", "CLINICIAN_NOTE": ""})
ids = [c["case_id"] for c in lib["cases"]]
for m in MANUAL:
    if m["case_id"] in ids: lib["cases"][ids.index(m["case_id"])] = m
    else: lib["cases"].insert(ids.index("AC1-002") + 1, m); ids = [c["case_id"] for c in lib["cases"]]
for c in lib["cases"]:
    if c["case_id"] in ("AC1-002", "AC1-012"): c["pair_complete_in_accepted"] = True
lib.setdefault("provenance", {})["manual"] = "smart_triggers/manual_cases.json (AC1-012, hand-derived stable partner of AC1-002)"
json.dump(lib, open("library_v2_smart_accepted.json", "w"), indent=1)
S = json.load(open("summary.json")); S["library_v2_smart_n"] = len(lib["cases"]); S["relabel_n_total"] = len(rel["cases"]); S["crescendo_relabels"] = sorted(c for c in log if CI.get(c, {}).get("kind") == "relabel_crescendo")
json.dump(S, open("summary.json", "w"), indent=1); json.dump(np_, open("new_pairs.json", "w"), indent=1)
with open("chest_pain_eval.csv", "w", newline="") as f:
    for r in rows: r["label_change"] = " ; ".join(log.get(r["case_id"], [])) or ("(non-trigger, not changed)" if CI[r["case_id"]]["kind"] in ("pair_partner", "non_trigger_chest_pain") else "none")
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
# review queue: append disputes (idempotent)
q = list(csv.DictReader(open("review_queue.csv"))); q = [r for r in q if r.get("pass") != "chest_pain"] + disputes
keys = []
for r in q: keys += [k for k in r if k not in keys]
with open("review_queue.csv", "w", newline="") as f: w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(q)
print(subprocess.run(["python3", "../../casegen/convert_casegen.py", "--source=LIB=library_v2_smart_accepted.json:library_v2_smart:v2.2-v2.3", "--out-prefix=library_v2_smart_"], capture_output=True, text=True).stdout)
json.dump({"label_changes": log, "disputes": [d["case_id"] for d in disputes]}, open("chest_pain_changes.json", "w"), indent=1)
for r in rows: print(r["case_id"], r["kind"], r["engine_tier"], r["band"], r["raw_band"], r["confirm_step"], r["timeout_min"], "|", r["modifiers"], "|", r["label_change"])
