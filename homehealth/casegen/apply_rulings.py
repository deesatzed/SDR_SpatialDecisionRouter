"""Apply Wayne's clinician rulings (clinician_rulings.csv, 13 review-queue cases, 2026-10-17/18) to library_v2_smart_accepted.json.
Run by build_outputs.py LAST (after apply_chest_pain.py and apply_recheck.py). Idempotent: the library is rebuilt from base on every build.
- The 6 ST pair cases were in the review queue (not accepted); a ruling resolves them, so they are added to the library with the ruled labels.
- Every ruled case gets clinician_ruling {ruled_by, date, ruling, note, changes, engine_check}. Engine checks re-derive the tier with
  trigger_eval.py (params 0.5-placeholder) and must agree with the ruled labels (assert).
- Resolved rows are removed from review_queue.csv. Synthetic data only; no API calls."""
import json, csv, glob, copy, subprocess, sys
sys.path.insert(0, "../../casegen/trigger_engine"); import trigger_eval as T
sys.path.insert(0, "../../casegen/prompts_v2"); import grade_merge as G
P = T.load_params("../../casegen/trigger_engine/trigger_params.json")
DAY = T.DAY

# ---- rulings file (the GC2-003 note contains an unquoted comma -> rejoin overflow columns)
RUL = {}
with open("clinician_rulings.csv", newline="") as f:
    rd = csv.reader(f); hdr = next(rd)
    for row in rd:
        if not row: continue
        RUL[row[0]] = {"ruling": row[1], "note": ",".join(row[2:]).strip()}
assert len(RUL) == 13, len(RUL)

lib = json.load(open("library_v2_smart_accepted.json")); L = {c["case_id"]: c for c in lib["cases"]}
B, V = {}, {}
for f in sorted(glob.glob("raw/ST*.batch.json")):
    for c in json.load(open(f))["cases"]: B[c["case_id"]] = c
for f in sorted(glob.glob("raw/ST*.grader.json")):
    for v in json.load(open(f))["verdicts"]: V[v["case_id"]] = v

# ---- engine checks (deterministic re-derivation of the ruled tiers)
def chest(inp, **ctx): return T.evaluate_chest_pain({"ts": 0.0, **inp}, P, context=ctx)
def established_hr(level):
    b = T.Baseline("SYN-HK7-009", 0.0, P); t = 0.0
    while t < 20 * DAY:
        b.add_sample({"vital": "hr", "value": level + ((int(t / 1800) % 5) - 2) * 0.8, "ts": t, "activity_state": "rest"}); t += 1800
    return b
EC = {}
EC["ST4-002"] = chest({"activity_state": "sleep", "vitals": {"hr": {"value": 50}, "sbp": {"value": 118}}, "symptoms": {"chest_pain": True, "red_flags": ["diaphoresis", "dyspnea"], "concordant": None}}, rate_control_med=True)
EC["ST1-010"] = chest({"activity_state": "active", "minutes_since_exertion": 5, "vitals": {"hr": {"value": 102}, "sbp": {"value": 156}},
                       "symptoms": {"chest_pain": True, "red_flags": ["diaphoresis", "persistent_ge_15min"], "concordant": True, "ecg_change": True, "ecg_reliable": False}}, rate_control_med=True)
EC["HK5-001"] = chest({"activity_state": "active", "minutes_since_exertion": 0, "vitals": {"hr": {"value": 88}, "sbp": {"value": 130}}, "symptoms": {"chest_pain": True, "red_flags": [], "concordant": None, "ecg_change": False}})
EC["ST2-009"] = T.resolve_confirm({"tier": "CONFIRM_FIRST", "rule": "HT_FALL_ANTICOAG", "route": "escalate_human", "page": "if_confirmed_or_timeout", "confirm_step": "watch_prompt", "timeout_min": 10},
                                  "no_answer", P, {"lives_alone": True})
