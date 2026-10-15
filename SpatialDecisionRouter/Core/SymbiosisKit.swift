import Foundation

// MARK: - Symbiosis layer 1: per-context division of labour (docs/SYMBIOSIS_PLAN.md §3)
// Data model adapted (rewritten, not copied) from the Symbiont concept's areas + policy vector; see docs/SYMBIOSIS.md.
// M1: dials are SEEDED placeholders (not learned). Earned movement is M2. Clinical caps are enforced already.

struct DialCaps: Codable, Hashable {
    var autonomyMax: Double = 100     // clinical: autonomy horizon capped
    var deferenceMin: Double = 0      // clinical: deference floor
    static let clinical = DialCaps(autonomyMax: 40, deferenceMin: 80)
    static let none = DialCaps()
}

struct SymbiosisContext: Codable, Hashable, Identifiable {
    let id: String                    // e.g. "ed_triage", "personal_finance"
    let title: String
    let clinical: Bool
    var dials: DialSnapshot
    var caps: DialCaps
    var generation: Int = 0
    let humanFocus: [String]          // what the human keeps (functional knowledge)
    let aiFocus: [String]             // what the AI carries

    /// Enforce caps (clinical: autonomy ≤ cap, deference ≥ floor; all 0–100). Returns the clamped context.
    func enforced() -> SymbiosisContext {
        var c = self
        func cl(_ x: Double) -> Double { min(100, max(0, x)) }
        c.dials.deference = max(cl(c.dials.deference), caps.deferenceMin)
        c.dials.autonomy_horizon = min(cl(c.dials.autonomy_horizon), caps.autonomyMax)
        c.dials.detail_absorption = cl(c.dials.detail_absorption)
        c.dials.challenge = cl(c.dials.challenge)
        return c
    }
}

enum SymbiosisSeeds {
    static let seedSource = "seed (placeholder starting value — moves only on outcome-graded evidence)"
    /// Clinical seed profile. Starting values follow the Symbiont concept's clinical area (deference 90, detail 92,
    /// challenge 78, autonomy 55) — autonomy is then clamped to the clinical cap (40).
    static let clinical = SymbiosisContext(
        id: "ed_triage", title: "ED triage", clinical: true,
        dials: DialSnapshot(deference: 90, detail_absorption: 92, challenge: 78, autonomy_horizon: 55, source: seedSource),
        caps: .clinical,
        humanFocus: ["Gestalt: does this patient look sick?", "Which red flag changes the plan", "When the protocol does not fit"],
        aiFocus: ["Scoring criteria and thresholds", "Drug and dose details", "Rare differentials and edge cases"]).enforced()
    static let teleDoc = SymbiosisContext(
        id: "ai_tele_doc", title: "AI tele-doc", clinical: true, dials: clinical.dials, caps: .clinical,
        humanFocus: clinical.humanFocus, aiFocus: clinical.aiFocus).enforced()
    static let weriam = SymbiosisContext(
        id: "weriam_principal", title: "WERIAM Principal", clinical: false,
        dials: DialSnapshot(deference: 85, detail_absorption: 80, challenge: 70, autonomy_horizon: 30, source: seedSource),
        caps: DialCaps(autonomyMax: 50, deferenceMin: 70),
        humanFocus: ["Is this reversible?", "Does it harm someone who did not consent?"], aiFocus: ["Evidence trail", "Replay of past episodes"]).enforced()
    static let finance = SymbiosisContext(
        id: "personal_finance", title: "Personal finance", clinical: false,
        dials: DialSnapshot(deference: 70, detail_absorption: 85, challenge: 65, autonomy_horizon: 45, source: seedSource),
        caps: .none,
        humanFocus: ["What the money is for", "How much risk you can sleep with", "Family obligations no spreadsheet sees"],
        aiFocus: ["Tax rules and limits", "Fees, rates and fine print", "Scenario arithmetic"]).enforced()

    static func profile(for configId: String) -> SymbiosisContext? {
        switch configId {
        case "ed_triage": clinical
        case "ai_doc_review": teleDoc
        case "weriam_principal": weriam
        default: nil
        }
    }
}

/// Default unified-record context for every domain; Symbiosis overrides per card area.
extension DomainModule {
    func decisionContext(item: DomainItem) -> DecisionContext {
        let p = SymbiosisSeeds.profile(for: config.id)
        return DecisionContext(domain: UnifiedDomainId.of(config.id), contextId: "\(config.id)/\(config.defaultSite)",
                               dials: p?.dials, generation: p?.generation ?? 0,
                               reliability: RecordReliability(score: nil, n: 0, label: "not computed in the unified record for this domain"),
                               outcomeSource: config.id == "weriam_principal" ? "weriam_teacher (WERIAM observed outcome)" : "simulator_ground_truth (synthetic)")
    }
}

// MARK: - Optional local-LLM hook (stub). M1 ships seeded cards only; nothing calls a model.
protocol SymbiosisCardGenerator { func synthesize(area: SymbiosisContext, prompt: String) async -> SymbiosisCard? }
struct OfflineStubGenerator: SymbiosisCardGenerator {
    /// Stub: a real implementation would call a local model (e.g. a localhost endpoint), delimit/escape the user text,
    /// and return a card that is then reviewed like any other. It may only PROPOSE (plan non-negotiable 8).
    func synthesize(area: SymbiosisContext, prompt: String) async -> SymbiosisCard? { nil }
}

/// Three-column card content (Human holds / Bridge / AI holds). Schema adapted from the Symbiont synthesis concept.
struct SymbiosisCard: Codable, Hashable {
    let id: String
    let area: String
    let title: String
    let situation: String
    // human (warm orange) — short
    let humanJudgment: String
    let humanQuestion: String
    // bridge
    let bridgeArchitecture: String
    let bridgeCheckpoint: String
    let bridgeWorkflow: String
    // AI (blue, collapsed)
    let aiDistilled: String
    let aiDetail: [String]
    let aiEdgeCases: [String]
    // decision
    let planText: String              // what "Accept plan" means here
    let alternativeText: String       // what "Alternative plan" means here
    let proposal: String              // agent's pick (one of SymbiosisDomain.options)
    let proposalConfidence: Double    // seeded, labeled as such
    let scriptedOutcome: String?      // seeded/imported outcome (synthetic) — the graded "truth"; nil = unknown
    let hardTrigger: String?
    let demoSplit: SplitRating
    var severity: String? = nil       // "critical": a wrong agent pick here is a critical miss (M2 demotion)
    var origin = "seed"               // seed | imported
}
