import Foundation

/// Localhost client for homehealth Layer 1 (homehealth/sdr_bridge, default 127.0.0.1:8767).
/// Nil on any failure, including `-noHomeHealthBridge`. The domain then shows the bundled snapshot.
struct HHTicket: Decodable, Equatable {
    var type: String
    var detail: String?
    var rule: String?
}

struct HHLayer1: Decodable, Equatable {
    var route: String?
    var owner: String?
    var tier: String?
    var rule: String?
    var reason: String?
    var plain_reason: String?
    var route_definition: String?
    var escalation_target: String?
    var ticket: HHTicket?
    var ticket_note: String?
}

struct HHVignette: Decodable, Identifiable {
    var case_id: String
    var source: String
    var library_label: String?
    var age_band: String
    var sex: String
    var living: String
    var pmh: String
    var meds: String
    var devices: String
    var goals: String
    var function: String
    var baseline: String
    var baseline_status: String
    var discharge: String
    var trend: String
    var note: String
    var artifact_flags: String
    var layer1: HHLayer1
    var id: String { case_id }
}

struct HHPack: Decodable {
    var engine_version: String
    var params_version: String
    var note: String?
    var cases: [HHVignette]
}

enum HomeHealthClient {
    struct LiveCase: Decodable { var case_id: String; var layer1: HHLayer1 }
    struct Live: Decodable {
        var ok: Bool
        var engine_version: String
        var params_version: String
        var cases: [LiveCase]
    }

    static var baseURL: URL = {
        if let s = ProcessInfo.processInfo.environment["HOMEHEALTH_URL"], let u = URL(string: s) { return u }
        return URL(string: "http://127.0.0.1:8767")!
    }()

    static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 1.2
        c.timeoutIntervalForResource = 2.0
        return URLSession(configuration: c)
    }()

    /// Recomputed Layer 1 for the bundled pack. Nil when the bridge is down or refused.
    static func fetchCases() async -> Live? {
        if ProcessInfo.processInfo.arguments.contains("-noHomeHealthBridge") { return nil }
        guard let (data, resp) = try? await session.data(from: baseURL.appendingPathComponent("cases")),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let live = try? JSONDecoder().decode(Live.self, from: data),
              live.ok, !live.cases.isEmpty else { return nil }
        return live
    }
}

/// Display-only pattern pack. Not a Layer 1 input and not part of the vignette snapshot.
struct HHPatternPack: Decodable {
    var cases: [HHPatternEntry]
}

struct HHPatternEntry: Decodable {
    var vignette: HHVignette
    var pattern: HHPattern
    var mind: HHMindNote?
}

/// Optional fixture override for the L0 intelligence read. Absent keys are derived.
struct HHMindNote: Decodable, Equatable {
    var differential: [String]?
    var confidence: String?
    var act_under_uncertainty: Bool?
    var act_banner: String?
    var prior_decision: String?
    var new_evidence: String?
    var falsifies_prior: Bool?
    var wait_for: String?
    /// Explicit window in minutes. Absent means the face derives one from the wait text or a situation default.
    var wait_minutes: Int?
    var flip_route: String?
    var flip_if: String?
    var agent_refused: Bool?
    var refusal_reason: String?
    var goals_line: String?
    var goals_kind: String?
    var blocks_escalation: Bool?
}

struct HHPattern: Decodable, Equatable {
    var case_id: String
    var fixture: Bool
    var trigger: String
    var headline: String
    var summary: String
    var rule_note: String
    var horizon: String
    var alerts: [HHPatternEvent]
    var vitals: [HHPatternVital]
}

struct HHPatternEvent: Decodable, Equatable, Identifiable {
    var when: String
    var what: String
    var action: String
    var id: String { when + what }
}

struct HHPatternVital: Decodable, Equatable, Identifiable {
    var name: String
    var band: String
    var low: Int
    var high: Int
    var points: [Int]
    var outside_note: String
    var id: String { name }
}
