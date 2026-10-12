import Foundation

/// Per-site category registry layered on a domain's base option sets. (Phase A: base sets only.)
struct CategoryRegistry {
    let siteId: String
    var version = 1
    private var base: [String: [String]]
    init(siteId: String, links: [LinkSpec]) {
        self.siteId = siteId
        base = Dictionary(uniqueKeysWithValues: links.map { ($0.id, $0.options) })
    }
    func mainOptions(_ link: LinkSpec) -> [String] { base[link.id] ?? link.options }
    func trialOptions(_ link: LinkSpec) -> [String] { [] }
    func isTrial(_ name: String, link: LinkSpec) -> Bool { false }
}
