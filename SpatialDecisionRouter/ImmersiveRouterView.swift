import SwiftUI
import RealityKit

struct ImmersiveRouterView: View {
    @Environment(ProposalStore.self) private var store
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    @State private var root = Entity()
    @State private var animatedOut: Set<String> = []
    @State private var inspected: Set<String> = []
    @State private var builtVersion = -1

    private func rebuild(_ attachments: RealityViewAttachments) {
        for c in Array(root.children) { c.removeFromParent() }
        let ring = ModelEntity(mesh: .generateCylinder(height: 0.005, radius: 0.35),
                               materials: [SimpleMaterial(color: .white.withAlphaComponent(0.3), isMetallic: false)])
        root.addChild(ring)
        var found = 0
        for p in store.proposals {
            let size: Float = p.type == .binary ? 0.14 : 0.12
            let mesh: MeshResource = p.type == .binary ? .generateBox(size: size, cornerRadius: 0.02) : .generateSphere(radius: size / 1.6)
            let e = ModelEntity(mesh: mesh, materials: [SimpleMaterial(color: Layout.color(for: p), roughness: 0.3, isMetallic: false)])
            e.name = p.id
            e.position = store.position(of: p.id)
            e.components.set(InputTargetComponent())
            e.components.set(HoverEffectComponent())
            e.generateCollisionShapes(recursive: false)
            if let label = attachments.entity(for: p.id) {
                label.position = [0, 0.17, 0]
                label.scale = [0.8, 0.8, 0.8]
                label.components.set(BillboardComponent())
                e.addChild(label); found += 1
            }
            root.addChild(e)
            store.markShown(p.id)
        }
        if let panel = attachments.entity(for: "metrics") {
            panel.position = [-0.5, 1.0, -0.75]   // low-left, closer than the 1.3 m stop so cards never overlap it
            panel.components.set(BillboardComponent())
            root.addChild(panel)
        }
        guard found == store.proposals.count else { return }   // attachments not ready yet; retry next update
        let v = store.packVersion
        Task { @MainActor in builtVersion = v; animatedOut = []; inspected = [] }
    }

    var body: some View {
        RealityView { content, attachments in
            content.add(root)
            rebuild(attachments)
        } update: { _, attachments in
            if builtVersion != store.packVersion { rebuild(attachments) }
            for id in store.resolved where !animatedOut.contains(id) {
                guard let e = root.findEntity(named: id) else { continue }
                var t = e.transform
                t.translation = e.position * 2.5 + [0, 1.2, 0]
                t.scale = [0.01, 0.01, 0.01]
                e.move(to: t, relativeTo: root, duration: 0.8, timingFunction: .easeIn)
                Task { @MainActor in animatedOut.insert(id) }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) { e.removeFromParent() }
            }
            for id in store.inspecting.keys where !inspected.contains(id) {
                guard let e = root.findEntity(named: id) else { continue }
                var t = e.transform
                t.translation = simd_normalize(e.position - ProposalStore.head) * 0.8 + ProposalStore.head
                t.scale = [1.6, 1.6, 1.6]
                e.move(to: t, relativeTo: root, duration: 0.4)
                Task { @MainActor in inspected.insert(id) }
            }
            for p in store.proposals where !store.resolved.contains(p.id) && store.inspecting[p.id] == nil {
                root.findEntity(named: p.id)?.position = store.position(of: p.id)
            }
        } attachments: {
            ForEach(store.proposals) { p in
                Attachment(id: p.id) { ProposalCard(proposal: p, rank: store.rank(of: p.id) ?? 0) }
            }
            Attachment(id: "metrics") {
                MetricsPanel {
                    Task { openWindow(id: "main"); await dismissImmersiveSpace(); store.immersiveOpen = false }
                }
            }
        }
        .gesture(SpatialTapGesture().targetedToAnyEntity().onEnded { v in
            store.resolve(v.entity.name, action: .accept)
        })
        .simultaneousGesture(LongPressGesture(minimumDuration: 0.5).targetedToAnyEntity().onEnded { v in
            store.beginInspect(v.entity.name)
        })
        .simultaneousGesture(DragGesture(minimumDistance: 20).targetedToAnyEntity().onEnded { v in
            let dx = v.translation.width, dy = v.translation.height
            let action: HumanAction = (abs(dx) > abs(dy) ? dx < 0 : dy > 0) ? .reject : .recategorize
            store.resolve(v.entity.name, action: action)
        })
        .task {
            // drift loop
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(100))
                store.tick(dt: 0.1 * driftSpeedup)
            }
        }
        .task {
            let args = ProcessInfo.processInfo.arguments
            if args.contains("-testNextPack") {
                try? await Task.sleep(for: .seconds(3))
                store.nextPack()   // same call the Next Pack button makes
            }
            if let i = args.firstIndex(of: "-autoResolve"), i + 1 < args.count, let n = Int(args[i + 1]) {
                try? await Task.sleep(for: .seconds(3))
                await store.autoResolve(n)
                if args.contains("-autoExport") { store.export() }
            }
        }
    }

    private var driftSpeedup: Float {
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-driftSpeedup"), i + 1 < a.count, let v = Float(a[i + 1]) { return v }
        return 1
    }
}

struct MetricsPanel: View {
    @Environment(ProposalStore.self) private var store
    let onClose: () -> Void
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            VStack(alignment: .leading, spacing: 8) {
                Text("Router Metrics").font(.title3.bold())
                Text("Resolved \(store.resolved.count)/\(store.proposals.count) · session \(store.sessionLogs.count)").monospacedDigit()
                Text(String(format: "Decisions/min  %.1f", store.decisionsPerMinute)).monospacedDigit()
                Text(store.accuracy.map { String(format: "Accuracy vs GT  %.0f%%", $0 * 100) } ?? "Accuracy vs GT  —").monospacedDigit()
                if !store.lastAction.isEmpty { Text("Last: \(store.lastAction)").font(.caption).lineLimit(1) }
                @Bindable var s = store
                Toggle("Bias toward uncertain", isOn: $s.biasUncertain).font(.caption)
                Text("Pack: \(store.stream)").font(.caption.bold())
                HStack {
                    Button("Next Pack") { store.nextPack() }.font(.caption)
                    Button("Export") { store.export() }.font(.caption)
                }
                if !store.lastExport.isEmpty { Text(store.lastExport).font(.caption2) }
                Button("Close Space", action: onClose).font(.caption)
            }
            .frame(width: 300)
            .padding(16)
            .glassBackgroundEffect()
        }
    }
}

struct ProposalCard: View {
    let proposal: Proposal
    let rank: Int
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("#\(rank + 1) \(proposal.category.uppercased())").font(.title3.bold())
                Spacer()
                Text(proposal.type == .binary ? "BINARY" : "CATEGORY").font(.caption.bold())
                    .padding(.horizontal, 8).padding(.vertical, 2).background(.thinMaterial, in: Capsule())
            }
            Text("“\(proposal.evidence)”").font(.body).lineLimit(3)
            HStack {
                Text("conf \(Int(proposal.confidence * 100))%").font(.headline.monospacedDigit())
                ProgressView(value: Double(proposal.confidence)).frame(width: 80)
                Spacer()
                Text("→ \(proposal.recommended)").font(.headline)
            }
        }
        .frame(width: 400)
        .padding(16)
        .glassBackgroundEffect()
    }
}
