"""SMART_TRIGGERS v1.13.0 Layer 1 device-ticket emission (params layer1_v110.v1130; every number is a PLACEHOLDER).
Built ONLY from library_expansion_v1 ticket cases (LX1-003, LX1-004, LX2-*, LX7-003), the original library and hand-written
synthetic vignettes (test_layer1_v1130.py). holdout_v3/holdout_v4 case text was NOT read while designing these rules.
Patterns (stable patient only: no symptoms, no acute words, no ABSOLUTE/CONFIRM_FIRST trigger):
  A. activity_artifact: a step/activity stream moves >= steps_change_ratio from baseline while either a second activity
     device stays flat, a firmware/update/re-pair flag precedes the change, or the patient/caregiver says activity is unchanged.
  B. transient_flagged: a single device's reading is flagged (motion/fit/contact) while a second device reads normal at the
     same time, and it resolves after a strap/fit adjustment.
  D. (OFF by default) maintenance_report: explicit device-fault wording (sync/battery/charger/error code/broken strap) -> ticket only.
  E. (OFF by default) scale_blip: one scale reading jumps >= scale_blip_kg and the next returns -> ticket only.
  C. firmware_shift: a firmware/update/re-pair flag with otherwise flat physiology and a stream change after it.
Route: a no-trigger case becomes Layer-1-owned silent_log + device_maintenance ticket; any other decision keeps its route and only gains the ticket."""
import re

ACT_DEVS = r"watch|ring|phone|pedometer|tracker|fitbit|band"
SAME_ACT = (r"(?:walk\w*|activ\w*|mov\w*|steps?|doing)[^.;]{0,40}(?:same as (?:always|usual|before)|as usual|no more than usual|not (?:any )?more|isn'?t (?:walking|doing) any more|hasn'?t (?:been )?(?:walking|doing) (?:any )?more|unchanged|no different|not changed)"
            r"|(?:same as always|as always|as usual)[^.;]{0,30}(?:walk\w*|activ\w*|mov\w*)"
            r"|(?:isn'?t|is not|hasn'?t been|has not been|not) (?:walking|moving|doing) (?:any )?(?:more|less|differently)")
FW = r"firmware|software update|app update|update (?:installed|applied)|re-?paired|reset to factory|new (?:watch|ring|band|strap|sensor)\b"
REFIT = r"re-?fit\w*|refitted|re-?strap\w*|re-?seat\w*|strap (?:adjust\w*|tighten\w*|loosen\w*)|tightened the strap|adjusted the strap|after strap adjustment|re-?position\w*"
FLAG = r"motion flag|movement flag|poor (?:fit|contact|signal)|low (?:perfusion|signal)|contact flag|loose"
ACUTE = (r"breathless\w*|short of breath|nause\w*|vomit\w*|confus\w*|chest (?:pain|tight)|exhausted|dizz\w*|faint\w*|palpitat\w*|swollen|swelling|puffy|"
         r"fell\b|fall\b|pain\b|unwell|worse|tired\w*|fatigue\w*|weak\w*|cough\w*|fever|\bRR (?:2[2-9]|[3-9]\d)")
FLATW = r"\bflat\b|unchanged|stable|no symptoms|felt fine|feels? fine|usual self|feels? well|all normal|no other change"
NEG = r"\b(?:no|denies|without|not|nor|never)\b[^.;:]{0,30}"

def _txt(c): return (c.get("trend_last_7d") or ""), (c.get("caregiver_or_nurse_note") or "")
def _flags(c): return " ".join((c.get("data_quality") or {}).get("artifact_flags") or [])
def acute_words(trend, note): return re.search(ACUTE, re.sub(NEG, " ", trend + " " + note, flags=re.I), re.I)