b = established_hr(72.0)
EC["HK7-009"] = T.evaluate({"vital": "hr", "value": 112, "ts": 20 * DAY + 2.9 * 3600, "activity_state": "rest"}, b, P, {})
EC["NV2-015"] = T.evaluate({"vital": "glucose", "value": 50, "ts": 99 * DAY, "source": "cgm", "cgm": {"overnight": True, "fingerstick": {"value": 58, "minutes_apart": 30}, "symptoms": True}}, T.Baseline("SYN-NV2-015", 0.0, P), P, {})
EC["GL1-005"] = T.evaluate({"vital": "glucose", "value": 47, "ts": 99 * DAY, "source": "cgm", "cgm": {"overnight": True, "fingerstick": {"value": 44, "minutes_apart": 10}, "symptoms": False}}, T.Baseline("SYN-GL1-005", 0.0, P), P, {})
bg = T.Baseline("SYN-GC2-003", 0.0, P)
EC["GC2-003_0210"] = T.evaluate({"vital": "glucose", "value": 46, "ts": 99 * DAY + 2 * 3600 + 600, "source": "cgm", "cgm": {"overnight": True}}, bg, P, {"goals": "comfort_only"})
EC["GC2-003"] = T.evaluate({"vital": "glucose", "value": 49, "ts": 99 * DAY + 3 * 3600 + 300, "source": "cgm", "cgm": {"overnight": True, "symptoms": True}}, bg, P, {"goals": "comfort_only"})
def slim(d): return {k: d.get(k) for k in ("rule", "tier", "band", "raw_band", "modifiers", "reason", "route", "page", "confirm_step", "timeout_min", "recheck", "escalation_target", "notify", "goals_basis", "confirm_result", "z") if d.get(k) is not None}
assert EC["ST4-002"]["tier"] == "CONFIRM_FIRST" and EC["ST4-002"]["band"] == "C" and EC["ST4-002"]["timeout_min"] == 15
assert EC["ST1-010"]["tier"] == "ABSOLUTE" and EC["ST1-010"]["rule"] == "HT_CHEST_PAIN_VITALS"
assert EC["HK5-001"]["tier"] == "LOG_ONLY" and EC["HK5-001"]["band"] == "D"
assert EC["ST2-009"]["confirm_step"] == "already_confirmed" and EC["ST2-009"]["page"] is True
assert EC["HK7-009"]["tier"] == "CONFIRM_FIRST" and EC["HK7-009"]["rule"] == "HT_VS_BASELINE"
assert EC["NV2-015"]["tier"] == "ABSOLUTE" and EC["NV2-015"]["reason"] == "hard_limit_danger_symptomatic"
assert EC["GL1-005"]["tier"] == "ABSOLUTE" and EC["GL1-005"]["reason"] == "hard_limit_danger_fingerstick_confirmed"
assert EC["GC2-003_0210"]["tier"] == "SUPPRESSED" and EC["GC2-003"]["tier"] == "ABSOLUTE" and EC["GC2-003"]["escalation_target"] == "hospice_nurse"
TMO_DEV = P["confirm_first"]["timeouts_min"]["device_recheck"]
def cpe(d): return {"band": d["band"], "raw_band": d["raw_band"], "modifiers": d["modifiers"], "tier": d["tier"], "timeout_min": d.get("timeout_min"), "engine": "trigger_eval.evaluate_chest_pain params " + P["version"] + " (net-then-clamp)"}

