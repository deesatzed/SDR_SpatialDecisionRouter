"""SMART_TRIGGERS v1.14.0 Layer 1 device tickets for named device faults (params layer1_v110.v1140; every number is a PLACEHOLDER).
Built ONLY from library cases (library_expansion_v2 device-fault batch LX9-LX12, library_expansion_v1) and hand-written synthetic vignettes
(test_layer1_v1140.py). holdout_v3/holdout_v4 case text was NOT read while designing these rules.
DEFAULTS: the scale, fit and cuff families are OFF (params). Scored blind after design, each put one unexpected ticket on holdout_v4
(HX4-006 scale, HX5-006 fit, HX6-004 cuff; routes unchanged), so they were switched off rather than tuned on the holdout.
TICKET ONLY: these rules add a device_maintenance ticket and never change the route, whatever the clinical picture
(a ticket can sit on top of nurse_task / provider_task / urgent_page). One exception goes the safe way:
  R. firmware_shift_guard: a v1.13.0 firmware-shift ticket whose only evidence is a re-pair/update flag with NO stream change after it,
     or with new positional-breathing words (sleeping propped up, lying flat feels stuffy/breathless), is withdrawn and the v1.13 silent_log
     ownership is undone (the case goes back to the pre-v1.13 decision, usually Jev).
Fault families (any one -> ticket), each with its own 'it was real' or 'already fixed' veto:
  sync/upload failure, battery or charger failure (veto: charged, replaced/new charger, continuous data since);
  BP cuff error code, cuff over a sleeve, wrong cuff size;
  strap replaced/loose with motion flags, watch removed for skin trouble, CGM patch lifted/peeling;
  scale: impossible weight (< min_plausible_kg) with a normal repeat, someone/something else on the scale, scale moved onto carpet/rug, new scale with a step offset
         (veto: a clinic/second scale or visit weight agrees with the new value);
  app/firmware update that changes how a stream is measured or exported; duplicated records; device clock/time-zone shift;
  CGM warm-up or expired sensor named in the trend or note (a routine warm-up window in the quality flags alone does not count). (CGM compression lows are NOT ticketed: library_expansion_v1 labels them nurse_task with no ticket.)"""
import re

NEG = r"\b(?:no|denies|without|not|nor|never)\b[^.;:]{0,30}"
FAM = {
 "sync": r"sync(?:ing)? (?:fail\w*|error)|'sync failed'|upload\w* (?:stopped|gap|stop)|stopped (?:watch )?upload\w*|no upload|not syncing|stopped syncing",
 "battery": r"battery (?:flat|dead|died|drain\w*)|flat battery|battery \d{1,2}%|not charging|(?:charg\w+ )?(?:cable|lead|cradle|charger) (?:not (?:yet )?found|lost|missing|broken|failed)|cradle failed",
 "cuff": r"\berror E\d\b|cuff (?:displayed |showed )?(?:error|err)\b|E\d with no (?:number|reading)|over (?:a |the |her |his )?(?:\w+ )?sleeve|wrong[- ]size(?:d)? cuff|wide (?:adult )?cuff|too[- ]large cuff|cuff (?:was )?too (?:big|small|large)",
 "fit": r"strap (?:replaced|changed)|new (?:watch )?strap|longer (?:replacement )?(?:strap|pin)|turn(?:s|ing) round on (?:her|his|the) wrist|sits? loose|patch (?:edge )?lift\w*|lifted at one corner|patch peel\w*|peeling patch|removed [^.;]{0,30}(?:rash|sore|itch\w*|patch)",
 "scale": r"stood on the scale|on the scale (?:platform|holding)|bag [^.;]{0,30}on the scale|(?:put|placed) [^.;]{0,30}on the scale|scale (?:was )?moved (?:on)?to (?:a |the )?(?:\w+ )?(?:rug|carpet|mat)|new scale installed|old scale retired",
 "update": r"(?:app|firmware|software) update\w*[^.;]{0,120}(?:no readings above|different measure|reports? \w+ on a different|look\w* lower|shows? (?:far )?higher|export)",
 "dup": r"duplicat\w+|clock (?:runs? |is )?\d+ ?h(?:ours?)? (?:ahead|behind)|clock [^.;]{0,20}(?:ahead|behind)|time[- ]?zone",
 "cgm": r"warm[- ]?up|sensor (?:expired|expiry|past (?:its|the) \d+)|expired sensor",
}
FIXED = r"replaced|(?:re)?charged\b|new (?:cradle|charger|cable|lead)\b|fitted|continuous data since|syncing again"
SCALE_REAL = r"clinic scale|second scale|visit[^.;]{0,30}weigh\w*|nurse[^.;]{0,30}weigh\w*"
POSITIONAL = r"propped|lying flat|sleep\w* (?:sitting )?up(?:right)? in (?:a|the) (?:arm)?chair|in the armchair|extra pillow|more pillows|orthopn\w*"