def step_series(trend):
    """{device: [values in order]} for step counts; values without a device name go to the single named/default device."""
    out = {}; default = None
    for s in re.split(r"(?<=[.])\s+(?=[A-Z])", trend):
        if not re.search(r"\bsteps?\b", s, re.I): continue
        s2 = re.sub(r"Day\s*[-\u2013+]?\s*\d+\s*(?:to\s*[-\u2013+]?\s*\d+)?\s*:?", ";", s, flags=re.I)
        s2 = re.sub(r"firmware\s*[\d.]+|version\s*[\d.]+|\d{1,2}:\d{2}", " ", s2, flags=re.I)
        for seg in s2.split(";"):
            pairs = [(m.group(1).lower(), int(m.group(2))) for m in re.finditer(r"\b(" + ACT_DEVS + r")\s+(?:steps?\s+)?(\d{3,5})(?!\d|\.\d|%|/)", seg, re.I)]
            if pairs:
                for n, v in pairs: out.setdefault(n, []).append(v)
                if len(pairs) == 1: default = pairs[0][0]
                continue
            if re.search(r"(?:" + ACT_DEVS + r")\s+(?!steps?\b)[a-z]", seg, re.I) and not re.search(r"\bsteps?\b", seg, re.I): continue
            nums = [int(x) for x in re.findall(r"(?<![\d.])(\d{3,5})(?!\d|\.\d|%|/)", seg) if 200 <= int(x) <= 40000]
            if not nums or (not re.search(r"\bsteps?\b", seg, re.I) and not re.fullmatch(r"[\s\d,.]*", seg)): continue
            named = [k for k in out if k != "steps"]
            if len(nums) >= 2 and len(named) >= 2 and len(nums) == len(named):   # "3100, 2950" continuing a two-device series
                for n, v in zip(named, nums): out[n].append(v)
            else:
                out.setdefault(default or "steps", []).extend(nums)
    return out

def physiology_moved(c, trend, P):
    """resting HR or weight in the trend far from the 30-day baseline -> not a stable patient (PLACEHOLDER deltas)."""
    b = c.get("baseline_30d") or {}
    hr = [int(x) for m in re.finditer(r"(?:rest(?:ing)? HR|resting heart rate)\s*(\d{2,3})(?:\s*[-\u2013]\s*(\d{2,3}))?", trend, re.I) for x in m.groups() if x]
    if b.get("rest_hr") and hr and max(abs(h - b["rest_hr"]) for h in hr) >= P["hr_shift_bpm"]: return True
    wt = [float(x) for x in re.findall(r"(\d{2,3}(?:\.\d)?)\s*kg", trend)]
    if b.get("weight_kg") and wt and max(abs(w - b["weight_kg"]) for w in wt) >= P["weight_shift_kg"]: return True
    return False

def activity_artifact(c, trend, note, P):
    if physiology_moved(c, trend, P): return None
    base = (c.get("baseline_30d") or {}).get("steps"); ser = step_series(trend)
    if not ser: return None
    ratio = P["steps_change_ratio"]
    def moved(vals, ref): return ref and vals and (vals[-1] >= ref * ratio or vals[-1] <= ref / ratio)
    moving = {d: v for d, v in ser.items() if moved(v, base or v[0])}
    flat = {d: v for d, v in ser.items() if d != "steps" and d not in moving and len(v) >= 2 and max(v) <= min(v) * P["flat_ratio"]}
    if not moving: return None
    d = next(iter(moving))
    if flat: return f"{d} steps {moving[d][0]}->{moving[d][-1]} while {next(iter(flat))} steps stay flat"
    if re.search(FW, trend + " " + _flags(c), re.I): return f"{d} steps {moving[d][0]}->{moving[d][-1]} after a firmware/update flag"
    if re.search(SAME_ACT, note + " " + trend, re.I): return f"{d} steps {moving[d][0]}->{moving[d][-1]} but activity reported unchanged"
    return None

def transient_flagged(c, trend, note):
    txt = trend + " " + note + " " + _flags(c)
    if not (re.search(FLAG, txt, re.I) and re.search(REFIT, txt, re.I)): return None
    devs = set(m.group(0).lower() for m in re.finditer(r"watch|ring|chest strap|patch|fingertip|oximeter|cuff", trend, re.I))
    if len(devs) < 2: return None
    if not re.search(r"\bwhile\b|whereas|\bbut\b|contradict\w*|at the same time|same time", trend, re.I): return None
    if not re.search(r"(?:back to|returned to|went back|went back to) normal|after (?:strap|refit|re-?seat|adjust)\w*[^.;]{0,40}\d", txt, re.I): return None
    return "single-device reading flagged and contradicted by a second device; resolved after a fit adjustment"

