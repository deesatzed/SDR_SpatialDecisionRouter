"""Layer 1 v1.12.0 generalized wording/matching (SYNTHETIC; params layer1_v110.v1120, every number a PLACEHOLDER).
Post-processes the v1.11.2 decision from STRUCTURED FACT fields only (same field whitelist as layer1_adapter.facts_only).
Built ONLY from homehealth/library_expansion_v1, the original library and hand-written practice vignettes (test_layer1_v1120.py);
holdout_v3 / holdout_v4 case text was not read while designing these rules (Wayne's holdout rulings were used only as abstract patterns).
A v1.12.0 decision that sets owned_route is routed by Layer 1 directly (route(): layer1_v1120) unless Layer 1 flags an acute presentation
(urgent owned routes are ABSOLUTE and always page). Rules never lower a FOUNDATION rule, syncope, focal neuro, pain after a fall or a head strike."""
import re
NEVER_LOWER = {"HT_DRUG_LOW", "HT_SYNCOPE", "HT_FOCAL_NEURO", "HT_FALL_PAIN", "HT_CHEST_PAIN_ECG", "HT_SPO2_REST_DYSPNEA", "HT_BRADY_RATE_DRUG", "HT_SEROTONERGIC_CONFUSION"}
DAYREF = re.compile(r"\bDays?\s+(-?\d+)(?:\s*(?:to|-|–|and|through)\s*(?:Day\s+)?(-?\d+))?", re.I)
def _sents(t): return [s.strip() for s in re.split(r"(?<=[.;!?])\s+(?=[A-Z'\"]|Day\b|\d)", t or "") if s.strip()]

# ---------------- shared fact helpers
def home_o2(c, L):
    """negation-aware home oxygen on the problem / med / device lists ('home oxygen not prescribed' and 'no home oxygen' are NOT home O2)."""
    for s in list(c.get("pmh") or []) + [m.get("name", "") + " " + m.get("dose", "") for m in c.get("meds") or []] + list(c.get("devices") or []):
        if re.search(r"home (?:oxygen|O2)|oxygen (?:\d|concentrator|at night|overnight)|\d(?:\.\d)? ?L/min|concentrator", s, re.I) and \
           not re.search(r"\bno\b[^.;]{0,20}(?:home )?(?:oxygen|O2)|(?:oxygen|O2)[^.;]{0,25}\b(?:not|never)\b|\bnot\b[^.;]{0,15}prescribed|without (?:home )?oxygen|declined", s, re.I):
            return True
    return False
BAND_RX = [r"(?:band|target|range|accept\w*|happy if (?:sats|SpO2|saturations?) (?:stay|are|sit)|agreed|goal|aim)[^.;%\d]{0,30}?(\d{2})\s*%?\s*(?:-|–|to)\s*(\d{2})\s*%",
           r"(?:SpO2|sats?|saturations?)\s*(?:band|target|range|goal)?\s*(?:of\s*)?(\d{2})\s*%?\s*(?:-|–|to)\s*(\d{2})\s*%\s*(?:\(|is |as )?(?:clinician|agreed|target|accepted|care plan)"]
FLOOR_RX = r"(?:target )?floor (?:of )?(\d{2})\s*%|(?:not|never) (?:below|under) (\d{2})\s*%"
def spo2_band(c, L):
    """(lo, hi) from structured patient_bands, or a band/target/floor written in a care plan or clinician note (pmh, note, pre-Day-0 trend)."""
    pbs = (c.get("patient_bands") or {}).get("spo2")
    if pbs: return int(pbs[0]), int(pbs[1])
    pre, _ = L.split_day0(c.get("trend_last_7d") or "")
    for txt in list(c.get("pmh") or []) + _sents(c.get("patient_goals")) + _sents(c.get("caregiver_or_nurse_note")) + _sents(pre):
        if not re.search(r"care plan|clinician|pulmonolog\w*|respiratory (?:team|nurse)|chest clinic|agreed|documented|letter|consultant|GP|prescriber|band|target|accept", txt, re.I): continue
        for rx in BAND_RX:
            m = re.search(rx, txt, re.I)
            if m:
                lo, hi = sorted((int(m.group(1)), int(m.group(2))))
                if 70 <= lo < hi <= 100: return lo, hi
        m = re.search(FLOOR_RX, txt, re.I)
        if m and re.search(r"SpO2|sats?|saturation|oxygen", txt, re.I):
            lo = int(m.group(1) or m.group(2))
            if 70 <= lo <= 95: return lo, 100
    return None
