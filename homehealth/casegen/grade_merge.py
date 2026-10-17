#!/usr/bin/env python3
"""grade_merge.py - merge GRADER_LLM3 verdicts with a generated batch (SYNTHETIC cases only).

Outputs (in --out):
  review_queue.csv  cases needing a clinician ruling (route/hard-trigger disagreement, reject, ungraded)
  fix_list.csv      mechanical fixes to send back to the generator (not for clinician)
  accepted.json     {"cases":[...], "provenance":{...}} - cleaned set, feed to convert_casegen.py
  merge_report.txt  counts (all counts parsed, nothing estimated)
Usage:
  python3 grade_merge.py --batch batch.json [--batch ...] --grader grader.json [--grader ...] --out DIR [--src TAG] [--legacy]
--legacy : batch is v1 schema (skip v2-only field checks, v1 banned-word list)
--smart  : smart hard-trigger policy (SMART_TRIGGERS.md, GEN v2.2-2.3 / GRADER v1.2-1.3; v2.3 VS-layer checks when cases carry baseline_layer). Auto-on if any case has trigger_tier.
           Adds tier validation, CRITICAL_MISS / TIER_DISPUTE queue reasons and trigger_stats.csv.
Previous behaviour is kept in grade_merge_v2.1.py (and is the default here when --smart is off).
"""
import argparse, csv, json, os, re, sys, collections

ROUTES = {"silent_log", "nurse_task", "wake_specialist", "escalate_human"}
MECH = {"noise","recovery","hf","arrhythmia","acs","stroke","syncope","fall","delirium","infection","sepsis",
        "respiratory","hypoglycemia","hyperglycemia","dehydration","electrolyte","renal","missing_data"}
TAGS = {"med_change","spo2_bias","dementia","caregiver","goals_of_care","conflicting","missing_data"}
V1_CATS = {"noise","hf","delirium","fall","med_change","spo2_bias","dementia","caregiver","goals_of_care",
           "hypoglycemia","infection","conflicting"}
BANNED_V2 = [r"emergency", r"emergent", r"911", r"(?:call(?:ed|ing)?|dial(?:l?ed)?|phon(?:e|ed)|ring)\s+(?:999|112)", r"A&E", r"ambulance", r"paramedics?", r"urgent(ly)?",
             r"urgency", r"stat", r"asap", r"immediately", r"right away", r"red flags?", r"warning signs?", r"critical",
             r"life-threatening", r"alarming", r"worrying", r"concerning", r"escalat\w*", r"triage", r"specialist",
             r"silent", r"benign(?!\s+(?:prostatic|positional|essential|paroxysmal))", r"harmless", r"reassuring", r"false alarm", r"artifacts?", r"nothing to worry",
             r"just noise"]
BANNED_CS = [r"ER(?!\s*\d)", r"ED", r"EMS"]   # case-sensitive; "ER"+dose = extended-release (run-2 false positive)
BANNED_V1 = [r"emergency", r"911", r"urgent(ly)?", r"red flags?", r"escalat\w*"]
ANSWER_KEYS = {"rationale","decisive_feature","expected_route","acceptable_alternates","category","difficulty",
               "case_id","pair_id","hard_trigger_rule","hard_trigger","subtle_deterioration",
               "trigger_tier","confirm_step","confirm_timeout_min","suppression_reason","baseline_layer"}
META_KEYS = {"src", "grade", "relabel", "prev_labels", "prev_grade", "chest_pain_eval", "chest_pain_inputs"}  # provenance/metadata, not case text
TIERS = {"ABSOLUTE", "CONFIRM_FIRST", "SUPPRESSED", "ARTIFACT"}
RULE_TIER = {"HT_SYNCOPE": "ABSOLUTE", "HT_FOCAL_NEURO": "ABSOLUTE", "HT_CHEST_PAIN_ECG": "ABSOLUTE", "HT_CHEST_PAIN_VITALS": "CONFIRM_FIRST",
             "HT_SPO2_LT88": "CONFIRM_FIRST", "HT_GAP48_HIGHRISK": "CONFIRM_FIRST", "HT_FALL_ANTICOAG": "CONFIRM_FIRST",
             "HT_VS_DANGER": "ABSOLUTE", "HT_VS_IMPLAUSIBLE": "ARTIFACT"}   # last two: v2.3 VS layers
