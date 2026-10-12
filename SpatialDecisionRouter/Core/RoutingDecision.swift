import Foundation

struct Vec3: Codable, Hashable { var x: Float; var y: Float; var z: Float }

/// Generic training record: one human routing decision at the crossroads. No domain terms.
struct RoutingDecision: Codable, Identifiable {
    var id = UUID()
    let domain: String
    let siteId: String
    let registryVersion: Int
    let itemId: String
    let linkId: String
    let sourceAgent: String
    let destAgent: String
    let question: String
    let displayLine: String
    let context: [String: String]       // structured item snapshot
    let history: String
    let capacity: [String: String]      // world/capacity snapshot at emission
    let upstream: [String: String]      // effective answers of dependencies
    let proposedAnswer: String
    let proposedConfidence: Double
    let answerType: AnswerType
    let options: [String]               // main ring at decision time
    let trialOptions: [String]
    let routedAnswer: String            // what the human chose
    let effectiveAnswer: String         // what was actually delivered (trial guardrail)
    let routedIsTrial: Bool
    let newCategoryCreated: Bool
    let changed: Bool
    let gesture: String                 // pass | flip | select | new
    let priority: Double
    let latency: TimeInterval
    let shownAt: Date
    let decidedAt: Date
    let position: Vec3
    let distanceFromHead: Float
    let neighbors: [String]
    let queueDepth: Int
    let groundTruth: String?
    let agreesWithGroundTruth: Bool?
    var downstreamOutcome: String?
}