FLAG2 = r"low[- ]perfusion|pressure[- ]on[- ]sensor|pressed (?:in)?to|poor[- ](?:skin )?contact|motion|cold (?:wrist|fingers|hands)|loose|off[- ]wrist|charging|\bflag(?:ged)?\b"
def clean_spo2_day0(c, L):
    """(value, device) Day 0 resting SpO2 readings whose clause carries no artifact flag (ranges count by their low end)."""
    out = []
    for r in L.recs(c, "spo2"):
        if r[3] == "active": continue
        segs = [x for x in re.split(r";|,(?=\s*(?:watch|ring|fingertip|oximeter))", r[1]) if re.search(r"(?<!\d)%s\s*%%" % int(r[0]), x) or re.search(r"%s\s*[-–]\s*\d+\s*%%" % int(r[0]), x)]
        seg = " ".join(segs) if segs else r[1]
        if L.find(FLAG2, seg): continue
        out.append((r[0], r[6]))
    return out
def symptomatic(now, L):
    return bool(L.find(r"confus\w*|drowsy|sweaty|sweating|clammy|slurred|unresponsive|short phrases|few words|gasping|struggling to breathe|breathless (?:at rest|sitting)|dizz\w*|light-?headed|faint\w*|chest (?:pain|pressure)|palpitat\w*|hard to rouse|not making sense", now))

# ---------------- 1. device disagreement v2 (any vital; device attributed to the clause subject)
DEV2 = [("fingertip", r"fingertip|finger (?:clip|probe|oximeter)|oximeter|\bfinger\b"), ("glucometer", r"glucometer|finger-?(?:stick|prick)|finger test|\bmeter\b"),
        ("cgm", r"\bCGM\b|\bsensor\b(?! side)|sensor app"), ("ring", r"\bring\b"), ("watch", r"\bwatch\b|\bwrist\b"), ("cuff", r"\bcuff\b"), ("patch", r"\bpatch\b"),
        ("bed", r"bed sensor"), ("thermometer", r"thermometer|\boral\b")]
UNIT = r"([+-]?\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*([+-]?\d+(?:\.\d+)?))?\s*(%|bpm|ms\b|h\b|mg/dL|°?\s*C\b)"
def _vital(unit, clause):
    u = unit.replace("°", "").strip()
    if u == "%": return "spo2"
    if u == "bpm": return "hr"
    if u == "ms": return "hrv"
    if u == "h": return "sleep" if re.search(r"sleep|slept", clause, re.I) else None
    if u == "mg/dL": return "glucose"
    if u == "C": return "skin_temp"
    return None
LIMITS = {"spo2": (60, 100), "hr": (25, 220), "hrv": (5, 200), "sleep": (1, 14), "glucose": (40, 500), "skin_temp": (-3, 3)}
def device_values(text):
    """[(device, vital, lo, hi)] attributing each value to the first device named in its clause (else the previous clause's device)."""
    out = []
    for s in _sents(text):
        cur = None
        for cl in re.split(r";|,|\bwhile\b|\bwhereas\b|\bbut\b|\bagainst\b", s):
            if re.search(FLAG2, cl, re.I) and not re.search(r"\bno\b[^.;,]{0,25}flags?", cl, re.I): cur = None; continue
            hits = sorted([(m.start(), k) for k, rx in DEV2 for m in [re.search(rx, cl, re.I)] if m])
            if hits: cur = hits[0][1]
            if not cur: continue
            for m in re.finditer(UNIT, cl):
                v = _vital(m.group(3), cl)
                if not v: continue
                a = float(m.group(1)); b = float(m.group(2)) if m.group(2) else a
                lo, hi = min(a, b), max(a, b); L0, H0 = LIMITS[v]
                if v == "skin_temp" and (abs(lo) > 3 or abs(hi) > 3): continue
                if lo < L0 or hi > H0: continue
                if re.search(r"(?:below|above|lower|higher|apart|gap|difference)", cl[m.end():m.end() + 25], re.I) or re.search(r"gap of\s*$", cl[:m.start()], re.I): continue
                out.append((cur, v, lo, hi))
    return out