NO = dict(confirm_step=None, confirm_timeout_min=None, suppression_reason=None)
SPEC = {
 "ST1-002": dict(labels={}, rationale=None),
 "ST1-004": dict(labels=dict(expected_route="escalate_human", acceptable_alternates=[], route_basis="clinical_presentation"),
   rationale="Check 1 (reliable reading) passes: fingertip repeats at 09:40 and 09:43 both read 87% with good waveforms. Check 2 (change from own baseline) fails: her own fingertip rest readings over 30 days sit at 86-88%, so the saturation rule is SUPPRESSED with at_patient_baseline. The route does not come from the saturation rule: since this morning she is breathless walking to the kitchen and speaking in short sentences, with resting HR 96 bpm (from 76-80) and RR 26/min, which is an acute decompensation in its own right, so a clinician needs to see her now and the route is escalate_human with no alternate (route_basis clinical_presentation). Naive-model trap: a shallow model correctly suppresses the 87% reading as her usual range and stops there with a same-day review, missing that her breathing effort, heart rate and respiratory rate have changed acutely."),
 "ST1-008": dict(labels=dict(expected_route="silent_log", acceptable_alternates=["nurse_task"]),
   rationale="Check 1 passes as a device state: the watch logged an impact at 06:55 and then an off-wrist flag. Check 3 (no explanation) fails: the spouse heard the watch clatter on the kitchen tiles at about 06:55, and at a timed check at 07:00 she was standing at the sink, walking and pain-free, so the impact was the dropped watch, not a fall, and HT_FALL_ANTICOAG is SUPPRESSED with explained. Check 4 (goals of care) passes. With no fall and no clinical change the event is logged (silent_log); a nurse call about watch fit is an acceptable alternate. Naive-model trap: a shallow model reads a watch impact on apixaban as a fall and sends it to a human, which the spouse's timed check at 07:00 contradicts."),
 "ST1-010": dict(labels=dict(expected_route="escalate_human", acceptable_alternates=[], hard_trigger_rule="HT_CHEST_PAIN_VITALS", trigger_tier="ABSOLUTE", **NO,
                             secondary_triggers=[{"hard_trigger_rule": "HT_CHEST_PAIN_ECG", "trigger_tier": "SUPPRESSED", "suppression_reason": "unreliable_reading",
                                                  "evidence": "06:41 strip poor-contact flag; clean repeat strip 06:47 shows no ST change"}],
                             pair_id=None, pair_complete_in_accepted=None),
   chest="ST1-010",
   pair_note="Unpaired 2026-10-18 (Wayne): kept as a standalone trap case; its former partner ST1-009 also routes escalate_human, so the pair no longer contrasts.",
   decisive_feature="Clean repeat single-lead strip with no ST change, but central chest pressure for about 15 minutes with ongoing sweating and HR 102 bpm on bisoprolol, so the vital-sign chest-pain rule still fires.",
   rationale="Check 1 (reliable reading) fails for the ECG only: the 06:41 strip carries a poor-contact flag and the clean repeat strip at 06:47 shows no ST change, so HT_CHEST_PAIN_ECG is SUPPRESSED with unreliable_reading. A single-lead watch strip cannot rule out an acute coronary syndrome, so the chest-pain vital rule still applies: central chest pressure on the stairs for about 15 minutes with sweating that continues, and watch HR 102 bpm despite bisoprolol (raw band C; post-exertion -1, tachycardia on rate control +1), plus two red flags (sweating, duration of 15 minutes or more, +2) net to band A, so HT_CHEST_PAIN_VITALS is ABSOLUTE and the route is escalate_human with no alternate. BP 156/94 is above her 128/78 baseline but below the BP bands. Checks 3 and 4 pass (no timed contact; full treatment goals). This is a standalone case, not part of a pair. Naive-model trap: a shallow model takes the clean repeat strip as reassurance and routes a same-day review, but a normal single-lead trace does not exclude ACS while symptoms continue."),
 "ST2-009": dict(labels=dict(expected_route="escalate_human", acceptable_alternates=[], trigger_tier="CONFIRM_FIRST", confirm_step="already_confirmed", confirm_timeout_min=None, suppression_reason=None),
   decisive_feature="Watch impact on-wrist at 22:10 on edoxaban with HR 118 bpm, in a woman living alone who did not answer the tap-to-confirm prompt, which counts as a failed confirm.",
   rationale="Check 1 passes: the impact was logged while the watch was on-wrist, with HR 118 bpm and no poor-contact flag. Check 2 passes: HR rose from her 66-70 bpm range and steps stayed at zero for 30 minutes after the impact. Check 3 passes: no timed contact or watch removal explains the event. Check 4 passes: no goals of care are documented. Edoxaban is current, so HT_FALL_ANTICOAG applies. She lives alone and did not answer the watch tap-to-confirm prompt by 22:15; under the policy an unanswered patient prompt in a person living alone counts as a failed confirm, so the tier is CONFIRM_FIRST with confirm_step already_confirmed and the route is escalate_human now, with no alternate. Naive-model trap: a shallow model reads the unanswered prompt as a possible false alarm and logs it, or waits for a caregiver ping that no one is there to answer."),
 "ST4-002": dict(labels=dict(expected_route="escalate_human", trigger_tier="CONFIRM_FIRST", confirm_step="patient_call", confirm_timeout_min=15, suppression_reason=None), chest="ST4-002",
   decisive_feature="Sweating and breathlessness added to the same 03:10 sleeping episode offset the sleep and rate-control modifiers, so the band stays C with a 15-minute patient call.",
   rationale="Checks: the watch and cuff are reliable with no poor-contact flag (check 1 passes), and HR 50 is below his usual sleeping 54-58, a real change from his own baseline (check 2 passes). No timed contact explains the episode (check 3 passes), and full treatment goals pass (check 4). Raw band C (HR 50) with sleep -1, rate control -1 and two red flags (sweating, breathlessness) +2 nets to 0, so the band stays C and HT_CHEST_PAIN_VITALS is CONFIRM_FIRST with a 15-minute patient call before a clinician looks. Naive-model trap: a shallow model reads HR 50 with BP 118/72 as mild and sends a nurse task, but the sweating and breathlessness keep the banded score above threshold."),
 "HK5-001": dict(labels=dict(expected_route="nurse_task", acceptable_alternates=["wake_specialist"], hard_trigger=True, hard_trigger_rule="HT_CHEST_PAIN_VITALS", trigger_tier="SUPPRESSED",
                             confirm_step=None, confirm_timeout_min=None, suppression_reason="below_band_threshold"), chest="HK5-001",
   rationale="Exertional chest tightness in a patient with known stable angina, the same tight feeling as before, eased within about 10 minutes of sitting. The watch peak HR was 88 bpm, seated BP stayed at 130/78 (her 30-day baseline) and the single-lead ECG showed sinus rhythm with no ST change, so every vital is in band D and there are no red flags: HT_CHEST_PAIN_VITALS fires but is SUPPRESSED with below_band_threshold, and the route is nurse_task (a call to review her angina pattern and medication), with wake_specialist as the alternate. Naive-model trap: a shallow model that sees chest tightness goes straight to escalate_human, but a typical, stable episode with unchanged vitals and frequency is band D."),
 "HK6-001": dict(labels=dict(expected_route="escalate_human", acceptable_alternates=[], hard_trigger=True, hard_trigger_rule="HT_FALL_ANTICOAG", trigger_tier="CONFIRM_FIRST",
                             confirm_step="already_confirmed", confirm_timeout_min=None, suppression_reason=None),
   rationale="The watch logged an impact at 03:10 while it was on the wrist, followed by HR 124 bpm from 03:12 to 03:20 and no steps for 40 minutes, in a woman taking edoxaban with CKD 3b and a prior hip fracture who lives alone. She did not answer calls from 03:10 to 04:10, and at 04:10 she told a neighbour she got up on her own, which confirms she went down: HT_FALL_ANTICOAG fires and passes all four checks, and the fall is already confirmed (confirm_step already_confirmed), so the route is escalate_human now with no alternate. A head injury or bleed on a DOAC can be silent, and HR was still 96 bpm at 04:05 against her 68-72 bpm range. Naive-model trap: a shallow model treats the 'I'm fine' reply as reassurance and logs it, when the same reply confirms a fall on an anticoagulant."),
 "HK6-002": dict(labels=dict(expected_route="wake_specialist", acceptable_alternates=["nurse_task"], hard_trigger=True, hard_trigger_rule="HT_FALL_ANTICOAG", trigger_tier="SUPPRESSED",
                             confirm_step=None, confirm_timeout_min=None, suppression_reason="unreliable_reading"),
   rationale="The impact event was logged at 03:10 while the watch sat off-wrist on the bedside charger, with no HR recorded from 02:55 to 04:30, so the impact reading is unreliable and HT_FALL_ANTICOAG is SUPPRESSED with unreliable_reading. She did not answer calls from 03:10 to 04:10, and her 04:10 reply to a neighbour that she got up on her own is not an observed account and, without on-wrist data, does not establish a fall. Because she takes edoxaban and lives alone, a possible unwitnessed fall still needs a same-day device check and clinician phone review (wake_specialist), with nurse_task as the alternate. Naive-model trap: a shallow model sees 'impact' plus 'anticoagulant' and treats it as a confirmed fall for a human now, even though the watch was not on the body."),
 "HK7-009": dict(labels=dict(expected_route="nurse_task", acceptable_alternates=["wake_specialist"], hard_trigger=True, hard_trigger_rule="HT_FALL_ANTICOAG", trigger_tier="SUPPRESSED",
                             confirm_step=None, confirm_timeout_min=None, suppression_reason="explained",
                             secondary_triggers=[{"hard_trigger_rule": "HT_VS_BASELINE", "trigger_tier": "CONFIRM_FIRST", "confirm_step": "device_recheck", "confirm_timeout_min": TMO_DEV,
                                                  "if_confirmed_route": "escalate_human", "if_refuted_route": "nurse_task", "purpose": "HR recheck for possible AF with rapid ventricular rate",
                                                  "evidence": "HR 124 at 02:40, 118 at 02:44, 112 at 02:55 vs 30-day resting baseline 72 (7-day 70-74); atrial fibrillation, no rate-control drug"}]),
   decisive_feature="The spouse saw her catch the door frame and stay on her feet, so the impact was a near-fall, but HR was still 112 bpm at 02:55 against her 72 bpm baseline with atrial fibrillation.",
   rationale="The watch impact at 02:39, the bed exit at 02:38 and HR 124 bpm mirror the floor-fall case, but the spouse saw her catch the bathroom door frame and stay on her feet, so there was no fall: HT_FALL_ANTICOAG is SUPPRESSED with explained, and the near-fall itself needs a next-day nurse call about balance, dizziness and bleeding signs on dabigatran (nurse_task, wake_specialist as alternate). Separately, HR was still 112 bpm at 02:55 against her 72 bpm baseline, in a woman with atrial fibrillation on no rate-control drug, which could be AF with a rapid ventricular rate: a second trigger (HT_VS_BASELINE, CONFIRM_FIRST) asks for an HR recheck and escalates to a human if the rate stays high. Naive-model trap: a shallow model escalates the near-fall because any impact on dabigatran looks like a hard trigger, or logs it because she feels fine, missing the persistent fast heart rate."),
 "NV2-015": dict(labels=dict(expected_route="escalate_human", acceptable_alternates=[], hard_trigger=True, hard_trigger_rule="HT_VS_DANGER", trigger_tier="ABSOLUTE", **NO),
   rationale="The daylight-saving transition offers a plausible explanation for her grogginess, but the objective data show a real problem: bedtime insulin glargine was increased to 20 units on Day -6, followed by nocturnal CGM readings of 50-62 mg/dL (at or below the 54 mg/dL danger limit), a fingerstick of 58 mg/dL at 05:00, and the caregiver finding her confused and sweaty at 05:30. Hypoglycaemia symptoms are checked before a fingerstick that reads just above the limit, so this is symptomatic hypoglycaemia: HT_VS_DANGER is ABSOLUTE and the route is escalate_human with no alternate. Naive-model trap: attributing the confusion and low glucose to the time change, or reading the 58 mg/dL fingerstick as refuting the CGM low, and missing the insulin-dose-related nocturnal hypoglycaemia."),
 "GC2-003": dict(labels=dict(expected_route="escalate_human", acceptable_alternates=[], hard_trigger=True, hard_trigger_rule="HT_VS_DANGER", trigger_tier="ABSOLUTE", **NO, escalation_target="hospice_nurse"),
   decisive_feature="Recurrent nocturnal CGM low (46, then 49 mg/dL after gel) with drowsiness on glargine in a hospice patient: an urgent, treatable comfort problem for the hospice nurse now.",
   rationale="Recurrent nocturnal hypoglycaemia on basal insulin after a glargine cut from 18 to 14 units on Day -3: CGM 46 mg/dL at 02:10, then 49 mg/dL at 03:05 after glucose gel, with drowsiness and response only to her name. HT_VS_DANGER fires and the low is symptomatic and recurrent. Her hospice plan declines hospital admission, which suppresses hospital-directed escalation only; a recurrent symptomatic low is urgent, treatable at home and consistent with her comfort goals, so it is not suppressed: the route is escalate_human to the hospice nurse now (escalation_target hospice_nurse), not a same-shift contact, with no alternate. The 71 mg/dL reading at 02:45 was a treatment response, not resolution, since it fell again within 20 minutes. Naive-model trap: a shallow model sees the 71 mg/dL recovery and the comfort goals and routes nurse_task for a routine insulin review, or sends her to a hospital team against her wishes."),
 "GL1-005": dict(labels=dict(expected_route="escalate_human", acceptable_alternates=[], hard_trigger=True, hard_trigger_rule="HT_VS_DANGER", trigger_tier="ABSOLUTE", **NO, baseline_layer="hard_limit_danger"),
   add_category="fall",
   rationale="A meter-confirmed nocturnal low (CGM 47 mg/dL at 02:45, glucometer 44 mg/dL at 02:55, at or below the 54 mg/dL danger limit) in an insulin-treated man who lives alone makes HT_VS_DANGER ABSOLUTE (hard_limit_danger). It was followed by a watch-logged impact at 03:21 with HR 108 bpm, and a neighbour found him on the bedroom floor at 03:40 after he pressed his pendant. A fall after a severe low needs clinician assessment for injury and for the cause of the low, and the 92 mg/dL reading after treatment does not close the event. Route escalate_human with no alternate. Naive-model trap: a shallow model sees a treated low that is now resolved and routes nurse_task for a glucose-education call, missing both the danger-level low and the fall."),
}
assert set(SPEC) == set(RUL)
TRACK = ["expected_route", "acceptable_alternates", "hard_trigger", "hard_trigger_rule", "trigger_tier", "confirm_step", "confirm_timeout_min", "suppression_reason",
         "baseline_layer", "category", "pair_id", "escalation_target", "route_basis", "secondary_triggers", "chest_pain_eval"]
