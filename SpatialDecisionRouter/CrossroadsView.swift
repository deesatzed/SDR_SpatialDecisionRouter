import SwiftUI
import RealityKit

struct CrossroadsView: View {
    @Environment(CrossroadsStore.self) private var store
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    @State private var root = Entity()
    @State private var built: Set<String> = []

    var body: some View {
        RealityView { content, attachments in
            content.add(root)
            buildStatic(attachments)
        } update: { _, attachments in
            sync(attachments)
        } attachments: {
            if let sc = store.scenario {
                ForEach(sc.agents, id: \.id) { a in
                    Attachment(id: "agent-\(a.id)") { AgentCard(agent: a, inbox: store.inbox[a.id] ?? 0) }
                }
            }
            ForEach(store.handoffs.filter { store.phase[$0.id] != .delivered }) { h in
                Attachment(id: h.id) { HandoffCard(h: h, routed: store.routed[h.id]) }
            }
            Attachment(id: "ring") { OptionRing() }
            Attachment(id: "metrics") {
                MetricsPanel { Task { openWindow(id: "main"); await dismissImmersiveSpace(); store.immersiveOpen = false } }
            }
        }
        .gesture(SpatialTapGesture().targetedToAnyEntity().onEnded { v in store.pass(v.entity.name) })
        .simultaneousGesture(LongPressGesture(minimumDuration: 0.6).targetedToAnyEntity().onEnded { v in
            if let h = store.handoffs.first(where: { $0.id == v.entity.name }), h.link.answerType == .category { store.ringFor = h.id }
        })
        .simultaneousGesture(DragGesture(minimumDistance: 60).targetedToAnyEntity().onEnded { v in store.flip(v.entity.name) })
        .task { while !Task.isCancelled { try? await Task.sleep(for: .milliseconds(50)); store.tick(0.05) } }
        .task {
            let a = ProcessInfo.processInfo.arguments
            if let i = a.firstIndex(of: "-autoResolve"), i + 1 < a.count, let n = Int(a[i + 1]) {
                try? await Task.sleep(for: .seconds(2))
                await store.autoResolve(n)
                if a.contains("-autoExport") { store.export() }
            }
        }
    }

    private func line(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ color: UIColor) -> Entity {
        let len = simd_distance(a, b)
        let e = ModelEntity(mesh: .generateCylinder(height: len, radius: 0.004),
                            materials: [UnlitMaterial(color: color)])
        e.position = (a + b) / 2
        e.orientation = simd_quatf(from: [0, 1, 0], to: simd_normalize(b - a))
        return e
    }

    private func buildStatic(_ att: RealityViewAttachments) {
        guard let sc = store.scenario else { return }
        let hub: SIMD3<Float> = [0, 1.4, -1.05]
        let hubE = ModelEntity(mesh: .generateSphere(radius: 0.03), materials: [UnlitMaterial(color: .white)])
        hubE.position = hub; root.addChild(hubE)
        for (i, a) in sc.agents.enumerated() {
            let p = store.agentPosition(a.id)
            let node = ModelEntity(mesh: .generateSphere(radius: 0.11),
                                   materials: [SimpleMaterial(color: UIColor(hue: CGFloat(i) / 4.5, saturation: 0.7, brightness: 0.95, alpha: 0.95), isMetallic: false)])
            node.position = p; node.name = "agent-\(a.id)"
            root.addChild(node)
            root.addChild(line(p, hub, UIColor(white: 1, alpha: 0.5)))
            if let card = att.entity(for: "agent-\(a.id)") {
                card.position = p + [0, 0.24, 0]; card.components.set(BillboardComponent()); root.addChild(card)
            }
        }
        if let m = att.entity(for: "metrics") {
            m.position = [-0.95, 1.95, -1.6]; m.components.set(BillboardComponent()); root.addChild(m)
        }
        if let r = att.entity(for: "ring") { r.name = "ringAttachment"; r.isEnabled = false; root.addChild(r) }
    }

    private func sync(_ att: RealityViewAttachments) {
        for h in store.handoffs {
            let ph = store.phase[h.id] ?? .incoming
            if ph == .delivered {
                if let e = root.findEntity(named: h.id) { e.removeFromParent() }
                continue
            }
            var e = root.findEntity(named: h.id)
            if e == nil, !built.contains(h.id), let card = att.entity(for: h.id) {
                let binary = h.link.answerType == .binary
                let hue = CGFloat(h.stage) / 4.5
                let m = ModelEntity(mesh: binary ? .generateBox(size: 0.1, cornerRadius: 0.02) : .generateSphere(radius: 0.065),
                                    materials: [SimpleMaterial(color: UIColor(hue: hue, saturation: 0.25 + 0.7 * CGFloat(h.confidence), brightness: 1, alpha: 0.85), isMetallic: false)])
                m.name = h.id
                m.components.set(InputTargetComponent()); m.components.set(HoverEffectComponent())
                m.generateCollisionShapes(recursive: false)
                card.position = [0, 0.19, 0]; card.scale = [1.25, 1.25, 1.25]
                card.components.set(BillboardComponent())
                m.addChild(card)
                root.addChild(m)
                Task { @MainActor in built.insert(h.id) }
                e = m
            }
            e?.position = store.position(h)
        }
        if let r = root.findEntity(named: "ringAttachment") {
            if let id = store.ringFor, let h = store.handoffs.first(where: { $0.id == id }) {
                r.isEnabled = true
                let p = store.position(h)
                r.position = CrossroadsStore.head + simd_normalize(p - CrossroadsStore.head) * 0.75
                r.components.set(BillboardComponent())
            } else { r.isEnabled = false }
        }
    }
}

