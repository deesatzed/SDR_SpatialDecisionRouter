import SwiftUI
#if os(visionOS)
import RealityKit

struct CrossroadsView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.openWindow) private var openWindow
    @State private var root = Entity()
    @State private var builtVersion = -1
    @State private var pulsed: [String: Date] = [:]
    @State private var lastBurst = ""

    var body: some View {
        let layoutToken = homeLayoutToken
        RealityView { content, att in
            content.add(root); buildStatic(att)
        } update: { _, att in
            if builtVersion != engine.packVersion { buildStatic(att) }
            sync(att)
        } attachments: {
            ForEach(engine.config.agents, id: \.id) { a in
                Attachment(id: "agent-\(a.id)") { AgentCard(agent: a, received: engine.inbox[a.id] ?? 0, queued: engine.queueCount(a.id)) }
            }
            Attachment(id: "now") { NowCard() }
            Attachment(id: "upnext") { UpNextStrip() }
            Attachment(id: "side") { SidePanel() }
            Attachment(id: "ring") { OptionRing() }
            Attachment(id: "board") { BoardView() }
            Attachment(id: "game") { if engine.domain.gameHUD() != nil { VStack(spacing: 8) { GameHUDStrip(); RevealBanner() } } }
            Attachment(id: "insights") { GameInsights() }
        }
        .task { while !Task.isCancelled { try? await Task.sleep(for: .milliseconds(50)); engine.tick(0.05) } }
        .onAppear { engine.immersiveOpen = true; uiLog.notice("immersive content appeared") }
        .onDisappear {   // closed by Close button, Digital Crown or system: bring the start window back
            engine.immersiveOpen = false; uiLog.notice("immersive content disappeared"); openWindow(id: "main")
        }
        .task {
            let a = ProcessInfo.processInfo.arguments
            if DemoState.on && DemoState.auto { try? await Task.sleep(for: .seconds(3)); await engine.demoPlay(); return }
            if let i = a.firstIndex(of: "-autoResolve"), i + 1 < a.count, let n = Int(a[i + 1]) {
                try? await Task.sleep(for: .seconds(2)); await engine.autoResolve(n)
                if a.contains("-autoExport") { engine.export() }
            }
        }
        .onChange(of: layoutToken) { _, _ in }
    }

    private func line(_ a: SIMD3<Float>, _ b: SIMD3<Float>, alpha: CGFloat = 0.22) -> Entity {
        let e = ModelEntity(mesh: .generateCylinder(height: simd_distance(a, b), radius: 0.003), materials: [UnlitMaterial(color: UIColor(white: 1, alpha: alpha))])
        e.position = (a + b) / 2; e.orientation = simd_quatf(from: [0, 1, 0], to: simd_normalize(b - a)); return e
    }

    private func place(_ att: RealityViewAttachments, _ id: String, _ p: SIMD3<Float>, _ sc: Float) {
        guard let e = att.entity(for: id) else { return }
        e.name = "att-\(id)"; e.position = p; e.scale = [sc, sc, sc]; e.components.set(BillboardComponent()); root.addChild(e)
    }

    private func buildStatic(_ att: RealityViewAttachments) {
        let cfg = engine.config
        guard cfg.agents.allSatisfy({ att.entity(for: "agent-\($0.id)") != nil }) else { return }
        for c in Array(root.children) { c.removeFromParent() }
        let env = ProceduralEnvironment.make(cfg.theme); env.isEnabled = engine.fullImmersion; root.addChild(env)
        let hub = ModelEntity(mesh: .generateSphere(radius: 0.02), materials: [UnlitMaterial(color: UIColor(white: 1, alpha: 0.6))])
        hub.position = RouterEngine.hub; root.addChild(hub)
        let home = cfg.id == "home_health"
        for (i, a) in cfg.agents.enumerated() {
            let p = engine.agentPosition(a.id)
            // Home spheres are solid work objects. Sync sizes them and lights the one that needs attention.
            let radius: Float = home ? homeSphereRadius : (a.tier == 0 ? 0.08 : 0.1)
            let node = ModelEntity(mesh: .generateSphere(radius: radius),
                                   materials: [SimpleMaterial(color: UIColor(hue: CGFloat(i) / CGFloat(cfg.agents.count + 1), saturation: 0.5, brightness: 0.9, alpha: 0.55), isMetallic: false)])
            node.position = p; node.name = "agent-\(a.id)"; root.addChild(node)
            if home {
                node.scale = SIMD3(repeating: nodeRestScale(a.id))
                let halo = ModelEntity(mesh: .generateSphere(radius: homeSphereRadius * 1.62),
                                        materials: [UnlitMaterial(color: UIColor(white: 1, alpha: 0))])
                halo.name = "halo"; halo.isEnabled = false; node.addChild(halo)
            }
            root.addChild(line(p, RouterEngine.hub, alpha: home ? 0.07 : 0.22))
            if let card = att.entity(for: "agent-\(a.id)") {
                let sc: Float = home ? 1.7 : 1.4
                let dy: Float = home ? homeLabelOffset(a, nodeRestScale(a.id)) : (a.tier == 0 ? -0.2 : 0.24)
                card.name = home ? "label-\(a.id)" : "att-agent-\(a.id)"
                card.position = p + [0, dy, home ? 0.06 : 0]; card.scale = [sc, sc, sc]
                card.components.set(BillboardComponent()); root.addChild(card)
            }
        }
        if home {
            place(att, "board", [-1.15, 1.78, -1.72], 1.38)
            place(att, "now", [0, 1.50, -1.18], 1.40)
            place(att, "upnext", [1.22, 1.42, -1.70], 1.32)
        } else {
            place(att, "board", [0, 2.45, -2.05], 1.3)
            place(att, "now", RouterEngine.nowCard, 1.5)
            place(att, "upnext", RouterEngine.upNextPos, 1.15)
        }
        place(att, "game", RouterEngine.nowCard + [0, 0.52, 0.02], 1.2)
        place(att, "insights", [0, 0.62, -1.4], 1.0)
        place(att, "side", RouterEngine.sidePos, 1.15)
        if let r = att.entity(for: "ring") { r.name = "ringAttachment"; r.isEnabled = false; r.position = [0, 1.02, -1.28]; r.components.set(BillboardComponent()); root.addChild(r) }   // ring below the Now card: never covers its text
        let v = engine.packVersion
        Task { @MainActor in builtVersion = v; pulsed = [:] }
    }

    private func sync(_ att: RealityViewAttachments) {
        let cfg = engine.config
        for h in engine.handoffs {
            if engine.phase[h.id] == .delivered { root.findEntity(named: h.id)?.removeFromParent(); continue }
            var e = root.findEntity(named: h.id)
            if e == nil {
                let hue = CGFloat(engine.agentIndex(h.link.source)) / CGFloat(cfg.agents.count + 1)
                let m = ModelEntity(mesh: h.link.answerType == .binary ? .generateBox(size: 0.06, cornerRadius: 0.015) : .generateSphere(radius: 0.04),
                                    materials: [SimpleMaterial(color: UIColor(hue: hue, saturation: 0.25 + 0.7 * CGFloat(h.confidence), brightness: 1, alpha: 0.9), isMetallic: false)])
                m.name = h.id; root.addChild(m); e = m
            }
            e?.position = engine.position(h)
            let s: Float = h.id == engine.nowId ? 1.6 : 1
            e?.scale = [s, s, s]
        }
        for (agent, t) in engine.lastDelivered where pulsed[agent] != t {
            if let n = root.findEntity(named: "agent-\(agent)") {
                let rest = nodeRestScale(agent)
                let peak: Float = engine.config.id == "home_health" ? rest * 1.55 : 1.8
                let back: Float = engine.config.id == "home_health" ? rest : 1
                var big = n.transform; big.scale = [peak, peak, peak]; n.move(to: big, relativeTo: root, duration: 0.18)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { var s = n.transform; s.scale = [back, back, back]; n.move(to: s, relativeTo: root, duration: 0.35) }
            }
            Task { @MainActor in pulsed[agent] = t }
        }
        if let r = engine.reveal, r.id != lastBurst, engine.gameMode {   // predict-then-reveal: particle burst at the Now card
            let e = Entity(); var pe = ParticleEmitterComponent.Presets.sparks
            pe.mainEmitter.color = .constant(.single(r.hit == true ? .green : r.hit == false ? .red : .gray))
            pe.emitterShape = .sphere; pe.burstCount = 400; pe.isEmitting = false; pe.burst()
            e.components.set(pe); e.position = RouterEngine.nowCard + [0, 0.05, 0.1]; root.addChild(e)
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { e.removeFromParent() }
            Task { @MainActor in lastBurst = r.id }
        }
        root.findEntity(named: "environment")?.isEnabled = engine.fullImmersion
        let homeDossier = engine.config.id == "home_health" && engine.homeShownLevel > 0
        root.findEntity(named: "att-side")?.isEnabled = engine.detailOpen || engine.spotCheckOpen || homeDossier
        root.findEntity(named: "ringAttachment")?.isEnabled = engine.ringFor != nil
        if engine.config.id == "home_health" {
            layoutHomeFocus()
            layoutHomeNodes()
        } else if let b = root.findEntity(named: "att-board") {   // Enlarge: ~2x, closer and lower; Shrink: overhead
            let big = engine.boardLarge
            let p: SIMD3<Float> = big ? [0, 2.40, -1.75] : [0, 2.45, -2.05], sc: Float = big ? 2.0 : 1.3
            moveAtt(b, p, sc)
        }
    }

    /// Read during body so a Show/Hide tap moves the attachments. The update closure alone is not observed.
    private var homeLayoutToken: String {
        let h = engine.nowHandoff
        let dest = h.map { engine.highlightedDest($0) } ?? ""
        let moving = engine.handoffs.map { engine.phase[$0.id] == .outgoing ? "1" : "0" }.joined()
        let load = engine.config.agents.map { "\($0.id):\(engine.queueCount($0.id)):\(engine.inbox[$0.id] ?? 0)" }.joined(separator: ",")
        return "\(engine.config.id)|\(engine.focusStatusOpen)|\(engine.focusQueueOpen)|\(engine.detailOpen)|\(engine.homeShownLevel)|\(h?.id ?? "")|\(h?.proposal ?? "")|\(dest)|\(engine.stats.alertsFired)|\(engine.stats.corrections)|\(engine.packVersion)|\(moving)|\(load)|\(engine.homeSphereOpen ?? "")"
    }

    /// Mesh radius for a home-health work sphere, before `nodeRestScale`.
    private let homeSphereRadius: Float = 0.16

    /// Queue load and route urgency. Idle destinations stay solid, just smaller.
    private func nodeRestScale(_ id: String) -> Float {
        guard engine.config.id == "home_health", let a = engine.agent(id) else { return 1 }
        if a.tier == 0 {
            let n = Float(engine.queueCount(id))
            return min(2.45, 1.35 + 0.16 * n)
        }
        let received = Float(engine.inbox[id] ?? 0)
        if let route = attentionRoute(for: id) {
            let base: Float
            switch route {
            case "urgent_page": base = 2.2
            case "provider_task": base = 1.85
            case "nurse_task": base = 1.65
            case "silent_log": base = 1.4
            default: base = 1.55
            }
            return min(2.55, base + 0.04 * received)
        }
        return min(1.2, 0.95 + 0.06 * received)
    }

    /// The open case, or a Pass already in flight, is what makes a destination glow.
    private func attentionRoute(for id: String) -> String? {
        if let h = engine.nowHandoff, engine.highlightedDest(h) == id { return h.proposal }
        return engine.handoffs.first {
            engine.phase[$0.id] == .outgoing && (engine.destFor[$0.id] ?? $0.link.dest) == id
        }?.proposal
    }

    private func homeLabelOffset(_ a: AgentSpec, _ scale: Float) -> Float {
        let gap = homeSphereRadius * scale + 0.36
        return a.tier == 0 ? -gap : gap
    }

    private struct SpherePaint {
        var body: UIColor
        var halo: UIColor
        var haloAlpha: CGFloat
        var haloScale: Float
    }

    /// Solid body. Halo only when this sphere needs a look: a waiting queue, or the destination of this Pass.
    private func spherePaint(_ a: AgentSpec, route: String?) -> SpherePaint {
        if a.tier == 0 {
            let teal = UIColor(red: 0.10, green: 0.78, blue: 0.74, alpha: 1)
            let waiting = engine.queueCount(a.id) > 0
            return SpherePaint(body: teal, halo: teal, haloAlpha: waiting ? 0.40 : 0, haloScale: 1)
        }
        guard let route else {
            return SpherePaint(body: UIColor(red: 0.58, green: 0.64, blue: 0.72, alpha: 1), halo: .white, haloAlpha: 0, haloScale: 1)
        }
        switch route {
        case "urgent_page":
            let c = UIColor(red: 0.96, green: 0.18, blue: 0.16, alpha: 1)
            return SpherePaint(body: c, halo: c, haloAlpha: 0.55, haloScale: 1.2)
        case "silent_log":
            let c = UIColor(red: 0.16, green: 0.74, blue: 0.58, alpha: 1)
            return SpherePaint(body: c, halo: c, haloAlpha: 0.34, haloScale: 1)
        default:
            let c = UIColor(red: 0.98, green: 0.58, blue: 0.12, alpha: 1)
            return SpherePaint(body: c, halo: c, haloAlpha: 0.44, haloScale: 1.08)
        }
    }

    private func moveAtt(_ e: Entity, _ p: SIMD3<Float>, _ sc: Float) {
        if simd_distance(e.position, p) > 0.001 || abs(e.scale.x - sc) > 0.001 {
            var t = e.transform; t.translation = p; t.scale = [sc, sc, sc]
            e.move(to: t, relativeTo: root, duration: 0.35)
        }
    }

    /// A: decision stays near. Status and queue sit mid-field until Show.
    private func layoutHomeFocus() {
        let dossier = engine.homeShownLevel > 0
        let statusOpen = engine.focusStatusOpen && !engine.detailOpen && !dossier
        let queueOpen = engine.focusQueueOpen
        let attention = engine.stats.alertsFired > 0 || engine.stats.corrections > 0
        if let e = root.findEntity(named: "att-now") { moveAtt(e, [0, 1.50, -1.18], 1.40) }
        if let e = root.findEntity(named: "att-board") {
            if dossier { moveAtt(e, [0, 2.08, -1.92], 1.22) }
            else if statusOpen { moveAtt(e, [-1.25, 1.62, -1.50], 1.48) }
            else { moveAtt(e, [-1.15, 1.78, -1.72], attention ? 1.55 : 1.38) }
        }
        if let e = root.findEntity(named: "att-upnext") {
            if queueOpen { moveAtt(e, [1.05, 1.40, -1.38], 1.40) }
            else { moveAtt(e, [1.22, 1.42, -1.70], 1.32) }
        }
        if let e = root.findEntity(named: "ringAttachment") { moveAtt(e, [0, 0.88, -1.15], 1.15) }
        if let e = root.findEntity(named: "att-side") {
            if engine.homeShownLevel > 0 { moveAtt(e, [-1.22, 1.46, -1.18], 1.30) }
            else if engine.detailOpen { moveAtt(e, [-0.98, 1.46, -1.22], 1.32) }
            else { moveAtt(e, RouterEngine.sidePos, 1.15) }
        }
    }

    /// Work objects. Size follows queue load or the urgency of this Pass. Glow means look here.
    private func layoutHomeNodes() {
        let cfg = engine.config
        for a in cfg.agents {
            guard let n = root.findEntity(named: "agent-\(a.id)") as? ModelEntity else { continue }
            let want = nodeRestScale(a.id)
            let recent = pulsed[a.id].map { Date().timeIntervalSince($0) < 0.75 } ?? false
            if !recent, abs(n.scale.x - want) > 0.04 { n.scale = [want, want, want] }
            let route = attentionRoute(for: a.id)
            let paint = spherePaint(a, route: route)
            if var model = n.model {
                model.materials = [UnlitMaterial(color: paint.body)]
                n.model = model
            }
            if let halo = n.findEntity(named: "halo") as? ModelEntity {
                halo.isEnabled = paint.haloAlpha > 0.02
                if var model = halo.model {
                    model.materials = [UnlitMaterial(color: paint.halo.withAlphaComponent(paint.haloAlpha))]
                    halo.model = model
                }
                halo.scale = SIMD3(repeating: paint.haloScale)
            }
            if let card = root.findEntity(named: "label-\(a.id)") {
                let dy = homeLabelOffset(a, want)
                moveAtt(card, n.position + [0, dy, 0.06], 1.7)
            }
        }
    }
}

