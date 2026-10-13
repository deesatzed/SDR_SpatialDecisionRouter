"""One-shot helper (kept for provenance): appends the 6 outpatient complaints to params.yaml. ALL values placeholder."""
import sys, yaml
from itertools import product
P = "params.yaml"
d = yaml.safe_load(open(P))
def ph(x, note=None):
    e = {"value": x, "source": "placeholder", "citation": ""}
    if note: e["note"] = note
    return e
CTX = ["companion", "interpreter", "adolescent", "low_literacy", "elderly_alone"]
def truth(name, q, priors, sensitive=True, conceal=0.25, cctx=None, rctx=None, recall=0.08, fp=0.01, reveal=0.8, signals=None):
    if name in d["truths"]:
        for c, p in priors.items(): d["truths"][name]["prior"][c] = ph(p)
        return
    t = {"states": ["no", "yes"], "sensitive": sensitive, "question": q, "prior": {c: ph(p) for c, p in priors.items()},
         "report": {"false_positive": ph(fp), "recall_miss": ph(recall), "conceal_base": ph(conceal),
                    "conceal_context": {k: ph(x) for k, x in (cctx or {"companion": 0.2, "interpreter": 0.1}).items()},
                    "recall_context": {k: ph(x) for k, x in (rctx or {"low_literacy": 0.1, "elderly_alone": 0.15}).items()}},
         "ask": {"reveal": ph(reveal), "false_positive": ph(0.01)}}
    if signals: t["signals"] = {s: {"p_if_true": ph(a), "p_if_false": ph(b)} for s, (a, b) in signals.items()}
    d["truths"][name] = t
def dx(parents, sev, worst, plan, mit, ps):
    rows = [{"when": dict(zip(parents, k)), "p": ph(p)} for k, p in zip(product(["no", "yes"], repeat=len(parents)), ps)]
    return {"parents": parents, "severity": sev, "worst_miss": worst, "plan_change": plan, "mitigated_by": mit, "cpt": rows}
def complaint(name, truths, dxs, flags=()):
    d["complaints"][name] = {"truths": truths, "context": list(CTX), "plan_flags": list(flags), "dx": dxs}
