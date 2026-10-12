import SwiftUI

struct ContentView: View {
    @Environment(ProposalStore.self) private var store
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow

    var body: some View {
        Group {
            if store.immersiveOpen { compact } else { full }
        }
        .task {
            if ProcessInfo.processInfo.arguments.contains("-autoOpenImmersive"), !store.immersiveOpen { await toggle() }
        }
    }

    private var compact: some View {
        VStack(spacing: 8) {
            Text("Router").font(.headline)
            Text("\(store.resolved.count)/\(store.proposals.count) resolved").font(.caption.monospacedDigit())
            if !store.lastAction.isEmpty { Text(store.lastAction).font(.caption2).lineLimit(1) }
            Button("Close") { Task { await toggle() } }.font(.caption)
        }
        .padding(16)
        .frame(width: 240)
    }

    private var full: some View {
        VStack(spacing: 16) {
            Text("Spatial Decision Router").font(.extraLargeTitle2)
            Text("\(store.proposals.count) proposals loaded · \(store.stream) stream")
            if let err = store.loadError { Text(err).foregroundStyle(.red) }
            HStack {
                ForEach(Array(Set(store.proposals.map(\.category))).sorted(), id: \.self) { c in
                    Text("\(c): \(store.proposals.filter { $0.category == c }.count)")
                        .font(.caption).padding(6).background(.thinMaterial, in: Capsule())
                }
            }
            Button("Open Router Space") { Task { await toggle() } }.font(.title2)
            Text("Tap/pinch = accept · swipe left = reject · swipe right/up = recategorize · long-press = inspect")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .padding(40)
    }

    private func toggle() async {
        if store.immersiveOpen { await dismissImmersiveSpace(); store.immersiveOpen = false }
        else if case .opened = await openImmersiveSpace(id: "Router") { store.immersiveOpen = true; dismissWindow(id: "main") }
    }
}