#endif

/// Glossary-backed hover: highlight + tooltip.
struct Gloss: ViewModifier {
    @Environment(RouterEngine.self) private var engine
    let key: String
    func body(content: Content) -> some View {
        content.contentShape(.hoverEffect, RoundedRectangle(cornerRadius: 8)).hoverEffect(.highlight)
            .help(engine.config.glossary[key] ?? engine.config.glossary[key.lowercased()] ?? key)
    }
}
extension View { func gloss(_ k: String) -> some View { modifier(Gloss(key: k)) } }

struct Chip: View {
    let r: ReasonChip
    var body: some View {
        let c: Color = r.severity == .high ? .red : r.severity == .warn ? .orange : .teal
        Text(r.text).font(.callout.bold()).lineLimit(1).padding(.horizontal, 9).padding(.vertical, 3)
            .background(c.opacity(0.5), in: Capsule()).gloss(r.key)
    }
}

struct AgentCard: View {
    #if os(visionOS)
    @Environment(RouterEngine.self) private var engine
    #endif
    let agent: AgentSpec; let received: Int; let queued: Int
    var body: some View {
        #if os(visionOS)
        if engine.config.id == "home_health" { homeNode } else { classic }
        #else
        classic
        #endif
    }
    #if os(visionOS)
    @State private var looking = false
    /// Nameplate readable at distance: site plus count. Look or Show list opens who is waiting or who was sent.
    private var homeNode: some View {
        let pinned = engine.homeSphereOpen == agent.id
        let open = looking || pinned
        let sent = engine.inbox[agent.id] ?? 0
        let count = agent.tier == 0 ? "\(queued) waiting" : "\(sent) sent"
        let passHere = passRoute
        let nowFields = passFields
        let lines = waitLines
        return VStack(alignment: .leading, spacing: 8) {
            Text("\(agent.name) · \(count)")
                .font(.sdrHuge.bold())
                .lineLimit(1)
                .minimumScaleFactor(0.45)
                .frame(maxWidth: 520, alignment: .leading)
            if let passHere {
                Text("This pass · \(HomeHealthSeat.recipientChip(route: passHere, fields: nowFields))")
                    .font(.title.bold())
                    .foregroundStyle(rim)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .frame(maxWidth: 520, alignment: .leading)
            }
            if open {
                Text(agent.tier == 0 ? "Waiting on you" : "Pass sends here. You are not the recipient.")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .frame(maxWidth: 460, alignment: .leading)
                if lines.isEmpty {
                    Text(agent.tier == 0 ? "Queue is clear" : "Nothing sent here yet")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    Text(line).font(.title3).lineLimit(2).frame(maxWidth: 460, alignment: .leading)
                }
            }
            Button(pinned ? "Hide list" : "Show list") { engine.homeSphereToggle(agent.id) }
                .font(.title2.bold())
                .tint(.teal)
        }
        .padding(16)
        .sdrPanel()
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(rim, lineWidth: passRoute != nil || (agent.tier == 0 && queued > 0) ? 4 : 1.5))
        .onContinuousHover { phase in
            switch phase {
            case .ended: looking = false
            default: looking = true
            }
        }
    }
    /// Route that currently lights this destination: the open case, or a Pass in flight.
    private var passRoute: String? {
        guard agent.tier != 0 else { return nil }
        if let h = engine.nowHandoff, engine.highlightedDest(h) == agent.id { return h.proposal }
        return engine.handoffs.first {
            engine.phase[$0.id] == .outgoing && (engine.destFor[$0.id] ?? $0.link.dest) == agent.id
        }?.proposal
    }
    private var passFields: [String: String] {
        if let h = engine.nowHandoff, engine.highlightedDest(h) == agent.id {
            return engine.items[h.itemId]?.fields ?? [:]
        }
        if let h = engine.handoffs.first(where: {
            engine.phase[$0.id] == .outgoing && (engine.destFor[$0.id] ?? $0.link.dest) == agent.id
        }) {
            return engine.items[h.itemId]?.fields ?? [:]
        }
        return [:]
    }
    private var rim: Color {
        if agent.tier == 0 { return queued > 0 ? .teal : Color.white.opacity(0.35) }
        guard let route = passRoute else { return Color.white.opacity(0.35) }
        switch route {
        case "urgent_page": return .red
        case "silent_log": return .teal
        default: return .orange
        }
    }
    private var waitLines: [String] {
        if agent.tier == 0 {
            return engine.waiting.prefix(4).map { h in
                let fields = engine.items[h.itemId]?.fields ?? [:]
                return "\(h.itemId) · \(HomeHealthRoute.title(h.proposal)) · \(HomeHealthSeat.recipientChip(route: h.proposal, fields: fields))"
            }
        }
        return engine.decisions
            .filter { $0.domain == "home_health" && HomeHealthSeat.deskId(for: $0.effectiveAnswer) == agent.id }
            .suffix(4)
            .reversed()
            .map { d in "\(d.itemId) · \(HomeHealthSeat.recipientChip(route: d.effectiveAnswer, fields: d.context))" }
    }
    #endif
    private var classic: some View {
        HStack(spacing: 8) {
            VStack(spacing: 1) {
                Text(agent.name).font(.headline)
                if let r = agent.role { Text(r).font(.caption).foregroundStyle(.secondary) }
                if agent.tier == 1 { Text("received \(received)").font(.caption.monospacedDigit()) }
            }
            if agent.tier == 0 {
                Text("\(queued)").font(.title3.bold().monospacedDigit()).frame(minWidth: 30).padding(4)
                    .background(queued > 0 ? Color.orange.opacity(0.8) : Color.white.opacity(0.15), in: Circle()).help("items from this agent waiting in the review queue")
            }
        }.padding(8).sdrPanel().opacity(0.85)
    }
}

