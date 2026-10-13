import Foundation

/// Global demo switch: `-demo` launch arg or the Demo button on the start window.
enum DemoState {
    static var on = ProcessInfo.processInfo.arguments.contains("-demo")
    static var auto = ProcessInfo.processInfo.arguments.contains("-demoAuto")
}

/// One hidden-truth field of an outpatient AI-doc request (SYNTHETIC). key == risk_engine truth name.
struct OPField {
    let key: String, benign: String, risky: String, p: Double, sensitive: Bool
    let signal: String?          // "record" | "hedge" — what the system can see when the truth is hidden
    let clue: String?
    let action: String           // plan option if the risky truth is real
    let worst: String
    let question: String
}

enum OPSpec {
    static let outpatient: [DRComplaint] = [.uriAbx, .refill, .glp1, .hrt, .testosterone, .erectile]
    /// generic ED-style fields that also apply (BN truth via BNMap.field)
    static let generic: [DRComplaint: [String]] = [.uriAbx: ["meds", "pregnancy", "allergies"], .erectile: ["meds"], .glp1: ["pregnancy"]]
    static let actionRank = ["sign off": 0, "with conditions": 1, "labs first": 2, "decline": 3, "escalate": 4]

    static let fields: [DRComplaint: [OPField]] = [
        .uriAbx: [
            OPField(key: "airway_red_flag", benign: "no red flags", risky: "drooling + muffled voice, can't open mouth", p: 0.03, sensitive: false,
                    signal: "hedge", clue: "transcript: \"it hurts to swallow my own spit\"", action: "escalate", worst: "epiglottitis / peritonsillar abscess",
                    question: "Any trouble swallowing saliva, drooling, muffled voice, trouble opening mouth, or short of breath?")],
        .refill: [
            OPField(key: "nonadherent", benign: "takes daily", risky: "missed most doses", p: 0.3, sensitive: true, signal: "record",
                    clue: "refill gap: last fill 70 days ago for 30-day supply", action: "with conditions", worst: "decompensation", question: "How many doses did you miss in the last week? (no judgement)"),
            OPField(key: "overdue_monitoring", benign: "labs current", risky: "no K/Cr in 18 mo on lisinopril", p: 0.3, sensitive: false, signal: "record",
                    clue: "lab record: last K/Cr 18 months ago (ACEi)", action: "labs first", worst: "hyperkalemia / AKI; TSH/A1c/INR out of range",
                    question: "When were your last blood tests for this medicine (K/Cr, TSH, A1c, INR)?"),
            OPField(key: "controlled_misuse", benign: "as prescribed", risky: "early fills from 2 prescribers", p: 0.06, sensitive: true, signal: "record",
                    clue: "PDMP: 2 prescribers, early fills", action: "decline", worst: "overdose / diversion", question: "Asked privately: taking more than prescribed, or getting it elsewhere?"),
            OPField(key: "new_interaction", benign: "no new meds", risky: "new clarithromycin from urgent care", p: 0.12, sensitive: false, signal: nil,
                    clue: nil, action: "with conditions", worst: "new drug interaction", question: "Any new medicines, supplements or prescriptions from another doctor?"),
            OPField(key: "masked_symptom", benign: "no new symptoms", risky: "new ankle swelling + breathless on stairs", p: 0.1, sensitive: true, signal: "hedge",
                    clue: "transcript: \"just need the refill… bit more tired lately\"", action: "escalate", worst: "refill masks new problem (HF, arrhythmia)",
                    question: "Any new symptoms since your last visit — swelling, chest pain, palpitations, weight change?")],
        .glp1: [
            OPField(key: "mtc_men2", benign: "no family history", risky: "mother: medullary thyroid cancer", p: 0.04, sensitive: false, signal: "hedge",
                    clue: "transcript: \"my mom had some thyroid thing… not sure what\"", action: "decline", worst: "GLP-1 in MTC/MEN2 family (boxed warning)",
                    question: "Anyone in your family with medullary thyroid cancer or MEN2? Any thyroid lumps?"),
            OPField(key: "pancreatitis_hx", benign: "never", risky: "pancreatitis 2019", p: 0.03, sensitive: false, signal: "record",
                    clue: "record: lipase 900 (2019 admission)", action: "decline", worst: "recurrent pancreatitis", question: "Ever had pancreatitis?"),
            OPField(key: "gallbladder", benign: "none", risky: "gallstones, untreated", p: 0.08, sensitive: false, signal: nil, clue: nil,
                    action: "with conditions", worst: "cholecystitis", question: "Any gallbladder problems or gallstones?"),
            OPField(key: "eating_disorder", benign: "none", risky: "past bulimia", p: 0.06, sensitive: true, signal: "hedge",
                    clue: "transcript: \"I've always had a complicated relationship with food\"", action: "decline", worst: "eating-disorder relapse",
                    question: "Asked privately: ever had an eating disorder, purging or restricting?"),
            OPField(key: "hypoglycemic_meds", benign: "none", risky: "glipizide 10 mg bid", p: 0.1, sensitive: false, signal: "record",
                    clue: "pharmacy record: glipizide", action: "with conditions", worst: "hypoglycemia with sulfonylurea/insulin",
                    question: "Do you take insulin or a sulfonylurea (glipizide, glyburide)?"),
            OPField(key: "inflated_bmi", benign: "BMI 32 (measured)", risky: "self-report BMI 31; measured 26", p: 0.1, sensitive: true, signal: "hedge",
                    clue: "transcript: weight given as a round number, no scale", action: "labs first", worst: "prescribed below indication",
                    question: "Can we confirm weight/height on a measured scale (photo or clinic)?")],
        .hrt: [
            OPField(key: "hormone_cancer", benign: "none", risky: "ER+ breast cancer 2018", p: 0.03, sensitive: false, signal: "record",
                    clue: "record: tamoxifen 2018–2023", action: "decline", worst: "estrogen in hormone-sensitive cancer", question: "Any history of breast or endometrial cancer?"),
            OPField(key: "vte_stroke_hx", benign: "none", risky: "DVT 2015", p: 0.04, sensitive: false, signal: "record",
                    clue: "record: apixaban 2015 × 6 mo", action: "decline", worst: "VTE / stroke on oral estrogen", question: "Any blood clots, stroke or heart attack, ever?"),
            OPField(key: "smoker", benign: "non-smoker", risky: "smokes 10/day", p: 0.15, sensitive: true, signal: "hedge",
                    clue: "transcript: \"I've mostly quit\"", action: "with conditions", worst: "VTE / stroke risk ↑", question: "Do you smoke or vape nicotine?"),
            OPField(key: "unexplained_bleeding", benign: "no bleeding", risky: "spotting 1 y after menopause", p: 0.06, sensitive: true, signal: "hedge",
                    clue: "transcript: \"a little spotting, probably nothing\"", action: "labs first", worst: "undiagnosed endometrial cancer",
                    question: "Any vaginal bleeding after your periods stopped?"),
            OPField(key: "migraine_aura", benign: "no aura", risky: "migraine with visual aura", p: 0.06, sensitive: false, signal: nil, clue: nil,
                    action: "with conditions", worst: "stroke in migraine with aura", question: "Do your migraines come with visual changes or numbness (aura)?"),
            OPField(key: "liver_disease", benign: "none", risky: "cirrhosis (NASH)", p: 0.02, sensitive: false, signal: "record",
                    clue: "record: elevated ALT ×3", action: "labs first", worst: "hepatic decompensation", question: "Any liver disease?"),
            OPField(key: "late_start", benign: "<10 y since menopause, <60", risky: "14 y since menopause, age 63", p: 0.15, sensitive: false, signal: nil, clue: nil,
                    action: "with conditions", worst: "CV events starting HRT late", question: "When was your last period? (timing: <10 y and <60?)")],
        .testosterone: [
            OPField(key: "fertility_desire", benign: "no plans", risky: "trying to conceive this year", p: 0.25, sensitive: false, signal: nil, clue: nil,
                    action: "decline", worst: "testosterone suppresses sperm production (infertility)", question: "Are you hoping to have children in the next year or two?"),
            OPField(key: "high_hct", benign: "Hct normal", risky: "Hct 52%", p: 0.08, sensitive: false, signal: "record",
                    clue: "lab record: Hct 51.8% (2025)", action: "labs first", worst: "erythrocytosis / thrombosis", question: "Recent blood count (hematocrit)?"),
            OPField(key: "untreated_osa", benign: "no OSA symptoms", risky: "loud snoring + apneas, untreated", p: 0.2, sensitive: false, signal: "hedge",
                    clue: "transcript: \"my wife says I snore a bit\"", action: "labs first", worst: "worsened untreated OSA", question: "Snoring, stopped breathing at night, daytime sleepiness?"),
            OPField(key: "prostate_issue", benign: "none", risky: "PSA 4.8, not followed up", p: 0.08, sensitive: false, signal: "record",
                    clue: "lab record: PSA 4.8 (2024)", action: "labs first", worst: "unrecognized prostate cancer", question: "Any prostate problems, raised PSA, urinary symptoms?"),
            OPField(key: "cv_risk_high", benign: "no CV disease", risky: "MI 2022", p: 0.1, sensitive: true, signal: "hedge",
                    clue: "transcript: \"had a small heart thing a few years ago\"", action: "labs first", worst: "CV event", question: "Any heart attack, stroke, or chest pain on exertion?"),
            OPField(key: "not_confirmed_low", benign: "2 AM levels low", risky: "single afternoon level; wants gym gains", p: 0.4, sensitive: true, signal: "hedge",
                    clue: "transcript: \"mainly want to bulk up\"", action: "labs first", worst: "TRT without confirmed hypogonadism",
                    question: "Two early-morning testosterone levels confirmed low? Main goal: symptoms or gym/performance?")],
        .erectile: [
            OPField(key: "nitrate_use", benign: "no nitrates", risky: "isosorbide mononitrate + poppers", p: 0.05, sensitive: true, signal: "record",
                    clue: "pharmacy record: isosorbide mononitrate filled 3 wk ago", action: "decline", worst: "PDE5 + nitrate: profound hypotension (HARD STOP)",
                    question: "Asked privately: any nitroglycerin, isosorbide, or 'poppers' (amyl nitrite)?"),
            OPField(key: "exertional_cp", benign: "no exertional symptoms", risky: "chest pressure on stairs", p: 0.06, sensitive: true, signal: "hedge",
                    clue: "transcript: \"I get winded, I'm just out of shape\"", action: "escalate", worst: "ED as CV marker: missed CAD",
                    question: "Any chest pain or breathlessness with exertion or during sex?"),
            OPField(key: "alpha_blocker", benign: "none", risky: "tamsulosin 0.4 mg", p: 0.1, sensitive: false, signal: "record",
                    clue: "pharmacy record: tamsulosin", action: "with conditions", worst: "orthostatic hypotension / syncope", question: "Taking tamsulosin, doxazosin or other prostate/BP pills?"),
            OPField(key: "recreational_drugs", benign: "none", risky: "cocaine with sex", p: 0.08, sensitive: true, signal: "hedge",
                    clue: "transcript: \"sometimes at parties…\"", action: "with conditions", worst: "stimulant + PDE5 CV event", question: "Asked privately: any recreational drugs (cocaine, meth) with sex?")],
    ]
    static func field(_ k: String) -> OPField? { fields.values.joined().first { $0.key == k } }