def explicit_gaps(text):
    """[(vital, gap)] from 'a gap of 11-13 bpm', '20-25 mg/dL below the CGM', etc."""
    out = []
    for m in re.finditer(r"(?:gap of\s*)?(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*(%|bpm|ms\b|h\b|mg/dL)\s*(below|above|lower|higher|apart|different)?", text or "", re.I):
        if not (m.group(4) or re.search(r"gap of\s*$", text[max(0, m.start() - 8):m.start()] + (m.group(0)[:7] if m.group(0).lower().startswith("gap") else ""), re.I) or m.group(0).lower().startswith("gap")): continue
        v = _vital(m.group(3), text[max(0, m.start() - 60):m.end()] if m.group(3) != "h" else "sleep")
        if v: out.append((v, float(m.group(1))))
    return out
GAP_MIN = {"spo2": 3, "hr": 8, "hrv": 8, "sleep": 1.0, "glucose": 15, "skin_temp": 0.4}
def device_disagreement_v2(c, ctx, L, P12):
    trend = c.get("trend_last_7d") or ""; note = c.get("caregiver_or_nurse_note") or ""
    WEAR = r"\b(?:worn|wear(?: time)?)\s*\d+\s*%|\d+\s*%\s*(?:worn|wear)"
    trend = re.sub(WEAR, "", trend, flags=re.I); note = re.sub(WEAR, "", note, flags=re.I)
    vals = []
    for i_, s_ in enumerate(_sents(trend) + _sents(note)): vals += [(d, vv, lo, hi, i_) for d, vv, lo, hi in device_values(s_)]
    acute = re.search(r"breathless\w*|short of breath|nause\w*|vomit\w*|confus\w*|chest (?:pain|tight)|exhausted|cannot leave|dizz\w*|faint\w*|\bRR (?:2[2-9]|[3-9]\d)|resting HR (?:1\d\d)|HR (?:1[01]\d)\b", re.sub(r"\b(?:no|denies|without|not)\b[^.;:]{0,30}", " ", trend + " " + note, flags=re.I), re.I)
    if acute: return None   # symptoms or abnormal other vitals: a clinical question, not a device-disagreement ticket
    best = None
    for v in GAP_MIN:
        by = {}
        for d, vv, lo, hi, si in vals:
            if vv == v: by.setdefault(d, []).append((lo, hi, si))
        if v == "glucose": by = {k: x for k, x in by.items() if k in ("cgm", "glucometer")}
        SANE = {"glucose": (70, 250), "hr": (45, 110), "spo2": (85, 100)}   # a disagreement where a device reads out of range is a clinical question, not a device ticket
        if v in SANE and any(lo < SANE[v][0] or hi > SANE[v][1] for xs in by.values() for lo, hi, _ in xs): continue
        devs = list(by)
        for i in range(len(devs)):
            for j in range(i + 1, len(devs)):
                for a in by[devs[i]]:
                    for b in by[devs[j]]:
                        if abs(a[2] - b[2]) > (0 if v == "glucose" else 2): continue   # glucose pairs must be near each other in the text (same time window)
                        sep = max(b[0] - a[1], a[0] - b[1], 0)
                        if sep >= GAP_MIN[v] and (best is None or sep / GAP_MIN[v] > best[3] / GAP_MIN[best[0]]): best = (v, devs[i], devs[j], sep)
    if best is None:
        for v, g in explicit_gaps(trend + " " + note):
            if g >= GAP_MIN[v]: best = (v, "device", "device", g); break
    asks = re.search(r"which (?:one|reading|device|number)?\s*(?:is|should|to)\b[^.?]{0,25}(?:right|trust|believe)|not sure which|reads? (?:high|low)\b|got it wrong|thinks the (?:sensor|watch|ring) reads", note, re.I)
    if best is None: return None
    v = best[0]; txt = trend + " " + note; devs = " ".join(c.get("devices") or [])
    refit = re.search(r"re-?fit\w*|refitted|re-?strap\w*|re-?seat\w*|re-?paired|strap (?:adjust\w*|tighten\w*|loosen\w*)|tightened the strap|a hole looser|looser|new (?:strap|band)|re-?position\w*", txt, re.I)
    med_chg = [m for m in (c.get("recent_med_changes") or []) if m.get("change") in ("started", "dose_increased", "dose_decreased", "stopped", "switched") and m.get("day") is not None and m["day"] >= -P12["med_change_days"]]
    tip_clean = [lo for d, vv, lo, hi, _s in vals if d == "fingertip" and vv == "spo2"]
    trusted_tip = bool(tip_clean) and re.search(r"good waveform|good signal|trusted|reliable", txt, re.I)
    pending = re.search(r"(?:decision|referral|review|assessment|evaluation)[^.;]{0,40}(?:pending|awaited|due)|pending[^.;]{0,30}(?:decision|referral|review)|whether to (?:change|increase|reduce|adjust|start|stop)", txt, re.I)
    changes = bool(med_chg) or bool(pending)
    if v == "spo2" and tip_clean and min(tip_clean) < P12["spo2_trusted_low"]: changes = True
    if v == "spo2" and refit and trusted_tip and min(tip_clean) >= P12["spo2_trusted_low"]: changes = False   # Wayne: refit + trusted good-waveform fingertip -> silent + ticket even if an O2 decision is pending
    if v == "hr" and (re.search(r"atrial fibrillation|\bAF\b|AFib|flutter|arrhythm", ctx["pmh"], re.I) or re.search(r"irregular", txt, re.I)): ticket = "ecg_strip_request"
    elif v == "spo2" and not refit and ({best[1], best[2]} & {"fingertip"} or not re.search(r"fingertip|oximeter", devs, re.I)): ticket = "supply_reference_oximeter_and_baseline"
    else: ticket = "device_maintenance"
    return {"ticket": ticket, "changes_care": changes, "detail": f"{v} differs by {best[3]:g} between {best[1]} and {best[2]}" + (" (caregiver asks which to trust)" if asks else ""), "vital": v}

