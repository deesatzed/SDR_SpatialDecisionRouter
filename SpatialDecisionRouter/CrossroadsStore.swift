import Foundation
import Observation
import simd

enum Phase: Hashable { case incoming, waiting, outgoing, delivered }

@MainActor @Observable final class CrossroadsStore {
    static let head: SIMD3<Float> = [0, 1.5, 0]
    static let hub: SIMD3<Float> = [0, 1.4, -1.05]
    var scenario: Scenario?
    var handoffs: [Handoff] = []
    var phase: [String: Phase] = [:]
    var progress: [String: Float] = [:]
    var slot: [String: Int] = [:]
    var shownAt: [String: Date] = [:]
    var routed: [String: String] = [:]
    var inbox: [String: Int] = [:]
    var ringFor: String?                 // handoff whose radial option ring is open
    var decisions: [RoutingDecision] = []
    var upstream: [String: [String]] = [:]   // caseID -> routed answers so far
    var sessionStart = Date()
    var lastAction = ""
    var lastExport = ""
    var loadError: String?
    var immersiveOpen = false
    var speedup: Float = 1
    var fullImmersion = !ProcessInfo.processInfo.arguments.contains("-mixed")
    private var nextCase = 0
    private var spawnTimer: Float = 0
    var maxActive: Int { isStream ? 8 : 5 }

