import Foundation

enum CategoryTier: String, Codable { case main, trial, dormant }

struct CategoryEntry: Codable, Hashable {
    var name: String
    var tier: CategoryTier
    var isBase: Bool
    var createdAt = Date()
    var uses = 0
    var reviewerAgree = 0, reviewerTotal = 0
    var outcomeSupport = 0, outcomeTotal = 0
    var lastUsedTick = 0
    var consistency: Double { reviewerTotal == 0 ? 0 : Double(reviewerAgree) / Double(reviewerTotal) }
    var support: Double { outcomeTotal == 0 ? 0 : Double(outcomeSupport) / Double(outcomeTotal) }
    /// combined score shown in the Categories panel
    var score: Double { min(1, Double(uses) / 5) * 0.4 + consistency * 0.35 + support * 0.25 }
}

struct RegistryEvent: Codable {
    let version: Int
    let time: Date
    let siteId: String
    let linkId: String
    let op: String          // seed | add | promote | relegate | drop | merge | split | reactivate
    let category: String
    let detail: String
}

struct RegistryThresholds: Codable {
    var promoteUses = 3, promoteConsistency = 0.6, promoteSupport = 2
    var relegateIdleDecisions = 60
    var dropAfterUses = 6, dropBelowConsistency = 0.34
}

/// Per-site category registry layered on a domain's base option sets.
/// New categories start in TRIAL; they never fire alerts or change routing until promoted to MAIN.
struct CategoryRegistry: Codable {
    let siteId: String
    var version = 1
    var entries: [String: [CategoryEntry]] = [:]      // linkId -> entries
    var history: [RegistryEvent] = []
    var tickCount = 0
    var thresholds = RegistryThresholds()

    init(siteId: String, links: [LinkSpec]) {
        self.siteId = siteId
        for l in links where l.answerType == .category {
            entries[l.id] = l.options.map { CategoryEntry(name: $0, tier: .main, isBase: true) }
        }
        log("*", "seed", "*", "base sets from domain config")
    }

    /// Layer a persisted site registry over the current base set (keeps added categories, adds new base options).
    mutating func merge(persisted p: CategoryRegistry) {
        version = p.version; history = p.history; tickCount = p.tickCount
        for (link, es) in p.entries {
            for e in es where !(entries[link]?.contains { $0.name == e.name } ?? false) { entries[link, default: []].append(e) }
            for e in es { if let i = entries[link]?.firstIndex(where: { $0.name == e.name }) { entries[link]![i] = e } }
        }
    }

    func list(_ link: LinkSpec, _ t: CategoryTier) -> [CategoryEntry] { (entries[link.id] ?? []).filter { $0.tier == t } }
    func mainOptions(_ link: LinkSpec) -> [String] { link.answerType == .binary ? link.options : list(link, .main).map(\.name) }
    func trialOptions(_ link: LinkSpec) -> [String] { list(link, .trial).map(\.name) }
    func isTrial(_ name: String, link: LinkSpec) -> Bool { list(link, .trial).contains { $0.name == name } }
    func exists(_ name: String, link: LinkSpec) -> Bool { (entries[link.id] ?? []).contains { $0.name.caseInsensitiveCompare(name) == .orderedSame && $0.tier != .dormant } }

    private mutating func log(_ link: String, _ op: String, _ cat: String, _ detail: String) {
        history.append(RegistryEvent(version: version, time: Date(), siteId: siteId, linkId: link, op: op, category: cat, detail: detail))
    }
    private mutating func bump(_ link: String, _ op: String, _ cat: String, _ detail: String) { version += 1; log(link, op, cat, detail) }
    private func idx(_ link: String, _ name: String) -> Int? { entries[link]?.firstIndex { $0.name.caseInsensitiveCompare(name) == .orderedSame } }

    /// HITM "New…": adds a TRIAL category (or reactivates a dormant one as trial).
    @discardableResult mutating func add(_ raw: String, link: LinkSpec) -> String {
        let name = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return name }
        if let i = idx(link.id, name) {
            if entries[link.id]![i].tier == .dormant { entries[link.id]![i].tier = .trial; bump(link.id, "reactivate", name, "dormant -> trial") }
            return entries[link.id]![i].name
        }
        entries[link.id, default: []].append(CategoryEntry(name: name, tier: .trial, isBase: false, lastUsedTick: tickCount))
        bump(link.id, "add", name, "new trial category")
        return name
    }

    mutating func recordUse(_ name: String, link: LinkSpec, reviewerAgrees: Bool?) {
        guard let i = idx(link.id, name) else { return }
        entries[link.id]![i].uses += 1; entries[link.id]![i].lastUsedTick = tickCount
        if let r = reviewerAgrees { entries[link.id]![i].reviewerTotal += 1; if r { entries[link.id]![i].reviewerAgree += 1 } }
    }
    mutating func recordOutcome(_ name: String, linkId: String, ok: Bool) {
        guard let i = idx(linkId, name) else { return }
        entries[linkId]![i].outcomeTotal += 1; if ok { entries[linkId]![i].outcomeSupport += 1 }
    }

    /// Promotion (trial -> main), drop (trial -> dormant), relegation (non-base main -> dormant). Returns new events.
    mutating func evaluate() -> [RegistryEvent] {
        tickCount += 1
        let before = history.count
        for link in entries.keys.sorted() {
            for i in entries[link]!.indices {
                let e = entries[link]![i], t = thresholds
                if e.tier == .trial, e.uses >= t.promoteUses, e.consistency >= t.promoteConsistency, e.outcomeSupport >= t.promoteSupport {
                    entries[link]![i].tier = .main
                    bump(link, "promote", e.name, String(format: "uses %d, consistency %.2f, outcome support %d", e.uses, e.consistency, e.outcomeSupport))
                } else if e.tier == .trial, e.uses >= t.dropAfterUses, e.consistency < t.dropBelowConsistency {
                    entries[link]![i].tier = .dormant
                    bump(link, "drop", e.name, String(format: "low consistency %.2f", e.consistency))
                } else if e.tier == .main, !e.isBase, tickCount - e.lastUsedTick > t.relegateIdleDecisions {
                    entries[link]![i].tier = .dormant
                    bump(link, "relegate", e.name, "idle \(tickCount - e.lastUsedTick) decisions")
                }
            }
        }
        return Array(history[before...])
    }

    mutating func merge(_ from: String, into: String, linkId: String) {
        guard let a = idx(linkId, from), let b = idx(linkId, into), a != b else { return }
        let e = entries[linkId]![a]
        entries[linkId]![b].uses += e.uses; entries[linkId]![b].reviewerAgree += e.reviewerAgree
        entries[linkId]![b].reviewerTotal += e.reviewerTotal; entries[linkId]![b].outcomeSupport += e.outcomeSupport
        entries[linkId]![b].outcomeTotal += e.outcomeTotal
        entries[linkId]![a].tier = .dormant
        bump(linkId, "merge", from, "merged into \(into)")
    }
    mutating func split(_ name: String, into parts: [String], linkId: String) {
        guard let a = idx(linkId, name) else { return }
        entries[linkId]![a].tier = .dormant
        for p in parts where idx(linkId, p) == nil {
            entries[linkId]!.append(CategoryEntry(name: p, tier: .trial, isBase: false, lastUsedTick: tickCount))
        }
        bump(linkId, "split", name, "split into \(parts.joined(separator: ", "))")
    }
}
