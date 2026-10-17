"""Smart hard-trigger relabel + near-miss pair batch (SYNTHETIC). Resumable: each step skips if its raw output parsed OK.
Spend = sum of usage.cost in raw/*.json. Per-call timeout 600 s. Stops if spend would exceed $2 (target ~$1). Never prints the key."""
import os, json, os, re, sys, glob, time, copy, threading
from orcall import chat, parse_json
P = "../../casegen/prompts_v2/"
POLICY = open(P + "SMART_TRIGGERS.md").read(); GEN = open(P + "GEN_LLM2_v2.2.md").read(); GRADER = open(P + "GRADER_LLM3_v1.2.md").read()
GEN3 = open(P + "GEN_LLM2_v2.3.md").read(); GRADER3 = open(P + "GRADER_LLM3_v1.3.md").read()   # VS layers (steering 14:56)
HAIKU, GRADERM = "anthropic/claude-haiku-5.5", "google/gemini-4-argon"
HARD_CAP = 2.0
STEP_LIMIT = float(os.environ.get('STEP_LIMIT', '0') or 0)   # absolute spend limit for one step (chest-pain step: start + $0.50)
LOCK = threading.Lock()
def log(m):
    with LOCK:
        line = time.strftime("%H:%M:%S") + " " + m; print(line, flush=True); open("run.log", "a").write(line + "\n")
def spend():
    return sum((json.load(open(f)).get("usage") or {}).get("cost_usd") or 0 for f in glob.glob("raw/*.json"))
def call(tag, model, system, user, max_tokens, temp, extra=None, need=None):
    """need(obj)->bool. Up to 3 tries. Saves raw/tag.tryN.json. Returns obj or None."""
    ok = f"raw/{tag}.ok.json"
    if os.path.exists(ok): return json.load(open(ok))
    for t in range(1, 4):
        s = spend()
        if s > HARD_CAP - 0.25: log(f"BUDGET STOP before {tag}: spend ${s:.3f}"); sys.exit(3)
        if STEP_LIMIT and s > STEP_LIMIT - 0.12: log(f"STEP BUDGET STOP before {tag}: spend ${s:.3f} limit ${STEP_LIMIT:.3f}"); sys.exit(4)
        r = chat(model, system, user, max_tokens=max_tokens, temperature=temp, extra=extra, timeout=600)
        obj, how = parse_json(r["content"])
        json.dump({**r, "parse": how, "tag": tag}, open(f"raw/{tag}.try{t}.json", "w"), indent=1)
        good = r["error"] is None and r["finish_reason"] == "stop" and obj is not None and (need is None or need(obj))
        log(f"CALL {tag} try{t} {model} err={r['error']} finish={r['finish_reason']} parse={how} good={good} lat={r['latency_s']}s cost={r['usage']['cost_usd']} spend=${spend():.3f}")
        if good: json.dump(obj, open(ok, "w"), indent=1); return obj
    log(f"FAILED {tag} after 3 tries"); return None
STRIP = {"src", "grade", "src_model", "src_batch", "src_module", "src_prompt", "src_grader", "src_library"}
def clean(c): return {k: v for k, v in c.items() if k not in STRIP}
def short(df, cat):
    t = re.sub(r"\([^)]*\)", "", df or ""); t = re.sub(r"\s+", " ", t).strip(" .")
    return f"[{cat}] " + " ".join(t.split()[:16])
