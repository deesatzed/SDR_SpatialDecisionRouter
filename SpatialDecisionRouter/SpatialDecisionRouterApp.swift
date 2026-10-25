import SwiftUI

@main
struct SpatialDecisionRouterApp: App {
    @State private var engine = RouterEngine()
    var body: some Scene {
        #if os(visionOS)
        WindowGroup(id: "main") { LauncherView().environment(engine) }
            .defaultSize(width: 1180, height: 440)
        WindowGroup(id: "manifesto") { ManifestoView() }
            .defaultSize(width: 900, height: 760)
        WindowGroup(id: "promotion") { PromotionView().environment(engine) }
            .defaultSize(width: 1100, height: 820)
        WindowGroup(id: "lineage") { LineageView().environment(engine) }
            .defaultSize(width: 1200, height: 860)
        ImmersiveSpace(id: "Router") { CrossroadsView().environment(engine) }
            .immersionStyle(selection: Binding<any ImmersionStyle>(
                get: { engine.fullImmersion ? (FullImmersionStyle.full as any ImmersionStyle) : (MixedImmersionStyle.mixed as any ImmersionStyle) },
                set: { engine.fullImmersion = $0 is FullImmersionStyle }), in: .mixed, .full)
        #else
        WindowGroup(id: "main") { PadRootView().environment(engine) }   // iPad / Mac (Designed for iPad): flat 2D crossroads
        #endif
    }
}
