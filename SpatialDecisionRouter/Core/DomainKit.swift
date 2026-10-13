import Foundation

// MARK: - Domain-agnostic configuration (data-driven; loaded from <domain>.domain.json)

enum AnswerType: String, Codable { case binary, category }

struct AgentSpec: Codable, Hashable {
    let id: String
    let name: String
    var role: String?
    /// 0 = source (decision) agents, 1 = destination / consumer nodes
    var tier: Int = 0
}

/// One decision a narrow agent makes about an item, delivered to a destination node.
struct LinkSpec: Codable, Hashable {
    let id: String
    let source: String
    let dest: String
    let question: String
    let answerType: AnswerType
    let options: [String]            // base category set (registry seed)
    var dependsOn: [String] = []     // link ids whose *routed* answers this decision needs
    var firesAlert: Bool = false     // positive answers fire alerts (trial categories never do)
    var alertNegative: [String] = [] // answers that do NOT count as an alert
    var costWeight: Double = 0       // error cost; drives priority surfacing
    var shortLabel: String?
    /// downstream preview templates: answer → text ("*" = default); {dest} {answer} substituted
    var previews: [String: String] = [:]
    /// when an alert fires on this link, the handoff travels here instead of `dest`
    var alertDest: String?
}

struct Terminology: Codable {
    var itemNoun = "item"
    var itemNounPlural = "items"
    var boardTitle = "Throughput"
    var syntheticBanner = "SYNTHETIC data"
    var completedLabel = "Completed"
    var historyLabel = "Hx"
    var capacityLabel = "Capacity"
}

struct ThemeSpec: Codable {
    var skyTop: [Double] = [0.80, 0.85, 0.90]
    var skyHorizon: [Double] = [0.55, 0.63, 0.71]
    var skyBottom: [Double] = [0.30, 0.36, 0.43]
    var floor: [Double] = [0.20, 0.24, 0.29]
    var grid: [Double] = [0.42, 0.52, 0.60]
    var panel: [Double] = [0.16, 0.20, 0.25]
    var trim: [Double] = [0.35, 0.70, 0.80]
}

struct DomainConfig: Codable {
    let id: String
    let title: String
    var synthetic: Bool = true
    var defaultSite: String = "site-A"
    var terminology = Terminology()
    var theme = ThemeSpec()
    let agents: [AgentSpec]
    let links: [LinkSpec]
    var rulesTable: [String] = []
    /// free-form numeric parameters for the domain's capacity/queue model
    var capacity: [String: Double] = [:]
    /// names the test driver uses to exercise "New…" categories, keyed by link id
    var testNewCategories: [String: [String]] = [:]
    var review = ReviewSpec()
    /// term → explanation, shown as hover tooltips on every field / chip
    var glossary: [String: String] = [:]
    /// ordered detail-panel section titles (content from ReviewHooks.detail; "Capacity snapshot" is built in)
    var detailSections: [String] = []
}

// MARK: - Runtime item

struct DomainItem: Identifiable {
    let id: String
    /// structured fields (generic context snapshot that is logged verbatim)
    let fields: [String: String]
    let displayLine: String          // full card line
    let shortLine: String            // board row line
    let historyLine: String          // "none" if empty
    let arrivalTime: Double          // domain clock (minutes)
}

struct Proposal { let answer: String; let confidence: Double }

struct MetricValue: Identifiable { var id: String { label }; let label: String; let value: String }

/// Engine-side counters handed to the domain for board rendering.
struct EngineStats {
    var completed = 0, decisions = 0, corrections = 0, errorsPrevented = 0, misses = 0, alertsFired = 0
    var medianLatency: Double = 0
    var agentErrorRate: Double = 0
}

// MARK: - Domain plug-in contract

@MainActor protocol DomainModule: AnyObject {
    var config: DomainConfig { get }
    /// domain clock in minutes (simulation time); advanced by `advance`
    var now: Double { get }
    var minutesPerSecond: Double { get }
    func reset(seed: UInt64)
    /// advance the domain's own world (arrivals, capacity/queue DES)
    func advance(minutes: Double)
    /// next item ready for the human router, if any
    func nextItem() -> DomainItem?
    /// narrow (possibly noisy/biased) agent proposal; `routed` holds effective answers of dependencies
    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal
    /// rule-based ground truth (may use capacity state at emission time); nil = unknown
    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String?
    /// item fully routed: apply effects in the domain world using *effective* (guard-railed) answers
    func complete(item: DomainItem, effective: [String: String])
    /// an alert-type answer was confirmed for an item
    func alertFired(item: DomainItem, link: LinkSpec)
    func capacitySnapshot() -> [String: String]
    func capacityLine() -> String
    func boardMetrics(_ s: EngineStats) -> [MetricValue]
    /// breakdown chips (e.g. counts by destination area)
    func breakdown() -> [(String, Int)]
    // review hooks (defaults in ReviewKit.swift)
    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip]
    func urgency(item: DomainItem, link: LinkSpec, proposal: String) -> Double
    func downstreamPreview(item: DomainItem, link: LinkSpec, answer: String) -> String?
    func detail(item: DomainItem, section: String) -> [(String, String)]?
    // reliability layer (defaults in ReliabilityKit.swift)
    /// hard escalation trigger: bypasses reliability analysis, fires escalation immediately
    func hardTrigger(item: DomainItem) -> String?
    func reliability(item: DomainItem) -> [FieldReliability]
    func askNext(item: DomainItem) -> [VOIQuestion]
    /// send a question; returns the simulated answer and updates domain state
    func ask(item: DomainItem, questionId: String) -> String?
    func rerate(item: DomainItem, field: String, state: ReliabilityState)
    func hiddenTruth(item: DomainItem) -> [String: String]
    /// item with updated display after ask/re-rate
    func refreshed(item: DomainItem) -> DomainItem?
    func transcript(item: DomainItem) -> [String]
}

