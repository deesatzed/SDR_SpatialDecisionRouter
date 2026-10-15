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
                        if DomainCatalog.all.count > 1 { Button("Next Domain") { engine.nextDomain() } }
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
        if wide && side {
            HStack(alignment: .top, spacing: 16) {
                NowCard().frame(maxWidth: .infinity)
                SidePanel().frame(width: 520)
            }
        } else {
            NowCard()
            if side { SidePanel() }
        }
        PadMiniBoard(tab: $tab)
    }

    private func tap(_ which: String) {
        switch which {
        case "demo": engine.startDemo(auto: false)
        case "demoAuto": engine.startDemo(auto: true)
        case "weriamDemo": DomainCatalog.demoId = "weriam_principal"; engine.startDemo(auto: false)
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
                }.font(.title2.bold()).buttonStyle(.bordered).controlSize(.extraLarge)
                Text("Demo: 6 scripted SYNTHETIC encounters · BN badge needs the risk_engine sidecar on this Mac (else fallback badge)")
                    .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                Text("Not for clinical use").font(.caption.bold()).foregroundStyle(.red.opacity(0.8))
            }
            .padding(48).frame(maxWidth: 820).sdrPanel().padding(30)
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
#endif
