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
               "baseline_30d", "baseline_status", "trend_last_7d", "caregiver_or_nurse_note", "data_quality", "skin_tone_note")
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

def _dec(rule, tier, reason=None, **kw): return {"rule": rule, "tier": tier, "reason": reason, **kw}
RANK = {"ABSOLUTE": 5, "CONFIRM_FIRST": 4, "SUPPRESSED_goals": 3, "SUPPRESSED": 2, "LOG_ONLY": 2, "ARTIFACT": 1}
def _rank(d): return RANK["SUPPRESSED_goals"] if d["tier"] == "SUPPRESSED" and d.get("reason") == "goals_of_care" else RANK.get(d["tier"], 0)

def evaluate_case(case):
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
            cands.append({**d, "source": "chest_pain", "inputs": {"activity": act, "mse": mse, "vitals": vit, "red_flags": rf, "ecg_change": sym["ecg_change"], "ecg_reliable": sym["ecg_reliable"], "rate_control": ctx["rate_control_med"]}})
    # ---- 5. fall on an anticoagulant
    FALL = r"\bimpact\b|\bfell\b|\bfall(?:en)?\b(?! risk)|found (?:him|her) on|on the (?:\w+ )?floor|slipp\w*|sat down hard|went down|go down|tripped|lost (?:his|her) footing"
    if ctx["anticoag"] and find(FALL, now):
        confirmed = any(find(r"\bfell\b|slipp?\w*|\bslip\b|sat down hard|found (?:him|her) on (?:the )?floor|on the (?:\w+ )?floor|tripped|went down|go down|had a fall|fallen", x)
                        and not re.search(r"\b(?:watch|band|device|phone|ring)\b[^.;]{0,40}\bfloor\b|\bfloor\b[^.;]{0,25}\b(?:watch|band|device)\b", x, re.I) for x in sentences(note))
        cg_check = (not confirmed) and find(r"checked (?:on )?(?:him|her)|went to (?:check|see)|found (?:him|her) (?:walking|sitting|standing|in bed|well|fine)|(?:she|he) (?:was|is) (?:walking|fine|well|pain-?free)|pain-?free|(?:did not|didn't|denies having) fall\w*|no (?:sign of a )?fall|no injur\w*", note, neg=False)
        fA = (T.v110(P).get("fall_anticoag") or {}).get("confirmed_tier", "CONFIRM_FIRST")
        if find(r"dropped (?:the |his |her )?(?:watch|band)|watch (?:fell|slid|dropped|clatter\w*|came off)|clatter\w*|caught (?:herself|himself)|stayed on (?:her|his) feet|near[- ]fall|knocked (?:the|her|his) (?:watch|wrist)", now, neg=False):
            cands.append(_dec("HT_FALL_ANTICOAG", "SUPPRESSED", "explained", route=None))
        elif cg_check and not find(r"\bfell\b|had a fall|fallen", note):   # v1.10: unwitnessed possible fall cleared by a caregiver check -> nurse confirms no fall
            cands.append(_dec("HT_FALL_ANTICOAG", "SUPPRESSED", "explained_caregiver_check", route=None, explained_by=cg_check.group(0)))
        elif not confirmed and find(r"off[- ]wrist|on (?:the )?(?:bedside )?charger|charging|not on (?:the|her|his) wrist", day0):
            cands.append(_dec("HT_FALL_ANTICOAG", "SUPPRESSED", "unreliable_reading", route=None))
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
            if not rel or (tips and min(t[0] for t in tips) >= 92):
                cands.append(_dec("HT_SPO2_LT88", "SUPPRESSED", "unreliable_reading", route=None))
            elif own is not None and min(r[0] for r in rel) >= own:
                cands.append(_dec("HT_SPO2_LT88", "SUPPRESSED", "at_patient_baseline", route=None, own_low=own))
            else:
                conf = any(t[0] < thr for t in tips) and len(rel) >= 1 and any(r[6] == "fingertip" for r in rel)
                d = _dec("HT_SPO2_LT88", "CONFIRM_FIRST", "below_88_change_from_own_baseline", route="urgent_page", confirm_step="already_confirmed" if conf else "fingertip_recheck", page=True if conf else "if_confirmed_or_timeout", own_low=own)
                basis = T.urgent_comfort_basis({"vital": "spo2", "value": min(r[0] for r in rel)}, None, P, {**ectx, "breathlessness": breath, "trigger_family": "respiratory"})
                cands.append(T.apply_goals_of_care(d, P, ectx, basis))
    # ---- 7. 48 h data gap in a high-risk patient
    dq = c.get("data_quality") or {}
    if (dq.get("longest_gap_h") or 0) >= 48 and ctx["high_risk"]:
        gs = re.search(r"(?:offline|no [\w ,]*data|data[\w ,]* (?:run|ran|stop\w*)[\w ]* to|last [\w ]*sync|from)\s*(?:from\s*)?Day (-\d+)(?:\s+(\d{1,2}):(\d{2}))?", flags + " ; " + trend, re.I)
        g_day = int(gs.group(1)) if gs else None; g_min = (int(gs.group(2)) * 60 + int(gs.group(3))) if (gs and gs.group(2)) else 0
        contact = None
        for x in sentences(note + " " + trend):
            m = re.search(r"Day (-?\d+)\s*(?:at\s*)?(\d{1,2}):(\d{2})", x)
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
            rep = [r for r in sp if r[4] > lo_[4] and r[4] - lo_[4] <= cr["window_min"] * 60 and r[0] >= cr["spo2_clean_min"] and not r[2]
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
    # ---- v1.10 insulin user with CKD and a danger-level low: always HITM, floor nurse_task
    ik = T.v110(P).get("insulin_ckd_low"); hitm_required = False
    danger_low = sens or [r for r in gl if r[0] <= gmin]   # CGM or meter at/below the danger limit
    if ik and danger_low and (re.search(ik["insulin_rx"], ctx["meds"], re.I) or (ik.get("sulfonylurea_rx") and re.search(ik["sulfonylurea_rx"], ctx["meds"], re.I))) and re.search(ik["ckd_rx"], ctx["pmh"], re.I):   # v1.10.1: + sulfonylureas
        hitm_required = True
    # ---- acute presentation flag (the router lets Jev's clinical read stand on a suppressed trigger when this is set)
    rr0 = [r[0] for r in recs(c, "rr") if not r[2] and not r[8]]; hr0 = [r[0] for r in recs(c, "hr") if not r[2] and r[3] != "active" and not r[8]]
    acute = bool((rr0 and max(rr0) >= 24) or distress or (hr0 and base30.get("rest_hr") and max(hr0) >= base30["rest_hr"] + 20 and find(r"(?:breathless|short of breath)(?![^.;]{0,25}(?:after|walking|climbing|on) (?:the )?(?:stairs|walk|exertion|hill))(?<!after the stairs)", now)))
    if not cands: return {"tier": None, "rule": None, "reason": "no_trigger", "acute_presentation": acute, "hitm_required": hitm_required, "context": {k: ctx[k] for k in ("goals", "lives_alone", "high_risk")}, "candidates": []}
    best = max(cands, key=_rank)
    keep = ("rule", "tier", "reason", "route", "confirm_step", "page", "escalation_target", "notify", "band", "raw_band", "modifiers", "inputs", "source", "goals_basis", "original_tier", "own_low", "explained_by", "confirm_result", "default_route")
    out = {k: v for k, v in best.items() if k in keep}
    if hitm_required and out.get("tier") not in ("ABSOLUTE", "CONFIRM_FIRST"): out.update(default_route=ik["route"], hitm_reason="insulin_or_sulfonylurea_ckd_danger_low")
    return {**out, "acute_presentation": acute, "hitm_required": hitm_required, "context": {k: ctx[k] for k in ("goals", "lives_alone", "high_risk")},
            "candidates": [{"rule": d.get("rule"), "tier": d["tier"], "reason": d.get("reason")} for d in cands]}

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
    if t == "ABSOLUTE": return "urgent_page", "layer1"
    if t == "CONFIRM_FIRST": return "urgent_page", "layer1_confirm"
    if t == "SUPPRESSED" and l1.get("reason") == "goals_of_care": return "nurse_task", "layer1_goals"
    if t in ("SUPPRESSED", "ARTIFACT"):
        # v1.10: derive the route per rule (no blanket provider_task fallback); a cleared artifact is silent; insulin+CKD lows floor nurse_task
        if l1.get("reason") == "cleared_by_repeat" and not l1.get("hitm_required") and not l1.get("acute_presentation"): return "silent_log", "layer1_cleared"
        floor = "nurse_task" if l1.get("hitm_required") else T.route_floor(l1, PARAMS)
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