/// The single large decision card (top of the review queue).
struct NowCard: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            if let h = engine.nowHandoff { content(h) }
            else {
                VStack(spacing: 14) {
                    Text(DemoState.on && engine.domain.isDemoDone ? "Demo complete · \(engine.autoPassed) auto-passed · Reset demo to replay" : "Queue clear · \(engine.autoPassed) auto-passed").font(.title)
                    if engine.domain is SymbiosisDomain { HStack { PromotionButton(); LineageButton() }.font(.title3.bold()) }
                }.padding(30).sdrWidth(880).sdrPanel()
            }
        }
    }
    static func badgeFill(_ b: String) -> Color {
        if b.hasPrefix("BN") { return .indigo }
        if b.hasPrefix("L1 live") { return .teal }
        if b.hasPrefix("L1 bundled") { return .orange }
        return Color.gray.opacity(0.6)
    }
    static func badgeKey(_ b: String) -> String {
        if b.hasPrefix("BN") { return "BN" }
        if b.hasPrefix("L1") { return "Layer 1" }
        return "fallback"
    }
    @ViewBuilder func content(_ h: Handoff) -> some View {
        if let item = engine.items[h.itemId], item.fields["home_health"] == "1" {
            HomeHealthNowFace(handoff: h, item: item)
        } else {
            legacyNow(h)
        }
    }
    @ViewBuilder func legacyNow(_ h: Handoff) -> some View {
        let item = engine.items[h.itemId], t = engine.config.terminology
        let src = engine.agent(h.link.source)?.name ?? h.link.source, dst = engine.agent(h.link.dest)?.name ?? h.link.dest
        let reasons = engine.reasons(h)
        let rel = engine.reliability(h)
        VStack(alignment: .leading, spacing: 10) {
            if DemoState.on, let item, let cap = engine.domain.demoCaption(item: item) {
                Text("DEMO \(cap)").font(.title3.bold()).foregroundStyle(.black).padding(.horizontal, 10).padding(.vertical, 4)
                    .background(.yellow, in: RoundedRectangle(cornerRadius: 8)).gloss("DEMO")
            }
            if let t = h.trigger {
                HStack {
                    Text("⚠ HARD ESCALATION — \(t)").font(.title2.bold()).foregroundStyle(.white)
                    Spacer()
                    Text("fired \(h.firedAt.map { Int(Date().timeIntervalSince($0)) } ?? 0)s ago · reliability analysis bypassed").font(.headline)
                }.padding(10).background(.red, in: RoundedRectangle(cornerRadius: 10)).gloss("hard trigger")
            }
            HStack {
                Text("NOW").font(.headline.bold()).padding(.horizontal, 8).background(.blue, in: Capsule())
                Text("\(src) → \(dst) · \(h.itemId)").font(.title3).foregroundStyle(.secondary)
                Spacer()
                if let item = engine.items[h.itemId], let b = engine.domain.riskBadge(item: item) {
                    Text(b).font(.headline.bold()).padding(.horizontal, 8).padding(.vertical, 2)
                        .background(Self.badgeFill(b), in: Capsule()).gloss(Self.badgeKey(b))
                }
                Text(String(format: "priority %.2f", engine.livePriority(h))).font(.headline.monospacedDigit()).gloss("priority")
                if engine.livePriority(h) >= 1.0 { Text("⚑").font(.title2).foregroundStyle(.red).gloss("priority") }
            }
            Text(item?.displayLine ?? "").font(.title2).lineLimit(2).gloss("ESI")
            Text("\(t.historyLabel): \(item?.historyLine ?? "none")").font(.title3).foregroundStyle(.yellow).lineLimit(1).gloss("PMH")
            if item?.fields["showCapacity"] != "no" {
                Text("\(t.capacityLabel): \(h.capacityLine)").font(.headline).foregroundStyle(.cyan).lineLimit(1).gloss("census")
            }
            let sharp = engine.isSharp(h)
            if !reasons.isEmpty && !sharp {
                VStack(alignment: .leading, spacing: 4) {
                    Text("WHY QUEUED").font(.caption.bold()).foregroundStyle(.secondary)
                    #if os(visionOS)
                    ForEach(Array(stride(from: 0, to: reasons.count, by: 3)), id: \.self) { i in
                        HStack(spacing: 6) { ForEach(reasons[i..<min(i + 3, reasons.count)], id: \.self) { Chip(r: $0) } }
                    }
                    #else
                    FlowRow { ForEach(reasons, id: \.self) { Chip(r: $0) } }
                    #endif
                }
            }
            if !rel.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("TRUST IN KEY ANSWERS").font(.caption.bold()).foregroundStyle(.secondary).gloss("reliability score")
                    let keys = Array(rel.filter(\.key).prefix(6))
                    #if os(visionOS)
                    ForEach(Array(stride(from: 0, to: keys.count, by: 3)), id: \.self) { i in
                        HStack(spacing: 6) { ForEach(keys[i..<min(i + 3, keys.count)]) { r in RelChip(r: r) } }
                    }
                    #else
                    FlowRow { ForEach(keys) { r in RelChip(r: r) } }
                    #endif
                    Text("% safe = chance the answer is true · said differently = likely held back on purpose · said wrong = honest mistake · not said = never asked")
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.7)
                    if let w = rel.compactMap({ f in f.ifWrong.map { (f, $0) } }).max(by: { $0.1.riskHi < $1.1.riskHi }) {
                        Text("IF WRONG · \(w.0.field): “\(w.0.stated)” → \(w.1.alternative): risk \(Int((w.1.riskLo * 100).rounded()))–\(Int((w.1.riskHi * 100).rounded()))% · worst: \(w.1.worstMiss) · plan: \(w.1.planChange)")
                            .font(.headline).foregroundStyle(.pink).lineLimit(2).gloss("if wrong")
                    }
                    if let a = engine.lastAnswer[h.itemId] { Text("last answer · \(a)").font(.headline).foregroundStyle(.mint) }
                }
            }
            if let item, item.fields["symbiosis"] == "1" {
                SymbiosisPanel(item: item)
                HStack { ManifestoButton(); PromotionButton(); LineageButton() }
            }
            if sharp { YourCallFirst(h: h) } else {
            HStack(alignment: .firstTextBaseline) {
                Text(h.link.question).font(.title)
                Text(h.proposal).font(.sdrHuge.bold())
                Text("\(Int(h.confidence * 100))%").font(.title2.monospacedDigit()).foregroundStyle(h.confidence < 0.7 ? .orange : .secondary).gloss("confidence")
                Spacer()
            }
            VStack(alignment: .leading, spacing: 3) {
                Text("WHAT HAPPENS NEXT").font(.caption.bold()).foregroundStyle(.secondary).gloss("what happens next")
                Text("Pass → \(h.preview)").font(.title3).foregroundStyle(.green)
                if let alt = h.altPreview { Text("Flip → \(alt)").font(.title3).foregroundStyle(.orange) }
                else if h.link.answerType == .category { Text("Change… → pick another \(h.link.shortLabel ?? "option") (preview on hover)").font(.headline).foregroundStyle(.blue) }
            }
            ActionRow {
                Button(h.trigger != nil ? "Acknowledge ✓" : (h.link.id == engine.config.review.escalationLink ? "Sign off ✓" : "Pass ✓")) { engine.pass(h.id) }.tint(.green)
                if h.link.answerType == .binary { Button("Flip") { engine.flip(h.id) }.tint(.orange) }
                else if h.trigger == nil { Button("Modify…") { engine.openRing(h.id) }.tint(.blue) }
                if h.trigger == nil && h.link.id == engine.config.review.escalationLink {
                    Button("Escalate") { engine.escalate(h.id) }.tint(.red)
                }
                #if os(visionOS)
                Spacer()
                #endif
                if !rel.isEmpty {
                    Button { engine.sideTab = "reliability"; if !engine.detailOpen { engine.toggleDetail() } } label: { Text("Rate trust").lineLimit(1).fixedSize() }.tint(.purple)
                    Button("Ask next") { engine.sideTab = "ask"; if !engine.detailOpen { engine.toggleDetail() } }.tint(.teal)
                }
                Button(engine.detailOpen ? "ⓘ Hide" : "ⓘ Details") { engine.sideTab = "details"; engine.toggleDetail() }.tint(.gray)
            }.font(.title2.bold())
            }
        }
        .sdrWidth(880).padding(22).sdrPanel()
    }
}