struct AgentCard: View {
    let agent: AgentSpec; let inbox: Int
    var body: some View {
        VStack(spacing: 2) {
            Text(agent.name).font(.title3.bold())
            Text("inbox \(inbox)").font(.headline.monospacedDigit())
        }.padding(12).glassBackgroundEffect()
    }
}

struct HandoffCard: View {
    @Environment(CrossroadsStore.self) private var store
    let h: Handoff; let routed: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("\(h.link.source) → \(h.link.dest) · \(h.caseID)").font(.headline).foregroundStyle(.secondary)
            Text(h.inputContext).font(.title3).lineLimit(2)
            HStack {
                Text(h.link.question).font(.title3)
                Spacer()
                if let r = routed, r != h.proposedAnswer {
                    Text(h.proposedAnswer).strikethrough().font(.title3).foregroundStyle(.secondary)
                    Text(r).font(.title.bold()).foregroundStyle(.orange)
                } else {
                    Text(routed ?? h.proposedAnswer).font(.title.bold())
                }
                Text("\(Int(h.confidence * 100))%").font(.headline.monospacedDigit())
            }
            if routed == nil {
                HStack(spacing: 12) {
                    Button("Pass ✓") { store.pass(h.id) }.tint(.green)
                    if h.link.answerType == .binary {
                        Button("Flip") { store.flip(h.id) }.tint(.orange)
                    } else {
                        Button("Change…") { store.openRing(h.id) }.tint(.blue)
                    }
                }.font(.title3.bold())
            }
        }
        .frame(width: 440).padding(18).glassBackgroundEffect()
    }
}

struct OptionRing: View {
    @Environment(CrossroadsStore.self) private var store
    var body: some View {
        let h = store.handoffs.first { $0.id == store.ringFor }
        let opts = h?.link.options ?? []
        ZStack {
            Circle().stroke(.white.opacity(0.4), lineWidth: 2).frame(width: 260, height: 260)
            Text(h?.link.question ?? "").font(.headline)
            ForEach(Array(opts.enumerated()), id: \.offset) { i, o in
                let ang = Double(i) / Double(max(opts.count, 1)) * 2 * .pi - .pi / 2
                Button(o) { if let h { store.select(h.id, o) } }
                    .font(.headline)
                    .tint(o == h?.proposedAnswer ? .gray : .blue)
                    .offset(x: 130 * cos(ang), y: 130 * sin(ang))
            }
        }
        .frame(width: 400, height: 380)
    }
}

struct MetricsPanel: View {
    @Environment(CrossroadsStore.self) private var store
    let onClose: () -> Void
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            VStack(alignment: .leading, spacing: 6) {
                Text("Crossroads").font(.title3.bold())
                Text("Routed \(store.decisions.count) · waiting \(store.waiting.count)").monospacedDigit()
                Text(String(format: "Handoffs/min  %.1f", store.handoffsPerMinute)).monospacedDigit()
                Text(String(format: "Changed  %.0f%%", store.pctChanged * 100)).monospacedDigit()
                Text(store.agreement.map { String(format: "Agree w/ GT  %.0f%%", $0 * 100) } ?? "Agree w/ GT  —").monospacedDigit()
                if !store.lastAction.isEmpty { Text(store.lastAction).font(.caption).lineLimit(1) }
                Text("tap = pass · hold = options · drag = flip (binary)").font(.caption2).foregroundStyle(.secondary)
                HStack { Button("Export") { store.export() }; Button("Close", action: onClose) }.font(.caption)
                if !store.lastExport.isEmpty { Text(store.lastExport).font(.caption2) }
            }.frame(width: 280).padding(14).glassBackgroundEffect()
        }
    }
}

struct LauncherView: View {
    @Environment(CrossroadsStore.self) private var store
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow
    var body: some View {
        VStack(spacing: 14) {
            Text("Crossroads Router").font(.extraLargeTitle2)
            Text("\(store.scenario?.agents.map(\.name).joined(separator: " → ") ?? "") · \(store.scenario?.cases.count ?? 0) cases")
            if let e = store.loadError { Text(e).foregroundStyle(.red) }
            Button("Enter Crossroads") { Task { await open() } }.font(.title2)
        }
        .padding(40)
        .task { if ProcessInfo.processInfo.arguments.contains("-autoOpenImmersive") { await open() } }
    }
    private func open() async {
        if case .opened = await openImmersiveSpace(id: "Router") { store.immersiveOpen = true; dismissWindow(id: "main") }
    }
}
