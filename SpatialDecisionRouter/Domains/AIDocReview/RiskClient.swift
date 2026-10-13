import Foundation

/// Client for the localhost Bayesian risk sidecar (risk_engine/). Short timeout; nil on any failure → Swift fallback.
struct BNTruth: Decodable {
    struct IfWrong: Decodable { let dx: String; let current: Double; let low: Double; let high: Double; let severity: Int
        let worst_miss: String; let plan_change: String; let label_current: String; let label_high: String }
    let truth: String; let posterior: Double; let label: String; let state: String; let why: String
    let report: String?; let answer: String?; let sensitive: Bool; let if_wrong: IfWrong?
}
struct BNVOI: Decodable { let truth: String; let question: String; let voi: Double; let p_answer_pos: Double; let p_ruleout: Double }
struct BNEscalation: Decodable { let recommend: Bool; let p_critical: Double; let threshold: Double; let best_question_ruleout: Double; let reason: String }
struct BNResult: Decodable {
    let complaint: String; let engine: String; let param_source: String
    let truths: [BNTruth]; let voi: [BNVOI]; let escalation: BNEscalation
    let p_critical: Double; let p_critical_label: String; let best_action: String
}

enum RiskClient {
    static var baseURL = URL(string: ProcessInfo.processInfo.environment["RISK_URL"] ?? "http://127.0.0.1:8765")!
    static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 0.8; c.timeoutIntervalForResource = 1.5
        return URLSession(configuration: c)
    }()
    /// one-shot health ping (demo start): sidecar reachable?
    static func checkHealth(_ done: @escaping @MainActor (Bool) -> Void) {
        Task { @MainActor in
            if ProcessInfo.processInfo.arguments.contains("-noSidecar") { done(false); return }
            let ok = (try? await session.data(from: baseURL.appendingPathComponent("health"))).map { ($0.1 as? HTTPURLResponse)?.statusCode == 200 } ?? false
            done(ok)
        }
    }
    static func assess(_ body: [String: Any]) async -> BNResult? {
        guard !ProcessInfo.processInfo.arguments.contains("-noSidecar"),
              let data = try? JSONSerialization.data(withJSONObject: body) else { return nil }
        var rq = URLRequest(url: baseURL.appendingPathComponent("assess"))
        rq.httpMethod = "POST"; rq.httpBody = data; rq.setValue("application/json", forHTTPHeaderField: "Content-Type")
        guard let (d, resp) = try? await session.data(for: rq), (resp as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONDecoder().decode(BNResult.self, from: d)
    }
}

/// Swift field ↔ BN truth mapping.
enum BNMap {
    static let complaint: [DRComplaint: String] = [.abdPain: "abdominal_pain", .chestPain: "chest_pain", .headInjury: "head_injury",
                                                   .cough: "infection_abx", .uti: "infection_abx",
                                                   .uriAbx: "uri_abx", .refill: "med_refill", .glp1: "glp1_weight", .hrt: "hrt_menopause",
                                                   .testosterone: "testosterone", .erectile: "erectile_dysfunction"]
    static let truths: [String: [String]] = ["abdominal_pain": ["pregnant", "substance", "minimized", "unsafe_home"],
                                             "chest_pain": ["substance", "minimized", "qt_med"], "head_injury": ["anticoag", "substance", "unsafe_home"],
                                             "infection_abx": ["qt_med", "pregnant", "minimized"],
                                             "uri_abx": ["qt_med", "pregnant", "pcn_allergy", "airway_red_flag"],
                                             "med_refill": OPSpec.fields[.refill]!.map(\.key),
                                             "glp1_weight": ["mtc_men2", "pancreatitis_hx", "gallbladder", "pregnant", "eating_disorder", "hypoglycemic_meds", "inflated_bmi"],
                                             "hrt_menopause": OPSpec.fields[.hrt]!.map(\.key), "testosterone": OPSpec.fields[.testosterone]!.map(\.key),
                                             "erectile_dysfunction": ["nitrate_use", "exertional_cp", "alpha_blocker", "recreational_drugs", "qt_med"]]
    static let field: [String: String] = ["pregnant": "pregnancy", "qt_med": "meds", "anticoag": "meds", "substance": "substance",
                                          "unsafe_home": "safety", "minimized": "symptoms", "pcn_allergy": "allergies"]
        .merging(Dictionary(uniqueKeysWithValues: OPSpec.fields.values.joined().map { ($0.key, $0.key) })) { a, _ in a }
    static let hedgeTruths: Set<String> = ["pregnant", "substance", "unsafe_home", "minimized"]

    @MainActor static func request(_ e: DREncounter) -> [String: Any]? {
        guard let c = complaint[e.cc], let ts = truths[c] else { return nil }
        var reports: [String: Any] = [:], signals: [String: Any] = [:], answers: [String: Any] = [:], known: [String: Any] = [:]
        for t in ts {
            let fname = field[t]!
            guard let fd = e.fields[fname] else {
                if t == "pregnant" { known[t] = "no" }       // not eligible (sex/age) → known not pregnant
                else if t == "unsafe_home" { reports[t] = NSNull() } else { reports[t] = NSNull() }
                continue
            }
            // report
            switch (t, fd.stated) {
            case (_, "—"): reports[t] = NSNull()
            case ("qt_med", let s): reports[t] = s == "methadone" ? "pos" : "neg"
            case ("anticoag", let s): reports[t] = s == "apixaban" ? "pos" : "neg"
            case ("substance", let s): reports[t] = s == "cocaine" ? "cocaine" : s == "heavy alcohol" ? "alcohol" : "neg"
            case (_, let s): reports[t] = (s == fd.benign || s == "unsure") ? "neg" : "yes"     // disclosed → truth fixed
            }
            if let sig = OPSpec.field(t)?.signal { signals[t] = [sig: fd.clue != nil] }   // system checked record/transcript
            if fd.confirmed && !e.asks.contains(fname) && fd.truth == fd.benign { known[t] = "no" }   // verified in record
            else if let clue = fd.clue {
                if hedgeTruths.contains(t) && (clue.hasPrefix("transcript") || clue.contains("answered")) { signals[t] = ["hedge": true] }
                if (t == "qt_med" || t == "anticoag") { signals[t] = ["record": true] }
            }
            if e.asks.contains(fname) {
                let relevant = (t == "qt_med" && fd.truth == "methadone") || (t == "anticoag" && fd.truth == "apixaban") || !["qt_med", "anticoag"].contains(t)
                answers[t] = fd.confirmed && fd.truth != fd.benign && relevant ? "pos" : "neg"
            }
        }
        let p = e.aiPlan
        var flags: [String: Any] = [:]
        let flagNames: [String: [String]] = ["abdominal_pain": ["plan_teratogen"], "chest_pain": ["plan_qt_drug"], "head_injury": [],
                                             "infection_abx": ["plan_qt_drug", "plan_teratogen"], "uri_abx": ["plan_qt_drug", "plan_teratogen"]]
        for f in flagNames[c] ?? [] {
            flags[f] = f == "plan_qt_drug" ? ["azithro", "levo", "cipro", "ondansetron"].contains { p.contains($0) }
                                           : ["cipro", "ibuprofen", "doxy"].contains { p.contains($0) }
        }
        return ["complaint": c, "encounter_id": e.id,
                "context": ["companion": e.companion != nil, "interpreter": e.interpreter, "adolescent": e.age < 18,
                            "low_literacy": e.literacyLow, "elderly_alone": e.age >= 75 && e.companion == nil],
                "plan_flags": flags, "reports": reports, "signals": signals, "answers": answers, "known": known]
    }
}