    var logURL: URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("routing_log.jsonl") }

    init() {
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-speedup"), i + 1 < a.count, let v = Float(a[i + 1]) { speedup = v }
        if let i = a.firstIndex(of: "-pack"), i + 1 < a.count { load(a[i + 1]) } else { load("triage_stream") }
    }
    static let packs = ["triage_stream", "ed_patient_flow", "support_crossroads"]
    var packName = ""
    var packVersion = 0
    var lastDelivered: [String: Date] = [:]
    var caseStatus: [String: String] = [:]   // caseID -> correct | corrected | missed
    var deliveries = 0
    func nextPack() {
        let i = ((Self.packs.firstIndex(of: packName) ?? 0) + 1) % Self.packs.count
        load(Self.packs[i])
    }

    var cases: [CaseSpec] = []
    var isStream: Bool { packName == "triage_stream" }
    var gen = TriageGenerator(seed: 2026)
    var patients: [String: TriagePatient] = [:]
    var routedByStage: [String: [Int: String]] = [:]
    var deliveredStages: [String: Set<Int>] = [:]
    var completedOrder: [String] = []

    func load(_ name: String) {
        if name == "triage_stream" {
            scenario = TriageGenerator.scenario; cases = []; patients = [:]; gen = TriageGenerator(seed: 2026)
            resetState(name); return
        }
        guard let u = Bundle.main.url(forResource: name, withExtension: "json"),
              let d = try? Data(contentsOf: u) else { loadError = "missing \(name).json"; return }
        do { scenario = try JSONDecoder().decode(Scenario.self, from: d) } catch { loadError = "\(error)"; return }
        cases = scenario?.cases ?? []
        resetState(name)
    }
    private func resetState(_ name: String) {
        routedByStage = [:]; deliveredStages = [:]; completedOrder = []
        handoffs = []; phase = [:]; progress = [:]; slot = [:]; routed = [:]; upstream = [:]
        decisions = []; caseStatus = [:]; deliveries = 0; lastDelivered = [:]; ringFor = nil
        packName = name; packVersion += 1
        inbox = Dictionary(uniqueKeysWithValues: (scenario?.agents ?? []).map { ($0.id, 0) })
        nextCase = 0; spawnTimer = 99; sessionStart = Date()
    }

    // MARK: geometry
    func agentIndex(_ id: String) -> Int { scenario?.agents.firstIndex { $0.id == id } ?? 0 }
    func agentPosition(_ id: String) -> SIMD3<Float> {
        if let sc = scenario, let ag = sc.agents.first(where: { $0.id == id }), let tier = ag.tier {
            let peers = sc.agents.filter { $0.tier == tier }
            let k = Float(peers.firstIndex { $0.id == id } ?? 0), m = Float(peers.count)
            if tier == 0 {   // source agents: low tier, wide
                let a = (-36 + 72 * k / max(m - 1, 1)) * .pi / 180
                return [2.1 * sin(a), 0.95, -2.1 * cos(a)]
            } else {         // destinations: high tier, split left/right of the board
                let angs: [Float] = [-44, -27, 27, 44]
                let a = angs[min(Int(k), 3)] * .pi / 180
                return [2.5 * sin(a), 1.85, -2.5 * cos(a)]
            }
        }
        let n = Float(scenario?.agents.count ?? 4)
        let a = (-46 + 92 * Float(agentIndex(id)) / max(n - 1, 1)) * .pi / 180
        return [2.1 * sin(a), 1.55, -2.1 * cos(a)]
    }
    func slotPosition(_ k: Int) -> SIMD3<Float> {
        if isStream {   // 4 columns x 2 rows
            let a = (-36 + 24 * Float(k % 4)) * .pi / 180
            return [1.45 * sin(a), 1.16 + Float(k / 4) * 0.36, -1.45 * cos(a)]
        }
        let a = (-30 + 15 * Float(k)) * .pi / 180
        return [1.3 * sin(a), 1.2 + Float(k % 2) * 0.34, -1.3 * cos(a)]
    }
    func position(_ h: Handoff) -> SIMD3<Float> {
        let s = slotPosition(slot[h.id] ?? 0), t = progress[h.id] ?? 0
        switch phase[h.id] ?? .incoming {
        case .incoming: return simd_mix(agentPosition(h.link.source), s, SIMD3(repeating: smooth(t)))
        case .waiting: return s
        case .outgoing, .delivered:
            let hub = Self.hub, d = agentPosition(h.link.dest)
            return t < 0.3 ? simd_mix(s, hub, SIMD3(repeating: smooth(t / 0.3)))
                           : simd_mix(hub, d, SIMD3(repeating: smooth((t - 0.3) / 0.7)))
        }
    }
    private func smooth(_ t: Float) -> Float { t * t * (3 - 2 * t) }

    var active: [Handoff] { handoffs.filter { [.incoming, .waiting].contains(phase[$0.id]) } }
    var waiting: [Handoff] { handoffs.filter { phase[$0.id] == .waiting } }

    // MARK: simulation
    func tick(_ dt0: Float) {
        guard let sc = scenario else { return }
        let dt = dt0 * speedup
        spawnTimer += dt
        _ = sc
        if isStream {
            if spawnTimer > 3, active.count <= maxActive - 4 {
                spawnTimer = 0
                let (c, p) = gen.nextCase(); cases.append(c); patients[c.caseID] = p
                for s in 0..<4 { emit(case: c, stage: s, upstreamCorrect: true) }   // parallel off the same intake
            }
        } else if spawnTimer > 4, nextCase < cases.count, active.count < maxActive {
            spawnTimer = 0
            let c = cases[nextCase]; nextCase += 1
            emit(case: c, stage: 0, upstreamCorrect: true)
        }
        for h in handoffs {
            switch phase[h.id] {
            case .incoming:
                let p = (progress[h.id] ?? 0) + dt / 3
                if p >= 1 { phase[h.id] = .waiting; shownAt[h.id] = Date() } else { progress[h.id] = p }
            case .outgoing:
                let p = (progress[h.id] ?? 0) + dt / 2.6
                if p >= 1 { progress[h.id] = 1; phase[h.id] = .delivered; deliver(h) } else { progress[h.id] = p }
            default: break
            }
        }
    }

    private func freeSlot() -> Int {
        let used = Set(active.compactMap { slot[$0.id] })
        return (0..<maxActive).first { !used.contains($0) } ?? 0
    }

    private func emit(case c: CaseSpec, stage: Int, upstreamCorrect: Bool, proposal: String? = nil) {
        guard let sc = scenario, stage < sc.links.count, stage < c.stages.count else { return }
        let st = c.stages[stage]
        let h = Handoff(id: "\(c.caseID)-s\(stage + 1)", caseID: c.caseID, stage: stage, link: sc.links[stage],
                        inputContext: c.context, history: c.history ?? "none", proposedAnswer: proposal ?? (upstreamCorrect ? st.propOk : st.propBad),
                        confidence: st.conf, groundTruth: st.gt, createdAt: Date())
        slot[h.id] = freeSlot(); phase[h.id] = .incoming; progress[h.id] = 0
        handoffs.append(h)
    }

    /// Destination agent consumes the routed answer and (deterministically) emits its own handoff.
    private func deliver(_ h: Handoff) {
        inbox[h.link.dest, default: 0] += 1
        deliveries += 1
        lastDelivered[h.link.dest] = Date()
        guard let sc = scenario, let c = cases.first(where: { $0.caseID == h.caseID }) else { return }
        let correct = routed[h.id] == h.groundTruth
        if isStream {
            deliveredStages[h.caseID, default: []].insert(h.stage)
            let d = deliveredStages[h.caseID]!
            let r = routedByStage[h.caseID] ?? [:]
            if h.stage < 4, d.isSuperset(of: [0, 1, 2]), !handoffs.contains(where: { $0.id == "\(h.caseID)-s5" }) {
                let prop = gen.placementProposal(esi: r[0] ?? "3", sepsis: r[1] ?? "no", alert: r[2] ?? "none")
                emit(case: c, stage: 4, upstreamCorrect: true, proposal: prop)
            }
            if d.count == 5 { finishCase(h.caseID) }
            return
        }
        if h.stage + 1 < sc.links.count {
            emit(case: c, stage: h.stage + 1, upstreamCorrect: correct)
        } else {
            // terminal agent acted: join outcome onto every decision in this chain
            let chain = decisions.indices.filter { decisions[$0].caseID == h.caseID }
            let allOK = chain.allSatisfy { decisions[$0].agreesWithGroundTruth == true }
            let changedAny = chain.contains { decisions[$0].changed }
            let outcome = correct ? (allOK ? (changedAny ? "resolved-after-human-correction" : "resolved-correctly") : "resolved-despite-upstream-error")
                                  : "misrouted:\(routed[h.id] ?? "?")≠\(h.groundTruth ?? "?")"
            for k in chain { decisions[k].downstreamOutcome = outcome }
            let anyWrong = chain.contains { decisions[$0].agreesWithGroundTruth == false }
            let anyChanged = chain.contains { decisions[$0].changed }
            caseStatus[h.caseID] = anyWrong ? "missed" : (anyChanged ? "corrected" : "correct")
            rewriteLog()
        }
    }

    private func finishCase(_ id: String) {
        let chain = decisions.indices.filter { decisions[$0].caseID == id }
        let anyWrong = chain.contains { decisions[$0].agreesWithGroundTruth == false }
        let anyChanged = chain.contains { decisions[$0].changed }
        let outcome = anyWrong ? "triage-error-reached-floor" : (anyChanged ? "triaged-after-human-correction" : "triaged-correctly")
        for k in chain { decisions[k].downstreamOutcome = outcome }
        caseStatus[id] = anyWrong ? "missed" : (anyChanged ? "corrected" : "correct")
        completedOrder.append(id)
        rewriteLog()
    }

    // triage board stats
    var areaCounts: [(String, Int)] {
        let placed = decisions.filter { $0.stage == 5 && caseStatus[$0.caseID] != nil }
        return ["resus", "main ED", "fast track", "waiting room"].map { a in (a, placed.filter { $0.routedAnswer == a }.count) }
    }
    var alertsFired: Int { decisions.filter { ($0.stage == 2 && $0.routedAnswer == "yes") || ($0.stage == 3 && $0.routedAnswer != "none") }.count }
    var misses: Int { decisions.filter { $0.agreesWithGroundTruth == false }.count }
    var medianLatency: Double {
        let l = decisions.map(\.latency).sorted(); return l.isEmpty ? 0 : l[l.count / 2]
    }
    var agentErrorRate: Double {
        let j = decisions.compactMap { d in d.groundTruth.map { $0 != d.proposedAnswer } }
        return j.isEmpty ? 0 : Double(j.filter { $0 }.count) / Double(j.count)
    }

    // MARK: human routing
    func pass(_ id: String) { route(id, answer: nil, gesture: "pass") }
    func flip(_ id: String) {
        guard let h = handoffs.first(where: { $0.id == id }) else { return }
        if h.link.answerType == .binary {
            route(id, answer: h.link.options.first { $0 != h.proposedAnswer }, gesture: "flip")
        }   // drag on a category item is ignored (use long-press or "Change…")
    }
    func openRing(_ id: String) { ringFor = id }
    func select(_ id: String, _ option: String) { ringFor = nil; route(id, answer: option, gesture: "select") }

    private func route(_ id: String, answer: String?, gesture: String) {
        guard let h = handoffs.first(where: { $0.id == id }), [.incoming, .waiting].contains(phase[id]) else { return }
        let ans = answer ?? h.proposedAnswer
        let pos = position(h), now = Date(), shown = shownAt[id] ?? h.createdAt
        let others = active.filter { $0.id != id }
        let d = RoutingDecision(
            scenario: scenario?.scenario ?? "", caseID: h.caseID, stage: h.stage + 1,
            sourceAgent: h.link.source, destAgent: h.link.dest, question: h.link.question,
            inputContext: h.inputContext, history: h.history, upstreamAnswers: upstream[h.caseID] ?? [],
            proposedAnswer: h.proposedAnswer, proposedConfidence: h.confidence,
            answerType: h.link.answerType, options: h.link.options,
            routedAnswer: ans, changed: ans != h.proposedAnswer, gesture: gesture,
            latency: now.timeIntervalSince(shown), shownAt: shown, decidedAt: now,
            position: Vec3(x: pos.x, y: pos.y, z: pos.z), distanceFromHead: simd_distance(pos, Self.head),
            neighbors: others.map(\.id), queueDepth: others.count,
            groundTruth: h.groundTruth, agreesWithGroundTruth: h.groundTruth.map { $0 == ans },
            downstreamOutcome: nil)
        decisions.append(d)
        upstream[h.caseID, default: []].append("\(h.link.source)→\(h.link.dest): \(ans)")
        routed[id] = ans
        routedByStage[h.caseID, default: [:]][h.stage] = ans
        if phase[id] == .incoming { progress[id] = 0 }   // snap to crossroads before leaving
        phase[id] = .outgoing; progress[id] = 0
        if ringFor == id { ringFor = nil }
        lastAction = "\(gesture) \(id): \(h.proposedAnswer)\(d.changed ? " → \(ans)" : " ✓")"
        appendLog(d)
    }

    // MARK: metrics
    var handoffsPerMinute: Double {
        decisions.isEmpty ? 0 : Double(decisions.count) / max(Date().timeIntervalSince(sessionStart) / 60, 1.0 / 60)
    }
    var pctChanged: Double { decisions.isEmpty ? 0 : Double(decisions.filter(\.changed).count) / Double(decisions.count) }
    var agreement: Double? {
        let j = decisions.compactMap(\.agreesWithGroundTruth)
        return j.isEmpty ? nil : Double(j.filter { $0 }.count) / Double(j.count)
    }

    // MARK: board
    struct BoardRow: Identifiable { let id: String; let context: String; let steps: [(String, Bool, Bool)]; let status: String }
    var boardRows: [BoardRow] {
        guard let sc = scenario else { return [] }
        let started = cases.filter { c in handoffs.contains { $0.caseID == c.caseID } }
        return started.map { c in
            let ds = decisions.filter { $0.caseID == c.caseID }.sorted { $0.stage < $1.stage }
            let steps = ds.map { ($0.routedAnswer, $0.changed, $0.agreesWithGroundTruth ?? true) }
            var ctx = c.context.replacingOccurrences(of: "[SYNTHETIC] ", with: "")
            if isStream, let p = patients[c.caseID] { ctx = "\(p.age)\(p.sex) \(p.complaint.rawValue)" + (c.history == "none" ? "" : " · \(c.history ?? "")") }
            return BoardRow(id: c.caseID, context: ctx,
                            steps: steps, status: caseStatus[c.caseID] ?? "in progress \(ds.count)/\(sc.links.count)")
        }
    }
    var casesCompleted: Int { caseStatus.count }
    var corrections: Int { decisions.filter(\.changed).count }
    var errorsPrevented: Int { decisions.filter { $0.changed && $0.agreesWithGroundTruth == true }.count }
    var missed: Int { caseStatus.values.filter { $0 == "missed" }.count }

    // MARK: logging / export
    private func enc() -> JSONEncoder { let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; e.outputFormatting = [.sortedKeys]; return e }
    private func appendLog(_ d: RoutingDecision) {
        guard var data = try? enc().encode(d) else { return }
        data.append(0x0A)
        if let f = try? FileHandle(forWritingTo: logURL) { f.seekToEndOfFile(); f.write(data); try? f.close() } else { try? data.write(to: logURL) }
    }
    /// Rewrites this session's lines so downstream outcomes are joined (prior sessions' lines are kept).
    private func rewriteLog() {
        let dec = JSONDecoder(); dec.dateDecodingStrategy = .iso8601
        let text = (try? String(contentsOf: logURL, encoding: .utf8)) ?? ""
        let mine = Set(decisions.map(\.id))
        var old = text.split(separator: "\n").compactMap { try? dec.decode(RoutingDecision.self, from: Data($0.utf8)) }.filter { !mine.contains($0.id) }
        old.append(contentsOf: decisions)
        let e = enc()
        let data = old.compactMap { try? e.encode($0) }.reduce(into: Data()) { $0.append($1); $0.append(0x0A) }
        try? data.write(to: logURL)
    }
    func export() {
        rewriteLog()
        let dir = logURL.deletingLastPathComponent().appendingPathComponent("exports", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let ts = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        try? FileManager.default.copyItem(at: logURL, to: dir.appendingPathComponent("routing-\(ts).jsonl"))
        let e = enc(); e.outputFormatting = [.sortedKeys, .prettyPrinted]
        try? e.encode(decisions).write(to: dir.appendingPathComponent("routing-\(ts).json"))
        lastExport = "Exported \(decisions.count) decisions"
    }

    /// Test driver: acts on waiting handoffs. Mostly routes to ground truth (as an attentive human would),
    /// sometimes passes through blindly, exercising pass / flip / select.
    func autoResolve(_ n: Int) async {
        var k = 0
        while k < n {
            try? await Task.sleep(for: .seconds(Double(1.6 / speedup)))
            guard let h = waiting.first else { continue }
            if k % 9 == 8 { pass(h.id) }
            else if let gt = h.groundTruth, gt != h.proposedAnswer {
                if h.link.answerType == .binary { flip(h.id) }
                else { ringFor = h.id; try? await Task.sleep(for: .milliseconds(700)); select(h.id, gt) }
            } else { pass(h.id) }
            k += 1
        }
    }
}