# ---------------- 2. stable angina (wording-general)
ANG_EP = r"tight\w*|chest (?:pain|pressure|discomfort|heaviness|ache)|angina\w*|behind the breastbone|breastbone|\bsqueez\w*|heaviness"
def angina(c, ctx, L, P12):
    pmh = ctx["pmh"]; meds = ctx["meds"]
    if not re.search(r"angina|\bCAD\b|coronary|stent|\bPCI\b|\bMI\b|myocardial infarction|ischaemic heart|ischemic heart", pmh, re.I): return None
    trend = c.get("trend_last_7d") or ""; note = c.get("caregiver_or_nurse_note") or ""; txt = trend + " " + note
    eps = [s for s in _sents(txt) if L.find(ANG_EP, s) and not re.search(r"no (?:chest )?tightness|no chest pain|no (?:rest )?pain\b", s, re.I) or re.search(r"\bepisodes?\b", s, re.I) and re.search(ANG_EP, txt, re.I)]
    if not eps: return None
    if re.search(r"musculoskeletal|chest wall|reproduc\w* (?:by|on) press\w*|press\w* (?:on|along) the ribs|reflux|heartburn|antacid", txt + " " + pmh, re.I): return None
    E = " ".join(eps)
    mins = [int(m.group(1)) for m in re.finditer(r"(\d{1,3})\s*min(?:utes)?\b(?!\s+(?:after|later|of rest|rest|seated|sitting|by))", E)
            if not re.search(r"walk\w*|stairs|hill|exercis\w*|garden\w*|mow\w*|cycl\w*|on the flat|ground", E[max(0, m.start() - 40):m.start()], re.I)]   # activity duration, not episode duration
    mins = [m for m in mins if not re.search(r"within %d\s*min|after %d\s*min|in %d\s*min|by %d\s*min" % (m, m, m, m), E, re.I)]
    urgent = []
    if mins and max(mins) >= P12["angina_urgent_minutes"]: urgent.append("episode_ge_15min")
    if L.find(r"sweat\w*|clammy|diaphore\w*|nause\w*|vomit\w*|grey|ashen|faint\w*", E + " " + note): urgent.append("red_flag_symptoms")
    if L.find(r"getting worse|worse (?:every|each)|more often|more frequent\w*|more than (?:his|her|their) usual|most walks|crescendo|no longer (?:shifts|works|helps|relieves)|lasting longer|longer than usual", txt): urgent.append("crescendo")
    rest = L.find(r"at rest\b|in bed\b|woke|asleep|while (?:sitting|resting|lying)|lying down|watching (?:TV|television)", E)
    usual_rest = re.search(r"(?:gets?|has|had) this[^.;]{0,40}(?:once a|every|usual)|usual[^.;]{0,20}(?:in (?:her|his) chair|at rest)", txt, re.I)
    if rest and not usual_rest: urgent.append("rest_episode")
    if urgent: return {"route": "urgent_page", "reason": "angina_unstable_features", "features": urgent}
    gtn_new = re.search(r"asked for (?:the |her |his |a |their )?(?:usual )?(?:spray|GTN|nitro\w*)|request\w* (?:the |her |his )?(?:spray|GTN)|wanted (?:the |her |his )?spray", txt, re.I) and \
              re.search(r"no GTN|without (?:GTN|a spray|spray)|no spray", txt, re.I)
    if gtn_new: return {"route": "provider_task", "reason": "angina_new_gtn_request"}
    if re.search(r"past (?:its )?(?:labelled |expiry |use-by )?date|expired|out of date|less sting|weaker", txt, re.I) and re.search(r"spray|GTN|nitro|tablet", txt, re.I):
        return {"route": "provider_task", "reason": "angina_gtn_efficacy"}
    anti = r"metoprolol|bisoprolol|atenolol|carvedilol|nebivolol|diltiazem|verapamil|amlodipine|isosorbide|nicorandil|ranolazine|ivabradine|nitrate"
    if any(m.get("change") in ("stopped", "dose_decreased", "held") and re.search(anti, m.get("name", ""), re.I) for m in c.get("recent_med_changes") or []):
        return {"route": "provider_task", "reason": "angina_after_antianginal_stop"}
    usual = re.search(r"same as (?:always|usual|before|ever|the last|it has been)|usual (?:count|pattern|frequency|tightness)|(?:his|her|their) usual\b|nothing different|unchanged|no (?:more|different)|for (?:the past |the last )?(?:a |two |three |\d+ )?(?:year|month)s?|once a (?:week|month)|\d\s*[-–]\s*\d (?:episodes |times )?a week|chatting again|back to normal", txt, re.I)
    eased = re.search(r"eas\w*|settl\w*|relieved|went (?:off|away)|cleared|passed|fine after|back to normal|chatting again", E + " " + note, re.I)
    if usual and eased: return {"route": "nurse_task", "reason": "stable_angina_unchanged"}
    return None

