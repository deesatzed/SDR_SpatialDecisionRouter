import Foundation

/// AI-doc review (SYNTHETIC): a physician-in-the-middle reviews AI–patient encounters.
/// Parametric generator with hidden truth per field and context-seeded omissions / recall errors / nondisclosure.

enum DRComplaint: String, CaseIterable {
    case chestPain = "chest pain", abdPain = "abdominal pain", headInjury = "fall / head strike", cough = "cough + fever"
    case uti = "urinary symptoms", headache, palpitations = "palpitations / anxiety", refill = "medication refill"
    case uriAbx = "sore throat / sinus — wants antibiotics", glp1 = "GLP-1 weight-loss request", hrt = "menopause — HRT request"
    case testosterone = "testosterone request", erectile = "erectile dysfunction — PDE5 request"
    static let ed: [DRComplaint] = [.chestPain, .abdPain, .headInjury, .cough, .uti, .headache, .palpitations]
    var isOutpatient: Bool { OPSpec.outpatient.contains(self) }
}

/// One reported field: hidden truth, what was said, and how it was said.
struct DRField {
    let name: String
    let benign: String          // the reassuring value
    var truth: String
    var stated: String          // "—" = not said
    var trueState: ReliabilityState
    var asked: Bool
    var clue: String?           // consistency clue visible to the system (record, transcript)
    var sensitive: Bool
    var confirmed = false
    var physician: ReliabilityState?
}

struct DREncounter {
    var id: String; var age: Int; var sex: String; var cc: DRComplaint
    var channel: String; var companion: String?; var interpreter: Bool; var language: String; var literacyLow: Bool
    var hr: Int?, sbp: Int?, spo2: Int?, temp: Double?
    var pmh: [String]
    var fields: [String: DRField] = [:]
    var aiPlan: String; var aiDdx: [(String, Double)]
    var trigger: String?
    var arrival: Double
    var asks: [String] = []
    var demoCaption: String? = nil
    var centor: String? = nil
    var vitalsLine: String {
        guard let hr, let sbp, let spo2, let temp else { return "vitals: not available" }
        return "HR \(hr) BP \(sbp)/\(Int(Double(sbp) * 0.62)) SpO2 \(spo2)% T \(String(format: "%.1f", temp))"
    }
    func f(_ k: String) -> DRField? { fields[k] }
    func truthIs(_ k: String, _ v: String) -> Bool { fields[k]?.truth == v }
    func truthRisky(_ k: String) -> Bool { fields[k].map { $0.truth != $0.benign } ?? false }
}

enum DRSpec {
    static let expected: [DRComplaint: [String]] = [
        .chestPain: ["symptoms", "meds", "substance", "pmh", "allergies"],
        .abdPain: ["pregnancy", "meds", "substance", "symptoms", "allergies"],
        .headInjury: ["meds", "substance", "symptoms", "safety"],
        .cough: ["meds", "allergies", "symptoms", "substance"],
        .uti: ["pregnancy", "allergies", "meds", "sexual"],
        .headache: ["symptoms", "pregnancy", "meds"],
        .palpitations: ["substance", "meds", "safety", "symptoms"],
        .refill: ["adherence", "meds", "allergies"],
    ]
    static let question: [String: String] = [
        "pregnancy": "Could you be pregnant? When was your last period? (offer test)",
        "meds": "Any medicines from a clinic or pharmacy — e.g. methadone, blood thinners?",
        "substance": "Asked privately: any alcohol, cocaine or other drugs this week?",
        "safety": "Asked privately, without companion: do you feel safe at home?",
        "adherence": "How many doses did you miss in the last week?",
        "allergies": "Any reaction ever to penicillin or other antibiotics?",
        "symptoms": "At its worst, 0–10? Any sweating, fainting, worst-ever pain?",
        "sexual": "Any new sexual partners or possible STI exposure?",
        "pmh": "Any heart disease, clots, or atrial fibrillation?",
    ]
    static let sensitive: Set<String> = ["pregnancy", "substance", "safety", "adherence", "sexual", "symptoms"]
    static func expectedFor(_ c: DRComplaint) -> [String] {
        c.isOutpatient ? (OPSpec.generic[c] ?? []) + (OPSpec.fields[c] ?? []).map(\.key) : expected[c] ?? []
    }
    static func q(_ k: String) -> String { question[k] ?? OPSpec.field(k)?.question ?? k }
    static let plans: [DRComplaint: [String]] = [
        .chestPain: ["reassure, PCP in 48 h", "PPI trial, PCP follow-up"],
        .abdPain: ["oral hydration, ondansetron", "ibuprofen, recheck 24 h"],
        .headInjury: ["observe at home, return precautions"],
        .cough: ["azithromycin 5 days", "levofloxacin 7 days"],
        .uti: ["ciprofloxacin 3 days", "nitrofurantoin 5 days"],
        .headache: ["ibuprofen + rest", "sumatriptan"],
        .palpitations: ["reassure, propranolol 10 mg prn"],
        .refill: ["refill 30 days"],
    ]
    static let ddx: [DRComplaint: [(String, Double)]] = [
        .chestPain: [("MSK", 0.35), ("GERD", 0.25), ("ACS", 0.15), ("anxiety", 0.15), ("PE", 0.1)],
        .abdPain: [("gastroenteritis", 0.45), ("biliary", 0.2), ("appendicitis", 0.15), ("UTI", 0.2)],
        .headInjury: [("concussion", 0.55), ("scalp contusion", 0.4), ("ICH", 0.05)],
        .cough: [("viral URI", 0.55), ("CAP", 0.25), ("bronchitis", 0.2)],
        .uti: [("cystitis", 0.7), ("pyelonephritis", 0.15), ("STI", 0.15)],
        .headache: [("migraine", 0.6), ("tension", 0.35), ("SAH", 0.05)],
        .palpitations: [("anxiety", 0.5), ("SVT", 0.25), ("AF", 0.15), ("thyroid", 0.1)],
        .refill: [("stable chronic disease", 0.9), ("decompensation", 0.1)],
    ]
}

