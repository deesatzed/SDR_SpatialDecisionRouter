import Foundation
/// Phase A stub: no queueing yet (replaced by the DES in phase C).
struct EDCapacity {
    var lwbs = 0, waitingCount = 0, boardingMinutes = 0.0, alertWaits: [Double] = []
    var placed: [String: Int] = [:]
    init(params: [String: Double], seed: UInt64) {}
    mutating func prewarm(now: Double) {}
    mutating func step(now: Double, dm: Double) {}
    func capacityAwareArea(esi: Int, alert: String, base: String) -> String { base }
    mutating func place(id: String, esi: Int, area: String, isolation: Bool, arrival: Double, now: Double) { placed[area, default: 0] += 1 }
    func snapshot(queue: Int) -> [String: String] { ["triageQueue": "\(queue)"] }
    func line(queue: Int) -> String { "triage queue \(queue)" }
    var medianDoorToRoom: Double { 0 }
    var medianAlertWait: Double { let s = alertWaits.sorted(); return s.isEmpty ? 0 : s[s.count / 2] }
    var placedCounts: [(String, Int)] { ["resus", "main ED", "fast track", "waiting room"].map { ($0, placed[$0] ?? 0) } }
}
