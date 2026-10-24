"""SMART_TRIGGERS v1.14.1 device-ticket policy (params layer1_v110.v1141; every number is a PLACEHOLDER). Wayne 2026-10-24 rulings.
Built ONLY from Wayne's rulings on library_expansion_v2 disputes, library cases and hand-written synthetic vignettes (test_layer1_v1141.py).
holdout_v3/holdout_v4 case text was NOT read while designing these rules.
  POLICY 1: when the route is clinical (nurse_task / provider_task / urgent_page), NO device ticket; the evaluating clinician files one.
            Layer 1 drops the ticket when its own route is clinical (kept as device_ticket_suppressed for audit). When Layer 1 leaves the
            route to Jev, the ticket is conditional (ticket_if_route='silent_log'); final_ticket() drops it if the final route is clinical.
  POLICY 2: tickets only for internal device faults (sensor fault/expiry, battery, firmware/app, clock, sync, duplicate records, device
            error codes, impossible scale weights, a new scale's step offset). External human causes (strap fit, cuff over a sleeve or
            wrong size, objects/people on the scale, scale on a rug, lying on a CGM sensor) get no ticket: the v1.14 fit family and the
            human-cause parts of the cuff/scale families stay OFF.
  Wayne's library rulings: expired CGM sensor (wear-limit flag) -> ticket (LX11-006); wearable SpO2 with a contact/motion flag cleared by a
            good-waveform fingertip -> ticket (LX12-007); oximeter disagreement tickets are device_maintenance, not a separate type.
  CGM warm-up: a reading during a sensor warm-up window is expected device behaviour, not a fault: no ticket (LX11-005 ruling).
  Internal sub-families (param-gated): cuff_error (cuff error code with no number), scale_internal (impossible weight with a normal repeat,
            new scale installed / old retired with no clinic or visit weight agreeing).
  v1.14.2 (Wayne 2026-10-24, POLICY 2 tightening; built from library LX2-006 / LX11-002 and synthetic vignettes in test_layer1_v1142.py,
            holdout text NOT read): human_cause_guard withdraws a cuff ticket when the cuff was re-seated / repositioned / pinched or a
            seated-rest repeat cleared it (unless a cuff error code was shown), and withdraws a scale ticket when a bag / object / person / pet
            was on the scale or the note says the patient was not on it (but a zero / near-zero reading keeps its ticket: extra weight cannot read 0 kg, LX11-001). Internal faults (error code, impossible weight with a normal repeat
            and no human cause, new-scale offset) keep their ticket."""
import re
CLIN = ("nurse_task", "provider_task", "urgent_page")
CUFF_ERR = r"\berror E\d\b|cuff (?:displayed |showed )?(?:error|err)\b|\bE\d (?:cuff )?error\b|E\d with no (?:number|reading)"
SCALE_NEW = r"new scale installed|old scale retired|new scale (?:arrived|delivered|set up)"
WARMUP = r"warm[- ]?up"
EXPIRY = r"sensor (?:expired|expiry|past (?:its|the) \d+)|expired sensor|past (?:its |the )?\d+-day (?:wear )?limit"

SPO2_FLAG = r"(?:ring|watch)[^.;]{0,30}SpO2 \d{2}%[^.;]{0,40}(?:poor[- ]contact|motion|fit) flag"
# v1.14.4 (Wayne 2026-10-24, from library LX10-004 / LX12-007 / LX12-008 and synthetic vignettes; holdout text NOT read): only a
# poor-contact flag on a reading taken at rest counts as an internal sensor fault. Motion and fit flags are external/human (POLICY 2;
# Wayne's motion-artifact = no ticket ruling), so they never earn this ticket.
SPO2_CONTACT_REST = r"(?:ring|watch)[^.;]{0,40}(?:rest(?:ing)?\b[^.;]{0,20}SpO2 \d{2}%|SpO2 \d{2}%[^.;]{0,15}\bat rest)[^.;]{0,40}poor[- ]contact flag"
FINGER_OK = r"fingertip[^.;]{0,30}(?:9[4-9]|100)%[^.;]{0,30}good waveform|fingertip oximeter (?:9[4-9]|100)%"
def internal_extra(c, V, V14, out=None):
    txt = V14._all(c); clean = re.sub(V14.NEG, " ", txt, flags=re.I)
    if V.get("cgm_expiry", True):
        m = re.search(EXPIRY, clean, re.I)
        if m: return "cgm_expiry", m.group(0)
    if V.get("spo2_flag_vs_fingertip", True) and out is not None and out.get("reason") == "cleared_by_repeat" and re.search(SPO2_CONTACT_REST if V.get("spo2_contact_rest_only", True) else SPO2_FLAG, clean, re.I) and re.search(FINGER_OK, clean, re.I):
        return "spo2_flag_vs_fingertip", "flagged wearable SpO2 cleared by a fingertip reading"
    if V.get("cuff_error") and re.search(CUFF_ERR, clean, re.I): return "cuff_error", re.search(CUFF_ERR, clean, re.I).group(0)
    if V.get("scale_internal") and not re.search(V14.SCALE_REAL, txt, re.I):
        if V14.impossible_weight(txt, V14_P(V)): return "scale_internal", "impossible weight with a normal repeat"
        m = re.search(SCALE_NEW, clean, re.I)
        if m: return "scale_internal", m.group(0)
    return None