enum DomainLoader {
    static func config(named name: String) throws -> DomainConfig {
        guard let u = Bundle.main.url(forResource: name, withExtension: "json") else {
            throw NSError(domain: "DomainLoader", code: 1, userInfo: [NSLocalizedDescriptionKey: "missing \(name).json"]) }
        return try JSONDecoder().decode(DomainConfig.self, from: Data(contentsOf: u))
    }
}

/// Registry of available domain plug-ins. Adding a domain = add a module + config and register it here.
enum DomainCatalog {
    @MainActor static let all: [() -> DomainModule] = [
        { AIDocReviewDomain() },   // default
        { EDTriageDomain() },
    ]
}

struct SplitMix64 { var s: UInt64
    mutating func next() -> UInt64 { s &+= 0x9E3779B97F4A7C15; var z = s; z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9; z = (z ^ (z >> 27)) &* 0x94D049BB133111EB; return z ^ (z >> 31) }
    mutating func unit() -> Double { Double(next() >> 11) / Double(1 << 53) }
    mutating func range(_ a: Double, _ b: Double) -> Double { a + (b - a) * unit() }
    mutating func chance(_ p: Double) -> Bool { unit() < p }
    mutating func pick<T>(_ xs: [T]) -> T { xs[Int(next() % UInt64(xs.count))] }
}

// MARK: - Lenient decoding (missing keys fall back to defaults so domain JSON stays short)
extension AgentSpec {
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id); name = try c.decode(String.self, forKey: .name)
        role = try c.decodeIfPresent(String.self, forKey: .role); tier = try c.decodeIfPresent(Int.self, forKey: .tier) ?? 0
    }
}
extension LinkSpec {
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id); source = try c.decode(String.self, forKey: .source)
        dest = try c.decode(String.self, forKey: .dest); question = try c.decode(String.self, forKey: .question)
        answerType = try c.decode(AnswerType.self, forKey: .answerType); options = try c.decode([String].self, forKey: .options)
        dependsOn = try c.decodeIfPresent([String].self, forKey: .dependsOn) ?? []
        firesAlert = try c.decodeIfPresent(Bool.self, forKey: .firesAlert) ?? false
        alertNegative = try c.decodeIfPresent([String].self, forKey: .alertNegative) ?? []
        costWeight = try c.decodeIfPresent(Double.self, forKey: .costWeight) ?? 0
        shortLabel = try c.decodeIfPresent(String.self, forKey: .shortLabel)
        previews = try c.decodeIfPresent([String: String].self, forKey: .previews) ?? [:]
        alertDest = try c.decodeIfPresent(String.self, forKey: .alertDest)
    }
}
extension Terminology {
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self); let t = Terminology()
        itemNoun = try c.decodeIfPresent(String.self, forKey: .itemNoun) ?? t.itemNoun
        itemNounPlural = try c.decodeIfPresent(String.self, forKey: .itemNounPlural) ?? t.itemNounPlural
        boardTitle = try c.decodeIfPresent(String.self, forKey: .boardTitle) ?? t.boardTitle
        syntheticBanner = try c.decodeIfPresent(String.self, forKey: .syntheticBanner) ?? t.syntheticBanner
        completedLabel = try c.decodeIfPresent(String.self, forKey: .completedLabel) ?? t.completedLabel
        historyLabel = try c.decodeIfPresent(String.self, forKey: .historyLabel) ?? t.historyLabel
        capacityLabel = try c.decodeIfPresent(String.self, forKey: .capacityLabel) ?? t.capacityLabel
    }
}
extension ThemeSpec {
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self); let t = ThemeSpec()
        skyTop = try c.decodeIfPresent([Double].self, forKey: .skyTop) ?? t.skyTop
        skyHorizon = try c.decodeIfPresent([Double].self, forKey: .skyHorizon) ?? t.skyHorizon
        skyBottom = try c.decodeIfPresent([Double].self, forKey: .skyBottom) ?? t.skyBottom
        floor = try c.decodeIfPresent([Double].self, forKey: .floor) ?? t.floor
        grid = try c.decodeIfPresent([Double].self, forKey: .grid) ?? t.grid
        panel = try c.decodeIfPresent([Double].self, forKey: .panel) ?? t.panel
        trim = try c.decodeIfPresent([Double].self, forKey: .trim) ?? t.trim
    }
}
extension DomainConfig {
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id); title = try c.decode(String.self, forKey: .title)
        synthetic = try c.decodeIfPresent(Bool.self, forKey: .synthetic) ?? true
        defaultSite = try c.decodeIfPresent(String.self, forKey: .defaultSite) ?? "site-A"
        terminology = try c.decodeIfPresent(Terminology.self, forKey: .terminology) ?? Terminology()
        theme = try c.decodeIfPresent(ThemeSpec.self, forKey: .theme) ?? ThemeSpec()
        agents = try c.decode([AgentSpec].self, forKey: .agents); links = try c.decode([LinkSpec].self, forKey: .links)
        rulesTable = try c.decodeIfPresent([String].self, forKey: .rulesTable) ?? []
        capacity = try c.decodeIfPresent([String: Double].self, forKey: .capacity) ?? [:]
        testNewCategories = try c.decodeIfPresent([String: [String]].self, forKey: .testNewCategories) ?? [:]
        review = try c.decodeIfPresent(ReviewSpec.self, forKey: .review) ?? ReviewSpec()
        glossary = try c.decodeIfPresent([String: String].self, forKey: .glossary) ?? [:]
        detailSections = try c.decodeIfPresent([String].self, forKey: .detailSections) ?? []
    }
}