struct ActionRow<C: View>: View {
    @ViewBuilder var content: C
    var body: some View {
        #if os(visionOS)
        HStack(spacing: 14) { content }
        #else
        FlowRow(spacing: 12) { content }
        #endif
    }
}

/// human-readable field names for chips
func fieldLabel(_ f: String) -> String {
    let m = ["nitrate_use": "nitrates", "alpha_blocker": "alpha-blocker", "exertional_cp": "chest pain on exertion", "recreational_drugs": "recreational drugs",
             "meds": "medications", "mtc_men2": "family thyroid cancer", "pancreatitis_hx": "pancreatitis history", "eating_disorder": "eating disorder",
             "hypoglycemic_meds": "insulin / sulfonylurea", "inflated_bmi": "measured weight", "fertility_desire": "fertility plans", "high_hct": "hematocrit",
             "untreated_osa": "sleep apnea", "prostate_issue": "prostate / PSA", "cv_risk_high": "heart disease", "not_confirmed_low": "confirmed low T",
             "airway_red_flag": "airway red flags", "nonadherent": "adherence", "overdue_monitoring": "monitoring labs", "controlled_misuse": "controlled-drug use",
             "new_interaction": "new medicines", "masked_symptom": "new symptoms", "hormone_cancer": "breast / uterine cancer", "vte_stroke_hx": "clots / stroke",
             "unexplained_bleeding": "post-menopause bleeding", "migraine_aura": "migraine aura", "liver_disease": "liver disease", "late_start": "timing since menopause"]
    return m[f] ?? f.replacingOccurrences(of: "_", with: " ")
}
func relColor(_ s: ReliabilityState) -> Color {
    switch s { case .reliable: .green; case .notSaid: .gray; case .saidWrong: .orange; case .saidDifferently: .purple }
}
struct RelChip: View {
    let r: FieldReliability
    var body: some View {
        Text(r.state == .notSaid ? "\(fieldLabel(r.field)) · not said" : "\(fieldLabel(r.field)) · \(r.state.spoken) · \(Int((r.score * 100).rounded()))% safe")
            .font(.callout.bold()).lineLimit(1).fixedSize().padding(.horizontal, 8).padding(.vertical, 3)
            .background(relColor(r.state).opacity(0.55), in: Capsule()).gloss(r.state.rawValue)
    }
}