@MainActor final class AIDocReviewDomain: DomainModule {
    let config: DomainConfig
    private var rng = SplitMix64(s: 3)
    private var n = 0
    private(set) var now: Double = 0
    var minutesPerSecond: Double { config.capacity["minutesPerSecond"] ?? 1 }
    var enc: [String: DREncounter] = [:]
    private var arrivals: [DREncounter] = []
    var capacity: EDCapacity
    var escalations = 0, triggers = 0, asksSent = 0, rerates = 0, revealed = 0
    var triggerAckWaits: [Double] = []
    var imported: [DREncounter] = []
    // Bayesian sidecar results (nil → Swift fallback)
    var bn: [String: BNResult] = [:]
    var dirty: [String] = []
    var sidecarSeen = false
    var sidecarOnline: Bool? = nil
    var completed: Set<String> = []
    var demoDone: Bool { DemoState.on && arrivals.isEmpty && Set(enc.keys).isSubset(of: completed) }

    init() {
        config = (try? DomainLoader.config(named: "ai_doc_review.domain")) ?? DomainConfig(id: "ai_doc_review", title: "AI Doc Review (config missing)", agents: [], links: [])
        capacity = EDCapacity(params: config.capacity, seed: 11)
    }

    func reset(seed: UInt64) {
        rng = SplitMix64(s: seed &+ 17); n = 0; enc = [:]; arrivals = []
        escalations = 0; triggers = 0; asksSent = 0; rerates = 0; revealed = 0; triggerAckWaits = []
        now = (config.capacity["startHour"] ?? 9) * 60
        capacity = EDCapacity(params: config.capacity, seed: seed &+ 5); capacity.prewarm(now: now)
        bn = [:]; dirty = []; completed = []
        RiskClient.checkHealth { ok in self.sidecarOnline = ok }
        if DemoState.on { imported = []; arrivals = demoEncounters(at: now); return }
        imported = EncounterImporter.loadDefault(now: now)
        arrivals.append(contentsOf: imported)
        for _ in 0..<3 { arrivals.append(make(at: now)) }
    }

    func advance(minutes: Double) {
        let steps = max(1, Int(minutes.rounded(.up))), dm = minutes / Double(steps)
        for _ in 0..<steps {
            now += dm
            if !DemoState.on, rng.chance((config.capacity["encountersPerHour"] ?? 14) / 60 * dm) { arrivals.append(make(at: now)) }
            capacity.step(now: now, dm: dm)
        }
    }

    func nextItem() -> DomainItem? {
        guard !arrivals.isEmpty else { return nil }
        if DemoState.on && !Set(enc.keys).isSubset(of: completed) { return nil }   // demo: one encounter at a time
        var e = arrivals.removeFirst(); e.arrival = now; enc[e.id] = e
        requestBN(e.id)
        return item(e)
    }

    private func item(_ e: DREncounter) -> DomainItem {
        var f: [String: String] = ["age": "\(e.age)", "sex": e.sex, "cc": e.cc.rawValue, "channel": e.channel,
                                   "companion": e.companion ?? "none", "interpreter": e.interpreter ? "yes" : "no",
                                   "language": e.language, "healthLiteracy": e.literacyLow ? "low" : "adequate",
                                   "aiPlan": e.aiPlan, "vitals": e.vitalsLine]
        for (k, v) in e.fields { f["stated_" + k] = v.stated }
        f["showCapacity"] = e.cc.isOutpatient ? "no" : "yes"
        f["pmh"] = e.pmh.isEmpty ? "none" : e.pmh.joined(separator: ", ")
        let ctx = [e.channel, e.companion.map { "with \($0)" }, e.interpreter ? "interpreter (\(e.language))" : nil].compactMap { $0 }.joined(separator: " · ")
        return DomainItem(id: e.id, fields: f,
                          displayLine: "[SYNTHETIC] \(e.age)\(e.sex) · \(e.cc.rawValue) · \(ctx) · \(e.vitalsLine)",
                          shortLine: "\(e.age)\(e.sex) \(e.cc.rawValue)\(e.trigger.map { " · ⚠ \($0)" } ?? "")",
                          historyLine: (e.pmh.isEmpty ? "none" : e.pmh.joined(separator: ", ")) + " · meds: \(e.fields["meds"]?.stated ?? "—")",
                          arrivalTime: e.arrival)
    }

