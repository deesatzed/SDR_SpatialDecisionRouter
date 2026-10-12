import Foundation

/// SYNTHETIC parametric triage stream. No narratives: complaint template × age × sampled vitals × history flags.
/// Ground truth comes from the rules table below; simulated agents are narrow, noisy and history-blind.
struct SplitMix64 { var s: UInt64
    mutating func next() -> UInt64 { s &+= 0x9E3779B97F4A7C15; var z = s; z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9; z = (z ^ (z >> 27)) &* 0x94D049BB133111EB; return z ^ (z >> 31) }
    mutating func unit() -> Double { Double(next() >> 11) / Double(1 << 53) }
    mutating func range(_ a: Double, _ b: Double) -> Double { a + (b - a) * unit() }
    mutating func chance(_ p: Double) -> Bool { unit() < p }
    mutating func pick<T>(_ xs: [T]) -> T { xs[Int(next() % UInt64(xs.count))] }
}

enum Complaint: String, CaseIterable {
    case chestPain = "chest pain", sob = "SOB", abdPain = "abd pain", fever, headache
    case fallHead = "fall/head strike", neuro = "weakness/neuro deficit", laceration, ankle = "ankle injury", psych, uri = "sore throat/URI"
}

struct TriagePatient {
    var id: String; var age: Int; var sex: String; var complaint: Complaint
    var hr: Int, sbp: Int, rr: Int, spo2: Int, temp: Double, gcs: Int
    var ecgSTE = false, onsetHours = 48.0, suicidal = false
    var anticoag = false, immuno = false, chf = false, ckd = false, priorStrokeMI = false
    var mdro = false, bounceback72h = false, recentSurgery = false, baselineAMS = false, pregnant = false

    var context: String {
        var s = "\(age)\(sex) · \(complaint.rawValue) · HR \(hr) BP \(sbp)/\(Int(Double(sbp) * 0.62)) RR \(rr) SpO2 \(spo2)% T \(String(format: "%.1f", temp)) GCS \(gcs)"
        if complaint == .chestPain { s += ecgSTE ? " · ECG: STE" : " · ECG: no STE" }
        if complaint == .neuro { s += " · onset \(Int(onsetHours)) h" }
        if complaint == .psych { s += suicidal ? " · SI+" : " · SI−" }
        return "[SYNTHETIC] " + s
    }
    var historyFlags: [String] {
        var h: [String] = []
        if anticoag { h.append("anticoag") }; if immuno { h.append("immunosuppressed") }
        if chf { h.append("CHF") }; if ckd { h.append("CKD") }; if priorStrokeMI { h.append("prior stroke/MI") }
        if mdro { h.append("MDRO") }; if bounceback72h { h.append("72h bounceback") }
        if recentSurgery { h.append("recent surgery") }; if baselineAMS { h.append("baseline AMS") }
        if pregnant { h.append("pregnant") }
        return h
    }
}

enum TriageRules {
    /// Documented rules table (also shown in README / exported with logs).
    static let table: [String] = [
        "ESI 1: SBP<80 or SpO2<85 or GCS<9 or RR>35",
        "ESI 2: stroke/STEMI alert, sepsis yes, SpO2<92, HR>130, chest pain age>=40, SI+, pregnant+abd pain, anticoag+head strike, immunosuppressed+fever",
        "ESI 3: chest pain/SOB/abd pain/fever/headache/neuro/fall (default for these); ESI 4: laceration, ankle, fall without head risk; ESI 5: URI",
        "72h bounceback: ESI one level more acute (min 2) for ESI 3-5",
        "Baseline AMS: low GCS (>=13) attributed to baseline does not by itself trigger ESI 1",
        "Sepsis yes: >=2 SIRS (T>=38.3 or <36, HR>90, RR>20) with infection-type complaint; immunosuppressed + T>=38.0 -> yes",
        "Stroke alert: neuro deficit with onset <=24 h; STEMI alert: chest pain + ECG STE",
        "Isolation yes: MDRO history, or fever with respiratory complaint (SOB/URI/fever)",
        "Area: ESI1 or stroke/STEMI -> resus; ESI2-3 -> main ED; ESI4 -> fast track (main ED if isolation); ESI5 -> waiting room (fast track if isolation)",
    ]

    static func sirs(_ p: TriagePatient) -> Int {
        (p.temp >= 38.3 || p.temp < 36 ? 1 : 0) + (p.hr > 90 ? 1 : 0) + (p.rr > 20 ? 1 : 0)
    }
    static let infectionComplaints: Set<Complaint> = [.fever, .sob, .uri, .abdPain]

