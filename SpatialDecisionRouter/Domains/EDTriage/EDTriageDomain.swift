import Foundation

/// ED triage plug-in (SYNTHETIC). Generator + rule hooks; everything else lives in ed_triage.domain.json.
enum Complaint: String, CaseIterable {
    case chestPain = "chest pain", sob = "SOB", abdPain = "abd pain", fever, headache
    case fallHead = "fall/head strike", neuro = "weakness/neuro deficit", laceration, ankle = "ankle injury", psych, uri = "sore throat/URI"
}

struct EDPatient {
    var id: String; var age: Int; var sex: String; var complaint: Complaint
    var hr: Int, sbp: Int, rr: Int, spo2: Int, temp: Double, gcs: Int
    var ecgSTE = false, onsetHours = 48.0, suicidal = false
    var anticoag = false, immuno = false, chf = false, ckd = false, priorStrokeMI = false
    var mdro = false, bounceback72h = false, recentSurgery = false, baselineAMS = false, pregnant = false
    var arrival: Double = 0

    var vitals: String { "HR \(hr) BP \(sbp)/\(Int(Double(sbp) * 0.62)) RR \(rr) SpO2 \(spo2)% T \(String(format: "%.1f", temp)) GCS \(gcs)" }
    var extra: String {
        switch complaint {
        case .chestPain: return ecgSTE ? " · ECG: STE" : " · ECG: no STE"
        case .neuro: return " · onset \(Int(onsetHours)) h"
        case .psych: return suicidal ? " · SI+" : " · SI−"
        default: return ""
        }
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
    var fields: [String: String] {
        var f: [String: String] = ["age": "\(age)", "sex": sex, "complaint": complaint.rawValue, "hr": "\(hr)", "sbp": "\(sbp)",
                                   "rr": "\(rr)", "spo2": "\(spo2)", "temp": String(format: "%.1f", temp), "gcs": "\(gcs)"]
        if complaint == .chestPain { f["ecgSTE"] = ecgSTE ? "yes" : "no" }
        if complaint == .neuro { f["onsetHours"] = "\(Int(onsetHours))" }
        if complaint == .psych { f["suicidal"] = suicidal ? "yes" : "no" }
        for h in historyFlags { f["hx_" + h.replacingOccurrences(of: " ", with: "_")] = "yes" }
        return f
    }
}

enum EDRules {
    static func sirs(_ p: EDPatient) -> Int { (p.temp >= 38.3 || p.temp < 36 ? 1 : 0) + (p.hr > 90 ? 1 : 0) + (p.rr > 20 ? 1 : 0) }
    static let infection: Set<Complaint> = [.fever, .sob, .uri, .abdPain]
    static func sepsis(_ p: EDPatient, hx: Bool = true) -> Bool {
        if hx && p.immuno && p.temp >= 38.0 { return true }
        return infection.contains(p.complaint) && sirs(p) >= 2 && (p.temp >= 38.3 || p.temp < 36)
    }
    static func alert(_ p: EDPatient) -> String {
        if p.complaint == .neuro && p.onsetHours <= 24 { return "stroke" }
        if p.complaint == .chestPain && p.ecgSTE { return "STEMI" }
        return "none"
    }
    static func isolation(_ p: EDPatient, hx: Bool = true) -> Bool {
        (hx && p.mdro) || (p.temp >= 38.0 && [.sob, .uri, .fever].contains(p.complaint))
    }
    static func esi(_ p: EDPatient, hx: Bool = true) -> Int {
        if p.sbp < 80 || p.spo2 < 85 || p.rr > 35 || p.gcs < 9 { return 1 }
        let gcsBaseline = hx && p.baselineAMS && p.gcs >= 13
        let high = alert(p) != "none" || sepsis(p, hx: hx) || p.spo2 < 92 || p.hr > 130
            || (p.complaint == .chestPain && p.age >= 40) || (p.complaint == .psych && p.suicidal)
            || (p.gcs < 13 && !gcsBaseline)
            || (hx && p.pregnant && p.complaint == .abdPain) || (hx && p.anticoag && p.complaint == .fallHead)
            || (hx && p.immuno && p.temp >= 38.0)
        var e: Int
        if high { e = 2 } else {
            switch p.complaint {
            case .laceration, .ankle: e = 4
            case .uri: e = 5
            case .fallHead: e = p.age >= 65 ? 3 : 4
            default: e = 3
            }
        }
        if hx && p.bounceback72h && e >= 3 { e = max(2, e - 1) }
        return e
    }
    static func baseArea(esi: Int, alert: String, isolation: Bool) -> String {
        if esi == 1 || alert != "none" { return "resus" }
        if esi <= 3 { return "main ED" }
        if esi == 4 { return isolation ? "main ED" : "fast track" }
        return isolation ? "fast track" : "waiting room"
    }
}

@MainActor final class EDTriageDomain: DomainModule {
    let config: DomainConfig
    private var rng = SplitMix64(s: 1)
    private var n = 0
    private(set) var now: Double = 0
    var minutesPerSecond: Double { config.capacity["minutesPerSecond"] ?? 1 }
    var patients: [String: EDPatient] = [:]
    private var arrivals: [EDPatient] = []
    var capacity: EDCapacity   // internal so EDReview can read it