added, report = [], {}
for cid, sp in SPEC.items():
    if cid in L: c = L[cid]
    else:
        c = copy.deepcopy(B[cid]); v = V.get(cid) or {}; bl = v.get("blind") or {}
        c.update({"src": "library_v2_smart_pairs", "grade": {"score": v.get("score"), "grader_route": bl.get("grader_route"), "grader_confidence": bl.get("confidence"), "action": v.get("action"), "batch_id": cid[:3]},
                  "src_model": "anthropic/claude-haiku-5.5", "src_batch": cid[:3], "src_module": "smart_trigger_pairs",
                  "src_prompt": "GEN_LLM2_v2.3 rev b" if cid.startswith("ST4") else "GEN_LLM2_v2.2", "src_grader": "google/gemini-4-argon GRADER_LLM3_v1.3" if cid.startswith("ST4") else "google/gemini-4-argon GRADER_LLM3_v1.2",
                  "src_library": "library_v2_smart_pairs", "pair_complete_in_accepted": False})
        added.append(cid)
    old = {k: copy.deepcopy(c.get(k)) for k in TRACK}
    for k, x in sp["labels"].items(): c[k] = copy.deepcopy(x)
    if sp.get("chest"): c["chest_pain_eval"] = cpe(EC[sp["chest"]])
    if sp.get("add_category") and sp["add_category"] not in c["category"]: c["category"] = c["category"] + [sp["add_category"]]
    if sp.get("pair_note"): c["pair_note"] = sp["pair_note"]
    if sp.get("decisive_feature"): c["decisive_feature"] = sp["decisive_feature"]
    rat_changed = bool(sp.get("rationale")) and sp["rationale"] != c.get("rationale")
    if sp.get("rationale"): c["rationale"] = sp["rationale"]
    for k in ("escalation_target", "route_basis", "secondary_triggers"):
        if c.get(k) is None: c.pop(k, None)
    new = {k: c.get(k) for k in TRACK}
    ch = [f"{k}: {json.dumps(old[k])} -> {json.dumps(new[k])}" for k in TRACK if old[k] != new[k] and k != "chest_pain_eval"]
    if old["chest_pain_eval"] != new["chest_pain_eval"]: ch.append(f"chest_pain_eval band: {(old['chest_pain_eval'] or {}).get('band')} -> {(new['chest_pain_eval'] or {}).get('band')}")
    if rat_changed: ch.append("rationale rewritten")
    if sp.get("decisive_feature"): ch.append("decisive_feature updated")
    if cid in added: ch.insert(0, "added to library (resolved from review queue)")
    eck = {k: slim(v) for k, v in EC.items() if k.split("_")[0] == cid}
    c["clinician_ruling"] = {"ruled_by": "Wayne", "date": RUL[cid]["note"].split("Wayne ")[-1].split(";")[0].rstrip(")") if "Wayne 20" in RUL[cid]["note"] else None,
                             "ruling_route": RUL[cid]["ruling"], "note": RUL[cid]["note"], "policy": "SMART_TRIGGERS v1.5", "changes": ch, **({"engine_check": eck} if eck else {})}
    assert c["expected_route"] == RUL[cid]["ruling"], cid
    iss = G.smart_checks(c) + (G.layer_checks(c) if "baseline_layer" in c else [])
    assert not iss, (cid, iss)
    report[cid] = ch
    if cid not in L: lib["cases"].append(c); L[cid] = c