    // MARK: generator
    private func make(at t: Double) -> DREncounter {
        n += 1
        let edMix = ProcessInfo.processInfo.arguments.contains("-edMix")
        let cc = edMix || !rng.chance(0.75) ? rng.pick(DRComplaint.ed + [.refill]) : rng.pick(OPSpec.outpatient)
        if cc.isOutpatient { return makeOutpatient(cc, at: t) }
        let sex = cc == .uti ? (rng.chance(0.85) ? "F" : "M") : (rng.chance(0.5) ? "F" : "M")
        var age = Int(rng.range(16, 88)); if cc == .headInjury { age = max(age, Int(rng.range(50, 90))) }
        let companion: String? = rng.chance(age >= 75 || age < 18 ? 0.7 : 0.3) ? rng.pick(age < 18 ? ["parent"] : ["partner", "adult child", "friend"]) : nil
        let interp = rng.chance(0.18)
        var e = DREncounter(id: String(format: "E%03d", n), age: age, sex: sex, cc: cc,
                            channel: rng.pick(["text chat", "voice call", "app video", "kiosk"]), companion: companion,
                            interpreter: interp, language: interp ? rng.pick(["Spanish", "Haitian Creole", "Vietnamese", "Arabic"]) : "English",
                            literacyLow: rng.chance(0.2), pmh: [], aiPlan: rng.pick(DRSpec.plans[cc]!), aiDdx: DRSpec.ddx[cc]!, arrival: t)
        // vitals (home device / kiosk) sometimes available
        if rng.chance(0.65) {
            e.hr = Int(rng.range(64, 108)); e.sbp = Int(rng.range(104, 158)); e.spo2 = Int(rng.range(94, 100)); e.temp = rng.range(36.4, 37.8)
            if cc == .cough { e.temp = rng.range(37.6, 39.4); e.hr = Int(rng.range(84, 118)) }
        }
        if rng.chance(0.2) { e.pmh.append("hypertension") }; if rng.chance(0.12) { e.pmh.append("diabetes") }
        if age > 60 && rng.chance(0.2) { e.pmh.append("CAD") }
        // hidden truths
        func addField(_ k: String, benign: String, risky: String, p: Double) {
            e.fields[k] = DRField(name: k, benign: benign, truth: rng.chance(p) ? risky : benign, stated: "—", trueState: .reliable,
                                  asked: false, sensitive: DRSpec.sensitive.contains(k))
        }
        if sex == "F" && age >= 14 && age <= 50 { addField("pregnancy", benign: "not pregnant", risky: "pregnant", p: cc == .abdPain || cc == .uti ? 0.25 : 0.1) }
        let methadoneP = 0.1, anticoagP = age > 65 ? 0.35 : 0.08
        let medTruth = rng.chance(anticoagP) ? "apixaban" : (rng.chance(methadoneP) ? "methadone" : "none")
        e.fields["meds"] = DRField(name: "meds", benign: "none", truth: medTruth, stated: "—", trueState: .reliable, asked: false, sensitive: medTruth == "methadone")
        addField("substance", benign: "none", risky: cc == .chestPain || cc == .palpitations ? "cocaine" : "heavy alcohol", p: 0.18)
        addField("allergies", benign: "NKDA", risky: "penicillin (anaphylaxis)", p: 0.12)
        addField("symptoms", benign: "mild", risky: cc == .chestPain ? "exertional pressure + diaphoresis" : cc == .headache ? "thunderclap, worst ever" : "severe", p: 0.2)
        if [.headInjury, .palpitations].contains(cc) || companion == "partner" { addField("safety", benign: "safe", risky: "unsafe (partner violence)", p: 0.15) }
        if cc == .refill { addField("adherence", benign: "adherent", risky: "missed most doses", p: 0.35) }
        if cc == .uti || cc == .abdPain { addField("sexual", benign: "no new partners", risky: "new partner, unprotected", p: 0.25) }
        if anticoagP > 0.2 && medTruth == "apixaban" { e.pmh.append(rng.chance(0.5) ? "atrial fibrillation" : "") ; e.pmh.removeAll { $0.isEmpty } }
        // conversation: ask / omit / recall error / deliberate nondisclosure, by context
        let exp = Set(DRSpec.expectedFor(cc))
        for k in Array(e.fields.keys) {
            var fd = e.fields[k]!
            fd.asked = rng.chance(exp.contains(k) ? 0.7 : 0.25)
            if !fd.asked { fd.stated = "—"; fd.trueState = .notSaid }
            else {
                var pND = 0.0
                if fd.sensitive && fd.truth != fd.benign {
                    pND = 0.3 + (companion != nil && ["safety", "substance", "sexual", "pregnancy"].contains(k) ? 0.3 : 0)
                        + (interp ? 0.1 : 0) + (age < 18 && ["pregnancy", "sexual", "substance"].contains(k) ? 0.25 : 0) + (e.literacyLow ? 0.05 : 0)
                    if k == "symptoms" { pND = 0.35 + (age > 70 ? 0.15 : 0) }   // minimization
                }
                let pRecall = 0.06 + (age >= 75 && companion == nil ? 0.18 : 0) + (e.literacyLow && ["meds", "allergies"].contains(k) ? 0.12 : 0)
                    + (interp ? 0.08 : 0)
                if rng.chance(min(pND, 0.9)) { fd.stated = fd.benign; fd.trueState = .saidDifferently }
                else if fd.truth != fd.benign && rng.chance(pRecall) { fd.stated = fd.benign; fd.trueState = .saidWrong }
                else if fd.truth == fd.benign && rng.chance(pRecall * 0.3) { fd.stated = "unsure"; fd.trueState = .saidWrong }
                else { fd.stated = fd.truth; fd.trueState = .reliable }
            }
            // consistency clues the system can see
            if fd.truth != fd.benign && fd.stated != fd.truth {
                switch k {
                case "meds" where fd.truth == "methadone": if rng.chance(0.5) { fd.clue = "pharmacy record: methadone clinic dispensing" }
                case "meds" where fd.truth == "apixaban": if e.pmh.contains("atrial fibrillation") { fd.clue = "PMH lists AFib but no anticoagulant stated" }
                case "pregnancy": if rng.chance(0.35) { fd.clue = "transcript: \"my period is a bit late\"" }
                case "safety": if companion == "partner" && rng.chance(0.5) { fd.clue = "partner answered most questions for patient" }
                case "adherence": if rng.chance(0.6) { fd.clue = "refill gap: last fill 70 days ago for 30-day supply" }
                case "substance": if rng.chance(0.3) { fd.clue = "transcript: \"just a few drinks on weekends\" then hesitation" }
                case "symptoms": if rng.chance(0.3) { fd.clue = "transcript: \"it's probably nothing\" + needed to stop walking" }
                default: break
                }
            }
            e.fields[k] = fd
        }
        // hard escalation triggers (unambiguous stated data) — forced on encounter 3 with -forceTrigger
        let force = ProcessInfo.processInfo.arguments.contains("-forceTrigger") && n % 7 == 3
        if force || rng.chance(0.08) {
            switch force ? (n % 2 == 1 ? 0 : 1) : Int(rng.next() % 4) {
            case 0: e.cc = .chestPain; e.trigger = "STEMI: home ECG patch ST elevation + crushing pain"; e.aiDdx = DRSpec.ddx[.chestPain]!
            case 1: e.trigger = "stroke: facial droop + arm weakness, onset 40 min"
            case 2: e.sbp = 78; e.hr = 132; e.spo2 = 89; e.temp = e.temp ?? 37.0; e.trigger = "unstable vitals: SBP 78, HR 132"
            default: e.trigger = "AMS: companion reports new confusion since morning"
            }
        }
        return e
    }