H = {"hedge": (0.3, 0.03)}; R = {"record": (0.5, 0.01)}
# --- URI / sinus / pharyngitis requesting antibiotics
truth("qt_med", "", {"uri_abx": 0.04, "erectile_dysfunction": 0.02})
truth("pregnant", "", {"uri_abx": 0.05, "glp1_weight": 0.04})
truth("pcn_allergy", "Any reaction ever to penicillin or other antibiotics? What happened?", {"uri_abx": 0.1}, sensitive=False, conceal=0.02, recall=0.15, signals=R)
truth("airway_red_flag", "Any trouble swallowing your saliva, drooling, muffled voice, can't open your mouth, or short of breath?", {"uri_abx": 0.02}, conceal=0.1, recall=0.15, signals=H, reveal=0.9)
complaint("uri_abx", ["qt_med", "pregnant", "pcn_allergy", "airway_red_flag"], {
  "qt_event": dx(["qt_med", "plan_qt_drug"], 4, "QT prolongation / torsades (macrolide/FQ + methadone)", "avoid azithro/FQ; ECG for QTc or choose amoxicillin/no abx", ["modify", "escalate"], [0.0, 0.002, 0.003, 0.08]),
  "teratogen_exposure": dx(["pregnant", "plan_teratogen"], 3, "teratogenic antibiotic (doxy/FQ)", "pregnancy test; pregnancy-safe choice", ["modify", "escalate"], [0.0, 0.0, 0.0, 0.6]),
  "anaphylaxis": dx(["pcn_allergy"], 5, "anaphylaxis to beta-lactam", "non-beta-lactam or no antibiotic", ["modify", "escalate"], [0.0, 0.05]),
  "deep_neck_infection": dx(["airway_red_flag"], 5, "epiglottitis / peritonsillar abscess", "ED now (airway)", ["escalate"], [0.002, 0.5]),
}, flags=["plan_qt_drug", "plan_teratogen"])
# --- medication refill
truth("nonadherent", "How many doses did you miss in the last week? (no judgement)", {"med_refill": 0.3}, conceal=0.35, signals=R)
truth("overdue_monitoring", "When were your last blood tests for this medicine (potassium/kidney, TSH, A1c, INR)?", {"med_refill": 0.3}, sensitive=False, conceal=0.05, recall=0.3, signals=R)
truth("controlled_misuse", "Asked privately: taking more than prescribed, or getting it elsewhere?", {"med_refill": 0.06}, conceal=0.5, signals=R)
truth("new_interaction", "Any new medicines, supplements or prescriptions from another doctor?", {"med_refill": 0.12}, sensitive=False, conceal=0.05, recall=0.25)
truth("masked_symptom", "Any new symptoms since your last visit — swelling, chest pain, palpitations, weight change?", {"med_refill": 0.1}, conceal=0.3, signals=H)
complaint("med_refill", ["nonadherent", "overdue_monitoring", "controlled_misuse", "new_interaction", "masked_symptom"], {
  "unmonitored_toxicity": dx(["overdue_monitoring"], 4, "hyperkalemia/AKI on ACEi, INR out of range on warfarin", "labs first (K/Cr, TSH, A1c, INR) before refill", ["modify", "escalate"], [0.005, 0.1]),
  "decompensation": dx(["nonadherent"], 3, "uncontrolled disease / decompensation", "adherence plan; reassess dose before refill", ["modify", "escalate"], [0.01, 0.15]),
  "overdose_diversion": dx(["controlled_misuse"], 5, "overdose / diversion of controlled substance", "PDMP check; decline early refill; in-person visit", ["modify", "escalate"], [0.0, 0.2]),
  "interaction_harm": dx(["new_interaction"], 3, "new drug interaction", "med reconciliation; adjust", ["modify", "escalate"], [0.0, 0.2]),
  "missed_new_dx": dx(["masked_symptom"], 4, "refill masks new problem (e.g. HF, arrhythmia)", "visit before refill", ["escalate"], [0.002, 0.25]),
})
# --- GLP-1 weight loss
truth("mtc_men2", "Anyone in your family with medullary thyroid cancer or MEN2? Any thyroid lumps?", {"glp1_weight": 0.01}, sensitive=False, conceal=0.05, recall=0.35, signals=H)
truth("pancreatitis_hx", "Ever had pancreatitis?", {"glp1_weight": 0.02}, sensitive=False, conceal=0.05, recall=0.15, signals=R)
truth("gallbladder", "Any gallbladder problems or gallstones?", {"glp1_weight": 0.08}, sensitive=False, conceal=0.03, recall=0.2)
truth("eating_disorder", "Asked privately: ever had an eating disorder, purging or restricting?", {"glp1_weight": 0.06}, conceal=0.5, signals=H)
truth("hypoglycemic_meds", "Do you take insulin or a sulfonylurea (glipizide, glyburide)?", {"glp1_weight": 0.1}, sensitive=False, conceal=0.02, recall=0.15, signals=R)
truth("inflated_bmi", "Can we confirm weight/height on a measured scale (photo or clinic)?", {"glp1_weight": 0.1}, conceal=0.4, signals=H)
complaint("glp1_weight", ["mtc_men2", "pancreatitis_hx", "gallbladder", "pregnant", "eating_disorder", "hypoglycemic_meds", "inflated_bmi"], {
  "mtc_contraindication": dx(["mtc_men2"], 4, "GLP-1 in MTC/MEN2 family (boxed warning)", "decline GLP-1; alternatives", ["modify", "escalate"], [0.0, 0.9]),
  "recurrent_pancreatitis": dx(["pancreatitis_hx"], 4, "recurrent pancreatitis", "avoid GLP-1 or specialist review", ["modify", "escalate"], [0.002, 0.1]),
  "cholecystitis": dx(["gallbladder"], 3, "cholecystitis", "counsel; consider alternative", ["modify"], [0.005, 0.06]),
  "fetal_exposure": dx(["pregnant"], 4, "GLP-1 exposure in pregnancy", "pregnancy test; contraception plan; stop 2 mo before conception", ["modify", "escalate"], [0.0, 0.9]),
  "ed_relapse": dx(["eating_disorder"], 4, "eating-disorder relapse", "decline; behavioral health", ["modify", "escalate"], [0.0, 0.4]),
  "hypoglycemia": dx(["hypoglycemic_meds"], 4, "hypoglycemia with insulin/SU", "reduce insulin/SU; glucose monitoring", ["modify"], [0.0, 0.15]),
  "inappropriate_rx": dx(["inflated_bmi"], 2, "prescribed below indication threshold", "verified weight before prescribing", ["modify"], [0.0, 0.8]),
})
# --- midlife HRT
truth("hormone_cancer", "Any history of breast or endometrial cancer?", {"hrt_menopause": 0.03}, sensitive=False, conceal=0.05, recall=0.05, signals=R)
truth("vte_stroke_hx", "Any blood clots, stroke or heart attack, ever?", {"hrt_menopause": 0.04}, sensitive=False, conceal=0.05, recall=0.15, signals=R)
truth("smoker", "Do you smoke or vape nicotine?", {"hrt_menopause": 0.15}, conceal=0.3, signals=H)
truth("unexplained_bleeding", "Any vaginal bleeding after your periods stopped?", {"hrt_menopause": 0.06}, conceal=0.3, signals=H)
truth("migraine_aura", "Do your migraines come with visual changes or numbness (aura)?", {"hrt_menopause": 0.06}, sensitive=False, conceal=0.02, recall=0.3)
truth("liver_disease", "Any liver disease?", {"hrt_menopause": 0.02}, sensitive=False, conceal=0.05, recall=0.15, signals=R)
truth("late_start", "When was your last period, and what is your age? (>10 y since menopause or ≥60?)", {"hrt_menopause": 0.15}, sensitive=False, conceal=0.02, recall=0.2)
complaint("hrt_menopause", ["hormone_cancer", "vte_stroke_hx", "smoker", "unexplained_bleeding", "migraine_aura", "liver_disease", "late_start"], {
  "cancer_progression": dx(["hormone_cancer"], 5, "estrogen in hormone-sensitive cancer", "decline systemic HRT; oncology", ["modify", "escalate"], [0.0, 0.5]),
  "vte_stroke": dx(["vte_stroke_hx", "smoker"], 5, "VTE / stroke on oral estrogen", "transdermal or non-hormonal; specialist", ["modify", "escalate"], [0.002, 0.006, 0.08, 0.15]),
  "missed_endometrial_ca": dx(["unexplained_bleeding"], 5, "undiagnosed endometrial cancer", "evaluate bleeding (US/biopsy) first", ["modify", "escalate"], [0.0, 0.1]),
  "aura_stroke": dx(["migraine_aura"], 4, "stroke in migraine with aura", "transdermal low-dose; avoid oral", ["modify"], [0.0, 0.02]),
  "hepatotoxicity": dx(["liver_disease"], 3, "hepatic decompensation", "LFTs; avoid oral", ["modify"], [0.0, 0.2]),
  "late_start_cv": dx(["late_start"], 3, "CV events starting HRT late", "shared decision; non-hormonal options", ["modify"], [0.0, 0.05]),
})
# --- testosterone
truth("fertility_desire", "Are you hoping to have children in the next year or two?", {"testosterone": 0.25}, sensitive=False, conceal=0.05, recall=0.05, reveal=0.95)
truth("high_hct", "Recent blood count (hematocrit)?", {"testosterone": 0.08}, sensitive=False, conceal=0.02, recall=0.3, signals=R)
truth("untreated_osa", "Snoring, stopped breathing at night, daytime sleepiness?", {"testosterone": 0.2}, sensitive=False, conceal=0.05, recall=0.3, signals=H)
truth("prostate_issue", "Any prostate problems, raised PSA, urinary symptoms?", {"testosterone": 0.08}, sensitive=False, conceal=0.1, recall=0.2, signals=R)
truth("cv_risk_high", "Any heart attack, stroke, or chest pain on exertion?", {"testosterone": 0.1}, conceal=0.15, recall=0.1, signals=H)
truth("not_confirmed_low", "Two early-morning testosterone levels confirmed low? Main goal: symptoms vs gym/performance?", {"testosterone": 0.4}, conceal=0.35, signals=H)
complaint("testosterone", ["fertility_desire", "high_hct", "untreated_osa", "prostate_issue", "cv_risk_high", "not_confirmed_low"], {
  "infertility": dx(["fertility_desire"], 4, "testosterone suppresses spermatogenesis", "decline TRT; refer (hCG/clomiphene) ", ["modify"], [0.0, 0.9]),
  "polycythemia_thrombosis": dx(["high_hct"], 4, "erythrocytosis / thrombosis", "CBC first; hold if Hct >50%", ["modify"], [0.0, 0.15]),
  "osa_worsening": dx(["untreated_osa"], 3, "worsened untreated OSA", "sleep study first", ["modify"], [0.0, 0.2]),
  "prostate_progression": dx(["prostate_issue"], 4, "unrecognized prostate cancer", "PSA/DRE first", ["modify", "escalate"], [0.0, 0.08]),
  "cv_event": dx(["cv_risk_high"], 4, "CV event", "cardiology review before TRT", ["modify", "escalate"], [0.0, 0.08]),
  "inappropriate_rx": dx(["not_confirmed_low"], 2, "TRT without confirmed hypogonadism", "two AM total T levels first", ["modify"], [0.0, 0.9]),
})
# --- erectile dysfunction (PDE5)
truth("nitrate_use", "Asked privately: any nitroglycerin, isosorbide, or 'poppers' (amyl nitrite)?", {"erectile_dysfunction": 0.04}, conceal=0.4, recall=0.1, signals=R, reveal=0.9)
truth("exertional_cp", "Any chest pain or breathlessness with exertion or during sex?", {"erectile_dysfunction": 0.06}, conceal=0.3, signals=H)
truth("alpha_blocker", "Taking tamsulosin, doxazosin or other prostate/BP pills?", {"erectile_dysfunction": 0.1}, sensitive=False, conceal=0.02, recall=0.2, signals=R)
truth("recreational_drugs", "Asked privately: any recreational drugs (cocaine, meth) with sex?", {"erectile_dysfunction": 0.08}, conceal=0.5, signals=H)
complaint("erectile_dysfunction", ["nitrate_use", "exertional_cp", "alpha_blocker", "recreational_drugs", "qt_med"], {
  "nitrate_hypotension": dx(["nitrate_use"], 5, "PDE5 + nitrate: profound hypotension (HARD STOP)", "do not prescribe PDE5i", ["modify", "escalate"], [0.0, 0.6]),
  "missed_cad": dx(["exertional_cp"], 5, "ED as CV marker: missed CAD", "cardiac evaluation before PDE5i", ["escalate"], [0.005, 0.3]),
  "orthostatic_syncope": dx(["alpha_blocker"], 3, "orthostatic hypotension / syncope", "start low dose, separate timing", ["modify"], [0.0, 0.1]),
  "stimulant_event": dx(["recreational_drugs"], 4, "stimulant + PDE5 CV event", "counsel; private screen", ["modify", "escalate"], [0.0, 0.05]),
  "qt_event": dx(["qt_med"], 2, "QT interaction (vardenafil)", "choose sildenafil/tadalafil", ["modify"], [0.0, 0.05]),
})
d["meta"]["version"] = 2
yaml.safe_dump(d, open(P, "w"), sort_keys=False, width=140, allow_unicode=True)
print("complaints:", list(d["complaints"]))
