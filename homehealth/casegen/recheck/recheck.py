"""Re-check non-trigger cases under SMART_TRIGGERS v1.3 (SYNTHETIC). Steps: propose (Haiku, independent of det.py), grade (argon v1.3, blind, compact verdicts), decide (local).
Resumable via smart_run.call (raw/RC_*.ok.json). Budget: STEP_LIMIT env (absolute spend). Never prints the key."""
import os, sys, json, threading
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/.."); sys.path.insert(0, os.getcwd())
import smart_run as S
P = json.load(open("../../casegen/trigger_engine/trigger_params.json"))
LIB = json.load(open("pre_recheck/library_v2_smart_accepted.json"))["cases"]
NT = [c for c in LIB if not c.get("hard_trigger")]
KEEP = ["case_id", "age_band", "sex", "living", "pmh", "function_baseline", "patient_goals", "discharge", "meds", "recent_med_changes", "devices", "baseline_30d", "trend_last_7d", "caregiver_or_nurse_note", "data_quality", "expected_route", "acceptable_alternates", "category"]
compact = lambda c: {k: c.get(k) for k in KEEP}
PROPOSE_SYS = S.POLICY + "\n\n---\n## Hard-limit parameters (trigger_params.json, placeholders)\n" + json.dumps({k: v for k, v in P["hard_limits"].items() if k != "_note"}) + """

## Your task: re-check accepted synthetic cases that are currently labelled as NON-trigger
For each case decide, under this policy (v1.3, sections 1-7), whether any hard-trigger rule's condition is met by data from the last 48 h (Day -1 and Day 0).
Rules: HT_SPO2_LT88, HT_GAP48_HIGHRISK, HT_FALL_ANTICOAG, HT_SYNCOPE, HT_FOCAL_NEURO, HT_CHEST_PAIN_ECG, HT_CHEST_PAIN_VITALS (banded, crescendo rule), HT_VS_DANGER (hard danger limits above), HT_VS_IMPLAUSIBLE (implausible values or rates).
- A rule that fired only on older days and has resolved does NOT count. Note it in `older_event` instead.
- Do not invent triggers. If no condition is met, set trigger_present false and leave the other fields null.
- If a trigger fires, apply the four checks and give the tier:
  - ABSOLUTE, or CONFIRM_FIRST with confirm_step and confirm_timeout_min.
  - SUPPRESSED with suppression_reason: unreliable_reading, at_patient_baseline, explained, goals_of_care or below_band_threshold.
  - ARTIFACT with a recheck step and timeout.
- policy_route is the route the policy implies for the WHOLE case (silent_log | nurse_task | wake_specialist | escalate_human). A suppressed trigger normally keeps the case's existing clinical route.
- route_change_needed is true only if policy_route is neither the current expected_route nor in acceptable_alternates.
- critical_miss_risk is true if a real (unsuppressed) trigger is present and the current label does not escalate.
Output ONLY {"results":[{"case_id":"...","trigger_present":true|false,"hard_trigger_rule":null,"trigger_tier":null,"suppression_reason":null,"confirm_step":null,"confirm_timeout_min":null,"baseline_layer":null,"chest_pain_band":null,"policy_route":"...","route_change_needed":false,"critical_miss_risk":false,"evidence":"<=25-word quote from the case","older_event":null,"note":"<=20 words"}]} with one entry per input case, in input order."""
GRADE_NOTE = """This is a RE-CHECK QA batch: accepted cases that were non-trigger; the labels now carry PROPOSED trigger fields. Do the blind pass first from the case data, then judge the labels.
Return COMPACT verdicts only (cost control), one per case:
{"verdicts":[{"case_id":"...","blind":{"grader_route":"...","grader_hard_trigger_rule":"HT_...|null","grader_trigger_tier":"ABSOLUTE|CONFIRM_FIRST|SUPPRESSED|ARTIFACT|null","grader_suppression_reason":"...|null","grader_baseline_layer":"...|null","confidence":0.0,"reasoning":"<=30 words"},
"trigger_tier_correct":{"ok":true,"suggested_tier":null,"suggested_confirm_step":null,"suggested_suppression_reason":null,"critical_miss":false,"issue":null},
"baseline_layer_correct":{"drift_miss":false},"expected_route_agree":{"verdict":"agree|disagree","grader_route":"..."},"action":"keep|fix|reject","score":1-5}]}"""
def propose():
    k = 50; chunks = [NT[i:i + k] for i in range(0, len(NT), k)]; res = {}
    def one(j, cs):
        u = json.dumps({"n": len(cs), "cases": [compact(c) for c in cs]})
        o = S.call(f"RC_PROP_{j}", S.HAIKU, PROPOSE_SYS, u, 32000, 0.2, {"reasoning": {"effort": "low"}},
                   need=lambda o: isinstance(o, dict) and [r.get("case_id") for r in o.get("results", [])] == [c["case_id"] for c in cs])
        res[j] = o
    ts = [threading.Thread(target=one, args=(j, cs)) for j, cs in enumerate(chunks)]; [t.start() for t in ts]; [t.join() for t in ts]
    allr = []
    for j in range(len(chunks)):
        if not res.get(j): S.log(f"RC propose chunk {j} missing"); return None
        allr += res[j]["results"]
    json.dump({"n": len(allr), "model": S.HAIKU, "results": allr}, open("recheck/proposals.json", "w"), indent=1); return allr
