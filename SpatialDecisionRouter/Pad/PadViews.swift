#if !os(visionOS)
import SwiftUI

/// iPad / Mac (Designed for iPad): the crossroads as a flat, touch-first review console.
/// Sidebar = review queue (Up next, spot-checks, agents); detail = Now card + detail panel, or the Encounter Review board.
struct PadRootView: View {
    @Environment(RouterEngine.self) private var engine
    @State private var tab = "review"
    @State private var showStart = !(DemoState.on || ProcessInfo.processInfo.arguments.contains("-skipStart"))
    @State private var columns: NavigationSplitViewVisibility = ProcessInfo.processInfo.arguments.contains("-hideSidebar") ? .detailOnly : .automatic

    var body: some View {
        NavigationSplitView(columnVisibility: $columns) {
            PadSidebar(tab: $tab)
                .navigationTitle("Review queue")
                .navigationSplitViewColumnWidth(min: 320, ideal: 380, max: 460)
        } detail: {
            GeometryReader { geo in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if tab == "board" { ScrollView(.horizontal) { BoardView().frame(width: max(1040, geo.size.width - 40)) } } else { review(wide: geo.size.width > 1150) }
                    }
                    .padding(20)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .background(PadBackdrop())
            .navigationTitle(engine.config.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Picker("View", selection: $tab) {
                        Text("Review").tag("review"); Text(engine.config.terminology.boardTitle).tag("board")
                    }.pickerStyle(.segmented).frame(width: 340)
                }
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button("Enter Crossroads") { tap("enter") }
                        Button("Demo") { tap("demo") }
                        Button("Demo (auto-play)") { tap("demoAuto") }
                        Button("WERIAM Principal demo") { tap("weriamDemo") }
                        Button("Symbiosis demo") { tap("symbiosisDemo") }
                        Button("Home health") { tap("homeHealth") }
                        Button("Manifesto") { engine.showManifesto = true }
                        Button("Promotion") { engine.showPromotion = true }
                        Button("Lineage") { engine.showLineage = true }
                        if DomainCatalog.all.count > 1 { Button("Next Domain") { engine.nextDomain() } }
                        Button(engine.gameMode ? "Switch to Focus mode" : "Switch to Game mode") { engine.gameMode.toggle() }
                        Button("Export decisions") { engine.export() }
                    } label: { Label("Session", systemImage: "play.circle") }
                }
            }
        }
        .navigationSplitViewStyle(.prominentDetail)
        .buttonStyle(.bordered)
        .controlSize(.large)
        .preferredColorScheme(.dark)
        .sheet(isPresented: Binding(get: { engine.ringFor != nil }, set: { if !$0 { engine.ringFor = nil } })) {
            ScrollView { OptionRing().padding() }
                .presentationDetents([.medium, .large])
                .buttonStyle(.bordered).controlSize(.large).preferredColorScheme(.dark)
        }
        .fullScreenCover(isPresented: $showStart) { PadStartView { tap($0) } }
        .sheet(isPresented: Binding(get: { engine.showManifesto }, set: { engine.showManifesto = $0 })) { ManifestoView() }
        .sheet(isPresented: Binding(get: { engine.showPromotion }, set: { engine.showPromotion = $0 })) { PromotionView().preferredColorScheme(.dark).presentationSizing(.page) }
        .sheet(isPresented: Binding(get: { engine.showLineage }, set: { engine.showLineage = $0 })) { LineageView().preferredColorScheme(.light).presentationSizing(.page) }
        .onChange(of: engine.nowId) { _, id in   // -openSections "A,B": screenshot/test aid, re-opens detail sections on each Now card
            let a = ProcessInfo.processInfo.arguments
            guard id != nil, let i = a.firstIndex(of: "-openSections"), i + 1 < a.count else { return }
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(1.2))
                engine.sideTab = "details"; if !engine.detailOpen { engine.toggleDetail() }
                for k in a[i + 1].split(separator: ",").map(String.init) where engine.openSections[k] == nil { engine.toggleSection(k) }
            }
        }
        .task { while !Task.isCancelled { try? await Task.sleep(for: .milliseconds(50)); engine.tick(0.05) } }
        .task {
            engine.immersiveOpen = true   // the console is always "open" on iPad
            let a = ProcessInfo.processInfo.arguments
            if let i = a.firstIndex(of: "-autoTap"), i + 1 < a.count { try? await Task.sleep(for: .seconds(1)); tap(a[i + 1]) }
            if let i = a.firstIndex(of: "-tab"), i + 1 < a.count { tab = a[i + 1] }
            if DemoState.on && DemoState.auto { try? await Task.sleep(for: .seconds(3)); await engine.demoPlay()
                if a.contains("-boardAfterDemo") { tab = "board" }; return }
            if let i = a.firstIndex(of: "-autoResolve"), i + 1 < a.count, let n = Int(a[i + 1]) {
                try? await Task.sleep(for: .seconds(2)); await engine.autoResolve(n)
                if a.contains("-autoExport") { engine.export() }
            }
        }
    }

    @ViewBuilder private func review(wide: Bool) -> some View {
        let side = engine.spotCheckOpen || (engine.detailOpen && engine.nowHandoff != nil)
        if engine.domain.gameHUD() != nil { GameHUDStrip(); RevealBanner() }
        if wide && side {
            HStack(alignment: .top, spacing: 16) {
                SwipeCard().frame(maxWidth: .infinity)
                SidePanel().frame(width: 520)
            }
        } else {
            SwipeCard()
            if side { SidePanel() }
        }
        GameInsights()
        PadMiniBoard(tab: $tab)
        KeyboardShortcuts()
    }

    private func tap(_ which: String) {
        switch which {
        case "demo": engine.startDemo(auto: false)
        case "demoAuto": engine.startDemo(auto: true)
        case "weriamDemo": DomainCatalog.demoId = "weriam_principal"; engine.startDemo(auto: false)
        case "symbiosisDemo": DomainCatalog.demoId = "symbiosis"; engine.startDemo(auto: false)
        case "homeHealth": DemoState.on = false; engine.start(HomeHealthDomain())
        default: if DemoState.on { DemoState.on = false; engine.start(AIDocReviewDomain()) }
        }
        tab = "review"; showStart = false
    }
}

