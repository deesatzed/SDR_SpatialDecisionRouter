import Foundation

// MARK: - Optional "Game mode" layer (generic; a domain fills GameHUD, the engine/views render it).
// Focus mode hides all of it. Nothing here changes routing, ground truth or what is sent to an agent.

struct GameGoal: Identifiable, Hashable { var id: String { title }; let title: String; let progress: Int; let target: Int
    var done: Bool { progress >= target } }
struct GameLevel: Identifiable, Hashable { var id: String { scope }; let scope: String; let level: Int; let progress: Double; let note: String }
struct CalibrationBin: Identifiable, Hashable { var id: String { label }; let label: String; let predicted: Double; let observed: Double?; let n: Int }
struct Reveal: Identifiable, Equatable { let id: String; let title: String; let detail: String; let hit: Bool?; let at: Date }

struct GameHUD {
    var score = 0, streak = 0, bestStreak = 0, combo = 1
    var graded = 0, hits = 0
    var goals: [GameGoal] = []
    var levels: [GameLevel] = []
    var levelCaption = ""
    var calibration: [CalibrationBin] = []
    var calibrationNote = ""
    var flipLine = ""
    var recap: [String]? = nil          // non-nil → end-of-session recap card
    var actions: [(id: String, title: String)] = []
    var countdown: String? = nil        // e.g. live pause timeout
}

/// Optional domain hooks (defaults: no game layer, no late truth).
extension DomainModule {
    func gameHUD() -> GameHUD? { nil }
    func takeReveal() -> Reveal? { nil }
    func gameAction(_ id: String) {}
    /// late ground truth from the world (item id → truth answer), applied to logged decisions + board
    func takeOutcomes() -> [(String, String)] { [] }
    /// demo script answer (never used as ground truth)
    func demoAnswer(item: DomainItem, link: LinkSpec) -> String? { nil }
    /// called the moment the human (or auto-pass) decides, before delivery animation
    func decided(item: DomainItem, link: LinkSpec, answer: String, latency: TimeInterval, by: String) {}
}
