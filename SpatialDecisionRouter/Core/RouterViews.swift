import SwiftUI
import RealityKit

struct CrossroadsView: View {
    @Environment(RouterEngine.self) private var engine
    @State private var root = Entity()
    @State private var builtVersion = -1
    @State private var pulsed: [String: Date] = [:]

    var body: some View {
        RealityView { content, att in
            content.add(root); buildStatic(att)
        } update: { _, att in
            if builtVersion != engine.packVersion { buildStatic(att) }
            sync(att)
        } attachments: {
            ForEach(engine.config.agents, id: \.id) { a in
                Attachment(id: "agent-\(a.id)") { AgentCard(agent: a, received: engine.inbox[a.id] ?? 0) }
            }
            ForEach(engine.handoffs.filter { engine.phase[$0.id] != .delivered }) { h in
                Attachment(id: h.id) { HandoffCard(h: h) }
            }
            Attachment(id: "ring") { OptionRing() }
            Attachment(id: "board") { BoardView() }
        }
        .gesture(SpatialTapGesture().targetedToAnyEntity().onEnded { v in engine.pass(v.entity.name) })
        .simultaneousGesture(LongPressGesture(minimumDuration: 0.6).targetedToAnyEntity().onEnded { v in
            if let h = engine.handoffs.first(where: { $0.id == v.entity.name }), h.link.answerType == .category { engine.openRing(h.id) }
        })
        .simultaneousGesture(DragGesture(minimumDistance: 60).targetedToAnyEntity().onEnded { v in engine.flip(v.entity.name) })
        .task { while !Task.isCancelled { try? await Task.sleep(for: .milliseconds(50)); engine.tick(0.05) } }
        .task {
            let a = ProcessInfo.processInfo.arguments
            if let i = a.firstIndex(of: "-autoResolve"), i + 1 < a.count, let n = Int(a[i + 1]) {
                try? await Task.sleep(for: .seconds(2)); await engine.autoResolve(n)
                if a.contains("-autoExport") { engine.export() }
            }
        }
    }

    private func line(_ a: SIMD3<Float>, _ b: SIMD3<Float>) -> Entity {
        let e = ModelEntity(mesh: .generateCylinder(height: simd_distance(a, b), radius: 0.004), materials: [UnlitMaterial(color: UIColor(white: 1, alpha: 0.5))])
        e.position = (a + b) / 2; e.orientation = simd_quatf(from: [0, 1, 0], to: simd_normalize(b - a)); return e
    }

    private func buildStatic(_ att: RealityViewAttachments) {
        let cfg = engine.config
        guard cfg.agents.allSatisfy({ att.entity(for: "agent-\($0.id)") != nil }) else { return }
        for c in Array(root.children) { c.removeFromParent() }
        let env = ProceduralEnvironment.make(cfg.theme); env.isEnabled = engine.fullImmersion; root.addChild(env)
        let hub = ModelEntity(mesh: .generateSphere(radius: 0.025), materials: [UnlitMaterial(color: .white)])
        hub.position = RouterEngine.hub; root.addChild(hub)
        for (i, a) in cfg.agents.enumerated() {
            let p = engine.agentPosition(a.id)
            let node = ModelEntity(mesh: .generateSphere(radius: a.tier == 0 ? 0.1 : 0.12),
                                   materials: [SimpleMaterial(color: UIColor(hue: CGFloat(i) / CGFloat(cfg.agents.count + 1), saturation: 0.7, brightness: 0.95, alpha: 0.95), isMetallic: false)])
            node.position = p; node.name = "agent-\(a.id)"; root.addChild(node)
            root.addChild(line(p, RouterEngine.hub))
            if let card = att.entity(for: "agent-\(a.id)") {
                card.position = p + [0, a.tier == 0 ? -0.24 : 0.28, 0]; card.scale = [1.7, 1.7, 1.7]
                card.components.set(BillboardComponent()); root.addChild(card)
            }
        }
        if let b = att.entity(for: "board") {
            b.position = [0, 1.93, -1.4]; b.components.set(BillboardComponent()); root.addChild(b)
        }
        if let r = att.entity(for: "ring") { r.name = "ringAttachment"; r.isEnabled = false; root.addChild(r) }
        let v = engine.packVersion
        Task { @MainActor in builtVersion = v; pulsed = [:] }
    }