A = json.load(open("../accepted_cases.json"))["cases"]
H = [c for c in A if c.get("hard_trigger")]
RELABEL_SYS = POLICY + """

---
## Your task: relabel existing synthetic cases under this policy
You receive synthetic cases that were labelled under the OLD policy, where every hard trigger was escalate_human with empty alternates. Do NOT change any case facts. For each case, apply the four checks to the facts as written and return the new labels.
- `hard_trigger_rule` uses the v2.2 ids. HT_CHEST_PAIN_CHANGE becomes HT_CHEST_PAIN_ECG if the facts show an ECG change, else HT_CHEST_PAIN_VITALS.
- If, on the facts, no rule actually fires, set hard_trigger false, all trigger fields null, and choose the route.
- Choose SUPPRESSED only if the case data clearly shows the failed check; a suppressed real trigger is a critical miss.
- `rationale_addendum`: 1-2 sentences, ≤300 characters, naming which checks passed or failed and why the tier and route follow. No banned leak words are needed here because this is an answer field.
Return ONE JSON object only, with no prose or fences:
{"relabels":[{"case_id":"...","hard_trigger":true,"hard_trigger_rule":"HT_...","trigger_tier":"ABSOLUTE|CONFIRM_FIRST|SUPPRESSED|null","confirm_step":null,"confirm_timeout_min":null,"suppression_reason":null,
 "expected_route":"...","acceptable_alternates":[],"checks":{"reliable_reading":"pass|fail|n/a","own_baseline_change":"pass|fail|n/a","unexplained":"pass|fail|n/a","within_goals":"pass|fail|n/a"},
 "rationale_addendum":"...","label_note":"what changed vs the old label, ≤200 chars"}]}
Include every case_id exactly once, in input order."""
def relabel():
    out = {}
    halves = [H[:17], H[17:]]
    def one(k, cs):
        ids = [c["case_id"] for c in cs]
        u = json.dumps({"cases": [clean(c) for c in cs]})
        o = call(f"relabel_{k}", HAIKU, RELABEL_SYS, u, 64000, 0.2, {"reasoning": {"effort": "medium"}},
                 need=lambda o: isinstance(o, dict) and [x.get("case_id") for x in o.get("relabels", [])] == ids)
        if o:
            for x in o["relabels"]: out[x["case_id"]] = x
    ts = [threading.Thread(target=one, args=(k + 1, cs)) for k, cs in enumerate(halves)]
    [t.start() for t in ts]; [t.join() for t in ts]
    rel = []
    for c in H:
        x = out.get(c["case_id"])
        if not x: continue
        n = copy.deepcopy(c); n["prev_labels"] = {k: c.get(k) for k in ("expected_route", "acceptable_alternates", "hard_trigger", "hard_trigger_rule")}
        n["prev_grade"] = n.pop("grade", None)
        for k in ("hard_trigger", "hard_trigger_rule", "trigger_tier", "confirm_step", "confirm_timeout_min", "suppression_reason", "expected_route", "acceptable_alternates"):
            n[k] = x.get(k)
        if not n["hard_trigger"]:
            for k in ("hard_trigger_rule", "trigger_tier", "confirm_step", "confirm_timeout_min", "suppression_reason"): n[k] = None
        n["rationale"] = (c.get("rationale") or "").rstrip() + " Smart-trigger review: " + (x.get("rationale_addendum") or "").strip()
        n["relabel"] = {"model": HAIKU, "checks": x.get("checks"), "label_note": x.get("label_note"), "policy": "SMART_TRIGGERS v1"}
        rel.append(n)
    json.dump({"cases": rel}, open("raw/relabel_batch.json", "w"), indent=1)
    return rel
def grade(tag, cases, requested, dnr, system=None):
    ids = [c["case_id"] for c in cases]
    u = json.dumps({"batch_id": tag, "requested": requested, "do_not_repeat": dnr, "batch": {"cases": [clean({k: v for k, v in c.items() if k not in ("prev_labels", "prev_grade", "relabel")}) for c in cases], "tally": None}})
    return call(f"grade_{tag}", GRADERM, system or GRADER, u, 60000, 0.2, need=lambda o: isinstance(o, dict) and len(o.get("verdicts", [])) >= len(ids) - 1)
