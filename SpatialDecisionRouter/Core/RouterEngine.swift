import Foundation
import Observation
import simd

enum Phase: Hashable { case incoming, waiting, outgoing, delivered }

/// One routed decision in flight from a source agent to a destination node.
struct Handoff: Identifiable, Hashable {
    let id: String
    let itemId: String
    let link: LinkSpec
    let proposal: String
    let confidence: Double
    let groundTruth: String?
    let upstream: [String: String]
    let capacity: [String: String]
    let capacityLine: String
    let priority: Double          // base: (1-conf)(1+cost) + domain urgency; wait added live
    let createdAt: Date
    var reasons: [ReasonChip] = []
    var emittedAtMin: Double = 0  // domain clock
    var preview: String = ""      // what happens if passed
    var altPreview: String?       // what happens if flipped (binary)
    var trigger: String?          // hard escalation trigger (bypasses reliability analysis)
    var firedAt: Date?
    static func == (a: Handoff, b: Handoff) -> Bool { a.id == b.id }
    func hash(into h: inout Hasher) { h.combine(id) }
}

/// Domain-agnostic crossroads engine: spatial queue, gestures → decisions, dependency graph, logging, export.
@MainActor @Observable final class RouterEngine {
    static let head: SIMD3<Float> = [0, 1.5, 0]
    static let hub: SIMD3<Float> = [0, 0.85, -1.5]
    static let nowCard: SIMD3<Float> = [0, 1.5, -1.4]
    static let upNextPos: SIMD3<Float> = [0.86, 1.52, -1.24]
    static let sidePos: SIMD3<Float> = [-0.86, 1.52, -1.24]

    private(set) var domain: DomainModule
    var config: DomainConfig { domain.config }
    var registry: CategoryRegistry
    var siteId: String

    var items: [String: DomainItem] = [:]
    var itemOrder: [String] = []
    var handoffs: [Handoff] = []
    var phase: [String: Phase] = [:]
    var progress: [String: Float] = [:]
    var slot: [String: Int] = [:]
    var shownAt: [String: Date] = [:]
    var routed: [String: String] = [:]                 // handoff id -> human answer
    var effective: [String: [String: String]] = [:]    // item id -> link id -> effective answer
    var delivered: [String: Set<String>] = [:]         // item id -> link ids delivered
    var itemStatus: [String: String] = [:]             // correct | corrected | missed
    var inbox: [String: Int] = [:]
    var lastDelivered: [String: Date] = [:]
    var decisions: [RoutingDecision] = []
    var alertsFired = 0
    var deliveries = 0
    var ringFor: String?
    var lastAction = ""
    var lastExport = ""
    var immersiveOpen = false
    var fullImmersion = !ProcessInfo.processInfo.arguments.contains("-mixed")
    var speedup: Float = 1
    var packVersion = 0
    var sessionStart = Date()
    private var spawnTimer: Float = 99
    let maxActive = 14
    var departFrom: [String: SIMD3<Float>] = [:]