/// Per-field reliability with 4-state re-rating and if-wrong risk.
struct ReliabilityPanel: View {
    @Environment(RouterEngine.self) private var engine
    let h: Handoff
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack { Text("Reliability · \(h.itemId)").font(.title2.bold()).gloss("reliability score"); Spacer()
                     Text("R N W D = re-rate").font(.caption).foregroundStyle(.secondary).gloss("re-rate") }
            let rl = engine.reliability(h).sorted { ($0.state == .reliable ? 1 : 0, $0.key ? 0 : 1) < ($1.state == .reliable ? 1 : 0, $1.key ? 0 : 1) }
            let shown = rl.filter { $0.state != .reliable || $0.ifWrong != nil }
            let hidden = rl.count - shown.count
            ForEach(shown) { r in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(r.field + (r.key ? " ★" : "")).font(.headline).frame(width: 110, alignment: .leading)
                        Text("“\(r.stated)”").font(.callout).lineLimit(1).frame(width: 130, alignment: .leading)
                        Text("\(Int(r.score * 100))%").font(.callout.monospacedDigit()).frame(width: 44)
                        ForEach(ReliabilityState.allCases, id: \.self) { st in
                            Button(st.short) { engine.rerate(h.id, field: r.field, to: st) }
                                .font(.caption.bold()).tint(r.state == st ? relColor(st) : .gray.opacity(0.4)).gloss(st.rawValue)
                        }
                    }
                    Text(r.state.rawValue + " · " + r.why.prefix(3).joined(separator: " · ")).font(.callout).foregroundStyle(relColor(r.state))
                    if !r.notAsked.isEmpty { Text("☐ not asked: " + r.notAsked.joined(separator: "; ")).font(.callout).foregroundStyle(.secondary) }
                    if let w = r.ifWrong {
                        Text("if wrong → \(w.alternative): risk \(Int((w.riskLo * 100).rounded()))–\(Int((w.riskHi * 100).rounded()))% · worst \(w.worstMiss) · \(w.planChange) · ddx \(w.ddxShift)")
                            .font(.callout.bold()).foregroundStyle(.pink).gloss("if wrong")
                    }
                }
            }
            if hidden > 0 { Text("+ \(hidden) reliable field\(hidden == 1 ? "" : "s") (no if-wrong risk): " + rl.filter { $0.state == .reliable && $0.ifWrong == nil }.map(\.field).joined(separator: ", "))
                .font(.callout).foregroundStyle(.green) }
        }
    }
}

/// (reliable fields without if-wrong risk are collapsed into one line)
/// Top-3 value-of-information questions; send one.
struct AskNextPanel: View {
    @Environment(RouterEngine.self) private var engine
    let h: Handoff
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Ask next · \(h.itemId)").font(.title2.bold()).gloss("ask next")
            let qs = engine.askNextList(h)
            if qs.isEmpty { Text("no high-value questions left").foregroundStyle(.secondary) }
            ForEach(qs) { q in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(String(format: "VOI %.2f", q.voi)).font(.headline.monospacedDigit()).foregroundStyle(.teal).gloss("VOI")
                        Text(q.field).font(.headline)
                        Spacer()
                        Button("Send") { engine.ask(h.id, q) }.tint(.teal)
                    }
                    Text(q.text).font(.callout)
                    Text(q.rationale).font(.callout).foregroundStyle(.secondary)
                }
            }
            ForEach(Array((engine.itemAsks[h.itemId] ?? []).enumerated()), id: \.offset) { _, a in
                Text("✉ \(a.field) → \(a.answer)").font(.callout).foregroundStyle(.mint)
            }
            if engine.reasons(h).contains(where: { $0.key == "recommend escalation" }) {
                Text("Critical miss not excluded and info unreliable → recommend Escalate").font(.headline).foregroundStyle(.red).gloss("recommend escalation")
            }
        }
    }
}