PAIRS = {
 "ST1": "5 near-miss pairs (10 cases). In each pair the SAME trigger rule fires. One member is real (tier ABSOLUTE or CONFIRM_FIRST, escalate_human); the other differs in EXACTLY ONE fact that makes it SUPPRESSED. Pairs:\n(a) HT_SPO2_LT88 real (reliable on-skin repeat, change from own baseline) vs unreliable_reading (poor-contact/motion flag with the fingertip recheck normal)\n(b) HT_SPO2_LT88 in a COPD patient: a real drop below the usual 88-90% vs at_patient_baseline (87% at rest, matching their own 30-day pattern)\n(c) HT_GAP48_HIGHRISK unexplained (travel claim, no contact) vs explained (caregiver check-in with a stated time inside the gap)\n(d) HT_FALL_ANTICOAG confirmed by caregiver (CONFIRM_FIRST already_confirmed) vs explained (dropped watch on the bathroom floor, patient fine on the caregiver's timed check)\n(e) HT_CHEST_PAIN_ECG real (chest pressure + watch ECG change) vs chest-pain-free watch ECG change with a poor-contact flag and a normal repeat strip (unreliable_reading)",
 "ST2": "5 near-miss pairs (10 cases). In each pair the SAME trigger rule fires. One member keeps a real tier (escalate_human); the other differs in EXACTLY ONE fact that makes it SUPPRESSED. Pairs:\n(a) HT_SYNCOPE ABSOLUTE vs the same event in a hospice comfort-only patient (goals_of_care → nurse_task, hospice nurse)\n(b) HT_FOCAL_NEURO new deficit vs at_patient_baseline (the same residual deficit documented after an old stroke, unchanged)\n(c) HT_GAP48_HIGHRISK on insulin, unexplained vs explained by a docked-charger log plus a timed video call\n(d) HT_SPO2_LT88 CONFIRM_FIRST pending (wearable 86% on-skin, no fingertip yet; confirm_step fingertip_recheck 15) vs unreliable_reading (cold-fingers/poor-contact flag, caregiver fingertip 95% at a stated time)\n(e) HT_FALL_ANTICOAG on a DOAC, pending (fall event, no answer yet; confirm_step caregiver_ping) vs goals_of_care (hospice comfort-only plan; hospice nurse)",
}
PAIRS["ST3"] = ("5 near-miss pairs (10 cases) on the three-layer VS rule. Each pair differs in EXACTLY ONE fact and the routes differ:\n"
"(a) learning period: COPD patient, rest SpO2 87% on a reliable ring reading, baseline_status phase learning (monitoring day 4 of 10, no clinician-set baseline) -> CONFIRM_FIRST fingertip_recheck, escalate_human, baseline_layer learning_period; vs the same reading on monitoring day 46 with the learned own baseline 86-90% -> SUPPRESSED at_patient_baseline, silent_log\n"
"(b) hard limits: watch HR 280 bpm with a motion burst while walking (HT_VS_IMPLAUSIBLE, ARTIFACT, device_recheck 10, silent_log, baseline_layer hard_limit_artifact) vs HR 184 bpm at rest, reliable, with dizziness (HT_VS_DANGER, ABSOLUTE, escalate_human, baseline_layer hard_limit_danger)\n"
"(c) condition-change reset: rest HR 58-61 for 3 days after metoprolol was started on Day -4 (baseline_status relearning, last_condition_change rate_control_med Day -4) -> silent_log, baseline_layer baseline_reset; vs the same HR drop from a baseline of about 78 with NO medication change -> wake_specialist (or escalate_human if another sign is present)\n"
"(d) drift guard: rest HR creeping up steadily day by day over 16 days (about 70 to 80) plus nightly RR up by 3, no condition change -> wake_specialist, subtle_deterioration true, baseline_layer drift_not_absorbed; vs the same 16-day window where HR goes up and down within 68-74 with no trend -> silent_log\n"
"(e) hard limits, rate: SpO2 drops 97% to 79% within 4 seconds while the watch shows motion and recovers in the next sample (HT_VS_IMPLAUSIBLE, ARTIFACT, fingertip_recheck 15, silent_log) vs SpO2 falling 96% to 85% over 25 minutes at rest with RR rising (HT_SPO2_LT88, CONFIRM_FIRST fingertip_recheck 15, escalate_human)\n"
"Every case fills baseline_status. Write device values as data with no interpretation words.")

