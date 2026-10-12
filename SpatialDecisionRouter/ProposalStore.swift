import Foundation
import Observation
import simd

@MainActor @Observable final class ProposalStore {
    static let head: SIMD3<Float> = [0, 1.5, 0]
    var proposals: [Proposal] = []
    var positions: [String: SIMD3<Float>] = [:]
    var firstShown: [String: Date] = [:]
    var resolved: Set<String> = []
    var inspecting: [String: Date] = [:]
    var logs: [DecisionLog] = []
    var loadError: String?
    var immersiveOpen = false
    var sessionStart = Date()
    var lastAction: String = ""
    var biasUncertain = true
    var stream = "content_safety"
    var packVersion = 0
    var lastExport: String = ""
    static let packs = ["content_safety", "medical_imaging", "robot_actions"]
    static let stopDistance: Float = 1.3
    static let minSpacing: Float = 0.5

    var logURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("decision_log.jsonl")
    }

    init() {
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-pack"), i + 1 < a.count { load(stream: a[i + 1]) } else { load(stream: "content_safety") }
    }

    func nextPack() {
        let i = (Self.packs.firstIndex(of: stream) ?? 0) + 1
        load(stream: Self.packs[i % Self.packs.count])
    }

    func load(stream: String) {
        guard let url = Bundle.main.url(forResource: stream, withExtension: "json") else {
            loadError = "Missing \(stream).json"; return }
        do {
            proposals = try JSONDecoder().decode([Proposal].self, from: Data(contentsOf: url))
                .sorted { $0.priority > $1.priority }
            positions = Dictionary(uniqueKeysWithValues: proposals.enumerated().map {
                ($1.id, Layout.position(rank: $0, count: proposals.count)) })
            resolved = []; firstShown = [:]; inspecting = [:]; loadError = nil
            self.stream = stream; packVersion += 1
        } catch { loadError = "Decode failed: \(error)" }
    }

    // MARK: metrics
    var decisionsPerMinute: Double {
        guard let first = firstShown.values.min(), !logs.isEmpty else { return 0 }
        return Double(logs.count) / max(Date().timeIntervalSince(first) / 60, 1.0 / 60)
    }
    var accuracy: Double? {
        let judged = logs.compactMap(\.agreesWithGroundTruth)
        return judged.isEmpty ? nil : Double(judged.filter { $0 }.count) / Double(judged.count)
    }

    func rank(of id: String) -> Int? { proposals.firstIndex { $0.id == id } }
    func position(of id: String) -> SIMD3<Float> { positions[id] ?? .zero }
    func markShown(_ id: String) { if firstShown[id] == nil { firstShown[id] = Date() } }
    func beginInspect(_ id: String) { if inspecting[id] == nil { inspecting[id] = Date() } }

    /// Drift: unresolved items move toward the head at a rate scaled by priority (and uncertainty when biased).
    func tick(dt: Float) {
        let active = proposals.filter { !resolved.contains($0.id) && inspecting[$0.id] == nil }
        for p in active {
            guard let pos = positions[p.id] else { continue }
            let toHead = Self.head - pos
            let dist = simd_length(toHead)
            guard dist > Self.stopDistance + 0.001 else { continue }
            // max priority reaches stop from the outer ring (~2.7 m) in ~75 s
            var rate: Float = 0.018 * p.priority * p.priority
            if biasUncertain && abs(p.confidence - 0.5) < 0.12 { rate *= 1.5 }
            positions[p.id] = pos + simd_normalize(toHead) * min(rate * dt, dist - Self.stopDistance)
        }
        // separation: push overlapping cards apart (tangentially + vertically), keep >= stop distance
        for _ in 0..<2 {
            for (a, pa) in active.enumerated() {
                for pb in active[(a + 1)...] {
                    guard var A = positions[pa.id], var B = positions[pb.id] else { continue }
                    var d = A - B
                    let len = simd_length(d)
                    guard len < Self.minSpacing else { continue }
                    if len < 1e-4 { d = [0.01, 0.01, 0] }
                    let push = simd_normalize(d) * (Self.minSpacing - len) * 0.5
                    A += push; B -= push
                    positions[pa.id] = clampOut(A); positions[pb.id] = clampOut(B)
                }
            }
        }
    }

    private func clampOut(_ p: SIMD3<Float>) -> SIMD3<Float> {
        var v = p - Self.head
        v.y = max(-0.45, min(0.75, v.y))
        let l = simd_length(v)
        return l < Self.stopDistance ? Self.head + v / l * Self.stopDistance : Self.head + v
    }

    // MARK: Phase 5 — outcome joining + export
    func readLog() -> [DecisionLog] {
        guard let text = try? String(contentsOf: logURL, encoding: .utf8) else { return [] }
        let dec = JSONDecoder(); dec.dateDecodingStrategy = .iso8601
        return text.split(separator: "\n").compactMap { try? dec.decode(DecisionLog.self, from: Data($0.utf8)) }
    }

    /// Applies `<stream>_outcomes.json` ({proposalID: outcome}) for every pack to existing log lines.
    @discardableResult func joinOutcomes() -> Int {
        var outcomes: [String: String] = [:]
        for pack in Self.packs {
            if let u = Bundle.main.url(forResource: "\(pack)_outcomes", withExtension: "json"),
               let d = try? Data(contentsOf: u), let m = try? JSONDecoder().decode([String: String].self, from: d) {
                outcomes.merge(m) { a, _ in a }
            }
        }
        var entries = readLog(); var joined = 0; let now = Date()
        for k in entries.indices {
            guard entries[k].outcome == nil, let o = outcomes[entries[k].proposal.id] else { continue }
            entries[k].outcome = o; entries[k].outcomeJoinedAt = now
            entries[k].agreesWithOutcome = entries[k].chosenLabel.map { $0 == o }
            joined += 1
        }
        let enc = encoder()
        let data = entries.compactMap { try? enc.encode($0) }.reduce(into: Data()) { $0.append($1); $0.append(0x0A) }
        try? data.write(to: logURL)
        logs = entries
        return joined
    }

    func export() {
        let joined = joinOutcomes()
        let dir = logURL.deletingLastPathComponent().appendingPathComponent("exports", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let ts = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let entries = readLog()
        try? FileManager.default.copyItem(at: logURL, to: dir.appendingPathComponent("session-\(ts).jsonl"))
        let enc = encoder(); enc.outputFormatting = [.sortedKeys, .prettyPrinted]
        try? enc.encode(entries).write(to: dir.appendingPathComponent("session-\(ts).json"))
        lastExport = "Exported \(entries.count) (\(joined) outcomes joined)"
    }

    private func encoder() -> JSONEncoder {
        let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; e.outputFormatting = [.sortedKeys]; return e
    }

    /// Next item a reviewer would naturally take: closest unresolved.
    var nearestUnresolved: Proposal? {
        proposals.filter { !resolved.contains($0.id) }
            .min { simd_distance(position(of: $0.id), Self.head) < simd_distance(position(of: $1.id), Self.head) }
    }

    func resolve(_ id: String, action: HumanAction, label: String? = nil) {
        guard let i = rank(of: id), !resolved.contains(id) else { return }
        let p = proposals[i]
        let pos = position(of: id)
        let chosen: String? = label ?? {
            switch action {
            case .accept: return p.recommended
            case .reject: return p.options.first { $0 != p.recommended } ?? "keep"
            case .recategorize:
                if p.type == .binary { return "needs-review" }
                let alts = p.options.filter { $0 != p.recommended }
                let prior = logs.filter { $0.proposal.category == p.category && $0.action == .recategorize }.count
                return alts.isEmpty ? "needs-review" : alts[prior % alts.count]
            case .needsMoreInfo: return nil
            }
        }()
        let unresolved = proposals.filter { !resolved.contains($0.id) && $0.id != id }
        let neighbors = unresolved.sorted { simd_distance(position(of: $0.id), pos) < simd_distance(position(of: $1.id), pos) }
            .prefix(4).map(\.id)
        let now = Date()
        let shown = firstShown[id] ?? now
        let inspectStart = inspecting.removeValue(forKey: id)
        let agrees: Bool? = (p.groundTruth != nil && chosen != nil) ? p.groundTruth == chosen : nil
        let entry = DecisionLog(
            proposal: p,
            position: SpatialSnapshot(x: pos.x, y: pos.y, z: pos.z, priority: p.priority, distance: simd_distance(pos, Self.head)),
            action: action, chosenLabel: chosen, shownAt: shown, decidedAt: now,
            decisionLatency: now.timeIntervalSince(shown),
            inspected: inspectStart != nil, inspectDuration: inspectStart.map { now.timeIntervalSince($0) },
            neighborProposalIDs: Array(neighbors), unresolvedCount: unresolved.count,
            recentOverrideCount: logs.suffix(10).filter { $0.action != .accept }.count,
            outcome: nil, outcomeJoinedAt: nil, agreesWithOutcome: nil, stream: stream, agreesWithGroundTruth: agrees)
        logs.append(entry)
        resolved.insert(id)
        lastAction = "\(action.rawValue) \(p.id) → \(chosen ?? "—")"
        append(entry)
    }

    private func append(_ entry: DecisionLog) {
        let enc = JSONEncoder(); enc.dateEncodingStrategy = .iso8601; enc.outputFormatting = [.sortedKeys]
        guard var data = try? enc.encode(entry) else { return }
        data.append(0x0A)
        if let h = try? FileHandle(forWritingTo: logURL) { h.seekToEndOfFile(); h.write(data); try? h.close() }
        else { try? data.write(to: logURL) }
    }

    /// Test helper: resolves N nearest items with a mix of actions.
    func autoResolve(_ n: Int, interval: Double = 1.5) async {
        let acts: [HumanAction] = [.accept, .reject, .recategorize, .accept, .needsMoreInfo, .accept, .recategorize]
        for k in 0..<n {
            try? await Task.sleep(for: .seconds(interval))
            guard let p = nearestUnresolved else { return }
            if k % 3 == 1 { beginInspect(p.id); try? await Task.sleep(for: .milliseconds(400)) }
            resolve(p.id, action: acts[k % acts.count])
        }
    }
}