def firmware_shift(c, trend, note):
    if not re.search(FW, trend + " " + _flags(c), re.I): return None
    if not re.search(FLATW, trend + " " + note, re.I): return None
    return "stream change after a firmware/update/re-pair flag with otherwise flat physiology"

MAINT = (r"won'?t sync|not syncing|stopped syncing|sync(?:ing)? (?:fail\w*|error|problem\w*)|battery (?:low|dying|died|dead|drain\w*)|low battery|won'?t charge|not charging|"
         r"charger (?:broken|lost|missing)|error code|(?:sensor|cuff|device) (?:error|fault|fail\w*|malfunction\w*)|signal loss|(?:strap|band) (?:broken|snapped|torn)|cracked (?:screen|sensor|case)|keeps (?:disconnecting|dropping out)|bluetooth (?:drop\w*|issue\w*|problem\w*)")
def maintenance_report(c, trend, note):
    """explicit device-fault wording (sync, battery, charger, error code, broken strap) -> maintenance ticket only (route untouched)."""
    allt = trend + " " + note + " " + _flags(c)
    for s_ in re.split(r"(?<=[.;!?])\s+", allt):
        if re.search(r"replaced|charged|recharged|fixed|resolved|repaired|swapped", allt, re.I): return None   # fault already resolved somewhere in the record
        if re.search(r"replaced|charged|recharged|fixed|resolved|repaired|swapped|new (?:band|strap|sensor|battery)|since then (?:fine|normal)", s_, re.I): continue   # already resolved
        m = re.search(MAINT, re.sub(NEG, " ", s_, flags=re.I), re.I)
        if m: return f"device fault reported ({m.group(0)})"
    return None
def scale_blip(c, trend, P):
    """a single scale reading jumps >= scale_blip_kg and the next reading returns to within 0.5 kg of the one before -> scale ticket only."""
    w = [float(x) for x in re.findall(r"(\d{2,3}\.\d)\s*kg", trend)]
    for i in range(1, len(w) - 1):
        if abs(w[i] - w[i - 1]) >= P["scale_blip_kg"] and abs(w[i + 1] - w[i - 1]) <= 0.5: return f"single scale reading {w[i]:g} kg between {w[i-1]:g} and {w[i+1]:g} kg"
    return None

def apply(case, c, out, ctx, L, T, P, V12):
    V = (T.v110(P).get("v1130") or {})
    if not V.get("enabled") or out.get("device_ticket"): return out
    trend, note = _txt(c); pre, day0 = L.split_day0(trend)
    if V12.symptomatic(day0 + " " + note, L) or out.get("acute_presentation") or acute_words(trend, note): return out
    tier = out.get("tier"); owned = out.get("owned_route")
    if tier in ("ABSOLUTE", "CONFIRM_FIRST") or (owned and owned != "silent_log"): return out
    if tier == "SUPPRESSED" and out.get("reason") not in ("cleared_by_repeat", "device_disagreement", "unreliable_reading"): return out
    why = None
    if V.get("activity_artifact", True): why = activity_artifact(c, trend, note, V)
    if not why and V.get("transient_flagged", True): why = transient_flagged(c, trend, note)
    if not why and V.get("firmware_shift", True) and tier is None: why = firmware_shift(c, trend, note)
    ticket_only = False
    if not why and V.get("maintenance_report"): why = maintenance_report(c, trend, note); ticket_only = bool(why)
    if not why and V.get("scale_blip"): why = scale_blip(c, trend, V); ticket_only = bool(why)
    if not why: return out
    tk = {"type": "device_maintenance", "interruptive": False, "detail": why, "route_to": "device_maintenance_process_else_whoever_can_check_the_device", "rule": "v1130"}
    if tier is None and not ticket_only:
        return {**out, "rule": "HT_DEVICE_DISAGREE", "tier": "SUPPRESSED", "reason": "device_artifact_stable_patient", "owned_route": "silent_log", "default_route": "silent_log", "v1130": True, "device_ticket": tk}
    return {**out, "device_ticket": tk}