    /// Outpatient AI-doc request: generic fields that apply + complaint-specific hidden truths, same ask/omit/conceal model.
    private func makeOutpatient(_ cc: DRComplaint, at t: Double) -> DREncounter {
        let sex: String = cc == .hrt ? "F" : (cc == .testosterone || cc == .erectile) ? "M" : (rng.chance(0.55) ? "F" : "M")
        let age: Int = cc == .hrt ? Int(rng.range(45, 64)) : cc == .erectile ? Int(rng.range(38, 78)) : cc == .testosterone ? Int(rng.range(25, 66)) : Int(rng.range(19, 72))
        let companion: String? = rng.chance(age >= 75 ? 0.6 : 0.2) ? rng.pick(["partner", "adult child", "friend"]) : nil
        let interp = rng.chance(0.12)
        var e = DREncounter(id: String(format: "E%03d", n), age: age, sex: sex, cc: cc,
                            channel: rng.pick(["text chat", "voice call", "app video"]), companion: companion,
                            interpreter: interp, language: interp ? rng.pick(["Spanish", "Haitian Creole", "Vietnamese", "Arabic"]) : "English",
                            literacyLow: rng.chance(0.15), pmh: [], aiPlan: rng.pick(OPSpec.plans[cc]!), aiDdx: OPSpec.ddx[cc]!, arrival: t)
        if rng.chance(0.4) { e.hr = Int(rng.range(62, 96)); e.sbp = Int(rng.range(108, 150)); e.spo2 = Int(rng.range(96, 100)); e.temp = rng.range(36.4, 37.6) }
        if rng.chance(0.25) { e.pmh.append("hypertension") }; if rng.chance(0.12) { e.pmh.append("diabetes") }
        if cc == .uriAbx {
            let c = Int(rng.range(0, 4.99)), d = Int(rng.range(2, 12))
            e.centor = "Centor/McIsaac \(c) · \(d) days\(d >= 10 ? " (≥10 d)" : "")\(rng.chance(0.15) ? " · double-sickening" : " · no double-sickening")"
        }
        let gen = OPSpec.generic[cc] ?? []
        if gen.contains("meds") {
            let m = rng.chance(0.1) ? "methadone" : "none"
            e.fields["meds"] = DRField(name: "meds", benign: "none", truth: m, stated: "—", trueState: .reliable, asked: false, sensitive: m == "methadone")
        }
        if gen.contains("pregnancy") && sex == "F" && age <= 50 {
            e.fields["pregnancy"] = DRField(name: "pregnancy", benign: "not pregnant", truth: rng.chance(0.08) ? "pregnant" : "not pregnant", stated: "—",
                                            trueState: .reliable, asked: false, sensitive: true)
        }
        if gen.contains("allergies") {
            e.fields["allergies"] = DRField(name: "allergies", benign: "NKDA", truth: rng.chance(0.1) ? "penicillin (anaphylaxis)" : "NKDA", stated: "—",
                                            trueState: .reliable, asked: false, sensitive: false)
        }
        for f in OPSpec.fields[cc] ?? [] {
            e.fields[f.key] = DRField(name: f.key, benign: f.benign, truth: rng.chance(min(0.6, f.p * 2.5)) ? f.risky : f.benign, stated: "—",
                                      trueState: .reliable, asked: false, sensitive: f.sensitive)
        }
        for k in Array(e.fields.keys) {
            var fd = e.fields[k]!
            fd.asked = rng.chance(0.7)
            let risky = fd.truth != fd.benign
            if !fd.asked { fd.trueState = .notSaid }
            else {
                let pND = fd.sensitive && risky ? 0.35 + (companion != nil ? 0.2 : 0) + (interp ? 0.1 : 0) : 0
                let pRecall = 0.06 + (age >= 75 && companion == nil ? 0.15 : 0) + (e.literacyLow ? 0.1 : 0) + (interp ? 0.08 : 0)
                if rng.chance(pND) { fd.stated = fd.benign; fd.trueState = .saidDifferently }
                else if risky && rng.chance(pRecall + (fd.sensitive ? 0 : 0.15)) { fd.stated = fd.benign; fd.trueState = .saidWrong }
                else { fd.stated = fd.truth; fd.trueState = .reliable }
            }
            if risky && fd.stated != fd.truth {
                if let op = OPSpec.field(k), let c = op.clue, rng.chance(0.5) { fd.clue = c }
                if k == "meds", rng.chance(0.5) { fd.clue = "pharmacy record: methadone clinic dispensing" }
            }
            e.fields[k] = fd
        }
        if let tr = OPSpec.triggers[cc], rng.chance(0.05) { e.trigger = rng.pick(tr) }
        return e
    }

    // MARK: Bayesian sidecar
    func requestBN(_ id: String) {
        guard let e = enc[id], let body = BNMap.request(e) else { return }
        Task { @MainActor in
            if let r = await RiskClient.assess(body) { self.bn[id] = r; self.sidecarSeen = true; self.dirty.append(id) }
            else { self.bn[id] = nil }
        }
    }
    func takeDirty() -> [String] { defer { dirty = [] }; return dirty }
    func riskBadge(item: DomainItem) -> String? {
        guard let e = enc[item.id] else { return nil }
        if let r = bn[e.id] { return "BN · params: \(r.param_source)" }
        if BNMap.complaint[e.cc] == nil { return "fallback · no BN for complaint" }
        return sidecarOnline == false && !sidecarSeen ? "fallback · sidecar offline" : "fallback · sidecar pending"
    }

    /// BN-backed reliability where the sidecar answered; Swift heuristics for the remaining fields.
    func reliabilityList(_ e: DREncounter) -> [FieldReliability] {
        var base = fallbackReliability(e)
        guard e.trigger == nil, let r = bn[e.id] else { return base }
        for t in r.truths {
            guard let fname = BNMap.field[t.truth], let k = base.firstIndex(where: { $0.field == fname }), let fd = e.fields[fname] else { continue }
            var f = base[k]
            f.state = ReliabilityState(rawValue: t.state) ?? f.state
            f.score = t.report == "pos" || t.answer == "pos" ? 0.95 : max(0.02, 1 - t.posterior)
            f.why = ["BN: P(\(t.truth)) \(t.label) (\(Int((t.posterior * 100).rounded()))%)", t.why, "params: \(r.param_source)"] + f.why.filter { $0.hasPrefix("inconsistent") }
            if let p = fd.physician { f.state = p; f.why.insert("physician re-rated", at: 0) }
            if let w = t.if_wrong, f.state != .reliable || t.posterior >= 0.15 {
                f.ifWrong = RiskRange(alternative: t.truth == "substance" ? "substance use" : t.truth.replacingOccurrences(of: "_", with: " "),
                                      pAlt: t.posterior, riskLo: w.low, riskHi: w.high, severity: w.severity, worstMiss: w.worst_miss,
                                      planChange: w.plan_change, ddxShift: "\(w.dx): now \(w.label_current) · if wrong up to \(w.label_high)")
            } else { f.ifWrong = nil }
            base[k] = f
        }
        return base
    }

