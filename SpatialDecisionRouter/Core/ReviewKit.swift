import Foundation

// MARK: - Review-queue + detail/glossary config (generic; declared in <domain>.domain.json)

/// Queue ordering + auto-pass policy.
struct ReviewSpec: Codable {
    /// auto-pass when confidence ≥ this AND link costWeight ≤ autoPassMaxCost AND no high-severity reason chip
    var autoPassConfidence: Double = 0.9
    var autoPassMaxCost: Double = 0.4
    /// fraction of auto-passes sampled into the spot-check queue
    var spotCheckRate: Double = 0.3
    /// priority = (1-conf)·(1+cost) + waitWeight·wait(domain minutes) + domain urgency
    var waitWeight: Double = 0.02
    var upNextCount: Int = 4
    /// link whose proposal is replaced by `escalateAnswer` when a hard trigger fires (nil = none)
    var escalationLink: String?
    var escalateAnswer: String = "escalate"
    init() {}
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self); let t = ReviewSpec()
        autoPassConfidence = try c.decodeIfPresent(Double.self, forKey: .autoPassConfidence) ?? t.autoPassConfidence
        autoPassMaxCost = try c.decodeIfPresent(Double.self, forKey: .autoPassMaxCost) ?? t.autoPassMaxCost
        spotCheckRate = try c.decodeIfPresent(Double.self, forKey: .spotCheckRate) ?? t.spotCheckRate
        waitWeight = try c.decodeIfPresent(Double.self, forKey: .waitWeight) ?? t.waitWeight
        upNextCount = try c.decodeIfPresent(Int.self, forKey: .upNextCount) ?? t.upNextCount
        escalationLink = try c.decodeIfPresent(String.self, forKey: .escalationLink)
        escalateAnswer = try c.decodeIfPresent(String.self, forKey: .escalateAnswer) ?? t.escalateAnswer
    }
}

/// Why an item is in the human queue. `key` looks up the glossary tooltip.
struct ReasonChip: Hashable, Codable {
    enum Severity: Int, Codable { case info = 0, warn = 1, high = 2 }
    let text: String
    var key: String = ""
    var severity: Severity = .warn
}

/// One expandable section in the detail panel.
struct DetailSection: Identifiable { var id: String { title }; let title: String; let rows: [(String, String)] }

/// Optional review hooks are DomainModule requirements with these defaults (a config-only domain still works).
extension DomainModule {
    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip] { [] }
    func urgency(item: DomainItem, link: LinkSpec, proposal: String) -> Double { 0 }
    func downstreamPreview(item: DomainItem, link: LinkSpec, answer: String) -> String? { nil }
    func ledgerFields(item: DomainItem) -> [String: String] { item.fields }
    func detail(item: DomainItem, section: String) -> [(String, String)]? { nil }
}

/// Engine-side helpers that combine config templates with domain hooks.
@MainActor enum Review {
    static func preview(_ d: DomainModule, _ item: DomainItem, _ l: LinkSpec, _ answer: String, trial: Bool) -> String {
        let destName = d.config.agents.first { $0.id == l.dest }?.name ?? l.dest
        if trial { return "\(destName): receives agent proposal (trial category logged only)" }
        if let s = d.downstreamPreview(item: item, link: l, answer: answer) { return s }
        let t = l.previews[answer] ?? l.previews["*"] ?? "{dest}: receives “{answer}”"
        return t.replacingOccurrences(of: "{dest}", with: destName).replacingOccurrences(of: "{answer}", with: answer)
    }
}