PAIRS["ST4"] = ("4 near-miss pairs (8 cases) on the BANDED chest-pain rule HT_CHEST_PAIN_VITALS (see the chest-pain band table and modifiers in your instructions). Every case has chest discomfort or pressure. Each pair differs in EXACTLY ONE fact and the routes differ. Fill chest_pain_eval on every case:\n"
 "(a) asleep at 03:10, watch HR 50 (usual sleeping HR 54-58) on bisoprolol 5 mg, woken by mild central chest discomfort, BP 118/72, no red flags -> band C raw, sleep -1 and rate-control -1 -> D: SUPPRESSED below_band_threshold, nurse_task; vs the SAME but with sweating and breathlessness (2 red flags) -> band B: CONFIRM_FIRST patient_call 5, escalate_human\n"
 "(b) mild chest tightness during a brisk walk, watch HR 104 measured 8 min after stopping and falling, BP 132/80, no rate-control drug, no red flags -> raw C, post-exertion -1 -> D: SUPPRESSED below_band_threshold, nurse_task; vs the SAME HR 104 and symptom but at rest in a chair with no recent exertion -> band C: CONFIRM_FIRST patient_call 15, escalate_human\n"
 "(c) chest pressure at rest, cuff SBP 85 (usual 125-135), HR 78, reliable cuff -> band A: ABSOLUTE, escalate_human, no alternates; vs the SAME with cuff SBP 112 -> band D: SUPPRESSED below_band_threshold, nurse_task\n"
 "(d) chest discomfort at rest, watch HR 135 with a poor-contact quality flag (loose strap), BP 128/78 -> unreliable vital: CONFIRM_FIRST confirm_step device_recheck+patient_call, confirm_timeout_min 5, escalate_human; vs the SAME symptom where the clean repeat reading after re-seating the strap is HR 82 and BP 128/78 -> band D: SUPPRESSED below_band_threshold, nurse_task\n"
 "Use trigger_tier SUPPRESSED + suppression_reason below_band_threshold for band D (never silent_log, never escalate_human). Vary sex, age, Fitzpatrick (at least 3 of 8 V-VI) and devices. Make them hard.")
PAIR_EXPECT = {"ST4": "engine-checked: a D/B, b D/C(15), c A/D, d recheck(5)/D"}
def gen_pairs(bid, dnr, system=None, n=10):
    np_ = n // 2
    text = PAIRS[bid] + f"\nPair members share pair_id and adjacent IDs; everything else is identical (pmh, meds, devices, baseline, and the same trend wording apart from that fact). Routes of the members differ. Non-escalate members use silent_log, nurse_task or wake_specialist, and are never silent_log for goals_of_care.\nAt least {round(n*0.4)} of {n} patients are Fitzpatrick V-VI; {np_} of {n} are male. difficulty: hard or adversarial for all {n}. Every rationale states which of the four checks passed or failed and contains 'Naive-model trap:'.\ntally.minimums: pairs {np_}."
    u = (f"N={n}\nID_START={bid}-001\nCase IDs are {bid}-001 .. {bid}-{n:03d} (exact format). pair_id values are {bid}-P01 .. {bid}-P{np_:02d}.\nDO_NOT_REPEAT (compressed: [category] decisive feature) = {json.dumps(dnr)}\n"
         f"MODULE (smart-trigger near-miss pairs):\n{text}\nFollow the system prompt. Output the {{\"cases\":[...],\"tally\":{{...}}}} object only.")
    o = call(f"gen_{bid}", HAIKU, system or GEN, u, 64000, 0.7, {"reasoning": {"effort": "medium"}}, need=lambda o: isinstance(o, dict) and len(o.get("cases", [])) == n)
    if o: json.dump({"cases": o["cases"], "tally": o.get("tally"), "meta": {"batch": bid, "model": HAIKU, "prompt": "GEN_LLM2_v2.3 rev b" if bid == "ST4" else ("GEN_LLM2_v2.3" if system else "GEN_LLM2_v2.2")}}, open(f"raw/{bid}.batch.json", "w"), indent=1)
    return o