    // MARK: reliability estimate (system view: context + consistency, never the hidden truth)
    func fallbackReliability(_ e: DREncounter) -> [FieldReliability] {
        let key = Set(DRSpec.expectedFor(e.cc))
        return e.fields.values.sorted { ($0.name) < ($1.name) }.map { fd in
            var why: [String] = []
            var score = 0.9
            if fd.sensitive { score -= 0.15; why.append("sensitive topic") }
            if let c = e.companion, ["safety", "substance", "sexual", "pregnancy"].contains(fd.name) { score -= 0.2; why.append("\(c) present") }
            if e.interpreter { score -= 0.1; why.append("interpreter (\(e.language))") }
            if e.age < 18 && ["pregnancy", "sexual", "substance"].contains(fd.name) { score -= 0.15; why.append("adolescent") }
            if e.age >= 75 && e.companion == nil && ["meds", "allergies"].contains(fd.name) { score -= 0.15; why.append("age ≥75, no companion (recall)") }
            if e.literacyLow && ["meds", "allergies", "adherence"].contains(fd.name) { score -= 0.1; why.append("low health literacy") }
            if fd.name == "symptoms" && e.age > 70 { score -= 0.1; why.append("older adults minimize") }
            var state: ReliabilityState = .reliable
            var notAsked: [String] = []
            if fd.stated == "—" { state = .notSaid; score = 0.2; notAsked = [DRSpec.q(fd.name)]; why.insert("never asked", at: 0) }
            else if fd.stated == "unsure" { state = .saidWrong; score = 0.35; why.insert("uncertain answer", at: 0) }
            if let c = fd.clue { state = fd.sensitive ? .saidDifferently : .saidWrong; score = 0.25; why.insert("inconsistent: \(c)", at: 0) }
            if fd.confirmed { state = .reliable; score = max(score, 0.9); why.insert(e.asks.contains(fd.name) ? "confirmed by direct question" : "verified in record", at: 0) }
            if let p = fd.physician { state = p; score = p == .reliable ? max(score, 0.85) : min(score, 0.3); why.insert("physician re-rated", at: 0) }
            score = max(0.05, min(0.98, score))
            var r = FieldReliability(field: fd.name, stated: fd.stated, state: state, score: score, why: why, key: key.contains(fd.name),
                                     ifWrong: nil, notAsked: notAsked, physicianState: fd.physician, confirmedByAsk: fd.confirmed,
                                     trueValue: fd.truth, trueState: fd.trueState)
            if score < 0.75 { r.ifWrong = ifWrong(e, fd, score) }
            return r
        }
    }

    /// Alternative-if-wrong: the dangerous value, risk delta range, worst miss, plan change.
    private func ifWrong(_ e: DREncounter, _ fd: DRField, _ score: Double) -> RiskRange? {
        let base: [String: Double] = ["pregnancy": 0.15, "meds": 0.15, "substance": 0.2, "safety": 0.15, "adherence": 0.35,
                                      "allergies": 0.1, "symptoms": 0.25, "sexual": 0.25]
        let pAlt = min(0.9, (1 - score) * (base[fd.name] ?? 0.1) * 2.4)
        var alt = fd.benign == fd.stated || fd.stated == "—" || fd.stated == "unsure" ? "" : fd.benign
        var sev = 2, worst = "", plan = "", ddx = ""
        let p = e.aiPlan
        switch fd.name {
        case "pregnancy":
            alt = "pregnant"; sev = e.cc == .abdPain ? 5 : 3
            worst = e.cc == .abdPain ? "ruptured ectopic" : "teratogenic exposure"
            plan = "hCG before any disposition" + ((p.contains("cipro") || p.contains("ibuprofen")) ? "; replace \(p.components(separatedBy: " ").first!)" : "")
            ddx = e.cc == .abdPain ? "ectopic enters ddx" : "pregnancy-safe meds only"
        case "meds":
            if e.cc == .headInjury { alt = "on anticoagulant"; sev = 5; worst = "delayed ICH"; plan = "CT head now"; ddx = "ICH ↑×4" }
            else if p.contains("azithro") || p.contains("levo") || p.contains("cipro") || p.contains("ondansetron") {
                alt = "on methadone"; sev = 4; worst = "QT prolongation / torsades"; plan = "ECG for QTc; avoid \(p.components(separatedBy: " ").first!)"; ddx = "—" }
            else { alt = "on undisclosed meds"; sev = 2; worst = "interaction"; plan = "med reconciliation"; ddx = "—" }
        case "substance":
            if e.cc == .chestPain || e.cc == .palpitations { alt = "cocaine use"; sev = 4; worst = "cocaine-associated ACS"; plan = "ED eval; no β-blocker"; ddx = "ACS ↑, vasospasm" }
            else { alt = "heavy alcohol"; sev = 3; worst = "withdrawal / pancreatitis"; plan = "CIWA, lipase"; ddx = "pancreatitis enters" }
        case "safety": alt = "unsafe at home"; sev = 4; worst = "return with injury"; plan = "private screen, SW, safe disposition"; ddx = "NAT/IPV injury pattern"
        case "adherence": alt = "non-adherent"; sev = 3; worst = "decompensation (DKA/seizure)"; plan = "labs before refill, adherence plan"; ddx = "decompensation ↑"
        case "allergies":
            alt = "penicillin anaphylaxis"; let beta = p.contains("amox") || p.contains("cephal")
            sev = beta ? 5 : 1; worst = beta ? "anaphylaxis" : "none for current plan"; plan = beta ? "switch antibiotic class" : "none"; ddx = "—"
        case "symptoms":
            alt = "worse than stated"; sev = e.cc == .chestPain || e.cc == .headache ? 5 : 3
            worst = e.cc == .chestPain ? "missed ACS" : e.cc == .headache ? "missed SAH" : "under-triage"
            plan = e.cc == .chestPain ? "ECG + troponin today" : e.cc == .headache ? "ED for CT" : "same-day visit"
            ddx = e.cc == .chestPain ? "ACS 15%→up to 40%" : e.cc == .headache ? "SAH 5%→up to 20%" : "shift to serious causes"
        case "sexual": alt = "STI exposure"; sev = 2; worst = "untreated PID/STI"; plan = "add STI testing"; ddx = "STI/PID ↑"
        default:
            guard let op = OPSpec.field(fd.name) else { return nil }
            alt = op.risky; sev = ["escalate": 5, "decline": 4, "labs first": 3].first { $0.key == op.action }?.value ?? 2
            if op.key == "nitrate_use" { sev = 5 }
            worst = op.worst; plan = op.action; ddx = "—"
        }
        let w = Double(sev) / 5
        return RiskRange(alternative: alt, pAlt: pAlt, riskLo: pAlt * w * 0.6, riskHi: min(1, pAlt * w * 1.4), severity: sev,
                         worstMiss: worst, planChange: plan, ddxShift: ddx)
    }

