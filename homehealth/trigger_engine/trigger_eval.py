"""trigger_eval.py: three-layer vital-sign trigger evaluation (SMART_TRIGGERS.md section 6). SYNTHETIC / design reference.

Layer 1 HARD LIMITS: fixed values from trigger_params.json, never learned. A physiologically implausible value, a non-physiologic
         rate of change or a flatline with motion -> ARTIFACT (auto recheck, no page). A danger value -> ABSOLUTE (HT_VS_DANGER),
         regardless of baseline. Only a human changes them: apply_param_change(approved_by=...).
Layer 2 LEARNING: a per-patient onboarding window learns baselines per vital x activity_state x time_of_day. While learning:
         conservative population defaults, confirm-first widened, and no at_patient_baseline suppression.
Layer 3 ADAPTATION: rolling weighted median/MAD. A condition change (new dx, rate-control med, hospitalization, hospice ...)
         partially resets the affected vitals and re-enters a shortened learning period. A slow monotonic drift toward abnormal is
         NOT absorbed: it is flagged SUBTLE_DETERIORATION_TREND, the vital is frozen and the drifting samples are excluded.
Every adaptive change is clamped inside learn_bounds (which sit inside the hard limits) and appended to Baseline.log.
Time is in seconds; DAY = 86400.
"""
import json, math, copy, datetime
DAY = 86400.0
QUALITY_FLAGS = {"motion", "poor_contact", "off_wrist", "low_perfusion", "cold_fingers", "charging"}

def load_params(path):
    p = json.load(open(path)); validate_params(p); return p

def validate_params(p):
    """Bounds must nest: implausible < danger <= learn_bounds and population bands. Raises ValueError."""
    for v, h in p["hard_limits"].items():
        if v.startswith("_"): continue
        lo, hi = h["implausible_low"], h["implausible_high"]
        if h["danger_low"] is not None and not lo < h["danger_low"]: raise ValueError(f"{v}: danger_low must be > implausible_low")
        if h["danger_high"] is not None and not h["danger_high"] < hi: raise ValueError(f"{v}: danger_high must be < implausible_high")
        b = p["adaptation"]["learn_bounds"][v]
        dl = h["danger_low"] if h["danger_low"] is not None else lo; dh = h["danger_high"] if h["danger_high"] is not None else hi
        if not (dl <= b[0] < b[1] <= dh): raise ValueError(f"{v}: learn_bounds {b} not inside hard limits [{dl},{dh}]")
        for st, band in p["population_defaults"][v].items():
            if not (lo < band[0] < band[1] <= hi): raise ValueError(f"{v}/{st}: population band outside implausible limits")
    lt = p["learning"].get("outside_population_default_tier", "CONFIRM_FIRST")   # v1.8: never silent during learning
    if lt not in ("CONFIRM_FIRST", "ABSOLUTE"): raise ValueError("learning.outside_population_default_tier must be CONFIRM_FIRST or ABSOLUTE (a reading beyond the population defaults is never silent while learning)")
    cc = p["adaptation"]["condition_change"]
    if not cc["relearn_days"] > cc["retain_weight"] * p["adaptation"]["rolling_window_days"]:
        raise ValueError("relearn_days must exceed retain_weight x rolling_window_days so new data outweighs the old baseline after relearning")