if __name__ == "__main__":
    step = sys.argv[1]
    log(f"STEP {step} start spend=${spend():.3f}")
    if step == "relabel":
        rel = relabel(); log(f"relabelled {len(rel)}/{len(H)}")
        req = {"n": len(rel), "purpose": "relabel QA: existing accepted cases with fired triggers, relabelled under the smart hard-trigger policy. No route mix or minimums requested; novelty is not in scope (these are already accepted).", "routes": None, "hard_plus_adversarial_min_pct": 0, "minimums": {}}
        h = (len(rel) + 1) // 2; res = {}
        def g(k, cs): res[k] = grade(f"RELABEL-{k}", cs, {**req, "n": len(cs)}, [])
        ts = [threading.Thread(target=g, args=(k + 1, cs)) for k, cs in enumerate((rel[:h], rel[h:]))]
        [t.start() for t in ts]; [t.join() for t in ts]
        for k, o in res.items():
            if o: json.dump(o, open(f"raw/RELABEL-{k}.grader.json", "w"), indent=1)
    elif step == "pairs":
        dnr = [short(c.get("decisive_feature"), (c.get("category") or ["?"])[0]) for c in A]
        res = {}
        def gp(b): res[b] = gen_pairs(b, dnr)
        ts = [threading.Thread(target=gp, args=(b,)) for b in ("ST1", "ST2")]; [t.start() for t in ts]; [t.join() for t in ts]
        def gg(b):
            if res.get(b):
                cs = json.load(open(f"raw/{b}.batch.json"))["cases"]
                o = grade(b, cs, {"n": 10, "routes": "5 escalate_human + 5 non-escalate (one per pair)", "hard_plus_adversarial_min_pct": 100, "minimums": {"pairs": 5}}, dnr)
                if o: json.dump(o, open(f"raw/{b}.grader.json", "w"), indent=1)
        ts = [threading.Thread(target=gg, args=(b,)) for b in ("ST1", "ST2")]; [t.start() for t in ts]; [t.join() for t in ts]
    elif step == "pairs3":
        dnr = [short(c.get("decisive_feature"), (c.get("category") or ["?"])[0]) for c in A]
        if gen_pairs("ST3", dnr, GEN3):
            cs = json.load(open("raw/ST3.batch.json"))["cases"]
            o = grade("ST3", cs, {"n": 10, "routes": "one escalating/non-silent and one other member per pair", "hard_plus_adversarial_min_pct": 100, "minimums": {"pairs": 5}}, dnr, GRADER3)
            if o: json.dump(o, open("raw/ST3.grader.json", "w"), indent=1)
    elif step == "pairs4":
        dnr = [short(c.get("decisive_feature"), (c.get("category") or ["?"])[0]) for c in A]
        if not os.path.exists("raw/ST4.batch.json"): gen_pairs("ST4", dnr, GEN3, n=8)
        if os.path.exists("raw/ST4.batch.json") and not os.path.exists("raw/ST4.grader.json"):
            cs = json.load(open("raw/ST4.batch.json"))["cases"]
            o = grade("ST4", cs, {"n": len(cs), "routes": "one escalating/non-silent and one other member per pair", "hard_plus_adversarial_min_pct": 100, "minimums": {"pairs": 4}}, dnr, GRADER3)
            if o: json.dump(o, open("raw/ST4.grader.json", "w"), indent=1)
    elif step == "cprl":   # blind v1.3 regrade of the 4 chest-pain vitals-only relabels after the banded-rule update
        if not os.path.exists("raw/CPRL.grader.json"):
            R = {c["case_id"]: c for c in json.load(open("relabeled_cases.json"))["cases"]}
            cs = [R[i] for i in ("HK5-002", "AC1-003", "AC1-005", "AC2-001")]
            o = grade("CPRL", cs, {"n": 4, "purpose": "relabel QA of already accepted chest-pain cases under the banded chest-pain rule. No route mix or minimums; novelty not in scope.", "routes": None, "hard_plus_adversarial_min_pct": 0, "minimums": {}}, [], GRADER3)
            if o: json.dump(o, open("raw/CPRL.grader.json", "w"), indent=1)
    elif step == "cprl2":   # blind v1.3 rev c regrade after Wayne's crescendo decision
        if not os.path.exists("raw/CPRL2.grader.json"):
            L = {c["case_id"]: c for c in json.load(open("library_v2_smart_accepted.json"))["cases"]}
            cs = [L[i] for i in ("AC1-002", "AC1-012", "AC2-005")]
            o = grade("CPRL2", cs, {"n": 3, "purpose": "relabel QA of chest-pain cases after the decided crescendo rule (AC1-002/AC1-012 are a near-miss pair). No route mix or minimums; novelty not in scope.", "routes": None, "hard_plus_adversarial_min_pct": 0, "minimums": {}}, [], GRADER3)
            if o: json.dump(o, open("raw/CPRL2.grader.json", "w"), indent=1)
    log(f"STEP {step} end spend=${spend():.3f}")
