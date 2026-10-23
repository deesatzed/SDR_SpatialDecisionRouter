"""v1.10 Jev prompt (v1.11.2, 2026-10-23): computed 7-day trend summary (direction + size) for HR, RR, weight, steps and SpO2.
Pure text arithmetic over the case's own trend sentences; no labels, no route words. Thresholds below are PLACEHOLDERS (not clinically validated)."""
import re
import layer1_adapter as L
FLAT = {"HR": 5, "RR": 2, "weight": 1.0, "SpO2": 2}   # PLACEHOLDER absolute change below which the trend is called flat
STEPS_FLAT_PCT = 20                                     # PLACEHOLDER relative change for steps
UNIT = {"HR": " bpm", "RR": "/min", "weight": " kg", "SpO2": " points", "steps": ""}
def _series(text):
    s = {"HR": [(r[7], r[0]) for r in L.readings(text, "hr") if not r[2] and r[7] is not None],
         "RR": [(r[7], r[0]) for r in L.readings(text, "rr") if not r[2] and r[7] is not None],
         "SpO2": [(r[7], r[0]) for r in L.readings(text, "spo2") if not r[2] and r[7] is not None], "weight": [], "steps": []}
    cur = None
    for sent in re.split(r"(?<=[.;])\s+", text or ""):
        for part in re.split(r"(?=\bDays?\s+-?\d)", sent):
            m = L.DAYREF.search(part)
            if m: cur = int(m.group(2) or m.group(1))
            if cur is None: continue
            for w in re.finditer(r"\bweight\s*(?:of\s*)?(\d{2,3}(?:\.\d)?)", part, re.I): s["weight"].append((cur, float(w.group(1))))
            for st in re.finditer(r"\bsteps?\s*(?:of\s*)?(\d{1,3}(?:,\d{3})+|\d{3,6})\b|\b(\d{1,3}(?:,\d{3})+|\d{3,6})\s*steps\b", part, re.I): s["steps"].append((cur, int((st.group(1) or st.group(2)).replace(",", ""))))
    return s
def summary(text):
    """'Computed 7-day trend (earliest -> latest reading): ...' or None when no vital has readings on two different days."""
    out = []
    for k, ser in _series(text).items():
        days = sorted({d for d, _ in ser})
        if len(days) < 2: continue
        first = [v for d, v in ser if d == days[0]]; last = [v for d, v in ser if d == days[-1]]
        a, b = sum(first) / len(first), sum(last) / len(last); delta = b - a
        flat = abs(delta) < (abs(a) * STEPS_FLAT_PCT / 100 if k == "steps" else FLAT[k])
        dirn = "flat" if flat else ("rising" if delta > 0 else "falling")
        fmt = (lambda x: f"{x:.1f}") if k == "weight" else (lambda x: f"{x:.0f}")
        size = f"{100 * delta / a:+.0f}%" if k == "steps" and a else f"{'+' if delta >= 0 else ''}{fmt(delta)}{UNIT[k]}"
        out.append(f"{k} {fmt(a)} to {fmt(b)} ({size}, {dirn}, Day {days[0]} to Day {days[-1]})")
    return ("Computed 7-day trend (earliest vs latest reading): " + "; ".join(out) + ".") if out else None
