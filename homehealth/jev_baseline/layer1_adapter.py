"""Deterministic Layer 1 adapter (SYNTHETIC). Derives trigger_eval inputs from a library case's STRUCTURED FACT fields only:
age_band/sex/living, pmh, meds, recent_med_changes, devices, discharge, patient_goals, baseline_30d, baseline_status (a fact field),
trend_last_7d, caregiver_or_nurse_note, data_quality (device flags, wear, gaps). It never reads label/answer fields
(expected_route, acceptable_alternates, hard_trigger*, trigger_tier, confirm_*, suppression_reason, baseline_layer, escalation_target,
route_basis, rationale, decisive_feature, category, difficulty, subtle_deterioration, chest_pain_eval, router_input, ...).
The SMART_TRIGGERS checks are applied with the engine: trigger_eval.evaluate (hard limits, artifact, CGM, learning period),
evaluate_chest_pain (banded chest pain incl. crescendo), apply_goals_of_care / urgent_comfort_basis (hospice) and resolve_confirm
(unanswered prompt, lives alone). Text patterns are generic (no case IDs). Output: one decision per case."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, "..", "trigger_engine"), "/workspace/jevfly_smoke/casegen/trigger_engine"):
    if os.path.exists(os.path.join(p, "trigger_eval.py")): sys.path.insert(0, p); break
import trigger_eval as T
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import routes as RT  # noqa: E402  (SMART_TRIGGERS v1.9 route ids; legacy ids accepted on read)
DAY = T.DAY
FACT_FIELDS = ("age_band", "sex", "living", "pmh", "meds", "recent_med_changes", "devices", "discharge", "patient_goals", "function_baseline",
               "baseline_30d", "baseline_status", "trend_last_7d", "caregiver_or_nurse_note", "data_quality", "skin_tone_note",
               "patient_bands")   # v1.11.0: patient-level bands entered as a patient rule (e.g. {"spo2": [86, 88]})
NEG = re.compile(r"(\bno\b|\bnot\b|\bwithout\b|\bdenies\b|\bdenied\b|\bnever\b|\bfree of\b|n't\b|\bnor\b|\bnone\b)[^.;:]*$", re.I)
ANTICOAG = r"apixaban|rivaroxaban|edoxaban|dabigatran|warfarin|enoxaparin|dalteparin|heparin|fondaparinux|acenocoumarol"
RATE_CONTROL = r"bisoprolol|metoprolol|atenolol|carvedilol|nebivolol|propranolol|diltiazem|verapamil|digoxin"
GLUCOSE_LOWERING = r"insulin|glargine|detemir|degludec|lispro|aspart|glipizide|gliclazide|glimepiride|glyburide|glibenclamide"
def facts_only(case): return {k: case.get(k) for k in FACT_FIELDS}
def sentences(t): return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z]|Day\b|\d)", t or "") if s.strip()]
def find(rx, text, neg=True):
    """first non-negated match of rx in text (negation = a negation word earlier in the same clause, within 40 chars)"""
    for m in re.finditer(rx, text or "", re.I):
        pre = text[max(0, m.start() - 40):m.start()]
        if neg and NEG.search(pre): continue
        return m
    return None
def split_day0(trend):
    m = re.search(r"\bDay 0\b(?!\s*(?:to|-|–)\s*Day)", trend or "")
    return (trend[:m.start()], trend[m.start():]) if m else (trend or "", "")
def hhmmss(s):
    m = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", s)
    return (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0), m.group(3) is not None) if m else (None, False)
FLAG_RX = r"poor[- ](skin )?contact|motion( flag| artifact)?|cold fingers|loose strap|loose|low perfusion|off[- ]wrist|on (the )?(bedside )?charger|charging|not worn"
def flagged(s): return find(FLAG_RX, s) is not None
def activity(s):
    if re.search(r"\b(asleep|sleeping|woke|woken|overnight|night)\b", s, re.I): return "sleep"
    if re.search(r"\b(walk(ing)?|stairs|climb(ing)?|uphill|hill|carrying|exercis\w*|garden\w*|brisk|hoover\w*|exertion)\b", s, re.I) and not re.search(r"\b(seated|sitting|at rest|in (a|the) chair|lying)\b", s, re.I): return "active"
    return "rest"
def clause_flagged(r):
    """v1.11.0: artifact flag of the clause (split on ';') that holds this SpO2 value, so a clean repeat written after a flagged reading in the
    same sentence still counts as clean (whatever the first reading's flag was)."""
    segs = [x for x in re.split(r";", r[1]) if re.search(r"(?<!\d)%s\s*%%" % r[0], x)]
    return any(flagged(x) for x in segs) if segs else r[2]
def ts_fallback(s, m):
    """v1.11.0: a reading whose time is > 40 chars before the value in the same clause, or written as '<value> at hh:mm'."""
    after = re.match(r"[^.;\d]{0,12}?\bat (\d{1,2}):(\d{2})\b", s[m.end():])
    if after: return int(after.group(1)) * 3600 + int(after.group(2)) * 60, False
    clause = re.split(r";", s[:m.start()])[-1]
    t = list(re.finditer(r"\b(\d{1,2}):(\d{2})\b", clause))
    return ((int(t[-1].group(1)) * 3600 + int(t[-1].group(2)) * 60), False) if t else (None, False)
DAYREF = re.compile(r"\bDays?\s+(-?\d+)(?:\s*(?:to|-|–|and|through)\s*(?:Day\s+)?(-?\d+))?", re.I)
PATS = {"spo2": r"(?<![\d.])(?:(\d{2,3})\s*[-–]\s*)?(\d{2,3})\s*%(?!\s*of)",
        "hr": r"\bHR\s*(?:peak\s*|of\s*|at\s*onset\s*|was\s*|rose to\s*)?(\d{2,3})\b(?!\s*[-–]\s*\d)|\b(\d{2,3})\s*bpm\b|heart rate (?:of )?(\d{2,3})|\bpeak (\d{2,3})\b",
        "rr": r"\bRR\s*(\d{1,2})\b(?!\s*[-–]\s*\d)|respiratory rate (?:of )?(\d{1,2})\b(?!\s*[-–]\s*\d)|\b(\d{1,2})\s*breaths",
        "sbp": r"\b(\d{2,3})\s*/\s*\d{2,3}\b|\bSBP\s*(\d{2,3})\b",
        "glucose": r"(\d{2,3})\s*(?:[-–]\s*(\d{2,3})\s*)?mg/dL",
        "temp_c": r"(\d{2}\.\d)\s*°?\s*C\b"}
CTX = {"spo2": r"SpO2|saturation|\bsats?\b|fingertip|oximeter|finger probe", "sbp": r"\bBP\b|cuff|mmHg|SBP|blood pressure",
       "glucose": r"CGM|glucose|glucometer|finger-?stick|meter|sugar|nadir|lows?\b|minimum", "hr": r".", "rr": r".", "temp_c": r"."}
def readings(text, vital, default_day=None):
    """[(value, sentence, flagged, activity, ts_s, has_seconds, device, day, is_range)] from text. Each value is attributed to the
    latest 'Day N' (range end) mentioned before it in the text; sentences with no day reference inherit, else default_day."""
    out = []; text = text or ""; pos = 0; cur = default_day
    for s in sentences(text):
        i = text.find(s, pos); pos = i + len(s) if i >= 0 else pos
        refs = [(m.start(), int(m.group(2) or m.group(1))) for m in DAYREF.finditer(s)
                if re.match(r"\s*(?:[;,:(]|and\b|$)", s[:m.start()][-3:] or "") or not s[:m.start()].strip() or re.match(r"\s*(?:\d{1,2}:\d{2}|:|\()", s[m.end():])]
        if not re.search(CTX[vital], s, re.I): 
            if refs: cur = refs[-1][1]
            continue
        for m in re.finditer(PATS[vital], s, re.I):
            g = [x for x in m.groups() if x]; x = float(g[0]) if vital == "temp_c" else int(g[0])
            is_range = False
            if vital == "spo2":
                if not (50 <= x <= 100) or re.search(r"(wear|worn|wear time|battery|charge|of hours|rated)\W{0,3}[\w ]{0,10}$", s[max(0, m.start() - 22):m.start()], re.I): continue
                if m.group(1): x = min(int(m.group(1)), int(m.group(2))); is_range = True
            if vital == "rr" and not (3 <= x <= 70): continue
            if vital == "sbp" and not (50 <= x <= 300): continue
            if vital == "hr" and not (20 <= x <= 300): continue
            if vital == "hr" and re.search(r"(\d{2,3})\s*[-–]\s*$", s[max(0, m.start() - 6):m.start()]): continue
            if vital == "glucose" and len(g) > 1: x = min(int(g[0]), int(g[1])); is_range = True
            here = [d for p_, d in refs if p_ <= m.start()]
            day = here[-1] if here else cur
            ts, sec = hhmmss(s[:m.end()][-40:]) if re.search(r"\d{1,2}:\d{2}", s[:m.end()]) else (None, False)
            if ts is None: ts, sec = ts_fallback(s, m)   # v1.11.0: time earlier in the clause, or 'at hh:mm' just after the value
            dev = "fingertip" if re.search(r"fingertip|oximeter|finger probe", s[max(0, m.start() - 60):m.end()], re.I) else \
                  ("fingerstick" if re.search(r"finger-?stick|glucometer|\bmeter\b", s[max(0, m.start() - 40):m.end()], re.I) else "wearable")
            out.append((x, s, flagged(s), activity(s), ts, sec, dev, day, is_range))
        if refs: cur = refs[-1][1]
    return out
def recs(c, vital, days=(0,)):
    """readings attributed to the given days from the trend plus the caregiver/nurse note (note defaults to Day 0)"""
    r = readings(c.get("trend_last_7d"), vital) + readings(c.get("caregiver_or_nurse_note"), vital, default_day=0)
    return [x for x in r if x[7] in days]
def own_low(c, vital, before_day=0):
    """lowest reliable reading documented before Day 0 (and before a recent medication start/increase, which can shift readings)"""
    r = [x for x in readings(c.get("trend_last_7d"), vital) if x[7] is not None and x[7] < before_day and not x[2] and x[3] != "active"]
    return min(x[0] for x in r) if r else None

def documented_spo2_baseline(c):
    """v1.10: the lowest documented usual/baseline resting SpO2 (pmh, note, trend text before Day 0, baseline_30d text fields)."""
    pre, _ = split_day0(c.get("trend_last_7d") or "")
    txt = " ; ".join([" ".join(c.get("pmh") or []), c.get("caregiver_or_nurse_note") or "", pre, json_text(c.get("baseline_30d"))])
    vals = []
    for m in re.finditer(r"(?:usual|baseline|normally|habitual|typical|known|chronic(?:ally)?|lives at|runs at)[^.;%]{0,40}?(?:SpO2|sats?|saturation)?[^.;%\d]{0,20}(\d{2})(?:\s*[-–]\s*(\d{2}))?\s*%", txt, re.I):
        v = int(m.group(1)); vals.append(v) if 70 <= v <= 100 else None
    return min(vals) if vals else None
def documented_spo2_band(c):
    """v1.11.0: the documented usual/baseline resting SpO2 band (lo, hi) written in advance (pmh, note, pre-Day-0 trend, baseline_30d text)."""
    pre, _ = split_day0(c.get("trend_last_7d") or "")
    txt = " ; ".join([" ".join(c.get("pmh") or []), c.get("caregiver_or_nurse_note") or "", pre, json_text(c.get("baseline_30d"))])
    bands = []
    for m in re.finditer(r"(?:usual|baseline|normally|habitual|typical|known|chronic(?:ally)?|lives at|runs at)[^.;%]{0,40}?(?:SpO2|sats?|saturation)?[^.;%\d]{0,20}(\d{2})(?:\s*[-\u2013]\s*(\d{2}))?\s*%", txt, re.I):
        lo = int(m.group(1)); hi = int(m.group(2) or m.group(1))
        if 70 <= lo <= hi <= 100: bands.append((lo, hi))
    return min(bands) if bands else None
def json_text(x):
    if isinstance(x, dict): return " ".join(f"{k} {v}" for k, v in x.items() if isinstance(v, str))
    return ""

def context(c):
    goals = (c.get("patient_goals") or "") + " " + " ".join(c.get("pmh") or [])
    comfort = bool(re.search(r"hospice|comfort[- ]?(only|focused|care|plan)", goals, re.I)) and not re.search(r"\bno (comfort|hospice)[- \w]*plan|not (on )?hospice", goals, re.I)
    meds = " ".join(m["name"] + " " + m.get("dose", "") for m in c.get("meds") or [])
    pmh = " ".join(c.get("pmh") or []); dis = c.get("discharge") or {}
    alone = bool(re.search(r"\balone\b", c.get("living") or "", re.I))
    hr_ = []
    if re.search(r"heart failure|\bHF\w*\b|HFrEF|HFpEF|cardiomyopathy", pmh, re.I): hr_.append("HF")
    if dis.get("day") is not None and dis["day"] >= -30: hr_.append("discharge_30d")
    if re.search(r"home (oxygen|O2)|oxygen \d|L/min", pmh + " " + meds + " " + " ".join(c.get("devices") or []), re.I): hr_.append("home_O2")
    if re.search(r"dementia|cognitive impairment", pmh, re.I) and alone: hr_.append("dementia_alone")
    if re.search(GLUCOSE_LOWERING, meds, re.I): hr_.append("insulin_or_sulfonylurea")
    if re.search(ANTICOAG, meds, re.I) and re.search(r"fall", pmh, re.I): hr_.append("anticoag_fall_history")
    return {"goals": "comfort_only" if comfort else None, "lives_alone": alone, "anticoag": bool(re.search(ANTICOAG, meds, re.I)),
            "rate_control_med": bool(re.search(RATE_CONTROL, meds, re.I)), "high_risk": hr_, "meds": meds, "pmh": pmh}

INACT_RX = r"(?:no|0|zero) steps[^.;]{0,25}?(?:for )?(\d{1,3})\s*min|(?:still|motionless|no movement)[^.;]{0,15}?(?:for )?(\d{1,3})\s*min|(\d{1,3})\s*min\w*[^.;]{0,20}(?:without|with no|of no) (?:steps|movement)"
def impact_then_inactive(pre, day0, min_inactive):
    """v1.10.2: an on-wrist device impact on Day -1 or Day 0 followed by >= min_inactive minutes without steps/movement."""
    m = re.search(r"\bDay -1\b(?!\s*(?:to|-|\u2013)\s*Day)", pre or "")
    txt = (pre[m.start():] if m else "") + " " + (day0 or "")
    for s in sentences(txt):
        if not re.search(r"\bimpact\b", s, re.I) or re.search(r"off[- ]wrist|not (?:on|worn)|on (?:the )?charger|charging", s, re.I): continue
        i = txt.find(s); win = txt[i:i + len(s) + 200]; mins = []
        for mm in re.finditer(INACT_RX, win, re.I): mins.append(int(next(g for g in mm.groups() if g)))
        for mm in re.finditer(r"(?:0|no|zero) steps (?:from )?(\d{1,2}):(\d{2})\s*(?:to|-|\u2013)\s*(\d{1,2}):(\d{2})", win, re.I):   # v1.11.0: also '0 steps hh:mm-hh:mm'
            a, b_, c_, d_ = map(int, mm.groups()); mins.append((c_ * 60 + d_) - (a * 60 + b_))
        if mins and max(mins) >= min_inactive: return True
    return False
def patient_spo2_band(c):
    """v1.11.0: (band, is_patient_rule). A structured patient_bands.spo2 or a band documented in advance by a clinician (visit/clinic note) is a
    patient-level rule; a band mentioned only in the problem list keeps the v1.10 at_patient_baseline behaviour (nurse_task)."""
    pbs = (c.get("patient_bands") or {}).get("spo2")
    if pbs: return (int(pbs[0]), int(pbs[1])), True
    band = documented_spo2_band(c)
    if not band: return None, False
    pre, _ = split_day0(c.get("trend_last_7d") or ""); txt = (c.get("caregiver_or_nurse_note") or "") + " ; " + pre
    clin = any(re.search(r"(?:visit|clinic|nurse|pulmonolog\w*|clinician|respiratory team)\b[^.;]{0,60}(?:note|documented|records?|recorded|set)|documented as|clinician-set", x, re.I)
               and re.search(r"%", x) for x in sentences(txt))
    return band, clin
def prior_danger_low(c, gmin, days):
    """v1.11.0: a danger-level glucose low documented in the days before Day 0 (pattern of lows)."""
    pre, _ = split_day0(c.get("trend_last_7d") or "")
    return any(r[7] is not None and -days <= r[7] < 0 and r[0] <= gmin for r in readings(pre, "glucose"))
DEVS = {"watch": r"\bwatch\b|\bwrist\b", "ring": r"\bring\b", "fingertip": r"fingertip|finger (?:clip|probe)|\bclip\b|oximeter", "cuff": r"\bcuff\b", "patch": r"\bpatch\b"}
def device_disagreement(c, ctx, dt):
    """v1.11.0: persistent disagreement between two devices on the same vital (or rhythm). Returns {ticket, changes_care, detail} or None."""
    for s in sentences((c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or "")):
        devs = {k for k, rx in DEVS.items() if re.search(rx, s, re.I)}
        if len(devs) < 2 or not re.search(r"\bwhile\b|\bbut\b|whereas|\bvs\.?\b|versus|reads? (?:lower|higher)|disagree\w*|which one is right|simultaneously|at the same (?:time|moments?)", s, re.I): continue
        if not re.search(dt["persist_rx"], s, re.I): continue
        if re.search(r"\birregular\b", s, re.I) and re.search(r"(?<!ir)\bregular\b", s, re.I):
            return {"ticket": "ecg_strip_request", "changes_care": False, "detail": "rhythm disagreement between devices"}
        sp = [int(x) for a in re.findall(r"(\d{2,3})(?:\s*[-\u2013]\s*(\d{2,3}))?\s*%", s) for x in a if x and 70 <= int(x) <= 100]
        if sp:
            thr = dt["spo2_wrist_finger_variance_points"] if {"watch", "fingertip"} <= devs else dt["spo2_device_variance_points"]
            if max(sp) - min(sp) > thr:
                ref = "fingertip" in devs or re.search(r"fingertip|oximeter", " ".join(c.get("devices") or []), re.I)
                return {"ticket": "device_maintenance" if ref else "supply_reference_oximeter_and_baseline", "changes_care": False, "detail": f"SpO2 devices differ by {max(sp) - min(sp)} points"}
            continue
        hr = [int(x) for m in re.finditer(r"(?:\bHR\b|heart rate|pulse|bpm)[^.;%\d]{0,25}(\d{2,3})(?:\s*[-\u2013]\s*(\d{2,3}))?", s, re.I) for x in m.groups() if x and 25 <= int(x) <= 220]
        if len(hr) >= 2 and max(hr) - min(hr) >= dt["hr_disagree_bpm"]:
            rate_drug = re.search(RATE_CONTROL, ctx["meds"], re.I)
            changed = any(m.get("change") in ("started", "dose_increased") and re.search(RATE_CONTROL, m.get("name", ""), re.I) for m in (c.get("recent_med_changes") or [])) \
                or bool(rate_drug and re.search(r"(?:" + RATE_CONTROL + r")[^.;]{0,15}(?:increase\w*|up-?titrat\w*|start\w*)|(?:increase\w*|up-?titrat\w*|start\w*)[^.;]{0,15}(?:" + RATE_CONTROL + ")",
                                              (c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or ""), re.I))
            return {"ticket": "device_maintenance", "changes_care": bool(changed), "detail": f"HR devices differ by {max(hr) - min(hr)} bpm" + (" after a rate-drug change" if changed else "")}
    return None
PLAIN = {   # v1.11.0 plain reasons, keyed by rule:reason, then reason, then rule
    "hospice_distressing_breathlessness": "comfort-focused plan with distressing breathlessness; urgent hospice nurse visit (not hospital)",
    "within_patient_band_home_o2": "oxygen level inside the patient's documented COPD band and home oxygen is prescribed; no action",
    "flagged_reading_below_band_recheck": "low oxygen reading below the COPD band but every low reading carries a device flag; nurse to recheck",
    "learning_spo2_85_88_no_recheck": "oxygen 85-87% during the learning period, no baseline or band and no recheck; prescriber review (below 85% pages)",
    "fall_comfort_only_hospice_nurse": "possible fall on a blood thinner in a comfort-focused plan; hospice nurse to check",
    "possible_fall_inr_high": "possible fall on warfarin with a high INR; prescriber review",
    "unwitnessed_probable_fall_age85": "unwitnessed probable fall on a blood thinner at 85 or older; prescriber review even without pain or head strike",
    "heavy_sit_on_anticoagulant": "sat down heavily (not a fall) on a blood thinner, no pain or head strike; nurse to check",
    "explained_bump_on_anticoagulant": "explained bump on a blood thinner, no pain or head strike; nurse to check",
    "angina_unstable_features": "angina with unstable features (longer, more often, at rest or with sweating)",
    "angina_new_gtn_request": "angina episodes with a new request for GTN; prescriber review",
    "angina_gtn_efficacy": "angina with a GTN spray that may be out of date or less effective; prescriber review",
    "angina_after_antianginal_stop": "angina after an anti-anginal drug was stopped; prescriber review",
    "stable_angina_unchanged": "stable angina at the usual pattern; nurse check (not silent)",
    "gap_partly_explained_by_device_uploads": "high-risk patient with a watch data gap while other devices kept uploading and no human contact; nurse to check",
    "bp_cleared_by_clean_repeat": "high or movement-flagged BP cleared by a clean repeat within 15 minutes; no action",
    "within_patient_band": "oxygen level inside the patient's documented band; no action",
    "HT_DRUG_LOW": "confirmed low blood sugar with symptoms on {glu}; a drug-induced low is a foundation rule and is never suppressed{hosp}",
    "ckd_low_dose_review": "low blood sugar on {glu} with kidney disease, recovered without symptoms; please review the dose (not a nurse visit)",
    "ckd_low_compression_explained": "low blood sugar on {glu} with kidney disease, likely sensor compression, normal recheck; check sensor placement and confirm no symptoms",
    "ckd_low_exertion_explained": "low blood sugar on {glu} with kidney disease after exertion, recovered without symptoms; teach exercise precautions (a repeat goes to the provider)",
    "recent_ckd_low_dose_review": "a recent low blood sugar on {glu} with kidney disease (within 72 hours), recovered without symptoms; please review the dose",
    "within_band_low_no_home_o2": "at her documented baseline but that baseline is low without oxygen; evaluate for home oxygen",
    "repeated_lows_dose_review": "repeated low blood sugars on {glu}; please review the dose",
    "below_patient_band_copd_lt85": "COPD oxygen level confirmed below 85% and below the patient's own band; this is not baseline",
    "below_88_change_from_own_baseline": "oxygen level below 88% and below this patient's own usual level",
    "at_patient_baseline": "low oxygen reading close to this patient's usual level; nurse to confirm the baseline is current",
    "unreliable_reading": "abnormal reading that looks unreliable (device or fit); nurse to recheck",
    "possible_fall_unverified": "possible fall on a blood thinner (impact or device signal) without a confirmed fall, pain or head strike; nurse to check",
    "explained_caregiver_check": "possible fall on a blood thinner that a caregiver checked; nurse to confirm there was no fall",
    "explained": "trigger explained by the caregiver note; nurse to confirm",
    "device_artifact_stable_patient": "device reading looks like a device problem (second device, firmware flag or reported activity disagree) and the patient is stable; device ticket filed, no clinical alert",
    "device_disagreement": "two devices disagree on the same reading; device ticket filed, no clinical alert",
    "device_disagreement_could_change_care": "devices disagree on heart rate after a rate-drug change; a manual pulse will tell us which is right (device ticket filed)",
    "device_disagreement_changes_care": "two devices disagree and the answer could change care; nurse to check which is right (device ticket filed)",
    "goals_of_care": "comfort-focused plan: same-shift hospice nurse rather than hospital escalation",
    "HT_FALL_PAIN": "pain after a fall; possible injury needs urgent assessment",
    "HT_FALL_ANTICOAG": "fall on a blood thinner; risk of internal bleeding",
    "HT_SYNCOPE": "loss of consciousness (fainting or collapse)",
    "HT_FOCAL_NEURO": "new one-sided weakness, facial droop or speech change; possible stroke",
    "HT_CHEST_PAIN_VITALS": "chest pain with concerning features or vital signs",
    "HT_GAP48_HIGHRISK": "high-risk patient with no data and no contact for 48 hours",
    "HT_BRADY_RATE_DRUG": "slow heart rate with symptoms on a rate-slowing drug",
    "HT_SPO2_REST_DYSPNEA": "confirmed low oxygen with breathlessness at rest in heart or lung disease",
    "HT_VS_IMPLAUSIBLE": "reading is not physiologically possible (likely a device error); recheck the device",
    "HT_CHEST_PAIN_ECG": "chest pain with an abnormal ECG",
    "HT_VS_DANGER": "vital sign beyond the danger limit",
    "HT_SEROTONERGIC_CONFUSION": "new confusion on a serotonergic drug combination",
    "HT_SPO2_LT88": "oxygen level below 88%",
}
def plain_reason(l1, ctx):
    """v1.11.0: one short sentence for the receiver saying why Layer 1 routed the alert this way (None if Layer 1 has no decision)."""
    if not l1.get("tier"): return None
    glu = ", ".join(sorted({m.group(0).lower() for m in re.finditer(GLUCOSE_LOWERING, ctx.get("meds") or "", re.I)})) or "a glucose-lowering drug"
    rule, reason = l1.get("rule"), l1.get("reason")
    t = PLAIN.get(f"{rule}:{reason}") or PLAIN.get(reason or "") or PLAIN.get(rule or "") or f"Layer 1 rule {rule} ({reason})"
    r = t.format(glu=glu, hosp=" (page the hospice nurse)" if l1.get("escalation_target") == "hospice_nurse" else "")
    if l1.get("hitm_required") and "dose" not in r: r += "; insulin/sulfonylurea with kidney disease, so a clinician reviews it"
    return r
def route_reason(l1, route_, owner, case=None):
    """v1.11.0: plain_reason for any routed alert (nurse_task, provider_task, urgent_page). Layer 1-owned -> the Layer 1 reason;
    Jev-owned -> a model-routed reason naming the context facts the receiver needs. silent_log -> None."""
    if route_ in (None, "silent_log"): return None
    if l1.get("plain_reason") and owner not in ("jev",): return l1["plain_reason"]
    hr_ = (l1.get("context") or {}).get("high_risk") or []
    facts = {"HF": "heart failure", "discharge_30d": "recently discharged", "home_O2": "on home oxygen", "dementia_alone": "dementia, lives alone",
             "insulin_or_sulfonylurea": "on insulin/sulfonylurea", "anticoag_fall_history": "on a blood thinner with falls"}
    ctxs = ", ".join(facts[h] for h in hr_ if h in facts)
    return f"no Layer 1 trigger; the decision models routed this to {route_.replace('_', ' ')} on the overall picture" + (f" ({ctxs})" if ctxs else "")
def _dec(rule, tier, reason=None, **kw): return {"rule": rule, "tier": tier, "reason": reason, **kw}
RANK = {"ABSOLUTE": 5, "CONFIRM_FIRST": 4, "SUPPRESSED_goals": 3, "SUPPRESSED": 2, "LOG_ONLY": 2, "ARTIFACT": 1}
def _rank(d): return (RANK["SUPPRESSED_goals"] if d["tier"] == "SUPPRESSED" and d.get("reason") == "goals_of_care" else RANK.get(d["tier"], 0)) + (0.5 if d.get("foundation") else 0)   # v1.11.0: a FOUNDATION rule wins ties

def _evaluate_v1112(case):
    c = facts_only(case); ctx = context(c); P = PARAMS
    trend = c.get("trend_last_7d") or ""; note = c.get("caregiver_or_nurse_note") or ""
    flags = " ; ".join((c.get("data_quality") or {}).get("artifact_flags") or [])
    pre, day0 = split_day0(trend); now = day0 + " " + note
    bs = c.get("baseline_status") or {}; base30 = c.get("baseline_30d") or {}
    learning = bs.get("phase") == "learning"
    cands = []; ectx = {"goals": ctx["goals"], "lives_alone": ctx["lives_alone"]}
    distress = find(r"few words|short sentences|cannot catch (?:her|his|my) breath|can't catch|struggling to breathe|gasping|breathless (?:at rest|sitting)|fighting for breath", now) is not None
    gl_sym = find(r"confus\w*|drowsy|sweaty|sweating|shak(?:y|ing)|clammy|slurred|not making sense|only to (?:her|his) name|unresponsive|seizure|disorient\w*", now) is not None
    breath = {"distressing": distress, "home_treatable": ctx["goals"] == "comfort_only"}
    b = T.Baseline("L1", 0.0, P)
    if learning: ts0 = (max(int(bs.get("monitoring_day") or 1), 1) - 1) * DAY + 9 * 3600   # inside the onboarding window
    else: ts0 = 99 * DAY; b.learning_until = -1.0
    # ---- 1. hard limits / implausible / rate artifact on Day 0 readings; CGM rule on the last 48 h (Day -1, Day 0)
    for vital in ("hr", "spo2", "rr", "sbp", "temp_c"):
        h = P["hard_limits"][vital]; prev = None
        for x, s, fl, act, t, sec, dev, day, rng in sorted(recs(c, vital), key=lambda r: (r[4] is None, r[4] or 0)):
            r = {"vital": vital, "value": x, "ts": ts0 + (t or 0), "activity_state": act, "quality_flags": ["motion"] if fl else []}
            if prev and sec and prev[2] and t is not None and prev[1] is not None and 0 < t - prev[1] <= 60: r["prev"] = {"value": prev[0], "dt_s": t - prev[1]}
            prev = (x, t, sec)
            beyond = not (h["implausible_low"] <= x <= h["implausible_high"]) or (h["danger_low"] is not None and x <= h["danger_low"]) or (h["danger_high"] is not None and x >= h["danger_high"])
            fast = "prev" in r and h.get("max_rate_per_s") and abs(x - r["prev"]["value"]) / r["prev"]["dt_s"] > h["max_rate_per_s"]
            if not (beyond or fast) or rng: continue
            d = T.evaluate(r, b, P, {**ectx, "symptoms": gl_sym, "breathlessness": breath})
            if d["tier"] in ("NORMAL", "WATCH", "CONFIRM_FIRST"): continue
            cands.append({**d, "source": f"evaluate:{vital}={x}"})
    gl = recs(c, "glucose", days=(-1, 0)); gmin = P["hard_limits"]["glucose"]["danger_low"]
    sens = [r for r in gl if r[6] != "fingerstick" and r[0] <= gmin]
    if sens:
        x, s = min((r[0], r[1]) for r in sens)
        fs = [r[0] for r in gl if r[6] == "fingerstick"]
        cgm = {"overnight": bool(re.search(r"night|nocturnal|0[0-5]:\d\d", s, re.I)), "symptoms": gl_sym,
               "pressure_documented": bool(find(r"pinned|pressed|under (?:the )?bed rail|lying on (?:the )?sensor|compression", flags + " " + note + " " + s)),
               "fingerstick": {"value": min(fs), "minutes_apart": None} if fs else None}
        d = T.evaluate({"vital": "glucose", "value": x, "ts": ts0, "source": "cgm", "cgm": cgm, "symptoms": gl_sym}, b, P, {**ectx, "symptoms": gl_sym})
        if d["tier"] not in ("NORMAL", "WATCH"): cands.append({**d, "source": f"evaluate:glucose={x}"})
    cgm_pressure = bool(sens) and cgm["pressure_documented"]
    # ---- v1.11.0 FOUNDATION: confirmed + symptomatic danger-level low on insulin or a sulfonylurea -> urgent page, even in hospice, regardless of CKD
    V11 = T.v110(P).get("v1110") or {}; dl = V11.get("drug_low_floor")
    drug_lowering = bool(re.search(GLUCOSE_LOWERING, ctx["meds"], re.I))
    if dl and drug_lowering:
        meter_lo = [r for r in gl if r[6] == "fingerstick" and r[0] <= dl["glucose_confirm_max"]]
        confirmed_low = bool(meter_lo) or len([r for r in gl if r[6] != "fingerstick" and r[0] <= gmin]) >= 2
        if confirmed_low and find(dl["symptoms_rx"], now):
            cands.append(_dec("HT_DRUG_LOW", "ABSOLUTE", "drug_induced_low_symptomatic", route=dl["route"], page=True, foundation=True,
                              escalation_target="hospice_nurse" if ctx["goals"] == "comfort_only" else None))
    # ---- 1b. learning period (v1.8): a reading beyond the population defaults -> CONFIRM_FIRST (engine rule)
    if learning:
        for vital in ("spo2", "hr", "rr"):
            for x, s, fl, act, *_rest in recs(c, vital):
                if fl or act == "active" or _rest[-1]: continue
                d = T.evaluate({"vital": vital, "value": x, "ts": ts0, "activity_state": act}, b, P, {**ectx, "breathlessness": breath})
                if d["tier"] == "CONFIRM_FIRST": cands.append({**d, "source": f"learning:{vital}={x}"})
    # ---- 2. syncope
    if find(T.wording_rx(P, "syncope", r"\bfaint(?:ed|ing)?\b|passed out|lost consciousness|loss of consciousness|went limp|\blimp\b|blacked out|unresponsive|\bsyncop\w*"), now) and \
       not find(r"near[- ]?faint|nearly faint|presyncop\w*|feel\w* faint|felt faint|faint when (?:she|he) stands", now, neg=False):
        cands.append(T.apply_goals_of_care(_dec("HT_SYNCOPE", "ABSOLUTE", "syncope", route="urgent_page"), P, ectx, None))
    # ---- 3. focal neuro
    fn = find(T.wording_rx(P, "focal_neuro", r"slurred|facial droop|face (?:is )?droop\w*|droop\w* (?:on the )?(?:left|right)|(?:arm|leg|hand|side) (?:has )?(?:just )?(?:gone|went|is|became) (?:weak|numb)|weak(?:ness)? (?:in|of) (?:the |his |her )?(?:left|right)|(?:left|right) (?:arm|leg|side|foot) (?:weak\w*|gave way|numb)|cannot find (?:the )?words|can't find words|word[- ]finding|could not lift the (?:left|right)|garbled|aphasi\w*|not following (?:two-step )?instructions|cannot follow"), now)
    if fn:
        base_def = find(r"unchanged (?:from|since)|residual|same (?:weakness|deficit) (?:as|since)|long-?standing|documented (?:at|in) (?:a )?(?:prior|earlier|clinic)", note) and re.search(r"stroke|deficit|palsy", ctx["pmh"], re.I)
        if base_def: cands.append(_dec("HT_FOCAL_NEURO", "SUPPRESSED", "at_patient_baseline", route=None))
        else: cands.append(T.apply_goals_of_care(_dec("HT_FOCAL_NEURO", "ABSOLUTE", "new_focal_deficit", route="urgent_page"), P, ectx, None))
    # ---- 4. chest pain (banded, engine evaluate_chest_pain)
    CP = r"chest (?:pain|pressure|tightness|discomfort|heaviness|ache)|(?:pressure|tightness|pain|discomfort|heaviness|squeez\w*) in the (?:centre|center|middle) of (?:the|his|her) chest|middle of (?:his|her) chest|tight\w* (?:was )?across (?:his|her|the) chest|tight(?:ness)? in (?:the|his|her) chest|central chest|\bsqueeze\b|angina\w* (?:episode|attack)"
    CP = T.wording_rx(P, "chest_pain", CP)
    prior_ep = {int(m.group(1)) for m in re.finditer(r"Day (-\d+)[^.;]{0,60}?(?:episodes? (?:of )?(?:chest|tight)|chest (?:tight|pain|pressure|discomfort)|\bepisodes?\b)", pre, re.I)} if re.search(CP, pre + " " + now, re.I) else set()
    day0_ep = bool(re.search(r"\bepisodes?\b", day0, re.I)) and bool(prior_ep)
    if find(CP, now) or day0_ep:
        ss = sentences(now)
        chest_s = " ".join(x for x in ss if re.search(CP + r"|episode|tight|pressure|eased|easing|minutes|\bmin\b", x, re.I))
        d0 = lambda v: [r for r in recs(c, v) if not r[2] and not r[8]]
        hrs, sb = d0("hr"), d0("sbp"); vit = {}
        if hrs: vit["hr"] = {"value": max(r[0] for r in hrs)}
        if sb:
            lo_, hi_ = min(r[0] for r in sb), max(r[0] for r in sb); vit["sbp"] = {"value": lo_ if lo_ <= 104 else hi_}
        sp, rr_ = d0("spo2"), d0("rr")
        if sp: vit["spo2"] = {"value": min(r[0] for r in sp)}
        if rr_: vit["rr"] = {"value": max(r[0] for r in rr_)}
        if not day0_ep and prior_ep and not hrs:   # Day 0 episode with no Day 0 HR: use the episode HR from the trend
            pass
        if day0_ep and not hrs:
            ep_hr = [r[0] for r in readings(trend, "hr") if r[7] is not None and r[7] < 0 and re.search(r"episode|stairs|chest", r[1], re.I) and not r[8]]
            if ep_hr: vit["hr"] = {"value": max(ep_hr)}
        onset = [x for x in ss if re.search(CP + r"|\bepisodes?\b", x, re.I)]
        on_s = re.split(r";", onset[0])[0] if onset else ""
        act = activity(on_s) if on_s else "rest"; mse = None
        if act != "active" and find(r"\b(climb\w*|stairs|walk(?:ing|ed)? (?:up|to|uphill)|uphill|on hills)\b", note + " " + (chest_s if day0_ep else "")) and not re.search(r"seated|sitting in|in a chair|not walked|no walking", chest_s, re.I): act = "active"
        if act == "active":
            m = re.search(r"stopped walking at (\d{1,2}):(\d{2})|stopped walking[^.;]*?(\d{1,2}):(\d{2})", chest_s, re.I)
            hr_t = re.search(r"HR \d{2,3} at (\d{1,2}):(\d{2})", chest_s)
            mse = (int(hr_t.group(1)) * 60 + int(hr_t.group(2))) - (int(m.group(1) or m.group(3)) * 60 + int(m.group(2) or m.group(4))) if (m and hr_t) else 0
            mse = max(mse, 0)
        rf = []
        if find(r"sweat\w*|diaphore\w*|clammy", now): rf.append("diaphoresis")
        if find(r"breathless\w*|short of breath|dyspn\w*|out of breath", now): rf.append("dyspnea")
        if find(r"radiat\w*|(?:into|down|to) (?:his|her|the) (?:left )?(?:arm|jaw|neck|shoulder)|\bjaw\b", now): rf.append("radiation")
        if find(r"dizz\w*|light-?headed|near[- ]?faint|presyncop\w*", now): rf.append("syncope_or_presyncope")
        if find(r"\bpale\b|pallor|\bgrey\b|\bgray\b|ashen", now): rf.append("pallor")
        mins = [int(x) for x in re.findall(r"(\d{1,3})\s*min(?:utes)?\b(?!\s+(?:after|of rest|rest|later))", chest_s) ]
        eased = re.search(r"eased (?:within|after|in) (?:about )?(\d+)\s*min", chest_s, re.I)
        if (mins and max(mins) >= 15 and not re.search(r"(?:walk\w*|exercise\w*)[^.;]{0,20}(?:for )?about \d+ min", chest_s, re.I) and not (eased and int(eased.group(1)) < 15)) or find(r"still (?:tight|present|there|has (?:the )?(?:pain|pressure))|ongoing|persist\w*|not easing|has not eased", chest_s): rf.append("persistent_ge_15min")
        stable = find(r"same as (?:it has been|usual|always)|no more often|unchanged pattern|stable pattern|for the past (?:year|months)", now, neg=False)
        if not stable and (find(r"more often|more frequent\w*|increasingly|getting worse|worse each|crescendo|(?:third|fourth|fifth|sixth|\d+(?:rd|th)) episode|new onset", now) or len(prior_ep) >= 2):
            rf.append("crescendo_pattern")
        ecg_pos = [x for x in sentences(day0 + " " + note) if re.search(r"ECG|strip|trace", x, re.I) and find(r"ST[- ]?(?:segment )?(?:depression|elevation)|ST changes?|ischaemic changes|ischemic changes", x)]
        ecg_rel = [x for x in ecg_pos if not flagged(x)]
        refuted = any(re.search(r"repeat|clean", x, re.I) and re.search(r"no ST|without ST", x, re.I) for x in sentences(day0))
        sym = {"chest_pain": True, "red_flags": rf, "concordant": None, "ecg_change": bool(ecg_rel) or (bool(ecg_pos) and not refuted), "ecg_reliable": bool(ecg_rel)}
        d = T.evaluate_chest_pain({"ts": ts0, "activity_state": act, "minutes_since_exertion": mse, "vitals": vit, "symptoms": sym}, P,
                                  context={"rate_control_med": ctx["rate_control_med"], "goals": ctx["goals"]})
        if d:
            if d["tier"] == "LOG_ONLY": d = {**d, "tier": "SUPPRESSED", "reason": "below_band_threshold"}
            sa = bool(stable) and not rf and d.get("band") == "D" and act == "active" \
                and find(r"angina|\bCAD\b|coronary", " ".join(str(x) for x in (c.get("pmh") or [])), neg=False) \
                and find(r"eased|settle\w*|relieved|went off|passed", chest_s + " " + note) \
                and not find(r"at rest|while (?:sitting|resting|lying)|in bed|woke|asleep|not happened before|first time|new\b|longer|more often|more frequent\w*|worse|sick|nause\w*|vomit\w*|sweat\w*|faint", now) \
                and not (mins and max(mins) >= 10)   # PLACEHOLDER v1.11.2: 10-min duration ceiling
            if sa: d = {**d, "stable_angina": True}
            cands.append({**d, "source": "chest_pain", "inputs": {"activity": act, "mse": mse, "vitals": vit, "red_flags": rf, "ecg_change": sym["ecg_change"], "ecg_reliable": sym["ecg_reliable"], "rate_control": ctx["rate_control_med"]}})
    # ---- 5. fall on an anticoagulant
    F2 = T.v110(P).get("fall_v1102") or {}
    FALL = (F2.get("witnessed_rx") + "|" if F2 else "") + r"\bimpact\b|\bfell\b|\bfall(?:en)?\b(?! risk)|found (?:him|her) on|on the (?:\w+ )?floor|slipp\w*|sat down hard|went down|go down|tripped|lost (?:his|her) footing"
    # v1.10.2: witnessed fall / pain after a fall / on-wrist impact + inactivity (Day -1 or Day 0)
    witnessed = bool(F2) and find(F2["witnessed_rx"], now) is not None
    fell_any = witnessed or any(find(r"\bfell\b|had a fall|\bfallen\b|tripped and fell|on the (?:\w+ )?floor", x) and not re.search(r"\b(?:watch|band|device|phone|ring)\b[^.;]{0,40}\bfloor\b", x, re.I) for x in sentences(now))
    pain_after = bool(F2) and fell_any and find(F2["pain_rx"], now) is not None
    if pain_after:   # blocks suppression; escalates with or without an anticoagulant
        cands.append(T.apply_goals_of_care(_dec("HT_FALL_PAIN", "ABSOLUTE", "pain_after_fall", route=F2.get("route", "urgent_page"), confirm_step=None, page=True), P, ectx, None))
    imp_inact = bool(F2) and ctx["anticoag"] and impact_then_inactive(pre, day0, F2.get("inactivity_min", 10))
    if ctx["anticoag"] and not pain_after and (find(FALL, now) or imp_inact):
        confirmed = witnessed or any(find(r"\bfell\b|slipp?\w*|\bslip\b|sat down hard|found (?:him|her) on (?:the )?floor|on the (?:\w+ )?floor|tripped|went down|go down|had a fall|fallen", x)
                        and not re.search(r"\b(?:watch|band|device|phone|ring)\b[^.;]{0,40}\bfloor\b|\bfloor\b[^.;]{0,25}\b(?:watch|band|device)\b", x, re.I) for x in sentences(note))
        hs = (V11.get("impact_inactivity_cap") or {}).get("head_strike_rx")
        if hs and find(hs, now): confirmed = True   # v1.11.0: a head strike lifts the impact+inactivity cap
        unanswered = find(r"did not answer|didn't answer|no answer|not answered|unanswered|did not respond|no response", now, neg=False) is not None
        cap_ = V11.get("impact_inactivity_cap") or {}   # v1.11.0: long inactivity or lives alone with dementia keeps the v1.10.2 confirm-first path
        cap_exempt = bool(cap_) and (impact_then_inactive(pre, day0, cap_.get("long_inactivity_min", 10 ** 6)) or (ctx["lives_alone"] and bool(re.search(r"dementia|cognitive impairment", ctx["pmh"], re.I))))
        cg_check = (not confirmed) and find(r"checked (?:on )?(?:him|her)|went to (?:check|see)|found (?:him|her) (?:walking|sitting|standing|in bed|well|fine)|(?:she|he) (?:was|is) (?:walking|fine|well|pain-?free)|pain-?free|(?:did not|didn't|denies having) fall\w*|no (?:sign of a )?fall|no injur\w*", note, neg=False)
        fA = (T.v110(P).get("fall_anticoag") or {}).get("confirmed_tier", "CONFIRM_FIRST")
        if not witnessed and not imp_inact and find(r"dropped (?:the |his |her )?(?:watch|band)|watch (?:fell|slid|dropped|clatter\w*|came off)|clatter\w*|caught (?:herself|himself)|stayed on (?:her|his) feet|near[- ]fall|knocked (?:the|her|his) (?:watch|wrist)", now, neg=False):
            cands.append(_dec("HT_FALL_ANTICOAG", "SUPPRESSED", "explained", route=None))
        elif imp_inact and not confirmed and not unanswered and not cap_exempt:   # v1.10.2 / v1.11.0 cap at nurse_task: on-wrist impact + inactivity on an anticoagulant, even if explained away
            cands.append(_dec("HT_FALL_ANTICOAG", "SUPPRESSED", "possible_fall_unverified", route=None))
        elif cg_check and not find(r"\bfell\b|had a fall|fallen", note):   # v1.10: unwitnessed possible fall cleared by a caregiver check -> nurse confirms no fall
            cands.append(_dec("HT_FALL_ANTICOAG", "SUPPRESSED", "explained_caregiver_check", route=None, explained_by=cg_check.group(0)))
        elif not confirmed and find(r"off[- ]wrist|on (?:the )?(?:bedside )?charger|charging|not on (?:the|her|his) wrist", day0):
            cands.append(_dec("HT_FALL_ANTICOAG", "SUPPRESSED", "possible_fall_unverified" if F2 else "unreliable_reading", route=None))   # v1.10.2: floor nurse_task
        elif confirmed and fA == "ABSOLUTE":   # v1.10: a confirmed fall on an anticoagulant is ABSOLUTE (Wayne: HK6-001, GL1-005)
            cands.append(T.apply_goals_of_care(_dec("HT_FALL_ANTICOAG", "ABSOLUTE", "fall_on_anticoagulant_confirmed", route="urgent_page", confirm_step=None, page=True), P, ectx, None))
        else:
            d = _dec("HT_FALL_ANTICOAG", "CONFIRM_FIRST", "fall_on_anticoagulant", route="urgent_page", confirm_step="already_confirmed" if confirmed else "watch_prompt", page=True if confirmed else "if_confirmed_or_timeout")
            if not confirmed and find(r"did not answer|didn't answer|no answer|not answered|unanswered|did not respond|no response", now, neg=False):
                d = T.resolve_confirm(d, "no_answer", P, ectx)
            cands.append(T.apply_goals_of_care(d, P, ectx, None))
    # ---- 6. SpO2 < 88 at rest, established phase: reliable? at own documented baseline? already confirmed?
    if not learning:
        thr = P["confirm_first"]["spo2_population_threshold"]
        sp0 = [r for r in recs(c, "spo2") if not r[8] and r[3] != "active"]
        low = [r for r in sp0 if r[0] < thr and r[0] > P["hard_limits"]["spo2"]["danger_low"]]
        if low:
            tips = [r for r in sp0 if r[6] == "fingertip" and not r[2]]
            rel = [r for r in low if not r[2]]
            chg = [m["day"] for m in (c.get("recent_med_changes") or []) if m.get("change") in ("started", "dose_increased") and m.get("day") is not None]
            ref_day = min(chg + [0])
            own = own_low(c, "spo2", before_day=ref_day)
            if own is None: own = base30.get("spo2_night_min")
            doc = documented_spo2_baseline(c)   # v1.10: a documented usual/baseline SpO2 (e.g. COPD 'usual resting SpO2 86-89%')
            if doc is not None: own = doc if own is None else min(own, doc)
            band, band_rule = patient_spo2_band(c)   # v1.11.0: a documented band's lower bound replaces night minimums (below the band is not baseline)
            if band: own = band[0]
            pb = V11.get("patient_band") or {}
            if not rel or (tips and min(t[0] for t in tips) >= 92):
                cands.append(_dec("HT_SPO2_LT88", "SUPPRESSED", "unreliable_reading", route=None))
            elif band and band_rule and pb and min(r[0] for r in rel) >= band[0] and not distress:   # v1.11.0: inside a patient-level band -> rule does not fire
                bn = (T.v110(P).get("v1111") or {}).get("band_no_home_o2")
                if bn and re.search(pb["copd_rx"], ctx["pmh"], re.I) and "home_O2" not in ctx["high_risk"] and (band[0] <= bn["band_low_max"] or (base30.get("spo2_night_min") or 100) < bn["night_min_below"]):
                    cands.append(_dec("HT_SPO2_LT88", "SUPPRESSED", "within_band_low_no_home_o2", route=None, default_route=bn["route"], own_low=band[0], band=list(band)))   # v1.11.1: evaluate for home oxygen
                else: cands.append(_dec("HT_SPO2_LT88", "SUPPRESSED", "within_patient_band", route=None, default_route="silent_log", own_low=band[0], band=list(band)))
            elif own is not None and min(r[0] for r in rel) >= own:
                cands.append(_dec("HT_SPO2_LT88", "SUPPRESSED", "at_patient_baseline", route=None, own_low=own))
            else:
                conf = any(t[0] < thr for t in tips) and len(rel) >= 1 and any(r[6] == "fingertip" for r in rel)
                below85 = bool(band and pb and re.search(pb["copd_rx"], ctx["pmh"], re.I) and ctx["goals"] != "comfort_only" and min(r[0] for r in rel) < pb["copd_urgent_below"])
                d = _dec("HT_SPO2_LT88", "CONFIRM_FIRST", "below_patient_band_copd_lt85" if below85 else "below_88_change_from_own_baseline", route="urgent_page", confirm_step="already_confirmed" if conf else "fingertip_recheck", page=True if conf else "if_confirmed_or_timeout", own_low=own)
                basis = T.urgent_comfort_basis({"vital": "spo2", "value": min(r[0] for r in rel)}, None, P, {**ectx, "breathlessness": breath, "trigger_family": "respiratory"})
                cands.append(T.apply_goals_of_care(d, P, ectx, basis))
    # ---- 6b. v1.10.2 candidate: confirmed SpO2 <= max at rest + rest dyspnea in HF/COPD (not comfort-only)
    s5 = T.v110(P).get("spo2_rest_dyspnea")
    if s5 and not learning and ctx["goals"] != "comfort_only" and re.search(s5["dx_rx"], ctx["pmh"], re.I):
        sp5 = [r for r in recs(c, "spo2") if not r[2] and not r[8] and r[3] != "active" and r[0] <= s5["spo2_max"] and r[0] > P["hard_limits"]["spo2"]["danger_low"]]
        tips5 = [r for r in sp5 if r[6] == "fingertip"]
        if (len(tips5) >= 2 or (tips5 and len(sp5) >= 2)) and find(s5["dyspnea_rx"], now):
            cands.append(_dec("HT_SPO2_REST_DYSPNEA", "CONFIRM_FIRST", "spo2_le_max_confirmed_rest_dyspnea", route="urgent_page", confirm_step="already_confirmed", page=True))
    # ---- 7. 48 h data gap in a high-risk patient
    dq = c.get("data_quality") or {}
    if (dq.get("longest_gap_h") or 0) >= 48 and ctx["high_risk"]:
        gs = re.search(r"(?:offline|no [\w ,]*data|data[\w ,]* (?:run|ran|stop\w*)[\w ]* to|last [\w ]*sync|from)\s*(?:from\s*)?Day (-\d+)(?:\s+(\d{1,2}):(\d{2}))?", flags + " ; " + trend, re.I)
        g_day = int(gs.group(1)) if gs else None; g_min = (int(gs.group(2)) * 60 + int(gs.group(3))) if (gs and gs.group(2)) else 0
        contact = None
        _ss = sentences(note + " " + trend); _nx = (T.v110(P).get("v1111") or {}).get("gap_contact", {}).get("next_sentence")
        for _i, x in enumerate(_ss):
            m = re.search(r"Day (-?\d+)\s*(?:at\s*)?(\d{1,2}):(\d{2})", x)
            if m and _nx and _i + 1 < len(_ss) and not re.search(r"Day -?\d+", _ss[_i + 1]): x = x + " " + _ss[_i + 1]   # v1.11.1: detail in the next sentence
            if not (m and re.search(r"video call|phoned|phone (?:call|check)|called|visited|visit\b|check-?in|checked on|saw (?:him|her)|texted|spoke|talked", x, re.I)): continue
            if find(r"not answered|no answer|did not answer|didn't answer|unanswered|no call|no check-?in|no contact", x, neg=False): continue
            gx = T.v110(P).get("gap_contact_exclude") or {}
            if gx and re.search(gx["device_rx"], x, re.I) and not re.search(gx["human_rx"], x, re.I): continue   # v1.10: scale weigh-ins / syncs are not contact
            if not re.search(r"answered|looked|said|eating|well|fine|stable|described|talking|chatted|reported|sounded", x, re.I): continue
            if g_day is not None and (int(m.group(1)), int(m.group(2)) * 60 + int(m.group(3))) < (g_day, g_min): continue   # contact before the gap began does not explain it
            contact = x; break
        dock = find(r"charger log|dock(?:ed)? log|on (?:the )?(?:charger|dock)\b[^.;]*(?:log|whole|entire|throughout)", flags + " " + trend + " " + note)
        if contact or dock: cands.append(_dec("HT_GAP48_HIGHRISK", "SUPPRESSED", "explained", route=None, explained_by=(contact or "dock/charger log")[:120]))
        else: cands.append(T.apply_goals_of_care(_dec("HT_GAP48_HIGHRISK", "CONFIRM_FIRST", "unexplained_gap_high_risk", route="urgent_page", confirm_step="caregiver_ping", page="if_confirmed_or_timeout", high_risk=ctx["high_risk"]), P, ectx, None))
    # ---- v1.10 bradycardia on a rate-slowing drug
    bv = T.v110(P).get("bradycardia_rate_drug")
    if bv and re.search(bv["drugs_rx"], ctx["meds"], re.I):
        hrl = [r for r in recs(c, "hr") if not r[2] and r[3] != "active" and not r[8] and r[0] < bv["hr_below"] and r[0] > P["hard_limits"]["hr"]["danger_low"]]
        if hrl:
            if find(bv["symptoms_rx"], now):
                cands.append(T.apply_goals_of_care(_dec("HT_BRADY_RATE_DRUG", "CONFIRM_FIRST", "bradycardia_on_rate_drug_symptomatic", route="urgent_page", confirm_step="patient_call", page="if_confirmed_or_timeout"), P, ectx, None))
    # ---- v1.10 clean repeat: an abnormal SpO2 cleared by a clean repeat (other finger/hand or second device) within the window, no symptoms
    cr = T.v110(P).get("clean_repeat"); symptomatic = gl_sym or distress or bool(find(r"breathless\w*|short of breath|dizz\w*|chest (?:pain|pressure)|confus\w*", now))
    cleared = False
    if cr and not symptomatic:
        sp = [r for r in recs(c, "spo2") if not r[8] and r[4] is not None]
        lows = [r for r in sp if r[0] < P["confirm_first"]["spo2_population_threshold"]]
        for lo_ in lows:
            rep = [r for r in sp if r[4] > lo_[4] and r[4] - lo_[4] <= cr["window_min"] * 60 and r[0] >= cr["spo2_clean_min"] and not clause_flagged(r)
                   and (r[6] != lo_[6] or r[1] != lo_[1] or re.search(r"other (?:hand|finger)|contralateral|(?:left|right) (?:index|middle|hand|finger)|repeat|second", r[1], re.I))]
            if rep: cleared = True; break
        spo2_c = [d for d in cands if (str(d.get("source", "")).startswith("evaluate:spo2") or d.get("rule") == "HT_SPO2_LT88") and d.get("tier") != "ARTIFACT"]
        if cleared and spo2_c:   # an engine ARTIFACT (implausible / non-physiologic rate) stays ARTIFACT
            kept = [d for d in cands if d not in spo2_c]
            cands = kept + [_dec("HT_SPO2_LT88" if lows and min(r[0] for r in lows) > P["hard_limits"]["spo2"]["danger_low"] else "HT_VS_DANGER", "SUPPRESSED", "cleared_by_repeat", route=None, default_route="silent_log")]
    # CGM low already refuted by a fingerstick (engine section 8 -> unreliable_reading) with no symptoms: also a clean repeat
    if cr and not symptomatic:
        for d in cands:
            if str(d.get("source", "")).startswith("evaluate:glucose") and d.get("tier") == "SUPPRESSED" and d.get("reason") == "unreliable_reading" and any(r[6] == "fingerstick" and r[0] >= cr.get("glucose_clean_min", 70) for r in gl):
                d.update(reason="cleared_by_repeat", default_route="silent_log")
    # ---- v1.11.0 BP cuff clean repeat: flagged / implausible / danger-level SBP + a normal repeat within the window, no symptoms -> silent_log
    if cr and not symptomatic and cr.get("bp_window_min"):
        bp = [r for r in recs(c, "sbp") if r[4] is not None]; hs_ = P["hard_limits"]["sbp"]
        cuff_flag = " ".join(((c.get("data_quality") or {}).get("artifact_flags") or []))
        bad = [r for r in bp if r[2] or re.search(r"deflat\w*|cuff (?:error|flag\w*)|kinked|loose cuff|arm moved|talking during", r[1] + " " + cuff_flag, re.I) and re.search(r"%s" % re.escape(str(r[0])), r[1])
               or not (hs_["implausible_low"] <= r[0] <= hs_["implausible_high"]) or r[0] <= hs_["danger_low"] or r[0] >= hs_["danger_high"]]
        if any(any(0 < r[4] - lo_[4] <= cr["bp_window_min"] * 60 and cr["sbp_clean_low"] <= r[0] <= cr["sbp_clean_high"] and not r[2] for r in bp) for lo_ in bad):
            bp_c = [d for d in cands if str(d.get("source", "")).startswith("evaluate:sbp")]
            if bp_c or bad:
                cands = [d for d in cands if d not in bp_c] + [_dec("HT_VS_DANGER", "SUPPRESSED", "cleared_by_repeat", route=None, default_route="silent_log", source="evaluate:sbp_clean_repeat")]
    # ---- v1.10 insulin user with CKD and a danger-level low: always HITM, floor nurse_task
    ik = T.v110(P).get("insulin_ckd_low"); hitm_required = False
    danger_low = sens or [r for r in gl if r[0] <= gmin]   # CGM or meter at/below the danger limit
    if ik and danger_low and (re.search(ik["insulin_rx"], ctx["meds"], re.I) or (ik.get("sulfonylurea_rx") and re.search(ik["sulfonylurea_rx"], ctx["meds"], re.I))) and re.search(ik["ckd_rx"], ctx["pmh"], re.I):   # v1.10.1: + sulfonylureas
        hitm_required = True
    # ---- v1.11.0 device disagreement / likely device fault (stable patient) -> silent_log + device ticket; could change care -> nurse_task + ticket
    ticket = None; dt = V11.get("device_ticket")
    if dt and not symptomatic and not any(d["tier"] in ("ABSOLUTE", "CONFIRM_FIRST") for d in cands):
        dd = device_disagreement(c, ctx, dt)
        if dd:
            ticket = {"type": dd["ticket"], "interruptive": False, "detail": dd["detail"], "route_to": "device_maintenance_process_else_whoever_can_check_the_device"}
            if dd["changes_care"]: cands.append(_dec("HT_DEVICE_DISAGREE", "SUPPRESSED", "device_disagreement_could_change_care", route=None, default_route="nurse_task"))
            else: cands.append(_dec("HT_DEVICE_DISAGREE", "SUPPRESSED", "device_disagreement", route=None, default_route="silent_log"))
    sc = V11.get("serotonergic_confusion")
    if sc and sc.get("enabled") and re.search(sc["drugs_a_rx"], ctx["meds"], re.I) and re.search(sc["drugs_b_rx"], ctx["meds"], re.I) and find(sc["confusion_rx"], now):
        if find(sc["current_rx"], now): cands.append(_dec("HT_SEROTONERGIC_CONFUSION", "CONFIRM_FIRST", "serotonergic_new_confusion_current", route="urgent_page", confirm_step="patient_call", page="if_confirmed_or_timeout", candidate=True))
        else: cands.append(_dec("HT_SEROTONERGIC_CONFUSION", "SUPPRESSED", "serotonergic_confusion_at_baseline_now", route=None, default_route="provider_task", candidate=True))
    # ---- acute presentation flag (the router lets Jev's clinical read stand on a suppressed trigger when this is set)
    rr0 = [r[0] for r in recs(c, "rr") if not r[2] and not r[8]]; hr0 = [r[0] for r in recs(c, "hr") if not r[2] and r[3] != "active" and not r[8]]
    acute = bool((rr0 and max(rr0) >= 24) or distress or (hr0 and base30.get("rest_hr") and max(hr0) >= base30["rest_hr"] + 20 and find(r"(?:breathless|short of breath)(?![^.;]{0,25}(?:after|walking|climbing|on) (?:the )?(?:stairs|walk|exertion|hill))(?<!after the stairs)", now)))
    V111 = T.v110(P).get("v1111") or {}; ce = V111.get("ckd_low_explained"); gb = V111.get("glucose_lookback")
    def ckd_expl():   # v1.11.1: compression (witness/artifact flag) or recent exertion explains a recovered, asymptomatic CKD low
        if not ce: return None
        if cgm_pressure or re.search(ce["compression_rx"], flags + " " + note + " " + trend, re.I): return "ckd_low_compression_explained"
        if re.search(ce["exertion_rx"], (split_day0(trend)[1] or "") + " " + note, re.I): return "ckd_low_exertion_explained"
        return None
    if gb and ik and drug_lowering and not hitm_required and not symptomatic and re.search(ik["ckd_rx"], ctx["pmh"], re.I) and not any(d.get("rule") == "HT_VS_DANGER" for d in cands):
        days = max(2, -(-gb["lookback_h"] // 24))
        old = [r for r in readings(split_day0(trend)[0], "glucose") if r[7] is not None and -days <= r[7] < -1 and r[0] <= gmin]
        if old:   # v1.11.1: a recent (<= 72 h, placeholder) recovered drug-related CKD low is still a dose review
            cands.append(_dec("HT_VS_DANGER", "SUPPRESSED", "recent_ckd_low_dose_review", route=None, default_route=gb["route"], source=f"lookback:glucose={min(r[0] for r in old)}"))
    if not cands: return {"tier": None, "rule": None, "reason": "no_trigger", "acute_presentation": acute, "hitm_required": hitm_required, "context": {k: ctx[k] for k in ("goals", "lives_alone", "high_risk")}, "candidates": [], **({"device_ticket": ticket} if ticket else {})}
    best = max(cands, key=_rank)
    keep = ("rule", "tier", "reason", "route", "confirm_step", "page", "escalation_target", "notify", "band", "raw_band", "modifiers", "inputs", "source", "goals_basis", "original_tier", "own_low", "explained_by", "confirm_result", "default_route", "foundation", "candidate")
    out = {k: v for k, v in best.items() if k in keep}
    if best.get("stable_angina"): out["stable_angina"] = True   # v1.11.2 PLACEHOLDER rule flag
    if hitm_required and out.get("tier") not in ("ABSOLUTE", "CONFIRM_FIRST"):
        out.update(default_route=ik["route"], hitm_reason="insulin_or_sulfonylurea_ckd_danger_low")
        kd = V11.get("ckd_low_dose_review")   # v1.11.0: cleared, asymptomatic, no documented compression -> prescriber dose review
        if kd and out.get("reason") == "cleared_by_repeat" and str(out.get("source", "")).startswith("evaluate:glucose") and not symptomatic:
            ex = ckd_expl()
            if ex != "ckd_low_compression_explained" and prior_danger_low(c, gmin, kd["prior_low_days"]): out.update(reason="repeated_lows_dose_review", default_route=kd["route"], hitm_floor=kd["route"])   # v1.11.1: a repeat (exertion or unexplained) escalates; repeated compression artifacts stay nurse_task
            elif ex: out.update(reason=ex, default_route=ce["route"], hitm_floor=ce["route"])   # v1.11.1: explained -> nurse_task
            elif not cgm_pressure: out.update(reason="ckd_low_dose_review", default_route=kd["route"], hitm_floor=kd["route"])
    elif drug_lowering and out.get("reason") == "cleared_by_repeat" and V11.get("ckd_low_dose_review") and prior_danger_low(c, gmin, V11["ckd_low_dose_review"]["prior_low_days"]):
        out.update(reason="repeated_lows_dose_review", default_route=V11["ckd_low_dose_review"]["route"])   # v1.11.0: a pattern of lows -> dose review
    if ticket: out["device_ticket"] = ticket
    out["plain_reason"] = plain_reason({**out, "hitm_required": hitm_required}, ctx)
    return {**out, "acute_presentation": acute, "hitm_required": hitm_required, "context": {k: ctx[k] for k in ("goals", "lives_alone", "high_risk")},
            "candidates": [{"rule": d.get("rule"), "tier": d["tier"], "reason": d.get("reason")} for d in cands]}

import layer1_v1141 as V141  # noqa: E402  (v1.14.1 ticket policy: no ticket on clinical routes, internal faults only)
import layer1_v1140 as V14  # noqa: E402  (v1.14.0 named device-fault tickets, ticket only; params layer1_v110.v1140)
import layer1_v1130 as V13  # noqa: E402  (v1.13.0 device-ticket emission; params layer1_v110.v1130)
import layer1_v1120 as V12  # noqa: E402  (v1.12.0 generalized wording/matching; params layer1_v110.v1120)
def evaluate_case(case):
    """v1.13.0 decision, then the v1.14.0 named device-fault tickets (ticket only; no-op when layer1_v110.v1140.enabled is false)."""
    out = _evaluate_v1112(case); c = facts_only(case); ctx = context(c)
    o14 = V14.apply(case, c, _evaluate_v1130(case), out, ctx, sys.modules[__name__], T, PARAMS, V13)
    return V141.apply(c, o14, sys.modules[__name__], T, PARAMS, V14)   # v1.14.1 ticket policy (Wayne 2026-10-24; no-op when layer1_v110.v1141.enabled is false)
def _evaluate_v1130(case):
    """v1.11.2 decision, then the v1.12.0 generalized rules (no-op when layer1_v110.v1120.enabled is false)."""
    out = _evaluate_v1112(case)
    c = facts_only(case); ctx = context(c)
    new = V12.apply(case, c, out, ctx, sys.modules[__name__], T, PARAMS)
    if new is out: return V13.apply(case, c, out, ctx, sys.modules[__name__], T, PARAMS, V12)   # v1.13.0 device tickets (stable patient)
    if route(out, None)[0] == new.get("owned_route") and not (new.get("device_ticket") and not out.get("device_ticket")) and out.get("tier") and not (out.get("hitm_required") and new.get("owned_route") == "provider_task" and out.get("reason") != new.get("reason")):
        return out   # v1.12.0 agrees with the v1.11.2 route: keep the v1.11.2 decision (reason, owner, HITM floor)
    new = dict(new); new["v1112_decision"] = {k: out.get(k) for k in ("rule", "tier", "reason")}
    new["plain_reason"] = plain_reason({**new, "hitm_required": new.get("hitm_required") and new.get("owned_route") != "nurse_task" and "dose" not in (new.get("reason") or "")}, ctx)
    return new

def _params():
    for p in (os.path.join(HERE, "..", "trigger_engine", "trigger_params.json"), "/workspace/jevfly_smoke/casegen/trigger_engine/trigger_params.json"):
        if os.path.exists(p): return T.load_params(p)
PARAMS = _params()

# ---- Layer 1 + Jev router (Wayne 2026-10-18): Layer 1 owns triggers; Jev decides non-trigger cases and, within limits, suppressed ones
CAP = dict(RT.RANK)
def route(l1, jev_pick):
    """Returns (route, owner). ABSOLUTE -> escalate (hospice-aware target in l1['escalation_target']); CONFIRM_FIRST -> confirm step,
    paged on confirmation or timeout (offline: no confirm result, so urgent_page; a refuting result would hand back to Jev);
    SUPPRESSED goals_of_care -> nurse_task (same-shift hospice nurse); other SUPPRESSED/ARTIFACT/below-band -> Jev, capped at
    provider_task unless Layer 1 flags an acute presentation (below_band floor nurse_task); no trigger -> Jev."""
    jev_pick = RT.canon(jev_pick)   # v1.9: a stored v1.8 pick (wake_specialist / escalate_human) is mapped on read
    t = l1.get("tier")
    if l1.get("owned_route") and l1.get("floor_only"):   # v1.12.0 floor (e.g. gap partly explained): at least the owned route, Jev may raise it
        rk = {"silent_log": 0, "nurse_task": 1, "provider_task": 2, "urgent_page": 3}
        return (jev_pick, "jev_v1120_floor") if jev_pick in rk and rk[jev_pick] > rk[l1["owned_route"]] else (l1["owned_route"], "jev_v1120_floor")
    if l1.get("owned_route") and (l1["owned_route"] == "urgent_page" or not l1.get("acute_presentation")):   # v1.12.0: Layer 1 owns this route
        return l1["owned_route"], "layer1_v1120"
    if t == "ABSOLUTE": return "urgent_page", "layer1"
    if t == "CONFIRM_FIRST": return "urgent_page", "layer1_confirm"
    if t == "SUPPRESSED" and l1.get("reason") == "goals_of_care": return "nurse_task", "layer1_goals"
    if t in ("SUPPRESSED", "ARTIFACT"):
        # v1.10: derive the route per rule (no blanket provider_task fallback); a cleared artifact is silent; insulin+CKD lows floor nurse_task
        if l1.get("reason") == "cleared_by_repeat" and not l1.get("hitm_required") and not l1.get("acute_presentation"): return "silent_log", "layer1_cleared"
        if l1.get("stable_angina") and not l1.get("acute_presentation") and ((T.v110(PARAMS).get("v1112") or {}).get("stable_angina_owner") or {}).get("enabled"):
            return "nurse_task", "layer1_stable_angina"
        if l1.get("rule") == "HT_DEVICE_DISAGREE" and not l1.get("acute_presentation") and ((T.v110(PARAMS).get("v1112") or {}).get("device_ticket_owner") or {}).get("enabled"):
            return l1["default_route"], "layer1_device_ticket"   # v1.11.2: Layer 1 owns device-disagreement routes; Jev is not consulted
        floor = (l1.get("hitm_floor") or "nurse_task") if l1.get("hitm_required") else T.route_floor(l1, PARAMS)
        if jev_pick is None:
            p = T.suppressed_default_route(l1, PARAMS)
            if floor and CAP[p] < CAP[floor]: p = floor
            return p, "layer1_default"
        p = jev_pick
        if p == "urgent_page" and not l1.get("acute_presentation"): p = "provider_task"
        if l1.get("reason") == "below_band_threshold" and CAP[p] < 1: p = "nurse_task"
        if floor and CAP[p] < CAP[floor]: p = floor
        return p, "jev_capped"
    if l1.get("hitm_required") and jev_pick is not None and CAP[jev_pick] < CAP["nurse_task"]: return "nurse_task", "jev_hitm_floor"
    return jev_pick, "jev"