# ---------------- 3. CKD drug low explained (any wording)
EXERT = r"\bhoe\w*|\bdig(?:s|ging|ged)?\b|\bdug\b|\bmow\w*|\brak(?:e|ed|ing)\b|shovel\w*|garden\w*|allotment|\bplot\b|yard ?work|\bweed\w*|fenc\w*|brisk walk|long walk|\bhik\w*|exercis\w*|\bcycl(?:ed|ing)\b|\bswim\w*|\bdanc\w*|workout|\bgym\b|mov(?:e|ed|ing) (?:house|flat|home)|(?:house|flat|home) move|\bmove\b|carr(?:y|ied|ying)\b|boxes|flights? of stairs|lift(?:ed|ing) |\bDIY\b|decorat\w*|paint(?:ed|ing)|spring[- ]clean\w*|chopp\w* wood|repair\w*|heavy (?:work|lifting|job)|steps? (?:\d[\d,]*) against (?:usual|his usual|her usual)"
COMP = r"compression|pinned|pressed|pressure flag|sensor[- ]side pressure|lying on (?:the |his |her )?sensor|slept on (?:the |his |her )?sensor|sensor (?:was )?under (?:her|him|his|the)|on (?:the |her |his )?sensor|(?:rolled|lay|lying|slept|sleeps?|sleeping)\b[^.;]{0,30}\bsensor"
def ckd_low_events(c, L, gmin, ce=None):
    """[(day, explanation)] danger-level glucose lows in the 7 days to Day 0 (explanation: compression | exertion | None), from trend + note."""
    trend = c.get("trend_last_7d") or ""; note = c.get("caregiver_or_nurse_note") or ""; flags = " ; ".join((c.get("data_quality") or {}).get("artifact_flags") or [])
    days = {}
    for r in L.readings(trend, "glucose") + L.readings(note, "glucose", default_day=0):
        if r[7] is None or r[7] < -7 or r[7] > 0 or r[0] > gmin or r[6] == "fingerstick": continue
        days.setdefault(r[7], []).append(r[1])
    out = []
    for d, ss in sorted(days.items()):
        ctxs = " ".join(ss) + " " + " ".join(x for x in _sents(trend) + _sents(note) + _sents(flags) if re.search(r"\bDay %d\b" % d, x)) 
        if d == max(days): ctxs += " " + note
        ctxs = re.sub(r"\bno\b[^.;]{0,25}(?:pressure|compression)[^.;]{0,15}(?:flag|logged)\w*", " ", ctxs, flags=re.I)
        e = "compression" if re.search(COMP + ("|" + ce["compression_rx"] if ce else ""), ctxs, re.I) else ("exertion" if re.search(EXERT + ("|" + ce["exertion_rx"] if ce else ""), ctxs, re.I) else None)
        out.append((d, e))
    return out