    static let plans: [DRComplaint: [String]] = [
        .uriAbx: ["azithromycin 5 days (Z-pack)", "levofloxacin 7 days", "amoxicillin 10 days"],
        .refill: ["refill lisinopril 90 days", "refill levothyroxine 90 days", "refill warfarin 30 days", "refill metformin 90 days", "refill alprazolam 30 days"],
        .glp1: ["semaglutide 0.25 mg weekly, titrate"], .hrt: ["oral estradiol 1 mg + micronized progesterone"],
        .testosterone: ["testosterone cypionate 100 mg IM weekly"], .erectile: ["sildenafil 50 mg prn"],
    ]
    static let ddx: [DRComplaint: [(String, Double)]] = [
        .uriAbx: [("viral URI", 0.6), ("strep pharyngitis", 0.2), ("bacterial sinusitis", 0.15), ("PTA/epiglottitis", 0.05)],
        .refill: [("stable chronic disease", 0.85), ("new problem", 0.15)],
        .glp1: [("obesity, indication met", 0.85), ("indication not met", 0.15)],
        .hrt: [("vasomotor symptoms of menopause", 0.85), ("other cause", 0.15)],
        .testosterone: [("symptomatic hypogonadism", 0.4), ("age/lifestyle (not hypogonadal)", 0.6)],
        .erectile: [("vasculogenic ED", 0.6), ("psychogenic ED", 0.25), ("medication-related", 0.15)],
    ]
    static let counselling: [DRComplaint: [(String, String)]] = [
        .glp1: [("cost / coverage", "often not covered for weight loss; check PA"), ("compounded products", "not FDA-approved; dosing errors reported"),
                ("GI adverse effects", "nausea/vomiting common; titrate slowly; hydrate"), ("lean mass", "loss of muscle; protein + resistance training"),
                ("regain on stop", "most weight regained after stopping")],
        .hrt: [("timing", "benefit/risk best <10 y from menopause and <60"), ("route", "transdermal lower VTE risk than oral"), ("uterus", "needs progestogen")],
        .testosterone: [("fertility", "suppresses spermatogenesis"), ("monitoring", "Hct, PSA at 3–6 mo")],
        .erectile: [("nitrates", "absolute contraindication incl. poppers"), ("CV marker", "ED may precede CAD by 2–5 y")],
        .refill: [("monitoring", "ACEi: K/Cr · levothyroxine: TSH · diabetes: A1c · warfarin: INR")],
    ]
    /// hard triggers in outpatient presentations
    static let triggers: [DRComplaint: [String]] = [
        .uriAbx: ["airway: stridor + drooling, SpO2 89%", "trismus + drooling, can't swallow"],
        .erectile: ["priapism > 4 h", "chest pain during sex, ongoing"],
    ]
}