struct UpNextStrip: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            if engine.config.id == "home_health" { homeQueue(engine.queue) }
            else { classicQueue(engine.queue) }
        }
    }
    /// Mid-right layer: a few fat chips. Priority and the wait chip stay off this face.
    private func homeQueue(_ q: [Handoff]) -> some View {
        #if os(visionOS)
        let open = engine.focusQueueOpen
        #else
        let open = true
        #endif
        return VStack(alignment: .leading, spacing: 12) {
            Button { engine.focusQueueOpen.toggle() } label: {
                HStack(spacing: 12) {
                    Text(open ? "Up next" : "Queue").font(.title.bold())
                    Spacer()
                    Text("\(q.count)").font(.system(size: 36, weight: .bold)).monospacedDigit()
                    #if os(visionOS)
                    Text(open ? "Hide" : "Show").font(.title2).foregroundStyle(.secondary)
                    #endif
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel(open ? "Hide queue" : "Show queue")
            ForEach(q.prefix(4)) { h in
                Button { engine.makeNow(h.id) } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 12) {
                            Text(h.itemId).font(.system(size: 28, weight: .bold)).lineLimit(1)
                            Spacer(minLength: 8)
                            HomeHealthRouteChip(route: h.proposal, prominent: false)
                        }
                        if open {
                            let why = HomeHealthBrief.hook(engine.items[h.itemId]?.fields ?? [:])
                            if !why.isEmpty {
                                Text(why).font(.title3).foregroundStyle(.secondary).lineLimit(2)
                            }
                            let ticket = engine.items[h.itemId]?.fields["ticket_type"] ?? "none"
                            if ticket != "none" {
                                Text("Device ticket").font(.title3.bold()).foregroundStyle(.orange)
                            }
                            let who = HomeHealthSeat.recipientChip(route: h.proposal, fields: engine.items[h.itemId]?.fields ?? [:])
                            Text("to \(who)").font(.title3).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                    .padding(.vertical, 10)
                    .padding(.horizontal, 6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.bordered)
            }
            if q.count > 4 { Text("+\(q.count - 4) more").font(.title2).foregroundStyle(.secondary) }
        }
        .sdrWidth(open ? 560 : 500)
        .padding(18)
        .sdrPanel()
        .opacity(open ? 1 : 0.92)
    }
    private func classicQueue(_ q: [Handoff]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Up next").font(.title2.bold())
                Spacer()
                Text("\(q.count) queued").font(.headline.monospacedDigit()).gloss("priority")
            }
            HStack(spacing: 10) {
                Text("auto-passed \(engine.autoPassed)").gloss("auto-pass")
                Button("spot-check \(engine.pendingSpotChecks.count)") { engine.spotCheckOpen.toggle(); if engine.detailOpen { engine.toggleDetail() } }
                    .gloss("spot-check")
            }.font(.callout)
            ForEach(q.prefix(engine.config.review.upNextCount)) { h in
                Button { engine.makeNow(h.id) } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            if h.trigger != nil { Text("⚠").foregroundStyle(.red).font(.headline) }
                            Text("\(h.itemId) · \(h.link.shortLabel ?? h.link.id)").font(.headline)
                            Spacer()
                            if engine.nowHandoff.map(engine.isSharp) == true { Text("AI pick hidden").font(.caption).foregroundStyle(.secondary) }
                            else { Text("\(h.proposal) \(Int(h.confidence * 100))%").font(.headline.monospacedDigit()) }
                            Text(String(format: "%.2f", engine.livePriority(h))).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        }
                        if let r = engine.reasons(h).max(by: { $0.severity.rawValue < $1.severity.rawValue }) { Chip(r: r) }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(.bordered)
            }
            if q.count > engine.config.review.upNextCount { Text("+\(q.count - engine.config.review.upNextCount) more").font(.callout).foregroundStyle(.secondary) }
        }
        .sdrWidth(470).padding(16).sdrPanel()
    }
}

/// Beside the Now card: detail sections, or the spot-check queue.
struct SidePanel: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        if engine.config.id == "home_health", engine.homeShownLevel > 0, let h = engine.nowHandoff, let item = engine.items[h.itemId] {
            homeCascade(item)
        } else {
            TimelineView(.periodic(from: .now, by: 1)) { _ in
                ScrollView(.vertical) { Group {
                    if engine.spotCheckOpen { spot }
                    else if let h = engine.nowHandoff {
                        if engine.sideTab == "reliability" && !engine.reliability(h).isEmpty { ReliabilityPanel(h: h) }
                        else if engine.sideTab == "ask" && !engine.reliability(h).isEmpty { AskNextPanel(h: h) }
                        else { detail(h) }
                    } else { Text("—") }
                }.frame(maxWidth: .infinity, alignment: .leading) }
                .sdrWidth(560)
                .sdrMaxHeight(640)
                .padding(16).sdrPanel()
            }
        }
    }
    /// Bounded viewport. The old max-height plus fixedSize let the panel grow with the chart, so there was nothing to scroll.
    @ViewBuilder func homeCascade(_ item: DomainItem) -> some View {
        let dossier = HomeHealthDossier(item: item, level: engine.homeShownLevel)
            .frame(maxWidth: .infinity, alignment: .leading)
        #if os(visionOS)
        ScrollView(.vertical) { dossier }
            .frame(width: 720, height: 680)
            .padding(16)
            .sdrPanel()
        #else
        dossier.padding(16).sdrPanel()
        #endif
    }
    func detail(_ h: Handoff) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Details · \(h.itemId)").font(.title2.bold())
            ForEach(engine.detailSections(h)) { s in
                let open = engine.openSections[s.title] != nil
                Button { engine.toggleSection(s.title) } label: {
                    HStack { Text(open ? "▾" : "▸"); Text(s.title).font(.title3.bold()); Spacer(); Text("\(s.rows.count)").foregroundStyle(.secondary) }
                }.buttonStyle(.plain).gloss(s.title)
                if open {
                    let home = engine.config.id == "home_health"
                    ForEach(Array(s.rows.enumerated()), id: \.offset) { _, r in
                        HStack(alignment: .top) {
                            Text(r.0).font(home ? .title3.bold() : .callout.bold()).frame(width: home ? 210 : 170, alignment: .leading).gloss(r.0)
                            Text(r.1).font(home ? .title3 : .callout).foregroundStyle(.secondary)
                        }
                    }.padding(.leading, 18)
                }
            }
            Text("sections opened + dwell are logged with the decision").font(.caption2).foregroundStyle(.secondary)
        }
    }
    var spot: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack { Text("Spot-check queue").font(.title2.bold()).gloss("spot-check"); Spacer(); Button("Close") { engine.spotCheckOpen = false } }
            let p = engine.pendingSpotChecks
            if p.isEmpty { Text("nothing sampled yet").foregroundStyle(.secondary) }
            ForEach(p.prefix(6)) { d in
                VStack(alignment: .leading, spacing: 3) {
                    Text("\(d.itemId) · \(d.question) \(d.proposedAnswer) (\(Int(d.proposedConfidence * 100))%) · auto-passed").font(.headline)
                    Text(d.displayLine).font(.caption).lineLimit(1).foregroundStyle(.secondary)
                    Text("→ \(d.downstreamPreview ?? "")").font(.caption).foregroundStyle(.green)
                    HStack { Button("Agree") { engine.reviewSpotCheck(d.id, agree: true) }.tint(.green)
                             Button("Disagree") { engine.reviewSpotCheck(d.id, agree: false) }.tint(.red) }.font(.callout)
                }
            }
            let done = engine.decisions.filter { $0.spotCheckResult != nil }
            Text("reviewed \(done.count) · disagree \(done.filter { $0.spotCheckResult == "disagree" }.count)").font(.callout).foregroundStyle(.secondary)
        }
    }
}

struct OptionRing: View {
    @Environment(RouterEngine.self) private var engine
    @State private var newName = ""
    @State private var adding = false
    var body: some View {
        let h = engine.handoffs.first { $0.id == engine.ringFor }
        let opts = h.map { engine.registry.mainOptions($0.link) } ?? []
        let trials = h.map { engine.registry.trialOptions($0.link) } ?? []
        let fields = h.flatMap { engine.items[$0.itemId]?.fields } ?? [:]
        let home = engine.config.id == "home_health"
        return VStack(spacing: 10) {
            if home, let h {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Change route").font(.title.bold())
                    Text("Sends to the on-call. You stay the Overseer.").font(.title3).foregroundStyle(.secondary)
                    ForEach(opts, id: \.self) { o in
                        Button { engine.select(h.id, o) } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(HomeHealthRoute.title(o)).font(.title2.bold())
                                Text(HomeHealthSeat.recipientChip(route: o, fields: fields)).font(.title3)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .tint(o == h.proposal ? .gray : .blue)
                    }
                    Button("Cancel") { engine.ringFor = nil }.tint(.gray)
                }
                .padding(8)
                .sdrWidth(520)
            } else {
            ZStack {
                Circle().stroke(.white.opacity(0.4), lineWidth: 2).frame(width: 280, height: 280)
                Text(h?.link.question ?? "").font(.headline)
                ForEach(Array(opts.enumerated()), id: \.offset) { i, o in
                    let ang = Double(i) / Double(max(opts.count, 1)) * 2 * .pi - .pi / 2
                    Button(o) { if let h { engine.select(h.id, o) } }
                        .help(h.flatMap { hh in engine.items[hh.itemId].map { Review.preview(engine.domain, $0, hh.link, o, trial: false) } } ?? o)
                        .font(.headline).tint(o == h?.proposal ? .gray : .blue)
                        .offset(x: 140 * cos(ang), y: 140 * sin(ang))
                }
            }.frame(width: 440, height: 360)
            if !trials.isEmpty {
                HStack {
                    Text("trial:").font(.callout).foregroundStyle(.purple)
                    ForEach(trials, id: \.self) { t in Button(t) { if let h { engine.select(h.id, t) } }.tint(.purple).font(.callout) }
                }
            }
            if adding {
                HStack {
                    TextField("new category", text: $newName).textFieldStyle(.roundedBorder).frame(width: 220)
                    Button("Add") { if let h, !newName.isEmpty { engine.selectNew(h.id, newName); newName = ""; adding = false } }
                }
                Text("trial categories are logged but never change routing or fire alerts until promoted").font(.caption2).foregroundStyle(.secondary)
            } else {
                Button("New…") { adding = true }.tint(.purple).font(.headline)
            }
            }
        }.padding(12).sdrPanel()
    }
}

