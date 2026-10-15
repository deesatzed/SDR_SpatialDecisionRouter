import SwiftUI

@main
struct SpatialDecisionRouterApp: App {
    @State private var engine = RouterEngine()
    var body: some Scene {
        #if os(visionOS)
        WindowGroup(id: "main") { LauncherView().environment(engine) }
            .defaultSize(width: 800, height: 360)
        WindowGroup(id: "manifesto") { ManifestoView() }
            .defaultSize(width: 900, height: 760)
        ImmersiveSpace(id: "Router") { CrossroadsView().environment(engine) }
            .immersionStyle(selection: Binding<any ImmersionStyle>(
                get: { engine.fullImmersion ? (FullImmersionStyle.full as any ImmersionStyle) : (MixedImmersionStyle.mixed as any ImmersionStyle) },
                set: { engine.fullImmersion = $0 is FullImmersionStyle }), in: .mixed, .full)
        #else
        WindowGroup(id: "main") { PadRootView().environment(engine) }   // iPad / Mac (Designed for iPad): flat 2D crossroads
        #endif
    }
}
