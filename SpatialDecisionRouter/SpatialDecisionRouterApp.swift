import SwiftUI

@main
struct SpatialDecisionRouterApp: App {
    @State private var store = CrossroadsStore()
    var body: some Scene {
        WindowGroup(id: "main") { LauncherView().environment(store) }
            .defaultSize(width: 800, height: 360)
        ImmersiveSpace(id: "Router") { CrossroadsView().environment(store) }
            .immersionStyle(selection: .constant(.mixed), in: .mixed)
    }
}