struct BoardView: View {
    @Environment(RouterEngine.self) private var engine
    #if os(visionOS)
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    #endif
    var body: some View {
        #if os(visionOS)
        if engine.config.id == "home_health" { homeStatus } else { classicBoard }
        #else
        classicBoard
        #endif
    }
    private var classicBoard: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            let cfg = engine.config, s = engine.stats
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Button { engine.boardLarge.toggle() } label: { Text(cfg.terminology.boardTitle).font(.title.bold()) }.buttonStyle(.plain)
                    Button(engine.boardLarge ? "Shrink" : "Enlarge") { engine.boardLarge.toggle() }.font(.callout).fixedSize()
                    if cfg.synthetic { Text(cfg.terminology.syntheticBanner).font(.callout.bold()).foregroundStyle(.yellow) }
                    Spacer()
                    Text("site \(engine.siteId) · agent error \(Int(s.agentErrorRate * 100))%").font(.callout).foregroundStyle(.secondary)
                }
                HStack(spacing: 14) {
                    stat(cfg.terminology.completedLabel, "\(s.completed)"); stat("Decisions", "\(s.decisions)")
                    stat("Alerts", "\(s.alertsFired)"); stat("Corrections", "\(s.corrections)")
                    stat("Prevented", "\(s.errorsPrevented)"); stat("Misses", "\(s.misses)")
                    stat("Median dec.", String(format: "%.1fs", s.medianLatency)); stat("Auto-passed", "\(engine.autoPassed)")
                }
                HStack(spacing: 14) { ForEach(engine.domain.boardMetrics(s)) { m in stat(m.label, m.value) } }
                HStack(spacing: 10) {
                    ForEach(engine.domain.breakdown(), id: \.0) { b in
                        Text("\(b.0): \(b.1)").font(.headline).padding(.horizontal, 8).padding(.vertical, 3).background(.white.opacity(0.12), in: Capsule())
                    }
                }
                Divider()
                ForEach(engine.recentRows) { r in
                    HStack(spacing: 6) {
                        Text(r.id).font(.headline.monospaced()).frame(width: 56, alignment: .leading)
                        Text(r.line).font(.callout).lineLimit(1).frame(width: 300, alignment: .leading)
                        HStack(spacing: 3) {
                            ForEach(Array(r.steps.enumerated()), id: \.offset) { _, st in
                                Text(st.0).font(.callout.bold()).padding(.horizontal, 6).padding(.vertical, 1)
                                    .background(st.3 ? Color.purple.opacity(0.6) : (st.1 ? Color.orange : Color.white.opacity(0.15)), in: Capsule())
                                    .foregroundStyle(st.2 ? Color.primary : Color.red)
                            }
                        }.frame(width: 360, alignment: .leading)
                        Text(label(r.status)).font(.callout.bold()).foregroundStyle(color(r.status))
                    }
                }
                CategoriesStrip()
                HStack(spacing: 12) {
                    Text("orange = changed · purple = trial · red = wrong · hover any field for its meaning").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if DemoState.on {
                        Text(engine.demoRunning ? "▶ \(engine.demoStep)" : engine.demoStep).foregroundStyle(.yellow)
                        Button("Reset demo") { engine.startDemo(auto: false) }.tint(.yellow)
                        Button("Auto-play") { engine.startDemo(auto: true) }.tint(.yellow).disabled(engine.demoRunning)
                    } else if DomainCatalog.all.count > 1 { Button("Next Domain") { engine.nextDomain() } }
                    Button("Export") { engine.export() }
                    @Bindable var e = engine
                    #if os(visionOS)
                    Toggle("Environment", isOn: $e.fullImmersion).frame(width: 170)
                    Button("Close") { Task { await dismissImmersiveSpace() } }   // onDisappear reopens the start window (exactly once)
                    #endif
                }.font(.callout)
            }
            .sdrWidth(1000).padding(16).sdrPanel()
        }
    }
    #if os(visionOS)
    /// Mid-left layer. Collapsed is Reviewed / Alerts / Corrections in large type. Show brings the log forward.
    private var homeStatus: some View {
        let cfg = engine.config
        let s = engine.stats
        let open = engine.focusStatusOpen && !engine.detailOpen
        let attention = s.alertsFired > 0 || s.corrections > 0
        let reviewed = engine.domain.boardMetrics(s).first { $0.label == "Reviewed" }?.value ?? "\(s.completed)"
        return TimelineView(.periodic(from: .now, by: attention && !open ? 0.12 : 1)) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate
            let pulse = (!open && attention) ? (1 + 0.045 * sin(phase * 2.6)) : 1.0
            VStack(alignment: .leading, spacing: open ? 16 : 10) {
                HStack(alignment: .center, spacing: 14) {
                    Button { engine.focusStatusOpen.toggle() } label: {
                        HStack(spacing: 8) {
                            Text(open ? "Status" : "Overseer").font(.title.bold())
                            Text(open ? "Hide" : "Show").font(.title2).foregroundStyle(.secondary)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(open ? "Hide status" : "Show status")
                    if cfg.synthetic {
                        Text("SYNTHETIC").font(.title3.bold()).foregroundStyle(.black)
                            .padding(.horizontal, 10).padding(.vertical, 4)
                            .background(.yellow, in: Capsule())
                            .help(cfg.terminology.syntheticBanner)
                    }
                    Spacer()
                    Button("Close") { Task { await dismissImmersiveSpace() } }.font(.title2.bold())
                }
                Text(HomeHealthSeat.framing).font(.title3).foregroundStyle(.secondary).lineLimit(1)
                HStack(alignment: .top, spacing: 28) {
                    bigStat("Reviewed", reviewed)
                    bigStat("Alerts", "\(s.alertsFired)", hot: s.alertsFired > 0)
                    bigStat("Corrections", "\(s.corrections)", hot: s.corrections > 0)
                    if open {
                        bigStat("Decisions", "\(s.decisions)")
                        bigStat("Median", compactDuration(s.medianLatency))
                    }
                }
                if !open && attention {
                    Text("Alerts or corrections").font(.title2.bold()).foregroundStyle(.orange)
                }
                if open {
                    HStack(alignment: .top, spacing: 28) {
                        ForEach(engine.domain.boardMetrics(s).filter { $0.label != "Reviewed" }) { m in
                            bigStat(m.label, m.value, hot: m.label == "Bridge" && m.value != "live")
                        }
                    }
                    Divider()
                    ForEach(engine.recentRows) { r in
                        HStack(spacing: 14) {
                            Text(r.id).font(.title2.bold().monospaced()).frame(width: 160, alignment: .leading)
                            Text(r.line).font(.title2).lineLimit(1)
                            Spacer(minLength: 8)
                            Text(label(r.status)).font(.title3.bold()).foregroundStyle(color(r.status)).lineLimit(1)
                        }
                    }
                    HStack(spacing: 16) {
                        if DomainCatalog.all.count > 1 { Button("Next Domain") { engine.nextDomain() } }
                        Button("Export") { engine.export() }
                        @Bindable var e = engine
                        Toggle("Environment", isOn: $e.fullImmersion)
                    }
                    .font(.title3.bold())
                }
            }
            .scaleEffect(pulse)
            .sdrWidth(open ? 920 : 700)
            .padding(open ? 22 : 18)
            .sdrPanel()
        }
    }
    private func bigStat(_ t: String, _ v: String, hot: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(v).font(.system(size: 44, weight: .bold)).monospacedDigit()
                .foregroundStyle(hot ? Color.orange : Color.primary)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(t).font(.title2).foregroundStyle(hot ? Color.orange : Color.secondary).lineLimit(1)
        }
    }
    private func compactDuration(_ seconds: Double) -> String {
        if seconds < 60 { return String(format: "%.0fs", seconds) }
        if seconds < 3600 { return String(format: "%.0fm", seconds / 60) }
        return String(format: "%.1fh", seconds / 3600)
    }
    #endif
    private func stat(_ t: String, _ v: String) -> some View {
        VStack(spacing: 0) { Text(v).font(.title2.bold().monospacedDigit()); Text(t).font(.caption) }
    }
    private func label(_ s: String) -> String {
        switch s { case "correct": "✓ correct"; case "corrected": "✓ corrected"; case "missed": "✗ miss"; default: s }
    }
    private func color(_ s: String) -> Color {
        switch s { case "correct": .green; case "corrected": .orange; case "missed": .red; default: .secondary }
    }
}

