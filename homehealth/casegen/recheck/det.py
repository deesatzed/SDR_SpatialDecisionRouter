"""Deterministic screen of non-trigger cases with trigger_eval (SYNTHETIC). Readings are regex-extracted from trend/note text and tagged with the
nearest preceding 'Day N' marker. Only the last 48 h (Day -1, Day 0) count as current. Scored layers: hard limits (implausible -> ARTIFACT,
danger -> ABSOLUTE, quality-flagged crossing -> SUPPRESSED unreliable_reading), SpO2 < 88 (rule fires; the tier needs a baseline judgement, so it is left to the model),
gap >= 48 h (rule candidate) and chest pain (evaluate_chest_pain). Other rules (fall, syncope, focal neuro) are not deterministically scorable."""
import json, re, sys
sys.path.insert(0, "../../../casegen/trigger_engine"); import trigger_eval as T
P = T.load_params("../../../casegen/trigger_engine/trigger_params.json")
QW = re.compile(r"compression|lying on (the|her|his) (sensor|arm)|sensor (warm|error|fault)|poor[- ]contact|motion|loose|off[- ]wrist|artifact|cold (hands|fingers)|low perfusion|nail polish|dropout|charging|charger", re.I)
DAYM = re.compile(r"Day\s*(-?\d+)(?:\s*(?:to|-|–)\s*(?:Day\s*)?(-?\d+))?", re.I)
PATS = {
 "spo2": re.compile(r"SpO2[^0-9;.]{0,30}?(\d{2,3})(?:\s*[-–]\s*(\d{2,3}))?\s*%", re.I),
 "hr": re.compile(r"\bHR\b[^0-9;.]{0,25}?(\d{2,3})(?:\s*[-–]\s*(\d{2,3}))?", re.I),
 "rr": re.compile(r"\bRR\b[^0-9;.]{0,15}?(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?", re.I),
 "sbp": re.compile(r"(?<![\d/])(\d{2,3})/\d{2,3}(?![\d/])"),
 "sbp_word": re.compile(r"\bSBP\b[^0-9;.]{0,15}?(\d{2,3})(?:\s*[-–]\s*(\d{2,3}))?", re.I),
 "glucose_mmol": re.compile(r"(?:CGM|glucose|glucometer|finger[- ]?stick|capillary|BG)[^;]{0,40}?\b(\d{1,2}\.\d)(?:\s*[-–]\s*(\d{1,2}\.\d))?\s*mmol", re.I),
 "temp_c": re.compile(r"(?:temp(?:erature)?|tympanic|oral)[^0-9;.]{0,20}?(3\d\.\d)\s*(?:°\s*)?C", re.I),
}
CHEST = re.compile(r"chest (pain|pressure|tight\w*|discomfort|squeez\w*|heaviness)|tightness across|the squeeze", re.I)
NEG = re.compile(r"\b(no|denies|without|nor|not)\b[^.;]{0,25}$", re.I)
GLU_NUM = re.compile(r"(?<![\d.])(\d{2,3})(?:\s*[-–]\s*(\d{2,3}))?\s*mg/dL", re.I)
GLU_KEY = re.compile(r"\b(CGM|sensor|glucometer|finger[- ]?sticks?|capillary|meter|BG|glucose|creatinine|urea|BUN|calcium|cholesterol|LDL|triglycerides?)\b", re.I)
FS_WORDS = ("glucometer", "fingerstick", "finger-stick", "finger stick", "fingersticks", "capillary", "meter", "bg")
PRESSURE = re.compile(r"(pinned|pressed|compress\w*|squashed|lying on|sleeping on|sat under|under (the )?(bed ?rail|body|arm|pillow))[^.;]{0,40}sensor|sensor[^.;]{0,40}(pinned|pressed|compress\w*|squashed|under (the )?(bed ?rail|body|arm|pillow)|on (his|her|the) sleeping side)", re.I)
REBOUND = re.compile(r"rebound\w*|bounced back|back (up )?to \d{2,3} mg/dL within \d+ ?min|recovered within \d+ ?min without treatment", re.I)
SYMPT = re.compile(r"sweat\w*|clammy|shak(y|ing|es)|tremor\w*|confus\w*|drows\w*|hard to rouse|responding only|unresponsive|seizure", re.I)
SNEG = re.compile(r"\b(no|not|denies|without|nor)\b[^.;]{0,30}$", re.I)
TIME = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")
def _clause(text, i, j):
    a = max(text.rfind(";", 0, i), text.rfind(". ", 0, i)); b = [x for x in (text.find(";", j), text.find(". ", j)) if x != -1]
    return a + 1, (min(b) if b else len(text))
def _day_at(marks, pos):
    day = None
    for p_, d in marks:
        if p_ <= pos: day = d
    return day