    /// differential with uncertainty: low-reliability fields widen/shift probabilities
    func ddxWithUncertainty(_ e: DREncounter) -> [(String, Double, Double)] {
        var d = e.aiDdx.map { ($0.0, $0.1, $0.1) }
        for r in reliabilityList(e) {
            guard let w = r.ifWrong else { continue }
            let add: String? = r.field == "pregnancy" && e.cc == .abdPain ? "ectopic" :
                r.field == "meds" && e.cc == .headInjury ? "ICH" : r.field == "substance" && e.cc == .chestPain ? "ACS" :
                r.field == "symptoms" && e.cc == .chestPain ? "ACS" : r.field == "symptoms" && e.cc == .headache ? "SAH" :
                r.field == "substance" && e.cc == .abdPain ? "pancreatitis" : r.field == "sexual" ? "STI" : nil
            guard let a = add else { continue }
            let hi = w.pAlt * 0.8
            if let i = d.firstIndex(where: { $0.0 == a }) { d[i].2 = min(0.9, d[i].2 + hi) } else { d.append((a, 0, hi)) }
            for i in d.indices where d[i].0 != a { d[i].1 = d[i].1 * (1 - hi) }
        }
        return d.sorted { $0.2 > $1.2 }
    }

    // MARK: ground truth / proposals
    func trueESI(_ e: DREncounter) -> Int {
        if e.trigger != nil { return e.trigger!.hasPrefix("unstable") ? 1 : 2 }
        if e.truthIs("pregnancy", "pregnant") && e.cc == .abdPain { return 2 }
        if e.truthIs("meds", "apixaban") && e.cc == .headInjury { return 2 }
        if e.truthRisky("symptoms") && [.chestPain, .headache].contains(e.cc) { return 2 }
        if e.truthIs("substance", "cocaine") && e.cc == .chestPain { return 2 }
        return statedESI(e)
    }
    func statedESI(_ e: DREncounter) -> Int {
        if let s = e.sbp, s < 90 { return 1 }
        switch e.cc {
        case .chestPain: return e.age >= 40 ? 2 : 3
        case .headInjury: return e.age >= 65 ? 3 : 4
        case .abdPain, .headache, .palpitations: return 3
        case .cough: return (e.spo2 ?? 97) < 92 ? 2 : 4
        case .uti, .refill: return 5
        case .uriAbx: return (e.spo2 ?? 98) < 92 ? 2 : 5
        case .glp1, .hrt, .testosterone, .erectile: return 5
        }
    }
    func truePlan(_ e: DREncounter) -> String {
        if e.trigger != nil { return "escalate" }
        if e.cc.isOutpatient { return outpatientPlan(e) }
        let dxDanger = (e.truthIs("pregnancy", "pregnant") && e.cc == .abdPain) || (e.truthIs("meds", "apixaban") && e.cc == .headInjury)
            || (e.truthRisky("symptoms") && [.chestPain, .headache].contains(e.cc)) || (e.truthIs("substance", "cocaine") && e.cc == .chestPain)
            || e.truthRisky("safety")
        if dxDanger { return "escalate" }
        let p = e.aiPlan
        let planHazard = (e.truthIs("meds", "methadone") && (p.contains("azithro") || p.contains("levo") || p.contains("cipro") || p.contains("ondansetron")))
            || (e.truthIs("pregnancy", "pregnant") && (p.contains("cipro") || p.contains("ibuprofen")))
            || (e.truthRisky("allergies") && (p.contains("amox") || p.contains("cephal"))) || e.truthRisky("adherence")
            || (e.truthIs("substance", "cocaine") && p.contains("propranolol"))
        return planHazard ? "with conditions" : "sign off"
    }
    func outpatientPlan(_ e: DREncounter) -> String {
        var acts: [String] = []
        for (k, fd) in e.fields where fd.truth != fd.benign {
            if let op = OPSpec.field(k) { acts.append(op.action); continue }
            let p = e.aiPlan
            switch k {
            case "meds" where ["azithro", "levo"].contains { p.contains($0) }: acts.append("with conditions")
            case "pregnancy": acts.append(e.cc == .glp1 ? "decline" : (p.contains("levo") ? "with conditions" : "sign off"))
            case "allergies" where p.contains("amox"): acts.append("with conditions")
            default: break
            }
        }
        return acts.max { (OPSpec.actionRank[$0] ?? 0) < (OPSpec.actionRank[$1] ?? 0) } ?? "sign off"
    }

    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String? {
        guard let e = enc[item.id] else { return nil }
        switch link.id { case "esi": return "\(trueESI(e))"; case "plan": return truePlan(e); default: return nil }
    }
    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal {
        guard let e = enc[item.id] else { return Proposal(answer: link.options[0], confidence: 0.5) }
        switch link.id {
        case "esi":
            var x = statedESI(e); if rng.chance(0.1) { x = min(5, max(1, x + (rng.chance(0.5) ? 1 : -1))) }
            return Proposal(answer: "\(x)", confidence: rng.range(0.62, 0.95))
        case "plan":
            if DemoState.on { let k = min(max((Int(e.id.dropFirst()) ?? 1) - 1, 0), 5)
                return Proposal(answer: "sign off", confidence: [0.82, 0.86, 0.84, 0.8, 1.0, 0.95][k]) }
            return Proposal(answer: rng.chance(0.08) ? "with conditions" : "sign off", confidence: rng.range(0.6, 0.93))
        default: return Proposal(answer: link.options[0], confidence: 0.5)
        }
    }