    private func sync(_ att: RealityViewAttachments) {
        let cfg = engine.config
        for h in engine.handoffs {
            if engine.phase[h.id] == .delivered { root.findEntity(named: h.id)?.removeFromParent(); continue }
            var e = root.findEntity(named: h.id)
            if e == nil, let card = att.entity(for: h.id) {
                let hue = CGFloat(engine.agentIndex(h.link.source)) / CGFloat(cfg.agents.count + 1)
                let m = ModelEntity(mesh: h.link.answerType == .binary ? .generateBox(size: 0.09, cornerRadius: 0.02) : .generateSphere(radius: 0.06),
                                    materials: [SimpleMaterial(color: UIColor(hue: hue, saturation: 0.25 + 0.7 * CGFloat(h.confidence), brightness: 1, alpha: 0.85), isMetallic: false)])
                m.name = h.id
                m.components.set(InputTargetComponent()); m.components.set(HoverEffectComponent()); m.generateCollisionShapes(recursive: false)
                card.position = [0, 0.16, 0]; card.components.set(BillboardComponent()); m.addChild(card)
                root.addChild(m); e = m
            }
            e?.position = engine.position(h)
        }
        for (agent, t) in engine.lastDelivered where pulsed[agent] != t {
            if let n = root.findEntity(named: "agent-\(agent)") {
                var big = n.transform; big.scale = [1.8, 1.8, 1.8]; n.move(to: big, relativeTo: root, duration: 0.18)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { var s = n.transform; s.scale = [1, 1, 1]; n.move(to: s, relativeTo: root, duration: 0.35) }
            }
            Task { @MainActor in pulsed[agent] = t }
        }
        root.findEntity(named: "environment")?.isEnabled = engine.fullImmersion
        if let r = root.findEntity(named: "ringAttachment") {
            if let id = engine.ringFor, let h = engine.handoffs.first(where: { $0.id == id }) {
                r.isEnabled = true
                r.position = RouterEngine.head + simd_normalize(engine.position(h) - RouterEngine.head) * 0.75
                r.components.set(BillboardComponent())
            } else { r.isEnabled = false }
        }
    }
}

struct AgentCard: View {
    let agent: AgentSpec; let received: Int
    var body: some View {
        VStack(spacing: 2) {
            Text(agent.name).font(.title3.bold())
            if let r = agent.role { Text(r).font(.callout).foregroundStyle(.secondary) }
            if agent.tier == 1 { Text("received \(received)").font(.headline.monospacedDigit()) }
        }.padding(10).glassBackgroundEffect()
    }
}

struct HandoffCard: View {
    @Environment(RouterEngine.self) private var engine
    let h: Handoff
    var body: some View {
        let item = engine.items[h.itemId]
        let routed = engine.routed[h.id]
        let t = engine.config.terminology
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("\(h.link.source) → \(h.link.dest) · \(h.itemId)").font(.headline).foregroundStyle(.secondary)
                Spacer()
                if h.priority >= 1.0 { Text("⚑ PRIORITY").font(.headline.bold()).foregroundStyle(.red) }
            }
            Text(item?.displayLine ?? "").font(.title3).lineLimit(3)
            Text("\(t.historyLabel): \(item?.historyLine ?? "none")").font(.callout).foregroundStyle(.yellow).lineLimit(2)
            Text("\(t.capacityLabel): \(h.capacityLine)").font(.callout).foregroundStyle(.cyan).lineLimit(1)
            HStack {
                Text(h.link.question).font(.title3)
                Spacer()
                if let r = routed, r != h.proposal {
                    Text(h.proposal).strikethrough().font(.title3).foregroundStyle(.secondary)
                    Text(r).font(.title.bold()).foregroundStyle(.orange)
                } else { Text(routed ?? h.proposal).font(.title.bold()) }
                Text("\(Int(h.confidence * 100))%").font(.headline.monospacedDigit())
            }
            if routed == nil {
                HStack(spacing: 12) {
                    Button("Pass ✓") { engine.pass(h.id) }.tint(.green)
                    if h.link.answerType == .binary { Button("Flip") { engine.flip(h.id) }.tint(.orange) }
                    else { Button("Change…") { engine.openRing(h.id) }.tint(.blue) }
                }.font(.title3.bold())
            }
        }
        .frame(width: 460).padding(16).glassBackgroundEffect()
    }
}