    static func sepsis(_ p: TriagePatient, historyAware: Bool = true) -> Bool {
        if historyAware && p.immuno && p.temp >= 38.0 { return true }
        return infectionComplaints.contains(p.complaint) && sirs(p) >= 2 && (p.temp >= 38.3 || p.temp < 36)
    }
    static func alert(_ p: TriagePatient) -> String {
        if p.complaint == .neuro && p.onsetHours <= 24 { return "stroke" }
        if p.complaint == .chestPain && p.ecgSTE { return "STEMI" }
        return "none"
    }
    static func isolation(_ p: TriagePatient, historyAware: Bool = true) -> Bool {
        (historyAware && p.mdro) || (p.temp >= 38.0 && [.sob, .uri, .fever].contains(p.complaint))
    }
    static func esi(_ p: TriagePatient, historyAware: Bool = true) -> Int {
        let lowGCSdueToBaseline = historyAware && p.baselineAMS && p.gcs >= 13
        if p.sbp < 80 || p.spo2 < 85 || p.rr > 35 || (p.gcs < 9) { return 1 }
        var e: Int
        let high = alert(p) != "none" || sepsis(p, historyAware: historyAware) || p.spo2 < 92 || p.hr > 130
            || (p.complaint == .chestPain && p.age >= 40) || (p.complaint == .psych && p.suicidal)
            || (p.gcs < 13 && !lowGCSdueToBaseline)
            || (historyAware && p.pregnant && p.complaint == .abdPain)
            || (historyAware && p.anticoag && p.complaint == .fallHead)
            || (historyAware && p.immuno && p.temp >= 38.0)
        if high { e = 2 }
        else {
            switch p.complaint {
            case .laceration, .ankle: e = 4
            case .uri: e = 5
            case .fallHead: e = p.age >= 65 ? 3 : 4
            default: e = 3
            }
        }
        if historyAware && p.bounceback72h && e >= 3 { e = max(2, e - 1) }
        return e
    }
    static func area(esi: Int, alert: String, isolation: Bool) -> String {
        if esi == 1 || alert != "none" { return "resus" }
        if esi <= 3 { return "main ED" }
        if esi == 4 { return isolation ? "main ED" : "fast track" }
        return isolation ? "fast track" : "waiting room"
    }
}

struct TriageGenerator {
    var rng: SplitMix64
    var n = 0
    init(seed: UInt64) { rng = SplitMix64(s: seed) }

    static let scenario = Scenario(
        scenario: "triage_stream",
        agents: [
            AgentSpec(id: "acuity", name: "Acuity Agent", role: "ESI 1–5", tier: 0),
            AgentSpec(id: "sepsis", name: "Sepsis Screen", role: "sepsis yes/no", tier: 0),
            AgentSpec(id: "alert", name: "Stroke/STEMI Alert", role: "none/stroke/STEMI", tier: 0),
            AgentSpec(id: "infection", name: "Infection Control", role: "isolation yes/no", tier: 0),
            AgentSpec(id: "placement", name: "Placement Agent", role: "area (needs ESI+alerts)", tier: 0),
            AgentSpec(id: "charge", name: "Charge Nurse", role: "receives acuity", tier: 1),
            AgentSpec(id: "alertteam", name: "Alert Team", role: "sepsis/stroke/STEMI", tier: 1),
            AgentSpec(id: "isodesk", name: "Isolation Desk", role: "isolation rooms", tier: 1),
            AgentSpec(id: "bedboard", name: "Bed Board", role: "assigns area", tier: 1),
        ],
        links: [
            LinkSpec(source: "acuity", dest: "charge", question: "ESI?", answerType: .category, options: ["1", "2", "3", "4", "5"]),
            LinkSpec(source: "sepsis", dest: "alertteam", question: "Sepsis alert?", answerType: .binary, options: ["yes", "no"]),
            LinkSpec(source: "alert", dest: "alertteam", question: "Stroke/STEMI?", answerType: .category, options: ["none", "stroke", "STEMI"]),
            LinkSpec(source: "infection", dest: "isodesk", question: "Isolation?", answerType: .binary, options: ["yes", "no"]),
            LinkSpec(source: "placement", dest: "bedboard", question: "Area?", answerType: .category, options: ["resus", "main ED", "fast track", "waiting room"]),
        ],
        cases: [])