/// Categories panel: main / trial / dormant per category link, with scores.
struct CategoriesStrip: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        let reg = engine.registry
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text("Categories · site \(reg.siteId) · registry v\(reg.version)").font(.callout.bold())
                if let ev = reg.history.last(where: { $0.op != "seed" }) {
                    Text("last: \(ev.op) “\(ev.category)” \(ev.detail)").font(.caption).foregroundStyle(.purple).lineLimit(1)
                }
            }
            ForEach(engine.config.links.filter { $0.answerType == .category }, id: \.id) { l in
                HStack(spacing: 6) {
                    Text(l.shortLabel ?? l.id).font(.caption.bold()).frame(width: 44, alignment: .leading)
                    ForEach(reg.list(l, .main).filter { !$0.isBase }, id: \.name) { e in chip("★ \(e.name)", .green) }
                    ForEach(reg.list(l, .trial), id: \.name) { e in
                        chip(String(format: "%@ · %du %.0f%% %d✓", e.name, e.uses, e.consistency * 100, e.outcomeSupport), .purple)
                    }
                    ForEach(reg.list(l, .dormant), id: \.name) { e in chip("⌀ \(e.name)", .gray) }
                    if reg.list(l, .trial).isEmpty && reg.list(l, .dormant).isEmpty && reg.list(l, .main).allSatisfy(\.isBase) {
                        Text("base set only").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
    private func chip(_ t: String, _ c: Color) -> some View {
        Text(t).font(.caption.bold()).padding(.horizontal, 6).padding(.vertical, 1).background(c.opacity(0.45), in: Capsule())
    }
}

import os
let uiLog = Logger(subsystem: "com.wsatz.SpatialDecisionRouter", category: "launcher")

#if os(visionOS)

struct LauncherView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    @Environment(\.openWindow) private var openWindow
    @State private var status = ""
    var body: some View {
        VStack(spacing: 14) {
            Text(engine.config.title).font(.sdrHuge)
            Text(engine.config.agents.filter { $0.tier == 0 }.map(\.name).joined(separator: " · "))
            if engine.config.synthetic { Text(engine.config.terminology.syntheticBanner).foregroundStyle(.yellow) }
            HStack(spacing: 20) {
                Button("Enter Crossroads") { tap("enter") }
                Button("Demo") { tap("demo") }.tint(.yellow)
                Button("Demo (auto-play)") { tap("demoAuto") }.tint(.orange)
                Button("WERIAM Principal") { tap("weriamDemo") }.tint(.purple)
                Button("Symbiosis") { tap("symbiosisDemo") }.tint(.orange)
                Button("Home health") { tap("homeHealth") }.tint(.teal)
                ManifestoButton()
            }.font(.title2)
            Text("Demo: 6 scripted SYNTHETIC encounters · needs risk_engine sidecar for BN (else fallback badge). Home health uses Layer 1 (bridge on :8767, or the bundled snapshot).").font(.callout).foregroundStyle(.secondary)
            if !status.isEmpty { Text(status).font(.headline).foregroundStyle(status.hasPrefix("⚠") ? .red : .secondary) }
        }
        .padding(40)
        .task {
            let a = ProcessInfo.processInfo.arguments
            // -openLineageAfter N: screenshot aid — opens the Lineage window N seconds after launch
            if let n = a.argValue("-openLineageAfter").flatMap(Double.init) {
                Task { try? await Task.sleep(for: .seconds(n)); openWindow(id: "lineage") }
            }
            // -autoTap enter|demo|demoAuto: exercises exactly the button code path (debug/test)
            if let i = a.firstIndex(of: "-autoTap"), i + 1 < a.count { try? await Task.sleep(for: .seconds(2)); tap(a[i + 1]); return }
            let sym = DomainCatalog.demoId == "symbiosis"
            if a.contains("-autoOpenImmersive") { tap(sym ? "symbiosisDemo" : DemoState.on ? (DemoState.auto ? "demoAuto" : "demo") : "enter") }
            else if DemoState.on { tap(sym ? "symbiosisDemo" : DemoState.auto ? "demoAuto" : "demo") }
        }
    }
    /// single entry point for buttons AND launch args
    private func tap(_ which: String) {
        uiLog.notice("tap \(which, privacy: .public) immersiveOpen=\(engine.immersiveOpen)")
        status = "tap received (\(which)) — opening…"
        switch which {
        case "demo": engine.startDemo(auto: false)
        case "demoAuto": engine.startDemo(auto: true)
        case "weriamDemo": DomainCatalog.demoId = "weriam_principal"; engine.startDemo(auto: false)
        case "symbiosisDemo": DomainCatalog.demoId = "symbiosis"; engine.startDemo(auto: DemoState.auto)
        case "homeHealth": DemoState.on = false; engine.start(HomeHealthDomain())
        default: if DemoState.on { DemoState.on = false; engine.start(AIDocReviewDomain()) }
        }
        Task { await open() }
    }
    private func open() async {
        status = "opening immersive space…"
        if engine.immersiveOpen {   // stale state (space closed by system, or still open): close first, then reopen
            uiLog.notice("space marked open — dismissing before reopen"); await dismissImmersiveSpace(); engine.immersiveOpen = false
        }
        let r = await openImmersiveSpace(id: "Router")
        uiLog.notice("openImmersiveSpace -> \(String(describing: r), privacy: .public)")
        switch r {
        case .opened: engine.immersiveOpen = true; status = ""; dismissWindow(id: "main")
        case .userCancelled: status = "⚠ immersive space cancelled by system/user — tap again"
        case .error: status = "⚠ could not open immersive space (another app's space open, or simulator issue) — close other immersive apps and tap again"
        @unknown default: status = "⚠ immersive space: unexpected result"
        }
    }
}
#endif