    init() {
        config = (try? DomainLoader.config(named: "ed_triage.domain")) ?? DomainConfig(id: "ed_triage", title: "ED (config missing)", agents: [], links: [])
        capacity = EDCapacity(params: config.capacity, seed: 7)
    }

    func reset(seed: UInt64) {
        rng = SplitMix64(s: seed); n = 0; patients = [:]; arrivals = []
        now = (config.capacity["startHour"] ?? 10) * 60
        capacity = EDCapacity(params: config.capacity, seed: seed &+ 1)
        capacity.prewarm(now: now)
        // a few patients already at the door
        for _ in 0..<3 { arrivals.append(makePatient(at: now)) }
    }

    func advance(minutes: Double) {
        let steps = max(1, Int(minutes.rounded(.up)))
        let dm = minutes / Double(steps)
        for _ in 0..<steps {
            now += dm
            let hour = now / 60
            let base = config.capacity["arrivalsPerHourBase"] ?? 9, amp = config.capacity["arrivalsPerHourAmp"] ?? 5
            let lambda = max(1, base + amp * sin((hour - 9) / 24 * 2 * .pi))   // peak mid-afternoon
            if rng.chance(lambda / 60 * dm) { arrivals.append(makePatient(at: now)) }
            capacity.step(now: now, dm: dm)
        }
    }

    func nextItem() -> DomainItem? {
        guard !arrivals.isEmpty else { return nil }
        let p = arrivals.removeFirst()
        patients[p.id] = p
        let hx = p.historyFlags.isEmpty ? "none" : p.historyFlags.joined(separator: ", ")
        return DomainItem(id: p.id, fields: p.fields,
                          displayLine: "[SYNTHETIC] \(p.age)\(p.sex) · \(p.complaint.rawValue) · \(p.vitals)\(p.extra)",
                          shortLine: "\(p.age)\(p.sex) \(p.complaint.rawValue)" + (hx == "none" ? "" : " · \(hx)"),
                          historyLine: hx, arrivalTime: p.arrival)
    }

    private func makePatient(at t: Double) -> EDPatient {
        n += 1
        let c = rng.pick(Complaint.allCases)
        var p = EDPatient(id: String(format: "P%03d", n), age: Int(rng.range(18, 92)), sex: rng.chance(0.5) ? "F" : "M", complaint: c,
                          hr: Int(rng.range(62, 105)), sbp: Int(rng.range(105, 160)), rr: Int(rng.range(14, 20)),
                          spo2: Int(rng.range(94, 100)), temp: rng.range(36.4, 37.6), gcs: 15)
        p.arrival = t
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
        if rng.chance(0.05) { p.sbp = Int(rng.range(65, 82)) }
        p.anticoag = rng.chance(c == .fallHead ? 0.5 : 0.2)
        p.immuno = rng.chance([.fever, .uri, .sob].contains(c) ? 0.35 : 0.12)
        p.chf = rng.chance(0.12); p.ckd = rng.chance(0.1); p.priorStrokeMI = rng.chance(0.12)
        p.mdro = rng.chance(0.2); p.bounceback72h = rng.chance(0.2); p.recentSurgery = rng.chance(0.07)
        p.baselineAMS = p.age > 70 && rng.chance(0.25)
        if p.baselineAMS { p.gcs = Int(rng.range(13, 15)) }
        p.pregnant = p.sex == "F" && p.age < 45 && rng.chance(c == .abdPain ? 0.35 : 0.08)
        return p
    }