FIELDS = ["hard_trigger_rule", "trigger_tier", "suppression_reason", "confirm_step", "confirm_timeout_min", "baseline_layer"]
def labelled(c, p):
    c = S.clean(dict(c)); c.pop("chest_pain_eval", None); c.pop("prev_labels", None); c.pop("prev_grade", None)
    c["hard_trigger"] = True; c.update({f: p.get(f) for f in FIELDS})
    if p.get("route_change_needed"): c["expected_route"] = p["policy_route"]
    return c
def grade(props):
    L = {c["case_id"]: c for c in NT}
    todo = [p for p in props if p.get("trigger_present")]
    k = 25; chunks = [todo[i:i + k] for i in range(0, len(todo), k)]; res = {}
    def one(j, ps):
        u = json.dumps({"batch_id": f"RC_GRADE_{j}", "requested": {"n": len(ps), "purpose": "re-check QA (see note); no route mix, minimums or novelty in scope", "routes": None, "hard_plus_adversarial_min_pct": 0, "minimums": {}},
                        "note": GRADE_NOTE, "do_not_repeat": [], "batch": {"cases": [labelled(L[p["case_id"]], p) for p in ps], "tally": None}})
        res[j] = S.call(f"RC_GRADE_{j}", S.GRADERM, S.GRADER3 + "\n\n---\n" + GRADE_NOTE, u, 24000, 0.2, need=lambda o: isinstance(o, dict) and len(o.get("verdicts", [])) >= len(ps))
    ts = [threading.Thread(target=one, args=(j, ps)) for j, ps in enumerate(chunks)]; [t.start() for t in ts]; [t.join() for t in ts]
    v = []
    for j in range(len(chunks)):
        if res.get(j): v += res[j]["verdicts"]
        else: S.log(f"RC grade chunk {j} missing")
    json.dump({"n_graded": len(v), "n_proposed": len(todo), "grader": S.GRADERM + " GRADER_LLM3_v1.3 rev c (compact)", "verdicts": v}, open("recheck/grades.json", "w"), indent=1); return v
if __name__ == "__main__":
    S.log(f"RECHECK {sys.argv[1]} start spend=${S.spend():.3f}")
    if sys.argv[1] == "propose": r = propose(); S.log(f"RC proposals: {len(r) if r else None}")
    elif sys.argv[1] == "grade": v = grade(json.load(open("recheck/proposals.json"))["results"]); S.log(f"RC graded: {len(v)}")
    S.log(f"RECHECK {sys.argv[1]} end spend=${S.spend():.3f}")