def glucose_readings(text, marks):
    """All mg/dL glucose numbers, with source (cgm / fingerstick / None) from the nearest preceding keyword, day, clause time and overnight flag."""
    out = []
    for m in GLU_NUM.finditer(text):
        keys = [k for k in GLU_KEY.finditer(text, max(0, m.start() - 90), m.start())]
        if not keys: continue
        k = keys[-1].group(1).lower()
        if k in ("creatinine", "urea", "bun", "calcium", "cholesterol", "ldl", "triglyceride", "triglycerides"): continue
        src = "cgm" if k in ("cgm", "sensor") else "fingerstick" if k in FS_WORDS else ("cgm" if re.search(r"CGM", text[max(0, m.start() - 90):m.start()]) else None)
        a, b = _clause(text, m.start(), m.end()); cl = text[a:b]
        tms = [int(t.group(1)) * 60 + int(t.group(2)) for t in TIME.finditer(cl)]; hh = tms[0] if tms else None
        rng = (min(tms), max(tms)) if tms else None   # an episode window like "between 01:40 and 03:20"
        night = (hh is not None and (hh >= 22 * 60 or hh < 7 * 60)) or bool(re.search(r"night|nocturnal|overnight", cl, re.I))
        for g in m.groups():
            if g: out.append({"vital": "glucose", "value": float(g), "source": src, "day": _day_at(marks, m.start(1)), "min_of_day": hh, "time_range": rng, "overnight": night, "quality_flags": [], "quote": cl.strip()[:160]})
    return out
def symptoms_by_day(text, marks):
    days = set()
    for m in SYMPT.finditer(text):
        a, _ = _clause(text, m.start(), m.end())
        if SNEG.search(text[a:m.start()]) or re.search(r"no symptoms", text[a:m.start() + 20], re.I): continue
        days.add(_day_at(marks, m.start()))
    return days

def readings(text):
    out = []
    marks = [(m.start(), int(m.group(2) or m.group(1))) for m in DAYM.finditer(text)]
    for v, pat in PATS.items():
        for m in pat.finditer(text):
            day = None
            for pos, d in marks:
                if pos <= m.start(): day = d
            s0 = max(text.rfind(";", 0, m.start()), text.rfind(". ", 0, m.start())); s1 = min([x for x in (text.find(";", m.end()), text.find(". ", m.end())) if x != -1] or [len(text)])
            sent = text[s0 + 1:s1]
            for g in m.groups():
                if not g: continue
                x = float(g); vv = v
                if v == "glucose_mmol": x, vv = round(x * 18), "glucose"
                if v == "sbp_word": vv = "sbp"
                if vv == "sbp" and not (60 <= x <= 260): continue
                out.append({"vital": vv, "value": x, "day": day, "quality_flags": ["poor_contact"] if QW.search(sent) else [], "quote": sent.strip()[:160]})
    return out + glucose_readings(text, marks)
def chest(text):
    hits = []
    for m in CHEST.finditer(text):
        if not NEG.search(text[max(0, m.start() - 40):m.start()]): hits.append(m.group(0))
    return hits