    // MARK: rule hooks
    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String? {
        guard let p = patients[item.id] else { return nil }
        let yn: (Bool) -> String = { $0 ? "yes" : "no" }
        switch link.id {
        case "acuity": return "\(EDRules.esi(p))"
        case "sepsis": return yn(EDRules.sepsis(p))
        case "alert": return EDRules.alert(p)
        case "isolation": return yn(EDRules.isolation(p))
        case "placement":
            let e = EDRules.esi(p), a = EDRules.alert(p), iso = EDRules.isolation(p)
            return capacity.capacityAwareArea(esi: e, alert: a, base: EDRules.baseArea(esi: e, alert: a, isolation: iso))
        default: return nil
        }
    }

    /// Narrow, history-blind, capacity-blind heuristics + noise.
    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal {
        guard let p = patients[item.id] else { return Proposal(answer: link.options[0], confidence: 0.5) }
        let yn: (Bool) -> String = { $0 ? "yes" : "no" }
        let conf = rng.range(0.55, 0.95)
        switch link.id {
        case "acuity":
            var e = EDRules.esi(p, hx: false)
            if rng.chance(0.12) { e = min(5, max(1, e + (rng.chance(0.5) ? 1 : -1))) }
            return Proposal(answer: "\(e)", confidence: conf)
        case "sepsis":
            var s = EDRules.sepsis(p, hx: false); if rng.chance(0.08) { s.toggle() }
            return Proposal(answer: yn(s), confidence: conf)
        case "alert":
            var a = EDRules.alert(p)
            if rng.chance(0.1) { a = a == "none" ? ([.headache, .neuro].contains(p.complaint) ? "stroke" : "none") : "none" }
            return Proposal(answer: a, confidence: conf)
        case "isolation":
            var i = EDRules.isolation(p, hx: false); if rng.chance(0.06) { i.toggle() }
            return Proposal(answer: yn(i), confidence: conf)
        case "placement":
            let e = Int(routed["acuity"] ?? "3") ?? 3
            var a = EDRules.baseArea(esi: e, alert: routed["alert"] ?? "none", isolation: false)
            if rng.chance(0.08) { a = rng.pick(["main ED", "fast track", "waiting room"]) }
            return Proposal(answer: a, confidence: rng.range(0.6, 0.9))
        default: return Proposal(answer: link.options[0], confidence: 0.5)
        }
    }

    func complete(item: DomainItem, effective: [String: String]) {
        guard let p = patients[item.id] else { return }
        capacity.place(id: p.id, esi: Int(effective["acuity"] ?? "3") ?? 3, area: effective["placement"] ?? "waiting room",
                       isolation: effective["isolation"] == "yes", arrival: p.arrival, now: now)
    }
    func alertFired(item: DomainItem, link: LinkSpec) {
        if let p = patients[item.id] { capacity.alertWaits.append(now - p.arrival) }
    }
    func capacitySnapshot() -> [String: String] { capacity.snapshot(queue: arrivals.count) }
    func capacityLine() -> String { capacity.line(queue: arrivals.count) }
    func boardMetrics(_ s: EngineStats) -> [MetricValue] {
        [MetricValue(label: "Door→room (med)", value: String(format: "%.0f min", capacity.medianDoorToRoom)),
         MetricValue(label: "Waiting", value: "\(capacity.waitingCount + arrivals.count)"),
         MetricValue(label: "LWBS", value: "\(capacity.lwbs)"),
         MetricValue(label: "Boarding", value: String(format: "%.1f h", capacity.boardingMinutes / 60)),
         MetricValue(label: "Alert wait (med)", value: String(format: "%.0f min", capacity.medianAlertWait))]
    }
    func breakdown() -> [(String, Int)] { capacity.placedCounts }
}
