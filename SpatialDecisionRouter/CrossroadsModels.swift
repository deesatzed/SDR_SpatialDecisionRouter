import Foundation

enum AnswerType: String, Codable { case binary, category }

struct AgentSpec: Codable, Hashable { let id: String; let name: String; var role: String? }
struct LinkSpec: Codable, Hashable { let source: String; let dest: String; let question: String; let answerType: AnswerType; let options: [String] }
/// Deterministic simulated agent output for one stage: what it proposes depends on whether its input was correct.
struct StageSpec: Codable, Hashable { let gt: String; let propOk: String; let propBad: String; let conf: Double }
struct CaseSpec: Codable, Hashable { let caseID: String; let context: String; let stages: [StageSpec] }
struct Scenario: Codable { let scenario: String; let agents: [AgentSpec]; let links: [LinkSpec]; let cases: [CaseSpec] }

/// One answer in flight from a source agent to a destination agent.
struct Handoff: Identifiable, Hashable {
    let id: String
    let caseID: String
    let stage: Int
    let link: LinkSpec
    let inputContext: String
    let proposedAnswer: String
    let confidence: Double
    let groundTruth: String?
    let createdAt: Date
}

struct Vec3: Codable, Hashable { var x: Float; var y: Float; var z: Float }

/// Training record: one human routing decision at the crossroads.
struct RoutingDecision: Codable, Identifiable {
    var id = UUID()
    let scenario: String
    let caseID: String
    let stage: Int
    let sourceAgent: String
    let destAgent: String
    let question: String
    let inputContext: String
    let upstreamAnswers: [String]
    let proposedAnswer: String
    let proposedConfidence: Double
    let answerType: AnswerType
    let options: [String]
    let routedAnswer: String
    let changed: Bool
    let gesture: String              // pass | flip | select
    let latency: TimeInterval
    let shownAt: Date
    let decidedAt: Date
    let position: Vec3
    let distanceFromHead: Float
    let neighbors: [String]          // other handoffs waiting at the crossroads
    let queueDepth: Int
    let groundTruth: String?
    let agreesWithGroundTruth: Bool?
    var downstreamOutcome: String?   // filled when the chain reaches the Action Agent
}
