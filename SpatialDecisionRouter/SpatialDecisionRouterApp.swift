import SwiftUI

@main
struct SpatialDecisionRouterApp: App {
    @State private var store = ProposalStore()
    var body: some Scene {
        WindowGroup(id: "main") { ContentView().environment(store) }
            .defaultSize(width: 900, height: 520)
            .windowResizability(.contentSize)
            .defaultWindowPlacement { _, _ in WindowPlacement(.utilityPanel) }
        ImmersiveSpace(id: "Router") { ImmersiveRouterView().environment(store) }
            .immersionStyle(selection: .constant(.mixed), in: .mixed)
    }
}