    func complete(item: DomainItem, effective: [String: String]) {
        guard let e = enc[item.id] else { return }
        completed.insert(e.id)
        if effective["plan"] == "escalate" {
            capacity.place(id: e.id, esi: Int(effective["esi"] ?? "3") ?? 3, area: (Int(effective["esi"] ?? "3") ?? 3) <= 2 ? "resus" : "main ED",
                           isolation: false, arrival: now, now: now)
        }
    }
    func alertFired(item: DomainItem, link: LinkSpec) { escalations += 1 }

    // MARK: review + reliability hooks
    func hardTrigger(item: DomainItem) -> String? { enc[item.id]?.trigger }
    func reliability(item: DomainItem) -> [FieldReliability] { enc[item.id].map(reliabilityList) ?? [] }
    func hiddenTruth(item: DomainItem) -> [String: String] {
        guard let e = enc[item.id] else { return [:] }
        var h = e.fields.mapValues { "\($0.truth) [\($0.trueState.rawValue)]" }
        h["trueESI"] = "\(trueESI(e))"; h["truePlan"] = truePlan(e)
        return h
    }
    func askNext(item: DomainItem) -> [VOIQuestion] {
        guard let e = enc[item.id], e.trigger == nil else { return [] }
        if let r = bn[e.id], r.voi.contains(where: { $0.voi > 0.0005 && BNMap.field[$0.truth].map { !e.asks.contains($0) } == true }) {
            return r.voi.compactMap { q -> VOIQuestion? in
                guard let f = BNMap.field[q.truth], !e.asks.contains(f), q.voi > 0.0005 else { return nil }
                return VOIQuestion(id: "\(e.id)-\(f)", field: f, text: q.question, voi: q.voi,
                                   rationale: "BN: expected-loss reduction \(String(format: "%.2f", q.voi)) · P(answer rules out critical) \(Int(q.p_ruleout * 100))%")
            }.prefix(3).map { $0 }
        }
        return reliabilityList(e).compactMap { r -> VOIQuestion? in
            guard let w = r.ifWrong, !r.confirmedByAsk, !e.asks.contains(r.field) else { return nil }
            let planChange = w.planChange == "none" || w.planChange == "sign off" ? 0.1 : 1.0
            let voi = w.pAlt * planChange * Double(w.severity)
            return VOIQuestion(id: "\(e.id)-\(r.field)", field: r.field, text: DRSpec.q(r.field), voi: voi,
                               rationale: "P(wrong) \(Int(w.pAlt * 100))% × plan change \(w.planChange) × severity \(w.severity)")
        }.sorted { $0.voi > $1.voi }.prefix(3).map { $0 }
    }
    func ask(item: DomainItem, questionId: String) -> String? {
        guard var e = enc[item.id], let field = questionId.split(separator: "-").last.map(String.init), var fd = e.fields[field] else { return nil }
        asksSent += 1; e.asks.append(field)
        // simulated patient answers per hidden truth; direct private physician questions reveal more, but not always
        let reveal = DemoState.on || fd.truth == fd.benign || rng.chance(fd.sensitive ? 0.7 : 0.9)
        fd.stated = reveal ? fd.truth : fd.benign
        fd.asked = true; fd.confirmed = reveal; fd.clue = nil
        if reveal && fd.truth != fd.benign { revealed += 1 }
        e.fields[field] = fd; enc[e.id] = e
        requestBN(e.id)
        return reveal ? "Pt: \(fd.truth)" : "Pt: \(fd.benign) (hesitant)"
    }
    func rerate(item: DomainItem, field: String, state: ReliabilityState) {
        guard var e = enc[item.id] else { return }
        e.fields[field]?.physician = state; enc[e.id] = e; rerates += 1; dirty.append(e.id)
    }
    func refreshed(item: DomainItem) -> DomainItem? { enc[item.id].map(self.item) }