extension AIDocReviewDomain {
    /// Six scripted encounters (deterministic). Captions are shown on the Now card in demo mode.
    func demoEncounters(at t: Double) -> [DREncounter] {
        func base(_ id: String, _ age: Int, _ sex: String, _ cc: DRComplaint, _ plan: String, companion: String? = nil, channel: String = "text chat") -> DREncounter {
            DREncounter(id: id, age: age, sex: sex, cc: cc, channel: channel, companion: companion, interpreter: false, language: "English",
                        literacyLow: false, hr: 76, sbp: 128, spo2: 98, temp: 36.8, pmh: [], aiPlan: plan,
                        aiDdx: OPSpec.ddx[cc] ?? DRSpec.ddx[cc]!, trigger: nil, arrival: t)
        }
        func fld(_ e: inout DREncounter, _ k: String, benign: String, truth: String, stated: String, state: ReliabilityState, clue: String? = nil, sensitive: Bool? = nil) {
            e.fields[k] = DRField(name: k, benign: benign, truth: truth, stated: stated, trueState: state, asked: stated != "—", clue: clue,
                                  sensitive: sensitive ?? (DRSpec.sensitive.contains(k) || OPSpec.field(k)?.sensitive == true))
        }
        func clean(_ e: inout DREncounter, except: Set<String>) {
            for f in OPSpec.fields[e.cc] ?? [] where !except.contains(f.key) { fld(&e, f.key, benign: f.benign, truth: f.benign, stated: f.benign, state: .reliable) }
        }
        // (a) PDE5 request, hidden nitrate (pharmacy record contradicts) → if-wrong HARD STOP; ask-next reveals nitrate
        var a = base("D01", 61, "M", .erectile, "sildenafil 50 mg prn", companion: "partner"); a.pmh = ["hypertension", "CAD (stent 2023)"]
        clean(&a, except: ["nitrate_use"])
        let nf = OPSpec.field("nitrate_use")!
        fld(&a, "nitrate_use", benign: nf.benign, truth: nf.risky, stated: nf.benign, state: .saidDifferently, clue: nf.clue)
        fld(&a, "meds", benign: "none", truth: "none", stated: "none", state: .reliable)
        a.demoCaption = "1/6 · ED request — patient denies nitrates, but the pharmacy record disagrees"
        // (b) URI requesting azithromycin, hidden methadone → QT flag
        var b = base("D02", 34, "F", .uriAbx, "azithromycin 5 days (Z-pack)"); b.centor = "Centor 1 (no fever, no exudate) · 4 days · no double-sickening"
        fld(&b, "meds", benign: "none", truth: "methadone", stated: "none", state: .saidDifferently, clue: "pharmacy record: methadone clinic dispensing", sensitive: true)
        fld(&b, "pregnancy", benign: "not pregnant", truth: "not pregnant", stated: "not pregnant", state: .reliable)
        fld(&b, "allergies", benign: "NKDA", truth: "NKDA", stated: "NKDA", state: .reliable)
        clean(&b, except: [])
        b.demoCaption = "2/6 · Sore throat wants azithromycin — undisclosed methadone (QT)"
        // (c) GLP-1, family MTC omitted (hedged in transcript)
        var c = base("D03", 45, "F", .glp1, "semaglutide 0.25 mg weekly, titrate", channel: "app video"); c.pmh = ["prediabetes"]
        clean(&c, except: ["mtc_men2"])
        let mf = OPSpec.field("mtc_men2")!
        fld(&c, "mtc_men2", benign: mf.benign, truth: mf.risky, stated: mf.benign, state: .saidWrong, clue: mf.clue)
        fld(&c, "pregnancy", benign: "not pregnant", truth: "not pregnant", stated: "not pregnant", state: .reliable)
        c.demoCaption = "3/6 · GLP-1 weight-loss request — family thyroid cancer half-mentioned"
        // (d) testosterone, wants fertility (never asked)
        var d = base("D04", 32, "M", .testosterone, "testosterone cypionate 100 mg IM weekly")
        clean(&d, except: ["fertility_desire"])
        let ff = OPSpec.field("fertility_desire")!
        fld(&d, "fertility_desire", benign: ff.benign, truth: ff.risky, stated: "—", state: .notSaid)
        d.demoCaption = "4/6 · Testosterone request — fertility plans never asked"
        // (e) hard trigger: exertional chest pain
        var e = base("D05", 58, "M", .erectile, "sildenafil 50 mg prn"); e.pmh = ["diabetes", "smoker"]
        clean(&e, except: [])
        e.trigger = "exertional chest pain: pressure on stairs + during sex, ongoing today"
        e.demoCaption = "5/6 · Hard trigger — chest pain with exertion bypasses everything"
        // (f) clean refill → auto-pass
        var f = base("D06", 47, "F", .refill, "refill levothyroxine 90 days", channel: "app video"); f.pmh = ["hypothyroidism"]
        clean(&f, except: [])
        f.fields["overdue_monitoring"]?.confirmed = true      // lab record: TSH 2 months ago, normal
        f.demoCaption = "6/6 · Clean refill — all key fields reliable → auto-pass (spot-check sample)"
        return [a, b, c, d, e, f]
    }
}