# ---------------- 4. falls on an anticoagulant
HEAD = r"hit (?:his|her|their) head|head (?:hit|strike|struck|bump|knock)|banged (?:his|her) head|bumped (?:his|her) head|knocked (?:his|her) head|lump on (?:his|her) head|cut (?:on|above) (?:his|her)"
FELL = r"\bfell\b|had a fall|\bfallen\b|on the (?:\w+ )?floor\b|went down|go down|slipped|tripped(?! the)|lay on|long lie|could not get up|couldn't get up|got (?:herself|himself) up"
def fall_v12(c, ctx, L, P12, age_lo):
    trend = c.get("trend_last_7d") or ""; note = c.get("caregiver_or_nurse_note") or ""; pre, day0 = L.split_day0(trend); now = day0 + " " + note
    if L.find(HEAD, now) or L.find(r"\bpain\w*|hurts?\b|sore|cannot (?:bear|put) weight|swell\w*|bruis\w*|confus\w*", now): return None
    body_floor = [s for s in _sents(now) if L.find(FELL, s) and not re.search(r"\b(?:watch|band|device|phone|ring|tracker)\b[^.;]{0,40}\bfloor\b|\bfloor\b[^.;]{0,25}\b(?:watch|band|device)\b", s, re.I)]
    heavy_sit = L.find(r"(?:sat|sit|sits|sitting) (?:down )?(?:hard|heavily)|(?:sat|sit) down (?:hard|heavily)|dropped (?:heavily )?(?:on ?to|onto|into|on) (?:the |a |her |his )?(?:stool|chair|bed|sofa|seat|armchair|settee|toilet|bench)|plonked|sat down with a (?:bump|thud)", now)
    bump = L.find(r"bump\w*|knock\w*|bang\w*|caught (?:his|her|the) (?:wrist|hand|arm|elbow|door|frame)|hit (?:his|her) (?:wrist|hand|arm|elbow)|lurch\w*|jolt\w*|snagg\w*", now)
    ok = L.find(r"\bfine\b|no pain|nothing hurts|not hurt|okay|\bok\b|went (?:to|back)|carried on|kept (?:going|making)|walked", now, neg=False)
    witnessed = not re.search(r"no one (?:was )?(?:present|there|with (?:her|him))|nobody (?:saw|was)|unwitnessed|alone", note + " " + day0, re.I) and re.search(r"\bsaw\b|watched (?:her|him)|witness\w*|was with (?:her|him)|in the (?:same )?room|beside (?:her|him) when|present\b|heard (?:a|the) thump", note, re.I)
    if ctx["goals"] == "comfort_only": return {"route": "nurse_task", "reason": "fall_comfort_only_hospice_nurse", "escalation_target": "hospice_nurse"}
    inr = re.search(r"\bINR\s*(?:of\s*|was\s*)?(\d(?:\.\d)?)", note + " " + trend)
    if inr and re.search(r"warfarin|acenocoumarol", ctx["meds"], re.I) and float(inr.group(1)) >= P12["inr_provider_min"]:
        return {"route": "provider_task", "reason": "possible_fall_inr_high"}
    if age_lo is not None and age_lo >= P12["unwitnessed_age_min"] and not witnessed and not heavy_sit:
        return {"route": "provider_task", "reason": "unwitnessed_probable_fall_age85"}
    if heavy_sit and not body_floor: return {"route": "nurse_task", "reason": "heavy_sit_on_anticoagulant"}
    if bump and ok and not body_floor: return {"route": "nurse_task", "reason": "explained_bump_on_anticoagulant"}
    return None