    func transcript(item: DomainItem) -> [String] {
        guard let e = enc[item.id] else { return [] }
        var t = ["AI: What brings you in today?", "Pt: \(e.cc.rawValue)\(e.trigger.map { " — \($0)" } ?? "")."]
        let order = ["symptoms", "meds", "pregnancy", "substance", "allergies", "safety", "adherence", "sexual"] + (OPSpec.fields[e.cc] ?? []).map(\.key)
        for k in order {
            guard let fd = e.fields[k], fd.asked else { continue }
            t.append("AI: \(DRSpec.q(k).components(separatedBy: "?").first!)?")
            t.append("Pt: " + (fd.stated == "unsure" ? "I'm not sure…" : fd.stated) + (fd.clue.flatMap { $0.hasPrefix("transcript") ? " " + $0.replacingOccurrences(of: "transcript: ", with: "") : nil } ?? ""))
        }
        for a in e.asks { if let fd = e.fields[a] { t.append("MD: \(DRSpec.q(a))"); t.append("Pt: \(fd.stated)") } }
        return t
    }

    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip] {
        guard let e = enc[item.id] else { return [] }
        if let t = e.trigger { return [ReasonChip(text: "HARD TRIGGER: \(t)", key: "hard trigger", severity: .high)] }
        var r: [ReasonChip] = []
        if let n = e.fields["nitrate_use"], n.stated != n.benign && n.stated != "—" {
            r.append(ReasonChip(text: "HARD STOP: PDE5 inhibitor + nitrate (\(n.stated)) — do not prescribe", key: "HARD STOP", severity: .high))
        }
        let rel = reliabilityList(e)
        for f in rel where f.key && f.state != .reliable {
            r.append(ReasonChip(text: "\(f.field): \(f.state.rawValue)", key: f.state.rawValue,
                                severity: (f.ifWrong?.severity ?? 0) >= 4 ? .high : .warn))
        }
        if let b = bn[e.id] {
            if b.escalation.recommend {
                r.append(ReasonChip(text: "BN: P(critical miss) \(b.p_critical_label) → recommend escalation", key: "recommend escalation", severity: .high))
            }
        } else if rel.contains(where: { ($0.ifWrong?.severity ?? 0) >= 4 && ($0.ifWrong?.pAlt ?? 0) >= 0.2 && !$0.confirmedByAsk && $0.physicianState != .reliable }) {
            r.append(ReasonChip(text: "critical miss not excluded → recommend escalation", key: "recommend escalation", severity: .high))
        }
        if let s = e.sbp, s < 95 { r.append(ReasonChip(text: "SBP \(s)", key: "abnormal vitals", severity: .high)) }
        return r
    }
    func urgency(item: DomainItem, link: LinkSpec, proposal: String) -> Double {
        guard let e = enc[item.id] else { return 0 }
        let w = reliabilityList(e).compactMap { $0.ifWrong }.map { $0.riskHi }.max() ?? 0
        return w * 1.5 + (link.id == "plan" ? 0.2 : 0)
    }
    func downstreamPreview(item: DomainItem, link: LinkSpec, answer: String) -> String? {
        guard let e = enc[item.id] else { return nil }
        switch (link.id, answer) {
        case ("plan", "sign off"): return "Orders: \(e.cc.isOutpatient ? "prescription sent" : "AI plan released to patient") — \(e.aiPlan)"
        case ("plan", "with conditions"): return "Orders: prescribe with changes (\(reliabilityList(e).compactMap { $0.ifWrong?.planChange }.first ?? "edit plan"))"
        case ("plan", "labs first"): return "Orders: request held; labs / measurement / evaluation ordered first"
        case ("plan", "decline"): return "Orders: request declined — patient message with reason + alternative/referral"
        case ("plan", "escalate"):
            return e.trigger != nil ? "Alert Team already paged; ED \((capacity.rooms["resus"] ?? 0) - capacity.used("resus")) resus free" :
                "Alert Team: physician callback ≤15 min; ED main \(capacity.used("main ED"))/\(capacity.rooms["main ED"] ?? 0)"
        case ("esi", let x): return "ED Intake: ESI \(x) → \(Int(x) ?? 3 <= 2 ? "send to ED now" : Int(x) ?? 3 == 3 ? "same-day visit" : "virtual follow-up")"
        default: return nil
        }
    }
    func detail(item: DomainItem, section: String) -> [(String, String)]? {
        guard let e = enc[item.id] else { return nil }
        switch section {
        case "Transcript": return transcript(item: item).enumerated().map { ("\($0.offset + 1)", $0.element) }
        case "Extracted fields":
            return [("CC", e.cc.rawValue), ("vitals", e.vitalsLine), ("PMH", e.pmh.isEmpty ? "none" : e.pmh.joined(separator: ", "))]
                + e.fields.values.sorted { $0.name < $1.name }.map { ($0.name, $0.stated) }
        case "Context":
            return [("age/sex", "\(e.age)\(e.sex)"), ("channel", e.channel), ("companion", e.companion ?? "none"),
                    ("language", e.interpreter ? "\(e.language) via interpreter" : e.language), ("health literacy", e.literacyLow ? "low" : "adequate")]
        case "AI differential (with uncertainty)":
            return ddxWithUncertainty(e).map { ($0.0, $0.1 == $0.2 ? "\(Int($0.1 * 100))%" : "\(Int($0.1 * 100))–\(Int($0.2 * 100))%") }
        case "AI triage + plan":
            let alt = reliabilityList(e).contains { $0.ifWrong != nil && ($0.ifWrong!.severity >= 4) } ? " (ESI \(max(1, statedESI(e) - 1)) if key field wrong)" : ""
            return [("ESI", "\(statedESI(e))\(alt)"), ("plan", e.aiPlan)]
        case "Scores + counselling":
            let rows = (e.centor.map { [("Centor/McIsaac", $0)] } ?? []) + (OPSpec.counselling[e.cc] ?? [])
            return rows.isEmpty ? nil : rows
        case "Expected questions not asked":
            let miss = reliabilityList(e).filter { $0.state == .notSaid }.flatMap { $0.notAsked }
            return miss.isEmpty ? [("—", "all expected questions asked")] : miss.map { ("☐", $0) }
        default: return nil
        }
    }

    func applicableLinks(item: DomainItem) -> [String]? { enc[item.id].map { $0.cc.isOutpatient ? ["plan"] : nil } ?? nil }
    func demoCaption(item: DomainItem) -> String? { enc[item.id]?.demoCaption }
    var isDemoDone: Bool { demoDone }
    func capacitySnapshot() -> [String: String] { capacity.snapshot(queue: arrivals.count) }
    func capacityLine() -> String { "ED " + capacity.line(queue: arrivals.count).replacingOccurrences(of: "triage", with: "AI queue") }
    func boardMetrics(_ s: EngineStats) -> [MetricValue] {
        [MetricValue(label: "Hard triggers", value: "\(enc.values.filter { $0.trigger != nil }.count)"),
         MetricValue(label: "Escalations", value: "\(escalations)"),
         MetricValue(label: "Ask-next sent", value: "\(asksSent)"),
         MetricValue(label: "Truth revealed", value: "\(revealed)"),
         MetricValue(label: "Re-ratings", value: "\(rerates)"),
         MetricValue(label: "Risk engine", value: sidecarSeen || sidecarOnline == true ? "BN online" : sidecarOnline == false ? "fallback (offline)" : "checking…"),
         MetricValue(label: "ED census", value: "main \(capacity.used("main ED"))/\(capacity.rooms["main ED"] ?? 0)")]
    }
    func breakdown() -> [(String, Int)] {
        var c: [String: Int] = [:]
        for e in enc.values { for f in reliabilityList(e) where f.state != .reliable { c[f.state.rawValue, default: 0] += 1 } }
        return ReliabilityState.allCases.filter { $0 != .reliable }.map { ($0.rawValue, c[$0.rawValue] ?? 0) }
    }
}