struct OptionRing: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        let h = engine.handoffs.first { $0.id == engine.ringFor }
        let opts = h.map { engine.registry.mainOptions($0.link) } ?? []
        ZStack {
            Circle().stroke(.white.opacity(0.4), lineWidth: 2).frame(width: 280, height: 280)
            Text(h?.link.question ?? "").font(.headline)
            ForEach(Array(opts.enumerated()), id: \.offset) { i, o in
                let ang = Double(i) / Double(max(opts.count, 1)) * 2 * .pi - .pi / 2
                Button(o) { if let h { engine.select(h.id, o) } }
                    .font(.headline).tint(o == h?.proposal ? .gray : .blue)
                    .offset(x: 140 * cos(ang), y: 140 * sin(ang))
            }
        }.frame(width: 440, height: 420)
    }
}

struct BoardView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            let cfg = engine.config, s = engine.stats
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(cfg.terminology.boardTitle).font(.title.bold())
                    if cfg.synthetic { Text(cfg.terminology.syntheticBanner).font(.callout.bold()).foregroundStyle(.yellow) }
                    Spacer()
                    Text("site \(engine.siteId) · agent error \(Int(s.agentErrorRate * 100))%").font(.callout).foregroundStyle(.secondary)
                }
                HStack(spacing: 14) {
                    stat(cfg.terminology.completedLabel, "\(s.completed)"); stat("Decisions", "\(s.decisions)")
                    stat("Alerts", "\(s.alertsFired)"); stat("Corrections", "\(s.corrections)")
                    stat("Prevented", "\(s.errorsPrevented)"); stat("Misses", "\(s.misses)")
                    stat("Median dec.", String(format: "%.1fs", s.medianLatency))
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
                    Text("tap = pass · hold = options · orange = changed · purple = trial · red = wrong").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if DomainCatalog.all.count > 1 { Button("Next Domain") { engine.nextDomain() } }
                    Button("Export") { engine.export() }
                    @Bindable var e = engine
                    Toggle("Environment", isOn: $e.fullImmersion).frame(width: 170)
                    Button("Close") { Task { openWindow(id: "main"); await dismissImmersiveSpace(); engine.immersiveOpen = false } }
                }.font(.callout)
            }
            .frame(width: 1000).padding(16).glassBackgroundEffect()
        }
    }
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

/// Compact categories panel (phase B fills in trial/dormant tiers).
struct CategoriesStrip: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        Text("Categories · registry v\(engine.registry.version)").font(.caption).foregroundStyle(.secondary)
    }
}

struct LauncherView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow
    var body: some View {
        VStack(spacing: 14) {
            Text(engine.config.title).font(.extraLargeTitle2)
            Text(engine.config.agents.filter { $0.tier == 0 }.map(\.name).joined(separator: " · "))
            if engine.config.synthetic { Text(engine.config.terminology.syntheticBanner).foregroundStyle(.yellow) }
            Button("Enter Crossroads") { Task { await open() } }.font(.title2)
        }
        .padding(40)
        .task { if ProcessInfo.processInfo.arguments.contains("-autoOpenImmersive") { await open() } }
    }
    private func open() async {
        if case .opened = await openImmersiveSpace(id: "Router") { engine.immersiveOpen = true; dismissWindow(id: "main") }
    }
}