    mutating func nextPatient() -> TriagePatient {
        n += 1
        let c = rng.pick(Complaint.allCases)
        var p = TriagePatient(id: String(format: "T%03d", n), age: Int(rng.range(18, 92)), sex: rng.chance(0.5) ? "F" : "M", complaint: c,
                              hr: Int(rng.range(62, 105)), sbp: Int(rng.range(105, 160)), rr: Int(rng.range(14, 20)),
                              spo2: Int(rng.range(94, 100)), temp: rng.range(36.4, 37.6), gcs: 15)
        // complaint-specific sampling
        switch c {
        case .chestPain: p.ecgSTE = rng.chance(0.25); if rng.chance(0.3) { p.hr = Int(rng.range(100, 135)) }
        case .sob: p.spo2 = Int(rng.range(84, 97)); p.rr = Int(rng.range(18, 32)); if rng.chance(0.4) { p.temp = rng.range(37.8, 39.4) }
        case .fever, .uri: p.temp = rng.range(37.6, 39.8); p.hr = Int(rng.range(80, 125)); p.rr = Int(rng.range(14, 26))
        case .abdPain: if rng.chance(0.3) { p.temp = rng.range(38.0, 39.2); p.hr = Int(rng.range(92, 120)) }
        case .neuro: p.onsetHours = rng.chance(0.6) ? rng.range(0.5, 20) : rng.range(26, 96); p.sbp = Int(rng.range(140, 200))
        case .fallHead: p.age = max(p.age, Int(rng.range(55, 92)))
        case .psych: p.suicidal = rng.chance(0.4)
        default: break
        }
        if rng.chance(0.05) { p.sbp = Int(rng.range(65, 82)) }              // occasional shock
        // history features (prevalence-ish)
        p.anticoag = rng.chance(c == .fallHead ? 0.5 : 0.2)
        p.immuno = rng.chance([.fever, .uri, .sob].contains(c) ? 0.35 : 0.12)
        p.chf = rng.chance(0.12); p.ckd = rng.chance(0.1); p.priorStrokeMI = rng.chance(0.12)
        p.mdro = rng.chance(0.2); p.bounceback72h = rng.chance(0.2); p.recentSurgery = rng.chance(0.07)
        p.baselineAMS = p.age > 70 && rng.chance(0.25)
        if p.baselineAMS { p.gcs = Int(rng.range(13, 15)) }
        p.pregnant = p.sex == "F" && p.age < 45 && rng.chance(c == .abdPain ? 0.35 : 0.08)
        return p
    }

    /// Builds a case: GT from history-aware rules; agent proposals from narrow history-blind heuristics + noise.
    mutating func nextCase() -> (CaseSpec, TriagePatient) {
        let p = nextPatient()
        let gtESI = TriageRules.esi(p), gtSep = TriageRules.sepsis(p), gtAlert = TriageRules.alert(p), gtIso = TriageRules.isolation(p)
        let gtArea = TriageRules.area(esi: gtESI, alert: gtAlert, isolation: gtIso)
        // agent heuristics
        var aESI = TriageRules.esi(p, historyAware: false)
        if rng.chance(0.12) { aESI = min(5, max(1, aESI + (rng.chance(0.5) ? 1 : -1))) }
        var aSep = TriageRules.sepsis(p, historyAware: false); if rng.chance(0.08) { aSep.toggle() }
        var aAlert = TriageRules.alert(p)
        if rng.chance(0.1) { aAlert = aAlert == "none" ? (p.complaint == .headache || p.complaint == .neuro ? "stroke" : "none") : "none" }
        var aIso = TriageRules.isolation(p, historyAware: false); if rng.chance(0.06) { aIso.toggle() }
        func st(_ gt: String, _ prop: String, _ conf: Double) -> StageSpec { StageSpec(gt: gt, propOk: prop, propBad: prop, conf: conf) }
        let yn: (Bool) -> String = { $0 ? "yes" : "no" }
        let stages = [st("\(gtESI)", "\(aESI)", rng.range(0.55, 0.95)), st(yn(gtSep), yn(aSep), rng.range(0.55, 0.95)),
                      st(gtAlert, aAlert, rng.range(0.6, 0.97)), st(yn(gtIso), yn(aIso), rng.range(0.55, 0.95)),
                      st(gtArea, "", rng.range(0.6, 0.9))]   // placement proposal computed from routed inputs
        let c = CaseSpec(caseID: p.id, context: p.context,
                         history: p.historyFlags.isEmpty ? "none" : p.historyFlags.joined(separator: ", "),
                         rulesApplied: nil, stages: stages)
        return (c, p)
    }

    /// Placement heuristic over the *routed* ESI + alerts (ignores isolation → error source).
    mutating func placementProposal(esi: String, sepsis: String, alert: String) -> String {
        let e = Int(esi) ?? 3
        var a = TriageRules.area(esi: e, alert: alert, isolation: false)
        if rng.chance(0.08) { a = rng.pick(["main ED", "fast track", "waiting room"]) }
        return a
    }
}
