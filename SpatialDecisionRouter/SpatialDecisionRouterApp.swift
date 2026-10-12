import SwiftUI

@main
struct SpatialDecisionRouterApp: App {
    @State private var store = CrossroadsStore()
    var body: some Scene {
        WindowGroup(id: "main") { LauncherView().environment(store) }
            .defaultSize(width: 800, height: 360)
        ImmersiveSpace(id: "Router") { CrossroadsView().environment(store) }
            .immersionStyle(selection: Binding<any ImmersionStyle>(
                get: { store.fullImmersion ? (FullImmersionStyle.full as any ImmersionStyle) : (MixedImmersionStyle.mixed as any ImmersionStyle) },
                set: { store.fullImmersion = $0 is FullImmersionStyle }), in: .mixed, .full)
    }
}