CONFIRM_STEPS = {"fingertip_recheck", "patient_call", "caregiver_ping", "already_confirmed", "device_recheck+patient_call"}  # last: chest-pain rule with a quality-flagged vital
ARTIFACT_STEPS = {"device_recheck", "fingertip_recheck", "fingerstick_recheck"}  # last: CGM pressure-low rule
BASELINE_LAYERS = {"hard_limit_artifact", "hard_limit_danger", "learning_period", "baseline_reset", "drift_not_absorbed"}
PHASES = {"learning", "established", "relearning"}
SUPP_REASONS = {"unreliable_reading", "at_patient_baseline", "explained", "goals_of_care", "below_band_threshold"}
BANDED_RULES = {"HT_CHEST_PAIN_VITALS"}   # SMART_TRIGGERS.md section 7: ABSOLUTE / CONFIRM_FIRST / SUPPRESSED below_band_threshold
CF_ALTS = {"nurse_task_with_recheck", "wake_specialist"}
SMART_FIELDS = ["trigger_tier", "confirm_step", "confirm_timeout_min", "suppression_reason"]

V2_REQ = ["case_id","pair_id","age_band","sex","skin_tone_note","living","pmh","function_baseline","patient_goals",
          "discharge","meds","recent_med_changes","devices","baseline_30d","trend_last_7d","caregiver_or_nurse_note",
          "data_quality","router_input","expected_route","acceptable_alternates","hard_trigger","hard_trigger_rule",
          "subtle_deterioration","difficulty","category","rationale","decisive_feature"]
V1_REQ = ["case_id","age_band","sex","meds","devices","baseline_30d","trend_last_7d","data_quality","expected_route",
          "acceptable_alternates","hard_trigger","difficulty","category","rationale","decisive_feature"]
EXACT_AGE = re.compile(r"(?<![-\d])\b\d{2,3}(-year-old| years old|yo|y/o)\b", re.I)
TITLE_NAME = re.compile(r"\b(Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+")

def load_cases(path):
    d = json.load(open(path))
    return d["cases"] if isinstance(d, dict) else d

def case_text(c):
    out = []
    def walk(v):
        if isinstance(v, str): out.append(v)
        elif isinstance(v, list): [walk(x) for x in v]
        elif isinstance(v, dict): [walk(x) for x in v.values()]
    for k, v in c.items():
        if k not in ANSWER_KEYS and k not in META_KEYS and not k.startswith(("src_", "prev_")): walk(v)
    return "\n".join(out)

