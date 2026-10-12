import Foundation
import simd

enum DecisionType: String, Codable, CaseIterable { case binary, category }

struct Proposal: Codable, Identifiable, Hashable {
    let id: String
    let modelID: String
    let type: DecisionType
    let category: String          // e.g. toxicity, self-harm, spam, copyright
    let evidence: String
    let confidence: Float
    let recommended: String
    let options: [String]
    let groundTruth: String?
    /// Priority 0...1: uncertain (confidence near 0.5) or severe items rank higher.
    var priority: Float {
        let uncertainty = 1 - abs(confidence - 0.5) * 2
        let severe: Float = ["self-harm", "violence"].contains(category) ? 0.25 : 0
        return min(1, uncertainty * 0.75 + severe)
    }
}

enum HumanAction: String, Codable { case accept, reject, recategorize, needsMoreInfo }

struct SpatialSnapshot: Codable, Hashable { var x: Float; var y: Float; var z: Float; var priority: Float; var distance: Float }

struct DecisionLog: Codable, Identifiable {
    var id = UUID()
    // what was shown
    let proposal: Proposal
    let position: SpatialSnapshot
    // human action
    let action: HumanAction
    let chosenLabel: String?
    let shownAt: Date
    let decidedAt: Date
    let decisionLatency: TimeInterval
    let inspected: Bool
    let inspectDuration: TimeInterval?
    // local context
    let neighborProposalIDs: [String]
    let unresolvedCount: Int
    let recentOverrideCount: Int
    // optional delayed outcome
    var outcome: String?
    var outcomeJoinedAt: Date?
    var agreesWithOutcome: Bool?
    var stream: String?
    let agreesWithGroundTruth: Bool?
}