def screen(c):
    text = (c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or "") + " Data quality: " + "; ".join((c.get("data_quality") or {}).get("artifact_flags") or []) + "."
    marks = [(m.start(), int(m.group(2) or m.group(1))) for m in DAYM.finditer(text)]
    pressure = bool(PRESSURE.search(text)); rebound = bool(REBOUND.search(text)); symp_days = symptoms_by_day(text, marks)
    rs = readings(text); cur = [r for r in rs if r["day"] is not None and r["day"] >= -1]
    goals = "comfort_only" if re.search(r"comfort|hospice|palliative|no (hospital|transfer)", json.dumps(c.get("patient_goals") or ""), re.I) else None
    found = []
    base = T.Baseline(c["case_id"], 0.0, P)
    for r in cur:
        rr = {"vital": r["vital"], "value": r["value"], "ts": 99 * 86400.0, "activity_state": "rest", "quality_flags": r["quality_flags"]}
        if r["vital"] == "glucose" and r.get("source") == "cgm":
            fss = [f for f in rs if f["vital"] == "glucose" and f.get("source") == "fingerstick" and f["day"] == r["day"]]
            def gap(f):
                if f.get("min_of_day") is None or not r.get("time_range"): return None
                lo, hi = r["time_range"]; t = f["min_of_day"]
                return 0 if lo <= t <= hi else min(abs(t - lo), abs(t - hi))
            fss.sort(key=lambda f: (gap(f) is None, gap(f) or 0))
            fs = {"value": fss[0]["value"], "minutes_apart": gap(fss[0])} if fss else None
            rr.update(source="cgm", cgm={"overnight": r["overnight"], "pressure_documented": pressure, "sensor_side_sleep": False, "drop_rebound": rebound, "fingerstick": fs, "symptoms": r["day"] in symp_days})
        d = T.evaluate(rr, base, P, {"goals": goals})
        if d["rule"] in ("HT_VS_DANGER", "HT_VS_IMPLAUSIBLE") and (d["tier"] in ("ABSOLUTE", "ARTIFACT", "SUPPRESSED")):   # hard-limit layer only; baseline layer needs learned state
            found.append({"rule": d["rule"], "tier": d["tier"], "reason": d["reason"], "vital": r["vital"], "value": r["value"], "day": r["day"], "quote": r["quote"], "source": r.get("source"), "cgm": rr.get("cgm"), "basis": d.get("basis"), "cgm_signs": d.get("cgm_signs")})
        elif r["vital"] == "spo2" and r["value"] < P["confirm_first"]["spo2_population_threshold"]:
            found.append({"rule": "HT_SPO2_LT88", "tier": "NEEDS_BASELINE_JUDGEMENT", "reason": "spo2_below_88", "vital": "spo2", "value": r["value"], "day": r["day"], "quote": r["quote"]})
    past = [r for r in rs if r["day"] is not None and r["day"] < -1 and (lambda h: (h["danger_low"] is not None and r["value"] <= h["danger_low"]) or (h["danger_high"] is not None and r["value"] >= h["danger_high"]))(P["hard_limits"][r["vital"]])]
    gap = (c.get("data_quality") or {}).get("longest_gap_h") or 0
    if gap >= 48: found.append({"rule": "HT_GAP48_HIGHRISK", "tier": "NEEDS_RISK_JUDGEMENT", "reason": f"longest_gap_h {gap}"})
    ch = chest(text); cp = None
    if ch:
        def mx(v, f): xs = [r["value"] for r in rs if r["vital"] == v and r["day"] is not None and r["day"] >= 0 and not r["quality_flags"]]; return f(xs) if xs else None   # episode day only
        vit = {k: {"value": x} for k, x in (("hr", mx("hr", max)), ("sbp", mx("sbp", min)), ("spo2", mx("spo2", min))) if x is not None}
        rf = [n for n, p in (("crescendo_pattern", r"more often|more frequent|increasing|fourth episode|rising from|three episodes|getting worse"), ("diaphoresis", r"sweat|clammy"), ("dyspnea", r"short of breath|breathless"), ("pallor", r"\bpale\b|grey"), ("radiation", r"jaw|left arm|down (his|her) arm")) if re.search(p, text, re.I)]
        act = "active" if re.search(r"walk|stairs|climb|uphill|carrying|exert", text, re.I) else "rest"
        cp = T.evaluate_chest_pain({"ts": 0.0, "activity_state": act, "minutes_since_exertion": 0 if act == "active" else None, "vitals": vit,
                                    "symptoms": {"chest_pain": True, "severity": "moderate", "red_flags": rf, "concordant": None, "ecg_change": bool(re.search(r"ST[- ]segment (depression|elevation)|ST (depression|elevation)", text)) and not re.search(r"without ST|no ST", text)},
                                    "already_confirmed": False}, P, context={"rate_control_med": any(re.search(r"olol|diltiazem|verapamil|digoxin", m["name"], re.I) for m in c.get("meds") or []), "goals": goals})
        if cp: found.append({"rule": cp["rule"], "tier": cp["tier"], "reason": cp.get("reason"), "band": cp.get("band"), "raw_band": cp.get("raw_band"), "modifiers": cp.get("modifiers"), "confirm_step": cp.get("confirm_step"), "timeout_min": cp.get("timeout_min"), "chest_terms": ch, "inputs": {"vitals": vit, "red_flags": rf, "activity": act}})
    return {"case_id": c["case_id"], "n_readings": len(rs), "n_current": len(cur), "scoreable": len(cur) > 0 or bool(ch), "goals": goals, "det_findings": found,
            "past_hard_limit": [{k: r[k] for k in ("vital", "value", "day", "quote")} for r in past]}
if __name__ == "__main__":
    L = json.load(open("../pre_recheck/library_v2_smart_accepted.json"))["cases"]   # recheck scope = pre-recheck non-trigger set
    nt = [c for c in L if not c.get("hard_trigger")]
    out = [screen(c) for c in nt]
    json.dump({"n": len(out), "params_version": P["version"], "results": out}, open("det_results.json", "w"), indent=1)
    import collections
    print("non-trigger cases:", len(nt), "| scoreable:", sum(o["scoreable"] for o in out), "| with findings:", sum(bool(o["det_findings"]) for o in out), "| past hard-limit:", sum(bool(o["past_hard_limit"]) for o in out))
    print(collections.Counter((f["rule"], f["tier"], f.get("reason")) for o in out for f in o["det_findings"]))
    for o in out:
        if o["det_findings"] or o["past_hard_limit"]: print(o["case_id"], [(f["rule"], f["tier"], f.get("value"), f.get("day"), f.get("band")) for f in o["det_findings"]], "| past:", [(p["vital"], p["value"], p["day"]) for p in o["past_hard_limit"]])