def smart_checks(c):
    """Tier / field validation for the smart hard-trigger policy (SMART_TRIGGERS.md section 4)."""
    iss = []
    miss = [k for k in SMART_FIELDS if k not in c]
    if miss: return ["missing smart-trigger fields: " + ",".join(miss)]
    ht, rule, tier = bool(c.get("hard_trigger")), c.get("hard_trigger_rule"), c.get("trigger_tier")
    exp, alts = c.get("expected_route"), c.get("acceptable_alternates") or []
    cs, to, sr = c.get("confirm_step"), c.get("confirm_timeout_min"), c.get("suppression_reason")
    if not ht:
        if any(c.get(k) is not None for k in SMART_FIELDS) or rule: iss.append("trigger fields set on a non-trigger case")
        if "nurse_task_with_recheck" in alts: iss.append("nurse_task_with_recheck alternate on a non-trigger case")
        return iss
    if rule not in RULE_TIER: iss.append(f"unknown hard_trigger_rule {rule!r} (v2.2 ids; HT_CHEST_PAIN_CHANGE is split)")
    if tier not in TIERS: return iss + [f"bad trigger_tier {tier!r}"]
    if tier != "SUPPRESSED" and rule in RULE_TIER and RULE_TIER[rule] == "CONFIRM_FIRST" and tier == "ABSOLUTE" and rule not in BANDED_RULES:
        iss.append(f"{rule} labelled ABSOLUTE (policy tier CONFIRM_FIRST)")
    if tier == "ABSOLUTE":
        if exp != "escalate_human": iss.append("ABSOLUTE but not escalate_human")
        if alts: iss.append("ABSOLUTE with non-empty alternates")
        if cs or to is not None or sr: iss.append("ABSOLUTE with confirm/suppression fields set")
    elif tier == "CONFIRM_FIRST":
        if exp != "escalate_human": iss.append("CONFIRM_FIRST but not escalate_human")
        if cs not in CONFIRM_STEPS: iss.append(f"CONFIRM_FIRST bad confirm_step {cs!r}")
        if cs == "already_confirmed":
            if to is not None: iss.append("already_confirmed with a timeout")
            if alts: iss.append("already_confirmed with non-empty alternates")
        elif not (isinstance(to, int) and 5 <= to <= 120): iss.append(f"CONFIRM_FIRST confirm_timeout_min {to!r} not int 5-120")
        bad = [x for x in alts if x not in CF_ALTS]
        if bad: iss.append("CONFIRM_FIRST alternates outside {nurse_task_with_recheck, wake_specialist}: " + ",".join(bad))
        if sr: iss.append("CONFIRM_FIRST with suppression_reason")
    elif tier == "SUPPRESSED":
        if exp == "escalate_human": iss.append("SUPPRESSED but expected escalate_human")
        if sr not in SUPP_REASONS: iss.append(f"SUPPRESSED bad suppression_reason {sr!r}")
        if sr == "goals_of_care" and exp == "silent_log": iss.append("goals_of_care suppression routed silent_log")
        if cs or to is not None: iss.append("SUPPRESSED with confirm fields set")
        if "nurse_task_with_recheck" in alts: iss.append("SUPPRESSED with nurse_task_with_recheck alternate")
    elif tier == "ARTIFACT":
        if rule != "HT_VS_IMPLAUSIBLE": iss.append("ARTIFACT tier only for HT_VS_IMPLAUSIBLE")
        if exp not in ("silent_log", "wake_specialist"): iss.append("ARTIFACT must route silent_log or wake_specialist (no page)")
        if cs not in ARTIFACT_STEPS or not (isinstance(to, int) and 5 <= to <= 120): iss.append("ARTIFACT needs confirm_step device_recheck|fingertip_recheck and a 5-120 min timeout")
        if sr: iss.append("ARTIFACT with suppression_reason")
        if "nurse_task_with_recheck" in alts: iss.append("ARTIFACT with nurse_task_with_recheck alternate")
    if tier != "ARTIFACT" and rule == "HT_VS_IMPLAUSIBLE": iss.append("HT_VS_IMPLAUSIBLE must be tier ARTIFACT")
    if exp == "nurse_task_with_recheck": iss.append("nurse_task_with_recheck used as expected_route")
    if sr == "below_band_threshold":
        if rule not in BANDED_RULES: iss.append("below_band_threshold only for banded rules")
        if exp == "silent_log": iss.append("below_band_threshold chest pain routed silent_log")
    if rule in BANDED_RULES and isinstance(c.get("chest_pain_eval"), dict):
        band = c["chest_pain_eval"].get("band"); want = {"A": "ABSOLUTE", "B": "CONFIRM_FIRST", "C": "CONFIRM_FIRST", "D": "SUPPRESSED"}.get(band)
        if want and tier not in (want, "SUPPRESSED" if sr == "goals_of_care" else want): iss.append(f"chest_pain_eval band {band} implies {want}, labelled {tier}")
    return iss

