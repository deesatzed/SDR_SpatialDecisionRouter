"""Derive per-day Fly inputs (latent, repeated, verified) from structured case FACT fields + Layer 1 only.

Never reads labels (expected_route, acceptable_alternates, trigger_tier, hard_trigger*, rationale, ...): the case is
passed through layer1_adapter.facts_only() first. All cut-offs below are fixed a priori (not tuned on labels).
"""
from __future__ import annotations
import os, re, sys, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("JEV_BASELINE_DIR", os.path.join(HERE, "..", "jev_baseline")))
import layer1_adapter as L  # noqa: E402

DAYS = tuple(range(-7, 1))          # 8 daily steps, Day -7 .. Day 0
CUT = {"hr_dev": 15, "spo2_drop": 3, "spo2_floor": 90, "rr_high": 22, "rr_rise": 4, "sbp_dev": 25, "sbp_low": 95,
       "temp_high": 37.8, "glucose_low": 70, "glucose_high": 300, "steps_frac": 0.5, "weight_gain_kg": 1.5,
       "gap_hours_48": 12}
SYMPTOMS = (r"breathless\w*|short of breath|out of breath|can'?t catch|chest (?:pain|tight\w*|pressure)|confus\w*|dizz\w*|"
            r"\bfell\b|\bfall\b|slipped|faint\w*|drowsy|swollen|swelling|vomit\w*|not eating|off (?:her|his) food|"
            r"weak\w*|cough\w*|fever\w*|sweat\w*|clammy|slurred|palpitation\w*|unsteady|pain\w*")

def _day_vals(text, rx, after=False):
    """[(value, day)] for regex rx; value attributed to the Day N reference before it (or right after it if after=True)."""
    out, cur = [], None
    for s in L.sentences(text or ""):
        refs = [(m.start(), m.end(), int(m.group(2) or m.group(1))) for m in L.DAYREF.finditer(s)]
        for m in re.finditer(rx, s, re.I):
            g = [x for x in m.groups() if x]
            v = min(float(x.replace(",", "")) for x in g)
            day = None
            if after:
                nxt = [d for st, en, d in refs if 0 <= st - m.end() <= 12]
                day = nxt[0] if nxt else None
            if day is None:
                prev = [d for st, en, d in refs if st <= m.start()]
                day = prev[-1] if prev else cur
            out.append((v, day))
        if refs: cur = refs[-1][2]
    return out

def _base(own, early):
    if own is not None: return own
    return statistics.median(early) if early else None

def derive_flags(case):
    """Return {'days': [{'day', 'latent', 'repeated', 'verified', 'why'}], 'l1': {...}} from facts + Layer 1 only."""
    c = L.facts_only(case); l1 = L.evaluate_case(case)
    b30 = c.get("baseline_30d") or {}; dq = c.get("data_quality") or {}
    trend = c.get("trend_last_7d") or ""; note = c.get("caregiver_or_nurse_note") or ""
    why = {d: [] for d in DAYS}
    def mark(day, tag):
        if day is not None and day in why and tag not in why[day]: why[day].append(tag)
    def reads(v):
        return [(r[0], r[7]) for r in L.readings(trend, v) + L.readings(note, v, default_day=0)
                if not r[2] and r[3] != "active" and r[7] is not None]
    def early(rs): return [x for x, d in rs if d <= -4]
    hr = reads("hr"); hb = _base(b30.get("rest_hr"), early(hr))
    for x, d in hr:
        if hb is not None and abs(x - hb) >= CUT["hr_dev"]: mark(d, "hr")
    sp = reads("spo2"); sb = _base(b30.get("spo2_night_min"), early(sp))
    for x, d in sp:
        if x < CUT["spo2_floor"] or (sb is not None and x <= sb - CUT["spo2_drop"]): mark(d, "spo2")
    rr = reads("rr"); rb = _base(None, early(rr))
    for x, d in rr:
        if x >= CUT["rr_high"] or (rb is not None and x >= rb + CUT["rr_rise"]): mark(d, "rr")
    bp = reads("sbp"); bb = _base(b30.get("sbp"), early(bp))
    for x, d in bp:
        if x < CUT["sbp_low"] or (bb is not None and abs(x - bb) >= CUT["sbp_dev"]): mark(d, "sbp")
    for x, d in reads("temp_c"):
        if x >= CUT["temp_high"]: mark(d, "temp")
    for x, d in reads("glucose"):
        if x < CUT["glucose_low"] or x > CUT["glucose_high"]: mark(d, "glucose")
    steps = _day_vals(trend, r"steps\s*(\d[\d,]*)(?:\s*[-–]\s*(\d[\d,]*))?|(\d[\d,]{2,})\s*steps")
    stb = _base(b30.get("steps"), [x for x, d in steps if d is not None and d <= -4])
    for x, d in steps:
        if stb and d is not None and d > -4 and x <= CUT["steps_frac"] * stb: mark(d, "steps")
    wt = [(x, d) for x, d in _day_vals(trend, r"(\d{2,3}(?:\.\d)?)\s*kg", after=True) if d is not None]
    if wt:
        w0 = _base(b30.get("weight_kg"), [x for x, d in wt if d == min(dd for _, dd in wt)])
        for x, d in wt:
            if w0 is not None and x - w0 >= CUT["weight_gain_kg"]: mark(d, "weight")
    if (dq.get("missing_hours_last_48") or 0) >= CUT["gap_hours_48"]: mark(-1, "data_gap"); mark(0, "data_gap")
    if L.find(SYMPTOMS, note) or L.find(SYMPTOMS, L.split_day0(trend)[1]): mark(0, "symptom")
    tier = l1.get("tier")
    if tier == "CONFIRM_FIRST": mark(0, "l1_confirm_first")
    verified0 = tier == "ABSOLUTE" or l1.get("original_tier") == "ABSOLUTE"
    days, prev = [], False
    for d in DAYS:
        lat = bool(why[d])
        days.append({"day": d, "latent": lat, "repeated": lat and prev, "verified": bool(d == 0 and verified0), "why": why[d]})
        prev = lat
    return {"days": days, "l1": {"tier": tier, "reason": l1.get("reason"), "rule": l1.get("rule"),
                                 "acute_presentation": l1.get("acute_presentation")}}