/// Start screen (same three entry points as the visionOS launcher).
struct PadStartView: View {
    @Environment(RouterEngine.self) private var engine
    let go: (String) -> Void
    var body: some View {
        ZStack {
            PadBackdrop()
            VStack(spacing: 22) {
                Image(systemName: "arrow.triangle.branch").font(.system(size: 64, weight: .semibold)).foregroundStyle(.teal)
                Text(engine.config.title).font(.sdrHuge).multilineTextAlignment(.center)
                Text(engine.config.agents.filter { $0.tier == 0 }.map(\.name).joined(separator: " · ")).font(.title3).foregroundStyle(.secondary)
                if engine.config.synthetic { Text(engine.config.terminology.syntheticBanner).foregroundStyle(.yellow) }
                HStack(spacing: 18) {
                    Button { go("enter") } label: { Text("Enter Crossroads").frame(minWidth: 180) }.buttonStyle(.borderedProminent)
                    Button { go("demo") } label: { Text("Demo").frame(minWidth: 120) }.tint(.yellow)
                    Button { go("demoAuto") } label: { Text("Demo (auto-play)").frame(minWidth: 160) }.tint(.orange)
                    Button { go("weriamDemo") } label: { Text("WERIAM Principal").frame(minWidth: 170) }.tint(.purple)
                    Button { go("symbiosisDemo") } label: { Text("Symbiosis").frame(minWidth: 140) }.tint(.orange)
                    Button { go("homeHealth") } label: { Text("Home health").frame(minWidth: 150) }.tint(.teal)
                }.font(.title2.bold()).buttonStyle(.bordered).controlSize(.extraLarge)
                Text("Demo: 6 scripted SYNTHETIC encounters · BN badge needs the risk sidecar. Home health uses Layer 1 (bridge on :8767, or the bundled snapshot).")
                    .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                Text("Not for clinical use").font(.caption.bold()).foregroundStyle(.red.opacity(0.8))
            }
            .padding(48).frame(maxWidth: 1040).sdrPanel().padding(30)
        }
        .preferredColorScheme(.dark)
    }
}

/// Queue column: Up next (tap to make Now), spot-checks, agent status.
struct PadSidebar: View {
    @Environment(RouterEngine.self) private var engine
    @Binding var tab: String
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                UpNextStrip()
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Agents").font(.title3.bold())
                        ForEach(engine.config.agents, id: \.id) { a in
                            AgentCard(agent: a, received: engine.inbox[a.id] ?? 0, queued: engine.queueCount(a.id))
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                if !engine.lastAction.isEmpty {
                    Text("last: \(engine.lastAction)").font(.caption).foregroundStyle(.secondary).lineLimit(2)
                }
            }.padding(14)
        }
        .background(PadBackdrop())
    }
}