def layer_checks(c):
    """v2.3 three-layer VS checks (SMART_TRIGGERS.md section 6). Only for cases that carry baseline_layer."""
    iss = []; bl = c.get("baseline_layer"); bs = c.get("baseline_status")
    if not isinstance(bs, dict) or bs.get("phase") not in PHASES: iss.append("baseline_status missing or bad phase")
    if bl is not None and bl not in BASELINE_LAYERS: return iss + [f"bad baseline_layer {bl!r}"]
    tier = c.get("trigger_tier"); exp = c.get("expected_route")
    if (bl == "hard_limit_artifact") != (tier == "ARTIFACT"): iss.append("hard_limit_artifact <-> ARTIFACT tier mismatch")
    if bl == "hard_limit_danger" and not (c.get("hard_trigger_rule") == "HT_VS_DANGER" and tier in ("ABSOLUTE", "SUPPRESSED")): iss.append("hard_limit_danger needs HT_VS_DANGER (ABSOLUTE, or SUPPRESSED only for goals/unreliable)")
    if bl == "learning_period" or (isinstance(bs, dict) and bs.get("phase") == "learning"):
        if c.get("suppression_reason") == "at_patient_baseline" and "clinician" not in (c.get("caregiver_or_nurse_note") or "").lower():
            iss.append("at_patient_baseline suppression during learning without a clinician-set baseline")
    if bl == "drift_not_absorbed":
        if not c.get("subtle_deterioration"): iss.append("drift_not_absorbed without subtle_deterioration")
        if exp == "silent_log": iss.append("drift_not_absorbed routed silent_log (drift learned away)")
    if bl == "baseline_reset" and not (isinstance(bs, dict) and bs.get("last_condition_change")): iss.append("baseline_reset without last_condition_change")
    return iss

def script_checks(c, legacy, smart=False):
    """Deterministic checks the script does itself (does not trust the grader for these)."""
    issues = []
    req = V1_REQ if legacy else V2_REQ
    miss = [k for k in req if k not in c]
    if miss: issues.append("missing fields: " + ",".join(miss))
    txt = case_text(c)
    pats = BANNED_V1 if legacy else BANNED_V2
    found = [m.group(0) for p in pats for m in re.finditer(r"\b" + p + r"\b", txt, re.I)]
    if not legacy:
        found += [m.group(0) for p in BANNED_CS for m in re.finditer(r"\b" + p + r"\b", txt)]
    if found: issues.append("banned words: " + ",".join(sorted(set(found))))
    ages = EXACT_AGE.findall(txt)
    if ages: issues.append("exact age mention")
    if TITLE_NAME.search(txt): issues.append("title+name: " + TITLE_NAME.search(txt).group(0))
    if c.get("expected_route") not in ROUTES: issues.append("bad expected_route")
    if c.get("expected_route") in (c.get("acceptable_alternates") or []): issues.append("expected in alternates")
    if smart:
        issues += smart_checks(c)
        if "baseline_layer" in c: issues += layer_checks(c)
    else:
        if c.get("hard_trigger") and c.get("expected_route") != "escalate_human": issues.append("hard_trigger but not escalate_human")
        if c.get("hard_trigger") and (c.get("acceptable_alternates") or []) and not legacy: issues.append("hard_trigger with non-empty acceptable_alternates (v2.1)")
    g = (c.get("baseline_30d") or {}).get("glucose_mean")
    if isinstance(g, (int, float)) and g < 30: issues.append("glucose looks like mmol/L")
    cats = c.get("category") or []
    if legacy:
        bad = [x for x in cats if x not in V1_CATS]
    else:
        bad = [x for x in cats if x not in MECH | TAGS]
        if cats and cats[0] not in MECH: issues.append(f"category[0] '{cats[0]}' not a mechanism")
        if "Naive-model trap:" not in (c.get("rationale") or ""): issues.append("rationale lacks 'Naive-model trap:'")
        if c.get("hard_trigger") and not c.get("hard_trigger_rule"): issues.append("hard_trigger without rule id")
    if bad: issues.append("off-vocab category: " + ",".join(bad))
    dq = c.get("data_quality") or {}
    if isinstance(dq.get("missing_hours_last_48"), (int, float)) and dq["missing_hours_last_48"] > 48:
        issues.append(f"missing_hours_last_48={dq['missing_hours_last_48']} > 48")
    if not legacy:
        bk = {"rest_hr","hrv_ms","sleep_h","steps","spo2_night_min","skin_temp_dev_c","weight_kg","glucose_mean","sbp","dbp"}
        mk = bk - set((c.get("baseline_30d") or {}).keys())
        if mk: issues.append("baseline_30d missing keys: " + ",".join(sorted(mk)))
    # device provenance (v2 rule 4): baseline keys / obvious trend readings need the device
    dev = set(c.get("devices") or []); b = c.get("baseline_30d") or {}; tr = c.get("trend_last_7d") or ""
    need = [("weight_kg", {"scale"}), ("sbp", {"bp_cuff"}), ("dbp", {"bp_cuff"}), ("glucose_mean", {"cgm", "glucometer"})]
    for k, ds in need:
        if b.get(k) is not None and not (dev & ds) and "visit:" not in (c.get("caregiver_or_nurse_note") or ""):
            issues.append(f"device: baseline {k} without {'/'.join(sorted(ds))}")
    if re.search(r"\b(BP|blood pressure)\b[^.;]{0,25}\d{2,3}/\d{2,3}", tr) and "bp_cuff" not in dev:
        issues.append("device: BP reading without bp_cuff")
    if re.search(r"\btemp(erature)?\s*(of\s*)?3\d(\.\d)?\s*C", tr, re.I) and "thermometer" not in dev:
        issues.append("device: absolute temperature without thermometer")
    for m in c.get("meds") or []:
        if m.get("started_day") is None: issues.append(f"started_day null: {m.get('name')}"); break
    return issues