def apply(case, c, out, ctx, L, T, P):
    """Return the v1.12.0 decision (dict) for case given the v1.11.2 decision out; out unchanged when no v1.12.0 rule applies."""
    V = (T.v110(P).get("v1120") or {})
    if not V.get("enabled"): return out
    trend = c.get("trend_last_7d") or ""; note = c.get("caregiver_or_nurse_note") or ""; pre, day0 = L.split_day0(trend); now = day0 + " " + note
    rule, tier, reason = out.get("rule"), out.get("tier"), out.get("reason")
    sym = symptomatic(now, L)
    bs = c.get("baseline_status") or {}; learning = bs.get("phase") == "learning"
    m = re.match(r"(\d{2,3})", c.get("age_band") or ""); age_lo = int(m.group(1)) if m else None
    def own(route_, reason_, rule_=None, **kw):
        d = {**out, "rule": rule_ or rule or "HT_V1120", "tier": "ABSOLUTE" if route_ == "urgent_page" else ("CONFIRM_FIRST" if route_ == "provider_task" and tier == "CONFIRM_FIRST" else "SUPPRESSED"), "reason": reason_, "owned_route": route_, "default_route": route_, "v1120": True, **kw}
        if route_ == "urgent_page": d.update(route="urgent_page", page=True)
        if ctx["goals"] == "comfort_only" and route_ in ("urgent_page", "nurse_task"): d["escalation_target"] = "hospice_nurse"
        d.pop("hitm_floor", None) if route_ != "provider_task" else None
        return d
    if rule in NEVER_LOWER or out.get("foundation"): return out
    copd = re.search(r"COPD|emphysema|chronic bronchitis", ctx["pmh"], re.I)
    # hospice respiratory distress (comfort-only) -> urgent page to the hospice nurse
    rr = [r[0] for r in L.recs(c, "rr") if not r[2]]
    sp = clean_spo2_day0(c, L)
    if ctx["goals"] == "comfort_only" and L.find(r"gasping|could not settle|can't settle|frightened|struggling to breathe|fighting for breath|distress\w*|short phrases|few words", now) and \
       ((rr and max(rr) >= V["hospice_rr_urgent"]) or (sp and min(x[0] for x in sp) < 88)):
        return own("urgent_page", "hospice_distressing_breathlessness", "HT_SPO2_LT88")
    # COPD patient band (varied wording), established phase
    band = spo2_band(c, L)
    if copd and band and not learning and not sym and tier != "ABSOLUTE":
        if sp:
            lo_v = min(x[0] for x in sp); o2 = home_o2(c, L)
            if lo_v >= band[0]:
                if o2: return own("silent_log", "within_patient_band_home_o2", "HT_SPO2_LT88", band=list(band))
                if band[0] <= V["band_low_max"]: return own("provider_task", "within_band_low_no_home_o2", "HT_SPO2_LT88", band=list(band))
                return own("silent_log", "within_patient_band", "HT_SPO2_LT88", band=list(band))
        else:
            allsp = L.recs(c, "spo2")
            if allsp and min(r[0] for r in allsp) < band[0]: return own("nurse_task", "flagged_reading_below_band_recheck", "HT_SPO2_LT88", band=list(band))
    # learning period, no band: DISABLED by default (learning_spo2_low=88, Wayne ruling 2026-10-24) -> 85-87 without a recheck stays urgent_page.
    # Kept only as a param-gated hook; with the threshold at 88 the range below is empty.
    if learning and not band and (tier == "CONFIRM_FIRST" and str(out.get("source", "")).startswith("learning:spo2") or reason == "outside_population_default_learning") and not sym:
        if sp:
            lo_v = min(x[0] for x in sp); tips = [x for x in sp if x[1] == "fingertip"]
            if V["learning_spo2_low"] <= lo_v < 88 and not tips: return own("provider_task", "learning_spo2_85_88_no_recheck", "HT_SPO2_LT88")
    # falls on an anticoagulant
    if ctx["anticoag"] and rule == "HT_FALL_ANTICOAG":
        f = fall_v12(c, ctx, L, V, age_lo)
        if f: return own(f["route"], f["reason"], "HT_FALL_ANTICOAG", **({"escalation_target": f["escalation_target"]} if f.get("escalation_target") else {}))
    # stable angina
    a = angina(c, ctx, L, V)
    if a and (rule in (None, "HT_CHEST_PAIN_VITALS") or str(out.get("source", "")) == "chest_pain"):
        if a["route"] == "urgent_page": return own("urgent_page", a["reason"], "HT_CHEST_PAIN_VITALS", features=a.get("features"))
        if tier != "ABSOLUTE" and not (out.get("inputs") or {}).get("red_flags") and not (out.get("inputs") or {}).get("ecg_change"):
            return own(a["route"], a["reason"], "HT_CHEST_PAIN_VITALS")
    # CKD drug low explained (any wording); repeated -> provider unless every event is compression (repeat compression = patient-specific override)
    GL = r"insulin|glargine|detemir|degludec|lispro|aspart|glipizide|gliclazide|glimepiride|glyburide|glibenclamide"
    if reason in ("recent_ckd_low_dose_review", "repeated_lows_dose_review", "ckd_low_dose_review", "ckd_low_compression_explained", "ckd_low_exertion_explained") and \
       re.search(GL, ctx["meds"], re.I) and re.search(r"CKD|chronic kidney|renal|eGFR", ctx["pmh"], re.I) and not sym:
        ev = ckd_low_events(c, L, P["hard_limits"]["glucose"]["danger_low"], (T.v110(P).get("v1111") or {}).get("ckd_low_explained"))
        if ev:
            idx = ev[-1]; prior = [e for e in ev[:-1] if idx[0] - e[0] <= V["ckd_repeat_days"]]
            if prior:
                if all(e[1] == "compression" for e in ev): return own("nurse_task", "ckd_low_compression_explained", "HT_VS_DANGER")
                return own("provider_task", "repeated_lows_dose_review", "HT_VS_DANGER")
            if idx[1] == "compression": return own("nurse_task", "ckd_low_compression_explained", "HT_VS_DANGER")
            if idx[1] == "exertion": return own("nurse_task", "ckd_low_exertion_explained", "HT_VS_DANGER")
            return own("provider_task", "ckd_low_dose_review", "HT_VS_DANGER")
    # high-risk gap partly explained by other device uploads -> nurse floor (Layer 1 owned)
    if rule == "HT_GAP48_HIGHRISK" and tier in ("SUPPRESSED", "CONFIRM_FIRST") and not sym:
        up = re.search(r"(?:scale|weigh\w*|weight|cuff|BP|glucometer|CGM)[^.;]{0,60}(?:upload\w*|sync\w*|both mornings|each morning|every morning|kept|continued|still)|kept weighing|weighed (?:herself|himself)", trend + " " + note, re.I)
        allgone = re.search(r"\bno (?:[\w-]+,? (?:or |and )?){1,4}(?:data|readings|uploads?)\b", trend + " " + note, re.I)
        if up and not allgone and (tier == "SUPPRESSED" or not L.find(r"did not answer|no answer|unanswered", now, neg=False)):
            return own("nurse_task", "gap_partly_explained_by_device_uploads", "HT_GAP48_HIGHRISK", floor_only=True)
    # motion-flagged / re-seated BP cleared by a clean repeat within the window -> silent (+ device ticket when the cuff was re-seated)
    cr = T.v110(P).get("clean_repeat") or {}
    if not sym and cr.get("bp_window_min"):
        bp = [r for r in L.readings(trend, "sbp") + L.readings(note, "sbp", default_day=0) if r[4] is not None and r[7] in (-1, 0)]
        for b in bp:
            bad = re.search(r"arm (?:movement|moved|lifted)|movement|moved (?:her|his) arm|lifted (?:her|his) arm|motion|talking|pinch\w*|re-?seat\w*|kinked|loose cuff|cuff (?:error|flag\w*)", b[1], re.I) or b[0] >= 160 or b[0] <= 90
            if not bad: continue
            rep = [r for r in bp if r[7] == b[7] and 0 < r[4] - b[4] <= cr["bp_window_min"] * 60 and cr["sbp_clean_low"] <= r[0] <= cr["sbp_clean_high"]]
            if rep and (tier in (None, "SUPPRESSED", "ARTIFACT", "LOG_ONLY") or rule == "HT_VS_DANGER"):
                tk = re.search(r"re-?seat\w*|pinch\w*|refit\w*|re-?position\w*", trend + " " + note, re.I)
                d = own("silent_log", "bp_cleared_by_clean_repeat", "HT_VS_DANGER")
                if tk: d["device_ticket"] = {"type": "device_maintenance", "interruptive": False, "detail": "BP cuff re-seated before a clean repeat", "route_to": "device_maintenance_process_else_whoever_can_check_the_device"}
                return d
    # device disagreement v2 (stable patient)
    if not sym and not out.get("device_ticket") and tier in (None, "SUPPRESSED", "ARTIFACT", "LOG_ONLY") and reason not in ("goals_of_care",):
        dd = device_disagreement_v2(c, ctx, L, V)
        if dd and (tier is None or rule in ("HT_SPO2_LT88", "HT_DEVICE_DISAGREE") or reason in ("unreliable_reading", "below_band_threshold")):
            d = own("nurse_task" if dd["changes_care"] else "silent_log", ("device_disagreement_could_change_care" if dd["vital"] == "hr" and any(re.search(r"olol|diltiazem|verapamil|digoxin", m.get("name", ""), re.I) for m in c.get("recent_med_changes") or []) else "device_disagreement_changes_care") if dd["changes_care"] else "device_disagreement", "HT_DEVICE_DISAGREE")
            d["device_ticket"] = {"type": dd["ticket"], "interruptive": False, "detail": dd["detail"], "route_to": "device_maintenance_process_else_whoever_can_check_the_device"}
            return d
    return out