CUFF_HUMAN = r"cuff (?:was )?re-?(?:seated|seating|positioned|positioning|applied|wrapped)|re-?seat\w* (?:the |her |his )?cuff|cuff pinched|pinched on the first|after [^.;]{0,30}seated rest|seated[^.;]{0,20}repeat|repeat[^.;]{0,40}seated"
SCALE_HUMAN = r"(?:bag|box|basket|parcel|package|object|laundry|compost|groceries|shopping|suitcase|pet|dog|cat|child|grandchild|someone else|another person|(?:her|his) (?:husband|wife|son|daughter|spouse))[^.;]{0,40}on the (?:scale|platform)|on the scale (?:platform )?[^.;]{0,20}(?:bag|box|object|pet|dog|cat|child)|not the patient's weight|patient was not on the scale|(?:stood|stepped) on (?:her|his|the patient's) scale"
def human_cause(tk, txt):
    d = (tk.get("detail") or "").lower(); fam = None
    if "cuff" in d or "bp" in d or "blood pressure" in d: fam = "cuff"
    elif "scale" in d or "weight" in d: fam = "scale"
    if fam == "cuff" and not re.search(CUFF_ERR, txt, re.I):
        m = re.search(CUFF_HUMAN, txt, re.I); return m and m.group(0)
    if fam == "scale":
        if any(float(x) < 1.0 for x in re.findall(r"(\d{1,3}\.\d)\s*kg", txt)): return None   # a zero / near-zero reading is not explained by extra weight: internal fault (LX11-001)
        m = re.search(SCALE_HUMAN, txt, re.I); return m and m.group(0)
    return None
def V14_P(V): return {"min_plausible_kg": V.get("min_plausible_kg", 25.0)}

def apply(c, out, L, T, P, V14):
    V = (T.v110(P).get("v1141") or {})
    if not V.get("enabled"): return out
    out = dict(out); tk = out.get("device_ticket")
    if tk and V.get("warmup_no_ticket", True) and "(cgm:" in (tk.get("detail") or "") and re.search(WARMUP, tk["detail"], re.I):
        nb = (c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or "") + " " + " ".join((c.get("data_quality") or {}).get("artifact_flags") or [])
        if not re.search(EXPIRY, nb, re.I): out["device_ticket_suppressed"] = {**tk, "why": "CGM warm-up reading is expected behaviour, not a fault"}; out.pop("device_ticket"); tk = None
    if not tk:
        f = internal_extra(c, V, V14, out)
        if f: tk = out["device_ticket"] = {"type": "device_maintenance", "interruptive": False, "detail": f"device fault ({f[0]}: {f[1]})", "route_to": "device_maintenance_process_else_whoever_can_check_the_device", "rule": "v1141"}
    if tk and V.get("human_cause_guard", True):   # v1.14.2
        h = human_cause(tk, V14._all(c))
        if h: out["device_ticket_suppressed"] = {**tk, "why": f"POLICY 2 (v1.14.2): human/external cause ({h}), no device ticket"}; out.pop("device_ticket"); tk = None
    if tk and tk.get("type") == "supply_reference_oximeter_and_baseline" and V.get("oximeter_as_maintenance", True):
        tk = out["device_ticket"] = {**tk, "type": "device_maintenance"}   # Wayne 2026-10-24: oximeter disagreement = the same device_maintenance ticket
    if tk and V.get("suppress_on_clinical_route", True):
        r = L.route(out, None)[0]
        if r in CLIN:
            out["device_ticket_suppressed"] = {**tk, "why": f"POLICY 1: route {r} is clinical; the evaluating clinician files a device ticket"}; out.pop("device_ticket")
        elif r is None: out["device_ticket"] = {**tk, "ticket_if_route": "silent_log"}
    return out

def final_ticket(l1, final_route):
    """POLICY 1 at the final (Layer 1 + Jev) route: a conditional ticket survives only when the final route is silent_log."""
    tk = l1.get("device_ticket")
    if not tk: return None
    if final_route in CLIN: return None
    return tk