def apply_param_change(path, keys, new_value, approved_by, reason):
    """The ONLY way to change trigger_params.json. Needs a named human approver and is appended to change_log."""
    if not approved_by or not isinstance(approved_by, str) or approved_by.lower().startswith(("engine", "auto", "system", "model")):
        raise PermissionError("trigger params can only be changed by a named human approver")
    p = json.load(open(path)); node = p
    for k in keys[:-1]: node = node[k]
    old = node.get(keys[-1]); node[keys[-1]] = new_value   # new keys allowed (old=None), still human-approved + logged
    validate_params(p)
    p["change_log"].append({"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "keys": keys, "old": old, "new": new_value, "approved_by": approved_by, "reason": reason})
    json.dump(p, open(path, "w"), indent=1); return p

def tod_bin(ts, p):
    h = (ts % DAY) / 3600.0
    for name, (a, b) in p["learning"]["time_of_day_bins"].items():
        if a <= h < b: return name
    return "night"

def wquantile(vals, wts, q):
    pairs = sorted((v, w) for v, w in zip(vals, wts) if w > 0)
    tot = sum(w for _, w in pairs)
    if not pairs: return None
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= q * tot: return v
    return pairs[-1][0]

def kendall_tau(xs, ys):
    n = len(xs); c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (xs[i] - xs[j]) * (ys[i] - ys[j])
            if s > 0: c += 1
            elif s < 0: d += 1
    return (c - d) / (n * (n - 1) / 2) if n > 1 else 0.0

class Baseline:
    """Per-patient baseline object + state. Serializable with to_dict/from_dict."""
    def __init__(self, patient_id, enrolled_ts, params, clinician_set=None):
        self.p = params; self.patient_id = patient_id; self.enrolled_ts = enrolled_ts
        self.learning_until = enrolled_ts + params["learning"]["onboarding_days"] * DAY
        self.relearn_until = {}          # vital -> ts
        self.samples = {}                # vital -> list of [ts, value, activity, tod, weight]
        self.daily_rest = {}             # vital -> {day_index: [values]}  (all reliable rest readings, learned or not; drift guard input)
        self.frozen = {}                 # vital -> {"since": ts, "reason": str, "total_change": x}
        self.events = []                 # condition changes
        self.clinician_set = clinician_set or {}   # vital -> {activity: [lo, hi], "set_by": name}
        self.log = []
        self._last_drift_day = {}
        self._clamp_logged = set()
    # ---- state
    def phase(self, vital, ts):
        if ts < self.learning_until: return "learning"
        if ts < self.relearn_until.get(vital, -1): return "relearning"
        return "established"
    def _log(self, ts, kind, **kw):
        self.log.append({"ts": ts, "day": round((ts - self.enrolled_ts) / DAY, 2), "type": kind, **kw})
    # ---- learning
    def add_sample(self, r):
        """Learn from a reliable reading. Returns a drift flag dict or None."""
        v, ts, x = r["vital"], r["ts"], r["value"]
        h = self.p["hard_limits"][v]
        if (r.get("quality_flags") and set(r["quality_flags"]) & QUALITY_FLAGS) or not (h["implausible_low"] <= x <= h["implausible_high"]):
            return None   # artifacts are never learned
        act = r.get("activity_state", "rest")
        day = int((ts - self.enrolled_ts) // DAY)
        if act == self.p["adaptation"]["drift_guard"]["stratum"]:
            self.daily_rest.setdefault(v, {}).setdefault(day, []).append(x)
        flag = None
        if self._last_drift_day.get(v) != day:
            self._last_drift_day[v] = day; flag = self.check_drift(v, ts)
        if v in self.frozen:
            return flag
        S = self.samples.setdefault(v, [])
        S.append([ts, x, act, tod_bin(ts, self.p), 1.0])
        lim = ts - self.p["adaptation"]["rolling_window_days"] * DAY
        if S and S[0][0] < lim: self.samples[v] = [s for s in S if s[0] >= lim]
        return flag
    def stats(self, vital, activity, ts):
        """Weighted median/MAD for the stratum (activity x tod -> activity only -> None). Median clamped to learn_bounds (logged)."""
        S = self.samples.get(vital, []); tod = tod_bin(ts, self.p); mn = self.p["learning"]["min_samples_per_stratum"]
        for level, sel in (("activity_tod", [s for s in S if s[2] == activity and s[3] == tod]), ("activity", [s for s in S if s[2] == activity])):
            if sum(1 for s in sel if s[4] > 0) >= mn:
                vals = [s[1] for s in sel]; wts = [s[4] for s in sel]
                med = wquantile(vals, wts, 0.5)
                mad = wquantile([abs(x - med) for x in vals], wts, 0.5)
                lb = self.p["adaptation"]["learn_bounds"][vital]; cm = min(max(med, lb[0]), lb[1])
                if cm != med:
                    key = (vital, activity, int(ts // DAY))
                    if key not in self._clamp_logged:
                        self._clamp_logged.add(key); self._log(ts, "BOUND_CLAMP", vital=vital, activity=activity, learned=med, clamped=cm, bounds=lb)
                    med = cm
                mad = max(mad, self.p["adaptation"]["mad_floor"][vital])
                return {"median": med, "mad": mad, "n": len(sel), "level": level}
        return None
    # ---- adaptation
    def condition_change(self, ctype, ts, detail=""):
        cc = self.p["adaptation"]["condition_change"]
        if ctype not in cc["affected_vitals"]: raise ValueError(f"unknown condition change {ctype}")
        vit = cc["affected_vitals"][ctype]
        for v in vit:
            for s in self.samples.get(v, []): s[4] *= cc["retain_weight"]
            self.relearn_until[v] = ts + cc["relearn_days"] * DAY
        self.events.append({"type": ctype, "ts": ts, "detail": detail, "vitals": vit})
        self._log(ts, "PARTIAL_RESET", condition=ctype, detail=detail, vitals=vit, retain_weight=cc["retain_weight"], relearn_until_day=round((ts + cc["relearn_days"] * DAY - self.enrolled_ts) / DAY, 2))
    def check_drift(self, vital, ts):
        g = self.p["adaptation"]["drift_guard"]
        if not g["enabled"] or vital in self.frozen: return None
        day = int((ts - self.enrolled_ts) // DAY)
        D = self.daily_rest.get(vital, {})
        days = [d for d in sorted(D) if day - g["window_days"] <= d < day]   # completed days only
        if len(days) < g["min_days"]: return None
        med = [sorted(D[d])[len(D[d]) // 2] for d in days]
        tau = kendall_tau(days, med)
        k = max(1, min(3, len(med) // 4)); change = sum(med[-k:]) / k - sum(med[:k]) / k
        direc = g["abnormal_direction"][vital]
        toward = (direc in ("up", "both") and tau >= g["min_kendall_tau"] and change >= g["min_total_change"][vital]) or \
                 (direc in ("down", "both") and tau <= -g["min_kendall_tau"] and change <= -g["min_total_change"][vital])
        if not toward: return None
        recent = [e for e in self.events if vital in e["vitals"] and ts - e["ts"] <= g["explained_by_condition_change_days"] * DAY]
        if recent:
            self._log(ts, "DRIFT_EXPLAINED", vital=vital, tau=round(tau, 2), total_change=round(change, 2), by=recent[-1]["type"]); return None
        start_ts = self.enrolled_ts + days[0] * DAY
        n_ex = 0
        for s in self.samples.get(vital, []):
            if s[0] >= start_ts and s[4] > 0: s[4] = 0.0; n_ex += 1
        self.frozen[vital] = {"since": ts, "reason": "SUBTLE_DETERIORATION_TREND", "total_change": round(change, 2), "tau": round(tau, 2)}
        self._log(ts, "DRIFT_FLAG", vital=vital, tau=round(tau, 2), total_change=round(change, 2), window_days=len(days), samples_excluded=n_ex, action="freeze learning; route for review")
        return {"flag": "SUBTLE_DETERIORATION_TREND", "vital": vital, "tau": round(tau, 2), "total_change": round(change, 2)}
    def clear_drift(self, vital, ts, approved_by, note=""):
        """A reviewed drift is released only by a human; learning resumes from now."""
        if not approved_by: raise PermissionError("drift review must be cleared by a named human")
        self.frozen.pop(vital, None); self._log(ts, "DRIFT_CLEARED", vital=vital, approved_by=approved_by, note=note)
    def to_dict(self):
        d = {k: copy.deepcopy(getattr(self, k)) for k in ("patient_id", "enrolled_ts", "learning_until", "relearn_until", "samples", "frozen", "events", "clinician_set", "log", "_last_drift_day")}
        d["daily_rest"] = {v: {str(k): x for k, x in dd.items()} for v, dd in self.daily_rest.items()}; return d
    @classmethod
    def from_dict(cls, d, params):
        b = cls(d["patient_id"], d["enrolled_ts"], params, d["clinician_set"])
        for k in ("learning_until", "relearn_until", "samples", "frozen", "events", "log", "_last_drift_day"): setattr(b, k, d[k])
        b.daily_rest = {v: {int(k): x for k, x in dd.items()} for v, dd in d["daily_rest"].items()}; return b

def _decision(tier, reason, route, page, rule=None, recheck=None, **kw):
    return {"tier": tier, "reason": reason, "route": route, "page": page, "rule": rule, "recheck": recheck, **kw}

def _cgm_pressure_low(r, p):
    """CGM pressure-low ('compression low') artifact rule. trigger_params.json -> cgm_pressure_low (placeholders).
    Applies to a CGM reading at or below the glucose danger limit. r["cgm"] = {overnight, sensor_side_sleep, pressure_documented,
    drop_rebound, fingerstick: {value, minutes_apart}|None, symptoms: bool}. Returns a decision, or None to fall through to the
    normal hard-limit logic. Order:
      1. Fingerstick within the window and <= danger limit -> ABSOLUTE (confirmed).
      2. Symptoms of hypoglycaemia -> ABSOLUTE (even with pressure signs).
      3. Fingerstick within the window and above the danger limit -> SUPPRESSED unreliable_reading (CGM low not confirmed; already rechecked).
      4. Any pressure sign (pinned/pressed sensor documented, overnight sensor-side sleep, rapid drop and rebound) -> ARTIFACT, fingerstick recheck.
      5. Otherwise None (danger value stands -> ABSOLUTE)."""
    cp = p.get("cgm_pressure_low") or {}
    h = p["hard_limits"]["glucose"]; x = r["value"]
    if not cp.get("enabled") or h["danger_low"] is None or x > h["danger_low"]: return None
    g = r.get("cgm") or {}; fs = g.get("fingerstick")
    fs_ok = fs is not None and fs.get("value") is not None and (fs.get("minutes_apart") is None or fs["minutes_apart"] <= cp["fingerstick_window_min"])
    signs = [k for k in ("pressure_documented", "sensor_side_sleep", "drop_rebound") if g.get(k)]
    if g.get("sensor_side_sleep") and not g.get("overnight"): signs.remove("sensor_side_sleep")
    if fs_ok:
        disc = fs["value"] - x >= max(cp["discordant_abs_mg_dl"], cp["discordant_pct"] * x)
        if disc: signs.append("discordant_fingerstick")
    if fs_ok and fs["value"] <= h["danger_low"]:
        return _decision("ABSOLUTE", "hard_limit_danger_fingerstick_confirmed", "urgent_page", True, "HT_VS_DANGER", cgm_signs=signs)
    if g.get("symptoms"):
        return _decision("ABSOLUTE", "hard_limit_danger_symptomatic", "urgent_page", True, "HT_VS_DANGER", cgm_signs=signs)
    if fs_ok:
        return _decision("SUPPRESSED", "unreliable_reading", "silent_log", False, "HT_VS_DANGER", None, basis="cgm_low_not_confirmed_by_fingerstick", cgm_signs=signs, hitm_sample=True)
    if signs:
        return _decision("ARTIFACT", "cgm_pressure_low_suspected", "silent_log", False, "HT_VS_IMPLAUSIBLE", {"step": cp["recheck_step"], "timeout_min": cp["recheck_timeout_min"]}, cgm_signs=signs)
    return None

# ---------------- goals of care (v1.5 hospice narrowing, Wayne 2026-10-18, GC2-003) ----------------
def urgent_comfort_basis(r, base, p, context=None):
    """Return the reason a fired trigger in a comfort-only/hospice patient is an URGENT, treatable, goal-consistent comfort problem
    (-> urgent hospice-nurse page now), or None. trigger_params.json -> goals_of_care.urgent_comfort (placeholders).
    context["comfort_treatable"] = True lets the caller (or a clinician-set plan) declare one explicitly."""
    ctx = context or {}; uc = (p.get("goals_of_care") or {}).get("urgent_comfort") or {}
    if not uc.get("enabled"): return None
    if ctx.get("comfort_treatable"): return "declared_comfort_treatable"
    cond = uc.get("conditions") or {}
    # v1.6 (Wayne 2026-10-18): distressing breathlessness that can be treated at home (respiratory trigger + context
    # breathlessness = {"distressing": True, "home_treatable": True}); treatment that needs a hospital stays hospital-directed.
    br = ctx.get("breathlessness") or {}
    if cond.get("breathlessness_distressing_home_treatable") and br.get("distressing") and br.get("home_treatable") \
       and (r is None or r.get("vital") in uc.get("breathlessness_vitals", ["spo2", "rr"])) and ctx.get("trigger_family", "respiratory" if r else None) == "respiratory":
        return "breathlessness_distressing_home_treatable"
    if not r or r.get("vital") != "glucose": return None
    h = p["hard_limits"]["glucose"]; x = r.get("value")
    if h["danger_low"] is None or x is None or x > h["danger_low"]: return None
    if cond.get("hypoglycemia_symptomatic") and ((r.get("cgm") or {}).get("symptoms") or r.get("symptoms") or ctx.get("symptoms")): return "hypoglycemia_symptomatic"
    # v1.7 (Wayne 2026-10-18): hypoglycemia_recurrent is DISABLED in params (only symptomatic lows qualify); the check stays for re-enabling.
    if cond.get("hypoglycemia_recurrent") and base is not None:
        win = uc["recurrent_window_h"] * 3600.0
        for e in base.log:
            if e.get("type") == "DECISION" and e.get("vital") == "glucose" and isinstance(e.get("value"), (int, float)) and e["value"] <= h["danger_low"] \
               and 0 < r["ts"] - e["ts"] <= win and e.get("tier") not in ("ARTIFACT",) and e.get("reason") != "unreliable_reading":
                return "hypoglycemia_recurrent"
    return None

def apply_goals_of_care(d, p, context=None, basis=None):
    """SMART_TRIGGERS check 4 (v1.5). With a comfort-only/hospice plan, goals-of-care suppression applies to HOSPITAL-DIRECTED escalation only.
    basis (from urgent_comfort_basis) set -> keep the tier, page the hospice nurse NOW (urgent_page, escalation_target hospice_nurse).
    Otherwise -> SUPPRESSED goals_of_care, nurse_task (same-shift hospice nurse contact), as before."""
    ctx = context or {}
    if ctx.get("goals") != "comfort_only" or d["tier"] not in ("ABSOLUTE", "CONFIRM_FIRST"): return d
    gc = p.get("goals_of_care") or {}; uc = gc.get("urgent_comfort") or {}
    if basis:
        return {**d, "route": "urgent_page", "page": True, "escalation_target": uc.get("escalation_target", "hospice_nurse"), "notify": uc.get("notify", "hospice_nurse_urgent_page"),
                "hospital_directed": False, "goals_basis": basis, "confirm_step": None if d["tier"] == "ABSOLUTE" else d.get("confirm_step")}
    return {**d, "tier": "SUPPRESSED", "reason": "goals_of_care", "route": "nurse_task", "page": False, "notify": gc.get("default_notify", "hospice_nurse_same_shift"),
            "original_tier": d["tier"], "hitm_sample": True, "confirm_step": None, "timeout_min": None, "recheck": None}

# ---------------- confirm-step outcome (v1.5, Wayne 2026-10-17, ST2-009) ----------------
def resolve_confirm(d, outcome, p, context=None):
    """Resolve a CONFIRM_FIRST decision once its confirm step has an outcome.
    outcome: 'confirmed' -> escalate now. 'no_answer' -> if the step is a patient-directed prompt (patient_call / watch_prompt) and the
    patient LIVES ALONE, the unanswered prompt counts as a FAILED confirm -> escalate now (confirm_step already_confirmed);
    otherwise keep waiting for the timeout. 'pending' -> unchanged. trigger_params.json -> confirm_first.unanswered_prompt."""
    ctx = context or {}
    if d.get("tier") != "CONFIRM_FIRST": return d
    step = d.get("confirm_step") or (d.get("recheck") or {}).get("step")
    if outcome == "pending": return d
    if outcome == "confirmed":
        return {**d, "page": True, "confirm_step": "already_confirmed", "timeout_min": None, "confirm_result": "confirmed"}
    if outcome == "no_answer":
        up = p["confirm_first"].get("unanswered_prompt") or {}
        if up.get("enabled") and ctx.get("lives_alone") and step in up.get("prompt_steps", []):
            return {**d, "page": True, "confirm_step": "already_confirmed", "timeout_min": None, "confirm_result": "unanswered_prompt_lives_alone", "prompt_step": step}
        return {**d, "confirm_result": "no_answer_waiting_for_timeout"}
    raise ValueError(f"unknown confirm outcome {outcome!r}")

def evaluate(r, base, p, context=None):
    """r: {vital, value, ts, activity_state, quality_flags, motion, prev:{value, dt_s}, flat_s}. context: {goals: None|'comfort_only'}.
    Returns a decision; non-NORMAL decisions are appended to base.log."""
    ctx = context or {}; v, x, ts = r["vital"], r["value"], r["ts"]; act = r.get("activity_state", "rest")
    h = p["hard_limits"][v]; cf = p["confirm_first"]; steps = cf["default_steps"]; tmo = cf["timeouts_min"]
    rc_step = "fingertip_recheck" if v == "spo2" else "device_recheck"
    d = None
    cg = _cgm_pressure_low(r, p) if v == "glucose" and r.get("source") == "cgm" else None
    if cg is not None:
        d = cg
    # Layer 1a: implausible -> ARTIFACT
    elif x < h["implausible_low"] or x > h["implausible_high"]:
        d = _decision("ARTIFACT", "implausible_value", "silent_log", False, "HT_VS_IMPLAUSIBLE", {"step": rc_step, "timeout_min": tmo[rc_step]})
    elif h.get("max_rate_per_s") and r.get("prev") and r["prev"].get("dt_s") and abs(x - r["prev"]["value"]) / r["prev"]["dt_s"] > h["max_rate_per_s"]:
        d = _decision("ARTIFACT", "nonphysiologic_rate", "silent_log", False, "HT_VS_IMPLAUSIBLE", {"step": rc_step, "timeout_min": tmo[rc_step]})
    elif h.get("flatline_s") and r.get("flat_s", 0) >= h["flatline_s"] and r.get("motion"):
        d = _decision("ARTIFACT", "flatline_with_motion", "silent_log", False, "HT_VS_IMPLAUSIBLE", {"step": rc_step, "timeout_min": tmo[rc_step]})
    elif set(r.get("quality_flags") or []) & QUALITY_FLAGS:
        danger = (h["danger_low"] is not None and x <= h["danger_low"]) or (h["danger_high"] is not None and x >= h["danger_high"])
        below = v == "spo2" and x < cf["spo2_population_threshold"]
        if danger or below:   # trigger fired on an unreliable reading: suppressed, logged, auto recheck
            d = _decision("SUPPRESSED", "unreliable_reading", "silent_log", False, "HT_VS_DANGER" if danger else "HT_SPO2_LT88", {"step": rc_step, "timeout_min": tmo[rc_step]}, hitm_sample=True)
        else:
            d = _decision("NORMAL", "unreliable_reading_not_learned", "silent_log", False)
    # Layer 1b: danger -> ABSOLUTE regardless of baseline
    elif (h["danger_low"] is not None and x <= h["danger_low"]) or (h["danger_high"] is not None and x >= h["danger_high"]):
        d = _decision("ABSOLUTE", "hard_limit_danger", "urgent_page", True, "HT_VS_DANGER")
    else:
        ph = base.phase(v, ts); st = base.stats(v, act, ts) if ph != "learning" else None
        pop = p["population_defaults"][v][act]; cs = (base.clinician_set.get(v) or {}).get(act)
        spo2_low = v == "spo2" and x < cf["spo2_population_threshold"]
        rule = "HT_SPO2_LT88" if spo2_low else "HT_VS_BASELINE"
        step = steps[v]; conf = {"step": step, "timeout_min": tmo[step]}
        if cs and cs[0] <= x <= cs[1] and spo2_low:   # clinician-set baseline allows at-baseline suppression even while learning
            d = _decision("SUPPRESSED", "at_patient_baseline", "silent_log", False, rule, None, basis="clinician_set_baseline", hitm_sample=True)
        elif ph == "learning" or st is None:
            if not (pop[0] <= x <= pop[1]) or spo2_low:   # v1.8 learning-period rule (Wayne): beyond population defaults -> CONFIRM_FIRST, not silent
                lt = p["learning"].get("outside_population_default_tier", "CONFIRM_FIRST")
                if lt == "ABSOLUTE": d = _decision("ABSOLUTE", "outside_population_default_" + ph, "urgent_page", True, rule, phase=ph)
                else: d = _decision("CONFIRM_FIRST", "outside_population_default_" + ph, "urgent_page", "if_confirmed_or_timeout", rule, conf, phase=ph, learning_rule="v1.8")
            else:
                d = _decision("NORMAL", "within_population_default_" + ph, "silent_log", False, phase=ph)
        else:
            z = (x - st["median"]) / (1.4826 * st["mad"])
            zc, zw = p["adaptation"]["z_confirm"], p["adaptation"]["z_watch"]
            if ph == "relearning" and pop[0] <= x <= pop[1] and not spo2_low:
                d = _decision("NORMAL", "relearning_within_population", "silent_log", False, phase=ph, z=round(z, 2))
            elif abs(z) >= zc:
                d = _decision("CONFIRM_FIRST", "baseline_deviation", "urgent_page", "if_confirmed_or_timeout", rule, conf, phase=ph, z=round(z, 2), baseline=st)
            elif spo2_low:
                d = _decision("SUPPRESSED", "at_patient_baseline", "silent_log", False, rule, None, phase=ph, z=round(z, 2), baseline=st, hitm_sample=True)
            elif abs(z) >= zw:
                d = _decision("WATCH", "baseline_deviation_small", "silent_log", False, phase=ph, z=round(z, 2))
            else:
                d = _decision("NORMAL", "within_patient_baseline", "silent_log", False, phase=ph, z=round(z, 2))
    # goals of care apply to every tier (SMART_TRIGGERS check 4)
    if ctx.get("goals") == "comfort_only" and d["tier"] in ("ABSOLUTE", "CONFIRM_FIRST"):   # v1.5: narrowed to hospital-directed escalation
        d = apply_goals_of_care(d, p, ctx, urgent_comfort_basis(r, base, p, ctx))
    # drift review flag (layer 3)
    if v in base.frozen:
        d["drift_flag"] = base.frozen[v]
        if d["route"] == "silent_log": d["route"] = "provider_task"; d["reason"] += "+SUBTLE_DETERIORATION_TREND"
    if d["tier"] != "NORMAL" or "drift_flag" in d:
        base._log(ts, "DECISION", vital=v, value=x, tier=d["tier"], reason=d["reason"], route=d["route"], rule=d["rule"])
    return d

# ---------------- chest pain: parametric HT_CHEST_PAIN_VITALS (SMART_TRIGGERS.md section 7) ----------------
BAND_ORDER = ["D", "C", "B", "A"]
def _shift(band, n):
    i = max(0, min(3, BAND_ORDER.index(band) + n)); return BAND_ORDER[i]

def _vital_band(vital, x, cp):
    """Return (band, side) for a vital value given chest-pain thresholds; ("D", None) if within all bands."""
    vb = cp["vital_bands"][vital]
    for side in ("high", "low"):
        th = vb.get(side)
        if not th: continue
        for b in ("A", "B", "C"):
            t = th.get(b)
            if t is None: continue
            if (side == "high" and x >= t) or (side == "low" and x <= t): return b, side
    return "D", None

def evaluate_chest_pain(inp, p, base=None, context=None):
    """inp: {ts, activity_state: sleep|rest|active, minutes_since_exertion, vitals: {hr|sbp|spo2|rr: {value, quality_flags}},
             symptoms: {chest_pain, severity, red_flags: [...], concordant: True|False|None, ecg_change, ecg_reliable}, already_confirmed}
    context: {rate_control_med, pacemaker_lower_rate, known_brady_range, known_tachy_range, goals}
    Output: tier ABSOLUTE | CONFIRM_FIRST (band-scaled timeout) | LOG_ONLY (or SUPPRESSED goals_of_care); every applied modifier is listed."""
    ctx = context or {}; cp = p["chest_pain"]; M = cp["modifiers"]; sym = inp.get("symptoms") or {}
    if not sym.get("chest_pain"): return None
    ts = inp.get("ts", 0.0); mods = []; unreliable = []
    def out(tier, band, raw, rule, **kw):
        d = {"rule": rule, "tier": tier, "band": band, "raw_band": raw, "modifiers": mods, "unreliable_vitals": unreliable, **kw}
        if tier == "ABSOLUTE": d.update(route="urgent_page", page=True, confirm_step=None, timeout_min=None)
        elif tier == "LOG_ONLY": d.update(route=cp["bands"]["D"]["route"], page=False, confirm_step=None, timeout_min=None)
        if ctx.get("goals") == "comfort_only" and tier in ("ABSOLUTE", "CONFIRM_FIRST"):   # v1.5 narrowing; chest pain is urgent-comfort only if declared
            d = apply_goals_of_care(d, p, ctx, urgent_comfort_basis(None, None, p, ctx))
        if base is not None: base._log(ts, "CHEST_PAIN_DECISION", tier=d["tier"], band=band, raw_band=raw, modifiers=mods, route=d["route"])
        return d
    # 1. hard limits (reliable danger -> ABSOLUTE; implausible -> treated as unreliable)
    reliable = {}
    for v, r in (inp.get("vitals") or {}).items():
        h = p["hard_limits"][v]; x = r["value"]
        if (set(r.get("quality_flags") or []) & QUALITY_FLAGS) or not (h["implausible_low"] <= x <= h["implausible_high"]):
            unreliable.append(v); continue
        if (h["danger_low"] is not None and x <= h["danger_low"]) or (h["danger_high"] is not None and x >= h["danger_high"]):
            mods.append(f"{v}={x} hard danger limit"); return out("ABSOLUTE", "A", "A", "HT_VS_DANGER")
        reliable[v] = x
    # 2. reliable ECG change
    if sym.get("ecg_change") and sym.get("ecg_reliable", True):
        mods.append("reliable ECG change"); return out("ABSOLUTE", "A", "A", "HT_CHEST_PAIN_ECG")
    # 3. per-vital band + side-specific context modifiers
    act = inp.get("activity_state", "rest"); mse = inp.get("minutes_since_exertion")
    post_ex = mse is not None and mse <= M["post_exertion"]["window_min"]
    net = {}; raw_worst = "D"
    for v, x in reliable.items():
        b, side = _vital_band(v, x, cp)
        if BAND_ORDER.index(b) > BAND_ORDER.index(raw_worst): raw_worst = b
        if side is None: continue                 # unbanded vital: no contribution
        s = 0; key = f"{v}_{side}"
        if v == "hr" and ctx.get("pacemaker_lower_rate"):
            lr = ctx["pacemaker_lower_rate"]; tol = M["pacemaker"]["tolerance_bpm"]
            if side == "low" and x >= lr - tol: mods.append(f"pacemaker: HR {x} at lower rate {lr} -> not banded"); continue
            if x < lr - tol: s += M["pacemaker"]["below_lower_rate"]; mods.append(f"pacemaker: HR {x} below lower rate {lr} +1")
        if act == "sleep" and key in M["sleep"]: s += M["sleep"][key]; mods.append(f"sleep {key} {M['sleep'][key]:+d}")
        if post_ex and key in M["post_exertion"]: s += M["post_exertion"][key]; mods.append(f"post-exertion ({mse} min) {key} {M['post_exertion'][key]:+d}")
        if ctx.get("rate_control_med") and key in M["rate_control_med"]: s += M["rate_control_med"][key]; mods.append(f"rate-control med {key} {M['rate_control_med'][key]:+d}")
        kb = ctx.get("known_brady_range")
        if v == "hr" and side == "low" and kb and x >= kb[0] - 3: s += M["known_brady"]["hr_low"]; mods.append(f"known brady {kb} -1")
        kt = ctx.get("known_tachy_range")
        if v == "hr" and side == "high" and kt and x <= kt[1] + 10: s += M["known_tachy"]["hr_high"]; mods.append(f"known tachy {kt} -1")
        net[v] = BAND_ORDER.index(b) + s          # v1.5: net, NOT clamped yet
    # v1.5 band math (Wayne 2026-10-17, ST4-002): net ALL modifiers first, then apply the floor/ceiling clamps once.
    # base = worst net of the BANDED vitals (unbanded vitals do not contribute); no banded vital -> band D (0).
    total = max(net.values()) if net else 0
    clampi = lambda i: max(0, min(3, i))
    vb = {v: BAND_ORDER[clampi(n)] for v, n in net.items()}   # per-vital (clamped) only for the multi-vital count / reporting
    # 4. symptom-level modifiers (conditions read the provisional clamped band; shifts are added to the unclamped net)
    if sum(1 for b in vb.values() if b in ("A", "B")) >= M["multi_vital"]["min_vitals_at_B_or_worse"]:
        total += M["multi_vital"]["shift"]; mods.append("multi-vital (>=2 at band B or worse) +1")
    rf = [f for f in (sym.get("red_flags") or []) if f in M["red_flags"]["features"]]
    if rf:
        n = min(len(rf) * M["red_flags"]["per_flag"], M["red_flags"]["max_total"]); total += n; mods.append(f"red flags {rf} +{n}")
    if sym.get("concordant") is True and BAND_ORDER[clampi(total)] != "A": total += M["concordance"]["concordant"]; mods.append("symptom-vital concordant +1")
    elif sym.get("concordant") is False and BAND_ORDER[clampi(total)] in ("B", "C"): total += M["concordance"]["discordant"]; mods.append("symptom-vital discordant -1")
    # 5. clamps, applied once to the net: ceiling A / floor D, then the safety floors
    band = BAND_ORDER[clampi(total)]
    if total != clampi(total): mods.append(f"net band index {total} clamped to {band}")
    floor = _shift(raw_worst, -cp["safety"]["max_total_downgrade"])
    if raw_worst == "A" and BAND_ORDER.index(floor) < BAND_ORDER.index(cp["safety"]["band_A_floor"]): floor = cp["safety"]["band_A_floor"]
    if BAND_ORDER.index(band) < BAND_ORDER.index(floor): mods.append(f"safety floor {band}->{floor}"); band = floor
    # 5b. decided rule (Wayne 2026-10-17): crescendo pattern -> at least CONFIRM_FIRST even with normal vitals
    cr = cp.get("crescendo_rule") or {}
    if cr.get("enabled") and "crescendo_pattern" in (sym.get("red_flags") or []) and BAND_ORDER.index(band) < BAND_ORDER.index(cr["min_band"]):
        mods.append(f"crescendo rule floor {band}->{cr['min_band']}"); band = cr["min_band"]
    pattern_driven = raw_worst == "D" and band != "D"   # vitals normal; band comes from the symptom pattern
    # 6. output
    if band == "A": return out("ABSOLUTE", "A", raw_worst, "HT_CHEST_PAIN_VITALS")
    lo, hi = cp["timeout_bounds_min"]
    if unreliable:
        dr = M["device_reliability"]; mods.append(f"unreliable {unreliable} -> recheck")
        return out("CONFIRM_FIRST", band, raw_worst, "HT_CHEST_PAIN_VITALS", route="urgent_page", page="if_confirmed_or_timeout", confirm_step=dr["recheck_step"] + "+patient_call", timeout_min=dr["recheck_timeout_min"])
    if band == "D": return out("LOG_ONLY", "D", raw_worst, "HT_CHEST_PAIN_VITALS", reason="below_band_threshold")
    if inp.get("already_confirmed"):
        return out("CONFIRM_FIRST", band, raw_worst, "HT_CHEST_PAIN_VITALS", route="urgent_page", page=True, confirm_step="already_confirmed", timeout_min=None)
    t = cp["bands"][band]["timeout_min"]; f = 1.0
    if post_ex and not (pattern_driven and (cp.get("crescendo_rule") or {}).get("no_exertion_timeout_factor_when_vitals_normal")):
        f *= M["post_exertion"]["timeout_factor"]; mods.append(f"post-exertion timeout x{M['post_exertion']['timeout_factor']}")
    t = int(round(min(max(t * f, lo), hi)))
    return out("CONFIRM_FIRST", band, raw_worst, "HT_CHEST_PAIN_VITALS", route="urgent_page", page="if_confirmed_or_timeout", confirm_step=cp["default_confirm_step"], timeout_min=t)

# ---- SMART_TRIGGERS v1.10 (Wayne 2026-10-21): Layer 1 fixes from the review-queue rulings. Params: layer1_v110.
def v110(p): return p.get("layer1_v110") or {}
def wording_rx(p, key, base):
    """base regex extended with the v1.10 synonym list for key (syncope, focal_neuro, chest_pain)."""
    extra = (v110(p).get("wording") or {}).get(key) or []
    return base + ("|" + "|".join(extra) if extra else "")
def suppressed_default_route(d, p):
    """Layer 1 route for a SUPPRESSED/ARTIFACT decision with no model pick (v1.10 replaces the provider_task fallback)."""
    t = v110(p).get("suppressed_default_route") or {}
    if d.get("default_route"): return d["default_route"]
    if d.get("tier") == "ARTIFACT" and d.get("reason") != "cleared_by_repeat": return t.get("ARTIFACT", "silent_log")
    return t.get(d.get("reason") or "", t.get("_other", "nurse_task"))
def route_floor(d, p):
    """minimum route for a suppressed decision (None = no floor)."""
    f = v110(p).get("route_floor") or {}
    return f.get(f'{d.get("rule")}:{d.get("reason")}') or f.get(d.get("reason") or "")