    var registryEvents: [RegistryEvent] = []
    // review queue
    var nowId: String?
    var detailOpen = false
    var openSections: [String: Date] = [:]
    private var sectionAcc: [String: Double] = [:]
    private var sectionsSeen: [String] = []
    private var detailOpenedAt: Date?
    private var detailAcc = 0.0
    private var detailUsed = false
    var spotChecks: [UUID] = []
    var spotCheckOpen = false
    private var spotRng = SplitMix64(s: 4242)
    var autoPassed = 0
    // reliability layer
    var sideTab = "details"                    // details | reliability | ask
    var itemReRatings: [String: [ReRating]] = [:]
    var itemAsks: [String: [AskEvent]] = [:]
    var lastAnswer: [String: String] = [:]     // item id -> last simulated answer
    var destFor: [String: String] = [:]        // handoff id -> actual destination (alertDest when fired)
    private var reviewerRng = SplitMix64(s: 99)
    private var testNameIdx = 0
    var registryURL: URL { logURL.deletingLastPathComponent().appendingPathComponent("registry-\(config.id)-\(siteId).json") }
    static func dec() -> JSONDecoder { let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601; return d }
    var logURL: URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("routing_log.jsonl") }

    init() {
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-speedup"), i + 1 < a.count, let v = Float(a[i + 1]) { speedup = v }
        let pick = a.firstIndex(of: "-domain").flatMap { $0 + 1 < a.count ? a[$0 + 1] : nil }
        let d = DomainCatalog.all.map { $0() }.first { $0.config.id == pick } ?? DomainCatalog.all[0]()
        domain = d
        let site = (a.firstIndex(of: "-site").flatMap { $0 + 1 < a.count ? a[$0 + 1] : nil }) ?? d.config.defaultSite
        siteId = site
        registry = CategoryRegistry(siteId: site, links: d.config.links)
        start(d)
    }

    func start(_ d: DomainModule) {
        domain = d; d.reset(seed: 2026)
        registry = CategoryRegistry(siteId: siteId, links: d.config.links)
        if !ProcessInfo.processInfo.arguments.contains("-freshRegistry"),
           let data = try? Data(contentsOf: registryURL), let p = try? Self.dec().decode(CategoryRegistry.self, from: data), p.siteId == siteId {
            registry.merge(persisted: p)
        }
        reviewerRng = SplitMix64(s: 99); testNameIdx = 0; spotRng = SplitMix64(s: 4242)
        nowId = nil; spotChecks = []; autoPassed = 0; resetDetailTelemetry()
        itemReRatings = [:]; itemAsks = [:]; lastAnswer = [:]; destFor = [:]; sideTab = "details"
        items = [:]; itemOrder = []; handoffs = []; phase = [:]; progress = [:]; slot = [:]; shownAt = [:]
        routed = [:]; effective = [:]; delivered = [:]; itemStatus = [:]; decisions = []; alertsFired = 0; deliveries = 0
        inbox = Dictionary(uniqueKeysWithValues: d.config.agents.map { ($0.id, 0) })
        lastDelivered = [:]; ringFor = nil; spawnTimer = 99; sessionStart = Date(); packVersion += 1
    }
    func nextDomain() {
        let all = DomainCatalog.all
        guard all.count > 1, let i = all.firstIndex(where: { type(of: $0()) == type(of: domain) }) else { return }
        start(all[(i + 1) % all.count]())
    }

    // MARK: geometry
    func agent(_ id: String) -> AgentSpec? { config.agents.first { $0.id == id } }
    func agentIndex(_ id: String) -> Int { config.agents.firstIndex { $0.id == id } ?? 0 }
    func agentPosition(_ id: String) -> SIMD3<Float> {
        let ag = agent(id); let tier = ag?.tier ?? 0
        let peers = config.agents.filter { $0.tier == tier }
        let k = Float(peers.firstIndex { $0.id == id } ?? 0), m = Float(max(peers.count - 1, 1))
        if tier == 0 {
            let a = (-28 + 56 * k / m) * .pi / 180
            return [2.1 * sin(a), 1.0, -2.1 * cos(a)]
        } else {
            // destinations flank the board (left pair / right pair)
            let half = Int(ceil(Float(peers.count) / 2)), ki = Int(k)
            let side: Float = ki < half ? -1 : 1
            let j = Float(ki < half ? half - 1 - ki : ki - half)
            let a = side * (25 + 11 * j) * .pi / 180
            return [2.5 * sin(a), 1.8, -2.5 * cos(a)]
        }
    }
    /// slot order: center columns first so high-priority items land front-and-center
    static let slotOrder = [1, 2, 5, 6, 0, 3, 4, 7]
    func slotPosition(_ k: Int) -> SIMD3<Float> {
        let a = (-33 + 22 * Float(k % 4)) * .pi / 180
        return [1.45 * sin(a), 1.05 + Float(k / 4) * 0.34, -1.45 * cos(a)]
    }
    /// queue rail above the Now card: index 0 = Now, then priority order
    func railPosition(_ h: Handoff) -> SIMD3<Float> {
        if h.id == nowId { return [-0.6, 2.0, -1.5] }
        let i = Float(queue.firstIndex(of: h) ?? queue.count)
        return [-0.42 + 0.095 * min(i, 9), 2.0, -1.5]
    }
    func position(_ h: Handoff) -> SIMD3<Float> {
        let s = railPosition(h), t = progress[h.id] ?? 0
        switch phase[h.id] ?? .incoming {
        case .incoming: return simd_mix(agentPosition(h.link.source), s, SIMD3(repeating: smooth(t)))
        case .waiting: return s
        case .outgoing, .delivered:
            let d = agentPosition(destFor[h.id] ?? h.link.dest), s = departFrom[h.id] ?? s
            return t < 0.3 ? simd_mix(s, Self.hub, SIMD3(repeating: smooth(t / 0.3)))
                           : simd_mix(Self.hub, d, SIMD3(repeating: smooth((t - 0.3) / 0.7)))
        }
    }
    private func smooth(_ t: Float) -> Float { t * t * (3 - 2 * t) }

    var active: [Handoff] { handoffs.filter { [.incoming, .waiting].contains(phase[$0.id]) } }
    var waiting: [Handoff] { handoffs.filter { phase[$0.id] == .waiting }.sorted { livePriority($0) > livePriority($1) } }
    var nowHandoff: Handoff? { handoffs.first { $0.id == nowId } }
    /// waiting items behind Now, priority order
    var queue: [Handoff] { waiting.filter { $0.id != nowId } }
    func waitMinutes(_ h: Handoff) -> Double { max(0, domain.now - h.emittedAtMin) }
    func livePriority(_ h: Handoff) -> Double { h.priority + config.review.waitWeight * waitMinutes(h) }
    func queueCount(_ agent: String) -> Int { waiting.filter { $0.link.source == agent }.count }
    /// domain reasons + generic ones (confidence, cost, live wait)
    func reasons(_ h: Handoff) -> [ReasonChip] {
        var r = h.reasons
        if h.confidence < 0.7 { r.append(ReasonChip(text: "low confidence \(Int(h.confidence * 100))%", key: "low confidence", severity: .warn)) }
        if h.link.costWeight >= 0.7 { r.append(ReasonChip(text: "high error cost", key: "high error cost", severity: .warn)) }
        let w = waitMinutes(h)
        if w >= 5 {
            let alert = h.link.firesAlert && !h.link.alertNegative.contains(h.proposal)
            r.append(ReasonChip(text: "\(alert ? "alert " : "")waiting \(Int(w))m", key: "waiting", severity: alert && w >= 10 ? .high : .warn))
        }
        return r
    }
    var rootLinks: [LinkSpec] { config.links.filter { $0.dependsOn.isEmpty } }

    // MARK: simulation
    func tick(_ dt0: Float) {
        let dt = dt0 * speedup
        domain.advance(minutes: Double(dt) * domain.minutesPerSecond)
        spawnTimer += dt
        if spawnTimer > 2.5, active.count <= maxActive - rootLinks.count, let item = domain.nextItem() {
            spawnTimer = 0
            items[item.id] = item; itemOrder.append(item.id)
            for l in rootLinks { emit(item: item, link: l) }
        }
        for h in handoffs {
            switch phase[h.id] {
            case .incoming:
                let p = (progress[h.id] ?? 0) + dt / 3
                if p >= 1 { phase[h.id] = .waiting; shownAt[h.id] = Date(); progress[h.id] = 1; maybeAutoPass(h) } else { progress[h.id] = p }
            case .outgoing:
                let p = (progress[h.id] ?? 0) + dt / 2.6
                if p >= 1 { progress[h.id] = 1; phase[h.id] = .delivered; deliver(h) } else { progress[h.id] = p }
            default: break
            }
        }
        // hard triggers pre-empt the Now card
        if let t = waiting.first(where: { $0.trigger != nil }), nowHandoff?.trigger == nil, nowId != t.id {
            nowId = t.id; shownAt[t.id] = Date(); resetDetailTelemetry()
        }
        if nowHandoff.map({ phase[$0.id] != .waiting }) ?? true {
            nowId = waiting.first?.id; resetDetailTelemetry()
            if nowId != nil { shownAt[nowId!] = Date() }   // latency counts from when it became Now
        }
    }

    private func maybeAutoPass(_ h: Handoff) {
        let r = config.review
        guard h.confidence >= r.autoPassConfidence, h.link.costWeight <= r.autoPassMaxCost,
              !reasons(h).contains(where: { $0.severity == .high }) else { return }
        route(h.id, answer: nil, gesture: "auto-pass", by: "auto")
        autoPassed += 1
        if spotRng.chance(r.spotCheckRate), let d = decisions.last {
            decisions[decisions.count - 1].spotCheckSampled = true; spotChecks.append(d.id)
        }
    }
    func reviewSpotCheck(_ id: UUID, agree: Bool) {
        guard let k = decisions.firstIndex(where: { $0.id == id }) else { return }
        decisions[k].spotCheckResult = agree ? "agree" : "disagree"; rewriteLog()
    }
    var pendingSpotChecks: [RoutingDecision] { decisions.filter { spotChecks.contains($0.id) && $0.spotCheckResult == nil } }

    // MARK: detail telemetry
    func toggleDetail() {
        detailOpen.toggle()
        if detailOpen { detailOpenedAt = Date(); detailUsed = true }
        else { flushDetail(); for k in Array(openSections.keys) { toggleSection(k) } }
    }
    func toggleSection(_ name: String) {
        if let t = openSections.removeValue(forKey: name) { sectionAcc[name, default: 0] += Date().timeIntervalSince(t) }
        else { openSections[name] = Date(); if !sectionsSeen.contains(name) { sectionsSeen.append(name) } }
    }
    private func flushDetail() { if let t = detailOpenedAt { detailAcc += Date().timeIntervalSince(t); detailOpenedAt = nil } }
    private func resetDetailTelemetry() {
        sectionAcc = [:]; sectionsSeen = []; detailAcc = 0; detailUsed = detailOpen
        openSections = [:]; detailOpenedAt = detailOpen ? Date() : nil
    }
    func detailSections(_ h: Handoff) -> [DetailSection] {
        guard let item = items[h.itemId] else { return [] }
        return config.detailSections.compactMap { name in
            if name == "Capacity snapshot" { return DetailSection(title: name, rows: h.capacity.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }) }
            return domain.detail(item: item, section: name).map { DetailSection(title: name, rows: $0) }
        }
    }

    private func freeSlot() -> Int {
        let used = Set(active.compactMap { slot[$0.id] })
        return Self.slotOrder.first { !used.contains($0) } ?? 0
    }

    private func emit(item: DomainItem, link: LinkSpec) {
        let up = effective[item.id] ?? [:]
        var p = domain.propose(item: item, link: link, routed: up)
        let trig = link.id == config.review.escalationLink ? domain.hardTrigger(item: item) : nil
        if trig != nil { p = Proposal(answer: config.review.escalateAnswer, confidence: 1.0) }
        let gt = domain.groundTruth(item: item, link: link, routed: up)
        let prio = (1 - p.confidence) * (1 + link.costWeight) + domain.urgency(item: item, link: link, proposal: p.answer)
        let alt = link.answerType == .binary ? link.options.first { $0 != p.answer } : nil
        let h0 = Handoff(id: "\(item.id)-\(link.id)", itemId: item.id, link: link, proposal: p.answer, confidence: p.confidence,
                        groundTruth: gt, upstream: up, capacity: domain.capacitySnapshot(), capacityLine: domain.capacityLine(),
                        priority: prio, createdAt: Date(),
                        reasons: domain.reasons(item: item, link: link, proposal: p.answer, upstream: up), emittedAtMin: domain.now,
                        preview: Review.preview(domain, item, link, p.answer, trial: false),
                        altPreview: alt.map { Review.preview(domain, item, link, $0, trial: false) })
        let h = h0
        var hh = h
        if let t = trig {
            // HARD TRIGGER: bypass reliability analysis, fire escalation now, jump to top of queue
            hh = Handoff(id: h.id, itemId: h.itemId, link: h.link, proposal: h.proposal, confidence: 1, groundTruth: h.groundTruth,
                         upstream: h.upstream, capacity: h.capacity, capacityLine: h.capacityLine, priority: 100 + h.priority, createdAt: h.createdAt,
                         reasons: [ReasonChip(text: "HARD TRIGGER: \(t)", key: "hard trigger", severity: .high)], emittedAtMin: h.emittedAtMin,
                         preview: "ESCALATED at emission — Alert Team paged; acknowledge", altPreview: nil, trigger: t, firedAt: Date())
            alertsFired += 1; domain.alertFired(item: item, link: link)
            if let ad = link.alertDest { destFor[h.id] = ad; lastDelivered[ad] = Date() }
            lastAction = "⚠ hard trigger \(item.id): \(t) — escalated"
        }
        let hfinal = hh
        slot[hfinal.id] = freeSlot(); phase[hfinal.id] = .incoming; progress[hfinal.id] = 0
        handoffs.append(hfinal)
    }

    private func deliver(_ h: Handoff) {
        let dst = destFor[h.id] ?? h.link.dest
        inbox[dst, default: 0] += 1; deliveries += 1; lastDelivered[dst] = Date()
        guard let item = items[h.itemId] else { return }
        delivered[item.id, default: []].insert(h.link.id)
        let done = delivered[item.id] ?? []
        for l in config.links where !l.dependsOn.isEmpty && !handoffs.contains(where: { $0.id == "\(item.id)-\(l.id)" }) {
            if Set(l.dependsOn).isSubset(of: done) { emit(item: item, link: l) }
        }
        if done.count == config.links.count { finish(item) }
    }

    private func finish(_ item: DomainItem) {
        let chain = decisions.indices.filter { decisions[$0].itemId == item.id }
        let anyWrong = chain.contains { decisions[$0].agreesWithGroundTruth == false }
        let anyChanged = chain.contains { decisions[$0].changed }
        let outcome = anyWrong ? "error-reached-destination" : (anyChanged ? "completed-after-human-correction" : "completed-correctly")
        for k in chain { decisions[k].downstreamOutcome = outcome }
        itemStatus[item.id] = anyWrong ? "missed" : (anyChanged ? "corrected" : "correct")
        domain.complete(item: item, effective: effective[item.id] ?? [:])
        itemCompleted(item, ok: !anyWrong)
        rewriteLog()
    }
    /// hook for subclass-like extensions (category scoring)
    func itemCompleted(_ item: DomainItem, ok: Bool) {
        for d in decisions where d.itemId == item.id && !config.links.first(where: { $0.id == d.linkId })!.options.contains(d.routedAnswer) {
            registry.recordOutcome(d.routedAnswer, linkId: d.linkId, ok: ok)
        }
        saveRegistry()
    }
    func saveRegistry() {
        let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; e.outputFormatting = [.sortedKeys, .prettyPrinted]
        try? e.encode(registry).write(to: registryURL)
    }
    func selectNew(_ id: String, _ name: String) { ringFor = nil; route(id, answer: name, gesture: "new", isNew: true) }
    func mergeCategory(_ from: String, into: String, linkId: String) {
        registry.merge(from, into: into, linkId: linkId); registryEvents.append(registry.history.last!); saveRegistry()
    }
    func splitCategory(_ name: String, into: [String], linkId: String) {
        registry.split(name, into: into, linkId: linkId); registryEvents.append(registry.history.last!); saveRegistry()
    }

    // MARK: human routing
    func pass(_ id: String) { route(id, answer: nil, gesture: "pass") }
    func flip(_ id: String) {
        guard let h = handoffs.first(where: { $0.id == id }), h.link.answerType == .binary else { return }
        route(id, answer: h.link.options.first { $0 != h.proposal }, gesture: "flip")
    }
    func openRing(_ id: String) { ringFor = id }
    // MARK: reliability actions (generic)
    func reliability(_ h: Handoff) -> [FieldReliability] { h.trigger != nil ? [] : (items[h.itemId].map { domain.reliability(item: $0) } ?? []) }
    func askNextList(_ h: Handoff) -> [VOIQuestion] { h.trigger != nil ? [] : (items[h.itemId].map { domain.askNext(item: $0) } ?? []) }
    func rerate(_ hid: String, field: String, to state: ReliabilityState) {
        guard let h = handoffs.first(where: { $0.id == hid }), let item = items[h.itemId] else { return }
        let from = domain.reliability(item: item).first { $0.field == field }?.state.rawValue ?? "?"
        domain.rerate(item: item, field: field, state: state)
        itemReRatings[item.id, default: []].append(ReRating(field: field, from: from, to: state.rawValue, at: Date()))
        lastAction = "re-rated \(item.id).\(field): \(from) → \(state.rawValue)"
        refreshItem(item.id)
    }
    func ask(_ hid: String, _ q: VOIQuestion) {
        guard let h = handoffs.first(where: { $0.id == hid }), let item = items[h.itemId],
              let ans = domain.ask(item: item, questionId: q.id) else { return }
        itemAsks[item.id, default: []].append(AskEvent(questionId: q.id, field: q.field, question: q.text, voi: q.voi, answer: ans, at: Date()))
        lastAnswer[item.id] = "\(q.field): \(ans)"; lastAction = "asked \(item.id) \(q.field) (VOI \(String(format: "%.2f", q.voi))) → \(ans)"
        refreshItem(item.id)
    }
    /// re-score an item's waiting handoffs after new information
    private func refreshItem(_ itemId: String) {
        guard let old = items[itemId] else { return }
        let item = domain.refreshed(item: old) ?? old; items[itemId] = item
        for k in handoffs.indices where handoffs[k].itemId == itemId && [.incoming, .waiting].contains(phase[handoffs[k].id]) && handoffs[k].trigger == nil {
            let h = handoffs[k]
            handoffs[k].reasons = domain.reasons(item: item, link: h.link, proposal: h.proposal, upstream: h.upstream)
            handoffs[k].preview = Review.preview(domain, item, h.link, h.proposal, trial: false)
        }
    }
    func escalate(_ id: String) { route(id, answer: config.review.escalateAnswer, gesture: "escalate") }

    /// human pulls an up-next item to the front
    func makeNow(_ id: String) { guard phase[id] == .waiting else { return }; nowId = id; shownAt[id] = Date(); resetDetailTelemetry() }
    func select(_ id: String, _ option: String) { ringFor = nil; route(id, answer: option, gesture: "select") }

    func route(_ id: String, answer: String?, gesture: String, isNew: Bool = false, by: String = "human") {
        guard let h = handoffs.first(where: { $0.id == id }), [.incoming, .waiting].contains(phase[id]),
              let item = items[h.itemId] else { return }
        var ans = answer ?? h.proposal
        if isNew { ans = registry.add(ans, link: h.link) }
        let trial = registry.isTrial(ans, link: h.link)
        let custom = !h.link.options.contains(ans)   // HITM-added category (trial or promoted)
        let eff = trial ? h.proposal : ans                 // guardrail: trial categories never change routing
        let pos = position(h), now = Date(), shown = shownAt[id] ?? h.createdAt
        let others = active.filter { $0.id != id }
        let agrees: Bool? = custom ? nil : h.groundTruth.map { $0 == ans }
        let d = RoutingDecision(
            domain: config.id, siteId: siteId, registryVersion: registry.version, itemId: item.id, linkId: h.link.id,
            sourceAgent: h.link.source, destAgent: h.link.dest, question: h.link.question,
            displayLine: item.displayLine, context: item.fields, history: item.historyLine, capacity: h.capacity,
            upstream: h.upstream, proposedAnswer: h.proposal, proposedConfidence: h.confidence,
            answerType: h.link.answerType, options: registry.mainOptions(h.link), trialOptions: registry.trialOptions(h.link),
            routedAnswer: ans, effectiveAnswer: eff, routedIsTrial: trial, newCategoryCreated: isNew,
            changed: ans != h.proposal, gesture: gesture, priority: h.priority,
            latency: now.timeIntervalSince(shown), shownAt: shown, decidedAt: now,
            position: Vec3(x: pos.x, y: pos.y, z: pos.z), distanceFromHead: simd_distance(pos, Self.head),
            neighbors: others.map(\.id), queueDepth: others.count,
            groundTruth: h.groundTruth, agreesWithGroundTruth: agrees, downstreamOutcome: nil)
        var dd = d
        dd.decidedBy = by
        dd.reasons = reasons(h).map(\.text)
        dd.downstreamPreview = Review.preview(domain, item, h.link, eff, trial: trial)
        if id == nowId && by == "human" {
            flushDetail(); for k in Array(openSections.keys) { toggleSection(k) }
            dd.detailOpened = detailUsed; dd.sectionsOpened = sectionsSeen
            dd.sectionDwell = sectionAcc.mapValues { ($0 * 10).rounded() / 10 }; dd.detailDwell = (detailAcc * 10).rounded() / 10
            if detailOpen { detailOpenedAt = Date() }
        } else { dd.detailOpened = false; dd.sectionsOpened = []; dd.sectionDwell = [:]; dd.detailDwell = 0 }
        dd.spotCheckSampled = false
        dd.hardTrigger = h.trigger; dd.triggerFiredAt = h.firedAt
        let rel = domain.reliability(item: item)
        if !rel.isEmpty || h.trigger != nil {
            dd.reliability = rel; dd.reRatings = itemReRatings[item.id] ?? []; dd.asks = itemAsks[item.id] ?? []
            dd.voiOffered = domain.askNext(item: item); dd.hiddenTruth = domain.hiddenTruth(item: item)
        }
        decisions.append(dd)
        if h.link.answerType == .category {
            // simulated second reviewer (inter-rater consistency) for HITM-added categories
            let agreeP = ans.count <= 9 ? 0.45 : 0.8
            registry.recordUse(ans, link: h.link, reviewerAgrees: custom ? reviewerRng.chance(agreeP) : nil)
        }
        let ev = registry.evaluate()
        registryEvents.append(contentsOf: ev)
        if !ev.isEmpty || isNew { saveRegistry() }
        routed[id] = ans
        effective[item.id, default: [:]][h.link.id] = eff
        if h.trigger == nil && h.link.firesAlert && !trial && !h.link.alertNegative.contains(eff) {
            alertsFired += 1; domain.alertFired(item: item, link: h.link)
            if let ad = h.link.alertDest { destFor[id] = ad }
        }
        departFrom[id] = pos
        phase[id] = .outgoing; progress[id] = 0
        if ringFor == id { ringFor = nil }
        lastAction = "\(gesture) \(id): \(h.proposal)\(d.changed ? " → \(ans)" : " ✓")\(trial ? " (trial)" : "")"
            + (ev.last.map { " · \($0.op) \($0.category)" } ?? "")
        appendLog(dd)
    }

    // MARK: stats
    var stats: EngineStats {
        var s = EngineStats()
        s.completed = itemStatus.count; s.decisions = decisions.count
        s.corrections = decisions.filter(\.changed).count
        s.errorsPrevented = decisions.filter { $0.changed && $0.agreesWithGroundTruth == true }.count
        s.misses = decisions.filter { $0.agreesWithGroundTruth == false }.count
        s.alertsFired = alertsFired
        let l = decisions.map(\.latency).sorted(); s.medianLatency = l.isEmpty ? 0 : l[l.count / 2]
        let j = decisions.compactMap { d in d.groundTruth.map { $0 != d.proposedAnswer } }
        s.agentErrorRate = j.isEmpty ? 0 : Double(j.filter { $0 }.count) / Double(j.count)
        return s
    }
    struct Row: Identifiable { let id: String; let line: String; let steps: [(String, Bool, Bool, Bool)]; let status: String }
    var recentRows: [Row] {
        itemOrder.suffix(6).reversed().compactMap { id in
            guard let it = items[id] else { return nil }
            let steps = config.links.compactMap { l -> (String, Bool, Bool, Bool)? in
                guard let d = decisions.first(where: { $0.itemId == id && $0.linkId == l.id }) else { return nil }
                return (d.routedAnswer, d.changed, d.agreesWithGroundTruth ?? true, d.routedIsTrial)
            }
            let n = decisions.filter { $0.itemId == id }.count
            return Row(id: id, line: it.shortLine, steps: steps, status: itemStatus[id] ?? "in progress \(n)/\(config.links.count)")
        }
    }

    // MARK: logging / export
    private func enc() -> JSONEncoder { let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; e.outputFormatting = [.sortedKeys]; return e }
    private func appendLog(_ d: RoutingDecision) {
        guard var data = try? enc().encode(d) else { return }
        data.append(0x0A)
        if let f = try? FileHandle(forWritingTo: logURL) { f.seekToEndOfFile(); f.write(data); try? f.close() } else { try? data.write(to: logURL) }
    }
    func rewriteLog() {
        let dec = JSONDecoder(); dec.dateDecodingStrategy = .iso8601
        let text = (try? String(contentsOf: logURL, encoding: .utf8)) ?? ""
        let mine = Set(decisions.map(\.id))
        var all = text.split(separator: "\n").compactMap { try? dec.decode(RoutingDecision.self, from: Data($0.utf8)) }.filter { !mine.contains($0.id) }
        all.append(contentsOf: decisions)
        let e = enc()
        try? all.compactMap { try? e.encode($0) }.reduce(into: Data()) { $0.append($1); $0.append(0x0A) }.write(to: logURL)
    }
    var exportDir: URL { logURL.deletingLastPathComponent().appendingPathComponent("exports", isDirectory: true) }
    func export() {
        rewriteLog()
        try? FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)
        let ts = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        try? FileManager.default.copyItem(at: logURL, to: exportDir.appendingPathComponent("routing-\(ts).jsonl"))
        let e = enc(); e.outputFormatting = [.sortedKeys, .prettyPrinted]
        try? e.encode(decisions).write(to: exportDir.appendingPathComponent("routing-\(ts).json"))
        exportExtras(ts: ts)
        lastExport = "Exported \(decisions.count) decisions"
    }
    func exportExtras(ts: String) {
        let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; e.outputFormatting = [.sortedKeys, .prettyPrinted]
        try? e.encode(registry.history).write(to: exportDir.appendingPathComponent("registry-history-\(siteId)-\(ts).json"))
        try? e.encode(registry).write(to: exportDir.appendingPathComponent("registry-\(siteId)-\(ts).json"))
    }

    // MARK: test driver
    /// -testDocReview: re-rate a field (oracle = hidden truth state), send the top ask-next, hold panels for screenshots
    func testDocReview(_ k: Int, _ h: Handoff) async {
        if h.trigger != nil { try? await Task.sleep(for: .seconds(3)); return }   // let the red banner be seen, then ack via pass
        let rel = reliability(h)
        guard let low = rel.filter({ $0.ifWrong != nil }).max(by: { ($0.ifWrong!.riskHi) < ($1.ifWrong!.riskHi) }) else { return }
        if k % 4 == 1 || k == 6 {
            sideTab = "reliability"; if !detailOpen { toggleDetail() }
            try? await Task.sleep(for: .seconds(k == 6 ? 12 : 1.5))
            // oracle physician: re-rate the field whose hidden state differs from the system estimate
            if let m = rel.first(where: { $0.trueState != nil && $0.trueState != $0.state }) { rerate(h.id, field: m.field, to: m.trueState!) }
            try? await Task.sleep(for: .seconds(k == 6 ? 6 : 1))
        } else if k % 4 == 3 || k == 10, let q = askNextList(h).first {
            sideTab = "ask"; if !detailOpen { toggleDetail() }
            try? await Task.sleep(for: .seconds(k == 10 ? 10 : 1.5))
            ask(h.id, q)
            try? await Task.sleep(for: .seconds(k == 10 ? 8 : 1.5))
        } else if k == 14 {
            sideTab = "details"; if !detailOpen { toggleDetail() }
            for s in detailSections(h).map(\.title).prefix(5) { toggleSection(s) }
            try? await Task.sleep(for: .seconds(10))
        } else if detailOpen { toggleDetail() }
    }
    /// -testReview: exercise detail panel sections + spot-check queue (with holds for screenshots)
    func testReviewUI(_ k: Int) async {
        if ProcessInfo.processInfo.arguments.contains("-testDocReview"), let h = nowHandoff { await testDocReview(k, h); return }
        guard ProcessInfo.processInfo.arguments.contains("-testReview"), let h = nowHandoff else { return }
        let secs = detailSections(h).map(\.title)
        if k % 5 == 2 && !secs.isEmpty {
            if !detailOpen { toggleDetail() }
            let pick = k == 12 ? secs : Array(secs.prefix(1 + k % 3))
            for sct in pick { toggleSection(sct) }
            try? await Task.sleep(for: .seconds(k == 12 ? 14 : 1.2))
        } else if detailOpen { toggleDetail() }
        if k == 30 && !pendingSpotChecks.isEmpty {
            if detailOpen { toggleDetail() }
            spotCheckOpen = true; try? await Task.sleep(for: .seconds(6))
            for (i, d) in pendingSpotChecks.prefix(3).enumerated() { reviewSpotCheck(d.id, agree: i != 1); try? await Task.sleep(for: .seconds(1)) }
            try? await Task.sleep(for: .seconds(6)); spotCheckOpen = false
        }
    }
    /// Acts on waiting handoffs, highest priority first. Mostly routes to ground truth; every 9th is a blind pass.
    func autoResolve(_ n: Int) async {
        var k = 0
        while k < n {
            try? await Task.sleep(for: .seconds(Double(1.4 / speedup)))
            guard let h = nowHandoff, phase[h.id] == .waiting else { continue }
            await testReviewUI(k)
            let testNew = ProcessInfo.processInfo.arguments.contains("-testNewCategories")
            if testNew, h.link.answerType == .category, let names = config.testNewCategories[h.link.id], k % 3 == 1 {
                let name = names[testNameIdx % names.count]; testNameIdx += 1
                ringFor = h.id; try? await Task.sleep(for: .milliseconds(600))
                if registry.exists(name, link: h.link) { select(h.id, name) } else { selectNew(h.id, name) }
                // demonstrate a merge once a typo-variant exists
                if registry.exists("vert care", link: h.link), registry.exists("vertical care", link: h.link) {
                    mergeCategory("vert care", into: "vertical care", linkId: h.link.id)
                }
            }
            else if k % 9 == 8 { pass(h.id) }
            else if let gt = h.groundTruth, gt != h.proposal {
                if gt == config.review.escalateAnswer && h.link.id == config.review.escalationLink { escalate(h.id) }
                else if h.link.answerType == .binary { flip(h.id) }
                else { ringFor = h.id; try? await Task.sleep(for: .milliseconds(600)); select(h.id, gt) }
            } else { pass(h.id) }
            k += 1
        }
    }
}