/// Compact results strip under the card; tap to open the full board.
struct PadMiniBoard: View {
    @Environment(RouterEngine.self) private var engine
    @Binding var tab: String
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            let s = engine.stats
            Button { tab = "board" } label: {
                HStack(spacing: 22) {
                    m(engine.config.terminology.completedLabel, "\(s.completed)"); m("Decisions", "\(s.decisions)")
                    m("Corrections", "\(s.corrections)"); m("Prevented", "\(s.errorsPrevented)"); m("Misses", "\(s.misses)")
                    m("Auto-passed", "\(engine.autoPassed)")
                    Spacer()
                    Label("Open board", systemImage: "chart.bar.doc.horizontal").font(.headline)
                }.padding(14).frame(maxWidth: .infinity).foregroundStyle(.primary).contentShape(Rectangle())
            }.buttonStyle(.plain).sdrPanel().accessibilityIdentifier("openBoard")
        }
    }
    private func m(_ t: String, _ v: String) -> some View {
        VStack(spacing: 0) { Text(v).font(.title2.bold().monospacedDigit()); Text(t).font(.caption).foregroundStyle(.secondary) }
    }
}

/// Clinical, low-distraction backdrop (replaces the immersive environment).
struct PadBackdrop: View {
    var body: some View {
        LinearGradient(colors: [Color(red: 0.05, green: 0.09, blue: 0.13), Color(red: 0.03, green: 0.14, blue: 0.17)],
                       startPoint: .topLeading, endPoint: .bottomTrailing).ignoresSafeArea()
    }
}

/// Now card with swipe gestures: right = Pass, left = Flip (binary) / Modify (category), up = WAIT-like option.
struct SwipeCard: View {
    @Environment(RouterEngine.self) private var engine
    @State private var dx: CGFloat = 0
    var body: some View {
        NowCard()
            .offset(x: dx).rotationEffect(.degrees(Double(dx) / 40))
            .gesture(DragGesture(minimumDistance: 30).onChanged { v in dx = v.translation.width / 2 }.onEnded { v in
                defer { withAnimation(.spring) { dx = 0 } }
                guard let h = engine.nowHandoff, engine.phase[h.id] == .waiting else { return }
                if v.translation.width > 140 { engine.pass(h.id) }
                else if v.translation.width < -140 { h.link.answerType == .binary ? engine.flip(h.id) : engine.openRing(h.id) }
                else if v.translation.height < -140, let w = engine.registry.mainOptions(h.link).first(where: { $0.uppercased().hasPrefix("WAIT") || $0 == "Defer" }) { engine.select(h.id, w) }
            })
    }
}

/// Hardware-keyboard shortcuts: P pass · F flip/modify · 1–5 option · W wait/defer · R refuse/decline · E escalate · G game/focus
struct KeyboardShortcuts: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        ZStack {
            Button("") { act { engine.pass($0.id) } }.keyboardShortcut("p", modifiers: [])
            Button("") { act { $0.link.answerType == .binary ? engine.flip($0.id) : engine.openRing($0.id) } }.keyboardShortcut("f", modifiers: [])
            ForEach(1...5, id: \.self) { i in
                Button("") { act { h in let o = engine.registry.mainOptions(h.link); if i <= o.count { engine.select(h.id, o[i - 1]) } } }
                    .keyboardShortcut(KeyEquivalent(Character("\(i)")), modifiers: [])
            }
            Button("") { pick { $0.uppercased().hasPrefix("WAIT") || $0 == "Defer" } }.keyboardShortcut("w", modifiers: [])
            Button("") { pick { $0.hasPrefix("Refuse") || $0 == "Decline" } }.keyboardShortcut("r", modifiers: [])
            Button("") { act { engine.escalate($0.id) } }.keyboardShortcut("e", modifiers: [])
            Button("") { engine.gameMode.toggle() }.keyboardShortcut("g", modifiers: [])
        }.frame(width: 0, height: 0).opacity(0).accessibilityHidden(true)
    }
    private func act(_ f: (Handoff) -> Void) { if let h = engine.nowHandoff, engine.phase[h.id] == .waiting { f(h) } }
    private func pick(_ m: @escaping (String) -> Bool) { act { h in if let o = engine.registry.mainOptions(h.link).first(where: m) { engine.select(h.id, o) } } }
}
#endif
