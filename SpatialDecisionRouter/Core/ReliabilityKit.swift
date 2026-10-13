import Foundation

// MARK: - Generic reliability / if-wrong / value-of-information layer (domain supplies content)

enum ReliabilityState: String, Codable, CaseIterable, Hashable {
    case reliable = "Reliable"
    case notSaid = "Not said"
    case saidWrong = "Said wrong"
    case saidDifferently = "Said differently on purpose"
    var short: String { switch self { case .reliable: "R"; case .notSaid: "N"; case .saidWrong: "W"; case .saidDifferently: "D" } }
}

/// If the reported value is wrong: the dangerous alternative and what it changes.
struct RiskRange: Codable, Hashable {
    let alternative: String
    let pAlt: Double              // estimated probability the alternative is true
    let riskLo: Double            // serious-miss risk delta range (0–1)
    let riskHi: Double
    let severity: Int             // 1–5
    let worstMiss: String
    let planChange: String
    let ddxShift: String          // how the differential moves
}

/// One reported field with its context-dependent reliability estimate.
struct FieldReliability: Codable, Hashable, Identifiable {
    var id: String { field }
    let field: String
    let stated: String
    var state: ReliabilityState   // system estimate (or physician re-rating when set)
    var score: Double             // 0–1 confidence the stated value is true
    var why: [String]             // context drivers (age, companion, interpreter, topic, inconsistency…)
    var key: Bool                 // key field for this complaint
    var ifWrong: RiskRange?
    var notAsked: [String] = []   // expected questions not asked (Not said)
    var physicianState: ReliabilityState?
    var confirmedByAsk = false
    // hidden truth: logged for training, never rendered
    var trueValue: String?
    var trueState: ReliabilityState?
}

/// A candidate next question, ranked by expected plan change × miss severity.
struct VOIQuestion: Codable, Hashable, Identifiable {
    let id: String
    let field: String
    let text: String
    let voi: Double
    let rationale: String
}

struct ReRating: Codable, Hashable { let field: String; let from: String; let to: String; let at: Date }
struct AskEvent: Codable, Hashable { let questionId: String; let field: String; let question: String; let voi: Double; let answer: String; let at: Date }

extension DomainModule {
    func hardTrigger(item: DomainItem) -> String? { nil }
    func reliability(item: DomainItem) -> [FieldReliability] { [] }
    func askNext(item: DomainItem) -> [VOIQuestion] { [] }
    func ask(item: DomainItem, questionId: String) -> String? { nil }
    func rerate(item: DomainItem, field: String, state: ReliabilityState) {}
    func hiddenTruth(item: DomainItem) -> [String: String] { [:] }
    func refreshed(item: DomainItem) -> DomainItem? { nil }
    func transcript(item: DomainItem) -> [String] { [] }
    func riskBadge(item: DomainItem) -> String? { nil }
    func takeDirty() -> [String] { [] }
}