# ST1-009 loses its pair with ST1-010 (standalone ruling)
s9 = L["ST1-009"]
if s9.get("pair_id") == "ST1-P05":
    s9["pair_id"] = None; s9["pair_complete_in_accepted"] = None
    s9["pair_note"] = "Unpaired 2026-10-18: former partner ST1-010 is now a standalone escalate_human case (Wayne ruling), so ST1-P05 no longer contrasts."
    report["ST1-009"] = ["pair_id: \"ST1-P05\" -> null (partner ST1-010 made standalone)"]
# pair completeness for ST pairs
allp = {}
for x in B.values(): allp.setdefault(x["pair_id"], []).append(x["case_id"])
for c in lib["cases"]:
    if c["case_id"] in B and c.get("pair_id"):
        c["pair_complete_in_accepted"] = all(m in L for m in allp.get(c["pair_id"], []))
lib.setdefault("provenance", {})["clinician_rulings"] = f"clinician_rulings.csv (Wayne, 2026-10-17/18): {len(SPEC)} review-queue cases ruled; {len(added)} added from the queue; applied by apply_rulings.py under SMART_TRIGGERS v1.5"
json.dump(lib, open("library_v2_smart_accepted.json", "w"), indent=1)
# review queue: drop resolved rows
q = list(csv.DictReader(open("review_queue.csv"))); keys = list(q[0].keys()) if q else ["case_id", "queue_reasons", "pass"]
left = [r for r in q if r["case_id"] not in RUL]
with open("review_queue.csv", "w", newline="") as f: w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(left)
print(subprocess.run(["python3", "../../casegen/convert_casegen.py", "--source=LIB=library_v2_smart_accepted.json:library_v2_smart:v2.2-v2.3", "--out-prefix=library_v2_smart_"], capture_output=True, text=True).stdout)
import collections
S = json.load(open("summary.json")); cs = lib["cases"]
S["library_v2_smart_n"] = len(cs); S["library_hard_trigger_n"] = sum(bool(c.get("hard_trigger")) for c in cs)
S["library_routes"] = dict(collections.Counter(c["expected_route"] for c in cs))
S["library_tiers"] = dict(collections.Counter(c.get("trigger_tier") for c in cs if c.get("trigger_tier")))
S["clinician_rulings"] = {"n": len(SPEC), "added_to_library": added, "review_queue_rows_before": len(q), "review_queue_rows_after": len(left), "changes": report, "policy": "SMART_TRIGGERS v1.5", "params": P["version"]}
json.dump(S, open("summary.json", "w"), indent=1)
json.dump({"changes": report, "engine_checks": {k: slim(v) for k, v in EC.items()}}, open("rulings_applied.json", "w"), indent=1)
print("rulings applied:", len(SPEC), "| added:", added, "| review queue", len(q), "->", len(left), "| library", len(cs), dict(collections.Counter(c["expected_route"] for c in cs)))