def _all(c):
    return " ".join([c.get("trend_last_7d") or "", c.get("caregiver_or_nurse_note") or "", " ".join((c.get("data_quality") or {}).get("artifact_flags") or [])])

def impossible_weight(txt, P):
    """an impossible weight (below min_plausible_kg, e.g. 0.0 kg) followed by a plausible repeat."""
    w = [float(x) for x in re.findall(r"(\d{1,3}\.\d)\s*kg", txt)]
    return any(v < P["min_plausible_kg"] and any(u >= P["min_plausible_kg"] for u in w[i + 1:]) for i, v in enumerate(w))

def fault(c, P):
    txt = _all(c); clean = re.sub(NEG, " ", txt, flags=re.I)
    for fam, pat in FAM.items():
        if not P.get(fam, True): continue
        m = re.search(pat, clean, re.I)
        if not m: continue
        if fam in ("sync", "battery") and re.search(FIXED, txt, re.I): continue
        if fam == "cgm" and not re.search(pat, re.sub(NEG, " ", (c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or ""), flags=re.I), re.I): continue   # a routine warm-up window in the flags alone is not a fault
        if fam == "scale" and re.search(SCALE_REAL, txt, re.I): continue
        return fam, m.group(0)
    if P.get("scale", True) and impossible_weight(txt, P) and not re.search(SCALE_REAL, txt, re.I): return "scale", "impossible weight with a normal repeat"
    return None

def firmware_guard(c, out13, out0, V13, P):
    """withdraw a v1.13.0 firmware-shift ticket with no stream change or with new positional-breathing words."""
    tk = out13.get("device_ticket") or {}
    if tk.get("rule") != "v1130" or not (tk.get("detail") or "").startswith("stream change after a firmware") or out0.get("device_ticket"): return None
    txt = _all(c)
    if re.search(POSITIONAL, re.sub(NEG, " ", txt, flags=re.I), re.I): return out0
    after = re.split(V13.FW, c.get("trend_last_7d") or "", maxsplit=1, flags=re.I)
    if len(after) < 2 or not re.search(r"\d", after[-1]): return out0   # nothing measured after the flag
    return None

def apply(case, c, out13, out0, ctx, L, T, P, V13):
    V = (T.v110(P).get("v1140") or {})
    if not V.get("enabled"): return out13
    if V.get("firmware_shift_guard", True):
        g = firmware_guard(c, out13, out0, V13, V)
        if g is not None: return {**g, "v1140_withdrawn": "v1.13 firmware-shift ticket withdrawn (no stream change or new positional breathing words)"}
    if out13.get("device_ticket"): return out13
    f = fault(c, V)
    if not f: return out13
    tk = {"type": "device_maintenance", "interruptive": False, "detail": f"device fault ({f[0]}: {f[1]})", "route_to": "device_maintenance_process_else_whoever_can_check_the_device", "rule": "v1140"}
    return {**out13, "device_ticket": tk}