def flat_issues(v):
    out = []
    for k in ("physiologic_consistency","device_consistency","med_timeline_consistency","router_input_faithful"):
        for i in (v.get(k) or {}).get("issues", []) or []: out.append(f"{k.split('_')[0]}: {i}")
    for i in v.get("schema_issues", []) or []: out.append(f"schema: {i}")
    blc = v.get("baseline_layer_correct") or {}
    if blc.get("applicable") and blc.get("ok") is False: out.append(f"baseline_layer -> {blc.get('suggested')}: {blc.get('issue')}")
    tt = v.get("trigger_tier_correct") or {}
    if tt.get("applicable") and tt.get("ok") is False: out.append(f"tier -> {tt.get('suggested_tier')}/{tt.get('suggested_confirm_step')}: {tt.get('issue')}")
    rl = v.get("route_leak") or {}
    if rl.get("words_found"): out.append("grader leak: " + ",".join(rl["words_found"]))
    ph = v.get("phi_or_names") or {}
    if ph.get("found"): out.append("grader names/PHI: " + ",".join(ph["found"]))
    cc = v.get("category_correct") or {}
    if cc.get("ok") is False: out.append("category -> " + ",".join(cc.get("suggested") or []))
    pv = v.get("pair_validity") or {}
    if pv.get("applicable") and pv.get("ok") is False: out.append("pair invalid: " + "; ".join(pv.get("differences") or []))
    df = v.get("difficulty_fair") or {}
    if df.get("ok") is False: out.append(f"difficulty -> {df.get('suggested')}")
    nv = v.get("novelty") or {}
    if nv.get("ok") is False: out.append(f"novelty: {nv.get('overlap_note') or nv.get('closest_do_not_repeat')}")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", action="append", required=True)
    ap.add_argument("--grader", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", default="")
    ap.add_argument("--legacy", action="store_true")
    ap.add_argument("--smart", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    cases = collections.OrderedDict()
    for b in a.batch:
        for c in load_cases(b):
            if c["case_id"] in cases: sys.exit(f"duplicate case_id {c['case_id']} across batches")
            cases[c["case_id"]] = c
    smart = a.smart or any("trigger_tier" in c for c in cases.values())
    verdicts, batch_ids, warn = {}, [], []
    for g in a.grader:
        d = json.load(open(g)); batch_ids.append(d.get("batch_id"))
        for v in d.get("verdicts", []):
            if v["case_id"] not in cases: warn.append(f"verdict for unknown case {v['case_id']}"); continue
            verdicts[v["case_id"]] = v

    qcols = ["case_id","src","queue_reasons","expected_route","acceptable_alternates","grader_route","grader_confidence",
             "hard_trigger_rule_case","hard_trigger_rule_grader","grader_action","grader_score","grader_reasoning",
             "issues","fix_instructions","decisive_feature","rationale","trend_last_7d","caregiver_or_nurse_note",
             "CLINICIAN_RULING (route)","CLINICIAN_NOTE"]
    if smart:
        qcols[8:8] = ["trigger_tier_case", "confirm_step", "suppression_reason", "grader_trigger_tier", "grader_suppression_reason"]
    tstats = collections.defaultdict(collections.Counter)
    queue, fixes, accepted = [], [], []
    cnt = collections.Counter()
    for cid, c in cases.items():
        v = verdicts.get(cid)
        exp = c.get("expected_route"); alts = c.get("acceptable_alternates") or []
        rule_case = c.get("hard_trigger_rule") or (("legacy:true" if c.get("hard_trigger") else None) if a.legacy else None)
        s_issues = script_checks(c, a.legacy, smart)
        g_tier = g_supp = ""
        reasons = []
        if v is None:
            reasons.append("UNGRADED"); g_route = g_conf = g_rule = g_act = g_score = g_reason = ""
            g_issues, g_fix = [], []
        else:
            b = v.get("blind") or {}
            g_route = b.get("grader_route"); g_conf = b.get("confidence"); g_rule = b.get("grader_hard_trigger_rule")
            g_act = v.get("action"); g_score = v.get("score"); g_reason = b.get("reasoning") or ""
            g_issues = flat_issues(v); g_fix = v.get("fix_instructions") or []
            if g_route not in ROUTES: reasons.append("GRADER_ROUTE_INVALID")
            elif g_route != exp and g_route not in alts and not (smart and g_route == "nurse_task" and "nurse_task_with_recheck" in alts):
                reasons.append("ROUTE_DISAGREE")
            elif g_route != exp: cnt["route_alternate"] += 1
            # hard-trigger dispute: grader names a rule the case lacks, or vice versa
            case_ht = bool(c.get("hard_trigger")); grader_ht = bool(g_rule)
            htc = v.get("hard_trigger_correct") or {}
            if case_ht != grader_ht or htc.get("ok") is False or (not a.legacy and case_ht and grader_ht and g_rule != rule_case):
                reasons.append("HARD_TRIGGER_DISPUTE")
            if smart:
                g_tier = b.get("grader_trigger_tier"); g_supp = b.get("grader_suppression_reason")
                tt = v.get("trigger_tier_correct") or {}
                crit = c.get("trigger_tier") == "SUPPRESSED" and (g_tier in ("ABSOLUTE", "CONFIRM_FIRST") or g_route == "escalate_human" or tt.get("critical_miss") is True)
                if crit: reasons.insert(0, "CRITICAL_MISS"); cnt["critical_miss"] += 1
                elif c.get("hard_trigger") and (tt.get("ok") is False or (g_tier and g_tier != c.get("trigger_tier"))):
                    reasons.append("TIER_DISPUTE")
                blc = v.get("baseline_layer_correct") or {}
                if blc.get("drift_miss") is True or (b.get("grader_baseline_layer") == "drift_not_absorbed" and exp == "silent_log"):
                    reasons.insert(0, "DRIFT_MISS"); cnt["DRIFT_MISS"] += 1
            if g_act == "reject":
                # novelty-only rejects go to the clinician queue, not auto-reject
                other = [i for i in g_issues if not i.startswith(("novelty:", "difficulty ->"))]
                if (v.get("novelty") or {}).get("ok") is False and not other and v.get("schema_ok") is not False and not s_issues:
                    reasons.append("NOVELTY_REVIEW")
                else:
                    reasons.append("REJECT")
        row_common = dict(case_id=cid, src=a.src, expected_route=exp, acceptable_alternates="|".join(alts),
                          grader_route=g_route, grader_confidence=g_conf, hard_trigger_rule_case=rule_case,
                          hard_trigger_rule_grader=g_rule, grader_action=g_act, grader_score=g_score,
                          grader_reasoning=g_reason, issues=" || ".join(s_issues + g_issues),
                          fix_instructions=" || ".join(g_fix))
        if smart:
            row_common.update(trigger_tier_case=c.get("trigger_tier"), confirm_step=c.get("confirm_step"), suppression_reason=c.get("suppression_reason"),
                              grader_trigger_tier=g_tier, grader_suppression_reason=g_supp)
            if c.get("hard_trigger"):
                r_ = c.get("hard_trigger_rule") or "?"; tstats[r_]["fired"] += 1; tstats[r_][c.get("trigger_tier") or "?"] += 1
                if "CRITICAL_MISS" in reasons: tstats[r_]["critical_miss"] += 1
        if reasons:
            for r in reasons: cnt[r] += 1
            queue.append({**row_common, "queue_reasons": "|".join(reasons),
                          "decisive_feature": c.get("decisive_feature"), "rationale": c.get("rationale"),
                          "trend_last_7d": c.get("trend_last_7d"), "caregiver_or_nurse_note": c.get("caregiver_or_nurse_note"),
                          "CLINICIAN_RULING (route)": "", "CLINICIAN_NOTE": ""})
        elif g_act == "fix" or s_issues:
            cnt["FIX"] += 1
            src = ("script" if s_issues else "") + ("+grader" if g_act == "fix" else "")
            fixes.append({**row_common, "fix_source": src.strip("+")})
        else:
            cnt["ACCEPT"] += 1
            accepted.append({**c, "src": a.src, "grade": {"score": g_score, "grader_route": g_route,
                                                          "grader_confidence": g_conf, "batch_id": v and batch_ids}})
    with open(os.path.join(a.out, "review_queue.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=qcols); w.writeheader(); w.writerows(queue)
    fcols = ["case_id","src","fix_source","expected_route","grader_route","grader_action","grader_score","issues","fix_instructions"]
    if smart:
        fcols[4:4] = ["trigger_tier_case", "grader_trigger_tier"]
        rows = []
        for r_, t in sorted(tstats.items()):
            act = t["ABSOLUTE"] + t["CONFIRM_FIRST"]; rate = act / t["fired"] if t["fired"] else None
            rows.append(dict(rule=r_, fired=t["fired"], ABSOLUTE=t["ABSOLUTE"], CONFIRM_FIRST=t["CONFIRM_FIRST"], SUPPRESSED=t["SUPPRESSED"], ARTIFACT=t["ARTIFACT"],
                             actionable_escalation_rate=round(rate, 3) if rate is not None else "", critical_miss=t["critical_miss"],
                             flag="NOISY" if t["fired"] >= 3 and rate is not None and rate < 0.5 else ""))
        with open(os.path.join(a.out, "trigger_stats.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["rule","fired","ABSOLUTE","CONFIRM_FIRST","SUPPRESSED","ARTIFACT","actionable_escalation_rate","critical_miss","flag"]); w.writeheader(); w.writerows(rows)
    with open(os.path.join(a.out, "fix_list.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fcols, extrasaction="ignore"); w.writeheader(); w.writerows(fixes)
    json.dump({"cases": accepted, "provenance": {"batches": a.batch, "graders": a.grader, "grader_batch_ids": batch_ids,
               "src": a.src, "legacy": a.legacy}}, open(os.path.join(a.out, "accepted.json"), "w"), indent=1)
    rep = [f"cases in: {len(cases)} | verdicts matched: {sum(1 for k in cases if k in verdicts)}",
           f"accepted: {cnt['ACCEPT']} | graded cases where grader chose an acceptable alternate: {cnt['route_alternate']}",
           f"fix_list: {cnt['FIX']}",
           f"review_queue: {len(queue)} | reasons: " + ", ".join(f"{k}={cnt[k]}" for k in
              ("ROUTE_DISAGREE","HARD_TRIGGER_DISPUTE","REJECT","NOVELTY_REVIEW","UNGRADED","GRADER_ROUTE_INVALID") + (("CRITICAL_MISS","TIER_DISPUTE","DRIFT_MISS") if smart else ())),
           "accepted routes: " + json.dumps(collections.Counter(c["expected_route"] for c in accepted))]
    if smart: rep.append("smart triggers: " + json.dumps({r_: dict(t) for r_, t in sorted(tstats.items())}))
    rep += [f"WARN {w_}" for w_ in warn]
    open(os.path.join(a.out, "merge_report.txt"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))

if __name__ == "__main__":
    main()
